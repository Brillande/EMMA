"""La radiación en el estado del hábitat: se enseña con su origen y no decide nada.

Decisión del usuario del 2026-10-26 (decimoséptima ronda, U4): la especificación (§3,
HabitatState) pide «radiation» en el estado del hábitat y la base de conocimiento (§10, Habitat
Twin) la pone entre lo que el hábitat cambia en la persona. `GET /api/habitat` enseña la última
tasa de dosis de cada dosímetro y el evento solar vigente, cada cifra con de dónde sale, con el
módulo sin declarar (no se sabe dónde está el dosímetro) y sin factores de blindaje (el refugio
por módulo está rechazado en «No se adopta»).

Lo que estas pruebas fijan: la cifra es la del registro tal cual y de quién es; el corte de
Tierra; el evento es el mismo que elige el estado; sin DONKI se dice que falta; nada de esto es
una excursión ni firma nada, y lo que decide el motor es lo mismo con o sin ello. Sin red.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import twins
from app.api import routes
from app.api.routes import get_store
from app.environment import habitat
from app.environment.donki import EventType, SolarEvent
from app.environment.donki import Severity as SolarSeverity
from app.text_guard import check
from tests.test_habitat_sources import _verdict

T0 = dt.datetime(2026, 12, 1, 0, 0, tzinfo=dt.UTC)


def _dose(client: TestClient, subject: str, value: float, at: dt.datetime,
          source: str = "dosimeter") -> None:
    response = client.post("/api/observations", json={
        "key": "absorbed-dose-rate", "value": value, "subject": subject, "source": source,
        "effective": at.isoformat(),
    })
    assert response.status_code == 201, response.text


def _event(event_id: str, kind: EventType, severity: SolarSeverity, at: dt.datetime) -> SolarEvent:
    return SolarEvent(
        event_id=event_id, event_type=kind, time=at, severity=severity, instruments=(),
        linked_event_ids=(), flare_class=None, link=f"https://example.invalid/{event_id}",
    )


def _radiation(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/api/habitat", params=params)
    assert response.status_code == 200, response.text
    radiation: dict[str, Any] = response.json()["radiation"]
    return radiation


def test_each_dosimeter_shows_its_last_signed_reading_with_its_owner_and_no_module(
    client: TestClient,
) -> None:
    _dose(client, "crew-01", 10.0, T0)
    _dose(client, "crew-01", 14.3, T0 + dt.timedelta(hours=1), source="dosimeter-a")
    _dose(client, "crew-02", 150.0, T0)

    radiation = _radiation(client)
    readings = radiation["dose_rate"]["readings"]
    # La cifra del registro, tal cual: sin factor de blindaje ni reparto por módulo.
    assert [(item["subject"], item["value"]) for item in readings] == [
        ("crew-01", 14.3), ("crew-02", 150.0),
    ]
    assert readings[0]["source"] == "dosimeter-a"
    assert readings[0]["effective"] == (T0 + dt.timedelta(hours=1)).isoformat()
    assert readings[0]["unit"] == "uGy/h" and readings[0]["decimals"] == 1
    assert "crew-01" in readings[0]["origin_text"] and "dosimeter-a" in readings[0]["origin_text"]
    assert all(item["module"] is None for item in readings)
    assert radiation["module"] is None
    assert radiation["module_text"].startswith("módulo sin declarar")
    assert radiation["shielding"].startswith("Sin factores de blindaje")
    assert radiation["evaluated"] is False
    assert radiation["dose_rate"]["missing_text"] is None
    assert "crew-01 14,3 µGy/h; crew-02 150,0 µGy/h" in radiation["summary"]


def test_the_last_reading_is_the_one_the_state_reads_not_one_with_a_broken_clock(
    client: TestClient,
) -> None:
    # Como en el estado, el «ahora» de cada tripulante sale de TODAS sus lecturas: una tasa de
    # dosis suelta fechada en 2099 queda después de su referencia y no es la última.
    for hour in range(6):
        response = client.post("/api/observations", json={
            "key": "heart-rate", "value": 60.0, "subject": "crew-01",
            "effective": (T0 + dt.timedelta(hours=hour)).isoformat(),
        })
        assert response.status_code == 201, response.text
    _dose(client, "crew-01", 12.0, T0 + dt.timedelta(hours=2))
    _dose(client, "crew-01", 999.0, dt.datetime(2099, 1, 1, tzinfo=dt.UTC))

    [reading] = _radiation(client)["dose_rate"]["readings"]
    assert reading["value"] == 12.0


def test_the_ground_sees_only_the_readings_that_reached_it(client: TestClient) -> None:
    _dose(client, "crew-01", 10.0, T0)
    _dose(client, "crew-01", 14.0, T0 + dt.timedelta(hours=2))
    _dose(client, "crew-02", 150.0, T0 + dt.timedelta(hours=3))

    cut = _radiation(client, until=(T0 + dt.timedelta(hours=1)).isoformat())
    assert [(item["subject"], item["value"]) for item in cut["dose_rate"]["readings"]] == [
        ("crew-01", 10.0),
    ]


def test_without_readings_or_donki_it_says_what_is_missing(client: TestClient) -> None:
    radiation = _radiation(client)
    assert radiation["dose_rate"]["readings"] == []
    assert radiation["dose_rate"]["missing_text"] == habitat.DOSE_RATE_MISSING
    solar = radiation["solar_event"]
    # Modo sin red y sin caché: no se sabe, y no se dice que no haya evento.
    assert solar["state"] == habitat.SOLAR_UNKNOWN
    assert solar["text"] == habitat.SOLAR_UNAVAILABLE
    assert solar["event"] is None and solar["data_age"] is None
    assert solar["freshness"]["state"] == "missing"


def test_the_solar_event_is_the_one_the_state_chooses_with_its_date_and_source(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    events = [
        _event("SEP-ANTES", EventType.SEP, SolarSeverity.HIGH, now - dt.timedelta(days=2)),
        _event("SEP-HOY", EventType.SEP, SolarSeverity.HIGH, now - dt.timedelta(hours=5)),
        # Más reciente, pero de severidad que el motor no cuenta: no es el vigente.
        _event("CME-LUEGO", EventType.CME, SolarSeverity.ELEVATED, now - dt.timedelta(hours=1)),
    ]
    monkeypatch.setattr(
        routes, "_fetch_solar_events", lambda settings: (events, ("hace 4 min", 240))
    )
    _dose(client, "crew-01", 12.0, T0)

    solar = _radiation(client)["solar_event"]
    status = client.get("/api/status", params={"subject": "crew-01"}).json()
    assert solar["state"] == habitat.SOLAR_ACTIVE
    assert solar["event"] == status["active_solar_event"]
    assert solar["event"]["event_id"] == "SEP-HOY"
    stamp = (now - dt.timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")
    assert solar["text"] == f"SEP SEP-HOY, del {stamp} UTC, según NASA DONKI."
    assert solar["source"] == habitat.SOLAR_SOURCE
    assert solar["data_age"] == "hace 4 min" and solar["freshness"]["state"] == "fresh"


def test_without_a_relevant_event_it_says_none_in_the_window_of_the_state(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "_fetch_solar_events", lambda settings: ([], ("hace 1 h", 3600)))
    solar = _radiation(client)["solar_event"]
    assert solar["state"] == habitat.SOLAR_NONE and solar["event"] is None
    assert "últimos 3 días" in solar["text"] and "últimos 3 días" in solar["basis"]


def test_radiation_is_never_a_habitat_excursion_and_decides_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.post("/api/simulate", params={"scenario": "spe-event", "days": 30, "crew_size": 2})
    event = _event("SEP-HOY", EventType.SEP, SolarSeverity.SEVERE, dt.datetime.now(dt.UTC))
    monkeypatch.setattr(routes, "_fetch_solar_events", lambda settings: ([event], ("ahora", 0)))
    before = _verdict(client)
    size = len(get_store().ledger)

    body = client.get("/api/habitat").json()
    assert body["radiation"]["solar_event"]["state"] == habitat.SOLAR_ACTIVE
    assert body["radiation"]["dose_rate"]["readings"]
    # Nada de radiación entra en las excursiones de cabina ni en las vigentes.
    for item in (*body["excursions"], *body["active"]):
        assert item["parameter"] != habitat.DOSE_RATE_KEY
    assert habitat.DOSE_RATE_KEY not in habitat.PARAMETERS
    assert habitat.DOSE_RATE_KEY not in habitat.DISPLAY_ONLY

    client.get("/api/twins", params={"subject": "crew-01"})
    assert len(get_store().ledger) == size, "enseñar la radiación no firma nada"
    assert _verdict(client) == before


def test_the_habitat_twin_carries_the_radiation_as_a_note_not_an_answer(
    client: TestClient,
) -> None:
    _dose(client, "crew-01", 12.0, T0)
    body = client.get("/api/twins", params={"subject": "crew-01"}).json()
    layer = next(item for item in body["questions"] if item["key"] == "habitat")
    summary = _radiation(client)["summary"]
    assert summary in layer["notes"]
    assert twins.RADIATION_SOURCE in layer["sources"]


def test_the_twin_note_names_the_event_of_its_own_state_without_asking_donki_again(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # La primera consulta (la del estado) ve un evento; cualquier otra posterior, otro. La nota
    # del gemelo tiene que nombrar el del estado que la acompaña.
    now = dt.datetime.now(dt.UTC)
    first = _event("SEP-ESTADO", EventType.SEP, SolarSeverity.HIGH, now - dt.timedelta(hours=2))
    later = _event("SEP-OTRA", EventType.SEP, SolarSeverity.HIGH, now - dt.timedelta(hours=1))
    calls: list[int] = []

    def fetch(settings: Any) -> tuple[list[SolarEvent], tuple[str, int]]:
        calls.append(1)
        return ([first] if len(calls) == 1 else [later]), ("ahora", 0)

    monkeypatch.setattr(routes, "_fetch_solar_events", fetch)
    _dose(client, "crew-01", 12.0, T0)
    body = client.get("/api/twins", params={"subject": "crew-01"}).json()
    layer = next(item for item in body["questions"] if item["key"] == "habitat")
    [note] = [note for note in layer["notes"] if habitat.SOLAR_DISPLAY in note]
    assert "SEP-ESTADO" in note and "SEP-OTRA" not in note


def test_for_the_ground_the_twin_note_is_cut_where_its_state_is(client: TestClient) -> None:
    _dose(client, "crew-01", 10.0, T0)
    _dose(client, "crew-01", 14.0, T0 + dt.timedelta(hours=2))
    cut = (T0 + dt.timedelta(hours=1)).isoformat()
    body = client.get("/api/twins", params={"subject": "crew-01", "until": cut}).json()
    layer = next(item for item in body["questions"] if item["key"] == "habitat")
    assert _radiation(client, until=cut)["summary"] in layer["notes"]
    assert any("crew-01 10,0 µGy/h" in note for note in layer["notes"])


def test_the_note_does_not_change_the_state_of_the_habitat_answer() -> None:
    status = {"subject": "crew-01", "alerts": []}
    crew = {"correlation": {"affected": [], "hypotheses": []}}
    plain = twins.habitat(status, crew)
    noted = twins.habitat(status, crew, {"summary": "Radiación de prueba."})
    assert noted["state"] == plain["state"] and noted["items"] == plain["items"]
    assert noted["notes"] == [*plain["notes"], "Radiación de prueba."]
    assert twins.habitat(status, None, {"summary": "R."})["notes"] == ["R."]


def test_nothing_written_here_sounds_like_an_order() -> None:
    texts = [
        habitat.RADIATION_MODULE_TEXT, habitat.RADIATION_NO_SHIELDING,
        habitat.RADIATION_NOT_EVALUATED, habitat.DOSE_RATE_BASIS, habitat.DOSE_RATE_MISSING,
        habitat.SOLAR_UNAVAILABLE, habitat.SOLAR_SOURCE, habitat.SOLAR_DISPLAY,
        habitat.DOSE_RATE_DISPLAY, twins.RADIATION_SOURCE,
    ]
    for text in texts:
        # «dosis» es aquí de radiación, no de un fármaco (como en test_radiation_read.py).
        found = [
            finding for finding in check(text)
            if (finding.category, finding.match.lower()) != ("dosing", "dosis")
        ]
        assert found == [], text
