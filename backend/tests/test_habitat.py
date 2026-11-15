"""Hábitat y correlación entre tripulantes (especificación del equipo §3, §7, §9).

El hábitat es parte del sistema sanitario: un cambio simultáneo en varios tripulantes con el
CO2 de cabina fuera de límite apunta primero al hábitat. Estas pruebas fijan los límites
normativos (con su requisito), la media de una hora del CO2, la regla de correlación y que
todo lo que se dice es hipótesis.
"""

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.advisor import countermeasures
from app.analysis.context import (
    ASSUMPTION,
    ASSUMPTION_LOCATED,
    CHECK_LOCATION,
    LABEL,
    NOT_COMPARABLE,
    UNIDENTIFIED_LOCATED,
    Stay,
    correlate,
)
from app.api.routes import get_store, identity_for
from app.core.storage import TamperedRecordError
from app.environment.habitat import (
    DEFAULT_MODULE,
    MODULES,
    MODULES_BASIS,
    MODULES_PATH,
    PARAMETERS,
    Excursion,
    HabitatReading,
    Limit,
    excursions,
    load_modules,
    parameter,
)
from app.ingest.habitat_simulator import HabitatSimulator
from app.text_guard import check

T0 = dt.datetime(2026, 12, 1, 0, 0, tzinfo=dt.UTC)


def _co2(values: list[float], step_minutes: int = 15) -> list[HabitatReading]:
    return [
        HabitatReading("m1", "cabin-ppco2", value, T0 + dt.timedelta(minutes=step_minutes * i),
                       "simulator:habitat")
        for i, value in enumerate(values)
    ]


def test_every_limit_names_its_requirement_and_every_code_says_why_not_loinc() -> None:
    for spec in PARAMETERS.values():
        assert spec.system == "https://emma.mission/codes"
        assert spec.not_loinc_reason
        assert spec.limits
        for limit in spec.limits:
            # Un requisito de NASA-STD-3001 Vol 2 o un SMAC de JSC 20584.
            assert limit.requirement.startswith(("[V2 ", "SMAC ")), limit
            assert limit.kind in {"health", "performance", "target"}


def test_the_co2_limit_is_three_mmhg_averaged_over_one_hour() -> None:
    spec = parameter("cabin-ppco2")
    assert spec.limits[0].high == 3.0
    assert spec.averaging == dt.timedelta(hours=1)


def test_a_brief_co2_spike_is_not_an_excursion_but_a_sustained_one_is() -> None:
    # Un pico de 15 min a 6 mmHg entre lecturas de 2: la media de una hora no pasa de 3.
    assert excursions(_co2([2.0, 2.0, 2.0, 6.0, 2.0, 2.0, 2.0])) == []
    found = excursions(_co2([2.0, 4.0, 4.0, 4.0, 4.0, 4.0]))
    assert [(item.parameter, item.kind, item.requirement) for item in found] == [
        ("cabin-ppco2", "health", "[V2 6004]")
    ]


def test_outside_the_comfort_zone_is_performance_not_health() -> None:
    warm = [HabitatReading("m1", "cabin-temperature", 26.0, T0, "sensor")]
    [item] = excursions(warm)
    assert (item.kind, item.requirement) == ("performance", "[V2 6013]")


def test_an_impossible_reading_is_a_sensor_fault() -> None:
    with pytest.raises(ValueError, match="físicamente posible"):
        HabitatReading("m1", "cabin-humidity", 140.0, T0, "sensor")
    with pytest.raises(ValueError, match="zona horaria"):
        HabitatReading("m1", "cabin-humidity", 40.0, T0.replace(tzinfo=None), "sensor")


def test_a_reading_survives_its_payload() -> None:
    reading = HabitatReading("m1", "cabin-ppco2", 2.4, T0, "simulator:habitat")
    back = HabitatReading.from_payload(reading.to_payload())
    assert back == reading
    assert back.evidence.value == "simulated"


def test_the_nominal_simulation_stays_within_the_standard() -> None:
    readings = list(HabitatSimulator(co2_excursion=False).generate(days=10))
    assert [item for item in excursions(readings) if item.kind == "health"] == []


def test_the_co2_scenario_crosses_the_limit_only_at_the_end() -> None:
    readings = list(HabitatSimulator(co2_excursion=True).generate(days=10))
    [item] = [item for item in excursions(readings) if item.kind == "health"]
    assert item.parameter == "cabin-ppco2"
    assert item.start >= T0.replace(day=1, month=11) + dt.timedelta(days=7)


# --------------------------------------------------------------------------- #
# Correlación
# --------------------------------------------------------------------------- #

WINDOW = dt.timedelta(days=2)


def _co2_excursion(end: dt.datetime) -> list:
    readings = [
        HabitatReading("m1", "cabin-ppco2", 5.0, end - dt.timedelta(hours=h), "sensor")
        for h in range(10, -1, -1)
    ]
    return excursions(readings)


def test_several_crew_and_a_co2_excursion_put_the_shared_environment_first() -> None:
    result = correlate(
        {"crew-01": "concern", "crew-02": "watch", "crew-03": "nominal"},
        _co2_excursion(T0), T0, WINDOW,
    )
    first = result["hypotheses"][0]
    assert first["kind"] == "shared_environment"
    assert first["affected"] == ["crew-01", "crew-02"]
    assert first["label"] == LABEL
    assert "Law" in first["what_is_known"] and "contestado" in first["what_is_known"]
    assert result["assumption"] == ASSUMPTION


def test_one_crew_member_is_individual_even_with_an_excursion() -> None:
    result = correlate({"crew-01": "concern", "crew-02": "nominal"}, _co2_excursion(T0), T0, WINDOW)
    assert [item["kind"] for item in result["hypotheses"]] == ["individual"]


def test_several_crew_without_excursion_is_an_unidentified_common_cause() -> None:
    result = correlate({"crew-01": "watch", "crew-02": "watch"}, [], T0, WINDOW)
    assert [item["kind"] for item in result["hypotheses"]] == ["shared_unknown"]


