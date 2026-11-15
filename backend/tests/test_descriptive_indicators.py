"""Indicadores descriptivos: salud conductual más allá del ánimo, síntomas visuales y forma física.

Decisión del usuario (2026-10-15): entran como observaciones —firmadas en el ledger, listadas en
`/api/indicators` con su sistema de códigos y enseñadas con lo leído de su medida— pero son
descriptivos: el estado no los lee. Aquí se comprueba lo que eso exige, sin red:

- cada código LOINC con la unidad de su PROPIEDAD (invariante 2) y cada código propio con su
  porqué (invariante 1);
- solo entra lo que tiene medida leída, con su frase (`data/instruments_read.json`);
- una lectura descriptiva, por extrema que sea, no mueve niveles, alertas, puntuaciones, la hora
  de referencia ni la versión de las reglas (invariante 5);
- ningún sitio que describe lo que evalúa un dominio los cuenta.
"""

import copy
import datetime as dt
import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import risk_entity, timeline
from app.api import descriptive, diary
from app.api.routes import new_store, reset_store
from app.core import versioning
from app.core.config import Settings, get_settings
from app.evidence import instruments_read
from app.evidence.instruments_read import InstrumentsError
from app.ingest.codes import (
    CATALOG,
    COGNITION_KEYS,
    COGNITION_TESTS,
    DESCRIPTIVE_DECISIONS,
    DESCRIPTIVE_LOINC,
    DESCRIPTIVE_ONLY,
    FORCE_UNITS,
    MASS_PER_DAY_UNITS,
    MISSION_SPECIFIC,
    NO_LOINC_AVAILABLE,
    REGULAR_CYCLE_STATUS,
    RENAL_URINE_LOINC,
    TEAM_COHESION_KEYS,
    TEAM_COHESION_STATEMENT,
    CodeSystem,
    Domain,
    ObservationCategory,
    by_domain,
    evaluated_by_domain,
)
from app.ingest.cost import COST_PATH, cost
from app.ingest.fhir import observation
from app.ingest.names_es import NameOrigin, spanish_name
from app.ingest.simulator import PhysiologicalSimulator, Scenario
from app.main import app
from app.text_guard import check

# La química de la orina de 24 horas del riesgo de cálculos renales (decisión del usuario del
# 2026-10-26), en el orden del catálogo.
URINE = (
    "urine-calcium-24h", "urine-oxalate-24h", "urine-urate-24h", "urine-citrate-24h",
    "urine-ph-24h", "urine-sodium-24h", "urine-osmolality-24h", "urine-caox-supersaturation-24h",
)
# Sensoriomotor y músculo (decisión del plan de la decimonovena ronda, 2026-10-31), en el orden
# del catálogo: dos pruebas funcionales de Standard Measures y dos medidas de músculo.
SENSORIMOTOR_MUSCLE = (
    "tandem-walk-correct-steps", "recovery-from-fall-time", "dxa-lean-mass", "imtp-peak-force",
)
# Equipo, estrés y cognición (decimonovena ronda, U14, 2026-10-31): las nueve pruebas de la batería
# Cognition sin indicador previo (la PVT ya tenía los suyos), con su velocidad y, salvo la MPT, su
# precisión (la BART, su riesgo); el estrés de la escala visual analógica del Reaction Self Test; y
# las tres afirmaciones de cohesión del cuestionario de fin de día de Standard Measures.
COGNITION = (
    "cognition-mpt-speed",
    "cognition-volt-speed", "cognition-volt-accuracy",
    "cognition-f2b-speed", "cognition-f2b-accuracy",
    "cognition-am-speed", "cognition-am-accuracy",
    "cognition-lot-speed", "cognition-lot-accuracy",
    "cognition-ert-speed", "cognition-ert-accuracy",
    "cognition-mrt-speed", "cognition-mrt-accuracy",
    "cognition-dsst-speed", "cognition-dsst-accuracy",
    "cognition-bart-speed", "cognition-bart-risk",
)
STRESS = "stress-rating-vas"
COHESION = ("team-cohesion-cared", "team-cohesion-task-focus", "team-cohesion-shared-purpose")
BEHAVIORAL_INSTRUMENTS = (*COGNITION, STRESS, *COHESION)
# Los nutrientes ingeridos al día (decimonovena ronda, 2026-10-31), en el orden del catálogo.
NUTRIENTS = (
    "sodium-intake-daily", "calcium-intake-daily", "protein-intake-daily",
    "vitamin-d-intake-daily",
)
GLUCOSE_CAPILLARY = "glucose-capillary"
# El ciclo menstrual y la anticoncepción (lote «ciclo», 2026-11-14), en el orden del catálogo.
CYCLE = (
    "menstrual-flow", "menstruation-start", "intermenstrual-bleeding", "ovulation-test",
    "contraceptive-in-use", "basal-body-temperature",
)
# El estado reproductivo, la terapia hormonal de la menopausia y los síntomas vasomotores (lote
# «ciclo», unidad C2, 2026-11-15), en el orden del catálogo.
REPRODUCTIVE = ("reproductive-status", "menopausal-hormone-therapy", "hot-flashes", "night-sweats")
EXPECTED = {
    "vision-change", "nasa-tlx-workload", "vo2-peak", "grip-strength-right", "grip-strength-left",
    "vitamin-d-25oh", GLUCOSE_CAPILLARY, *URINE, "bmd-dxa-lumbar-spine", "bmd-dxa-hip",
    *SENSORIMOTOR_MUSCLE, *BEHAVIORAL_INSTRUMENTS, *NUTRIENTS, *CYCLE,
    *REPRODUCTIVE,
}
# Lo más extremo que admite cada uno: si algo de esto llegara al motor, se notaría.
EXTREME = {
    "vision-change": 3.0,
    "nasa-tlx-workload": 100.0,
    "vo2-peak": 1.0,
    "grip-strength-right": 0.0,
    "grip-strength-left": 0.0,
    "vitamin-d-25oh": 300.0,
    GLUCOSE_CAPILLARY: 1000.0,
    "urine-calcium-24h": 2000.0,
    "urine-oxalate-24h": 500.0,
    "urine-urate-24h": 3000.0,
    "urine-citrate-24h": 0.0,
    "urine-ph-24h": 0.0,
    "urine-sodium-24h": 1000.0,
    "urine-osmolality-24h": 2000.0,
    "urine-caox-supersaturation-24h": 100.0,
    "bmd-dxa-lumbar-spine": 0.1,
    "bmd-dxa-hip": 3.0,
    "tandem-walk-correct-steps": 0.0,
    "recovery-from-fall-time": 1800.0,
    "dxa-lean-mass": 10.0,
    "imtp-peak-force": 1.0,
    # Un minuto de media por respuesta, y ningún acierto (o el riesgo máximo).
    **{key: 60000.0 for key in COGNITION if key.endswith("-speed")},
    **{key: 0.0 for key in COGNITION if key.endswith("-accuracy")},
    "cognition-bart-risk": 1.0,
    STRESS: 100.0,
    **dict.fromkeys(COHESION, 1.0),
    "sodium-intake-daily": 20000.0,
    "calcium-intake-daily": 0.0,
    "protein-intake-daily": 1000.0,
    "vitamin-d-intake-daily": 1000.0,
    "menstrual-flow": 3.0,
    "menstruation-start": 1.0,
    "intermenstrual-bleeding": 1.0,
    "ovulation-test": 2.0,
    "contraceptive-in-use": 7.0,
    "basal-body-temperature": 45.0,
    "reproductive-status": 6.0,
    "menopausal-hormone-therapy": 1.0,
    "hot-flashes": 3.0,
    "night-sweats": 3.0,
}
DENSITOMETRY = ("bmd-dxa-lumbar-spine", "bmd-dxa-hip")
# El día en que se leyó la medida de cada uno: la vitamina D entró una semana después; la química
# de la orina y la densitometría, el 2026-10-26; sensoriomotor y músculo, los instrumentos
# conductuales y los nutrientes ingeridos, el 2026-10-31.
READ_ON = (
    {key: "2026-10-16" for key in EXPECTED}
    | {"vitamin-d-25oh": "2026-10-22"}
    | {GLUCOSE_CAPILLARY: "2026-11-04"}
    | dict.fromkeys(URINE, "2026-10-26")
    | dict.fromkeys(DENSITOMETRY, "2026-10-26")
    | dict.fromkeys(SENSORIMOTOR_MUSCLE, "2026-10-31")
    | dict.fromkeys(BEHAVIORAL_INSTRUMENTS, "2026-10-31")
    | dict.fromkeys(NUTRIENTS, "2026-10-31")
    | dict.fromkeys(CYCLE, "2026-11-14")
    | dict.fromkeys(REPRODUCTIVE, "2026-11-15")
)
# El día en que el usuario decidió que entrara cada uno (los conductuales, por la regla del plan de
# la decimonovena ronda: solo con instrumento leído; los nutrientes, en ese mismo plan).
DECIDED = (
    {key: "2026-10-15" for key in EXPECTED}
    | {"vitamin-d-25oh": "2026-10-22"}
    | {GLUCOSE_CAPILLARY: "2026-11-04"}
    | dict.fromkeys(URINE, "2026-10-26")
    | dict.fromkeys(DENSITOMETRY, "2026-10-26")
    | dict.fromkeys(SENSORIMOTOR_MUSCLE, "2026-10-31")
    | dict.fromkeys(BEHAVIORAL_INSTRUMENTS, "2026-10-31")
    | dict.fromkeys(NUTRIENTS, "2026-10-31")
    | dict.fromkeys(CYCLE, "2026-11-14")
    | dict.fromkeys(REPRODUCTIVE, "2026-11-15")
)
# La versión de LOINC en que se leyó cada ficha: la química de la orina, la densitometría, los
# nutrientes y la glucosa capilar, en la 2.83, la que servía tx.fhir.org esos días; las demás, en
# la 2.82.
LOINC_VERSION = (
    dict.fromkeys(URINE, "2.83") | dict.fromkeys(DENSITOMETRY, "2.83")
    | dict.fromkeys(NUTRIENTS, "2.83") | {GLUCOSE_CAPILLARY: "2.83"}
)


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _verdict(client: TestClient) -> tuple[Any, ...]:
    response = client.get("/api/status")
    assert response.status_code == 200, response.text
    status = response.json()
    return (
        status["overall_level"],
        {key: (item["level"], item["score"]) for key, item in status["domains"].items()},
        [(item["id"], item["level"]) for item in status["alerts"]],
        # Ni el «ahora» de los datos ni cuántas lecturas se analizan: las descriptivas no cuentan.
        status["data"]["reference_time"],
        status["data"]["observations"],
        status["rules_version"],
    )


