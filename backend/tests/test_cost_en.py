"""El coste de medir en inglés (`ingest/cost.py`, `data/measurement_cost.en.json`).

El castellano no se mueve: lo fijan `tests/test_measurement_cost.py` y las campañas `cost_*`.
Aquí se comprueba el otro idioma: que todo lo que se enseña tiene inglés, que el inglés no dice
más que el castellano (las mismas reservas: «sin fuente», «sin clasificar», la marca de la
deducción), que los identificadores no cambian y que pedirlo en inglés no deja nada en caché para
quien lo pide después en castellano.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from fastapi.testclient import TestClient

from app.core import i18n
from app.ingest import cost
from app.ingest.codes import CATALOG
from tests.conftest import ENGLISH_HEADERS

# Lo que se escribe igual en los dos idiomas: un nombre de equipo que ya es inglés y los sitios
# de un documento que son solo su título de apartado, copiado de la fuente.
SAME_IN_BOTH = frozenset({
    "wearable",
    "Materials and methods, «Immunophenotype analysis»",
    "Materials and methods, «Sample collection»",
    "«How to monitor»",
    "«More tips to keep in mind»",
    "«Biochemical markers»",
    "Materials and methods, «Blood samples»",
    "Methods, «Blood sampling»",
    "Materials and methods, «Diurnal salivary cortisol and DHEA»",
    "Methods",
    "«Radiation Detectors: REMs and HERA»",
    "Methods, «Processing»",
    "Discussion",
    "Abstract",
    "Procedure, «Pre-Mission Baseline»",
    "«Sensorimotor standard measures»",
    "2.2 The Cognition Battery",
    "«Background»",
    "«Sleep logs and actigraphy»",
    "«Experimental Design»",
    "Introduction",
    "Background",
    "«Cognition test battery (CTB)»",
    "«Cellular profile»",
})
# Lo que no se traduce nunca: identificadores, fichas, fechas y lo copiado de una fuente.
UNTRANSLATED_FIELDS = frozenset({"quote", "ref", "read_on"})
SPANISH = re.compile(r"[áéíóúñ¿¡]", re.IGNORECASE)
OVERCLAIM = re.compile(r"certified|validated|diagnos|administer|must take", re.IGNORECASE)
# Una cita de la fuente va entre comillas angulares y se queda en el idioma de la fuente.
QUOTED = re.compile(r"«[^»]*»")
# Lo que viene de otro módulo y lleva su propio inglés: los perfiles de misión y las fichas del
# registro de evidencia.
FOREIGN_FIELDS = frozenset({"quote", "term", "title", "source", "profiles"})


def _document() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(cost.COST_PATH.read_text(encoding="utf-8"))
    return document


def _shown_strings() -> list[str]:
    """Las cadenas de `measurement_cost.json` que llegan a la pantalla."""
    document = _document()
    found: list[str] = []
    for item in document["indicators"].values():
        found.extend(
            item[name] for name in ("equipment", "crew_time_basis", "inputs_basis") if name in item
        )
    for rule in document["dimension_rules"]:
        found.append(rule["basis"])
        for kind in ("sources", "discrepancies"):
            for reading in rule.get(kind, []):
                found.extend(
                    value for name, value in reading.items() if name not in UNTRANSLATED_FIELDS
                )
    found.extend(item["searched"] for item in document["searched_not_found"])
    return found


def _texts(value: Any, skip: frozenset[str] = FOREIGN_FIELDS) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in skip:
                yield from _texts(item, skip)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _texts(item, skip)


def _identifiers(item: dict[str, Any]) -> dict[str, Any]:
    """Lo que el código compara de un indicador: nada de esto cambia con el idioma."""
    return {
        "mode": item["mode"],
        "crew_time_minutes": item["crew_time_minutes"],
        "inputs": item.get("inputs"),
        "inherits": item.get("inherits"),
        "dimensions": {
            name: (held["value"], held["rule"], held["inherited_from"])
            for name, held in item["dimensions"].items()
        },
    }


def test_every_shown_string_of_the_data_has_its_english() -> None:
    shown = _shown_strings()
    assert len(shown) > 300
    assert i18n.missing(cost.COST_PATH, shown, skip=lambda text: text in SAME_IN_BOTH) == []
    # Y lo declarado igual en los dos idiomas no lleva una traducción escondida.
    assert not SAME_IN_BOTH & i18n.overlay(cost.COST_PATH).keys()


def test_the_overlay_has_no_orphan_and_translates_no_quote() -> None:
    document = _document()
    strings = i18n.overlay(cost.COST_PATH)
    assert sorted(strings.keys() - set(_shown_strings())) == []
    quotes = {
        reading["quote"]
        for rule in document["dimension_rules"]
        for kind in ("sources", "discrepancies")
        for reading in rule.get(kind, [])
    }
    assert quotes and not quotes & strings.keys()
    identifiers = {rule["id"] for rule in document["dimension_rules"]} | set(cost.DIMENSIONS)
    assert not identifiers & strings.keys()


def test_the_english_claims_no_more_and_keeps_no_spanish() -> None:
    english = [*i18n.overlay(cost.COST_PATH).values(), *cost._EN.values()]
    assert len(english) > 250
    for text in english:
        outside_quotes = QUOTED.sub("", text)
        assert not OVERCLAIM.search(outside_quotes), text
        assert not SPANISH.search(outside_quotes), text
        assert text.strip() == text and text


def test_the_admissions_survive_in_english() -> None:
    strings = i18n.overlay(cost.COST_PATH)
    assert strings["sin fuente"] == "no source"
    # Cada «sin fuente» del castellano sigue diciéndolo en inglés.
    for spanish, english in strings.items():
        assert spanish.count("sin fuente") <= english.count("no source"), spanish
        assert spanish.count("sin clasificar") <= english.count("unclassified"), spanish
        # La deducción de EMMA se rotula también en inglés, en la regla.
        if cost.DEDUCED_MARK in spanish:
            assert "EMMA deduces it" in english, spanish
    with i18n.use("en"):
        assert i18n.loc(cost.UNCLASSIFIED_DISPLAY) == "unclassified"
        assert i18n.loc(cost.NO_SOURCE) == "EMMA has no source"
        for word in cost.DIMENSIONS["automation"]["values"].values():
            assert "EMMA deduces it from the measurement class" in i18n.loc(word)


def test_every_constant_that_is_shown_has_its_english(english: None) -> None:
    for text in cost.MODES.values():
        assert i18n.loc(text) != text or not SPANISH.search(text)
    for spec in cost.DIMENSIONS.values():
        assert spec["display"] in cost._EN
        assert set(spec["values"].values()) <= cost._EN.keys()
    for text in _texts([cost.summary(), [cost.cost(key) for key in CATALOG]]):
        assert not SPANISH.search(QUOTED.sub("", text)), text


def test_what_is_copied_from_the_team_stays_as_written(english: None) -> None:
    for coverage, terms in (
        (cost.kb_coverage(), cost.KB_TERMS), (cost.conversation_coverage(), cost.CONVERSATION_TERMS)
    ):
        assert [item["term"] for item in coverage["terms"]] == [term for term, _ in terms]
        assert "(in Spanish): «" in coverage["origin"]
    # La frase del equipo, entera y en castellano, dentro de la presentación en inglés.
    assert cost.kb_coverage()["origin"].endswith(cost.KB_ORIGIN.partition(": ")[2])
    assert cost.kb_coverage()["origin"].startswith("Knowledge base §9")
    excluded = cost.conversation_coverage()["terms"][0]
    assert excluded["display"] == "Not included in EMMA" and excluded["kind"] == cost.EXCLUDED_KIND
    assert excluded["note"].startswith("Not included: ")


def test_an_indicator_in_english_keeps_its_identifiers() -> None:
    spanish = {key: cost.cost(key) for key in CATALOG}
    with i18n.use("en"):
        english = {key: cost.cost(key) for key in CATALOG}
    again = {key: cost.cost(key) for key in CATALOG}
    # Pedirlo en inglés no cambia lo que recibe después quien lo pide en castellano.
    assert again == spanish
    changed = 0
    for key, item in spanish.items():
        other = english[key]
        assert (item is None) == (other is None)
        if item is None or other is None:
            continue
        assert _identifiers(item) == _identifiers(other), key
        assert other["mode_display"] == cost._EN[item["mode_display"]]
        changed += other["equipment"] != item["equipment"]
    assert changed > 100
    heart = english["heart-rate"]
    assert heart is not None
    assert heart["crew_time_basis"] == "no source" and heart["mode_display"] == (
        "continuous and passive"
    )
    assert heart["dimensions"]["processing"]["display"] == "on board, on the device itself"
    assert heart["dimensions"]["mass"]["display"] == "unclassified"


def test_an_inherited_class_is_written_in_english(english: None) -> None:
    ratio = cost.cost("neutrophil-lymphocyte-ratio")
    assert ratio is not None
    held = ratio["dimensions"]["processing"]
    assert held["inherited_from"] == ["neutrophils", "lymphocytes"]
    assert held["basis"].startswith(
        "Calculated from neutrophils, lymphocytes, which give “requires sample return or "
        "analysis on Earth” (rule leucocitos-en-tierra). It comes from the same laboratory report"
    )
    assert "Calculado" not in held["basis"]


def test_a_figure_read_is_written_with_the_decimal_point_in_english() -> None:
    raw = {"a": {"mode": "continuous-passive", "equipment": "wearable"}}
    rule = {
        "id": "f1", "match": {"mode": "continuous-passive"},
        "set": {"mass": {"figure": "10.32", "unit": "lbs"}}, "basis": "leído",
        "sources": [{
            "ref": "nasa-hrp-roi-iss-facilities-2023",
            "quote": "16.2 x 10.1 x 6.5 inches, 10.32 lbs",
            "where": "diapositiva 8", "read_on": "2026-10-23",
        }],
    }
    with i18n.use("en"):
        found = cost.classify(raw, [rule])["a"]["mass"]
    assert found["display"] == "10.32 lbs"
    assert cost.classify(raw, [rule])["a"]["mass"]["display"] == "10,32 lbs"
    assert found["figure"] == cost.classify(raw, [rule])["a"]["mass"]["figure"]


def test_the_summary_in_english_counts_the_same() -> None:
    spanish = cost.summary()
    with i18n.use("en"):
        english = cost.summary()
    assert cost.summary() == spanish
    for name in ("indicators", "unclassified", "fully_classified", "unclassified_value"):
        assert english[name] == spanish[name]
    assert english["unclassified_display"] == "unclassified"
    assert english["searched_display"] == "Searched and not found"
    assert english["deduced_display"] == "EMMA's deduction, not a reading"
    for row, other in zip(spanish["dimensions"], english["dimensions"], strict=True):
        assert (row["key"], row["deduced"], row["unclassified"]) == (
            other["key"], other["deduced"], other["unclassified"]
        )
        assert [(item["value"], item["count"]) for item in row["values"]] == [
            (item["value"], item["count"]) for item in other["values"]
        ]
        assert other["display"] == cost._EN[row["display"]]
    for rule, other in zip(spanish["rules"], english["rules"], strict=True):
        assert (rule["id"], rule["indicators"]) == (other["id"], other["indicators"])
        assert other["basis"] == i18n.overlay(cost.COST_PATH)[rule["basis"]]
        for kind in ("sources", "discrepancies"):
            assert [item["quote"] for item in rule[kind]] == [item["quote"] for item in other[kind]]
            assert [item["ref"] for item in rule[kind]] == [item["ref"] for item in other[kind]]
    ground, other_ground = spanish["ground_dependence"], english["ground_dependence"]
    assert other_ground["display"] == "Today it is known afterwards"
    assert other_ground["no_source"] == "EMMA has no source"
    assert other_ground["value"] == ground["value"] and other_ground["rules"] == ground["rules"]
    assert [item["key"] for item in other_ground["indicators"]] == [
        item["key"] for item in ground["indicators"]
    ]
    assert [item["id"] for item in other_ground["profiles"]] == [
        item["id"] for item in ground["profiles"]
    ]


def test_the_routes_answer_in_the_language_asked(client: TestClient) -> None:
    spanish = client.get("/api/measurement-cost")
    english = client.get("/api/measurement-cost", headers=ENGLISH_HEADERS)
    assert spanish.status_code == 200 and english.status_code == 200
    # Sin cabecera, lo de siempre.
    assert spanish.json() == client.get("/api/measurement-cost").json()
    assert spanish.json()["summary"]["unclassified_display"] == "sin clasificar"
    by_key = {item["key"]: item for item in spanish.json()["indicators"]}
    assert by_key["heart-rate"]["crew_time_basis"] == "sin fuente"
    assert by_key["pvt-mean-rt"]["equipment"] == "test PVT"
    body = english.json()
    assert body["summary"]["unclassified_display"] == "unclassified"
    assert "Sin clasificar" not in json.dumps(body, ensure_ascii=False)
    other = {item["key"]: item for item in body["indicators"]}
    assert other.keys() == by_key.keys()
    assert other["heart-rate"]["crew_time_basis"] == "no source"
    assert other["urine-specific-gravity"]["equipment"] == (
        "urine sample and dipstick or refractometer"
    )
    # La cifra del texto, con punto: «urea / 2,14» en castellano.
    assert "urea / 2,14 ÷" in by_key["bun-creatinine-ratio"]["inputs_basis"]
    assert "urea / 2.14 ÷" in other["bun-creatinine-ratio"]["inputs_basis"]
    assert other["bun-creatinine-ratio"]["mode"] == by_key["bun-creatinine-ratio"]["mode"]

    listed = client.get("/api/indicators", headers=ENGLISH_HEADERS).json()["indicators"]
    measured = {item["key"]: item["measurement_cost"] for item in listed}
    assert measured["heart-rate"]["mode_display"] == "continuous and passive"
    plain = client.get("/api/indicators").json()["indicators"]
    assert {item["key"]: item["measurement_cost"] for item in plain}["heart-rate"][
        "mode_display"
    ] == "continuo y pasivo"
