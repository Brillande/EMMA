"""Contramedidas como datos y su seguimiento (especificacion del equipo §7, §8, §14).

La especificacion pide una contramedida estructurada —fuente, recursos, tiempo de tripulacion,
seguimiento— con su estado de seguimiento y confirmacion humana. Estas pruebas fijan el contrato
de la biblioteca (una cifra sin fuente no entra) y el ciclo adoptar → ventana → evaluar → cerrar.
"""

import datetime as dt
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.advisor import countermeasures
from app.advisor.countermeasures import NO_SOURCE, LibraryError, load
from app.advisor.followup import CAUSALITY_NOTE, followups
from app.advisor.recommendations import Advisor
from app.analysis.risk import CrewHealthStatus, RiskLevel
from app.environment.donki import EventType, Severity, SolarEvent
from app.ingest.codes import Domain, Ridge
from app.ingest.fhir import observation

NOW = dt.datetime(2026, 12, 10, 12, 0, tzinfo=dt.UTC)


# --------------------------------------------------------------------------- #
# Biblioteca
# --------------------------------------------------------------------------- #


def test_every_countermeasure_declares_its_basis() -> None:
    library = countermeasures.library()
    assert library, "la biblioteca no puede estar vacía"
    for item in library.values():
        assert item.basis in countermeasures.BASES
        if item.basis == "evidence-backed":
            assert item.protocol_ref is not None and item.protocol_ref.url.startswith("https://")
        if item.crew_time_minutes is not None:
            assert item.crew_time_basis != NO_SOURCE
        assert item.followup_window_hours > 0


def test_every_clinical_domain_has_countermeasures_and_a_ridge_hazard() -> None:
    for domain in Domain:
        assert countermeasures.for_domain(domain), domain
        assert isinstance(domain.ridge, Ridge)


def test_the_shelter_is_not_offered_by_domain_level() -> None:
    assert countermeasures.SHELTER_ID not in {
        item.id for item in countermeasures.for_domain(Domain.RADIATION)
    }


def _write(tmp_path: Path, **override: object) -> Path:
    entry = {
        "id": "x", "domain": "cardiovascular", "action": "Repetir la medida.",
        "indication": "i", "crew_time_minutes": None,
        "resources": [{"key": "same-sensor", "description": "el mismo sensor"}],
        "crew_time_basis": NO_SOURCE, "protocol_ref": None, "followup_checks": ["heart-rate"],
        "followup_window_hours": 1, "followup_basis": "diseño EMMA",
        "contraindications_note": None, "adverse_effects_note": None, "basis": "demo",
        "family": "check-surveillance",
    }
    entry.update(override)
    path = tmp_path / "library.json"
    path.write_text(json.dumps({"countermeasures": [entry]}), encoding="utf-8")
    return path


def test_a_valid_entry_loads(tmp_path: Path) -> None:
    assert set(load(_write(tmp_path))) == {"x"}


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"basis": "maybe"}, "basis"),
        ({"basis": "evidence-backed"}, "protocolo"),
        ({"crew_time_minutes": 30}, "sin fuente"),
        ({"crew_time_basis": ""}, "crew_time_basis"),
        ({"followup_checks": ["no-such-indicator"]}, "catálogo"),
        ({"followup_window_hours": 0}, "ventana"),
        ({"followup_basis": ""}, "sin base"),
        ({"domain": "habitat"}, "dominio"),
    ],
)
def test_an_entry_without_its_basis_is_refused(
    tmp_path: Path, override: dict[str, object], reason: str
) -> None:
    with pytest.raises(LibraryError, match=reason):
        load(_write(tmp_path, **override))


# --------------------------------------------------------------------------- #
# Recomendaciones
# --------------------------------------------------------------------------- #


def _status(level: RiskLevel, solar: SolarEvent | None = None) -> CrewHealthStatus:
    from app.analysis.risk import DomainRisk

    return CrewHealthStatus(
        subject="crew-01",
        domains={Domain.BEHAVIORAL: DomainRisk(Domain.BEHAVIORAL, 50.0, level, ("sueño",))},
        comms=None, isolation_factor=1.0, cumulative_dose_msv=0.0, dose_limit_msv=600.0,
        active_solar_event=solar,
    )


def test_each_recommendation_carries_its_countermeasure_and_its_own_evidence_first() -> None:
    recommendations = Advisor().recommend(_status(RiskLevel.CONCERN))
    assert recommendations
    for item in recommendations:
        assert item.countermeasure is not None
        assert item.action == item.countermeasure.action
        if item.countermeasure.protocol_ref is not None:
            assert item.evidence[0] == item.countermeasure.protocol_ref


def test_a_solar_event_offers_the_sourced_shelter_first() -> None:
    event = SolarEvent(
        event_id="SEP-1", event_type=EventType.SEP, time=NOW, severity=Severity.HIGH,
        instruments=(), linked_event_ids=(), flare_class=None, link="https://example.invalid",
    )
    first = Advisor().recommend(_status(RiskLevel.NOMINAL, event))[0]
    assert first.countermeasure is not None
    assert first.countermeasure.id == countermeasures.SHELTER_ID
    assert first.countermeasure.crew_time_minutes == 60
    assert first.to_dict()["countermeasure"]["protocol_ref"]["source"] == (
        "NASA (22 de septiembre de 2016)"
    )


# --------------------------------------------------------------------------- #
# Seguimiento: logica pura
# --------------------------------------------------------------------------- #


