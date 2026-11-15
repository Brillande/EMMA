"""El ejercicio, medido: junto a la banda ósea y como contexto de una alerta (§9 y §10).

Qué fijan estas pruebas:
- que lo medido sale de lo que el motor ya calculó (línea base y tendencia), no de otra cuenta;
- que «hay registro» deja de ser cierto con una lectura de 0 minutos: son tres casos;
- que no hay «% de adherencia», y se dice por qué;
- que el ejercicio es una fuente más del contexto de una alerta, con la misma ventana, el mismo
  rótulo de no-causa y diciendo si había dato;
- que todo el texto pasa el linter de lenguaje (invariante 7);
- y la que importa (invariante 5): la banda, los niveles y las alertas son idénticos con y sin
  esta pieza.
"""

import ast
import datetime as dt
import inspect
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import alert_context, baseline, exercise_summary, inferred, risk, trend
from app.analysis.alert_context import LABEL, around
from app.analysis.baseline import BaselineEngine, Deviation
from app.analysis.exercise_summary import (
    IMPACTS,
    KEYS,
    MINUTES,
    NO_ADHERENCE,
    NO_RECORD,
    RECORDED,
    RECORDED_ZERO,
    RELATION,
    WEEK,
    WEEK_BASIS,
    in_window,
    measured,
    record_state,
)
from app.analysis.trend import Trend, trends_by_indicator
from app.api import routes
from app.ingest.codes import get
from app.ingest.fhir import ObservationType, VitalObservation
from app.ingest.simulator import PhysiologicalSimulator, Scenario
from app.text_guard import check

START = dt.date(2026, 11, 1)
T0 = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.UTC)
REFERENCE = T0 + dt.timedelta(hours=30)


def _h(hours: float) -> dt.datetime:
    return T0 + dt.timedelta(hours=hours)


def _obs(key: str, value: float, moment: dt.datetime, **extra: Any) -> VitalObservation:
    return VitalObservation(
        code=get(key), value=value, effective=moment, subject="crew-01", source="manual", **extra
    )


Analysed = tuple[list[VitalObservation], list[Deviation], dict[str, Trend], dt.datetime]


def _analysed(observations: list[VitalObservation]) -> Analysed:
    """Lo mismo que hace `/api/status` antes de componer: línea base móvil y tendencias."""
    latest = max(obs.effective for obs in observations)
    return (
        observations, BaselineEngine().evaluate_rolling(observations),
        trends_by_indicator(observations), latest,
    )


@pytest.fixture(scope="module")
def simulated() -> Analysed:
    return _analysed(list(
        PhysiologicalSimulator(scenario=Scenario.CARDIOVASCULAR_DECONDITIONING).generate(
            days=30, keys=list(KEYS)
        )
    ))


def _by_key(block: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["key"]: item for item in block["indicators"]}


# --------------------------------------------------------------------------- #
# Lo medido, junto a la banda
# --------------------------------------------------------------------------- #

def test_the_week_is_a_declared_design_parameter() -> None:
    assert WEEK.days == 7
    assert "diseño EMMA" in WEEK_BASIS and "sin fuente" in WEEK_BASIS


def test_measured_counts_only_the_last_week_of_data(simulated: Analysed) -> None:
    observations, _, _, latest = simulated
    block = measured(*simulated)
    assert block["observation_type"] == "measured"
    assert dt.datetime.fromisoformat(block["window_start"]) == latest - WEEK
    for key, item in _by_key(block).items():
        expected = [
            obs for obs in observations
            if obs.key == key and latest - WEEK <= obs.effective <= latest
        ]
        assert item["readings"] == len(expected) > 0
        assert item["observation_type"] == "measured"
        assert item["evidence_context"] == {"simulated": len(expected)}
        assert item["first"] == min(obs.effective for obs in expected).isoformat()
        assert item["last"] == latest.isoformat()
        assert item["lowest"] == min(obs.value for obs in expected)
        assert item["highest"] == max(obs.value for obs in expected)


def test_a_reading_just_outside_the_week_is_not_counted() -> None:
    edge = REFERENCE - WEEK
    readings = [
        _obs(MINUTES, 40.0, edge - dt.timedelta(seconds=1)),
        _obs(MINUTES, 50.0, edge),
        _obs(MINUTES, 60.0, REFERENCE),
    ]
    _, deviations, trends, _ = _analysed(readings)
    item = _by_key(measured(readings, deviations, trends, REFERENCE))[MINUTES]
    assert (item["readings"], item["lowest"], item["highest"]) == (2, 50.0, 60.0)


