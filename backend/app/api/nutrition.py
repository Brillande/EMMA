"""La comida frente a su criterio de aceptable, valoración a valoración.

POR QUÉ EXISTE
--------------
El usuario decidió (2026-10-15) que el criterio de 6,0 de la escala hedónica se evalúe: cada
valoración de la comida por debajo se marca con la frase de NASA-STD-3001 Vol. 2 [V2 7002] y su
página. La marca y sus textos se escriben en `analysis/food_acceptability.py`; aquí solo se
leen las lecturas firmadas del registro y se sirven.

Desde el 2026-10-26 (decisión del usuario) la respuesta trae también la comida plato a plato
(`dishes`): cuántas veces se valoró cada alimento, en cuántos días y cada valoración en el tiempo,
sobre todas las valoraciones medidas y no solo las `limit` que se enseñan. Descriptivo, sin umbral
ni veredicto de fatiga de menú. Desde el 2026-10-31, cada plato dice además de cuánto a cuánto fue
entre su primera y su última valoración, y lleva al lado la fracción rechazada que se anotó con su
nombre: para eso la ruta lee también las lecturas de `food-rejected-fraction`.

Ruta de solo lectura: no escribe en el registro, no la lee el estado y no mueve ningún nivel,
alerta, puntuación ni recomendación (invariante 5).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.analysis import food_acceptability
from app.api.routes import StoreDep
from app.evidence import instruments_read

nutrition_router = APIRouter(prefix="/nutrition")


@nutrition_router.get("/food-acceptability")
def food_acceptability_ratings(
    store: StoreDep,
    subject: str = "crew-01",
    limit: int = Query(default=60, ge=1, le=500),
) -> dict[str, Any]:
    """Cada valoración de la comida del tripulante, marcada frente al criterio leído.

    Cuenta todas las del registro y enseña las `limit` últimas. Sin valoraciones, lo dice;
    no es un 404: no tener valoraciones de la comida es un dato, no un error.
    """
    return food_acceptability.describe(
        subject,
        [
            *store.query(subject, key=food_acceptability.KEY),
            *store.query(subject, key=food_acceptability.REJECTED_KEY),
        ],
        instruments_read.scale_criterion(food_acceptability.KEY),
        limit,
    )
