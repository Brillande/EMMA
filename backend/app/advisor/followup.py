"""Seguimiento de una contramedida: de "hágase" a "¿ha servido?".

La especificacion del equipo (§7, §14) cierra el ciclo con "confirmacion humana → seguimiento
de la recuperacion". Hasta ahora EMMA recomendaba y ahi se acababa: nadie registraba que la
tripulacion habia adoptado la contramedida, ni cuando tocaba mirar si habia servido.

El estado se **deriva**, no se guarda, igual que las alertas: el ledger solo registra las
decisiones humanas (adoptar, cerrar y no adoptar), firmadas por la consola. Lo demas —si sigue
en ventana, si ya se puede evaluar y que dice la evaluacion— se recalcula con los datos del momento.

LA EVALUACION NO ES UNA PRUEBA DE EFICACIA
------------------------------------------
Compara el nivel del dominio cuando se adopto con el de ahora, y comprueba que se ha repetido
la medida de seguimiento. No introduce ningun umbral ni estadistico nuevo (invariante 5: los
ejes de validacion no se tocan desde aqui), y dice siempre que coincidir en el tiempo no
demuestra que la contramedida sea la causa. Quien cierra el seguimiento es una persona.

EL NIVEL, AL CERRAR (2026-10-13)
--------------------------------
El cierre no guardaba el nivel del dominio, asi que de una adopcion cerrada hace semanas solo se
podia decir «como esta hoy frente a entonces», que mezcla todo lo que paso despues del cierre.
Desde esa fecha el asiento de cierre lleva, como campos opcionales, el nivel del dominio en el
estado del instante en que se cerro y ese instante (los calcula la ruta; no los manda el cliente).
`followups` da entonces, AL LADO de la evaluacion de siempre, una segunda comparacion: nivel al
adoptar frente a nivel al cerrar. Sigue siendo la comparacion de dos niveles, con la misma nota de
causalidad. Un cierre anterior no tiene ese nivel y no se le inventa: `level_at_close` y
`evaluation_at_close` van a `None`, y quien lo lee dice que compara con el estado actual.

DECIR QUE NO TAMBIEN ES UNA DECISION (2026-10-09)
-------------------------------------------------
Se podia adoptar o cerrar, pero no dejar dicho "esta no la adoptamos, y por esto". La decision
de no actuar no dejaba rastro, y es justo la que Tierra querra entender despues (especificacion
§2, human-in-the-loop). `DECLINED` es un tercer valor de `action` en el mismo asiento, con motivo
obligatorio. Es el REGISTRO de una decision humana, no una evaluacion: no cierra la alerta, no la
silencia, no baja ningun nivel y no retira la recomendacion, que vuelve a salir mientras los datos
la sostengan, con la nota de lo decidido al lado (`with_decisions`). Nada de este modulo lo lee
el analisis ni la puntuacion.

COMO SE CONSULTA LO DECIDIDO
----------------------------
`standing_declines(decisions)` da, por contramedida, el ultimo "no" que sigue en pie (deja de
estarlo si despues se adopta: la gente cambia de opinion, y eso tambien se firma).
`open_adoption(decisions, id)` da la adopcion sin cerrar de una contramedida. Las dos reciben los
asientos de `store.followup_decisions(subject)` ya filtrados a los que cuentan.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence
from typing import Any

from app.advisor import countermeasures
from app.analysis.risk import RiskLevel
from app.core import i18n
from app.core.storage import RULES_VERSION_FIELD
from app.core.versioning import decided_with
from app.ingest.codes import get
from app.ingest.fhir import VitalObservation

ADOPTED = "adopted"
CLOSED = "closed"
DECLINED = "declined"
ACTIONS = (ADOPTED, CLOSED, DECLINED)

# Que significa un "no", dicho siempre junto a el: texto de registro, nunca una orden.
DECLINE_MEANING = (
    "Es el registro de una decisión humana, no una evaluación: no cierra ni silencia ninguna "
    "alerta, no cambia ningún nivel, y la recomendación sigue saliendo mientras los datos la "
    "sostengan."
)

_ORDER = [RiskLevel.NOMINAL, RiskLevel.WATCH, RiskLevel.CONCERN, RiskLevel.CRITICAL]

CAUSALITY_NOTE = (
    "Que el cambio coincida en el tiempo no demuestra que la contramedida sea la causa."
)
i18n.en_many({
    DECLINE_MEANING: (
        "It is the record of a human decision, not an evaluation: it neither closes nor "
        "silences any alert, it changes no level, and the recommendation keeps appearing for "
        "as long as the data support it."
    ),
    CAUSALITY_NOTE: (
        "That the change coincides in time does not show that the countermeasure is the cause."
    ),
})


def _outcome(before: RiskLevel, now: RiskLevel) -> str:
    delta = _ORDER.index(now) - _ORDER.index(before)
    if delta < 0:
        return "improved"
    if delta > 0:
        return "worsened"
    return "unchanged"


def _evaluation(
    item: countermeasures.Countermeasure,
    before: RiskLevel,
    now: RiskLevel,
    repeated: Sequence[str],
    at_close: bool = False,
) -> dict[str, Any]:
    """Dos niveles comparados, y si se repitio la medida. Nada mas: no es una valoracion.

    Con `at_close`, `now` es el nivel que el cierre dejo guardado y `repeated` lo repetido hasta
    ese instante: la misma regla, con otro extremo, y dicho con otras palabras.
    """
    if i18n.current() == "en":
        return _evaluation_en(item, before, now, repeated, at_close)
    missing = [key for key in item.followup_checks if key not in repeated]
    if item.followup_checks and len(missing) == len(item.followup_checks):
        names = ", ".join(get(key).display_es for key in item.followup_checks)
        if at_close:
            return {
                "outcome": "no_repeat",
                "text": (
                    f"No se había repetido la medida de seguimiento ({names}) entre la "
                    f"adopción y el cierre: no hay con qué evaluar."
                ),
            }
        return {
            "outcome": "no_repeat",
            "text": (
                f"No se ha repetido la medida de seguimiento ({names}) desde que se adoptó: "
                f"no hay con qué evaluar."
            ),
        }
    outcome = _outcome(before, now)
    domain = item.domain.display if item.domain is not None else "hábitat"
    span = "entre la adopción y el cierre" if at_close else "desde que se adoptó"
    if outcome == "unchanged":
        verb = "siguió" if at_close else "sigue"
        text = f"El dominio {domain} {verb} en {now.display} {span}."
    else:
        text = (
            f"El dominio {domain} pasó de {before.display} a {now.display} {span}."
        )
    return {"outcome": outcome, "text": f"{text} {CAUSALITY_NOTE}"}


def _evaluation_en(
    item: countermeasures.Countermeasure,
    before: RiskLevel,
    now: RiskLevel,
    repeated: Sequence[str],
    at_close: bool,
) -> dict[str, Any]:
    """La evaluación de `_evaluation`, dicha en inglés: la misma regla y los mismos resultados.

    Va aparte y no frase a frase porque el castellano de arriba se compone por trozos («sigue» o
    «siguió», «desde que se adoptó») que en inglés no caen en el mismo sitio.
    """
    span = "between adoption and closure" if at_close else "since it was adopted"
    if item.followup_checks and not any(key in repeated for key in item.followup_checks):
        names = ", ".join(get(key).display_es for key in item.followup_checks)
        verb = "had not been" if at_close else "has not been"
        return {
            "outcome": "no_repeat",
            "text": (
                f"The follow-up measurement ({names}) {verb} repeated {span}: there is "
                f"nothing to evaluate with."
            ),
        }
    outcome = _outcome(before, now)
    domain = item.domain.display if item.domain is not None else "habitat"
    if outcome == "unchanged":
        verb = "stayed" if at_close else "remains"
        text = f"The {domain} domain {verb} at {now.display} {span}."
    else:
        text = f"The {domain} domain went from {before.display} to {now.display} {span}."
    return {"outcome": outcome, "text": f"{text} {i18n.loc(CAUSALITY_NOTE)}"}


def _at_close(closure: dict[str, Any]) -> tuple[RiskLevel, dt.datetime] | None:
    """El nivel que el cierre dejo guardado y el instante de su estado, o `None`.

    `None` para un cierre firmado antes de 2026-10-13 (no lleva esos campos) y tambien para uno
    cuyo nivel o instante no se entienda: una copia descriptiva ilegible no puede tumbar el
    estado, y sin ella se dice que el cierre no guardo el nivel, que es lo que se puede afirmar.
    """
    try:
        level = RiskLevel(closure["level_at_close"])
        moment = dt.datetime.fromisoformat(closure["closed_reference_time"])
    except (KeyError, ValueError):
        return None
    return (level, moment) if moment.tzinfo is not None else None


def followups(
    decisions: Iterable[dict[str, Any]],
    current_levels: dict[str, RiskLevel],
    observations: Sequence[VitalObservation],
    now: dt.datetime,
) -> list[dict[str, Any]]:
    """Estado de cada contramedida adoptada, a partir de las decisiones firmadas.

    `decisions` son los asientos `countermeasure-followup` que cuentan (firmados por la
    consola), con su `ledger_index`. `now` es el instante del estado: la ultima lectura, o el
    corte de Tierra.
    """
    ordered = sorted(decisions, key=lambda item: item["ledger_index"])
    closures = {
        int(item["adoption_index"]): item for item in ordered if item["action"] == CLOSED
    }
    result: list[dict[str, Any]] = []
    for adoption in ordered:
        if adoption["action"] != ADOPTED:
            continue
        try:
            item = countermeasures.get(adoption["countermeasure_id"])
        except KeyError:
            continue
        adopted_at = dt.datetime.fromisoformat(adoption["reference_time"])
        window_end = adopted_at + dt.timedelta(hours=item.followup_window_hours)
        closure = closures.get(adoption["ledger_index"])
        before = RiskLevel(adoption["level"])
        current = current_levels.get(adoption["domain"], RiskLevel.NOMINAL)
        repeated = sorted({
            obs.key for obs in observations
            if obs.key in item.followup_checks and obs.effective > adopted_at
        })
        if closure is not None:
            state = "closed"
        elif now < window_end:
            state = "in_window"
        else:
            state = "due"
        # AL CIERRE (2026-10-13). El cierre guarda el nivel del dominio en el estado de ese
        # instante: con el se compara «al adoptar frente a al cerrar», al lado de la evaluacion
        # de siempre (frente al estado que se mira), que no cambia. Lo repetido se cuenta hasta
        # el cierre, para comparar cosas iguales. Es una copia de lo que el motor ya calculo:
        # de aqui no sale ningun nivel, alerta ni recomendacion.
        at_close = _at_close(closure) if closure is not None else None
        level_at_close: RiskLevel | None = None
        closed_at: dt.datetime | None = None
        evaluation_at_close: dict[str, Any] | None = None
        if at_close is not None:
            level_at_close, closed_at = at_close
            by_then = sorted({
                obs.key for obs in observations
                if obs.key in item.followup_checks and adopted_at < obs.effective <= closed_at
            })
            evaluation_at_close = _evaluation(
                item, before, level_at_close, by_then, at_close=True
            )
        result.append({
            "adoption_index": adoption["ledger_index"],
            "countermeasure": item.to_dict(),
            "domain": adoption["domain"],
            "level_at_adoption": str(before),
            "adopted_at": adopted_at.isoformat(),
            "adopted_by": adoption["decided_by"],
            "window_ends": window_end.isoformat(),
            "state": state,
            "repeated_checks": repeated,
            # En ventana todavia no toca: evaluar antes de tiempo invita a abandonar.
            "evaluation": (
                None if state == "in_window" else _evaluation(item, before, current, repeated)
            ),
            "closed_by": closure["decided_by"] if closure else None,
            "closed_reason": closure["reason"] if closure else None,
            # Del cierre: el instante del estado en que se cerro (en el tiempo de los datos,
            # como `adopted_at`), cuando se firmo el asiento, el nivel que guardo y la
            # comparacion con el. `None` si no esta cerrada o si el cierre es anterior al campo.
            "closed_at": closed_at.astimezone(dt.UTC).isoformat() if closed_at else None,
            "closed_recorded_at": closure.get("recorded") if closure else None,
            "level_at_close": str(level_at_close) if level_at_close is not None else None,
            "evaluation_at_close": evaluation_at_close,
            # Con que reglas se firmaron la adopcion y el cierre, frente a las de hoy
            # (`record-integrity.md` §3.26): leido del asiento y dicho; no se recalcula nada.
            "adoption_rules": decided_with(adoption.get(RULES_VERSION_FIELD)),
            "closure_rules": (
                decided_with(closure.get(RULES_VERSION_FIELD)) if closure is not None else None
            ),
        })
    return result


def open_adoption(
    decisions: Iterable[dict[str, Any]], countermeasure_id: str
) -> dict[str, Any] | None:
    """La adopcion de esa contramedida que sigue sin cerrar, o `None`."""
    ordered = sorted(decisions, key=lambda item: item["ledger_index"])
    closed = {item["adoption_index"] for item in ordered if item["action"] == CLOSED}
    return next(
        (
            item for item in ordered
            if item["action"] == ADOPTED
            and item["countermeasure_id"] == countermeasure_id
            and str(item["ledger_index"]) not in closed
        ),
        None,
    )


def standing_declines(decisions: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Por contramedida, el ultimo "no adoptar" que sigue en pie.

    Sigue en pie mientras no haya una adopcion posterior de esa misma contramedida. Un "no"
    repetido sustituye al anterior: vale el ultimo motivo. El cierre de un seguimiento no cuenta
    aqui: cierra una adopcion, no opina sobre adoptar.
    """
    last: dict[str, dict[str, Any]] = {}
    for item in sorted(decisions, key=lambda item: item["ledger_index"]):
        if item["action"] == DECLINED:
            last[item["countermeasure_id"]] = item
        elif item["action"] == ADOPTED:
            last.pop(item["countermeasure_id"], None)
    return last


