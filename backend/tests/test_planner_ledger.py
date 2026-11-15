"""La base de datos de Marplanner vive en el ledger firmado (decisión del usuario, 2026-11-12).

Fija lo que tiene que cumplir para que Marplanner pueda reconstruir su base en memoria: cada
transacción es UN asiento firmado por `marplanner`; se entregan en orden y desde un número; quien
escribe sin haber visto todas las anteriores recibe 409 y no se anota nada; lo que no es un
changeset es 422; y un changeset alterado en disco no llega a reproducirse.
"""

import base64
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app import planner_ground, planner_link
from app.api.routes import _is_reserved_source, get_store, identity_for
from app.core import identities
from app.core.config import Settings, get_settings
from app.core.storage import PLANNER_ENTRY_TYPE, TamperedRecordError
from app.main import app

ONE = base64.b64encode(b"\x12changeset-uno").decode()
TWO = base64.b64encode(b"\x12changeset-dos").decode()


def _append(client: TestClient, changeset: str, expected: int) -> Any:
    body = {"changeset": changeset, "expected": expected}
    return client.post("/api/planner/changesets", json=body)


def test_changesets_come_back_in_order_and_signed(client: TestClient) -> None:
    assert _append(client, ONE, 0).status_code == 201
    second = _append(client, TWO, 1)
    assert second.status_code == 201 and second.json()["seq"] == 2
    body = client.get("/api/planner/changesets").json()
    assert [c["changeset"] for c in body["changesets"]] == [ONE, TWO]
    assert [c["seq"] for c in body["changesets"]] == [1, 2]
    assert {c["signer"] for c in body["changesets"]} == {identities.PLANNER_IDENTITY}
    assert body["changesets"][0]["sha256"] == hashlib.sha256(b"\x12changeset-uno").hexdigest()
    later = client.get("/api/planner/changesets", params={"after": 1}).json()
    assert [c["seq"] for c in later["changesets"]] == [2]


def test_a_stale_writer_is_rejected_and_nothing_is_written(client: TestClient) -> None:
    assert _append(client, ONE, 0).status_code == 201
    assert _append(client, TWO, 0).status_code == 409
    assert _append(client, TWO, 5).status_code == 409
    assert client.get("/api/planner/changesets").json()["count"] == 1


@pytest.mark.parametrize("bad", ["no-es-base64!!", "===="])
def test_what_is_not_a_changeset_is_422(client: TestClient, bad: str) -> None:
    assert _append(client, bad, 0).status_code == 422
    assert client.get("/api/planner/changesets").json()["count"] == 0


def test_a_changeset_altered_with_its_hash_kept_is_detected(client: TestClient) -> None:
    store = get_store()
    # Un asiento bien firmado cuyo changeset no es el de su huella: como si se hubiera escrito
    # a mano en la base con la huella vieja.
    store._record_action(PLANNER_ENTRY_TYPE, {
        "subject": "planner", "changeset": TWO,
        "sha256": hashlib.sha256(b"\x12changeset-uno").hexdigest(), "written_by": "marplanner",
    }, identity_for(identities.PLANNER_IDENTITY))
    with pytest.raises(TamperedRecordError, match="huella"):
        store.planner_changesets()


def test_nothing_else_can_sign_as_marplanner() -> None:
    assert _is_reserved_source(identities.PLANNER_IDENTITY)


def test_planner_entries_are_not_observations(client: TestClient) -> None:
    assert _append(client, ONE, 0).status_code == 201
    assert get_store().query("crew-01") == []



# --- Lo que Marplanner pide a internet, por la puerta de EMMA (invariante 3 bis) -------------

QUOTE_URL = "https://zenquotes.io/api/today"


@pytest.fixture
def online(client: TestClient, tmp_path: Path) -> TestClient:
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=False)
    return client


def _fetch(client: TestClient, purpose: str, url: str) -> Any:
    return client.post("/api/planner/fetch", json={"purpose": purpose, "url": url})


def test_without_network_nothing_leaves(client: TestClient) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.get(QUOTE_URL)
        response = _fetch(client, "planner-quotes", QUOTE_URL)
    assert response.status_code == 503 and "sin red" in response.json()["detail"]
    assert not route.called


