"""Quién firma en la consola de a bordo, y qué acciones firmadas cuenta el estado.

POR QUÉ EXISTE
--------------
Las dos cosas vivían en `api/routes.py`, y la crónica (`app/timeline.py`) y los hilos en espera
(`app/waiting.py`) las necesitan. Como las rutas importan esos módulos, las leían con un `import`
dentro de una función, y un módulo de fuera de la API dependía de la API para saber una regla del
registro (§5.37.13, «Queda»). Aquí no dependen de nadie.

`routes.py` las sigue dando con su nombre (`CONSOLE_IDENTITY`, `_counts`) al resto de la API: son la
misma constante y la misma función, no una copia.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

# Identidad con que firma la consola los reconocimientos. Es una fuente mas del
# registro de confianza: no puede firmar lapidas ni enmiendas.
CONSOLE_IDENTITY = "crew-console"
# Identidad con que firman los lotes de lecturas de las anclas de modulo (`POST
# /api/location/sightings`, `analysis/location.py`). No es la consola: no firma ninguna accion
# que cuente, y ninguna lectura de `/api/observations` puede firmar con ella
# (`routes._is_reserved_source`).
ANCHOR_IDENTITY = "location-anchors"
# Identidad con que firma Marplanner sus transacciones (`api/planner.py`, decision del usuario
# 2026-11-12: su base de datos es el ledger). No firma acciones que cuenten ni lecturas.
PLANNER_IDENTITY = "marplanner"


def action_counts(action: dict[str, Any], until: dt.datetime | None) -> bool:
    """Una accion cuenta si la firmo la consola y, para Tierra, si ya existia en su corte."""
    if action.get("signer") != CONSOLE_IDENTITY:
        return False
    return until is None or dt.datetime.fromisoformat(action["recorded"]) <= until
