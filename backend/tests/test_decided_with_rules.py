"""La versión de reglas, firmada con cada decisión (decimonovena ronda, U9; especificación §12).

«Todo modelo/regla debe estar versionado y disponer de trazabilidad/audit trail». La huella
(`core/versioning.rules_version`) iba en el estado y en las instantáneas de proyección, pero no en
los asientos de las decisiones humanas; y como la historia de alertas se recalcula con las reglas
de hoy, no se podía saber con qué reglas salió la alerta que alguien firmó. Estas pruebas fijan lo
que el campo es y lo que no (`record-integrity.md` §3.26):

* lo pone la ruta al firmar, con la huella vigente; el cliente no puede mandarlo (422);
* es opcional y aditivo: un asiento firmado sin él es, campo por campo, el de antes, y un ledger
  escrito con el código anterior sigue verificándose y se lee diciendo «sin versión registrada»;
* al leer se dice con qué versión se firmó y si coincide con la de hoy, sin recalcular nada: el
  veredicto del estado es idéntico con el campo y sin él (invariante 5), y `rules_version` no
  cambia por el cambio (el campo no es una regla);
* una sola redacción para el detalle de alerta, el seguimiento, el «no» y la crónica, que pasa el
  filtro de lenguaje (invariante 7).
"""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import timeline
from app.advisor.followup import decision_note, followups, standing_declines
from app.analysis.risk import RiskLevel
from app.api import alert_history, routes
from app.core import storage
from app.core.ledger import Identity
from app.core.storage import (
    _ACKNOWLEDGEMENT_FIELDS,
    _DECIDED_WITH_OPTIONAL,
    _DISMISSAL_FIELDS,
    _FOLLOWUP_FIELDS,
    _FOLLOWUP_OPTIONAL,
    _RESOLUTION_FIELDS,
    RULES_VERSION_FIELD,
    ObservationStore,
)
from app.core.versioning import NO_VERSION_RECORDED, SAME_AS_TODAY, decided_with, rules_version
from app.text_guard import check

T0 = dt.datetime(2026, 12, 1, 8, 0, tzinfo=dt.UTC)
NOW = T0 + dt.timedelta(days=30)
SLEEP = "bh-protect-sleep"
LIGHT = "bh-circadian-lighting"
OTHER = "reglas@0000000000000000"  # una huella que no es la de hoy
# Ledger con las seis decisiones (reconocimiento, estado declarado, descarte, adopción, cierre y
# «no adoptar»), escrito con el código de `main` ANTERIOR a este cambio (commit 6372fad) y
# guardado tal cual. Los hashes de contenido son los que firmó aquel código.
PRE_CHANGE_LEDGER = Path(__file__).parent / "data" / "decisions_pre_rules_version.db"
PRE_CHANGE_HASHES = [
    "fae2673035e8251b147d228dc71705f6d1c4a7ad3754e95a0c8059305a596616",
    "f6b55f3bde1e6c258453d098728578608278bdb3fbdca7d39343c15a317406d5",
    "77d0fdd2c0f0b0264487c07fa677ae415fe5d0d89ddccdbf87326cb40df77847",
    "fb278216336301ae782ff2c7ff729e563c668f8d983cb70ff890dc3f26d4ea2a",
    "352a52c0454d24cf5de247bdf62b8d0988b48833ee26f52f3d7022344de5a3c7",
    "7a786fc46e1c09b648170797d9aee50b9259564b36c56713910cb6fae36a8b3f",
]


def _public(payload: dict[str, Any]) -> set[str]:
    return {key for key in payload if not key.startswith("_")}


def _console() -> Identity:
    return Identity.generate("crew-console")


# --------------------------------------------------------------------------- #
# La frase: con qué se firmó, frente a hoy, sin recalcular
# --------------------------------------------------------------------------- #


