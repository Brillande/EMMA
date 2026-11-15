"""El sentido en que cambió cada indicador en vuelo en otras tripulaciones, frase a frase.

POR QUÉ EXISTE
--------------
La conversación de ideación del equipo (`docs/contexto/conversacion-ideacion-v1.md`, hacia la
línea 34) lo pone en el centro: «En microgravedad algunas variables van a cambiar
necesariamente», y por eso la referencia no puede ser solo la de Tierra. El perfil de línea base
(`analysis/baseline_profile.py`) dice contra qué se compara cada indicador; no decía si lo que se
ve se parece a lo que se observó en otros vuelos. Y el sitio donde EMMA lo tenía escrito,
`ingest/simulator.py` (`LITERATURE`), da el sentido de cada deriva del MODELO con fuentes en
prosa, casi ninguna con ficha: al leerlas una a una salió que la deriva de la frecuencia cardiaca
en reposo, «sentido documentado», sube durante el vuelo en el simulador cuando los estudios que
dan su cifra la ven sin cambio en vuelo y la subida DESPUÉS (Hughson 2012, Xu 2013, Fraser
2012). Es el aviso de `CLAUDE.md` cumplido otra vez: el siguiente parámetro sin verificar
también estaba mal. Por eso esto no copia el simulador: cada sentido tiene su propia frase leída.

QUÉ HACE, Y QUÉ NO
------------------
Lo leído el 2026-10-22 vive en `data/flight_direction_read.json` y este cargador es su defensa:
una frase sin sección, sin ficha oficial o de una fuente que no es de personas no se sirve; el
sentido tiene que estar escrito en el literal de la frase (y el literal, en la frase), la frase
tiene que hablar del vuelo, y un indicador con sentido necesita al menos una frase con ese mismo
sentido; «discutido», dos frases que no coinciden. Sin frase leída, «sin fuente», y si se buscó
y no se encontró, dónde. Lo leído el 2026-10-23 (decimosexta ronda: respiración, saturación,
sueño frente a antes del vuelo, PVT y analíticas) lleva su fecha en su fuente, y lo leído junto a
un indicador con sentido que no lo da se dice aparte («leído también»), con su ficha. Lo leído
el 2026-10-26 (decimoctava ronda: hígado, riñón, electrolitos e inflamación) es casi todo
«buscado y no encontrado»: la bioquímica de a bordo publicada es sobre todo de antes y de después
del vuelo, y la que se midió en vuelo da a menudo una tabla, una tendencia sin estadística o una
frase que no dice cuándo se tomó la muestra. Lo leído el 2026-10-31 (decimonovena ronda:
hematología y bioquímica) deja dos indicadores «discutidos» por la duración del vuelo o el
momento de la toma (leucocitos, cortisol salival) y el porcentaje de linfocitos al alza en una
sola frase; y una regla: un analito que el estudio suplementa (la vitamina D, el calcio) no se
lee como sentido del vuelo, se dice en lo buscado.
Lo leído ese mismo día sobre función (lapsos
de la PVT, desfase circadiano, caída ortostática y yugular derecha) sigue «buscado y no
encontrado», pero ya con lo que hay en vuelo delante: un retraso de fase en horas, que es un
signo y no una subida ni una bajada mientras EMMA no declare el de su desfase; una prueba que en
ingravidez no existe (ponerse en pie) y su sustituto en vuelo (soltar manguitos de muslo); una
serie de una sola persona frente a tumbado; y frases de la yugular que no dicen el lado.

Se enseña solo junto a la línea base (decisión del usuario, 2026-10-22), como «lo que se observó
en otros vuelos, no lo esperado en esta persona». No entra en la base, el riesgo, los niveles ni
las alertas (invariante 5), y ninguna frase dice que algo sea normal o esperable: una lectura que
vaya en el sentido observado no queda explicada por ello (invariante 7). Tampoco sale a la red: la
lectura se hizo una vez, en Tierra.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Iterable
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.core import display, i18n
from app.evidence import registry
from app.evidence.instruments_read import EXTENTS, OFFICIAL_HOSTS
from app.evidence.read_contract import check_sources
from app.ingest.codes import CATALOG, get

READ_PATH = Path(__file__).resolve().parents[1] / "data" / "flight_direction_read.json"

# Lo que una frase puede decir que se observó en vuelo, y cómo se lee.
OBSERVED: dict[str, str] = {"rises": "sube", "falls": "baja", "unchanged": "sin cambio"}
CONTESTED = "contested"
NO_SOURCE = "no_source"
DIRECTION_DISPLAY: dict[str, str] = {
    **OBSERVED, CONTESTED: "discutido", NO_SOURCE: "sin fuente",
}
# Su inglés y el de cuánto se leyó (`EXTENTS`), al lado y no en el registro común de `i18n.en`:
# son palabras cortas («sube», «sin fuente») que otros módulos también enseñan, cada uno con el
# suyo. Solo es lo que se enseña: lo que valida el fichero sigue leyendo las de arriba.
_DIRECTION_EN: dict[str, str] = {
    "rises": "rises", "falls": "falls", "unchanged": "no change",
    CONTESTED: "contested", NO_SOURCE: "no source",
}
_EXTENT_TEXT_EN: dict[str, str] = {
    EXTENTS["full"]: "read in full", EXTENTS["partial"]: "read in part",
}

# Las palabras con que la frase, en inglés, dice cada sentido. El literal tiene que llevar una
# de su sentido y ninguna de otro: «HR was unchanged inflight and elevated postflight» no es una
# frase de subida, y su literal tampoco puede serlo.
_DIRECTION_WORDS: dict[str, re.Pattern[str]] = {
    "rises": re.compile(r"\b(increase[ds]?|elevated|higher|rises?)\b", re.IGNORECASE),
    "falls": re.compile(r"\b(reduced|reductions?|decrease[ds]?|diminished|loss|lower|less)\b",
                        re.IGNORECASE),
    # «No significant differences were detected for total protein concentration during flight»
    # (Zwart 2022) es la frase de «sin cambio» de las analíticas de la ISS: entra con su negación,
    # como «no changes», y se quita antes de buscar otra («no statistically significant
    # differences», también; y «not significantly altered», la del cortisol salival de Buchheim
    # 2019, desde la decimonovena ronda). Una diferencia ENTRE grupos no es un cambio en el
    # tiempo: ver `_GROUP_COMPARISON`.
    "unchanged": re.compile(
        r"\b(unchanged|unaltered|no changes?|did not change|"
        r"not (?:significantly )?(?:different|altered)|"
        r"no (?:statistically )?(?:significant )?differences?)\b",
        re.IGNORECASE,
    ),
}
# Una frase sobre la rapidez de respuesta («Slower performance on the PVT») dice el sentido del
# TIEMPO de reacción al revés de sus palabras: más lento es un tiempo mayor. Se declara en la
# frase (`reads_speed`), se lee solo con estas palabras —con las de arriba, «reduced speed» diría
# que baja— y solo la puede citar un indicador que sea un tiempo de reacción. Una frase que habla
# de rapidez sin declararlo se rechaza: leída con las palabras del valor diría el sentido al revés.
_SPEED_WORDS: dict[str, re.Pattern[str]] = {
    "rises": re.compile(r"\b(slow(?:ed|er|ing|ly)?)\b", re.IGNORECASE),
    "falls": re.compile(r"\b(fast(?:er)?|quick(?:er|ly)?|rapid(?:ly)?)\b", re.IGNORECASE),
    "unchanged": _DIRECTION_WORDS["unchanged"],
}
# Cualquier palabra de rapidez, también las que no dan sentido («speeds», «rapidity»): «Response
# speeds decreased» leída con las palabras del valor diría que el tiempo baja.
_SPEED_TALK = re.compile(
    r"\b(slow(?:ed|er|ing|ly|ness)?|fast(?:er|est)?|quick(?:er|ly|ness)?|rapid(?:ly|ity)?|"
    r"speed(?:s|ed|ier)?)\b",
    re.IGNORECASE,
)
REACTION_TIME = frozenset({"pvt-mean-rt"})
# Un tiempo de reacción solo se lee de una frase de rapidez o de una que nombre el tiempo: «PVT
# performance decreased» leída con las palabras del valor diría que el tiempo baja cuando la
# frase dice que empeoró (que sube).
_TIME_TALK = re.compile(
    r"\b(?:reaction|response)\s+times?\b|\bRTs?\b|\blatenc(?:y|ies)\b", re.IGNORECASE,
)
# Una negación en el literal («no less than», «not ~16 % lower», «lower, but not
# significantly», «failed to decrease», «not unaltered») no deja leer el sentido: se rechaza en
# vez de leerla al revés o a medias, esté donde esté. Las únicas negaciones admitidas son las que
# SON la frase de «sin cambio» («no changes», «did not change», «not different»), y se quitan antes
# de buscar otra.
_NEGATION = re.compile(
    r"\b(no|not|nor|never|neither|none|without|cannot|fail(?:ed|s|ing)?\s+to)\b|n't\b",
    re.IGNORECASE,
)
# La negación puede quedar justo fuera del literal: «ONSD was not increased during flight» con el
# literal «increased during flight». Se mira lo que lo precede en la frase dentro de su oración
# (desde la última coma, punto y coma, dos puntos o punto) y hasta tres palabras.
_CLAUSE_BREAK = re.compile(r"[,;:.]")
_LEAD_WORDS = 3
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# El sentido es en el tiempo. «No differences were detected among groups» o «higher between men
# and women» compara grupos, no el vuelo con antes: una frase que nombra la comparación entre
# grupos en la oración de su literal (también justo después: «No significant differences were
# detected among countermeasure groups during flight») no se lee como sentido, sea cual sea. Lo
# que compara momentos («between preflight and inflight», «between study phases») sí vale.
_GROUP_COMPARISON = re.compile(
    r"\b(between|among|amongst)\b(?!\s+(?:the\s+)?(?:(?:study|flight|mission)\s+)?"
    r"(?:pre-?flight|in-?flight|post-?flight|baseline|time\s?points?|sessions?|phases?|"
    r"days?)\b)",
    re.IGNORECASE,
)
# La frase habla del vuelo, no de después: lo que se mide al volver es otra pregunta (y es justo
# donde se equivocó la deriva del simulador). Dos filtros de palabras: la frase tiene que nombrar
# el vuelo, y el literal —el trozo que da el sentido— no puede nombrar el después («elevated
# postflight» en una frase que también dice «inflight»). Cazan el despiste de copiar una frase de
# tierra o de la vuelta, no toda frase mal elegida.
_IN_FLIGHT = re.compile(
    r"\b(in[- ]?flight|during (?:the )?(?:early |late )?(?:space)?flight|in space|of flight|"
    r"(?:early|mid|late)-flight|spaceflight|on the ISS|ISS\d*|micro-?G)\b",
    re.IGNORECASE,
)
_AFTER_FLIGHT = re.compile(
    # «post space flight» y «after space flight», en dos palabras, también son después: el vuelo
    # en dos palabras no cuenta como vuelo en `_IN_FLIGHT`, pero su después sí se rechaza.
    r"\b(post[- ]?(?:space[ -]?)?flight|post-?mission|"
    r"after (?:the )?(?:flight|landing|return|space[ -]?flight)|"
    r"on return|upon return|recovery|R\s?\+\s?\d+)\b",
    re.IGNORECASE,
)
# Ni el antes como momento del cambio: «increased at L-10» o «during preflight» es otra pregunta.
# «compared to preflight» sí vale: es la comparación, no el momento.
_BEFORE_FLIGHT = re.compile(
    r"\bL\s?[-−]\s?\d+\b|\b(?:at|during|in|on)\s+(?:the\s+)?pre-?(?:flight|launch)\b",
    re.IGNORECASE,
)
# Y la frase no puede ser de un análogo en tierra: «simulated microG» o el reposo en cama nombran
# el vuelo sin serlo, y una palabra como «microG» ya basta para pasar el primer filtro.
_GROUND_ANALOG = re.compile(
    r"\b(simulated|bed[- ]?rest|head[- ]down|dry immersion|parabolic|analogu?e?s?)\b",
    re.IGNORECASE,
)

FRAME = (
    "Lo que se observó en otros vuelos, no lo esperado en esta persona. Cada sentido sale de una "
    "frase leída de un estudio publicado con otras tripulaciones, con su fuente; sin frase leída, "
    "«sin fuente». No cambia la base, ni el nivel, ni ninguna alerta, y una lectura que vaya en "
    "ese sentido no queda explicada por ello."
)
_TEXT: dict[str, str] = {
    "rises": "En otros vuelos se observó que sube.",
    "falls": "En otros vuelos se observó que baja.",
    "unchanged": "En otros vuelos no se observó cambio.",
    NO_SOURCE: "Sin fuente leída sobre su sentido en vuelo.",
}
# Un indicador que el fichero no nombra no se buscó: no es lo mismo que buscarlo y no encontrarlo.
NOT_SEARCHED = "Sin fuente leída sobre su sentido en vuelo; no se ha buscado."
SEARCHED_PREFIX = "Buscado y no encontrado: "
# Lo leído junto a un indicador CON sentido que no da sentido en vuelo (el único estudio con
# hemoglobina en vuelo con estadística la ve subir; otro, leído al buscar, solo da los
# productos de su degradación, y otro, una tendencia a bajar sin estadística): se dice, con su
# ficha, y no cuenta como frase.
ALSO_READ_PREFIX = "Leído también, sin sentido en vuelo: "
i18n.en_many({
    FRAME: (
        "What was observed on other flights, not what is expected in this person. Each direction "
        "comes from a sentence read in a published study with other crews, with its source; "
        "with no sentence read, «no source». It does not change the baseline, the level or any "
        "alert, and a reading that goes in that direction is not explained by it."
    ),
    _TEXT["rises"]: "On other flights it was observed to rise.",
    _TEXT["falls"]: "On other flights it was observed to fall.",
    _TEXT["unchanged"]: "On other flights no change was observed.",
    _TEXT[NO_SOURCE]: "No source read on its direction in flight.",
    NOT_SEARCHED: "No source read on its direction in flight; it has not been searched for.",
    SEARCHED_PREFIX: "Searched and not found: ",
    ALSO_READ_PREFIX: "Also read, with no direction in flight: ",
})


class FlightDirectionError(ValueError):
    """Lo leído no cumple su contrato: no se sirve."""


def _text(item: dict[str, Any], field: str) -> bool:
    value = item.get(field)
    return isinstance(value, str) and bool(value.strip())


def _check_date(value: Any, what: str) -> None:
    """Una fecha de lectura es AAAA-MM-DD: se compara como texto para dar la más reciente.

    `date.fromisoformat` acepta también «20260101» o «2026-W43-5», que ordenados como texto
    darían una fecha que no es la más reciente.
    """
    if not isinstance(value, str) or _DATE.fullmatch(value) is None:
        raise FlightDirectionError(f"{what}: `read_on` no es una fecha AAAA-MM-DD")
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        raise FlightDirectionError(f"{what}: `read_on` no es una fecha") from None


def _negated(literal: str, direction: str) -> bool:
    """El literal niega algo, fuera de la frase misma de «sin cambio»."""
    if direction == "unchanged":
        literal = _DIRECTION_WORDS["unchanged"].sub(" ", literal)
    return _NEGATION.search(literal) is not None


def _negated_before(quote: str, literal: str) -> bool:
    """La frase niega el literal justo antes de él, en su misma oración."""
    lead = _CLAUSE_BREAK.split(quote[: quote.index(literal)])[-1]
    return _NEGATION.search(" ".join(lead.split()[-_LEAD_WORDS:])) is not None


def _clause(quote: str, literal: str) -> str:
    """La oración del literal en su frase: desde la pausa de antes hasta la de después."""
    start = quote.index(literal)
    lead = _CLAUSE_BREAK.split(quote[:start])[-1]
    tail = _CLAUSE_BREAK.split(quote[start + len(literal):])[0]
    return lead + literal + tail


def _validate_statement(item: dict[str, Any], sources: dict[str, Any]) -> None:
    key = item.get("id", "?")
    for field in ("id", "ref", "where", "quote", "literal", "direction", "compared_with",
                  "population"):
        if not _text(item, field):
            raise FlightDirectionError(
                f"{key}: falta `{field}`: sin frase, sección, comparación y fuente no es un dato"
            )
    if item["ref"] not in sources:
        raise FlightDirectionError(f"{key}: de {item['ref']!r} no se declara cuánto se leyó")
    ref = registry.get(item["ref"])
    if ref.population != "human":
        # Un ratón en la ISS no dice en qué sentido cambia nada en un tripulante.
        raise FlightDirectionError(f"{key}: {ref.id} no es una fuente medida solo en personas")
    parts = urlsplit(ref.url or "")
    if parts.scheme != "https" or parts.hostname not in OFFICIAL_HOSTS:
        raise FlightDirectionError(f"{key}: {ref.url!r} no es la revista, PubMed Central ni NASA")
    direction, literal, quote = item["direction"], item["literal"], item["quote"]
    if direction not in OBSERVED:
        raise FlightDirectionError(f"{key}: una frase dice que sube, que baja o que no cambia")
    if literal not in quote:
        raise FlightDirectionError(f"{key}: {literal!r} no está escrito en su frase")
    reads_speed = item.get("reads_speed", False)
    if not isinstance(reads_speed, bool):
        raise FlightDirectionError(f"{key}: `reads_speed` es verdadero o falso")
    table = _SPEED_WORDS if reads_speed else _DIRECTION_WORDS
    if table[direction].search(literal) is None:
        raise FlightDirectionError(f"{key}: el literal no dice que {OBSERVED[direction]}")
    for other, words in table.items():
        if other != direction and words.search(literal):
            raise FlightDirectionError(f"{key}: el literal dice también que {OBSERVED[other]}")
    if reads_speed and any(
        _DIRECTION_WORDS[name].search(literal) for name in ("rises", "falls")
    ):
        # «Reduced speed»: con palabras de los dos registros, el sentido no se puede leer.
        raise FlightDirectionError(f"{key}: el literal mezcla rapidez y sentido del valor")
    if not reads_speed and _SPEED_TALK.search(literal):
        raise FlightDirectionError(f"{key}: el literal habla de rapidez sin declararlo")
    if _negated(literal, direction) or _negated_before(quote, literal):
        raise FlightDirectionError(f"{key}: el literal niega algo: no se lee su sentido")
    if _GROUP_COMPARISON.search(_clause(quote, literal)):
        raise FlightDirectionError(f"{key}: la frase compara grupos, no el vuelo con antes")
    if "read_on" in item:
        # Una frase leída otro día que el resto de su fuente lleva su propia fecha.
        _check_date(item["read_on"], key)
    if _IN_FLIGHT.search(quote) is None:
        raise FlightDirectionError(f"{key}: la frase no dice que sea en vuelo")
    if _GROUND_ANALOG.search(quote):
        raise FlightDirectionError(f"{key}: la frase es de un análogo en tierra, no del vuelo")
    if _AFTER_FLIGHT.search(literal):
        raise FlightDirectionError(f"{key}: el literal habla de después del vuelo")
    if _BEFORE_FLIGHT.search(literal):
        raise FlightDirectionError(f"{key}: el literal sitúa el cambio antes del vuelo")


def _validate_searched(
    key: str, item: dict[str, Any], sources: dict[str, Any], what: str
) -> list[str]:
    searched_refs = item.get("searched_refs")
    if not isinstance(searched_refs, list) or not searched_refs:
        # Lo buscado también se leyó: sin ficha, sería prosa sin comprobar.
        raise FlightDirectionError(f"{key}: {what} sin su ficha leída")
    if len(set(searched_refs)) != len(searched_refs):
        raise FlightDirectionError(f"{key}: {what} con una ficha repetida")
    for ref in searched_refs:
        if ref not in sources:
            raise FlightDirectionError(f"{key}: de {ref!r} no se declara cuánto se leyó")
    return searched_refs


def _validate_indicator(
    key: str, item: dict[str, Any], statements: dict[str, Any], sources: dict[str, Any]
) -> None:
    if key not in CATALOG:
        raise FlightDirectionError(f"{key}: no es un indicador del catálogo")
    direction = item.get("direction")
    if direction not in DIRECTION_DISPLAY:
        raise FlightDirectionError(f"{key}: sentido desconocido {direction!r}")
    cited = item.get("statements")
    if not isinstance(cited, list):
        raise FlightDirectionError(f"{key}: `statements` es una lista")
    for ref in cited:
        if ref not in statements:
            raise FlightDirectionError(f"{key}: {ref!r} no es una frase leída")
    if len(set(cited)) != len(cited):
        raise FlightDirectionError(f"{key}: una frase repetida")
    if "scope" in item and not _text(item, "scope"):
        raise FlightDirectionError(f"{key}: `scope` vacío")
    for ref in cited:
        if statements[ref].get("reads_speed") and key not in REACTION_TIME:
            # «Más lento» es «sube» solo para un tiempo de reacción.
            raise FlightDirectionError(f"{key}: una frase de rapidez solo da un tiempo de reacción")
        if (key in REACTION_TIME and not statements[ref].get("reads_speed")
                and _TIME_TALK.search(statements[ref]["literal"]) is None):
            raise FlightDirectionError(
                f"{key}: un tiempo de reacción sale de una frase de rapidez o que nombre el tiempo"
            )
    found = {statements[ref]["direction"] for ref in cited}
    if direction == NO_SOURCE:
        if cited:
            raise FlightDirectionError(f"{key}: «sin fuente» con frases leídas")
        if not _text(item, "searched"):
            # Uno sin declarar ya es «sin fuente»: si se declara, es que se buscó, y dónde.
            raise FlightDirectionError(f"{key}: «sin fuente» declarado sin decir dónde se buscó")
        _validate_searched(key, item, sources, "lo buscado y no encontrado")
        return
    if "searched" in item or "searched_refs" in item:
        # Con sentido, lo buscado es lo leído también que no lo da: texto y ficha, los dos.
        if not _text(item, "searched"):
            raise FlightDirectionError(f"{key}: lo leído también sin decir qué dice")
        also = _validate_searched(key, item, sources, "lo leído también")
        if overlap := sorted(set(also) & {statements[ref]["ref"] for ref in cited}):
            # La fuente que da el sentido no puede salir a la vez como la que no lo da.
            raise FlightDirectionError(f"{key}: {overlap} da una frase y no da sentido a la vez")
    if direction == CONTESTED:
        if len(found) < 2:
            raise FlightDirectionError(f"{key}: «discutido» necesita frases que no coincidan")
        return
    if not cited:
        raise FlightDirectionError(f"{key}: un sentido sin frase leída es «sin fuente»")
    if found != {direction}:
        raise FlightDirectionError(
            f"{key}: las frases no dicen todas que {DIRECTION_DISPLAY[direction]}"
        )


def validate(raw: dict[str, Any]) -> dict[str, Any]:
    """Rechaza lo que no se pueda sostener con la fuente delante."""
    if "read_on" not in raw:
        raise FlightDirectionError("falta `read_on`: una lectura sin fecha no se puede contrastar")
    _check_date(raw["read_on"], "el fichero")
    # El contrato común de las fuentes. Lo leído otro día que el del fichero lleva su fecha, y la
    # de cada frase es la suya: se comprueba con la forma de fecha de este fichero.
    sources = check_sources(raw, FlightDirectionError, EXTENTS, own_read_on=_check_date)
    statements: dict[str, dict[str, Any]] = {}
    for item in raw["statements"]:
        _validate_statement(item, sources)
        if item["id"] in statements:
            raise FlightDirectionError(f"{item['id']}: identificador repetido")
        statements[item["id"]] = item
    for key, item in raw["indicators"].items():
        _validate_indicator(key, item, statements, sources)
    used = {ref for item in raw["indicators"].values() for ref in item["statements"]}
    if unused := sorted(set(statements) - used):
        raise FlightDirectionError(f"frases leídas que ningún indicador usa: {unused}")
    # Una ficha declarada y no usada contaría como citada sin que nada la cite.
    read_refs = {statements[ref]["ref"] for ref in used} | {
        ref for item in raw["indicators"].values() for ref in item.get("searched_refs", ())
    }
    if idle := sorted(set(sources) - read_refs):
        raise FlightDirectionError(f"fichas declaradas que ninguna frase ni búsqueda usa: {idle}")
    return raw


@cache
def read() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(READ_PATH.read_text(encoding="utf-8"))
    return validate(raw)


@cache
def _statements() -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in read()["statements"]}


def cited_refs() -> frozenset[str]:
    """Las fichas del registro de las que se declara lectura."""
    return frozenset(read()["sources"])


def _source_read_on(ref_id: str) -> str:
    """El día en que se leyó una fuente: el suyo, si no el del fichero."""
    raw = read()
    return str(raw["sources"][ref_id].get("read_on") or raw["read_on"])


def _read_on(item: dict[str, Any]) -> str:
    """El día en que se leyó la frase: el suyo, si no el de su fuente, si no el del fichero."""
    return str(item.get("read_on") or _source_read_on(item["ref"]))


def _direction_display(direction: str) -> str:
    """El sentido como se enseña, en el idioma de la petición."""
    return i18n.tr(DIRECTION_DISPLAY[direction], _DIRECTION_EN[direction])


def _statement(item: dict[str, Any]) -> dict[str, Any]:
    raw = read()
    ref = registry.get(item["ref"])
    source = raw["sources"][item["ref"]]
    # Lo que redacta EMMA de la frase (frente a qué, en quién, dónde) va en el idioma de la
    # petición; la frase y su literal son de la fuente y no están en el hermano inglés.
    item = i18n.localized(item, READ_PATH)
    return {
        "id": item["id"],
        "direction": item["direction"],
        "direction_display": _direction_display(item["direction"]),
        "quote": item["quote"],
        "quote_display": f"«{item['quote']}»",
        "literal": item["literal"],
        "compared_with": item["compared_with"],
        "compared_with_display": i18n.tr(
            f"Frente a: {item['compared_with']}.", f"Compared with: {item['compared_with']}."
        ),
        "population": item["population"],
        "where": item["where"],
        "ref": ref.id,
        "source": ref.source,
        "url": ref.url,
        "read_on": _read_on(item),
        "extent": source["extent"],
        "extent_text": _extent_text(EXTENTS[source["extent"]]),
    }


def _extent_text(text: str) -> str:
    """Cuánto se leyó de una fuente, en el idioma de la petición.

    Se busca por el texto castellano de `EXTENTS`, que es de otro módulo: uno que se añada
    allí sin su inglés aquí sale en castellano, no tumba la respuesta.
    """
    return i18n.tr(text, _EXTENT_TEXT_EN.get(text, text))


def _contested_text(rows: list[dict[str, Any]]) -> str:
    counts = {direction: sum(1 for row in rows if row["direction"] == direction)
              for direction in OBSERVED}
    parts = [
        f"{display.number(count, 0)} {'frase' if count == 1 else 'frases'}: {OBSERVED[direction]}"
        for direction, count in counts.items() if count
    ]
    english = [
        f"{display.number(count, 0)} {'sentence' if count == 1 else 'sentences'}: "
        f"{_DIRECTION_EN[direction]}"
        for direction, count in counts.items() if count
    ]
    return i18n.tr(
        f"Discutido: las frases leídas no coinciden ({'; '.join(parts)}).",
        f"Contested: the sentences read do not agree ({'; '.join(english)}).",
    )


def for_indicator(key: str) -> dict[str, Any]:
    """El sentido en vuelo de un indicador, tal como se sirve junto a su línea base."""
    item = read()["indicators"].get(key, {"direction": NO_SOURCE, "statements": []})
    direction = item["direction"]
    rows = [_statement(_statements()[ref]) for ref in item["statements"]]
    # El alcance y lo buscado los redacta EMMA: en el idioma de la petición (el hermano inglés se
    # aplica aquí, al servir, y no en `read()`, que está cacheado y es lo que se valida).
    item = i18n.localized(item, READ_PATH)
    searched = item.get("searched")
    if direction == CONTESTED:
        text = _contested_text(rows)
    elif direction == NO_SOURCE and not searched:
        text = i18n.loc(NOT_SEARCHED)
    else:
        text = i18n.loc(_TEXT[direction])
    prefix = SEARCHED_PREFIX if direction == NO_SOURCE else ALSO_READ_PREFIX
    searched_refs = item.get("searched_refs", ())
    shown = {
        "key": key,
        "display_es": get(key).display_es,
        "direction": direction,
        "direction_display": _direction_display(direction),
        "text": text,
        "scope": item.get("scope"),
        "searched": searched,
        "searched_display": f"{i18n.loc(prefix)}{searched}" if searched else None,
        # La cita de lo buscado y no encontrado (o leído también), tal como la da el registro.
        "searched_sources": [registry.get(ref).source for ref in searched_refs],
        # Lo buscado también se leyó un día: el de cada ficha, en el orden de sus citas.
        "searched_read_on": [_source_read_on(ref) for ref in searched_refs],
        # Y cuánto se leyó de cada una, como en las frases.
        "searched_extent_text": [
            EXTENTS[read()["sources"][ref]["extent"]] for ref in searched_refs
        ],
        "statements": rows,
    }
    shown["searched_extent_text"] = [
        _extent_text(text) for text in shown["searched_extent_text"]
    ]
    return shown


def _summary(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return i18n.tr(
            "Ningún indicador analizado: no hay sentido en vuelo que enseñar.",
            "No indicator analysed: there is no direction in flight to show.",
        )
    read_rows = [row for row in rows if row["direction"] != NO_SOURCE]
    counts = [
        f"{_direction_display(key)}: "
        f"{display.number(sum(1 for row in read_rows if row['direction'] == key), 0)}"
        for key in DIRECTION_DISPLAY
        if key != NO_SOURCE and any(row["direction"] == key for row in read_rows)
    ]
    noun = i18n.tr(
        "indicador analizado" if len(rows) == 1 else "indicadores analizados",
        "indicator analysed" if len(rows) == 1 else "indicators analysed",
    )
    text = i18n.tr(
        f"{display.number(len(rows), 0)} {noun}: {display.number(len(read_rows), 0)} con "
        f"sentido leído en otros vuelos",
        f"{display.number(len(rows), 0)} {noun}: {display.number(len(read_rows), 0)} with "
        f"a direction read on other flights",
    )
    if counts:
        text += f" ({'; '.join(counts)})"
    without = display.number(len(rows) - len(read_rows), 0)
    return text + i18n.tr(f" y {without} sin fuente.", f" and {without} with no source.")


def for_profile(keys: Iterable[str]) -> dict[str, Any]:
    """El bloque que acompaña al perfil de línea base: uno por indicador analizado, en su orden."""
    rows = [for_indicator(key) for key in keys]
    return {
        "note": i18n.loc(FRAME),
        "statement": _summary(rows),
        # La lectura más reciente de lo que se enseña, frases y lo buscado; cada frase lleva la
        # suya. La del fichero, solo si no se enseña nada leído.
        "read_on": max(
            [row["read_on"] for item in rows for row in item["statements"]]
            + [day for item in rows for day in item["searched_read_on"]],
            default=read()["read_on"],
        ),
        "indicators": rows,
    }
