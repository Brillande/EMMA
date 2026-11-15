"""El catálogo de indicadores en inglés (`ingest/codes.py`, `ingest/category_fit.py`).

El nombre de cada indicador en inglés ya es el `display` del catálogo (`ingest/names_es.py`).
Aquí se comprueba lo demás: que el `display` de cada código propio es inglés de verdad, que cada
razón de un código propio y cada ancla de una escala propia tienen su inglés al lado sin tocar el
castellano, que el dominio y el peligro RIDGE se nombran en el idioma pedido, y que el motivo de
una categoría que no casa sale en inglés con el mismo código de FHIR.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.core import i18n
from app.ingest import category_fit, codes
from app.ingest.codes import CATALOG, CodeSystem, Domain, Ridge
from tests.conftest import ENGLISH_HEADERS

SPANISH = re.compile(r"[áéíóúñ¿¡]", re.IGNORECASE)
OVERCLAIM = re.compile(r"certified|validated|diagnos|administer|must take", re.IGNORECASE)
# Palabras castellanas sin acento que delatarían un `display` a medio traducir.
SPANISH_WORDS = re.compile(
    r"\b(de|del|la|el|los|las|por|con|sin|para|propio|escala|prueba|medida|tasa|dosis)\b",
    re.IGNORECASE,
)
DOMAINS_EN = {
    Domain.CARDIOVASCULAR: "cardiovascular",
    Domain.BEHAVIORAL: "behavioral",
    Domain.RADIATION: "radiation",
    Domain.BONE: "bone",
    Domain.IMMUNE: "immune",
    Domain.NEURO_OCULAR: "neuro-ocular",
    Domain.GENITOURINARY: "genitourinary",
    Domain.MUSCULOSKELETAL: "musculoskeletal",
    Domain.NUTRITION: "nutrition",
}
RIDGE_EN = {
    Ridge.RADIATION: "radiation",
    Ridge.ISOLATION: "isolation and confinement",
    Ridge.DISTANCE: "distance from Earth",
    Ridge.GRAVITY: "gravity fields",
    Ridge.ENVIRONMENT: "hostile and closed environment",
}


def test_the_display_of_every_own_code_is_english() -> None:
    own = [code for code in CATALOG.values() if code.system is CodeSystem.EMMA]
    assert len(own) > 50
    for code in own:
        assert not SPANISH.search(code.display), code.key
        assert not SPANISH_WORDS.search(code.display), code.key
        assert code.display[0].isupper(), code.key


def test_every_reason_of_an_own_code_has_its_english() -> None:
    assert codes.MISSION_SPECIFIC_EN.keys() == codes.MISSION_SPECIFIC.keys()
    for key, spanish in codes.MISSION_SPECIFIC.items():
        english = codes.MISSION_SPECIFIC_EN[key]
        assert i18n.loc(spanish) == spanish
        with i18n.use("en"):
            assert i18n.loc(spanish) == english
        assert english != spanish and not SPANISH.search(english), key
        assert not OVERCLAIM.search(english), key
    # Lo que la razón niega sigue negado: no es una prueba ni una observación clínica.
    assert "not a routine clinical test" in codes.MISSION_SPECIFIC_EN["pvt-mean-rt"]
    assert "it is not a clinical observation" in codes.MISSION_SPECIFIC_EN["food-acceptability"]


def test_the_anchors_of_the_own_scales_have_their_english() -> None:
    assert codes.OWN_SCALE_ANCHORS_EN.keys() == codes.OWN_SCALE_ANCHORS.keys()
    for key, spanish in codes.OWN_SCALE_ANCHORS.items():
        english = codes.OWN_SCALE_ANCHORS_EN[key]
        for name in ("low", "high", "why"):
            text = getattr(spanish, name)
            assert i18n.loc(text) == text
            with i18n.use("en"):
                assert i18n.loc(text) == getattr(english, name)
            assert not SPANISH.search(getattr(english, name)), (key, name)
        # No hay instrumento publicado detrás, y el inglés lo dice igual.
        assert english.why.startswith("There is no published instrument behind it")
        assert english.why.endswith("no source says what each point means.")


def test_domains_and_hazards_are_named_in_the_language_asked() -> None:
    spanish = {domain: domain.display for domain in Domain}
    assert spanish[Domain.BONE] == "óseo" and spanish[Domain.BEHAVIORAL] == "conductual"
    assert Ridge.GRAVITY.display == "campos gravitatorios"
    with i18n.use("en"):
        assert {domain: domain.display for domain in Domain} == DOMAINS_EN
        assert {hazard: hazard.display for hazard in Ridge} == RIDGE_EN
        assert codes.domain_name("bone") == "bone"
        assert codes.domain_name("no-es-un-dominio") == "no-es-un-dominio"
        # Lo que se firma se escribe en castellano, lo pida quien lo pida.
        with i18n.record_language():
            assert Domain.BONE.display == "óseo"
            assert Ridge.DISTANCE.display == "distancia de la Tierra"
        assert i18n.loc(codes.CODE_SYSTEM_DISPLAY[CodeSystem.EMMA]) == "EMMA's own code"
        assert i18n.loc(codes.CODE_SYSTEM_DISPLAY[CodeSystem.LOINC]) == "LOINC"
    # El valor del enum es la clave de la API y no cambia.
    assert str(Domain.BONE) == "bone" and str(Ridge.GRAVITY) == "gravity"
    assert {domain: domain.display for domain in Domain} == spanish
    assert codes.CODE_SYSTEM_DISPLAY[CodeSystem.EMMA] == "código propio de EMMA"


@pytest.mark.parametrize("key", sorted(category_fit._MISFITS))
def test_a_category_that_does_not_fit_says_why_in_english(key: str) -> None:
    spanish = {item["key"]: item for item in category_fit.misfits()}[key]
    with i18n.use("en"):
        english = {item["key"]: item for item in category_fit.misfits()}[key]
    assert spanish["reason"] == category_fit._MISFITS[key]
    assert english["category"] == spanish["category"]
    reason = english["reason"]
    assert reason is not None and reason == category_fit._MISFITS_EN[key]
    # El motivo habla de la categoría que el recurso lleva de verdad, con su código de FHIR.
    assert f"«{english['category']}»" in reason
    assert reason.startswith("It comes out as «") and "none of the nine categories" in reason
    assert not SPANISH.search(reason.replace("«", "").replace("»", ""))
    assert not OVERCLAIM.search(reason)


def test_every_misfit_has_its_english() -> None:
    assert category_fit._MISFITS_EN.keys() == category_fit._MISFITS.keys()


def test_the_catalogue_route_answers_in_the_language_asked(client: TestClient) -> None:
    spanish = client.get("/api/indicators").json()
    english = client.get("/api/indicators", headers=ENGLISH_HEADERS).json()
    assert [item["reason"] for item in spanish["category_fit"]] == list(
        category_fit._MISFITS.values()
    )
    assert [item["reason"] for item in english["category_fit"]] == list(
        category_fit._MISFITS_EN.values()
    )
    assert "Sale «" not in str(english["category_fit"])
    # Lo que identifica al indicador y a su código es igual en los dos idiomas (invariantes 1 y 2).
    fixed = ("key", "display", "unit", "domain", "system", "is_standard_code", "category",
             "category_display", "descriptive_only", "reference_low", "reference_high",
             "reference_basis", "critical_low", "critical_high", "decimals")
    assert [[item[name] for name in fixed] for item in english["indicators"]] == [
        [item[name] for name in fixed] for item in spanish["indicators"]
    ]
    named = {item["key"]: item for item in english["indicators"]}
    assert named["hrv-rmssd"]["display_es"] == "Heart rate variability (RMSSD)"
    assert named["hrv-rmssd"]["display_es_origin"] == "catalog"
