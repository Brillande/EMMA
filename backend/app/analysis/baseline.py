"""Linea base personal y deteccion de desviacion.

Por que una linea base **personal** y no un rango de referencia poblacional:
en vuelo de larga duracion lo "normal" se desplaza. Un pulso en reposo de 70 lpm
puede ser alarmante en un tripulante cuya base era 55 y perfectamente nominal en
otro cuya base era 68. Juzgar contra una tabla terrestre genera falsas alarmas al
principio y ceguera despues, justo cuando la deriva importa.

Los rangos del catalogo (`reference_low`/`reference_high`) se usan solo como
respaldo mientras no hay base personal establecida, y como red de seguridad para
valores criticos absolutos.

Estadistica robusta: se usa mediana y MAD en vez de media y desviacion tipica.
Los datos fisiologicos de wearable traen artefactos (mal contacto, movimiento), y
un solo artefacto arrastra la media y **infla** la desviacion, con lo que el
sistema se vuelve mas ciego justo despues de un mal dato.

DOS BASES, DOS PREGUNTAS DISTINTAS
----------------------------------
`fit()` + `evaluate()` congelan una base fija. Sirve para la base **preflight**:
responde a "cuanto me he alejado de mi normalidad terrestre", que es la pregunta
de la vigilancia longitudinal de salud.

`evaluate_rolling()` usa una ventana movil de los dias previos a cada lectura.
Responde a "ha pasado algo **hoy**", que es la pregunta de la monitorizacion en
mision.

La distincion no es un detalle de implementacion. Una base congelada al inicio de
la mision se vuelve falsa a medida que la tripulacion se adapta: al segundo mes,
comparar contra la semana 1 marca como alarma cada indicador con deriva, y el
sistema pasa a gritar continuamente. Eso es fatiga de alarma, y termina con la
tripulacion ignorandolo.

La deriva lenta **no** es trabajo de este modulo: es trabajo de `trend.py`, que
esta hecho para medirla y contrastarla. Aqui se detecta lo agudo.

CONFIANZA DE MEDIDA
-------------------
Una lectura cuyo sensor declara **mal contacto con la piel** no vale lo mismo que
una tomada correctamente. Se usa de dos formas, y ambas importan:

1. **No entra en la linea base.** Una medida dudosa que contamina la referencia
   vuelve al sistema mas ciego justo despues de un mal dato — el mismo motivo por
   el que la base usa mediana y MAD en vez de media y desviacion tipica.
2. **No sostiene por si sola un hallazgo grave.** Puede ser real, asi que no se
   descarta; pero afirmar "grave" a partir de una lectura que el propio sensor
   marca como dudosa es afirmar mas de lo que se sabe.

COMPARAR ESTADOS COMPARABLES
----------------------------
La validacion externa contra MMASH demostro que una base movil sin mas **es ciega
al estado**. En 24 h de un sujeto sano el pulso recorrio 59-128 lpm —68 lpm de
amplitud circadiana— mientras la dispersion de su propia base era de 11 lpm. Una
lectura despierto contra una referencia construida mientras dormia queda a seis
sigmas por fisiologia normal, no por patologia.

Por eso `evaluate_rolling` estratifica por `Context`: reposo contra reposo, sueno
contra sueno. Sin contexto declarado el comportamiento es el de antes.
"""

from __future__ import annotations

import bisect
import datetime as dt
import functools
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from app.analysis.cycle_phase import PhaseOffset
from app.core import display, i18n
from app.ingest.codes import VitalCode, get
from app.ingest.fhir import LOW_CONFIDENCE_THRESHOLD, Context, VitalObservation

# Factor de consistencia que convierte la MAD en un estimador de la desviacion
# tipica bajo normalidad.
MAD_TO_SD = 1.4826

# Muestras minimas para considerar establecida una linea base.
#
# ESTA ACOPLADO A LO QUE EL SISTEMA PUEDE AFIRMAR. Una base se considera
# establecida exactamente cuando tiene datos para sostener la afirmacion mas
# debil que se hace con ella: el cuantil 99. Con menos, "fuera de lo que he
# visto" no es evidencia — con 30 observaciones eso ocurre en torno al 6 % de
# las veces por puro azar, y ese era justo el residuo de falsa alarma medido:
# 213 de 220 lecturas marcadas usaban una base de menos de 100 muestras, con
# mediana de 30.
#
# Ver `_SAMPLES_FOR_SEVERITY`: si se cambia uno, hay que cambiar el otro, y la
# prueba `test_established_matches_the_weakest_claim` lo comprueba.
MIN_SAMPLES = 100

# Suelo de dispersion: evita que una serie momentaneamente plana produzca
# z-scores infinitos y una cascada de alertas espurias.
MIN_SD_FRACTION = 0.01

