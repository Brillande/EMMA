# SPDX-License-Identifier: AGPL-3.0-or-later
"""Los informes técnicos de la NASA que cita EMMA, cotejados con su ficha en NTRS.

Por qué existe: cerca de cincuenta fichas del registro de evidencia (`data/evidence_refs.json`)
son informes de NTRS —resúmenes del HRP Investigators' Workshop, memorandos técnicos, informes de
evidencia, normas de JSC— y casi ninguna tiene DOI ni PMID. La comprobación de citas
(`evidence/citations.py`) solo sabía preguntar a Crossref, DataCite, doi.org, PubMed y
ClinicalTrials.gov: esas fichas quedaban sin comprobar, y su título, sus autores, su año y su
número de informe se habían copiado a mano. Aquí se cotejan con la ficha pública de NTRS
(`ntrs.nasa.gov/api/citations/<n>`, sin clave; spike en `spikes/spike_ntrs.py`).

Qué dice y qué no:
  * **Existencia**: `existe`, `no_encontrada_en_ntrs` o `no_resoluble` (los estados de
    `citations.py`). Un número que NTRS no tiene **no** es una cita inventada: NTRS es el único
    registro de esos números y retira o restringe fichas; se declara «no encontrada en NTRS» y
    nada más.
  * **Campos**: título, autores, año y número de informe, cada uno `coincide`, `difiere` (con lo
    que dice cada lado) o `no_comprobable` (con el motivo). Es un cotejo de lo que EMMA copió, no
    un juicio sobre la fuente: no toca la gradación de evidencia (`evidence/tier.py`), ni el
    registro, ni ninguna alerta. Una diferencia se enseña para que una persona la revise. Una
    diferencia ya revisada con el documento delante sale `explicada`, con el motivo
    (`EXPLAINED_DIFFERENCES`), y solo mientras los dos lados digan lo mismo que al revisarla.
  * Que NTRS tenga la ficha no dice nada de lo que el informe respalda: eso lo dice la nota de la
    ficha de EMMA, leída con el documento delante.

Red: solo por `core/egress.py` (propósito `citations`), y lo único que sale es el número de NTRS
del informe, público, en la ruta. Sin red (`EMMA_OFFLINE`, el modo nominal) se sirve la última
consulta guardada con su edad, o «no disponible»; nunca se inventa una ficha. Una ficha de NTRS
cambia poco: la consulta vale `FRESH_FOR` y, pasado ese tiempo, se repite si hay red.

Licencia y origen: este fichero no contiene código de Polaris.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

import httpx

from app.core import egress, i18n
from app.core.cache import CachedPayload, FileCache
from app.core.config import Settings, get_settings
from app.evidence import registry
from app.evidence.citations import EXISTS, NOT_IN_NTRS, NTRS_API, UNRESOLVABLE
from app.evidence.registry import EvidenceRef

# Una ficha de NTRS se corrige rara vez (parámetro de diseño, no de NASA). Pasado esto, con red, se
# vuelve a preguntar; sin red, se sirve igual con su edad.
FRESH_FOR = dt.timedelta(days=30)
PURPOSE = "citations"
NTRS_ID = re.compile(r"^\d{11}$")
_ID_IN_URL = re.compile(r"ntrs\.nasa\.gov/(?:api/)?citations/(\d{11})\b")
_ID_IN_SOURCE = re.compile(r"\bNTRS\s*:?\s*(\d{11})\b")
# Números de informe que una cita de EMMA puede escribir: NASA/TM-2017-219290, NASA-CR-168775,
# HRP-48032 Rev. B, JSC 20584 Rev C, JSC-CN-35749.
_REPORT_NUMBER = re.compile(
    r"\bNASA[/-](?:TM|TP|CR|CP|SP)-[0-9][0-9-]*[0-9]"
    r"|\b(?:HRP|JSC)[- ](?:CN-)?\d{4,6}(?:\s*Rev\.?\s*[A-Z](?![a-z]))?"
)

STATUS_DISPLAY = {
    EXISTS: "existe en NTRS",
    NOT_IN_NTRS: "no encontrada en NTRS",
    UNRESOLVABLE: "no disponible",
}
# El inglés, en una tabla hermana con las mismas claves: los estados no se traducen nunca.
STATUS_DISPLAY_EN = {
    EXISTS: "exists in NTRS",
    NOT_IN_NTRS: "not found in NTRS",
    UNRESOLVABLE: "not available",
}
MATCH, DIFFERS, UNCHECKABLE = "coincide", "difiere", "no_comprobable"
EXPLAINED = "explicada"

# Diferencias ya revisadas con el documento delante (la portada manda sobre los metadatos de NTRS).
# Cada una guarda lo que escribía cada lado al revisarla: si cualquiera de los dos cambia, la
# explicación deja de valer y el campo vuelve a salir como «difiere». Así no se esconde una
# diferencia nueva bajo una explicación vieja. Revisadas el 2026-11-11 en el PDF de cada ficha de
# NTRS (spike en `spikes/HALLAZGOS.md` §8).
EXPLAINED_DIFFERENCES: dict[str, dict[str, dict[str, Any]]] = {
    "jsc-20584-rev-c": {"title": {
        "emma": "Spacecraft Maximum Allowable Concentrations for Airborne Contaminants",
        "ntrs": "Spacecraft Maximum Allowable Concentrations for Airborne Contaminants: "
                "Revision C",
        "why": "NTRS añade «: Revision C» al título. La portada de JSC 20584 (p. 1 del PDF de "
               "NTRS) da el título sin él y «Revision C» en otra línea, como edición; EMMA la "
               "escribe en la cita («JSC 20584 Rev C»).",
    }},
    "ahmed-1981-high-density-foods": {
        "title": {
            "emma": "Experimental Study of High Density Foods",
            "ntrs": "The 1981 NASA ASEE Summer Faculty Fellowship Program, volume 1",
            "why": "NTRS 19820015234 es el volumen entero y EMMA cita un capítulo. El título es "
                   "el de la portada del capítulo (p. 2 del PDF del volumen, capa de texto del "
                   "escaneo): «EXPERIMENTAL STUDY OF HIGH DENSITY FOODS». NTRS tiene el capítulo "
                   "como ficha aparte, 19820015235 (sin PDF), con el título «Experimental study "
                   "of high density foods for the Space Operations Center», que no es el de la "
                   "portada.",
        },
        "authors": {
            "emma": ["Ahmed SM"],
            "ntrs": ["Robertson, N. G.", "Huang, C. J."],
            "why": "NTRS da los responsables del volumen; la autora del capítulo es Selina M. "
                   "Ahmed según su portada, y así la da también la ficha del capítulo en NTRS "
                   "(19820015235, «Ahmed, S. M.»).",
        },
    },
    "ntrs-20130000839": {"title": {
        "emma": "Nutritional Status Assessment (SMO 016E)",
        "ntrs": "Nutritional Status Assessment (SMO -16E)",
        "why": "NTRS lo escribe «SMO -16E»; el resumen (PDF de NTRS, una página) dice «NUTRITIONAL "
               "STATUS ASSESSMENT (SMO 016E)». Errata de NTRS.",
    }},
    "ntrs-20090007818": {"authors": {
        "emma": ["Feeback DL", "Cibuzar BR", "Milstead JR", "Pietrzyk RA", "Clarke MSF"],
        "ntrs": ["Feeback, Daniel L.", "Cibuzar, Branelle R.", "Milstead, Jeffery R.",
                 "Pietrzyk,, Robert A.", "Clark, Mark S.F."],
        "why": "NTRS lo escribe «Clark»; el póster (PDF de NTRS) firma «Mark S.F. Clarke, Ph.D.». "
               "Errata de NTRS.",
    }},
    "ntrs-20110008547": {"authors": {
        "emma": ["Rodriguez BR", "Broyan JL Jr"],
        "ntrs": ["Rodriquez, Branelle R.", "Broyan, James Lee, Jr."],
        "why": "NTRS lo escribe «Rodriquez»; la ponencia (PDF de NTRS, p. 1) firma «Branelle R. "
               "Rodriguez». Errata de NTRS.",
    }},
    "hrp-sleep-evidence-report-2016": {"title": {
        "emma": "Evidence Report: Risk of Performance Decrements and Adverse Health Outcomes "
                "Resulting from Sleep Loss, Circadian Desynchronization, and Work Overload",
        "ntrs": "Risk of Performance Decrements and Adverse Health Outcomes Resulting from Sleep "
                "Loss, Circadian Desynchronization, and Work Overload",
        "why": "NTRS omite «Evidence Report:»; la portada (p. 1 del PDF de NTRS) lo lleva "
               "delante del título.",
    }},
    "ntrs-20205011728": {"title": {
        "emma": "Clinical Decision Support – ConOps",
        "ntrs": "Clinical Decision Support - Concepts of Operation",
        "why": "NTRS desarrolla la abreviatura; la portada de las diapositivas (p. 1 del PDF de "
               "NTRS) dice «Clinical Decision Support – ConOps».",
    }},
}
# El inglés de cada motivo. Lo que va entre «» es lo que escribe cada lado y no se traduce; `emma`
# y `ntrs` son los valores que se comparan y tampoco.
i18n.en_many({
    EXPLAINED_DIFFERENCES["jsc-20584-rev-c"]["title"]["why"]: (
        "NTRS adds «: Revision C» to the title. The cover of JSC 20584 (p. 1 of the NTRS PDF) "
        "gives the title without it and «Revision C» on another line, as the edition; EMMA "
        "writes it in the citation («JSC 20584 Rev C»)."
    ),
    EXPLAINED_DIFFERENCES["ahmed-1981-high-density-foods"]["title"]["why"]: (
        "NTRS 19820015234 is the whole volume and EMMA cites a chapter. The title is that of "
        "the chapter's cover page (p. 2 of the volume's PDF, text layer of the scan): "
        "«EXPERIMENTAL STUDY OF HIGH DENSITY FOODS». NTRS has the chapter as a separate record, "
        "19820015235 (without a PDF), with the title «Experimental study of high density foods "
        "for the Space Operations Center», which is not the one on the cover page."
    ),
    EXPLAINED_DIFFERENCES["ahmed-1981-high-density-foods"]["authors"]["why"]: (
        "NTRS gives those responsible for the volume; the author of the chapter is Selina M. "
        "Ahmed according to its cover page, and the chapter's record in NTRS gives her as well "
        "(19820015235, «Ahmed, S. M.»)."
    ),
    EXPLAINED_DIFFERENCES["ntrs-20130000839"]["title"]["why"]: (
        "NTRS writes it «SMO -16E»; the abstract (NTRS PDF, one page) says «NUTRITIONAL STATUS "
        "ASSESSMENT (SMO 016E)». NTRS typo."
    ),
    EXPLAINED_DIFFERENCES["ntrs-20090007818"]["authors"]["why"]: (
        "NTRS writes it «Clark»; the poster (NTRS PDF) is signed «Mark S.F. Clarke, Ph.D.». "
        "NTRS typo."
    ),
    EXPLAINED_DIFFERENCES["ntrs-20110008547"]["authors"]["why"]: (
        "NTRS writes it «Rodriquez»; the paper (NTRS PDF, p. 1) is signed «Branelle R. "
        "Rodriguez». NTRS typo."
    ),
    EXPLAINED_DIFFERENCES["hrp-sleep-evidence-report-2016"]["title"]["why"]: (
        "NTRS omits «Evidence Report:»; the cover (p. 1 of the NTRS PDF) carries it before the "
        "title."
    ),
    EXPLAINED_DIFFERENCES["ntrs-20205011728"]["title"]["why"]: (
        "NTRS expands the abbreviation; the cover of the slides (p. 1 of the NTRS PDF) says "
        "«Clinical Decision Support – ConOps»."
    ),
})


@dataclass(frozen=True, slots=True)
class NtrsRecord:
    """Lo que EMMA coteja de una ficha de NTRS. Se guarda así en la caché, no la ficha entera."""

    ntrs_id: str
    title: str
    authors: tuple[str, ...]
    # Años de publicación y de congreso: una presentación del HRP IWS se fecha por cualquiera.
    years: tuple[int, ...]
    report_numbers: tuple[str, ...]
    sti_type: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ntrs_id": self.ntrs_id,
            "title": self.title,
            "authors": list(self.authors),
            "years": list(self.years),
            "report_numbers": list(self.report_numbers),
            "sti_type": self.sti_type,
            "url": f"https://ntrs.nasa.gov/citations/{self.ntrs_id}",
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> NtrsRecord:
        return cls(
            ntrs_id=str(raw["ntrs_id"]),
            title=str(raw["title"]),
            authors=tuple(str(name) for name in raw["authors"]),
            years=tuple(int(year) for year in raw["years"]),
            report_numbers=tuple(str(number) for number in raw["report_numbers"]),
            sti_type=raw.get("sti_type"),
        )


def _year(value: Any) -> int | None:
    match = re.match(r"(\d{4})-", str(value or ""))
    return int(match.group(1)) if match else None


def parse_record(raw: Any) -> NtrsRecord:
    """La ficha de `GET /api/citations/<n>`. Sin número o sin título no es una ficha: ValueError."""
    if not isinstance(raw, dict) or not str(raw.get("id") or "").isdigit():
        raise ValueError("la respuesta de NTRS no trae el número de la ficha")
    title = str(raw.get("title") or "").strip()
    if not title:
        raise ValueError("la ficha de NTRS no trae título")
    authors = tuple(
        str(item["meta"]["author"]["name"])
        for item in sorted(raw.get("authorAffiliations") or [], key=lambda a: a.get("sequence", 0))
        if isinstance(item, dict) and (item.get("meta") or {}).get("author", {}).get("name")
    )
    dates = [item.get("publicationDate") for item in raw.get("publications") or []]
    for meeting in raw.get("meetings") or []:
        dates += [meeting.get("startDate"), meeting.get("endDate")]
    years = tuple(sorted({year for year in map(_year, dates) if year is not None}))
    numbers: list[str] = []
    for number in [*(raw.get("reportNumbers") or []), *(raw.get("otherReportNumbers") or [])]:
        # NTRS repite cada número con el prefijo «Report Number: ».
        clean = re.sub(r"^Report Number:\s*", "", str(number)).strip()
        if clean and clean not in numbers:
            numbers.append(clean)
    return NtrsRecord(
        ntrs_id=str(raw["id"]), title=title, authors=authors, years=years,
        report_numbers=tuple(numbers), sti_type=raw.get("stiType"),
    )


@dataclass(frozen=True, slots=True)
class Lookup:
    """Lo que se sabe de un número de NTRS ahora, con de cuándo es."""

    ntrs_id: str
    status: str
    record: NtrsRecord | None
    detail: str
    payload: CachedPayload | None  # None: no hay consulta, ni nueva ni guardada

    def to_dict(self) -> dict[str, Any]:
        return {
            "ntrs_id": self.ntrs_id,
            "status": self.status,
            "status_display": i18n.tr(
                STATUS_DISPLAY[self.status], STATUS_DISPLAY_EN[self.status]
            ),
            "detail": self.detail,
            "record": self.record.to_dict() if self.record else None,
            "fetched_at": self.payload.fetched_at.isoformat() if self.payload else None,
            "age_seconds": self.payload.age_seconds if self.payload else None,
            "age": self.payload.describe_age() if self.payload else None,
            "from_cache": self.payload.from_cache if self.payload else None,
        }


class NtrsClient:
    """Fichas de NTRS por número, con caché y sin red como modo nominal."""

    def __init__(self, settings: Settings | None = None, cache: FileCache | None = None) -> None:
        self.settings = settings or get_settings()
        self.cache = cache or FileCache(self.settings.cache_dir / "ntrs")

    def lookup(self, ntrs_id: str, *, network: bool = True) -> Lookup:
        """La ficha de un número. `network=False`: solo lo guardado (una lectura que no espera)."""
        if not NTRS_ID.match(ntrs_id):
            raise ValueError(f"{ntrs_id!r} no es un número de NTRS (11 cifras)")
        key = f"ntrs:{ntrs_id}"
        cached = self.cache.get(key)
        if cached is not None and (
            not network or self.settings.offline or not cached.is_stale(FRESH_FOR)
        ):
            return self._from_payload(ntrs_id, cached)
        if not network or self.settings.offline:
            return Lookup(
                ntrs_id, UNRESOLVABLE, None,
                i18n.tr(
                    "sin red y sin consulta guardada: no disponible",
                    "offline and no saved lookup: not available",
                ) if self.settings.offline
                else i18n.tr("sin consulta guardada todavía", "no saved lookup yet"),
                None,
            )
        try:
            data = self._fetch(ntrs_id)
        except (httpx.HTTPError, ValueError) as exc:
            if cached is not None:
                # Lo último que se supo, con su edad, es mejor que nada; el fallo se dice.
                stale = self._from_payload(ntrs_id, cached)
                return Lookup(
                    ntrs_id, stale.status, stale.record,
                    i18n.tr(
                        f"{stale.detail}; la consulta de ahora falló ({_reason(exc)})",
                        f"{stale.detail}; the lookup just now failed ({_reason(exc)})",
                    ),
                    cached,
                )
            return Lookup(
                ntrs_id, UNRESOLVABLE, None,
                i18n.tr(
                    f"NTRS no respondió ({_reason(exc)})",
                    f"NTRS did not answer ({_reason(exc)})",
                ),
                None,
            )
        return self._from_payload(ntrs_id, self.cache.put(key, data, source="NTRS"))

    def _fetch(self, ntrs_id: str) -> dict[str, Any]:
        response = egress.get(self.settings, PURPOSE, f"{NTRS_API}/{ntrs_id}")
        if response.status_code == 404:
            return {"found": False}
        response.raise_for_status()
        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError("NTRS respondió sin JSON") from exc
        return {"found": True, "record": parse_record(body).to_dict()}

    @staticmethod
    def _from_payload(ntrs_id: str, payload: CachedPayload) -> Lookup:
        data = payload.data
        when = i18n.tr("consulta guardada ", "saved lookup ") if payload.from_cache else ""
        if data.get("found"):
            return Lookup(
                ntrs_id, EXISTS, NtrsRecord.from_dict(data["record"]),
                i18n.tr(
                    f"{when}de NTRS ({payload.describe_age()})",
                    f"{when}from NTRS ({payload.describe_age()})",
                ).strip(),
                payload,
            )
        return Lookup(
            ntrs_id, NOT_IN_NTRS, None,
            i18n.tr(
                f"NTRS no tiene ese número ({when}{payload.describe_age()}). No prueba que la "
                "cita sea inventada: NTRS retira o restringe fichas",
                f"NTRS does not have that number ({when}{payload.describe_age()}). It does not "
                "prove that the citation is made up: NTRS withdraws or restricts records",
            ),
            payload,
        )


def _reason(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return str(exc)[:120] or type(exc).__name__


# --- Cotejo con la ficha de EMMA -----------------------------------------------------------------


def ntrs_id_of(ref: EvidenceRef) -> str | None:
    """El número de NTRS de una ficha: el de su URL, o el que escribe su cita."""
    for text, pattern in ((ref.url or "", _ID_IN_URL), (ref.source, _ID_IN_SOURCE)):
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^0-9a-z]+", " ", ascii_only.casefold()).split())


def _surname(author: str) -> str | None:
    """El apellido de un autor como lo escribe EMMA («Myers JG Jr», «De Dios YE»)."""
    tokens = [token for token in author.replace(",", " ").split() if token]
    while tokens and (
        tokens[-1].rstrip(".") in {"Jr", "Sr", "II", "III"}
        or re.fullmatch(r"[A-Z]{1,3}\.?", tokens[-1])
    ):
        tokens.pop()
    return _plain(" ".join(tokens)) or None


def _compact(number: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", number.upper())


def _field(state: str, emma: Any, ntrs: Any, detail: str = "") -> dict[str, Any]:
    return {"state": state, "emma": emma, "ntrs": ntrs, "detail": detail}


def _not_in_ntrs(missing: list[str]) -> str:
    """Lo que EMMA escribe y NTRS no da, con sus nombres; nada si no falta nada."""
    if not missing:
        return ""
    names = ", ".join(missing)
    return i18n.tr(f"no están en NTRS: {names}", f"not in NTRS: {names}")


def compare(ref: EvidenceRef, record: NtrsRecord) -> dict[str, dict[str, Any]]:
    """Título, autores, año y número de informe: lo que escribe EMMA frente a lo que da NTRS."""
    fields: dict[str, dict[str, Any]] = {}
    fields["title"] = _field(
        MATCH if _plain(ref.title) == _plain(record.title) else DIFFERS, ref.title, record.title
    )

    cited = [name for name in ref.authors if _plain(name) not in {"et al", ""}]
    ntrs_names = [f" {_plain(name)} " for name in record.authors]
    if not cited:
        fields["authors"] = _field(
            UNCHECKABLE, [], list(record.authors),
            i18n.tr(
                "la ficha de EMMA no escribe autores",
                "EMMA's reference card writes no authors",
            ),
        )
    elif not record.authors:
        fields["authors"] = _field(
            UNCHECKABLE, cited, [], i18n.tr("NTRS no da autores", "NTRS gives no authors")
        )
    else:
        missing = [
            name for name in cited
            if not any(f" {_surname(name)} " in ntrs for ntrs in ntrs_names)
        ]
        fields["authors"] = _field(
            DIFFERS if missing else MATCH, cited, list(record.authors),
            _not_in_ntrs(missing),
        )

    emma_year = _year(f"{ref.date}-") if ref.date else None
    if emma_year is None:
        fields["year"] = _field(
            UNCHECKABLE, ref.date, list(record.years),
            i18n.tr("la ficha de EMMA no da fecha", "EMMA's reference card gives no date"),
        )
    elif not record.years:
        fields["year"] = _field(
            UNCHECKABLE, emma_year, [],
            i18n.tr(
                "NTRS no da fecha de publicación ni de congreso",
                "NTRS gives no publication or meeting date",
            ),
        )
    else:
        fields["year"] = _field(
            MATCH if emma_year in record.years else DIFFERS, emma_year, list(record.years)
        )

    numbers = list(dict.fromkeys(m.group(0).strip() for m in _REPORT_NUMBER.finditer(ref.source)))
    if not numbers:
        fields["report_number"] = _field(
            UNCHECKABLE, [], list(record.report_numbers),
            i18n.tr(
                "la cita de EMMA no escribe número de informe",
                "EMMA's citation writes no report number",
            ),
        )
    else:
        known = {_compact(number) for number in record.report_numbers}
        missing = [number for number in numbers if _compact(number) not in known]
        fields["report_number"] = _field(
            DIFFERS if missing else MATCH, numbers, list(record.report_numbers),
            _not_in_ntrs(missing),
        )
    return _explain(ref.id, fields)


def _explain(ref_id: str, fields: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Marca `explicada` la diferencia ya revisada, solo si los dos lados siguen como entonces."""
    for name, explanation in EXPLAINED_DIFFERENCES.get(ref_id, {}).items():
        field = fields.get(name)
        if (
            field is not None and field["state"] == DIFFERS
            and field["emma"] == explanation["emma"] and field["ntrs"] == explanation["ntrs"]
        ):
            fields[name] = _field(
                EXPLAINED, field["emma"], field["ntrs"], i18n.loc(explanation["why"])
            )
    return fields


