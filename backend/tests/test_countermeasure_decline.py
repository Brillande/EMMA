"""Decir «no» a una contramedida, con motivo y firmado (especificación §2, §14).

La consola dejaba adoptar o cerrar, y la decisión de NO actuar no dejaba rastro. Estas pruebas
fijan lo que esa tercera acción es y, sobre todo, lo que no es: un registro de una decisión
humana que no cierra ni silencia nada, no mueve ningún nivel (invariante 5) y no retira la
recomendación. Va por el ledger, en el asiento de siempre, y los asientos firmados antes del
cambio siguen verificándose (invariante 4).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.advisor import countermeasures
from app.advisor.countermeasures import CONTRAINDICATIONS_PENDING, LibraryError, load
from app.advisor.followup import (
    ACTIONS,
    DECLINE_MEANING,
    DECLINED,
    decision_note,
    followups,
    open_adoption,
    standing_declines,
    with_decisions,
)
from app.core.ledger import Identity
from app.core.storage import _FOLLOWUP_FIELDS, FOLLOWUP_ENTRY_TYPE, ObservationStore
from app.core.versioning import decided_with, rules_version

NOW = dt.datetime(2026, 12, 10, 12, 0, tzinfo=dt.UTC)
REASON = "ya duerme siete horas; el turno no admite el recorte esta semana"
# Ledger con una adopción y su cierre, escrito con el código ANTERIOR a este cambio (commit
# 9292ada) y guardado tal cual. Los hashes de contenido son los que firmó aquel código.
PRE_CHANGE_LEDGER = Path(__file__).parent / "data" / "followup_pre_decline.db"
PRE_CHANGE_HASHES = [
    "c50864a6a62bb77e95bd6d79a0c88ff2c8c9228fd6dd9012be3f99f81be77f2b",
    "0aab328e7274c3305f499e18ed2c600ecf3ddc3302f3ae8b2fa78b9221cbaeca",
]


def _decision(index: int, action: str, ident: str = "bh-protect-sleep", **extra: str) -> dict:
    return {
        "ledger_index": index, "action": action, "countermeasure_id": ident,
        "domain": "behavioral", "level": "concern", "reference_time": NOW.isoformat(),
        "decided_by": "CDR", "reason": "", "adoption_index": "", **extra,
    }


# --------------------------------------------------------------------------- #
# Lógica pura: qué «no» sigue en pie
# --------------------------------------------------------------------------- #


def test_declining_is_a_third_action_of_the_same_followup() -> None:
    assert ACTIONS == ("adopted", "closed", "declined")


def test_a_decline_stands_until_the_same_countermeasure_is_adopted() -> None:
    no = _decision(3, DECLINED, reason=REASON)
    assert standing_declines([no]) == {"bh-protect-sleep": no}
    # Adoptar otra contramedida no dice nada de esta.
    assert standing_declines([no, _decision(4, "adopted", "bh-repeat-pvt")]) == {
        "bh-protect-sleep": no
    }
    # Cambiar de opinión, sí: el «no» deja de estar en pie.
    assert standing_declines([no, _decision(5, "adopted")]) == {}


def test_the_last_decline_wins_and_order_is_the_ledger_not_the_list() -> None:
    first = _decision(3, DECLINED, reason="primer motivo")
    second = _decision(8, DECLINED, reason="segundo motivo")
    assert standing_declines([second, first])["bh-protect-sleep"]["reason"] == "segundo motivo"
    # Un «no» posterior a una adopción vuelve a estar en pie.
    assert standing_declines([second, _decision(5, "adopted"), first]) == {
        "bh-protect-sleep": second
    }


def test_closing_a_followup_does_not_lift_a_decline() -> None:
    no = _decision(9, DECLINED, reason=REASON)
    closure = _decision(7, "closed", adoption_index="5", reason="hecho")
    assert standing_declines([_decision(5, "adopted"), closure, no]) == {"bh-protect-sleep": no}


def test_an_open_adoption_is_one_without_its_closure() -> None:
    adoption = _decision(5, "adopted")
    assert open_adoption([adoption], "bh-protect-sleep") == adoption
    assert open_adoption([adoption], "bh-repeat-pvt") is None
    closure = _decision(7, "closed", adoption_index="5", reason="hecho")
    assert open_adoption([adoption, closure], "bh-protect-sleep") is None
    # El cierre de OTRA adopción no cierra esta.
    other = _decision(8, "closed", adoption_index="6", reason="hecho")
    assert open_adoption([adoption, other], "bh-protect-sleep") == adoption


def test_the_note_is_a_record_with_date_author_and_reason_never_an_order() -> None:
    note = decision_note(_decision(3, DECLINED, reason=REASON))
    assert note["text"] == f"Se decidió no adoptarla el 2026-12-10 12:00 UTC (CDR): {REASON}"
    assert note["meaning"] == DECLINE_MEANING
    assert (note["action"], note["ledger_index"], note["decided_by"], note["reason"]) == (
        "declined", 3, "CDR", REASON)
    assert note["decided_at"] == NOW.isoformat()
    for word in ("debe", "hay que", "obligatori"):
        assert word not in (note["text"] + note["meaning"]).lower().replace(REASON, "")


def test_annotating_only_adds_a_field() -> None:
    recommendations = [
        {"domain": "behavioral", "action": "a", "countermeasure": {"id": "bh-protect-sleep"}},
        {"domain": "behavioral", "action": "b", "countermeasure": {"id": "bh-repeat-pvt"}},
        {"domain": "radiation", "action": "c", "countermeasure": None},
    ]
    annotated = with_decisions(recommendations, [_decision(3, DECLINED, reason=REASON)])
    # Las mismas, en el mismo orden y con el mismo contenido: decir que no no retira nada.
    assert [
        {key: value for key, value in item.items() if key != "decision"} for item in annotated
    ] == recommendations
    assert annotated[0]["decision"]["reason"] == REASON
    assert annotated[1]["decision"] is None and annotated[2]["decision"] is None
    assert all(item["decision"] is None for item in with_decisions(recommendations, []))


def test_a_decline_opens_no_followup() -> None:
    assert followups([_decision(3, DECLINED, reason=REASON)], {}, [], NOW) == []


# --------------------------------------------------------------------------- #
# Ledger: el asiento de siempre, y lo ya firmado sigue verificándose
# --------------------------------------------------------------------------- #


def test_the_store_refuses_a_decline_without_reason_or_pointing_to_an_adoption() -> None:
    store = ObservationStore.in_memory()
    console = Identity.generate("crew-console")
    args = ("crew-01", "declined", "bh-protect-sleep", "behavioral", "concern", NOW, "CDR")
    with pytest.raises(ValueError, match="motivo"):
        store.record_followup(*args, console, reason="   ")
    with pytest.raises(ValueError, match="no apunta"):
        store.record_followup(*args, console, reason=REASON, adoption_index=0)
    with pytest.raises(ValueError, match="desconocida"):
        store.record_followup("crew-01", "ignored", *args[2:], console, reason=REASON)
    assert store.followup_decisions("crew-01") == []


def test_a_decline_is_the_same_entry_type_with_the_same_fields() -> None:
    store = ObservationStore.in_memory()
    console = Identity.generate("crew-console")
    entry = store.record_followup(
        "crew-01", "declined", "bh-protect-sleep", "behavioral", "concern", NOW, "CDR", console,
        reason=REASON,
    )
    assert entry.entry_type == FOLLOWUP_ENTRY_TYPE == "countermeasure-followup"
    assert entry.signer == "crew-console"
    # Ni un campo más ni uno menos que una adopción (salvo la sal del asiento).
    assert {key for key in entry.payload if not key.startswith("_")} == set(_FOLLOWUP_FIELDS)
    assert (entry.payload["action"], entry.payload["reason"]) == ("declined", REASON)
    assert entry.payload["adoption_index"] == ""
    assert store.verify_integrity().ok


def test_a_ledger_signed_before_the_change_still_verifies_and_accepts_a_decline(
    tmp_path: Path,
) -> None:
    path = tmp_path / "emma.db"
    shutil.copyfile(PRE_CHANGE_LEDGER, path)
    store = ObservationStore.at(path)

    assert store.verify_integrity().ok
    old = store.followup_decisions("crew-01")
    assert [item["action"] for item in old] == ["adopted", "closed"]
    assert [entry["content_hash"] for entry in store.audit_trail()] == PRE_CHANGE_HASHES
    # Y se leen como antes: una adopción cerrada, sin ningún «no» en pie.
    [follow] = followups(old, {}, [], NOW)
    assert follow["state"] == "closed" and follow["closed_reason"] == "sueño recuperado"
    assert standing_declines(old) == {}

    store.record_followup(
        "crew-01", "declined", "bh-protect-sleep", "behavioral", "concern", NOW, "CDR",
        Identity.generate("otra-consola"), reason=REASON,
    )
    assert store.verify_integrity().ok
    store.engine.dispose()

    reopened = ObservationStore.at(path)
    assert reopened.verify_integrity().ok
    assert [entry["content_hash"] for entry in reopened.audit_trail()][:2] == PRE_CHANGE_HASHES
    assert [item["action"] for item in reopened.followup_decisions("crew-01")] == [
        "adopted", "closed", "declined"]
    reopened.engine.dispose()


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


@pytest.fixture
def insomnia(client: TestClient) -> dict[str, Any]:
    assert client.post(
        "/api/simulate", params={"scenario": "progressive-insomnia", "days": 40}
    ).status_code == 201
    status: dict[str, Any] = client.get("/api/status").json()
    return status


def _verdict(status: dict[str, Any]) -> tuple[Any, ...]:
    """Lo que decide el motor: niveles, puntuaciones y alertas enteras."""
    return (
        status["overall_level"],
        {key: (item["level"], item["score"], item["drivers"])
         for key, item in status["domains"].items()},
        status["alerts"],
        status["followups"],
    )


def _decline(client: TestClient, status: dict[str, Any], ident: str, reason: str = REASON) -> Any:
    return client.post("/api/countermeasures/decline", json={
        "countermeasure_id": ident, "reference_time": status["data"]["reference_time"],
        "reason": reason, "declined_by": "CDR",
    })


def _plain(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in item.items() if key != "decision"}
        for item in recommendations
    ]


def test_declining_is_signed_and_changes_no_level_alert_or_recommendation(
    client: TestClient, insomnia: dict[str, Any]
) -> None:
    assert insomnia["alerts"], "el escenario tiene que tener una alerta que no se pueda cerrar"
    assert all(item["decision"] is None for item in insomnia["recommendations"])
    chosen = insomnia["recommendations"][0]["countermeasure"]["id"]
    before = client.get("/api/audit").json()["total_entries"]

    response = _decline(client, insomnia, chosen, f"  {REASON}  ")
    assert response.status_code == 201, response.text
    index = response.json()["ledger_index"]

    audit = client.get("/api/audit", params={"limit": 1}).json()
    assert audit["integrity_ok"] and audit["total_entries"] == before + 1
    [entry] = audit["entries"]
    assert (entry["index"], entry["entry_type"], entry["signer"]) == (
        index, "countermeasure-followup", "crew-console")

    after = client.get("/api/status").json()
    # Invariante 5: el veredicto del motor es idéntico con y sin la decisión.
    assert _verdict(after) == _verdict(insomnia)
    # La recomendación sigue saliendo, la misma y en su sitio, ahora con la nota al lado.
    assert _plain(after["recommendations"]) == _plain(insomnia["recommendations"])
    first, *rest = after["recommendations"]
    assert first["countermeasure"]["id"] == chosen
    assert first["decision"]["ledger_index"] == index
    assert first["decision"]["reason"] == REASON  # sin los espacios de alrededor
    assert first["decision"]["text"].startswith("Se decidió no adoptarla el ")
    assert first["decision"]["text"].endswith(f"(CDR): {REASON}")
    assert all(
        item["decision"] is None for item in rest if item["countermeasure"]["id"] != chosen
    )


@pytest.mark.parametrize("reason", ["", "   ", "\n\t"])
def test_a_decline_without_reason_is_a_422_that_says_so(
    client: TestClient, insomnia: dict[str, Any], reason: str
) -> None:
    chosen = insomnia["recommendations"][0]["countermeasure"]["id"]
    before = client.get("/api/audit").json()["total_entries"]
    response = _decline(client, insomnia, chosen, reason)
    assert response.status_code == 422
    assert "el motivo no puede ir vacío" in response.text
    assert client.get("/api/audit").json()["total_entries"] == before


def test_an_unknown_countermeasure_is_a_422_that_says_so(
    client: TestClient, insomnia: dict[str, Any]
) -> None:
    response = _decline(client, insomnia, "no-existe")
    assert response.status_code == 422
    assert "contramedida desconocida" in response.json()["detail"]
    assert client.get("/api/countermeasures/decisions").json()["decisions"] == []


def test_what_is_adopted_and_open_cannot_be_declined_until_it_is_closed(
    client: TestClient, insomnia: dict[str, Any]
) -> None:
    chosen = insomnia["recommendations"][0]["countermeasure"]["id"]
    reference = insomnia["data"]["reference_time"]
    adopted = client.post("/api/countermeasures/adopt", json={
        "countermeasure_id": chosen, "reference_time": reference, "adopted_by": "CDR",
    }).json()["ledger_index"]

    refused = _decline(client, insomnia, chosen)
    assert refused.status_code == 422
    detail = refused.json()["detail"]
    assert "está adoptada y con el seguimiento abierto" in detail
    assert f"asiento {adopted}" in detail
    assert client.get("/api/status").json()["recommendations"][0]["decision"] is None

    # Otra contramedida, sin adoptar, sí admite el «no».
    other = insomnia["recommendations"][1]["countermeasure"]["id"]
    assert other != chosen
    assert _decline(client, insomnia, other).status_code == 201

    # Y cerrado el seguimiento, esta también.
    assert client.post("/api/countermeasures/close", json={
        "adoption_index": adopted, "reason": "no se pudo mantener", "closed_by": "CDR",
    }).status_code == 201
    assert _decline(client, insomnia, chosen).status_code == 201
    status = client.get("/api/status").json()
    assert status["recommendations"][0]["decision"]["reason"] == REASON
    assert [item["state"] for item in status["followups"]] == ["closed"]


def test_what_was_not_recommended_cannot_be_declined(
    client: TestClient, insomnia: dict[str, Any]
) -> None:
    response = _decline(client, insomnia, countermeasures.SHELTER_ID)
    assert response.status_code == 409
    assert "no estaba recomendada" in response.json()["detail"]


def test_people_change_their_mind_and_that_is_signed_too(
    client: TestClient, insomnia: dict[str, Any]
) -> None:
    chosen = insomnia["recommendations"][0]["countermeasure"]["id"]
    reference = insomnia["data"]["reference_time"]
    declined = _decline(client, insomnia, chosen).json()["ledger_index"]

    adopted = client.post("/api/countermeasures/adopt", json={
        "countermeasure_id": chosen, "reference_time": reference, "adopted_by": "CMO",
    })
    assert adopted.status_code == 201, adopted.text

    status = client.get("/api/status").json()
    assert status["recommendations"][0]["decision"] is None
    [follow] = status["followups"]
    assert (follow["countermeasure"]["id"], follow["adopted_by"]) == (chosen, "CMO")
    # Las dos decisiones siguen firmadas, en su orden: nada se borra al cambiar de opinión.
    listing = client.get("/api/countermeasures/decisions").json()
    assert [(item["ledger_index"], item["action"]) for item in listing["decisions"]] == [
        (declined, "declined"), (adopted.json()["ledger_index"], "adopted")]
    assert listing["declined"] == {}
    assert client.get("/api/audit").json()["integrity_ok"]


def test_what_was_decided_can_be_read_back(client: TestClient, insomnia: dict[str, Any]) -> None:
    chosen = insomnia["recommendations"][0]["countermeasure"]["id"]
    index = _decline(client, insomnia, chosen).json()["ledger_index"]
    listing = client.get("/api/countermeasures/decisions", params={"subject": "crew-01"}).json()
    [decision] = listing["decisions"]
    assert (decision["action"], decision["reason"], decision["decided_by"]) == (
        "declined", REASON, "CDR")
    assert "signer" not in decision
    assert listing["declined"][chosen]["ledger_index"] == index
    assert listing["declined_meaning"] == DECLINE_MEANING
    # De otro tripulante no hay nada decidido.
    assert client.get(
        "/api/countermeasures/decisions", params={"subject": "crew-02"}
    ).json()["decisions"] == []


def test_a_decline_signed_by_another_source_does_not_count(
    client: TestClient, insomnia: dict[str, Any]
) -> None:
    from app.api.routes import get_store

    chosen = insomnia["recommendations"][0]["countermeasure"]["id"]
    get_store().record_followup(
        "crew-01", "declined", chosen, "behavioral", "concern", NOW, "CDR",
        Identity.generate("wearable-01"), reason=REASON,
    )
    assert client.get("/api/status").json()["recommendations"][0]["decision"] is None
    assert client.get("/api/countermeasures/decisions").json()["decisions"] == []


def test_the_chronicle_tells_the_decision_as_it_tells_adoptions(
    client: TestClient, insomnia: dict[str, Any]
) -> None:
    chosen = insomnia["recommendations"][0]["countermeasure"]["id"]
    index = _decline(client, insomnia, chosen).json()["ledger_index"]
    events = client.get("/api/timeline/chronicle").json()["events"]
    [told] = [event for event in events if event["fact"] == "countermeasure-declined"]
    assert told["que"] == f"contramedida {chosen}: se decidió no adoptarla; motivo: {REASON}"
    # La fuente dice además con qué reglas se firmó (`record-integrity.md` §3.26).
    assert (told["quien"], told["fuente"], told["tipo"]) == (
        "CDR", f"asiento {index}; {decided_with(rules_version())['text']}", "contramedida")
    assert told["stage"] == "intervention"
    assert told["at"] == dt.datetime.fromisoformat(
        insomnia["data"]["reference_time"]).astimezone(dt.UTC).isoformat()
    # No se cuenta como un cierre ni como una adopción.
    assert not [
        event for event in events
        if event["fact"] in ("countermeasure-closed", "countermeasure-adopted")
    ]


def test_the_reason_never_reaches_a_log(
    client: TestClient, insomnia: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    secret = "motivo-privado-de-quien-decide-7f3a"
    chosen = insomnia["recommendations"][0]["countermeasure"]["id"]
    with caplog.at_level(logging.DEBUG):
        assert _decline(client, insomnia, chosen, secret).status_code == 201
        client.get("/api/status")
        client.get("/api/timeline/chronicle")
        client.get("/api/countermeasures/decisions")
        # Los rechazos tampoco lo escriben.
        assert _decline(client, insomnia, "no-existe", secret).status_code == 422
        assert _decline(client, insomnia, countermeasures.SHELTER_ID, secret).status_code == 409
    logged = "\n".join(
        f"{record.getMessage()}\n{record.exc_text or ''}" for record in caplog.records
    )
    assert secret not in logged


# --------------------------------------------------------------------------- #
# Biblioteca: recursos obligatorios y contraindicaciones que no se callan
# --------------------------------------------------------------------------- #


def _write(tmp_path: Path, **override: object) -> Path:
    entry: dict[str, object] = {
        "id": "x", "domain": "cardiovascular", "action": "Repetir la medida.",
        "indication": "i", "crew_time_minutes": None,
        "resources": [{"key": "same-sensor", "description": "el mismo sensor"}],
        "crew_time_basis": "sin fuente", "protocol_ref": None,
        "followup_checks": ["heart-rate"], "followup_window_hours": 1,
        "followup_basis": "diseño EMMA", "contraindications_note": None,
        "adverse_effects_note": None, "basis": "demo",
        "family": "check-surveillance",
    }
    entry.update(override)
    for key in [key for key, value in entry.items() if value == "<ausente>"]:
        del entry[key]
    path = tmp_path / "library.json"
    path.write_text(json.dumps({"countermeasures": [entry]}), encoding="utf-8")
    return path


_SCANNER = {"key": "ultrasound-scanner", "description": "ecógrafo"}


def test_every_entry_of_the_library_says_its_resources() -> None:
    library = countermeasures.library()
    assert library
    for item in library.values():
        assert item.resources or item.resources_note, item.id
        assert all(name.strip() for name in item.resources), item.id
        assert not (item.resources and item.resources_note), item.id


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"resources": "<ausente>"}, "sin `resources`"),
        ({"resources": None}, "lista de"),
        ({"resources": "ecógrafo"}, "lista de"),
        ({"resources": [_SCANNER, {"key": "trained-operator", "description": ""}]},
         "sin `description`"),
        ({"resources": [_SCANNER, {"key": "trained-operator", "description": 3}]},
         "sin `description`"),
        ({"resources": []}, "vacía sin `resources_note`"),
        ({"resources": [], "resources_note": "  "}, "`resources_note` vacía"),
        ({"resources": [], "resources_note": 0}, "`resources_note` vacía"),
        ({"resources_note": "no requiere recursos"}, "solo acompaña"),
        ({"contraindications_note": "  "}, "`contraindications_note` vacía"),
    ],
)
def test_an_entry_that_does_not_say_its_resources_is_refused(
    tmp_path: Path, override: dict[str, object], reason: str
) -> None:
    with pytest.raises(LibraryError, match=reason):
        load(_write(tmp_path, **override))


def test_an_empty_list_loads_only_when_the_entry_says_why(tmp_path: Path) -> None:
    library = load(_write(tmp_path, resources=[], resources_note="no requiere recursos"))
    body = library["x"].to_dict()
    assert (body["resources"], body["resources_note"]) == ([], "no requiere recursos")
    assert load(_write(tmp_path))["x"].to_dict()["resources_note"] is None


def test_missing_contraindications_are_said_pending_not_absent(tmp_path: Path) -> None:
    pending = load(_write(tmp_path))["x"].to_dict()
    assert pending["contraindications_note"] is None
    assert pending["contraindications_display"] == CONTRAINDICATIONS_PENDING
    assert "pendiente de revisión médica" in CONTRAINDICATIONS_PENDING
    written = load(_write(tmp_path, contraindications_note="texto de la revisión"))["x"]
    assert written.to_dict()["contraindications_display"] == "texto de la revisión"
    # La biblioteca real: lo que no está escrito se dice pendiente, entrada por entrada.
    for item in countermeasures.library().values():
        assert item.contraindications_display == (
            item.contraindications_note or CONTRAINDICATIONS_PENDING)


def test_the_published_library_carries_both_texts(client: TestClient) -> None:
    for item in client.get("/api/countermeasures").json()["countermeasures"]:
        assert item["contraindications_display"]
        assert "resources_note" in item and isinstance(item["resources"], list)
