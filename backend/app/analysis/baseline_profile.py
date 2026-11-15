"""El perfil de línea base de un tripulante: contra qué se compara cada indicador hoy.

POR QUÉ EXISTE
--------------
La especificación del equipo pone `baseline_profile` en el modelo del astronauta (§3) y pregunta
en cada alerta «¿respecto a qué baseline?» (§10). EMMA calculaba la base y no la enseñaba: solo
salía dentro de una alerta (`explain.changed`: mediana y número de lecturas), así que sin alerta no
había forma de saber si un indicador se juzgaba contra la normalidad de esa persona o todavía
contra nada. Y la columna «Línea base» de la calidad del dato habla de las lecturas que se
apartan de la referencia, no de la referencia. «Nominal» sin base personal significa «no ha
cruzado ningún límite de peligro», no «está como siempre»: quien lee tiene que poder ver cuál de
las dos cosas es, indicador a indicador.

QUÉ HACE, Y QUÉ NO
------------------
**Describe; no calcula otra base.** Lee las desviaciones que `BaselineEngine.evaluate_rolling` ya
dejó hechas para el estado (`api/routes._assess`): cada una lleva el objeto `Baseline` contra el
que se juzgó su lectura. Por indicador y estado fisiológico se toma la de la lectura más reciente,
y de ella salen la mediana (`center`), la dispersión (`spread`, la desviación absoluta mediana
escalada), el número de lecturas y si estaba establecida (`used_population_range`). Nada se
vuelve a calcular con otra regla: si mañana el motor cambia de estadística, esto enseña la nueva.

Lo único que se cuenta aquí es **de dónde salieron** esas lecturas, porque la desviación no lo
guarda: `evaluate_rolling` toma el estado exacto y, si no da para una base, las lecturas de los
estados de su familia. Se cuentan las del estado exacto en la misma ventana y con la misma regla
(sin las de baja confianza); si no coinciden con las de la base, la base vino de la familia. La
prueba lo contrasta con el motor.

No escribe en el ledger, no toca el motor y no lo lee ningún nivel, alerta ni recomendación.

Los indicadores descriptivos no tienen base —el estado no los lee (`codes.DESCRIPTIVE_ONLY`)— y
se dice así, con su nombre.

SEXO DECLARADO APARTE, EDAD SIN CAMPO (§5.36.19, revisado el 2026-11-14)
----------------------------------------------------------------------
La especificación pone en el astronauta «sex/age sólo si el dataset lo permite» (§3). En la
decimosexta ronda el perfil no tenía campo para ninguno de los dos, y unas frases fijas lo decían
para que nadie supusiera que un rango dependía de ellos. El 2026-11-14 el usuario pidió que EMMA
contemple el ciclo menstrual, y eso revierte la mitad de aquella decisión: el sexo se declara
ahora, aparte del perfil, en su propio asiento firmado (`crew-sex`), lo declara el propio
tripulante y se puede borrar solo él. La edad sigue sin campo.

Lo que no cambia es lo que hacía cierta la frase: ningún rango ni umbral del catálogo depende del
sexo, y nada de `analysis/`, `advisor/` ni `ingest/` lo lee (lo comprueba
`test_no_rule_of_emma_reads_sex_or_age`). El sexo declarado solo decide, en `api/`, si se ofrece
el seguimiento del ciclo y si la línea base puede ajustarse por fase (`api/cycle_phase.py`, lote
«ciclo», B3); ese seguimiento es dato descriptivo, y lo que ajusta la línea base es la fase del
ciclo, que sale de los inicios de regla registrados como observación, no el sexo.

El perfil lo dice con frases fijas (`personal_data`): cómo se guarda el sexo y que ningún rango
depende de él ni de la edad —y que la única fecha de nacimiento que EMMA guarda es la de la
identidad declarada, que solo sirve para comprobar de quién es un informe o un volumen
(`reports/identity.py`, `volumes/privacy.py`)—; para qué sirve el sexo (el ciclo); que el límite
de radiación de carrera de NASA-STD-3001 [V1 4030] es el mismo para cualquier edad y sexo, con la
frase de la norma leída en su ficha; dónde la norma sí los usa y EMMA no da referencia; y por qué
guardarlo ahora es compatible con la privacidad de la especificación (§12): es el mínimo y se
borra aparte. Ninguna decide nada.

DE QUÉ ESTÁ HECHA Y DÓNDE CORTA (decimoséptima ronda, §5.37.2)
--------------------------------------------------------------
La especificación pide no mezclar datos de entornos distintos «sin conservar evidence_context»
(§2), pone los «personal thresholds» en el modelo del astronauta (§3) y pregunta en cada alerta
«¿respecto a qué baseline?» (§10). El perfil decía de qué estado salían las lecturas, pero no de
qué entorno ni de qué tipo (medido, inferido, predicho) eran, y el umbral personal no se veía como
cifra: solo «se juzga contra los percentiles de sus propias lecturas».

Ahora cada base dice las dos cosas. **Composición**: se toman las lecturas que el motor pudo usar
(las del estado, o las de su familia) y solo se dan por las de la base si sus valores, ordenados,
son exactamente los de `Baseline.sorted_values`; si no coinciden, se dice que no se puede saber,
no se cuenta otra cosa. **Cortes**: los de `baseline.personal_cuts` sobre la misma base que juzgó
la última lectura; por el lado que preocupa (`VitalCode.concerning`), y sin cifra el que la base
aún no sostiene. Todo descriptivo: no cambia el motor, la versión de las reglas ni ninguna alerta.

UNA SOLA FUNCIÓN DE CORTES (decimoctava ronda, §5.38.11)
--------------------------------------------------------
La primera versión repetía aquí la regla de lados y mínimos del motor (el cuantil por arriba y su
espejo por abajo, solo el lado que preocupa, las lecturas que pide cada gravedad) y una prueba la
contrastaba con él. Ya no la repite: `baseline.personal_cuts` es la función con la que gradúa
`crossed_personal_cut`, y de ella salen la gravedad, el cuantil, el mínimo de lecturas, si la base
lo sostiene y el valor por cada lado. Si el motor cambia de regla, el perfil enseña la nueva sin
que nadie lo toque aquí. Las tablas privadas del motor (`_QUANTILE_THRESHOLDS`,
`_SAMPLES_FOR_SEVERITY`) ya no se importan.
"""

