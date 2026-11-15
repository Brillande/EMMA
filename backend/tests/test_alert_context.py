"""Contexto alrededor de una alerta y concordancia entre señales (especificación §3, §6, §10).

Qué fijan estas pruebas:
- qué entra en la ventana y qué no, en sus dos bordes y en el del instante del estado;
- que cada elemento va rotulado «correlación temporal, no causa»;
- que lo que no se tiene se dice («sin dato»), fuente a fuente, en vez de callarlo;
- que la concordancia cuenta con la misma regla de hallazgo del motor, y nada más;
- que todo el texto que redacta el sistema pasa el linter de lenguaje (invariante 7);
- y la que importa (invariante 5): los niveles de un escenario son idénticos con y sin esta capa.
"""

import ast
import datetime as dt
import inspect
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.advisor import countermeasures
from app.analysis import alert_context, baseline, explain, risk, trend
from app.analysis.alert_context import (
    CONCORDANCE_BASIS,
    LABEL,
    NOTE,
    NOTE_WITHOUT_ALERT,
    WINDOW_AFTER,
    WINDOW_BASIS,
    WINDOW_BEFORE,
    SolarRecord,
    around,
    concordance,
)
from app.analysis.baseline import Baseline, Deviation, Severity, SeverityBasis
from app.analysis.context import (
    ASSUMPTION,
    ASSUMPTION_ESTIMATED_LOCATED,
    ASSUMPTION_LOCATED,
    NOT_COMPARABLE,
    Stay,
)
from app.analysis.trend import Direction, Trend
from app.api import routes
from app.environment.donki import EventType, SolarEvent
from app.environment.donki import Severity as SolarSeverity
from app.environment.habitat import PARAMETERS, HabitatReading, excursions
from app.ingest.codes import Domain
from app.ingest.habitat_simulator import NOMINAL, HabitatSimulator
from app.text_guard import check

START = dt.date(2026, 11, 1)
# Inicio de la alerta: día de misión 19,5, en plena fase estable.
T0 = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.UTC)
REFERENCE = T0 + dt.timedelta(hours=30)


def _h(hours: float) -> dt.datetime:
    return T0 + dt.timedelta(hours=hours)


def _context(**override: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "onset": T0, "reference": REFERENCE, "habitat_readings": [], "habitat_excursions": [],
        "mission_events": [], "solar": None, "adoptions": [], "mission_start": START,
        "mission_days": 180, "gravity_regime": "microgravedad",
    }
    arguments.update(override)
    return around(**arguments)


def _cabin(co2_by_hour: dict[int, float]) -> dict[str, Any]:
    """Lecturas horarias de CO2 (hora respecto al inicio → mmHg) y sus excursiones."""
    readings = [
        HabitatReading("m1", "cabin-ppco2", value, _h(hour), "habitat-telemetry")
        for hour, value in sorted(co2_by_hour.items())
    ]
    return {"habitat_readings": readings, "habitat_excursions": excursions(readings)}


def _event(kind: str, start: float, end: float, label: str, index: int = 7) -> dict[str, Any]:
    return {
        "kind": kind, "start": _h(start).isoformat(), "end": _h(end).isoformat(),
        "label": label, "declared_by": "CDR", "ledger_index": index,
    }


def _adoption(hours: float, countermeasure_id: str, index: int = 12) -> dict[str, Any]:
    return {
        "action": "adopted", "countermeasure_id": countermeasure_id, "domain": "behavioral",
        "level": "watch", "reference_time": _h(hours).isoformat(), "decided_by": "CMO",
        "reason": "", "adoption_index": "", "ledger_index": index,
    }


def _solar(*hours: float, known: tuple[float, float] = (-100, 100)) -> SolarRecord:
    return SolarRecord(
        events=[
            SolarEvent(
                f"SEP-{index}", EventType.SEP, _h(hour), SolarSeverity.HIGH, (), (), None, ""
            )
            for index, hour in enumerate(hours)
        ],
        known_from=_h(known[0]), known_until=_h(known[1]),
    )


