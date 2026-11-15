"""Linter de lenguaje: cada caso bloqueado tiene un gemelo que no bloquea.

El método es de Polaris (`evals/honestidad.json`): un linter se juzga tanto por lo que caza como
por lo que deja pasar. Uno que bloquee los gemelos acabará rechazando borradores correctos, y de
un filtro que falla así se aprende a desconfiar.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.core import ground_notes
from app.text_guard import advisories, check

EVALS = Path(__file__).parent / "data" / "text_guard_evals.json"
CASES: list[dict[str, Any]] = json.loads(EVALS.read_text(encoding="utf-8"))["casos"]


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_the_linter_blocks_exactly_the_expected_categories(case: dict[str, Any]) -> None:
    categories = {finding.category for finding in check(case["texto"])}
    assert categories == set(case["bloquea"]), case["texto"]


def test_every_blocked_case_names_a_twin_that_passes() -> None:
    by_id = {case["id"]: case for case in CASES}
    for case in CASES:
        if case["bloquea"]:
            twin = by_id[case["gemelo"]]
            assert twin["bloquea"] == [], (case["id"], twin["id"])


# Decisión del usuario (2026-09-29): las listas completas de Polaris se comprueban todas, pero lo
# que no es la parte clínica que EMMA ya bloqueaba solo avisa a quien firma.
FALSE_BLOCKS = "No tiene signos de telemetría alterada y si persiste se repite la medida."


def test_polaris_full_lists_warn_but_do_not_block_generic_phrases() -> None:
    assert check(FALSE_BLOCKS) == []
    assert {finding.match for finding in advisories(FALSE_BLOCKS)} >= {"no tiene", "y si"}


def test_what_blocks_is_not_repeated_as_a_warning() -> None:
    text = "Nunca se observó. Administre 10 mg."
    blocked = {finding.match for finding in check(text)}
    assert {"nunca", "10 mg"} <= blocked
    assert not blocked & {finding.match for finding in advisories(text)}


def test_a_tag_question_counts_for_advisories_too() -> None:
    found = {finding.match for finding in advisories("Hay que decidir si repetirla, ¿vale?")}
    assert "hay que decidir" in found


def test_the_notes_and_the_filter_share_one_rule_for_what_a_question_is() -> None:
    assert ground_notes.mandate_findings("Debe descansar, ¿vale?") == ["debe"]
    assert [finding.match for finding in check("Conviene descansar, ¿vale?")] == ["conviene"]
    assert not hasattr(ground_notes, "_OPENED_QUESTION")
    assert not hasattr(ground_notes, "_BARE_QUESTION")


def test_the_pauta_imperative_stays_with_the_notes() -> None:
    """Decisión de §5.39.21: el filtro general no lo bloquea, ni con coletilla ni sin ella."""
    assert check("Repita la medida esta tarde, ¿vale?") == []
    assert ground_notes.mandate_findings("Repita la medida esta tarde, ¿vale?") == ["repita"]