# Ventana movil por defecto para la base en mision. Dos semanas es suficiente
# para estabilizar la estadistica y corto para seguir la adaptacion del cuerpo.
DEFAULT_ROLLING_WINDOW = dt.timedelta(days=14)

# Hueco entre una lectura y su propia base. Sin el, un episodio de varias
# horas entra en su propia referencia y se camufla a si mismo.
DEFAULT_ROLLING_LAG = dt.timedelta(hours=12)


class Severity(StrEnum):
    NONE = "none"
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


# CUANTILES EMPIRICOS EN LUGAR DE SIGMAS
#
# El z-score asume normalidad. La validacion externa demostro que la fisiologia
# no la cumple ni de lejos: |z| >= 2 deberia excederse en el 4,55 % de las
# lecturas y se excedia en el **22,02 %**. El percentil 99 real de |z| estaba en
# 12,63, asi que el umbral de "grave" (|z| = 4) caia alrededor del percentil 80.
# Subir el umbral tampoco arreglaba nada: con |z| >= 4 seguia habiendo un 7 %.
#
# Con cuantiles empiricos la tasa de falsa alarma deja de ser una consecuencia
# emergente de un supuesto falso y pasa a ser **un parametro de diseno**: si se
# marca por encima del percentil 99 de la propia base, se obtiene ~1 % por
# construccion, sea cual sea la forma de la distribucion.
#
# Ademas es interpretable sin estadistica: "esta lectura esta por encima del 99 %
# de tus ultimas dos semanas en reposo".
_QUANTILE_THRESHOLDS: tuple[tuple[float, Severity], ...] = (
    (0.999, Severity.SEVERE),
    (0.995, Severity.MODERATE),
    (0.990, Severity.MILD),
)

# LA RESOLUCION DE LA MUESTRA LIMITA LO QUE SE PUEDE AFIRMAR.
#
# Con 40 muestras, los cortes p99, p99,5 y p99,9 colapsan practicamente en el
# maximo observado: cualquier exceso saldria "grave" cuando lo unico que se puede
# decir es "por encima de todo lo que he visto, y he visto poco". Afirmar un
# percentil mas fino que 1/n es inventarse precision.
#
# Cada nivel de gravedad exige, como minimo, muestras suficientes para estimar su
# cuantil con algo de sustancia: unas diez observaciones mas alla del corte.
_SAMPLES_FOR_SEVERITY: dict[Severity, int] = {
    Severity.SEVERE: 1000,    # p99,9
    Severity.MODERATE: 200,   # p99,5
    Severity.MILD: 100,       # p99
}

# El z-score se sigue calculando: es como la gente lee una desviacion, y sirve
# para ordenar hallazgos. Pero ya no decide la gravedad.
_Z_THRESHOLDS: tuple[tuple[float, Severity], ...] = (
    (4.0, Severity.SEVERE),
    (3.0, Severity.MODERATE),
    (2.0, Severity.MILD),
)


@dataclass(frozen=True, slots=True)
class Baseline:
    """Referencia personal de un indicador."""

    key: str
    center: float
    spread: float
    samples: int
    # Valores ordenados de la ventana, para cuantiles empiricos. Vacio en las
    # bases construidas antes de que existiera esta via.
    sorted_values: tuple[float, ...] = ()

    @property
    def established(self) -> bool:
        return self.samples >= MIN_SAMPLES

    def z_score(self, value: float) -> float:
        spread = max(self.spread, abs(self.center) * MIN_SD_FRACTION, 1e-9)
        return (value - self.center) / spread

    def quantile(self, fraction: float) -> float | None:
        """Cuantil empirico por interpolacion lineal."""
        if not self.sorted_values:
            return None
        values = self.sorted_values
        if len(values) == 1:
            return values[0]
        position = fraction * (len(values) - 1)
        lower = int(position)
        upper = min(lower + 1, len(values) - 1)
        weight = position - lower
        return values[lower] * (1 - weight) + values[upper] * weight

    def percentile_of(self, value: float) -> float | None:
        """En que percentil de la propia base cae una lectura."""
        if not self.sorted_values:
            return None
        import bisect

        return bisect.bisect_left(self.sorted_values, value) / len(self.sorted_values)


class SeverityBasis(StrEnum):
    """Que decidio la gravedad de una lectura.

    Existe porque lo que se ensena a la tripulacion tiene que ser **la base real
    de la decision**. `describe()` justificaba todo con el z-score, y el z-score
    ya no decide la gravedad: medido en el escenario de arritmia, un hallazgo
    GRAVE se explicaba como "35 /min, 1,7 desviaciones por debajo de su base
    personal" cuando lo que lo hizo grave fue cruzar el limite de peligro de
    40 /min. 1,7 desviaciones no es grave para nadie; el texto contradecia la
    etiqueta que acompanaba.

    La exencion CDS del 21st Century Cures Act descansa en que quien recibe la
    recomendacion pueda **revisar independientemente su base**. Una base mostrada
    que no es la usada no es revisable: es decorado.
    """

    PERSONAL_PERCENTILE = "personal-percentile"
    DANGER_LIMIT = "danger-limit"
    LOW_CONFIDENCE = "low-confidence"


