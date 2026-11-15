"""El hábitat en inglés: cabina, módulos, sistemas declarados, radiación y anclas.

Por qué existe: casi todo lo que la pantalla del hábitat enseña lo redacta el backend, y su
castellano no se puede mover —el requisito de cada `Limit` entra en `rules_version()`, las
pruebas en castellano lo fijan y las campañas de mutantes lo buscan letra a letra—. El inglés va
al lado (`i18n.en`, `i18n.tr`, los hermanos `.en.json`) y se resuelve al servir. Aquí se comprueba
que quien pide inglés lo recibe entero y con punto decimal, que quien no lo pide recibe el
castellano de siempre, que los identificadores son los mismos en los dos idiomas, que la huella
de reglas no se mueve y que el inglés no afirma más que el castellano.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import habitat as habitat_api
from app.core import i18n, versioning
from app.environment import habitat, systems
from app.environment.donki import EventType, Severity, SolarEvent
from app.ingest import habitat_simulator
from app.ingest.habitat_simulator import HabitatSimulator
from tests.conftest import ENGLISH_HEADERS

_SPANISH_ONLY = re.compile(r"[áéíóúñ¿¡«»]", re.IGNORECASE)
_FORBIDDEN = re.compile(r"certified|validated|diagnos|administer|must take", re.IGNORECASE)
_DECIMAL_COMMA = re.compile(r"\d,\d")

# Textos que el hábitat sirve y redacta otro módulo: su inglés es de su unidad, no de esta.
_FOREIGN_KEYS = {"personal_exposure", "freshness", "data_age"}


def _strings(value: Any, skip: frozenset[str] = frozenset()) -> list[str]:
    """Todas las cadenas de un cuerpo, sin las de las claves que redacta otro módulo."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [
            text for key, item in value.items() if key not in skip
            for text in _strings(item, skip)
        ]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item, skip)]
    return []


def _assert_plain_english(texts: list[str]) -> None:
    for text in texts:
        assert not _SPANISH_ONLY.search(text), text
        assert not _FORBIDDEN.search(text), text


def _without(value: Any, keys: set[str]) -> Any:
    """El mismo cuerpo sin los campos de texto: lo que tiene que ser igual en los dos idiomas."""
    if isinstance(value, dict):
        return {k: _without(v, keys) for k, v in value.items() if k not in keys}
    if isinstance(value, list):
        return [_without(item, keys) for item in value]
    return value


# --------------------------------------------------------------------------- #
# Los hermanos ingleses de los dos ficheros de datos
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", [habitat.MODULES_PATH, systems.SYSTEMS_PATH])
def test_the_overlay_covers_every_shown_string_and_stays_sober(path: Any) -> None:
    spanish = json.loads(path.read_text(encoding="utf-8"))
    keys = {
        item["key"]
        for name in ("modules", "systems", "states") for item in spanish.get(name, [])
    }
    keys |= set(spanish.get("basis_refs", [])) | {
        param for item in spanish.get("systems", []) for param in item["parameters"]
    }
    # Sin pareja: las claves y las fichas (identificadores) y «nominal», igual en los dos idiomas.
    assert i18n.missing(path, spanish, skip=lambda text: text in keys or text == "nominal") == []
    overlay = i18n.overlay(path)
    assert overlay
    for spanish_text, english in overlay.items():
        assert english.strip() and english != spanish_text
        assert not _FORBIDDEN.search(english), english
        assert not re.search(r"[áéíóúñ¿¡«»]", english, re.IGNORECASE), english
    # Ninguna entrada sobra: una cadena que ya no está en el castellano sería inglés huérfano.
    assert set(overlay) <= set(_strings(spanish))


def test_the_declared_label_is_the_same_in_the_registry_and_in_the_overlay(english: None) -> None:
    assert i18n.loc(systems.DECLARED_LABEL) == i18n.localized(
        systems.DECLARED_LABEL, systems.SYSTEMS_PATH
    ) == "declared by a person, not telemetry"


