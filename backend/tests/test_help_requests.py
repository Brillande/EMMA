"""Petición de ayuda urgente (decisión del usuario, 2026-11-14; `record-integrity.md` §3.32).

Un asiento `help-request` firmado por la consola de a bordo: la tripulación lo ve al firmarse, con
el resto ordenado por cercanía; Tierra, con su corte (`until`). Sigue abierta hasta un cierre
`help-request-close`, que no la borra. No toca niveles, alertas ni `rules_version`.
"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from app.api import routes
from app.core import help_requests as rules
from app.core.storage import HELP_CLOSE_ENTRY_TYPE, HELP_REQUEST_ENTRY_TYPE, ObservationStore
from tests.test_api import alerting, client  # noqa: F401 — fixtures

__all__ = ["alerting", "client"]


def _store() -> ObservationStore:
    store = routes._store
    assert store is not None
    return store


def _ask(client: TestClient, **overrides: object):
    body = {"subject": "crew-01", "signed_by": "Comandante", **overrides}
    return client.post("/api/help-requests", json=body)


# --------------------------------------------------------------------------- #
# Rápidas: qué hace falta para pedir ayuda
# --------------------------------------------------------------------------- #


def test_nothing_is_required_and_the_reason_is_not_filtered() -> None:
    # Un solo toque: ni nombre ni motivo (decisión del usuario, 2026-11-14).
    assert rules.problem("", "") is None
    assert rules.problem("Comandante", "") is None
    # Las palabras de quien pide ayuda no pasan el filtro de lenguaje: «dolor en el pecho» suena a
    # diagnóstico, y rechazarlo dejaría a alguien sin poder pedir ayuda.
    assert rules.problem("Comandante", "Dolor en el pecho, mareo") is None
    assert rules.problem("x" * (rules.MAX_NAME + 1), "") is not None
    assert rules.problem("Comandante", "x" * (rules.MAX_REASON + 1)) is not None
    assert rules.close_problem("") is not None
    assert rules.close_problem("Ingeniera") is None


# --------------------------------------------------------------------------- #
# Por la API
# --------------------------------------------------------------------------- #


def test_the_crew_sees_it_at_once_and_ground_after_its_cut(
    alerting: tuple[TestClient, dict],
) -> None:
    client, _ = alerting
    response = _ask(client, reason="Me he golpeado la cabeza")
    assert response.status_code == 201, response.text
    index = response.json()["ledger_index"]
    signed_at = dt.datetime.fromisoformat(response.json()["signed_at"])

    aboard = client.get("/api/help-requests").json()
    assert [item["ledger_index"] for item in aboard["open"]] == [index]
    shown = aboard["open"][0]
    assert shown["subject"] == "crew-01"
    assert shown["signed_by"] == "Comandante"
    assert shown["reason"] == "Me he golpeado la cabeza"
    assert aboard["headline"] == rules.HEADLINE and aboard["basis"] == rules.BASIS
    # Un solo tripulante con lecturas: no hay a quién ordenar, y se dice qué hacer en su lugar.
    assert shown["nearby"] == [] and shown["nearby_note"] == rules.NO_CREWMATES

    before = (signed_at - dt.timedelta(minutes=11)).isoformat()
    after = (signed_at + dt.timedelta(seconds=1)).isoformat()
    assert client.get("/api/help-requests", params={"until": before}).json()["open"] == []
    assert len(client.get("/api/help-requests", params={"until": after}).json()["open"]) == 1


def test_closing_keeps_the_request_and_ground_sees_it_open_until_the_close_arrives(
    alerting: tuple[TestClient, dict],
) -> None:
    client, _ = alerting
    index = _ask(client).json()["ledger_index"]
    closed = client.post(f"/api/help-requests/{index}/close", json={"signed_by": "Ingeniera"})
    assert closed.status_code == 201, closed.text
    closed_at = dt.datetime.fromisoformat(closed.json()["signed_at"])

    assert client.get("/api/help-requests").json()["open"] == []
    # Tierra, con un corte anterior al cierre, todavía la ve abierta.
    cut = (closed_at - dt.timedelta(microseconds=1)).isoformat()
    assert [
        item["ledger_index"]
        for item in client.get("/api/help-requests", params={"until": cut}).json()["open"]
    ] == [index]
    # No se borra nada: los dos asientos siguen en la cadena.
    types = [entry.entry_type for entry in _store().ledger.entries]
    assert types.count(HELP_REQUEST_ENTRY_TYPE) == 1 and types.count(HELP_CLOSE_ENTRY_TYPE) == 1
    # Ni dos cierres, ni el cierre de algo que no es una petición.
    again = client.post(f"/api/help-requests/{index}/close", json={"signed_by": "Ingeniera"})
    assert again.status_code == 422 and "ya está atendida" in again.json()["detail"]
    other = client.post("/api/help-requests/0/close", json={"signed_by": "Ingeniera"})
    assert other.status_code == 422


def test_refusals_say_why(alerting: tuple[TestClient, dict]) -> None:
    client, _ = alerting
    assert _ask(client, subject="crew-99").status_code == 422
    # Sin nombre se pide igual, y se enseña sin nombre.
    nameless = client.post("/api/help-requests", json={"subject": "crew-01"})
    assert nameless.status_code == 201, nameless.text
    shown = client.get("/api/help-requests").json()["open"][0]
    assert shown["signed_by"] is None and shown["reason"] is None
    too_long = _ask(client, reason="x" * (rules.MAX_REASON + 1))
    assert too_long.status_code == 422 and str(rules.MAX_REASON) in too_long.json()["detail"]
    naive = client.get("/api/help-requests", params={"until": "2026-11-14T10:00:00"})
    assert naive.status_code == 422


def test_it_changes_no_level_alert_or_rules_version(alerting: tuple[TestClient, dict]) -> None:
    client, status = alerting
    assert _ask(client, reason="Sangra la nariz").status_code == 201
    after = client.get("/api/status").json()
    assert after["overall_level"] == status["overall_level"]
    assert after["alerts"] == status["alerts"]
    assert after["rules_version"] == status["rules_version"]


def test_crewmates_are_ordered_by_proximity(alerting: tuple[TestClient, dict]) -> None:
    """Primero quien está en el mismo módulo, luego en otro módulo, al final sin ubicación."""
    client, status = alerting
    reference = dt.datetime.fromisoformat(status["data"]["reference_time"])
    for subject in ("crew-02", "crew-03", "crew-04"):
        observation = {"subject": subject, "key": "heart-rate", "value": 60,
                       "effective": reference.isoformat()}
        assert client.post("/api/observations", json=observation).status_code == 201, subject

    def locate(subject: str, module: str) -> None:
        response = client.post("/api/mission/events", json={
            "subject": subject, "kind": "location", "module": module,
            "start": "2026-01-01T00:00:00+00:00", "end": "2027-12-31T00:00:00+00:00",
            "declared_by": "CDR",
        })
        assert response.status_code == 201, response.text

    locate("crew-01", "laboratorio")
    locate("crew-02", "camarotes")
    locate("crew-04", "laboratorio")
    assert _ask(client, at=reference.isoformat()).status_code == 201
    shown = client.get("/api/help-requests").json()["open"][0]
    assert [(item["subject"], item["proximity"]) for item in shown["nearby"]] == [
        ("crew-04", rules.SAME_MODULE),
        ("crew-02", rules.OTHER_MODULE),
        ("crew-03", rules.UNKNOWN_PLACE),
    ]
    assert shown["location_display"] != rules.NO_LOCATION
    assert shown["nearby_note"] is None
