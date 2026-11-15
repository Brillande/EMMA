"""Pasarela de anclas de módulo: escucha balizas BLE de la nave y manda lo oído al backend de EMMA.

    .venv/Scripts/python.exe scripts/anchor_gateway.py --subject crew-1 [--device pasarela-nodo2]
        [--backend http://127.0.0.1:8000] [--window 5] [--from-file grabacion.jsonl] [--dry-run]

Por qué existe: el usuario (2026-11-10) quiere la ubicación por módulo «real, no simulada», y
viable en el espacio. Lo viable es que las anclas sean equipo de la nave —certificado y
alimentado por ella— y que EMMA solo escuche (`compliance/location-sensing-feasibility.md`). Esta
pasarela es esa escucha: recibe anuncios BLE, reconoce los dos formatos de baliza más comunes y
manda las lecturas a `POST /api/location/sightings`, que las anexa al ledger (invariante 4). No
decide el módulo: eso lo hace el backend con las anclas declaradas en la consola.

**Solo escucha.** Nunca se conecta a un dispositivo ni emite nada: el escaneo es pasivo
(`scanning_mode="passive"`). Un escaneo activo mandaría peticiones de escaneo (SCAN_REQ), es decir,
emitiría; si el sistema operativo no permite el pasivo, la pasarela se para y lo dice, no cae al
activo.

**Formatos reconocidos** (cualquier otro anuncio se ignora):
  * iBeacon: datos de fabricante de Apple (0x004C), tipo 0x02 y longitud 0x15 →
    `ibeacon:<uuid>:<major>:<minor>`.
  * Eddystone-UID: datos de servicio 0xFEAA, trama 0x00 → `eddystone:<namespace>:<instance>`.

**Lote por ventana.** Por cada ventana (`--window`, 5 s por defecto) y cada ancla sale una sola
lectura: la mediana del RSSI y la hora del último anuncio oído. La mediana resiste picos sueltos de
multitrayecto; es una elección de esta pasarela **sin respaldo medido en un módulo metálico**
(«calibrar en cada nave»), igual que los parámetros de `app/data/location_sensing.json`. Los lotes
se trocean a 500 lecturas, el máximo del contrato.

**Red: solo hacia el backend propio, en loopback o LAN.** No es salida a internet, así que no pasa
por `app/core/egress.py` (que gobierna la salida a internet por propósito; invariante 3 bis). Para
que eso sea cierto y no una promesa, `--backend` solo admite `localhost` o una IP literal de
loopback, privada o de enlace local; un nombre de host cualquiera se rechaza, porque podría
resolver a internet. Usa `httpx` como el resto del backend (y así se prueba con `respx`, sin red).

**`bleak` es opcional** (extra `[anchors]` de `pyproject.toml`, fuera de `dev`). Sin él la escucha
en vivo está «no disponible»: mensaje claro y código 3, no un fallo. `--from-file` y `--dry-run`
funcionan sin él: reproducen anuncios grabados (una línea JSON por anuncio) para probar sin radio.

Formato de `--from-file` (JSONL, una línea por anuncio; claves de fabricante en decimal si son
solo cifras y en hexadecimal si llevan `0x` o letras, servicios como UUID de 16, 32 o 128 bits,
bytes en hexadecimal):
    {"at": "2026-11-10T09:00:00Z", "rssi": -61,
     "manufacturer_data": {"76": "0215…"}, "service_data": {"feaa": "00…"}}

Códigos de salida: 0 bien; 1 el backend no aceptó un lote o no se pudo escanear; 2 uso o fichero
mal formado; 3 escucha en vivo no disponible (falta `bleak`).

Herramienta de la nave, no del paquete de escritorio: no viaja en el instalador.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import importlib.util
import ipaddress
import json
import math
import statistics
import sys
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

APPLE_COMPANY_ID = 0x004C
IBEACON_TYPE = 0x02
IBEACON_LENGTH = 0x15
EDDYSTONE_SERVICE = "0000feaa-0000-1000-8000-00805f9b34fb"
EDDYSTONE_UID_FRAME = 0x00
# Bluetooth Core, informe de anuncio LE del HCI: RSSI en -127..+20 dBm; 127 = «no disponible».
RSSI_MIN_DBM = -127.0
RSSI_MAX_DBM = 20.0
MAX_SIGHTINGS = 500  # contrato de POST /api/location/sightings
SIGHTINGS_PATH = "/api/location/sightings"
DEFAULT_BACKEND = "http://127.0.0.1:8000"
DEFAULT_WINDOW_S = 5.0

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_UNAVAILABLE = 3

UNAVAILABLE_TEXT = (
    "Escucha de anclas no disponible: instala el extra [anchors] "
    "(.venv/Scripts/python.exe -m pip install -e \".[anchors]\"). "
    "Sin radio se puede reproducir una grabación con --from-file."
)


@dataclass(frozen=True)
class Reading:
    """Un anuncio oído de un ancla reconocida."""

    anchor_id: str
    rssi_dbm: float
    at: dt.datetime


# --- Análisis de anuncios (funciones puras) -------------------------------------------------


def parse_ibeacon(payload: bytes) -> str | None:
    """`payload` son los datos de fabricante de Apple SIN el identificador de compañía (como los
    da `bleak`): tipo, longitud, UUID (16), major (2), minor (2) y potencia calibrada (1)."""
    if len(payload) != 2 + IBEACON_LENGTH:
        return None
    if payload[0] != IBEACON_TYPE or payload[1] != IBEACON_LENGTH:
        return None
    beacon_uuid = uuid.UUID(bytes=bytes(payload[2:18]))
    major = int.from_bytes(payload[18:20], "big")
    minor = int.from_bytes(payload[20:22], "big")
    return f"ibeacon:{beacon_uuid}:{major}:{minor}"


def parse_eddystone_uid(payload: bytes) -> str | None:
    """`payload` son los datos de servicio 0xFEAA: trama, potencia a 0 m (1), espacio de nombres
    (10), instancia (6) y, opcionales, dos bytes reservados."""
    if len(payload) not in (18, 20) or payload[0] != EDDYSTONE_UID_FRAME:
        return None
    return f"eddystone:{bytes(payload[2:12]).hex()}:{bytes(payload[12:18]).hex()}"


def _service_key(key: str) -> str:
    key = key.strip().lower()
    if key.startswith("0x"):
        key = key[2:]
    if len(key) == 4:
        key = f"0000{key}"
    if len(key) == 8:
        return f"{key}-0000-1000-8000-00805f9b34fb"
    return key


def _company_key(key: str) -> int:
    """Identificador de compañía: `0x…` o sin prefijo con letras → hexadecimal; solo cifras →
    decimal (como serializa `bleak` sus claves enteras)."""
    key = key.strip().lower()
    if key.startswith("0x"):
        return int(key[2:], 16)
    return int(key, 10) if key.isdigit() else int(key, 16)


def anchor_from_advertisement(
    manufacturer_data: Mapping[int, bytes], service_data: Mapping[str, bytes]
) -> str | None:
    """El `anchor_id` de un anuncio, o `None` si no es una baliza reconocida."""
    apple = manufacturer_data.get(APPLE_COMPANY_ID)
    if apple is not None:
        found = parse_ibeacon(apple)
        if found:
            return found
    for key, payload in service_data.items():
        if _service_key(key) == EDDYSTONE_SERVICE:
            found = parse_eddystone_uid(payload)
            if found:
                return found
    return None


def usable_rssi(rssi: float) -> bool:
    return math.isfinite(rssi) and RSSI_MIN_DBM <= rssi <= RSSI_MAX_DBM


# --- Lotes ------------------------------------------------------------------------------------


def split_windows(readings: Iterable[Reading], window_s: float) -> list[list[Reading]]:
    """Agrupa por ventanas fijas contadas desde la primera lectura (orden por hora). Una ventana
    sin lecturas no aparece."""
    if window_s <= 0:
        raise ValueError("la ventana tiene que ser positiva")
    ordered = sorted(readings, key=lambda r: r.at)
    if not ordered:
        return []
    start = ordered[0].at
    groups: dict[int, list[Reading]] = {}
    for reading in ordered:
        index = math.floor((reading.at - start).total_seconds() / window_s)
        groups.setdefault(index, []).append(reading)
    return [groups[i] for i in sorted(groups)]


def _iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def summarize_window(readings: Iterable[Reading]) -> list[dict[str, Any]]:
    """Una lectura por ancla: mediana del RSSI utilizable y hora del último anuncio."""
    by_anchor: dict[str, list[Reading]] = {}
    for reading in readings:
        if usable_rssi(reading.rssi_dbm):
            by_anchor.setdefault(reading.anchor_id, []).append(reading)
    sightings = []
    for anchor_id in sorted(by_anchor):
        heard = by_anchor[anchor_id]
        sightings.append({
            "anchor_id": anchor_id,
            "rssi_dbm": float(statistics.median(r.rssi_dbm for r in heard)),
            "at": _iso(max(r.at for r in heard)),
        })
    return sightings


def build_payloads(
    sightings: list[dict[str, Any]], subject: str, device: str | None
) -> list[dict[str, Any]]:
    """Cuerpos de `POST /api/location/sightings`, de 1 a 500 lecturas cada uno."""
    payloads = []
    for start in range(0, len(sightings), MAX_SIGHTINGS):
        body: dict[str, Any] = {"subject": subject}
        if device:
            body["device"] = device
        body["sightings"] = sightings[start:start + MAX_SIGHTINGS]
        payloads.append(body)
    return payloads


# --- Envío (loopback o LAN, nunca internet) --------------------------------------------------


_ULA = ipaddress.ip_network("fc00::/7")


def _is_local(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Loopback, privada (RFC 1918) o de enlace local. En IPv6 no se usa `is_private`, que da
    por privados rangos que llegan a internet (Teredo, y en algunas versiones de Python las
    IPv4 mapeadas): solo loopback, enlace local y ULA (fc00::/7); una IPv4 mapeada se juzga como
    la IPv4 que lleva dentro."""
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return _is_local(address.ipv4_mapped)
        return address.is_loopback or address.is_link_local or address in _ULA
    return address.is_loopback or address.is_private or address.is_link_local


