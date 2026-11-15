"""Lo que espera por una persona (`atascos.esperan_por_titular` de Polaris). Sin red."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import polaris, waiting
from app.api import timeline as timeline_api
from app.api.routes import CONSOLE_IDENTITY, get_store

TODAY = dt.date(2026, 10, 10)


class FakeStore:
    def __init__(self, **items: list[dict[str, Any]]) -> None:
        self.items = items

    def alert_resolutions(self, subject: str) -> list[dict[str, Any]]:
        # Como los firma la API: con la identidad de la consola, salvo que el caso diga otra.
        return [{"signer": CONSOLE_IDENTITY, **item} for item in self.items.get("resolutions", [])]

    def alert_dismissals(self, subject: str) -> list[dict[str, Any]]:
        return self.items.get("dismissals", [])

    def scanned_reports(self, subject: str) -> list[dict[str, Any]]:
        return self.items.get("reports", [])

    def lab_confirmations(self, index: int) -> list[dict[str, Any]]:
        return self.items.get("confirmations", [])

    def imaging_studies(self, subject: str) -> list[dict[str, Any]]:
        return self.items.get("studies", [])

    def drafts(self, study: int) -> list[dict[str, Any]]:
        return self.items.get("drafts", [])


def _status(*alerts: dict[str, Any], reference: str = "2026-12-10T00:00:00+00:00") -> dict:  # type: ignore[type-arg]
    return {"alerts": list(alerts), "data": {"reference_time": reference}}


def _alert(onset: str, acknowledged: bool = False) -> dict[str, Any]:
    return {"domain": "cardiovascular", "level": "concern", "acknowledged": acknowledged,
            "detail": {"onset": onset}}


def test_an_alert_unacknowledged_for_days_waits_and_a_new_one_does_not() -> None:
    status = _status(_alert("2026-12-01T00:00:00+00:00"), _alert("2026-12-09T00:00:00+00:00"))
    found = waiting.waiting(status, FakeStore(), {}, "crew-01", [], TODAY)
    assert [(item["title"], item["days"]) for item in found["waiting"]] == [
        ("Alerta cardiovascular sin reconocer", 9),
    ]
    assert found["threshold_days"] == 3


def test_each_clock_counts_its_own_days_and_the_oldest_comes_first() -> None:
    store = FakeStore(
        reports=[{"ledger_index": 4, "recorded": "2026-10-01T09:00:00+00:00",
                  "lab_readings": {"readings": [{}, {}, {}]}}],
        confirmations=[{"reading_index": 0}],
        studies=[{"ledger_index": 2}],
        drafts=[{"ledger_index": 7, "status": "unvalidated", "signoff": None,
                 "recorded": "2026-10-06T09:00:00+00:00"}],
        resolutions=[{"domain": "cardiovascular", "level": "concern", "state": "en_arreglo",
                      "recorded": "2026-09-20T00:00:00+00:00"}],
    )
    found = waiting.waiting(_status(), store, {}, "crew-01", [], TODAY)
    assert [(item["kind"], item["days"]) for item in found["waiting"]] == [
        ("resolver", 20), ("confirmar", 9), ("firmar", 4),
    ]
    assert found["waiting"][1]["title"] == "2 cifras sin confirmar en el informe 4"


def test_an_alert_dismissed_after_being_in_repair_does_not_wait() -> None:
    """Vale lo último que se dijo (§5.37.6): descartada después de «en arreglo», ya no espera."""
    repair = {"domain": "cardiovascular", "level": "concern", "state": "en_arreglo",
              "recorded": "2026-09-20T00:00:00+00:00", "ledger_index": 5}
    dismissal = {"domain": "cardiovascular", "level": "concern", "ledger_index": 6,
                 "recorded": "2026-09-21T00:00:00+00:00"}
    later = waiting.waiting(_status(), FakeStore(resolutions=[repair], dismissals=[dismissal]),
                            {}, "crew-01", [], TODAY)
    assert later["waiting"] == []
    # Un descarte anterior al «en arreglo» no lo retira, ni uno de otro nivel.
    earlier = {**dismissal, "ledger_index": 4}
    other = {**dismissal, "level": "watch"}
    for kept in (earlier, other):
        found = waiting.waiting(_status(), FakeStore(resolutions=[repair], dismissals=[kept]),
                                {}, "crew-01", [], TODAY)
        assert [item["kind"] for item in found["waiting"]] == ["resolver"]


def test_what_is_resolved_or_signed_does_not_wait() -> None:
    store = FakeStore(
        resolutions=[{"domain": "cardiovascular", "level": "concern", "state": "resuelto",
                      "recorded": "2026-09-20T00:00:00+00:00"}],
        studies=[{"ledger_index": 2}],
        drafts=[{"ledger_index": 7, "status": "unvalidated", "signoff": {"decision": "accepted"},
                 "recorded": "2026-09-01T09:00:00+00:00"}],
    )
    status = _status(_alert("2026-11-01T00:00:00+00:00", acknowledged=True))
    assert waiting.waiting(status, store, {}, "crew-01", [], TODAY)["waiting"] == []


def test_a_broken_routine_waits_from_its_last_good_reading() -> None:
    routines = {"routines": [{"display": "Heart rate", "display_es": "Frecuencia cardiaca",
                              "state": "rota",
                              "last_success": "2026-12-01T00:00:00+00:00"}]}
    found = waiting.waiting(_status(), FakeStore(), routines, "crew-01", [], TODAY)
    assert [(item["kind"], item["days"]) for item in found["waiting"]] == [("medir", 9)]


def test_incongruences_are_shown_without_waiting_days() -> None:
    crossed = [{"key": "hemoglobin", "sample": "sangre 2026-12-09", "readings": []}]
    assert waiting.waiting(_status(), FakeStore(), {}, "crew-01", crossed, TODAY)[
        "incongruences"] == crossed


def test_it_is_polaris_rule_that_decides_who_waits() -> None:
    # Su `_manos`: un hilo con `gate` es de una persona. Sin `gate` y con dueño, de un agente.
    tool = polaris.load("atascos")
    thread = waiting._thread("x", "firmar", "2026-10-01")
    assert tool.esperan_por_titular([thread], TODAY)
    assert not tool.esperan_por_titular([{**thread, "gate": None, "dueno": "agente"}], TODAY)


def test_the_endpoint_answers(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "arrhythmia", "days": 40})
    body = client.get("/api/timeline/waiting").json()
    assert body["threshold_days"] == 3 and isinstance(body["waiting"], list)


# --------------------------------------------------------------------------- #
# El dominio por su nombre (§5.36.3)
# --------------------------------------------------------------------------- #


def test_the_threads_name_the_domain_in_spanish_not_by_its_api_key() -> None:
    alert = {**_alert("2026-12-01T00:00:00+00:00"), "domain": "immune"}
    store = FakeStore(resolutions=[{"domain": "musculoskeletal", "level": "watch",
                                    "state": "en_arreglo",
                                    "recorded": "2026-09-20T00:00:00+00:00"}])
    found = waiting.waiting(_status(alert), store, {}, "crew-01", [], TODAY)
    assert [item["title"] for item in found["waiting"]] == [
        "Alerta musculoesquelético en arreglo", "Alerta inmune sin reconocer",
    ]


def test_a_domain_the_catalogue_does_not_know_keeps_its_key() -> None:
    assert waiting.unacknowledged_title("desconocido") == "Alerta desconocido sin reconocer"


# --------------------------------------------------------------------------- #
# Tierra: lo que hay en su corte, y nada de después (§5.36.3)
# --------------------------------------------------------------------------- #

CUT = dt.datetime(2026, 10, 5, 12, tzinfo=dt.UTC)
BEFORE = "2026-10-01T09:00:00+00:00"
AFTER = "2026-10-07T09:00:00+00:00"


def _cut(store: FakeStore) -> list[tuple[str, int]]:
    found = waiting.waiting(_status(), store, {}, "crew-01", [], TODAY, until=CUT)
    return [(item["title"], item["days"]) for item in found["waiting"]]


def test_for_the_ground_a_report_registered_after_the_cut_has_not_arrived() -> None:
    late = {"ledger_index": 4, "recorded": AFTER, "lab_readings": {"readings": [{}, {}]}}
    assert _cut(FakeStore(reports=[late])) == []
    assert waiting.reports_known(FakeStore(reports=[late]), "crew-01", CUT) == []
    assert waiting.reports_known(FakeStore(reports=[late]), "crew-01", None) == [late]


def test_for_the_ground_a_confirmation_after_the_cut_leaves_the_figure_pending() -> None:
    report = {"ledger_index": 4, "recorded": BEFORE, "lab_readings": {"readings": [{}, {}]}}
    store = FakeStore(reports=[report], confirmations=[
        {"reading_index": 0, "recorded": "2026-10-02T09:00:00+00:00"},
        {"reading_index": 1, "recorded": AFTER},
    ])
    # El reloj del registro se para en el corte: 4 días (del 1 al 5), no 9 (hasta hoy).
    assert _cut(store) == [("1 cifra sin confirmar en el informe 4", 4)]


def test_for_the_ground_a_signature_after_the_cut_has_not_arrived_and_a_later_draft_neither(
) -> None:
    store = FakeStore(studies=[{"ledger_index": 2, "recorded": BEFORE}], drafts=[
        {"ledger_index": 7, "status": "unvalidated", "recorded": BEFORE,
         "signoff": {"decision": "accepted", "recorded": AFTER}},
        {"ledger_index": 9, "status": "unvalidated", "recorded": AFTER, "signoff": None},
    ])
    assert _cut(store) == [("Borrador 7 sin firmar", 4)]
    # Los hilos mismos, antes de contar días: el borrador posterior al corte no está ni empieza
    # a contar (con el reloj parado en el corte, sus días saldrían negativos y se esconderían).
    _, record_clock = waiting.threads(_status(), store, {}, "crew-01", CUT)
    assert [thread["titulo"] for thread in record_clock] == ["Borrador 7 sin firmar"]


def test_for_the_ground_what_was_signed_right_at_the_cut_has_arrived() -> None:
    store = FakeStore(studies=[{"ledger_index": 2, "recorded": BEFORE}], drafts=[
        {"ledger_index": 7, "status": "unvalidated", "recorded": BEFORE,
         "signoff": {"decision": "accepted", "recorded": CUT.isoformat()}},
    ])
    assert _cut(store) == []


def test_for_the_ground_a_study_registered_after_the_cut_has_no_drafts_yet() -> None:
    store = FakeStore(studies=[{"ledger_index": 2, "recorded": AFTER}], drafts=[
        {"ledger_index": 7, "status": "unvalidated", "recorded": BEFORE, "signoff": None},
    ])
    assert _cut(store) == []


def test_for_the_ground_the_alert_state_is_the_last_one_signed_before_the_cut() -> None:
    store = FakeStore(resolutions=[
        {"domain": "immune", "level": "watch", "state": "en_arreglo", "recorded": BEFORE},
        {"domain": "immune", "level": "watch", "state": "resuelto", "recorded": AFTER},
        {"domain": "bone", "level": "watch", "state": "en_arreglo", "recorded": AFTER},
    ])
    assert _cut(store) == [("Alerta inmune en arreglo", 4)]


def test_the_record_clock_never_runs_past_the_real_one() -> None:
    # Un corte por delante del reloj real (el simulador va por delante): cuenta hasta hoy.
    report = {"ledger_index": 4, "recorded": BEFORE, "lab_readings": {"readings": [{}]}}
    found = waiting.waiting(_status(), FakeStore(reports=[report]), {}, "crew-01", [], TODAY,
                            until=dt.datetime(2027, 1, 1, tzinfo=dt.UTC))
    assert [item["days"] for item in found["waiting"]] == [9]


def _ground_cut(client: TestClient) -> dt.datetime:
    """Doce días antes de la última lectura de a bordo, tras sembrar el simulador."""
    client.post("/api/simulate", params={"scenario": "arrhythmia", "days": 40})
    reference = client.get("/api/status").json()["data"]["reference_time"]
    return dt.datetime.fromisoformat(reference) - dt.timedelta(days=12)


def test_the_ground_route_cuts_by_until_and_signs_nothing(client: TestClient) -> None:
    cut = _ground_cut(client)
    ledger = client.get("/api/audit").json()
    body = client.get("/api/timeline/waiting", params={"until": cut.isoformat()}).json()
    ground = client.get("/api/status", params={"until": cut.isoformat()}).json()
    assert client.get("/api/audit").json() == ledger
    open_alerts = {
        waiting.unacknowledged_title(alert["domain"])
        for alert in ground["alerts"] if not alert["acknowledged"]
    }
    for item in body["waiting"]:
        assert item["since"] <= cut.date().isoformat()
        if item["kind"] == "reconocer":
            assert item["title"] in open_alerts
    # Lo que espera se cuenta hasta la última lectura llegada, no hasta la de a bordo.
    ground_today = dt.date.fromisoformat(ground["data"]["reference_time"][:10])
    for item in body["waiting"]:
        if item["kind"] == "reconocer":
            assert item["days"] == (ground_today - dt.date.fromisoformat(item["since"])).days


def test_the_shared_wiring_hands_the_cut_to_every_piece(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Con el simulador los asientos del registro son siempre anteriores al corte (los datos van
    # por delante del reloj), así que una ruta entera no ve si el corte llega a cada pieza: se
    # mira aquí qué recibe cada una del cableado que comparten la ruta y las cinco preguntas.
    cut = _ground_cut(client)
    status =client.get("/api/status", params={"until": cut.isoformat()}).json()
    seen: dict[str, Any] = {}

    def spy_waiting(*args: Any, **kwargs: Any) -> dict[str, Any]:
        seen["routines"], seen["until"] = args[2], kwargs.get("until")
        return {}

    def spy_reports(store: Any, subject: str, until: dt.datetime | None) -> list[Any]:
        seen["reports_until"] = until
        return []

    monkeypatch.setattr(waiting, "waiting", spy_waiting)
    monkeypatch.setattr(waiting, "reports_known", spy_reports)
    timeline_api.waiting_for(status, get_store(), "crew-01", cut)
    assert seen["until"] == cut and seen["reports_until"] == cut
    assert seen["routines"]["now_source"] == "cut"


def test_the_ground_route_hands_the_ground_state_and_its_cut_to_the_wiring(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sin alertas viejas en el corte, la respuesta entera no distingue el estado de a bordo del de
    # Tierra: se mira qué estado y qué corte recibe el cableado.
    cut = _ground_cut(client)
    ground = client.get("/api/status", params={"until": cut.isoformat()}).json()
    seen: list[tuple[str, dt.datetime | None]] = []

    def spy(status: dict[str, Any], store: Any, subject: str,
            until: dt.datetime | None = None) -> dict[str, Any]:
        seen.append((status["data"]["reference_time"], until))
        return {"threshold_days": 3, "waiting": [], "incongruences": []}

    monkeypatch.setattr(timeline_api, "waiting_for", spy)
    client.get("/api/timeline/waiting", params={"until": cut.isoformat()})
    assert seen == [(ground["data"]["reference_time"], cut)]


def test_the_ground_route_refuses_an_instant_without_time_zone(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "arrhythmia", "days": 40})
    response = client.get("/api/timeline/waiting", params={"until": "2026-11-20T00:00:00"})
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Decimoséptima ronda (§5.37.13): la regla del estado, los errores y un solo corte
# --------------------------------------------------------------------------- #


def test_only_the_console_signs_the_state_of_an_alert_as_for_the_status() -> None:
    # Con la regla de `routes._counts`: un «en arreglo» que no firmó la consola no espera, y un
    # «resuelto» que no firmó la consola no cierra el arreglo que sí firmó.
    other = "otra-identidad"
    store = FakeStore(resolutions=[
        {"domain": "bone", "level": "watch", "state": "en_arreglo", "recorded": BEFORE,
         "signer": other},
        {"domain": "immune", "level": "watch", "state": "en_arreglo", "recorded": BEFORE},
        {"domain": "immune", "level": "watch", "state": "resuelto",
         "recorded": "2026-10-02T09:00:00+00:00", "signer": other},
    ])
    found = waiting.waiting(_status(), store, {}, "crew-01", [], TODAY)
    assert [item["title"] for item in found["waiting"]] == ["Alerta inmune en arreglo"]


def test_the_domain_has_one_name_where_the_domains_are_named() -> None:
    from app import twins
    from app.ingest import codes

    assert waiting.domain_name is codes.domain_name and twins.domain_name is codes.domain_name
    assert codes.domain_name("immune") == "inmune"
    assert codes.domain_name("desconocido") == "desconocido"


def test_the_route_swallows_only_the_absence_of_data(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sin lecturas, nada espera (200); cualquier otro error del estado sale con su código, no
    # como «nada espera».
    assert client.get("/api/timeline/waiting").json() == {
        "threshold_days": None, "waiting": [], "incongruences": []}

    def broken(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise HTTPException(status_code=409, detail="registro alterado")

    monkeypatch.setattr(timeline_api, "crew_status", broken)
    assert client.get("/api/timeline/waiting").status_code == 409


def test_readings_without_an_analysable_date_are_nothing_to_analyse_too(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # La 422 de `_assess` cuando ninguna lectura tiene fecha analizable: como la crónica, «nada
    # que analizar», no un error del panel.
    def undated(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise HTTPException(status_code=422, detail="ninguna lectura con fecha analizable")

    monkeypatch.setattr(timeline_api, "crew_status", undated)
    assert client.get("/api/timeline/waiting").json() == {
        "threshold_days": None, "waiting": [], "incongruences": []}


def test_the_reports_are_cut_once_per_request(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    cut = _ground_cut(client)
    status = client.get("/api/status", params={"until": cut.isoformat()}).json()
    real = waiting.reports_known
    calls: list[dt.datetime | None] = []

    def counted(store: Any, subject: str, until: dt.datetime | None) -> list[Any]:
        calls.append(until)
        return real(store, subject, until)

    monkeypatch.setattr(waiting, "reports_known", counted)
    timeline_api.waiting_for(status, get_store(), "crew-01", cut)
    assert calls == [cut]
