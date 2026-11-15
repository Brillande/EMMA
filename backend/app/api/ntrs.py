"""Los informes de NTRS que cita EMMA, cotejados con su ficha pública (`evidence/ntrs.py`).

Leer no sale a la red: `GET /dossier/ntrs` enseña lo último que se consultó, con su edad, o «sin
consulta guardada». Salir a NTRS es una orden: `POST /dossier/ntrs/refresh` (con la cabecera de la
consola) o la ficha de una sola referencia, `GET /dossier/ntrs/{ref_id}`, que pregunta si su
consulta ha caducado y hay red. Sin red (`EMMA_OFFLINE`), las tres sirven lo guardado con su edad
o «no disponible», y ninguna falla por eso.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.console_header import console_post
from app.api.routes import SettingsDep
from app.evidence import ntrs, registry

ntrs_router = APIRouter(prefix="/dossier/ntrs")


@ntrs_router.get("")
def read_ntrs(settings: SettingsDep) -> dict[str, Any]:
    """Cada ficha con número de NTRS, con lo último que se supo de ella. No sale a la red."""
    return ntrs.check_all(ntrs.NtrsClient(settings), network=False)


@ntrs_router.post("/refresh", **console_post())
def refresh_ntrs(settings: SettingsDep) -> dict[str, Any]:
    """Pregunta a NTRS por las fichas cuya consulta caducó o no existe (con red). Sin red, lo
    guardado con su edad: no es un fallo."""
    return ntrs.check_all(ntrs.NtrsClient(settings), network=True)


@ntrs_router.get("/{ref_id}")
def read_ntrs_reference(ref_id: str, settings: SettingsDep) -> dict[str, Any]:
    """Una ficha del registro frente a NTRS; pregunta si su consulta caducó y hay red."""
    try:
        ref = registry.get(ref_id)
    except registry.RegistryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if ntrs.ntrs_id_of(ref) is None:
        raise HTTPException(status_code=404, detail=f"{ref_id}: la ficha no cita un número de NTRS")
    return ntrs.check_reference(ref, ntrs.NtrsClient(settings), network=True)