def test_the_baseline_and_the_trend_are_the_ones_the_engine_computed(simulated: Analysed) -> None:
    _, deviations, trends, _ = simulated
    block = _by_key(measured(*simulated))
    for key in KEYS:
        latest = max((dev for dev in deviations if dev.key == key), key=lambda dev: dev.effective)
        item = block[key]
        assert latest.baseline is not None
        assert item["latest"] == latest.value
        # «Propia» solo si el motor la usó de verdad para esa lectura.
        assert item["baseline"]["personal"] is not latest.used_population_range
        assert ("aún sin establecer" in item["baseline"]["statement"]) is (
            latest.used_population_range
        )
        assert item["baseline"]["samples"] == latest.baseline.samples
        assert item["baseline"]["median"] == round(latest.baseline.quantile(0.5) or 0.0, 4)
        assert item["against_baseline"] == latest.describe()
        assert item["trend"] == trends[key].describe()
        assert trends[key].describe() in item["trend_statement"]
        week = [
            dev for dev in deviations
            if dev.key == key and dev.effective >= latest.effective - WEEK
        ]
        assert item["outside_expected"] == sum(1 for dev in week if dev.is_concerning)


def test_a_baseline_the_engine_did_not_use_is_not_presented_as_the_reference() -> None:
    readings = [_obs(MINUTES, 45.0, _h(hour)) for hour in range(0, 30, 6)]
    _, deviations, trends, latest = _analysed(readings)
    assert all(dev.used_population_range for dev in deviations)
    item = _by_key(measured(readings, deviations, trends, latest))[MINUTES]
    assert item["baseline"]["personal"] is False
    assert "rango de referencia del catálogo" in item["baseline"]["statement"]
    assert not item["baseline"]["statement"].startswith("Línea base propia: ")
    # La primera lectura de todas no tiene nada detrás: ni mediana ni lecturas anteriores.
    first = readings[:1]
    alone = _by_key(measured(first, *_analysed(first)[1:3], _h(0)))[MINUTES]
    assert (alone["baseline"]["median"], alone["baseline"]["samples"]) == (None, 0)
    assert "Sin línea base propia todavía" in alone["baseline"]["statement"]


def test_an_indicator_without_readings_says_so_and_invents_nothing() -> None:
    readings = [_obs(MINUTES, 45.0, _h(0))]
    _, deviations, trends, latest = _analysed(readings)
    item = _by_key(measured(readings, deviations, trends, latest))[IMPACTS]
    assert item["readings"] == 0 and "sin lecturas medidas" in item["statement"]
    for field in ("latest", "lowest", "highest", "baseline", "against_baseline", "trend", "first"):
        assert item[field] is None, field
    assert "Sin tendencia calculada" in item["trend_statement"]


def test_a_reading_that_is_not_measured_is_left_out_of_the_measured_block() -> None:
    readings = [
        _obs(MINUTES, 45.0, _h(0)),
        _obs(MINUTES, 90.0, _h(1), observation_type=ObservationType.INFERRED, model_version="m@1"),
    ]
    _, deviations, trends, latest = _analysed(readings)
    block = measured(readings, deviations, trends, latest)
    item = _by_key(block)[MINUTES]
    assert (item["readings"], item["highest"]) == (1, 45.0)
    assert block["not_measured_excluded"] == 1


# --------------------------------------------------------------------------- #
# Hay registro / no hay registro / hay registro y es 0
# --------------------------------------------------------------------------- #

def test_a_zero_minute_reading_is_not_an_exercise_record() -> None:
    assert record_state([]) == NO_RECORD
    assert record_state([0.0, 0.0]) == RECORDED_ZERO
    assert record_state([0.0, 30.0]) == RECORDED