def test_a_host_outside_its_purpose_is_refused_even_online(online: TestClient) -> None:
    # Open-Meteo y UniFi sacan datos nuestros: no tienen propósito (decisión del 2026-11-12).
    for url in ("https://api.open-meteo.com/v1/forecast?latitude=1&longitude=2",
                "https://api.ui.com/v1/hosts", "https://zenquotes.io.evil.org/api/today"):
        assert _fetch(online, "planner-quotes", url).status_code == 403, url
    assert _fetch(online, "weather", QUOTE_URL).status_code == 422


def test_with_network_the_quote_comes_through_the_gate(online: TestClient) -> None:
    with respx.mock() as router:
        router.get(QUOTE_URL).respond(200, json=[{"q": "Hola", "a": "Alguien"}])
        response = _fetch(online, "planner-quotes", QUOTE_URL)
    body = response.json()
    assert response.status_code == 200 and body["status"] == 200
    assert json.loads(body["body"]) == [{"q": "Hola", "a": "Alguien"}]


def test_an_upstream_error_keeps_its_status(online: TestClient) -> None:
    url = "https://es.wikipedia.org/api/rest_v1/feed/onthisday/all/11/12"
    with respx.mock() as router:
        router.get(url).respond(404)
        response = _fetch(online, "planner-onthisday", url)
    assert response.status_code == 200 and response.json()["status"] == 404


# --- Las pantallas de EMMA hablan con Marplanner por el backend (`app/planner_link.py`) -------


class FakeMarplanner:
    """Marplanner simulado: aprovisiona con la clave de arranque y exige la de dispositivo."""

    def __init__(self) -> None:
        self.provisions = 0
        self.seen: list[httpx.Request] = []
        self.revoked = False
        # Como en una base nueva: todos los complementos inactivos.
        self.plugins = {
            name: "inactive" for name in (
                *planner_link.EMMA_PLUGINS, "weather", "network-devices",
            )
        }
        self.activations: list[str] = []
        self.members: list[dict[str, Any]] = []
        # Como en una base nueva: Marplanner en inglés.
        self.locale: dict[str, Any] = {"timezone": "UTC", "language": "en", "weekStartDay": 1}
        self.locale_writes = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if request.url.path == "/api/auth/provision":
            bootstrap = planner_link.DEFAULT_BOOTSTRAP_KEY
            assert request.headers["authorization"] == f"Bearer {bootstrap}"
            self.provisions += 1
            return httpx.Response(
                200, json={"provisioned": True},
                headers={"set-cookie": f"mp_device_key=dev-{self.provisions}; Path=/; HttpOnly"},
            )
        expected = f"mp_device_key=dev-{self.provisions}"
        if self.revoked or request.headers.get("cookie") != expected:
            self.revoked = False
            return httpx.Response(401, json={"error": "unauthorized"})
        if request.url.path == "/api/members":
            if request.method == "POST":
                body = json.loads(request.content)
                self.members.append({"id": f"m{len(self.members)}", **body})
                return httpx.Response(201, json=self.members[-1])
            return httpx.Response(200, json=self.members)
        if request.url.path == "/api/settings":
            if request.method == "PUT":
                body = json.loads(request.content)
                assert body["object"] == "locale"
                self.locale = body["settings"]
                self.locale_writes += 1
            return httpx.Response(200, json={"locale": self.locale})
        if request.url.path == "/api/plugins":
            listing = [{"id": k, "state": v} for k, v in self.plugins.items()]
            return httpx.Response(200, json={"plugins": listing})
        if request.url.path.startswith("/api/plugins/"):
            plugin = request.url.path.split("/")[3]
            self.plugins[plugin] = "active"
            self.activations.append(plugin)
            return httpx.Response(200, json={"id": plugin, "state": "active"})
        if any(
            request.url.path.startswith(f"/api/{name}") and state != "active"
            for name, state in self.plugins.items()
        ):
            return httpx.Response(503, json={"code": "plugin_unavailable"})
        return httpx.Response(
            200, json={"path": request.url.path, "query": request.url.query.decode()}
        )


