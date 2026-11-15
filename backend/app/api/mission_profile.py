"""Entorno de la misión: declararlo, firmado, y leer el vigente (`core/mission_profile_changes.py`).

Por qué existe: el perfil de misión solo se podía cambiar reiniciando con otra configuración, y
nadie a bordo podía declarar «ya estamos en órbita baja» dejando constancia (petición del usuario,
2026-11-04). Dos rutas, con el patrón del nivel de misión (`api/mission_mode.py`): una firma UN
asiento por cambio, con la consola de a bordo; la otra lee el entorno vigente, de dónde sale (el
registro o la configuración) y los entornos que se pueden declarar.

Lo que NO hace: el riesgo, los niveles y las alertas no leen esto (invariante 5). Lo único que
mueve es hacia qué cuerpo se calculan las efemérides (el objetivo lo decide el perfil desde el
2026-11-11, `mission_profiles.ephemeris_target`), y con él el tiempo de luz que escala el riesgo.
Con `until`, lo que Tierra puede tener: lo firmado hasta su corte.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.routes import CONSOLE_IDENTITY, SettingsDep, StoreDep, identity_for
from app.core import mission_profile_changes

mission_profile_router = APIRouter(prefix="/mission/profile")

Operator = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class MissionProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str
    reason: str = Field(default="", max_length=300)
    declared_by: Operator


@mission_profile_router.get("")
def read_mission_profile(
    store: StoreDep, settings: SettingsDep, until: dt.datetime | None = None
) -> dict[str, Any]:
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    return mission_profile_changes.view(store.mission_profile(until, settings.mission_profile))


@mission_profile_router.post("", status_code=201)
def set_mission_profile(
    store: StoreDep, settings: SettingsDep, payload: MissionProfileIn
) -> dict[str, Any]:
    try:
        changed = store.change_mission_profile(
            payload.profile, payload.reason, payload.declared_by, identity_for(CONSOLE_IDENTITY),
            settings.mission_profile,
        )
    except mission_profile_changes.MissionProfileConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return mission_profile_changes.view(changed)
