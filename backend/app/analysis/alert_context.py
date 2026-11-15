"""Que cambio alrededor de una alerta, y cuantas senales de su dominio la acompanan.

La especificacion del equipo pide tres cosas que el detalle de una alerta no tenia: en el modelo
de dominio (§3), `Alert.context_correlations`; entre las preguntas del detalle (§10), "¿que
contexto ha cambiado?"; y en el motor (§6), la "concordancia entre senales". Hasta ahora esa
pregunta la respondia la interfaz con lo que tenia a mano —dia de mision, fase y un "el habitat,
en otro panel"— y las EVA y los bloques de trabajo que la tripulacion declara no los leia ningun
modulo de analisis. Quien abria una alerta de fatiga no veia que el CO2 llevaba horas fuera de
limite ni que la vispera hubo una EVA.

LO QUE ES Y LO QUE NO ES
------------------------
Es una capa **descriptiva**, por encima del motor y sin camino de vuelta hacia el. Lee lo que el
motor ya calculo (desviaciones y tendencias) y la regla con que decide que es un hallazgo
(`risk.representative_deviation`); no llama a `RiskEngine` ni a `BaselineEngine`, ninguno de los
dos lo importa, y hay una prueba de que los niveles de un escenario son identicos con y sin esta
capa (invariante 5).

Cada elemento de contexto va rotulado `correlación temporal, no causa`. Que una EVA solape con
el inicio de una alerta dice cuando ocurrieron las dos cosas, y nada mas.

Lo que no se tiene se dice: cada fuente declara si habia dato en la ventana. "Sin excursiones"
con el sensor callado y "sin excursiones" con el sensor midiendo son afirmaciones distintas, y
"ningun evento solar" no se puede decir de unos dias que la cache de DONKI no cubre.

LA VENTANA ES UN PARAMETRO DE DISENO
------------------------------------
No hay una cifra citable de cuanto antes de un cambio fisiologico hay que mirar el contexto:
dependeria del mecanismo, y aqui caben varios (la atmosfera de cabina, una EVA, un cambio de
fase). Se declara como diseno EMMA, sin fuente y sin ajustar con datos (`WINDOW_BASIS`).

LA CONCORDANCIA NO INVENTA UN CRITERIO
--------------------------------------
"Se desvia" es lo que el motor ya entiende por hallazgo: la lectura representativa (con su
persistencia) o una deriva que el propio `Trend` da por preocupante. El sentido "coherente" es
el que el catalogo declara como preocupante para cada indicador (`VitalCode.concerning`): menos
horas de sueno y mas tiempo de reaccion van en el mismo sentido aunque una cifra baje y la otra
suba. El catalogo no dice como se acoplan dos indicadores entre si, y aqui no se inventa: de
uno que preocupa en los dos sentidos se da su descripcion, con el sentido en que va.

"En contra" solo se juzga por deriva, con las mismas condiciones que `Trend.is_concerning` y el
sentido opuesto. Para una lectura suelta del lado que no preocupa el motor no tiene criterio.

LA UBICACION DECLARADA SE LEE, NO SE LISTA
------------------------------------------
Desde que un tripulante puede declarar en que modulo esta (`mission-event` de tipo `location`),
esa declaracion llega aqui con el resto de eventos. No es un evento del plan de mision: no se
lista junto a las EVA. Sirve para leer cada excursion del habitat: de la excursion se dice si,
segun lo declarado, el tripulante estaba en ese modulo, con la misma regla que ordena las
hipotesis de la vista de tripulacion (`context.presence`). Sin ninguna ubicacion declarada se
mantiene, y se dice, el supuesto de habitat compartido. Sigue siendo texto: no mueve nada.

EL ESTADO DE UN SISTEMA SE DECLARA, NO SE MIDE
----------------------------------------------
EMMA no lee el estado de ningun sistema del habitat. Lo que una persona declara en la consola
(`system-status`, `environment/systems.py`) es una fuente mas, con el mismo esquema y el mismo
rotulo que las demas, y dice de si misma que es una declaracion y no telemetria. Sin ninguna
declaracion la fuente no tiene dato: no se sabe, que no es «todo funcionaba».

UN CAMBIO DE TURNO SE LISTA COMO UNA EVA
----------------------------------------
Desde la decimoctava ronda (U4) un cambio de turno o de horario de sueño declarado (`shift`,
`core/shift.py`) entra con los demas eventos de mision: mismo rotulo, misma ventana, sin umbral de
horas propio. Se lista en la alerta de cualquier dominio, como una EVA, porque esta capa no filtra
fuentes por dominio; la nota de la fuente dice lo que la fuente leida cuenta de ellos (el sueno y
el ritmo circadiano) y lo que no. No mueve ningun nivel ni entra en `rules_version`.

LA INGESTA Y EL SUENO SE LISTAN, NO SE JUZGAN
---------------------------------------------
Desde la decimonovena ronda (U12) la ingesta de liquidos, la dieta (energia y apetito) y el sueno
del propio tripulante son tres fuentes mas (`RECORDED_SOURCES`), como el ejercicio: la base de
conocimiento pide «conectar dieta con ejercicio, hidratacion, metabolismo» (§5) y la
especificacion pone la ingesta de liquidos junto al ejercicio en el escenario de hidratacion (§9),
y hasta ahora ninguna de las dos entraba en la alerta de otro dominio. Cada fuente dice que hubo
—cuantas lecturas medidas, entre que instantes y entre que valores— y si tenia dato; **no dice si
fue poco o mucho**: no tiene umbral propio, y si un indicador se desvia lo juzga el estado en su
dominio con su linea base. Se listan en la alerta de cualquier dominio, porque esta capa no
filtra fuentes por dominio; en una alerta conductual el sueno sale ademas en la concordancia, que
responde a otra pregunta (si se desvia, no si consta). Solo lecturas medidas, las mismas que
analiza el estado (`routes.state_reference`). El mecanismo es el del ejercicio, que ya se listaba
asi: la misma forma de contar lo registrado (`exercise_summary.recorded_in_window`) y la misma de
decir si la fuente tenia dato (`_listed`). Las claves del ejercicio siguen en `exercise_summary`
porque tambien se ensenan junto a la banda osea; estas tres no tienen otro lector y viven aqui.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from app.advisor import countermeasures
from app.analysis.baseline import Deviation
from app.analysis.context import (
    ASSUMPTION,
    ASSUMPTION_ESTIMATED_LOCATED,
    ASSUMPTION_LOCATED,
    ELSEWHERE,
    NOT_COMPARABLE,
    PRESENT,
    UNDECLARED,
    Stay,
    correlate,
    estimated_location,
    presence,
)
from app.analysis.exercise_summary import HEADING as EXERCISE_HEADING
from app.analysis.exercise_summary import KEYS as EXERCISE_KEYS
from app.analysis.exercise_summary import in_window as exercise_in_window
from app.analysis.exercise_summary import recorded_in_window
from app.analysis.risk import representative_deviation
from app.analysis.trend import Direction, Trend
from app.core import display, i18n
from app.core import shift as shift_event
from app.core.mission import ADAPTATION_DAYS, RETURN_DAYS, phase_at
from app.core.mission import context as mission_context
from app.environment import systems as habitat_systems
from app.environment.donki import FRESH_FOR, SolarEvent
from app.environment.habitat import (
    MODULES,
    PARAMETERS,
    Excursion,
    HabitatReading,
    cabin_readings,
    module_display,
)
from app.ingest.codes import Domain, ReferenceBasis, VitalCode, evaluated_by_domain, get
from app.ingest.fhir import VitalObservation

LABEL = "correlación temporal, no causa"
i18n.en(LABEL, "temporal correlation, not cause")

# Diseno EMMA, sin fuente (ver cabecera).
WINDOW_BEFORE = dt.timedelta(hours=24)
WINDOW_AFTER = dt.timedelta(hours=6)
WINDOW_BASIS = (
    "Ventana de diseño EMMA, sin fuente y sin ajustar con datos: 24 h antes del inicio (un "
    "ciclo completo de sueño, trabajo y ejercicio) y 6 h después (los límites del hábitat se "
    "juzgan con medias y los eventos se declaran a mano: sus instantes no son exactos). Lo "
    "posterior al instante del estado no se mira."
)
NOTE = (
    "Coincidir en el tiempo con el inicio de una alerta no dice que sea su causa. Esta lista "
    "no cambia el nivel de la alerta."
)
# El mismo contexto pedido sin alerta (el modo anatómico, de una región que no la tiene): no hay
# inicio al que anclarlo ni alerta cuyo nivel no cambie, y la nota no puede hablar de una.
NOTE_WITHOUT_ALERT = (
    "Coincidir en el tiempo con el instante del estado no dice que sea causa de nada. Esta "
    "lista no cambia ningún nivel."
)
i18n.en_many({
    WINDOW_BASIS: (
        "EMMA design window, with no source and not tuned with data: 24 h before the onset (a "
        "full cycle of sleep, work and exercise) and 6 h after (habitat limits are judged with "
        "averages and events are declared by hand: their times are not exact). Nothing after "
        "the time of the state is looked at."
    ),
    NOTE: (
        "Coinciding in time with the onset of an alert does not say it is its cause. This list "
        "does not change the level of the alert."
    ),
    NOTE_WITHOUT_ALERT: (
        "Coinciding in time with the time of the state does not say it is the cause of "
        "anything. This list does not change any level."
    ),
})

WITH_DATA = "with_data"
PARTIAL = "partial"
NO_DATA = "no_data"
_STATUS_DISPLAY = {WITH_DATA: "con dato", PARTIAL: "dato parcial", NO_DATA: "sin dato"}
# Palabras sueltas: su inglés va en una tabla paralela y no en el registro común de `i18n`,
# donde otra unidad podría dar a «sin dato» otro inglés.
_STATUS_DISPLAY_EN = {WITH_DATA: "with data", PARTIAL: "partial data", NO_DATA: "no data"}

_EVENT_KIND_DISPLAY = {
    "eva": "EVA declarada",
    "workload": "Bloque de trabajo declarado",
    shift_event.KIND: f"{shift_event.DISPLAY} declarado",
}
_UNKNOWN_EVENT_KIND = "Evento de misión declarado"
i18n.en_many({
    _EVENT_KIND_DISPLAY["eva"]: "Declared EVA",
    _EVENT_KIND_DISPLAY["workload"]: "Declared work block",
    _EVENT_KIND_DISPLAY[shift_event.KIND]: "Declared shift or sleep-schedule change",
    _UNKNOWN_EVENT_KIND: "Declared mission event",
})
# Una ubicacion declarada no es un evento del plan: dice donde estaba el tripulante y se usa
# para leer las excursiones del habitat (ver cabecera). No se lista.
_LOCATION_KIND = "location"
_PRESENCE_DISPLAY = {
    PRESENT: (
        "Según la ubicación declarada, el tripulante estaba en {module} durante la excursión."
    ),
    ELSEWHERE: (
        "Según la ubicación declarada, el tripulante no estaba en {module} durante la "
        "excursión. La ubicación la declara una persona, no se mide."
    ),
    UNDECLARED: (
        "Sin ubicación declarada en todo el tramo de la excursión: se le supone en el hábitat "
        "compartido."
    ),
}
# Las mismas frases cuando la ubicacion que las decide la estimaron las anclas de modulo: no la
# declaro nadie y no se dice que la declarara una persona.
_ESTIMATED_PRESENCE_DISPLAY = {
    PRESENT: (
        "Según la ubicación declarada o estimada por las anclas de módulo, el tripulante estaba "
        "en {module} durante la excursión."
    ),
    ELSEWHERE: (
        "Según la ubicación declarada o estimada por las anclas de módulo, el tripulante no "
        "estaba en {module} durante la excursión. Las anclas la estiman por la señal más fuerte, "
        "solo el módulo y sin validar dentro de un módulo metálico."
    ),
    UNDECLARED: _PRESENCE_DISPLAY[UNDECLARED],
}
i18n.en_many({
    _PRESENCE_DISPLAY[PRESENT]: (
        "According to the declared location, the crew member was in {module} during the "
        "excursion."
    ),
    _PRESENCE_DISPLAY[ELSEWHERE]: (
        "According to the declared location, the crew member was not in {module} during the "
        "excursion. The location is declared by a person; it is not measured."
    ),
    _PRESENCE_DISPLAY[UNDECLARED]: (
        "No declared location for the whole span of the excursion: the crew member is assumed "
        "to be in the shared habitat."
    ),
    _ESTIMATED_PRESENCE_DISPLAY[PRESENT]: (
        "According to the location declared or estimated by the module anchors, the crew "
        "member was in {module} during the excursion."
    ),
    _ESTIMATED_PRESENCE_DISPLAY[ELSEWHERE]: (
        "According to the location declared or estimated by the module anchors, the crew "
        "member was not in {module} during the excursion. The anchors estimate it from the "
        "strongest signal, the module only, and this has not been checked inside a metal "
        "module."
    ),
})

Window = tuple[dt.datetime, dt.datetime]


@dataclass(frozen=True, slots=True)
class SolarRecord:
    """Lo que el estado sabe de eventos solares, y de que intervalo lo sabe.

    Fuera de `known_from`..`known_until` no se puede decir "ningun evento": solo "sin dato".
    """

    events: Sequence[SolarEvent]
    known_from: dt.datetime
    known_until: dt.datetime


@dataclass(frozen=True, slots=True)
class _Anchor:
    """El instante al que se ancla la ventana, y como se nombra en una frase."""

    moment: dt.datetime
    name: str  # "el inicio de la alerta"
    of: str  # "del inicio de la alerta"
    heading: str  # "Inicio de la alerta"
    basis: str


@dataclass(frozen=True, slots=True)
class _Verbs:
    """Como se dice que algo empezo, termino o seguia, segun lo que de verdad se sabe de ello."""

    began: str
    ended: str
    ongoing: str


_DECLARED = _Verbs("empezó", "terminó", "en curso")
# De una excursion solo se conocen sus lecturas: la ultima fuera de limite no es su final.
_MEASURED = _Verbs(
    "primera lectura fuera de límite", "última lectura fuera de límite", "fuera de límite"
)
# De una serie de lecturas solo se conocen la primera y la ultima de la ventana.
_READINGS = _Verbs("primera lectura", "última lectura", "con lecturas")
# Los mismos verbos en inglés: son fragmentos de la frase de `_timing`, no constantes servidas.
_VERBS_EN = {
    _DECLARED: _Verbs("began", "ended", "ongoing"),
    _MEASURED: _Verbs(
        "first reading outside the limit", "last reading outside the limit", "outside the limit"
    ),
    _READINGS: _Verbs("first reading", "last reading", "with readings"),
}


def _anchor_en(onset: dt.datetime | None, reference: dt.datetime, alert: bool) -> _Anchor:
    """El ancla de `_anchor`, nombrada en inglés: misma regla, mismas tres ramas."""
    if alert and onset is not None:
        return _Anchor(
            onset, "the alert onset", "the alert onset", "Alert onset",
            "alert onset: first reading outside the expected range",
        )
    basis = (
        "no reading outside the expected range: the time of the state is taken" if alert
        else "no alert: the time of the state is taken"
    )
    return _Anchor(
        reference, "the time of the state", "the time of the state", "Time of the state", basis
    )


def _anchor(onset: dt.datetime | None, reference: dt.datetime, alert: bool = True) -> _Anchor:
    if i18n.current() == "en":
        return _anchor_en(onset, reference, alert)
    if not alert:
        return _Anchor(
            reference, "el instante del estado", "del instante del estado", "Instante del estado",
            "sin alerta: se toma el instante del estado",
        )
    if onset is not None:
        return _Anchor(
            onset, "el inicio de la alerta", "del inicio de la alerta", "Inicio de la alerta",
            "inicio de la alerta: primera lectura fuera de lo esperado",
        )
    return _Anchor(
        reference, "el instante del estado", "del instante del estado", "Instante del estado",
        "sin lectura fuera de lo esperado: se toma el instante del estado",
    )


def _overlaps(start: dt.datetime, end: dt.datetime, window: Window) -> bool:
    """Un intervalo toca la ventana. Un instante es un intervalo de longitud cero."""
    return end >= window[0] and start <= window[1]


def _hours(delta: dt.timedelta) -> str:
    return f"{display.number(abs(delta.total_seconds()) / 3600, 1)} h"


def _count(value: int) -> str:
    return display.number(value, 0)


def _timing(start: dt.datetime, end: dt.datetime, anchor: _Anchor, verbs: _Verbs) -> str:
    """Donde cae el elemento respecto al ancla: una relacion de tiempo, no de causa."""
    moment = anchor.moment
    instant = start == end
    if i18n.current() == "en":
        # En inglés la frase se ordena de otro modo: se redacta entera, no fragmento a fragmento.
        said = _VERBS_EN[verbs]
        if end < moment:
            ended = "" if instant else f"{said.ended} "
            return f"{ended}{_hours(moment - end)} before {anchor.name}"
        if start > moment:
            began = "" if instant else f"{said.began} "
            return f"{began}{_hours(start - moment)} after {anchor.name}"
        if instant:
            return f"at the same time as {anchor.name}"
        if start == moment:
            return f"{said.began} at the same time as {anchor.name}"
        return f"{said.ongoing} at {anchor.name}; {said.began} {_hours(moment - start)} earlier"
    if end < moment:
        return f"{'' if instant else verbs.ended + ' '}{_hours(moment - end)} antes {anchor.of}"
    if start > moment:
        return f"{'' if instant else verbs.began + ' '}{_hours(start - moment)} después {anchor.of}"
    if instant:
        return f"a la vez que {anchor.name}"
    if start == moment:
        return f"{verbs.began} a la vez que {anchor.name}"
    return f"{verbs.ongoing} en {anchor.name}; {verbs.began} {_hours(moment - start)} antes"


def _item(
    *,
    kind: str,
    title: str,
    start: dt.datetime,
    end: dt.datetime,
    anchor: _Anchor,
    source: str,
    verbs: _Verbs = _DECLARED,
    detail: str | None = None,
    value: float | None = None,
    value_label: str | None = None,
    unit: str | None = None,
    presence: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": i18n.loc(LABEL),
        "title": title,
        # Texto declarado por una persona o por la biblioteca, no redactado aqui. La excepcion
        # es una excursion del habitat con ubicacion declarada: ahi es la frase de presencia.
        "detail": detail,
        # Solo en una excursion del habitat, y solo si el tripulante ha declarado ubicacion.
        "presence": presence,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "timing": _timing(start, end, anchor, verbs),
        "source": source,
        "value": value,
        "value_label": value_label,
        "unit": unit,
    }


def _source(
    kind: str, name: str, status: str, found: int, note: str, en: str | None = None
) -> dict[str, Any]:
    """`en` es la nota en inglés cuando se redacta con cifras; sin él, la nota es una constante
    registrada (o de otro módulo) y se resuelve con `loc`."""
    return {
        "kind": kind,
        "display": i18n.loc(name),
        "status": status,
        "status_display": i18n.tr(_STATUS_DISPLAY[status], _STATUS_DISPLAY_EN[status]),
        "found": found,
        "note": i18n.loc(note) if en is None else i18n.tr(note, en),
    }


Found = tuple[list[dict[str, Any]], dict[str, Any]]

# Cómo se nombra cada fuente, en inglés. Los nombres castellanos se quedan donde se usan y
# `_source` los resuelve al servir.
i18n.en_many({
    "Hábitat": "Habitat",
    "Eventos de misión": "Mission events",
    "Fase de misión": "Mission phase",
    "Evento solar": "Solar event",
    "Contramedidas": "Countermeasures",
    "Sistemas del hábitat": "Habitat systems",
})


def _where(stays: Sequence[Stay], item: dict[str, Any], window: Window) -> tuple[str, str]:
    """Donde estaba el tripulante durante una excursion, segun lo declarado, y como se dice."""
    # Solo el tramo de la excursion que cae en la ventana, como en la vista de tripulacion.
    start = max(dt.datetime.fromisoformat(item["start"]), window[0])
    end = min(dt.datetime.fromisoformat(item["end"]), window[1])
    where = presence(stays, item["module"], start, end)
    if item["module"] not in MODULES:
        return where, i18n.loc(NOT_COMPARABLE)
    said = (
        _ESTIMATED_PRESENCE_DISPLAY if estimated_location(stays, start, end)
        else _PRESENCE_DISPLAY
    )
    return where, i18n.loc(said[where]).format(module=i18n.loc(module_display(item["module"])))


def _habitat(
    readings: Sequence[HabitatReading], excursions: Sequence[Excursion],
    window: Window, anchor: _Anchor, stays: Sequence[Stay] = (),
) -> Found:
    # Que excursiones cuentan lo decide `context.correlate`, con su regla (solo limite normativo
    # y que toquen la ventana). Sin tripulantes no propone hipotesis: solo devuelve esas.
    relevant = correlate({}, excursions, window[1], window[1] - window[0])["habitat_excursions"]
    # Solo la cabina (`cabin_readings`): una muestra de agua o un recuento microbiano no dicen
    # que la atmosfera se vigilara, y no convierten «sin lecturas» en «en parte».
    measured = {
        item.parameter for item in cabin_readings(readings)
        if _overlaps(item.effective, item.effective, window)
    } | {item["parameter"] for item in relevant}
    missing = [
        i18n.loc(spec.display) for key, spec in PARAMETERS.items() if key not in measured
    ]
    # Con alguna ubicacion declarada, de cada excursion se dice donde estaba el tripulante.
    located = bool(stays)
    items = []
    for item in relevant:
        where, said = _where(stays, item, window) if located else (None, None)
        name = i18n.loc(item["display"])
        items.append(_item(
            kind="habitat",
            title=i18n.tr(
                f"{name} fuera de su límite normativo ({item['requirement']})",
                f"{name} outside its normative limit ({item['requirement']})",
            ),
            start=dt.datetime.fromisoformat(item["start"]),
            end=dt.datetime.fromisoformat(item["end"]),
            anchor=anchor, verbs=_MEASURED,
            source=i18n.tr(
                f"telemetría de cabina, módulo {item['module']}",
                f"cabin telemetry, module {item['module']}",
            ),
            value=item["worst"],
            value_label=i18n.tr("valor más alejado del límite", "value furthest from the limit"),
            unit=item["unit"],
            detail=said, presence=where,
        ))
    assumption = i18n.loc(
        ASSUMPTION if not located
        else ASSUMPTION_ESTIMATED_LOCATED if estimated_location(stays, *window)
        else ASSUMPTION_LOCATED
    )
    if not measured:
        return items, _source(
            "habitat", "Hábitat", NO_DATA, 0,
            "Sin lecturas de hábitat en la ventana: no se sabe si cambió.",
            en="No habitat readings in the window: it is not known whether it changed.",
        )
    scope = i18n.tr(
        "Solo cuentan los límites normativos de NASA-STD-3001; la zona de confort, no.",
        "Only the normative limits of NASA-STD-3001 count; the comfort zone does not.",
    )
    if missing:
        return items, _source(
            "habitat", "Hábitat", PARTIAL, len(items),
            f"Sin lectura en la ventana: {', '.join(missing)}. {scope} {assumption}",
            en=f"No reading in the window: {', '.join(missing)}. {scope} {assumption}",
        )
    return items, _source("habitat", "Hábitat", WITH_DATA, len(items), f"{scope} {assumption}")


def _mission_events(events: Sequence[dict[str, Any]], window: Window, anchor: _Anchor) -> Found:
    items = []
    listed = [event for event in events if event["kind"] != _LOCATION_KIND]
    shifted = False
    for event in listed:
        start = dt.datetime.fromisoformat(event["start"])
        end = dt.datetime.fromisoformat(event["end"])
        if _overlaps(start, end, window):
            shifted = shifted or event["kind"] == shift_event.KIND
            items.append(_item(
                kind="mission_event",
                title=i18n.loc(_EVENT_KIND_DISPLAY.get(event["kind"], _UNKNOWN_EVENT_KIND)),
                detail=event["label"], start=start, end=end, anchor=anchor,
                source=i18n.tr(
                    f"declarado por {event['declared_by']}, asiento {event['ledger_index']}",
                    f"declared by {event['declared_by']}, ledger entry {event['ledger_index']}",
                ),
            ))
    if not listed:
        return items, _source(
            "mission_event", "Eventos de misión", NO_DATA, 0,
            "No hay ninguna EVA, bloque de trabajo ni cambio de turno declarado: que no conste "
            "no quiere decir que no lo hubiera.",
            en=(
                "No EVA, work block or shift change has been declared: that none is on record "
                "does not mean there was none."
            ),
        )
    scope = "Solo las EVA, los bloques de trabajo y los cambios de turno declarados en la consola."
    scope_en = "Only the EVAs, work blocks and shift changes declared in the console."
    # Con un cambio de turno en la ventana, lo que dice de ellos la fuente leida y lo que no:
    # coincidir con la alerta no es su causa (`core/shift.py`).
    return items, _source(
        "mission_event", "Eventos de misión", WITH_DATA, len(items),
        f"{scope} {shift_event.SOURCE_SAYS}" if shifted else scope,
        en=f"{scope_en} {i18n.loc(shift_event.SOURCE_SAYS)}" if shifted else scope_en,
    )


def _phase_changes(
    start: dt.date, duration_days: int, window: Window, anchor: _Anchor
) -> Found:
    origin = dt.datetime.combine(start, dt.time(0, 0, tzinfo=dt.UTC))
    days = sorted({0, ADAPTATION_DAYS, duration_days - RETURN_DAYS, duration_days})
    items = []
    for boundary in (origin + dt.timedelta(days=day) for day in days):
        if not _overlaps(boundary, boundary, window):
            continue
        before = phase_at(boundary - dt.timedelta(seconds=1), start, duration_days)
        after = phase_at(boundary, start, duration_days)
        # Con una mision muy corta dos limites caen en la misma fase: ahi no cambia nada.
        if before is not after:
            items.append(_item(
                kind="phase_change",
                title=i18n.tr(
                    f"Cambio de fase de misión: de {before.display} a {after.display}",
                    f"Mission phase change: from {i18n.loc(before.display)} to "
                    f"{i18n.loc(after.display)}",
                ),
                start=boundary, end=boundary, anchor=anchor,
                source=i18n.tr(
                    "calendario de misión; los límites de fase son diseño EMMA, sin fuente",
                    "mission calendar; the phase boundaries are EMMA design, with no source",
                ),
            ))
    return items, _source(
        "phase_change", "Fase de misión", WITH_DATA, len(items),
        "La fase se calcula del calendario y no cambia el análisis.",
        en="The phase is computed from the calendar and does not change the analysis.",
    )


def _solar(record: SolarRecord | None, window: Window, anchor: _Anchor) -> Found:
    if record is None:
        return [], _source(
            "solar_event", "Evento solar", NO_DATA, 0,
            "Sin datos de NASA DONKI: no se sabe si hubo un evento solar.",
            en="No NASA DONKI data: it is not known whether there was a solar event.",
        )
    # Un dato de DONKI tan reciente como el que su cliente da por actual llega hasta ahora.
    known: Window = (record.known_from, record.known_until + FRESH_FOR)
    # Con una cache mas vieja que lo que el estado guarda, el intervalo conocido esta vacio.
    if known[1] < known[0] or not _overlaps(known[0], known[1], window):
        return [], _source(
            "solar_event", "Evento solar", NO_DATA, 0,
            "Los datos de NASA DONKI que tiene el estado no cubren la ventana: no se sabe si "
            "hubo un evento solar en ella.",
            en=(
                "The NASA DONKI data held by the state do not cover the window: it is not "
                "known whether there was a solar event in it."
            ),
        )
    items = [
        _item(
            kind="solar_event",
            title=i18n.tr(
                f"Evento solar {event.event_type}", f"Solar event {event.event_type}"
            ),
            detail=event.event_id, start=event.time, end=event.time, anchor=anchor,
            source="NASA DONKI",
        )
        for event in record.events
        if _overlaps(event.time, event.time, window)
    ]
    if known[0] <= window[0] and known[1] >= window[1]:
        return items, _source(
            "solar_event", "Evento solar", WITH_DATA, len(items),
            "Eventos de partículas solares registrados en NASA DONKI.",
            en="Solar particle events recorded in NASA DONKI.",
        )
    return items, _source(
        "solar_event", "Evento solar", PARTIAL, len(items),
        "Los datos de NASA DONKI que tiene el estado cubren solo una parte de la ventana.",
        en="The NASA DONKI data held by the state cover only part of the window.",
    )


def _countermeasures(
    adoptions: Sequence[dict[str, Any]], window: Window, anchor: _Anchor
) -> Found:
    items = []
    for adoption in adoptions:
        moment = dt.datetime.fromisoformat(adoption["reference_time"])
        if not _overlaps(moment, moment, window):
            continue
        try:
            action: str = countermeasures.get(adoption["countermeasure_id"]).action
        except KeyError:
            # Una adopcion firmada no se esconde porque su ficha ya no este en la biblioteca.
            action = str(adoption["countermeasure_id"])
        items.append(_item(
            kind="countermeasure",
            title=i18n.tr("Contramedida adoptada", "Countermeasure adopted"), detail=action,
            start=moment, end=moment, anchor=anchor,
            source=i18n.tr(
                f"decisión de {adoption['decided_by']}, asiento {adoption['ledger_index']}",
                f"decision by {adoption['decided_by']}, ledger entry {adoption['ledger_index']}",
            ),
        ))
    return items, _source(
        "countermeasure", "Contramedidas", WITH_DATA, len(items),
        "Solo las adoptadas en la consola, de cualquier dominio.",
        en="Only those adopted in the console, from any domain.",
    )


@dataclass(frozen=True, slots=True)
class RecordedSource:
    """Una fuente que lista lo registrado de unos indicadores del catalogo, sin juzgarlo.

    `heading` encabeza cada elemento («Sueño registrado — Duración del sueño: …»); `scope` dice
    lo que la fuente cuenta y lo que no, y `no_data` lo que se dice cuando no hay ninguna lectura
    en la ventana. Ninguna lleva umbral: esta capa no decide (ver cabecera).
    """

    kind: str
    display: str
    keys: tuple[str, ...]
    heading: str
    scope: str
    no_data: str


def _listed(
    spec: RecordedSource, recorded: Sequence[dict[str, Any]], anchor: _Anchor
) -> Found:
    """Lo que una fuente dice de lo registrado en la ventana: sus elementos y si tenia dato.

    `recorded` es lo que da `exercise_summary.recorded_in_window` (o `in_window`): un registro
    por indicador con lecturas. Sin ninguno, la fuente no tiene dato; con alguno de sus
    indicadores sin lectura, el dato es parcial y se nombra el que falta.
    """
    items = [
        _item(
            kind=spec.kind, title=found["title"], start=found["start"], end=found["end"],
            anchor=anchor, verbs=_READINGS,
            source=i18n.tr(
                f"lecturas de {', '.join(found['sources'])}",
                f"readings from {', '.join(found['sources'])}",
            ),
        )
        for found in recorded
    ]
    if not items:
        return items, _source(spec.kind, spec.display, NO_DATA, 0, spec.no_data)
    listed = {found["key"] for found in recorded}
    missing = [get(key).display_es for key in spec.keys if key not in listed]
    if missing:
        return items, _source(
            spec.kind, spec.display, PARTIAL, len(items),
            f"Sin lectura en la ventana: {', '.join(missing)}. {spec.scope}",
            en=f"No reading in the window: {', '.join(missing)}. {i18n.loc(spec.scope)}",
        )
    return items, _source(spec.kind, spec.display, WITH_DATA, len(items), spec.scope)


_EXERCISE = RecordedSource(
    "exercise", "Ejercicio", EXERCISE_KEYS, EXERCISE_HEADING,
    "Minutos de ejercicio e impactos de carga registrados; sin pauta prescrita con la que "
    "compararlos.",
    "Sin lecturas de ejercicio en la ventana: que no conste no quiere decir que no lo hubiera.",
)


def _exercise(
    observations: Sequence[VitalObservation], window: Window, anchor: _Anchor
) -> Found:
    """El ejercicio registrado en la ventana: cuanto consta, sin decir si es mucho o poco.

    Vale para una alerta de cualquier dominio (la especificacion §9 lo pone en el escenario de
    hidratacion y en el musculoesqueletico). No hay pauta prescrita con la que compararlo.
    """
    recorded = exercise_in_window(observations, window[0], window[1])
    return _listed(_EXERCISE, recorded, anchor)


_NOT_RECORDED = "que no conste no quiere decir que no la hubiera."
RECORDED_SOURCES: tuple[RecordedSource, ...] = (
    RecordedSource(
        "fluid_intake", "Ingesta de líquidos", ("fluid-intake-24h",),
        "Ingesta de líquidos registrada",
        "Totales de 24 h registrados. Sin umbral propio: esta lista no dice si fue poca o mucha.",
        f"Sin lecturas de ingesta de líquidos en la ventana: {_NOT_RECORDED}",
    ),
    RecordedSource(
        "diet", "Dieta", ("energy-intake-daily", "appetite-rating"), "Dieta registrada",
        "Ingesta energética diaria y apetito declarado. Sin umbral propio: la necesidad "
        "energética es individual y esta lista no dice si fue poca o mucha.",
        f"Sin lecturas de dieta en la ventana: {_NOT_RECORDED}",
    ),
    RecordedSource(
        "sleep", "Sueño", ("sleep-duration", "sleep-efficiency"), "Sueño registrado",
        "Duración y eficiencia del sueño registradas. Sin umbral propio aquí: esta lista no dice "
        "si fue poco o mucho; si se desvía lo juzga el estado en el dominio conductual, con su "
        "línea base.",
        "Sin lecturas de sueño en la ventana: que no conste no quiere decir que no lo hubiera.",
    ),
)
# Lo que quien construye el contexto tiene que pasar en `recorded`: solo estas claves se leen.
RECORDED_KEYS = frozenset(key for source in RECORDED_SOURCES for key in source.keys)

_FLUID, _DIET, _SLEEP = RECORDED_SOURCES
_NOT_ON_RECORD = "that none is on record does not mean there was none."
i18n.en_many({
    _EXERCISE.display: "Exercise",
    _EXERCISE.scope: (
        "Minutes of exercise and loading impacts recorded; there is no prescribed regimen to "
        "compare them with."
    ),
    _EXERCISE.no_data: f"No exercise readings in the window: {_NOT_ON_RECORD}",
    _FLUID.display: "Fluid intake",
    _FLUID.heading: "Fluid intake recorded",
    _FLUID.scope: (
        "24 h totals recorded. No threshold of its own: this list does not say whether it was "
        "little or much."
    ),
    _FLUID.no_data: f"No fluid intake readings in the window: {_NOT_ON_RECORD}",
    _DIET.display: "Diet",
    _DIET.heading: "Diet recorded",
    _DIET.scope: (
        "Daily energy intake and declared appetite. No threshold of its own: energy needs are "
        "individual and this list does not say whether it was little or much."
    ),
    _DIET.no_data: f"No diet readings in the window: {_NOT_ON_RECORD}",
    _SLEEP.display: "Sleep",
    _SLEEP.heading: "Sleep recorded",
    _SLEEP.scope: (
        "Sleep duration and efficiency recorded. No threshold of its own here: this list does "
        "not say whether it was little or much; if it deviates, the state judges it in the "
        "behavioral domain, with its baseline."
    ),
    _SLEEP.no_data: f"No sleep readings in the window: {_NOT_ON_RECORD}",
})


def _in_language(spec: RecordedSource) -> RecordedSource:
    """La misma fuente con sus textos en el idioma de la petición (el encabezado va al título)."""
    return RecordedSource(
        spec.kind, i18n.loc(spec.display), spec.keys, i18n.loc(spec.heading),
        i18n.loc(spec.scope), i18n.loc(spec.no_data),
    )


def _recorded(
    spec: RecordedSource, observations: Sequence[VitalObservation], window: Window, anchor: _Anchor
) -> Found:
    """Lo registrado de los indicadores de una fuente dentro de la ventana: cuanto consta."""
    spec = _in_language(spec)
    recorded = recorded_in_window(observations, window[0], window[1], spec.keys, spec.heading)
    return _listed(spec, recorded, anchor)


def _system_status(
    declarations: Sequence[dict[str, Any]], window: Window, anchor: _Anchor
) -> Found:
    """Lo que una persona declaro del estado de un sistema del habitat dentro de la ventana.

    EMMA no lee el estado de ningun sistema (`environment/systems.py`): esto es lo declarado,
    y lo dice. Sin ninguna declaracion la fuente no tiene dato, que no es lo mismo que «los
    sistemas estaban bien». Cada declaracion cuenta en el instante al que se refiere.
    """
    items = []
    for told in habitat_systems.history(declarations):
        moment = dt.datetime.fromisoformat(told["at"])
        if not _overlaps(moment, moment, window):
            continue
        where_en = "" if told["module"] is None else f" in {told['module_display']}"
        before_en = (
            f"previously on record as «{told['previous_state_display']}»" if told["changed"]
            else "no change from what was declared before"
        )
        where = "" if told["module"] is None else f" en {told['module_display']}"
        before = (
            f"antes constaba «{told['previous_state_display']}»" if told["changed"]
            else "sin cambio respecto a lo declarado antes"
        )
        items.append(_item(
            kind="system_status",
            title=i18n.tr(
                f"Sistema {told['system_display']}{where}: estado declarado "
                f"«{told['state_display']}» ({before})",
                f"System {told['system_display']}{where_en}: declared state "
                f"«{told['state_display']}» ({before_en})",
            ),
            detail=told["note"], start=moment, end=moment, anchor=anchor,
            source=i18n.tr(
                f"{habitat_systems.DECLARED_LABEL}; declarado por {told['declared_by']}, "
                f"asiento {told['ledger_index']}",
                f"{i18n.loc(habitat_systems.DECLARED_LABEL)}; declared by "
                f"{told['declared_by']}, ledger entry {told['ledger_index']}",
            ),
        ))
    if not declarations:
        return items, _source(
            "system_status", "Sistemas del hábitat", NO_DATA, 0,
            "Nadie ha declarado el estado de ningún sistema del hábitat: no se sabe si alguno "
            "cambió. EMMA no lee el estado de los sistemas.",
            en=(
                "No one has declared the state of any habitat system: it is not known whether "
                "any changed. EMMA does not read the state of the systems."
            ),
        )
    return items, _source(
        "system_status", "Sistemas del hábitat", WITH_DATA, len(items),
        f"Solo lo declarado en la consola ({habitat_systems.DECLARED_LABEL}): que no conste un "
        "cambio no quiere decir que no lo hubiera.",
        en=(
            f"Only what was declared in the console ({i18n.loc(habitat_systems.DECLARED_LABEL)}): "
            "that no change is on record does not mean there was none."
        ),
    )


def around(
    *,
    onset: dt.datetime | None,
    reference: dt.datetime,
    habitat_readings: Sequence[HabitatReading],
    habitat_excursions: Sequence[Excursion],
    mission_events: Sequence[dict[str, Any]],
    solar: SolarRecord | None,
    adoptions: Sequence[dict[str, Any]],
    mission_start: dt.date,
    mission_days: int,
    gravity_regime: str,
    stays: Sequence[Stay] = (),
    exercise: Sequence[VitalObservation] = (),
    system_declarations: Sequence[dict[str, Any]] = (),
    recorded: Sequence[VitalObservation] = (),
    alert: bool = True,
) -> dict[str, Any]:
    """Lo que solapa con la ventana alrededor del inicio de una alerta, fuente a fuente.

    `onset` es el inicio que da `explain.detail`; sin el (alerta por tendencia o por evento
    externo) la ventana se ancla al instante del estado, y se dice. `reference` es ese
    instante: nada posterior entra, tampoco un evento declarado de antemano. `solar` es None
    si no hay datos de DONKI. `mission_events` y `adoptions` llegan ya filtrados: solo los
    firmados por la consola y, para Tierra, los que existian en su corte. `stays` es donde ha
    declarado estar el tripulante (`api.mission.crew_stays`); vacio, habitat compartido.
    `exercise` son las lecturas de ejercicio del tripulante, ya cortadas al instante del estado.
    `system_declarations` es lo que una persona declaro del estado de los sistemas del habitat
    (`api.systems.system_declarations`), con el mismo filtro; vacio, nadie ha declarado nada.
    `recorded` son las lecturas medidas del tripulante de las claves de `RECORDED_KEYS` (ingesta
    de liquidos, dieta y sueno), ya cortadas al instante del estado como el ejercicio; vacio,
    las tres fuentes dicen que no tienen dato.
    `alert=False`: lo pide quien no tiene alerta (una region del modo anatomico sin ella); la
    ventana se ancla al instante del estado aunque haya `onset`, y lo dice.
    """
    anchor = _anchor(onset, reference, alert)
    window: Window = (
        anchor.moment - WINDOW_BEFORE, min(anchor.moment + WINDOW_AFTER, reference)
    )
    found = [
        _habitat(habitat_readings, habitat_excursions, window, anchor, stays),
        _mission_events(mission_events, window, anchor),
        _phase_changes(mission_start, mission_days, window, anchor),
        _solar(solar, window, anchor),
        _countermeasures(adoptions, window, anchor),
        _exercise(exercise, window, anchor),
        *(_recorded(spec, recorded, window, anchor) for spec in RECORDED_SOURCES),
        _system_status(system_declarations, window, anchor),
    ]
    mission = mission_context(anchor.moment, mission_start, mission_days, gravity_regime)
    items = sorted(
        (item for found_items, _ in found for item in found_items),
        key=lambda item: (item["start"], item["kind"], item["title"]),
    )
    day = i18n.tr("día de misión", "mission day")
    return {
        "label": i18n.loc(LABEL),
        # La frase que resume la lista, para que la interfaz no tenga que redactarla.
        "summary": i18n.tr(
            f"Registrado dentro de la ventana: {_count(len(items))}."
            if items
            else "Nada de lo registrado cae dentro de la ventana.",
            f"Recorded within the window: {_count(len(items))}."
            if items
            else "Nothing on record falls within the window.",
        ),
        "anchor": anchor.moment.isoformat(),
        "anchor_basis": anchor.basis,
        "window_start": window[0].isoformat(),
        "window_end": window[1].isoformat(),
        "window_hours_before": WINDOW_BEFORE.total_seconds() / 3600,
        "window_hours_after": WINDOW_AFTER.total_seconds() / 3600,
        "window_basis": i18n.loc(WINDOW_BASIS),
        "mission": {
            **mission,
            "statement": (
                f"{anchor.heading}: {day} {display.number(mission['mission_day'], 1)}, "
                f"{mission['phase_display']}, {mission['gravity_display']}."
            ),
        },
        "items": items,
        "sources": [source for _, source in found],
        "note": i18n.loc(NOTE if alert else NOTE_WITHOUT_ALERT),
    }


# --------------------------------------------------------------------------- #
# Concordancia entre senales del mismo dominio
# --------------------------------------------------------------------------- #

CONCORDANT = "concordant"
AGAINST = "against"
UNCHANGED = "unchanged"
MISSING = "no_data"

_STATE_DISPLAY = {
    CONCORDANT: "se desvía en su sentido preocupante",
    AGAINST: "deriva en el sentido contrario al preocupante",
    UNCHANGED: "con dato, sin desviación",
    MISSING: "sin dato",
}
_STATE_DISPLAY_EN = {
    CONCORDANT: "deviates in its concerning direction",
    AGAINST: "drifting opposite to its concerning direction",
    UNCHANGED: "with data, no deviation",
    MISSING: "no data",
}
_STATE_ORDER = (CONCORDANT, AGAINST, UNCHANGED, MISSING)

CONCORDANCE_BASIS = (
    "Descriptivo: no cambia el nivel de la alerta. «Se desvía» es un hallazgo persistente o "
    "una deriva preocupante según las mismas reglas del estado; el sentido preocupante de "
    "cada indicador es el que declara el catálogo. «En contra» es una deriva en el sentido "
    "opuesto que supera su umbral con la misma confianza. «Con dato»: alguna lectura en la "
    "ventana actual o una tendencia calculada."
)
_TRIGGER_BY_READING = (
    "Se toma como el que inició la alerta, de los indicadores con hallazgo persistente, el de "
    "la primera lectura fuera de lo esperado en la ventana actual."
)
_TRIGGER_BY_TREND = (
    "Ninguna lectura llega a hallazgo persistente: se toma como el que inició la alerta la "
    "deriva que supera su umbral con más margen."
)
_NO_TRIGGER = "Ningún indicador del dominio se desvía: la alerta no procede de sus lecturas."
TRIGGER_ROLE = "inició la alerta"
i18n.en_many({
    CONCORDANCE_BASIS: (
        "Descriptive: it does not change the level of the alert. «Deviates» is a persistent "
        "finding or a concerning drift under the same rules as the state; the concerning "
        "direction of each indicator is the one the catalogue declares. «Against» is a drift in "
        "the opposite direction that exceeds its threshold with the same confidence. «With "
        "data»: some reading in the current window or a computed trend."
    ),
    _TRIGGER_BY_READING: (
        "Among the indicators with a persistent finding, the one with the first reading "
        "outside the expected range in the current window is taken as the one that started "
        "the alert."
    ),
    _TRIGGER_BY_TREND: (
        "No reading reaches a persistent finding: the drift that exceeds its threshold by the "
        "widest margin is taken as the one that started the alert."
    ),
    _NO_TRIGGER: (
        "No indicator in the domain deviates: the alert does not come from its readings."
    ),
    TRIGGER_ROLE: "started the alert",
})


def _opposes(code: VitalCode, trend: Trend | None) -> bool:
    """El espejo de `Trend.is_concerning`: real, apreciable y en el sentido que NO preocupa."""
    if trend is None or code.concerning == "both":
        return False
    if not trend.significant or not trend.confidently_relevant:
        return False
    if code.reference_basis is ReferenceBasis.GUIDELINE:
        return False
    harmless = Direction.FALLING if code.concerning == "high" else Direction.RISING
    return trend.direction is harmless


def concordance(
    domain: Domain, current: Sequence[Deviation], trends: Iterable[Trend]
) -> dict[str, Any]:
    """Cuantos indicadores del dominio acompanan al que inicio la alerta, y cuales no.

    `current` son las desviaciones de la ventana actual (las mismas que ve el motor) y
    `trends` las tendencias. No puntua ni decide: cuenta.
    """
    series: dict[str, list[Deviation]] = {}
    for deviation in current:
        if get(deviation.key).domain is domain:
            series.setdefault(deviation.key, []).append(deviation)
    drift = {item.key: item for item in trends if get(item.key).domain is domain}
    findings = {
        key: found for key, readings in series.items()
        if (found := representative_deviation(readings)) is not None
    }
    drifting = [item for item in drift.values() if item.is_concerning]

    trigger: str | None = None
    trigger_basis = _NO_TRIGGER
    if findings:
        first = {
            key: min(item.effective for item in series[key] if item.is_concerning)
            for key in findings
        }
        trigger = min(first, key=lambda key: (first[key], key))
        trigger_basis = _TRIGGER_BY_READING
    elif drifting:
        trigger = min(drifting, key=lambda item: (-item.threshold_contrast, item.key)).key
        trigger_basis = _TRIGGER_BY_TREND

    indicators: list[dict[str, Any]] = []
    # Sin los descriptivos: el estado no los lee, y un «sin lecturas» suyo diría que cuentan.
    for code in evaluated_by_domain(domain):
        trend = drift.get(code.key)
        finding = findings.get(code.key)
        description: str | None = None
        if finding is not None:
            state, description = CONCORDANT, finding.describe()
        elif trend is not None and trend.is_concerning:
            state, description = CONCORDANT, trend.describe()
        elif trend is not None and _opposes(code, trend):
            state, description = AGAINST, trend.describe()
        elif code.key in series or trend is not None:
            state = UNCHANGED
        else:
            state = MISSING
        indicators.append({
            "key": code.key,
            "display": code.display,
            "display_es": code.display_es,
            "state": state,
            "state_display": i18n.tr(_STATE_DISPLAY[state], _STATE_DISPLAY_EN[state]),
            "is_trigger": code.key == trigger,
            "role_display": i18n.loc(TRIGGER_ROLE) if code.key == trigger else None,
            # La frase del motor, con la cifra y el sentido en que va. Sin desviacion, nada.
            "description": description,
        })
    indicators.sort(
        key=lambda item: (not item["is_trigger"], _STATE_ORDER.index(item["state"]), item["key"])
    )

    counts = {
        state: sum(1 for item in indicators if item["state"] == state) for state in _STATE_ORDER
    }
    with_data = len(indicators) - counts[MISSING]
    return {
        "trigger": trigger,
        "trigger_display": get(trigger).display_es if trigger is not None else None,
        "trigger_basis": i18n.loc(trigger_basis),
        "total": len(indicators),
        "with_data": with_data,
        "concordant": counts[CONCORDANT],
        "against": counts[AGAINST],
        "unchanged": counts[UNCHANGED],
        "no_data": counts[MISSING],
        "indicators": indicators,
        "statement": i18n.tr(
            f"Indicadores del dominio: {_count(len(indicators))}. Con dato: {_count(with_data)}. "
            f"Desviados en su sentido preocupante"
            f"{', contando el que inició la alerta' if trigger is not None else ''}: "
            f"{_count(counts[CONCORDANT])}. Con deriva en el sentido contrario: "
            f"{_count(counts[AGAINST])}. Sin desviación: {_count(counts[UNCHANGED])}. "
            f"Sin dato: {_count(counts[MISSING])}.",
            f"Indicators in the domain: {_count(len(indicators))}. With data: "
            f"{_count(with_data)}. Deviating in their concerning direction"
            f"{', counting the one that started the alert' if trigger is not None else ''}: "
            f"{_count(counts[CONCORDANT])}. Drifting in the opposite direction: "
            f"{_count(counts[AGAINST])}. No deviation: {_count(counts[UNCHANGED])}. "
            f"No data: {_count(counts[MISSING])}.",
        ),
        "basis": i18n.loc(CONCORDANCE_BASIS),
    }
