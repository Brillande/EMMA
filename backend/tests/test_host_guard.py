"""DNS rebinding y orígenes ajenos (`core/host_guard.py`, hallazgo run-2
`emma:api:dns-rebinding-no-host-allowlist`)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.host_guard import host_name, is_loopback_host, is_loopback_origin
from app.main import app

CONSOLE = {"X-EMMA-Console": "1"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "127.0.0.1:8000", "localhost:5173", "LOCALHOST", "[::1]:8000", "testserver"],
)
def test_loopback_hosts_pass(client: TestClient, host: str) -> None:
    assert client.get("/api/indicators", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize(
    "host",
    ["ataque.example", "ataque.example:8000", "127.0.0.1.nip.io", "localhost.ataque.example",
     "127.0.0.2", "[::2]:80", "localhost:abc", ""],
)
def test_a_rebound_host_is_refused_before_any_route(client: TestClient, host: str) -> None:
    """Con rebinding, el navegador manda el nombre del atacante: ni lee ni escribe."""
    assert client.get("/api/indicators", headers={"Host": host}).status_code == 400
    # Tampoco la cadena de actualización ni el modo seguro, aunque ponga la cabecera de consola.
    for path in ("/api/app-update/check", "/api/safe-mode/activate"):
        response = client.post(path, headers={"Host": host, **CONSOLE})
        assert response.status_code == 400, path


def test_a_foreign_origin_cannot_write(client: TestClient) -> None:
    response = client.post(
        "/api/simulate", params={"days": 1},
        headers={"Origin": "http://ataque.example", **CONSOLE},
    )
    assert response.status_code == 403


def test_reading_with_a_foreign_origin_is_left_to_cors(client: TestClient) -> None:
    """Leer no cambia nada y CORS ya no le deja ver la respuesta a otra página."""
    response = client.get("/api/indicators", headers={"Origin": "http://ataque.example"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:5173", "http://127.0.0.1:5173", "http://127.0.0.1:61234", "http://[::1]:8000"],
)
def test_the_console_origins_can_write(client: TestClient, origin: str) -> None:
    response = client.post(
        "/api/simulate", params={"days": 1}, headers={"Origin": origin, **CONSOLE}
    )
    assert response.status_code == 201, response.text


def test_without_origin_desktop_and_bridge_still_write(client: TestClient) -> None:
    """El arranque de escritorio y el puente de Marplanner no son navegadores: no mandan Origin."""
    assert client.post("/api/simulate", params={"days": 1}, headers=CONSOLE).status_code == 201


def test_host_parsing() -> None:
    assert host_name("[::1]:8000") == "::1"
    assert host_name("Localhost:5173") == "localhost"
    assert host_name("[::1]x") is None
    assert not is_loopback_host("localhost:")
    assert is_loopback_origin("http://localhost:5173")
    assert not is_loopback_origin("null")
    assert not is_loopback_origin("http://localhost.ataque.example")
    assert not is_loopback_origin("file://localhost")
