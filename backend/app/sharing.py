"""Qué se comparte y qué no: la tabla, por categoría de dato, y su contrato.

Por qué existe: la privacidad de EMMA estaba repartida en una docena de sitios —la lista blanca de
`core/egress.py`, el corte del retardo que pide la consola de Tierra, la cámara y la escucha de
la interfaz, la memoria del asistente, las trazas sin contenido personal— y cada uno lo contaba en
su docstring. Ninguna pantalla decía a la tripulación, en un solo sitio, qué sale de la nave, qué
ve Tierra y qué se queda a bordo; y lo que no se contaba en ningún sitio era lo que EMMA **no**
hace: no hay notas personales que Tierra no vea, y el corte del retardo lo pide la consola, no lo
impone el backend. Una vista de privacidad que solo dice lo bueno engaña (invariante 6).

La tabla vive en `data/data_sharing.json` y este cargador es la defensa al leerla:

- cada fila dice a dónde llega el dato (`DESTINATIONS`) y si lo impone el código (`ENFORCEMENT`);
- lo que el código impone del todo cita al menos un símbolo, una prueba o un fichero de la consola;
- lo que impone en parte cita algo **y** dice qué queda fuera; lo que no impone no cita nada (no
  hay qué citar) y dice por qué;
- los propósitos y los hosts de internet son los de `egress.ALLOWLIST`, ni uno más ni uno menos:
  la tabla no puede prometer menos salidas de las que hay.

El resto de lo que la tabla afirma se comprueba en las pruebas, porque necesita la aplicación
entera o los ficheros de la interfaz, que no viajan en el paquete: las rutas con corte contra las
de la aplicación, cada símbolo y prueba citados contra su módulo (`tests/test_sharing.py`), y cada
fichero de la consola y cada panel que Tierra no monta contra los `.tsx`
(`tests/test_sharing_console.py`).

Es un inventario: no entra en el análisis, en el riesgo ni en ninguna alerta (invariante 5), y no
sale a la red. El texto se escribe aquí y en la tabla, no en la interfaz.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from app.core import egress, i18n
from app.core.config import Settings

SHARING_PATH = Path(__file__).resolve().parent / "data" / "data_sharing.json"

# A dónde llega cada dato, en el orden en que se lee: de lo que más lejos va a lo que no se guarda.
DESTINATIONS = ("internet", "ground", "board", "device", "nowhere")
ENFORCEMENT = ("code", "partial", "none")
DIRECTIONS = ("down", "up")
ITEM_FIELDS = frozenset({
    "id", "title", "destination", "text", "enforcement", "limit",
    "code", "tests", "console", "ground_absent",
})
POINTER_FIELDS = ("code", "tests", "console", "ground_absent")
PURPOSE_FIELDS = frozenset({"purpose", "what", "carries", "hosts"})

# Lo que se dice del modo sin red ahora mismo. La frase, aquí; la interfaz la enseña tal cual.
OFFLINE_NOW = {
    True: "Ahora: modo sin red. No sale nada a internet.",
    False: "Ahora: con red. Solo salen las consultas de los propósitos de abajo.",
}
i18n.en_many({
    OFFLINE_NOW[True]: "Now: offline mode. Nothing goes out to the internet.",
    OFFLINE_NOW[False]: "Now: online. Only the queries for the purposes below go out.",
})


class SharingError(ValueError):
    """La tabla de lo que se comparte no cumple su contrato: no se sirve."""


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SharingError(f"{where}: falta el texto")
    return value


def _labelled(rows: Any, ids: tuple[str, ...], where: str) -> dict[str, str]:
    """Una lista de `{id, label}` con exactamente los ids esperados, en su orden."""
    if not isinstance(rows, list) or [row.get("id") for row in rows] != list(ids):
        raise SharingError(f"{where}: tienen que ser {', '.join(ids)}, en ese orden")
    return {row["id"]: _text(row.get("label"), f"{where} {row['id']}") for row in rows}


def _check_item(item: Any) -> None:
    if not isinstance(item, dict) or set(item) != ITEM_FIELDS:
        raise SharingError(f"una fila no tiene los campos {sorted(ITEM_FIELDS)}: {item!r}")
    where = f"fila {item['id']!r}"
    _text(item["title"], where)
    _text(item["text"], where)
    if item["destination"] not in DESTINATIONS:
        raise SharingError(f"{where}: destino desconocido {item['destination']!r}")
    if item["enforcement"] not in ENFORCEMENT:
        raise SharingError(f"{where}: grado desconocido {item['enforcement']!r}")
    for field in POINTER_FIELDS:
        if not isinstance(item[field], list):
            raise SharingError(f"{where}: {field} tiene que ser una lista")
    cited = sum(len(item[field]) for field in POINTER_FIELDS)
    limit = item["limit"]
    if limit is not None:
        _text(limit, f"{where}, límite")
    enforcement = item["enforcement"]
    if enforcement == "code" and cited == 0:
        raise SharingError(f"{where}: dice que lo impone el código y no cita dónde")
    if enforcement == "partial" and (cited == 0 or limit is None):
        raise SharingError(f"{where}: en parte exige citar dónde y decir qué queda fuera")
    if enforcement == "none" and (cited > 0 or limit is None):
        raise SharingError(f"{where}: lo que el código no impone no cita código y dice por qué")


def _check_internet(internet: Any) -> None:
    purposes = internet.get("purposes") if isinstance(internet, dict) else None
    if not isinstance(purposes, list):
        raise SharingError("internet: faltan los propósitos")
    declared: dict[str, frozenset[str]] = {}
    for row in purposes:
        if not isinstance(row, dict) or set(row) != PURPOSE_FIELDS:
            raise SharingError(
                f"un propósito no tiene los campos {sorted(PURPOSE_FIELDS)}: {row!r}"
            )
        _text(row["what"], f"propósito {row['purpose']!r}")
        _text(row["carries"], f"propósito {row['purpose']!r}")
        if row["purpose"] in declared:
            raise SharingError(f"propósito repetido: {row['purpose']!r}")
        declared[row["purpose"]] = frozenset(row["hosts"])
    # La tabla contra la puerta: lo que sale es lo de `egress`, no lo que diga este fichero.
    if declared != egress.ALLOWLIST:
        missing = sorted(set(egress.ALLOWLIST) - set(declared))
        extra = sorted(set(declared) - set(egress.ALLOWLIST))
        hosts = sorted(
            purpose for purpose in set(declared) & set(egress.ALLOWLIST)
            if declared[purpose] != egress.ALLOWLIST[purpose]
        )
        raise SharingError(
            "los propósitos de internet no son los de la lista blanca de core/egress.py: "
            f"faltan {missing}, sobran {extra}, otros hosts en {hosts}"
        )
    clients = internet.get("http_clients")
    if not isinstance(clients, list) or not clients:
        raise SharingError("internet: faltan los módulos que abren un cliente HTTP")
    for client in clients:
        _text(client.get("file"), "cliente HTTP")
        _text(client.get("why"), f"cliente HTTP {client.get('file')!r}")


def _check_cut(cut: Any) -> None:
    if not isinstance(cut, dict):
        raise SharingError("falta el corte del retardo")
    _text(cut.get("note"), "corte del retardo")
    _labelled(cut.get("directions"), DIRECTIONS, "sentidos del corte")
    paths = [route.get("path") for route in cut.get("routes", [])]
    if not paths or len(set(paths)) != len(paths):
        raise SharingError("corte del retardo: rutas vacías o repetidas")
    for route in cut["routes"]:
        if route.get("direction") not in DIRECTIONS:
            raise SharingError(f"ruta {route.get('path')!r}: sentido desconocido")


def check(table: Any) -> dict[str, Any]:
    """La tabla, si cumple su contrato; si no, `SharingError` con el primer motivo."""
    if not isinstance(table, dict):
        raise SharingError("la tabla tiene que ser un objeto")
    _text(table.get("note"), "nota")
    _labelled(table.get("destinations"), DESTINATIONS, "destinos")
    _labelled(table.get("enforcement"), ENFORCEMENT, "grados")
    items = table.get("items")
    if not isinstance(items, list) or not items:
        raise SharingError("la tabla no tiene filas")
    for item in items:
        _check_item(item)
    ids = [item["id"] for item in items]
    if len(set(ids)) != len(ids):
        raise SharingError("hay filas con el mismo id")
    _check_internet(table.get("internet"))
    _check_cut(table.get("ground_cut"))
    return table


@cache
def read() -> dict[str, Any]:
    """La tabla leída y comprobada, una vez."""
    try:
        raw = json.loads(SHARING_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SharingError(f"{SHARING_PATH.name} no se puede leer: {error}") from error
    return check(raw)


def _pointer(item: dict[str, Any]) -> list[str]:
    """Dónde lo impone el código, dicho como se busca: módulo y símbolo, prueba o fichero."""
    cited = [
        f"{entry['module']}.{entry['symbol']}" if entry["symbol"] else entry["module"]
        for entry in item["code"]
    ]
    cited += list(item["tests"])
    cited += [entry["file"] for entry in item["console"]]
    cited += [
        i18n.tr(
            f"{path} (no lo monta la consola de Tierra)",
            f"{path} (the Earth console does not mount it)",
        )
        for path in item["ground_absent"]
    ]
    return cited


def payload(settings: Settings) -> dict[str, Any]:
    """La tabla para las dos consolas, con el estado del modo sin red de ahora.

    La tabla leída y comprobada se queda en castellano (`read` está cacheada): su inglés, el del
    hermano `data_sharing.en.json`, se pone aquí, al servir. Los ids, los hosts, las rutas y lo
    que se cita del código no se traducen.
    """
    table = i18n.localized(read(), SHARING_PATH)
    destinations = {row["id"]: row["label"] for row in table["destinations"]}
    enforcement = {row["id"]: row["label"] for row in table["enforcement"]}
    order = {key: index for index, key in enumerate(DESTINATIONS)}
    items = sorted(table["items"], key=lambda item: order[item["destination"]])
    directions = {row["id"]: row["label"] for row in table["ground_cut"]["directions"]}
    return {
        "note": table["note"],
        "destinations": table["destinations"],
        "items": [
            {
                "id": item["id"],
                "title": item["title"],
                "destination": item["destination"],
                "destination_text": destinations[item["destination"]],
                "text": item["text"],
                "enforcement": item["enforcement"],
                "enforcement_text": enforcement[item["enforcement"]],
                "limit": item["limit"],
                "enforced_by": _pointer(item),
            }
            for item in items
        ],
        "internet": {
            "offline": settings.offline,
            "offline_text": i18n.loc(OFFLINE_NOW[settings.offline]),
            # Los hosts, de la puerta: la tabla ya se comprobó contra ella al leerse.
            "purposes": [
                {
                    "purpose": row["purpose"],
                    "what": row["what"],
                    "carries": row["carries"],
                    "hosts": sorted(egress.ALLOWLIST[row["purpose"]]),
                }
                for row in table["internet"]["purposes"]
            ],
        },
        "ground_cut": {
            "note": table["ground_cut"]["note"],
            "routes": [
                {
                    "path": route["path"],
                    "direction": route["direction"],
                    "direction_text": directions[route["direction"]],
                }
                for route in table["ground_cut"]["routes"]
            ],
        },
    }