@pytest.mark.parametrize(
    ("values", "state", "said"),
    [
        ([], NO_RECORD, "Sin registro de ejercicio"),
        ([0.0, 0.0, 0.0], RECORDED_ZERO, "es de 0 minutos"),
        ([0.0, 35.0], RECORDED, "Hay registro de ejercicio"),
    ],
)
def test_the_note_beside_the_band_tells_the_three_cases_apart(
    values: list[float], state: str, said: str
) -> None:
    readings = [_obs(MINUTES, value, _h(index)) for index, value in enumerate(values)]
    # Los impactos no cuentan como minutos: con solo ellos sigue sin haber registro de minutos.
    readings.append(_obs(IMPACTS, 5000.0, _h(0)))
    _, deviations, trends, latest = _analysed(readings)
    block = measured(readings, deviations, trends, _h(10))
    assert latest <= _h(10)
    assert block["record"]["state"] == state
    band = inferred.bone_density_band(60.0, exercise_logged=state == RECORDED, exercise=block)
    assert said in band["exercise_note"]
    assert band["exercise_note"] == block["record"]["note"]
    if state != RECORDED:
        assert "Hay registro de ejercicio: " not in band["exercise_note"]


def test_there_is_no_adherence_percentage_and_the_block_says_why(simulated: Analysed) -> None:
    block = measured(*simulated)
    assert block["adherence"] is None
    assert block["adherence_note"] == NO_ADHERENCE
    assert "pauta prescrita" in NO_ADHERENCE and "EMMA no tiene ninguna" in NO_ADHERENCE

    def numbers(value: Any, path: str = "") -> list[str]:
        if isinstance(value, dict):
            return [name for key, item in value.items() for name in numbers(item, f"{path}.{key}")]
        if isinstance(value, list):
            return [name for item in value for name in numbers(item, path)]
        return [path] if isinstance(value, int | float) and not isinstance(value, bool) else []

    # Ninguna cifra del bloque es una fracción cumplida ni una pauta.
    assert not [name for name in numbers(block) if "adher" in name or "target" in name]
    assert all("%" not in item["statement"] for item in block["indicators"])


# --------------------------------------------------------------------------- #
# La banda no se mueve
# --------------------------------------------------------------------------- #

def test_the_band_is_the_same_with_and_without_the_measured_exercise(simulated: Analysed) -> None:
    block = measured(*simulated)
    for day in (0.0, 12.5, 60.0, 200.0, 400.0):
        plain = inferred.bone_density_band(day, exercise_logged=False)
        beside = inferred.bone_density_band(day, exercise_logged=True, exercise=block)
        assert beside["exercise"] is block
        assert beside["exercise"]["relation"] == RELATION
        assert "no la modifica" in RELATION
        for field in plain:
            if field != "exercise_note":
                assert beside[field] == plain[field], field
        assert beside["observation_type"] == "inferred"
        assert set(beside) - set(plain) == {"exercise"}


# --------------------------------------------------------------------------- #
# El ejercicio como fuente del contexto de una alerta
# --------------------------------------------------------------------------- #

def _context(exercise: list[VitalObservation], **override: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "onset": T0, "reference": REFERENCE, "habitat_readings": [], "habitat_excursions": [],
        "mission_events": [], "solar": None, "adoptions": [], "mission_start": START,
        "mission_days": 180, "gravity_regime": "microgravedad", "exercise": exercise,
    }
    arguments.update(override)
    return around(**arguments)