def test_the_wording_says_the_signed_version_and_whether_it_is_todays() -> None:
    today = rules_version()
    assert decided_with(today) == {
        "rules_version": today, "same_as_today": True,
        "text": f"decidido con {today}; {SAME_AS_TODAY}",
    }
    assert decided_with(OTHER) == {
        "rules_version": OTHER, "same_as_today": False,
        "text": f"decidido con {OTHER}; distinta de la de hoy: {today} hoy",
    }
    # Sin campo no se inventa ni se compara: se dice que el asiento no lo lleva.
    assert decided_with(None) == {
        "rules_version": None, "same_as_today": None, "text": NO_VERSION_RECORDED,
    }
    assert NO_VERSION_RECORDED.startswith("sin versión registrada")


def test_every_wording_passes_the_language_guard() -> None:
    for signed in (None, rules_version(), OTHER):
        assert check(decided_with(signed)["text"]) == []


# --------------------------------------------------------------------------- #
# El almacén: un campo opcional de los asientos de decisión, y solo si se da
# --------------------------------------------------------------------------- #


def test_each_decision_entry_carries_the_version_only_when_given() -> None:
    store = ObservationStore.in_memory()
    console = _console()
    today = rules_version()
    args = ("crew-01", "behavioral", "concern", T0)

    with_it = store.acknowledge(*args, "CDR", console, rules_version=today)
    without = store.acknowledge(*args, "CDR", console)
    assert _public(with_it.payload) == {*_ACKNOWLEDGEMENT_FIELDS, RULES_VERSION_FIELD}
    assert with_it.payload[RULES_VERSION_FIELD] == today
    assert _public(without.payload) == set(_ACKNOWLEDGEMENT_FIELDS)

    with_it = store.record_alert_resolution(
        *args, "en_arreglo", "", "CMO", console, rules_version=today
    )
    without = store.record_alert_resolution(*args, "en_arreglo", "", "CMO", console)
    assert _public(with_it.payload) == {*_RESOLUTION_FIELDS, RULES_VERSION_FIELD}
    assert _public(without.payload) == set(_RESOLUTION_FIELDS)

    with_it = store.record_alert_dismissal(
        *args, "sensor_artifact", "", "CMO", console, rules_version=today
    )
    without = store.record_alert_dismissal(*args, "sensor_artifact", "", "CMO", console)
    assert _public(with_it.payload) == {*_DISMISSAL_FIELDS, RULES_VERSION_FIELD}
    assert _public(without.payload) == set(_DISMISSAL_FIELDS)

    # Las tres acciones del seguimiento, y el cierre junto a los campos opcionales que ya tenía.
    adopted = store.record_followup(
        "crew-01", "adopted", SLEEP, "behavioral", "concern", T0, "CDR", console,
        rules_version=today,
    )
    assert _public(adopted.payload) == {*_FOLLOWUP_FIELDS, RULES_VERSION_FIELD}
    closed = store.record_followup(
        "crew-01", "closed", SLEEP, "behavioral", "concern", T0, "CDR", console,
        reason="hecho", adoption_index=adopted.index, level_at_close="watch",
        closed_reference_time=NOW, rules_version=today,
    )
    assert _public(closed.payload) == {
        *_FOLLOWUP_FIELDS, *_FOLLOWUP_OPTIONAL, RULES_VERSION_FIELD}
    declined = store.record_followup(
        "crew-01", "declined", LIGHT, "behavioral", "concern", T0, "CDR", console,
        reason="no esta semana", rules_version=today,
    )
    assert _public(declined.payload) == {*_FOLLOWUP_FIELDS, RULES_VERSION_FIELD}
    bare = store.record_followup(
        "crew-01", "adopted", SLEEP, "behavioral", "concern", T0, "CDR", console
    )
    assert _public(bare.payload) == set(_FOLLOWUP_FIELDS)
    assert store.verify_integrity().ok

    # Al leer, el campo se entrega si está y no se entrega si no: nada se rellena.
    assert _DECIDED_WITH_OPTIONAL == (RULES_VERSION_FIELD,)
    for read in (
        store.acknowledgements("crew-01"), store.alert_resolutions("crew-01"),
        store.alert_dismissals("crew-01"),
    ):
        assert [item.get(RULES_VERSION_FIELD) for item in read] == [today, None]
    assert [item.get(RULES_VERSION_FIELD) for item in store.followup_decisions("crew-01")] == [
        today, today, today, None]


