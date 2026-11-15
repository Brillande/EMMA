"""Modo seguro: corta la red, no la IA local. Regla de Polaris `codigo_rojo`: lo activa cualquiera
con motivo y solo una persona lo levanta. Sin red real (invariante 3).
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
import respx
from fastapi.testclient import TestClient

from app.api import routes, safe_mode
from app.api.routes import CONSOLE_IDENTITY, identity_for
from app.core import egress
from app.core.config import Settings
from tests.test_interpret import LLM, clean_run

ON = {"active": True, "reason": "sospecha de fuga por la red", "declared_by": "CMO"}
OFF = {"active": False, "declared_by": "Comandante"}


def test_activating_needs_a_reason_and_lifting_needs_a_person(client: TestClient) -> None:
    # Sin motivo o sin nombre es un dato malo (422); repetir el estado es un conflicto (409).
    assert client.post("/api/safe-mode", json={**ON, "reason": "  "}).status_code == 422
    assert client.post("/api/safe-mode", json=ON).status_code == 201
    assert client.post("/api/safe-mode", json=ON).status_code == 409  # ya activo
    assert client.post("/api/safe-mode", json={**OFF, "declared_by": "123"}).status_code == 422
    # Lo que el ledger no puede firmar (un sustituto UTF-16 suelto) también es del dato.
    raw = rb'{"active": false, "reason": "\ud800", "declared_by": "Comandante"}'
    sent = client.post(
        "/api/safe-mode", content=raw, headers={"Content-Type": "application/json"}
    )
    assert sent.status_code == 422
    assert client.get("/api/safe-mode").json()["active"] is True
    assert client.post("/api/safe-mode", json=OFF).status_code == 201
    state = client.get("/api/safe-mode").json()
    assert state["active"] is False and state["declared_by"] == "Comandante"


def test_safe_mode_cuts_every_exit_to_the_internet(client: TestClient, tmp_path: Path) -> None:
    online = Settings(cache_dir=tmp_path, offline=False)
    client.post("/api/safe-mode", json=ON)
    for purpose, url in (
        ("space-weather", "https://api.nasa.gov/DONKI/FLR"),
        ("radiation", "https://visualization.osdr.nasa.gov/radlab/api/"),
        ("ephemeris", "https://ssd.jpl.nasa.gov/api/horizons.api"),
        ("citations", "https://api.crossref.org/works/10.1000/x"),
    ):
        with pytest.raises(egress.EgressBlocked, match="modo seguro"):
            egress.authorize(online, purpose, url)
    client.post("/api/safe-mode", json=OFF)
    egress.authorize(online, "space-weather", "https://api.nasa.gov/DONKI/FLR")  # vuelve a salir


@respx.mock
def test_the_local_model_keeps_drafting_in_safe_mode(client: TestClient, measured: int) -> None:
    client.post("/api/safe-mode", json=ON)
    respx.post(f"{LLM}/api/chat").mock(side_effect=clean_run())
    assert client.post(f"/api/imaging/studies/{measured}/draft").status_code == 201


# Versión del estado (§5.38.13): cuenta los cambios, sube en uno con cada uno y viaja en la lectura
# y en la respuesta de cada cambio, para que la consola se quede con la más nueva sin releer.


def test_every_change_raises_the_version_and_every_answer_carries_it(client: TestClient) -> None:
    assert client.get("/api/safe-mode").json()["version"] == 0
    first = client.post("/api/safe-mode", json=ON).json()
    assert (first["version"], first["active"]) == (1, True)
    assert client.get("/api/safe-mode").json()["version"] == 1
    assert client.post("/api/safe-mode", json=ON).status_code == 409  # rechazado: no sube
    assert client.get("/api/safe-mode").json()["version"] == 1
    second = client.post("/api/safe-mode", json=OFF).json()
    assert (second["version"], second["active"]) == (2, False)
    assert client.get("/api/safe-mode").json()["version"] == 2


def test_the_version_says_which_store_it_counts(client: TestClient) -> None:
    """Cambiar de almacén (escenario nuevo, backend reiniciado) vuelve la versión a 0: la época
    del almacén, que va en la lectura y en la respuesta de cada cambio, crece con cada uno."""
    before = client.get("/api/safe-mode").json()
    changed = client.post("/api/safe-mode", json=ON).json()
    assert changed["store_epoch"] == before["store_epoch"]
    routes.reset_store(routes.new_store())
    after = client.get("/api/safe-mode").json()
    assert (after["version"], after["active"]) == (0, False)
    assert after["store_epoch"] > before["store_epoch"]
    epochs = [routes.new_store().epoch for _ in range(3)]
    assert epochs == sorted(set(epochs))  # distintas y crecientes aunque se abran seguidas


def test_a_change_answers_with_its_own_version_not_with_a_later_one(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otro cambio se firma mientras se compone la respuesta: la respuesta sigue siendo la suya."""
    store = routes._store
    assert store is not None
    real = egress.halt_state
    sneaked: list[int] = []

    def halt_state_with_a_change_in_between() -> dict[str, Any]:
        if not sneaked:
            entry = store.record_safe_mode(
                False, "", "Comandante", identity_for(CONSOLE_IDENTITY)
            )
            sneaked.append(entry.index)
        return real()

    monkeypatch.setattr(safe_mode.egress, "halt_state", halt_state_with_a_change_in_between)
    answer = client.post("/api/safe-mode", json=ON).json()
    assert sneaked, "el cambio de en medio no se firmó"
    assert (answer["version"], answer["active"]) == (1, True)
    assert answer["ledger_index"] < sneaked[0]
    monkeypatch.setattr(safe_mode.egress, "halt_state", real)
    now = client.get("/api/safe-mode").json()
    assert (now["version"], now["active"]) == (2, False)


