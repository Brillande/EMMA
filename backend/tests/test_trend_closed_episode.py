"""Un episodio cerrado frente a una deriva en curso (§5.38.6, medido y sin adoptar).

La regla se prueba aqui por sus tres condiciones y, de punta a punta, por lo que NO hace: el
estado no la usa; solo la sombra de `/api/status` dice que cerraria.

Las desviaciones se construyen a mano para fijar exactamente lo que la via de desviacion «vio»:
la regla no se prueba aqui contra la base movil, sino contra sus tres condiciones.
"""

from __future__ import annotations

import datetime as dt
import inspect
import math
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.analysis.baseline import Deviation, Severity
from app.analysis.episode import closing
from app.analysis.trend import Settle, Trend, projection, trends_by_indicator
from app.api import routes
from app.api.routes import CURRENT_WINDOW, get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.ingest.fhir import Context, VitalObservation, observation
from app.main import app
from app.validation import report
from app.validation.report import STATE_WINDOW

KEY = "pvt-mean-rt"  # rango 200-350 ms: umbral de relevancia 22,5 ms; preocupa al subir
START = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)
PER_DAY = 4


def _series(
    value_at: Callable[[float], float],
    days: float = 21.0,
    context: Context = Context.REST,
    until: float | None = None,
    noise: float = 1.5,
    wave: bool = False,
) -> list[VitalObservation]:
    out = []
    step = 1.0 / PER_DAY
    day = 0.0
    while day <= (until if until is not None else days) + 1e-9:
        index = int(round(day * PER_DAY))
        jitter = noise * math.sin(1.7 * index) if wave else (noise if index % 2 else -noise)
        out.append(observation(
            KEY, value_at(day) + jitter, START + dt.timedelta(days=day), "crew-01", "test",
            context=context,
        ))
        day += step
    return out


def _deviations(
    series: list[VitalObservation], flagged: Callable[[float], bool]
) -> list[Deviation]:
    """Una desviacion por lectura: moderada y alta donde `flagged(dia)`, ninguna en el resto."""
    out = []
    for obs in series:
        day = (obs.effective - START).total_seconds() / 86400.0
        hit = flagged(day)
        out.append(Deviation(
            subject="crew-01", key=obs.key, value=obs.value, effective=obs.effective,
            z_score=3.0 if hit else 0.2,
            severity=Severity.MODERATE if hit else Severity.NONE,
            direction="high", baseline=None, used_population_range=False,
        ))
    return out


def _now(days: float = 21.0) -> dt.datetime:
    return START + dt.timedelta(days=days)


def _trend(
    series: list[VitalObservation], deviations: list[Deviation] | None, now: dt.datetime
) -> Trend:
    settle = closing(deviations, CURRENT_WINDOW) if deviations is not None else None
    return trends_by_indicator(series, now=now, settle=settle)[KEY]


def _episode(day: float) -> float:
    """Cuatro dias y medio peor y vuelta, como el PVT de `transient-sleep-loss`."""
    return 370.0 if 13.0 <= day < 17.5 else 250.0


def _in_episode(day: float) -> bool:
    return 13.0 <= day < 17.5


def test_a_finished_episode_is_described_in_the_past_and_does_not_concern() -> None:
    series = _series(_episode)
    without = _trend(series, None, _now())
    assert without.is_concerning, "sin la regla la recta tiene que preocupar, o no dice nada"
    assert projection(without) is not None

    trend = _trend(series, _deviations(series, _in_episode), _now())

    assert trend.closed_episode
    assert not trend.is_concerning
    assert projection(trend) is None
    text = trend.describe()
    assert "episodio cerrado" in text and "por encima" in text and "subiendo" not in text
    # Lo demas de la tendencia no cambia: solo como se lee.
    assert trend.slope_per_day == without.slope_per_day


def test_an_episode_still_in_the_current_window_is_not_closed() -> None:
    def still(day: float) -> float:
        return 370.0 if day >= 13.0 else 250.0

    series = _series(still)
    trend = _trend(series, _deviations(series, lambda day: day >= 13.0), _now())
    assert trend.is_concerning and not trend.closed_episode


def test_while_the_state_still_flags_it_it_is_not_closed() -> None:
    """Casi en su nivel (5 ms por encima) pero el estado lo sigue viendo fuera de su rango."""
    def near(day: float) -> float:
        return 370.0 if 13.0 <= day < 17.5 else (255.0 if day >= 17.5 else 250.0)

    series = _series(near)
    trend = _trend(series, _deviations(series, lambda day: day >= 13.0), _now())
    assert trend.is_concerning and not trend.closed_episode