def test_an_old_excursion_does_not_explain_a_new_change() -> None:
    old = _co2_excursion(T0 - dt.timedelta(days=5))
    result = correlate({"crew-01": "watch", "crew-02": "watch"}, old, T0, WINDOW)
    assert [item["kind"] for item in result["hypotheses"]] == ["shared_unknown"]


def test_a_comfort_excursion_is_not_a_cause() -> None:
    warm = excursions([HabitatReading("m1", "cabin-temperature", 26.0, T0, "sensor")])
    result = correlate({"crew-01": "watch", "crew-02": "watch"}, warm, T0, WINDOW)
    assert [item["kind"] for item in result["hypotheses"]] == ["shared_unknown"]


def test_every_fixed_text_of_the_correlation_passes_the_guard() -> None:
    result = correlate(
        {"crew-01": "concern", "crew-02": "watch"}, _co2_excursion(T0), T0, WINDOW
    )
    none_found = correlate({"crew-01": "watch", "crew-02": "watch"}, [], T0, WINDOW)
    texts = [ASSUMPTION]
    for item in [*result["hypotheses"], *none_found["hypotheses"]]:
        texts += [item["title"], *(item["checks"]), item["what_is_known"] or ""]
    assert [(t, check(t)) for t in texts if t and check(t)] == []


# --------------------------------------------------------------------------- #
# API: el hábitat por el ledger y la vista de tripulación
# --------------------------------------------------------------------------- #

def test_co2_scenario_puts_the_whole_crew_under_the_shared_habitat(client: TestClient) -> None:
    body = client.post("/api/simulate", params={"scenario": "co2-fatigue", "days": 40}).json()
    assert body["simulation"]["crew"] == ["crew-01", "crew-02", "crew-03", "crew-04"]
    assert body["habitat_recorded"] > 0

    crew = client.get("/api/crew").json()
    first = crew["correlation"]["hypotheses"][0]
    assert first["kind"] == "shared_environment"
    assert first["excursion"]["parameter"] == "cabin-ppco2"
    assert len(first["affected"]) >= 2

    habitat = client.get("/api/habitat").json()
    assert [item["requirement"] for item in habitat["active"]] == ["[V2 6004]"]
    assert get_store().verify_integrity().ok


def test_an_individual_scenario_with_a_crew_is_not_blamed_on_the_habitat(
    client: TestClient,
) -> None:
    client.post(
        "/api/simulate", params={"scenario": "progressive-insomnia", "days": 40, "crew_size": 4}
    )
    crew = client.get("/api/crew").json()
    kinds = [item["kind"] for item in crew["correlation"]["hypotheses"]]
    assert "shared_environment" not in kinds
    assert client.get("/api/habitat").json()["active"] == []


def test_a_real_habitat_reading_goes_through_the_ledger_and_blocks_a_scenario_swap(
    client: TestClient,
) -> None:
    client.post("/api/simulate", params={"days": 5})
    response = client.post(
        "/api/habitat", json={"parameter": "cabin-ppco2", "value": 2.1}
    )
    assert response.status_code == 201
    entry = get_store().ledger.entries[response.json()["ledger_index"]]
    assert entry.entry_type == "habitat-reading"
    assert entry.signer == "habitat-telemetry"
    swap = client.post("/api/simulate", params={"days": 5, "replace": True})
    assert swap.status_code == 409


def test_an_impossible_or_unknown_habitat_reading_is_refused(client: TestClient) -> None:
    assert client.post(
        "/api/habitat", json={"parameter": "cabin-humidity", "value": 140}
    ).status_code == 422
    assert client.post(
        "/api/habitat", json={"parameter": "cabin-radon", "value": 1}
    ).status_code == 422
    assert client.post(
        "/api/habitat", json={"parameter": "cabin-ppco2", "value": 2, "source": "simulator"}
    ).status_code == 422


def test_the_parameters_are_published_with_their_requirement(client: TestClient) -> None:
    body = client.get("/api/habitat/parameters").json()
    assert {item["key"] for item in body["parameters"]} == set(PARAMETERS)


# --------------------------------------------------------------------------- #
# Ruido y contaminantes (OCHMO-TB-035 y SMAC de JSC 20584 Rev C)
# --------------------------------------------------------------------------- #


def _series(key: str, values: list[float], step: dt.timedelta) -> list[HabitatReading]:
    return [
        HabitatReading("m1", key, value, T0 + step * i, "sensor")
        for i, value in enumerate(values)
    ]


def test_noise_above_85_dba_breaks_v2_6077() -> None:
    [item] = excursions(_series("cabin-noise", [60.0, 90.0, 60.0], dt.timedelta(minutes=10)))
    assert (item.requirement, item.kind) == ("[V2 6077]", "health")


def test_co_is_judged_against_each_exposure_time_with_its_own_average() -> None:
    # 120 ppm sostenidos 30 h: por debajo del SMAC de 1 h (425) pero por encima del de 24 h (100).
    found = excursions(_series("cabin-co", [120.0] * 31, dt.timedelta(hours=1)))
    requirements = {item.requirement for item in found}
    assert "SMAC 24 h" in requirements
    assert "SMAC 1 h" not in requirements


def test_a_brief_co_spike_does_not_break_the_24_hour_smac() -> None:
    values = [1.0] * 24 + [300.0] + [1.0] * 24
    found = excursions(_series("cabin-co", values, dt.timedelta(hours=1)))
    assert "SMAC 24 h" not in {item.requirement for item in found}


def test_formaldehyde_is_a_ceiling_not_an_average() -> None:
    [item] = excursions(_series("cabin-formaldehyde", [0.02, 0.15, 0.02], dt.timedelta(hours=1)))
    assert item.requirement.startswith("SMAC techo")


def test_the_nominal_cabin_stays_under_every_new_limit() -> None:
    readings = list(HabitatSimulator(co2_excursion=False).generate(days=35))
    assert [item for item in excursions(readings) if item.kind == "health"] == []


