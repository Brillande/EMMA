"""El linter de lenguaje en inglés: cada caso bloqueado tiene un gemelo que no bloquea.

Por qué existe: con la salida en inglés (decisión del usuario, 2026-11-15) un filtro de patrones
castellanos lo dejaba pasar todo sin decir nada. El método es el de `test_text_guard.py`: un
linter se juzga tanto por lo que caza como por lo que deja pasar, y aquí además por una tercera
cosa, que el castellano no se haya movido.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from app import text_guard
from app.core import ground_notes, i18n
from app.text_guard import advisories, check

DATA = Path(__file__).parent / "data"
CASES: list[dict[str, Any]] = json.loads(
    (DATA / "text_guard_evals_en.json").read_text(encoding="utf-8")
)["casos"]
SPANISH: list[dict[str, Any]] = json.loads(
    (DATA / "text_guard_evals.json").read_text(encoding="utf-8")
)["casos"]
GROUPS = ("dosing", "diagnosis", "certainty", "order", "overclaim", "deliberation")


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_the_english_linter_blocks_exactly_the_expected_categories(case: dict[str, Any]) -> None:
    categories = {finding.category for finding in check(case["texto"], "en")}
    assert categories == set(case["bloquea"]), case["texto"]


def test_every_blocked_case_names_a_twin_that_passes() -> None:
    by_id = {case["id"]: case for case in CASES}
    assert len(by_id) == len(CASES)
    for case in CASES:
        if case["bloquea"]:
            twin = by_id[case["gemelo"]]
            assert twin["bloquea"] == [], (case["id"], twin["id"])


def test_every_group_has_enough_blocked_and_allowed_cases() -> None:
    blocked = Counter(case["grupo"] for case in CASES if case["bloquea"])
    allowed = Counter(case["grupo"] for case in CASES if not case["bloquea"])
    assert set(blocked) == set(allowed) == set(GROUPS)
    assert all(blocked[group] >= 8 and allowed[group] >= 8 for group in GROUPS), (blocked, allowed)


def test_every_kind_of_spanish_case_has_its_english_translation() -> None:
    """Los casos castellanos que no tienen gemelo inglés son los de pronombres pegados: el inglés
    no los tiene, y está dicho en el módulo."""
    spanish = {case["id"] for case in SPANISH}
    translated = {case["de"] for case in CASES if "de" in case}
    assert translated <= spanish
    assert all("pronombre" in name for name in spanish - translated), spanish - translated


# --- Qué idioma se aplica --------------------------------------------------------------------

ENGLISH_ORDER = "The crew member must be treated today."


def test_the_suite_default_is_spanish_and_spanish_does_not_read_english() -> None:
    assert i18n.current() == "es"
    assert check(ENGLISH_ORDER) == []
    assert check(ENGLISH_ORDER, "es") == []


def test_the_language_of_the_request_picks_the_patterns() -> None:
    with i18n.use("en"):
        assert [finding.match for finding in check(ENGLISH_ORDER)] == ["must be treated"]
        # Pedido a mano, el castellano sigue siendo el castellano aunque la petición sea inglesa.
        assert check(ENGLISH_ORDER, "es") == []
    assert [finding.category for finding in check(ENGLISH_ORDER, "en")] == ["order"]


def test_the_english_fixture_reaches_the_filter(english: None) -> None:
    assert {finding.category for finding in check("Administer 10 mg tonight.")} == {"dosing"}


# --- El castellano no se ha movido -----------------------------------------------------------


@pytest.mark.parametrize("case", SPANISH, ids=[case["id"] for case in SPANISH])
def test_spanish_results_are_the_same_with_and_without_the_parameter(case: dict[str, Any]) -> None:
    implicit = check(case["texto"])
    assert check(case["texto"], "es") == implicit
    assert {finding.category for finding in implicit} == set(case["bloquea"])
    assert advisories(case["texto"], "es") == advisories(case["texto"])


@pytest.mark.parametrize("case", SPANISH, ids=[case["id"] for case in SPANISH])
def test_a_spanish_text_is_blocked_the_same_under_an_english_console(case: dict[str, Any]) -> None:
    """La barrera no se salta cambiando de idioma: un modelo, una nota de Tierra o un fichero de
    datos pueden venir en castellano con la consola en inglés."""
    spanish = check(case["texto"], "es")
    english = check(case["texto"], "en")
    assert english == spanish, case["texto"]


def test_spanish_findings_keep_their_order_and_positions() -> None:
    text = "Nunca se observó. Administre 10 mg. Conviene repetir, ¿vale?"
    assert [(f.category, f.match, f.start) for f in check(text, "es")] == [
        ("dosing", "10 mg", 29),
        ("dosing", "administre", 18),
        ("overclaim", "nunca", 0),
        ("order", "conviene", 36),
    ]


# --- Lo propio del inglés --------------------------------------------------------------------


def test_one_span_caught_by_both_languages_is_reported_once() -> None:
    found = check("Administer 10 mg tonight.", "en")
    assert [(finding.category, finding.match) for finding in found] == [
        ("dosing", "10 mg"), ("dosing", "administer"),
    ]


def test_english_findings_come_first_and_spanish_ones_are_kept() -> None:
    found = check("This is definitely noise. Conviene repetir la medida.", "en")
    assert [(finding.category, finding.match) for finding in found] == [
        ("certainty", "definitely"), ("order", "conviene"),
    ]


def test_the_english_question_is_opened_by_an_auxiliary() -> None:
    plain = text_guard.normalize("Should we, in your opinion, repeat it? It is fine.")
    assert text_guard.outside_opened_questions(plain, "en").strip() == "it is fine."
    assert text_guard.outside_opened_questions(plain, "es") == plain
    assert len(text_guard.stated(plain, "en")) == len(plain)
    # Sin auxiliar que la abra, solo es pregunta la última cláusula.
    tagged = text_guard.normalize("It is confirmed that it bleeds, right?")
    assert text_guard.outside_opened_questions(tagged, "en") == tagged
    assert text_guard.stated(tagged, "en").strip() == "it is confirmed that it bleeds,"


def test_a_spanish_question_is_still_a_question_under_an_english_console() -> None:
    assert check("¿Conviene, en su opinión, repetir la medida?", "en") == []
    with i18n.use("en"):
        assert ground_notes.mandate_findings("¿Debe descansar?") == []
        assert ground_notes.mandate_findings("Debe descansar, ¿vale?") == ["debe"]


def test_what_blocks_in_english_is_not_repeated_as_a_warning() -> None:
    text = "The reading never changes. No tiene signos de telemetría alterada."
    blocked = {finding.match for finding in check(text, "en")}
    warned = {finding.match for finding in advisories(text, "en")}
    assert "never" in blocked
    assert "no tiene" in warned
    assert not blocked & warned


def test_emma_actions_have_their_english_twins() -> None:
    assert len(text_guard.EMMA_ACTIONS_EN) >= len(text_guard.EMMA_ACTIONS)
    for text in ("Lumbar puncture.", "Drainage of the collection.", "Drain the abscess."):
        assert {finding.category for finding in check(text, "en")} == {"order"}, text