def test_shared_vocabulary_of_states_and_modules(english: None) -> None:
    assert [systems.state_display(key) for key in systems.STATES] == [
        "nominal", "degraded", "out of service", "not declared",
    ]
    assert systems.scope_display(None) == "whole system"
    assert systems.scope_display("esclusa") == habitat.module_display("esclusa") == "Airlock"
    assert habitat.module_display("ya-no-existe") == "ya-no-existe"
    assert systems.system_display("ya-no-existe") == "ya-no-existe"


# --------------------------------------------------------------------------- #
# El catálogo de cabina
# --------------------------------------------------------------------------- #


def test_the_catalogue_reads_in_english_and_its_identifiers_do_not_move() -> None:
    everything = [*habitat.PARAMETERS.values(), *habitat.DISPLAY_ONLY.values()]
    spanish = [item.to_dict() for item in everything]
    with i18n.use("en"):
        english = [item.to_dict() for item in everything]
    # `source_row` es la fila tal como la escribe la norma, ya en inglés: entra en el barrido.
    _assert_plain_english(_strings(english))
    text = {
        "display", "group_display", "not_loinc_reason", "limit_note", "reference_label",
        "requirement", "kind_display", "label", "table", "condition", "title", "name",
    }
    assert _without(english, text) == _without(spanish, text)
    for before, after in zip(spanish, english, strict=True):
        assert after["display"] != before["display"]
        assert after["key"] == before["key"] and after["unit"] == before["unit"]
        assert [item["source_row"] for item in after["reference_requirements"]] == [
            item["source_row"] for item in before["reference_requirements"]
        ]


def test_the_requirement_is_translated_only_on_the_way_out(english: None) -> None:
    """El campo que entra en la huella de reglas sigue en castellano; lo servido, en inglés."""
    oxygen = habitat.PARAMETERS["cabin-ppo2"]
    assert [item.requirement for item in oxygen.limits] == [
        "[V2 6003] rango objetivo", "[V2 6003] hipoxia leve, media 1 h",
        "[V2 6003] mínimo absoluto", "[V2 6003] hiperoxia indefinida",
    ]
    served = oxygen.to_dict()["limits"]
    assert [item["requirement"] for item in served] == [
        "[V2 6003] target range", "[V2 6003] mild hypoxia, 1 h average",
        "[V2 6003] absolute minimum", "[V2 6003] indefinite hyperoxia",
    ]
    assert [item["kind_display"] for item in served] == [
        "target range", "normative limit", "normative limit", "normative limit",
    ]
    assert "not a health limit" in served[0]["label"]
    temperature = habitat.PARAMETERS["cabin-temperature"].to_dict()["limits"]
    assert temperature[0]["figure"]["name"] == "Figure 6.2-2"
    assert temperature[1]["kind_display"] == "comfort zone"
    assert habitat.PARAMETERS["cabin-formaldehyde"].to_dict()["limits"][0]["requirement"] == (
        "SMAC ceiling (> 7 d)"
    )
    assert versioning.rules_version() == versioning.rules_version.__wrapped__()


