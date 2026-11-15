"""El entorno de la misión, declarado en marcha: un asiento firmado, y sigue siendo descriptivo.

Lo que se fija aquí (petición del usuario, 2026-11-04: «poder elegir el entorno»): que la
configuración da el de partida y cada cambio es un asiento firmado por la consola, con el patrón
del nivel de misión (versión, corte de Tierra, asientos inservibles en 409); que el estado, la
matriz y la crónica siguen al entorno declarado; y, sobre todo, que **declarar otro entorno no
mueve ningún nivel, puntuación ni alerta** más allá de hacia qué cuerpo se calcula el tiempo de
luz (decisión del usuario del 2026-11-11; `tests/test_mission_profile.py`) (invariante 5). Sin
red (invariante 3).
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import text_guard
from app.api import routes
from app.api.routes import CONSOLE_IDENTITY, identity_for
from app.core import mission_profile_changes
from app.core.storage import MISSION_PROFILE_ENTRY_TYPE, MISSION_PROFILE_SUBJECT
from tests.test_api import alerting, client  # noqa: F401 — fixtures

__all__ = ["alerting", "client"]

LEO = {"profile": "leo", "reason": "regreso a la estación", "declared_by": "CMO"}
APP = Path(__file__).resolve().parents[1] / "app"


def _post(client: TestClient, **body: Any) -> Any:
    return client.post("/api/mission/profile", json=body)


def _store() -> Any:
    store = routes._store
    assert store is not None
    return store


def _sign(**payload: str) -> None:
    _store()._record_action(
        MISSION_PROFILE_ENTRY_TYPE,
        {"subject": MISSION_PROFILE_SUBJECT, "reason": "", "declared_by": "Y", **payload},
        identity_for(CONSOLE_IDENTITY),
    )


# --------------------------------------------------------------------------- #
# De partida, la configuración; después, lo firmado
# --------------------------------------------------------------------------- #


def test_without_entries_the_profile_is_the_configured_one(client: TestClient) -> None:
    state = client.get("/api/mission/profile").json()
    assert (state["id"], state["source"], state["version"]) == ("mars-transit", "configuración", 0)
    assert state["declared_by"] is None and "configuración" in state["source_text"]
    assert [item["id"] for item in state["profiles"]] == [
        "leo", "cislunar", "lunar-surface", "mars-transit", "mars-surface",
    ]


def test_a_change_is_one_signed_entry_by_the_console_with_what_it_left_behind(
    client: TestClient,
) -> None:
    answer = _post(client, **LEO)
    assert answer.status_code == 201, answer.text
    body = answer.json()
    assert (body["id"], body["source"], body["version"], body["previous"]) == (
        "leo", "registro", 1, "mars-transit"
    )
    entries = [e for e in _store().ledger.entries if e.entry_type == MISSION_PROFILE_ENTRY_TYPE]
    assert len(entries) == 1
    entry = entries[0]
    assert entry.signer == CONSOLE_IDENTITY and entry.index == body["ledger_index"]
    assert {key: value for key, value in entry.payload.items() if key != "_salt"} == {
        "subject": MISSION_PROFILE_SUBJECT, "profile": "leo", "previous": "mars-transit",
        "reason": LEO["reason"], "declared_by": "CMO",
    }
    audit = client.get("/api/audit").json()
    assert audit["integrity_ok"] is True and audit["total_entries"] == 1
    state = client.get("/api/mission/profile").json()
    assert (state["id"], state["declared_by"], state["reason"]) == ("leo", "CMO", LEO["reason"])
    assert f"asiento {body['ledger_index']}" in state["source_text"]


def test_redeclaring_the_current_one_is_a_409_and_an_unknown_one_a_422(
    client: TestClient,
) -> None:
    assert _post(client, **{**LEO, "profile": "mars-transit"}).status_code == 409  # el de partida
    assert _post(client, **{**LEO, "profile": "jupiter"}).status_code == 422
    assert _post(client, **{**LEO, "declared_by": "123"}).status_code == 422
    assert _post(client, **{**LEO, "declared_by": ""}).status_code == 422
    assert _post(client, **{**LEO, "previous": "leo"}).status_code == 422  # lo pone el almacén
    assert _post(client, **{**LEO, "reason": "x" * 301}).status_code == 422
    assert client.get("/api/audit").json()["total_entries"] == 0
    assert _post(client, **LEO).status_code == 201
    assert _post(client, **LEO).status_code == 409
    # El motivo es opcional.
    assert _post(client, profile="mars-surface", declared_by="CMO").status_code == 201
    assert client.get("/api/mission/profile").json()["version"] == 2


def test_the_store_refuses_what_the_api_refuses(client: TestClient) -> None:
    store, me = _store(), identity_for(CONSOLE_IDENTITY)
    with pytest.raises(ValueError, match="desconocido"):
        store.record_mission_profile("jupiter", "", "CMO", me, "mars-transit")
    with pytest.raises(ValueError, match="persona"):
        store.record_mission_profile("leo", "", "42", me, "mars-transit")
    with pytest.raises(mission_profile_changes.MissionProfileConflict):
        store.record_mission_profile("leo", "", "CMO", me, "leo")


def test_two_crossed_declarations_apply_once(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Las dos miran el entorno a la vez: una se firma y la otra choca, no las dos."""
    store = _store()
    slow_read = store.mission_profile

    def slow(until: dt.datetime | None, configured: str) -> dict[str, Any]:
        state = slow_read(until, configured)
        time.sleep(0.05)
        return dict(state)

    monkeypatch.setattr(store, "mission_profile", slow)
    start = threading.Barrier(2)

    def declare(_: int) -> int:
        start.wait()
        return int(_post(client, **LEO).status_code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(declare, range(2))) == [201, 409]
    monkeypatch.setattr(store, "mission_profile", slow_read)
    assert client.get("/api/mission/profile").json()["version"] == 1