@dataclass(frozen=True, slots=True)
class Deviation:
    """Una lectura evaluada contra su linea base.

    Lleva el sujeto a proposito. EMMA vigila a una **tripulacion**, y sin esta
    atribucion nada impide que el motor de riesgo reciba lecturas de dos personas
    y las cuente como una sola. Confundir a dos tripulantes en un sistema clinico
    es de los errores que no admiten "no deberia pasar".
    """

    subject: str
    key: str
    value: float
    # EL MOMENTO DE LA LECTURA, PORQUE SIN EL NO SE PUEDE DECIR "ACTUAL".
    #
    # El estado de tripulacion seleccionaba las lecturas recientes emparejando
    # por `(clave, valor)`, que es ambiguo: una desviacion de hace semanas con el
    # mismo valor contaba como actual. Medido sobre 40 dias de escenario nominal,
    # **2582 desviaciones se daban por actuales cuando solo 1078 lecturas caian
    # en la ventana**: un inflado de 2,4x. Con pulsos enteros de un wearable real
    # es peor — 960 lecturas toman 36 valores distintos y el mas repetido sale 99
    # veces.
    #
    # Eso corrompe la persistencia, que es el control central contra la fatiga de
    # alarma: se contaminan numerador y denominador a la vez.
    effective: dt.datetime
    z_score: float
    severity: Severity
    direction: str  # "high" | "low"
    baseline: Baseline | None
    used_population_range: bool
    # Que decidio la gravedad, y el limite cruzado si fue un limite de peligro.
    # Con defecto para que una desviacion construida a mano siga siendo valida;
    # el motor los rellena siempre que la gravedad no es NONE.
    basis: SeverityBasis | None = None
    danger_limit: float | None = None

    @property
    def is_concerning(self) -> bool:
        return self.severity is not Severity.NONE

    def describe(self) -> str:
        """Explica la lectura con la base que **de verdad** decidio su gravedad."""
        if i18n.current() == "en":
            return self._describe_en()
        code = get(self.key)
        if not self.is_concerning:
            return f"{code.display_es}: dentro de lo esperado"
        sense = "por encima" if self.direction == "high" else "por debajo"
        head = f"{code.display_es}: {display.quantity(self.key, self.value, code.unit)}, "

        if self.basis is SeverityBasis.DANGER_LIMIT and self.danger_limit is not None:
            limit = display.quantity(self.key, self.danger_limit, code.unit)
            return head + f"{sense} del límite de peligro ({limit})"

        if (
            self.basis is SeverityBasis.PERSONAL_PERCENTILE
            and self.baseline is not None
            and self.baseline.sorted_values
        ):
            reference = self.baseline.sorted_values
            if self.direction == "high":
                beyond = bisect.bisect_left(reference, self.value) / len(reference)
            else:
                beyond = 1.0 - bisect.bisect_right(reference, self.value) / len(reference)
            return head + (
                f"{sense} del {display.percent(beyond)} de sus propias lecturas de referencia "
                f"({display.number(len(reference), 0)} lecturas)"
            )

        if self.basis is SeverityBasis.LOW_CONFIDENCE:
            where = (
                f"{sense} del límite de peligro "
                f"({display.quantity(self.key, self.danger_limit, code.unit)})"
                if self.danger_limit is not None
                else f"{sense} de su base personal"
            )
            return head + (
                f"{where}, pero con baja confianza de medida: no se afirma más que un "
                f"hallazgo leve hasta que lo confirmen lecturas con buen contacto"
            )

        reference_name = (
            "el rango poblacional" if self.used_population_range else "su base personal"
        )
        return head + (
            f"{display.number(abs(self.z_score), 1)} desviaciones {sense} de {reference_name}"
        )

    def _describe_en(self) -> str:
        """`describe` en inglés (`core/i18n.py`): las mismas ramas, en el mismo orden, y la misma
        afirmación en cada una. Va entera y no por trozos porque la frase inglesa se ordena de
        otra forma; el castellano de arriba no se toca.
        """
        code = get(self.key)
        name = code.display_es
        if not self.is_concerning:
            return f"{name}: within what is expected"
        sense = "above" if self.direction == "high" else "below"
        reading = display.quantity(self.key, self.value, code.unit)
        start = f"{name}: {reading}, "

        if self.basis is SeverityBasis.DANGER_LIMIT and self.danger_limit is not None:
            limit = display.quantity(self.key, self.danger_limit, code.unit)
            return start + f"{sense} the danger limit ({limit})"

        if (
            self.basis is SeverityBasis.PERSONAL_PERCENTILE
            and self.baseline is not None
            and self.baseline.sorted_values
        ):
            reference = self.baseline.sorted_values
            if self.direction == "high":
                beyond = bisect.bisect_left(reference, self.value) / len(reference)
            else:
                beyond = 1.0 - bisect.bisect_right(reference, self.value) / len(reference)
            return start + (
                f"{sense} {display.percent(beyond)} of their own reference readings "
                f"({display.number(len(reference), 0)} readings)"
            )

        if self.basis is SeverityBasis.LOW_CONFIDENCE:
            where = (
                f"{sense} the danger limit "
                f"({display.quantity(self.key, self.danger_limit, code.unit)})"
                if self.danger_limit is not None
                else f"{sense} their personal baseline"
            )
            return start + (
                f"{where}, but with low measurement confidence: no more than a mild finding is "
                f"stated until readings with good contact support it"
            )

        against = (
            "the population range" if self.used_population_range else "their personal baseline"
        )
        return start + f"{display.number(abs(self.z_score), 1)} deviations {sense} {against}"


