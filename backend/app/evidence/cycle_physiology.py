"""Cuánto cambian la temperatura, la frecuencia cardiaca y la variabilidad con la fase del ciclo.

POR QUÉ EXISTE
--------------
La línea base de EMMA compara a cada tripulante con sus últimos 14 días, y la validación que la
sostiene (`compliance/external-validation.md`) se hizo con MMASH: 24 h de varones. En una mujer con
ciclo natural, la fase lútea sube la temperatura y la frecuencia cardiaca y baja la variabilidad
vagal; con el ruido de temperatura del simulador (0,18 °C), un escalón lúteo de varias décimas ya
son unas dos desviaciones típicas. Es una causa conocida de falsa alarma que nadie había medido,
y la invariante 5 obliga a medirla junto con la sensibilidad. Antes de medirla o de corregirla
(lote «ciclo»: el simulador con ciclo y la línea base consciente de la fase) hace falta saber
cuánto es, y eso no se inventa: la regla de `CLAUDE.md` («cómo se justifica lo que se afirma») es
que el siguiente parámetro sin verificar también está mal.

QUÉ HACE, Y QUÉ NO
------------------
Lo leído el 2026-11-14 vive en `data/cycle_physiology_read.json` y este cargador es su defensa:
cada frase lleva su ficha del registro, de personas y en la revista, PubMed Central o PubMed; el
sentido tiene que estar escrito en su literal (y el literal, en la frase); cada cifra está escrita
en una frase leída de la misma fuente, o es la resta declarada de dos medias que lo están; y cada
indicador y fase declara su clase con el vocabulario de las derivas del simulador
(`ingest/simulator.py`, `EVIDENCE_CLASSES`): magnitud documentada, sentido documentado, discutido
(frases que no coinciden, de al menos dos fuentes) o buscado y no encontrado, con lo leído al
buscar. Las frases que no van en el sentido de la fila se dicen (`dissent`) con el motivo de que
no la vuelvan «discutida»; no se callan.

La referencia es la fase folicular. `amplitude(key, phase)` es una función pura sobre el fichero:
da la diferencia frente a ella con su clase y sus fichas, y `None` en la cifra cuando lo leído no
la sostiene. La supresión menstrual (Jain y Wotring 2016) se sirve aparte: con ella no hay fase.

Nada de esto entra hoy en la base, el riesgo, los niveles ni las alertas, ni lee el sexo de nadie:
es lo que leerán la línea base y el simulador cuando se decida (invariante 5: las dos métricas
juntas). Tampoco sale a la red: la lectura se hizo una vez, en Tierra.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, TypeGuard
from urllib.parse import urlsplit

from app.core import i18n
from app.evidence import registry
from app.evidence.instruments_read import EXTENTS
from app.evidence.read_contract import check_sources
from app.ingest.codes import CATALOG

READ_PATH = Path(__file__).resolve().parents[1] / "data" / "cycle_physiology_read.json"

REFERENCE_PHASE = "follicular"
PHASES: dict[str, str] = {
    "menstrual": "menstruación",
    "follicular": "fase folicular",
    "luteal": "fase lútea",
}
DIRECTIONS: dict[str, str] = {"rises": "sube", "falls": "baja", "unchanged": "sin cambio"}
CONTESTED = "contested"
# El vocabulario de las derivas del simulador (`ingest/simulator.py`, `EVIDENCE_CLASSES`), sin
# «design»: aquí todo se buscó.
EVIDENCE: dict[str, str] = {
    "established": "magnitud documentada",
    "direction_only": "sentido documentado",
    "contested": "discutido",
    "unsupported": "buscado y no encontrado",
}
# Lo que devuelve la fase de referencia: no es una clase de respaldo, es la definición del cero.
REFERENCE = "reference"
# El inglés de las fases y de las clases, al lado y no en el registro común de `i18n.en`: son
# rótulos cortos («discutido») que otros módulos también enseñan, cada uno con el suyo. Solo es
# lo que se enseña: lo que valida el fichero y los mensajes de rechazo siguen con los de arriba.
_PHASES_EN: dict[str, str] = {
    "menstrual": "menstruation",
    "follicular": "follicular phase",
    "luteal": "luteal phase",
}
_EVIDENCE_EN: dict[str, str] = {
    "established": "documented magnitude",
    "direction_only": "documented direction",
    "contested": "contested",
    "unsupported": "searched and not found",
}

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Las palabras con que la frase, en inglés, dice cada sentido. El literal lleva una de su sentido
# y ninguna del otro.
_WORDS: dict[str, re.Pattern[str]] = {
    "rises": re.compile(r"\b(higher|increase[ds]?|elevated|greater|rises?)\b", re.IGNORECASE),
    "falls": re.compile(r"\b(lower|decrease[ds]?|reduced|reductions?)\b", re.IGNORECASE),
    "unchanged": re.compile(
        r"\b(unchanged|not different|no (?:statistically )?(?:significant )?differences?)\b",
        re.IGNORECASE,
    ),
}
_FLIP = {"rises": "falls", "falls": "rises", "unchanged": "unchanged"}
# Una frase que no nombra la fase de su fila («increased across the cycle», «lower toward the end»)
# se puede usar, pero dice en `phase_note` cómo se lee la fase: si no, la fila diría más de lo que
# dice la frase.
_PHASE_WORDS: dict[str, re.Pattern[str]] = {
    "luteal": re.compile(r"\bluteal\b", re.IGNORECASE),
    "menstrual": re.compile(r"\b(menses|menstrual phase)\b", re.IGNORECASE),
}
# Estas fuentes son artículos de revista: la ficha apunta a PubMed Central, a PubMed o al DOI.
_HOSTS = frozenset({"pmc.ncbi.nlm.nih.gov", "pubmed.ncbi.nlm.nih.gov", "doi.org"})
_FINDING_FIELDS = (
    "id", "ref", "where", "quote", "literal", "phase", "compared_with", "direction", "measure",
    "population",
)


class CyclePhysiologyError(ValueError):
    """Lo leído no cumple su contrato: no se sirve."""


@dataclass(frozen=True, slots=True)
class Amplitude:
    """La diferencia de un indicador en una fase frente a la folicular, con su respaldo.

    `low`/`high` van en la unidad del catálogo y con signo (una bajada es negativa); son `None`
    cuando la clase no es «magnitud documentada». `refs` son las fichas del registro de lo leído.
    """

    key: str
    phase: str
    evidence: str
    direction: str
    low: float | None
    high: float | None
    unit: str
    refs: tuple[str, ...]


def _text(item: dict[str, Any], field: str) -> bool:
    value = item.get(field)
    return isinstance(value, str) and bool(value.strip())


def _number(value: Any) -> TypeGuard[float]:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _written(value: float, text: str) -> bool:
    """El número está escrito en el texto tal cual se publicó (136, 0.3, 57.92), y no como trozo
    de otro: el 59 de «59.98» no es un 59 escrito (arreglo de C1 en `menopause_physiology`,
    copiado aquí por B3 el 2026-11-15)."""
    return re.search(rf"(?<![\d.]){re.escape(f'{value:g}')}(?![\d]|\.\d)", text) is not None


def _human_official(ref_id: str, what: str) -> None:
    ref = registry.get(ref_id)
    if ref.population != "human":
        raise CyclePhysiologyError(f"{what}: {ref_id} no es una fuente medida solo en personas")
    parts = urlsplit(ref.url or "")
    if parts.scheme != "https" or parts.hostname not in _HOSTS:
        raise CyclePhysiologyError(f"{what}: {ref.url!r} no es PubMed Central, PubMed ni el DOI")


def _validate_magnitude(item: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> None:
    key = item["id"]
    magnitude = item["magnitude"]
    if not isinstance(magnitude, dict):
        raise CyclePhysiologyError(f"{key}: `magnitude` es un objeto")
    low, high = magnitude.get("low"), magnitude.get("high")
    if not _number(low) or not _number(high) or low > high:
        raise CyclePhysiologyError(f"{key}: la cifra necesita `low` <= `high`")
    indicator = magnitude.get("key")
    if indicator not in CATALOG:
        # Una SDNN no da la cifra de la RMSSD aunque las dos vayan en milisegundos.
        raise CyclePhysiologyError(f"{key}: la cifra no dice de qué indicador del catálogo es")
    if magnitude.get("unit") != CATALOG[indicator].unit:
        raise CyclePhysiologyError(f"{key}: la cifra no está en {CATALOG[indicator].unit}")
    direction = item["direction"]
    if (direction == "rises" and low <= 0) or (direction == "falls" and high >= 0) or (
        direction == "unchanged"
    ):
        raise CyclePhysiologyError(f"{key}: el signo de la cifra no es el de su sentido")
    derived = magnitude.get("derived_from")
    own_reference = item["compared_with"]
    if derived is None:
        if "compared_with" in magnitude or "reference_from" in magnitude:
            # Sin resta, la cifra se compara con lo que dice su frase, no con otra cosa.
            raise CyclePhysiologyError(f"{key}: una cifra escrita no cambia de referencia")
        # La cifra está escrita en su propia frase; una bajada se publica sin signo («5.5 lower»).
        for value in (low, high):
            if not _written(abs(value), item["quote"]):
                raise CyclePhysiologyError(f"{key}: {value} no está escrito en su frase")
        return
    if not isinstance(derived, list) or not derived:
        raise CyclePhysiologyError(f"{key}: `derived_from` son pares [fase, referencia]")
    reference = own_reference
    source = item
    if "compared_with" in magnitude and magnitude["compared_with"] != own_reference:
        # La resta usa la media de la referencia de otra frase del mismo estudio: esa frase tiene
        # que ser la que compara con esa referencia y hablar de ella.
        other = by_id.get(str(magnitude.get("reference_from")))
        if (
            other is None or other.get("ref") != item["ref"]
            or other.get("compared_with") != magnitude["compared_with"]
            or other.get("literal_about") != "reference"
        ):
            raise CyclePhysiologyError(
                f"{key}: la media de la referencia sale de una frase del mismo estudio que hable "
                "de esa referencia (`reference_from`)"
            )
        reference, source = magnitude["compared_with"], other
    elif "reference_from" in magnitude:
        raise CyclePhysiologyError(f"{key}: `reference_from` sin cambiar de referencia")
    # La media de la referencia es la que su frase da para ESA fase (`means`), no otra media de la
    # misma frase: «56.56 (folicular) compared with 57.92 (menstruación)» lleva las dos.
    means = source.get("means")
    if not isinstance(means, dict) or not _number(means.get(reference)):
        raise CyclePhysiologyError(
            f"{key}: sin la media de la referencia ({reference}) en `means` de su frase"
        )
    for phase, value in means.items():
        if not _number(value) or not _written(value, str(source.get("quote", ""))):
            raise CyclePhysiologyError(f"{key}: la media de {phase} no está escrita en su frase")
    differences = []
    for pair in derived:
        if not (isinstance(pair, list) and len(pair) == 2 and all(_number(x) for x in pair)):
            raise CyclePhysiologyError(f"{key}: `derived_from` son pares [fase, referencia]")
        if not _written(pair[0], item["quote"]):
            raise CyclePhysiologyError(f"{key}: {pair[0]} no está escrito en su frase")
        if pair[1] != means[reference]:
            raise CyclePhysiologyError(f"{key}: {pair[1]} no es la media de la referencia")
        differences.append(round(pair[0] - pair[1], 2))
    if (round(low, 2), round(high, 2)) != (min(differences), max(differences)):
        raise CyclePhysiologyError(f"{key}: la cifra no es la resta de sus medias")


def _validate_finding(
    item: dict[str, Any], sources: dict[str, Any], by_id: dict[str, dict[str, Any]]
) -> None:
    key = item.get("id", "?")
    for field in _FINDING_FIELDS:
        if not _text(item, field):
            raise CyclePhysiologyError(
                f"{key}: falta `{field}`: sin frase, sección, comparación y fuente no es un dato"
            )
    if item["ref"] not in sources:
        raise CyclePhysiologyError(f"{key}: de {item['ref']!r} no se declara cuánto se leyó")
    _human_official(item["ref"], key)
    if item["phase"] not in PHASES or item["phase"] == REFERENCE_PHASE:
        raise CyclePhysiologyError(f"{key}: fase desconocida o la de referencia")
    direction, literal = item["direction"], item["literal"]
    if direction not in DIRECTIONS:
        raise CyclePhysiologyError(f"{key}: una frase dice que sube, que baja o que no cambia")
    if literal not in item["quote"]:
        raise CyclePhysiologyError(f"{key}: {literal!r} no está escrito en su frase")
    about = item.get("literal_about", "phase")
    if about not in ("phase", "reference"):
        raise CyclePhysiologyError(f"{key}: `literal_about` es `phase` o `reference`")
    # «Lower in the follicular phase» dice que la fase de la fila está más alta.
    said = _FLIP[direction] if about == "reference" else direction
    if _WORDS[said].search(literal) is None:
        raise CyclePhysiologyError(f"{key}: el literal no dice que {DIRECTIONS[said]}")
    for other, words in _WORDS.items():
        if other != said and words.search(literal):
            raise CyclePhysiologyError(f"{key}: el literal dice también que {DIRECTIONS[other]}")
    if _PHASE_WORDS[item["phase"]].search(item["quote"]) is None and not _text(item, "phase_note"):
        raise CyclePhysiologyError(
            f"{key}: la frase no nombra su fase y no dice cómo se lee (`phase_note`)"
        )
    if "magnitude" in item:
        _validate_magnitude(item, by_id)


def _check_findings(
    key: str, cited: Any, findings: dict[str, dict[str, Any]], phase: str, what: str
) -> list[dict[str, Any]]:
    if not isinstance(cited, list):
        raise CyclePhysiologyError(f"{key}: `{what}` es una lista")
    if len(set(cited)) != len(cited):
        raise CyclePhysiologyError(f"{key}: una frase repetida en `{what}`")
    rows = []
    for ref in cited:
        if ref not in findings:
            raise CyclePhysiologyError(f"{key}: {ref!r} no es una frase leída")
        if findings[ref]["phase"] != phase:
            raise CyclePhysiologyError(f"{key}: {ref} habla de otra fase")
        rows.append(findings[ref])
    return rows


def _validate_entry(
    key: str, phase: str, entry: dict[str, Any], findings: dict[str, dict[str, Any]],
    sources: dict[str, Any],
) -> None:
    where = f"{key}/{phase}"
    evidence = entry.get("evidence")
    if not isinstance(evidence, str) or evidence not in EVIDENCE:
        raise CyclePhysiologyError(f"{where}: clase desconocida {evidence!r}")
    if evidence == "unsupported":
        if any(field in entry for field in ("findings", "magnitude_findings", "dissent")):
            raise CyclePhysiologyError(f"{where}: «buscado y no encontrado» con frases leídas")
        if not _text(entry, "searched"):
            raise CyclePhysiologyError(f"{where}: sin decir qué se buscó")
        refs = entry.get("searched_refs")
        if not isinstance(refs, list) or not refs or len(set(refs)) != len(refs):
            raise CyclePhysiologyError(f"{where}: lo buscado sin sus fichas leídas")
        for ref in refs:
            if ref not in sources:
                raise CyclePhysiologyError(f"{where}: de {ref!r} no se declara cuánto se leyó")
        return
    rows = _check_findings(where, entry.get("findings"), findings, phase, "findings")
    if not rows:
        raise CyclePhysiologyError(f"{where}: una clase con respaldo necesita frases leídas")
    if not _text(entry, "note"):
        raise CyclePhysiologyError(f"{where}: sin nota que diga de dónde sale lo que se dice")
    low, high = entry.get("low"), entry.get("high")
    magnitude = _check_findings(
        where, entry.get("magnitude_findings", []), findings, phase, "magnitude_findings"
    )
    if set(entry.get("magnitude_findings", [])) - set(entry["findings"]):
        # La frase que da la cifra también respalda el sentido: está arriba, a la vista.
        raise CyclePhysiologyError(f"{where}: una frase con cifra que no está en `findings`")
    directions = {row["direction"] for row in rows}
    if evidence == CONTESTED:
        if entry.get("direction") != CONTESTED:
            raise CyclePhysiologyError(f"{where}: lo discutido no tiene sentido propio")
        if len(directions) < 2 or len({row["ref"] for row in rows}) < 2:
            raise CyclePhysiologyError(
                f"{where}: «discutido» necesita frases que no coincidan, de dos fuentes o más"
            )
        if low is not None or high is not None or magnitude or entry.get("dissent"):
            raise CyclePhysiologyError(f"{where}: lo discutido no lleva cifra ni disenso aparte")
        return
    direction = entry.get("direction")
    if directions != {direction}:
        raise CyclePhysiologyError(f"{where}: las frases no dicen todas que {direction}")
    if "dissent" in entry:
        dissent = _check_findings(where, entry["dissent"], findings, phase, "dissent")
        if not dissent or set(entry["dissent"]) & set(entry["findings"]):
            raise CyclePhysiologyError(f"{where}: el disenso son frases leídas que no están arriba")
        if any(row["direction"] == direction for row in dissent):
            raise CyclePhysiologyError(f"{where}: un disenso que va en el sentido de la fila")
        if not _text(entry, "dissent_note"):
            raise CyclePhysiologyError(f"{where}: un disenso sin decir por qué no es «discutido»")
    if evidence == "direction_only":
        if low is not None or high is not None or magnitude:
            raise CyclePhysiologyError(f"{where}: un sentido documentado no lleva cifra")
        return
    # Magnitud documentada: la cifra es la envolvente de las frases que la dan, frente a la
    # folicular y en la unidad del catálogo.
    if not magnitude:
        raise CyclePhysiologyError(f"{where}: una magnitud documentada sin frase con cifra")
    unit = CATALOG[key].unit
    lows, highs = [], []
    for row in magnitude:
        if "magnitude" not in row:
            raise CyclePhysiologyError(f"{where}: {row['id']} no da cifra")
        figure = row["magnitude"]
        if figure.get("key") != key:
            # La cifra de otro indicador (la SDNN de 24 h para la RMSSD) no vale aunque la unidad
            # coincida.
            raise CyclePhysiologyError(f"{where}: {row['id']} da la cifra de otro indicador")
        if figure["unit"] != unit:
            raise CyclePhysiologyError(f"{where}: {row['id']} no está en {unit}")
        if figure.get("compared_with", row["compared_with"]) != REFERENCE_PHASE:
            raise CyclePhysiologyError(f"{where}: {row['id']} no se compara con la folicular")
        lows.append(figure["low"])
        highs.append(figure["high"])
    if low != min(lows) or high != max(highs):
        raise CyclePhysiologyError(
            f"{where}: la cifra no es la de sus frases ({min(lows)}, {max(highs)})"
        )


def validate(raw: dict[str, Any]) -> dict[str, Any]:
    """Rechaza lo que no se pueda sostener con la fuente delante."""
    read_on = raw.get("read_on")
    if not isinstance(read_on, str) or _DATE.fullmatch(read_on) is None:
        raise CyclePhysiologyError(
            "falta `read_on` AAAA-MM-DD: una lectura sin fecha no se contrasta"
        )
    try:
        dt.date.fromisoformat(read_on)
    except ValueError:
        raise CyclePhysiologyError("`read_on` no es una fecha") from None
    if raw.get("reference_phase") != REFERENCE_PHASE:
        raise CyclePhysiologyError("la referencia es la fase folicular")
    sources = check_sources(raw, CyclePhysiologyError, EXTENTS)
    suppression = raw.get("suppression")
    if not isinstance(suppression, dict) or not all(
        _text(suppression, field) for field in ("ref", "where", "quote", "text")
    ):
        raise CyclePhysiologyError("la supresión menstrual sin su frase, su fuente y su texto")
    if suppression["ref"] not in sources:
        raise CyclePhysiologyError("de la fuente de la supresión no se declara cuánto se leyó")
    _human_official(suppression["ref"], "supresión")
    items = raw.get("findings")
    if not isinstance(items, list):
        raise CyclePhysiologyError("`findings` es una lista")
    if not all(isinstance(item, dict) for item in items):
        raise CyclePhysiologyError("una frase leída es un objeto")
    # Para la media de referencia que una resta toma de otra frase del mismo estudio.
    by_id = {str(item.get("id")): item for item in items}
    findings: dict[str, dict[str, Any]] = {}
    for item in items:
        _validate_finding(item, sources, by_id)
        if item["id"] in findings:
            raise CyclePhysiologyError(f"{item['id']}: identificador repetido")
        findings[item["id"]] = item
    indicators = raw.get("indicators")
    if not isinstance(indicators, dict) or not indicators:
        raise CyclePhysiologyError("`indicators` dice, por indicador y fase, lo leído")
    used: set[str] = set()
    read_refs = {suppression["ref"]}
    for key, phases in indicators.items():
        if key not in CATALOG:
            raise CyclePhysiologyError(f"{key}: no es un indicador del catálogo")
        if not isinstance(phases, dict) or not phases:
            raise CyclePhysiologyError(f"{key}: sin fases")
        for phase, entry in phases.items():
            if phase not in PHASES or phase == REFERENCE_PHASE:
                raise CyclePhysiologyError(f"{key}: fase {phase!r} desconocida o la de referencia")
            if not isinstance(entry, dict):
                raise CyclePhysiologyError(f"{key}/{phase}: es un objeto")
            _validate_entry(key, phase, entry, findings, sources)
            cited = [*entry.get("findings", ()), *entry.get("dissent", ())]
            used.update(cited)
            read_refs.update(findings[ref]["ref"] for ref in cited)
            read_refs.update(entry.get("searched_refs", ()))
    if unused := sorted(set(findings) - used):
        raise CyclePhysiologyError(f"frases leídas que ningún indicador usa: {unused}")
    # Una ficha declarada y no usada contaría como citada sin que nada la cite.
    if idle := sorted(set(sources) - read_refs):
        raise CyclePhysiologyError(f"fichas declaradas que ninguna frase ni búsqueda usa: {idle}")
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


def keys() -> tuple[str, ...]:
    """Los indicadores de los que se buscó la variación por fase."""
    return tuple(read()["indicators"])


def _unique(refs: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(refs))


def amplitude(key: str, phase: str) -> Amplitude:
    """La diferencia de `key` en `phase` frente a la fase folicular, con su clase y sus fichas.

    La folicular es el cero por definición (`REFERENCE`). Un indicador que no se buscó es un
    `KeyError`: no es lo mismo que buscarlo y no encontrarlo (`unsupported`).
    """
    if phase not in PHASES:
        raise ValueError(f"fase desconocida {phase!r}; una de {sorted(PHASES)}")
    indicators = read()["indicators"]
    if key not in indicators:
        raise KeyError(f"{key}: no se buscó su variación por fase")
    unit = CATALOG[key].unit
    if phase == REFERENCE_PHASE:
        return Amplitude(key, phase, REFERENCE, REFERENCE, 0.0, 0.0, unit, ())
    entry = indicators[key].get(phase)
    if entry is None:
        raise KeyError(f"{key}/{phase}: no se buscó")
    if entry["evidence"] == "unsupported":
        return Amplitude(key, phase, "unsupported", "unknown", None, None, unit,
                         _unique(list(entry["searched_refs"])))
    by_id = _findings()
    refs = [by_id[ref]["ref"] for ref in (*entry["findings"], *entry.get("dissent", ()))]
    return Amplitude(
        key, phase, entry["evidence"], entry["direction"], entry.get("low"), entry.get("high"),
        unit, _unique(refs),
    )


def suppression() -> dict[str, Any]:
    """Por qué nada de esto vale para una tripulante con supresión menstrual, con su cita."""
    # El texto y el sitio de la frase, en el idioma de la petición; la frase es de la fuente.
    item = i18n.localized(read()["suppression"], READ_PATH)
    ref = registry.get(item["ref"])
    return {**item, "source": ref.source, "url": ref.url}


def phase_display(phase: str) -> str:
    """El nombre de una fase como se enseña, en el idioma de la petición."""
    return i18n.tr(PHASES[phase], _PHASES_EN[phase])


def evidence_display(evidence: str) -> str:
    """La clase de respaldo como se enseña, en el idioma de la petición."""
    return i18n.tr(EVIDENCE[evidence], _EVIDENCE_EN[evidence])


def table() -> list[dict[str, Any]]:
    """Una fila por indicador y fase leídos, para enseñar o para el informe (solo lectura)."""
    rows = []
    # La nota de cada fila la redacta EMMA: el hermano inglés se aplica aquí, al servir, y no en
    # `read()`, que está cacheado y es lo que se valida.
    for key, phases in i18n.localized(read()["indicators"], READ_PATH).items():
        for phase, entry in phases.items():
            found = amplitude(key, phase)
            rows.append({
                "key": key,
                "phase": phase,
                "phase_display": phase_display(phase),
                "evidence": found.evidence,
                "evidence_display": evidence_display(found.evidence),
                "direction": found.direction,
                "low": found.low,
                "high": found.high,
                "unit": found.unit,
                "refs": list(found.refs),
                "note": entry.get("note") or entry.get("searched"),
            })
    return rows
