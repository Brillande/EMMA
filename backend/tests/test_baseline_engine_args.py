"""Lógica 2: el motor de línea base no acepta un umbral que no aplica.

`BaselineEngine(min_samples=...)` se aceptaba y se guardaba, pero `Baseline.established` mira
`MIN_SAMPLES`: quien pasara 30 creía tener una base establecida con 30 lecturas y el motor seguía
exigiendo 100. Un parámetro que no hace nada es peor que no tenerlo.
"""

import pytest

from app.analysis.baseline import BaselineEngine


def test_the_engine_rejects_a_min_samples_it_would_ignore() -> None:
    with pytest.raises(TypeError):
        BaselineEngine(min_samples=30)  # type: ignore[call-arg]
