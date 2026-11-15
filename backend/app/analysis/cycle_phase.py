"""La fase del ciclo menstrual como desplazamiento de la línea base, no como estrato.

POR QUÉ EXISTE
--------------
Una tripulante con ciclo regular pasa cada mes unas dos semanas con la temperatura y el pulso en
reposo desplazados hacia arriba (fase lútea). Medido con el motor sin tocar (lote «ciclo», A5,
hallazgo 32 de `compliance/external-validation.md`): una tripulante sana simulada pasaba de 12 a
63-71 evaluaciones en WATCH de 84, y la causa era la TENDENCIA —el escalón lúteo, visto por una
recta de 21 días, parece una deriva—, no la lectura suelta. Y el ciclo tapaba la fiebre: el
estado ya estaba en WATCH por la molestia y la febrícula lútea no lo subía.

POR QUÉ UN DESPLAZAMIENTO Y NO UNA BASE POR FASE
------------------------------------------------
Estratificar de más ya hundió la detección del 90 % al 20 % (`ingest/fhir.py`, la familia de
contextos): cada estrato se queda con menos lecturas y deja de ser una base establecida. Aquí no
se parte la ventana: a cada lectura se le resta lo que su fase documentada desplaza el indicador,
y la base de cada lectura se lleva a la fase de la lectura que se juzga. La ventana conserva todas
sus lecturas, y la tendencia ajusta la recta sobre la serie sin el escalón.

CUÁNTO DESCONTAR: LO PROPIO, DENTRO DE LO LEÍDO
-----------------------------------------------
Solo donde lo leído da cifra (`evidence/cycle_physiology.py`, magnitud documentada) y solo en la
fase lútea: temperatura +0,23 a +0,7 °C, pulso +3,42 a +3,91 lpm. Descontar más de lo que la fase
sube taparía una fiebre o una taquicardia real (peligro H1 de `compliance/risk-management-file.md`);
descontar de menos deja falsa alarma, que es el fallo seguro.

Primero se probó el **extremo menor** del rango, igual para todas. Medido con las dos métricas
(`tests/test_cycle_nuisance.py`): con una subida real de 0,3 °C bajaba la falsa alarma de 63 a 26 de
84, pero con 0,5 y 0,7 °C casi no la movía (71 → 61, 75 → 72): lo que queda sin descontar sigue
siendo un escalón que la recta de 21 días ve. Por eso la subida es **la de la propia tripulante**,
medida en sus ciclos ya cerrados y **acotada al rango leído**: la mediana de sus lecturas de los
últimos 7 días antes de cada regla menos la folicular interpolada a su fecha entre la de antes de
los últimos 17 días (los extremos del intervalo de la fase lútea de Bull) y la de los 7 primeros
días del ciclo siguiente, dentro de cada familia de contexto. La interpolación cancela una deriva
lenta y real, que si no se leería como subida lútea y se descontaría. Sin un ciclo cerrado con
lecturas suficientes, el extremo menor. La subida de un ciclo sale solo de ciclos ANTERIORES: una
fiebre del ciclo en curso no puede descontarse a sí misma, y lo más que una enfermedad de un ciclo
pasado puede inflar el descuento es hasta el extremo mayor de lo leído.

La RMSSD y la SDNN bajan en la lútea, pero lo leído solo da el sentido, sin cifra: no se ajustan, y
se dice. El pulso en la menstruación (+1,36 lpm) sale de un solo estudio con autores de la empresa
de la pulsera y su fase necesitaría una duración de la regla que no se ha leído: tampoco se ajusta.

DÓNDE ESTÁ LA FASE LÚTEA (Bull et al. 2019, `bull-2019-menstrual-cycle-characteristics`)
--------------------------------------------------------------------------------------
612.613 ciclos ovulatorios: «mean luteal phase length was 12.4 days (95% CI: 7–17)», y varía
menos que la folicular. La lútea se cuenta hacia atrás desde la regla siguiente. Como la regla
siguiente aún no ha llegado, se estima con los ciclos recientes de la propia tripulante, y el
ajuste se aplica solo en los días que serían lúteos con **cualquiera** de esas longitudes: desde
«último inicio + ciclo reciente más largo − 12,4 días» hasta «último inicio + ciclo reciente más
corto». Si los ciclos recientes difieren tanto que esa franja no existe, no hay ajuste: un ciclo
irregular no se sitúa. Cuando la regla se retrasa más allá del ciclo reciente más corto (ciclo
atípico: anovulación, estrés, embarazo, lo que sea), no hay ajuste hasta el inicio siguiente.

CUÁNTOS INICIOS (diseño de EMMA, declarado)
-------------------------------------------
Tres inicios de regla, es decir, dos ciclos completos. Con un solo inicio haría falta una longitud
por defecto (la media poblacional de Bull, 29,3 días, con desviación típica de 5,2): una población,
no esta persona, y con eso la franja lútea podría caer en la folicular. Con dos inicios, un único
ciclo no deja ver si es el habitual. Con tres, la franja ya sale de dos longitudes propias y se
estrecha sola si discrepan. Se usan los tres ciclos más recientes como mucho: la longitud cambia
con los años y un ciclo raro de hace meses no debe cerrar el ajuste para siempre.

CAUSAL
------
La fase de cada instante sale solo de los inicios registrados hasta ese instante: el ajuste de
una lectura pasada es el que habría tenido en directo, y la historia recalculada no cambia porque
llegue un inicio nuevo.

LO QUE ESTE MÓDULO NO SABE
--------------------------
No lee el sexo ni el estado reproductivo de nadie (`test_no_rule_of_emma_reads_sex_or_age`): la
puerta que decide si una tripulante tiene un ciclo que ajustar vive en `api/cycle_phase.py`. Aquí
llegan solo los instantes de inicio de regla. Tampoco toca los límites de peligro absolutos ni el
rango poblacional: el desplazamiento solo mueve la base personal y la tendencia.
"""

