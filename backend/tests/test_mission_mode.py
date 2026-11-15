"""Nivel de misión (desconexión progresiva): qué medidas se siguen esperando, firmado.

Lo que se fija aquí: que el cambio es un asiento firmado por la consola con su versión, como el
modo seguro; quién baja (cualquiera con nombre y motivo, saltando niveles) y quién sube (una
persona con nombre, un nivel cada vez); que el criterio sale del coste de medir y lo comprueba el
cargador; y, sobre todo, que **el análisis y las alertas no cambian con el nivel** (invariante 5:
se llega al 0 % de falsas alarmas apagando el sistema, y eso ya pasó). Sin red (invariante 3).
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
import json
import re
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
from app.core import mission_modes
from app.core.mission_modes import (
    LEVELS,
    MODES_PATH,
    MissionModeConflict,
    expected_measurements,
    suspended_measurements,
)
from app.core.storage import MISSION_MODE_ENTRY_TYPE, MISSION_MODE_SUBJECT
from app.ingest import codes, cost
from tests.test_api import alerting, client  # noqa: F401 — fixtures

__all__ = ["alerting", "client"]

DOWN = {"level": "minimal", "reason": "energía racionada tras el fallo de un panel",
        "declared_by": "CMO"}
APP = Path(__file__).resolve().parents[1] / "app"


def _post(client: TestClient, **body: Any) -> Any:
    return client.post("/api/mission-mode", json=body)


def _store() -> Any:
    store = routes._store
    assert store is not None
    return store


# --------------------------------------------------------------------------- #
# Quién baja y quién sube
# --------------------------------------------------------------------------- #


def test_without_entries_the_level_is_nominal_and_there_is_no_notice(client: TestClient) -> None:
    state = client.get("/api/mission-mode").json()
    assert (state["level"], state["version"], state["notice"]) == ("nominal", 0, None)
    assert state["current"]["suspended"] == []
    assert len(state["current"]["expected"]) == len(codes.CATALOG)


def test_lowering_needs_a_reason_and_a_person_with_a_name(client: TestClient) -> None:
    assert _post(client, **{**DOWN, "reason": "  "}).status_code == 422
    assert _post(client, **{**DOWN, "declared_by": "123"}).status_code == 422
    assert _post(client, **{**DOWN, "declared_by": ""}).status_code == 422
    assert client.get("/api/mission-mode").json()["version"] == 0  # nada firmado
    assert _post(client, **DOWN).status_code == 201
    assert _post(client, **DOWN).status_code == 409  # ya es mínimo
    state = client.get("/api/mission-mode").json()
    assert (state["level"], state["reason"], state["declared_by"]) == (
        "minimal", DOWN["reason"], "CMO"
    )


def test_lowering_can_skip_levels_and_raising_goes_one_level_at_a_time(
    client: TestClient,
) -> None:
    assert _post(client, **DOWN).status_code == 201  # de nominal a mínimo de una vez
    assert _post(client, level="nominal", declared_by="Comandante").status_code == 409
    assert client.get("/api/mission-mode").json()["level"] == "minimal"
    assert _post(client, level="reduced", declared_by="Comandante").status_code == 201
    assert _post(client, level="nominal", declared_by="Comandante").status_code == 201
    assert client.get("/api/mission-mode").json()["level"] == "nominal"


def test_raising_needs_a_person_but_not_a_reason(client: TestClient) -> None:
    _post(client, **{**DOWN, "level": "reduced"})
    assert _post(client, level="nominal", declared_by="  ").status_code == 422
    assert _post(client, level="nominal", declared_by="Comandante").status_code == 201
    state = client.get("/api/mission-mode").json()
    assert (state["level"], state["reason"], state["declared_by"]) == (
        "nominal", None, "Comandante"
    )


def test_an_unknown_level_or_an_extra_field_is_a_422_and_nothing_is_written(
    client: TestClient,
) -> None:
    assert _post(client, **{**DOWN, "level": "apagado"}).status_code == 422
    assert _post(client, **{**DOWN, "cited_state": "degraded"}).status_code == 422
    assert client.get("/api/audit").json()["total_entries"] == 0


def test_the_store_refuses_what_the_api_refuses(client: TestClient) -> None:
    store, me = _store(), identity_for(CONSOLE_IDENTITY)
    with pytest.raises(ValueError, match="motivo"):
        store.record_mission_mode("reduced", "", "CMO", me)
    with pytest.raises(ValueError, match="persona"):
        store.record_mission_mode("reduced", "energía", "42", me)
    with pytest.raises(ValueError, match="desconocido"):
        store.record_mission_mode("turbo", "energía", "CMO", me)
    with pytest.raises(ValueError, match="citar"):
        store.record_mission_mode("reduced", "energía", "CMO", me, cited_system="lighting")
    store.record_mission_mode("minimal", "energía", "CMO", me)
    with pytest.raises(MissionModeConflict, match="un nivel cada vez"):
        store.record_mission_mode("nominal", "", "CMO", me)
    with pytest.raises(MissionModeConflict, match="ya es"):
        store.record_mission_mode("minimal", "energía", "CMO", me)
    assert store.mission_mode()["version"] == 1


# --------------------------------------------------------------------------- #
# El asiento firmado, su versión y sus cruces
# --------------------------------------------------------------------------- #


def test_a_change_is_one_signed_entry_by_the_console_and_the_chain_verifies(
    client: TestClient,
) -> None:
    answer = _post(client, **DOWN).json()
    entries = [entry for entry in _store().ledger.entries if entry.entry_type == "mission-mode"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry.signer == CONSOLE_IDENTITY and entry.index == answer["ledger_index"]
    assert {key: value for key, value in entry.payload.items() if key != "_salt"} == {
        "subject": MISSION_MODE_SUBJECT, "level": "minimal", "reason": DOWN["reason"],
        "declared_by": "CMO",
    }
    audit = client.get("/api/audit").json()
    assert audit["integrity_ok"] is True and audit["total_entries"] == 1


def test_every_change_raises_the_version_and_every_answer_carries_it(client: TestClient) -> None:
    assert client.get("/api/mission-mode").json()["version"] == 0
    first = _post(client, **DOWN).json()
    assert (first["version"], first["level"]) == (1, "minimal")
    assert _post(client, **DOWN).status_code == 409  # rechazado: no sube
    assert client.get("/api/mission-mode").json()["version"] == 1
    second = _post(client, level="reduced", declared_by="Comandante").json()
    assert (second["version"], second["level"]) == (2, "reduced")
    now = client.get("/api/mission-mode").json()
    assert (now["version"], now["store_epoch"]) == (2, first["store_epoch"])


def test_another_store_starts_again_at_nominal_with_a_later_epoch(client: TestClient) -> None:
    before = _post(client, **DOWN).json()
    routes.reset_store(routes.new_store())
    after = client.get("/api/mission-mode").json()
    assert (after["level"], after["version"]) == ("nominal", 0)
    assert after["store_epoch"] > before["store_epoch"]


def test_two_crossed_lowerings_apply_once(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Las dos miran el nivel a la vez: una se firma y la otra choca, no las dos."""
    store = _store()
    slow_read = store.mission_mode

    def slow(until: dt.datetime | None = None) -> dict[str, Any]:
        state = slow_read(until)
        time.sleep(0.05)
        return dict(state)

    monkeypatch.setattr(store, "mission_mode", slow)
    start = threading.Barrier(2)

    def lower(_: int) -> int:
        start.wait()
        return int(_post(client, **DOWN).status_code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lower, range(2))) == [201, 409]
    monkeypatch.setattr(store, "mission_mode", slow_read)
    assert client.get("/api/mission-mode").json()["version"] == 1