def _post(client: TestClient, key: str, value: float, when: dt.datetime) -> None:
    response = client.post(
        "/api/observations",
        json={"key": key, "value": value, "subject": "crew-01", "effective": when.isoformat()},
    )
    assert response.status_code == 201, response.text


# --------------------------------------------------------------------------- #
# Invariantes 1 y 2: el código y la unidad
# --------------------------------------------------------------------------- #


def test_the_descriptive_indicators_are_the_ones_decided() -> None:
    assert DESCRIPTIVE_ONLY == EXPECTED
    assert set(CATALOG) >= DESCRIPTIVE_ONLY
    # Ninguno trae rango ni límite: lo que la norma pide se cita, no se evalúa.
    for key in DESCRIPTIVE_ONLY:
        code = CATALOG[key]
        assert (code.reference_low, code.reference_high) == (None, None), key
        assert (code.critical_low, code.critical_high) == (None, None), key
        assert code.physical_min is not None and code.physical_max is not None, key


def test_each_loinc_code_was_read_and_its_unit_follows_the_property() -> None:
    loinc = {key for key in DESCRIPTIVE_ONLY if CATALOG[key].system is CodeSystem.LOINC}
    assert loinc == set(DESCRIPTIVE_LOINC) == {
        "vo2-peak", "grip-strength-right", "grip-strength-left", "vitamin-d-25oh",
        GLUCOSE_CAPILLARY,
        *(key for key in URINE if key != "urine-caox-supersaturation-24h"),
        *DENSITOMETRY,
        "calcium-intake-daily", "protein-intake-daily",
    }
    for key, read in DESCRIPTIVE_LOINC.items():
        code = CATALOG[key]
        assert read.status == "ACTIVE" and read.version == LOINC_VERSION.get(key, "2.82"), key
        assert read.read_on == READ_ON[key], key
        assert read.url.startswith("https://tx.fhir.org/r4/CodeSystem/$lookup")
        assert f"code={code.code}&" in read.url, key
        if read.property == "Force":
            # Fuerza, no masa: un kilogramo a secas sería el error silencioso de la invariante 2.
            assert code.unit in FORCE_UNITS and code.unit != "kg", key
        elif read.property == "MCnc" and key == GLUCOSE_CAPILLARY:
            # Masa por volumen: mg/dL. En mmol/L sería SCnc, que es otro código.
            assert code.unit == read.example_ucum == "mg/dL", key
        elif read.property == "MCnc":
            # Masa por volumen: ng/mL. En nmol/L sería SCnc, que es otro código (68438-1).
            assert code.unit == read.example_ucum == "ng/mL", key
        elif read.property == "MRat":
            # Masa por tiempo: mg o g al día. En mmol al día sería SRat, otro código.
            assert code.unit in MASS_PER_DAY_UNITS and read.example_ucum in MASS_PER_DAY_UNITS, key
            if key in NUTRIENTS:
                # La ficha de la ingesta no escribe la propiedad en el nombre: dice «24 hour».
                assert code.display.endswith("intake 24 hour") and read.method is None, key
            else:
                assert "[Mass/time]" in code.display, key
        elif read.property == "SRat":
            # Sustancia por tiempo: mmol al día, la unidad de ejemplo.
            assert code.unit == read.example_ucum == "mmol/(24.h)", key
            assert "[Moles/time]" in code.display, key
        elif read.property == "Osmol":
            assert code.unit == read.example_ucum == "mosm/kg", key
        elif read.property == "LsCnc":
            assert code.unit == read.example_ucum == "[pH]", key
        elif read.property == "ArMass":
            # Masa por área: g/cm², la densidad areal de la DXA. Una densidad de volumen (g/cm3,
            # la de la tomografía) sería otra propiedad y otro código.
            assert code.unit == read.example_ucum == "g/cm2", key
            assert read.method == "DXA", key
        else:
            assert read.property == "VRatCnt"
            assert code.unit == read.example_ucum == "mL/min/kg{body_wt}"
    assert DESCRIPTIVE_LOINC["grip-strength-right"].system == "Hand.right"
    assert DESCRIPTIVE_LOINC["grip-strength-left"].system == "Hand.left"


def test_each_own_code_says_why_it_is_not_loinc() -> None:
    own = {key for key in DESCRIPTIVE_ONLY if CATALOG[key].system is CodeSystem.EMMA}
    assert own == {
        "vision-change", "nasa-tlx-workload", "urine-caox-supersaturation-24h",
        *SENSORIMOTOR_MUSCLE,
        *BEHAVIORAL_INSTRUMENTS,
        "sodium-intake-daily", "vitamin-d-intake-daily",
        *CYCLE,
        *REPRODUCTIVE,
    }
    assert "vision-change" in MISSION_SPECIFIC and MISSION_SPECIFIC["vision-change"].strip()
    assert "nasa-tlx-workload" in NO_LOINC_AVAILABLE
    assert "urine-caox-supersaturation-24h" in NO_LOINC_AVAILABLE
    # Las cuatro de sensoriomotor y músculo: se buscó y no hay código adecuado.
    for key in SENSORIMOTOR_MUSCLE:
        assert key in NO_LOINC_AVAILABLE and key not in MISSION_SPECIFIC, key
    # Los instrumentos conductuales se buscaron en LOINC y ninguno tiene código: lo dice el panel.
    for key in BEHAVIORAL_INSTRUMENTS:
        assert key in NO_LOINC_AVAILABLE, key
        searched = descriptive.LOINC_SEARCHED[key]
        assert "2026-10-31" in searched and "2.83" in searched, key
    assert "sodium-intake-daily" in NO_LOINC_AVAILABLE
    assert "vitamin-d-intake-daily" in NO_LOINC_AVAILABLE
    # Los seis del ciclo: se buscó en LOINC el 2026-11-14 y ninguno casa; lo dice el panel.
    for key in CYCLE:
        assert key in NO_LOINC_AVAILABLE and key not in MISSION_SPECIFIC, key
        searched = descriptive.LOINC_SEARCHED[key]
        assert "2026-11-14" in searched and "2.83" in searched, key
    # Los cuatro del estado reproductivo y los síntomas vasomotores: buscado el 2026-11-15.
    for key in REPRODUCTIVE:
        assert key in NO_LOINC_AVAILABLE and key not in MISSION_SPECIFIC, key
        searched = descriptive.LOINC_SEARCHED[key]
        assert "2026-11-15" in searched and "2.83" in searched, key


def test_their_fhir_category_is_what_they_are() -> None:
    when = dt.datetime(2026, 10, 1, 12, tzinfo=dt.UTC)
    category = {}
    for key in DESCRIPTIVE_ONLY:
        resource = observation(key, EXTREME[key], when, "crew-01", "manual").to_fhir()
        # Un registro de ingesta no lleva categoría: ninguna de las nueve lo describe
        # (`test_fhir.test_an_intake_record_goes_without_a_category_and_still_validates`).
        listed = resource.get("category")
        category[key] = listed[0]["coding"][0]["code"] if listed is not None else None
    # Ni el cuestionario es una imagen ni el VO2 pico un signo vital.
    assert category == {
        "vision-change": "survey",
        "nasa-tlx-workload": "survey",
        "vo2-peak": "exam",
        "grip-strength-right": "exam",
        "grip-strength-left": "exam",
        # Un analito de suero, aunque se agrupe en el dominio óseo («activity»).
        "vitamin-d-25oh": "laboratory",
        # Un analito de sangre leído con glucómetro (clase CHEM de su ficha).
        GLUCOSE_CAPILLARY: "laboratory",
        # La química de la orina, aunque el dominio genitourinario sea «imaging» (la vejiga).
        **dict.fromkeys(URINE, "laboratory"),
        # Una prueba de imagen con rayos X, aunque se agrupe en el dominio óseo.
        "bmd-dxa-lumbar-spine": "imaging",
        "bmd-dxa-hip": "imaging",
        # Pruebas funcionales observadas y una de fuerza: «exam», no la «survey» del dominio
        # musculoesquelético; la composición corporal por DXA, imagen, como la densidad ósea.
        "tandem-walk-correct-steps": "exam",
        "recovery-from-fall-time": "exam",
        "dxa-lean-mass": "imaging",
        "imtp-peak-force": "exam",
        # Una batería de pruebas en un ordenador y dos cuestionarios: instrumentos de valoración.
        **dict.fromkeys(BEHAVIORAL_INSTRUMENTS, "survey"),
        # Un registro de lo que se come, como la energía: sin categoría.
        **dict.fromkeys(NUTRIENTS, None),
        # Un diario del ciclo y un test casero leído por quien lo usa: ninguna de las nueve los
        # describe; la temperatura basal con código propio no puede ir como signo vital.
        **dict.fromkeys(CYCLE, None),
        # El estado reproductivo y los síntomas vasomotores, por el mismo motivo: un autoinforme
        # que no sale de un cuestionario con sus preguntas.
        **dict.fromkeys(REPRODUCTIVE, None),
    }


# --------------------------------------------------------------------------- #
# Solo entra lo que tiene medida leída
# --------------------------------------------------------------------------- #


def test_every_descriptive_indicator_has_its_measure_read() -> None:
    raw = instruments_read.read()
    assert set(raw["measures"]) == DESCRIPTIVE_ONLY
    for key in DESCRIPTIVE_ONLY:
        measure = instruments_read.measure(key)
        assert measure is not None
        assert measure["statements"] and measure["scope"] and measure["instrument"]
        for item in measure["statements"]:
            assert item["quote"] and item["where"] and item["url"]
            assert item["read_on"] == READ_ON[key], key
    assert instruments_read.measure("heart-rate") is None


def test_the_vision_categories_are_written_in_the_source_and_their_numbers_are_emma() -> None:
    measure = instruments_read.measure("vision-change")
    assert measure is not None
    quotes = {item["id"]: item["quote"] for item in measure["statements"]}
    assert [item["value"] for item in measure["categories"]] == [1, 2, 3]
    for item in measure["categories"]:
        assert item["literal"] in quotes[item["statement"]]
    assert [item["literal"].split(" ")[0] for item in measure["categories"]] == [
        "mild", "moderate", "severe",
    ]
    assert "los números son de EMMA" in measure["numbering"]
    assert CATALOG["vision-change"].physical_min == 0
    assert CATALOG["vision-change"].physical_max == 3