def check_reference(
    ref: EvidenceRef, client: NtrsClient, *, network: bool = True
) -> dict[str, Any]:
    """Una ficha del registro frente a NTRS. La ficha sin número de NTRS no se comprueba aquí."""
    ntrs_id = ntrs_id_of(ref)
    if ntrs_id is None:
        raise ValueError(f"{ref.id}: la ficha no cita un número de NTRS")
    lookup = client.lookup(ntrs_id, network=network)
    fields = compare(ref, lookup.record) if lookup.record else None
    return {
        "ref_id": ref.id,
        **lookup.to_dict(),
        "fields": fields,
        "differs": sorted(name for name, f in (fields or {}).items() if f["state"] == DIFFERS),
        "explained": sorted(
            name for name, f in (fields or {}).items() if f["state"] == EXPLAINED
        ),
    }


def ntrs_references() -> list[EvidenceRef]:
    """Las fichas del registro que citan un informe de NTRS, en el orden del registro."""
    return [ref for ref in registry.registry().values() if ntrs_id_of(ref) is not None]


def check_all(client: NtrsClient, *, network: bool) -> dict[str, Any]:
    """Todas las fichas con número de NTRS, con el recuento por estado y las que difieren."""
    items = [check_reference(ref, client, network=network) for ref in ntrs_references()]
    counts: dict[str, int] = {state: 0 for state in STATUS_DISPLAY}
    for item in items:
        counts[item["status"]] += 1
    return {
        "references": items,
        "count": len(items),
        "by_status": counts,
        "with_differences": [item["ref_id"] for item in items if item["differs"]],
        "with_explained_differences": [item["ref_id"] for item in items if item["explained"]],
        "offline": client.settings.offline,
        "scope": i18n.tr(
            "Coteja lo que EMMA copió de cada informe (título, autores, año, número) con su ficha "
            "pública en NTRS. No gradúa la evidencia ni dice qué respalda el informe; «no "
            "encontrada en NTRS» no significa cita inventada.",
            "It compares what EMMA copied from each report (title, authors, year, number) with "
            "its public record in NTRS. It does not grade the evidence or say what the report "
            "supports; «not found in NTRS» does not mean a made-up citation.",
        ),
    }
