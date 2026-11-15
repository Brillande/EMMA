"""El detalle de alerta: qué cuesta comprobar, por qué paso va y cuánto cambió (decimocuarta ronda).

Qué fijan estas pruebas:
- que cada comprobación lleva su coste tal como lo dice `ingest/cost.py` y la biblioteca de
  contramedidas, sin rellenar lo «sin clasificar», y que las comprobaciones NO se reordenan;
- que el cambio relativo es `(valor − mediana) / mediana` frente a la mediana personal, solo en
  escala de razón, y que donde no tiene sentido (ordinal, °C, diferencia con signo, mediana 0,
  rango poblacional) se dice por qué; que la tabla de escalas es cerrada;
- que los ocho pasos del flujo de la base de conocimiento (§10) salen de lo que el estado ya
  registró, con la convención de las hipótesis;
- que todo el texto pasa el linter de lenguaje (invariante 7);
- y que nada de esto puntúa: el veredicto es idéntico con y sin ello (invariante 5).
"""

import ast
import datetime as dt
import inspect
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.advisor import check_cost as check_cost_module
from app.advisor import countermeasures
from app.advisor.check_cost import NO_COUNTERMEASURE, NO_FIGURE, NO_REPEAT
from app.advisor.check_cost import of as check_cost
from app.advisor.recommendations import Recommendation, Urgency, _evidence
from app.analysis import alert_flow, alert_support, baseline, context, explain, risk, trend
from app.analysis.alert_support import (
    NOT_RATIO_KEYS,
    NOT_RATIO_UNITS,
    PERCENT_NOTE,
    RATIO_UNITS,
    UNDECLARED_SCALE,
    relative_change,
    scale_reason,
    support,
)
from app.analysis.baseline import Baseline, Deviation, Severity, SeverityBasis
from app.analysis.trend import Direction, Trend
from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.ingest import cost
from app.ingest.codes import CATALOG, Domain
from app.main import app
from app.text_guard import check

T0 = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.UTC)


def _h(hours: float) -> dt.datetime:
    return T0 + dt.timedelta(hours=hours)


def _deviation(
    key: str, value: float, values: tuple[float, ...] = (40.0, 50.0, 60.0),
    population: bool = False, concerning: bool = True,
) -> Deviation:
    reference = Baseline(
        key=key, center=sum(values) / len(values) if values else 0.0, spread=5.0,
        samples=len(values), sorted_values=values,
    )
    return Deviation(
        subject="crew-01", key=key, value=value, effective=_h(0), z_score=3.0,
        severity=Severity.MODERATE if concerning else Severity.NONE, direction="high",
        baseline=reference, used_population_range=population,
        basis=SeverityBasis.PERSONAL_PERCENTILE if concerning else None,
    )


def _library(domain: Domain) -> list[Recommendation]:
    return [
        Recommendation(
            domain=domain, action=item.action, rationale="motivo", urgency=Urgency.ROUTINE,
            evidence=_evidence(item), countermeasure=item,
        )
        for item in countermeasures.for_domain(domain)
    ]


# --------------------------------------------------------------------------- #
# Qué cuesta comprobar (KB §9)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("domain", list(Domain))
def test_each_check_carries_the_cost_of_what_it_repeats_as_cost_py_says(domain: Domain) -> None:
    for item in support(domain, _library(domain))["checks"]["items"]:
        measure = countermeasures.get(item["id"])
        shown = item["cost"]
        # El tiempo de la acción es el de la biblioteca, con su base; sin cifra, se dice.
        assert shown["action"]["minutes"] == measure.crew_time_minutes
        # De dónde sale el tiempo; «sin fuente» no se repite junto a «sin cifra con fuente».
        assert shown["action"]["basis"] == (
            None if measure.crew_time_basis == "sin fuente" else measure.crew_time_basis
        )
        assert shown["action"]["missing"] is (measure.crew_time_minutes is None)
        if measure.crew_time_minutes is None:
            assert shown["action"]["display"] == NO_FIGURE
        assert [row["key"] for row in shown["indicators"]] == list(measure.followup_checks)
        assert shown["statement"] == (None if measure.followup_checks else NO_REPEAT)
        for row in shown["indicators"]:
            source = cost.cost(row["key"])
            assert source is not None
            facts = {fact["key"]: fact for fact in row["facts"]}
            assert list(facts) == ["mode", "crew_time", *cost.DIMENSIONS]
            assert facts["mode"]["display"] == source["mode_display"]
            assert facts["crew_time"]["missing"] is (source["crew_time_minutes"] is None)
            assert facts["crew_time"]["basis"] == (
                None if source["crew_time_basis"] == "sin fuente" else source["crew_time_basis"]
            )
            for dimension in cost.DIMENSIONS:
                held = source["dimensions"][dimension]
                assert facts[dimension]["display"] == held["display"]
                assert facts[dimension]["label"] == cost.DIMENSIONS[dimension]["display"]
                # «Sin clasificar» sigue sin clasificar: se marca como ausente, no se rellena.
                assert facts[dimension]["missing"] is (held["value"] == cost.UNCLASSIFIED)