def test_two_crossed_activations_apply_once(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Las dos miran el estado a la vez: una se firma y la otra se rechaza, no las dos.

    La lectura del estado se alarga a propósito para que la segunda llegue mientras la primera
    aún no ha firmado: sin cerrojo, las dos ven «levantado» y las dos se firman.
    """
    store = routes._store
    assert store is not None
    slow_read = store.safe_mode

    def slow() -> dict[str, Any]:
        state = slow_read()
        time.sleep(0.05)
        return state

    monkeypatch.setattr(store, "safe_mode", slow)
    start = threading.Barrier(2)

    def activate(_: int) -> int:
        start.wait()
        return client.post("/api/safe-mode", json=ON).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(pool.map(activate, range(2)))
    assert codes == [201, 409]
    assert client.get("/api/safe-mode").json()["version"] == 1


def test_crossed_changes_get_distinct_increasing_versions(client: TestClient) -> None:
    """Muchos cambios a la vez: cada uno aceptado tiene su versión, en el orden en que se firmó.

    Sin el cerrojo sobre «mirar el estado y firmar», dos activaciones cruzadas podían pasar las
    dos la comprobación de «ya está activo»: dos versiones seguidas con el mismo estado.
    """
    workers = 8
    rounds = 6
    start = threading.Barrier(workers)

    def change(worker: int) -> list[dict[str, Any]]:
        accepted: list[dict[str, Any]] = []
        start.wait()
        for turn in range(rounds):
            body = ON if (worker + turn) % 2 == 0 else OFF
            response = client.post("/api/safe-mode", json=body)
            if response.status_code == 201:
                state = response.json()
                assert state["active"] is body["active"]  # la respuesta es la de su cambio
                accepted.append(state)
            else:
                assert response.status_code == 409
        return accepted

    with ThreadPoolExecutor(max_workers=workers) as pool:
        answers = [state for found in pool.map(change, range(workers)) for state in found]
    versions = sorted(state["version"] for state in answers)
    assert versions == list(range(1, len(answers) + 1))  # distintas, de una en una, sin huecos
    in_order = sorted(answers, key=lambda state: state["version"])
    # Activar y levantar alternan: ninguno se aplicó dos veces seguidas.
    assert [state["active"] for state in in_order] == [version % 2 == 1 for version in versions]
    assert [state["ledger_index"] for state in in_order] == sorted(
        state["ledger_index"] for state in answers
    )
    final = client.get("/api/safe-mode").json()
    assert final["version"] == len(answers)
    assert final["active"] is in_order[-1]["active"]
