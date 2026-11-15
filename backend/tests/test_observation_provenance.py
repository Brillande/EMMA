"""Medido / inferido / predicho y entorno de cada dato (especificacion del equipo §2, §14).

La especificacion exige que ningun valor calculado o proyectado se presente con el mismo
aspecto que una lectura de sensor, y que no se mezclen datos de la ISS, de un analogo, de
Tierra o simulados sin decirlo. Estas pruebas fijan las dos etiquetas de punta a punta:
modelo, ledger, FHIR, API y estado.
"""

import datetime as dt
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.analysis.trend import Direction, Trend, projection
from app.api.routes import get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.core.ledger import Identity
from app.core.storage import ObservationStore, _from_payload
from app.ingest.fhir import (
    EvidenceContext,
    ObservationType,
    VitalObservation,
    deployed,
    observation,
)
from app.ingest.inspiration4 import SOURCE as INSPIRATION4_SOURCE
from app.ingest.simulator import PhysiologicalSimulator, Scenario
from app.main import app

NOW = dt.datetime(2026, 11, 14, 8, 0, tzinfo=dt.UTC)


def test_a_value_that_is_not_measured_must_name_its_model() -> None:
    with pytest.raises(ValueError, match="model_version"):
        observation(
            "cumulative-dose", 12.0, NOW, "crew-01", "dosimetria",
            observation_type=ObservationType.INFERRED,
        )
    inferred = observation(
        "cumulative-dose", 12.0, NOW, "crew-01", "dosimetria",
        observation_type=ObservationType.INFERRED, model_version="q-medio@1",
    )
    assert inferred.observation_type is ObservationType.INFERRED


def test_the_environment_is_deduced_only_when_nobody_declared_it() -> None:
    assert observation("heart-rate", 60, NOW, "c", "simulator:nominal").evidence is (
        EvidenceContext.SIMULATED
    )
    assert observation("heart-rate", 60, NOW, "c", INSPIRATION4_SOURCE).evidence is (
        EvidenceContext.SPACEFLIGHT
    )
    assert observation("heart-rate", 60, NOW, "c", "wearable-ble").evidence is (
        EvidenceContext.GROUND
    )
    declared = observation(
        "heart-rate", 60, NOW, "c", "wearable-ble", evidence_context=EvidenceContext.ISS
    )
    assert declared.evidence is EvidenceContext.ISS


def test_entries_written_before_the_labels_read_as_measured() -> None:
    """Un asiento antiguo no lleva los campos: era una medida y su entorno sale de la fuente."""
    old = {
        "subject": "crew-01", "key": "heart-rate", "value": 61.0,
        "effective": NOW.isoformat(), "source": "simulator:nominal",
        "context": "rest", "confidence": 1.0,
    }
    reading = _from_payload(old, NOW)
    assert reading.observation_type is ObservationType.MEASURED
    assert reading.evidence is EvidenceContext.SIMULATED
    assert reading.model_version is None


def test_the_labels_travel_through_the_ledger() -> None:
    store = ObservationStore.in_memory()
    identity = Identity.generate("dosimetria")
    store.record(
        observation(
            "cumulative-dose", 40.0, NOW, "crew-01", "dosimetria",
            observation_type=ObservationType.INFERRED,
            evidence_context=EvidenceContext.ISS, model_version="q-medio@1",
        ),
        identity,
    )
    payload = store.ledger.entries[-1].payload
    assert payload is not None
    assert payload["observation_type"] == "inferred"
    assert payload["evidence_context"] == "iss"
    assert payload["model_version"] == "q-medio@1"

    reading = store.query("crew-01")[0]
    assert (reading.observation_type, reading.evidence, reading.model_version) == (
        ObservationType.INFERRED, EvidenceContext.ISS, "q-medio@1"
    )
    assert store.verify_integrity().ok


def test_the_labels_survive_a_fhir_round_trip_and_validate() -> None:
    original = observation(
        "cumulative-dose", 40.0, NOW, "crew-01", "dosimetria",
        observation_type=ObservationType.INFERRED,
        evidence_context=EvidenceContext.ANALOG_BEDREST, model_version="q-medio@1",
    )
    assert original.validates()
    back = VitalObservation.from_fhir(original.to_fhir())
    assert back.observation_type is ObservationType.INFERRED
    assert back.evidence is EvidenceContext.ANALOG_BEDREST
    assert back.model_version == "q-medio@1"


def test_the_simulator_says_it_is_simulated_and_how_to_reproduce_it() -> None:
    reading = next(PhysiologicalSimulator(Scenario.NOMINAL, seed=7).generate(days=1))
    assert reading.evidence is EvidenceContext.SIMULATED
    assert reading.model_version == "simulator:nominal@7"


def test_deployment_relabels_real_readings_and_leaves_simulated_ones() -> None:
    real = observation("heart-rate", 60, NOW, "c", "wearable-ble")
    simulated = observation("heart-rate", 60, NOW, "c", "simulator:nominal")
    relabelled = deployed([real, simulated], EvidenceContext.ISS)
    assert [item.evidence for item in relabelled] == [
        EvidenceContext.ISS, EvidenceContext.SIMULATED
    ]


def _trend(significant: bool, direction: Direction) -> Trend:
    return Trend(
        key="heart-rate", slope_per_day=0.5, t_statistic=5.0, points=40, span_days=21,
        direction=direction, significant=significant, mean_value=64.0,
        standard_error=0.05,
    )


def test_a_projection_is_labelled_predicted_with_its_model_and_margin() -> None:
    item = projection(_trend(True, Direction.RISING))
    assert item is not None
    assert item["observation_type"] == "predicted"
    assert item["model_version"]
    assert item["projected_change_low"] < item["projected_change"] < item[
        "projected_change_high"
    ]
    assert "no es un pronóstico clínico" in item["basis"]


def test_noise_is_never_projected() -> None:
    assert projection(_trend(False, Direction.RISING)) is None
    assert projection(_trend(True, Direction.STABLE)) is None


@pytest.fixture
def iss_client(tmp_path) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, deployment_context=EvidenceContext.ISS
    )
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def test_manual_readings_take_the_deployment_environment(iss_client: TestClient) -> None:
    response = iss_client.post(
        "/api/observations", json={"key": "heart-rate", "value": 62.0}
    )
    assert response.status_code == 201
    reading = get_store().query("crew-01")[0]
    assert reading.evidence is EvidenceContext.ISS
    assert reading.observation_type is ObservationType.MEASURED


def test_the_api_refuses_an_inferred_value_without_its_model(iss_client: TestClient) -> None:
    response = iss_client.post(
        "/api/observations",
        json={"key": "cumulative-dose", "value": 12.0, "observation_type": "inferred"},
    )
    assert response.status_code == 422
    assert "model_version" in response.text


def test_the_status_labels_dose_projections_and_provenance(iss_client: TestClient) -> None:
    assert iss_client.post(
        "/api/simulate", params={"scenario": "cardiovascular-deconditioning", "days": 40}
    ).status_code == 201
    status = iss_client.get("/api/status").json()

    assert status["dose"]["observation_type"] == "inferred"
    assert status["provenance"]["evidence_context"] == {
        "simulated": status["data"]["observations"]
    }
    assert status["provenance"]["observation_type"] == {
        "measured": status["data"]["observations"]
    }
    assert status["predictions"], "el desacondicionamiento deriva: tiene que proyectarse"
    assert all(item["observation_type"] == "predicted" for item in status["predictions"])
