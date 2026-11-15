"""Crónica, "esta semana" y "qué depende de este dato" (Polaris `cronica`, `anticipa`,
`cascada_mapa`) con datos de EMMA: del simulador y del ledger, sin red.

La línea temporal va en el tiempo de los datos. Para demostrarlo, el reloj real de estas pruebas
está parado en 2031 (`frozen_clock`), a años de la misión de prueba (noviembre y diciembre de
2026): lo que aquí cuadra con la misión no puede haber salido del reloj.

Las pruebas rápidas van primero y las que simulan una misión entera, al final: la campaña de
mutantes (`tests/mutants/timeline.json`) corre este fichero una vez por mutante y para en el
primer fallo.
"""

from __future__ import annotations

import datetime as dt
import io
import re
import types
from typing import Any, Self

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app import export, polaris, text_guard, timeline
from app.analysis import recovery
from app.api import routes
from app.api.routes import CONSOLE_IDENTITY, audit_identity, identity_for, new_store
from app.core import display
from app.core.storage import DISMISSAL_ENTRY_TYPE, TamperedRecordError, seed_from_simulator
from app.environment.habitat import DEFAULT_MODULE, HabitatReading
from app.ingest import inspiration4
from app.ingest.fhir import observation
from app.reports import labs
from tests.test_api import alerting  # noqa: F401 — fixture

__all__ = ["alerting"]

START = dt.date(2026, 11, 1)  # el origen de misión por defecto (`Settings.mission_start`)
DURATION = 180
NOW = dt.datetime(2026, 12, 10, 23, tzinfo=dt.UTC)  # la última lectura de la misión de prueba
FROZEN = dt.datetime(2031, 5, 5, 12, tzinfo=dt.UTC)  # el reloj real, parado
MINUTE = dt.timedelta(minutes=1)
HOUR = dt.timedelta(hours=1)
DAY = dt.timedelta(days=1)


class _FrozenDate(dt.date):
    @classmethod
    def today(cls) -> Self:
        return cls(FROZEN.year, FROZEN.month, FROZEN.day)


class _FrozenDateTime(dt.datetime):
    @classmethod
    def now(cls, tz: dt.tzinfo | None = None) -> Self:
        return cls.fromtimestamp(FROZEN.timestamp(), tz)


@pytest.fixture
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> dt.datetime:
    """El reloj real, parado en 2031 para la API, para `app/timeline.py` y para `anticipa`."""
    clock = types.SimpleNamespace(**vars(dt))
    clock.date, clock.datetime = _FrozenDate, _FrozenDateTime
    monkeypatch.setattr(timeline, "dt", clock)
    monkeypatch.setattr(polaris.load("anticipa"), "date", _FrozenDate)
    monkeypatch.setattr(routes, "_now", lambda: FROZEN)
    return FROZEN


# --------------------------------------------------------------------------- #
# El ahora
# --------------------------------------------------------------------------- #


def test_now_is_the_one_of_the_data_and_the_clock_only_without_readings() -> None:
    status = {"data": {"reference_time": NOW.isoformat()}}
    assert timeline.as_of(status, None, FROZEN) == timeline.AsOf(NOW, "data")
    # Con lecturas, el corte de Tierra no mueve el ahora: ya va dentro del estado.
    assert timeline.as_of(status, NOW + DAY, FROZEN) == timeline.AsOf(NOW, "data")
    # Sin lecturas: el corte pedido y, si no lo hay, el reloj real. Y se dice cuál.
    assert timeline.as_of({}, NOW, FROZEN) == timeline.AsOf(NOW, "cut")
    declared = timeline.as_of({}, None, FROZEN).to_dict()
    assert declared["as_of"] == FROZEN.isoformat() and declared["as_of_source"] == "clock"
    assert "reloj real" in declared["as_of_basis"]


# --------------------------------------------------------------------------- #
# Esta semana
# --------------------------------------------------------------------------- #


def test_this_week_is_the_week_of_the_data_with_the_wall_clock_frozen_years_away(
    frozen_clock: dt.datetime,
) -> None:
    soon, later = (NOW + 3 * DAY).date(), (NOW + 40 * DAY).date()
    wall = (frozen_clock + 2 * DAY).date()  # en la semana del reloj real, no en la de los datos
    status = {
        "data": {"reference_time": NOW.isoformat()},
        "followups": [
            # La forma del estado (`advisor/followup.py`) y la de un asunto suelto.
            {"countermeasure": {"id": "cv-repeat-rest"}, "domain": "cardiovascular",
             "window_ends": f"{soon}T00:00:00Z", "state": "in_window"},
            {"countermeasure_id": "viejo", "domain": "x", "window_ends": f"{soon}",
             "state": "closed"},
        ],
        "predictions": [{"key": "heart-rate", "horizon_at": f"{later}T00:00:00Z"}],
        "mission": {"events": [
            {"kind": "eva", "label": "EVA 2", "start": f"{soon}"},
            {"kind": "eva", "label": "EVA del reloj", "start": f"{wall}"},
        ]},
    }
    items = timeline.week_items(status)
    assert len(items) == 4, "lo cerrado no cuenta"
    week = timeline.this_week(status, timeline.as_of(status, None, frozen_clock), 7)
    titles = [item["titulo"] for item in week["items"]]
    assert any("cv-repeat-rest" in title for title in titles)
    assert any("EVA 2" in title for title in titles)
    assert not any("heart-rate" in title for title in titles), "a 40 días queda fuera de la semana"
    assert not any("EVA del reloj" in title for title in titles), "la semana es la de los datos"
    assert (week["as_of"], week["as_of_source"]) == (NOW.isoformat(), "data")
    # El bloque de Polaris cuenta la misma semana: su `date.today()` es el día de los datos.
    assert "cv-repeat-rest" in week["block"] and "EVA 2" in week["block"]
    assert "EVA del reloj" not in week["block"]


def test_this_week_restores_the_copy_after_the_call() -> None:
    follow, summit = polaris.load("seguimiento"), polaris.load("cumbre")
    anticipa = polaris.load("anticipa")
    before = (follow.recopilar, summit.foco, anticipa.date)
    timeline.this_week({}, timeline.as_of({}, None, FROZEN), 7)
    assert follow.recopilar is before[0] and summit.foco is before[1]
    assert anticipa.date is before[2], "el reloj de la copia vuelve a ser el suyo"


# --------------------------------------------------------------------------- #
# Crónica
# --------------------------------------------------------------------------- #


def _cabin(parameter: str, value: float, at: dt.datetime) -> HabitatReading:
    return HabitatReading(DEFAULT_MODULE, parameter, value, at, "habitat-telemetry")


