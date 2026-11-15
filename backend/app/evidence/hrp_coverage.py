"""Los riesgos del Human Research Program, todos, y qué hace EMMA con cada uno.

Por qué existe: EMMA cita un riesgo del HRP por dominio (`evidence/links.py`, `HRP_RISKS`), nueve
en total, y `GET /api/risks` los sirve como si fueran «los riesgos». El Human Research Roadmap
publicaba 22 el 2026-10-23 (el total lo lee `validate` del listado). Leída solo la lista de
EMMA, parecía que el programa no tiene riesgo sensoriomotor, de descompresión, de polvo, de
medicamentos o de cálculos renales, cuando lo que pasa es que EMMA no los vigila. La base de
conocimiento del equipo pone RIDGE como índice superior de los riesgos (§2.1) y nombra el riesgo
de cálculos (§4); la especificación pide la entidad Riesgo con su categoría (§3), y la invariante
6, que el alcance se declare con precisión. Un sistema que no dice qué deja fuera acaba sugiriendo
que lo cubre.

Lo que carga este módulo (`data/hrp_risks_coverage.json`) es una fila por página de riesgo del
Roadmap, con la cabecera leída en ella (título, «Short Title», estado, elemento, fecha de
publicación) y lo que es de EMMA, separado y con su motivo: el eje RIDGE —con si lo nombra una
fuente de NASA o lo deduce EMMA— y la cobertura.

LA COBERTURA NO SE ESCRIBE A OJO. «Cubierto» tiene una definición que se comprueba: el riesgo es el
que cita el dominio en `HRP_RISKS`. Un riesgo que un dominio vigila en parte sin citarlo es «en
parte», y uno que ningún dominio vigila, «fuera del alcance de EMMA». `validate` rechaza un
«cubierto» que no sea la cita de su dominio, un riesgo citado por un dominio cuya fila no diga
«cubierto» por él o falte (la página de un riesgo o un informe del Roadmap tienen que tener la
suya), un dominio que no existe, un dominio de EMMA que no aparezca en ninguna fila (vigilaría algo
que no está en la lista), una ficha que no esté en el registro, cuya página no sea la de esa fila
o que esté en dos filas, una ficha o un analito repetidos, un recuento distinto del que declara el
listado y un texto que el filtro de lenguaje bloquea.

Es un inventario: no entra en el análisis, en el riesgo ni en ninguna alerta (invariante 5), no
cambia lo que cita ningún dominio y no sale a la red. Los analitos que una fuente nombra y el
catálogo no tiene van en `pending`, como pendientes: no se añade un código aquí (invariantes 1 y 2).
Los que nombra y el catálogo sí tiene van en `in_catalog`, por su clave: desde el 2026-10-26, los
ocho de la orina de 24 horas del riesgo de cálculos renales, descriptivos
(`codes.DESCRIPTIVE_ONLY`), y desde el 2026-10-31 las medidas de la batería Cognition en la fila de
salud conductual, también descriptivas y con código propio. Un descriptivo no convierte una fila
en «en parte»: se registra y el estado no lo lee, así que no vigila nada (por eso las afirmaciones
de cohesión constan en el motivo de la fila de equipo, que sigue «fuera del alcance»).
Cada clave tiene que ser del catálogo y de un dominio de su fila.

Cada fila lleva además, desde el 2026-10-26, la ficha del informe de evidencia que enlaza la página
de su riesgo (o la página de evidencias del Roadmap bajo ese riesgo), leído en su portada: su
fecha y el elemento que nombra. Un informe se ata a las filas de los riesgos que lo enlazan
(`REPORT_RISK`); el de descompresión e hipoxia es uno para dos riesgos, y es el único que está en
dos filas.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import re
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any

from app import text_guard
from app.core import display, i18n
from app.evidence import registry
from app.evidence.links import ADDITIONAL_HRP_RISKS, HRP_RISKS, amcl_alignment
from app.ingest.codes import (
    CATALOG,
    CODE_SYSTEM_DISPLAY,
    DESCRIPTIVE_ONLY,
    CodeSystem,
    Domain,
    Ridge,
)

COVERAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "hrp_risks_coverage.json"

# La página de cada riesgo en el Roadmap: la fila lleva su número (`hrr_id`), no la dirección.
RISK_PAGE = "https://humanresearchroadmap.nasa.gov/Risks/risk.aspx?i={}"

# La cobertura, con la palabra que se lee. La interfaz no la redacta.
COVERAGE = {
    "covered": "cubierto",
    "partial": "en parte",
    "outside": "fuera del alcance de EMMA",
}
# La frase de cada fila, con los dominios por su nombre: «cubierto» a secas, junto al nombre corto
# del riesgo, se leía «cubierto por el dominio Behavioral Health» en la primera captura.
COVERAGE_STATEMENT = {
    "covered": "cubierto por el dominio {domains}",
    "partial": "en parte, por {article} {domains}",
    "outside": "fuera del alcance de EMMA",
}
STATUS = {
    "active": "activo",
    "inactive": "inactivo",
}
# De dónde sale el eje RIDGE de cada fila: una fuente de NASA lo nombra, o lo deduce EMMA.
RIDGE_BASIS = {
    "source": "lo nombra una fuente de NASA",
    "emma": "lo deduce EMMA; ninguna fuente leída lo nombra",
}
NOTE = (
    "Los riesgos que publica el Human Research Roadmap y qué hace EMMA con cada uno. «Cubierto» "
    "quiere decir que es el riesgo que cita un dominio de EMMA, con el alcance que ese dominio "
    "declara, no que EMMA lo cubra entero. Inventario: no interviene en el estado de la "
    "tripulación ni en ninguna alerta."
)
ELEMENT_BASIS = (
    "El elemento del HRP al que el Roadmap asigna cada riesgo, leído en la cabecera de su página "
    "(«Element:»). Las portadas de los informes de evidencia que enlaza cada página se leyeron el "
    "2026-10-26, y cada ficha dice su fecha y el elemento que nombra. Casi todas nombran el de la "
    "página. Las de polvo («Space Human Factors and Habitability»), sueño y equipo («Behavioral "
    "Health and Performance») y el informe de medicamentos de 2011 («Human Health "
    "Countermeasures») nombran otro, el de cuando se aprobaron; la cardiovascular escribe «Human "
    "Health and Countermeasures»; y las de descompresión e hipoxia, de actividad extravehicular y "
    "el libro de nutrición no nombran ninguno. La fila da el de la página."
)
RIDGE_NOTE = (
    "El eje RIDGE de cada riesgo lo asigna EMMA: el Roadmap no lo publica por riesgo. Se apoya en "
    "la página de NASA sobre los cinco peligros cuando ella o el título del riesgo lo nombran, y "
    "si no, lo dice."
)
PENDING_NOTE = (
    "Analitos, medidas e instrumentos que nombra la fuente y no están en el catálogo de EMMA: "
    "quedan pendientes, sin código, hasta leer la medida y verificar su código y su unidad."
)
IN_CATALOG_NOTE = (
    "Analitos, medidas e instrumentos que nombra la fuente y están en el catálogo de EMMA, "
    "cada uno con su código (LOINC leído en su ficha, o propio con lo que se buscó) y la "
    "unidad de su propiedad."
)
# Lo que se dice de una medida o analito del catálogo que el estado no lee: se registra y se
# enseña, nada más.
DESCRIPTIVE_DISPLAY = (
    "descriptivo: se registra y se enseña, y el estado no lo lee"
)
SUMMARY = (
    "De los {total} riesgos del listado, {covered} son el que cita un dominio de EMMA, {partial} "
    "se cubren en parte, vigilados o solo registrados según la fila, y {outside} quedan fuera de "
    "su alcance."
)

# El inglés de lo de arriba (`core/i18n.py`): las constantes no se mueven y se resuelven al
# servir. «covered» sigue queriendo decir lo que dice `NOTE`: es el riesgo que cita un dominio, no
# que EMMA lo cubra entero. Los nombres de los ejes y de los elementos del HRP son los de NASA.
i18n.en_many({
    COVERAGE["covered"]: "covered",
    COVERAGE["partial"]: "partly",
    COVERAGE["outside"]: "outside EMMA's scope",
    COVERAGE_STATEMENT["covered"]: "covered by the {domains} domain",
    COVERAGE_STATEMENT["partial"]: "partly, by the {domains} {article}",
    STATUS["active"]: "active",
    STATUS["inactive"]: "inactive",
    RIDGE_BASIS["source"]: "named by a NASA source",
    RIDGE_BASIS["emma"]: "inferred by EMMA; no source read names it",
    NOTE: (
        "The risks the Human Research Roadmap publishes and what EMMA does with each. «Covered» "
        "means it is the risk an EMMA domain cites, with the scope that domain declares, not "
        "that EMMA covers it in full. Inventory: it plays no part in the crew's status or in "
        "any alert."
    ),
    ELEMENT_BASIS: (
        "The HRP element the Roadmap assigns each risk to, read in the header of its page "
        "(«Element:»). The covers of the evidence reports each page links were read on "
        "2026-10-26, and each record says its date and the element it names. Almost all name "
        "the page's element. Those for dust («Space Human Factors and Habitability»), sleep and "
        "team («Behavioral Health and Performance») and the 2011 medication report («Human "
        "Health Countermeasures») name another, the one in force when they were approved; the "
        "cardiovascular one writes «Human Health and Countermeasures»; and those for "
        "decompression and hypoxia, for extravehicular activity and the nutrition book name "
        "none. The row gives the page's."
    ),
    RIDGE_NOTE: (
        "The RIDGE axis of each risk is assigned by EMMA: the Roadmap does not publish it per "
        "risk. It rests on NASA's page on the five hazards when that page or the risk title "
        "names it, and otherwise it says so."
    ),
    PENDING_NOTE: (
        "Analytes, measures and instruments the source names that are not in EMMA's catalog: "
        "they remain pending, with no code, until the measure is read and its code and unit are "
        "verified."
    ),
    IN_CATALOG_NOTE: (
        "Analytes, measures and instruments the source names that are in EMMA's catalog, each "
        "with its code (LOINC as read on its record, or EMMA's own with what was searched for) "
        "and the unit of its property."
    ),
    DESCRIPTIVE_DISPLAY: "descriptive: it is recorded and shown, and the status does not read it",
    SUMMARY: (
        "Of the {total} risks in the listing, {covered} are the one an EMMA domain cites, "
        "{partial} are covered partly, watched or only recorded depending on the row, and "
        "{outside} are outside its scope."
    ),
})

RISK_FIELDS = frozenset({
    "hrr_id", "title", "short_title", "status", "hrp_element", "last_published", "ridge",
    "ridge_basis", "ridge_note", "coverage", "domains", "reason", "refs", "in_catalog", "pending",
})
LISTING_FIELDS = frozenset({"ref", "count_quote", "element_quote", "updates"})
TOP_FIELDS = frozenset({"_nota", "read_on", "listing", "ridge_source", "risks"})
# Lo que publica el propio Roadmap sobre un riesgo: si un dominio lo cita, su riesgo está en el
# listado y tiene fila.
ROADMAP_SOURCES = frozenset({"hrp_risk", "evidence_report"})
# El informe de evidencia de cada riesgo, atado al número de la página de su riesgo. La ficha de una
# página de riesgo se ata a su fila por su dirección; un informe no tiene esa dirección, y sin esto
# el de SANS podía moverse a otra fila, decirla «cubierta» por el dominio neuro-ocular y pasar
# (tercera revisión de código). Los tres primeros son el informe del riesgo que nombra su título
# («Evidence Report: Risk of …»); el de alimentación dice «Inadequate Food System» y la página de su
# riesgo, hoy, «Inadequate Food and Nutrition».
#
# Los demás (2026-10-26) son el informe que enlaza hoy la página de cada riesgo, o los que la página
# de evidencias del Roadmap pone bajo él cuando la del riesgo remite a esa lista («Multiple
# Evidence Reports»): medicamentos, actividad extravehicular, alimentación y nutrición, y el anexo
# de operaciones del renal. El título de la portada no siempre es el de la página de hoy (el de la
# integración de sistemas es de un riesgo anterior); lo que ata el informe a su fila es el enlace.
# El de descompresión e hipoxia lo enlazan dos páginas: es el único con dos filas.
REPORT_RISK: dict[str, tuple[int, ...]] = {
    "hrp-sans-evidence-report": (105,),
    "hrp-food-system-evidence-report": (176,),
    "hrp-renal-stone-evidence-report": (81,),
    "hrp-ivd-evidence-book": (78,),
    "hrp-bmed-evidence-report": (99,),
    "hrp-medical-conditions-evidence-report": (95,),
    "hrp-microhost-evidence-report": (80,),
    "hrp-dust-evidence-report": (82,),
    "hrp-hsia-evidence-report": (175,),
    "hrp-sensorimotor-evidence-report": (88,),
    "hrp-bone-fracture-evidence-report": (77,),
    "hrp-cardiovascular-evidence-report": (179,),
    "hrp-immune-evidence-report": (85,),
    "hrp-dynamic-loads-evidence-report": (167,),
    "hrp-team-evidence-report": (101,),
    "hrp-pharm-evidence-report-2023": (177,),
    "hrp-pharm-evidence-report-2011": (177,),
    "hrp-eva-evidence-report": (84,),
    "hrp-dcs-hypoxia-evidence-report": (168, 173),
    "hrp-muscle-aerobic-evidence-report": (180,),
    "hrp-food-nutrition-evidence-report-2024": (176,),
    "hrp-nutrition-human-adaptation-2020": (176,),
    "hrp-sleep-evidence-report": (100,),
    "hrp-carcinogenesis-evidence-report": (96,),
    "hrp-sans-evidence-report-2022": (105,),
    "hrp-renal-stone-conops-appendix-b": (81,),
}
# Los textos de cada fila que ve alguien: pasan el filtro de lenguaje (invariante 7).
_PROSE = ("ridge_note", "reason")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _iso_day(value: Any) -> bool:
    """Un día de calendario en ISO 8601 que existe: «2025-13-05» no es una fecha que enseñar."""
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        return False
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        return False
    return True


# «Risks 1 - 22 ( of 22 )»: el total que declara el listado.
_COUNT = re.compile(r"\(\s*of\s+(\d+)\s*\)")
_DOMAINS = frozenset(str(item) for item in Domain)
_RIDGES = frozenset(str(item) for item in Ridge)


class CoverageError(ValueError):
    """La cobertura de los riesgos del HRP no cumple su contrato: no se sirve."""


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _one_of(value: Any, allowed: Mapping[str, Any] | frozenset[str]) -> bool:
    """Un valor del enumerado. Primero si es texto: una lista no se busca en un conjunto (daría
    `TypeError` en vez de `CoverageError`)."""
    return isinstance(value, str) and value in allowed


def _exact(where: str, item: Any, expected: frozenset[str]) -> None:
    """Ni campos de menos (lo que no hay va vacío) ni de más (uno mal escrito no se sirve)."""
    if not isinstance(item, dict):
        raise CoverageError(f"{where}: se esperaba un objeto")
    if missing := sorted(expected - item.keys()):
        raise CoverageError(f"{where}: faltan campos {missing}")
    if extra := sorted(item.keys() - expected):
        raise CoverageError(f"{where}: campos desconocidos {extra}")


def _ref(where: str, ref_id: Any) -> registry.EvidenceRef:
    if not isinstance(ref_id, str):
        raise CoverageError(f"{where}: una ficha se cita por su identificador")
    try:
        return registry.get(ref_id)
    except registry.RegistryError as missing:
        raise CoverageError(f"{where}: ficha {ref_id} sin registrar") from missing


def _guarded(where: str, text: str) -> None:
    if found := text_guard.check(text):
        raise CoverageError(f"{where}: el filtro de lenguaje lo bloquea ({found[0].category})")


def _validate_in_catalog(where: str, keys: Any, domains: list[str]) -> None:
    """Los analitos de la fuente que el catálogo tiene: claves suyas, una vez, de la fila.

    Una clave de otro dominio diría que la fila vigila lo que vigila otro; una fila «fuera del
    alcance», sin dominios, no puede tener ninguna.
    """
    if not isinstance(keys, list) or not all(isinstance(key, str) for key in keys):
        raise CoverageError(f"{where}: `in_catalog` es la lista de claves del catálogo")
    if len(set(keys)) != len(keys):
        raise CoverageError(f"{where}: analito del catálogo repetido")
    for key in keys:
        code = CATALOG.get(key)
        if code is None:
            raise CoverageError(f"{where}: {key} no es un indicador del catálogo")
        if str(code.domain) not in domains:
            raise CoverageError(f"{where}: {key} es de un dominio que la fila no nombra")


def _validate_risk(item: Any, cited: Mapping[Domain, str]) -> None:
    where = f"riesgo {item.get('hrr_id') if isinstance(item, dict) else item!r}"
    _exact(where, item, RISK_FIELDS)
    hrr_id = item["hrr_id"]
    if not isinstance(hrr_id, int) or isinstance(hrr_id, bool) or hrr_id <= 0:
        raise CoverageError(f"{where}: `hrr_id` es el número de la página del riesgo")
    for name in ("title", "short_title", "hrp_element", *_PROSE):
        if not _text(item[name]):
            raise CoverageError(f"{where}: `{name}` vacío")
    for name in _PROSE:
        _guarded(f"{where}/{name}", item[name])
    if not _one_of(item["status"], STATUS):
        raise CoverageError(f"{where}: estado desconocido {item['status']!r}")
    if not _iso_day(item["last_published"]):
        raise CoverageError(f"{where}: `last_published` es la fecha de la página, en ISO")
    if not _one_of(item["ridge"], _RIDGES):
        raise CoverageError(f"{where}: eje RIDGE desconocido {item['ridge']!r}")
    if not _one_of(item["ridge_basis"], RIDGE_BASIS):
        raise CoverageError(f"{where}: de dónde sale el eje RIDGE: {item['ridge_basis']!r}")
    domains = item["domains"]
    if not isinstance(domains, list) or not all(_one_of(name, _DOMAINS) for name in domains):
        raise CoverageError(f"{where}: dominio que EMMA no tiene en {domains!r}")
    if len(set(domains)) != len(domains):
        raise CoverageError(f"{where}: dominio repetido")
    refs = item["refs"]
    if not isinstance(refs, list) or not all(isinstance(ref_id, str) for ref_id in refs):
        raise CoverageError(f"{where}: `refs` es la lista de fichas, aunque vacía")
    if len(set(refs)) != len(refs):
        raise CoverageError(f"{where}: ficha repetida")
    for ref_id in refs:
        ref = _ref(where, ref_id)
        # La ficha de un riesgo tiene que ser la página de esta fila, no la de otro.
        if ref.evidence_type == "hrp_risk" and ref.url != RISK_PAGE.format(hrr_id):
            raise CoverageError(f"{where}: la ficha {ref.id} es la página de otro riesgo")
        # Y un informe, el de su riesgo (`REPORT_RISK`): uno sin riesgo declarado no entra.
        if ref.evidence_type == "evidence_report" and hrr_id not in REPORT_RISK.get(ref.id, ()):
            raise CoverageError(f"{where}: el informe {ref.id} no es el de este riesgo")
    _validate_in_catalog(where, item["in_catalog"], domains)
    coverage = item["coverage"]
    if coverage == "covered":
        if len(domains) != 1:
            raise CoverageError(f"{where}: cubierto por un dominio, y solo uno")
        if cited.get(Domain(domains[0])) not in refs:
            raise CoverageError(
                f"{where}: «cubierto» es el riesgo que cita el dominio; {domains[0]} cita otro"
            )
    elif coverage == "partial":
        if not domains:
            raise CoverageError(f"{where}: en parte, pero sin dominio que lo vigile")
    elif coverage == "outside":
        if domains:
            raise CoverageError(f"{where}: fuera del alcance, pero con dominios {domains!r}")
    else:
        raise CoverageError(f"{where}: cobertura desconocida {coverage!r}")
    pending = item["pending"]
    if not isinstance(pending, list) or not all(_text(name) for name in pending):
        raise CoverageError(f"{where}: `pending` es la lista de analitos pendientes")
    if len(set(pending)) != len(pending):
        raise CoverageError(f"{where}: analito pendiente repetido")
    for name in pending:
        _guarded(f"{where}/pending", name)


def validate(raw: Any) -> dict[str, Any]:
    """El fichero entero, comprobado: si algo no cumple, no se sirve nada."""
    _exact("cobertura", raw, TOP_FIELDS)
    if not _iso_day(raw["read_on"]):
        raise CoverageError("cobertura: falta `read_on`: una lectura sin fecha no se contrasta")
    listing = raw["listing"]
    _exact("listado", listing, LISTING_FIELDS)
    _ref("listado", listing["ref"])
    _ref("RIDGE", raw["ridge_source"])
    found = _COUNT.search(listing["count_quote"]) if _text(listing["count_quote"]) else None
    if found is None:
        raise CoverageError("listado: sin el total que declara («( of N )»)")
    for name in ("element_quote", "updates"):
        if not _text(listing[name]):
            raise CoverageError(f"listado: `{name}` vacío")
    # Lo que EMMA dice del listado se enseña: pasa el filtro (la cita, en inglés, es de la fuente).
    _guarded("listado/updates", listing["updates"])
    risks = raw["risks"]
    if not isinstance(risks, list):
        raise CoverageError("cobertura: `risks` es una lista")
    if len(risks) != int(found.group(1)):
        raise CoverageError(
            f"cobertura: {len(risks)} riesgos y el listado declara {found.group(1)}"
        )
    cited = {domain: item.id for domain, item in HRP_RISKS.items()}
    for item in risks:
        _validate_risk(item, cited)
    ids = [item["hrr_id"] for item in risks]
    if len(set(ids)) != len(ids):
        raise CoverageError("cobertura: página de riesgo repetida")
    # Una ficha respalda una fila: la de un riesgo copiada en otra lo daría por respaldado. Solo un
    # informe que enlazan dos páginas (`REPORT_RISK`) va en las dos, y en ninguna más (eso lo dice
    # ya la regla de cada fila).
    holder: dict[str, int] = {}
    for item in risks:
        for ref_id in item["refs"]:
            if ref_id in holder and len(REPORT_RISK.get(ref_id, ())) < 2:
                raise CoverageError(
                    f"cobertura: la ficha {ref_id} está en dos filas "
                    f"({holder[ref_id]} y {item['hrr_id']})"
                )
            holder[ref_id] = item["hrr_id"]
    # Y un informe que enlazan varias páginas está en todas: quitarlo de una dejaría esa fila sin
    # el respaldo que su página publica.
    refs_by_row = {item["hrr_id"]: set(item["refs"]) for item in risks}
    for ref_id, pages in REPORT_RISK.items():
        held = [page for page in pages if ref_id in refs_by_row.get(page, set())]
        if len(pages) > 1 and held and len(held) < len(pages):
            missing_row = next(page for page in pages if page not in held)
            raise CoverageError(
                f"cobertura: el informe {ref_id} falta en la fila {missing_row}, "
                "cuya página lo enlaza"
            )
    # Un dominio que no vigila ningún riesgo del listado vigilaría algo que el HRP no publica.
    watched = {name for item in risks for name in item["domains"]}
    if missing := sorted(_DOMAINS - watched):
        raise CoverageError(f"cobertura: dominios sin ningún riesgo del HRP: {missing}")
    # Cada riesgo citado por un dominio es «cubierto», por ese dominio, en la fila de su página.
    # La fila se busca por la ficha y, si la ficha es la página de un riesgo, también por su
    # dirección: quitarle la ficha a la fila no la libra de la regla. Si lo que cita el dominio es
    # del propio Roadmap (la página de un riesgo o un informe de evidencia), su fila tiene que
    # estar: un informe no tiene dirección que buscar, y sin esto bastaría con quitarlo de su fila
    # para rebajarla. Lo que no es del Roadmap (la ficha de una condición médica, un artículo) no
    # tiene fila, y el dominio aparece «en parte» en alguna (la regla de arriba).
    for domain, ref_id in cited.items():
        card = registry.get(ref_id)
        rows = [
            item for item in risks
            if ref_id in item["refs"]
            or (card.evidence_type == "hrp_risk" and card.url == RISK_PAGE.format(item["hrr_id"]))
        ]
        if card.evidence_type in ROADMAP_SOURCES and not rows:
            raise CoverageError(f"cobertura: {domain} cita {ref_id} y no está en el listado")
        for item in rows:
            if item["coverage"] != "covered" or item["domains"] != [str(domain)]:
                raise CoverageError(
                    f"cobertura: {domain} cita {ref_id} y su fila no dice cubierto por él"
                )
    # Un riesgo que un dominio cita además del suyo tiene su fila, y en ella está ese dominio.
    for domain, extras in ADDITIONAL_HRP_RISKS.items():
        for extra in extras:
            rows = [item for item in risks if extra.id in item["refs"]]
            if not rows or any(str(domain) not in item["domains"] for item in rows):
                raise CoverageError(
                    f"cobertura: {domain} cita además {extra.id} y su fila no lo nombra"
                )
    return dict(raw)


@cache
def _loaded() -> dict[str, Any]:
    return validate(json.loads(COVERAGE_PATH.read_text(encoding="utf-8")))


def load() -> dict[str, Any]:
    """El fichero validado; una copia en cada llamada, para que nadie cambie lo que se sirve."""
    return copy.deepcopy(_loaded())


def cited_refs() -> set[str]:
    """Las fichas del registro que cita la cobertura (la prueba de huérfanas las cuenta)."""
    raw = load()
    refs = {raw["listing"]["ref"], raw["ridge_source"]}
    for item in raw["risks"]:
        refs.update(item["refs"])
    return refs


def _names(items: list[str]) -> str:
    """«a», «a y b», «a, b y c»: los dominios por su nombre, como se leen."""
    joiner = i18n.tr("y", "and")
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} {joiner} {items[-1]}"


def coverage_statement(coverage: str, domains: list[str]) -> str:
    """La cobertura de una fila en una frase, con los nombres de sus dominios.

    En inglés el nombre va delante («by the Bone domain»), así que la plantilla inglesa recibe en
    `article` solo la palabra, en singular o en plural.
    """
    names = [Domain(name).display for name in domains]
    plural = len(names) != 1
    return i18n.loc(COVERAGE_STATEMENT[coverage]).format(
        domains=_names(names) if names else "",
        article=i18n.tr(
            "los dominios" if plural else "el dominio", "domains" if plural else "domain"
        ),
    )


def _risk(item: Mapping[str, Any]) -> dict[str, Any]:
    ridge = Ridge(item["ridge"])
    return {
        "hrr_id": item["hrr_id"],
        "url": RISK_PAGE.format(item["hrr_id"]),
        "title": item["title"],
        "short_title": item["short_title"],
        "status": item["status"],
        "status_display": i18n.loc(STATUS[item["status"]]),
        "hrp_element": item["hrp_element"],
        "last_published": item["last_published"],
        "ridge": {
            "category": str(ridge),
            "display": ridge.display,
            "basis": item["ridge_basis"],
            "basis_display": i18n.loc(RIDGE_BASIS[item["ridge_basis"]]),
            "note": i18n.localized(item["ridge_note"], COVERAGE_PATH),
        },
        "coverage": item["coverage"],
        "coverage_display": i18n.loc(COVERAGE[item["coverage"]]),
        "coverage_statement": coverage_statement(item["coverage"], item["domains"]),
        "domains": [
            {
                "key": name,
                "display": Domain(name).display,
                # Qué parte vigila ese dominio y cuál no: la frase del marco de ExMC, sin copia.
                "scope": amcl_alignment(Domain(name)),
            }
            for name in item["domains"]
        ],
        "reason": i18n.localized(item["reason"], COVERAGE_PATH),
        # Con la forma de toda cita (`registry.cite`): la interfaz las pinta con `EvidenceList`, y
        # la salvedad de alcance de cada ficha va con ella, como en el resto de EMMA.
        "refs": [registry.cite(ref_id).to_dict() for ref_id in item["refs"]],
        "in_catalog": [_analyte(key) for key in item["in_catalog"]],
        "pending": i18n.localized(list(item["pending"]), COVERAGE_PATH),
    }


def _analyte(key: str) -> dict[str, Any]:
    """Una medida o analito de la fuente que el catálogo tiene, como lo nombra la tripulación."""
    code = CATALOG[key]
    descriptive = key in DESCRIPTIVE_ONLY
    return {
        "key": key,
        "display_es": code.display_es,
        "code": code.code,
        "system": str(code.system),
        "system_display": i18n.loc(CODE_SYSTEM_DISPLAY[code.system]),
        "is_standard_code": code.system is CodeSystem.LOINC,
        "unit": code.unit,
        # La unidad como se lee la da el backend, como en el panel de descriptivos: la interfaz
        # no tiene que conocer cada UCUM para pintar la fila.
        "unit_display": display.unit(code.unit),
        "descriptive_only": descriptive,
        "descriptive_display": i18n.loc(DESCRIPTIVE_DISPLAY) if descriptive else None,
    }


def payload() -> dict[str, Any]:
    """La cobertura entera, en el orden del listado del Roadmap."""
    raw = load()
    risks = [_risk(item) for item in raw["risks"]]
    counts = {key: sum(item["coverage"] == key for item in risks) for key in COVERAGE}
    return {
        "note": i18n.loc(NOTE),
        "read_on": raw["read_on"],
        "listing": {
            "source": registry.get(raw["listing"]["ref"]).to_dict(),
            "count_quote": raw["listing"]["count_quote"],
            "element_quote": raw["listing"]["element_quote"],
            "updates": i18n.localized(raw["listing"]["updates"], COVERAGE_PATH),
        },
        "count": len(risks),
        "counts": counts,
        "summary": i18n.loc(SUMMARY).format(total=len(risks), **counts),
        "coverage_display": {key: i18n.loc(word) for key, word in COVERAGE.items()},
        "element_basis": i18n.loc(ELEMENT_BASIS),
        "ridge_note": i18n.loc(RIDGE_NOTE),
        "ridge_source": registry.get(raw["ridge_source"]).to_dict(),
        "pending_note": i18n.loc(PENDING_NOTE),
        "in_catalog_note": i18n.loc(IN_CATALOG_NOTE),
        "risks": risks,
    }
