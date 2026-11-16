"""Rutas de informes clínicos escaneados: subir el original, leer su texto y verlo.

Por qué es un módulo aparte: un informe escaneado no es una ecografía ni una lectura. No se mide
ni entra en el análisis; se guarda, se firma y se lee. Comparte con la imagen el almacén de
binarios firmados por su hash (`record-integrity.md` §3.12), la lectura por trozos con tope y el
cupo de importaciones simultáneas, que se reutilizan de `routes.py`.

La excepción son las cifras de una analítica: se leen al subirla, quedan **por confirmar** dentro
del asiento del informe y solo entran en el análisis cuando una persona confirma cada una
(`POST /{índice}/labs/confirm`, `record-integrity.md` §3.21).
"""

from __future__ import annotations

import datetime as dt
import io
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.console_header import console_post
from app.api.mission import latest_identity
from app.api.routes import (
    CONSOLE_IDENTITY,
    SettingsDep,
    StoreDep,
    _import_slots,
    _read_capped,
    _unit_length_or_422,
    identity_for,
)
from app.core.ledger import sha256_hex
from app.core.storage import LabReadingConflict, ObservationStore
from app.ingest.codes import CATALOG
from app.ingest.fhir import Context, observation
from app.reports import deid, identity, incongruences, labs, ocr

reports_router = APIRouter(prefix="/reports")

# Un informe escaneado de unas decenas de páginas a 300 ppp cabe de sobra.
MAX_REPORT_BYTES = 32 * 1024 * 1024

# Qué es el documento, de una lista cerrada: el texto libre no sirve para ordenar ni buscar.
ReportKind = Literal["analitica", "informe-especialista", "alta", "otro"]

UNAVAILABLE_NOTE = (
    "OCR no disponible: no hay tesseract instalado en esta máquina. El informe se guarda y se "
    "ve; su texto no se extrae."
)


@reports_router.get("/ocr")
def ocr_status(settings: SettingsDep) -> dict[str, Any]:
    """Si hay OCR local. Sin él, la función se declara ausente, no se simula."""
    executable = ocr.find_tesseract(settings.tesseract_cmd)
    if executable is None:
        return {"available": False, "engine": None, "note": UNAVAILABLE_NOTE}
    try:
        engine = ocr.version(executable)
    except ocr.OcrUnavailable as exc:
        return {"available": False, "engine": None, "note": f"{UNAVAILABLE_NOTE} ({exc})"}
    return {"available": True, "engine": engine, "languages": ocr.LANGUAGES, "note": None}


@reports_router.post("", status_code=201, **console_post())
async def upload_report(
    request: Request,
    store: StoreDep,
    settings: SettingsDep,
    kind: ReportKind,
    recorded_by: Annotated[str, Query(min_length=1, max_length=64)],
    subject: Annotated[str, Query(min_length=1)] = "crew-01",
) -> dict[str, Any]:
    """Sube un informe (PDF, PNG, JPEG o TIFF), le saca el texto en local y lo firma todo."""
    media_type = request.headers.get("content-type", "").split(";")[0].strip()
    if media_type not in ocr.MEDIA_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"tipo no admitido: {media_type!r}. Admitidos: {', '.join(ocr.MEDIA_TYPES)}",
        )
    raw = await _read_capped(request, MAX_REPORT_BYTES)
    async with _import_slots:
        return await run_in_threadpool(
            _upload, store, settings.tesseract_cmd, raw, media_type, kind, subject, recorded_by
        )


