"""Por donde va una alerta: los pasos del flujo de la base de conocimiento, con su estado.

POR QUE EXISTE
--------------
La base de conocimiento (§10) fija el flujo objetivo: SENSE → CONTEXTUALIZE → DETECT → EXPLAIN →
RELATE TO RISK → RECOMMEND CHECK/COUNTERMEASURE → HUMAN DECISION → FOLLOW-UP. Las hipotesis de
causa compartida ya decian por que paso iban (`analysis/context.py`, `flow`); las alertas, no. El
detalle de una alerta respondia a las preguntas de §10 de la especificacion, pero quien lo leia
no veia de un vistazo que habia hecho ya el sistema, que esperaba a una persona y que no le
correspondia. Todo eso ya esta en el estado: lo medido, la desviacion y su persistencia, el
contexto, la recomendacion, el reconocimiento y la adopcion firmados y el seguimiento. Aqui solo
se lee y se dice, con la misma convencion que las hipotesis (mismos estados, mismas palabras),
para que la interfaz no deduzca nada.

QUE NO HACE
-----------
No decide nada (invariante 5): no toca niveles, alertas ni el orden de nada, y el motor no
importa este modulo. «Recomendar» esta hecho cuando el sistema PROPONE, que es lo que pide el
paso: EMMA registra la adopcion firmada de una contramedida, no si alguien hizo una comprobacion,
y el texto lo dice.

QUE ADOPCIONES SON DE ESTA ALERTA
---------------------------------
Las del dominio de la alerta que siguen abiertas (en ventana o con la ventana cumplida y sin
cerrar) y las cerradas adoptadas desde su inicio, en tiempo de los datos (la regla de
`analysis/time_to_action.py`). Las abiertas cuentan aunque se adoptaran antes del inicio: el
inicio es la primera lectura fuera de lo esperado DENTRO DE LA VENTANA ACTUAL, que avanza con
ella, y una contramedida de 72 o 168 h adoptada al principio de una alerta larga quedaria fuera a
las 48 h con su seguimiento en curso. Una alerta sin inicio (tendencia o evento externo) toma
solo las abiertas.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Any

from app.analysis.context import (
    AWAITING_HUMAN,
    DONE,
    IN_PROGRESS,
    NOT_APPLICABLE,
    STEP_STATE_DISPLAY,
    STEP_STATE_DISPLAY_EN,
)
from app.analysis.risk import RiskLevel
from app.core import display, i18n

# Clave, nombre en español y nombre en la base de conocimiento, en su orden.
STEPS: tuple[tuple[str, str, str], ...] = (
    ("sense", "Medir", "SENSE"),
    ("contextualize", "Contextualizar", "CONTEXTUALIZE"),
    ("detect", "Detectar", "DETECT"),
    ("explain", "Explicar", "EXPLAIN"),
    ("relate_to_risk", "Relacionar con el riesgo", "RELATE TO RISK"),
    ("recommend", "Recomendar comprobación o contramedida", "RECOMMEND CHECK/COUNTERMEASURE"),
    ("human_decision", "Decisión humana", "HUMAN DECISION"),
    ("follow_up", "Seguimiento", "FOLLOW-UP"),
)
# El nombre de cada paso en inglés, por su clave: el de la base de conocimiento, en minúsculas.
STEP_NAMES_EN: dict[str, str] = {
    "sense": "Sense",
    "contextualize": "Contextualize",
    "detect": "Detect",
    "explain": "Explain",
    "relate_to_risk": "Relate to risk",
    "recommend": "Recommend check or countermeasure",
    "human_decision": "Human decision",
    "follow_up": "Follow-up",
}
BASIS = (
    "Flujo de la base de conocimiento del equipo (§10). Cada estado sale de lo que el sistema ya "
    "registró; describe por dónde va la alerta y no cambia su nivel."
)
EXTERNAL = "la alerta viene de un evento externo"
AWAITING_DECISION = "Pendiente de que una persona la reconozca o adopte una contramedida."
NO_FOLLOW_UP = "Sin contramedida adoptada para esta alerta: no hay seguimiento que llevar."
i18n.en_many({
    BASIS: (
        "Flow of the team's knowledge base (§10). Each state comes from what the system "
        "already recorded; it describes where the alert stands and does not change its level."
    ),
    EXTERNAL: "the alert comes from an external event",
    AWAITING_DECISION: "Awaiting a person to acknowledge it or adopt a countermeasure.",
    NO_FOLLOW_UP: (
        "No countermeasure adopted for this alert: there is no follow-up to carry out."
    ),
})
_RESOLUTION_DISPLAY = {"en_arreglo": "en arreglo", "resuelto": "resuelta"}
_RESOLUTION_DISPLAY_EN = {"en_arreglo": "being fixed", "resuelto": "resolved"}
_FOLLOW_UP_DISPLAY = {
    "in_window": "en su ventana de seguimiento",
    "due": "ventana cumplida, lista para revisar y cerrar",
}
_FOLLOW_UP_DISPLAY_EN = {
    "in_window": "in its follow-up window",
    "due": "window elapsed, ready to review and close",
}


def _count(amount: int, singular: str, plural: str) -> str:
    return f"{display.number(amount, 0)} {singular if amount == 1 else plural}"


def _entry(index: Any) -> str:
    """«(asiento 12 del registro)», en el idioma de la petición."""
    return i18n.tr(f"(asiento {index} del registro)", f"(ledger entry {index})")


def _sense(detail: Mapping[str, Any]) -> tuple[str, str]:
    sensed = detail.get("sensed") or {}
    readings, indicators = int(sensed.get("readings", 0)), int(sensed.get("indicators", 0))
    if readings:
        return DONE, i18n.tr(
            f"{_count(readings, 'lectura', 'lecturas')} de "
            f"{_count(indicators, 'indicador', 'indicadores')} del dominio en la ventana actual.",
            f"{_count(readings, 'reading', 'readings')} from "
            f"{_count(indicators, 'indicator', 'indicators')} of the domain in the current "
            "window.",
        )
    if detail.get("trends"):
        return DONE, i18n.tr(
            "Sin lecturas del dominio en la ventana actual: la tendencia sale de lecturas "
            "anteriores.",
            "No readings from the domain in the current window: the trend comes from earlier "
            "readings.",
        )
    return NOT_APPLICABLE, i18n.tr(
        f"Sin lecturas del dominio en la ventana actual: {EXTERNAL}.",
        f"No readings from the domain in the current window: {i18n.loc(EXTERNAL)}.",
    )


def _contextualize(detail: Mapping[str, Any]) -> tuple[str, str]:
    context = detail.get("context")
    if not context:
        return NOT_APPLICABLE, i18n.tr(
            "Sin contexto compuesto para esta alerta.", "No context composed for this alert."
        )
    return DONE, f"{context['summary']} {context['label'].capitalize()}."


def _detect(detail: Mapping[str, Any]) -> tuple[str, str]:
    changed, trends = len(detail.get("changed") or ()), len(detail.get("trends") or ())
    if not changed and not trends:
        return NOT_APPLICABLE, i18n.tr(
            f"Ninguna lectura ni tendencia del dominio fuera de lo esperado: {EXTERNAL}.",
            "No reading or trend of the domain outside the expected range: "
            f"{i18n.loc(EXTERNAL)}.",
        )
    text = i18n.tr(
        f"{_count(changed, 'indicador', 'indicadores')} con lecturas fuera de lo esperado y "
        f"{_count(trends, 'tendencia sostenida', 'tendencias sostenidas')}.",
        f"{_count(changed, 'indicator', 'indicators')} with readings outside the expected "
        f"range and {_count(trends, 'sustained trend', 'sustained trends')}.",
    )
    persistence = (detail.get("persistence") or {}).get("statement")
    return DONE, f"{text} {persistence}" if persistence else text


def _relate(alert: Mapping[str, Any], detail: Mapping[str, Any]) -> tuple[str, str]:
    level = i18n.loc(RiskLevel(alert["level"]).display)
    return DONE, i18n.tr(
        f"Nivel «{level}» en el dominio. {detail['relevance']}",
        f"Level «{level}» in the domain. {detail['relevance']}",
    )


def _recommend(detail: Mapping[str, Any]) -> tuple[str, str]:
    checks = detail.get("checks") or {}
    items = checks.get("items") or ()
    if not items:
        return NOT_APPLICABLE, str(
            checks.get("statement")
            or i18n.tr("Sin comprobación propuesta.", "No check proposed.")
        )
    return DONE, i18n.tr(
        f"{_count(len(items), 'comprobación propuesta', 'comprobaciones propuestas')}, en el "
        "orden del recomendador. EMMA no registra si se han hecho; sí la adopción firmada de "
        "una contramedida.",
        f"{_count(len(items), 'check proposed', 'checks proposed')}, in the recommender's "
        "order. EMMA does not record whether they have been done; it does record the signed "
        "adoption of a countermeasure.",
    )


def _decision(alert: Mapping[str, Any], adopted: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    said: list[str] = []
    if alert.get("acknowledged"):
        said.append(i18n.tr(
            f"Reconocida por {alert['acknowledged_by']} "
            f"(asiento {alert['acknowledgement_index']} del registro).",
            f"Acknowledged by {alert['acknowledged_by']} "
            f"{_entry(alert['acknowledgement_index'])}.",
        ))
    resolution = alert.get("resolution") or {}
    if resolution.get("state") in _RESOLUTION_DISPLAY:
        said.append(i18n.tr(
            f"Declarada «{_RESOLUTION_DISPLAY[resolution['state']]}» por "
            f"{resolution['declared_by']} (asiento {resolution['ledger_index']} del registro).",
            f"Declared «{_RESOLUTION_DISPLAY_EN[resolution['state']]}» by "
            f"{resolution['declared_by']} {_entry(resolution['ledger_index'])}.",
        ))
    # Descartarla también es la decisión humana del flujo («Dismiss», conversación de ideación).
    # Solo viene si es lo último que se dijo de la alerta (`api.routes._alerts`).
    dismissal = alert.get("dismissal")
    if dismissal:
        said.append(i18n.tr(
            f"Descartada por {dismissal['declared_by']}, motivo: {dismissal['reason_display']} "
            f"(asiento {dismissal['ledger_index']} del registro).",
            f"Dismissed by {dismissal['declared_by']}, reason: {dismissal['reason_display']} "
            f"{_entry(dismissal['ledger_index'])}.",
        ))
    for item in adopted:
        said.append(i18n.tr(
            f"Contramedida adoptada por {item['adopted_by']}: "
            f"{item['countermeasure']['action'].rstrip('.')} "
            f"(asiento {item['adoption_index']} del registro).",
            f"Countermeasure adopted by {item['adopted_by']}: "
            f"{item['countermeasure']['action'].rstrip('.')} "
            f"{_entry(item['adoption_index'])}.",
        ))
    if not said:
        return AWAITING_HUMAN, i18n.loc(AWAITING_DECISION)
    return DONE, " ".join(said)


def _follow_up(adopted: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    if not adopted:
        return NOT_APPLICABLE, i18n.loc(NO_FOLLOW_UP)
    parts = [
        f"{item['countermeasure']['action'].rstrip('.')}: "
        + (
            i18n.tr(_FOLLOW_UP_DISPLAY[item["state"]], _FOLLOW_UP_DISPLAY_EN[item["state"]])
            if item["state"] in _FOLLOW_UP_DISPLAY
            else i18n.tr(f"cerrada por {item['closed_by']}", f"closed by {item['closed_by']}")
        )
        for item in adopted
    ]
    states = {item["state"] for item in adopted}
    if "due" in states:
        state = AWAITING_HUMAN
    elif "in_window" in states:
        state = IN_PROGRESS
    else:
        state = DONE
    return state, "; ".join(parts) + "."


def adopted_for(
    alert: Mapping[str, Any], onset_iso: str | None, followups: Sequence[Mapping[str, Any]]
) -> list[Mapping[str, Any]]:
    """Las contramedidas adoptadas que cuentan para esta alerta (ver el docstring del modulo)."""
    domain = alert["domain"]
    onset = dt.datetime.fromisoformat(onset_iso) if onset_iso is not None else None
    return [
        item for item in followups
        if item["domain"] == domain
        and (
            item["state"] != "closed"
            or (onset is not None and dt.datetime.fromisoformat(item["adopted_at"]) >= onset)
        )
    ]


def flow(
    alert: Mapping[str, Any],
    detail: Mapping[str, Any],
    followups: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Los ocho pasos de una alerta, cada uno con su estado y una frase.

    `alert` es la de `api/routes.py` (`_alerts`), con su reconocimiento y su estado declarado;
    `detail`, el de `explain.detail` ya con su contexto; `followups`, el seguimiento de las
    contramedidas adoptadas que da el estado.
    """
    adopted = adopted_for(alert, detail.get("onset"), followups)
    states: tuple[tuple[str, str], ...] = (
        _sense(detail),
        _contextualize(detail),
        _detect(detail),
        (DONE, i18n.tr(
            "Qué cambió, desde cuándo, frente a qué base y por qué puede importar: en este "
            "detalle, como apoyo a la decisión de una persona.",
            "What changed, since when, against which baseline and why it may matter: in this "
            "detail, as support for a person's decision.",
        )),
        _relate(alert, detail),
        _recommend(detail),
        _decision(alert, adopted),
        _follow_up(adopted),
    )
    return {
        "steps": [
            {
                "key": key, "name": i18n.tr(name, STEP_NAMES_EN[key]), "kb_name": kb_name,
                "state": state,
                "state_display": i18n.tr(STEP_STATE_DISPLAY[state], STEP_STATE_DISPLAY_EN[state]),
                "detail": text,
            }
            for (key, name, kb_name), (state, text) in zip(STEPS, states, strict=True)
        ],
        "basis": i18n.loc(BASIS),
    }
