"""Lo que se sabe de la menopausia y la perimenopausia que toca a EMMA, y lo que falta en vuelo.

POR QUÉ EXISTE
--------------
Muchas astronautas vuelan pasados los 40: en una misión larga, la perimenopausia es el caso
probable, no el raro. Toca a EMMA por tres sitios. Los sofocos suben la frecuencia cardiaca y la
temperatura de la piel en picos de minutos, y el motor puede leerlos como episodios agudos. Sin
ciclo regular no hay fase que ajustar: la variación por fase del ciclo (`cycle_physiology`) se
refiere a mujeres con ciclo ovulatorio, y aplicarla a quien no lo tiene restaría un escalón lúteo
que no existe y podría tapar una subida real. Y la caída de estrógenos acelera la pérdida ósea igual
que la microgravedad, en el dominio óseo de EMMA, donde ya están el estradiol, la FSH y la LH.

Antes de tocar el motor, el simulador o la línea base hace falta saber cuánto es cada cosa, y eso
no se inventa (`CLAUDE.md`, «cómo se justifica lo que se afirma»).

POR QUÉ ES UN FICHERO HERMANO Y NO UNA FASE MÁS
-----------------------------------------------
`cycle_physiology_read.json` da cada fase como diferencia frente a la folicular. Un sofoco no es
una fase (es un episodio frente a los minutos de antes), una tasa de pérdida ósea no está en la
unidad del catálogo y, sin ovulación, no hay folicular con la que comparar. Meterlo allí habría
obligado a aflojar sus defensas (la fase de referencia, la cifra en la unidad del indicador). Aquí
van las mismas defensas sobre la frase —literal escrito en ella, sentido escrito en el literal,
cifra escrita, fichas de personas en sitios oficiales, clase con el vocabulario del simulador—, y
dos clases de tema: `change` (un indicador sube, baja o no cambia) y `figure` (una cantidad con su
unidad: minutos de un sofoco, años con síntomas, porcentaje de pérdida ósea).

QUÉ HACE, Y QUÉ NO
------------------
Lo leído el 2026-11-15 vive en `data/menopause_physiology_read.json`; este cargador lo rechaza si
una cifra no está escrita en su frase, una clase no tiene el respaldo que dice o un tema sin
indicador no dice por qué. `in_flight` dice qué se sabe en vuelo: frases leídas que hablan de
astronautas y lo buscado sin encontrar (nada se ha medido de la menopausia en vuelo).

Nada de esto entra en la base, el riesgo, los niveles ni las alertas, ni lee el sexo de nadie: es lo
que leerán la línea base consciente de la fase (para NO ajustar sin ciclo regular) y el simulador
cuando se decida (invariante 5: las dos métricas juntas). Tampoco sale a la red.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.core import i18n
from app.evidence import registry
from app.evidence.cycle_physiology import CONTESTED, DIRECTIONS, EVIDENCE, evidence_display
from app.evidence.cycle_physiology import _number as is_number
from app.evidence.cycle_physiology import _text as has_text
from app.evidence.instruments_read import EXTENTS
from app.evidence.read_contract import check_sources
from app.ingest.codes import CATALOG

READ_PATH = Path(__file__).resolve().parents[1] / "data" / "menopause_physiology_read.json"

KINDS: dict[str, str] = {"change": "cambio", "figure": "cifra"}
SUBJECTS: dict[str, str] = {
    "hot_flash": "sofocos",
    "perimenopause": "perimenopausia",
    "bone": "hueso",
}
# Las unidades de una cifra de este fichero. Las de un indicador del catálogo son las suyas (UCUM);
# las demás son de una cantidad que no es un indicador.
UNITS: dict[str, str] = {
    "Cel": "°C",
    "/min": "lpm",
    "ms": "ms",
    "min": "min",
    "a": "años",
    "/d": "al día",
    "%": "%",
    "%/mo": "% al mes",
    "{ratio}": "veces",
}
# El inglés de lo que se enseña, al lado y no en el registro común de `i18n.en`: son palabras
# cortas («hueso», «años») que otros módulos también enseñan, cada uno con el suyo.
_SUBJECTS_EN: dict[str, str] = {
    "hot_flash": "hot flashes",
    "perimenopause": "perimenopause",
    "bone": "bone",
}
_UNITS_EN: dict[str, str] = {
    "Cel": "°C",
    "/min": "bpm",
    "ms": "ms",
    "min": "min",
    "a": "years",
    "/d": "per day",
    "%": "%",
    "%/mo": "% per month",
    "{ratio}": "times",
}

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def written(value: float, text: str) -> bool:
    """El número está escrito tal cual en el texto, y no como trozo de otro (el 3 de «3.9»)."""
    return re.search(rf"(?<![\d.]){re.escape(f'{value:g}')}(?![\d]|\.\d)", text) is not None


# Las palabras con que la frase, en inglés, dice cada sentido. Son las de `cycle_physiology` más
# las que usan estas fuentes («fell», «elevations», «similar», «the same», «did not show
# differences»). El literal lleva una de su sentido y ninguna del otro.
_WORDS: dict[str, re.Pattern[str]] = {
    "rises": re.compile(
        r"\b(higher|increase[ds]?|elevated|elevations?|greater|rises?|rose)\b", re.IGNORECASE
    ),
    "falls": re.compile(
        r"\b(lower|decrease[ds]?|reduced?|reduces|reductions?|fell|falls?)\b", re.IGNORECASE
    ),
    "unchanged": re.compile(
        r"\b(unchanged|not different|similar|the same|did not show differences|"
        r"no (?:statistically )?(?:significant )?differences?)\b",
        re.IGNORECASE,
    ),
}
# Las revistas: PubMed Central, PubMed o el DOI, y la ficha tiene que ser de personas.
_JOURNAL_HOSTS = frozenset({"pmc.ncbi.nlm.nih.gov", "pubmed.ncbi.nlm.nih.gov", "doi.org"})
# Los documentos de la NASA juntan astronautas con cohortes de Tierra o con animales; se aceptan,
# y la frase dice en `population` de qué parte habla.
_NASA_HOSTS = frozenset({"humanresearchroadmap.nasa.gov", "www.nasa.gov", "ntrs.nasa.gov"})
_FINDING_FIELDS = ("id", "ref", "where", "quote", "literal", "measure", "population")


class MenopausePhysiologyError(ValueError):
    """Lo leído no cumple su contrato: no se sirve."""


@dataclass(frozen=True, slots=True)
class Topic:
    """Un tema leído con su respaldo.

    `direction` es `None` en una cifra (`figure`); `low`/`high` van en `unit` y con signo (una
    bajada es negativa), y son `None` cuando la clase no es «magnitud documentada». `indicator` es
    la clave del catálogo, o `None` si lo medido no es un indicador de EMMA.
    """

    key: str
    subject: str
    kind: str
    indicator: str | None
    evidence: str
    direction: str | None
    low: float | None
    high: float | None
    unit: str
    refs: tuple[str, ...]


def _official(ref_id: str, what: str) -> None:
    ref = registry.get(ref_id)
    parts = urlsplit(ref.url or "")
    if parts.scheme != "https":
        raise MenopausePhysiologyError(f"{what}: {ref.url!r} no es una dirección https")
    if parts.hostname in _JOURNAL_HOSTS:
        if ref.population != "human":
            raise MenopausePhysiologyError(
                f"{what}: {ref_id} no es una fuente medida solo en personas"
            )
        return
    if parts.hostname not in _NASA_HOSTS:
        raise MenopausePhysiologyError(
            f"{what}: {ref.url!r} no es PubMed Central, PubMed, el DOI ni la NASA"
        )


def _check_direction(item: dict[str, Any], key: str) -> None:
    direction, literal = item["direction"], item["literal"]
    if direction not in DIRECTIONS:
        raise MenopausePhysiologyError(f"{key}: una frase dice que sube, que baja o que no cambia")
    if _WORDS[direction].search(literal) is None:
        raise MenopausePhysiologyError(f"{key}: el literal no dice que {DIRECTIONS[direction]}")
    for other, words in _WORDS.items():
        if other != direction and words.search(literal):
            raise MenopausePhysiologyError(
                f"{key}: el literal dice también que {DIRECTIONS[other]}"
            )


def _check_magnitude(item: dict[str, Any], key: str) -> None:
    magnitude = item["magnitude"]
    if not isinstance(magnitude, dict):
        raise MenopausePhysiologyError(f"{key}: `magnitude` es un objeto")
    low, high = magnitude.get("low"), magnitude.get("high")
    if not is_number(low) or not is_number(high) or low > high:
        raise MenopausePhysiologyError(f"{key}: la cifra necesita `low` <= `high`")
    if magnitude.get("unit") not in UNITS:
        raise MenopausePhysiologyError(f"{key}: unidad desconocida {magnitude.get('unit')!r}")
    if set(magnitude) - {"low", "high", "unit", "text"}:
        # Aquí no hay restas de medias: la cifra está escrita tal cual en su frase.
        raise MenopausePhysiologyError(
            f"{key}: la cifra es `low`, `high`, `unit` y `text`, sin más"
        )
    # La cifra se busca en el trozo de la frase que la da (`text`), no en toda la frase: si no, una
    # desviación típica, un valor p o el año de una cita pasarían por la cifra.
    text = magnitude.get("text")
    if not isinstance(text, str) or not text.strip() or text not in item["quote"]:
        raise MenopausePhysiologyError(f"{key}: la cifra sin el trozo de su frase que la da")
    # Una bajada se publica sin signo («fell 0.2-0.6 degrees C»).
    for value in (low, high):
        if not written(abs(value), text):
            raise MenopausePhysiologyError(f"{key}: {value} no está escrito en su frase")
    direction = item.get("direction")
    if (direction == "rises" and low <= 0) or (direction == "falls" and high >= 0) or (
        direction == "unchanged"
    ):
        raise MenopausePhysiologyError(f"{key}: el signo de la cifra no es el de su sentido")


def _validate_finding(item: dict[str, Any], sources: dict[str, Any]) -> None:
    key = item.get("id", "?")
    for field in _FINDING_FIELDS:
        if not has_text(item, field):
            raise MenopausePhysiologyError(
                f"{key}: falta `{field}`: sin frase, sección, medida y fuente no es un dato"
            )
    if item["ref"] not in sources:
        raise MenopausePhysiologyError(f"{key}: de {item['ref']!r} no se declara cuánto se leyó")
    _official(item["ref"], key)
    if item["literal"] not in item["quote"]:
        raise MenopausePhysiologyError(f"{key}: {item['literal']!r} no está escrito en su frase")
    if "direction" in item:
        _check_direction(item, key)
    if "magnitude" in item:
        _check_magnitude(item, key)


def _rows(
    where: str, cited: Any, findings: dict[str, dict[str, Any]], what: str
) -> list[dict[str, Any]]:
    if not isinstance(cited, list):
        raise MenopausePhysiologyError(f"{where}: `{what}` es una lista")
    if len(set(cited)) != len(cited):
        raise MenopausePhysiologyError(f"{where}: una frase repetida en `{what}`")
    rows = []
    for ref in cited:
        if ref not in findings:
            raise MenopausePhysiologyError(f"{where}: {ref!r} no es una frase leída")
        rows.append(findings[ref])
    return rows


def _check_unsupported(where: str, entry: dict[str, Any], sources: dict[str, Any]) -> None:
    # (También es la única clase que lleva `searched_refs`: en una con respaldo, una ficha citada
    # solo ahí contaría como leída sin que ninguna frase la use.)
    if any(field in entry for field in ("findings", "magnitude_findings", "dissent", "found")):
        raise MenopausePhysiologyError(f"{where}: «buscado y no encontrado» con frases leídas")
    if entry.get("low") is not None or entry.get("high") is not None:
        raise MenopausePhysiologyError(f"{where}: «buscado y no encontrado» con cifra")
    if not has_text(entry, "searched"):
        raise MenopausePhysiologyError(f"{where}: sin decir qué se buscó")
    refs = entry.get("searched_refs")
    if not isinstance(refs, list) or not refs or len(set(refs)) != len(refs):
        raise MenopausePhysiologyError(f"{where}: lo buscado sin sus fichas leídas")
    for ref in refs:
        if ref not in sources:
            raise MenopausePhysiologyError(f"{where}: de {ref!r} no se declara cuánto se leyó")


def _check_indicator(key: str, entry: dict[str, Any]) -> None:
    indicator = entry.get("indicator", "?")
    if indicator is None:
        if not has_text(entry, "why_no_indicator"):
            raise MenopausePhysiologyError(f"{key}: sin indicador y sin decir por qué")
    elif indicator not in CATALOG:
        raise MenopausePhysiologyError(f"{key}: {indicator!r} no es un indicador del catálogo")
    elif entry.get("unit") != CATALOG[indicator].unit:
        raise MenopausePhysiologyError(f"{key}: la cifra no está en {CATALOG[indicator].unit}")
    related = entry.get("related", [])
    if not isinstance(related, list) or any(item not in CATALOG for item in related):
        raise MenopausePhysiologyError(f"{key}: `related` son indicadores del catálogo")


def _validate_topic(
    key: str, entry: dict[str, Any], findings: dict[str, dict[str, Any]],
    sources: dict[str, Any],
) -> None:
    if entry.get("subject") not in SUBJECTS:
        raise MenopausePhysiologyError(f"{key}: tema de {entry.get('subject')!r} desconocido")
    kind = entry.get("kind")
    if kind not in KINDS:
        raise MenopausePhysiologyError(f"{key}: un tema es `change` o `figure`")
    if entry.get("unit") not in UNITS:
        raise MenopausePhysiologyError(f"{key}: unidad desconocida {entry.get('unit')!r}")
    if not has_text(entry, "context"):
        raise MenopausePhysiologyError(f"{key}: sin decir frente a qué se mide")
    _check_indicator(key, entry)
    evidence = entry.get("evidence")
    if not isinstance(evidence, str) or evidence not in EVIDENCE:
        raise MenopausePhysiologyError(f"{key}: clase desconocida {evidence!r}")
    if kind == "figure" and "direction" in entry:
        raise MenopausePhysiologyError(f"{key}: una cifra no tiene sentido")
    if evidence == "unsupported":
        _check_unsupported(key, entry, sources)
        return
    if "searched_refs" in entry or "searched" in entry:
        raise MenopausePhysiologyError(f"{key}: lo buscado sin encontrar va solo en esa clase")
    rows = _rows(key, entry.get("findings"), findings, "findings")
    if not rows:
        raise MenopausePhysiologyError(f"{key}: una clase con respaldo necesita frases leídas")
    if not has_text(entry, "note"):
        raise MenopausePhysiologyError(f"{key}: sin nota que diga de dónde sale lo que se dice")
    magnitude = _rows(key, entry.get("magnitude_findings", []), findings, "magnitude_findings")
    if set(entry.get("magnitude_findings", [])) - set(entry["findings"]):
        raise MenopausePhysiologyError(f"{key}: una frase con cifra que no está en `findings`")
    low, high = entry.get("low"), entry.get("high")
    if kind == "change":
        if any("direction" not in row for row in rows):
            raise MenopausePhysiologyError(f"{key}: un cambio citado con una frase sin sentido")
        directions = {row["direction"] for row in rows}
        if evidence == CONTESTED:
            if entry.get("direction") != CONTESTED:
                raise MenopausePhysiologyError(f"{key}: lo discutido no tiene sentido propio")
            if len(directions) < 2 or len({row["ref"] for row in rows}) < 2:
                raise MenopausePhysiologyError(
                    f"{key}: «discutido» necesita frases que no coincidan, de dos fuentes o más"
                )
            if low is not None or high is not None or magnitude or entry.get("dissent"):
                raise MenopausePhysiologyError(
                    f"{key}: lo discutido no lleva cifra ni disenso aparte"
                )
            return
        direction = entry.get("direction")
        if directions != {direction}:
            raise MenopausePhysiologyError(f"{key}: las frases no dicen todas que {direction}")
        if "dissent" in entry:
            dissent = _rows(key, entry["dissent"], findings, "dissent")
            if not dissent or set(entry["dissent"]) & set(entry["findings"]):
                raise MenopausePhysiologyError(
                    f"{key}: el disenso son frases leídas que no están arriba"
                )
            if any(row.get("direction") in (None, direction) for row in dissent):
                raise MenopausePhysiologyError(f"{key}: un disenso que va en el sentido del tema")
            if not has_text(entry, "dissent_note"):
                raise MenopausePhysiologyError(
                    f"{key}: un disenso sin decir por qué no es «discutido»"
                )
    elif evidence == CONTESTED or "dissent" in entry:
        # Dos cifras que no coinciden se dicen en la envolvente y en la nota, no como sentido.
        raise MenopausePhysiologyError(f"{key}: una cifra no es «discutida» ni lleva disenso")
    if evidence == "direction_only":
        if low is not None or high is not None or magnitude:
            raise MenopausePhysiologyError(f"{key}: un sentido documentado no lleva cifra")
        return
    if not magnitude:
        raise MenopausePhysiologyError(f"{key}: una magnitud documentada sin frase con cifra")
    lows, highs = [], []
    for row in magnitude:
        if "magnitude" not in row:
            raise MenopausePhysiologyError(f"{key}: {row['id']} no da cifra")
        if row["magnitude"]["unit"] != entry["unit"]:
            raise MenopausePhysiologyError(f"{key}: {row['id']} no está en {entry['unit']}")
        lows.append(row["magnitude"]["low"])
        highs.append(row["magnitude"]["high"])
    if low != min(lows) or high != max(highs):
        raise MenopausePhysiologyError(
            f"{key}: la cifra no es la de sus frases ({min(lows)}, {max(highs)})"
        )


def _validate_in_flight(
    raw: dict[str, Any], findings: dict[str, dict[str, Any]], sources: dict[str, Any]
) -> list[str]:
    block = raw.get("in_flight")
    if not isinstance(block, dict):
        raise MenopausePhysiologyError("`in_flight` dice qué se sabe en vuelo")
    if block.get("evidence") != "unsupported":
        # Si un día se mide algo en vuelo, será un tema con su clase, no este bloque.
        raise MenopausePhysiologyError("`in_flight`: la menopausia en vuelo es «buscado y no "
                                       "encontrado» mientras nadie la mida")
    if not has_text(block, "text"):
        raise MenopausePhysiologyError("`in_flight`: sin el texto que lo cuenta")
    found = block.get("found")
    rows = _rows("in_flight", found, findings, "found")
    if not rows:
        raise MenopausePhysiologyError("`in_flight`: sin las frases leídas que lo sostienen")
    copy = {key: value for key, value in block.items() if key != "found"}
    _check_unsupported("in_flight", copy, sources)
    return [row["id"] for row in rows]


def validate(raw: dict[str, Any]) -> dict[str, Any]:
    """Rechaza lo que no se pueda sostener con la fuente delante."""
    read_on = raw.get("read_on")
    if not isinstance(read_on, str) or _DATE.fullmatch(read_on) is None:
        raise MenopausePhysiologyError(
            "falta `read_on` AAAA-MM-DD: una lectura sin fecha no se contrasta"
        )
    try:
        dt.date.fromisoformat(read_on)
    except ValueError:
        raise MenopausePhysiologyError("`read_on` no es una fecha") from None
    sources = check_sources(raw, MenopausePhysiologyError, EXTENTS)
    items = raw.get("findings")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise MenopausePhysiologyError("`findings` es una lista de frases leídas")
    findings: dict[str, dict[str, Any]] = {}
    for item in items:
        _validate_finding(item, sources)
        if item["id"] in findings:
            raise MenopausePhysiologyError(f"{item['id']}: identificador repetido")
        findings[item["id"]] = item
    topics = raw.get("topics")
    if not isinstance(topics, dict) or not topics:
        raise MenopausePhysiologyError("`topics` dice, tema a tema, lo leído")
    used: set[str] = set()
    read_refs: set[str] = set()
    for key, entry in topics.items():
        if not isinstance(entry, dict):
            raise MenopausePhysiologyError(f"{key}: es un objeto")
        _validate_topic(key, entry, findings, sources)
        cited = [*entry.get("findings", ()), *entry.get("dissent", ())]
        used.update(cited)
        read_refs.update(findings[ref]["ref"] for ref in cited)
        read_refs.update(entry.get("searched_refs", ()))
    flight = _validate_in_flight(raw, findings, sources)
    used.update(flight)
    read_refs.update(findings[ref]["ref"] for ref in flight)
    read_refs.update(raw["in_flight"]["searched_refs"])
    if unused := sorted(set(findings) - used):
        raise MenopausePhysiologyError(f"frases leídas que ningún tema usa: {unused}")
    if idle := sorted(set(sources) - read_refs):
        raise MenopausePhysiologyError(
            f"fichas declaradas que ninguna frase ni búsqueda usa: {idle}"
        )
    return raw


@cache
def read() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(READ_PATH.read_text(encoding="utf-8"))
    return validate(raw)


@cache
def _findings() -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in read()["findings"]}


def cited_refs() -> frozenset[str]:
    """Las fichas del registro de las que se declara lectura."""
    return frozenset(read()["sources"])


def topic_keys() -> tuple[str, ...]:
    """Los temas leídos."""
    return tuple(read()["topics"])


def _unique(refs: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(refs))


def topic(key: str) -> Topic:
    """Un tema con su clase y sus fichas. Uno que no se buscó es un `KeyError`."""
    topics = read()["topics"]
    if key not in topics:
        raise KeyError(f"{key}: no es un tema leído")
    entry = topics[key]
    if entry["evidence"] == "unsupported":
        refs = _unique(list(entry["searched_refs"]))
    else:
        by_id = _findings()
        refs = _unique(
            [by_id[ref]["ref"] for ref in (*entry["findings"], *entry.get("dissent", ()))]
        )
    direction = entry.get("direction") if entry["kind"] == "change" else None
    if entry["evidence"] == "unsupported" and entry["kind"] == "change":
        direction = "unknown"
    return Topic(
        key, entry["subject"], entry["kind"], entry.get("indicator"), entry["evidence"],
        direction, entry.get("low"), entry.get("high"), entry["unit"], refs,
    )


def in_flight() -> dict[str, Any]:
    """Qué se sabe en vuelo: el texto, las frases leídas con su fuente y lo buscado."""
    # El texto, lo buscado y lo que EMMA redacta de cada frase (qué mide, en quién, dónde), en el
    # idioma de la petición: el hermano inglés se aplica aquí, al servir, y no en `read()`, que
    # está cacheado y es lo que se valida. La frase y su literal son de la fuente.
    block = i18n.localized(read()["in_flight"], READ_PATH)
    by_id = _findings()
    found = []
    for finding_id in block["found"]:
        item = i18n.localized(by_id[finding_id], READ_PATH)
        ref = registry.get(item["ref"])
        found.append({**item, "source": ref.source, "url": ref.url})
    return {
        "evidence": block["evidence"],
        "evidence_display": evidence_display(block["evidence"]),
        "text": block["text"],
        "found": found,
        "searched": block["searched"],
        "searched_refs": list(block["searched_refs"]),
    }


def table() -> list[dict[str, Any]]:
    """Una fila por tema leído, para enseñar o para el informe (solo lectura)."""
    rows = []
    # Frente a qué se mide y la nota de cada tema, en el idioma de la petición.
    for key, entry in i18n.localized(read()["topics"], READ_PATH).items():
        found = topic(key)
        rows.append({
            "key": key,
            "subject": found.subject,
            "subject_display": i18n.tr(SUBJECTS[found.subject], _SUBJECTS_EN[found.subject]),
            "kind": found.kind,
            "indicator": found.indicator,
            "context": entry["context"],
            "evidence": found.evidence,
            "evidence_display": evidence_display(found.evidence),
            "direction": found.direction,
            "low": found.low,
            "high": found.high,
            "unit": found.unit,
            "unit_display": i18n.tr(UNITS[found.unit], _UNITS_EN[found.unit]),
            "refs": list(found.refs),
            "note": entry.get("note") or entry.get("searched"),
        })
    return rows
