"""Comparación de un indicador entre tripulantes (especificación del equipo §10).

La especificación pide comparar tripulantes "para detectar posibles causas ambientales
compartidas". Estas pruebas fijan lo que hace honesta esa comparación: cada serie va contra la
línea base PROPIA de su tripulante, quien "se desvía" lo deciden las reglas de su estado y no
otras, quien no tiene dato se dice (no pasa por normal), el resumen solo cuenta coincidencias y
lo rotula como tal, Tierra no ve más de lo que le ha llegado, y nada de esto escribe en el
ledger.
"""

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.analysis.context import (
    ASSUMPTION,
    COINCIDENCE_LABEL,
    COMPARISON_IGNORES_LOCATION,
    coincidence,
)
from app.api import habitat as habitat_api
from app.api.routes import get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.core.storage import ObservationStore
from app.environment.habitat import Excursion
from app.main import app
from app.text_guard import check

T0 = dt.datetime(2026, 12, 1, 0, 0, tzinfo=dt.UTC)
WINDOW = dt.timedelta(days=2)
CREW = ["crew-01", "crew-02", "crew-03", "crew-04"]


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ObservationStore]:
    """El escenario de CO2 con sus cuatro tripulantes, sembrado una vez para todo el módulo.

    Sembrar cuatro tripulantes tarda un minuto y las pruebas que lo usan solo leen: repetirlo
    en cada una multiplicaba por siete la duración de este fichero.
    """
    cache: Path = tmp_path_factory.mktemp("cache")
    store = new_store()
    reset_store(store)
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=cache, offline=True)
    try:
        response = TestClient(app).post(
            "/api/simulate", params={"scenario": "co2-fatigue", "days": 40}
        )
        assert response.status_code == 201, response.text
        assert response.json()["simulation"]["crew"] == CREW
        yield store
    finally:
        app.dependency_overrides.clear()
        reset_store(None)


@pytest.fixture
def co2(client: TestClient, seeded: ObservationStore) -> TestClient:
    """El cliente de siempre (sin red), mirando al almacén ya sembrado."""
    reset_store(seeded)
    return client


def _excursion() -> list[Excursion]:
    return [Excursion("m1", "cabin-ppco2", "health", "[V2 6004]",
                      T0 - dt.timedelta(hours=30), T0, 4.2)]


def _moment(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text)


# --- La regla descriptiva, sin API ---------------------------------------------------------


def test_two_deviating_crew_coincide_since_the_last_one_to_deviate() -> None:
    early, late = T0 - dt.timedelta(hours=40), T0 - dt.timedelta(hours=10)
    result = coincidence(
        "Frecuencia cardiaca", {"crew-01": early, "crew-02": late, "crew-03": None}, set(),
        _excursion(), T0, WINDOW,
    )
    assert result["label"] == COINCIDENCE_LABEL == "coincidencia temporal, no causa"
    assert result["deviating"] == ["crew-01", "crew-02"]
    assert result["with_data"] == 3
    assert result["first_onset"] == early.isoformat()
    # "A la vez" empieza cuando se desvía el último, no el primero.
    assert result["simultaneous_since"] == late.isoformat()
    assert result["undated_note"] is None
    assert result["text"].startswith("Frecuencia cardiaca: 2 de 3 tripulantes")
    assert "no señala una causa común" in result["text"]
    assert [item["parameter"] for item in result["habitat_excursions"]] == ["cabin-ppco2"]
    assert result["assumption"] == ASSUMPTION


def test_a_drift_counts_but_has_no_start_to_report() -> None:
    result = coincidence(
        "Frecuencia cardiaca", {"crew-01": T0, "crew-02": None, "crew-03": None}, {"crew-02"},
        [], T0, WINDOW,
    )
    assert result["deviating"] == ["crew-01", "crew-02"]
    # Una pendiente no tiene instante de inicio: no se inventa, y se dice.
    assert result["simultaneous_since"] is None
    assert result["first_onset"] == T0.isoformat()
    assert "deriva sostenida" in result["undated_note"]


