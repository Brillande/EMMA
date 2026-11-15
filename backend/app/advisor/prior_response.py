"""La respuesta previa: qué pasó la otra vez que se adoptó esta misma contramedida.

La base de conocimiento del equipo pide un «Countermeasure Twin que conozca recursos, protocolos
y **respuesta previa**» (hipótesis H5). EMMA firmaba cada adopción y cada cierre y derivaba su
seguimiento, pero cuando volvía a recomendar la misma contramedida al mismo tripulante la tarjeta
no decía nada de la vez anterior: quien decide tenía que acordarse, o ir a buscarlo.

LO QUE ESTE MÓDULO NO HACE, Y POR QUÉ
-------------------------------------
* **No evalúa nada.** Lee la evaluación que `advisor/followup.py` ya calculó para cada adopción
  (el mismo objeto que el estado sirve en `followups`) y la repite con sus mismas palabras. No hay
  aquí ninguna regla, umbral ni ventana: nada que entre en `rules_version`.
* **No dice que una contramedida «funcionó».** Una evaluación de seguimiento es «el dominio hizo
  esto después de adoptarla»: no hay grupo de control, pudo deberse a otra cosa, y con una o dos
  adopciones no hay patrón. Por eso no se da ninguna tasa ni se cuenta cuántas veces «fue bien»,
  y la advertencia (`CAVEAT`) viaja siempre con el bloque, también cuando no hay historia.
* **No cambia qué se recomienda.** Solo AÑADE el campo `prior_response` a cada recomendación: ni
  quita, ni reordena, ni toca la urgencia, ni lo lee el análisis (invariante 5). Es un dato al lado.
* **No da por final una evaluación a medias.** De una adopción que sigue abierta se dice que está
  en seguimiento; su evaluación provisional se queda en el panel de seguimiento, no aquí.

CON QUÉ SE COMPARA, Y SE DICE (2026-10-13)
------------------------------------------
Hasta esa fecha el cierre no guardaba el nivel del dominio, y la única evaluación disponible era
la del seguimiento: nivel al adoptar frente al nivel del estado que se está mirando. Para una
adopción cerrada hace tiempo eso es «cómo está hoy frente a entonces», que mezcla todo lo que
pasó después del cierre. Ahora el asiento de cierre guarda el nivel de ese instante y
`advisor/followup.py` da, al lado, la evaluación «al cierre» (`evaluation_at_close`). Aquí se usa
ESA cuando existe y se rotula («Al cierre: …»). Un cierre anterior no lo guardó y no se le
inventa: sigue con la evaluación de siempre, rotulada tal cual («Este cierre no guardó el nivel:
se compara con el estado actual»). `evaluation_basis` dice, para el bloque, con qué se compara.
Cambia el extremo de la comparación, no su naturaleza: siguen siendo dos niveles, y la
advertencia (`CAVEAT`) es la misma.

Respeta `until` y qué firmas cuentan sin decidirlo: recibe los seguimientos ya derivados por el
estado, que son los de las decisiones firmadas por la consola hasta su corte.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

from app.core import i18n

NONE = "none"
OPEN = "open"
CLOSED = "closed"

NO_PRIOR = "Sin adopciones anteriores de esta contramedida para este tripulante."

# Va siempre con el bloque. Es la frase que impide leer la historia como una prueba.
CAVEAT = (
    "Es lo que pasó después, no una prueba de que fuera por la contramedida: no hay grupo de "
    "control, pudo deberse a otra cosa, y con una o dos adopciones no hay patrón."
)

AT_CLOSE = "at_close"
CURRENT_STATE = "current_state"

# El rótulo va delante de la evaluación de cada adopción cerrada: con qué extremo compara.
LABEL_AT_CLOSE = "Al cierre:"
LABEL_CURRENT_STATE = "Este cierre no guardó el nivel: se compara con el estado actual."

# Para el bloque entero, según lo que lleven sus adopciones cerradas.
EVALUATION_BASIS = (
    "La evaluación es la del seguimiento: compara el nivel del dominio cuando se adoptó con el "
    "de este estado, no con el que había al cerrarlo, porque el cierre no lo guardó."
)
EVALUATION_BASIS_AT_CLOSE = (
    "La evaluación compara el nivel del dominio cuando se adoptó con el que el cierre dejó "
    "guardado, no con el de este estado."
)
EVALUATION_BASIS_MIXED = (
    "Cada evaluación dice con qué compara el nivel del dominio cuando se adoptó: con el que el "
    "cierre dejó guardado o, si aquel cierre no lo guardó, con el de este estado."
)

OPEN_NO_EVALUATION = (
    "Sin evaluación final: el seguimiento sigue abierto y lo cierra una persona."
)

i18n.en_many({
    NO_PRIOR: "No earlier adoptions of this countermeasure for this crew member.",
    CAVEAT: (
        "It is what happened afterwards, not proof that it was due to the countermeasure: "
        "there is no control group, it may have been due to something else, and with one or "
        "two adoptions there is no pattern."
    ),
    LABEL_AT_CLOSE: "At closure:",
    LABEL_CURRENT_STATE: (
        "This closure did not store the level: it is compared with the current status."
    ),
    EVALUATION_BASIS: (
        "The evaluation is that of the follow-up: it compares the level of the domain when it "
        "was adopted with that of this status, not with the level at closure, because the "
        "closure did not store it."
    ),
    EVALUATION_BASIS_AT_CLOSE: (
        "The evaluation compares the level of the domain when it was adopted with the one the "
        "closure stored, not with that of this status."
    ),
    EVALUATION_BASIS_MIXED: (
        "Each evaluation says what it compares the level of the domain when it was adopted "
        "with: the one the closure stored or, if that closure did not store it, that of this "
        "status."
    ),
    OPEN_NO_EVALUATION: (
        "No final evaluation: the follow-up is still open and a person closes it."
    ),
})


def _loc(text: str | None) -> str | None:
    """Una constante de arriba en el idioma de la petición; `None` sigue siendo `None`."""
    return i18n.loc(text) if text is not None else None


def _when(iso: str) -> str:
    return f"{dt.datetime.fromisoformat(iso).astimezone(dt.UTC):%Y-%m-%d %H:%M} UTC"


def _checks(followup: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Los indicadores que seguía y cuáles se repitieron, con el nombre que da la biblioteca."""
    measure = followup["countermeasure"]
    names = dict(
        zip(measure["followup_checks"], measure["followup_checks_display"], strict=True)
    )
    repeated = [names[key] for key in followup["repeated_checks"] if key in names]
    return list(names.values()), repeated


