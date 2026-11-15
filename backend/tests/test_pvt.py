"""Puntuacion del PVT: la medida objetiva de fatiga.

Importa porque convierte "me encuentro bien" —que un astronauta motivado afirma
sistematicamente— en un numero que se puede contrastar con su propia linea base.
"""

import datetime as dt

import pytest

from app.ingest.pvt import (
    FALSE_START_THRESHOLD_MS,
    LAPSE_THRESHOLD_MS,
    MIN_TRIALS,
    InsufficientTrials,
    score,
    to_observations,
)

NOW = dt.datetime(2026, 11, 14, 8, 0, tzinfo=dt.UTC)


def test_scores_a_clean_session() -> None:
    result = score([250.0] * 20)

    assert result.trials == 20
    assert result.valid_trials == 20
    assert result.mean_rt_ms == 250.0
    assert result.lapses == 0
    assert result.false_starts == 0
    assert result.response_speed == pytest.approx(4.0)  # 1000/250


def test_counts_lapses_at_the_standard_threshold() -> None:
    just_under = LAPSE_THRESHOLD_MS - 1
    just_over = LAPSE_THRESHOLD_MS + 1
    result = score([250.0] * 18 + [just_under, just_over])

    assert result.lapses == 1
    assert result.lapse_rate == pytest.approx(0.05)


def test_false_starts_are_counted_but_excluded_from_timing() -> None:
    """Promediar las anticipaciones premiaria a quien no atiende."""
    clean = score([300.0] * 20)
    with_anticipation = score([300.0] * 20 + [50.0, 20.0])

    assert with_anticipation.false_starts == 2
    assert with_anticipation.valid_trials == 20
    # La media no mejora por haber anticipado.
    assert with_anticipation.mean_rt_ms == clean.mean_rt_ms


def test_false_start_threshold_is_physiological() -> None:
    result = score([FALSE_START_THRESHOLD_MS - 1] + [300.0] * 19)
    assert result.false_starts == 1
    result = score([FALSE_START_THRESHOLD_MS] + [300.0] * 19)
    assert result.false_starts == 0


def test_too_few_trials_is_refused_not_scored() -> None:
    with pytest.raises(InsufficientTrials, match="interpretable"):
        score([250.0] * (MIN_TRIALS - 1))


def test_all_false_starts_is_refused() -> None:
    with pytest.raises(InsufficientTrials, match="no mide vigilancia"):
        score([30.0] * 20)


def test_lapses_are_the_vigilance_measure_not_the_mean() -> None:
    """Dos sesiones de media identica pueden diferir en lo que de verdad importa."""
    erratic = score([220.0] * 16 + [600.0, 620.0, 640.0, 660.0])
    steady = score([erratic.mean_rt_ms] * 20)

    # Media exactamente igual por construccion...
    assert steady.mean_rt_ms == erratic.mean_rt_ms
    # ...y sin embargo una tiene cuatro fallos de vigilancia y la otra ninguno.
    assert steady.lapses == 0
    assert erratic.lapses == 4


def test_response_speed_sits_between_the_mean_and_the_median() -> None:
    """Por Jensen, la media de 1/RT es siempre >= 1/(RT medio). No es un fallo:
    es lo que la hace menos sesgada por la cola lenta, sin llegar a ignorarla."""
    erratic = score([220.0] * 16 + [600.0, 620.0, 640.0, 660.0])

    assert erratic.response_speed >= 1000.0 / erratic.mean_rt_ms
    assert erratic.response_speed <= 1000.0 / erratic.median_rt_ms


def test_slowest_decile_is_the_decile_not_the_single_worst() -> None:
    """Con 20 estimulos, el decil mas lento son dos respuestas, no una."""
    result = score([200.0] * 18 + [880.0, 920.0])
    assert result.slowest_10pct_mean_ms == 900.0

    # Con 10 estimulos el decil es una sola respuesta.
    assert score([200.0] * 9 + [900.0]).slowest_10pct_mean_ms == 900.0


def test_median_resists_outliers() -> None:
    result = score([250.0] * 19 + [2000.0])
    assert result.median_rt_ms == 250.0
    assert result.mean_rt_ms > 250.0


def test_converts_to_catalog_observations() -> None:
    result = score([250.0] * 18 + [600.0, 700.0])
    observations = to_observations(result, "crew-01", NOW)

    assert [item.key for item in observations] == ["pvt-mean-rt", "pvt-lapses"]
    assert observations[1].value == 2.0
    assert all(item.validates() for item in observations)


def test_result_serializes() -> None:
    payload = score([250.0] * 20).to_dict()
    assert payload["trials"] == 20
    assert "response_speed" in payload
    assert "lapse_rate" in payload