def test_a_stated_figure_travels_with_its_fact(monkeypatch: pytest.MonkeyPatch) -> None:
    # Decimosexta ronda: la cifra leída de masa, volumen o potencia va con su dato, para que la
    # interfaz la formatee (`lib/format.ts`) igual que en el panel del coste de medir.
    figure = {"amount": 10.32, "decimals": 2, "unit": "lbs", "figure": "10.32"}
    real = cost.dimensions()
    left = real["ijv-csa-left"]
    stated = {**left["mass"], "value": cost.STATED, "display": "10,32 lbs", "figure": figure}
    held = {**real, "ijv-csa-left": {**left, "mass": stated}}
    monkeypatch.setattr(cost, "dimensions", lambda: held)
    facts = {
        fact["key"]: fact for fact in check_cost_module._indicator_cost("ijv-csa-left")["facts"]
    }
    assert facts["mass"]["figure"] == figure and facts["mass"]["missing"] is False
    assert facts["processing"]["figure"] is None


def test_the_checks_keep_the_recommenders_order_whatever_they_cost() -> None:
    for domain in Domain:
        mine = _library(domain)
        for order in (mine, list(reversed(mine))):
            shown = support(domain, order)["checks"]
            assert [item["id"] for item in shown["items"]] == [
                rec.countermeasure.id for rec in order  # type: ignore[union-attr]
            ]
            assert shown["order_note"] == (alert_support.COST_ORDER_NOTE if mine else None)


def test_the_unclassified_note_is_said_once_when_some_check_needs_it() -> None:
    heart = _library(Domain.CARDIOVASCULAR)
    shown = support(Domain.CARDIOVASCULAR, heart)["checks"]
    # El consumible de la frecuencia cardiaca está sin clasificar en `measurement_cost.json`.
    assert cost.cost("heart-rate")["dimensions"]["consumables"]["value"] == cost.UNCLASSIFIED  # type: ignore[index]
    assert shown["unclassified_note"] == cost.UNCLASSIFIED_NOTE


def test_an_indicator_outside_the_cost_table_is_unclassified_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cost, "cost", lambda key: None)
    measure = countermeasures.get("cv-repeat-rest")
    [row] = check_cost(measure)["indicators"]
    assert all(fact["missing"] for fact in row["facts"])
    assert {fact["display"] for fact in row["facts"]} == {cost.UNCLASSIFIED_DISPLAY, NO_FIGURE}
    shown = support(Domain.CARDIOVASCULAR, _library(Domain.CARDIOVASCULAR))["checks"]
    assert shown["unclassified_note"] == cost.UNCLASSIFIED_NOTE


def test_a_check_without_countermeasure_or_without_repeat_says_so() -> None:
    assert check_cost(None) == {"action": None, "indicators": [], "statement": NO_COUNTERMEASURE}
    bare = countermeasures.get("sans-vision-log")
    assert bare.followup_checks == ()
    assert check_cost(bare)["statement"] == NO_REPEAT


# --------------------------------------------------------------------------- #
# Cuánto cambió frente a la mediana personal
# --------------------------------------------------------------------------- #