# --------------------------------------------------------------------------- #
# Clases de límite conformes a la norma (NASA-STD-3001 Vol 2 Rev F, releída el 2026-10-14)
# --------------------------------------------------------------------------- #


def _found(readings: list[HabitatReading]) -> set[tuple[str, str, str]]:
    return {(item.parameter, item.kind, item.requirement) for item in excursions(readings)}


def test_145_to_155_mmhg_of_o2_is_a_target_range_not_a_health_limit() -> None:
    limits = {item.requirement: item for item in parameter("cabin-ppo2").limits}
    target = limits["[V2 6003] rango objetivo"]
    assert (target.low, target.high, target.kind) == (145.0, 155.0, "target")
    # Los de salud son los de exposición de la tabla 6.2-1: 127 en media de 1 h, 122 absoluto
    # y 356 de hiperoxia indefinida.
    health = {
        (item.low, item.high, item.averaging) for item in limits.values() if item.kind == "health"
    }
    assert health == {
        (127.0, None, dt.timedelta(hours=1)), (122.0, None, None), (None, 356.0, None)}
    # 140 mmHg sostenidos: fuera del objetivo (aviso), dentro de la salud.
    assert _found(_series("cabin-ppo2", [140.0] * 4, dt.timedelta(minutes=15))) == {
        ("cabin-ppo2", "target", "[V2 6003] rango objetivo")}
    # 125 sostenidos: la media de 1 h cae bajo 127; el mínimo absoluto de 122, no.
    assert ("cabin-ppo2", "health", "[V2 6003] hipoxia leve, media 1 h") in _found(
        _series("cabin-ppo2", [125.0] * 4, dt.timedelta(minutes=15)))
    # Un instante a 121 entre lecturas de 150: la media de 1 h no baja de 127, el absoluto sí.
    brief = _found(_series("cabin-ppo2", [150.0, 150.0, 121.0, 150.0], dt.timedelta(minutes=15)))
    assert ("cabin-ppo2", "health", "[V2 6003] mínimo absoluto") in brief
    assert ("cabin-ppo2", "health", "[V2 6003] hipoxia leve, media 1 h") not in brief
    assert ("cabin-ppo2", "health", "[V2 6003] hiperoxia indefinida") in _found(
        _series("cabin-ppo2", [360.0], dt.timedelta(minutes=15)))


def _thermal(temperature: float, humidity: float | None) -> set[tuple[str, str, str]]:
    readings = [HabitatReading("m1", "cabin-temperature", temperature, T0, "sensor")]
    if humidity is not None:
        readings.append(HabitatReading("m1", "cabin-humidity", humidity, T0, "sensor"))
    return {item for item in _found(readings) if item[1] == "health"}


def test_v2_6012_is_one_figure_judged_with_its_four_labelled_vertices() -> None:
    limit = next(
        item for item in parameter("cabin-temperature").limits if item.requirement == "[V2 6012]")
    assert limit.figure is not None and limit.figure.pair == "cabin-humidity"
    assert sorted(map(tuple, limit.figure.vertices())) == sorted(
        [(18.0, 75.0), (25.7, 75.0), (27.0, 25.0), (19.1, 25.0)])
    out = {("cabin-temperature", "health", "[V2 6012]")}
    # Dentro de 18-27 y de 25-75 por separado, pero fuera del cuadrilátero: los lados son
    # inclinados. Con 30 % el lado izquierdo está en ~18,99 °C; con 70 %, el derecho en ~25,83.
    assert _thermal(18.5, 30.0) == out
    assert _thermal(26.5, 70.0) == out
    # Las mismas temperaturas con la humedad del otro extremo están dentro.
    assert _thermal(18.5, 70.0) == set()
    assert _thermal(26.5, 30.0) == set()
    # Sin humedad simultánea, 18,5 °C no es evaluable con una lectura: no se juzga.
    assert _thermal(18.5, None) == set()
    # Fuera de la envolvente 18-27 se está fuera con cualquier humedad: se juzga sin ella.
    assert _thermal(17.5, None) == out and _thermal(27.5, None) == out
    # La humedad se juzga sola: sus lados son los de 25 % y 75 %.
    assert _thermal(22.0, 80.0) == {("cabin-humidity", "health", "[V2 6012]")}


def test_a_humidity_reading_too_far_in_time_is_not_simultaneous() -> None:
    readings = [
        HabitatReading("m1", "cabin-temperature", 18.5, T0, "sensor"),
        HabitatReading("m1", "cabin-humidity", 30.0, T0 + dt.timedelta(minutes=30), "sensor"),
    ]
    assert {item for item in _found(readings) if item[1] == "health"} == set()
    # Ni la de otro módulo.
    readings[1] = HabitatReading("m2", "cabin-humidity", 30.0, T0, "sensor")
    assert {item for item in _found(readings) if item[1] == "health"} == set()


def test_the_85_dba_limit_says_what_the_standard_writes_it_for() -> None:
    [limit] = parameter("cabin-noise").limits
    assert (limit.high, limit.kind) == (85.0, "health")
    label = limit.label or ""
    for said in ("ruido peligroso", "fuera de lo nominal", "ponderación temporal rápida"):
        assert said in label
    assert not check(label)


def test_ammonia_carries_the_30_180_and_1000_day_smacs_of_its_row() -> None:
    limits = {item.requirement: item for item in parameter("cabin-ammonia").limits}
    for name, days in (("SMAC 30 d", 30), ("SMAC 180 d", 180), ("SMAC 1000 d", 1000)):
        assert (limits[name].high, limits[name].averaging) == (3.0, dt.timedelta(days=days))
    # 4 ppm sostenidos 31 días: fuera del de 30 d (y del de 7 d), por debajo del de 24 h.
    found = {item.requirement for item in excursions(
        _series("cabin-ammonia", [4.0] * 32, dt.timedelta(days=1)))}
    assert {"SMAC 7 d", "SMAC 30 d"} <= found and "SMAC 24 h" not in found


