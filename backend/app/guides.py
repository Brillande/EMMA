"""Guías de medida paso a paso y glosario para la tripulación.

Por qué existe: el enunciado del reto pide no dar por hecho que la tripulación sabe evaluar su
salud («Do not assume that astronauts know everything about how to assess their health. Your tool
could provide simple instructions and explanations covering measurements, health indicators, and
risks»), y EMMA explicaba cada alerta, cada protocolo ecográfico y cada contramedida, pero no cómo
tomarse la tensión o la temperatura ni qué quiere decir «línea base» o «tiempo de luz»
(`compliance/challenge-coverage.md`). Un tripulante con el retardo de Marte no puede preguntar a
Tierra cómo se coloca un manguito.

Dos ficheros de datos, con su cargador aquí:

  * `data/measurement_guides.json` — una guía por medida. Cada paso lo redacta EMMA en español y
    lo sostiene al menos una frase leída en su fuente: o la frase misma con su ficha del registro
    (`evidence/registry.py`), su sitio y su día, o el identificador de una frase ya leída en
    `data/instruments_read.json` (la PVT), que no se copia dos veces. **Un paso sin fuente no se
    escribe**: lo que se buscó y no se encontró va en `not_found`. Son instrucciones de cómo se
    mide, no de qué hacer con el resultado: ningún paso lleva un rango ni una conducta ante una
    cifra (invariante 7), y todo texto pasa el filtro de lenguaje (`text_guard.check`).
  * `data/glossary.json` — los términos de la interfaz. Cada definición dice su origen: de EMMA,
    con el fichero del repositorio que la sostiene, o de una fuente leída, con su frase. Es el
    mismo rótulo por origen que llevan los nombres de los indicadores (`ingest/names_es.py`).

Lo que no se repite: los protocolos ecográficos siguen en `imaging/protocols.py` (la guía los
enlaza en `elsewhere`), el equipo y el modo de cada medida en el coste de medir
(`ingest/cost.py`), que la guía adjunta por indicador, y el nombre en español de cada indicador en
`ingest/names_es.py`.

La carga es estricta y se hace al arrancar (`app/main.py`): un fichero roto no deja arrancar, y
dice cuál y por qué. Nada de esto entra en el análisis ni en `rules_version`: no decide nada.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from functools import cache
from pathlib import Path
from typing import Any

from app import text_guard
from app.core import i18n
from app.evidence import instruments_read, registry
from app.ingest import cost
from app.ingest.codes import CATALOG
from app.ingest.names_es import name_es

_DATA = Path(__file__).resolve().parent / "data"
GUIDES_PATH = _DATA / "measurement_guides.json"
GLOSSARY_PATH = _DATA / "glossary.json"

# Rótulo del origen de cada definición del glosario: la interfaz lo enseña tal cual.
ORIGIN_DISPLAY = {
    "emma": "definición de EMMA",
    "source": "definición tomada de la fuente",
}
# Lo que dice la guía de sí misma, para que no se lea como consejo clínico.
GUIDES_SCOPE = (
    "Cómo se toma cada medida, paso a paso. Cada paso lleva la frase de la fuente que lo "
    "sostiene, y lo que no se encontró se dice. Estas guías no dicen qué hacer con el resultado: "
    "eso lo explica cada alerta, y lo decide la tripulación con el equipo médico."
)
GLOSSARY_SCOPE = (
    "Los términos que usa la consola, con el origen de cada definición: de EMMA, con el fichero "
    "que la sostiene, o de una fuente leída, con su frase."
)
# El inglés de lo que este módulo dice (`core/i18n.py`). El de los pasos, los títulos, los
# términos y las definiciones va en los hermanos `measurement_guides.en.json` y
# `glossary.en.json`, que se aplican al servir; las frases literales de las fuentes no se traducen.
i18n.en_many({
    ORIGIN_DISPLAY["emma"]: "EMMA's definition",
    ORIGIN_DISPLAY["source"]: "definition taken from the source",
    GUIDES_SCOPE: (
        "How each measurement is taken, step by step. Each step carries the sentence from the "
        "source that supports it, and what was not found is stated. These guides do not say "
        "what to do with the result: each alert explains that, and the crew decides it with "
        "the medical team."
    ),
    GLOSSARY_SCOPE: (
        "The terms the console uses, with the origin of each definition: EMMA's, with the file "
        "that supports it, or from a source that was read, with its sentence."
    ),
})

_ID = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_ISO_DAY = re.compile(r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")
_READING_KEYS = frozenset({"ref", "quote", "where", "read_on"})
_STATEMENT_KEYS = frozenset({"statement"})
_GUIDE_KEYS = frozenset({"id", "title", "indicators", "steps", "in_flight", "not_found"})
_STEP_KEYS = frozenset({"text", "basis"})
_ELSEWHERE_KEYS = frozenset({"id", "text", "route", "module"})
_TERM_KEYS = frozenset({"id", "term", "definition", "origin", "document", "basis"})


class GuideError(ValueError):
    """Una guía o un término no cumple su contrato: no se carga."""


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _guarded(text: str, where: str, fail: Callable[[str], GuideError]) -> None:
    """Un texto para la tripulación que el filtro de lenguaje bloquea no se carga."""
    if found := text_guard.check(text):
        matches = sorted({finding.match for finding in found})
        raise fail(f"{where}: el filtro de lenguaje lo bloquea ({matches})")


def _check_basis(items: Any, *, statements: bool, fail: Callable[[str], GuideError]) -> None:
    """Las frases que sostienen un paso o una definición: al menos una, y cada una con su ficha."""
    if not isinstance(items, list) or not items:
        raise fail("sin `basis`: lo que no tiene frase leída no se escribe")
    known = {item["id"] for item in instruments_read.read()["statements"]} if statements else set()
    for item in items:
        if not isinstance(item, dict):
            raise fail("`basis`: cada frase es un objeto")
        if item.keys() == _STATEMENT_KEYS and statements:
            if item["statement"] not in known:
                raise fail(f"`basis`: {item['statement']!r} no es una frase de lo leído")
            continue
        if item.keys() != _READING_KEYS:
            raise fail(f"`basis`: una frase leída lleva exactamente {sorted(_READING_KEYS)}")
        for name in ("ref", "quote", "where"):
            if not _text(item[name]):
                raise fail(f"`basis` con `{name}` vacío: lo leído se copia o no se escribe")
        # El sitio lo escribe EMMA en español y se enseña: pasa el filtro como un paso.
        _guarded(item["where"], "`basis` (`where`)", fail)
        if not isinstance(item["read_on"], str) or not _ISO_DAY.fullmatch(item["read_on"]):
            raise fail("`basis`: `read_on` es el día de lectura, AAAA-MM-DD")
        try:
            registry.get(item["ref"])
        except registry.RegistryError as error:
            raise fail(str(error)) from None


def _check_step(step: Any, where: str, fail: Callable[[str], GuideError]) -> None:
    if not isinstance(step, dict) or step.keys() != _STEP_KEYS:
        raise fail(f"{where}: un paso es {{text, basis}}, sin más campos")
    if not _text(step["text"]):
        raise fail(f"{where}: paso sin texto")
    _guarded(step["text"], where, fail)
    _check_basis(step["basis"], statements=True, fail=fail)


def validate_guides(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Rechaza lo mal formado: el fichero entero o nada."""
    seen: set[str] = set()
    guides = raw.get("guides")
    if not isinstance(guides, list) or not guides:
        raise GuideError("`guides` es una lista con al menos una guía")
    for guide in guides:
        ident = str(guide.get("id", "?")) if isinstance(guide, dict) else "?"

        def fail(reason: str, ident: str = ident) -> GuideError:
            return GuideError(f"guía {ident}: {reason}")

        if not isinstance(guide, dict) or guide.keys() != _GUIDE_KEYS:
            raise fail(f"una guía lleva exactamente {sorted(_GUIDE_KEYS)}")
        if not _ID.fullmatch(ident) or ident in seen:
            raise fail("identificador no válido o repetido")
        seen.add(ident)
        if not _text(guide["title"]):
            raise fail("sin título")
        _guarded(guide["title"], "título", fail)
        indicators = guide["indicators"]
        if not isinstance(indicators, list) or not indicators:
            raise fail("`indicators`: al menos un indicador del catálogo")
        if unknown := sorted(set(indicators) - CATALOG.keys()):
            raise fail(f"indicadores que no están en el catálogo: {unknown}")
        for kind in ("steps", "in_flight"):
            if not isinstance(guide[kind], list):
                raise fail(f"`{kind}` es una lista")
            for index, step in enumerate(guide[kind], start=1):
                _check_step(step, f"`{kind}` {index}", fail)
        if not guide["steps"] and not guide["in_flight"]:
            raise fail("sin pasos ni nada leído de vuelo: una guía vacía no se sirve")
        not_found = guide["not_found"]
        if not isinstance(not_found, list) or not all(_text(item) for item in not_found):
            raise fail("`not_found` es una lista de frases")
        for item in not_found:
            _guarded(item, "`not_found`", fail)
        # Sin pasos, lo que falta tiene que decirse: una guía solo de vuelo no finge estar entera.
        if not guide["steps"] and not not_found:
            raise fail("sin pasos y sin decir qué se buscó y no se encontró")
    elsewhere = raw.get("elsewhere", [])
    if not isinstance(elsewhere, list):
        raise GuideError("`elsewhere` es una lista")
    elsewhere_ids: set[str] = set()
    for item in elsewhere:
        if not isinstance(item, dict) or item.keys() != _ELSEWHERE_KEYS:
            raise GuideError(f"`elsewhere`: cada entrada lleva {sorted(_ELSEWHERE_KEYS)}")
        if not all(_text(item[name]) for name in _ELSEWHERE_KEYS):
            raise GuideError("`elsewhere`: campo vacío")
        if not _ID.fullmatch(item["id"]) or item["id"] in elsewhere_ids:
            raise GuideError(f"`elsewhere`: identificador {item['id']!r} no válido o repetido")
        elsewhere_ids.add(item["id"])
        if not item["route"].startswith("/api/"):
            raise GuideError("`elsewhere`: `route` es una ruta de la API")
        _guarded(item["text"], f"`elsewhere` {item['id']}", GuideError)
    return dict(raw)