def test_what_is_only_shown_keeps_saying_it_is_not_evaluated(english: None) -> None:
    light = habitat.DISPLAY_ONLY["cabin-light"].to_dict()
    assert light["limit_note"].startswith("No general limit:")
    assert light["limit_note"].endswith("the reading is shown and not evaluated.")
    assert light["reference_label"] == "requirement per task; EMMA does not know the task"
    assert {item["table"] for item in light["reference_requirements"]} == {
        "Table 8.7-1", "Table 8.7-2",
    }
    assert "it is not the illuminance that EMMA reads" in (
        light["reference_requirements"][-1]["condition"]
    )
    silver = habitat.DISPLAY_ONLY["water-silver"].to_dict()
    assert [item["requirement"] for item in silver["reference_requirements"]] == [
        "SWEG 1 day", "SWEG 10 days", "SWEG 100 days", "SWEG 1000 days",
    ]
    assert "not fully protective of crew health" in silver["reference_requirements"][0]["condition"]
    assert "does not mean that harm is certain" in silver["reference_requirements"][2]["condition"]
    assert "does not compare the reading with any of them" in silver["reference_label"]
    assert silver["reference_source"]["title"].endswith("(November 2023)")
    toc = habitat.DISPLAY_ONLY["water-toc"].to_dict()
    assert toc["reference_requirements"][0]["condition"].endswith(
        "that all the measured carbon is formaldehyde (remark in the row)"
    )
    microbial = habitat.DISPLAY_ONLY["air-microbial"].to_dict()
    assert microbial["limit_note"].startswith("No limit read:")
    assert "which EMMA has not read" in microbial["limit_note"]
    assert microbial["reference_requirements"][0]["table"] == "section 6.2.8.5"
    assert microbial["group_display"] == "Microbiology of air and surfaces"


def test_an_excursion_names_its_parameter_in_english(english: None) -> None:
    moment = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)
    served = habitat.Excursion(
        "laboratorio", "cabin-ppo2", habitat.HEALTH, "[V2 6003] mínimo absoluto",
        moment, moment, 118.04,
    ).to_dict()
    assert served["display"] == "Cabin O2 (partial pressure)"
    assert served["requirement"] == "[V2 6003] absolute minimum"
    assert (served["module"], served["parameter"], served["kind"]) == (
        "laboratorio", "cabin-ppo2", "health",
    )


# --------------------------------------------------------------------------- #
# La radiación del hábitat
# --------------------------------------------------------------------------- #


def _radiation(event: SolarEvent | None, known: bool, **extra: Any) -> dict[str, Any]:
    return habitat.radiation_state(
        [], event, known, extra.pop("age", None), extra.pop("freshness", {}),
        dt.timedelta(days=3), **extra,
    )


def test_the_solar_sentences_in_english(english: None) -> None:
    event = SolarEvent(
        event_id="2026-11-01T10:00:00-SEP-001", event_type=EventType.SEP,
        time=dt.datetime(2026, 11, 1, 10, tzinfo=dt.UTC), severity=Severity.HIGH,
        instruments=(), linked_event_ids=(), flare_class=None,
        link="https://example.invalid/sep",
    )
    assert _radiation(None, False)["solar_event"]["text"] == (
        "No data from NASA DONKI: it is not known whether a solar particle event is in effect."
    )
    assert _radiation(None, True)["solar_event"]["text"] == (
        "No solar particle event of high or severe severity in NASA DONKI in the last 3 days."
    )
    active = _radiation(event, True)["solar_event"]
    assert active["text"] == (
        "SEP 2026-11-01T10:00:00-SEP-001, of 2026-11-01 10:00 UTC, according to NASA DONKI."
    )
    assert active["state"] == "active" and active["display"] == "Solar event in effect"
    stale = _radiation(
        None, True, age=("hace 9 días", 9 * 86400.0), freshness={"is_current": False},
        latest_recorded=event,
    )["solar_event"]
    assert stale["state"] == "unavailable"
    assert stale["text"].startswith("The NASA DONKI data at hand are stale (hace 9 días):")
    assert stale["text"].endswith("it is not known whether a solar particle event is in effect.")
    assert stale["latest_recorded"]["text"].endswith("UTC; it is not in effect.")
    empty = _radiation(None, True)
    assert empty["dose_rate"]["missing_text"] == "No dose rate reading recorded."
    assert empty["summary"].startswith("Absorbed dose rate: no reading recorded. Solar event in")
    _assert_plain_english(_strings(empty, frozenset(_FOREIGN_KEYS)))


