"""Cambio de turno o de horario de sueño como evento de misión (decimoctava ronda, U4).

Qué fijan estas pruebas:
- que `shift` es un cuarto tipo del asiento `mission-event`, firmado por la consola, con los
  mismos campos que una EVA y sin módulo;
- que los asientos escritos con el vocabulario anterior siguen verificando y leyéndose igual, y
  que el vocabulario no se usa al leer;
- que entra en el contexto de una alerta del dominio conductual como coincidencia en el tiempo,
  con lo que dice la fuente leída y lo que no;
- y que no mueve ningún nivel ni la versión de reglas (invariante 5).
"""

import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis.alert_context import LABEL, around
from app.api.routes import get_store
from app.core import shift as shift_event
from app.core import storage
from app.core.ledger import Identity
from app.core.storage import MISSION_EVENT_KINDS, SHIFT_EVENT_KIND, ObservationStore
from app.evidence import registry
from app.text_guard import check

T0 = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.UTC)
OLD_KINDS = ("eva", "workload", "location")
SHIFT_TITLE = "Cambio de turno o de horario de sueño declarado"


def _h(hours: float) -> dt.datetime:
    return T0 + dt.timedelta(hours=hours)


def _event(kind: str, start: float, end: float, label: str, index: int = 7) -> dict[str, Any]:
    return {
        "kind": kind, "start": _h(start).isoformat(), "end": _h(end).isoformat(),
        "label": label, "declared_by": "CDR", "ledger_index": index,
    }


def _context(events: list[dict[str, Any]]) -> dict[str, Any]:
    return around(
        onset=T0, reference=_h(30), habitat_readings=[], habitat_excursions=[],
        mission_events=events, solar=None, adoptions=[], mission_start=dt.date(2026, 11, 1),
        mission_days=180, gravity_regime="microgravedad",
    )


def _mission_source(context: dict[str, Any]) -> dict[str, Any]:
    [source] = [item for item in context["sources"] if item["kind"] == "mission_event"]
    return source


# --------------------------------------------------------------------------- #
# El asiento
# --------------------------------------------------------------------------- #

def test_a_shift_is_a_fourth_kind_of_the_same_entry_and_the_old_ones_stay() -> None:
    assert SHIFT_EVENT_KIND == shift_event.KIND == "shift"
    assert MISSION_EVENT_KINDS[:-1] == OLD_KINDS
    assert MISSION_EVENT_KINDS[-1] == "shift"


def test_a_shift_is_signed_with_the_fields_of_an_eva_and_without_a_module() -> None:
    store = ObservationStore.in_memory()
    console = Identity.generate("crew-console")
    entry = store.record_mission_event(
        "crew-01", "shift", _h(-10), _h(14), "Dormir 6 h antes por el atraque", "CDR", console,
    )
    assert entry.entry_type == "mission-event" and entry.signer == "crew-console"
    assert {k: v for k, v in entry.payload.items() if k != "_salt"} == {
        "subject": "crew-01", "kind": "shift", "start": _h(-10).isoformat(),
        "end": _h(14).isoformat(), "label": "Dormir 6 h antes por el atraque",
        "declared_by": "CDR",
    }
    assert store.verify_integrity().ok
    with pytest.raises(ValueError, match="solo una declaración de ubicación lleva módulo"):
        store.record_mission_event(
            "crew-01", "shift", _h(0), _h(1), "x", "CDR", console, module="laboratorio"
        )
    with pytest.raises(ValueError, match="terminar después de empezar"):
        store.record_mission_event("crew-01", "shift", _h(1), _h(1), "x", "CDR", console)
    assert len(store.ledger) == 1