from __future__ import annotations

import bisect
import datetime as dt
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

from app.analysis.baseline import (
    DEFAULT_ROLLING_LAG,
    DEFAULT_ROLLING_WINDOW,
    MAD_TO_SD,
    MIN_SAMPLES,
    Baseline,
    Deviation,
    Severity,
    cut_rules,
    personal_cuts,
)
from app.analysis.inferred import cited, english_relevance
from app.core import display, i18n
from app.evidence import registry
from app.ingest.codes import CATALOG, ReferenceBasis, VitalCode, get
from app.ingest.fhir import LOW_CONFIDENCE_THRESHOLD, Context, VitalObservation

# El estado fisiológico de la lectura, como se lee (`fhir.Context`). Un estado nuevo sin palabra
# falla en la prueba, no se enseña con su clave.
CONTEXT_DISPLAY: dict[Context, str] = {
    Context.UNKNOWN: "estado no declarado",
    Context.SLEEP: "sueño",
    Context.REST: "reposo",
    Context.WORK: "trabajo",
    Context.MEAL: "comida",
    Context.ACTIVE: "actividad física",
}

# De dónde sale el rango del catálogo (`codes.ReferenceBasis`), como se lee.
REFERENCE_BASIS_DISPLAY: dict[ReferenceBasis, str] = {
    ReferenceBasis.OBSERVED: "medido en población sana",
    ReferenceBasis.GUIDELINE: "recomendación clínica, no un umbral de alerta",
    ReferenceBasis.DESIGN: "escala definida por EMMA",
    ReferenceBasis.LIMIT: "límite normativo o de exposición",
}

ESTABLISHED = "establecida"
LEARNING = "en aprendizaje"

# Las mismas palabras en inglés (`core/i18n.py`), por la misma clave. Tablas aparte y no el
# registro de `i18n.en`: son palabras cortas («reposo», «comida», «establecida») que otro módulo
# puede usar con otro sentido, y el registro admite un solo inglés por castellano.
CONTEXT_DISPLAY_EN: dict[Context, str] = {
    Context.UNKNOWN: "undeclared state",
    Context.SLEEP: "sleep",
    Context.REST: "rest",
    Context.WORK: "work",
    Context.MEAL: "meal",
    Context.ACTIVE: "physical activity",
}
REFERENCE_BASIS_DISPLAY_EN: dict[ReferenceBasis, str] = {
    ReferenceBasis.OBSERVED: "measured in a healthy population",
    ReferenceBasis.GUIDELINE: "clinical recommendation, not an alert threshold",
    ReferenceBasis.DESIGN: "scale defined by EMMA",
    ReferenceBasis.LIMIT: "regulatory or exposure limit",
}
ESTABLISHED_EN = "established"
LEARNING_EN = "learning"


def _context_word(state: Context) -> str:
    """El estado fisiológico como se lee, en el idioma de la petición."""
    return i18n.tr(CONTEXT_DISPLAY[state], CONTEXT_DISPLAY_EN[state])


def _loc(text: str | None) -> str | None:
    """Una frase fija registrada, en el idioma de la petición; `None` se queda `None`."""
    return i18n.loc(text) if text is not None else None

# Lo que el motor hace sin base personal (`BaselineEngine._evaluate_against_population`): el
# rango del catálogo no avisa; solo un límite de peligro.
RANGE_ROLE = (
    "Mientras no hay base personal no se avisa por salir de este rango: solo por cruzar un "
    "límite de peligro."
)
NO_RANGE = "Sin rango de referencia en el catálogo."

DESCRIPTIVE_REASON = (
    "Indicador descriptivo: se firma y se enseña, pero el estado no lo lee, así que no tiene "
    "línea base."
)
# El inglés de las frases fijas de arriba; se resuelve donde se sirven, con `i18n.loc`.
i18n.en(
    RANGE_ROLE,
    "While there is no personal baseline, leaving this range raises no warning: only crossing "
    "a danger limit does.",
)
i18n.en(NO_RANGE, "No reference range in the catalogue.")
i18n.en(
    DESCRIPTIVE_REASON,
    "Descriptive indicator: it is signed and shown, but the status does not read it, so it has "
    "no baseline.",
)


def _days(span: dt.timedelta) -> str:
    return display.number(span.total_seconds() / 86_400, 0)


def _hours(span: dt.timedelta) -> str:
    return display.number(span.total_seconds() / 3_600, 0)


def method() -> str:
    """Cómo es la base del estado, con las cifras del motor (no copiadas)."""
    return i18n.tr(
        f"Base móvil: cada lectura se compara con las del mismo estado (sueño con sueño, reposo "
        f"con reposo) de los {_days(DEFAULT_ROLLING_WINDOW)} días que terminan "
        f"{_hours(DEFAULT_ROLLING_LAG)} h antes de ella, sin las de baja confianza. Centro: la "
        f"mediana; dispersión: la desviación absoluta mediana por "
        f"{display.number(MAD_TO_SD, 4)}. Se da por establecida con "
        f"{display.number(MIN_SAMPLES, 0)} lecturas; hasta entonces solo avisa un límite de "
        f"peligro del catálogo.",
        f"Rolling baseline: each reading is compared with those of the same state (sleep with "
        f"sleep, rest with rest) from the {_days(DEFAULT_ROLLING_WINDOW)} days ending "
        f"{_hours(DEFAULT_ROLLING_LAG)} h before it, without the low-confidence ones. Centre: "
        f"the median; spread: the median absolute deviation times "
        f"{display.number(MAD_TO_SD, 4)}. It is taken as established with "
        f"{display.number(MIN_SAMPLES, 0)} readings; until then only a catalogue danger limit "
        f"warns.",
    )


