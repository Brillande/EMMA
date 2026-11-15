"""El asistente de voz: contrato, catálogo, cada barrera, propuestas, Tierra con corte y sin modelo.

El modelo local se simula con `respx` sobre la API de Ollama (el cliente de `app/interpret/llm.py`
de verdad): ninguna prueba toca la red, tampoco el Ollama que pueda haber en esta máquina
(invariante 3). Lo que se prueba no es lo bien que contesta un modelo, sino que lo que dice mal
—una cifra inventada, una pastilla, una orden, una intención que no existe— nunca se oye, y que
el asistente no escribe en ningún sitio.
"""

from __future__ import annotations

import base64
import datetime as dt
import io
import json
import re
import subprocess
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app import voice
from app.api.routes import get_store
from app.assistant import audio, catalog, context, guards, retrieval, turn
from app.assistant.proposals import GROUND_REFUSAL, ORIGIN, propose
from app.core.config import Settings, get_settings
from app.interpret import llm as llm_module
from app.main import app
from app.pain.catalog import ZONES

LLM = "http://127.0.0.1:11434"
MODEL = get_settings().assistant_model
REPO = Path(__file__).resolve().parents[2]
OGG = b"OggS" + b"\x00" * 64


@pytest.fixture(autouse=True)
def _fresh_context() -> Iterator[None]:
    """Cada prueba con la caché del contexto vacía: otra prueba pudo dejar uno del mismo tamaño."""
    context.clear_cache()
    llm_module._HEARS.clear()
    yield
    context.clear_cache()


@pytest.fixture
def ollama() -> Iterator[respx.MockRouter]:
    """Ollama simulado. Sin respuesta preparada, el chat no conecta: es «sin modelo»."""
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{LLM}/api/tags").mock(
            return_value=httpx.Response(200, json={"models": [{"name": MODEL}]})
        )
        router.post(f"{LLM}/api/chat").mock(side_effect=httpx.ConnectError("sin servidor"))
        # El modelo por defecto no oye: la voz va por Whisper salvo que la prueba diga otra cosa.
        router.post(f"{LLM}/api/show").mock(
            return_value=httpx.Response(200, json={"capabilities": ["completion", "tools"]})
        )
        yield router


@pytest.fixture
def seeded(client: TestClient, ollama: respx.MockRouter) -> TestClient:
    assert client.post("/api/simulate", params={"scenario": "spe-event", "days": 10}).status_code \
        == 201
    return client


