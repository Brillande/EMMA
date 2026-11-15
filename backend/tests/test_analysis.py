"""Motor de analisis: linea base, tendencia y riesgo.

Las pruebas de extremo a extremo alimentan el motor con escenarios del simulador
y exigen que salte la alerta correcta. Son la verificacion documentada que exige
IEC 62304 para la funcion clinica del sistema.
"""

import datetime as dt
import math
from dataclasses import replace

import pytest

from app.analysis.baseline import (
    MIN_SAMPLES,
    BaselineEngine,
    Severity,
    compute_baseline,
)
from app.analysis.risk import (
    RiskEngine,
    RiskLevel,
    combine_findings,
    isolation_factor,
    level_for,
    min_severe_readings,
    representative_deviation,
)
from app.analysis.trend import Direction, linear_trend, trends_by_indicator
from app.environment.donki import EventType, SolarEvent
from app.environment.donki import Severity as SolarSeverity
from app.environment.ephemeris import CommsWindow
from app.ingest.codes import Domain
from app.ingest.fhir import observation
from app.ingest.simulator import PhysiologicalSimulator, Scenario

NOW = dt.datetime(2026, 11, 14, 8, 0, tzinfo=dt.UTC)


def obs_series(key: str, values: list[float], subject: str = "crew-01") -> list:
    return [
        observation(key, value, NOW + dt.timedelta(hours=i), subject, "test")
        for i, value in enumerate(values)
    ]


# --------------------------------------------------------------------------- #
# Linea base
# --------------------------------------------------------------------------- #


def test_baseline_uses_robust_statistics() -> None:
    """Un artefacto no debe arrastrar el centro ni inflar la dispersion."""
    clean = [60.0] * 30
    with_artifact = [*clean, 250.0]  # lectura imposible por mal contacto

    baseline_clean = compute_baseline("heart-rate", clean)
    baseline_dirty = compute_baseline("heart-rate", with_artifact)

    assert baseline_dirty.center == baseline_clean.center
    # Con media y desviacion tipica, ese 250 habria disparado la dispersion.
    assert baseline_dirty.spread == baseline_clean.spread


def test_baseline_needs_enough_samples() -> None:
    assert not compute_baseline("heart-rate", [60.0] * (MIN_SAMPLES - 1)).established
    assert compute_baseline("heart-rate", [60.0] * MIN_SAMPLES).established


def test_empty_baseline() -> None:
    baseline = compute_baseline("heart-rate", [])
    assert baseline.samples == 0
    assert not baseline.established


def test_personal_baseline_beats_population_range() -> None:
    """Un pulso de 70 es nominal para quien tiene base 68 y alto para quien tiene 55."""
    engine = BaselineEngine()
    engine.fit(obs_series("heart-rate", [55.0 + (i % 3) for i in range(150)], "atleta"))
    engine.fit(obs_series("heart-rate", [68.0 + (i % 3) for i in range(150)], "normal"))

    reading_atleta = observation("heart-rate", 70.0, NOW, "atleta", "test")
    reading_normal = observation("heart-rate", 70.0, NOW, "normal", "test")

    assert engine.evaluate(reading_atleta).is_concerning
    assert not engine.evaluate(reading_normal).is_concerning


def test_falls_back_to_population_range_without_baseline() -> None:
    engine = BaselineEngine()
    deviation = engine.evaluate(observation("heart-rate", 190.0, NOW, "crew-99", "test"))
    assert deviation.used_population_range
    assert deviation.is_concerning


def test_deviation_respects_concerning_direction() -> None:
    """Que la saturacion de oxigeno suba no es un hallazgo."""
    engine = BaselineEngine()
    engine.fit(obs_series("oxygen-saturation", [95.0 + (i % 2) * 0.2 for i in range(150)]))

    high = engine.evaluate(observation("oxygen-saturation", 99.5, NOW, "crew-01", "t"))
    low = engine.evaluate(observation("oxygen-saturation", 89.0, NOW, "crew-01", "t"))

    assert not high.is_concerning
    assert low.is_concerning
    assert low.direction == "low"


def test_severity_comes_from_empirical_quantiles_not_sigmas() -> None:
    """La gravedad la decide el percentil real, no un supuesto de normalidad.

    La validacion externa mostro que |z| >= 2 se excedia en el 22 % de las
    lecturas reales, no en el 4,55 % que predice la normalidad.
    """
    from app.analysis.baseline import _severity_from_quantiles
    from app.ingest.codes import get

    # Base amplia: permite estimar cuantiles finos.
    values = [60.0 + (i % 20) * 0.5 for i in range(1200)]
    baseline = compute_baseline("heart-rate", values)
    code = get("heart-rate")

    inside, _ = _severity_from_quantiles(baseline.center, baseline, code)
    extreme, _ = _severity_from_quantiles(max(values) + 50, baseline, code)

    assert inside is Severity.NONE
    assert extreme is Severity.SEVERE


def test_thin_baseline_claims_nothing() -> None:
    """Con pocas muestras no se puede afirmar un percentil fino.

    Con 40 observaciones, p99 y p99,9 colapsan en el maximo: decir "grave"
    seria inventarse una precision que la muestra no tiene.
    """
    from app.analysis.baseline import _severity_from_quantiles
    from app.ingest.codes import get

    baseline = compute_baseline("heart-rate", [60.0 + (i % 5) for i in range(40)])
    severity, _ = _severity_from_quantiles(200.0, baseline, get("heart-rate"))

    assert severity is Severity.NONE, (
        "con 40 muestras no se puede afirmar ningún cuantil; antes esto "
        "devolvia 'leve' por estar fuera del rango visto, y eso producia el "
        "grueso del residuo de falsa alarma"
    )


def test_wide_baseline_can_claim_severe() -> None:
    from app.analysis.baseline import _severity_from_quantiles
    from app.ingest.codes import get

    baseline = compute_baseline("heart-rate", [60.0 + (i % 30) * 0.3 for i in range(1500)])
    severity, _ = _severity_from_quantiles(200.0, baseline, get("heart-rate"))

    assert severity is Severity.SEVERE