def validate_glossary(raw: Mapping[str, Any]) -> dict[str, Any]:
    terms = raw.get("terms")
    if not isinstance(terms, list) or not terms:
        raise GuideError("`terms` es una lista con al menos un término")
    seen: set[str] = set()
    for term in terms:
        ident = str(term.get("id", "?")) if isinstance(term, dict) else "?"

        def fail(reason: str, ident: str = ident) -> GuideError:
            return GuideError(f"término {ident}: {reason}")

        if not isinstance(term, dict) or not term.keys() <= _TERM_KEYS:
            raise fail(f"campos fuera de {sorted(_TERM_KEYS)}")
        if not _ID.fullmatch(ident) or ident in seen:
            raise fail("identificador no válido o repetido")
        seen.add(ident)
        for name in ("term", "definition"):
            if not _text(term.get(name)):
                raise fail(f"sin `{name}`")
            _guarded(term[name], f"`{name}`", fail)
        origin = term.get("origin")
        if origin not in ORIGIN_DISPLAY:
            raise fail(f"`origin` es uno de {sorted(ORIGIN_DISPLAY)}")
        if origin == "emma":
            document = term.get("document")
            if (
                not isinstance(document, str) or not document.strip()
                or Path(document).is_absolute() or ".." in Path(document).parts
            ):
                raise fail("una definición de EMMA nombra su documento, con ruta del repositorio")
            if "basis" in term:
                _check_basis(term["basis"], statements=False, fail=fail)
        else:
            if "document" in term:
                raise fail("una definición de la fuente no nombra documento de EMMA")
            _check_basis(term.get("basis"), statements=False, fail=fail)
    return dict(raw)