def _raw() -> dict[str, Any]:
    return copy.deepcopy(json.loads(instruments_read.READ_PATH.read_text(encoding="utf-8")))


def test_the_loader_refuses_a_descriptive_indicator_without_its_measure() -> None:
    raw = _raw()
    del raw["measures"]["vo2-peak"]
    with pytest.raises(InstrumentsError, match="sin medida leída"):
        instruments_read.validate(raw)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda m: m["vision-change"]["categories"][0].update(literal="slight"), "no está escrito"),
        (lambda m: m["vision-change"].pop("numbering"), "numbering"),
        (lambda m: m["vision-change"]["categories"][1].update(value=1), "dos categorías"),
        (lambda m: m["vision-change"]["categories"][2].update(value=7), "fuera del rango"),
        (lambda m: m["vo2-peak"].update(statements=[]), "ninguna frase"),
        (lambda m: m["vo2-peak"].update(statements=["no-existe"]), "no es una frase"),
        (lambda m: m.update({"heart-rate": copy.deepcopy(m["vo2-peak"])}), "no es un indicador"),
        (lambda m: m["vo2-peak"].update(scope=" "), "scope"),
    ],
)
def test_the_loader_refuses_what_the_source_does_not_write(change: Any, reason: str) -> None:
    raw = _raw()
    change(raw["measures"])
    with pytest.raises(InstrumentsError, match=reason):
        instruments_read.validate(raw)


# --------------------------------------------------------------------------- #
# Invariante 5: el estado no los lee
# --------------------------------------------------------------------------- #


def test_they_are_not_simulated() -> None:
    produced = {
        obs.key
        for scenario in Scenario
        for obs in PhysiologicalSimulator(scenario=scenario).generate(days=2, samples_per_day=2)
    }
    assert not produced & DESCRIPTIVE_ONLY


def test_an_extreme_descriptive_reading_does_not_move_the_verdict(client: TestClient) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 14}
    ).status_code == 201
    before = _verdict(client)
    reference = dt.datetime.fromisoformat(before[3])
    # Dentro de la ventana actual, y después de la referencia: tampoco puede mover el «ahora».
    for offset in (dt.timedelta(hours=-2), dt.timedelta(hours=-1), dt.timedelta(days=3)):
        for key, value in EXTREME.items():
            _post(client, key, value, reference + offset)
    assert _verdict(client) == before
    # Y siguen ahí: firmadas y legibles.
    readings = client.get(
        "/api/observations", params={"subject": "crew-01", "key": "vo2-peak"}
    ).json()
    assert readings["count"] == 3


def test_a_subject_with_only_descriptive_readings_has_no_state_and_is_told_why(
    client: TestClient,
) -> None:
    _post(client, "grip-strength-right", 40.0, dt.datetime(2026, 10, 1, 9, tzinfo=dt.UTC))
    response = client.get("/api/status")
    assert response.status_code == 404
    assert "indicadores descriptivos" in response.json()["detail"]


def test_the_rules_version_does_not_count_them() -> None:
    assert not set(versioning.rules()["catalog"]) & DESCRIPTIVE_ONLY
    assert set(versioning.rules()["catalog"]) == set(CATALOG) - DESCRIPTIVE_ONLY


def test_indicators_lists_them_with_their_system_and_says_they_are_descriptive(
    client: TestClient,
) -> None:
    body = client.get("/api/indicators").json()
    by_key = {item["key"]: item for item in body["indicators"]}
    for key in DESCRIPTIVE_ONLY:
        item = by_key[key]
        assert item["system"] == str(CATALOG[key].system)
        assert item["is_standard_code"] is (CATALOG[key].system is CodeSystem.LOINC)
        assert item["descriptive_only"] is True
        assert item["measurement_cost"] is not None
    assert not any(
        item["descriptive_only"] for key, item in by_key.items() if key not in DESCRIPTIVE_ONLY
    )


def test_what_a_domain_evaluates_leaves_them_out() -> None:
    for domain in Domain:
        evaluated = {code.key for code in evaluated_by_domain(domain)}
        assert evaluated == {code.key for code in by_domain(domain)} - DESCRIPTIVE_ONLY
    for domain in (Domain.NEURO_OCULAR, Domain.BEHAVIORAL, Domain.CARDIOVASCULAR):
        listed = {item["key"] for item in risk_entity.entity(
            domain, {}, risk_entity.severity_schema())["indicators"]}
        assert not listed & DESCRIPTIVE_ONLY


def test_nothing_depends_on_a_descriptive_reading() -> None:
    for key in DESCRIPTIVE_ONLY:
        result = timeline.depends_on(key)
        assert result["affected"] == [] and result["map_errors"] == []


# --------------------------------------------------------------------------- #
# El registro diario: los dos autoinformes, con su instrumento leído
# --------------------------------------------------------------------------- #


def test_the_diary_offers_the_two_self_reports_with_their_instrument(client: TestClient) -> None:
    body = client.get("/api/diary").json()
    by_key = {item["key"]: item for item in body["indicators"]}
    assert {"vision-change", "nasa-tlx-workload", STRESS, *COHESION} <= set(by_key)
    assert not {
        "vo2-peak", "grip-strength-right", "grip-strength-left", "vitamin-d-25oh",
        "bmd-dxa-lumbar-spine", "bmd-dxa-hip", *SENSORIMOTOR_MUSCLE, *COGNITION,
    } & set(by_key)
    for key in ("vision-change", "nasa-tlx-workload", STRESS, *COHESION):
        scale = by_key[key]["scale"]
        assert by_key[key]["descriptive_only"] is True
        assert scale["labels"] is None and scale["design_anchors"] is None
        assert scale["labels_status"] == "instrument"
        if key == STRESS:
            # La fuente escribe sus anclas con número: la nota no puede negarlas.
            assert scale["labels_note"] == diary.SCALE_INSTRUMENT_ANCHORED
        else:
            assert scale["labels_note"].startswith(diary.SCALE_UNLABELLED)
        assert scale["concerning_note"] == diary.DESCRIPTIVE_NOTE
        assert scale["instrument"] == instruments_read.measure(key)
    assert by_key["mood-valence"]["descriptive_only"] is False
    assert by_key["mood-valence"]["scale"]["instrument"] is None


def test_a_diary_entry_of_a_descriptive_indicator_is_signed_and_leaves_the_verdict(
    client: TestClient,
) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 14}
    ).status_code == 201
    before = _verdict(client)
    for key, value in (("vision-change", 3), ("nasa-tlx-workload", 95)):
        response = client.post(
            "/api/diary/entries",
            json={"key": key, "value": value, "subject": "crew-01", "recorded_by": "CDR"},
        )
        assert response.status_code == 201, response.text
        assert response.json()["source"] == diary.DIARY_SOURCE
    assert _verdict(client) == before
    listed = client.get("/api/diary/entries").json()
    entries = listed["entries"]
    assert {entry["key"] for entry in entries} >= {"vision-change", "nasa-tlx-workload"}
    # Ni dentro ni fuera de la ventana del estado: el estado no las lee, y se dice eso.
    for entry in entries:
        assert (entry["position"], entry["position_note"]) == (
            "descriptive", diary.DESCRIPTIVE_NOTE
        )
    # Y la referencia con que se sitúan las demás es la del estado.
    assert listed["reference_time"] == before[3]


def test_a_diary_list_of_only_descriptive_entries_has_no_reference(client: TestClient) -> None:
    assert client.post(
        "/api/diary/entries",
        json={"key": "nasa-tlx-workload", "value": 40, "subject": "crew-01", "recorded_by": "CDR"},
    ).status_code == 201
    listed = client.get("/api/diary/entries").json()
    assert listed["reference_time"] is None
    assert [entry["position"] for entry in listed["entries"]] == ["descriptive"]


def test_no_text_calls_these_scales_validated() -> None:
    texts = [diary.SCALE_INSTRUMENT, diary.DESCRIPTIVE_NOTE]
    for key in DESCRIPTIVE_ONLY:
        measure = instruments_read.measure(key)
        assert measure is not None
        texts += [measure["scope"], measure["numbering"] or "", *measure["not_found"]]
    for text in texts:
        lowered = text.lower()
        assert "validad" not in lowered and "validated" not in lowered, text


# --------------------------------------------------------------------------- #
# El panel: GET /api/indicators/descriptive
# --------------------------------------------------------------------------- #


def test_the_panel_route_says_what_each_one_is_even_without_readings(client: TestClient) -> None:
    response = client.get("/api/indicators/descriptive")
    assert response.status_code == 200
    body = response.json()
    assert body["decided_on"] == "2026-10-15"
    assert body["statement"] == (
        "Sin lecturas de indicadores descriptivos en el registro de crew-01."
    )
    assert body["scope"] == descriptive.SCOPE
    assert [item["key"] for item in body["indicators"]] == [
        key for key in CATALOG if key in DESCRIPTIVE_ONLY
    ]
    for item in body["indicators"]:
        key, code = item["key"], CATALOG[item["key"]]
        assert (item["system"], item["code"], item["unit"]) == (
            str(code.system), code.code, code.unit
        )
        assert item["instrument"] == instruments_read.measure(key)
        assert item["count"] == 0 and item["readings"] == []
        basis = item["code_basis"]
        if code.system is CodeSystem.LOINC:
            assert basis["kind"] == "loinc" and basis["loinc"]["read_on"] == READ_ON[key]
            assert basis["loinc"]["property"] in basis["text"]
        else:
            assert basis["kind"] == "own" and basis["loinc"] is None
            assert basis["searched"] == descriptive.LOINC_SEARCHED[key]
    how = {item["key"]: item["how_recorded"]["route"] for item in body["indicators"]}
    assert how == {
        "vision-change": "/api/diary/entries",
        "nasa-tlx-workload": "/api/diary/entries",
        "vo2-peak": "/api/observations",
        "grip-strength-right": "/api/observations",
        "grip-strength-left": "/api/observations",
        "vitamin-d-25oh": "/api/observations",
        GLUCOSE_CAPILLARY: "/api/observations",
        **dict.fromkeys(URINE, "/api/observations"),
        **dict.fromkeys(DENSITOMETRY, "/api/observations"),
        **dict.fromkeys(SENSORIMOTOR_MUSCLE, "/api/observations"),
        # La batería llega del programa que la pasa; el estrés y la cohesión se anotan.
        **dict.fromkeys(COGNITION, "/api/observations"),
        STRESS: "/api/diary/entries",
        **dict.fromkeys(COHESION, "/api/diary/entries"),
        # Un registro de ingesta se anota en el diario, como la energía.
        **dict.fromkeys(NUTRIENTS, "/api/diary/entries"),
        # Lo que se declara del ciclo se anota en el diario; el test casero y la temperatura
        # basal entran por la ingesta genérica de observaciones (el importador de Apple Health
        # todavía no los lee: es otra unidad del lote).
        "menstrual-flow": "/api/diary/entries",
        "menstruation-start": "/api/diary/entries",
        "intermenstrual-bleeding": "/api/diary/entries",
        "ovulation-test": "/api/observations",
        "contraceptive-in-use": "/api/diary/entries",
        "basal-body-temperature": "/api/observations",
        # El estado reproductivo, la terapia hormonal y los síntomas se declaran en el diario.
        **dict.fromkeys(REPRODUCTIVE, "/api/diary/entries"),
    }
    assert set(DESCRIPTIVE_DECISIONS) == DESCRIPTIVE_ONLY
    decided = {item["key"]: item["decided_on"] for item in body["indicators"]}
    assert decided == DECIDED


