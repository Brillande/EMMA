"""La ubicación del tripulante en el estado: declarada o estimada por las anclas, nunca simulada.

El panel «Sububicación» de «Inicio» decía «Sin módulo: el backend no lo da». Desde el 2026-11-09
el estado sirve `mission.location`; aquel día el simulador ponía a cada tripulante simulado en un
módulo. El 2026-11-10 el usuario lo quitó («no las queremos simuladas, las queremos reales»): la
ubicación sale de la consola o de las anclas de módulo de la nave (`analysis/location.py`). Aquí:

- el simulador ya no pone a nadie en ningún sitio, y sin anclas la medida está «no disponible»;
- el estado sirve la ubicación del instante de referencia con su origen (`source`), su estado
  (`location_state`) y, si no hay, el texto de lo que falta, con las palabras de la vista de
  tripulación y de la radiación de la tripulación;
- la consola manda aunque las lecturas de las anclas lleguen después;
- lo estimado se dice como estimado, ambiguo o caducado;
- Tierra solo ve lo que existía en su corte;
- la ubicación no mueve ningún nivel ni ninguna alerta (invariante 5).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis.context import (
    ASSUMPTION_ESTIMATED_LOCATED,
    ASSUMPTION_LOCATED,
    CHECK_ESTIMATED_LOCATION,
    UNIDENTIFIED_ESTIMATED_LOCATED,
    Stay,
    correlate,
)
from app.analysis.location import (
    LOCATION_BASIS,
    LOCATION_MISSING,
    LOCATION_UNAVAILABLE,
    sensing,
)
from app.api import routes
from app.api.mission import crew_stays
from app.api.routes import get_store, identity_for
from app.core.identities import ANCHOR_IDENTITY
from app.core.storage import seed_from_simulator
from app.environment.habitat import DEFAULT_MODULE, MODULES, Excursion
from app.ingest.simulator import LITERATURE, CrewMember, PhysiologicalSimulator

DAYS = 10
NOMINAL = {"scenario": "nominal", "days": DAYS, "crew_size": 3, "habitat_modules": 4}
START = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)
CREW = ("crew-01", "crew-02", "crew-03")
LAB = "laboratorio"
AWAY = next(key for key in MODULES if key not in (LAB, DEFAULT_MODULE))
LAB_ANCHOR = "lab-01"
AWAY_ANCHOR = "away-01"


def _locations(subject: str) -> list[dict[str, Any]]:
    return [item for item in get_store().mission_events(subject) if item["kind"] == "location"]


def _status(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/api/status", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _reference(client: TestClient) -> dt.datetime:
    return dt.datetime.fromisoformat(_status(client)["data"]["reference_time"])


def _anchors(client: TestClient) -> None:
    for anchor, module in ((LAB_ANCHOR, LAB), (AWAY_ANCHOR, AWAY)):
        response = client.post("/api/location/anchors", json={
            "anchor_id": anchor, "module": module, "since": START.isoformat(),
            "declared_by": "CDR",
        })
        assert response.status_code == 201, response.text


def _heard(subject: str, *rows: tuple[str, float, dt.datetime]) -> int:
    """Un lote firmado como las anclas, sin la ventana de fechas de la ruta: el escenario simulado
    está fechado en la misión, no en el reloj de quien corre la prueba (la ruta tiene sus pruebas
    en `test_location_anchors.py`)."""
    entry = get_store().record_location_sightings(
        subject, list(rows), identity_for(ANCHOR_IDENTITY)
    )
    return entry.index


def _in_lab(reference: dt.datetime, seconds: int = 60) -> list[tuple[str, float, dt.datetime]]:
    return [
        row
        for back in range(seconds, -1, -5)
        for row in (
            (LAB_ANCHOR, -55.0, reference - dt.timedelta(seconds=back)),
            (AWAY_ANCHOR, -80.0, reference - dt.timedelta(seconds=back)),
        )
    ]


def test_the_simulator_places_nobody_and_without_anchors_the_measure_is_unavailable(
    client: TestClient,
) -> None:
    assert client.post("/api/simulate", params=NOMINAL).status_code == 201
    # Ni un asiento de ubicación del simulador, ni su parámetro de diseño.
    assert all(_locations(subject) == [] for subject in CREW)
    assert "simulated_location_declarations_per_crew" not in LITERATURE
    mission = _status(client)["mission"]
    assert mission["location"] is None
    assert mission["location_state"] == "unavailable"
    assert mission["location_missing_text"] == LOCATION_UNAVAILABLE
    assert mission["location_basis"] == LOCATION_BASIS
    # La vista de tripulación y la radiación de la tripulación dicen lo mismo.
    crew = {item["subject"]: item for item in client.get("/api/crew").json()["crew"]}
    assert crew["crew-01"]["location"] is None
    assert crew["crew-01"]["location_state"] == "unavailable"
    assert crew["crew-01"]["location_missing_text"] == LOCATION_UNAVAILABLE
    rows = {item["subject"]: item for item in client.get("/api/crew/radiation").json()["crew"]}
    assert rows["crew-01"]["location_state"] == "unavailable"


def test_with_anchors_but_nothing_heard_the_location_is_missing(client: TestClient) -> None:
    store = get_store()
    simulator = PhysiologicalSimulator(seed=7, crew=CrewMember(subject_id="crew-01"))
    seed_from_simulator(store, simulator.generate(days=3), identity_for("simulator"))
    _anchors(client)
    mission = _status(client)["mission"]
    assert (mission["location"], mission["location_state"]) == (None, "missing")
    assert mission["location_missing_text"] == LOCATION_MISSING


def test_a_console_declaration_is_declared(client: TestClient) -> None:
    client.post("/api/simulate", params=NOMINAL)
    response = client.post("/api/mission/events", json={
        "subject": "crew-01", "kind": "location", "module": LAB,
        "start": START.isoformat(), "end": "2026-12-31T00:00:00+00:00", "declared_by": "CDR",
    })
    assert response.status_code == 201, response.text
    mission = _status(client)["mission"]
    location = mission["location"]
    assert (location["module"], location["source"]) == (LAB, "console")
    assert location["ledger_index"] == response.json()["ledger_index"]
    assert location["last_seen"] is None
    assert (mission["location_state"], mission["location_missing_text"]) == ("declared", None)


def test_the_anchors_estimate_the_module_and_every_view_says_the_same(
    client: TestClient,
) -> None:
    client.post("/api/simulate", params=NOMINAL)
    _anchors(client)
    reference = _reference(client)
    batch = _heard("crew-01", *_in_lab(reference))
    store = get_store()
    entry = store.ledger.entries[batch]
    # Una entrada del ledger por lote, firmada como las anclas (invariante 4).
    assert (entry.entry_type, entry.signer) == ("location-sightings", ANCHOR_IDENTITY)
    assert store.verify_integrity().ok

    mission = _status(client)["mission"]
    location = mission["location"]
    assert (location["module"], location["source"]) == (LAB, "anchors")
    assert location["ledger_index"] == batch
    assert dt.datetime.fromisoformat(location["last_seen"]) == reference
    assert (mission["location_state"], mission["location_missing_text"]) == ("estimated", None)
    crew = {item["subject"]: item for item in client.get("/api/crew").json()["crew"]}
    assert crew["crew-01"]["location"] == location
    assert crew["crew-01"]["location_state"] == "estimated"
    rows = {item["subject"]: item for item in client.get("/api/crew/radiation").json()["crew"]}
    assert rows["crew-01"]["location"] == location
    assert rows["crew-01"]["location_state"] == "estimated"
    # A quien no oyó nada no se le estima: hay anclas, pero de él no se sabe.
    assert crew["crew-02"]["location_state"] == "missing"


def test_balanced_anchors_are_ambiguous_and_name_both_modules(client: TestClient) -> None:
    client.post("/api/simulate", params=NOMINAL)
    _anchors(client)
    reference = _reference(client)
    _heard("crew-01", *(
        row
        for back in range(60, -1, -5)
        for row in (
            (LAB_ANCHOR, -60.0, reference - dt.timedelta(seconds=back)),
            (AWAY_ANCHOR, -62.0, reference - dt.timedelta(seconds=back)),
        )
    ))
    mission = _status(client)["mission"]
    assert (mission["location"], mission["location_state"]) == (None, "ambiguous")
    assert "Laboratorio" in mission["location_missing_text"]
    assert "indeterminada" in mission["location_missing_text"]


def test_an_old_estimate_is_stale_and_says_when_it_was_heard(client: TestClient) -> None:
    client.post("/api/simulate", params=NOMINAL)
    _anchors(client)
    reference = _reference(client)
    old = reference - dt.timedelta(seconds=sensing().stale_after_s + 30)
    _heard("crew-01", *_in_lab(old, seconds=20))
    mission = _status(client)["mission"]
    assert mission["location_state"] == "stale"
    assert mission["location"]["source"] == "anchors"
    assert dt.datetime.fromisoformat(mission["location"]["last_seen"]) == old
    assert "caducada" in mission["location_missing_text"]


def test_the_console_wins_even_when_the_anchors_are_heard_after_it(client: TestClient) -> None:
    client.post("/api/simulate", params=NOMINAL)
    _anchors(client)
    declared = client.post("/api/mission/events", json={
        "subject": "crew-01", "kind": "location", "module": AWAY,
        "start": START.isoformat(), "end": "2026-12-31T00:00:00+00:00", "declared_by": "CDR",
    }).json()["ledger_index"]
    batch = _heard("crew-01", *_in_lab(_reference(client)))
    assert batch > declared
    mission = _status(client)["mission"]
    assert (mission["location"]["module"], mission["location"]["source"]) == (AWAY, "console")
    assert mission["location_state"] == "declared"
    # Las dos siguen ahí: la estimada no se borra, la tapa la consola.
    sources = sorted(stay.source for stay in crew_stays(get_store(), "crew-01"))
    assert sources == ["anchors", "console"]


def test_earth_only_sees_what_existed_at_its_cut(client: TestClient) -> None:
    client.post("/api/simulate", params=NOMINAL)
    cut = dt.datetime.now(dt.UTC)
    before = _status(client, until=cut.isoformat())
    assert before["mission"]["location_state"] == "unavailable"
    # Lo que Tierra ve como instante de referencia (lo llegado hasta su corte), oído después.
    reference = dt.datetime.fromisoformat(before["data"]["reference_time"])
    _anchors(client)
    _heard("crew-01", *_in_lab(reference))
    # Con su corte anterior a las anclas y a las lecturas, Tierra no estima nada.
    earth = _status(client, until=cut.isoformat())["mission"]
    assert (earth["location"], earth["location_state"]) == (None, "unavailable")
    # Con un corte posterior, sí: lo mismo que a bordo para ese instante.
    later = _status(client, until=dt.datetime.now(dt.UTC).isoformat())["mission"]
    assert (later["location"]["module"], later["location_state"]) == (LAB, "estimated")


def _verdict(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "domains": {name: item["level"] for name, item in status["domains"].items()},
        "alerts": [(alert["domain"], alert["level"]) for alert in status["alerts"]],
        "overall": status["overall_level"],
    }


def test_the_estimated_location_never_moves_a_level_or_an_alert(client: TestClient) -> None:
    client.post("/api/simulate", params={
        "scenario": "co2-fatigue", "days": DAYS, "crew_size": 3, "habitat_modules": 4,
    })
    before = {subject: _verdict(_status(client, subject=subject)) for subject in CREW}
    crew_before = client.get("/api/crew").json()
    _anchors(client)
    reference = _reference(client)
    for subject in CREW:
        _heard(subject, *_in_lab(reference, seconds=600))
    after = {subject: _verdict(_status(client, subject=subject)) for subject in CREW}
    assert after == before
    crew_after = client.get("/api/crew").json()
    assert [(item["subject"], item["overall_level"]) for item in crew_after["crew"]] == [
        (item["subject"], item["overall_level"]) for item in crew_before["crew"]
    ]


def test_the_status_reads_only_the_sightings_that_can_speak_of_its_instant(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.post("/api/simulate", params={**NOMINAL, "crew_size": 1})
    _anchors(client)
    reference = _reference(client)
    _heard("crew-01", *_in_lab(reference - dt.timedelta(days=2)))
    store = get_store()
    asked: list[dt.datetime | None] = []
    original = store.location_sightings

    def spy(subject: str, since: dt.datetime | None = None) -> list[dict[str, Any]]:
        asked.append(since)
        return original(subject, since)

    monkeypatch.setattr(store, "location_sightings", spy)
    _status(client)
    assert asked == [reference - sensing().lookback]


def test_a_batch_of_sightings_is_a_real_record_that_a_scenario_switch_cannot_drop(
    client: TestClient,
) -> None:
    client.post("/api/simulate", params=NOMINAL)
    _heard("crew-01", (LAB_ANCHOR, -60.0, START))
    response = client.post("/api/simulate", params={**NOMINAL, "replace": True})
    assert response.status_code == 409
    assert ANCHOR_IDENTITY in response.json()["detail"]


def test_the_correlation_does_not_present_an_estimated_location_as_a_person_s_declaration() -> None:
    reference = START + dt.timedelta(days=9)
    found = [Excursion(
        module=DEFAULT_MODULE, parameter="cabin-ppco2", kind="health", requirement="[V2 6004]",
        start=reference - dt.timedelta(hours=6), end=reference, worst=5.0,
    )]
    levels = {"crew-01": "concern", "crew-02": "watch"}
    span = (reference - dt.timedelta(days=3), reference + dt.timedelta(days=1))

    def located(source: str) -> dict[str, list[Stay]]:
        return {subject: [Stay(AWAY, *span, 1, source=source)] for subject in levels}

    estimated = correlate(levels, found, reference, dt.timedelta(hours=24), located("anchors"))
    console = correlate(levels, found, reference, dt.timedelta(hours=24), located("console"))
    assert estimated["assumption"] == ASSUMPTION_ESTIMATED_LOCATED
    assert console["assumption"] == ASSUMPTION_LOCATED
    [demoted] = [h for h in estimated["hypotheses"] if h["kind"] == "shared_environment"]
    assert "anclas" in demoted["likelihood_reason"]
    assert "declara una persona" not in demoted["likelihood_reason"]
    [declared] = [h for h in console["hypotheses"] if h["kind"] == "shared_environment"]
    assert "la declara una persona" in declared["likelihood_reason"]
    # La regla es la misma: solo cambia cómo se dice.
    assert [h["kind"] for h in estimated["hypotheses"]] == [
        h["kind"] for h in console["hypotheses"]
    ]
    [unknown] = [h for h in estimated["hypotheses"] if h["kind"] == "shared_unknown"]
    assert unknown["title"] == UNIDENTIFIED_ESTIMATED_LOCATED
    assert unknown["checks"][0] == CHECK_ESTIMATED_LOCATION


def test_a_console_declaration_over_an_estimate_is_said_as_declared() -> None:
    reference = START + dt.timedelta(days=9)
    span = (reference - dt.timedelta(days=3), reference + dt.timedelta(days=1))
    # La estimada es posterior en el ledger y aun así manda la consola.
    stays = [
        Stay(AWAY, *span, 1, source="console"),
        Stay(DEFAULT_MODULE, *span, 2, source="anchors"),
    ]
    found = [Excursion(
        module=DEFAULT_MODULE, parameter="cabin-ppco2", kind="health", requirement="[V2 6004]",
        start=reference - dt.timedelta(hours=6), end=reference, worst=5.0,
    )]
    result = correlate(
        {"crew-01": "concern", "crew-02": "watch"}, found, reference, dt.timedelta(hours=24),
        {"crew-01": stays, "crew-02": stays},
    )
    assert result["assumption"] == ASSUMPTION_LOCATED
    [demoted] = [h for h in result["hypotheses"] if h["kind"] == "shared_environment"]
    assert demoted["likelihood"] == "less_likely"
    assert "la declara una persona" in demoted["likelihood_reason"]


def test_no_route_can_sign_a_reading_as_the_anchors(client: TestClient) -> None:
    response = client.post(
        "/api/observations",
        json={"key": "heart-rate", "value": 61.0, "source": ANCHOR_IDENTITY},
    )
    assert response.status_code == 422
    assert routes._is_reserved_source(ANCHOR_IDENTITY)