def _checks_text(followed: Sequence[str], repeated: Sequence[str]) -> str:
    if not followed:
        return i18n.tr(
            "No tenía medida de seguimiento que repetir.",
            "It had no follow-up measurement to repeat.",
        )
    missing = [name for name in followed if name not in repeated]
    text = i18n.tr(f"Seguía {', '.join(followed)}.", f"It followed {', '.join(followed)}.")
    if not repeated:
        return i18n.tr(
            f"{text} No se repitió ninguna después de adoptarla.",
            f"{text} None was repeated after it was adopted.",
        )
    if missing:
        return i18n.tr(
            f"{text} Después de adoptarla se repitió {', '.join(repeated)}; "
            f"no {', '.join(missing)}.",
            f"{text} After it was adopted, {', '.join(repeated)} was repeated; "
            f"not {', '.join(missing)}.",
        )
    return i18n.tr(
        f"{text} Se repitió después de adoptarla.",
        f"{text} It was repeated after it was adopted.",
    )


def _closure_text(followup: dict[str, Any]) -> str:
    """Cómo se cerró, con su motivo firmado y, si el cierre lo guardó, cuándo."""
    closed_at = followup.get("closed_at")
    if i18n.current() == "en":
        # Quién cerró y su motivo son lo firmado, tal cual.
        on = f" on {_when(closed_at)}" if closed_at else ""
        return f"Closed{on} ({followup['closed_by']}): {followup['closed_reason']}"
    when = f" el {_when(closed_at)}" if closed_at else ""
    return f"Se cerró{when} ({followup['closed_by']}): {followup['closed_reason']}"