def _of(context: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [item for item in context["items"] if item["kind"] == kind]


def _source(context: dict[str, Any], kind: str) -> dict[str, Any]:
    [source] = [item for item in context["sources"] if item["kind"] == kind]
    return source


# --------------------------------------------------------------------------- #
# La ventana
# --------------------------------------------------------------------------- #

def test_the_window_is_a_declared_design_parameter() -> None:
    context = _context()
    assert context["window_start"] == (T0 - WINDOW_BEFORE).isoformat()
    assert context["window_end"] == (T0 + WINDOW_AFTER).isoformat()
    assert (context["window_hours_before"], context["window_hours_after"]) == (24.0, 6.0)
    assert "diseño EMMA" in WINDOW_BASIS and "sin fuente" in WINDOW_BASIS
    assert context["window_basis"] == WINDOW_BASIS


def test_an_excursion_that_overlaps_the_onset_is_listed_as_temporal_correlation() -> None:
    # CO2 nominal hasta 6 h antes del inicio; desde ahí, 4,5 mmHg (límite 3 en media de 1 h).
    cabin = _cabin({hour: (4.5 if hour >= -6 else 2.0) for hour in range(-12, 3)})
    [item] = _of(_context(**cabin), "habitat")
    assert item["label"] == LABEL == "correlación temporal, no causa"
    assert item["title"] == (
        "CO2 de cabina (presión parcial) fuera de su límite normativo ([V2 6004])"
    )
    assert (item["start"], item["end"]) == (_h(-6).isoformat(), _h(2).isoformat())
    assert item["timing"] == (
        "fuera de límite en el inicio de la alerta; primera lectura fuera de límite 6,0 h antes"
    )
    assert (item["value"], item["unit"]) == (4.5, "mm[Hg]")
    assert item["source"] == "telemetría de cabina, módulo m1"


def test_an_excursion_outside_the_window_is_not_context() -> None:
    # Fuera de límite de 72 a 48 h antes; después, nominal y con el sensor midiendo.
    before = _cabin({hour: (4.5 if -72 <= hour <= -48 else 2.0) for hour in range(-80, 3)})
    assert before["habitat_excursions"], "la prueba necesita que la excursión exista"
    context = _context(**before)
    assert _of(context, "habitat") == []
    assert _source(context, "habitat")["found"] == 0
    assert _source(context, "habitat")["status"] != "no_data"

    # Y una que empieza pasada la ventana (10 h después del inicio) tampoco.
    after = _cabin({hour: (4.5 if hour >= 10 else 2.0) for hour in range(-12, 20)})
    assert after["habitat_excursions"]
    assert _of(_context(**after), "habitat") == []


def test_the_window_edges_are_inclusive_and_nothing_beyond_them_enters() -> None:
    touching = _cabin({hour: (4.5 if -30 <= hour <= -24 else 2.0) for hour in range(-36, 3)})
    assert len(_of(_context(**touching), "habitat")) == 1
    just_out = _cabin({hour: (4.5 if -30 <= hour <= -25 else 2.0) for hour in range(-36, 3)})
    assert _of(_context(**just_out), "habitat") == []

    events = [_event("eva", 6, 9, "sale en el borde"), _event("eva", 6.5, 9, "ya fuera")]
    assert [item["detail"] for item in _of(_context(mission_events=events), "mission_event")] == [
        "sale en el borde"
    ]


def test_a_comfort_zone_excursion_is_not_listed() -> None:
    # 26 °C: fuera de la zona de rendimiento [V2 6013], dentro del límite de salud [V2 6012].
    readings = [
        HabitatReading("m1", "cabin-temperature", 26.0, _h(hour), "habitat-telemetry")
        for hour in range(-6, 3)
    ]
    found = excursions(readings)
    assert [item.kind for item in found] == ["performance"]
    context = _context(habitat_readings=readings, habitat_excursions=found)
    assert _of(context, "habitat") == []
    assert "zona de confort" in _source(context, "habitat")["note"]


def test_an_eva_inside_the_window_is_listed_and_one_outside_is_not() -> None:
    events = [
        _event("eva", -20, -14, "EVA 3: sustitución de bomba"),
        _event("workload", -120, -112, "Mantenimiento de hace cinco días", index=3),
    ]
    context = _context(mission_events=events)
    [item] = _of(context, "mission_event")
    assert item["title"] == "EVA declarada"
    assert item["detail"] == "EVA 3: sustitución de bomba"
    assert item["label"] == LABEL
    assert item["timing"] == "terminó 14,0 h antes del inicio de la alerta"
    assert item["source"] == "declarado por CDR, asiento 7"
    source = _source(context, "mission_event")
    assert (source["status"], source["found"]) == ("with_data", 1)


def test_a_work_block_in_progress_says_so_without_implying_cause() -> None:
    [item] = _of(
        _context(mission_events=[_event("workload", -2, 3, "Turno doble")]), "mission_event"
    )
    assert item["title"] == "Bloque de trabajo declarado"
    assert item["timing"] == "en curso en el inicio de la alerta; empezó 2,0 h antes"
    [later] = _of(_context(mission_events=[_event("eva", 2, 4, "EVA 4")]), "mission_event")
    assert later["timing"] == "empezó 2,0 h después del inicio de la alerta"


def test_nothing_after_the_state_instant_enters_the_window() -> None:
    # El estado es de una hora después del inicio; la EVA está declarada para más tarde.
    context = _context(
        reference=_h(1),
        mission_events=[_event("eva", 3, 5, "EVA planificada")],
        adoptions=[_adoption(2, "bh-protect-sleep")],
        solar=_solar(4),
    )
    assert context["window_end"] == _h(1).isoformat()
    assert context["items"] == []


# --------------------------------------------------------------------------- #
# Lo que no se tiene, se dice
# --------------------------------------------------------------------------- #

def test_without_habitat_readings_the_context_says_no_data() -> None:
    silent = _source(_context(), "habitat")
    assert (silent["status"], silent["status_display"]) == ("no_data", "sin dato")
    assert silent["found"] == 0
    assert "no se sabe si cambió" in silent["note"]

    # Lecturas hay, pero todas de antes de la ventana: tampoco se puede decir que no cambió.
    old = _cabin({hour: 2.0 for hour in range(-90, -30)})
    context = _context(**old)
    assert _source(context, "habitat")["status"] == "no_data"
    assert _of(context, "habitat") == []


def test_a_parameter_without_readings_is_named() -> None:
    only_co2 = _source(_context(**_cabin({hour: 2.0 for hour in range(-12, 3)})), "habitat")
    assert only_co2["status"] == "partial"
    for key, spec in PARAMETERS.items():
        assert (spec.display in only_co2["note"]) == (key != "cabin-ppco2")


def test_the_simulated_co2_excursion_is_context_with_every_sensor_reporting() -> None:
    readings = list(HabitatSimulator(co2_excursion=True, mission_start=START).generate(days=20))
    assert {item.parameter for item in readings} == set(NOMINAL)
    onset = dt.datetime(2026, 11, 19, 5, 0, tzinfo=dt.UTC)
    context = _context(
        onset=onset, reference=dt.datetime(2026, 11, 20, 23, 0, tzinfo=dt.UTC),
        habitat_readings=readings, habitat_excursions=excursions(readings),
    )
    [item] = _of(context, "habitat")
    assert item["title"].startswith("CO2 de cabina") and item["value"] > 3.0
    assert item["timing"].startswith("fuera de límite en el inicio de la alerta")
    source = _source(context, "habitat")
    assert (source["status"], source["status_display"], source["found"]) == (
        "with_data", "con dato", 1
    )
    assert "se supone que toda la tripulación comparte el hábitat" in source["note"]


def test_no_declared_events_is_not_the_same_as_no_events() -> None:
    source = _source(_context(), "mission_event")
    assert (source["status"], source["found"]) == ("no_data", 0)
    assert "que no conste no quiere decir que no lo hubiera" in source["note"]


def test_a_solar_event_is_context_only_where_the_data_reach() -> None:
    absent = _source(_context(), "solar_event")
    assert absent["status"] == "no_data" and "Sin datos de NASA DONKI" in absent["note"]

    context = _context(solar=_solar(-2, -40, 9))
    [item] = _of(context, "solar_event")
    assert (item["title"], item["detail"]) == ("Evento solar SEP", "SEP-0")
    assert item["source"] == "NASA DONKI"
    assert item["timing"] == "2,0 h antes del inicio de la alerta"
    assert item["label"] == LABEL
    source = _source(context, "solar_event")
    assert (source["status"], source["found"]) == ("with_data", 1)

    # El dato no alcanza la ventana: no se dice «ningún evento», se dice que no se sabe.
    stale = _context(solar=_solar(known=(-200, -60)))
    assert _source(stale, "solar_event")["status"] == "no_data"
    assert "no cubren la ventana" in _source(stale, "solar_event")["note"]
    empty = _context(solar=_solar(known=(-10, -60)))
    assert _source(empty, "solar_event")["status"] == "no_data"

    partial = _context(solar=_solar(-2, known=(-10, 100)))
    assert _source(partial, "solar_event")["status"] == "partial"
    assert len(_of(partial, "solar_event")) == 1


def test_an_adopted_countermeasure_in_the_window_is_context() -> None:
    known = countermeasures.get("bh-protect-sleep")
    context = _context(adoptions=[
        _adoption(2, "bh-protect-sleep"),
        _adoption(-72, "bh-circadian-lighting", index=4),
        _adoption(-1, "retirada-de-la-biblioteca", index=13),
    ])
    retired, adopted = _of(context, "countermeasure")
    assert adopted["title"] == "Contramedida adoptada"
    assert adopted["detail"] == known.action
    assert adopted["timing"] == "2,0 h después del inicio de la alerta"
    assert adopted["source"] == "decisión de CMO, asiento 12"
    assert adopted["label"] == LABEL
    # Una adopción firmada no se esconde porque su ficha ya no esté en la biblioteca.
    assert retired["detail"] == "retirada-de-la-biblioteca"
    assert _source(context, "countermeasure")["found"] == 2


def test_a_phase_change_inside_the_window_is_listed_with_its_design_origin() -> None:
    onset = dt.datetime(2026, 11, 15, 3, 0, tzinfo=dt.UTC)  # 3 h después del día 14
    context = _context(onset=onset, reference=onset + dt.timedelta(hours=12))
    [item] = _of(context, "phase_change")
    assert item["title"] == "Cambio de fase de misión: de adaptación a fase estable"
    assert item["timing"] == "3,0 h antes del inicio de la alerta"
    assert "diseño EMMA" in item["source"] and item["label"] == LABEL
    assert context["mission"]["statement"] == (
        "Inicio de la alerta: día de misión 14,1, fase estable, microgravedad."
    )
    assert _of(_context(), "phase_change") == []
    assert _source(_context(), "phase_change")["found"] == 0


def test_after_landing_the_alert_statement_gives_the_gravity_of_the_moment() -> None:
    onset = dt.datetime(2027, 5, 5, 12, 0, tzinfo=dt.UTC)  # día 185,5: posvuelo
    context = _context(onset=onset, reference=onset + dt.timedelta(hours=6))
    assert context["mission"]["statement"] == (
        "Inicio de la alerta: día de misión 185,5, posvuelo y recuperación, "
        "en Tierra (gravedad terrestre); "
        "gravedad de la misión, declarada por configuración: microgravedad."
    )


def test_without_an_alert_there_is_no_onset_to_hang_from_and_no_alert_in_the_note() -> None:
    """El modo anatómico pide el contexto de una región sin alerta: ni inicio ni «la alerta»."""
    context = _context(alert=False, mission_events=[_event("eva", 20, 26, "EVA 5")])
    assert context["anchor"] == REFERENCE.isoformat()
    assert context["anchor_basis"] == "sin alerta: se toma el instante del estado"
    assert context["note"] == NOTE_WITHOUT_ALERT != NOTE
    assert "alerta" not in context["note"]
    assert context["mission"]["statement"].startswith("Instante del estado")
    assert [item["timing"] for item in context["items"]] == [
        "terminó 4,0 h antes del instante del estado",
    ]
    assert check(NOTE_WITHOUT_ALERT) == []
    # Con alerta, el mismo inicio sigue mandando.
    assert _context(mission_events=[_event("eva", 20, 26, "EVA 5")])["anchor"] == T0.isoformat()


def test_without_an_onset_the_window_hangs_from_the_state_instant_and_says_so() -> None:
    context = _context(
        onset=None, mission_events=[_event("eva", 20, 26, "EVA 5")], solar=_solar(30),
    )
    assert context["anchor"] == REFERENCE.isoformat()
    assert "instante del estado" in context["anchor_basis"]
    assert (context["window_start"], context["window_end"]) == (
        (REFERENCE - WINDOW_BEFORE).isoformat(), REFERENCE.isoformat()
    )
    assert context["mission"]["statement"].startswith("Instante del estado: día de misión 20,8")
    assert [item["timing"] for item in context["items"]] == [
        "terminó 4,0 h antes del instante del estado", "a la vez que el instante del estado",
    ]


def _rich() -> dict[str, Any]:
    """Un contexto con un elemento de cada clase."""
    onset = dt.datetime(2026, 11, 15, 12, 0, tzinfo=dt.UTC)
    hour = lambda hours: (onset + dt.timedelta(hours=hours))  # noqa: E731
    readings = [
        HabitatReading("m1", "cabin-ppco2", 4.5, hour(offset), "habitat-telemetry")
        for offset in range(-6, 3)
    ]
    return around(
        onset=onset, reference=onset + dt.timedelta(hours=30),
        habitat_readings=readings, habitat_excursions=excursions(readings),
        mission_events=[{
            "kind": "eva", "start": hour(-20).isoformat(), "end": hour(-14).isoformat(),
            "label": "EVA 3", "declared_by": "CDR", "ledger_index": 7,
        }],
        solar=SolarRecord(
            [SolarEvent("SEP-1", EventType.SEP, hour(-2), SolarSeverity.HIGH, (), (), None, "")],
            hour(-100), hour(100),
        ),
        adoptions=[{
            "countermeasure_id": "bh-protect-sleep", "reference_time": hour(2).isoformat(),
            "decided_by": "CMO", "ledger_index": 12,
        }],
        mission_start=START, mission_days=180, gravity_regime="microgravedad",
    )


def test_every_item_carries_the_not_a_cause_label() -> None:
    context = _rich()
    assert {item["kind"] for item in context["items"]} == {
        "habitat", "mission_event", "phase_change", "solar_event", "countermeasure",
    }
    assert [item["label"] for item in context["items"]] == [LABEL] * 5
    assert context["label"] == LABEL
    assert context["summary"] == "Registrado dentro de la ventana: 5."
    assert _context()["summary"] == "Nada de lo registrado cae dentro de la ventana."
    assert context["note"] == NOTE
    assert "no dice que sea su causa" in NOTE and "no cambia el nivel" in NOTE
    assert [item["start"] for item in context["items"]] == sorted(
        item["start"] for item in context["items"]
    )


# --------------------------------------------------------------------------- #
# Concordancia entre señales
# --------------------------------------------------------------------------- #

def _deviations(key: str, concerning: int, total: int = 10, first_hour: int = 0,
                direction: str = "high", severity: Severity = Severity.MODERATE,
                subject: str = "crew-01") -> list[Deviation]:
    """`total` lecturas horarias de un indicador; las `concerning` primeras, preocupantes."""
    reference = Baseline(
        key=key, center=50.0, spread=5.0, samples=200,
        sorted_values=tuple(float(value) for value in range(40, 61)),
    )
    return [
        Deviation(
            subject=subject, key=key, value=70.0 if index < concerning else 50.0,
            effective=_h(first_hour + index), z_score=3.0 if index < concerning else 0.1,
            severity=severity if index < concerning else Severity.NONE, direction=direction,
            baseline=reference, used_population_range=False,
            basis=SeverityBasis.PERSONAL_PERCENTILE if index < concerning else None,
        )
        for index in range(total)
    ]


def _trend(key: str, direction: Direction, slope: float, error: float = 0.0) -> Trend:
    signed = -abs(slope) if direction is Direction.FALLING else abs(slope)
    return Trend(
        key=key, slope_per_day=signed, t_statistic=12.0, points=60, span_days=20.0,
        direction=direction, significant=True, mean_value=6.0, standard_error=error,
    )


def _states(result: dict[str, Any]) -> dict[str, str]:
    return {item["key"]: item["state"] for item in result["indicators"]}


def test_concordance_counts_three_of_four_signals_with_data() -> None:
    current = [
        *_deviations("pvt-mean-rt", concerning=10, first_hour=2),
        *_deviations("sleep-duration", concerning=5, first_hour=4, direction="low"),
        # Una sola lectura fuera de lo esperado entre diez es ruido para el motor: no acompaña,
        # y aunque sea la más antigua no es la que inició la alerta.
        *_deviations("sleep-efficiency", concerning=1, first_hour=0, direction="low",
                     severity=Severity.MILD),
        # De otro dominio: no cuenta aquí.
        *_deviations("heart-rate", concerning=10),
    ]
    trends = [_trend("mood-valence", Direction.FALLING, 0.5)]
    result = concordance(Domain.BEHAVIORAL, current, trends)

    assert (result["concordant"], result["with_data"]) == (3, 4)
    assert (result["against"], result["unchanged"]) == (0, 1)
    assert (result["no_data"], result["total"]) == (2, 6)
    assert _states(result) == {
        "pvt-mean-rt": "concordant", "sleep-duration": "concordant",
        "mood-valence": "concordant", "sleep-efficiency": "unchanged",
        "pvt-lapses": "no_data", "circadian-shift": "no_data",
    }
    assert (result["trigger"], result["indicators"][0]["key"]) == ("pvt-mean-rt", "pvt-mean-rt")
    assert result["indicators"][0]["is_trigger"] is True
    assert [item["role_display"] for item in result["indicators"]] == [
        "inició la alerta", None, None, None, None, None,
    ]
    assert "primera lectura fuera de lo esperado" in result["trigger_basis"]
    assert result["statement"] == (
        "Indicadores del dominio: 6. Con dato: 4. Desviados en su sentido preocupante, contando "
        "el que inició la alerta: 3. Con deriva en el sentido contrario: 0. Sin desviación: 1. "
        "Sin dato: 2."
    )
    assert result["basis"] == CONCORDANCE_BASIS and "no cambia el nivel" in CONCORDANCE_BASIS
    described = {item["key"]: item["description"] for item in result["indicators"]}
    assert described["pvt-mean-rt"].startswith(
        "Tiempo de reacción medio en la tarea de vigilancia psicomotora (PVT): ")
    assert "bajando" in described["mood-valence"]
    assert described["sleep-efficiency"] is None and described["pvt-lapses"] is None


def test_a_drift_in_the_harmless_direction_goes_against_and_is_not_counted_as_agreeing() -> None:
    current = _deviations("pvt-mean-rt", concerning=10)
    # Los lapsos preocupan si suben; bajan, y con margen sobre su umbral.
    trends = [_trend("pvt-lapses", Direction.FALLING, 0.5)]
    result = concordance(Domain.BEHAVIORAL, current, trends)
    assert _states(result)["pvt-lapses"] == "against"
    assert (result["concordant"], result["against"], result["with_data"]) == (1, 1, 2)
    assert "Con deriva en el sentido contrario: 1." in result["statement"]

    # Un indicador que preocupa en los dos sentidos no puede ir «en contra»: se desvía o no.
    both = concordance(
        Domain.BEHAVIORAL, current, [_trend("circadian-shift", Direction.FALLING, 0.5)]
    )
    assert _states(both)["circadian-shift"] == "concordant"
    # Y una deriva que no supera su umbral con confianza no se da por «en contra».
    weak = concordance(
        Domain.BEHAVIORAL, current, [_trend("pvt-lapses", Direction.FALLING, 0.0001)]
    )
    assert _states(weak)["pvt-lapses"] == "unchanged"


def test_without_a_persistent_finding_the_trigger_is_the_clearest_drift() -> None:
    trends = [
        _trend("sleep-duration", Direction.FALLING, 0.5, error=0.1),
        _trend("mood-valence", Direction.FALLING, 0.5, error=0.01),
    ]
    clearest = max(trends, key=lambda item: item.threshold_contrast)
    assert trends[0].threshold_contrast != trends[1].threshold_contrast
    result = concordance(Domain.BEHAVIORAL, _deviations("pvt-mean-rt", concerning=0), trends)
    assert result["trigger"] == clearest.key == "mood-valence"
    assert "deriva" in result["trigger_basis"]
    assert (result["concordant"], result["with_data"]) == (2, 3)


def test_an_alert_from_an_external_event_has_no_trigger_and_says_so() -> None:
    result = concordance(Domain.RADIATION, [], [])
    assert result["trigger"] is None and result["trigger_display"] is None
    assert "no procede de sus lecturas" in result["trigger_basis"]
    assert (result["concordant"], result["with_data"]) == (0, 0)
    assert "contando el que inició" not in result["statement"]
    assert {item["state"] for item in result["indicators"]} == {"no_data"}


def test_the_alert_detail_carries_the_concordance_and_why_it_may_matter() -> None:
    current = _deviations("pvt-mean-rt", concerning=10)
    detail = explain.detail(Domain.BEHAVIORAL, current, iter([]))
    assert detail["concordance"] == concordance(Domain.BEHAVIORAL, current, [])
    assert detail["relevance"] == f"Peligro RIDGE de NASA: {Domain.BEHAVIORAL.ridge.display}."


# --------------------------------------------------------------------------- #
# Lenguaje (invariante 7) y segregación del motor (invariante 5)
# --------------------------------------------------------------------------- #

def _system_texts(context: dict[str, Any]) -> Iterator[str]:
    """Lo que redacta el sistema. `detail` no: es texto declarado por una persona o la ficha
    de la biblioteca de contramedidas, que tiene sus propias pruebas."""
    yield from (
        context["label"], context["anchor_basis"], context["window_basis"], context["note"],
        context["summary"], context["mission"]["statement"], context["mission"]["phase_basis"],
    )
    for item in context["items"]:
        yield from (item["label"], item["title"], item["timing"], item["source"])
        yield item["value_label"] or ""
    for source in context["sources"]:
        yield from (source["display"], source["status_display"], source["note"])


def test_every_text_written_by_this_layer_passes_the_language_guard() -> None:
    texts = [LABEL, NOTE, WINDOW_BASIS, CONCORDANCE_BASIS]
    contexts = [
        _rich(),
        _context(),
        _context(onset=None, mission_events=[_event("workload", 20, 40, "Turno")]),
        _context(solar=_solar(known=(-200, -60))),
        _context(solar=_solar(-2, known=(-10, 100)), **_cabin({h: 2.0 for h in range(-12, 3)})),
        _context(mission_events=[_event("eva", 2, 4, "EVA"), _event("eva", 0, 4, "EVA")]),
        _context(onset=dt.datetime(2027, 5, 5, tzinfo=dt.UTC),
                 reference=dt.datetime(2027, 5, 5, 6, tzinfo=dt.UTC)),
    ]
    for context in contexts:
        texts += list(_system_texts(context))
    results = [
        concordance(Domain.BEHAVIORAL, _deviations("pvt-mean-rt", concerning=10),
                    [_trend("pvt-lapses", Direction.FALLING, 0.5)]),
        concordance(Domain.BEHAVIORAL, [], [_trend("mood-valence", Direction.FALLING, 0.5)]),
        concordance(Domain.RADIATION, [], []),
    ]
    for result in results:
        texts += [result["statement"], result["basis"], result["trigger_basis"]]
        texts += [item["state_display"] for item in result["indicators"]]
        texts += [item["role_display"] or "" for item in result["indicators"]]
    texts += [explain.detail(domain, [], [])["relevance"] for domain in Domain]

    assert len({text for text in texts if text}) > 40, "la prueba tiene que mirar textos de verdad"
    assert [(text, check(text)) for text in texts if text and check(text)] == []


def _imported_names(module: object) -> set[str]:
    tree = ast.parse(inspect.getsource(module))  # type: ignore[arg-type]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            names |= {f"{node.module}.{alias.name}" for alias in node.names}
    return names


def test_the_engine_does_not_know_this_layer_and_the_layer_cannot_decide() -> None:
    for engine in (risk, baseline, trend):
        assert not [name for name in _imported_names(engine) if "alert_context" in name]
        assert not [name for name in _imported_names(engine) if "explain" in name]
    reads = _imported_names(alert_context)
    assert "app.analysis.risk.representative_deviation" in reads
    forbidden = ("RiskEngine", "BaselineEngine", "level_for", "combine_findings")
    assert not [name for name in reads if name.rsplit(".", 1)[-1] in forbidden]


def test_the_context_does_not_alter_what_it_reads() -> None:
    current = _deviations("pvt-mean-rt", concerning=10)
    trends = [_trend("mood-valence", Direction.FALLING, 0.5)]
    before = (list(current), list(trends))
    concordance(Domain.BEHAVIORAL, current, trends)
    assert (current, trends) == before


# --------------------------------------------------------------------------- #
# De punta a punta. La última, porque es la lenta: siembra un escenario y pide el estado.
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
    }