def test_flat_series_does_not_produce_infinite_z() -> None:
    """Una serie momentaneamente plana no debe generar una cascada de alertas."""
    engine = BaselineEngine()
    engine.fit(obs_series("heart-rate", [60.0] * 150))
    deviation = engine.evaluate(observation("heart-rate", 61.0, NOW, "crew-01", "t"))
    assert abs(deviation.z_score) < 1000


def test_deviation_describes_itself_readably() -> None:
    engine = BaselineEngine()
    engine.fit(obs_series("heart-rate", [60.0 + (i % 4) for i in range(150)]))
    text = engine.evaluate(observation("heart-rate", 95.0, NOW, "crew-01", "t")).describe()
    assert "Frecuencia cardiaca" in text
    assert "por encima" in text


# --------------------------------------------------------------------------- #
# Tendencia
# --------------------------------------------------------------------------- #


def test_detects_sustained_rise() -> None:
    times = [NOW + dt.timedelta(days=i) for i in range(20)]
    values = [60.0 + i * 0.5 for i in range(20)]
    trend = linear_trend("heart-rate", times, values)

    assert trend is not None
    assert trend.significant
    assert trend.direction is Direction.RISING
    assert trend.slope_per_week == pytest.approx(3.5, abs=0.01)


def test_noise_is_not_a_trend() -> None:
    """Sin contraste de significancia, cualquier serie ruidosa 'tendria' pendiente."""
    times = [NOW + dt.timedelta(days=i) for i in range(20)]
    values = [60.0, 65.0, 58.0, 62.0, 61.0, 59.0, 64.0, 60.0, 63.0, 57.0] * 2
    trend = linear_trend("heart-rate", times, values)

    assert trend is not None
    assert not trend.significant
    assert trend.direction is Direction.STABLE


def test_trend_needs_enough_points() -> None:
    times = [NOW + dt.timedelta(days=i) for i in range(4)]
    assert linear_trend("heart-rate", times, [60.0, 61.0, 62.0, 63.0]) is None


def test_trend_needs_time_span() -> None:
    times = [NOW] * 12
    assert linear_trend("heart-rate", times, [60.0 + i for i in range(12)]) is None


def test_trend_direction_matters_for_concern() -> None:
    """Que el sueno suba no preocupa; que baje, si."""
    times = [NOW + dt.timedelta(days=i) for i in range(20)]
    rising = linear_trend("sleep-duration", times, [6.0 + i * 0.05 for i in range(20)])
    falling = linear_trend("sleep-duration", times, [8.0 - i * 0.05 for i in range(20)])

    assert rising is not None and not rising.is_concerning
    assert falling is not None and falling.is_concerning


def test_a_drift_that_starts_late_is_seen() -> None:
    """Una deriva que empieza a mitad de mision tiene que verse.

    Con la recta sobre toda la historia, una deriva de pulso al umbral clinico
    que arrancaba el dia 35 **no se detectaba nunca** (0 de 20 tripulantes): las
    semanas estables la diluian. Con la ventana de 21 dias y el contraste contra
    el umbral, 20 de 20, a los 16 dias de mediana. Aqui, 1,5 veces el umbral,
    escalada por el ritmo circadiano como la produce el simulador.
    """
    from app.analysis.trend import RELEVANCE_HORIZON_WEEKS
    from app.ingest.codes import get
    from app.ingest.simulator import CIRCADIAN_RATIO

    code = get("heart-rate")
    assert code.reference_high is not None and code.reference_low is not None
    threshold_per_day = (
        (code.reference_high - code.reference_low) * 0.15 / (RELEVANCE_HORIZON_WEEKS * 7)
    )
    observations = list(
        PhysiologicalSimulator(scenario=Scenario.NOMINAL, seed=0).generate(
            days=70, samples_per_day=24, keys=["heart-rate"]
        )
    )
    start = min(o.effective for o in observations)
    onset = start + dt.timedelta(days=35)
    drifted = [
        replace(
            o,
            value=o.value
            + CIRCADIAN_RATIO["heart-rate"].get(o.context.family, 1.0)
            * 1.5
            * threshold_per_day
            * max(0.0, (o.effective - onset).total_seconds() / 86400),
        )
        for o in observations
    ]

    def concerning_on(day: int) -> bool:
        moment = start + dt.timedelta(days=day)
        trend = trends_by_indicator([o for o in drifted if o.effective < moment]).get(
            "heart-rate"
        )
        return bool(trend and trend.is_concerning and trend.direction is Direction.RISING)

    assert not concerning_on(35), "marcada antes de empezar"
    assert concerning_on(50), "15 días después de empezar sigue sin verse"


def test_a_rarely_measured_indicator_keeps_its_trend() -> None:
    """La ventana en dias no puede dejar sin tendencia a lo que se mide poco.

    El PVT dos veces por semana reune 6 lecturas en 21 dias, menos de las 8 que
    exige un ajuste: una deriva de 14 ms/semana —umbral 5,6— pasaba sin verse.
    La ventana se estira hasta sus ultimas 8 lecturas.
    """
    ruido = [3.0, -4.0, 2.0, -1.0, 4.0, -3.0, 1.0, -2.0]
    lecturas = [
        observation(
            "pvt-mean-rt",
            265.0 + 2.0 * (i * 3.5) + ruido[i % len(ruido)],
            NOW + dt.timedelta(days=i * 3.5),
            "crew-01",
            "t",
        )
        for i in range(20)
    ]

    trend = trends_by_indicator(lecturas).get("pvt-mean-rt")

    assert trend is not None, "la ventana de 21 días dejo al PVT sin tendencia"
    assert trend.points == 8
    assert trend.is_concerning


def test_an_estimate_over_the_threshold_is_not_enough_without_confidence() -> None:
    """El caso que separa la regla nueva de la vieja.

    Pendiente estimada a 1,08 veces el umbral, pero con ruido: no hay confianza
    de que la deriva real lo supere. La regla vieja —estimacion puntual sobre el
    umbral y pendiente distinta de cero— la marcaba; esta no.
    """
    ruido = [1.0, -1.0, 0.5, -0.5, 1.0, -0.8, 0.2]
    umbral_por_dia = 50 * 0.15 / 28  # pulso: 15 % de 50-100 lpm a 4 semanas
    times = [NOW + dt.timedelta(days=i) for i in range(21)]
    values = [60.0 + 1.1 * umbral_por_dia * i + ruido[i % 7] for i in range(21)]
    trend = linear_trend("heart-rate", times, values)

    assert trend is not None
    assert trend.significant and trend.clinically_relevant, "la regla vieja la marcaria"
    assert trend.standard_error > 0
    assert not trend.confidently_relevant
    assert not trend.is_concerning
    assert "sin confianza" in trend.describe()


