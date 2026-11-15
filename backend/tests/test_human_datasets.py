"""El mapa de conjuntos de datos humanos y CIPHER: `GET /api/human-datasets`.

Lo que vigilan estas pruebas es que el mapa no diga más de lo que se leyó: cada frase con su ficha
y la página de su fuente; la población de cada conjunto, la de su ficha (OSD-288 no sale humano);
los ficheros abiertos de OSD-343, de ratón, aunque el estudio hable de 59 astronautas; cada día de
toma escrito en una frase de su fase y en su tramo de la escalera de hitos; MMASH sin vuelo; el
acceso con su origen; el uso en EMMA en un fichero que existe y sin reclamar de más; y los catorce
estudios de CIPHER, sin un solo día L-/R+ inventado. **Ninguna prueba sale a la red**: la lectura
se hizo el 2026-10-22.

La decimosexta ronda (E11, lecturas del 2026-10-23) añade los controles de cada conjunto (los de
OSD-288, ratones, en Tierra y a 1 g en vuelo), el reposo en cama (AGBRESA y OSD-51) sin días de
vuelo y con su calendario de análogo, los catálogos de §8 sin población, y las diez áreas del Twins
Study, enteras.

La decimoséptima ronda (U10, lecturas del 2026-10-26) añade los otros seis reposos en cama humanos
de OSDR, leídos en su API: OSD-195, OSD-198, OSD-370, OSD-942 y OSD-946, cada uno con su
calendario de análogo; y OSD-353, que junta cosmonautas, un reposo y una inmersión seca, con su
entorno fuera del enumerado y sin calendario de análogo.

La decimonovena ronda (U5, lecturas del 2026-10-31) añade el papel de cada conjunto en la
estrategia de datos (INPUT, KNOWLEDGE, CONTEXT) y para qué sirve al modelo (entrenar, validar o
solo contextualizar), deducción de EMMA rotulada así: todo el mapa es KNOWLEDGE y solo MMASH sirve
para validar; INPUT, CONTEXT y «entrenar» se rechazan con su motivo. Lee además el acceso de cada
conjunto de OSDR en su API de ficheros (la bandera «restricted»), los días que el artículo del
Twins Study escribe en resultados concretos, con el guion largo de PMC, el archivo de las medidas
estándar de AGBRESA (LSDA) y los calendarios de dos estudios de CIPHER, que no son el de la suite.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.evidence import human_datasets, registry
from app.evidence.human_datasets import DatasetMapError
from app.ingest.fhir import EvidenceContext
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
DATASETS = [
    "osd-569", "inspiration4-soma", "twins-study", "osd-343", "osd-288", "mmash", "agbresa",
    "osd-51", "osd-195", "osd-198", "osd-353", "osd-370", "osd-942", "osd-946",
]
# Los reposos en cama humanos de OSDR (la búsqueda «bed rest» del 2026-10-23 da siete), todos
# leídos: OSD-51 el 2026-10-23 y los otros seis el 2026-10-26.
OSDR_BED_RESTS = ["osd-51", "osd-195", "osd-198", "osd-353", "osd-370", "osd-942", "osd-946"]
CATALOGS = ["iss-research-explorer", "data-nasa-gov"]


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
    return copy.deepcopy(json.loads(human_datasets.DATASETS_PATH.read_text("utf-8")))


def _dataset(raw: dict[str, Any], ident: str) -> dict[str, Any]:
    return next(item for item in raw["datasets"] if item["id"] == ident)


def _served(ident: str) -> dict[str, Any]:
    return next(item for item in human_datasets.payload()["datasets"] if item["id"] == ident)


# --------------------------------------------------------------------------- #
# Lo leído
# --------------------------------------------------------------------------- #


def test_the_file_as_shipped_is_valid_and_has_the_datasets(raw: dict[str, Any]) -> None:
    assert human_datasets.validate(raw) is raw
    assert [item["id"] for item in human_datasets.payload()["datasets"]] == DATASETS
    assert [item["id"] for item in human_datasets.payload()["catalogs"]] == CATALOGS


def _all_cited(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        if {"quote", "ref", "source", "url"} <= node.keys():
            yield node
        for value in node.values():
            yield from _all_cited(value)
    elif isinstance(node, list):
        for value in node:
            yield from _all_cited(value)


def test_every_quote_comes_from_its_source_with_its_registry_card() -> None:
    payload = human_datasets.payload()
    # El sitio de un catálogo (data.nasa.gov) vale solo en las frases de los catálogos.
    hosts = [
        *((item, human_datasets.SOURCE_HOSTS)
          for item in _all_cited({**payload, "catalogs": []})),
        *((item, human_datasets.CATALOG_HOSTS) for item in _all_cited(payload["catalogs"])),
    ]
    assert len(hosts) > 30
    assert "data.nasa.gov" not in human_datasets.SOURCE_HOSTS
    for item, allowed in hosts:
        ref = registry.get(item["ref"])
        assert (item["source"], item["url"]) == (ref.source, ref.url)
        assert item["url"].split("/")[2] in allowed
        assert item["quote"].strip() and item["where"].strip()
        assert item["unverified_display"] == [
            registry.OPTIONAL_FIELDS[name] for name in ref.unverified
        ]


def test_each_card_was_read_on_the_day_it_says() -> None:
    """Cada frase, el día de su lectura (el suyo o el del fichero), anotado en su ficha."""
    raw = human_datasets.read()
    for quote in human_datasets.all_quotes(raw):
        read_on = quote.get("read_on") or raw["read_on"]
        assert read_on in (registry.get(quote["ref"]).notes or ""), (quote["ref"], read_on)
    served = list(_all_cited(human_datasets.payload()))
    assert {item["read_on"] for item in served} == {
        "2026-10-22", "2026-10-23", "2026-10-26", "2026-10-31",
    }
    # Y la ficha de cada conjunto y catálogo anota alguna de las lecturas de sus frases.
    rows = [(item, human_datasets._quotes_of(item)) for item in raw["datasets"]]
    rows += [(item, [*item["what"], *item["access"]["cited"]]) for item in raw["catalogs"]]
    for item, quotes in rows:
        dates = {
            quote.get("read_on") or raw["read_on"] for quote in quotes
            if quote["ref"] == item["ref"]
        } or {raw["read_on"]}
        notes = registry.get(item["ref"]).notes or ""
        assert any(date in notes for date in dates), item["id"]


def test_the_cipher_page_shows_no_date_and_it_stays_unverified() -> None:
    assert registry.get("nasa-cipher").unverified == ("date",)
    assert registry.get("nasa-cipher-experiments-2023").date == "2023-01-23"
    assert registry.get("garrett-bakelman-2019").doi == "10.1126/science.aau8650"


def test_no_served_text_carries_markdown() -> None:
    """La interfaz pinta el texto tal cual: un acento grave de Markdown saldría a la vista."""
    assert "`" not in json.dumps(human_datasets.payload(), ensure_ascii=False)


def test_the_files_the_map_names_exist() -> None:
    for name in human_datasets.named_files():
        assert (ROOT / name).is_file(), name


def test_each_use_in_emma_names_a_file_that_cites_its_card() -> None:
    for where, cites in human_datasets.emma_citations():
        text = (ROOT / where).read_text("utf-8")
        ref = registry.get(cites)
        assert f'"{cites}"' in text or (ref.url is not None and ref.url in text), (where, cites)


def test_osd_569_access_is_what_osdr_says_and_emma_keeps_its_file() -> None:
    """Hasta la decimonovena ronda el acceso se deducía de que EMMA tenía el fichero; desde el
    2026-10-31 lo dice la fuente: la bandera «restricted» de cada fichero en la API de OSDR, que
    solo cubre lo depositado, y el artículo de SOMA, que deja lo sensible en acceso controlado."""
    access = _served("osd-569")["access"]
    assert (access["level"], access["basis"]) == ("mixed", "source")
    quotes = [quote["quote"] for quote in access["cited"]]
    assert any(quote["ref"] == "overbey-2024-soma" for quote in access["cited"])
    assert '"restricted": false' in quotes
    assert "All crew members have consented for data and sample sharing." in quotes
    assert any(quote["ref"] == "nasa-osdr-controlled-access-tutorial" for quote in access["cited"])
    assert access["path"] == (
        "backend/app/data/osdr/OSD-569_LSDS-7_Complete_Blood_Count_CBC_TRANSFORMED.csv"
    )
    assert "lecturas en bruto de secuenciación no están" in access["why"]
    # Lo mismo en OSD-288 y OSD-343, que estaban no encontrado y deducido: ahora lo dice la API.
    for ident, count in (("osd-288", "178"), ("osd-343", "81")):
        access = _served(ident)["access"]
        assert (access["level"], access["basis"]) == ("open", "source"), ident
        assert any(quote["quote"] == '"restricted": false' for quote in access["cited"]), ident
        assert count in access["cited"][0]["where"], ident
    # El nivel «solo el fichero que EMMA tiene» sigue en el enumerado, por si vuelve a hacer falta.
    assert "del resto" in human_datasets.ACCESS_LEVELS["file_open"]


def test_the_team_texts_are_literal() -> None:
    raw = human_datasets.read()
    contexto = ROOT / "docs" / "contexto"
    kb = (contexto / "knowledge-base-v1.md").read_text("utf-8")
    talk = (contexto / "conversacion-ideacion-v1.md").read_text("utf-8")
    assert raw["rule"]["text"] in kb and raw["task"]["text"] in kb
    assert raw["milestones"]["text"] in talk
    # La regla de la aptitud («entrenar, validar o simplemente contextualizar») es de la
    # conversación, tal cual; la respuesta lleva además los tres rótulos y la base, una deducción.
    assert raw["fitness_rule"]["text"] in talk
    served = human_datasets.payload()
    assert served["fitness_rule"] == raw["fitness_rule"]
    assert served["datasets"][0]["role"]["basis_text"] == "deducción de EMMA sobre lo leído"
    # Los puntos de Biolab se leen pegados en la conversación: así están escritos.
    assert "".join(raw["controls_rule"]["points"]) in talk
    assert raw["analog_pattern"]["text"] in kb
    # Cada apartado que el cargador admite, con su encabezado y los que lo cierran: el siguiente
    # del mismo nivel o de uno mayor.
    sections = {"§8": ("\n# 8.", ("\n# ",)), "§3.1": ("\n## 3.1", ("\n# ", "\n## "))}
    assert set(sections) == human_datasets.KB_SECTIONS
    for item in [*raw["datasets"], *raw["catalogs"]]:
        if item["kb_row"] is not None:
            # Una fila entera de una tabla de la base de conocimiento, entre sus bordes, en su
            # apartado (§8 o §3.1, la de los análogos), sin pasar al siguiente.
            heading, closers = sections[item["kb_where"]]
            section = kb[kb.index(heading) + 1:]
            ends = [found for closer in closers if (found := section.find(closer)) >= 0]
            section = section[: min(ends)] if ends else section
            assert f"| {item['kb_row']} |" in section, item["id"]


# --------------------------------------------------------------------------- #
# Minas conocidas (CLAUDE.md)
# --------------------------------------------------------------------------- #


def test_osd_288_is_mice_and_says_so() -> None:
    item = _served("osd-288")
    assert (item["population"], item["evidence_context"]) == ("animal", "iss")
    assert item["population_display"] == registry.POPULATIONS["animal"]
    assert "Ratones" in item["caveat"] and "no mide signos vitales humanos" in item["caveat"]


def test_osd_343_open_files_are_mouse_not_59_astronauts() -> None:
    item = _served("osd-343")
    assert item["population"] == "human_and_animal"
    assert item["open_population"] == "animal"
    assert item["open_population_note"] and "ratón" in item["open_population_note"]
    assert item["evidence_context"] is None and item["outside_enum_text"] == registry.OUTSIDE_ENUM


def test_mmash_has_no_flight() -> None:
    item = _served("mmash")
    assert (item["population"], item["evidence_context"]) == ("human", "ground")
    assert {phase["status"] for phase in item["phases"].values()} == {"not_applicable"}
    assert "no es fisiología de vuelo" in item["caveat"]


def test_osd_288_controls_are_mice_on_the_ground_and_at_1g_in_flight() -> None:
    controls = _served("osd-288")["controls"]
    assert controls["status"] == "listed"
    assert [(item["kind"], item["population"]) for item in controls["items"]] == [
        ("ground", "animal"), ("inflight_1g", "animal"),
    ]
    quotes = [item["quote"] for item in controls["items"]]
    assert quotes == ["Ground Control", "1G by centrifugation"]
    assert controls["items"][1]["kind_text"] == human_datasets.CONTROL_KINDS["inflight_1g"]


def test_each_dataset_says_its_controls_or_why_not() -> None:
    kinds = {
        item["id"]: (item["controls"]["status"], [c["kind"] for c in item["controls"]["items"]])
        for item in human_datasets.payload()["datasets"]
    }
    assert kinds == {
        "osd-569": ("listed", ["own_baseline"]),
        "inspiration4-soma": ("listed", ["own_baseline"]),
        "twins-study": ("listed", ["twin"]),
        "osd-343": ("listed", ["ground"]),
        "osd-288": ("listed", ["ground", "inflight_1g"]),
        "mmash": ("not_applicable", []),
        "agbresa": ("listed", ["analog_control"]),
        "osd-51": ("listed", ["analog_control"]),
        # Decimoséptima ronda (U10): solo el reposo de 70 días de NASA tiene un grupo solo en
        # reposo; en los demás, todos hacen el reposo (o las tres campañas) y no se nombra ninguno.
        "osd-195": ("not_found", []),
        "osd-198": ("not_found", []),
        "osd-353": ("not_found", []),
        "osd-370": ("not_found", []),
        "osd-942": ("listed", ["analog_control"]),
        "osd-946": ("listed", ["analog_control"]),
    }
    # Inspiration4: su propio control, y la frase de que no hubo controles en Tierra. OSD-569 son
    # los mismos cuatro tripulantes: su control sale del mismo artículo, y se dice que su ficha
    # de OSDR no lo nombra.
    for ident in ("inspiration4-soma", "osd-569"):
        controls = _served(ident)["controls"]
        assert controls["items"][0]["ref"] == "jones-2024-inspiration4", ident
        assert "controls on Earth" in controls["absent"][0]["quote"], ident
    assert "no nombran ningún control" in _served("osd-569")["controls"]["searched"]
    assert _served("osd-343")["controls"]["items"][0]["population"] == "animal"


def test_the_bed_rest_is_not_a_flight_and_keeps_its_own_calendar() -> None:
    payload = human_datasets.payload()
    points = payload["analog_pattern"]["points"]
    for ident in ("agbresa", "osd-51"):
        item = _served(ident)
        assert item["evidence_context"] == "analog_bedrest" and item["population"] == "human"
        assert {phase["status"] for phase in item["phases"].values()} == {"not_applicable"}
        assert all(cell["labels"] == [] for cell in item["ladder"])
        stages = [stage for step in item["analog_schedule"] for stage in step["stages"]]
        assert {"PRE", "EXPOSURE", "COUNTERMEASURE", "RECOVERY"} <= set(stages) <= set(points)
    # El «R+» de AGBRESA es la recuperación tras el reposo: va en su calendario, no en la escalera.
    recovery = _served("agbresa")["analog_schedule"][-1]
    assert recovery["stages"] == ["RECOVERY"] and "R+0 through R+13" in recovery["quote"]
    # Las medidas estándar de AGBRESA están en el LSDA y se piden allí (Acta Astronautica 2022,
    # leído el 2026-10-31); el resto lo dan sus autores, y las dos frases van citadas.
    agbresa = _served("agbresa")["access"]
    assert (agbresa["level"], agbresa["basis"]) == ("request", "source")
    assert {quote["ref"] for quote in agbresa["cited"]} == {
        "clement-2022-agbresa-ism", "clement-2022-agbresa",
    }
    assert "LSDA" in agbresa["cited"][0]["quote"] and "Dos vías" in agbresa["why"]
    assert _served("osd-51")["access"]["basis"] == "source"
    for item in payload["datasets"]:
        if item["evidence_context"] != "analog_bedrest":
            assert item["analog_schedule"] is None, item["id"]


def test_the_seven_human_bed_rests_of_osdr_are_read_and_none_is_a_flight() -> None:
    """Lo que dejó escrito §5.36.11: leer los otros seis reposos en cama humanos de OSDR."""
    raw = human_datasets.read()
    assert [item["id"] for item in raw["datasets"] if item["id"] in OSDR_BED_RESTS] == (
        OSDR_BED_RESTS
    )
    assert not any("solo OSD-51 se leyó" in line for line in raw["not_found"])
    for ident in OSDR_BED_RESTS:
        item = _served(ident)
        assert item["population"] == item["open_population"] == "human", ident
        # Desde el 2026-10-31 el acceso lo dice la API de ficheros de OSDR («restricted: false»
        # en cada fichero), no una deducción de que tengan enlace.
        assert item["access"]["level"] == "open" and item["access"]["basis"] == "source", ident
        assert item["access"]["cited"][0]["quote"] == '"restricted": false', ident
        assert item["access"]["cited"][0]["read_on"] == "2026-10-31", ident
        assert "EMMA no los ha descargado" in item["access"]["why"], ident
        assert not item["emma_use"]["used"], ident
        assert "no constantes vitales" in item["caveat"] or "no son constantes" in item["caveat"]
        if ident == "osd-51":
            continue
        quotes = human_datasets._quotes_of(_dataset(raw, ident))
        dates = {quote["read_on"] for quote in quotes}
        assert "2026-10-26" in dates and dates <= {"2026-10-26", "2026-10-31"}, ident
    # Cinco son reposos en cama: sus tres fases de vuelo no proceden y llevan su calendario.
    for ident in ("osd-195", "osd-198", "osd-370", "osd-942", "osd-946"):
        item = _served(ident)
        assert item["evidence_context"] == "analog_bedrest", ident
        assert {phase["status"] for phase in item["phases"].values()} == {"not_applicable"}
        assert item["analog_schedule"], ident
    # El de 70 días de NASA recorre la pauta salvo la recuperación, con su grupo solo en reposo.
    for ident in ("osd-942", "osd-946"):
        stages = [stage for step in _served(ident)["analog_schedule"] for stage in step["stages"]]
        assert set(stages) == {"PRE", "EXPOSURE", "COUNTERMEASURE", "POST"}, ident
        assert "bed rest only" in _served(ident)["controls"]["items"][0]["quote"]
    # La «recovery» de OSD-198 es el descanso entre campañas, y el caveat lo dice.
    assert "entre campañas" in _served("osd-198")["caveat"]
    # OSD-370: diez hombres en el protocolo y veinte en la descripción; no se resuelve callando.
    subjects = [quote["quote"] for quote in _served("osd-370")["subjects"]]
    assert any("Ten young" in quote for quote in subjects)
    assert any("20 healthy" in quote for quote in subjects)
    assert "no se ha resuelto" in _served("osd-370")["caveat"]


def test_osd_353_mixes_flight_and_analogs_and_says_so() -> None:
    """Cosmonautas antes y después de la ISS, un reposo y una inmersión seca: ni vuelo ni análogo
    solo. Su entorno va fuera del enumerado, como OSD-343, y su reposo no lleva calendario."""
    ref = registry.get("osd-353")
    assert ref.evidence_context is None and ref.outside_enum == ("evidence_context",)
    assert ref.notes is not None and "se declara fuera del enumerado" in ref.notes
    item = _served("osd-353")
    assert item["analog_schedule"] is None
    assert item["phases"]["pre"]["status"] == item["phases"]["post"]["status"] == "stated"
    assert item["phases"]["inflight"]["status"] == "not_found"
    assert "13 cosmonauts" in item["phases"]["pre"]["cited"][0]["quote"]
    assert all(cell["labels"] == [] for cell in item["ladder"])
    assert "fuera del enumerado" in item["caveat"]


def test_the_twins_study_days_are_those_the_article_names_in_results() -> None:
    """Hasta la decimonovena ronda el Twins Study estaba «dice que hay tomas, sin día»; el
    2026-10-31 se leyeron los días que el artículo escribe en resultados concretos, con el guion
    largo con que PMC escribe «L–162», y cada uno cae en su tramo. El calendario entero sigue sin
    leerse, y la fase lo dice."""
    item = _served("twins-study")
    labels = {phase: item["phases"][phase]["labels"] for phase in item["phases"]}
    assert labels == {
        "pre": ["L-162"],
        "inflight": ["FD76", "FD259", "FD334", "FD340"],
        "post": ["R+0", "R+4", "R+12", "R+36", "R+104", "R+190"],
    }
    for phase in item["phases"].values():
        assert phase["status"] == "labels"
        assert "no se pudo descargar" in phase["why"]
    cells = {cell["segment"]: cell["labels"] for cell in item["ladder"]}
    assert cells["L-180 → L-30"] == ["L-162"]
    assert cells["Flight → R+0"] == ["FD76", "FD259", "FD334", "FD340"]
    assert cells["R+0 → R+7"] == ["R+0", "R+4"]
    assert cells["R+7 → R+30"] == ["R+12"]
    assert cells["R+30 → R+90"] == ["R+36"]
    assert cells["R+90 → R+180"] == ["R+104"]
    assert cells["R+180 → R+365"] == ["R+190"]
    assert "no su calendario entero" in item["caveat"]
    assert any("tabla S1" in line for line in human_datasets.payload()["not_found"])


def test_cipher_keeps_no_days_although_two_of_its_studies_publish_theirs() -> None:
    """Dos pósteres de NTRS (2026-10-31) dan el calendario de Space Physiology y de Vestibular
    Health. Son dos de catorce: CIPHER sigue «dice que hay tomas, sin día», con las frases a la
    vista y el motivo escrito."""
    cipher = human_datasets.payload()["cipher"]
    for phase in cipher["phases"].values():
        refs = {quote["ref"] for quote in phase["cited"]}
        assert refs == {
            "nasa-cipher", "ntrs-20230000776-cipher-space-physiology",
            "ntrs-20240000955-cipher-vestibular",
        }
        assert phase["labels"] == [] and "no lleva días" in phase["why"]
        assert "no el de los catorce" in phase["searched"]
    assert "ntrs.nasa.gov" in human_datasets.SOURCE_HOSTS
    # El acceso sigue sin encontrarse; lo más cercano, el plan de datos del HRP, va citado y dicho.
    access = cipher["access"]
    assert access["level"] == "not_found"
    assert access["cited"][0]["ref"] == "ntrs-20230013774-hrp-data-management-plan"
    assert "sin nombrar CIPHER" in access["searched"]


def test_every_dataset_and_cipher_carry_their_role_as_a_emma_deduction() -> None:
    """Lo que la conversación pide de cada fuente: INPUT, KNOWLEDGE o CONTEXT, y si sirve para
    entrenar, validar o solo contextualizar. Todo el mapa es KNOWLEDGE y solo MMASH sirve para
    validar; cada uno lleva su motivo y el rótulo de deducción, y los catálogos no se clasifican."""
    payload = human_datasets.payload()
    rows = [*payload["datasets"], payload["cipher"]]
    assert len(rows) == len(DATASETS) + 1
    for item in rows:
        role = item["role"]
        assert role["level"] == "KNOWLEDGE" and role["level_text"] == (
            human_datasets.ROLE_LEVELS["KNOWLEDGE"]
        ), item["name"]
        assert role["basis_text"] == human_datasets.ROLE_BASIS, item["name"]
        assert role["level_why"].strip() and role["fitness_why"].strip(), item["name"]
        assert role["fitness_text"] == human_datasets.FITNESS[role["fitness"]], item["name"]
    fitness = {item["id"]: item["role"]["fitness"] for item in payload["datasets"]}
    assert fitness.pop("mmash") == "validate"
    assert set(fitness.values()) == {"contextualize"}
    assert payload["cipher"]["role"]["fitness"] == "contextualize"
    # Un catálogo no es una fuente de datos: no se le pone papel.
    assert all("role" not in item for item in payload["catalogs"])
    # Los tres valores existen en el enumerado aunque dos se rechacen: la respuesta es deliberada.
    assert set(human_datasets.ROLE_LEVELS) == {"INPUT", "KNOWLEDGE", "CONTEXT"}
    assert set(human_datasets.ROLE_REJECTED) == {"INPUT", "CONTEXT"}
    assert set(human_datasets.FITNESS) == {"train", "validate", "contextualize"}
    assert set(human_datasets.FITNESS_REJECTED) == {"train"}


def test_the_twins_study_has_its_ten_areas_written_whole() -> None:
    item = _served("twins-study")
    areas = item["areas"]
    assert areas["count"] == 10 and len(areas["items"]) == 10
    assert [area["name"] for area in areas["items"]] == [
        "Metabolomics", "Proteomics", "Cognition", "Microbiome", "Telomeres", "Epigenomics",
        "Biochemical", "Gene Expression", "Integrative Omics", "Immunome",
    ]
    assert "split into 10 investigations" in areas["cited"]["quote"]
    assert not any("entre otras" in variable["what"] for variable in item["variables"])


def test_the_catalogs_measure_nobody() -> None:
    for item in human_datasets.payload()["catalogs"]:
        assert registry.get(item["ref"]).population is None, item["id"]
        assert item["kb_where"] == "§8" and item["what"]
        assert "population" not in item and "phases" not in item


def test_no_public_api_of_astronaut_vitals_is_claimed() -> None:
    lines = human_datasets.payload()["not_found"]
    said = "API pública de constantes vitales de astronautas: no existe"
    assert any(said in line for line in lines)


# --------------------------------------------------------------------------- #
# Los días de las tomas y la escalera de hitos
# --------------------------------------------------------------------------- #


def test_inspiration4_has_the_ten_timepoints_in_their_segments() -> None:
    item = _served("inspiration4-soma")
    labels = [label for phase in item["phases"].values() for label in phase["labels"]]
    assert labels == ["L-92", "L-44", "L-3", "FD1", "FD2", "FD3", "R+1", "R+45", "R+82", "R+194"]
    cells = {cell["segment"]: cell["labels"] for cell in item["ladder"]}
    assert cells["L-180 → L-30"] == ["L-92", "L-44"]
    assert cells["L-30 → Flight"] == ["L-3"]
    assert cells["Flight → R+0"] == ["FD1", "FD2", "FD3"]
    assert cells["R+0 → R+7"] == ["R+1"]
    assert cells["R+30 → R+90"] == ["R+45", "R+82"]
    assert cells["R+180 → R+365"] == ["R+194"]
    assert cells["desde R+365"] == []
    empty = next(cell for cell in item["ladder"] if cell["segment"] == "desde R+365")
    assert empty["text"] == human_datasets.EMPTY_SEGMENT


def test_osd_569_has_no_inflight_draws() -> None:
    inflight = _served("osd-569")["phases"]["inflight"]
    assert inflight["status"] == "none" and inflight["labels"] == []


def test_the_ladder_covers_every_segment_once() -> None:
    payload = human_datasets.payload()
    segments = [segment["label"] for segment in payload["milestones"]["segments"]]
    assert segments[0] == "antes de L-180" and segments[-1] == "desde R+365"
    for item in payload["datasets"]:
        assert [cell["segment"] for cell in item["ladder"]] == segments
        placed = [label for cell in item["ladder"] for label in cell["labels"]]
        listed = [label for phase in item["phases"].values() for label in phase["labels"]]
        assert sorted(placed) == sorted(listed), item["id"]


def test_a_label_is_matched_whole_and_across_typography() -> None:
    assert human_datasets.written_in("L-3", ["three pre-flight (L−92, L−44 and L−3)"])
    assert human_datasets.written_in("R+1", ["(R + 1, R + 45, R + 82 and R + 194)."])
    assert not human_datasets.written_in("R+1", ["(R+194)"])
    assert not human_datasets.written_in("L-3", ["(L-30)"])
    # La carga de los ratones de OSD-288 («L-1d») no es un día de toma «L-1».
    assert not human_datasets.written_in("L-1", ["One day prior to launch (L-1d), 12 mice"])
    # El guion largo con que PMC escribe el Twins Study («L–162») es el mismo guion.
    assert human_datasets.written_in("L-162", ["his preflight (L–162; L– days before launch)"])
    assert not human_datasets.written_in("L-16", ["his preflight (L–162; L– days before launch)"])


def test_cipher_lists_fourteen_studies_and_no_invented_day() -> None:
    cipher = human_datasets.payload()["cipher"]
    assert len(cipher["studies"]) == 14
    assert [rung["id"] for rung in cipher["ladder"]] == ["short", "standard", "extended"]
    assert cipher["emma_study"] in cipher["studies"]
    # Antes, durante y después, dicho por la página; ningún día, y se dice dónde se buscó.
    for phase in cipher["phases"].values():
        assert (phase["status"], phase["labels"]) == ("stated", [])
        assert phase["searched"] and "ninguna da días" in phase["searched"]
    assert all(cell["labels"] == [] for cell in cipher["ladder_cells"])
    assert cipher["access"]["level"] == "not_found" and cipher["access"]["searched"]


# --------------------------------------------------------------------------- #
# La defensa: lo que no se sostiene no se sirve
# --------------------------------------------------------------------------- #

Breaker = Callable[[dict[str, Any]], None]


def _set(path: list[Any], value: Any) -> Breaker:
    def apply(raw: dict[str, Any]) -> None:
        node: Any = raw
        for step in path[:-1]:
            if isinstance(node, list) and isinstance(step, str):
                node = next(item for item in node if item["id"] == step)
            else:
                node = node[step]
        node[path[-1]] = value

    return apply


BROKEN: list[tuple[str, Breaker, str]] = [
    ("frase de otro sitio", _set(["datasets", "mmash", "subjects", 0, "ref"], "hrr-gaps"),
     "no es la página de la fuente"),
    ("ficha que no existe", _set(["datasets", "mmash", "subjects", 0, "ref"], "inventada"),
     "inventada"),
    ("OSD-288 humano", _set(["datasets", "osd-288", "population"], "human"), "la ficha dice"),
    ("ficheros de ratón en un estudio humano",
     _set(["datasets", "mmash", "open_population"], "animal"), "que el estudio no tiene"),
    ("OSD-343 sin decir que sus ficheros son de ratón",
     _set(["datasets", "osd-343", "open_population_note"], None), "no se dice"),
    ("un día que no está en la frase",
     _set(["datasets", "osd-569", "phases", "pre", "labels"], ["L-92", "L-180"]),
     "no está escrito"),
    ("un día R+ antes del vuelo",
     _set(["datasets", "osd-569", "phases", "pre", "labels"], ["R+1"]), "no es un día de"),
    ("tomas en vuelo en un conjunto de Tierra",
     _set(["datasets", "mmash", "phases", "inflight"], {
         "status": "stated", "labels": [],
         "cited": [{"quote": "22 healthy young adult males were recruited.", "ref": "mmash",
                    "where": "página"}],
         "why": None, "searched": None}),
     "sin vuelo"),
    ("el R+ de un reposo en cama como regreso de un vuelo",
     _set(["datasets", "agbresa", "phases", "post"], {
         "status": "labels", "labels": ["R+0"],
         "cited": [{"quote": "a 14-days recovery (R+) phase (R+0 through R+13)",
                    "ref": "clement-2022-agbresa", "where": "Methods"}],
         "why": None, "searched": None}),
     "sin vuelo"),
    ("un reposo en cama sin su calendario",
     _set(["datasets", "agbresa", "analog_schedule"], None), "sin su calendario"),
    ("un calendario de análogo en un conjunto de vuelo",
     _set(["datasets", "osd-569", "analog_schedule"], [
         {"stages": ["PRE"], "quote": "L-92", "ref": "osd-569", "where": "x"}]),
     "que no lo es"),
    ("una etapa que no es de la pauta",
     _set(["datasets", "agbresa", "analog_schedule", 0, "stages"], ["BASELINE"]),
     "fuera de la pauta"),
    ("etapas de un paso fuera de orden",
     _set(["datasets", "osd-51", "analog_schedule", 0, "stages"], ["EXPOSURE", "PRE"]),
     "etapas fuera del orden"),
    ("el R+ de un reposo en cama como etapa POST del calendario",
     _set(["datasets", "agbresa", "analog_schedule", 4, "stages"], ["POST"]),
     "no nombra la etapa POST"),
    ("una centrifugación como etapa de exposición",
     _set(["datasets", "agbresa", "analog_schedule", 2, "stages"], ["EXPOSURE"]),
     "no nombra la etapa EXPOSURE"),
    ("una pauta del análogo con un punto repetido",
     _set(["analog_pattern", "points"], ["PRE", "EXPOSURE", "PRE"]), "punto repetido"),
    ("la pauta del análogo cambiada",
     _set(["analog_pattern", "points"], ["PRE", "POST"]), "pauta del análogo"),
    ("controles de OSD-288 humanos",
     _set(["datasets", "osd-288", "controls", "items", 0, "population"], "human"),
     "el conjunto mide 'animal'"),
    ("un control que su frase no nombra",
     _set(["datasets", "osd-288", "controls", "items", 0, "quote"], "Space Flight"),
     "la frase no nombra"),
    ("un control a 1 g en vuelo en un reposo en cama",
     _set(["datasets", "agbresa", "controls", "items", 0, "kind"], "inflight_1g"),
     "conjunto sin vuelo"),
    ("un control de análogo fuera de un análogo",
     _set(["datasets", "osd-343", "controls", "items", 0], {
         "kind": "analog_control", "population": "animal",
         "quote": "a habitat control group", "ref": "osd-343", "where": "protocolo"}),
     "fuera de un análogo"),
    ("un gemelo de control que no es una persona",
     _set(["datasets", "osd-343", "controls", "items", 0], {
         "kind": "twin", "population": "animal", "quote": "twin ground controls",
         "ref": "osd-343", "where": "protocolo"}),
     "no es una persona"),
    ("un control de tipo desconocido",
     _set(["datasets", "osd-288", "controls", "items", 0, "kind"], "vivarium"), "desconocido"),
    ("un control repetido",
     _set(["datasets", "osd-288", "controls", "items", 1], {
         "kind": "ground", "population": "animal", "quote": "Ground Control", "ref": "osd-288",
         "where": "x"}),
     "repetido"),
    ("controles listados sin ninguno",
     _set(["datasets", "osd-288", "controls", "items"], []), "sin ninguno"),
    ("controles no encontrados sin dónde",
     lambda raw: _dataset(raw, "mmash")["controls"].update(status="not_found", why=None),
     "dónde se buscó"),
    ("controles que no proceden sin motivo",
     _set(["datasets", "mmash", "controls", "why"], None), "sin decir por qué"),
    ("sin controles, sin frase ni motivo",
     lambda raw: _dataset(raw, "mmash")["controls"].update(status="none", why=None),
     "sin controles"),
    ("controles con un estado desconocido",
     _set(["datasets", "mmash", "controls", "status"], "quizá"), "desconocido"),
    ("el Twins Study con un área de menos",
     lambda raw: _dataset(raw, "twins-study")["areas"]["items"].pop(), "no cuadran"),
    ("el Twins Study con un área de más, repetida",
     lambda raw: _dataset(raw, "twins-study")["areas"]["items"].append(
         copy.deepcopy(_dataset(raw, "twins-study")["areas"]["items"][0])),
     "no cuadran"),
    ("el Twins Study con un área repetida",
     lambda raw: _dataset(raw, "twins-study")["areas"]["items"][1].update(name="Metabolomics"),
     "no cuadran"),
    ("el Twins Study con un número que su página no da",
     lambda raw: _dataset(raw, "twins-study")["areas"].update(
         count=9, items=_dataset(raw, "twins-study")["areas"]["items"][:9]),
     "no cuadran"),
    ("una cuenta que es un booleano, aunque la frase diga «True»",
     lambda raw: _dataset(raw, "twins-study")["areas"].update(
         count=True,
         cited={**_dataset(raw, "twins-study")["areas"]["cited"], "quote": "True investigations"},
         items=_dataset(raw, "twins-study")["areas"]["items"][:1]),
     "no cuadran"),
    ("un área sin su nombre",
     _set(["datasets", "twins-study", "areas", "items", 0, "what"], ""), "falta `name`"),
    ("un catálogo que mide a alguien",
     _set(["catalogs", "data-nasa-gov", "ref"], "mmash"), "un catálogo con población"),
    ("un catálogo sin frase",
     _set(["catalogs", "data-nasa-gov", "what"], []), "sin ninguna frase"),
    ("un catálogo con un campo de más",
     _set(["catalogs", "data-nasa-gov", "population"], "human"), "campos desconocidos"),
    ("un catálogo repetido",
     lambda raw: raw["catalogs"].append(copy.deepcopy(raw["catalogs"][0])), "repetido"),
    ("una fila de la base de conocimiento sin su apartado",
     _set(["datasets", "osd-288", "kb_where"], None), "sin su apartado"),
    ("un apartado sin fila",
     _set(["datasets", "mmash", "kb_where"], "§8"), "sin la fila"),
    ("una frase con una fecha que no es fecha",
     _set(["datasets", "osd-51", "subjects", 0, "read_on"], "ayer"), "no es una fecha"),
    ("una frase leída antes que el fichero",
     _set(["datasets", "osd-51", "subjects", 0, "read_on"], "2026-10-01"), "antes que el fichero"),
    ("pasos de un calendario fuera de orden entre sí",
     lambda raw: _dataset(raw, "agbresa")["analog_schedule"].reverse(), "pasos fuera del orden"),
    ("una pieza con frase con un campo de más",
     _set(["datasets", "osd-288", "controls", "items", 0, "labels"], ["R+1"]),
     "campos desconocidos"),
    ("un paso de calendario con un campo mal escrito",
     _set(["datasets", "agbresa", "analog_schedule", 0, "read-on"], "2026-10-23"),
     "campos desconocidos"),
    ("lo que la fuente dice que no hay, con controles que no proceden",
     _set(["datasets", "mmash", "controls", "absent"], [
         {"quote": "This study did not have age- and sex-matched controls on Earth",
          "ref": "jones-2024-inspiration4", "where": "Discussion", "read_on": "2026-10-23"}]),
     "el estado es 'not_applicable'"),
    ("una frase que niega el control como control",
     lambda raw: _dataset(raw, "inspiration4-soma")["controls"]["items"][0].update(
         kind="ground",
         quote="This study did not have age- and sex-matched controls on Earth"),
     "niega el control"),
    ("un periodo de control como grupo de control",
     _set(["datasets", "inspiration4-soma", "controls", "items", 0, "quote"],
          "a preflight control period"),
     "nombra un periodo"),
    ("una frase que niega el control después de nombrarlo",
     lambda raw: _dataset(raw, "inspiration4-soma")["controls"]["items"][0].update(
         kind="ground", quote="Ground controls were not flown"),
     "niega el control"),
    ("un «control» suelto como grupo del análogo",
     _set(["datasets", "agbresa", "controls", "items", 0, "quote"], "Ground Control"),
     "la frase no nombra"),
    ("un gemelo de control en un reposo en cama",
     _set(["datasets", "agbresa", "controls", "items", 0], {
         "kind": "twin", "population": "human",
         "quote": "his twin served as a genetically matched ground control.",
         "ref": "clement-2022-agbresa", "where": "Methods"}),
     "ya está allí"),
    ("una frase de un conjunto que cita un catálogo",
     _set(["datasets", "osd-288", "subjects", 0, "ref"], "nasa-open-data-portal"),
     "no es la página de la fuente"),
    ("la fase basal de un reposo en cama como control antes del vuelo",
     _set(["datasets", "agbresa", "controls", "items", 0], {
         "kind": "own_baseline", "population": "human",
         "quote": "a 14-days baseline data collection (BDC) phase",
         "ref": "clement-2022-agbresa", "where": "Methods"}),
     "antes del vuelo en un conjunto sin vuelo"),
    ("un control en Tierra en un reposo en cama",
     _set(["datasets", "agbresa", "controls", "items", 0], {
         "kind": "ground", "population": "human", "quote": "a ground control group",
         "ref": "clement-2022-agbresa", "where": "Methods"}),
     "ya está allí"),
    ("lo que no hay con un campo mal escrito",
     _set(["datasets", "inspiration4-soma", "controls", "absent", 0, "read-on"], "2026-10-23"),
     "campos desconocidos"),
    ("la frase que cuenta las áreas con un campo mal escrito",
     _set(["datasets", "twins-study", "areas", "cited", "read-on"], "2026-10-23"),
     "campos desconocidos"),
    ("una frase de catálogo con un campo mal escrito",
     _set(["catalogs", "data-nasa-gov", "what", 0, "read-on"], "2026-10-23"),
     "campos desconocidos"),
    ("una frase de las tomas con un campo mal escrito",
     _set(["datasets", "osd-569", "phases", "pre", "cited", 0, "read-on"], "2026-10-23"),
     "campos desconocidos"),
    ("una fila de un apartado que no es de la base de conocimiento",
     _set(["datasets", "osd-288", "kb_where"], "§9"), "las filas salen de"),
    ("sin los puntos de Biolab",
     lambda raw: raw.pop("controls_rule"), "controls_rule"),
    ("una pauta del análogo que no es texto",
     _set(["analog_pattern", "points"], [1, 2]), "analog_pattern"),
    ("sin catálogos", lambda raw: raw.pop("catalogs"), "no es una lista"),
    ("un «only» cualquiera como grupo de control",
     _set(["datasets", "osd-51", "controls", "items", 0, "quote"],
          "only 12 subjects completed the protocol"),
     "la frase no nombra"),
    ("una fecha del fichero sin forma", _set(["read_on"], "22-10-2026"), "AAAA-MM-DD"),
    ("los puntos de Biolab vacíos",
     _set(["controls_rule", "points"], []), "controls_rule"),
    ("tomas sin frase", _set(["datasets", "osd-353", "phases", "pre", "cited"], []),
     "sin una frase"),
    ("no encontrado sin dónde",
     _set(["datasets", "osd-343", "phases", "pre", "searched"], None), "dónde se buscó"),
    ("no procede sin motivo", _set(["datasets", "mmash", "phases", "post", "why"], None),
     "sin decir por qué"),
    ("acceso de la fuente sin frase", _set(["datasets", "mmash", "access", "cited"], []),
     "sin su frase"),
    ("fichero de EMMA sin nombre",
     lambda raw: _dataset(raw, "osd-569")["access"].update(
         level="file_open", basis="emma", path=None),
     "no lo nombra"),
    ("ruta de acceso fuera del repositorio",
     _set(["datasets", "osd-569", "access", "path"], "../fuera.csv"),
     "no es un fichero del repositorio"),
    ("deducción sin motivo",
     lambda raw: _dataset(raw, "osd-343")["access"].update(basis="deduced", cited=[], why=None),
     "sin su motivo"),
    ("uso en EMMA que reclama de más",
     _set(["datasets", "mmash", "emma_use", "text"], "Valida la fisiología espacial."),
     "reclama de más"),
    ("uso en EMMA que copia una cifra",
     _set(["datasets", "mmash", "emma_use", "text"], "Falsa alarma del 2,5 %."), "copia una cifra"),
    ("uso en EMMA sin fichero", _set(["datasets", "mmash", "emma_use", "where"], None),
     "no nombra un fichero"),
    ("CIPHER con un estudio de menos",
     _set(["cipher", "studies"], ["Bone Health"]), "no cuadra"),
    ("CIPHER cita un estudio que no tiene",
     _set(["cipher", "emma_study"], "Twins Study"), "no es uno de sus estudios"),
    ("hitos fuera de orden", _set(["milestones", "points"],
     ["L-30", "L-180", "Flight", "R+0", "R+7", "R+30", "R+90", "R+180", "R+365"]),
     "no son los del texto"),
    ("un campo de más", _set(["datasets", "mmash", "inventado"], 1), "campos desconocidos"),
    ("tomas con día sin ningún día",
     _set(["datasets", "osd-569", "phases", "pre", "labels"], []), "sin ningún día"),
    ("días con otro estado",
     _set(["datasets", "osd-353", "phases", "pre", "labels"], ["L-92"]),
     "sin el estado de tomas con día"),
    ("acceso no encontrado con origen de fuente",
     _set(["datasets", "mmash", "access", "level"], "not_found"), "en el nivel y en su origen"),
    ("sin uso en EMMA, pero con fichero",
     _set(["datasets", "inspiration4-soma", "emma_use", "where"], "backend/app/evidence/links.py"),
     "pero con fichero"),
    ("tener un fichero no dice que todo el conjunto sea abierto",
     _set(["datasets", "osd-569", "access", "basis"], "emma"), "solo dice que ese fichero"),
    # El papel y la aptitud (decimonovena ronda, U5): valores cerrados, cada uno con su motivo.
    ("un papel que no es texto", _set(["datasets", "mmash", "role", "level"], ["KNOWLEDGE"]),
     "desconocido"),
    ("una aptitud que no es texto", _set(["datasets", "mmash", "role", "fitness"], ["validate"]),
     "desconocida"),
    ("un conjunto como señal de misión (INPUT)",
     _set(["datasets", "mmash", "role", "level"], "INPUT"), "no están en este mapa"),
    ("un conjunto como contexto (CONTEXT)",
     _set(["datasets", "mmash", "role", "level"], "CONTEXT"), "con población es KNOWLEDGE"),
    ("un papel desconocido", _set(["datasets", "mmash", "role", "level"], "DATA"), "desconocido"),
    ("entrenar con un conjunto",
     _set(["datasets", "mmash", "role", "fitness"], "train"), "no entrena ningún modelo"),
    ("una aptitud desconocida",
     _set(["datasets", "mmash", "role", "fitness"], "calibrate"), "desconocida"),
    ("validar con un conjunto que EMMA no usa",
     _set(["datasets", "osd-51", "role", "fitness"], "validate"), "no usa no sirve para validar"),
    ("validar el motor con los ficheros de ratón de OSD-343",
     _set(["datasets", "osd-343", "role", "fitness"], "validate"), "no las miden"),
    ("CIPHER como validación, sin ficheros",
     _set(["cipher", "role", "fitness"], "validate"), "no las miden"),
    ("una deducción del papel sin motivo",
     _set(["datasets", "mmash", "role", "level_why"], ""), "sin su motivo"),
    ("un motivo de la aptitud que reclama de más",
     _set(["datasets", "mmash", "role", "fitness_why"], "Valida la fisiología espacial."),
     "reclama de más"),
    ("un motivo de la aptitud que copia una cifra",
     _set(["datasets", "mmash", "role", "fitness_why"], "Falsa alarma del 2,5 %."),
     "copia una cifra"),
    ("un papel con un campo de más",
     _set(["datasets", "mmash", "role", "basis"], "deduced"), "campos desconocidos"),
    ("un papel que no es un bloque",
     _set(["datasets", "mmash", "role"], "KNOWLEDGE"), "es un bloque"),
    ("un conjunto sin papel", lambda raw: _dataset(raw, "mmash").pop("role"), "faltan campos"),
    ("CIPHER sin papel", lambda raw: raw["cipher"].pop("role"), "faltan campos"),
    ("sin la regla de la aptitud", lambda raw: raw.pop("fitness_rule"), "fitness_rule"),
    ("uso en EMMA sin la ficha que cita",
     _set(["datasets", "mmash", "emma_use", "cites"], None), "sin la ficha que cita"),
    ("uso en EMMA con una ficha que no existe",
     _set(["datasets", "mmash", "emma_use", "cites"], "inventada"), "inventada"),
    ("CIPHER con un campo de más", _set(["cipher", "inventado"], 1), "campos desconocidos"),
    ("CIPHER con días que su página no da",
     _set(["cipher", "phases", "pre", "labels"], ["L-30"]), "sin el estado de tomas con día"),
    ("CIPHER con un número que no es un número",
     _set(["cipher", "study_count"], True), "no cuadra"),
    ("CIPHER con un estudio repetido",
     _set(["cipher", "studies"], ["Bone Health"] * 14), "no cuadra"),
    ("CIPHER con un número que su página no da",
     lambda raw: raw["cipher"].update(study_count=13, studies=raw["cipher"]["studies"][:13]),
     "no cuadra"),
]


@pytest.mark.parametrize(("label", "breaker", "reason"), BROKEN, ids=[item[0] for item in BROKEN])
def test_what_cannot_be_sustained_is_rejected(
    raw: dict[str, Any], label: str, breaker: Breaker, reason: str
) -> None:
    breaker(raw)
    with pytest.raises((DatasetMapError, registry.RegistryError, KeyError), match=reason):
        human_datasets.validate(raw)


@pytest.mark.parametrize("quote", [
    "a no-exercise control group",
    "subjects without countermeasure served as the control group",
])
def test_a_group_described_by_what_it_does_not_receive_is_still_a_control(
    raw: dict[str, Any], quote: str
) -> None:
    """La negación que rechaza un control es la que lo rige, no la que describe al grupo."""
    _dataset(raw, "osd-51")["controls"]["items"][0]["quote"] = quote
    human_datasets.validate(raw)


def test_milestones_in_the_wrong_order_are_rejected_even_if_the_text_agrees(
    raw: dict[str, Any],
) -> None:
    points = ["L-30", "L-180", "Flight", "R+0", "R+7", "R+30", "R+90", "R+180", "R+365"]
    raw["milestones"]["points"] = points
    raw["milestones"]["text"] = " → ".join(points)
    with pytest.raises(DatasetMapError, match="orden del vuelo"):
        human_datasets.validate(raw)


def test_what_is_served_does_not_share_the_cached_dictionaries() -> None:
    served = human_datasets.payload()
    served["task"]["text"] = "otra"
    served["rule"]["text"] = "otra"
    served["cipher"]["studies"].clear()
    fresh = human_datasets.payload()
    assert fresh["task"]["text"] != "otra" and fresh["rule"]["text"] != "otra"
    assert len(fresh["cipher"]["studies"]) == 14


def test_a_ground_dataset_is_not_told_to_use_an_analog_calendar(raw: dict[str, Any]) -> None:
    """El arreglo que propone el rechazo tiene que ser uno que el cargador admita."""
    _dataset(raw, "mmash")["phases"]["pre"].update(status="none")
    with pytest.raises(DatasetMapError, match="en Tierra sus tres fases no proceden") as caught:
        human_datasets.validate(raw)
    assert "calendario" not in str(caught.value)


def test_a_simulated_dataset_is_not_a_human_dataset(
    raw: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    real = registry.get

    def simulated(ident: str) -> Any:
        ref = real(ident)
        return replace(ref, evidence_context=EvidenceContext.SIMULATED) if ident == "mmash" else ref

    monkeypatch.setattr(human_datasets.registry, "get", simulated)
    with pytest.raises(DatasetMapError, match="simulado"):
        human_datasets.validate(raw)


def test_a_missing_phase_is_rejected(raw: dict[str, Any]) -> None:
    del _dataset(raw, "mmash")["phases"]["inflight"]
    with pytest.raises(DatasetMapError, match="tres fases"):
        human_datasets.validate(raw)


# --------------------------------------------------------------------------- #
# La API
# --------------------------------------------------------------------------- #


def test_the_api_serves_the_map_offline(client: TestClient) -> None:
    response = client.get("/api/human-datasets")
    assert response.status_code == 200
    body = response.json()
    assert body == json.loads(json.dumps(human_datasets.payload()))
    assert body["note"] == human_datasets.NOTE
    assert body["phases"] == human_datasets.PHASES
