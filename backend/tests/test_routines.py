"""Frescura de las medidas periódicas (Polaris `estado_rutina`) con datos de EMMA. Sin red.

Una medida que deja de llegar no mueve la línea base: sin esto, un pulsómetro sin batería se
parecería a "todo normal".
"""

from __future__ import annotations

import copy
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app import routines, text_guard
from app.analysis.risk import RiskEngine, active_solar_event
from app.api import routes
from app.environment.donki import EventType, SolarEvent
from app.environment.donki import Severity as SolarSeverity
from app.ingest.fhir import observation

T0 = dt.datetime(2026, 11, 10, 12, tzinfo=dt.UTC)


def _state(result: dict, key: str) -> str:  # type: ignore[type-arg]
    [found] = [item for item in result["routines"] if item["key"] == key]
    state: str = found["state"]
    return state


def _hr(hours_ago: float, confidence: float = 1.0):  # type: ignore[no-untyped-def]
    return observation("heart-rate", 60.0, T0 - dt.timedelta(hours=hours_ago), "crew-01", "x",
                       confidence=confidence)


def test_every_routine_is_a_catalogue_indicator_with_a_declared_basis() -> None:
    data = routines.load()
    assert data["routines"] and data["default_basis"] == "parámetro de diseño"


def test_the_edges_of_one_and_two_periods() -> None:
    # Pulso: periodo de 6 h.
    assert _state(routines.evaluate([_hr(6)], now=T0), "heart-rate") == "al-dia"  # justo en P
    assert _state(routines.evaluate([_hr(7)], now=T0), "heart-rate") == "atrasada"
    assert _state(routines.evaluate([_hr(12)], now=T0), "heart-rate") == "rota"  # justo en 2P
    assert _state(routines.evaluate([], now=T0), "heart-rate") == "nunca-corrio"


def test_a_low_confidence_reading_is_a_run_but_not_a_success() -> None:
    # Llegó hace 1 h, pero con confianza baja; la última buena es de hace 13 h: rota.
    result = routines.evaluate([_hr(1, confidence=0.2), _hr(13)], now=T0)
    assert _state(result, "heart-rate") == "rota"


def test_now_is_the_latest_reading_not_the_wall_clock() -> None:
    # Datos del futuro respecto al reloj (simulador): siguen al día frente a su propio "ahora".
    future = observation("heart-rate", 60.0, T0 + dt.timedelta(days=400), "crew-01", "x")
    assert _state(routines.evaluate([future]), "heart-rate") == "al-dia"


def test_the_endpoint_reads_the_signed_series_and_honours_the_ground_cut(
    client: TestClient,
) -> None:
    client.post("/api/simulate", params={"scenario": "nominal", "days": 10})
    body = client.get("/api/timeline/routines").json()
    assert body["counts"].get("al-dia", 0) > 0
    assert _state(body, "heart-rate") == "al-dia"
    assert body["now_source"] == "data"
    # Tierra, con un corte muy posterior a la última lectura que tiene: todo lo continuo, roto.
    late = (dt.datetime.fromisoformat(body["now"]) + dt.timedelta(days=3)).isoformat()
    cut = client.get("/api/timeline/routines", params={"until": late}).json()
    assert _state(cut, "heart-rate") == "rota"
    assert (cut["now"], cut["now_source"]) == (late, "cut")

    # Una sola lectura mal fechada no se convierte en el ahora: el de las rutinas es el del
    # estado, que la aparta. Con la última lectura a secas, todo lo demás quedaba roto para
    # siempre (el ledger no borra).
    stray = client.post("/api/observations", json={
        "subject": "crew-01", "key": "heart-rate", "value": 60.0, "source": "manual",
        "effective": dt.datetime(2099, 1, 1, tzinfo=dt.UTC).isoformat()})
    assert stray.status_code == 201, stray.text
    assert client.get("/api/timeline/routines").json() == body


def test_without_readings_the_clock_is_the_only_now_and_the_answer_says_so(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes, "_now", lambda: T0)
    body = client.get("/api/timeline/routines").json()
    assert (body["now"], body["now_source"]) == (T0.isoformat(), "clock")
    assert set(body["counts"]) == {"nunca-corrio"}


