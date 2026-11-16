"""Rutas de ecografía: subir un estudio, listarlo y servir su imagen.

Por qué es un módulo aparte: la imagen tiene reglas propias —tope de tamaño mayor,
des-identificación, calibración— que no pintan nada en las rutas de constantes. Lo que sí
comparte con ellas se reutiliza de `routes.py`, no se copia: el almacén, las identidades de
firma, la lectura por trozos con tope y el cupo de importaciones simultáneas.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from app import committee_dossier, countersign_rule
from app.api.console_header import console_post
from app.api.routes import (
    CONSOLE_IDENTITY,
    SettingsDep,
    StoreDep,
    _import_slots,
    _read_capped,
    identity_for,
)
from app.core import egress
from app.core.config import Settings
from app.core.storage import ObservationStore
from app.evidence import vault
from app.evidence.source_check import (
    CITATION_MAX_BYTES,
    check_source,
    offline_checker,
    registry_checker,
)
from app.evidence.tier import grade
from app.imaging.dicom import (
    CalibratedRegion,
    NotUltrasoundError,
    UltrasoundStudy,
    read_ultrasound,
)
from app.imaging.measure import (
    ALERTING_NOTE,
    MEASURES,
    METHOD,
    Annotation,
    MeasurementError,
    Point,
    measure,
)
from app.imaging.phantom import PHANTOM_SOURCE, build
from app.imaging.protocols import PROTOCOLS, validate_findings
from app.imaging.render import UnrenderableError, frame_png
from app.imaging.samples import SAMPLE_SOURCE, SampleFileChanged, catalog
from app.imaging.samples import build as build_sample
from app.ingest.fhir import Context, observation
from app.interpret.draft import facts_for, generate
from app.interpret.llm import LlmUnavailable, LocalLlm

imaging_router = APIRouter(prefix="/imaging")

# TOPE DE UN ESTUDIO.
#
# Mayor que el de las importaciones de wearables porque un cine de ecografía pesa: un clip
# de unos segundos exportado con compresión JPEG ronda las decenas de MB. Sin comprimir, un
# clip largo puede pasar de este tope; la respuesta 413 lo dice, y la salida es exportar
# comprimido o un clip más corto. Con dos importaciones a la vez (`_import_slots`) el pico
# queda acotado a unos cientos de MB: el cuerpo, más la copia des-identificada.
MAX_IMAGING_BYTES = 128 * 1024 * 1024

# Fuente con la que firma un ecógrafo. Un ecógrafo concreto traería su clave aprovisionada.
ULTRASOUND_SOURCE = "ultrasound"


@imaging_router.get("/protocols")
def list_protocols() -> dict[str, Any]:
    """Protocolos ecográficos, sus medidas y el respaldo de cada parámetro del método.

    Un protocolo sin medidas se puede adquirir y ver, pero todavía no medir.
    """
    return {
        "protocols": [
            {
                "key": p.key,
                "display": p.display,
                "rationale": p.rationale,
                "views": [
                    {
                        "key": view.key,
                        "display": view.display,
                        "signs": [
                            {"key": sign.key, "display": sign.display, "values": sign.values}
                            for sign in view.signs
                        ],
                    }
                    for view in p.views
                ],
                "checklist": list(p.checklist),
                "sources": list(p.sources),
                # Nivel de evidencia de cada fuente: del registro de PubMed guardado o, sin PMID,
                # de la propia cita (solo puede marcarla preclínica).
                "source_grades": [grade(source) for source in p.sources],
                "measures": [
                    {
                        "name": spec.name,
                        "display": spec.display,
                        "lateral": spec.lateral,
                        "annotations": dict(spec.labels),
                        "instructions": dict(spec.instructions),
                    }
                    for spec in MEASURES.values()
                    if spec.protocol == p.key
                ],
            }
            for p in PROTOCOLS.values()
        ],
        "method": {name: param.to_dict() for name, param in METHOD.items()},
        "alerting": {"active": False, "note": ALERTING_NOTE},
    }


@imaging_router.post(
    "/studies",
    status_code=201,
    **console_post(
        requestBody={
            "required": True,
            "content": {"application/dicom": {"schema": {"type": "string", "format": "binary"}}},
        }
    ),
)
async def upload_study(
    request: Request,
    store: StoreDep,
    protocol: Annotated[str, Query(min_length=1)],
    subject: Annotated[str, Query(min_length=1)] = "crew-01",
    acquired: dt.datetime | None = None,
) -> dict[str, Any]:
    """Sube un DICOM de ecografía. Se des-identifica y entra en el ledger con su hash.

    `acquired` solo hace falta si el DICOM no fija la zona horaria de la adquisición. Si
    la fija y además se da `acquired`, manda el DICOM: es lo que registró el equipo.
    """
    if protocol not in PROTOCOLS:
        raise HTTPException(
            status_code=422,
            detail=f"protocolo desconocido: {protocol!r}. Admitidos: {', '.join(PROTOCOLS)}",
        )
    if acquired is not None and acquired.tzinfo is None:
        raise HTTPException(status_code=422, detail="`acquired` debe llevar zona horaria")
    raw = await _read_capped(request, MAX_IMAGING_BYTES)
    async with _import_slots:
        return await run_in_threadpool(_upload_study, store, raw, protocol, subject, acquired)


def _upload_study(
    store: ObservationStore,
    raw: bytes,
    protocol: str,
    subject: str,
    acquired: dt.datetime | None,
) -> dict[str, Any]:
    try:
        study = read_ultrasound(raw)
    except NotUltrasoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    moment = study.acquired or acquired
    if moment is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "el DICOM no fija la zona horaria de la adquisición: indica `acquired` "
                "con zona. Adivinarla desplazaría el estudio horas en la tendencia"
            ),
        )
    try:
        entry = store.record_imaging_study(
            _payload(study, protocol, subject, moment.astimezone(dt.UTC)),
            study.data,
            identity_for(ULTRASOUND_SOURCE),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "ledger_index": entry.index,
        "content_hash": entry.content_hash,
        "sha256": study.sha256,
        "calibrated": bool(study.regions),
        "burned_in_annotation": study.burned_in_annotation,
        "removed_elements": study.removed_elements,
    }


def _payload(
    study: UltrasoundStudy,
    protocol: str,
    subject: str,
    acquired: dt.datetime,
    source: str = ULTRASOUND_SOURCE,
) -> dict[str, Any]:
    return {
        "subject": subject,
        "protocol": protocol,
        "acquired": acquired.isoformat(),
        "source": source,
        "media_type": "application/dicom",
        "sha256": study.sha256,
        "size_bytes": len(study.data),
        "frames": study.frames,
        "rows": study.rows,
        "columns": study.columns,
        # Lista vacía = sin calibración: se puede ver, no se puede medir en mm.
        "calibration": [region.as_payload() for region in study.regions],
        "burned_in_annotation": study.burned_in_annotation,
        "deidentification": "PS3.15 basic profile, retain longitudinal full dates",
    }


# Quien firma lo simulado: la misma identidad que el simulador de constantes. Asi el modo de
# mision lo declara simulado y cambiar de escenario lo puede descartar sin tocar nada real.
SIMULATOR_SIGNER = "simulator"


def _signer_for(source: str) -> str:
    return SIMULATOR_SIGNER if source.split(":", 1)[0] == SIMULATOR_SIGNER else ULTRASOUND_SOURCE


@imaging_router.post("/phantom", status_code=201, **console_post())
def create_phantom(
    store: StoreDep,
    settings: SettingsDep,
    protocol: Annotated[str, Query(min_length=1)],
    subject: Annotated[str, Query(min_length=1)] = "crew-01",
) -> dict[str, Any]:
    """Registra un fantoma sintético del protocolo, con su medida real conocida.

    Entra por la misma des-identificación y el mismo ledger que un estudio real, pero firmado
    como simulado: nunca pasa por dato de un tripulante.
    """
    try:
        phantom = build(protocol)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc.args[0])) from exc
    study = read_ultrasound(phantom.data)
    acquired = _phantom_time(store, settings, subject)
    payload = {
        **_payload(study, protocol, subject, acquired, PHANTOM_SOURCE),
        "synthetic": True,
        "ground_truth": phantom.truth,
        "phantom_note": phantom.note,
    }
    entry = store.record_imaging_study(payload, study.data, identity_for(SIMULATOR_SIGNER))
    return {"ledger_index": entry.index, "ground_truth": phantom.truth}


@imaging_router.get("/samples")
def list_samples() -> list[dict[str, Any]]:
    """Ecografías reales de datasets abiertos que trae el paquete, con su cita y licencia."""
    return [sample.as_public() for sample in catalog()]


@imaging_router.post("/samples/{key}", status_code=201, **console_post())
def create_sample(
    store: StoreDep,
    settings: SettingsDep,
    key: str,
    subject: Annotated[str, Query(min_length=1)] = "crew-01",
) -> dict[str, Any]:
    """Registra una ecografía real de ejemplo, firmada como simulada y sin calibrar.

    Es de un paciente de un dataset público, no de este tripulante: por eso firma el simulador.
    La cita viaja en el asiento, no solo en la interfaz, para que acompañe al estudio allá
    donde se exporte.
    """
    try:
        sample, data = build_sample(key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except SampleFileChanged as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    study = read_ultrasound(data)
    acquired = _phantom_time(store, settings, subject)
    payload = {
        **_payload(study, sample.protocol, subject, acquired, SAMPLE_SOURCE),
        "synthetic": False,
        "sample": sample.key,
        "dataset": sample.dataset,
    }
    entry = store.record_imaging_study(payload, study.data, identity_for(SIMULATOR_SIGNER))
    return {"ledger_index": entry.index, "protocol": sample.protocol, "dataset": sample.dataset}


def _phantom_time(store: ObservationStore, settings: Settings, subject: str) -> dt.datetime:
    """Cuando se "adquiere" un fantoma: dentro de la linea de tiempo simulada.

    Con la hora real, un fantoma caia antes del inicio de la mision simulada y el reloj de
    mision salia negativo. Se fecha con la ultima lectura del tripulante, o con el inicio de
    la mision si aun no hay ninguna.
    """
    latest = store.query(subject, limit=1)
    if latest:
        return latest[-1].effective
    return dt.datetime.combine(settings.mission_start, dt.time(0, 0), tzinfo=dt.UTC)


@imaging_router.get("/studies")
def list_studies(
    store: StoreDep,
    subject: Annotated[str, Query(min_length=1)] = "crew-01",
    until: dt.datetime | None = None,
) -> list[dict[str, Any]]:
    """Estudios de imagen vigentes de un tripulante, del más antiguo al más reciente.

    Con `until`, solo los registrados a bordo hasta ese instante: los que Tierra ya puede
    haber recibido. Se filtra por el registro y no por la adquisición, porque lo que viaja
    es lo registrado.
    """
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    studies = store.imaging_studies(subject)
    if until is not None:
        studies = [s for s in studies if dt.datetime.fromisoformat(s["recorded"]) <= until]
    return sorted(studies, key=lambda study: str(study["acquired"]))


@imaging_router.get("/studies/{ledger_index}/dicom")
def study_dicom(store: StoreDep, ledger_index: int) -> Response:
    """El DICOM des-identificado, solo si sigue siendo el que firma su asiento."""
    try:
        payload, data = store.imaging_blob(ledger_index)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    return Response(
        content=data,
        media_type="application/dicom",
        headers={"X-Content-SHA256": str(payload["sha256"])},
    )


@imaging_router.get("/studies/{ledger_index}/frames/{frame}")
def study_frame(store: StoreDep, ledger_index: int, frame: int) -> Response:
    """Un fotograma como PNG, sacado del binario firmado recién comprobado."""
    try:
        _, data = store.imaging_blob(ledger_index)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    try:
        png = frame_png(data, frame)
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnrenderableError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    # El contenido de un asiento no cambia: se puede guardar en caché sin revalidar.
    return Response(
        content=png, media_type="image/png",
        headers={"Cache-Control": "private, max-age=86400, immutable"},
    )


# --------------------------------------------------------------------------- #
# Medidas
# --------------------------------------------------------------------------- #

# Más puntos que esto no es un contorno: es un cuerpo de petición inflado.
MAX_POINTS_PER_ANNOTATION = 200


class AnnotationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame: int = Field(default=0, ge=0)
    points: list[tuple[float, float]] = Field(max_length=MAX_POINTS_PER_ANNOTATION)


class MeasurementIn(BaseModel):
    """Calibres puestos por el operador sobre un estudio. Las coordenadas son píxeles."""

    model_config = ConfigDict(extra="forbid")

    measure: str
    laterality: Literal["right", "left"] | None = None
    annotations: dict[str, AnnotationIn] = Field(max_length=10)
    # Declarado, sin autenticar: la API no autentica operadores (record-integrity.md §7.5).
    measured_by: str = Field(min_length=1, max_length=128)
    context: Context = Context.UNKNOWN


@imaging_router.post("/studies/{ledger_index}/measurements", status_code=201)
def record_measurement(
    store: StoreDep, ledger_index: int, payload: MeasurementIn
) -> dict[str, Any]:
    """Mide sobre un estudio y registra la lectura con su procedencia.

    La lectura entra en el catálogo como cualquier otra y pasa por la misma línea base.
    Su procedencia —estudio, puntos, método— queda firmada al lado, en el mismo `commit`.
    """
    try:
        study, _ = store.imaging_blob(ledger_index)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc

    spec = MEASURES.get(payload.measure)
    if spec is not None and spec.protocol != study["protocol"]:
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{payload.measure}' es del protocolo '{spec.protocol}' y el estudio es "
                f"de '{study['protocol']}'"
            ),
        )
    annotations = {
        label: Annotation(item.frame, tuple(Point(x, y) for x, y in item.points))
        for label, item in payload.annotations.items()
    }
    try:
        result = measure(
            payload.measure, payload.laterality, annotations,
            _regions(study["calibration"]), int(study["frames"]),
        )
        # La lectura hereda la fuente del estudio: medir un fantoma da una lectura simulada.
        reading = observation(
            result.key, result.value, dt.datetime.fromisoformat(study["acquired"]),
            study["subject"], study["source"], payload.context,
        )
    except (MeasurementError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    provenance = {
        "study_index": ledger_index,
        "study_sha256": study["sha256"],
        "protocol": study["protocol"],
        "measure": payload.measure,
        "laterality": payload.laterality,
        "annotations": {
            label: {"frame": item.frame, "points": [[x, y] for x, y in item.points]}
            for label, item in payload.annotations.items()
        },
        "details": result.details,
        "method": {name: param.value for name, param in METHOD.items()},
        "measured_by": payload.measured_by,
    }
    try:
        reading_entry, origin_entry = store.record_measurement(
            reading, provenance, identity_for(_signer_for(study["source"]))
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "key": result.key,
        "value": result.value,
        "details": result.details,
        "observation_index": reading_entry.index,
        "provenance_index": origin_entry.index,
    }


@imaging_router.get("/studies/{ledger_index}/measurements")
def list_measurements(store: StoreDep, ledger_index: int) -> list[dict[str, Any]]:
    """Medidas vigentes de un estudio, con sus puntos para volver a dibujarlas."""
    return store.measurements(ledger_index)


def _regions(calibration: Any) -> list[CalibratedRegion]:
    """Las regiones calibradas tal como las firmó el asiento del estudio."""
    try:
        return [
            CalibratedRegion(
                int(r["x0"]), int(r["y0"]), int(r["x1"]), int(r["y1"]),
                float(r["mm_per_px_x"]), float(r["mm_per_px_y"]),
            )
            for r in calibration
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="calibración del estudio ilegible") from exc


# --------------------------------------------------------------------------- #
# Borrador de interpretacion (app/interpret/)
# --------------------------------------------------------------------------- #

# Quien firma lo que redacta el modelo local. No es una persona: sus borradores nacen
# "sin validar" y solo una firma humana (`CONSOLE_IDENTITY`) los cambia.
LLM_SIGNER = "interpretation-local"

UNAVAILABLE_NOTE = (
    "Interpretación asistida no disponible: no hay modelo de lenguaje local en marcha. Las "
    "medidas y su historial siguen disponibles; el borrador es una ayuda, no un requisito."
)


def _llm(settings: Settings) -> LocalLlm:
    try:
        return LocalLlm(settings.llm_url, settings.llm_model)
    except ValueError as exc:  # una URL que no es de loopback
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _committee(settings: Settings) -> list[LocalLlm]:
    """Los verificadores configurados; sin ninguno, verifica el propio redactor."""
    models = settings.llm_verifiers or [settings.llm_model]
    try:
        return [LocalLlm(settings.llm_url, model) for model in models]
    except ValueError as exc:  # una URL que no es de loopback
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _missing_models(settings: Settings) -> list[str]:
    return [
        llm.model for llm in [_llm(settings), *_committee(settings)] if not llm.available()
    ]


@imaging_router.get("/interpretation")
def interpretation_status(settings: SettingsDep) -> dict[str, Any]:
    """Si están el redactor y todo el comité. Si falta uno, la función se declara ausente."""
    missing = _missing_models(settings)
    return {
        "available": not missing,
        "model": settings.llm_model,
        "committee": [llm.model for llm in _committee(settings)],
        "missing": missing,
        "note": None if not missing else f"{UNAVAILABLE_NOTE} Falta: {', '.join(missing)}.",
    }


@imaging_router.post("/studies/{ledger_index}/draft", status_code=201, **console_post())
def request_draft(store: StoreDep, settings: SettingsDep, ledger_index: int) -> dict[str, Any]:
    """Pide al modelo local un borrador sobre las medidas del estudio.

    Si alguna barrera automática lo bloquea, no se devuelve el texto: queda en el registro la
    constancia de que se bloqueó y por qué, y la respuesta es 422 con los motivos.
    """
    try:
        facts = facts_for(store, ledger_index)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        outcome = generate(_llm(settings), facts, _committee(settings))
    except LlmUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"{UNAVAILABLE_NOTE} ({exc})") from exc

    base = {
        "study_index": ledger_index,
        "model": settings.llm_model,
        "facts_sha256": outcome.facts_sha256,
        "committee": outcome.committee,
        "verifier_problems": outcome.verifier_problems,
        # Objeciones sin cita en el borrador: no bloquean, pero quedan para auditarlas.
        "discarded_objections": outcome.discarded_objections,
        # Las mismas objeciones, estructuradas, para el dosier del comité (`committee_dossier`).
        "objections": outcome.objections,
        # Lo que Polaris marcaría y EMMA no bloquea: para quien firma (text_guard.advisories).
        "language_notes": outcome.language_notes,
    }
    signer = identity_for(LLM_SIGNER)
    if outcome.blocked:
        entry = store.record_draft(
            {**base, "status": "blocked", "reasons": outcome.blocked_reasons}, signer
        )
        raise HTTPException(
            status_code=422,
            detail=(
                f"borrador bloqueado (asiento {entry.index}): "
                + "; ".join(outcome.blocked_reasons)
            ),
        )
    entry = store.record_draft(
        {
            **base,
            "status": "unvalidated",
            "text": outcome.text,
            "sections": {
                key: outcome.sections[key]
                for key in ("resumen", "evolucion", "limitaciones", "preguntas")
            },
        },
        signer,
    )
    return {"ledger_index": entry.index, "status": "unvalidated", "text": outcome.text}


@imaging_router.get("/studies/{ledger_index}/drafts")
def list_drafts(store: StoreDep, ledger_index: int) -> list[dict[str, Any]]:
    """Borradores del estudio, con su firma si la tienen. Los bloqueados, sin texto.

    Cada uno con el dosier de su comité (`committee_dossier`, Polaris `paso_consolidacion`).

    Y con la regla de la segunda firma (`countersign_rule`): sus textos, para que la consola los
    pinte, y —derivado aquí, al leer, sin tocar el asiento— el rótulo de una contrafirma que se
    admitió con la regla anterior al 2026-10-13 (cita no localizada, o frase no declarada vista),
    y si la contrafirma se cotejó con la frase de un informe o, si no, por qué
    (`countersign_collation`).
    """
    return [
        {
            **draft,
            "dossier": committee_dossier.dossier(draft),
            "second_signature_rule": countersign_rule.describe(),
            "countersign_note": countersign_rule.prior_rule_note(draft.get("countersign")),
            "countersign_collation": countersign_rule.collation(draft.get("countersign")),
        }
        for draft in store.drafts(ledger_index)
    ]


class SeenQuote(BaseModel):
    """Lo que quien firma vio en `source-quote`: se firma lo que se vio, como con `text_sha256`."""

    model_config = ConfigDict(extra="forbid")

    estado: Literal["localizada", "no_localizada"]
    frase: str = Field(default="", max_length=4000)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class SignoffIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["accepted", "rejected"]
    # Declarado, sin autenticar, como el resto de acciones de consola.
    signed_by: str = Field(min_length=1, max_length=128)
    comment: str = Field(default="", max_length=1000)
    # La huella del texto que se leyó, tal como la da la lista de borradores.
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    # La fuente en la que se apoya la decisión (PMID, DOI, NCT, una contramedida…). Opcional; si
    # trae un identificador externo, se comprueba que exista, sin bloquear la firma.
    source: str = Field(default="", max_length=500)
    # Si la fuente es un informe escaneado (`informe:<n>`), el fragmento que se cita de él: se
    # coteja que esté dentro (`evidence/vault.py`, Polaris `fuente_clinica`).
    source_fragment: str = Field(default="", max_length=500)
    # Lo que quien firma declara haber visto en `source-quote`, si cita un informe. En la primera
    # firma es opcional (con él, el asiento lleva la frase); en la segunda, obligatorio.
    seen_quote: SeenQuote | None = None


def _source_check(
    settings: Settings, source: str, store: ObservationStore | None = None,
    draft_index: int | None = None, fragment: str = "", who: str = "?",
) -> dict[str, Any]:
    """La fuente de una firma: un informe se coteja por dentro; PMID, DOI y NCT, en su registro.

    `_existencia_citas` de Polaris con el comprobador de EMMA; sin red, `no_resoluble`.
    """
    index = vault.report_index(source)
    if index is not None and store is not None and draft_index is not None:
        return vault.check(store, index, fragment, store.draft_subject(draft_index), who)
    if settings.offline or not source.strip():
        return check_source(source, offline_checker)
    # Un registro de citas responde JSON de kilobytes; la página de doi.org, HTML de unos cientos.
    with egress.client(settings, "citations", max_bytes=CITATION_MAX_BYTES) as client:
        return check_source(source, registry_checker(client))


@imaging_router.post("/drafts/{draft_index}/sign", status_code=201)
def sign_draft(
    store: StoreDep, settings: SettingsDep, draft_index: int, payload: SignoffIn
) -> dict[str, Any]:
    """Aceptar o rechazar un borrador. Es lo único que lo saca de "sin validar".

    La fuente es opcional y nunca bloquea esta firma. Si cita un informe y quien firma declara la
    frase que vio (`seen_quote`, de `source-quote`), el asiento lleva la frase literal de la
    bóveda; si la bóveda ya no da eso, 409. Sin `seen_quote` la bóveda no entrega texto y el
    asiento es el de siempre: no queda una línea de lectura de una frase que nadie pidió ver.
    """
    try:
        report = vault.report_index(payload.source)
        seen = payload.seen_quote
        if report is None or seen is None:
            check, quote = _checked(store, settings, draft_index, payload), None
        else:
            check, quote = vault.locate(
                store, report, payload.source_fragment, store.draft_subject(draft_index),
                payload.signed_by,
            )
        entry = store.sign_draft(
            draft_index, payload.decision, payload.signed_by, payload.comment,
            identity_for(CONSOLE_IDENTITY), payload.text_sha256,
            source=payload.source, source_check=check, source_quote=quote,
            seen_quote=seen.model_dump() if quote is not None and seen is not None else None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ledger_index": entry.index, "decision": payload.decision}


def _checked(
    store: ObservationStore, settings: Settings, draft_index: int, payload: SignoffIn
) -> dict[str, Any]:
    return _source_check(settings, payload.source, store, draft_index,
                         payload.source_fragment, payload.signed_by)


class SourceQuoteIn(BaseModel):
    """La cita que se quiere ver en el informe antes de firmar."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(max_length=500)
    source_fragment: str = Field(default="", max_length=500)
    # Queda en el registro de accesos de la bóveda. Declarado, sin autenticar.
    signed_by: str = Field(min_length=1, max_length=128)


