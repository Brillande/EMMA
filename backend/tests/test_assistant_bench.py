"""La batería de frases naturales del asistente contra un backend y un Ollama de verdad.

Fuera de la suite por defecto (`live`): necesita un backend local con el modelo del asistente y
CARGA el escenario de la batería, que reemplaza su almacén. Se le da con `EMMA_BENCH_URL` (sin
ella, la prueba se salta); `EMMA_BENCH_MIN` es el acierto mínimo sobre las frases nuevas
(0,85 por defecto). La batería y su lectura están en `scripts/assistant_bench.py`.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


@pytest.mark.live
def test_the_assistant_understands_natural_phrasings() -> None:
    url = os.environ.get("EMMA_BENCH_URL")
    if not url:
        pytest.skip("sin EMMA_BENCH_URL: un backend local propio con el modelo del asistente")
    spec = importlib.util.spec_from_file_location("assistant_bench",
                                                  BACKEND / "scripts" / "assistant_bench.py")
    assert spec and spec.loader
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    battery = json.loads(bench.DEFAULT_FILE.read_text(encoding="utf-8"))
    bench._post(f"{url}/api/simulate?scenario={battery['scenario']}&replace=true", None)
    results = bench.run(url, battery["cases"], battery["subject"])
    summary = bench.report(results)
    assert summary["eval"]["ok"] / summary["eval"]["cases"] >= float(
        os.environ.get("EMMA_BENCH_MIN", "0.85"))
