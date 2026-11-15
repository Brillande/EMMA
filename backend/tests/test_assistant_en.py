"""El asistente en inglés: el mismo catálogo con otras palabras, las mismas barreras y el mismo
turno (decisión del usuario, 2026-11-15).

Por qué existe: `tests/test_assistant.py` fija el castellano. Aquí se fija lo que el inglés añade
al lado y lo que NO puede cambiar con el idioma: los ids, las clases y los argumentos de las
intenciones; que no recetar sea al menos tan estricto; que lo que se firmaría lleve las palabras
de la persona tal cual y los identificadores sin traducir; y que en castellano los patrones
ingleses ni se miren. El modelo local se simula con `respx`, como en la otra suite: ninguna
prueba toca la red ni el Ollama de esta máquina.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app import memguard, voice
from app.assistant import catalog, context, controls, guards, retrieval, turn
from app.assistant.proposals import GROUND_REFUSAL, ORIGIN
from app.core import i18n
from app.core.config import get_settings
from app.interpret import llm as llm_module
from tests.conftest import ENGLISH_HEADERS

LLM = "http://127.0.0.1:11434"
MODEL = get_settings().assistant_model
EVAL = Path(__file__).resolve().parent / "data" / "assistant_nl_eval_en.json"
OGG = b"OggS" + b"\x00" * 64
_SPANISH_ONLY = re.compile(r"[áéíóúñ¿¡]", re.IGNORECASE)


@pytest.fixture(autouse=True)
def _fresh_context() -> Iterator[None]:
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
        router.post(f"{LLM}/api/show").mock(
            return_value=httpx.Response(200, json={"capabilities": ["completion"]})
        )
        yield router


@pytest.fixture
def seeded(client: TestClient, ollama: respx.MockRouter) -> TestClient:
    assert client.post("/api/simulate", params={"scenario": "spe-event", "days": 10}).status_code \
        == 201
    return client


def answer(router: respx.MockRouter, intent: str, args: dict[str, Any], reply: str,
           topic: str = "emma") -> list[Any]:
    seen: list[Any] = []

    def chat(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        content = json.dumps({"intent": intent, "args": args, "reply": reply, "topic": topic})
        return httpx.Response(200, json={"message": {"content": content}, "done_reason": "stop"})

    router.post(f"{LLM}/api/chat").mock(side_effect=chat)
    return seen


def say(client: TestClient, text: str, console: str = "crew", *, english: bool = True,
        **extra: Any) -> dict[str, Any]:
    response = client.post(
        "/api/assistant/turn",
        json={"text": text, "console": console, "subject": "crew-01", **extra},
        headers=ENGLISH_HEADERS if english else {},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# --------------------------------------------------------------------------- #
# Un catálogo por idioma, una sola estructura
# --------------------------------------------------------------------------- #


def test_the_english_catalogue_is_the_same_structure_with_other_words() -> None:
    spanish = catalog.catalog()
    with i18n.use("en"):
        english = catalog.catalog()
    assert english is not spanish
    assert list(english.intents) == list(spanish.intents)
    for intent_id, intent in spanish.intents.items():
        other = english.intents[intent_id]
        assert (other.kind, other.args, other.route, other.signer_field, other.origin_field,
                other.keywords_first) == (intent.kind, intent.args, intent.route,
                                          intent.signer_field, intent.origin_field,
                                          intent.keywords_first), intent_id
        assert other.label != intent.label or intent_id == "none", intent_id
        assert not _SPANISH_ONLY.search(other.label), other.label
    assert list(english.panels) == list(spanish.panels)
    assert {key: (panel.kind, panel.places) for key, panel in english.panels.items()} == {
        key: (panel.kind, panel.places) for key, panel in spanish.panels.items()}
    assert list(english.modes) == list(spanish.modes)
    for console in catalog.CONSOLES:
        assert english.section_keys(console) == spanish.section_keys(console)
    assert english.sections["crew"][1].label == "Radiation"
    assert spanish.sections["crew"][1].label == "Radiación"
    assert english.general_label == "knowledge of the model, no source"
    assert spanish.general_label == "conocimiento del modelo, sin fuente"
    # El catálogo castellano sigue siendo el de antes después de pedir el inglés.
    assert catalog.catalog() is spanish


def test_with_the_tabs_set_aside_everything_the_english_catalogue_shows_is_english() -> None:
    try:
        catalog.use_set_aside(True)
        with i18n.use("en"):
            shown = catalog.catalog()
            served = catalog.ui_inventory()
            examples = catalog.examples()
        for console in catalog.CONSOLES:
            for section in shown.sections[console]:
                if section.key.startswith("env-"):
                    continue  # su rótulo es el nombre del entorno, de otra unidad
                assert not _SPANISH_ONLY.search(section.label + section.about), section.key
        for panel in shown.panels.values():
            assert not _SPANISH_ONLY.search(_no_quotes(panel.label + panel.about)), panel.id
        assert [item["key"] for item in served["sections"]["crew"]] == [
            "home", "radiation", "isolation", "gravity", "environment", "nodes", "hazards"]
        assert served["sections"]["crew"][0]["label"] == "Home"
        assert {item["id"] for item in served["panels"]} == set(shown.panels)
        assert served["consoles"][0]["label"] == "Crew console"
        # Los ejemplos que el apartado deja sin destino no llegan al prompt; el resto, sí.
        assert 30 <= len(examples) <= 42
    finally:
        catalog.use_set_aside(False)
    assert catalog.set_aside_active() is False


def _no_quotes(text: str) -> str:
    return re.sub(r"«[^»]*»", "", text)


def test_the_english_words_cannot_fork_the_catalogue() -> None:
    raw = json.loads(catalog.INTENTS_PATH.read_text(encoding="utf-8"))
    english = json.loads(catalog.INTENTS_EN_PATH.read_text(encoding="utf-8"))
    merged = catalog.english_intents(raw, english)
    assert [item["id"] for item in merged["intents"]] == [item["id"] for item in raw["intents"]]
    assert merged["intents"][4]["route"] == raw["intents"][4]["route"]

    extra = copy.deepcopy(english)
    extra["intents"]["launch"] = {"label": "Launch", "keywords": ["launch"]}
    missing = copy.deepcopy(english)
    del missing["intents"]["none"]
    forked = copy.deepcopy(english)
    forked["intents"]["read_status"]["kind"] = "write"
    no_list = copy.deepcopy(english)
    del no_list["open_verbs"]
    for bad in (extra, missing, forked, no_list):
        with pytest.raises(catalog.CatalogError):
            catalog.english_intents(raw, bad)

    # Las palabras inglesas pasan las mismas comprobaciones que las castellanas.
    dirty = copy.deepcopy(english)
    dirty["intents"]["safe_mode"]["keywords"] = ["Safe Mode!"]
    wrong_zone = copy.deepcopy(english)
    wrong_zone["routing"]["zone_keywords"]["elbow-middle"] = ["middle elbow"]
    wrong_term = copy.deepcopy(english)
    wrong_term["routing"]["glossary_keywords"]["no-such-term"] = ["nothing"]
    for bad in (dirty, wrong_zone, wrong_term):
        with pytest.raises(catalog.CatalogError), i18n.use("en"):
            catalog.validate(catalog.english_intents(raw, bad))


def test_the_english_inventory_is_merged_by_id_and_validated() -> None:
    ui = json.loads(catalog.UI_PATH.read_text(encoding="utf-8"))
    english = json.loads(catalog.UI_EN_PATH.read_text(encoding="utf-8"))
    merged = catalog.english_ui(ui, english)
    by_id = {item["id"]: item for item in merged["panels"]}
    spanish = {item["id"]: item for item in ui["panels"]}
    assert by_id["alerts"]["label"] == "Active alerts"
    assert by_id["alerts"]["places"] == spanish["alerts"]["places"]
    # Una entrada sin inglés (las de las pestañas apartadas) se queda en castellano.
    assert "diary" not in english["panels"]
    assert by_id["diary"] == spanish["diary"]

    stray = copy.deepcopy(english)
    stray["panels"]["no-such-panel"] = {"label": "X", "aliases": ["x"], "about": "x"}
    with pytest.raises(catalog.CatalogError):
        catalog.english_ui(ui, stray)
    # Un alias inglés repetido entre dos paneles no carga, como en castellano.
    shared = copy.deepcopy(english)
    shared["panels"]["rad-limits"]["aliases"] = ["space weather"]
    raw = json.loads(catalog.INTENTS_PATH.read_text(encoding="utf-8"))
    with pytest.raises(catalog.CatalogError):
        catalog.validate(raw, catalog.english_ui(ui, shared))


def test_the_status_route_serves_the_inventory_in_the_language_asked(
        client: TestClient, ollama: respx.MockRouter) -> None:
    spanish = client.get("/api/assistant").json()
    english = client.get("/api/assistant", headers=ENGLISH_HEADERS).json()
    assert [item["id"] for item in english["intents"]] == [i["id"] for i in spanish["intents"]]
    assert [item["args"] for item in english["intents"]] == [i["args"] for i in spanish["intents"]]
    assert english["intents"][0]["label"] == "Stop listening for the word «EMMA»"
    assert english["ui"]["sections"]["crew"][1]["label"] == "Radiation"
    assert spanish["ui"]["sections"]["crew"][1]["label"] == "Radiación"
    assert "radiation" in english["ui"]["sections"]["crew"][1]["aliases"]
    assert [item["id"] for item in english["ui"]["panels"]] == [
        item["id"] for item in spanish["ui"]["panels"]]
    # El idioma de una petición no se queda puesto para la siguiente.
    assert client.get("/api/assistant").json()["ui"] == spanish["ui"]


# --------------------------------------------------------------------------- #
# La batería inglesa y los ejemplos
# --------------------------------------------------------------------------- #


def _routes(case: dict[str, Any]) -> bool:
    console = case.get("console", "crew")
    intent, args = turn._keyword_turn(case["say"], console, case.get("modes"))
    refused = guards.asks_for_medication(case["say"]) and intent not in ("open_tab", "open_panel")
    if case.get("refusal"):
        return refused
    return not refused and any(
        intent == want["intent"]
        and all(args.get(key) == value for key, value in (want.get("args") or {}).items())
        for want in (case, *case.get("accept", [])))


def test_every_keyword_case_of_the_english_battery_routes_without_a_model(english: None) -> None:
    battery = json.loads(EVAL.read_text(encoding="utf-8"))
    cases = [case for case in battery["cases"] if case["route"] == "keywords"]
    assert len(cases) >= 40
    wrong = [case["say"] for case in cases if not _routes(case)]
    assert wrong == []
    # Y cubre lo que tiene que cubrir: abrir, leer, modos, girar, desplazar, glosario, cifras y
    # la barrera de no recetar.
    seen = {case["intent"] for case in cases}
    assert {"open_tab", "open_panel", "read_panel", "low_vision", "privacy", "toggle_mode",
            "rotate", "scroll", "open_glossary", "pain_report", "diary_entry"} <= seen
    assert sum(1 for case in cases if case.get("refusal")) >= 4


def test_the_english_battery_names_what_exists_and_is_held_out(english: None) -> None:
    battery = json.loads(EVAL.read_text(encoding="utf-8"))
    said = [set(catalog.plain(example.say).split()) for example in catalog.examples()]
    assert len(said) >= 30
    for case in battery["cases"]:
        console = case.get("console", "crew")
        for want in (case, *case.get("accept", [])):
            assert want["intent"] in catalog.CONTRACT_IDS, case["say"]
            args = want.get("args") or {}
            assert catalog.valid_subset(want["intent"], args, console) == args, case["say"]
        words = set(catalog.plain(case["say"]).split())
        for example in said:
            assert len(words & example) / len(words | example) < 0.75, (case["say"], example)


def test_the_spanish_examples_and_the_english_ones_teach_the_same_intents() -> None:
    spanish = {example.intent for example in catalog.examples()}
    with i18n.use("en"):
        english = {example.intent for example in catalog.examples()}
        assert not any(_SPANISH_ONLY.search(example.say) for example in catalog.examples())
    assert english == spanish


# --------------------------------------------------------------------------- #
# Las trampas del inglés
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("text", "console", "intent", "args"), [
    # «environment» es la pestaña de la nave; «mission environment», las de entorno de misión.
    ("open the environment", "crew", "open_tab", {"section": "environment"}),
    ("open the mission environment", "crew", "open_tab", {"section": "env-leo"}),
    ("open the mission profile", "crew", "open_tab", {"section": "env-leo"}),
    # Girar: las palabras estaban en el inventario; ahora también las entiende el giro.
    ("screen upright", "crew", "rotate", {"degrees": 0}),
    ("normal view", "crew", "rotate", {"degrees": 0}),
    ("turn the screen sideways", "crew", "rotate", {"degrees": 90}),
    ("rotate the screen upside down", "crew", "rotate", {"degrees": 180}),
    # Pestaña y panel con el mismo nombre: la precedencia de siempre.
    ("open the alerts", "crew", "open_tab", {"section": "hazards"}),
    ("open the alerts panel", "crew", "open_panel", {"panel": "alerts"}),
    ("open the active alerts", "crew", "open_panel", {"panel": "alerts"}),
    ("open the glossary", "ground", "open_tab", {"section": "library"}),
    # El punto decimal y la coma de los miles.
    ("log my mood, 3.5", "crew", "diary_entry", {"key": "mood-valence", "value": 3.5}),
    ("note down that I drank 1,200 of water", "crew", "diary_entry",
     {"key": "fluid-intake-24h", "value": 1200.0}),
    # Una pregunta sin signo de apertura sigue siendo una pregunta: no pulsa un mando.
    ("what is the next one?", "crew", "none", {}),
    ("is privacy mode a good idea?", "crew", "none", {}),
    ("can you turn on privacy mode?", "crew", "privacy", {"on": True}),
])
def test_english_keywords_route_without_a_model(english: None, text: str, console: str,
                                                intent: str, args: dict[str, Any]) -> None:
    assert turn._keyword_turn(text, console) == (intent, args)


@pytest.mark.parametrize("text", [
    "how is my blood pressure?",      # «press» no es «pressure»
    "I am reading a book",            # «read» no es «reading»
    "the shower is broken",           # «show» no es «shower»
    "it happened once",               # «once» no es el 11
    "I already took a shower today",
])
def test_an_english_word_that_only_starts_like_a_command_does_nothing(english: None,
                                                                      text: str) -> None:
    intent, _ = turn._keyword_turn(text, "crew")
    assert intent in ("none", "read_status")
    assert controls.pick(text, [controls.Control("Pressure", False),
                                controls.Control("Reading", False)]) is None


def test_the_spanish_matching_is_the_one_it_was() -> None:
    # Por comienzo, como siempre: «atrasad» casa con «atrasadas».
    assert catalog._has(" medidas atrasadas ", "atrasad")
    assert catalog.keyword_intent("abre radiación", "crew") == ("open_tab",
                                                                {"section": "radiation"})
    # Y el inglés no se entiende en castellano: ni sus palabras ni sus giros.
    assert catalog.keyword_intent("rotate the screen upside down", "crew") == ("none", {})
    assert catalog.spoken_numbers("un 1,200") == [1.2]
    with i18n.use("en"):
        assert not catalog._has(" overdue measurements ", "over")
        assert catalog._has(" two alerts today ", "alert")


# --------------------------------------------------------------------------- #
# Las barreras
# --------------------------------------------------------------------------- #

BLOCKED = [
    "Take two tablets and rest.",
    "You should take something for it.",
    "You could take one after lunch.",
    "An ibuprofen would help.",
    "Try a painkiller.",
    "The usual dose is one every eight hours.",
    "That is 400 mg twice a day.",
    "I can prescribe something.",
    "Ask for your medication.",
    "A sleeping pill might help you.",
    "There are anti-inflammatory creams in the kit.",
    "Use the nasal spray.",
    "Tómese un ibuprofeno.",          # el castellano sigue cayendo con la consola en inglés
    "Debes tomar una pastilla.",
]
ALLOWED = [
    "Your heart rate is within your usual range.",
    "You can take your temperature with the guide open.",
    "Shall I take you to the radiation tab?",
    "It takes about 8 minutes.",
    "The trip can take several months.",
    "This may take a few minutes.",
    "Your career radiation dose is in the dosimetry panel.",
    "The dose rate went up during the solar event.",
    "That is for the onboard physician to assess.",
    "Take a look at the alerts panel if you want.",
]


@pytest.mark.parametrize("reply", BLOCKED)
def test_the_english_barrier_does_not_let_a_prescription_through(english: None,
                                                                 reply: str) -> None:
    assert guards.no_prescription(reply) is False


@pytest.mark.parametrize("reply", ALLOWED)
def test_the_english_barrier_lets_ordinary_sentences_through(english: None, reply: str) -> None:
    assert guards.no_prescription(reply) is True


def test_the_english_barrier_is_at_least_as_strict_as_the_spanish_one() -> None:
    """Cada patrón castellano de no recetar tiene su par inglés: la misma idea dicha en inglés
    cae en inglés. Y en castellano los patrones ingleses ni se miran."""
    pairs = [
        ("tome un comprimido", "take a tablet"),
        ("debes tomar algo", "you must take something"),
        ("una pastilla", "a pill"), ("un jarabe", "a syrup"), ("una pomada", "an ointment"),
        ("un analgésico", "an analgesic"), ("un antibiótico", "an antibiotic"),
        ("paracetamol", "acetaminophen"), ("melatonina", "melatonin"),
        ("la dosis", "the dosage"), ("200 mg", "200 mg"), ("miligramos", "milligrams"),
        ("te receto", "i prescribe"), ("un medicamento", "a medication"),
        ("un fármaco", "a drug"),
    ]
    for spanish, english in pairs:
        assert guards.no_prescription(spanish) is False, spanish
        with i18n.use("en"):
            assert guards.no_prescription(english) is False, english
            assert guards.no_prescription(spanish) is False, spanish
    assert guards.no_prescription("take a pill and a drug") is True  # no es castellano


def test_asking_for_medication_in_english(english: None) -> None:
    for text in ("what can I take for my headache?", "should I take an ibuprofen?",
                 "is there a pill for this?", "give me something for the pain",
                 "what dose do I need?", "can I take something to sleep?",
                 "do we have any painkillers?"):
        assert guards.asks_for_medication(text), text
    for text in ("how long does it take to reach Mars?", "what is my radiation dose?",
                 "how much career dose do I have so far?", "read me the dose limits panel",
                 "take me to the radiation tab", "can I take it off now?",
                 "show it on the tablet", "how is my blood pressure?"):
        assert not guards.asks_for_medication(text), text


def test_asking_for_medication_in_spanish_ignores_the_english_patterns() -> None:
    assert not guards.asks_for_medication("what can I take for my headache")
    assert guards.asks_for_medication("¿qué me tomo para el dolor de cabeza?")


@pytest.mark.parametrize(("text", "figures", "unreadable"), [
    ("seventy-four beats", [74.0], False),
    ("seventy four", [74.0], False),
    ("nineteen", [19.0], False),
    ("a hundred", [100.0], False),
    ("one hundred percent", [100.0], False),
    ("one hundred and twenty", [20.0], True),
    ("two hundred", [], True),
    ("three thousand", [3.0], True),
    ("the one on the left", [], False),      # «one» solo es pronombre, como «uno»
    ("a reading", [], False),
    ("once a day", [], False),               # «once» no es el 11 castellano
    ("400 miles away", [], False),           # ni «miles» es «miles de»
    ("setenta y cuatro", [74.0], False),     # una cifra en castellano sigue leyéndose
])
def test_spelled_numbers_in_english(english: None, text: str, figures: list[float],
                                    unreadable: bool) -> None:
    assert guards.spelled_numbers(text) == (figures, unreadable)


def test_the_figures_barrier_in_english(english: None) -> None:
    known = "Heart rate: 74 /min"
    assert guards.numbers_ok("Your heart rate is seventy-four.", known)
    assert not guards.numbers_ok("Your heart rate is ninety.", known)
    assert not guards.numbers_ok("About two thousand.", known)
    assert guards.spelled_numbers("once") == ([], False)


def test_spelled_numbers_in_spanish_are_the_ones_they_were() -> None:
    assert guards.spelled_numbers("setenta y cuatro") == ([74.0], False)
    assert guards.spelled_numbers("once") == ([11.0], False)
    assert guards.spelled_numbers("seventy four") == ([], False)


def test_the_general_and_companion_barriers_in_english(english: None) -> None:
    crew = ["crew-01", "crew-02"]
    assert not guards.about_crew_or_health("how long does light take from the Sun?", crew)
    for text in ("is my heart ok?", "why does my head hurt?", "how is crew-02?",
                 "what is a normal pulse?", "what dose is safe?", "am I sick?"):
        assert guards.about_crew_or_health(text, crew), text
    assert guards.general_ok("Light takes about 8 minutes from the Sun to Earth.", crew)
    for reply in ("A normal pulse is 60 beats.", "The body adapts.", "About 37 degrees.",
                  "It is 50 percent.", "crew-02 knows."):
        assert not guards.general_ok(reply, crew), reply
    assert guards.names_companion("how is my crewmate doing?", "crew-01", crew)
    assert guards.asks_about_group("how is the rest of the crew?")
    assert not guards.companion_ok("Your crewmate is fine.", "crew-01", crew)
    assert guards.companion_ok("Your reading is fine.", "crew-01", crew)


# --------------------------------------------------------------------------- #
# Botones, mapa y prompt
# --------------------------------------------------------------------------- #


def test_buttons_in_english_ask_for_confirm_and_keep_the_label_as_sent(english: None) -> None:
    shown = [controls.Control("Abdomen liver 1", False), controls.Control("Save Report", True),
             controls.Control("Guardar informe", True)]
    found = controls.pick("press abdomen liver one", shown)
    assert found is not None and found.control == shown[0]
    assert controls.reply(found) == ("Pressing «Abdomen liver 1».", False)
    saving = controls.pick("click save report", shown)
    assert saving is not None and saving.control == shown[1]
    said, confirm = controls.reply(saving)
    assert confirm and "«confirm»" in said and "«cancel»" in said and "confirmo" not in said
    # Un rótulo que la consola manda en castellano se devuelve tal cual, sin traducir.
    spanish_label = controls.pick("press guardar informe", shown)
    assert spanish_label is not None
    assert turn._pressed(spanish_label).args == {"control": "Guardar informe"}
    assert controls.pick("how is my blood pressure", [controls.Control("Blood", False)]) is None


def test_buttons_in_spanish_say_what_they_said() -> None:
    saving = controls.pick("pulsa guardar", [controls.Control("Guardar", True)])
    assert saving is not None
    assert "«confirmo»" in controls.reply(saving)[0]
    assert controls.pick("press save", [controls.Control("Save", False)]) is None


def test_the_english_map_compares_singulars_and_uses_english_stopwords(english: None) -> None:
    assert retrieval.stems("the doses and the bones") == {"dose", "bone"}
    assert retrieval.stems("status of the batteries") == {"batte"}
    assert retrieval.stems("show me what is in it") == set()
    found = [item.key for item in retrieval.candidates("is it too loud in the cabin", "crew")]
    assert "env-noise" in found
    assert retrieval.map_text("zzzz", "crew") == "(no panel resembles the request)"
    best = retrieval.best_place("take me to the shielding", "crew")
    assert best is not None and best.key == "rad-shielding"


def test_the_spanish_map_is_the_one_it_was() -> None:
    assert retrieval.stems("los huesos y las dosis") == {"hueso", "dosis"}
    assert retrieval.map_text("zzzz", "crew") == "(ningún panel se parece a la petición)"


def _rules(prompt: str) -> list[str]:
    return [line for line in prompt.splitlines() if line.startswith("- ")]


def test_the_english_system_prompt_carries_every_rule_of_the_spanish_one() -> None:
    spanish, english = _rules(turn.SYSTEM_PROMPT), _rules(turn.SYSTEM_PROMPT_EN)
    # Las mismas reglas, en el mismo orden, y una más: contestar en inglés.
    assert len(english) == len(spanish) + 1
    assert english[-1].startswith("- Always answer in English")
    assert "Hablas en español" in turn.SYSTEM_PROMPT and "You speak English" in \
        turn.SYSTEM_PROMPT_EN
    for needle in ("use only the CONTEXT", "say you do not have it", "Do not invent",
                   "has to be in the CONTEXT or in the REQUEST", "Do not diagnose",
                   "Do not name drugs, pills, doses or treatments", "do not say what to take",
                   "Do not give orders or recommend", "only PROPOSE",
                   "do not say that something is logged or signed", "NEVER \"general\"",
                   "never talk about another person", "you do not decide"):
        assert needle in turn.SYSTEM_PROMPT_EN, needle
    # Los ids no se traducen: las seis de escritura se nombran igual en los dos.
    for intent_id in catalog.WRITE_IDS:
        assert intent_id in turn.SYSTEM_PROMPT and intent_id in turn.SYSTEM_PROMPT_EN
    assert not _SPANISH_ONLY.search(turn.SYSTEM_PROMPT_EN)


def test_the_prompt_sent_to_the_model_follows_the_language() -> None:
    spanish = turn.system_prompt("crew")
    assert spanish.startswith(turn.SYSTEM_PROMPT) and "PESTAÑAS de esta consola" in spanish
    built = context.AssistantContext(subject="crew-01", console="crew")
    with i18n.use("en"):
        english = turn.system_prompt("crew")
        short = turn.system_prompt("crew", turn.vocabularies("open radiation"))
        system, user = (item["content"] for item in
                        turn.model_messages("open radiation", "crew", built, []))
    assert english.startswith(turn.SYSTEM_PROMPT_EN) and "TABS of this console" in english
    assert "- open_tab: Open a tab (args {\"section\"}, the key of one of the TABS)" in english
    assert "«open radiation»" not in english and "«take me to the cabin noise thing»" in english
    assert system == short and short.startswith(turn.SYSTEM_PROMPT_EN)
    assert user.startswith(turn.DATA_GUARD_EN)
    for block in ("MAP (", "CONTEXT:", "HISTORY:", "REQUEST:"):
        assert block in user
    assert "PETICION" not in user and "(no previous conversation)" in user
    # El prompt castellano no cambió por haber pedido el inglés.
    assert turn.system_prompt("crew") == spanish


# --------------------------------------------------------------------------- #
# El turno entero
# --------------------------------------------------------------------------- #


def test_without_a_model_an_english_turn_answers_in_english(seeded: TestClient) -> None:
    opened = say(seeded, "open radiation")
    assert (opened["intent"], opened["args"]) == ("open_tab", {"section": "radiation"})
    assert opened["reply"] == "Opening Radiation." and opened["reply_source"] == "fixed"
    assert say(seeded, "abre radiación", english=False)["reply"] == "Abro Radiación."
    assert say(seeded, "low vision on")["reply"] == "Turning low vision on."
    assert say(seeded, "rotate the screen upside down")["reply"] == \
        "Rotating the view to 180 degrees."
    assert say(seeded, "be quiet")["reply"] == "I will be quiet."
    assert say(seeded, "scroll down")["reply"] == "Scrolling down."
    assert say(seeded, "switch to the ground console")["reply"] == \
        "Switching to the ground console."
    assert say(seeded, "zzzz qqqq")["reply"] == i18n._registry[turn.NOT_UNDERSTOOD]
    # El contexto se compone en el idioma de cada petición, también el que está en caché.
    english = say(seeded, "how much radiation dose do I have?")
    spanish = say(seeded, "¿cuánta dosis de radiación llevo?", english=False)
    assert english["reply"].startswith("Cumulative career radiation dose:")
    assert spanish["reply"].startswith("Dosis de carrera acumulada:")
    again = say(seeded, "how much radiation dose do I have?")
    assert again["reply"] == english["reply"]


def test_a_medication_question_in_english_gets_the_fixed_refusal(
        seeded: TestClient, ollama: respx.MockRouter) -> None:
    seen = answer(ollama, "none", {}, "Take an ibuprofen.")
    for text in ("what can I take for my headache?", "should I take a painkiller?"):
        body = say(seeded, text)
        assert body["intent"] == "none" and body["proposal"] is None
        assert body["reply"] == i18n._registry[turn.NO_PRESCRIPTION]
    assert seen == []  # ni se pregunta al modelo
    refusal = i18n._registry[turn.NO_PRESCRIPTION]
    with i18n.use("en"):
        assert guards.no_prescription(refusal) and guards.language_ok(refusal)
        # Todas las frases fijas inglesas pasan sus propias barreras, como las castellanas.
        for fixed in (turn.NOT_UNDERSTOOD, turn.NO_DATA, turn.NO_COMPANIONS, turn.NOT_FOR_OTHERS,
                      turn.NO_SLEEP_IN_DIARY, turn.DIARY_INSTEAD, GROUND_REFUSAL,
                      *turn._FIXED.values(), *turn._SCROLLED.values()):
            said = i18n.loc(fixed)
            assert said != fixed and guards.no_prescription(said), said
    # Abrir sí: el panel del botiquín se abre por su nombre.
    assert say(seeded, "open medication management")["intent"] == "open_panel"


def test_an_english_model_answer_goes_through_the_barriers(seeded: TestClient,
                                                           ollama: respx.MockRouter) -> None:
    answer(ollama, "none", {}, "Your readings look steady today.")
    clean = say(seeded, "tell me something about today")
    assert clean["reply"] == "Your readings look steady today."
    assert clean["reply_source"] == "model"
    assert clean["label"] == "answer from the local model, not validated"
    assert all(clean["checks"].values())

    answer(ollama, "none", {}, "You should take two tablets after lunch.")
    recipe = say(seeded, "tell me something about today")
    assert recipe["checks"]["no_prescription"] is False
    assert "tablets" not in recipe["reply"] and recipe["reply_source"] != "model"

    answer(ollama, "none", {}, "Your heart rate is two hundred and fifty.")
    invented = say(seeded, "tell me something about today")
    assert invented["checks"]["numbers"] is False and "fifty" not in invented["reply"]

    answer(ollama, "none", {}, "Light takes about 8 minutes.", topic="general")
    general = say(seeded, "how long does light take from the Sun?")
    assert general["reply_source"] == "general"
    assert general["label"] == "knowledge of the model, no source"
    answer(ollama, "none", {}, "A healthy pulse is about 60 beats.", topic="general")
    assert say(seeded, "how long does light take from the Sun?")["reply_source"] != "general"


def test_what_would_be_signed_keeps_the_words_and_the_identifiers(
        seeded: TestClient) -> None:
    text = "my left knee hurts, a 7"
    body = say(seeded, text, operator="CMO")
    assert body["intent"] == "pain_report" and body["needs_confirmation"] is True
    proposal = body["proposal"]
    assert proposal["zones"] == [{"zone": "knee-left", "intensity": 7, "characters": []}]
    assert proposal["note"] == text              # las palabras de la persona, tal cual
    assert proposal["note_origin"] == ORIGIN == "asistente-confirmada"   # un id, sin traducir
    assert "say «confirm»" in body["reply"] and "CMO will sign" in body["reply"]
    assert "confirmo" not in body["reply"]
    # La ruta de siempre acepta ese cuerpo, firmado por la interfaz.
    signed = seeded.post("/api/pain/reports", json={**proposal, "reported_by": "CMO"})
    assert signed.status_code == 201, signed.text

    # Una zona que la persona no dijo no se propone: se pregunta, en inglés.
    asked = say(seeded, "it hurts a lot")
    assert asked["proposal"] is None
    assert asked["reply"] == "Where does it hurt and how much, from 1 to 10?"
    diary = say(seeded, "log my mood, 4", operator="CMO")
    assert diary["proposal"] == {"key": "mood-valence", "value": 4.0, "subject": "crew-01"}
    assert diary["reply"].startswith("Proposal for the diary:")
    refused = say(seeded, "log my mood, 4", console="ground")
    assert refused["reply"] == i18n._registry[GROUND_REFUSAL] and refused["proposal"] is None


def test_a_sleep_complaint_and_a_button_in_english(seeded: TestClient) -> None:
    slept = say(seeded, "I slept terribly last night")
    assert slept["reply"].startswith("The diary has no sleep entry")
    assert (slept["intent"], slept["args"]) == ("open_panel", {"panel": "diary"})
    shown = [{"label": "Abdomen liver 1", "writes": False}, {"label": "Save", "writes": True}]
    pressed = say(seeded, "press abdomen liver one", controls=shown)
    assert (pressed["intent"], pressed["args"]) == ("press", {"control": "Abdomen liver 1"})
    saving = say(seeded, "press save", controls=shown)
    assert saving["needs_confirmation"] is True and "«confirm»" in saving["reply"]


# --------------------------------------------------------------------------- #
# Oír
# --------------------------------------------------------------------------- #


def test_the_model_is_asked_to_transcribe_in_the_language_of_the_request(
        ollama: respx.MockRouter) -> None:
    seen: list[Any] = []

    def chat(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": json.dumps({"text": "hello"})}})

    ollama.post(f"{LLM}/api/chat").mock(side_effect=chat)
    client = llm_module.LocalLlm(LLM, MODEL)
    client.transcribe(b"RIFF")
    with i18n.use("en"):
        client.transcribe(b"RIFF")
    spanish, english = (item["messages"] for item in seen)
    assert spanish[0]["content"] == llm_module.HEARING_PROMPT
    assert spanish[1]["content"] == "Transcribe este audio."
    assert english[0]["content"] == llm_module.HEARING_PROMPT_EN
    assert "in English" in llm_module.HEARING_PROMPT_EN and "«EMMA»" in \
        llm_module.HEARING_PROMPT_EN
    assert english[1]["content"] == "Transcribe this audio."


def test_whisper_runs_the_polaris_script_in_the_language_of_the_request(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []

    def run(command: list[str], ceiling_gb: float, env: dict[str, str], **kwargs: Any) -> Any:
        calls.append((command, env))
        out = Path(env["BTP_AUDIO_OUT"])
        out.mkdir(parents=True)
        (out / "dictado.md").write_text("**[x]** `dictado.opus`\nhello\n\n", encoding="utf-8")
        return memguard.Outcome(0, 1.4)

    monkeypatch.setattr(voice, "ready", lambda: True)
    monkeypatch.setattr(voice.memguard, "run", run)
    monkeypatch.delenv(voice.LANGUAGE_ENV, raising=False)
    assert voice.transcribe(OGG) == "hello"
    with i18n.use("en"):
        assert voice.transcribe(OGG) == "hello"
    (spanish, spanish_env), (english, english_env) = calls
    # En castellano, su script tal cual, sin nada en medio y sin la variable.
    assert len(spanish) == 3 and spanish[1].endswith("transcribe_audios.py")
    assert spanish[2] == voice.MODEL and voice.LANGUAGE_ENV not in spanish_env
    # En inglés, el mismo fichero de la copia desde el lanzador, con el idioma en el entorno.
    assert english[1:3] == ["-c", voice._IN_LANGUAGE]
    assert english[3] == spanish[1] and english[4] == voice.MODEL
    assert english_env[voice.LANGUAGE_ENV] == "en"
    compile(voice._IN_LANGUAGE, "<lanzador>", "exec")
    # El script de la copia sigue llevando su idioma escrito: por eso hace falta el lanzador.
    assert f'language="{voice.SCRIPT_LANGUAGE}"' in Path(spanish[1]).read_text(encoding="utf-8")