def _mission() -> tuple[Any, dict[str, Any]]:
    """Un almacén con lo que se firma en una misión y el estado que lo acompaña.

    Todo va fechado respecto a `NOW`, la última lectura. El estado es el de `/api/status` en lo
    que la crónica lee de él: la crónica no calcula nada, así que aquí se le da hecho.
    """
    store = new_store()
    console = identity_for(CONSOLE_IDENTITY)
    store.record_habitat(
        [
            # Ruido: dos lecturas por encima de [V2 6077] y vuelve. Una excursión cerrada.
            _cabin("cabin-noise", 60, NOW - 30 * HOUR),
            _cabin("cabin-noise", 90, NOW - 29 * HOUR),
            _cabin("cabin-noise", 91, NOW - 28 * HOUR),
            _cabin("cabin-noise", 60, NOW - 27 * HOUR),
            # Oxígeno: la última lectura sigue fuera de [V2 6003]. Una excursión abierta.
            _cabin("cabin-ppo2", 150, NOW - 5 * HOUR),
            _cabin("cabin-ppo2", 120, NOW - 4 * HOUR),
            # Y una lectura posterior al ahora del tripulante: todavía no ha pasado.
            _cabin("cabin-noise", 95, NOW + 5 * HOUR),
        ],
        identity_for("habitat-telemetry"),
    )
    store.acknowledge("crew-01", "cardiovascular", "concern", NOW - 2 * HOUR, "comandante", console)
    store.record_alert_resolution(
        "crew-01", "cardiovascular", "concern", NOW - HOUR, "resuelto", "", "CMO", console)
    store.set_annunciation(
        "crew-01", "suppress", "cardiovascular", "concern", NOW - 3 * HOUR, NOW - 2 * HOUR,
        "en valoración", "comandante", console)
    adoption = store.record_followup(
        "crew-01", "adopted", "cv-repeat-rest", "cardiovascular", "concern", NOW - 90 * HOUR,
        "CMO", console)
    store.record_safe_mode(True, "prueba", "CMO", console)
    past = store.record_mission_event(
        "crew-01", "eva", NOW - 50 * HOUR, NOW - 44 * HOUR, "EVA 1", "CMO", console)
    future = store.record_mission_event(
        "crew-01", "eva", NOW + 50 * HOUR, NOW + 56 * HOUR, "EVA 2", "CMO", console)
    status = {
        "data": {"reference_time": NOW.isoformat()},
        "rules_version": "reglas-de-prueba",
        "alerts": [
            {"domain": "cardiovascular", "level": "concern", "rules_version": "reglas-de-prueba",
             "detail": {"onset": (NOW - 34 * HOUR).isoformat(),
                        "onset_basis": "primera lectura fuera de lo esperado"}},
            {"domain": "bone", "level": "watch", "rules_version": "reglas-de-prueba",
             "detail": {"onset": None, "onset_basis": "la alerta viene de una tendencia"}},
        ],
        "domains": {
            "cardiovascular": {"trajectory": {
                "direction": "worsening", "from_level": "nominal", "to_level": "concern",
                "since": (NOW - 48 * HOUR).isoformat(),
                "basis": "nivel de nominal hace una ventana y de preocupación ahora"}},
            "bone": {"trajectory": None},
        },
        "followups": [
            {"adoption_index": adoption.index, "countermeasure": {"id": "cv-repeat-rest"},
             "domain": "cardiovascular", "window_ends": (NOW - 42 * HOUR).isoformat()},
            {"adoption_index": 999, "countermeasure": {"id": "por-venir"},
             "domain": "cardiovascular", "window_ends": (NOW + 6 * HOUR).isoformat()},
        ],
        "mission": {"events": [
            {"kind": "eva", "label": label, "start": (NOW + start * HOUR).isoformat(),
             "end": (NOW + (start + 6) * HOUR).isoformat(), "declared_by": "CMO",
             "ledger_index": entry.index}
            for label, start, entry in (("EVA 1", -50, past), ("EVA 2", 50, future))
        ]},
    }
    return store, status


def _chronicle(until: dt.datetime | None = None) -> dict[str, Any]:
    store, status = _mission()
    now = timeline.as_of(status, until, FROZEN)
    return timeline.chronicle(store, "crew-01", status, now, START, DURATION, until)


def _facts(chronicle: dict[str, Any], fact: str) -> list[dict[str, Any]]:
    return [event for event in chronicle["events"] if event["fact"] == fact]


def test_the_chronicle_tells_what_happened_not_only_what_the_operator_did(
    frozen_clock: dt.datetime,
) -> None:
    chronicle = _chronicle()
    assert (chronicle["as_of"], chronicle["as_of_source"]) == (NOW.isoformat(), "data")

    # El inicio de la alerta: el `onset` del análisis, con su nivel y sus reglas.
    [onset] = _facts(chronicle, "alert-onset")
    assert onset["at"] == (NOW - 34 * HOUR).isoformat() and onset["level"] == "concern"
    assert "cardiovascular:concern" in onset["que"] and "primera lectura" in onset["que"]
    assert "reglas-de-prueba" in onset["fuente"] and onset["quien"] == "EMMA"
    # Una alerta que no tiene lectura que la feche se anota en el ahora, sin inventarle inicio.
    [undated] = _facts(chronicle, "alert-active")
    assert undated["at"] == NOW.isoformat() and "sin inicio que fechar" in undated["que"]
    # El cambio de nivel de un dominio, con las palabras del análisis.
    [change] = _facts(chronicle, "level-change")
    assert change["level"] == "concern" and "hace una ventana" in change["que"]

    # La excursión de cabina, con su requisito y la clase de límite.
    every_start = _facts(chronicle, "habitat-excursion-start")
    # Salir del rango objetivo del O2 (145-155) se cuenta con su clase, que no es de salud.
    [target] = [event for event in every_start if event["severity"] == "target"]
    assert target["at"] == (NOW - 4 * HOUR).isoformat() and "(rango objetivo)" in target["que"]
    starts = [event for event in every_start if event["severity"] != "target"]
    # Los 120 mmHg de O2 cruzan dos límites de la tabla 6.2-1 a la vez (la media de 1 h por
    # debajo de 127 y el mínimo absoluto de 122): dos hechos, cada uno con su requisito.
    assert [event["at"] for event in starts] == [
        (NOW - 29 * HOUR).isoformat(), (NOW - 4 * HOUR).isoformat(),
        (NOW - 4 * HOUR).isoformat()]
    assert all(event["severity"] == "health" and event["tipo"] == "habitat" for event in starts)
    sources = " | ".join(event["fuente"] for event in starts[1:])
    assert "[V2 6003] hipoxia leve, media 1 h" in sources
    assert "[V2 6003] mínimo absoluto" in sources
    assert "Ruido de cabina" in starts[0]["que"] and "[V2 6077]" in starts[0]["fuente"]

    # Los cambios de fase ya ocurridos en el día 39: el despegue y el fin de la adaptación.
    phases = _facts(chronicle, "phase-change")
    assert [event["mission_day"] for event in phases] == [0, 14]
    assert "prevuelo → adaptación" in phases[0]["que"]

    # La contramedida adoptada y el fin de su ventana de seguimiento; la EVA, cuando empezó.
    [adopted] = _facts(chronicle, "countermeasure-adopted")
    [window] = _facts(chronicle, "followup-window-end")
    assert adopted["at"] == (NOW - 90 * HOUR).isoformat()
    assert window["at"] == (NOW - 42 * HOUR).isoformat() and "cv-repeat-rest" in window["que"]
    assert [event["que"] for event in _facts(chronicle, "mission-event-start")] == [
        "eva: EVA 1, inicio"]
    # Dejar de anunciar una alerta también se cuenta, con su motivo.
    [silenced] = _facts(chronicle, "annunciation-suppress")
    assert "suprimido" in silenced["que"] and "en valoración" in silenced["que"]