def test_an_excursion_the_deviation_path_never_flagged_is_not_closed() -> None:
    """La regla solo cede ante lo que el estado vio salir y volver: sin hallazgo no hay episodio."""
    series = _series(_episode)
    trend = _trend(series, _deviations(series, lambda day: False), _now())
    assert trend.is_concerning and not trend.closed_episode


def test_a_slow_drift_that_never_left_its_personal_range_is_not_touched() -> None:
    series = _series(lambda day: 250.0 + 2.0 * day)  # 14 ms/semana, el umbral es 5,6
    trend = _trend(series, _deviations(series, lambda day: False), _now())
    assert trend.is_concerning and not trend.closed_episode


def test_back_in_range_against_a_base_that_followed_is_not_back_to_its_level() -> None:
    """La base es movil: la desviacion puede no ver nada con el nivel todavia desplazado."""
    def stepped(day: float) -> float:
        if 13.0 <= day < 17.5:
            return 370.0
        return 280.0 if day >= 17.5 else 250.0  # 30 ms por encima: mas que el umbral (22,5)

    series = _series(stepped)
    trend = _trend(series, _deviations(series, _in_episode), _now())
    assert trend.is_concerning and not trend.closed_episode


def test_a_live_drift_the_moving_base_flagged_once_is_not_closed() -> None:
    """2x el ritmo de relevancia: la base movil lo marca un par de dias y luego lo alcanza.

    Desde antes del «episodio» el nivel ha subido unos 22 ms: menos que el umbral entero (22,5),
    que es lo que importa en cuatro semanas, pero el doble de lo que una deriva al ritmo de
    relevancia habria movido en esos 13,5 dias.
    """
    series = _series(lambda day: 250.0 + 1.6 * day)
    trend = _trend(series, _deviations(series, lambda day: 13.0 <= day < 15.0), _now())
    assert trend.is_concerning and not trend.closed_episode


def test_no_readings_in_the_current_window_is_not_a_recovery() -> None:
    series = _series(_episode, until=18.9)
    trend = _trend(series, _deviations(series, _in_episode), _now())
    assert trend.is_concerning and not trend.closed_episode


def test_without_a_level_before_the_episode_it_is_not_closed() -> None:
    def ramp(day: float) -> float:
        return 250.0 + 5.0 * day if day < 19.0 else 250.0

    series = _series(ramp)
    trend = _trend(series, _deviations(series, lambda day: day < 19.0), _now())
    assert trend.is_concerning and not trend.closed_episode


def test_the_level_before_is_the_one_before_this_episode_not_an_older_one() -> None:
    """Con una excursion antigua y otra reciente que ceso, el «antes» es el de la reciente.

    Tras el episodio queda 16 ms por encima: mas de lo que una deriva al ritmo de relevancia
    habria movido desde antes de ESTE episodio (unos 11 ms), menos que desde antes de la
    excursion antigua (unos 16 ms en mas tiempo). Medido desde la antigua, se cerraria.
    """
    def flagged(day: float) -> bool:
        return 2.0 <= day < 3.0 or 13.0 <= day < 17.5

    def level(day: float) -> float:
        if flagged(day):
            return 370.0
        return 266.0 if day >= 17.5 else 250.0

    series = _series(level)
    trend = _trend(series, _deviations(series, flagged), _now())
    assert trend.is_concerning and not trend.closed_episode


def test_settle_runs_on_each_context_before_choosing_one() -> None:
    """Aplicado tras elegir, cerrar la recta elegida taparia una deriva viva en otro contexto."""
    steady = _series(lambda day: 250.0 + 2.0 * day, context=Context.REST)
    noisy = _series(lambda day: 250.0 + 2.0 * day, context=Context.ACTIVE, noise=25.0, wave=True)
    alone = [trends_by_indicator(part, now=_now())[KEY] for part in (steady, noisy)]
    assert all(item.is_concerning for item in alone)
    assert alone[0].threshold_contrast > alone[1].threshold_contrast  # sin mas, gana el reposo

    def close_rest(trend: Trend, series: Sequence[VitalObservation], now: dt.datetime) -> Trend:
        if series[0].context.family is Context.REST:
            return replace(trend, closed_episode=True)
        return trend

    chosen = trends_by_indicator(steady + noisy, now=_now(), settle=close_rest)[KEY]
    assert chosen.is_concerning and not chosen.closed_episode
    assert chosen.threshold_contrast == alone[1].threshold_contrast


