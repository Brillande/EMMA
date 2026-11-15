"""Segunda ronda del contexto del equipo: radiación en tres escalas, perfil, eventos de misión,
revisión humana de hipótesis, contramedidas de hábitat y versión de reglas.

Especificación §3, §7, §8, §12; base de conocimiento §7.
"""

import datetime as dt
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.advisor import countermeasures
from app.advisor.countermeasures import LibraryError, load
from app.analysis import risk
from app.analysis.radiation import mission_dose, scales, time_to_action
from app.api.routes import get_store
from app.core.versioning import fingerprint, rules
from app.ingest.fhir import observation

START = dt.date(2026, 11, 1)
T0 = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)


def _rates(hours: int, value: float) -> list:
    return [
        observation("absorbed-dose-rate", value, T0 + dt.timedelta(hours=h), "crew-01", "d")
        for h in range(hours + 1)
    ]


def test_mission_dose_integrates_the_rate_with_the_flight_quality_factor() -> None:
    dose = mission_dose(_rates(24, 10.0), START)
    assert dose is not None
    # 10 µGy/h × 24 h = 240 µGy = 0,24 mGy; × Q medio 2,38 = 0,571 mSv.
    assert dose["absorbed_mgy"] == pytest.approx(0.24)
    assert dose["value_msv"] == pytest.approx(0.24 * 2.38, abs=1e-3)
    assert dose["observation_type"] == "inferred" and dose["model_version"]


def test_one_reading_is_not_a_mission_dose() -> None:
    assert mission_dose(_rates(0, 10.0), START) is None


def test_career_needs_a_declared_prior_dose_and_never_assumes_zero() -> None:
    mission = mission_dose(_rates(24, 10.0), START)
    unknown = scales(active_event=None, event_time=None, now=T0, mission=mission,
                     prior_career_msv=None, limit_msv=600.0)
    assert unknown["career"]["value_msv"] is None
    assert "no se supone cero" in unknown["career"]["basis"]
    known = scales(active_event=None, event_time=None, now=T0, mission=mission,
                   prior_career_msv=100.0, limit_msv=600.0)
    assert known["career"]["value_msv"] == pytest.approx(100 + mission["value_msv"])
    assert known["career"]["limit_source"] == "NASA-STD-3001 [V1 4030]"


def test_time_to_action_follows_the_orion_procedure() -> None:
    plan = time_to_action(T0, T0 + dt.timedelta(minutes=20))
    assert plan is not None
    assert plan["shelter_ready_by"] == (T0 + dt.timedelta(hours=1)).isoformat()
    assert plan["max_stay_until"] == (T0 + dt.timedelta(hours=24)).isoformat()
    assert plan["elapsed_minutes"] == 20
    assert time_to_action(None, T0) is None


def test_the_rules_version_changes_when_a_threshold_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = fingerprint(rules())
    changed = ((71.0, risk.RiskLevel.CRITICAL), *risk._LEVEL_THRESHOLDS[1:])
    monkeypatch.setattr(risk, "_LEVEL_THRESHOLDS", changed)
    assert fingerprint(rules()) != before


def test_habitat_countermeasures_follow_the_cabin_and_carry_no_clinical_domain() -> None:
    habitat = countermeasures.for_habitat("cabin-ppco2")
    assert habitat
    for item in habitat:
        assert item.scope == "habitat" and item.domain is None
        assert item.protocol_ref is not None


def _library(tmp_path: Path, **override: object) -> Path:
    entry = {
        "id": "h", "scope": "habitat", "domain": None, "action": "Contrastar el sensor.",
        "indication": "i", "crew_time_minutes": None,
        "resources": [
            {"key": "second-sensor-or-manual-instrument", "description": "segundo sensor"},
        ],
        "crew_time_basis": "sin fuente", "protocol_ref": None,
        "followup_checks": ["cabin-ppco2"], "followup_window_hours": 1,
        "followup_basis": "diseño EMMA", "basis": "demo",
        "family": "check-surveillance",
    }
    entry.update(override)
    path = tmp_path / "l.json"
    path.write_text(json.dumps({"countermeasures": [entry]}), encoding="utf-8")
    return path


def test_a_habitat_countermeasure_cannot_claim_a_domain_or_a_clinical_check(
    tmp_path: Path,
) -> None:
    assert load(_library(tmp_path))
    with pytest.raises(LibraryError, match="dominio"):
        load(_library(tmp_path, domain="immune"))
    with pytest.raises(LibraryError, match="catálogo"):
        load(_library(tmp_path, followup_checks=["heart-rate"]))


def test_the_profile_feeds_the_career_scale(client: TestClient) -> None:
    client.post("/api/simulate", params={"days": 10})
    assert client.post("/api/crew/profile", json={
        "prior_missions": 1, "prior_career_dose_msv": 120.0, "declared_by": "CDR",
    }).status_code == 201
    radiation = client.get("/api/status").json()["radiation"]
    assert radiation["mission"]["observation_type"] == "inferred"
    assert radiation["career"]["prior_msv"] == 120.0
    assert radiation["career"]["value_msv"] > 120.0


def test_mission_events_appear_in_the_mission_context(client: TestClient) -> None:
    client.post("/api/simulate", params={"days": 10})
    start = T0 + dt.timedelta(days=5)
    assert client.post("/api/mission/events", json={
        "kind": "eva", "start": start.isoformat(),
        "end": (start + dt.timedelta(hours=6)).isoformat(), "label": "EVA 1",
        "declared_by": "CDR",
    }).status_code == 201
    [event] = client.get("/api/status").json()["mission"]["events"]
    assert (event["kind"], event["label"]) == ("eva", "EVA 1")
    assert client.post("/api/mission/events", json={
        "kind": "picnic", "start": start.isoformat(), "end": start.isoformat(),
        "label": "x", "declared_by": "CDR",
    }).status_code == 422


def test_a_crew_can_confirm_the_shared_hypothesis_and_follow_recovery(
    client: TestClient,
) -> None:
    client.post("/api/simulate", params={"scenario": "co2-fatigue", "days": 40})
    first = client.get("/api/crew").json()["correlation"]["hypotheses"][0]
    assert first["countermeasures"], "las comprobaciones ambientales van como contramedidas"
    body = {
        "decision": "confirmed", "parameter": first["excursion"]["parameter"],
        "excursion_start": first["excursion"]["start"], "reason": "segundo sensor coincide",
        "decided_by": "CDR",
    }
    assert client.post("/api/crew/hypotheses/review", json=body).status_code == 201
    reviewed = client.get("/api/crew").json()["correlation"]["hypotheses"][0]["review"]
    assert reviewed["decision"] == "confirmed"
    assert reviewed["recovery"]["habitat_within_limit"] is False
    assert get_store().verify_integrity().ok

    wrong = {**body, "excursion_start": "2026-11-02T00:00:00+00:00"}
    assert client.post("/api/crew/hypotheses/review", json=wrong).status_code == 409


def test_every_status_and_alert_declares_its_rules_version(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "progressive-insomnia", "days": 40})
    status = client.get("/api/status").json()
    assert status["rules_version"].startswith("reglas@")
    assert all(item["rules_version"] == status["rules_version"] for item in status["alerts"])