FIXED_NOTE = (
    "No hay base fija: el estado usa solo la móvil. El motor sabe congelar una base de "
    "prevuelo, pero el estado no la usa, y las bases por fase de misión siguen pendientes "
    "(especificación §6)."
)
i18n.en(
    FIXED_NOTE,
    "There is no fixed baseline: the status uses only the rolling one. The engine can freeze a "
    "preflight baseline, but the status does not use it, and baselines per mission phase are "
    "still pending (specification §6).",
)


def _family_members(state: Context) -> list[Context]:
    """Los estados cuyas lecturas forman la «familia» de `state` en `evaluate_rolling`.

    Son los que el motor agrupa: estados cuya familia es la de `state` y que no son su propia
    familia. Se deriva de `Context.family` igual que allí, sin escribir la lista a mano.
    """
    family = state.family
    return [item for item in Context if item.family is family and item.family is not item]


def _join(words: Sequence[str]) -> str:
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + i18n.tr(" y ", " and ") + words[-1]


def _limits_text_en(code: VitalCode, low: float | None, high: float | None) -> str:
    """`_limits_text` en inglés."""
    sides = []
    if low is not None:
        sides.append(f"below {display.quantity(code.key, low, code.unit)}")
    if high is not None:
        sides.append(f"above {display.quantity(code.key, high, code.unit)}")
    if not sides:
        return "No danger limit in the catalogue for this state."
    return (
        "Danger limit in this state: " + " or ".join(sides)
        + " (checked whether or not there is a personal baseline)."
    )


def _limits_text(code: VitalCode, low: float | None, high: float | None) -> str:
    if i18n.current() == "en":
        return _limits_text_en(code, low, high)
    parts = []
    if low is not None:
        parts.append(f"por debajo de {display.quantity(code.key, low, code.unit)}")
    if high is not None:
        parts.append(f"por encima de {display.quantity(code.key, high, code.unit)}")
    if not parts:
        return "Sin límite de peligro en el catálogo para este estado."
    return (
        "Límite de peligro en este estado: " + " o ".join(parts)
        + " (se comprueba haya o no base personal)."
    )


def _danger_bounds(code: VitalCode, state: Context) -> tuple[float | None, float | None]:
    """Los límites que aplica `baseline.crossed_danger_limit` a una lectura en ese estado."""
    at_rest = state.family in {Context.REST, Context.SLEEP}
    exerting = state is Context.ACTIVE
    return code.critical_bounds(at_rest, exerting)


def _judged_against_en(established: bool, unlimited: bool) -> str:
    """`_judged_against` en inglés; `unlimited`: el estado no tiene límite de peligro."""
    if established and unlimited:
        return "Judged against the percentiles of their own readings."
    if established:
        return (
            "Judged against the percentiles of their own readings and also against the danger "
            "limit."
        )
    if unlimited:
        return "While learning it raises no warning: there is no personal baseline or danger limit."
    return "While learning only the catalogue danger limit warns."


def _judged_against(established: bool, low: float | None, high: float | None) -> str:
    no_limit = low is None and high is None
    if i18n.current() == "en":
        return _judged_against_en(established, no_limit)
    if established and no_limit:
        return "Se juzga contra los percentiles de sus propias lecturas."
    if established:
        return (
            "Se juzga contra los percentiles de sus propias lecturas y también contra el "
            "límite de peligro."
        )
    if no_limit:
        return "Mientras aprende no avisa: no hay base personal ni límite de peligro."
    return "Mientras aprende solo avisa el límite de peligro del catálogo."


def _reference_text_en(code: VitalCode) -> str:
    """La frase del rango del catálogo (`_reference`) en inglés."""
    bottom, top = code.reference_low, code.reference_high
    if code.reference_basis is None:
        return i18n.loc(NO_RANGE)
    if bottom is not None and top is not None:
        extent = (
            f"from {display.number(bottom, display.decimals_for(code.key))} to "
            f"{display.quantity(code.key, top, code.unit)}"
        )
    elif bottom is not None:
        extent = f"from {display.quantity(code.key, bottom, code.unit)} upwards"
    else:
        assert top is not None  # `VitalCode.__post_init__`: hay base <=> hay rango
        extent = f"up to {display.quantity(code.key, top, code.unit)}"
    origin = REFERENCE_BASIS_DISPLAY_EN[code.reference_basis]
    return f"Catalogue range: {extent} ({origin}). {i18n.loc(RANGE_ROLE)}"


def _reference_shown(code: VitalCode) -> dict[str, Any]:
    """`_reference` como se sirve: los mismos campos, con la frase en el idioma de la petición."""
    found = _reference(code)
    if i18n.current() != "en":
        return found
    return {**found, "text": _reference_text_en(code)}


def _reference(code: VitalCode) -> dict[str, Any]:
    low, high = code.reference_low, code.reference_high
    if code.reference_basis is None:
        return {"low": None, "high": None, "basis": None, "text": NO_RANGE}
    if low is not None and high is not None:
        span = (
            f"de {display.number(low, display.decimals_for(code.key))} a "
            f"{display.quantity(code.key, high, code.unit)}"
        )
    elif low is not None:
        span = f"desde {display.quantity(code.key, low, code.unit)}"
    else:
        assert high is not None  # `VitalCode.__post_init__`: hay base <=> hay rango
        span = f"hasta {display.quantity(code.key, high, code.unit)}"
    basis = REFERENCE_BASIS_DISPLAY[code.reference_basis]
    return {
        "low": low,
        "high": high,
        "basis": str(code.reference_basis),
        "text": f"Rango del catálogo: {span} ({basis}). {RANGE_ROLE}",
    }