def test_a_declared_location_is_told_as_such_and_is_not_a_plan_event(
    frozen_clock: dt.datetime,
) -> None:
    """La ubicación de un tripulante llega con los eventos de misión (`kind` = `location`). Es un
    hecho firmado y se cuenta, con su nombre; pero no es un evento del plan: su intervalo no
    «empieza» ni «termina» en la crónica, ni es un asunto de los próximos días."""
    store = new_store()
    console = identity_for(CONSOLE_IDENTITY)
    stay = store.record_mission_event(
        "crew-01", "location", NOW - 10 * HOUR, NOW + 3 * DAY, "Laboratorio", "CMO", console,
        module="laboratorio")
    eva = store.record_mission_event(
        "crew-01", "eva", NOW - 50 * HOUR, NOW - 44 * HOUR, "EVA 1", "CMO", console)
    events = [
        {"kind": "location", "label": "Laboratorio", "module": "laboratorio",
         "start": (NOW - 10 * HOUR).isoformat(), "end": (NOW + 3 * DAY).isoformat(),
         "declared_by": "CMO", "ledger_index": stay.index},
        {"kind": "eva", "label": "EVA 1", "start": (NOW - 50 * HOUR).isoformat(),
         "end": (NOW - 44 * HOUR).isoformat(), "declared_by": "CMO", "ledger_index": eva.index},
    ]
    status = {"data": {"reference_time": NOW.isoformat()}, "mission": {"events": events}}
    now = timeline.as_of(status, None, FROZEN)
    chronicle = timeline.chronicle(store, "crew-01", status, now, START, DURATION, None)

    [declared] = _facts(chronicle, "location-declared")
    assert declared["que"] == "ubicación declarada: Laboratorio"
    assert (declared["clave"], declared["quien"]) == (f"ledger:{stay.index}", "CMO")
    # La EVA se cuenta como siempre: declarada, y con su inicio y su fin ya pasados.
    assert [event["que"] for event in _facts(chronicle, "mission-event-declared")] == [
        "eva declarada: EVA 1"]
    assert [event["que"] for event in _facts(chronicle, "mission-event-start")] == [
        "eva: EVA 1, inicio"]
    assert [event["que"] for event in _facts(chronicle, "mission-event-end")] == [
        "eva: EVA 1, fin"]
    # La clave interna del tipo no llega a ningún texto de la crónica.
    assert not any("location" in event["que"] for event in chronicle["events"])

    # Tampoco es un asunto de «próximos días», aunque su intervalo acabe dentro de la semana.
    assert [item["titulo"] for item in timeline.week_items(status)] == ["eva: EVA 1"]
    week = timeline.this_week(status, now, 7)
    assert week["items"] == [] and "Laboratorio" not in week["block"]


def test_the_chronicle_only_tells_the_decisions_the_status_counts(
    frozen_clock: dt.datetime,
) -> None:
    """Lo firmado por otra identidad no lo cuenta el estado (`routes._counts`) y, desde el
    2026-10-26 (decisión del usuario), tampoco la crónica: se omite. Ni un descarte o un silencio
    que la API no habría aceptado, aunque lo firme la consola. El modo seguro sí, como el estado."""
    store, status = _mission()
    now = timeline.as_of(status, None, FROZEN)

    def told() -> list[tuple[str, str]]:
        chronicle = timeline.chronicle(store, "crew-01", status, now, START, DURATION)
        return [(event["fact"], event["que"]) for event in chronicle["events"]]

    before = told()
    other = identity_for("otra-identidad")
    level = ("crew-01", "cardiovascular", "concern", NOW - HOUR / 2)
    store.acknowledge(*level, "intruso", other)
    store.record_alert_resolution(*level, "en_arreglo", "", "intruso", other)
    store.record_alert_dismissal(*level, "sensor_artifact", "", "intruso", other)
    store.set_annunciation(
        "crew-01", "inhibit", "cardiovascular", "concern", NOW - HOUR, NOW + HOUR, "x", "intruso",
        other)
    store.record_followup(
        "crew-01", "closed", "cv-repeat-rest", "cardiovascular", "concern", NOW - HOUR,
        "intruso", other)
    store.record_mission_event(
        "crew-01", "eva", NOW - 20 * HOUR, NOW - 18 * HOUR, "EVA ajena", "intruso", other)
    store.record_system_status("communications", "out-of-service", NOW - HOUR, "", "intruso", other)
    store.record_sensor_binding(
        "wearable-ble", "bind", NOW - HOUR, "", "intruso", other, crew="crew-01")
    store.record_resource_availability("ared", "unavailable", NOW - HOUR, "", "intruso", other)
    # Firmados por la consola, pero que la API no habría aceptado: un motivo fuera del vocabulario
    # (escrito por fuera de la API, que lo rechaza) y una supresión de 13 h (el tope es 12).
    console = identity_for(CONSOLE_IDENTITY)
    store._record_action(DISMISSAL_ENTRY_TYPE, {
        "subject": "crew-01", "domain": "cardiovascular", "level": "concern",
        "reference_time": (NOW - HOUR).isoformat(), "reason": "inventado", "note": "",
        "declared_by": "CMO"}, console)
    store.set_annunciation(
        "crew-01", "suppress", "cardiovascular", "concern", NOW - HOUR, NOW + 12 * HOUR,
        "demasiado", "CMO", console)
    assert told() == before
    # El modo seguro vale el último asiento, lo firme quien lo firme, aquí y en el estado.
    store.record_safe_mode(False, "", "intruso", other)
    assert [fact for fact, _ in told() if fact.startswith("safe-mode")] == [
        "safe-mode-on", "safe-mode-off"]
    # Y lo mismo firmado por la consola sí se cuenta.
    store.record_alert_resolution(*level, "en_arreglo", "", "CMO", console)
    assert [fact for fact, _ in told()].count("alert-in-progress") == 1