def test_the_store_refuses_a_blank_version_and_writes_nothing() -> None:
    store = ObservationStore.in_memory()
    console = _console()
    args = ("crew-01", "behavioral", "concern", T0)
    for blank in ("", "   "):
        with pytest.raises(ValueError, match="no va vacía"):
            store.acknowledge(*args, "CDR", console, rules_version=blank)
        with pytest.raises(ValueError, match="no va vacía"):
            store.record_alert_resolution(
                *args, "resuelto", "", "CMO", console, rules_version=blank
            )
        with pytest.raises(ValueError, match="no va vacía"):
            store.record_alert_dismissal(
                *args, "sensor_artifact", "", "CMO", console, rules_version=blank
            )
        with pytest.raises(ValueError, match="no va vacía"):
            store.record_followup(
                "crew-01", "adopted", SLEEP, "behavioral", "concern", T0, "CDR", console,
                rules_version=blank,
            )
    assert store.audit_trail() == []


# --------------------------------------------------------------------------- #
# Un ledger escrito antes del cambio: verifica, se lee y no se le inventa la versión
# --------------------------------------------------------------------------- #


def test_a_ledger_signed_before_the_change_still_verifies_and_says_no_version_recorded(
    tmp_path: Path,
) -> None:
    path = tmp_path / "emma.db"
    shutil.copyfile(PRE_CHANGE_LEDGER, path)
    store = ObservationStore.at(path)

    assert store.verify_integrity().ok
    assert [entry["content_hash"] for entry in store.audit_trail()] == PRE_CHANGE_HASHES
    [ack] = store.acknowledgements("crew-01")
    [resolution] = store.alert_resolutions("crew-01")
    [dismissal] = store.alert_dismissals("crew-01")
    decisions = store.followup_decisions("crew-01")
    assert [item["action"] for item in decisions] == ["adopted", "closed", "declined"]
    for item in (ack, resolution, dismissal, *decisions):
        assert RULES_VERSION_FIELD not in item
        assert decided_with(item.get(RULES_VERSION_FIELD))["text"] == NO_VERSION_RECORDED
    # El cierre antiguo conserva sus propios campos opcionales: nada se pierde al leer.
    assert decisions[1]["level_at_close"] == "watch"

    # Lo derivado lo dice con las mismas palabras, y lo demás es lo de siempre.
    [follow] = followups(decisions, {"behavioral": RiskLevel.WATCH}, [], NOW)
    assert follow["adoption_rules"]["text"] == NO_VERSION_RECORDED
    assert follow["closure_rules"]["text"] == NO_VERSION_RECORDED
    assert (follow["state"], follow["level_at_close"]) == ("closed", "watch")
    [declined] = standing_declines(decisions).values()
    assert decision_note(declined)["rules"]["text"] == NO_VERSION_RECORDED

    # Sobre esa misma cadena, una decisión nueva CON la versión: y se vuelve a verificar. (Otra
    # identidad: la clave de `crew-console` quedó fijada en aquel ledger a la de aquel día.)
    today = rules_version()
    store.acknowledge("crew-01", "behavioral", "concern", NOW, "CMO",
                      Identity.generate("otra-consola"), rules_version=today)
    assert store.verify_integrity().ok
    store.engine.dispose()

    reopened = ObservationStore.at(path)
    assert reopened.verify_integrity().ok
    assert [entry["content_hash"] for entry in reopened.audit_trail()][:6] == PRE_CHANGE_HASHES
    old, new = reopened.acknowledgements("crew-01")
    assert RULES_VERSION_FIELD not in old and new[RULES_VERSION_FIELD] == today
    assert decided_with(new[RULES_VERSION_FIELD])["same_as_today"] is True
    reopened.engine.dispose()


