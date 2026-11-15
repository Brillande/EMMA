# SPDX-License-Identifier: AGPL-3.0-or-later
"""¿El artículo citado respalda las cifras de la frase, o solo existe?

Por qué existe: `citations.py` comprueba que una cita existe y `tier.py` qué nivel de evidencia es.
Una cita real a la que se le atribuye una cifra que no dice pasa las dos. Es el fallo más dañino
de una justificación clínica: "52 % de 728 astronautas (PMID X)" se lee y se recuerda aunque X
diga otra cosa.

Adaptador de `polaris/tools/soporte_cita.py`, de la copia literal de Polaris, sin modificarla
(commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the
Protocol»; se carga con `app.polaris.load`). Del original, sin tocar: `clean_source`
(`_limpia_fuente`), `entities` (`entidades`), la canonicalización de cifras (`_num_canon`) y la
normalización (`_plano`).

Siguen ADAPTADAS a mano de `tools/soporte_cita.py` @ 7bf47257 (el commit que se copió primero),
por divergencia con el original (cambios AGPL §5a, docs/polaris-divergencias.md):
  * `numbers()`: en un resumen inglés, una fracción ("382/728") y un rango ("7-10") aportan sus
    dos cifras. Polaris descarta el número pegado a una barra (para que "CDK4/6" no cuente) y con
    eso daba "728 no está" contra Kerstman 2012, que sí lo dice. Lo demuestran
    `test_a_fraction_in_the_abstract_backs_both_figures` y `..._range_...`, y dos mutantes.
  * `check()`: es `cotejar()` con ese `numbers()`, sin los alias oncológicos y con el detalle en
    inglés; el `cotejar()` original usa su `numeros()` y no vería la fracción.
El resto de lo que hacía la versión portada (red, juez semántico, texto completo) no se usa: sin
red en la aplicación, el resumen lo baja `tests/test_citation_support_live.py` (marcado `live`).

LO QUE NO HACE, como dice el original: "respalda literal" es que las cifras y las siglas están en
el resumen, no que el artículo respalde la frase. La dirección del efecto y la población siguen
siendo de lectura humana.
"""

from __future__ import annotations

import re
from functools import cache
from typing import Any, cast

from app import polaris

SUPPORTS = "RESPALDA_LITERAL"
NOT_SUPPORTED = "NO_RESPALDA"
DOUBTFUL = "DUDOSO"
NOT_ASSESSABLE = "NO_EVALUABLE"

_NUMBER = re.compile(r"(?<![A-Za-z0-9.,/-])(\d+(?:[.,]\d+)?)(?![A-Za-z0-9/]|[.,]\d)")
_CATEGORY = re.compile(
    r"(fase|phase|grado|grade|estadio|stage|l[ií]nea|line|brazo|arm|cohorte|cohort|nivel|"
    r"level|tier|apartado|secci[oó]n|paso|punto)\s*$",
    re.I,
)
_THOUSANDS_ES = re.compile(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+)(?![\d,])")
_THOUSANDS_EN = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+)(?![\d.])")
_CITATION = re.compile(
    r"10\.\d{4,9}/\S+|NCT\d{8}|PMID\s*[:#]?\s*\d{1,9}|arXiv\s*:?\s*\d{4}\.\d{4,5}(?:v\d+)?", re.I
)
_YEAR = re.compile(r"^(19[5-9]\d|20[0-4]\d)$")
_MONTH = r"(?:ene|feb|mar|abr|may|jun|jul|ago|sep|sept|oct|nov|dic|jan|apr|aug|dec)[a-z]*"
_NOISE = re.compile(
    r"\]\([^)]*\)"
    r"|\S*[/\\]\S*"
    r"|\b\d{1,2}\s*(?:de\s+|-|/|\s)" + _MONTH + r"\b(?:[-/\s]*(?:de\s+)?\d{2,4})?"
    r"|\b\d{1,2}[-/]\d{1,2}(?:[-/]\d{2,4})?\b"
    r"|\b\d{1,2}:\d{2}\b"
    r"|(?m:^\s*(?:[-*|]\s*)?\d{1,2}[.)]\s)"
    r"|(?<=[.:!?]\s)\d{1,2}[.)]\s"
    r"|\b\d{1,4};\s*\d{1,4}(?:\(\d+\))?:\s*\d+(?:-\d+)?"
    r"|\b[A-Z]{1,6}-\d+",
    re.I,
)
_LONG_ID = re.compile(r"^\d{6,}$")
_FRACTION = re.compile(r"(?<![\w.])(\d+)/(\d+)(?![\w.])")
_RANGE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)(?![\w.])")


