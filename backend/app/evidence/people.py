"""Personas y organizaciones de las fuentes, derivadas del registro de evidencia en cada consulta.

Por qué existe: la conversación de ideación pedía una pestaña «People & Organizations» (quién
investiga, con qué institución, en qué trabajo) y la base de conocimiento la deja en su backlog
(§15, P2). Hasta la decimosexta ronda era una lista escrita a mano
(`docs/contexto/personas-y-organizaciones.md`), y se quedó atrás: el registro ya traía ESA, NASA
Glenn, JPL, Boeing o la Universidad de Waterloo que la lista no tenía. Una lista que se copia del
registro deja de decir lo mismo que él en cuanto alguien añade una ficha. Aquí no se escribe
ninguna persona ni ninguna organización: se recorren las fichas y se agrupa lo que ya dicen.

Qué se dice y qué no, porque son personas reales:
  * La organización es la que da la ficha (`organization`), con el año de la ficha: en un
    artículo, la afiliación que firma en él (casi siempre la del primer autor; la nota de cada
    ficha dice cuál), no la de hoy. Una ficha con dos organizaciones las separa con « / » y sale
    en las dos. Los nombres se agrupan letra a letra: «NASA OCHMO» y «NASA Office of the Chief
    Health and Medical Officer» son dos filas porque dos fichas los escriben distinto, y juntarlas
    sería decidir algo que ninguna ficha dice.
  * Quien firma sale con la grafía de la cita (`authors`, comprobado contra la cita o la nota en
    `registry.py`) y su puesto en ella. La organización de la ficha NO es la afiliación de cada
    firmante: el panel la enseña como de la ficha, nunca junto al nombre como si fuera suya.
  * Quien la fuente nombra sin firmar (`named_people`) sale con el cargo que le da la fuente, de la
    fecha de la fuente.
  * Se agrupa por la grafía exacta: la misma persona escrita de dos formas («Dinges DF» y
    «Dinges, David») sale dos veces, porque no se juntan nombres por parecido; y dos personas
    distintas con las mismas iniciales («Anderson A» en dos presentaciones) salen juntas, porque
    ninguna ficha dice si lo son. La regla se sirve con la lista para que se lea así. Ningún dato
    de contacto: el registro no admite cifras ni arrobas en un nombre.
  * Desde la decimonovena ronda (U4), una persona lleva la organización que el documento escribe
    junto a su nombre (`affiliations`: la portada de Krihak et al. 2020 da una por autor, y la
    conversación de ideación pedía institución y especialidad de cada persona), de la fecha del
    documento y solo si la ficha la escribe; sin frase, no se sirve nada. Y una organización que
    una fuente nombra sin darla (`named_organizations`: Teledyne Brown, CASIS, la NSF) sale entre
    las organizaciones con el papel que la fuente le da y la ficha que la nombra, aparte de las
    fichas que esa organización da, que son otra cosa.

Solo lectura y sin red: no lee el almacén ni el estado de la tripulación.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Any

from app.core import i18n
from app.evidence import registry
from app.evidence.registry import ORG_SEPARATOR, EvidenceRef

# Una cita que abrevia la lista de firmantes no los nombra a todos. Lo que cabe detrás del último
# firmante antes de su «et al.» («, et al.»): más allá ya es el título o la revista.
_ET_AL = re.compile(r"\bet al\b")
_AFTER_LIST = ", et al."

NOTE = (
    "Derivado del registro de evidencia en cada consulta: ninguna persona ni organización se "
    "escribe aparte. Una organización da fichas, con su año, o la nombra una ficha; cada "
    "persona, la que firma una ficha o la que la fuente nombra, con el papel que le da la ficha."
)
AFFILIATION_RULE = (
    "La organización de una ficha es la de la fuente en su fecha (en un artículo, la afiliación "
    "que firma en él), no la de hoy, y no es la afiliación de cada firmante. Un cargo es el que "
    "da la fuente en su fecha."
)
SAME_PERSON_RULE = (
    "Se agrupa por la grafía exacta de la cita: la misma persona escrita de dos formas sale dos "
    "veces, y dos personas con la misma grafía (las mismas iniciales) salen juntas, porque "
    "ninguna ficha dice cuál es cuál. No hay datos de contacto."
)
NAMED_ORGANIZATION_RULE = (
    "Una organización que una fuente nombra sin darla sale con el papel que la fuente le da, en "
    "su fecha, y con la ficha que la nombra; no es la organización de esa ficha. La afiliación "
    "de una persona es la que el documento escribe junto a su nombre, en su fecha. Se agrupa "
    "por la grafía exacta: dos grafías de la misma organización salen en dos filas."
)
NO_ORGANIZATION = "sin organización en la ficha"
NO_YEAR = "sin fecha en la ficha"
i18n.en_many({
    NOTE: (
        "Derived from the evidence registry on each request: no person or organisation is "
        "written separately. An organisation provides reference cards, with their year, or is "
        "named by one; each person, the one who authors a card or the one the source names, "
        "with the role the card gives them."
    ),
    AFFILIATION_RULE: (
        "The organisation of a reference card is that of the source at its date (in an article, "
        "the affiliation that signs it), not today's, and is not the affiliation of each "
        "author. A position is the one the source gives at its date."
    ),
    SAME_PERSON_RULE: (
        "Grouping is by the exact spelling of the citation: the same person written in two ways "
        "appears twice, and two people with the same spelling (the same initials) appear "
        "together, because no reference card says which is which. There are no contact details."
    ),
    NAMED_ORGANIZATION_RULE: (
        "An organisation that a source names without being its provider appears with the role "
        "the source gives it, at its date, and with the reference card that names it; it is "
        "not the organisation of that card. The affiliation of a person is the one the document "
        "writes next to their name, at its date. Grouping is by the exact spelling: two "
        "spellings of the same organisation appear in two rows."
    ),
    NO_ORGANIZATION: "no organisation on the reference card",
    NO_YEAR: "no date on the reference card",
})


def organizations_of(ref: EvidenceRef) -> list[str]:
    """Las organizaciones que da una ficha, en su orden; ninguna si la ficha no la tiene."""
    if ref.organization is None:
        return []
    return [part.strip() for part in ref.organization.split(ORG_SEPARATOR) if part.strip()]


def _year(ref: EvidenceRef) -> str | None:
    return ref.date[:4] if ref.date is not None else None


def _et_al(ref: EvidenceRef) -> bool:
    """La cita abrevia la lista de firmantes: el puesto de cada uno es entre los que nombra, y el
    total no se sabe.

    Solo cuenta un «et al.» dentro de la lista de firmantes de la cita o justo detrás de ella
    («Tauber S, et al.; Ullrich O», «Kerstman et al.,»), no uno de otra obra que la cita mencione.
    Si algún firmante no sale de la cita (la firma de una página, que copia la nota), la lista no
    es la de la cita y no hay nada que abreviar.
    """
    if not ref.authors or any(name not in ref.source for name in ref.authors):
        return False
    start = ref.source.find(ref.authors[0])
    last = ref.authors[-1]
    end = ref.source.find(last, start) + len(last)
    return bool(_ET_AL.search(ref.source[start : end + len(_AFTER_LIST)]))


def _author_role(ref: EvidenceRef, position: int) -> str:
    total = len(ref.authors)
    if _et_al(ref):
        return i18n.tr(
            f"firma ({position}.ª de las que nombra la cita, que abrevia con «et al.»)",
            f"author (no. {position} of those the citation names, which it abbreviates with "
            "«et al.»)",
        )
    if total == 1:
        return i18n.tr("firma (única firma en la ficha)", "author (the only one on the card)")
    return i18n.tr(f"firma ({position}.ª de {total})", f"author (no. {position} of {total})")


def _when(ref: EvidenceRef) -> str:
    year = _year(ref)
    return i18n.tr(
        f"en la fecha de la fuente, {year}" if year is not None
        else "en una fecha que la ficha no da",
        f"at the date of the source, {year}" if year is not None
        else "at a date the reference card does not give",
    )


def _named_role(ref: EvidenceRef, role: str) -> str:
    return i18n.tr(
        f"la fuente la nombra como «{role}» ({_when(ref)})",
        f"named by the source as «{role}» ({_when(ref)})",
    )


def _affiliation_text(ref: EvidenceRef, organization: str) -> str:
    return i18n.tr(
        f"el documento la sitúa en «{organization}» ({_when(ref)})",
        f"placed by the document at «{organization}» ({_when(ref)})",
    )


def _affiliation(ref: EvidenceRef, name: str) -> str | None:
    """La organización que el documento escribe junto a esa persona, o nada."""
    return next((item.organization for item in ref.affiliations if item.name == name), None)


def _reference(ref: EvidenceRef) -> dict[str, Any]:
    return {
        "id": ref.id,
        "title": ref.title,
        "source": ref.source,
        "url": ref.url,
        "date": ref.date,
        "year": _year(ref),
        "evidence_type_display": i18n.loc(ref.evidence_type_display),
        "organization": ref.organization,
        "authors": list(ref.authors),
        "et_al": _et_al(ref),
        "named_people": [
            {"name": p.name, "role": p.role, "role_text": _named_role(ref, p.role)}
            for p in ref.named_people
        ],
        "affiliations": [
            {
                "name": item.name,
                "organization": item.organization,
                "text": _affiliation_text(ref, item.organization),
            }
            for item in ref.affiliations
        ],
        "named_organizations": [
            {"name": item.name, "role": item.role, "role_text": _named_role(ref, item.role)}
            for item in ref.named_organizations
        ],
    }


def _sort_key(name: str) -> str:
    """Orden alfabético sin que una tilde mande al final («Ébert» va con la E)."""
    plain = unicodedata.normalize("NFKD", name)
    return "".join(char for char in plain if not unicodedata.combining(char)).casefold()


def _citation(ref: EvidenceRef, name: str, role: str, role_text: str) -> dict[str, Any]:
    affiliation = _affiliation(ref, name)
    return {
        **_source_of(ref, role, role_text),
        # La organización que el documento escribe junto a esa persona, o nada: no se deduce de
        # la de la ficha.
        "affiliation": affiliation,
        "affiliation_text": (
            _affiliation_text(ref, affiliation) if affiliation is not None else None
        ),
    }


def _source_of(ref: EvidenceRef, role: str, role_text: str) -> dict[str, Any]:
    return {
        "ref": ref.id,
        "title": ref.title,
        "year": _year(ref),
        "organization": ref.organization,
        "role": role,
        "role_text": role_text,
    }


def payload() -> dict[str, Any]:
    """Organizaciones y personas del registro, recorridas ahora: nada se guarda entre consultas."""
    refs = list(registry.registry().values())
    by_org: dict[str, list[dict[str, Any]]] = defaultdict(list)
    named_org: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_person: dict[str, list[dict[str, Any]]] = defaultdict(list)
    without: list[dict[str, Any]] = []
    for ref in refs:
        entry = _reference(ref)
        orgs = organizations_of(ref)
        if not orgs:
            without.append(entry)
        for org in orgs:
            by_org[org].append(entry)
        for organization in ref.named_organizations:
            named_org[organization.name].append(
                _source_of(ref, organization.role, _named_role(ref, organization.role))
            )
        for position, name in enumerate(ref.authors, start=1):
            by_person[name].append(_citation(ref, name, "author", _author_role(ref, position)))
        for person in ref.named_people:
            by_person[person.name].append(
                _citation(ref, person.name, "named", _named_role(ref, person.role))
            )
    # Las que dan una ficha y las que una ficha nombra, en una sola lista por su grafía: la que
    # hace las dos cosas sale una vez, con las dos listas.
    organizations = [
        {"name": name, "references": by_org.get(name, []), "named_by": named_org.get(name, [])}
        for name in sorted(by_org.keys() | named_org.keys(), key=_sort_key)
    ]
    people = [
        {"name": name, "citations": citations}
        for name, citations in sorted(by_person.items(), key=lambda item: _sort_key(item[0]))
    ]
    return {
        "note": i18n.loc(NOTE),
        "affiliation_rule": i18n.loc(AFFILIATION_RULE),
        "same_person_rule": i18n.loc(SAME_PERSON_RULE),
        "named_organization_rule": i18n.loc(NAMED_ORGANIZATION_RULE),
        "no_organization": i18n.loc(NO_ORGANIZATION),
        "no_year": i18n.loc(NO_YEAR),
        "organizations": organizations,
        "people": people,
        "without_organization": without,
        "references": len(refs),
    }