# --- Dónde corta la base: los percentiles del motor, como cifra (especificación §3) -------------
# La gravedad de cada corte, con la palabra con que se enseña un hallazgo
# (`risk_entity.FINDING_SEVERITY_DISPLAY`; la prueba las contrasta).
CUT_SEVERITY_DISPLAY: dict[Severity, str] = {
    Severity.MILD: "leve",
    Severity.MODERATE: "moderada",
    Severity.SEVERE: "grave",
}
# Un indicador que solo preocupa por un lado no avisa por percentil hacia el otro
# (`baseline.watches`); el límite de peligro sí se mira por los dos.
ONE_SIDED_NOTE: dict[str, str] = {
    "high": (
        "Por debajo de su base no se avisa por percentil: en este indicador lo que se vigila es "
        "la subida."
    ),
    "low": (
        "Por encima de su base no se avisa por percentil: en este indicador lo que se vigila es "
        "la bajada."
    ),
}
NO_VALUES = "la base no guarda sus valores, así que no hay corte que enseñar"
# En inglés (`core/i18n.py`). La gravedad, en tabla aparte como el estado: «leve» o «grave» son
# palabras que otros módulos también rotulan.
CUT_SEVERITY_DISPLAY_EN: dict[Severity, str] = {
    Severity.MILD: "mild",
    Severity.MODERATE: "moderate",
    Severity.SEVERE: "severe",
}
i18n.en_many({
    ONE_SIDED_NOTE["high"]: (
        "Below their baseline no percentile warning is given: in this indicator what is "
        "watched is the rise."
    ),
    ONE_SIDED_NOTE["low"]: (
        "Above their baseline no percentile warning is given: in this indicator what is "
        "watched is the fall."
    ),
    NO_VALUES: "the baseline does not keep its values, so there is no cut to show",
})


def _percentile(fraction: float) -> str:
    """Un cuantil como percentil, con los decimales que tiene: «99», «99,5», «0,1»."""
    share = round(fraction * 100, 3)
    for decimals in range(4):
        if round(share, decimals) == share:
            return display.number(share, decimals)
    return display.number(share, 3)


def _cuts(code: VitalCode, baseline: Baseline | None, established: bool) -> list[dict[str, Any]]:
    """Los cortes de percentil con que el motor gradúa una lectura contra esta base.

    Salen de `baseline.personal_cuts`, la función con la que gradúa el motor: qué cortes tiene la
    base, por qué lado (solo el que preocupa), cuáles sostiene con sus lecturas y cuánto vale cada
    uno. Aquí solo se ordenan de leve a grave y se dicen. Sin base establecida no hay ninguno: no
    es contra lo que se juzga.
    """
    if not established or baseline is None:
        return []
    # Un decimal más que la lectura: el corte se interpola entre dos, y redondearlo a la cifra de
    # la lectura haría parecer que una lectura igual al corte lo cruza.
    decimals = display.decimals_for(code.key) + 1
    unit = display.unit(code.unit)
    rows: list[dict[str, Any]] = []
    # De leve a grave; el motor los recorre al revés, del más exigente al menos.
    for cut in sorted(personal_cuts(baseline, code), key=lambda item: item.rule.fraction):
        rule = cut.rule
        applies = cut.supported and cut.has_values
        high, low = cut.high, cut.low
        word = i18n.tr(
            CUT_SEVERITY_DISPLAY[rule.severity], CUT_SEVERITY_DISPLAY_EN[rule.severity]
        )
        if applies:
            parts = []
            if high is not None:
                parts.append(i18n.tr(
                    f"por encima de {display.number(high, decimals)} {unit} (percentil "
                    f"{_percentile(rule.quantile('high'))} de su base)",
                    f"above {display.number(high, decimals)} {unit} (percentile "
                    f"{_percentile(rule.quantile('high'))} of their baseline)",
                ))
            if low is not None:
                parts.append(i18n.tr(
                    f"por debajo de {display.number(low, decimals)} {unit} (percentil "
                    f"{_percentile(rule.quantile('low'))} de su base)",
                    f"below {display.number(low, decimals)} {unit} (percentile "
                    f"{_percentile(rule.quantile('low'))} of their baseline)",
                ))
            text = f"{word.capitalize()}: " + i18n.tr(" o ", " or ").join(parts) + "."
        elif not cut.supported:
            text = i18n.tr(
                f"{word.capitalize()}: sin corte todavía; pide "
                f"{display.number(rule.min_samples, 0)} lecturas de base y tiene "
                f"{display.number(baseline.samples, 0)}.",
                f"{word.capitalize()}: no cut yet; it asks for "
                f"{display.number(rule.min_samples, 0)} baseline readings and has "
                f"{display.number(baseline.samples, 0)}.",
            )
        else:
            text = f"{word.capitalize()}: {i18n.loc(NO_VALUES)}."
        rows.append({
            "severity": str(rule.severity),
            "display": word,
            "quantile": rule.fraction,
            "min_samples": rule.min_samples,
            "applies": applies,
            # Sin redondear, como la mediana: redondear aquí y al pintar cambiaría la cifra.
            "high": high,
            "low": low,
            "text": text,
        })
    return rows


def cuts_method() -> str:
    """Cómo corta una base establecida, con las cifras del motor (no copiadas).

    Dice también el tope por baja confianza (`baseline._apply_confidence`): sin él, «grave por
    encima de X» no sería cierto para una lectura dudosa, que se queda en leve.
    """
    graded = sorted(cut_rules(), key=lambda rule: rule.fraction)  # de leve a grave
    if i18n.current() == "en":
        above = _join([
            f"{CUT_SEVERITY_DISPLAY_EN[rule.severity]} above percentile "
            f"{_percentile(rule.quantile('high'))} (with {display.number(rule.min_samples, 0)} "
            f"baseline readings or more)"
            for rule in graded
        ])
        below = _join([f"percentile {_percentile(rule.quantile('low'))}" for rule in graded])
        return (
            f"Each established baseline cuts at the percentiles of its own readings: {above}; "
            f"on the low side, below {below}. A reading with confidence below "
            f"{display.number(LOW_CONFIDENCE_THRESHOLD, 1)} that crosses a cut stays at mild: "
            f"the quality of the measurement supports no more."
        )
    upper = _join([
        f"{CUT_SEVERITY_DISPLAY[rule.severity]} por encima del "
        f"{_percentile(rule.quantile('high'))} (con {display.number(rule.min_samples, 0)} "
        f"lecturas de base o más)"
        for rule in graded
    ])
    lower = _join([f"del {_percentile(rule.quantile('low'))}" for rule in graded])
    return (
        f"Cada base establecida corta en los percentiles de sus propias lecturas: {upper}; por "
        f"abajo, por debajo {lower}. Una lectura con confianza por debajo de "
        f"{display.number(LOW_CONFIDENCE_THRESHOLD, 1)} que cruce un corte se queda en leve: la "
        f"calidad de la medida no sostiene más."
    )