def test_the_relative_change_is_value_minus_median_over_median() -> None:
    above = relative_change(_deviation("heart-rate", 70.0))
    assert (above["applies"], above["percent"], above["median"]) == (True, 40.0, 50.0)
    assert above["statement"] == "Un 40 % por encima de su mediana personal."
    # El ejemplo de la conversación de ideación: la variabilidad, un 14 % por debajo.
    below = relative_change(_deviation("hrv-sdnn", 43.0))
    assert below["percent"] == -14.0
    assert below["statement"] == "Un 14 % por debajo de su mediana personal."
    small = relative_change(_deviation("heart-rate", 52.0))
    assert small["statement"].startswith("Un 4,0 % por encima")
    same = relative_change(_deviation("heart-rate", 50.0))
    assert same["statement"].startswith("Sin cambio apreciable")
    # Los decimales salen de la cifra redondeada: 9,96 % se lee «10 %», como 10,2 %.
    edge = relative_change(_deviation("heart-rate", 54.98))
    assert edge["statement"].startswith("Un 10 % por encima")


def test_a_percentage_says_it_is_relative_and_not_points() -> None:
    shown = relative_change(_deviation("oxygen-saturation", 93.0, (96.0, 98.0, 99.0)))
    assert shown["applies"] is True
    assert shown["statement"].endswith(PERCENT_NOTE)


@pytest.mark.parametrize(
    ("key", "reason"),
    [
        ("mood-valence", NOT_RATIO_UNITS["{score}"]),
        ("pain-intensity", NOT_RATIO_UNITS["{score}"]),
        ("body-temperature", NOT_RATIO_UNITS["Cel"]),
        ("circadian-shift", NOT_RATIO_KEYS["circadian-shift"]),
        ("orthostatic-drop", NOT_RATIO_KEYS["orthostatic-drop"]),
        ("urine-specific-gravity", NOT_RATIO_KEYS["urine-specific-gravity"]),
        ("cumulative-dose", NOT_RATIO_KEYS["cumulative-dose"]),
    ],
)
def test_where_the_scale_is_not_a_ratio_it_says_why_and_gives_no_figure(
    key: str, reason: str
) -> None:
    shown = relative_change(_deviation(key, 9.0, (1.0, 2.0, 3.0)))
    assert (shown["applies"], shown["percent"], shown["median"]) == (False, None, None)
    assert shown["statement"] == f"Sin cambio relativo: {reason}."


def test_with_median_zero_population_range_or_no_baseline_there_is_no_figure() -> None:
    zero = relative_change(_deviation("pvt-lapses", 4.0, (0.0, 0.0, 1.0)))
    assert (zero["applies"], zero["percent"]) == (False, None)
    assert "no es positiva" in zero["statement"]
    population = relative_change(_deviation("heart-rate", 130.0, population=True))
    assert (population["applies"], population["percent"]) == (False, None)
    assert "rango poblacional" in population["statement"]
    empty = relative_change(_deviation("heart-rate", 70.0, ()))
    assert (empty["applies"], empty["percent"]) == (False, None)


def test_the_scale_table_is_closed_and_a_new_unit_is_not_computed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    units = {code.unit for code in CATALOG.values()}
    assert not RATIO_UNITS & NOT_RATIO_UNITS.keys()
    # Toda unidad del catálogo está decidida; ninguna decisión sobra.
    assert units <= RATIO_UNITS | NOT_RATIO_UNITS.keys()
    assert RATIO_UNITS | NOT_RATIO_UNITS.keys() <= units
    assert NOT_RATIO_KEYS.keys() <= CATALOG.keys()
    for key in NOT_RATIO_KEYS:
        assert CATALOG[key].unit in RATIO_UNITS, f"{key}: la excepción por clave sobra"
    monkeypatch.setattr(alert_support, "get", lambda key: SimpleNamespace(unit="[furlong]"))
    assert scale_reason("heart-rate") == UNDECLARED_SCALE


