"""El banco de los verificadores locales (`score_local` de Polaris). La suite simula a Ollama; la
prueba `live` mide los modelos instalados contra su línea base."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app import committee_bench, polaris

BASELINE = Path(__file__).parent / "data" / "evals" / "baseline.json"


def test_the_bank_covers_every_answer_and_keeps_a_held_out_part() -> None:
    bank = committee_bench.cases()
    assert {case["etiqueta"] for case in bank} == set(committee_bench.OPTIONS)
    assert any(case["held_out"] for case in bank)
    assert len(committee_bench.cases(include_held_out=False)) < len(bank)


def _fake(answers: dict[str, str | None]) -> Any:
    def puntuar(text: str, instruction: str, options: dict[str, str], modelo: str) -> Any:
        case = next(c for c in committee_bench.cases() if committee_bench._text(c) == text)
        chosen = answers.get(case["id"], case["etiqueta"])
        return chosen, ({chosen: 0.9} if chosen else {}), 1.0
    return puntuar


def test_a_fault_passed_as_correct_is_what_the_committee_cares_about(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = polaris.load("score_local")
    monkeypatch.setattr(tool, "comprobar_memoria", lambda model, forzar=False: None)
    monkeypatch.setattr(tool, "puntuar", _fake({"inv-1": "A", "dx-1": "B", "tx-1": None}))
    result = committee_bench.run("simulado")
    # dx-1 → B sigue bloqueando (es un fallo); inv-1 → A y tx-1 sin respuesta pasarían.
    assert result["passed_with_fault"] == ["inv-1", "tx-1"]
    assert result["clean_kept"] == 1.0 and result["fault_detection"] < 1.0


def test_a_model_that_does_not_fit_is_not_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = polaris.load("score_local")

    def refuse(model: str, forzar: bool = False) -> None:
        raise SystemExit("NO se lanza: no deja margen")

    monkeypatch.setattr(tool, "comprobar_memoria", refuse)
    result = committee_bench.run("enorme")
    assert result["ran"] is False and "margen" in result["reason"]


def test_the_copy_is_restored(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = polaris.load("score_local")
    sentinel_url, sentinel_free = "http://centinela/api/generate", lambda: 1.0
    monkeypatch.setattr(tool, "URL", sentinel_url)
    monkeypatch.setattr(tool, "_memoria_libre_gb", sentinel_free)
    monkeypatch.setattr(tool, "comprobar_memoria", lambda model, forzar=False: None)
    monkeypatch.setattr(tool, "puntuar", _fake({}))
    committee_bench.run("simulado")
    restored = (tool.URL, tool._memoria_libre_gb)
    assert restored[0] is sentinel_url and restored[1] is sentinel_free


@pytest.mark.live
def test_the_installed_verifiers_hold_their_baseline() -> None:
    baseline = {k: v for k, v in json.loads(BASELINE.read_text(encoding="utf-8")).items()
                if not k.startswith("_")}
    for model, expected in baseline.items():
        result = committee_bench.run(model)
        if not result["ran"]:
            pytest.skip(f"{model}: {result['reason']}")
        print(model, {k: result[k] for k in ("accuracy", "fault_detection", "clean_kept")})
        assert result["fault_detection"] >= expected["fault_detection"], model
        assert result["clean_kept"] >= expected["clean_kept"], model