# --- De qué está hecha la base: entorno y tipo de sus lecturas (especificación §2) -------------
UNKNOWN_COMPOSITION = (
    "No se puede decir de qué entorno ni de qué tipo son: las lecturas de la ventana no son "
    "exactamente las de la base."
)
EMPTY_COMPOSITION = "La base no tiene lecturas."
NOT_KEPT_COMPOSITION = (
    "No se puede decir de qué entorno ni de qué tipo son: la base no guarda sus valores."
)
i18n.en_many({
    UNKNOWN_COMPOSITION: (
        "It cannot be told which environment or type they are: the readings in the window are "
        "not exactly those of the baseline."
    ),
    EMPTY_COMPOSITION: "The baseline has no readings.",
    NOT_KEPT_COMPOSITION: (
        "It cannot be told which environment or type they are: the baseline does not keep its "
        "values."
    ),
})

_Pool = tuple[list[dt.datetime], list[VitalObservation]]


def _in_window(pool: _Pool | None, start: dt.datetime, end: dt.datetime) -> list[VitalObservation]:
    """Las lecturas de un estado en la ventana, con los bordes de `evaluate_rolling` (incluidos)."""
    if pool is None:
        return []
    times, readings = pool
    return readings[bisect.bisect_left(times, start):bisect.bisect_right(times, end)]


def _tally(values: Iterable[str]) -> dict[str, int]:
    """Cuántas de cada valor, de la más frecuente a la menos (y por nombre si empatan)."""
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))


def _composition(
    baseline: Baseline | None,
    candidates: Iterable[Sequence[VitalObservation]],
) -> dict[str, Any] | None:
    """El entorno (`evidence_context`) y el tipo de las lecturas que forman la base.

    Solo se cuentan si sus valores son exactamente los de la base: `candidates` da primero las
    del estado, como hace el motor, y después las de su familia (perezoso: casi siempre bastan
    las del estado). Si ninguna coincide, `None`: se dice que no se sabe en vez de contar unas
    lecturas que quizá no son las que usó.
    """
    if baseline is None or len(baseline.sorted_values) != baseline.samples:
        return None
    wanted = list(baseline.sorted_values)
    for readings in candidates:
        if len(readings) != len(wanted):
            continue
        if sorted(item.value for item in readings) == wanted:
            return {
                "samples": len(readings),
                "evidence_context": _tally(str(item.evidence) for item in readings),
                "observation_type": _tally(str(item.observation_type) for item in readings),
            }
    return None


def _composition_text(composition: dict[str, Any] | None, kept: bool) -> str | None:
    """Lo que hay que decir de la composición; nada si es de un solo entorno y toda medida.

    `kept`: si la base guarda sus valores. Sin ellos no hay con qué comparar, y es otro motivo.
    """
    if composition is None:
        return UNKNOWN_COMPOSITION if kept else NOT_KEPT_COMPOSITION
    if composition["samples"] == 0:
        return EMPTY_COMPOSITION
    parts = []
    contexts = len(composition["evidence_context"])
    if contexts > 1:
        parts.append(i18n.tr(
            f"Mezcla lecturas de {display.number(contexts, 0)} entornos de evidencia; se cuentan "
            f"por separado.",
            f"It mixes readings from {display.number(contexts, 0)} evidence environments; they "
            f"are counted separately.",
        ))
    others = composition["samples"] - composition["observation_type"].get("measured", 0)
    if others:
        parts.append(i18n.tr(
            f"{display.number(others, 0)} de las {display.number(composition['samples'], 0)} "
            f"no {'es una medida' if others == 1 else 'son medidas'}: "
            f"{'es inferida o predicha' if others == 1 else 'son inferidas o predichas'}.",
            f"{display.number(others, 0)} of the {display.number(composition['samples'], 0)} "
            f"{'is not a measurement' if others == 1 else 'are not measurements'}: "
            f"{'it is' if others == 1 else 'they are'} inferred or predicted.",
        ))
    return " ".join(parts) or None