def test_the_transient_scenario_is_measured_not_adopted(tmp_path: Path) -> None:
    """De punta a punta con el escenario que cesa (§5.37.3). La regla esta medida y SIN ADOPTAR:
    el estado sigue en vigilancia con las tendencias de siempre, y la sombra dice que cerraria.

    Medido (§5.38.6): cierra tres de los cuatro indicadores del episodio. Los lapsos del PVT no,
    porque su estrato de esfuerzo tiene cuatro lecturas en el «ahora» y su mediana no ha vuelto
    (condicion 3); un estrato abierto basta, y el dominio conductual seguiria en vigilancia."""
    reset_store(new_store())
    settings = Settings(cache_dir=tmp_path, offline=True)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        client = TestClient(app)
        assert client.post(
            "/api/simulate", params={"scenario": "transient-sleep-loss", "days": 40}
        ).is_success
        status = client.get("/api/status").json()
        assessed = routes._assess(settings, get_store(), "crew-01", None, None, None)
    finally:
        app.dependency_overrides.clear()
        reset_store(None)

    # Lo que decide no la usa: ni el estado, ni la historia, ni la trayectoria.
    assert not any(trend.closed_episode for trend in assessed.trends.values())
    after = assessed.trends_before(assessed.latest + dt.timedelta(seconds=1))
    assert not any(trend.closed_episode for trend in after.values())
    assert status["overall_level"] == "watch"
    assert status["domains"]["behavioral"]["level"] == "watch"

    shadow = status["closed_episode_shadow"]
    assert shadow["adopted"] is False
    closed = {item["key"] for item in shadow["closed"]}
    assert closed == {"pvt-mean-rt", "sleep-duration", "sleep-efficiency"}
    assert all("episodio cerrado" in item["text"] for item in shadow["closed"])
    assert shadow["overall_level"] == "watch"
    assert shadow["domains_changed"] == []


def test_without_a_closed_episode_the_shadow_changes_nothing(tmp_path: Path) -> None:
    """Una deriva que sigue (insomnio progresivo) no se cierra: la sombra coincide con el estado."""
    reset_store(new_store())
    settings = Settings(cache_dir=tmp_path, offline=True)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        client = TestClient(app)
        assert client.post(
            "/api/simulate", params={"scenario": "progressive-insomnia", "days": 40}
        ).is_success
        status = client.get("/api/status").json()
    finally:
        app.dependency_overrides.clear()
        reset_store(None)

    shadow = status["closed_episode_shadow"]
    assert shadow["closed"] == [] and shadow["domains_changed"] == []
    assert shadow["overall_level"] == status["overall_level"]


def test_the_validation_measures_without_adopting_by_default() -> None:
    """La validacion externa aplica la regla solo si se le pide, y con el «ahora» del estado."""
    assert STATE_WINDOW == CURRENT_WINDOW
    for function in (
        report.evaluate_subject, report.run, report.measure_sensitivity,
        report.measure_all_sensitivity,
    ):
        assert inspect.signature(function).parameters["closed_episodes"].default is False


def test_the_shadow_says_which_levels_would_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La sombra recalcula el nivel con las tendencias cerradas, sin que el estado se entere.

    Se prueba la fontaneria, no la regla (esa, arriba): con un `closing` que cierra todo lo que
    preocupa, el dominio conductual de `transient-sleep-loss` bajaria de vigilancia a nominal.
    """
    def close_all(
        deviations: object, window: dt.timedelta, now: dt.datetime | None = None
    ) -> Settle:
        def settle(trend: Trend, series: Sequence[VitalObservation], at: dt.datetime) -> Trend:
            return replace(trend, closed_episode=True) if trend.is_concerning else trend
        return settle

    monkeypatch.setattr(routes, "closing", close_all)
    reset_store(new_store())
    settings = Settings(cache_dir=tmp_path, offline=True)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        client = TestClient(app)
        assert client.post(
            "/api/simulate", params={"scenario": "transient-sleep-loss", "days": 40}
        ).is_success
        status = client.get("/api/status").json()
    finally:
        app.dependency_overrides.clear()
        reset_store(None)

    assert status["overall_level"] == "watch"
    assert status["domains"]["behavioral"]["level"] == "watch"
    shadow = status["closed_episode_shadow"]
    assert shadow["adopted"] is False
    assert shadow["overall_level"] == "nominal"
    assert shadow["domains_changed"] == [
        {"domain": "behavioral", "adopted": "watch", "with_rule": "nominal"}
    ]
