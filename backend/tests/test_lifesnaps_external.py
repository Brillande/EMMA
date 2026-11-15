"""Las variantes del respaldo de familia sobre LifeSnaps: las dos metricas, juntas.

Marcadas `external`: necesitan `scripts/fetch_lifesnaps.py` (615 MB y una pasada larga, una vez).
La medida tarda del orden de un cuarto de hora con 6 procesos. Se apunta a otra copia del conjunto
con `EMMA_LIFESNAPS_DIR`.

**Esto no es un visto bueno a ninguna variante.** Son pruebas de regresion sobre un conjunto fijo
y determinista: dicen que algo cambio. Las cifras de la regla vigente **no** son buenas, y el
hallazgo 31 de `compliance/external-validation.md` lo dice. Si una cambia, se actualiza aqui y alli
en el mismo cambio, con las dos metricas delante (invariante 5). Nada se adopta: `evaluate_rolling`
sigue siendo la regla, por decision del usuario.
"""

from pathlib import Path
from typing import Any

import pytest

from app.analysis.baseline import BaselineEngine, Deviation
from app.validation.family_variants import RMSSD_LABEL, Variant, evaluate, run, spread
from app.validation.injection import hrv_collapse, inject, onset_after
from app.validation.lifesnaps import LOADED, LifeSnapsLoader, dataset_dir
from app.validation.mmash import MmashLoader

pytestmark = pytest.mark.external

MMASH = Path(__file__).resolve().parents[2] / "data" / "mmash" / "MMASH.zip"
FOLDER = dataset_dir() / "normalized"

READINGS = 1_322_974
DAYS = 4768
# Variante: lecturas marcadas, marcadas en reposo, juzgadas con base personal, episodios,
# dias-persona marcados.
HEALTHY = {
    "vigente": (46_721, 38_304, 1_258_065, 14_059, 3355),
    "A": (46_835, 38_418, 1_263_869, 14_082, 3355),
    "B": (46_815, 38_398, 1_263_696, 14_082, 3355),
    "C": (43_316, 35_311, 1_228_722, 13_508, 3347),
}
# Deterioro: (sujetos, lecturas perturbadas, acotadas); y por variante, inyectado y simulado:
# detectado, marcado, escalado, lecturas marcadas; simulado detectado, marcado, lecturas marcadas.
# Las columnas simuladas son de la misma persona y tramo sin deterioro: el acierto bruto solo
# dice algo comparado con ellas.
TACHYCARDIA = "taquicardia sostenida (+25 lpm)"
DRIFT = "taquicardia progresiva (+15 lpm/día)"
ACUTE = "episodio agudo (+40 lpm, 2 h)"
Arm = tuple[int, int, int, int, int, int, int]
SENSITIVITY: dict[str, tuple[tuple[int, int, int], dict[str, Arm]]] = {
    TACHYCARDIA: ((59, 38_365, 0), {
        "vigente": (59, 59, 54, 10_397, 57, 47, 1259),
        "A": (59, 59, 54, 10_407, 57, 47, 1259),
        "B": (59, 59, 54, 10_407, 57, 47, 1259),
        "C": (59, 59, 55, 10_200, 57, 47, 1181),
    }),
    DRIFT: ((59, 38_365, 0), {
        "vigente": (57, 59, 49, 13_554, 57, 47, 1259),
        "A": (57, 59, 49, 13_593, 57, 47, 1259),
        "B": (57, 59, 49, 13_593, 57, 47, 1259),
        "C": (57, 59, 50, 13_358, 57, 47, 1181),
    }),
    ACUTE: ((49, 1145, 0), {
        "vigente": (47, 49, 30, 736, 13, 38, 39),
        "A": (47, 49, 30, 736, 13, 38, 39),
        "B": (47, 49, 30, 736, 13, 38, 39),
        "C": (47, 49, 32, 725, 13, 38, 39),
    }),
    RMSSD_LABEL: ((35, 8029, 0), {
        "vigente": (32, 34, 23, 1836, 21, 27, 208),
        "A": (32, 34, 23, 1836, 21, 27, 208),
        "B": (32, 34, 23, 1836, 21, 27, 208),
        "C": (32, 34, 22, 1798, 20, 27, 207),
    }),
}
# Variante: intervalo de la falsa alarma, y diferencia con la vigente (puntos, remuestreando
# personas), mediana por persona.
SPREAD = {
    "vigente": ([3.33, 3.76], [0.0, 0.0], 3.44),
    "A": ([3.34, 3.77], [0.004, 0.014], 3.44),
    "B": ([3.34, 3.77], [0.004, 0.011], 3.44),
    "C": ([3.09, 3.49], [-0.303, -0.217], 3.13),
}
# Lecturas de trabajo (de 7575) con base personal: lo unico que A y B pueden mover.
WORK_PERSONAL = {"vigente": 1764, "A": 7440, "B": 7387, "C": 7253}