def test_a_guideline_indicator_trend_is_described_not_alerted() -> None:
    """Una guia no es un umbral de alarma, tampoco por la via de tendencia.

    El ejercicio resistivo cayendo 8 min/semana es una deriva real y clara, pero
    su umbral de relevancia sale de una recomendacion, no de gente sana.
    """
    times = [NOW + dt.timedelta(days=i) for i in range(21)]
    values = [95.0 - 8.0 / 7 * i for i in range(21)]
    trend = linear_trend("exercise-minutes", times, values)

    assert trend is not None
    assert trend.significant and trend.confidently_relevant
    assert not trend.is_concerning
    assert "bajando" in trend.describe()


def test_a_drift_below_the_threshold_is_not_concerning_however_certain() -> None:
    """Con cientos de lecturas cualquier deriva es "significativa". No basta.

    Se contrasta contra el umbral clinico, no contra cero: una pendiente muy
    segura pero por debajo de lo relevante no preocupa.
    """
    times = [NOW + dt.timedelta(hours=i) for i in range(24 * 21)]
    # Pulso: umbral 15 % de 50-100 lpm a 4 semanas = 1,875 lpm/semana. Aqui, 1,5.
    values = [60.0 + 1.5 / (7 * 24) * i for i in range(len(times))]
    trend = linear_trend("heart-rate", times, values)

    assert trend is not None
    assert trend.significant
    assert not trend.is_concerning


def test_trends_by_indicator_respects_window() -> None:
    """La ventana debe descartar el historial antiguo, no mezclarlo con lo reciente."""
    old = [
        observation("heart-rate", 60.0, NOW + dt.timedelta(days=i), "crew-01", "t")
        for i in range(12)
    ]
    recent_rise = [
        observation("heart-rate", 60.0 + i * 2.0, NOW + dt.timedelta(days=100 + i), "crew-01", "t")
        for i in range(12)
    ]

    windowed = trends_by_indicator([*old, *recent_rise], window=dt.timedelta(days=15))
    full = trends_by_indicator([*old, *recent_rise], window=None)

    # Dentro de la ventana solo entran las 12 muestras recientes.
    assert windowed["heart-rate"].points == 12
    assert windowed["heart-rate"].slope_per_day == pytest.approx(2.0, abs=0.01)
    # Sin ventana, las 24 muestras diluyen la pendiente real.
    assert full["heart-rate"].points == 24
    assert full["heart-rate"].slope_per_day < windowed["heart-rate"].slope_per_day


def test_statistical_significance_is_not_clinical_significance() -> None:
    """Con muchas muestras, cualquier deriva minuscula sale significativa."""
    times = [NOW + dt.timedelta(hours=i * 6) for i in range(200)]
    # Caida de 0,37 %/semana en eficiencia de sueno: real pero irrelevante.
    values = [88.0 - i * (0.37 / 7 / 4) for i in range(200)]
    trend = linear_trend("sleep-efficiency", times, values)

    assert trend is not None
    assert trend.significant, "la pendiente es estadisticamente detectable"
    assert not trend.clinically_relevant, "pero no alcanza el umbral clínico"
    assert not trend.is_concerning
    assert "umbral clínico" in trend.describe()


def test_clinically_relevant_trend_is_concerning() -> None:
    times = [NOW + dt.timedelta(hours=i * 6) for i in range(200)]
    # Caida de ~1 %/dia: a cuatro semanas son 28 puntos de eficiencia.
    values = [88.0 - i * 0.25 for i in range(200)]
    trend = linear_trend("sleep-efficiency", times, values)

    assert trend is not None
    assert trend.significant
    assert trend.clinically_relevant
    assert trend.is_concerning


# --------------------------------------------------------------------------- #
# Riesgo
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, RiskLevel.NOMINAL),
        (25, RiskLevel.WATCH),
        (50, RiskLevel.CONCERN),
        (80, RiskLevel.CRITICAL),
    ],
)
def test_level_thresholds(score: float, expected: RiskLevel) -> None:
    assert level_for(score) is expected


def test_isolation_factor_grows_with_delay() -> None:
    near = CommsWindow(dt.date(2026, 11, 14), 0.01, 0.1, "301")
    mars = CommsWindow(dt.date(2026, 11, 14), 1.324, 11.01, "499")
    far = CommsWindow(dt.date(2028, 2, 10), 2.348, 19.53, "499")

    assert isolation_factor(None) == 1.0
    assert isolation_factor(near) == 1.0
    assert 1.0 < isolation_factor(mars) < isolation_factor(far)


def test_isolation_factor_saturates() -> None:
    """Pasado cierto retardo, mas distancia ya no cambia la conducta."""
    far = CommsWindow(dt.date(2028, 2, 10), 2.348, 19.53, "499")
    absurd = CommsWindow(dt.date(2030, 1, 1), 40.0, 330.0, "999")
    assert isolation_factor(absurd) == pytest.approx(isolation_factor(far), abs=0.06)


def test_isolation_raises_the_same_finding() -> None:
    """El mismo hallazgo clinico escala antes cuando no hay ayuda cerca."""
    engine = BaselineEngine()
    engine.fit(obs_series("heart-rate", [60.0 + (i % 4) for i in range(150)]))
    deviations = [engine.evaluate(observation("heart-rate", 78.0, NOW, "crew-01", "t"))]

    risk = RiskEngine()
    near_earth = risk.assess("crew-01", deviations)
    deep_space = risk.assess(
        "crew-01", deviations, comms=CommsWindow(dt.date(2028, 2, 10), 2.348, 19.53, "499")
    )

    assert deep_space.domains[Domain.CARDIOVASCULAR].score > (
        near_earth.domains[Domain.CARDIOVASCULAR].score
    )


