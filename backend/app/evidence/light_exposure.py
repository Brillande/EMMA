"""La luz que llega a los ojos de un tripulante: qué hay publicado, y que NASA no da un límite.

La cabina ya tenía su lectura (`environment/habitat.py`): la norma fija niveles por tarea y por
periodo, no un límite general, y la luz se muestra sin evaluarse. Quedaba abierta la otra
pregunta, la de la PERSONA: ¿hay un límite o una recomendación publicada de cuánta luz debe
recibir un tripulante y cuándo? Es fácil contestarla mal por dos caminos:

- **Tomar el requisito de cabina por un límite personal.** La tabla 8.7-2 de NASA-STD-3001
  Vol 2 se mide en la córnea, y por eso parece de la persona; pero el texto obliga al SISTEMA
  de iluminación («The system shall provide...»). Y [V2 6117], el único límite que la norma
  llama «crew exposure» a la luz, es de seguridad del ojo y de la piel, fuente a fuente, con
  las fórmulas de la ACGIH: no es una dosis diaria de luz.
- **Traer de Tierra una recomendación como si fuera de vuelo.** Brown et al. (2022) sí da
  cifras para la persona (EDI melanópica en el ojo, de día, por la tarde y donde se duerme),
  pero los autores dicen que valen para adultos sanos con horario diurno regular y que NO
  están pensadas para el trabajo de noche: una tripulación con cambios de turno queda fuera.

Lo leído el 2026-10-14 vive en `data/light_exposure_read.json` y este cargador es su defensa:
una frase sin sección o sin ficha oficial no se sirve, una cifra tiene que estar escrita en su
frase, una recomendación no se sirve sin a quién se aplica, y un límite de NASA no se puede
declarar sin la frase que lo escribe. Nada de esto se evalúa ni entra en el riesgo
(invariante 5): EMMA no tiene sensor de luz en el ojo de nadie, y lo que mide en cabina es
iluminancia en lux, otra magnitud. Tampoco sale a la red: la lectura se hizo una vez, en Tierra.
"""

from __future__ import annotations

import datetime as dt
import json
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.core import i18n
from app.evidence import registry
from app.evidence.instruments_read import EXTENTS, OFFICIAL_HOSTS
from app.evidence.read_contract import check_sources

READ_PATH = Path(__file__).resolve().parents[1] / "data" / "light_exposure_read.json"

DISPLAY = "Exposición personal a la luz"
LABEL = "contexto leído; no se evalúa"
NO_NASA_LIMIT = (
    "Sin límite personal publicado por NASA: la norma da la luz que debe proporcionar el "
    "sistema de iluminación por periodo ([V2 8055], medida en la córnea) y un límite de "
    "seguridad del ojo y de la piel para cada fuente ([V2 6117]), no cuánta luz debe recibir "
    "un tripulante."
)
NOT_MEASURED = (
    "EMMA no mide la luz que llega a los ojos de nadie: no tiene sensor personal de luz, y la "
    "lectura de cabina es iluminancia en lux, no EDI melanópica en el ojo. Nada de esto se "
    "compara con ninguna lectura ni entra en el riesgo."
)
NOT_FLIGHT = (
    "Las cifras publicadas para una persona son una recomendación de consenso para interiores "
    "en Tierra, para adultos sanos con horario diurno regular; sus autores dicen que no están "
    "pensadas para el trabajo de noche. No son un límite de vuelo."
)
i18n.en_many({
    DISPLAY: "Personal light exposure",
    LABEL: "context read; not assessed",
    NO_NASA_LIMIT: (
        "No personal limit published by NASA: the standard gives the light the lighting system "
        "is to provide by period ([V2 8055], measured at the cornea) and an eye and skin safety "
        "limit for each source ([V2 6117]), not how much light a crew member is to receive."
    ),
    NOT_MEASURED: (
        "EMMA does not measure the light reaching anyone's eyes: it has no personal light "
        "sensor, and the cabin reading is illuminance in lux, not melanopic EDI at the eye. "
        "None of this is compared with any reading or enters the risk."
    ),
    NOT_FLIGHT: (
        "The figures published for a person are a consensus recommendation for indoor "
        "environments on Earth, for healthy adults with a regular daytime schedule; their "
        "authors say they are not intended for night work. They are not a flight limit."
    ),
})
# El inglés de cuánto se leyó (`EXTENTS`), al lado y no en el registro común: es un rótulo corto
# que otros cargadores también enseñan, cada uno con el suyo.
_EXTENT_TEXT_EN = {EXTENTS["full"]: "read in full", EXTENTS["partial"]: "read in part"}


