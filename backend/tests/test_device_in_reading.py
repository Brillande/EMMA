"""El dispositivo que envió una lectura, firmado con ella cuando existe.

Decisión del usuario, 2026-10-13.

El aviso de «sensor vinculado a otro tripulante» solo existía en la respuesta de la ingesta: el
identificador no se guardaba y nadie podía reconstruirlo después. Estas pruebas fijan lo que el
campo nuevo es y, sobre todo, lo que no puede romper: es OPCIONAL, una lectura sin dispositivo
se firma byte a byte como antes, y lo firmado antes del cambio sigue verificándose
(invariante 4).
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import logging
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import data_quality
from app.api.routes import get_store, identity_for, new_store, reset_store
from app.core.ledger import SALT_FIELD, Identity, canonical_bytes, sha256_hex
from app.core.storage import ObservationStore, _from_payload, _to_payload
from app.core.versioning import FINGERPRINTED, GUARDED, rules_version
from app.ingest import bindings
from app.ingest.fhir import Context, VitalObservation, from_device, observation

T = dt.datetime(2026, 9, 1, 8, 0, tzinfo=dt.UTC)
DEVICE = "aa:bb:cc:dd:ee:01"
# Ledger con tres lecturas, escrito con el código ANTERIOR a este cambio (commit 7c44dc3,
# exportado con `git archive` a una carpeta aparte) y guardado tal cual. Los hashes de
# contenido son los que firmó aquel código; el `.fhir.json` es lo que aquel código serializaba.
DATA = Path(__file__).parent / "data"
PRE_CHANGE_LEDGER = DATA / "readings_pre_device.db"
PRE_CHANGE_FHIR = DATA / "readings_pre_device.fhir.json"
PRE_CHANGE_HASHES = [
    "97da6bf12cefa80ee18f8f323e56ff8c17e4c21575f6c971fa1ddc95e300f915",
    "8b4fcb533930b9bb866e3bba19dcb930e27fb6fa02be69d8b5e23be1f75f2d32",
    "742a29e280a9b55acca68d45bd668cb2ba5f3dd432197ed6ffa87425bb05b629",
]


def _reading(device: str | None = None, minute: int = 0) -> VitalObservation:
    return observation(
        "heart-rate", 61.0, T + dt.timedelta(minutes=minute), "crew-02", "wearable-ble",
        context=Context.REST, confidence=0.4, device=device,
    )


@pytest.fixture
def pre_change(tmp_path: Path) -> Iterator[ObservationStore]:
    path = tmp_path / "emma.db"
    shutil.copyfile(PRE_CHANGE_LEDGER, path)
    store = ObservationStore.at(path)
    yield store
    store.engine.dispose()


def _signed_payloads(store: ObservationStore) -> list[dict[str, Any]]:
    return [dict(entry.payload) for entry in store.ledger.entries]


# --------------------------------------------------------------------------- #
# Lo ya firmado
# --------------------------------------------------------------------------- #


def test_readings_signed_before_the_field_still_verify(pre_change: ObservationStore) -> None:
    assert pre_change.verify_integrity().ok
    assert [e["content_hash"] for e in pre_change.audit_trail()] == PRE_CHANGE_HASHES
    readings = pre_change.query("crew-02") + pre_change.query("crew-01")
    assert len(readings) == 3
    assert all(obs.device is None for obs in readings)


def test_a_reading_without_device_serializes_byte_for_byte_as_before(
    pre_change: ObservationStore,
) -> None:
    """Con el código de ahora, cada lectura antigua produce los bytes que firmó el de antes."""
    payloads = _signed_payloads(pre_change)
    assert len(payloads) == 3
    for payload, signed in zip(payloads, PRE_CHANGE_HASHES, strict=True):
        obs = _from_payload(payload, dt.datetime.fromisoformat(payload["effective"]))
        again = _to_payload(obs)
        assert "device" not in again
        # Las mismas claves, en el mismo orden, y los mismos bytes canónicos bajo la misma sal.
        assert list(again) == [key for key in payload if key != SALT_FIELD]
        assert sha256_hex(canonical_bytes({**again, SALT_FIELD: payload[SALT_FIELD]})) == signed

    # Y el FHIR: lo que serializaba `main`, carácter a carácter (también el orden de claves).
    # Lo de antes se exporta con los URI de hoy: hasta 2026-11-02 eran `https://halo.mission/`
    # (el fixture los conserva tal cual se grabaron) y el FHIR los traduce al leer.
    expected = json.loads(
        PRE_CHANGE_FHIR.read_text(encoding="utf-8").replace(
            "https://halo.mission/", "https://emma.mission/")
    )
    readings = pre_change.query("crew-02") + pre_change.query("crew-01")
    assert [json.dumps(obs.to_fhir(), ensure_ascii=False) for obs in readings] == expected
    assert all("identifier" not in obs.to_fhir()["device"] for obs in readings)


def test_new_readings_chain_after_the_old_ones(
    pre_change: ObservationStore, tmp_path: Path
) -> None:
    ble = Identity.generate("otra-pasarela")
    pre_change.record_many([_reading(DEVICE, 5), _reading(None, 6)], ble)
    assert pre_change.verify_integrity().ok
    pre_change.engine.dispose()

    reopened = ObservationStore.at(tmp_path / "emma.db")
    try:
        assert reopened.verify_integrity().ok
        assert [e["content_hash"] for e in reopened.audit_trail()][:3] == PRE_CHANGE_HASHES
        assert [obs.device for obs in reopened.query("crew-02")] == [None, None, DEVICE, None]
    finally:
        reopened.engine.dispose()


# --------------------------------------------------------------------------- #
# El campo
# --------------------------------------------------------------------------- #


def test_the_device_is_signed_only_when_it_exists() -> None:
    without, with_device = _to_payload(_reading()), _to_payload(_reading(DEVICE))
    assert "device" not in without
    assert with_device == {**without, "device": DEVICE}
    # Es parte de lo firmado: otro dispositivo, otro hash.
    assert canonical_bytes(with_device) != canonical_bytes(without)
    assert canonical_bytes(with_device) != canonical_bytes(_to_payload(_reading("otro")))


def test_fhir_carries_it_as_a_logical_identifier_without_inventing_a_system() -> None:
    plain, tagged = _reading().to_fhir(), _reading(DEVICE).to_fhir()
    assert plain["device"] == {"display": "wearable-ble"}
    assert tagged["device"] == {"display": "wearable-ble", "identifier": {"value": DEVICE}}
    assert {**tagged, "device": plain["device"]} == plain
    assert VitalObservation.from_fhir(tagged).device == DEVICE
    assert VitalObservation.from_fhir(plain).device is None
    assert VitalObservation.from_fhir(tagged) == _reading(DEVICE)


@pytest.mark.parametrize("bad", ["", 7])
def test_an_empty_or_non_text_device_is_not_a_device(bad: object) -> None:
    with pytest.raises(ValueError, match="identificador de dispositivo"):
        _reading(bad)  # type: ignore[arg-type]


def test_from_device_tags_every_reading_or_none() -> None:
    batch = [_reading(), _reading(minute=1)]
    assert from_device(batch, None) is batch
    tagged = from_device(batch, DEVICE)
    assert [obs.device for obs in tagged] == [DEVICE, DEVICE]
    assert [obs.device for obs in batch] == [None, None]
    assert [(o.key, o.value, o.effective, o.confidence) for o in tagged] == [
        (o.key, o.value, o.effective, o.confidence) for o in batch
    ]


def test_the_device_survives_the_store_and_is_read_from_what_was_signed(tmp_path: Path) -> None:
    store = ObservationStore.at(tmp_path / "emma.db")
    try:
        store.record_many([_reading(DEVICE), _reading(None, 1)], Identity.generate("wearable-ble"))
        assert store.verify_integrity().ok
        assert [obs.device for obs in store.query("crew-02")] == [DEVICE, None]
        assert [("device" in p) for p in _signed_payloads(store)] == [True, False]
    finally:
        store.engine.dispose()


# --------------------------------------------------------------------------- #
# El aviso sobre lecturas ya firmadas: lógica pura
# --------------------------------------------------------------------------- #

BLE = "wearable-ble"
T0 = dt.datetime(2026, 11, 8, 12, 0, tzinfo=dt.UTC)
P0 = dt.datetime(2026, 9, 1, 8, 0, tzinfo=dt.UTC)
HOUR = dt.timedelta(hours=1)
SPAN = "los últimos 2 días"
XML = {"content-type": "application/xml"}


def _row(index: int, action: str = "bind", crew: str | None = "crew-01",
         since: dt.datetime = T0, device: str | None = DEVICE, source: str = BLE) -> dict[str, Any]:
    """Una declaración con la forma en que la entrega el almacén."""
    row: dict[str, Any] = {
        "subject": "tripulacion", "source": source, "action": action,
        "since": since.isoformat(), "note": "", "declared_by": "CDR",
        "ledger_index": index, "recorded": "2026-11-08T12:00:00+00:00", "signer": "crew-console",
    }
    if device is not None:
        row["device"] = device
    if crew is not None:
        row["crew"] = crew
    return row


def _obs(at: dt.datetime, device: str | None = DEVICE, key: str = "heart-rate",
         source: str = BLE, subject: str = "crew-02") -> VitalObservation:
    return observation(key, 60.0, at, subject, source, device=device)


def test_nothing_declared_says_nothing() -> None:
    said = bindings.in_readings([], [_obs(T0), _obs(T0 + HOUR, None)], "crew-02", SPAN)
    assert (said["kind"], said["mismatched"], said["text"]) == ("none", 0, None)
    assert (said["readings"], said["with_device"]) == (2, 1)
    assert said["groups"] == [] and said["indicators"] == [] and said["since"] is None
    assert said["analysis_note"] is None


def test_each_signed_reading_is_judged_against_the_binding_of_its_instant() -> None:
    told = [_row(10, crew="crew-01", since=T0), _row(11, crew="crew-02", since=T0 + 5 * HOUR)]
    readings = [
        _obs(T0 - HOUR),                      # antes de la primera declaración: sin vínculo
        _obs(T0 + HOUR),                      # de crew-01 entonces: se señala
        _obs(T0 + 2 * HOUR, key="respiratory-rate"),  # ídem, otro indicador
        _obs(T0 + 6 * HOUR),                  # ya vinculado al propio crew-02
        _obs(T0 + HOUR, "otro-reloj"),        # otro dispositivo: nada declarado
        _obs(T0 + HOUR, None),                # sin identificador: se compara con la fuente
        _obs(T0 + HOUR, source="manual"),     # no es una fuente de wearable: no se compara
    ]
    said = bindings.in_readings(told, readings, "crew-02", SPAN)
    assert (said["kind"], said["label"]) == ("bound-to-other-crew", "declarado por una persona")
    assert (said["readings"], said["with_device"], said["mismatched"]) == (6, 5, 2)
    assert said["since"] == (T0 + HOUR).isoformat()
    assert said["indicators"] == [
        {"key": "heart-rate", "display": "Heart rate", "display_es": "Frecuencia cardiaca",
         "readings": 1},
        {"key": "respiratory-rate", "display": "Respiratory rate",
         "display_es": "Frecuencia respiratoria", "readings": 1},
    ]
    [group] = said["groups"]
    assert (group["crew"], group["ledger_index"], group["readings"]) == ("crew-01", 10, 2)
    assert (group["first"], group["last"]) == (
        (T0 + HOUR).isoformat(), (T0 + 2 * HOUR).isoformat())
    assert (group["since"], group["declared_by"]) == (T0.isoformat(), "CDR")
    assert (group["source"], group["whole_source"]) == (BLE, False)
    text = said["text"]
    assert text.startswith(
        "2 de 6 lecturas de wearable de los últimos 2 días llegaron para crew-02")
    assert "constaba vinculado a crew-01 desde el 2026-11-08 12:00 UTC" in text
    assert "la primera, del 2026-11-08 13:00 UTC" in text
    assert "declarado por una persona: EMMA no comprueba quién lo lleva puesto" in text
    # Lo decidido (ficha, punto 4): se dice que se analizan igual y que decide una persona.
    assert text.endswith(
        "EMMA las analiza igual; decidir si son de este tripulante es de una persona.")
    assert said["analysis_note"] == bindings.ANALYSED_ANYWAY
    # Para el tripulante que sí consta vinculado, las mismas lecturas no son un aviso.
    mine = bindings.in_readings(told[:1], readings, "crew-01", SPAN)
    assert (mine["kind"], mine["mismatched"]) == ("none", 0)
    assert mine["text"].startswith("Ninguna lectura de los últimos 2 días llegó desde")


def test_one_reading_is_told_in_the_singular() -> None:
    said = bindings.in_readings([_row(10)], [_obs(T0 + HOUR)], "crew-02", SPAN)
    assert said["text"].startswith(
        "1 de 1 lectura de wearable de los últimos 2 días llegó para crew-02")
    assert "1 lectura desde el dispositivo" in said["text"]


def test_a_reading_without_identifier_is_compared_with_the_whole_source_binding() -> None:
    told = [_row(10, crew="crew-01", device=None, source="google-fit")]
    readings = [
        _obs(T0 + HOUR, None, source="google-fit"),
        _obs(T0 + HOUR, "pixel-7", source="google-fit"),
        _obs(T0 + HOUR, None),
    ]
    said = bindings.in_readings(told, readings, "crew-02", SPAN)
    assert (said["readings"], said["mismatched"]) == (3, 1)
    [group] = said["groups"]
    assert (group["whole_source"], group["device_display"]) == (
        True, bindings.WHOLE_SOURCE_DISPLAY)
    assert "desde la fuente datos de Google Fit, sin identificador de dispositivo" in said["text"]


def test_a_withdrawn_binding_and_one_that_names_nobody_give_no_notice() -> None:
    gone = [_row(10), _row(11, action="unbind", crew=None, since=T0 + HOUR)]
    assert bindings.in_readings(gone, [_obs(T0 + 2 * HOUR)], "crew-02", SPAN)["kind"] == "none"
    nobody = [_row(10, crew=None)]
    assert bindings.in_readings(nobody, [_obs(T0 + HOUR)], "crew-02", SPAN)["kind"] == "none"


def test_two_bindings_are_two_groups_in_ledger_order() -> None:
    told = [
        _row(20, crew="crew-03", device="reloj-b"),
        _row(10, crew="crew-01"),
    ]
    readings = [_obs(T0 + HOUR, "reloj-b"), _obs(T0 + 2 * HOUR), _obs(T0 + 3 * HOUR)]
    said = bindings.in_readings(told, readings, "crew-02", SPAN)
    assert [(g["ledger_index"], g["crew"], g["readings"]) for g in said["groups"]] == [
        (10, "crew-01", 2), (20, "crew-03", 1)]
    assert said["mismatched"] == 3 and said["since"] == (T0 + HOUR).isoformat()
    assert said["text"].count("que constaba vinculado a ") == 2
    # Cada indicador, con cuántas lecturas: en su grupo y en el total.
    pulse = {"key": "heart-rate", "display": "Heart rate", "display_es": "Frecuencia cardiaca"}
    assert [g["indicators"] for g in said["groups"]] == [
        [{**pulse, "readings": 2}], [{**pulse, "readings": 1}]]
    assert said["indicators"] == [{**pulse, "readings": 3}]
    assert "Frecuencia cardiaca (2)" in said["text"]


def test_the_status_never_repeats_the_whole_identifier() -> None:
    assert bindings.device_short(DEVICE) == "…e:01"
    assert bindings.device_short("w1") == "w1"
    assert bindings.device_short(None) == bindings.WHOLE_SOURCE_DISPLAY
    said = bindings.in_readings([_row(10)], [_obs(T0 + HOUR)], "crew-02", SPAN)
    assert DEVICE not in json.dumps(said, ensure_ascii=False)
    assert said["groups"][0]["device_display"] == "…e:01" and "«…e:01»" in said["text"]
    assert said["device_note"] == bindings.SHORT_DEVICE_NOTE


def test_an_unreadable_binding_record_is_said_not_guessed() -> None:
    said = bindings.in_readings(None, [_obs(T0)], "crew-02", SPAN)
    assert (said["kind"], said["mismatched"], said["groups"]) == ("not-checked", None, [])
    assert "No se ha podido comparar" in said["text"]


def test_data_quality_only_gains_the_block_and_only_looks_at_recent_readings() -> None:
    window = dt.timedelta(days=2)
    latest = T0 + 3 * dt.timedelta(days=1)
    old, recent = _obs(T0 + HOUR), _obs(latest)
    told = [_row(10)]
    plain = data_quality.describe([old, recent], [], latest, window)
    flagged = data_quality.describe([old, recent], [], latest, window, sensor_bindings=told)
    # La lectura antigua queda fuera de la ventana: solo cuenta la reciente.
    assert flagged["device_bindings"]["mismatched"] == 1
    assert flagged["device_bindings"]["readings"] == 1
    assert plain["device_bindings"]["kind"] == "none"
    # Nada más del bloque de calidad cambia por haber vínculos.
    assert {k: v for k, v in flagged.items() if k != "device_bindings"} == {
        k: v for k, v in plain.items() if k != "device_bindings"}
    # Ni por llevar las lecturas un dispositivo.
    bare = data_quality.describe(
        [_obs(T0 + HOUR, None), _obs(latest, None)], [], latest, window)
    assert {k: v for k, v in bare.items() if k != "device_bindings"} == {
        k: v for k, v in plain.items() if k != "device_bindings"}
    broken = data_quality.describe([recent], [], latest, window, sensor_bindings=None)
    assert broken["device_bindings"]["kind"] == "not-checked"


# --------------------------------------------------------------------------- #
# Las tres rutas guardan el identificador que ya recibían
# --------------------------------------------------------------------------- #


def _declare(client: TestClient, crew: str | None = "crew-01", **extra: Any) -> Any:
    body: dict[str, Any] = {
        "source": BLE, "device": DEVICE, "action": "bind", "since": T0.isoformat(),
        "declared_by": "CDR", **extra,
    }
    if crew is not None:
        body["crew"] = crew
    return client.post("/api/sensor-bindings", json=body)


def _ble(client: TestClient, subject: str, at: dt.datetime = T0, **extra: Any) -> Any:
    return client.post("/api/wearable/ble", json={
        "frame_hex": bytes([0b0000_0000, 60]).hex(), "subject": subject,
        "effective": at.isoformat(), **extra,
    })


def _fit(*instants: dt.datetime) -> dict[str, Any]:
    return {"point": [
        {
            "dataTypeName": "com.google.heart_rate.bpm",
            "startTimeNanos": str(int(at.timestamp()) * 1_000_000_000),
            "endTimeNanos": str(int(at.timestamp()) * 1_000_000_000),
            "value": [{"fpVal": 64.0}],
        }
        for at in instants
    ]}


def _apple(*instants: dt.datetime) -> bytes:
    records = "".join(
        '<Record type="HKQuantityTypeIdentifierHeartRate" unit="count/min" value="64" '
        f'startDate="{at.strftime("%Y-%m-%d %H:%M:%S +0000")}"/>'
        for at in instants
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><HealthData>{records}</HealthData>'.encode()


def _last_payloads(count: int) -> list[dict[str, Any]]:
    entries = get_store().ledger.entries[-count:]
    assert all(entry.entry_type == "vital-observation" for entry in entries)
    return [dict(entry.payload) for entry in entries]


def test_the_ble_route_signs_the_device_it_was_given_normalized(client: TestClient) -> None:
    sent = _ble(client, "crew-02", device=" AA:BB:CC:DD:EE:01 ")
    assert sent.status_code == 201, sent.text
    assert sent.json()["binding_notice"] is None
    assert _last_payloads(1)[0]["device"] == DEVICE
    # Sin identificador, la lectura se firma sin el campo: como antes.
    assert _ble(client, "crew-02", T0 + HOUR).status_code == 201
    assert "device" not in _last_payloads(1)[0]
    assert [obs.device for obs in get_store().query("crew-02")] == [DEVICE, None]
    assert get_store().verify_integrity().ok


def test_the_two_imports_sign_the_device_on_every_reading(client: TestClient) -> None:
    sent = client.post(
        "/api/import/google-fit", params={"subject": "crew-02", "device": "Pixel-7"},
        json=_fit(P0, P0 + HOUR),
    )
    assert sent.status_code == 201, sent.text
    assert [item["device"] for item in _last_payloads(2)] == ["pixel-7", "pixel-7"]
    sent = client.post(
        "/api/import/apple-health", params={"subject": "crew-02", "device": "Watch-Ana"},
        content=_apple(P0 + 2 * HOUR), headers=XML,
    )
    assert sent.status_code == 201, sent.text
    assert _last_payloads(1)[0]["device"] == "watch-ana"
    for path, kwargs in (
        ("/api/import/google-fit", {"json": _fit(P0 + 3 * HOUR)}),
        ("/api/import/apple-health", {"content": _apple(P0 + 4 * HOUR), "headers": XML}),
    ):
        plain = client.post(path, params={"subject": "crew-02"}, **kwargs)
        assert plain.status_code == 201, plain.text
        assert "device" not in _last_payloads(1)[0]
    assert get_store().verify_integrity().ok


def test_the_routes_still_accept_and_still_answer_with_the_notice(client: TestClient) -> None:
    _declare(client, "crew-01")
    size = len(get_store().ledger)
    sent = _ble(client, "crew-02", T0 + HOUR, device=DEVICE)
    assert sent.status_code == 201 and len(get_store().ledger) == size + 1
    said = sent.json()["binding_notice"]
    assert (said["kind"], said["accepted"], said["mismatched"]) == ("bound-to-other-crew", True, 1)


# --------------------------------------------------------------------------- #
# El estado lo dice
# --------------------------------------------------------------------------- #


def _status(client: TestClient, subject: str, **params: Any) -> dict[str, Any]:
    response = client.get("/api/status", params={"subject": subject, **params})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _seeded(client: TestClient) -> tuple[list[str], dt.datetime]:
    assert client.post(
        "/api/simulate", params={"scenario": "co2-fatigue", "days": 10}).status_code == 201
    crew = [item["subject"] for item in client.get("/api/crew").json()["crew"]]
    reference = dt.datetime.fromisoformat(_status(client, crew[0])["data"]["reference_time"])
    return crew, reference


def test_the_status_tells_the_readings_from_a_device_bound_to_someone_else(
    client: TestClient,
) -> None:
    crew, reference = _seeded(client)
    quiet = _status(client, crew[0])["data"]["quality"]["device_bindings"]
    assert (quiet["kind"], quiet["text"], quiet["mismatched"]) == ("none", None, 0)

    since = reference - dt.timedelta(days=1)
    index = _declare(client, crew[1], since=since.isoformat()).json()["ledger_index"]
    for minutes in (30, 20):
        assert _ble(client, crew[0], reference - dt.timedelta(minutes=minutes),
                    device=DEVICE).status_code == 201
    # Una lectura anterior al vínculo y otra sin identificador no se señalan.
    assert _ble(client, crew[0], since - HOUR, device=DEVICE).status_code == 201
    assert _ble(client, crew[0], reference - dt.timedelta(minutes=10)).status_code == 201

    status = _status(client, crew[0])
    said = status["data"]["quality"]["device_bindings"]
    assert (said["kind"], said["mismatched"], said["readings"], said["with_device"]) == (
        "bound-to-other-crew", 2, 4, 3)
    assert said["indicators"] == [{
        "key": "heart-rate", "display": "Heart rate", "display_es": "Frecuencia cardiaca",
        "readings": 2,
    }]
    assert said["since"] == (reference - dt.timedelta(minutes=30)).isoformat()
    [group] = said["groups"]
    assert (group["crew"], group["ledger_index"], group["declared_by"]) == (crew[1], index, "CDR")
    assert f"llegaron para {crew[0]} desde un dispositivo" in said["text"]
    assert said["text"].endswith(bindings.ANALYSED_ANYWAY)
    # El identificador entero no sale en el estado; sí donde se preguntan los vínculos.
    assert DEVICE not in json.dumps(status, ensure_ascii=False)
    assert client.get("/api/sensor-bindings").json()["bindings"][0]["device"] == DEVICE
    # Para el tripulante vinculado no hay nada que avisar, y se dice sin alarma.
    other = _status(client, crew[1])["data"]["quality"]["device_bindings"]
    assert (other["kind"], other["mismatched"]) == ("none", 0)


def test_ground_compares_with_the_bindings_that_existed_at_its_cut(client: TestClient) -> None:
    # Lecturas con fecha pasada y un vínculo firmado hoy: en el corte de Tierra aún no existía.
    _declare(client, "crew-01", since=P0.isoformat())
    for minutes in (10, 20, 30):
        assert _ble(client, "crew-02", P0 + dt.timedelta(minutes=minutes),
                    device=DEVICE).status_code == 201
    aboard = _status(client, "crew-02")["data"]["quality"]["device_bindings"]
    assert (aboard["kind"], aboard["mismatched"]) == ("bound-to-other-crew", 3)
    cut = (P0 + dt.timedelta(minutes=25)).isoformat()
    ground = _status(client, "crew-02", until=cut)["data"]["quality"]["device_bindings"]
    assert (ground["kind"], ground["readings"], ground["mismatched"]) == ("none", 2, 0)


def test_a_broken_binding_record_does_not_break_the_status(client: TestClient) -> None:
    crew, reference = _seeded(client)
    assert _ble(client, crew[0], reference - HOUR, device=DEVICE).status_code == 201
    get_store()._record_action("sensor-binding", {
        "subject": "tripulacion", "source": BLE, "action": "bind", "crew": 7,
        "since": T0.isoformat(), "note": "", "declared_by": "CDR",
    }, identity_for("crew-console"))
    said = _status(client, crew[0])["data"]["quality"]["device_bindings"]
    assert (said["kind"], said["mismatched"]) == ("not-checked", None)
    assert "No se ha podido comparar" in said["text"]


def test_the_identifier_is_signed_and_never_logged(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    secret = "f0:0d:ca:fe:00:99"
    crew, reference = _seeded(client)
    _declare(client, crew[1], device=secret, since=(reference - HOUR).isoformat())
    assert _ble(client, crew[0], reference - dt.timedelta(minutes=5),
                device=secret).status_code == 201
    sent = client.post(
        "/api/import/google-fit", params={"subject": crew[0], "device": secret}, json=_fit(P0))
    assert sent.status_code == 201, sent.text
    said = _status(client, crew[0])["data"]["quality"]["device_bindings"]
    assert said["mismatched"] == 1
    client.get("/api/observations", params={"subject": crew[0], "limit": 10})
    assert secret in str(_last_payloads(1)[0]), "se firma: es su sitio"
    written = "\n".join(record.getMessage() for record in caplog.records)
    assert secret not in written and secret.upper() not in written


# --------------------------------------------------------------------------- #
# Invariante 5: el veredicto del motor no cambia
# --------------------------------------------------------------------------- #


def _without_device(reading: dict[str, Any]) -> dict[str, Any]:
    """Una lectura FHIR sin su `id` ni el identificador de dispositivo: lo que el motor lee."""
    return {
        **{k: v for k, v in reading.items() if k != "id"},
        "device": {k: v for k, v in reading["device"].items() if k != "identifier"},
    }


def _what_the_engine_decided(client: TestClient) -> dict[str, Any]:
    """Todo lo que la invariante 5 prohíbe mover, y las lecturas que hay de cada tripulante."""
    decided: dict[str, Any] = {
        "crew": client.get("/api/crew").json(),
        "habitat": client.get("/api/habitat").json(),
    }
    for member in [item["subject"] for item in decided["crew"]["crew"]]:
        status = _status(client, member)
        readings = client.get(
            "/api/observations", params={"subject": member, "limit": 5000}).json()
        # Lo único que esta pieza añade al estado es `data.quality.device_bindings`.
        quality = {
            k: v for k, v in status["data"]["quality"].items() if k != "device_bindings"}
        decided[member] = {
            "readings": [_without_device(item) for item in readings["observations"]],
            "data": {**status["data"], "quality": quality},
            **{
                key: status[key]
                for key in (
                    "overall_level", "summary", "domains", "alerts", "recommendations",
                    "rules_version", "predictions", "followups", "notes",
                )
            },
        }
    return decided


def _run(client: TestClient, device: str | None, with_bindings: bool) -> dict[str, Any]:
    reset_store(new_store())
    crew, reference = _seeded(client)
    if with_bindings:
        since = (reference - dt.timedelta(days=3)).isoformat()
        assert _declare(client, crew[1], since=since).status_code == 201
        assert _declare(client, crew[1], device=None, since=since).status_code == 201
    extra = {} if device is None else {"device": device}
    for minutes in (30, 20, 10):
        sent = _ble(client, crew[0], reference - dt.timedelta(minutes=minutes), **extra)
        assert sent.status_code == 201, sent.text
    flagged = _status(client, crew[0])["data"]["quality"]["device_bindings"]["mismatched"]
    return {"decided": _what_the_engine_decided(client), "flagged": flagged, "subject": crew[0]}


def test_the_same_verdict_with_and_without_device_and_with_and_without_bindings(
    client: TestClient,
) -> None:
    base = _run(client, None, with_bindings=False)
    runs = {
        "con dispositivo, sin vínculos": _run(client, DEVICE, with_bindings=False),
        "sin dispositivo, con vínculos": _run(client, None, with_bindings=True),
        "con dispositivo, con vínculos": _run(client, DEVICE, with_bindings=True),
    }
    assert base["flagged"] == 0
    assert [run["flagged"] for run in runs.values()] == [0, 3, 3]
    for name, run in runs.items():
        assert run["decided"] == base["decided"], name
    mine = base["decided"][base["subject"]]
    assert mine["alerts"] and mine["overall_level"] != "nominal", "hay un veredicto que comparar"
    assert mine["readings"] and mine["rules_version"] == rules_version()


def test_the_device_is_not_read_by_anything_that_decides() -> None:
    assert not [name for name in FINGERPRINTED if "binding" in name or "quality" in name]
    root = Path(bindings.__file__).resolve().parents[1]
    for name in GUARDED:
        source = (root / Path(*name.split(".")[1:])).with_suffix(".py").read_text("utf-8")
        used = {
            node.attr for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Attribute)
        }
        assert "device" not in used, name
        assert "bindings" not in source and "data_quality" not in source, name
