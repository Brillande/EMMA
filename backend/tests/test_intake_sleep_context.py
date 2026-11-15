"""La ingesta de líquidos, la dieta y el sueño como contexto de una alerta (base de conocimiento
§5, especificación §9 y §10).

Qué fijan estas pruebas:
- qué claves del catálogo lee cada una de las tres fuentes, y que el estado las analiza;
- que cada fuente dice si tenía dato en la ventana, y nombra el indicador que falta;
- que lo registrado se lista con la misma ventana, el mismo rótulo de no-causa y la cifra del
  catálogo, y que ningún texto dice si fue poco o mucho;
- que una lectura que no es medida no llega a estas fuentes por la API;
- que todo el texto pasa el linter de lenguaje (invariante 7);
- y la que importa (invariante 5): el veredicto es idéntico con y sin estas fuentes.
"""

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import alert_context
from app.analysis.alert_context import (
    LABEL,
    NO_DATA,
    PARTIAL,
    RECORDED_KEYS,
    RECORDED_SOURCES,
    WINDOW_AFTER,
    WINDOW_BEFORE,
    WITH_DATA,
    around,
)
from app.ingest.codes import DESCRIPTIVE_ONLY, get
from app.ingest.fhir import VitalObservation
from app.text_guard import check

START = dt.date(2026, 11, 1)
T0 = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.UTC)
REFERENCE = T0 + dt.timedelta(hours=30)

FLUID = "fluid-intake-24h"
ENERGY = "energy-intake-daily"
APPETITE = "appetite-rating"
SLEEP = "sleep-duration"
EFFICIENCY = "sleep-efficiency"
KINDS = ("fluid_intake", "diet", "sleep")


def _h(hours: float) -> dt.datetime:
    return T0 + dt.timedelta(hours=hours)


def _obs(key: str, value: float, moment: dt.datetime, source: str = "manual") -> VitalObservation:
    return VitalObservation(
        code=get(key), value=value, effective=moment, subject="crew-01", source=source
    )


def _context(recorded: list[VitalObservation], **override: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "onset": T0, "reference": REFERENCE, "habitat_readings": [], "habitat_excursions": [],
        "mission_events": [], "solar": None, "adoptions": [], "mission_start": START,
        "mission_days": 180, "gravity_regime": "microgravedad", "recorded": recorded,
    }
    arguments.update(override)
    return around(**arguments)


