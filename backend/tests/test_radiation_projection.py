"""Radiación: proyección al fin de misión, horquilla por tipo y límites a corto plazo (C7).

Decimocuarta ronda: la dosis de misión proyectada al fin configurado es PREDICHA y no alimenta
`cumulative_dose_msv` ni ningún nivel; la horquilla usa los Q de atrapada y GCR medidos con TEPC
en el SLS-1, con su ficha; los límites de 30 días y 1 año de NASA-STD-3001 Vol 1 se muestran en
su unidad (mGy-Eq o mGy), sin convertir. Base de conocimiento §7; `analysis/radiation.py`.
"""

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import radiation
from app.analysis.radiation import mission_projection, scales, short_term_limits
from app.api import routes
from app.environment.dosimetry import MEAN_QUALITY_FACTORS, QualityFactorModel
from app.evidence import registry
from app.ingest.fhir import observation
from app.text_guard import check

START = dt.date(2026, 11, 1)
T0 = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)


def _rates(hours: int, value: float, start: dt.datetime = T0) -> list[Any]:
    return [
        observation("absorbed-dose-rate", value, start + dt.timedelta(hours=h), "crew-01", "d")
        for h in range(hours + 1)
    ]


def _project(rates: list[Any], *, days: int = 10, prior: float | None = None) -> dict[str, Any]:
    result = mission_projection(
        rates, mission_start=START, mission_days=days, prior_career_msv=prior, limit_msv=600.0
    )
    assert result is not None
    return result