def test_the_chronicle_tells_each_change_of_mission_level_as_the_status_counts_it(
    frozen_clock: dt.datetime,
) -> None:
    """Cada cambio de nivel de misión (`core/mission_modes.py`, §3.27), como el modo seguro: en
    su hora de firma, con el nivel anterior y el nuevo, quién lo firmó y el motivo. Pero cuenta lo
    que cuenta el estado (`storage.mission_mode`): lo firmado por la consola y, para Tierra, lo
    que ya existía en su corte. Un asiento redactado se va, y el siguiente cuenta desde el que
    queda, como la versión, que baja en uno."""
    store = new_store()
    console, other = identity_for(CONSOLE_IDENTITY), identity_for("otra-identidad")
    status = {"data": {"reference_time": NOW.isoformat()}}

    def told(until: dt.datetime | None = None, source: Any = None) -> list[dict[str, Any]]:
        now = timeline.as_of(status, until, FROZEN)
        chronicle = timeline.chronicle(
            source or store, "crew-01", status, now, START, DURATION, until)
        return _facts(chronicle, "mission-mode-change")

    assert told() == []
    store.record_system_status("power", "degraded", NOW - HOUR, "", "CDR", console)
    down = store.record_mission_mode(
        "reduced", "energía racionada", "CMO", console, cited_system="power")
    # Lo firmado por otra identidad no lo cuenta el estado, ni la crónica.
    store._record_action("mission-mode", {
        "subject": "sistema", "level": "nominal", "reason": "", "declared_by": "intruso"}, other)
    lower = store.record_mission_mode("minimal", "sin tiempo de tripulación", "CDR", console)
    up = store.record_mission_mode("reduced", "", "CMO", console)
    assert store.mission_mode()["version"] == 3

    events = told()
    assert [event["que"].split(";")[0] for event in events] == [
        "nivel de misión: de nominal a reducido",
        "nivel de misión: de reducido a mínimo",
        "nivel de misión: de mínimo a reducido",
    ]
    assert events[0]["que"] == (
        "nivel de misión: de nominal a reducido; motivo: energía racionada; cita Energía: "
        "degradado al firmar (declarado, no telemetría)")
    assert events[1]["que"].endswith("motivo: sin tiempo de tripulación")
    assert "motivo" not in events[2]["que"], "subir no exige motivo y no se inventa uno"
    # Lo redacta el backend y no manda nada (invariante 7).
    assert all(text_guard.check(event["que"]) == [] for event in events)
    assert [(event["clave"], event["quien"], event["tipo"]) for event in events] == [
        (f"ledger:{down.index}", "CMO", "sistema"), (f"ledger:{lower.index}", "CDR", "sistema"),
        (f"ledger:{up.index}", "CMO", "sistema")]
    # Sin instante de datos, como el modo seguro: su hora de firma, aparte de la misión.
    assert all(event["time_basis"] == "recorded" and event["stage"] == "unplaced"
               and event["at"] == event["recorded"] for event in events)

    # Tierra, con el corte en la firma del segundo cambio: los dos primeros, y nada más. Las
    # firmas caen en el mismo instante del ordenador: aquí cada asiento se firma un minuto
    # después del anterior.
    stamped = _SignedByIndex(store, NOW)
    assert [event["clave"] for event in told(NOW + lower.index * MINUTE, stamped)] == [
        f"ledger:{down.index}", f"ledger:{lower.index}"]
    assert told(NOW + down.index * MINUTE - MINUTE, stamped) == []

    # Redactar el segundo cambio: el tercero cuenta desde el primero, y la versión baja en uno.
    store.redact(lower.index, audit_identity(), "nivel firmado por error", "CMO")
    assert store.mission_mode()["version"] == 2
    assert [event["que"].split(";")[0] for event in told()] == [
        "nivel de misión: de nominal a reducido", "nivel de misión: de reducido a reducido"]

    # Un asiento firmado por la consola pero fuera del vocabulario: un 409, como en el estado.
    store._record_action("mission-mode", {
        "subject": "sistema", "level": "apagado", "reason": "x", "declared_by": "CMO"}, console)
    with pytest.raises(TamperedRecordError, match="nivel desconocido"):
        told()


def test_every_fact_carries_its_instant_in_data_time_and_its_source(
    frozen_clock: dt.datetime,
) -> None:
    chronicle = _chronicle()
    events = chronicle["events"]
    assert all(event["fuente"] and event["quien"] for event in events)
    assert len({event["clave"] for event in events}) == len(events), "la clave no se repite"
    signed = [event for event in events if event["fuente"].startswith("asiento ")]
    assert all(event["clave"].startswith(("ledger:", "mission-event:")) for event in signed)

    # Un reconocimiento va en el instante del estado sobre el que se decidió, no en el de la
    # firma (el reloj del ordenador, que con una misión simulada es de otro mes).
    [ack] = _facts(chronicle, "alert-acknowledged")
    assert ack["at"] == (NOW - 2 * HOUR).isoformat() and ack["time_basis"] == "data"
    assert ack["fecha"] == "2026-12-10" and ack["mission_day"] == 39
    assert ack["recorded"] != ack["at"] and ack["clave"].startswith("ledger:")

    # Lo que solo tiene hora de firma se dice, no se sitúa en la misión y va al final.
    unplaced = [event for event in events if event["time_basis"] == "recorded"]
    assert {event["fact"] for event in unplaced} == {"safe-mode-on", "mission-event-declared"}
    assert all(
        event["stage"] == "unplaced" and event["mission_day"] is None for event in unplaced)
    assert events[-len(unplaced):] == unplaced
    placed = [dt.datetime.fromisoformat(event["at"]) for event in events[:-len(unplaced)]]
    assert placed == sorted(placed) and placed[-1] <= NOW, "en orden y nada posterior al ahora"

    # Cada evento, además, con la línea de bitácora de Polaris.
    assert len(chronicle["lines"]) == len(events)
    assert any("reconocida" in line and "comandante" in line for line in chronicle["lines"])


def test_the_chronicle_is_grouped_by_the_stages_of_the_specification(
    frozen_clock: dt.datetime,
) -> None:
    chronicle = _chronicle()
    stages = {stage["key"]: stage for stage in chronicle["stages"]}
    # La carrera (misiones previas declaradas) va antes del prevuelo: `test_mission_history.py`.
    assert list(stages) == [
        "career", "preflight", "mission-day", "intervention", "followup", "postflight", "unplaced"]
    assert all(stage["display"] for stage in stages.values())
    assert sum(stage["count"] for stage in stages.values()) == len(chronicle["events"])

    def stage_of(fact: str) -> set[str]:
        return {event["stage"] for event in _facts(chronicle, fact)}

    assert stage_of("alert-acknowledged") == stage_of("countermeasure-adopted") == {"intervention"}
    assert stage_of("alert-resolved") == stage_of("followup-window-end") == {"followup"}
    assert stage_of("alert-onset") == stage_of("habitat-excursion-start") == {"mission-day"}

    # Antes del despegue y tras el regreso manda la fecha: una decisión de dos días antes del
    # origen es de prevuelo, y con la misión acabada lo último es de posvuelo.
    store, status = _mission()
    console = identity_for(CONSOLE_IDENTITY)
    origin = dt.datetime.combine(START, dt.time(0, tzinfo=dt.UTC))
    store.acknowledge("crew-01", "behavioral", "watch", origin - 2 * DAY, "CMO", console)
    store.acknowledge(
        "crew-01", "behavioral", "watch", origin + (DURATION + 3) * DAY, "CMO", console)
    over = {"data": {"reference_time": (origin + (DURATION + 10) * DAY).isoformat()}}
    after = timeline.chronicle(
        store, "crew-01", over, timeline.as_of(over, None, FROZEN), START, DURATION)
    acks = {event["mission_day"]: event["stage"] for event in _facts(after, "alert-acknowledged")}
    assert acks[-2] == "preflight" and acks[DURATION + 3] == "postflight"
    phases = _facts(after, "phase-change")
    assert [event["mission_day"] for event in phases] == [0, 14, DURATION - 7, DURATION]
    assert phases[-1]["stage"] == "postflight"