def test_only_what_the_console_signed_counts(client: TestClient) -> None:
    _store()._record_action(
        MISSION_PROFILE_ENTRY_TYPE,
        {"subject": MISSION_PROFILE_SUBJECT, "profile": "leo", "previous": "mars-transit",
         "reason": "", "declared_by": "Y"},
        identity_for("otra-fuente"),
    )
    state = client.get("/api/mission/profile").json()
    assert (state["id"], state["version"]) == ("mars-transit", 0)


@pytest.mark.parametrize(("payload", "problem"), [
    ({"profile": "jupiter", "previous": "mars-transit"}, "entorno desconocido"),
    ({"profile": "leo", "previous": "leo"}, "mismo que dejaba atrás"),
])
def test_a_signed_entry_the_api_would_not_accept_is_a_409(
    client: TestClient, payload: dict[str, str], problem: str
) -> None:
    _sign(**payload)
    _sign(profile="cislunar", previous="leo")  # uno bueno después no lo tapa
    for path in ("/api/mission/profile", "/api/mission/profiles", "/api/timeline/chronicle"):
        response = client.get(path)
        assert response.status_code == 409, path
    assert problem in client.get("/api/mission/profile").text


def test_a_malformed_entry_is_not_delivered(client: TestClient) -> None:
    _store()._record_action(
        MISSION_PROFILE_ENTRY_TYPE,
        {"subject": MISSION_PROFILE_SUBJECT, "profile": "leo", "declared_by": "Y"},
        identity_for(CONSOLE_IDENTITY),
    )
    assert client.get("/api/mission/profile").status_code == 409


def test_ground_sees_the_profile_signed_up_to_its_cut(client: TestClient) -> None:
    _post(client, **LEO)
    signed = dt.datetime.fromisoformat(client.get("/api/mission/profile").json()["since"])
    before = (signed - dt.timedelta(seconds=1)).isoformat()
    after = (signed + dt.timedelta(seconds=1)).isoformat()
    early = client.get("/api/mission/profile", params={"until": before}).json()
    assert (early["id"], early["version"]) == ("mars-transit", 0)
    cut = client.get("/api/mission/profile", params={"until": after}).json()
    assert (cut["id"], cut["version"]) == ("leo", 1)
    matrix = client.get("/api/mission/profiles", params={"until": before}).json()
    assert matrix["declared_id"] == "mars-transit"
    for path in ("/api/mission/profile", "/api/mission/profiles"):
        assert client.get(path, params={"until": "2026-11-02T10:00:00"}).status_code == 422


