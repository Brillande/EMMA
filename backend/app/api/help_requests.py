"""Rutas de la petición de ayuda urgente: pedirla a bordo, verla en las dos consolas y atenderla.

Por qué es un módulo aparte: es la única acción de consola que tiene que llegar a todos a la vez
—la tripulación de a bordo al momento y Tierra con su retardo— y la única que ordena a la
tripulación por cercanía. Las reglas están en `core/help_requests.py`; lo que comparte con las
demás acciones de consola (el almacén, la identidad de a bordo, el 422 de un dato que el ledger no
admite) se reutiliza de `routes.py`.

El retardo, como en las notas de Tierra pero al revés: la consola de Tierra pide con `until` = su
corte (el reloj menos un tiempo de luz) y lo firmado a bordo después no se entrega. Un cierre
firmado después del corte tampoco: para Tierra, la petición sigue abierta hasta que le llega que
alguien la atendió.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.analysis import location as location_rules
from app.api.routes import CONSOLE_IDENTITY, StoreDep, _recorded_or_422, identity_for
from app.core import help_requests as rules
from app.core import i18n
from app.core.storage import ObservationStore

help_requests_router = APIRouter(prefix="/help-requests")


class HelpRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    # Opcional (2026-11-14): pedir ayuda no espera a que nadie escriba su nombre. Declarado, sin
    # autenticar, como toda acción de consola (`record-integrity.md` §7.5).
    signed_by: str = Field(default="", max_length=4 * rules.MAX_NAME)
    # Opcional: pedir ayuda no puede esperar a que alguien escriba. El tope lo impone el almacén.
    reason: str = Field(default="", max_length=4 * rules.MAX_REASON)
    # El instante de la misión (el de los datos que ve la consola); sin él, ahora.
    at: dt.datetime | None = None


class HelpCloseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signed_by: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
    ]


def _place(store: ObservationStore, subject: str, at: dt.datetime) -> dict[str, Any] | None:
    """Dónde estaba un tripulante en ese instante: su módulo (consola o anclas), o None."""
    from app.api.mission import crew_whereabouts

    whereabouts = crew_whereabouts(store, subject, None, at - location_rules.sensing().lookback)
    return location_rules.location_at(whereabouts.stays, at)


def _location_display(place: dict[str, Any] | None) -> str:
    """El módulo en palabras, en el idioma de quien lee; el inglés lo registran sus dueños
    (`core/help_requests.py`, `environment/habitat.py`) y sin registrar sale el castellano."""
    return i18n.loc(rules.NO_LOCATION if place is None else str(place["display"]))


def _nearby(
    store: ObservationStore, subject: str, at: dt.datetime, module: str | None
) -> list[dict[str, Any]]:
    """El resto de la tripulación, de más a menos cerca de quien pide ayuda."""
    found: list[dict[str, Any]] = []
    for other in store.subjects():
        if other == subject:
            continue
        place = _place(store, other, at)
        if place is None:
            proximity = rules.UNKNOWN_PLACE
        elif module is not None and place["module"] == module:
            proximity = rules.SAME_MODULE
        else:
            proximity = rules.OTHER_MODULE
        found.append(
            {
                "subject": other,
                "proximity": proximity,
                "proximity_display": i18n.loc(rules.PROXIMITY_DISPLAY[proximity]),
                "location_display": _location_display(place),
            }
        )
    found.sort(key=lambda item: (rules.PROXIMITY_ORDER.index(item["proximity"]), item["subject"]))
    return found


def _view(store: ObservationStore, request: dict[str, Any]) -> dict[str, Any]:
    at = dt.datetime.fromisoformat(request["at"])
    place = _place(store, request["subject"], at)
    nearby = _nearby(store, request["subject"], at, None if place is None else place["module"])
    return {
        "ledger_index": request["ledger_index"],
        "subject": request["subject"],
        "signed_by": request["signed_by"] or None,
        "reason": request["reason"] or None,
        "at": request["at"],
        "signed_at": request["recorded"],
        "location_display": _location_display(place),
        "nearby": nearby,
        "nearby_note": None if nearby else i18n.loc(rules.NO_CREWMATES),
    }


@help_requests_router.post("", status_code=201)
def request_help(store: StoreDep, payload: HelpRequestIn) -> dict[str, Any]:
    """Firma en el ledger una petición de ayuda urgente de un tripulante con lecturas.

    Sin nombre ni motivo obligatorios: un solo toque basta. 422 con el motivo si algo es demasiado
    largo o si el tripulante no tiene lecturas: una petición de «crew-1» no la sabría situar nadie.
    """
    if payload.subject not in store.subjects():
        raise HTTPException(
            status_code=422,
            detail=f"tripulante desconocido: {payload.subject!r}; uno con lecturas",
        )
    at = payload.at if payload.at is not None else dt.datetime.now(dt.UTC)
    if at.tzinfo is None:
        raise HTTPException(status_code=422, detail="`at` debe llevar zona horaria")
    entry = _recorded_or_422(
        lambda: store.record_help_request(
            payload.subject, payload.signed_by, payload.reason, at,
            identity_for(CONSOLE_IDENTITY),
        )
    )[0]
    return {
        "ledger_index": entry.index,
        "content_hash": entry.content_hash,
        "signed_at": entry.recorded.isoformat(),
    }


@help_requests_router.post("/{ledger_index}/close", status_code=201)
def close_help_request(
    store: StoreDep, ledger_index: int, payload: HelpCloseIn
) -> dict[str, Any]:
    """Da por atendida una petición abierta. 422 si no existe o ya está atendida."""
    entry = _recorded_or_422(
        lambda: store.record_help_close(
            ledger_index, payload.signed_by, identity_for(CONSOLE_IDENTITY)
        )
    )[0]
    return {"ledger_index": entry.index, "signed_at": entry.recorded.isoformat()}


@help_requests_router.get("")
def list_help_requests(
    store: StoreDep,
    until: Annotated[dt.datetime | None, Query()] = None,
) -> dict[str, Any]:
    """Las peticiones de ayuda abiertas de toda la tripulación, de la más reciente a la más antigua.

    `until` es para la consola de Tierra: lo firmado a bordo después de ese instante —peticiones y
    cierres— todavía no ha llegado. Solo cuenta lo firmado por la consola de a bordo.
    """
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")

    def arrived(item: dict[str, Any]) -> bool:
        return item.get("signer") == CONSOLE_IDENTITY and (
            until is None or dt.datetime.fromisoformat(item["recorded"]) <= until
        )

    requests, closes = store.help_requests()
    closed = {item["request_index"] for item in closes if arrived(item)}
    open_ = [
        item for item in requests if arrived(item) and str(item["ledger_index"]) not in closed
    ]
    open_.sort(key=lambda item: item["ledger_index"], reverse=True)
    return {
        "until": until.isoformat() if until is not None else None,
        "headline": i18n.loc(rules.HEADLINE),
        "basis": i18n.loc(rules.BASIS),
        "open": [_view(store, item) for item in open_],
    }
