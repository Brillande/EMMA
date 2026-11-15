# SPDX-License-Identifier: AGPL-3.0-or-later
"""Nivel de evidencia de cada fuente citada, sin que lo decida un modelo.

Por qué existe: EMMA cita literatura para justificar sus protocolos y su evidencia, y citar no es
lo mismo que respaldar. Un estudio en cerdos en microgravedad y un ensayo en personas son dos
cosas distintas, y la cita sola no lo dice. CLAUDE.md pide declarar el respaldo de cada
parámetro; esto hace lo mismo con cada fuente.

Adaptador de `polaris/tools/tier_evidencia.py`, de la copia literal de Polaris, sin modificarla
(commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the
Protocol»; se carga con `app.polaris.load`). El patrón es de Polaris (idea que allí se atribuye a
Marc Recio): no se pide una clasificación abierta; se leen señales booleanas atómicas del registro
de PubMed y la jerarquía la aplica el código, así que el resultado es reproducible y explicable
señal a señal. Del original, sin tocar: las señales y su lectura del registro
(`senales_desde_registro()`), su léxico del texto (`senales_desde_texto()`), la jerarquía
(`teje()`) y sus etiquetas.

Pegamento de EMMA, no cambios al original:
  * Sin red en tiempo de ejecución. `scripts/grade_sources.py` lee el registro una vez y guarda
    los tipos de publicación y los MeSH en `app/data/evidence_tiers.json`, con la fecha; aquí se
    le dan al original por su `fetch` inyectable. La suite no toca la red (invariante 3).
  * Las claves del resultado, en inglés como el resto de la API (`etiqueta` → `label`...).
Fail-closed, como el original: con PMID sin registro guardado sale "desconocido"; sin PMID, la
cita y su título pasan por el léxico, del que solo se acepta la marca de preclínico, rotulada
`basis: "text"`; no se le inventa un nivel.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from app import polaris
from app.core import i18n

TIERS_FILE = Path(__file__).resolve().parents[1] / "data" / "evidence_tiers.json"
_PMID = re.compile(r"\bPMID:?\s*(\d{5,9})\b")
# Claves del resultado de `teje()` -> las de la API de EMMA.
_KEYS = {
    "tier": "tier", "etiqueta": "label", "preclinico": "preclinical", "motivo": "reason",
    "senales": "signals", "faltan": "missing",
}


@cache
def _original() -> Any:
    return polaris.load("tier_evidencia")


def signals_from_record(publication_types: list[str], mesh: list[str]) -> dict[str, bool]:
    """Tipos de publicación y MeSH -> señales: `senales_desde_registro()` del registro guardado."""
    record = "".join(f"<PublicationType>{item}</PublicationType>" for item in publication_types)
    record += "".join(f"<DescriptorName>{item}</DescriptorName>" for item in mesh)
    signals, _origin = _original().senales_desde_registro("guardado", fetch=lambda _pmid: record)
    return {str(key): bool(value) for key, value in signals.items()}


# Decisión del usuario (2026-09-29): el nivel lo decide `teje()` de Polaris, pero lo que ve la
# tripulación va con la redacción de EMMA, sin mayúsculas de alarma ni emojis (lib/palette.ts,
# F.5-1: el color y el glifo los pone la interfaz). Son las etiquetas que EMMA usaba antes.
LABELS: dict[str, str] = {
    "guia_clinica": "guía clínica / consenso",
    "metaanalisis": "metaanálisis",
    "revision_sistematica": "revisión sistemática",
    "rct": "ensayo aleatorizado",
    "ensayo_clinico": "ensayo clínico no aleatorizado",
    "cohorte_prospectiva": "cohorte prospectiva",
    "cohorte_retrospectiva": "cohorte retrospectiva",
    "serie_casos": "serie de casos",
    "caso_clinico": "caso clínico",
    "modelo_animal": "modelo animal (preclínico)",
    "in_vitro": "in vitro (preclínico)",
    "revision_narrativa": "revisión narrativa / opinión",
    "preprint": "preprint sin revisar",
    "desconocido": "desconocido: no clasificable desde el registro",
}
i18n.en_many({
    LABELS["guia_clinica"]: "clinical guideline / consensus",
    LABELS["metaanalisis"]: "meta-analysis",
    LABELS["revision_sistematica"]: "systematic review",
    LABELS["rct"]: "randomized trial",
    LABELS["ensayo_clinico"]: "non-randomized clinical trial",
    LABELS["cohorte_prospectiva"]: "prospective cohort",
    LABELS["cohorte_retrospectiva"]: "retrospective cohort",
    LABELS["serie_casos"]: "case series",
    LABELS["caso_clinico"]: "case report",
    LABELS["modelo_animal"]: "animal model (preclinical)",
    LABELS["in_vitro"]: "in vitro (preclinical)",
    LABELS["revision_narrativa"]: "narrative review / opinion",
    LABELS["preprint"]: "preprint, not reviewed",
    LABELS["desconocido"]: "unknown: cannot be classified from the record",
})
_REASON_TEXT = (("⚠️ PREPRINT, sin revisión por pares", "preprint, sin revisión por pares"),)
# Los motivos que escribe `teje()` de Polaris, con su inglés. El motivo es una lista de trozos
# unidos por « · »; cada trozo se busca aquí entero, y uno que el original cambie sale como venga
# (en castellano), no con un inglés adivinado. Los nombres de las señales («animal», «rct»…) son
# identificadores y no se traducen.
i18n.en_many({
    "catalogado como guía/consenso": "cataloged as guideline/consensus",
    "catalogado como metaanálisis": "cataloged as meta-analysis",
    "revisión sistemática sin metaanálisis": "systematic review without meta-analysis",
    "datos recogidos prospectivamente": "data collected prospectively",
    "datos retrospectivos de registro/historia": "retrospective data from a registry or records",
    "serie de casos sin comparador": "case series without a comparator",
    "informe de un solo paciente": "report of a single patient",
    "preprint, sin revisión por pares": "preprint, not peer-reviewed",
    "preprint sin diseño identificable": "preprint with no identifiable design",
    "señal de banco (animal) sin señal de personas": (
        "bench signal (animal) with no signal of people"
    ),
    "señal de banco (in vitro) sin señal de personas": (
        "bench signal (in vitro) with no signal of people"
    ),
})
_REASON_SEPARATOR = " · "
_NO_DESIGN_SIGNAL = re.compile(r"ninguna señal de diseño resuelta \(faltan: (.*)\)")


def _translate(result: dict[str, Any]) -> dict[str, Any]:
    ours = {mine: result[theirs] for theirs, mine in _KEYS.items()}
    ours["label"] = i18n.loc(LABELS.get(str(ours["tier"]), str(ours["label"])))
    reason = str(ours["reason"])
    for theirs, mine in _REASON_TEXT:
        reason = reason.replace(theirs, mine)
    ours["reason"] = _reason(reason)
    return ours


def _reason(reason: str) -> str:
    """El motivo en el idioma de la petición, trozo a trozo; en castellano, tal cual."""
    if i18n.current() != "en":
        return reason
    parts = []
    for part in reason.split(_REASON_SEPARATOR):
        unresolved = _NO_DESIGN_SIGNAL.fullmatch(part)
        parts.append(
            f"no design signal resolved (missing: {unresolved.group(1)})"
            if unresolved is not None else i18n.loc(part)
        )
    return _REASON_SEPARATOR.join(parts)


def weave(given: dict[str, bool]) -> dict[str, Any]:
    """Señales -> nivel: `teje()`. Ningún modelo interviene; lo preclínico manda."""
    return _translate(_original().teje(given))


def _unknown(reason: str) -> dict[str, Any]:
    signals = _original().SENALES
    return _translate(_original()._resultado("desconocido", reason, {}, list(signals)))


@cache
def _records() -> dict[str, dict[str, Any]]:
    data: dict[str, dict[str, Any]] = json.loads(TIERS_FILE.read_text(encoding="utf-8"))["records"]
    return data


# Fuente sin registro: la red de léxico de Polaris (`senales_desde_texto()`), tal cual.
#
# Por qué: "NASA OSDR · OSD-288" no tiene PMID y salía "desconocido", cuando su propio título dice
# que es bazo de ratón. Callar eso deja un estudio preclínico con la misma cara que un informe en
# personas sin catalogar. El léxico del original está hecho para este hueco y solo lee señales que
# degradan (banco, caso) o que niegan lo preclínico (personas); "aleatorizado" o "guía" no los
# detecta a propósito, porque un texto que los menciona ascendería un estudio en ratones. Se usa
# como en su `--texto`: `teje(senales_desde_texto(texto))`, sin otra fuente de señales al lado.
#
# Candados de EMMA alrededor, sin tocar el original:
#   * Solo se lee la cita y su título, que son palabras de la fuente. Lo que EMMA escribe sobre
#     ella (relevancia, alcance) no: casi siempre son negaciones ("NO mide signos vitales
#     humanos") y un léxico literal lee una negación como una afirmación.
#   * El texto solo se lee cuando la cita no nombra PubMed. Nunca se mezcla con las señales del
#     registro: su señal de personas ("patients") quitaría lo preclínico a un registro de animales
#     que además trae un tipo de ensayo, y eso sí sería ascender. Con PMID manda el registro,
#     también cuando falta por guardar o está escrito de una forma que `_PMID` no lee.
#   * Techo: del texto solo se acepta la marca de preclínico (`TEXT_TIERS`). El original saca
#     también "caso clínico" de una frase y su `--texto` lo da por bueno; aquí no, porque
#     partiendo de "desconocido" eso es subir. Un nivel clínico solo lo da el registro.
#   * Rótulo: `basis` dice de dónde sale el nivel y la etiqueta visible lo repite, para que nadie
#     lea un nivel sacado de una frase como si lo hubiera catalogado la NLM.
TEXT_TIERS = frozenset({"modelo_animal", "in_vitro"})
BASIS_RECORD, BASIS_TEXT, BASIS_NONE = "record", "text", "none"
TEXT_LABEL = "desde el texto de la cita, no del registro"
i18n.en(TEXT_LABEL, "from the text of the citation, not from the record")
_PUBMED_MENTION = re.compile(r"pmid|pubmed", re.IGNORECASE)


def signals_from_text(text: str) -> dict[str, bool]:
    """Texto de la cita -> señales: `senales_desde_texto()`. Solo degrada; no detecta ensayos."""
    return {str(key): bool(value) for key, value in _original().senales_desde_texto(text).items()}


def _from_text(text: str) -> dict[str, Any] | None:
    """El nivel que da el texto, rotulado; `None` si no da señales o se sale del techo."""
    graded = weave(signals_from_text(text))
    if graded["tier"] not in TEXT_TIERS:
        return None
    graded["label"] = f"{graded['label']} · {i18n.loc(TEXT_LABEL)}"
    no_pmid = i18n.tr(
        "sin PMID: leído del texto de la cita, no del registro",
        "no PMID: read from the text of the citation, not from the record",
    )
    graded["reason"] = f"{graded['reason']} · {no_pmid}"
    return graded


def grade(source: str, text: str = "") -> dict[str, Any]:
    """El nivel de una fuente citada como texto, y de dónde sale (`basis`).

    `text` son palabras de la propia fuente además de la cita: su título. Solo se lee si la cita
    no nombra PubMed, y de él solo se acepta la marca de preclínico. Si no, desconocido.
    """
    match = _PMID.search(source)
    if match is None and _PUBMED_MENTION.search(source):
        return {"source": source, "pmid": None, "basis": BASIS_NONE,
                **_unknown(i18n.tr(
                    "la cita nombra PubMed pero su PMID no se lee: escribirlo como "
                    "«PMID 12345678»",
                    "the citation names PubMed but its PMID cannot be read: write it as "
                    "«PMID 12345678»",
                ))}
    if match is None:
        from_text = _from_text(f"{source} {text}")
        if from_text is not None:
            return {"source": source, "pmid": None, "basis": BASIS_TEXT, **from_text}
        return {"source": source, "pmid": None, "basis": BASIS_NONE,
                **_unknown(i18n.tr(
                    "sin PMID: no hay registro que catalogue el diseño, y el texto de la "
                    "cita no da señales suficientes",
                    "no PMID: there is no record cataloging the design, and the text of the "
                    "citation does not give enough signals",
                ))}
    pmid = match.group(1)
    record = _records().get(pmid)
    if record is None:
        return {"source": source, "pmid": pmid, "basis": BASIS_NONE,
                **_unknown(i18n.tr(
                    "registro no guardado: correr scripts/grade_sources.py",
                    "record not stored: run scripts/grade_sources.py",
                ))}
    graded = weave(signals_from_record(record["publication_types"], record["mesh"]))
    return {"source": source, "pmid": pmid, "retrieved": record["retrieved"],
            "basis": BASIS_RECORD, **graded}
