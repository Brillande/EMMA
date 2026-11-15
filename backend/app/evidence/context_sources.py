"""Las fuentes del contexto de producto: cuáles se leyeron, cuáles no y para qué las tiene EMMA.

La especificación del equipo (§17) lista las direcciones de las que sale su contexto, y la primera
es el enunciado del reto. Hasta la decimoséptima ronda varias no tenían ficha en el registro de
evidencia —el enunciado entre ellas: ningún fichero del repositorio nombraba su sitio—, y la base
de conocimiento (§11.3) daba los dos posts de X por irrecuperables. Una lista de fuentes que nadie
ha abierto acaba citándose como si estuviera leída. Y la lectura del 2026-10-26 enseñó que el
enunciado del reto no se puede leer todavía: el sitio devuelve su página de error, y sus preguntas
frecuentes dicen que los enunciados completos salen el 28 de octubre.

La decimoctava ronda (U19) leyó las seis direcciones de §17 que seguían sin ficha y metió aquí,
junto a la carta de Stuhlinger, las dos frases del «espacio a la Tierra» de la conversación de
ideación: la del origen de HACCP, copiada del informe de comida del HRP, que ya tenía ficha; y la
de la estación como plataforma de atención médica miniaturizada, que se buscó en NASA y no se
encontró, y se dice así en vez de repetirse. Astroquery y ZeroKeyUSB entran con su ficha para decir
qué son, no porque EMMA adopte nada de ellos.

La decimonovena ronda (U2, 2026-10-31) leyó por fin el enunciado: el sitio lo sirve en otra
dirección (`/2026/challenges/health-monitoring-software/`), no en la que lista la especificación
§17, que sigue dando «Oops! Page Not Found». La ficha conserva la dirección de §17 —es la que el
equipo listó y la que la prueba contrasta— y dice dónde está de verdad. Como esa lectura no es del
mismo día que las demás, cada fuente puede llevar su propia fecha (`read_on`), y es esa la que
tiene que estar en su ficha; `null` quiere decir «el día del fichero».

Lo leído vive en `data/context_sources_read.json` y este cargador es la defensa:

- cada fuente cita una ficha del registro que dice que se leyó (o se buscó) ese día: el del
  fichero o, si lo trae, el suyo;
- una fuente de las listas del equipo dice con qué rótulo aparece; una que no está en ellas,
  por qué se añadió;
- lo leído en parte o no leído dice por qué: no se calla ni se rellena.

La población de cada fuente la dice su ficha, no este inventario: casi ninguna de estas fuentes es
un estudio (el informe de comida del HRP es un informe de evidencia y su ficha dice sobre quién se
midió), y la portada de OSDR, que guarda datos de personas y de animales, la declara no
aplicable y remite a la ficha de cada estudio.

Es un inventario: no entra en el análisis, en el riesgo ni en ninguna alerta (invariante 5), y no
sale a la red; la lectura se hizo una vez, en Tierra.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from app.core import i18n
from app.evidence import registry

CONTEXT_SOURCES_PATH = Path(__file__).resolve().parents[1] / "data" / "context_sources_read.json"

# Qué se pudo leer de cada fuente. La frase se escribe aquí, no en la interfaz.
STATUSES: dict[str, str] = {
    "read": "leída",
    "partial": "leída en parte",
    "not_read": "buscada y no leída",
}
# El inglés, en una tabla hermana con las mismas claves (las claves de estado no se traducen).
STATUSES_EN: dict[str, str] = {
    "read": "read",
    "partial": "read in part",
    "not_read": "searched for and not read",
}
SOURCE_FIELDS = frozenset({
    "ref", "lists", "listed_as", "why_added", "status", "not_read", "emma_use", "read_on",
})
LIST_FIELDS = frozenset({"id", "document", "section", "title"})
# La fecha de una lectura, completa: la misma convención que las fichas del registro.
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# La fuente por la que existe este inventario: su fecha de lectura es la que la nota enseña.
CHALLENGE_REF = "space-apps-2026-health-monitoring-challenge"

NOTE = (
    "Las fuentes del contexto del equipo, con lo que se pudo leer de cada una y lo que no, y su "
    "motivo. El enunciado del reto se leyó el {day}; sus requisitos, uno por fila, están en "
    "compliance/challenge-coverage.md. Inventario: no interviene en el estado de la tripulación "
    "ni en ninguna alerta."
)
i18n.en(
    NOTE,
    "The sources of the team's context, with what could be read from each and what could not, "
    "and why. The challenge statement was read on {day}; its requirements, one per row, are in "
    "compliance/challenge-coverage.md. Inventory: it plays no part in the crew status or in any "
    "alert.",
)


class ContextSourcesError(ValueError):
    """Lo leído de las fuentes del contexto no cumple su contrato: no se sirve."""


def _text(item: dict[str, Any], field: str) -> bool:
    value = item.get(field)
    return isinstance(value, str) and bool(value.strip())


def _day(value: Any, where: str) -> str:
    """Una fecha de lectura: ISO 8601 completo (AAAA-MM-DD) y un día que existe en el calendario.

    Ninguna de las dos comprobaciones basta sola: `date.fromisoformat` acepta desde Python 3.11
    «20261031» y las semanas ISO, y la forma sola deja pasar «2026-13-45».
    """
    if not (isinstance(value, str) and _ISO_DATE.fullmatch(value)):
        raise ContextSourcesError(f"{where}: `read_on` va en ISO 8601 (AAAA-MM-DD)")
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        raise ContextSourcesError(
            f"{where}: `read_on` {value} no es un día del calendario (ISO 8601)"
        ) from None
    return value


def _fields(key: str, item: Any, expected: frozenset[str]) -> None:
    if not isinstance(item, dict):
        raise ContextSourcesError(f"{key}: se esperaba un objeto con {sorted(expected)}")
    if missing := sorted(expected - item.keys()):
        raise ContextSourcesError(f"{key}: faltan campos {missing}: lo que no hay va como null")
    if extra := sorted(item.keys() - expected):
        raise ContextSourcesError(f"{key}: campos desconocidos {extra}")


def _validate_source(item: Any, lists: set[str], read_on: str) -> None:
    key = str(item.get("ref", "?")) if isinstance(item, dict) else "?"
    _fields(key, item, SOURCE_FIELDS)
    try:
        ref = registry.get(item["ref"])
    except registry.RegistryError as error:  # una ficha que no está en el registro no se cita
        raise ContextSourcesError(f"{key}: {error}") from None
    # Una fuente leída otro día lo dice con su fecha; si no, vale la del fichero.
    own = item["read_on"]
    day = _day(own, key) if own is not None else read_on
    if day not in (ref.notes or ""):
        raise ContextSourcesError(
            f"{key}: la ficha no dice que se leyera (o se buscara) el {day}"
        )
    named = item["lists"]
    if not isinstance(named, list) or not all(isinstance(name, str) for name in named):
        raise ContextSourcesError(f"{key}: `lists` es una lista de identificadores, aunque vacía")
    if unknown := sorted(set(named) - lists):
        raise ContextSourcesError(f"{key}: listas desconocidas {unknown}")
    if len(set(named)) != len(named):
        raise ContextSourcesError(f"{key}: una lista repetida")
    # De una lista del equipo, con su rótulo; de fuera, con su motivo. Nunca las dos cosas.
    if named:
        if not _text(item, "listed_as") or item["why_added"] is not None:
            raise ContextSourcesError(f"{key}: de una lista del equipo, con su rótulo y sin motivo")
    elif item["listed_as"] is not None or not _text(item, "why_added"):
        raise ContextSourcesError(f"{key}: fuera de las listas del equipo, con su motivo")
    if item["status"] not in STATUSES:
        raise ContextSourcesError(f"{key}: estado desconocido {item['status']!r}")
    if item["status"] == "read":
        if item["not_read"] is not None:
            raise ContextSourcesError(f"{key}: lo leído entero no lleva motivo de no leerse")
    elif not _text(item, "not_read"):
        raise ContextSourcesError(f"{key}: lo leído en parte o no leído dice por qué")
    if not _text(item, "emma_use"):
        raise ContextSourcesError(f"{key}: falta para qué la tiene EMMA, aunque sea para nada")


def validate(raw: dict[str, Any]) -> dict[str, Any]:
    """Rechaza una fuente sin ficha leída, sin origen o con lo no leído callado."""
    # La fecha del fichero se comprueba igual que la propia de una fuente: es la que más se sirve.
    read_on = _day(raw.get("read_on"), "el fichero")
    lists = raw.get("lists")
    if not isinstance(lists, list) or not lists:
        raise ContextSourcesError("ninguna lista de fuentes del equipo")
    ids: set[str] = set()
    for item in lists:
        _fields(str(item.get("id", "?")) if isinstance(item, dict) else "?", item, LIST_FIELDS)
        if not all(_text(item, field) for field in sorted(LIST_FIELDS)):
            raise ContextSourcesError(f"{item.get('id')}: lista con un campo vacío")
        ids.add(item["id"])
    sources = raw.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ContextSourcesError("ninguna fuente")
    seen: set[str] = set()
    for item in sources:
        _validate_source(item, ids, read_on)
        if item["ref"] in seen:
            raise ContextSourcesError(f"{item['ref']}: fuente repetida")
        seen.add(item["ref"])
    if CHALLENGE_REF not in seen:
        raise ContextSourcesError("falta el enunciado del reto: por él existe este inventario")
    return raw


def _read_on(item: dict[str, Any], raw: dict[str, Any]) -> str:
    """El día en que se leyó esta fuente: el suyo o, si no trae uno, el del fichero."""
    return str(item["read_on"] or raw["read_on"])


def _note(raw: dict[str, Any]) -> str:
    """La nota de la ruta, con la fecha del enunciado tomada del inventario, no escrita a mano."""
    statement = next(item for item in raw["sources"] if item["ref"] == CHALLENGE_REF)
    return i18n.loc(NOTE).format(day=_read_on(statement, raw))


@cache
def read() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(CONTEXT_SOURCES_PATH.read_text(encoding="utf-8"))
    return validate(raw)


def cited_refs() -> frozenset[str]:
    """Las fichas del registro de las que se dice qué se leyó y para qué las tiene EMMA."""
    return frozenset(item["ref"] for item in read()["sources"])


def payload() -> dict[str, Any]:
    """Las fuentes como se sirven: cada una con su ficha resuelta y la frase de su estado."""
    # Una copia en el idioma de la petición, después de validar: la caché guarda el castellano.
    raw = i18n.localized(read(), CONTEXT_SOURCES_PATH)
    return {
        "note": _note(raw),
        "read_on": raw["read_on"],
        "lists": [dict(item) for item in raw["lists"]],
        "sources": [
            {
                "ref": item["ref"],
                "lists": list(item["lists"]),
                "listed_as": item["listed_as"],
                "why_added": item["why_added"],
                "status": item["status"],
                "status_text": i18n.tr(STATUSES[item["status"]], STATUSES_EN[item["status"]]),
                "not_read": item["not_read"],
                "emma_use": item["emma_use"],
                "read_on": _read_on(item, raw),
                "card": registry.get(item["ref"]).to_dict(),
            }
            for item in raw["sources"]
        ],
    }