def test_explain_carries_the_relative_change_of_each_change() -> None:
    current = [_deviation("heart-rate", 70.0), _deviation("body-temperature", 38.4)]
    shown = explain.detail(Domain.CARDIOVASCULAR, current, [])
    by_key = {item["key"]: item["relative_change"] for item in shown["changed"]}
    assert by_key["heart-rate"]["percent"] == 40.0
    assert by_key["body-temperature"]["applies"] is False
    assert shown["sensed"] == {"readings": 2, "indicators": 2}


# --------------------------------------------------------------------------- #
# Por qué paso va la alerta (KB §10)
# --------------------------------------------------------------------------- #

def _falling(key: str) -> Trend:
    return Trend(
        key=key, slope_per_day=-0.5, t_statistic=12.0, points=60, span_days=20.0,
        direction=Direction.FALLING, significant=True, mean_value=6.0, standard_error=0.0,
    )


ALERT: dict[str, Any] = {
    "domain": "cardiovascular", "level": "concern", "acknowledged": False,
    "acknowledged_by": None, "acknowledgement_index": None,
    "resolution": {"state": "detectado"},
}


def _detail(**extra: Any) -> dict[str, Any]:
    current = [_deviation("heart-rate", 70.0), _deviation("heart-rate", 50.0, concerning=False)]
    shown = explain.detail(
        Domain.CARDIOVASCULAR, current, [], _library(Domain.CARDIOVASCULAR)
    )
    return {**shown, **extra}


def _followup(state: str, adopted: dt.datetime, domain: str = "cardiovascular") -> dict[str, Any]:
    measure = countermeasures.get("cv-repeat-rest")
    return {
        "adoption_index": 41, "countermeasure": measure.to_dict(), "domain": domain,
        "adopted_at": adopted.isoformat(), "adopted_by": "CDR", "state": state,
        "closed_by": "FE" if state == "closed" else None,
    }


def _steps(alert: dict[str, Any], detail: dict[str, Any], followups: Any = ()) -> dict[str, Any]:
    return {step["key"]: step for step in alert_flow.flow(alert, detail, followups)["steps"]}


def test_the_eight_steps_are_the_knowledge_base_flow_in_its_order() -> None:
    result = alert_flow.flow(ALERT, _detail())
    assert [step["kb_name"] for step in result["steps"]] == [
        "SENSE", "CONTEXTUALIZE", "DETECT", "EXPLAIN", "RELATE TO RISK",
        "RECOMMEND CHECK/COUNTERMEASURE", "HUMAN DECISION", "FOLLOW-UP",
    ]
    # La convención de las hipótesis: los mismos estados y las mismas palabras.
    for step in result["steps"]:
        assert step["state"] in context.STEP_STATE_DISPLAY
        assert step["state_display"] == context.STEP_STATE_DISPLAY[step["state"]]
        assert step["detail"]
    assert result["basis"] == alert_flow.BASIS


def test_an_unattended_alert_waits_for_a_person() -> None:
    steps = _steps(ALERT, _detail())
    assert steps["sense"]["state"] == context.DONE
    assert steps["sense"]["detail"].startswith("2 lecturas de 1 indicador")
    assert steps["contextualize"]["state"] == context.NOT_APPLICABLE
    assert steps["detect"]["state"] == context.DONE
    assert steps["relate_to_risk"]["detail"].startswith("Nivel «precaución» en el dominio.")
    assert steps["recommend"]["state"] == context.DONE
    assert steps["human_decision"]["state"] == context.AWAITING_HUMAN
    assert steps["follow_up"]["state"] == context.NOT_APPLICABLE


def test_acknowledgement_declaration_and_adoption_are_the_human_decision() -> None:
    acknowledged = {
        **ALERT, "acknowledged": True, "acknowledged_by": "CDR", "acknowledgement_index": 12,
        "resolution": {"state": "en_arreglo", "declared_by": "FE", "ledger_index": 13},
    }
    detail = _detail(context={"summary": "Registrado dentro de la ventana: 1.",
                              "label": "correlación temporal, no causa"})
    steps = _steps(acknowledged, detail, [_followup("in_window", _h(1))])
    assert steps["contextualize"]["state"] == context.DONE
    decision = steps["human_decision"]
    assert decision["state"] == context.DONE
    for said in ("Reconocida por CDR (asiento 12", "«en arreglo» por FE (asiento 13",
                 "Contramedida adoptada por CDR", "(asiento 41"):
        assert said in decision["detail"]
    assert steps["follow_up"]["state"] == context.IN_PROGRESS