@pytest.fixture
def marplanner(client: TestClient) -> Iterator[FakeMarplanner]:
    fake = FakeMarplanner()
    planner_link.reset_link(planner_link.PlannerLink(httpx.MockTransport(fake)))
    yield fake
    planner_link.reset_link()


def test_the_console_reads_marplanner_without_holding_its_keys(
    client: TestClient, marplanner: FakeMarplanner
) -> None:
    first = client.get("/api/planner/app/chores/board", params={"date": "2026-11-12"})
    assert first.status_code == 200
    assert first.json() == {"path": "/api/chores/board", "query": "date=2026-11-12"}
    client.get("/api/planner/app/members")
    assert marplanner.provisions == 1  # se aprovisiona una vez, no en cada petición
    assert "mp_device_key" not in first.headers.get("set-cookie", "")


def test_the_plugins_emma_uses_are_activated_and_the_leaky_ones_are_not(
    client: TestClient, marplanner: FakeMarplanner
) -> None:
    # En el instalador, la primera vez: «This plugin is unavailable» (2026-11-12).
    assert client.get("/api/planner/app/reminders").status_code == 200
    assert sorted(marplanner.activations) == sorted(planner_link.EMMA_PLUGINS)
    assert {marplanner.plugins[n] for n in ("weather", "network-devices")} == {"inactive"}
    # Sin `printing` la hoja diaria se compone sin imagen y no se ve (2026-11-12).
    assert "printing" in marplanner.activations
    marplanner.revoked = True
    client.get("/api/planner/app/members")
    assert len(marplanner.activations) == len(planner_link.EMMA_PLUGINS)  # ya activos: no repite


def test_the_print_queue_reaches_marplanner(
    client: TestClient, marplanner: FakeMarplanner
) -> None:
    # La pantalla de EMMA es quien imprime en la térmica (2026-11-13): reclama, lee y confirma.
    assert client.get("/api/planner/app/printing/status").status_code == 200
    claim = client.post("/api/planner/app/printing/claim", headers={"X-EMMA-Console": "1"})
    assert claim.status_code == 200
    paths = [r.url.path for r in marplanner.seen]
    assert paths[-2:] == ["/api/printing/status", "/api/printing/claim"]


def test_the_planner_speaks_spanish(client: TestClient, marplanner: FakeMarplanner) -> None:
    # La hoja diaria salía en inglés (el usuario: «ponlo en español», 2026-11-12).
    client.get("/api/planner/app/members")
    assert marplanner.locale == {"timezone": "UTC", "language": "es", "weekStartDay": 1}
    marplanner.revoked = True
    client.get("/api/planner/app/members")
    assert marplanner.locale_writes == 1  # ya en español: no lo reescribe


def test_each_crew_member_is_a_planner_member_once(
    client: TestClient, marplanner: FakeMarplanner
) -> None:
    # «Si estamos en crew-01 está claro que el miembro es crew-01» (usuario, 2026-11-12).
    assert client.post(
        "/api/simulate", params={"scenario": "co2-fatigue", "days": 2},
        headers={"X-EMMA-Console": "1"},
    ).status_code == 201
    client.get("/api/planner/app/chores/board")
    client.get("/api/planner/app/members")
    names = sorted(m["displayName"] for m in marplanner.members)
    assert names == ["crew-01", "crew-02", "crew-03", "crew-04"]
    assert {m["role"] for m in marplanner.members} == {"parent"}


def test_a_revoked_device_is_provisioned_again(
    client: TestClient, marplanner: FakeMarplanner
) -> None:
    assert client.get("/api/planner/app/members").status_code == 200
    marplanner.revoked = True
    assert client.get("/api/planner/app/members").status_code == 200
    assert marplanner.provisions == 2


@pytest.mark.parametrize("path", [
    "auth/provision", "plugins", "backups", "telemetry", "weather", "network-devices",
    "members/../auth/provision",
])
def test_administration_and_what_leaks_are_not_reachable(
    client: TestClient, marplanner: FakeMarplanner, path: str
) -> None:
    assert client.get(f"/api/planner/app/{path}").status_code in (403, 404)
    assert marplanner.seen == []


