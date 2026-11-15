"""Contramedidas en investigación: a la vista, con su fuente, y sin ofrecerse jamás.

La base de conocimiento (§4) pone en la fila de visión y fluidos «contramedidas de fluid shift en
investigación» y, en la de hueso y músculo, la «gravedad artificial»; su §3.2 cuenta que AGBRESA
comparó 60 días de reposo en cama con dos grupos de centrifugación. La conversación de ideación,
leyendo el PDF de NASA «The Human Body in Space» (2022), pone en la matriz RIDGE la realidad
virtual para el aislamiento y «LBNP, cuffs» para la gravedad. La biblioteca de contramedidas
(`advisor/countermeasures.py`) no tenía ninguna de estas, y con razón: no son
acciones que una tripulación pueda adoptar hoy con lo que lleva a bordo, y la biblioteca exige a
cada entrada tiempo de tripulación, recursos, ventana de seguimiento y respaldo.

El riesgo de meterlas ahí es doble. Una tarjeta de recomendación con «presión negativa en la
parte inferior del cuerpo» se leería como algo que EMMA propone hacer; y la huella de reglas
(`core/versioning.py`) resume `countermeasures.json` entero, así que añadirlas cambiaría la versión
de las reglas sin cambiar ninguna decisión. Por eso viven en un fichero aparte
(`data/countermeasures_research.json`) que solo lee este módulo, sin familia, sin dominio clínico
y sin nada que el asesor sepa usar. Que no se cuelen tiene prueba
(`tests/test_research_countermeasures.py`): ningún módulo del motor importa este, la huella sigue
resumiendo solo la biblioteca, el asesor no ofrece ninguna de estas en ningún dominio ni nivel, el
estado servido no nombra ninguna, y adoptar una se rechaza (no estaba recomendada) y declinarla
también (contramedida desconocida).

Lo que sí hace este módulo es la defensa de lo leído: una entrada sin frase literal, sin página o
sin ficha del registro no se sirve; un peligro RIDGE que no existe tampoco; un id que choque con la
biblioteca, tampoco (se leería como la misma acción). Los textos que escribe EMMA —nombre, qué
ataca, estado, lo que la fuente dice del vuelo, lo no encontrado— pasan el linter de lenguaje
(`text_guard`, invariante 7). Las frases literales no: son de la fuente, en su idioma, y no se
reescriben. Lo que la fuente no dice (si es equipo de vuelo, quién la usa hoy, cuánto cuesta) se
declara, no se rellena.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Iterable
from functools import cache
from pathlib import Path
from typing import Any

from app.core import i18n
from app.evidence import registry
from app.evidence.instruments_read import EXTENTS
from app.evidence.read_contract import check_sources
from app.ingest.codes import Ridge
from app.text_guard import check

RESEARCH_PATH = Path(__file__).resolve().parents[1] / "data" / "countermeasures_research.json"

NOTE = (
    "Contramedidas en investigación: se enseñan para saber que existen y en qué estado las deja "
    "su fuente. EMMA no las ofrece: no entran en ninguna recomendación ni en la huella de reglas, "
    "no tienen familia y no se pueden adoptar ni declinar."
)
i18n.en(
    NOTE,
    "Countermeasures under research: they are shown so that it is known that they exist and in "
    "what state their source leaves them. EMMA does not offer them: they enter no "
    "recommendation and are not part of the rules fingerprint, they have no family and they "
    "cannot be adopted or declined.",
)
OFFERED = False
# Los campos que escribe EMMA: los que pasan el linter. La frase literal es de la fuente.
AUTHORED = ("name", "targets", "status", "flight_note")
_READ_ON = re.compile(r"\d{4}-\d{2}-\d{2}")


class ResearchError(ValueError):
    """Lo leído no cumple su contrato: no se sirve."""


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _guarded(where: str, texts: Iterable[str]) -> None:
    for text in texts:
        found = check(text)
        if found:
            raise ResearchError(
                f"{where}: el texto suena a pauta u orden ({found[0].category}): {text!r}"
            )


def _guard_what(ref_id: str, what: str) -> None:
    """Lo que EMMA escribe de cuánto se leyó de una fuente también pasa el linter."""
    _guarded(ref_id, (what,))


def _entry(item: dict[str, Any], sources: dict[str, Any]) -> None:
    key = item.get("id", "?")
    for field in ("id", *AUTHORED):
        if not _text(item.get(field)):
            raise ResearchError(f"{key}: falta `{field}`")
    try:
        Ridge(str(item.get("ridge")))
    except ValueError:
        raise ResearchError(f"{key}: peligro RIDGE desconocido: {item.get('ridge')!r}") from None
    quotes = item.get("quotes")
    if not isinstance(quotes, list) or not quotes:
        raise ResearchError(f"{key}: sin frase de su fuente no se sirve")
    for quote in quotes:
        if not isinstance(quote, dict) or not all(
            _text(quote.get(field)) for field in ("ref", "where", "quote")
        ):
            raise ResearchError(f"{key}: una frase sin `ref`, `where` o `quote`")
        if quote["ref"] not in sources:
            raise ResearchError(f"{key}: de {quote['ref']!r} no se declara cuánto se leyó")
    _guarded(key, (item[field] for field in AUTHORED))
    # La página y la sección también las escribe EMMA: salen bajo cada frase.
    _guarded(key, (quote["where"] for quote in quotes))


def validate(raw: dict[str, Any], library_ids: Iterable[str] = ()) -> dict[str, Any]:
    """Rechaza lo que no se pueda sostener con la fuente delante.

    `library_ids` son los de la biblioteca de contramedidas: un id que coincida se leería como la
    misma acción, que sí se ofrece.
    """
    if not isinstance(raw, dict):
        raise ResearchError(
            "el fichero tiene que ser un objeto con `read_on`, `sources` y `entries`"
        )
    # AAAA-MM-DD y nada más: `fromisoformat` admite también «20261023» o «2026-W43-5», que la
    # interfaz (`formatSourceDate`) no pinta.
    try:
        if not _READ_ON.fullmatch(raw["read_on"]):
            raise ValueError(raw["read_on"])
        dt.date.fromisoformat(raw["read_on"])
    except (KeyError, TypeError, ValueError):
        raise ResearchError(
            "falta `read_on`: una lectura sin fecha no se puede contrastar"
        ) from None
    def own_read_on(value: Any, ref_id: str) -> None:
        """El día propio de una fuente leída después (decimoctava ronda, U15): sin él, sus frases
        se servirían con el día del fichero, que no es el suyo. AAAA-MM-DD, y no anterior al del
        fichero: antes de ese día no se había leído nada."""
        if not (isinstance(value, str) and _READ_ON.fullmatch(value)):
            raise ResearchError(f"{ref_id}: `read_on` {value!r} no es una fecha AAAA-MM-DD")
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            raise ResearchError(f"{ref_id}: `read_on` {value!r} no es una fecha") from None
        if value < raw["read_on"]:
            raise ResearchError(
                f"{ref_id}: `read_on` anterior a la lectura del fichero ({raw['read_on']})"
            )

    # El contrato común de las fuentes (`read_contract`), con el linter sobre lo que EMMA escribe
    # de cada una y el día propio de la que lo lleve.
    sources = check_sources(
        raw, ResearchError, EXTENTS, own_read_on=own_read_on, authored=_guard_what
    )
    entries = raw.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ResearchError("sin entradas")
    seen: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            raise ResearchError(f"una entrada que no es un objeto: {item!r}")
        _entry(item, sources)
        if item["id"] in seen:
            raise ResearchError(f"{item['id']}: identificador repetido")
        seen.add(item["id"])
    # Una ficha declarada leída que ninguna frase cita se serviría como si respaldara algo.
    quoted = {quote["ref"] for item in entries for quote in item["quotes"]}
    unquoted = sorted(set(sources) - quoted)
    if unquoted:
        raise ResearchError(f"fichas declaradas leídas que ninguna frase cita: {unquoted}")
    clash = seen & set(library_ids)
    if clash:
        raise ResearchError(
            f"ids que también están en la biblioteca de contramedidas: {sorted(clash)}"
        )
    for field in ("not_found", "read_not_included"):
        lines = raw.get(field)
        if not isinstance(lines, list) or not all(_text(line) for line in lines):
            raise ResearchError(f"`{field}` tiene que ser una lista de frases")
        _guarded(field, lines)
    return raw


@cache
def read() -> dict[str, Any]:
    # La biblioteca se importa aquí y no arriba: este módulo la lee para no chocar con ella, y la
    # biblioteca no sabe nada de este (ni debe).
    from app.advisor.countermeasures import library

    raw: dict[str, Any] = json.loads(RESEARCH_PATH.read_text(encoding="utf-8"))
    return validate(raw, library())


def cited_refs() -> frozenset[str]:
    """Las fichas del registro de las que se declara lectura."""
    return frozenset(read()["sources"])


def ids() -> frozenset[str]:
    return frozenset(item["id"] for item in read()["entries"])


def _quote(quote: dict[str, Any]) -> dict[str, Any]:
    ref = registry.get(quote["ref"])
    return {
        "ref": ref.id,
        "title": ref.title,
        "source": ref.source,
        "url": ref.url,
        "where": quote["where"],
        "quote": quote["quote"],
    }


def overview() -> dict[str, Any]:
    """Lo leído, tal como se sirve. `offered` es siempre falso y no sale del fichero.

    Lo que escribe EMMA (nombre, qué ataca, estado, la nota de vuelo, el sitio de cada frase, lo
    no encontrado) sale en el idioma de la petición, con el hermano inglés del fichero
    (`countermeasures_research.en.json`); las frases literales son de la fuente y se quedan en
    su idioma. Se traduce aquí, al servir: `read` está cacheada y valida el castellano.
    """
    raw = i18n.localized(read(), RESEARCH_PATH)
    return {
        "entries": [
            {
                "id": item["id"],
                "name": item["name"],
                "ridge": item["ridge"],
                "ridge_display": Ridge(item["ridge"]).display,
                "targets": item["targets"],
                "status": item["status"],
                "flight_note": item["flight_note"],
                "quotes": [_quote(quote) for quote in item["quotes"]],
                "offered": OFFERED,
            }
            for item in raw["entries"]
        ],
        "note": i18n.loc(NOTE),
        "offered": OFFERED,
        "read_on": raw["read_on"],
        "sources": {
            ref.id: {
                "title": ref.title,
                "source": ref.source,
                "url": ref.url,
                "extent": source["extent"],
                # De `instruments_read`: en inglés cuando su dueño lo registre.
                "extent_text": i18n.loc(EXTENTS[source["extent"]]),
                "what": source["what"],
                # El día de su lectura: el suyo, si se leyó otro día; si no, el del fichero.
                "read_on": source.get("read_on", raw["read_on"]),
            }
            for ref, source in (
                (registry.get(ref_id), source) for ref_id, source in raw["sources"].items()
            )
        },
        "not_found": list(raw["not_found"]),
        "read_not_included": list(raw["read_not_included"]),
    }