def test_every_limit_publishes_its_class_label_and_figure() -> None:
    for spec in PARAMETERS.values():
        for published, limit in zip(spec.to_dict()["limits"], spec.limits, strict=True):
            assert published["kind_display"] in {
                "límite normativo", "zona de confort", "rango objetivo"}
            assert published["label"] == limit.label
            assert (published["figure"] is None) == (limit.figure is None)
            if published["label"] is not None:
                assert not check(published["label"])
    [temperature] = [
        item for item in parameter("cabin-temperature").to_dict()["limits"]
        if item["figure"] is not None]
    assert temperature["figure"]["name"] == "Figura 6.2-2"
    assert temperature["figure"]["pair"] == "cabin-humidity"
    with pytest.raises(ValueError, match="clase de límite"):
        Limit(1.0, 2.0, "[V2 0000]", "comfort")


# --------------------------------------------------------------------------- #
# Ubicación por módulo (especificación §3: HabitatState "module/location", MissionContext
# "location"). La declara una persona, va al ledger, y solo ORDENA hipótesis.
# --------------------------------------------------------------------------- #

GOLDEN = Path(__file__).parent / "data" / "context" / "correlate_sin_ubicacion.json"


def _excursion_in(module: str, key: str, value: float, end: dt.datetime) -> list[Excursion]:
    return excursions([
        HabitatReading(module, key, value, end - dt.timedelta(hours=h), "sensor")
        for h in range(10, -1, -1)
    ])


def _golden_cases() -> dict[str, tuple[dict[str, str], list[Excursion]]]:
    return {
        "varios_con_co2": (
            {"crew-01": "concern", "crew-02": "watch", "crew-03": "nominal"},
            _excursion_in("m1", "cabin-ppco2", 5.0, T0),
        ),
        "uno_con_co2": (
            {"crew-01": "concern", "crew-02": "nominal"},
            _excursion_in("m1", "cabin-ppco2", 5.0, T0),
        ),
        "varios_sin_excursion": ({"crew-01": "watch", "crew-02": "watch"}, []),
        "excursion_antigua": (
            {"crew-01": "watch", "crew-02": "watch"},
            _excursion_in("m1", "cabin-ppco2", 5.0, T0 - dt.timedelta(days=5)),
        ),
        "dos_modulos": (
            {"crew-01": "watch", "crew-02": "critical", "crew-03": "watch"},
            _excursion_in("habitat-principal", "cabin-ppco2", 5.0, T0)
            + _excursion_in("laboratorio", "cabin-noise", 90.0, T0),
        ),
        "nadie_afectado": ({"crew-01": "nominal"}, _excursion_in("m1", "cabin-ppco2", 5.0, T0)),
    }


def _slim(result: dict[str, Any]) -> dict[str, Any]:
    """La salida de `correlate` con las contramedidas reducidas a una marca.

    Las contramedidas de una hipótesis son, tal cual, las de la biblioteca para ese parámetro.
    Eso se comprueba aquí contra la biblioteca de ahora y en el fichero queda la marca: la
    prueba fija lo que `correlate` decide y dice, no el contenido de `countermeasures.json`,
    que tiene sus pruebas y cambia por su cuenta.
    """
    for item in result["hypotheses"]:
        if "countermeasures" in item:
            library = [
                measure.to_dict()
                for measure in countermeasures.for_habitat(item["excursion"]["parameter"])
            ]
            if item["countermeasures"] == library:
                item["countermeasures"] = "las de la biblioteca para ese parámetro"
    return result


def _stay(module: str, start: dt.datetime, end: dt.datetime, order: int = 1) -> Stay:
    return Stay(module, start, end, order)


def test_without_a_declared_location_the_output_is_the_one_from_before_locations() -> None:
    # No regresión. El fichero se generó con `correlate` TAL Y COMO ESTABA antes de que
    # existiera la ubicación (el `context.py` del commit 8471801: `main` justo antes de fusionar
    # la ubicación, ya con el registro único de evidencia), sobre estos mismos casos y con este
    # mismo `_slim`. Sin ubicación, con un mapa vacío, con una ubicación que no toca
    # la ventana o con la de alguien que no es de la tripulación, la salida tiene que ser esa
    # clave por clave: mismas hipótesis, mismo orden, mismo supuesto de hábitat compartido.
    # Si otro cambio altera A PROPÓSITO lo que dice una hipótesis, el fichero se vuelve a
    # generar con la salida de este mismo bucle para `locations=None` y se revisa su diff.
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    old = _stay("laboratorio", T0 - dt.timedelta(days=30), T0 - dt.timedelta(days=20))
    for locations in (None, {}, {"crew-01": [old], "crew-02": [old]}, {"crew-09": [old]}):
        got = {
            name: _slim(correlate(levels, found, T0, WINDOW, locations))
            for name, (levels, found) in _golden_cases().items()
        }
        assert json.loads(json.dumps(got)) == golden
        assert all(item["assumption"] == ASSUMPTION for item in got.values())
    # El fichero no es trivial: tiene los tres tipos de hipótesis y el caso sin ninguna.
    kinds = {h["kind"] for case in golden.values() for h in case["hypotheses"]}
    assert kinds == {"shared_environment", "shared_unknown", "individual"}
    assert golden["nadie_afectado"]["hypotheses"] == []


def test_an_excursion_in_a_module_where_the_crew_was_not_goes_down_and_says_why() -> None:
    levels = {"crew-01": "concern", "crew-02": "watch"}
    found = _excursion_in("habitat-principal", "cabin-ppco2", 5.0, T0)
    away = _stay("laboratorio", T0 - dt.timedelta(days=3), T0 + dt.timedelta(days=1))
    result = correlate(levels, found, T0, WINDOW, {"crew-01": [away], "crew-02": [away]})
    assert [item["kind"] for item in result["hypotheses"]] == [
        "shared_unknown", "shared_environment",
    ]
    # Lo primero que se propone es comprobar la declaración de la que depende el orden.
    assert result["hypotheses"][0]["title"] == UNIDENTIFIED_LOCATED
    assert result["hypotheses"][0]["checks"][0] == CHECK_LOCATION
    last = result["hypotheses"][1]
    assert last["likelihood"] == "less_likely"
    assert "crew-01 y crew-02 no estaban en Hábitat principal" in last["likelihood_reason"]
    assert "la declara una persona" in last["likelihood_reason"]
    assert last["location"]["elsewhere"] == ["crew-01", "crew-02"]
    assert last["label"] == LABEL
    assert result["assumption"] == ASSUMPTION_LOCATED
    assert result["location_declared"] == ["crew-01", "crew-02"]