def test_the_set_aside_sentences_keep_their_slots() -> None:
    for template in (habitat_api.DOSE_RATE_SET_ASIDE_SHOWN, habitat_api.DOSE_RATE_SET_ASIDE_ONLY):
        with i18n.use("en"):
            english = i18n.loc(template)
        assert english != template
        assert re.findall(r"\{\w+\}", english).count("{typed}") == 1
        assert sorted(set(re.findall(r"\{\w+\}", english))) == ["{analysed}", "{typed}"]
        _assert_plain_english([english])


# --------------------------------------------------------------------------- #
# Los sistemas declarados y el enlace con Tierra
# --------------------------------------------------------------------------- #


def _told(index: int, system: str, state: str, by: str = "CMO", **extra: Any) -> dict[str, Any]:
    return {
        "system": system, "state": state, "module": extra.get("module"),
        "at": f"2026-11-0{index + 1}T10:00:00+00:00", "note": extra.get("note", ""),
        "declared_by": by, "ledger_index": index, "recorded": "2026-11-09T00:00:00+00:00",
    }


def test_a_declaration_reads_as_one_english_sentence() -> None:
    declarations = [
        _told(0, "air-revitalization", "degraded", module="laboratorio", note="filtro"),
        _told(1, "air-revitalization", "degraded", module="laboratorio"),
    ]
    spanish = [systems.sentence(item) for item in systems.history(declarations)]
    assert spanish == [
        "sistema Revitalización de aire en Laboratorio: estado declarado «degradado» (antes "
        "constaba «sin declarar»; declarado por una persona, no telemetría); nota: filtro",
        "sistema Revitalización de aire en Laboratorio: estado declarado «degradado» (sin "
        "cambio respecto a lo declarado antes; declarado por una persona, no telemetría)",
    ]
    with i18n.use("en"):
        told = systems.history(declarations)
        english = [systems.sentence(item) for item in told]
    assert english == [
        "system Air revitalization in Laboratory: declared state “degraded” (“not declared” "
        "was on record before; declared by a person, not telemetry); note: filtro",
        "system Air revitalization in Laboratory: declared state “degraded” (no change from "
        "what was declared before; declared by a person, not telemetry)",
    ]
    # Lo que se compara y se firma no cambia de idioma.
    assert [
        (item["system"], item["state"], item["previous_state"], item["module"]) for item in told
    ] == [
        ("air-revitalization", "degraded", "undeclared", "laboratorio"),
        ("air-revitalization", "degraded", "degraded", "laboratorio"),
    ]
    assert [span["state"] for span in systems.off_nominal_spans(declarations)] == ["degraded"]


def test_the_earth_link_sentences_in_english() -> None:
    declarations = [
        _told(0, "communications", "out-of-service", by="CMO", note="antena"),
        _told(1, "communications", "out-of-service", by="CDR"),
    ]
    spanish = systems.earth_link(declarations)
    assert spanish["headline"] == (
        "Enlace declarado «fuera de servicio» desde 2026-11-01 10:00 UTC por CMO, confirmado "
        "por CDR (declarado por una persona, no telemetría)"
    )
    with i18n.use("en"):
        english = systems.earth_link(declarations)
        nobody = systems.earth_link([])
        nominal = systems.earth_link([_told(0, "communications", "nominal")])
    assert english["headline"] == (
        "Link declared “out of service” since 2026-11-01 10:00 UTC by CMO, confirmed by CDR "
        "(declared by a person, not telemetry)"
    )
    assert english["sentence"] == (
        "Link with Earth declared “out of service” since 2026-11-01 10:00 UTC by CMO, confirmed "
        "by CDR (declared by a person, not telemetry). EMMA does not measure the link: the "
        "delay comes from the ephemerides and does not change with this declaration."
    )
    with i18n.use("en"):
        noted = systems.earth_link(declarations[:1])
    assert noted["sentence"].endswith(" Note from the person who declared it: antena")
    assert nobody["headline"] is None and nominal["headline"] is None
    assert nobody["sentence"].startswith(
        "Nobody has declared the state of the link with Earth (system Communications): it is "
        "not known whether it works."
    )
    assert nominal["sentence"].startswith("Link with Earth declared “nominal” since ")
    text = {"system_display", "state_display", "label", "headline", "sentence", "scope_rule"}
    assert _without(english, text) == _without(spanish, text)
    _assert_plain_english(_strings([english, nobody, nominal]))


