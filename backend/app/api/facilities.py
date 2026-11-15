"""Ruta de inventario: EPM y Biolab, de la instalación a la aplicación (`evidence/facilities.py`).

Módulo aparte porque no comparte nada con el estado de un tripulante: no lee el almacén, no firma
nada y no sale a la red. Describe dónde se ha medido en Columbus, con qué, quién y qué quedó de
ello, y lo que no se encontró; nada más.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.evidence import facilities

facilities_router = APIRouter()


@facilities_router.get("/facilities")
def read_facilities() -> dict[str, Any]:
    """Cada instalación con su cadena de nueve eslabones: frases literales con su ficha, el
    estado de cada eslabón y, donde falta algo, qué falta y dónde se buscó."""
    return facilities.payload()
