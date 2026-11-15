"""La fuente que cita una firma de alto riesgo: ¿existe en su registro? Sin red.

`_existencia_citas` de Polaris decide; aquí se le da un registro simulado o, con la API en modo
sin red, el comprobador que no acusa sin prueba. No bloquea la firma (decisión del usuario).
"""

from __future__ import annotations

import respx
from fastapi.testclient import TestClient

from app.evidence.source_check import check_source, offline_checker
from tests.test_interpret import LLM, clean_run


def registry(states: dict[str, str]):  # type: ignore[no-untyped-def]
    return lambda tokens: [{"entrada": t, "estado": states[t]} for t in tokens]


def test_a_citation_the_registry_denies_is_fabricated() -> None:
    result = check_source("PMID 12345678", registry({"PMID 12345678": "no_existe"}))
    assert result["estado"] == "FABRICADA"


def test_a_citation_the_registry_confirms_is_confirmed() -> None:
    result = check_source("PMID 24806559", registry({"PMID 24806559": "existe"}))
    assert result["estado"] == "confirmada"


def test_without_network_nothing_is_accused() -> None:
    assert check_source("PMID 12345678", offline_checker)["estado"] == "no_resoluble"


def test_an_internal_reference_or_no_source_is_not_checked() -> None:
    assert check_source("contramedida: refugio radiológico", offline_checker)["estado"] == "n/a"
    assert check_source("  ", offline_checker)["estado"] == "sin_fuente"


@respx.mock
def test_the_signature_keeps_its_source_and_check_and_is_not_blocked(
    client: TestClient, measured: int
) -> None:
    respx.post(f"{LLM}/api/chat").mock(side_effect=clean_run())
    client.post(f"/api/imaging/studies/{measured}/draft")
    [draft] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    body = {
        "decision": "accepted", "signed_by": "CMO", "comment": "concuerda con la imagen",
        "text_sha256": draft["text_sha256"], "source": "PMID 12345678",
    }
    url = f"/api/imaging/drafts/{draft['ledger_index']}/sign"
    assert client.post(url, json=body).status_code == 201
    [signed] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    assert signed["signoff"]["source"] == "PMID 12345678"
    assert signed["signoff"]["source_check"]["estado"] == "no_resoluble"  # la suite va sin red