def test_the_panel_shows_the_signed_readings_last_first_and_reads_nothing_else(
    client: TestClient,
) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 14}
    ).status_code == 201
    before = _verdict(client)
    reference = dt.datetime.fromisoformat(before[3])
    for hours, value in ((-30, 38.5), (-6, 36.0), (-1, 35.25)):
        _post(client, "vo2-peak", value, reference + dt.timedelta(hours=hours))
    assert client.post(
        "/api/diary/entries",
        json={"key": "vision-change", "value": 1, "subject": "crew-01", "recorded_by": "CDR"},
    ).status_code == 201
    body = client.get("/api/indicators/descriptive", params={"limit": 2}).json()
    by_key = {item["key"]: item for item in body["indicators"]}
    vo2 = by_key["vo2-peak"]
    assert vo2["count"] == 3 and vo2["shown"] == 2
    assert [reading["value"] for reading in vo2["readings"]] == [35.25, 36.0]
    assert vo2["readings"][0]["value_text"] == "35,2 mL/(kg·min)"
    assert vo2["readings"][0]["recorded_by_display"] == diary.NOT_RECORDED
    vision = by_key["vision-change"]["readings"]
    assert [(item["value"], item["recorded_by"]) for item in vision] == [(1.0, "CDR")]
    assert body["statement"] == "4 lecturas de indicadores descriptivos en el registro de crew-01."
    # Servirlo no mueve nada.
    assert _verdict(client) == before


def test_the_fixed_texts_of_the_panel_pass_the_guard() -> None:
    texts = [
        descriptive.SCOPE, descriptive.NO_LOINC, descriptive.HOW_DIARY, descriptive.HOW_INGEST,
        *descriptive.LOINC_SEARCHED.values(), diary.SCALE_INSTRUMENT, diary.DESCRIPTIVE_NOTE,
    ]
    for key in DESCRIPTIVE_ONLY:
        texts.append(descriptive._code_basis(CATALOG[key])["text"])
        measure = instruments_read.measure(key)
        assert measure is not None
        texts += [measure["scope"], *measure["not_found"]]
    for text in texts:
        assert check(text) == [], text


# --------------------------------------------------------------------------- #
# La vitamina D 25-OH (decisión del usuario del 2026-10-22)
# --------------------------------------------------------------------------- #

VITAMIN_D = "vitamin-d-25oh"


def test_vitamin_d_is_the_loinc_code_read_with_the_unit_of_its_property() -> None:
    """Invariantes 1 y 2: 62292-8 es masa por volumen; en nmol/L sería otro código (68438-1)."""
    code, read = CATALOG[VITAMIN_D], DESCRIPTIVE_LOINC[VITAMIN_D]
    assert (code.code, code.system) == ("62292-8", CodeSystem.LOINC)
    assert (read.component, read.property, read.system, read.scale, read.method) == (
        "Calcidiol+ercalcidiol", "MCnc", "Ser/Plas", "Qn", None,
    )
    assert "[Mass/volume]" in code.display and "Serum or Plasma" in code.display
    assert code.unit == read.example_ucum == "ng/mL"
    assert read.read_on == "2026-10-22" and "code=62292-8&" in read.url
    assert code.domain is Domain.BONE
    assert (code.reference_low, code.critical_low, code.critical_high) == (None, None, None)


def test_the_vitamin_d_unit_is_the_one_its_nasa_standard_writes() -> None:
    """La unidad no se supone: la norma médica de NASA la escribe, y la discrepancia se dice."""
    measure = instruments_read.measure(VITAMIN_D)
    assert measure is not None
    quotes = {item["id"]: item for item in measure["statements"]}
    # La norma escribe el analito con unidad de masa: de ahí la propiedad MCnc.
    assert "25-OH Vitamin D" in quotes["mtb013-6037-unit"]["quote"]
    assert "ng/ml" in quotes["mtb013-6037-unit"]["quote"]
    assert quotes["mtb013-6037-unit"]["ref"] == "ochmo-mtb-013"
    # El protocolo de medidas estándar la cuenta entre lo que se analiza en suero.
    assert "serum 25-hydroxyvitamin D" in quotes["ssm-serum-25ohd"]["quote"]
    assert "before, during, and after flight" in quotes["ssm-blood-before-during-after"]["quote"]
    # El experimento de nutrición de la ISS que pidió el plan, con lo que dice y lo que no.
    assert quotes["smo016e-vitd"]["ref"] == "ntrs-20130000839"
    # El mismo laboratorio la escribió en nmol/L: otra propiedad, otro código, y se dice.
    assert "nmol" in quotes["nbl-2006-nmol"]["quote"]
    assert "68438-1" in measure["scope"] and "ng/mL" in measure["scope"]
    assert any("SMO 016E" in line for line in measure["not_found"])


def test_vitamin_d_has_its_name_and_its_cost_like_the_rest() -> None:
    """Paridad: el nombre en español y el coste de medir (la familia va en su propia prueba)."""
    name = spanish_name(VITAMIN_D)
    # No es un analito que lea Polaris: el nombre es de EMMA, y lo dice.
    assert name.origin is NameOrigin.EMMA
    assert name.text == CATALOG[VITAMIN_D].display_es
    assert "25-hidroxivitamina D" in name.text
    measured = cost(VITAMIN_D)
    assert measured is not None
    assert (measured["mode"], measured["equipment"]) == (
        "laboratory", "extracción de sangre y analizador",
    )
    assert measured["dimensions"]["processing"]["value"] == "ground-or-return"
    assert measured["dimensions"]["result"]["value"] == "deferred"


def test_a_vitamin_d_reading_enters_by_the_generic_ingest_and_moves_nothing(
    client: TestClient,
) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 14}
    ).status_code == 201
    before = _verdict(client)
    reference = dt.datetime.fromisoformat(before[3])
    for value in (0.0, 300.0):
        _post(client, VITAMIN_D, value, reference - dt.timedelta(hours=1))
    assert _verdict(client) == before
    body = client.get("/api/indicators/descriptive").json()
    item = next(entry for entry in body["indicators"] if entry["key"] == VITAMIN_D)
    assert item["count"] == 2
    assert {reading["value_text"] for reading in item["readings"]} == {"0,0 ng/mL", "300,0 ng/mL"}
    assert item["code_basis"]["kind"] == "loinc" and "MCnc" in item["code_basis"]["text"]


# --------------------------------------------------------------------------- #
# La glucosa capilar con glucómetro (2026-11-04)
# --------------------------------------------------------------------------- #


def test_capillary_glucose_is_its_own_code_not_the_serum_one() -> None:
    """Invariantes 1 y 2: 41653-7 es sangre capilar por glucómetro, masa por volumen; la glucosa
    de laboratorio (2345-7) es otra muestra y sigue siendo otro indicador, evaluado como antes."""
    code, read = CATALOG[GLUCOSE_CAPILLARY], DESCRIPTIVE_LOINC[GLUCOSE_CAPILLARY]
    assert (code.code, code.system) == ("41653-7", CodeSystem.LOINC)
    assert (read.component, read.property, read.system, read.scale, read.method) == (
        "Glucose", "MCnc", "BldC", "Qn", "Glucometer",
    )
    assert code.display == "Glucose [Mass/volume] in Capillary blood by Glucometer"
    assert code.unit == read.example_ucum == "mg/dL"
    assert read.read_on == "2026-11-04" and "code=41653-7&" in read.url
    assert code.domain is Domain.NUTRITION
    assert (code.reference_low, code.critical_low, code.critical_high) == (None, None, None)
    serum = CATALOG["glucose"]
    assert serum.code == "2345-7" and "Serum or Plasma" in serum.display
    assert "glucose" not in DESCRIPTIVE_ONLY


def test_capillary_glucose_has_its_measure_name_and_cost() -> None:
    measure = instruments_read.measure(GLUCOSE_CAPILLARY)
    assert measure is not None
    refs = {item["ref"] for item in measure["statements"]}
    assert refs == {"cdc-monitoring-blood-sugar", "medlineplus-blood-sugar-test"}
    assert "2345-7" in measure["scope"] and "41653-7" in measure["scope"]
    assert any("ISS" in line for line in measure["not_found"])
    name = spanish_name(GLUCOSE_CAPILLARY)
    assert name.origin is NameOrigin.EMMA and "capilar" in name.text
    measured = cost(GLUCOSE_CAPILLARY)
    assert measured is not None
    assert measured["mode"] == "periodic-invasive"
    assert measured["dimensions"]["processing"]["value"] == "on-device"
    assert measured["dimensions"]["result"]["value"] == "immediate"
    assert measured["dimensions"]["consumables"]["value"] == "consumes"


def test_a_capillary_glucose_reading_moves_nothing(client: TestClient) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 14}
    ).status_code == 201
    before = _verdict(client)
    reference = dt.datetime.fromisoformat(before[3])
    for value in (0.0, 1000.0):
        _post(client, GLUCOSE_CAPILLARY, value, reference - dt.timedelta(hours=1))
    assert _verdict(client) == before
    body = client.get("/api/indicators/descriptive").json()
    item = next(entry for entry in body["indicators"] if entry["key"] == GLUCOSE_CAPILLARY)
    assert item["count"] == 2
    assert {reading["value_text"] for reading in item["readings"]} == {"0 mg/dL", "1000 mg/dL"}