def _adoption(index: int, countermeasure_id: str, level: str, when: dt.datetime) -> dict:
    item = countermeasures.get(countermeasure_id)
    return {
        "ledger_index": index, "action": "adopted", "countermeasure_id": countermeasure_id,
        "domain": str(item.domain), "level": level, "reference_time": when.isoformat(),
        "decided_by": "CDR", "reason": "", "adoption_index": "",
    }


def test_inside_the_window_there_is_no_verdict() -> None:
    adopted = _adoption(5, "bh-repeat-pvt", "concern", NOW)
    [item] = followups([adopted], {"behavioral": RiskLevel.WATCH}, [], NOW + dt.timedelta(hours=2))
    assert item["state"] == "in_window"
    assert item["evaluation"] is None


def test_after_the_window_it_says_what_changed_and_that_it_proves_no_cause() -> None:
    adopted = _adoption(5, "bh-repeat-pvt", "concern", NOW)
    repeat = observation("pvt-mean-rt", 280.0, NOW + dt.timedelta(hours=20), "crew-01", "pvt")
    [item] = followups(
        [adopted], {"behavioral": RiskLevel.WATCH}, [repeat], NOW + dt.timedelta(hours=30)
    )
    assert item["state"] == "due"
    assert item["evaluation"]["outcome"] == "improved"
    assert CAUSALITY_NOTE in item["evaluation"]["text"]


def test_without_repeating_the_check_there_is_nothing_to_evaluate() -> None:
    adopted = _adoption(5, "bh-repeat-pvt", "concern", NOW)
    before = observation("pvt-mean-rt", 280.0, NOW - dt.timedelta(hours=1), "crew-01", "pvt")
    [item] = followups(
        [adopted], {"behavioral": RiskLevel.NOMINAL}, [before], NOW + dt.timedelta(hours=30)
    )
    assert item["evaluation"]["outcome"] == "no_repeat"


def test_worse_and_unchanged_are_said_as_such() -> None:
    adopted = _adoption(5, "bh-protect-sleep", "watch", NOW)
    repeat = observation("sleep-duration", 5.0, NOW + dt.timedelta(hours=20), "crew-01", "s")
    later = NOW + dt.timedelta(hours=60)
    [worse] = followups([adopted], {"behavioral": RiskLevel.CONCERN}, [repeat], later)
    [same] = followups([adopted], {"behavioral": RiskLevel.WATCH}, [repeat], later)
    assert worse["evaluation"]["outcome"] == "worsened"
    assert same["evaluation"]["outcome"] == "unchanged"


def test_a_closure_closes_its_own_adoption_only() -> None:
    first = _adoption(5, "bh-protect-sleep", "watch", NOW)
    second = _adoption(6, "bh-repeat-pvt", "watch", NOW)
    closure = dict(first, ledger_index=7, action="closed", adoption_index="5", reason="hecho")
    states = {
        item["adoption_index"]: item["state"]
        for item in followups([first, second, closure], {}, [], NOW + dt.timedelta(hours=1))
    }
    assert states == {5: "closed", 6: "in_window"}


# --------------------------------------------------------------------------- #
# API: adoptar y cerrar, firmado y con 409
# --------------------------------------------------------------------------- #


@pytest.fixture
def insomnia(client: TestClient) -> dict:
    assert client.post(
        "/api/simulate", params={"scenario": "progressive-insomnia", "days": 40}
    ).status_code == 201
    status: dict = client.get("/api/status").json()
    return status


def test_adopting_follows_and_closing_ends_it(client: TestClient, insomnia: dict) -> None:
    chosen = insomnia["recommendations"][0]["countermeasure"]["id"]
    reference = insomnia["data"]["reference_time"]
    adopted = client.post("/api/countermeasures/adopt", json={
        "countermeasure_id": chosen, "reference_time": reference, "adopted_by": "CDR",
    })
    assert adopted.status_code == 201
    index = adopted.json()["ledger_index"]

    [follow] = client.get("/api/status").json()["followups"]
    assert follow["countermeasure"]["id"] == chosen
    assert follow["adopted_by"] == "CDR"
    assert follow["level_at_adoption"] == "concern"
    assert follow["state"] == "in_window"

    closed = client.post("/api/countermeasures/close", json={
        "adoption_index": index, "reason": "sueño recuperado", "closed_by": "CDR",
    })
    assert closed.status_code == 201
    [follow] = client.get("/api/status").json()["followups"]
    assert follow["state"] == "closed"
    assert follow["closed_reason"] == "sueño recuperado"

    again = client.post("/api/countermeasures/close", json={
        "adoption_index": index, "reason": "otra vez", "closed_by": "CDR",
    })
    assert again.status_code == 409
    assert client.get("/api/audit").status_code == 200


def test_what_was_not_recommended_cannot_be_adopted(client: TestClient, insomnia: dict) -> None:
    response = client.post("/api/countermeasures/adopt", json={
        "countermeasure_id": countermeasures.SHELTER_ID,
        "reference_time": insomnia["data"]["reference_time"], "adopted_by": "CDR",
    })
    assert response.status_code == 409


def test_a_closure_needs_an_adoption(client: TestClient, insomnia: dict) -> None:
    response = client.post("/api/countermeasures/close", json={
        "adoption_index": 0, "reason": "x", "closed_by": "CDR",
    })
    assert response.status_code == 409


def test_the_library_is_published(client: TestClient) -> None:
    body = client.get("/api/countermeasures").json()
    ids = {item["id"] for item in body["countermeasures"]}
    assert countermeasures.SHELTER_ID in ids
    assert all(item["ridge"] for item in body["countermeasures"])
