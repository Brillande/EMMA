"""Registro único de evidencia: una ficha por fuente y todos la citan por identificador.

La especificación del equipo (§3, EvidenceRef) pide `id`, `title`, `url/doi`, `organization`,
`date`, `evidence_type` y `notes`; §2, no mezclar humanos, animales y análogos sin conservar de
dónde sale cada cosa. Estas pruebas siguen el espíritu de la del catálogo de códigos: citar una
fuente que no está en el registro, dejar una ficha que nadie cita, volver a escribir en línea una
fuente ya registrada o presentar como humano un estudio en animales hace fallar la suite.

Lo que no puede comprobar una prueba —que una fecha se leyó de verdad en la fuente— se acota por
el otro lado: un campo sin valor tiene que salir declarado, nunca callado.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import anatomy, guides
from app.advisor import countermeasures
from app.advisor.countermeasures import LibraryError
from app.analysis import baseline_profile, context, cycle_phase, inferred, radiation
from app.environment import conjunction, ephemeris_coverage, habitat
from app.environment.habitat import HabitatReading, excursions
from app.evidence import (
    context_sources,
    credibility,
    cycle_physiology,
    dossier,
    facilities,
    flight_direction,
    hrp_coverage,
    human_datasets,
    imm_radiation,
    instruments_read,
    light_exposure,
    links,
    menopause_physiology,
    mission_profiles,
    nasa_framework,
    radiation_read,
    registry,
    research_countermeasures,
    testbeds,
    tier,
)
from app.evidence.registry import NON_HUMAN, OPTIONAL_FIELDS, POPULATIONS, RegistryError
from app.ingest import cost, fhir, simulator
from app.ingest.codes import Domain
from app.ingest.fhir import EvidenceContext
from app.validation import mmash

APP = Path(registry.__file__).resolve().parents[1]
RAW = json.loads(registry.REGISTRY_PATH.read_text(encoding="utf-8"))
T0 = dt.datetime(2026, 11, 14, 8, 0, tzinfo=dt.UTC)

# Los campos de EvidenceRef en la especificación (§3). `url/doi` es uno de los dos.
SPEC_FIELDS = {"id", "title", "url", "doi", "organization", "date", "evidence_type", "notes"}
# Lo que ya daba la API antes del registro y siguen leyendo la interfaz y las pruebas.
LEGACY_FIELDS = {"title", "source", "url", "relevance", "scope_caveat", "grade"}

# PMID del registro cuyo registro de PubMed aún no está guardado en `evidence_tiers.json`: hay que
# correr `scripts/grade_sources.py`, que sale a la red. Las rondas 10 a 17
# acumularon aquí 61 PMID leídos en PubMed, PMC o Europe PMC sin graduar, porque el guion fecha lo
# guardado en el día y eso caía después del `NOW` fijo de `tests/test_evidence_dossier.py`. La
# decimoctava ronda (§5.38.20) los graduó todos el 2026-10-26 y movió ese `NOW`: ninguno se quedó
# sin registro. Una ficha nueva con PMID se añade aquí, con su ronda y su motivo, hasta que el
# guion la gradúe.
PENDING_PUBMED: set[str] = set()
# La decimonovena ronda (U7, 2026-10-31) volvió a correr `scripts/grade_sources.py` con sus doce
# fichas nuevas (el sentido en vuelo de la función y la cabina): graduó también las catorce que la
# decimoctava ronda había dejado pendientes (U15, U16 y U17), y no queda ninguna sin registro.
# Los artículos de OSD-353 (Brzhozovskiy 2019) y OSD-198 (Rullman 2016), leídos en PMC el
# 2026-10-31 para el mapa de conjuntos de datos humanos (decimonovena ronda, U5), por lo mismo.
PENDING_PUBMED |= {"31261866", "27117806"}
# La batería Cognition (decimonovena ronda, U14): Basner 2015, leído en PMC el 2026-10-31, por lo
# mismo.
PENDING_PUBMED |= {"26564759"}
# Lote ciclo (A4, 2026-11-14): las once fichas de la variación por fase del ciclo y la supresión
# menstrual, leídas en PubMed y PMC ese día. Se graduaron con el `parse` y la puerta de salida de
# `scripts/grade_sources.py` (los once registros traen el artículo; los que tienen MeSH dicen
# «Humans» y ninguno «Animals»), pero guardarlos con fecha 2026-11-14 deja la fecha posterior al
# `NOW` fijo de `tests/test_evidence_dossier.py` (2026-11-01) y el expediente deja de ser
# entregable: se quedan pendientes hasta que una ronda mueva ese `NOW` y corra el guion.
PENDING_PUBMED |= {
    "28725726", "33123618", "31783840", "29175999", "30998226", "35422659", "32499153",
    "31726666", "41545627", "26828607", "24942292",
}
# Lote ciclo (C1, 2026-11-15): las quince fichas de la menopausia y la perimenopausia (sofocos,
# ovulación en la transición, pérdida ósea y lo poco que hay en vuelo), leídas en PubMed y PMC ese
# día. Pendientes por lo mismo que las de A4: su fecha caería después del `NOW` fijo de
# `tests/test_evidence_dossier.py`.
PENDING_PUBMED |= {
    "6472126", "17700502", "31453964", "11400216", "23897855", "21326119", "26926327",
    "42121335", "25686030", "19568209", "39108015", "21976317", "24470067", "39487998",
    "35228092",
}
# Lote ciclo (B3, 2026-11-15): Bull 2019, la duración de la fase lútea, leído en PMC ese día.
# Pendiente por lo mismo que las de A4 y C1.
PENDING_PUBMED |= {"31482137"}
# Lote ciclo (C2, 2026-11-15): STRAW+10 (Harlow 2012, la versión de Menopause), leído en PMC ese
# día, por lo mismo que las de A4: graduarlo con fecha posterior al `NOW` del expediente lo
# dejaría no entregable.
PENDING_PUBMED |= {"22343510"}

# Sitios que todavía escriben por su cuenta la URL de una fuente registrada, con su motivo. Solo
# puede encoger: un sitio nuevo cita por identificador.
RETYPED = {
    # (El catálogo de límites de cabina escribía la URL de OCHMO-TB-002; desde la decimonovena
    # ronda, U3, cada parámetro cita la ficha de su documento y la URL sale del registro.)
    # La procedencia de cada analítica importada apunta a la ficha del estudio en OSDR.
    ("ingest/inspiration4.py", "osd-569"),
    # La URL de descarga del dataset que usa `scripts/fetch_mmash.py`.
    ("validation/mmash.py", "mmash"),
    # Cada hueco del Roadmap tiene su página bajo la dirección del listado, y lo leído cita
    # la página concreta de cada uno.
    ("data/nasa_framework_read.json", "hrr-gaps"),
    # El perfil de misión nombra con su dirección las páginas que leyó sin citar; dos de ellas
    # tienen ficha desde los bancos de prueba (decimocuarta ronda, C9), que sí las citan.
    ("data/mission_profiles.json", "nasa-hrp-step1-analogs"),
    ("data/mission_profiles.json", "nasa-hera-comm-delays"),
    # Una tercera, la de los récords de la ISS, tiene ficha desde la decimoctava ronda (U19), que
    # la cita en las fuentes del contexto. (Las dos frases del Apéndice E del bloque del IMM, que
    # también escribían su dirección, citan desde entonces su ficha por identificador.)
    ("data/mission_profiles.json", "nasa-iss-astronaut-record-holders"),
}


def _cited() -> dict[str, set[str]]:
    """Quién cita cada ficha. Un sitio nuevo que cite se añade aquí o deja fichas huérfanas."""
    cited: dict[str, set[str]] = {}

    def add(ref_id: str, where: str) -> None:
        cited.setdefault(ref_id, set()).add(where)

    for item in links.HRP_RISKS.values():
        add(item.id, "evidence/links.py")
    for group in links.OSDR_BY_DOMAIN.values():
        for item in group:
            add(item.id, "evidence/links.py")
    for known in context._KNOWLEDGE.values():
        for item in known.get("evidence", ()):
            add(item.id, "analysis/context.py")
    add(context.LIMITS_SOURCE.id, "analysis/context.py")
    for citations in context.standard_evidence().values():
        for citation in citations:
            add(citation.id, "analysis/context.py")
    add(inferred.BMD_SOURCE.id, "analysis/inferred.py")
    add(radiation.ORION_SOURCE.id, "analysis/radiation.py")
    # La horquilla por tipo de radiación y los límites a corto plazo (decimocuarta ronda, C7).
    add(radiation.TEPC_SOURCE.id, "analysis/radiation.py")
    add(radiation.SHORT_TERM_SOURCE.id, "analysis/radiation.py")
    add(mmash.DATASET.id, "validation/mmash.py")
    # Lo que dice la literatura de la cobertura de la hora y los conjuntos de varias semanas
    # donde se podría medir (decimosexta ronda, E1; hallazgo 29). Ninguno decide nada.
    for ref_id in (*mmash.FAMILY_BASELINE_LITERATURE, *mmash.MULTI_WEEK_CANDIDATES):
        add(ref_id, "validation/mmash.py")
    # Los analitos de la región «hígado», sin nivel propio (decimoquinta ronda, D11).
    add(anatomy.LIVER_SOURCE.id, "anatomy.py")
    # El límite de carrera igual para toda edad y sexo, en el perfil de línea base (decimosexta
    # ronda, E19).
    add(baseline_profile.LIMIT_SOURCE.id, "analysis/baseline_profile.py")
    # Los pulmones, sin nivel propio, y la ficha de cada hito de «Momento» (decimosexta, E13).
    add(anatomy.LUNG_SOURCE.id, "anatomy.py")
    # La capa de investigación de cada región y la instalación del cerebro (decimonovena, U16).
    for region in anatomy.REGIONS:
        for item in region.research_refs:
            add(item.id, "anatomy.py")
        if region.research_facility is not None:
            add(region.research_facility.id, "anatomy.py")
        # Para qué sirve cada órgano (vigésima ronda, unidad 2).
        for item in region.function_refs:
            add(item.id, "anatomy.py")
    for milestones in (*anatomy.POSTFLIGHT_SOURCES, *anatomy.PREFLIGHT_SOURCES):
        add(milestones.citation.id, "anatomy.py")
    for measure in countermeasures.library().values():
        if measure.protocol_ref is not None:
            add(measure.protocol_ref.id, "data/countermeasures.json")
    # El marco de NASA leído (décima ronda): cada documento del que se declara lectura.
    for ref_id in nasa_framework.read()["sources"]:
        add(ref_id, "data/nasa_framework_read.json")
    for ref_id in mission_profiles.cited_refs():
        add(ref_id, "data/mission_profiles.json")
    # La PVT y las escalas de autoinforme, leídas (décima ronda, F3).
    for ref_id in instruments_read.read()["sources"]:
        add(ref_id, "data/instruments_read.json")
    # Dónde se procesa cada medida, leído (undécima ronda, F2).
    for ref_id in cost.cited_refs():
        add(ref_id, "data/measurement_cost.json")
    # La exposición personal a la luz, leída (undécima ronda, F3).
    for ref_id in light_exposure.cited_refs():
        add(ref_id, "data/light_exposure_read.json")
    # Los requisitos que se enseñan sin evaluar junto a la luz, el agua y la microbiología
    # (decimoquinta ronda, D18).
    for ref_id in habitat.cited_refs():
        add(ref_id, "environment/habitat.py")
    # Los bancos de prueba y las dos validaciones (decimocuarta ronda, C9).
    for ref_id in testbeds.cited_refs():
        add(ref_id, "data/testbeds.json")
    # El sentido en vuelo junto a la línea base, leído (decimoquinta ronda, D14).
    for ref_id in flight_direction.cited_refs():
        add(ref_id, "data/flight_direction_read.json")
    # EPM y Biolab, de la instalación a la aplicación (decimoquinta ronda, D3).
    for ref_id in facilities.cited_refs():
        add(ref_id, "data/facilities_read.json")
    # El mapa de conjuntos de datos humanos y CIPHER (decimoquinta ronda, D2).
    for ref_id in human_datasets.cited_refs():
        add(ref_id, "data/human_datasets_read.json")
    # La clase de respaldo de las derivas del simulador (decimosexta ronda, E18).
    for ref_id in simulator.cited_refs():
        add(ref_id, "ingest/simulator.py")
    # La conjunción solar: el ángulo de Horizons y el umbral de JPL (decimoquinta ronda, D6).
    for ref_id in conjunction.cited_refs():
        add(ref_id, "environment/conjunction.py")
    # Los 22 riesgos del Roadmap y lo que EMMA hace con cada uno; el de cálculos renales, citado
    # además por el dominio genitourinario y por la frase de su región (decimosexta ronda, E9).
    for ref_id in hrp_coverage.cited_refs():
        add(ref_id, "data/hrp_risks_coverage.json")
    # Lo que publica el IMM sobre radiación (sección «Radiación», 2026-11-14).
    for ref_id in imm_radiation.cited_refs():
        add(ref_id, "data/imm_ars.json")
    # La variación por fase del ciclo menstrual y la supresión menstrual (lote ciclo, A4).
    for ref_id in cycle_physiology.cited_refs():
        add(ref_id, "data/cycle_physiology_read.json")
    # La menopausia y la perimenopausia: sofocos, ciclos sin ovulación, hueso y vuelo (lote
    # ciclo, C1).
    for ref_id in menopause_physiology.cited_refs():
        add(ref_id, "data/menopause_physiology_read.json")
    # La duración de la fase lútea con que la línea base sitúa la fase (lote ciclo, B3).
    for ref_id in cycle_phase.cited_refs():
        add(ref_id, "analysis/cycle_phase.py")
    for group in links.ADDITIONAL_HRP_RISKS.values():
        for item in group:
            add(item.id, "evidence/links.py")
    for region in anatomy.REGIONS:
        for item in region.note_refs:
            add(item.id, "anatomy.py")
        # La capa de evidencia de investigación del hígado (decimoséptima ronda, U16).
        for item in region.research_refs:
            add(item.id, "anatomy.py")
    # La especificación de UCUM, por la comparación de unidades (decimosexta ronda, E5).
    add(fhir.UCUM_REF, "ingest/fhir.py")
    # La definición de `Observation.focus`, por el alimento de la valoración (decimoctava, U2).
    add(fhir.FOCUS_REF, "ingest/fhir.py")
    # El aviso de HERA, la fase del ciclo solar y el fin del refugio (decimosexta ronda, E8).
    for ref_id in radiation_read.cited_refs():
        add(ref_id, "data/radiation_read.json")
    # NASA-STD-7009B y su guía, leídas para la credibilidad de cada capa (decimosexta ronda, E10).
    for ref_id in credibility.cited_refs():
        add(ref_id, "data/credibility_read.json")
    # La API de Horizons: un rango de días en una sola consulta (decimosexta ronda, E6).
    for ref_id in ephemeris_coverage.cited_refs():
        add(ref_id, "environment/ephemeris_coverage.py")
    # Las contramedidas en investigación, aparte de la biblioteca (decimosexta ronda, E15).
    for ref_id in research_countermeasures.cited_refs():
        add(ref_id, "data/countermeasures_research.json")
    # Las fuentes del contexto del equipo que no tenían ficha, el enunciado del reto incluido
    # (decimoséptima ronda, U8).
    for ref_id in context_sources.cited_refs():
        add(ref_id, "data/context_sources_read.json")
    # Las guías de medida y el glosario, con las frases que sostienen cada paso (unidad 3).
    for ref_id in guides.guides_cited_refs():
        add(ref_id, "data/measurement_guides.json")
    for ref_id in guides.glossary_cited_refs():
        add(ref_id, "data/glossary.json")
    # El docstring de la biblioteca nombra por identificador el estudio que motivó el campo de
    # efectos adversos: es una cita en prosa, y solo cuenta si la ficha existe.
    for ref_id in registry.registry():
        if f"`{ref_id}`" in (countermeasures.__doc__ or ""):
            add(ref_id, "advisor/countermeasures.py")
    return cited


def _resolved(node: Any) -> Iterator[dict[str, Any]]:
    """Toda referencia que aparezca en una respuesta, esté donde esté."""
    if isinstance(node, dict):
        if {"title", "source", "url"} <= node.keys():
            yield node
        for value in node.values():
            yield from _resolved(value)
    elif isinstance(node, list):
        for value in node:
            yield from _resolved(value)


def _check_resolved(item: dict[str, Any]) -> None:
    """Una referencia en una respuesta es la ficha del registro, sin retocar ni rebajar."""
    assert "id" in item, f"referencia escrita en línea, sin ficha: {item['title']}"
    ref = registry.get(item["id"])
    assert item.keys() >= SPEC_FIELDS
    assert item["population"] == ref.population
    assert item["evidence_context"] == (ref.evidence_context and str(ref.evidence_context))
    assert item["unverified"] == list(ref.unverified)
    for name in OPTIONAL_FIELDS:
        # Un campo sin valor sale declarado: pendiente, no aplicable o fuera del enumerado.
        declared = {*item["unverified"], *item["not_applicable"], *item["outside_enum"]}
        assert item[name] is not None or name in declared
    if ref.population in NON_HUMAN:
        assert item["population_display"] != POPULATIONS["human"]
        assert item["notes"], f"{ref.id}: fuente con animales sin salvedad de alcance"
    if ref.population == "animal":
        # El nivel de evidencia tampoco puede decir lo contrario que la ficha.
        assert item["grade"]["preclinical"] or item["grade"]["tier"] == "desconocido"


# --------------------------------------------------------------------------- #
# El registro
# --------------------------------------------------------------------------- #


def test_every_reference_carries_the_fields_of_the_specification() -> None:
    assert registry.registry(), "el registro no puede estar vacío"
    for raw in RAW["references"]:
        # Lo que no se sabe se escribe `null`: una clave omitida no declara nada. Las listas
        # opcionales (y las personas, desde la decimosexta ronda) se omiten cuando no hay nada.
        optional = {
            "not_applicable", "outside_enum", "authors", "named_people",
            # Decimonovena ronda (U4): la afiliación por persona y las organizaciones nombradas.
            "affiliations", "named_organizations",
        }
        assert raw.keys() - optional == registry._REQUIRED, raw["id"]
    for ref in registry.registry().values():
        resolved = ref.to_dict()
        assert resolved.keys() >= SPEC_FIELDS
        assert ref.title and ref.source and (ref.url or ref.doi)


def test_identifiers_are_unique() -> None:
    ids = [raw["id"] for raw in RAW["references"]]
    assert len(ids) == len(set(ids)) == len(registry.registry())
    twice = {"references": [RAW["references"][0], RAW["references"][0]]}
    with pytest.raises(RegistryError, match="duplicado"):
        registry.parse(twice)


def test_every_citation_exists_and_no_reference_is_an_orphan() -> None:
    cited = _cited()
    known = set(registry.registry())
    assert set(cited) <= known, f"citadas sin ficha: {set(cited) - known}"
    assert known <= set(cited), f"fichas que nadie cita: {known - set(cited)}"
    # Los tres sitios que tenían cada uno su copia citan ahora por identificador.
    sites = set().union(*cited.values())
    assert {"evidence/links.py", "analysis/context.py", "data/countermeasures.json"} <= sites


def test_the_countermeasure_library_cites_by_identifier_only() -> None:
    raw = json.loads(countermeasures.LIBRARY_PATH.read_text(encoding="utf-8"))
    cited = [item["protocol_ref"] for item in raw["countermeasures"] if item["protocol_ref"]]
    assert cited
    for reference in cited:
        assert reference.keys() == {"ref", "relevance"}, reference
        assert reference["ref"] in registry.registry()


def test_citing_a_reference_that_is_not_registered_fails(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="no está en el registro"):
        registry.cite("no-existe", "inventada")
    raw = json.loads(countermeasures.LIBRARY_PATH.read_text(encoding="utf-8"))
    entry = next(item for item in raw["countermeasures"] if item["protocol_ref"])
    for bad in (
        {"ref": "no-existe", "relevance": "x"},
        # La forma anterior, con la ficha escrita en línea, ya no entra.
        {"title": "t", "source": "s", "url": "https://example.org", "relevance": "x"},
        # Citar sin decir qué respalda de esta acción tampoco.
        {"ref": entry["protocol_ref"]["ref"], "relevance": None},
        {"ref": entry["protocol_ref"]["ref"], "relevance": " "},
    ):
        path = tmp_path / "library.json"
        path.write_text(
            json.dumps({"countermeasures": [{**entry, "protocol_ref": bad}]}), encoding="utf-8"
        )
        with pytest.raises(LibraryError):
            countermeasures.load(path)


def test_a_registered_source_is_not_typed_again_elsewhere() -> None:
    """La misma fuente escrita en dos sitios es lo que el registro vino a quitar."""
    sources = [*APP.rglob("*.py"), *(APP / "data").glob("*.json")]
    found = set()
    for path in sources:
        if path == registry.REGISTRY_PATH:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for ref in registry.registry().values():
            if ref.url is not None and ref.url in text:
                found.add((path.relative_to(APP).as_posix(), ref.id))
    assert found == RETYPED


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"date": None, "drop": "date"}, "faltan campos"),
        ({"inventado": 1}, "campos desconocidos"),
        ({"id": "OSD 288"}, "identificador"),
        ({"url": None, "doi": None}, "sin `url` ni `doi`"),
        ({"url": "http://example.org"}, "https"),
        ({"date": "2017-13"}, "ISO 8601"),
        ({"date": "hacia 2017"}, "ISO 8601"),
        ({"organization": " "}, "vacío"),
        ({"evidence_type": "estudio"}, "evidence_type"),
        # El entorno es el enumerado de las observaciones: "humano" no es un entorno.
        ({"evidence_context": "human"}, "evidence_context"),
        ({"population": "astronauts"}, "population"),
        ({"pmid": "PMID 22272509"}, "pmid"),
        ({"not_applicable": ["evidence_context"]}, "no aplicable"),
        ({"not_applicable": ["title"]}, "no existe"),
        # Una fuente con animales no se registra sin decir qué no mide en personas.
        ({"notes": None}, "animales"),
        # Fuera del enumerado solo cabe un campo con enumerado, vacío y no excusado, y con motivo.
        ({"outside_enum": ["date"]}, "sin enumerado"),
        ({"outside_enum": ["evidence_context"]}, "no puede tener valor"),
        ({"evidence_context": None, "not_applicable": ["doi", "evidence_context"],
          "outside_enum": ["evidence_context"]}, "no puede tener valor"),
        ({"evidence_context": None, "outside_enum": ["evidence_context"], "notes": "Ratones."},
         "por qué"),
    ],
)
def test_the_registry_rejects_what_breaks_its_contract(
    change: dict[str, Any], reason: str
) -> None:
    entry = copy.deepcopy(next(raw for raw in RAW["references"] if raw["id"] == "osd-288"))
    entry.update(change)
    if dropped := entry.pop("drop", None):
        del entry[dropped]
    with pytest.raises(RegistryError, match=reason):
        registry.parse({"references": [entry]})


# --------------------------------------------------------------------------- #
# Lo que no está verificado se declara
# --------------------------------------------------------------------------- #


def test_every_reference_declares_its_context_and_its_population() -> None:
    for ref in registry.registry().values():
        # El entorno es el enumerado que ya llevan las observaciones, no otro.
        assert ref.evidence_context is None or isinstance(ref.evidence_context, EvidenceContext)
        for name in ("evidence_context", "population"):
            value = getattr(ref, name)
            pending = name in ref.unverified
            excused = name in ref.not_applicable
            outside = name in ref.outside_enum
            # Exactamente una de las cuatro: tiene valor, está pendiente, no procede o se leyó y
            # ningún valor del enumerado la cubre.
            assert [value is not None, pending, excused, outside].count(True) == 1, (ref.id, name)


def test_a_missing_field_is_null_and_listed_never_guessed() -> None:
    for ref in registry.registry().values():
        resolved = ref.to_dict()
        missing = {name for name in OPTIONAL_FIELDS if resolved[name] is None}
        declared = {*resolved["unverified"], *resolved["not_applicable"], *resolved["outside_enum"]}
        assert missing == declared, ref.id
        assert len(resolved["unverified_display"]) == len(resolved["unverified"])
        assert len(resolved["outside_enum_display"]) == len(resolved["outside_enum"])
        if ref.evidence_type is None:
            # Leída y sin clase del registro que la cubra (un vídeo, una publicación en X:
            # decimoséptima ronda, U8), lo dice; si no, queda sin clasificar.
            expected = (
                registry.OUTSIDE_ENUM if "evidence_type" in ref.outside_enum
                else registry.UNCLASSIFIED
            )
            assert resolved["evidence_type_display"] == expected, ref.id
    # La norma no tiene entorno de estudio: no cuenta como pendiente, y lo dice.
    standard = registry.get("ochmo-tb-002").to_dict()
    assert standard["population_display"] == registry.NOT_APPLICABLE
    assert "evidence_context" not in standard["unverified"]


def test_dates_and_identifiers_agree_with_the_citation_text() -> None:
    """La fecha y los identificadores de la ficha son los que se leen en la cita, no otros."""
    for ref in registry.registry().values():
        if ref.date is not None:
            assert ref.date[:4] in ref.source, f"{ref.id}: el año no está en la cita"
        if ref.doi is not None:
            assert ref.doi in ref.source or ref.doi in (ref.url or ""), ref.id
        if ref.pmid is not None:
            assert ref.pmid in ref.source or ref.pmid in (ref.url or ""), ref.id


# --------------------------------------------------------------------------- #
# Minas conocidas (CLAUDE.md): el registro las dice tal cual
# --------------------------------------------------------------------------- #


def test_osd_288_is_mice_on_the_iss_not_astronauts() -> None:
    ref = registry.get("osd-288")
    assert (ref.population, ref.evidence_context) == ("animal", EvidenceContext.ISS)
    assert ref.evidence_type == "dataset"
    assert ref.notes is not None
    # 12 ratones volaron; el conjunto tiene 9 muestras (3 por grupo). Leído en OSDR el 2026-10-14.
    assert "murino" in ref.notes and "9 muestras de bazo" in ref.notes
    assert ref.notes.startswith("Modelo murino: 12 ratones volaron")
    assert "NO mide signos vitales humanos" in ref.notes
    assert "RNA-Seq de bazo de ratón tras 35 días en la ISS" in (links.OSD_288.relevance or "")


def test_osd_343_open_files_are_mouse_and_the_card_says_so() -> None:
    ref = registry.get("osd-343")
    assert ref.population == "human_and_animal"
    assert ref.notes is not None and "ratón" in ref.notes


def test_mmash_is_healthy_people_on_the_ground_not_flight() -> None:
    ref = mmash.DATASET
    assert (ref.population, ref.evidence_context) == ("human", EvidenceContext.GROUND)
    assert ref.notes is not None
    for said in ("22 personas sanas", "24 h", "en Tierra", "no es fisiología de vuelo"):
        assert said in ref.notes


# --------------------------------------------------------------------------- #
# Con el nivel de evidencia (`evidence/tier.py`): una sola verdad por fuente
# --------------------------------------------------------------------------- #


def test_every_registered_pmid_is_graded_or_declared_pending() -> None:
    cited = {ref.pmid for ref in registry.registry().values() if ref.pmid is not None}
    assert cited - set(tier._records()) == PENDING_PUBMED
    for ref in registry.registry().values():
        graded = ref.to_dict()["grade"]
        # El PMID de la ficha es el que se gradúa, esté en el texto de la cita o no.
        assert graded["pmid"] == ref.pmid
        if ref.pmid in PENDING_PUBMED:
            # Sin registro guardado no se presenta como leído en PubMed.
            assert "retrieved" not in graded


def test_the_population_agrees_with_the_pubmed_record() -> None:
    checked = 0
    for ref in registry.registry().values():
        signals = ref.to_dict()["grade"]["signals"]
        if not signals:
            continue
        checked += 1
        human, animal = signals.get("humanos", False), signals.get("animal", False)
        if "population" in ref.not_applicable and ref.to_dict()["grade"]["tier"] == "guia_clinica":
            # Una norma no estudia a nadie: el MeSH «Humans» de su registro dice de quién habla,
            # no una población estudiada (Task Force 1996, graduada en la decimoctava ronda). Solo
            # la exime su registro de PubMed, no la ficha: un estudio marcado «no aplica» falla.
            continue
        if human and not animal:
            assert ref.population == "human", ref.id
        if animal and not human:
            assert ref.population == "animal", ref.id
    assert checked, "ninguna ficha con registro de PubMed: la prueba no comprueba nada"


# --------------------------------------------------------------------------- #
# Lo que sale por la API
# --------------------------------------------------------------------------- #


def test_the_resolved_reference_keeps_what_the_api_already_gave() -> None:
    for domain in Domain:
        for item in links.evidence_for(domain):
            resolved = item.to_dict()
            assert resolved.keys() >= LEGACY_FIELDS
            assert resolved["scope_caveat"] == resolved["notes"]
            _check_resolved(resolved)


# --------------------------------------------------------------------------- #
# Lo que la ficha enseña de su nota sin abrir nada (`scope_in_view`)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("note", "lead"),
    [
        ("Mide en Tierra. Leída el 2026-10-13: nada más.", "Mide en Tierra."),
        ("Leída el 2026-10-13. Es una norma.", None),
        ("Sin ninguna lectura fechada. Otra frase.", "Sin ninguna lectura fechada. Otra frase."),
        # Un punto dentro de una cita o de un paréntesis no es fin de frase.
        ("Mide en Tierra. Dice «sin datos. Nada» leído el 2026-10-14.", "Mide en Tierra."),
        ("Mide en Tierra. Página (versión vieja. Otra) releída el 2026-10-14.", "Mide en Tierra."),
        ("Una frase. Otra (citada luego 2026-10-13) sigue.", "Una frase."),
        # Una inicial o una abreviatura no acaban frase: la bitácora no sale a la vista a medias.
        ("Mide en Tierra. Registro de J. Smith leído el 2026-10-13.", "Mide en Tierra."),
        ("Mide algo. Law et al. lo leyeron; leído el 2026-10-13.", "Mide algo."),
        ("Es una norma. Según su Rev. C, leída el 2026-10-13.", "Es una norma."),
    ],
)
def test_the_lead_is_what_the_note_says_before_its_first_dated_reading(
    note: str, lead: str | None,
) -> None:
    assert registry._lead(note) == lead


def test_what_a_card_shows_in_view_is_its_own_note_cut_and_never_rewritten() -> None:
    folded = 0
    for ref in registry.registry().values():
        shown = ref.scope_in_view
        if ref.notes is None:
            assert shown is None
            continue
        if shown is None or shown == ref.notes:
            folded += shown is None
            continue
        folded += 1
        # Un prefijo literal, cortado en un fin de frase, sin ninguna lectura fechada dentro.
        assert ref.notes.startswith(shown), ref.id
        assert shown.endswith(".") and ref.notes[len(shown)] == " ", ref.id
        assert registry._READ_DATE.search(shown) is None, ref.id
    assert folded, "ninguna nota se pliega: la prueba no comprueba nada"


# Las fichas cuya nota se corta (alcance a la vista, nota entera plegada) y la que va entera a la
# vista por no ser solo de personas, revisadas a mano frase a frase el 2026-10-20. El corte es una
# regla sobre texto libre: si editar una nota cambia lo que la tripulación ve sin abrir nada,
# esta prueba lo dice y alguien relee lo que queda a la vista antes de actualizarla.
CUT_REVIEWED = {
    "osd-288", "osd-569", "osd-343", "nasa-twins-study", "hrp-sans-evidence-report",
    "hrr-urinary-retention", "kerstman-2012", "hrp-food-system-evidence-report", "mmash",
    "hayslip-2026",
    # El informe del IMM (2026-11-14): a la vista, qué es y qué calcula («no un estudio»), sin la
    # bitácora de lectura.
    "imm-ranking-2015",
    # Decimonovena ronda (U16, 2026-10-31): a la vista queda de quién es el informe (sobre todo
    # pacientes y roedores; tripulantes, análogos y animales; vuelo, análogos y animales en el
    # muscular, que dejó de enseñarse entero) y que no mide a este tripulante; las citas y la
    # bitácora, plegadas.
    "hrp-cns-radiation-evidence-report", "hrp-immune-evidence-report",
    "hrp-muscle-evidence-report",
    # Las páginas de los bancos de prueba (decimocuarta ronda, C9), revisadas el 2026-10-21: lo que
    # queda a la vista es qué clase de página es («no un estudio»), sin la bitácora de lectura.
    "nasa-hrp-step1-analogs", "bnl-nsrl", "nasa-bed-rest-agbresa", "nasa-chapea-crew-2",
    "nasa-mmea-program", "nasa-mmea-announcement", "nasa-hera-comm-delays",
    # Las de los bancos y columnas de la decimoquinta ronda (D5), revisadas el 2026-10-22: a la
    # vista, también solo qué clase de página es («no un estudio»).
    "nasa-hera-45-day-2024", "nasa-neemo-studies", "nasa-neemo-19",
    "nasa-jsc-space-suits-argos", "nasa-parabolic-flight",
    # Decimocuarta ronda (C7, 2026-10-21): a la vista queda qué mide (el campo de radiación en el
    # Spacelab, no personas) y que EMMA usa sus Q fuera de ese entorno; las citas, plegadas.
    "badhwar-1992-sls1-tepc",
    # Decimoquinta ronda (D14, 2026-10-22): a la vista, sobre quién y cómo se midió y lo que el
    # resumen no nombra (el ojo, la SDNN, el lado de la yugular); la bitácora de lectura, plegada.
    "hughson-2012-cardiovascular-iss", "xu-2013-hrv-sleep-iss", "fraser-2012-heart-rate-iss",
    "norsk-2015-ambulatory-bp-iss", "otsuka-2016-hrv-time-structure",
    "stahn-2017-core-temperature", "zwart-2014-body-mass", "smith-2005-bone-markers-mir",
    "sirek-2014-onsd-iss", "marshall-goebel-2019-ijv", "barger-2014-sleep-spaceflight",
    "trudel-2022-hemolysis",
    # EPM y Biolab (decimoquinta ronda, D3), revisadas el 2026-10-22: a la vista, qué clase de
    # documento es cada página y, en los dos artículos, sobre quién se midió (células de rata;
    # cinco astronautas) con su frase; la bitácora de lectura, plegada.
    "esa-epm", "esa-biolab", "nasa-iss-research-explorer", "esa-iss-status-report-84",
    "esa-image-2015-triplelux", "thiel-2017-macrophage-microgravity", "petit-2019-local-sleep-iss",
    # Decimoquinta ronda (D2, 2026-10-22): a la vista queda qué es cada fuente (N = 1, cuatro
    # civiles y tres días, una página de programa que no es un estudio); la bitácora, plegada.
    "garrett-bakelman-2019", "overbey-2024-soma", "jones-2024-inspiration4", "nasa-cipher",
    "nasa-cipher-experiments-2023",
    # Decimoquinta ronda (D6, 2026-10-22): a la vista, qué es cada página (el manual de Horizons,
    # «no un estudio»; la nota de JPL de 2015, que los dos grados son el periodo de una pausa de
    # órdenes a robots y no un umbral de enlace); las citas, plegadas.
    "jpl-horizons-manual", "jpl-2015-mars-conjunction",
    # Decimosexta ronda (E11, 2026-10-23): a la vista, qué es cada fuente (las diez investigaciones
    # del Twins Study sin sus datos; reposo en cama en Tierra, no vuelo; un catálogo que no aloja
    # datos); la bitácora de lectura, plegada.
    "nasa-twins-study-research", "clement-2022-agbresa", "osd-51", "nasa-open-data-portal",
    # Decimosexta ronda (E16, 2026-10-23): a la vista, sobre quién, dónde y cómo se midió (vuelos
    # cortos del transbordador, la Mir, la ISS) y, en Paul 2020, que el NLR es de los roedores;
    # la bitácora de lectura, plegada.
    "baevsky-2007-autonomic-iss", "prisk-1995-gas-exchange-sls", "conkin-2017-spo2-microgravity",
    "piltch-2025-sleep-mir", "jones-2022-sleep-pvt-iss", "dev-2024-cognition-iss",
    "flynn-evans-2016-circadian-iss", "smith-2012-bone-resistance-iss",
    "smith-2015-renal-stone-iss", "smith-2005-nutrition-iss", "agha-2020-salivary-iss",
    "paul-2020-nlr",
    # Decimosexta ronda (E9, 2026-10-23): a la vista, de dónde salen los datos del informe de
    # cálculos renales y que lo único animal es un estudio con cerdos sin reproducir en personas;
    # la bitácora de lectura, plegada.
    "hrp-renal-stone-evidence-report",
    # Decimosexta ronda (E18, 2026-10-23): a la vista, sobre quién y cuándo se midió (y lo que el
    # resumen no nombra: la estación); las frases leídas y la bitácora, plegadas.
    "baevsky-1997-holter-mir", "otsuka-2022-one-year-hrv",
    "buchheim-2019-inflammaging-cosmonauts",
    # Decimosexta ronda (E8, 2026-10-23): a la vista, qué clase de documento es cada una (artículos
    # de la agencia previos al vuelo, la nota de 2024 con su previsión, el preprint sin revisión y
    # medido con un instrumento en Marte); las frases y la bitácora de lectura, plegadas.
    "nasa-artemis1-radiation-research", "nasa-artemis2-eyes-on-sun",
    "nasa-noaa-solar-maximum-2024", "lowe-2025-sep-nowcasting-mars",
    # Decimosexta ronda (E6, 2026-10-23): a la vista, que es la documentación de la API de
    # Horizons y no un estudio; lo leído y lo buscado sin encontrar, plegado.
    "jpl-horizons-api",
    # Decimosexta ronda (E12, 2026-10-23): las páginas de los bancos de prueba nuevos y de las
    # fichas de misión; a la vista, solo qué clase de página es («no un estudio»).
    "nasa-analog-missions", "nasa-hera-mission", "nasa-antarctic-stations-mission",
    "nasa-nsrl-mission", "bnl-nsrl-about", "nasa-chapea-habitat", "nasa-kraken-2023",
    "nasa-jsc-nbl", "nasa-altitude-chambers", "nasa-altitude-chamber-complex",
    # Decimosexta ronda (E15, 2026-10-23): a la vista, qué es (un documento de divulgación de 12
    # páginas, «no un estudio»); de dónde sale su fecha y lo leído, plegado.
    "nasa-body-in-space-2022",
    # Decimoséptima ronda (U8, 2026-10-26): las fuentes del contexto sin ficha; a la vista, qué es
    # cada una («no un estudio», «no el enunciado del reto») y, en la del reto, leído en la
    # decimonovena ronda (U2, 2026-10-31), que es la página del reto y no un estudio; lo leído y
    # lo no leído, plegado.
    "space-apps-2026-health-monitoring-challenge", "nasa-space-apps-2026-announcement",
    "space-apps-2026-participant-faqs", "nasa-living-in-space", "nasa-osdr-portal",
    "esa-kids-columbus-10-years", "estacionespacial-columbus", "naukas-stuhlinger-letter",
    "nasa-iss-humanity-lab-video", "x-miriamgonp-liver-render", "x-israeldfirzt-protoclone",
    # Decimoséptima ronda (U10, 2026-10-26): a la vista, sobre quién, cuánto tiempo y en qué
    # entorno se midió, y que no es vuelo (o, en el resumen de Sirius-21, que no da resultados);
    # las frases leídas y la bitácora, plegadas.
    "satish-2012-co2-decision-making", "manzey-1998-co2-performance", "gundel-1998-co2-sleep",
    "van-hoy-2026-co2-sleep-analog", "christian-2024-hdtbr-co2-sleep",
    "meiselman-2000-variety-monotony", "ntrs-20220014371",
    "osd-195", "osd-198", "osd-353", "osd-370", "osd-942", "osd-946",
    # Decimoctava ronda (U17, 2026-10-26): a la vista, sobre quién y cuándo se midió (antes,
    # durante o después del vuelo; Skylab, el transbordador) y, en las dos revisiones, que no son
    # estudios con medidas propias (la de Strollo 1999, con animales); lo leído, plegado.
    "strollo-1998-testicular-androgen", "strollo-1999-hormonal-review",
    "smith-2011-thyroid-shuttle", "ntrs-19750006310", "meck-2004-orthostatic-shuttle",
    "gimunova-2024-reproductive-review",
    # Decimoctava ronda (U19, 2026-10-26): las seis direcciones de §17 que quedaban sin ficha; a la
    # vista, qué es cada una («no un estudio», y de la estación, «sin ningún dato de salud»); lo
    # leído y lo no leído, plegado.
    "nasa-hrp-roi", "nasa-iss-astronaut-record-holders", "astroquery-docs",
    "nasa-std-3001-appendix-e", "beyondtheprotocol-polaris", "bonilista-zerokeyusb",
    # Decimoctava ronda (U15, 2026-10-26): a la vista, que es el artículo de resultados de AGBRESA
    # sobre la capacidad física, en reposo en cama en Tierra y no en vuelo, y que no da las demás
    # áreas del estudio; las frases leídas y la bitácora, plegadas.
    "kramer-2021-agbresa",
    # Decimoctava ronda (U18, 2026-10-26): la calibración y la formación del coste de medir. A la
    # vista, qué es cada fuente (el campo de radiación de Columbus, no personas; una página del
    # SRAG, «no es un estudio»; una hoja comercial fuera del enumerado; un póster de un análogo en
    # Tierra, «no es vuelo»); las frases leídas y la bitácora, plegadas.
    "berger-2017-dosis-3d-dostel", "nasa-srag-protect-astronauts",
    "philips-actiwatch-service-offerings-2016", "ntrs-20190000238",
    # Decimoctava ronda (U16, 2026-10-26): a la vista, sobre quién, dónde y cómo se midió (la Mir
    # con sangre del dedo, la ISS, el reposo en cama junto al vuelo, la RMN que no da
    # concentraciones); las frases leídas y la bitácora, plegadas.
    "markin-1998-blood-biochemistry-mir", "grigoriev-1994-biochemical-status",
    "zwart-2022-albumin-iss", "smith-2015-magnesium-iss", "zheng-2023-time-resolved-iss",
    "stroud-2022-metabolomics-iss", "lee-2020-arterial-iss", "zwart-2013-iron-iss",
    # Decimoctava ronda (U5, 2026-10-26): el informe de SANS de 2022; a la vista, sobre qué junta
    # (tripulaciones, reposo en cama, modelos y animales) y que no mide a este tripulante, como el
    # de 2017; lo leído, plegado.
    "hrp-sans-evidence-report-2022",
    # Decimonovena ronda (U13, 2026-10-31): los informes de evidencia del riesgo sensoriomotor y
    # del de músculo y capacidad aeróbica, leídos en parte para cuatro indicadores descriptivos. A
    # la vista, qué junta cada uno (vuelo, análogos en Tierra, animales y células) y que no mide a
    # este tripulante, con lo que EMMA cita de ellos; las lecturas fechadas, plegadas.
    "hrp-sensorimotor-evidence-report", "hrp-muscle-aerobic-evidence-report",
    # Decimoctava ronda (U14, 2026-10-26): a la vista, qué es la página de NOAA («no un estudio»,
    # no dice la fase) y que no lleva fecha; la cifra copiada de sus gráficas y la bitácora,
    # plegadas.
    "noaa-swpc-solar-cycle-progression",
    # Decimonovena ronda (U3, 2026-10-31): los trece informes del HRP cuya población, ya leída, es
    # humana y animal; a la vista, qué junta cada uno y que no mide a este tripulante, como el de
    # SANS; lo leído, plegado.
    "hrp-ivd-evidence-book",
    "hrp-bmed-evidence-report",
    "hrp-microhost-evidence-report",
    "hrp-dust-evidence-report",
    "hrp-bone-fracture-evidence-report",
    "hrp-cardiovascular-evidence-report",
    "hrp-dynamic-loads-evidence-report",
    "hrp-pharm-evidence-report-2011",
    "hrp-nutrition-human-adaptation-2020",
    "hrp-carcinogenesis-evidence-report",
    # Decimonovena ronda (U4, 2026-10-31): los bancos de prueba releídos, los proveedores de la
    # ISS y la investigación 7562. A la vista, qué es cada página («ficha de misión», «página de
    # programa», «nota de adjudicación», «no un estudio») y, en las de Loma Linda y el foro de
    # tejidos, que son experimentos o muestras de animales y no personas; las frases leídas y lo
    # buscado y no encontrado, plegados.
    "nasa-envihab-mission", "nasa-antarctic-stations-nsf", "nasa-space-radiation-element",
    "nasa-tissue-sharing-forum", "nasa-jsc-space-radiation", "nasa-chapea-program",
    "nasa-argos-patent", "nasa-iss-facts-figures", "nasa-iss-health-care-faq",
    "nasa-iss-national-lab-casis-2022", "nasa-mossi-ii-teledyne-2022",
    "nasa-iss-sustaining-boeing-2010", "nasa-food-appeal-2021", "ntrs-20200001311",
    # Decimonovena ronda (U5, 2026-10-31): el mapa de conjuntos de datos humanos. A la vista, qué
    # es cada fuente y sobre quién («no un estudio ni sus datos» el tutorial de OSDR; cosmonautas,
    # reposo e inmersión «no son constantes vitales»; PlanHab «no es vuelo»; dos pósteres de CIPHER
    # «no un artículo con resultados»; el plan de datos del HRP «no mide a nadie»; AGBRESA «en
    # Tierra y no en vuelo»); las frases leídas y la bitácora, plegadas.
    "nasa-osdr-controlled-access-tutorial", "brzhozovskiy-2019-plasma-proteome",
    "rullman-2016-planhab-mirna", "ntrs-20240000955-cipher-vestibular",
    "ntrs-20230000776-cipher-space-physiology", "ntrs-20230013774-hrp-data-management-plan",
    "clement-2022-agbresa-ism",
    # Decimonovena ronda (U6, 2026-10-31): el sentido en vuelo de hematología y bioquímica; a la
    # vista, a quién se midió y cuánto duró; lo leído, plegado.
    "vorobiev-1995-altair-mir", "zittermann-2000-calcium-absorption-spaceflight",
    "crucian-2013-shuttle-immunity", "smith-1997-portable-analyzer-shuttle",
    "morey-holton-1988-vitamin-d-spacelab2", "heer-2002-nutrition-european-missions",
    "mehta-2014-shuttle-viruses", "zwart-2018-dietary-acid-load",
    # Decimonovena ronda (U7, 2026-10-31): el sentido en vuelo de la función y la cabina. A la
    # vista, sobre quién, dónde y cuándo se midió (la Mir, el transbordador, la ISS; antes y
    # después del vuelo, o en vuelo con un sustituto o con una sola persona) y lo que el resumen
    # no dice (el lado de la yugular, la estación, los resultados); las frases leídas y la
    # bitácora, plegadas.
    "tu-2022-pvt-prediction-iss", "dijk-2001-sleep-circadian-shuttle",
    "gundel-1997-sleep-circadian-mir", "monk-1998-sleep-circadian-shuttle",
    "fu-2019-orthostatic-tolerance-iss", "wood-2019-inflight-leg-cuff-iss",
    "lee-2015-orthostatic-intolerance-iss-shuttle", "arbeille-2015-vessel-imaging-iss",
    "pavela-2022-jugular-surveillance-iss", "david-2021-right-ijv-tilt-microgravity",
    "zamboni-2026-jugular-venous-pulse-iss", "strollo-1997-spacelab-adrenal-gonadal",
    # Decimonovena ronda (U14, 2026-10-31): a la vista, que Basner 2015 valida la batería en Tierra
    # y que no es un dato de vuelo; las frases leídas, plegadas.
    "basner-2015-cognition-battery",
    # Unidad 3 (2026-11-03): las cuatro páginas de MedlinePlus de las guías de medida. A la vista,
    # qué explica cada página y que es divulgación para el público, no un estudio; la bitácora de
    # lo leído, plegada.
    "medlineplus-blood-pressure-measurement", "medlineplus-temperature-measurement",
    "medlineplus-pulse-oximetry", "medlineplus-pulse",
    # Guía de glucosa capilar (2026-11-04): las dos páginas de la guía del glucómetro, con el mismo
    # corte que las de MedlinePlus de la unidad 3.
    "cdc-monitoring-blood-sugar", "medlineplus-blood-sugar-test",
    # Unidad 8 (2026-11-03): el polvo y el ciclo de día y noche de los perfiles de misión. A la
    # vista, qué clase de documento es (divulgación, libro blanco, artículo sobre un estudio que no
    # se ha leído); lo leído, plegado.
    "nasa-perseverance-mars-dust", "nasa-acr22-lunar-south-pole", "nasa-moon-facts",
    "nasa-mars-facts",
    # Lote ciclo (A4, 2026-11-14): la variación por fase del ciclo y la supresión menstrual. A la
    # vista, qué clase de estudio es y sobre quién (mujeres en Tierra, con qué sensor; la revisión
    # de Jain y Wotring «no mide nada en ninguna tripulante»); las frases leídas, plegadas.
    "jain-2016-amenorrhea-astronauts", "baker-2020-temperature-menstrual-review",
    "maijala-2019-oura-finger-temperature", "shilaih-2018-wrist-temperature-cycle",
    "goodale-2019-wearable-menses-physiology", "alzueta-2022-oura-menstrual-cycle",
    "giersch-2020-menstrual-thermoregulation-meta", "schmalenberger-2019-vagal-menstrual-meta",
    "dejager-2026-wearable-hrv-cycle-review", "yazar-2016-hrv-menstrual-phase",
    "tenan-2014-resting-hrv-cycle",
    # Lote ciclo (C1, 2026-11-15): la menopausia y la perimenopausia. A la vista, qué estudio es y
    # sobre quién (mujeres en Tierra; la revisión de Hughes-Fulford y el comentario de Rose «no
    # mide» a ninguna tripulante; Smith 2014, 9 astronautas de la ISS); las frases, plegadas.
    "kronenberg-1984-hot-flash-physiology", "low-2008-hot-flash-hemodynamics",
    "jones-2019-core-temperature-hot-flush", "freedman-2001-hot-flash-physiology",
    "sievert-2013-hot-flash-measures", "mann-2011-hot-flush-concordance",
    "thurston-2016-hrv-vasomotor", "hira-2026-hrv-vasomotor-review",
    "avis-2015-vasomotor-duration-swan", "oconnor-2009-perimenopause-ovulation",
    "alzueta-2024-midlife-cycle-oura", "greendale-2012-bmd-final-menstrual-period",
    "smith-2014-bone-sex-iss", "hughes-fulford-2024-women-in-space",
    "rose-2022-radiation-menopause",
    # Lote ciclo (C2, 2026-11-15): STRAW+10. A la vista, qué es (el resumen de un taller de
    # consenso, la referencia de los estadios) y por qué esa versión; lo leído, plegado.
    "harlow-2012-straw10-menopause",
}
SHOWN_WHOLE_REVIEWED: set[str] = set()


def test_a_change_in_what_is_shown_in_view_does_not_pass_unseen() -> None:
    refs = [ref for ref in registry.registry().values() if ref.notes is not None]
    cut = {ref.id for ref in refs if ref.scope_in_view not in (None, ref.notes)}
    whole = {ref.id for ref in refs if ref.scope_in_view == ref.notes}
    assert cut == CUT_REVIEWED
    assert whole == SHOWN_WHOLE_REVIEWED


def test_a_source_that_is_not_only_human_never_folds_away_what_it_does_not_measure() -> None:
    for ref in registry.registry().values():
        if ref.population in NON_HUMAN:
            assert ref.scope_in_view, f"{ref.id}: su salvedad quedaría entera detrás de un clic"
    mouse = registry.get("osd-288").scope_in_view
    assert mouse is not None and "Modelo murino" in mouse
    assert "NO mide signos vitales humanos" in mouse
    assert "leídos el" not in mouse
    # Una nota que empieza por la lectura se enseña entera, no se pliega.
    reading_first = dataclasses.replace(
        registry.get("hrp-muscle-evidence-report"), notes="Leída el 2026-10-16: lo que fuera."
    )
    assert reading_first.scope_in_view == reading_first.notes


def test_the_cabin_hypothesis_cards_fold_their_reading_log() -> None:
    # La línea que se vio en la undécima ronda: junto a la hipótesis de cabina, la nota de
    # lectura entera (organización releída en PubMed incluida) estaba a la vista.
    readings = [
        HabitatReading("m1", "cabin-ppco2", 5.0, T0 - dt.timedelta(hours=hours), "sensor")
        for hours in range(10, -1, -1)
    ]
    result = context.correlate(
        {"crew-01": "concern", "crew-02": "watch"}, excursions(readings), T0,
        dt.timedelta(days=2),
    )
    evidence = result["hypotheses"][0]["evidence"]
    with_caveat = {item["id"] for item in evidence if item["scope_caveat"] is not None}
    # Desde la decimocuarta ronda la ficha de OCHMO-TB-002 también lleva nota de lectura.
    assert with_caveat == {"law-2014", "scully-2019", "ochmo-tb-002"}
    for item in evidence:
        assert item["scope_in_view"] == registry.get(item["id"]).scope_in_view
        if item["scope_caveat"] is None:
            continue
        # La bitácora (cada lectura lleva su fecha) se queda plegada, sea de la ficha que sea.
        assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b", item["scope_in_view"] or "")
        if item["id"] == "ochmo-tb-002":
            # Su nota empieza por la lectura: va plegada entera.
            assert item["scope_in_view"] is None
        else:
            assert "organización" in item["scope_caveat"]
            assert "organización" not in (item["scope_in_view"] or "")


def test_the_shared_cause_hypothesis_cites_the_registry() -> None:
    readings = [
        HabitatReading("m1", "cabin-ppco2", 5.0, T0 - dt.timedelta(hours=hours), "sensor")
        for hours in range(10, -1, -1)
    ]
    result = context.correlate(
        {"crew-01": "concern", "crew-02": "watch"}, excursions(readings), T0,
        dt.timedelta(days=2),
    )
    evidence = result["hypotheses"][0]["evidence"]
    assert [item["id"] for item in evidence] == ["law-2014", "scully-2019", "ochmo-tb-002"]
    # El requisito cruzado no se pierde al citar la norma por su ficha.
    assert evidence[-1]["relevance"] == "NASA-STD-3001 Vol 2 [V2 6004]"
    for item in _resolved(result):
        _check_resolved(item)


def test_inferred_and_shelter_sources_are_registry_cards() -> None:
    band = inferred.bone_density_band(60.0, exercise_logged=False)
    assert band["source"]["id"] == "nasa-human-body-in-space"
    shelter = radiation.time_to_action(T0, T0 + dt.timedelta(minutes=5))
    assert shelter is not None and shelter["source"]["id"] == "nasa-orion-radiation-protection"
    for item in (band["source"], shelter["source"]):
        _check_resolved(item)


def test_the_dossier_still_reaches_each_countermeasure_source() -> None:
    pieces = {item["id"]: item for item in dossier.pieces()}
    for measure in countermeasures.library().values():
        expected = [measure.protocol_ref.url] if measure.protocol_ref is not None else []
        assert pieces[f"contramedida:{measure.id}"]["fuentes"] == expected


def test_no_animal_source_is_presented_as_human_by_the_api(client: TestClient) -> None:
    seen: set[str] = set()
    for path in (
        *(f"/api/evidence/{domain}" for domain in Domain),
        "/api/countermeasures",
        "/api/dossier/references",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        for item in _resolved(response.json()):
            _check_resolved(item)
            seen.add(item["id"])
    # Todo lo que cita el producto ha pasado por aquí; solo falta lo que no sale por estas rutas.
    assert {"osd-288", "osd-343"} <= seen
    immune = client.get(f"/api/evidence/{Domain.IMMUNE}").json()["evidence"]
    mouse = next(item for item in immune if item["id"] == "osd-288")
    assert (mouse["population"], mouse["population_display"]) == ("animal", "animal")
    assert mouse["evidence_context"] == "iss" and mouse["evidence_type"] == "dataset"
    assert "NO mide signos vitales humanos" in mouse["scope_caveat"]


def test_the_api_serves_the_registry_with_its_pending_fields(client: TestClient) -> None:
    body = client.get("/api/dossier/references").json()
    assert body["count"] == len(registry.registry()) == len(body["references"])
    assert body["unverified_fields"] == sum(len(item["unverified"]) for item in body["references"])
    for item in body["references"]:
        _check_resolved(item)


def test_recommendations_carry_resolved_references(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "progressive-insomnia", "days": 40})
    payload = client.get("/api/status").json()
    found = list(_resolved(payload["recommendations"]))
    assert found, "un dominio en alerta trae recomendaciones con su evidencia"
    for item in _resolved(payload):
        _check_resolved(item)