def _chronicle_sources(store: ObservationStore) -> tuple[dict[str, str], dict[str, str]]:
    """La fuente y el hecho de cada asiento que la crónica cuenta, por su clave."""
    mission = timeline._Mission(start=dt.date(2026, 11, 1), duration_days=180, now=None)  # type: ignore[arg-type]
    events = list(timeline._ledger_events(store, "crew-01", mission, None))
    return (
        {event["clave"]: event["fuente"] for event in events},
        {event["clave"]: event["fact"] for event in events},
    )


def test_the_chronicle_says_with_which_rules_each_decision_was_signed(tmp_path: Path) -> None:
    """La fuente de cada decisión firmada lleva la frase; la de lo declarado del plan, no."""
    today = rules_version()
    store = ObservationStore.in_memory()
    console = routes.identity_for(routes.CONSOLE_IDENTITY)
    new_ack = store.acknowledge(
        "crew-01", "behavioral", "concern", NOW, "CMO", console, rules_version=today
    )
    foreign = store.acknowledge(
        "crew-01", "behavioral", "watch", NOW, "CMO", console, rules_version=OTHER
    )
    # Firmado sin la versión (por fuera de las rutas): se dice, no se inventa.
    bare = store.record_alert_dismissal(
        "crew-01", "behavioral", "watch", NOW, "sensor_artifact", "", "CMO", console
    )
    eva = store.record_mission_event(
        "crew-01", "eva", NOW, NOW + dt.timedelta(hours=6), "EVA 1", "CMO", console
    )
    source, _ = _chronicle_sources(store)
    assert source[f"ledger:{new_ack.index}"] == (
        f"asiento {new_ack.index}; decidido con {today}; {SAME_AS_TODAY}"
    )
    assert source[f"ledger:{foreign.index}"] == (
        f"asiento {foreign.index}; decidido con {OTHER}; distinta de la de hoy: {today} hoy"
    )
    assert source[f"ledger:{bare.index}"] == f"asiento {bare.index}; {NO_VERSION_RECORDED}"
    # Un evento del plan no es una decisión sobre una alerta: su fuente es la de siempre.
    assert source[f"ledger:{eva.index}"] == f"asiento {eva.index}"

    # Las seis decisiones del ledger anterior al campo: «sin versión registrada», en todas.
    path = tmp_path / "emma.db"
    shutil.copyfile(PRE_CHANGE_LEDGER, path)
    old = ObservationStore.at(path)
    source, facts = _chronicle_sources(old)
    for index in range(6):
        assert source[f"ledger:{index}"] == f"asiento {index}; {NO_VERSION_RECORDED}", index
    assert sorted(facts[f"ledger:{index}"] for index in range(6)) == [
        "alert-acknowledged", "alert-dismissed", "alert-in-progress", "countermeasure-adopted",
        "countermeasure-closed", "countermeasure-declined",
    ]
    old.engine.dispose()


# --------------------------------------------------------------------------- #
# API: la ruta la pone, el cliente no puede, y el estado la dice
# --------------------------------------------------------------------------- #


@pytest.fixture
def alerting(client: TestClient) -> dict[str, Any]:
    assert client.post(
        "/api/simulate", params={"scenario": "arrhythmia", "days": 40}
    ).status_code == 201
    status: dict[str, Any] = client.get("/api/status").json()
    assert status["alerts"], "el escenario de arritmia debe alertar"
    return status


def _alert_body(status: dict[str, Any]) -> dict[str, Any]:
    alert = status["alerts"][0]
    return {
        "domain": alert["domain"], "level": alert["level"],
        "reference_time": status["data"]["reference_time"],
    }


def _first_alert(client: TestClient, status: dict[str, Any]) -> dict[str, Any]:
    after = client.get("/api/status", params={"until": status["data"]["reference_time"]}).json()
    found: dict[str, Any] = next(
        item for item in after["alerts"] if item["id"] == status["alerts"][0]["id"]
    )
    return found


