"""El mapa de la aplicación que ve el modelo en cada turno: las pestañas y los paneles que más se
parecen a lo que ha dicho la persona, con lo que hay dentro de cada uno.

Por qué existe: medido el 2026-11-04 con qwen3.5:9b, la mitad de las frases naturales fallaban
porque el modelo solo veía los RÓTULOS de las pestañas y los paneles. «¿Cómo está el aire de la
nave?» contestaba «no tengo datos» (el CO2 está en «Tripulación y hábitat»), y «llévame a donde se
apunta cómo duermo» abría el seguimiento de contramedidas. Cada entrada del inventario lleva ahora
un `about` (qué enseña y qué deja hacer, escrito desde el propio componente), pero los ~175 no
caben en el contexto de cada turno. Aquí se puntúan contra la frase y se le dan al modelo los
pocos que se parecen, con su `about`.

La puntuación es léxica, sin modelo y sin red: palabras sin tildes y en minúsculas, sin palabras
vacías, comparadas por su comienzo (cinco letras: «duermo» y «dormir» no casan, «tendencia» y
«tendencias» sí) y ensanchadas con los grupos de sinónimos de `assistant_intents.json` («dormir»
trae «sueño», «aire» trae «CO2»). Lo que casa con el rótulo o un alias pesa más que lo que casa
con el `about`, y cada palabra pesa según lo rara que es en el inventario (una que sale en todos
los paneles no distingue ninguno).

NO DECIDE NADA. Solo ordena candidatos para el prompt; la intención la elige el modelo y la valida
el catálogo como siempre. Sin modelo, la consola usa el mejor candidato solo si la persona pidió
ver o ir a algo y la puntuación es clara (`best_place`).

EN INGLÉS (2026-11-15) el mapa es el del catálogo inglés y cambian dos cosas del idioma: las
palabras vacías, y que la raíz se toma tras quitar el plural. El castellano marca género y número
al final de palabras largas y cinco letras bastan («hueso», «huesos»); en inglés las palabras con
contenido son cortas y el plural ya cambia la quinta letra («bone» y «bones», «dose» y «doses»,
«eye» y «eyes» no casarían).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.assistant.catalog import Panel, Section, catalog, plain
from app.core import i18n

STEM = 5
# Lo que no distingue un panel de otro.
STOPWORDS = frozenset((
    "a", "al", "algo", "alguna", "alguno", "ante", "aqui", "asi", "como", "con", "cual", "cuando",
    "de", "del", "desde", "donde", "dos", "el", "ella", "en", "entre", "es", "esa", "ese", "eso",
    "esta", "este", "esto", "estoy", "estan", "estas", "fue", "ha", "han", "hay", "la", "las",
    "le", "les", "lo", "los", "me", "mi", "mis", "muy", "no", "nos", "o", "para", "pero", "poco",
    "por", "que", "quiero", "se", "si", "sin", "sobre", "su", "sus", "te", "ti", "tu", "tus",
    "un", "una", "uno", "unos", "unas", "y", "ya", "yo", "emma", "oye", "vale", "pues", "porfa",
    "favor", "puedes", "podrias", "dime", "ver", "ensena", "ensename", "muestrame", "muestra",
    "abre", "abreme", "llevame", "lleva", "ir", "ve", "vete", "pon", "ponme", "sale", "salen",
    "cosa", "cosas", "tengo", "tiene", "tienes", "estado", "mio", "mia", "hoy", "ahora", "otra",
    "vez",
))
# Las palabras vacías del inglés, sobre texto de `plain` («don't» llega como «don» y «t»): lo
# gramatical, y los verbos de pedir, ver e ir, que salen en casi todas las frases.
STOPWORDS_EN = frozenset((
    "a", "about", "again", "all", "am", "an", "and", "any", "are", "as", "at", "be", "been",
    "but", "by", "can", "could", "did", "do", "does", "don", "for", "from", "had", "has", "have",
    "he", "her", "here", "him", "his", "how", "i", "if", "in", "into", "is", "it", "its", "just",
    "ll", "m", "me", "my", "no", "not", "now", "of", "on", "one", "or", "our", "out", "over",
    "re", "s", "she", "so", "some", "t", "than", "that", "the", "their", "them", "then", "there",
    "these", "they", "this", "those", "to", "too", "two", "up", "us", "ve", "very", "was", "we",
    "were", "what", "when", "where", "which", "who", "why", "will", "with", "would", "you",
    "your", "emma", "hey", "ok", "okay", "please", "tell", "see", "show", "open", "take",
    "bring", "go", "going", "put", "let", "want", "like", "look", "get", "give", "find", "thing",
    "things", "got", "today", "time", "other", "another", "status",
))
LABEL_WEIGHT = 3.0
ABOUT_WEIGHT = 1.0
SECTION_WEIGHT = 0.5
TOP_PANELS = 6
# Por debajo de esto un candidato no se usa sin modelo: casó una palabra suelta del `about`.
CLEAR_SCORE = 3.0


@dataclass(frozen=True)
class Candidate:
    kind: str  # "panel" o "section"
    key: str
    label: str
    section: str | None
    about: str
    score: float


def stems(text: str, size: int = STEM) -> set[str]:
    """Las raíces de las palabras con contenido de un texto (sus `size` primeras letras)."""
    if i18n.current() == "en":
        return {_singular(word)[:size] for word in plain(text).split()
                if word not in STOPWORDS_EN and len(word) > 1}
    return {word[:size] for word in plain(text).split()
            if word not in STOPWORDS and len(word) > 1}


def _singular(word: str) -> str:
    """Una palabra inglesa sin su plural (o su tercera persona): «doses» es «dose», «batteries»
    es «battery», «boxes» es «box». Deja como están las que acaban en «ss», «us» o «is»
    («status», «analysis») y las de tres letras o menos."""
    if len(word) <= 3 or not word.endswith("s") or word.endswith(("ss", "us", "is")):
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ches", "shes", "xes", "zes", "sses")):
        return word[:-2]
    return word[:-1]


@i18n.lang_cache
def _synonym_stems(size: int) -> tuple[frozenset[str], ...]:
    return tuple(frozenset(stem for word in group for stem in stems(word, size))
                 for group in catalog().synonyms)


def expand(query: set[str], size: int = STEM) -> set[str]:
    """La consulta con los sinónimos de cada palabra suya (raíces del mismo tamaño)."""
    out = set(query)
    for group in _synonym_stems(size):
        if query & group:
            out |= group
    return out


@dataclass(frozen=True)
class _Doc:
    kind: str
    key: str
    label: str
    section: str | None
    about: str
    named: frozenset[str]
    described: frozenset[str]
    placed: frozenset[str]


def _section_label(console: str, key: str | None) -> str:
    if key is None:
        return ""
    section = catalog().section(console, key)
    return section.label if section is not None else ""


@i18n.lang_cache
def _docs(console: str) -> tuple[_Doc, ...]:
    cat = catalog()
    docs: list[_Doc] = []
    for section in cat.sections[console]:
        if section.key.startswith("env-"):
            continue  # las de entorno son una por perfil, con el mismo `about`: va una sola
        docs.append(_section_doc(section))
    env = next((s for s in cat.sections[console] if s.key.startswith("env-")), None)
    if env is not None:
        docs.append(_Doc("section", "env-*",
                         i18n.tr("Entornos de misión", "Mission environments"), None, env.about,
                         frozenset(stems(" ".join(env.keywords))), frozenset(stems(env.about)),
                         frozenset()))
    for panel in cat.panels.values():
        if panel.in_console(console):
            docs.append(_panel_doc(panel, console))
    return tuple(docs)


def _section_doc(section: Section) -> _Doc:
    return _Doc("section", section.key, section.label, None, section.about,
                frozenset(stems(section.label + " " + " ".join(section.keywords))),
                frozenset(stems(section.about)), frozenset())


def _panel_doc(panel: Panel, console: str) -> _Doc:
    place = next(p for p in panel.places if p.console == console)
    section_label = _section_label(console, place.section) if place.section != "env-*" else ""
    return _Doc("panel", panel.id, panel.label, place.section, panel.about,
                frozenset(stems(panel.label + " " + " ".join(panel.aliases))),
                frozenset(stems(panel.about)), frozenset(stems(section_label)))


@i18n.lang_cache
def _idf(console: str) -> dict[str, float]:
    docs = _docs(console)
    counts: dict[str, int] = {}
    for doc in docs:
        for stem in doc.named | doc.described:
            counts[stem] = counts.get(stem, 0) + 1
    return {stem: math.log(1 + len(docs) / count) for stem, count in counts.items()}


def _score(doc: _Doc, query: set[str], direct: set[str], idf: dict[str, float]) -> float:
    total = 0.0
    for stem in query:
        weight = idf.get(stem)
        if weight is None:
            continue
        if stem in doc.named:
            field = LABEL_WEIGHT
        elif stem in doc.described:
            field = ABOUT_WEIGHT
        elif stem in doc.placed:
            field = SECTION_WEIGHT
        else:
            continue
        # Lo que dijo la persona pesa el doble que lo que trae un sinónimo.
        total += field * weight * (1.0 if stem in direct else 0.5)
    return total


def rank(text: str, console: str) -> list[Candidate]:
    """Pestañas y paneles de esta consola por parecido con la frase (solo los que casan)."""
    direct = stems(text)
    if not direct:
        return []
    query = expand(direct)
    idf = _idf(console)
    scored = [(round(_score(doc, query, direct, idf), 3), doc) for doc in _docs(console)]
    return [Candidate(doc.kind, doc.key, doc.label, doc.section, doc.about, score)
            for score, doc in sorted(scored, key=lambda item: (-item[0], item[1].key))
            if score > 0]


def candidates(text: str, console: str, top: int = TOP_PANELS) -> list[Candidate]:
    """Los paneles que van al prompt de este turno: los `top` mejores."""
    return [item for item in rank(text, console) if item.kind == "panel"][:top]


def best_place(text: str, console: str) -> Candidate | None:
    """El candidato claro para «llévame a…» sin modelo: el mejor, si se despega del segundo."""
    ranked = rank(text, console)
    if not ranked or ranked[0].score < CLEAR_SCORE:
        return None
    if len(ranked) > 1 and ranked[1].score >= ranked[0].score * 0.9 and (
        ranked[1].kind == ranked[0].kind
    ):
        return None
    return ranked[0]


def map_text(text: str, console: str) -> str:
    """El bloque del prompt: los paneles más parecidos, con su pestaña y lo que hay dentro."""
    lines = []
    tab = i18n.tr("pestaña", "tab")
    for item in candidates(text, console):
        where = f", {tab} {item.section}" if item.section and item.section != "env-*" else ""
        lines.append(f"- {item.key} «{item.label}»{where}: {item.about}")
    return "\n".join(lines) or i18n.tr("(ningún panel se parece a la petición)",
                                       "(no panel resembles the request)")