def _severity_for(z_score: float, code: VitalCode) -> tuple[Severity, str]:
    direction: Side = "high" if z_score >= 0 else "low"

    # Un indicador solo preocupa en la direccion que tiene sentido clinico: que
    # la saturacion de oxigeno suba no es un hallazgo. La misma regla que el percentil.
    if not watches(code, direction):
        return Severity.NONE, direction

    magnitude = abs(z_score)
    for threshold, severity in _Z_THRESHOLDS:
        if magnitude >= threshold:
            return severity, direction
    return Severity.NONE, direction


def exceeds_danger_limit(observation: VitalObservation) -> bool:
    """Si la lectura cruza un umbral de peligro fisiologico absoluto.

    SE COMPRUEBA SIEMPRE, TENGA O NO LINEA BASE PERSONAL.
    ------------------------------------------------------
    Antes solo se miraba en el respaldo poblacional, asi que en cuanto el sistema
    conocia al tripulante dejaba de vigilar los umbrales de peligro. El fallo se
    vio en el escenario de evento solar: 35 lecturas de dosis por encima del
    limite —pico de 1668 uGy/h contra un limite de 100— y **ningun hallazgo**,
    porque la via de cuantiles las graduaba por debajo de grave y la persistencia
    las descartaba.

    Un valor absolutamente peligroso lo es sea cual sea tu normalidad. La linea
    base personal sirve para detectar lo que es anormal **para ti**; no para
    rebajar lo que es peligroso para cualquiera.
    """
    return crossed_danger_limit(observation) is not None


def crossed_danger_limit(observation: VitalObservation) -> float | None:
    """El limite de peligro que cruza la lectura, o None si no cruza ninguno.

    El limite depende del estado: 145 lpm corriendo es normal, en reposo no. Un
    estado desconocido se trata como NO reposo, que es lo conservador frente a
    la falsa alarma. "Reposo" significa sin esfuerzo fisico, no inmovilidad.
    """
    code = get(observation.key)
    at_rest = observation.context.family in {Context.REST, Context.SLEEP}
    exerting = observation.context is Context.ACTIVE
    low, high = code.critical_bounds(at_rest, exerting)

    if low is not None and observation.value < low:
        return low
    if high is not None and observation.value > high:
        return high
    return None


def _grade_against_personal(
    observation: VitalObservation, baseline: Baseline, code: VitalCode
) -> tuple[Severity, str, SeverityBasis | None, float | None]:
    """Gravedad de una lectura frente a su base personal, y que la decidio.

    UNA SOLA GRADUACION PARA LOS DOS CAMINOS.
    -----------------------------------------
    `evaluate()` y `evaluate_rolling()` graduaban por separado, y solo el segundo
    aplicaba el tope por baja confianza y la red de peligro absoluto. El primero
    —publico— se saltaba ambas, contradiciendo el "se comprueba siempre" de
    `exceeds_danger_limit`. Produccion solo usa el segundo, asi que no fallaba
    nada todavia; era una trampa esperando a su primer uso.
    """
    severity, direction = _severity_from_quantiles(observation.value, baseline, code)
    basis = SeverityBasis.PERSONAL_PERCENTILE if severity is not Severity.NONE else None

    # La red de peligro absoluto no depende de conocer al sujeto.
    limit = crossed_danger_limit(observation)
    if limit is not None:
        severity, basis = Severity.SEVERE, SeverityBasis.DANGER_LIMIT
        direction = "high" if observation.value > limit else "low"

    severity, basis = _apply_confidence(observation, severity, basis)
    return severity, direction, basis, limit


