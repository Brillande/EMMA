"""Ruta de inventario: las fuentes del contexto del equipo y lo leído de cada una
(`evidence/context_sources.py`).

Módulo aparte porque no comparte nada con el estado de un tripulante: no lee el almacén, no firma
nada y no sale a la red. Dice qué fuentes del contexto se leyeron, cuáles no y por qué; nada más.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.evidence import context_sources

context_sources_router = APIRouter()


@context_sources_router.get("/context-sources")
def read_context_sources() -> dict[str, Any]:
    """Cada fuente con su ficha, de qué lista del equipo sale, qué se pudo leer y para qué la
    tiene EMMA; lo no leído, con su motivo."""
    return context_sources.payload()