def _texts(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [text for value in node.values() for text in _texts(value)]
    if isinstance(node, list):
        return [text for value in node for text in _texts(value)]
    return []


# --------------------------------------------------------------------------- #
# La proyección
# --------------------------------------------------------------------------- #


def test_the_projection_extends_the_mean_rate_to_the_configured_end() -> None:
    # 10 µGy/h durante el primer día de una misión de 10: 2 400 µGy absorbidos al final.
    projected = _project(_rates(24, 10.0), days=10)
    assert projected["observation_type"] == "predicted"
    assert projected["model_version"] == radiation.PROJECTION_MODEL
    assert projected["mission_end"] == "2026-11-11" and projected["end_day"] == 10
    assert projected["remaining_days"] == pytest.approx(9.0)
    assert projected["absorbed_mgy"] == pytest.approx(2.4)
    assert projected["value_msv"] == pytest.approx(2.4 * 2.38, abs=1e-3)
    assert projected["rate_ugy_per_h"] == pytest.approx(10.0)
    # Lo que supone, dicho: tasa constante, sin eventos solares.
    assert "supone tasa constante: no prevé eventos solares" in projected["basis"]
    assert "no entra en la dosis acumulada" in projected["scope"]


def test_the_range_by_radiation_type_uses_the_sls1_quality_factors_and_is_inferred() -> None:
    projected = _project(_rates(24, 10.0), days=10)
    by_type = projected["by_type"]
    trapped = MEAN_QUALITY_FACTORS[QualityFactorModel.TRAPPED].value
    cosmic = MEAN_QUALITY_FACTORS[QualityFactorModel.GALACTIC_COSMIC].value
    assert (trapped, cosmic) == (1.83, 2.74)
    assert by_type["low_msv"] == pytest.approx(2.4 * trapped, abs=1e-3)
    assert by_type["high_msv"] == pytest.approx(2.4 * cosmic, abs=1e-3)
    assert by_type["low_msv"] < projected["value_msv"] < by_type["high_msv"]
    assert by_type["observation_type"] == "inferred"
    assert "no es un intervalo de confianza" in by_type["basis"]
    # La fuente es la ficha leída, no una cadena: con su PMID y su salvedad de alcance.
    assert by_type["source"]["id"] == "badhwar-1992-sls1-tepc"
    card = registry.get("badhwar-1992-sls1-tepc")
    assert card.pmid == "11537535"
    assert card.notes is not None
    for literal in (
        "1.83 +/- 0.1", "2.74 +/- 0.1", "overall quality factor for the flight was 2.38",
    ):
        assert literal in card.notes


def test_after_the_configured_end_there_is_nothing_to_project() -> None:
    ended = _project(_rates(24, 10.0, T0 + dt.timedelta(days=12)), days=10)
    assert ended["value_msv"] is None
    assert "terminó el día 10" in ended["basis"]
    assert "by_type" not in ended and "career" not in ended


def test_without_a_mission_dose_there_is_no_projection() -> None:
    assert mission_projection(
        _rates(0, 10.0), mission_start=START, mission_days=10, prior_career_msv=None,
        limit_msv=600.0,
    ) is None


def test_the_projected_career_needs_a_declared_prior_dose_and_never_assumes_zero() -> None:
    unknown = _project(_rates(24, 10.0), days=10)["career"]
    assert unknown["value_msv"] is None and "no se supone cero" in unknown["basis"]
    known = _project(_rates(24, 10.0), days=10, prior=100.0)
    career = known["career"]
    assert career["value_msv"] == pytest.approx(100.0 + known["value_msv"])
    assert career["fraction"] == pytest.approx(career["value_msv"] / 600.0, abs=1e-4)
    assert career["limit_source"] == "NASA-STD-3001 [V1 4030]"


def test_the_days_before_the_first_rate_reading_are_said_not_extrapolated() -> None:
    late = _project(_rates(24, 10.0, T0 + dt.timedelta(days=3)), days=10)
    # Del día 3 al 10 a 10 µGy/h: 7 días, 1 680 µGy. Los tres primeros no se inventan.
    assert late["absorbed_mgy"] == pytest.approx(1.68)
    assert "no cuenta los 3 días anteriores a la primera lectura de tasa" in late["basis"]
    assert "anteriores a la primera lectura" not in _project(_rates(24, 10.0))["basis"]


def test_without_a_positive_limit_there_is_no_career_fraction() -> None:
    projected = mission_projection(
        _rates(24, 10.0), mission_start=START, mission_days=10, prior_career_msv=100.0,
        limit_msv=0.0,
    )
    assert projected is not None and projected["career"]["fraction"] is None
    mission = radiation.mission_dose(_rates(24, 10.0), START)
    plain = scales(active_event=None, event_time=None, now=T0, mission=mission,
                   prior_career_msv=100.0, limit_msv=0.0)
    assert plain["career"]["fraction"] is None


def test_every_flight_quality_factor_names_the_card_the_range_cites() -> None:
    for model in (QualityFactorModel.MISSION_AVERAGE, QualityFactorModel.TRAPPED,
                  QualityFactorModel.GALACTIC_COSMIC):
        assert MEAN_QUALITY_FACTORS[model].ref_id == "badhwar-1992-sls1-tepc"
    assert MEAN_QUALITY_FACTORS[QualityFactorModel.UNIT].ref_id is None
    assert radiation.TEPC_SOURCE.id == "badhwar-1992-sls1-tepc"
    mission = radiation.mission_dose(_rates(24, 10.0), START)
    assert mission is not None and mission["quality_ref"] == "badhwar-1992-sls1-tepc"


def test_the_projection_does_not_change_the_mission_or_the_career_scales() -> None:
    rates = _rates(24, 10.0)
    mission = radiation.mission_dose(rates, START)
    plain = scales(active_event=None, event_time=None, now=T0, mission=mission,
                   prior_career_msv=100.0, limit_msv=600.0)
    projected = _project(rates, days=10, prior=100.0)
    with_projection = scales(active_event=None, event_time=None, now=T0, mission=mission,
                             prior_career_msv=100.0, limit_msv=600.0, projection=projected)
    assert with_projection["mission"] == plain["mission"]
    assert with_projection["career"] == plain["career"]
    assert with_projection["projection"] is projected


# --------------------------------------------------------------------------- #
# Los límites a corto plazo
# --------------------------------------------------------------------------- #


def test_the_short_term_limits_are_table_4_8_1_in_its_own_units() -> None:
    table = short_term_limits()
    rows = {row["organ"]: row for row in table["rows"]}
    assert list(rows) == [
        "Lens", "Skin", "Blood-forming Organs", "Circulatory System",
        "Central Nervous System", "Central Nervous System (Z≥10)",
    ]
    assert rows["Lens"]["thirty_day"] == {
        "value": 1000.0, "unit": "mGy-Eq", "absent": None, "literal": None,
    }
    assert rows["Lens"]["one_year"]["value"] == 2000.0
    assert rows["Skin"]["thirty_day"]["value"] == 1500.0
    assert rows["Blood-forming Organs"]["one_year"] == {
        "value": 500.0, "unit": "mGy-Eq", "absent": None, "literal": None,
    }
    assert rows["Blood-forming Organs"]["career"]["value"] is None
    assert rows["Blood-forming Organs"]["career"]["absent"] == "no aplica"
    assert rows["Blood-forming Organs"]["career"]["literal"] == "Not applicable"
    assert rows["Lens"]["unit"] == "mGy-Eq" and rows["Central Nervous System"]["unit"] == "mGy"
    assert rows["Circulatory System"]["thirty_day"]["value"] == 250.0
    # El sistema nervioso central va en mGy, no en mGy-Eq; y sin cifra de 30 días con Z ≥ 10.
    assert rows["Central Nervous System"]["thirty_day"] == {
        "value": 500.0, "unit": "mGy", "absent": None, "literal": None,
    }
    assert rows["Central Nervous System (Z≥10)"]["thirty_day"]["value"] is None
    assert rows["Central Nervous System (Z≥10)"]["thirty_day"]["literal"] == "-"
    assert rows["Central Nervous System (Z≥10)"]["one_year"]["value"] == 100.0
    # Ninguna casilla en mSv: la unidad de la norma, sin convertir, y lo dice.
    units = {cell["unit"] for row in table["rows"]
             for cell in (row["thirty_day"], row["one_year"], row["career"])}
    assert units == {"mGy-Eq", "mGy", None}
    assert "no se convierten" in table["units"]
    assert "no les compara ninguna cifra suya" in table["scope"]
    assert table["source"]["id"] == "nasa-std-3001-vol1-rev-c"
    assert "Tabla 4.8-1" in table["source"]["relevance"]


def test_what_the_radiation_block_writes_passes_the_language_guard() -> None:
    projected = _project(_rates(24, 10.0), days=10, prior=100.0)
    ended = _project(_rates(24, 10.0, T0 + dt.timedelta(days=12)), days=10)
    texts = [*_texts(projected), *_texts(ended), *_texts(short_term_limits())]
    # «dosis» a secas es la dosis de radiación, no una de fármaco: el filtro la caza siempre
    # (categoría `dosing`), y la escala de radiación la escribe desde la segunda ronda. Todo lo
    # demás —órdenes, certezas, diagnósticos, dosis con vía o pauta— sí tiene que pasar.
    found = [
        (text, finding) for text in texts for finding in check(text)
        if (finding.category, finding.match.lower()) != ("dosing", "dosis")
    ]
    assert found == []


# --------------------------------------------------------------------------- #
# Por la API: se ve, y no alimenta la dosis acumulada ni ningún nivel
# --------------------------------------------------------------------------- #


def test_status_serves_the_projection_and_the_limits(client: TestClient) -> None:
    client.post("/api/simulate", params={"days": 10})
    radiation_block = client.get("/api/status").json()["radiation"]
    projected = radiation_block["projection"]
    assert projected["observation_type"] == "predicted"
    assert projected["value_msv"] > radiation_block["mission"]["value_msv"]
    assert projected["by_type"]["source"]["id"] == "badhwar-1992-sls1-tepc"
    assert len(radiation_block["short_term_limits"]["rows"]) == 6


def test_the_projection_never_feeds_the_cumulative_dose_or_any_level(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.post("/api/simulate", params={"scenario": "spe-event", "days": 10})
    client.post("/api/crew/profile", json={
        "prior_missions": 1, "prior_career_dose_msv": 120.0, "declared_by": "CDR",
    })
    before = client.get("/api/status").json()
    real = routes.mission_projection

    def enormous(*args: Any, **kwargs: Any) -> dict[str, Any] | None:
        result = real(*args, **kwargs)
        assert result is not None
        return {**result, "value_msv": 1e6, "career": {**result["career"], "value_msv": 1e6}}

    monkeypatch.setattr(routes, "mission_projection", enormous)
    after = client.get("/api/status").json()
    assert after["radiation"]["projection"]["value_msv"] == 1e6
    # Lo que decide no se movió: dosis acumulada, dominios, nivel global, alertas y reglas.
    for key in ("dose", "domains", "overall_level", "rules_version"):
        assert after[key] == before[key], key
    assert [alert["level"] for alert in after["alerts"]] == [
        alert["level"] for alert in before["alerts"]
    ]
    assert after["radiation"]["mission"] == before["radiation"]["mission"]
    assert after["radiation"]["career"] == before["radiation"]["career"]