def test_nothing_after_now_is_told_and_an_open_excursion_has_no_end(
    frozen_clock: dt.datetime,
) -> None:
    chronicle = _chronicle()
    # El ruido volvió a su límite: tiene fin. El oxígeno sigue fuera: no lo tiene todavía.
    [end] = _facts(chronicle, "habitat-excursion-end")
    assert end["at"] == (NOW - 28 * HOUR).isoformat() and "Ruido de cabina" in end["que"]
    # La lectura de cabina posterior al ahora, la EVA por venir y la ventana que aún no vence.
    assert all(dt.datetime.fromisoformat(event["at"]) <= NOW
               for event in chronicle["events"] if event["time_basis"] == "data")
    assert not any("EVA 2" in event["que"] for event in _facts(chronicle, "mission-event-start"))
    assert not any("por-venir" in event["que"] for event in chronicle["events"])
    # La EVA por venir consta solo como declarada.
    assert any("EVA 2" in event["que"] for event in _facts(chronicle, "mission-event-declared"))


def test_an_excursion_of_a_single_reading_starts_before_it_ends(
    frozen_clock: dt.datetime,
) -> None:
    store = new_store()
    store.record_habitat(
        [_cabin("cabin-noise", value, NOW - hours * HOUR)
         for value, hours in ((60, 3), (90, 2), (60, 1))],
        identity_for("habitat-telemetry"),
    )
    status = {"data": {"reference_time": NOW.isoformat()}}
    chronicle = timeline.chronicle(
        store, "crew-01", status, timeline.as_of(status, None, frozen_clock), START, DURATION)
    cabin = [event for event in chronicle["events"] if event["tipo"] == "habitat"]
    # Los dos hechos caen en el mismo instante: el orden lo da lo que pasó, no la clave.
    assert [event["fact"] for event in cabin] == [
        "habitat-excursion-start", "habitat-excursion-end"]
    assert cabin[0]["at"] == cabin[1]["at"] == (NOW - 2 * HOUR).isoformat()


class _SignedAt:
    """El almacén de verdad, con la hora de firma que diga la prueba.

    El ledger fecha cada asiento con el reloj del ordenador y el corte de Tierra se compara con
    esa hora: sin esto, el resultado dependería del día en que se corre la prueba.
    """

    def __init__(self, store: Any, recorded: dt.datetime) -> None:
        self._store, self._recorded = store, recorded.isoformat()

    def __getattr__(self, name: str) -> Any:
        read = getattr(self._store, name)

        def stamped(*args: Any, **kwargs: Any) -> list[Any]:
            return [
                {**item, "recorded": self._recorded} if isinstance(item, dict) else item
                for item in read(*args, **kwargs)
            ]

        return stamped


class _SignedByIndex(_SignedAt):
    """Como `_SignedAt`, pero cada asiento firmado un minuto después del anterior."""

    def __getattr__(self, name: str) -> Any:
        read = getattr(self._store, name)
        base = dt.datetime.fromisoformat(self._recorded)

        def stamped(*args: Any, **kwargs: Any) -> list[Any]:
            return [
                {**item, "recorded": (base + item["ledger_index"] * MINUTE).isoformat()}
                if isinstance(item, dict) and "ledger_index" in item else item
                for item in read(*args, **kwargs)
            ]

        return stamped


def test_earth_only_gets_what_was_already_signed_and_measured_at_its_cut(
    frozen_clock: dt.datetime,
) -> None:
    store, status = _mission()
    signed = _SignedAt(store, NOW - 100 * MINUTE)  # todo se firmó 100 minutos antes del ahora

    def earth(cut: dt.datetime) -> dict[str, Any]:
        received = {**status, "data": {"reference_time": cut.isoformat()}}
        now = timeline.as_of(received, cut, frozen_clock)
        return timeline.chronicle(signed, "crew-01", received, now, START, DURATION, cut)

    # El reconocimiento se decidió sobre el estado de hace 120 minutos; la resolución, sobre el
    # de hace 60: con el corte a 90, la segunda todavía no ha podido llegar.
    late = earth(NOW - 90 * MINUTE)
    assert _facts(late, "alert-acknowledged") and not _facts(late, "alert-resolved")
    # Con el corte antes de la firma, tampoco el reconocimiento: ese asiento aún no existía.
    assert not _facts(earth(NOW - 110 * MINUTE), "alert-acknowledged")
    # La cabina, igual: con el corte entre dos lecturas fuera de límite, la excursión de ruido
    # ha empezado y para Tierra sigue abierta.
    during = earth(NOW - 28.5 * HOUR)
    assert [event["at"] for event in _facts(during, "habitat-excursion-start")] == [
        (NOW - 29 * HOUR).isoformat()]
    assert not _facts(during, "habitat-excursion-end")
    # Y un corte anterior a todo, sin lecturas: ni lo firmado, ni la cabina, ni el calendario.
    cut = dt.datetime.combine(START, dt.time(0, tzinfo=dt.UTC)) - 30 * DAY
    nothing = timeline.chronicle(
        signed, "crew-01", {}, timeline.as_of({}, cut, frozen_clock), START, DURATION, cut)
    assert nothing["events"] == [] and nothing["as_of_source"] == "cut"


def test_without_readings_it_falls_back_to_the_real_clock_and_says_so(
    frozen_clock: dt.datetime,
) -> None:
    store, _ = _mission()
    chronicle = timeline.chronicle(
        store, "crew-01", {}, timeline.as_of({}, None, frozen_clock), START, DURATION)
    assert chronicle["as_of"] == frozen_clock.isoformat()
    assert chronicle["as_of_source"] == "clock" and "reloj real" in chronicle["as_of_basis"]
    # Sin lecturas no hay tiempo de misión: no se cuentan fases. Lo firmado sí consta.
    assert not _facts(chronicle, "phase-change")
    assert _facts(chronicle, "safe-mode-on") and _facts(chronicle, "alert-acknowledged")


def test_the_pdf_tells_the_same_chronicle_by_stage(frozen_clock: dt.datetime) -> None:
    markdown = export.chronicle_markdown(_chronicle(), "crew-01", frozen_clock)
    # Dos fechas distintas y las dos dichas: cuándo se generó y hasta dónde llegan los hechos.
    assert "Generada el 2031-05-05 12:00 UTC" in markdown
    assert "Hechos hasta el 2026-12-10 23:00 UTC (última lectura analizada" in markdown
    for heading in ("## día de misión", "## intervención", "## seguimiento", "## sin instante"):
        assert heading in markdown
    assert "## prevuelo" not in markdown, "una etapa sin hechos no se pinta"
    assert "| 2026-12-10 21:00 | 39 | alerta cardiovascular:concern reconocida |" in markdown
    pdf = export.to_pdf(markdown, "EMMA — crónica de crew-01")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    assert pdf.startswith(b"%PDF") and "reconocida" in text and "2026-12-10" in text
    assert "Sin hechos" in export.chronicle_markdown({"events": []}, "crew-01", frozen_clock)


