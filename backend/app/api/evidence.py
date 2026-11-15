"""La evidencia de EMMA, de solo lectura: el estado del dosier (reglas de Polaris) y el registro
único de referencias con lo que le queda por verificar."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.evidence import dossier, registry

evidence_router = APIRouter(prefix="/dossier")


@evidence_router.get("")
def read_dossier() -> dict[str, Any]:
    """Esquema, contradicciones, fuentes y frescura de la evidencia (`evidence/dossier.py`)."""
    return dossier.status()


@evidence_router.get("/references")
def read_references() -> dict[str, Any]:
    """Cada fuente citada, con su identificador, su tipo, su entorno y sus campos sin verificar.

    Es la misma ficha que acompaña a una recomendación o a una hipótesis: aquí se ve entera y
    con el recuento de lo que nadie ha leído todavía en la fuente (`evidence/registry.py`).
    """
    return registry.summary()
