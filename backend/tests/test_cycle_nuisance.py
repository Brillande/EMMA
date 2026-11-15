"""El ciclo menstrual como molestia, y la línea base consciente de la fase: las dos métricas.

POR QUÉ EXISTE. Una tripulante sin supresión menstrual pasa cada ~4 semanas dos con la
temperatura, el pulso en reposo y la variabilidad del pulso desplazados. Nadie lo había
medido: MMASH son 24 h de varones y el tripulante simulado no tenía ciclo. La invariante 5
pide medir la falsa alarma y la sensibilidad juntas. A5 (lote «ciclo», 2026-11-14) fijó la
línea de partida con el motor sin tocar: el ciclo multiplicaba la falsa alarma y borraba el
contraste del estado, sin quitar la detección en la lectura.

B3 (2026-11-15) añade el ajuste por fase (`analysis/cycle_phase.py`, con su puerta en
`api/cycle_phase.py`): en la fase lútea se descuenta, de la base y de la tendencia, la subida
de temperatura y pulso de la propia tripulante, acotada a lo leído. Aquí se mide cada caso tres
veces —sin ciclo, con ciclo sin ajuste y con ciclo y ajuste— y en las dos métricas a la vez. Las
cifras de A5 se reescribieron a propósito: las que describían el motor de antes siguen aquí, en
la fila «sin ajuste».

Lo que NO se arregla, y se dice: la RMSSD y la SDNN no se ajustan (lo leído solo da el sentido,
sin cifra), y el primer ciclo de una serie, sin ciclo cerrado propio, descuenta solo el extremo
menor de lo leído. La amplitud de la RMSSD del simulador es de diseño.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from functools import cache
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.analysis import cycle_phase
from app.analysis.baseline import BaselineEngine, Deviation, Severity, SeverityBasis
from app.analysis.cycle_phase import CyclePhaseModel, PhaseOffset
from app.analysis.risk import RiskEngine, RiskLevel
from app.analysis.trend import trends_by_indicator
from app.api.routes import CURRENT_WINDOW
from app.core.config import get_settings
from app.evidence import cycle_physiology, registry
from app.ingest.codes import get as get_code
from app.ingest.fhir import Context, VitalObservation, observation
from app.ingest.simulator import (
    LITERATURE,
    NO_SOURCE,
    CrewMember,
    MenstrualCycle,
    PhysiologicalSimulator,
    Scenario,
    evidence_report,
    literature_problems,
    luteal_level,
)
from app.validation import injection
from app.validation.injection import Injection, Perturbation

# Las amplitudes del simulador, tal como las da un ciclo por defecto.
_CYCLE_AMPLITUDES = dict(MenstrualCycle().amplitudes)

CYCLE_PARAMETERS = (
    "cycle_period_days",
    "cycle_luteal_days",
    "cycle_transition_days",
    "cycle_temperature_luteal_rise_c",
    "cycle_heart_rate_luteal_rise_bpm",
    "cycle_rmssd_luteal_drop_ms",
    "cycle_sdnn_luteal_drop_ms",
)


def _cycle(temperature: float) -> MenstrualCycle:
    """El ciclo de diseño con otra amplitud de temperatura (el resto, la de diseño)."""
    return MenstrualCycle(amplitudes={**_CYCLE_AMPLITUDES, "body-temperature": temperature})


def _series(
    cycle: MenstrualCycle | None, seed: int, days: int, keys: list[str] | None = None
) -> list[VitalObservation]:
    crew = CrewMember("crew-01", cycle=cycle)
    return sorted(
        PhysiologicalSimulator(Scenario.NOMINAL, seed=seed, crew=crew).generate(
            days=days, samples_per_day=24, keys=keys
        ),
        key=lambda o: o.effective,
    )


# --------------------------------------------------------------------------- #
# El simulador: apagado por defecto, y cuando se enciende hace lo que dice
# --------------------------------------------------------------------------- #


def test_no_cycle_by_default_and_the_nominal_series_does_not_move() -> None:
    assert CrewMember("crew-01").cycle is None
    assert PhysiologicalSimulator().crew.cycle is None
    plain = list(PhysiologicalSimulator(seed=7).generate(days=3))
    explicit = list(
        PhysiologicalSimulator(seed=7, crew=CrewMember("crew-01", cycle=None)).generate(days=3)
    )
    assert plain == explicit


def test_a_cycle_with_no_amplitude_leaves_the_series_bit_for_bit() -> None:
    """El ciclo no gasta números aleatorios: sin amplitud, la serie es la de siempre."""
    flat = MenstrualCycle(amplitudes=dict.fromkeys(_CYCLE_AMPLITUDES, 0.0))
    # Solo cambia la procedencia, que nombra el ciclo aunque sea plano.
    with_flat = [(o.key, o.effective, o.value) for o in _series(flat, 3, 30)]
    assert with_flat == [(o.key, o.effective, o.value) for o in _series(None, 3, 30)]


def test_a_series_with_a_cycle_says_so_in_its_provenance() -> None:
    """Escenario y semilla ya no bastan para reproducir una serie con ciclo: lo dice la
    procedencia de cada lectura y `describe()`. Sin ciclo, la de siempre."""
    plain = PhysiologicalSimulator(seed=4)
    assert next(plain.generate(days=1)).model_version == "simulator:nominal@4"
    assert "cycle" not in plain.describe()
    cycle = MenstrualCycle(start_cycle_day=3.0)
    cycled = PhysiologicalSimulator(seed=4, crew=CrewMember("crew-01", cycle=cycle))
    version = next(cycled.generate(days=1)).model_version
    assert version == f"simulator:nominal@4+{cycle.label()}"
    assert "start=3" in version and "body-temperature=0.4" in version
    assert cycled.describe()["cycle"] == cycle.label()


def test_a_cycle_is_hashable_and_its_amplitudes_do_not_change_after_validation() -> None:
    cycle = MenstrualCycle()
    hash(cycle)
    hash(Injection("heart-rate", Perturbation.CYCLE, 3.0, dt.datetime(2026, 1, 1), cycle=cycle))
    with pytest.raises(TypeError):
        cycle.amplitudes["no-such-key"] = 1.0  # type: ignore[index]


def test_the_luteal_step_is_smooth_periodic_and_has_its_plateau() -> None:
    period = LITERATURE["cycle_period_days"].value
    luteal = LITERATURE["cycle_luteal_days"].value
    ramp = LITERATURE["cycle_transition_days"].value
    ovulation = period - luteal
    assert luteal_level(0.0) == 0.0
    assert luteal_level(ovulation - 0.01) == 0.0
    assert luteal_level(ovulation + ramp / 2) == pytest.approx(0.5)
    assert luteal_level(ovulation + ramp) == pytest.approx(1.0)
    assert luteal_level(period - ramp - 0.01) == 1.0
    assert luteal_level(period - ramp / 2) == pytest.approx(0.5)
    # Periódico y continuo de un ciclo al siguiente: no hay salto al volver la regla.
    for day in np.linspace(0.0, period, 400):
        assert luteal_level(day) == pytest.approx(luteal_level(day + period))
    steps = np.diff([luteal_level(day) for day in np.linspace(0.0, 2 * period, 4001)])
    # Paso de ~0,014 días: la pendiente máxima del medio coseno (π/2 por rampa) da ~0,011; un
    # salto daría 1.
    assert np.max(np.abs(steps)) < 0.02
    # Una forma imposible se rechaza al crearla, no a mitad de una serie.
    with pytest.raises(ValueError):
        MenstrualCycle(luteal_days=30.0)
    with pytest.raises(ValueError):
        MenstrualCycle(transition_days=8.0)
    with pytest.raises(KeyError):
        MenstrualCycle(amplitudes={"no-such-key": 1.0})


def test_the_cycle_moves_only_its_keys_by_its_amplitude() -> None:
    cycle = MenstrualCycle(start_cycle_day=5.0)
    with_cycle = _series(cycle, 0, 28)
    without = _series(None, 0, 28)
    start = without[0].effective
    for a, b in zip(with_cycle, without, strict=True):
        assert (a.key, a.effective, a.context) == (b.key, b.effective, b.context)
        if a.key not in _CYCLE_AMPLITUDES:
            assert a.value == b.value, a.key
    temperature = [
        (a, b) for a, b in zip(with_cycle, without, strict=True) if a.key == "body-temperature"
    ]
    for a, b in temperature:
        day = (a.effective - start).total_seconds() / 86400
        assert a.value - b.value == pytest.approx(cycle.offset_at(a.key, day), abs=0.002)
    # Y el sentido: la temperatura y el pulso suben en la lútea; la variabilidad baja.
    assert _CYCLE_AMPLITUDES["body-temperature"] > 0
    assert _CYCLE_AMPLITUDES["heart-rate"] > 0
    assert _CYCLE_AMPLITUDES["hrv-rmssd"] < 0
    assert _CYCLE_AMPLITUDES["hrv-sdnn"] < 0


def test_the_cycle_parameters_cite_what_was_read_and_the_rest_says_design() -> None:
    """Las subidas con cifra leída (B3) son magnitud documentada, con sus fichas y un valor
    dentro del rango leído; la forma del ciclo y la bajada de la variabilidad, de diseño."""
    read = {
        "cycle_temperature_luteal_rise_c": "body-temperature",
        "cycle_heart_rate_luteal_rise_bpm": "heart-rate",
    }
    for name in CYCLE_PARAMETERS:
        param = LITERATURE[name]
        if name in read:
            found = cycle_physiology.amplitude(read[name], "luteal")
            assert param.evidence == "established" == found.evidence, name
            assert param.refs and set(param.refs) <= set(found.refs), name
            assert found.low is not None and found.high is not None
            assert found.low <= param.value <= found.high, name
        else:
            assert param.evidence == "design", name
            assert param.source == NO_SOURCE and not param.refs, name
    assert not literature_problems(LITERATURE, registry.registry())
    report = evidence_report(["simulator:nominal"])
    assert report is not None
    assert set(CYCLE_PARAMETERS) - set(read) <= set(report["evidence"]["design"])
    assert set(read) <= set(report["evidence"]["established"])
    assert MenstrualCycle().period_days == LITERATURE["cycle_period_days"].value


# --------------------------------------------------------------------------- #
# La perturbación cíclica de la validación
# --------------------------------------------------------------------------- #


def test_the_cyclic_perturbation_is_the_simulator_shape_on_every_key() -> None:
    onset = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)
    cycle = MenstrualCycle()
    parts = injection.cyclic(onset, cycle)
    assert {part.key for part in parts} == set(_CYCLE_AMPLITUDES)
    assert {part.kind for part in parts} == {Perturbation.CYCLE}
    for part in parts:
        for hours in range(0, 24 * 60, 7):
            moment = onset + dt.timedelta(hours=hours)
            assert part.offset_at(moment) == pytest.approx(
                cycle.offset_at(part.key, hours / 24)
            )
    # Sobre la temperatura (sin ritmo circadiano) el ciclo inyectado y el simulado coinciden.
    plain = _series(None, 1, 40, keys=["body-temperature"])
    simulated = _series(cycle, 1, 40, keys=["body-temperature"])
    injected = injection.inject_all(plain, injection.cyclic(plain[0].effective, cycle))
    for a, b in zip(injected, simulated, strict=True):
        assert a.value == pytest.approx(b.value, abs=0.002)


def test_the_cycle_is_a_nuisance_and_not_a_reference_deterioration() -> None:
    """Meterlo en `REFERENCE_INJECTIONS` rotularía en la matriz de riesgos como sensibilidad
    lo que es una molestia."""
    onset = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)
    kinds = {build(onset).kind for build in injection.REFERENCE_INJECTIONS.values()}
    assert Perturbation.CYCLE not in kinds
    assert all(kind is not Perturbation.CYCLE for _, kind in injection.REFERENCE_TARGETS.values())


def test_composed_perturbations_add_up() -> None:
    plain = _series(None, 2, 3, keys=["heart-rate"])
    onset = plain[0].effective
    step = Injection("heart-rate", Perturbation.STEP, 5.0, onset)
    both = injection.inject_all(plain, [step, step])
    for a, b in zip(both, plain, strict=True):
        assert a.value == pytest.approx(b.value + 10.0, abs=0.002)


# --------------------------------------------------------------------------- #
# La fase que recibe el motor: los inicios de regla del ciclo simulado
# --------------------------------------------------------------------------- #

# La tripulante registra sus inicios de regla: los de dos ciclos antes de la misión (prevuelo) y
# los que van llegando. El motor solo usa, en cada instante, los registrados hasta ese instante.
PREFLIGHT_CYCLES = 3


def _starts(origin: dt.datetime, cycle: MenstrualCycle, days: int) -> list[dt.datetime]:
    """Los inicios de regla del ciclo simulado (día 0 del ciclo), del prevuelo al final."""
    first = origin - dt.timedelta(days=cycle.start_cycle_day)
    count = PREFLIGHT_CYCLES + int(days // cycle.period_days) + 1
    return [
        first + dt.timedelta(days=cycle.period_days * (k - PREFLIGHT_CYCLES)) for k in range(count)
    ]


def _phase(
    series: list[VitalObservation], cycle: MenstrualCycle | None, adjusted: bool, days: int
) -> PhaseOffset | None:
    """El desplazamiento que le daría la puerta abierta, o `None` (sin ciclo o sin ajuste)."""
    if cycle is None or not adjusted:
        return None
    origin = series[0].effective.replace(hour=0, minute=0, second=0, microsecond=0)
    return CyclePhaseModel.from_starts(_starts(origin, cycle, days), series).offset


def test_with_the_cycle_starts_the_simulated_luteal_plateau_is_luteal_for_the_engine() -> None:
    """La franja lútea del motor cae en la meseta del simulador, y no en su fase folicular."""
    cycle = MenstrualCycle()
    series = _series(cycle, 0, 60, keys=["body-temperature"])
    origin = series[0].effective
    model = CyclePhaseModel.from_starts(_starts(origin, cycle, 60), series)
    for hours in range(0, 24 * 60, 5):
        moment = origin + dt.timedelta(hours=hours)
        found = model.phase_at(moment)
        level = cycle.level_at(hours / 24)
        if found.phase == "luteal":
            assert level > 0.0, (hours / 24, level)
        if level == 0.0 and found.phase is not None:
            assert found.phase == "follicular", hours / 24
    # La subida propia se mide en los ciclos cerrados y cae dentro de lo leído.
    rises = [value for (_, key), value in model.personal.items() if key == "body-temperature"]
    assert rises and all(0.23 <= value <= 0.7 for value in rises)


# --------------------------------------------------------------------------- #
# (a) Falsa alarma: tripulante sana, 70 días, 3 semillas; sin ciclo, con ciclo sin ajuste y con
#     ciclo y ajuste por fase
# --------------------------------------------------------------------------- #

# `None` es el tripulante sin ciclo (la plantilla de `test_analysis.py`, 12 de 84). Las otras son
# el ciclo con 0,3, 0,5 y 0,7 °C de subida lútea de temperatura (0,7: el extremo alto de lo
# leído); el pulso con su subida documentada del simulador (+3,7 lpm), la RMSSD y la SDNN (-6 ms)
# con su amplitud de diseño.
AMPLITUDES: tuple[float | None, ...] = (None, 0.3, 0.5, 0.7)

# Medido el 2026-11-15, evaluando en días alternos (84 evaluaciones). Clave: (amplitud, ajuste).
#   Sin ajuste (el motor de A5): con el ciclo, tres cuartas partes de la misión en WATCH; la
#   TENDENCIA de la temperatura (el escalón lúteo visto por una recta de 21 días) y de la RMSSD.
#   Con ajuste: lo que queda de temperatura es el primer ciclo de la serie, que no tiene un ciclo
#   cerrado propio con lecturas y descuenta el extremo menor de lo leído (0,23 °C), y su eco en la
#   recta de 21 días; desde el día 44, la tendencia de la temperatura marca 0 de 39 evaluaciones a
#   0,5 °C y 1 de 39 a 0,7 °C (medido aparte). Lo que queda de RMSSD (15) no se ajusta:
#   lo leído no da cifra. CONCERN no aparece en ningún caso.
MEASURED_WATCH: dict[tuple[float | None, bool], int] = {
    (None, False): 12,
    (0.3, False): 63, (0.3, True): 26,
    (0.5, False): 71, (0.5, True): 43,
    (0.7, False): 75, (0.7, True): 52,
}
WATCH_TOLERANCE = 2


@cache
def _healthy(temperature: float | None, adjusted: bool) -> tuple[int, int, int]:
    cycle = None if temperature is None else _cycle(temperature)
    concern = watch = evaluated = 0
    for seed in (0, 1, 2):
        observations = _series(cycle, seed, 70)
        phase = _phase(observations, cycle, adjusted, 70)
        deviations = BaselineEngine().evaluate_rolling(observations, phase_offset=phase)
        start = observations[0].effective
        for day in range(14, 70, 2):
            now = start + dt.timedelta(days=day + 1)
            past = [o for o in observations if o.effective < now]
            cutoff = past[-1].effective - CURRENT_WINDOW
            status = RiskEngine().assess(
                "crew-01",
                [d for d in deviations if cutoff <= d.effective < now],
                # Igual que la plantilla de `test_analysis.py` (sin `now`), para que la cifra sin
                # ciclo sea comparable con la suya: 12 de 84 en las dos.
                trends=trends_by_indicator(past, phase_offset=phase),
            )
            evaluated += 1
            concern += status.overall_level in (RiskLevel.CONCERN, RiskLevel.CRITICAL)
            watch += status.overall_level is not RiskLevel.NOMINAL
    return concern, watch, evaluated


CASES = [(None, False)] + [
    (temperature, adjusted) for temperature in AMPLITUDES[1:] for adjusted in (False, True)
]


@pytest.mark.parametrize(("temperature", "adjusted"), CASES)
def test_false_alarm_without_and_with_the_phase_adjustment(
    temperature: float | None, adjusted: bool
) -> None:
    """La falsa alarma por amplitud, sin y con el ajuste por fase. CONCERN, nunca."""
    concern, watch, evaluated = _healthy(temperature, adjusted)
    assert evaluated == 84
    assert concern == 0, f"{concern} días en CONCERN sobre una tripulante sana"
    measured = MEASURED_WATCH[(temperature, adjusted)]
    assert abs(watch - measured) <= WATCH_TOLERANCE, (
        f"WATCH en {watch} de {evaluated} con ciclo {temperature}, ajuste {adjusted} (medido: "
        f"{measured}); si lo ha cambiado el motor, actualiza la cifra y la sensibilidad juntas"
    )


# --------------------------------------------------------------------------- #
# (b) Sensibilidad: deterioros de referencia y una febrícula, en plena fase lútea
# --------------------------------------------------------------------------- #

SENSITIVITY_KEYS = ["body-temperature", "heart-rate", "hrv-rmssd", "hrv-sdnn"]
# Día 48 a las 10:00: con el ciclo empezando el día 0, en plena meseta lútea del SEGUNDO ciclo
# (días 44-54), después de un ciclo cerrado con lecturas del que se mide la subida propia; y en
# vigilia (el estrato de reposo, con base personal: el de sueño tiene pocas lecturas y gradúa
# contra el rango poblacional, donde un pulso de 90 lpm no destaca). A5 lo ponía el día 20, en el
# primer ciclo: ahí no hay ciclo cerrado propio y el ajuste descuenta el extremo menor de lo leído.
# Se movió a propósito para medir el ajuste como funciona en una misión con ciclos registrados; la
# fila sin ciclo se volvió a medir en el mismo día.
ONSET = dt.timedelta(days=48, hours=10)
SENSITIVITY_DAYS = 51
CHECKPOINTS = (dt.timedelta(hours=24), dt.timedelta(hours=48))
_ORDER = [RiskLevel.NOMINAL, RiskLevel.WATCH, RiskLevel.CONCERN, RiskLevel.CRITICAL]
FEVER_LABEL = "febrícula en fase lútea (+0,5 °C sostenida)"


def low_grade_fever(onset: dt.datetime) -> Injection:
    """+0,5 °C sostenida: sobre la meseta lútea, la temperatura queda ~0,9 °C sobre la folicular."""
    return Injection("body-temperature", Perturbation.STEP, 0.5, onset)


INJECTIONS = {**injection.REFERENCE_INJECTIONS, FEVER_LABEL: low_grade_fever}


def _level(
    observations: list[VitalObservation],
    deviations: list[Deviation],
    moment: dt.datetime,
    phase: PhaseOffset | None,
) -> RiskLevel:
    past = [o for o in observations if o.effective <= moment]
    current = [d for d in deviations if moment - CURRENT_WINDOW <= d.effective <= moment]
    return RiskEngine().assess(
        "crew-01", current, trends=trends_by_indicator(past, now=moment, phase_offset=phase)
    ).overall_level


@cache
def _sensitivity(temperature: float | None, adjusted: bool) -> dict[str, dict[str, int]]:
    """Por deterioro, sobre 3 semillas: lecturas tocadas que se marcan, estado que sale de
    NOMINAL, estado que sube por encima del de la misma serie sin deterioro, y esa serie sin
    deterioro ya fuera de NOMINAL."""
    cycle = None if temperature is None else _cycle(temperature)
    out: dict[str, dict[str, int]] = {
        label: {"detected": 0, "flagged": 0, "escalated": 0, "sham_flagged": 0}
        for label in INJECTIONS
    }
    for seed in (0, 1, 2):
        series = _series(cycle, seed, SENSITIVITY_DAYS, keys=SENSITIVITY_KEYS)
        onset = series[0].effective + ONSET
        segment = [o for o in series if o.effective <= onset + CHECKPOINTS[-1]]
        clean_phase = _phase(segment, cycle, adjusted, SENSITIVITY_DAYS)
        clean = BaselineEngine().evaluate_rolling(segment, phase_offset=clean_phase)
        sham = [_level(segment, clean, onset + delay, clean_phase) for delay in CHECKPOINTS]
        for label, build in INJECTIONS.items():
            injected = injection.inject(segment, build(onset))
            # La subida propia se mide con lo que de verdad llegó, deterioro incluido: como en
            # la API, que la mide con las lecturas analizadas.
            phase = _phase(injected.observations, cycle, adjusted, SENSITIVITY_DAYS)
            deviations = BaselineEngine().evaluate_rolling(
                injected.observations, phase_offset=phase
            )
            by_reading = {(d.key, d.effective): d for d in deviations}
            hits = sum(
                by_reading[(o.key, o.effective)].is_concerning for o in injected.affected
            )
            levels = [
                _level(injected.observations, deviations, onset + delay, phase)
                for delay in CHECKPOINTS
            ]
            row = out[label]
            row["detected"] += hits > 0
            row["flagged"] += any(level is not RiskLevel.NOMINAL for level in levels)
            row["escalated"] += any(
                _ORDER.index(level) > _ORDER.index(base)
                for level, base in zip(levels, sham, strict=True)
            )
            row["sham_flagged"] += any(level is not RiskLevel.NOMINAL for level in sham)
    return out


def _totals(temperature: float | None, adjusted: bool) -> dict[str, int]:
    rows = _sensitivity(temperature, adjusted).values()
    return {field: sum(row[field] for row in rows) for field in next(iter(rows))}


# Medido el 2026-11-15: 5 deterioros x 3 semillas = 15 casos por fila.
#   detected     alguna lectura tocada se marca: 15 de 15 en todas las filas. Ni el ciclo ni el
#                ajuste tapan la lectura.
#   escalated    el estado (a 24 o 48 h) sube por encima del de la misma serie sin deterioro.
#                Sin ciclo, 10. Con ciclo sin ajuste, 0: la serie sin deterioro YA está en WATCH
#                por la molestia. Con ajuste vuelve a subir, sin llegar a la de sin ciclo: la
#                serie sin deterioro sigue en WATCH en algunas semillas por la tendencia de la
#                RMSSD, que no se ajusta (lo leído no da cifra).
#   sham_flagged la serie sin deterioro fuera de NOMINAL (la molestia): 0 sin ciclo; 15 con ciclo
#                sin ajuste; con ajuste, solo la RMSSD.
MEASURED_SENSITIVITY: dict[tuple[float | None, bool], dict[str, int]] = {
    (None, False): {"detected": 15, "flagged": 10, "escalated": 10, "sham_flagged": 0},
    (0.3, False): {"detected": 15, "flagged": 15, "escalated": 0, "sham_flagged": 15},
    (0.3, True): {"detected": 15, "flagged": 14, "escalated": 6, "sham_flagged": 10},
    (0.5, False): {"detected": 15, "flagged": 15, "escalated": 0, "sham_flagged": 15},
    (0.5, True): {"detected": 15, "flagged": 14, "escalated": 7, "sham_flagged": 10},
    (0.7, False): {"detected": 15, "flagged": 15, "escalated": 0, "sham_flagged": 15},
    (0.7, True): {"detected": 15, "flagged": 14, "escalated": 7, "sham_flagged": 10},
}
# La febrícula sola: el estado sube por ella en 2 de 3 semillas sin ciclo; con ciclo sin ajuste,
# en ninguna (por el nivel no se distingue de la fase lútea); con ajuste, otra vez en 2 de 3 a
# 0,3 °C y en 3 de 3 a 0,5 y 0,7 °C (la serie sin deterioro ya está en WATCH por la RMSSD y la
# febrícula la lleva más arriba).
MEASURED_FEVER_ESCALATED: dict[tuple[float | None, bool], int] = {
    (None, False): 2,
    (0.3, False): 0, (0.3, True): 2,
    (0.5, False): 0, (0.5, True): 3,
    (0.7, False): 0, (0.7, True): 3,
}
SENSITIVITY_TOLERANCE = 1


@pytest.mark.parametrize(("temperature", "adjusted"), CASES)
def test_sensitivity_without_and_with_the_phase_adjustment(
    temperature: float | None, adjusted: bool
) -> None:
    """La sensibilidad por amplitud, sin y con el ajuste, con la febrícula en fase lútea."""
    measured = MEASURED_SENSITIVITY[(temperature, adjusted)]
    totals = _totals(temperature, adjusted)
    for field, value in measured.items():
        assert abs(totals[field] - value) <= SENSITIVITY_TOLERANCE, (field, totals, measured)
    fever = _sensitivity(temperature, adjusted)[FEVER_LABEL]
    assert fever["detected"] == 3, "la febrícula en fase lútea tiene que marcarse en la lectura"
    assert fever["escalated"] == MEASURED_FEVER_ESCALATED[(temperature, adjusted)], fever


def test_both_metrics_together() -> None:
    """La invariante 5 en una sola mirada, por amplitud, ajuste contra no ajuste.

    El ajuste por fase tiene que bajar la falsa alarma Y no bajar la sensibilidad: la detección
    en la lectura igual, el contraste del estado (`escalated`) y la febrícula lútea, iguales o
    mejores. Si alguien baja la falsa alarma a costa de lo segundo, esta prueba lo dice. Y la
    detección en la lectura con ciclo y ajuste no cae por debajo de la de sin ciclo."""
    for temperature in AMPLITUDES[1:]:
        assert _healthy(temperature, True)[1] < _healthy(temperature, False)[1], temperature
        assert _healthy(temperature, True)[0] == 0
        adjusted, plain = _totals(temperature, True), _totals(temperature, False)
        assert adjusted["detected"] >= plain["detected"]
        assert adjusted["detected"] >= _totals(None, False)["detected"]
        assert adjusted["escalated"] >= plain["escalated"]
        fever = _sensitivity(temperature, True)[FEVER_LABEL]["escalated"]
        assert fever >= _sensitivity(temperature, False)[FEVER_LABEL]["escalated"]


# --------------------------------------------------------------------------- #
# La regla, pieza a pieza
# --------------------------------------------------------------------------- #

T0 = dt.datetime(2026, 9, 1, tzinfo=dt.UTC)


def _model(*lengths: float, observations: list[VitalObservation] | None = None) -> CyclePhaseModel:
    starts = [T0]
    for length in lengths:
        starts.append(starts[-1] + dt.timedelta(days=length))
    return CyclePhaseModel.from_starts(starts, observations or [])


def _day(model: CyclePhaseModel, day: float) -> dt.datetime:
    return model.starts[-1] + dt.timedelta(days=day)


def test_the_phase_needs_three_starts() -> None:
    assert _model(28).phase_at(_day(_model(28), 20)).reason == "too_few_starts"
    assert _model(28).offset("body-temperature", _day(_model(28), 20)) == 0.0
    model = _model(28, 28)
    assert model.phase_at(_day(model, 20)).phase == "luteal"
    # Un inicio marcado dos veces el mismo día cuenta una vez.
    twice = CyclePhaseModel.from_starts(
        [T0, T0 + dt.timedelta(hours=3), T0 + dt.timedelta(days=28)]
    )
    assert len(twice.starts) == 2


def test_the_luteal_window_is_counted_back_from_every_recent_length() -> None:
    model = _model(28, 28, 28)
    # 28 - 12,4 = 15,6: lútea desde ahí hasta el día 28 (sin incluirlo).
    assert model.phase_at(_day(model, 15.5)).phase == "follicular"
    assert model.phase_at(_day(model, 15.7)).phase == "luteal"
    assert model.phase_at(_day(model, 27.9)).phase == "luteal"
    assert model.phase_at(_day(model, 5)).phase == "follicular"
    assert model.offset("body-temperature", _day(model, 5)) == 0.0
    assert model.offset("body-temperature", _day(model, 20)) == pytest.approx(0.23)
    assert model.offset("heart-rate", _day(model, 20)) == pytest.approx(3.42)
    # Sin cifra leída, sin ajuste.
    assert model.offset("hrv-rmssd", _day(model, 20)) == 0.0
    assert model.offset("hrv-sdnn", _day(model, 20)) == 0.0
    assert set(cycle_phase.UNADJUSTED_KEYS) == {"hrv-rmssd", "hrv-sdnn"}
    # Ciclos de 26 y 32 días: lútea solo donde lo sería con los dos (32 - 12,4 = 19,6 a 26).
    mixed = _model(26, 32)
    assert mixed.phase_at(_day(mixed, 18)).phase is None
    assert mixed.phase_at(_day(mixed, 18)).reason == "uncertain"
    assert mixed.phase_at(_day(mixed, 20)).phase == "luteal"


def test_an_atypical_or_irregular_cycle_is_not_placed() -> None:
    model = _model(28, 28)
    late = model.phase_at(_day(model, 29))
    assert late.phase is None and late.reason == "overdue"
    assert model.offset("body-temperature", _day(model, 29)) == 0.0
    irregular = _model(22, 38)
    found = irregular.phase_at(_day(irregular, 21))
    assert found.phase is None and found.reason == "irregular"


def test_the_offset_is_causal() -> None:
    """La fase de un instante solo usa los inicios registrados hasta él."""
    model = _model(28, 28, 28)
    moment = model.starts[2] + dt.timedelta(days=20)
    assert model.phase_at(moment) == _model(28, 28).phase_at(moment)


def _temperatures(rise: float) -> list[VitalObservation]:
    """Tres ciclos de 28 días de temperatura en reposo cada hora, con su escalón lúteo."""
    readings = []
    for hour in range(24 * 28 * 3):
        moment = T0 + dt.timedelta(hours=hour)
        luteal = (hour / 24) % 28 >= 14
        readings.append(_reading("body-temperature", 36.6 + (rise if luteal else 0.0), moment))
    return readings


def _reading(key: str, value: float, moment: dt.datetime) -> VitalObservation:
    return observation(key, value, moment, "crew-01", "test", context=Context.REST)


def test_the_rise_is_her_own_bounded_by_what_was_read_and_from_closed_cycles_only() -> None:
    for rise, expected in ((0.5, 0.5), (0.1, 0.23), (1.5, 0.7)):
        model = _model(28, 28, 28, observations=_temperatures(rise))
        # El primer ciclo no tiene ciclo cerrado antes: el extremo menor de lo leído.
        assert model.luteal_rise("body-temperature", model.starts[0] + dt.timedelta(days=20)) == (
            pytest.approx(0.23)
        )
        later = model.starts[1] + dt.timedelta(days=20)
        assert model.luteal_rise("body-temperature", later) == pytest.approx(expected), rise
        # Mientras no pasan los primeros días del ciclo en curso (la folicular de después del
        # anterior), la propia no se conoce: el extremo menor (causal).
        early = model.starts[1] + dt.timedelta(days=3)
        assert model.luteal_rise("body-temperature", early) == pytest.approx(0.23), rise
    # Una fiebre en el ciclo en curso no cambia lo que se descuenta en él.
    readings = _temperatures(0.4)
    # Los últimos 7 días del ciclo, los que miden la subida lútea propia: bastan para
    # mover su mediana.
    fever_from = T0 + dt.timedelta(days=28 + 21)
    fevered = [
        replace(o, value=o.value + 1.0) if fever_from <= o.effective < fever_from
        + dt.timedelta(days=7) else o
        for o in readings
    ]
    clean = _model(28, 28, 28, observations=readings)
    sick = _model(28, 28, 28, observations=fevered)
    during = fever_from + dt.timedelta(days=1)
    assert sick.luteal_rise("body-temperature", during) == clean.luteal_rise(
        "body-temperature", during
    )


def test_a_slow_real_drift_is_not_taken_for_her_luteal_rise() -> None:
    """Una deriva lenta y real (+0,03 °C al día, un deterioro) sin escalón lúteo: la folicular
    interpolada a la fecha de la lútea la cancela, y lo que se descuenta es el extremo menor de lo
    leído, no la deriva (hallazgo de la revisión de código de B3). Sin interpolar, la lútea de cada
    ciclo cerrado saldría ~0,55 °C por encima de su folicular y se descontaría casi todo."""
    readings = [
        _reading("body-temperature", 36.6 + 0.03 * hour / 24, T0 + dt.timedelta(hours=hour))
        for hour in range(24 * 28 * 3)
    ]
    model = _model(28, 28, 28, observations=readings)
    for opening in (1, 2, 3):
        later = model.starts[opening] + dt.timedelta(days=20)
        assert model.luteal_rise("body-temperature", later) == pytest.approx(0.23), opening


def test_the_offset_moves_the_base_never_the_reading_nor_the_danger_limit() -> None:
    """En fase lútea, una lectura sobre el límite de peligro sigue siendo GRAVE por el límite, y
    la desviación lleva el valor medido; lo que se mueve es la base."""
    model = _model(28, 28, 28)
    code = get_code("body-temperature")
    assert code.critical_high is not None
    start = model.starts[-1]
    readings = [
        _reading("body-temperature", 36.6 + (index % 7) * 0.02, start + dt.timedelta(hours=index))
        # Solo la fase folicular: la base, sin nada que descontar, se lleva entera a la lútea.
        for index in range(24 * 14)
    ]
    moment = start + dt.timedelta(days=21, hours=1)
    assert model.phase_at(moment).phase == "luteal"
    hot = _reading("body-temperature", code.critical_high + 0.1, moment)
    deviations = BaselineEngine().evaluate_rolling([*readings, hot], phase_offset=model.offset)
    (found,) = [d for d in deviations if d.effective == moment]
    assert found.value == hot.value
    assert found.basis is SeverityBasis.DANGER_LIMIT and found.severity is Severity.SEVERE
    plain = BaselineEngine().evaluate_rolling([*readings, hot])
    (unadjusted,) = [d for d in plain if d.effective == moment]
    # La base, llevada a la fase de la lectura: 0,23 °C por encima de la que no se ajusta.
    assert found.baseline is not None and unadjusted.baseline is not None
    assert found.baseline.center - unadjusted.baseline.center == pytest.approx(0.23, abs=1e-6)


def test_with_exactly_the_discounted_rise_the_base_is_the_reading_in_both_phases() -> None:
    """Una serie plana con un escalón lúteo igual a lo que se descuenta: la base de cada lectura,
    llevada a su fase, es la propia lectura, en la folicular y en la lútea. Con el signo al revés
    en cualquiera de los dos pasos (quitar la fase a la ventana, ponerle la de la lectura), no."""
    model = _model(28, 28, 28)
    readings = []
    for hour in range(24 * 40):
        moment = model.starts[2] + dt.timedelta(hours=hour)
        rise = model.offset("body-temperature", moment)
        readings.append(_reading("body-temperature", 36.6 + rise, moment))
    deviations = BaselineEngine().evaluate_rolling(readings, phase_offset=model.offset)
    personal = [d for d in deviations if not d.used_population_range]
    phases = {model.phase_at(d.effective).phase for d in personal}
    assert phases >= {"luteal", "follicular"}
    for found in personal:
        assert found.baseline is not None
        assert found.baseline.center == pytest.approx(found.value, abs=1e-9), found.effective
        assert not found.is_concerning


def test_without_a_phase_the_engine_is_bit_for_bit_the_same() -> None:
    series = _series(_cycle(0.5), 0, 30)
    assert BaselineEngine().evaluate_rolling(series) == BaselineEngine().evaluate_rolling(
        series, phase_offset=None
    )
    assert trends_by_indicator(series) == trends_by_indicator(series, phase_offset=None)


def test_the_phase_adjustment_is_in_the_trend_too() -> None:
    """Sin el ajuste en la tendencia no se arregla nada: la deriva lútea desaparece de la recta."""
    readings = _temperatures(0.5)
    model = _model(28, 28, 28, observations=readings)
    # Día 25 del tercer ciclo: 11 días en la meseta en una ventana de 21.
    moment = model.starts[2] + dt.timedelta(days=25)
    past = [o for o in readings if o.effective <= moment]
    plain = trends_by_indicator(past, now=moment)["body-temperature"]
    adjusted = trends_by_indicator(past, now=moment, phase_offset=model.offset)[
        "body-temperature"
    ]
    assert abs(adjusted.slope_per_day) < abs(plain.slope_per_day) / 3


# --------------------------------------------------------------------------- #
# La puerta (en `api/`): sexo declarado femenino, ciclo regular declarado e inicios suficientes
# --------------------------------------------------------------------------- #

FAR = "2100-01-01T00:00:00+00:00"


def _post(client: TestClient, key: str, value: float, when: dt.datetime) -> None:
    response = client.post(
        "/api/observations",
        json={"key": key, "value": value, "source": "manual", "effective": when.isoformat()},
    )
    assert response.status_code == 201, response.text


def _status(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/status", params={"until": FAR})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _verdict(body: dict[str, Any]) -> Any:
    """Lo que decide: el nivel, los dominios, las alertas y las recomendaciones."""
    return (
        body["overall_level"], body["domains"], body["alerts"], body["recommendations"],
        body["predictions"],
    )


def test_the_gate_opens_only_with_all_three_and_says_what_is_missing(
    client: TestClient,
) -> None:
    from app.api import cycle_phase as gate

    start = dt.datetime.combine(get_settings().mission_start, dt.time(), tzinfo=dt.UTC)
    response = client.post("/api/simulate", params={"days": 45, "cycle": True})
    assert response.status_code == 201, response.text
    closed = _status(client)
    assert closed["cycle_phase"] == {"applied": False, "phase": None, "reason": gate.NO_DECLARED}

    assert client.post(
        "/api/crew/sex", json={"sex": "male", "declared_by": "Ane"}
    ).status_code == 201
    male = _status(client)
    assert male["cycle_phase"]["reason"] == gate.NOT_FEMALE
    assert _verdict(male) == _verdict(closed)

    assert client.post(
        "/api/crew/sex", json={"sex": "female", "declared_by": "Ane"}
    ).status_code == 201
    assert _status(client)["cycle_phase"]["reason"] == gate.NO_STATUS
    _post(client, "reproductive-status", 1.0, start - dt.timedelta(days=60))
    few = _status(client)["cycle_phase"]
    assert few["applied"] is False and "faltan inicios de regla" in few["reason"]
    for k in (-2, -1, 0, 1):
        _post(client, "menstruation-start", 1.0, start + dt.timedelta(days=28 * k))
    # Un 0 no es un inicio.
    _post(client, "menstruation-start", 0.0, start + dt.timedelta(days=10))
    opened = _status(client)
    # Día 45 de la misión = día 17 del ciclo: fase lútea.
    assert opened["cycle_phase"]["applied"] is True
    assert opened["cycle_phase"]["phase"] == "luteal"
    assert "fase lútea" in opened["cycle_phase"]["reason"]
    profile = client.get("/api/baseline-profile", params={"until": FAR}).json()
    assert profile["cycle_phase"] == opened["cycle_phase"]
    # Y el estado se calculó con el desplazamiento, en la base y en la tendencia.
    from app.api import routes
    from app.main import app as application

    settings = application.dependency_overrides[get_settings]()
    assessed = routes._assess(settings, routes.get_store(), "crew-01", None, None, None)
    assert assessed.cycle is not None and assessed.cycle.offset is not None
    offset = assessed.cycle.offset
    adjusted = trends_by_indicator(assessed.observations, phase_offset=offset)
    plain = trends_by_indicator(assessed.observations)
    assert assessed.trends == adjusted != plain
    assert assessed.deviations == BaselineEngine().evaluate_rolling(
        assessed.observations, phase_offset=offset
    ) != BaselineEngine().evaluate_rolling(assessed.observations)

    # Tierra, con un corte anterior al último inicio: tres inicios aún, la fase de entonces.
    earlier = (start + dt.timedelta(days=20)).isoformat()
    ground = client.get("/api/baseline-profile", params={"until": earlier}).json()
    assert ground["cycle_phase"]["phase"] == "luteal"

    # Supresión (3), perimenopausia (4) y 1,5 cierran la puerta: lo mismo que sin ajuste.
    for step, value in enumerate((3.0, 4.0, 1.5)):
        _post(client, "reproductive-status", value, start + dt.timedelta(days=44, hours=step))
        shut = _status(client)
        assert shut["cycle_phase"] == {
            "applied": False, "phase": None, "reason": gate.NOT_REGULAR,
        }, value
        assert _verdict(shut) == _verdict(closed), value


def test_what_cannot_open_the_gate_does_not(client: TestClient) -> None:
    """Un asiento de sexo mal formado cierra la puerta sin tumbar el estado; un inicio predicho o
    de baja confianza no cuenta (la regla del estado sobre el tipo de lectura)."""
    from app.api import cycle_phase as gate
    from app.api.routes import get_store, identity_for
    from app.core.storage import CREW_SEX_ENTRY_TYPE

    start = dt.datetime.combine(get_settings().mission_start, dt.time(), tzinfo=dt.UTC)
    assert client.post("/api/simulate", params={"days": 45, "cycle": True}).status_code == 201
    get_store()._record_action(
        CREW_SEX_ENTRY_TYPE,
        {"subject": "crew-01", "sex": "x", "declared_by": "Ane"},
        identity_for("crew-console"),
    )
    assert _status(client)["cycle_phase"]["reason"] == gate.MALFORMED

    assert client.post(
        "/api/crew/sex", json={"sex": "female", "declared_by": "Ane"}
    ).status_code == 201
    _post(client, "reproductive-status", 1.0, start - dt.timedelta(days=60))
    for k in (-2, -1):
        _post(client, "menstruation-start", 1.0, start + dt.timedelta(days=28 * k))
    predicted = {"observation_type": "predicted", "model_version": "app-del-ciclo@1"}
    for extra in (predicted, {"confidence": 0.1}):
        response = client.post("/api/observations", json={
            "key": "menstruation-start", "value": 1.0, "source": "manual",
            "effective": start.isoformat(), **extra,
        })
        assert response.status_code == 201, response.text
        found = _status(client)["cycle_phase"]
        assert found["applied"] is False and "faltan inicios de regla" in found["reason"], extra
    _post(client, "menstruation-start", 1.0, start)
    assert _status(client)["cycle_phase"]["applied"] is True
