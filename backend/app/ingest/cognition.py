"""Las puntuaciones de una sesión de la batería Cognition de NASA, como observaciones del catálogo.

POR QUÉ EXISTE
--------------
El usuario pidió (2026-11-03) que las pruebas psicomotrices sean las del protocolo de NASA. Las
nueve pruebas de la batería Cognition que no son la PVT ya estaban en el catálogo como 17
indicadores descriptivos (`codes.COGNITION_CODES`, decimonovena ronda), pero no había por dónde
anotar una sesión entera: solo la ingesta genérica, lectura a lectura y sin quién teclea.

Lo que este módulo NO hace, a propósito:

- **No pasa las pruebas ni las puntúa.** Cognition es software de terceros (Basner et al. 2015:
  «15 unique forms of 10 neuropsychological tests»), con sus estímulos, sus quince versiones y su
  puntuación. Reimplementarlo en un navegador daría cifras con el nombre de la batería que no
  serían las suyas. EMMA registra lo que el programa de la batería ya calculó.
- **No compara con normas ni con la línea base.** Las cifras son descriptivas
  (`codes.DESCRIPTIVE_ONLY`): fuera del riesgo, de las alertas y de la huella de reglas. Lo que
  la fuente publica de 25 astronautas (Dev et al. 2024, su Tabla 1) no se adopta como rango.

Lo que sí hace: comprueba que cada clave es de la batería, que cada prueba enviada llega con todas
sus puntuaciones y que cada cifra cae en el rango físico del catálogo, y construye las
observaciones con el modelo canónico (`fhir.observation`), que las rechaza otra vez si algo se
escapa. Quien las firma y las anexa al ledger es la ruta (`api/cognition.py`, invariante 4).

Que una prueba enviada lleve todas sus puntuaciones es diseño de EMMA, sin fuente leída: el
programa de la batería da la velocidad y la precisión de cada prueba juntas (Dev et al. 2024,
«speed … and accuracy scores»), y una velocidad sin su precisión es una sesión copiada a medias.
Una sesión puede traer menos de nueve pruebas: lo leído no dice qué hace el programa con una
prueba interrumpida, y EMMA no rellena las que faltan.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.core import display
from app.ingest.codes import (
    CATALOG,
    COGNITION_CODES,
    COGNITION_KEYS,
    COGNITION_TESTS,
    CognitionTest,
)

# La décima prueba de la batería, que tiene su consola y sus indicadores propios (`ingest/pvt.py`).
PVT_KEYS = frozenset({"pvt-mean-rt", "pvt-lapses"})


class InvalidSession(ValueError):
    """La sesión no se puede registrar tal cual. Lleva todos los motivos, no solo el primero."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True, slots=True)
class CognitionField:
    """Una puntuación de una prueba: qué indicador del catálogo es y con qué frase se lee.

    `statement` es el identificador de la frase leída (`data/instruments_read.json`) que dice qué
    es esa cifra; se resuelve con su ficha al servirla.
    """

    key: str
    test: CognitionTest
    measure: str  # "speed", "accuracy" o "risk"
    statement: str


def _measure(key: str) -> str:
    return key.rsplit("-", 1)[1]


def _statement(test: CognitionTest, measure: str) -> str:
    """La frase de Dev et al. 2024 que define esa puntuación de esa prueba."""
    if measure == "speed":
        return "cog-speed-definition"
    if measure == "risk":
        return "cog-bart-risk"
    if test.accuracy == "proportion":
        # El F2B y el LOT: una proporción calculada de otra forma, con su frase propia.
        return f"cog-{test.abbrev}-accuracy"
    return "cog-accuracy-proportion"


def _fields() -> tuple[CognitionField, ...]:
    by_prefix = {f"cognition-{test.abbrev}-": test for test in COGNITION_TESTS}
    found = []
    for code in COGNITION_CODES:
        test = next(test for prefix, test in by_prefix.items() if code.key.startswith(prefix))
        measure = _measure(code.key)
        found.append(CognitionField(code.key, test, measure, _statement(test, measure)))
    return tuple(found)


# En el orden del catálogo, que es el de administración de la batería.
FIELDS: tuple[CognitionField, ...] = _fields()
_BY_KEY = {field.key: field for field in FIELDS}


def keys_of(test: CognitionTest) -> tuple[str, ...]:
    """Las claves que deja una prueba, en el orden del catálogo."""
    return tuple(field.key for field in FIELDS if field.test == test)


def field(key: str) -> CognitionField:
    return _BY_KEY[key]


def problems(scores: Mapping[str, Any]) -> list[str]:
    """Por qué estas puntuaciones no se pueden registrar; vacío si se pueden."""
    found: list[str] = []
    if not scores:
        return ["la sesión no trae ninguna puntuación"]
    unknown = sorted(key for key in scores if key not in COGNITION_KEYS)
    pvt = [key for key in unknown if key in PVT_KEYS]
    other = [key for key in unknown if key not in PVT_KEYS]
    if pvt:
        found.append(
            f"{', '.join(pvt)}: la PVT se pasa y se registra en su consola (/api/pvt/console), "
            f"no aquí"
        )
    if other:
        found.append(f"{', '.join(other)}: no es una puntuación de la batería Cognition")
    for test in COGNITION_TESTS:
        keys = keys_of(test)
        present = [key for key in keys if key in scores]
        if present and len(present) < len(keys):
            missing = [key for key in keys if key not in scores]
            found.append(
                f"{test.sigla}: llega {', '.join(present)} sin {', '.join(missing)}; una prueba "
                f"se registra con todas sus puntuaciones"
            )
    for key, value in scores.items():
        if key not in COGNITION_KEYS:
            continue
        code = CATALOG[key]
        if isinstance(value, bool) or not isinstance(value, int | float):
            found.append(f"{key}: no es una cifra")
            continue
        if not math.isfinite(value):
            found.append(f"{key}: no es una cifra finita")
            continue
        if not code.is_physically_possible(float(value)):
            decimals = display.decimals_for(key)
            unit = display.unit(code.unit)
            low, high = code.physical_min, code.physical_max
            # Un extremo sin declarar no se rellena con un cero inventado: se nombra el que hay.
            bounds = " y ".join(
                part for part in (
                    f"desde {display.number(low, decimals)}" if low is not None else "",
                    f"hasta {display.number(high, decimals)}" if high is not None else "",
                ) if part
            )
            found.append(
                f"{key}: {display.number(float(value), decimals)} {unit} está fuera del rango "
                f"físico del catálogo, {bounds} {unit}".replace("  ", " ").strip()
            )
    return found


def to_observations(
    scores: Mapping[str, float], subject: str, effective: Any, source: str
) -> list[Any]:
    """Las puntuaciones como observaciones del catálogo, en el orden del catálogo.

    Lanza `InvalidSession` con todos los motivos si alguna no se puede registrar: o entra la
    sesión entera, o no entra nada.
    """
    from app.ingest.fhir import observation

    found = problems(scores)
    if found:
        raise InvalidSession(found)
    return [
        observation(item.key, float(scores[item.key]), effective, subject, source)
        for item in FIELDS
        if item.key in scores
    ]
