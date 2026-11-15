"""El estado de los sistemas del hábitat: declararlo y leerlo (`environment/systems.py`).

Por qué existe: la especificación del equipo pide `system_status` en `HabitatState` (§3) y
EMMA no lee el estado de ningún sistema. Lo que sí puede hacer es dejar que una persona lo
declare, firmarlo en el registro y enseñarlo con ese rótulo. Dos rutas: una escribe UN asiento
por declaración, firmado por la consola como las demás acciones del operador; la otra lee lo
vigente y desde cuándo. Ninguna toca el análisis: los niveles y las alertas son los mismos con
y sin declaraciones (invariante 5).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator, model_validator

from app.api.routes import CONSOLE_IDENTITY, StoreDep, _counts, _recorded_or_422, identity_for
from app.environment import systems

systems_router = APIRouter()

Operator = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class SystemStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system: str
    state: str
    # Opcional: sin módulo, la declaración habla del sistema entero.
    module: str | None = None
    # El instante al que se refiere quien declara («desde las 14:00 no enfría»), que no tiene
    # por qué ser el de la firma.
    at: dt.datetime
    note: Note = ""
    declared_by: Operator

    @field_validator("at")
    @classmethod
    def _aware(cls, value: dt.datetime) -> dt.datetime:
        if value.tzinfo is None:
            raise ValueError("el instante debe llevar zona horaria")
        return value

    @model_validator(mode="after")
    def _in_the_vocabulary(self) -> SystemStatusIn:
        systems.check(self.system, self.state, self.module)
        return self


def system_declarations(store: Any, until: dt.datetime | None = None) -> list[dict[str, Any]]:
    """Las declaraciones que cuentan, leídas del ledger.

    Solo las firmadas por la consola y, para Tierra, las que ya existían en su corte y no se
    refieren a un instante posterior a él, como toda acción del operador.
    """
    return [
        item for item in store.system_statuses()
        if _counts(item, until)
        and (until is None or dt.datetime.fromisoformat(item["at"]) <= until)
    ]


@systems_router.post("/habitat/systems/status", status_code=201)
def declare_system_status(store: StoreDep, payload: SystemStatusIn) -> dict[str, Any]:
    """Firma lo que una persona declara de un sistema. 422 fuera del vocabulario."""
    entry = _recorded_or_422(
        lambda: store.record_system_status(
            payload.system, payload.state, payload.at, payload.note, payload.declared_by,
            identity_for(CONSOLE_IDENTITY), module=payload.module,
        )
    )[0]
    return {"ledger_index": entry.index}


@systems_router.get("/habitat/systems")
def read_system_status(
    store: StoreDep,
    # Lo que Tierra puede tener: hasta el corte del retardo, como `/api/habitat`.
    until: dt.datetime | None = None,
) -> dict[str, Any]:
    """El estado vigente de cada sistema y desde cuándo: lo declarado, no telemetría.

    Lleva también el enlace con Tierra declarado (`declared_link`, el mismo de `/api/status`),
    leído de las mismas declaraciones: antes de que llegue a Tierra ninguna lectura no hay estado
    recibido (404) y la consola de Tierra lo lee de aquí, con su corte. Solo texto, como allí.
    """
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    declarations = system_declarations(store, until)
    return {**systems.overview(declarations), "declared_link": systems.earth_link(declarations)}