def _apply_confidence(
    observation: VitalObservation, severity: Severity, basis: SeverityBasis | None
) -> tuple[Severity, SeverityBasis | None]:
    """El tope por baja confianza, aplicado el ULTIMO, tambien a limites de peligro.

    Antes la red de peligro se imponia al tope: el tope se aplicaba y despues un
    cruce de limite devolvia la lectura a GRAVE, y la via poblacional ni siquiera
    miraba la confianza. Una trama BLE sin contacto de sensor que marcase 30 lpm
    salia como hallazgo grave. Es exactamente el caso en que el valor es menos
    fiable: con el sensor suelto la cifra no es fisiologia.

    Las dos reglas no se contradicen si se leen bien. "Un valor peligroso lo es
    sea cual sea tu normalidad" habla de la **normalidad del sujeto**, no de la
    **calidad de la medida**. Que la lectura sea mala no rebaja el peligro de un
    valor real: pone en duda que el valor sea real.

    No se descarta: queda como hallazgo leve, conserva el limite cruzado y el
    texto dice por que no se afirma mas. Y como los artefactos de contacto llegan
    en rachas, esto no puede delegarse en la regla de rafaga: una racha de
    lecturas sin contacto es una racha, pero no es evidencia fisiologica.

    Ninguna fuente de validacion —MMASH, simulador, inyeccion— produce lecturas
    de baja confianza, asi que esto no mueve ninguna cifra publicada. Tampoco
    esta validado mas alla de las pruebas unitarias, y se declara.
    """
    if severity is Severity.NONE or not observation.is_low_confidence:
        return severity, basis
    return cap_for_confidence(severity, observation.confidence), SeverityBasis.LOW_CONFIDENCE


def cap_for_confidence(severity: Severity, confidence: float) -> Severity:
    """Una lectura dudosa no puede sostener por si sola un hallazgo grave.

    No se descarta —podria ser real— pero se rebaja a leve: es lo que la calidad
    de la medida permite afirmar. Si el problema es de verdad, las lecturas
    siguientes con buen contacto lo confirmaran.
    """
    if confidence >= LOW_CONFIDENCE_THRESHOLD or severity is Severity.NONE:
        return severity
    return Severity.MILD


def _severity_from_quantiles(
    value: float, baseline: Baseline, code: VitalCode
) -> tuple[Severity, str]:
    """Gravedad segun donde cae la lectura en la distribucion real del sujeto."""
    direction = "high" if value >= baseline.center else "low"
    crossed = crossed_personal_cut(value, baseline, code)
    # Antes habia aqui un respaldo: con pocas muestras, salirse del rango
    # observado se reportaba como leve. **Se quito**: con 30 observaciones eso
    # pasa ~6 % de las veces por azar, y era el grueso del residuo de falsa
    # alarma. Una base que no llega a MIN_SAMPLES ya no se considera establecida,
    # asi que este camino no deberia alcanzarse.
    return (crossed.severity if crossed is not None else Severity.NONE), direction


@dataclass(frozen=True, slots=True)
class PersonalCut:
    """El corte de la propia base que cruza una lectura: en que cuantil esta y cuanto vale.

    `quantile` es la fraccion de la distribucion por debajo del corte: 0,99 para el percentil 99
    por arriba, 0,01 para el percentil 1 por abajo. `value` va en la unidad del indicador.
    """

    quantile: float
    value: float
    severity: Severity


# --- Los cortes de una base: una sola funcion para el motor y para el perfil -------------------
#
# POR QUE ESTA AQUI Y NO EN CADA LECTOR (decimoctava ronda, §5.38.11)
# El perfil de linea base (`baseline_profile`) ensenaba los cortes repitiendo la regla de lados y
# minimos de `crossed_personal_cut`: el cuantil `fraction` por arriba y `1 - fraction` por abajo,
# solo por el lado que preocupa y solo si la base tiene las lecturas que esa gravedad pide. Dos
# copias de una regla acaban diciendo cosas distintas, y una prueba que las contrasta solo cubre
# los casos que alguien penso. Ahora la regla esta una vez: `personal_cuts` dice que cortes tiene
# una base, de que lado, cuales sostiene con sus lecturas y cuanto valen; el motor gradua con ella
# y el perfil la describe con ella.

# Un lado de la distribucion: por encima («high») o por debajo («low») de la mediana.
Side = Literal["high", "low"]
SIDES: tuple[Side, Side] = ("high", "low")


@dataclass(frozen=True, slots=True)
class CutRule:
    """Un nivel de corte, sin base: su gravedad, su cuantil por arriba y las lecturas que pide."""

    severity: Severity
    # Cuantil por arriba (0,99 para leve); por abajo se corta en `1 - fraction`.
    fraction: float
    min_samples: int

    def quantile(self, side: Side) -> float:
        """El cuantil del corte por ese lado."""
        return self.fraction if side == "high" else 1.0 - self.fraction