def test_the_location_only_orders_hypotheses_and_never_moves_a_level() -> None:
    # Invariante 5: ni niveles ni afectados ni excursiones cambian con la ubicación.
    levels = {"crew-01": "concern", "crew-02": "watch", "crew-03": "nominal"}
    found = _excursion_in("habitat-principal", "cabin-ppco2", 5.0, T0)
    away = _stay("laboratorio", T0 - dt.timedelta(days=3), T0 + dt.timedelta(days=1))
    before = correlate(dict(levels), found, T0, WINDOW)
    given = dict(levels)
    after = correlate(given, found, T0, WINDOW, {"crew-01": [away], "crew-02": [away]})
    assert given == levels
    for key in ("affected", "habitat_excursions", "window_hours"):
        assert after[key] == before[key]
    # La hipótesis ambiental sigue ahí, entera: solo ha cambiado de sitio y lleva su motivo.
    [same] = [item for item in after["hypotheses"] if item["kind"] == "shared_environment"]
    added = {"likelihood", "likelihood_reason", "location"}
    assert {k: v for k, v in same.items() if k not in added} == before["hypotheses"][0]


def test_two_crew_the_excursion_could_reach_keep_the_environment_first() -> None:
    levels = {"crew-01": "concern", "crew-02": "watch", "crew-03": "watch"}
    found = _excursion_in("habitat-principal", "cabin-ppco2", 5.0, T0)
    span = (T0 - dt.timedelta(days=3), T0 + dt.timedelta(days=1))
    result = correlate(levels, found, T0, WINDOW, {
        "crew-01": [_stay("habitat-principal", *span)],
        "crew-03": [_stay("laboratorio", *span)],
    })
    first = result["hypotheses"][0]
    assert (first["kind"], first["likelihood"]) == ("shared_environment", "primary")
    assert first["location"]["present"] == ["crew-01"]
    assert first["location"]["undeclared"] == ["crew-02"]
    assert first["location"]["elsewhere"] == ["crew-03"]
    assert first["likelihood_reason"].startswith("No explica el cambio de todos")


def test_a_gap_in_the_declaration_never_clears_the_habitat() -> None:
    # Declarado fuera solo la mitad de la excursión: el resto no se sabe, y no saber no exculpa.
    levels = {"crew-01": "concern", "crew-02": "watch"}
    found = _excursion_in("habitat-principal", "cabin-ppco2", 5.0, T0)
    half = _stay("laboratorio", T0 - dt.timedelta(hours=4), T0 + dt.timedelta(days=1))
    result = correlate(levels, found, T0, WINDOW, {"crew-01": [half], "crew-02": [half]})
    first = result["hypotheses"][0]
    assert (first["kind"], first["likelihood"]) == ("shared_environment", "primary")
    assert first["location"]["undeclared"] == ["crew-01", "crew-02"]
    assert first["likelihood_reason"] is None


def test_a_later_declaration_corrects_an_earlier_one() -> None:
    levels = {"crew-01": "concern", "crew-02": "watch"}
    found = _excursion_in("habitat-principal", "cabin-ppco2", 5.0, T0)
    span = (T0 - dt.timedelta(days=3), T0 + dt.timedelta(days=1))
    wrong, fixed = _stay("laboratorio", *span, order=5), _stay("habitat-principal", *span, order=9)
    away = [_stay("laboratorio", *span)]
    corrected = correlate(levels, found, T0, WINDOW, {"crew-01": [wrong, fixed], "crew-02": away})
    assert corrected["hypotheses"][-1]["location"]["present"] == ["crew-01"]
    # Al revés —la corrección dice que NO estaba—, queda fuera.
    wrong, fixed = _stay("habitat-principal", *span, order=5), _stay("laboratorio", *span, order=9)
    reverted = correlate(levels, found, T0, WINDOW, {"crew-01": [wrong, fixed], "crew-02": away})
    assert reverted["hypotheses"][-1]["location"]["elsewhere"] == ["crew-01", "crew-02"]


def test_a_reading_from_a_module_outside_the_list_places_nobody_elsewhere() -> None:
    # "m1" no está en la lista declarada (una lectura firmada antes de que hubiera lista). No
    # se puede comparar con la ubicación de nadie, y no poder comparar no es estar ausente.
    levels = {"crew-01": "concern", "crew-02": "watch"}
    away = _stay("laboratorio", T0 - dt.timedelta(days=3), T0 + dt.timedelta(days=1))
    result = correlate(
        levels, _excursion_in("m1", "cabin-ppco2", 5.0, T0), T0, WINDOW,
        {"crew-01": [away], "crew-02": [away]},
    )
    first = result["hypotheses"][0]
    assert (first["kind"], first["likelihood"]) == ("shared_environment", "primary")
    assert first["location"]["elsewhere"] == []
    assert first["likelihood_reason"] == NOT_COMPARABLE


