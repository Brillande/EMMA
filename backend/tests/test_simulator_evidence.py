"""El simulador declara el respaldo de TODAS sus derivas, y declararlo no cambia nada.

Varias derivas estaban escritas a mano en los modelos y en los escenarios, sin pasar por
`LITERATURE`. Al declararlas: los valores no cambian (la serie es idéntica, escenario a
escenario y semilla a semilla), lo que no tenía fuente queda como «diseño» y lo dice, y el
estado lo enseña sin que el veredicto del motor se entere (invariante 5).

Y la clase es una afirmación sobre lo leído (decimosexta ronda, E18): dos derivas del modelo
nominal que lo leído contradice cambiaron de clase sin cambiar de valor, la huella de la serie y
el veredicto de abajo siguen siendo los de antes, y una clase sin lo leído detrás no se declara.

El 2026-10-31 (decimonovena ronda, U22) el usuario decidió: esas dos derivas pasan a 0, y cuatro
de diseño que lo leído ya juzgaba toman su clase con su valor. La huella de la serie cambia solo
en la FC y en el cortisol (`SERIES_PINNED`, con las huellas por indicador de lo que no se movió),
y el veredicto por escenario sigue siendo el de antes (`VERDICT_BEFORE`): lo que se midió al
corregir está en `compliance/hmi-state-of-the-art.md` §5.39.22.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.api.routes import new_store, reset_store
from app.core import versioning
from app.evidence import flight_direction, registry
from app.ingest import simulator
from app.ingest.simulator import (
    EVIDENCE_CLASSES,
    LITERATURE,
    NO_SOURCE,
    CrewMember,
    DriftParameter,
    PhysiologicalSimulator,
    Scenario,
    cited_refs,
    evidence_by_class,
    evidence_report,
    literature_problems,
)

# Huella de la serie de cada escenario y semilla (40 días, 24 muestras/día, todos los
# indicadores), con `_digests` de abajo. Si una cambia, ha cambiado un valor del modelo, no su
# etiqueta. Las dieciocho primeras se calcularon sobre el árbol ANTERIOR a declarar las derivas
# (commit 45d43f4) y aguantaron hasta el 2026-10-31, cuando la FC en reposo y el cortisol salival
# del modelo nominal pasaron a 0 por decisión del usuario (U22): las de ahora son las de ese
# árbol, calculadas al corregir. Lo que no se movió lo guarda `SERIES_BEFORE_WITHOUT_THE_TWO`.
SERIES_PINNED = {
    ("arrhythmia", 20261114): "25245854f1889f67",
    ("arrhythmia", 7): "0bdeff2e1a5c2073",
    ("cardiovascular-deconditioning", 20261114): "e9be1d76905cf3d3",
    ("cardiovascular-deconditioning", 7): "75ac5a8286b3182c",
    ("co2-fatigue", 20261114): "4ef77b9f448ff285",
    ("co2-fatigue", 7): "a8ce73211e816c2d",
    ("dehydration", 20261114): "260af2c7f931d45d",
    ("dehydration", 7): "c5292906cb5a02dd",
    ("immune-reactivation", 20261114): "10fc3ad8dcf3ca4c",
    ("immune-reactivation", 7): "c2af0fe912c13c13",
    ("menu-fatigue", 20261114): "9a97d941bd5275da",
    ("menu-fatigue", 7): "6ca2af4642e1a752",
    ("nominal", 20261114): "576588177d6397ad",
    ("nominal", 7): "4102c738c0583854",
    ("progressive-insomnia", 20261114): "9eb8dc896dc02f6f",
    ("progressive-insomnia", 7): "20baa2b773a15616",
    ("spe-event", 20261114): "6ced3959d7853484",
    ("spe-event", 7): "f1a2376b22113095",
    # Añadido en la decimoséptima ronda (§5.37.3), calculado al crearlo: no hay árbol anterior
    # en el que existiera. Las dieciocho de arriba no se movieron al añadirlo.
    ("transient-sleep-loss", 20261114): "b152dbf46f781a6a",
    ("transient-sleep-loss", 7): "d0d5e42a8b8a3137",
    # Añadido el 2026-11-04, calculado al crearlo. Declarar la subida y el decaimiento del pico
    # (`spe_dose_rise_days`, `spe_dose_decay_days`) no movió las huellas de `spe-event`.
    ("spe-event-recovery", 20261114): "71bb5d677235a749",
    ("spe-event-recovery", 7): "711a7bb3825c477e",
}

# Los dos indicadores del modelo nominal cuya deriva pasó a 0 el 2026-10-31.
CORRECTED_TO_ZERO = frozenset({"heart-rate", "cortisol-salivary"})

# Huella de todo lo demás —la serie de cada indicador salvo esos dos, combinadas— calculada sobre
# el árbol anterior a la corrección (commit 6372fad). Corregir dos derivas no puede mover un
# decimal de ningún otro indicador; si una de estas cambia, se movió algo más que la FC y el
# cortisol.
SERIES_BEFORE_WITHOUT_THE_TWO = {
    ("arrhythmia", 20261114): "dee6f3de8f50af19",
    ("arrhythmia", 7): "5fd38913090b6222",
    ("cardiovascular-deconditioning", 20261114): "fa1d73d7f4b90196",
    ("cardiovascular-deconditioning", 7): "2f148e2bd6e7d405",
    ("co2-fatigue", 20261114): "ae0a59f9368dd24f",
    ("co2-fatigue", 7): "fccc2ced99a1497d",
    ("dehydration", 20261114): "9ddaec85b6f6cacb",
    ("dehydration", 7): "cf7676954754f9f5",
    ("immune-reactivation", 20261114): "4277a3ab287ec5e6",
    ("immune-reactivation", 7): "1bc4e984ca819be7",
    ("menu-fatigue", 20261114): "2bfa69d28c1adf53",
    ("menu-fatigue", 7): "f25859f3f0628dec",
    ("nominal", 20261114): "c061b3b097efd54e",
    ("nominal", 7): "be9b7d906036bb2e",
    ("progressive-insomnia", 20261114): "ad11b71714bb37d0",
    ("progressive-insomnia", 7): "53c8e744dae98b8f",
    ("spe-event", 20261114): "389f959515b8e0e0",
    ("spe-event", 7): "5c84a9da00d18ffd",
    ("transient-sleep-loss", 20261114): "755f7ab5717475b3",
    ("transient-sleep-loss", 7): "f30f3f45ebcc334b",
    # El escenario no existía antes de la corrección: la de su árbol, calculada al crearlo.
    ("spe-event-recovery", 20261114): "d71a0e7c7ae7e901",
    ("spe-event-recovery", 7): "7c23ad5dac9863f9",
}

# Nivel global y alertas (dominio, nivel) de `/api/status` tras `POST /api/simulate` con 40
# días, medidos sobre ese mismo árbol anterior.
VERDICT_BEFORE: dict[str, tuple[str, list[list[str]]]] = {
    "nominal": ("nominal", []),
    "spe-event": ("concern", [["immune", "watch"], ["radiation", "concern"]]),
    "progressive-insomnia": ("concern", [["behavioral", "concern"]]),
    "arrhythmia": ("concern", [["cardiovascular", "concern"]]),
    "cardiovascular-deconditioning": ("watch", [["cardiovascular", "watch"]]),
    "immune-reactivation": ("watch", [["immune", "watch"]]),
    "co2-fatigue": ("watch", [["immune", "watch"]]),
    "dehydration": ("watch", [["genitourinary", "watch"]]),
    "menu-fatigue": ("nominal", []),
    # Decimoséptima ronda (§5.37.3): el episodio ya cesó y el dominio baja de precaución a
    # vigilancia; lo que queda lo sostienen las tendencias de 21 días, que aún lo contienen.
    "transient-sleep-loss": ("watch", [["behavioral", "watch"]]),
    # 2026-11-04: el pico de dosis empieza 12 días antes del final y a los 40 días ya volvió a
    # su fondo: nominal y sin alertas. El episodio está en la crónica, no en el presente.
    "spe-event-recovery": ("nominal", []),
}


def _digests(scenario: Scenario, seed: int) -> tuple[str, str]:
    """Huella de la serie entera y, aparte, de la serie sin los dos indicadores corregidos a 0
    (la huella de cada indicador, combinadas por clave)."""
    whole = hashlib.sha256()
    rest: dict[str, Any] = {}
    sim = PhysiologicalSimulator(scenario=scenario, seed=seed)
    for obs in sim.generate(days=40, samples_per_day=24):
        line = f"{obs.key}|{obs.effective.isoformat()}|{obs.value!r}|{obs.context}\n".encode()
        whole.update(line)
        if obs.key not in CORRECTED_TO_ZERO:
            rest.setdefault(obs.key, hashlib.sha256()).update(line)
    combined = "".join(f"{key}:{digest.hexdigest()[:16]}\n" for key, digest in sorted(rest.items()))
    return whole.hexdigest()[:16], hashlib.sha256(combined.encode()).hexdigest()[:16]


def test_the_pinned_series_cover_every_scenario() -> None:
    assert {name for name, _ in SERIES_PINNED} == {str(item) for item in Scenario}
    assert set(SERIES_BEFORE_WITHOUT_THE_TWO) == set(SERIES_PINNED)
    assert set(VERDICT_BEFORE) == {str(item) for item in Scenario}


@pytest.mark.parametrize(("scenario", "seed"), sorted(SERIES_PINNED))
def test_correcting_the_two_drifts_moved_only_heart_rate_and_cortisol(
    scenario: str, seed: int
) -> None:
    whole, without_the_two = _digests(Scenario(scenario), seed)
    assert whole == SERIES_PINNED[(scenario, seed)], "ha cambiado un valor del modelo"
    assert without_the_two == SERIES_BEFORE_WITHOUT_THE_TWO[(scenario, seed)], (
        "algo distinto de la FC y del cortisol se movió respecto al árbol anterior (6372fad)"
    )


# --------------------------------------------------------------------------- #
# Ninguna deriva escrita a mano
# --------------------------------------------------------------------------- #


def _nonzero_numbers(node: ast.AST) -> list[float]:
    return [
        item.value
        for item in ast.walk(node)
        if isinstance(item, ast.Constant)
        and isinstance(item.value, (int, float))
        and not isinstance(item.value, bool)
        and item.value != 0
    ]


def handwritten_drifts(source: str) -> list[tuple[int, list[float]]]:
    """Derivas semanales con un número escrito: como `weekly_drift=` o como tercer argumento
    posicional de `IndicatorModel`. El cero (no deriva) no cuenta."""
    found: list[tuple[int, list[float]]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        drifts = [kw.value for kw in node.keywords if kw.arg == "weekly_drift"]
        if isinstance(node.func, ast.Name) and node.func.id == "IndicatorModel":
            drifts += node.args[2:3]
        for drift in drifts:
            numbers = _nonzero_numbers(drift)
            if numbers:
                found.append((node.lineno, numbers))
    return found


def test_the_drift_guard_sees_both_ways_of_writing_one() -> None:
    source = (
        'a = IndicatorModel("x", 1.0, -0.6, 2.0)\n'
        'b = IndicatorModel("x", 1.0, 0.0, 2.0)\n'
        'c = _replace(m, weekly_drift=-drop * 300)\n'
        'd = _replace(m, weekly_drift=-lit["k"].value, noise_sd=0.5)\n'
        'e = IndicatorModel("x", 1.0, weekly_drift=lit["k"].value, noise_sd=2.5)\n'
    )
    assert handwritten_drifts(source) == [(1, [0.6]), (3, [300])]


def test_no_drift_is_written_by_hand() -> None:
    """Toda deriva sale de `LITERATURE`, donde declara su clase. Una escrita a mano no la
    declara, y así fue como la mitad se quedó sin clasificar."""
    source = Path(simulator.__file__).read_text(encoding="utf-8")
    assert handwritten_drifts(source) == []


def test_every_drift_in_every_scenario_is_a_declared_parameter() -> None:
    """Por el otro lado: lo que de verdad llevan los modelos, escenario a escenario, sale de
    valores declarados (uno, o el producto de dos en los escenarios que encadenan efectos)."""
    values = [param.value for param in LITERATURE.values()]
    declared = {round(value, 9) for value in values} | {
        round(a * b, 9) for a in values for b in values
    }
    for scenario in Scenario:
        models = PhysiologicalSimulator(scenario=scenario)._models
        for key, model in models.items():
            if model.weekly_drift:
                assert round(abs(model.weekly_drift), 9) in declared, (scenario, key)


# --------------------------------------------------------------------------- #
# La clase «diseño»
# --------------------------------------------------------------------------- #


def test_design_is_a_class_and_says_it_has_no_backing() -> None:
    assert "design" in EVIDENCE_CLASSES
    design = {name: param for name, param in LITERATURE.items() if param.evidence == "design"}
    assert design
    for name, param in design.items():
        assert param.source == NO_SOURCE, f"{name} cita una fuente siendo de diseño"
        assert "sin respaldo escrito en el repositorio" in param.note, name
    # Y al revés: lo que dice no tener fuente no se cuela en una clase con respaldo.
    for name, param in LITERATURE.items():
        if param.source == NO_SOURCE:
            assert param.evidence == "design", name


def test_the_drifts_the_audit_found_unclassified_are_declared_as_design() -> None:
    for name, value in (
        ("exercise_minutes_decline_per_week", 0.6),
        ("loading_impacts_decline_per_week", 40.0),
        ("symptom_burden_rise_per_week", 0.02),
    ):
        assert LITERATURE[name].evidence == "design"
        assert LITERATURE[name].value == value


def test_the_four_drifts_the_reading_already_judged_took_their_class_with_their_value() -> None:
    """Decisión del usuario (2026-10-31): de «diseño» a la clase que lo leído en vuelo sostiene,
    sin tocar el valor. Ninguna conserva la fuente de diseño ni se queda sin ficha."""
    for name, value, evidence in (
        ("systolic_bp_decline_mmhg_per_week", 0.3, "contested"),
        ("diastolic_bp_decline_mmhg_per_week", 0.2, "contested"),
        ("hrv_rmssd_decline_ms_per_week", 0.8, "contested"),
        ("ntx_rise_per_week", 1.1, "direction_only"),
    ):
        param = LITERATURE[name]
        assert (param.value, param.evidence) == (value, evidence), name
        assert param.source != NO_SOURCE and param.refs, name
        assert "2026-10-31" in param.note and "sin cambiarlo" in param.note, name


def test_every_parameter_falls_in_exactly_one_class() -> None:
    grouped = evidence_by_class()
    names = [name for group in grouped.values() for name in group]
    assert sorted(names) == sorted(LITERATURE)
    assert PhysiologicalSimulator().describe()["evidence"] == grouped


def test_the_report_is_only_for_this_simulator() -> None:
    assert evidence_report([]) is None
    assert evidence_report(["wearable:polar-h10", "manual"]) is None
    # Analíticas reales reproducidas: firmadas como simulador, pero no son este modelo.
    assert evidence_report(["simulator:inspiration4"]) is None
    assert evidence_report(["simulator:habitat"]) is None
    report = evidence_report(["simulator:nominal", "wearable:polar-h10", "simulator:nominal"])
    assert report is not None
    assert report["scenarios"] == ["nominal"]
    assert report["evidence"] == evidence_by_class()
    assert set(report["parameters"]) == set(LITERATURE)
    assert report["parameters"]["symptom_burden_rise_per_week"] == {
        "value": 0.02, "evidence": "design",
        "note": LITERATURE["symptom_burden_rise_per_week"].note, "source": NO_SOURCE,
        "refs": [], "searched": "",
    }
    cortisol = report["parameters"]["cortisol_rise_per_week"]
    assert cortisol["evidence"] == "contested"
    assert cortisol["refs"] == list(LITERATURE["cortisol_rise_per_week"].refs)
    assert cortisol["searched"] == ""


# --------------------------------------------------------------------------- #
# Lo que lo leído contradice (decimosexta ronda, E18)
# --------------------------------------------------------------------------- #

# Lo que lee la frecuencia cardiaca en vuelo del lado de «sin cambio», y lo único leído que la ve
# subir. Si cambia uno de los dos lados, la clase de la deriva se revisa a mano.
HR_UNCHANGED_IN_FLIGHT = {
    "hughson-2012-cardiovascular-iss", "xu-2013-hrv-sleep-iss", "fraser-2012-heart-rate-iss",
    "baevsky-2007-autonomic-iss",
}
HR_RISES_IN_FLIGHT = {"baevsky-1997-holter-mir"}


def test_the_resting_heart_rate_drift_is_contested_with_both_sides_and_is_now_zero() -> None:
    """Decisión del usuario (2026-10-31): el modelo nominal toma el lado del peso de lo leído,
    «sin cambio», y la clase sigue diciendo que un estudio discrepa."""
    param = LITERATURE["resting_hr_drift_bpm_per_week"]
    assert param.evidence == "contested"
    assert param.value == 0.0, "corregida a 0 el 2026-10-31: decisión del usuario"
    assert CrewMember("crew-01").models["heart-rate"].weekly_drift == 0.0
    assert "2026-10-31" in param.note
    refs = set(param.refs)
    assert refs >= HR_UNCHANGED_IN_FLIGHT | HR_RISES_IN_FLIGHT
    # Lo que el sentido en vuelo del perfil de línea base lee de la FC, el simulador lo cita. No
    # se exige que siga «sin cambio»: si aquel recoge a Baevsky 2007 y 1997 (lo que queda en
    # §5.36.18), pasa a discutido y esta prueba no tiene por qué romperse.
    read = flight_direction.read()
    heart_rate = read["indicators"]["heart-rate"]
    assert heart_rate["direction"] in {"unchanged", "contested"}
    statements = {s["id"]: s["ref"] for s in read["statements"]}
    assert {statements[item] for item in heart_rate["statements"]} <= refs
    # Y la nota dice de dónde salía la cifra: de después del vuelo.
    assert "DESPUÉS del vuelo" in param.note


def test_the_salivary_cortisol_drift_is_contested_with_what_was_read_and_is_now_zero(
) -> None:
    """Decisión del usuario (2026-10-31): el modelo nominal ya no sube el cortisol salival. La
    clase es «contestado» desde que Vorobiev 1995 y Buchheim 2019 discrepan: una frase discutida
    no sostiene una deriva semanal. El escenario de reactivación conserva su subida, de diseño."""
    param = LITERATURE["cortisol_rise_per_week"]
    assert param.evidence == "contested"
    assert param.value == 0.0, "corregida a 0 el 2026-10-31: decisión del usuario"
    assert CrewMember("crew-01").models["cortisol-salivary"].weekly_drift == 0.0
    assert LITERATURE["immune_cortisol_rise_per_week"].value == 0.065
    assert "2026-10-31" in param.note
    assert param.source != NO_SOURCE
    cortisol = flight_direction.read()["indicators"]["cortisol-salivary"]
    # La clase de la deriva y el sentido leído junto a la línea base dicen lo mismo: que no se
    # contradigan `/api/status` y el perfil es lo que vigila esta línea.
    assert cortisol["direction"] == "contested"
    assert {
        "vorobiev-1995-altair-mir", "buchheim-2019-inflammaging-cosmonauts",
        "mehta-2017-latent-virus-iss", "agha-2020-salivary-iss",
    } <= set(param.refs)
    for name in ("Mehta 2017", "Buchheim 2019", "Agha 2020", "Vorobiev 1995"):
        assert name in param.note


# Las cuatro contestadas que no nombraban ficha (§5.36.18, «Queda»), con lo leído el 2026-10-26
# (decimoséptima ronda, U10): cada una, sus dos lados por ficha y su valor de siempre. Si cambia un
# lado, la clase se revisa a mano. La cuarta, la fatiga de menú, ya no está: pasó a «sin respaldo
# en lo leído» (decimoctava ronda, §5.38.10; su prueba, más abajo).
CONTESTED_SIDES: dict[str, tuple[float, set[str], set[str]]] = {
    # El cortisol salival en vuelo: sube en dos cosmonautas, no cambia en doce. El modelo, en 0.
    "cortisol_rise_per_week": (
        0.0,
        {"buchheim-2019-inflammaging-cosmonauts"},
        {"vorobiev-1995-altair-mir"},
    ),
    # El tiempo de reacción de la PVT sube con el CO2: la única PVT leída no lo ve.
    "co2_pvt_rt_rise_ms": (
        12.0,
        {"satish-2012-co2-decision-making", "manzey-1998-co2-performance"},
        {"scully-2019"},
    ),
    # La eficiencia del sueño baja con el CO2: menos sueño profundo frente a sueño sin cambio.
    "co2_sleep_efficiency_drop_pct": (
        3.0,
        {"van-hoy-2026-co2-sleep-analog"},
        {"gundel-1998-co2-sleep", "christian-2024-hdtbr-co2-sleep"},
    ),
    # La SDNN cae en vuelo: el dominio temporal baja en el sueño, la potencia total sube.
    "hrv_sdnn_decline_ms_per_week": (
        0.3, {"xu-2013-hrv-sleep-iss"}, {"otsuka-2016-hrv-time-structure"},
    ),
    # La FC en reposo, corregida a 0 el 2026-10-31 (decisión del usuario): el lado del modelo es
    # ahora «sin cambio», el del peso de lo leído; el otro, el único que la ve subir.
    "resting_hr_drift_bpm_per_week": (0.0, HR_UNCHANGED_IN_FLIGHT, HR_RISES_IN_FLIGHT),
    # Las tres de diseño que lo leído en vuelo ya daba por discutidas, reclasificadas el
    # 2026-10-31 con su valor (decimonovena ronda, U22).
    # La RMSSD baja: el dominio temporal y la banda de alta frecuencia bajan (Xu 2013, Hughson
    # 2012); la banda de alta frecuencia no cambia (Baevsky 2007). Ningún resumen la nombra.
    "hrv_rmssd_decline_ms_per_week": (
        0.8, {"xu-2013-hrv-sleep-iss", "hughson-2012-cardiovascular-iss"},
        {"baevsky-2007-autonomic-iss"},
    ),
    # La presión baja: la ambulatoria de 24 h (Norsk 2015) y «BP decreased» (Baevsky 2007)
    # frente a las medidas cortas sentados sin cambio (Hughson 2012).
    "systolic_bp_decline_mmhg_per_week": (
        0.3, {"norsk-2015-ambulatory-bp-iss", "baevsky-2007-autonomic-iss"},
        {"hughson-2012-cardiovascular-iss"},
    ),
    "diastolic_bp_decline_mmhg_per_week": (
        0.2, {"norsk-2015-ambulatory-bp-iss", "baevsky-2007-autonomic-iss"},
        {"hughson-2012-cardiovascular-iss"},
    ),
}


@pytest.mark.parametrize("name", sorted(CONTESTED_SIDES))
def test_each_contested_drift_names_both_sides_and_keeps_its_value(name: str) -> None:
    param = LITERATURE[name]
    value, model_side, other_side = CONTESTED_SIDES[name]
    assert param.evidence == "contested", "nombrar las fichas no cambia la clase"
    assert param.value == value, "nombrar las fichas no cambia el valor"
    assert model_side and other_side and not model_side & other_side
    assert model_side | other_side <= set(param.refs)
    # Cada ficha citada se nombra en la nota o en la fuente: un artículo por su primer autor y su
    # año; un documento de NTRS, por su número.
    said = f"{param.note} {param.source}"
    for ref_id in param.refs:
        if ref_id.startswith("ntrs-"):
            assert f"NTRS {ref_id.removeprefix('ntrs-')}" in said, (name, ref_id)
            continue
        author = registry.get(ref_id).source.split(" ")[0].rstrip(".,")
        year = re.search(r"\d{4}", ref_id)
        assert year is not None and f"{author}" in said and year.group(0) in said, (name, ref_id)


def test_no_contested_drift_is_left_without_its_cards() -> None:
    """§5.36.18 dejaba cuatro sin ficha porque `literature_problems` solo pedía dos a un
    «contestado» que citara alguna. Ya no queda ninguno, y desde §5.38.10 se le piden a todos."""
    contested = {name for name, param in LITERATURE.items() if param.evidence == "contested"}
    assert contested == set(CONTESTED_SIDES)
    assert all(len(LITERATURE[name].refs) >= 2 for name in contested)


def test_the_menu_fatigue_drift_is_unsupported_with_its_old_value_and_what_was_searched() -> None:
    """Decisión del usuario (§5.38.10): lo único leído en vuelo no ve la caída y lo que la ve es de
    Tierra con monotonía estricta. Pasa a «sin respaldo en lo leído» con el mismo valor."""
    param = LITERATURE["menu_fatigue_acceptability_drop_per_week"]
    assert param.evidence == "unsupported"
    assert param.value == 0.4, "reclasificar no cambia el valor: lo decide el usuario"
    assert param.source != NO_SOURCE
    assert set(param.refs) == {
        "douglas-2025-iss-food-acceptability", "meiselman-2000-variety-monotony",
        "ntrs-20220014371",
    }
    for said in ("Douglas 2025", "did not decrease", "Meiselman 2000", "en Tierra",
                 "NTRS 20220014371", "Data are currently being assessed"):
        assert said in param.searched, said
    # Las fichas ya no dicen que la deriva sea «contestada».
    for ref_id in param.refs:
        notes = registry.get(ref_id).notes or ""
        assert "deriva contestada" not in notes, ref_id
        assert "sin respaldo en lo leído" in notes, ref_id


def test_the_sleep_drift_no_longer_reads_into_law_2014_what_its_abstract_does_not_say() -> None:
    param = LITERATURE["co2_sleep_efficiency_drop_pct"]
    assert "Law 2014 describe" not in param.note
    assert "solo habla de cefaleas" in param.note
    assert "law-2014" in param.refs
    notes = registry.get("law-2014").notes or ""
    assert "no nombra el sueño ni la fatiga" in notes and "2026-10-26" in notes


def test_the_blood_pressure_drifts_are_contested_as_the_flight_direction_reads_them() -> None:
    """La sistólica y la diastólica citan las mismas fichas que el sentido en vuelo, que las da
    por discutidas (Hughson 2012 sin cambio; Norsk 2015 y Baevsky 2007, bajan)."""
    read = flight_direction.read()
    statements = {s["id"]: s["ref"] for s in read["statements"]}
    for key, name in (
        ("systolic-bp", "systolic_bp_decline_mmhg_per_week"),
        ("diastolic-bp", "diastolic_bp_decline_mmhg_per_week"),
    ):
        found = read["indicators"][key]
        assert found["direction"] == "contested", key
        assert {statements[item] for item in found["statements"]} == set(LITERATURE[name].refs)
        assert "mide distinto" in LITERATURE[name].note, name


def test_the_rmssd_drift_is_contested_as_the_flight_direction_reads_it() -> None:
    """La decisión del 2026-10-31 decía «sentido documentado» sobre la nota del 2026-10-23, escrita
    con la lectura de D14 (Xu 2013 y Hughson 2012: baja). La lectura del sentido en vuelo (E16, el
    mismo 2026-10-23) añadió a Baevsky 2007 y da la RMSSD por discutida; el simulador dice lo que
    la lectura, con las mismas fichas."""
    read = flight_direction.read()
    found = read["indicators"]["hrv-rmssd"]
    assert found["direction"] == "contested"
    statements = {s["id"]: s["ref"] for s in read["statements"]}
    param = LITERATURE["hrv_rmssd_decline_ms_per_week"]
    assert {statements[item] for item in found["statements"]} == set(param.refs)
    assert "la da por discutida" in param.note


def test_the_ntx_drift_has_its_direction_documented_with_its_old_value() -> None:
    """Dos frases leídas hablan de los marcadores de resorción en conjunto; el telopéptido N se
    nombra después del aterrizaje y, en vuelo, en Zwart 2018. La nota lo dice, y la magnitud sigue
    siendo la de diseño."""
    param = LITERATURE["ntx_rise_per_week"]
    assert (param.evidence, param.value) == ("direction_only", 1.1)
    assert set(param.refs) == {
        "smith-2005-bone-markers-mir", "smith-2012-bone-resistance-iss",
        "zwart-2018-dietary-acid-load",
    }
    read = flight_direction.read()
    found = read["indicators"]["ntx-telopeptide"]
    assert found["direction"] == "rises"
    statements = {s["id"]: s["ref"] for s in read["statements"]}
    assert {statements[item] for item in found["statements"]} == set(param.refs)
    assert "en conjunto" in param.note and "después del aterrizaje" in param.note
    for said in (
        "Smith 2005", "Smith 2012", "Zwart 2018", "higher than before flight", "during flight",
    ):
        assert said in param.note, said


def test_the_sdnn_drift_cites_what_the_flight_direction_reads() -> None:
    """La SDNN del simulador y la del sentido en vuelo citan las mismas frases leídas."""
    read = flight_direction.read()
    sdnn = read["indicators"]["hrv-sdnn"]
    assert sdnn["direction"] == "contested"
    statements = {s["id"]: s["ref"] for s in read["statements"]}
    assert {statements[item] for item in sdnn["statements"]} <= set(
        LITERATURE["hrv_sdnn_decline_ms_per_week"].refs
    )


def test_every_declaration_is_sound_against_the_registry() -> None:
    assert literature_problems(LITERATURE, registry.registry()) == []
    assert cited_refs() <= set(registry.registry())
    assert cited_refs(), "las dos derivas reclasificadas citan lo leído"


def _with(name: str, **changes: Any) -> dict[str, DriftParameter]:
    return {name: dataclasses.replace(LITERATURE[name], **changes)}


@pytest.mark.parametrize(
    ("literature", "fragment"),
    [
        (_with("ntx_rise_per_week", evidence="likely"), "clase desconocida"),
        (_with("menu_fatigue_acceptability_drop_per_week", refs=("no-such-ref",)), "no existen"),
        (
            _with(
                "menu_fatigue_acceptability_drop_per_week",
                refs=("mehta-2017-latent-virus-iss",) * 2,
            ),
            "dos veces",
        ),
        (_with("menu_fatigue_acceptability_drop_per_week", searched="  "), "donde se busco"),
        (_with("menu_fatigue_acceptability_drop_per_week", refs=()), "ficha de lo leido"),
        (_with("menu_fatigue_acceptability_drop_per_week", source=NO_SOURCE), "no es diseño"),
        (_with("hrv_sdnn_decline_ms_per_week", searched="algo"), "solo es de la clase"),
        (
            _with("resting_hr_drift_bpm_per_week", refs=("hughson-2012-cardiovascular-iss",)),
            "el otro lado",
        ),
        # Sin ninguna ficha, también (§5.38.10): antes solo se le pedían al que citara alguna.
        (_with("resting_hr_drift_bpm_per_week", refs=()), "el otro lado"),
        (
            _with("symptom_burden_rise_per_week", refs=("mehta-2017-latent-virus-iss",)),
            "cita fichas",
        ),
    ],
)
def test_an_unsound_declaration_is_named(
    literature: dict[str, DriftParameter], fragment: str
) -> None:
    problems = literature_problems(literature, registry.registry())
    assert len(problems) == 1 and fragment in problems[0], problems
    assert problems[0].startswith(next(iter(literature)))


# --------------------------------------------------------------------------- #
# El estado lo enseña y el veredicto no cambia
# --------------------------------------------------------------------------- #


def _verdict(status: dict[str, Any]) -> dict[str, Any]:
    """Lo que el motor decide: niveles, dominios enteros, alertas, recomendaciones."""
    return {
        "overall_level": status["overall_level"],
        "domains": status["domains"],
        "alerts": [
            {k: v for k, v in alert.items() if k != "rules_version"}
            for alert in status["alerts"]
        ],
        "recommendations": status["recommendations"],
        "predictions": status["predictions"],
    }


def _simulated_status(client: TestClient, scenario: str) -> dict[str, Any]:
    reset_store(new_store())
    assert client.post("/api/simulate", params={"scenario": scenario, "days": 40}).is_success
    status: dict[str, Any] = client.get("/api/status").json()
    return status


def test_status_has_no_simulation_block_without_simulated_data(client: TestClient) -> None:
    body = {
        "key": "heart-rate", "value": 61.0, "source": "manual",
        "effective": "2026-11-02T08:00:00+00:00",
    }
    posted = client.post("/api/observations", json=body)
    if not posted.is_success:
        pytest.skip(f"la ingesta manual pide otro cuerpo: {posted.status_code}")
    assert client.get("/api/status").json()["simulation"] is None


@pytest.mark.parametrize("scenario", sorted(VERDICT_BEFORE))
def test_status_declares_the_evidence_and_the_verdict_is_the_one_before(
    client: TestClient, scenario: str
) -> None:
    status = _simulated_status(client, scenario)

    simulation = status["simulation"]
    assert simulation["scenarios"] == [scenario]
    assert simulation["evidence"] == evidence_by_class()
    assert {p["evidence"] for p in simulation["parameters"].values()} <= set(EVIDENCE_CLASSES)

    overall, alerts = VERDICT_BEFORE[scenario]
    assert status["overall_level"] == overall
    assert sorted([a["domain"], a["level"]] for a in status["alerts"]) == alerts


def test_the_verdict_is_identical_with_and_without_this_unit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invariante 5. Con la huella antigua (casi vacía) y sin bloque `simulation`, el motor
    decide exactamente lo mismo: lo único que cambia es lo que se declara."""
    scenario = "progressive-insomnia"
    with_unit = _simulated_status(client, scenario)

    monkeypatch.setattr(routes, "evidence_report", lambda sources: None)
    monkeypatch.setattr(versioning, "FINGERPRINTED", {})
    versioning.rules_version.cache_clear()
    try:
        without_unit = _simulated_status(client, scenario)
    finally:
        monkeypatch.undo()
        versioning.rules_version.cache_clear()

    assert without_unit["simulation"] is None and with_unit["simulation"] is not None
    assert without_unit["rules_version"] != with_unit["rules_version"]
    assert with_unit["alerts"], "el escenario tiene que alertar para que la prueba diga algo"
    assert _verdict(with_unit) == _verdict(without_unit)