# --------------------------------------------------------------------------- #
# El ciclo menstrual y la anticoncepción (lote «ciclo», unidad A3, 2026-11-14)
# --------------------------------------------------------------------------- #

# Los números de cada categoría, como los decidió EMMA (`numbering`), y los de la temperatura.
CYCLE_CATEGORIES = {
    "menstrual-flow": [0, 1, 2, 3],
    "menstruation-start": [0, 1],
    "intermenstrual-bleeding": [1],
    "ovulation-test": [0, 1, 2],
    "contraceptive-in-use": [1, 2, 3, 4, 5, 6, 7],
}
# El rango de cada escala: el de sus números, y el 0 del sangrado intermenstrual (declarado sin
# manchado), que es de EMMA y no tiene categoría en la fuente.
CYCLE_RANGE = {
    "menstrual-flow": (0, 3),
    "menstruation-start": (0, 1),
    "intermenstrual-bleeding": (0, 1),
    "ovulation-test": (0, 2),
    "contraceptive-in-use": (1, 7),
}
DATA_API_HOSTS = ("https://developer.apple.com/", "https://developer.android.com/")


def test_the_cycle_records_have_their_own_code_scale_and_domain() -> None:
    """Invariantes 1 y 2: código propio con lo buscado escrito; las categorías en `{score}` con el
    rango de sus números, y la temperatura basal en Cel, la unidad de la propiedad Temp."""
    for key in CYCLE:
        code = CATALOG[key]
        assert (code.system, code.code) == (CodeSystem.EMMA, key), key
        assert code.domain is Domain.GENITOURINARY, key
        assert (code.reference_low, code.critical_low, code.critical_high) == (None, None, None)
        assert key not in {item.key for item in evaluated_by_domain(Domain.GENITOURINARY)}
        if key in CYCLE_CATEGORIES:
            assert code.unit == "{score}", key
            assert (code.physical_min, code.physical_max) == CYCLE_RANGE[key], key
    basal = CATALOG["basal-body-temperature"]
    assert basal.unit == CATALOG["body-temperature"].unit == "Cel"
    assert (basal.physical_min, basal.physical_max) == (20, 45)


def test_the_basal_temperature_is_not_filed_under_the_body_temperature_code() -> None:
    """8310-5 casa en propiedad, pero ya es el código de una temperatura que el estado evalúa:
    reutilizarlo juntaría las dos series en una línea base."""
    assert CATALOG["basal-body-temperature"].code != CATALOG["body-temperature"].code == "8310-5"
    assert "basal-body-temperature" in DESCRIPTIVE_ONLY
    assert "body-temperature" not in DESCRIPTIVE_ONLY
    assert "8310-5" in descriptive.LOINC_SEARCHED["basal-body-temperature"]
    measure = instruments_read.measure("basal-body-temperature")
    assert measure is not None and "8310-5" in measure["scope"]
    assert measure["categories"] == [] and measure["numbering"] is None


def test_the_cycle_categories_are_written_in_their_source_and_their_numbers_are_emma() -> None:
    for key, numbers in CYCLE_CATEGORIES.items():
        measure = instruments_read.measure(key)
        assert measure is not None, key
        quotes = {item["id"]: item for item in measure["statements"]}
        assert [item["value"] for item in measure["categories"]] == numbers, key
        for item in measure["categories"]:
            statement = quotes[item["statement"]]
            assert item["literal"] in statement["quote"], key
            # Las palabras de las categorías son las de la documentación de la API de HealthKit.
            assert statement["url"].startswith("https://developer.apple.com/"), key
        assert "de EMMA" in measure["numbering"], key
    # Lo que la fuente no ordena no tiene número, y se dice.
    flow = instruments_read.measure("menstrual-flow")
    ovulation = instruments_read.measure("ovulation-test")
    assert flow is not None and ovulation is not None
    assert "«unspecified»" in flow["numbering"]
    assert all("unspecified" not in item["literal"] for item in flow["categories"])
    assert "«indeterminate»" in ovulation["numbering"]
    assert all("inconclusive" not in item["literal"] for item in ovulation["categories"])


def test_what_health_connect_numbers_differently_is_said() -> None:
    """El 0 de Health Connect en el flujo es «desconocido», no «sin flujo»; y su resultado del test
    de ovulación tiene otros números. Una ingesta que copiara el número lo confundiría."""
    flow = instruments_read.measure("menstrual-flow")
    ovulation = instruments_read.measure("ovulation-test")
    contraceptive = instruments_read.measure("contraceptive-in-use")
    assert flow is not None and ovulation is not None and contraceptive is not None
    assert "FLOW_UNKNOWN" in flow["numbering"] and "no es el 0 de EMMA" in flow["numbering"]
    for name in ("RESULT_NEGATIVE", "RESULT_HIGH", "RESULT_POSITIVE", "RESULT_INCONCLUSIVE"):
        assert name in ovulation["numbering"], name
    assert any("Health Connect no tiene un registro" in line for line in contraceptive["not_found"])
    # El enum de flujo de HealthKit está renombrado desde iOS 18: se dice, no se calla.
    assert any("HKCategoryValueVaginalBleeding" in line for line in flow["not_found"])


def test_the_contraceptive_is_nominal_and_does_not_claim_to_be_hormonal() -> None:
    measure = instruments_read.measure("contraceptive-in-use")
    assert measure is not None
    assert "NOMINAL" in measure["numbering"] and "No hay 0" in measure["numbering"]
    assert "no dice si el anticonceptivo es hormonal" in measure["scope"]
    # Las existencias de a bordo van en el inventario firmado, no en este indicador.
    assert "inventario firmado" in measure["scope"]
    assert "8659-5" in measure["scope"] and "8659-5" in descriptive.LOINC_SEARCHED[
        "contraceptive-in-use"
    ]


def test_the_cycle_sources_are_the_data_apis_and_a_public_health_page() -> None:
    urls = set()
    for key in CYCLE:
        measure = instruments_read.measure(key)
        assert measure is not None, key
        urls |= {item["url"] for item in measure["statements"]}
        name = spanish_name(key)
        assert name.origin is NameOrigin.EMMA and name.text == CATALOG[key].display_es, key
        assert cost(key) is not None, key
    assert all(
        url.startswith(DATA_API_HOSTS) or url == "https://medlineplus.gov/ency/article/007062.htm"
        for url in urls
    ), urls
    # La muestra del test de ovulación es orina: lo dice la fuente, y el modo lo sigue.
    measured = cost("ovulation-test")
    assert measured is not None and measured["mode"] == "periodic-invasive"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        # Una medida que no es del ciclo cita la documentación de una API.
        (lambda raw: raw["measures"]["vo2-peak"]["statements"].append("cycle-hk-flow-none"),
         "solo vale para las medidas del ciclo"),
        # La PVT la cita como contexto.
        (lambda raw: raw["pvt"]["context"].append("cycle-hk-basal"), "fuera de las medidas"),
    ],
)
def test_the_data_api_documentation_only_backs_the_cycle_measures(change: Any, reason: str) -> None:
    raw = _raw()
    change(raw)
    with pytest.raises(InstrumentsError, match=reason):
        instruments_read.validate(raw)


def test_the_diary_offers_the_declared_cycle_records_with_their_categories(
    client: TestClient,
) -> None:
    body = client.get("/api/diary").json()
    by_key = {item["key"]: item for item in body["indicators"]}
    declared = ("menstrual-flow", "menstruation-start", "intermenstrual-bleeding",
                "contraceptive-in-use")
    assert set(declared) <= set(by_key)
    assert not {"ovulation-test", "basal-body-temperature"} & set(by_key)
    for key in declared:
        scale = by_key[key]["scale"]
        assert by_key[key]["descriptive_only"] is True
        assert scale["labels_status"] == "instrument"
        assert scale["instrument"] == instruments_read.measure(key)


def test_cycle_readings_are_signed_and_move_nothing(client: TestClient) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 14}
    ).status_code == 201
    before = _verdict(client)
    reference = dt.datetime.fromisoformat(before[3])
    for key in CYCLE:
        _post(client, key, EXTREME[key], reference - dt.timedelta(hours=1))
    _post(client, "basal-body-temperature", 36.55, reference - dt.timedelta(hours=2))
    assert _verdict(client) == before
    body = client.get("/api/indicators/descriptive").json()
    by_key = {item["key"]: item for item in body["indicators"]}
    basal = by_key["basal-body-temperature"]
    assert [reading["value_text"] for reading in basal["readings"]] == ["45,00 °C", "36,55 °C"]
    assert by_key["menstrual-flow"]["readings"][0]["value_text"] == "3 puntos"
    for key in CYCLE:
        assert by_key[key]["decided_on"] == "2026-11-14", key
        assert by_key[key]["code_basis"]["kind"] == "own", key
    # Un valor fuera de la escala no es un dato: se rechaza en la frontera.
    for key, value in (("menstrual-flow", 4.0), ("contraceptive-in-use", 0.0),
                       ("basal-body-temperature", 50.0)):
        response = client.post(
            "/api/observations",
            json={"key": key, "value": value, "subject": "crew-01",
                  "effective": reference.isoformat()},
        )
        assert response.status_code == 422, (key, response.text)


# --------------------------------------------------------------------------- #
# El estado reproductivo, la terapia hormonal de la menopausia y los síntomas vasomotores (lote
# «ciclo», unidad C2, 2026-11-15)
# --------------------------------------------------------------------------- #

# Los números de cada categoría, como los decidió EMMA (`numbering`).
REPRODUCTIVE_CATEGORIES = {
    "reproductive-status": [1, 2, 3, 4, 5, 6],
    "menopausal-hormone-therapy": [1],
    "hot-flashes": [0, 1, 2, 3],
    "night-sweats": [0, 1, 2, 3],
}
# El rango de cada escala: el de sus números, y el 0 de la terapia (declarada sin ella), que es de
# EMMA y no tiene categoría en la fuente.
REPRODUCTIVE_RANGE = {
    "reproductive-status": (1, 6),
    "menopausal-hormone-therapy": (0, 1),
    "hot-flashes": (0, 3),
    "night-sweats": (0, 3),
}
STRAW10 = "https://pmc.ncbi.nlm.nih.gov/articles/PMC3340903/"
JAIN = "https://pmc.ncbi.nlm.nih.gov/articles/PMC5516549/"
HORMONE_THERAPY_PAGE = "https://medlineplus.gov/ency/patientinstructions/000695.htm"


