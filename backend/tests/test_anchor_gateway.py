"""Pasarela de anclas (`scripts/anchor_gateway.py`) sin radio y sin red.

Por qué existe: la pasarela es la única pieza de la ubicación medida que toca hardware, y aquí no
hay balizas. Lo que sí se puede fijar sin radio es lo que importa al contrato: qué bytes son un
ancla y cuáles no, cómo se resume una ventana y la forma exacta del cuerpo de
`POST /api/location/sightings` (envío simulado con `respx`). Corre sin `bleak` instalado.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import uuid
from pathlib import Path
from types import ModuleType

import httpx
import pytest
import respx

BACKEND = Path(__file__).resolve().parents[1]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "anchor_gateway", BACKEND / "scripts" / "anchor_gateway.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # `dataclass` busca su módulo en sys.modules
    spec.loader.exec_module(module)
    return module


gw = _load()

BEACON_UUID = uuid.UUID("f7826da6-4fa2-4e98-8024-bc5b71e0893e")
IBEACON = bytes([0x02, 0x15]) + BEACON_UUID.bytes + bytes([0x00, 0x01, 0x00, 0x2A, 0xC5])
NAMESPACE = bytes(range(10))
INSTANCE = bytes([0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5])
EDDYSTONE = bytes([0x00, 0xEE]) + NAMESPACE + INSTANCE + bytes([0x00, 0x00])
IBEACON_ID = f"ibeacon:{BEACON_UUID}:1:42"
EDDYSTONE_ID = "eddystone:00010203040506070809:a0a1a2a3a4a5"
T0 = dt.datetime(2026, 11, 10, 9, 0, 0, tzinfo=dt.UTC)


# --- Análisis de anuncios ---------------------------------------------------------------


def test_an_ibeacon_frame_names_its_anchor_by_uuid_major_and_minor() -> None:
    assert gw.parse_ibeacon(IBEACON) == IBEACON_ID


@pytest.mark.parametrize("frame", [
    IBEACON[:-1],                        # truncado
    IBEACON + b"\x00",                   # sobra un byte
    bytes([0x03, 0x15]) + IBEACON[2:],   # otro tipo de Apple
    bytes([0x02, 0x14]) + IBEACON[2:],   # longitud declarada que no casa
    b"",
])
def test_a_malformed_ibeacon_frame_is_not_an_anchor(frame: bytes) -> None:
    assert gw.parse_ibeacon(frame) is None


def test_an_eddystone_uid_frame_names_its_anchor_with_or_without_the_reserved_bytes() -> None:
    assert gw.parse_eddystone_uid(EDDYSTONE) == EDDYSTONE_ID
    assert gw.parse_eddystone_uid(EDDYSTONE[:18]) == EDDYSTONE_ID


@pytest.mark.parametrize("frame", [
    bytes([0x10]) + EDDYSTONE[1:],   # trama URL, no UID
    bytes([0x20]) + EDDYSTONE[1:],   # trama TLM
    EDDYSTONE[:17],                  # truncado
    EDDYSTONE + b"\x00",             # sobra un byte
    b"",
])
def test_a_malformed_or_non_uid_eddystone_frame_is_not_an_anchor(frame: bytes) -> None:
    assert gw.parse_eddystone_uid(frame) is None


def test_only_apple_manufacturer_data_and_the_eddystone_service_are_looked_at() -> None:
    assert gw.anchor_from_advertisement({0x004C: IBEACON}, {}) == IBEACON_ID
    assert gw.anchor_from_advertisement({0x0059: IBEACON}, {}) is None   # otra compañía
    assert gw.anchor_from_advertisement({}, {gw.EDDYSTONE_SERVICE: EDDYSTONE}) == EDDYSTONE_ID
    assert gw.anchor_from_advertisement({}, {"FEAA": EDDYSTONE}) == EDDYSTONE_ID
    assert gw.anchor_from_advertisement({}, {"0x0000feaa": EDDYSTONE}) == EDDYSTONE_ID
    assert gw.anchor_from_advertisement({}, {"0000fe9f-0000-1000-8000-00805f9b34fb":
                                             EDDYSTONE}) is None
    assert gw.anchor_from_advertisement({0x004C: b"\x10\x05\x01"}, {}) is None  # no es iBeacon


# --- Ventanas y resumen ---------------------------------------------------------------------


def _r(anchor: str, rssi: float, seconds: float) -> object:
    return gw.Reading(anchor, rssi, T0 + dt.timedelta(seconds=seconds))


def test_a_window_gives_one_sighting_per_anchor_with_the_median_and_the_last_time() -> None:
    window = [_r(IBEACON_ID, -70, 0), _r(IBEACON_ID, -60, 1), _r(IBEACON_ID, -90, 2),
              _r(EDDYSTONE_ID, -80, 1.5)]
    assert gw.summarize_window(window) == [
        {"anchor_id": EDDYSTONE_ID, "rssi_dbm": -80.0, "at": "2026-11-10T09:00:01.500Z"},
        {"anchor_id": IBEACON_ID, "rssi_dbm": -70.0, "at": "2026-11-10T09:00:02.000Z"},
    ]


def test_an_rssi_outside_the_hci_range_is_dropped() -> None:
    window = [_r(IBEACON_ID, 127, 0), _r(IBEACON_ID, float("nan"), 0), _r(IBEACON_ID, -128, 0),
              _r(EDDYSTONE_ID, -65, 0)]
    assert [s["anchor_id"] for s in gw.summarize_window(window)] == [EDDYSTONE_ID]


def test_readings_split_into_fixed_windows_counted_from_the_first() -> None:
    readings = [_r(IBEACON_ID, -60, 12), _r(IBEACON_ID, -60, 0), _r(IBEACON_ID, -60, 4.9),
                _r(IBEACON_ID, -60, 5)]
    windows = gw.split_windows(readings, 5.0)
    assert [[r.at for r in w] for w in windows] == [
        [T0, T0 + dt.timedelta(seconds=4.9)],
        [T0 + dt.timedelta(seconds=5)],
        [T0 + dt.timedelta(seconds=12)],
    ]
    assert gw.split_windows([], 5.0) == []
    with pytest.raises(ValueError):
        gw.split_windows(readings, 0)


# --- Forma del cuerpo (contrato) ------------------------------------------------------------


def _sightings(count: int) -> list[dict[str, object]]:
    return [{"anchor_id": f"ibeacon:{BEACON_UUID}:1:{i}", "rssi_dbm": -60.0,
             "at": "2026-11-10T09:00:00.000Z"} for i in range(count)]


def test_the_payload_has_exactly_the_contract_keys() -> None:
    [with_device] = gw.build_payloads(_sightings(2), "crew-1", "pasarela-nodo2")
    assert set(with_device) == {"subject", "device", "sightings"}
    assert with_device["subject"] == "crew-1" and with_device["device"] == "pasarela-nodo2"
    for sighting in with_device["sightings"]:
        assert set(sighting) == {"anchor_id", "rssi_dbm", "at"}
        assert isinstance(sighting["rssi_dbm"], float)
        dt.datetime.fromisoformat(sighting["at"].replace("Z", "+00:00"))
    [without_device] = gw.build_payloads(_sightings(1), "crew-1", None)
    assert set(without_device) == {"subject", "sightings"}


def test_batches_never_exceed_the_contract_maximum() -> None:
    payloads = gw.build_payloads(_sightings(1201), "crew-1", None)
    assert [len(p["sightings"]) for p in payloads] == [500, 500, 201]
    assert gw.build_payloads([], "crew-1", None) == []


# --- El backend es loopback o LAN, nunca internet -----------------------------------------


@pytest.mark.parametrize(("url", "base"), [
    ("http://127.0.0.1:8000", "http://127.0.0.1:8000"),
    ("http://localhost:8000/", "http://localhost:8000"),
    ("http://[::1]:8000", "http://[::1]:8000"),
    ("http://192.168.1.20:8000", "http://192.168.1.20:8000"),
    ("http://10.0.0.5", "http://10.0.0.5"),
    ("http://169.254.10.1:8000", "http://169.254.10.1:8000"),
    ("http://[fd00::5]:8000", "http://[fd00::5]:8000"),
    ("http://[fe80::1]:8000", "http://[fe80::1]:8000"),
    ("http://[::ffff:192.168.1.1]:8000", "http://[::ffff:192.168.1.1]:8000"),
])
def test_a_loopback_or_lan_backend_is_accepted(url: str, base: str) -> None:
    assert gw.check_local_backend(url) == base


@pytest.mark.parametrize("url", [
    "http://example.org", "http://8.8.8.8:8000", "ftp://127.0.0.1", "127.0.0.1:8000",
    "http://emma.local",
    "http://[::ffff:8.8.8.8]:8000",      # IPv4 pública mapeada en IPv6
    "http://[2001:0:4136:e378::1]",      # Teredo: `is_private` lo da por privado
    "http://[2606:4700::1111]",
])
def test_a_backend_that_could_be_on_the_internet_is_refused(url: str) -> None:
    with pytest.raises(ValueError):
        gw.check_local_backend(url)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000/emma", "http://127.0.0.1:8000/?a=1",
                                 "http://127.0.0.1:8000#x", "http://u:p@127.0.0.1:8000"])
def test_a_backend_with_path_query_fragment_or_credentials_is_refused(url: str) -> None:
    with pytest.raises(ValueError):
        gw.check_local_backend(url)


# --- Envío (respx: sin red) ---------------------------------------------------------------


@respx.mock
def test_a_batch_is_posted_to_the_sightings_route_as_json() -> None:
    route = respx.post("http://127.0.0.1:8000/api/location/sightings").mock(
        return_value=httpx.Response(200, json={"ledger_index": 7, "accepted": 2,
                                               "unknown_anchors": []}))
    [payload] = gw.build_payloads(_sightings(2), "crew-1", "gw")
    with httpx.Client() as client:
        result = gw.post_batch(client, "http://127.0.0.1:8000", payload)
    assert result["ledger_index"] == 7
    sent = route.calls.last.request
    assert json.loads(sent.content) == payload
    assert sent.headers["content-type"] == "application/json"


@respx.mock
def test_a_rejected_batch_raises() -> None:
    respx.post("http://127.0.0.1:8000/api/location/sightings").mock(
        return_value=httpx.Response(422, json={"detail": "x"}))
    with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError):
        gw.post_batch(client, "http://127.0.0.1:8000", gw.build_payloads(
            _sightings(1), "crew-1", None)[0])


# --- Programa de punta a punta, sin radio -------------------------------------------------


def _recording(tmp_path: Path) -> Path:
    lines = [
        {"at": "2026-11-10T09:00:00Z", "rssi": -62, "manufacturer_data": {"76": IBEACON.hex()}},
        {"at": "2026-11-10T09:00:01Z", "rssi": -58, "manufacturer_data": {"0x004C": IBEACON.hex()}},
        {"at": "2026-11-10T09:00:02Z", "rssi": -75, "service_data": {"feaa": EDDYSTONE.hex()}},
        {"at": "2026-11-10T09:00:03Z", "rssi": -40, "manufacturer_data": {"6": "0102"}},  # otro
        {"at": "2026-11-10T09:00:07Z", "rssi": -66, "manufacturer_data": {"76": IBEACON.hex()}},
    ]
    path = tmp_path / "grabacion.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return path


def test_a_dry_run_replay_prints_contract_shaped_batches(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = gw.main(["--subject", "crew-1", "--device", "gw", "--from-file",
                    str(_recording(tmp_path)), "--dry-run"])
    assert code == gw.EXIT_OK
    [batch] = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert batch == {"subject": "crew-1", "device": "gw", "sightings": [
        {"anchor_id": EDDYSTONE_ID, "rssi_dbm": -75.0, "at": "2026-11-10T09:00:02.000Z"},
        {"anchor_id": IBEACON_ID, "rssi_dbm": -60.0, "at": "2026-11-10T09:00:01.000Z"},
        {"anchor_id": IBEACON_ID, "rssi_dbm": -66.0, "at": "2026-11-10T09:00:07.000Z"},
    ]}


@respx.mock
def test_a_replay_posts_and_reports_what_the_backend_answered(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    route = respx.post("http://127.0.0.1:8000/api/location/sightings").mock(
        return_value=httpx.Response(200, json={"ledger_index": 3, "accepted": 3,
                                               "unknown_anchors": [EDDYSTONE_ID]}))
    code = gw.main(["--subject", "crew-1", "--from-file", str(_recording(tmp_path))])
    assert code == gw.EXIT_OK and route.call_count == 1
    assert json.loads(capsys.readouterr().out) == {
        "ledger_index": 3, "accepted": 3, "unknown_anchors": [EDDYSTONE_ID]}


@pytest.mark.parametrize(("key", "company"), [("76", 0x004C), ("0x004C", 0x004C),
                                              ("004C", 0x004C), ("4c", 0x004C), ("89", 89)])
def test_company_keys_in_a_recording_read_as_decimal_or_hex(key: str, company: int) -> None:
    assert gw._company_key(key) == company


@respx.mock
@pytest.mark.parametrize("answer", [httpx.Response(200, text="<html>"),
                                    httpx.Response(200, json=[1, 2])])
def test_a_2xx_answer_off_contract_fails_cleanly(tmp_path: Path, answer: httpx.Response) -> None:
    respx.post("http://127.0.0.1:8000/api/location/sightings").mock(return_value=answer)
    assert gw.main(["--subject", "crew-1", "--from-file",
                    str(_recording(tmp_path))]) == gw.EXIT_FAILED


@respx.mock
def test_a_replay_rejected_by_the_backend_fails(tmp_path: Path) -> None:
    respx.post("http://127.0.0.1:8000/api/location/sightings").mock(
        return_value=httpx.Response(503))
    assert gw.main(["--subject", "crew-1", "--from-file",
                    str(_recording(tmp_path))]) == gw.EXIT_FAILED


def test_a_malformed_recording_is_a_usage_error_with_its_line(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "mala.jsonl"
    path.write_text('{"at": "2026-11-10T09:00:00Z", "rssi": -60}\n{"rssi": "x"}\n',
                    encoding="utf-8")
    assert gw.main(["--subject", "c", "--from-file", str(path), "--dry-run"]) == gw.EXIT_USAGE
    assert "mala.jsonl:2" in capsys.readouterr().err


def test_without_bleak_live_listening_is_unavailable_not_a_crash(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(gw, "bleak_available", lambda: False)
    assert gw.main(["--subject", "crew-1"]) == gw.EXIT_UNAVAILABLE
    err = capsys.readouterr().err
    assert "no disponible" in err and "[anchors]" in err


def test_a_non_local_backend_is_refused_before_anything_is_sent(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert gw.main(["--subject", "c", "--backend", "http://example.org",
                    "--from-file", str(_recording(tmp_path))]) == gw.EXIT_USAGE
    assert "internet" in capsys.readouterr().err
