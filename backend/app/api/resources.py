"""Los recursos de a bordo: declarar su disponibilidad y leerla (`core/resources.py`).

Por qué existe: la especificación del equipo pide `available_resources` en el contexto de misión
(§3) y los recursos de cada contramedida (§3, §8), y EMMA no lleva inventario. Lo que sí puede
hacer es dejar que una persona declare que un recurso del vocabulario cerrado está o no está
disponible, firmarlo en el registro y enseñarlo con ese rótulo. Dos rutas: una escribe UN asiento
por declaración, firmado por la consola como las demás acciones del operador; la otra lee todo el
vocabulario con su estado —«sin declarar» por defecto, que no es «disponible»—, qué contramedidas
nombran cada recurso y qué le consta a cada una. Nada de esto toca el análisis ni qué se
recomienda: los niveles, las alertas y las recomendaciones son los mismos con y sin declaraciones
(invariante 5).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator, model_validator

from app.advisor import countermeasures
from app.api.routes import CONSOLE_IDENTITY, StoreDep, _counts, _recorded_or_422, identity_for
from app.core import resources

resources_router = APIRouter()

Operator = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class ResourceAvailabilityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource: str
    state: str
    # Desde cuándo vale lo que se declara («la sonda falla desde el martes»), que no tiene por
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
    def _in_the_vocabulary(self) -> ResourceAvailabilityIn:
        resources.check(self.resource, self.state)
        return self


def resource_declarations(store: Any, until: dt.datetime | None = None) -> list[dict[str, Any]]:
    """Las declaraciones que cuentan, leídas del ledger.

    Solo las firmadas por la consola y, para Tierra, las que ya existían en su corte y no valen
    desde un instante posterior a él, como toda acción del operador.
    """
    return resources.visible(
        [item for item in store.resource_declarations() if _counts(item, until)], until
    )


@resources_router.post("/resources", status_code=201)
def declare_resource(store: StoreDep, payload: ResourceAvailabilityIn) -> dict[str, Any]:
    """Firma lo que una persona declara de un recurso. 422 si no se puede firmar."""
    entry = _recorded_or_422(
        lambda: store.record_resource_availability(
            payload.resource, payload.state, payload.since, payload.note, payload.declared_by,
            identity_for(CONSOLE_IDENTITY),
        )
    )[0]
    return {"ledger_index": entry.index}


@resources_router.get("/resources")
def read_resources(
    store: StoreDep,
    # Lo que Tierra puede tener: hasta el corte del retardo, como `/api/sensor-bindings`.
    until: dt.datetime | None = None,
) -> dict[str, Any]:
    """El vocabulario con su estado y su historial: lo declarado, no un inventario."""
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    declared = resource_declarations(store, until)
    body = resources.overview(declared, countermeasures.resource_users())
    # Qué le consta a cada contramedida de la biblioteca, también a las de hábitat, que no
    # salen entre las recomendaciones del estado. Describe; no retira ninguna.
    body["countermeasures"] = [
        {"id": item.id, "action": item.action, "scope": item.scope,
         "resource_status": resources.describe(item.to_dict(), declared)}
        for item in countermeasures.library().values()
    ]
    return body
