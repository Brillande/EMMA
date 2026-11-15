"""Decisión de alto riesgo: segunda firma de otra persona (portado de Polaris
`decision_alto_riesgo.py`). Sin red: el modelo local se simula con respx.
"""

from __future__ import annotations

import pytest
import respx
from fastapi.testclient import TestClient

from app.api.routes import get_store
from app.decision_risk import trigger
from tests.test_interpret import LLM, clean_run
from tests.test_source_quote import TYPED, _seen
from tests.test_vault import report  # noqa: F401  (fixture)


@pytest.mark.parametrize(
    ("comment", "applies"),
    [
        ("concuerda con la imagen", False),
        ("Acepto; suspender la medicación y repetir en 24 h", True),
        ("Aceptado. Programar punción mañana.", True),
        ("Decisión irreversible: evacuación del tripulante", True),
        ("Resumen correcto, archivar", False),
        ("Rechazado: el borrador no describe la ventana 2", False),
    ],
)
def test_the_trigger_at_sign_off(comment: str, applies: bool) -> None:
    assert trigger(comment, deciding=True).applies is applies


def test_outside_a_decision_an_action_needs_a_doubt_as_in_polaris() -> None:
    assert not trigger("se suspendió el tratamiento el martes").applies
    assert trigger("¿debo suspender el tratamiento?").applies


@respx.mock
def test_a_high_risk_sign_off_needs_another_person(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    respx.post(f"{LLM}/api/chat").mock(side_effect=clean_run())
    client.post(f"/api/imaging/studies/{measured}/draft")
    [draft] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    first = {
        "decision": "accepted", "signed_by": "CMO",
        "comment": "Acepto; suspender la medicación y repetir la medida en 24 h",
        "text_sha256": draft["text_sha256"],
    }
    base = f"/api/imaging/drafts/{draft['ledger_index']}"
    assert client.post(f"{base}/sign", json=first).status_code == 201

    [pending] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    assert pending["record"] == {
        "second_signature_required": True, "complete": False, "disagreement": False,
    }
    # La misma persona no cuenta como segunda voz, tampoco con otras mayúsculas o espacios.
    same = {**first, "signed_by": " cmo ", "comment": ""}
    assert client.post(f"{base}/countersign", json=same).status_code == 409
    second = {**first, "signed_by": "Ingeniera de vuelo", "decision": "rejected", "comment": ""}
    # Desde el 2026-10-15 cita un informe guardado, con la frase vista (`test_countersign_strict`).
    assert client.post(f"{base}/countersign", json=second).status_code == 422
    cite = {"source": f"informe:{report}", "source_fragment": TYPED}
    quote = client.post(f"{base}/source-quote",
                        json={**cite, "signed_by": second["signed_by"]}).json()["quote"]
    second = {**second, **cite, "seen_quote": _seen(quote)}
    assert client.post(f"{base}/countersign", json=second).status_code == 201
    assert client.post(f"{base}/countersign", json=second).status_code == 409

    [signed] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    assert signed["record"] == {
        "second_signature_required": True, "complete": True, "disagreement": True,
    }
    assert get_store().verify_integrity().ok


@respx.mock
def test_an_ordinary_sign_off_needs_no_second_signature(
    client: TestClient, measured: int
) -> None:
    respx.post(f"{LLM}/api/chat").mock(side_effect=clean_run())
    client.post(f"/api/imaging/studies/{measured}/draft")
    [draft] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    sign = {
        "decision": "accepted", "signed_by": "CMO", "comment": "concuerda con la imagen",
        "text_sha256": draft["text_sha256"],
    }
    base = f"/api/imaging/drafts/{draft['ledger_index']}"
    assert client.post(f"{base}/sign", json=sign).status_code == 201
    [signed] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    assert signed["record"]["complete"] is True
    assert signed["record"]["second_signature_required"] is False
    other = {**sign, "signed_by": "otra"}
    assert client.post(f"{base}/countersign", json=other).status_code == 409


def test_the_reason_uses_emma_wording_not_polaris_panel() -> None:
    """En EMMA no hay "panel de élite": lo que exige el alto riesgo es la segunda firma."""
    reason = trigger("¿Deberíamos suspender el tratamiento y hacer una biopsia?").reason
    assert "élite" not in reason and "segunda firma" in reason
