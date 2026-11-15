"""El marco de NASA y las hipótesis de diseño H1-H7 en `/api/framework`.

Lo que vigilan estas pruebas es que el inventario no afirme más de lo que hay: que el enunciado
de cada hipótesis sea el de la base de conocimiento, que ninguna figure como probada, que cada
módulo, ruta, escenario y documento citados existan de verdad, y que un anclaje que nadie ha
leído no aparezca descrito. Y que nada de esto mueva el veredicto del motor (invariante 5).
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.evidence import design_hypotheses, nasa_framework, registry
from app.ingest.codes import Domain
from app.ingest.simulator import Scenario
from app.main import app

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
KNOWLEDGE_BASE = REPO / "docs" / "contexto" / "knowledge-base-v1.md"
SPECIFICATION = REPO / "docs" / "contexto" / "especificacion-tecnica-v1.1.md"
EVIDENCE_REFS = BACKEND / "app" / "data" / "evidence_refs.json"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


@pytest.fixture
def raw() -> dict[str, Any]:
    """Una copia del fichero, para estropearla sin tocar la que está en caché."""
    return copy.deepcopy(json.loads(design_hypotheses.HYPOTHESES_PATH.read_text("utf-8")))


def _hypotheses() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = design_hypotheses.payload()["hypotheses"]
    return items


# --------------------------------------------------------------------------- #
# El enunciado es el del equipo, y ninguna figura como probada
# --------------------------------------------------------------------------- #


def test_each_statement_is_the_literal_one_of_the_knowledge_base() -> None:
    """Copiadas de §13 sin retocar: si el inventario las reescribe, deja de ser su hipótesis."""
    text = KNOWLEDGE_BASE.read_text(encoding="utf-8")
    section = text.split("# 13. Hipótesis prioritarias que deben probarse")[1].split("\n# ")[0]
    written = dict(re.findall(r"^- (H\d)\. (.+)$", section, flags=re.MULTILINE))

    assert len(written) == 7
    served = {item["label"]: item["statement"] for item in _hypotheses()}
    assert served == written


def test_the_seven_come_in_order_and_with_a_prefix_that_is_not_a_hazard_id() -> None:
    """«H1…H18» a secas son los peligros del expediente de riesgos: aquí llevan `KB-`."""
    ids = [item["id"] for item in _hypotheses()]
    assert ids == [f"KB-H{number}" for number in range(1, 8)]


def test_no_hypothesis_is_presented_as_proven() -> None:
    assert not {"proven", "probada", "validated", "demonstrated"} & set(design_hypotheses.STATUSES)
    for text in design_hypotheses.STATUSES.values():
        assert text.startswith("hipótesis")
    for item in _hypotheses():
        assert item["status"] in design_hypotheses.STATUSES
        assert item["status_text"] == design_hypotheses.STATUSES[item["status"]]
        # Lo que EMMA no demuestra va siempre, también en la que tiene datos reales.
        assert item["not_demonstrated"].strip()


def test_real_data_is_declared_with_its_scope_and_only_where_there_is_some() -> None:
    """MMASH son 22 personas sanas en Tierra: quien lo cite tiene que decirlo."""
    for item in _hypotheses():
        if item["status"] == design_hypotheses.REAL_DATA_STATUS:
            assert "22 personas sanas" in item["real_data"]
            assert "en Tierra" in item["real_data"]
            assert "No es fisiología de vuelo" in item["real_data"]
        else:
            assert item["real_data"] is None


# --------------------------------------------------------------------------- #
# Lo que se cita existe
# --------------------------------------------------------------------------- #


def test_every_cited_module_exists() -> None:
    """Un módulo que se movió o se borró no puede seguir figurando como pieza de una hipótesis."""
    cited = {touch["module"] for item in _hypotheses() for touch in item["touches"]}
    assert cited
    for module in sorted(cited):
        assert importlib.util.find_spec(module) is not None, module


def test_a_module_that_does_not_exist_is_caught() -> None:
    """La comprobación de arriba distingue: con un nombre inventado, no encuentra nada."""
    with pytest.raises(ModuleNotFoundError):
        importlib.util.find_spec("app.analysis_que_no_existe.inferred")
    assert importlib.util.find_spec("app.analysis.modulo_que_no_existe") is None


def test_every_cited_route_is_served_with_that_method() -> None:
    served = {
        (method.upper(), path)
        for path, methods in app.openapi()["paths"].items()
        for method in methods
    }
    assert ("GET", "/api/ruta-que-no-existe") not in served
    cited = {
        (touch["method"], touch["route"])
        for item in _hypotheses()
        for touch in item["touches"]
        if touch["route"] is not None
    }
    assert cited
    assert cited <= served, sorted(cited - served)


def test_every_cited_scenario_and_document_exists() -> None:
    scenarios = {str(item) for item in Scenario}
    for item in _hypotheses():
        if item["scenario"] is not None:
            assert item["scenario"] in scenarios
        for document in item["documents"]:
            assert (REPO / document).is_file(), document
    source = design_hypotheses.payload()["source"]
    assert (REPO / source["document"]).is_file()


# --------------------------------------------------------------------------- #
# La arquitectura CDSS de ExMC: anclaje de la especificación, leído el 2026-10-13
# --------------------------------------------------------------------------- #

CDSS_ANCHOR = {
    "anchor": "ExMC CDSS architecture",
    "listed_in": "docs/contexto/especificacion-tecnica-v1.1.md §16 y §17",
    "references": [
        {
            "ntrs": "20220017869",
            "title": "Exploration Medical Capability CDSS Architecture Recommendation",
            "url": "https://ntrs.nasa.gov/citations/20220017869",
        },
        {
            "ntrs": "20160012678",
            "title": "Exploration Clinical Decision Support System: Medical Data Architecture",
            "url": "https://ntrs.nasa.gov/citations/20160012678",
        },
        {
            "ntrs": "20205008731",
            "title": "Clinical Decision Support – Concepts of Operation",
            "url": "https://ntrs.nasa.gov/citations/20205008731",
        },
    ],
}


def test_the_cdss_anchor_was_read_and_left_the_unread_list() -> None:
    """Las dos cosas a la vez: en el registro y leídas, y fuera de «sin leer»."""
    assert design_hypotheses.payload()["unread_anchors"] == []

    specification = SPECIFICATION.read_text(encoding="utf-8")
    assert f"| {CDSS_ANCHOR['anchor']} |" in specification
    read = nasa_framework.payload()
    declared = {source["ref"]: source for source in read["sources"]}
    cited = {item["ref"] for block in read["blocks"] for item in block["statements"]}
    for reference in CDSS_ANCHOR["references"]:
        # Título y dirección tal como los da §17, pegados como allí.
        assert f"- NASA NTRS – {reference['title']}{reference['url']}" in specification
        ref = registry.get(f"ntrs-{reference['ntrs']}")
        assert ref.url == reference["url"]
        # Leída no es «está en el registro»: tiene alcance declarado y alguna frase citada.
        assert declared[ref.id]["extent"] in nasa_framework.EXTENTS
        assert ref.id in cited


def test_h1_says_what_was_read_and_still_does_not_claim_the_gap() -> None:
    h1 = _hypotheses()[0]
    assert h1["status"] == "architecture"
    text = h1["not_demonstrated"]
    assert "sin leer" in text and "HRP-48033" in text
    assert "Med07 como cerrado" in text and "Medical-701" in text
    assert "haber leído los documentos no la prueba" in text
    assert "están sin leer" not in text


def test_an_anchor_nobody_read_still_says_so(
    raw: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """La lista está vacía hoy; el mecanismo sigue: un anclaje sin leer se sirve como tal."""
    raw["unread_anchors"] = [copy.deepcopy(CDSS_ANCHOR)]
    monkeypatch.setattr(design_hypotheses, "inventory", lambda: design_hypotheses.validate(raw))

    anchor = design_hypotheses.payload()["unread_anchors"][0]
    assert anchor["status_text"] == "sin leer: no está en el registro de evidencia de EMMA"
    assert set(anchor) == {"anchor", "listed_in", "status", "status_text", "references"}


def test_an_unread_anchor_is_not_in_the_evidence_registry_and_is_not_described() -> None:
    """Si alguien las lee y las registra, este inventario tiene que dejar de decir «sin leer»."""
    registry = EVIDENCE_REFS.read_text(encoding="utf-8")
    for anchor in design_hypotheses.payload()["unread_anchors"]:
        # Solo identificación: ningún campo que resuma lo que dice un documento no leído.
        assert set(anchor) == {"anchor", "listed_in", "status", "status_text", "references"}
        for reference in anchor["references"]:
            assert set(reference) == {"ntrs", "title", "url"}
            assert reference["ntrs"] not in registry


# --------------------------------------------------------------------------- #
# La carga rechaza un inventario que afirme de más o calle lo que falta
# --------------------------------------------------------------------------- #


def test_the_file_as_shipped_is_valid(raw: dict[str, Any]) -> None:
    assert design_hypotheses.validate(raw) is raw


def test_a_status_outside_the_vocabulary_is_rejected(raw: dict[str, Any]) -> None:
    raw["hypotheses"][1]["status"] = "proven"
    with pytest.raises(ValueError, match="estado desconocido"):
        design_hypotheses.validate(raw)


def test_a_hypothesis_without_what_emma_does_not_demonstrate_is_rejected(
    raw: dict[str, Any],
) -> None:
    raw["hypotheses"][3]["not_demonstrated"] = "  "
    with pytest.raises(ValueError, match="no demuestra"):
        design_hypotheses.validate(raw)


def test_real_data_without_scope_or_scope_without_real_data_is_rejected(
    raw: dict[str, Any],
) -> None:
    missing = copy.deepcopy(raw)
    del missing["hypotheses"][1]["real_data"]
    with pytest.raises(ValueError, match="datos reales"):
        design_hypotheses.validate(missing)

    raw["hypotheses"][3]["real_data"] = "datos de vuelo"
    with pytest.raises(ValueError, match="datos reales"):
        design_hypotheses.validate(raw)


def test_a_missing_reordered_or_unprefixed_hypothesis_is_rejected(raw: dict[str, Any]) -> None:
    dropped = copy.deepcopy(raw)
    dropped["hypotheses"].pop()
    with pytest.raises(ValueError, match="se esperaban"):
        design_hypotheses.validate(dropped)

    raw["hypotheses"][0]["id"] = "H1"
    with pytest.raises(ValueError, match="se esperaban"):
        design_hypotheses.validate(raw)


def test_a_hypothesis_with_no_piece_cannot_claim_a_piece(raw: dict[str, Any]) -> None:
    raw["hypotheses"][4]["touches"] = []
    with pytest.raises(ValueError, match="sin ninguna pieza"):
        design_hypotheses.validate(raw)


def test_a_touch_outside_emma_or_without_explanation_is_rejected(raw: dict[str, Any]) -> None:
    foreign = copy.deepcopy(raw)
    foreign["hypotheses"][0]["touches"][0]["module"] = "polaris.tools.borde"
    with pytest.raises(ValueError, match="no es un módulo de EMMA"):
        design_hypotheses.validate(foreign)

    raw["hypotheses"][0]["touches"][0]["what"] = ""
    with pytest.raises(ValueError, match="no dice qué hace"):
        design_hypotheses.validate(raw)


# --------------------------------------------------------------------------- #
# La ruta
# --------------------------------------------------------------------------- #


def test_framework_serves_the_frame_and_the_seven_hypotheses(client: TestClient) -> None:
    body = client.get("/api/framework").json()

    assert set(body["exmc_gaps"]) >= {"source", "url", "med07", "med10"}
    for gap in ("med07", "med10"):
        assert body["exmc_gaps"][gap]["gap"] and body["exmc_gaps"][gap]["emma"]
    assert body["imm"]["not_duplicated"]
    assert set(body["ridge"]) == {str(domain) for domain in Domain}

    served = body["design_hypotheses"]
    assert served == design_hypotheses.payload()
    assert [item["label"] for item in served["hypotheses"]] == [f"H{n}" for n in range(1, 8)]
    assert all(item["status_text"] for item in served["hypotheses"])
    assert body["read_sources"] == nasa_framework.payload()


# --------------------------------------------------------------------------- #
# Invariante 5: es un inventario, no entra en el análisis
# --------------------------------------------------------------------------- #


def _verdict(client: TestClient) -> dict[str, Any]:
    status = client.get("/api/status").json()
    return {
        "overall": status["overall_level"],
        "domains": status["domains"],
        "alerts": status["alerts"],
        "recommendations": status["recommendations"],
    }


@pytest.mark.parametrize("scenario", ["nominal", "spe-event", "menu-fatigue"])
def test_the_engine_verdict_is_the_same_with_and_without_the_inventory(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": scenario, "days": 40}
    ).status_code == 201

    monkeypatch.setattr(design_hypotheses, "payload", lambda: {})
    without = _verdict(client)
    monkeypatch.undo()

    assert client.get("/api/framework").json()["design_hypotheses"]["hypotheses"]
    assert _verdict(client) == without


def test_nothing_that_decides_reads_the_inventory() -> None:
    """Análisis, recomendaciones, ingesta, entorno y validación no lo importan."""
    for package in ("analysis", "advisor", "ingest", "environment", "validation", "core"):
        for path in (BACKEND / "app" / package).rglob("*.py"):
            assert "design_hypotheses" not in path.read_text(encoding="utf-8"), path
