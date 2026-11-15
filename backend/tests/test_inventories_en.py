"""Los inventarios de evidencia en inglés: bancos de prueba, instalaciones, conjuntos humanos,
fuentes del contexto, personas, y los cotejos con OSDR y NTRS.

Por qué existe: estos inventarios son donde EMMA dice contra qué se ha medido y contra qué no. Su
texto vive en cuatro JSON de `app/data/` que los cargadores validan en castellano (lo que reclama
de más, una cifra copiada, una frase sin ficha), y el inglés entra después, al servir, por un
fichero hermano. Una traducción no pasa por esos validadores: si dijera más que el castellano
—una cifra que el original no tiene, un «validated» donde ponía «no valida»— nada lo vería. Aquí
se coteja el inglés con su castellano, cadena a cadena, y se comprueba lo que NO cambia con el
idioma: las frases literales de las fuentes y de los documentos del equipo, los identificadores y
la respuesta en castellano de siempre.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.routes import new_store, reset_store
from app.core import i18n
from app.core.cache import FileCache
from app.core.config import Settings, get_settings
from app.evidence import (
    context_sources,
    facilities,
    human_datasets,
    ntrs,
    osdr_data,
    people,
    registry,
    testbeds,
)
from app.main import app
from tests.conftest import ENGLISH_HEADERS

# Los campos que no se traducen, por su clave: citas literales (`quote`, `kb_row`, `listed_as`,
# el `title` de una lista del equipo), identificadores, fechas, días de toma, rutas y nombres que
# la fuente escribe así. Es la lista que declara el `_nota` de cada fichero inglés.
UNTRANSLATED_KEYS = frozenset({
    "_nota", "quote", "ref", "read_on", "id", "basis", "hazard", "status", "evidence_context",
    "rung", "validation", "full_name", "context", "step", "experiment", "level", "fitness",
    "kind", "population", "open_population", "path", "cites", "kb_row", "kb_where", "document",
    "section", "listed_as", "labels", "stages", "points", "studies", "emma_study", "lists",
    "figures_in",
})
# `text` es literal cuando su bloque es una cita de un documento del equipo; en `emma_use` es
# redacción de EMMA y se traduce.
QUOTED_TEXT_BLOCKS = frozenset({
    "rule", "principle", "task", "fitness_rule", "milestones", "analog_pattern", "chain",
    "kb_role",
})

MAPS: dict[str, tuple[Path, Callable[[], dict[str, Any]], Callable[[], dict[str, Any]]]] = {
    "testbeds": (testbeds.TESTBEDS_PATH, testbeds.read, testbeds.payload),
    "facilities": (facilities.FACILITIES_PATH, facilities.read, facilities.payload),
    "human-datasets": (human_datasets.DATASETS_PATH, human_datasets.read, human_datasets.payload),
    "context-sources": (
        context_sources.CONTEXT_SOURCES_PATH, context_sources.read, context_sources.payload,
    ),
}

# Lo que va entre «» es una cita (de la fuente, o de un documento del equipo) y no se juzga como
# inglés de EMMA: «an experienced and certified professional diving staff» es de NASA.
_QUOTED = re.compile(r"«[^»]*»")
_SPANISH_ONLY = re.compile(r"[áéíóúñ¿¡]", re.IGNORECASE)
# Rótulos de la consola o del propio mapa que un texto nombra entre «»: no son citas de nadie.
_OWN_LABELS = frozenset({
    "«en parte»", "«Qué deja fuera»", "«aislamiento de misión»", "«Parámetros medidos»",
    "«Equipos»", "«Investigadores»", "«Experimentos»", "«Limitaciones»",
    "«Aplicación ISS / Luna / Marte»", "«Oportunidad»",
})
# Nombres propios con tilde que el inglés conserva.
_PROPER_NAMES = ("Clément",)
# Nada que suene a certificación, a prueba concluyente, a diagnóstico o a orden médica.
_FORBIDDEN = re.compile(r"certified|validated EMMA|proves|diagnos|administer", re.IGNORECASE)
# Lo que el validador castellano (`testbeds.CLAIM`) impide decir de EMMA, en inglés.
_CLAIM_EN = re.compile(
    r"\b(certif\w*|validated|validates|verified|compliant|complies|approved)\b", re.IGNORECASE
)
# `testbeds.COPIED_FIGURE` en inglés: un porcentaje, «n of m», «n/m» o un decimal.
_COPIED_FIGURE_EN = re.compile(
    r"%|\b\d+\s+(?:out\s+)?of\s+\d+\b|\b\d+\s*/\s*\d+\b|\b\d+[.,]\d+\b"
)
# Los millares se escriben con espacio en castellano y a veces con coma en una cita inglesa.
_GROUP = re.compile(r"(?<=\d)[   ,](?=\d{3}(?!\d))")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _numbers(text: str) -> list[str]:
    """Las cifras de un texto, con la coma decimal como punto y sin separador de millares."""
    return sorted(found.replace(",", ".") for found in _NUMBER.findall(_GROUP.sub("", text)))


def _own_words(text: str) -> str:
    """El texto sin lo que cita entre «» ni los nombres propios con tilde."""
    plain = _QUOTED.sub("", text)
    for name in _PROPER_NAMES:
        plain = plain.replace(name, "")
    return plain


def _strings(value: Any, key: str = "", block: str = "") -> Iterator[tuple[str, str, str]]:
    """Cada cadena con la clave bajo la que está y el bloque que la contiene."""
    if isinstance(value, str):
        yield value, key, block
    elif isinstance(value, dict):
        for name, item in value.items():
            yield from _strings(item, name, key)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item, key, block)


def _is_untranslated(key: str, block: str) -> bool:
    return (
        key in UNTRANSLATED_KEYS
        or (key == "text" and block in QUOTED_TEXT_BLOCKS)
        # El encabezado de un documento del equipo, tal cual; el título de la escalera se traduce.
        or (key == "title" and block == "lists")
    )


def _untranslated(raw: dict[str, Any]) -> set[str]:
    """Las cadenas del fichero castellano que el `_nota` del inglés declara fuera."""
    return {text for text, key, block in _strings(raw) if _is_untranslated(key, block)}


def _translatable(raw: dict[str, Any]) -> set[str]:
    return {text for text, key, block in _strings(raw) if not _is_untranslated(key, block)}


def _differences(spanish: Any, english: Any, path: str = "") -> Iterator[str]:
    """Las rutas en que dos respuestas difieren. Formas distintas también son una diferencia."""
    if isinstance(spanish, dict) and isinstance(english, dict):
        if spanish.keys() != english.keys():
            yield f"{path} (claves)"
            return
        for key in spanish:
            yield from _differences(spanish[key], english[key], f"{path}.{key}")
    elif isinstance(spanish, list) and isinstance(english, list):
        if len(spanish) != len(english):
            yield f"{path} (longitud)"
            return
        for one, other in zip(spanish, english, strict=True):
            yield from _differences(one, other, f"{path}[]")
    elif spanish != english:
        yield path


def _last_key(path: str) -> str:
    return path.rsplit(".", 1)[-1].removesuffix("[]")


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, assistant_warmup=False
    )
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


# --------------------------------------------------------------------------- #
# El fichero inglés frente a su castellano
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", sorted(MAPS))
def test_every_text_emma_writes_has_its_english_and_no_quote_does(name: str) -> None:
    path, read, _ = MAPS[name]
    raw = read()
    skipped = _untranslated(raw)
    assert i18n.missing(path, raw, skip=lambda text: text in skipped) == []
    overlay = i18n.overlay(path)
    # Ni una entrada de más: una frase que ya no está en el castellano no se queda traducida.
    assert set(overlay) - _translatable(raw) == set()
    # Una cita literal no tiene inglés, salvo que el mismo texto sea además redacción de EMMA en
    # otro campo (un rótulo de la fuente usado como `where`), y entonces queda igual.
    for text in skipped & set(overlay):
        assert overlay[text] == text, text


@pytest.mark.parametrize("name", sorted(MAPS))
def test_the_english_has_the_figures_of_its_spanish_and_no_others(name: str) -> None:
    """Lo que `testbeds.COPIED_FIGURE` vigila en castellano, para la traducción: ninguna cifra
    aparece en el inglés sin estar en la frase que traduce, ni se pierde ninguna."""
    for spanish, english in i18n.overlay(MAPS[name][0]).items():
        assert _numbers(english) == _numbers(spanish), spanish
        # Lo que el castellano cita entre «» sigue igual en el inglés (con su glosa fuera, si la
        # lleva), salvo los rótulos de la propia consola, que tienen su inglés.
        for quote in _QUOTED.findall(spanish):
            assert quote in english or quote in _OWN_LABELS, (quote, spanish)


@pytest.mark.parametrize("name", sorted(MAPS))
def test_the_english_claims_nothing_and_leaves_no_spanish(name: str) -> None:
    for spanish, english in i18n.overlay(MAPS[name][0]).items():
        own = _own_words(english)
        assert not _FORBIDDEN.search(own), english
        assert not _SPANISH_ONLY.search(own), english
        assert english.strip() == english and english, spanish


def test_the_english_about_emma_does_not_claim_what_the_spanish_may_not() -> None:
    """Los campos en los que `validate` rechaza un «validado» o un «cumple», en su inglés."""
    with i18n.use("en"):
        served = testbeds.payload()
        datasets = human_datasets.payload()
    about: list[str] = []
    for bank in served["banks"]:
        about += [bank["emma_use"], bank["context_basis"]]
        about += [column["not_found"] or "" for column in bank["columns"]]
        about += [cell["why"] or "" for cell in bank["ridge"]]
    for validation in served["validations"]:
        about += [validation["name"], validation["what"], validation["not_covered"]]
        for item in validation["emma"]:
            about.append(item["what"])
            # Ni una cifra de la validación externa: allí se mide, aquí se remite.
            assert not _COPIED_FIGURE_EN.search(item["what"] + item["does_not_show"]), item["id"]
    for item in [*datasets["datasets"], *datasets["catalogs"], datasets["cipher"]]:
        about.append(item["emma_use"]["text"])
        if "role" in item:
            about += [item["role"]["level_why"], item["role"]["fitness_why"]]
    assert len(about) > 150
    for text in about:
        assert not _CLAIM_EN.search(_own_words(text)), text


# --------------------------------------------------------------------------- #
# Lo que no cambia con el idioma
# --------------------------------------------------------------------------- #

# Las claves de la respuesta cuyo valor puede cambiar con el idioma. Todo lo demás —ids, fichas,
# estados, fechas, frases literales, direcciones— tiene que salir igual.
DISPLAY_KEYS: dict[str, frozenset[str]] = {
    "testbeds": frozenset({
        "note", "where", "context_basis", "emma_use", "variables_kb", "what", "why", "not_found",
        "label", "status_text", "basis_text", "validation_text", "text", "name", "title",
        "environment", "strength", "limitation", "use", "does_not_show", "not_covered",
    }),
    "facilities": frozenset({
        "note", "where", "what", "searched", "scope_caveat", "not_found", "label", "status_text",
        "unsourced",
    }),
    "human-datasets": frozenset({
        "note", "where", "what", "why", "searched", "caveat", "open_population_note", "text",
        "name", "label", "segment", "status_text", "level_text", "basis_text", "fitness_text",
        "kind_text", "used_text", "level_why", "fitness_why", "studies_where", "not_found",
        "pre", "inflight", "post",
    }),
    "context-sources": frozenset({"note", "why_added", "not_read", "emma_use", "status_text"}),
}


@pytest.mark.parametrize("name", sorted(MAPS))
def test_only_display_text_changes_with_the_language(name: str, client: TestClient) -> None:
    _, _, payload = MAPS[name]
    spanish = client.get(f"/api/{name}").json()
    english = client.get(f"/api/{name}", headers=ENGLISH_HEADERS).json()
    # Sin la cabecera, la respuesta de siempre.
    assert spanish == json.loads(json.dumps(payload()))
    changed = list(_differences(spanish, english))
    assert len(changed) > 20
    assert {_last_key(path) for path in changed} - DISPLAY_KEYS[name] == set()
    # Y el castellano en caché no se ha tocado al servir el inglés.
    assert client.get(f"/api/{name}").json() == spanish


def _quotes(value: Any) -> list[str]:
    return [text for text, key, _ in _strings(value) if key == "quote"]


@pytest.mark.parametrize("name", sorted(MAPS))
def test_source_quotes_are_served_as_written(name: str) -> None:
    _, read, payload = MAPS[name]
    with i18n.use("en"):
        english = payload()
    assert _quotes(english) == _quotes(payload())
    assert set(_quotes(read())) >= set(_quotes(english))


def test_the_team_documents_are_quoted_in_their_language() -> None:
    with i18n.use("en"):
        beds, places = testbeds.payload(), facilities.payload()
        data, sources = human_datasets.payload(), context_sources.payload()
    raw = testbeds.read()
    assert beds["rule"] == raw["rule"]
    assert beds["principle"]["text"] == raw["principle"]["text"]
    raw = facilities.read()
    assert places["chain"] == raw["chain"]
    assert [item["kb_role"] for item in places["facilities"]] == [
        item["kb_role"] for item in raw["facilities"]
    ]
    raw = human_datasets.read()
    for block in ("rule", "task", "fitness_rule", "milestones", "analog_pattern"):
        assert data[block]["text"] == raw[block]["text"], block
    assert data["analog_pattern"]["points"] == raw["analog_pattern"]["points"]
    assert data["controls_rule"]["points"] == raw["controls_rule"]["points"]
    assert [item["kb_row"] for item in data["datasets"]] == [
        item["kb_row"] for item in raw["datasets"]
    ]
    raw = context_sources.read()
    assert [item["listed_as"] for item in sources["sources"]] == [
        item["listed_as"] for item in raw["sources"]
    ]
    assert sources["lists"] == raw["lists"]


# --------------------------------------------------------------------------- #
# Lo que dice el inglés
# --------------------------------------------------------------------------- #


def test_testbeds_in_english_keep_every_limit(client: TestClient) -> None:
    body = client.get("/api/testbeds", headers=ENGLISH_HEADERS).json()
    assert body["note"].startswith("No testbed reproduces a whole mission to Mars")
    assert body["ridge"]["note"].endswith("All of them leave out at least one.")
    assert [item["text"] for item in body["ridge"]["statuses"]] == [
        "reproduces it", "partly", "leaves it out", "not known",
    ]
    scientific, operational = body["validations"]
    assert scientific["name"] == "Scientific validation"
    assert scientific["emma_status"] == {
        "status": "partial", "text": "Scientific validation of EMMA: partly.",
    }
    assert operational["emma_status"] == {
        "status": "none", "text": "Operational validation of EMMA: none.",
    }
    assert operational["not_covered"] == "EMMA has not been through HERA, CHAPEA, MMEA or NEEMO."
    # Las minas de CLAUDE.md, con sus negaciones.
    mmash = next(item for item in scientific["emma"] if item["id"] == "mmash")
    assert mmash["does_not_show"] == (
        "It does not validate space physiology or the drift of a mission: they are healthy "
        "people on Earth for one day."
    )
    assert "there is no public API of astronaut vital signs" in scientific["not_covered"]
    iss = next(bank for bank in body["banks"] if bank["id"] == "iss")
    assert "there is no public API" in iss["emma_use"]
    assert "OSD-288, which are mice (immunological support, not telemetry)" in iss["emma_use"]
    hera = next(bank for bank in body["banks"] if bank["id"] == "hera")
    assert hera["validation_text"] == "operational"
    assert [column["label"] for column in hera["columns"]] == list(testbeds.COLUMNS_EN.values())
    assert all(cell["basis_text"] in testbeds.RIDGE_BASIS_EN.values() for cell in hera["ridge"])
    assert "EMMA has not been through HERA" in hera["emma_use"]
    # Lo buscado y no encontrado sigue dicho, columna a columna y al pie.
    empty = [column for bank in body["banks"] for column in bank["columns"] if not column["quotes"]]
    assert empty and all(column["not_found"] for column in empty)
    assert not any(_SPANISH_ONLY.search(_own_words(column["not_found"])) for column in empty)
    assert len(body["not_found"]) == len(testbeds.read()["not_found"])
    mars = next(rung for rung in body["ladder"]["rungs"] if rung["id"] == "mars")
    assert mars["limitation"] == "no complete testbed exists"


def test_emma_status_follows_the_language() -> None:
    assert testbeds.emma_status("operational")["text"] == "Validación operacional de EMMA: ninguna."
    with i18n.use("en"):
        assert testbeds.emma_status("operational") == {
            "status": "none", "text": "Operational validation of EMMA: none.",
        }


def test_facilities_in_english_say_what_was_not_found(client: TestClient) -> None:
    body = client.get("/api/facilities", headers=ENGLISH_HEADERS).json()
    assert body["note"].startswith("Two European facilities of the station")
    epm, biolab = body["facilities"]
    assert [link["label"] for link in epm["links"]] == list(facilities.STEPS_EN.values())
    assert biolab["unsourced"] == ["dataset"]
    dataset = next(link for link in biolab["links"] if link["step"] == "dataset")
    assert dataset["status"] == "not_found"
    assert dataset["status_text"] == "unverified: searched and not found"
    assert dataset["missing"]["what"] == "A dataset of TripleLux-A."
    assert len(dataset["missing"]["searched"]) == 3
    assert biolab["scope_caveat"].startswith("Rat cells in culture, not people")
    assert len(body["not_found"]) == 5
    assert all("no se" not in line and "not" in line for line in body["not_found"])


def test_human_datasets_in_english_keep_the_known_pitfalls(client: TestClient) -> None:
    body = client.get("/api/human-datasets", headers=ENGLISH_HEADERS).json()
    assert "There is no public API of astronaut vital signs" in body["note"]
    assert body["phases"] == human_datasets.PHASES_EN
    assert body["milestones"]["segments"][0]["label"].startswith("before L-")
    assert body["milestones"]["segments"][-1]["label"].startswith("from R+")
    by_id = {item["id"]: item for item in body["datasets"]}
    # OSD-288 es bazo de ratón, no datos de astronautas ni telemetría.
    mice = by_id["osd-288"]
    assert mice["caveat"] == "Mice, not astronauts: it does not measure human vital signs."
    assert "It is not telemetry and does not measure a person." in mice["emma_use"]["text"]
    # MMASH: 22 personas sanas, 24 h, en Tierra; no valida fisiología de vuelo.
    mmash = by_id["mmash"]
    assert mmash["caveat"] == (
        "Healthy people on Earth for 24 h: it is not the physiology of flight or of a long "
        "mission."
    )
    assert "22 healthy people measured for one day on Earth" in mmash["controls"]["why"]
    assert mmash["phases"]["inflight"]["status_text"] == "not applicable"
    assert mmash["role"]["fitness"] == "validate"
    assert mmash["role"]["basis_text"] == "EMMA's deduction from what was read"
    assert "It trains nothing" in mmash["role"]["fitness_why"]
    # OSD-343: los ficheros abiertos son de ratón aunque el estudio hable de astronautas.
    assert by_id["osd-343"]["open_population_note"].endswith(
        "are from mice (muscle, Rodent Research-9)."
    )
    assert by_id["osd-569"]["access"]["level_text"] == (
        "open in part; what is sensitive, under controlled access"
    )
    assert body["cipher"]["access"]["level_text"] == "searched and not found"
    assert any(line.startswith("A public API of astronaut vital signs: it does not exist.")
               for line in body["not_found"])
    texts = {cell["text"] for item in body["datasets"] for cell in item["ladder"]}
    assert texts <= {None, "no sample in this segment", *human_datasets.PHASE_STATUS_EN.values()}


def test_context_sources_in_english_say_what_was_not_read(client: TestClient) -> None:
    body = client.get("/api/context-sources", headers=ENGLISH_HEADERS).json()
    assert body["note"].startswith("The sources of the team's context")
    assert "was read on 2026-10-31" in body["note"]
    by_ref = {item["ref"]: item for item in body["sources"]}
    challenge = by_ref[context_sources.CHALLENGE_REF]
    assert (challenge["status"], challenge["status_text"]) == ("partial", "read in part")
    assert "has not been watched" in challenge["not_read"]
    assert "«Resources will be available on Friday, November 13.»" in challenge["not_read"]
    assert {item["status_text"] for item in body["sources"]} == {"read", "read in part"}
    # La mina de CLAUDE.md: astroquery no es un backend de salud.
    assert "It is not a health backend or a source of biomedical data" in (
        by_ref["astroquery-docs"]["emma_use"]
    )
    video = by_ref["nasa-iss-humanity-lab-video"]
    assert "it is in none of them" in video["not_read"]
    assert video["not_read"].endswith("EMMA does not repeat the sentence of the conversation.")


@pytest.mark.parametrize(
    ("spanish", "english"),
    [
        (testbeds.VALIDATIONS, testbeds.VALIDATIONS_EN),
        (testbeds.LEAVES_OUT_BASIS, testbeds.LEAVES_OUT_BASIS_EN),
        (testbeds.COLUMNS, testbeds.COLUMNS_EN),
        (testbeds.RIDGE_STATUS, testbeds.RIDGE_STATUS_EN),
        (testbeds.RIDGE_BASIS, testbeds.RIDGE_BASIS_EN),
        (facilities.STEPS, facilities.STEPS_EN),
        (facilities.STATUSES, facilities.STATUSES_EN),
        (human_datasets.PHASES, human_datasets.PHASES_EN),
        (human_datasets.PHASE_STATUS, human_datasets.PHASE_STATUS_EN),
        (human_datasets.ACCESS_LEVELS, human_datasets.ACCESS_LEVELS_EN),
        (human_datasets.ACCESS_BASIS, human_datasets.ACCESS_BASIS_EN),
        (human_datasets.EMMA_USE, human_datasets.EMMA_USE_EN),
        (human_datasets.ROLE_LEVELS, human_datasets.ROLE_LEVELS_EN),
        (human_datasets.FITNESS, human_datasets.FITNESS_EN),
        (human_datasets.CONTROL_KINDS, human_datasets.CONTROL_KINDS_EN),
        (human_datasets.CONTROL_STATUS, human_datasets.CONTROL_STATUS_EN),
        (context_sources.STATUSES, context_sources.STATUSES_EN),
        (osdr_data.VERDICTS, osdr_data.VERDICTS_EN),
        (osdr_data.STATUS, osdr_data.STATUS_EN),
        (ntrs.STATUS_DISPLAY, ntrs.STATUS_DISPLAY_EN),
    ],
)
def test_each_table_of_labels_has_its_english_key_by_key(
    spanish: dict[Any, str], english: dict[Any, str]
) -> None:
    assert list(english) == list(spanish)
    for text in english.values():
        assert text.strip() and not _SPANISH_ONLY.search(text) and not _FORBIDDEN.search(text)
    assert {testbeds.EMMA_NONE, testbeds.EMMA_PART} == set(testbeds.EMMA_STATUS_EN)


# --------------------------------------------------------------------------- #
# Personas y organizaciones
# --------------------------------------------------------------------------- #


def test_people_in_english_keep_names_and_roles_as_the_source_writes_them(
    client: TestClient,
) -> None:
    spanish = client.get("/api/people").json()
    english = client.get("/api/people", headers=ENGLISH_HEADERS).json()
    assert spanish == json.loads(json.dumps(people.payload()))
    assert english["note"].startswith("Derived from the evidence registry on each request")
    assert english["no_organization"] == "no organisation on the reference card"
    assert english["no_year"] == "no date on the reference card"
    for key in ("affiliation_rule", "same_person_rule", "named_organization_rule"):
        assert english[key] != spanish[key] and not _SPANISH_ONLY.search(english[key]), key
    assert "There are no contact details." in english["same_person_rule"]
    changed = {_last_key(path) for path in _differences(spanish, english)}
    # Solo cambian las frases de EMMA; nombres, cargos, organizaciones y fichas, no. El rótulo
    # del tipo de evidencia es del registro y cambia solo si el registro trae su inglés.
    assert changed <= {
        "note", "affiliation_rule", "same_person_rule", "named_organization_rule",
        "no_organization", "no_year", "role_text", "text", "affiliation_text",
        "evidence_type_display",
    }
    assert {"role_text", "text"} <= changed
    roles = [
        citation["role_text"] for person in english["people"] for citation in person["citations"]
    ]
    assert roles and all(not _SPANISH_ONLY.search(_own_words(role)) for role in roles)
    assert any(re.fullmatch(r"author \(no\. \d+ of \d+\)", role) for role in roles)
    assert any(role == "author (the only one on the card)" for role in roles)
    assert any("which it abbreviates with «et al.»" in role for role in roles)
    named = [role for role in roles if role.startswith("named by the source as «")]
    assert named and all(
        re.search(r"\(at the date of the source, \d{4}\)$", role)
        or role.endswith("(at a date the reference card does not give)")
        for role in named
    )
    # El cargo va entre «» tal como lo da la fuente.
    for person_es, person_en in zip(spanish["people"], english["people"], strict=True):
        for one, other in zip(person_es["citations"], person_en["citations"], strict=True):
            assert one["role"] == other["role"]
            if one["role"] == "named":
                assert _QUOTED.findall(one["role_text"]) == _QUOTED.findall(other["role_text"])


# --------------------------------------------------------------------------- #
# OSDR y NTRS
# --------------------------------------------------------------------------- #


def test_osdr_offline_says_unavailable_in_english_in_every_thread(client: TestClient) -> None:
    """`studies` reparte las fichas en un grupo de hilos: el idioma de la petición va con ellas."""
    spanish = client.get("/api/osdr/studies").json()
    english = client.get("/api/osdr/studies", headers=ENGLISH_HEADERS).json()
    assert english["note"].startswith("What EMMA says about each OSDR study")
    assert "not a measurement of any crew member" in english["note"]
    assert len(english["studies"]) > 3
    for one, other in zip(spanish["studies"], english["studies"], strict=True):
        assert (one["id"], one["status"]) == (other["id"], other["status"])
        assert other["status"] == "unavailable"
        assert other["status_display"] == (
            "OSDR not available: the reference card could not be checked"
        )
        assert other["reason"] == (
            f"the record of {other['accession']} in OSDR has not been read yet and the system "
            "is offline"
        )
        assert one["status_display"] == osdr_data.STATUS["unavailable"]
        assert "sin red" in one["reason"]


def _record(**changes: Any) -> osdr_data.StudyRecord:
    base = osdr_data.StudyRecord(
        accession="OSD-288", title="otro título", organisms=("Mus musculus",),
        mission={"name": "SpaceX-9", "start date": "7/18/16", "end date": "9/26/16"},
        measurement_types=(), technology_types=(), project_type=None, release_date=None,
        assay_count=1, sample_count=9, source_url="https://example.invalid/",
    )
    return dataclasses.replace(base, **changes)


def test_osdr_comparison_in_english_keeps_the_verdicts_and_the_scope() -> None:
    ref = registry.get("osd-288")
    spanish = osdr_data.compare(ref, _record())
    assert _record().scope.endswith("las muestras no son de astronautas ni de ninguna persona.")
    with i18n.use("en"):
        english = osdr_data.compare(ref, _record())
        assert _record().scope == (
            "Animal model (Mus musculus): the samples are not from astronauts or from any person."
        )
        assert _record(organisms=()).scope.startswith("Organism not classified in EMMA (no organ")
        notes = osdr_data.mission_notes(_record())
    assert [check["verdict"] for check in english] == [check["verdict"] for check in spanish]
    assert [check["field"] for check in english] == [check["field"] for check in spanish]
    assert [check["label"] for check in english] == [
        "title", "publication date", "population", "samples",
    ]
    assert {check["verdict_display"] for check in english} <= set(osdr_data.VERDICTS_EN.values())
    assert english[1]["note"] == "OSDR does not give it"
    assert english[3]["note"] == "distinct samples in the assays of the dataset, not subjects"
    # La nota revisada de la misión: las citas de la fuente, iguales; lo de EMMA, en inglés.
    original = osdr_data.MISSION_NOTES["OSD-288"]
    assert len(notes) == 1 and notes[0] | {"note": original["note"]} == original
    assert notes[0]["note"].startswith("It is not the return of the mice.")
    assert _QUOTED.findall(notes[0]["note"]) == _QUOTED.findall(original["note"])
    assert _numbers(notes[0]["note"]) == _numbers(original["note"])
    assert not _SPANISH_ONLY.search(_own_words(notes[0]["note"]))
    assert osdr_data.mission_notes(_record()) == [original]


def test_ntrs_offline_and_scope_in_english(client: TestClient) -> None:
    spanish = client.get("/api/dossier/ntrs").json()
    english = client.get("/api/dossier/ntrs", headers=ENGLISH_HEADERS).json()
    assert english["scope"].startswith("It compares what EMMA copied from each report")
    assert "«not found in NTRS» does not mean a made-up citation" in english["scope"]
    assert english["by_status"] == spanish["by_status"]
    assert english["count"] == spanish["count"] > 10
    for one, other in zip(spanish["references"], english["references"], strict=True):
        assert (one["ref_id"], one["status"]) == (other["ref_id"], other["status"])
        assert other["status_display"] == "not available"
        assert other["detail"] == "offline and no saved lookup: not available"
        assert one["detail"] == "sin red y sin consulta guardada: no disponible"


def test_ntrs_lookup_details_in_english(tmp_path: Path) -> None:
    settings = Settings(cache_dir=tmp_path, offline=True, assistant_warmup=False)
    client = ntrs.NtrsClient(settings, FileCache(tmp_path / "ntrs"))
    client.cache.put("ntrs:20130000839", {"found": False}, source="NTRS")
    with i18n.use("en"):
        missing = client.lookup("20200000567")
        gone = client.lookup("20130000839")
        assert gone.to_dict()["status_display"] == "not found in NTRS"
    assert missing.detail == "offline and no saved lookup: not available"
    assert gone.status == ntrs.NOT_IN_NTRS
    assert gone.detail.startswith("NTRS does not have that number (saved lookup ")
    # No se dice más que en castellano: que NTRS no la tenga no la hace inventada.
    assert gone.detail.endswith(
        "It does not prove that the citation is made up: NTRS withdraws or restricts records"
    )
    assert gone.to_dict()["status_display"] == "no encontrada en NTRS"
    assert client.lookup("20130000839").detail.startswith("NTRS no tiene ese número (consulta ")


def test_ntrs_comparison_in_english_keeps_states_and_both_sides() -> None:
    ref = dataclasses.replace(
        registry.get("ntrs-20170004345"), authors=("Hailey M", "Pérez J"), date=None,
        source="sin número de informe",
    )
    record = ntrs.NtrsRecord(
        ntrs_id="20170004345", title="Otro", authors=("Hailey, M.",), years=(),
        report_numbers=(), sti_type=None,
    )
    spanish = ntrs.compare(ref, record)
    with i18n.use("en"):
        english = ntrs.compare(ref, record)
        explained = ntrs.compare(
            registry.get("ntrs-20130000839"),
            ntrs.NtrsRecord(
                ntrs_id="20130000839", title="Nutritional Status Assessment (SMO -16E)",
                authors=("Smith, Scott M.", "Heer, M. A.", "Zwart, S. R."), years=(2012, 2013),
                report_numbers=(), sti_type="CONFERENCE_PAPER",
            ),
        )
    for name, field in english.items():
        # Los estados son identificadores: `coincide`, `difiere`, `no_comprobable`, `explicada`.
        assert field["state"] == spanish[name]["state"], name
        assert (field["emma"], field["ntrs"]) == (spanish[name]["emma"], spanish[name]["ntrs"])
    assert english["authors"]["detail"] == "not in NTRS: Pérez J"
    assert english["year"]["detail"] == "EMMA's reference card gives no date"
    assert english["report_number"]["detail"] == "EMMA's citation writes no report number"
    assert explained["title"]["state"] == ntrs.EXPLAINED == "explicada"
    assert explained["title"]["detail"] == (
        "NTRS writes it «SMO -16E»; the abstract (NTRS PDF, one page) says «NUTRITIONAL STATUS "
        "ASSESSMENT (SMO 016E)». NTRS typo."
    )


def test_every_reviewed_difference_has_its_english_with_the_same_quotes() -> None:
    whys = [
        field["why"]
        for fields in ntrs.EXPLAINED_DIFFERENCES.values()
        for field in fields.values()
    ]
    assert len(whys) == 8
    with i18n.use("en"):
        for why in whys:
            english = i18n.loc(why)
            assert english != why, why
            assert _QUOTED.findall(english) == _QUOTED.findall(why)
            assert _numbers(english) == _numbers(why)
            assert not _SPANISH_ONLY.search(_own_words(english))
            assert not _FORBIDDEN.search(_own_words(english))