# --------------------------------------------------------------------------- #
# Posvuelo: cada toma frente al prevuelo del propio tripulante
# --------------------------------------------------------------------------- #


def _inspiration4() -> tuple[Any, dt.datetime, dt.datetime]:
    """El hemograma real de Inspiration4 en un almacén, y el instante de su última toma."""
    store = new_store()
    launch = dt.datetime.combine(START, dt.time(0, tzinfo=dt.UTC))
    replay = inspiration4.load(launch)
    seed_from_simulator(store, replay.observations, identity_for(routes._SIMULATOR_SOURCE))
    last = max(item.effective for item in replay.observations if item.subject == "crew-01")
    return store, launch, last


def test_each_postflight_sample_enters_the_chronicle_against_the_crews_own_preflight(
    frozen_clock: dt.datetime,
) -> None:
    store, launch, last = _inspiration4()
    status = {"data": {"reference_time": last.isoformat()}}
    chronicle = timeline.chronicle(
        store, "crew-01", status, timeline.as_of(status, None, frozen_clock), START, DURATION)
    samples = _facts(chronicle, "postflight-sample")
    # Las mismas tomas que el panel, con su mismo regreso: el de los tres días de Inspiration4,
    # no el fin de la misión configurada (180 días). Una toma por indicador y día: ningún día
    # se agrupa, y cada evento va en el instante de su toma.
    expected = recovery.recovery(store.query("crew-01"), launch, launch + 3 * DAY)
    told = [(item["key"], sample) for item in expected for sample in item["postflight"]]
    assert told and len(samples) == len(told) and not _facts(chronicle, "postflight-day")
    assert sorted((event["clave"], event["at"]) for event in samples) == sorted(
        (f"recovery:{key}:R+{sample['days_after_landing']}", sample["at"])
        for key, sample in told)
    # En la etapa posvuelo aunque el calendario configurado la ponga en vuelo, sin nivel ni
    # insignia (no es una alerta) y con la regla de regreso en la fuente.
    assert {event["stage"] for event in samples} == {"postflight"}
    assert all(event["level"] is None and event["severity"] is None for event in samples)
    assert all(event["tipo"] == "posvuelo" and event["quien"] == "EMMA" for event in samples)
    assert all("OSD-569" in event["fuente"] and "sin veredicto" in event["fuente"]
               for event in samples)
    # Descriptivo: cuánto se separa y si cae dentro del rango, sin «recuperado».
    lymphocytes = next(item for item in expected if item["key"] == "lymphocytes")
    first = lymphocytes["postflight"][0]
    [event] = [event for event in samples
               if event["clave"] == f"recovery:lymphocytes:R+{first['days_after_landing']}"]
    assert f"R+{first['days_after_landing']};" in event["que"]
    assert f"{lymphocytes['preflight']['samples']} tomas" in event["que"]
    inside = "dentro" if first["within_preflight_range"] else "fuera"
    assert f"{inside} de su rango prevuelo" in event["que"]
    assert not any("recuperad" in event["que"].lower() for event in samples)
    # Legible: el nombre con que EMMA enseña la lectura de una analítica (no el de LOINC en
    # inglés) y las cifras con los decimales y la unidad del indicador, no los de la media.
    before = lymphocytes["preflight"]
    figure = display.number(first["value"], display.DECIMALS["lymphocytes"])
    mean = display.number(before["mean"], display.DECIMALS["lymphocytes"])
    assert event["que"].startswith(f"{labs.names()['lymphocytes']}: {figure} ×10³/µL en R+")
    assert f"media prevuelo propia {mean} ×10³/µL" in event["que"]
    assert f"{display.number(abs(first['delta_pct']), 1)} % por debajo" in event["que"]
    for told_event in samples:
        assert "[#/volume]" not in told_event["que"] and "10*3/uL" not in told_event["que"]
        assert not re.search(r"\d\.\d", told_event["que"]), "coma decimal, no punto"
        assert not re.search(r"\d,\d{3}", told_event["que"]), "estos recuentos llevan uno o dos"
    # Leer dos veces no repite ni cambia nada.
    again = timeline.chronicle(
        store, "crew-01", status, timeline.as_of(status, None, frozen_clock), START, DURATION)
    assert _facts(again, "postflight-sample") == samples


def test_earth_and_now_cut_the_postflight_samples(frozen_clock: dt.datetime) -> None:
    store, launch, last = _inspiration4()
    landing = launch + 3 * DAY
    # Tierra, con el corte una semana después del regreso: solo las tomas de R+1.
    cut = landing + 7 * DAY
    received = {"data": {"reference_time": cut.isoformat()}}
    earth = _facts(timeline.chronicle(
        store, "crew-01", received, timeline.as_of(received, cut, frozen_clock), START,
        DURATION, cut), "postflight-sample")
    assert earth and all(" en R+1;" in event["que"] for event in earth)
    # Sin corte, pero con el ahora antes de la última toma: lo posterior no ha pasado.
    before = {"data": {"reference_time": (last - DAY).isoformat()}}
    now = _facts(timeline.chronicle(
        store, "crew-01", before, timeline.as_of(before, None, frozen_clock), START, DURATION),
        "postflight-sample")
    assert now and all(dt.datetime.fromisoformat(event["at"]) <= last - DAY for event in now)
    # Sin prevuelo no hay rango: un tripulante sin el hemograma no gana nada.
    assert not _facts(timeline.chronicle(
        store, "crew-09", received, timeline.as_of(received, None, frozen_clock), START,
        DURATION), "postflight-sample")


SHORT = 10  # una misión de diez días: el regreso, al acabar (no es Inspiration4)
LANDING = dt.datetime.combine(START, dt.time(0, tzinfo=dt.UTC)) + SHORT * DAY


def _dense_postflight() -> tuple[Any, list[Any]]:
    """Un pulso con prevuelo propio (60, 62, 64) y, tras el regreso, una serie densa.

    R+1: sesenta tomas, una cada diez minutos, de 60 a 69 (la mitad dentro del rango prevuelo).
    R+5: una sola, 66. R+8: tres, las tres de 63. Lecturas del ledger, no de Inspiration4.
    """
    launch = LANDING - SHORT * DAY
    readings = [
        *(observation("heart-rate", value, launch - days * DAY + 8 * HOUR, "crew-01",
                      routes._SIMULATOR_SOURCE)
          for days, value in ((3, 60.0), (2, 62.0), (1, 64.0))),
        *(observation("heart-rate", 60.0 + step % 10, LANDING + DAY + 10 * step * MINUTE,
                      "crew-01", routes._SIMULATOR_SOURCE)
          for step in range(60)),
        observation("heart-rate", 66.0, LANDING + 5 * DAY, "crew-01", routes._SIMULATOR_SOURCE),
        *(observation("heart-rate", 63.0, LANDING + 8 * DAY + hour * HOUR, "crew-01",
                      routes._SIMULATOR_SOURCE)
          for hour in range(3)),
    ]
    store = new_store()
    seed_from_simulator(store, readings, identity_for(routes._SIMULATOR_SOURCE))
    return store, readings