def test_only_the_part_of_the_excursion_inside_the_window_is_judged() -> None:
    # La excursión lleva diez días; estuvo en el módulo al principio y fuera toda la ventana.
    # Lo de antes de la ventana no explica un cambio de ahora, como en la regla sin ubicación.
    levels = {"crew-01": "concern", "crew-02": "watch"}
    long = excursions([
        HabitatReading("habitat-principal", "cabin-ppco2", 5.0, T0 - dt.timedelta(hours=h), "s")
        for h in range(240, -1, -6)
    ])
    there = _stay("habitat-principal", T0 - dt.timedelta(days=11), T0 - dt.timedelta(days=4), 1)
    away = _stay("laboratorio", T0 - dt.timedelta(days=4), T0 + dt.timedelta(days=1), 2)
    result = correlate(
        levels, long, T0, WINDOW, {"crew-01": [there, away], "crew-02": [there, away]}
    )
    assert result["hypotheses"][-1]["location"]["elsewhere"] == ["crew-01", "crew-02"]
    # Y con que vuelva al módulo un rato dentro de la ventana, pudo alcanzarle.
    back = _stay("habitat-principal", T0 - dt.timedelta(hours=3), T0 - dt.timedelta(hours=2), 3)
    result = correlate(
        levels, long, T0, WINDOW, {"crew-01": [there, away, back], "crew-02": [there, away]}
    )
    assert result["hypotheses"][-1]["location"]["present"] == ["crew-01"]


def test_the_location_texts_pass_the_guard() -> None:
    levels = {"crew-01": "concern", "crew-02": "watch", "crew-03": "watch"}
    found = _excursion_in("habitat-principal", "cabin-ppco2", 5.0, T0)
    span = (T0 - dt.timedelta(days=3), T0 + dt.timedelta(days=1))
    away = [_stay("laboratorio", *span)]
    texts = [ASSUMPTION_LOCATED, NOT_COMPARABLE]
    for locations in ({"crew-01": away}, {"crew-01": away, "crew-02": away, "crew-03": away}):
        for item in correlate(levels, found, T0, WINDOW, locations)["hypotheses"]:
            texts += [item["title"], *item["checks"], item.get("likelihood_reason") or ""]
    assert {UNIDENTIFIED_LOCATED, CHECK_LOCATION} <= set(texts)
    assert sum("menos probable" in text for text in texts) == 1
    assert sum(text.startswith("No explica el cambio de todos") for text in texts) == 1
    assert [(t, check(t)) for t in texts if t and check(t)] == []


def test_the_module_list_is_declared_design_and_refuses_a_broken_file(tmp_path: Path) -> None:
    assert DEFAULT_MODULE in MODULES and 2 <= len(MODULES) <= 8
    assert "diseño" in MODULES_BASIS and "sin respaldo bibliográfico" in MODULES_BASIS
    raw = json.loads(MODULES_PATH.read_text(encoding="utf-8"))
    broken = tmp_path / "m.json"
    for change in ({"default": "puente"}, {"basis": " "}, {"modules": raw["modules"] * 2}):
        broken.write_text(json.dumps({**raw, **change}), encoding="utf-8")
        with pytest.raises(ValueError):
            load_modules(broken)


def test_extra_modules_are_deterministic_and_leave_the_first_series_as_it_was() -> None:
    alone = list(HabitatSimulator(co2_excursion=True).generate(days=5))
    several = HabitatSimulator(co2_excursion=True, extra_modules=["laboratorio", "camarotes"])
    readings = list(several.generate(days=5))
    assert [item for item in readings if item.module == DEFAULT_MODULE] == alone
    assert readings == list(several.generate(days=5))
    lab = [item.value for item in readings if item.module == "laboratorio"]
    cabins = [item.value for item in readings if item.module == "camarotes"]
    assert lab != cabins
    # La excursión ocurre en un solo módulo; es un supuesto de diseño y lo dice.
    assert {item.module for item in excursions(readings) if item.kind == "health"} == {
        DEFAULT_MODULE
    }
    assert "sin respaldo bibliográfico" in str(several.describe()["modules_basis"])
    with pytest.raises(ValueError, match="dos veces"):
        HabitatSimulator(co2_excursion=False, extra_modules=[DEFAULT_MODULE])


# Diez días bastan para el escenario de CO2: el ppCO2 sube los tres últimos y la tripulación
# entera sale de nominal por la deriva del escenario (PVT, sueño, síntomas). Con 40 la prueba
# dice lo mismo y tarda varias veces más.
CO2_SCENARIO = {"scenario": "co2-fatigue", "days": 10}
MISSION_START = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)


def _declare(client: TestClient, subject: str, module: str, **extra: Any) -> Any:
    return client.post("/api/mission/events", json={
        "subject": subject, "kind": "location", "module": module,
        "start": "2026-11-01T00:00:00+00:00", "end": "2026-12-31T00:00:00+00:00",
        "declared_by": "CDR", **extra,
    })


def _what_the_engine_decided(client: TestClient, subject: str) -> dict[str, Any]:
    """Todo lo que la invariante 5 prohíbe mover, de la tripulación y de un tripulante.

    De `/crew`, cada tripulante entero salvo su ubicación y su estado (`location*`: nivel,
    resumen, dominios, motivos);
    de `/status`, puntuaciones, niveles, alertas con su detalle, recomendaciones y reglas.

    Del detalle de cada alerta se aparta `context`: es la capa descriptiva
    (`analysis/alert_context.py`) y dice a propósito dónde estaba el tripulante durante una
    excursión del hábitat. Es texto sobre lo decidido, no parte de lo decidido; lo que cambia
    en él con la ubicación lo fija `_context_of`, y `tests/test_alert_context.py`.
    """
    crew = client.get("/api/crew").json()["crew"]
    status = client.get("/api/status", params={"subject": subject}).json()
    alerts = [
        {**alert, "detail": {k: v for k, v in alert["detail"].items() if k != "context"}}
        for alert in status["alerts"]
    ]
    return {
        "crew": [
            {k: v for k, v in member.items() if not k.startswith("location")}
            for member in crew
        ],
        "alerts": alerts,
        **{
            key: status[key]
            for key in (
                "overall_level", "summary", "domains", "recommendations", "rules_version",
                "predictions",
            )
        },
    }