from __future__ import annotations

import bisect
import datetime as dt
import statistics
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from app.core import i18n
from app.evidence import cycle_physiology
from app.ingest.fhir import Context, VitalObservation

# Lo que recibe el motor: cuánto desplaza la fase la clave en ese instante (0 si nada).
PhaseOffset = Callable[[str, dt.datetime], float]

# La fase que se ajusta, y la de referencia de lo leído.
ADJUSTED_PHASE = "luteal"
REFERENCE_PHASE = cycle_physiology.REFERENCE_PHASE

# Duración media de la fase lútea (Bull et al. 2019, resumen leído el 2026-11-15 en PMC6710244).
LUTEAL_DAYS = 12.4
PHASE_REFS: tuple[str, ...] = ("bull-2019-menstrual-cycle-characteristics",)

# Inicios de regla necesarios para situar la fase, y ciclos recientes que cuentan (diseño de EMMA,
# ver arriba).
MIN_STARTS = 3
RECENT_CYCLES = 3

# El valor de `menstruation-start` que marca un inicio (`ingest/codes.py`): exactamente 1.
START_MARK = 1.0

# Para medir la subida propia en un ciclo cerrado (ver «CUÁNTO DESCONTAR»): los extremos del
# intervalo de la fase lútea de Bull 2019 («95% CI: 7–17»). Los últimos 7 días antes de la regla
# son lúteos casi en cualquier ciclo; lo anterior a los últimos 17, folicular.
LUTEAL_CORE_DAYS = 7.0
LUTEAL_MAX_DAYS = 17.0
# Y los primeros días del ciclo siguiente, folicular de después: con la de antes, la folicular
# se interpola a la fecha de la lútea y una deriva lenta no se toma por subida (diseño de EMMA).
AFTER_DAYS = 7.0
# Lecturas mínimas de cada lado, por familia de contexto, para comparar medianas (diseño de EMMA).
MIN_PHASE_READINGS = 10


def _conservative(found: cycle_physiology.Amplitude) -> float:
    """El extremo del rango leído más cercano a cero, con su signo; 0 sin cifra."""
    if found.evidence != "established" or found.low is None or found.high is None:
        return 0.0
    return min(found.low, found.high, key=abs)


def _luteal_offsets() -> dict[str, float]:
    offsets = {}
    searched = cycle_physiology.keys()
    for key in searched:
        value = _conservative(cycle_physiology.amplitude(key, ADJUSTED_PHASE))
        if value:
            offsets[key] = value
    return offsets


# Lo que se descuenta en la fase lútea sin ciclo cerrado propio, por clave: el extremo menor de lo
# leído (hoy: temperatura 0,23 °C y pulso 3,42 lpm). Se calcula al importar desde lo leído: cambiar
# lo leído cambia la huella de las reglas.
LUTEAL_OFFSETS: dict[str, float] = _luteal_offsets()