# --------------------------------------------------------------------------- #
# Más a menudo mientras dura un evento solar (2026-11-02)
# --------------------------------------------------------------------------- #


def _solar(at: dt.datetime, severity: str = "high", event_id: str = "SEP-PRUEBA") -> SolarEvent:
    return SolarEvent(
        event_id=event_id, event_type=EventType.SEP, time=at, severity=SolarSeverity(severity),
        instruments=(), linked_event_ids=(), flare_class=None,
        link=f"https://example.invalid/{event_id}",
    )


def _routine(result: dict, key: str) -> dict:  # type: ignore[type-arg]
    [found] = [item for item in result["routines"] if item["key"] == key]
    return found  # type: ignore[no-any-return]


def test_without_an_event_nothing_changes_and_each_period_says_it_is_the_design_one() -> None:
    readings = [_hr(3)]
    plain = routines.evaluate(readings, now=T0)
    assert plain == routines.evaluate(readings, now=T0, event=None)
    assert plain["active_event"] is None and plain["event_note"] is None
    assert plain["event_over_note"] == routines.EVENT_OVER_NOTE
    assert text_guard.check(routines.EVENT_OVER_NOTE) == []
    data = routines.load()
    # El orden y los periodos, los de `routines.json`.
    assert [item["key"] for item in plain["routines"]] == list(data["routines"])
    for item in plain["routines"]:
        assert item["period_hours"] == item["design_period_hours"]
        assert item["period_hours"] == data["routines"][item["key"]]["period_hours"]
        assert item["basis"] == data["default_basis"]
        assert (item["period_source"], item["event_id"], item["priority"], item["period_note"]) == (
            routines.DESIGN, None, None, None)
    assert _state(plain, "heart-rate") == "al-dia"


def test_during_an_event_the_key_routines_use_their_shorter_period_and_go_first() -> None:
    event = _solar(T0 - dt.timedelta(hours=5))
    # Pulso de hace 3 h: al día con 6 h; atrasado con las 2 h del evento.
    result = routines.evaluate([_hr(3)], now=T0, event=event)
    during = routines.load()["during_event"]
    heart = _routine(result, "heart-rate")
    assert heart["state"] == "atrasada"
    assert (heart["period_hours"], heart["design_period_hours"]) == (
        during["routines"]["heart-rate"]["period_hours"], 6)
    assert (heart["period_source"], heart["event_id"]) == (routines.EVENT, "SEP-PRUEBA")
    assert heart["basis"] == during["basis"]
    assert heart["period_note"] == (
        "periodo acortado durante el evento solar SEP-PRUEBA: de 6 h a 2 h")
    # Lo que no está en `during_event` sigue con su periodo y su base de siempre.
    sleep = _routine(result, "sleep-duration")
    assert (sleep["period_source"], sleep["period_hours"], sleep["priority"]) == (
        routines.DESIGN, 24, None)
    # Solo orden: las del evento primero, por prioridad; el resto en el orden de siempre.
    ranked = sorted(during["routines"], key=lambda key: during["routines"][key]["priority"])
    keys = [item["key"] for item in result["routines"]]
    assert keys[: len(ranked)] == ranked and keys[0] == "absorbed-dose-rate"
    rest = [key for key in routines.load()["routines"] if key not in during["routines"]]
    assert keys[len(ranked):] == rest
    assert result["active_event"] == event.to_dict()
    assert result["event_note"] is not None and "SEP-PRUEBA" in result["event_note"]
    assert result["event_over_note"] is None
    # Las mismas rutinas: nada se añade ni se quita.
    assert sum(result["counts"].values()) == len(routines.load()["routines"])


def test_an_event_after_the_now_has_not_shortened_anything_yet() -> None:
    # El corte de Tierra (o datos anteriores al reloj real): el evento todavía no ha empezado.
    later = _solar(T0 + dt.timedelta(minutes=1))
    assert routines.evaluate([_hr(3)], now=T0, event=later) == routines.evaluate(
        [_hr(3)], now=T0)
    # Justo en su instante, ya cuenta.
    at_now = routines.evaluate([_hr(3)], now=T0, event=_solar(T0))
    assert _routine(at_now, "heart-rate")["period_source"] == routines.EVENT