def test_a_dismissal_alone_is_the_human_decision() -> None:
    dismissed = {**ALERT, "dismissal": {
        "declared_by": "CMO", "reason_display": "artefacto del sensor", "ledger_index": 14,
    }}
    decision = _steps(dismissed, _detail())["human_decision"]
    assert decision["state"] == context.DONE
    assert "Descartada por CMO, motivo: artefacto del sensor (asiento 14" in decision["detail"]


@pytest.mark.parametrize(
    ("state", "expected"),
    [("in_window", context.IN_PROGRESS), ("due", context.AWAITING_HUMAN),
     ("closed", context.DONE)],
)
def test_the_follow_up_step_follows_the_signed_follow_up(state: str, expected: str) -> None:
    steps = _steps(ALERT, _detail(), [_followup(state, _h(1))])
    assert steps["follow_up"]["state"] == expected
    assert steps["human_decision"]["state"] == context.DONE
    if state == "closed":
        assert "cerrada por FE" in steps["follow_up"]["detail"]


def test_closed_adoptions_before_the_onset_or_of_another_domain_are_not_this_alerts() -> None:
    detail = _detail()
    assert detail["onset"] == _h(0).isoformat()
    others = [_followup("closed", _h(-1)), _followup("in_window", _h(1), domain="bone")]
    steps = _steps(ALERT, detail, others)
    assert steps["human_decision"]["state"] == context.AWAITING_HUMAN
    assert steps["follow_up"]["state"] == context.NOT_APPLICABLE


def test_an_open_follow_up_adopted_before_the_moving_onset_still_counts() -> None:
    # El inicio es la primera lectura fuera de lo esperado de la ventana actual, que avanza:
    # una contramedida de 72 h adoptada hace 60 h sigue en seguimiento aunque quede antes.
    for state, expected in (("in_window", context.IN_PROGRESS), ("due", context.AWAITING_HUMAN)):
        steps = _steps(ALERT, _detail(), [_followup(state, _h(-60))])
        assert steps["human_decision"]["state"] == context.DONE
        assert steps["follow_up"]["state"] == expected


def test_without_onset_the_open_adoptions_of_the_domain_count() -> None:
    trend_only = explain.detail(Domain.BEHAVIORAL, [], [_falling("sleep-duration")])
    alert = {**ALERT, "domain": "behavioral"}
    open_one = _followup("in_window", _h(-50), domain="behavioral")
    closed = _followup("closed", _h(-50), domain="behavioral")
    assert alert_flow.adopted_for(alert, None, [open_one, closed]) == [open_one]
    steps = _steps(alert, trend_only, [closed])
    assert steps["sense"]["state"] == context.DONE
    assert "tendencia" in steps["sense"]["detail"]
    assert steps["follow_up"]["state"] == context.NOT_APPLICABLE


def test_an_alert_from_an_external_event_does_not_pretend_to_have_readings() -> None:
    detail = explain.detail(Domain.RADIATION, [], [])
    steps = _steps({**ALERT, "domain": "radiation"}, detail)
    assert steps["sense"]["state"] == context.NOT_APPLICABLE
    assert steps["detect"]["state"] == context.NOT_APPLICABLE
    assert alert_flow.EXTERNAL in steps["sense"]["detail"]