def test_one_deviating_crew_member_is_not_a_coincidence() -> None:
    result = coincidence(
        "Frecuencia cardiaca", {"crew-01": T0, "crew-02": None}, set(), _excursion(), T0, WINDOW
    )
    assert result["deviating"] == ["crew-01"]
    assert result["simultaneous_since"] is None
    assert "no hay coincidencia" in result["text"]
    # Sin coincidencia no se arrima la excursión de cabina a la frase.
    assert "límite normativo" not in result["text"]


def test_nobody_with_readings_is_not_reported_as_nobody_deviating() -> None:
    result = coincidence("Frecuencia cardiaca", {}, set(), [], T0, WINDOW)
    assert result["with_data"] == 0
    assert "no hay nada que comparar" in result["text"]
    assert "fuera de lo esperado" not in result["text"]


def test_an_old_excursion_is_not_put_next_to_a_new_coincidence() -> None:
    old = [Excursion("m1", "cabin-ppco2", "health", "[V2 6004]",
                     T0 - dt.timedelta(days=9), T0 - dt.timedelta(days=8), 4.0)]
    result = coincidence(
        "Frecuencia cardiaca", {"crew-01": T0, "crew-02": T0}, set(), old, T0, WINDOW
    )
    assert result["habitat_excursions"] == []
    assert "límite normativo" not in result["text"]


def test_every_summary_text_passes_the_guard() -> None:
    cases: list[tuple[dict[str, dt.datetime | None], set[str]]] = [
        ({}, set()),
        ({"crew-01": None, "crew-02": None}, set()),
        ({"crew-01": T0, "crew-02": None}, set()),
        ({"crew-01": T0, "crew-02": T0}, set()),
        ({"crew-01": T0, "crew-02": None}, {"crew-02"}),
    ]
    for onsets, drifting in cases:
        result = coincidence("Frecuencia cardiaca", onsets, drifting, _excursion(), T0, WINDOW)
        for text in (result["text"], result["undated_note"], result["onset_basis"]):
            if text is not None:
                assert check(text) == [], text


# --- La API --------------------------------------------------------------------------------


def test_the_seeded_crew_is_listed(co2: TestClient) -> None:
    assert co2.get("/api/crew/members").json() == {"crew": [{"subject": s} for s in CREW]}


def test_each_crew_member_gets_a_series_against_their_own_baseline(co2: TestClient) -> None:
    body = co2.get("/api/crew/compare", params={"key": "heart-rate"}).json()
    assert [item["subject"] for item in body["series"]] == CREW
    assert body["summary"]["label"] == COINCIDENCE_LABEL
    assert body["habitat"] is None
    reference, since = _moment(body["reference_time"]), _moment(body["since"])
    assert reference - since == dt.timedelta(days=14)
    baselines = []
    for item in body["series"]:
        assert item["state"] in {"within", "deviating"} and item["baseline_text"] is None
        # Cada serie dice de qué tipo y de qué entorno son sus lecturas.
        assert item["origins"] == [{"type": "measured", "context": "simulated"}]
        times = [_moment(point["effective"]) for point in item["points"]]
        # El mismo eje para todos, en orden.
        assert times == sorted(times)
        assert since <= times[0] and times[-1] <= reference
        assert _moment(item["latest"]) == times[-1]
        with_base = [point for point in item["points"] if point["delta"] is not None]
        assert with_base
        for point in with_base:
            assert point["delta"] == pytest.approx(point["value"] - point["baseline"], abs=1e-3)
        baselines.append(with_base[-1]["baseline"])
    # Bases propias: cuatro personas no comparten la misma mediana.
    assert len(set(baselines)) == len(CREW)