class LightExposureError(ValueError):
    """Lo leído no cumple su contrato: no se sirve."""


def _text(item: dict[str, Any], field: str) -> bool:
    value = item.get(field)
    return isinstance(value, str) and bool(value.strip())


def _validate_statement(item: dict[str, Any], sources: dict[str, Any]) -> None:
    key = item.get("id", "?")
    for field in ("id", "label", "quote", "ref", "where"):
        if not _text(item, field):
            raise LightExposureError(
                f"{key}: falta `{field}`: sin frase, sección y fuente no es un dato"
            )
    if item["ref"] not in sources:
        raise LightExposureError(f"{key}: de {item['ref']!r} no se declara cuánto se leyó")
    url = registry.get(item["ref"]).url
    parts = urlsplit(url or "")
    if parts.scheme != "https" or parts.hostname not in OFFICIAL_HOSTS:
        raise LightExposureError(f"{key}: {url!r} no es la revista, PubMed Central ni NASA")


def _number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and value >= 0


def _validate_recommendations(
    recommendations: dict[str, Any], statements: dict[str, dict[str, Any]]
) -> None:
    if not _text(recommendations, "quantity") or not _text(recommendations, "setting"):
        raise LightExposureError("recommendations: falta la magnitud o dónde se aplican")
    if not recommendations["scope"]:
        # Una cifra sin a quién se aplica se leería como válida para cualquiera.
        raise LightExposureError("recommendations: falta a quién se aplican (`scope`)")
    for ref in recommendations["scope"]:
        if ref not in statements:
            raise LightExposureError(f"recommendations/scope: {ref!r} no es una frase leída")
    periods: set[str] = set()
    for item in recommendations["items"]:
        where = f"recommendations/{item.get('period', '?')}"
        if not _text(item, "period") or not _text(item, "label"):
            raise LightExposureError(f"{where}: falta el periodo o su rótulo")
        if item["period"] in periods:
            raise LightExposureError(f"{where}: periodo repetido")
        periods.add(item["period"])
        statement = statements.get(item.get("statement"))
        if statement is None:
            raise LightExposureError(f"{where}: la cifra no apunta a ninguna frase leída")
        literal = item.get("literal")
        if not isinstance(literal, str) or not literal.strip() or literal not in statement["quote"]:
            raise LightExposureError(
                f"{where}: {literal!r} no está escrito en la frase que lo sostiene"
            )
        low, high = item.get("low"), item.get("high")
        bounds = [value for value in (low, high) if value is not None]
        if len(bounds) != 1 or not all(_number(value) for value in bounds):
            raise LightExposureError(f"{where}: una recomendación es un mínimo o un máximo")
        # La cifra del rango, escrita tal cual en el literal: «250 lux» con un 250.
        figure = f"{bounds[0]:g} lux"
        if figure not in literal:
            raise LightExposureError(f"{where}: {figure!r} no es la cifra de su literal")
        word = "minimum" if low is not None else "maximum"
        if word not in literal:
            raise LightExposureError(f"{where}: el literal no dice que sea un {word}")


