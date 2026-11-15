"""El flujo de una hipótesis a la vista, el contraste de sensor y la luz (especificación §3, §7).

Tres cosas que la especificación pide y faltaban, y lo que NO pueden hacer:

- Los siete pasos del flujo (§7) con su estado, redactados por el backend: la interfaz los
  pinta sin deducir nada. No deciden nada.
- Un contraste de sensor, como dato de la biblioteca, para cada parámetro evaluado. Los que no
  son el CO2 van `demo` y sin protocolo: no hay ninguno leído. Y donde EMMA solo tiene la cita
  del límite, lo dice en vez de callar o de inventar un efecto sobre la salud.
- La luz de cabina (§3, «noise/light»): se firma y se muestra, dice «sin límite general» y
  no se evalúa nunca. Con ningún valor da una excursión, y con ella o sin ella el motor decide
  lo mismo (invariante 5).
"""

import datetime as dt
import math
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.advisor import countermeasures
from app.analysis import context
from app.analysis.context import (
    AWAITING_HUMAN,
    DONE,
    IN_PROGRESS,
    LIMIT_ONLY,
    NOT_APPLICABLE,
    STEP_KEYS,
    STEP_STATE_DISPLAY,
    STEPS,
    annotate,
    correlate,
    flow,
)
from app.api.routes import get_store, new_store, reset_store
from app.core import versioning
from app.core.display import unit
from app.environment import habitat
from app.environment.habitat import (
    DEFAULT_MODULE,
    DISPLAY_ONLY,
    PARAMETERS,
    Excursion,
    HabitatParameter,
    HabitatReading,
    Limit,
    excursions,
    parameter,
)
from app.ingest import habitat_simulator
from app.ingest.habitat_simulator import HabitatSimulator
from app.text_guard import check

T0 = dt.datetime(2026, 12, 1, 0, 0, tzinfo=dt.UTC)
WINDOW = dt.timedelta(hours=48)
LIGHT = "cabin-light"


def _light(values: list[float]) -> list[HabitatReading]:
    return [
        HabitatReading(DEFAULT_MODULE, LIGHT, value, T0 + dt.timedelta(minutes=15 * index),
                       "simulator:habitat")
        for index, value in enumerate(values)
    ]


def _excursion(key: str, worst: float, requirement: str) -> Excursion:
    return Excursion(
        DEFAULT_MODULE, key, "health", requirement, T0 - dt.timedelta(hours=6), T0, worst
    )


# --------------------------------------------------------------------------- #
# La luz: se muestra, no se evalúa
# --------------------------------------------------------------------------- #

def test_light_is_declared_display_only_with_no_limit_and_says_so() -> None:
    # La luz y, desde el 2026-10-22, el agua y la microbiología (`test_habitat_water.py`).
    assert LIGHT in DISPLAY_ONLY
    assert not set(DISPLAY_ONLY) & set(PARAMETERS)
    spec = parameter(LIGHT)
    assert spec.limits == ()
    assert spec.limit_note is not None and "sin límite general" in spec.limit_note.lower()
    # Código propio con su porqué (invariante 1) y sin norma que citar: no hay fuente leída.
    assert spec.system == "https://emma.mission/codes" and spec.not_loinc_reason
    published = spec.to_dict()
    assert published["limits"] == [] and published["source"] is None
    assert published["limit_note"] == spec.limit_note
    assert unit(spec.unit) == "lx"
    # Los evaluados no llevan la nota y siguen citando su norma.
    for evaluated in PARAMETERS.values():
        assert evaluated.limit_note is None and evaluated.to_dict()["source"] is not None


@pytest.mark.parametrize("value", [0.0, 0.001, 1.0, 300.0, 5_000.0, 100_000.0, 1_000_000.0])
def test_light_cannot_produce_an_excursion_with_any_value(value: float) -> None:
    assert excursions(_light([value] * 12)) == []
    # Ni alternando extremos, que es lo que haría saltar una media o un techo.
    assert excursions(_light([0.0, value, 1_000_000.0, value] * 6)) == []