def test_who_deviates_is_what_each_crew_status_says(co2: TestClient) -> None:
    """La comparación no tiene reglas propias: cuenta lo que el estado de cada uno ya dice.

    En este escenario a los cuatro los mueve una DERIVA de la carga de síntomas, no lecturas
    sueltas. Mirando solo las lecturas, la comparación respondía "nadie se desvía" mientras
    `/crew` daba a los cuatro por afectados.
    """
    crew = co2.get("/api/crew").json()
    body = co2.get("/api/crew/compare", params={"key": "symptom-burden"}).json()
    summary = body["summary"]
    assert summary["deviating"] == crew["correlation"]["affected"] == CREW
    assert summary["with_data"] == len(CREW)
    assert summary["text"].startswith("Carga de síntomas autoinformada: 4 de 4 tripulantes")
    assert "CO2 de cabina" in summary["text"]
    assert check(summary["text"]) == []
    status_drivers = {
        member["subject"]: {text for risk in member["domains"].values() for text in risk["drivers"]}
        for member in crew["crew"]
    }
    for item in body["series"]:
        assert item["deviating"] and item["state"] == "deviating"
        assert item["state_text"] == "deriva sostenida"
        # Las mismas frases, palabra por palabra, que el estado de ese tripulante.
        assert item["drivers"] and set(item["drivers"]) <= status_drivers[item["subject"]]
        # Quien solo deriva no tiene instante de inicio.
        assert item["onset"] is None
    assert summary["simultaneous_since"] is None
    assert summary["undated_note"] is not None
    # `/crew` dice qué indicadores dan hallazgo en cada uno: es lo que propone qué comparar.
    assert all("symptom-burden" in member["indicators"] for member in crew["crew"])
    assert all("heart-rate" not in member["indicators"] for member in crew["crew"])

    # Y donde el estado no señala nada, la comparación tampoco.
    calm = co2.get("/api/crew/compare", params={"key": "heart-rate"}).json()
    assert calm["summary"]["deviating"] == []
    assert all(item["state_text"] == "dentro de lo esperado" for item in calm["series"])


def test_the_cabin_parameter_shares_the_axis_and_brings_its_excursion(co2: TestClient) -> None:
    body = co2.get(
        "/api/crew/compare", params={"key": "heart-rate", "parameter": "cabin-ppco2"}
    ).json()
    cabin = body["habitat"]
    assert cabin["parameter"]["key"] == "cabin-ppco2"
    assert cabin["state"] == "ok" and cabin["points"]
    assert cabin["evidence_contexts"] == ["simulated"]
    since = _moment(body["since"])
    assert all(_moment(point["effective"]) >= since for point in cabin["points"])
    assert [item["requirement"] for item in cabin["excursions"]] == ["[V2 6004]"]

    # Otro parámetro no arrastra la excursión del CO2, pero el resumen la sigue viendo.
    other = co2.get(
        "/api/crew/compare", params={"key": "heart-rate", "parameter": "cabin-temperature"}
    ).json()
    assert other["habitat"]["parameter"]["key"] == "cabin-temperature"
    assert all(item["parameter"] == "cabin-temperature" for item in other["habitat"]["excursions"])
    assert [item["parameter"] for item in other["summary"]["habitat_excursions"]] == ["cabin-ppco2"]


def test_an_unknown_indicator_or_parameter_is_a_404(co2: TestClient) -> None:
    unknown = co2.get("/api/crew/compare", params={"key": "no-existe"})
    assert unknown.status_code == 404
    assert "no-existe" in unknown.json()["detail"]
    response = co2.get(
        "/api/crew/compare", params={"key": "heart-rate", "parameter": "cabin-unicorn"}
    )
    assert response.status_code == 404
    assert co2.get("/api/crew/compare").status_code == 422