# Una fuente que no es un informe no tiene frase que enseñar: no se abre nada ni se sale a la red.
_NO_QUOTE = {"estado": "no_aplica", "frase": "", "detalle": "la fuente no es un informe escaneado"}


@imaging_router.post("/drafts/{draft_index}/source-quote")
def source_quote(store: StoreDep, draft_index: int, payload: SourceQuoteIn) -> dict[str, Any]:
    """La frase literal que la bóveda da para una cita `informe:<n>`, antes de firmar.

    Es el texto des-identificado del informe, tal cual; si la cita no se localiza, lo dice y no
    devuelve frase (`evidence/vault.py`, `locate`). No escribe en el ledger: es una lectura, que
    deja su línea en el registro de accesos de la bóveda.
    """
    try:
        subject = store.draft_subject(draft_index)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    index = vault.report_index(payload.source)
    check: dict[str, Any] | None = None
    quote = dict(_NO_QUOTE)
    if index is not None:
        check, quote = vault.locate(
            store, index, payload.source_fragment, subject, payload.signed_by)
    # Si con esta cita se podrá poner la segunda firma, y si no, por qué: el mismo texto del 422.
    # Sin fuente, el motivo es que no cita nada, no que cite algo que no es un informe.
    cited = quote if payload.source.strip() else None
    return {"source": payload.source.strip(), "source_check": check, "quote": quote,
            "second_signature": countersign_rule.gate(cited)}


