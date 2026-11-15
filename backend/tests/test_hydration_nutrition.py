"""Hidratación, nutrición y modo anatómico (especificación del equipo §9, §10; KB H7).

Los códigos LOINC nuevos se leyeron en su ficha (2026-09-26) y llevan la unidad de su
propiedad (invariante 2). La fatiga de menú es una hipótesis: se proyecta, no alerta.
"""

from fastapi.testclient import TestClient

from app import anatomy
from app.ingest.codes import CATALOG, CodeSystem, Domain, ReferenceBasis
from app.ingest.simulator import DAILY_KEYS, DAILY_REPORT_HOUR, PhysiologicalSimulator, Scenario


def test_the_new_loinc_codes_carry_the_unit_of_their_property() -> None:
    expected = {
        "fluid-intake-24h": ("9108-2", "mL/(24.h)"),  # VRat:24H
        "urine-volume-24h": ("3167-4", "mL"),  # Vol:24H
        "urine-specific-gravity": ("2965-2", "1"),  # SpGrav, adimensional
    }
    for key, (code, unit) in expected.items():
        item = CATALOG[key]
        assert (item.system, item.code, item.unit) == (CodeSystem.LOINC, code, unit)


def test_guidelines_never_become_alarm_thresholds() -> None:
    for key in ("fluid-intake-24h", "food-acceptability"):
        assert CATALOG[key].reference_basis is ReferenceBasis.GUIDELINE
    for key in DAILY_KEYS:
        assert CATALOG[key].critical_low is None and CATALOG[key].critical_high is None


def test_daily_totals_are_reported_once_a_day() -> None:
    readings = list(PhysiologicalSimulator(Scenario.DEHYDRATION).generate(days=5))
    daily = [item for item in readings if item.key in DAILY_KEYS]
    assert daily
    assert {item.effective.hour for item in daily} == {DAILY_REPORT_HOUR}
    assert len([item for item in daily if item.key == "urine-volume-24h"]) == 5


def test_daily_totals_are_once_a_day_at_any_sampling_rate() -> None:
    # `POST /api/simulate` admite de 1 a 96 muestras al día. Con 96, la hora 7 tiene cuatro
    # pasos y el total diario salía cuatro veces; con 1, 2 o 5 ningún paso caía en la hora 7 y
    # el escenario de deshidratación se quedaba sin un solo dato de orina.
    for samples_per_day in (1, 2, 5, 24, 48, 96):
        readings = list(
            PhysiologicalSimulator(Scenario.DEHYDRATION).generate(
                days=3, samples_per_day=samples_per_day
            )
        )
        urine = [item for item in readings if item.key == "urine-volume-24h"]
        assert len(urine) == 3, samples_per_day
        assert {(item.effective.hour, item.effective.minute) for item in urine} == {
            (DAILY_REPORT_HOUR, 0)
        }, samples_per_day


def test_the_nominal_scenario_does_not_invent_hydration_or_food_data() -> None:
    keys = {item.key for item in PhysiologicalSimulator(Scenario.NOMINAL).generate(days=2)}
    assert not keys & DAILY_KEYS


def test_dehydration_is_detected_and_offers_the_hydration_countermeasure_first(
    client: TestClient,
) -> None:
    client.post("/api/simulate", params={"scenario": "dehydration", "days": 40})
    status = client.get("/api/status").json()
    assert status["domains"]["genitourinary"]["level"] != "nominal"
    first = next(item for item in status["recommendations"] if item["domain"] == "genitourinary")
    assert first["countermeasure"]["id"] == "gu-hydration-target"


def test_menu_fatigue_is_projected_as_a_hypothesis_without_an_alarm(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "menu-fatigue", "days": 40})
    status = client.get("/api/status").json()
    assert status["domains"]["nutrition"]["level"] == "nominal"
    projected = {item["key"] for item in status["predictions"]}
    assert "food-acceptability" in projected


def test_every_domain_has_a_region_of_the_body(client: TestClient) -> None:
    covered = {domain for region in anatomy.REGIONS for domain in region.domains}
    assert covered == set(Domain)
    body = client.get("/api/anatomy").json()
    assert {item["key"] for item in body["regions"]} == {item.key for item in anatomy.REGIONS}


def test_inspiration4_recovery_is_measured_against_each_crews_own_preflight(
    client: TestClient,
) -> None:
    assert client.post("/api/replay/inspiration4").status_code == 201
    body = client.get("/api/replay/recovery", params={"subject": "crew-01"}).json()
    lymphocytes = next(item for item in body["indicators"] if item["key"] == "lymphocytes")
    assert lymphocytes["preflight"]["samples"] >= 2
    days = [item["days_after_landing"] for item in lymphocytes["postflight"]]
    assert days == sorted(days) and days[0] <= 1
    assert "no es un veredicto" in body["basis"]


def test_every_indicator_declares_what_it_costs_to_measure() -> None:
    from app.ingest.cost import MODES, costs

    assert set(costs()) == set(CATALOG)
    for key, item in costs().items():
        assert item["mode"] in MODES, key
        if item["crew_time_minutes"] is not None:
            assert item["crew_time_basis"] != "sin fuente", key


def test_the_cost_is_published_with_each_indicator(client: TestClient) -> None:
    body = client.get("/api/indicators").json()
    assert all(item["measurement_cost"] for item in body["indicators"])


def test_a_cost_entry_without_its_basis_is_refused() -> None:
    import pytest

    from app.ingest.cost import validate

    good = {"mode": "laboratory", "equipment": "x", "crew_time_minutes": None,
            "crew_time_basis": "sin fuente"}
    assert validate({"k": good})
    with pytest.raises(ValueError, match="sin fuente"):
        validate({"k": {**good, "crew_time_minutes": 10}})
    with pytest.raises(ValueError, match="clase"):
        validate({"k": {**good, "mode": "guessed"}})