def validate(raw: dict[str, Any]) -> dict[str, Any]:
    """Rechaza lo que no se pueda sostener con la fuente delante."""
    try:
        dt.date.fromisoformat(raw["read_on"])
    except (KeyError, TypeError, ValueError):
        raise LightExposureError(
            "falta `read_on`: una lectura sin fecha no se puede contrastar"
        ) from None
    sources = check_sources(raw, LightExposureError, EXTENTS)  # el contrato común de las fuentes
    statements: dict[str, dict[str, Any]] = {}
    for item in raw["statements"]:
        _validate_statement(item, sources)
        if item["id"] in statements:
            raise LightExposureError(f"{item['id']}: identificador repetido")
        statements[item["id"]] = item
    limit = raw["nasa_personal_limit"]
    if limit is not None and limit not in statements:
        # Un límite de NASA solo existe con la frase que lo escribe.
        raise LightExposureError("nasa_personal_limit: no apunta a ninguna frase leída")
    if limit is None and not raw["searched"]:
        raise LightExposureError("sin límite de NASA hay que decir dónde se buscó (`searched`)")
    if not all(isinstance(line, str) and line.strip() for line in raw["searched"]):
        raise LightExposureError("una línea vacía en `searched`")
    _validate_recommendations(raw["recommendations"], statements)
    for ref in raw["context"]:
        if ref not in statements:
            raise LightExposureError(f"context: {ref!r} no es una frase leída")
    return raw


@cache
def read() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(READ_PATH.read_text(encoding="utf-8"))
    return validate(raw)


def cited_refs() -> frozenset[str]:
    """Las fichas del registro de las que se declara lectura."""
    return frozenset(read()["sources"])


def _statement(statement_id: str) -> dict[str, Any]:
    raw = read()
    item = next(entry for entry in raw["statements"] if entry["id"] == statement_id)
    ref = registry.get(item["ref"])
    source = raw["sources"][item["ref"]]
    # El rótulo y el sitio de la frase los redacta EMMA: en el idioma de la petición. La frase
    # (`quote`) es de la fuente y no está en el hermano inglés.
    item = i18n.localized(item, READ_PATH)
    return {
        "id": item["id"],
        "label": item["label"],
        "quote": item["quote"],
        "ref": ref.id,
        "source": ref.source,
        "title": ref.title,
        "url": ref.url,
        "where": item["where"],
        "read_on": raw["read_on"],
        "extent": source["extent"],
        "extent_text": _extent_text(EXTENTS[source["extent"]]),
    }


def _extent_text(text: str) -> str:
    """Cuánto se leyó de una fuente, en el idioma de la petición.

    Se busca por el texto castellano de `EXTENTS`, que es de otro módulo: uno que se añada
    allí sin su inglés aquí sale en castellano, no tumba la respuesta.
    """
    return i18n.tr(text, _EXTENT_TEXT_EN.get(text, text))


def summary() -> dict[str, Any]:
    """Lo que se sabe de la exposición personal a la luz, tal como se sirve.

    `evaluated` es siempre falso y no sale del fichero: no hay lectura con la que comparar.
    """
    raw = read()
    limit = raw["nasa_personal_limit"]
    # Lo buscado, la magnitud, dónde se aplican y el rótulo de cada periodo, en el idioma de la
    # petición: el hermano inglés se aplica aquí, al servir, y no en `read()`, que está cacheado.
    recommendations = i18n.localized(raw["recommendations"], READ_PATH)
    shown = {
        "display": i18n.loc(DISPLAY),
        "label": i18n.loc(LABEL),
        "evaluated": False,
        "nasa_personal_limit": None if limit is None else _statement(limit),
        "status": NO_NASA_LIMIT if limit is None else None,
        "not_measured": i18n.loc(NOT_MEASURED),
        "searched": list(i18n.localized(raw["searched"], READ_PATH)),
        "recommendations": {
            "quantity": recommendations["quantity"],
            "setting": recommendations["setting"],
            "note": i18n.loc(NOT_FLIGHT),
            "items": [
                {
                    "period": item["period"],
                    "label": item["label"],
                    "low": item["low"],
                    "high": item["high"],
                    "unit": "lx",
                    "literal": item["literal"],
                    "statement": _statement(item["statement"]),
                }
                for item in recommendations["items"]
            ],
            "scope": [_statement(ref) for ref in recommendations["scope"]],
        },
        "context": [_statement(ref) for ref in raw["context"]],
        "read_on": raw["read_on"],
    }
    if shown["status"] is not None:
        shown["status"] = i18n.loc(shown["status"])
    return shown
