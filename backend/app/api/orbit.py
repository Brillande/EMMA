"""Dónde está la ISS y si pasa por el contorno publicado de la SAA (`environment/orbit.py`).

Por qué existe: en órbita baja, un pico de la dosimetría sin evento solar suele ser un paso por la
Anomalía del Atlántico Sur, y la consola no tenía cómo decirlo. Esta ruta lo enseña con la edad de
la efeméride; solo con el perfil de misión `leo`. Con otro perfil dice «no aplica» y no sale a la
red: fuera de la órbita baja la SAA no es el entorno de la nave.

Lo que NO hace: no cambia el riesgo, los niveles, los umbrales ni las alertas (invariante 5), no
firma nada y no escribe en el ledger (no es una observación de nadie).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter

from app.api.routes import SettingsDep, StoreDep
from app.core import i18n
from app.core.cache import OfflineDataUnavailable
from app.environment.orbit import OrbitClient, describe, saa_region

orbit_router = APIRouter(prefix="/orbit")

LEO = "leo"
DESCRIPTIVE = "descriptivo: no cambia el riesgo, los niveles, los umbrales ni las alertas"
i18n.en(
    DESCRIPTIVE,
    "descriptive: it does not change the risk, the levels, the thresholds or the alerts",
)


@orbit_router.get("/iss")
def iss_position(store: StoreDep, settings: SettingsDep) -> dict[str, Any]:
    profile = store.mission_profile(None, settings.mission_profile)["id"]
    base: dict[str, Any] = {
        "mission_profile": profile, "saa_region": saa_region(),
        "scope": i18n.loc(DESCRIPTIVE),
    }
    if profile != LEO:
        return {
            **base, "applies": False, "available": False,
            "reason": i18n.tr(
                f"no aplica: el perfil de misión es «{profile}», no órbita baja",
                f"not applicable: the mission profile is “{profile}”, not low Earth orbit",
            ),
        }
    now = dt.datetime.now(dt.UTC)
    try:
        payload = OrbitClient(settings).samples(now)
    except OfflineDataUnavailable as exc:
        return {**base, "applies": True, "available": False, "reason": str(exc)}
    return {**base, "applies": True, **describe(payload, now)}