def _postflight(store: Any, now: dt.datetime, clock: dt.datetime) -> list[dict[str, Any]]:
    status = {"data": {"reference_time": now.isoformat()}}
    chronicle = timeline.chronicle(
        store, "crew-01", status, timeline.as_of(status, None, clock), START, SHORT)
    return [event for event in chronicle["events"] if event["tipo"] == "posvuelo"]


def test_many_postflight_samples_of_a_day_are_one_event_with_their_count_and_range(
    frozen_clock: dt.datetime,
) -> None:
    store, readings = _dense_postflight()
    told = _postflight(store, readings[-1].effective, frozen_clock)
    # Un evento por indicador y día, el día que el panel da a cada toma (su R+), sin tope: las
    # sesenta de R+1 van juntas. El día con una sola se cuenta como siempre.
    panel = recovery.recovery(store.query("crew-01"), LANDING - SHORT * DAY, LANDING)
    days = sorted({sample["days_after_landing"] for sample in panel[0]["postflight"]})
    assert days == [1, 5, 8]
    assert [event["clave"] for event in told] == [f"recovery:heart-rate:R+{day}" for day in days]
    assert [event["fact"] for event in told] == [
        "postflight-day", "postflight-sample", "postflight-day"]
    # El pulso, con su nombre en español de EMMA (`ingest/names_es.py`), como en el resto de
    # las frases.
    name = "Frecuencia cardiaca"
    assert [event["que"] for event in told] == [
        f"{name}: 60 tomas en R+1, entre 60 y 69 /min; 30 dentro y 30 fuera de su rango "
        "prevuelo 60–64 /min; media prevuelo propia 62 /min (3 tomas)",
        f"{name}: 66 /min en R+5; 6,5 % por encima de la media prevuelo propia 62 /min "
        "(3 tomas); fuera de su rango prevuelo 60–64 /min",
        f"{name}: 3 tomas en R+8, todas de 63 /min; todas dentro de su rango prevuelo "
        "60–64 /min; media prevuelo propia 62 /min (3 tomas)",
    ]
    # Cada día, en su última toma; en la etapa posvuelo, sin nivel ni veredicto.
    assert [event["at"] for event in told] == [
        (LANDING + DAY + 590 * MINUTE).isoformat(), (LANDING + 5 * DAY).isoformat(),
        (LANDING + 8 * DAY + 2 * HOUR).isoformat()]
    assert {event["stage"] for event in told} == {"postflight"}
    assert all(event["level"] is None for event in told)
    assert all("lecturas del ledger" in event["fuente"] for event in told)


def test_a_postflight_day_only_counts_the_samples_already_taken(
    frozen_clock: dt.datetime,
) -> None:
    store, _ = _dense_postflight()
    # A media mañana de R+1: treinta tomas, en la última que ya pasó, y la misma clave que
    # tendrá el día entero.
    [event] = _postflight(store, LANDING + DAY + 295 * MINUTE, frozen_clock)
    assert event["clave"] == "recovery:heart-rate:R+1"
    assert event["at"] == (LANDING + DAY + 290 * MINUTE).isoformat()
    assert event["que"].startswith(
        "Frecuencia cardiaca: 30 tomas en R+1, entre 60 y 69 /min; 15 dentro y 15 fuera de su "
        "rango")
    # Con otro prevuelo (50 y 52), las tres de R+8 caen fuera: «todas fuera».
    lower = new_store()
    launch = LANDING - SHORT * DAY
    seed_from_simulator(lower, [
        *(observation("heart-rate", value, launch - days * DAY, "crew-01",
                      routes._SIMULATOR_SOURCE) for days, value in ((2, 50.0), (1, 52.0))),
        *(observation("heart-rate", 63.0 + hour, LANDING + 8 * DAY + hour * HOUR, "crew-01",
                      routes._SIMULATOR_SOURCE) for hour in range(3)),
    ], identity_for(routes._SIMULATOR_SOURCE))
    [outside] = _postflight(lower, LANDING + 9 * DAY, frozen_clock)
    assert outside["que"] == (
        "Frecuencia cardiaca: 3 tomas en R+8, entre 63 y 65 /min; todas fuera de su rango "
        "prevuelo "
        "50–52 /min; media prevuelo propia 51 /min (2 tomas)")


# --------------------------------------------------------------------------- #
# Qué depende de este dato
# --------------------------------------------------------------------------- #


def test_what_depends_on_a_reading() -> None:
    result = timeline.depends_on("heart-rate")
    ids = {item["id"] for item in result["affected"]}
    assert {"dominio:cardiovascular", "linea-base:heart-rate", "proyeccion:heart-rate",
            "region:heart"} <= ids
    assert any(item.startswith("contramedida:") for item in ids)
    assert all(item["mode"] in ("auto", "humano") for item in result["affected"])
    assert result["map_errors"] == []


def test_depends_endpoint_rejects_unknown_keys_and_restores_the_map(client: TestClient) -> None:
    cascade = polaris.load("cascada_mapa")
    before = (cascade.MAPA, cascade.DEPENDIENTES)
    assert client.get("/api/timeline/depends/no-existe").status_code == 404
    assert client.get("/api/timeline/depends/heart-rate").status_code == 200
    # Por identidad: dos mapas de EMMA construidos aparte son iguales por valor.
    assert cascade.MAPA is before[0] and cascade.DEPENDIENTES is before[1]


# --------------------------------------------------------------------------- #
# Por la API, con una misión simulada entera (lentas: al final)
# --------------------------------------------------------------------------- #


def test_week_endpoint_counts_from_the_simulated_mission_not_from_the_wall_clock(
    client: TestClient, frozen_clock: dt.datetime,
) -> None:
    # Sin lecturas no hay otro ahora que el reloj real, y la respuesta lo dice.
    for path in ("/api/timeline/week", "/api/timeline/chronicle"):
        empty = client.get(path).json()
        assert (empty["as_of"], empty["as_of_source"]) == (frozen_clock.isoformat(), "clock")
        assert "reloj real" in empty["as_of_basis"]
    assert client.get("/api/timeline/chronicle").json()["events"] == []

    client.post("/api/simulate", params={"scenario": "nominal", "days": 30})
    body = client.get("/api/timeline/week", params={"days": 60}).json()
    assert body["days"] == 31, "la ventana tiene tope"
    # La misión simulada acaba en noviembre de 2026 y el reloj está en 2031: la ventana es la
    # de la misión, y por eso entran los horizontes firmados a cuatro semanas de su último dato.
    now = dt.datetime.fromisoformat(body["as_of"])
    assert body["as_of_source"] == "data" and now.date() == START + 29 * DAY
    assert body["items"], "con el reloj real no entraría ninguno"
    assert all(now <= dt.datetime.fromisoformat(item["vence"]) <= now + 31 * DAY
               for item in body["items"])
    assert str(now.year) in body["block"] and str(frozen_clock.year) not in body["block"]


