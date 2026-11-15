"""Ruta de inventario: el mapa de conjuntos humanos y CIPHER (`evidence/human_datasets.py`).

Módulo aparte porque no comparte nada con el estado de un tripulante: no lee el almacén, no firma
nada y no sale a la red. Dice qué conjuntos humanos existen, en qué días tienen tomas y cómo se
accede a ellos; no trae ninguno.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.evidence import human_datasets

datasets_router = APIRouter()


@datasets_router.get("/human-datasets")
def read_human_datasets() -> dict[str, Any]:
    """Cada conjunto con su población, sus variables, sus tomas antes, durante y después del vuelo
    (frase literal), su acceso y su uso en EMMA; y CIPHER, con sus estudios y sus duraciones."""
    return human_datasets.payload()
