"""La confianza de cada lectura tiene que verse, y enseñarla no puede cambiar nada.

La especificación del equipo (§2, §10) pide mostrar la confianza o calidad del dato. El
análisis ya la usaba —una lectura por debajo del umbral no entra en la referencia de la
línea base ni sostiene más que un hallazgo leve— pero `/api/status` no la contaba. Aquí
se comprueba que el bloque `data.quality`:

- dice cuándo una lectura es de baja confianza, con el umbral y la regla del motor;
- no le pone número a una fuente que no declaró nada, ni da por buena su calidad;
- cuenta lo que el motor hizo de verdad (lo que apartó, lo que limitó, y que la tendencia
  no mira la confianza);
- y solo lee: el estado sale igual con el bloque y sin él (invariante 5).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import data_quality
from app.analysis.baseline import MIN_SAMPLES, BaselineEngine, Severity, SeverityBasis
from app.analysis.trend import trends_by_indicator
from app.api import routes
from app.ingest.fhir import LOW_CONFIDENCE_THRESHOLD, VitalObservation, observation
from app.ingest.wearable import NO_CONTACT_CONFIDENCE

START = dt.datetime(2026, 3, 1, tzinfo=dt.UTC)
HOUR = dt.timedelta(hours=1)
RECENT = dt.timedelta(days=2)


def _post(client: TestClient, **body: Any) -> None:
    response = client.post("/api/observations", json={"subject": "crew-01", **body})
    assert response.status_code == 201, response.text


def _quality(client: TestClient, **params: str) -> dict[str, Any]:
    response = client.get("/api/status", params=params)
    assert response.status_code == 200, response.text
    quality: dict[str, Any] = response.json()["data"]["quality"]
    return quality


def _indicator(quality: dict[str, Any], key: str) -> dict[str, Any]:
    found: dict[str, Any] = next(item for item in quality["indicators"] if item["key"] == key)
    return found


def _pulse(
    value: float, when: dt.datetime, confidence: float = 1.0, source: str = "wearable-ble"
) -> VitalObservation:
    return observation("heart-rate", value, when, "crew-01", source, confidence=confidence)


def _describe(observations: list[VitalObservation]) -> dict[str, Any]:
    latest = max(obs.effective for obs in observations)
    deviations = BaselineEngine().evaluate_rolling(observations)
    return data_quality.describe(observations, deviations, latest, RECENT)


# --------------------------------------------------------------------------- #
# Lo que sale por la API
# --------------------------------------------------------------------------- #


def test_a_low_confidence_reading_shows_up_with_the_engine_threshold(
    client: TestClient,
) -> None:
    for hour in range(3):
        _post(
            client, key="heart-rate", value=64, source="manual",
            effective=(START + hour * HOUR).isoformat(),
        )
    _post(
        client, key="heart-rate", value=58, source="wearable-ble", confidence=0.3,
        effective=(START + 3 * HOUR).isoformat(),
    )

    quality = _quality(client)
    # El umbral es el del motor, no uno propio de este bloque.
    assert quality["low_confidence_threshold"] == LOW_CONFIDENCE_THRESHOLD
    assert quality["labels"]["low"] == "baja confianza"
    assert quality["recent"] == {"readings": 4, "low_confidence": 1, "undeclared": 3}
    assert quality["summary"].startswith("1 de 4 lecturas de los últimos 2 días")
    assert "no cuenta como referencia de la línea base" in quality["summary"]

    pulse = _indicator(quality, "heart-rate")
    assert quality["indicators"][0] is pulse, "lo dudoso va primero"
    assert pulse["latest"]["state"] == "low"
    assert pulse["latest"]["label"] == "baja confianza"
    assert pulse["latest"]["confidence"] == 0.3
    assert pulse["latest"]["source"] == "wearable-ble"
    assert pulse["latest"]["source_label"] == "wearable BLE"
    assert pulse["latest"]["observation_type"] == "measured"
    assert pulse["recent"]["readings"] == 4
    assert pulse["recent"]["low_confidence"] == 1
    # De qué fuente salen las dudosas: es lo que dice qué sensor mirar.
    assert pulse["recent"]["sources"] == [
        {"source": "manual", "label": "alta manual", "readings": 3, "low_confidence": 0},
        {"source": "wearable-ble", "label": "wearable BLE", "readings": 1, "low_confidence": 1},
    ]
    assert pulse["baseline"]["discounted"] is True
    assert pulse["baseline"]["excluded_readings"] == 1


def test_a_source_that_declares_nothing_gets_no_number(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "nominal", "days": 5})

    quality = _quality(client)
    assert quality["indicators"], "el simulador tiene que dejar indicadores"
    for item in quality["indicators"]:
        assert item["latest"]["state"] == "undeclared"
        assert item["latest"]["label"] == "no declarada"
        # El 1,0 por defecto no es un dato de la fuente: no se presenta como cifra.
        assert item["latest"]["confidence"] is None
        assert item["latest"]["source_label"] == "simulador (nominal)"
        assert item["latest"]["evidence_context"] == "simulated"
        assert item["recent"]["low_confidence"] == 0
        assert item["recent"]["undeclared"] == item["recent"]["readings"]
        assert item["baseline"]["discounted"] is False

    # Y que nadie las marcara no se cuenta como "son buenas": se dice que no se sabe.
    recent = quality["recent"]
    assert recent["low_confidence"] == 0
    assert recent["undeclared"] == recent["readings"] > 0
    assert "ninguna con baja confianza" in quality["summary"]
    assert "no declaran confianza" in quality["undeclared_note"]
    assert data_quality.TREND_NOTE not in quality["summary"]


def test_a_declared_confidence_above_the_threshold_keeps_its_number(
    client: TestClient,
) -> None:
    _post(client, key="heart-rate", value=64, confidence=0.8, effective=START.isoformat())

    quality = _quality(client)
    pulse = _indicator(quality, "heart-rate")
    assert pulse["latest"]["state"] == "declared"
    assert pulse["latest"]["label"] == "confianza declarada"
    assert pulse["latest"]["confidence"] == 0.8
    assert pulse["recent"]["low_confidence"] == 0
    # Declarada no es dudosa: la línea base no aparta nada.
    assert pulse["baseline"]["discounted"] is False
    # Todas las recientes declaran su confianza: no hay nada que advertir.
    assert quality["undeclared_note"] is None


def test_earth_only_sees_the_quality_of_what_has_arrived(client: TestClient) -> None:
    """Con `until`, el bloque se calcula con las lecturas llegadas, como el resto del estado."""
    _post(client, key="heart-rate", value=64, effective=START.isoformat())
    _post(
        client, key="heart-rate", value=58, confidence=0.3,
        effective=(START + 2 * HOUR).isoformat(),
    )

    assert _quality(client)["recent"]["low_confidence"] == 1
    on_earth = _quality(client, until=(START + HOUR).isoformat())
    assert on_earth["recent"] == {"readings": 1, "low_confidence": 0, "undeclared": 1}


# --------------------------------------------------------------------------- #
# Lo que cuenta es lo que el motor hizo
# --------------------------------------------------------------------------- #


def test_the_state_is_the_rule_the_baseline_uses() -> None:
    """Justo en el umbral no es baja confianza: la frontera es la de `is_low_confidence`."""
    at = _pulse(62.0, START, LOW_CONFIDENCE_THRESHOLD)
    below = _pulse(62.0, START, LOW_CONFIDENCE_THRESHOLD - 0.01)

    assert at.is_low_confidence is False
    assert data_quality.state_of(at) is data_quality.QualityState.DECLARED
    assert below.is_low_confidence is True
    assert data_quality.state_of(below) is data_quality.QualityState.LOW


def test_what_it_counts_as_set_aside_is_what_the_baseline_left_out() -> None:
    good = [_pulse(60.0 + index % 5, START + index * HOUR) for index in range(MIN_SAMPLES + 20)]
    # Sin contacto, con cifras que no se confunden con ninguna de las buenas. La de 30
    # cruza el límite de peligro: un hallazgo limitado a leve, pero de hace días.
    doubtful = [
        _pulse(value, START + (40 + index) * HOUR + HOUR / 2, NO_CONTACT_CONFIDENCE)
        for index, value in enumerate([97.0, 97.0, 97.0, 97.0, 30.0])
    ]
    # La última, también sin contacto y por debajo del límite de peligro.
    last = _pulse(30.0, good[-1].effective + dt.timedelta(days=1), NO_CONTACT_CONFIDENCE)
    observations = [*good, *doubtful, last]
    deviations = BaselineEngine().evaluate_rolling(observations)
    judged = next(dev for dev in deviations if dev.effective == last.effective)

    quality = data_quality.describe(observations, deviations, last.effective, RECENT)
    pulse = _indicator(quality, "heart-rate")

    # El motor usó de referencia todas las buenas y ninguna de las dudosas...
    assert judged.baseline is not None and judged.baseline.established
    assert judged.baseline.samples == len(good)
    assert not {97.0, 30.0} & set(judged.baseline.sorted_values)
    # ...y el bloque cuenta justo las que quedaron fuera.
    assert pulse["baseline"]["excluded_readings"] == len(doubtful) + 1
    assert pulse["baseline"]["discounted"] is True
    assert "fuera de la referencia de la línea base" in pulse["baseline"]["text"]
    # El hallazgo limitado que cuenta es el que limitó el motor.
    assert judged.basis is SeverityBasis.LOW_CONFIDENCE
    assert judged.severity is Severity.MILD
    old = next(dev for dev in deviations if dev.effective == doubtful[-1].effective)
    assert old.basis is SeverityBasis.LOW_CONFIDENCE, "el de hace días también se limitó"
    assert pulse["baseline"]["capped_findings"] == 1, "solo cuenta el reciente"
    assert "1 hallazgo reciente limitado a leve" in pulse["baseline"]["text"]
    # Las dudosas de hace días no son "recientes"; la de ahora sí.
    assert pulse["recent"]["low_confidence"] == 1


def test_the_trend_note_says_what_the_trend_does() -> None:
    """La tendencia no descuenta la baja confianza. El día que lo haga, la frase sobra."""
    step = 6 * HOUR
    good = [_pulse(60.0 + index % 3, START + index * step) for index in range(40)]
    doubtful = [
        _pulse(120.0, good[-1].effective + (index + 1) * step, NO_CONTACT_CONFIDENCE)
        for index in range(6)
    ]

    flat = trends_by_indicator(good)["heart-rate"]
    drifting = trends_by_indicator([*good, *doubtful])["heart-rate"]

    assert drifting.points == len(good) + len(doubtful)
    assert drifting.slope_per_week > flat.slope_per_week + 10
    assert data_quality.TREND_NOTE in _describe([*good, *doubtful])["summary"]


def test_singular_and_plural_read_right() -> None:
    one = _describe([_pulse(62.0, START), _pulse(58.0, START + HOUR, 0.3)])
    assert one["summary"].startswith("1 de 2 lecturas de los últimos 2 días")
    assert "(1 indicador): no cuenta como referencia" in one["summary"]
    assert "no sostiene por sí sola más que un hallazgo leve" in one["summary"]
    assert one["undeclared_note"].startswith("1 de 2 lecturas recientes no declara confianza")

    two = _describe([_pulse(58.0, START, 0.3), _pulse(58.0, START + HOUR, 0.3)])
    assert "no cuentan como referencia" in two["summary"]
    assert "no sostienen por sí solas más que un hallazgo leve" in two["summary"]
    assert two["undeclared_note"] is None

    alone = _describe([_pulse(62.0, START)])
    assert alone["summary"] == (
        "1 lectura en los últimos 2 días: ninguna con baja confianza de medida."
    )


def test_the_window_is_named_as_it_is() -> None:
    observations = [_pulse(62.0, START)]
    hours = data_quality.describe(observations, [], START, dt.timedelta(hours=36))
    days = data_quality.describe(observations, [], START, dt.timedelta(days=3))

    assert hours["recent_label"] == "últimas 36 h"
    assert "en las últimas 36 h" in hours["summary"]
    assert days["recent_label"] == "últimos 3 días"
    assert "en los últimos 3 días" in days["summary"]


def test_an_unknown_source_keeps_the_name_it_signed_with() -> None:
    assert data_quality.source_label("simulator:nominal") == "simulador (nominal)"
    assert data_quality.source_label("apple-health") == "Apple Health"
    assert data_quality.source_label("analitica:12") == "analítica del informe 12"
    # Lo que no se conoce no se rebautiza.
    assert data_quality.source_label("holter-xyz") == "holter-xyz"
    assert data_quality.source_label("simulator:") == "simulator:"


# --------------------------------------------------------------------------- #
# Invariante 5: enseñarlo no cambia el análisis
# --------------------------------------------------------------------------- #


def test_showing_quality_does_not_move_any_level(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El bloque lee el análisis; con él o sin él, el estado entero es el mismo."""
    client.post("/api/simulate", params={"scenario": "arrhythmia", "days": 40})
    reference = dt.datetime.fromisoformat(
        client.get("/api/status").json()["data"]["reference_time"]
    )
    # Una racha sin contacto encima de un escenario con hallazgos reales.
    for minutes in (30, 20, 10):
        _post(
            client, key="heart-rate", value=31, source="wearable-ble",
            confidence=NO_CONTACT_CONFIDENCE,
            effective=(reference - dt.timedelta(minutes=minutes)).isoformat(),
        )

    with_block = client.get("/api/status").json()
    assert with_block["data"]["quality"]["recent"]["low_confidence"] == 3

    monkeypatch.setattr(routes, "describe_quality", lambda *args: None)
    without_block = client.get("/api/status").json()
    assert without_block["data"]["quality"] is None

    for payload in (with_block, without_block):
        del payload["data"]["quality"]
    assert with_block == without_block
    assert any(risk["level"] != "nominal" for risk in with_block["domains"].values())


def test_describing_does_not_touch_its_inputs() -> None:
    observations = [
        _pulse(62.0, START), _pulse(58.0, START + HOUR, 0.3), _pulse(60.0, START + 2 * HOUR, 0.8)
    ]
    deviations = BaselineEngine().evaluate_rolling(observations)
    before = (list(observations), list(deviations))

    data_quality.describe(observations, deviations, observations[-1].effective, RECENT)

    assert (observations, deviations) == before