def test_alert_levels_are_identical_with_and_without_context_and_concordance(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.post("/api/simulate", params={"scenario": "co2-fatigue", "days": 14, "crew_size": 1})
    plain = client.get("/api/status").json()
    assert plain["alerts"], "el escenario tiene que alertar para que la prueba diga algo"
    assert plain["overall_level"] != "nominal"

    # Con la capa: cada alerta trae su contexto, con el CO2 fuera de límite rotulado, y su
    # concordancia.
    for alert in plain["alerts"]:
        context = alert["detail"]["context"]
        [habitat] = [item for item in context["items"] if item["kind"] == "habitat"]
        assert habitat["label"] == LABEL and habitat["title"].startswith("CO2 de cabina")
        assert context["anchor"] == alert["detail"]["onset"]
        assert alert["detail"]["concordance"]["trigger"] is not None
        assert alert["detail"]["concordance"]["with_data"] >= 1
        assert alert["detail"]["relevance"].startswith("Peligro RIDGE de NASA: ")
        sources = {item["kind"]: item["status"] for item in context["sources"]}
        assert sources["habitat"] == "with_data"
        # Sin EVA declarada y sin caché de DONKI (la suite corre sin red): se dice, no se calla.
        assert (sources["mission_event"], sources["solar_event"]) == ("no_data", "no_data")

    # Más contexto no mueve nada: una EVA declarada sobre el inicio de la primera alerta.
    onset = dt.datetime.fromisoformat(plain["alerts"][0]["detail"]["onset"])
    assert client.post("/api/mission/events", json={
        "kind": "eva", "start": (onset - dt.timedelta(hours=8)).isoformat(),
        "end": (onset - dt.timedelta(hours=2)).isoformat(), "label": "EVA 2",
        "declared_by": "CDR",
    }).status_code == 201
    richer = client.get("/api/status").json()
    [eva] = [
        item for item in richer["alerts"][0]["detail"]["context"]["items"]
        if item["kind"] == "mission_event"
    ]
    assert (eva["title"], eva["detail"], eva["label"]) == ("EVA declarada", "EVA 2", LABEL)
    assert _verdict(richer) == _verdict(plain)

    # Sin la capa: ni contexto ni concordancia. El veredicto es el mismo, cifra a cifra.
    monkeypatch.setattr(routes, "_alert_context_builder", lambda *args, **kwargs: None)
    monkeypatch.setattr(explain, "concordance", lambda *args, **kwargs: {})
    bare = client.get("/api/status").json()
    assert all("context" not in alert["detail"] for alert in bare["alerts"])
    assert all(alert["detail"]["concordance"] == {} for alert in bare["alerts"])
    assert _verdict(bare) == _verdict(plain)


# --------------------------------------------------------------------------- #
# La ubicación declarada se lee en cada excursión del hábitat, y no se lista
# --------------------------------------------------------------------------- #
#
# El contexto de alerta y la ubicación por módulo se hicieron a la vez y por separado. Juntos, sin
# esto, el detalle de una alerta listaba «estoy en el laboratorio» como un evento de misión más y
# seguía diciendo que EMMA no registra en qué módulo está cada tripulante.

def _cabin_in(module: str, co2_by_hour: dict[int, float]) -> dict[str, Any]:
    readings = [
        HabitatReading(module, "cabin-ppco2", value, _h(hour), "habitat-telemetry")
        for hour, value in sorted(co2_by_hour.items())
    ]
    return {"habitat_readings": readings, "habitat_excursions": excursions(readings)}


def _stays(*declared: tuple[str, float, float]) -> list[Stay]:
    """Ubicaciones declaradas, en el orden de sus asientos: la posterior corrige a la anterior."""
    return [
        Stay(module, _h(start), _h(end), order)
        for order, (module, start, end) in enumerate(declared, start=1)
    ]


# CO2 fuera de límite desde 6 h antes del inicio de la alerta hasta 2 h después.
_CO2_OUT = {hour: (4.5 if hour >= -6 else 2.0) for hour in range(-12, 3)}


def test_without_a_declared_location_the_habitat_item_is_the_one_from_before() -> None:
    context = _context(**_cabin_in("laboratorio", _CO2_OUT))
    [item] = _of(context, "habitat")
    assert (item["detail"], item["presence"]) == (None, None)
    note = _source(context, "habitat")["note"]
    assert ASSUMPTION in note and ASSUMPTION_LOCATED not in note


@pytest.mark.parametrize(
    ("declared", "presence", "detail"),
    [
        (
            [("camarotes", -30, 10)], "elsewhere",
            "Según la ubicación declarada, el tripulante no estaba en Laboratorio durante la "
            "excursión. La ubicación la declara una persona, no se mide.",
        ),
        (
            [("laboratorio", -30, 10)], "present",
            "Según la ubicación declarada, el tripulante estaba en Laboratorio durante la "
            "excursión.",
        ),
        # Declarado solo hasta 3 h antes del inicio: queda un tramo de la excursión sin declarar,
        # y un tramo sin declarar nunca exculpa al hábitat.
        (
            [("camarotes", -30, -3)], "undeclared",
            "Sin ubicación declarada en todo el tramo de la excursión: se le supone en el "
            "hábitat compartido.",
        ),
        # Una hora en el laboratorio durante la excursión basta para no darlo por ausente; la
        # declaración posterior corrige a la anterior en ese tramo.
        (
            [("camarotes", -30, 10), ("laboratorio", -2, -1)], "present",
            "Según la ubicación declarada, el tripulante estaba en Laboratorio durante la "
            "excursión.",
        ),
    ],
)
def test_a_declared_location_says_where_the_crew_member_was_during_the_excursion(
    declared: list[tuple[str, float, float]], presence: str, detail: str
) -> None:
    context = _context(stays=_stays(*declared), **_cabin_in("laboratorio", _CO2_OUT))
    [item] = _of(context, "habitat")
    assert (item["presence"], item["detail"]) == (presence, detail)
    # Sigue siendo una coincidencia en el tiempo, con el mismo rótulo y los mismos datos.
    assert item["label"] == LABEL
    assert (item["start"], item["end"], item["value"]) == (
        _h(-6).isoformat(), _h(2).isoformat(), 4.5
    )
    note = _source(context, "habitat")["note"]
    assert ASSUMPTION_LOCATED in note and ASSUMPTION not in note


@pytest.mark.parametrize(
    ("module", "presence", "detail"),
    [
        (
            "camarotes", "elsewhere",
            "Según la ubicación declarada o estimada por las anclas de módulo, el tripulante no "
            "estaba en Laboratorio durante la excursión. Las anclas la estiman por la señal más "
            "fuerte, solo el módulo y sin validar dentro de un módulo metálico.",
        ),
        (
            "laboratorio", "present",
            "Según la ubicación declarada o estimada por las anclas de módulo, el tripulante "
            "estaba en Laboratorio durante la excursión.",
        ),
    ],
)
def test_a_location_the_anchors_estimated_is_not_said_to_be_declared_by_a_person(
    module: str, presence: str, detail: str
) -> None:
    # La ubicación que estiman las anclas de módulo (2026-11-10): misma regla, pero ni el detalle
    # ni el supuesto dicen que la declarara una persona.
    stays = [Stay(module, _h(-30), _h(10), 1, source="anchors")]
    context = _context(stays=stays, **_cabin_in("laboratorio", _CO2_OUT))
    [item] = _of(context, "habitat")
    assert (item["presence"], item["detail"]) == (presence, detail)
    note = _source(context, "habitat")["note"]
    assert ASSUMPTION_ESTIMATED_LOCATED in note and ASSUMPTION_LOCATED not in note
    assert "declara una persona" not in item["detail"]


def test_only_the_part_of_the_excursion_inside_the_window_counts_for_the_location() -> None:
    # Fuera de límite desde 40 h antes; la ventana empieza 24 h antes. Estuvo en el laboratorio
    # solo hasta 30 h antes: fuera de la ventana. Dentro de ella, en los camarotes.
    cabin = _cabin_in("laboratorio", {hour: 4.5 for hour in range(-40, 3)})
    stays = _stays(("laboratorio", -60, -30), ("camarotes", -30, 10))
    [item] = _of(_context(stays=stays, **cabin), "habitat")
    assert item["presence"] == "elsewhere"


def test_a_module_outside_the_declared_list_cannot_be_compared_and_says_so() -> None:
    # `m1` no está en la lista de módulos: no se puede comparar con la ubicación de nadie.
    context = _context(stays=_stays(("camarotes", -30, 10)), **_cabin_in("m1", _CO2_OUT))
    [item] = _of(context, "habitat")
    assert (item["presence"], item["detail"]) == ("undeclared", NOT_COMPARABLE)


def test_a_location_declaration_is_not_listed_as_a_mission_event() -> None:
    location = {**_event("location", -20, -14, "Laboratorio"), "module": "laboratorio"}
    alone = _context(mission_events=[location])
    assert _of(alone, "mission_event") == []
    # Declarar dónde se está no es declarar una EVA: de eventos sigue sin saberse nada.
    source = _source(alone, "mission_event")
    assert (source["status"], source["found"]) == ("no_data", 0)
    both = _context(mission_events=[location, _event("eva", -20, -14, "EVA 3")])
    assert [item["title"] for item in _of(both, "mission_event")] == ["EVA declarada"]
    assert _source(both, "mission_event")["found"] == 1


def test_the_location_texts_pass_the_language_guard() -> None:
    texts = [NOT_COMPARABLE, ASSUMPTION_LOCATED]
    texts += [
        text.format(module="Laboratorio") for text in alert_context._PRESENCE_DISPLAY.values()
    ]
    assert len(texts) == 5
    assert [(text, check(text)) for text in texts if check(text)] == []


def test_a_location_declared_in_the_console_reaches_the_alert_detail_and_moves_nothing(
    client: TestClient,
) -> None:
    """De punta a punta: la ubicación firmada en el ledger llega al detalle de la alerta por
    `routes._alert_context_builder`, y el veredicto del motor es el mismo (invariante 5)."""
    client.post("/api/simulate", params={"scenario": "co2-fatigue", "days": 14, "crew_size": 1})
    plain = client.get("/api/status").json()
    assert plain["alerts"], "el escenario tiene que alertar para que la prueba diga algo"
    [before] = [
        item for item in plain["alerts"][0]["detail"]["context"]["items"]
        if item["kind"] == "habitat"
    ]
    assert (before["presence"], before["detail"]) == (None, None)

    def declare(module: str) -> None:
        response = client.post("/api/mission/events", json={
            "kind": "location", "module": module, "start": "2026-01-01T00:00:00+00:00",
            "end": "2027-12-31T00:00:00+00:00", "declared_by": "CDR",
        })
        assert response.status_code == 201, response.text

    declare("camarotes")
    away = client.get("/api/status").json()
    for alert in away["alerts"]:
        context = alert["detail"]["context"]
        [habitat] = [item for item in context["items"] if item["kind"] == "habitat"]
        assert habitat["presence"] == "elsewhere"
        assert "no estaba en Hábitat principal" in habitat["detail"]
        # La declaración de ubicación no aparece como evento de misión.
        assert [item for item in context["items"] if item["kind"] == "mission_event"] == []
        sources = {item["kind"]: item for item in context["sources"]}
        assert sources["mission_event"]["status"] == "no_data"
        assert ASSUMPTION_LOCATED in sources["habitat"]["note"]
    assert _verdict(away) == _verdict(plain)

    # Una declaración posterior corrige a la anterior: estaba en el módulo de la excursión.
    declare("habitat-principal")
    there = client.get("/api/status").json()
    [habitat] = [
        item for item in there["alerts"][0]["detail"]["context"]["items"]
        if item["kind"] == "habitat"
    ]
    assert habitat["presence"] == "present"
    assert _verdict(there) == _verdict(plain)