def _state_row(
    deviation: Deviation,
    state: Context,
    pools: dict[Context, _Pool],
    latest: bool,
) -> dict[str, Any]:
    """La base contra la que se juzgó la última lectura de un indicador en un estado.

    `pools`: por estado, las lecturas del indicador que el motor pudo usar (sin las de baja
    confianza), ordenadas, con sus horas; de ahí sale la composición.
    """
    code = get(deviation.key)
    baseline = deviation.baseline
    samples = baseline.samples if baseline is not None else 0
    window_end = deviation.effective - DEFAULT_ROLLING_LAG
    window_start = window_end - DEFAULT_ROLLING_WINDOW
    # Las lecturas del estado exacto en la ventana, con los mismos bordes que `evaluate_rolling`
    # (desde el inicio incluido hasta el final incluido). Si la base tiene otras, vino de la
    # familia.
    own = _in_window(pools.get(state), window_start, window_end)
    exact = len(own)
    from_family = samples != exact
    members = [_context_word(item) for item in _family_members(state)]
    state_word = _context_word(state)
    if from_family and members:
        drawn = i18n.tr(
            f"Lecturas de {_join(members)}: las de {state_word} no bastaban "
            f"({display.number(exact, 0)}).",
            f"Readings from {_join(members)}: those from {state_word} were not enough "
            f"({display.number(exact, 0)}).",
        )
    elif from_family:
        # Un estado sin familia no puede tomar prestado: si las cuentas no casan, el motor ha
        # cambiado su forma de agrupar y esto ya no lo describe. Se dice, no se inventa.
        drawn = i18n.tr(
            f"La base tiene {display.number(samples, 0)} lecturas y {state_word} "
            f"{display.number(exact, 0)}: no se puede decir de dónde salen las demás.",
            f"The baseline has {display.number(samples, 0)} readings and {state_word} has "
            f"{display.number(exact, 0)}: it cannot be told where the rest come from.",
        )
    else:
        drawn = i18n.tr(f"Lecturas de {state_word}.", f"Readings from {state_word}.")

    established = not deviation.used_population_range
    decimals = display.decimals_for(code.key)
    median = baseline.center if (established and baseline is not None) else None
    spread = baseline.spread if (established and baseline is not None) else None
    low, high = _danger_bounds(code, state)

    def candidates() -> Iterator[list[VitalObservation]]:
        yield own
        yield [
            reading
            for member in _family_members(state)
            for reading in _in_window(pools.get(member), window_start, window_end)
        ]

    composition = _composition(baseline, candidates())
    kept = baseline is not None and len(baseline.sorted_values) == baseline.samples
    row: dict[str, Any] = {
        "context": str(state),
        "context_display": state_word,
        "latest": latest,
        "reading_effective": deviation.effective.isoformat(),
        "window": {"start": window_start.isoformat(), "end": window_end.isoformat()},
        "drawn_from": "family" if from_family else "state",
        "drawn_from_display": drawn,
        "established": established,
        "status_display": (
            i18n.tr(ESTABLISHED, ESTABLISHED_EN) if established
            else i18n.tr(LEARNING, LEARNING_EN)
        ),
        "samples": samples,
        "min_samples": MIN_SAMPLES,
        # Sin base establecida no se da mediana: no es contra lo que se juzga, y enseñarla haría
        # creer que sí. Sin redondear: redondear aquí y otra vez al pintar cambiaría la cifra.
        "median": median,
        "spread": spread,
        "decimals": decimals,
        "danger_limit": {"low": low, "high": high, "text": _limits_text(code, low, high)},
        "judged_against": _judged_against(established, low, high),
        # De qué está hecha: por entorno y por tipo (None si no se puede saber), y la frase.
        "composition": composition,
        # `_loc`: la frase puede ser una de las fijas; las compuestas ya salen en su idioma.
        "composition_display": _loc(_composition_text(composition, kept)),
        # Dónde corta: los percentiles del motor, en la unidad del indicador.
        "cuts": _cuts(code, baseline, established),
        "cuts_note": ONE_SIDED_NOTE.get(code.concerning) if established else None,
    }
    row["cuts_note"] = _loc(row["cuts_note"])
    return row


# --- Sexo declarado aparte, edad sin campo (especificación §3 y §12) ---------------------------
# Los dos datos que el modelo del astronauta deja «sólo si el dataset lo permite». El sexo se
# declara en su propio asiento (`crew-sex`, 2026-11-14) y solo lo lee `api/` para ofrecer el
# seguimiento del ciclo; la edad no tiene campo. Ninguna regla de EMMA los lee; si alguna llegara a
# hacerlo, estas frases dejarían de ser ciertas.
NO_FIELD: tuple[str, ...] = ("edad",)
# El límite de [V1 4030], el de la norma: el que configura EMMA por defecto
# (`Settings.career_dose_limit_msv`) lo comprueba una prueba contra este.
NORM_CAREER_LIMIT_MSV = 600
LIMIT_SOURCE = registry.cite(
    "nasa-std-3001-vol1-rev-c",
    "[V1 4030], sección 4.8.2: el límite de carrera de 600 mSv «is universal for all ages and "
    "sexes»; el cálculo individual del riesgo (REID) sí usa parámetros de sexo y edad, como "
    "[V1 4020] (nutrición) y [V1 4026] (densidad ósea prevuelo)",
)
PERSONAL_DATA_STATEMENT = (
    "El sexo no es un campo del perfil: lo declara el propio tripulante en un asiento firmado "
    "aparte, que se puede borrar solo. La edad no tiene campo. Ningún rango ni umbral "
    "depende de ellos: cada rango del catálogo es el mismo para cualquier tripulante, y la línea "
    "base se hace con sus propias lecturas. La única fecha de nacimiento que EMMA guarda es la "
    "de la identidad declarada, y solo sirve para comprobar que un informe escaneado o un "
    "volumen de imagen es suyo."
)
# Para qué sirve el sexo declarado: la puerta del seguimiento del ciclo y del ajuste por fase,
# que vive en `api/`.
PERSONAL_DATA_CYCLE = (
    "El sexo declarado solo decide si se ofrece el seguimiento del ciclo menstrual y si la "
    "línea base puede ajustarse por su fase. Ese seguimiento es dato descriptivo y no avisa por "
    "sí mismo; lo que puede ajustar la línea base es la fase del ciclo registrada, no el sexo: "
    "solo con ciclo regular declarado e inicios de regla suficientes, y en la fase lútea se "
    "descuenta de la temperatura y del pulso lo que la fase sube según lo leído."
)
PERSONAL_DATA_RADIATION = (
    "El límite de radiación de toda la carrera de NASA-STD-3001 [V1 4030], "
    f"{display.number(NORM_CAREER_LIMIT_MSV, 0)} mSv efectivos, es el mismo para cualquier edad y "
    "sexo: la norma dice que es «universal for all ages and sexes». EMMA no calcula el riesgo "
    "individual de muerte inducida por la exposición (REID), para el que la norma sí usa "
    "parámetros de sexo y edad."
)
# Donde la norma leída sí ajusta por sexo y edad, y por qué EMMA no lo necesita: no da esas
# referencias (la ingesta energética no lleva rango en `ingest/codes.py`; la densidad ósea solo se
# infiere como banda de pérdida en `analysis/inferred.py`).
PERSONAL_DATA_ELSEWHERE = (
    "Donde la misma norma sí usa el sexo y la edad, EMMA no da referencia: no calcula la "
    "necesidad de energía y nutrientes de [V1 4020] —la ingesta energética no lleva rango— ni "
    "compara la densidad ósea prevuelo de [V1 4026], que es por DXA; de la densidad solo infiere "
    "una banda de pérdida."
)
PERSONAL_DATA_PRIVACY = (
    "La especificación pide evitar guardar contenido personal innecesario en los registros "
    "(especificación §12). El sexo se guarda porque hace falta para ofrecer el seguimiento del "
    "ciclo; se guarda lo mínimo —femenino o masculino, y quién lo declaró—, y borrarlo no toca "
    "el resto del registro. La edad no se guarda: ninguna regla de EMMA la necesita."
)
# El inglés de las frases de arriba (`core/i18n.py`): dicen lo mismo, ni más ni menos. Se resuelve
# al servir, en `personal_data`.
_NO_FIELD_EN: dict[str, str] = {"edad": "age"}
english_relevance(
    LIMIT_SOURCE,
    "[V1 4030], section 4.8.2: the 600 mSv career limit “is universal for all ages and sexes”; "
    "the individual risk calculation (REID) does use sex and age parameters, as do [V1 4020] "
    "(nutrition) and [V1 4026] (preflight bone density)",
)
i18n.en_many({
    PERSONAL_DATA_STATEMENT: (
        "Sex is not a profile field: the crew member declares it in a separate signed entry, "
        "which can be erased on its own. Age has no field. No range or threshold depends on "
        "them: each catalogue range is the same for any crew member, and the baseline is built "
        "from their own readings. The only date of birth EMMA keeps is that of the declared "
        "identity, and it only serves to check that a scanned report or an imaging volume is "
        "theirs."
    ),
    PERSONAL_DATA_CYCLE: (
        "The declared sex only decides whether menstrual cycle tracking is offered and whether "
        "the baseline can be adjusted for its phase. That tracking is descriptive data and "
        "raises no warning by itself; what can adjust the baseline is the recorded cycle phase, "
        "not sex: only with a declared regular cycle and enough period starts, and in the "
        "luteal phase what the phase raises, according to what was read, is discounted from "
        "temperature and heart rate."
    ),
    PERSONAL_DATA_RADIATION: (
        "The whole-career radiation limit of NASA-STD-3001 [V1 4030], "
        f"{display.number(NORM_CAREER_LIMIT_MSV, 0)} mSv effective dose, is the same for any age "
        "and sex: the standard says it is “universal for all ages and sexes”. EMMA does not "
        "calculate the individual risk of exposure-induced death (REID), for which the standard "
        "does use sex and age parameters."
    ),
    PERSONAL_DATA_ELSEWHERE: (
        "Where the same standard does use sex and age, EMMA gives no reference: it does not "
        "calculate the energy and nutrient requirement of [V1 4020] —energy intake carries no "
        "range— nor compare the preflight bone density of [V1 4026], which is by DXA; of density "
        "it only infers a loss band."
    ),
    PERSONAL_DATA_PRIVACY: (
        "The specification asks to avoid keeping unnecessary personal content in the records "
        "(specification §12). Sex is kept because it is needed to offer cycle tracking; the "
        "minimum is kept —female or male, and who declared it—, and erasing it does not touch "
        "the rest of the record. Age is not kept: no EMMA rule needs it."
    ),
})


