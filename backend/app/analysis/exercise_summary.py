"""El ejercicio, medido: lo que acompaña a la banda ósea y lo que cae junto a una alerta.

La especificación del equipo (§9) pone el ejercicio en dos escenarios —musculoesquelético:
«adherencia al ejercicio + actividad + día de misión + estado inferido»; hidratación/renal:
«ingesta de líquidos + proxy de orina + ejercicio + día de misión»— y en el detalle de una alerta
(§10) pregunta «¿qué contexto ha cambiado?». EMMA medía el ejercicio (`exercise-minutes`,
`loading-impacts`) y no lo enseñaba en ninguno de los dos sitios: junto a la banda de pérdida
ósea solo había un booleano, cierto con cualquier lectura —también una de 0 minutos—, y el
contexto de una alerta no lo leía.

LO QUE ES Y LO QUE NO ES
------------------------
Es una capa **descriptiva**. Lee lo que el motor ya calculó —cada lectura evaluada contra su
línea base (`Deviation`) y la tendencia (`Trend`)— y lo cuenta; no ajusta una segunda
estadística ni llama a `BaselineEngine` ni a `RiskEngine`, y ninguno de los dos lo importa.

**Lo medido acompaña a la banda; no la modifica.** El ejercicio resistivo reduce la pérdida
ósea (sentido documentado), pero no hay datos de respuesta con que calcular cuánto: estrechar o
mover la banda con estos minutos sería inventar (`docs/contexto/README.md`, «No se adopta»).

**No hay «% de adherencia».** Una adherencia es lo hecho frente a lo prescrito, y EMMA no tiene
ninguna pauta prescrita con la que comparar. Se dice con esas palabras en vez de dar una cifra.

LA SEMANA ES UN PARÁMETRO DE DISEÑO
-----------------------------------
`WEEK` solo decide qué lecturas se enseñan junto a la banda. Es diseño EMMA, sin fuente; no
entra en ningún nivel, y por eso no está en la huella de `rules_version`.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.analysis.baseline import Deviation
from app.analysis.trend import TREND_WINDOW, Trend
from app.core import display, i18n
from app.ingest.codes import get
from app.ingest.fhir import ObservationType, VitalObservation

MINUTES = "exercise-minutes"
IMPACTS = "loading-impacts"
# Los dos indicadores de ejercicio del catálogo, en el orden en que se enseñan.
KEYS = (MINUTES, IMPACTS)

# Diseño EMMA, sin fuente (ver cabecera).
WEEK = dt.timedelta(days=7)
WEEK_BASIS = (
    "Última semana de datos: los 7 días anteriores al instante del estado. Ventana de diseño "
    "EMMA, sin fuente; solo decide qué lecturas se enseñan aquí."
)

RELATION = (
    "Lo medido acompaña a la banda; no la modifica. El ejercicio resistivo reduce la pérdida "
    "ósea, pero no hay datos de respuesta con que calcular cuánto: la banda inferida es la "
    "misma con estas lecturas y sin ellas."
)
NO_ADHERENCE = (
    "Sin «% de adherencia»: exige una pauta prescrita con la que comparar y EMMA no tiene "
    "ninguna."
)

RECORDED = "recorded"
RECORDED_ZERO = "recorded_zero"
NO_RECORD = "no_record"
_RECORD_DISPLAY = {
    RECORDED: "hay registro",
    RECORDED_ZERO: "hay registro y es 0",
    NO_RECORD: "no hay registro",
}
_RECORD_NOTE = {
    RECORDED: (
        "Hay registro de ejercicio en la última semana de datos: el ejercicio resistivo reduce "
        "la pérdida, pero su efecto no tiene magnitud citable y la banda no se ajusta."
    ),
    RECORDED_ZERO: (
        "Hay registro de ejercicio en la última semana de datos y es de 0 minutos: la banda "
        "es la de sin contramedidas."
    ),
    NO_RECORD: (
        "Sin registro de ejercicio en la última semana de datos: la banda es la de sin "
        "contramedidas. Que no conste no quiere decir que no lo hubiera."
    ),
}
# El inglés de las frases fijas de arriba (`core/i18n.py`); se resuelve al servir, en `measured`.
i18n.en(
    WEEK_BASIS,
    "Last week of data: the 7 days before the instant of the status. An EMMA design window, "
    "with no source; it only decides which readings are shown here.",
)
i18n.en(
    RELATION,
    "What is measured goes alongside the band; it does not change it. Resistive exercise "
    "reduces bone loss, but there are no response data to work out by how much: the inferred "
    "band is the same with these readings and without them.",
)
i18n.en(
    NO_ADHERENCE,
    "No “% adherence”: it needs a prescribed regimen to compare against, and EMMA has none.",
)
i18n.en_many({
    _RECORD_DISPLAY[RECORDED]: "there is a record",
    _RECORD_DISPLAY[RECORDED_ZERO]: "there is a record and it is 0",
    _RECORD_DISPLAY[NO_RECORD]: "there is no record",
    _RECORD_NOTE[RECORDED]: (
        "There is an exercise record in the last week of data: resistive exercise reduces the "
        "loss, but its effect has no citable magnitude and the band is not adjusted."
    ),
    _RECORD_NOTE[RECORDED_ZERO]: (
        "There is an exercise record in the last week of data and it is 0 minutes: the band is "
        "the one without countermeasures."
    ),
    _RECORD_NOTE[NO_RECORD]: (
        "No exercise record in the last week of data: the band is the one without "
        "countermeasures. That none is on record does not mean there was none."
    ),
})


def _count(value: int) -> str:
    return display.number(value, 0)


def record_state(minutes: Sequence[float]) -> str:
    """Hay registro, no lo hay, o lo hay y es 0: tres afirmaciones distintas."""
    if not minutes:
        return NO_RECORD
    return RECORDED if any(value > 0 for value in minutes) else RECORDED_ZERO


def _baseline(latest: Deviation, unit: str) -> dict[str, Any]:
    """Frente a qué comparó el motor la última lectura: su base propia, o el rango del catálogo."""
    base = latest.baseline
    median = base.quantile(0.5) if base is not None else None
    if base is None or median is None:
        return {
            "personal": False, "median": None, "samples": 0,
            "statement": i18n.tr(
                "Sin línea base propia todavía para esta lectura: el motor la comparó con el "
                "rango de referencia del catálogo.",
                "No baseline of their own yet for this reading: the engine compared it with "
                "the catalogue reference range.",
            ),
        }
    if latest.used_population_range:
        # Hay lecturas anteriores, pero el motor no las dio por suficientes y no las usó: se
        # enseñan como lo que son, sin presentarlas como la referencia de la comparación.
        return {
            "personal": False, "median": round(median, 4), "samples": base.samples,
            "statement": i18n.tr(
                f"Línea base propia aún sin establecer: mediana "
                f"{display.quantity(latest.key, median, unit)} en {_count(base.samples)} "
                f"lecturas anteriores, que el motor no da por suficientes; comparó la lectura "
                f"con el rango de referencia del catálogo.",
                f"Baseline of their own not yet established: median "
                f"{display.quantity(latest.key, median, unit)} over {_count(base.samples)} "
                f"earlier readings, which the engine does not take as enough; it compared the "
                f"reading with the catalogue reference range.",
            ),
        }
    return {
        "personal": True, "median": round(median, 4), "samples": base.samples,
        "statement": i18n.tr(
            f"Línea base propia: mediana {display.quantity(latest.key, median, unit)} en "
            f"{_count(base.samples)} lecturas anteriores.",
            f"Baseline of their own: median {display.quantity(latest.key, median, unit)} over "
            f"{_count(base.samples)} earlier readings.",
        ),
    }


def _indicator(
    key: str,
    readings: Sequence[Deviation],
    contexts: Mapping[str, int],
    trend: Trend | None,
) -> dict[str, Any]:
    code = get(key)
    entry: dict[str, Any] = {
        "key": key,
        "display": code.display,
        "display_es": code.display_es,
        "unit": code.unit,
        "observation_type": str(ObservationType.MEASURED),
        "evidence_context": dict(contexts),
        "readings": len(readings),
        "first": None, "last": None, "latest": None, "lowest": None, "highest": None,
        "outside_expected": None,
        "baseline": None,
        "against_baseline": None,
        # La frase del motor sobre la deriva, tal cual; sin tendencia calculada, se dice.
        "trend": trend.describe() if trend is not None else None,
        "trend_statement": (
            i18n.tr(
                f"Tendencia del motor (hasta {_count(TREND_WINDOW.days)} días): "
                f"{trend.describe()}.",
                f"Engine trend (up to {_count(TREND_WINDOW.days)} days): {trend.describe()}.",
            )
            if trend is not None
            else i18n.tr(
                "Sin tendencia calculada: faltan lecturas para ajustarla.",
                "No trend calculated: there are not enough readings to fit it.",
            )
        ),
    }
    if not readings:
        entry["statement"] = i18n.tr(
            f"{code.display_es}: sin lecturas medidas en la última semana de datos.",
            f"{code.display_es}: no measured readings in the last week of data.",
        )
        return entry
    latest = readings[-1]
    values = [item.value for item in readings]
    outside = sum(1 for item in readings if item.is_concerning)
    entry.update(
        first=readings[0].effective.isoformat(),
        last=latest.effective.isoformat(),
        latest=latest.value, lowest=min(values), highest=max(values),
        outside_expected=outside,
        baseline=_baseline(latest, code.unit),
        # La frase del motor sobre la última lectura, con la base que de verdad usó.
        against_baseline=latest.describe(),
    )
    entry["statement"] = i18n.tr(
        f"{code.display_es}: {_count(len(readings))} lecturas medidas en la última semana de "
        f"datos, entre {display.quantity(key, min(values), code.unit)} y "
        f"{display.quantity(key, max(values), code.unit)}; la última, "
        f"{display.quantity(key, latest.value, code.unit)}. Fuera de lo esperado según el "
        f"motor: {_count(outside)} de {_count(len(readings))}.",
        f"{code.display_es}: {_count(len(readings))} measured "
        f"{'reading' if len(readings) == 1 else 'readings'} in the last week of data, between "
        f"{display.quantity(key, min(values), code.unit)} and "
        f"{display.quantity(key, max(values), code.unit)}; the latest, "
        f"{display.quantity(key, latest.value, code.unit)}. Outside what is expected according "
        f"to the engine: {_count(outside)} of {_count(len(readings))}.",
    )
    return entry


def measured(
    observations: Iterable[VitalObservation],
    deviations: Iterable[Deviation],
    trends: Mapping[str, Trend],
    reference: dt.datetime,
) -> dict[str, Any]:
    """Minutos de ejercicio e impactos de carga de la última semana, como los vio el motor.

    `deviations` son las lecturas ya evaluadas contra su línea base y `trends` las tendencias:
    las mismas que usa el estado. `observations` solo dice qué lecturas son medidas y de qué
    entorno; una que no sea medida no se cuenta aquí, porque este bloque va rotulado MEDIDO.
    """
    start = reference - WEEK
    kept: dict[str, set[dt.datetime]] = {key: set() for key in KEYS}
    contexts: dict[str, Counter[str]] = {key: Counter() for key in KEYS}
    not_measured = 0
    for obs in observations:
        if obs.key not in kept or not start <= obs.effective <= reference:
            continue
        if obs.observation_type is not ObservationType.MEASURED:
            not_measured += 1
            continue
        kept[obs.key].add(obs.effective)
        contexts[obs.key][str(obs.evidence)] += 1
    week: dict[str, list[Deviation]] = {key: [] for key in KEYS}
    for item in deviations:
        if item.key in week and item.effective in kept[item.key]:
            week[item.key].append(item)
    for readings in week.values():
        readings.sort(key=lambda item: item.effective)

    state = record_state([item.value for item in week[MINUTES]])
    return {
        "observation_type": str(ObservationType.MEASURED),
        "window_days": WEEK.days,
        "window_start": start.isoformat(),
        "window_end": reference.isoformat(),
        "window_basis": i18n.loc(WEEK_BASIS),
        "indicators": [
            _indicator(key, week[key], contexts[key], trends.get(key)) for key in KEYS
        ],
        "record": {
            "state": state,
            "display": i18n.loc(_RECORD_DISPLAY[state]),
            "note": i18n.loc(_RECORD_NOTE[state]),
        },
        "not_measured_excluded": not_measured,
        "relation": i18n.loc(RELATION),
        "adherence": None,
        "adherence_note": i18n.loc(NO_ADHERENCE),
    }


# Encabezado de cada elemento del contexto de una alerta: lo que se lista es lo registrado.
HEADING = "Ejercicio registrado"
i18n.en(HEADING, "Exercise on record")


def in_window(
    observations: Iterable[VitalObservation], start: dt.datetime, end: dt.datetime
) -> list[dict[str, Any]]:
    """Lo registrado de cada indicador de ejercicio dentro de una ventana, sin juzgarlo.

    Para el contexto de una alerta (`alert_context`): un elemento por indicador con lecturas,
    con cuántas son, entre qué instantes y entre qué valores. Solo cuenta lo que hay.
    """
    return recorded_in_window(observations, start, end, KEYS, HEADING)


def recorded_in_window(
    observations: Iterable[VitalObservation], start: dt.datetime, end: dt.datetime,
    keys: Sequence[str], heading: str,
) -> list[dict[str, Any]]:
    """Lo registrado de unos indicadores del catálogo dentro de una ventana, sin juzgarlo.

    La forma de `in_window` para cualquier lista de claves: el contexto de una alerta la usa
    también para la ingesta de líquidos, la dieta y el sueño (`alert_context.RECORDED_SOURCES`),
    que se listan igual que el ejercicio —un elemento por indicador con lecturas, con cuántas
    son, entre qué instantes y entre qué valores— y, como él, sin decir si es poco o mucho.
    """
    found: dict[str, list[VitalObservation]] = {key: [] for key in keys}
    for obs in observations:
        if obs.key in found and start <= obs.effective <= end:
            found[obs.key].append(obs)
    result = []
    for key in keys:
        readings = sorted(found[key], key=lambda obs: obs.effective)
        if not readings:
            continue
        code = get(key)
        values = [obs.value for obs in readings]
        low = display.quantity(key, min(values), code.unit)
        high = display.quantity(key, max(values), code.unit)
        said = low if low == high else i18n.tr(f"entre {low} y {high}", f"between {low} and {high}")
        result.append({
            "key": key,
            "display": code.display,
            "display_es": code.display_es,
            "start": readings[0].effective,
            "end": readings[-1].effective,
            "readings": len(readings),
            # `heading` llega en castellano de quien llama (`HEADING`, o los de `alert_context`):
            # su inglés lo registra su dueño y aquí, donde se sirve, se resuelve.
            "title": i18n.tr(
                f"{heading} — {code.display_es}: {_count(len(readings))} "
                f"{'lectura' if len(readings) == 1 else 'lecturas'}, {said}",
                f"{i18n.loc(heading)} — {code.display_es}: {_count(len(readings))} "
                f"{'reading' if len(readings) == 1 else 'readings'}, {said}",
            ),
            "sources": sorted({obs.source for obs in readings}),
        })
    return result
