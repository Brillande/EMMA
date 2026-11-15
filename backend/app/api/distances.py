"""Ruta de las distancias por perfil (`environment/distances.py`): Tierra, Luna y Marte, sin red.

Módulo aparte para no tocar `api/routes.py` ni `api/spice.py`. Solo GET: la consola de a bordo
mira el perfil que elige en «Ubicación de la tripulación», que puede no ser el declarado, y el
retardo de `/api/status` es solo el del declarado. Sin `profile`, el vigente (el último firmado,
o el de la configuración); sin `epoch`, el día UTC de hoy.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter

from app.api.routes import SettingsDep, StoreDep
from app.environment import distances

distances_router = APIRouter(prefix="/distances")


@distances_router.get("")
def read_distances(
    settings: SettingsDep,
    store: StoreDep,
    profile: str | None = None,
    epoch: dt.date | None = None,
) -> dict[str, Any]:
    """Distancia y tiempo de luz de la Luna y Marte, y el retardo con Tierra del perfil."""
    declared = str(store.mission_profile(None, settings.mission_profile)["id"])
    day = epoch or dt.datetime.now(dt.UTC).date()
    return {**distances.describe(settings, day, profile or declared), "declared_profile": declared}