def _chosen(status: dict[str, Any]) -> dict[str, Any]:
    first: dict[str, Any] = next(
        item for item in status["recommendations"] if item["countermeasure"]
    )
    return first


def test_the_routes_sign_todays_version_and_the_client_cannot_send_one(
    client: TestClient, alerting: dict[str, Any]
) -> None:
    today = rules_version()
    expected = decided_with(today)
    assert expected["same_as_today"] is True
    store = routes.get_store()

    # El cliente no puede mandarla: los cuerpos rechazan campos que sobran.
    for path, body in (
        ("/api/alerts/acknowledge", {**_alert_body(alerting), "acknowledged_by": "CDR"}),
        ("/api/alerts/resolution",
         {**_alert_body(alerting), "state": "en_arreglo", "declared_by": "CMO"}),
        ("/api/alerts/dismissal",
         {**_alert_body(alerting), "reason": "sensor_artifact", "declared_by": "CMO"}),
    ):
        assert client.post(path, json={**body, "rules_version": OTHER}).status_code == 422
    assert store.audit_trail()[-1]["entry_type"] != "alert-acknowledgement"

    # Reconocer.
    response = client.post(
        "/api/alerts/acknowledge", json={**_alert_body(alerting), "acknowledged_by": "CDR"}
    )
    assert response.status_code == 201, response.text
    assert store.acknowledgements("crew-01")[-1][RULES_VERSION_FIELD] == today
    alert = _first_alert(client, alerting)
    assert alert["acknowledged"] is True
    assert alert["acknowledgement_rules"] == expected
    # Y la del estado, de siempre, sigue siendo la misma huella.
    assert alert["rules_version"] == today

    # Declarar «en arreglo».
    response = client.post(
        "/api/alerts/resolution",
        json={**_alert_body(alerting), "state": "en_arreglo", "declared_by": "CMO"},
    )
    assert response.status_code == 201, response.text
    assert store.alert_resolutions("crew-01")[-1][RULES_VERSION_FIELD] == today
    alert = _first_alert(client, alerting)
    assert alert["resolution"]["state"] == "en_arreglo"
    assert alert["resolution"]["rules"] == expected

    # Descartar.
    response = client.post(
        "/api/alerts/dismissal",
        json={**_alert_body(alerting), "reason": "sensor_artifact", "declared_by": "CMO"},
    )
    assert response.status_code == 201, response.text
    assert store.alert_dismissals("crew-01")[-1][RULES_VERSION_FIELD] == today
    alert = _first_alert(client, alerting)
    assert alert["dismissal"]["declared_by"] == "CMO"
    assert alert["dismissal"]["rules"] == expected
    assert store.verify_integrity().ok