def test_the_chronicle_comes_from_the_ledger_and_the_state_with_stable_keys(
    alerting: tuple[TestClient, dict],  # noqa: F811
    frozen_clock: dt.datetime,
) -> None:
    client, status = alerting
    alert = status["alerts"][0]
    reference = status["data"]["reference_time"]
    body = {"domain": alert["domain"], "level": alert["level"], "reference_time": reference}
    assert client.post("/api/alerts/acknowledge",
                       json={**body, "acknowledged_by": "comandante"}).status_code == 201
    assert client.post("/api/alerts/resolution", json={
        **body, "state": "en_arreglo", "note": "", "declared_by": "CMO"}).status_code == 201
    assert client.post("/api/safe-mode", json={
        "active": True, "reason": "prueba", "declared_by": "CMO"}).status_code == 201

    first = client.get("/api/timeline/chronicle").json()
    # El ahora es el del estado, no el reloj (parado en 2031).
    assert (first["as_of"], first["as_of_source"]) == (reference, "data")
    facts = [event["fact"] for event in first["events"]]
    assert facts.count("alert-acknowledged") == facts.count("alert-in-progress") == 1
    assert "safe-mode-on" in facts and facts.count("phase-change") == 2
    # El inicio de la alerta sale del estado: el mismo `onset` que enseña su detalle.
    [onset] = [event for event in first["events"]
               if event["fact"] == "alert-onset" and event["level"] == alert["level"]
               and alert["domain"] in event["que"]]
    assert onset["at"] == alert["detail"]["onset"] and alert["rules_version"] in onset["fuente"]
    # Lo firmado se fecha con el estado sobre el que se decidió; su clave es el asiento.
    signed = [event for event in first["events"] if event["clave"].startswith("ledger:")]
    assert {event["at"] for event in signed if event["time_basis"] == "data"} == {reference}
    assert len({event["clave"] for event in first["events"]}) == len(first["events"])
    assert any("reconocida" in line and "comandante" in line for line in first["lines"])
    # Leer dos veces no repite ni cambia nada.
    assert client.get("/api/timeline/chronicle").json() == first
    # A Tierra, con un corte anterior a todo, no le ha llegado nada: ni la alerta ni lo firmado.
    earth = client.get(
        "/api/timeline/chronicle", params={"until": "2020-01-01T00:00:00+00:00"}).json()
    assert earth["events"] == [] and earth["as_of_source"] == "cut"
    assert client.get("/api/timeline/chronicle", params={"until": "2026-12-01T00:00:00"}
                      ).status_code == 422, "un corte sin zona horaria es ambiguo"


def test_the_chronicle_and_the_recovery_panel_tell_the_same_postflight(
    client: TestClient, frozen_clock: dt.datetime,
) -> None:
    assert client.post("/api/replay/inspiration4").status_code == 201
    panel = client.get("/api/replay/recovery", params={"subject": "crew-02"}).json()
    chronicle = client.get("/api/timeline/chronicle", params={"subject": "crew-02"}).json()
    samples = _facts(chronicle, "postflight-sample")
    assert sorted(event["clave"] for event in samples) == sorted(
        f"recovery:{item['key']}:R+{sample['days_after_landing']}"
        for item in panel["indicators"] for sample in item["postflight"])
    postflight = next(stage for stage in chronicle["stages"] if stage["key"] == "postflight")
    assert postflight["count"] >= len(samples) > 0
    # El panel no cambia: sigue con el nombre del catálogo (la crónica es la que se lee en
    # español).
    assert all(item["display"].endswith("by Automated count") for item in panel["indicators"])


def test_the_chronicle_links_its_milestones_to_the_moments_of_the_body(
    client: TestClient, frozen_clock: dt.datetime,
) -> None:
    """Pulsar un hito de la crónica elige ese momento en «Cuerpo»: la clave que lleva un hecho
    es la de un momento que `/anatomy/state` ofrece, con su mismo rótulo, y a Tierra no le llega
    ninguno (no monta «Cuerpo» y sus momentos no se dan con corte)."""
    assert client.post("/api/replay/inspiration4").status_code == 201
    moments = client.get("/api/anatomy/state", params={"subject": "crew-02"}).json()["moments"]
    offered = {item["key"]: item["display"] for item in moments["items"]}
    chronicle = client.get("/api/timeline/chronicle", params={"subject": "crew-02"}).json()
    linked = [event for event in chronicle["events"] if event["moment"] is not None]
    assert all(offered[event["moment"]["key"]] == event["moment"]["display"] for event in linked)
    # El lanzamiento (cambio a adaptación) es el fin del prevuelo.
    assert any(event["fact"] == "phase-change" and event["moment"]["key"] == "preflight"
               for event in linked)
    # Cada hito posvuelo que se ofrece tiene en la crónica al menos un hecho que lo pide, y un
    # hecho enlaza con el primero que ya lo cuenta: ninguno pedido antes que él.
    milestones = {item["key"]: dt.datetime.fromisoformat(item["until"])
                  for item in moments["items"] if item["kind"] == "postflight_milestone"}
    told = [event for event in linked if event["fact"].startswith("postflight")]
    assert told, "la reproducción de Inspiration4 tiene tomas posvuelo"
    assert {event["moment"]["key"] for event in told} == set(milestones)
    for event in told:
        at = dt.datetime.fromisoformat(event["at"])
        assert milestones[event["moment"]["key"]] >= at
        assert not any(at <= until < milestones[event["moment"]["key"]]
                       for until in milestones.values())
    # La toma de hoy (R+82, la última) no la cuenta ningún momento pasado.
    assert any(event["fact"].startswith("postflight") and event["moment"] is None
               for event in chronicle["events"])
    earth = client.get("/api/timeline/chronicle", params={
        "subject": "crew-02", "until": chronicle["as_of"]}).json()
    assert earth["events"] and all(event["moment"] is None for event in earth["events"])


def test_the_chronicle_moments_come_from_the_readings_the_status_analyses(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Los momentos con que la crónica enlaza sus hechos salen de las lecturas que analiza el
    estado: una lectura descriptiva no entra (§5.37.13; antes se copiaba aquí el filtro de
    `routes._assess`)."""
    from app import anatomy
    from app.ingest.codes import DESCRIPTIVE_ONLY

    client.post("/api/simulate", params={"scenario": "arrhythmia", "days": 20})
    status = client.get("/api/status").json()
    reference = dt.datetime.fromisoformat(status["data"]["reference_time"])
    response = client.post("/api/observations", json={
        "key": "grip-strength-right", "value": 40.0, "subject": "crew-01",
        "effective": (reference - dt.timedelta(hours=1)).isoformat()})
    assert response.status_code == 201, response.text
    real = anatomy.moments
    seen: list[list[Any]] = []

    def spy(observations: Any, *args: Any) -> dict[str, Any]:
        seen.append(list(observations))
        return real(observations, *args)

    monkeypatch.setattr(anatomy, "moments", spy)
    client.get("/api/timeline/chronicle")
    assert len(seen) == 1 and seen[0]
    assert not [item for item in seen[0] if item.key in DESCRIPTIVE_ONLY]
