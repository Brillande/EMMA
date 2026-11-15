"""Recuperación posvuelo: cuándo vuelve y si vuelve (estado del arte §5.37.7).

La conversación de ideación preguntaba «¿cuánto tarda en volver al baseline? ¿Vuelve
completamente?». Estas pruebas fijan lo que EMMA contesta con las tomas que hay: el primer R+
dentro del rango prevuelo propio, si las siguientes se mantienen dentro y «sin volver» si la
última sigue fuera; sin tasa inventada ni veredicto, y sin tocar ninguna alerta.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi.testclient import TestClient

from app.analysis import recovery
from app.api import routes
from app.api.routes import identity_for, new_store, reset_store
from app.core.storage import seed_from_simulator
from app.ingest.fhir import observation

DAY = dt.timedelta(days=1)
LAUNCH = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)  # `Settings.mission_start` por defecto
LANDING = LAUNCH + 180 * DAY  # fin de la misión configurada: no es Inspiration4


def _samples(*taken: tuple[int, bool]) -> list[dict[str, Any]]:
    return [
        {"days_after_landing": day, "within_preflight_range": within} for day, within in taken
    ]


def test_out_then_back_and_held_says_the_first_day_back_and_how_many_followed() -> None:
    back = recovery.return_to_range(_samples((1, False), (45, True), (82, True), (194, True)))
    assert back["state"] == "within"
    assert (back["first_within_day"], back["held"], back["later_samples"]) == (45, True, 2)
    assert (back["within_since_day"], back["last_day"]) == (45, 194)
    assert back["text"] == (
        "Fuera de su rango prevuelo en la primera toma posvuelo; vuelve dentro en R+45; se "
        "mantiene dentro en las 2 tomas siguientes, hasta R+194.")


def test_back_and_out_again_is_without_return_when_the_last_sample_is_out() -> None:
    # Linfocitos de crew-01 en Inspiration4: fuera, dentro, dentro, fuera.
    back = recovery.return_to_range(_samples((1, False), (45, True), (82, True), (194, False)))
    assert back["state"] == "not-back"
    assert (back["first_within_day"], back["held"], back["within_since_day"]) == (45, False, None)
    assert back["text"] == (
        "Fuera de su rango prevuelo en la primera toma posvuelo; vuelve dentro en R+45; no se "
        "mantiene: una toma fuera después, en R+194; la última toma, R+194, sigue fuera: sin "
        "volver.")


def test_in_out_and_in_again_says_since_when_it_is_inside() -> None:
    # Neutrófilos de crew-01: dentro en la primera, fuera en dos, dentro en la última.
    back = recovery.return_to_range(_samples((1, True), (45, False), (82, False), (194, True)))
    assert back["state"] == "back-again"
    assert (back["first_within_day"], back["held"], back["within_since_day"]) == (1, False, 194)
    assert back["text"] == (
        "Dentro de su rango prevuelo en la primera toma posvuelo, R+1; no se mantiene: 2 tomas "
        "fuera después, entre R+45 y R+82; dentro de nuevo en la última toma, R+194.")


def test_never_inside_is_without_return() -> None:
    back = recovery.return_to_range(_samples((1, False), (45, False), (82, False)))
    assert back["state"] == "not-back" and back["first_within_day"] is None
    assert back["held"] is None and back["within_since_day"] is None
    assert back["text"] == (
        "Sin volver: ninguna de sus 3 tomas posvuelo (R+1 a R+82) cae dentro de su rango "
        "prevuelo.")
    [single] = [recovery.return_to_range(_samples((3, False)))["text"]]
    assert single == "Sin volver: su única toma posvuelo, R+3, cae fuera de su rango prevuelo."


def test_a_single_sample_inside_holds_nothing_and_says_so() -> None:
    back = recovery.return_to_range(_samples((2, True)))
    assert back["state"] == "within" and back["held"] is None and back["later_samples"] == 0
    assert back["text"] == (
        "Dentro de su rango prevuelo en la primera toma posvuelo, R+2; no hay tomas posteriores.")
    one_more = recovery.return_to_range(_samples((2, False), (5, True), (9, True)))
    assert one_more["text"].endswith("se mantiene dentro en la toma siguiente, hasta R+9.")


def test_many_samples_out_on_one_day_are_counted_on_that_day() -> None:
    back = recovery.return_to_range(_samples((1, True), (1, False), (1, False), (1, False)))
    assert back["text"].endswith("no se mantiene: 3 tomas fuera después, en R+1; la última "
                                 "toma, R+1, sigue fuera: sin volver.")


def test_several_samples_on_one_day_are_counted_not_contradicted() -> None:
    # Fuera, fuera, dentro, fuera, dentro, dentro: todas en R+1. Con días solos la frase decía
    # «hasta R+1; vuelve dentro en R+1».
    back = recovery.return_to_range(_samples(
        (1, False), (1, False), (1, True), (1, False), (1, True), (1, True)))
    assert back["state"] == "back-again"
    assert back["text"] == (
        "Fuera de su rango prevuelo en las 2 primeras tomas posvuelo; vuelve dentro en R+1; no "
        "se mantiene: una toma fuera después, en R+1; dentro de nuevo en las 2 últimas tomas, "
        "desde R+1.")


def test_no_sentence_names_a_rate_or_a_verdict() -> None:
    patterns = [
        _samples((1, False), (45, True), (82, True)),
        _samples((1, True), (45, False)),
        _samples((1, False)),
        _samples((1, True), (45, False), (82, True)),
    ]
    for taken in patterns:
        text = recovery.return_to_range(taken)["text"].lower()
        assert "recuperad" not in text and "tasa" not in text and "normal" not in text, text


def _seed(readings: list[Any]) -> None:
    store = new_store()
    seed_from_simulator(store, readings, identity_for(routes._SIMULATOR_SOURCE))
    reset_store(store)


def _reading(key: str, value: float, when: dt.datetime) -> Any:
    return observation(key, value, when, "crew-01", routes._SIMULATOR_SOURCE)


def test_an_indicator_without_a_preflight_range_is_said_not_supposed(client: TestClient) -> None:
    _seed([
        # Pulso: tres tomas prevuelo, rango 60–64; tras el regreso, fuera y luego dentro.
        *(_reading("heart-rate", value, LAUNCH - days * DAY)
          for days, value in ((3, 60.0), (2, 62.0), (1, 64.0))),
        _reading("heart-rate", 70.0, LANDING + DAY),
        _reading("heart-rate", 63.0, LANDING + 7 * DAY),
        # saturation: una sola toma prevuelo. Temperatura: ninguna. Las dos con posvuelo.
        _reading("oxygen-saturation", 98.0, LAUNCH - DAY),
        _reading("oxygen-saturation", 97.0, LANDING + DAY),
        _reading("oxygen-saturation", 96.0, LANDING + 7 * DAY),
        _reading("body-temperature", 36.8, LANDING + 2 * DAY),
        # Frecuencia respiratoria: sin posvuelo, no sale en ninguna lista.
        _reading("respiratory-rate", 14.0, LAUNCH - DAY),
    ])
    body = client.get("/api/replay/recovery", params={"subject": "crew-01"}).json()
    [pulse] = body["indicators"]
    assert pulse["key"] == "heart-rate"
    assert pulse["return_to_range"]["text"] == (
        "Fuera de su rango prevuelo en la primera toma posvuelo; vuelve dentro en R+7; no hay "
        "tomas posteriores.")
    unranged = {item["key"]: item for item in body["without_preflight_range"]}
    assert set(unranged) == {"oxygen-saturation", "body-temperature"}
    saturation = unranged["oxygen-saturation"]
    assert (saturation["preflight_samples"], saturation["postflight_samples"]) == (1, 2)
    assert (saturation["first_day"], saturation["last_day"]) == (1, 7)
    assert saturation["return_to_range"] == {
        "state": "no-preflight-range",
        "text": "Sin rango prevuelo: una sola toma antes del lanzamiento, y EMMA pide 2 para un "
                "rango; sus 2 tomas posvuelo (R+1 a R+7) no se comparan.",
    }
    assert unranged["body-temperature"]["return_to_range"]["text"] == (
        "Sin rango prevuelo: ninguna toma antes del lanzamiento; su única toma posvuelo, R+2, no "
        "se compara.")
    # Sin rango no hay dentro ni fuera: ninguna toma comparada ni cifra de separación.
    assert "postflight" not in saturation and "preflight" not in saturation


def test_inspiration4_says_when_each_analyte_comes_back(client: TestClient) -> None:
    assert client.post("/api/replay/inspiration4").status_code == 201
    body = client.get("/api/replay/recovery", params={"subject": "crew-01"}).json()
    assert body["without_preflight_range"] == []
    assert "no es un veredicto" in body["basis"]
    for item in body["indicators"]:
        back = item["return_to_range"]
        days = [sample["days_after_landing"] for sample in item["postflight"]]
        inside = [sample["within_preflight_range"] for sample in item["postflight"]]
        # El primer R+ dentro es el de la primera toma dentro; «sin volver», si la última está
        # fuera; en la escala de días del propio panel.
        expected = next((day for day, ok in zip(days, inside, strict=True) if ok), None)
        assert back["first_within_day"] == expected, item["key"]
        assert back["last_day"] == days[-1]
        assert ("sin volver" in back["text"].lower()) == (not inside[-1]), item["key"]
    lymphocytes = next(item for item in body["indicators"] if item["key"] == "lymphocytes")
    assert lymphocytes["return_to_range"]["state"] == "not-back"
    assert "vuelve dentro en R+45" in lymphocytes["return_to_range"]["text"]


def test_saying_the_return_changes_no_rule_and_no_alert(client: TestClient) -> None:
    """Descriptivo de verdad: leer la recuperación no escribe en el ledger, y ni la versión de
    las reglas ni las alertas dependen de ella."""
    client.post("/api/simulate", params={"scenario": "cardiovascular-deconditioning", "days": 30})
    assert client.post("/api/replay/inspiration4").status_code == 201
    before = client.get("/api/status").json()
    ledger = client.get("/api/audit").json()
    client.get("/api/replay/recovery", params={"subject": "crew-01"}).raise_for_status()
    after = client.get("/api/status").json()
    assert after["rules_version"] == before["rules_version"]
    assert after["alerts"] == before["alerts"]
    assert client.get("/api/audit").json() == ledger
