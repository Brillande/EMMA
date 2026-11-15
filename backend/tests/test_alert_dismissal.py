"""Descartar una alerta (la «HUMAN DECISION / Dismiss» de la conversación de ideación, L161-162).

Un asiento firmado `alert-dismissal` con un motivo de vocabulario cerrado y quién lo dice. La
alerta sigue en la lista marcada como descartada y ningún cálculo cambia: niveles, riesgo,
`rules_version`, reconocimiento y anuncio son los mismos. Un estado declarado después la deja
atrás, y no cubre otro nivel ni lo que alerte pasada la ventana (`record-integrity.md` §3.20 bis).

Las pruebas rápidas van primero: la campaña de mutantes (`tests/mutants/alert_dismissal.json`)
corre este fichero una vez por mutante y para en el primer fallo.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis.risk import RiskLevel
from app.api import alert_history as api_history
from app.api import routes
from app.core.storage import DISMISSAL_ENTRY_TYPE, DISMISSAL_REASONS, ObservationStore
from app.ingest.codes import Domain
from tests.test_api import alerting, client  # noqa: F401 — fixtures

__all__ = ["alerting", "client"]

T = dt.datetime(2026, 11, 13, 4, tzinfo=dt.UTC)


def _signed(index: int, level: str = "watch", at: dt.datetime = T, **extra: str) -> dict[str, Any]:
    return {"ledger_index": index, "domain": "behavioral", "level": level,
            "reference_time": at.isoformat(), "declared_by": "CMO", "note": "", **extra}


def _dismissal_of(dismissals: list[dict[str, Any]], level: RiskLevel = RiskLevel.WATCH,
                  resolutions: tuple[dict[str, Any], ...] = ()) -> Any:
    domains: dict[Domain, Any] = {Domain.BEHAVIORAL: SimpleNamespace(level=level)}
    [alert] = routes._alerts(domains, [], {}, T, T, resolutions, dismissals)
    return alert["dismissal"]


# --------------------------------------------------------------------------- #
# Rápidas: lo que cubre un descarte, lo que cuenta y lo que el almacén rechaza
# --------------------------------------------------------------------------- #


def test_a_dismissal_covers_that_alert_and_not_future_ones() -> None:
    dismissed = _signed(5, reason="sensor_artifact")
    shown = _dismissal_of([dismissed])
    assert (shown["ledger_index"], shown["reason_display"]) == (5, "artefacto del sensor")
    # Un cambio de nivel es otra alerta: llega sin descartar.
    assert _dismissal_of([dismissed], level=RiskLevel.CONCERN) is None
    # Pasada la ventana de cálculo, lo que alerta se apoya en lecturas nuevas.
    old = _signed(5, at=T - routes.CURRENT_WINDOW - dt.timedelta(minutes=1),
                  reason="sensor_artifact")
    assert _dismissal_of([old]) is None
    # Lo último que una persona dijo de la alerta es lo que se ve.
    later_state = _signed(6, state="resuelto")
    assert _dismissal_of([dismissed], resolutions=(later_state,)) is None
    earlier_state = _signed(4, state="en_arreglo")
    assert _dismissal_of([dismissed], resolutions=(earlier_state,))["ledger_index"] == 5


def test_only_what_the_api_would_have_accepted_counts() -> None:
    assert routes._acceptable_dismissal(_signed(1, reason="sensor_artifact"))
    assert routes._acceptable_dismissal(_signed(1, reason="other", note="electrodo"))
    assert not routes._acceptable_dismissal(_signed(1, reason="other", note="  "))
    assert not routes._acceptable_dismissal(_signed(1, reason="inventado", note="x"))
    assert not routes._acceptable_dismissal({**_signed(1, reason="sensor_artifact"),
                                             "declared_by": "42"})


def test_the_store_refuses_what_the_api_refuses() -> None:
    store: Any = ObservationStore.__new__(ObservationStore)
    console = routes.identity_for(routes.CONSOLE_IDENTITY)
    with pytest.raises(ValueError, match="motivo"):
        store.record_alert_dismissal("crew-01", "behavioral", "watch", T, "x", "", "CMO", console)
    with pytest.raises(ValueError, match="nota"):
        store.record_alert_dismissal(
            "crew-01", "behavioral", "watch", T, "other", " ", "CMO", console
        )
    with pytest.raises(ValueError, match="persona"):
        store.record_alert_dismissal(
            "crew-01", "behavioral", "watch", T, "sensor_artifact", "", "42", console
        )


class _Dismissals:
    """Un almacén con solo descartes: lo que lee la historia de alertas."""

    def __init__(self) -> None:
        base = {**_signed(0), "recorded": T.isoformat(), "signer": routes.CONSOLE_IDENTITY}
        self._items = [
            {**base, "ledger_index": 1, "reason": "explained_by_context"},
            {**base, "ledger_index": 2, "reason": "other"},  # sin nota: no cuenta
            {**base, "ledger_index": 3, "reason": "sensor_artifact", "signer": "wearable-ble"},
        ]

    def acknowledgements(self, subject: str) -> list[dict[str, Any]]:
        return []

    def alert_resolutions(self, subject: str) -> list[dict[str, Any]]:
        return []

    def annunciation_changes(self, subject: str) -> list[dict[str, Any]]:
        return []

    def alert_dismissals(self, subject: str) -> list[dict[str, Any]]:
        return self._items


def test_the_history_lists_the_dismissal_that_counts() -> None:
    store: Any = _Dismissals()
    found = api_history._signed(store, "crew-01", None)
    assert [(item["ledger_index"], item["kind"], item["kind_display"]) for item in found] == [
        (1, "dismissal", "alerta descartada: explicada por el contexto"),
    ]


def test_the_exported_status_says_who_dismissed_it_and_why() -> None:
    from app.export import status_markdown

    alert = {"domain": "behavioral", "level": "watch", "acknowledged": False,
             "dismissal": {"declared_by": "CMO", "reason_display": "artefacto del sensor"}}
    status = {"subject": "crew-01", "data": {"reference_time": T.isoformat()},
              "alerts": [alert], "recommendations": [], "domains": {}}
    text = status_markdown(status, T)
    assert "- Descartada por CMO; motivo: artefacto del sensor" in text


def test_a_long_note_is_cut_visibly_in_the_chronicle() -> None:
    from app import timeline

    item = {**_signed(9, reason="other", note="x" * 300), "recorded": T.isoformat(),
            "signer": routes.CONSOLE_IDENTITY}

    class _Only:
        def __getattr__(self, name: str) -> Any:
            return lambda *args: [item] if name == "alert_dismissals" else []

    mission = timeline._Mission(start=dt.date(2026, 11, 1), duration_days=180, now=None)  # type: ignore[arg-type]
    events = list(timeline._ledger_events(_Only(), "crew-01", mission, None))
    [fact] = [event for event in events if event["fact"] == "alert-dismissed"]
    assert fact["que"].endswith("…)") and len(fact["que"]) <= 280


# --------------------------------------------------------------------------- #
# Por la API, sobre un escenario que alerta
# --------------------------------------------------------------------------- #


def _dismiss(client: TestClient, status: dict, reason: str, **overrides: object):  # type: ignore[no-untyped-def]  # noqa: F811
    alert = status["alerts"][0]
    body = {
        "domain": alert["domain"], "level": alert["level"],
        "reference_time": status["data"]["reference_time"],
        "reason": reason, "note": "", "declared_by": "CMO", **overrides,
    }
    return client.post("/api/alerts/dismissal", json=body)


def _without_dismissal(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """La alerta sin su descarte ni el paso del flujo que lo cuenta (descriptivo, §10)."""
    return [
        {**{k: v for k, v in alert.items() if k not in ("dismissal", "detail")},
         "detail": {k: v for k, v in alert["detail"].items() if k != "flow"}}
        for alert in alerts
    ]


def test_the_reasons_are_a_closed_list_with_their_words(client: TestClient) -> None:  # noqa: F811
    body = client.get("/api/alerts/dismissal-reasons").json()
    assert [item["code"] for item in body["reasons"]] == list(DISMISSAL_REASONS)
    assert {item["code"]: item["note_required"] for item in body["reasons"]} == {
        "sensor_artifact": False, "explained_by_context": False, "other": True,
    }
    assert all(item["display"] for item in body["reasons"]) and body["basis"]


@pytest.mark.parametrize(
    ("reason", "note"),
    [("sensor_artifact", ""), ("explained_by_context", "tras el ejercicio"),
     ("other", "electrodo recolocado")],
)
def test_a_dismissed_alert_stays_listed_and_nothing_is_recalculated(
    alerting: tuple[TestClient, dict],  # noqa: F811
    reason: str,
    note: str,
) -> None:
    client, before = alerting
    assert before["alerts"][0]["dismissal"] is None
    response = _dismiss(client, before, reason, note=note)
    assert response.status_code == 201

    assert client.get("/api/audit", params={"limit": 1}).json()["integrity_ok"] is True
    after = client.get("/api/status").json()
    dismissal = after["alerts"][0]["dismissal"]
    assert dismissal["reason"] == reason
    assert dismissal["reason_display"] == DISMISSAL_REASONS[reason]
    assert (dismissal["note"], dismissal["declared_by"]) == (note, "CMO")
    assert dismissal["ledger_index"] == response.json()["ledger_index"]
    # Ningún cálculo cambia: niveles, riesgo, reglas, y la alerta entera salvo su descarte.
    assert after["domains"] == before["domains"]
    assert after["rules_version"] == before["rules_version"]
    assert _without_dismissal(after["alerts"]) == _without_dismissal(before["alerts"])
    # Descartar no reconoce ni silencia: sigue parpadeando si nadie la reconoció.
    assert after["alerts"][0]["acknowledged"] is False
    assert after["alerts"][0]["annunciation"] == "normal"
    # Lo que sí cambia es el paso «decisión humana» del flujo, que lo cuenta.
    steps = {step["key"]: step for step in after["alerts"][0]["detail"]["flow"]["steps"]}
    assert "Descartada por CMO" in steps["human_decision"]["detail"]


def test_a_dismissal_needs_a_known_reason_a_note_for_other_a_person_and_an_alert(
    alerting: tuple[TestClient, dict],  # noqa: F811
) -> None:
    client, status = alerting
    assert _dismiss(client, status, "other").status_code == 422
    assert _dismiss(client, status, "other", note="   ").status_code == 422
    assert _dismiss(client, status, "me_parece_bien").status_code == 422
    assert _dismiss(client, status, "sensor_artifact", declared_by="123").status_code == 422
    other = "critical" if status["alerts"][0]["level"] != "critical" else "watch"
    assert _dismiss(client, status, "sensor_artifact", level=other).status_code == 409
    naive = status["data"]["reference_time"][:19]
    assert _dismiss(client, status, "sensor_artifact", reference_time=naive).status_code == 422
    # Nada de lo rechazado quedó firmado.
    assert client.get("/api/status").json()["alerts"][0]["dismissal"] is None


def test_a_dismissal_signed_outside_the_console_or_the_rules_is_not_shown(
    alerting: tuple[TestClient, dict],  # noqa: F811
) -> None:
    client, status = alerting
    alert = status["alerts"][0]
    at = dt.datetime.fromisoformat(status["data"]["reference_time"])
    store = routes.get_store()
    store.record_alert_dismissal(
        "crew-01", alert["domain"], alert["level"], at, "sensor_artifact", "", "nadie",
        routes.identity_for("wearable-ble"),
    )
    # Firmado a mano por la consola, saltándose el almacén: «otro» sin nota no vale.
    store._record_action(DISMISSAL_ENTRY_TYPE, {
        "subject": "crew-01", "domain": alert["domain"], "level": alert["level"],
        "reference_time": at.isoformat(), "reason": "other", "note": "",
        "declared_by": "CMO",
    }, routes.identity_for(routes.CONSOLE_IDENTITY))
    assert client.get("/api/status").json()["alerts"][0]["dismissal"] is None


def test_a_later_declared_state_leaves_the_dismissal_behind_and_it_can_be_dismissed_again(
    alerting: tuple[TestClient, dict],  # noqa: F811
) -> None:
    client, status = alerting
    alert = status["alerts"][0]
    body = {"domain": alert["domain"], "level": alert["level"],
            "reference_time": status["data"]["reference_time"]}
    assert _dismiss(client, status, "sensor_artifact").status_code == 201
    assert client.post("/api/alerts/acknowledge",
                       json={**body, "acknowledged_by": "CMO"}).status_code == 201
    acknowledged = client.get("/api/status").json()["alerts"][0]
    # Reconocer después no retira el descarte: son cosas distintas.
    assert acknowledged["acknowledged"] is True and acknowledged["dismissal"] is not None
    assert client.post("/api/alerts/resolution", json={
        **body, "state": "en_arreglo", "note": "", "declared_by": "CMO",
    }).status_code == 201
    working = client.get("/api/status").json()["alerts"][0]
    assert working["dismissal"] is None and working["resolution"]["state"] == "en_arreglo"
    assert _dismiss(client, status, "explained_by_context").status_code == 201
    again = client.get("/api/status").json()["alerts"][0]
    assert again["dismissal"]["reason"] == "explained_by_context"
    # La crónica cuenta los dos descartes, con su motivo: nada se borró.
    chronicle = client.get("/api/timeline/chronicle").json()
    facts = [event for event in chronicle["events"] if event["fact"] == "alert-dismissed"]
    assert len(facts) == 2 and all(event["stage"] == "intervention" for event in facts)
    assert any("artefacto del sensor" in event["que"] for event in facts)
