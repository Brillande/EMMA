"""Bancos de prueba y las dos validaciones: qué reproduce cada análogo y qué tiene EMMA de cada una.

La base de conocimiento del equipo (§3) ordena la evidencia en una escalera —análogos en Tierra,
ISS, Luna, Marte— y su §3.1 lo convierte en regla: «cada dato debe conservar el contexto
experimental y las variables manipuladas o ausentes». La conversación de ideación lo resume en una
línea, «Scientific validation ≠ Operational validation», y `docs/contexto/bancos-de-prueba.md`
hizo el mapa. Pero el mapa vivía en un documento: ninguna pantalla decía qué banco corresponde a
qué `evidence_context` de las observaciones, ni que EMMA tiene parte de la primera validación y
**ninguna** de la segunda. Un proyecto que no dice qué le falta acaba sugiriendo que lo tiene
(invariante 6).

Lo que carga este módulo (`data/testbeds.json`) son frases literales de cada página, cada banco
con el día en que se leyó y cada frase citada por su ficha del registro; lo que una página no dice
y EMMA deduce va aparte, marcado como deducción y con su motivo. La conversación de ideación pedía
además columnas de participantes, datos disponibles y proveedores, y hasta la decimoquinta ronda
quedaban vacías sin que el mapa lo dijera: ahora cada banco las lleva, con la frase de la fuente
donde la da y, donde no, `not_found` con dónde se buscó. Una columna sin frase ni búsqueda no se
sirve, y una con las dos tampoco (o se leyó o se buscó y no estaba).

La decimonovena ronda (U4) releyó banco a banco las páginas de NASA y las que NASA enlaza como la
del operador o la del banco (la ficha de misión de :envihab, la página «Antarctic Stations» del
enlace «NSF», la cartera de patentes para ARGOS) y añadió las columnas «Parámetros medidos»,
«Equipos», «Investigadores» y «Experimentos» con la misma regla; «Limitaciones» ya era
`leaves_out`, y «Aplicación ISS / Luna / Marte» y «Oportunidad» son juicio de EMMA (`emma_use`, la
escalera), no frases de una página. Entró el centro de protones de Loma Linda como banco, por la
página del Space Radiation Element que lo nombra; la colección de biospecímenes alrededor del NSRL
y los modelos de riesgo de JSC entran como filas del NSRL (columnas de datos y experimentos), que
es lo que dicen sus páginas: muestras de animales irradiados allí y modelos que esas muestras
alimentan, no otro banco.

La misma conversación pedía dos columnas más que la decimosexta ronda añade: «Duración», que es
otra columna como las de arriba, y «Riesgo RIDGE», que no lo es. Ninguna página dice «este banco
deja fuera la distancia»: casi toda la matriz banco × peligro es deducción de EMMA, y se sirve
como tal, celda a celda y con su motivo, igual que lo que un banco deja fuera. Solo donde una
página de NASA del banco nombra el peligro que estudia (el campo «Hazards» de su ficha de misión,
o la página de estudios de NEEMO) la celda lleva esa frase. El
vocabulario de los cinco peligros es el de `ingest.codes.Ridge`, el mismo de las contramedidas y
los riesgos: aquí no se escribe otro.

La defensa está en `validate`: rechaza una frase sin ficha, sin día de lectura o fuera de un sitio
oficial, un banco sin lo que deja fuera, un entorno que no sea del enumerado de
las observaciones (o un hueco sin decir por qué ninguno lo cubre: el enumerado no se amplía aquí),
una validación de EMMA cuya ficha diga otro entorno, una validación operacional que no salga de un
banco operacional, una cifra copiada de `compliance/external-validation.md` (allí se mide; aquí se
remite) y un texto sobre EMMA que reclame más de lo que tiene. El «ninguna» de la validación
operacional no se escribe a mano: sale de que la lista está vacía. De la matriz RIDGE rechaza un
banco al que le falte o le sobre un peligro, una celda sin estado conocido, una deducción sin
motivo, una frase de fuente que diga que un banco deja fuera un peligro (la ficha nombra lo que
estudia, no lo que le falta), un banco que no deje fuera ningún peligro (la base de conocimiento,
§3: «no existe banco de prueba completo»; la conversación: «cada entorno elimina variables que otro
sí contiene») y una celda que contradiga el entorno de evidencia del banco
(un análogo de aislamiento que dejara fuera el aislamiento).

Es un inventario: no entra en el análisis, en el riesgo ni en ninguna alerta (invariante 5), y no
sale a la red.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.core import i18n
from app.evidence import registry
from app.ingest.codes import Ridge
from app.ingest.fhir import EvidenceContext

TESTBEDS_PATH = Path(__file__).resolve().parents[1] / "data" / "testbeds.json"

# Solo la página del propio organismo: NASA (nasa.gov, su servidor de informes técnicos NTRS y su
# cartera de patentes, que es donde el catálogo de análogos manda para ARGOS) o el laboratorio que
# aloja el banco. La página de un operador que NASA nombra pero no es NASA (protons.com, de Loma
# Linda) no entra: se dice en `not_found`.
OFFICIAL_HOSTS = frozenset({"www.nasa.gov", "ntrs.nasa.gov", "technology.nasa.gov", "www.bnl.gov"})

# Las dos validaciones de la base de conocimiento (§3), con el rótulo que se lee.
VALIDATIONS = {
    "scientific": "científica",
    "operational": "operacional",
}
# El inglés de cada tabla de rótulos va en una tabla hermana con las mismas claves (y no en el
# registro común de `i18n.en`): son palabras sueltas —«Equipos», «en parte»— que en otro módulo
# pueden querer otro inglés. Lo que se sirve lo elige `_label`.
VALIDATIONS_EN = {
    "scientific": "scientific",
    "operational": "operational",
}

# Cómo se sabe lo que un banco deja fuera: lo dice la fuente, o lo deduce EMMA y explica por qué.
LEAVES_OUT_BASIS = {
    "source": "lo dice la fuente",
    "deduced": "lo deduce EMMA; la fuente no lo enumera",
}
LEAVES_OUT_BASIS_EN = {
    "source": "stated by the source",
    "deduced": "deduced by EMMA; the source does not list it",
}

# Lo que EMMA tiene de cada validación, según la lista: vacía es «ninguna».
EMMA_NONE = "ninguna"
EMMA_PART = "en parte"
EMMA_STATUS_EN = {EMMA_NONE: "none", EMMA_PART: "partly"}

# Lo que un texto sobre EMMA no puede decir de sí mismo (invariante 6). Por palabra entera:
# «validación» nombra la cosa y no reclama nada; «valida» o «validado», sí. No se aplica a
# `does_not_show`, que es justo la negación («No valida fisiología espacial»).
CLAIM = re.compile(
    r"\b(certific\w*|validad[oa]s?|valida|validan|validó|conforme|cumple|aprobad[oa]s?"
    r"|verificad[oa]s?)\b",
    re.IGNORECASE,
)
# Una cifra de la validación externa copiada aquí: un porcentaje, «n de m», «n/m» o un decimal.
# Las cifras viven en `compliance/external-validation.md` y en las pruebas `-m external`, que son
# la fuente de verdad; copiadas aquí envejecen sin que nada lo diga.
COPIED_FIGURE = re.compile(r"%|\b\d+\s+de\s+\d+\b|\b\d+\s*/\s*\d+\b|\b\d+[.,]\d+\b")
# Lo que un banco sin entorno tiene que decir: que ningún valor del enumerado lo cubre.
NO_CONTEXT_REASON = "ningún valor del enumerado"
# Las columnas que pedía la conversación de ideación para cada banco, con el rótulo que se lee.
# Proveedor es «fabricante/integrador cuando sea identificable»; quien aloja u opera el banco va
# en la misma columna porque las páginas no separan lo uno de lo otro. Las cuatro últimas entran
# en la decimonovena ronda (U4) con la misma regla: frase de la página o dónde se buscó. De las
# que pedía la conversación no se añaden como columnas «Limitaciones» (es `leaves_out`, con su
# base), ni «Aplicación ISS / Luna / Marte» ni «Oportunidad», que no las da ninguna página: son
# juicio de EMMA y viven en `emma_use` y en la escalera (`ladder`), marcados como tales.
COLUMNS = {
    "duration": "Duración",
    "participants": "Participantes",
    "data": "Datos disponibles",
    "providers": "Proveedores u operador",
    "parameters": "Parámetros medidos",
    "equipment": "Equipos",
    "investigators": "Investigadores",
    "experiments": "Experimentos",
}
COLUMNS_EN = {
    "duration": "Duration",
    "participants": "Participants",
    "data": "Available data",
    "providers": "Providers or operator",
    "parameters": "Measured parameters",
    "equipment": "Equipment",
    "investigators": "Investigators",
    "experiments": "Experiments",
}
# Los campos de cada pieza: el que no se sabe va como null, no se omite (y `payload` los lee).
BANK_FIELDS = frozenset({
    "id", "name", "full_name", "where", "read_on", "rung", "validation", "evidence_context",
    "context_basis", "reproduces", "leaves_out", *COLUMNS, "ridge", "variables_kb", "emma_use",
})
COLUMN_FIELDS = frozenset({"read_on", "quotes", "not_found"})
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
EMMA_FIELDS = frozenset({"id", "ref", "context", "bank", "what", "does_not_show", "figures_in"})
FIGURES_HOME = "compliance/external-validation.md"

# La matriz banco × peligro RIDGE. Cuatro estados y no dos: «en parte» es lo más frecuente (un
# reposo en cama induce efectos de la ingravidez sin ser microgravedad) y «no se sabe» es lo que
# queda cuando ninguna página lo dice y EMMA no tiene de dónde deducirlo; ponerlo en «deja fuera»
# sería inventar.
RIDGE_STATUS = {
    "reproduces": "lo reproduce",
    "partial": "en parte",
    "leaves_out": "lo deja fuera",
    "unknown": "no se sabe",
}
RIDGE_STATUS_EN = {
    "reproduces": "reproduces it",
    "partial": "partly",
    "leaves_out": "leaves it out",
    "unknown": "not known",
}
# Lo que una ficha de NASA dice del peligro que un banco estudia: lo reproduce, entero o en parte.
SOURCE_STATUSES = frozenset({"reproduces", "partial"})
RIDGE_BASIS = {
    "source": "lo nombra una página del banco",
    "deduced": "lo deduce EMMA",
}
RIDGE_BASIS_EN = {
    "source": "named by a page of the testbed",
    "deduced": "deduced by EMMA",
}
RIDGE_FIELDS = frozenset({"read_on", "cells"})
RIDGE_CELL_FIELDS = frozenset({"hazard", "status", "basis", "why", "quote", "ref", "where"})
# El peligro que un dato con ese entorno de evidencia lleva dentro: un análogo de aislamiento que
# dejara fuera el aislamiento, o una ISS sin microgravedad, se contradirían con su propio entorno.
# Las claves son del enumerado, no cadenas sueltas: un valor renombrado en `ingest/fhir.py` hace
# fallar la importación en vez de apagar la comprobación en silencio.
CONTEXT_HAZARD: dict[str, Ridge] = {
    EvidenceContext.ANALOG_ISOLATION: Ridge.ISOLATION,
    EvidenceContext.ANALOG_BEDREST: Ridge.GRAVITY,
    EvidenceContext.ISS: Ridge.GRAVITY,
    EvidenceContext.SPACEFLIGHT: Ridge.GRAVITY,
}
# Lo que ese peligro tiene que ser en la fila del banco: reproducido, entero o en parte. Es otra
# regla que la de las fichas (`SOURCE_STATUSES`), aunque hoy coincidan; cambian por separado.
CONTEXT_STATUSES = frozenset({"reproduces", "partial"})
RIDGE_NOTE = (
    "Qué peligro RIDGE reproduce cada banco. Es una deducción de EMMA, celda a celda y con su "
    "motivo: las páginas de los bancos no lo enumeran. Solo donde una página de NASA del banco "
    "nombra el peligro que estudia va su frase. Todos dejan fuera al menos uno."
)
i18n.en(
    RIDGE_NOTE,
    "Which RIDGE hazard each testbed reproduces. It is a deduction by EMMA, cell by cell and "
    "with its reason: the pages of the testbeds do not list it. Only where a NASA page of the "
    "testbed names the hazard it studies does its sentence appear. All of them leave out at "
    "least one.",
)

_CONTEXTS = frozenset(str(item) for item in EvidenceContext)

NOTE = (
    "Ningún banco de prueba reproduce una misión a Marte entera: cada uno aísla unas condiciones "
    "y deja fuera otras, y por eso cada dato lleva el entorno en que se obtuvo. Las frases son de "
    "la página de cada banco, en su idioma; lo que EMMA deduce va marcado como deducción, también "
    "la matriz de peligros RIDGE, y donde ninguna página leída da la duración, los participantes, "
    "los datos, los proveedores, los parámetros, los equipos, los investigadores o los "
    "experimentos se dice dónde se buscó. "
    "Inventario: no interviene en el estado de la tripulación ni en ninguna alerta."
)
i18n.en(
    NOTE,
    "No testbed reproduces a whole mission to Mars: each one isolates some conditions and "
    "leaves out others, and that is why each piece of data carries the environment in which it "
    "was obtained. The sentences are from the page of each testbed, in its language; what EMMA "
    "deduces is marked as a deduction, including the RIDGE hazard matrix, and where no page "
    "that was read gives the duration, the participants, the data, the providers, the "
    "parameters, the equipment, the investigators or the experiments, it says where it was "
    "searched for. "
    "Inventory: it plays no part in the crew status or in any alert.",
)


class AnalogMapError(ValueError):
    """El mapa de bancos no cumple su contrato: no se sirve."""


def _label(table: dict[str, str], english: dict[str, str], key: str) -> str:
    """El rótulo de una tabla en el idioma de la petición; la clave no se traduce nunca."""
    return i18n.tr(table[key], english[key])


def _text(item: dict[str, Any], field: str) -> bool:
    value = item.get(field)
    return isinstance(value, str) and bool(value.strip())


def _claims(text: str) -> list[str]:
    return [found.group(0) for found in CLAIM.finditer(text)]


def _fields(key: str, item: dict[str, Any], expected: frozenset[str]) -> None:
    """Ni campos de menos (lo que no se sabe es null) ni de más (uno mal escrito no se sirve)."""
    if missing := sorted(expected - item.keys()):
        raise AnalogMapError(f"{key}: faltan campos {missing}: lo que no se sabe va como null")
    if extra := sorted(item.keys() - expected):
        raise AnalogMapError(f"{key}: campos desconocidos {extra}")


def _read_on(key: str, item: dict[str, Any]) -> None:
    """El día de la lectura, en ISO: sin él, la frase no se puede contrastar con la página."""
    value = item.get("read_on")
    if not isinstance(value, str) or not ISO_DATE.fullmatch(value):
        raise AnalogMapError(f"{key}: falta `read_on`: una lectura sin fecha no se contrasta")


def _validate_column(key: str, column: Any) -> None:
    """Una columna: o la frase de la fuente, o dónde se buscó y no estaba; ni las dos ni nada."""
    if not isinstance(column, dict):
        raise AnalogMapError(f"{key}: una columna es un objeto, aunque no se encontrara nada")
    _fields(key, column, COLUMN_FIELDS)
    _read_on(key, column)
    quotes = column["quotes"]
    if not isinstance(quotes, list):
        raise AnalogMapError(f"{key}: `quotes` es la lista de frases, aunque vacía")
    for index, item in enumerate(quotes):
        _quoted(f"{key}/{index}", item)
    found = column["not_found"]
    if quotes and found is not None:
        raise AnalogMapError(f"{key}: con frase y con `not_found`: o se leyó o no estaba")
    if not quotes and not _text(column, "not_found"):
        raise AnalogMapError(
            f"{key}: sin frase y sin `not_found`: una columna vacía dice dónde se buscó"
        )
    if found is not None and (claimed := _claims(found)):
        raise AnalogMapError(f"{key}: `not_found` reclama de más sobre EMMA ({claimed})")


def _quoted(key: str, item: dict[str, Any]) -> None:
    """Una frase de fuente: literal, con su sitio en la página y una ficha oficial del registro."""
    for field in ("quote", "ref", "where"):
        if not _text(item, field):
            raise AnalogMapError(f"{key}: falta `{field}`: sin frase, sitio y ficha no es un dato")
    url = registry.get(item["ref"]).url  # una ficha que no está en el registro falla aquí
    if urlsplit(url or "").hostname not in OFFICIAL_HOSTS:
        raise AnalogMapError(f"{key}: {url!r} no es la página oficial del banco")


def _validate_ridge(key: str, ridge: Any, context: str | None) -> None:
    """La fila del banco en la matriz RIDGE: los cinco peligros, cada uno con estado y base."""
    if not isinstance(ridge, dict):
        raise AnalogMapError(f"{key}: la matriz RIDGE es un objeto, con su fecha y sus celdas")
    _fields(key, ridge, RIDGE_FIELDS)
    _read_on(key, ridge)
    cells = ridge["cells"]
    if not isinstance(cells, list) or not all(isinstance(cell, dict) for cell in cells):
        raise AnalogMapError(f"{key}: `cells` es la lista de los cinco peligros")
    hazards = [cell.get("hazard") for cell in cells]
    if hazards != [str(hazard) for hazard in Ridge]:
        raise AnalogMapError(
            f"{key}: los peligros {hazards} no son los cinco de RIDGE, una vez y en su orden"
        )
    for cell in cells:
        where = f"{key}/{cell['hazard']}"
        if extra := sorted(cell.keys() - RIDGE_CELL_FIELDS):
            raise AnalogMapError(f"{where}: campos desconocidos {extra}")
        status = cell.get("status")
        if not isinstance(status, str) or status not in RIDGE_STATUS:
            raise AnalogMapError(f"{where}: estado {status!r} que la matriz no tiene")
        kind = cell.get("basis")
        if kind == "source":
            _quoted(where, cell)
            if status not in SOURCE_STATUSES:
                raise AnalogMapError(
                    f"{where}: una ficha nombra el peligro que el banco estudia, "
                    "no el que deja fuera"
                )
        elif kind == "deduced":
            if not _text(cell, "why"):
                raise AnalogMapError(f"{where}: una deducción sin su motivo")
            if found := sorted(cell.keys() & {"quote", "ref", "where"}):
                raise AnalogMapError(f"{where}: una deducción con {found}: o fuente o deducción")
        else:
            raise AnalogMapError(f"{where}: `basis` {kind!r}: se dice si es fuente o deducción")
        if cell.get("why") is not None and not _text(cell, "why"):
            raise AnalogMapError(f"{where}: `why` vacío: lo que no hay no se escribe")
        if claimed := _claims(cell.get("why") or ""):
            raise AnalogMapError(f"{where}: `why` reclama de más sobre EMMA ({claimed})")
    if not any(cell["status"] == "leaves_out" for cell in cells):
        raise AnalogMapError(
            f"{key}: no deja fuera ningún peligro; no existe banco de prueba completo (§3)"
        )
    hazard = CONTEXT_HAZARD.get(context or "")
    if hazard is not None:
        cell = next(item for item in cells if item["hazard"] == str(hazard))
        if cell["status"] not in CONTEXT_STATUSES:
            raise AnalogMapError(
                f"{key}: entorno {context!r} y el peligro «{hazard.display}» con «"
                f"{RIDGE_STATUS[cell['status']]}»: se contradicen"
            )


def _refs(item: Any) -> set[str]:
    """Las fichas que cita una pieza del mapa, a cualquier profundidad."""
    found: set[str] = set()
    if isinstance(item, dict):
        if isinstance(item.get("ref"), str):
            found.add(item["ref"])
        for value in item.values():
            found |= _refs(value)
    elif isinstance(item, list):
        for value in item:
            found |= _refs(value)
    return found


def _validate_ridge_refs(banks: list[dict[str, Any]]) -> None:
    """Una celda de fuente cita una página de su banco, y la que cita otro banco no lo es.

    `_quoted` solo mira que la ficha exista y sea de un sitio oficial: un `ref` copiado de la fila
    de otro banco, o el de un catálogo que nombra varios, pasaría por la página de este.
    """
    cited = {bank["id"]: _refs(bank) for bank in banks}
    for bank in banks:
        for cell in bank["ridge"]["cells"]:
            if cell["basis"] != "source":
                continue
            others = sorted(
                ident for ident, refs in cited.items()
                if ident != bank["id"] and cell["ref"] in refs
            )
            if others:
                raise AnalogMapError(
                    f"{bank['id']}/ridge/{cell['hazard']}: la ficha {cell['ref']!r} la cita "
                    f"también {others}: no es la página de este banco"
                )


def _validate_bank(bank: dict[str, Any], rungs: set[str]) -> None:
    key = str(bank.get("id", "?"))
    _fields(key, bank, BANK_FIELDS)
    for field in ("id", "name", "where", "context_basis", "emma_use"):
        if not _text(bank, field):
            raise AnalogMapError(f"{key}: falta `{field}`")
    _read_on(key, bank)
    if bank["full_name"] is not None and not _text(bank, "full_name"):
        raise AnalogMapError(f"{key}: `full_name` vacío: lo que no hay es null")
    if bank.get("rung") not in rungs:
        raise AnalogMapError(f"{key}: peldaño {bank.get('rung')!r} que la escalera no tiene")
    if bank.get("validation") not in VALIDATIONS:
        raise AnalogMapError(f"{key}: validación {bank.get('validation')!r} desconocida")
    context = bank.get("evidence_context")
    if context is None:
        if NO_CONTEXT_REASON not in bank["context_basis"].lower():
            raise AnalogMapError(
                f"{key}: sin entorno y sin decir por qué ningún valor del enumerado lo cubre"
            )
    elif context not in _CONTEXTS:
        raise AnalogMapError(
            f"{key}: entorno {context!r} fuera del enumerado de las observaciones; no se amplía"
        )
    if not bank.get("reproduces"):
        raise AnalogMapError(f"{key}: sin ninguna frase leída de lo que reproduce")
    for index, item in enumerate(bank["reproduces"]):
        _quoted(f"{key}/reproduces/{index}", item)
    if not bank.get("leaves_out"):
        raise AnalogMapError(f"{key}: ningún banco lo reproduce todo; falta qué deja fuera")
    for index, item in enumerate(bank["leaves_out"]):
        where = f"{key}/leaves_out/{index}"
        if not _text(item, "what"):
            raise AnalogMapError(f"{where}: falta `what`")
        basis = item.get("basis")
        if basis == "source":
            _quoted(where, item)
        elif basis == "deduced":
            if not _text(item, "why"):
                raise AnalogMapError(f"{where}: una deducción sin su motivo")
        else:
            raise AnalogMapError(f"{where}: `basis` {basis!r}: se dice si es fuente o deducción")
    for column in COLUMNS:
        _validate_column(f"{key}/{column}", bank[column])
    _validate_ridge(f"{key}/ridge", bank["ridge"], context)
    if bank["variables_kb"] is not None and not _text(bank, "variables_kb"):
        raise AnalogMapError(f"{key}: `variables_kb` vacía: lo que no hay es null")
    for field in ("emma_use", "context_basis"):
        if claimed := _claims(bank[field]):
            raise AnalogMapError(f"{key}: `{field}` reclama de más sobre EMMA ({claimed})")


def _validate_emma(
    validation: str, item: dict[str, Any], banks: dict[str, dict[str, Any]]
) -> None:
    key = f"{validation}/{item.get('id', '?')}"
    _fields(key, item, EMMA_FIELDS)
    for field in ("id", "ref", "context", "what", "does_not_show", "figures_in"):
        if not _text(item, field):
            raise AnalogMapError(f"{key}: falta `{field}`: lo que EMMA tiene y lo que no muestra")
    ref = registry.get(item["ref"])
    if ref.evidence_context is None or str(ref.evidence_context) != item["context"]:
        raise AnalogMapError(
            f"{key}: el entorno {item['context']!r} no es el de su ficha "
            f"({ref.evidence_context!s}): se dice el del estudio, no uno más cercano"
        )
    bank = item.get("bank")
    if bank is not None and bank not in banks:
        raise AnalogMapError(f"{key}: banco {bank!r} que el mapa no tiene")
    if validation == "operational" and (bank is None or banks[bank]["validation"] != validation):
        raise AnalogMapError(
            f"{key}: una validación operacional se hace con una tripulación en un banco "
            "operacional; un conjunto de datos no la da"
        )
    if not item["figures_in"].startswith(FIGURES_HOME):
        raise AnalogMapError(f"{key}: las cifras se remiten a {FIGURES_HOME}")
    for field in ("what", "does_not_show"):
        if COPIED_FIGURE.search(item[field]):
            raise AnalogMapError(f"{key}: `{field}` copia una cifra; se remite a {FIGURES_HOME}")
    if claimed := _claims(item["what"]):
        raise AnalogMapError(f"{key}: `what` reclama de más sobre EMMA ({claimed})")


def validate(raw: dict[str, Any]) -> dict[str, Any]:
    """Rechaza lo que no se pueda sostener con la página delante, o que diga de más sobre EMMA."""
    for block, head in (("rule", "text"), ("principle", "text"), ("ladder", "title")):
        if not isinstance(raw.get(block), dict) or not all(
            _text(raw[block], field) for field in (head, "where")
        ):
            raise AnalogMapError(f"`{block}` sin su texto y de dónde sale")
    rungs = raw["ladder"].get("rungs") or []
    if not rungs:
        raise AnalogMapError("la escalera sin peldaños")
    for rung in rungs:
        for field in ("id", "environment", "strength", "limitation", "use"):
            if not _text(rung, field):
                raise AnalogMapError(f"peldaño {rung.get('id', '?')}: falta `{field}`")
    rung_ids = {rung["id"] for rung in rungs}
    banks: dict[str, dict[str, Any]] = {}
    for bank in raw["banks"]:
        _validate_bank(bank, rung_ids)
        if bank["id"] in banks:
            raise AnalogMapError(f"{bank['id']}: banco repetido")
        banks[bank["id"]] = bank
    _validate_ridge_refs(raw["banks"])
    seen = []
    for validation in raw["validations"]:
        ident = validation.get("id")
        if ident not in VALIDATIONS:
            raise AnalogMapError(f"validación {ident!r} desconocida")
        seen.append(ident)
        for field in ("name", "what", "not_covered"):
            if not _text(validation, field):
                raise AnalogMapError(f"{ident}: falta `{field}`")
            if claimed := _claims(validation[field]):
                raise AnalogMapError(f"{ident}: `{field}` reclama de más sobre EMMA ({claimed})")
        if not isinstance(validation.get("emma"), list):
            raise AnalogMapError(f"{ident}: `emma` es la lista de lo que EMMA tiene, aunque vacía")
        for item in validation["emma"]:
            _validate_emma(ident, item, banks)
    if sorted(seen) != sorted(VALIDATIONS):
        raise AnalogMapError("hacen falta las dos validaciones, una vez cada una")
    if not all(isinstance(line, str) and line.strip() for line in raw["not_found"]):
        raise AnalogMapError("una línea vacía en `not_found`")
    return raw


@cache
def read() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(TESTBEDS_PATH.read_text(encoding="utf-8"))
    return validate(raw)


def cited_refs() -> frozenset[str]:
    """Las fichas del registro que sostienen alguna frase o alguna validación."""
    raw = read()
    refs = {
        item["ref"]
        for bank in raw["banks"]
        for item in [*bank["reproduces"], *bank["leaves_out"]]
        if "ref" in item
    }
    refs |= {
        item["ref"] for bank in raw["banks"] for column in COLUMNS
        for item in bank[column]["quotes"]
    }
    refs |= {
        cell["ref"] for bank in raw["banks"] for cell in bank["ridge"]["cells"]
        if cell["basis"] == "source"
    }
    refs |= {item["ref"] for validation in raw["validations"] for item in validation["emma"]}
    return frozenset(refs)


def _cited(item: dict[str, Any], read_on: str) -> dict[str, Any]:
    ref = registry.get(item["ref"])
    return {
        "quote": item["quote"],
        "where": item["where"],
        "read_on": read_on,
        "ref": ref.id,
        "source": ref.source,
        "url": ref.url,
        "organization": ref.organization,
        "date": ref.date,
        "unverified_display": [
            i18n.loc(registry.OPTIONAL_FIELDS[name]) for name in ref.unverified
        ],
    }


def _leaves_out(item: dict[str, Any], read_on: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "what": item["what"],
        "basis": item["basis"],
        "basis_text": _label(LEAVES_OUT_BASIS, LEAVES_OUT_BASIS_EN, item["basis"]),
        "why": item.get("why"),
        "cited": _cited(item, read_on) if item["basis"] == "source" else None,
    }
    return out


def _column(ident: str, column: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": ident,
        "label": _label(COLUMNS, COLUMNS_EN, ident),
        "read_on": column["read_on"],
        "quotes": [_cited(item, column["read_on"]) for item in column["quotes"]],
        "not_found": column["not_found"],
    }


def _ridge_cell(cell: dict[str, Any], read_on: str) -> dict[str, Any]:
    hazard = Ridge(cell["hazard"])
    return {
        "hazard": str(hazard),
        "hazard_display": i18n.loc(hazard.display),
        "status": cell["status"],
        "status_text": _label(RIDGE_STATUS, RIDGE_STATUS_EN, cell["status"]),
        "basis": cell["basis"],
        "basis_text": _label(RIDGE_BASIS, RIDGE_BASIS_EN, cell["basis"]),
        "why": cell.get("why"),
        "cited": _cited(cell, read_on) if cell["basis"] == "source" else None,
    }


def _emma_part(item: dict[str, Any]) -> dict[str, Any]:
    ref = registry.get(item["ref"])
    return {**item, "source": ref.source, "url": ref.url}


def _served() -> dict[str, Any]:
    """Lo cargado, con sus textos en el idioma de la petición: una copia, después de validar. La
    caché (`read`) guarda solo el castellano, que es lo que se valida y lo que las pruebas cotejan
    con los documentos."""
    return i18n.localized(read(), TESTBEDS_PATH)


def emma_status(validation_id: str) -> dict[str, str]:
    """Lo que EMMA tiene de una validación: «ninguna» si la lista está vacía, nunca a mano."""
    return _emma_status(
        next(item for item in _served()["validations"] if item["id"] == validation_id)
    )


def _emma_status(validation: dict[str, Any]) -> dict[str, str]:
    status = EMMA_PART if validation["emma"] else EMMA_NONE
    return {
        "status": "none" if status == EMMA_NONE else "partial",
        "text": i18n.tr(
            f"{validation['name']} de EMMA: {status}.",
            f"{validation['name']} of EMMA: {EMMA_STATUS_EN[status]}.",
        ),
    }


def payload() -> dict[str, Any]:
    """El mapa como se sirve: cada cita resuelta en su ficha y cada peldaño con sus bancos."""
    raw = _served()
    banks = raw["banks"]
    return {
        "note": i18n.loc(NOTE),
        # Copias: lo que se sirve no comparte diccionarios con lo cargado en caché.
        "rule": dict(raw["rule"]),
        "principle": dict(raw["principle"]),
        # La cabecera de la matriz: los cinco peligros y los cuatro estados, con su palabra.
        "ridge": {
            "note": i18n.loc(RIDGE_NOTE),
            "hazards": [
                {"id": str(hazard), "display": i18n.loc(hazard.display)} for hazard in Ridge
            ],
            "statuses": [
                {"id": key, "text": _label(RIDGE_STATUS, RIDGE_STATUS_EN, key)}
                for key in RIDGE_STATUS
            ],
        },
        "ladder": {
            "title": raw["ladder"]["title"],
            "where": raw["ladder"]["where"],
            "rungs": [
                {
                    **rung,
                    "banks": [bank["id"] for bank in banks if bank["rung"] == rung["id"]],
                }
                for rung in raw["ladder"]["rungs"]
            ],
        },
        "validations": [
            {
                "id": validation["id"],
                "name": validation["name"],
                "what": validation["what"],
                "banks": [bank["id"] for bank in banks if bank["validation"] == validation["id"]],
                "emma": [_emma_part(item) for item in validation["emma"]],
                "emma_status": _emma_status(validation),
                "not_covered": validation["not_covered"],
            }
            for validation in raw["validations"]
        ],
        "banks": [
            {
                "id": bank["id"],
                "name": bank["name"],
                "full_name": bank["full_name"],
                "where": bank["where"],
                "read_on": bank["read_on"],
                "rung": bank["rung"],
                "validation": bank["validation"],
                "validation_text": _label(
                    VALIDATIONS, VALIDATIONS_EN, bank["validation"]
                ),
                "evidence_context": bank["evidence_context"],
                # Sin entorno: la palabra con que el registro dice que ningún valor lo cubre.
                "outside_enum_text": (
                    i18n.loc(registry.OUTSIDE_ENUM)
                    if bank["evidence_context"] is None else None
                ),
                "context_basis": bank["context_basis"],
                "reproduces": [_cited(item, bank["read_on"]) for item in bank["reproduces"]],
                "leaves_out": [
                    _leaves_out(item, bank["read_on"]) for item in bank["leaves_out"]
                ],
                "columns": [_column(ident, bank[ident]) for ident in COLUMNS],
                "ridge_read_on": bank["ridge"]["read_on"],
                "ridge": [
                    _ridge_cell(cell, bank["ridge"]["read_on"]) for cell in bank["ridge"]["cells"]
                ],
                "variables_kb": bank["variables_kb"],
                "emma_use": bank["emma_use"],
            }
            for bank in banks
        ],
        "not_found": list(raw["not_found"]),
    }
