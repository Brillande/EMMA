"""Analíticas reales de Inspiration4 (OSD-569): se reproducen tal cual, y lo incoherente se aparta.

El fichero de OSDR viaja con el paquete y se verifica por su huella: estas pruebas no tocan la
red (invariante 3) y leen exactamente los datos que se revisaron.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes import get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.evidence.links import evidence_for
from app.ingest import inspiration4
from app.ingest.codes import Domain
from app.main import app

LAUNCH = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)


@pytest.fixture(scope="module")
def replay() -> inspiration4.Replay:
    return inspiration4.load(LAUNCH)


def value(replay: inspiration4.Replay, subject: str, key: str, when: dt.datetime) -> float:
    [reading] = [
        o for o in replay.observations
        if o.subject == subject and o.key == key and o.effective == when
    ]
    return reading.value


def test_every_coherent_sample_is_replayed(replay: inspiration4.Replay) -> None:
    # 4 tripulantes × 7 momentos = 28 muestras; una apartada; 3 indicadores por muestra.
    assert len(replay.observations) == 27 * 3
    assert {o.subject for o in replay.observations} == set(inspiration4.CREW.values())
    assert {o.source for o in replay.observations} == {inspiration4.SOURCE}


def test_the_shifted_row_in_the_source_is_excluded_and_said(replay: inspiration4.Replay) -> None:
    """En origen, C003 L-92 trae los absolutos desplazados una columna: la suma cuadra igual."""
    [reason] = replay.excluded
    assert reason.startswith("C003 L-92")
    assert "columnas desplazadas" in reason


def test_counts_are_converted_to_the_loinc_unit(replay: inspiration4.Replay) -> None:
    # C001 en L-3: 2667 linfocitos/µL en origen = 2,667 × 10³/µL; leucocitos ya en miles.
    at = LAUNCH - dt.timedelta(days=3)
    assert value(replay, "crew-01", "lymphocytes", at) == pytest.approx(2.667)
    assert value(replay, "crew-01", "leukocytes", at) == pytest.approx(7.0)


def test_the_timeline_puts_return_three_days_after_launch() -> None:
    assert inspiration4.moment("L-92", LAUNCH) == LAUNCH - dt.timedelta(days=92)
    assert inspiration4.moment("R+1", LAUNCH) == LAUNCH + dt.timedelta(days=4)
    with pytest.raises(ValueError):
        inspiration4.moment("X+1", LAUNCH)


def test_the_real_signal_every_crew_member_lost_lymphocytes_on_return(
    replay: inspiration4.Replay,
) -> None:
    """Lo que estos datos documentan: R+1 frente a L-3, los cuatro por debajo."""
    before, after = LAUNCH - dt.timedelta(days=3), LAUNCH + dt.timedelta(days=4)
    for subject in inspiration4.CREW.values():
        assert value(replay, subject, "lymphocytes", after) < value(
            replay, subject, "lymphocytes", before
        ), subject


def test_a_changed_data_file_replays_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inspiration4, "DATA_SHA256", "0" * 64)
    with pytest.raises(inspiration4.DataFileChanged):
        inspiration4.load(LAUNCH)


def test_a_permuted_row_is_caught_even_when_its_sum_matches() -> None:
    header = (
        "Sample Name,white_blood_cell_count_value_thousand_per_microliter,"
        "absolute_lymphocytes_value_cells_per_microliter,"
        "absolute_neutrophils_value_cells_per_microliter,"
        "lymphocytes_value_percent,neutrophils_value_percent\n"
    )
    good = "C001_whole-blood_L-3_cbc,10.0,2000,7000,20,70\n"
    permuted = "C002_whole-blood_L-3_cbc,10.0,7000,2000,20,70\n"
    result = inspiration4.load(LAUNCH, raw=(header + good + permuted).encode())
    assert len(result.observations) == 3
    assert result.excluded and result.excluded[0].startswith("C002 L-3")


def test_the_immune_domain_cites_the_real_study() -> None:
    sources = [item.source for item in evidence_for(Domain.IMMUNE)]
    # La fuente lleva detrás su fecha de publicación desde que el registro la tiene leída
    # (décima ronda): se fija qué estudio se cita, no cómo se redacta la ficha.
    assert any(source.startswith("NASA OSDR · OSD-569") for source in sources)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def test_the_replay_enters_signed_as_simulated_with_its_citation(client: TestClient) -> None:
    response = client.post("/api/replay/inspiration4")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["recorded"] == 81
    assert "osdr.nasa.gov" in body["citation"]
    assert len(body["excluded"]) == 1

    assert get_store().reading_signers() == {"simulator"}
    status = client.get("/api/status", params={"subject": "crew-02"}).json()
    assert status["mission"]["mode"] == "simulation"
    # Lo simulado se puede sustituir: la reproducción no bloquea un cambio de escenario.
    switch = client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 1, "replace": "true"}
    )
    assert switch.status_code == 201
