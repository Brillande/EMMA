"""El vínculo sensor-tripulante: declararlo, leerlo y avisar en la ingesta (`ingest/bindings.py`).

Por qué existe: la especificación del equipo pide «sensor bindings» en el astronauta (§3) y EMMA
no comprueba quién lleva puesto un reloj. Lo que sí puede hacer es dejar que una persona lo
declare, firmarlo en el registro y enseñarlo con ese rótulo. Dos rutas: una escribe UN asiento
por declaración, firmado por la consola como las demás acciones del operador; la otra lee los
vínculos vigentes y su historial. El aviso de la ingesta no está aquí: lo adjuntan las tres
rutas de ingesta de wearables (`api/routes.py`, `_binding_notice`) DESPUÉS de registrar sus
lecturas; describe, no rechaza. Nada de esto toca el análisis: las lecturas aceptadas, los
niveles y las alertas son los mismos con y sin vínculos (invariante 5).

El identificador de un dispositivo puede ser un dato personal: aquí no hay ninguna línea de log.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator, model_validator

from app.api.routes import CONSOLE_IDENTITY, StoreDep, _counts, _recorded_or_422, identity_for
from app.ingest import bindings

sensor_bindings_router = APIRouter()

Operator = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class SensorBindingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    # Opcional: sin identificador, el vínculo es de la fuente entera.
    device: str | None = None
    action: str
    # Solo al vincular. Retirar un vínculo no nombra a nadie.
    crew: str | None = None
    # Desde cuándo vale lo que se declara («lleva este reloj desde el lunes»), que no tiene por
    # qué ser el instante de la firma.
    since: dt.datetime
    note: Note = ""
    declared_by: Operator

    @field_validator("since")
    @classmethod
    def _aware(cls, value: dt.datetime) -> dt.datetime:
        if value.tzinfo is None:
            raise ValueError("el instante debe llevar zona horaria")
        return value

    @model_validator(mode="after")
    def _signable(self) -> SensorBindingIn:
        bindings.check(self.source, self.action, self.crew, self.device)
        return self


def binding_declarations(store: Any, until: dt.datetime | None = None) -> list[dict[str, Any]]:
    """Las declaraciones que cuentan, leídas del ledger.

    Solo las firmadas por la consola y, para Tierra, las que ya existían en su corte y no valen
    desde un instante posterior a él, como toda acción del operador.
    """
    return [
        item for item in store.sensor_bindings()
        if _counts(item, until)
        and (until is None or dt.datetime.fromisoformat(item["since"]) <= until)
    ]


@sensor_bindings_router.post("/sensor-bindings", status_code=201)
def declare_sensor_binding(store: StoreDep, payload: SensorBindingIn) -> dict[str, Any]:
    """Firma lo que una persona declara de quién lleva un dispositivo. 422 si no se puede firmar."""
    entry = _recorded_or_422(
        lambda: store.record_sensor_binding(
            payload.source, payload.action, payload.since, payload.note, payload.declared_by,
            identity_for(CONSOLE_IDENTITY), crew=payload.crew, device=payload.device,
        )
    )[0]
    return {"ledger_index": entry.index}


@sensor_bindings_router.get("/sensor-bindings")
def read_sensor_bindings(
    store: StoreDep,
    # Lo que Tierra puede tener: hasta el corte del retardo, como `/api/habitat/systems`.
    until: dt.datetime | None = None,
) -> dict[str, Any]:
    """Los vínculos vigentes y su historial: lo declarado por una persona, no una comprobación."""
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    return bindings.overview(binding_declarations(store, until))
