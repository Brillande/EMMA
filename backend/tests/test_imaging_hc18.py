"""Validación externa del motor de medida ecográfica contra HC18 (CC BY 4.0).

Marcadas `external`: necesitan el dataset descargado (`scripts/fetch_hc18.py`).

QUÉ DEMUESTRA Y QUÉ NO
----------------------
Que la conversión de píxeles a milímetros con la calibración declarada y la distancia del
motor (`imaging.measure.distance_mm`) no introducen error: sobre 999 imágenes reales, el
perímetro reconstruido a partir de dos diámetros casa con el de referencia de los autores.

No demuestra la precisión de un operador —los puntos salen del contorno experto— ni nada
sobre anatomía de vuelo. Y el acuerdo es tan alto porque los autores calcularon la
referencia a partir de la misma elipse que anotaron: por eso hay un control negativo que
prueba que la validación **sí falla** si la escala se desvía un 1 %.

LOS UMBRALES SE FIJARON DESPUÉS DE MEDIR (2026-09-24), no antes. Detectan empeoramientos.
"""

import pytest

from app.validation.hc18 import DATASET_DIR, evaluate, load_cases

pytestmark = pytest.mark.external

# Medido el 2026-09-24 sobre los 999 casos del conjunto de entrenamiento.
MEASURED_MEDIAN_PCT = 0.003
MEASURED_MAX_PCT = 0.024
# Holgura para cambios legítimos del motor; un error de escala real es de otro orden.
TOLERANCE_PCT = 0.02


@pytest.fixture(scope="module")
def available() -> None:
    if not (DATASET_DIR / "training_set.zip").exists():
        pytest.skip("HC18 no descargado: ejecutar scripts/fetch_hc18.py")


def test_calibrated_distance_reproduces_the_reference(available: None) -> None:
    report = evaluate(load_cases())
    assert report.cases == 999
    assert report.median_abs_error_pct <= MEASURED_MEDIAN_PCT + TOLERANCE_PCT
    assert report.max_abs_error_pct <= MEASURED_MAX_PCT + TOLERANCE_PCT, report.worst


def test_a_one_percent_scale_error_is_caught(available: None) -> None:
    """Control negativo: una validación que no puede fallar no valida nada."""
    report = evaluate(load_cases(), scale_error=0.01)
    assert report.median_abs_error_pct > MEASURED_MAX_PCT + TOLERANCE_PCT
    assert report.median_abs_error_pct == pytest.approx(1.0, abs=0.05)
