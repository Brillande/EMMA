"""Los bancos de prueba y las dos validaciones: `GET /api/testbeds`.

Lo que vigilan estas pruebas es que el mapa no diga más de lo que se leyó ni más de lo que EMMA
tiene: cada frase con su ficha y su página oficial; cada banco con lo que deja fuera y con el
entorno de evidencia del enumerado de las observaciones (sin ampliarlo); la validación de EMMA
con el entorno de su ficha, sin copiar cifras que viven en `compliance/external-validation.md`; y
la validación operacional en «ninguna» mientras ninguna tripulación haya usado EMMA en un banco
operacional. Desde la decimoquinta ronda, también que cada columna de participantes, datos y
proveedores lleve la frase de la fuente o diga dónde se buscó, nunca las dos ni ninguna. Desde la
decimosexta, la duración como una columna más y la matriz banco × peligro RIDGE: los cinco
peligros por banco, deducidos por EMMA salvo donde la ficha de NASA nombra el que estudia, sin un
banco que los reproduzca todos ni una celda que contradiga el entorno del banco. Desde la
decimonovena (U4), cuatro columnas más (parámetros, equipos, investigadores, experimentos) con la
misma regla, el centro de protones de Loma Linda como banco, y lo que la relectura de las páginas
de NASA rellenó de lo que antes decía «no encontrado». **Ninguna prueba sale a la red**: las
lecturas se hicieron el 2026-10-21, el 2026-10-22, el 2026-10-23 y el 2026-10-31.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.evidence import registry, testbeds
from app.evidence.testbeds import AnalogMapError
from app.ingest.codes import Ridge
from app.ingest.fhir import EvidenceContext
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
BANKS = [
    "hera", "envihab", "antarctica", "nsrl", "loma-linda", "chapea", "mmea", "neemo", "argos",
    "parabolic", "kraken", "nbl", "altitude", "iss",
]
# El entorno que llevaría un dato de cada banco. NSRL no tiene: son muestras y equipos, no
# personas, y el enumerado no se amplía para él; Loma Linda (protones sobre experimentos, U4)
# tampoco. Tampoco ARGOS (una persona en Tierra con parte
# del peso descargado) ni los vuelos parabólicos (segundos de ingravidez en un avión), ni los tres
# de la decimosexta ronda: el Kraken (una plataforma que gira), el NBL (una piscina) y las cámaras
# de altitud (presión de una salida extravehicular).
CONTEXTS = {
    "hera": "analog_isolation",
    "envihab": "analog_bedrest",
    "antarctica": "analog_isolation",
    "nsrl": None,
    "loma-linda": None,
    "chapea": "analog_isolation",
    "mmea": "analog_isolation",
    "neemo": "analog_isolation",
    "argos": None,
    "parabolic": None,
    "kraken": None,
    "nbl": None,
    "altitude": None,
    "iss": "iss",
}
# Las dos páginas de la decimoquinta ronda que no muestran fecha de publicación.
UNDATED_R15 = {"nasa-jsc-space-suits-argos", "nasa-parabolic-flight"}
# Las de la decimosexta ronda que tampoco la muestran (solo «Page Last Updated», o nada).
UNDATED_E12 = {
    "nasa-analog-missions", "nasa-hera-mission", "nasa-antarctic-stations-mission",
    "nasa-nsrl-mission", "bnl-nsrl-about", "nasa-chapea-habitat", "nasa-jsc-nbl",
    "nasa-altitude-chambers",
}
# Las de la decimonovena ronda (U4) que tampoco muestran fecha de publicación.
UNDATED_U4 = {
    "nasa-envihab-mission", "nasa-antarctic-stations-nsf", "nasa-space-radiation-element",
    "nasa-tissue-sharing-forum", "nasa-chapea-program", "nasa-argos-patent",
    "nasa-iss-facts-figures",
}
# Y las que sí la muestran, con la fecha que escriben.
DATED_U4 = {
    "nasa-jsc-space-radiation": "2023-03-16",
    "nasa-iss-health-care-faq": "2024-11-21",
    "nasa-iss-national-lab-casis-2022": "2022-09-14",
    "nasa-mossi-ii-teledyne-2022": "2022-09-07",
    "nasa-iss-sustaining-boeing-2010": "2010-09-14",
    "nasa-food-appeal-2021": "2021-04-28",
    "ntrs-20200001311": "2020-01-27",
}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


@pytest.fixture
def raw() -> dict[str, Any]:
    """Una copia del fichero, para estropearla sin tocar la que está en caché."""
    return copy.deepcopy(json.loads(testbeds.TESTBEDS_PATH.read_text("utf-8")))


def _bank(raw: dict[str, Any], ident: str) -> dict[str, Any]:
    return next(bank for bank in raw["banks"] if bank["id"] == ident)


def _validation(raw: dict[str, Any], ident: str) -> dict[str, Any]:
    return next(item for item in raw["validations"] if item["id"] == ident)


# --------------------------------------------------------------------------- #
# Lo leído
# --------------------------------------------------------------------------- #


def test_the_file_as_shipped_is_valid_and_has_the_banks(raw: dict[str, Any]) -> None:
    assert testbeds.validate(raw) is raw
    assert [bank["id"] for bank in testbeds.payload()["banks"]] == BANKS


def test_every_quote_comes_from_an_official_page_with_its_registry_card() -> None:
    for bank in testbeds.payload()["banks"]:
        cited = [*bank["reproduces"]]
        cited += [item["cited"] for item in bank["leaves_out"] if item["cited"] is not None]
        assert bank["reproduces"], bank["id"]
        for item in cited:
            ref = registry.get(item["ref"])
            assert (item["source"], item["url"]) == (ref.source, ref.url)
            assert item["url"].split("/")[2] in testbeds.OFFICIAL_HOSTS
            assert item["quote"].strip() and item["where"].strip()
            # Lo que la ficha no tiene verificado se sirve como tal, no se calla.
            assert item["unverified_display"] == [
                registry.OPTIONAL_FIELDS[name] for name in ref.unverified
            ]


def test_each_card_was_read_on_the_day_it_says() -> None:
    raw = testbeds.read()
    read: list[tuple[str, str]] = []
    for bank in raw["banks"]:
        for item in [*bank["reproduces"], *bank["leaves_out"]]:
            if "ref" in item:
                read.append((item["ref"], bank["read_on"]))
        for column in testbeds.COLUMNS:
            read += [(item["ref"], bank[column]["read_on"]) for item in bank[column]["quotes"]]
        read += [
            (cell["ref"], bank["ridge"]["read_on"])
            for cell in bank["ridge"]["cells"] if cell["basis"] == "source"
        ]
    # Los conjuntos de la validación de EMMA llevan su propia bitácora.
    assert {ref_id for ref_id, _ in read} | {"mmash", "osd-569"} == testbeds.cited_refs()
    for ref_id, read_on in read:
        assert read_on in (registry.get(ref_id).notes or ""), (ref_id, read_on)
    # Lo que se sirve dice cuándo se leyó cada frase, no una fecha para todo el mapa.
    for bank in testbeds.payload()["banks"]:
        assert all(item["read_on"] == bank["read_on"] for item in bank["reproduces"])
        for column in bank["columns"]:
            assert all(item["read_on"] == column["read_on"] for item in column["quotes"])
        for cell in bank["ridge"]:
            assert cell["cited"] is None or cell["cited"]["read_on"] == bank["ridge_read_on"]


def test_a_date_or_organization_not_shown_by_the_page_stays_unverified() -> None:
    # La página del programa MMEA y la del NSRL no muestran fecha: no se pone una de memoria.
    assert registry.get("nasa-mmea-program").unverified == ("date",)
    assert registry.get("bnl-nsrl").unverified == ("date",)
    assert registry.get("nasa-mmea-announcement").date == "2026-07-01"
    assert registry.get("nasa-hrp-step1-analogs").date == "2021-02-25"
    # Tampoco la de ARGOS (la de trajes espaciales de Johnson) ni la de los vuelos parabólicos.
    for ref_id in UNDATED_R15 | UNDATED_E12 | UNDATED_U4:
        assert registry.get(ref_id).unverified == ("date",), ref_id
    for ref_id, date in DATED_U4.items():
        assert registry.get(ref_id).date == date and not registry.get(ref_id).unverified, ref_id
    assert registry.get("nasa-kraken-2023").date == "2023-05-17"
    assert registry.get("nasa-altitude-chamber-complex").date == "2015-05-07"
    assert registry.get("nasa-neemo-studies").date == "2015-05-06"
    assert registry.get("nasa-neemo-19").date == "2014-09-13"
    assert registry.get("nasa-hera-45-day-2024").date == "2024-07-02"


def test_every_bank_says_what_it_leaves_out_and_how_that_is_known() -> None:
    for bank in testbeds.payload()["banks"]:
        assert bank["leaves_out"], bank["id"]
        for item in bank["leaves_out"]:
            assert item["basis_text"] == testbeds.LEAVES_OUT_BASIS[item["basis"]]
            if item["basis"] == "deduced":
                assert item["why"] and item["cited"] is None
            else:
                assert item["cited"] is not None


def test_bed_rest_does_not_reproduce_microgravity_and_the_page_says_so() -> None:
    envihab = next(bank for bank in testbeds.payload()["banks"] if bank["id"] == "envihab")
    sourced = [item for item in envihab["leaves_out"] if item["basis"] == "source"]
    assert any("Microgravity cannot be reproduced" in item["cited"]["quote"] for item in sourced)


# --------------------------------------------------------------------------- #
# El entorno de evidencia: el enumerado de las observaciones, sin ampliar
# --------------------------------------------------------------------------- #


def test_each_bank_maps_to_an_existing_evidence_context() -> None:
    served = {bank["id"]: bank["evidence_context"] for bank in testbeds.payload()["banks"]}
    assert served == CONTEXTS
    # El enumerado sigue siendo el de las observaciones: este mapa no le añade valores.
    assert {str(item) for item in EvidenceContext} == {
        "iss", "spaceflight", "analog_bedrest", "analog_isolation", "ground", "simulated",
    }


def test_a_bank_without_context_says_why_none_covers_it() -> None:
    for bank in testbeds.payload()["banks"]:
        if bank["evidence_context"] is not None:
            assert bank["outside_enum_text"] is None
            continue
        assert bank["id"] in {
            "nsrl", "loma-linda", "argos", "parabolic", "kraken", "nbl", "altitude",
        }
        assert "enumerado" in bank["context_basis"] and "no se amplía" in bank["context_basis"]
        # La palabra con que el registro dice que ningún valor lo cubre, no una de la interfaz.
        assert bank["outside_enum_text"] == registry.OUTSIDE_ENUM


def test_a_parabolic_flight_is_not_spaceflight_and_its_page_says_how_short_it_is() -> None:
    banks = {bank["id"]: bank for bank in testbeds.payload()["banks"]}
    parabolic = banks["parabolic"]
    assert "spaceflight" in parabolic["context_basis"]
    sourced = [item["cited"] for item in parabolic["leaves_out"] if item["basis"] == "source"]
    assert any("lasts for around 20 seconds" in item["quote"] for item in sourced)
    # NEEMO sí es aislamiento y confinamiento, y su página lo dice con esas palabras.
    assert banks["neemo"]["evidence_context"] == "analog_isolation"
    assert any("isolation, confinement" in item["quote"] for item in banks["neemo"]["reproduces"])


# --------------------------------------------------------------------------- #
# Las dos validaciones
# --------------------------------------------------------------------------- #


def test_emma_has_no_operational_validation_and_says_it() -> None:
    operational = next(
        item for item in testbeds.payload()["validations"] if item["id"] == "operational"
    )
    assert operational["emma"] == []
    assert operational["emma_status"] == {
        "status": "none", "text": "Validación operacional de EMMA: ninguna.",
    }
    assert set(operational["banks"]) == {"hera", "chapea", "mmea", "neemo"}
    # Cada banco operacional se nombra en lo que EMMA no tiene.
    names = {bank["id"]: bank["name"] for bank in testbeds.payload()["banks"]}
    for ident in operational["banks"]:
        assert names[ident] in operational["not_covered"], ident


def test_the_scientific_validation_is_partial_and_each_part_says_what_it_does_not_show() -> None:
    scientific = next(
        item for item in testbeds.payload()["validations"] if item["id"] == "scientific"
    )
    assert scientific["emma_status"]["status"] == "partial"
    contexts = {item["id"]: item["context"] for item in scientific["emma"]}
    assert contexts == {"mmash": "ground", "inspiration4": "spaceflight"}
    for item in scientific["emma"]:
        assert str(registry.get(item["ref"]).evidence_context) == item["context"]
        assert item["does_not_show"].strip()
    mmash = next(item for item in scientific["emma"] if item["id"] == "mmash")
    # La mina de CLAUDE.md: MMASH no valida fisiología espacial.
    assert "No valida fisiología espacial" in mmash["does_not_show"]


def test_the_figures_are_referred_to_not_copied() -> None:
    document = (ROOT / "compliance" / "external-validation.md").read_text("utf-8")
    headings = {line.lstrip("#").strip() for line in document.splitlines() if line.startswith("#")}
    for validation in testbeds.payload()["validations"]:
        for item in validation["emma"]:
            assert item["figures_in"].startswith(testbeds.FIGURES_HOME)
            # Cada apartado al que se remite existe en el documento.
            named = [part.split("»")[0] for part in item["figures_in"].split("«")[1:]]
            assert named and all(
                any(heading.startswith(name) for heading in headings) for name in named
            ), named
            assert not testbeds.COPIED_FIGURE.search(item["what"] + item["does_not_show"])


def test_the_ladder_has_its_four_rungs_and_mars_has_no_complete_testbed() -> None:
    rungs = {rung["id"]: rung for rung in testbeds.payload()["ladder"]["rungs"]}
    assert list(rungs) == ["ground", "iss", "moon", "mars"]
    assert rungs["mars"]["banks"] == [] and rungs["moon"]["banks"] == []
    assert rungs["mars"]["limitation"] == "no existe banco de prueba completo"
    assert rungs["iss"]["banks"] == ["iss"]


# --------------------------------------------------------------------------- #
# Las columnas que pedía la conversación: participantes, datos y proveedores
# --------------------------------------------------------------------------- #


def test_every_bank_has_the_three_columns_with_a_quote_or_where_it_was_searched() -> None:
    for bank in testbeds.payload()["banks"]:
        assert [column["id"] for column in bank["columns"]] == list(testbeds.COLUMNS), bank["id"]
        for column in bank["columns"]:
            assert column["label"] == testbeds.COLUMNS[column["id"]]
            # O se leyó la frase, o se dice dónde se buscó: exactamente una de las dos.
            assert bool(column["quotes"]) != bool(column["not_found"]), (bank["id"], column["id"])
            for item in column["quotes"]:
                assert item["url"].split("/")[2] in testbeds.OFFICIAL_HOSTS
                assert item["quote"].strip() and item["where"].strip()


def test_what_the_pages_give_is_filled_and_what_they_do_not_is_said() -> None:
    columns = {
        (bank["id"], column["id"]): column
        for bank in testbeds.payload()["banks"]
        for column in bank["columns"]
    }
    filled = {key for key, column in columns.items() if column["quotes"]}
    # Las cuatro columnas de antes, con lo que la relectura del 2026-10-31 (U4) rellenó.
    first_four = ("duration", "participants", "data", "providers")
    assert {key for key in filled if key[1] in first_four} == {
        ("hera", "duration"), ("envihab", "duration"), ("antarctica", "duration"),
        ("chapea", "duration"), ("mmea", "duration"), ("neemo", "duration"),
        ("parabolic", "duration"), ("kraken", "duration"), ("altitude", "duration"),
        ("iss", "duration"),
        ("hera", "participants"), ("envihab", "participants"), ("envihab", "providers"),
        ("antarctica", "participants"), ("antarctica", "providers"),
        ("nsrl", "participants"), ("nsrl", "providers"), ("chapea", "participants"),
        ("chapea", "providers"), ("mmea", "participants"), ("neemo", "participants"),
        ("neemo", "providers"), ("argos", "providers"), ("parabolic", "providers"),
        ("kraken", "participants"), ("kraken", "providers"), ("nbl", "providers"),
        ("altitude", "participants"), ("altitude", "providers"), ("iss", "participants"),
        ("iss", "providers"),
        ("nsrl", "data"),
    }
    # Y las cuatro nuevas (U4): frase donde la página la da.
    assert {key for key in filled if key[1] in testbeds.COLUMNS and key[1] not in first_four} == {
        ("envihab", "parameters"), ("envihab", "equipment"), ("envihab", "experiments"),
        ("antarctica", "parameters"), ("antarctica", "investigators"),
        ("antarctica", "experiments"),
        ("nsrl", "parameters"), ("nsrl", "equipment"), ("nsrl", "experiments"),
        ("chapea", "parameters"), ("chapea", "investigators"), ("chapea", "experiments"),
        ("mmea", "equipment"), ("mmea", "experiments"),
        ("neemo", "equipment"), ("neemo", "experiments"),
        ("argos", "equipment"),
        ("parabolic", "experiments"),
        ("kraken", "parameters"), ("kraken", "equipment"), ("kraken", "experiments"),
        ("nbl", "equipment"), ("nbl", "experiments"),
        ("altitude", "equipment"), ("altitude", "experiments"),
        ("iss", "parameters"), ("iss", "equipment"), ("iss", "investigators"),
        ("iss", "experiments"),
    }
    # Dónde quedan los datos: solo tres páginas dicen algo, y ninguna de personas. El NSRL, el
    # catálogo de las muestras de animales irradiados (LSDA); Loma Linda y MMEA, a quién van los
    # resultados, no dónde se publican. El resto lo dice en `not_found`.
    with_data = {
        bank for (bank, ident), column in columns.items() if ident == "data" and column["quotes"]
    }
    assert with_data == {"nsrl"}
    assert "Life Sciences Data Archive" in columns[("nsrl", "data")]["quotes"][0]["quote"]
    assert "no datos de personas" in columns[("nsrl", "data")]["quotes"][0]["where"]
    providers = " ".join(item["quote"] for item in columns[("parabolic", "providers")]["quotes"])
    assert "Zero Gravity Corporation" in providers and "Novespace" in providers
    assert "FIU Aquarius Reef Base" in columns[("neemo", "providers")]["quotes"][0]["quote"]
    # La mina de CLAUDE.md, dicha donde se buscaban los datos de la ISS.
    assert "no hay API pública" in columns[("iss", "data")]["not_found"]


def test_the_u4_rereading_filled_what_the_pages_give_and_named_where_it_looked() -> None:
    columns = {
        (bank["id"], column["id"]): column
        for bank in testbeds.payload()["banks"]
        for column in bank["columns"]
    }
    # Los rótulos de las cuatro columnas nuevas, con el dibujo que elige la interfaz por su clave.
    labels = {column["id"]: column["label"] for column in testbeds.payload()["banks"][0]["columns"]}
    assert labels == testbeds.COLUMNS
    assert {"parameters", "equipment", "investigators", "experiments"} <= set(labels)
    # La Antártida: la página «Antarctic Stations» del enlace «NSF» da lo que la ficha no daba.
    nsf = "nasa-antarctic-stations-nsf"
    assert {item["ref"] for item in columns[("antarctica", "participants")]["quotes"]} == {nsf}
    assert "24 subjects" in columns[("antarctica", "participants")]["quotes"][0]["quote"]
    where = columns[("antarctica", "participants")]["quotes"][0]["where"]
    assert "no cuántas personas invernan" in where
    providers = " ".join(item["quote"] for item in columns[("antarctica", "providers")]["quotes"])
    assert "Antarctic Program (USAP) maintains McMurdo" in providers
    assert "National Science Foundation" in providers
    investigators = columns[("antarctica", "investigators")]["quotes"]
    assert [item["ref"] for item in investigators] == [nsf, nsf]
    assert "Brian Crucian" in investigators[0]["quote"]
    assert "Satish Mehta" in investigators[1]["quote"]
    assert all("sin darle cargo" in item["where"] for item in investigators)
    # La ISS: la duración de una estancia, la tripulación, quién la opera y tres contratistas.
    assert "about six months" in columns[("iss", "duration")]["quotes"][0]["quote"]
    assert "crew of seven people" in columns[("iss", "participants")]["quotes"][0]["quote"]
    iss_providers = {item["ref"]: item["quote"] for item in columns[("iss", "providers")]["quotes"]}
    assert set(iss_providers) == {
        "nasa-iss-facts-figures", "nasa-iss-sustaining-boeing-2010", "nasa-mossi-ii-teledyne-2022",
        "nasa-iss-national-lab-casis-2022",
    }
    assert "five space agencies" in iss_providers["nasa-iss-facts-figures"]
    assert "sustaining engineering" in iss_providers["nasa-iss-sustaining-boeing-2010"]
    assert "Teledyne Brown Engineering" in iss_providers["nasa-mossi-ii-teledyne-2022"]
    assert "(CASIS)" in iss_providers["nasa-iss-national-lab-casis-2022"]
    # De COLSA no hay página viva de NASA: se dice, no se inventa.
    assert any("COLSA" in line and "404" in line for line in testbeds.read()["not_found"])
    # La investigación 7562 (comida) entra por el artículo de 2021 y el póster de 2020; el Explorer
    # no se pudo releer y la 975 sigue sin resolverse.
    experiments = {item["ref"] for item in columns[("iss", "experiments")]["quotes"]}
    assert {"nasa-food-appeal-2021", "ntrs-20200001311"} <= experiments
    assert "Grace Douglas" in columns[("iss", "investigators")]["quotes"][0]["quote"]
    assert any("7562" in line and "975" in line for line in testbeds.read()["not_found"])
    # ARGOS: la ficha de la patente, a la que remite el catálogo, da quién lo desarrolló.
    assert "NASA Johnson Space Center" in columns[("argos", "providers")]["quotes"][0]["quote"]
    assert columns[("argos", "providers")]["quotes"][0]["url"].startswith("https://technology.nasa.gov/")
    # Lo que sigue sin frase dice dónde se buscó, con la fecha de la relectura.
    # La del NBL se releyó ese día y sigue sin participantes: la fecha de la columna lo dice.
    still_empty = (
        ("hera", "providers"), ("hera", "data"), ("mmea", "providers"), ("nbl", "participants"),
    )
    for key in still_empty:
        assert columns[key]["quotes"] == [] and columns[key]["read_on"] == "2026-10-31", key
        assert columns[key]["not_found"], key


def test_loma_linda_is_a_bank_by_the_space_radiation_element_page_only() -> None:
    bank = next(bank for bank in testbeds.payload()["banks"] if bank["id"] == "loma-linda")
    assert bank["rung"] == "ground" and bank["validation"] == "scientific"
    assert bank["evidence_context"] is None and bank["outside_enum_text"] == registry.OUTSIDE_ENUM
    assert {item["ref"] for item in bank["reproduces"]} == {"nasa-space-radiation-element"}
    assert "Loma Linda University Proton Treatment Center" in bank["reproduces"][0]["quote"]
    # Lo que la página no dice no se rellena: ni qué se irradia, ni cuánto dura, ni quién lo
    # opera, ni dónde quedan los datos (dice a qué sirven los resultados).
    empty = {column["id"] for column in bank["columns"] if not column["quotes"]}
    assert empty == {column["id"] for column in bank["columns"]}
    providers = next(column for column in bank["columns"] if column["id"] == "providers")
    assert "protons.com" in providers["not_found"]
    # La radiación «en parte» (protones sobre experimentos, no una tripulación) y el resto fuera.
    ridge = {cell["hazard"]: cell["status"] for cell in bank["ridge"]}
    assert ridge == {
        "radiation": "partial", "isolation": "leaves_out", "distance": "leaves_out",
        "gravity": "leaves_out", "environment": "leaves_out",
    }
    assert "EMMA no usa datos de Loma Linda" in bank["emma_use"]
    # La colección de biospecímenes y los modelos de JSC son filas del NSRL, no otro banco.
    nsrl = next(bank for bank in testbeds.payload()["banks"] if bank["id"] == "nsrl")
    data = next(column for column in nsrl["columns"] if column["id"] == "data")
    assert {item["ref"] for item in data["quotes"]} == {
        "nasa-tissue-sharing-forum", "nasa-jsc-space-radiation",
    }
    assert any("acute radiation syndrome" in item["quote"] for item in data["quotes"])


def test_the_nsrl_columns_come_from_its_about_page_not_the_front_page() -> None:
    columns = {
        column["id"]: column
        for bank in testbeds.payload()["banks"] if bank["id"] == "nsrl"
        for column in bank["columns"]
    }
    # Los «más de 50 institutos» que la conversación atribuía a Brookhaven: instituciones, no
    # personas.
    participants = columns["participants"]["quotes"][0]
    assert participants["ref"] == "bnl-nsrl-about"
    assert "more than 50 institutes and universities" in participants["quote"]
    assert "no personas" in participants["where"]
    assert columns["providers"]["quotes"][0]["ref"] == "bnl-nsrl-about"
    assert "funded by NASA and managed by Brookhaven Lab for DOE" in (
        columns["providers"]["quotes"][0]["quote"]
    )


def test_the_chapea_habitat_page_names_icon_and_not_big() -> None:
    chapea = next(bank for bank in testbeds.payload()["banks"] if bank["id"] == "chapea")
    providers = next(column for column in chapea["columns"] if column["id"] == "providers")
    assert [item["ref"] for item in providers["quotes"]] == ["nasa-chapea-habitat"]
    assert "ICON" in providers["quotes"][0]["quote"]
    assert "BIG" not in providers["quotes"][0]["quote"]
    assert any("no a BIG" in line for line in testbeds.read()["not_found"])
    # Y el documento de personas ya no le atribuye el hábitat a BIG.
    people = (ROOT / "docs" / "contexto" / "personas-y-organizaciones.md").read_text("utf-8")
    assert "| ICON y BIG |" not in people


# --------------------------------------------------------------------------- #
# La matriz banco × peligro RIDGE
# --------------------------------------------------------------------------- #


def test_every_bank_has_the_five_ridge_hazards_in_order_with_their_words() -> None:
    payload = testbeds.payload()
    assert [item["id"] for item in payload["ridge"]["hazards"]] == [str(item) for item in Ridge]
    assert [item["display"] for item in payload["ridge"]["hazards"]] == [
        item.display for item in Ridge
    ]
    assert [item["id"] for item in payload["ridge"]["statuses"]] == list(testbeds.RIDGE_STATUS)
    for bank in payload["banks"]:
        assert [cell["hazard"] for cell in bank["ridge"]] == [str(item) for item in Ridge]
        for cell in bank["ridge"]:
            assert cell["hazard_display"] == Ridge(cell["hazard"]).display
            assert cell["status_text"] == testbeds.RIDGE_STATUS[cell["status"]]
            assert cell["basis_text"] == testbeds.RIDGE_BASIS[cell["basis"]]
            if cell["basis"] == "deduced":
                assert cell["why"] and cell["cited"] is None
            else:
                assert cell["cited"] is not None and cell["status"] in testbeds.SOURCE_STATUSES


def test_the_matrix_is_a_deduction_except_where_the_nasa_card_names_the_hazard() -> None:
    sourced = {
        (bank["id"], cell["hazard"]): cell["cited"]["quote"]
        for bank in testbeds.payload()["banks"]
        for cell in bank["ridge"] if cell["basis"] == "source"
    }
    assert sourced == {
        ("hera", "isolation"): "Isolation and Confinement",
        ("antarctica", "isolation"): "Isolation and Confinement",
        # La página «Antarctic Stations» del enlace «NSF» (U4) cuenta el entorno hostil entre lo
        # que estudia; la ficha de misión, no.
        ("antarctica", "environment"): "Hostile environment, isolation",
        ("nsrl", "radiation"): "Space radiation",
        ("neemo", "isolation"): (
            "Most experiments conducted at the Aquarius facility focus on isolation, confinement, "
            "communications, telemedicine, and remote collaboration."
        ),
    }
    assert "deducción de EMMA" in testbeds.payload()["ridge"]["note"]


def test_every_bank_leaves_one_out_and_distance_is_where_they_fall_short() -> None:
    banks = testbeds.payload()["banks"]
    # «Cada entorno elimina variables que otro sí contiene»: todos dejan fuera al menos uno.
    for bank in banks:
        assert any(cell["status"] == "leaves_out" for cell in bank["ridge"]), bank["id"]
    # Ningún banco reproduce entera la distancia de la Tierra: el hueco de EMMA (la «D» de RIDGE).
    distance = {
        bank["id"]: next(cell["status"] for cell in bank["ridge"] if cell["hazard"] == "distance")
        for bank in banks
    }
    assert "reproduces" not in distance.values()
    # La Antártida pasa de «no se sabe» a «en parte» el 2026-10-31: la página del enlace «NSF»
    # dice que solo Palmer tiene acceso rutinario en invierno (sin reabastecimiento ni evacuación
    # en McMurdo y el Polo Sur), y sigue sin decir si hay retardo.
    assert {ident for ident, status in distance.items() if status == "partial"} == {
        "hera", "chapea", "neemo", "antarctica",
    }
    # Lo que ninguna página dice y EMMA no puede deducir queda en «no se sabe», no en «deja fuera»;
    # de las cámaras de altitud, lo que se sabe es de las simulaciones largas de otras décadas.
    assert {ident for ident, status in distance.items() if status == "unknown"} == {
        "mmea", "altitude",
    }
    # Ningún banco reproduce entera la radiación: el NSRL y Loma Linda irradian muestras, la ISS
    # está en LEO.
    radiation = {
        bank["id"]: next(cell["status"] for cell in bank["ridge"] if cell["hazard"] == "radiation")
        for bank in banks
    }
    assert {ident for ident, status in radiation.items() if status != "leaves_out"} == {
        "nsrl", "loma-linda", "iss",
    }
    assert set(radiation.values()) == {"partial", "leaves_out"}


def test_the_matrix_agrees_with_each_bank_evidence_context() -> None:
    for bank in testbeds.payload()["banks"]:
        hazard = testbeds.CONTEXT_HAZARD.get(bank["evidence_context"] or "")
        if hazard is None:
            continue
        cell = next(cell for cell in bank["ridge"] if cell["hazard"] == str(hazard))
        assert cell["status"] in testbeds.CONTEXT_STATUSES, bank["id"]


def test_kraken_nbl_and_the_altitude_chambers_come_from_nasa_pages() -> None:
    banks = {bank["id"]: bank for bank in testbeds.payload()["banks"]}
    assert "spins on multiple axes" in banks["kraken"]["reproduces"][0]["quote"]
    assert "simulate full or partial gravity" in banks["nbl"]["reproduces"][0]["quote"]
    assert "decompression sickness" in banks["altitude"]["reproduces"][0]["quote"]
    # Lo que el NBL deja fuera lo dice «Step 2»: la piscina no da el efecto a largo plazo.
    sourced = [item["cited"] for item in banks["nbl"]["leaves_out"] if item["basis"] == "source"]
    assert any("long-term effects of microgravity" in item["quote"] for item in sourced)
    for ident in ("kraken", "nbl", "altitude"):
        assert banks[ident]["validation"] == "scientific"
        assert banks[ident]["evidence_context"] is None


# --------------------------------------------------------------------------- #
# La defensa: lo que no se sostiene no se sirve
# --------------------------------------------------------------------------- #


def _drop_ref(raw: dict[str, Any]) -> None:
    del _bank(raw, "hera")["reproduces"][0]["ref"]


def _unregistered(raw: dict[str, Any]) -> None:
    _bank(raw, "hera")["reproduces"][0]["ref"] = "nasa-hera-inventada"


def _unofficial(raw: dict[str, Any]) -> None:
    # MMASH es una ficha real, pero no la página de un banco.
    _bank(raw, "hera")["reproduces"][0]["ref"] = "mmash"


def _new_context(raw: dict[str, Any]) -> None:
    _bank(raw, "nsrl")["evidence_context"] = "analog_radiation"


def _silent_null(raw: dict[str, Any]) -> None:
    bank = _bank(raw, "hera")
    bank["evidence_context"] = None


def _nothing_left_out(raw: dict[str, Any]) -> None:
    _bank(raw, "chapea")["leaves_out"] = []


def _deduction_without_why(raw: dict[str, Any]) -> None:
    del _bank(raw, "hera")["leaves_out"][0]["why"]


def _unknown_basis(raw: dict[str, Any]) -> None:
    _bank(raw, "hera")["leaves_out"][0]["basis"] = "obvio"


def _source_without_quote(raw: dict[str, Any]) -> None:
    del _bank(raw, "envihab")["leaves_out"][0]["quote"]


def _claim(raw: dict[str, Any]) -> None:
    _bank(raw, "hera")["emma_use"] = "EMMA validado en HERA."


def _unknown_rung(raw: dict[str, Any]) -> None:
    _bank(raw, "iss")["rung"] = "leo"


def _unknown_validation(raw: dict[str, Any]) -> None:
    _bank(raw, "hera")["validation"] = "clinical"


def _duplicate(raw: dict[str, Any]) -> None:
    raw["banks"].append(copy.deepcopy(_bank(raw, "hera")))


def _wrong_context(raw: dict[str, Any]) -> None:
    _validation(raw, "scientific")["emma"][0]["context"] = "spaceflight"


def _operational_from_a_dataset(raw: dict[str, Any]) -> None:
    item = copy.deepcopy(_validation(raw, "scientific")["emma"][0])
    _validation(raw, "operational")["emma"].append(item)


def _operational_from_a_scientific_bank(raw: dict[str, Any]) -> None:
    item = copy.deepcopy(_validation(raw, "scientific")["emma"][0])
    item["bank"] = "envihab"
    _validation(raw, "operational")["emma"].append(item)


def _copied_percent(raw: dict[str, Any]) -> None:
    _validation(raw, "scientific")["emma"][0]["what"] += " Falsa alarma del 0,18 %."


def _copied_count(raw: dict[str, Any]) -> None:
    _validation(raw, "scientific")["emma"][0]["what"] += " Sin alertas en 21 de 22."


def _figures_elsewhere(raw: dict[str, Any]) -> None:
    _validation(raw, "scientific")["emma"][0]["figures_in"] = "README.md"


def _no_caveat(raw: dict[str, Any]) -> None:
    _validation(raw, "scientific")["emma"][0]["does_not_show"] = " "


def _one_validation(raw: dict[str, Any]) -> None:
    raw["validations"] = [_validation(raw, "scientific")]


def _undated(raw: dict[str, Any]) -> None:
    _bank(raw, "hera")["read_on"] = None


def _not_iso(raw: dict[str, Any]) -> None:
    _bank(raw, "neemo")["read_on"] = "22 de octubre"


def _column_undated(raw: dict[str, Any]) -> None:
    _bank(raw, "argos")["participants"]["read_on"] = None


def _column_empty(raw: dict[str, Any]) -> None:
    _bank(raw, "argos")["data"]["not_found"] = None


def _column_blank(raw: dict[str, Any]) -> None:
    _bank(raw, "argos")["data"]["not_found"] = "  "


def _column_both(raw: dict[str, Any]) -> None:
    _bank(raw, "hera")["participants"]["not_found"] = "Buscado y no encontrado."


def _column_unofficial(raw: dict[str, Any]) -> None:
    _bank(raw, "neemo")["providers"]["quotes"][0]["ref"] = "mmash"


def _column_without_quote(raw: dict[str, Any]) -> None:
    del _bank(raw, "parabolic")["providers"]["quotes"][1]["quote"]


def _column_missing(raw: dict[str, Any]) -> None:
    del _bank(raw, "neemo")["providers"]


def _column_not_an_object(raw: dict[str, Any]) -> None:
    _bank(raw, "argos")["providers"] = None


def _column_quotes_not_a_list(raw: dict[str, Any]) -> None:
    _bank(raw, "argos")["providers"]["quotes"] = None


def _column_extra(raw: dict[str, Any]) -> None:
    _bank(raw, "argos")["data"]["count"] = 4


def _column_claim(raw: dict[str, Any]) -> None:
    _bank(raw, "iss")["data"]["not_found"] = "EMMA validado con datos de la ISS."


def _claim_verb(raw: dict[str, Any]) -> None:
    _bank(raw, "hera")["emma_use"] = "EMMA valida la respuesta de la tripulación en HERA."


def _claim_in_not_covered(raw: dict[str, Any]) -> None:
    _validation(raw, "operational")["not_covered"] = "Nada: EMMA está verificado en la ISS."


def _claim_in_context(raw: dict[str, Any]) -> None:
    _bank(raw, "iss")["context_basis"] = "Microgravedad real; EMMA certificado para ella."


def _copied_decimal(raw: dict[str, Any]) -> None:
    _validation(raw, "scientific")["emma"][0]["what"] += " Sensibilidad 0,93."


def _copied_fraction(raw: dict[str, Any]) -> None:
    _validation(raw, "scientific")["emma"][0]["what"] += " Sin alertas en 21/22."


def _missing_field(raw: dict[str, Any]) -> None:
    del _bank(raw, "hera")["full_name"]


def _unknown_field(raw: dict[str, Any]) -> None:
    _bank(raw, "hera")["budget"] = 4


def _null_without_reason(raw: dict[str, Any]) -> None:
    # La palabra «enumerado» sola no es el motivo: tiene que decir que ningún valor lo cubre.
    _bank(raw, "nsrl")["context_basis"] = "El enumerado lo cubre de sobra."


def _no_rule(raw: dict[str, Any]) -> None:
    del raw["rule"]["where"]


def _emma_not_a_list(raw: dict[str, Any]) -> None:
    del _validation(raw, "operational")["emma"]


def _cell(raw: dict[str, Any], ident: str, hazard: str) -> dict[str, Any]:
    return next(cell for cell in _bank(raw, ident)["ridge"]["cells"] if cell["hazard"] == hazard)


def _ridge_missing(raw: dict[str, Any]) -> None:
    del _bank(raw, "hera")["ridge"]


def _ridge_not_an_object(raw: dict[str, Any]) -> None:
    _bank(raw, "hera")["ridge"] = []


def _ridge_object_extra(raw: dict[str, Any]) -> None:
    _bank(raw, "hera")["ridge"]["source"] = "nasa-hera-mission"


def _ridge_undated(raw: dict[str, Any]) -> None:
    _bank(raw, "hera")["ridge"]["read_on"] = "hoy"


def _ridge_cells_not_a_list(raw: dict[str, Any]) -> None:
    _bank(raw, "hera")["ridge"]["cells"] = {}


def _ridge_hazard_missing(raw: dict[str, Any]) -> None:
    _bank(raw, "argos")["ridge"]["cells"].pop()


def _ridge_hazard_repeated(raw: dict[str, Any]) -> None:
    cells = _bank(raw, "argos")["ridge"]["cells"]
    cells[1] = copy.deepcopy(cells[0])


def _ridge_hazard_out_of_order(raw: dict[str, Any]) -> None:
    cells = _bank(raw, "argos")["ridge"]["cells"]
    cells[0], cells[1] = cells[1], cells[0]


def _ridge_hazard_invented(raw: dict[str, Any]) -> None:
    _bank(raw, "argos")["ridge"]["cells"][4]["hazard"] = "noise"


def _ridge_status_unknown(raw: dict[str, Any]) -> None:
    _cell(raw, "argos", "gravity")["status"] = "simula"


def _ridge_status_not_a_string(raw: dict[str, Any]) -> None:
    _cell(raw, "argos", "gravity")["status"] = ["partial"]


def _ridge_basis_unknown(raw: dict[str, Any]) -> None:
    _cell(raw, "argos", "gravity")["basis"] = "obvio"


def _ridge_deduction_without_why(raw: dict[str, Any]) -> None:
    del _cell(raw, "argos", "gravity")["why"]


def _ridge_deduction_with_ref(raw: dict[str, Any]) -> None:
    _cell(raw, "argos", "gravity")["ref"] = "nasa-jsc-space-suits-argos"


def _ridge_source_without_ref(raw: dict[str, Any]) -> None:
    del _cell(raw, "hera", "isolation")["ref"]


def _ridge_source_unofficial(raw: dict[str, Any]) -> None:
    _cell(raw, "hera", "isolation")["ref"] = "mmash"


def _ridge_source_leaves_out(raw: dict[str, Any]) -> None:
    _cell(raw, "nsrl", "radiation")["status"] = "leaves_out"


def _ridge_empty_why(raw: dict[str, Any]) -> None:
    _cell(raw, "nsrl", "radiation")["why"] = " "


def _ridge_source_from_another_bank(raw: dict[str, Any]) -> None:
    _cell(raw, "hera", "isolation")["ref"] = "nasa-antarctic-stations-mission"


def _ridge_source_from_a_catalogue(raw: dict[str, Any]) -> None:
    _cell(raw, "nsrl", "radiation")["ref"] = "nasa-hrp-step1-analogs"


def _ridge_claim(raw: dict[str, Any]) -> None:
    _cell(raw, "argos", "gravity")["why"] = "EMMA validado con la gravedad reducida de ARGOS."


def _ridge_extra_field(raw: dict[str, Any]) -> None:
    _cell(raw, "argos", "gravity")["weight"] = 1


def _ridge_complete(raw: dict[str, Any]) -> None:
    for cell in _bank(raw, "iss")["ridge"]["cells"]:
        cell["status"] = "reproduces"


def _ridge_nothing_left_out(raw: dict[str, Any]) -> None:
    # Cuatro reproducidos y uno sin saber: tampoco deja fuera nada que se sepa.
    for cell in _bank(raw, "iss")["ridge"]["cells"]:
        cell["status"] = "reproduces"
    _cell(raw, "iss", "distance")["status"] = "unknown"


def _ridge_spaceflight_without_gravity(raw: dict[str, Any]) -> None:
    _bank(raw, "iss")["evidence_context"] = "spaceflight"
    _cell(raw, "iss", "gravity")["status"] = "leaves_out"


def _ridge_isolation_analog_without_isolation(raw: dict[str, Any]) -> None:
    _cell(raw, "chapea", "isolation")["status"] = "leaves_out"


def _ridge_bedrest_without_gravity(raw: dict[str, Any]) -> None:
    _cell(raw, "envihab", "gravity")["status"] = "unknown"


def _ridge_iss_without_gravity(raw: dict[str, Any]) -> None:
    _cell(raw, "iss", "gravity")["status"] = "leaves_out"


def _duration_missing(raw: dict[str, Any]) -> None:
    del _bank(raw, "kraken")["duration"]


def _duration_both(raw: dict[str, Any]) -> None:
    _bank(raw, "kraken")["duration"]["not_found"] = "No se dice."


@pytest.mark.parametrize(
    ("spoil", "reason"),
    [
        (_drop_ref, "falta `ref`"),
        (_unregistered, "no está en el registro"),
        (_unofficial, "no es la página oficial"),
        (_new_context, "no se amplía"),
        (_silent_null, "por qué ningún valor"),
        (_nothing_left_out, "deja fuera"),
        (_deduction_without_why, "sin su motivo"),
        (_unknown_basis, "fuente o deducción"),
        (_source_without_quote, "falta `quote`"),
        (_claim, "reclama de más"),
        (_unknown_rung, "peldaño"),
        (_unknown_validation, "validación"),
        (_duplicate, "repetido"),
        (_wrong_context, "no es el de su ficha"),
        (_operational_from_a_dataset, "banco operacional"),
        (_operational_from_a_scientific_bank, "banco operacional"),
        (_copied_percent, "copia una cifra"),
        (_copied_count, "copia una cifra"),
        (_figures_elsewhere, "se remiten"),
        (_no_caveat, "falta `does_not_show`"),
        (_one_validation, "las dos validaciones"),
        (_undated, "sin fecha"),
        (_not_iso, "sin fecha"),
        (_column_undated, "sin fecha"),
        (_column_empty, "dónde se buscó"),
        (_column_blank, "dónde se buscó"),
        (_column_both, "o se leyó o no estaba"),
        (_column_unofficial, "no es la página oficial"),
        (_column_without_quote, "falta `quote`"),
        (_column_missing, "faltan campos"),
        (_column_not_an_object, "es un objeto"),
        (_column_quotes_not_a_list, "aunque vacía"),
        (_column_extra, "campos desconocidos"),
        (_column_claim, "reclama de más"),
        (_claim_verb, "reclama de más"),
        (_claim_in_not_covered, "reclama de más"),
        (_claim_in_context, "reclama de más"),
        (_copied_decimal, "copia una cifra"),
        (_copied_fraction, "copia una cifra"),
        (_missing_field, "faltan campos"),
        (_unknown_field, "campos desconocidos"),
        (_null_without_reason, "por qué ningún valor"),
        (_no_rule, "de dónde sale"),
        (_emma_not_a_list, "aunque vacía"),
        (_ridge_missing, "faltan campos"),
        (_ridge_not_an_object, "es un objeto"),
        (_ridge_object_extra, "campos desconocidos"),
        (_ridge_undated, "sin fecha"),
        (_ridge_cells_not_a_list, "lista de los cinco"),
        (_ridge_hazard_missing, "los cinco de RIDGE"),
        (_ridge_hazard_repeated, "los cinco de RIDGE"),
        (_ridge_hazard_out_of_order, "los cinco de RIDGE"),
        (_ridge_hazard_invented, "los cinco de RIDGE"),
        (_ridge_status_unknown, "estado"),
        (_ridge_status_not_a_string, "estado"),
        (_ridge_basis_unknown, "fuente o deducción"),
        (_ridge_deduction_without_why, "sin su motivo"),
        (_ridge_deduction_with_ref, "o fuente o deducción"),
        (_ridge_source_without_ref, "falta `ref`"),
        (_ridge_source_unofficial, "no es la página oficial"),
        (_ridge_source_leaves_out, "no el que deja fuera"),
        (_ridge_empty_why, "`why` vacío"),
        (_ridge_source_from_another_bank, "no es la página de este banco"),
        (_ridge_source_from_a_catalogue, "no es la página de este banco"),
        (_ridge_claim, "reclama de más"),
        (_ridge_extra_field, "campos desconocidos"),
        (_ridge_complete, "no existe banco de prueba completo"),
        (_ridge_nothing_left_out, "no existe banco de prueba completo"),
        (_ridge_spaceflight_without_gravity, "se contradicen"),
        (_ridge_isolation_analog_without_isolation, "se contradicen"),
        (_ridge_bedrest_without_gravity, "se contradicen"),
        (_ridge_iss_without_gravity, "se contradicen"),
        (_duration_missing, "faltan campos"),
        (_duration_both, "o se leyó o no estaba"),
    ],
)
def test_the_loader_rejects_what_cannot_be_sustained(
    raw: dict[str, Any], spoil: Callable[[dict[str, Any]], None], reason: str
) -> None:
    spoil(raw)
    with pytest.raises((AnalogMapError, registry.RegistryError), match=reason):
        testbeds.validate(raw)


def test_a_source_cell_without_why_may_say_null(raw: dict[str, Any]) -> None:
    # «Lo que no se sabe va como null»: una celda de fuente sin motivo puede llevarlo así.
    _cell(raw, "hera", "isolation")["why"] = None
    testbeds.validate(raw)


def test_naming_validation_is_not_claiming_it() -> None:
    # «validación» nombra la cosa; la negación de lo que no muestra tampoco reclama nada.
    assert testbeds._claims("Serviría para la validación operacional.") == []
    assert testbeds._claims("EMMA valida en HERA; validado; certificado") == [
        "valida", "validado", "certificado",
    ]


def test_the_served_map_does_not_share_the_cached_dicts() -> None:
    served = testbeds.payload()
    served["rule"]["text"] = "otra cosa"
    served["principle"]["text"] = "otra cosa"
    assert testbeds.payload()["rule"]["text"] != "otra cosa"
    assert testbeds.payload()["principle"]["text"] != "otra cosa"


# --------------------------------------------------------------------------- #
# La ruta
# --------------------------------------------------------------------------- #


def test_the_route_serves_the_map_offline_and_reads_no_crew_state(client: TestClient) -> None:
    response = client.get("/api/testbeds")
    assert response.status_code == 200
    assert response.json() == json.loads(json.dumps(testbeds.payload()))
    # Inventario: no hay tripulante, nivel ni alerta en la respuesta.
    text = response.text
    for word in ('"subject"', '"level"', '"alerts"', '"risk_score"'):
        assert word not in text


# --------------------------------------------------------------------------- #
# El anexo refleja el JSON (decimonovena ronda, U4)
# --------------------------------------------------------------------------- #


def _annex_row(doc: str, header: str, name: str) -> str:
    section = doc[doc.index(header):]
    table = section[:section.index("\n\n")]
    (row,) = [line for line in table.splitlines() if line.startswith(f"| {name} |")]
    return row


@pytest.mark.parametrize(
    ("header", "columns"),
    [
        ("| Banco | Participantes |", ("participants", "data", "providers")),
        ("| Banco | Duración |", ("duration",)),
        ("| Banco | Parámetros medidos |", ("parameters", "equipment")),
        ("| Banco | Investigadores |", ("investigators", "experiments")),
    ],
)
def test_the_annex_says_for_each_bank_what_the_json_says(
    header: str, columns: tuple[str, ...]
) -> None:
    doc = (ROOT / "docs" / "contexto" / "bancos-de-prueba.md").read_text("utf-8")
    for bank in testbeds.read()["banks"]:
        row = _annex_row(doc, header, bank["name"])
        for column in columns:
            found = bank[column]
            if found["not_found"]:
                assert found["not_found"].replace("|", "\\|") in row, (bank["id"], column)
            for item in found["quotes"]:
                assert item["quote"].replace("|", "\\|") in row, (bank["id"], column)
                assert f"`{item['ref']}`" in row, (bank["id"], column)
