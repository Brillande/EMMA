"""El vínculo sensor-tripulante, declarado por una persona (especificación §3, Astronauta).

EMMA no comprueba quién lleva puesto un reloj. Estas pruebas fijan lo que sí hace y lo que no
puede pasar: un dispositivo es lo que la ingesta distingue (la fuente y, si llega, un
identificador); cada declaración es UN asiento firmado por la consola (invariante 4); vale la
última y una lectura antigua se juzga contra el vínculo de su instante; de lo no declarado no se
avisa; el aviso no rechaza ninguna lectura y no mueve un solo nivel ni alerta (invariante 5).
"""

import ast
import datetime as dt
import logging
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.routes import get_store, identity_for, new_store, reset_store
from app.core.storage import TamperedRecordError
from app.core.versioning import FINGERPRINTED, GUARDED
from app.ingest import bindings

BLE = "wearable-ble"
WATCH = "aa:bb:cc:dd:ee:01"
LABEL = "declarado por una persona"
T0 = dt.datetime(2026, 11, 8, 12, 0, tzinfo=dt.UTC)
# Una importación no admite lecturas con fecha futura: sus pruebas viven en el pasado.
P0 = dt.datetime(2026, 9, 1, 8, 0, tzinfo=dt.UTC)


def _row(index: int, action: str = "bind", crew: str | None = "crew-01",
         since: dt.datetime = T0, device: str | None = WATCH, source: str = BLE) -> dict[str, Any]:
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


# --------------------------------------------------------------------------- #
# Qué es un dispositivo y qué se puede firmar
# --------------------------------------------------------------------------- #


def test_a_device_is_what_the_ingest_tells_apart_and_the_module_says_so() -> None:
    # Las tres fuentes de wearable que existen como rutas de ingesta, y ninguna más.
    assert list(bindings.SOURCES) == ["wearable-ble", "apple-health", "google-fit"]
    assert bindings.DECLARED_LABEL == LABEL
    assert "no comprueba quién lleva puesto" in bindings.DECLARED_NOTE
    assert "no puede distinguir" in bindings.DEVICE_BASIS
    assert "no lo lee de la trama ni del export" in bindings.DEVICE_BASIS
    assert "no bloquea ninguna lectura" in bindings.SCOPE
    assert "no se avisa" in bindings.SCOPE