def decision_note(decline: dict[str, Any]) -> dict[str, Any]:
    """Lo que se ensena junto a una recomendacion que se decidio no adoptar.

    El texto lo compone el backend y la interfaz lo pinta tal cual. El instante es el del estado
    que vio quien decidio (`reference_time`), en el tiempo de los datos, como en las adopciones.
    """
    decided_at = dt.datetime.fromisoformat(decline["reference_time"]).astimezone(dt.UTC)
    note: dict[str, Any] = {
        "action": DECLINED,
        "ledger_index": decline["ledger_index"],
        "decided_at": decided_at.isoformat(),
        "decided_by": decline["decided_by"],
        "reason": decline["reason"],
        "text": (
            f"Se decidió no adoptarla el {decided_at:%Y-%m-%d %H:%M} UTC "
            f"({decline['decided_by']}): {decline['reason']}"
        ),
        "meaning": DECLINE_MEANING,
        # Con que reglas se firmo el «no» (§3.26 de `record-integrity.md`).
        "rules": decided_with(decline.get(RULES_VERSION_FIELD)),
    }
    if i18n.current() == "en":
        # Quién decidió y su motivo son lo firmado, tal cual; lo de alrededor, en inglés.
        note["text"] = (
            f"It was decided not to adopt it on {decided_at:%Y-%m-%d %H:%M} UTC ("
            f"{decline['decided_by']}): {decline['reason']}"
        )
        note["meaning"] = i18n.loc(str(note["meaning"]))
    return note


def with_decisions(
    recommendations: Sequence[dict[str, Any]], decisions: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Cada recomendacion con lo que una persona ya decidio sobre ella, o `None`.

    Solo ANADE el campo `decision`: no quita, no reordena y no cambia ninguna recomendacion.
    Decir que no a una contramedida no la retira de lo que el sistema recomienda.
    """
    declined = standing_declines(decisions)
    annotated: list[dict[str, Any]] = []
    for item in recommendations:
        measure = item.get("countermeasure") or {}
        decline = declined.get(measure.get("id", ""))
        annotated.append(
            {**item, "decision": decision_note(decline) if decline is not None else None}
        )
    return annotated