def test_only_what_the_console_signed_counts(client: TestClient) -> None:
    _store()._record_action(
        MISSION_MODE_ENTRY_TYPE,
        {"subject": MISSION_MODE_SUBJECT, "level": "minimal", "reason": "x", "declared_by": "Y"},
        identity_for("otra-fuente"),
    )
    state = client.get("/api/mission-mode").json()
    assert (state["level"], state["version"]) == ("nominal", 0)


def test_a_signed_level_outside_the_vocabulary_is_a_409(client: TestClient) -> None:
    _store()._record_action(
        MISSION_MODE_ENTRY_TYPE,
        {"subject": MISSION_MODE_SUBJECT, "level": "turbo", "reason": "x", "declared_by": "Y"},
        identity_for(CONSOLE_IDENTITY),
    )
    response = client.get("/api/mission-mode")
    assert response.status_code == 409 and "nivel desconocido" in response.text


def test_an_earlier_signed_level_outside_the_vocabulary_is_also_a_409(client: TestClient) -> None:
    """No basta con mirar el último: uno malo antes contaría en la versión como un cambio."""
    _store()._record_action(
        MISSION_MODE_ENTRY_TYPE,
        {"subject": MISSION_MODE_SUBJECT, "level": "turbo", "reason": "x", "declared_by": "Y"},
        identity_for(CONSOLE_IDENTITY),
    )
    _store()._record_action(
        MISSION_MODE_ENTRY_TYPE,
        {"subject": MISSION_MODE_SUBJECT, "level": "reduced", "reason": "x", "declared_by": "Y"},
        identity_for(CONSOLE_IDENTITY),
    )
    assert client.get("/api/mission-mode").status_code == 409


