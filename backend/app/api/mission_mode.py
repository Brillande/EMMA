"""Nivel de misión: declarar, firmado, qué medidas se siguen esperando (`core/mission_modes.py`).

Por qué existe: con la energía racionada o la tripulación sin tiempo, la consola seguía esperando
cada muestra y cada ecografía, y lo no tomado parecía olvidado. Dos rutas, con el patrón del modo
seguro (`api/safe_mode.py`): una firma UN asiento por cambio, con la consola de a bordo; la otra
lee el nivel vigente, lo que espera, lo que suspende y el aviso que la consola pinta tal cual.

Lo que NO hace: no apaga la ingesta, el análisis, el riesgo, las alertas ni el modo seguro, que no
leen esto (invariante 5). Tampoco las rutinas, todavía: `expected_measurements` es la pieza que
se les cablea, y hasta entonces el nivel solo informa.

Con `until`, lo que Tierra puede tener: el nivel firmado hasta su corte, como
`/api/habitat/systems` (el modo seguro aún no lo respeta, y lo declara `SafeMode.tsx`).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.routes import CONSOLE_IDENTITY, StoreDep, identity_for
from app.core import mission_modes

mission_mode_router = APIRouter(prefix="/mission-mode")

Operator = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class MissionModeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str
    reason: str = Field(default="", max_length=300)
    declared_by: Operator
    # Opcional: la energía o las comunicaciones del hábitat. Se firma el estado declarado que
    # consta al firmar; el cliente no lo manda.
    cited_system: str | None = None


@mission_mode_router.get("")
def read_mission_mode(store: StoreDep, until: dt.datetime | None = None) -> dict[str, Any]:
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    return mission_modes.view(store.mission_mode(until))


@mission_mode_router.post("", status_code=201)
def set_mission_mode(store: StoreDep, payload: MissionModeIn) -> dict[str, Any]:
    try:
        # El estado tal como lo dejó este asiento, con su versión (como `change_safe_mode`).
        changed = store.change_mission_mode(
            payload.level, payload.reason, payload.declared_by, identity_for(CONSOLE_IDENTITY),
            cited_system=payload.cited_system,
        )
    except mission_modes.MissionModeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return mission_modes.view(changed)