@cache
def guides() -> dict[str, Any]:
    return validate_guides(json.loads(GUIDES_PATH.read_text(encoding="utf-8")))


@cache
def glossary() -> dict[str, Any]:
    return validate_glossary(json.loads(GLOSSARY_PATH.read_text(encoding="utf-8")))


def _resolved_basis(item: Mapping[str, Any]) -> dict[str, Any]:
    """Una frase con su ficha resuelta del registro, en la misma forma venga de donde venga."""
    if "statement" in item:
        read = instruments_read.statement(item["statement"])
        # El sitio de una frase de lo leído de la PVT lo escribe su fichero: su inglés es el de
        # su hermano, si lo tiene (la frase literal no está en él y no cambia).
        reading = i18n.localized(
            {key: read[key] for key in ("quote", "where", "read_on")}, instruments_read.READ_PATH
        )
        ref_id = read["ref"]
    else:
        reading = {key: item[key] for key in ("quote", "where", "read_on")}
        ref_id = item["ref"]
    return {**reading, "citation": registry.cite(ref_id).to_dict()}


def _step(step: Mapping[str, Any]) -> dict[str, Any]:
    return {"text": step["text"], "basis": [_resolved_basis(item) for item in step["basis"]]}


def _indicator(key: str) -> dict[str, Any]:
    """El indicador con su nombre en español y lo que cuesta medirlo, si el coste lo dice."""
    measured = cost.cost(key)
    return {
        "key": key,
        "display_es": name_es(key),
        "equipment": measured["equipment"] if measured else None,
        "mode_display": measured["mode_display"] if measured else None,
    }


