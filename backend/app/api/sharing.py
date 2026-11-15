"""Ruta de inventario: qué se comparte y qué no, por categoría de dato (`app/sharing.py`).

Módulo aparte porque no comparte nada con el estado de un tripulante: no lee el almacén, no firma
nada y no sale a la red. Las dos consolas piden lo mismo y sin corte: es una tabla del paquete,
no un dato de a bordo que tenga que viajar.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app import sharing
from app.api.routes import SettingsDep

sharing_router = APIRouter()


@sharing_router.get("/sharing")
def read_sharing(settings: SettingsDep) -> dict[str, Any]:
    """Cada categoría de dato con a dónde llega, si lo impone el código y qué queda fuera; los
    propósitos de internet con sus hosts, y las rutas que aceptan el corte del retardo."""
    return sharing.payload(settings)