def _luteal_ranges() -> dict[str, tuple[float, float]]:
    ranges = {}
    for key in LUTEAL_OFFSETS:
        found = cycle_physiology.amplitude(key, ADJUSTED_PHASE)
        if found.low is not None and found.high is not None:
            ranges[key] = (
                min(abs(found.low), abs(found.high)), max(abs(found.low), abs(found.high))
            )
    return ranges


# El rango leído de cada subida, en valor absoluto: la propia se acota a él (hoy: temperatura
# 0,23-0,7 °C, pulso 3,42-3,91 lpm).
LUTEAL_RANGES: dict[str, tuple[float, float]] = _luteal_ranges()

# Las claves cuya variación por fase se buscó (`evidence/cycle_physiology.py`).
_SEARCHED: tuple[str, ...] = cycle_physiology.keys()
# Las que no se ajustan: su fase lútea solo tiene sentido documentado, sin cifra.
UNADJUSTED_KEYS: tuple[str, ...] = tuple(
    key for key in _SEARCHED if key not in LUTEAL_OFFSETS
)


@dataclass(frozen=True, slots=True)
class PhaseAt:
    """La fase en un instante: `phase` es «follicular», «luteal» o `None` si no se sitúa.

    `reason` es la clave fija del motivo (`REASONS`); `cycle_day` y `cycle_days` (la mediana de los
    ciclos recientes) se dan cuando hay inicios suficientes.
    """

    phase: str | None
    reason: str
    cycle_day: float | None = None
    cycle_days: float | None = None


# Por qué la fase es la que es, o por qué no se sitúa. Frases fijas: las enseña la consola tal cual.
REASONS: dict[str, str] = {
    "too_few_starts": (
        f"faltan inicios de regla: hacen falta {MIN_STARTS} (dos ciclos completos) para "
        "situar la fase"
    ),
    "irregular": (
        "los ciclos recientes difieren demasiado para situar la fase lútea en ningún día con "
        "seguridad"
    ),
    "overdue": (
        "la regla esperada no ha llegado (ciclo atípico): sin ajuste hasta el inicio siguiente"
    ),
    "uncertain": (
        "día del ciclo que puede ser folicular o lúteo según la longitud del ciclo: sin ajuste"
    ),
    "follicular": "fase folicular: es la referencia, no hay nada que descontar",
    "luteal": "fase lútea: se descuenta lo que la fase sube según lo leído",
}
# El inglés de cada motivo (`core/i18n.py`); quien lo sirve (`api/cycle_phase.py`) lo resuelve con
# `i18n.loc`. Las claves («irregular», «overdue»…) son identificadores y no se traducen.
i18n.en_many({
    REASONS["too_few_starts"]: (
        f"period starts are missing: {MIN_STARTS} are needed (two complete cycles) to place "
        "the phase"
    ),
    REASONS["irregular"]: (
        "recent cycles differ too much to place the luteal phase on any day with confidence"
    ),
    REASONS["overdue"]: (
        "the expected period has not arrived (atypical cycle): no adjustment until the next start"
    ),
    REASONS["uncertain"]: (
        "a cycle day that may be follicular or luteal depending on cycle length: no adjustment"
    ),
    REASONS["follicular"]: "follicular phase: it is the reference, there is nothing to discount",
    REASONS["luteal"]: (
        "luteal phase: what the phase raises, according to what was read, is discounted"
    ),
})


def _distinct_days(starts: Iterable[dt.datetime]) -> tuple[dt.datetime, ...]:
    """Un inicio marcado dos veces el mismo día es el mismo inicio."""
    by_day: dict[dt.date, dt.datetime] = {}
    for moment in sorted(starts):
        by_day.setdefault(moment.astimezone(dt.UTC).date(), moment)
    return tuple(sorted(by_day.values()))


def _center(samples: list[tuple[float, float]]) -> tuple[float, float]:
    """(día mediano, valor mediano) de unas lecturas (día, valor)."""
    return (
        statistics.median(day for day, _ in samples),
        statistics.median(value for _, value in samples),
    )


def _cycle_rise(
    luteal: list[tuple[float, float]],
    before: list[tuple[float, float]],
    after: list[tuple[float, float]],
) -> float | None:
    """La subida lútea de un ciclo cerrado en una familia de contexto, o `None` sin lecturas.

    La lútea se compara con la folicular **interpolada** a su fecha entre la de antes (el mismo
    ciclo) y la de después (los primeros días del ciclo siguiente): una deriva real y lenta
    —un deterioro que sube cada día— sube las dos foliculares y la lútea por igual y se cancela,
    en vez de leerse como subida lútea y descontarse después (lo vio la revisión de código de B3).
    """
    if min(len(luteal), len(before), len(after)) < MIN_PHASE_READINGS:
        return None
    luteal_day, luteal_value = _center(luteal)
    before_day, before_value = _center(before)
    after_day, after_value = _center(after)
    weight = (luteal_day - before_day) / (after_day - before_day)
    return luteal_value - (before_value + weight * (after_value - before_value))


