"""Rutas de las guías de medida y del glosario (`app/guides.py`).

Módulo aparte porque no comparte nada con el estado de un tripulante: no lee el almacén, no firma
nada y no sale a la red. Son datos fijos del paquete, los mismos a bordo y en Tierra.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app import guides

guides_router = APIRouter()


@guides_router.get("/guides")
def read_guides() -> dict[str, Any]:
    """Cómo se toma cada medida, paso a paso, con la frase leída que sostiene cada paso."""
    return guides.guides_payload()


@guides_router.get("/glossary")
def read_glossary() -> dict[str, Any]:
    """Los términos de la consola, con el origen de cada definición."""
    return guides.glossary_payload()