def _context_of(client: TestClient, subject: str) -> list[dict[str, Any]]:
    """El contexto de cada alerta de un tripulante, sin lo que la ubicación puede cambiar.

    Con una ubicación declarada solo pueden cambiar tres cosas, y solo en el hábitat: la frase
    y el estado de presencia de cada excursión, y el supuesto que se declara en su nota.
    """
    status = client.get("/api/status", params={"subject": subject}).json()
    contexts = []
    for alert in status["alerts"]:
        context = alert["detail"]["context"]
        contexts.append({
            **context,
            "items": [
                {k: v for k, v in item.items() if k not in ("detail", "presence")}
                if item["kind"] == "habitat" else item
                for item in context["items"]
            ],
            "sources": [
                {k: v for k, v in source.items() if k != "note"}
                if source["kind"] == "habitat" else source
                for source in context["sources"]
            ],
        })
    return contexts


def test_a_declared_location_is_a_signed_ledger_entry_and_reorders_the_hypothesis(
    client: TestClient,
) -> None:
    client.post("/api/simulate", params=CO2_SCENARIO)
    before = client.get("/api/crew").json()
    first = before["correlation"]["hypotheses"][0]
    assert first["kind"] == "shared_environment" and "likelihood" not in first
    assert before["correlation"]["assumption"] == ASSUMPTION
    assert "location_declared" not in before["correlation"]
    assert all(member["location"] is None for member in before["crew"])
    affected = first["affected"]
    assert len(affected) >= 3
    decided_before = _what_the_engine_decided(client, affected[1])
    context_before = _context_of(client, affected[1])
    assert decided_before["overall_level"] != "nominal" and decided_before["alerts"]

    store = get_store()
    size = len(store.ledger)
    indices = []
    for subject in affected[1:]:
        response = _declare(client, subject, "laboratorio")
        assert response.status_code == 201, response.text
        indices.append(response.json()["ledger_index"])
    # Cada declaración es UN asiento encadenado y firmado por la consola, con su módulo: el
    # índice que devuelve la API es el suyo, y no hay nada más escrito.
    assert indices == list(range(size, size + len(affected) - 1))
    assert len(store.ledger) == size + len(affected) - 1
    for index, subject in zip(indices, affected[1:], strict=True):
        entry = store.ledger.entries[index]
        assert (entry.entry_type, entry.signer) == ("mission-event", "crew-console")
        # (`_salt` lo pone el ledger en todo asiento; no es un campo de la declaración.)
        assert {k: v for k, v in entry.payload.items() if k != "_salt"} == {
            "subject": subject, "kind": "location", "module": "laboratorio",
            "start": "2026-11-01T00:00:00+00:00", "end": "2026-12-31T00:00:00+00:00",
            "label": "Laboratorio", "declared_by": "CDR",
        }
    assert store.verify_integrity().ok
    assert client.get("/api/status").json()["data"]["integrity_ok"] is True

    after = client.get("/api/crew").json()
    hypotheses = after["correlation"]["hypotheses"]
    assert [item["kind"] for item in hypotheses] == ["shared_unknown", "shared_environment"]
    assert hypotheses[0]["checks"][0] == CHECK_LOCATION
    assert hypotheses[1]["likelihood"] == "less_likely"
    assert "no estaban en Hábitat principal" in hypotheses[1]["likelihood_reason"]
    assert hypotheses[1]["location"]["elsewhere"] == affected[1:]
    assert hypotheses[1]["location"]["undeclared"] == affected[:1]
    assert hypotheses[1]["excursion"] == first["excursion"]
    assert after["correlation"]["assumption"] == ASSUMPTION_LOCATED
    assert after["correlation"]["location_declared"] == affected[1:]
    located = {member["subject"]: member["location"] for member in after["crew"]}
    assert located[affected[0]] is None
    assert located[affected[1]]["module"] == "laboratorio"
    assert located[affected[1]]["display"] == "Laboratorio"
    assert located[affected[1]]["ledger_index"] == indices[0]
    # Invariante 5: la ubicación no ha movido un solo nivel, puntuación, motivo ni alerta.
    assert _what_the_engine_decided(client, affected[1]) == decided_before
    # Del contexto descriptivo de cada alerta solo cambia lo que nombra la ubicacion.
    assert _context_of(client, affected[1]) == context_before
    # Aparece en el contexto de misión del tripulante, como una EVA, y la hipótesis que ha
    # bajado se puede seguir confirmando: la persona decide, no el orden.
    events = client.get("/api/status", params={"subject": affected[1]}).json()["mission"]["events"]
    assert [(item["kind"], item["module"]) for item in events] == [("location", "laboratorio")]
    assert client.post("/api/crew/hypotheses/review", json={
        "decision": "confirmed", "parameter": first["excursion"]["parameter"],
        "excursion_start": first["excursion"]["start"], "decided_by": "CDR",
        "reason": "el segundo sensor coincide y la ubicación estaba mal declarada",
    }).status_code == 201

    # Una declaración posterior corrige a la anterior: vuelven a ser dos los que estaban.
    fixed = _declare(client, affected[1], DEFAULT_MODULE, label="corrección")
    assert fixed.status_code == 201
    again = client.get("/api/crew").json()
    assert again["correlation"]["hypotheses"][0]["kind"] == "shared_environment"
    assert again["correlation"]["hypotheses"][0]["likelihood"] == "primary"
    assert again["correlation"]["hypotheses"][0]["location"]["present"] == [affected[1]]
    assert again["correlation"]["hypotheses"][0]["review"]["decision"] == "confirmed"
    now_in = {member["subject"]: member["location"] for member in again["crew"]}
    assert now_in[affected[1]]["module"] == DEFAULT_MODULE
    assert now_in[affected[1]]["ledger_index"] == fixed.json()["ledger_index"]
    assert store.verify_integrity().ok