def test_repeated_readings_count_once() -> None:
    """Cien lecturas altas del mismo indicador siguen siendo un hallazgo, no cien."""
    engine = BaselineEngine()
    engine.fit(obs_series("heart-rate", [60.0 + (i % 4) for i in range(150)]))
    once = [engine.evaluate(observation("heart-rate", 95.0, NOW, "crew-01", "t"))]
    hundred = [
        engine.evaluate(
            observation("heart-rate", 95.0, NOW + dt.timedelta(minutes=i), "crew-01", "t")
        )
        for i in range(100)
    ]

    risk = RiskEngine()
    assert (
        risk.assess("crew-01", hundred).domains[Domain.CARDIOVASCULAR].score
        == risk.assess("crew-01", once).domains[Domain.CARDIOVASCULAR].score
    )


def test_solar_event_drives_radiation_risk() -> None:
    event = SolarEvent(
        event_id="2026-11-19T00:00:00-SEP-001",
        event_type=EventType.SEP,
        time=NOW,
        severity=SolarSeverity.SEVERE,
        instruments=(),
        linked_event_ids=(),
        flare_class=None,
        link="",
    )
    status = RiskEngine().assess("crew-01", [], solar_events=[event])

    assert status.active_solar_event is event
    assert status.domains[Domain.RADIATION].level is not RiskLevel.NOMINAL


def test_cumulative_dose_drives_radiation_risk() -> None:
    status = RiskEngine(dose_limit_msv=600).assess(
        "crew-01", [], cumulative_dose_msv=450.0
    )
    assert status.dose_fraction == pytest.approx(0.75)
    assert status.domains[Domain.RADIATION].level is not RiskLevel.NOMINAL


def test_overall_level_takes_the_worst_domain() -> None:
    """Un riesgo critico no se promedia con dos dominios nominales."""
    status = RiskEngine().assess("crew-01", [], cumulative_dose_msv=900.0)
    assert status.domains[Domain.CARDIOVASCULAR].level is RiskLevel.NOMINAL
    assert status.overall_level is RiskLevel.CRITICAL


def _deviation(z: float, key: str = "heart-rate"):
    from app.analysis.baseline import Baseline, Deviation
    from app.ingest.codes import get

    magnitude = abs(z)
    if magnitude >= 4.0:
        severity = Severity.SEVERE
    elif magnitude >= 3.0:
        severity = Severity.MODERATE
    elif magnitude >= 2.0:
        severity = Severity.MILD
    else:
        severity = Severity.NONE
    get(key)
    return Deviation(
        subject="crew-01",
        key=key, value=0.0, effective=NOW, z_score=z, severity=severity,
        direction="high" if z >= 0 else "low",
        baseline=Baseline(key, 0.0, 1.0, 40), used_population_range=False,
    )


def test_isolated_outlier_is_noise_not_a_finding() -> None:
    """Una sola lectura a 3,5 sigma entre veinte es lo que produce el azar."""
    readings = [_deviation(0.5) for _ in range(19)] + [_deviation(3.5)]
    assert representative_deviation(readings) is None


def test_persistent_deviation_is_a_finding() -> None:
    """Si la mitad de las lecturas se desvian, ya no es ruido."""
    readings = [_deviation(2.5) for _ in range(10)] + [_deviation(0.5) for _ in range(10)]
    found = representative_deviation(readings)
    assert found is not None
    assert found.severity is Severity.MILD


def test_a_single_extreme_reading_is_not_evidence() -> None:
    """Una lectura grave suelta no basta.

    Cuando la red de seguridad dejaba pasar una sola, **9 de 22 sujetos sanos
    acababan en nivel CONCERN**, todos por un unico hallazgo con 0,4 % de
    persistencia. En los sanos de MMASH, el 0,49 % de las lecturas de pulso cruza
    un limite de peligro: en una ventana de 280 se esperan 1,4, asi que ver una
    no sorprende. (La justificacion original hablaba del percentil 99,9 y de
    0,25 por azar; ese suceso no ocurre en ningun dato disponible — ver
    `risk._HEALTHY_SEVERE_RATE`.)
    """
    readings = [_deviation(0.5) for _ in range(19)] + [_deviation(8.0)]
    assert representative_deviation(readings) is None


def test_a_burst_of_severe_readings_reports_without_persistence() -> None:
    """Pero una rafaga si: un episodio agudo corto es una fraccion pequena de
    una ventana larga y nunca alcanzaria el porcentaje de persistencia."""
    readings = [_deviation(0.5) for _ in range(40)] + [_deviation(8.0) for _ in range(3)]
    found = representative_deviation(readings)

    assert found is not None, "tres lecturas graves deberian bastar"
    assert found.severity is Severity.SEVERE
    # La persistencia por si sola no llegaria: 3 de 43 es el 7 %, umbral 30 %.
    assert 3 / 43 < 0.30


def test_a_long_window_demands_a_bigger_burst() -> None:
    """Tres graves entre 400 lecturas no es la evidencia que es entre 280.

    Un wearable continuo produce ventanas de cientos o miles de lecturas; con la
    constante 3 el azar la alcanzaba casi seguro.
    """
    def ventana(graves: int) -> list:
        return [_deviation(0.5) for _ in range(400 - graves)] + [
            _deviation(8.0) for _ in range(graves)
        ]

    assert representative_deviation(ventana(3)) is None
    assert representative_deviation(ventana(4)) is not None


