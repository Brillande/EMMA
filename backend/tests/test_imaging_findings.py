"""Signos anotados (pulmón, FAST, hígado): el formulario entero o nada, y nunca un diagnóstico."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.api.routes import get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.imaging.measure import MEASURES
from app.imaging.protocols import NOT_ASSESSABLE, PROTOCOLS, validate_findings
from app.main import app
from tests.test_imaging import ultrasound_dicom

LLM = "http://127.0.0.1:11434"
LUNG = PROTOCOLS["lung"]


def complete(protocol_key: str, value: str | None = None) -> dict[str, dict[str, str]]:
    """Todas las ventanas y signos del protocolo contestados (con el primer valor, o `value`)."""
    protocol = PROTOCOLS[protocol_key]
    return {
        view.key: {
            sign.key: value if value is not None else next(iter(sign.values))
            for sign in view.signs
        }
        for view in protocol.views
    }


# --------------------------------------------------------------------------- #
# Registro
# --------------------------------------------------------------------------- #


def test_every_sign_can_be_answered_as_not_assessable() -> None:
    for protocol in PROTOCOLS.values():
        for view in protocol.views:
            for sign in view.signs:
                assert NOT_ASSESSABLE in sign.values, (protocol.key, view.key, sign.key)


def test_every_protocol_declares_its_checklist_and_sources() -> None:
    for protocol in PROTOCOLS.values():
        assert protocol.checklist, protocol.key
        assert protocol.sources, protocol.key


def test_a_protocol_is_measured_or_annotated() -> None:
    measured = {spec.protocol for spec in MEASURES.values()}
    for protocol in PROTOCOLS.values():
        assert (protocol.key in measured) != bool(protocol.views), protocol.key


def test_a_complete_form_is_valid() -> None:
    assert validate_findings(LUNG, complete("lung")) == []
    assert validate_findings(LUNG, complete("lung", NOT_ASSESSABLE)) == []


def test_a_missing_sign_is_not_read_as_absent() -> None:
    form = complete("lung")
    del form["derecha-anterior"]["deslizamiento-pleural"]
    [problem] = validate_findings(LUNG, form)
    assert "falta 'Deslizamiento pleural'" in problem


@pytest.mark.parametrize(
    "form",
    [
        {**complete("lung"), "espalda": {"lineas-b": "ninguna"}},
        {**complete("lung"), "derecha-anterior": {
            **complete("lung")["derecha-anterior"], "neumotorax": "presente"}},
        {**complete("lung"), "derecha-anterior": {
            **complete("lung")["derecha-anterior"], "lineas-b": "muchisimas"}},
    ],
)
def test_unknown_views_signs_or_values_are_refused(form: dict[str, dict[str, str]]) -> None:
    assert validate_findings(LUNG, form)


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def upload(client: TestClient, protocol: str) -> int:
    response = client.post(
        "/api/imaging/studies", params={"protocol": protocol},
        content=ultrasound_dicom(), headers={"content-type": "application/dicom"},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["ledger_index"])


def body(protocol: str, **overrides: Any) -> dict[str, Any]:
    return {
        "checklist": dict.fromkeys(PROTOCOLS[protocol].checklist, True),
        "findings": complete(protocol),
        "recorded_by": "CMO",
        **overrides,
    }


@pytest.mark.parametrize("protocol", ["lung", "fast", "liver"])
def test_findings_are_recorded_against_the_signed_study(client: TestClient, protocol: str) -> None:
    study = upload(client, protocol)
    response = client.post(f"/api/imaging/studies/{study}/findings", json=body(protocol))
    assert response.status_code == 201, response.text
    [stored] = client.get(f"/api/imaging/studies/{study}/findings").json()
    assert stored["findings"] == complete(protocol)
    assert [point["item"] for point in stored["checklist"]] == list(PROTOCOLS[protocol].checklist)
    assert get_store().verify_integrity().ok


def test_a_measured_protocol_records_only_its_checklist(client: TestClient) -> None:
    study = upload(client, "optic-nerve")
    response = client.post(f"/api/imaging/studies/{study}/findings", json=body("optic-nerve"))
    assert response.status_code == 201, response.text


@pytest.mark.parametrize(
    "overrides",
    [
        {"findings": {}},  # sin contestar ninguna ventana
        {"checklist": {}},  # sin contestar la lista de calidad
        {"checklist": {**dict.fromkeys(LUNG.checklist, True), "otro punto": True}},
    ],
)
def test_an_incomplete_form_writes_nothing(client: TestClient, overrides: dict[str, Any]) -> None:
    study = upload(client, "lung")
    before = len(get_store().ledger)
    response = client.post(f"/api/imaging/studies/{study}/findings", json=body("lung", **overrides))
    assert response.status_code == 422
    assert len(get_store().ledger) == before


def test_no_findings_on_a_missing_or_redacted_study(client: TestClient) -> None:
    assert client.post("/api/imaging/studies/9/findings", json=body("lung")).status_code == 404
    study = upload(client, "lung")
    reason = {"reason": "equivocado", "requested_by": "CMO"}
    redacted = client.post(f"/api/audit/redact/{study}", json=reason)
    assert redacted.status_code == 200, redacted.text
    url = f"/api/imaging/studies/{study}/findings"
    assert client.post(url, json=body("lung")).status_code == 404


def test_findings_are_not_readings(client: TestClient) -> None:
    study = upload(client, "fast")
    client.post(f"/api/imaging/studies/{study}/findings", json=body("fast"))
    assert get_store().query("crew-01") == []


def chat(content: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200, json={"message": {"role": "assistant", "content": json.dumps(content)}, "done": True}
    )


SUPPORTED: dict[str, Any] = {"problemas": []}


@respx.mock
def test_a_draft_may_describe_signs_but_not_name_a_disease(client: TestClient) -> None:
    study = upload(client, "lung")
    form = complete("lung", NOT_ASSESSABLE)
    form["derecha-anterior"]["deslizamiento-pleural"] = "ausente"
    client.post(f"/api/imaging/studies/{study}/findings", json=body("lung", findings=form))

    described = {
        "resumen": "Deslizamiento pleural ausente en la ventana derecha anterior.",
        "evolucion": "No hay estudios previos con los que comparar.",
        "limitaciones": ["El resto de signos se anotaron como no valorables."],
        "preguntas": ["¿Conviene repetir la ventana derecha anterior?"],
    }
    named = {**described, "resumen": "Hallazgo compatible con neumotórax derecho."}

    # Redactor y los dos miembros del comité.
    respx.post(f"{LLM}/api/chat").mock(
        side_effect=[chat(described), chat(SUPPORTED), chat(SUPPORTED)]
    )
    assert client.post(f"/api/imaging/studies/{study}/draft").status_code == 201

    respx.post(f"{LLM}/api/chat").mock(side_effect=[chat(named), chat(SUPPORTED)])
    blocked = client.post(f"/api/imaging/studies/{study}/draft")
    assert blocked.status_code == 422
    assert "diagnosis" in blocked.json()["detail"]


def test_the_facts_carry_the_signs_as_a_person_reads_them(client: TestClient) -> None:
    from app.interpret.draft import facts_for

    study = upload(client, "fast")
    form = complete("fast", "ausente")
    client.post(
        f"/api/imaging/studies/{study}/findings",
        json=body("fast", findings=form, checklist={
            **dict.fromkeys(PROTOCOLS["fast"].checklist, True),
            "Las cuatro ventanas adquiridas.": False,
        }),
    )
    [annotated] = facts_for(get_store(), study)["hallazgos_anotados_por_el_operador"]
    assert annotated["signos"]["Pélvica (suprapúbica)"] == {"Líquido libre": "Ausente"}
    assert annotated["calidad_no_cumplida"] == ["Las cuatro ventanas adquiridas."]
