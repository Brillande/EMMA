"""El inglés de las recomendaciones, las guías, las rutinas, la crónica y los gemelos (unidad 13).

Por qué existe: lo que la tripulación lee en «Qué hacer» lo redacta el backend, y desde que hay
dos idiomas (`core/i18n.py`) cada frase tiene dos formas. El castellano lo fijan las pruebas de
siempre; aquí se fija lo que el inglés tiene que cumplir y ninguna de ellas mira:

* que no quede texto sin traducir en lo que se sirve (los hermanos `.en.json` cubren su fichero);
* que el inglés recomiende e informe y no ordene (invariante 7), y que no diga más que el
  castellano: ni «certified», ni «validated», ni «diagnosis»;
* que los identificadores, las claves y las cifras sean los mismos en los dos idiomas, y que las
  cifras salgan con punto decimal;
* que sin pedir inglés la respuesta sea la de antes, y que pedirlo no mueva la huella de reglas.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import guides, planner_ground, routines, sharing, timeline, twins
from app.advisor import check_cost, countermeasures, effects, prior_response
from app.advisor.followup import CAUSALITY_NOTE, decision_note, followups
from app.analysis.risk import RiskLevel
from app.core import i18n, versioning
from app.core.config import Settings
from app.evidence import research_countermeasures
from app.ingest.codes import get
from app.ingest.fhir import VitalObservation
from tests.conftest import ENGLISH_HEADERS

T0 = dt.datetime(2026, 12, 1, 8, 0, tzinfo=dt.UTC)
SLEEP = "bh-protect-sleep"

# Lo que el inglés no puede decir: una certificación, un diagnóstico o una orden médica.
_FORBIDDEN = re.compile(
    r"certified|validated|diagnos|administer|must take|\bshould\b|ought to|(is|are) recommended"
    r"|advisable|it is best|had better|\bworth\b|is reasonable|consider whether|medication"
    r"|consistent with|compatible with|suggests|confirms the|rules out the|\balways\b"
    r"|\bnever\b|zero risk|\bproven\b|impossible|without doubt|certainly|definitely|guarantee"
    r"|\b(?<!radiation )dos(e|es|age|ing)\b(?! rate| equivalent)",
    re.IGNORECASE,
)
_SPANISH = re.compile(r"[áéíóúñ¿¡]", re.IGNORECASE)
# Lo que va entre comillas angulares es la frase literal de una fuente o un rótulo de la consola.
_QUOTED = re.compile(r"«[^»]*»")

OVERLAYS = (
    countermeasures.LIBRARY_PATH,
    effects.EFFECTS_PATH,
    research_countermeasures.RESEARCH_PATH,
    guides.GUIDES_PATH,
    guides.GLOSSARY_PATH,
    routines.DATA,
    sharing.SHARING_PATH,
)


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def _raw(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _decision(index: int, action: str, when: dt.datetime, **extra: str) -> dict[str, Any]:
    return {
        "ledger_index": index, "action": action, "countermeasure_id": SLEEP,
        "domain": "behavioral", "level": "concern", "reference_time": when.isoformat(),
        "decided_by": "CDR", "reason": "", "adoption_index": "", **extra,
    }


# --------------------------------------------------------------------------- #
# Los hermanos ingleses de los ficheros de datos
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", OVERLAYS, ids=lambda path: path.name)
def test_each_overlay_translates_only_text_of_its_file_and_says_nothing_stronger(
    path: Path,
) -> None:
    strings = i18n.overlay(path)
    assert strings, f"{path.name} no tiene hermano inglés"
    spanish = set(_strings(_raw(path)))
    for original, english in strings.items():
        # Una clave que no sea un valor entero del fichero no traduciría nada: un despiste.
        assert original in spanish, f"{path.name}: {original[:60]!r} no es un valor del fichero"
        assert english.strip(), original
        # Lo que va entre comillas angulares es de la fuente: no lo redacta EMMA.
        assert not _FORBIDDEN.search(_QUOTED.sub("", english)), english
        assert not _SPANISH.search(_QUOTED.sub("", english)), english


def test_the_english_of_the_module_constants_passes_the_same_list() -> None:
    """El inglés registrado de las constantes de estos módulos: ni orden, ni certeza, ni dosis."""
    modules = (
        check_cost, countermeasures, effects, prior_response, guides, routines, sharing,
        timeline, twins, research_countermeasures,
    )
    checked = 0
    for module in modules:
        for value in vars(module).values():
            if not isinstance(value, (str, dict, tuple)):
                continue
            for text in _strings(value):
                with i18n.use("en"):
                    english = i18n.loc(text)
                if english == text:
                    continue
                checked += 1
                assert not _FORBIDDEN.search(_QUOTED.sub("", english)), english
                assert not _SPANISH.search(_QUOTED.sub("", english)), english
    assert checked > 40


def test_the_library_overlay_recommends_and_does_not_order() -> None:
    """Cada acción de la biblioteca, en inglés, es una sugerencia («Consider…»), nunca un
    imperativo a secas (invariante 7) ni una deliberación afirmada («It is recommended to…»),
    que el filtro de lenguaje bloquea en inglés igual que «Se recomienda…» en castellano."""
    with i18n.use("en"):
        actions = [item.to_dict()["action"] for item in countermeasures.library().values()]
    assert len(actions) == len(countermeasures.library())
    for action in actions:
        assert action.startswith("Consider "), action


def test_the_overlays_leave_the_spanish_files_and_the_fingerprint_alone() -> None:
    fingerprint = versioning.rules_version()
    digest = hashlib.sha256(countermeasures.LIBRARY_PATH.read_bytes()).hexdigest()
    with i18n.use("en"):
        assert versioning.rules_version() == fingerprint
        countermeasures.overview()
    assert versioning.rules_version() == fingerprint
    assert hashlib.sha256(countermeasures.LIBRARY_PATH.read_bytes()).hexdigest() == digest
    # Lo cacheado sigue en castellano después de servirlo en inglés.
    assert countermeasures.get(SLEEP).action.startswith("Proteger el periodo de sueño")


def _library_text(item: dict[str, Any]) -> list[str]:
    fields = (
        "action", "indication", "resources", "resources_note", "crew_time_basis",
        "followup_basis", "contraindications_display", "adverse_effects_note", "family_display",
    )
    texts = [text for field in fields for text in _strings(item[field])]
    if item["protocol_ref"]:
        texts.append(item["protocol_ref"]["relevance"])
    return texts


def test_the_whole_library_is_served_in_english_with_the_same_identifiers(
    english: None,
) -> None:
    served = countermeasures.overview()
    with i18n.use("es"):
        spanish = countermeasures.overview()
    keys = ("id", "scope", "domain", "ridge", "family", "resource_keys", "crew_time_minutes",
            "followup_checks", "followup_window_hours", "basis")
    for english_item, spanish_item in zip(
        served["countermeasures"], spanish["countermeasures"], strict=True
    ):
        assert {key: english_item[key] for key in keys} == {
            key: spanish_item[key] for key in keys
        }
        for text in _library_text(english_item):
            assert not _SPANISH.search(_QUOTED.sub("", text)), text
        assert english_item["action"] != spanish_item["action"]
    assert i18n.missing(
        countermeasures.LIBRARY_PATH,
        [_library_text(item) for item in spanish["countermeasures"]],
        # Constantes del módulo, no texto del fichero: su inglés va por el registro.
        skip=lambda text: text in {
            countermeasures.CONTRAINDICATIONS_PENDING,
            *(family.display for family in countermeasures.FAMILIES.values()),
        },
    ) == []
    assert served["note"].startswith("The whole library, grouped by RIDGE hazard")
    assert [item["key"] for item in served["families"]] == list(countermeasures.FAMILIES)
    assert served["families"][0]["display"] == "physical or mass"
    assert served["families"][-1]["display"] == "pharmacological: outside EMMA's scope"
    pending = next(
        item for item in served["countermeasures"] if item["contraindications_note"] is None
    )
    assert pending["contraindications_display"] == (
        "no contraindications written: pending medical review"
    )


def test_effects_are_recomposed_in_english_and_the_cached_sheet_stays_spanish(
    english: None,
) -> None:
    exercise = effects.library_entry("cv-exercise-session")
    assert exercise["benefit"]["text"].startswith("Expected benefit: on the ")
    assert "Beneficio" not in exercise["benefit"]["text"]
    assert exercise["adverse"][0]["text"].startswith("Exertion raises heart rate")
    assert exercise["co_adoption_basis"].startswith("The co-adoption note comes from")
    undeclared = effects.library_entry(SLEEP)
    assert undeclared["adverse_text"].startswith("Not declared: the library entry writes no")
    assert effects.overview()["interactions_note"] == (
        "No source read says how two countermeasures of the library interact."
    )
    assert effects.get("cv-exercise-session").benefit_text.startswith("Beneficio esperado")
    with i18n.use("es"):
        assert effects.library_entry(SLEEP)["adverse_text"] == effects.NOT_DECLARED
        assert effects.library_entry("cv-exercise-session")["benefit"]["text"].startswith(
            "Beneficio esperado"
        )


def test_co_adoption_note_in_english() -> None:
    decisions = [
        _decision(3, "adopted", T0),
        {**_decision(5, "adopted", T0), "countermeasure_id": "bh-circadian-lighting"},
    ]
    with i18n.use("en"):
        open_followups = followups(
            decisions, {"behavioral": RiskLevel.CONCERN}, [], T0 + dt.timedelta(hours=1)
        )
        notes = effects.co_adopted(SLEEP, open_followups)
        offered = effects.co_adopted("bh-repeat-pvt", open_followups)
    assert [note["countermeasure_id"] for note in notes] == ["bh-circadian-lighting"]
    assert notes[0]["text"] == (
        "Adopted together with «Consider adjusting the lighting to the mission cycle to "
        "re-anchor the circadian rhythm.»: no source read says how they interact."
    )
    assert offered[0]["text"].startswith("If adopted, it will go together with «Consider ")
    assert offered[0]["text"].endswith(", under follow-up: no source read says how they interact.")


# --------------------------------------------------------------------------- #
# Seguimiento, respuesta previa y coste de una comprobación
# --------------------------------------------------------------------------- #


def test_followup_evaluation_and_prior_response_in_english() -> None:
    decisions = [
        _decision(3, "adopted", T0),
        _decision(
            9, "closed", T0, adoption_index="3", reason="sueño recuperado tras dos noches",
            level_at_close="watch",
            closed_reference_time=(T0 + dt.timedelta(days=3)).isoformat(),
        ),
    ]
    now = T0 + dt.timedelta(days=10)
    spanish = followups(decisions, {"behavioral": RiskLevel.NOMINAL}, [], now)
    with i18n.use("en"):
        served = followups(decisions, {"behavioral": RiskLevel.NOMINAL}, [], now)
        block = prior_response.describe(SLEEP, served)
    [item], [before] = served, spanish
    # Lo firmado y lo que el código compara no cambia con el idioma.
    for key in ("adoption_index", "domain", "level_at_adoption", "state", "closed_reason",
                "level_at_close", "window_ends", "closed_at"):
        assert item[key] == before[key]
    assert item["evaluation"]["outcome"] == before["evaluation"]["outcome"] == "no_repeat"
    assert item["evaluation"]["text"].startswith("The follow-up measurement (")
    assert item["evaluation"]["text"].endswith(
        "has not been repeated since it was adopted: there is nothing to evaluate with."
    )
    assert item["evaluation_at_close"]["text"].endswith(
        "had not been repeated between adoption and closure: there is nothing to evaluate with."
    )
    assert block["text"] == (
        "It has been adopted once for this crew member; on 2026-12-01 08:00 UTC (CDR)."
    )
    assert block["caveat"].startswith("It is what happened afterwards, not proof")
    assert block["evaluation_basis"].startswith("The evaluation compares the level")
    last = block["last"]
    assert last["adopted_text"] == "Adopted on 2026-12-01 08:00 UTC (CDR)."
    # El motivo es lo que firmó una persona: se enseña tal cual.
    assert last["state_text"] == (
        "Closed on 2026-12-04 08:00 UTC (CDR): sueño recuperado tras dos noches"
    )
    assert last["evaluation_text"].startswith("At closure: The follow-up measurement (")
    assert last["checks_text"].startswith("It followed ")
    assert last["checks_text"].endswith("None was repeated after it was adopted.")


def test_followup_levels_are_compared_in_english_with_the_causality_note() -> None:
    decisions = [_decision(3, "adopted", T0)]
    item = countermeasures.get(SLEEP)
    key = item.followup_checks[0]
    repeated = VitalObservation(
        code=get(key), value=7.0, effective=T0 + dt.timedelta(days=1), subject="crew-01",
        source="prueba",
    )
    now = T0 + dt.timedelta(days=5)
    with i18n.use("en"):
        [improved] = followups(decisions, {"behavioral": RiskLevel.WATCH}, [repeated], now)
        [same] = followups(decisions, {"behavioral": RiskLevel.CONCERN}, [repeated], now)
        note = i18n.loc(CAUSALITY_NOTE)
    assert improved["evaluation"]["outcome"] == "improved"
    assert " domain went from " in improved["evaluation"]["text"]
    assert improved["evaluation"]["text"].endswith(f"since it was adopted. {note}")
    assert same["evaluation"]["outcome"] == "unchanged"
    assert " domain remains at " in same["evaluation"]["text"]
    assert note == (
        "That the change coincides in time does not show that the countermeasure is the cause."
    )
    assert "demuestra" not in improved["evaluation"]["text"]


def test_no_prior_adoptions_and_a_standing_no_in_english(english: None) -> None:
    block = prior_response.describe(SLEEP, [])
    assert block["state"] == prior_response.NONE and block["count"] == 0
    assert block["text"] == "No earlier adoptions of this countermeasure for this crew member."
    assert block["caveat"].startswith("It is what happened afterwards")
    note = decision_note(
        {**_decision(4, "declined", T0, reason="no hay tiempo esta semana")}
    )
    assert note["action"] == "declined" and note["ledger_index"] == 4
    assert note["text"] == (
        "It was decided not to adopt it on 2026-12-01 08:00 UTC (CDR): no hay tiempo esta semana"
    )
    assert note["meaning"].startswith("It is the record of a human decision, not an evaluation")


def test_check_cost_labels_in_english(english: None) -> None:
    nothing = check_cost.of(None)
    assert nothing["statement"] == "No structured countermeasure behind it: no declared cost."
    cost = check_cost.of(countermeasures.get(SLEEP))
    assert cost["action"]["key"] == "crew_time"
    assert cost["action"]["label"] == "Crew time of the action"
    assert cost["action"]["basis"].startswith("It is schedule time free of tasks before sleep")
    labels = {fact["key"]: fact["label"] for fact in cost["indicators"][0]["facts"]}
    assert labels["mode"] == "Measurement class"
    assert labels["crew_time"] == "Crew time to measure it"
    with i18n.use("es"):
        assert check_cost.of(None)["statement"] == check_cost.NO_COUNTERMEASURE
        assert check_cost.of(countermeasures.get(SLEEP))["action"]["label"] == (
            check_cost.ACTION_TIME
        )


# --------------------------------------------------------------------------- #
# Guías, glosario, contramedidas en investigación y lo que se comparte
# --------------------------------------------------------------------------- #


def test_guides_and_glossary_in_english_keep_quotes_ids_and_citations(english: None) -> None:
    served = guides.guides_payload()
    with i18n.use("es"):
        spanish = guides.guides_payload()
    assert served["scope"].startswith("How each measurement is taken, step by step.")
    assert [guide["id"] for guide in served["guides"]] == [g["id"] for g in spanish["guides"]]
    pressure = served["guides"][0]
    assert pressure["title"] == "Blood pressure with an upper-arm monitor"
    assert pressure["steps"][0]["text"] == "Empty your bladder before measuring."
    for mine, theirs in zip(served["guides"], spanish["guides"], strict=True):
        for kind in ("steps", "in_flight"):
            for step, original in zip(mine[kind], theirs[kind], strict=True):
                assert not _SPANISH.search(_QUOTED.sub("", step["text"])), step["text"]
                # La frase literal de la fuente y su ficha no se tocan.
                assert [item["quote"] for item in step["basis"]] == [
                    item["quote"] for item in original["basis"]
                ]
                assert [item["citation"] for item in step["basis"]] == [
                    item["citation"] for item in original["basis"]
                ]
        for line in mine["not_found"]:
            assert not _SPANISH.search(_QUOTED.sub("", line)), line
    raw = _raw(guides.GUIDES_PATH)
    authored = [
        [guide["title"], guide["not_found"],
         [step["text"] for step in (*guide["steps"], *guide["in_flight"])],
         [item["where"] for step in (*guide["steps"], *guide["in_flight"])
          for item in step["basis"] if "where" in item]]
        for guide in raw["guides"]
    ] + [item["text"] for item in raw["elsewhere"]]
    assert i18n.missing(guides.GUIDES_PATH, authored) == []

    glossary = guides.glossary_payload()
    with i18n.use("es"):
        spanish_glossary = guides.glossary_payload()
    assert glossary["scope"].startswith("The terms the console uses")
    by_id = {term["id"]: term for term in glossary["terms"]}
    assert list(by_id) == [term["id"] for term in spanish_glossary["terms"]]
    assert by_id["baseline"]["term"] == "Personal baseline"
    assert by_id["baseline"]["origin"] == "emma"
    assert by_id["baseline"]["origin_display"] == "EMMA's definition"
    assert "1.3 seconds to the Moon" in by_id["light-time"]["definition"]
    assert {term["origin_display"] for term in glossary["terms"]} == {
        "EMMA's definition", "definition taken from the source"
    }
    assert i18n.missing(
        guides.GLOSSARY_PATH,
        [[term["term"], term["definition"],
          [item["where"] for item in term.get("basis", [])]]
         for term in _raw(guides.GLOSSARY_PATH)["terms"]],
    ) == []
    # Lo que la consola enseña en castellano (y pasa el filtro de lenguaje) sigue igual.
    assert guides.GUIDES_SCOPE in guides.displayed_texts()


def test_research_countermeasures_in_english_keep_the_source_sentences(english: None) -> None:
    served = research_countermeasures.overview()
    with i18n.use("es"):
        spanish = research_countermeasures.overview()
    assert served["offered"] is False
    assert served["note"].startswith("Countermeasures under research: they are shown")
    assert "EMMA does not offer them" in served["note"]
    for mine, theirs in zip(served["entries"], spanish["entries"], strict=True):
        assert (mine["id"], mine["ridge"], mine["offered"]) == (
            theirs["id"], theirs["ridge"], False
        )
        assert [quote["quote"] for quote in mine["quotes"]] == [
            quote["quote"] for quote in theirs["quotes"]
        ]
        for field in research_countermeasures.AUTHORED:
            assert not _SPANISH.search(_QUOTED.sub("", mine[field])), mine[field]
            assert mine[field] != theirs[field]
    assert served["read_on"] == spanish["read_on"]
    assert list(served["sources"]) == list(spanish["sources"])
    raw = _raw(research_countermeasures.RESEARCH_PATH)
    authored = [
        [[item[field] for field in research_countermeasures.AUTHORED],
         [quote["where"] for quote in item["quotes"]]]
        for item in raw["entries"]
    ] + [raw["not_found"], raw["read_not_included"],
         [source["what"] for source in raw["sources"].values()]]
    assert i18n.missing(research_countermeasures.RESEARCH_PATH, authored) == []


def test_sharing_table_in_english_keeps_ids_hosts_and_pointers(english: None) -> None:
    settings = Settings(offline=True)
    served = sharing.payload(settings)
    with i18n.use("es"):
        spanish = sharing.payload(settings)
    assert served["note"].startswith("What leaves this computer, what Earth sees")
    assert served["internet"]["offline_text"] == (
        "Now: offline mode. Nothing goes out to the internet."
    )
    assert sharing.payload(Settings(offline=False))["internet"]["offline_text"].startswith(
        "Now: online."
    )
    assert [row["label"] for row in served["destinations"]] == [
        "Goes out to the internet", "Earth sees it, with the delay", "Stays on board",
        "Only in this console", "Not stored",
    ]
    for mine, theirs in zip(served["items"], spanish["items"], strict=True):
        for key in ("id", "destination", "enforcement"):
            assert mine[key] == theirs[key]
        for key in ("title", "text", "destination_text", "enforcement_text"):
            assert not _SPANISH.search(_QUOTED.sub("", mine[key])), mine[key]
            assert mine[key] != theirs[key]
        if mine["limit"] is not None:
            assert not _SPANISH.search(_QUOTED.sub("", mine["limit"])), mine["limit"]
    absent = [
        pointer for item in served["items"] for pointer in item["enforced_by"]
        if pointer.endswith(")")
    ]
    assert absent and all(
        pointer.endswith(" (the Earth console does not mount it)") for pointer in absent
    )
    for mine, theirs in zip(
        served["internet"]["purposes"], spanish["internet"]["purposes"], strict=True
    ):
        assert (mine["purpose"], mine["hosts"]) == (theirs["purpose"], theirs["hosts"])
        assert not _SPANISH.search(mine["what"] + mine["carries"])
    assert [route["path"] for route in served["ground_cut"]["routes"]] == [
        route["path"] for route in spanish["ground_cut"]["routes"]
    ]
    assert {route["direction_text"] for route in served["ground_cut"]["routes"]} == {
        "From on board to Earth", "From Earth to on board"
    }
    table = sharing.read()
    authored = [
        table["note"], [row["label"] for row in table["destinations"]],
        [row["label"] for row in table["enforcement"]],
        [[item["title"], item["text"], item["limit"] or ""] for item in table["items"]],
        [[row["what"], row["carries"]] for row in table["internet"]["purposes"]],
        table["ground_cut"]["note"],
        [row["label"] for row in table["ground_cut"]["directions"]],
    ]
    assert i18n.missing(sharing.SHARING_PATH, authored, skip=lambda text: not text) == []


def test_planner_ground_rule_is_served_in_english_without_touching_the_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(planner_ground, "run_node", lambda payload: {"people": []})
    monkeypatch.setattr(planner_ground, "_cache", {})
    until = dt.datetime(2026, 12, 1, 12, 0, tzinfo=dt.UTC)
    with i18n.use("en"):
        first = planner_ground.summarize([], until, 7)
    spanish = planner_ground.summarize([], until, 7)
    with i18n.use("en"):
        again = planner_ground.summarize([], until, 7)
    assert first["leisure_rule"] == again["leisure_rule"] == (
        "Leisure: calendar events whose title contains a word from a declared list "
        "(data/planner_leisure.json); it is not a measurement."
    )
    assert spanish["leisure_rule"].startswith("Ocio: eventos del calendario")
    assert first["cut"] == spanish["cut"] and first["people"] == []


# --------------------------------------------------------------------------- #
# Rutinas, crónica y gemelos
# --------------------------------------------------------------------------- #


def test_routine_sentences_keep_their_placeholders_in_english() -> None:
    for template in (
        routines.EVENT_PERIOD_NOTE, routines.EVENT_NOTE, routines.EVENT_OVER_NOTE,
        routines.DOSE_PERIOD_NOTE, routines.DOSE_NOTE, routines.DOSE_OVER_NOTE,
        routines.SUSPENDED_NOTE,
    ):
        with i18n.use("en"):
            english = i18n.loc(template)
        assert english != template
        assert sorted(re.findall(r"\{\w+\}", english)) == sorted(
            re.findall(r"\{\w+\}", template)
        )
        assert not _SPANISH.search(english)
    assert i18n.missing(
        routines.DATA,
        [routines.load()["default_basis"], routines.load()["during_event"]["basis"]],
    ) == []


def test_postflight_sentence_in_english_uses_the_decimal_point(english: None) -> None:
    item = {
        "key": "hemoglobin", "unit": "g/dL", "display_es": "hemoglobin",
        "preflight": {"mean": 14.25, "low": 13.5, "high": 15.0, "samples": 3},
    }
    one = timeline._postflight_day(item, 1, [
        {"value": 13.0, "delta_pct": -8.8, "within_preflight_range": False},
    ])
    assert one.startswith("hemoglobin: 13.0 g/dL") and " at R+1; " in one
    assert "8.8 % below the own preflight mean" in one
    assert one.endswith("outside their preflight range 13.5–15.0 g/dL")
    assert "," not in one.split("; ")[1]
    many = timeline._postflight_day(item, 2, [
        {"value": 13.0, "delta_pct": -8.8, "within_preflight_range": False},
        {"value": 14.0, "delta_pct": -1.8, "within_preflight_range": True},
    ])
    assert "2 samples at R+2, between 13.0 and 14.0 g/dL; 1 inside and 1 outside" in many
    with i18n.use("es"):
        spanish = timeline._postflight_day(item, 1, [
            {"value": 13.0, "delta_pct": -8.8, "within_preflight_range": False},
        ])
    assert "8,8 % por debajo de la media prevuelo propia" in spanish


def test_week_items_and_dependency_titles_in_english(english: None) -> None:
    items = timeline.week_items({
        "followups": [{"countermeasure": {"id": SLEEP}, "domain": "behavioral",
                       "state": "in_window", "window_ends": "2026-12-03T08:00:00+00:00"}],
        "predictions": [{"key": "heart-rate", "horizon_at": "2026-12-05T08:00:00+00:00"}],
    })
    assert [item["titulo"] for item in items] == [
        f"Follow-up of {SLEEP} (behavioral)", "Horizon of the projection of heart-rate",
    ]
    # Las claves de la forma de Polaris y su estado no se traducen: las lee su código.
    assert all(item["estado"] == "abierto" for item in items)
    assert items[0]["siguiente_accion"] == "repeating the follow-up measurement"
    affected = {item["id"]: item for item in timeline.depends_on("heart-rate")["affected"]}
    assert affected["linea-base:heart-rate"]["title"] == "Baseline of heart-rate"
    assert affected["linea-base:heart-rate"]["mode"] == "auto"
    assert any(title["title"].startswith("Follow-up of countermeasure ")
               for title in affected.values())


def test_twins_table_is_the_document_in_spanish_and_emmas_translation_in_english() -> None:
    status = {"subject": "crew-01", "summary": "", "domains": {}}
    spanish = twins.compose(status, None, None)
    with i18n.use("en"):
        served = twins.compose(status, None, None, until=T0)
    # En castellano, la tabla literal del documento (lo fija `tests/test_twins.py`).
    assert [q["question"] for q in spanish["questions"]] == [
        layer.question for layer in twins.LAYERS
    ]
    assert [q["key"] for q in served["questions"]] == [layer.key for layer in twins.LAYERS]
    assert [q["twin"] for q in served["questions"]] == [layer.twin for layer in twins.LAYERS]
    assert [q["state"] for q in served["questions"]] == [q["state"] for q in spanish["questions"]]
    assert served["questions"][0]["question"] == "what is changing in this person?"
    assert served["questions"][3]["question"] == (
        "what can be done now and what effect do we expect?"
    )
    for question in served["questions"]:
        for text in (question["question"], question["content"], question["answer"],
                     *question["sources"], *question["notes"]):
            assert not _SPANISH.search(text), text
    # La fuente dice que lo que se enseña es una traducción: el original está en castellano.
    assert "The original is in Spanish" in served["source"]
    assert served["note"].endswith("is still in transit.")
    assert served["questions"][3]["notes"][0].startswith(
        "EMMA does not predict the effect of a countermeasure"
    )
    assert served["questions"][4]["answer"] == (
        "What has been waiting for a person for days could not be read."
    )


# --------------------------------------------------------------------------- #
# Por la API: con la cabecera, inglés; sin ella, lo de antes
# --------------------------------------------------------------------------- #


def test_routes_answer_in_english_only_when_asked(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "spe-event", "days": 10})
    for route in (
        "/api/countermeasures", "/api/countermeasures/research", "/api/guides",
        "/api/glossary", "/api/sharing",
    ):
        before = client.get(route)
        english = client.get(route, headers=ENGLISH_HEADERS)
        after = client.get(route)
        assert before.status_code == english.status_code == 200, route
        assert before.json() == after.json(), route
        assert english.json() != before.json(), route

    library = client.get("/api/countermeasures", headers=ENGLISH_HEADERS).json()
    shelter = next(
        item for item in library["countermeasures"] if item["id"] == countermeasures.SHELTER_ID
    )
    assert shelter["action"] == (
        "Consider taking shelter immediately in the designated shielded area."
    )
    assert shelter["effects"]["benefit"]["text"].startswith("Expected benefit: on the ")
    assert client.get("/api/countermeasures").json()["countermeasures"][0]["action"] == (
        "Completar la sesión de ejercicio aeróbico y resistivo del protocolo."
    )

    spanish = client.get("/api/status").json()
    english = client.get("/api/status", headers=ENGLISH_HEADERS).json()
    assert spanish["recommendations"], "el escenario tiene que recomendar algo"
    assert [item["countermeasure"]["id"] for item in english["recommendations"]] == [
        item["countermeasure"]["id"] for item in spanish["recommendations"]
    ]
    assert [item["urgency"] for item in english["recommendations"]] == [
        item["urgency"] for item in spanish["recommendations"]
    ]
    for item in english["recommendations"]:
        assert item["action"].startswith("Consider "), item["action"]
        assert item["action"] == item["countermeasure"]["action"]
        assert item["prior_response"]["text"] == (
            "No earlier adoptions of this countermeasure for this crew member."
        )
        assert not _FORBIDDEN.search(item["action"])
    assert english["summary"].startswith(("Attention in the ", "No live consultation"))
    assert spanish["summary"] != english["summary"]

    routine = client.get("/api/timeline/routines", headers=ENGLISH_HEADERS).json()
    same = client.get("/api/timeline/routines").json()
    assert [item["key"] for item in routine["routines"]] == [
        item["key"] for item in same["routines"]
    ]
    assert [item["state"] for item in routine["routines"]] == [
        item["state"] for item in same["routines"]
    ]
    assert routine["streaks"]["label"] == (
        "Design cadence: consecutive periods with a good reading"
    )
    assert same["streaks"]["label"] == routines.STREAK_TEXT["label"]
    assert {item["basis"] for item in routine["routines"]} <= {
        "design parameter",
        "EMMA design parameter: no NASA procedure that sets this cadence during a solar event "
        "has been read",
    }
    assert routine["event_note"] is None or routine["event_note"].startswith(
        ("Onboard dose rate above its danger limit (", "Solar event ")
    )
    if routine["event_note"] and routine["event_note"].startswith("Onboard"):
        # La cifra, con punto decimal y con la unidad de `core/display.py`.
        figure = routine["event_note"].split("(")[1].split(",")[0]
        assert re.fullmatch(r"[\d.]+ \S+", figure), figure

    chronicle = client.get("/api/timeline/chronicle", headers=ENGLISH_HEADERS).json()
    before = client.get("/api/timeline/chronicle").json()
    assert [event["clave"] for event in chronicle["events"]] == [
        event["clave"] for event in before["events"]
    ]
    # Las claves que lee la interfaz (`tipo`, `fact`, `stage`) no se traducen.
    for key in ("tipo", "fact", "stage", "at"):
        assert [event[key] for event in chronicle["events"]] == [
            event[key] for event in before["events"]
        ]
    assert [stage["key"] for stage in chronicle["stages"]] == [
        key for key, _ in timeline.STAGES
    ]
    displays = {stage["key"]: stage["display"] for stage in chronicle["stages"]}
    assert displays["career"] == "career: declared prior missions"
    assert displays["followup"] == "follow-up"
    assert chronicle["as_of_basis"].startswith("last reading analysed")

    answer = client.get("/api/twins", headers=ENGLISH_HEADERS).json()
    assert answer["questions"][0]["question"] == "what is changing in this person?"
    assert client.get("/api/twins").json()["questions"][0]["question"] == (
        twins.LAYERS[0].question
    )