# --------------------------------------------------------------------------- #
# El simulador de cabina
# --------------------------------------------------------------------------- #


def test_the_simulator_still_says_it_is_design_and_not_telemetry(english: None) -> None:
    described = HabitatSimulator(co2_excursion=True, extra_modules=("laboratorio",)).describe()
    assert described["basis"] == (
        "design values within NASA-STD-3001 Vol 2; it is not real telemetry"
    )
    assert str(described["modules_basis"]).startswith(
        "design assumption without bibliographic support:"
    )
    assert described["display_only"] == {
        "cabin-light": i18n.loc(habitat_simulator.LIGHT_EVIDENCE)
    }
    light = str(i18n.loc(habitat_simulator.LIGHT_EVIDENCE))
    assert light.startswith("EMMA design without a source:")
    assert "with no day and night cycle" in light and "only shown and not evaluated" in light
    assert (described["module"], described["extra_modules"]) == (
        "habitat-principal", ["laboratorio"],
    )
    _assert_plain_english(_strings(described))


# --------------------------------------------------------------------------- #
# Por la API: el idioma lo pide la cabecera, y sin ella todo sigue en castellano
# --------------------------------------------------------------------------- #


@pytest.fixture
def seeded(client: TestClient) -> TestClient:
    response = client.post(
        "/api/simulate", params={"scenario": "co2-fatigue", "crew_size": 2, "seed": 7},
    )
    assert response.status_code == 201, response.text
    for body in (
        {"system": "communications", "state": "degraded", "note": "antena"},
        {"system": "air-revitalization", "state": "out-of-service", "module": "laboratorio"},
    ):
        declared = client.post(
            "/api/habitat/systems/status",
            json={"at": "2026-11-10T10:00:00+00:00", "declared_by": "CMO", **body},
        )
        assert declared.status_code == 201, declared.text
    return client


def test_simulate_describes_the_cabin_in_the_language_asked(client: TestClient) -> None:
    params = {"scenario": "co2-fatigue", "crew_size": 2, "seed": 7}
    english = client.post("/api/simulate", params=params, headers=ENGLISH_HEADERS)
    assert english.status_code == 201, english.text
    assert "design values within NASA-STD-3001 Vol 2; it is not real telemetry" in english.text
    assert "no es telemetría real" not in english.text
    spanish = client.post("/api/simulate", params=params)
    assert "valores de diseño dentro de NASA-STD-3001 Vol 2; no es telemetría real" in spanish.text
    assert "supuesto de diseño sin respaldo bibliográfico" in spanish.text