def _upload(
    store: ObservationStore,
    tesseract_cmd: str | None,
    raw: bytes,
    media_type: str,
    kind: str,
    subject: str,
    recorded_by: str,
) -> dict[str, Any]:
    try:
        images = ocr.page_images(raw, media_type)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo al abrirlo es un original ilegible
        raise HTTPException(
            status_code=422, detail=f"no se puede abrir el documento: {exc}"
        ) from exc
    executable = ocr.find_tesseract(tesseract_cmd)
    try:
        pages = ocr.read(raw, media_type, executable)
        reading: dict[str, Any] = {
            "available": True,
            "engine": ocr.version(executable) if executable else "capa de texto del PDF",
            "languages": ocr.LANGUAGES,
            "min_confidence": ocr.MIN_CONFIDENCE,
            "pages": [_deidentified(page.as_payload()) for page in pages],
        }
    except ocr.OcrUnavailable as exc:
        pages = []
        reading = {"available": False, "note": f"{UNAVAILABLE_NOTE} ({exc})", "pages": []}
    # ¿Es de este tripulante? Sobre el texto leído antes de des-identificarlo, que es donde está
    # la filiación. El resultado no repite datos de otra persona (identidad_paciente de Polaris).
    text = "\n".join(str(page.text) for page in pages)
    patient = identity.check(text, latest_identity(store, subject))
    # Las cifras, también sobre el texto sin des-identificar: la des-identificación puede tapar
    # una fecha o un número que no identifica a nadie. Se guarda lo estructurado, no la línea.
    lab_readings = labs.extract(text)
    payload = {
        "subject": subject,
        "kind": kind,
        "media_type": media_type,
        "sha256": sha256_hex(raw),
        "size_bytes": len(raw),
        "pages": len(images),
        "source": CONSOLE_IDENTITY,
        "recorded_by": recorded_by,
        "ocr": reading,
        "identity": patient,
        "lab_readings": lab_readings,
    }
    entry = store.record_scanned_report(payload, raw, identity_for(CONSOLE_IDENTITY))
    low = [p["page"] for p in reading["pages"] if p.get("low_confidence")]
    return {
        "ledger_index": entry.index,
        "pages": len(images),
        "low_confidence_pages": low,
        "lab_readings": len(lab_readings["readings"]),
    }


def _deidentified(page: dict[str, Any]) -> dict[str, Any]:
    """El texto de la página sin identificadores; retenido si la des-identificación no verifica.

    Solo se firma el texto des-identificado: el que se muestra y viaja a Tierra. El original
    escaneado, que sí los lleva, se guarda aparte, en local y redactable.
    """
    result = deid.deidentify(str(page["text"]))
    return {
        **page,
        "text": result.text,
        "deidentification": {
            "redactions": result.redactions,
            "verified": result.verified,
            # Qué quedaba a la vista cuando se retuvo el texto: el tipo, nunca el dato.
            "remaining": list(result.remaining),
        },
    }


@reports_router.get("")
def list_reports(
    store: StoreDep, subject: Annotated[str, Query(min_length=1)] = "crew-01"
) -> list[dict[str, Any]]:
    """Informes vigentes de un tripulante, con su texto; sin el original.

    Cada lectura de analítica lleva su estado: `por_confirmar` o `confirmada` (con quién, cuándo y
    el asiento de la cifra). Lo confirmado lo dice el ledger, no el asiento del informe.
    """
    reports = store.scanned_reports(subject)  # copia: anotarla no toca el asiento firmado
    for report in reports:
        readings = (report.get("lab_readings") or {}).get("readings") or []
        if not readings:
            continue
        done = {
            item["reading_index"]: item for item in store.lab_confirmations(report["ledger_index"])
        }
        for position, item in enumerate(readings):
            confirmation = done.get(position)
            if confirmation is not None:
                item["status"] = "confirmada"
                item["confirmation"] = {
                    "confirmed_by": confirmation.get("confirmed_by"),
                    "value": confirmation.get("value"),
                    "observation_index": confirmation.get("observation_index"),
                    "ledger_index": confirmation.get("ledger_index"),
                }
    return reports


