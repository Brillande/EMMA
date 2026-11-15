"""Ruta de solo lectura: personas y organizaciones de las fuentes (`evidence/people.py`).

Módulo aparte porque no comparte nada con el estado de un tripulante: no lee el almacén, no firma
nada y no sale a la red. Agrupa lo que ya dicen las fichas del registro de evidencia.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.evidence import people

people_router = APIRouter()


@people_router.get("/people")
def read_people() -> dict[str, Any]:
    """Cada organización con las fichas que la dan y cada persona con las fichas que la citan y su
    papel en ellas, recorriendo el registro en esta consulta."""
    return people.payload()
