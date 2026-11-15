"""Rutas del mapa corporal de dolor: qué se puede marcar, registrar un informe y leerlos.

Por qué es un módulo aparte: el informe de dolor tiene su propio asiento en el ledger y sus
propias listas cerradas. Lo que comparte con las constantes —el almacén, las identidades de
firma, el instante de la lectura— se reutiliza de `routes.py`, no se copia.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app import voice
from app.api.routes import (
    SettingsDep,
    StoreDep,
    _read_capped,
    _recorded_or_422,
    _when,
    identity_for,
)
from app.core import i18n
from app.ingest.fhir import observation
from app.pain.alarm import DISCUSS_NOTE, discuss
from app.pain.catalog import MAX_INTENSITY, ZONES, describe, validate_zones

pain_router = APIRouter(prefix="/pain")

# Fuente con que se firman los informes. Reservada: la ingesta genérica no puede firmar así
# (`routes._is_reserved_source`).
PAIN_REPORT_SOURCE = "pain-report"


class PainZoneIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone: str
    # Entero: la escala numérica verbal no tiene decimales. De 1 en adelante, porque una
    # zona marcada con 0 no es una zona que duela (`validate_zones`).
    intensity: int = Field(ge=0, le=MAX_INTENSITY)
    characters: list[str] = Field(default_factory=list, max_length=10)


class PainReportIn(BaseModel):
    """Un informe de dolor. Sin zonas significa "no me duele nada", y registra un 0.

    Que no se envíe informe **no** es un cero: es que no se preguntó.
    """

    model_config = ConfigDict(extra="forbid")

    zones: list[PainZoneIn] = Field(max_length=len(ZONES))
    subject: str = Field(default="crew-01", min_length=1)
    # Declarado, sin autenticar, como el resto de acciones de consola.
    reported_by: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
    ]
    effective: dt.datetime | None = None
    # Lo que el tripulante quiera añadir con sus palabras. Si viene de un audio (`app/voice.py`),
    # `note_origin` lo dice: un modelo lo transcribió y la persona lo revisó antes de enviarlo.
    # `asistente-confirmada` (2026-11-03): el asistente de voz preparó el informe con lo que dijo
    # la persona, que es la nota, y ella lo confirmó antes de enviarlo (`app/assistant/`).
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None
    note_origin: Literal["escrita", "dictada-revisada", "asistente-confirmada"] | None = None

    @field_validator("reported_by")
    @classmethod
    def _has_text(cls, value: str) -> str:
        if not any(character.isalnum() for character in value):
            raise ValueError("debe contener al menos una letra o una cifra")
        return value


@pain_router.get("/catalog")
def pain_catalog() -> dict[str, object]:
    """Zonas del mapa corporal, tipos de dolor y escala, con los nombres que se muestran."""
    return describe()


@pain_router.post("/reports", status_code=201)
def record_pain_report(
    store: StoreDep, settings: SettingsDep, payload: PainReportIn
) -> dict[str, Any]:
    """Registra un informe de dolor: la intensidad máxima como lectura y el informe firmado."""
    problems = validate_zones(
        [(zone.zone, zone.intensity, zone.characters) for zone in payload.zones]
    )
    if problems:
        raise HTTPException(status_code=422, detail="; ".join(problems))

    effective = _when(payload.effective)
    peak = max((zone.intensity for zone in payload.zones), default=0)
    reading = observation(
        key="pain-intensity",
        value=float(peak),
        effective=effective,
        subject=payload.subject,
        source=PAIN_REPORT_SOURCE,
        # Autoinforme de una persona real: su entorno es el del despliegue.
        evidence_context=settings.deployment_context,
    )
    report = {
        "subject": payload.subject,
        "effective": effective.isoformat(),
        "reported_by": payload.reported_by,
        "zones": [
            {"zone": zone.zone, "intensity": zone.intensity, "characters": zone.characters}
            for zone in payload.zones
        ],
    }
    if payload.note:
        report["note"] = payload.note
        report["note_origin"] = payload.note_origin or "escrita"
    written = _recorded_or_422(
        lambda: list(
            store.record_pain_report(reading, report, identity_for(PAIN_REPORT_SOURCE))
        )
    )
    return {
        "recorded": [entry.index for entry in written],
        "intensity": peak,
        **_discussion(report),
    }


def _discussion(report: dict[str, Any]) -> dict[str, Any]:
    """Marca informativa, calculada al leer desde lo firmado: no es una alerta (invariante 5)."""
    reasons = discuss(report)
    # Las frases se cotejan en castellano (`pain/alarm.py`); el idioma se pone aquí, al servir.
    return {
        "discuss": {
            "reasons": [i18n.loc(reason) for reason in reasons],
            "note": i18n.loc(DISCUSS_NOTE) if reasons else None,
        }
    }


@pain_router.get("/reports")
def list_pain_reports(
    store: StoreDep,
    subject: str = "crew-01",
    until: Annotated[dt.datetime | None, Query()] = None,
) -> list[dict[str, Any]]:
    """Informes vigentes, del más antiguo al más reciente.

    `until` es para la consola de Tierra: lo registrado a bordo después de ese
    instante todavía no ha llegado.
    """
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    reports = [{**report, **_discussion(report)} for report in store.pain_reports(subject)]
    if until is None:
        return reports
    return [r for r in reports if dt.datetime.fromisoformat(r["recorded"]) <= until]


@pain_router.get("/voice")
def voice_status() -> dict[str, object]:
    """Si se puede dictar la nota (Whisper local instalado). Sin él, se declara ausente."""
    return {"available": voice.ready(), "model": voice.MODEL}


@pain_router.post("/voice")
async def transcribe_note(request: Request) -> dict[str, object]:
    """Un audio Ogg/Opus a texto, como **borrador** de la nota: no se firma ni se guarda aquí."""
    raw = await _read_capped(request, voice.MAX_BYTES)
    try:
        text = await run_in_threadpool(voice.transcribe, raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except voice.VoiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"draft": text, "model": f"whisper {voice.MODEL}", "origin": "dictada-revisada"}