# --------------------------------------------------------------------------- #
# Lo que sigue al entorno declarado
# --------------------------------------------------------------------------- #


def test_the_matrix_and_the_chronicle_follow_the_declared_profile(client: TestClient) -> None:
    assert client.get("/api/mission/profiles").json()["declared_id"] == "mars-transit"
    _post(client, **LEO)
    matrix = client.get("/api/mission/profiles").json()
    assert matrix["declared_id"] == "leo"
    assert [p["id"] for p in matrix["profiles"] if p["declared"]] == ["leo"]
    assert "asiento firmado" in matrix["declared_note"]
    chronicle = client.get("/api/timeline/chronicle").json()
    facts = [event for event in chronicle["events"] if event["fact"] == "mission-profile-change"]
    assert len(facts) == 1
    assert facts[0]["tipo"] == "sistema" and facts[0]["quien"] == "CMO"
    assert "de tránsito a Marte a órbita baja" in facts[0]["que"]
    assert "regreso a la estación" in facts[0]["que"]


def _without_profile(status: dict[str, Any]) -> dict[str, Any]:
    """El estado sin lo que sigue al perfil: su bloque y la cobertura de efemérides, que desde el
    2026-11-11 es la de su objetivo (null sin objetivo), y la capacidad «retardo con Tierra» de la
    vigilancia, que sin objetivo no se pierde (no es un fallo). También `comms_status`, que dice
    del retardo «no aplica» sin objetivo y «sin efemérides» con él y sin dato: solo lo describe."""
    trimmed = copy.deepcopy(status)
    trimmed["mission"].pop("profile")
    trimmed["mission"].pop("ephemeris_coverage")
    trimmed.pop("monitoring")
    trimmed.pop("comms_status")
    return trimmed


def test_status_levels_and_alerts_are_identical_before_and_after_a_declared_change(
    alerting: tuple[TestClient, dict[str, Any]],
) -> None:
    client, status = alerting
    assert status["alerts"], "el escenario de arritmia alerta"
    assert status["mission"]["profile"]["id"] == "mars-transit"
    assert status["mission"]["profile"]["declaration"]["source"] == "configuración"
    reference = _without_profile(client.get("/api/status").json())
    # Sin red y sin caché no hay tiempo de luz de Marte: el factor ya es 1, y lo único que el
    # perfil mueve desde el 2026-11-11 (el objetivo de efemérides) no cambia nada aquí. Que con
    # tiempo de luz sí lo cambie, y solo eso, lo fija `tests/test_mission_profile.py`.
    assert reference["isolation_factor"] == 1.0
    for profile in ("leo", "lunar-surface", "mars-surface", "mars-transit"):
        assert _post(client, profile=profile, declared_by="CMO").status_code == 201
        now = client.get("/api/status").json()
        served = now["mission"]["profile"]
        assert served["id"] == profile and served["declaration"]["source"] == "registro"
        without_target = profile in ("leo", "lunar-surface")
        assert (now["mission"]["ephemeris_coverage"] is None) == without_target
        # Todo lo demás —niveles, puntuaciones, alertas, recomendaciones, factor de
        # aislamiento, versión de reglas— es idéntico: el entorno solo cambia su bloque.
        assert _without_profile(now) == reference


def test_nothing_that_decides_reads_the_declaration() -> None:
    """Ni el análisis ni el consejo importan el entorno declarado ni sus reglas."""
    watched = [*sorted((APP / "analysis").glob("*.py")), *sorted((APP / "advisor").glob("*.py"))]
    assert watched
    for module in watched:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        names = {
            alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
            for alias in node.names
        } | {
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        assert not {name for name in names if "mission_profile" in name}, module.name


def test_every_text_passes_the_language_guard(client: TestClient) -> None:
    _post(client, **LEO)
    state = client.get("/api/mission/profile").json()
    for text in (state["rule"], state["descriptive"], state["source_text"]):
        text_guard.check(text)
    text_guard.check(mission_profile_changes.chronicle_sentence(
        {"profile": "leo", "previous": "mars-transit", "reason": ""}
    ))