def test_ground_only_sees_what_has_arrived(co2: TestClient) -> None:
    full = co2.get("/api/crew/compare", params={"key": "symptom-burden"}).json()
    cut = _moment(full["reference_time"]) - dt.timedelta(days=5)
    body = co2.get(
        "/api/crew/compare",
        params={"key": "symptom-burden", "parameter": "cabin-ppco2", "until": cut.isoformat()},
    ).json()
    assert _moment(body["reference_time"]) <= cut
    for item in body["series"]:
        assert all(_moment(point["effective"]) <= cut for point in item["points"])
        assert _moment(item["latest"]) <= cut
    assert all(_moment(point["effective"]) <= cut for point in body["habitat"]["points"])
    # Cinco días antes el CO2 aún no había cruzado su límite: Tierra no puede saberlo todavía.
    assert body["habitat"]["excursions"] == []
    assert body["summary"]["habitat_excursions"] == []
    assert "límite normativo" not in body["summary"]["text"]

    # Antes de la primera lectura, Tierra no conoce a nadie.
    before = (_moment(full["since"]) - dt.timedelta(days=400)).isoformat()
    assert co2.get("/api/crew/members", params={"until": before}).json() == {"crew": []}
    early = co2.get("/api/crew/compare", params={"key": "heart-rate", "until": before})
    assert early.status_code == 404
    for path in ("/api/crew/compare", "/api/crew/members"):
        naive = co2.get(path, params={"key": "heart-rate", "until": "2026-12-01T00:00"})
        assert naive.status_code == 422, path


def test_comparing_is_read_only_and_moves_no_level(client: TestClient) -> None:
    # Almacén propio y pequeño: `/status` verifica la cadena entera y con el sembrado tarda.
    client.post("/api/simulate", params={"scenario": "nominal", "days": 4, "crew_size": 2})
    store = get_store()
    before = client.get("/api/status", params={"subject": "crew-02"}).json()
    assert before["subject"] == "crew-02"
    # `/status` firma sus proyecciones la primera vez: se cuenta después de pedirlo.
    entries = len(store.ledger)
    assert client.get("/api/crew/members").json() == {
        "crew": [{"subject": "crew-01"}, {"subject": "crew-02"}]
    }
    compared = client.get(
        "/api/crew/compare", params={"key": "heart-rate", "parameter": "cabin-ppco2"}
    )
    assert compared.status_code == 200
    assert len(store.ledger) == entries
    after = client.get("/api/status", params={"subject": "crew-02"}).json()
    assert len(store.ledger) == entries
    assert after["overall_level"] == before["overall_level"]
    assert {name: risk["level"] for name, risk in after["domains"].items()} == {
        name: risk["level"] for name, risk in before["domains"].items()
    }


def test_with_a_declared_location_the_summary_stops_claiming_emma_does_not_record_it(
    client: TestClient,
) -> None:
    """La comparación enumera las excursiones de cabina sin mirar dónde estaba cada uno. Con
    una ubicación declarada, decir que EMMA no la registra sería falso: dice que no la usa."""
    located = coincidence(
        "Frecuencia cardiaca", {"crew-01": T0, "crew-02": T0}, set(), _excursion(), T0, WINDOW, True
    )
    plain = coincidence(
        "Frecuencia cardiaca", {"crew-01": T0, "crew-02": T0}, set(), _excursion(), T0, WINDOW
    )
    assert located["assumption"] == COMPARISON_IGNORES_LOCATION
    assert check(COMPARISON_IGNORES_LOCATION) == []
    # Solo cambia la frase del supuesto: lo que se cuenta es lo mismo.
    assert {k: v for k, v in located.items() if k != "assumption"} == {
        k: v for k, v in plain.items() if k != "assumption"
    }

    # Por la API, con la ubicación firmada en el ledger.
    client.post("/api/simulate", params={"scenario": "nominal", "days": 4, "crew_size": 2})
    before = client.get("/api/crew/compare", params={"key": "heart-rate"}).json()
    assert before["summary"]["assumption"] == ASSUMPTION
    declared = client.post("/api/mission/events", json={
        "subject": "crew-02", "kind": "location", "module": "laboratorio",
        "start": "2026-01-01T00:00:00+00:00", "end": "2027-12-31T00:00:00+00:00",
        "declared_by": "CDR",
    })
    assert declared.status_code == 201, declared.text
    after = client.get("/api/crew/compare", params={"key": "heart-rate"}).json()
    assert after["summary"]["assumption"] == COMPARISON_IGNORES_LOCATION
    # Las series y el resto del resumen no se mueven por declarar una ubicación.
    assert after["series"] == before["series"]
    assert {k: v for k, v in after["summary"].items() if k != "assumption"} == {
        k: v for k, v in before["summary"].items() if k != "assumption"
    }