@pytest.mark.parametrize("cited", [
    {"cited_system": "power"},
    {"cited_state": "degraded"},
    {"cited_system": "hiperimpulsor", "cited_state": "degraded"},
    {"cited_system": "power", "cited_state": "roto"},
])
def test_a_signed_citation_half_written_or_outside_the_vocabulary_is_a_409(
    client: TestClient, cited: dict[str, str]
) -> None:
    _store()._record_action(
        MISSION_MODE_ENTRY_TYPE,
        {"subject": MISSION_MODE_SUBJECT, "level": "reduced", "reason": "x", "declared_by": "Y",
         **cited},
        identity_for(CONSOLE_IDENTITY),
    )
    response = client.get("/api/mission-mode")
    assert response.status_code == 409 and "cita" in response.text


def test_a_malformed_entry_is_not_delivered(client: TestClient) -> None:
    _store()._record_action(
        MISSION_MODE_ENTRY_TYPE,
        {"subject": MISSION_MODE_SUBJECT, "level": "minimal", "declared_by": "Y"},
        identity_for(CONSOLE_IDENTITY),
    )
    assert client.get("/api/mission-mode").status_code == 409


def test_ground_sees_the_level_signed_up_to_its_cut(client: TestClient) -> None:
    _post(client, **DOWN)
    signed = dt.datetime.fromisoformat(client.get("/api/mission-mode").json()["since"])
    before = (signed - dt.timedelta(seconds=1)).isoformat()
    after = (signed + dt.timedelta(seconds=1)).isoformat()
    assert client.get("/api/mission-mode", params={"until": before}).json()["level"] == "nominal"
    cut = client.get("/api/mission-mode", params={"until": after}).json()
    assert (cut["level"], cut["version"]) == ("minimal", 1)
    naive = client.get("/api/mission-mode", params={"until": "2026-11-02T10:00:00"})
    assert naive.status_code == 422


# --------------------------------------------------------------------------- #
# Citar la energía o las comunicaciones
# --------------------------------------------------------------------------- #


def test_citing_power_signs_the_state_declared_at_that_moment(client: TestClient) -> None:
    assert client.post("/api/habitat/systems/status", json={
        "system": "power", "state": "degraded", "at": "2026-11-02T10:00:00+00:00",
        "declared_by": "Ingeniera de vuelo",
    }).status_code == 201
    answer = _post(client, **DOWN, cited_system="power").json()
    assert (answer["cited_system"], answer["cited_state"]) == ("power", "degraded")
    assert answer["cited_state_display"] == "degradado"
    entry = _store().ledger.entries[answer["ledger_index"]]
    assert entry.payload["cited_system"] == "power" and entry.payload["cited_state"] == "degraded"
    # Lo declarado después no reescribe lo firmado.
    client.post("/api/habitat/systems/status", json={
        "system": "power", "state": "nominal", "at": "2026-11-02T12:00:00+00:00",
        "declared_by": "Ingeniera de vuelo",
    })
    assert client.get("/api/mission-mode").json()["cited_state"] == "degraded"
    assert "Energía" in " ".join(client.get("/api/mission-mode").json()["notice"]["details"])


def test_a_module_declaration_or_nothing_declared_is_cited_as_undeclared(
    client: TestClient,
) -> None:
    assert client.post("/api/habitat/systems/status", json={
        "system": "communications", "state": "out-of-service", "module": "laboratorio",
        "at": "2026-11-02T10:00:00+00:00", "declared_by": "Ingeniera de vuelo",
    }).status_code == 201
    answer = _post(client, **DOWN, cited_system="communications").json()
    assert answer["cited_state"] == "undeclared"


def test_a_declaration_the_console_did_not_sign_is_not_cited(client: TestClient) -> None:
    _store().record_system_status(
        "power", "out-of-service", dt.datetime(2026, 11, 2, 10, tzinfo=dt.UTC), "",
        "Alguien", identity_for("otra-fuente"),
    )
    assert _post(client, **DOWN, cited_system="power").json()["cited_state"] == "undeclared"


def test_only_power_or_communications_can_be_cited(client: TestClient) -> None:
    assert _post(client, **DOWN, cited_system="lighting").status_code == 422
    assert client.get("/api/audit").json()["total_entries"] == 0
    cited = client.get("/api/mission-mode").json()["citable_systems"]
    assert [item["key"] for item in cited] == ["power", "communications"]