def test_entries_written_with_the_old_vocabulary_still_verify_and_read_the_same(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "emma.db"
    console = Identity.generate("crew-console")
    # El ledger de antes de este cambio: solo los tres tipos de entonces.
    monkeypatch.setattr(storage, "MISSION_EVENT_KINDS", OLD_KINDS)
    first = ObservationStore.at(db)
    first.record_mission_event("crew-01", "eva", _h(-20), _h(-14), "EVA 3", "CDR", console)
    first.record_mission_event("crew-01", "workload", _h(-8), _h(-2), "Mantenimiento", "CDR",
                               console)
    first.record_mission_event("crew-01", "location", _h(-30), _h(10), "Lab", "CDR", console,
                               module="laboratorio")
    with pytest.raises(ValueError, match="desconocido"):
        first.record_mission_event("crew-01", "shift", _h(0), _h(1), "x", "CDR", console)
    before = [
        {k: v for k, v in entry.payload.items() if k != "_salt"} for entry in first.ledger.entries
    ]
    root = first.merkle_root()
    monkeypatch.undo()

    # Con el vocabulario nuevo, la misma cadena verifica y se lee igual, y admite el turno.
    reopened = ObservationStore.at(db)
    assert reopened.verify_integrity().ok
    assert reopened.merkle_root() == root
    assert [
        {k: v for k, v in entry.payload.items() if k != "_salt"}
        for entry in reopened.ledger.entries
    ] == before
    reopened.record_mission_event("crew-01", "shift", _h(-12), _h(12), "Turno de noche", "CDR",
                                  console)
    assert reopened.verify_integrity().ok
    assert [item["kind"] for item in reopened.mission_events("crew-01")] == [
        "eva", "workload", "location", "shift"
    ]

    # Y al revés: leer no usa el vocabulario. Un asiento `shift` se entrega aunque quien lo lea
    # no conozca el tipo (la lista de la alerta lo nombra de forma genérica).
    monkeypatch.setattr(storage, "MISSION_EVENT_KINDS", OLD_KINDS)
    older = ObservationStore.at(db)
    assert older.verify_integrity().ok
    assert [item["kind"] for item in older.mission_events("crew-01")][-1] == "shift"


def test_the_api_signs_a_shift_and_asks_for_a_description(client: TestClient) -> None:
    client.post("/api/simulate", params={"days": 10})
    start = dt.datetime(2026, 11, 6, tzinfo=dt.UTC)
    body = {
        "kind": "shift", "start": start.isoformat(),
        "end": (start + dt.timedelta(hours=30)).isoformat(), "declared_by": "CDR",
    }
    assert client.post("/api/mission/events", json=body).status_code == 422
    assert client.post(
        "/api/mission/events", json={**body, "label": "x", "module": "laboratorio"}
    ).status_code == 422
    response = client.post("/api/mission/events", json={**body, "label": "Turno de noche"})
    assert response.status_code == 201, response.text
    [event] = client.get("/api/status").json()["mission"]["events"]
    assert (event["kind"], event["label"], event["declared_by"]) == (
        "shift", "Turno de noche", "CDR"
    )
    assert "module" not in event
    assert get_store().verify_integrity().ok
    # En la crónica, con su nombre en español.
    chronicle = client.get("/api/timeline/chronicle").json()
    said = {
        item["fact"]: item["que"] for item in chronicle["events"]
        if item["fact"].startswith("mission-event-")
    }
    assert said == {
        "mission-event-declared": "cambio de turno o de horario de sueño declarado: Turno de noche",
        "mission-event-start": "cambio de turno o de horario de sueño: Turno de noche, inicio",
        "mission-event-end": "cambio de turno o de horario de sueño: Turno de noche, fin",
    }


def test_the_basis_says_how_a_shift_differs_from_a_work_block_and_cites_what_was_read(
    client: TestClient,
) -> None:
    basis = client.get("/api/mission/shift").json()
    assert basis == shift_event.describe()
    assert basis["kind"] == "shift"
    assert "bloque de trabajo" in basis["distinction"]
    assert basis["source"]["id"] == shift_event.SOURCE_REF
    registry.get(shift_event.SOURCE_REF)
    # La frase citada está escrita en la ficha leída, tal cual.
    notes = registry.get(shift_event.SOURCE_REF).notes or ""
    assert "These abrupt shifts in the imposed sleep–wake schedule can induce circadian " \
        "misalignment" in notes
    assert "These abrupt shifts in the imposed sleep–wake schedule" in basis["source_says"]
    for text in (basis["display"], basis["distinction"], basis["source_says"]):
        assert check(text) == [], text


# --------------------------------------------------------------------------- #
# El contexto de una alerta
# --------------------------------------------------------------------------- #

def test_a_shift_in_the_window_is_listed_as_a_coincidence_with_what_the_source_says() -> None:
    context = _context([
        _event("shift", -18, 6, "Dormir 6 h antes por el atraque"),
        _event("shift", -200, -150, "Turno de hace una semana", index=3),
    ])
    [item] = [entry for entry in context["items"] if entry["kind"] == "mission_event"]
    assert (item["title"], item["detail"], item["label"]) == (
        SHIFT_TITLE, "Dormir 6 h antes por el atraque", LABEL
    )
    assert item["timing"] == "en curso en el inicio de la alerta; empezó 18,0 h antes"
    assert item["source"] == "declarado por CDR, asiento 7"
    source = _mission_source(context)
    assert (source["status"], source["found"]) == ("with_data", 1)
    assert source["note"].endswith(shift_event.SOURCE_SAYS)
    for text in (item["title"], item["timing"], source["note"]):
        assert check(text) == [], text


def test_without_a_shift_in_the_window_the_note_does_not_speak_of_one() -> None:
    eva_only = _mission_source(_context([_event("eva", -10, -4, "EVA 3")]))
    assert shift_event.SOURCE_SAYS not in eva_only["note"]
    assert "cambios de turno" in eva_only["note"]
    outside = _mission_source(_context([_event("shift", -200, -150, "Turno viejo")]))
    assert (outside["found"], shift_event.SOURCE_SAYS in outside["note"]) == (0, False)
    nothing = _mission_source(_context([]))
    assert nothing["status"] == "no_data" and "cambio de turno" in nothing["note"]


# --------------------------------------------------------------------------- #
# De punta a punta: una alerta de sueño, un turno, y ni un nivel movido
# --------------------------------------------------------------------------- #

def _verdict(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "overall": status["overall_level"],
        "domains": {
            key: (value["score"], value["level"], value["drivers"])
            for key, value in status["domains"].items()
        },
        "alerts": [
            (alert["id"], alert["level"], alert["detail"]["onset"], alert["rules_version"])
            for alert in status["alerts"]
        ],
        "recommendations": [
            (item["domain"], item["action"]) for item in status["recommendations"]
        ],
    }


def test_a_declared_shift_enters_a_sleep_alert_without_moving_a_level(
    client: TestClient,
) -> None:
    client.post(
        "/api/simulate",
        params={"scenario": "progressive-insomnia", "days": 14, "crew_size": 1},
    )
    plain = client.get("/api/status").json()
    [alert] = [item for item in plain["alerts"] if item["domain"] == "behavioral"]
    onset = dt.datetime.fromisoformat(alert["detail"]["onset"])
    rules = client.get("/api/status").json()["rules_version"]

    assert client.post("/api/mission/events", json={
        "kind": "shift", "start": (onset - dt.timedelta(hours=20)).isoformat(),
        "end": (onset - dt.timedelta(hours=2)).isoformat(),
        "label": "Sueño adelantado 6 h por el atraque", "declared_by": "CDR",
    }).status_code == 201
    richer = client.get("/api/status").json()
    [after] = [item for item in richer["alerts"] if item["domain"] == "behavioral"]
    [listed] = [
        item for item in after["detail"]["context"]["items"] if item["kind"] == "mission_event"
    ]
    assert (listed["title"], listed["detail"], listed["label"]) == (
        SHIFT_TITLE, "Sueño adelantado 6 h por el atraque", LABEL
    )
    assert _verdict(richer) == _verdict(plain)
    assert richer["rules_version"] == rules
    assert get_store().verify_integrity().ok
