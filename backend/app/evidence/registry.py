"""Registro único de referencias: una ficha por fuente, y todos la citan por su identificador.

Por qué existe: la misma fuente estaba escrita en varios sitios, cada uno con su forma —los
riesgos del HRP y los estudios de OSDR en `evidence/links.py`, los artículos del CO2 en
`analysis/context.py`, el `protocol_ref` de cada contramedida en `data/countermeasures.json`—
y ninguna decía de cuándo es, qué clase de documento es ni si lo que mide es una persona o un
ratón. La especificación del equipo (§3, EvidenceRef) pide `id`, `title`, `url/doi`,
`organization`, `date`, `evidence_type` y `notes`; su principio de §2, no mezclar humanos,
animales y análogos sin conservar de dónde sale cada cosa. Con varias copias, corregir una
salvedad dejaba a las demás diciendo lo de antes.

Qué guarda y qué no:
  * La ficha (`data/evidence_refs.json`) dice qué ES la fuente. **Por qué se cita** —la
    relevancia— lo dice quien cita, porque la misma página respalda cosas distintas en dos
    contramedidas. Eso es `Citation`: una ficha más su relevancia.
  * `evidence_context` usa el enumerado de las observaciones (`EvidenceContext`): es el
    ENTORNO del estudio, y no dice la especie: un ratón en la ISS es `iss`. Por eso la ficha
    lleva además `population`, y OSD-288 sale `iss` + `animal`, nunca "astronautas".
  * `evidence_type` es la clase de documento (conjunto de datos, informe de evidencia,
    artículo...). El DISEÑO del estudio (cohorte, ensayo, modelo animal) no se escribe aquí:
    lo calcula `evidence/tier.py` desde el registro de PubMed guardado, y sale en `grade`.

NO SE RELLENA DE MEMORIA. Un campo que no esté escrito ya en el repositorio es `null`, y la
ficha resuelta lo lista en `unverified` para que alguien lo complete con la fuente delante.
Si al leerla resulta que el campo no procede (una norma no tiene entorno de estudio), se
anota en `not_applicable` y deja de contar como pendiente. Si procede pero el enumerado no
tiene un valor que lo cubra (un estudio que junta historias de siete programas de vuelo, de la
ISS y de fuera), se anota en `outside_enum` y `notes` dice por qué: es un campo leído, no un
hueco, y forzarlo al valor más parecido sería afirmar algo que la fuente no dice. Una fecha
plausible que nadie leyó es peor que un hueco declarado.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from app.core import i18n
from app.evidence.tier import grade
from app.ingest.fhir import EvidenceContext

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "evidence_refs.json"

# Clase de documento, con el rótulo que ve la tripulación (la interfaz no lo redacta).
EVIDENCE_TYPES: dict[str, str] = {
    "dataset": "conjunto de datos",
    "evidence_report": "informe de evidencia",
    "hrp_risk": "riesgo del HRP",
    "medical_condition_sheet": "ficha de condición médica",
    "journal_article": "artículo de revista",
    "technical_brief": "resumen técnico de norma",
    "agency_page": "página de agencia",
    "research_task": "tarea de investigación",
    # Documentos del marco de NASA leídos el 2026-10-13: ninguno es un estudio.
    "program_document": "documento de programa",
    "presentation": "presentación de congreso",
    "technical_memorandum": "memorando técnico",
    "technical_standard": "norma técnica",
    # Un manuscrito enviado a una revista y aún sin revisión por pares (decimosexta ronda, E8: el
    # fin del refugio ante un evento solar). Llamarlo «artículo de revista» diría que pasó la
    # revisión, y no la ha pasado.
    "preprint": "preprint sin revisión por pares",
}
i18n.en_many({
    EVIDENCE_TYPES["dataset"]: "dataset",
    EVIDENCE_TYPES["evidence_report"]: "evidence report",
    EVIDENCE_TYPES["hrp_risk"]: "HRP risk",
    EVIDENCE_TYPES["medical_condition_sheet"]: "medical condition record",
    EVIDENCE_TYPES["journal_article"]: "journal article",
    EVIDENCE_TYPES["technical_brief"]: "technical brief of a standard",
    EVIDENCE_TYPES["agency_page"]: "agency page",
    EVIDENCE_TYPES["research_task"]: "research task",
    EVIDENCE_TYPES["program_document"]: "program document",
    EVIDENCE_TYPES["presentation"]: "conference presentation",
    EVIDENCE_TYPES["technical_memorandum"]: "technical memorandum",
    EVIDENCE_TYPES["technical_standard"]: "technical standard",
    # Igual que en castellano: no decir «journal article» de lo que no pasó la revisión.
    EVIDENCE_TYPES["preprint"]: "preprint, not peer-reviewed",
})
# Sobre quién se midió. No hay valor por defecto: sin respaldo en el texto, `null`.
POPULATIONS: dict[str, str] = {
    "human": "humano",
    "animal": "animal",
    "human_and_animal": "humano y animal",
}
# «animal» se escribe igual en los dos idiomas: no se registra.
i18n.en_many({
    POPULATIONS["human"]: "human",
    POPULATIONS["human_and_animal"]: "human and animal",
})
# Una fuente que no es solo de personas lleva salvedad de alcance: no se cita sin decirlo.
NON_HUMAN = frozenset({"animal", "human_and_animal"})
UNCLASSIFIED = "sin clasificar"
NOT_APPLICABLE = "no aplica"
i18n.en_many({UNCLASSIFIED: "unclassified", NOT_APPLICABLE: "not applicable"})
# Los campos de §3 (y la población) que pueden faltar, con el nombre que se enseña.
OPTIONAL_FIELDS: dict[str, str] = {
    "url": "URL",
    "doi": "DOI",
    "organization": "organización",
    "date": "fecha",
    "evidence_type": "tipo de evidencia",
    "evidence_context": "entorno del estudio",
    "population": "población",
}
# «URL» y «DOI» se escriben igual en los dos idiomas.
i18n.en_many({
    OPTIONAL_FIELDS["organization"]: "organization",
    OPTIONAL_FIELDS["date"]: "date",
    OPTIONAL_FIELDS["evidence_type"]: "evidence type",
    OPTIONAL_FIELDS["evidence_context"]: "study setting",
    OPTIONAL_FIELDS["population"]: "population",
})
# Los campos con enumerado propio: solo de ellos se puede decir que la fuente cae fuera.
ENUMERATED_FIELDS = frozenset({"evidence_type", "evidence_context", "population"})
OUTSIDE_ENUM = "fuera del enumerado"
i18n.en(OUTSIDE_ENUM, "outside the enumeration")
_REQUIRED = frozenset({"id", "title", "source", "pmid", "notes", *OPTIONAL_FIELDS})
_KEYS = _REQUIRED | {
    "not_applicable", "outside_enum", "authors", "named_people", "affiliations",
    "named_organizations",
}
# Personas de una ficha (`GET /api/people`, `evidence/people.py`). Son personas reales: solo
# entra lo que la ficha ya escribe, copiado letra a letra —quien firma, como lo escribe la cita o
# la nota; quien la fuente nombra, con el cargo que le da— y nunca un dato de contacto. Un nombre
# es letras, espacios y la puntuación de un nombre; sin cifras ni arroba, no cabe un teléfono ni
# un correo. Quien firma va sin coma (una coma juntaría dos firmantes en uno: «Basner M, Dinges
# DF»); quien la fuente nombra admite una, para la forma «Apellido, Nombre». Un cargo no lleva
# arroba, enlace ni una tira de nueve cifras o más (un teléfono; un intervalo de años, sí).
_NAME_PART = r"[^\W\d_]+(?:[ .'’-]+[^\W\d_]+)*\.?"
_PERSON_NAME = re.compile(_NAME_PART)
_NAMED_NAME = re.compile(rf"{_NAME_PART}(?:, {_NAME_PART})?")
_CONTACT = re.compile(r"@|https?:|www\.|(?:\d[\s()+./-]?){9,}")
_NAMED_KEYS = frozenset({"name", "role"})
# Entre el nombre y el cargo de quien la fuente nombra, en la nota, solo puntuación: «Kerry Lee,
# radiation system manager for Orion» o «investigador principal: Dinges, David». Así el cargo es
# el que la nota da a esa persona, no uno que la nota da a otra.
_NAME_ROLE_GAP = r"[\s,:;—–-]{1,4}"
# Separador de una ficha con más de una organización («KBRwyle / NASA Johnson Space Center»).
ORG_SEPARATOR = " / "
# La afiliación de una persona de la ficha (decimonovena ronda, U4): la organización que el
# documento escribe junto a su nombre, en su fecha. Es por persona porque la de la ficha
# (`organization`) es la de la fuente entera y, en un artículo, casi siempre solo la del primero
# que firma; la conversación de ideación daba una por autor para Krihak et al. 2020 y EMMA no
# podía decirlas sin inventar. Misma regla que un cargo: nombre y organización escritos juntos
# en la nota, y la persona ya en la ficha (firma o nombrada).
_AFFILIATION_KEYS = frozenset({"name", "organization"})
# Una organización que la fuente nombra sin darla (Teledyne Brown, CASIS…), con el papel que le da
# la fuente en su fecha: la que sostiene la ficha es `organization`; estas son las que la ficha
# menciona. El nombre admite cifras y «&» (una razón social), nunca un dato de contacto.
_ORGANIZATION_NAME = re.compile(r"[^\W_](?:[\w .,&'’()/-]*[\w.)])?")


def _written(name: str, text: str) -> bool:
    """El nombre está en el texto como nombre entero: ni dentro de otra palabra («Lee» en
    «Leeds») ni como trozo de otro firmante («Myers J» dentro de «Myers JG»)."""
    return re.search(rf"(?<![^\W_]){re.escape(name)}(?![^\W_])", text) is not None


def _named_with_role(name: str, role: str, notes: str) -> bool:
    """La nota escribe el nombre junto a su cargo, en cualquiera de los dos órdenes."""
    a, b = re.escape(name), re.escape(role)
    pair = rf"(?<![^\W_])(?:{a}{_NAME_ROLE_GAP}{b}|{b}{_NAME_ROLE_GAP}{a})(?![^\W_])"
    return re.search(pair, notes) is not None
# El entorno es el de las observaciones: aquí no se define otro enumerado.
_CONTEXTS = frozenset(str(item) for item in EvidenceContext)
_ID = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
# ISO 8601 con la precisión que dé la fuente: año, año-mes o fecha completa.
_DATE = re.compile(r"\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?")
_PMID = re.compile(r"\d{5,9}")
# Cada lectura que anota una nota lleva su fecha en ISO 8601 («Leída el 2026-10-13»): es la
# convención del registro, lo leído se fecha. La primera fecha marca dónde empieza la bitácora.
_READ_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
# Un punto tras una inicial o una abreviatura («J. Smith», «et al.», «Rev. B») no acaba frase: si
# cortara, media frase de la bitácora saldría a la vista como alcance. Ante la duda no se corta
# ahí, y lo que quede detrás va plegado: el error posible es plegar de más, nunca enseñar de menos.
_ABBREVIATION = re.compile(r"(?:\b[^\W\d_]{1,2}|\b(?:Rev|Vol|Fig|Dra|Sra))$")


def _lead(notes: str) -> str | None:
    """Las frases de la nota anteriores a la primera que fecha una lectura, tal cual.

    Por qué existe: la nota de una ficha junta dos cosas —qué mide la fuente y la bitácora de
    cuándo y qué se leyó de ella— y, junto a una hipótesis de cabina, la consola de tripulación la
    enseñaba entera. Lo que se pone delante es lo que la nota dice antes de leer nada: un prefijo
    literal, cortado en un fin de frase, sin una palabra de EMMA. Un punto dentro de comillas
    angulares o de un paréntesis no corta (una cita o «1.0.0» no son fin de frase), ni uno tras
    una inicial o una abreviatura. `None` si la nota empieza ya por una lectura; la nota entera si
    no fecha ninguna.
    """
    found = _READ_DATE.search(notes)
    if found is None:
        return notes
    depth, cut = 0, -1
    for index, char in enumerate(notes[: found.start()]):
        if char in "«(":
            depth += 1
        elif char in "»)":
            depth = max(depth - 1, 0)
        elif (
            char == "." and depth == 0 and notes[index + 1 : index + 2] == " "
            and _ABBREVIATION.search(notes[:index]) is None
        ):
            cut = index
    return notes[: cut + 1] if cut >= 0 else None


class RegistryError(ValueError):
    """El registro no cumple su propio contrato: no se carga."""


@dataclass(frozen=True, slots=True)
class NamedPerson:
    """Alguien a quien la fuente nombra sin que firme, con el cargo que le da (de la fecha de la
    fuente, no de hoy: un cargo de un artículo de 2016 es el de 2016)."""

    name: str
    role: str


@dataclass(frozen=True, slots=True)
class Affiliation:
    """La organización que el documento escribe junto a una persona de la ficha, en la fecha del
    documento (la de la portada de 2020, no la de hoy)."""

    name: str
    organization: str


@dataclass(frozen=True, slots=True)
class NamedOrganization:
    """Una organización que la fuente nombra sin que sea la suya, con el papel que le da en su
    fecha («payload operations», «manage the U.S. segment of the International Space Station»)."""

    name: str
    role: str


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """La ficha de una fuente (especificación §3). `None` = no está escrito en el repositorio."""

    id: str
    title: str
    # La cita tal como se lee, en una línea. Es lo que ya enseñaba la interfaz.
    source: str
    url: str | None
    doi: str | None
    pmid: str | None
    organization: str | None
    date: str | None
    evidence_type: str | None
    evidence_context: EvidenceContext | None
    population: str | None
    # La salvedad de alcance: qué mide de verdad la fuente, para no atribuirle más.
    notes: str | None
    not_applicable: tuple[str, ...] = ()
    # Leídos en la fuente, sin valor del enumerado que los cubra: `notes` dice por qué.
    outside_enum: tuple[str, ...] = ()
    # Quien firma, en el orden y con la grafía de la cita (o de la nota, si la cita no lo lleva).
    # Ni esto ni `named_people` sale en `to_dict`: lo sirve `GET /api/people`, y una cita sigue
    # teniendo la forma de siempre en el resto de la API.
    authors: tuple[str, ...] = ()
    # Quien la fuente nombra sin firmar, con su cargo tal como lo copia la nota.
    named_people: tuple[NamedPerson, ...] = ()
    # La organización que el documento escribe junto a una persona de la ficha, y las
    # organizaciones que la fuente nombra sin darla. Tampoco salen en `to_dict`.
    affiliations: tuple[Affiliation, ...] = ()
    named_organizations: tuple[NamedOrganization, ...] = ()

    @property
    def unverified(self) -> tuple[str, ...]:
        """Campos sin valor que alguien tiene que completar con la fuente delante."""
        return tuple(
            name for name in OPTIONAL_FIELDS
            if getattr(self, name) is None
            and name not in self.not_applicable and name not in self.outside_enum
        )

    @property
    def scope_in_view(self) -> str | None:
        """Lo que la ficha enseña de su salvedad sin abrir nada; la nota entera va plegada.

        Es `_lead` de la nota, salvo en una fuente que no es solo de personas cuya nota empieza
        por la bitácora: esa se enseña entera, porque lo que no mide en personas no se pliega.
        """
        if self.notes is None:
            return None
        lead = _lead(self.notes)
        if lead is None and self.population in NON_HUMAN:
            return self.notes
        return lead

    def _label(self, name: str, labels: dict[str, str]) -> str:
        """El rótulo de un campo con enumerado, en el idioma de la petición. El valor del campo
        (`evidence_type`, `population`) es un identificador y no cambia."""
        value = getattr(self, name)
        if value is not None:
            return i18n.loc(labels[value])
        if name in self.outside_enum:
            return i18n.loc(OUTSIDE_ENUM)
        return i18n.loc(NOT_APPLICABLE if name in self.not_applicable else UNCLASSIFIED)

    @property
    def evidence_type_display(self) -> str:
        """La clase de documento con el rótulo que se enseña, sin calcular el nivel de evidencia."""
        return self._label("evidence_type", EVIDENCE_TYPES)

    def _grade(self) -> dict[str, Any]:
        # `tier.grade` busca el PMID en el texto de la cita; si la ficha lo lleva aparte, se añade.
        cited = self.source
        if self.pmid is not None and self.pmid not in cited:
            cited = f"{cited} · PMID {self.pmid}"
        # Sin PMID se lee la cita y su título con el léxico de Polaris, que solo degrada
        # (`tier.grade`). La salvedad de alcance no: son palabras de EMMA, a menudo negaciones,
        # y el léxico es literal.
        return grade(cited, self.title)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "doi": self.doi,
            "pmid": self.pmid,
            "organization": self.organization,
            "date": self.date,
            "evidence_type": self.evidence_type,
            "evidence_type_display": self.evidence_type_display,
            "evidence_context": str(self.evidence_context) if self.evidence_context else None,
            "population": self.population,
            "population_display": self._label("population", POPULATIONS),
            "notes": self.notes,
            "not_applicable": list(self.not_applicable),
            "outside_enum": list(self.outside_enum),
            "outside_enum_display": [
                i18n.loc(OPTIONAL_FIELDS[name]) for name in self.outside_enum
            ],
            "unverified": list(self.unverified),
            "unverified_display": [i18n.loc(OPTIONAL_FIELDS[name]) for name in self.unverified],
            # Nivel de evidencia desde el registro de PubMed (`app/evidence/tier.py`).
            "grade": self._grade(),
        }


@dataclass(frozen=True, slots=True)
class Citation:
    """Una ficha citada para algo concreto: la fuente es del registro; la relevancia, de quien cita.

    `relevance` es `None` cuando el texto que acompaña a la cita ya dice para qué sirve (la
    hipótesis de causa compartida lo cuenta en `what_is_known`).
    """

    ref: EvidenceRef
    relevance: str | None = None

    @property
    def id(self) -> str:
        return self.ref.id

    @property
    def title(self) -> str:
        return self.ref.title

    @property
    def source(self) -> str:
        return self.ref.source

    @property
    def url(self) -> str | None:
        return self.ref.url

    @property
    def scope_caveat(self) -> str | None:
        return self.ref.notes

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.ref.to_dict(),
            # Quien cita registra el inglés de su relevancia (`i18n.en`); sin él, sale como está.
            "relevance": None if self.relevance is None else i18n.loc(self.relevance),
            # El nombre con el que la API daba `notes` antes del registro; se conserva.
            "scope_caveat": self.ref.notes,
            # Lo que se lee de ella a la vista; si no es la nota entera, la nota va plegada.
            "scope_in_view": self.ref.scope_in_view,
        }


def _entry(raw: dict[str, Any]) -> EvidenceRef:
    ident = str(raw.get("id", "?"))

    def fail(reason: str) -> RegistryError:
        return RegistryError(f"referencia {ident}: {reason}")

    def text(key: str) -> str | None:
        value = raw[key]
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise fail(f"`{key}` vacío: lo que no se sabe es null")
        return value

    if missing := sorted(_REQUIRED - raw.keys()):
        raise fail(f"faltan campos {missing}: lo que no se sabe se declara null, no se omite")
    if extra := sorted(raw.keys() - _KEYS):
        raise fail(f"campos desconocidos {extra}")
    if not _ID.fullmatch(ident):
        raise fail("identificador no válido: minúsculas, cifras y guiones")
    title, source = text("title"), text("source")
    if title is None or source is None:
        raise fail("sin `title` o sin `source`")
    url, doi = text("url"), text("doi")
    if url is None and doi is None:
        raise fail("sin `url` ni `doi`: una referencia que no se puede abrir no es una referencia")
    if url is not None and not url.startswith("https://"):
        raise fail("`url` tiene que ser https")
    pmid, date = text("pmid"), text("date")
    if pmid is not None and not _PMID.fullmatch(pmid):
        raise fail("`pmid` no es un PMID")
    if date is not None and not _DATE.fullmatch(date):
        raise fail("`date` va en ISO 8601 (AAAA, AAAA-MM o AAAA-MM-DD)")
    kind = text("evidence_type")
    if kind is not None and kind not in EVIDENCE_TYPES:
        raise fail(f"`evidence_type` desconocido; uno de {sorted(EVIDENCE_TYPES)} o null")
    context = text("evidence_context")
    if context is not None and context not in _CONTEXTS:
        raise fail(f"`evidence_context` desconocido; uno de {sorted(_CONTEXTS)} o null")
    population, notes = text("population"), text("notes")
    if population is not None and population not in POPULATIONS:
        raise fail(f"`population` desconocida; una de {sorted(POPULATIONS)} o null")
    if population in NON_HUMAN and notes is None:
        raise fail("fuente con animales sin `notes`: tiene que decir qué no mide en personas")
    not_applicable = tuple(raw.get("not_applicable") or ())
    for name in not_applicable:
        if name not in OPTIONAL_FIELDS:
            raise fail(f"`not_applicable` nombra un campo que no existe: {name}")
        if raw[name] is not None:
            raise fail(f"`{name}` tiene valor y a la vez se declara no aplicable")
    outside_enum = tuple(raw.get("outside_enum") or ())
    for name in outside_enum:
        if name not in ENUMERATED_FIELDS:
            raise fail(f"`outside_enum` nombra un campo sin enumerado: {name}")
        if raw[name] is not None or name in not_applicable:
            raise fail(f"`{name}` fuera del enumerado no puede tener valor ni ser no aplicable")
    if outside_enum and (notes is None or "enumerado" not in notes):
        raise fail("campo fuera del enumerado sin decir en `notes` por qué ningún valor lo cubre")
    authors, named = _people(raw, source, notes or "", fail)
    people = (*authors, *(person.name for person in named))
    affiliations = _affiliations(raw, people, notes or "", fail)
    organizations = _named_organizations(raw, notes or "", fail)
    return EvidenceRef(
        id=ident, title=title, source=source, url=url, doi=doi, pmid=pmid,
        organization=text("organization"), date=date, evidence_type=kind,
        evidence_context=EvidenceContext(context) if context is not None else None,
        population=population, notes=notes, not_applicable=not_applicable,
        outside_enum=outside_enum, authors=authors, named_people=named,
        affiliations=affiliations, named_organizations=organizations,
    )


def _affiliations(
    raw: dict[str, Any], people: tuple[str, ...], notes: str, fail: Callable[[str], RegistryError],
) -> tuple[Affiliation, ...]:
    """La organización que el documento escribe junto a una persona de la ficha.

    Solo de quien ya está en la ficha (firma o la fuente la nombra): una afiliación de alguien que
    la ficha no escribe sería una persona añadida. Y escrita en la nota junto al nombre, igual que
    un cargo: así es la del documento en su fecha para esa persona, no la de otro firmante ni la
    de hoy. Una por persona: dos organizaciones de la misma persona van en una, como las escriba
    el documento.
    """
    if "affiliations" not in raw:
        return ()
    listed = raw["affiliations"]
    if not isinstance(listed, list) or not listed:
        raise fail("`affiliations` es una lista con al menos una persona; sin ella, se omite")
    out: list[Affiliation] = []
    for item in listed:
        if not isinstance(item, dict) or item.keys() != _AFFILIATION_KEYS:
            raise fail("`affiliations`: cada una es {name, organization}, sin más campos")
        name, organization = item["name"], item["organization"]
        if not isinstance(name, str) or name not in people:
            raise fail(f"`affiliations`: {name!r} no firma la ficha ni la fuente la nombra")
        if (
            not isinstance(organization, str) or not organization.strip()
            or _CONTACT.search(organization)
        ):
            raise fail(f"`affiliations`: organización de {name} vacía o con datos de contacto")
        if not _named_with_role(name, organization, notes):
            raise fail(
                f"`affiliations`: {name} y su organización no están escritos juntos en la nota"
            )
        if any(found.name == name for found in out):
            raise fail(f"`affiliations`: {name} repetida; dos organizaciones van en una")
        out.append(Affiliation(name=name, organization=organization))
    return tuple(out)


def _named_organizations(
    raw: dict[str, Any], notes: str, fail: Callable[[str], RegistryError],
) -> tuple[NamedOrganization, ...]:
    """Las organizaciones que la fuente nombra sin darla, con el papel que les da.

    Misma regla que una persona nombrada: nombre y papel escritos juntos en la nota, letra a
    letra, sin datos de contacto y sin repetir; y ninguna que sea ya la organización de la ficha,
    que la daría dos veces. Lo que esto comprueba es que la nota los escribe juntos, no que la
    fuente lo haga: la nota puede componer el par, y la frase literal es la que cita la nota o la
    columna del banco.
    """
    if "named_organizations" not in raw:
        return ()
    listed = raw["named_organizations"]
    if not isinstance(listed, list) or not listed:
        raise fail("`named_organizations` es una lista con al menos una; sin ella, se omite")
    own = {part.strip() for part in (raw.get("organization") or "").split(ORG_SEPARATOR)}
    out: list[NamedOrganization] = []
    for item in listed:
        if not isinstance(item, dict) or item.keys() != _NAMED_KEYS:
            raise fail("`named_organizations`: cada una es {name, role}, sin más campos")
        name, role = item["name"], item["role"]
        if (
            not isinstance(name, str) or not _ORGANIZATION_NAME.fullmatch(name)
            or _CONTACT.search(name)
        ):
            raise fail(f"`named_organizations`: {name!r} no es el nombre de una organización")
        if not isinstance(role, str) or not role.strip() or _CONTACT.search(role):
            raise fail(f"`named_organizations`: papel de {name} vacío o con datos de contacto")
        if not _named_with_role(name, role, notes):
            raise fail(
                f"`named_organizations`: {name} y su papel no están escritos juntos en la nota"
            )
        if name in own or any(found.name == name for found in out):
            raise fail(
                f"`named_organizations`: {name} repetida o es ya la organización de la ficha"
            )
        out.append(NamedOrganization(name=name, role=role))
    return tuple(out)


def _people(
    raw: dict[str, Any], source: str, notes: str, fail: Callable[[str], RegistryError],
) -> tuple[tuple[str, ...], tuple[NamedPerson, ...]]:
    """Quien firma y quien la fuente nombra, comprobados contra lo que la ficha ya escribe.

    Una lista vacía no se escribe (sin personas, el campo se omite); un nombre que la cita o la
    nota no escriben letra a letra, como nombre entero, sería una persona añadida de memoria; uno
    repetido, la misma persona contada dos veces. El cargo de quien la fuente nombra tiene que
    estar en la nota tal cual y junto a su nombre: es el que la fuente le da a esa persona en su
    fecha, no uno de hoy ni el de otra.
    """
    authors: list[str] = []
    if "authors" in raw:
        listed = raw["authors"]
        if not isinstance(listed, list) or not listed:
            raise fail("`authors` es una lista con al menos un nombre; sin autores, se omite")
        for name in listed:
            if not isinstance(name, str) or not _PERSON_NAME.fullmatch(name):
                raise fail(f"`authors`: {name!r} no es un nombre (ni cifras ni datos de contacto)")
            if not _written(name, source) and not _written(name, notes):
                raise fail(f"`authors`: {name!r} no está escrito en la cita ni en la nota")
            if name in authors:
                raise fail(f"`authors`: {name!r} repetido")
            authors.append(name)
    named: list[NamedPerson] = []
    if "named_people" in raw:
        listed = raw["named_people"]
        if not isinstance(listed, list) or not listed:
            raise fail("`named_people` es una lista con al menos una persona; sin ella, se omite")
        for item in listed:
            if not isinstance(item, dict) or item.keys() != _NAMED_KEYS:
                raise fail("`named_people`: cada persona es {name, role}, sin más campos")
            name, role = item["name"], item["role"]
            if not isinstance(name, str) or not _NAMED_NAME.fullmatch(name):
                raise fail(f"`named_people`: {name!r} no es un nombre (ni cifras ni contacto)")
            if not isinstance(role, str) or not role.strip() or _CONTACT.search(role):
                raise fail(f"`named_people`: cargo de {name} vacío o con datos de contacto")
            if not _named_with_role(name, role, notes):
                raise fail(f"`named_people`: {name} y su cargo no están escritos juntos en la nota")
            if name in authors or any(person.name == name for person in named):
                raise fail(f"`named_people`: {name} repetido o ya entre quienes firman")
            named.append(NamedPerson(name=name, role=role))
    return tuple(authors), tuple(named)


def parse(raw: dict[str, Any]) -> dict[str, EvidenceRef]:
    """Valida el registro entero. Un identificador repetido es un error, no una sobrescritura."""
    out: dict[str, EvidenceRef] = {}
    for item in raw["references"]:
        ref = _entry(item)
        if ref.id in out:
            raise RegistryError(f"referencia {ref.id}: identificador duplicado")
        out[ref.id] = ref
    return out


@cache
def registry() -> dict[str, EvidenceRef]:
    return parse(json.loads(REGISTRY_PATH.read_text(encoding="utf-8")))


def get(ref_id: str) -> EvidenceRef:
    """La ficha de un identificador. Citar una que no existe falla: no se inventa una en blanco."""
    try:
        return registry()[ref_id]
    except KeyError:
        raise RegistryError(f"referencia {ref_id}: no está en el registro de evidencia") from None


def cite(ref_id: str, relevance: str | None = None) -> Citation:
    """Cita una ficha del registro diciendo para qué se usa aquí."""
    return Citation(ref=get(ref_id), relevance=relevance)


def summary() -> dict[str, Any]:
    """El registro entero resuelto, con lo que queda por verificar a la vista (solo lectura)."""
    references = [ref.to_dict() for ref in registry().values()]
    return {
        "references": references,
        "count": len(references),
        "unverified_fields": sum(len(item["unverified"]) for item in references),
        "evidence_types": {key: i18n.loc(label) for key, label in EVIDENCE_TYPES.items()},
        "populations": {key: i18n.loc(label) for key, label in POPULATIONS.items()},
    }
