"""El inglés del núcleo (`app/core/`): misión, niveles, historial, entorno, enlace, turno,
recursos, inventario, ayuda urgente, notas de Tierra y la frase de la versión de las reglas.

Por qué existe: el castellano de estos módulos lo fijan sus propias pruebas; el inglés se puso al
lado (`i18n.tr`, `i18n.en` + `i18n.loc`, y los hermanos `mission_modes.en.json` y
`resources.en.json`) y nada lo vigilaba. Aquí se comprueba que cada frase que se sirve tiene su
inglés, que las cifras llevan punto decimal, que sin pedir inglés la respuesta es la de antes, que
los identificadores son los mismos en los dos idiomas y que lo firmado no cambia con el idioma de
quien lo firma. Y que el inglés no dice más que el castellano: ni «certified», ni «validated», ni
palabras de diagnóstico o de orden médica.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.core import (
    ground_notes,
    help_requests,
    i18n,
    inventory,
    link_sync,
    mission,
    mission_history,
    mission_modes,
    mission_profile_changes,
    resources,
    shift,
    storage,
    versioning,
)
from app.core.identities import CONSOLE_IDENTITY
from app.core.ledger import SALT_FIELD
from tests.conftest import ENGLISH_HEADERS

_SPANISH_ONLY = re.compile(r"[áéíóúñ¿¡]", re.IGNORECASE)
_FORBIDDEN = re.compile(r"certified|validated|diagnos|administer|must take", re.IGNORECASE)
# Lo que va entre comillas angulares es una cita o un nombre: se queda como en su fuente (las
# formas de mandato que busca el filtro, el nombre que una persona dio a una misión).
_QUOTED = re.compile(r"«[^»]*»")

START = dt.date(2026, 1, 1)
NOON = dt.time(12, 0, tzinfo=dt.UTC)


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for inner in value.values():
            yield from _strings(inner)
    elif isinstance(value, (list, tuple)):
        for inner in value:
            yield from _strings(inner)


def _assert_plain_english(value: Any) -> None:
    """Ni una palabra prohibida ni una tilde castellana fuera de una cita."""
    texts = list(_strings(value))
    assert texts
    for text in texts:
        assert not _FORBIDDEN.search(text), text
        assert not _SPANISH_ONLY.search(_QUOTED.sub("", text)), text


def _spanish(fn: Any, *args: Any, **kwargs: Any) -> Any:
    with i18n.use("es"):
        return fn(*args, **kwargs)


# --- Los dos hermanos ingleses -----------------------------------------------------------------


def _raw(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    loaded.pop("_nota", None)
    return loaded


def _mode_identifiers(raw: dict[str, Any]) -> set[str]:
    """Las claves de `mission_modes.json`, que no se traducen; y «nominal», igual en los dos."""
    found = {"nominal", *raw["citable_systems"]}
    for level in raw["levels"]:
        found |= {level["key"], *level["modes"], *level["consumables"]}
        found |= {entry["key"] for entry in level["also_expected"]}
    return found


@pytest.mark.parametrize("path", [mission_modes.MODES_PATH, resources.VOCABULARY_PATH])
def test_each_overlay_covers_its_spanish_file_and_nothing_else(path: Path) -> None:
    raw = _raw(path)
    identifiers = (
        _mode_identifiers(raw) if path == mission_modes.MODES_PATH
        else {item["key"] for item in raw["resources"]}
    )
    assert i18n.missing(path, raw, skip=lambda text: text in identifiers) == []
    english = i18n.overlay(path)
    spanish = set(_strings(raw))
    assert set(english) <= spanish, sorted(set(english) - spanish)
    assert not set(english) & identifiers
    _assert_plain_english(list(english.values()))
    assert all(text.strip() == text and text for text in english.values())


def test_the_spanish_data_files_are_not_touched_by_the_overlay(english: None) -> None:
    assert mission_modes.vocabulary().levels["reduced"].display == "reducido"
    assert resources.vocabulary()["ultrasound-scanner"].name == "ecógrafo"
    assert mission_modes.shown("reducido") == "reduced"
    assert resources.name_of("ultrasound-scanner") == "ultrasound scanner"
    assert resources.name_of("fuera-del-vocabulario") == "fuera-del-vocabulario"


# --- Constantes con su inglés registrado -------------------------------------------------------

REGISTERED: tuple[str, ...] = (
    *(item.display for item in mission.MissionPhase),
    mission.EARTH_GRAVITY, mission.MISSION_GRAVITY_LABEL,
    *mission_modes.UNCHANGED, mission_modes.RULE, mission_modes.NOT_POWER,
    mission_history.SCOPE, mission_history.DAYS_BASIS, mission_history.CHRONICLE_SOURCE,
    mission_profile_changes.RULE, mission_profile_changes.DESCRIPTIVE,
    link_sync.LABEL, link_sync.NOT_MEASURED, link_sync.RULE,
    link_sync.NOT_READ_BY, link_sync.KNOWN_ONLY_HERE, link_sync.INSTANT_BASIS,
    shift.DISPLAY, shift.DISTINCTION, shift.SOURCE_SAYS, shift.RELEVANCE,
    resources.DECLARED_LABEL, resources.DECLARED_NOTE, resources.UNDECLARED_NOTE,
    resources.VOCABULARY_BASIS, resources.RULE, resources.SCOPE,
    *(item.label for item in inventory.CATEGORIES), inventory.LABEL, inventory.NOTE,
    inventory.RULE, inventory.AUTONOMY_RULE, inventory.ALTERNATIVES_RULE, inventory.SCOPE,
    *help_requests.PROXIMITY_DISPLAY.values(), help_requests.HEADLINE, help_requests.BASIS,
    help_requests.NO_CREWMATES, help_requests.NO_LOCATION,
    *ground_notes.GROUND_NOTE_KINDS.values(), ground_notes.BASIS, ground_notes.REFUSED,
    versioning.NO_VERSION_RECORDED, versioning.SAME_AS_TODAY,
    *storage.DISMISSAL_REASONS.values(),
)


def test_every_displayed_constant_has_its_english_and_keeps_its_spanish() -> None:
    assert len(set(REGISTERED)) > 60
    for text in REGISTERED:
        assert i18n.loc(text) == text
        with i18n.use("en"):
            shown = i18n.loc(text)
        assert shown != text, text
        _assert_plain_english(shown)


def test_help_request_and_ground_note_words_shown_at_read_time(english: None) -> None:
    proximity = {key: i18n.loc(text) for key, text in help_requests.PROXIMITY_DISPLAY.items()}
    assert proximity == {
        "same_module": "in the same module", "other_module": "in another module",
        "unknown": "location unknown",
    }
    assert i18n.loc(help_requests.HEADLINE) == "Urgent help"
    assert "not an alert from the analysis nor a medical assessment" in i18n.loc(
        help_requests.BASIS
    )
    kinds = {key: i18n.loc(text) for key, text in ground_notes.GROUND_NOTE_KINDS.items()}
    assert kinds == {"information": "information", "question": "question"}
    assert "it is not a medical order" in i18n.loc(ground_notes.BASIS)
    # Las formas de mandato se citan como las busca el filtro, que lee castellano.
    assert "«tiene que»" in i18n.loc(ground_notes.REFUSED)
    assert i18n.loc(storage.DISMISSAL_REASONS["sensor_artifact"]) == "sensor artifact"


# --- Contexto de misión ------------------------------------------------------------------------


def _context(day: int, regime: str = "microgravedad") -> dict[str, Any]:
    moment = dt.datetime.combine(START + dt.timedelta(days=day), NOON)
    return mission.context(moment, START, 180, regime)


def test_the_mission_context_in_english(english: None) -> None:
    told = _context(3)
    assert told["phase"] == "adaptation"
    assert told["phase_display"] == "adaptation"
    assert [item["display"] for item in told["phases"]] == [
        "preflight", "adaptation", "stable phase", "return preparation", "postflight and recovery",
    ]
    assert told["gravity_display"] == told["gravity_now"] == "microgravity"
    assert told["gravity_mission_label"] == "mission gravity, declared by configuration"
    assert told["phase_basis"] == (
        "EMMA design: adaptation for the first 14 days and return for the last 7; the phase is "
        "shown and does not change the analysis"
    )
    after = _context(200)
    assert after["gravity_now"] == "on Earth (Earth gravity)"
    assert after["gravity_display"] == (
        "on Earth (Earth gravity); mission gravity, declared by configuration: microgravity"
    )
    _assert_plain_english([told, after])
    # Una gravedad escrita a mano en la configuración no tiene inglés: se enseña como se escribió,
    # aunque coincida con una constante que otro módulo registró con su inglés.
    assert _context(3, "gravedad lunar (1/6)")["gravity_display"] == "gravedad lunar (1/6)"
    assert _context(3, "fase estable")["gravity_mission"] == "fase estable"


def test_the_mission_context_keeps_its_identifiers_and_its_spanish(english: None) -> None:
    shown, spanish = _context(200), _spanish(_context, 200)
    for key in ("mission_day", "duration_days", "phase", "gravity_regime"):
        assert shown[key] == spanish[key]
    assert [item["key"] for item in shown["phases"]] == [item["key"] for item in spanish["phases"]]
    assert shown["gravity_regime"] == "microgravedad"
    assert spanish["phase_display"] == "posvuelo y recuperación"
    assert spanish["gravity_display"] == (
        "en Tierra (gravedad terrestre); gravedad de la misión, declarada por configuración: "
        "microgravedad"
    )
    # La propiedad y la función que usan otros módulos siguen dando el castellano.
    assert mission.MissionPhase.STABLE.display == "fase estable"
    assert mission.gravity_now(mission.MissionPhase.POSTFLIGHT, "x") == mission.EARTH_GRAVITY


# --- Niveles de misión -------------------------------------------------------------------------

_MODE_OWNED = ("label", "basis", "rule", "not_power", "unchanged", "citable_basis", "notice")


def test_the_mission_level_over_the_api(client: TestClient) -> None:
    quiet = client.get("/api/mission-mode", headers=ENGLISH_HEADERS).json()
    assert quiet["notice"] is None
    assert quiet["label"] == "EMMA design vocabulary"
    assert [item["display"] for item in quiet["levels"]] == ["nominal", "reduced", "minimal"]
    assert quiet["current"]["description"] == "All the measurements in the catalogue are expected."

    body = {"level": "reduced", "reason": "poca energía", "declared_by": "Ana"}
    changed = client.post("/api/mission-mode", json=body, headers=ENGLISH_HEADERS)
    assert changed.status_code == 201, changed.text
    english = client.get("/api/mission-mode", headers=ENGLISH_HEADERS).json()
    spanish = client.get("/api/mission-mode").json()

    assert english["level"] == spanish["level"] == "reduced"
    assert english["level_display"] == "reduced" and spanish["level_display"] == "reducido"
    notice = english["notice"]
    assert notice["title"] == "Mission level reduced"
    assert re.fullmatch(r"\d+ of \d+ measurements not expected", notice["headline"])
    assert notice["summary"] == "Ingestion, analysis, risk, alerts and safe mode carry on."
    assert notice["since_label"] == "since (time of the signed entry)"
    assert len(notice["details"]) == len(spanish["notice"]["details"]) == 9
    assert spanish["notice"]["title"] == "Nivel de misión reducido"
    assert spanish["notice"]["details_label"] == "Qué cambia y qué no"
    assert "medidas sin esperar" in spanish["notice"]["headline"]
    _assert_plain_english([english[key] for key in _MODE_OWNED])
    _assert_plain_english([[item["display"], item["description"]] for item in english["levels"]])
    # El motivo lo escribió una persona: se enseña tal cual en los dos idiomas.
    assert english["reason"] == spanish["reason"] == "poca energía"
    # Lo mismo esperado y suspendido, con las mismas claves; cambia solo la frase del porqué.
    for side in ("expected", "suspended"):
        assert [m["key"] for m in english["current"][side]] == [
            m["key"] for m in spanish["current"][side]
        ]
    whys = {item["why"].split(":")[0] for item in english["current"]["suspended"]}
    assert whys <= {
        "measurement class", "consumables", "calculated from measurements that are not expected",
    }
    assert whys


def test_the_minimal_level_says_why_in_english(english: None) -> None:
    view = mission_modes.level_view("minimal")
    added = {item["key"]: item["why"] for item in view["expected"]}
    assert added["pain-intensity"].startswith("added by hand: Pain can only be declared by")
    assert view["display"] == "minimal"
    entry = {"level": "minimal", "reason": "tormenta solar"}
    assert mission_modes.chronicle_sentence("nominal", entry) == (
        "mission level: from nominal to minimal; reason: tormenta solar"
    )
    assert _spanish(mission_modes.chronicle_sentence, "nominal", entry) == (
        "nivel de misión: de nominal a mínimo; motivo: tormenta solar"
    )


# --- Historial misión a misión -----------------------------------------------------------------


def _history(*missions: mission_history.PriorMission) -> dict[str, Any]:
    return {
        "missions": list(missions), "declared_by": "Ana", "recorded": "2026-01-01T00:00:00+00:00",
        "ledger_index": 4,
    }


def test_the_mission_history_in_english(english: None) -> None:
    profile = {"prior_missions": 2, "prior_career_dose_msv": 80.0}
    none = mission_history.describe(None, profile, current_start=None)
    assert none["text"] == "No mission-by-mission history declared."
    assert none["scope"].startswith("Declared by a person; EMMA does not check it")

    one = mission_history.PriorMission("Exp. 70", dt.date(2024, 1, 1), dt.date(2024, 6, 29), 62.5)
    two = mission_history.PriorMission("Exp. 74", dt.date(2025, 1, 1), dt.date(2025, 1, 2))
    told = mission_history.describe(_history(one), profile, current_start=START)
    assert told["text"] == "Declared: 1 prior mission."
    missions, dose = told["checks"]
    assert missions["text"] == (
        "The history declares 1 mission and the profile, 2 missions. Neither is corrected: "
        "whoever declared them can review it."
    )
    # La cifra, con punto decimal: la da `core/display.py`.
    assert dose["text"].startswith(
        "The sum of the doses in the history (62.50 mSv) does not match the prior career dose of "
        "the profile (80.00 mSv)."
    )
    assert (missions["matches"], dose["matches"]) == (False, False)

    both = mission_history.describe(_history(one, two), profile, current_start=dt.date(2025, 1, 1))
    assert both["text"] == "Declared: 2 prior missions."
    texts = {item["key"]: item["text"] for item in both["checks"]}
    assert texts["missions"] == "The history declares 2 missions, the same number as the profile."
    assert texts["dose"].startswith("1 mission in the history with no declared dose")
    assert texts["overlap"].startswith(
        "Mission «Exp. 74» (ends on 2025-01-02) ends after the start of the current mission "
        "(2025-01-01): it overlaps with it."
    )
    assert mission_history.chronicle_sentence(one) == (
        "prior mission «Exp. 70», from 2024-01-01 to 2024-06-29 (180 days between dates); "
        "declared radiation exposure 62.50 mSv"
    )
    assert mission_history.chronicle_sentence(two).endswith(
        "(1 day between dates); no declared radiation exposure (this is not zero)"
    )
    _assert_plain_english([none, told["checks"], both["checks"], both["days_basis"]])

    spanish = _spanish(mission_history.describe, _history(one), profile, current_start=START)
    assert spanish["text"] == "Declaradas 1 misión previas."
    assert "(62,50 mSv) no casa con" in spanish["checks"][1]["text"]
    assert [item["key"] for item in spanish["checks"]] == [item["key"] for item in told["checks"]]
    assert spanish["missions"] == told["missions"]


# --- Entorno de la misión ----------------------------------------------------------------------


def test_the_mission_environment_over_the_api(client: TestClient) -> None:
    english = client.get("/api/mission/profile", headers=ENGLISH_HEADERS).json()
    spanish = client.get("/api/mission/profile").json()
    assert english["source_text"] == (
        "Starting value from the configuration (EMMA_MISSION_PROFILE): no change has been signed."
    )
    assert english["rule"].startswith("The starting environment is the one in the configuration.")
    assert english["descriptive"].endswith("changes a level, a score or an alert.")
    assert spanish["source_text"].startswith("Valor de partida de la configuración")
    assert spanish["rule"] == mission_profile_changes.RULE
    for key in ("id", "configured", "source"):
        assert english[key] == spanish[key]
    assert [item["id"] for item in english["profiles"]] == [
        item["id"] for item in spanish["profiles"]
    ]
    _assert_plain_english([english["source_text"], english["rule"], english["descriptive"]])


def test_the_mission_environment_sentences_in_english(english: None) -> None:
    state = {"source": mission_profile_changes.REGISTRY, "ledger_index": 12, "declared_by": "Ana"}
    assert mission_profile_changes.source_text(state) == (
        "Declared in the signed ledger (entry 12) by Ana."
    )
    assert mission_profile_changes.display("no-existe") == "«no-existe» (not in the catalogue)"
    entry = {"previous": "no-existe", "profile": "otro", "reason": "cambio de plan"}
    assert mission_profile_changes.chronicle_sentence(entry) == (
        "mission environment: from «no-existe» (not in the catalogue) to «otro» (not in the "
        "catalogue); reason: cambio de plan"
    )


# --- Enlace con Tierra simulado ----------------------------------------------------------------


def _link_change(index: int, state: str, at: str) -> dict[str, Any]:
    return {
        "signer": CONSOLE_IDENTITY, "ledger_index": index, "state": state, "at": at,
        "declared_by": "Ana", "note": "", "recorded": at,
    }


def test_the_simulated_link_in_english(english: None) -> None:
    quiet = link_sync.view([], [], None)
    assert quiet["label"] == "Simulated link with Earth (declared by a person)"
    assert quiet["state"] == "up" and quiet["state_display"] == "up"
    assert quiet["crew_sentence"].startswith("Nobody has declared the simulated link with Earth")
    assert quiet["ground_sentence"] == (
        "Earth has everything from on board: without ephemerides there is no delay and the link "
        "is up."
    )
    down = _link_change(3, "down", "2026-03-01T10:00:00+00:00")
    waiting = [
        {"signer": "sensor", "instant": "2026-03-01T11:00:00+00:00", "index": 4,
         "basis": "effective"},
    ]
    cut = dt.datetime(2026, 3, 1, 12, 0, tzinfo=dt.UTC)
    held = link_sync.view([down], waiting, cut)
    assert held["state_display"] == "down"
    assert held["crew_sentence"] == (
        "Simulated link with Earth down since 2026-03-01 10:00 UTC, declared by Ana. 1 entry "
        "waiting to be sent to Earth since 2026-03-01 11:00 UTC. They are sent in the order in "
        "which they were signed once it is declared restored; nothing is lost."
    )
    assert held["ground_sentence"] == (
        "Earth has data up to 2026-03-01 10:00 UTC: the simulated link was declared down then. "
        "1 entry still to arrive."
    )
    assert held["history"][0]["state_display"] == "down"
    back = link_sync.view([down, _link_change(5, "up", "2026-03-01T11:30:00+00:00")], waiting, cut)
    assert back["history"][0]["state_display"] == "restored"
    assert back["crew_sentence"].startswith("Simulated link with Earth restored since")
    owned = [
        [view[key] for key in (
            "label", "state_display", "crew_sentence", "ground_sentence", "rule", "not_measured",
            "not_read_by", "known_only_here", "instant_basis",
        )]
        for view in (quiet, held, back)
    ]
    _assert_plain_english(owned)

    spanish = _spanish(link_sync.view, [down], waiting, cut)
    assert spanish["state_display"] == "caído" and spanish["state"] == held["state"] == "down"
    assert "1 asiento pendiente de enviar a Tierra desde" in spanish["crew_sentence"]
    for key in ("cut", "held", "held_since", "to_send", "to_arrive", "version"):
        assert spanish[key] == held[key]


def test_the_simulated_link_over_the_api(client: TestClient) -> None:
    english = client.get("/api/link-sync", headers=ENGLISH_HEADERS).json()
    spanish = client.get("/api/link-sync").json()
    assert english["rule"].startswith("Earth has what was signed on board up to the light time")
    assert spanish["rule"] == link_sync.RULE
    assert spanish["crew_sentence"].startswith("Nadie ha declarado caído el enlace")
    assert english["state"] == spanish["state"]


# --- Cambio de turno ---------------------------------------------------------------------------


def test_the_shift_change_in_english(english: None) -> None:
    told = shift.describe()
    assert told["kind"] == shift.KIND
    assert told["display"] == "Shift or sleep schedule change"
    assert told["distinction"].startswith("A shift change is the interval in which")
    # La cita de la fuente, tal cual en su idioma, en los dos.
    quote = "«These abrupt shifts in the imposed sleep–wake schedule can induce circadian"
    assert quote in told["source_says"] and quote in shift.SOURCE_SAYS
    assert told["source"]["relevance"].startswith("Introduction: on the ISS crew are often asked")
    _assert_plain_english([told["display"], told["distinction"], told["source_says"]])
    spanish = _spanish(shift.describe)
    assert spanish["display"] == shift.DISPLAY
    assert spanish["source"]["relevance"] == shift.RELEVANCE


# --- Recursos declarados -----------------------------------------------------------------------


def _declaration(index: int, resource: str, state: str, note: str = "") -> dict[str, Any]:
    return {
        "resource": resource, "state": state, "since": "2026-03-01T10:00:00+00:00", "note": note,
        "declared_by": "Ana", "ledger_index": index, "recorded": "2026-03-01T10:00:00+00:00",
    }


def test_the_declared_resources_in_english(english: None) -> None:
    empty = resources.overview([], {})
    assert empty["undeclared_display"] == "undeclared"
    assert [item["display"] for item in empty["states"]] == [
        "declared available", "declared unavailable",
    ]
    assert re.fullmatch(
        r"Declared resources: 0 \(0 unavailable\)\. Undeclared: \d+; of those EMMA does not know "
        r"whether they are on board\.",
        empty["summary"],
    )
    names = {item["key"]: item["name"] for item in empty["resources"]}
    assert names["ared"] == "ARED (resistive exercise)"
    assert names["saliva-sample-kit"] == "saliva sample kit"
    assert {item["state_display"] for item in empty["resources"]} == {"undeclared"}

    declared = [
        _declaration(7, "ared", "unavailable", "cable roto"),
        _declaration(8, "ared", "available"),
    ]
    first, second = resources.history(declared)
    assert resources.sentence(first) == (
        "resource «ARED (resistive exercise)»: declared unavailable (previously on record as "
        "undeclared; declared by a person; EMMA keeps no inventory); note: cable roto"
    )
    assert second["previous_state_display"] == "declared unavailable"
    assert second["state"] == "available" and second["previous_state"] == "unavailable"

    measure = {
        "resource_keys": ["ared", "trained-operator"],
        "resources": ["ARED (ejercicio resistivo)", "operador entrenado"],
    }
    lacking = resources.describe(measure, declared[:1])
    assert lacking["state"] == resources.SOME_UNAVAILABLE
    assert lacking["text"] == (
        "On record as unavailable: ARED (resistive exercise). Undeclared: trained operator."
    )
    assert lacking["caveat"].endswith(
        "The countermeasure is offered all the same: whether it can be done is for a person to "
        "judge."
    )
    assert resources.describe({}, [])["text"] == "It asks for no resources."
    ready = resources.describe({**measure, "resource_keys": ["ared"], "resources": ["x"]}, declared)
    assert ready["text"] == "All the resources it asks for are on record as declared available."
    assert ready["items"][0]["description"] == "x"
    _assert_plain_english([
        {key: value for key, value in empty.items() if key != "history"}, lacking["text"],
        lacking["caveat"], lacking["label"], resources.sentence(second),
    ])

    spanish = _spanish(resources.describe, measure, declared[:1])
    assert spanish["text"] == (
        "Consta como no disponible: ARED (ejercicio resistivo). Sin declarar: operador entrenado."
    )
    assert spanish["state"] == lacking["state"]
    assert [item["key"] for item in spanish["items"]] == [item["key"] for item in lacking["items"]]


def test_the_declared_resources_over_the_api(client: TestClient) -> None:
    english = client.get("/api/resources", headers=ENGLISH_HEADERS).json()
    spanish = client.get("/api/resources").json()
    assert english["label"] == "declared by a person; EMMA keeps no inventory"
    assert spanish["label"] == resources.DECLARED_LABEL
    assert spanish["undeclared_display"] == "sin declarar"
    assert [item["key"] for item in english["resources"]] == [
        item["key"] for item in spanish["resources"]
    ]
    assert {item["name"] for item in spanish["resources"]} == {
        item.name for item in resources.vocabulary().values()
    }
    assert not {item["name"] for item in english["resources"]} & {
        item["name"] for item in spanish["resources"]
    }


# --- Inventario --------------------------------------------------------------------------------


def test_the_inventory_in_english(client: TestClient) -> None:
    english = client.get("/api/inventory", headers=ENGLISH_HEADERS).json()
    spanish = client.get("/api/inventory").json()
    assert [item["label"] for item in english["categories"]] == [
        "Medications", "Food", "Medical equipment",
    ]
    assert [item["label"] for item in spanish["categories"]] == [
        "Medicamentos", "Alimentos", "Equipo médico",
    ]
    assert [item["id"] for item in english["categories"]] == list(inventory.CATEGORY_IDS)
    assert english["undeclared_display"] == "undeclared"
    assert spanish["undeclared_display"] == inventory.UNDECLARED_DISPLAY
    assert english["autonomy_rule"].startswith("Autonomy = stock / declared daily use")
    assert spanish["note"] == inventory.NOTE
    owned = ("label", "note", "rule", "autonomy_rule", "alternatives_rule", "scope")
    _assert_plain_english([english[key] for key in owned])


# --- Con qué reglas se firmó -------------------------------------------------------------------


def test_the_rules_sentence_in_english_and_the_fingerprint_untouched() -> None:
    today = versioning.rules_version()
    with i18n.use("en"):
        assert versioning.rules_version() == today
        assert today.startswith("reglas@")
        assert versioning.decided_with(None) == {
            "rules_version": None, "same_as_today": None,
            "text": "no version recorded: the entry does not carry it",
        }
        assert versioning.decided_with(today)["text"] == (
            f"decided with {today}; same version as today"
        )
        other = versioning.decided_with("reglas@0000000000000000")
        assert other["text"] == (
            f"decided with reglas@0000000000000000; different from today's: {today} today"
        )
        assert (other["rules_version"], other["same_as_today"]) == (
            "reglas@0000000000000000", False,
        )
    assert versioning.decided_with("reglas@0000000000000000")["text"] == (
        f"decidido con reglas@0000000000000000; distinta de la de hoy: {today} hoy"
    )


# --- Lo firmado no cambia con el idioma --------------------------------------------------------


def _signed_after_declaring(client: TestClient, headers: dict[str, str]) -> list[Any]:
    routes.reset_store(routes.new_store())
    posts = (
        ("/api/mission-mode", {"level": "minimal", "reason": "poca energía", "declared_by": "Ana"}),
        ("/api/resources", {
            "resource": "ared", "state": "unavailable", "since": "2026-03-01T10:00:00+00:00",
            "note": "cable roto", "declared_by": "Ana",
        }),
        ("/api/link-sync", {
            "state": "down", "at": "2026-03-01T10:00:00+00:00", "declared_by": "Ana",
        }),
        ("/api/mission/profile", {"profile": "lunar-surface", "declared_by": "Ana"}),
    )
    for path, body in posts:
        answer = client.post(path, json=body, headers=headers)
        assert answer.status_code == 201, (path, answer.text)
    return [
        (entry.entry_type, {k: v for k, v in (entry.payload or {}).items() if k != SALT_FIELD})
        for entry in routes.get_store().ledger.entries
    ]


def test_declaring_in_english_signs_the_same_as_declaring_in_spanish(client: TestClient) -> None:
    spanish = _signed_after_declaring(client, {})
    english = _signed_after_declaring(client, ENGLISH_HEADERS)
    assert len(spanish) >= 4
    assert english == spanish
    signed = json.dumps(english, ensure_ascii=False, default=str)
    for word in ("minimal level", "declared unavailable", "resistive exercise", "restored"):
        assert word not in signed
