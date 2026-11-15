"""El enlace con Tierra simulado: declararlo caído o restablecido, y lo pendiente.

La cuenta vive en `core/link_sync.py`; aquí, las dos rutas.

Por qué existe: la consola de Tierra solo descontaba el tiempo de luz, como si el enlace no se
cayera nunca. Dos rutas, con el patrón del modo seguro (`api/safe_mode.py`):

- `POST /api/link-sync` firma UN asiento (`simulated-link`, `record-integrity.md` §3.29) con la
  consola de a bordo: «caído» o «restablecido» desde un instante, con el nombre de quien lo declara.
- `GET /api/link-sync?light_cut=…` lee el estado y devuelve el corte de Tierra (`cut`), el que la
  consola pide a las demás rutas en lugar del tiempo de luz solo, y las dos colas: lo pendiente de
  enviar a bordo (`to_send`) y lo que le falta a Tierra (`to_arrive`). `light_cut` es el corte por
  tiempo de luz que calcula la consola (`groundCut`); sin él, sin efemérides, no hay retardo.

Lo que NO hace: no transporta nada ni sale a la red (las dos consolas corren en la misma máquina).
Tampoco toca el riesgo, las alertas, las recomendaciones ni la declaración del sistema
Comunicaciones, que sigue siendo solo texto (invariante 5; decisión del usuario del 2026-10-21).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from app.api.routes import CONSOLE_IDENTITY, StoreDep, _recorded_or_422, identity_for
from app.core import link_sync

link_sync_router = APIRouter(prefix="/link-sync")

Operator = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]


class LinkChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["down", "up"]
    # El instante al que se refiere quien declara, en la hora de los datos («caído desde hace 6 h»),
    # no la hora de la firma.
    at: dt.datetime
    note: Note = ""
    declared_by: Operator

    @field_validator("at")
    @classmethod
    def _aware(cls, value: dt.datetime) -> dt.datetime:
        if value.tzinfo is None:
            raise ValueError("el instante debe llevar zona horaria")
        return value


def _view(store: Any, light_cut: dt.datetime | None) -> dict[str, Any]:
    entries, instants = store.link_snapshot()
    return {**link_sync.view(entries, instants, light_cut), "store_epoch": store.epoch}


@link_sync_router.get("")
def read_link_sync(
    store: StoreDep,
    light_cut: Annotated[dt.datetime | None, Query()] = None,
) -> dict[str, Any]:
    """El enlace simulado, el corte de Tierra y lo pendiente. Solo lee."""
    if light_cut is not None and light_cut.tzinfo is None:
        raise HTTPException(status_code=422, detail="`light_cut` debe llevar zona horaria")
    return _view(store, light_cut)


@link_sync_router.post("", status_code=201)
def declare_link(store: StoreDep, payload: LinkChangeIn) -> dict[str, Any]:
    """Firma «caído» o «restablecido».

    409 si repite el estado o va hacia atrás; 422 si es un dato malo.
    """

    def write() -> Any:
        # El conflicto se traduce aquí, antes que `_recorded_or_422` lo tome por un dato malo:
        # `LinkConflict` también es un `ValueError`.
        try:
            return store.change_simulated_link(
                payload.state, payload.at, payload.note, payload.declared_by,
                identity_for(CONSOLE_IDENTITY),
            )
        except link_sync.LinkConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    entry = _recorded_or_422(write)[0]
    return {"ledger_index": entry.index, **_view(store, None)}