# --------------------------------------------------------------------------- #
# Lo que NUNCA cambia con el nivel
# --------------------------------------------------------------------------- #


def _verdict(status: dict[str, Any]) -> dict[str, Any]:
    return {key: status[key] for key in (
        "overall_level", "rules_version", "domains", "summary", "alerts",
    )} | {"observations": status["data"]["observations"]}


def test_status_and_alerts_are_identical_at_every_level(
    alerting: tuple[TestClient, dict[str, Any]],
) -> None:
    client, status = alerting
    assert status["alerts"], "el escenario de arritmia alerta"
    nominal = _verdict(status)
    assert _post(client, level="reduced", reason="energía", declared_by="CMO").status_code == 201
    assert _verdict(client.get("/api/status").json()) == nominal
    assert _post(client, **DOWN).status_code == 201
    assert _verdict(client.get("/api/status").json()) == nominal
    _post(client, level="reduced", declared_by="CMO")
    _post(client, level="nominal", declared_by="CMO")
    assert _verdict(client.get("/api/status").json()) == nominal


def test_a_suspended_measure_that_arrives_still_goes_through_the_ledger(
    client: TestClient,
) -> None:
    _post(client, **DOWN)
    assert "cortisol-salivary" in suspended_measurements("minimal")
    before = client.get("/api/audit").json()["total_entries"]
    response = client.post("/api/observations", json={"key": "cortisol-salivary", "value": 0.3})
    assert response.status_code == 201
    assert client.get("/api/audit").json()["total_entries"] == before + 1
    listed = client.get("/api/observations", params={"key": "cortisol-salivary"}).json()
    assert listed["count"] == 1


def test_safe_mode_works_the_same_at_the_minimal_level(client: TestClient) -> None:
    _post(client, **DOWN)
    on = {"active": True, "reason": "sospecha de fuga", "declared_by": "CMO"}
    assert client.post("/api/safe-mode", json=on).status_code == 201
    assert client.post("/api/safe-mode", json={"active": False, "declared_by": "CMO"}
                       ).status_code == 201


def test_nothing_that_decides_reads_the_level() -> None:
    """Ni el análisis, ni el consejo, ni la ingesta, ni el estado importan el nivel."""
    watched = [
        *sorted((APP / "analysis").glob("*.py")), *sorted((APP / "advisor").glob("*.py")),
        *sorted((APP / "ingest").glob("*.py")),
        APP / "api" / "routes.py", APP / "core" / "egress.py",
    ]
    for path in watched:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {
            *(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
              for alias in node.names),
            *(f"{node.module}.{alias.name}" for node in ast.walk(tree)
              if isinstance(node, ast.ImportFrom) and node.module for alias in node.names),
        }
        assert not any("mission_mode" in name for name in names), path


# --------------------------------------------------------------------------- #
# El criterio: del coste de medir, comprobado al cargar
# --------------------------------------------------------------------------- #


def test_each_level_expects_a_subset_of_the_one_above_and_nominal_expects_everything() -> None:
    assert expected_measurements("nominal") == frozenset(codes.CATALOG)
    assert expected_measurements("minimal") < expected_measurements("reduced")
    assert expected_measurements("reduced") < expected_measurements("nominal")
    for level in LEVELS:
        assert expected_measurements(level) | suspended_measurements(level) == set(codes.CATALOG)
        assert not expected_measurements(level) & suspended_measurements(level)


def test_the_criterion_follows_the_cost_of_measuring() -> None:
    costs, dims = cost.costs(), cost.dimensions()
    for key in expected_measurements("reduced"):
        if costs[key]["mode"] != "derived":
            assert costs[key]["mode"] in {"continuous-passive", "periodic-noninvasive"}, key
            assert dims[key]["consumables"]["value"] != "consumes", key
    added = {"symptom-burden", "pain-intensity"}
    for key in expected_measurements("minimal") - added:
        assert costs[key]["mode"] in {"continuous-passive", "derived"}, key
    for key in expected_measurements("minimal"):
        if costs[key]["mode"] == "derived":
            assert set(costs[key]["inputs"]) <= expected_measurements("minimal"), key
    # Lo que pide muestra o laboratorio solo se espera en nominal.
    for key, item in costs.items():
        if item["mode"] in {"periodic-invasive", "laboratory"}:
            assert key in suspended_measurements("reduced"), key