def test_adopting_closing_and_declining_sign_todays_version_and_the_followup_says_it(
    client: TestClient, alerting: dict[str, Any]
) -> None:
    today = rules_version()
    expected = decided_with(today)
    ident = _chosen(alerting)["countermeasure"]["id"]
    reference_time = alerting["data"]["reference_time"]
    params = {"until": reference_time}

    for path, body in (
        ("/api/countermeasures/adopt",
         {"countermeasure_id": ident, "reference_time": reference_time, "adopted_by": "CDR"}),
        ("/api/countermeasures/decline",
         {"countermeasure_id": ident, "reference_time": reference_time, "declined_by": "CDR",
          "reason": "no"}),
    ):
        assert client.post(path, json={**body, "rules_version": OTHER}).status_code == 422

    response = client.post("/api/countermeasures/adopt", json={
        "countermeasure_id": ident, "reference_time": reference_time, "adopted_by": "CDR",
    })
    assert response.status_code == 201, response.text
    adoption = int(response.json()["ledger_index"])
    [follow] = client.get("/api/status", params=params).json()["followups"]
    assert follow["adoption_rules"] == expected
    assert follow["closure_rules"] is None

    assert client.post("/api/countermeasures/close", json={
        "adoption_index": adoption, "reason": "hecho", "closed_by": "CDR",
        "rules_version": OTHER,
    }).status_code == 422
    response = client.post("/api/countermeasures/close", json={
        "adoption_index": adoption, "reason": "hecho", "closed_by": "CDR",
    })
    assert response.status_code == 201, response.text
    [follow] = client.get("/api/status", params=params).json()["followups"]
    assert follow["state"] == "closed"
    assert follow["adoption_rules"] == expected
    assert follow["closure_rules"] == expected

    # Decir que no, después de cerrar: la recomendación sale con su «no» y con qué reglas se firmó.
    response = client.post("/api/countermeasures/decline", json={
        "countermeasure_id": ident, "reference_time": reference_time, "declined_by": "CDR",
        "reason": "no esta semana",
    })
    assert response.status_code == 201, response.text
    status = client.get("/api/status", params=params).json()
    decision = next(
        item["decision"] for item in status["recommendations"]
        if (item["countermeasure"] or {}).get("id") == ident
    )
    assert decision["action"] == "declined"
    assert decision["rules"] == expected

    # Lo firmado, tal cual: las tres decisiones llevan el campo.
    decisions = client.get("/api/countermeasures/decisions").json()["decisions"]
    assert [(item["action"], item[RULES_VERSION_FIELD]) for item in decisions] == [
        ("adopted", today), ("closed", today), ("declined", today)]
    assert routes.get_store().verify_integrity().ok


def test_a_decision_signed_with_other_rules_is_said_to_differ_from_today(
    client: TestClient, alerting: dict[str, Any]
) -> None:
    """No se recalcula ni se cambia el veredicto: se dice con cuál se firmó y cuál rige hoy.

    Cada lectura dice la versión de SU asiento, no la de hoy ni la de otro asiento: aquí la
    alerta se reconoce, se declara y se descarta con otra versión, y la contramedida se adopta
    con otra y se cierra con la de hoy.
    """
    today = rules_version()
    differs = {
        "rules_version": OTHER, "same_as_today": False,
        "text": f"decidido con {OTHER}; distinta de la de hoy: {today} hoy",
    }
    alert = alerting["alerts"][0]
    store = routes.get_store()
    console = routes.identity_for(routes.CONSOLE_IDENTITY)
    at = dt.datetime.fromisoformat(alerting["data"]["reference_time"])
    where = ("crew-01", alert["domain"], alert["level"], at)
    store.acknowledge(*where, "CDR", console, rules_version=OTHER)
    store.record_alert_resolution(*where, "en_arreglo", "", "CMO", console, rules_version=OTHER)
    store.record_alert_dismissal(*where, "sensor_artifact", "", "CMO", console, rules_version=OTHER)
    adoption = store.record_followup(
        "crew-01", "adopted", SLEEP, "behavioral", "concern", at, "CDR", console,
        rules_version=OTHER,
    )
    store.record_followup(
        "crew-01", "closed", SLEEP, "behavioral", "concern", at, "CDR", console,
        reason="hecho", adoption_index=adoption.index, rules_version=today,
    )

    shown = _first_alert(client, alerting)
    assert shown["acknowledged"] is True
    assert shown["acknowledgement_rules"] == differs
    assert shown["resolution"]["rules"] == differs
    assert shown["dismissal"]["rules"] == differs
    assert (shown["domain"], shown["level"]) == (alert["domain"], alert["level"])
    assert shown["rules_version"] == today
    [follow] = client.get(
        "/api/status", params={"until": alerting["data"]["reference_time"]}
    ).json()["followups"]
    assert follow["adoption_rules"] == differs
    assert follow["closure_rules"] == decided_with(today)
    assert follow["closure_rules"]["same_as_today"] is True