def test_a_display_only_parameter_is_not_judged_even_if_its_entry_carried_a_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # La defensa no es que la ficha esté vacía, es que lo de solo mostrar no se juzga.
    with_limit = HabitatParameter(
        key=LIGHT, display="Iluminación", unit="lx", physical_min=0.0, physical_max=1e6,
        limits=(Limit(None, 1.0, "[V2 0000]", "health"),),
    )
    monkeypatch.setitem(habitat.DISPLAY_ONLY, LIGHT, with_limit)
    assert excursions(_light([300.0] * 12)) == []


def test_an_impossible_light_reading_is_still_a_sensor_fault() -> None:
    for value in (-1.0, 2_000_000.0, math.nan):
        with pytest.raises(ValueError):
            _light([value])


def test_light_is_not_a_limit_in_the_rules_fingerprint() -> None:
    assert LIGHT not in versioning.rules()["habitat"]
    assert set(versioning.rules()["habitat"]) == set(PARAMETERS)


def test_the_simulated_light_leaves_every_other_series_as_it_was(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run() -> list[HabitatReading]:
        simulator = HabitatSimulator(co2_excursion=True, extra_modules=("laboratorio",))
        return list(simulator.generate(days=6))

    with_light = run()
    lights = [item for item in with_light if item.parameter == LIGHT]
    assert lights and {item.evidence.value for item in lights} == {"simulated"}
    assert "sin fuente" in HabitatSimulator(False).describe()["display_only"][LIGHT]  # type: ignore[index]

    monkeypatch.delitem(habitat_simulator.NOMINAL, LIGHT)
    without = run()
    assert not [item for item in without if item.parameter == LIGHT]
    assert [item for item in with_light if item.parameter != LIGHT] == without
    assert excursions(with_light) == excursions(without) != []


# --------------------------------------------------------------------------- #
# El contraste de sensor y «solo está la cita del límite»
# --------------------------------------------------------------------------- #

def test_every_evaluated_parameter_has_a_sensor_crosscheck_and_the_new_ones_are_demo() -> None:
    for key in PARAMETERS:
        checks = [
            item for item in countermeasures.for_habitat(key) if "sensor-crosscheck" in item.id
        ]
        assert len(checks) == 1, key
        [item] = checks
        assert item.followup_checks == (key,) and item.scope == "habitat"
        assert "segundo sensor" in item.action
        if key == "cabin-ppco2":
            continue
        # Sin protocolo leído: demo, sin cita, sin cifra de tiempo, y la ventana dice su base.
        assert item.basis == "demo" and item.protocol_ref is None
        assert item.crew_time_minutes is None and item.crew_time_basis == "sin fuente"
        assert "diseño EMMA" in item.followup_basis
        assert not check(item.action) and not check(item.indication)
    assert countermeasures.for_habitat(LIGHT) == []


def test_a_parameter_with_only_its_limit_says_that_is_all_there_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Desde el 2026-10-13 el ruido lleva lo que la norma escribe junto a su límite
    # (`tests/test_habitat_sources.py`). Aquí se le quita para probar el caso que sigue
    # existiendo: un parámetro del que solo está la cita del límite.
    monkeypatch.delitem(context._STANDARD_KNOWLEDGE, "cabin-noise")
    crew = {"crew-01": "watch", "crew-02": "concern"}
    found = [
        _excursion("cabin-noise", 91.0, "[V2 6077]"),
        _excursion("cabin-ppco2", 5.0, "[V2 6004]"),
    ]
    by_parameter = {
        item["excursion"]["parameter"]: item
        for item in correlate(crew, found, T0, WINDOW)["hypotheses"]
    }
    noise, co2 = by_parameter["cabin-noise"], by_parameter["cabin-ppco2"]
    annotate(noise)
    annotate(co2)

    assert noise["what_is_known"] is None and noise["knowledge_note"] == LIMIT_ONLY
    assert [item["relevance"] for item in noise["evidence"]] == ["NASA-STD-3001 Vol 2 [V2 6077]"]
    assert [item["id"] for item in noise["countermeasures"]] == ["hab-noise-sensor-crosscheck"]
    assert noise["flow"][3]["detail"] == LIMIT_ONLY
    assert not check(LIMIT_ONLY)
    # El CO2 sí tiene fuentes leídas: no se le pone la nota.
    assert co2["what_is_known"] and co2["knowledge_note"] is None
    assert "fuentes citadas" in co2["flow"][3]["detail"]


# --------------------------------------------------------------------------- #
# Los siete pasos con su estado
# --------------------------------------------------------------------------- #

def _states(hypothesis: dict[str, Any]) -> list[str]:
    return [step["state"] for step in flow(hypothesis)]


def _shared() -> dict[str, Any]:
    crew = {"crew-01": "watch", "crew-02": "concern", "crew-03": "nominal"}
    [item] = correlate(crew, [_excursion("cabin-ppco2", 5.0, "[V2 6004]")], T0, WINDOW)[
        "hypotheses"
    ]
    return item


def test_the_flow_has_the_seven_steps_of_the_specification_in_order() -> None:
    steps = flow(_shared())
    assert [step["name"] for step in steps] == list(STEPS)
    assert [step["key"] for step in steps] == list(STEP_KEYS)
    assert len(steps) == 7
    for step in steps:
        assert step["state_display"] == STEP_STATE_DISPLAY[step["state"]]
        assert step["detail"].strip()


def test_an_unreviewed_environment_hypothesis_waits_for_a_person() -> None:
    hypothesis = _shared()
    assert _states(hypothesis) == [DONE] * 5 + [AWAITING_HUMAN, NOT_APPLICABLE]
    steps = flow(hypothesis)
    assert "2 tripulantes fuera de nominal: crew-01 y crew-02" in steps[0]["detail"]
    assert "[V2 6004]" in steps[1]["detail"]
    assert "correlación, no causa" in steps[2]["detail"]
    assert "EMMA no registra si se han hecho" in steps[4]["detail"]
    # Sin `review` la hipótesis se lee igual que con `review: None`.
    assert flow({**hypothesis, "review": None}) == steps


def test_a_confirmed_hypothesis_is_followed_until_cabin_and_crew_recover() -> None:
    review = {"decision": "confirmed", "reason": "x", "decided_by": "CDR", "ledger_index": 7}
    still = {**review, "recovery": {"habitat_within_limit": False, "still_affected": ["crew-01"]}}
    steps = flow({**_shared(), "review": still})
    assert [step["state"] for step in steps[5:]] == [DONE, IN_PROGRESS]
    assert "Confirmada por CDR (asiento 7" in steps[5]["detail"]
    assert "sigue fuera de su límite" in steps[6]["detail"] and "crew-01" in steps[6]["detail"]

    # Con el parámetro dentro de límite pero alguien todavía fuera de nominal, sigue abierto.
    half = {**review, "recovery": {"habitat_within_limit": True, "still_affected": ["crew-02"]}}
    assert _states({**_shared(), "review": half})[6] == IN_PROGRESS
    # Y al revés: todos de vuelta en nominal con el parámetro todavía fuera de su límite.
    cabin = {**review, "recovery": {"habitat_within_limit": False, "still_affected": []}}
    assert _states({**_shared(), "review": cabin})[6] == IN_PROGRESS

    back = {**review, "recovery": {"habitat_within_limit": True, "still_affected": []}}
    recovered = flow({**_shared(), "review": back})[6]
    assert recovered["state"] == DONE
    assert "ha vuelto a su límite" in recovered["detail"]
    assert "ningún afectado sigue fuera de nominal" in recovered["detail"]


def test_a_discarded_hypothesis_is_decided_and_not_followed() -> None:
    review = {"decision": "discarded", "reason": "x", "decided_by": "CMO", "ledger_index": 9}
    steps = flow({**_shared(), "review": review})
    assert [step["state"] for step in steps[5:]] == [DONE, NOT_APPLICABLE]
    assert "Descartada por CMO" in steps[5]["detail"]
    assert "descartada" in steps[6]["detail"].lower()


def test_a_hypothesis_without_an_excursion_has_nothing_to_cite_or_confirm() -> None:
    [alone] = correlate({"crew-01": "watch"}, [], T0, WINDOW)["hypotheses"]
    [unknown] = correlate({"crew-01": "watch", "crew-02": "watch"}, [], T0, WINDOW)["hypotheses"]
    expected = [DONE, DONE, DONE, NOT_APPLICABLE, DONE, NOT_APPLICABLE, NOT_APPLICABLE]
    assert _states(alone) == _states(unknown) == expected
    assert flow(alone)[0]["detail"] == "1 tripulante fuera de nominal: crew-01."
    assert "Un solo tripulante" in flow(alone)[1]["detail"]
    assert "Ninguna excursión" in flow(unknown)[1]["detail"]
    annotate(alone)
    assert alone["knowledge_note"] is None


def test_every_text_of_the_flow_passes_the_guard() -> None:
    confirmed = {"decision": "confirmed", "reason": "x", "decided_by": "CDR", "ledger_index": 1}
    cases = [
        _shared(),
        {**_shared(), "review": {**confirmed, "decision": "discarded"}},
        *(
            {**_shared(), "review": {**confirmed, "recovery": {
                "habitat_within_limit": within, "still_affected": still}}}
            for within in (True, False) for still in (["crew-01"], [])
        ),
        *correlate({"crew-01": "watch"}, [], T0, WINDOW)["hypotheses"],
        *correlate({"crew-01": "watch", "crew-02": "watch"}, [], T0, WINDOW)["hypotheses"],
        *correlate(
            {"crew-01": "watch", "crew-02": "watch"},
            [_excursion("cabin-ppo2", 120.0, "[V2 6003]")], T0, WINDOW,
        )["hypotheses"],
    ]
    texts = {
        text for case in cases for step in flow(case)
        for text in (step["name"], step["state_display"], step["detail"])
    } | {habitat.NO_VERIFIED_LIMIT, habitat_simulator.LIGHT_EVIDENCE}
    assert [(text, check(text)) for text in sorted(texts) if check(text)] == []


def test_the_flow_only_reads_the_hypothesis() -> None:
    hypothesis = _shared()
    before = repr(hypothesis)
    flow(hypothesis)
    assert repr(hypothesis) == before


# --------------------------------------------------------------------------- #
# API: lo nuevo se ve y el motor decide lo mismo
# --------------------------------------------------------------------------- #

CO2_SCENARIO = {"scenario": "co2-fatigue", "days": 10}


def _what_the_engine_decided(client: TestClient) -> dict[str, Any]:
    """Niveles, alertas y excursiones: lo que la invariante 5 prohíbe mover."""
    crew = client.get("/api/crew").json()
    cabin = client.get("/api/habitat").json()
    decided: dict[str, Any] = {
        "crew": crew["crew"],
        "correlation": crew["correlation"],
        "excursions": cabin["excursions"],
        "active": cabin["active"],
    }
    for member in crew["crew"]:
        status = client.get("/api/status", params={"subject": member["subject"]}).json()
        decided[member["subject"]] = {
            key: status[key]
            for key in (
                "overall_level", "summary", "domains", "alerts", "recommendations",
                "rules_version", "predictions",
            )
        }
    return decided


def test_the_engine_decides_the_same_with_and_without_the_light_reading(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.post("/api/simulate", params=CO2_SCENARIO)
    with_light = _what_the_engine_decided(client)
    assert any(item["parameter"] == LIGHT for item in client.get("/api/habitat").json()["latest"])
    assert with_light["active"] and any(
        status["alerts"] for key, status in with_light.items() if key.startswith("crew-")
    )

    reset_store(new_store())
    monkeypatch.delitem(habitat_simulator.NOMINAL, LIGHT)
    client.post("/api/simulate", params=CO2_SCENARIO)
    assert all(item["parameter"] != LIGHT for item in client.get("/api/habitat").json()["latest"])
    assert _what_the_engine_decided(client) == with_light


def test_the_crew_view_shows_the_flow_the_light_and_the_crosscheck(client: TestClient) -> None:
    client.post("/api/simulate", params=CO2_SCENARIO)

    published = client.get("/api/habitat/parameters").json()
    assert {item["key"] for item in published["parameters"]} == set(PARAMETERS)
    # La luz va la primera; detrás, el agua y la microbiología (`test_habitat_water.py`).
    light = published["display_only"][0]
    assert light["key"] == LIGHT and light["unit"] == "lx" and light["limits"] == []
    assert "sin límite general" in light["limit_note"].lower()

    before = client.get("/api/crew").json()
    [first] = before["correlation"]["hypotheses"]
    assert first["excursion"]["parameter"] == "cabin-ppco2" and first["knowledge_note"] is None
    assert [step["name"] for step in first["flow"]] == list(STEPS)
    assert [step["state"] for step in first["flow"]] == [DONE] * 5 + [
        AWAITING_HUMAN, NOT_APPLICABLE
    ]
    levels = {item["subject"]: item["overall_level"] for item in before["crew"]}

    # Una luz cualquiera, por la misma vía firmada que las demás lecturas: se ve y no mueve nada.
    reference = before["reference_time"]
    last = dt.datetime.fromisoformat(client.get("/api/habitat").json()["reference_time"])
    dark = client.post("/api/habitat", json={
        "parameter": LIGHT, "value": 0.0,
        "effective": (last + dt.timedelta(minutes=1)).isoformat(),
    })
    assert dark.status_code == 201
    cabin = client.get("/api/habitat").json()
    assert [item["value"] for item in cabin["latest"] if item["parameter"] == LIGHT] == [0.0]
    assert all(item["parameter"] != LIGHT for item in cabin["excursions"])
    assert client.get("/api/crew").json()["correlation"]["hypotheses"] == [first]

    # Una excursión de otro parámetro ofrece su contraste de sensor y dice que solo hay límite.
    assert client.post("/api/habitat", json={
        "parameter": "cabin-ppo2", "value": 120.0, "effective": reference,
    }).status_code == 201
    hypotheses = client.get("/api/crew").json()["correlation"]["hypotheses"]
    [oxygen] = [item for item in hypotheses if item["excursion"]["parameter"] == "cabin-ppo2"]
    assert [item["id"] for item in oxygen["countermeasures"]] == ["hab-o2-sensor-crosscheck"]
    assert oxygen["countermeasures"][0]["basis"] == "demo"
    # Y desde el 2026-10-13, lo que la norma escribe junto a ese límite, con su cita.
    assert "[V2 6003]" in oxygen["what_is_known"] and oxygen["knowledge_note"] is None

    # Una persona confirma: el paso deja de esperar y la recuperación pasa a seguirse.
    assert client.post("/api/crew/hypotheses/review", json={
        "decision": "confirmed", "parameter": "cabin-ppco2",
        "excursion_start": first["excursion"]["start"], "decided_by": "CDR",
        "reason": "el segundo sensor coincide",
    }).status_code == 201
    after = client.get("/api/crew").json()
    [reviewed] = [
        item for item in after["correlation"]["hypotheses"]
        if item["excursion"]["parameter"] == "cabin-ppco2"
    ]
    assert [step["state"] for step in reviewed["flow"][5:]] == [DONE, IN_PROGRESS]
    assert {item["subject"]: item["overall_level"] for item in after["crew"]} == levels
    assert get_store().verify_integrity().ok
