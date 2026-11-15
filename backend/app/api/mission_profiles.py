"""Ruta de inventario: los perfiles de misión lado a lado (`evidence/mission_profiles.py`).

La base de conocimiento del equipo (§15, P1) pide comparar estación, Luna y Marte en una matriz;
`/api/status` solo trae el perfil declarado. Módulo aparte porque no comparte nada con el estado
de un tripulante: no firma nada y no sale a la red. Del almacén y de la configuración solo lee qué
entorno está declarado (`storage.mission_profile`: el último firmado por la consola o, sin
asientos, el de la configuración), para señalar su columna; el riesgo no pasa por aquí.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.routes import SettingsDep, StoreDep
from app.evidence import imm_radiation, mission_profiles

mission_profiles_router = APIRouter()


@mission_profiles_router.get("/mission/profiles")
def read_mission_profiles(
    store: StoreDep, settings: SettingsDep, until: dt.datetime | None = None
) -> dict[str, Any]:
    """Cada perfil con todos sus aspectos, en el mismo orden: la frase leída con su cita, o «EMMA
    no tiene fuente» con lo que se buscó; y la columna del entorno declarado, señalada. Con
    `until`, el declarado hasta el corte de Tierra."""
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    declared = store.mission_profile(until, settings.mission_profile)["id"]
    return mission_profiles.compare(declared)


@mission_profiles_router.get("/radiation/imm")
def read_imm_radiation(
    store: StoreDep, settings: SettingsDep, until: dt.datetime | None = None
) -> dict[str, Any]:
    """Lo que publica el IMM de NASA sobre radiación (`evidence/imm_radiation.py`): la probabilidad
    de al menos un síndrome agudo de radiación por misión de referencia, con su fila citada, y la
    misión a la que EMMA asimila cada perfil; el declarado, señalado. No decide nada."""
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    declared = store.mission_profile(until, settings.mission_profile)["id"]
    return imm_radiation.describe(declared)
