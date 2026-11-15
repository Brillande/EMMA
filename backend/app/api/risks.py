"""Rutas de inventario: la entidad Riesgo (especificación del equipo §3) y el coste de medir.

Módulo aparte porque no comparten nada con el estado de un tripulante: describen el catálogo,
no a una persona. No leen el almacén ni firman nada; la composición vive en
`app/risk_entity.py` y en `app/ingest/cost.py`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app import risk_entity
from app.api import routes
from app.evidence import hrp_coverage
from app.ingest.codes import CATALOG
from app.ingest.cost import cost
from app.ingest.cost import summary as cost_summary

risks_router = APIRouter()


@risks_router.get("/risks")
def risks() -> dict[str, Any]:
    """Cada riesgo con su RIDGE, su región, su evidencia, el esquema de niveles y lo que EMMA
    sabe decir de su incertidumbre. Sin probabilidad: EMMA no la cuantifica, y lo dice.

    Y la matriz de la conversación de ideación: efecto, dato, detección y contramedidas de cada
    riesgo. La regla de detección recibe la ventana de «lo actual» de la ruta de estado, la misma
    con que esta elige las lecturas que evalúa.

    Cada riesgo dice además qué indicadores suyos salen de MMASH —las claves que emite el
    cargador (`validation/mmash.py`)— y que eso valida el motor de medida y la falsa alarma en
    Tierra, no la fisiología espacial; y cada variable, su equipo del coste de medir."""
    return risk_entity.payload(routes.CURRENT_WINDOW)


@risks_router.get("/risks/hrp-coverage")
def hrp_coverage_view() -> dict[str, Any]:
    """Los riesgos que publica el Human Research Roadmap, todos, y qué hace EMMA con cada uno:
    el que cita un dominio, uno vigilado en parte o uno fuera de su alcance, con el motivo, el eje
    RIDGE (y si lo nombra una fuente o lo deduce EMMA) y el elemento del HRP al que el Roadmap lo
    asigna. Ruta aparte de `/risks`, que sigue siendo un riesgo por dominio: esto es un inventario
    de lo que EMMA no vigila, y no decide nada (`app/evidence/hrp_coverage.py`)."""
    return hrp_coverage.payload()


@risks_router.get("/measurement-cost")
def measurement_cost() -> dict[str, Any]:
    """El coste de medir con sus dimensiones —dónde se procesa, cuándo llega el resultado y si
    gasta consumibles— y el total que queda sin clasificar. Cada clase dice de dónde sale."""
    return {
        "summary": cost_summary(),
        "indicators": [
            {
                "key": code.key, "display": code.display, "display_es": code.display_es,
                "domain": str(code.domain), **item,
            }
            for code in CATALOG.values()
            if (item := cost(code.key)) is not None
        ],
    }
