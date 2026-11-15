"""Las anclas de módulo: declararlas, leerlas y recibir lo que oye un receptor.

Por qué existe (decisión del usuario, 2026-11-10): la ubicación de la tripulación tiene que ser
real, no simulada, y viable en el espacio. Tres rutas, y ninguna escribe fuera del ledger
(invariante 4):

- `POST /api/location/anchors`: una persona declara en la consola que un ancla (equipo fijo de la
  nave) está en un módulo desde un instante. Firmada por la consola, como un vínculo de sensor
  (`api/sensor_bindings.py`): manda la última firmada y no se borra nada.
- `GET /api/location/anchors`: las vigentes, con en qué se basa la estimación.
- `POST /api/location/sightings`: un lote de lo que oyó el receptor de un tripulante (el wearable
  o la pasarela `scripts/anchor_gateway.py`, que solo escuchan). UN asiento por lote, firmado
  como `location-anchors`. Un ancla que nadie ha declarado se guarda igual y se dice, pero no se
  usa al estimar.

Lo que se estima con esto (`analysis/location.py`) es solo el módulo, solo ordena hipótesis y no
entra en ningún nivel ni en ninguna alerta (invariante 5).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.analysis.location import LOCATION_BASIS, SENSING_PATH, sensing
from app.api.mission import anchor_declarations
from app.api.routes import (
    CONSOLE_IDENTITY,
    StoreDep,
    _device_or_422,
    _recorded_or_422,
    identity_for,
)
from app.core import i18n
from app.core.identities import ANCHOR_IDENTITY
from app.environment.habitat import module_display
from app.ingest import location_anchors as anchor_rules
from app.ingest.wearable import EARLIEST_IMPORTED_READING, MAX_CLOCK_SKEW

location_router = APIRouter()

Operator = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Subject = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=anchor_rules.MAX_SUBJECT_LENGTH
    ),
]


def _aware(value: dt.datetime) -> dt.datetime:
    return anchor_rules.aware(value)


class AnchorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor_id: str
    module: str
    # Desde cuándo está ahí, que no tiene por qué ser el instante de la firma.
    since: dt.datetime
    declared_by: Operator

    _since = field_validator("since")(_aware)

    @field_validator("anchor_id")
    @classmethod
    def _anchor(cls, value: str) -> str:
        return anchor_rules.anchor_key(value)


class SightingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor_id: str
    rssi_dbm: float
    at: dt.datetime

    @field_validator("anchor_id")
    @classmethod
    def _anchor(cls, value: str) -> str:
        return anchor_rules.anchor_key(value)

    @field_validator("rssi_dbm", mode="before")
    @classmethod
    def _rssi(cls, value: Any) -> float:
        # Antes de que Pydantic convierta `true` en 1.0: un booleano no es una lectura.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("el RSSI es un número de dBm")
        return anchor_rules.check_rssi(value)

    @field_validator("at")
    @classmethod
    def _plausible(cls, value: dt.datetime) -> dt.datetime:
        """La misma ventana de verosimilitud que una lectura de wearable (`ingest/wearable.py`):
        un reloj de receptor mal puesto no puede mover al futuro la estimación del estado."""
        utc = _aware(value).astimezone(dt.UTC)
        if not EARLIEST_IMPORTED_READING <= utc <= dt.datetime.now(dt.UTC) + MAX_CLOCK_SKEW:
            raise ValueError(f"fecha {utc.isoformat()} fuera del intervalo admitido")
        return utc


class SightingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: Subject
    # Opcional, como en la ingesta de wearables: el receptor que oyó, si quien envía lo pone.
    device: str | None = None
    sightings: list[SightingIn] = Field(min_length=1, max_length=anchor_rules.MAX_SIGHTINGS)


@location_router.post("/location/anchors", status_code=201)
def declare_anchor(store: StoreDep, payload: AnchorIn) -> dict[str, Any]:
    """Firma lo que una persona declara: esta ancla está en este módulo. 422 si no se puede."""
    entry = _recorded_or_422(
        lambda: store.record_location_anchor(
            payload.anchor_id, payload.module, payload.since, payload.declared_by,
            identity_for(CONSOLE_IDENTITY),
        )
    )[0]
    return {"ledger_index": entry.index}


@location_router.get("/location/anchors")
def read_anchors(
    store: StoreDep,
    # Lo que Tierra puede tener: hasta el corte del retardo, como `/api/sensor-bindings`.
    until: dt.datetime | None = None,
) -> dict[str, Any]:
    """Las anclas vigentes y en qué se basa la estimación.

    Vigente es lo que usa la estimación (`analysis.location.module_of`): de las declaraciones de
    cada ancla con `since` ≤ ahora (o el corte de Tierra), la de asiento posterior. Una declarada
    para más adelante todavía no sale.
    """
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    moment = until or dt.datetime.now(dt.UTC)
    latest: dict[str, Any] = {}
    for item in anchor_declarations(store, until):
        if item.since > moment:
            continue
        if item.anchor_id not in latest or item.order > latest[item.anchor_id].order:
            latest[item.anchor_id] = item
    params = sensing()
    # El idioma se pone aquí, al servir, y no en `sensing()`, que está cacheada. El inglés de la
    # base y el de `location_sensing.json` son de quien los declara (`analysis/location.py` y su
    # hermano `.en.json`): mientras no existan, estas llamadas devuelven el castellano tal cual.
    return {
        "anchors": [
            {
                "anchor_id": item.anchor_id,
                "module": item.module,
                "display": module_display(item.module),
                "since": item.since.isoformat(),
                "ledger_index": item.order,
            }
            for item in sorted(latest.values(), key=lambda item: item.anchor_id)
        ],
        "basis": i18n.loc(LOCATION_BASIS),
        "parameters": {
            "window_s": params.window_s,
            "margin_db": params.margin_db,
            "min_dwell_s": params.min_dwell_s,
            "stale_after_s": params.stale_after_s,
            "min_rssi_dbm": params.min_rssi_dbm,
            "evidence": params.evidence,
            "evidence_note": i18n.localized(params.evidence_note, SENSING_PATH),
        },
        "sources": i18n.localized(list(params.basis), SENSING_PATH),
        "not_coded": i18n.localized(params.not_coded, SENSING_PATH),
    }


@location_router.post("/location/sightings", status_code=201)
def submit_sightings(store: StoreDep, payload: SightingsIn) -> dict[str, Any]:
    """Firma un lote de lo que oyó el receptor de un tripulante: un asiento, todo el lote."""
    device = _device_or_422(payload.device)
    entry = _recorded_or_422(
        lambda: store.record_location_sightings(
            payload.subject,
            [(item.anchor_id, item.rssi_dbm, item.at) for item in payload.sightings],
            identity_for(ANCHOR_IDENTITY),
            device=device,
        )
    )[0]
    known = {item.anchor_id for item in anchor_declarations(store)}
    unknown = sorted({item.anchor_id for item in payload.sightings} - known)
    return {
        "ledger_index": entry.index,
        "accepted": len(payload.sightings),
        "unknown_anchors": unknown,
    }
