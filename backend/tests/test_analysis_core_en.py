"""El núcleo del análisis en inglés: las palabras de nivel y las frases de `app/analysis/`.

La interfaz enseña lo que redacta el backend (invariante 7), así que el inglés de un nivel, de
una desviación o de una tendencia se decide aquí (`core/i18n.py`). Estas pruebas piden el texto
en inglés —con la fixture `english` o con la cabecera— y comprueban cuatro cosas: que sale en
inglés y con punto decimal, que la frase castellana no se cuela, que lo que no es texto (claves,
estados, niveles, cifras) es idéntico en los dos idiomas, y que quien no pide idioma recibe el
castellano de siempre. El castellano exacto lo fijan las pruebas de cada módulo; aquí se compara
la respuesta sin cabecera con la pedida en castellano.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import (
    baseline_profile,
    cycle_phase,
    data_quality,
    densitometry,
    episode,
    exercise_summary,
    explain,
    forecast_check,
    inferred,
    recovery,
    recovery_state,
    staleness,
    wording,
)
from app.analysis.baseline import Baseline, BaselineEngine, Deviation, Severity, SeverityBasis
from app.analysis.risk import DomainRisk, RiskEngine, RiskLevel
from app.analysis.trend import Direction, Trend, linear_trend, projection
from app.api import cycle_phase as cycle_gate
from app.core import i18n
from app.core.mission import MissionPhase
from app.ingest.codes import BMD_DXA_HIP, Domain
from app.ingest.fhir import Context, ObservationType, VitalObservation, observation
from tests.conftest import ENGLISH_HEADERS

NOW = dt.datetime(2026, 11, 14, 8, 0, tzinfo=dt.UTC)
DAY = dt.timedelta(days=1)

# Lo que delata una frase castellana que se ha colado en una respuesta en inglés.
SPANISH = re.compile(
    r"[áéíóúñ¿¡]|\b(de|del|la|las|los|el|una|con|sin|por|para|que|hay|lecturas?|límite|"
    r"línea|según|días|semanas?|tomas?|prevuelo|posvuelo|encima|debajo|dentro|fuera)\b",
    re.IGNORECASE,
)
# Lo que el inglés no puede decir: una orden médica, una certeza o una certificación.
FORBIDDEN = re.compile(
    r"\b(certified|validated|diagnos\w*|confirms?|definitely|guaranteed|administer|must be)\b",
    re.IGNORECASE,
)


def _texts(value: Any, skip: tuple[str, ...] = ()) -> list[str]:
    """Todas las cadenas de un cuerpo, sin las de los campos de `skip` (los de otras unidades)."""
    found: list[str] = []
    if isinstance(value, str):
        found.append(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in skip:
                found.extend(_texts(item, skip))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_texts(item, skip))
    return found


def _assert_english(texts: list[str]) -> None:
    assert texts
    for text in texts:
        assert not SPANISH.search(text), text
        assert not FORBIDDEN.search(text), text


def _shape(value: Any) -> Any:
    """Un cuerpo sin sus cadenas: lo que tiene que ser idéntico en los dos idiomas."""
    if isinstance(value, str):
        return "<texto>"
    if isinstance(value, dict):
        return {key: _shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_shape(item) for item in value]
    return value


def _reading(
    value: float, key: str = "heart-rate", context: Context = Context.UNKNOWN,
    confidence: float = 1.0,
) -> VitalObservation:
    return observation(key, value, NOW, "crew-01", "t", context, confidence)


def _deviation(**changes: Any) -> Deviation:
    values = tuple(float(60 + index % 5) for index in range(200))
    base: dict[str, Any] = {
        "subject": "crew-01", "key": "body-temperature", "value": 38.25, "effective": NOW,
        "z_score": 2.46, "severity": Severity.MILD, "direction": "high",
        "baseline": Baseline("body-temperature", 36.6, 0.2, len(values), tuple(sorted(values))),
        "used_population_range": False, "basis": None, "danger_limit": None,
    }
    return Deviation(**{**base, **changes})


# --- Las palabras de nivel: el vocabulario común -------------------------------------------------


def test_the_levels_have_the_shared_english_words(english: None) -> None:
    assert [level.display for level in RiskLevel] == ["nominal", "watch", "concern", "critical"]
    assert [level.label for level in RiskLevel] == ["Nominal", "Watch", "Concern", "Critical"]
    assert wording.level_labels() == {
        "nominal": "Nominal", "watch": "Watch", "concern": "Concern", "critical": "Critical",
    }


def test_the_level_keys_and_the_spanish_words_do_not_move() -> None:
    spanish = wording.level_labels()
    assert spanish == {
        "nominal": "Nominal", "watch": "Vigilancia", "concern": "Precaución",
        "critical": "Crítico",
    }
    with i18n.use("en"):
        assert list(wording.level_labels()) == list(spanish)
        assert [str(level) for level in RiskLevel] == ["nominal", "watch", "concern", "critical"]
    assert RiskLevel.CONCERN.display == "precaución"


def test_a_trajectory_is_worded_in_english_and_keeps_its_identifiers() -> None:
    found = recovery_state.trajectories(
        {Domain.CARDIOVASCULAR: RiskLevel.NOMINAL}, {Domain.CARDIOVASCULAR: RiskLevel.WATCH}, NOW
    )["cardiovascular"]
    spanish = wording.with_wording(found)
    with i18n.use("en"):
        again = recovery_state.trajectories(
            {Domain.CARDIOVASCULAR: RiskLevel.NOMINAL},
            {Domain.CARDIOVASCULAR: RiskLevel.WATCH}, NOW,
        )["cardiovascular"]
        english = wording.with_wording(again)
    assert spanish is not None and english is not None and found is not None and again is not None
    assert spanish["display"] == "recuperándose (antes Vigilancia)"
    assert english["display"] == "recovering (was Watch)"
    assert english["direction_display"] == "recovering"
    assert english["from_level_display"] == "Watch"
    assert again["basis"] == (
        "watch level one window ago and nominal level now, under the same rules; it describes "
        "the change, it does not explain it"
    )
    for field in ("direction", "from_level", "to_level", "since"):
        assert english[field] == spanish[field]
    assert "hace una ventana" in found["basis"]


def test_a_domain_summary_names_the_level_in_english(english: None) -> None:
    risk = DomainRisk(Domain.CARDIOVASCULAR, 50.0, RiskLevel.CONCERN, ("x",))
    assert "(concern): x" in risk.describe()
    assert "precaución" not in risk.describe()


# --- Desviación y tendencia: las frases del motor ------------------------------------------------


def test_a_danger_limit_reading_is_described_in_english_with_a_decimal_point() -> None:
    deviation = BaselineEngine().evaluate(_reading(41.25, key="body-temperature"))
    assert deviation.basis is SeverityBasis.DANGER_LIMIT
    spanish = deviation.describe()
    with i18n.use("en"):
        english = deviation.describe()
    assert "por encima del límite de peligro" in spanish
    assert "41,3" in spanish or "41,2" in spanish
    assert "above the danger limit" in english
    assert "41.3" in english or "41.2" in english
    assert not re.search(r"\d,\d", english)
    _assert_english([english.split(": ", 1)[1]])
    assert deviation.describe() == spanish


def test_every_branch_of_a_deviation_has_its_english(english: None) -> None:
    assert _deviation(severity=Severity.NONE).describe().endswith(": within what is expected")
    percentile = _deviation(basis=SeverityBasis.PERSONAL_PERCENTILE, value=70.0).describe()
    assert "above 100.0 % of their own reference readings (200 readings)" in percentile
    doubtful = _deviation(basis=SeverityBasis.LOW_CONFIDENCE, direction="low").describe()
    assert "below their personal baseline, but with low measurement confidence" in doubtful
    assert "no more than a mild finding is stated" in doubtful
    limited = _deviation(basis=SeverityBasis.LOW_CONFIDENCE, danger_limit=39.5).describe()
    assert "above the danger limit (39.5" in limited
    by_range = _deviation(used_population_range=True).describe()
    assert by_range.endswith("2.5 deviations above the population range")
    assert _deviation().describe().endswith("2.5 deviations above their personal baseline")
    _assert_english([
        text.split(": ", 1)[1] for text in (percentile, doubtful, limited, by_range)
    ])


def test_the_spanish_deviation_is_the_same_under_an_explicit_spanish_request() -> None:
    deviation = _deviation(basis=SeverityBasis.LOW_CONFIDENCE, danger_limit=39.5)
    plain = deviation.describe()
    with i18n.use("es"):
        assert deviation.describe() == plain
    assert "por encima del límite de peligro (39,5" in plain
    assert "pero con baja confianza de medida" in plain


def _trend(**changes: Any) -> Trend:
    base: dict[str, Any] = {
        "key": "heart-rate", "slope_per_day": 0.5, "t_statistic": 9.0, "points": 40,
        "span_days": 21.0, "direction": Direction.RISING, "significant": True,
        "mean_value": 62.0, "standard_error": 0.01,
    }
    return Trend(**{**base, **changes})


def test_a_trend_is_described_in_english() -> None:
    trend = _trend()
    spanish = trend.describe()
    with i18n.use("en"):
        english = trend.describe()
        closed = _trend(closed_episode=True, direction=Direction.FALLING).describe()
        none = _trend(significant=False).describe()
        small = _trend(slope_per_day=0.01).describe()
    assert "subiendo" in spanish and "a lo largo de 21 días" in spanish and "3,5" in spanish
    assert "rising 3.5" in english and "/week" in english and "over 21 days" in english
    assert "closed episode; it was below their personal range within the last 21 days" in closed
    assert "it is not an ongoing drift" in closed
    assert none.endswith(": no detectable trend")
    assert small.endswith("(a real drift, but below the clinical threshold)")
    _assert_english([text.split(": ", 1)[1] for text in (english, closed, none, small)])
    assert trend.describe() == spanish


def test_a_projection_says_its_basis_in_english_and_keeps_its_figures() -> None:
    trend = linear_trend(
        "heart-rate",
        [NOW + index * DAY / 4 for index in range(60)],
        [60.0 + 0.3 * index + (index % 3) * 0.2 for index in range(60)],
    )
    assert trend is not None
    spanish = projection(trend)
    with i18n.use("en"):
        english = projection(trend)
    assert spanish is not None and english is not None
    assert "extrapolación lineal" in spanish["basis"]
    assert english["basis"] == (
        "linear extrapolation of 15 days to 4 weeks if the drift continued unchanged; it is not "
        "a clinical forecast"
    )
    for field in ("key", "observation_type", "model_version", "projected_change", "unit"):
        assert english[field] == spanish[field]


def test_the_risk_engine_words_its_radiation_drivers_and_notes_in_english() -> None:
    spanish = RiskEngine().assess("crew-01", [], cumulative_dose_msv=123.45)
    with i18n.use("en"):
        english = RiskEngine().assess("crew-01", [], cumulative_dose_msv=123.45)
    es_driver = spanish.domains[Domain.RADIATION].drivers[0]
    en_driver = english.domains[Domain.RADIATION].drivers[0]
    assert es_driver == "dosis acumulada 123,5 mSv (21 % del límite de carrera)"
    assert en_driver == "cumulative dose 123.5 mSv (21 % of the career limit)"
    assert english.domains[Domain.RADIATION].score == spanish.domains[Domain.RADIATION].score
    assert english.overall_level is spanish.overall_level


# --- Caducidad, episodio cerrado, comprobación de proyecciones -----------------------------------


def test_freshness_is_named_in_english_and_its_state_is_the_same() -> None:
    spanish = staleness.describe(staleness.ExternalSource.SPACE_WEATHER, 7 * 3600)
    with i18n.use("en"):
        english = staleness.describe(staleness.ExternalSource.SPACE_WEATHER, 7 * 3600)
        words = [state.display for state in staleness.Freshness]
        basis = i18n.loc(staleness.BASIS)
        rule = i18n.loc(episode.CLOSED_EPISODE_RULE)
        checks = forecast_check.summary([])
    assert spanish["display"] == "caducado" and english["display"] == "stale"
    assert words == ["up to date", "stale", "no data"]
    assert {**english, "display": ""} == {**spanish, "display": ""}
    assert basis.startswith("EMMA design, with no source")
    assert rule.startswith("Measured, not adopted (§5.38.6)")
    assert checks["basis"].startswith("measured mean daily change against the projected one")
    _assert_english([basis, rule, checks["basis"]])
    assert i18n.loc(staleness.BASIS) == staleness.BASIS
    assert "calibración del propio modelo" in forecast_check.summary([])["basis"]


# --- Detalle de una alerta -----------------------------------------------------------------------


def test_the_alert_detail_keeps_the_compared_value_and_adds_its_english_twin() -> None:
    deviation = _deviation()
    spanish = explain.changed(deviation)
    with i18n.use("en"):
        english = explain.changed(deviation)
        detail = explain.detail(Domain.CARDIOVASCULAR, [], [])
    # La interfaz compara este valor (`AlertDetailView.tsx`): no cambia con el idioma.
    assert english["compared_with"] == spanish["compared_with"] == "línea base personal"
    assert spanish["compared_with_display"] == "línea base personal"
    assert english["compared_with_display"] == "personal baseline"
    with i18n.use("en"):
        assert explain.changed(_deviation(used_population_range=True))[
            "compared_with_display"
        ] == "population range"
    for field in ("key", "unit", "value", "severity", "direction", "basis", "baseline_median"):
        assert english[field] == spanish[field]
    assert detail["onset_basis"] == (
        "no reading outside what is expected: the alert comes from a trend or from an external "
        "event"
    )
    assert detail["relevance"].startswith("NASA RIDGE hazard: ")
    assert explain.detail(Domain.CARDIOVASCULAR, [], [])["relevance"].startswith(
        "Peligro RIDGE de NASA: "
    )


# --- Recuperación posvuelo -----------------------------------------------------------------------


def _samples(*taken: tuple[int, bool]) -> list[dict[str, Any]]:
    return [
        {"days_after_landing": day, "within_preflight_range": within} for day, within in taken
    ]


RETURNS: tuple[tuple[tuple[tuple[int, bool], ...], str], ...] = (
    (
        ((1, False), (45, True), (82, True), (194, True)),
        "Outside their preflight range at the first postflight sample; back within it at R+45; "
        "it stays within it at the next 2 samples, up to R+194.",
    ),
    (
        ((1, False), (45, True), (82, True), (194, False)),
        "Outside their preflight range at the first postflight sample; back within it at R+45; "
        "it does not stay within it: one sample outside afterwards, at R+194; the last sample, "
        "R+194, is still outside: not back.",
    ),
    (
        ((1, True), (45, False), (82, False), (194, True)),
        "Within their preflight range at the first postflight sample, R+1; it does not stay "
        "within it: 2 samples outside afterwards, between R+45 and R+82; within it again at the "
        "last sample, R+194.",
    ),
    (
        ((1, False), (45, False)),
        "Not back: none of their 2 postflight samples (R+1 to R+45) falls within their "
        "preflight range.",
    ),
    (
        ((3, False),),
        "Not back: their only postflight sample, R+3, falls outside their preflight range.",
    ),
    (
        ((1, True),),
        "Within their preflight range at the first postflight sample, R+1; there are no later "
        "samples.",
    ),
    (
        ((1, False), (2, False), (45, True), (82, False), (100, True), (194, True)),
        "Outside their preflight range at the first 2 postflight samples; back within it at "
        "R+45; it does not stay within it: one sample outside afterwards, at R+82; within it "
        "again at the last 2 samples, since R+100.",
    ),
)


@pytest.mark.parametrize(("taken", "sentence"), RETURNS)
def test_the_return_to_range_sentence_in_english(
    taken: tuple[tuple[int, bool], ...], sentence: str
) -> None:
    spanish = recovery.return_to_range(_samples(*taken))
    with i18n.use("en"):
        english = recovery.return_to_range(_samples(*taken))
    assert english["text"] == sentence
    assert {**english, "text": ""} == {**spanish, "text": ""}
    assert SPANISH.search(spanish["text"])
    _assert_english([english["text"]])


def test_an_indicator_without_preflight_range_says_so_in_english() -> None:
    launch = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)
    landing = launch + 180 * DAY
    readings = [
        observation("leukocytes", 6.1, launch - 10 * DAY, "crew-01", "t"),
        observation("leukocytes", 5.2, landing + 1 * DAY, "crew-01", "t"),
        observation("leukocytes", 5.9, landing + 45 * DAY, "crew-01", "t"),
    ]
    _, spanish = recovery.split(readings, launch, landing)
    with i18n.use("en"):
        _, english = recovery.split(readings, launch, landing)
        basis = i18n.loc(recovery.BASIS)
    assert english[0]["return_to_range"] == {
        "state": "no-preflight-range",
        "text": (
            "No preflight range: only one sample before launch, and EMMA asks for 2 for a "
            "range; their 2 postflight samples (R+1 to R+45) are not compared."
        ),
    }
    assert spanish[0]["return_to_range"]["text"].startswith("Sin rango prevuelo: una sola toma")
    assert basis.endswith("it is not a recovery verdict or a rate.")
    _assert_english([basis])


# --- Calidad del dato ----------------------------------------------------------------------------


def _quality(language: i18n.Lang) -> dict[str, Any]:
    readings = [
        observation("heart-rate", 60.0 + index, NOW - index * dt.timedelta(hours=1),
                    "crew-01", "wearable-ble", Context.REST, 0.2 if index < 2 else 1.0)
        for index in range(6)
    ] + [observation("pvt-mean-rt", 250.0, NOW, "crew-01", "console-pvt")]
    with i18n.use(language):
        return data_quality.describe(readings, [], NOW, 2 * DAY, ())


def test_data_quality_is_worded_in_english_and_counts_the_same() -> None:
    spanish, english = _quality("es"), _quality("en")
    assert english["summary"] == (
        "2 of 7 readings from the last 2 days with low measurement confidence (1 indicator): "
        "they do not count as baseline reference and cannot on their own support more than a "
        "mild finding. The trend does not distinguish measurement confidence: its fit also "
        "uses the low-confidence readings."
    )
    assert english["undeclared_note"] == (
        "5 of 7 recent readings do not declare confidence: the record keeps the default one, "
        "which does not tell a checked measurement from an unchecked one. They are analysed as "
        "full confidence."
    )
    assert english["recent_label"] == "last 2 days"
    assert english["labels"] == {
        "low": "low confidence", "declared": "declared confidence", "undeclared": "not declared",
    }
    by_key = {item["key"]: item for item in english["indicators"]}
    assert by_key["pvt-mean-rt"]["latest"]["source_label"] == "PVT test on the console"
    assert by_key["pvt-mean-rt"]["latest"]["label"] == "not declared"
    assert by_key["heart-rate"]["baseline"]["text"] == (
        "2 readings of low confidence among those analysed: they are left out of the baseline "
        "reference"
    )
    assert by_key["pvt-mean-rt"]["baseline"]["text"] == "no readings set aside for low confidence"
    assert spanish["summary"].startswith("2 de 7 lecturas de los últimos 2 días con baja confianza")
    assert spanish["labels"]["low"] == "baja confianza"
    assert _shape(english) == _shape(spanish)
    assert [item["key"] for item in english["indicators"]] == [
        item["key"] for item in spanish["indicators"]
    ]
    _assert_english(_texts(english, skip=(
        "key", "display", "display_es", "domain", "unit", "source", "state", "effective",
        "observation_type", "evidence_context", "device_bindings",
    )))


def test_the_sources_are_named_in_english(english: None) -> None:
    assert data_quality.source_label("manual") == "manual entry"
    assert data_quality.source_label("simulator:nominal") == "simulator (nominal)"
    assert data_quality.source_label("analitica:abc") == "lab results of report abc"
    assert data_quality.source_label("apple-health") == "Apple Health"
    assert data_quality.source_label("otra-fuente") == "otra-fuente"


# --- Banda ósea, ejercicio y densitometría -------------------------------------------------------


def test_the_bone_band_is_worded_in_english_and_its_figures_do_not_move() -> None:
    spanish = inferred.bone_density_band(
        200.0, True, phase=MissionPhase.POSTFLIGHT, return_day=180.0
    )
    with i18n.use("en"):
        english = inferred.bone_density_band(
            200.0, True, phase=MissionPhase.POSTFLIGHT, return_day=180.0
        )
        unlogged = inferred.bone_density_band(30.0, False)
    assert english["display"] == "Bone mineral density loss in weight-bearing bones"
    assert "1-1.5 % per month" in english["basis"] and "1-1,5 %" in spanish["basis"]
    assert english["cut"]["label"] == "up to the return day"
    assert english["cut"]["recovery"].startswith("According to NASA's technical brief")
    assert english["cut"]["recovery_source"]["relevance"] == (
        "what NASA says about bone recovery after flight (pages 2 and 20)"
    )
    assert spanish["cut"]["recovery_source"]["relevance"].startswith("lo que dice NASA")
    assert unlogged["exercise_note"].startswith("No exercise record in the data")
    for field in ("key", "unit", "observation_type", "model_version", "now", "trajectory"):
        assert english[field] == spanish[field]
    assert english["cut"]["phase"] == spanish["cut"]["phase"] == "postflight"
    _assert_english([
        english["display"], english["basis"], english["exercise_note"], english["cut"]["label"],
        english["cut"]["basis"], english["cut"]["recovery"], unlogged["exercise_note"],
    ])


def _exercise(language: i18n.Lang) -> dict[str, Any]:
    readings = [
        observation("exercise-minutes", 40.0 + index * 2.5, NOW - index * DAY, "crew-01", "t")
        for index in range(5)
    ]
    with i18n.use(language):
        deviations = BaselineEngine().evaluate_all(readings)
        return exercise_summary.measured(readings, deviations, {}, NOW)


def test_the_measured_exercise_is_worded_in_english() -> None:
    spanish, english = _exercise("es"), _exercise("en")
    minutes = english["indicators"][0]
    assert english["record"] == {
        "state": "recorded",
        "display": "there is a record",
        "note": (
            "There is an exercise record in the last week of data: resistive exercise reduces "
            "the loss, but its effect has no citable magnitude and the band is not adjusted."
        ),
    }
    assert english["relation"].startswith("What is measured goes alongside the band")
    assert english["adherence_note"].startswith("No “% adherence”")
    assert english["window_basis"].startswith("Last week of data")
    assert "5 measured readings in the last week of data, between 40 min and 50 min" in (
        minutes["statement"]
    )
    assert minutes["trend_statement"] == (
        "No trend calculated: there are not enough readings to fit it."
    )
    assert minutes["baseline"]["statement"].startswith("No baseline of their own yet")
    assert english["indicators"][1]["statement"].endswith(
        ": no measured readings in the last week of data."
    )
    assert spanish["record"]["display"] == "hay registro"
    assert "5 lecturas medidas en la última semana de datos" in (
        spanish["indicators"][0]["statement"]
    )
    assert _shape(english) == _shape(spanish)
    _assert_english(_texts(english, skip=(
        "key", "display", "display_es", "unit", "observation_type", "state", "window_start",
        "window_end", "first", "last", "against_baseline",
    )))


def test_what_is_on_record_in_a_window_is_titled_in_english() -> None:
    readings = [
        observation("exercise-minutes", 40.0, NOW - DAY, "crew-01", "t"),
        observation("exercise-minutes", 52.5, NOW, "crew-01", "t"),
    ]
    spanish = exercise_summary.in_window(readings, NOW - 2 * DAY, NOW)
    with i18n.use("en"):
        english = exercise_summary.in_window(readings, NOW - 2 * DAY, NOW)
    assert spanish[0]["title"].startswith("Ejercicio registrado — ")
    assert spanish[0]["title"].endswith(": 2 lecturas, entre 40 min y 53 min") or (
        "entre 40 min y 5" in spanish[0]["title"]
    )
    assert english[0]["title"].startswith("Exercise on record — ")
    assert ": 2 readings, between 40 min and 5" in english[0]["title"]
    assert {**english[0], "title": "", "display_es": ""} == {
        **spanish[0], "title": "", "display_es": "",
    }


def _dxa(language: i18n.Lang) -> dict[str, Any]:
    start = dt.date(2026, 11, 1)
    launch = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)
    readings = [
        observation(BMD_DXA_HIP.key, 1.0, launch - 40 * DAY, "crew-01", "t"),
        observation(BMD_DXA_HIP.key, 0.9, launch + 190.5 * DAY, "crew-01", "t"),
    ]
    assert all(item.observation_type is ObservationType.MEASURED for item in readings)
    with i18n.use(language):
        found = densitometry.against_band(readings, mission_start=start, return_day=180.0)
    assert found is not None
    return found


def test_the_densitometry_beside_the_band_is_worded_in_english() -> None:
    spanish, english = _dxa("es"), _dxa("en")
    hip = english["regions"][0]
    assert hip["region"] == "Hip" and spanish["regions"][0]["region"] == "Cadera"
    assert hip["statement"] == (
        "The measured loss is above the inferred band: densitometry gives more loss than the "
        "band estimates."
    )
    assert hip["preflight"]["label"] == "before launch"
    assert hip["postflight"]["label"] == "after the return"
    assert hip["postflight"]["when_display"] == "R+10.5 d"
    assert spanish["regions"][0]["postflight"]["when_display"] == "R+10,5 d"
    assert english["loss_label"] == "loss measured since before launch"
    assert english["band_label"] == "cumulative loss the band estimates for the return day"
    assert english["source"]["relevance"].startswith("where and when bone density is measured")
    assert (hip["state"], hip["position"]) == ("compared", "above")
    assert _shape(english) == _shape(spanish)
    for field in ("measured_loss_pct", "state", "position", "key", "unit", "in_flight"):
        assert hip[field] == spanish["regions"][0][field]
    _assert_english([
        hip["statement"], english["relation"], english["precision_note"], english["loss_label"],
        english["band_label"], english["source"]["relevance"], hip["preflight"]["label"],
    ])


def test_every_fixed_densitometry_sentence_has_its_english(english: None) -> None:
    fixed = [
        *densitometry.POSITION_STATEMENTS.values(), *densitometry.STATE_STATEMENTS.values(),
        densitometry.IN_FLIGHT_NOTE, densitometry.RELATION, densitometry.PRECISION_NOTE,
    ]
    shown = [i18n.loc(text) for text in fixed]
    assert all(after != before for after, before in zip(shown, fixed, strict=True))
    _assert_english(shown)


# --- Fase del ciclo ------------------------------------------------------------------------------


def test_the_cycle_gate_sentences_have_their_english() -> None:
    closed = [
        cycle_gate.NO_DECLARED, cycle_gate.NOT_FEMALE, cycle_gate.NO_STATUS,
        cycle_gate.NOT_REGULAR, cycle_gate.MALFORMED,
    ]
    spanish = [cycle_gate._closed(text).reason for text in closed]
    with i18n.use("en"):
        english = [cycle_gate._closed(text).reason for text in closed]
        reasons = {key: i18n.loc(text) for key, text in cycle_phase.REASONS.items()}
        unadjusted = cycle_gate._unadjusted()
    assert spanish == closed
    assert all(text.startswith("No baseline adjustment for cycle phase: ") for text in english)
    assert english[1].endswith("the declared sex is not female.")
    assert reasons["too_few_starts"] == (
        f"period starts are missing: {cycle_phase.MIN_STARTS} are needed (two complete cycles) "
        "to place the phase"
    )
    assert list(reasons) == list(cycle_phase.REASONS)
    assert all(reasons[key] != cycle_phase.REASONS[key] for key in reasons)
    assert unadjusted.endswith(
        " not adjusted: what was read says how they change in the luteal phase, but not by how "
        "much."
    )
    assert cycle_gate._unadjusted() == cycle_gate.UNADJUSTED
    _assert_english([*english, *reasons.values()])


# --- Perfil de línea base: la ruta ---------------------------------------------------------------

# Lo que no es de esta unidad (el sentido en otros vuelos) y lo que no es frase.
PROFILE_SKIP = (
    "flight_direction", "key", "display", "display_es", "domain", "unit", "context", "kind",
    "drawn_from", "reading_effective", "window", "severity", "basis", "subject",
    "reference_time", "source", "phase", "until", "composition",
)


def test_the_baseline_profile_route_answers_in_english(client: TestClient) -> None:
    seeded = client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 30, "crew_size": 1, "seed": 7}
    )
    assert seeded.status_code == 201, seeded.text
    plain = client.get("/api/baseline-profile")
    spanish = client.get("/api/baseline-profile", headers={i18n.HEADER: "es"})
    english = client.get("/api/baseline-profile", headers=ENGLISH_HEADERS)
    assert plain.status_code == spanish.status_code == english.status_code == 200
    # Quien no pide idioma recibe el castellano, byte a byte el de quien lo pide.
    assert plain.content == spanish.content
    es, en = spanish.json(), english.json()

    assert es["method"].startswith("Base móvil: cada lectura se compara")
    assert en["method"] == (
        "Rolling baseline: each reading is compared with those of the same state (sleep with "
        "sleep, rest with rest) from the 14 days ending 12 h before it, without the "
        "low-confidence ones. Centre: the median; spread: the median absolute deviation times "
        "1.4826. It is taken as established with 100 readings; until then only a catalogue "
        "danger limit warns."
    )
    assert "1,4826" in es["method"]
    assert en["cuts_method"].startswith(
        "Each established baseline cuts at the percentiles of its own readings: mild above "
        "percentile 99 (with 100 baseline readings or more), moderate above percentile 99.5"
    )
    assert "percentile 1, percentile 0.5 and percentile 0.1" in en["cuts_method"]
    assert en["fixed_note"].startswith("There is no fixed baseline")
    assert re.match(r"^\d+ analysed indicators, with \d+ baselines \(one per state\): ",
                    en["statement"])
    assert en["personal_data"]["no_field"] == ["age"]
    assert es["personal_data"]["no_field"] == ["edad"]
    assert en["personal_data"]["statement"].startswith("Sex is not a profile field")
    assert "“universal for all ages and sexes”" in en["personal_data"]["radiation"]
    assert en["personal_data"]["source"]["relevance"].startswith("[V1 4030], section 4.8.2")
    assert en["personal_data"]["source"]["id"] == es["personal_data"]["source"]["id"]

    rows = [row for item in en["indicators"] for row in item["states"]]
    assert {row["status_display"] for row in rows} <= {"established", "learning"}
    assert any(row["status_display"] == "established" for row in rows)
    assert {row["context_display"] for row in rows} <= set(
        baseline_profile.CONTEXT_DISPLAY_EN.values()
    )
    cuts = [cut for row in rows for cut in row["cuts"]]
    assert {cut["display"] for cut in cuts} == {"mild", "moderate", "severe"}
    assert any(
        re.search(r"^Mild: (above|below) \d+\.\d+ .*\(percentile (99|1) of their baseline\)",
                  cut["text"])
        for cut in cuts
    )
    assert any("no cut yet; it asks for 1000 baseline readings" in cut["text"] for cut in cuts)
    assert any(
        item["reference"]["text"].startswith("Catalogue range: from ")
        for item in en["indicators"]
    )

    # Nada de lo que no es texto cambia con el idioma.
    assert _shape(en) == _shape(es)
    for field in ("context", "drawn_from", "established", "samples", "median", "spread"):
        assert [row[field] for row in rows] == [
            row[field] for item in es["indicators"] for row in item["states"]
        ]
    assert [cut["severity"] for cut in cuts] == [
        cut["severity"]
        for item in es["indicators"] for row in item["states"] for cut in row["cuts"]
    ]
    _assert_english(_texts(en, skip=PROFILE_SKIP))
    assert any(SPANISH.search(text) for text in _texts(es, skip=PROFILE_SKIP))


def test_every_fixed_profile_sentence_has_its_english(english: None) -> None:
    fixed = [
        baseline_profile.RANGE_ROLE, baseline_profile.NO_RANGE,
        baseline_profile.DESCRIPTIVE_REASON, baseline_profile.FIXED_NOTE,
        baseline_profile.NO_VALUES, *baseline_profile.ONE_SIDED_NOTE.values(),
        baseline_profile.UNKNOWN_COMPOSITION, baseline_profile.EMPTY_COMPOSITION,
        baseline_profile.NOT_KEPT_COMPOSITION, baseline_profile.PERSONAL_DATA_STATEMENT,
        baseline_profile.PERSONAL_DATA_CYCLE, baseline_profile.PERSONAL_DATA_RADIATION,
        baseline_profile.PERSONAL_DATA_ELSEWHERE, baseline_profile.PERSONAL_DATA_PRIVACY,
    ]
    shown = [i18n.loc(text) for text in fixed]
    assert all(after != before for after, before in zip(shown, fixed, strict=True))
    _assert_english(shown)
    assert set(baseline_profile.CONTEXT_DISPLAY_EN) == set(baseline_profile.CONTEXT_DISPLAY)
    assert set(baseline_profile.REFERENCE_BASIS_DISPLAY_EN) == set(
        baseline_profile.REFERENCE_BASIS_DISPLAY
    )
    assert set(baseline_profile.CUT_SEVERITY_DISPLAY_EN) == set(
        baseline_profile.CUT_SEVERITY_DISPLAY
    )


# --- El estado: niveles y motivos por la API -----------------------------------------------------


def test_the_status_names_levels_and_drivers_in_english(client: TestClient) -> None:
    seeded = client.post(
        "/api/simulate",
        params={"scenario": "cardiovascular-deconditioning", "days": 40, "crew_size": 1,
                "seed": 7},
    )
    assert seeded.status_code == 201, seeded.text
    plain = client.get("/api/status").json()
    spanish = client.get("/api/status", headers={i18n.HEADER: "es"}).json()
    english = client.get("/api/status", headers=ENGLISH_HEADERS).json()
    assert english["level_labels"] == {
        "nominal": "Nominal", "watch": "Watch", "concern": "Concern", "critical": "Critical",
    }
    assert plain["level_labels"] == spanish["level_labels"]
    assert plain["level_labels"]["concern"] == "Precaución"
    # El veredicto no depende del idioma: mismos niveles y puntuaciones, dominio a dominio.
    assert english["overall_level"] == spanish["overall_level"] == plain["overall_level"]
    for domain, risk in spanish["domains"].items():
        assert english["domains"][domain]["level"] == risk["level"]
        assert english["domains"][domain]["score"] == risk["score"]
        assert plain["domains"][domain]["drivers"] == risk["drivers"]
    es_drivers = [text for risk in spanish["domains"].values() for text in risk["drivers"]]
    en_drivers = [text for risk in english["domains"].values() for text in risk["drivers"]]
    assert es_drivers and len(en_drivers) == len(es_drivers)
    assert any("subiendo" in text or "bajando" in text or "por " in text for text in es_drivers)
    for text in en_drivers:
        sentence = text.split(": ", 1)[1]
        assert not SPANISH.search(sentence), text
        assert not re.search(r"\d,\d", sentence), text
    assert any(re.search(r"\d\.\d", text) for text in en_drivers)
    assert english["rules_version"] == spanish["rules_version"]
