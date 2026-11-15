"""Borrador asistido: cada barrera se prueba ejecutando lo que debe parar.

El modelo local se simula con `respx`: ninguna prueba toca la red (invariante 3). Lo que se
prueba no es la calidad del modelo —no la hay que probar aquí—, sino que un modelo que dice
lo que no debe, inventa una cifra o no está, nunca llega a la tripulación como si valiera.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.advisor import countermeasures
from app.api.routes import get_store
from app.core.config import Settings, get_settings
from app.imaging.measure import ALERTING_NOTE, MEASURES
from app.imaging.protocols import PROTOCOLS
from app.interpret.draft import unsupported_numbers
from app.interpret.llm import LocalLlm
from app.main import app
from app.text_guard import check

LLM = "http://127.0.0.1:11434"

# --------------------------------------------------------------------------- #
# Linter de lenguaje
# --------------------------------------------------------------------------- #


def test_every_fixed_crew_text_passes_the_guard() -> None:
    """Si el propio EMMA dijera lo que prohíbe al modelo, la regla no valdría nada."""
    # Toda la biblioteca de contramedidas: accion, indicacion, notas y bases.
    texts = [
        text
        for item in countermeasures.library().values()
        for text in (
            item.action, item.indication, item.crew_time_basis, item.followup_basis,
            item.contraindications_note, item.adverse_effects_note,
        )
        if text
    ]
    texts += [ALERTING_NOTE]
    texts += [i for spec in MEASURES.values() for i in spec.instructions.values()]
    texts += [protocol.rationale for protocol in PROTOCOLS.values()]
    assert [(t, check(t)) for t in texts if check(t)] == []


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("Administre 10 mg de acetazolamida.", "dosing"),
        ("Valorar sondaje vesical.", "dosing"),
        ("El tripulante padece SANS.", "diagnosis"),
        ("La imagen confirma la trombosis.", "diagnosis"),
        ("Hallazgo compatible con SANS.", "diagnosis"),
        ("Sugestivo de retención urinaria.", "diagnosis"),
        ("Sin duda la vaina está ensanchada.", "certainty"),
        ("La medida es 100 % fiable.", "certainty"),
        ("Inicie tratamiento inmediato.", "order"),
        # Evasiones: tildes, mayúsculas y un carácter invisible entre letras.
        ("ADMINISTRÉ el fármaco", "dosing"),
        ("admi​nistre la dosis", "dosing"),
    ],
)
def test_what_emma_cannot_say_is_caught(text: str, category: str) -> None:
    assert category in {finding.category for finding in check(text)}


# --------------------------------------------------------------------------- #
# Cifras
# --------------------------------------------------------------------------- #

FACTS_TEXT = '{"valor": "5,485 mm", "previa": "5,1 mm", "fecha": "2026-11-14", "profundidad": "3"}'


def test_a_rounded_copy_of_a_fact_is_allowed() -> None:
    assert unsupported_numbers("La vaina mide 5,5 mm (antes 5,1 mm), a 3 mm.", FACTS_TEXT) == []


def test_an_invented_number_is_caught() -> None:
    assert unsupported_numbers("La vaina mide 7,2 mm.", FACTS_TEXT) == ["7,2"]


def test_a_date_from_the_facts_can_be_cited() -> None:
    assert unsupported_numbers("Adquirido el 2026-11-14.", FACTS_TEXT) == []


# --------------------------------------------------------------------------- #
# Cliente
# --------------------------------------------------------------------------- #


def test_a_remote_model_is_refused() -> None:
    """Los datos clínicos no salen de la nave."""
    with pytest.raises(ValueError, match="loopback"):
        LocalLlm("https://api.example.com", "cualquiera")


@respx.mock
def test_availability_requires_the_configured_model() -> None:
    llm = LocalLlm(LLM, "qwen3:8b")
    respx.get(f"{LLM}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "otro:1b"}]})
    )
    assert llm.available() is False
    respx.get(f"{LLM}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "qwen3:8b"}]})
    )
    assert llm.available() is True
    respx.get(f"{LLM}/api/tags").mock(side_effect=httpx.ConnectError("sin servidor"))
    assert llm.available() is False


# --------------------------------------------------------------------------- #
# Flujo por la API
# --------------------------------------------------------------------------- #

GOOD_DRAFT = {
    "resumen": "Vaina del nervio óptico derecho: 5,5 mm, medida a 3 mm del globo.",
    "evolucion": "No hay mediciones previas con las que comparar.",
    "limitaciones": ["Fantoma simulado: no es un tripulante."],
    "preguntas": ["¿Conviene repetir la medida en el ojo izquierdo?"],
}
SUPPORTED: dict[str, Any] = {"problemas": []}


def chat(content: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"message": {"role": "assistant", "content": json.dumps(content)}, "done": True},
    )


def clean_run() -> list[httpx.Response]:
    """Redactor y el comité por defecto (un verificador), conformes."""
    return [chat(GOOD_DRAFT), chat(SUPPORTED)]




@respx.mock
def test_a_clean_draft_is_stored_unvalidated_and_signed_once(
    client: TestClient, measured: int
) -> None:
    respx.post(f"{LLM}/api/chat").mock(side_effect=clean_run())
    response = client.post(f"/api/imaging/studies/{measured}/draft")
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "unvalidated"

    [draft] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    assert draft["text"].startswith("Vaina del nervio óptico derecho: 5,5 mm")
    assert draft["signoff"] is None

    sign = {"decision": "accepted", "signed_by": "CMO", "comment": "concuerda con la imagen"}
    url = f"/api/imaging/drafts/{draft['ledger_index']}/sign"
    # Sin la huella del texto leído, o con otra, no hay firma (patrón de Polaris `salida.py`).
    assert client.post(url, json=sign).status_code == 422
    other = hashlib.sha256(b"otro texto").hexdigest()
    assert client.post(url, json={**sign, "text_sha256": other}).status_code == 409
    assert draft["text_sha256"] == hashlib.sha256(draft["text"].encode()).hexdigest()
    sign["text_sha256"] = draft["text_sha256"]
    assert client.post(url, json=sign).status_code == 201
    again = client.post(url, json=sign)
    assert again.status_code == 409

    [signed] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    assert signed["signoff"]["decision"] == "accepted"
    assert signed["signoff"]["signed_by"] == "CMO"
    assert signed["signoff"]["text_sha256"] == draft["text_sha256"]
    assert get_store().verify_integrity().ok


@respx.mock
@pytest.mark.parametrize(
    ("draft", "verdict", "reason"),
    [
        ({**GOOD_DRAFT, "resumen": "Hallazgo compatible con SANS."}, SUPPORTED, "lenguaje"),
        ({**GOOD_DRAFT, "resumen": "La vaina mide 7,2 mm."}, SUPPORTED, "cifra"),
        (
            GOOD_DRAFT,
            {"problemas": [
                {"cita": "medida a 3 mm del globo", "motivo": "sin base", "es_fallo": True}
            ]},
            "verificador",
        ),
        (dict.fromkeys(GOOD_DRAFT, ""), SUPPORTED, "secciones"),
    ],
)
def test_a_draft_that_fails_a_barrier_is_never_shown(
    client: TestClient, measured: int, draft: dict[str, Any], verdict: dict[str, Any], reason: str
) -> None:
    respx.post(f"{LLM}/api/chat").mock(side_effect=[chat(draft), chat(verdict)])
    response = client.post(f"/api/imaging/studies/{measured}/draft")
    assert response.status_code == 422
    assert reason in response.json()["detail"]

    [stored] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    assert stored["status"] == "blocked"
    assert "text" not in stored  # el texto bloqueado no se guarda ni se muestra
    sign = {"decision": "accepted", "signed_by": "CMO", "text_sha256": "0" * 64}
    url = f"/api/imaging/drafts/{stored['ledger_index']}/sign"
    assert client.post(url, json=sign).status_code == 409


@respx.mock
def test_an_objection_that_quotes_nothing_in_the_draft_does_not_block(
    client: TestClient, measured: int
) -> None:
    """Con un modelo real, el verificador inventaba objeciones sobre frases que no existían."""
    invented = {"problemas": [
        {"cita": "el tripulante tiene fiebre", "motivo": "inventado", "es_fallo": True},
        # qwen3.5:9b: cita una frase real y dice que no es un fallo.
        {"cita": "medida a 3 mm del globo", "motivo": "no es un fallo", "es_fallo": False},
    ]}
    respx.post(f"{LLM}/api/chat").mock(
        side_effect=[chat(GOOD_DRAFT), chat(invented)]
    )
    assert client.post(f"/api/imaging/studies/{measured}/draft").status_code == 201
    [draft] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    assert draft["status"] == "unvalidated"
    # Cada objeción descartada dice qué miembro del comité la hizo.
    assert draft["discarded_objections"] == [
        "gemma4:12b-it-qat · inventado", "gemma4:12b-it-qat · no es un fallo",
    ]


@respx.mock
def test_a_truncated_answer_is_not_read_as_empty(client: TestClient, measured: int) -> None:
    """Si el modelo agota el contexto, se dice así, no como un JSON inservible."""
    respx.post(f"{LLM}/api/chat").mock(
        return_value=httpx.Response(
            200, json={"message": {"content": ""}, "done": True, "done_reason": "length"}
        )
    )
    response = client.post(f"/api/imaging/studies/{measured}/draft")
    assert response.status_code == 503
    assert "agotó el contexto" in response.json()["detail"]


@respx.mock
def test_without_a_local_model_the_function_is_declared_absent(
    client: TestClient, measured: int
) -> None:
    respx.post(f"{LLM}/api/chat").mock(side_effect=httpx.ConnectError("sin servidor"))
    respx.get(f"{LLM}/api/tags").mock(side_effect=httpx.ConnectError("sin servidor"))
    before = len(get_store().ledger)

    response = client.post(f"/api/imaging/studies/{measured}/draft")
    assert response.status_code == 503
    assert "no disponible" in response.json()["detail"]
    assert len(get_store().ledger) == before

    status = client.get("/api/imaging/interpretation").json()
    assert status["available"] is False and "no disponible" in status["note"]


def test_no_draft_without_measurements(client: TestClient) -> None:
    study = client.post("/api/imaging/phantom", params={"protocol": "bladder"}).json()
    response = client.post(f"/api/imaging/studies/{study['ledger_index']}/draft")
    assert response.status_code == 422


@respx.mock
def test_drafts_are_not_readings(client: TestClient, measured: int) -> None:
    """Un borrador no entra en el análisis ni cuenta como dato del tripulante."""
    respx.post(f"{LLM}/api/chat").mock(side_effect=clean_run())
    client.post(f"/api/imaging/studies/{measured}/draft")
    assert "interpretation-local" not in get_store().reading_signers()
    assert len(get_store().query("crew-01")) == 1  # solo la medida


# --------------------------------------------------------------------------- #
# Comité de verificadores (patrón de Polaris)
# --------------------------------------------------------------------------- #


TWO_VOICES = ["qwen3.5:9b", "gemma4:12b-it-qat"]


@pytest.fixture
def two_voices(client: TestClient, tmp_path: Path) -> TestClient:
    """Un comité de dos: el de serie tiene uno, pero la lógica del comité admite varios."""
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, assistant_warmup=False, llm_verifiers=TWO_VOICES
    )
    return client


@respx.mock
def test_one_committee_member_is_enough_to_block(two_voices: TestClient, measured: int) -> None:
    """El primero lo da por bueno; el segundo cita un fallo: no se muestra."""
    objection = {"problemas": [
        {"cita": "medida a 3 mm del globo", "motivo": "sin base", "es_fallo": True}
    ]}
    respx.post(f"{LLM}/api/chat").mock(
        side_effect=[chat(GOOD_DRAFT), chat(SUPPORTED), chat(objection)]
    )
    response = two_voices.post(f"/api/imaging/studies/{measured}/draft")
    assert response.status_code == 422
    assert "gemma4:12b-it-qat" in response.json()["detail"]
    [stored] = two_voices.get(f"/api/imaging/studies/{measured}/drafts").json()
    assert stored["committee"] == TWO_VOICES


@respx.mock
def test_a_missing_committee_member_makes_the_function_unavailable(client: TestClient) -> None:
    respx.get(f"{LLM}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "gemma4:e4b"}]})
    )
    status = client.get("/api/imaging/interpretation").json()
    assert status["available"] is False
    assert status["missing"] == ["gemma4:12b-it-qat"]
    assert status["committee"] == ["gemma4:12b-it-qat"]