class LabConfirmIn(BaseModel):
    """Una persona confirma una cifra leída, con el papel delante.

    `value` y `unit` solo si corrige: una lectura de unidad de otra familia o censurada («<9») los
    exige; la unidad, si se da, tiene que ser la del catálogo (EMMA no convierte por su cuenta).
    `effective_date` hace falta si el informe no trae fecha de extracción legible.

    La unidad no lleva tope en el esquema: lo pone la ruta, con el de toda la API
    (`routes.UNIT_MAX_LENGTH`) y su motivo en español. El esquema tenía `max_length=32` y,
    pasado, respondía con la lista de errores de Pydantic (decimoctava ronda, §5.38.9).
    """

    model_config = ConfigDict(extra="forbid")

    reading_index: int = Field(ge=0)
    confirmed_by: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
    ]
    value: float | None = None
    unit: str | None = None
    effective_date: dt.date | None = None


@reports_router.post("/{ledger_index}/labs/confirm", status_code=201)
def confirm_lab_reading(
    store: StoreDep, ledger_index: int, body: LabConfirmIn
) -> dict[str, Any]:
    """Confirma una lectura: entra como observación firmada, con su confirmación, en un `commit`."""
    try:
        report, _ = store.report_blob(ledger_index)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    found = report.get("lab_readings") or {}
    readings = found.get("readings") or []
    if not body.reading_index < len(readings):
        raise HTTPException(
            status_code=404,
            detail=f"el informe {ledger_index} no tiene la lectura {body.reading_index}",
        )
    reading = readings[body.reading_index]
    code = CATALOG.get(str(reading.get("key")))
    if body.unit is not None and code is not None:
        # Antes que nada: una unidad gigante ni se compara ni se repite. Una clave fuera del
        # catálogo la rechaza `labs.confirmed_value`, con su motivo.
        _unit_length_or_422(code, body.unit)
    day = body.effective_date
    if day is None and found.get("date"):
        try:
            day = dt.date.fromisoformat(str(found["date"]))
        except ValueError:
            day = None
    if day is None:
        raise HTTPException(
            status_code=422,
            detail="el informe no trae fecha de extracción legible: indica la del papel",
        )
    try:
        value = labs.confirmed_value(reading, body.value, body.unit)
        reading_entry, origin = store.record_lab_reading(
            observation(
                str(reading["key"]), value, labs.effective_at(day), str(report["subject"]),
                source=f"analitica:{ledger_index}", context=Context.UNKNOWN,
            ),
            {
                "report_index": ledger_index,
                "reading_index": body.reading_index,
                "confirmed_by": body.confirmed_by,
                "value": value,
                "corrected": body.value is not None,
            },
            identity_for(CONSOLE_IDENTITY),
        )
    except LabReadingConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"observation_index": reading_entry.index, "ledger_index": origin.index}


@reports_router.get("/incongruences")
def report_incongruences(
    store: StoreDep, subject: Annotated[str, Query(min_length=1)] = "crew-01"
) -> dict[str, Any]:
    """Analíticas de la misma extracción que no dicen lo mismo (Polaris `incongruencias_caso`)."""
    reports = store.scanned_reports(subject)
    return {
        "incongruences": incongruences.find(reports),
        "undated_reports": incongruences.undated(reports),
        "tolerance": incongruences.RELATIVE_TOLERANCE,
    }


@reports_router.get("/{ledger_index}/pages/{page}")
def report_page(store: StoreDep, ledger_index: int, page: int) -> Response:
    """Una página del original como PNG, sacada del binario firmado recién comprobado."""
    try:
        payload, data = store.report_blob(ledger_index)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    try:
        images = ocr.page_images(data, str(payload["media_type"]))
    except ocr.PageTooLarge as exc:
        # Guardado antes del tope (2026-11-16): se dice, no se pinta.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not 1 <= page <= len(images):
        raise HTTPException(status_code=404, detail=f"el informe tiene {len(images)} páginas")
    buffer = io.BytesIO()
    images[page - 1].save(buffer, format="PNG")
    return Response(content=buffer.getvalue(), media_type="image/png")
