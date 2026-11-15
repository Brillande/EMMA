"""La serie continua del entorno de partículas, junto a los eventos de DONKI.

Por qué existe: `GET /api/space-weather` da los SEP catalogados por DONKI, sueltos. Entre uno y
otro la consola no veía la curva: ni el flujo de protones ≥10 MeV ni el viento solar. Esta ruta
sirve las dos series de CCMC iSWA (`environment/iswa.py`), cada una con su unidad, su edad y su
fuente. Una serie que falta no tumba la otra: sale «no disponible» con su motivo.

Lo que NO hace, a propósito: no compara con ningún umbral, no cambia ningún nivel, alerta ni
riesgo, y no escribe nada en el ledger (no es una observación de nadie: es el entorno en órbita
geoestacionaria y en L1). La referencia S1 de NOAA viaja con su cita y `evaluated: false`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.api.routes import SettingsDep
from app.core import i18n
from app.core.cache import OfflineDataUnavailable
from app.environment import iswa

space_weather_series_router = APIRouter()


@space_weather_series_router.get("/space-weather/series")
def space_weather_series(
    settings: SettingsDep,
    hours: int = Query(default=24, ge=1, le=iswa.MAX_HOURS),
) -> dict[str, Any]:
    """Flujo de protones ≥10 MeV (pfu) y viento solar de las últimas `hours` horas."""
    client = iswa.IswaClient(settings=settings)
    blocks: dict[str, Any] = {}
    for which in iswa.Series:
        try:
            blocks[str(which)] = iswa.describe(which, client.series(which), hours)
        except OfflineDataUnavailable as exc:
            blocks[str(which)] = iswa.unavailable(which, str(exc))
    blocks[str(iswa.Series.PROTONS)]["reference"] = iswa.s1_reference()
    return {
        "series": blocks,
        "scope": i18n.loc(iswa.SCOPE),
        "licence": i18n.loc(iswa.LICENCE),
        "events": i18n.tr(
            "Los eventos catalogados (SEP) están en GET /api/space-weather (NASA DONKI).",
            "The catalogued events (SEP) are at GET /api/space-weather (NASA DONKI).",
        ),
    }
