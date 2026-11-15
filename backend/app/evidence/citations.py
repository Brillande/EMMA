# SPDX-License-Identifier: AGPL-3.0-or-later
"""Que cada cita de EMMA exista: DOI, PMID y NCT, comprobados contra su registro.

Por qué existe: EMMA cita literatura en el código (protocolos, evidencia), en los datos (el
manifiesto de ecografías) y en la documentación de cumplimiento. Una cita mal copiada o
inventada es exactamente el error que este proyecto dice no cometer, y a mano no se revisa: son
decenas. CLAUDE.md: "si no encuentras respaldo, se marca como tal — no se inventa una cita".

Adaptador de `polaris/tools/verifica_citas.py`, de la copia literal de Polaris, sin modificarla
(commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the
Protocol»; se carga con `app.polaris.load`). Del original, sin tocar: `clean_doi()`
(`_limpia_doi()`), los cuatro estados y el orden de comprobación por registro (Crossref → DataCite
→ doi.org para un DOI, porque un 404 de Crossref no prueba nada; eutils para PMID;
ClinicalTrials.gov para NCT).

Siguen ADAPTADAS a mano de `tools/verifica_citas.py` @ 7bf47257 (el commit que se copió primero;
cambios AGPL §5a, docs/polaris-divergencias.md):
  * `classify()`: busca el DOI en la cadena original antes de recortarla. `clasifica()` recorta
    primero los paréntesis de los extremos y pierde el ")" final de un DOI con paréntesis
    emparejados: "doi:10.1234/abcd(12)" → "10.1234/abcd(12". Lo demuestra
    `test_classify_as_polaris_does[doi:10.1234/abcd(12)-...]`.
  * Las comprobaciones con red usan httpx con un cliente inyectable, no `curl`: así se prueban
    sin red (invariante 3). La que sí sale a la red la ejecuta `tests/test_citations_live.py`
    (marcado `live`), nunca la aplicación. Sin arXiv: `verify()` devuelve un identificador de
    arXiv como no comprobable. EMMA cita un solo preprint, junto a la radiación y rotulado como
    tal (`lowe-2025-sep-nowcasting-mars`, `evidence/radiation_read.py`); su ficha lleva el DOI
    que arXiv le da (10.48550), que se comprueba como cualquier DOI.
  * `find_identifiers()` es de EMMA: todos los identificadores de un texto largo.
  * NTRS es de EMMA (Polaris no lo comprueba): un informe técnico de la NASA citado por su
    número de NTRS (`NTRS 20200000567`, `ntrs.nasa.gov/citations/20200000567`) se busca en
    `ntrs.nasa.gov/api/citations/<n>`. Un 404 de NTRS **no** es `no_existe`: NTRS es el único
    registro de esos números y retira o restringe fichas (exportación controlada, cambios de
    distribución), así que «no está» no prueba «nunca existió». Sale `no_encontrada_en_ntrs`,
    que no acusa; Polaris (`_existencia_citas`) lo trata como no confirmado, no como fabricado.
    El cotejo de título, autores, año y número de informe con la ficha de EMMA, con caché y sin
    red, está en `evidence/ntrs.py`.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass

import httpx

from app import polaris

EXISTS = "existe"
NOT_FOUND = "no_existe"  # el registro confirma que no existe: cita fabricada o mal copiada
UNRESOLVABLE = "no_resoluble"  # red caída o registro mudo: no se acusa sin prueba
UNPARSEABLE = "no_parseable"
# NTRS no tiene el número: no se acusa (ver arriba), pero tampoco se confirma.
NOT_IN_NTRS = "no_encontrada_en_ntrs"
NTRS_API = "https://ntrs.nasa.gov/api/citations"


def clean_doi(doi: str) -> str:
    """`_limpia_doi()` del original: markdown y puntuación fuera; el `)` final, solo desparejado."""
    return str(polaris.load("verifica_citas")._limpia_doi(doi))


def classify(raw: str) -> tuple[str, str]:
    """(tipo, id) de una cadena que es una cita. De Polaris `clasifica()`.

    tipo ∈ {doi, pmid, nct, ntrs, arxiv, desconocido}.
    """
    # El DOI se busca en la cadena ORIGINAL: recortar antes los paréntesis de los extremos se
    # comía el ")" final de un DOI con paréntesis emparejados que cierra la cita. Error heredado
    # de Polaris, destapado por una campaña de mutantes (`tests/mutants/citations.json`).
    match = re.search(r"10\.\d{4,9}/\S+", raw or "")
    if match:
        return "doi", clean_doi(match.group(0))
    text = (raw or "").strip().strip(".,;()[]<>\"' ")
    low = text.lower()
    match = re.search(r"(NCT\d{8})", text, re.I)
    if match:
        return "nct", match.group(1).upper()
    match = re.search(r"(?:\bntrs\b[:\s]*|ntrs\.nasa\.gov/(?:api/)?citations/)(\d{11})\b", low)
    if match:
        return "ntrs", match.group(1)
    match = re.match(r"pmid[:\s]*([0-9]{1,8})$", low)
    if match:
        return "pmid", match.group(1)
    match = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", text)
    if ("arxiv" in low or (match and "/" not in text and len(text) <= 16)) and match:
        return "arxiv", match.group(1) + (match.group(2) or "")
    if re.fullmatch(r"[0-9]{1,8}", text):
        return "pmid", text
    return "desconocido", text


_IN_TEXT = (
    # Un DOI puede llevar paréntesis emparejados (el año, en algunas revistas); un paréntesis suelto
    # o unas comillas latinas cierran la cita que lo rodea, no el DOI.
    ("doi", re.compile(r"10\.\d{4,9}/[^\s()\]>,;«»]+(?:\([^\s()]*\)[^\s()\]>,;«»]*)*")),
    ("pmid", re.compile(r"\bPMID:?\s*(\d{5,9})\b")),
    ("nct", re.compile(r"\b(NCT\d{8})\b", re.I)),
    # Los números de NTRS tienen 11 cifras (año + 7). Con la palabra o en su URL: once cifras
    # sueltas en un documento no son una cita.
    ("ntrs", re.compile(r"\bNTRS:?\s*(\d{11})\b")),
    ("ntrs", re.compile(r"ntrs\.nasa\.gov/(?:api/)?citations/(\d{11})\b")),
)


def find_identifiers(text: str) -> set[tuple[str, str]]:
    """Todos los identificadores de un texto largo. Un PMID sin la palabra "PMID" no se toma:
    en un documento, un número suelto es una cifra, no una cita."""
    found: set[tuple[str, str]] = set()
    for kind, pattern in _IN_TEXT:
        for match in pattern.finditer(text):
            value = match.group(1) if pattern.groups else match.group(0)
            found.add((kind, clean_doi(value) if kind == "doi" else value.upper()))
    return found


@dataclass(frozen=True)
class Verdict:
    kind: str
    identifier: str
    status: str
    detail: str
    registry: str


def _get(client: httpx.Client, url: str) -> tuple[int | None, str]:
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        return None, str(exc)[:80]
    return response.status_code, response.text


def check_doi(client: httpx.Client, doi: str) -> Verdict:
    """Crossref → DataCite → doi.org. Solo NOT_FOUND si los tres dicen que no."""
    code, body = _get(client, f"https://api.crossref.org/works/{doi}")
    if code == 200:
        return Verdict("doi", doi, EXISTS, _title(body, "crossref"), "Crossref")
    if code != 404:
        return Verdict("doi", doi, UNRESOLVABLE, f"Crossref no respondió ({code})", "Crossref")
    code, body = _get(client, f"https://api.datacite.org/dois/{doi}")
    if code == 200:
        return Verdict("doi", doi, EXISTS, _title(body, "datacite"), "DataCite")
    if code != 404:
        return Verdict("doi", doi, UNRESOLVABLE, f"DataCite no respondió ({code})", "DataCite")
    code, body = _get(client, f"https://doi.org/api/handles/{doi}")
    try:
        response_code = json.loads(body).get("responseCode") if code in (200, 404) else None
    except ValueError:
        response_code = None
    if response_code == 1:
        return Verdict("doi", doi, EXISTS, "(registrado en doi.org)", "doi.org")
    if response_code == 100:
        return Verdict("doi", doi, NOT_FOUND, "no está en Crossref, DataCite ni doi.org", "doi.org")
    return Verdict("doi", doi, UNRESOLVABLE, f"doi.org no respondió ({code})", "doi.org")


def check_pmid(client: httpx.Client, pmid: str) -> Verdict:
    code, body = _get(
        client,
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        f"?db=pubmed&retmode=json&id={pmid}",
    )
    if code != 200:
        return Verdict("pmid", pmid, UNRESOLVABLE, f"eutils no respondió ({code})", "PubMed")
    try:
        result = json.loads(body).get("result", {})
    except ValueError:
        return Verdict("pmid", pmid, UNRESOLVABLE, "respuesta no JSON", "PubMed")
    record = result.get(pmid)
    if isinstance(record, dict) and not record.get("error"):
        return Verdict("pmid", pmid, EXISTS, str(record.get("title") or ""), "PubMed")
    return Verdict("pmid", pmid, NOT_FOUND, "PMID inexistente", "PubMed")


def check_nct(client: httpx.Client, nct: str) -> Verdict:
    code, body = _get(client, f"https://clinicaltrials.gov/api/v2/studies/{nct}")
    if code == 200:
        return Verdict("nct", nct, EXISTS, "", "ClinicalTrials.gov")
    if code == 404:
        return Verdict("nct", nct, NOT_FOUND, "ensayo inexistente", "ClinicalTrials.gov")
    return Verdict("nct", nct, UNRESOLVABLE, f"no respondió ({code})", "ClinicalTrials.gov")


def check_ntrs(client: httpx.Client, ntrs_id: str) -> Verdict:
    """La ficha de NTRS de un número. 404: `no_encontrada_en_ntrs`, nunca `no_existe`."""
    code, body = _get(client, f"{NTRS_API}/{ntrs_id}")
    if code == 200:
        try:
            title = str(json.loads(body).get("title") or "")
        except (ValueError, AttributeError):
            return Verdict("ntrs", ntrs_id, UNRESOLVABLE, "respuesta no JSON", "NTRS")
        return Verdict("ntrs", ntrs_id, EXISTS, title, "NTRS")
    if code == 404:
        return Verdict("ntrs", ntrs_id, NOT_IN_NTRS, "NTRS no tiene ese número", "NTRS")
    if code == 400:
        return Verdict("ntrs", ntrs_id, UNPARSEABLE, "NTRS no lo lee como número", "NTRS")
    return Verdict("ntrs", ntrs_id, UNRESOLVABLE, f"NTRS no respondió ({code})", "NTRS")


def verify(
    client: httpx.Client, identifiers: Iterable[tuple[str, str]], pause: float = 0.0
) -> list[Verdict]:
    """`pause` entre peticiones: NCBI responde 429 a más de 3 por segundo sin clave."""
    checks = {"doi": check_doi, "pmid": check_pmid, "nct": check_nct, "ntrs": check_ntrs}
    verdicts: list[Verdict] = []
    for kind, identifier in sorted(identifiers):
        check = checks.get(kind)
        if check is None:
            verdicts.append(Verdict(kind, identifier, UNPARSEABLE, "", ""))
            continue
        verdicts.append(check(client, identifier))
        time.sleep(pause)
    return verdicts


def _title(body: str, registry: str) -> str:
    try:
        data = json.loads(body)
    except ValueError:
        return ""
    if registry == "crossref":
        titles = data.get("message", {}).get("title") or [""]
        return str(titles[0])
    titles = data.get("data", {}).get("attributes", {}).get("titles") or []
    return str((titles[0] or {}).get("title", "")) if titles else ""