def test_the_habitat_state_in_english_and_in_spanish(seeded: TestClient) -> None:
    spanish = seeded.get("/api/habitat").json()
    english = seeded.get("/api/habitat", headers=ENGLISH_HEADERS).json()
    assert spanish["active"][0]["display"] == "CO2 de cabina (presión parcial)"
    assert english["active"][0]["display"] == "Cabin CO2 (partial pressure)"
    assert english["active"][0]["requirement"] == spanish["active"][0]["requirement"] == "[V2 6004]"
    radiation = english["radiation"]
    assert radiation["display"] == "Radiation"
    assert radiation["module_text"].startswith("module not declared:")
    assert radiation["shielding"].startswith("No shielding factors:")
    assert radiation["note"].startswith("Shown and not evaluated here:")
    assert radiation["dose_rate"]["readings"][0]["origin_text"].startswith(
        "reading from the dosimeter of crew-01 (source “simulator:"
    )
    # La cifra, con punto en inglés y con coma en castellano; es la misma lectura.
    summary = radiation["summary"]
    assert summary.startswith("Absorbed dose rate, latest reading of each dosimeter (module not")
    assert re.search(r"crew-01 \d+\.\d µGy/h", summary) and not _DECIMAL_COMMA.search(summary)
    assert "Tasa de dosis absorbida" not in summary and "sin factores de blindaje" not in summary
    before = spanish["radiation"]["summary"]
    assert before.startswith("Tasa de dosis absorbida, última lectura de cada dosímetro (módulo")
    assert re.search(r"crew-01 \d+,\d µGy/h", before)
    assert before.replace(",", ".").split("crew-01 ")[1].split(" ")[0] == (
        summary.split("crew-01 ")[1].split(" ")[0]
    )
    text = {
        "display", "module_text", "shielding", "note", "basis", "missing_text",
        "set_aside_display", "origin_text", "text", "source", "summary",
    }
    foreign = text | _FOREIGN_KEYS
    assert _without(english, foreign) == _without(spanish, foreign)
    _assert_plain_english(_strings(radiation, frozenset(_FOREIGN_KEYS)))


def test_the_parameters_route_in_english(client: TestClient) -> None:
    english = client.get("/api/habitat/parameters", headers=ENGLISH_HEADERS).json()
    spanish = client.get("/api/habitat/parameters").json()
    assert [item["display"] for item in english["parameters"]][:2] == [
        "Cabin CO2 (partial pressure)", "Cabin O2 (partial pressure)",
    ]
    assert [item["display"] for item in spanish["parameters"]][:2] == [
        "CO2 de cabina (presión parcial)", "O2 de cabina (presión parcial)",
    ]
    assert [item["key"] for item in english["display_only"]] == [
        item["key"] for item in spanish["display_only"]
    ]
    _assert_plain_english(_strings(english, frozenset(_FOREIGN_KEYS)))


def test_the_modules_route_in_english(client: TestClient) -> None:
    english = client.get("/api/habitat/modules", headers=ENGLISH_HEADERS).json()
    spanish = client.get("/api/habitat/modules").json()
    assert [item["display"] for item in english["modules"]] == [
        "Main habitat", "Laboratory", "Crew quarters", "Airlock",
    ]
    assert english["basis"].startswith("EMMA design parameter, without bibliographic support:")
    assert spanish["basis"] == habitat.MODULES_BASIS
    assert [item["display"] for item in spanish["modules"]][0] == "Hábitat principal"
    assert [item["key"] for item in english["modules"]] == [
        item["key"] for item in spanish["modules"]
    ]
    assert english["default"] == spanish["default"] == "habitat-principal"
    _assert_plain_english(_strings(english))