def test_detection_does_not_depend_on_sampling_rate() -> None:
    """Un motor no puede perder una arritmia por recibir mas datos.

    Por el camino desplegado —ventana actual de `/api/status`— la arritmia se
    detectaba a 8 y 24 muestras/dia y **se perdia a 4 y a 12**: dos lecturas
    graves en 25 no llegaban al `3` fijo, y tres en 49 si.

    La mitad "sano" NO prueba la regla de rafaga: el escenario nominal no produce
    ninguna lectura grave a estas frecuencias, asi que pasaria incluso exigiendo
    una. Vigila que nada mas del camino desplegado alarme; lo que protege de la
    lectura suelta es `test_an_isolated_crossing_in_a_short_window_is_not_a_burst`.
    """
    from app.api.routes import CURRENT_WINDOW

    def dominios_marcados(scenario: Scenario, samples_per_day: int) -> set[Domain]:
        observations = list(
            PhysiologicalSimulator(scenario=scenario).generate(
                days=40, samples_per_day=samples_per_day
            )
        )
        cutoff = max(o.effective for o in observations) - CURRENT_WINDOW
        actuales = [
            d
            for d in BaselineEngine().evaluate_rolling(observations)
            if d.effective >= cutoff
        ]
        status = RiskEngine().assess(
            "crew-01", actuales, trends=trends_by_indicator(observations)
        )
        return {n for n, r in status.domains.items() if r.level is not RiskLevel.NOMINAL}

    for samples_per_day in (4, 8, 12, 24):
        assert dominios_marcados(Scenario.ARRHYTHMIA, samples_per_day) == {
            Domain.CARDIOVASCULAR
        }, f"arritmia perdida a {samples_per_day}/día"
        assert dominios_marcados(Scenario.NOMINAL, samples_per_day) == set(), (
            f"falsa alarma a {samples_per_day}/día"
        )


def test_a_healthy_crew_member_gets_no_concern_over_a_mission() -> None:
    """Falsas alertas por tripulante-mes, que es como se sufren de verdad.

    Una tasa por lectura no dice cuanto molesta el sistema: `/api/status` se
    reevalua sin parar sobre una ventana de dos dias y 24 indicadores a la vez.
    Aqui se recorre el camino desplegado dia a dia durante 56 dias de mision
    nominal. Medido el 2026-09-21 sobre 50 tripulantes simulados: **0 dias en
    CONCERN**. El WATCH bajo del 7,4 % al 0,4 % de los dias cuando la tendencia
    paso a contrastarse contra el umbral clinico y no contra cero (ver
    `trend.py`). Y subio otra vez cuando se decidio que una deriva confirmada
    llegue sola a la tripulacion (`risk._TREND_POINTS` = 20): la adaptacion
    circadiana real de las semanas 2-3 sale como WATCH, igual que ya salia con el
    retardo de Marte. En estas tres semillas, evaluando en dias alternos: 12 de
    84 (antes de las dos correcciones, 11; entre ambas, 0). CONCERN sigue en 0.
    """
    from app.api.routes import CURRENT_WINDOW

    concern = watch = evaluated = 0
    for seed in (0, 1, 2):
        observations = sorted(
            PhysiologicalSimulator(scenario=Scenario.NOMINAL, seed=seed).generate(
                days=70, samples_per_day=24
            ),
            key=lambda o: o.effective,
        )
        deviations = BaselineEngine().evaluate_rolling(observations)
        start = observations[0].effective
        for day in range(14, 70, 2):  # dias alternos: la ventana actual es de dos
            now = start + dt.timedelta(days=day + 1)
            past = [o for o in observations if o.effective < now]
            cutoff = past[-1].effective - CURRENT_WINDOW
            status = RiskEngine().assess(
                "crew-01",
                [d for d in deviations if cutoff <= d.effective < now],
                trends=trends_by_indicator(past),
            )
            evaluated += 1
            concern += status.overall_level in (RiskLevel.CONCERN, RiskLevel.CRITICAL)
            watch += status.overall_level is not RiskLevel.NOMINAL

    assert concern == 0, f"{concern} días en CONCERN sobre un tripulante sano"
    assert evaluated == 84
    assert watch <= 12, f"WATCH en {watch} de {evaluated} evaluaciones (medido: 12)"


def test_an_isolated_crossing_in_a_short_window_is_not_a_burst() -> None:
    """Bajar la exigencia a 2 en ventanas cortas no puede dejar pasar una sola.

    Un cruce aislado de limite es con mas probabilidad un artefacto que un
    evento, por corta que sea la ventana. Desde 4 lecturas: con menos, una sola
    ya es el 30 % de persistencia y la reporta esa otra regla, no esta.
    """
    for window in (4, 8, 25, 49):
        readings = [_deviation(0.5) for _ in range(window - 1)] + [_deviation(8.0)]
        assert representative_deviation(readings) is None, window


def test_burst_threshold_survives_a_wearable_window() -> None:
    """Un wearable a 1 Hz reune decenas de miles de lecturas en la ventana actual.

    Con `math.comb` el calculo desbordaba el float a partir de ~22 000 lecturas
    —unas 6 h a 1 Hz— y `/api/status` habria respondido 500 justo con el
    dispositivo que mas datos da.
    """
    from app.analysis.risk import _HEALTHY_SEVERE_RATE

    for readings in (21_891, 22_000, 172_800):
        k = min_severe_readings(readings)
        # Algo por encima de lo que el azar da de media, no un numero absurdo.
        assert readings * _HEALTHY_SEVERE_RATE < k < 1.2 * readings * _HEALTHY_SEVERE_RATE

    readings = [_deviation(0.5) for _ in range(21_999)] + [_deviation(8.0)]
    assert representative_deviation(readings) is None


def test_no_deviations_is_no_finding() -> None:
    assert representative_deviation([]) is None
    assert representative_deviation([_deviation(0.5) for _ in range(10)]) is None


def test_many_mild_findings_do_not_reach_critical() -> None:
    """Muchos hallazgos leves no equivalen a una emergencia, por muchos que sean."""
    assert level_for(combine_findings([10.0] * 4)) is not RiskLevel.CRITICAL
    assert level_for(combine_findings([10.0] * 50)) is not RiskLevel.CRITICAL


def test_one_severe_finding_outweighs_several_mild() -> None:
    assert combine_findings([45.0]) > combine_findings([10.0] * 5)


def test_critical_requires_real_severity_not_accumulation() -> None:
    """Solo la gravedad real llega a critico, por muchos hallazgos leves que haya."""
    assert level_for(combine_findings([10.0] * 20)) is not RiskLevel.CRITICAL
    assert level_for(combine_findings([45.0, 45.0, 25.0])) is RiskLevel.CRITICAL


def test_combine_findings_is_order_independent() -> None:
    assert combine_findings([10.0, 45.0, 25.0]) == combine_findings([45.0, 25.0, 10.0])


def test_combine_findings_empty() -> None:
    assert combine_findings([]) == 0.0