def test_every_new_sentence_passes_the_language_guard() -> None:
    texts: list[str] = [
        alert_support.COST_ORDER_NOTE, NO_FIGURE, NO_REPEAT, NO_COUNTERMEASURE,
        alert_support.RELATIVE_BASIS, PERCENT_NOTE, UNDECLARED_SCALE,
        *NOT_RATIO_UNITS.values(), *NOT_RATIO_KEYS.values(), alert_flow.BASIS,
        alert_flow.AWAITING_DECISION, alert_flow.NO_FOLLOW_UP,
    ]
    for domain in Domain:
        for item in support(domain, _library(domain))["checks"]["items"]:
            # Sin el nombre del indicador: «dosis» de radiación es un nombre del catálogo, no una
            # dosis de un fármaco, y el linter no lo distingue.
            texts += [
                row["statement"].removeprefix(f"{row['display_es']}: ")
                for row in item["cost"]["indicators"]
            ]
    for key in ("heart-rate", "hrv-sdnn", "mood-valence", "pvt-lapses"):
        texts.append(relative_change(_deviation(key, 43.0, (0.0, 50.0, 60.0)))["statement"])
    for state in ("in_window", "due", "closed"):
        acknowledged = {**ALERT, "acknowledged": True, "acknowledged_by": "CDR",
                        "acknowledgement_index": 3}
        texts += [step["detail"] for step in alert_flow.flow(
            acknowledged, _detail(), [_followup(state, _h(1))]
        )["steps"]]
    texts += [step["detail"] for step in alert_flow.flow(ALERT, _detail())["steps"]]
    assert len(set(texts)) > 30, "la prueba tiene que mirar textos de verdad"
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


def test_the_engine_does_not_know_the_flow_and_the_flow_cannot_decide() -> None:
    for engine in (risk, baseline, trend):
        assert not [name for name in _imported_names(engine) if "alert_flow" in name]
    source = inspect.getsource(alert_flow)
    for decides in ("RiskEngine", "BaselineEngine", "level_for", "combine_findings", "score"):
        assert decides not in source


# --------------------------------------------------------------------------- #
# De punta a punta: el veredicto no se mueve (invariante 5)
# --------------------------------------------------------------------------- #

@pytest.fixture
def client(tmp_path: Any) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _verdict(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "overall": status["overall_level"],
        "summary": status["summary"],
        "domains": {
            key: (value["score"], value["level"], value["drivers"])
            for key, value in status["domains"].items()
        },
        "alerts": [
            {key: value for key, value in alert.items() if key != "detail"}
            | {"onset": alert["detail"]["onset"]}
            for alert in status["alerts"]
        ],
        "recommendations": status["recommendations"],
        "followups": status["followups"],
    }


def test_the_verdict_is_identical_with_and_without_cost_flow_and_relative_change(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.post("/api/simulate", params={"scenario": "dehydration", "days": 40, "crew_size": 1})
    first = client.get("/api/status").json()
    alert = first["alerts"][0]
    measure = next(
        item["countermeasure"] for item in first["recommendations"]
        if item["domain"] == alert["domain"] and item["countermeasure"]
    )
    assert client.post("/api/alerts/acknowledge", json={
        "domain": alert["domain"], "level": alert["level"],
        "reference_time": first["data"]["reference_time"], "acknowledged_by": "CDR",
    }).status_code == 201
    assert client.post("/api/countermeasures/adopt", json={
        "countermeasure_id": measure["id"], "reference_time": first["data"]["reference_time"],
        "adopted_by": "CDR",
    }).status_code == 201

    full = client.get("/api/status").json()
    shown = next(item for item in full["alerts"] if item["domain"] == alert["domain"])
    steps = {step["key"]: step for step in shown["detail"]["flow"]["steps"]}
    assert steps["human_decision"]["state"] == context.DONE
    assert "Reconocida por CDR" in steps["human_decision"]["detail"]
    assert "Contramedida adoptada por CDR" in steps["human_decision"]["detail"]
    assert steps["follow_up"]["state"] == context.IN_PROGRESS
    for item in full["alerts"]:
        assert all("relative_change" in change for change in item["detail"]["changed"])
        assert all("cost" in check_ for check_ in item["detail"]["checks"]["items"])

    monkeypatch.setattr(alert_flow, "flow", lambda *args, **kwargs: {})
    monkeypatch.setattr(alert_support, "relative_change", lambda *args, **kwargs: {})
    monkeypatch.setattr(check_cost_module, "of", lambda *args, **kwargs: {})
    bare = client.get("/api/status").json()
    for item in bare["alerts"]:
        assert item["detail"]["flow"] == {}
    assert _verdict(bare) == _verdict(full)
