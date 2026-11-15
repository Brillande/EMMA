"""El comité de verificadores en un dosier (`paso_consolidacion.consolidar` de Polaris). Sin red."""

from __future__ import annotations

import respx
from fastapi.testclient import TestClient

from app import committee_dossier
from tests.test_interpret import GOOD_DRAFT, LLM, SUPPORTED, chat


def _objection(model: str, reason: str, quote: str = "", counted: bool = False) -> dict:  # type: ignore[type-arg]
    return {"model": model, "quote": quote, "reason": reason, "counted": counted}


def test_counted_objections_lead_and_uncited_ones_are_flagged_untraceable() -> None:
    found = committee_dossier.dossier({
        "committee": ["a", "b"],
        "objections": [
            _objection("a", "sin cita válida"),
            _objection("b", "cifra inventada", "mide 7,2 mm", counted=True),
        ],
    })
    assert found is not None
    assert [item["impact"] for item in found["head"]] == ["critica", "media"]
    assert found["head"][0]["source"] == "mide 7,2 mm"
    assert found["head"][1]["source"] == "?"
    assert found["untraceable"] is True
    assert any("SIN fuente" in warning for warning in found["warnings"])


def test_deterministic_barriers_enter_and_verifier_reasons_are_not_duplicated() -> None:
    found = committee_dossier.dossier({
        "objections": [_objection("a", "sin base", "medida a 3 mm", counted=True)],
        "reasons": ["cifra que no está en los hechos: 7,2", "el verificador a objeta «medida»"],
    })
    assert found is not None
    titles = [item["title"] for item in found["head"]]
    assert "cifra que no está en los hechos: 7,2" in titles
    assert not any(title.startswith("el verificador") for title in titles)


def test_above_the_cap_goes_to_deferred_never_dropped() -> None:
    many = [_objection("a", f"motivo {n}", f"cita número {n}", counted=True) for n in range(9)]
    found = committee_dossier.dossier({"objections": many})
    assert found is not None
    assert len(found["head"]) + len(found["deferred"]) == 9 and found["deferred"]


def test_a_draft_from_before_has_no_dossier() -> None:
    assert committee_dossier.dossier({"verifier_problems": []}) is None


@respx.mock
def test_each_listed_draft_carries_its_committee_dossier(
    client: TestClient, measured: int
) -> None:
    invented = {"problemas": [
        {"cita": "el tripulante tiene fiebre", "motivo": "inventado", "es_fallo": True},
    ]}
    respx.post(f"{LLM}/api/chat").mock(
        side_effect=[chat(GOOD_DRAFT), chat(invented), chat(SUPPORTED)]
    )
    assert client.post(f"/api/imaging/studies/{measured}/draft").status_code == 201
    [draft] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    dossier = draft["dossier"]
    assert dossier["committee"] == draft["committee"]
    [item] = dossier["head"]
    assert item["title"] == "inventado" and item["source"] == "?"
    assert dossier["untraceable"] is True