def test_dose_at_career_limit_is_critical_on_its_own() -> None:
    """Rebasar el limite de dosis de carrera termina una mision."""
    status = RiskEngine(dose_limit_msv=600).assess("crew-01", [], cumulative_dose_msv=600.0)
    assert status.domains[Domain.RADIATION].level is RiskLevel.CRITICAL


def test_nominal_status_when_nothing_is_wrong() -> None:
    status = RiskEngine().assess("crew-01", [])
    assert status.overall_level is RiskLevel.NOMINAL
    assert not status.domains_needing_attention()


def test_isolation_does_not_inflate_radiation_dose() -> None:
    """La distancia no cambia la dosis recibida; solo lo que cuesta equivocarse."""
    risk = RiskEngine()
    far = CommsWindow(dt.date(2028, 2, 10), 2.348, 19.53, "499")
    near = risk.assess("crew-01", [], cumulative_dose_msv=300.0)
    deep = risk.assess("crew-01", [], comms=far, cumulative_dose_msv=300.0)
    assert deep.domains[Domain.RADIATION].score == near.domains[Domain.RADIATION].score


# --------------------------------------------------------------------------- #
# Extremo a extremo: escenario del simulador -> alerta correcta
# --------------------------------------------------------------------------- #


def _status_for(scenario: Scenario, days: int = 40):
    """Modo mision: base movil para lo agudo, tendencia para lo cronico.

    El estado se evalua sobre las lecturas **recientes**, no sobre toda la
    mision: la pregunta es como esta la tripulacion ahora, y el historial ya lo
    interpreta el analisis de tendencia.
    """
    sim = PhysiologicalSimulator(scenario=scenario, seed=11)
    everything = list(sim.generate(days=days, samples_per_day=4))

    engine = BaselineEngine()
    deviations = engine.evaluate_rolling(everything)

    latest = max(obs.effective for obs in everything)
    recent_keys = {
        (obs.key, obs.value)
        for obs in everything
        if obs.effective >= latest - dt.timedelta(days=2)
    }
    current = [dev for dev in deviations if (dev.key, dev.value) in recent_keys]
    trends = trends_by_indicator(everything)

    return RiskEngine().assess("crew-01", current, trends=trends)


def test_insomnia_scenario_raises_behavioral_risk() -> None:
    status = _status_for(Scenario.PROGRESSIVE_INSOMNIA)
    assert status.domains[Domain.BEHAVIORAL].level is not RiskLevel.NOMINAL
    assert status.domains[Domain.BEHAVIORAL].drivers


def test_deconditioning_scenario_raises_cardiovascular_risk() -> None:
    status = _status_for(Scenario.CARDIOVASCULAR_DECONDITIONING)
    assert status.domains[Domain.CARDIOVASCULAR].level is not RiskLevel.NOMINAL


def test_immune_scenario_raises_immune_risk() -> None:
    status = _status_for(Scenario.IMMUNE_REACTIVATION)
    assert status.domains[Domain.IMMUNE].level is not RiskLevel.NOMINAL


def test_nominal_scenario_stays_calm() -> None:
    """El caso que importa para la confianza: sin hallazgos, sin alarmas."""
    status = _status_for(Scenario.NOMINAL)
    assert status.domains[Domain.BEHAVIORAL].level is RiskLevel.NOMINAL
    assert status.domains[Domain.IMMUNE].level is RiskLevel.NOMINAL


# --------------------------------------------------------------------------- #
# La confianza de medida tiene que hacer algo
# --------------------------------------------------------------------------- #


def test_low_confidence_cannot_sustain_a_severe_finding() -> None:
    """Afirmar 'grave' desde una lectura que el sensor marca como dudosa es
    afirmar mas de lo que se sabe."""
    from app.analysis.baseline import Severity, cap_for_confidence

    assert cap_for_confidence(Severity.SEVERE, 0.3) is Severity.MILD
    assert cap_for_confidence(Severity.MODERATE, 0.3) is Severity.MILD


def test_good_confidence_leaves_severity_intact() -> None:
    from app.analysis.baseline import Severity, cap_for_confidence

    assert cap_for_confidence(Severity.SEVERE, 1.0) is Severity.SEVERE


def test_a_clean_reading_is_never_promoted() -> None:
    from app.analysis.baseline import Severity, cap_for_confidence

    assert cap_for_confidence(Severity.NONE, 0.1) is Severity.NONE


def test_low_confidence_readings_stay_out_of_the_baseline() -> None:
    """Una medida dudosa que contamina la referencia vuelve ciego al sistema
    justo despues de un mal dato."""
    from app.ingest.fhir import observation as make

    clean = [
        make("heart-rate", 60.0, NOW + dt.timedelta(minutes=i), "crew-01", "w")
        for i in range(40)
    ]
    dirty = [
        make(
            "heart-rate", 200.0, NOW + dt.timedelta(minutes=40 + i), "crew-01", "w",
            confidence=0.2,
        )
        for i in range(40)
    ]
    later = make("heart-rate", 62.0, NOW + dt.timedelta(hours=20), "crew-01", "w")

    engine = BaselineEngine()
    results = engine.evaluate_rolling(
        [*clean, *dirty, later],
        window=dt.timedelta(days=1),
        lag=dt.timedelta(minutes=1),
    )

    final = results[-1]
    assert final.baseline is not None
    # Si las lecturas sucias hubieran entrado, el centro estaria cerca de 130.
    assert final.baseline.center == pytest.approx(60.0, abs=2.0)


def test_established_matches_the_weakest_claim() -> None:
    """Una base esta establecida exactamente cuando puede afirmar algo.

    Desacoplar estas dos constantes deja bases "establecidas" pero incapaces de
    alcanzar ningun corte de cuantil: un estado incoherente que producia el
    grueso del residuo de falsa alarma (213 de 220 lecturas marcadas usaban una
    base de menos de 100 muestras, mediana 30).
    """
    from app.analysis.baseline import _SAMPLES_FOR_SEVERITY, MIN_SAMPLES, Severity

    assert _SAMPLES_FOR_SEVERITY[Severity.MILD] <= MIN_SAMPLES, (
        "hay bases que se consideran establecidas y no pueden sostener ni el "
        "hallazgo más leve"
    )


# --------------------------------------------------------------------------- #
# La via de tendencia, donde SI se puede validar
# --------------------------------------------------------------------------- #


