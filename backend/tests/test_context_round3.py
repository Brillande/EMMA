"""Tercera ronda del contexto del equipo: «recuperándose», comprobación de proyecciones, tiempo
hasta la acción y nutrición completa.

Conversación de ideación ("CAUTION → RECOVERING → NOMINAL", "predicción → resultado →
validación", "Detection → Decision → Intervention") y base de conocimiento §5 (H7).
"""

import datetime as dt
import math

from fastapi.testclient import TestClient

from app.analysis.forecast_check import hindcast, matured
from app.analysis.recovery_state import trajectories
from app.analysis.risk import RiskLevel
from app.analysis.time_to_action import time_to_action_of
from app.api.routes import get_store
from app.ingest.codes import CATALOG, MISSION_SPECIFIC, CodeSystem, Domain
from app.ingest.fhir import observation

T0 = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)


# --------------------------------------------------------------------------- #
# Recuperándose
# --------------------------------------------------------------------------- #


def test_a_domain_that_came_back_is_recovering_and_a_stable_one_says_nothing() -> None:
    now = {Domain.BEHAVIORAL: RiskLevel.NOMINAL, Domain.BONE: RiskLevel.WATCH}
    before = {Domain.BEHAVIORAL: RiskLevel.CONCERN, Domain.BONE: RiskLevel.WATCH}
    found = trajectories(now, before, T0)
    assert found["behavioral"] is not None
    assert found["behavioral"]["direction"] == "recovering"
    assert found["behavioral"]["from_level"] == "concern"
    assert found["bone"] is None


def test_a_domain_that_got_worse_says_so() -> None:
    found = trajectories({Domain.BONE: RiskLevel.CONCERN}, {Domain.BONE: RiskLevel.WATCH}, T0)
    assert found["bone"] is not None and found["bone"]["direction"] == "worsening"


def test_the_status_carries_a_trajectory_per_domain(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "spe-event", "days": 40})
    domains = client.get("/api/status").json()["domains"]
    assert all("trajectory" in item for item in domains.values())


# --------------------------------------------------------------------------- #
# Comprobación de proyecciones
# --------------------------------------------------------------------------- #


def _drift(days: int, per_day: float) -> list:
    # Con ruido: una recta perfecta tiene margen cero y cualquier redondeo la saca de el.
    return [
        observation(
            "heart-rate", 60 + per_day * (h / 24) + 1.5 * math.sin(h * 1.7),
            T0 + dt.timedelta(hours=h), "c", "w",
        )
        for h in range(days * 24)
    ]


def test_a_steady_drift_is_projected_within_its_margin() -> None:
    data = _drift(60, 0.3)
    [check] = [item for item in hindcast(data, data[-1].effective) if item["key"] == "heart-rate"]
    assert check["kind"] == "hindcast"
    assert check["within_margin"], check


def test_a_drift_that_stops_is_caught_as_a_miss() -> None:
    rising = _drift(40, 0.3)
    flat_value = rising[-1].value
    flat = [
        observation("heart-rate", flat_value, rising[-1].effective + dt.timedelta(hours=h + 1),
                    "c", "w")
        for h in range(28 * 24)
    ]
    data = rising + flat
    [check] = [item for item in hindcast(data, data[-1].effective) if item["key"] == "heart-rate"]
    assert not check["within_margin"]
    assert check["error"] < 0


def test_a_signed_snapshot_is_checked_once_its_horizon_arrives() -> None:
    snapshot = {
        "key": "heart-rate", "made_at": T0.isoformat(),
        "horizon_at": (T0 + dt.timedelta(days=28)).isoformat(),
        "anchor_value": "60.0", "projected_change": "5.0",
        "projected_change_low": "4.0", "projected_change_high": "6.0", "ledger_index": 3,
    }
    readings = [
        observation("heart-rate", 65.2, T0 + dt.timedelta(days=28, hours=-h), "c", "w")
        for h in range(3)
    ]
    assert matured([snapshot], readings, T0 + dt.timedelta(days=10)) == []
    [check] = matured([snapshot], readings, T0 + dt.timedelta(days=29))
    assert check["kind"] == "snapshot" and check["within_margin"]


def test_the_status_signs_snapshots_once_a_day_and_ground_signs_none(
    client: TestClient,
) -> None:
    client.post("/api/simulate", params={"scenario": "cardiovascular-deconditioning", "days": 40})
    store = get_store()
    before = len(store.ledger)
    # Primero Tierra, con el almacén sin instantáneas: si firmara, se notaría aquí.
    client.get("/api/status", params={"until": "2026-12-10T23:00:00+00:00"})
    assert len(store.ledger) == before, "la vista de Tierra no firma proyecciones"
    status = client.get("/api/status").json()
    after_first = len(store.ledger)
    client.get("/api/status")
    assert after_first > before
    assert len(store.ledger) == after_first, "una instantánea por indicador y día"
    until = status["data"]["reference_time"]
    client.get("/api/status", params={"until": until})
    assert len(store.ledger) == after_first, "la vista de Tierra no firma proyecciones"
    assert status["forecast_checks"]["checked"] >= 1
    assert store.verify_integrity().ok


# --------------------------------------------------------------------------- #
# Tiempo hasta la acción
# --------------------------------------------------------------------------- #


def test_time_to_action_measures_decisions_in_data_time() -> None:
    onset = T0.isoformat()
    ack = [{"domain": "behavioral", "reference_time": (T0 + dt.timedelta(minutes=30)).isoformat()}]
    adopted = [{"domain": "behavioral", "reference_time": (T0 + dt.timedelta(hours=2)).isoformat()}]
    other = [{"domain": "bone", "reference_time": (T0 + dt.timedelta(minutes=5)).isoformat()}]
    result = time_to_action_of("behavioral", onset, ack + other, adopted)
    assert result is not None
    assert result["acknowledged_after_minutes"] == 30
    assert result["countermeasure_after_minutes"] == 120
    pending = time_to_action_of("behavioral", onset, [], [])
    assert pending is not None and pending["acknowledged_after_minutes"] is None
    assert time_to_action_of("behavioral", None, ack, adopted) is None


def test_an_action_before_the_onset_does_not_count() -> None:
    early = [{"domain": "behavioral", "reference_time": (T0 - dt.timedelta(hours=1)).isoformat()}]
    result = time_to_action_of("behavioral", T0.isoformat(), early, [])
    assert result is not None and result["acknowledged_after_minutes"] is None


# --------------------------------------------------------------------------- #
# Nutrición completa
# --------------------------------------------------------------------------- #


def test_appetite_and_rejected_food_are_own_codes_that_say_why() -> None:
    for key in ("appetite-rating", "food-rejected-fraction"):
        assert CATALOG[key].system is CodeSystem.EMMA
        assert key in MISSION_SPECIFIC
        assert CATALOG[key].critical_low is None and CATALOG[key].critical_high is None