def _personal_amplitudes(
    starts: tuple[dt.datetime, ...], observations: Iterable[VitalObservation]
) -> dict[tuple[int, str], float]:
    """Por ciclo (índice de su inicio) y clave, la subida lútea propia de los ciclos ya cerrados.

    Ver «CUÁNTO DESCONTAR» arriba. En un ciclo cerrado (de un inicio al siguiente), lútea segura son
    sus últimos `LUTEAL_CORE_DAYS`, folicular segura lo anterior a sus últimos `LUTEAL_MAX_DAYS`, y
    folicular de después los primeros `AFTER_DAYS` del ciclo siguiente. Se compara dentro de cada
    familia de contexto (reposo con reposo, sueño con sueño); la subida es la mediana de lo medido
    en los ciclos recientes, acotada al rango leído.
    """
    by_key: dict[str, list[VitalObservation]] = {}
    for obs in observations:
        if obs.key in LUTEAL_OFFSETS and not obs.is_low_confidence:
            by_key.setdefault(obs.key, []).append(obs)
    origin = starts[0] if starts else dt.datetime.now(dt.UTC)
    # Por ciclo cerrado, clave y familia: (lútea, folicular de antes, folicular de después).
    samples: dict[
        tuple[int, str, Context],
        tuple[list[tuple[float, float]], list[tuple[float, float]], list[tuple[float, float]]],
    ] = {}
    for key, series in by_key.items():
        series.sort(key=lambda obs: obs.effective)
        times = [obs.effective for obs in series]
        for index, (opened, closed) in enumerate(zip(starts, starts[1:], strict=False)):
            luteal_from = closed - dt.timedelta(days=LUTEAL_CORE_DAYS)
            follicular_until = closed - dt.timedelta(days=LUTEAL_MAX_DAYS)
            after_until = closed + dt.timedelta(days=AFTER_DAYS)
            low = bisect.bisect_left(times, opened)
            high = bisect.bisect_left(times, after_until)
            for obs in series[low:high]:
                if obs.effective >= closed:
                    side = 2
                elif obs.effective >= luteal_from:
                    side = 0
                elif obs.effective < follicular_until:
                    side = 1
                else:
                    continue
                group = samples.setdefault((index, key, obs.context.family), ([], [], []))
                day = (obs.effective - origin).total_seconds() / 86400.0
                group[side].append((day, obs.value))
    rises: dict[tuple[int, str], list[float]] = {}
    for (index, key, _family), (luteal, before, after) in samples.items():
        rise = _cycle_rise(luteal, before, after)
        if rise is not None:
            rises.setdefault((index, key), []).append(rise)

    personal: dict[tuple[int, str], float] = {}
    for key, documented in LUTEAL_OFFSETS.items():
        smallest, largest = LUTEAL_RANGES[key]
        sign = 1.0 if documented > 0 else -1.0
        for opening in range(1, len(starts)):
            # Solo ciclos cerrados ANTES de este: el que está en curso no se mide a sí mismo
            # (de él solo entran sus primeros días, como folicular de después del anterior).
            measured = [
                rise
                for closed_cycle in range(max(0, opening - RECENT_CYCLES), opening)
                for rise in rises.get((closed_cycle, key), [])
            ]
            if not measured:
                continue
            rise = sign * statistics.median(measured)
            personal[(opening, key)] = sign * min(max(rise, smallest), largest)
    return personal


@dataclass(frozen=True, slots=True)
class _Window:
    """Lo que sale de los ciclos recientes al abrirse uno: se calcula una vez por inicio."""

    opened: dt.datetime
    shortest: float
    longest: float
    typical: float


