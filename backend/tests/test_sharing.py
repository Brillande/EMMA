"""Qué se comparte y qué no (`app/sharing.py`, `GET /api/sharing`): la tabla contra el código.

Una vista de privacidad que dice más de lo que el código hace es peor que no tenerla. Aquí falla
la prueba si la tabla promete otra lista blanca que la de `core/egress.py`, si aparece una ruta con
corte del retardo que no declara, si cita un símbolo o una prueba que no existen, si un módulo de
la aplicación abre un cliente HTTP fuera de los declarados o si una fila dice que el código la
impone sin decir dónde. Lo de la interfaz (ficheros de la consola y paneles que Tierra no monta)
va en `test_sharing_console.py`, que lee el frontend: la campaña de mutantes copia solo el backend.
"""

from __future__ import annotations

import copy
import importlib
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import sharing
from app.core import egress
from app.main import app
from app.sharing import SharingError

BACKEND = Path(__file__).resolve().parents[1]
# Lo que abre una conexión HTTP. `httpx.HTTPError` y compañía (tipos de error) no cuentan.
HTTP_CLIENT = re.compile(
    r"httpx\.(?:get|post|put|patch|delete|head|request|stream|Client|AsyncClient)\("
    r"|requests\.(?:get|post|put|patch|delete|head|request|Session)\("
    r"|urlopen\(|http\.client\.|socket\.create_connection\("
)


def table() -> dict[str, Any]:
    return copy.deepcopy(sharing.read())


def item(data: dict[str, Any], item_id: str) -> dict[str, Any]:
    return next(row for row in data["items"] if row["id"] == item_id)


def test_the_route_serves_every_row_with_its_destination_and_its_degree(client: TestClient) -> None:
    body = client.get("/api/sharing").json()
    assert [row["id"] for row in body["destinations"]] == list(sharing.DESTINATIONS)
    declared = {row["id"] for row in sharing.read()["items"]}
    assert {row["id"] for row in body["items"]} == declared
    order = [sharing.DESTINATIONS.index(row["destination"]) for row in body["items"]]
    assert order == sorted(order)
    for row in body["items"]:
        assert row["destination_text"] and row["enforcement_text"]
        if row["enforcement"] != "none":
            assert row["enforced_by"], row["id"]


def test_the_offline_state_is_the_one_of_now(client: TestClient) -> None:
    body = client.get("/api/sharing").json()
    assert body["internet"]["offline"] is True
    assert body["internet"]["offline_text"] == sharing.OFFLINE_NOW[True]


def test_the_purposes_and_hosts_are_those_of_the_allowlist(client: TestClient) -> None:
    served = client.get("/api/sharing").json()["internet"]["purposes"]
    assert {row["purpose"]: frozenset(row["hosts"]) for row in served} == egress.ALLOWLIST


def test_a_table_that_hides_a_purpose_does_not_load() -> None:
    data = table()
    data["internet"]["purposes"] = data["internet"]["purposes"][1:]
    with pytest.raises(SharingError, match="lista blanca"):
        sharing.check(data)


def test_a_table_that_names_another_host_does_not_load() -> None:
    data = table()
    data["internet"]["purposes"][0]["hosts"] = ["example.org"]
    with pytest.raises(SharingError, match="otros hosts"):
        sharing.check(data)


def test_a_table_with_an_extra_purpose_does_not_load() -> None:
    data = table()
    data["internet"]["purposes"].append(
        {"purpose": "telemetry", "what": "x", "carries": "x", "hosts": ["example.org"]}
    )
    with pytest.raises(SharingError, match="sobran"):
        sharing.check(data)


def test_code_without_a_pointer_does_not_load() -> None:
    data = table()
    row = item(data, "logs")
    row["code"], row["tests"] = [], []
    with pytest.raises(SharingError, match="no cita dónde"):
        sharing.check(data)


def test_partial_without_its_limit_does_not_load() -> None:
    data = table()
    item(data, "readings")["limit"] = None
    with pytest.raises(SharingError, match="qué queda fuera"):
        sharing.check(data)


def test_none_that_cites_code_does_not_load() -> None:
    data = table()
    item(data, "personal-notes")["code"] = [{"module": "app.core.egress", "symbol": "ALLOWLIST"}]
    with pytest.raises(SharingError, match="no cita código"):
        sharing.check(data)


def test_none_without_its_reason_does_not_load() -> None:
    data = table()
    item(data, "personal-notes")["limit"] = None
    with pytest.raises(SharingError, match="no cita código"):
        sharing.check(data)


def test_an_unknown_destination_does_not_load() -> None:
    data = table()
    item(data, "logs")["destination"] = "cloud"
    with pytest.raises(SharingError, match="destino desconocido"):
        sharing.check(data)


def test_two_rows_with_one_id_do_not_load() -> None:
    data = table()
    data["items"].append(copy.deepcopy(data["items"][0]))
    with pytest.raises(SharingError, match="mismo id"):
        sharing.check(data)


def test_what_ground_cannot_be_kept_from_is_said() -> None:
    """La fila que no impone nada existe: la tabla no solo cuenta lo que EMMA protege."""
    row = item(sharing.read(), "personal-notes")
    assert row["enforcement"] == "none"
    assert row["destination"] == "ground"


def _routes_with_cut() -> set[str]:
    schema = app.openapi()
    return {
        path
        for path, operations in schema["paths"].items()
        for operation in operations.values()
        if any(
            param.get("name") == "until" and param.get("in") == "query"
            for param in operation.get("parameters", [])
        )
    }


def test_every_route_with_the_delay_cut_is_declared() -> None:
    declared = {route["path"] for route in sharing.read()["ground_cut"]["routes"]}
    assert declared == _routes_with_cut()


def test_the_only_route_cut_on_board_is_the_ground_notes() -> None:
    up = [r["path"] for r in sharing.read()["ground_cut"]["routes"] if r["direction"] == "up"]
    assert up == ["/api/ground-notes"]


def _resolve(module: str, symbol: str | None) -> object:
    target: object = importlib.import_module(module)
    for part in (symbol or "").split(".") if symbol else []:
        target = getattr(target, part)
    return target


@pytest.mark.parametrize(
    "pointer",
    [entry for row in sharing.read()["items"] for entry in row["code"]],
    ids=lambda entry: f"{entry['module']}:{entry['symbol']}",
)
def test_every_cited_symbol_exists(pointer: dict[str, Any]) -> None:
    assert _resolve(pointer["module"], pointer["symbol"]) is not None


@pytest.mark.parametrize(
    "cited", [test for row in sharing.read()["items"] for test in row["tests"]]
)
def test_every_cited_test_exists(cited: str) -> None:
    file, _, name = cited.partition("::")
    source = (BACKEND / file).read_text(encoding="utf-8")
    assert re.search(rf"^def {re.escape(name)}\(", source, re.MULTILINE), cited


def test_no_other_module_of_the_app_opens_an_http_client() -> None:
    allowed = {client["file"] for client in sharing.read()["internet"]["http_clients"]}
    found = {
        path.relative_to(BACKEND).as_posix()
        for path in (BACKEND / "app").rglob("*.py")
        if HTTP_CLIENT.search(path.read_text(encoding="utf-8"))
    }
    assert found == allowed