def test_the_reproductive_records_have_their_own_code_scale_and_domain() -> None:
    """Invariantes 1 y 2: código propio con lo buscado escrito, y escalas de puntos con el rango
    de sus números. No evalúan: el dominio los agrupa, no los cuenta."""
    for key in REPRODUCTIVE:
        code = CATALOG[key]
        assert (code.system, code.code) == (CodeSystem.EMMA, key), key
        assert code.domain is Domain.GENITOURINARY, key
        assert code.unit == "{score}", key
        assert (code.physical_min, code.physical_max) == REPRODUCTIVE_RANGE[key], key
        assert (code.reference_low, code.critical_low, code.critical_high) == (None, None, None)
        assert key not in {item.key for item in evaluated_by_domain(Domain.GENITOURINARY)}
        assert DESCRIPTIVE_DECISIONS[key] == "2026-11-15", key


def test_the_reproductive_categories_are_written_in_their_source_and_numbered_by_emma() -> None:
    for key, numbers in REPRODUCTIVE_CATEGORIES.items():
        measure = instruments_read.measure(key)
        assert measure is not None, key
        quotes = {item["id"]: item for item in measure["statements"]}
        assert [item["value"] for item in measure["categories"]] == numbers, key
        for item in measure["categories"]:
            assert item["literal"] in quotes[item["statement"]]["quote"], key
        assert "de EMMA" in measure["numbering"], key
        assert check(measure["numbering"]) == [], key
    # Las gravedades de los síntomas son las palabras de HealthKit; «unspecified» no tiene número.
    for key in ("hot-flashes", "night-sweats"):
        measure = instruments_read.measure(key)
        assert measure is not None
        quotes = {item["id"]: item for item in measure["statements"]}
        for item in measure["categories"]:
            assert quotes[item["statement"]]["url"].startswith("https://developer.apple.com/")
        assert "«unspecified»" in measure["numbering"]
        assert all("not specified" not in item["literal"] for item in measure["categories"])


def test_the_reproductive_status_is_nominal_and_says_which_value_is_a_regular_cycle() -> None:
    """Lo que leerá la línea base consciente de la fase (B3): solo el 1 es un ciclo regular."""
    measure = instruments_read.measure("reproductive-status")
    assert measure is not None
    assert "NOMINAL" in measure["numbering"]
    assert "Solo el 1 dice que hay un ciclo regular que seguir" in measure["numbering"]
    assert REGULAR_CYCLE_STATUS == 1
    (regular,) = [item for item in measure["categories"] if item["value"] == REGULAR_CYCLE_STATUS]
    assert regular["literal"] == "menstrual cycles remain regular"
    # Cada categoría sale de lo leído: STRAW+10, la supresión menstrual en astronautas y HealthKit.
    quotes = {item["id"]: item for item in measure["statements"]}
    sources = {item["value"]: quotes[item["statement"]]["url"] for item in measure["categories"]}
    # Ninguna categoría sale de la documentación de una API: esa solo dice qué valores da la fuente.
    assert sources[1] == sources[2] == sources[4] == sources[5] == sources[6] == STRAW10
    assert sources[3] == JAIN
    # Del estado menopáusico de HealthKit: «perimenopause» es el 4, «menopause» el 5 y «none» no
    # tiene número, porque no dice cuál de los otros es.
    numbering = measure["numbering"]
    assert "«perimenopause» es el 4 y «menopause» el 5" in numbering
    assert "«none»" in numbering and "no tiene número" in numbering
    # No es el sexo declarado, y lo dice.
    assert "no es el sexo declarado" in measure["scope"]
    assert "EMMA no estadifica" in measure["scope"]


def test_the_hormone_therapy_is_not_the_contraceptive_and_is_not_suggested() -> None:
    measure = instruments_read.measure("menopausal-hormone-therapy")
    assert measure is not None
    assert {item["url"] for item in measure["statements"]} == {HORMONE_THERAPY_PAGE}
    scope = measure["scope"]
    assert "No es el anticonceptivo en uso" in scope
    assert "inventario firmado" in scope
    assert "EMMA no valora la terapia: solo registra lo declarado" in scope
    assert check(scope) == []
    assert "98134-0" in scope and "98134-0" in descriptive.LOINC_SEARCHED[
        "menopausal-hormone-therapy"
    ]
    # Con la pauta cíclica puede haber un sangrado mensual que no es la regla de un ciclo propio.
    assert "sangrado mensual" in scope


def test_the_hormone_therapy_cannot_cite_the_data_api_documentation() -> None:
    """Ninguna de las dos API registra la terapia: su documentación no puede sostenerla."""
    raw = _raw()
    raw["measures"]["menopausal-hormone-therapy"]["statements"].append("vaso-hk-severity")
    with pytest.raises(InstrumentsError, match="solo vale para las medidas del ciclo"):
        instruments_read.validate(raw)


def test_health_connect_has_none_of_the_four_and_it_is_said() -> None:
    for key in REPRODUCTIVE:
        measure = instruments_read.measure(key)
        assert measure is not None
        assert any("Health Connect no tiene" in line for line in measure["not_found"]), key


def test_the_diary_offers_the_reproductive_records_with_their_categories(
    client: TestClient,
) -> None:
    body = client.get("/api/diary").json()
    by_key = {item["key"]: item for item in body["indicators"]}
    assert set(REPRODUCTIVE) <= set(by_key)
    for key in REPRODUCTIVE:
        scale = by_key[key]["scale"]
        assert by_key[key]["descriptive_only"] is True
        assert scale["labels_status"] == "instrument"
        assert scale["instrument"] == instruments_read.measure(key)


def test_reproductive_readings_are_signed_and_move_nothing(client: TestClient) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 14}
    ).status_code == 201
    before = _verdict(client)
    reference = dt.datetime.fromisoformat(before[3])
    for key in REPRODUCTIVE:
        _post(client, key, EXTREME[key], reference - dt.timedelta(hours=1))
    assert _verdict(client) == before
    body = client.get("/api/indicators/descriptive").json()
    by_key = {item["key"]: item for item in body["indicators"]}
    assert by_key["reproductive-status"]["readings"][0]["value_text"] == "6 puntos"
    for key in REPRODUCTIVE:
        assert by_key[key]["decided_on"] == "2026-11-15", key
        assert by_key[key]["code_basis"]["kind"] == "own", key
    # Un valor fuera de la escala no es un dato: se rechaza en la frontera.
    for key, value in (("reproductive-status", 0.0), ("reproductive-status", 7.0),
                       ("menopausal-hormone-therapy", 2.0), ("hot-flashes", 4.0),
                       ("night-sweats", -1.0)):
        response = client.post(
            "/api/observations",
            json={"key": key, "value": value, "subject": "crew-01",
                  "effective": reference.isoformat()},
        )
        assert response.status_code == 422, (key, response.text)


# --------------------------------------------------------------------------- #
# La química de la orina de 24 horas del riesgo de cálculos renales (decisión del usuario del
# 2026-10-26)
# --------------------------------------------------------------------------- #

# Lo leído de cada ficha el 2026-10-26: código, componente, propiedad, escala, unidad de ejemplo y
# la unidad con que lo registra EMMA. Si alguien cambia uno, tiene que hacerlo aquí, con la ficha.
URINE_READ = {
    "urine-calcium-24h": ("6874-2", "Calcium", "MRat", "Qn", "mg/(24.h)", "mg/(24.h)"),
    "urine-oxalate-24h": ("2701-1", "Oxalate", "MRat", "Qn", "mg/(24.h)", "mg/(24.h)"),
    "urine-urate-24h": ("3087-4", "Urate", "MRat", "Qn", "g/(24.h)", "mg/(24.h)"),
    "urine-citrate-24h": ("6687-8", "Citrate", "MRat", "Qn", "mg/(24.h)", "mg/(24.h)"),
    "urine-ph-24h": ("27378-9", "pH", "LsCnc", "SemiQn", "[pH]", "[pH]"),
    "urine-sodium-24h": ("2956-1", "Sodium", "SRat", "Qn", "mmol/(24.h)", "mmol/(24.h)"),
    "urine-osmolality-24h": ("2694-8", "Observation", "Osmol", "Qn", "mosm/kg", "mosm/kg"),
}
# El código de la otra propiedad, leído y descartado: lo nombra lo leído de la medida.
OTHER_PROPERTY = {
    "urine-calcium-24h": "14637-3",
    "urine-oxalate-24h": "14862-7",
    "urine-urate-24h": "14935-1",
    "urine-citrate-24h": "14650-6",
    "urine-ph-24h": "2756-5",
    "urine-sodium-24h": "21527-7",
    "urine-osmolality-24h": "2695-5",
}


def test_the_urine_codes_are_the_ones_read_with_the_unit_of_their_property() -> None:
    """Invariantes 1 y 2: cada código, de la orina de 24 horas, con la unidad de su propiedad."""
    assert set(RENAL_URINE_LOINC) == set(URINE_READ)
    for key, (code_id, component, prop, scale, example, unit) in URINE_READ.items():
        code, read = CATALOG[key], RENAL_URINE_LOINC[key]
        assert DESCRIPTIVE_LOINC[key] is read, key
        assert (code.code, code.system, code.unit) == (code_id, CodeSystem.LOINC, unit), key
        assert (read.component, read.property, read.system, read.scale, read.method) == (
            component, prop, "Urine", scale, None,
        ), key
        assert read.example_ucum == example, key
        assert "24 hour Urine" in code.display, key
        assert code.domain is Domain.GENITOURINARY, key
        assert (code.reference_low, code.critical_low, code.critical_high) == (None, None, None)
    # El urato es la única unidad que no es la de ejemplo: la misma propiedad, en mg y no en g.
    differs = {key for key, row in URINE_READ.items() if row[4] != row[5]}
    assert differs == {"urine-urate-24h"}


def test_the_supersaturation_is_an_own_code_that_says_what_was_searched() -> None:
    code = CATALOG["urine-caox-supersaturation-24h"]
    assert (code.system, code.unit) == (CodeSystem.EMMA, "1")
    assert "Calcium oxalate" in code.display and "24 hour urine" in code.display
    searched = descriptive.LOINC_SEARCHED["urine-caox-supersaturation-24h"]
    for read_code in ("81232-1", "42673-4", "81623-1", "34736-9"):
        assert read_code in searched, read_code
    assert check(searched) == []


