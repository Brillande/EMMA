"""Credibilidad de cada capa que predice o infiere, por los factores de NASA-STD-7009B.

La base de conocimiento del equipo (§2.3) lo dice tras repasar las limitaciones del IMM: «cualquier
capa predictiva nueva debe explicitar credibilidad e incertidumbre». EMMA ya rotulaba cada cifra
como MEDIDA, INFERIDA o PREDICHA, le ponía `model_version` y contrastaba sus proyecciones de deriva
(«¿Acertaron las proyecciones?»), y había leído la frase del IMM sobre ponderar sus resultados
«for its level of credibility» (`data/nasa_framework_read.json`). Pero la norma con que NASA mide
esa credibilidad, NASA-STD-7009, no estaba en el repositorio, y nada decía, capa por capa, qué
respaldo tiene cada cifra que no es una medida.

El 2026-10-23 se leyó la revisión vigente, NASA-STD-7009B (2024), en standards.nasa.gov. Separa
la credibilidad en dos evaluaciones con once factores: cinco de capacidad del modelo ([M&S 48]) y
seis de sus resultados ([M&S 31]). Lo leído y la ficha de cada capa viven en
`data/credibility_read.json`.

El peligro de rellenar una tabla así es dar a cada casilla un nivel que suene a evaluación. La
norma puntúa cada factor con tablas de nivel que EMMA no ha aplicado a ninguna capa, y pide no
combinar factores. Por eso este cargador es la defensa:

- los once factores están todos, con su grupo y su pregunta literal, y ninguno sobra;
- cada capa dice algo de cada factor, en palabras: sin campo de nivel ni de puntuación y sin un
  «nivel 3» o un «2/4» escondido en el texto;
- el texto sobre EMMA no reclama conformidad con la norma ni da una capa por validada
  (invariante 6), y lo que lo niega («ninguna implementación», «no validada») sí pasa;
- cada frase leída es de un documento del que se declara cuánto se leyó, con ficha en el registro
  y de un sitio oficial de NASA;
- cada capa nombra la función que rotula su cifra, su modelo (o por qué no lo lleva), dónde se
  sirve y qué pruebas la verifican. Que toda función que rotula una cifra INFERIDA o PREDICHA tenga
  ficha, y que las pruebas nombradas existan, lo comprueba `tests/test_credibility.py` leyendo el
  código: aquí no se importa el análisis.

La ficha decía también que el Apéndice D de la norma, el de la criticidad del uso ([M&S 6]), no se
había leído. Se leyó el 2026-10-26 (decimoctava ronda, U14): propone una matriz que cruza la
consecuencia de la decisión con la influencia que tienen en ella los resultados del modelo, y la
norma pone esa determinación en manos de la dirección del programa con la autoridad técnica
delegada (§4.1). EMMA no tiene esa autoridad. Lo que sí puede decir, capa por capa, es lo que hay
en cada eje: qué decisión informa la cifra y qué otra información hay al tomarla. Y la defensa es la
misma: sin casilla, sin color de la matriz y sin el nombre de ninguna de sus categorías
(«Negligible», «Catastrophic», «Controlling» o su traducción) en lo que escribe EMMA.

Es un inventario: no entra en el análisis, en el riesgo ni en ninguna alerta (invariante 5), y no
sale a la red; la lectura se hizo una vez, en Tierra.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import logging
import re
import unicodedata
from functools import cache
from pathlib import Path
from typing import Any

from app.core import i18n
from app.evidence import registry

# Lo que EMMA no puede decir de sí mismo por citar una fuente de NASA (invariante 6): una sola
# lista para los dos paneles que se enseñan juntos.
from app.evidence.nasa_framework import CLAIM_WORDS, EXTENTS
from app.evidence.read_contract import check_sources, claims

READ_PATH = Path(__file__).resolve().parents[1] / "data" / "credibility_read.json"

_log = logging.getLogger(__name__)

# La norma y su guía están en standards.nasa.gov; NTRS por si se añade algo de allí. Más estrecha
# a propósito que la de `nasa_framework`: aquí solo entran normas y documentos técnicos.
OFFICIAL_HOSTS = frozenset({"standards.nasa.gov", "ntrs.nasa.gov"})

# Los dos grupos y sus factores, en el orden de [M&S 48] y [M&S 31]. Fijos: la norma los da como
# «the minimum set», y una ficha sin uno de ellos callaría justo el que no conviene.
GROUPS: dict[str, tuple[str, ...]] = {
    "capability": (
        "data-pedigree", "verification", "validation", "development-review",
        "development-management",
    ),
    "results": (
        "use-assessment", "input-pedigree", "uncertainty", "robustness", "use-review",
        "use-management",
    ),
}
FACTOR_IDS = tuple(factor for factors in GROUPS.values() for factor in factors)

# Lo que una ficha rotula: solo lo que no es una medida.
OBSERVATION_TYPES = {"inferred": "INFERIDO", "predicted": "PREDICHO"}
# Su inglés y el de cuánto se leyó (`EXTENTS`), al lado y no en el registro común de `i18n.en`:
# son rótulos cortos que otros módulos también enseñan, cada uno con el suyo.
_OBSERVATION_TYPES_EN = {"inferred": "INFERRED", "predicted": "PREDICTED"}
_EXTENT_TEXT_EN = {
    EXTENTS["full"]: "read in full",
    EXTENTS["partial"]: "read in part",
    EXTENTS["record"]: "read: NTRS abstract; not the full document",
}

# Un nivel o una puntuación no se escriben: ni como campo ni dentro del texto. El nombre de un
# campo se compara en minúsculas y sin tildes («Level», «puntuación»); en el texto, un nivel con o
# sin dos puntos o guion, en singular o en plural, en cifra (con letra detrás o con «de» delante),
# en romanos, en palabra o en ordinal («nivel 3», «Nivel: 3», «nivel-3», «Level 2b», «nivel de 3»,
# «nivel III», «niveles 2 y 3», «nivel tres», «tercer nivel»), una nota sobre cuatro («2/4», «3 de
# 4») y el rótulo más alto de la propia norma («gold-standard», §E.2), que en una casilla sería un
# nivel que nadie evaluó. Lo que no es un nivel pasa: «3 de 4 pruebas» cuenta pruebas, y en «dos
# niveles: uno de ellos» el número no es el de un nivel.
SCORE_FIELDS = frozenset({
    "level", "levels", "score", "scores", "rating", "nivel", "niveles", "puntuacion",
    "puntuaciones", "nota",
})
_LEVEL_WORD = r"\b(?:nivel(?:es)?|levels?|grados?|tiers?|scores?|puntuaci(?:[oó]n|ones))"
_SCORE_TEXT = (
    re.compile(
        # Una cifra con decimales o con unidad («nivel de 0,3 mSv») es una magnitud, no un nivel.
        _LEVEL_WORD + r"(?:\s*[:=-]\s*|\s*(?:(?:de|of)\s+)?)[0-4][a-z]?\b"
        r"(?![.,]\d)(?!\s*(?:m?sv|m?gy|%))",
        re.IGNORECASE,
    ),
    re.compile(
        _LEVEL_WORD + r"\s*[:=-]?\s*"
        r"(?:i{1,3}|iv|cero|uno|dos|tres|cuatro|zero|one|two|three|four)\b"
        r"(?!\s+(?:de|of)\s+(?:ellos|ellas|estos|estas|esos|esas|them|these|those)\b)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:primer|segundo|tercer|cuarto|first|second|third|fourth)[\s-]+"
        r"(?:nivel|grado|level|tier)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b[0-4]\s*(?:/|de|sobre|out of)\s*4\b(?![.,]\d)(?!\s*[^\W\d_])"),
    re.compile(r"\bgold[- ]standard\b", re.IGNORECASE),
)

# Lo que no se puede decir de una capa sin haberlo hecho: además de reclamar conformidad
# (`CLAIM_WORDS`), darla por validada o acreditada. Y lo que niega no reclama: «ninguna
# implementación de referencia» o «no está validada» son justo lo que una ficha honrada dice; la
# negación cuenta si va en la misma frase y a tres palabras o menos (`read_contract.claims`, la
# misma regla que en el panel de lo leído de NASA).
VALIDATION_WORDS = ("validad", "validated", "acreditad", "accredited")

# Los dos ejes de la matriz de criticidad del Apéndice D, en su orden (figura 1): la consecuencia de
# la decisión y la influencia de los resultados del modelo en ella. Cada ficha dice algo de los dos.
AXES = ("decision", "influence")

# Lo que sería aplicar la matriz sin autoridad para ello: el nombre de una categoría de la tabla 3
# (consecuencia) o de la 4 (influencia), en inglés o traducido; un número romano de la tabla 3 con
# sus dos puntos («III:»); una posición de la matriz con su número («nivel 5», «fila 4»,
# «categoría III»: los niveles del Apéndice D van de 1 a 5, §D.2); el color de una casilla de la
# figura 1 junto a la casilla, o su letra entre paréntesis («(R)»). Se busca en todo lo que
# escribe EMMA en estas fichas (en forma NFC: una tilde suelta no lo esquiva), y aunque vaya
# negado: «no es catastrófica» también clasifica. Las palabras van enteras: «criticidad» no es
# «crítica», y «significación» no es «significativa». Dos traducciones corrientes NO se miran, a
# sabiendas: «menor» y «dominante» (ni «red», sin red): se usan en castellano sin hablar de la
# matriz, y vetarlas rechazaría fichas honradas. El color, solo junto a la casilla.
_CRITICALITY_CATEGORY = (
    re.compile(
        r"\b(?:negligible|minor|moderate|significant|catastrophic|controlling|critical|"
        r"despreciables?|insignificantes?|inapreciables?|moderad[oa]s?|significativ[oa]s?|"
        r"catastr[oó]fic[oa]s?|determinantes?|controlantes?|cr[ií]tic[oa]s?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:casillas?|celdas?|cuadros?|boxe?s?|cells?)\s+(?:\w+\s+){0,4}"
        r"(?:roj[oa]s?|amarill[oa]s?|verdes?|red|yellow|green)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\((?:R|Y|G)\)", re.IGNORECASE),
    re.compile(r"\b(?:I{1,3}|IV|V)\s*:"),
    re.compile(
        r"\b(?:nivel(?:es)?|levels?|categor[ií]as?|categor(?:y|ies)|filas?|rows?|columnas?|"
        r"columns?)\s*(?:(?:de|of)\s+)?[:=-]?\s*(?:[1-5]\b(?![.,]\d)|(?:I{1,3}|IV|V)\b)",
        re.IGNORECASE,
    ),
)

# Una fecha AAAA-MM-DD y nada más: `fromisoformat` acepta también «20261026» o «2026-W43-1», que
# la consola no sabe pintar (la misma guarda que `radiation_read._date`).
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def _day(value: Any) -> dt.date:
    """Un día escrito AAAA-MM-DD; si no, `ValueError` (o `TypeError` si no es texto)."""
    if not isinstance(value, str):
        raise TypeError(value)
    if not _DAY.fullmatch(value):
        raise ValueError(value)
    return dt.date.fromisoformat(value)

_SITE = re.compile(r"[a-z_]+(/[a-z_]+)*\.py:[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*")
_TEST = re.compile(r"tests/test_[a-z0-9_]+\.py::test_[a-z0-9_]+")
_ID = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")

NOTE = (
    "Lo que hay en cada factor de credibilidad de NASA-STD-7009B para cada cifra INFERIDA o "
    "PREDICHA, dicho en palabras. Sin nivel ni puntuación: EMMA no ha evaluado ninguna capa con "
    "las tablas de la norma. Y lo que hay en los dos ejes de criticidad del Apéndice D, sin "
    "aplicar su matriz. Inventario: no interviene en el estado de la tripulación."
)
i18n.en(
    NOTE,
    "What there is under each NASA-STD-7009B credibility factor for each INFERRED or PREDICTED "
    "figure, said in words. With no level or score: EMMA has not assessed any layer with the "
    "tables of the standard. And what there is on the two criticality axes of Appendix D, "
    "without applying its matrix. Inventory: it plays no part in the state of the crew.",
)


class CredibilityError(ValueError):
    """Lo leído o una ficha no cumplen su contrato: no se sirve."""


def _text(item: dict[str, Any], field: str) -> bool:
    value = item.get(field)
    return isinstance(value, str) and bool(value.strip())


def _plain(name: str) -> str:
    """Un nombre de campo en minúsculas y sin tildes, para compararlo con `SCORE_FIELDS`."""
    decomposed = unicodedata.normalize("NFKD", name.strip().lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _no_score(where: str, text: str) -> None:
    for pattern in _SCORE_TEXT:
        if found := pattern.search(text):
            raise CredibilityError(
                f"{where}: «{found.group(0)}» es un nivel: EMMA no ha evaluado niveles, y una "
                "casilla dice lo que hay, no cuánto vale"
            )


def _no_category(where: str, text: str) -> None:
    text = unicodedata.normalize("NFC", text)
    for pattern in _CRITICALITY_CATEGORY:
        if found := pattern.search(text):
            raise CredibilityError(
                f"{where}: «{found.group(0)}» es una categoría de la matriz de criticidad: EMMA no "
                "la ha aplicado, y una ficha dice lo que hay en cada eje, no dónde cae"
            )


def _emma_writes(where: str, text: str) -> None:
    """Lo que escribe EMMA sobre la criticidad: ni nivel, ni reclamo, ni categoría de la matriz."""
    _no_score(where, text)
    _no_claim(where, text)
    _no_category(where, text)


def _validate_criticality(raw: dict[str, Any]) -> None:
    """Lo leído del Apéndice D: fechado, con sus frases y sus dos ejes, y sin aplicar la matriz."""
    block = raw["criticality"]
    if not isinstance(block, dict):
        raise CredibilityError("`criticality`: se esperaba lo leído del Apéndice D")
    try:
        own = _day(block["read_on"])
    except (KeyError, TypeError, ValueError):
        raise CredibilityError(
            "`criticality`: falta `read_on`: una lectura sin fecha no se puede contrastar"
        ) from None
    if own < dt.date.fromisoformat(raw["read_on"]):
        raise CredibilityError(
            "`criticality`: `read_on` anterior a la primera lectura de la norma: errata de fecha"
        )
    for field in ("title", "about", "not_applied"):
        if not _text(block, field):
            raise CredibilityError(f"`criticality`: falta `{field}`")
        _emma_writes(f"criticality/{field}", block[field])
    _validate_statements(raw, block)
    for item in block["statements"]:
        # El apéndice se leyó el día que dice el bloque: su fuente tiene que tener esa lectura
        # como la última, o el panel fecharía la fuente un día y el apéndice otro.
        source_day = raw["sources"][item["ref"]].get("read_on", raw["read_on"])
        if source_day != block["read_on"]:
            raise CredibilityError(
                f"criticality/frase {item['id']}: `read_on` {block['read_on']} y la última "
                f"lectura de {item['ref']} ({source_day}) no casan"
            )
        for field in ("label", "where"):
            _emma_writes(f"criticality/frase {item['id']}/{field}", item[field])
    # La lista tal cual: un eje repetido o callado no se funde con el otro.
    if [axis.get("id") for axis in block["axes"]] != list(AXES):
        raise CredibilityError(
            "`criticality`: los ejes de la matriz son la consecuencia y la influencia, una vez "
            "cada uno y en ese orden"
        )
    for axis in block["axes"]:
        for field in ("name", "name_es", "quote", "where"):
            if not _text(axis, field):
                raise CredibilityError(f"criticality/eje {axis['id']}: falta `{field}`")
        for field in ("name", "name_es", "where"):
            _emma_writes(f"criticality/eje {axis['id']}/{field}", axis[field])


def _validate_layer_criticality(key: str, layer: dict[str, Any]) -> None:
    states = layer.get("criticality")
    if not isinstance(states, dict) or list(states) != list(AXES):
        raise CredibilityError(
            f"{key}: la ficha dice algo de los dos ejes de criticidad, en su orden; lo que no hay "
            "se dice, no se calla"
        )
    for axis, text in states.items():
        spot = f"{key}/criticidad/{axis}"
        if not (isinstance(text, str) and text.strip()):
            raise CredibilityError(f"{spot}: vacío: lo que no hay se dice, no se calla")
        _emma_writes(spot, text)


def _no_claim(where: str, text: str) -> None:
    # Lo negado no reclama: la regla es la del contrato común (`read_contract.claims`).
    if claimed := claims(text, (*CLAIM_WORDS, *VALIDATION_WORDS)):
        raise CredibilityError(
            f"{where}: el texto sobre EMMA reclama conformidad o validación ({claimed})"
        )


def _validate_sources(raw: dict[str, Any]) -> None:
    first = dt.date.fromisoformat(raw["read_on"])

    def own_read_on(value: Any, ref_id: str) -> None:
        """La última lectura de una fuente, si no es la primera: una fecha, y no anterior."""
        try:
            own = _day(value)
        except (TypeError, ValueError):
            raise CredibilityError(f"{ref_id}: `read_on` no es una fecha") from None
        if own < first:
            raise CredibilityError(
                f"{ref_id}: `read_on` anterior a la primera lectura ({raw['read_on']})"
            )
        # Y la ficha del registro anota esa lectura con su día: si no, el panel diría «Leído el»
        # un día del que no queda rastro.
        if value not in (registry.get(ref_id).notes or ""):
            raise CredibilityError(
                f"{ref_id}: la ficha del registro no anota la lectura del {value}"
            )

    # El contrato común de las fuentes, con la lista de sitios de aquí, más estrecha, y la fecha
    # de la última lectura de una fuente que se leyó más de un día (la norma: el Apéndice D).
    check_sources(
        raw, CredibilityError, EXTENTS, official_hosts=OFFICIAL_HOSTS, own_read_on=own_read_on
    )


def _validate_statements(raw: dict[str, Any], block: dict[str, Any] | None = None) -> None:
    """Las frases de la norma o, con `block`, las del Apéndice D: con sitio y fuente leída, y sin
    repetir el identificador de ninguna otra (las de arriba incluidas)."""
    items = raw["statements"] if block is None else block["statements"]
    if not items:
        raise CredibilityError("sin ninguna frase leída de la norma no hay de qué hablar")
    seen: set[str] = set() if block is None else {item["id"] for item in raw["statements"]}
    prefix = "frase" if block is None else "criticality/frase"
    for item in items:
        key = f"{prefix} {item.get('id', '?')}"
        for field in ("id", "label", "quote", "ref", "where"):
            if not _text(item, field):
                raise CredibilityError(
                    f"{key}: falta `{field}`: sin frase, sitio y fuente no se sirve"
                )
        if item["ref"] not in raw["sources"]:
            raise CredibilityError(f"{key}: de {item['ref']!r} no se declara cuánto se leyó")
        if item["id"] in seen:
            raise CredibilityError(f"{key}: identificador repetido")
        seen.add(item["id"])


def _validate_factors(raw: dict[str, Any]) -> None:
    # La lista tal cual, no un diccionario: un grupo repetido no se funde con el otro.
    ids = [group.get("id") for group in raw["groups"]]
    if ids != list(GROUPS):
        raise CredibilityError(
            f"grupos {ids}: la norma separa capacidad y resultados, una vez cada uno y en ese orden"
        )
    for group in raw["groups"]:
        for field in ("name", "name_es", "requirement", "quote", "where"):
            if not _text(group, field):
                raise CredibilityError(f"grupo {group['id']}: falta `{field}`")
    found = [(item.get("group"), item.get("id")) for item in raw["factors"]]
    expected = [(group, factor) for group, factors in GROUPS.items() for factor in factors]
    if found != expected:
        raise CredibilityError(
            "los factores no son los once de [M&S 48] y [M&S 31], en su grupo y en su orden: "
            "ninguno se omite ni se añade"
        )
    for item in raw["factors"]:
        for field in ("name", "name_es", "question", "where"):
            if not _text(item, field):
                raise CredibilityError(f"factor {item['id']}: falta `{field}`")


def _validate_layer(layer: dict[str, Any]) -> None:
    key = f"capa {layer.get('id', '?')}"
    if not isinstance(layer.get("id"), str) or not _ID.fullmatch(layer["id"]):
        raise CredibilityError(f"{key}: identificador ausente o mal formado")
    if not _text(layer, "display"):
        raise CredibilityError(f"{key}: falta `display`")
    factors = layer.get("factors")
    # Un campo de nivel dentro de `factors` ya cae abajo: sus claves son las once, ni una más.
    if scored := sorted(name for name in layer if _plain(str(name)) in SCORE_FIELDS):
        raise CredibilityError(f"{key}: campo de nivel o de puntuación ({scored})")
    if layer.get("observation_type") not in OBSERVATION_TYPES:
        raise CredibilityError(
            f"{key}: tipo {layer.get('observation_type')!r}: una ficha es de una cifra INFERIDA "
            "o PREDICHA"
        )
    # Las dos claves siempre, aunque una sea null: lo que se sirve las lee las dos.
    if not {"model_version", "model_note"} <= layer.keys():
        raise CredibilityError(f"{key}: `model_version` y `model_note` van siempre, null si no hay")
    model, note = layer["model_version"], layer["model_note"]
    if model is None and not _text(layer, "model_note"):
        raise CredibilityError(f"{key}: sin `model_version` hay que decir por qué (`model_note`)")
    if model is not None and (not _text(layer, "model_version") or note is not None):
        raise CredibilityError(
            f"{key}: con `model_version` no hace falta `model_note`, y el modelo no va vacío"
        )
    for field, pattern in (("sites", _SITE), ("tests", _TEST)):
        values = layer.get(field)
        if (
            not isinstance(values, list) or not values
            or not all(isinstance(value, str) and pattern.fullmatch(value) for value in values)
        ):
            raise CredibilityError(f"{key}: `{field}` vacío o mal escrito")
    served = layer.get("served_in")
    if not isinstance(served, list) or not served or not all(
        isinstance(value, str) and value.startswith("/api/") for value in served
    ):
        raise CredibilityError(f"{key}: `served_in` tiene que nombrar la ruta que la sirve")
    # Tras la ruta va texto libre, y se enseña: tampoco puntúa ni reclama.
    for value in served:
        _emma_writes(f"{key}/served_in", value)
    if not isinstance(factors, dict) or list(factors) != list(FACTOR_IDS):
        raise CredibilityError(
            f"{key}: la ficha dice algo de los once factores, en su orden; lo que no hay se dice "
            "(«ninguna»), no se calla"
        )
    for factor, text in factors.items():
        where = f"{key}/{factor}"
        if not isinstance(text, str) or not text.strip():
            raise CredibilityError(f"{where}: vacío: lo que no hay se dice, no se calla")
        _emma_writes(where, text)
    for field in ("display", "model_note", "model_version"):
        if _text(layer, field):
            _emma_writes(f"{key}/{field}", layer[field])
    _validate_layer_criticality(key, layer)


def _emma_texts(raw: dict[str, Any]) -> list[tuple[str, str]]:
    """Todo lo que redacta EMMA fuera de las fichas de capa, con dónde está.

    Lo que no entra son las frases de la norma (`quote`, `question`) y los nombres en inglés de
    grupos y factores: son de la fuente, en su idioma, y no hablan de EMMA. El sitio de cada frase
    (`where`) y el requisito de cada grupo sí: los escribe EMMA y se enseñan junto a la cita.
    """
    texts = [(field, raw[field]) for field in ("title", "about", "emma", "not_assessed")]
    texts += [(f"fuente {ref}", source["what"]) for ref, source in raw["sources"].items()]
    for item in raw["statements"]:
        texts += [(f"frase {item['id']}", item[field]) for field in ("label", "where")]
    for item in raw["groups"]:
        texts += [
            (f"grupo {item['id']}", item[field]) for field in ("name_es", "requirement", "where")
        ]
    for item in raw["factors"]:
        texts += [(f"factor {item['id']}", item[field]) for field in ("name_es", "where")]
    texts += [(field, line) for field in ("out_of_scope", "not_read") for line in raw[field]]
    return texts


def validate(raw: dict[str, Any]) -> dict[str, Any]:
    """Rechaza una ficha que puntúe, calle un factor o afirme de más sobre EMMA.

    Un fichero mal formado (una clave que falta, una ficha que no está en el registro) también
    sale como `CredibilityError`: se dice qué falla, no un error de otra clase.
    """
    try:
        return _validate(raw)
    except CredibilityError:
        raise
    # `ValueError` incluido: `urlsplit` lo lanza con una dirección rota («https://[host»).
    except (KeyError, TypeError, AttributeError, ValueError, registry.RegistryError) as error:
        raise CredibilityError(f"fichero mal formado: {error!r}") from error


def _validate(raw: dict[str, Any]) -> dict[str, Any]:
    try:
        _day(raw["read_on"])
    except (KeyError, TypeError, ValueError):
        raise CredibilityError(
            "falta `read_on`: una lectura sin fecha no se puede contrastar"
        ) from None
    for field in ("title", "about", "not_assessed", "emma"):
        if not _text(raw, field):
            raise CredibilityError(f"falta `{field}`")
    _validate_sources(raw)
    _validate_statements(raw)
    _validate_factors(raw)
    for field in ("out_of_scope", "not_read"):
        if not isinstance(raw.get(field), list) or not all(
            isinstance(line, str) and line.strip() for line in raw[field]
        ):
            raise CredibilityError(f"`{field}`: una línea vacía o ausente")
    for where, text in _emma_texts(raw):
        _emma_writes(where, text)
    _validate_criticality(raw)
    if not raw["layers"]:
        raise CredibilityError("sin ninguna ficha de capa no hay nada que servir")
    seen: set[str] = set()
    for layer in raw["layers"]:
        _validate_layer(layer)
        if layer["id"] in seen:
            raise CredibilityError(f"capa {layer['id']}: identificador repetido")
        seen.add(layer["id"])
    return raw


@cache
def read() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(READ_PATH.read_text(encoding="utf-8"))
    return validate(raw)


def cited_refs() -> frozenset[str]:
    """Las fichas del registro de las que se declara lectura."""
    return frozenset(read()["sources"])


def marked_sites() -> dict[tuple[str, str], list[str]]:
    """Cada función que rotula una cifra, con su tipo, y las capas que la cubren."""
    sites: dict[tuple[str, str], list[str]] = {}
    for layer in read()["layers"]:
        for site in layer["sites"]:
            sites.setdefault((site, layer["observation_type"]), []).append(layer["id"])
    return sites


def payload() -> dict[str, Any]:
    """Lo leído y las fichas como se sirven. Una copia: quien la reciba puede tocarla."""
    return copy.deepcopy(_payload())


def served() -> dict[str, Any] | None:
    """Lo que sirve `/api/framework`: las fichas, o `None` si el fichero no pasa su contrato.

    Va en la misma respuesta que EIMO, el IMM y lo leído de NASA: una ficha rota no se sirve, pero
    tampoco se lleva por delante el resto del panel del marco. Se anota, y la interfaz lo enseña
    como no disponible.
    """
    try:
        return payload()
    except CredibilityError:
        _log.exception("fichas de credibilidad no servidas")
        return None


def _extent_text(text: str) -> str:
    """Cuánto se leyó de una fuente, en el idioma de la petición.

    Se busca por el texto castellano de `EXTENTS`, que es de otro módulo: uno que se añada
    allí sin su inglés aquí sale en castellano, no tumba la respuesta.
    """
    return i18n.tr(text, _EXTENT_TEXT_EN.get(text, text))


@i18n.lang_cache
def _payload() -> dict[str, Any]:
    # Los datos no cambian en vida del proceso (como `read()`): se resuelve una vez por idioma.
    # El inglés de lo que redacta EMMA es el hermano `credibility_read.en.json`, que se aplica a
    # lo leído, ya validado en castellano, antes de montar la respuesta: así no toca lo que viene
    # del registro. Las frases de la norma (`quote`, `question`) y los nombres oficiales (`name`)
    # no están en él y salen como se leyeron.
    raw = i18n.localized(read(), READ_PATH)
    sources = raw["sources"]

    def source(ref_id: str) -> dict[str, Any]:
        ref = registry.get(ref_id)
        return {
            "ref": ref.id,
            "title": ref.title,
            "source": ref.source,
            "url": ref.url,
            "date": ref.date,
            # El día de la última lectura: el suyo si lo declara, si no el de la primera.
            "read_on": sources[ref_id].get("read_on", raw["read_on"]),
            "extent": sources[ref_id]["extent"],
            "extent_text": _extent_text(EXTENTS[sources[ref_id]["extent"]]),
            "what": sources[ref_id]["what"],
        }

    resolved = [source(ref_id) for ref_id in sources]
    titles = {item["ref"]: item["title"] for item in resolved}
    names = {item["id"]: item["name_es"] for item in raw["factors"]}
    block = raw["criticality"]
    axis_names = {axis["id"]: axis["name_es"] for axis in block["axes"]}
    return {
        "note": i18n.loc(NOTE),
        "title": raw["title"],
        "about": raw["about"],
        "read_on": raw["read_on"],
        "sources": resolved,
        "statements": [
            {
                "id": item["id"],
                "label": item["label"],
                "quote": item["quote"],
                "where": item["where"],
                "source": titles[item["ref"]],
                "ref": item["ref"],
            }
            for item in raw["statements"]
        ],
        "groups": [
            {
                **{field: group[field] for field in (
                    "id", "name", "name_es", "requirement", "quote", "where"
                )},
                "factors": [
                    {field: item[field] for field in ("id", "name", "name_es", "question", "where")}
                    for item in raw["factors"]
                    if item["group"] == group["id"]
                ],
            }
            for group in raw["groups"]
        ],
        "not_assessed": raw["not_assessed"],
        "emma": raw["emma"],
        "layers": [
            {
                "id": layer["id"],
                "display": layer["display"],
                "observation_type": layer["observation_type"],
                "observation_type_text": i18n.tr(
                    OBSERVATION_TYPES[layer["observation_type"]],
                    _OBSERVATION_TYPES_EN[layer["observation_type"]],
                ),
                "model_version": layer["model_version"],
                "model_note": layer["model_note"],
                "sites": list(layer["sites"]),
                "served_in": list(layer["served_in"]),
                "tests": list(layer["tests"]),
                # Por grupo y en el orden de la norma, con el nombre del factor: la interfaz no
                # tiene que casar claves.
                "factors": [
                    {
                        "group": group,
                        "id": factor,
                        "name_es": names[factor],
                        "state": layer["factors"][factor],
                    }
                    for group, factors in GROUPS.items()
                    for factor in factors
                ],
                # Los dos ejes de criticidad, en su orden y con su nombre, como los factores.
                "criticality": [
                    {"axis": axis, "name_es": axis_names[axis], "state": layer["criticality"][axis]}
                    for axis in AXES
                ],
            }
            for layer in raw["layers"]
        ],
        "criticality": {
            "read_on": block["read_on"],
            "title": block["title"],
            "about": block["about"],
            "not_applied": block["not_applied"],
            "statements": [
                {
                    "id": item["id"],
                    "label": item["label"],
                    "quote": item["quote"],
                    "where": item["where"],
                    "source": titles[item["ref"]],
                    "ref": item["ref"],
                }
                for item in block["statements"]
            ],
            "axes": [
                {field: axis[field] for field in ("id", "name", "name_es", "quote", "where")}
                for axis in block["axes"]
            ],
        },
        "out_of_scope": list(raw["out_of_scope"]),
        "not_read": list(raw["not_read"]),
    }
