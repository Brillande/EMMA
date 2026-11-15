"""Rutas de las notas de Tierra a bordo: firmarlas en Tierra y leerlas, con el retardo, a bordo.

Por qué es un módulo aparte: es la única escritura que hace la consola de Tierra, con su propia
clave (`routes.GROUND_IDENTITY`), y su propia regla de lenguaje (`core/ground_notes.py`). Lo que
comparte con las demás acciones de consola —el almacén, las identidades, el 422 de un dato que el
ledger no admite— se reutiliza de `routes.py`.

El retardo: la nota viaja cuando se firma. A bordo se pide con `until` = el reloj menos un tiempo
de luz (`arrivalCut` en `frontend/src/lib/crew.ts`, la cuenta con que la consola de Tierra corta lo
que baja, al revés), y lo firmado después de ese corte no se entrega **ni se cuenta**: a bordo no
se puede saber que hay una nota en camino. Sin `until` (la consola de Tierra, o a bordo sin
efemérides, sin retardo que aplicar) se entrega todo.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.routes import GROUND_IDENTITY, StoreDep, _recorded_or_422, identity_for
from app.core.ground_notes import BASIS, GROUND_NOTE_KINDS, MAX_TEXT, REFUSED, problem
from app.core.storage import CREW_SUBJECT

ground_notes_router = APIRouter(prefix="/ground-notes")

# Cómo se lee el destinatario «toda la tripulación».
CREW_DISPLAY = "toda la tripulación"


class GroundNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Un tripulante con lecturas, o `tripulacion` para toda la tripulación.
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    kind: str
    # La regla de longitud la impone el almacén con su motivo; aquí, un tope para no leer de más.
    text: str = Field(max_length=4 * MAX_TEXT)
    # Declarado, sin autenticar, como toda acción de consola (`record-integrity.md` §7.5).
    signed_by: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
    ]


@ground_notes_router.get("/rules")
def ground_note_rules() -> dict[str, Any]:
    """Las clases de nota con su palabra, el tope y lo que se rechaza: la interfaz no lo redacta."""
    return {
        "kinds": [
            {"code": code, "display": display} for code, display in GROUND_NOTE_KINDS.items()
        ],
        "max_length": MAX_TEXT,
        "crew_subject": CREW_SUBJECT,
        "crew_display": CREW_DISPLAY,
        "basis": BASIS,
        "refused": REFUSED,
    }


@ground_notes_router.post("", status_code=201)
def sign_ground_note(store: StoreDep, payload: GroundNoteIn) -> dict[str, Any]:
    """Firma en el ledger una nota de Tierra para un tripulante o para toda la tripulación.

    422 con el motivo si no es información ni pregunta, si no pasa el filtro de lenguaje o si
    manda (`core/ground_notes.problem`), o si el destinatario no es un tripulante con lecturas ni
    toda la tripulación: una nota a «crew-1» no la leería nadie.
    """
    if payload.subject != CREW_SUBJECT and payload.subject not in store.subjects():
        raise HTTPException(
            status_code=422,
            detail=(
                f"destinatario desconocido: {payload.subject!r}; un tripulante con lecturas o "
                f"{CREW_SUBJECT!r} ({CREW_DISPLAY})"
            ),
        )
    entry = _recorded_or_422(
        lambda: store.record_ground_note(
            payload.subject, payload.kind, payload.text, payload.signed_by,
            identity_for(GROUND_IDENTITY),
        )
    )[0]
    return {
        "ledger_index": entry.index,
        "content_hash": entry.content_hash,
        "signed_at": entry.recorded.isoformat(),
    }


def _shown(note: dict[str, Any]) -> bool:
    """Firmada por la consola de Tierra y aceptable con la regla vigente.

    Una nota firmada con otra clave no es de Tierra; una que el filtro de hoy rechazaría no se
    enseña aunque se firmara con el de ayer (fail-closed: la invariante 7 vale al leer).
    """
    return (
        note.get("signer") == GROUND_IDENTITY
        and problem(note["kind"], note["text"], note["signed_by"]) is None
    )


def _view(note: dict[str, Any]) -> dict[str, Any]:
    to_all = note["subject"] == CREW_SUBJECT
    return {
        "ledger_index": note["ledger_index"],
        "kind": note["kind"],
        "kind_display": GROUND_NOTE_KINDS[note["kind"]],
        "text": note["text"],
        "signed_by": note["signed_by"],
        "signed_at": note["recorded"],
        "addressed_to": note["subject"],
        "addressed_to_display": CREW_DISPLAY if to_all else note["subject"],
    }


@ground_notes_router.get("")
def list_ground_notes(
    store: StoreDep,
    subject: str = "crew-01",
    until: Annotated[dt.datetime | None, Query()] = None,
) -> dict[str, Any]:
    """Las notas de Tierra a un tripulante y a toda la tripulación, de la más antigua a la última.

    `until` es para la consola de tripulación: lo firmado en Tierra después de ese instante
    todavía no ha llegado, y no se entrega ni se cuenta. `withheld` cuenta las ya llegadas que no
    se enseñan (otra clave, o un texto que la regla vigente rechaza), con su frase.
    """
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    arrived = [
        note for note in store.ground_notes(subject, CREW_SUBJECT)
        if until is None or dt.datetime.fromisoformat(note["recorded"]) <= until
    ]
    shown = sorted((note for note in arrived if _shown(note)), key=lambda n: n["ledger_index"])
    withheld = len(arrived) - len(shown)
    return {
        "subject": subject,
        "until": until.isoformat() if until is not None else None,
        "notes": [_view(note) for note in shown],
        "withheld": withheld,
        "withheld_note": (
            "Hay notas firmadas que no se enseñan: no las firmó la consola de Tierra o su texto "
            "no pasa la regla vigente (informa o pregunta, nunca manda)."
            if withheld else None
        ),
        "basis": BASIS,
    }