def test_the_urine_measures_cite_what_the_report_writes() -> None:
    """La unidad no se supone: el informe escribe la calciuria, el oxalato y el citrato en mg al
    día, y la medida dice el código de la otra propiedad, que EMMA no tiene."""
    for key in URINE:
        measure = instruments_read.measure(key)
        assert measure is not None, key
        refs = {item["ref"] for item in measure["statements"]}
        assert "hrp-renal-stone-evidence-report" in refs, key
        if key in OTHER_PROPERTY:
            assert OTHER_PROPERTY[key] in measure["scope"], key
            assert CATALOG[key].code in measure["scope"], key
    quotes = {
        item["id"]: item["quote"]
        for key in URINE
        for item in (instruments_read.measure(key) or {})["statements"]
    }
    assert ">300mg/day" in quotes["renal-hypercalciuria-mg-day"]
    assert "45mg/day" in quotes["renal-oxalate-mg-day"]
    assert "mg a day" in quotes["renal-citrate-mg-day"]
    assert "24h urine collection" in quotes["renal-rsri-24h-annual"]
    assert "post-flight" in quotes["renal-assessment-postflight"]
    assert "calcium oxalate supersaturation" in quotes["renal-iss-supersaturation"]


def test_the_urine_analytes_have_their_name_family_cost_and_category() -> None:
    """Paridad con los demás descriptivos: nombre de EMMA, coste de laboratorio en Tierra."""
    for key in URINE:
        name = spanish_name(key)
        assert name.origin is NameOrigin.EMMA, key
        assert "orina de 24 horas" in name.text, key
        measured = cost(key)
        assert measured is not None, key
        assert measured["mode"] == "laboratory", key
        assert measured["dimensions"]["processing"]["value"] == "ground-or-return", key
        assert measured["dimensions"]["result"]["value"] == "deferred", key
        assert measured["dimensions"]["processing"]["rule"] == "perfil-litiasico-en-tierra"


def test_a_urine_reading_enters_moves_nothing_and_keeps_its_unit(client: TestClient) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 14}
    ).status_code == 201
    before = _verdict(client)
    reference = dt.datetime.fromisoformat(before[3])
    for key in URINE:
        _post(client, key, EXTREME[key], reference - dt.timedelta(hours=1))
    # Con la unidad de la otra propiedad no entra: la ingesta no convierte.
    refused = client.post(
        "/api/observations",
        json={
            "key": "urine-calcium-24h", "value": 7.5, "unit": "mmol/(24.h)",
            "subject": "crew-01", "effective": reference.isoformat(),
        },
    )
    assert refused.status_code == 422
    assert _verdict(client) == before
    body = client.get("/api/indicators/descriptive").json()
    by_key = {item["key"]: item for item in body["indicators"]}
    assert by_key["urine-calcium-24h"]["readings"][0]["value_text"] == "2000 mg/día"
    assert by_key["urine-ph-24h"]["readings"][0]["value_text"] == "0,00 pH"
    assert by_key["urine-sodium-24h"]["readings"][0]["value_text"] == "1000 mmol/día"
    assert by_key["urine-osmolality-24h"]["readings"][0]["value_text"] == "2000 mOsm/kg"
    assert by_key["urine-caox-supersaturation-24h"]["code_basis"]["kind"] == "own"


# --------------------------------------------------------------------------- #
# Sensoriomotor y músculo (decimonovena ronda, 2026-10-31): dos pruebas funcionales de Standard
# Measures y dos medidas de músculo, las cuatro con código propio y su instrumento leído
# --------------------------------------------------------------------------- #

# Clave → (unidad, extremo vigilado, un código LOINC que se buscó y se descartó, nombrado en lo
# buscado).
SM_READ = {
    "tandem-walk-correct-steps": ("%", "low", "66045-6"),
    "recovery-from-fall-time": ("s", "high", "91553-8"),
    "dxa-lean-mass": ("kg", "low", "91557-9"),
    "imtp-peak-force": ("N", "low", "LA29117-1"),
}


def test_sensorimotor_and_muscle_are_own_codes_with_their_unit_and_what_was_searched() -> None:
    """Invariantes 1 y 2: ninguna tiene LOINC, cada una dice qué se buscó, y la unidad es la de
    la magnitud (un porcentaje, segundos, kilogramos de masa, newtons de fuerza)."""
    for key, (unit, concerning, searched_code) in SM_READ.items():
        code = CATALOG[key]
        assert (code.system, code.code, code.unit) == (CodeSystem.EMMA, key, unit), key
        assert code.domain is Domain.MUSCULOSKELETAL and code.concerning == concerning, key
        assert (code.reference_low, code.reference_high) == (None, None), key
        assert (code.critical_low, code.critical_high) == (None, None), key
        searched = descriptive.LOINC_SEARCHED[key]
        assert "2026-10-31" in searched and searched_code in searched, key
        assert check(searched) == []
    # La fuerza de la tracción es fuerza, no masa: en newtons, no en kilos ni en kgf.
    assert CATALOG["imtp-peak-force"].unit in FORCE_UNITS
    assert CATALOG["imtp-peak-force"].unit not in {"kg", "kgf"}
    # La masa magra es una masa: en kilogramos, como el peso.
    assert CATALOG["dxa-lean-mass"].unit == CATALOG["body-weight"].unit == "kg"


def test_the_sensorimotor_and_muscle_measures_cite_what_standard_measures_writes() -> None:
    """La medida de cada una está escrita en la fuente: el porcentaje de pasos correctos, el tiempo
    hasta la postura estable, la masa magra de la composición corporal y la fuerza máxima en la
    plataforma; y lo que la fuente no escribe (la unidad) se dice en «no encontrado»."""
    quotes: dict[str, dict[str, Any]] = {}
    refs: dict[str, set[str]] = {}
    for key in SM_READ:
        measure = instruments_read.measure(key)
        assert measure is not None, key
        refs[key] = {item["ref"] for item in measure["statements"]}
        quotes.update({item["id"]: item for item in measure["statements"]})
        assert "hardy-2025-spaceflight-standard-measures" in refs[key], key
    assert "hrp-sensorimotor-evidence-report" in refs["tandem-walk-correct-steps"]
    assert "hrp-sensorimotor-evidence-report" in refs["recovery-from-fall-time"]
    assert "hrp-muscle-aerobic-evidence-report" in refs["dxa-lean-mass"]
    assert "hrp-muscle-aerobic-evidence-report" in refs["imtp-peak-force"]
    assert "percent of correct steps" in quotes["ssm-tandem-percent"]["quote"]
    assert "10 heel-to-toe steps" in quotes["ssm-tandem-ten-steps"]["quote"]
    assert "achievement of a stable posture" in quotes["ssm-rff-measure"]["quote"]
    assert "Body composition (bone, fat, lean" in quotes["ssm-table1-dxa-body-composition"]["quote"]
    assert quotes["ssm-table1-dxa-body-composition"]["quote"].endswith("Pre/Post")
    assert "peak force production using a force plate" in quotes["ssm-imtp-force-plate"]["quote"]
    assert quotes["ssm-table2-imtp"]["quote"].endswith("Pre/In/Post")
    assert "advanced resistance exercise device" in quotes["ssm-imtp-inflight-ared"]["quote"]
    # La salvedad del informe de 2023 sobre la masa magra del cuerpo entero va con la medida.
    assert "whole body lean mass" in quotes["ma2023-whole-body-lean-caveat"]["quote"]
    for key in ("recovery-from-fall-time", "dxa-lean-mass", "imtp-peak-force"):
        measure = instruments_read.measure(key)
        assert measure is not None
        assert any("unidad" in line for line in measure["not_found"]), key
    # La posturografía se buscó y no entra: su puntuación no está escrita en lo leído.
    tandem = instruments_read.measure("tandem-walk-correct-steps")
    assert tandem is not None
    assert any("posturografía" in line for line in tandem["not_found"])
    # Y lo leído de estas medidas se leyó el día de la decisión.
    for key in SM_READ:
        measure = instruments_read.measure(key)
        assert measure is not None
        assert {item["read_on"] for item in measure["statements"]} == {"2026-10-31"}, key


def test_sensorimotor_and_muscle_have_their_name_and_cost_like_the_rest() -> None:
    """Paridad: nombre de EMMA y coste de medir; la masa magra se procesa en Tierra por su regla
    leída, y las tres pruebas sin muestra llevan el matiz de Standard Measures en su regla."""
    words = {
        "tandem-walk-correct-steps": "tándem",
        "recovery-from-fall-time": "tumbado",
        "dxa-lean-mass": "magra",
        "imtp-peak-force": "Tracción isométrica",
    }
    for key, word in words.items():
        name = spanish_name(key)
        assert name.origin is NameOrigin.EMMA and word in name.text, key
        assert cost(key) is not None, key
    lean, hip = cost("dxa-lean-mass"), cost("bmd-dxa-hip")
    assert lean is not None and hip is not None
    assert lean["mode"] == "laboratory" and lean["equipment"] == hip["equipment"]
    assert lean["dimensions"]["processing"]["value"] == "ground-or-return"
    assert lean["dimensions"]["processing"]["rule"] == "composicion-corporal-dxa-en-tierra"
    assert lean["dimensions"]["result"]["value"] == "unclassified"
    for key in ("tandem-walk-correct-steps", "recovery-from-fall-time", "imtp-peak-force"):
        measured = cost(key)
        assert measured is not None
        assert measured["mode"] == "periodic-noninvasive", key
    for key in ("recovery-from-fall-time", "imtp-peak-force"):
        measured = cost(key)
        assert measured is not None
        assert measured["dimensions"]["result"]["rule"] == "sin-muestra-periodico", key
    # Los pasos correctos los cuentan tres revisores después: ni «inmediato» ni «en el propio
    # dispositivo», y dónde se revisa el vídeo lo leído no lo dice.
    tandem = cost("tandem-walk-correct-steps")
    assert tandem is not None
    assert tandem["dimensions"]["result"]["value"] == "deferred"
    assert tandem["dimensions"]["result"]["rule"] == "marcha-en-tandem-puntuada-sobre-video"
    assert tandem["dimensions"]["processing"]["value"] == "unclassified"
    rules = {
        rule["id"]: rule
        for rule in json.loads(COST_PATH.read_text(encoding="utf-8"))["dimension_rules"]
    }
    discrepant = {
        item["quote"] for item in rules["sin-muestra-periodico"]["discrepancies"]
        if item["ref"] == "hardy-2025-spaceflight-standard-measures"
    }
    assert not any("Three reviewers" in quote for quote in discrepant)
    assert any("IMU data" in quote for quote in discrepant)
    video = rules["marcha-en-tandem-puntuada-sobre-video"]
    assert any("Three reviewers" in item["quote"] for item in video["sources"])