def test_the_systems_route_in_english_and_in_spanish(seeded: TestClient) -> None:
    spanish = seeded.get("/api/habitat/systems").json()
    english = seeded.get("/api/habitat/systems", headers=ENGLISH_HEADERS).json()
    assert english["label"] == "declared by a person, not telemetry"
    assert english["summary"] == (
        "Systems with some declared state: 2 of 10. Nothing is known about the others: that "
        "nobody has declared it does not mean that they work."
    )
    assert spanish["summary"].startswith("Sistemas con algún estado declarado: 2 de 10. De los")
    assert spanish["label"] == "declarado por una persona, no telemetría"
    assert [item["display"] for item in english["states"]] == [
        "nominal", "degraded", "out of service", "not declared",
    ]
    assert [item["display"] for item in spanish["states"]] == [
        "nominal", "degradado", "fuera de servicio", "sin declarar",
    ]
    air = english["systems"][0]
    assert (air["key"], air["display"]) == ("air-revitalization", "Air revitalization")
    assert [item["display"] for item in air["parameters"]] == [
        "Cabin CO2 (partial pressure)", "Cabin O2 (partial pressure)",
    ]
    assert air["statuses"][0]["module_display"] == "Laboratory"
    assert air["statuses"][0]["state_display"] == "out of service"
    undeclared = next(item for item in english["systems"] if item["key"] == "power")
    assert undeclared["statuses"][0]["module_display"] == "whole system"
    assert undeclared["statuses"][0]["state_display"] == "not declared"
    assert english["whole_system_display"] == "whole system"
    link = english["declared_link"]
    assert link["attention"] is True and link["state"] == "degraded"
    assert link["headline"] == (
        "Link declared “degraded” since 2026-11-10 10:00 UTC by CMO (declared by a person, not "
        "telemetry)"
    )
    assert link["sentence"].endswith(" Note from the person who declared it: antena")
    assert spanish["declared_link"]["headline"] == (
        "Enlace declarado «degradado» desde 2026-11-10 10:00 UTC por CMO (declarado por una "
        "persona, no telemetría)"
    )
    text = {
        "label", "note", "basis", "relation_basis", "not_coded", "rule", "since_basis",
        "whole_system_display", "display", "description", "summary", "system_display",
        "state_display", "previous_state_display", "module_display", "headline", "sentence",
        "scope_rule",
    }
    assert _without(english, text) == _without(spanish, text)
    # Las fichas del registro de evidencia (`basis_sources`) las redacta su unidad.
    _assert_plain_english(_strings(english, frozenset({"basis_sources"})))


def test_the_comparison_in_english(seeded: TestClient) -> None:
    params = {"key": "heart-rate", "parameter": "cabin-ppco2"}
    english = seeded.get("/api/crew/compare", params=params, headers=ENGLISH_HEADERS).json()
    spanish = seeded.get("/api/crew/compare", params=params).json()
    assert english["baseline_basis"].startswith("each reading minus the median of that crew")
    assert english["summary"]["window_basis"] == (
        "the 48 h before the latest reading of this indicator in the crew"
    )
    assert spanish["summary"]["window_basis"] == habitat_api.WINDOW_BASIS
    assert spanish["baseline_basis"] == habitat_api.BASELINE_BASIS
    states = {item["state"]: item["state_text"] for item in english["series"]}
    allowed = {
        "within": {"within the expected range"},
        "no_data": {"no data"},
        "no_recent": {"no readings in the compared window"},
        "deviating": {
            "readings outside the expected range", "sustained drift",
            "readings outside the expected range and sustained drift",
        },
    }
    assert states and all(text in allowed[state] for state, text in states.items())
    assert [item["state"] for item in english["series"]] == [
        item["state"] for item in spanish["series"]
    ]
    assert english["habitat"]["parameter"]["group_display"] == "Cabin atmosphere"
    assert english["habitat"]["excursions"][0]["display"] == "Cabin CO2 (partial pressure)"
    assert [item["points"] for item in english["series"]] == [
        item["points"] for item in spanish["series"]
    ]


def test_the_anchors_route_names_the_module_in_english(client: TestClient) -> None:
    declared = client.post("/api/location/anchors", json={
        "anchor_id": "AA:01", "module": "laboratorio", "since": "2026-11-01T00:00:00+00:00",
        "declared_by": "CMO",
    })
    assert declared.status_code == 201, declared.text
    english = client.get("/api/location/anchors", headers=ENGLISH_HEADERS).json()
    spanish = client.get("/api/location/anchors").json()
    assert english["anchors"][0]["display"] == "Laboratory"
    assert spanish["anchors"][0]["display"] == "Laboratorio"
    assert english["anchors"][0]["module"] == spanish["anchors"][0]["module"] == "laboratorio"
    assert english["anchors"][0]["anchor_id"] == "aa:01"
    # Los parámetros y el identificador de su respaldo no dependen del idioma.
    numbers = {"evidence_note"}
    assert _without(english["parameters"], numbers) == _without(spanish["parameters"], numbers)
    assert english["parameters"]["evidence"] == "unsupported"