def _of(context: dict[str, Any], kind: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    [source] = [item for item in context["sources"] if item["kind"] == kind]
    return [item for item in context["items"] if item["kind"] == kind], source


def _status_of(context: dict[str, Any]) -> dict[str, tuple[str, int]]:
    sources = {kind: _of(context, kind)[1] for kind in KINDS}
    return {kind: (source["status"], source["found"]) for kind, source in sources.items()}


# --------------------------------------------------------------------------- #
# Qué leen las tres fuentes
# --------------------------------------------------------------------------- #

def test_the_three_sources_read_catalog_keys_that_the_state_analyses() -> None:
    by_kind = {spec.kind: spec for spec in RECORDED_SOURCES}
    assert tuple(by_kind) == KINDS
    assert by_kind["fluid_intake"].keys == (FLUID,)
    assert by_kind["diet"].keys == (ENERGY, APPETITE)
    assert by_kind["sleep"].keys == (SLEEP, EFFICIENCY)
    for key in RECORDED_KEYS:
        assert get(key).display_es, key
        # Descriptivo: el estado no lo lee, y una fuente suya diría que cuenta.
        assert key not in DESCRIPTIVE_ONLY, key
    assert {FLUID, ENERGY, APPETITE, SLEEP, EFFICIENCY} == RECORDED_KEYS
    # Las tres van entre el ejercicio y los sistemas del hábitat, y ninguna repite clase.
    kinds = [source["kind"] for source in _context([])["sources"]]
    assert len(kinds) == len(set(kinds))
    assert kinds[kinds.index("exercise") + 1:kinds.index("system_status")] == list(KINDS)


def test_without_readings_each_source_says_no_data() -> None:
    plain = {
        "onset": T0, "reference": REFERENCE, "habitat_readings": [], "habitat_excursions": [],
        "mission_events": [], "solar": None, "adoptions": [], "mission_start": START,
        "mission_days": 180, "gravity_regime": "microgravedad",
    }
    for context in (_context([]), around(**plain)):
        assert _status_of(context) == {kind: (NO_DATA, 0) for kind in KINDS}
        for kind in KINDS:
            items, source = _of(context, kind)
            assert items == []
            assert "que no conste no quiere decir que no" in source["note"]
        assert context["summary"] == "Nada de lo registrado cae dentro de la ventana."


def test_an_indicator_without_readings_in_the_window_is_named() -> None:
    context = _context([_obs(SLEEP, 6.5, _h(-2)), _obs(APPETITE, 6.0, _h(-1))])
    assert _status_of(context) == {
        "fluid_intake": (NO_DATA, 0), "diet": (PARTIAL, 1), "sleep": (PARTIAL, 1),
    }
    assert _of(context, "sleep")[1]["note"].startswith(
        "Sin lectura en la ventana: Eficiencia del sueño. "
    )
    assert _of(context, "diet")[1]["note"].startswith(
        f"Sin lectura en la ventana: {get(ENERGY).display_es}. "
    )
    assert context["summary"] == "Registrado dentro de la ventana: 2."


# --------------------------------------------------------------------------- #
# Lo registrado se lista con la ventana y el rótulo de siempre, y sin juzgarlo
# --------------------------------------------------------------------------- #

def _around_the_onset() -> list[VitalObservation]:
    return [
        _obs(FLUID, 1600.0, _h(-16)), _obs(FLUID, 2400.0, _h(2)),
        _obs(ENERGY, 2100.0, _h(-20)), _obs(APPETITE, 4.0, _h(-20)),
        # Justo en el límite inferior del catálogo: aquí no se dice nada de eso.
        _obs(SLEEP, 5.0, _h(-3)), _obs(EFFICIENCY, 80.0, _h(-3)),
    ]


def test_readings_around_the_onset_are_listed_as_temporal_correlation() -> None:
    context = _context(_around_the_onset())
    assert _status_of(context) == {"fluid_intake": (WITH_DATA, 1), "diet": (WITH_DATA, 2),
                                   "sleep": (WITH_DATA, 2)}
    [fluid], _ = _of(context, "fluid_intake")
    assert fluid["title"] == (
        "Ingesta de líquidos registrada — Ingesta total de líquidos en 24 horas: 2 lecturas, "
        "entre 1600 mL/día y 2400 mL/día"
    )
    assert (fluid["start"], fluid["end"]) == (_h(-16).isoformat(), _h(2).isoformat())
    assert fluid["timing"] == "con lecturas en el inicio de la alerta; primera lectura 16,0 h antes"
    [sleep, efficiency], _ = _of(context, "sleep")
    assert sleep["title"] == "Sueño registrado — Duración del sueño: 1 lectura, 5,0 h"
    assert sleep["timing"] == "3,0 h antes del inicio de la alerta"
    assert efficiency["title"].endswith("Eficiencia del sueño: 1 lectura, 80 %")
    diet, _ = _of(context, "diet")
    assert [item["title"].split(" — ")[0] for item in diet] == ["Dieta registrada"] * 2
    for item in [fluid, sleep, efficiency, *diet]:
        assert item["label"] == LABEL
        assert item["source"] == "lecturas de manual"
        assert (item["value"], item["unit"], item["detail"], item["presence"]) == (
            None, None, None, None
        )
    assert context["summary"] == "Registrado dentro de la ventana: 5."


def test_no_text_of_these_sources_says_whether_it_was_too_little_or_too_much() -> None:
    context = _context(_around_the_onset())
    judging = (
        "poco ", "poca ", "mucho ", "mucha ", "bajo", "baja ", "alto", "alta ", "insuficiente",
        "escas", "límite", "umbral de", "fuera de",
    )
    for kind in KINDS:
        items, source = _of(context, kind)
        assert "no dice si fue" in source["note"], kind
        for text in [item["title"] for item in items] + [item["timing"] for item in items]:
            assert not [word for word in judging if word in text.lower()], text
    for spec in RECORDED_SOURCES:
        assert "Sin umbral propio" in spec.scope


def test_readings_outside_the_window_or_after_the_state_instant_are_not_context() -> None:
    before = WINDOW_BEFORE.total_seconds() / 3600
    after = WINDOW_AFTER.total_seconds() / 3600
    outside = [_obs(FLUID, 2000.0, _h(-before - 1)), _obs(SLEEP, 6.0, _h(after + 1))]
    assert _status_of(_context(outside)) == {kind: (NO_DATA, 0) for kind in KINDS}
    edges = [_obs(FLUID, 2000.0, _h(-before)), _obs(FLUID, 2200.0, _h(after))]
    [item], source = _of(_context(edges), "fluid_intake")
    assert source["status"] == WITH_DATA and "2 lecturas" in item["title"]
    # El estado es de una hora después del inicio: lo registrado más tarde aún no existe.
    late = [_obs(SLEEP, 6.0, _h(2))]
    assert _of(_context(late, reference=_h(1)), "sleep")[1]["status"] == NO_DATA


def test_a_reading_of_another_indicator_is_not_listed_by_these_sources() -> None:
    others = [_obs("heart-rate", 60.0, _h(0)), _obs("exercise-minutes", 30.0, _h(0))]
    context = _context(others)
    assert _status_of(context) == {kind: (NO_DATA, 0) for kind in KINDS}
    assert [item["kind"] for item in context["items"]] == []


def test_the_source_names_every_device_that_recorded() -> None:
    readings = [
        _obs(SLEEP, 6.0, _h(-5), source="wearable:ble"), _obs(SLEEP, 6.2, _h(-4)),
        _obs(SLEEP, 6.1, _h(-3), source="wearable:ble"),
    ]
    [item], _ = _of(_context(readings), "sleep")
    assert item["source"] == "lecturas de manual, wearable:ble"
    assert item["title"].endswith("3 lecturas, entre 6,0 h y 6,2 h")


# --------------------------------------------------------------------------- #
# Lenguaje (invariante 7)
# --------------------------------------------------------------------------- #

def test_every_text_written_by_these_sources_passes_the_language_guard() -> None:
    texts: list[str] = []
    for spec in RECORDED_SOURCES:
        texts += [spec.display, spec.heading, spec.scope, spec.no_data]
    contexts = [
        _context([]), _context(_around_the_onset()),
        _context([_obs(SLEEP, 6.5, _h(-2)), _obs(APPETITE, 6.0, _h(-1))]),
        _context(_around_the_onset(), onset=None),
    ]
    for context in contexts:
        for kind in KINDS:
            items, source = _of(context, kind)
            texts += [source["display"], source["status_display"], source["note"]]
            for item in items:
                texts += [item["title"], item["timing"], item["source"], item["label"]]
    assert len(set(texts)) > 25, "la prueba tiene que mirar textos de verdad"
    # Un volumen bebido en mL es una medida, no una dosis: el filtro de patrones lo caza como
    # «dosing» igual que caza «dosis» en la escala de radiación, y se aparta con el mismo criterio
    # (`test_radiation_projection.py`), solo en la frase de la ingesta y solo esa pareja.
    findings = [
        (text, [
            finding for finding in check(text)
            if not (
                finding.category == "dosing" and finding.match.lower().endswith(" ml")
                and get(FLUID).display_es in text
            )
        ])
        for text in texts
    ]
    assert [(text, found) for text, found in findings if found] == []
    assert any(check(text) for text in texts if get(FLUID).display_es in text), (
        "la frase de la ingesta tiene que llevar su cifra en mL para que la excepción se ejerza"
    )


# --------------------------------------------------------------------------- #
# De punta a punta: solo lecturas medidas, y el veredicto no cambia
# --------------------------------------------------------------------------- #

def _sources(status: dict[str, Any]) -> list[dict[str, dict[str, Any]]]:
    return [
        {item["kind"]: item for item in alert["detail"]["context"]["sources"]}
        for alert in status["alerts"]
    ]


def test_the_simulated_readings_reach_the_alert_context_and_an_inferred_one_does_not(
    client: TestClient,
) -> None:
    client.post("/api/simulate", params={"scenario": "dehydration", "days": 20, "crew_size": 1})
    status = client.get("/api/status").json()
    assert status["alerts"], "el escenario tiene que alertar para que la prueba diga algo"
    for alert, sources in zip(status["alerts"], _sources(status), strict=True):
        context = alert["detail"]["context"]
        assert sources["fluid_intake"]["status"] == WITH_DATA
        assert sources["sleep"]["status"] == WITH_DATA
        start = dt.datetime.fromisoformat(context["window_start"])
        end = dt.datetime.fromisoformat(context["window_end"])
        listed = [item for item in context["items"] if item["kind"] in KINDS]
        assert listed and all(item["label"] == LABEL for item in listed)
        for item in listed:
            assert start <= dt.datetime.fromisoformat(item["start"])
            assert dt.datetime.fromisoformat(item["end"]) <= end
            assert item["source"] == "lecturas de simulator:dehydration"

    # Una lectura INFERIDA de la ingesta dentro de la ventana entra en el registro, pero el
    # estado no la analiza (`routes.decides`), y estas fuentes tampoco la listan.
    anchor = dt.datetime.fromisoformat(status["alerts"][0]["detail"]["context"]["anchor"])
    posted = client.post("/api/observations", json={
        "key": FLUID, "value": 900.0, "source": "model", "subject": "crew-01",
        "effective": (anchor - dt.timedelta(hours=1)).isoformat(),
        "observation_type": "inferred", "model_version": "demo@1",
    })
    assert posted.status_code == 201, posted.text
    again = client.get("/api/status").json()
    before = [sources["fluid_intake"] for sources in _sources(status)]
    after = [sources["fluid_intake"] for sources in _sources(again)]
    assert after == before
    assert all(
        "model" not in item["source"]
        for alert in again["alerts"] for item in alert["detail"]["context"]["items"]
        if item["kind"] == "fluid_intake"
    )


def _verdict(status: dict[str, Any]) -> dict[str, Any]:
    """Todo lo que el estado decide: niveles, puntuaciones, motivos, alertas, consejo y banda."""
    return {
        "overall": status["overall_level"],
        "summary": status["summary"],
        "rules_version": status["rules_version"],
        "domains": {
            key: (value["score"], value["level"], value["drivers"])
            for key, value in status["domains"].items()
        },
        "alerts": [
            (alert["id"], alert["level"], alert["annunciation"], alert["acknowledged"],
             alert["detail"]["onset"], alert["time_to_action"], alert["detail"]["concordance"])
            for alert in status["alerts"]
        ],
        "recommendations": [
            (item["domain"], item["action"]) for item in status["recommendations"]
        ],
        "predictions": status["predictions"],
        "inferred": status["inferred"],
    }


@pytest.mark.parametrize(
    "scenario", ["dehydration", "progressive-insomnia", "cardiovascular-deconditioning"]
)
def test_the_verdict_is_identical_with_and_without_these_sources(
    scenario: str, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.post("/api/simulate", params={"scenario": scenario, "days": 30, "crew_size": 1})
    full = client.get("/api/status").json()
    assert full["alerts"], "el escenario tiene que alertar para que la prueba diga algo"
    for sources in _sources(full):
        assert set(KINDS) <= set(sources)
        assert sources["sleep"]["status"] == WITH_DATA

    # Sin las fuentes: el contexto como se servía antes, y el veredicto igual, cifra a cifra.
    monkeypatch.setattr(alert_context, "RECORDED_SOURCES", ())
    bare = client.get("/api/status").json()
    for sources in _sources(bare):
        assert not set(KINDS) & set(sources)
    assert all(
        item["kind"] not in KINDS
        for alert in bare["alerts"] for item in alert["detail"]["context"]["items"]
    )
    assert _verdict(bare) == _verdict(full)