@functools.cache
def cut_rules() -> tuple[CutRule, ...]:
    """Los niveles de corte del motor, del mas exigente al menos: el orden en que se buscan.

    Se construye una vez: el motor la pide en cada lectura y las tablas no cambian.
    """
    return tuple(
        CutRule(severity=severity, fraction=fraction, min_samples=_SAMPLES_FOR_SEVERITY[severity])
        for fraction, severity in _QUANTILE_THRESHOLDS
    )


def watches(code: VitalCode, side: Side) -> bool:
    """Si el percentil avisa por ese lado: solo por el que preocupa (`VitalCode.concerning`).

    El limite de peligro se mira por los dos lados; esto es solo la base personal.
    """
    return code.concerning in {side, "both"}


@dataclass(frozen=True, slots=True)
class BaseCut:
    """Un nivel de corte sobre una base concreta.

    Cada motivo para no tener cifra va en su campo, sin deducirlo de un `None`:
    `supported` (la base tiene las lecturas que pide esa gravedad), `has_values` (la base guarda
    sus valores; sin ellos no hay cuantil) y `watches` (si ese lado preocupa). `high` y `low` son
    el corte por cada lado en la unidad del indicador, solo cuando los tres se cumplen y ese lado
    se pidio.
    """

    rule: CutRule
    supported: bool
    has_values: bool
    high: float | None
    low: float | None

    def on(self, side: Side) -> float | None:
        """El corte por ese lado."""
        return self.high if side == "high" else self.low


def personal_cuts(
    baseline: Baseline, code: VitalCode, sides: Sequence[Side] = SIDES
) -> tuple[BaseCut, ...]:
    """Los cortes de percentil de una base, del mas exigente al menos.

    ES LA REGLA, NO UNA COPIA: `crossed_personal_cut` (con la que gradua el motor y lee el detalle
    de una alerta) y el perfil de linea base salen de aqui. `sides` limita los lados que se
    calculan: el motor, que ya sabe hacia donde cae la lectura, pide solo ese; los cuantiles del
    otro lado no los necesita y se calculan en cada lectura.
    """
    has_values = bool(baseline.sorted_values)
    cuts = []
    for rule in cut_rules():
        # No afirmar una gravedad que la muestra no puede sostener.
        supported = baseline.samples >= rule.min_samples
        values: dict[Side, float | None] = {
            side: (
                baseline.quantile(rule.quantile(side))
                if side in sides and supported and has_values and watches(code, side) else None
            )
            for side in SIDES
        }
        cuts.append(BaseCut(
            rule=rule, supported=supported, has_values=has_values,
            high=values["high"], low=values["low"],
        ))
    return tuple(cuts)


def crossed_personal_cut(
    value: float, baseline: Baseline, code: VitalCode
) -> PersonalCut | None:
    """El corte mas exigente de la propia base que la lectura cruza, o `None` si no cruza ninguno.

    ES LA REGLA, NO UNA COPIA. `_severity_from_quantiles` gradua con esto, y el detalle de una
    alerta lo lee para decir que corte cruzo cada lectura (percentil y valor). Si el detalle
    recalculara el corte por su cuenta, podria ensenar uno distinto del que decidio. Los cortes
    salen de `personal_cuts`, los mismos que ensena el perfil de linea base.
    """
    direction: Side = "high" if value >= baseline.center else "low"
    if not watches(code, direction):
        return None

    for cut in personal_cuts(baseline, code, sides=(direction,)):
        if not cut.supported:
            continue
        if not cut.has_values:
            break
        threshold = cut.on(direction)
        if threshold is None:
            # No pasa (sostenida, con valores y por el lado que preocupa), pero sin `assert`:
            # con `python -O` desapareceria y la comparacion con `None` romperia la lectura.
            continue
        if (direction == "high" and value > threshold) or (
            direction == "low" and value < threshold
        ):
            return PersonalCut(
                quantile=cut.rule.quantile(direction), value=threshold, severity=cut.rule.severity
            )
    return None


def compute_baseline(key: str, values: Sequence[float]) -> Baseline:
    """Calcula la linea base robusta de una serie."""
    if not values:
        return Baseline(key=key, center=0.0, spread=0.0, samples=0)

    # Una sola ordenacion de la ventana: `statistics.median` ordenaba otra vez lo mismo que
    # luego guardan los cuantiles. Ordenar una lista ya ordenada es lineal, y la mediana sale
    # de la misma funcion: el mismo valor, bit a bit (`evaluate_rolling` la llama por lectura).
    ordered = sorted(values)
    center = statistics.median(ordered)
    absolute_deviations = [abs(value - center) for value in values]
    spread = statistics.median(absolute_deviations) * MAD_TO_SD

    return Baseline(
        key=key,
        center=center,
        spread=spread,
        samples=len(values),
        sorted_values=tuple(ordered),
    )


def _confident_values(series: Sequence[VitalObservation]) -> list[float | None]:
    """El valor de cada lectura, o `None` si es dudosa: lo que entra en una referencia."""
    return [None if obs.is_low_confidence else obs.value for obs in series]


