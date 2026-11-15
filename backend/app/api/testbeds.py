"""Ruta de inventario: los bancos de prueba y las dos validaciones (`evidence/testbeds.py`).

Módulo aparte porque no comparte nada con el estado de un tripulante: no lee el almacén, no firma
nada y no sale a la red. Describe de dónde puede venir la evidencia y qué tiene EMMA de cada
validación, nada más.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.evidence import testbeds

testbeds_router = APIRouter()


@testbeds_router.get("/testbeds")
def read_testbeds() -> dict[str, Any]:
    """Cada banco con lo que reproduce (frase literal), lo que deja fuera, su entorno de evidencia
    y la escalera Tierra → ISS → Luna → Marte; y lo que EMMA tiene de cada validación."""
    return testbeds.payload()