def check_local_backend(url: str) -> str:
    """Devuelve `esquema://anfitrión[:puerto]`, o `ValueError` si no es loopback ni LAN o si
    trae ruta, consulta o fragmento (la ruta de las lecturas la pone la pasarela)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"--backend no es una URL http(s): {url!r}")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.params:
        raise ValueError(f"--backend solo lleva esquema, anfitrión y puerto: {url!r}")
    if parsed.username or parsed.password:
        raise ValueError("--backend no lleva credenciales")
    host = parsed.hostname
    if host != "localhost":
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            raise ValueError(
                f"--backend tiene que ser localhost o una IP de loopback o de la red local de la "
                f"nave, no un nombre ({host!r}): la pasarela no sale a internet"
            ) from None
        if not _is_local(address):
            raise ValueError(
                f"--backend {host} no es de loopback ni de la red local: la pasarela no sale a "
                f"internet")
    return f"{parsed.scheme}://{parsed.netloc}"


def post_batch(client: httpx.Client, backend: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Manda un lote. La cabecera de consola no autentica nada (`api/console_header.py`); se pone
    por si la ruta la exige, como la consola en todos sus `POST`."""
    response = client.post(
        f"{backend}{SIGHTINGS_PATH}", json=payload, headers={"X-EMMA-Console": "1"})
    response.raise_for_status()
    try:
        result = response.json()
    except ValueError:
        raise BadAnswer("el backend no respondió JSON") from None
    if not isinstance(result, dict):
        raise BadAnswer("el backend no respondió un objeto JSON")
    return result