def _not_collatable(source: str) -> dict[str, Any] | None:
    """Lo que se sabe de una fuente citada que no es un informe; None si no cita nada.

    Desde el 2026-10-15 la segunda firma la rechaza (`countersign_rule.refusal`): esto solo
    distingue el motivo, citar otra cosa o no citar nada.
    """
    if not source.strip():
        return None
    return {**_NO_QUOTE, "detalle": countersign_rule.NOT_COLLATABLE_DETAIL}


@imaging_router.post("/drafts/{draft_index}/countersign", status_code=201)
def countersign_draft(store: StoreDep, draft_index: int, payload: SignoffIn) -> dict[str, Any]:
    """Segunda firma, de otra persona, cuando la primera registró una decisión de alto riesgo.

    Tiene que citar un informe guardado (`informe:<n>`), la única fuente que se puede cotejar, y
    la regla es estricta (`app/countersign_rule.py`): la cita tiene que localizarse en el informe
    y la firma tiene que declarar la frase que vio (`seen_quote`; decisión del usuario,
    2026-10-13). Si no, 422 con el motivo y ningún asiento. Si declara lo que vio y la bóveda ya
    no da eso, 409, como antes. La frase literal, su puntero y la huella del texto quedan en el
    asiento, y la respuesta dice que se cotejó (`collation`, el mismo texto que la lista).

    Desde el 2026-10-15 (decisión del usuario) lo que NO se puede cotejar también se rechaza:
    una fuente que no es un informe guardado (PMID, DOI, NCT, una contramedida), o ninguna, no
    tiene frase que localizar; 422 con el motivo y ningún asiento. Como no se va a escribir, esa
    fuente no se consulta en su registro: la ruta no sale a la red para rechazar. Quien rechaza
    es el almacén, después de sus comprobaciones de siempre (409).
    """
    check: dict[str, Any] | None = None
    try:
        report = vault.report_index(payload.source)
        if report is None:
            quote = _not_collatable(payload.source)
        else:
            check, quote = vault.locate(
                store, report, payload.source_fragment, store.draft_subject(draft_index),
                payload.signed_by,
            )
        seen = payload.seen_quote
        entry = store.countersign_draft(
            draft_index, payload.decision, payload.signed_by, payload.comment,
            identity_for(CONSOLE_IDENTITY), payload.text_sha256,
            source=payload.source, source_check=check, source_quote=quote,
            seen_quote=seen.model_dump() if seen is not None else None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except countersign_rule.CountersignRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    signed = entry.payload if isinstance(entry.payload, dict) else None
    return {"ledger_index": entry.index, "decision": payload.decision,
            "collation": countersign_rule.collation(signed)}


# --------------------------------------------------------------------------- #
# Signos anotados y lista de calidad
# --------------------------------------------------------------------------- #


class FindingsIn(BaseModel):
    """Lo que el operador ve en cada ventana, y si la adquisición cumple la lista de calidad."""

    model_config = ConfigDict(extra="forbid")

    # Cada punto de la lista de calidad del protocolo, con si se cumplió.
    checklist: dict[str, bool] = Field(max_length=20)
    # ventana -> signo -> valor. Vacío en los protocolos que se miden en vez de anotarse.
    findings: dict[str, dict[str, str]] = Field(default_factory=dict, max_length=20)
    # Declarado, sin autenticar, como el resto de acciones de consola.
    recorded_by: str = Field(min_length=1, max_length=128)


@imaging_router.post("/studies/{ledger_index}/findings", status_code=201)
def record_findings(store: StoreDep, ledger_index: int, payload: FindingsIn) -> dict[str, Any]:
    """Registra los signos anotados y la lista de calidad de un estudio.

    Todo el formulario o nada: cada punto de la lista y cada signo de cada ventana tienen que
    venir contestados. Un signo sin contestar no se guarda como "ausente".
    """
    try:
        study, _ = store.imaging_blob(ledger_index)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    protocol = PROTOCOLS[str(study["protocol"])]
    problems = validate_findings(protocol, payload.findings)
    if set(payload.checklist) != set(protocol.checklist):
        problems.append("la lista de calidad tiene que contestar todos sus puntos, y solo esos")
    if problems:
        raise HTTPException(status_code=422, detail="; ".join(problems))
    entry = store.record_findings(
        {
            "study_index": ledger_index,
            "study_sha256": study["sha256"],
            "protocol": protocol.key,
            "checklist": [
                {"item": item, "done": payload.checklist[item]} for item in protocol.checklist
            ],
            "findings": payload.findings,
            "recorded_by": payload.recorded_by,
        },
        identity_for(CONSOLE_IDENTITY),
    )
    return {"ledger_index": entry.index}


@imaging_router.get("/studies/{ledger_index}/findings")
def list_findings(store: StoreDep, ledger_index: int) -> list[dict[str, Any]]:
    """Hallazgos anotados en el estudio, del más antiguo al más reciente."""
    return store.findings(ledger_index)