def test_the_event_is_the_one_the_state_chooses() -> None:
    # Mismo criterio que el riesgo: un evento de gravedad «elevada» no es un evento activo.
    elevated = _solar(T0 - dt.timedelta(hours=1), severity="elevated")
    assert active_solar_event([elevated]) is None
    assert active_solar_event([]) is None and active_solar_event(None) is None
    old = _solar(T0 - dt.timedelta(hours=9), event_id="SEP-VIEJO")
    new = _solar(T0 - dt.timedelta(hours=2), event_id="SEP-NUEVO", severity="severe")
    events = [old, new, elevated]
    assert active_solar_event(events) == RiskEngine._active_solar_event(events) == new


def test_rota_during_an_event_is_still_not_an_alert_and_the_texts_pass_the_guard() -> None:
    result = routines.evaluate([], now=T0, event=_solar(T0 - dt.timedelta(hours=1)))
    texts = [result["event_note"], routines.load()["during_event"]["basis"]]
    texts += [item["period_note"] for item in result["routines"] if item["period_note"]]
    assert len(texts) == 2 + len(routines.load()["during_event"]["routines"])
    for text in texts:
        assert text_guard.check(text) == [], text
    # La respuesta no lleva nivel, alerta ni riesgo: solo estados de rutina.
    assert set(result) == {
        "now", "counts", "routines", "active_event", "active_trigger", "event_note",
        "event_over_note"}


def test_an_event_period_has_to_shorten_the_usual_one_and_priorities_are_unique() -> None:
    data = copy.deepcopy(routines.load())
    data["during_event"]["routines"]["heart-rate"]["period_hours"] = 6
    with pytest.raises(ValueError, match="acortar"):
        routines._check_during_event(data)
    data = copy.deepcopy(routines.load())
    data["during_event"]["routines"]["heart-rate"]["priority"] = 1
    with pytest.raises(ValueError, match="prioridad"):
        routines._check_during_event(data)
    data = copy.deepcopy(routines.load())
    data["during_event"]["routines"]["no-existe"] = {"period_hours": 1, "priority": 99}
    with pytest.raises(ValueError, match="no es una rutina"):
        routines._check_during_event(data)


def test_the_endpoint_uses_the_state_event_and_honours_the_ground_cut(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.post("/api/simulate", params={"scenario": "spe-event", "days": 10})
    plain = client.get("/api/timeline/routines").json()
    assert plain["active_event"] is None  # sin red y sin caché de DONKI: ningún evento
    now = dt.datetime.fromisoformat(plain["now"])
    event = _solar(now - dt.timedelta(hours=3), event_id="SEP-ENDPOINT")
    monkeypatch.setattr(
        routes, "_fetch_solar_events", lambda settings: ([event], ("hace 1 min", 60)))
    body = client.get("/api/timeline/routines").json()
    dose = _routine(body, "absorbed-dose-rate")
    assert (dose["period_source"], dose["event_id"]) == (routines.EVENT, "SEP-ENDPOINT")
    assert body["routines"][0]["key"] == "absorbed-dose-rate"
    assert body["active_event"]["event_id"] == "SEP-ENDPOINT"
    # Tierra, con un corte anterior al evento: para ella todavía no hay periodo acortado.
    cut = (event.time - dt.timedelta(hours=1)).isoformat()
    ground = client.get("/api/timeline/routines", params={"until": cut}).json()
    assert ground["active_event"] is None
    # Sin el evento de DONKI, lo que acorta en `spe-event` es la dosis de a bordo, que ya está por
    # encima de su límite de peligro (2026-11-04, `test_spe_demo_offline.py`): no el evento.
    assert ground["active_trigger"]["kind"] == routines.DOSE_TRIGGER
    assert {item["event_id"] for item in ground["routines"]} == {None}
    # Con un corte posterior, sí.
    after = (event.time + dt.timedelta(hours=1)).isoformat()
    later = client.get("/api/timeline/routines", params={"until": after}).json()
    assert _routine(later, "absorbed-dose-rate")["period_source"] == routines.EVENT
    # `/waiting` juzga con el evento de su propio estado, que es el mismo.
    status = client.get("/api/status").json()
    assert status["active_solar_event"]["event_id"] == "SEP-ENDPOINT"
    assert client.get("/api/timeline/waiting").status_code == 200