class BadAnswer(Exception):
    """El backend aceptó la petición pero su respuesta no tiene la forma del contrato."""


# --- Reproducción de grabaciones ------------------------------------------------------------


def _hex_bytes(value: Any, where: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError(f"{where}: se esperaba hexadecimal")
    return bytes.fromhex(value)


def _moment(value: Any, where: str) -> dt.datetime:
    if not isinstance(value, str):
        raise ValueError(f"{where}: falta «at»")
    moment = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError(f"{where}: «at» sin zona horaria")
    return moment


def read_recording(path: Path) -> list[Reading]:
    """Lee un JSONL de anuncios. Los que no son balizas reconocidas se saltan; una línea mal
    formada es un error con su número de línea."""
    readings = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            where = f"{path.name}:{number}"
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError(f"{where}: se esperaba un objeto JSON")
                manufacturer = {_company_key(str(key)): _hex_bytes(value, where)
                                for key, value in (record.get("manufacturer_data") or {}).items()}
                service = {str(key): _hex_bytes(value, where)
                           for key, value in (record.get("service_data") or {}).items()}
                rssi = float(record["rssi"])
                at = _moment(record.get("at"), where)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{where}: anuncio mal formado ({exc})") from None
            anchor = anchor_from_advertisement(manufacturer, service)
            if anchor is not None:
                readings.append(Reading(anchor, rssi, at))
    return readings


# --- Escucha en vivo ----------------------------------------------------------------------


def bleak_available() -> bool:
    return importlib.util.find_spec("bleak") is not None


def _passive_scanner_kwargs() -> dict[str, Any]:
    """Argumentos del escáner pasivo. En Linux (BlueZ) el pasivo exige patrones: solo se pide lo
    que puede ser iBeacon o Eddystone."""
    kwargs: dict[str, Any] = {"scanning_mode": "passive"}
    if sys.platform.startswith("linux"):
        from bleak.assigned_numbers import AdvertisementDataType
        from bleak.backends.bluezdbus.advertisement_monitor import OrPattern

        kwargs["bluez"] = {"or_patterns": [
            OrPattern(0, AdvertisementDataType.MANUFACTURER_SPECIFIC_DATA,
                      b"\x4c\x00\x02\x15"),
            OrPattern(0, AdvertisementDataType.SERVICE_DATA_UUID16, b"\xaa\xfe\x00"),
        ]}
    return kwargs


async def listen(window_s: float, on_window: Callable[[list[Reading]], None]) -> None:
    """Escucha hasta que se interrumpa y entrega lo oído cada `window_s` segundos."""
    from bleak import BleakScanner

    heard: list[Reading] = []

    def detected(_device: Any, advertisement: Any) -> None:
        anchor = anchor_from_advertisement(
            advertisement.manufacturer_data or {}, advertisement.service_data or {})
        rssi = advertisement.rssi
        if anchor is not None and rssi is not None:
            heard.append(Reading(anchor, float(rssi), dt.datetime.now(dt.UTC)))

    # Las ventanas van por plazos fijos del reloj monótono y el envío corre aparte: un backend
    # lento no estira la ventana siguiente. Al parar (Ctrl+C) se manda lo oído en la última.
    loop = asyncio.get_running_loop()
    sending: set[asyncio.Task[None]] = set()

    def flush() -> None:
        batch, heard[:] = list(heard), []
        task = asyncio.create_task(asyncio.to_thread(on_window, batch))
        sending.add(task)
        task.add_done_callback(sending.discard)

    try:
        async with BleakScanner(detection_callback=detected, **_passive_scanner_kwargs()):
            deadline = loop.time()
            while True:
                deadline += window_s
                await asyncio.sleep(max(0.0, deadline - loop.time()))
                flush()
    finally:
        pending = list(sending)
        batch, heard[:] = list(heard), []
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        on_window(batch)


# --- Programa ---------------------------------------------------------------------------------


def _emit(payloads: list[dict[str, Any]], args: argparse.Namespace,
          client: httpx.Client | None) -> bool:
    for payload in payloads:
        if args.dry_run or client is None:
            print(json.dumps(payload, ensure_ascii=False))
            continue
        try:
            result = post_batch(client, args.backend, payload)
        except (httpx.HTTPError, BadAnswer) as exc:
            print(f"lote no aceptado por {args.backend}: {exc}", file=sys.stderr)
            return False
        print(json.dumps({"ledger_index": result.get("ledger_index"),
                          "accepted": result.get("accepted"),
                          "unknown_anchors": result.get("unknown_anchors", [])},
                         ensure_ascii=False))
    return True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pasarela pasiva de anclas de módulo (BLE) hacia el backend de EMMA.")
    parser.add_argument("--subject", required=True, help="tripulante que lleva la pasarela")
    parser.add_argument("--device", help="identificador de la pasarela o del wearable")
    parser.add_argument("--backend", default=DEFAULT_BACKEND,
                        help="backend de EMMA en loopback o LAN (por defecto %(default)s)")
    parser.add_argument("--window", type=float, default=DEFAULT_WINDOW_S,
                        help="segundos por ventana (por defecto %(default)s; sin respaldo: "
                             "calibrar en cada nave)")
    parser.add_argument("--from-file", type=Path,
                        help="reproduce anuncios grabados (JSONL) en vez de escuchar la radio")
    parser.add_argument("--dry-run", action="store_true",
                        help="imprime los lotes en vez de mandarlos")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not (args.window > 0 and math.isfinite(args.window)):
        print("--window tiene que ser un número de segundos positivo", file=sys.stderr)
        return EXIT_USAGE
    try:
        args.backend = check_local_backend(args.backend)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE

    if args.from_file is not None:
        try:
            readings = read_recording(args.from_file)
        except (OSError, ValueError) as exc:
            print(f"no se pudo leer la grabación: {exc}", file=sys.stderr)
            return EXIT_USAGE
        sightings = [s for window in split_windows(readings, args.window)
                     for s in summarize_window(window)]
        if not sightings:
            print("la grabación no tiene anuncios de anclas reconocidas", file=sys.stderr)
            return EXIT_OK
        payloads = build_payloads(sightings, args.subject, args.device)
        if args.dry_run:
            return EXIT_OK if _emit(payloads, args, None) else EXIT_FAILED
        with httpx.Client(timeout=10.0) as replay_client:
            return EXIT_OK if _emit(payloads, args, replay_client) else EXIT_FAILED

    if not bleak_available():
        print(UNAVAILABLE_TEXT, file=sys.stderr)
        return EXIT_UNAVAILABLE

    client = None if args.dry_run else httpx.Client(timeout=10.0)

    def on_window(batch: list[Reading]) -> None:
        sightings = summarize_window(batch)
        if sightings:
            # En vivo, un lote rechazado se cuenta en la consola de errores y se sigue
            # escuchando: parar la pasarela perdería también las ventanas siguientes.
            _emit(build_payloads(sightings, args.subject, args.device), args, client)

    try:
        asyncio.run(listen(args.window, on_window))
    except KeyboardInterrupt:
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001 — la radio del sistema falla de muchas formas
        print(f"no se pudo escuchar en modo pasivo: {exc}. La pasarela no cae al escaneo "
              f"activo porque emitiría.", file=sys.stderr)
        return EXIT_FAILED
    finally:
        if client is not None:
            client.close()
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
