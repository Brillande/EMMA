"""Ruta de la comprobación de las fichas de OSDR contra la API de OSDR (`evidence/osdr_data.py`).

Módulo aparte porque no comparte nada con el estado de un tripulante: no lee el almacén ni firma
nada. Va en `/api/osdr/...` y no en `/api/evidence/...`, donde `/evidence/{domain}` de
`routes.py` se tragaría la ruta. Solo GET: no cambia nada.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import Settings, get_settings
from app.evidence import osdr_data
from app.evidence.registry import RegistryError

osdr_data_router = APIRouter()


@osdr_data_router.get("/osdr/studies")
def read_osdr_studies(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    """Cada estudio de OSDR que EMMA cita: su ficha, lo que dice la API de OSDR (con su edad) y
    la comparación campo a campo. Sin red y sin lectura previa, cada uno sale «no disponible»."""
    return osdr_data.studies(osdr_data.OsdrDataClient(settings))


@osdr_data_router.get("/osdr/studies/{ref_id}")
def read_osdr_study(
    ref_id: str, settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, Any]:
    """Un estudio, por el identificador de su ficha (`osd-288`)."""
    try:
        return osdr_data.study(ref_id, osdr_data.OsdrDataClient(settings))
    except (RegistryError, osdr_data.OsdrDataError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
