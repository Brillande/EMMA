# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cuándo una decisión humana registrada en EMMA es de alto riesgo y exige una segunda firma.

Por qué existe: EMMA no decide nada clínico, pero registra lo que deciden las personas. La firma
de un borrador de interpretación lleva un comentario, y ese comentario puede ser una decisión
("acepto; suspender la medicación y repetir en 24 h"). Una decisión así, tomada a veinte minutos
de luz de Tierra, no debería descansar en una sola persona y un solo clic.

Adaptador de `polaris/tools/decision_alto_riesgo.py`, de la copia literal de Polaris, sin
modificarla (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris,
«Beyond the Protocol»; se carga con `app.polaris.load`). El disparador es `disparar()` del
original, con sus ejes (clínica, riesgo, acción, deliberación) y sus léxicos, sin tocar. El
principio también es suyo: una decisión clínica de alto riesgo no sale de una sola voz; se reúnen
voces independientes y queda un acta con las discrepancias explícitas. En EMMA las voces son
personas de la tripulación, no agentes: la firma queda pendiente de una segunda firma de otra
persona (`core/storage.py`, `sign_draft` y `countersign_draft`).

Reglas de EMMA, encima del original (no son cambios de la copia):
  * En la firma de un borrador (`deciding=True`), una acción clínica declarada basta para
    disparar aunque no se formule como duda: firmar ya es el momento de decidir. En Polaris la
    acción tiene que venir en marco deliberativo ("¿debo…?").
  * Acciones y términos clínicos de a bordo que el léxico oncológico de Polaris no trae: punción,
    drenaje (`text_guard.EMMA_ACTIONS`), evacuación, sondaje.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from typing import Any

from app import polaris
from app.text_guard import EMMA_ACTIONS

# Términos clínicos de EMMA que no están en `_CLINICO` del original, sobre texto canónico.
_EMMA_CLINICAL = ("puncion", "drenaje", "evacuacion", "evacuar", "sondaje")
_EMMA_ACTIONS = tuple(re.compile(pattern) for pattern in EMMA_ACTIONS)


@cache
def _original() -> Any:
    return polaris.load("decision_alto_riesgo")


# Decisión del usuario (2026-09-29): los motivos de `disparar()` con la redacción de EMMA. En EMMA
# no hay "panel de élite": lo que exige una decisión de alto riesgo es la segunda firma.
_REASONS: tuple[tuple[str, str], ...] = (
    ("se está DECIDIENDO una acción clínica",
     "se decide una acción clínica (dosis, suspensión, procedimiento): segunda firma obligatoria"),
    ("la pregunta remite a una acción clínica del turno anterior",
     "remite a una acción clínica anterior: segunda firma obligatoria"),
    ("decisión CLÍNICA + ALTO RIESGO",
     "decisión clínica e irreversible o de alto riesgo: segunda firma obligatoria"),
    ("forzado por el agente",
     "marcada como de alto riesgo por precaución: segunda firma obligatoria"),
    ("parece organización/info", "no es una decisión clínica"),
)


def emma_reason(reason: str) -> str:
    """El motivo de Polaris, con la redacción de EMMA (el sentido no cambia)."""
    for theirs, ours in _REASONS:
        if reason.startswith(theirs):
            return ours
    return reason.replace("panel de élite obligatorio", "segunda firma obligatoria")


@dataclass(frozen=True)
class Trigger:
    applies: bool
    reason: str
    axes: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"applies": self.applies, "reason": self.reason, "axes": self.axes}


def trigger(text: str, deciding: bool = False) -> Trigger:
    """¿Es una decisión clínica de alto riesgo? `disparar()` del original más las reglas de EMMA.

    `deciding=True`: el texto se escribe en el momento de decidir (una firma), así que una acción
    clínica declarada basta, sin marco de duda. Ante la duda, dispara.
    """
    original = _original()
    applies, reason, found = original.disparar(text)
    plain = original._canon_txt(text)
    emma_clinical = sorted(k for k in _EMMA_CLINICAL if k in plain)
    actions = bool(found["accion"]) or any(p.search(plain) for p in _EMMA_ACTIONS)
    deliberating = bool(found["delibera"])
    risk = list(found["lex_riesgo"])
    axes: dict[str, Any] = {
        "clinical": sorted({*found["lex_clinica"], *emma_clinical}),
        "risk": risk,
        "action": actions,
        "deliberating": deliberating,
    }
    if applies:
        return Trigger(True, emma_reason(str(reason)), axes)
    if actions and (deliberating or deciding):
        return Trigger(
            True, "se decide una acción clínica (dosis, suspensión, procedimiento)", axes
        )
    if emma_clinical and risk:
        return Trigger(True, "decisión clínica e irreversible o de alto riesgo", axes)
    return Trigger(False, emma_reason(str(reason)), axes)
