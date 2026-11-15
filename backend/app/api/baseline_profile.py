"""El perfil de línea base de un tripulante, de solo lectura (`app/analysis/baseline_profile.py`).

Por qué es una ruta aparte y no un bloque más de `/api/status`: el estado ya pesa, y lo que se
enseña aquí se lee de las desviaciones que el estado calcula, no al revés. Se llama a `_assess`
(lecturas → línea base → tendencia → riesgo, sin escribir) una vez, como `/api/alerts/history`, y
el perfil se compone con lo que devuelve: la misma base que juzgó cada lectura, no otra calculada
aparte. Pedirla no firma nada —tampoco instantáneas de predicción— y no mueve ningún nivel.

Con `until`, el perfil con las lecturas que Tierra tiene (el corte del retardo, como `/status`).

Junto a la base va, por indicador analizado, el sentido en que cambió en otros vuelos
(`evidence/flight_direction.py`): lo leído en estudios con otras tripulaciones, no lo esperado en
esta persona. Va aquí y no en la alerta (decisión del usuario, 2026-10-22), y no lo lee nada del
estado.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter

from app.analysis.baseline_profile import profile
from app.api import routes
from app.api.routes import SettingsDep, StoreDep
from app.evidence import flight_direction
from app.ingest.codes import DESCRIPTIVE_ONLY

baseline_profile_router = APIRouter()


@baseline_profile_router.get("/baseline-profile")
def read_baseline_profile(
    store: StoreDep,
    settings: SettingsDep,
    subject: str = "crew-01",
    until: dt.datetime | None = None,
) -> dict[str, Any]:
    """Por indicador y estado, la base contra la que se juzgó su última lectura. No escribe."""
    assessed = routes._assess(settings, store, subject, None, None, until)
    descriptive = {
        item.key for item in store.query(subject, until=until) if item.key in DESCRIPTIVE_ONLY
    }
    body = profile(subject, assessed.observations, assessed.deviations, assessed.latest,
                   descriptive)
    return {
        **body,
        "flight_direction": flight_direction.for_profile(
            item["key"] for item in body["indicators"]
        ),
        # Si la base de arriba está llevada a la fase del ciclo, y por qué (lote «ciclo», B3):
        # `{applied, phase, reason}`, con la frase fija de `api/cycle_phase.py`. Respeta `until`.
        "cycle_phase": assessed.cycle.to_dict() if assessed.cycle is not None else None,
        "until": until.isoformat() if until else None,
    }
