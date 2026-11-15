"""Estados de una alerta después de reconocerla: detectado → en arreglo → resuelto (Polaris
`salud.py`). No tocan el cálculo: una alerta resuelta cuyos datos siguen fuera sigue en la lista.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.test_api import alerting  # noqa: F401 — fixture

__all__ = ["alerting"]


def _state(client: TestClient, status: dict, state: str, **overrides: object):  # type: ignore[no-untyped-def]
    alert = status["alerts"][0]
    body = {
        "domain": alert["domain"], "level": alert["level"],
        "reference_time": status["data"]["reference_time"],
        "state": state, "note": "revisando el sensor", "declared_by": "CMO", **overrides,
    }
    return client.post("/api/alerts/resolution", json=body)


def test_an_alert_starts_detected_then_in_progress_then_resolved(
    alerting: tuple[TestClient, dict],  # noqa: F811
) -> None:
    client, status = alerting
    assert status["alerts"][0]["resolution"] == {"state": "detectado"}
    assert _state(client, status, "en_arreglo").status_code == 201
    assert client.get("/api/status").json()["alerts"][0]["resolution"]["state"] == "en_arreglo"
    assert _state(client, status, "resuelto").status_code == 201
    after = client.get("/api/status").json()
    assert after["alerts"][0]["resolution"]["state"] == "resuelto"
    # Resolver no oculta: la alerta sigue en la lista y el análisis no cambia.
    assert after["domains"] == status["domains"]
    assert len(after["alerts"]) == len(status["alerts"])


def test_a_state_needs_a_person_and_an_existing_alert(
    alerting: tuple[TestClient, dict],  # noqa: F811
) -> None:
    client, status = alerting
    assert _state(client, status, "en_arreglo", declared_by="123").status_code == 422
    other = "critical" if status["alerts"][0]["level"] != "critical" else "watch"
    assert _state(client, status, "resuelto", level=other).status_code == 409
    assert _state(client, status, "cerrado").status_code == 422