def _phase_free(
    series: Sequence[VitalObservation], phase_offset: PhaseOffset | None
) -> list[float | None]:
    """Como `_confident_values`, sin lo que la fase del ciclo desplaza cada lectura.

    Sin `phase_offset`, exactamente `_confident_values`: la serie de siempre, bit a bit.
    """
    values = _confident_values(series)
    if phase_offset is None:
        return values
    return [
        None if value is None else value - phase_offset(obs.key, obs.effective)
        for obs, value in zip(series, values, strict=True)
    ]


class BaselineEngine:
    """Mantiene lineas base por tripulante e indicador."""

    def __init__(self) -> None:
        # Sin `min_samples`: el constructor lo aceptaba y lo guardaba, pero nadie lo leía —
        # `Baseline.established` mira `MIN_SAMPLES`, acoplado a `_SAMPLES_FOR_SEVERITY`—. Un
        # `BaselineEngine(min_samples=30)` se aceptaba en silencio y seguía exigiendo 100.
        self._baselines: dict[tuple[str, str], Baseline] = {}

    def fit(self, observations: Iterable[VitalObservation]) -> dict[tuple[str, str], Baseline]:
        """Aprende las lineas base a partir de un periodo de referencia."""
        grouped: dict[tuple[str, str], list[float]] = {}
        for obs in observations:
            grouped.setdefault((obs.subject, obs.key), []).append(obs.value)

        for (subject, key), values in grouped.items():
            self._baselines[(subject, key)] = compute_baseline(key, values)
        return dict(self._baselines)

    def get(self, subject: str, key: str) -> Baseline | None:
        return self._baselines.get((subject, key))

    def evaluate(self, observation: VitalObservation) -> Deviation:
        """Evalua una lectura contra la base personal, o contra el rango poblacional."""
        code = get(observation.key)
        baseline = self.get(observation.subject, observation.key)

        if baseline is not None and baseline.established:
            severity, direction, basis, limit = _grade_against_personal(
                observation, baseline, code
            )
            return Deviation(
                subject=observation.subject,
                key=observation.key,
                value=observation.value,
                effective=observation.effective,
                z_score=baseline.z_score(observation.value),
                severity=severity,
                direction=direction,
                baseline=baseline,
                used_population_range=False,
                basis=basis,
                danger_limit=limit,
            )

        return self._evaluate_against_population(observation, code, baseline)

    def _evaluate_against_population(
        self, observation: VitalObservation, code: VitalCode, baseline: Baseline | None
    ) -> Deviation:
        """Respaldo mientras no hay base personal: el rango del catalogo.

        Se traduce la distancia fuera del rango a un z-score equivalente para que
        el resto del sistema no tenga que distinguir el origen.
        """
        low, high = code.reference_low, code.reference_high
        direction = "high"
        z_score = 0.0

        if low is not None and high is not None:
            span = max((high - low) / 4.0, 1e-9)
            center = (high + low) / 2.0
            z_score = (observation.value - center) / span
            direction = "high" if z_score >= 0 else "low"

        # SIN BASE PERSONAL, SOLO SE AVISA DE PELIGRO ABSOLUTO.
        #
        # Antes se marcaba a 2 sigmas de un punto medio poblacional, y eso
        # generaba el 58 % de todas las falsas alarmas de la validacion externa:
        # 1497 de 1831 hallazgos leves venian de esta via. Comparar a alguien que
        # no conoces contra el centro de una tabla es estadistica, no medicina.
        #
        # La regla pasa a ser: mientras no haya linea base personal, solo se
        # avisa si el valor esta fuera de los limites de peligro fisiologico.
        # El limite depende del estado: 145 lpm corriendo es normal, en reposo no.
        # Un estado desconocido se trata como NO reposo, que es lo conservador
        # frente a la falsa alarma: no se puede afirmar que alguien estaba quieto.
        #
        # "Reposo" aqui significa **sin esfuerzo fisico**, no inmovilidad: trabajo
        # de escritorio y comida son no-exertivos. Al anadir WORK y MEAL se
        # quedaron fuera de este conjunto por descuido, y la deteccion del
        # episodio agudo cayo del 90 % al 20 % porque esas lecturas pasaban a
        # juzgarse con el limite de esfuerzo (150 lpm) en vez del de reposo (110).
        severity = Severity.NONE
        basis: SeverityBasis | None = None
        limit = crossed_danger_limit(observation)
        if limit is not None:
            severity, basis = Severity.SEVERE, SeverityBasis.DANGER_LIMIT
            direction = "high" if observation.value > limit else "low"
        severity, basis = _apply_confidence(observation, severity, basis)

        return Deviation(
            subject=observation.subject,
            key=observation.key,
            value=observation.value,
            effective=observation.effective,
            z_score=z_score,
            severity=severity,
            direction=direction,
            baseline=baseline,
            used_population_range=True,
            basis=basis,
            danger_limit=limit,
        )

    def evaluate_all(self, observations: Iterable[VitalObservation]) -> list[Deviation]:
        return [self.evaluate(obs) for obs in observations]

    def evaluate_rolling(
        self,
        observations: Iterable[VitalObservation],
        window: dt.timedelta = DEFAULT_ROLLING_WINDOW,
        lag: dt.timedelta = DEFAULT_ROLLING_LAG,
        stratify_by_context: bool = True,
        phase_offset: PhaseOffset | None = None,
    ) -> list[Deviation]:
        """Evalua cada lectura contra la ventana movil que la precede.

        `lag` separa la lectura de su propia base: sin ese hueco, un episodio que
        dura varias horas se incorpora a su propia referencia y se camufla solo.

        Las lecturas que no tienen ventana previa suficiente se evaluan contra el
        rango poblacional, que es lo honesto al principio de la mision.

        `phase_offset` (`analysis/cycle_phase.py`, lote «ciclo») es cuanto desplaza la fase
        del ciclo cada clave en cada instante. Sin el, todo es como siempre. Con el, cada
        lectura de la ventana se lleva a la fase de la lectura que se juzga (se le resta su
        desplazamiento y se le suma el de la juzgada): la base se mueve, la lectura no. Asi
        el limite de peligro absoluto y el rango poblacional siguen viendo el valor medido, y
        la base que se enseña esta en las unidades de la lectura.
        """
        # Dos agrupaciones: el estado exacto y su familia. La base se toma del
        # estado exacto si tiene datos suficientes, y si no de la familia, antes
        # de caer al rango poblacional. Asi el detalle no fragmenta la muestra.
        grouped: dict[tuple[str, str, Context], list[VitalObservation]] = {}
        families: dict[tuple[str, str, Context], list[VitalObservation]] = {}
        for obs in observations:
            state = obs.context if stratify_by_context else Context.UNKNOWN
            grouped.setdefault((obs.subject, obs.key, state), []).append(obs)
            if stratify_by_context and obs.context.family is not obs.context:
                families.setdefault(
                    (obs.subject, obs.key, obs.context.family), []
                ).append(obs)

        for series in families.values():
            series.sort(key=lambda item: item.effective)
        # Lo que cada ventana necesita de una serie, calculado una vez y no por lectura:
        # los instantes (la familia ordenada se corta por biseccion en vez de recorrerla
        # entera) y el valor, o `None` si la lectura es dudosa. Las mismas lecturas, en el
        # mismo orden, que el filtro de antes.
        family_times = {
            group: [item.effective for item in series] for group, series in families.items()
        }
        family_values = {
            group: _phase_free(series, phase_offset) for group, series in families.items()
        }

        results: list[Deviation] = []

        for (subject, key, state), series in grouped.items():
            series.sort(key=lambda obs: obs.effective)
            times = [obs.effective for obs in series]
            confident = _phase_free(series, phase_offset)
            code = get(key)

            # Dos punteros sobre la serie ordenada: evita recorrerla entera por
            # cada lectura.
            start_index = 0
            end_index = 0

            for position, obs in enumerate(series):
                window_end = obs.effective - lag
                window_start = window_end - window

                while start_index < position and times[start_index] < window_start:
                    start_index += 1
                while end_index < position and times[end_index] <= window_end:
                    end_index += 1

                # La fase de la lectura que se juzga: la ventana, sin fase, se lleva a la suya.
                shift = phase_offset(key, obs.effective) if phase_offset is not None else 0.0

                # Una lectura dudosa no debe contaminar la referencia.
                values = [
                    value + shift
                    for value in confident[start_index:end_index] if value is not None
                ]
                baseline = compute_baseline(key, values)

                # Si el estado exacto no da para una base, usar su familia.
                if not baseline.established and stratify_by_context:
                    group = (subject, key, state.family)
                    relative_times = family_times.get(group)
                    if relative_times:
                        low = bisect.bisect_left(relative_times, window_start)
                        high = bisect.bisect_right(relative_times, window_end)
                        wider = [
                            value + shift
                            for value in family_values[group][low:high]
                            if value is not None
                        ]
                        if len(wider) > len(values):
                            baseline = compute_baseline(key, wider)

                if baseline.established:
                    severity, direction, basis, limit = _grade_against_personal(
                        obs, baseline, code
                    )
                    results.append(
                        Deviation(
                            subject=obs.subject,
                            key=key, value=obs.value, effective=obs.effective,
                            z_score=baseline.z_score(obs.value), severity=severity,
                            direction=direction, baseline=baseline,
                            used_population_range=False,
                            basis=basis, danger_limit=limit,
                        )
                    )
                else:
                    results.append(
                        self._evaluate_against_population(obs, code, baseline)
                    )

        return results