def _without_decided_with(value: Any) -> Any:
    """Lo mismo, sin los bloques «con qué reglas se firmó» (los únicos que este cambio añade)."""
    if isinstance(value, dict):
        if set(value) == {"rules_version", "same_as_today", "text"}:
            return None
        return {key: _without_decided_with(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_without_decided_with(item) for item in value]
    return value


def test_the_verdict_is_identical_with_and_without_the_field(
    client: TestClient, alerting: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invariante 5: el mismo ledger, leído con el campo y como lo leía el código anterior."""
    ident = _chosen(alerting)["countermeasure"]["id"]
    reference_time = alerting["data"]["reference_time"]
    assert client.post(
        "/api/alerts/acknowledge", json={**_alert_body(alerting), "acknowledged_by": "CDR"}
    ).status_code == 201
    assert client.post(
        "/api/alerts/dismissal",
        json={**_alert_body(alerting), "reason": "sensor_artifact", "declared_by": "CMO"},
    ).status_code == 201
    adoption = client.post("/api/countermeasures/adopt", json={
        "countermeasure_id": ident, "reference_time": reference_time, "adopted_by": "CDR",
    }).json()["ledger_index"]
    assert client.post("/api/countermeasures/close", json={
        "adoption_index": adoption, "reason": "hecho", "closed_by": "CDR",
    }).status_code == 201
    params = {"until": reference_time}

    with_field = client.get("/api/status", params=params).json()
    assert with_field["alerts"][0]["acknowledgement_rules"]["same_as_today"] is True
    assert with_field["followups"][0]["closure_rules"]["same_as_today"] is True

    # El mismo ledger, leído sin el campo opcional: la frase cambia y nada más.
    monkeypatch.setattr(storage, "_DECIDED_WITH_OPTIONAL", ())
    without = client.get("/api/status", params=params).json()
    assert without["alerts"][0]["acknowledgement_rules"]["text"] == NO_VERSION_RECORDED
    assert without["alerts"][0]["dismissal"]["rules"]["text"] == NO_VERSION_RECORDED
    assert without["followups"][0]["adoption_rules"]["text"] == NO_VERSION_RECORDED
    assert without["followups"][0]["closure_rules"]["text"] == NO_VERSION_RECORDED

    assert with_field["rules_version"] == without["rules_version"] == rules_version()
    assert with_field["overall_level"] == without["overall_level"]
    assert with_field["domains"] == without["domains"]
    assert _without_decided_with(with_field) == _without_decided_with(without)
    # Y nada de esto movió un nivel: son los del estado inicial.
    assert {name: item["level"] for name, item in with_field["domains"].items()} == {
        name: item["level"] for name, item in alerting["domains"].items()}


def test_the_recalculated_history_says_with_which_rules_each_entry_was_signed() -> None:
    """La historia se recalcula con las reglas de hoy: justo ahí hay que decir con cuáles se firmó.

    Cada entrada dice la versión de SU asiento; lo firmado antes del campo, que no la lleva; y un
    anuncio, que no es de los asientos del campo, no recibe ninguna.
    """
    store = ObservationStore.in_memory()
    identity = _console()
    today = rules_version()
    store.acknowledge("crew-01", "cardiovascular", "watch", T0, "CDR", identity,
                      rules_version=OTHER)
    store.record_alert_resolution("crew-01", "cardiovascular", "watch", T0, "en_arreglo", "",
                                  "CMO", identity, rules_version=today)
    store.record_alert_dismissal("crew-01", "cardiovascular", "watch", T0, "sensor_artifact",
                                 "", "CMO", identity)
    store.set_annunciation("crew-01", "suppress", "cardiovascular", "watch", T0,
                           T0 + dt.timedelta(hours=1), "guardia", "CDR", identity)

    rules = {item["kind"]: item["rules"] for item in alert_history._signed(store, "crew-01", None)}
    assert rules == {
        "acknowledgement": decided_with(OTHER),
        "resolution": decided_with(today),
        "dismissal": decided_with(None),
        "annunciation": None,
    }