@pytest.fixture(scope="module")
def loader() -> LifeSnapsLoader:
    if not any(FOLDER.glob("*.json.gz")):
        pytest.skip(f"LifeSnaps no normalizado en {FOLDER}")
    return LifeSnapsLoader(FOLDER)


@pytest.fixture(scope="module")
def measured(loader: LifeSnapsLoader) -> dict[str, Any]:
    return run(loader.folder, workers=6)


def _verdicts(items: list[Deviation]) -> list[tuple[Any, ...]]:
    return sorted((d.key, d.effective, d.severity, d.used_population_range) for d in items)


def test_dataset_has_its_people_and_only_the_loaded_indicators(loader: LifeSnapsLoader) -> None:
    assert len(loader.subjects()) == 71
    data = loader.load(loader.subjects()[0])
    assert {o.key for o in data.observations} <= set(LOADED)


def test_current_variant_is_the_engine_on_a_real_person(loader: LifeSnapsLoader) -> None:
    observations = loader.load(loader.subjects()[0]).observations
    assert _verdicts(evaluate(observations, Variant.CURRENT)) == _verdicts(
        BaselineEngine().evaluate_rolling(observations)
    )


def test_variants_reproduce_the_mmash_table_of_finding_29() -> None:
    """La reimplementacion da lo que dio la rama: lecturas marcadas y colapso de HRV detectado."""
    if not MMASH.exists():
        pytest.skip(f"MMASH no descargado en {MMASH}")
    mmash = MmashLoader(MMASH)
    subjects = [series for name in mmash.subjects() if (series := mmash.load(name).observations)]
    expected = {
        Variant.CURRENT: (34, 3), Variant.FAMILY: (43, 4),
        Variant.COVERED: (30, 2), Variant.ALL_COVERED: (22, 0),
    }
    for variant, (flagged, detected) in expected.items():
        marks = sum(
            item.is_concerning for series in subjects for item in evaluate(series, variant)
        )
        found = 0
        for series in subjects:
            injected = inject(series, hrv_collapse(onset_after(series)))
            touched = {(o.key, o.value) for o in injected.affected}
            found += any(
                item.is_concerning and (item.key, item.value) in touched
                for item in evaluate(injected.observations, variant)
            )
        assert (marks, found) == (flagged, detected), variant


def test_false_alarm_of_every_variant(measured: dict[str, Any]) -> None:
    assert measured["subjects"] == 71
    for variant, (flagged, at_rest, personal, episodes, days) in HEALTHY.items():
        arm = measured["healthy"][variant]
        assert (arm["readings"], arm["days"]) == (READINGS, DAYS)
        assert (arm["flagged"], arm["flagged_at_rest"], arm["personal"]) == (
            flagged, at_rest, personal,
        )
        assert (arm["episodes"], arm["days_flagged"]) == (episodes, days)


def test_sensitivity_of_every_variant(measured: dict[str, Any]) -> None:
    """Va junto a la anterior: una sin la otra no dice nada (invariante 5)."""
    for label, ((subjects, perturbed, clamped), by_variant) in SENSITIVITY.items():
        for variant, expected in by_variant.items():
            arm = measured["sensitivity"][label][variant]
            assert (arm["subjects"], arm["perturbed"], arm["clamped"]) == (
                subjects, perturbed, clamped,
            )
            assert (
                arm["detected"], arm["flagged"], arm["escalated"], arm["hits"],
                arm["sham_detected"], arm["sham_flagged"], arm["sham_hits"],
            ) == expected


def test_sham_arm_is_what_keeps_detection_honest(measured: dict[str, Any]) -> None:
    """Sin deterioro, casi todos tienen ya «alguna lectura marcada» en esos tres dias."""
    arm = measured["sensitivity"][TACHYCARDIA]["vigente"]
    assert arm["sham_detected"] / arm["subjects"] > 0.9
    assert arm["sham_flagged"] / arm["subjects"] > 0.75


def test_spread_of_the_false_alarm(measured: dict[str, Any]) -> None:
    computed = spread(measured)
    for variant, (interval, difference, median) in SPREAD.items():
        assert computed[variant]["interval"] == interval
        assert computed[variant]["difference"] == difference
        assert computed[variant]["median_person"] == median


def test_work_is_all_the_family_can_move(measured: dict[str, Any]) -> None:
    for variant, personal in WORK_PERSONAL.items():
        context = measured["healthy"][variant]["by_context"]
        assert context["work:lecturas"] == 7575
        assert context["work:base personal"] == personal
        assert measured["healthy"][variant]["subjects_with_reading"] == 70