def test_trend_needs_several_circadian_cycles() -> None:
    """Ajustar una recta a menos de un dia mide fase circadiana, no deriva.

    Medido en MMASH sobre un sujeto sano, el ajuste de 24 h daba -92,9 lpm por
    semana, significativo y relevante. Nadie pierde 93 lpm de pulso a la semana:
    la serie recogia la rama descendente del ciclo diario.
    """
    from app.analysis.trend import MIN_SPAN_DAYS, linear_trend

    times = [NOW + dt.timedelta(hours=i) for i in range(24)]
    values = [80.0 - i * 0.8 for i in range(24)]  # pendiente clara en 23 h

    assert linear_trend("heart-rate", times, values) is None
    assert MIN_SPAN_DAYS >= 2.0, "hace falta más de un ciclo para promediar la fase"


def test_trend_path_works_on_mission_length_data() -> None:
    """Con semanas de datos, la tendencia hace su trabajo — y solo entonces.

    Es la contrapartida de la prueba anterior: el requisito de varios ciclos no
    puede haber desactivado la deteccion de deriva, solo haberla acotado a donde
    tiene sentido.
    """
    nominal = list(
        PhysiologicalSimulator(scenario=Scenario.NOMINAL, seed=5).generate(days=40)
    )
    decon = list(
        PhysiologicalSimulator(
            scenario=Scenario.CARDIOVASCULAR_DECONDITIONING, seed=5
        ).generate(days=40)
    )

    quiet = {k for k, t in trends_by_indicator(nominal).items() if t.is_concerning}
    drifting = {k for k, t in trends_by_indicator(decon).items() if t.is_concerning}

    assert not quiet, f"el escenario nominal no debería dar tendencias: {quiet}"
    assert "heart-rate" in drifting
    assert "orthostatic-drop" in drifting
    # La SDNN no se exige: el escenario la hace derivar 5,5 ms/semana frente a un
    # umbral de 5,62, por debajo de lo que el propio sistema declara relevante.
    # Este test la exigia y pasaba solo cuando el ruido empujaba la estimacion
    # por encima — con 36 de 60 semillas. Lo que se fija es el hecho del modelo,
    # no la no deteccion: si la sensibilidad mejora, esto no debe romper.
    from app.analysis.trend import RELEVANCE_FRACTION_OF_RANGE, RELEVANCE_HORIZON_WEEKS
    from app.ingest.codes import get

    sdnn = get("hrv-sdnn")
    assert sdnn.reference_high is not None and sdnn.reference_low is not None
    umbral_semanal = (
        (sdnn.reference_high - sdnn.reference_low)
        * RELEVANCE_FRACTION_OF_RANGE
        / RELEVANCE_HORIZON_WEEKS
    )
    deriva = PhysiologicalSimulator(
        scenario=Scenario.CARDIOVASCULAR_DECONDITIONING, seed=5
    )._models["hrv-sdnn"].weekly_drift
    assert abs(deriva) < umbral_semanal


# --------------------------------------------------------------------------- #
# El peligro absoluto no depende de conocer al sujeto
# --------------------------------------------------------------------------- #


def test_danger_limit_applies_even_with_a_personal_baseline() -> None:
    """Conocer al tripulante no puede rebajar lo que es peligroso para todos.

    Se vio en el escenario de evento solar: 35 lecturas de dosis por encima del
    limite —pico de 1668 uGy/h contra un limite de 100— y **ningun hallazgo**,
    porque los umbrales de peligro solo se miraban en el respaldo poblacional.
    """
    from app.ingest.fhir import observation as make

    engine = BaselineEngine()
    # Base amplia y estable: el sistema "conoce" al sujeto.
    series = [
        make("absorbed-dose-rate", 12.0 + (i % 5), NOW + dt.timedelta(minutes=i * 5),
             "crew-01", "dosimeter")
        for i in range(400)
    ]
    spike = make(
        "absorbed-dose-rate", 1500.0,
        NOW + dt.timedelta(minutes=400 * 5), "crew-01", "dosimeter",
    )

    results = engine.evaluate_rolling(
        [*series, spike], window=dt.timedelta(days=14), lag=dt.timedelta(minutes=10)
    )
    final = results[-1]

    assert not final.used_population_range, "debería tener base personal"
    assert final.severity is Severity.SEVERE, (
        "una dosis 125 veces por encima del fondo tiene que ser grave aunque el "
        "sujeto tenga línea base"
    )


def test_danger_limit_respects_the_exertion_tier() -> None:
    """150 lpm sentado es un hallazgo; corriendo es normal."""
    from app.analysis.baseline import exceeds_danger_limit
    from app.ingest.fhir import Context
    from app.ingest.fhir import observation as make

    resting = make("heart-rate", 150.0, NOW, "crew-01", "w", context=Context.REST)
    exerting = make("heart-rate", 150.0, NOW, "crew-01", "w", context=Context.ACTIVE)
    maximal = make("heart-rate", 205.0, NOW, "crew-01", "w", context=Context.ACTIVE)

    assert exceeds_danger_limit(resting)
    assert not exceeds_danger_limit(exerting)
    assert exceeds_danger_limit(maximal)


