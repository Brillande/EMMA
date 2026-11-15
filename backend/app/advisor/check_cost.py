"""Que cuesta una comprobacion del detalle de alerta (base de conocimiento §9).

POR QUE EXISTE
--------------
La base de conocimiento pide que cada variable lleve su «coste de medicion» (tiempo de
tripulacion, donde se procesa, latencia hasta el resultado, consumibles) para usar lo pasivo y
continuo antes que lo invasivo. Las comprobaciones del detalle de una alerta salian sin coste
aunque el repositorio ya lo tenia: el tiempo de cada accion en la biblioteca de contramedidas y el
de medir cada indicador en `ingest/cost.py`. Aqui se juntan, leidos tal cual: lo «sin clasificar»
sigue «sin clasificar» y un tiempo sin fuente es «sin cifra con fuente». Nada se suma (dos tiempos
con bases distintas no hacen un total con base) y nada se ordena.

POR QUE VIVE EN `advisor/` Y NO EN `analysis/`
----------------------------------------------
Ningun modulo del analisis lee el tiempo de tripulacion (lo vigila
`tests/test_evidence_completion.py`): el veredicto no puede depender de el. Esto es inventario de
la contramedida, del lado del consejero, y el detalle de alerta (`analysis/alert_support.py`) solo
lo pega en cada comprobacion. Es descriptivo: no puntua ni cambia ninguna alerta.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from app.core import display, i18n
from app.ingest import cost
from app.ingest.codes import get

if TYPE_CHECKING:
    from app.advisor.countermeasures import Countermeasure

UNCLASSIFIED_NOTE = cost.UNCLASSIFIED_NOTE
NO_FIGURE = "sin cifra con fuente"
NO_REPEAT = "No repite ningún indicador: no hay coste de medida que anotar."
NO_COUNTERMEASURE = "Sin contramedida estructurada detrás: sin coste declarado."
ACTION_TIME = "Tiempo de tripulación de la acción"
MODE_LABEL = "Clase de medida"
MEASURE_TIME = "Tiempo de tripulación para medirlo"
# Como dicen la biblioteca de contramedidas y el coste de medir que un tiempo no tiene fuente.
NO_SOURCE = "sin fuente"

# El inglés de lo que se sirve (`core/i18n.py`). `NO_SOURCE` no: es el valor con que se compara
# el dato, no un texto que se enseñe desde aquí.
i18n.en_many({
    NO_FIGURE: "no sourced figure",
    NO_REPEAT: "It repeats no indicator: there is no measurement cost to note.",
    NO_COUNTERMEASURE: "No structured countermeasure behind it: no declared cost.",
    ACTION_TIME: "Crew time of the action",
    MODE_LABEL: "Measurement class",
    MEASURE_TIME: "Crew time to measure it",
})


def _library_text(text: str | None) -> str | None:
    """La base de un tiempo, en el idioma de la petición si es de la biblioteca de contramedidas.

    La biblioteca se importa aquí y no arriba, como su tipo: este módulo solo la lee de paso.
    """
    if text is None:
        return None
    from app.advisor.countermeasures import LIBRARY_PATH

    return i18n.localized(text, LIBRARY_PATH)


def _minutes(value: int | None) -> str:
    return f"{display.number(value, 0)} min" if value is not None else NO_FIGURE


def _time_basis(text: str | None) -> str | None:
    """De donde sale un tiempo; «sin fuente» no se repite: ya lo dice «sin cifra con fuente»."""
    return None if text is None or text == NO_SOURCE else text


def _fact(
    key: str, label: str, shown: str, missing: bool, basis: str | None = None,
    figure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Un dato del coste: rotulo y valor; `basis`, de donde sale un tiempo (o `None`).

    `figure` es la cifra leida de una dimension con cifra (`ingest/cost.py`), para que la
    interfaz la formatee con `lib/format.ts` como en el panel del coste de medir; `None` si no hay.

    El rótulo y el valor salen en el idioma de la petición: los de este módulo, con su inglés
    registrado arriba; los de `ingest/cost.py`, con el que registre su dueño.
    """
    return {
        "key": key, "label": i18n.loc(label), "display": i18n.loc(shown), "missing": missing,
        "basis": _library_text(basis), "figure": figure,
    }


def _indicator_cost(key: str) -> dict[str, Any]:
    """Lo que `ingest/cost.py` dice de medir un indicador, sin añadir nada.

    Un indicador fuera del coste de medir queda entero «sin clasificar»: no se le supone clase.
    """
    item = cost.cost(key)
    facts: list[dict[str, Any]] = []
    if item is None:
        facts.append(_fact("mode", MODE_LABEL, cost.UNCLASSIFIED_DISPLAY, True))
        facts.append(_fact("crew_time", MEASURE_TIME, NO_FIGURE, True))
        for dimension, spec in cost.DIMENSIONS.items():
            facts.append(_fact(dimension, spec["display"], cost.UNCLASSIFIED_DISPLAY, True))
    else:
        minutes = item["crew_time_minutes"]
        facts.append(_fact("mode", MODE_LABEL, item["mode_display"], False))
        facts.append(_fact(
            "crew_time", MEASURE_TIME, _minutes(minutes), minutes is None,
            _time_basis(item["crew_time_basis"]),
        ))
        for dimension, spec in cost.DIMENSIONS.items():
            held = item["dimensions"][dimension]
            facts.append(_fact(
                dimension, spec["display"], held["display"], held["value"] == cost.UNCLASSIFIED,
                figure=held["figure"],
            ))
    name = get(key).display_es
    return {
        "key": key,
        "display_es": name,
        "facts": facts,
        "statement": f"{name}: " + "; ".join(
            f"{fact['label'].lower()}, {fact['display']}" for fact in facts
        ) + ".",
    }


def of(measure: Countermeasure | None) -> dict[str, Any]:
    """Que cuesta una comprobacion: el tiempo de la accion y el de medir lo que repite.

    El tiempo de la accion es el de la biblioteca de contramedidas (con su base, o «sin
    fuente»); el de cada indicador, el de `ingest/cost.py`. Nada se calcula ni se suma: dos
    tiempos con bases distintas no hacen un total con base.
    """
    if measure is None:
        return {"action": None, "indicators": [], "statement": i18n.loc(NO_COUNTERMEASURE)}
    minutes = measure.crew_time_minutes
    indicators = [_indicator_cost(key) for key in measure.followup_checks]
    body: dict[str, Any] = {
        "action": {
            **_fact(
                "crew_time", ACTION_TIME, _minutes(minutes), minutes is None,
                _time_basis(measure.crew_time_basis),
            ),
            "minutes": minutes,
        },
        "indicators": indicators,
        "statement": None if indicators else NO_REPEAT,
    }
    if body["statement"] is not None:
        body["statement"] = i18n.loc(body["statement"])
    return body


# Lo que puede quedar «sin clasificar» (el tiempo sin cifra es otra cosa: «sin cifra con fuente»).
_CLASSES = frozenset({"mode", *cost.DIMENSIONS})


def has_unclassified(costs: Iterable[dict[str, Any]]) -> bool:
    """Si alguna comprobacion lleva algo «sin clasificar» (para decir una vez que quiere decir)."""
    return any(
        fact["missing"] and fact["key"] in _CLASSES
        for item in costs
        for indicator in item.get("indicators", ())
        for fact in indicator["facts"]
    )
