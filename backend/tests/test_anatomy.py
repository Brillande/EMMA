"""La cadena del modo anatómico (especificación §10): región → estado → variables → evidencia
→ tendencia → contramedida.

Lo que se vigila aquí no es que el endpoint devuelva cosas, sino que no pueda decir algo
distinto de `/status`: el visor es cliente del estado (§4), y un nivel calculado dos veces con
dos reglas acaba discrepando. Lo mismo con qué variable «contribuye»: lo decide el motor, con
su filtro de persistencia, no una lectura suelta. Sin red (invariante 3).
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import anatomy, risk_entity, timeline
from app.advisor.recommendations import Advisor
from app.analysis import alert_history
from app.analysis.alert_context import LABEL as CONTEXT_LABEL
from app.analysis.alert_context import NOTE_WITHOUT_ALERT
from app.analysis.recovery import days_after_landing
from app.analysis.risk import RiskEngine
from app.api.routes import CURRENT_WINDOW, new_store, reset_store
from app.core import versioning
from app.core.config import Settings, get_settings
from app.evidence.links import evidence_for
from app.evidence.registry import POPULATIONS, cite, registry
from app.ingest import inspiration4
from app.ingest.codes import CATALOG, DESCRIPTIVE_ONLY, Domain
from app.ingest.fhir import observation
from app.main import app
from app.text_guard import check
from tests.test_analysis import NOW, _deviation

ORDER = ["nominal", "watch", "concern", "critical"]
SCENARIOS = ["nominal", "arrhythmia", "progressive-insomnia"]
# Los dos hallazgos del motor que no salen de un indicador: se dan por dominio, no por variable.
NOT_FROM_AN_INDICATOR = ("evento solar activo", "dosis acumulada")
# El guardián caza «dosis» porque en un borrador clínico es posología. En la región de
# radiación es la dosis absorbida, una magnitud física con indicador en el catálogo.
RADIATION_DOSE = ("dosing", "dosis")

Chain = tuple[dict[str, Any], dict[str, Any]]
_LIVER_RECOMMENDATIONS_NOTE = (
    "Sin contramedidas propias: las del dominio nutrición salen en la región «Aparato digestivo: "
    "nutrición»."
)
_LUNG_RECOMMENDATIONS_NOTE = (
    "Sin contramedidas propias: las del dominio cardiovascular salen en la región «Corazón y "
    "circulación»."
)
# La nota de contramedidas de cada región sin nivel propio, por su clave.
_ELSEWHERE_NOTES = {"liver": _LIVER_RECOMMENDATIONS_NOTE, "lungs": _LUNG_RECOMMENDATIONS_NOTE}


@pytest.fixture(scope="module")
def chain(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Callable[[str], Chain]]:
    """`/anatomy/state` y `/status` del mismo escenario, sembrado una vez por módulo.

    Sembrar 40 días y valorarlos cuesta decenas de segundos; las pruebas solo leen.
    """
    cache_dir: Path = tmp_path_factory.mktemp("anatomy")
    seeded: dict[str, Chain] = {}

    def load(scenario: str) -> Chain:
        if scenario not in seeded:
            reset_store(new_store())
            app.dependency_overrides[get_settings] = lambda: Settings(
                cache_dir=cache_dir, offline=True
            )
            try:
                client = TestClient(app)
                loaded = client.post("/api/simulate", params={"scenario": scenario, "days": 40})
                assert loaded.status_code == 201, loaded.text
                state = client.get("/api/anatomy/state", params={"subject": "crew-01"})
                status = client.get("/api/status", params={"subject": "crew-01"})
                assert state.status_code == 200 and status.status_code == 200, state.text
                seeded[scenario] = (state.json(), status.json())
            finally:
                app.dependency_overrides.clear()
                reset_store(None)
        return seeded[scenario]

    yield load


def _region(state: dict[str, Any] | list[dict[str, Any]], key: str) -> dict[str, Any]:
    regions = state["regions"] if isinstance(state, dict) else state
    return next(item for item in regions if item["key"] == key)


def _strings(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [text for value in node.values() for text in _strings(value)]
    if isinstance(node, list):
        return [text for value in node for text in _strings(value)]
    return []


# --------------------------------------------------------------------------- #
# La cadena está entera
# --------------------------------------------------------------------------- #


def test_every_region_carries_the_whole_chain(chain: Callable[[str], Chain]) -> None:
    state, _status = chain("arrhythmia")
    assert [item["key"] for item in state["regions"]] == [item.key for item in anatomy.REGIONS]
    for region in state["regions"]:
        assert {
            "level", "has_data", "data_note", "state", "variables", "unmeasured", "evidence",
            "recommendations", "recommendations_note",
        } <= set(region)
        assert [entry["domain"] for entry in region["state"]] == region["domains"]
        # Evidencia: toda región la tiene, con el nivel de cada fuente y lo que cubre el sistema.
        assert [block["domain"] for block in region["evidence"]] == region["domains"]
        for block in region["evidence"]:
            assert block["amcl_alignment"] and block["items"]
            assert all(item["grade"]["label"] for item in block["items"])
        # Cada indicador del catálogo de la región está o medido o declarado sin medir; los
        # descriptivos, en ninguno de los dos: el estado no los lee.
        expected = {
            c.key for c in CATALOG.values()
            if str(c.domain) in region["domains"] and c.key not in DESCRIPTIVE_ONLY
        } or set(region["analytes"])
        listed = [v["key"] for v in region["variables"]] + [u["key"] for u in region["unmeasured"]]
        assert sorted(listed) == sorted(expected)
        assert region["has_data"] is bool(region["variables"])
        assert (region["data_note"] is None) is region["has_data"]
        # La lista de analitos solo la lleva una región sin nivel propio, y con su fuente.
        assert bool(region["analytes"]) is (region["level_of"] is not None)
        assert (region["analytes_source"] is None) is (region["level_of"] is None)


def test_an_alerting_region_shows_variables_trend_evidence_and_countermeasure(
    chain: Callable[[str], Chain],
) -> None:
    state, status = chain("arrhythmia")
    heart = _region(state, "heart")
    assert heart["level"] == status["domains"]["cardiovascular"]["level"] != "nominal"
    contributing = [item for item in heart["variables"] if item["contributes"]]
    assert contributing and heart["variables"][: len(contributing)] == contributing
    for variable in heart["variables"]:
        code = CATALOG[variable["key"]]
        # La unidad es la del catálogo (invariante 2): aquí no se convierte nada.
        assert (variable["unit"], variable["display"]) == (code.unit, code.display)
        assert variable["observation_type"] == "measured"
        assert variable["evidence_context"] == "simulated"
        assert dt.datetime.fromisoformat(variable["effective"]).tzinfo is not None
    assert any(item["deviation"] for item in contributing)
    assert any(item["trend"] and item["trend"]["description"] for item in heart["variables"])
    assert heart["recommendations"] and heart["recommendations_note"] is None
    assert all(item["countermeasure"]["action"] for item in heart["recommendations"])


# --------------------------------------------------------------------------- #
# Coherencia con /status: el visor es cliente, no fuente
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_region_level_is_the_one_status_gives(
    chain: Callable[[str], Chain], scenario: str
) -> None:
    """Mismo sujeto, mismo escenario, mismo veredicto. Si falla, hay dos reglas."""
    state, status = chain(scenario)
    assert state["subject"] == status["subject"]
    assert state["reference_time"] == status["data"]["reference_time"]
    assert state["rules_version"] == status["rules_version"]
    for region in state["regions"]:
        for entry in region["state"]:
            theirs = status["domains"][entry["domain"]]
            assert entry["drivers"] == theirs["drivers"]
            if entry["level"] is None:
                # Solo se calla el nivel sin lecturas y sin hallazgo del motor.
                assert not entry["has_data"] and theirs["level"] == "nominal"
                assert not theirs["drivers"]
            else:
                assert entry["level"] == theirs["level"]
        levels = [entry["level"] for entry in region["state"] if entry["level"] is not None]
        assert region["level"] == (max(levels, key=ORDER.index) if levels else None)
        # Las contramedidas son las de `/status` para esos dominios, en su mismo orden.
        assert region["recommendations"] == [
            item for item in status["recommendations"] if item["domain"] in region["domains"]
        ]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_what_contributes_is_what_the_engine_counted(
    chain: Callable[[str], Chain], scenario: str
) -> None:
    """Cada motivo de `/status` que sale de un indicador lo explica una variable, y al revés."""
    state, status = chain(scenario)
    for region in state["regions"]:
        for entry in region["state"]:
            drivers = status["domains"][entry["domain"]]["drivers"]
            explained: set[str] = set()
            for variable in region["variables"]:
                if variable["domain"] != entry["domain"]:
                    continue
                counted = variable["deviation"]
                drifting = variable["trend"] is not None and variable["trend"]["concerning"]
                # La dosis registrada cuenta sin desviación: la delata su motivo en `/status`.
                dose = variable["key"] == anatomy.CUMULATIVE_DOSE and any(
                    item.startswith("dosis acumulada") for item in drivers
                )
                assert variable["contributes"] is bool(counted or drifting or dose)
                if counted:
                    explained.add(counted["description"])
                if drifting:
                    explained.add(variable["trend"]["description"])
            assert explained == {
                item for item in drivers if not item.startswith(NOT_FROM_AN_INDICATOR)
            }


def test_what_the_engine_discards_as_noise_does_not_contribute() -> None:
    """Una lectura aislada fuera de lo esperado no mueve el nivel: tampoco se señala aquí."""
    reading = observation("heart-rate", 62.0, NOW, "crew-01", "test")
    isolated = [_deviation(0.5) for _ in range(19)] + [_deviation(3.5)]
    status = RiskEngine().assess("crew-01", isolated)
    heart = _region(anatomy.state(status, [reading], isolated, {}, []), "heart")
    [variable] = heart["variables"]
    assert (heart["level"], variable["contributes"], variable["deviation"]) == (
        "nominal", False, None
    )

    persistent = [_deviation(4.5) for _ in range(12)]
    status = RiskEngine().assess("crew-01", persistent)
    proposed = Advisor().recommend(status)
    heart = _region(anatomy.state(status, [reading], persistent, {}, proposed), "heart")
    [variable] = heart["variables"]
    risk = status.domains[Domain.CARDIOVASCULAR]
    assert heart["level"] == str(risk.level) != "nominal"
    assert variable["contributes"] and [variable["deviation"]["description"]] == list(risk.drivers)
    assert heart["recommendations"] == [
        item.to_dict() for item in proposed if item.domain is Domain.CARDIOVASCULAR
    ]


def test_a_recorded_cumulative_dose_is_the_variable_that_moves_radiation(
    client: TestClient,
) -> None:
    """`/status` toma la dosis de la última lectura registrada: esa lectura es la que cuenta."""
    client.post("/api/observations", json={"key": "cumulative-dose", "value": 600.0})
    status = client.get("/api/status").json()
    body = _region(client.get("/api/anatomy/state").json(), "whole-body")
    assert status["dose"]["source"] == "observation"
    assert body["level"] == status["domains"]["radiation"]["level"] != "nominal"
    assert body["state"][0]["drivers"] == status["domains"]["radiation"]["drivers"]
    [variable] = body["variables"]
    assert (variable["key"], variable["value"]) == (anatomy.CUMULATIVE_DOSE, 600.0)
    assert variable["contributes"] is True and variable["deviation"] is None


def test_a_dose_given_by_parameter_is_not_pinned_on_a_reading(client: TestClient) -> None:
    """Si la dosis valorada vino por parámetro, la lectura registrada no es la que cuenta."""
    client.post("/api/observations", json={"key": "cumulative-dose", "value": 10.0})
    given = {"cumulative_dose_msv": 600.0}
    status = client.get("/api/status", params=given).json()
    body = _region(client.get("/api/anatomy/state", params=given).json(), "whole-body")
    assert status["dose"]["source"] == "parameter"
    assert body["level"] == status["domains"]["radiation"]["level"] != "nominal"
    [variable] = body["variables"]
    assert (variable["value"], variable["contributes"]) == (10.0, False)


def test_until_gives_the_state_ground_can_have(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "nominal", "days": 3})
    full = client.get("/api/anatomy/state").json()
    until = (dt.datetime.fromisoformat(full["reference_time"]) - dt.timedelta(days=1)).isoformat()
    cut = client.get("/api/anatomy/state", params={"until": until}).json()
    status = client.get("/api/status", params={"until": until}).json()
    assert cut["reference_time"] == status["data"]["reference_time"] <= until
    assert cut["reference_time"] < full["reference_time"]
    naive = client.get("/api/anatomy/state", params={"until": "2026-11-14T08:00:00"})
    assert naive.status_code == 422


def test_unknown_subject_is_404_like_status(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "nominal", "days": 1})
    assert client.get("/api/status", params={"subject": "nadie"}).status_code == 404
    assert client.get("/api/anatomy/state", params={"subject": "nadie"}).status_code == 404


# --------------------------------------------------------------------------- #
# Sin datos no es nominal
# --------------------------------------------------------------------------- #


def test_a_region_without_readings_says_so_instead_of_nominal() -> None:
    status = RiskEngine().assess("crew-01", [])
    for region in anatomy.state(status, [], [], {}, []):
        assert region["level"] is None and region["has_data"] is False
        assert region["data_note"] == anatomy.NO_DATA_NOTE
        assert all(entry["level"] is None for entry in region["state"])
        assert region["variables"] == [] and region["unmeasured"]
        assert region["recommendations"] == []
        # Tampoco se dice que "el análisis no encontró nada": no había nada que mirar. (La región
        # sin nivel propio no propone nada nunca, y dice dónde está lo de su dominio.)
        assert region["recommendations_note"] == (
            anatomy.NOTHING_TO_ASSESS_NOTE if region["level_of"] is None
            else _ELSEWHERE_NOTES[region["key"]]
        )


def test_only_the_measured_region_gets_a_level() -> None:
    reading = observation("heart-rate", 62.0, NOW, "crew-01", "test")
    status = RiskEngine().assess("crew-01", [_deviation(0.5)])
    regions = anatomy.state(status, [reading], [_deviation(0.5)], {}, [])
    assert {item["key"]: item["level"] for item in regions if item["level"] is not None} == {
        "heart": "nominal"
    }
    # "No encontró nada" solo se dice de la región que sí se miró.
    assert {item["key"] for item in regions
            if item["recommendations_note"] == anatomy.NO_FINDINGS_NOTE} == {"heart"}


def test_a_finding_without_readings_keeps_the_engine_level() -> None:
    """La dosis de carrera sube la radiación sin una sola lectura del tripulante: no se tapa."""
    status = RiskEngine().assess("crew-01", [], cumulative_dose_msv=600.0)
    risk = status.domains[Domain.RADIATION]
    proposed = Advisor().recommend(status)
    body = _region(anatomy.state(status, [], [], {}, proposed), "whole-body")
    assert body["level"] == str(risk.level) != "nominal"
    assert body["has_data"] is False and body["data_note"] == anatomy.NO_DATA_NOTE
    assert body["state"][0]["drivers"] == list(risk.drivers)
    assert body["recommendations"] and body["recommendations_note"] is None


def test_a_finding_without_a_library_entry_does_not_read_as_no_findings() -> None:
    status = RiskEngine().assess("crew-01", [], cumulative_dose_msv=600.0)
    body = _region(anatomy.state(status, [], [], {}, []), "whole-body")
    assert body["recommendations_note"] == anatomy.NO_LIBRARY_ENTRY_NOTE


# --------------------------------------------------------------------------- #
# Lo que se dice: evidencia con su alcance, y nada con tono de orden
# --------------------------------------------------------------------------- #


def test_mouse_evidence_keeps_its_scope() -> None:
    """OSD-288 es bazo de ratón: su alcance viaja con la referencia, sin resumir."""
    status = RiskEngine().assess("crew-01", [])
    immune = _region(anatomy.state(status, [], [], {}, []), "immune")
    [block] = immune["evidence"]
    assert block["items"] == [item.to_dict() for item in evidence_for(Domain.IMMUNE)]
    osd = next(item for item in block["items"] if "OSD-288" in item["source"])
    assert "Modelo murino" in osd["scope_caveat"]
    assert "NO mide signos vitales humanos" in osd["scope_caveat"]
    assert "ratón" in osd["relevance"]


def test_the_fixed_texts_of_this_module_pass_the_guard() -> None:
    for note in (
        anatomy.NO_DATA_NOTE, anatomy.NOTHING_TO_ASSESS_NOTE, anatomy.NO_FINDINGS_NOTE,
        anatomy.NO_LIBRARY_ENTRY_NOTE, _LIVER_RECOMMENDATIONS_NOTE, _LUNG_RECOMMENDATIONS_NOTE,
        anatomy.LEVEL_OF_NOTE.format(domain=Domain.NUTRITION.display),
        anatomy.LEVEL_OF_NOTE.format(domain=Domain.CARDIOVASCULAR.display),
        anatomy.MILESTONES_BASIS, anatomy.PREFLIGHT_MILESTONES_BASIS,
        anatomy.STANDARD_MEASURES_SCOPE, anatomy.BONE_DXA_SCOPE,
    ):
        assert check(note) == [], note
    for region in anatomy.REGIONS:
        found = {
            (finding.category, finding.match)
            for text in (region.display, region.note)
            for finding in check(text)
        }
        allowed = {RADIATION_DOSE} if Domain.RADIATION in region.domains else set()
        assert found <= allowed, region.key


@pytest.mark.parametrize("scenario", ["arrhythmia", "progressive-insomnia"])
def test_nothing_in_the_chain_reads_as_an_order(
    chain: Callable[[str], Chain], scenario: str
) -> None:
    """Invariante 7 sobre la cadena entera, tal y como la enseña el panel de una alerta."""
    state, _status = chain(scenario)
    orders = [
        (finding.match, text)
        for text in _strings(state)
        for finding in check(text)
        if finding.category == "order"
    ]
    assert orders == []


# --------------------------------------------------------------------------- #
# Riesgo, hábitat y tiempo (KB §11.1; conversación de ideación)
# --------------------------------------------------------------------------- #


def test_every_domain_carries_the_risk_step_of_the_risk_entity(
    chain: Callable[[str], Chain],
) -> None:
    """El paso RIESGO es el de `/risks`, sin depender de que haya contramedida propuesta."""
    state, _status = chain("nominal")
    risks = {item["risk_id"]: item for item in risk_entity.payload(CURRENT_WINDOW)["risks"]}
    for region in state["regions"]:
        for entry in region["state"]:
            risk = entry["risk"]
            assert risk == risk_entity.summary(Domain(entry["domain"]))
            whole = risks[entry["domain"]]
            assert risk["ridge"] == whole["ridge"]
            assert (risk["hrp_risk"] or {}).get("id") == whole["hrp_risk_id"]
            # La ficha va con la clase que declara el registro: no todas son riesgos del HRP.
            if risk["hrp_risk"] is not None:
                [cited] = [
                    item for item in whole["evidence_refs"] if item["id"] == whole["hrp_risk_id"]
                ]
                assert risk["hrp_risk"]["evidence_type_display"] == cited["evidence_type_display"]
            assert risk["uncertainty_statement"] == whole["uncertainty"]["statement"]
    # Sin ninguna recomendación en el escenario nominal, el RIDGE sigue en cada región.
    assert all(entry["risk"]["ridge"]["display"]
               for region in state["regions"] for entry in region["state"])


def test_an_alerting_region_has_the_same_context_as_its_alert(
    chain: Callable[[str], Chain],
) -> None:
    """Un solo constructor: el contexto de la región es, entero, el del detalle de su alerta."""
    state, status = chain("arrhythmia")
    alerts = {item["domain"]: item for item in status["alerts"]}
    assert alerts, "el escenario de arritmia tiene que alertar"
    for region in state["regions"]:
        # Una región sin nivel propio se ancla en la alerta del dominio de su nivel.
        [domain] = region["domains"] or [region["level_of"]]
        if domain in alerts:
            assert region["context"] == alerts[domain]["detail"]["context"]
        else:
            context = region["context"]
            assert context["anchor"] == state["reference_time"]
            assert context["anchor_basis"] == "sin alerta: se toma el instante del estado"
            assert context["note"] == NOTE_WITHOUT_ALERT
            assert all(item["label"] == CONTEXT_LABEL for item in context["items"])


def test_without_the_builder_there_is_no_context_rather_than_an_empty_one() -> None:
    status = RiskEngine().assess("crew-01", [])
    assert all(region["context"] is None for region in anatomy.state(status, [], [], {}, []))


def _reading(day: float, start: dt.date = dt.date(2026, 11, 1)) -> Any:
    moment = dt.datetime.combine(start, dt.time(0, 0), tzinfo=dt.UTC) + dt.timedelta(days=day)
    return observation("heart-rate", 62.0, moment, "crew-01", "test")


def test_moments_are_the_phase_changes_the_landing_and_each_postflight_day() -> None:
    start = dt.date(2026, 11, 1)
    launch = dt.datetime.combine(start, dt.time(0, 0), tzinfo=dt.UTC)
    readings = [_reading(day) for day in (-3, 2, 20, 26, 29.9, 30.2, 31.1, 31.4, 31.6, 33)]
    found = anatomy.moments(readings, start, 30)
    assert found["current_display"] == anatomy.CURRENT_MOMENT
    assert found["basis"] == anatomy.MOMENTS_BASIS
    keys = [item["key"] for item in found["items"]]
    # El último día posvuelo (R+3) es el de ahora: no se ofrece como momento pasado, y su tramo
    # (el del hito R+7) se pide en el día de antes con lecturas, R+2.
    assert keys == [
        "preflight", "phase-stable", "phase-return", "landing", "R+0", "R+1", "R+2",
    ]
    until = {item["key"]: dt.datetime.fromisoformat(item["until"]) for item in found["items"]}
    second = dt.timedelta(seconds=1)
    assert until["preflight"] == launch - second
    assert until["phase-stable"] == launch + dt.timedelta(days=14) - second
    assert until["phase-return"] == launch + dt.timedelta(days=23) - second
    assert until["landing"] == launch + dt.timedelta(days=30) - second
    # El R+ es el de la recuperación, y el instante, la última lectura de ese día.
    landing = launch + dt.timedelta(days=30)
    assert until["R+0"] == readings[5].effective
    assert until["R+1"] == readings[7].effective
    assert until["R+2"] == readings[8].effective
    assert [days_after_landing(item.effective, landing) for item in readings[5:9]] == [0, 1, 1, 2]
    days = {item["key"]: item["days_after_landing"] for item in found["items"]}
    assert days == {
        "preflight": None, "phase-stable": None, "phase-return": None, "landing": None,
        "R+0": 0, "R+1": 1, "R+2": 2,
    }
    texts = {item["key"]: item["display"] for item in found["items"]}
    assert texts["phase-stable"] == "Cambio de fase: de adaptación a fase estable (día 14)"
    assert texts["landing"] == "Regreso (día 30)"
    assert texts["R+1"] == "R+1: última lectura de ese día"
    assert texts["R+2"] == "Tramo de R+2 a R+7: última lectura, en R+2"
    milestones = found["postflight_milestones"]
    for text in [*texts.values(), found["basis"], found["current_display"], milestones["basis"]]:
        assert check(text) == [], text


def test_a_replayed_flight_lands_when_it_landed_and_skips_the_configured_phases() -> None:
    """Con Inspiration4 el regreso es el de su vuelo (tres días), como en la recuperación; los
    límites de fase del calendario configurado caen después y no se ofrecen."""
    start = dt.date(2026, 11, 1)
    launch = dt.datetime.combine(start, dt.time(0, 0), tzinfo=dt.UTC)
    readings = [
        observation("lymphocytes", 25.0, launch + dt.timedelta(days=day), "crew-01",
                    inspiration4.SOURCE)
        for day in (-92, -44, -3, 4, 48, 85)
    ]
    found = anatomy.moments(readings, start, 180)
    # R+45 y R+82 caen en el tramo del hito R+90; R+82 es la de ahora, y el tramo se pide en R+45.
    # Antes del vuelo, L-92 cae en el tramo de L-90 y L-44 en el de L-30; L-3 es el lanzamiento.
    assert [item["key"] for item in found["items"]] == [
        "L-92", "L-44", "preflight", "landing", "R+1", "R+45",
    ]
    texts = {item["key"]: item["display"] for item in found["items"]}
    assert texts["L-92"] == "Tramo de L-179 a L-90: última lectura, en L-92"
    assert texts["L-44"] == "Tramo de L-89 a L-30: última lectura, en L-44"
    assert {item["key"]: item["days_before_launch"] for item in found["items"]} == {
        "L-92": 92, "L-44": 44, "preflight": None, "landing": None, "R+1": None, "R+45": None,
    }
    [late] = [item for item in found["items"] if item["key"] == "R+45"]
    assert late["display"] == "Tramo de R+31 a R+90: última lectura, en R+45"
    landing = next(item for item in found["items"] if item["key"] == "landing")
    assert landing["display"] == "Regreso del vuelo reproducido"
    assert dt.datetime.fromisoformat(landing["until"]) == (
        launch + dt.timedelta(days=inspiration4.MISSION_DAYS, seconds=-1)
    )


def test_a_moment_needs_readings_before_and_after_it() -> None:
    start = dt.date(2026, 11, 1)
    # Sin prevuelo ni posvuelo, y con la serie entera dentro de la adaptación: nada que pedir.
    assert anatomy.moments([_reading(1), _reading(5)], start, 180)["items"] == []
    assert anatomy.moments([], start, 180)["items"] == []
    [only] = anatomy.moments([_reading(1), _reading(15)], start, 180)["items"]
    assert only["key"] == "phase-stable"
    # Un límite que cae justo en la última lectura es el estado de ahora, no un momento pasado.
    launch = dt.datetime.combine(start, dt.time(0, 0), tzinfo=dt.UTC)
    boundary = observation(
        "heart-rate", 62.0, launch + dt.timedelta(days=14, seconds=-1), "crew-01", "test")
    assert anatomy.moments([_reading(1), boundary], start, 180)["items"] == []


def test_each_postflight_day_falls_in_one_milestone() -> None:
    """Hitos R+0, R+1, R+7 y R+30 de Standard Measures, R+180, R+365, R+730 y R+1095 de la
    densitometría ósea y R+90 de diseño: cada día va al primero que no queda antes de él, y lo
    posterior al último va junto."""
    assert anatomy.POSTFLIGHT_MILESTONES == (0, 1, 7, 30, 90, 180, 365, 730, 1095)
    expected = {
        0: 0, 1: 1, 2: 7, 7: 7, 8: 30, 30: 30, 31: 90, 90: 90, 91: 180, 180: 180, 181: 365,
        365: 365, 366: 730, 1000: 1095, 730: 730, 731: 1095, 1095: 1095, 1096: None, 2000: None,
    }
    assert {day: anatomy.postflight_milestone(day) for day in expected} == expected


def test_a_long_daily_recovery_gives_one_moment_per_milestone() -> None:
    """Con una toma diaria durante más de un año el selector no crece un botón por día: un
    momento por hito, en la última lectura de su tramo, y el tramo del día de ahora se pide en
    el día de antes."""
    start = dt.date(2026, 11, 1)
    landing = dt.datetime.combine(start, dt.time(0, 0), tzinfo=dt.UTC) + dt.timedelta(days=30)
    readings = [_reading(-2), _reading(5)] + [
        observation("heart-rate", 62.0, landing + dt.timedelta(days=day, hours=hour), "crew-01",
                    "test")
        for day in range(1201) for hour in (1, 9)
    ]
    found = anatomy.moments(readings, start, 30)
    postflight = [item for item in found["items"] if item["kind"] == "postflight_milestone"]
    assert [item["key"] for item in postflight] == [
        "R+0", "R+1", "R+7", "R+30", "R+90", "R+180", "R+365", "R+730", "R+1095", "R+1199",
    ]
    assert [item["days_after_landing"] for item in postflight] == [
        0, 1, 7, 30, 90, 180, 365, 730, 1095, 1199,
    ]
    for item in postflight:
        # La última lectura del día del hito, no la primera.
        assert dt.datetime.fromisoformat(item["until"]) == landing + dt.timedelta(
            days=item["days_after_landing"], hours=9)
    texts = {item["key"]: item["display"] for item in postflight}
    assert texts["R+30"] == "R+30: última lectura de ese día"
    assert texts["R+730"] == "R+730: última lectura de ese día"
    assert texts["R+1199"] == "Después de R+1095: última lectura, en R+1199"
    # De dónde sale cada hito: los leídos y los de diseño, con la ficha de la fuente.
    milestones = found["postflight_milestones"]
    assert milestones["read"] == [0, 1, 7, 30, 180, 365, 730, 1095]
    assert milestones["design"] == [90]
    sources = {item["source"]["id"]: item for item in milestones["sources"]}
    assert set(sources) <= set(registry())
    assert sources["hardy-2025-spaceflight-standard-measures"]["days"] == [0, 1, 7, 30]
    assert sources["ochmo-mtb-013"]["days"] == [180, 365, 730, 1095]
    # Cada fuente dice qué cubre: la densitometría es solo del hueso, y Standard Measures es el
    # calendario de ese estudio; ninguna, el de todos los indicadores.
    assert sources["ochmo-mtb-013"]["scope"] == anatomy.BONE_DXA_SCOPE
    assert "Solo del hueso" in anatomy.BONE_DXA_SCOPE
    assert "no el de todos los indicadores" in anatomy.STANDARD_MEASURES_SCOPE
    assert "R+90 es de diseño de EMMA, sin fuente" in milestones["basis"]
    assert "solo del hueso" in milestones["basis"]
    for text in [*texts.values(), milestones["basis"]]:
        assert check(text) == [], text


def test_a_chronicle_fact_is_the_moment_it_names() -> None:
    """Un cambio de fase es el momento que acaba un segundo antes; un hecho posvuelo, el primer
    hito que ya lo cuenta (por instantes: el R+ de la crónica y el de los momentos se calculan con
    lecturas distintas)."""
    start = dt.date(2026, 11, 1)
    launch = dt.datetime.combine(start, dt.time(0, 0), tzinfo=dt.UTC)
    readings = [_reading(day) for day in (-3, 2, 20, 26, 29.9, 30.2, 31.1, 31.4, 31.6, 33)]
    found = anatomy.moments(readings, start, 30)

    def phase(day: int) -> dict[str, Any]:
        return {"fact": "phase-change", "at": (launch + dt.timedelta(days=day)).isoformat()}

    def sample(day: float, fact: str = "postflight-sample") -> dict[str, Any]:
        return {"fact": fact, "at": (launch + dt.timedelta(days=day)).isoformat()}

    assert anatomy.chronicle_moment(phase(0), found) == {
        "key": "preflight", "display": "Fin del prevuelo: lanzamiento",
    }
    assert anatomy.chronicle_moment(phase(14), found) == {
        "key": "phase-stable",
        "display": "Cambio de fase: de adaptación a fase estable (día 14)",
    }
    # El cambio a posvuelo del calendario es el regreso.
    assert anatomy.chronicle_moment(phase(30), found)["key"] == "landing"  # type: ignore[index]
    assert anatomy.chronicle_moment(phase(15), found) is None
    # La toma de R+0 la cuenta ya R+0; una de R+1, aunque sea anterior a la última de R+0 del
    # todo no lo es, la cuenta R+1 (su última lectura, a 31,4).
    assert anatomy.chronicle_moment(sample(30.2), found)["key"] == "R+0"  # type: ignore[index]
    assert anatomy.chronicle_moment(sample(31.1), found) == {
        "key": "R+1", "display": "R+1: última lectura de ese día",
    }
    assert anatomy.chronicle_moment(sample(31.4, "postflight-day"), found)["key"] == "R+1"  # type: ignore[index]
    # Después de la última lectura de R+1, el primero que la cuenta es el tramo de R+7, en R+2.
    assert anatomy.chronicle_moment(sample(31.5), found)["key"] == "R+2"  # type: ignore[index]
    # R+3 es el día de ahora: ningún hito pasado lo cuenta.
    assert anatomy.chronicle_moment(sample(33), found) is None
    # Un hecho que no es ningún momento, o sin momentos (Tierra), no enlaza.
    assert anatomy.chronicle_moment({"fact": "alert", "at": launch.isoformat()}, found) is None
    assert anatomy.chronicle_moment(phase(14), None) is None


def test_the_state_at_a_moment_is_recomputed_and_signs_nothing(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "nominal", "days": 16})
    now = client.get("/api/anatomy/state").json()
    assert now["moment"] is None
    [stable] = [item for item in now["moments"]["items"] if item["key"] == "phase-stable"]
    signed = client.get("/api/audit", params={"limit": 1}).json()["total_entries"]
    past = client.get("/api/anatomy/state", params={"until": stable["until"]})
    assert past.status_code == 200, past.text
    body = past.json()
    assert body["reference_time"] <= stable["until"] < now["reference_time"]
    assert body["moment"] == {
        "until": stable["until"],
        "label": "Recalculado con las reglas de hoy, sin asiento",
        "basis": [
            alert_history.RECOMPUTED_BASIS, anatomy.MOMENT_EXTERNAL_BASIS,
            alert_history.NOT_STORED,
        ],
    }
    assert body["moment"]["label"].startswith(alert_history.LABEL)
    assert check(anatomy.MOMENT_EXTERNAL_BASIS) == []
    # Con las lecturas cortadas la lista saldría mermada: no se da.
    assert body["moments"] is None
    # Pedir un momento no escribe en el ledger.
    assert client.get("/api/audit", params={"limit": 1}).json()["total_entries"] == signed
    # El estado de ese momento es el que `/status` da con el mismo corte.
    status = client.get("/api/status", params={"until": stable["until"]}).json()
    for region in body["regions"]:
        for entry in region["state"]:
            if entry["level"] is not None:
                assert entry["level"] == status["domains"][entry["domain"]]["level"]


def test_the_series_of_a_past_moment_reaches_that_moment(client: TestClient) -> None:
    """La serie de una variable en un momento pasado: las lecturas más recientes HASTA él."""
    client.post("/api/simulate", params={"scenario": "nominal", "days": 3})
    full = client.get("/api/observations", params={"key": "heart-rate", "limit": 5}).json()
    until = "2026-11-02T00:00:00+00:00"
    cut = client.get(
        "/api/observations", params={"key": "heart-rate", "limit": 5, "until": until}
    ).json()
    assert cut["count"] == 5
    assert all(item["effectiveDateTime"] <= until for item in cut["observations"])
    assert all(item["effectiveDateTime"] > until for item in full["observations"])
    naive = client.get("/api/observations", params={"key": "heart-rate", "until": until[:19]})
    assert naive.status_code == 422


# --------------------------------------------------------------------------- #
# El hígado: una región sin nivel propio (decimoquinta ronda, D11)
# --------------------------------------------------------------------------- #


def test_the_liver_is_a_view_without_a_level_of_its_own() -> None:
    """Enseña sus analitos y dice de quién es el nivel; no crea dominio, nivel ni contramedida."""
    [liver] = [region for region in anatomy.REGIONS if region.key == "liver"]
    assert liver.domains == () and liver.level_of is Domain.NUTRITION
    assert liver.level_note == "El nivel es del dominio nutrición."
    # Los de la ficha de MedlinePlus que el catálogo tiene, todos evaluados en nutrición.
    assert set(liver.analytes) == {
        "albumin", "total-protein", "alkaline-phosphatase", "alt", "ast", "ggt",
        "bilirubin-total", "bilirubin-direct", "ldh",
    }
    assert all(CATALOG[key].domain is Domain.NUTRITION for key in liver.analytes)
    assert anatomy.LIVER_SOURCE.id == "medlineplus-liver-function-tests"
    # Siguen contando en el aparato digestivo: la vista no se los quita a su dominio.
    [digestive] = [region for region in anatomy.REGIONS if region.key == "digestive"]
    assert all(digestive.shows(key) for key in liver.analytes)
    assert not liver.shows("glucose") and not liver.shows("energy-intake-daily")

    persistent = [_deviation(4.5) for _ in range(12)]
    status = RiskEngine().assess("crew-01", persistent)
    proposed = Advisor().recommend(status)
    readings = [
        observation("alt", 30.0, NOW, "crew-01", "test"),
        observation("glucose", 90.0, NOW, "crew-01", "test"),
        observation("heart-rate", 62.0, NOW, "crew-01", "test"),
    ]
    regions = anatomy.state(status, readings, persistent, {}, proposed)
    shown = _region(regions, "liver")
    assert (shown["level"], shown["state"], shown["evidence"]) == (None, [], [])
    assert shown["level_note"] == liver.level_note and shown["level_of"] == "nutrition"
    assert [item["key"] for item in shown["variables"]] == ["alt"]
    assert "glucose" not in {item["key"] for item in shown["unmeasured"]}
    assert shown["has_data"] is True and shown["data_note"] is None
    assert shown["recommendations"] == []
    assert shown["recommendations_note"] == _LIVER_RECOMMENDATIONS_NOTE
    assert shown["analytes_source"]["id"] == "medlineplus-liver-function-tests"
    # El paso RIESGO es el del dominio de su nivel, el mismo que da la región de ese dominio.
    assert shown["level_risk"] == risk_entity.summary(Domain.NUTRITION)
    assert shown["level_risk"] == _region(regions, "digestive")["state"][0]["risk"]
    assert _region(regions, "heart")["level_risk"] is None
    # La región de nutrición sigue con la ALT entre sus variables.
    assert "alt" in {item["key"] for item in _region(regions, "digestive")["variables"]}
    # Corregir una ALT obliga a recalcular la vista del hígado; corregir la glucosa, no.
    data, _dependents = timeline.emma_map()
    assert {"region:liver", "region:digestive"} <= set(data["alt"]["dependientes"])
    assert "region:liver" not in data["glucose"]["dependientes"]


def test_a_region_without_level_declares_its_analytes_coherently() -> None:
    source = anatomy.LIVER_SOURCE
    with pytest.raises(ValueError, match="van juntos"):
        anatomy.Region("x", "X", (), "nota", analytes=("alt",), analytes_source=source)
    with pytest.raises(ValueError, match="van juntos"):
        anatomy.Region("x", "X", (), "nota", analytes=("alt",), level_of=Domain.NUTRITION)
    with pytest.raises(ValueError, match="van juntos"):
        anatomy.Region("x", "X", (Domain.NUTRITION,), "nota", analytes=("alt",),
                       level_of=Domain.NUTRITION, analytes_source=source)
    with pytest.raises(ValueError, match="no es un indicador evaluado"):
        anatomy.Region("x", "X", (), "nota", analytes=("heart-rate",), level_of=Domain.NUTRITION,
                       analytes_source=source)
    # Cada región sin nivel propio tiene la región del dominio de su nivel, comprobado al importar.
    assert {key: home.key for key, home in anatomy.HOME_REGIONS.items()} == {
        "liver": "digestive", "lungs": "heart",
    }
    [liver] = [region for region in anatomy.REGIONS if region.key == "liver"]
    with pytest.raises(ValueError, match="no tiene una región propia"):
        anatomy._home_regions([liver])


# --------------------------------------------------------------------------- #
# Evidencia de investigación, aparte de lo medido (decimoséptima ronda, U16)
# --------------------------------------------------------------------------- #


# Las regiones con capa de investigación y lo que cada una cita (decimonovena ronda, U16).
RESEARCH_BY_REGION = {
    "liver": ["hayslip-2026"],
    "brain": ["hrp-cns-radiation-evidence-report"],
    "muscles": ["hrp-muscle-evidence-report", "osd-51", "osd-343"],
    "immune": ["hrp-immune-evidence-report", "osd-288"],
}


def _by_key(key: str) -> anatomy.Region:
    [region] = [region for region in anatomy.REGIONS if region.key == key]
    return region


def test_the_liver_carries_a_research_layer_apart_from_what_is_measured() -> None:
    """La conversación de ideación: MEASURED / INFERRED / RESEARCH EVIDENCE. El hígado lleva el
    estudio en ratón como capa aparte, con la frase que dice que no está medido en el tripulante;
    las demás regiones con capa son las de la conversación (cerebro, músculo, sistema inmune/bazo)
    y ninguna otra la lleva."""
    liver = _by_key("liver")
    assert [item.id for item in liver.research_refs] == ["hayslip-2026"]
    for region in anatomy.REGIONS:
        assert [item.id for item in region.research_refs] == RESEARCH_BY_REGION.get(region.key, [])
        assert (region.research_dict() is None) == (region.key not in RESEARCH_BY_REGION)
        # Ni `/api/anatomy` ni la matriz de riesgos, que enseñan la frase, la llevan.
        assert "research" not in region.to_dict()
    shown = liver.research_dict()
    assert shown == {
        "note": anatomy.RESEARCH_NOTE, "items": [anatomy.LIVER_RESEARCH.to_dict()],
        "facility": None,
    }
    assert anatomy.RESEARCH_NOTE.startswith("Lo observado en estudios con otras personas o con")
    assert "no medido en este tripulante" in anatomy.RESEARCH_NOTE
    assert "cada ficha dice su población" in anatomy.RESEARCH_NOTE
    assert "No afirma que le esté ocurriendo" in anatomy.RESEARCH_NOTE
    assert "no cuenta en el nivel ni en las alertas" in anatomy.RESEARCH_NOTE
    [item] = shown["items"]
    # La ficha tal cual, con su salvedad: no es solo de personas y lo dice, y el rótulo también.
    assert item["population"] == "human_and_animal"
    assert item["population_label"].startswith("humanos y modelo animal: ")
    assert "hígado de ratón" in item["population_label"]
    assert "ratón" in item["scope_in_view"] and "No dice nada de un tripulante" in item["notes"]
    for text in (anatomy.RESEARCH_NOTE, item["relevance"], item["population_label"]):
        assert check(text) == [], text


def test_the_research_relevance_says_no_more_than_the_card() -> None:
    """Cada cosa que la relevancia dice del estudio está en su ficha (título o nota); nada del
    tratamiento que probó, que la ficha cita solo para decir que no mejoró nada."""
    ref = anatomy.LIVER_RESEARCH.citation.ref
    relevance = anatomy.LIVER_RESEARCH.citation.relevance or ""
    notes = ref.notes or ""
    said = {
        "hígado de ratón": "hígado de ratón" in notes,
        "no medido en este tripulante": "No dice nada de un tripulante" in notes,
        "miARN y TGF-β": "miRNA-TGF-β" in ref.title,
        "senescencia y fibrosis": "senescence and fibrosis" in ref.title,
        "microgravedad simulada y análogos de radiación de espacio profundo en Tierra": (
            "microgravedad simulada y análogos de radiación de espacio profundo, en Tierra" in notes
        ),
        "transcriptómica de sangre del Twins Study y de Inspiration4": (
            "transcriptómica de sangre del Twins Study y de Inspiration4" in notes
        ),
    }
    for phrase, backed in said.items():
        assert phrase in relevance, phrase
        assert backed, phrase
    for unsaid in ("antagomir", "tratamiento", "mejor", "astronauta"):
        assert unsaid not in relevance.lower(), unsaid


def test_the_research_layer_moves_no_level_and_no_domain_evidence() -> None:
    """Ni nivel, ni evidencia del dominio, ni contramedida: la capa va aparte, en su clave."""
    persistent = [_deviation(4.5) for _ in range(12)]
    status = RiskEngine().assess("crew-01", persistent)
    proposed = Advisor().recommend(status)
    readings = [observation("alt", 30.0, NOW, "crew-01", "test")]
    regions = anatomy.state(status, readings, persistent, {}, proposed)
    shown = _region(regions, "liver")
    assert (shown["level"], shown["state"], shown["evidence"]) == (None, [], [])
    liver = _by_key("liver")
    assert shown["research"] == liver.research_dict() and shown["research"] is not None
    assert shown["analytes_source"]["id"] == "medlineplus-liver-function-tests"
    for region in regions:
        # La capa de cada región es la de su `Region`, y las demás no llevan ninguna.
        assert region["research"] == _by_key(region["key"]).research_dict()
        cited = {
            item["id"]
            for block in region["evidence"] for item in block["items"]
        } | {ref["id"] for rec in region["recommendations"] for ref in rec.get("evidence", [])}
        assert "hayslip-2026" not in cited, region["key"]
        # La evidencia del dominio es la de siempre (`evidence/links.py`): la capa no la toca,
        # ni siquiera donde vuelve a citar una ficha que el dominio ya cita (OSD-288, inmune).
        assert [block["items"] for block in region["evidence"]] == [
            [item.to_dict() for item in evidence_for(Domain(block["domain"]))]
            for block in region["evidence"]
        ]
    for domain in Domain:
        assert "hayslip-2026" not in {item.id for item in evidence_for(domain)}
    # Ninguna ficha de la capa entra en una recomendación, las nuevas tampoco.
    layer = {item.id for region in anatomy.REGIONS for item in region.research_refs}
    for region in regions:
        for rec in region["recommendations"]:
            assert not layer & {ref["id"] for ref in rec.get("evidence", [])}, region["key"]


def test_the_research_layer_only_takes_cards_with_a_read_population() -> None:
    """Desde la decimonovena ronda la capa admite personas y animales, cada ficha con su rótulo;
    lo que no admite es una ficha sin población ni un rótulo que diga otra clase que la ficha."""
    # La página del NSRL no tiene población («no aplica»): no es un estudio, es una instalación.
    assert "population" in anatomy.NSRL_FACILITY.ref.not_applicable
    with pytest.raises(ValueError, match="sin población en el registro"):
        anatomy.ResearchItem(anatomy.NSRL_FACILITY, "humanos: usuarios del laboratorio")
    # Un informe cuya población nadie ha leído tampoco: el rótulo no tendría respaldo.
    # Desde U3 ninguna ficha del registro tiene la población por leer: se quita a una copia.
    read = cite("hrp-bmed-evidence-report")
    pending = replace(read, ref=replace(read.ref, population=None))
    assert "population" in pending.ref.unverified
    with pytest.raises(ValueError, match="sin población en el registro"):
        anatomy.ResearchItem(pending, "humanos: tripulantes")
    # Un rótulo que diga «humanos» de un estudio en ratón.
    with pytest.raises(ValueError, match="tiene que empezar por «modelo animal:»"):
        anatomy.ResearchItem(cite("osd-288"), "humanos: 12 tripulantes")
    # Y la clase sola, sin los dos puntos, tampoco vale: el rótulo sigue con lo concreto.
    with pytest.raises(ValueError, match="tiene que empezar por «humanos:»"):
        anatomy.ResearchItem(cite("osd-51"), "humanos sanos")
    # Ni la clase con sus dos puntos y nada detrás.
    with pytest.raises(ValueError, match="no dice nada tras la clase"):
        anatomy.ResearchItem(cite("osd-51"), "humanos:  ")
    allowed = anatomy.Region(
        "x", "X", (Domain.NUTRITION,), "nota", research_refs=(anatomy.LIVER_RESEARCH,),
        function_note="Sin función que describir.",
    )
    research = allowed.research_dict()
    assert research is not None and research["note"] == anatomy.RESEARCH_NOTE


def test_each_research_card_names_its_population_with_the_class_of_its_card() -> None:
    """Especificación §2, no mezclar humanos y animales: cada ficha de la capa lleva a la vista
    un rótulo que empieza por la clase que declara en el registro y sigue con lo leído (especie,
    cuántos, dónde). Los rótulos de las clases cubren todas las del registro."""
    assert set(anatomy.RESEARCH_POPULATION_LABELS) == set(POPULATIONS)
    seen: set[str] = set()
    for region in anatomy.REGIONS:
        for item in region.research_refs:
            ref = item.citation.ref
            assert ref.population is not None, item.id
            prefix = f"{anatomy.RESEARCH_POPULATION_LABELS[ref.population]}: "
            assert item.population.startswith(prefix), item.id
            assert len(item.population) > len(prefix) + 10, item.id
            assert item.to_dict()["population_label"] == item.population
            # Sin veredicto y sin orden: lo que dice la ficha, con el filtro de lenguaje.
            assert check(item.population) == [] and check(item.citation.relevance or "") == []
            seen.add(ref.population)
    assert seen == {"animal", "human", "human_and_animal"}
    # Los rótulos concretos: el bazo de ratón dice ratón y cuántos; el reposo en cama, 24 mujeres
    # y sin vuelo; los de «humano y animal» dicen qué parte es de personas.
    spleen = anatomy.IMMUNE_RESEARCH_SPLEEN.population
    assert spleen.startswith("modelo animal: ratón;") and "12 ratones" in spleen
    assert "9 muestras de bazo" in spleen
    bedrest = anatomy.MUSCLE_RESEARCH_BEDREST.population
    assert bedrest.startswith("humanos: 24 mujeres") and "en Tierra" in bedrest
    assert "destellos de luz del Apolo" in anatomy.CNS_RESEARCH.population
    assert "no astronautas" not in anatomy.CNS_RESEARCH.population
    assert "primates" not in anatomy.CNS_RESEARCH.population
    assert "STS-78" in anatomy.MUSCLE_RESEARCH_REPORT.population
    assert "ficheros abiertos son de músculo de ratón" in anatomy.MUSCLE_RESEARCH_MOUSE.population
    assert "no da un número total de tripulantes" in anatomy.IMMUNE_RESEARCH_REPORT.population


def test_the_brain_names_where_the_research_is_done_apart_from_the_studies() -> None:
    """El NSRL va como instalación, no como estudio: su ficha no tiene población («no aplica») y
    la capa lo enseña aparte con su propia frase. Una instalación sin estudios, o una ficha con
    población puesta como instalación, no se construyen."""
    brain = _by_key("brain")
    facility = brain.research_facility
    assert facility is not None and facility.id == "bnl-nsrl"
    assert "population" in facility.ref.not_applicable
    shown = brain.research_dict()
    assert shown is not None and shown["facility"] == {
        "note": anatomy.RESEARCH_FACILITY_NOTE, "item": facility.to_dict(),
    }
    assert "instalación" in anatomy.RESEARCH_FACILITY_NOTE
    assert "no tiene población" in anatomy.RESEARCH_FACILITY_NOTE
    assert check(anatomy.RESEARCH_FACILITY_NOTE) == [] and check(facility.relevance or "") == []
    # Lo que la relevancia cita de la página está leído en su ficha.
    assert "only place designed and built to study a space radiation environment" in (
        facility.ref.notes or ""
    )
    for region in anatomy.REGIONS:
        if region.key != "brain":
            assert region.research_facility is None
    with pytest.raises(ValueError, match="una instalación sin estudios"):
        anatomy.Region(
            "x", "X", (Domain.NUTRITION,), "nota", research_facility=anatomy.NSRL_FACILITY
        )
    with pytest.raises(ValueError, match="es un estudio, no una instalación"):
        anatomy.Region(
            "x", "X", (Domain.NUTRITION,), "nota",
            research_refs=(anatomy.LIVER_RESEARCH,), research_facility=cite("osd-288"),
        )


def test_each_new_research_relevance_says_no_more_than_its_card() -> None:
    """Lo que la relevancia y el rótulo dicen de cada estudio está en su ficha (título o nota),
    frase a frase; nada de astronautas medidos ni de veredictos. Son las frases elegidas, no todas:
    el resto del texto libre lo vigila la revisión."""
    said: dict[str, dict[str, str]] = {
        "hrp-cns-radiation-evidence-report": {
            "ratones y ratas": "mouse and rat behavioral paradigms",
            "10-50 cGy": "low doses (10-50 cGy)",
            "pacientes de radioterapia": "radiotherapy patients",
            "falta epidemiología humana": "lack of human epidemiology data",
            "misiones pasadas es muy improbable": "past NASA missions is highly unlikely",
            "destellos de luz del Apolo": "destellos de luz",
            "expuestos en Tierra": "expuestos en Tierra",
        },
        "hrp-muscle-evidence-report": {
            "antes y después de la misión": "antes y después de la misión",
            "ecografía (estudio SPRINT)": "ecografía (estudio SPRINT)",
            "dinamómetro de pantorrilla del STS-78": "dinamómetro de pantorrilla del STS-78",
            "tripulaciones de la ISS y del STS-78": "tripulaciones de la ISS y, en la capa",
            "de 2015": "Informe de evidencia muscular de 2015",
        },
        "osd-51": {
            "60 días de reposo en cama": "60 días en Tierra",
            "ejercicio o nutrición": "ejercicio o nutrición",
            "no es vuelo ni constantes vitales": "no es vuelo ni constantes vitales",
        },
        "osd-343": {
            "estrés mitocondrial": "mitochondrial stress",
            "gastrocnemio de Rodent Research-9": "Rodent Research-9 (RR-9) mission tissues",
            "no un umbral ni una medida sobre este tripulante": (
                "no un umbral ni una medida sobre este tripulante"
            ),
        },
        "hrp-immune-evidence-report": {
            "tras 6 meses de vuelo": "following 6 months of flight",
            "reactivación de herpesvirus latentes": "latent herpes viruses reactivate",
            "herpes labial, erupciones, alergias atípicas e infecciones": (
                "cold sores, rashes, atypical allergies, and infections"
            ),
            "sin poder confirmarlos": "diagnoses are generally not feasible",
            "ratas del SLS-2": "SLS-2 mission, rats were flown",
            "13 días del STS-135": "13 days of spaceflight",
        },
        "osd-288": {
            "35 días en la ISS": "35 días en la ISS",
            "performed about spleen": "performed about spleen",
            "altera la función inmune en un mamífero": "altera la función inmune en un mamífero",
        },
    }
    items = {
        item.id: item for region in anatomy.REGIONS for item in region.research_refs
    }
    for ref_id, phrases in said.items():
        item = items[ref_id]
        relevance = item.citation.relevance or ""
        said_of_it = f"{relevance} {item.population}"
        card = f"{item.citation.ref.title} {item.citation.ref.notes or ''}"
        for phrase, backing in phrases.items():
            assert phrase in said_of_it, (ref_id, phrase)
            assert backing in card, (ref_id, backing)
        for unsaid in ("demostrado en astronautas", "en este tripulante se", "diagnóstico"):
            assert unsaid not in relevance.lower(), (ref_id, unsaid)
    assert set(said) == set(items) - {"hayslip-2026"}


def test_the_research_layer_is_not_in_the_rules_footprint() -> None:
    """Invariante 5: citar no decide nada. `rules_version` mira solo el análisis, y la capa vive
    en el mapa anatómico."""
    assert "app.anatomy" not in versioning.GUARDED
    assert all(name.startswith("app.analysis.") for name in versioning.GUARDED)


def test_the_route_serves_each_research_card_with_its_label(chain: Callable[[str], Chain]) -> None:
    """`/api/anatomy/state` lleva la capa en las cuatro regiones, cada ficha con su rótulo y la
    instalación solo en el cerebro; las demás regiones, `null`. La versión de reglas es la misma
    que la de `/status`: la capa no la mueve."""
    state, status = chain("arrhythmia")
    assert state["rules_version"] == status["rules_version"]
    for region in state["regions"]:
        shown = region["research"]
        if region["key"] not in RESEARCH_BY_REGION:
            assert shown is None, region["key"]
            continue
        assert shown["note"] == anatomy.RESEARCH_NOTE
        assert [item["id"] for item in shown["items"]] == RESEARCH_BY_REGION[region["key"]]
        for item in shown["items"]:
            label, _, rest = item["population_label"].partition(":")
            assert label == anatomy.RESEARCH_POPULATION_LABELS[item["population"]]
            assert rest.strip(), item["id"]
            assert {"scope_caveat", "scope_in_view", "grade", "relevance"} <= set(item)
        if region["key"] == "brain":
            assert shown["facility"] == {
                "note": anatomy.RESEARCH_FACILITY_NOTE, "item": anatomy.NSRL_FACILITY.to_dict(),
            }
        else:
            assert shown["facility"] is None


# --------------------------------------------------------------------------- #
# Densitometrías de dos y tres años (decimoséptima ronda, U16)
# --------------------------------------------------------------------------- #


def test_the_two_and_three_year_scans_have_their_milestones() -> None:
    """R+730 y R+1095 salen de la misma frase de OCHMO-MTB-013 que R+180 y R+365, con la misma
    regla de tramos; lo posterior a R+1095 va junto."""
    note = anatomy.BONE_DXA_SOURCE.ref.notes or ""
    assert "two years, and 3 years post-flight" in note
    assert "or until recovered within least significant change of pre-flight" in note
    [dxa] = [
        item for item in anatomy.POSTFLIGHT_SOURCES if item.citation is anatomy.BONE_DXA_SOURCE
    ]
    assert dxa.days == (180, 365, 730, 1095) and dxa.scope == anatomy.BONE_DXA_SCOPE
    assert not {730, 1095} & set(anatomy.DESIGN_MILESTONES)
    start = dt.date(2026, 11, 1)
    readings = [_reading(day) for day in (-2, 5, 230, 530, 830, 1130, 1330)]
    found = anatomy.moments(readings, start, 30)
    texts = {
        item["key"]: item["display"]
        for item in found["items"] if item["kind"] == "postflight_milestone"
    }
    assert texts == {
        "R+200": "Tramo de R+181 a R+365: última lectura, en R+200",
        "R+500": "Tramo de R+366 a R+730: última lectura, en R+500",
        "R+800": "Tramo de R+731 a R+1095: última lectura, en R+800",
        "R+1100": "Después de R+1095: última lectura, en R+1100",
    }
    basis = found["postflight_milestones"]["basis"]
    assert "a uno, dos y tres años del regreso, o hasta que el hueso se recupera" in basis
    assert "lo posterior a R+1095 va junto" in basis


# --------------------------------------------------------------------------- #
# Hitos prevuelo con su ficha (decimosexta ronda, E13)
# --------------------------------------------------------------------------- #


def test_each_preflight_day_falls_in_one_milestone() -> None:
    """L-180 y L-90 de Standard Measures y L-30 de la densitometría: cada día va al primero que no
    queda antes de él, y los últimos 29 días son del lanzamiento."""
    assert anatomy.PREFLIGHT_MILESTONES == (180, 90, 30)
    expected = {
        400: 180, 181: 180, 180: 180, 179: 90, 90: 90, 89: 30, 30: 30, 29: None, 0: None,
    }
    assert {day: anatomy.preflight_milestone(day) for day in expected} == expected
    launch = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)
    assert anatomy.days_before_launch(launch - dt.timedelta(days=29, hours=13), launch) == 30
    assert anatomy.days_before_launch(launch - dt.timedelta(hours=3), launch) == 0


def test_a_milestone_day_is_read_or_design_not_both() -> None:
    """Un día de hito es leído o de diseño: las dos cosas a la vez se rechazan al importar. Que
    lo den dos fuentes leídas vale (cada una con su alcance), y el día sale una vez."""
    assert anatomy._join_milestones((30, 0), (7,)) == (0, 7, 30)
    assert anatomy._join_milestones((90,), (180,), reverse=True) == (180, 90)
    assert anatomy._join_milestones((180, 180), ()) == (180,)
    with pytest.raises(ValueError, match="de diseño a la vez"):
        anatomy._join_milestones((90,), (90,))
    assert "es de EMMA" in anatomy.PREFLIGHT_MILESTONES_BASIS


def test_each_milestones_basis_names_exactly_its_milestones() -> None:
    """La frase de la base se escribe a mano: si un hito cambia de día y la frase no, esto falla."""
    named_after = set(re.findall(r"R\+(\d+)", anatomy.MILESTONES_BASIS))
    assert {int(day) for day in named_after} == set(anatomy.POSTFLIGHT_MILESTONES)
    named_before = set(re.findall(r"L-(\d+)", anatomy.PREFLIGHT_MILESTONES_BASIS))
    assert {int(day) for day in named_before} == set(anatomy.PREFLIGHT_MILESTONES)
    # Y cada día leído, en la misma frase que la fuente que lo da (por su nombre en la base).
    for basis, sources, sign in (
        (anatomy.MILESTONES_BASIS, anatomy.POSTFLIGHT_SOURCES, "R+"),
        (anatomy.PREFLIGHT_MILESTONES_BASIS, anatomy.PREFLIGHT_SOURCES, "L-"),
    ):
        sentences = basis.split(". ")
        for item in sources:
            name = (
                "Spaceflight Standard Measures"
                if item.citation is anatomy.STANDARD_MEASURES_SOURCE
                else "pérdida ósea"
            )
            for day in item.days:
                assert any(
                    name in sentence and re.search(rf"{re.escape(sign)}{day}\b", sentence)
                    for sentence in sentences
                ), (sign, day, name)


def test_preflight_readings_give_one_moment_per_milestone() -> None:
    """Un momento por tramo prevuelo, en su última lectura; la última lectura prevuelo no se ofrece
    (es el estado del lanzamiento) y su tramo se pide en el día de antes con lecturas, como el
    tramo abierto del posvuelo; nada se ofrece sin lecturas antes."""
    start = dt.date(2026, 11, 1)
    launch = dt.datetime.combine(start, dt.time(0, 0), tzinfo=dt.UTC)
    readings = [_reading(day) for day in (-200, -185, -150, -120, -60, -45, -10, 5)]
    found = anatomy.moments(readings, start, 30)
    preflight = [item for item in found["items"] if item["kind"] == "preflight_milestone"]
    assert [item["key"] for item in preflight] == ["L-185", "L-120", "L-45"]
    texts = {item["key"]: item["display"] for item in preflight}
    assert texts == {
        "L-185": "Hasta L-180: última lectura, en L-185",
        "L-120": "Tramo de L-179 a L-90: última lectura, en L-120",
        "L-45": "Tramo de L-89 a L-30: última lectura, en L-45",
    }
    for item in preflight:
        assert dt.datetime.fromisoformat(item["until"]) == launch - dt.timedelta(
            days=item["days_before_launch"])
        assert item["days_after_landing"] is None
    keys = [item["key"] for item in found["items"]]
    assert keys.index("L-45") < keys.index("preflight")
    # Sin lecturas después de L-30 el tramo de L-45 es el estado del lanzamiento: no se repite.
    late = anatomy.moments([_reading(day) for day in (-120, -45, 5)], start, 30)
    assert [item["key"] for item in late["items"]] == ["L-120", "preflight"]
    # Con otra lectura antes en el mismo tramo, el tramo se pide en ella.
    earlier = anatomy.moments([_reading(day) for day in (-120, -60, -45, 5)], start, 30)
    assert [item["key"] for item in earlier["items"]] == ["L-120", "L-60", "preflight"]
    assert earlier["items"][1]["display"] == "Tramo de L-89 a L-30: última lectura, en L-60"
    # Lo posterior a L-30 no es un hito: es el momento del lanzamiento, aunque tenga dos días.
    close = anatomy.moments([_reading(day) for day in (-120, -20, -10, 5)], start, 30)
    assert [item["key"] for item in close["items"]] == ["L-120", "preflight"]
    # El día del hito se dice como tal.
    exact = anatomy.moments([_reading(day) for day in (-90, -10, 5)], start, 30)
    assert exact["items"][0]["display"] == "L-90: última lectura de ese día"
    # Sin nada antes del vuelo, ningún hito prevuelo.
    assert not [
        item for item in anatomy.moments([_reading(1), _reading(15)], start, 180)["items"]
        if item["kind"] == "preflight_milestone"
    ]
    milestones = found["preflight_milestones"]
    assert milestones["read"] == [180, 90, 30] and milestones["design"] == []
    sources = {item["source"]["id"]: item for item in milestones["sources"]}
    assert sources["hardy-2025-spaceflight-standard-measures"]["days"] == [180, 90]
    assert sources["ochmo-mtb-013"]["days"] == [30]
    assert sources["ochmo-mtb-013"]["scope"] == anatomy.BONE_DXA_SCOPE
    assert "solo del hueso" in milestones["basis"]
    for text in [*texts.values(), milestones["basis"], found["basis"]]:
        assert check(text) == [], text


def test_a_phase_change_never_links_to_a_milestone_that_falls_on_it() -> None:
    """Un hito cae en una lectura; si una lectura cayera un segundo antes de un cambio de fase, el
    cambio de fase no enlaza con ese hito, sino con su momento de fase."""
    start = dt.date(2026, 11, 1)
    launch = dt.datetime.combine(start, dt.time(0, 0), tzinfo=dt.UTC)
    moments = {"items": [
        {"key": "L-40", "kind": "preflight_milestone", "display": "L",
         "until": (launch - dt.timedelta(seconds=1)).isoformat()},
    ]}
    event = {"fact": "phase-change", "at": launch.isoformat()}
    assert anatomy.chronicle_moment(event, moments) is None


# --------------------------------------------------------------------------- #
# Los pulmones: una región sin nivel propio (decimosexta ronda, E13)
# --------------------------------------------------------------------------- #


def test_the_lungs_are_a_view_without_a_level_of_their_own() -> None:
    """Enseñan la frecuencia respiratoria y la saturación de oxígeno, que cuentan en el dominio
    cardiovascular; no crean dominio, nivel ni contramedida, y el motor dice lo mismo que antes."""
    [lungs] = [region for region in anatomy.REGIONS if region.key == "lungs"]
    assert lungs.domains == () and lungs.level_of is Domain.CARDIOVASCULAR
    assert lungs.level_note == "El nivel es del dominio cardiovascular."
    assert lungs.analytes == ("respiratory-rate", "oxygen-saturation")
    assert anatomy.LUNG_SOURCE.id == "nhlbi-respiratory-failure"
    [heart] = [region for region in anatomy.REGIONS if region.key == "heart"]
    assert all(heart.shows(key) for key in lungs.analytes)
    for key in ("heart-rate", "body-temperature", "systolic-bp", "vo2-peak"):
        assert not lungs.shows(key), key

    persistent = [_deviation(4.5, "respiratory-rate") for _ in range(12)]
    status = RiskEngine().assess("crew-01", persistent)
    proposed = Advisor().recommend(status)
    readings = [
        observation("respiratory-rate", 26.0, NOW, "crew-01", "test"),
        observation("heart-rate", 62.0, NOW, "crew-01", "test"),
    ]
    regions = anatomy.state(status, readings, persistent, {}, proposed)
    shown = _region(regions, "lungs")
    assert (shown["level"], shown["state"], shown["evidence"]) == (None, [], [])
    assert shown["level_of"] == "cardiovascular"
    assert [item["key"] for item in shown["variables"]] == ["respiratory-rate"]
    assert [item["key"] for item in shown["unmeasured"]] == ["oxygen-saturation"]
    assert shown["recommendations"] == []
    assert shown["recommendations_note"] == _LUNG_RECOMMENDATIONS_NOTE
    assert shown["analytes_source"]["id"] == "nhlbi-respiratory-failure"
    assert shown["level_risk"] == risk_entity.summary(Domain.CARDIOVASCULAR)
    assert shown["level_risk"] == _region(regions, "heart")["state"][0]["risk"]
    # La variable cuenta lo mismo en la vista que en su dominio: el motor la valora una vez.
    heart_shown = _region(regions, "heart")
    [mine] = shown["variables"]
    theirs = next(item for item in heart_shown["variables"] if item["key"] == "respiratory-rate")
    assert mine == theirs and mine["contributes"] is True
    # El nivel del corazón es el del motor, y el motor no tiene un dominio más.
    assert heart_shown["level"] == str(status.domains[Domain.CARDIOVASCULAR].level) != "nominal"
    assert set(status.domains) <= set(Domain)
    assert "lungs" not in {str(domain) for domain in Domain}
    # Corregir una frecuencia respiratoria obliga a recalcular la vista de los pulmones; un pulso,
    # no.
    data, _dependents = timeline.emma_map()
    assert {"region:lungs", "region:heart"} <= set(data["respiratory-rate"]["dependientes"])
    assert "region:lungs" not in data["heart-rate"]["dependientes"]
    assert check(lungs.note) == [] and check(lungs.level_note or "") == []


# --------------------------------------------------------------------------- #
# Para qué sirve cada órgano (vigésima ronda, unidad 2): la función, con su ficha leída
# --------------------------------------------------------------------------- #

# La ficha de la función de cada región; la radiación («todo el cuerpo») no es un órgano y no
# lleva ninguna.
FUNCTION_SOURCE_BY_REGION = {
    "brain": "seer-nervous-system",
    "eyes": "nei-how-the-eyes-work",
    "heart": "seer-cardiovascular-system",
    "lungs": "seer-respiratory-system",
    "bones": "seer-skeletal-system",
    "muscles": "seer-muscular-system",
    "bladder": "seer-urinary-system",
    "digestive": "seer-digestive-system",
    "liver": "seer-digestive-accessory-organs",
    "immune": "seer-lymphatic-system",
}


def test_every_region_says_what_it_is_for_with_a_read_card_or_says_it_has_none() -> None:
    known = registry()
    for region in anatomy.REGIONS:
        served = region.function_dict()
        # No viaja con cada riesgo de `/api/risks`: no es de la frase de la región.
        assert not {"function", "function_refs", "function_note"} & set(region.to_dict())
        expected = FUNCTION_SOURCE_BY_REGION.get(region.key)
        if expected is None:
            assert region.function is None and region.function_refs == (), region.key
            assert served["function"] is None and served["function_refs"] == []
            assert served["function_note"] == anatomy.NO_FUNCTION_NOTE
            continue
        assert region.function and region.function.strip(), region.key
        assert [item.id for item in region.function_refs] == [expected], region.key
        assert all(item.id in known and item.relevance for item in region.function_refs)
        assert served["function"] == region.function and served["function_note"] is None
        assert served["function_refs"] == [item.to_dict() for item in region.function_refs]
        # Es de anatomía humana, no de un estudio en animales: sin salvedad de población.
        assert all(known[item.id].population == "human" for item in region.function_refs)
    assert {region.key for region in anatomy.REGIONS} - set(FUNCTION_SOURCE_BY_REGION) == {
        "whole-body"
    }


def test_a_function_goes_with_its_cards_or_not_at_all() -> None:
    source = anatomy.HEART_FUNCTION_SOURCE
    with pytest.raises(ValueError, match="van juntas"):
        anatomy.Region("x", "X", (Domain.NUTRITION,), "nota", function="Sirve para algo.")
    with pytest.raises(ValueError, match="van juntas"):
        anatomy.Region("x", "X", (Domain.NUTRITION,), "nota", function_refs=(source,))
    with pytest.raises(ValueError, match="vacía"):
        anatomy.Region(
            "x", "X", (Domain.NUTRITION,), "nota", function=" ", function_refs=(source,)
        )
    # Sin función, la región dice por qué; con ella, no lleva esa frase.
    with pytest.raises(ValueError, match="una de las dos"):
        anatomy.Region("x", "X", (Domain.NUTRITION,), "nota")
    with pytest.raises(ValueError, match="una de las dos"):
        anatomy.Region("x", "X", (Domain.NUTRITION,), "nota", function_note=" ")
    with pytest.raises(ValueError, match="una de las dos"):
        anatomy.Region(
            "x", "X", (Domain.NUTRITION,), "nota", function="Sirve para algo.",
            function_refs=(source,), function_note="No hay función.",
        )


def test_the_function_texts_pass_the_guard() -> None:
    texts = [anatomy.NO_FUNCTION_NOTE]
    for region in anatomy.REGIONS:
        texts += [region.function or "", *(item.relevance or "" for item in region.function_refs)]
    for text in texts:
        assert check(text) == [], text


def test_each_function_says_no_more_than_its_card() -> None:
    """Lo que dice cada frase está en la nota de su ficha, frase a frase (las elegidas)."""
    said: dict[str, dict[str, str]] = {
        "seer-nervous-system": {
            "control, regulación y comunicación": "controlling, regulatory, and communicating",
            "el pensamiento, el aprendizaje y la memoria": "thought, learning, and memory",
        },
        "nei-how-the-eyes-work": {
            "fotorreceptores convierten la luz": "photoreceptors turn the light",
            "por el nervio óptico hasta el cerebro": "through the optic nerve to the brain",
            "las imágenes que se ven": "turns the signals into the images you see",
        },
        "seer-cardiovascular-system": {
            "bomba muscular": "muscular pumping device",
            "circuito cerrado de vasos": "closed circle or circuit of vessels",
            "función de transporte": "ultimate transport function",
        },
        "seer-respiratory-system": {
            "junto con el circulatorio": "works with the circulatory system",
            "productos de desecho del metabolismo": "waste products of metabolism",
            "se intercambian gases con la sangre": "exchange of gases between the lungs and",
            "regular el pH de la sangre": "regulate pH of the blood",
        },
        "seer-skeletal-system": {
            "frente a la gravedad": "against the pull of gravity",
            "protege los órganos blandos": "protect the soft organs",
            "hacen de palancas": "lever systems to produce body movement",
            "sobre todo en su médula roja": "mostly takes place in the red marrow",
        },
        "seer-muscular-system": {
            "unidos a los huesos, a órganos internos y a vasos": (
                "attached to bones or internal organs and blood vessels"
            ),
            "mantiene la postura": "Posture, such as sitting and standing",
            "temperatura del cuerpo": "to maintain body temperature",
        },
        "seer-urinary-system": {
            "el volumen y la composición de los líquidos": "volume and composition of body fluids",
            "cuánta agua se elimina con la orina": "amount of water that is excreted in the urine",
            "desecho del metabolismo de las células": "result of cellular metabolism",
        },
        "seer-digestive-system": {
            "moléculas que las células pueden absorber y usar": (
                "absorbed and utilized by the cells"
            ),
            "lo que no se puede digerir ni absorber": "cannot be digested or absorbed",
        },
        "seer-digestive-accessory-organs": {
            "muchas de ellas vitales": "many of these are vital to life",
            "sales biliares": "synthesis of bile salts",
            "proteínas del plasma": "synthesis of plasma protein",
            "desintoxica": "detoxification",
            "las de Kupffer, limpian la sangre": "Kupffer cells that line the sinusoids",
        },
        "seer-lymphatic-system": {
            "microorganismos invasores y de la enfermedad": (
                "defense against invading microorganisms and disease"
            ),
            "filtran la linfa": "filter the lymph to remove microorganisms",
            "linfocitos que destruyen": "lymphocytes that destroy invading organisms",
        },
    }
    known = registry()
    by_card = {
        item.id: region.function or ""
        for region in anatomy.REGIONS for item in region.function_refs
    }
    assert set(by_card) == set(said)
    for ref_id, pairs in said.items():
        notes = known[ref_id].notes or ""
        for ours, theirs in pairs.items():
            assert ours in by_card[ref_id], (ref_id, ours)
            assert theirs in notes, (ref_id, theirs)


def test_the_function_is_served_in_the_map_and_in_the_chain(
    client: TestClient, chain: Callable[[str], Chain]
) -> None:
    mapped = client.get("/api/anatomy").json()["regions"]
    state, _status = chain("arrhythmia")
    chained = state["regions"]
    for regions in (mapped, chained):
        for region in regions:
            assert {"function", "function_refs", "function_note"} <= set(region), region["key"]
            ids = [item["id"] for item in region["function_refs"]]
            expected = FUNCTION_SOURCE_BY_REGION.get(region["key"])
            assert ids == ([] if expected is None else [expected]), region["key"]
    # La función no toca la evidencia del dominio: sus fichas no salen en el bloque del motor.
    for region in chained:
        cited = {item["id"] for block in region["evidence"] for item in block["items"]}
        assert cited.isdisjoint(FUNCTION_SOURCE_BY_REGION.values()), region["key"]