@cache
def _original() -> Any:
    return polaris.load("soporte_cita")


def _plain(text: str) -> str:
    return cast(str, _original()._plano(text))


def _canonical(token: str) -> str:
    """«12,50» → «12.5»; «0,5» → «0.5»."""
    return cast(str, _original()._num_canon(token))


def clean_source(text: str) -> str:
    """Entidades HTML fuera y el punto medio decimal ("14·4") como punto."""
    return cast(str, _original()._limpia_fuente(text))


def numbers(text: str, language: str = "es") -> list[str]:
    """Cifras de un texto, canonicalizadas: `numeros()` de Polaris más fracciones y rangos."""
    text = re.sub(r"[‐-―−]", "-", _CITATION.sub(" ", clean_source(text)))
    if language == "es":
        text = _NOISE.sub(" ", text)
        text = _THOUSANDS_ES.sub(lambda m: m.group(1).replace(".", ""), text)
    text = _THOUSANDS_EN.sub(lambda m: m.group(1).replace(",", ""), text)
    if language == "en":
        # Una fracción de un resumen ("52% (382/728)") aporta sus dos cifras. En Polaris el número
        # pegado a una barra se descarta para que "CDK4/6" no cuente, y con eso se perdían las
        # fracciones: daba "728 no está" contra el resumen de Kerstman 2012, que sí lo dice.
        text = _FRACTION.sub(r"\1 \2", text)
        # Igual con un rango ("7-10 to severe pain"): el número tras el guion también cuenta.
        text = _RANGE.sub(r"\1 \2", text)
    found: list[str] = []
    for match in _NUMBER.finditer(text):
        if _CATEGORY.search(text[max(0, match.start() - 12):match.start()]):
            continue
        value = _canonical(match.group(1))
        if language == "es" and (_YEAR.match(value) or _LONG_ID.match(value)):
            continue
        if value not in found:
            found.append(value)
    return found


def entities(text: str) -> list[str]:
    """Siglas o nombres técnicos (HER2, SANS, IJV): `entidades()` del original."""
    return list(_original().entidades(text))


def check(claim: str, abstract: str) -> tuple[str, dict[str, Any]]:
    """(estado, detalle). `cotejar()` de Polaris con el `numbers()` de arriba; no toca la red."""
    if not (abstract or "").strip():
        return NOT_ASSESSABLE, {"reason": "el registro no trae resumen"}
    claim_numbers = numbers(claim, "es")
    claim_entities = entities(claim)
    if not claim_numbers and not claim_entities:
        return NOT_ASSESSABLE, {"reason": "la frase no trae cifras ni siglas que cotejar"}
    abstract_numbers = set(numbers(abstract, "en"))
    plain_abstract = _plain(abstract)
    missing_numbers = [n for n in claim_numbers if n not in abstract_numbers]
    missing_entities = [e for e in claim_entities if e not in plain_abstract]
    detail: dict[str, Any] = {
        "numbers": claim_numbers,
        "entities": claim_entities,
        "missing_numbers": missing_numbers,
        "missing_entities": missing_entities,
    }
    if missing_numbers:
        return NOT_SUPPORTED, detail
    if missing_entities:
        return DOUBTFUL, detail
    return SUPPORTS, detail