def _closed_evaluation(
    followup: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """La evaluación de una adopción cerrada, con qué compara y su rótulo.

    La del cierre si el cierre guardó el nivel; si no, la del seguimiento frente al estado que
    se mira. En los dos casos es el objeto que da `advisor/followup.py`, sin retocar.
    """
    at_close = followup.get("evaluation_at_close")
    if at_close is not None:
        return at_close, AT_CLOSE, LABEL_AT_CLOSE
    current = followup["evaluation"]
    if current is None:
        return None, None, None
    return current, CURRENT_STATE, LABEL_CURRENT_STATE


def _adoption(followup: dict[str, Any]) -> dict[str, Any]:
    """Una adopción anterior, contada con lo que el seguimiento ya dice de ella."""
    followed, repeated = _checks(followup)
    closed = followup["state"] == "closed"
    if closed:
        state_text = _closure_text(followup)
    elif followup["state"] == "in_window":
        state_text = i18n.tr(
            f"Sigue en seguimiento: su ventana termina el {_when(followup['window_ends'])}.",
            f"Still under follow-up: its window ends on {_when(followup['window_ends'])}.",
        )
    else:
        state_text = i18n.tr(
            f"Sigue en seguimiento: su ventana terminó el {_when(followup['window_ends'])} "
            f"y está sin cerrar.",
            f"Still under follow-up: its window ended on {_when(followup['window_ends'])} "
            f"and it has not been closed.",
        )
    # Solo una adopción cerrada enseña evaluación, y es la del seguimiento, sin retocar.
    evaluation, basis, label = _closed_evaluation(followup) if closed else (None, None, None)
    label = _loc(label)
    return {
        "adoption_index": followup["adoption_index"],
        "adopted_at": followup["adopted_at"],
        "adopted_by": followup["adopted_by"],
        "adopted_text": i18n.tr(
            f"Adoptada el {_when(followup['adopted_at'])} ({followup['adopted_by']}).",
            f"Adopted on {_when(followup['adopted_at'])} ({followup['adopted_by']}).",
        ),
        "level_at_adoption": followup["level_at_adoption"],
        "state": CLOSED if closed else OPEN,
        "state_text": state_text,
        "closed_by": followup["closed_by"],
        "closed_reason": followup["closed_reason"],
        # Del cierre, si los guardó: el instante de su estado y el nivel del dominio entonces.
        "closed_at": followup.get("closed_at"),
        "closed_recorded_at": followup.get("closed_recorded_at"),
        "level_at_close": followup.get("level_at_close"),
        "followup_checks_display": followed,
        "repeated_checks_display": repeated,
        "checks_text": _checks_text(followed, repeated),
        "evaluation": evaluation,
        # `at_close`, `current_state` o `None`: con qué extremo compara esa evaluación.
        "evaluation_basis": basis,
        "evaluation_text": (
            f"{label} {evaluation['text']}" if evaluation is not None
            else i18n.loc(OPEN_NO_EVALUATION) if not closed
            else None
        ),
    }


def _block_basis(adoptions: Sequence[dict[str, Any]]) -> str | None:
    """Con qué comparan las evaluaciones del bloque; `None` si ninguna adopción trae una."""
    bases = {item["evaluation_basis"] for item in adoptions} - {None}
    if not bases:
        return None
    if bases == {AT_CLOSE}:
        return EVALUATION_BASIS_AT_CLOSE
    if bases == {CURRENT_STATE}:
        return EVALUATION_BASIS
    return EVALUATION_BASIS_MIXED


def describe(countermeasure_id: str, followups: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Lo que pasó las otras veces que se adoptó esa contramedida, o que no hubo ninguna."""
    mine = sorted(
        (item for item in followups if item["countermeasure"]["id"] == countermeasure_id),
        key=lambda item: item["adoption_index"],
    )
    if not mine:
        nothing = {
            "state": NONE,
            "count": 0,
            "text": NO_PRIOR,
            "caveat": CAVEAT,
            "evaluation_basis": None,
            "last": None,
            "adoptions": [],
        }
        # Las dos frases, en el idioma de la petición: se resuelve lo que hay, no se repone.
        return {key: _loc(value) if isinstance(value, str) else value
                for key, value in nothing.items()}
    adoptions = [_adoption(item) for item in mine]
    last = adoptions[-1]
    times = "1 vez" if len(adoptions) == 1 else f"{len(adoptions)} veces"
    which = "el" if len(adoptions) == 1 else "la última, el"
    if i18n.current() == "en":
        times = "once" if len(adoptions) == 1 else f"{len(adoptions)} times"
        which = "on" if len(adoptions) == 1 else "the last time, on"
    return {
        "state": last["state"],
        "count": len(adoptions),
        "text": i18n.tr(
            f"Se ha adoptado {times} para este tripulante; {which} "
            f"{_when(last['adopted_at'])} ({last['adopted_by']}).",
            f"It has been adopted {times} for this crew member; {which} "
            f"{_when(last['adopted_at'])} ({last['adopted_by']}).",
        ),
        "caveat": i18n.loc(CAVEAT),
        "evaluation_basis": _loc(_block_basis(adoptions)),
        "last": last,
        "adoptions": adoptions,
    }


def with_prior_response(
    recommendations: Sequence[dict[str, Any]], followups: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Cada recomendación con la respuesta previa de su contramedida, o `None` si no lleva una.

    `followups` es lo que el estado ya derivó (`advisor.followup.followups`): mismas firmas,
    mismo corte y misma evaluación. Solo AÑADE el campo `prior_response`.
    """
    annotated: list[dict[str, Any]] = []
    for item in recommendations:
        measure = item.get("countermeasure")
        annotated.append({
            **item,
            "prior_response": describe(measure["id"], followups) if measure else None,
        })
    return annotated
