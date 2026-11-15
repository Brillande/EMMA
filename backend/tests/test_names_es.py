"""Cada indicador del catálogo tiene nombre en español, con su origen, y ninguno pasa por LOINC.

La decisión del usuario (2026-10-20): una tabla de EMMA para el catálogo entero, rotulada. Los
analitos de una analítica se nombran como los nombra Polaris; el resto, con un nombre de EMMA.
El `display` del catálogo, el nombre de LOINC, se queda en inglés en FHIR y en la API.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ingest import names_es
from app.ingest.codes import CATALOG, LAB_REPORT_ONLY, CodeSystem
from app.ingest.fhir import observation
from app.ingest.names_es import EMMA_NAMES, NameOrigin, spanish_name
from app.reports import labs
from tests.test_analysis import _deviation

NOW = dt.datetime(2026, 11, 14, 8, 0, tzinfo=dt.UTC)
BACKEND = Path(__file__).resolve().parents[1]


def test_every_indicator_has_a_spanish_name_with_its_origin() -> None:
    for key, code in CATALOG.items():
        name = spanish_name(key)
        assert name.text.strip() == name.text and name.text, key
        assert name.origin in NameOrigin, key
        assert code.display_es == name.text, key


def test_the_polaris_names_are_the_ones_polaris_gives() -> None:
    from_polaris = labs.names()
    named = {key for key in CATALOG if spanish_name(key).origin is NameOrigin.POLARIS}

    assert named == set(from_polaris)
    for key in named:
        assert spanish_name(key).text == from_polaris[key], key
    # Los analitos que solo llegan de una analítica se nombran todos como en Polaris.
    assert named >= LAB_REPORT_ONLY


def test_naming_an_indicator_does_not_load_polaris() -> None:
    """Una frase del análisis no puede depender de que la copia de Polaris importe."""
    script = (
        "import sys\n"
        "from app.ingest.codes import CATALOG\n"
        "names = [code.display_es for code in CATALOG.values()]\n"
        "assert 'biomarcadores' not in sys.modules, 'se cargó biomarcadores'\n"
        "print(len(names))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", script], cwd=BACKEND, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == str(len(CATALOG))


def test_emma_names_cover_exactly_what_polaris_does_not() -> None:
    """Sin hueco ni sobra: una clave de más en la tabla sería un nombre que nadie enseña."""
    assert set(EMMA_NAMES).isdisjoint(labs.names())
    assert set(EMMA_NAMES) | set(labs.names()) == set(CATALOG)
    for key in EMMA_NAMES:
        assert spanish_name(key).origin is NameOrigin.EMMA, key


def test_no_spanish_name_is_presented_as_loinc() -> None:
    for origin in NameOrigin:
        assert names_es.ORIGIN_DISPLAY[origin].endswith("no de LOINC"), origin
    assert "EMMA" in names_es.ORIGIN_DISPLAY[NameOrigin.EMMA]
    assert "Polaris" in names_es.ORIGIN_DISPLAY[NameOrigin.POLARIS]
    for key, code in CATALOG.items():
        # Un nombre igual al de la ficha no sería una traducción: sería el de LOINC rotulado
        # como de EMMA.
        assert spanish_name(key).text != code.display, key


def test_two_indicators_never_share_a_spanish_name() -> None:
    """Derecho e izquierdo, o dos analitos parecidos, no pueden leerse igual en pantalla."""
    texts = [spanish_name(key).text for key in CATALOG]
    assert len(texts) == len(set(texts))


def test_an_unknown_key_has_no_name() -> None:
    with pytest.raises(KeyError):
        spanish_name("no-such-indicator")


def test_fhir_keeps_the_loinc_name_in_english() -> None:
    resource = observation("heart-rate", 60.0, NOW, "crew-01", "t").to_fhir()
    assert resource["code"]["coding"][0]["display"] == "Heart rate"
    assert resource["code"]["text"] == "Heart rate"
    for key, code in CATALOG.items():
        if code.system is CodeSystem.LOINC:
            assert code.display != code.display_es, key


def test_the_engine_sentences_name_the_indicator_in_spanish() -> None:
    text = _deviation(4.5).describe()
    assert text.startswith("Frecuencia cardiaca: ")
    assert "Heart rate" not in text


def test_the_api_publishes_the_name_and_its_origin(client: TestClient) -> None:
    indicators = client.get("/api/indicators").json()["indicators"]
    by_key = {item["key"]: item for item in indicators}
    assert set(by_key) == set(CATALOG)

    heart = by_key["heart-rate"]
    assert heart["display"] == "Heart rate"
    assert heart["display_es"] == "Frecuencia cardiaca"
    assert heart["display_es_origin"] == "emma"
    assert heart["display_es_origin_display"] == "nombre de EMMA, no de LOINC"

    leukocytes = by_key["leukocytes"]
    assert leukocytes["display_es"] == labs.names()["leukocytes"]
    assert leukocytes["display_es_origin"] == "polaris"
    for item in indicators:
        assert item["display_es"] == spanish_name(item["key"]).text
        assert item["display_es_origin"] == str(spanish_name(item["key"]).origin)
