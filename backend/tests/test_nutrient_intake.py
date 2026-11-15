"""Nutrientes ingeridos al día, descriptivos (decimonovena ronda, U15, 2026-10-31).

La base de conocimiento §5 pide registrar la «composición nutricional» y la «ingesta real»; EMMA
solo tenía la energía diaria. Entran el sodio, el calcio, la proteína y la vitamina D ingeridos al
día, con las reglas de todo descriptivo (`test_descriptive_indicators.py` las comprueba sobre el
conjunto). Lo que se fija aquí es lo propio de estos cuatro:

- invariantes 1 y 2: los dos códigos LOINC son los de 24 horas y SIN método, con la unidad de su
  propiedad (masa por tiempo); los dos propios dicen lo buscado y por qué no hay código que
  adoptar sin inventar el método o cambiar la unidad;
- solo entran con fuente leída: la norma (Vol. 1 [V1 4020], Vol. 2 [V2 7100] y su Tabla 7.1-2),
  el resumen técnico de la pérdida ósea ([6038]) y Standard Measures; sin rango, porque lo que
  la norma fija se calcula por persona y EMMA no lo calcula, y la única cifra (la vitamina D) se
  cita en su frase;
- son un registro de ingesta: se anotan en el diario, no llevan categoría FHIR y su coste es el
  del registro de ingesta; y nada de esto mueve el estado ni la versión de las reglas.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import descriptive, diary
from app.api.routes import new_store, reset_store
from app.core import display, versioning
from app.core.config import Settings, get_settings
from app.evidence import instruments_read
from app.ingest.codes import (
    CATALOG,
    DESCRIPTIVE_DECISIONS,
    DESCRIPTIVE_LOINC,
    DESCRIPTIVE_ONLY,
    NO_LOINC_AVAILABLE,
    NUTRIENT_INTAKE_LOINC,
    NUTRIENT_INTAKES,
    CodeSystem,
    Domain,
    NoCategory,
)
from app.ingest.cost import cost
from app.ingest.fhir import category_of, observation
from app.ingest.names_es import NameOrigin, spanish_name
from app.main import app
from app.text_guard import check

KEYS = ("sodium-intake-daily", "calcium-intake-daily", "protein-intake-daily",
        "vitamin-d-intake-daily")
# Lo leído de cada ficha el 2026-10-31 en tx.fhir.org (LOINC 2.83): código, componente, propiedad,
# unidad de ejemplo. Si alguien cambia uno, tiene que hacerlo aquí, con la ficha.
LOINC_READ = {
    "calcium-intake-daily": ("35264-1", "Calcium intake", "MRat", "mg/(24.h)"),
    "protein-intake-daily": ("9085-2", "Protein intake", "MRat", "g/(24.h)"),
}
# Los códigos leídos y descartados, que lo buscado tiene que nombrar.
DISCARDED = {
    # La misma medida en sustancia por tiempo (SRat), otra propiedad.
    "calcium-intake-daily": ("9051-4",),
    # El sin método es de sustancia; los de masa llevan método.
    "sodium-intake-daily": ("9092-8", "81011-9", "81012-7"),
    # Solo existen con método.
    "vitamin-d-intake-daily": ("81929-2", "81930-0"),
}
T = dt.datetime(2026, 10, 1, 12, tzinfo=dt.UTC)


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _verdict(client: TestClient) -> tuple[Any, ...]:
    status = client.get("/api/status").json()
    return (
        status["overall_level"],
        {key: (item["level"], item["score"]) for key, item in status["domains"].items()},
        [(item["id"], item["level"]) for item in status["alerts"]],
        status["data"]["reference_time"],
        status["data"]["observations"],
        status["rules_version"],
    )


# --------------------------------------------------------------------------- #
# Invariantes 1 y 2: el código y la unidad
# --------------------------------------------------------------------------- #


def test_the_four_nutrients_are_descriptive_intake_records_of_the_nutrition_domain() -> None:
    assert tuple(code.key for code in NUTRIENT_INTAKES) == KEYS
    for key in KEYS:
        code = CATALOG[key]
        assert key in DESCRIPTIVE_ONLY and DESCRIPTIVE_DECISIONS[key] == "2026-10-31", key
        assert code.domain is Domain.NUTRITION and code.concerning == "low", key
        # Sin rango ni límite: lo que la norma fija se calcula por persona y EMMA no lo calcula.
        assert (code.reference_low, code.reference_high) == (None, None), key
        assert (code.critical_low, code.critical_high) == (None, None), key
        assert code.physical_min == 0 and code.physical_max is not None, key
        # Un registro de lo que se come, como la energía: sin categoría FHIR, y el recurso valida.
        assert code.category is NoCategory.NONE_FITS and category_of(code) is None, key
        reading = observation(key, 1.0, T, "crew-01", "manual")
        assert "category" not in reading.to_fhir() and reading.validates(), key


def test_the_loinc_codes_are_the_24_hour_ones_without_method_in_their_mass_unit() -> None:
    """Invariantes 1 y 2: 24H y no Pt (el 9052-2 de la energía); MRat; sin método."""
    assert set(NUTRIENT_INTAKE_LOINC) == set(LOINC_READ)
    for key, (code_id, component, prop, unit) in LOINC_READ.items():
        code, read = CATALOG[key], NUTRIENT_INTAKE_LOINC[key]
        assert DESCRIPTIVE_LOINC[key] is read, key
        assert (code.code, code.system, code.unit) == (code_id, CodeSystem.LOINC, unit), key
        assert (read.component, read.property, read.system, read.scale) == (
            component, prop, "^Patient", "Qn",
        ), key
        assert read.method is None and read.example_ucum == unit, key
        assert read.version == "2.83" and read.read_on == "2026-10-31", key
        assert f"code={code_id}&" in read.url, key
        assert code.display == f"{component} 24 hour", key


def test_the_own_codes_say_what_was_searched_and_why_nothing_fits() -> None:
    for key in ("sodium-intake-daily", "vitamin-d-intake-daily"):
        code = CATALOG[key]
        assert (code.system, code.code) == (CodeSystem.EMMA, key), key
        assert key in NO_LOINC_AVAILABLE, key
        searched = descriptive.LOINC_SEARCHED[key]
        for discarded in DISCARDED[key]:
            assert discarded in searched, (key, discarded)
        assert "2026-10-31" in searched and "método" in searched
        assert check(searched) == []
    # El sodio en masa (mg al día) y la vitamina D en microgramos al día, como la Tabla 7.1-2.
    assert CATALOG["sodium-intake-daily"].unit == "mg/d"
    assert CATALOG["vitamin-d-intake-daily"].unit == "ug/d"
    assert "moles" in descriptive.LOINC_SEARCHED["sodium-intake-daily"]
    assert "Tabla 7.1-2" in descriptive.LOINC_SEARCHED["vitamin-d-intake-daily"]


def test_the_units_read_per_day_and_the_decimals_are_declared() -> None:
    assert display.unit("mg/d") == "mg/día"
    assert display.unit("ug/d") == "µg/día"
    assert display.unit("g/(24.h)") == "g/día"
    assert display.unit("mg/(24.h)") == "mg/día"
    assert [display.decimals_for(key) for key in KEYS] == [0, 0, 0, 1]
    assert display.quantity("vitamin-d-intake-daily", 12.5, "ug/d") == "12,5 µg/día"
    assert display.quantity("protein-intake-daily", 85.0, "g/(24.h)") == "85 g/día"


# --------------------------------------------------------------------------- #
# Solo con fuente leída
# --------------------------------------------------------------------------- #


def test_each_nutrient_cites_the_standard_the_brief_and_standard_measures() -> None:
    for key in KEYS:
        measure = instruments_read.measure(key)
        assert measure is not None, key
        by_id = {item["id"]: item for item in measure["statements"]}
        assert {"v1-4020-nutrient-intake", "v2-7100-dri", "mtb013-6038-dietary-assessment",
                "ssm-table2-dietary-questionnaire"} <= set(by_id), key
        for item in by_id.values():
            assert item["read_on"] == "2026-10-31", (key, item["id"])
        # Lo que la norma fija se calcula por persona: la frase lo escribe.
        assert "age, sex, body mass (kg), height (m)" in by_id["v1-4020-nutrient-intake"]["quote"]
        assert "Dietary Reference Intake (DRI)" in by_id["v2-7100-dri"]["quote"]
        assert "On-orbit dietary assessments" in by_id["mtb013-6038-dietary-assessment"]["quote"]
        assert "dietary assessment questionnaire" in (
            by_id["ssm-table2-dietary-questionnaire"]["quote"]
        )
        # Y la medida dice que no sabe si la cifra se pesa o se estima: por eso sin método.
        assert any("se pesa o se estima" in line for line in measure["not_found"]), key
        assert "no convierte" in measure["scope"], key
    # La única cifra de la tabla es la de la vitamina D, en microgramos, y se cita en su frase.
    vitamin_d = instruments_read.measure("vitamin-d-intake-daily")
    assert vitamin_d is not None
    quotes = {item["id"]: item["quote"] for item in vitamin_d["statements"]}
    assert "Vitamin D 25 µg (micrograms)" in quotes["v2-table-7-1-2-vitamin-d"]
    assert "only expressed in metric units" in quotes["v2-table-7-1-2-vitamin-d"]
    for key in ("sodium-intake-daily", "calcium-intake-daily", "protein-intake-daily"):
        measure = instruments_read.measure(key)
        assert measure is not None
        assert "v2-table-7-1-2-vitamin-d" not in {item["id"] for item in measure["statements"]}


def test_a_nutrient_measure_without_its_sentence_is_refused() -> None:
    import copy
    import json

    raw = json.loads(instruments_read.READ_PATH.read_text(encoding="utf-8"))
    broken = copy.deepcopy(raw)
    broken["measures"]["sodium-intake-daily"]["statements"] = ["no-leida"]
    with pytest.raises(instruments_read.InstrumentsError, match="no es una frase leída"):
        instruments_read.validate(broken)
    without = copy.deepcopy(raw)
    del without["measures"]["protein-intake-daily"]
    with pytest.raises(instruments_read.InstrumentsError, match="sin medida leída"):
        instruments_read.validate(without)


# --------------------------------------------------------------------------- #
# Un registro de ingesta: diario, nombre, coste, familia
# --------------------------------------------------------------------------- #


def test_they_have_a_emma_name_and_the_cost_of_the_intake_record() -> None:
    for key in KEYS:
        name = spanish_name(key)
        assert name.origin is NameOrigin.EMMA, key
        assert "ingerid" in name.text, key
        measured = cost(key)
        assert measured is not None, key
        assert (measured["mode"], measured["equipment"]) == (
            "periodic-noninvasive", "registro de ingesta",
        ), key
        # La misma regla de las dimensiones que la energía: una anotación en la consola.
        energy = cost("energy-intake-daily")
        assert energy is not None
        assert measured["dimensions"] == energy["dimensions"], key
    assert set(KEYS) <= set(diary.diary_keys())


def test_the_diary_offers_them_as_descriptive_and_signs_them(client: TestClient) -> None:
    body = client.get("/api/diary").json()
    by_key = {item["key"]: item for item in body["indicators"]}
    for key in KEYS:
        assert by_key[key]["descriptive_only"] is True, key
        assert by_key[key]["scale"] is None and by_key[key]["food_item"] is None, key
        assert by_key[key]["equipment"] == "registro de ingesta", key
    for key, value in zip(KEYS, (2300.0, 1000.0, 85.0, 12.5), strict=True):
        response = client.post(
            "/api/diary/entries",
            json={"key": key, "value": value, "subject": "crew-01", "recorded_by": "CDR"},
        )
        assert response.status_code == 201, response.text
    entries = client.get("/api/diary/entries").json()["entries"]
    assert {item["key"] for item in entries} == set(KEYS)
    assert all(item["position"] == "descriptive" for item in entries)
    texts = {item["key"]: item["value_text"] for item in entries}
    # Cuatro cifras no llevan separador de millares en el backend (`display.number`).
    assert texts == {
        "sodium-intake-daily": "2300 mg/día",
        "calcium-intake-daily": "1000 mg/día",
        "protein-intake-daily": "85 g/día",
        "vitamin-d-intake-daily": "12,5 µg/día",
    }


# --------------------------------------------------------------------------- #
# Invariante 5: el estado no los lee
# --------------------------------------------------------------------------- #


def test_extreme_intakes_move_nothing_and_the_panel_shows_them(client: TestClient) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "menu-fatigue", "days": 14}
    ).status_code == 201
    before = _verdict(client)
    reference = dt.datetime.fromisoformat(before[3])
    for key in KEYS:
        # El tope, después: la lectura más reciente es la primera de `readings`.
        for hours, value in ((2, 0.0), (1, CATALOG[key].physical_max)):
            response = client.post(
                "/api/observations",
                json={
                    "key": key, "value": value, "subject": "crew-01",
                    "effective": (reference - dt.timedelta(hours=hours)).isoformat(),
                },
            )
            assert response.status_code == 201, response.text
    # Con la unidad de otra propiedad no entra: la ingesta no convierte.
    refused = client.post(
        "/api/observations",
        json={"key": "calcium-intake-daily", "value": 25.0, "unit": "mmol/(24.h)",
              "subject": "crew-01", "effective": reference.isoformat()},
    )
    assert refused.status_code == 422
    assert _verdict(client) == before
    assert before[5] == versioning.rules_version()
    assert not set(versioning.rules()["catalog"]) & set(KEYS)
    body = client.get("/api/indicators/descriptive").json()
    by_key = {item["key"]: item for item in body["indicators"]}
    assert by_key["calcium-intake-daily"]["code_basis"]["kind"] == "loinc"
    assert "MRat" in by_key["calcium-intake-daily"]["code_basis"]["text"]
    assert by_key["sodium-intake-daily"]["code_basis"]["kind"] == "own"
    assert by_key["sodium-intake-daily"]["count"] == 2
    assert by_key["vitamin-d-intake-daily"]["readings"][0]["value_text"] == "1000,0 µg/día"
    assert by_key["sodium-intake-daily"]["readings"][0]["value_text"] == "20 000 mg/día"
    assert by_key["sodium-intake-daily"]["how_recorded"]["route"] == "/api/diary/entries"


def test_the_nutrition_domain_still_evaluates_what_it_evaluated() -> None:
    from app.ingest.codes import evaluated_by_domain

    assert {code.key for code in evaluated_by_domain(Domain.NUTRITION)} == {
        "energy-intake-daily", "food-acceptability", "appetite-rating", "food-rejected-fraction",
        "glucose", "total-protein", "albumin", "ast", "alt", "ggt", "alkaline-phosphatase",
        "bilirubin-total", "bilirubin-direct", "ldh", "tsh", "free-t4",
    }