def personal_data() -> dict[str, Any]:
    """Qué se guarda del sexo y la edad, y para qué. Frases fijas: no decide nada."""
    body = {
        "no_field": list(NO_FIELD),
        "statement": PERSONAL_DATA_STATEMENT,
        "cycle": PERSONAL_DATA_CYCLE,
        "radiation": PERSONAL_DATA_RADIATION,
        "elsewhere": PERSONAL_DATA_ELSEWHERE,
        "privacy": PERSONAL_DATA_PRIVACY,
        "source": LIMIT_SOURCE.to_dict(),
    }
    # Lo de arriba, en el idioma de la petición: cada frase fija con su inglés registrado, el
    # nombre del campo sin sitio y el «para qué» de la cita.
    return {
        **{key: _loc(value) if isinstance(value, str) else value for key, value in body.items()},
        "no_field": [i18n.tr(name, _NO_FIELD_EN.get(name, name)) for name in NO_FIELD],
        "source": cited(LIMIT_SOURCE),
    }


_ORDER = {key: index for index, key in enumerate(CATALOG)}


def _catalog_order(key: str) -> int:
    return _ORDER.get(key, len(_ORDER))


def profile(
    subject: str,
    observations: Sequence[VitalObservation],
    deviations: Sequence[Deviation],
    reference_time: dt.datetime,
    descriptive_keys: Iterable[str] = (),
) -> dict[str, Any]:
    """El perfil de línea base: por indicador y estado, la base de su lectura más reciente.

    `observations` y `deviations` son las del estado (`_assess`): las lecturas analizadas y lo
    que el motor dijo de cada una. `descriptive_keys`, los descriptivos con lecturas.
    """
    # El estado de cada lectura: la desviación no lo lleva. Una misma clave, hora y valor en dos
    # estados no se puede atribuir, y se deja fuera en vez de adivinar.
    contexts: dict[tuple[str, dt.datetime, float], set[Context]] = {}
    usable: dict[tuple[str, Context], list[VitalObservation]] = {}
    for obs in observations:
        contexts.setdefault((obs.key, obs.effective, obs.value), set()).add(obs.context)
        if not obs.is_low_confidence:
            usable.setdefault((obs.key, obs.context), []).append(obs)
    # Por indicador y estado, las lecturas que el motor pudo usar, ordenadas, con sus horas.
    pools: dict[str, dict[Context, _Pool]] = {}
    for (key, state), readings in usable.items():
        readings.sort(key=lambda item: item.effective)
        pools.setdefault(key, {})[state] = ([item.effective for item in readings], readings)

    newest: dict[tuple[str, Context], Deviation] = {}
    # La hora de la última lectura de cada indicador. Dos estados con esa misma hora son, los
    # dos, «la última lectura»: elegir uno dependería del orden en que el motor agrupa.
    newest_time: dict[str, dt.datetime] = {}
    unattributed: dict[str, int] = {}
    for dev in deviations:
        if dev.key not in newest_time or dev.effective > newest_time[dev.key]:
            newest_time[dev.key] = dev.effective
        found = contexts.get((dev.key, dev.effective, dev.value), set())
        if len(found) != 1:
            unattributed[dev.key] = unattributed.get(dev.key, 0) + 1
            continue
        (state,) = found
        slot = (dev.key, state)
        if slot not in newest or dev.effective > newest[slot].effective:
            newest[slot] = dev

    indicators: list[dict[str, Any]] = []
    for key in sorted(newest_time, key=_catalog_order):
        code = get(key)
        # Del más reciente al más antiguo: el estado de la última lectura va primero.
        mine = sorted(
            ((state, dev) for (row_key, state), dev in newest.items() if row_key == key),
            key=lambda pair: pair[1].effective,
            reverse=True,
        )
        rows = [
            _state_row(dev, state, pools.get(key, {}),
                       latest=dev.effective == newest_time[key])
            for state, dev in mine
        ]
        current = [row for row in rows if row["latest"]]
        lost = unattributed.get(key, 0)
        indicators.append({
            "key": key,
            "display": code.display,
            "display_es": code.display_es,
            "domain": str(code.domain),
            "unit": code.unit,
            # Con dos estados a la misma última hora, establecida solo si lo están los dos.
            "established": all(row["established"] for row in current) if current else None,
            "reference": _reference_shown(code),
            "states": rows,
            "unattributed_readings": lost,
            "unattributed_display": (
                i18n.tr(
                    f"{display.number(lost, 0)} "
                    f"{'lectura tiene' if lost == 1 else 'lecturas tienen'} la misma hora y el "
                    f"mismo valor en dos estados: no se atribuyen a ninguno.",
                    f"{display.number(lost, 0)} "
                    f"{'reading has' if lost == 1 else 'readings have'} the same time and the "
                    f"same value in two states: they are attributed to neither.",
                )
                if lost else None
            ),
        })

    descriptive = [
        {"key": key, "display_es": get(key).display_es, "reason": i18n.loc(DESCRIPTIVE_REASON)}
        for key in sorted(set(descriptive_keys), key=_catalog_order)
    ]
    return {
        "subject": subject,
        "reference_time": reference_time.isoformat(),
        "kind": "rolling",
        "method": method(),
        "cuts_method": cuts_method(),
        "fixed_note": i18n.loc(FIXED_NOTE),
        "window_days": DEFAULT_ROLLING_WINDOW.days,
        "lag_hours": int(DEFAULT_ROLLING_LAG.total_seconds() // 3_600),
        "min_samples": MIN_SAMPLES,
        "statement": _statement(indicators, descriptive),
        "indicators": indicators,
        "descriptive": descriptive,
        "personal_data": personal_data(),
    }


def _statement(indicators: Sequence[dict[str, Any]], descriptive: Sequence[Any]) -> str:
    """Cuántas bases hay y en qué punto están, y contra qué se juzgó cada última lectura.

    Las dos cuentas importan y no son la misma: un indicador puede tener establecida la base de
    reposo y que su última lectura, de sueño, se haya juzgado sin base personal.
    """
    if not indicators:
        return i18n.tr(
            "Ningún indicador analizado: no hay línea base que enseñar.",
            "No indicator analysed: there is no baseline to show.",
        )
    rows = [row for item in indicators for row in item["states"]]
    established = sum(1 for row in rows if row["established"])
    noun = "indicador analizado" if len(indicators) == 1 else "indicadores analizados"
    bases = "base" if len(rows) == 1 else "bases"
    settled = "establecida" if established == 1 else "establecidas"
    text = i18n.tr(
        f"{display.number(len(indicators), 0)} {noun}, con {display.number(len(rows), 0)} "
        f"{bases} (una por estado): {display.number(established, 0)} {settled} y "
        f"{display.number(len(rows) - established, 0)} {LEARNING}.",
        f"{display.number(len(indicators), 0)} analysed "
        f"{'indicator' if len(indicators) == 1 else 'indicators'}, with "
        f"{display.number(len(rows), 0)} {'baseline' if len(rows) == 1 else 'baselines'} (one "
        f"per state): {display.number(established, 0)} {ESTABLISHED_EN} and "
        f"{display.number(len(rows) - established, 0)} {LEARNING_EN}.",
    )
    without = sum(1 for item in indicators if item["established"] is False)
    if without:
        text += i18n.tr(
            f" La última lectura de {display.number(without, 0)} se juzgó sin base personal "
            f"establecida.",
            f" The latest reading of {display.number(without, 0)} was judged without an "
            f"established personal baseline.",
        )
    unknown = sum(1 for item in indicators if item["established"] is None)
    if unknown:
        text += i18n.tr(
            f" De {display.number(unknown, 0)} no se puede decir el estado de su última "
            f"lectura.",
            f" For {display.number(unknown, 0)}, the state of the latest reading cannot be "
            f"told.",
        )
    # De qué están hechas (§5.37.2): solo se dice lo que se aparta de «un entorno, todo medido».
    compositions = [row["composition"] for row in rows]
    mixed = sum(1 for item in compositions if item and len(item["evidence_context"]) > 1)
    if mixed:
        text += i18n.tr(
            f" {display.number(mixed, 0)} "
            f"{'base mezcla' if mixed == 1 else 'bases mezclan'} lecturas de varios entornos de "
            f"evidencia.",
            f" {display.number(mixed, 0)} "
            f"{'baseline mixes' if mixed == 1 else 'baselines mix'} readings from several "
            f"evidence environments.",
        )
    not_measured = sum(
        1 for item in compositions
        if item and item["samples"] > item["observation_type"].get("measured", 0)
    )
    if not_measured:
        text += i18n.tr(
            f" {display.number(not_measured, 0)} "
            f"{'base incluye' if not_measured == 1 else 'bases incluyen'} valores que no son "
            f"medidas.",
            f" {display.number(not_measured, 0)} "
            f"{'baseline includes' if not_measured == 1 else 'baselines include'} values that "
            f"are not measurements.",
        )
    unknown_make = sum(1 for item in compositions if item is None)
    if unknown_make:
        text += i18n.tr(
            f" De {display.number(unknown_make, 0)} no se puede decir de qué entorno ni tipo "
            f"son sus lecturas.",
            f" For {display.number(unknown_make, 0)}, the environment and type of the readings "
            f"cannot be told.",
        )
    if descriptive:
        text += i18n.tr(
            f" {display.number(len(descriptive), 0)} descriptivos, sin línea base.",
            f" {display.number(len(descriptive), 0)} descriptive, with no baseline.",
        )
    return text