def test_the_fixed_texts_of_a_series_pass_the_guard() -> None:
    for text in (
        habitat_api.NO_DATA, habitat_api.NO_RECENT, habitat_api.WITHIN,
        habitat_api.OUT_OF_EXPECTED, habitat_api.DRIFTING, habitat_api.NO_BASELINE,
        habitat_api.BASELINE_BASIS, habitat_api.WINDOW_BASIS,
    ):
        assert check(text) == [], text
    assert "48 h" in habitat_api.WINDOW_BASIS


def test_an_empty_store_has_no_crew_to_compare(client: TestClient) -> None:
    assert client.get("/api/crew/members").json() == {"crew": []}
    assert client.get("/api/crew/compare", params={"key": "heart-rate"}).status_code == 404


def test_a_crew_member_without_readings_says_so_and_is_not_counted(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "nominal", "days": 4})
    first = client.get("/api/crew/compare", params={"key": "heart-rate"}).json()
    reference = _moment(first["reference_time"])

    def record(subject: str, back: dt.timedelta) -> None:
        response = client.post("/api/observations", json={
            "key": "heart-rate", "value": 61, "subject": subject,
            "effective": (reference - back).isoformat(),
        })
        assert response.status_code == 201, response.text

    record("crew-08", dt.timedelta(days=3))   # dentro del tramo, fuera de la ventana comparada
    record("crew-09", dt.timedelta(hours=1))  # una sola lectura reciente

    sleep = client.get("/api/crew/compare", params={"key": "sleep-duration"}).json()
    by_subject = {item["subject"]: item for item in sleep["series"]}
    assert set(by_subject) == {"crew-01", "crew-08", "crew-09"}
    for subject in ("crew-08", "crew-09"):
        missing = by_subject[subject]
        assert (missing["state"], missing["state_text"]) == ("no_data", "sin dato")
        assert missing["points"] == [] and missing["latest"] is None
        assert missing["origins"] == []
        assert not missing["deviating"]
    # Quien no tiene dato no cuenta como "dentro de lo esperado".
    assert sleep["summary"]["with_data"] == 1

    pulse = client.get("/api/crew/compare", params={"key": "heart-rate"}).json()
    by_subject = {item["subject"]: item for item in pulse["series"]}
    stale = by_subject["crew-08"]
    assert (stale["state"], stale["state_text"]) == (
        "no_recent", "sin lecturas en la ventana comparada"
    )
    assert len(stale["points"]) == 1
    lone = by_subject["crew-09"]
    # Una sola lectura no es una línea base: se dice, y no se inventa la diferencia.
    assert lone["state"] == "within"
    assert "sin línea base personal" in lone["baseline_text"]
    assert [point["delta"] for point in lone["points"]] == [None]
    assert pulse["summary"]["with_data"] == 2
    # Un tripulante simulado y una lectura real, en la misma vista: cada serie dice lo suyo.
    assert by_subject["crew-01"]["origins"] == [{"type": "measured", "context": "simulated"}]
    assert lone["origins"] == [{"type": "measured", "context": "ground"}]


def test_nobody_with_readings_of_the_indicator(client: TestClient) -> None:
    client.post("/api/observations", json={"key": "heart-rate", "value": 61})
    body = client.get(
        "/api/crew/compare", params={"key": "sleep-duration", "parameter": "cabin-ppco2"}
    ).json()
    assert body["reference_time"] is None and body["since"] is None
    assert [item["state_text"] for item in body["series"]] == ["sin dato"]
    # Sin lecturas del indicador no hay eje: la serie de cabina sola no se entrega.
    assert body["habitat"] is None
    assert "no hay nada que comparar" in body["summary"]["text"]
