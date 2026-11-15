"""La comida por debajo de su criterio de aceptable, con la frase de la norma al lado.

POR QUÉ EXISTE
--------------
El catálogo guardaba el 6 de la escala hedónica como «guía» (`codes.FOOD_ACCEPTABILITY`,
`reference_low=6`) y la documentación decía «guía ≥ 6, no alerta»; pero ninguna pantalla decía
qué valoraciones quedaban por debajo ni de dónde salía ese 6. En el escenario `menu-fatigue` la
aceptabilidad cae semana a semana y el dominio de nutrición sigue «nominal», con razón: una guía
sobre la comida no es un umbral sobre la persona. Lo que faltaba era decirlo valoración a
valoración, con la fuente delante.

El usuario decidió (2026-10-15) que el criterio se evalúe: cada valoración por debajo de 6,0 se
marca «por debajo del criterio de aceptable de la comida», con la frase exacta de NASA-STD-3001
Vol. 2 Rev F, [V2 7002], y su página. La frase se leyó en el PDF oficial
(`data/instruments_read.json`, `v2-7002-acceptable-6`) y escribe «6.0 or better»: el 6,0 se
adopta porque está escrito así. Si la frase no lo escribiera, el cargador no lo dejaría pasar y
aquí no se marcaría nada (`criterion` sería `None`).

LO QUE ES Y LO QUE NO ES
------------------------
Es una marca sobre la COMIDA, no sobre la persona. No entra en niveles, alertas, puntuaciones ni
recomendaciones (invariante 5): ningún módulo del motor la importa, el estado no la lee y la ruta
que la sirve no escribe nada.

La norma habla de la valoración global de un alimento de NASA a lo largo de la misión; EMMA
compara con esa cifra cada valoración registrada, una a una. Es una lectura de EMMA y se dice
con esas palabras: una valoración por debajo no dice que el alimento deje de ser aceptable para
la norma.

Se compara el valor registrado, sin redondear. La escala se enseña con un decimal, y 5,96 se
leería «6,0» junto a la marca de «por debajo»: cuando el redondeo cambiaría el lado del criterio,
la cifra lleva los decimales que hagan falta para que se vea.

PLATO A PLATO (decisión del usuario, 2026-10-26)
------------------------------------------------
Desde que la valoración lleva el alimento (`ingest/food_item.py`), las valoraciones se agrupan
por plato: cuántas veces se valoró cada uno, en cuántos días, y cada valoración en el tiempo. Es
la repetición del menú de la conversación de ideación, CONTADA, no juzgada: no hay umbral nuevo,
ni veredicto de «fatiga de menú» (en lo leído su sentido está contestado: `ingest/simulator.py`),
ni nada que el estado lea. La única marca sigue siendo la del criterio de 6,0, valoración a
valoración. Lo firmado sin alimento (lo anterior al campo, lo del simulador) se cuenta aparte y
no se reparte entre platos.

DE LA PRIMERA A LA ÚLTIMA, Y LO QUE SE DEJÓ (decimonovena ronda, 2026-10-31)
----------------------------------------------------------------------------
La conversación de ideación habla de «cambios de preferencia durante la misión». Cada plato dice
ahora, con palabras, de cuánto a cuánto fue entre su primera y su última valoración («de 7,0 a
4,0 puntos entre el 2026-09-03 y el 2026-09-10»): una comparación DESCRIPTIVA, sin umbral, sin
veredicto y sin color. Y si la fracción de la ración que se deja sin comer
(`food-rejected-fraction`) lleva el mismo plato —desde esta ronda puede llevarlo, opcional—, se
enseña al lado, también la primera y la última. Nada de esto entra en el análisis.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from typing import Any

from app.analysis.data_quality import source_label
from app.core import display
from app.ingest import food_item
from app.ingest.codes import get
from app.ingest.fhir import ObservationType, VitalObservation

KEY = "food-acceptability"
REJECTED_KEY = "food-rejected-fraction"

MARK = "por debajo del criterio de aceptable de la comida"
SCOPE = (
    "Es una marca sobre la comida, no sobre la persona: no entra en niveles, alertas, "
    "puntuaciones ni recomendaciones, y el estado no la lee."
)
APPLIES = (
    "La norma lo dice de la valoración global de un alimento de NASA a lo largo de la misión; "
    "EMMA lo compara con cada valoración registrada, una a una. Una valoración por debajo dice "
    "que esa comida quedó por debajo del criterio ese día, no que el alimento deje de ser "
    "aceptable para la norma."
)
NO_CRITERION = "Sin criterio leído en la fuente: no se marca ninguna valoración."
NOT_MEASURED = (
    "Solo cuentan como valoraciones las lecturas medidas: una inferida o predicha no es la "
    "valoración de nadie."
)

NO_FOOD = "sin alimento declarado"
WITHOUT_FOOD_NOTE = (
    "Las valoraciones sin alimento declarado (las anteriores a este campo, las del simulador) "
    "se cuentan aparte: no se reparten entre platos."
)
REPETITION_NOTE = (
    "Descriptivo: cuántas veces se valoró cada plato, en cuántos días distintos y cada "
    "valoración en el tiempo. No dice si hay fatiga de menú: no hay umbral ni veredicto, y el "
    "estado no lo lee."
)
CHANGE_NOTE = (
    "De la primera a la última: la primera valoración del plato y la última, con sus fechas "
    "(UTC). Es una comparación descriptiva de dos cifras, sin umbral ni veredicto: no dice si "
    "la preferencia cambió ni por qué."
)
REJECTED_NOTE = (
    "Si la fracción de la ración que se deja sin comer se anotó con el nombre del plato, se "
    "enseña junto a sus valoraciones: cuántas veces, la primera y la última. Sin umbral ni "
    "veredicto, y el estado no lo lee."
)
NO_REJECTED = "Sin fracción rechazada declarada para este plato."

# Hasta cuántos decimales se alarga una cifra para que el redondeo no esconda de qué lado del
# criterio cae. Más allá, la diferencia no es de una valoración.
_MAX_DECIMALS = 6


def is_below(value: float, threshold: float) -> bool:
    """Por debajo del criterio: estrictamente menor. La fuente da por aceptable «6.0 or better»."""
    return value < threshold


def _written(value: float, decimals: int) -> float:
    """La cifra tal como la escribe `display.number` con esos decimales."""
    return float(f"{value:.{decimals}f}")


def value_text(value: float, threshold: float | None) -> str:
    """La valoración como se lee, con los decimales que hagan falta para no cambiarla de lado."""
    code = get(KEY)
    decimals = display.decimals_for(KEY)
    if threshold is not None:
        below = is_below(value, threshold)
        while decimals < _MAX_DECIMALS and is_below(_written(value, decimals), threshold) != below:
            decimals += 1
    return f"{display.number(value, decimals)} {display.unit(code.unit)}"


def _count(value: int) -> str:
    return display.number(value, 0)


def _summary(subject: str, rated: int, below: int, criterion: dict[str, Any] | None) -> str:
    if rated == 0:
        return f"Sin valoraciones de la comida en el registro de {subject}."
    if criterion is None:
        return (
            f"{_count(rated)} valoraciones de la comida en el registro de {subject}. "
            f"{NO_CRITERION}"
        )
    threshold = display.number(criterion["value"], display.decimals_for(KEY))
    return (
        f"{_count(below)} de {_count(rated)} valoraciones de la comida en el registro de "
        f"{subject} quedan {MARK} ({threshold})."
    )


def _criterion(criterion: dict[str, Any] | None) -> dict[str, Any] | None:
    if criterion is None:
        return None
    threshold = display.number(criterion["value"], display.decimals_for(KEY))
    return {
        "value": criterion["value"],
        "value_text": threshold,
        "literal": criterion["literal"],
        # La frase de la norma, en su idioma, con su sección, página, ficha y fecha de lectura.
        "language": criterion["language"],
        "statement": criterion["statement"],
        "mark": MARK,
        "rule": (
            f"Se marca cada valoración por debajo de {threshold}: la norma da por aceptable "
            f"«{criterion['literal']}». Se compara el valor registrado, sin redondear."
        ),
        "applies_to": APPLIES,
        "scope": SCOPE,
    }


def _times(count: int) -> str:
    return "1 vez" if count == 1 else f"{_count(count)} veces"


def _days(count: int) -> str:
    return "en 1 día" if count == 1 else f"en {_count(count)} días distintos"


def _day(when: dt.datetime) -> str:
    """El día de una lectura, en UTC y en la forma ISO: la misma que escribe la consola."""
    return when.astimezone(dt.UTC).date().isoformat()


def _point(item: VitalObservation, text: str) -> dict[str, Any]:
    return {"effective": item.effective.isoformat(), "value": item.value, "value_text": text}


def _change(ordered: list[VitalObservation], threshold: float | None) -> dict[str, Any]:
    """La primera y la última valoración de un plato, con palabras: de cuánto a cuánto y cuándo.

    Descriptivo: dos cifras y dos fechas, sin juzgar el sentido ni el tamaño del cambio.
    """
    first, last = ordered[0], ordered[-1]
    first_text, last_text = value_text(first.value, threshold), value_text(last.value, threshold)
    first_day, last_day = _day(first.effective), _day(last.effective)
    if len(ordered) == 1:
        statement = f"Una sola valoración: {first_text}, el {first_day}."
    elif first_day == last_day:
        statement = f"De {first_text} a {last_text}, el {first_day}."
    else:
        statement = f"De {first_text} a {last_text} entre el {first_day} y el {last_day}."
    return {
        "first": _point(first, first_text),
        "last": _point(last, last_text),
        "statement": statement,
    }


def _rejected(readings: list[VitalObservation] | None) -> dict[str, Any] | None:
    """La fracción rechazada declarada con este plato: cuántas veces, la primera y la última."""
    if not readings:
        return None
    ordered = sorted(readings, key=lambda item: item.effective)
    code = get(REJECTED_KEY)
    texts = [display.quantity(REJECTED_KEY, item.value, code.unit) for item in ordered]
    first, last = ordered[0], ordered[-1]
    if len(ordered) == 1:
        statement = f"Fracción rechazada declarada una vez: {texts[0]}, el {_day(first.effective)}."
    elif _day(first.effective) == _day(last.effective):
        statement = (
            f"Fracción rechazada declarada {_times(len(ordered))}: de {texts[0]} a {texts[-1]}, "
            f"el {_day(first.effective)}."
        )
    else:
        statement = (
            f"Fracción rechazada declarada {_times(len(ordered))}: de {texts[0]} a {texts[-1]} "
            f"entre el {_day(first.effective)} y el {_day(last.effective)}."
        )
    return {
        "times": len(ordered),
        "first": _point(first, texts[0]),
        "last": _point(last, texts[-1]),
        "statement": statement,
        "series": [_point(item, text) for item, text in zip(ordered, texts, strict=True)],
    }


def _dish(
    ratings: list[VitalObservation],
    threshold: float | None,
    rejected: list[VitalObservation] | None = None,
) -> dict[str, Any]:
    """Un plato: sus valoraciones de la primera a la última, y cuántas y en cuántos días."""
    ordered = sorted(ratings, key=lambda item: item.effective)
    # Sin criterio leído no se compara: ni «por debajo» ni «no está por debajo».
    compared = threshold is not None
    marks = [threshold is not None and is_below(item.value, threshold) for item in ordered]
    below = sum(marks)
    days = len({item.effective.astimezone(dt.UTC).date() for item in ordered})
    statement = f"Valorado {_times(len(ordered))}, {_days(days)}."
    if threshold is not None:
        statement += (
            f" {_count(below)} de {_count(len(ordered))} quedan {MARK} "
            f"({display.number(threshold, display.decimals_for(KEY))})."
        )
    left = _rejected(rejected)
    return {
        # El nombre como se escribió la última vez: el grupo no distingue mayúsculas.
        "food": ordered[-1].food,
        "times": len(ordered),
        "distinct_days": days,
        "first_effective": ordered[0].effective.isoformat(),
        "last_effective": ordered[-1].effective.isoformat(),
        "below": below if compared else None,
        "statement": statement,
        # De la primera a la última valoración, con palabras (decimonovena ronda): descriptivo.
        "change": _change(ordered, threshold),
        # La fracción rechazada anotada con este plato, si la hay; y las palabras para cuando no.
        "rejected": left,
        "rejected_display": left["statement"] if left is not None else NO_REJECTED,
        "series": [
            {
                "effective": item.effective.isoformat(),
                "value": item.value,
                "value_text": value_text(item.value, threshold),
                "below": mark if compared else None,
                "mark": MARK if mark else None,
            }
            for item, mark in zip(ordered, marks, strict=True)
        ],
    }


def _by_dish(readings: Iterable[VitalObservation]) -> dict[str, list[VitalObservation]]:
    """Las lecturas con alimento, agrupadas por plato (`food_item.group_key`)."""
    groups: dict[str, list[VitalObservation]] = {}
    for item in readings:
        if item.food is not None:
            groups.setdefault(food_item.group_key(item.food), []).append(item)
    return groups


def dishes(
    rated: Iterable[VitalObservation],
    threshold: float | None,
    rejected: Iterable[VitalObservation] = (),
) -> list[dict[str, Any]]:
    """Las valoraciones con alimento, por plato: el más valorado primero; a igualdad, el último.

    `rated` son ya las valoraciones medidas; las que no llevan alimento no se agrupan. `rejected`
    son las fracciones rechazadas medidas: las que llevan el plato de alguna valoración se enseñan
    con él; las de un plato que nadie valoró, o sin plato, no hacen plato (son de la comida en
    general, y ya se enseñan en su indicador).
    """
    groups = _by_dish(rated)
    left = _by_dish(rejected)
    built = [_dish(items, threshold, left.get(key)) for key, items in groups.items()]
    # Por el instante y no por su texto ISO: con dos desfases horarios distintos, el texto no
    # va en el orden del tiempo.
    built.sort(key=lambda dish: dt.datetime.fromisoformat(dish["last_effective"]), reverse=True)
    built.sort(key=lambda dish: dish["times"], reverse=True)
    return built


def _dishes_statement(rated: int, with_food: int, count: int) -> str:
    without = rated - with_food
    plates = "1 plato" if count == 1 else f"{_count(count)} platos"
    ratings = "1 valoración" if with_food == 1 else f"{_count(with_food)} valoraciones"
    return f"{plates} en {ratings} con alimento; {_count(without)} sin alimento declarado."


def describe(
    subject: str,
    readings: Iterable[VitalObservation],
    criterion: dict[str, Any] | None,
    limit: int,
) -> dict[str, Any]:
    """Cada valoración de la comida del tripulante, la última primero, marcada frente al criterio.

    `readings` son las lecturas firmadas del registro; solo se miran las de aceptabilidad y,
    de ellas, las medidas; y, desde la decimonovena ronda, las fracciones rechazadas medidas con
    plato, para ponerlas junto a sus valoraciones. `criterion` es el de
    `instruments_read.scale_criterion`, o `None` si no hay ninguno leído: entonces no se marca
    nada. Cuenta sobre todas; enseña `limit`.
    """
    threshold = criterion["value"] if criterion is not None else None
    rated: list[VitalObservation] = []
    rejected: list[VitalObservation] = []
    not_measured = 0
    for reading in readings:
        if reading.key == REJECTED_KEY:
            if reading.observation_type is ObservationType.MEASURED and reading.food is not None:
                rejected.append(reading)
            continue
        if reading.key != KEY:
            continue
        if reading.observation_type is not ObservationType.MEASURED:
            not_measured += 1
            continue
        rated.append(reading)
    rated.sort(key=lambda item: item.effective, reverse=True)
    marks = [
        threshold is not None and is_below(item.value, threshold) for item in rated
    ]
    below = sum(marks)
    code = get(KEY)
    by_dish = dishes(rated, threshold, rejected)
    with_food = sum(dish["times"] for dish in by_dish)
    return {
        "subject": subject,
        "key": KEY,
        "display": code.display,
        "display_es": code.display_es,
        "criterion": _criterion(criterion),
        "rated": len(rated),
        "below": below if threshold is not None else None,
        "statement": _summary(subject, len(rated), below, criterion),
        "not_measured_excluded": not_measured,
        "not_measured_note": NOT_MEASURED,
        "shown": min(limit, len(rated)),
        # Plato a plato (decisión del usuario, 2026-10-26): descriptivo, sobre todas las
        # valoraciones medidas, no solo las `limit` que se enseñan.
        "dishes": by_dish,
        "dishes_statement": _dishes_statement(len(rated), with_food, len(by_dish)),
        "without_food": len(rated) - with_food,
        "without_food_note": WITHOUT_FOOD_NOTE,
        "repetition_note": REPETITION_NOTE,
        # Lo que dicen `change` y `rejected` de cada plato, y lo que no (decimonovena ronda).
        "change_note": CHANGE_NOTE,
        "rejected_note": REJECTED_NOTE,
        "grouping": food_item.GROUPING,
        "ratings": [
            {
                "effective": item.effective.isoformat(),
                "value": item.value,
                "value_text": value_text(item.value, threshold),
                # El alimento firmado con la valoración; `None` si no lo lleva.
                "food": item.food,
                "food_display": item.food if item.food is not None else NO_FOOD,
                "source": item.source,
                "source_display": source_label(item.source),
                "observation_type": str(item.observation_type),
                "evidence_context": str(item.evidence),
                # `None` sin criterio leído: no es «no está por debajo», es que no se compara.
                "below": mark if threshold is not None else None,
                "mark": MARK if mark else None,
            }
            for item, mark in list(zip(rated, marks, strict=True))[:limit]
        ],
    }