def answer(router: respx.MockRouter, intent: str, args: dict[str, Any], reply: str) -> list[Any]:
    """El modelo contesta esto; devuelve las peticiones que recibió, para mirarlas."""
    seen: list[Any] = []

    def chat(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        content = json.dumps({"intent": intent, "args": args, "reply": reply})
        return httpx.Response(200, json={"message": {"content": content}, "done_reason": "stop"})

    router.post(f"{LLM}/api/chat").mock(side_effect=chat)
    return seen


def say(client: TestClient, text: str, console: str = "crew", **extra: Any) -> dict[str, Any]:
    response = client.post(
        "/api/assistant/turn",
        json={"text": text, "console": console, "subject": "crew-01", **extra},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    assert set(body) == {"intent", "args", "reply", "reply_source", "needs_confirmation",
                         "proposal", "checks", "label"}
    assert set(body["checks"]) == {"text_guard", "numbers", "no_prescription", "schema"}
    return body


def heart_rate(client: TestClient) -> str:
    """La frecuencia cardiaca como la escribe el contexto del backend (`display.number`)."""
    built = context.build(get_settings_for(client), get_store(), "crew-01", "crew")
    match = re.search(r"Frecuencia cardiaca: (\d+)", built.readings["heart-rate"])
    assert match
    return match.group(1)


def get_settings_for(client: TestClient) -> Any:
    from app.main import app

    return app.dependency_overrides[get_settings]()


# --------------------------------------------------------------------------- #
# Contrato
# --------------------------------------------------------------------------- #


def test_the_status_lists_the_whole_catalog_and_says_why_there_is_no_model(
    client: TestClient, ollama: respx.MockRouter
) -> None:
    ollama.get(f"{LLM}/api/tags").mock(return_value=httpx.Response(200, json={"models": []}))
    body = client.get("/api/assistant").json()
    assert set(body) == {"available", "model", "reason", "voice_available", "voice_by",
                         "intents", "ui"}
    assert {item["id"] for item in body["ui"]["panels"]} == set(catalog.catalog().panels)
    assert body["available"] is False and body["model"] == MODEL
    assert MODEL in body["reason"]
    assert {item["id"] for item in body["intents"]} == catalog.CONTRACT_IDS
    for item in body["intents"]:
        assert set(item) == {"id", "kind", "label", "args"}
        assert item["kind"] in ("read", "write")
    kinds = {item["id"]: item["kind"] for item in body["intents"]}
    assert {key for key, kind in kinds.items() if kind == "write"} == {
        "diary_entry", "pain_report", "acknowledge_alert", "mission_level", "mission_profile",
        "safe_mode",
    }
    # La navegación por la interfaz es lectura: ninguna intención nueva escribe.
    for nav in ("open_panel", "read_panel", "toggle_mode", "switch_console", "scroll",
                "next_panel", "previous_panel"):
        assert kinds[nav] == "read", nav


def test_with_the_model_installed_the_assistant_is_available(
    client: TestClient, ollama: respx.MockRouter
) -> None:
    body = client.get("/api/assistant").json()
    assert body["available"] is True and body["reason"] is None


def test_a_server_that_is_down_is_declared_absent(
    client: TestClient, ollama: respx.MockRouter
) -> None:
    ollama.get(f"{LLM}/api/tags").mock(side_effect=httpx.ConnectError("apagado"))
    assert client.get("/api/assistant").json()["available"] is False


def test_the_history_is_capped_at_eight_turns(seeded: TestClient) -> None:
    history = [{"role": "user", "text": "hola"}] * 9
    response = seeded.post("/api/assistant/turn", json={
        "text": "¿cómo estoy?", "console": "crew", "subject": "crew-01", "history": history,
    })
    assert response.status_code == 422


def test_the_model_is_called_local_deterministic_and_with_json(seeded: TestClient,
                                                               ollama: respx.MockRouter) -> None:
    seen = answer(ollama, "read_status", {}, "Vas bien.")
    say(seeded, "¿cómo estoy?", history=[{"role": "user", "text": "hola"}])
    [request] = seen
    assert request["model"] == MODEL
    assert request["think"] is False and request["stream"] is False
    assert request["options"]["temperature"] == 0
    assert request["format"]["properties"]["intent"]["enum"]
    system, user = (message["content"] for message in request["messages"])
    assert "EMMA" in system and "No nombres fármacos" in system
    summary = seeded.get("/api/status").json()["summary"]
    assert summary in user and "persona: hola" in user


# --------------------------------------------------------------------------- #
# Catálogo
# --------------------------------------------------------------------------- #


def _frontend_keys(path: str) -> set[str]:
    return set(re.findall(r'key: "([a-z-]+)"', (REPO / path).read_text(encoding="utf-8")))


def test_every_section_is_a_real_tab_of_its_console() -> None:
    crew = _frontend_keys("frontend/src/dashboard/CrewConsole.tsx")
    ground = _frontend_keys("frontend/src/ground/GroundConsole.tsx")
    cat = catalog.catalog()
    for console, real in (("crew", crew), ("ground", ground)):
        own = [key for key in cat.section_keys(console) if not key.startswith("env-")]
        assert own and set(own) <= real, (console, set(own) - real)
    # Las de entorno, una por perfil de misión (`Environments.tsx`: `env-${profile.id}`).
    assert "env-mars-transit" in cat.section_keys("crew")


def test_the_value_lists_are_read_from_their_sources() -> None:
    schemas = {item["id"]: item["args"] for item in catalog.describe()}
    guides = json.loads((REPO / "backend/app/data/measurement_guides.json").read_text("utf-8"))
    assert schemas["open_guide"]["topic"]["enum"] == [g["id"] for g in guides["guides"]]
    assert schemas["pain_report"]["zone"]["enum"] == list(ZONES)
    assert "mood-valence" in schemas["diary_entry"]["key"]["enum"]
    assert schemas["mission_level"]["level"]["enum"] == ["nominal", "reduced", "minimal"]
    assert schemas["rotate"]["degrees"]["enum"] == [0, 90, 180, 270]


def test_a_catalog_that_breaks_its_rules_does_not_load() -> None:
    raw = json.loads(catalog.INTENTS_PATH.read_text(encoding="utf-8"))
    broken = json.loads(json.dumps(raw))
    broken["intents"].append(dict(broken["intents"][0]))
    with pytest.raises(catalog.CatalogError, match="repetida"):
        catalog.validate(broken)
    broken = json.loads(json.dumps(raw))
    broken["intents"] = [item for item in broken["intents"] if item["id"] != "safe_mode"]
    with pytest.raises(catalog.CatalogError, match="contrato"):
        catalog.validate(broken)
    broken = json.loads(json.dumps(raw))
    for item in broken["intents"]:
        if item["id"] == "diary_entry":
            item["signer_field"] = None
    with pytest.raises(catalog.CatalogError, match="firma"):
        catalog.validate(broken)
    broken = json.loads(json.dumps(raw))
    broken["guide_keywords"].pop("pvt")
    with pytest.raises(catalog.CatalogError, match="guía"):
        catalog.validate(broken)


@pytest.mark.parametrize(("text", "console", "intent", "args"), [
    ("abre radiación", "crew", "open_tab", {"section": "radiation"}),
    ("EMMA, abre el diario", "crew", "open_tab", {"section": "log"}),
    ("ve a tendencias", "ground", "open_tab", {"section": "trends"}),
    ("abre la guía de la tensión", "crew", "open_guide", {"topic": "blood-pressure"}),
    ("gira 90", "crew", "rotate", {"degrees": 90}),
    ("quita la privacidad", "crew", "privacy", {"on": False}),
    ("pon la baja visión", "crew", "low_vision", {"on": True}),
    ("silencio 10 minutos", "crew", "silence", {"minutes": 10}),
    ("deja de escuchar", "crew", "stop_listening", {}),
    ("¿cómo estoy?", "crew", "read_status", {}),
    ("léeme las alertas", "crew", "read_alerts", {}),
    ("empieza la PVT", "crew", "start_pvt", {}),
    ("qué tiempo hace en Madrid", "crew", "none", {}),
    # Lo que cazó la revisión de código del 2026-11-03.
    ("pon la letra grande, que no veo bien", "crew", "low_vision", {"on": True}),
    ("activa el modo seguro por la salud del comandante", "crew", "safe_mode", {"active": True}),
    ("sal del modo seguro", "crew", "safe_mode", {"active": False}),
    ("me duele otra vez la rodilla izquierda, un 7", "crew", "pain_report",
     {"zone": "knee-left", "intensity": 7}),
    ("me duele un poco la rodilla izquierda", "crew", "pain_report", {"zone": "knee-left"}),
])
def test_keywords_route_without_a_model(text: str, console: str, intent: str,
                                        args: dict[str, Any]) -> None:
    assert turn._keyword_turn(text, console) == (intent, args)


def test_the_schema_admits_nothing_outside_the_catalog() -> None:
    with pytest.raises(catalog.InvalidArgs):
        catalog.validate_args("launch", {}, "crew")
    with pytest.raises(catalog.InvalidArgs):
        catalog.validate_args("rotate", {"degrees": 45}, "crew")
    with pytest.raises(catalog.InvalidArgs):
        catalog.validate_args("open_tab", {"section": "trends"}, "crew")  # es de Tierra
    with pytest.raises(catalog.InvalidArgs):
        catalog.validate_args("privacy", {"on": True, "extra": 1}, "crew")
    assert catalog.validate_args("silence", {}, "crew") == {}


# --------------------------------------------------------------------------- #
# Sin modelo: sale igual, con lo determinista
# --------------------------------------------------------------------------- #


def test_without_a_model_navigation_is_fixed_text(seeded: TestClient) -> None:
    body = say(seeded, "abre radiación")
    assert (body["intent"], body["args"]) == ("open_tab", {"section": "radiation"})
    assert body["reply"] == "Abro Radiación."
    assert body["reply_source"] == "fixed" and body["label"] is None
    assert not any(body["checks"].values())


def test_without_a_model_the_status_is_the_backend_summary(seeded: TestClient) -> None:
    body = say(seeded, "¿cómo estoy?")
    assert body["intent"] == "read_status"
    assert body["reply"] == seeded.get("/api/status").json()["summary"]
    assert body["reply_source"] == "backend"


def test_without_a_model_a_reading_is_said_as_the_backend_writes_it(seeded: TestClient) -> None:
    body = say(seeded, "¿cuál es mi frecuencia cardiaca?")
    assert body["intent"] == "none" and body["reply_source"] == "backend"
    assert body["reply"].startswith(f"Frecuencia cardiaca: {heart_rate(seeded)} ")


def test_a_model_that_answers_garbage_is_the_same_as_no_model(seeded: TestClient,
                                                             ollama: respx.MockRouter) -> None:
    ollama.post(f"{LLM}/api/chat").mock(return_value=httpx.Response(
        200, json={"message": {"content": "no es json"}, "done_reason": "stop"}))
    body = say(seeded, "¿cómo estoy?")
    assert body["intent"] == "read_status" and body["reply_source"] == "backend"


def test_with_an_empty_store_it_says_so_and_does_not_fail(client: TestClient,
                                                          ollama: respx.MockRouter) -> None:
    body = say(client, "¿cómo estoy?")
    assert "No hay lecturas" in body["reply"]


# --------------------------------------------------------------------------- #
# Barreras de la respuesta del modelo
# --------------------------------------------------------------------------- #


def test_a_clean_model_answer_is_said_and_labelled(seeded: TestClient,
                                                  ollama: respx.MockRouter) -> None:
    rate = heart_rate(seeded)
    answer(ollama, "none", {}, f"Tu frecuencia cardiaca es de {rate} por minuto.")
    body = say(seeded, "¿cuál es mi frecuencia cardiaca?")
    assert body["reply"] == f"Tu frecuencia cardiaca es de {rate} por minuto."
    assert body["reply_source"] == "model"
    assert body["label"] == "respuesta del modelo local, sin validar"
    assert all(body["checks"].values())


def test_an_invented_figure_is_not_said(seeded: TestClient, ollama: respx.MockRouter) -> None:
    answer(ollama, "none", {}, "Tu frecuencia cardiaca es de 999 por minuto.")
    body = say(seeded, "¿cuál es mi frecuencia cardiaca?")
    assert body["checks"]["numbers"] is False
    assert body["reply_source"] == "backend" and "999" not in body["reply"]
    assert body["reply"].startswith("Frecuencia cardiaca:")


def test_an_invented_figure_in_words_is_not_said(seeded: TestClient,
                                                ollama: respx.MockRouter) -> None:
    answer(ollama, "none", {}, "Tu frecuencia cardiaca es de novecientos por minuto.")
    assert say(seeded, "¿cuál es mi frecuencia cardiaca?")["checks"]["numbers"] is False


def test_a_figure_only_in_the_history_is_not_support(seeded: TestClient,
                                                    ollama: respx.MockRouter) -> None:
    answer(ollama, "none", {}, "Como te dije, 8888.")
    body = say(seeded, "¿y ayer?", history=[{"role": "assistant", "text": "Eran 8888."}])
    assert body["checks"]["numbers"] is False and "8888" not in body["reply"]


def test_forbidden_language_is_not_said(seeded: TestClient, ollama: respx.MockRouter) -> None:
    answer(ollama, "read_status", {}, "Sin duda estás perfectamente.")
    body = say(seeded, "¿cómo estoy?")
    assert body["checks"]["text_guard"] is False
    assert body["reply"] == seeded.get("/api/status").json()["summary"]


def test_a_prescription_is_not_said(seeded: TestClient, ollama: respx.MockRouter) -> None:
    answer(ollama, "none", {}, "Un ibuprofeno te iría bien.")
    body = say(seeded, "me noto cansado")
    assert body["checks"]["no_prescription"] is False
    assert "ibuprofeno" not in body["reply"]


def test_asking_what_pill_to_take_gets_the_fixed_refusal(seeded: TestClient,
                                                        ollama: respx.MockRouter) -> None:
    answer(ollama, "none", {}, "Toma una pastilla para dormir.")
    body = say(seeded, "¿qué pastilla me tomo?")
    assert body["reply"] == turn.NO_PRESCRIPTION and body["reply_source"] == "fixed"
    # Sin modelo, la misma negativa.
    ollama.post(f"{LLM}/api/chat").mock(side_effect=httpx.ConnectError("sin servidor"))
    assert say(seeded, "¿qué pastilla me tomo?")["reply"] == turn.NO_PRESCRIPTION


def test_an_intent_outside_the_catalog_fails_the_schema(seeded: TestClient,
                                                       ollama: respx.MockRouter) -> None:
    answer(ollama, "launch_rocket", {}, "Despegamos.")
    body = say(seeded, "abre radiación")
    assert body["checks"]["schema"] is False
    assert (body["intent"], body["args"]) == ("open_tab", {"section": "radiation"})
    assert body["reply_source"] == "fixed"


def test_arguments_outside_the_schema_fail_it(seeded: TestClient,
                                             ollama: respx.MockRouter) -> None:
    answer(ollama, "rotate", {"degrees": 45}, "Giro.")
    body = say(seeded, "gira la pantalla")
    assert body["checks"]["schema"] is False and body["intent"] == "none"


def test_every_fixed_text_passes_its_own_barriers() -> None:
    texts = [turn.NO_PRESCRIPTION, turn.NOT_UNDERSTOOD, turn.NO_DATA, GROUND_REFUSAL,
             *turn._FIXED.values()]
    for text in texts:
        assert guards.language_ok(text), text
        assert guards.no_prescription(text), text


@pytest.mark.parametrize(("text", "known", "ok"), [
    ("Son 74 por minuto.", "Frecuencia cardiaca: 74 /min", True),
    ("Son setenta y cuatro.", "Frecuencia cardiaca: 74 /min", True),
    ("Son setenta y cuatro.", "Frecuencia cardiaca: 70 /min", False),
    ("Son setenta.", "Frecuencia cardiaca: 70 /min", True),
    ("Son 64.", "Frecuencia cardiaca: 74 /min", False),
    ("Hay dos alertas.", "2 alertas", True),
    ("Hay tres alertas.", "2 alertas", False),
    ("Llevas mil doscientos pasos.", "1200 pasos", False),
    ("Tu sistólica está en doscientos.", "Tensión sistólica: 120 mmHg", False),
    ("Es un dato científico.", "dato", True),
    ("Una alerta de radiación.", "radiación", True),
])
def test_the_figures_barrier(text: str, known: str, ok: bool) -> None:
    assert guards.numbers_ok(text, known) is ok


@pytest.mark.parametrize(("text", "ok"), [
    ("Tu tensión está en lo esperado.", True),
    ("¿Quieres que abra la guía para tomar la tensión?", True),
    ("Valora tu ánimo con el tomate de hoy.", True),
    ("Tome algo para el dolor.", False),
    ("Debes tomar dos comprimidos.", False),
    ("Debes tomar algo para dormir.", False),
    ("Un paracetamol cada ocho horas.", False),
    ("Te receto reposo.", False),
    ("La melatonina ayuda a dormir.", False),
    ("Con 400 mg basta.", False),
    ("Con 200 µg basta.", False),
    ("Llevas una dosis de radiación de 3 mSv.", True),
    ("Una dosis más de esto.", False),
    ("Un analgésico te aliviaría.", False),
])
def test_the_no_prescription_barrier(text: str, ok: bool) -> None:
    assert guards.no_prescription(text) is ok


def test_asking_for_medication_is_recognised() -> None:
    assert guards.asks_for_medication("¿Qué pastilla me tomo?")
    assert guards.asks_for_medication("¿qué me tomo para dormir?")
    assert not guards.asks_for_medication("¿Cómo me tomo la tensión?")
    assert not guards.asks_for_medication("¿Qué dosis de radiación llevo?")


def test_a_failed_none_answer_falls_back_to_what_was_asked(seeded: TestClient,
                                                          ollama: respx.MockRouter) -> None:
    """El modelo contesta las preguntas con «none»; si su frase no pasa, se lee lo pedido."""
    answer(ollama, "none", {}, "Estás a 9999 de algo.")
    body = say(seeded, "¿cómo estoy?")
    assert body["reply"] == seeded.get("/api/status").json()["summary"]


def test_opening_the_dose_tab_is_not_a_medication_refusal(seeded: TestClient) -> None:
    body = say(seeded, "abre dosis")
    assert body["intent"] == "open_tab" and body["reply"] == "Abro Misión y hábitat."


def test_an_article_is_not_an_intensity(seeded: TestClient, ollama: respx.MockRouter) -> None:
    answer(ollama, "pain_report", {"zone": "knee-left", "intensity": 1}, "Vale.")
    body = say(seeded, "me duele un poco la rodilla izquierda")
    assert body["proposal"] is None and "de 1 a 10" in body["reply"]


# --------------------------------------------------------------------------- #
# Propuestas de escritura: el cuerpo exacto de la ruta, sin firmar
# --------------------------------------------------------------------------- #


def test_a_diary_proposal_is_the_body_its_route_accepts(seeded: TestClient,
                                                       ollama: respx.MockRouter) -> None:
    answer(ollama, "diary_entry", {"key": "mood-valence", "value": 3}, "Lo anoto.")
    before = len(get_store().ledger)
    body = say(seeded, "apunta en el diario ánimo 3", operator="CMO")
    assert len(get_store().ledger) == before  # proponer no firma
    assert body["needs_confirmation"] is True and body["reply_source"] == "backend"
    assert body["proposal"] == {"key": "mood-valence", "value": 3.0, "subject": "crew-01"}
    assert "No se ha firmado" in body["reply"] and "Firmará CMO" in body["reply"]
    signed = seeded.post("/api/diary/entries", json={**body["proposal"], "recorded_by": "CMO"})
    assert signed.status_code == 201, signed.text


def test_a_diary_value_the_person_did_not_say_is_not_proposed(
    seeded: TestClient, ollama: respx.MockRouter
) -> None:
    answer(ollama, "diary_entry", {"key": "mood-valence", "value": 2}, "Anoto ánimo 2.")
    body = say(seeded, "apunta en el diario que estoy de mal humor")
    assert body["intent"] == "diary_entry"
    assert body["needs_confirmation"] is False and body["proposal"] is None
    assert "necesito el valor" in body["reply"]


def test_a_diary_value_out_of_range_is_not_proposed(seeded: TestClient,
                                                   ollama: respx.MockRouter) -> None:
    answer(ollama, "diary_entry", {"key": "mood-valence", "value": 40}, "Anoto.")
    body = say(seeded, "apunta ánimo 40")
    assert body["proposal"] is None and "No puedo preparar" in body["reply"]


def test_a_pain_proposal_carries_the_words_and_the_assistant_origin(
    seeded: TestClient, ollama: respx.MockRouter
) -> None:
    text = "me duele la rodilla izquierda, un 6, punzante"
    answer(ollama, "pain_report",
           {"zone": "knee-left", "intensity": 6, "characters": ["sharp", "burning"]}, "Vale.")
    body = say(seeded, text)
    assert body["proposal"] == {
        "zones": [{"zone": "knee-left", "intensity": 6, "characters": ["sharp"]}],
        "subject": "crew-01", "note": text, "note_origin": ORIGIN,
    }
    signed = seeded.post("/api/pain/reports", json={**body["proposal"], "reported_by": "CMO"})
    assert signed.status_code == 201, signed.text
    [report] = seeded.get("/api/pain/reports").json()[-1:]
    assert report["note_origin"] == "asistente-confirmada"


def test_a_write_with_half_valid_arguments_keeps_only_the_valid_ones(
    seeded: TestClient, ollama: respx.MockRouter
) -> None:
    """Visto con el modelo real: `"characters": "sharp"`, sin lista. No pasa el esquema, pero la
    zona y la intensidad sí, y la propuesta sale sin el tipo."""
    answer(ollama, "pain_report", {"zone": "knee-left", "intensity": 6, "characters": "sharp"},
           "Vale.")
    body = say(seeded, "me duele la rodilla izquierda, un 6, punzante")
    assert body["checks"]["schema"] is False
    assert body["proposal"]["zones"] == [
        {"zone": "knee-left", "intensity": 6, "characters": []}
    ]


def test_the_pdf_says_the_note_came_through_the_assistant() -> None:
    from app import export

    heading = export._note_heading(ORIGIN)
    assert "asistente de voz" in heading and "no la ha corregido ni verificado" in heading


def test_a_pain_zone_the_person_did_not_name_is_not_proposed(
    seeded: TestClient, ollama: respx.MockRouter
) -> None:
    answer(ollama, "pain_report", {"zone": "knee-right", "intensity": 6}, "Vale.")
    body = say(seeded, "me duele la rodilla, un 6")
    assert body["proposal"] is None and "zona" in body["reply"]
    # Si la persona sí la nombra, manda lo que dijo, no la zona del modelo (2026-11-04).
    body = say(seeded, "me duele la rodilla izquierda, un 6")
    assert body["proposal"]["zones"][0]["zone"] == "knee-left"


def test_an_acknowledgement_takes_level_and_instant_from_the_status(
    seeded: TestClient, ollama: respx.MockRouter
) -> None:
    status = seeded.get("/api/status").json()
    alert = next(item for item in status["alerts"] if item["domain"] == "radiation")
    answer(ollama, "acknowledge_alert", {"domain": "radiation"}, "Vale.")
    body = say(seeded, "reconoce la alerta de radiación")
    assert body["proposal"] == {
        "subject": "crew-01", "domain": "radiation", "level": alert["level"],
        "reference_time": status["data"]["reference_time"],
    }
    signed = seeded.post("/api/alerts/acknowledge",
                         json={**body["proposal"], "acknowledged_by": "CMO"})
    assert signed.status_code == 201, signed.text


def test_an_alert_that_is_not_there_is_not_proposed(seeded: TestClient,
                                                   ollama: respx.MockRouter) -> None:
    answer(ollama, "acknowledge_alert", {"domain": "bone"}, "Vale.")
    body = say(seeded, "reconoce la alerta de hueso")
    assert body["proposal"] is None and "No hay ninguna alerta" in body["reply"]


def test_a_mission_level_keeps_only_the_reason_the_person_gave(
    seeded: TestClient, ollama: respx.MockRouter
) -> None:
    answer(ollama, "mission_level", {"level": "reduced", "reason": "falta energía"}, "Vale.")
    body = say(seeded, "pasa el nivel de misión a reducido, falta energía")
    assert body["proposal"] == {"level": "reduced", "reason": "falta energía"}
    signed = seeded.post("/api/mission-mode", json={**body["proposal"], "declared_by": "CMO"})
    assert signed.status_code == 201, signed.text
    # Un motivo que redacta el modelo no se firma; y bajar de nivel exige uno.
    answer(ollama, "mission_level", {"level": "minimal", "reason": "por mantenimiento"}, "Vale.")
    body = say(seeded, "pasa el nivel de misión a mínimo")
    assert body["proposal"] is None and "motivo" in body["reply"]


def test_a_mission_profile_is_proposed_unsigned_and_signs_by_its_route(
    seeded: TestClient, ollama: respx.MockRouter
) -> None:
    answer(ollama, "mission_profile", {"profile": "leo", "reason": "por mantenimiento"}, "Vale.")
    body = say(seeded, "cambia el entorno a órbita baja")
    # El motivo que redacta el modelo no se firma; el entorno sí, porque lo dijo la persona.
    assert body["proposal"] == {"profile": "leo", "reason": ""}
    assert body["needs_confirmation"] is True and "No se ha firmado nada" in body["reply"]
    assert seeded.get("/api/mission/profile").json()["version"] == 0  # nada firmado aún
    signed = seeded.post("/api/mission/profile", json={**body["proposal"], "declared_by": "CMO"})
    assert signed.status_code == 201, signed.text
    # El vigente no se vuelve a proponer.
    answer(ollama, "mission_profile", {"profile": "leo"}, "Vale.")
    again = say(seeded, "cambia el entorno a órbita baja")
    assert again["proposal"] is None and "ya es" in again["reply"]


@pytest.mark.parametrize(("text", "profile"), [
    ("cambia el entorno a órbita baja", "leo"),
    ("declara entorno superficie lunar", "lunar-surface"),
    ("EMMA, cambia el entorno a la superficie de Marte", "mars-surface"),
    ("declara el entorno tránsito a Marte", "mars-transit"),
])
def test_the_profile_is_routed_by_keywords_without_a_model(text: str, profile: str) -> None:
    assert catalog.keyword_intent(text, "crew") == ("mission_profile", {"profile": profile})


def test_a_profile_without_a_name_asks_which(seeded: TestClient,
                                             ollama: respx.MockRouter) -> None:
    answer(ollama, "mission_profile", {}, "Vale.")
    body = say(seeded, "cambia de entorno")
    assert body["proposal"] is None and "superficie lunar" in body["reply"]


def test_safe_mode_needs_a_reason_to_be_proposed(seeded: TestClient,
                                                ollama: respx.MockRouter) -> None:
    answer(ollama, "safe_mode", {"active": True}, "Vale.")
    assert say(seeded, "activa el modo seguro")["proposal"] is None
    answer(ollama, "safe_mode", {"active": True, "reason": "sospecha de fuga"}, "Vale.")
    body = say(seeded, "activa el modo seguro por sospecha de fuga")
    assert body["proposal"] == {"active": True, "reason": "sospecha de fuga"}
    signed = seeded.post("/api/safe-mode", json={**body["proposal"], "declared_by": "CMO"})
    assert signed.status_code == 201, signed.text


def test_ground_prepares_no_writes(seeded: TestClient, ollama: respx.MockRouter) -> None:
    answer(ollama, "diary_entry", {"key": "mood-valence", "value": 3}, "Vale.")
    body = say(seeded, "apunta ánimo 3", console="ground")
    assert body["intent"] == "none" and body["proposal"] is None
    assert body["reply"] == GROUND_REFUSAL
    # La propuesta tampoco sale si se le pide directamente con un contexto de Tierra.
    made = propose("diary_entry", {"key": "mood-valence", "value": 3.0}, text="ánimo 3",
                   context=context.AssistantContext("crew-01", "ground"), store=get_store(),
                   settings=get_settings_for(seeded), operator=None)
    assert made.body is None and made.reply == GROUND_REFUSAL
    # Al modelo de Tierra ni siquiera se le ofrecen.
    seen = answer(ollama, "read_status", {}, "Vale.")
    say(seeded, "¿cómo está?", console="ground")
    assert "diary_entry" not in seen[0]["format"]["properties"]["intent"]["enum"]


# --------------------------------------------------------------------------- #
# Tierra con su corte
# --------------------------------------------------------------------------- #


def test_the_ground_cut_is_the_last_reading_minus_one_light_time() -> None:
    class Comms:
        one_way_minutes = 20.0

    class Status:
        comms = Comms()

    class Assessed:
        status = Status()
        latest = dt.datetime(2026, 11, 10, 23, tzinfo=dt.UTC)

    assert context.ground_cut(Assessed()) == dt.datetime(2026, 11, 10, 22, 40,  # type: ignore[arg-type]
                                                         tzinfo=dt.UTC)
    Assessed.status.comms = None  # type: ignore[assignment]
    assert context.ground_cut(Assessed()) is None  # type: ignore[arg-type]


def test_ground_sees_only_what_has_arrived(seeded: TestClient, monkeypatch: pytest.MonkeyPatch,
                                          ollama: respx.MockRouter) -> None:
    status = seeded.get("/api/status").json()
    reference = dt.datetime.fromisoformat(status["data"]["reference_time"])
    cut = reference - dt.timedelta(days=2)
    monkeypatch.setattr(context, "ground_cut", lambda assessed: cut)
    seen = answer(ollama, "none", {}, "Vale.")
    say(seeded, "¿cuál es mi frecuencia cardiaca?", console="ground")
    user = seen[0]["messages"][1]["content"]
    assert f"datos recibidos hasta {cut.strftime('%Y-%m-%d %H:%M')}" in user
    late = (reference - dt.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
    assert late not in user
    expected = seeded.get("/api/status", params={"until": cut.isoformat()}).json()["summary"]
    assert expected in user


# --------------------------------------------------------------------------- #
# Segregación: nada entra en el ledger ni en el análisis (invariante 6)
# --------------------------------------------------------------------------- #


def test_a_turn_writes_nothing_in_the_ledger(seeded: TestClient,
                                            ollama: respx.MockRouter) -> None:
    store = get_store()
    before = (len(store.ledger), len(store.query("crew-01")), store.reading_signers())
    answer(ollama, "none", {}, "Vale.")
    for text in ("¿cómo estoy?", "apunta ánimo 3", "me duele la cabeza, un 4",
                 "reconoce la alerta de radiación", "activa el modo seguro por prueba"):
        say(seeded, text)
        say(seeded, text, console="ground")
    assert (len(store.ledger), len(store.query("crew-01")), store.reading_signers()) == before


def test_nothing_in_the_analysis_reads_the_assistant() -> None:
    """Ni el motor, ni el advisor, ni las alertas importan el asistente: no puede alimentarlos."""
    for folder in ("analysis", "advisor", "core", "ingest", "environment"):
        for path in (REPO / "backend" / "app" / folder).rglob("*.py"):
            assert "app.assistant" not in path.read_text(encoding="utf-8"), path


# --------------------------------------------------------------------------- #
# El inventario de la interfaz: toda la pantalla, solo para mirar
# --------------------------------------------------------------------------- #

NAVIGATION = ("open_panel", "read_panel", "toggle_mode", "switch_console", "scroll",
              "next_panel", "previous_panel")


def test_the_navigation_intents_are_reads_and_no_new_intent_writes() -> None:
    cat = catalog.catalog()
    for intent_id in NAVIGATION:
        assert cat.intents[intent_id].kind == "read", intent_id
        assert cat.intents[intent_id].route is None, intent_id
    assert {i.id for i in cat.intents.values() if i.kind == "write"} == catalog.WRITE_IDS
    raw = json.loads(catalog.INTENTS_PATH.read_text(encoding="utf-8"))
    broken = json.loads(json.dumps(raw))
    for item in broken["intents"]:
        if item["id"] == "open_panel":
            item.update(kind="write", route="POST /api/diary/entries", signer_field="recorded_by")
    with pytest.raises(catalog.CatalogError, match="seis"):
        catalog.validate(broken)
    broken = json.loads(json.dumps(raw))
    for item in broken["intents"]:
        if item["id"] == "toggle_mode":
            item["route"] = "POST /api/safe-mode"
    with pytest.raises(catalog.CatalogError, match="lectura"):
        catalog.validate(broken)


def test_the_inventory_names_only_panels_and_display_modes() -> None:
    cat = catalog.catalog()
    schemas = {item["id"]: item["args"] for item in catalog.describe()}
    assert schemas["open_panel"]["panel"]["enum"] == list(cat.panels)
    assert schemas["read_panel"]["panel"]["enum"] == list(cat.panels)
    # Los modos son los de presentación de `displayModes.ts`: ninguno escribe en el registro.
    display = (REPO / "frontend/src/components/displayModes.ts").read_text(encoding="utf-8")
    block = re.search(r"DEFAULT_MODES: DisplayModes = \{(.*?)\};", display, re.S)
    assert block
    flags = re.findall(r"(\w+): (?:true|false),", block.group(1))
    assert schemas["toggle_mode"]["mode"]["enum"] == flags
    assert set(cat.modes) == {*flags, "rotation"}
    for word in ("safe", "sign", "firma", "mission", "acknowledge"):
        assert not any(word in mode.lower() for mode in cat.modes), word
    for panel in cat.panels.values():
        assert panel.places and panel.aliases and panel.label


def test_an_inventory_that_breaks_its_rules_does_not_load() -> None:
    raw = json.loads(catalog.INTENTS_PATH.read_text(encoding="utf-8"))
    ui = json.loads(catalog.UI_PATH.read_text(encoding="utf-8"))
    broken = json.loads(json.dumps(ui))
    broken["panels"].append(dict(broken["panels"][0]))
    with pytest.raises(catalog.CatalogError, match="repetido"):
        catalog.validate(raw, broken)
    broken = json.loads(json.dumps(ui))
    broken["panels"][0]["places"] = [{"console": "crew", "section": "trends"}]
    with pytest.raises(catalog.CatalogError, match="pestaña"):
        catalog.validate(raw, broken)
    broken = json.loads(json.dumps(ui))
    broken["panels"][0]["aliases"] = ["Radiación"]
    with pytest.raises(catalog.CatalogError, match="tildes"):
        catalog.validate(raw, broken)


@pytest.mark.parametrize(("text", "console", "intent", "args"), [
    # Las veinticuatro órdenes reales del 2026-11-03 que fallaban con gemma4 y qwen3.5.
    ("¿qué medidas tengo pendientes?", "crew", "read_routines", {}),
    ("¿qué significa línea base?", "crew", "open_glossary", {"term": "baseline"}),
    ("letra más grande, que no veo bien", "crew", "low_vision", {"on": True}),
    ("cállate", "crew", "stop_voice", {}),
    ("pon la pantalla derecha", "crew", "rotate", {"degrees": 0}),
    ("ponla boca abajo", "crew", "rotate", {"degrees": 180}),
    ("repítelo", "crew", "repeat_voice", {}),
    ("¿qué tal la radiación hoy?", "crew", "read_panel", {"panel": "dose"}),
    ("¿qué tal la radiación hoy?", "ground", "read_status", {}),
    # Lo que antes no alcanzaba.
    ("lee el panel de radiación", "crew", "read_panel", {"panel": "dose"}),
    ("abre el panel de radiación", "crew", "open_panel", {"panel": "dose"}),
    ("abre la crónica", "crew", "open_panel", {"panel": "chronicle"}),
    ("despliega el detalle de la alerta", "crew", "open_panel", {"panel": "alert-detail"}),
    ("muéstrame los bancos de prueba", "ground", "open_panel", {"panel": "testbeds"}),
    ("siguiente panel", "crew", "next_panel", {}),
    ("panel anterior", "ground", "previous_panel", {}),
    ("enciende seguir la cara", "crew", "toggle_mode", {"mode": "followFace", "on": True}),
    ("deja de seguir el sensor", "crew", "toggle_mode", {"mode": "followSensor", "on": False}),
    ("activa escuchar EMMA", "crew", "toggle_mode", {"mode": "wakeWord", "on": True}),
    ("apaga la iniciativa", "crew", "toggle_mode", {"mode": "proactive", "on": False}),
    ("pon la voz de las alertas", "crew", "toggle_mode", {"mode": "voice", "on": True}),
    ("pasa a la consola de Tierra", "crew", "switch_console", {"console": "ground"}),
    ("cambia de consola", "ground", "switch_console", {"console": "crew"}),
    ("baja un poco", "crew", "scroll", {"direction": "down"}),
    ("EMMA, sube", "crew", "scroll", {"direction": "up"}),
    ("vuelve al principio", "crew", "scroll", {"direction": "top"}),
    # Lo que no tiene que confundirse.
    ("¿me sube la tensión?", "crew", "none", {}),
    ("léeme las alertas", "crew", "read_alerts", {}),
    ("abre radiación", "crew", "open_tab", {"section": "radiation"}),
])
def test_keywords_reach_the_whole_interface(text: str, console: str, intent: str,
                                            args: dict[str, Any]) -> None:
    assert turn._keyword_turn(text, console) == (intent, args)


def test_every_panel_is_reachable_by_its_own_name() -> None:
    """Cada panel, apartado y pliegue se pide por su nombre y llega a él (o a uno igual de largo
    con el mismo nombre)."""
    cat = catalog.catalog()
    for panel in cat.panels.values():
        console = panel.places[0].console
        found = catalog.panel_for(catalog.plain(f"abre el panel {panel.aliases[0]}"), console)
        assert found is not None, panel.id
        assert panel.aliases[0] in cat.panels[found].aliases, (panel.id, found)


def test_a_screen_command_does_not_ask_the_model(seeded: TestClient,
                                                ollama: respx.MockRouter) -> None:
    seen = answer(ollama, "rotate", {"degrees": 90}, "Giro a 90.")
    body = say(seeded, "pon la pantalla derecha")
    assert (body["intent"], body["args"]) == ("rotate", {"degrees": 0})
    assert say(seeded, "cállate")["intent"] == "stop_voice"
    repeated = say(seeded, "repítelo")
    assert repeated["intent"] == "repeat_voice" and repeated["reply_source"] == "fixed"
    assert seen == []


def test_when_the_model_finds_nothing_the_words_decide(seeded: TestClient,
                                                      ollama: respx.MockRouter) -> None:
    answer(ollama, "none", {}, "No lo sé.")
    body = say(seeded, "¿cómo estoy?")
    assert body["intent"] == "read_status"
    assert body["reply"] == seeded.get("/api/status").json()["summary"]
    assert body["reply_source"] == "backend"
    assert say(seeded, "¿qué medidas tengo pendientes?")["intent"] == "read_routines"
    radiation = say(seeded, "¿qué tal la radiación hoy?")
    assert (radiation["intent"], radiation["args"]) == ("read_panel", {"panel": "dose"})


def test_the_glossary_definition_is_read_as_the_backend_writes_it(
    seeded: TestClient, ollama: respx.MockRouter
) -> None:
    terms = {item["id"]: item for item in seeded.get("/api/glossary").json()["terms"]}
    expected = f"{terms['baseline']['term']}: {terms['baseline']['definition']}"
    answer(ollama, "none", {}, "No tengo esa definición.")
    body = say(seeded, "¿qué significa línea base?")
    assert (body["intent"], body["args"]) == ("open_glossary", {"term": "baseline"})
    assert body["reply"] == expected and body["reply_source"] == "backend"
    answer(ollama, "open_glossary", {"term": "baseline"}, "Es lo normal para ti.")
    assert say(seeded, "cuéntame lo de la línea base")["reply"] == expected


def test_a_panel_the_inventory_does_not_have_fails_the_schema(seeded: TestClient,
                                                             ollama: respx.MockRouter) -> None:
    answer(ollama, "open_panel", {"panel": "boton-de-firmar"}, "Abro.")
    body = say(seeded, "abre el panel de firmar")
    assert body["intent"] != "open_panel" and body["checks"]["schema"] is False


def test_the_model_sees_the_panels_of_its_console(seeded: TestClient,
                                                 ollama: respx.MockRouter) -> None:
    seen = answer(ollama, "none", {}, "Vale.")
    say(seeded, "¿y la radiación del dosímetro?")
    say(seeded, "¿y la radiación del dosímetro?", console="ground")
    crew, ground = (request["messages"][0]["content"] for request in seen)
    assert "mission «Misión y hábitat»" in crew and "trends «Tendencias»" not in crew
    assert "trends «Tendencias»" in ground and "mission «Misión y hábitat»" not in ground
    assert "followFace (Seguir la cara (demo)" in crew
    # Los paneles van en el mapa de cada turno, solo los de esa consola.
    crew_map, ground_map = (request["messages"][1]["content"] for request in seen)
    assert "- dose «Radiación»" in crew_map and "- dose «Radiación»" not in ground_map


# --------------------------------------------------------------------------- #
# El contexto se reutiliza mientras el registro no cambie
# --------------------------------------------------------------------------- #


def test_the_context_is_reused_until_the_ledger_grows(seeded: TestClient,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[str] = []
    real = context._build

    def counting(*args: Any) -> context.AssistantContext:
        built.append(args[2])
        return real(*args)

    monkeypatch.setattr(context, "_build", counting)
    settings, store = get_settings_for(seeded), get_store()
    first = context.build(settings, store, "crew-01", "crew")
    assert context.build(settings, store, "crew-01", "crew") is first
    assert built == ["crew-01"]
    # Otra consola u otro tripulante son otro contexto.
    context.build(settings, store, "crew-01", "ground")
    assert len(built) == 2
    # Una observación nueva (aquí, del diario) cambia el registro: se vuelve a evaluar.
    signed = seeded.post("/api/diary/entries", json={
        "key": "mood-valence", "value": 4, "subject": "crew-01", "recorded_by": "CMO"})
    assert signed.status_code == 201, signed.text
    again = context.build(settings, store, "crew-01", "crew")
    assert again is not first and len(built) == 3


def test_the_context_cache_expires(seeded: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    settings, store = get_settings_for(seeded), get_store()
    first = context.build(settings, store, "crew-01", "crew")
    monkeypatch.setattr(context, "CACHE_SECONDS", 0.0)
    assert context.build(settings, store, "crew-01", "crew") is not first

def test_a_panel_named_by_its_own_words_is_not_reinterpreted(seeded: TestClient,
                                                            ollama: respx.MockRouter) -> None:
    """Visto con qwen3.5:9b el 2026-11-03: el modelo cambiaba el panel nombrado por otro."""
    seen = answer(ollama, "read_panel", {"panel": "alerts"}, "Te leo las alertas.")
    body = say(seeded, "despliega el detalle de la alerta")
    assert (body["intent"], body["args"]) == ("open_panel", {"panel": "alert-detail"})
    radiation = say(seeded, "¿qué tal la radiación hoy?")
    assert (radiation["intent"], radiation["args"]) == ("read_panel", {"panel": "dose"})
    assert seen == []

# --------------------------------------------------------------------------- #
# Conocimiento del modelo, sin fuente: lo no clínico, rotulado aparte
# --------------------------------------------------------------------------- #

GENERAL_LABEL = "conocimiento del modelo, sin fuente"


def general(router: respx.MockRouter, reply: str) -> list[Any]:
    """El modelo contesta de cultura general (`topic: general`)."""
    seen: list[Any] = []

    def chat(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        content = json.dumps({"intent": "none", "args": {}, "reply": reply, "topic": "general"})
        return httpx.Response(200, json={"message": {"content": content}, "done_reason": "stop"})

    router.post(f"{LLM}/api/chat").mock(side_effect=chat)
    return seen


def test_a_general_question_is_answered_and_labelled_apart(seeded: TestClient,
                                                          ollama: respx.MockRouter) -> None:
    seen = general(ollama,
                   "La luz del Sol tarda unos 8 minutos y 20 segundos en llegar a la Tierra.")
    body = say(seeded, "¿cuánto tarda la luz del Sol a la Tierra?")
    assert body["reply_source"] == "general" and body["label"] == GENERAL_LABEL
    assert catalog.catalog().general_label == GENERAL_LABEL
    assert body["label"] != catalog.catalog().model_label
    assert body["reply"].startswith("La luz del Sol") and all(body["checks"].values())
    assert seen[0]["format"]["properties"]["topic"]["enum"] == ["emma", "general"]
    # En Tierra igual.
    assert say(seeded, "¿qué es la Estación Espacial Internacional?", console="ground")[
        "reply_source"] == "general"


@pytest.mark.parametrize("question", [
    "¿es mucha la radiación que llevo?",
    "¿qué tal está crew-01?",
    "¿qué es la frecuencia cardiaca?",
    "¿es grave un dolor de rodilla?",
    "¿qué significa línea base personal en otra misión?",
    "¿qué me tomo para dormir?",
])
def test_a_question_about_health_or_the_crew_is_never_general(
    seeded: TestClient, ollama: respx.MockRouter, question: str
) -> None:
    general(ollama, "Es poca, no te preocupes.")
    body = say(seeded, question)
    assert body["reply_source"] != "general" and body["label"] != GENERAL_LABEL
    # Si se dice, es como cualquier respuesta del modelo con el contexto de EMMA: con su rótulo.
    if body["reply"] == "Es poca, no te preocupes.":
        assert body["reply_source"] == "model" and body["label"] == catalog.catalog().model_label


@pytest.mark.parametrize("reply", [
    "En la Estación la frecuencia cardiaca suele bajar.",
    "Allí se reciben unos 0,5 mSv al día.",
    "Una tensión de 120 mmHg es normal.",
    "La temperatura de la nave es de 22 °C.",
    "Tómate un ibuprofeno.",
    "crew-01 está bien.",
    "Es seguro, sin duda.",
])
def test_a_general_answer_that_touches_anything_clinical_is_not_said(
    seeded: TestClient, ollama: respx.MockRouter, reply: str
) -> None:
    general(ollama, reply)
    body = say(seeded, "¿qué hay en la Estación Espacial Internacional?")
    assert body["reply_source"] == "fixed" and body["reply"] != reply


def test_the_general_barrier() -> None:
    crew = ["crew-01", "Ana Pérez"]
    assert guards.general_ok("Marte está a unos 225 millones de kilómetros de media.", crew)
    assert not guards.general_ok("Ana Pérez lo sabe.", crew)
    assert not guards.general_ok("Son 70 lpm de media.", crew)
    assert not guards.general_ok("Hay un 21 % de oxígeno.", crew)
    assert not guards.general_ok("La saturación de oxígeno baja en altura.", crew)
    assert not guards.general_ok("Duele la rodilla izquierda.", crew)
    assert guards.about_crew_or_health("¿cómo está mi corazón?", crew)
    assert guards.about_crew_or_health("¿qué es el modo seguro?", crew)  # término del glosario
    assert not guards.about_crew_or_health("¿qué hora es en Houston?", crew)

# Lo que cazó la revisión de código del 2026-11-03 sobre la navegación y lo general.

@pytest.mark.parametrize(("text", "not_intent"), [
    ("¿la cámara está grabando?", "toggle_mode"),
    ("¿hay cámara hiperbárica a bordo?", "toggle_mode"),
    ("¿cuál es el siguiente paso?", "next_panel"),
    ("¿qué pasó al final de la misión Apolo 13?", "scroll"),
    ("¿cuáles son los nutrientes esenciales?", "essential"),
    ("¿qué hace la consola de Tierra con el retardo?", "switch_console"),
    ("apunta que he dormido bastante", "stop_voice"),
    ("muéstrame mi estado", "open_panel"),
])
def test_an_ordinary_sentence_does_not_press_a_screen_command(text: str, not_intent: str) -> None:
    assert turn._keyword_turn(text, "crew")[0] != not_intent


def test_a_medication_question_gets_the_refusal_even_naming_pain_or_a_panel(
    seeded: TestClient, ollama: respx.MockRouter
) -> None:
    answer(ollama, "none", {}, "Vale.")
    for text in ("¿Qué me tomo para el dolor de cabeza?", "¿qué puedo tomar? ¿qué tal la dosis?"):
        body = say(seeded, text)
        assert (body["intent"], body["proposal"]) == ("none", None), text
        assert body["reply"] == turn.NO_PRESCRIPTION, text
    assert say(seeded, "abre dosis")["intent"] == "open_tab"


def test_a_general_question_is_not_overridden_by_a_loose_keyword(
    seeded: TestClient, ollama: respx.MockRouter
) -> None:
    general(ollama, "Desde Marte, la Tierra se ve como un punto azul brillante.")
    body = say(seeded, "¿qué tal se ve la Tierra desde Marte?")
    assert body["reply_source"] == "general"


def test_a_health_question_marked_general_goes_through_the_emma_barriers(
    seeded: TestClient, ollama: respx.MockRouter
) -> None:
    general(ollama, "Eso no lo tengo en lo que da EMMA.")
    body = say(seeded, "¿cuánto dura mi turno de sueño?")
    assert body["reply_source"] == "model" and body["label"] != GENERAL_LABEL


def test_two_panels_cannot_share_a_name() -> None:
    raw = json.loads(catalog.INTENTS_PATH.read_text(encoding="utf-8"))
    ui = json.loads(catalog.UI_PATH.read_text(encoding="utf-8"))
    ui["panels"][1]["aliases"] = [*ui["panels"][1]["aliases"], ui["panels"][0]["aliases"][0]]
    with pytest.raises(catalog.CatalogError, match="alias"):
        catalog.validate(raw, ui)

def test_the_model_is_warmed_once_in_the_background(ollama: respx.MockRouter,
                                                   tmp_path: Path) -> None:
    from app.api import assistant as assistant_api
    from app.core.config import Settings

    seen = answer(ollama, "none", {}, "")
    assistant_api._warmed.clear()
    settings = Settings(cache_dir=tmp_path, offline=True)
    llm = assistant_api.llm_for(settings)
    thread = assistant_api.warm_up(settings, llm)
    assert thread is not None
    thread.join(timeout=10)
    assert len(seen) == 1 and seen[0]["model"] == settings.assistant_model
    assert assistant_api.warm_up(settings, llm) is None  # una sola vez
    # Apagado (las pruebas, por `conftest.py`), ni se intenta.
    off = Settings(cache_dir=tmp_path, offline=True, assistant_warmup=False)
    assistant_api._warmed.clear()
    assert assistant_api.warm_up(off, llm) is None
    # Sin Ollama no rompe, y se vuelve a intentar la próxima vez.
    ollama.post(f"{LLM}/api/chat").mock(side_effect=httpx.ConnectError("apagado"))
    failed = assistant_api.warm_up(settings, llm)
    assert failed is not None
    failed.join(timeout=10)
    assert (llm.base_url, llm.model) not in assistant_api._warmed
    assistant_api._warmed.clear()

# --------------------------------------------------------------------------- #
# Audio: Whisper local y el mismo turno
# --------------------------------------------------------------------------- #


def test_audio_without_whisper_is_503(seeded: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(voice, "ready", lambda: False)
    response = seeded.post("/api/assistant/audio", params={"console": "crew",
                                                           "subject": "crew-01"}, content=OGG)
    assert response.status_code == 503


def wav(seconds: float = 0.5, rate: int = 16000, channels: int = 1, width: int = 2) -> bytes:
    """Un WAV pequeño de silencio, hecho aquí."""
    out = io.BytesIO()
    with wave.open(out, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(width)
        writer.setframerate(rate)
        writer.writeframes(b"\x00" * int(seconds * rate) * channels * width)
    return out.getvalue()


AUDIO = {"console": "crew", "subject": "crew-01"}


@pytest.mark.parametrize(("body", "why"), [
    (b"MP3?" + b"\x00" * 32, "Ogg"),
    (wav(channels=2), "mono"),
    (wav(width=1), "16 bits"),
    (wav(rate=44100), "44100 Hz"),
    (wav(seconds=61, rate=8000), "más de 60 s"),
    (b"RIFF\x00\x00\x00\x00WAVEbasura", "ilegible"),
], ids=["no-ogg", "estereo", "8-bits", "44100", "largo", "ilegible"])
def test_audio_that_cannot_be_transcribed_is_422(seeded: TestClient, body: bytes,
                                                 why: str) -> None:
    response = seeded.post("/api/assistant/audio", params=AUDIO, content=body)
    assert response.status_code == 422 and why in response.json()["detail"], response.text


def _fake_turn_audio(monkeypatch: pytest.MonkeyPatch, said: str) -> list[list[str]]:
    from tests.test_voice import _fake_whisper

    monkeypatch.setattr(voice, "ready", lambda: True)
    monkeypatch.setattr(voice.memguard, "run", _fake_whisper(said))
    converted: list[list[str]] = []

    def convert(command: list[str], **kwargs: Any) -> Any:
        converted.append(command)
        Path(command[-1]).write_bytes(OGG)  # el Ogg/Opus que dejaría soundfile
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(audio.subprocess, "run", convert)
    return converted


def test_ogg_audio_becomes_a_turn_without_converting(seeded: TestClient,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    converted = _fake_turn_audio(monkeypatch, "abre radiación")
    response = seeded.post("/api/assistant/audio", params=AUDIO, content=OGG)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transcript"] == "abre radiación"
    assert body["turn"]["intent"] == "open_tab" and body["turn"]["args"] == {"section": "radiation"}
    assert converted == []


def test_wav_audio_is_converted_in_the_voice_environment(
    seeded: TestClient, monkeypatch: pytest.MonkeyPatch, ollama: respx.MockRouter
) -> None:
    converted = _fake_turn_audio(monkeypatch, "¿y ayer?")
    seen = answer(ollama, "read_status", {}, "Vale.")
    history = base64.b64encode(json.dumps(
        [{"role": "user", "text": "¿cómo estás, señora?"}]).encode("utf-8")).decode()
    response = seeded.post(
        "/api/assistant/audio", params=AUDIO, content=wav(),
        headers={"X-EMMA-History": history, "X-EMMA-Operator": "Jos%C3%A9"},
    )
    assert response.status_code == 200, response.text
    [command] = converted
    assert command[0] == str(voice._python()) and "OPUS" in command[3]
    assert "persona: ¿cómo estás, señora?" in seen[0]["messages"][1]["content"]
    # Y el operador llega a la propuesta.
    answer(ollama, "safe_mode", {"active": True, "reason": "prueba"}, "Vale.")
    _fake_turn_audio(monkeypatch, "activa el modo seguro por prueba")
    response = seeded.post("/api/assistant/audio", params=AUDIO, content=wav(),
                           headers={"X-EMMA-Operator": "Jos%C3%A9"})
    assert "Firmará José" in response.json()["turn"]["reply"]


def test_a_bad_history_header_is_422(seeded: TestClient) -> None:
    for value in ("no-es-base64!", base64.b64encode(b"[1]").decode(),
                  base64.b64encode(json.dumps([{"role": "user", "text": "x"}] * 9).encode())
                  .decode()):
        response = seeded.post("/api/assistant/audio", params=AUDIO, content=OGG,
                               headers={"X-EMMA-History": value})
        assert response.status_code == 422, value


@pytest.mark.skipif(not voice.ready(), reason="sin el entorno de la voz (scripts/install_voice.py)")
def test_the_voice_environment_really_writes_ogg_opus() -> None:
    """Sin red: el `soundfile` del entorno de la voz convierte un WAV de verdad."""
    assert audio.wav_to_ogg(wav()).startswith(b"OggS")


# --------------------------------------------------------------------------- #
# Audio: el propio modelo oye (gemma4:e4b, 2026-11-06)
# --------------------------------------------------------------------------- #


def _hears(router: respx.MockRouter, said: str | Exception) -> list[Any]:
    """El modelo declara `audio` y transcribe `said` (o falla con esa excepción).

    Devuelve las peticiones de transcripción; las del turno (sin audio) contestan read_status.
    """
    router.post(f"{LLM}/api/show").mock(
        return_value=httpx.Response(200, json={"capabilities": ["completion", "audio"]}))
    heard: list[Any] = []

    def chat(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if any(message.get("images") for message in body["messages"]):
            heard.append(body)
            if isinstance(said, Exception):
                raise said
            content = json.dumps({"text": said})
        else:
            content = json.dumps({"intent": "read_status", "args": {}, "reply": "Vale."})
        return httpx.Response(200, json={"message": {"content": content}, "done_reason": "stop"})

    router.post(f"{LLM}/api/chat").mock(side_effect=chat)
    return heard


def test_a_model_that_hears_gets_the_wav_and_whisper_is_not_used(
    seeded: TestClient, monkeypatch: pytest.MonkeyPatch, ollama: respx.MockRouter
) -> None:
    converted = _fake_turn_audio(monkeypatch, "esto lo diría Whisper")
    heard = _hears(ollama, "oye EMMA, abre radiación")
    sound = wav()
    response = seeded.post("/api/assistant/audio", params=AUDIO, content=sound)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transcript"] == "oye EMMA, abre radiación" and body["heard_by"] == "model"
    assert body["turn"]["intent"] == "open_tab"
    assert converted == []
    [request] = heard
    assert request["model"] == MODEL and request["options"]["temperature"] == 0
    assert request["messages"][0]["content"] == llm_module.HEARING_PROMPT
    assert base64.b64decode(request["messages"][1]["images"][0]) == sound
    status = seeded.get("/api/assistant").json()
    assert status["voice_available"] is True and status["voice_by"] == "model"


def test_ogg_still_goes_to_whisper_when_the_model_hears(
    seeded: TestClient, monkeypatch: pytest.MonkeyPatch, ollama: respx.MockRouter
) -> None:
    _fake_turn_audio(monkeypatch, "abre radiación")
    heard = _hears(ollama, "no debería oírse")
    response = seeded.post("/api/assistant/audio", params=AUDIO, content=OGG)
    assert response.json()["heard_by"] == "whisper" and heard == []


def test_hearing_whisper_only_skips_the_model(
    seeded: TestClient, monkeypatch: pytest.MonkeyPatch, ollama: respx.MockRouter,
    tmp_path: Path
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, assistant_warmup=False, assistant_hearing="whisper")
    _fake_turn_audio(monkeypatch, "abre radiación")
    heard = _hears(ollama, "no debería oírse")
    response = seeded.post("/api/assistant/audio", params=AUDIO, content=wav())
    assert response.json()["heard_by"] == "whisper" and heard == []
    assert seeded.get("/api/assistant").json()["voice_by"] == "whisper"


def test_a_failing_model_falls_back_to_whisper_or_is_503(
    seeded: TestClient, monkeypatch: pytest.MonkeyPatch, ollama: respx.MockRouter
) -> None:
    _fake_turn_audio(monkeypatch, "abre radiación")
    _hears(ollama, httpx.ReadTimeout("lento"))
    response = seeded.post("/api/assistant/audio", params=AUDIO, content=wav())
    assert response.status_code == 200 and response.json()["heard_by"] == "whisper"
    monkeypatch.setattr(voice, "ready", lambda: False)
    response = seeded.post("/api/assistant/audio", params=AUDIO, content=wav())
    assert response.status_code == 503, response.text


@pytest.mark.parametrize(("body", "why"), [
    (wav(channels=2), "mono"),
    (wav(seconds=61, rate=8000), "más de 60 s"),
], ids=["estereo", "largo"])
def test_the_model_gets_the_same_wav_limits_as_whisper(
    seeded: TestClient, ollama: respx.MockRouter, body: bytes, why: str
) -> None:
    heard = _hears(ollama, "no debería oírse")
    response = seeded.post("/api/assistant/audio", params=AUDIO, content=body)
    assert response.status_code == 422 and why in response.json()["detail"]
    assert heard == []


def test_silence_heard_by_the_model_is_422(seeded: TestClient, ollama: respx.MockRouter) -> None:
    _hears(ollama, "  ")
    response = seeded.post("/api/assistant/audio", params=AUDIO, content=wav())
    assert response.status_code == 422 and "no se ha entendido" in response.json()["detail"]


SHOWN = [
    {"label": "Abdomen: hígado 1", "writes": True},
    {"label": "Abdomen: hígado 2", "writes": True},
    {"label": "Cabeza: órbitas 1", "writes": True},
    {"label": "Visor de Polaris", "writes": False},
    {"label": "Render de Polaris", "writes": False},
]


@pytest.mark.parametrize(("said", "label", "confirm"), [
    ("abdomen higado 1 de volumenes 3d", "Abdomen: hígado 1", True),
    ("cabeza órbitas primera", "Cabeza: órbitas 1", True),
    ("pulsa render de polaris", "Render de Polaris", False),
    ("visor de polaris", "Visor de Polaris", False),
], ids=["con-panel", "ordinal", "verbo", "dos-palabras"])
def test_a_button_on_screen_said_by_its_label_is_pressed(
    seeded: TestClient, said: str, label: str, confirm: bool
) -> None:
    body = say(seeded, said, controls=SHOWN)
    assert body["intent"] == "press" and body["args"] == {"control": label}
    assert body["needs_confirmation"] is confirm and body["proposal"] is None
    assert ("confirmo" in body["reply"]) is confirm and label in body["reply"]


def test_a_button_is_only_one_of_those_on_screen(seeded: TestClient) -> None:
    # Sin botones a la vista no hay nada que pulsar.
    assert say(seeded, "abdomen higado 1 de volumenes 3d")["intent"] != "press"
    # Dos que empatan: pregunta cuál, sin pulsar.
    body = say(seeded, "pulsa abdomen hígado", controls=SHOWN)
    assert body["intent"] == "none" and "¿Cuál pulso?" in body["reply"]
    # Una palabra suelta sin verbo de pulsar no pulsa: «render» solo no es una orden.
    assert say(seeded, "render", controls=SHOWN)["intent"] != "press"


def test_the_model_picks_a_button_only_from_the_list(
    seeded: TestClient, ollama: respx.MockRouter
) -> None:
    seen = answer(ollama, "press", {"control": "abdomen: HIGADO 2"}, "Vale.")
    body = say(seeded, "ponme el TAC del segundo hígado", controls=SHOWN)
    assert body["intent"] == "press" and body["args"] == {"control": "Abdomen: hígado 2"}
    assert body["needs_confirmation"] is True
    prompt = seen[0]["messages"][1]["content"]
    assert "BOTONES A LA VISTA" in prompt and "«Visor de Polaris»" in prompt
    assert "«Abdomen: hígado 1» (guarda algo)" in prompt
    # Uno que no está en la lista no se pulsa ni se dice.
    answer(ollama, "press", {"control": "Borrar todo"}, "Borro todo.")
    body = say(seeded, "ponme el TAC del segundo hígado", controls=SHOWN)
    assert body["intent"] != "press" and "Borro" not in body["reply"]
    # Sin botones, el prompt es el de siempre.
    seen = answer(ollama, "none", {}, "Vale.")
    say(seeded, "ponme el TAC del segundo hígado")
    assert "BOTONES A LA VISTA" not in seen[0]["messages"][1]["content"]


def test_buttons_travel_with_a_spoken_turn(
    seeded: TestClient, monkeypatch: pytest.MonkeyPatch, ollama: respx.MockRouter
) -> None:
    _fake_turn_audio(monkeypatch, "abdomen hígado 1")
    shown = base64.b64encode(json.dumps(SHOWN).encode("utf-8")).decode()
    response = seeded.post("/api/assistant/audio", params=AUDIO, content=OGG,
                           headers={"X-EMMA-Controls": shown})
    assert response.status_code == 200, response.text
    assert response.json()["turn"]["args"] == {"control": "Abdomen: hígado 1"}
    bad = base64.b64encode(json.dumps([{"label": ""}]).encode()).decode()
    response = seeded.post("/api/assistant/audio", params=AUDIO, content=OGG,
                           headers={"X-EMMA-Controls": bad})
    assert response.status_code == 422


def test_what_a_model_hears_is_remembered_but_not_a_network_failure(
    ollama: respx.MockRouter
) -> None:
    client = llm_module.LocalLlm(LLM, "gemma4:e4b")
    show = ollama.post(f"{LLM}/api/show")
    show.mock(side_effect=httpx.ConnectError("apagado"))
    assert client.hears() is False and show.call_count == 1
    show.mock(return_value=httpx.Response(200, json={"capabilities": ["audio"]}))
    assert client.hears() is True and client.hears() is True
    assert show.call_count == 2


# --------------------------------------------------------------------------- #
# El mapa de la aplicación, el enrutado de la calle y la tripulación (2026-11-04)
# --------------------------------------------------------------------------- #

EVAL = Path(__file__).resolve().parent / "data" / "assistant_nl_eval.json"


def test_every_inventory_entry_says_what_it_holds() -> None:
    """Cada pestaña, panel, pliegue, modo y consola dice qué enseña y qué deja hacer, corto."""
    cat = catalog.catalog()
    entries = [*cat.panels.values(), *cat.modes.values(), *cat.consoles.values(),
               *(section for sections in cat.sections.values() for section in sections)]
    assert entries
    for entry in entries:
        assert entry.about.strip(), entry
        assert len(entry.about) <= catalog.ABOUT_MAX, entry
    served = catalog.ui_inventory()
    assert all(panel["about"] for panel in served["panels"])


@pytest.mark.parametrize("about", [None, "", "   ", "x" * 201, "dos\nlíneas"])
def test_an_entry_without_a_short_about_does_not_load(about: str | None) -> None:
    raw = json.loads(catalog.INTENTS_PATH.read_text(encoding="utf-8"))
    ui = json.loads(catalog.UI_PATH.read_text(encoding="utf-8"))
    for broken in (ui["panels"][0], ui["sections"]["crew"][0], ui["modes"][0]):
        copy = json.loads(json.dumps(ui))
        target = next(item for group in (copy["panels"], copy["sections"]["crew"], copy["modes"])
                      for item in group if item == broken)
        if about is None:
            del target["about"]
        else:
            target["about"] = about
        with pytest.raises(catalog.CatalogError):
            catalog.validate(raw, copy)


@pytest.mark.parametrize(("text", "console", "expected"), [
    # Por lo que hay DENTRO del panel, no por su rótulo.
    ("¿cómo está el aire de la nave?", "crew", "habitat"),
    ("¿cuánta radiación llevo acumulada?", "crew", "dose"),
    ("dónde veo lo que he comido", "crew", "food-acceptability"),
    ("QUIERO VER LA DOSIS DE RADIACIÓN", "crew", "dose"),
    ("las gráficas de la evolución", "ground", "trends"),
])
def test_the_map_finds_a_panel_by_what_is_inside(text: str, console: str, expected: str) -> None:
    top = [item.key for item in retrieval.candidates(text, console)[:3]]
    assert expected in top, top


def test_the_map_widens_with_synonyms_and_ignores_accents() -> None:
    assert retrieval.stems("Sueño") == retrieval.stems("sueno")
    assert "sueno" in retrieval.expand(retrieval.stems("he dormido mal"))
    assert "co2" in retrieval.expand(retrieval.stems("el aire"))
    assert retrieval.rank("de la", "crew") == []  # sin palabras con contenido no hay candidatos
    # Solo paneles de esa consola.
    assert all(catalog.catalog().panels[item.key].in_console("ground")
               for item in retrieval.candidates("radiación y hábitat", "ground"))


def test_the_map_goes_in_the_turn_prompt_and_the_system_prompt_holds_nothing_of_the_turn(
    seeded: TestClient, ollama: respx.MockRouter
) -> None:
    seen = answer(ollama, "none", {}, "Vale.")
    say(seeded, "¿qué tal está el aire de la nave hoy?")
    say(seeded, "hola")
    first, second = seen
    assert first["messages"][0]["content"] == second["messages"][0]["content"]
    system, user = (message["content"] for message in first["messages"])
    assert "MAPA" in user and "- habitat «Tripulación y hábitat»" in user
    assert "aire de la nave" not in system
    # Las pestañas con lo que hay dentro, y los ejemplos de frases de la calle.
    assert "mission «Misión y hábitat»" in system and "CO2" in system
    assert "estoy de bajón, apúntalo" in system
    assert first["options"]["num_ctx"] == 12288
    # Las listas largas, solo si la frase (o lo último que dijo la persona) las puede necesitar.
    assert "team-cohesion-cared" not in system and "knee (Rodilla)" not in system
    built = context.build(get_settings_for(seeded), get_store(), "crew-01", "crew")
    diary = turn.model_messages("apúntalo en el diario", "crew", built, [])[0]["content"]
    assert "team-cohesion-cared" in diary
    later = turn.model_messages("un 6", "crew", built,
                                [{"role": "user", "text": "me duele la rodilla"}])[0]["content"]
    assert "knee (Rodilla)" in later


def test_model_messages_are_exactly_what_is_sent(seeded: TestClient,
                                                 ollama: respx.MockRouter) -> None:
    seen = answer(ollama, "none", {}, "Vale.")
    history = [{"role": "user", "text": "hola"}, {"role": "assistant", "text": "Hola."}]
    say(seeded, "¿qué tal el ruido de la cabina?", history=history, modes={"privacy": True})
    built = context.build(get_settings_for(seeded), get_store(), "crew-01", "crew")
    messages = turn.model_messages("¿qué tal el ruido de la cabina?", "crew", built, history,
                                   {"privacy": True})
    assert seen[0]["messages"] == messages
    assert "Privacidad" in messages[1]["content"]
    assert seen[0]["format"] == turn.answer_schema("crew")
    expected = json.loads(turn.expected_answer("open_tab", {"section": "mission"}, "Abro."))
    assert set(expected) == set(turn.answer_schema("crew")["required"])


def test_the_prompt_fits_the_context_window(seeded: TestClient) -> None:
    """Sistema, mapa, contexto y ocho turnos largos de historial caben en el contexto pedido
    (cuatro caracteres por token es generoso para el español; medido: unos 3,4)."""
    from app.api.assistant import CONTEXT_TOKENS

    built = context.build(get_settings_for(seeded), get_store(), "crew-01", "crew")
    history = [{"role": "user", "text": "x" * 200}] * turn.MAX_HISTORY
    for console in ("crew", "ground"):
        messages = turn.model_messages("¿cómo está el aire de la nave?", console, built, history)
        chars = sum(len(message["content"]) for message in messages)
        assert chars / 3.4 < CONTEXT_TOKENS - 600, chars


def test_every_example_is_valid_and_a_broken_one_does_not_load() -> None:
    assert len(catalog.examples()) >= 30
    raw = json.loads(catalog.EXAMPLES_PATH.read_text(encoding="utf-8"))
    for bad in (
        {"say": "x", "console": "crew", "intent": "launch", "args": {}},
        {"say": "x", "console": "ground", "intent": "diary_entry", "args": {}},
        {"say": "x", "console": "crew", "intent": "open_panel", "args": {"panel": "trends"}},
        {"say": "x", "console": "crew", "intent": "rotate", "args": {"degrees": 45}},
        # Una escritura con un valor fuera de su lista: la propuesta lo dejaría caer en silencio.
        {"say": "x", "console": "crew", "intent": "pain_report", "args": {"zone": "elbow-middle"}},
    ):
        with pytest.raises(catalog.CatalogError):
            catalog.check_examples({"examples": [*raw["examples"], bad]})


def test_the_evaluation_set_is_held_out_from_the_examples() -> None:
    """Medir no puede ser repetir: ninguna frase de la batería está entre los ejemplos del prompt,
    ni casi igual (tres cuartas partes de las mismas palabras)."""
    battery = json.loads(EVAL.read_text(encoding="utf-8"))
    assert len([case for case in battery["cases"] if case["tag"] == "eval"]) >= 100
    said = [set(catalog.plain(example.say).split()) for example in catalog.examples()]
    for case in battery["cases"]:
        words = set(catalog.plain(case["say"]).split())
        for example in said:
            overlap = len(words & example) / len(words | example)
            assert overlap < 0.75, (case["say"], example)


def test_every_eval_case_names_what_exists() -> None:
    battery = json.loads(EVAL.read_text(encoding="utf-8"))
    for case in battery["cases"]:
        console = case.get("console", "crew")
        for want in (case, *case.get("accept", [])):
            assert want["intent"] in catalog.CONTRACT_IDS, case["say"]
            args = want.get("args") or {}
            assert catalog.valid_subset(want["intent"], args, console) == args, case["say"]


@pytest.mark.parametrize(("text", "modes", "intent", "args"), [
    ("siguiente", None, "next_panel", {}),
    ("vale, anterior", None, "previous_panel", {}),
    ("calla un rato que estoy concentrado", None, "silence", {}),
    ("calla media hora", None, "silence", {"minutes": 30}),
    ("silencio veinte minutos", None, "silence", {"minutes": 20}),
    ("cállate", None, "stop_voice", {}),
    ("ya se han ido, enséñalo otra vez", {"privacy": True}, "privacy", {"on": False}),
    ("vale, ya lo he visto, quita el aviso de radiación", None, "acknowledge_alert",
     {"domain": "radiation"}),
    ("estamos sin energía, hay que recortar", None, "mission_level", {"level": "reduced"}),
    ("en realidad estamos en la estación espacial, no yendo a Marte", None, "mission_profile",
     {"profile": "leo"}),
    ("gira la vista noventa grados", None, "rotate", {"degrees": 90}),
    ("la pantalla está del revés", None, "rotate", {"degrees": 180}),
    ("léeme lo que pone en este panel de la dosis", None, "read_panel", {"panel": "dose"}),
    ("abre los informes escaneados", None, "open_panel", {"panel": "reports"}),
    ("abre los informes", None, "open_tab", {"section": "imaging"}),
    ("apunta que tengo el ánimo en un 6", None, "diary_entry",
     {"key": "mood-valence", "value": 6.0}),
    ("no hace falta que tomes la iniciativa", None, "toggle_mode",
     {"mode": "proactive", "on": False}),
    ("¿qué es la tasa de falsa alarma?", None, "open_glossary", {"term": "false-alarm-rate"}),
])
def test_everyday_phrasings_route_without_a_model(text: str, modes: dict[str, bool] | None,
                                                  intent: str, args: dict[str, Any]) -> None:
    assert turn._keyword_turn(text, "crew", modes) == (intent, args)


@pytest.mark.parametrize(("text", "modes"), [
    # Sin la privacidad puesta (o sin que la consola diga sus modos) «ya se han ido» no es nada.
    ("ya se han ido, enséñalo otra vez", {"privacy": False}),
    ("ya se han ido, enséñalo otra vez", None),
    # Una palabra suelta no dispara mandos: «otra vez», «un rato» o «estamos en» solos.
    ("llevo un rato con dolor de cabeza", None),
    ("¿cuánto falta para que estemos en la Luna?", None),
    ("¿dónde se apunta lo que como?", None),
])
def test_an_everyday_phrase_does_not_press_the_wrong_command(
    text: str, modes: dict[str, bool] | None
) -> None:
    intent, _ = turn._keyword_turn(text, "crew", modes)
    assert intent not in ("privacy", "silence", "mission_profile", "diary_entry"), intent


@pytest.mark.parametrize(("text", "medication"), [
    ("léeme lo que pone en este panel de la dosis", False),
    ("¿cuánta dosis llevo acumulada?", False),
    ("¿qué dosis de radiación he recibido?", False),
    ("no hace falta que tomes la iniciativa", False),
    ("¿qué dosis de paracetamol me tomo?", True),
    ("¿cuál es la dosis?", True),
    ("¿me tomo algo para el dolor?", True),
    ("¿la dosis de ibuprofeno de la pantalla?", True),
])
def test_a_radiation_dose_is_not_a_medication_question(text: str, medication: bool) -> None:
    assert guards.asks_for_medication(text) is medication


def test_the_dose_question_is_answered_from_the_context(seeded: TestClient) -> None:
    body = say(seeded, "¿cuánta radiación llevo acumulada?")
    built = context.build(get_settings_for(seeded), get_store(), "crew-01", "crew")
    assert body["intent"] == "none" and body["reply_source"] == "backend"
    assert built.dose_line and built.dose_line in body["reply"]
    assert "no se supone cero" in built.dose_line  # el escenario no facilita la dosis de carrera
    assert guards.numbers_ok(body["reply"], built.text())


def test_the_cabin_air_is_in_the_context_and_answered_from_it(seeded: TestClient) -> None:
    built = context.build(get_settings_for(seeded), get_store(), "crew-01", "crew")
    assert any("CO2 de cabina" in line for line in built.habitat_lines)
    assert all(line in built.text() for line in built.habitat_lines)
    body = say(seeded, "¿cómo está el aire de la nave?")
    assert body["reply_source"] == "backend" and "CO2 de cabina" in body["reply"]
    assert guards.numbers_ok(body["reply"], built.text())


def test_a_question_about_another_member_is_answered_with_that_person(
    seeded: TestClient, ollama: respx.MockRouter
) -> None:
    seen = answer(ollama, "read_status", {}, "Tu compañero va bien.")
    body = say(seeded, "¿cómo anda crew-02?")
    assert not seen, "el modelo no contesta por otra persona"
    assert body["reply_source"] == "backend" and body["reply"].startswith("crew-02: ")
    other = context.build(get_settings_for(seeded), get_store(), "crew-02", "crew")
    assert other.summary in body["reply"]


def test_an_ambiguous_companion_question_asks_who_and_the_answer_resolves_it(
    seeded: TestClient, ollama: respx.MockRouter
) -> None:
    asked = say(seeded, "¿qué tal está mi compañero?")
    assert asked["reply"] == f"{turn.COMPANION_ASK}: crew-02, crew-03 o crew-04?"
    history = [{"role": "user", "text": "¿qué tal está mi compañero?"},
               {"role": "assistant", "text": asked["reply"]}]
    body = say(seeded, "la tres", history=history)
    assert body["reply"].startswith("crew-03: ")
    # Sin haber preguntado, «la tres» no es nadie.
    assert not say(seeded, "la tres")["reply"].startswith("crew-03")


def test_nothing_is_proposed_for_another_member(seeded: TestClient,
                                                ollama: respx.MockRouter) -> None:
    answer(ollama, "pain_report", {"zone": "head", "intensity": 5}, "Lo preparo.")
    body = say(seeded, "apunta que a mi compañero le duele la cabeza, un 5")
    assert body["proposal"] is None and body["reply"] == turn.NOT_FOR_OTHERS


def test_a_model_reply_about_another_member_is_not_said(seeded: TestClient,
                                                        ollama: respx.MockRouter) -> None:
    """El caso medido el 2026-11-04: los datos de crew-01 contados como los del compañero."""
    answer(ollama, "none", {}, "Tu compañero tiene una alerta de radiación.")
    body = say(seeded, "¿hay algo nuevo hoy?")
    assert body["reply_source"] != "model" and body["checks"]["numbers"] is False
    answer(ollama, "none", {}, "crew-02 tiene una alerta de radiación.")
    assert say(seeded, "¿hay algo nuevo hoy?")["checks"]["numbers"] is False


def test_a_write_said_from_ground_is_refused_whatever_the_model_says(
    seeded: TestClient, ollama: respx.MockRouter
) -> None:
    seen = answer(ollama, "open_tab", {"section": "history"}, "Abro el historial.")
    body = say(seeded, "apunta que me duele la rodilla, un 4", console="ground")
    assert not seen and body["reply"] == GROUND_REFUSAL and body["proposal"] is None


def test_the_companion_barrier() -> None:
    crew = ["crew-01", "crew-02"]
    assert guards.companion_ok("Tienes una alerta de radiación.", "crew-01", crew)
    assert not guards.companion_ok("Tu compañero tiene una alerta.", "crew-01", crew)
    assert not guards.companion_ok("crew-02 va bien.", "crew-01", crew)
    assert guards.companion_ok("crew-01 va bien.", "crew-01", crew)


def test_a_sleep_complaint_says_the_diary_has_no_sleep_entry(seeded: TestClient,
                                                             ollama: respx.MockRouter) -> None:
    seen = answer(ollama, "read_status", {}, "Duermes bien.")
    body = say(seeded, "he dormido fatal esta noche")
    assert not seen
    assert body["intent"] == "open_panel" and body["args"] == {"panel": "diary"}
    assert body["reply"].startswith(turn.NO_SLEEP_IN_DIARY) and body["proposal"] is None
    built = context.build(get_settings_for(seeded), get_store(), "crew-01", "crew")
    sleep = [line for key, line in built.readings.items() if "sleep" in key]
    assert sleep and all(line in body["reply"] for line in sleep)
    # Si el diario tuviera un indicador de sueño, se propondría; hoy no lo tiene (no se inventa).
    from app.api.diary import diary_keys

    assert not [key for key in diary_keys() if "sleep" in key]


def test_a_question_does_not_press_a_read_command_the_model_answered(
    seeded: TestClient, ollama: respx.MockRouter
) -> None:
    rate = heart_rate(seeded)
    answer(ollama, "none", {}, f"Tu frecuencia cardiaca es {rate} por minuto.")
    body = say(seeded, "¿qué tal voy de reflejos en la prueba de reflejos?")
    assert body["intent"] == "none" and body["reply_source"] == "model"


def test_without_a_model_a_reading_is_found_by_its_everyday_name(seeded: TestClient) -> None:
    body = say(seeded, "¿cuántas pulsaciones tengo?")
    assert body["reply_source"] == "backend" and body["reply"].startswith("Frecuencia cardiaca")
    # El oxígeno de la sangre es la saturación, no el aire de la cabina.
    assert say(seeded, "¿cuál es mi saturación de oxígeno?")["reply"].startswith("Saturación")
    # Una palabra que solo empieza igual no es esa lectura («internacional» no es «intervalo»).
    assert not say(seeded, "¿qué hay en la Estación Espacial Internacional?")["reply"].startswith(
        "Variabilidad")


def test_the_modes_are_checked_against_the_inventory(seeded: TestClient) -> None:
    response = seeded.post("/api/assistant/turn", json={
        "text": "hola", "console": "crew", "subject": "crew-01", "modes": {"fly": True}})
    assert response.status_code == 422
    response = seeded.post("/api/assistant/audio", params=AUDIO, content=OGG,
                           headers={"X-EMMA-Modes": "privacy,fly"})
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Contra Ollama de verdad (fuera de la suite por defecto)
# --------------------------------------------------------------------------- #


@pytest.mark.live
def test_live_model_routes_answers_and_does_not_prescribe(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "spe-event", "days": 10})
    if not client.get("/api/assistant").json()["available"]:
        pytest.skip(f"sin {MODEL} en {LLM}")
    assert say(client, "abre radiación")["args"] == {"section": "radiation"}
    assert say(client, "¿qué pastilla me tomo?")["proposal"] is None
    body = say(client, "apunta en el diario ánimo 3")
    assert body["intent"] == "diary_entry" and body["needs_confirmation"] is True