def test_every_scenario_flags_its_own_domain_only() -> None:
    """Con datos de duracion de mision, cada patologia marca lo suyo y nada mas.

    Es la validacion de la via de linea base personal, que MMASH no puede
    ejercitar: con 24 h de datos, el 99,4 % de las desviaciones caen al respaldo
    poblacional y la maquinaria de cuantiles queda dormida.
    """
    from app.analysis.risk import RiskEngine, RiskLevel
    from app.ingest.codes import Domain

    expected = {
        Scenario.NOMINAL: set(),
        # El escenario modela tambien una subida de la carga de sintomas (0,3 por
        # semana, cuatro veces el umbral), que el catalogo asigna al dominio
        # inmune. Antes no se veia: una tendencia sola no llegaba a WATCH. Desde
        # que llega (`risk._TREND_POINTS`), marcarla es detectar lo modelado.
        Scenario.SPE_EVENT: {Domain.RADIATION, Domain.IMMUNE},
        Scenario.PROGRESSIVE_INSOMNIA: {Domain.BEHAVIORAL},
        Scenario.ARRHYTHMIA: {Domain.CARDIOVASCULAR},
        Scenario.CARDIOVASCULAR_DECONDITIONING: {Domain.CARDIOVASCULAR},
        Scenario.IMMUNE_REACTIVATION: {Domain.IMMUNE},
        # Lo que cesa tambien marca lo suyo y nada mas: aqui se juzgan los 40 dias enteros, y
        # el episodio esta dentro.
        Scenario.TRANSIENT_SLEEP_LOSS: {Domain.BEHAVIORAL},
    }

    for scenario, domains in expected.items():
        observations = list(
            PhysiologicalSimulator(scenario=scenario, seed=11).generate(
                days=40, samples_per_day=24
            )
        )
        engine = BaselineEngine()
        status = RiskEngine().assess(
            "crew-01",
            engine.evaluate_rolling(observations),
            trends=trends_by_indicator(observations),
        )
        flagged = {
            domain
            for domain, risk in status.domains.items()
            if risk.level is not RiskLevel.NOMINAL
        }
        assert flagged == domains, f"{scenario}: marco {flagged}, se esperaba {domains}"


def test_assess_refuses_to_mix_two_crew_members() -> None:
    """Un informe es de una persona. Mezclar tripulantes debe fallar, no promediar.

    EMMA vigila a una tripulacion. Sin esta barrera, pasar por error lecturas de
    dos personas produce un informe bien formado, plausible y clinicamente falso:
    atribuye a una los hallazgos de la otra. No hay forma de detectarlo leyendo
    la salida, que es justo lo que lo hace peligroso.
    """
    mias = [_deviation(3.0) for _ in range(10)]
    ajena = replace(_deviation(3.0), subject="crew-02")

    with pytest.raises(ValueError, match="crew-02"):
        RiskEngine().assess("crew-01", [*mias, ajena])


def test_assess_accepts_a_single_subject() -> None:
    """El contrapeso: la barrera no debe estorbar al caso normal."""
    mias = [_deviation(3.0) for _ in range(10)]
    assert RiskEngine().assess("crew-01", mias) is not None


def test_a_deviation_knows_when_it_happened() -> None:
    """Sin el momento no se puede decir "actual", y se decia igualmente.

    El estado de tripulacion seleccionaba las lecturas recientes emparejando por
    `(clave, valor)`. Como las cifras se repiten —960 lecturas de pulso toman 36
    valores distintos, y el mas frecuente sale 99 veces— una desviacion de hace
    semanas contaba como actual en cuanto su valor reaparecia. Medido sobre 40
    dias de escenario nominal: **2582 desviaciones dadas por actuales frente a
    1078 lecturas realmente en ventana**, un inflado de 2,4x.

    Eso contamina numerador y denominador de la persistencia a la vez, que es el
    control central contra la fatiga de alarma.
    """
    simulator = PhysiologicalSimulator(scenario=Scenario.NOMINAL)
    observations = list(simulator.generate(days=40))
    deviations = BaselineEngine().evaluate_rolling(observations)

    latest = max(obs.effective for obs in observations)
    window = dt.timedelta(days=2)
    cutoff = latest - window

    en_ventana = sum(1 for obs in observations if obs.effective >= cutoff)
    actuales = sum(1 for dev in deviations if dev.effective >= cutoff)

    assert actuales == en_ventana, (
        f"{actuales} desviaciones actuales frente a {en_ventana} lecturas en "
        f"ventana: la seleccion no está siendo temporal"
    )


# --------------------------------------------------------------------------- #
# Cuantas lecturas graves hacen una rafaga: depende de cuantas lecturas hay
# --------------------------------------------------------------------------- #


def _chance_of_at_least(k: int, readings: int, chance: float) -> float:
    """P(X >= k) con X ~ Binomial(readings, chance), calculado aparte del motor."""
    below = sum(
        math.comb(readings, i) * chance**i * (1.0 - chance) ** (readings - i)
        for i in range(k)
    )
    return 1.0 - below


@pytest.mark.parametrize("readings", [2, 8, 25, 49, 100, 250, 280, 500, 1000])
def test_burst_threshold_holds_its_declared_surprise(readings: int) -> None:
    """El umbral cumple lo que promete, y es el menor que lo cumple."""
    from app.analysis.risk import _BURST_SURPRISE, _HEALTHY_SEVERE_RATE

    k = min_severe_readings(readings)
    assert k >= 2, "una sola lectura grave nunca es evidencia"
    if k <= readings:
        assert _chance_of_at_least(k, readings, _HEALTHY_SEVERE_RATE) <= _BURST_SURPRISE
    if k > 2:
        assert _chance_of_at_least(k - 1, readings, _HEALTHY_SEVERE_RATE) > _BURST_SURPRISE


def test_burst_threshold_grows_with_the_window() -> None:
    """Mas lecturas, mas graves por azar, mas hacen falta para sorprender."""
    umbrales = [min_severe_readings(n) for n in range(2, 3001)]
    assert umbrales == sorted(umbrales)


def test_burst_threshold_keeps_the_validated_operating_point() -> None:
    """En toda ventana que MMASH produce, sigue exigiendo 3: lo validado no se mueve.

    Las ventanas se midieron instrumentando la regla: 249-303 lecturas. Dos
    intentos anteriores movian este punto para el pulso —con 0,005 en toda la
    ventana, con 0,02 por encima de 284 lecturas— y la sensibilidad externa lo
    acuso las dos veces.
    """
    for readings in range(249, 304):
        assert min_severe_readings(readings) == 3, readings


def test_a_short_window_does_not_demand_a_long_windows_evidence() -> None:
    """Con 25 lecturas, dos graves ya no son azar, y deben contar.

    Con la regla fija de 3, una arritmia simulada a 12 muestras/dia —2 lecturas
    graves entre 25— quedaba en "nominal", y la misma arritmia a 24 muestras/dia
    se detectaba. El motor perdia el evento por tener menos datos, no por tener
    menos evidencia.
    """
    readings = [_deviation(0.5) for _ in range(23)] + [_deviation(8.0) for _ in range(2)]
    found = representative_deviation(readings)
    assert found is not None
    assert found.severity is Severity.SEVERE
