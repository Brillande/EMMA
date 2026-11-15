"""Lo leído sobre los instrumentos de la tripulación: la frase de la fuente, no un parecido.

La prueba de vigilancia psicomotora de la consola declaraba sus parámetros como «diseño de
EMMA, sin fuente leída», y las escalas de autoinforme, «sin rótulos verificados». Era verdad,
y era también un hueco: el umbral de lapso se sostenía en una «definición canónica» que nadie
había leído. El 2026-10-13 se leyeron los dos artículos que definen la prueba, y la lectura
enseñó por qué no se podía rellenar de memoria: la prueba de 10 minutos y su versión breve de
3 minutos usan intervalos y umbrales de lapso DISTINTOS, y lo que se sabe de una no vale para
la otra.

Lo leído vive en `data/instruments_read.json` y este cargador es la defensa:

- una frase sin sección, sin ficha en el registro o de un sitio que no es la revista, PubMed
  Central, NASA, (desde el 2026-11-04, para el glucómetro, y el 2026-11-14 para el test casero
  de ovulación) una agencia de salud pública de EE. UU. o (desde el 2026-11-14, solo en las
  medidas del ciclo y, desde el 2026-11-15, en el estado reproductivo y los síntomas vasomotores)
  la documentación de la API de HealthKit o de Health Connect no se sirve;
- un valor publicado tiene que estar escrito, tal cual, en la frase que lo sostiene: no se
  puede enseñar «355 ms» junto a una cita que no lo dice;
- un rótulo de escala tiene que estar en su frase, pegado a su número, y dentro del rango del
  catálogo;
- **una escala propia de la misión no admite rótulos**: no hay fuente que la defina, y ponerle
  las anclas de otra escala sería atribuirle una fuente que no tiene. Sus anclas existen desde
  el 2026-10-15, pero no viven aquí: son una decisión de diseño de EMMA, sin validar, y las
  declara el catálogo (`codes.OWN_SCALE_ANCHORS`). Este fichero es de lo leído, y de esas
  tres escalas no hay nada que leer;
- el criterio de aceptable de una escala (`criterion`, decisión del usuario del 2026-10-15
  sobre la comida) tiene que estar escrito en su frase con la misma cifra: si la fuente no
  escribe «6.0», no se adopta un 6,0;
- cada indicador descriptivo (`codes.DESCRIPTIVE_ONLY`, decisiones del usuario del 2026-10-15 y,
  para la vitamina D, del 2026-10-22) tiene su medida leída (`measures`), o no se sirve nada:
  solo entra lo que tiene fuente. Una categoría que la fuente da con palabras («mild (does not
  affect daily activities)») tiene que estar escrita tal cual en su frase; su número es de EMMA,
  y `numbering` lo tiene que decir.

No puntúa nada y no entra en el análisis (invariante 5): lo que puntúa una prueba sigue en
`ingest/pvt.py`. Tampoco sale a la red: la lectura se hizo una vez, en Tierra.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.evidence import registry
from app.evidence.read_contract import check_sources
from app.ingest.codes import (
    CATALOG,
    CYCLE_KEYS,
    DESCRIPTIVE_ONLY,
    REPRODUCTIVE_KEYS,
    VitalCode,
)

READ_PATH = Path(__file__).resolve().parents[1] / "data" / "instruments_read.json"

# La revista o PubMed Central, y los sitios oficiales de NASA. Un buscador no es una fuente.
OFFICIAL_HOSTS = frozenset({
    "pmc.ncbi.nlm.nih.gov",
    "pubmed.ncbi.nlm.nih.gov",
    "doi.org",
    "ntrs.nasa.gov",
    "www.nasa.gov",
    "humanresearchroadmap.nasa.gov",
})
# Las páginas de las agencias de salud pública de EE. UU. que explican al público cómo se toma una
# medida (2026-11-04, el glucómetro de la glucosa capilar): ni la revista ni NASA tienen el paso a
# paso de un glucómetro; el 2026-11-14 entró la de MedlinePlus del test casero de ovulación,
# por la misma razón. Solo valen en este fichero: el sentido en vuelo y la luz siguen pidiendo
# la revista, PubMed Central o NASA (`OFFICIAL_HOSTS`, que importan).
PUBLIC_HEALTH_HOSTS = frozenset({"www.cdc.gov", "medlineplus.gov"})
# La documentación de las dos API de las que llegan los registros del ciclo y la anticoncepción
# (2026-11-14, lote «ciclo»): las categorías de flujo, de test de ovulación y de anticonceptivo
# SON las que define la API, y no las escribe ninguna revista ni NASA. Solo valen en este
# fichero, y solo para decir qué categorías da la fuente de datos: no sostienen ningún efecto
# fisiológico ni nada del vuelo.
DATA_API_HOSTS = frozenset({"developer.apple.com", "developer.android.com"})
# Las únicas medidas que pueden citar esa documentación: la promesa de arriba, impuesta. Desde el
# 2026-11-15 entran también el estado reproductivo y los síntomas vasomotores, cuyas categorías
# (el estado menopáusico y la gravedad de un síntoma) también define HealthKit. La terapia
# hormonal no: ninguna de las dos API la registra, y su fuente es MedlinePlus.
DATA_API_MEASURES = CYCLE_KEYS | (REPRODUCTIVE_KEYS - {"menopausal-hormone-therapy"})

# Cuánto se leyó de cada documento. No hay valor por defecto: quien cita lo declara.
EXTENTS = {"full": "leído entero", "partial": "leído en parte"}

# Las escalas que el catálogo declara propias de la misión (`codes.MISSION_SPECIFIC`): ninguna
# fuente las define. Sus anclas las decidió EMMA (`codes.OWN_SCALE_ANCHORS`, sin validar): no
# son un dato leído y no entran en este fichero.
OWN_SCALES = frozenset({"mood-valence", "symptom-burden", "appetite-rating"})

_SCORE_UNIT = "{score}"


class InstrumentsError(ValueError):
    """Lo leído no cumple su contrato: no se sirve."""


def _text(item: dict[str, Any], field: str) -> bool:
    value = item.get(field)
    return isinstance(value, str) and bool(value.strip())


def _validate_statement(item: dict[str, Any], sources: dict[str, Any]) -> None:
    key = item.get("id", "?")
    for field in ("id", "label", "quote", "ref", "where"):
        if not _text(item, field):
            raise InstrumentsError(
                f"{key}: falta `{field}`: sin frase, sección y fuente no es un dato"
            )
    if item["ref"] not in sources:
        raise InstrumentsError(f"{key}: de {item['ref']!r} no se declara cuánto se leyó")
    # Una frase leída otro día que el resto lleva su fecha; si la lleva, es una fecha.
    if "read_on" in item:
        try:
            dt.date.fromisoformat(item["read_on"])
        except (TypeError, ValueError):
            raise InstrumentsError(f"{key}: `read_on` no es una fecha") from None
    url = registry.get(item["ref"]).url
    parts = urlsplit(url or "")
    allowed = OFFICIAL_HOSTS | PUBLIC_HEALTH_HOSTS | DATA_API_HOSTS
    if parts.scheme != "https" or parts.hostname not in allowed:
        raise InstrumentsError(
            f"{key}: {url!r} no es la revista, PubMed Central, NASA, una agencia de salud pública "
            "ni la documentación de la API de la que llega el dato"
        )


def _validate_value(key: str, value: Any) -> None:
    numbers = value if isinstance(value, list) else [value]
    if len(numbers) not in (1, 2) or not all(
        isinstance(number, int | float) and not isinstance(number, bool) and number > 0
        for number in numbers
    ):
        raise InstrumentsError(f"{key}: `value_ms` es un número o un par mínimo-máximo")
    if len(numbers) == 2 and numbers[0] >= numbers[1]:
        raise InstrumentsError(f"{key}: el mínimo publicado no queda por debajo del máximo")


def _validate_pvt(pvt: dict[str, Any], statements: dict[str, dict[str, Any]]) -> None:
    variants = pvt["variants"]
    for key, parameter in pvt["parameters"].items():
        for item in parameter["published"]:
            where = f"pvt/{key}"
            if item.get("variant") not in variants:
                raise InstrumentsError(f"{where}: no dice de qué versión de la prueba es el valor")
            statement = statements.get(item.get("statement"))
            if statement is None:
                raise InstrumentsError(f"{where}: el valor no apunta a ninguna frase leída")
            if not _text(item, "literal") or item["literal"] not in statement["quote"]:
                raise InstrumentsError(
                    f"{where}: {item.get('literal')!r} no está escrito en la frase que lo sostiene"
                )
            _validate_value(where, item.get("value_ms"))
        for ref in parameter["see_also"]:
            if ref not in statements:
                raise InstrumentsError(f"pvt/{key}: {ref!r} no es una frase leída")
    for ref in pvt["context"]:
        if ref not in statements:
            raise InstrumentsError(f"pvt/context: {ref!r} no es una frase leída")
    if not all(isinstance(line, str) and line.strip() for line in pvt["not_found"]):
        raise InstrumentsError("pvt: una línea vacía en `not_found`")


def _validate_scale(key: str, scale: dict[str, Any], statements: dict[str, dict[str, Any]]) -> None:
    where = f"scales/{key}"
    if key in OWN_SCALES:
        raise InstrumentsError(
            f"{where}: es una escala propia de la misión: no tiene fuente y no admite rótulos"
        )
    code = CATALOG.get(key)
    if code is None or code.unit != _SCORE_UNIT:
        raise InstrumentsError(f"{where}: no es una escala de puntos del catálogo")
    if not _text(scale, "language") or not _text(scale, "labels_note"):
        raise InstrumentsError(f"{where}: falta el idioma de la fuente o la nota de los rótulos")
    if not scale["labels"]:
        raise InstrumentsError(f"{where}: una escala sin ningún rótulo leído no se declara aquí")
    seen: set[int] = set()
    for item in scale["labels"]:
        value = item.get("value")
        if isinstance(value, bool) or not isinstance(value, int):
            raise InstrumentsError(f"{where}: el punto de un rótulo es un entero")
        low, high = code.physical_min, code.physical_max
        if low is None or high is None or not low <= value <= high:
            raise InstrumentsError(f"{where}: el punto {value} queda fuera del rango del catálogo")
        if value in seen:
            raise InstrumentsError(f"{where}: el punto {value} lleva dos rótulos")
        seen.add(value)
        statement = statements.get(item.get("statement"))
        if statement is None:
            raise InstrumentsError(f"{where}: el rótulo de {value} no apunta a ninguna frase leída")
        # El rótulo y su número, juntos y tal cual, en la frase: «1 = Dislike Extremely» o, en
        # una lista, «8-Like Very Much» (`_written_with_its_point`).
        if not _text(item, "label") or not _written_with_its_point(
            value, item["label"], statement["quote"]
        ):
            raise InstrumentsError(
                f"{where}: «{value} = {item.get('label')}» no está escrito en su frase"
            )
    for ref in scale["see_also"]:
        if ref not in statements:
            raise InstrumentsError(f"{where}: {ref!r} no es una frase leída")
    if not all(isinstance(line, str) and line.strip() for line in scale["not_found"]):
        raise InstrumentsError(f"{where}: una línea vacía en `not_found`")
    if "criterion" in scale:
        _validate_criterion(where, scale["criterion"], statements, code)


def _written_with_its_point(value: int, label: str, quote: str) -> bool:
    """Si la frase escribe el rótulo pegado a su número, en una de las dos formas leídas.

    En línea, «1 = Dislike Extremely» (Douglas et al. 2025), o en lista, un punto por línea,
    «8-Like Very Much» (el informe de JSC de 1981). El rótulo es todo lo que hay entre el número
    y el fin del punto (un «;», un «)», el « / » que separa las líneas copiadas o el final de la
    frase): ni un número que solo termine en el del punto («18-…»), ni un trozo del rótulo
    («Neither Like»), ni una palabra con guion de la prosa («9-pt hedonic scale») cuentan.
    """
    pattern = rf"(?<!\d){value}(?: = |-){re.escape(label)}(?=;|\)| / |$)"
    return re.search(pattern, quote) is not None


# La primera cifra escrita en el trozo de frase que lleva el criterio: «6.0 or better» → 6.0.
_WRITTEN_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _validate_criterion(
    where: str,
    criterion: dict[str, Any],
    statements: dict[str, dict[str, Any]],
    code: VitalCode,
) -> None:
    """El criterio de aceptable de una escala: escrito en su frase, con la misma cifra.

    Lo que se marca con él es lo que queda POR DEBAJO, así que solo vale para una escala cuyo
    extremo vigilado sea el bajo: en una que vigila el alto, «por debajo» sería lo bueno.
    """
    where = f"{where}/criterion"
    statement = statements.get(str(criterion.get("statement")))
    if statement is None:
        raise InstrumentsError(f"{where}: el criterio no apunta a ninguna frase leída")
    literal = criterion.get("literal")
    if not isinstance(literal, str) or not literal.strip() or literal not in statement["quote"]:
        raise InstrumentsError(f"{where}: {literal!r} no está escrito en la frase que lo sostiene")
    value = criterion.get("value")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InstrumentsError(f"{where}: el criterio es una cifra")
    written = _WRITTEN_NUMBER.search(literal)
    if written is None or float(written.group()) != float(value):
        raise InstrumentsError(
            f"{where}: la frase no escribe {value!r}: un criterio que no está escrito no se adopta"
        )
    low, high = code.physical_min, code.physical_max
    if low is None or high is None or not low <= value <= high:
        raise InstrumentsError(f"{where}: {value!r} queda fuera del rango del catálogo")
    if code.concerning != "low":
        raise InstrumentsError(
            f"{where}: se marca lo que queda por debajo y el catálogo no vigila el extremo bajo"
        )


def _validate_measure(
    key: str, measure: dict[str, Any], statements: dict[str, dict[str, Any]], scales: set[str]
) -> None:
    """Lo leído de la medida de un indicador descriptivo: frases conocidas y categorías escritas."""
    where = f"measures/{key}"
    code = CATALOG.get(key)
    if code is None or key not in DESCRIPTIVE_ONLY:
        raise InstrumentsError(f"{where}: no es un indicador descriptivo del catálogo")
    if key in OWN_SCALES or key in scales:
        raise InstrumentsError(f"{where}: esa escala ya se declara en otro sitio")
    for field in ("instrument", "language", "scope"):
        if not _text(measure, field):
            raise InstrumentsError(f"{where}: falta `{field}`")
    ids = measure.get("statements")
    if not isinstance(ids, list) or not ids:
        raise InstrumentsError(f"{where}: una medida sin ninguna frase leída no se declara")
    for ref in ids:
        if ref not in statements:
            raise InstrumentsError(f"{where}: {ref!r} no es una frase leída")
    not_found = measure.get("not_found")
    if not isinstance(not_found, list) or not all(
        isinstance(line, str) and line.strip() for line in not_found
    ):
        raise InstrumentsError(f"{where}: `not_found` es una lista de líneas no vacías")
    categories = measure.get("categories", [])
    if categories and not _text(measure, "numbering"):
        raise InstrumentsError(
            f"{where}: unas categorías sin `numbering`: su número es de EMMA y hay que decirlo"
        )
    numbered: set[int] = set()
    for item in categories:
        value = item.get("value")
        if isinstance(value, bool) or not isinstance(value, int):
            raise InstrumentsError(f"{where}: el número de una categoría es un entero")
        if code.physical_min is None or code.physical_max is None or not (
            code.physical_min <= value <= code.physical_max
        ):
            raise InstrumentsError(f"{where}: la categoría {value} queda fuera del rango")
        if value in numbered:
            raise InstrumentsError(f"{where}: el número {value} lleva dos categorías")
        numbered.add(value)
        if item.get("statement") not in ids:
            raise InstrumentsError(f"{where}: la categoría {value} no apunta a una de sus frases")
        literal = item.get("literal")
        quote = statements[item["statement"]]["quote"]
        if not isinstance(literal, str) or not literal.strip() or literal not in quote:
            raise InstrumentsError(
                f"{where}: {literal!r} no está escrito en la frase que lo sostiene"
            )


def _validate_data_api_scope(raw: dict[str, Any], statements: dict[str, dict[str, Any]]) -> None:
    """Una frase de la documentación de una API solo la cita una medida de `DATA_API_MEASURES`.

    Son las del ciclo y, desde el 2026-11-15, el estado reproductivo y los síntomas vasomotores.

    Esa documentación dice qué categorías da la fuente de datos, y nada de fisiología ni del
    vuelo: si la citara la PVT, una escala o la medida de otro indicador, sostendría lo que no
    dice.
    """
    api = {
        sid for sid, item in statements.items()
        if urlsplit(registry.get(item["ref"]).url or "").hostname in DATA_API_HOSTS
    }
    for key, measure in raw.get("measures", {}).items():
        for sid in measure.get("statements", []):
            if sid not in api or key in DATA_API_MEASURES:
                continue
            raise InstrumentsError(
                f"measures/{key}: {sid!r} es documentación de una API y solo vale para las "
                "medidas del ciclo, del estado reproductivo y de los síntomas vasomotores"
            )
    pvt, scales = raw["pvt"], raw["scales"]
    elsewhere = set(pvt["context"]) | {
        ref for parameter in pvt["parameters"].values()
        for ref in [*(item["statement"] for item in parameter["published"]),
                    *parameter["see_also"]]
    } | {
        ref for scale in scales.values()
        for ref in [*(item["statement"] for item in scale["labels"]), *scale["see_also"]]
    }
    if leaked := sorted(api & elsewhere):
        raise InstrumentsError(
            f"{leaked}: documentación de una API citada fuera de las medidas del ciclo y del "
            "estado reproductivo"
        )


def validate(raw: dict[str, Any]) -> dict[str, Any]:
    """Rechaza lo que no se pueda sostener con la fuente delante."""
    try:
        dt.date.fromisoformat(raw["read_on"])
    except (KeyError, TypeError, ValueError):
        raise InstrumentsError(
            "falta `read_on`: una lectura sin fecha no se puede contrastar"
        ) from None
    sources = check_sources(raw, InstrumentsError, EXTENTS)  # el contrato común de las fuentes
    statements: dict[str, dict[str, Any]] = {}
    for item in raw["statements"]:
        _validate_statement(item, sources)
        if item["id"] in statements:
            raise InstrumentsError(f"{item['id']}: identificador repetido")
        statements[item["id"]] = item
    _validate_pvt(raw["pvt"], statements)
    for key, scale in raw["scales"].items():
        _validate_scale(key, scale, statements)
    measures = raw.get("measures", {})
    for key, measure in measures.items():
        _validate_measure(key, measure, statements, set(raw["scales"]))
    _validate_data_api_scope(raw, statements)
    if missing := sorted(DESCRIPTIVE_ONLY - set(measures)):
        raise InstrumentsError(
            f"indicadores descriptivos sin medida leída: {missing}. Solo entra lo que tiene fuente"
        )
    return raw


@cache
def read() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(READ_PATH.read_text(encoding="utf-8"))
    return validate(raw)


def cited_refs() -> frozenset[str]:
    """Las fichas del registro de las que se declara lectura."""
    return frozenset(read()["sources"])


def statement(statement_id: str) -> dict[str, Any]:
    """Una frase leída como se sirve: con su cita resuelta y cuánto se leyó del documento."""
    raw = read()
    item = next(entry for entry in raw["statements"] if entry["id"] == statement_id)
    ref = registry.get(item["ref"])
    source = raw["sources"][item["ref"]]
    return {
        "id": item["id"],
        "label": item["label"],
        "quote": item["quote"],
        "ref": ref.id,
        "source": ref.source,
        "title": ref.title,
        "url": ref.url,
        "where": item["where"],
        "read_on": item.get("read_on", raw["read_on"]),
        "extent": source["extent"],
        "extent_text": EXTENTS[source["extent"]],
    }


def _sources(statement_ids: set[str]) -> list[dict[str, Any]]:
    """Los documentos que sostienen esas frases, con su ficha y cuánto se leyó de cada uno."""
    raw = read()
    used = {item["ref"] for item in raw["statements"] if item["id"] in statement_ids}
    return [
        {
            "ref": ref_id,
            "title": registry.get(ref_id).title,
            "source": registry.get(ref_id).source,
            "url": registry.get(ref_id).url,
            "extent": source["extent"],
            "extent_text": EXTENTS[source["extent"]],
            "what": source["what"],
        }
        for ref_id, source in raw["sources"].items()
        if ref_id in used
    ]


def _pvt_statement_ids() -> set[str]:
    pvt = read()["pvt"]
    ids = set(pvt["context"])
    for parameter in pvt["parameters"].values():
        ids.update(item["statement"] for item in parameter["published"])
        ids.update(parameter["see_also"])
    return ids


def pvt_sources() -> list[dict[str, Any]]:
    return _sources(_pvt_statement_ids())


def pvt_tests() -> list[str]:
    """El nombre de cada prueba publicada de la que se leyó algo (no el de «las dos»)."""
    return [name for key, name in read()["pvt"]["variants"].items() if key != "both"]


def pvt_context() -> list[dict[str, Any]]:
    """Lo leído que no es de un parámetro: con quién se estudió, con qué equipo, qué queda."""
    return [statement(ref) for ref in read()["pvt"]["context"]]


def pvt_not_found() -> list[str]:
    return list(read()["pvt"]["not_found"])


def pvt_published(key: str) -> dict[str, Any]:
    """Lo que las fuentes dan para un parámetro de la prueba, versión a versión."""
    pvt = read()["pvt"]
    parameter = pvt["parameters"][key]
    return {
        "values": [
            {
                "variant": item["variant"],
                "variant_display": pvt["variants"][item["variant"]],
                "literal": item["literal"],
                "value_ms": item["value_ms"],
                "statement": statement(item["statement"]),
            }
            for item in parameter["published"]
        ],
        "see_also": [statement(ref) for ref in parameter["see_also"]],
    }


def scale_labels(key: str) -> dict[str, Any] | None:
    """Los rótulos leídos de una escala, en el idioma de su fuente; `None` si no hay ninguno."""
    scale = read()["scales"].get(key)
    if scale is None:
        return None
    return {
        "language": scale["language"],
        "sources": _sources(scale_statement_ids(key)),
        "labels": [
            {
                "value": item["value"],
                "label": item["label"],
                "statement": statement(item["statement"]),
            }
            for item in scale["labels"]
        ],
        "see_also": [statement(ref) for ref in scale["see_also"]],
        "labels_note": scale["labels_note"],
        "not_found": list(scale["not_found"]),
    }


def scale_criterion(key: str) -> dict[str, Any] | None:
    """El criterio de aceptable de una escala, con la frase que lo escribe; `None` si no hay.

    Solo lo que la fuente escribe: la cifra, el trozo de frase que la lleva y la frase entera
    con su cita. Qué se hace con él lo decide quien lo usa (`analysis/food_acceptability.py`).
    """
    scale = read()["scales"].get(key)
    if scale is None or "criterion" not in scale:
        return None
    criterion = scale["criterion"]
    return {
        "value": float(criterion["value"]),
        "literal": criterion["literal"],
        # El de la fuente de la escala: la frase va en su idioma, sin traducir.
        "language": scale["language"],
        "statement": statement(criterion["statement"]),
    }


def measure(key: str) -> dict[str, Any] | None:
    """Lo leído de la medida de un indicador descriptivo, con sus frases citadas; `None` si no es.

    Cada categoría va con su frase y con el trozo que la escribe (`literal`), en el idioma de la
    fuente; `numbering` dice que los números son de EMMA. Quien lo enseña no traduce ni completa.
    """
    item = read().get("measures", {}).get(key)
    if item is None:
        return None
    ids = list(item["statements"])
    return {
        "instrument": item["instrument"],
        "language": item["language"],
        "scope": item["scope"],
        "statements": [statement(ref) for ref in ids],
        "categories": [
            {
                "value": category["value"],
                "literal": category["literal"],
                "statement": category["statement"],
            }
            for category in item.get("categories", [])
        ],
        "numbering": item.get("numbering"),
        "sources": _sources(set(ids)),
        "not_found": list(item["not_found"]),
    }


def scale_statement_ids(key: str) -> set[str]:
    """Las frases que sostienen lo leído de una escala."""
    scale = read()["scales"][key]
    return {item["statement"] for item in scale["labels"]} | set(scale["see_also"])