def test_the_identifier_is_one_and_the_same_for_declaring_and_for_ingesting() -> None:
    assert bindings.device_key("  AA:BB:CC:DD:EE:01 ") == WATCH
    assert bindings.device_key(None) is None and bindings.device_key("   ") is None
    for bad in ("reloj de Ana", "a" * 65, "-x", "ñandú", "a/b"):
        with pytest.raises(ValueError, match="identificador de dispositivo no válido"):
            bindings.device_key(bad)
    assert bindings.device_key("a" * 64) == "a" * 64


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("sextante", "bind", "crew-01", None), "fuente desconocida"),
        (("simulator", "bind", "crew-01", None), "fuente desconocida"),
        ((BLE, "borrar", "crew-01", None), "acción desconocida"),
        ((BLE, "bind", None, None), "exige decir a qué tripulante"),
        ((BLE, "bind", "  ", None), "exige decir a qué tripulante"),
        ((BLE, "bind", "c" * 65, None), "más de 64"),
        ((BLE, "unbind", "crew-01", None), "desvincular no lleva tripulante"),
        ((BLE, "bind", "crew-01", "reloj de Ana"), "identificador de dispositivo no válido"),
    ],
)
def test_what_cannot_be_signed(args: tuple[Any, ...], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        bindings.check(*args)


def test_check_gives_back_the_identifier_as_it_will_be_stored() -> None:
    assert bindings.check(BLE, "bind", "crew-01", " AA:BB:CC:DD:EE:01") == WATCH
    assert bindings.check(BLE, "unbind", None, None) is None


# --------------------------------------------------------------------------- #
# Qué declaración vale, y en qué instante
# --------------------------------------------------------------------------- #


def test_a_reading_is_judged_against_the_binding_of_its_own_instant() -> None:
    day = dt.timedelta(days=1)
    told = [
        _row(10, crew="crew-01", since=T0),
        _row(11, crew="crew-02", since=T0 + 10 * day),
    ]
    held = bindings.in_force(told, BLE, WATCH, T0 - day)
    assert held is None, "antes de la primera declaración no había vínculo"
    for at, crew in ((T0, "crew-01"), (T0 + 5 * day, "crew-01"), (T0 + 10 * day, "crew-02"),
                     (T0 + 30 * day, "crew-02")):
        held = bindings.in_force(told, BLE, WATCH, at)
        assert held is not None and held["crew"] == crew, at
    # Corregir es declarar de nuevo: la firmada más tarde manda desde su instante, aunque su
    # instante sea anterior al de otra ya firmada.
    told.append(_row(12, crew="crew-03", since=T0 + 2 * day))
    for at, crew in ((T0 + day, "crew-01"), (T0 + 5 * day, "crew-03"),
                     (T0 + 30 * day, "crew-03")):
        held = bindings.in_force(told, BLE, WATCH, at)
        assert held is not None and held["crew"] == crew, at
    # Retirar es otra declaración, y vale desde su instante: antes, lo que hubiera.
    told.append(_row(13, action="unbind", crew=None, since=T0 + 20 * day))
    held = bindings.in_force(told, BLE, WATCH, T0 + 25 * day)
    assert held is not None and held["action"] == "unbind"
    held = bindings.in_force(told, BLE, WATCH, T0 + 15 * day)
    assert held is not None and held["crew"] == "crew-03"
    # Otro dispositivo, la fuente entera y otra fuente no heredan nada de este.
    assert bindings.in_force(told, BLE, "otro", T0 + 5 * day) is None
    assert bindings.in_force(told, BLE, None, T0 + 5 * day) is None
    assert bindings.in_force(told, "google-fit", WATCH, T0 + 5 * day) is None
    # El instante se compara en UTC, venga con el desfase que venga.
    local = (T0 - dt.timedelta(minutes=1)).astimezone(dt.timezone(dt.timedelta(hours=5)))
    assert bindings.in_force(told[:1], BLE, WATCH, local) is None


def test_the_notice_speaks_only_of_a_device_bound_to_someone_else() -> None:
    day = dt.timedelta(days=1)
    told = [_row(10, crew="crew-01", since=T0), _row(11, crew="crew-02", since=T0 + 10 * day)]
    # Sin vínculo declarado no hay aviso: no es un error.
    assert bindings.notice([], BLE, WATCH, "crew-02", [T0]) is None
    assert bindings.notice(told, BLE, "otro", "crew-02", [T0]) is None
    assert bindings.notice(told, BLE, None, "crew-02", [T0]) is None
    # Con el vínculo del propio tripulante, tampoco.
    assert bindings.notice(told, BLE, WATCH, "crew-01", [T0 + day]) is None
    # Ni antes de que hubiera vínculo.
    assert bindings.notice(told, BLE, WATCH, "crew-02", [T0 - day]) is None

    # Un export de crew-02 que cruza el cambio: solo cuentan las lecturas del tramo de crew-01.
    instants = [T0 - day, T0 + day, T0 + 2 * day, T0 + 11 * day]
    said = bindings.notice(told, BLE, WATCH, "crew-02", instants)
    assert said is not None
    assert (said["kind"], said["label"], said["accepted"]) == ("bound-to-other-crew", LABEL, True)
    assert (said["readings"], said["mismatched"], said["subject"]) == (4, 2, "crew-02")
    assert said["bound_to"] == [{
        "crew": "crew-01", "since": T0.isoformat(), "declared_by": "CDR", "ledger_index": 10,
        "readings": 2,
    }]
    assert (said["device"], said["source"]) == (WATCH, BLE)
    text = said["text"]
    assert "2 de 4" in text and "crew-01 desde 2026-11-08T12:00:00+00:00 (2 lecturas)" in text
    assert "EMMA no comprueba quién lo lleva puesto" in text
    assert "se han registrado igual" in text and "lo valora una persona" in text
    # Apoyo a la decisión: describe, no ordena (invariante 7).
    for order in ("debe", "hay que", "corrija", "rechaz"):
        assert order not in text.lower()

    # Con el vínculo retirado en ese instante no hay con qué comparar.
    told.append(_row(12, action="unbind", crew=None, since=T0))
    assert bindings.notice(told, BLE, WATCH, "crew-02", instants) is None


def test_a_binding_entry_that_names_nobody_gives_nothing_to_compare_with() -> None:
    # Solo puede existir escrito a mano en el almacén; aun así, no se avisa «vinculado a nadie».
    assert bindings.notice([_row(10, crew=None)], BLE, WATCH, "crew-02", [T0]) is None


def test_the_whole_source_binding_is_named_as_what_it_is() -> None:
    told = [_row(10, crew="crew-01", device=None, source="apple-health")]
    said = bindings.notice(told, "apple-health", None, "crew-02", [T0])
    assert said is not None and said["device"] is None
    assert said["device_display"] == "sin identificador (la fuente entera)"
    assert "sin identificador de dispositivo" in said["text"] and "(1 lectura)" in said["text"]
    # Una lectura que sí trae identificador no se juzga contra el vínculo de la fuente entera.
    assert bindings.notice(told, "apple-health", WATCH, "crew-02", [T0]) is None


def test_the_overview_gives_the_latest_signed_per_device_and_keeps_the_history() -> None:
    told = [
        _row(10, crew="crew-01"),
        _row(11, crew="crew-02", since=T0 + dt.timedelta(days=1)),
        _row(12, crew="crew-01", device=None, source="google-fit"),
        _row(13, crew="crew-03", device="zz-9"),
        _row(14, action="unbind", crew=None, device="zz-9"),
    ]
    body = bindings.overview(told)
    assert body["label"] == LABEL and "no comprueba quién lleva puesto" in body["note"]
    assert [item["key"] for item in body["sources"]] == list(bindings.SOURCES)
    assert body["actions"] == ["bind", "unbind"]
    rows = body["bindings"]
    # El retirado no está entre los vigentes; el corregido sale con lo último firmado.
    assert [(row["source"], row["device"], row["crew"]) for row in rows] == [
        ("google-fit", None, "crew-01"), (BLE, WATCH, "crew-02"),
    ]
    assert (rows[1]["declarations"], rows[1]["ledger_index"]) == (2, 11)
    assert rows[1]["since"] == (T0 + dt.timedelta(days=1)).isoformat()
    assert rows[1]["caveat"] is None
    assert "no puede distinguir" in rows[0]["caveat"]
    assert "Dispositivos con vínculo declarado: 2." in body["summary"]
    assert "no es un fallo" in body["summary"]
    told_back = body["history"]
    assert [item["ledger_index"] for item in told_back] == [14, 13, 12, 11, 10]
    assert [(item["bound"], item["crew"], item["previous_crew"], item["changed"])
            for item in told_back] == [
        (False, None, "crew-03", True), (True, "crew-03", None, True),
        (True, "crew-01", None, True), (True, "crew-02", "crew-01", True),
        (True, "crew-01", None, True),
    ]
    # Nada declarado no es un fallo: una lista vacía y el mismo rótulo.
    empty = bindings.overview([])
    assert empty["bindings"] == [] and empty["history"] == []
    assert "vínculo declarado: 0." in empty["summary"]


def test_the_sentence_for_the_chronicle_never_repeats_the_identifier() -> None:
    told = bindings.history([
        _row(10, crew="crew-01"), _row(11, crew="crew-02"), _row(12, crew="crew-02"),
        _row(13, action="unbind", crew=None), _row(14, crew="crew-01", device=None),
    ])
    told[0]["note"] = "reloj azul"
    lines = [bindings.sentence(item) for item in told]
    assert all(WATCH not in line and LABEL in line for line in lines)
    assert "vinculado a crew-01 (antes no constaba vínculo" in lines[0]
    assert lines[0].endswith("; nota: reloj azul")
    assert "vinculado a crew-02 (antes constaba crew-01" in lines[1]
    assert "sin cambio respecto a lo declarado antes" in lines[2]
    assert "vínculo retirado (antes constaba crew-02" in lines[3]
    assert "la fuente pulsómetro Bluetooth LE entera" in lines[4]


# --------------------------------------------------------------------------- #
# El asiento
# --------------------------------------------------------------------------- #


def test_a_declaration_is_one_signed_entry_in_the_ledger(client: TestClient) -> None:
    store, console = get_store(), identity_for("crew-console")
    size = len(store.ledger)
    entry = store.record_sensor_binding(
        BLE, "bind", T0, "  reloj azul ", " CDR ", console, crew=" crew-01 ",
        device=" AA:BB:CC:DD:EE:01",
    )
    assert (entry.index, len(store.ledger)) == (size, size + 1)
    assert (entry.entry_type, entry.signer) == ("sensor-binding", "crew-console")
    assert {k: v for k, v in entry.payload.items() if k != "_salt"} == {
        "subject": "tripulacion", "source": BLE, "action": "bind", "device": WATCH,
        "crew": "crew-01", "since": "2026-11-08T12:00:00+00:00", "note": "reloj azul",
        "declared_by": "CDR",
    }
    # Retirar no nombra a nadie, y un vínculo de fuente entera no lleva identificador.
    gone = store.record_sensor_binding("google-fit", "unbind", T0, "", "CDR", console)
    assert {k: v for k, v in gone.payload.items() if k != "_salt"} == {
        "subject": "tripulacion", "source": "google-fit", "action": "unbind",
        "since": "2026-11-08T12:00:00+00:00", "note": "", "declared_by": "CDR",
    }
    assert store.verify_integrity().ok
    read = store.sensor_bindings()
    assert [(item["ledger_index"], item["action"], item.get("crew"), item.get("device"))
            for item in read] == [
        (size, "bind", "crew-01", WATCH), (size + 1, "unbind", None, None),
    ]
    assert all(item["signer"] == "crew-console" for item in read)


def test_the_store_refuses_what_cannot_be_signed(client: TestClient) -> None:
    # El almacén no se fía de quien le llama: la regla está en la escritura del asiento.
    store, console = get_store(), identity_for("crew-console")
    size = len(store.ledger)
    with pytest.raises(ValueError, match="fuente desconocida"):
        store.record_sensor_binding("sextante", "bind", T0, "", "CDR", console, crew="crew-01")
    with pytest.raises(ValueError, match="acción desconocida"):
        store.record_sensor_binding(BLE, "borrar", T0, "", "CDR", console, crew="crew-01")
    with pytest.raises(ValueError, match="exige decir a qué tripulante"):
        store.record_sensor_binding(BLE, "bind", T0, "", "CDR", console)
    with pytest.raises(ValueError, match="desvincular no lleva tripulante"):
        store.record_sensor_binding(BLE, "unbind", T0, "", "CDR", console, crew="crew-01")
    with pytest.raises(ValueError, match="identificador de dispositivo no válido"):
        store.record_sensor_binding(
            BLE, "bind", T0, "", "CDR", console, crew="crew-01", device="reloj de Ana")
    with pytest.raises(ValueError, match="zona horaria"):
        store.record_sensor_binding(
            BLE, "bind", T0.replace(tzinfo=None), "", "CDR", console, crew="crew-01")
    with pytest.raises(ValueError, match="una persona con nombre"):
        store.record_sensor_binding(BLE, "bind", T0, "", "  ", console, crew="crew-01")
    assert len(store.ledger) == size
    assert store.sensor_bindings() == []


def test_a_malformed_entry_is_not_delivered(client: TestClient) -> None:
    # `device` y `crew` son opcionales, pero si están tienen que ser texto.
    store = get_store()
    store._record_action("sensor-binding", {
        "subject": "tripulacion", "source": BLE, "action": "bind", "crew": 7,
        "since": T0.isoformat(), "note": "", "declared_by": "CDR",
    }, identity_for("crew-console"))
    with pytest.raises(TamperedRecordError, match="acción mal formada"):
        store.sensor_bindings()


def test_a_missing_field_is_a_malformed_entry(client: TestClient) -> None:
    store = get_store()
    store._record_action("sensor-binding", {
        "subject": "tripulacion", "source": BLE, "action": "bind", "crew": "crew-01",
        "since": T0.isoformat(), "declared_by": "CDR",
    }, identity_for("crew-console"))
    with pytest.raises(TamperedRecordError, match="acción mal formada"):
        store.sensor_bindings()


def test_what_was_already_signed_still_verifies_and_reads(client: TestClient) -> None:
    # Invariante 4: el tipo nuevo no cambia la lectura de los asientos que ya existían.
    store, console = get_store(), identity_for("crew-console")
    store.record_hypothesis_review("confirmed", "cabin-ppco2", T0, "visto", "CDR", console)
    client.post("/api/observations", json={"key": "heart-rate", "value": 61, "subject": "crew-01"})
    store.record_sensor_binding(BLE, "bind", T0, "", "CDR", console, crew="crew-01")
    assert store.verify_integrity().ok
    # Comparten sujeto («tripulacion») y no se mezclan: cada lectura filtra por su tipo.
    assert len(store.hypothesis_reviews()) == 1 and len(store.sensor_bindings()) == 1
    assert client.get("/api/observations", params={"subject": "crew-01"}).json()["count"] == 1


# --------------------------------------------------------------------------- #
# La ruta: declarar y leer
# --------------------------------------------------------------------------- #


def _declare(client: TestClient, crew: str | None = "crew-01", **extra: Any) -> Any:
    body: dict[str, Any] = {
        "source": BLE, "device": WATCH, "action": "bind", "since": T0.isoformat(),
        "declared_by": "CDR", **extra,
    }
    if crew is not None:
        body["crew"] = crew
    return client.post("/api/sensor-bindings", json=body)


def _read(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/api/sensor-bindings", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _frame(rate: int = 60) -> str:
    return bytes([0b0000_0000, rate]).hex()


def _ble(client: TestClient, subject: str, at: dt.datetime = T0, **extra: Any) -> Any:
    return client.post("/api/wearable/ble", json={
        "frame_hex": _frame(), "subject": subject, "effective": at.isoformat(), **extra,
    })


def test_nothing_declared_is_not_a_failure(client: TestClient) -> None:
    body = _read(client)
    assert body["label"] == LABEL
    assert body["bindings"] == [] and body["history"] == []
    assert "no comprueba quién lleva puesto" in body["note"]
    assert "no puede distinguir" in body["device_basis"]
    assert "no bloquea ninguna lectura" in body["scope"]
    assert "no es un fallo" in body["summary"]


def test_declaring_writes_one_console_entry_and_the_latest_holds(client: TestClient) -> None:
    store = get_store()
    size = len(store.ledger)
    first = _declare(client, device="AA:BB:CC:DD:EE:01", note="  reloj azul ")
    assert first.status_code == 201, first.text
    index = first.json()["ledger_index"]
    assert (index, len(store.ledger)) == (size, size + 1)
    entry = store.ledger.entries[index]
    assert (entry.entry_type, entry.signer) == ("sensor-binding", "crew-console")
    assert {k: v for k, v in entry.payload.items() if k != "_salt"} == {
        "subject": "tripulacion", "source": BLE, "action": "bind", "device": WATCH,
        "crew": "crew-01", "since": "2026-11-08T12:00:00+00:00", "note": "reloj azul",
        "declared_by": "CDR",
    }
    [row] = _read(client)["bindings"]
    assert row | {"recorded": None} == {
        "source": BLE, "source_display": "pulsómetro Bluetooth LE", "device": WATCH,
        "device_display": WATCH, "crew": "crew-01", "since": "2026-11-08T12:00:00+00:00",
        "note": "reloj azul", "declared_by": "CDR", "declarations": 1, "ledger_index": index,
        "recorded": None, "caveat": None,
    }
    assert row["recorded"] == entry.recorded.isoformat()

    # Se corrige declarando de nuevo: vale lo último firmado y lo anterior se conserva.
    later = (T0 + dt.timedelta(days=3)).isoformat()
    again = _declare(client, "crew-02", since=later, declared_by="FE-1")
    body = _read(client)
    [row] = body["bindings"]
    assert (row["crew"], row["since"], row["declarations"], row["declared_by"]) == (
        "crew-02", "2026-11-11T12:00:00+00:00", 2, "FE-1",
    )
    assert row["ledger_index"] == again.json()["ledger_index"]
    # Retirar es otra declaración: deja de estar entre los vigentes y sigue en el historial.
    gone = _declare(client, None, action="unbind", since=later)
    assert gone.status_code == 201, gone.text
    body = _read(client)
    assert body["bindings"] == []
    assert [(item["action"], item["crew"], item["previous_crew"]) for item in body["history"]] == [
        ("unbind", None, "crew-02"), ("bind", "crew-02", "crew-01"), ("bind", "crew-01", None),
    ]
    assert len(store.ledger) == size + 3 and store.verify_integrity().ok
    assert client.get("/api/sensor-bindings", params={"until": "2026-11-08T12:00:00"}
                      ).status_code == 422


@pytest.mark.parametrize(
    "change",
    [
        {"source": "sextante"},
        {"source": "simulator"},
        {"action": "borrar"},
        {"crew": "  "},
        {"crew": "c" * 65},
        {"device": "reloj de Ana"},
        {"device": "a" * 65},
        {"since": "2026-11-08T12:00:00"},
        {"since": "ayer"},
        {"declared_by": "   "},
        {"declared_by": "x" * 65},
        {"note": "n" * 501},
        {"signer": "crew-console"},
        {"action": "unbind"},
    ],
)
def test_what_cannot_be_signed_is_a_422_and_nothing_is_written(
    client: TestClient, change: dict[str, Any]
) -> None:
    size = len(get_store().ledger)
    assert _declare(client, **change).status_code == 422, change
    assert len(get_store().ledger) == size


def test_binding_without_a_crew_member_is_a_422(client: TestClient) -> None:
    size = len(get_store().ledger)
    assert _declare(client, None).status_code == 422
    for missing in ("source", "action", "since", "declared_by"):
        body = {"source": BLE, "action": "bind", "crew": "crew-01", "since": T0.isoformat(),
                "declared_by": "CDR"}
        del body[missing]
        assert client.post("/api/sensor-bindings", json=body).status_code == 422, missing
    assert len(get_store().ledger) == size


def test_only_what_the_console_signed_counts(client: TestClient) -> None:
    store = get_store()
    # Con la clave de un wearable no se declara de quién es un wearable.
    store.record_sensor_binding(
        BLE, "bind", T0, "", "nadie", identity_for("wearable-ble"), crew="crew-01", device=WATCH)
    assert len(store.sensor_bindings()) == 1
    assert _read(client)["bindings"] == [] and _read(client)["history"] == []
    sent = _ble(client, "crew-02", device=WATCH)
    assert sent.status_code == 201 and sent.json()["binding_notice"] is None


def test_ground_only_sees_what_existed_at_its_cut(client: TestClient) -> None:
    # Vale desde un instante anterior al corte, pero se firma ahora: en ese corte no existía.
    assert _declare(client, since="2020-06-01T00:00:00+00:00").status_code == 201
    assert _read(client, until="2021-01-01T00:00:00+00:00")["history"] == []
    # Ya firmado, pero vale desde un instante posterior al corte: tampoco.
    assert _declare(client, device="zz-9", since="2199-01-01T00:00:00+00:00").status_code == 201
    seen = _read(client, until="2100-01-01T00:00:00+00:00")
    assert [item["device"] for item in seen["history"]] == [WATCH]
    assert len(_read(client)["bindings"]) == 2


# --------------------------------------------------------------------------- #
# El aviso en la ingesta: describe, no rechaza
# --------------------------------------------------------------------------- #


def test_a_reading_from_a_device_bound_to_someone_else_enters_and_says_so(
    client: TestClient,
) -> None:
    store = get_store()
    index = _declare(client, "crew-01").json()["ledger_index"]
    size = len(store.ledger)
    # Mayúsculas y espacios: el mismo reloj que se declaró.
    sent = _ble(client, "crew-02", T0 + dt.timedelta(hours=1), device=" AA:BB:CC:DD:EE:01 ")
    assert sent.status_code == 201, sent.text
    body = sent.json()
    # La lectura entra igual: está en el ledger, firmada por su fuente, bajo quien dijo la
    # petición. El vínculo no la cambia de tripulante.
    assert body["indicators"] == ["heart-rate"] and body["recorded"] == [size]
    assert len(store.ledger) == size + 1
    entry = store.ledger.entries[size]
    assert (entry.entry_type, entry.signer) == ("vital-observation", "wearable-ble")
    assert client.get("/api/observations", params={"subject": "crew-02"}).json()["count"] == 1
    assert client.get("/api/observations", params={"subject": "crew-01"}).json()["count"] == 0
    # Desde el 2026-10-13 el identificador viaja en la lectura firmada, normalizado como el
    # del vínculo (`tests/test_device_in_reading.py`).
    assert entry.payload["device"] == WATCH

    said = body["binding_notice"]
    assert (said["kind"], said["accepted"], said["label"]) == ("bound-to-other-crew", True, LABEL)
    assert (said["subject"], said["device"], said["source"]) == ("crew-02", WATCH, BLE)
    assert (said["readings"], said["mismatched"]) == (1, 1)
    assert said["bound_to"] == [{
        "crew": "crew-01", "since": "2026-11-08T12:00:00+00:00", "declared_by": "CDR",
        "ledger_index": index, "readings": 1,
    }]
    assert "constaba vinculado a otro tripulante (crew-01 desde" in said["text"]
    assert "se han registrado igual" in said["text"]
    assert store.verify_integrity().ok


def test_no_notice_for_the_bound_crew_member_nor_before_the_binding_nor_unbound_devices(
    client: TestClient,
) -> None:
    # Sin ningún vínculo declarado, con y sin identificador: 201 y nada que decir.
    for extra in ({}, {"device": WATCH}):
        sent = _ble(client, "crew-02", **extra)
        assert sent.status_code == 201 and sent.json()["binding_notice"] is None
    _declare(client, "crew-01")
    hour = dt.timedelta(hours=1)
    # El propio tripulante; una lectura anterior al vínculo; otro dispositivo; sin identificador.
    for subject, at, extra in (
        ("crew-01", T0 + hour, {"device": WATCH}),
        ("crew-02", T0 - hour, {"device": WATCH}),
        ("crew-02", T0 + hour, {"device": "otro-reloj"}),
        ("crew-02", T0 + hour, {}),
    ):
        sent = _ble(client, subject, at, **extra)
        assert sent.status_code == 201, sent.text
        assert sent.json()["binding_notice"] is None, (subject, at, extra)
    # Retirado el vínculo, tampoco hay con qué comparar.
    _declare(client, None, action="unbind", since=(T0 + 2 * hour).isoformat())
    sent = _ble(client, "crew-02", T0 + 3 * hour, device=WATCH)
    assert sent.status_code == 201 and sent.json()["binding_notice"] is None
    # Pero una lectura del tramo en que sí constaba se sigue juzgando contra aquel vínculo.
    sent = _ble(client, "crew-02", T0 + hour, device=WATCH)
    assert sent.status_code == 201 and sent.json()["binding_notice"]["mismatched"] == 1


def test_an_identifier_that_is_not_one_is_a_422_before_anything_is_recorded(
    client: TestClient,
) -> None:
    size = len(get_store().ledger)
    refused = _ble(client, "crew-02", device="reloj de Ana")
    assert refused.status_code == 422
    assert "reloj de Ana" not in refused.text
    for route, kwargs in (
        ("/api/import/google-fit", {"json": _fit(P0)}),
        ("/api/import/apple-health", {"content": _apple(P0), "headers": XML}),
    ):
        refused = client.post(route, params={"device": "reloj de Ana"}, **kwargs)
        assert refused.status_code == 422, route
    assert len(get_store().ledger) == size


XML = {"content-type": "application/xml"}


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


def test_an_import_judges_each_reading_against_the_binding_of_its_instant(
    client: TestClient,
) -> None:
    day = dt.timedelta(days=1)
    # La fuente entera de Google Fit, de crew-01 hasta el día 10 y de crew-02 desde entonces.
    first = _declare(
        client, "crew-01", source="google-fit", device=None, since=P0.isoformat(),
    ).json()["ledger_index"]
    _declare(
        client, "crew-02", source="google-fit", device=None, since=(P0 + 10 * day).isoformat())
    instants = [P0 - day, P0 + day, P0 + 2 * day, P0 + 11 * day]
    sent = client.post(
        "/api/import/google-fit", params={"subject": "crew-02"}, json=_fit(*instants))
    assert sent.status_code == 201, sent.text
    body = sent.json()
    assert (body["imported"], body["rejected"]) == (4, 0)
    said = body["binding_notice"]
    assert (said["readings"], said["mismatched"], said["device"]) == (4, 2, None)
    assert [(row["crew"], row["readings"], row["ledger_index"]) for row in said["bound_to"]] == [
        ("crew-01", 2, first),
    ]
    assert "sin identificador de dispositivo" in said["text"]
    assert client.get("/api/observations", params={"subject": "crew-02"}).json()["count"] == 4
    # La misma importación con un identificador no se juzga contra el vínculo de fuente entera.
    again = client.post(
        "/api/import/google-fit", params={"subject": "crew-03", "device": "pixel-7"},
        json=_fit(*instants),
    )
    assert again.status_code == 201 and again.json()["binding_notice"] is None


def test_the_apple_health_import_carries_the_notice_too(client: TestClient) -> None:
    _declare(client, "crew-01", source="apple-health", device="watch-ana", since=P0.isoformat())
    sent = client.post(
        "/api/import/apple-health", params={"subject": "crew-02", "device": "Watch-Ana"},
        content=_apple(P0 + dt.timedelta(hours=1)), headers=XML,
    )
    assert sent.status_code == 201, sent.text
    said = sent.json()["binding_notice"]
    assert (sent.json()["imported"], said["mismatched"], said["device"]) == (1, 1, "watch-ana")
    mine = client.post(
        "/api/import/apple-health", params={"subject": "crew-01", "device": "watch-ana"},
        content=_apple(P0 + dt.timedelta(hours=2)), headers=XML,
    )
    assert mine.status_code == 201 and mine.json()["binding_notice"] is None


def test_a_broken_binding_record_does_not_turn_an_accepted_reading_into_an_error(
    client: TestClient,
) -> None:
    store = get_store()
    store._record_action("sensor-binding", {
        "subject": "tripulacion", "source": BLE, "action": "bind", "crew": 7,
        "since": T0.isoformat(), "note": "", "declared_by": "CDR",
    }, identity_for("crew-console"))
    size = len(store.ledger)
    sent = _ble(client, "crew-02", device=WATCH)
    assert sent.status_code == 201, sent.text
    assert len(store.ledger) == size + 1
    said = sent.json()["binding_notice"]
    assert (said["kind"], said["accepted"], said["mismatched"]) == ("not-checked", True, None)
    assert "No se ha podido comparar" in said["text"]
    # Quien pregunta por los vínculos sí ve que el registro no es de fiar.
    assert client.get("/api/sensor-bindings").status_code == 409


def test_the_identifier_is_never_written_to_the_log(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    secret = "f0:0d:ca:fe:00:99"
    _declare(client, "crew-01", device=secret)
    assert _declare(client, "crew-01", device=secret + " x").status_code == 422
    assert _ble(client, "crew-02", device=secret).json()["binding_notice"] is not None
    sent = client.post(
        "/api/import/google-fit", params={"subject": "crew-02", "device": secret}, json=_fit(P0))
    assert sent.status_code == 201, sent.text
    client.get("/api/sensor-bindings")
    client.get("/api/timeline/chronicle", params={"subject": "crew-02"})
    written = "\n".join(record.getMessage() for record in caplog.records)
    assert secret not in written and secret.upper() not in written
    # Y ninguna línea de log en los dos módulos del vínculo.
    root = Path(bindings.__file__).resolve().parents[1]
    for name in ("ingest/bindings.py", "api/sensor_bindings.py"):
        source = (root / name).read_text("utf-8")
        assert "logging" not in source and "print(" not in source, name


# --------------------------------------------------------------------------- #
# La crónica
# --------------------------------------------------------------------------- #


def test_the_chronicle_tells_the_declaration_without_the_identifier(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "co2-fatigue", "days": 10})
    crew = [item["subject"] for item in client.get("/api/crew").json()["crew"]]
    reference = dt.datetime.fromisoformat(
        client.get("/api/status", params={"subject": crew[0]}).json()["data"]["reference_time"])
    since = reference - dt.timedelta(days=2)
    bound = _declare(client, crew[0], since=since.isoformat(), note="reloj azul")
    gone = _declare(
        client, None, action="unbind", since=(since + dt.timedelta(days=1)).isoformat())
    # Es de la tripulación: sale en la crónica de todos.
    for subject in crew[:2]:
        chronicle = client.get("/api/timeline/chronicle", params={"subject": subject}).json()
        told = [event for event in chronicle["events"] if event["tipo"] == "sensor"]
        assert sorted((event["fact"], event["clave"]) for event in told) == sorted([
            ("sensor-binding-declared", f"ledger:{bound.json()['ledger_index']}"),
            ("sensor-binding-withdrawn", f"ledger:{gone.json()['ledger_index']}"),
        ])
        [declared] = [event for event in told if event["fact"] == "sensor-binding-declared"]
        assert declared["at"] == since.astimezone(dt.UTC).isoformat()
        assert (declared["time_basis"], declared["quien"]) == ("data", "CDR")
        assert f"vinculado a {crew[0]}" in declared["que"] and LABEL in declared["que"]
        assert "nota: reloj azul" in declared["que"]
        assert all(WATCH not in event["que"] for event in told)
    # Tierra no ve una declaración firmada después de su corte.
    cut = client.get("/api/timeline/chronicle", params={
        "subject": crew[0], "until": "2020-01-01T00:00:00+00:00"}).json()
    assert not [event for event in cut["events"] if event["tipo"] == "sensor"]

    # Y con un corte entre el instante de datos y la firma: una declaración que vale desde antes
    # del corte, pero firmada después. Solo este caso distingue el filtro por firma
    # (`timeline.counted`) del instante de datos de `_signed`: con 2020 los dos la quitan.
    past = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
    late = _declare(client, crew[0], since=past.isoformat())
    assert late.status_code == 201, late.text
    cut = client.get("/api/timeline/chronicle", params={
        "subject": crew[0], "until": (past + dt.timedelta(hours=1)).isoformat()}).json()
    assert not [event for event in cut["events"] if event["tipo"] == "sensor"]


# --------------------------------------------------------------------------- #
# Invariante 5: el veredicto del motor no cambia
# --------------------------------------------------------------------------- #


def _what_the_engine_decided(client: TestClient) -> dict[str, Any]:
    """Todo lo que la invariante 5 prohíbe mover, y las lecturas que hay de cada tripulante."""
    decided: dict[str, Any] = {
        "crew": client.get("/api/crew").json(),
        "habitat": client.get("/api/habitat").json(),
    }
    for member in [item["subject"] for item in decided["crew"]["crew"]]:
        status = client.get("/api/status", params={"subject": member}).json()
        readings = client.get(
            "/api/observations", params={"subject": member, "limit": 5000}).json()
        # Desde el 2026-10-13 el estado DICE el aviso (`data.quality.device_bindings`): es lo
        # único que un vínculo puede cambiar en él, y no es parte del veredicto
        # (`tests/test_device_in_reading.py` fija qué dice).
        said = status["data"]["quality"].pop("device_bindings")
        assert said["kind"] in ("none", "bound-to-other-crew")
        decided[member] = {
            "readings": [
                {k: v for k, v in item.items() if k != "id"} for item in readings["observations"]
            ],
            **{
                key: status[key]
                for key in (
                    "overall_level", "summary", "domains", "alerts", "recommendations",
                    "rules_version", "predictions", "data",
                )
            },
        }
    return decided


def _run(client: TestClient, with_bindings: bool) -> tuple[dict[str, Any], list[Any]]:
    reset_store(new_store())
    assert client.post(
        "/api/simulate", params={"scenario": "co2-fatigue", "days": 10}).status_code == 201
    crew = [item["subject"] for item in client.get("/api/crew").json()["crew"]]
    reference = dt.datetime.fromisoformat(
        client.get("/api/status", params={"subject": crew[0]}).json()["data"]["reference_time"])
    since = reference - dt.timedelta(days=3)
    if with_bindings:
        # El reloj consta como de otro tripulante, y la fuente entera de Google Fit también.
        assert _declare(client, crew[1], since=since.isoformat()).status_code == 201
        assert _declare(client, crew[1], source="google-fit", device=None,
                        since=(P0 - dt.timedelta(days=1)).isoformat()).status_code == 201
    notices = []
    for minutes in (30, 20, 10):
        sent = _ble(client, crew[0], reference - dt.timedelta(minutes=minutes), device=WATCH)
        assert sent.status_code == 201, sent.text
        notices.append(sent.json()["binding_notice"])
    sent = client.post("/api/import/google-fit", params={"subject": crew[0]},
                       json=_fit(P0))
    assert sent.status_code == 201, sent.text
    notices.append(sent.json()["binding_notice"])
    return _what_the_engine_decided(client), notices


def test_the_same_readings_levels_and_alerts_with_and_without_bindings(
    client: TestClient,
) -> None:
    without, silent = _run(client, with_bindings=False)
    with_them, said = _run(client, with_bindings=True)
    assert silent == [None, None, None, None]
    assert all(item is not None and item["mismatched"] == 1 for item in said)
    assert with_them == without
    subject = with_them["crew"]["crew"][0]["subject"]
    assert with_them[subject]["alerts"] and with_them[subject]["overall_level"] != "nominal"
    assert with_them[subject]["readings"], "hay lecturas que comparar"


def test_the_binding_is_not_a_rule_of_the_engine() -> None:
    # No entra en la huella de reglas, y ningún módulo que decide lo importa.
    assert not [name for name in FINGERPRINTED if "binding" in name]
    root = Path(bindings.__file__).resolve().parents[1]
    for name in GUARDED:
        tree = ast.parse((root / Path(*name.split(".")[1:])).with_suffix(".py").read_text("utf-8"))
        imported = {
            alias.name if isinstance(node, ast.Import) else f"{node.module}.{alias.name}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Import | ast.ImportFrom)
            for alias in node.names
        }
        assert not [item for item in imported if "binding" in item]