def _windows(starts: tuple[dt.datetime, ...]) -> tuple[_Window | None, ...]:
    """Por inicio, sus ciclos recientes; `None` mientras no haya `MIN_STARTS` inicios."""
    windows: list[_Window | None] = []
    for index, opened in enumerate(starts):
        known = index + 1
        if known < MIN_STARTS:
            windows.append(None)
            continue
        recent = starts[max(0, known - RECENT_CYCLES - 1):known]
        lengths = [
            (later - earlier).total_seconds() / 86400.0
            for earlier, later in zip(recent, recent[1:], strict=False)
        ]
        windows.append(_Window(opened, min(lengths), max(lengths), statistics.median(lengths)))
    return tuple(windows)


@dataclass(frozen=True, slots=True)
class CyclePhaseModel:
    """Los inicios de regla registrados, ordenados; de ellos sale la fase de cada instante.

    `personal` es la subida lútea propia por ciclo y clave (`_personal_amplitudes`); sin ella, el
    extremo menor del rango leído (`LUTEAL_OFFSETS`).
    """

    starts: tuple[dt.datetime, ...]
    personal: Mapping[tuple[int, str], float] = field(default_factory=dict, hash=False)
    windows: tuple[_Window | None, ...] = field(default=(), hash=False, compare=False)

    def __post_init__(self) -> None:
        # Construido a mano, sin `from_starts`: los ciclos recientes se calculan igual.
        if len(self.windows) != len(self.starts):
            object.__setattr__(self, "windows", _windows(self.starts))

    @classmethod
    def from_starts(
        cls,
        starts: Iterable[dt.datetime],
        observations: Iterable[VitalObservation] = (),
    ) -> CyclePhaseModel:
        """Con `observations` (las lecturas analizadas), la subida se mide en la propia serie."""
        ordered = _distinct_days(starts)
        return cls(
            ordered, MappingProxyType(_personal_amplitudes(ordered, observations)),
            _windows(ordered),
        )

    def luteal_rise(self, key: str, moment: dt.datetime) -> float:
        """La subida lútea que se descontaría en ese instante: la propia o, sin ella, la menor.

        La propia del ciclo en curso usa sus primeros `AFTER_DAYS`: hasta que han pasado, no se
        conoce, y vale la menor (causal).
        """
        documented = LUTEAL_OFFSETS.get(key)
        if documented is None:
            return 0.0
        opening = bisect.bisect_right(self.starts, moment) - 1
        if opening < 0 or moment < self.starts[opening] + dt.timedelta(days=AFTER_DAYS):
            return documented
        return self.personal.get((opening, key), documented)

    def phase_at(self, moment: dt.datetime) -> PhaseAt:
        known = bisect.bisect_right(self.starts, moment)
        window = self.windows[known - 1] if known else None
        if window is None:
            return PhaseAt(None, "too_few_starts")
        day = (moment - window.opened).total_seconds() / 86400.0
        luteal_from = window.longest - LUTEAL_DAYS
        if luteal_from >= window.shortest:
            return PhaseAt(None, "irregular", day, window.typical)
        if day >= window.shortest:
            return PhaseAt(None, "overdue", day, window.typical)
        if day >= luteal_from:
            return PhaseAt(ADJUSTED_PHASE, "luteal", day, window.typical)
        if day < window.shortest - LUTEAL_DAYS:
            return PhaseAt(REFERENCE_PHASE, "follicular", day, window.typical)
        return PhaseAt(None, "uncertain", day, window.typical)

    def offset(self, key: str, moment: dt.datetime) -> float:
        """Cuánto sube (o baja) la fase la clave en ese instante; 0 fuera de la fase lútea."""
        if key not in LUTEAL_OFFSETS:
            return 0.0
        if self.phase_at(moment).phase != ADJUSTED_PHASE:
            return 0.0
        return self.luteal_rise(key, moment)


def without_phase(
    observations: Iterable[VitalObservation], phase_offset: PhaseOffset | None
) -> list[VitalObservation]:
    """Las lecturas sin lo que la fase las desplaza: lo que ve la tendencia, la sombra del episodio
    cerrado y la comprobación de proyecciones, para que todas midan en la misma escala. Sin
    desplazamiento, las mismas lecturas."""
    if phase_offset is None:
        return list(observations)
    adjusted = []
    for obs in observations:
        shift = phase_offset(obs.key, obs.effective)
        adjusted.append(replace(obs, value=obs.value - shift) if shift else obs)
    return adjusted


def cited_refs() -> frozenset[str]:
    """Las fichas del registro que sostienen la fase y el desplazamiento."""
    return frozenset(PHASE_REFS) | frozenset(
        ref for key in LUTEAL_OFFSETS
        for ref in cycle_physiology.amplitude(key, ADJUSTED_PHASE).refs
    )