def _vocab(tmp_path: Path, change: Any) -> Path:
    raw = json.loads(MODES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "mission_modes.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


def _level(raw: dict[str, Any], key: str) -> dict[str, Any]:
    return next(item for item in raw["levels"] if item["key"] == key)


@pytest.mark.parametrize(("label", "change", "message"), [
    ("sin el rótulo de diseño", lambda raw: raw.update(label="protocolo de vuelo"), "se rotula"),
    ("sin base", lambda raw: raw.update(basis=" "), "base"),
    ("niveles en otro orden", lambda raw: raw["levels"].reverse(), "en ese orden"),
    ("un nivel de más", lambda raw: raw["levels"].append(
        {**copy.deepcopy(raw["levels"][-1]), "key": "apagado"}), "en ese orden"),
    ("una clase de medida que no existe",
     lambda raw: _level(raw, "reduced")["modes"].append("telepatía"), "clases de medida"),
    ("el calculado nombrado como clase",
     lambda raw: _level(raw, "reduced")["modes"].append("derived"), "clases de medida"),
    ("un consumible que no existe",
     lambda raw: _level(raw, "reduced")["consumables"].append("algo"), "consumibles"),
    ("añadir a mano una medida con muestra",
     lambda raw: _level(raw, "minimal")["also_expected"].append(
         {"key": "cortisol-salivary", "reason": "x"}), "muestra"),
    ("añadir a mano una medida que gasta consumibles",
     lambda raw: _level(raw, "minimal")["also_expected"].append(
         {"key": "onsd-left", "reason": "x"}), "consumibles"),
    ("añadir a mano una medida que no está en el catálogo",
     lambda raw: _level(raw, "minimal")["also_expected"].append(
         {"key": "telepatia", "reason": "x"}), "catálogo"),
    ("añadir a mano sin motivo",
     lambda raw: _level(raw, "minimal")["also_expected"][0].update(reason=" "), "sin motivo"),
    ("añadir a mano lo que el criterio ya espera",
     lambda raw: _level(raw, "minimal")["also_expected"].append(
         {"key": "heart-rate", "reason": "x"}), "ya lo espera"),
    ("nominal que no lo espera todo",
     lambda raw: _level(raw, "nominal")["modes"].remove("laboratory"), "nominal"),
    ("bajar que añade medidas",
     lambda raw: _level(raw, "minimal")["modes"].append("laboratory"), "añadiría"),
    ("citar un sistema que no existe",
     lambda raw: raw["citable_systems"].append("hiperimpulsor"), "citables"),
])
def test_the_loader_refuses_an_incoherent_vocabulary(
    tmp_path: Path, label: str, change: Any, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        mission_modes.load(_vocab(tmp_path, change))


def test_the_file_is_labelled_design_vocabulary_and_writes_no_watts() -> None:
    text = MODES_PATH.read_text(encoding="utf-8")
    assert json.loads(text)["label"] == "vocabulario de diseño de EMMA"
    assert not re.search(r"\d\s*(?:W|kW|Wh|kWh)\b|vatio", text)


# --------------------------------------------------------------------------- #
# El aviso: información, no una orden
# --------------------------------------------------------------------------- #


def _texts(body: dict[str, Any]) -> list[str]:
    notice = body["notice"]
    return [
        notice["title"], notice["headline"], notice["summary"], *notice["details"],
        body["rule"], body["basis"], body["not_power"], body["citable_basis"],
        *body["unchanged"], *(level["description"] for level in body["levels"]),
        *(item["why"] for item in body["current"]["expected"] + body["current"]["suspended"]),
    ]


@pytest.mark.parametrize("level", ["reduced", "minimal"])
def test_every_text_passes_the_language_guard(client: TestClient, level: str) -> None:
    _post(client, **{**DOWN, "level": level}, cited_system="power")
    for text in _texts(client.get("/api/mission-mode").json()):
        assert text_guard.check(text) == [], text


def test_the_notice_is_information_not_an_order(client: TestClient) -> None:
    """Invariante 7: el aviso dice qué se espera; no manda tomar ni dejar de tomar nada."""
    _post(client, **DOWN)
    text = " ".join(_texts(client.get("/api/mission-mode").json())).lower()
    for order in ("debe ", "tiene que", "hay que", "tome ", "deje de", "apague", "suspenda"):
        assert order not in text, order


def test_the_notice_says_what_stays_on_and_how_many_are_suspended(client: TestClient) -> None:
    _post(client, **DOWN)
    body = client.get("/api/mission-mode").json()
    notice = body["notice"]
    assert notice["title"] == "Nivel de misión mínimo"
    suspended = len(suspended_measurements("minimal"))
    assert notice["headline"].startswith(f"{suspended} de {len(codes.CATALOG)}")
    assert len(body["current"]["suspended"]) == suspended
    for piece in ("ingesta", "análisis", "riesgo", "alertas", "modo seguro"):
        assert piece in notice["summary"], piece
    assert notice["since"] == body["since"]