def test_marplanner_must_be_on_this_machine(
    client: TestClient, marplanner: FakeMarplanner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMMA_PLANNER_URL", "http://planner.example.org:8790")
    response = client.get("/api/planner/app/members")
    assert response.status_code == 503 and "loopback" in response.json()["detail"]
    assert marplanner.seen == []


def test_a_write_without_the_console_header_does_not_reach_marplanner(
    client: TestClient, marplanner: FakeMarplanner
) -> None:
    path = "/api/planner/app/chores/x/completions"
    headers = dict(client.headers)
    del client.headers["X-EMMA-Console"]
    try:
        assert client.post(path, content=b"{}").status_code == 403
        assert marplanner.seen == []
    finally:
        client.headers.update(headers)
    assert client.post(path, content=b"{}").status_code == 200


# --- Lo que Tierra ve del planificador: un resumen hasta el corte (`app/planner_ground.py`) ----


@pytest.fixture
def summary_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload)
        return {"from": "x", "until_day": payload["until_day"], "members": []}

    monkeypatch.setattr(planner_ground, "run_node", fake)
    planner_ground._cache.clear()
    return calls


def test_ground_only_gets_what_was_recorded_before_its_cut(
    client: TestClient, summary_calls: list[dict[str, Any]]
) -> None:
    assert _append(client, ONE, 0).status_code == 201
    first_recorded = client.get("/api/planner/changesets").json()["changesets"][0]["recorded"]
    assert _append(client, TWO, 1).status_code == 201
    early = {"until": "2000-01-01T00:00:00+00:00"}
    before = client.get("/api/planner/ground-summary", params=early)
    assert before.status_code == 200 and summary_calls[-1]["records"] == []
    at_first = client.get("/api/planner/ground-summary", params={"until": first_recorded})
    assert at_first.status_code == 200 and summary_calls[-1]["records"] == [ONE]
    now = client.get("/api/planner/ground-summary").json()
    assert summary_calls[-1]["records"] == [ONE, TWO]
    assert "no es una medida" in now["leisure_rule"]


def test_the_leisure_rule_is_the_declared_word_list(
    client: TestClient, summary_calls: list[dict[str, Any]]
) -> None:
    client.get("/api/planner/ground-summary")
    assert summary_calls[-1]["leisure_words"] == planner_ground.leisure_words()
    assert "ocio" in summary_calls[-1]["leisure_words"]


def test_the_same_cut_is_computed_once(
    client: TestClient, summary_calls: list[dict[str, Any]]
) -> None:
    params = {"until": "2026-11-12T10:00:00+00:00"}
    client.get("/api/planner/ground-summary", params=params)
    client.get("/api/planner/ground-summary", params=params)
    assert len(summary_calls) == 1


def test_without_node_or_with_a_naive_cut_it_says_so(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(payload: dict[str, Any]) -> dict[str, Any]:
        raise planner_ground.SummaryUnavailable("no hay Node en esta máquina")

    monkeypatch.setattr(planner_ground, "run_node", down)
    planner_ground._cache.clear()
    response = client.get("/api/planner/ground-summary")
    assert response.status_code == 503 and "Node" in response.json()["detail"]
    naive = client.get("/api/planner/ground-summary", params={"until": "2026-11-12T10:00:00"})
    assert naive.status_code == 422


def test_on_the_desktop_the_summary_is_asked_to_the_local_service(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """En el instalador `EMMA.exe` no hace de Node: el resumen lo da un servicio en loopback."""
    url = "http://127.0.0.1:8792/summary"
    monkeypatch.setenv("EMMA_PLANNER_SUMMARY_URL", url)
    planner_ground._cache.clear()
    with respx.mock() as router:
        route = router.post(url).respond(200, json={"until_day": "2026-11-12", "members": []})
        response = client.get("/api/planner/ground-summary")
    assert response.status_code == 200 and route.called
    sent = json.loads(route.calls[0].request.content)
    assert sent["leisure_words"] == planner_ground.leisure_words()


def test_the_summary_service_must_be_local(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMMA_PLANNER_SUMMARY_URL", "http://resumen.example.org/summary")
    planner_ground._cache.clear()
    response = client.get("/api/planner/ground-summary")
    assert response.status_code == 503 and "local" in response.json()["detail"]