def test_a_sensorimotor_or_muscle_reading_enters_moves_nothing_and_keeps_its_unit(
    client: TestClient,
) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 14}
    ).status_code == 201
    before = _verdict(client)
    reference = dt.datetime.fromisoformat(before[3])
    for key in SM_READ:
        _post(client, key, EXTREME[key], reference - dt.timedelta(hours=1))
    # La fuerza en kilogramos-fuerza (la unidad de la prensión) no entra: la ingesta no convierte.
    refused = client.post(
        "/api/observations",
        json={
            "key": "imtp-peak-force", "value": 180.0, "unit": "kgf",
            "subject": "crew-01", "effective": reference.isoformat(),
        },
    )
    assert refused.status_code == 422
    assert _verdict(client) == before
    body = client.get("/api/indicators/descriptive").json()
    by_key = {item["key"]: item for item in body["indicators"]}
    assert by_key["tandem-walk-correct-steps"]["readings"][0]["value_text"] == "0 %"
    assert by_key["recovery-from-fall-time"]["readings"][0]["value_text"] == "1800,0 s"
    assert by_key["dxa-lean-mass"]["readings"][0]["value_text"] == "10,0 kg"
    assert by_key["imtp-peak-force"]["readings"][0]["value_text"] == "1 N"
    for key in SM_READ:
        assert by_key[key]["code_basis"]["kind"] == "own", key
        assert by_key[key]["code_basis"]["searched"] == descriptive.LOINC_SEARCHED[key], key
        assert by_key[key]["decided_on"] == "2026-10-31", key


# --------------------------------------------------------------------------- #
# Equipo, estrés y cognición (decimonovena ronda, U14, 2026-10-31)
# --------------------------------------------------------------------------- #


def _quotes(key: str) -> dict[str, str]:
    measure = instruments_read.measure(key)
    assert measure is not None, key
    return {item["id"]: item["quote"] for item in measure["statements"]}


def test_the_cognition_battery_enters_with_the_measures_its_source_publishes() -> None:
    """Nueve pruebas, no diez: la PVT ya tiene sus indicadores. De cada una, la velocidad en ms y,
    salvo la MPT, una proporción de 0 a 1 (en la BART, el riesgo): lo que Dev et al. 2024 define."""
    assert set(COGNITION) == COGNITION_KEYS
    assert [test.sigla for test in COGNITION_TESTS] == [
        "MPT", "VOLT", "F2B", "AM", "LOT", "ERT", "MRT", "DSST", "BART",
    ]
    assert not any("pvt" in key for key in COGNITION_KEYS)
    assert "pvt-mean-rt" not in DESCRIPTIVE_ONLY and "pvt-lapses" not in DESCRIPTIVE_ONLY
    for key in COGNITION:
        code = CATALOG[key]
        assert code.domain is Domain.BEHAVIORAL and code.category is ObservationCategory.SURVEY
        assert "Cognition test battery" in code.display
        if key.endswith("-speed"):
            assert (code.unit, code.concerning) == ("ms", "high"), key
            assert (code.physical_min, code.physical_max) == (1, 60000), key
            assert "average response time" in code.display
        else:
            assert (code.unit, code.physical_min, code.physical_max) == ("1", 0, 1), key
            assert code.concerning == ("both" if key == "cognition-bart-risk" else "low"), key
    # Lo que cada medida cita: la frase que la define, en el idioma de la fuente.
    quotes = _quotes("cognition-dsst-speed")
    assert "average response time (in milliseconds)" in quotes["cog-speed-definition"]
    assert "proportion correct to total stimuli" in _quotes("cognition-dsst-accuracy")[
        "cog-accuracy-proportion"
    ]
    assert "correct rejection" in _quotes("cognition-f2b-accuracy")["cog-f2b-accuracy"]
    lot = _quotes("cognition-lot-accuracy")["cog-lot-accuracy"]
    assert "off from the correct orientation" in lot
    assert "Scores range from 0 to 1" in _quotes("cognition-bart-risk")["cog-bart-risk"]
    assert "No accuracy score was calculated for the MPT" in _quotes("cognition-mpt-speed")[
        "cog-mpt-no-accuracy"
    ]
    for key in COGNITION:
        quotes = _quotes(key)
        refs = {item["ref"] for item in (instruments_read.measure(key) or {})["statements"]}
        assert {
            "dev-2024-cognition-iss", "basner-2015-cognition-battery",
            "hardy-2025-spaceflight-standard-measures", "hrp-bmed-evidence-report",
        } <= refs, key
        assert "15 unique forms of 10 neuropsychological" in quotes["basner-15-forms-10-tests"]
        assert "340 days" in quotes["cog-twins-study"]
        sigla = CATALOG[key].display.split("(")[1].split(")")[0]
        assert f"({sigla})" in quotes[f"cog-test-{key.split('-')[1]}"], key


def test_the_cognition_costs_come_from_the_administration_times_read() -> None:
    """El tiempo de tripulación de cada prueba es la mediana de la Tabla I de Basner et al. 2015; la
    batería corre en un portátil y no gasta material, y por eso no se anota en el diario."""
    medians = {"mpt": 0.4, "volt": 1.7, "f2b": 2.0, "am": 1.8, "lot": 1.2, "ert": 1.7, "mrt": 2.1,
               "dsst": 1.6, "bart": 2.1}
    for key in COGNITION:
        measured = cost(key)
        assert measured is not None, key
        assert measured["equipment"] == "batería Cognition en ordenador portátil"
        assert measured["crew_time_minutes"] == medians[key.split("-")[1]], key
        assert "Basner et al. 2015, Tabla I" in measured["crew_time_basis"]
        assert measured["dimensions"]["consumables"]["value"] == "none", key
        assert measured["dimensions"]["consumables"]["rule"] == "bateria-cognitiva-en-portatil"
    assert not set(COGNITION) & set(diary.diary_keys())


def test_the_stress_scale_carries_the_anchors_its_source_writes_and_fatigue_stays_out() -> None:
    """El estrés del Reaction Self Test: 0 a 100 con las anclas del pie de la figura 1 (Jones et al.
    2022), que aquí son de la fuente y no de EMMA. La fatiga mental, sin anclas leídas, no entra."""
    code = CATALOG[STRESS]
    assert (code.unit, code.physical_min, code.physical_max, code.concerning) == (
        "{score}", 0, 100, "high",
    )
    measure = instruments_read.measure(STRESS)
    assert measure is not None
    quotes = {item["id"]: item["quote"] for item in measure["statements"]}
    assert "VAS anchors: 100 = very stressed; 0 = not stressed" in quotes["rst-stress-anchors"]
    assert [(item["value"], item["literal"]) for item in measure["categories"]] == [
        (0, "not stressed"), (100, "very stressed"),
    ]
    assert measure["numbering"] is not None and "son de la fuente" in measure["numbering"]
    assert "mental fatigue" in quotes["rst-vas-domains"]
    assert "stress level, and fatigue" in quotes["ssm-sleep-survey-items"]
    assert any("fatiga no entra" in line for line in measure["not_found"])
    assert any("Karolinska" in line and "Samn-Perelli" in line for line in measure["not_found"])
    # Ningún indicador de fatiga, somnolencia ni cansancio: no se leyó su instrumento.
    for word in ("fatigue", "sleepiness", "tiredness", "karolinska", "samn"):
        assert not any(word in key or word in CATALOG[key].display.lower() for key in CATALOG), word
    assert cost(STRESS) is not None and cost(STRESS)["equipment"] == "autoinforme"  # type: ignore[index]


def test_the_cohesion_items_are_the_three_statements_of_the_end_of_day_survey() -> None:
    """Una afirmación por indicador, tal como la escribe la Tabla 3 de Hardy et al. 2025, de 1 a 7;
    ningún agregado de las tres, porque la fuente no dice cómo se hace."""
    assert set(COHESION) == TEAM_COHESION_KEYS
    table = _quotes(COHESION[0])["ssm-eod-cohesion-items"]
    for key in COHESION:
        code = CATALOG[key]
        statement = TEAM_COHESION_STATEMENT[key]
        assert statement in table, key
        assert statement in code.display and statement in code.display_es, key
        assert (code.unit, code.physical_min, code.physical_max, code.concerning) == (
            "{score}", 1, 7, "low",
        )
        quotes = _quotes(key)
        assert "a scale from 1 to 7" in quotes["ssm-eod-scale"]
        assert "team cohesion, team performance, group living" in quotes["team-ssm-measures"]
        assert "task cohesion (working together well)" in quotes["team-cohesion-two-factors"]
        measure = instruments_read.measure(key)
        assert measure is not None and measure["categories"] == []
        assert any("anclas del 1 y del 7" in line for line in measure["not_found"])
    assert not any("team-cohesion" in key and key not in COHESION for key in CATALOG)


def test_the_behavioral_instruments_are_signed_and_leave_the_verdict(client: TestClient) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 14}
    ).status_code == 201
    before = _verdict(client)
    reference = dt.datetime.fromisoformat(before[3])
    for key in COGNITION:
        _post(client, key, EXTREME[key], reference - dt.timedelta(hours=1))
    for key, value in ((STRESS, 100), *((key, 1) for key in COHESION)):
        response = client.post(
            "/api/diary/entries",
            json={"key": key, "value": value, "subject": "crew-01", "recorded_by": "CDR"},
        )
        assert response.status_code == 201, response.text
    # Fuera del rango del instrumento no entra: el 8 no es un punto de la escala de 1 a 7.
    assert client.post(
        "/api/observations",
        json={"key": COHESION[0], "value": 8, "subject": "crew-01",
              "effective": reference.isoformat()},
    ).status_code == 422
    assert _verdict(client) == before
    body = client.get("/api/indicators/descriptive").json()
    by_key = {item["key"]: item for item in body["indicators"]}
    # El millar se agrupa con el espacio fino de F.5.6, como en el resto de EMMA.
    assert by_key["cognition-dsst-speed"]["readings"][0]["value_text"] == "60 000 ms"
    assert by_key["cognition-bart-risk"]["readings"][0]["value_text"] == "1,00"
    assert by_key[STRESS]["readings"][0]["value_text"] == "100 puntos"
    assert by_key[COHESION[0]]["readings"][0]["recorded_by"] == "CDR"
    assert by_key[STRESS]["instrument"]["categories"][1]["literal"] == "very stressed"