def test_only_a_location_the_console_signed_in_a_listed_module_counts(
    client: TestClient,
) -> None:
    client.post("/api/simulate", params=CO2_SCENARIO)
    before = client.get("/api/crew").json()
    affected = before["correlation"]["hypotheses"][0]["affected"]
    store = get_store()

    def nothing_changed() -> None:
        crew = client.get("/api/crew").json()
        assert crew["correlation"] == before["correlation"]
        assert all(member["location"] is None for member in crew["crew"])

    # Un asiento con la misma forma firmado por otra identidad no es una declaración de la
    # consola: no reordena nada ni sitúa a nadie.
    for subject in affected:
        store.record_mission_event(
            subject, "location", MISSION_START, MISSION_START + dt.timedelta(days=60), "x",
            "nadie", identity_for("otra-fuente"), module="laboratorio",
        )
    nothing_changed()
    # Y una de la consola en un módulo que ya no está en la lista (la lista es de diseño y
    # puede cambiar) no se puede comparar con ninguna lectura: no da por ausente a nadie.
    for subject in affected:
        store._record_action("mission-event", {
            "subject": subject, "kind": "location", "module": "taller", "label": "Taller",
            "start": "2026-11-01T00:00:00+00:00", "end": "2026-12-31T00:00:00+00:00",
            "declared_by": "CDR",
        }, identity_for("crew-console"))
    nothing_changed()
    assert store.verify_integrity().ok


def test_an_unknown_module_or_a_module_out_of_place_is_refused(client: TestClient) -> None:
    size = len(get_store().ledger)
    assert _declare(client, "crew-01", "puente").status_code == 422
    assert _declare(client, "crew-01", "Laboratorio").status_code == 422
    missing = client.post("/api/mission/events", json={
        "kind": "location", "start": "2026-11-01T00:00:00+00:00",
        "end": "2026-11-02T00:00:00+00:00", "declared_by": "CDR",
    })
    assert missing.status_code == 422
    # Un módulo en una EVA, una EVA sin descripción o un tipo de evento que no existe.
    eva = {
        "kind": "eva", "start": "2026-11-01T00:00:00+00:00",
        "end": "2026-11-02T00:00:00+00:00", "declared_by": "CDR",
    }
    assert client.post(
        "/api/mission/events", json={**eva, "label": "EVA 1", "module": "esclusa"}
    ).status_code == 422
    assert client.post("/api/mission/events", json=eva).status_code == 422
    assert client.post(
        "/api/mission/events", json={**eva, "kind": "picnic", "label": "x"}
    ).status_code == 422
    # Una lectura de cabina solo cae en un módulo de la lista declarada.
    assert client.post(
        "/api/habitat", json={"parameter": "cabin-ppco2", "value": 2.1, "module": "puente"}
    ).status_code == 422
    assert len(get_store().ledger) == size
    # Lo que sí entra: la EVA con su descripción, y la lectura con módulo y sin él.
    assert client.post("/api/mission/events", json={**eva, "label": "EVA 1"}).status_code == 201
    in_airlock = client.post(
        "/api/habitat", json={"parameter": "cabin-ppco2", "value": 2.1, "module": "esclusa"}
    )
    by_default = client.post("/api/habitat", json={"parameter": "cabin-ppco2", "value": 2.1})
    assert (in_airlock.status_code, by_default.status_code) == (201, 201)
    entries = get_store().ledger.entries
    assert entries[in_airlock.json()["ledger_index"]].payload["module"] == "esclusa"
    assert entries[by_default.json()["ledger_index"]].payload["module"] == DEFAULT_MODULE
    assert "module" not in entries[size].payload, "una EVA no lleva módulo en su asiento"


def test_the_store_refuses_what_the_api_refuses(client: TestClient) -> None:
    # El almacén no se fía de quien le llama: la regla está en la escritura del asiento, no
    # solo en el validador de la API.
    store, console = get_store(), identity_for("crew-console")
    size = len(store.ledger)
    end = MISSION_START + dt.timedelta(hours=1)
    for module in ("puente", "Laboratorio", None):
        with pytest.raises(ValueError, match="módulo desconocido"):
            store.record_mission_event(
                "crew-01", "location", MISSION_START, end, "x", "CDR", console, module=module
            )
    with pytest.raises(ValueError, match="tipo de evento de misión desconocido"):
        store.record_mission_event("crew-01", "picnic", MISSION_START, end, "x", "CDR", console)
    with pytest.raises(ValueError, match="solo una declaración de ubicación lleva módulo"):
        store.record_mission_event(
            "crew-01", "eva", MISSION_START, end, "x", "CDR", console, module="esclusa"
        )
    with pytest.raises(ValueError, match="terminar después de empezar"):
        store.record_mission_event(
            "crew-01", "location", end, MISSION_START, "x", "CDR", console, module="esclusa"
        )
    assert len(store.ledger) == size


def test_a_location_entry_with_a_malformed_module_is_not_delivered(client: TestClient) -> None:
    # `module` es opcional en el asiento, pero si está tiene que ser texto, como los demás
    # campos: un asiento firmado con otra cosa es una acción mal formada, no una ubicación.
    store = get_store()
    store._record_action("mission-event", {
        "subject": "crew-01", "kind": "location", "module": 7, "label": "x",
        "start": "2026-11-01T00:00:00+00:00", "end": "2026-11-02T00:00:00+00:00",
        "declared_by": "CDR",
    }, identity_for("crew-console"))
    with pytest.raises(TamperedRecordError, match="acción mal formada"):
        store.mission_events("crew-01")


def test_the_modules_are_published_and_the_simulation_can_fill_several(
    client: TestClient,
) -> None:
    body = client.get("/api/habitat/modules").json()
    assert [item["key"] for item in body["modules"]] == list(MODULES)
    assert body["default"] == DEFAULT_MODULE and "diseño" in body["basis"]
    seeded = client.post("/api/simulate", params={"days": 3, "habitat_modules": 2}).json()
    assert seeded["simulation"]["habitat"]["extra_modules"] == ["laboratorio"]
    latest = client.get("/api/habitat").json()["latest"]
    assert {item["module"] for item in latest} == {DEFAULT_MODULE, "laboratorio"}
    assert client.post(
        "/api/simulate", params={"days": 3, "habitat_modules": len(MODULES) + 1}
    ).status_code == 422