def guides_payload() -> dict[str, Any]:
    # Lo validado y cacheado se queda en castellano; el inglés se pone aquí, al servir.
    raw = i18n.localized(guides(), GUIDES_PATH)
    return {
        "scope": i18n.loc(GUIDES_SCOPE),
        "guides": [
            {
                "id": guide["id"],
                "title": guide["title"],
                "indicators": [_indicator(key) for key in guide["indicators"]],
                "steps": [_step(step) for step in guide["steps"]],
                "in_flight": [_step(step) for step in guide["in_flight"]],
                "not_found": list(guide["not_found"]),
            }
            for guide in raw["guides"]
        ],
        "elsewhere": [dict(item) for item in raw.get("elsewhere", [])],
    }


def glossary_payload() -> dict[str, Any]:
    terms = []
    for term in i18n.localized(glossary(), GLOSSARY_PATH)["terms"]:
        terms.append({
            "id": term["id"],
            "term": term["term"],
            "definition": term["definition"],
            "origin": term["origin"],
            "origin_display": i18n.loc(ORIGIN_DISPLAY[term["origin"]]),
            "document": term.get("document"),
            "basis": [_resolved_basis(item) for item in term.get("basis", [])],
        })
    return {"scope": i18n.loc(GLOSSARY_SCOPE), "terms": terms}


def guides_cited_refs() -> set[str]:
    """Las fichas del registro que citan las guías (para la prueba de huérfanas). Las de la PVT
    las cita `data/instruments_read.json`, de donde salen sus frases."""
    cited: set[str] = set()
    for guide in guides()["guides"]:
        for step in (*guide["steps"], *guide["in_flight"]):
            cited.update(item["ref"] for item in step["basis"] if "ref" in item)
    return cited


def glossary_cited_refs() -> set[str]:
    """Las fichas del registro que cita el glosario."""
    return {item["ref"] for term in glossary()["terms"] for item in term.get("basis", [])}


def displayed_texts() -> list[str]:
    """Todo el texto en español que la consola enseña de las guías y del glosario."""
    texts = [GUIDES_SCOPE, GLOSSARY_SCOPE]
    for guide in guides()["guides"]:
        texts.append(guide["title"])
        texts.extend(step["text"] for step in (*guide["steps"], *guide["in_flight"]))
        texts.extend(guide["not_found"])
        texts.extend(
            item["where"] for step in (*guide["steps"], *guide["in_flight"])
            for item in step["basis"] if "where" in item
        )
    texts.extend(item["text"] for item in guides().get("elsewhere", []))
    for term in glossary()["terms"]:
        texts.extend((term["term"], term["definition"]))
        texts.extend(item["where"] for item in term.get("basis", []))
    texts.extend(ORIGIN_DISPLAY.values())
    return texts