def _exercise_of(context: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    [source] = [item for item in context["sources"] if item["kind"] == "exercise"]
    return [item for item in context["items"] if item["kind"] == "exercise"], source


def test_without_exercise_readings_the_source_says_no_data() -> None:
    for context in (_context([]), around(**{
        key: value for key, value in {
            "onset": T0, "reference": REFERENCE, "habitat_readings": [],
            "habitat_excursions": [], "mission_events": [], "solar": None, "adoptions": [],
            "mission_start": START, "mission_days": 180, "gravity_regime": "microgravedad",
        }.items()
    })):
        items, source = _exercise_of(context)
        assert items == []
        assert (source["status"], source["found"]) == ("no_data", 0)
        assert "que no conste no quiere decir que no lo hubiera" in source["note"]


def test_an_exercise_indicator_without_readings_in_the_window_is_named() -> None:
    items, source = _exercise_of(_context([_obs(MINUTES, 30.0, _h(-2))]))
    assert len(items) == 1
    assert (source["status"], source["found"]) == ("partial", 1)
    assert source["note"].startswith(
        "Sin lectura en la ventana: Impactos de carga mecánica (acelerometría). "
    )


def test_exercise_recorded_around_the_onset_is_listed_as_temporal_correlation() -> None:
    readings = [
        _obs(MINUTES, 30.0, _h(-20)), _obs(MINUTES, 0.0, _h(-3)), _obs(IMPACTS, 4200.0, _h(2)),
    ]
    items, source = _exercise_of(_context(readings))
    assert (source["status"], source["found"]) == ("with_data", 2)
    assert "sin pauta prescrita" in source["note"]
    minutes, impacts = sorted(items, key=lambda item: item["start"])
    assert minutes["label"] == impacts["label"] == LABEL
    assert minutes["title"] == (
        "Ejercicio registrado — Duración del ejercicio resistivo: 2 lecturas, entre 0 min y 30 min"
    )
    assert (minutes["start"], minutes["end"]) == (_h(-20).isoformat(), _h(-3).isoformat())
    assert minutes["timing"] == "última lectura 3,0 h antes del inicio de la alerta"
    assert impacts["title"].endswith("1 lectura, 4200 recuento")
    assert impacts["timing"] == "2,0 h después del inicio de la alerta"
    assert minutes["source"] == "lecturas de manual"
    assert minutes["value"] is None and minutes["detail"] is None


def test_exercise_outside_the_window_or_after_the_state_instant_is_not_context() -> None:
    before = alert_context.WINDOW_BEFORE.total_seconds() / 3600
    after = alert_context.WINDOW_AFTER.total_seconds() / 3600
    outside = [_obs(MINUTES, 30.0, _h(-before - 1)), _obs(MINUTES, 30.0, _h(after + 1))]
    assert _exercise_of(_context(outside))[1]["status"] == "no_data"
    edges = [_obs(MINUTES, 30.0, _h(-before)), _obs(MINUTES, 40.0, _h(after))]
    [item] = _exercise_of(_context(edges))[0]
    assert "2 lecturas" in item["title"]
    # El estado es de una hora después del inicio: lo registrado más tarde aún no existe.
    late = [_obs(MINUTES, 30.0, _h(2))]
    assert _exercise_of(_context(late, reference=_h(1)))[1]["status"] == "no_data"


def test_the_window_listing_only_counts_what_is_there() -> None:
    readings = [_obs(IMPACTS, 5000.0, _h(0)), _obs("heart-rate", 60.0, _h(0))]
    [found] = in_window(readings, _h(-1), _h(1))
    assert (found["key"], found["readings"], found["sources"]) == (IMPACTS, 1, ["manual"])
    assert in_window(readings, _h(1), _h(2)) == []


# --------------------------------------------------------------------------- #
# Lenguaje (invariante 7) y segregación del motor (invariante 5)
# --------------------------------------------------------------------------- #

def test_every_text_written_by_this_piece_passes_the_language_guard(simulated: Analysed) -> None:
    texts = [RELATION, NO_ADHERENCE, WEEK_BASIS]
    zero = [_obs(MINUTES, 0.0, _h(0))]
    blocks = [
        measured(*simulated),
        measured([], [], {}, REFERENCE),
        measured(zero, *_analysed(zero)[1:3], _h(1)),
    ]
    for block in blocks:
        texts += [block["record"]["display"], block["record"]["note"]]
        for item in block["indicators"]:
            texts += [item["statement"], item["trend_statement"]]
            texts += [item["baseline"]["statement"]] if item["baseline"] else []
    listed = [_obs(MINUTES, 30.0, _h(-2)), _obs(MINUTES, 9.0, _h(1))]
    for context in (_context([]), _context(listed)):
        items, source = _exercise_of(context)
        texts += [source["display"], source["status_display"], source["note"]]
        for item in items:
            texts += [item["title"], item["timing"], item["source"], item["label"]]
    assert len(set(texts)) > 15, "la prueba tiene que mirar textos de verdad"
    assert [(text, check(text)) for text in texts if check(text)] == []


def _imported_names(module: object) -> set[str]:
    tree = ast.parse(inspect.getsource(module))  # type: ignore[arg-type]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            names |= {f"{node.module}.{alias.name}" for alias in node.names}
    return names


def test_the_engine_does_not_know_this_piece_and_the_piece_cannot_decide() -> None:
    for engine in (risk, baseline, trend):
        assert not [name for name in _imported_names(engine) if "exercise_summary" in name]
    reads = _imported_names(exercise_summary)
    forbidden = ("RiskEngine", "BaselineEngine", "level_for", "combine_findings", "linear_trend")
    assert not [name for name in reads if name.rsplit(".", 1)[-1] in forbidden]
    # La banda no importa lo medido: lo recibe ya compuesto, y solo para ponerlo al lado.
    assert not [name for name in _imported_names(inferred) if "exercise" in name]


def test_the_piece_does_not_alter_what_it_reads(simulated: Analysed) -> None:
    observations, deviations, trends, latest = simulated
    before = (list(observations), list(deviations), dict(trends))
    measured(observations, deviations, trends, latest)
    in_window(observations, latest - WEEK, latest)
    assert (observations, deviations, trends) == before


# --------------------------------------------------------------------------- #
# De punta a punta: mismo veredicto y misma banda, con y sin la pieza
# --------------------------------------------------------------------------- #

def _verdict(status: dict[str, Any]) -> dict[str, Any]:
    """Todo lo que el estado decide: niveles, puntuaciones, motivos, alertas y consejo."""
    return {
        "overall": status["overall_level"],
        "summary": status["summary"],
        "domains": {
            key: (value["score"], value["level"], value["drivers"])
            for key, value in status["domains"].items()
        },
        "alerts": [
            (alert["id"], alert["level"], alert["annunciation"], alert["acknowledged"],
             alert["detail"]["onset"], alert["time_to_action"])
            for alert in status["alerts"]
        ],
        "recommendations": [
            (item["domain"], item["action"]) for item in status["recommendations"]
        ],
        "predictions": status["predictions"],
    }


def _band(status: dict[str, Any]) -> dict[str, Any]:
    [band] = status["inferred"]
    return {key: value for key, value in band.items() if key not in ("exercise", "exercise_note")}


@pytest.mark.parametrize(
    "scenario", ["dehydration", "cardiovascular-deconditioning", "co2-fatigue", "nominal"]
)
def test_the_verdict_and_the_band_are_identical_with_and_without_the_exercise(
    scenario: str, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.post("/api/simulate", params={"scenario": scenario, "days": 40, "crew_size": 1})
    full = client.get("/api/status").json()
    if scenario != "nominal":
        assert full["alerts"], "el escenario tiene que alertar para que la prueba diga algo"

    # Con la pieza: lo medido va junto a la banda, rotulado, y cada alerta lo trae como fuente.
    [band] = full["inferred"]
    assert band["observation_type"] == "inferred"
    exercise = band["exercise"]
    assert exercise["observation_type"] == "measured"
    assert exercise["relation"] == RELATION and exercise["adherence"] is None
    assert exercise["record"]["state"] == RECORDED
    assert [item["key"] for item in exercise["indicators"]] == list(KEYS)
    assert all(
        item["readings"] > 0 and item["baseline"]["samples"] > 0 and item["trend"]
        for item in exercise["indicators"]
    )
    for alert in full["alerts"]:
        context = alert["detail"]["context"]
        sources = {item["kind"]: item for item in context["sources"]}
        assert sources["exercise"]["status"] == "with_data"
        listed = [item for item in context["items"] if item["kind"] == "exercise"]
        assert len(listed) == len(KEYS) and all(item["label"] == LABEL for item in listed)
        start = dt.datetime.fromisoformat(context["window_start"])
        end = dt.datetime.fromisoformat(context["window_end"])
        for item in listed:
            assert start <= dt.datetime.fromisoformat(item["start"])
            assert dt.datetime.fromisoformat(item["end"]) <= end

    # Sin la pieza: la banda como se servía antes y el contexto sin lecturas de ejercicio.
    monkeypatch.setattr(
        routes, "bone_density_band",
        lambda day, exercise_logged, exercise=None, **cut: inferred.bone_density_band(
            day, True, **cut
        ),
    )
    monkeypatch.setattr(alert_context, "exercise_in_window", lambda *args: [])
    bare = client.get("/api/status").json()
    assert "exercise" not in bare["inferred"][0]
    assert all(
        item["kind"] != "exercise"
        for alert in bare["alerts"] for item in alert["detail"]["context"]["items"]
    )
    assert _band(bare) == _band(full)
    assert _verdict(bare) == _verdict(full)
