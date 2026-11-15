"""EPM y Biolab, de la instalación a la aplicación: cada eslabón con su frase leída o su hueco.

La base de conocimiento del equipo (§9) pide analizar las dos instalaciones de Columbus como
cadenas «facility → experiment → equipment → parameter → investigator → provider → dataset →
publication → application», y la conversación de ideación lo dejó como tarea: seguir la pista
del laboratorio europeo de fisiología hasta hoy, qué equipo usa, quién investiga y dónde acaban
sus datos. Hasta la decimoquinta ronda esa cadena no existía en EMMA más que como frase. El
peligro de escribirla es el de toda cadena: rellenar el eslabón que falta con lo que «debería»
haber —un fabricante que se recuerda, un conjunto de datos que se supone público, una aplicación
médica que el artículo no declara—. Y la lectura del 2026-10-22 enseñó que faltan varios: ningún
conjunto de datos de los dos experimentos es público, ningún proveedor del equipo del
experimento está escrito en las fuentes leídas, y la lección de Biolab que la base de
conocimiento da por leída (la automatización pensada para ahorrar tiempo de tripulación) no
está en la página de ESA.

Lo leído vive en `data/facilities_read.json` y este cargador es la defensa:

- los nueve eslabones están todos y en el orden de la base de conocimiento: ninguno se omite
  porque no se encontró;
- una frase sin sitio en su fuente, sin ficha del registro, de una ficha que no diga que se leyó
  ese día o de un sitio que no es ESA, NASA o PubMed Central no se sirve;
- un eslabón sin ninguna frase tiene que decir qué falta y dónde se buscó, y lo mismo uno con
  frases y un hueco: lo buscado no se calla ni se rellena;
- una cadena con una fuente que no es solo de personas (las células de rata de TripleLux-A) lleva
  su salvedad de alcance, o no se sirve.

El estado de cada eslabón («leído», «leído, con un hueco», «sin verificar») no se escribe a mano:
sale de si tiene frases y de si tiene hueco. Es un inventario: no entra en el análisis, en el
riesgo ni en ninguna alerta (invariante 5), y no sale a la red; la lectura se hizo una vez, en
Tierra.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.core import i18n
from app.evidence import registry

FACILITIES_PATH = Path(__file__).resolve().parents[1] / "data" / "facilities_read.json"

# La agencia que opera la instalación, el catálogo de NASA o el artículo en PubMed Central. Un
# buscador, una enciclopedia o una nota de prensa no son la fuente.
OFFICIAL_HOSTS = frozenset({"www.esa.int", "www.nasa.gov", "pmc.ncbi.nlm.nih.gov"})

# Los eslabones de la base de conocimiento (§9), en su orden, con el rótulo que se lee.
STEPS: dict[str, str] = {
    "facility": "instalación",
    "experiment": "experimento",
    "equipment": "equipo",
    "parameter": "parámetro",
    "investigator": "investigador",
    "provider": "proveedor",
    "dataset": "conjunto de datos",
    "publication": "publicación",
    "application": "aplicación",
}
# El inglés de cada tabla de rótulos va en una tabla hermana con las mismas claves (y no en el
# registro común de `i18n.en`): «equipo» o «aplicación» pueden querer otro inglés en otro módulo.
STEPS_EN: dict[str, str] = {
    "facility": "facility",
    "experiment": "experiment",
    "equipment": "equipment",
    "parameter": "parameter",
    "investigator": "investigator",
    "provider": "provider",
    "dataset": "dataset",
    "publication": "publication",
    "application": "application",
}

# El estado de un eslabón, según lo que tiene: frases, hueco o las dos cosas.
STATUSES: dict[str, str] = {
    "read": "leído en la fuente",
    "partial": "leído, con un hueco",
    "not_found": "sin verificar: buscado y no encontrado",
}
STATUSES_EN: dict[str, str] = {
    "read": "read in the source",
    "partial": "read, with a gap",
    "not_found": "unverified: searched and not found",
}

FACILITY_FIELDS = frozenset({
    "id", "name", "full_name", "experiment", "kb_role", "scope_caveat", "links",
})
LINK_FIELDS = frozenset({"step", "quotes", "missing"})
QUOTE_FIELDS = frozenset({"quote", "ref", "where"})

NOTE = (
    "Dos instalaciones europeas de la estación, cada una seguida por uno de sus experimentos de la "
    "instalación a la aplicación. Cada eslabón lleva frases de su fuente, en su idioma, con su "
    "ficha; lo que se buscó y no se encontró se dice, con dónde se buscó, y no se rellena. "
    "Inventario: no interviene en el estado de la tripulación ni en ninguna alerta."
)
i18n.en(
    NOTE,
    "Two European facilities of the station, each followed through one of its experiments from "
    "the facility to the application. Each link carries sentences from its source, in its "
    "language, with its reference card; what was searched for and not found is stated, with "
    "where it was searched for, and is not filled in. "
    "Inventory: it plays no part in the crew status or in any alert.",
)


class FacilitiesError(ValueError):
    """Lo leído de las instalaciones no cumple su contrato: no se sirve."""


def _text(item: dict[str, Any], field: str) -> bool:
    value = item.get(field)
    return isinstance(value, str) and bool(value.strip())


def _fields(key: str, item: Any, expected: frozenset[str]) -> None:
    """Ni campos de menos (lo que no hay es null o lista vacía) ni de más (uno mal escrito)."""
    if not isinstance(item, dict):
        raise FacilitiesError(f"{key}: se esperaba un objeto con {sorted(expected)}")
    if missing := sorted(expected - item.keys()):
        raise FacilitiesError(f"{key}: faltan campos {missing}: lo que no hay va como null")
    if extra := sorted(item.keys() - expected):
        raise FacilitiesError(f"{key}: campos desconocidos {extra}")


def _quote(key: str, item: dict[str, Any], read_on: str) -> registry.EvidenceRef:
    """Una frase literal, con su sitio en la fuente y una ficha oficial leída ese día."""
    _fields(key, item, QUOTE_FIELDS)
    for field in sorted(QUOTE_FIELDS):
        if not _text(item, field):
            raise FacilitiesError(f"{key}: falta `{field}`: sin frase, sitio y ficha no es un dato")
    try:
        ref = registry.get(item["ref"])
    except registry.RegistryError as error:  # una ficha que no está en el registro no se cita
        raise FacilitiesError(f"{key}: {error}") from None
    if urlsplit(ref.url or "").hostname not in OFFICIAL_HOSTS:
        raise FacilitiesError(f"{key}: {ref.url!r} no es ESA, NASA ni PubMed Central")
    if read_on not in (ref.notes or ""):
        raise FacilitiesError(
            f"{key}: la ficha {ref.id} no dice que se leyera el {read_on}: sin rastro de la lectura"
        )
    return ref


def _missing(key: str, missing: Any) -> None:
    """Un hueco dice qué falta y dónde se buscó; no basta con «no se encontró»."""
    if not isinstance(missing, dict) or not _text(missing, "what"):
        raise FacilitiesError(f"{key}: un hueco sin decir qué falta")
    searched = missing.get("searched")
    if not isinstance(searched, list) or not searched:
        raise FacilitiesError(f"{key}: un hueco sin decir dónde se buscó")
    if not all(isinstance(line, str) and line.strip() for line in searched):
        raise FacilitiesError(f"{key}: una línea vacía en lo buscado")
    if len(set(searched)) != len(searched):
        raise FacilitiesError(f"{key}: una línea repetida en lo buscado")
    if extra := sorted(missing.keys() - {"what", "searched"}):
        raise FacilitiesError(f"{key}: campos desconocidos en el hueco {extra}")


def _validate_facility(facility: Any, read_on: str) -> None:
    key = str(facility.get("id", "?")) if isinstance(facility, dict) else "?"
    _fields(key, facility, FACILITY_FIELDS)
    for field in ("id", "name", "full_name", "experiment"):
        if not _text(facility, field):
            raise FacilitiesError(f"{key}: falta `{field}`")
    role = facility["kb_role"]
    if not isinstance(role, dict) or not (_text(role, "text") and _text(role, "where")):
        raise FacilitiesError(f"{key}: `kb_role` sin su texto y de dónde sale")
    links = facility["links"]
    steps = (
        [link.get("step") if isinstance(link, dict) else None for link in links]
        if isinstance(links, list) else None
    )
    if steps != list(STEPS):
        raise FacilitiesError(
            f"{key}: los eslabones son los nueve de la base de conocimiento, en su orden; "
            "uno sin fuente se deja vacío y dicho, no se quita"
        )
    populations: set[str] = set()
    for link in links:
        where = f"{key}/{link['step']}"
        _fields(where, link, LINK_FIELDS)
        quotes = link["quotes"]
        if not isinstance(quotes, list):
            raise FacilitiesError(f"{where}: `quotes` es una lista, aunque vacía")
        seen: set[str] = set()
        for index, item in enumerate(quotes):
            ref = _quote(f"{where}/{index}", item, read_on)
            if item["quote"] in seen:
                raise FacilitiesError(f"{where}: frase repetida")
            seen.add(item["quote"])
            if ref.population is not None:
                populations.add(ref.population)
        if link["missing"] is not None:
            _missing(where, link["missing"])
        elif not quotes:
            raise FacilitiesError(
                f"{where}: un eslabón sin frase tiene que decir qué falta y dónde se buscó"
            )
    caveat = facility["scope_caveat"]
    if populations & registry.NON_HUMAN:
        if not (isinstance(caveat, str) and caveat.strip()):
            raise FacilitiesError(
                f"{key}: una fuente que no mide solo personas, y la cadena sin su salvedad"
            )
    elif caveat is not None and not (isinstance(caveat, str) and caveat.strip()):
        raise FacilitiesError(f"{key}: `scope_caveat` vacía: lo que no hay es null")


def validate(raw: dict[str, Any]) -> dict[str, Any]:
    """Rechaza lo que no se pueda sostener con la fuente delante, o un hueco callado."""
    if not _text(raw, "read_on"):
        raise FacilitiesError("falta `read_on`: una lectura sin fecha no se puede contrastar")
    chain = raw.get("chain")
    if not isinstance(chain, dict) or not (_text(chain, "text") and _text(chain, "where")):
        raise FacilitiesError("`chain` sin su texto y de dónde sale")
    facilities = raw.get("facilities")
    if not isinstance(facilities, list) or not facilities:
        raise FacilitiesError("ninguna instalación")
    ids: set[str] = set()
    for facility in facilities:
        _validate_facility(facility, raw["read_on"])
        if facility["id"] in ids:
            raise FacilitiesError(f"{facility['id']}: instalación repetida")
        ids.add(facility["id"])
    not_found = raw.get("not_found")
    if not isinstance(not_found, list) or not all(
        isinstance(line, str) and line.strip() for line in not_found
    ):
        raise FacilitiesError("`not_found` es una lista de líneas, sin líneas vacías")
    if len(set(not_found)) != len(not_found):
        raise FacilitiesError("una línea repetida en `not_found`")
    return raw


@cache
def read() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(FACILITIES_PATH.read_text(encoding="utf-8"))
    return validate(raw)


def cited_refs() -> frozenset[str]:
    """Las fichas del registro que sostienen alguna frase de alguna cadena."""
    return frozenset(
        item["ref"]
        for facility in read()["facilities"]
        for link in facility["links"]
        for item in link["quotes"]
    )


def status(link: dict[str, Any]) -> str:
    """El estado de un eslabón, de lo que tiene: nunca escrito a mano."""
    if not link["quotes"]:
        return "not_found"
    return "partial" if link["missing"] is not None else "read"


def _loc(text: str | None) -> str | None:
    """Un rótulo de la ficha del registro, en el idioma de la petición si el registro lo tiene."""
    return i18n.loc(text) if text is not None else None


def _cited(item: dict[str, Any], resolved: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ref = registry.get(item["ref"])
    if ref.id not in resolved:  # una ficha resuelta una vez por respuesta, no una por frase
        resolved[ref.id] = ref.to_dict()
    card = resolved[ref.id]
    return {
        "quote": item["quote"],
        "where": item["where"],
        "ref": ref.id,
        "source": ref.source,
        "url": ref.url,
        "organization": ref.organization,
        "date": ref.date,
        "population": ref.population,
        "population_display": _loc(card["population_display"]),
        "evidence_type": ref.evidence_type,
        "evidence_type_display": _loc(card["evidence_type_display"]),
        "unverified_display": [i18n.loc(text) for text in card["unverified_display"]],
    }


def _link(link: dict[str, Any], resolved: dict[str, dict[str, Any]]) -> dict[str, Any]:
    state = status(link)
    missing = link["missing"]
    return {
        "step": link["step"],
        "label": i18n.tr(STEPS[link["step"]], STEPS_EN[link["step"]]),
        "status": state,
        "status_text": i18n.tr(STATUSES[state], STATUSES_EN[state]),
        "quotes": [_cited(item, resolved) for item in link["quotes"]],
        "missing": (
            None if missing is None
            else {"what": missing["what"], "searched": list(missing["searched"])}
        ),
    }


def payload() -> dict[str, Any]:
    """Las cadenas como se sirven: cada frase resuelta en su ficha y cada eslabón con su estado."""
    # Una copia en el idioma de la petición, después de validar: la caché guarda el castellano.
    raw = i18n.localized(read(), FACILITIES_PATH)
    resolved: dict[str, dict[str, Any]] = {}
    facilities = []
    for facility in raw["facilities"]:
        links = [_link(link, resolved) for link in facility["links"]]
        facilities.append({
            "id": facility["id"],
            "name": facility["name"],
            "full_name": facility["full_name"],
            "experiment": facility["experiment"],
            # Copias: lo que se sirve no comparte diccionarios con lo cargado en caché.
            "kb_role": dict(facility["kb_role"]),
            "scope_caveat": facility["scope_caveat"],
            "links": links,
            # Los rótulos de los eslabones sin ninguna frase: lo que esta cadena no sabe.
            "unsourced": [link["label"] for link in links if link["status"] == "not_found"],
        })
    return {
        "note": i18n.loc(NOTE),
        "read_on": raw["read_on"],
        "chain": dict(raw["chain"]),
        "facilities": facilities,
        "not_found": list(raw["not_found"]),
    }
