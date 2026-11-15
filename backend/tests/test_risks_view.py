"""La entidad Riesgo junta (`app/risk_entity.py`, `GET /api/risks`).

Junta lo que ya existe sin calcular nada: el esquema de niveles no puede divergir del motor, la
incertidumbre no lleva número, y describir los riesgos no mueve el veredicto.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import anatomy, risk_entity
from app.advisor.countermeasures import for_domain
from app.analysis import risk
from app.analysis.risk import RiskLevel, level_for
from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.evidence.links import HRP_RISKS, evidence_for
from app.ingest.codes import CATALOG, DESCRIPTIVE_ONLY, Domain
from app.main import app


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _risks(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/risks")
    assert response.status_code == 200
    return response.json()


def _scores() -> list[float]:
    return [step / 10 for step in range(0, 1001)]


def test_there_is_one_risk_per_domain_and_it_needs_no_crew(client: TestClient) -> None:
    body = _risks(client)  # almacén vacío: no depende del estado de nadie
    assert [item["risk_id"] for item in body["risks"]] == [str(domain) for domain in Domain]
    assert body["count"] == len(Domain)


def test_each_risk_carries_the_six_fields_of_the_specification(client: TestClient) -> None:
    for item in _risks(client)["risks"]:
        domain = Domain(item["risk_id"])
        assert item["display"] == domain.display
        assert item["ridge"]["category"] == str(domain.ridge)
        assert item["ridge"]["display"] == domain.ridge.display
        assert item["ridge"]["source"]["url"].startswith("https://")
        regions = [region["key"] for region in item["human_system"]["regions"]]
        assert regions == [r.key for r in anatomy.REGIONS if domain in r.engine_domains] and regions
        assert [ref["id"] for ref in item["evidence_refs"]] == [
            ref.id for ref in evidence_for(domain)
        ]
        assert item["hrp_risk_id"] == HRP_RISKS[domain].id
        assert item["severity_schema"]["levels"]
        assert item["uncertainty"]["quantified"] is False
        # Los descriptivos no evalúan el riesgo: el estado no los lee.
        assert [entry["key"] for entry in item["indicators"]] == [
            code.key for code in CATALOG.values()
            if code.domain is domain and code.key not in DESCRIPTIVE_ONLY
        ]


def test_a_region_without_its_own_level_is_named_in_the_risk_of_its_level(
    client: TestClient,
) -> None:
    """Decimosexta ronda (§5.36.19 y §5.36.13): el hígado y los pulmones, regiones sin nivel propio,
    salen en el riesgo del dominio de su nivel (nutrición y cardiovascular) y en ningún otro,
    leído de `anatomy.py`."""
    risks = {item["risk_id"]: item for item in _risks(client)["risks"]}
    without_level = [region for region in anatomy.REGIONS if region.level_of is not None]
    assert [region.key for region in without_level] == ["lungs", "liver"]
    for region in without_level:
        assert region.level_of is not None
        level_of = str(region.level_of)
        for risk_id, item in risks.items():
            named = {entry["key"]: entry for entry in item["human_system"]["regions"]}
            assert (region.key in named) is (risk_id == level_of), (region.key, risk_id)
        named = {entry["key"]: entry for entry in risks[level_of]["human_system"]["regions"]}
        # La región propia del dominio va también, y la sin nivel dice de quién es su nivel.
        assert anatomy.HOME_REGIONS[region.key].key in named
        assert named[region.key]["level_of"] == level_of
        assert named[region.key]["level_note"] == (
            f"El nivel es del dominio {region.level_of.display}."
        )
        assert named[region.key]["domains"] == []
    nutrition = {
        entry["key"]: entry for entry in risks[str(Domain.NUTRITION)]["human_system"]["regions"]
    }
    assert list(nutrition) == ["digestive", "liver"]
    assert nutrition["liver"]["level_note"] == "El nivel es del dominio nutrición."


def test_each_region_of_a_risk_carries_the_cards_its_phrase_names(client: TestClient) -> None:
    """Decimoséptima ronda (§5.36.9, «Queda»): bajo la frase de cada región, en «Sistema humano»,
    van las fichas que nombra —el riesgo de cálculos en la vejiga, MedlinePlus en el hígado y el
    NHLBI en los pulmones—, con la forma de toda cita (`registry.cite`) y leídas de la región."""
    risks = {item["risk_id"]: item for item in _risks(client)["risks"]}
    by_key = {region.key: region for region in anatomy.REGIONS}
    for item in risks.values():
        for entry in item["human_system"]["regions"]:
            region = by_key[entry["key"]]
            assert entry["note_refs"] == [ref.to_dict() for ref in region.note_refs]
            assert entry["analytes_source"] == (
                region.analytes_source.to_dict() if region.analytes_source is not None else None
            )
            # La capa de investigación del hígado no es de la frase: no viaja con el riesgo.
            assert "research" not in entry
            # Ni para qué sirve el órgano (vigésima ronda): es del mapa y de la cadena.
            assert not {"function", "function_refs", "function_note"} & set(entry)
    named = {
        entry["key"]: [ref["id"] for ref in entry["note_refs"]] + (
            [entry["analytes_source"]["id"]] if entry["analytes_source"] is not None else []
        )
        for item in risks.values() for entry in item["human_system"]["regions"]
    }
    assert named["bladder"] == ["hrp-renal-stone-evidence-report"]
    assert named["liver"] == ["medlineplus-liver-function-tests"]
    assert named["lungs"] == ["nhlbi-respiratory-failure"]
    assert named["heart"] == [] and named["digestive"] == []
    # La ficha con su relevancia y su salvedad, como en el resto de EMMA.
    [stone] = next(
        entry for entry in risks[str(Domain.GENITOURINARY)]["human_system"]["regions"]
        if entry["key"] == "bladder"
    )["note_refs"]
    assert {"relevance", "scope_caveat", "scope_in_view", "grade"} <= set(stone)
    assert "Bajo la frase de una región van las fichas" in (
        risks[str(Domain.NUTRITION)]["human_system"]["basis"]
    )


def test_the_published_schema_classifies_every_score_like_the_engine(
    client: TestClient,
) -> None:
    schema = _risks(client)["severity_schema"]
    for score in _scores():
        assert risk_entity.level_from_schema(schema, score) == str(level_for(score)), score


def test_the_schema_is_read_from_the_engine_not_copied(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _risks(client)["severity_schema"]
    moved = ((71.0, RiskLevel.CRITICAL), *risk._LEVEL_THRESHOLDS[1:])
    monkeypatch.setattr(risk, "_LEVEL_THRESHOLDS", moved)
    after = _risks(client)["severity_schema"]
    critical = next(item for item in after["levels"] if item["level"] == "critical")
    assert critical["min_score"] == 71.0
    assert before != after
    for score in _scores():
        assert risk_entity.level_from_schema(after, score) == str(level_for(score)), score


def test_the_levels_come_named_by_the_engine_and_in_order(client: TestClient) -> None:
    levels = _risks(client)["severity_schema"]["levels"]
    assert [item["level"] for item in levels] == [str(level) for level in RiskLevel]
    for item in levels:
        level = RiskLevel(item["level"])
        assert (item["display"], item["label"]) == (level.display, level.label)
    assert [item["min_score"] is None for item in levels] == [True, False, False, False]
    floors = [item["min_score"] for item in levels[1:]]
    assert floors == sorted(floors)


def test_uncertainty_is_never_a_number(client: TestClient) -> None:
    body = _risks(client)
    assert "no cuantifica la incertidumbre" in body["uncertainty_statement"]
    forbidden = {"probability", "confidence", "interval", "p", "likelihood", "score"}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            assert not forbidden & value.keys(), value.keys()
            for inner in value.values():
                walk(inner)
        elif isinstance(value, list):
            for inner in value:
                walk(inner)

    for item in body["risks"]:
        block = item["uncertainty"]
        assert block["statement"] == body["uncertainty_statement"]
        walk(block)


def test_uncertainty_says_what_the_registry_says_of_each_reference(client: TestClient) -> None:
    for item in _risks(client)["risks"]:
        domain = Domain(item["risk_id"])
        cited = [ref.to_dict() for ref in evidence_for(domain)]
        block = item["uncertainty"]["evidence"]
        assert block["count"] == len(cited)
        assert [ref["grade"] for ref in block["references"]] == [
            ref["grade"]["label"] for ref in cited
        ]
        assert [ref["unverified"] for ref in block["references"]] == [
            ref["unverified"] for ref in cited
        ]
        assert block["unverified_fields"] == sum(len(ref["unverified"]) for ref in cited)
        assert block["preclinical"] == sum(1 for ref in cited if ref["grade"]["preclinical"])
        assert sum(row["count"] for row in block["by_grade"]) == len(cited)
    immune = next(i for i in _risks(client)["risks"] if i["risk_id"] == "immune")
    # OSD-288 es de ratón: el riesgo inmune lo tiene que decir.
    assert immune["uncertainty"]["evidence"]["preclinical"] >= 1


def test_uncertainty_counts_the_demo_countermeasures(client: TestClient) -> None:
    for item in _risks(client)["risks"]:
        found = for_domain(Domain(item["risk_id"]))
        block = item["uncertainty"]["countermeasures"]
        assert block["count"] == len(found)
        assert block["demo"] == sum(1 for entry in found if entry.basis == "demo")
        assert sum(row["count"] for row in block["by_basis"]) == len(found)


def test_evaluation_tells_measured_from_calculated_from_none() -> None:
    keys = [code.key for code in CATALOG.values() if code.domain is Domain.RADIATION]
    real = risk_entity.evaluation(
        Domain.RADIATION, {key: "laboratory" for key in keys} | {"cumulative-dose": "derived"}
    )
    assert real["evaluated_with"] == "measured"
    assert real["calculated"] == ["cumulative-dose"]
    assert real["measured"] == len(keys) - 1 and real["indicators"] == len(keys)
    only = risk_entity.evaluation(Domain.RADIATION, {key: "derived" for key in keys})
    assert only["evaluated_with"] == "calculated-only" and only["measured"] == 0
    assert only["evaluated_with_display"] == risk_entity.EVALUATED_WITH["calculated-only"]


def test_a_domain_without_indicators_says_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(risk_entity, "evaluated_by_domain", lambda domain: ())
    empty = risk_entity.evaluation(Domain.BONE, {})
    assert empty["evaluated_with"] == "none" and empty["indicators"] == 0
    assert "ningún indicador" in empty["evaluated_with_display"]


def test_only_the_bone_risk_declares_an_inferred_state(client: TestClient) -> None:
    for item in _risks(client)["risks"]:
        states = item["uncertainty"]["evaluation"]["inferred_states"]
        if item["risk_id"] == "bone":
            assert [state["observation_type"] for state in states] == ["inferred"]
            assert states[0]["model_version"] and "no entra" in states[0]["note"]
        else:
            assert states == []


def test_describing_the_risks_does_not_move_the_verdict(client: TestClient) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "progressive-insomnia", "days": 30}
    ).status_code == 201

    def verdict() -> tuple[Any, ...]:
        body = client.get("/api/status").json()
        return (
            body["overall_level"],
            {key: (value["level"], value["score"]) for key, value in body["domains"].items()},
            body["alerts"],
            body["rules_version"],
        )

    before = verdict()
    assert before[0] != "nominal"
    _risks(client)
    assert verdict() == before


def test_unverified_fields_are_counted_even_when_the_registry_has_none_today() -> None:
    # Hoy todas las fichas citadas por un riesgo están completas, y con ellas un recuento que
    # devolviera siempre cero pasaba (lo cazó la campaña de mutantes en la decimocuarta ronda).
    ref = {
        "id": "ficha-a-medias", "title": "Ficha a medias",
        "grade": {"label": "desconocido", "tier": "desconocido", "preclinical": False},
        "unverified": ["date", "doi"], "unverified_display": ["fecha", "DOI"],
    }
    block = risk_entity.evidence_strength([ref])
    assert block["unverified_fields"] == 2
    assert block["references"][0]["unverified_display"] == ["fecha", "DOI"]
