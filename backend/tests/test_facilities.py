"""EPM y Biolab, de la instalación a la aplicación: `GET /api/facilities`.

Lo que vigilan estas pruebas es que las dos cadenas de la base de conocimiento (§9) no digan más
de lo que se leyó: los nueve eslabones están siempre, en su orden; cada frase tiene su ficha, su
sitio en la fuente y la fecha de la lectura en la ficha; un eslabón sin frase dice qué falta y
dónde se buscó; el estado de cada eslabón sale de lo que tiene, no se escribe; y la cadena de
células de rata lleva su salvedad. **Ninguna prueba sale a la red**: la lectura se hizo el
2026-10-22.
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
from app.evidence import facilities, registry
from app.evidence.facilities import FacilitiesError
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
KB = ROOT / "docs" / "contexto" / "knowledge-base-v1.md"
STEPS = [
    "facility", "experiment", "equipment", "parameter", "investigator", "provider", "dataset",
    "publication", "application",
]


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
    return copy.deepcopy(json.loads(facilities.FACILITIES_PATH.read_text("utf-8")))


def _facility(raw: dict[str, Any], ident: str) -> dict[str, Any]:
    return next(item for item in raw["facilities"] if item["id"] == ident)


def _link(raw: dict[str, Any], ident: str, step: str) -> dict[str, Any]:
    return next(link for link in _facility(raw, ident)["links"] if link["step"] == step)


def _served(ident: str) -> dict[str, Any]:
    return next(item for item in facilities.payload()["facilities"] if item["id"] == ident)


def _served_link(ident: str, step: str) -> dict[str, Any]:
    return next(link for link in _served(ident)["links"] if link["step"] == step)


# --------------------------------------------------------------------------- #
# Lo leído
# --------------------------------------------------------------------------- #


def test_the_file_as_shipped_is_valid_and_has_the_two_facilities(raw: dict[str, Any]) -> None:
    assert facilities.validate(raw) is raw
    served = facilities.payload()["facilities"]
    assert [(item["id"], item["experiment"]) for item in served] == [
        ("epm", "Neurospat"), ("biolab", "TripleLux-A"),
    ]


def test_every_chain_has_the_nine_links_of_the_knowledge_base_in_order() -> None:
    assert list(facilities.STEPS) == STEPS
    for facility in facilities.payload()["facilities"]:
        assert [link["step"] for link in facility["links"]] == STEPS
        assert [link["label"] for link in facility["links"]] == list(facilities.STEPS.values())


def test_the_chain_and_the_roles_are_literal_text_of_the_knowledge_base() -> None:
    kb = KB.read_text("utf-8")
    served = facilities.payload()
    assert served["chain"]["text"] in kb
    for facility in served["facilities"]:
        assert facility["kb_role"]["text"] in kb, facility["id"]
        assert facility["kb_role"]["where"].endswith("§9")


def test_every_quote_comes_from_an_official_source_read_that_day() -> None:
    read_on = facilities.read()["read_on"]
    assert read_on == "2026-10-22"
    for facility in facilities.payload()["facilities"]:
        for link in facility["links"]:
            for item in link["quotes"]:
                ref = registry.get(item["ref"])
                assert (item["source"], item["url"]) == (ref.source, ref.url)
                assert item["url"].split("/")[2] in facilities.OFFICIAL_HOSTS
                assert item["quote"].strip() and item["where"].strip()
                assert read_on in (ref.notes or ""), ref.id
                # Lo que la ficha no tiene verificado se sirve como tal, no se calla.
                assert item["unverified_display"] == [
                    registry.OPTIONAL_FIELDS[name] for name in ref.unverified
                ]


def test_a_page_that_shows_no_date_keeps_it_unverified() -> None:
    for ref_id in ("esa-epm", "esa-biolab", "nasa-iss-research-explorer"):
        assert registry.get(ref_id).unverified == ("date",), ref_id
    assert registry.get("esa-iss-status-report-84").date == "2010-12-31"
    assert registry.get("esa-image-2015-triplelux").date == "2015-10-06"


def test_the_two_articles_carry_their_population_and_environment() -> None:
    thiel = registry.get("thiel-2017-macrophage-microgravity")
    petit = registry.get("petit-2019-local-sleep-iss")
    assert (str(thiel.evidence_context), thiel.population) == ("iss", "animal")
    assert (str(petit.evidence_context), petit.population) == ("iss", "human")
    assert thiel.notes is not None and "NR8383 rat alveolar macrophages" in thiel.notes
    assert (thiel.pmid, petit.pmid) == ("28242876", "31069253")


# --------------------------------------------------------------------------- #
# Lo no encontrado: dicho, con dónde se buscó, nunca rellenado
# --------------------------------------------------------------------------- #


def test_the_status_of_each_link_comes_from_what_it_has() -> None:
    for facility in facilities.payload()["facilities"]:
        for link in facility["links"]:
            expected = (
                "not_found" if not link["quotes"]
                else "partial" if link["missing"] is not None
                else "read"
            )
            assert link["status"] == expected
            assert link["status_text"] == facilities.STATUSES[expected]
            if link["missing"] is not None:
                assert link["missing"]["what"].strip() and link["missing"]["searched"]
        assert facility["unsourced"] == [
            link["label"] for link in facility["links"] if link["status"] == "not_found"
        ]


def test_no_dataset_of_either_experiment_is_public_and_that_is_said() -> None:
    # TripleLux-A: ningún conjunto de datos encontrado; el eslabón está, vacío y dicho.
    triplelux = _served_link("biolab", "dataset")
    assert triplelux["quotes"] == [] and triplelux["status"] == "not_found"
    assert any("OSDR" in line for line in triplelux["missing"]["searched"])
    assert _served("biolab")["unsourced"] == ["conjunto de datos"]
    # Neurospat: la frase de la declaración de datos (a petición), y el hueco del público.
    neurospat = _served_link("epm", "dataset")
    assert neurospat["status"] == "partial"
    assert any("upon request" in item["quote"] for item in neurospat["quotes"])


def test_the_provider_of_the_experiment_equipment_was_not_found() -> None:
    for ident, developer in (("epm", "OHM Systems"), ("biolab", "EADS Astrium")):
        provider = _served_link(ident, "provider")
        assert provider["status"] == "partial"
        # Lo que hay es el desarrollador de la instalación, copiado tal cual del catálogo.
        assert provider["quotes"][0]["quote"].startswith(developer)
        assert any("Developer(s)" in line for line in provider["missing"]["searched"])


def test_the_crew_time_lesson_is_not_on_the_esa_page_and_that_is_said() -> None:
    facility = _served_link("biolab", "facility")
    assert facility["status"] == "partial"
    assert "tiempo de tripulación" in facility["missing"]["what"]
    assert any("crew time" in line for line in facilities.read()["not_found"])


def test_the_rat_cell_chain_carries_its_scope_caveat() -> None:
    biolab = _served("biolab")
    populations = {
        item["population"] for link in biolab["links"] for item in link["quotes"]
    }
    assert "animal" in populations
    assert biolab["scope_caveat"] is not None and "no personas" in biolab["scope_caveat"]
    # La cadena de EPM es de personas: no lleva salvedad que no le toca.
    assert _served("epm")["scope_caveat"] is None


# --------------------------------------------------------------------------- #
# La defensa: lo que no se sostiene no se sirve
# --------------------------------------------------------------------------- #


def _drop_ref(raw: dict[str, Any]) -> None:
    del _link(raw, "epm", "facility")["quotes"][0]["ref"]


def _unregistered(raw: dict[str, Any]) -> None:
    _link(raw, "epm", "facility")["quotes"][0]["ref"] = "esa-epm-inventada"


def _unofficial(raw: dict[str, Any]) -> None:
    # MMASH es una ficha real, pero no es ESA, NASA ni PubMed Central.
    _link(raw, "epm", "facility")["quotes"][0]["ref"] = "mmash"


def _not_read_that_day(raw: dict[str, Any]) -> None:
    # Una ficha oficial de nasa.gov leída otro día: sin rastro de esta lectura.
    _link(raw, "epm", "facility")["quotes"][0]["ref"] = "nasa-hrp-step2-station"


def _dropped_link(raw: dict[str, Any]) -> None:
    links = _facility(raw, "biolab")["links"]
    links.remove(_link(raw, "biolab", "dataset"))


def _reordered(raw: dict[str, Any]) -> None:
    links = _facility(raw, "epm")["links"]
    links[0], links[1] = links[1], links[0]


def _silent_gap(raw: dict[str, Any]) -> None:
    _link(raw, "biolab", "dataset")["missing"] = None


def _gap_without_where(raw: dict[str, Any]) -> None:
    _link(raw, "biolab", "dataset")["missing"]["searched"] = []


def _gap_without_what(raw: dict[str, Any]) -> None:
    _link(raw, "biolab", "dataset")["missing"]["what"] = " "


def _no_caveat(raw: dict[str, Any]) -> None:
    _facility(raw, "biolab")["scope_caveat"] = None


def _empty_where(raw: dict[str, Any]) -> None:
    _link(raw, "epm", "investigator")["quotes"][0]["where"] = ""


def _extra_field(raw: dict[str, Any]) -> None:
    _link(raw, "epm", "investigator")["quotes"][0]["page"] = "1"


def _repeated_quote(raw: dict[str, Any]) -> None:
    link = _link(raw, "epm", "investigator")
    link["quotes"].append(copy.deepcopy(link["quotes"][0]))


def _duplicate(raw: dict[str, Any]) -> None:
    raw["facilities"].append(copy.deepcopy(_facility(raw, "epm")))


def _no_read_on(raw: dict[str, Any]) -> None:
    raw["read_on"] = ""


def _no_quote_text(raw: dict[str, Any]) -> None:
    _link(raw, "epm", "investigator")["quotes"][0]["quote"] = " "


def _quote_not_an_object(raw: dict[str, Any]) -> None:
    _link(raw, "epm", "investigator")["quotes"][0] = "Guy Cheron"


def _facility_not_an_object(raw: dict[str, Any]) -> None:
    raw["facilities"].append("epm")


def _empty_role(raw: dict[str, Any]) -> None:
    _facility(raw, "epm")["kb_role"]["text"] = ""


def _empty_chain(raw: dict[str, Any]) -> None:
    raw["chain"]["where"] = ""


def _blank_not_found(raw: dict[str, Any]) -> None:
    raw["not_found"].append(" ")


def _repeated_not_found(raw: dict[str, Any]) -> None:
    raw["not_found"].append(raw["not_found"][0])


def _repeated_searched(raw: dict[str, Any]) -> None:
    searched = _link(raw, "biolab", "dataset")["missing"]["searched"]
    searched.append(searched[0])


def _gap_extra_field(raw: dict[str, Any]) -> None:
    _link(raw, "biolab", "dataset")["missing"]["obvious"] = True


def _blank_caveat(raw: dict[str, Any]) -> None:
    _facility(raw, "epm")["scope_caveat"] = " "


@pytest.mark.parametrize(
    ("damage", "message"),
    [
        (_drop_ref, "faltan campos"),
        (_unregistered, "esa-epm-inventada: no está en el registro"),
        (_unofficial, "no es ESA, NASA ni PubMed Central"),
        (_not_read_that_day, "sin rastro de la lectura"),
        (_dropped_link, "en su orden"),
        (_reordered, "en su orden"),
        (_silent_gap, "qué falta y dónde se buscó"),
        (_gap_without_where, "dónde se buscó"),
        (_gap_without_what, "qué falta"),
        (_no_caveat, "sin su salvedad"),
        (_empty_where, "falta `where`"),
        (_extra_field, "campos desconocidos"),
        (_repeated_quote, "frase repetida"),
        (_duplicate, "instalación repetida"),
        (_no_read_on, "falta `read_on`"),
        (_no_quote_text, "falta `quote`"),
        (_quote_not_an_object, "se esperaba un objeto"),
        (_facility_not_an_object, "se esperaba un objeto"),
        (_empty_role, "`kb_role` sin su texto"),
        (_empty_chain, "`chain` sin su texto"),
        (_blank_not_found, "sin líneas vacías"),
        (_repeated_not_found, "línea repetida en `not_found`"),
        (_repeated_searched, "línea repetida en lo buscado"),
        (_gap_extra_field, "campos desconocidos en el hueco"),
        (_blank_caveat, "`scope_caveat` vacía"),
    ],
)
def test_what_cannot_be_held_with_the_source_in_hand_is_not_served(
    raw: dict[str, Any], damage: Callable[[dict[str, Any]], None], message: str
) -> None:
    damage(raw)
    with pytest.raises(FacilitiesError, match=message):
        facilities.validate(raw)


# --------------------------------------------------------------------------- #
# La ruta
# --------------------------------------------------------------------------- #


def test_the_route_serves_the_payload_without_touching_the_store(client: TestClient) -> None:
    response = client.get("/api/facilities")
    assert response.status_code == 200
    body = response.json()
    assert body == facilities.payload()
    assert "Inventario" in body["note"] and "ninguna alerta" in body["note"]
