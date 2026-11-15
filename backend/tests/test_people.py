"""Personas y organizaciones de las fuentes: `GET /api/people`.

Lo que vigilan estas pruebas es que la ruta no diga nada que el registro de evidencia no diga ni
deje fuera nada de lo que dice: cada ficha bajo cada organización que da, y en ninguna otra; cada
persona con las fichas que la escriben y su papel en ellas; derivado en cada consulta, sin lista
escrita aparte. Y que el registro no admita una persona que la ficha no escriba letra a letra, ni
un dato de contacto. Son personas reales. **Ninguna prueba sale a la red.**
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.evidence import people, registry
from app.main import app
from app.text_guard import check

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "contexto" / "personas-y-organizaciones.md"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _raw() -> dict[str, Any]:
    return json.loads(registry.REGISTRY_PATH.read_text(encoding="utf-8"))


def _orgs(raw_ref: dict[str, Any]) -> list[str]:
    """Las organizaciones de una ficha, leídas del JSON sin pasar por `people`."""
    value = raw_ref["organization"]
    return [] if value is None else [part.strip() for part in value.split(" / ")]


# --------------------------------------------------------------------------- #
# La ruta y el registro no divergen
# --------------------------------------------------------------------------- #


def test_every_card_is_under_each_of_its_organizations_and_under_no_other() -> None:
    raw = _raw()
    expected: dict[str, set[str]] = {}
    without: set[str] = set()
    for ref in raw["references"]:
        orgs = _orgs(ref)
        if not orgs:
            without.add(ref["id"])
        for org in orgs:
            expected.setdefault(org, set()).add(ref["id"])
    served = people.payload()
    # Las que dan una ficha; las que solo una ficha nombra (U4) van en la misma lista, sin fichas.
    by_org = {
        org["name"]: {r["id"] for r in org["references"]}
        for org in served["organizations"] if org["references"]
    }
    assert by_org == expected
    assert {r["id"] for r in served["without_organization"]} == without
    assert served["references"] == len(raw["references"])
    # Cada ficha sale una vez por organización: ni repetida ni perdida.
    for org in served["organizations"]:
        ids = [r["id"] for r in org["references"]]
        assert len(ids) == len(set(ids)), org["name"]
        assert org["references"] or org["named_by"], org["name"]


def test_an_organization_a_source_names_is_listed_with_the_role_the_source_gives() -> None:
    # Decimonovena ronda (U4): Teledyne Brown, CASIS y Boeing por el documento de NASA que los
    # nombra; la NSF y el USAP por la página de las estaciones antárticas; el DLR por la ficha de
    # :envihab; el laboratorio de la Armada por la nota del Kraken. Ninguna da una ficha.
    expected: dict[str, set[tuple[str, str]]] = {}
    for ref in _raw()["references"]:
        for org in ref.get("named_organizations", []):
            expected.setdefault(org["name"], set()).add((ref["id"], org["role"]))
    served = {
        org["name"]: {(item["ref"], item["role"]) for item in org["named_by"]}
        for org in people.payload()["organizations"] if org["named_by"]
    }
    assert served == expected
    assert {
        "Teledyne Brown Engineering Inc.", "Center for the Advancement of Science in Space (CASIS)",
        "The Boeing Co.", "National Science Foundation (NSF)",
    } <= set(served)
    organizations = {org["name"]: org for org in people.payload()["organizations"]}
    casis = organizations["Center for the Advancement of Science in Space (CASIS)"]
    assert casis["references"] == []
    (named,) = casis["named_by"]
    assert named["ref"] == "nasa-iss-national-lab-casis-2022" and named["year"] == "2022"
    assert named["role_text"] == (
        "la fuente la nombra como «help manage the U.S. segment of the International Space "
        "Station» (en la fecha de la fuente, 2022)"
    )
    # La organización de la ficha que la nombra es NASA, no CASIS: la ficha sigue bajo NASA.
    assert named["organization"] == "NASA"
    nasa_cards = {r["id"] for r in organizations["NASA"]["references"]}
    assert "nasa-iss-national-lab-casis-2022" in nasa_cards
    # La regla se sirve con la lista.
    assert "no es la organización de esa ficha" in people.payload()["named_organization_rule"]
    # Y en cada ficha servida, las organizaciones que nombra con su papel compuesto.
    card = next(
        r for r in organizations["NASA"]["references"] if r["id"] == "nasa-mossi-ii-teledyne-2022"
    )
    assert card["named_organizations"] == [{
        "name": "Teledyne Brown Engineering Inc.",
        "role": "International Space Station payload operations and ground systems",
        "role_text": (
            "la fuente la nombra como «International Space Station payload operations and ground "
            "systems» (en la fecha de la fuente, 2022)"
        ),
    }]


def test_an_affiliation_is_the_one_the_document_writes_by_the_person_or_nothing() -> None:
    # Krihak et al. 2020: la conversación de ideación daba una afiliación por autor de memoria; la
    # portada del PDF las da, y la de Schmitt no es la que decía (KBR Inc, no Wyle).
    krihak = {c["ref"]: c for c in _person("Krihak M")["citations"]}
    assert krihak["ntrs-20200000567"]["affiliation"] == (
        "Universities Space Research Association, Mountain View, CA"
    )
    assert krihak["ntrs-20200000567"]["affiliation_text"] == (
        "el documento la sitúa en «Universities Space Research Association, Mountain View, CA» "
        "(en la fecha de la fuente, 2020)"
    )
    assert _person("Schmitt B")["citations"][0]["affiliation"] == "KBR Inc, Mountain View, CA"
    # La misma persona en otra ficha sin afiliación escrita: nada, no la de la ficha.
    assert krihak["ntrs-20205008731"]["affiliation"] is None
    assert krihak["ntrs-20205008731"]["affiliation_text"] is None
    # Bell ST firma el artículo de 2025 sin afiliación escrita en la ficha: sigue sin ella.
    bell = next(
        c for c in _person("Bell ST")["citations"]
        if c["ref"] == "douglas-2025-iss-food-acceptability"
    )
    assert bell["affiliation"] is None and bell["organization"] == "NASA Johnson Space Center"
    # La ficha servida bajo su organización lleva la lista entera.
    card = next(
        r for org in people.payload()["organizations"] for r in org["references"]
        if r["id"] == "ntrs-20200001311"
    )
    assert [(a["name"], a["organization"]) for a in card["affiliations"]] == [
        ("Douglas GL", "NASA Johnson Space Center"), ("Roma PG", "Wyle Laboratories, Inc."),
        ("Young M", "NASA Johnson Space Center"),
    ]
    assert all(a["text"].startswith("el documento la sitúa en «") for a in card["affiliations"])


def test_grace_douglas_is_served_with_the_roles_the_sources_give_her() -> None:
    # La investigación 7562 (U4): el artículo de 2021 la nombra con su cargo de entonces; la
    # página de CHAPEA, como investigadora principal (sin afiliación). Ni se juntan con «Douglas
    # GL», que firma los artículos, ni se le pone cargo de hoy.
    roles = {c["ref"]: c["role_text"] for c in _person("Grace Douglas")["citations"]}
    assert roles == {
        "nasa-food-appeal-2021": (
            "la fuente la nombra como «lead scientist for the Advanced Food Technology project at "
            "NASA’s Johnson Space Center in Houston» (en la fecha de la fuente, 2021)"
        ),
        "nasa-chapea-program": (
            "la fuente la nombra como «principal investigator» (en una fecha que la ficha no da)"
        ),
    }
    assert "nasa-food-appeal-2021" not in {c["ref"] for c in _person("Douglas GL")["citations"]}
    assert "ntrs-20200001311" in {c["ref"] for c in _person("Douglas GL")["citations"]}


def test_a_card_with_two_organizations_is_under_both() -> None:
    served = {org["name"]: org for org in people.payload()["organizations"]}
    assert "scully-2019" in {r["id"] for r in served["KBRwyle"]["references"]}
    assert "scully-2019" in {r["id"] for r in served["NASA Johnson Space Center"]["references"]}
    # La ficha conserva su organización entera, tal como la escribe.
    card = next(r for r in served["KBRwyle"]["references"] if r["id"] == "scully-2019")
    assert card["organization"] == "KBRwyle / NASA Johnson Space Center"


def test_every_person_of_the_registry_is_served_with_its_cards_and_nobody_else() -> None:
    expected: set[tuple[str, str, str]] = set()
    for ref in _raw()["references"]:
        for name in ref.get("authors", []):
            expected.add((name, ref["id"], "author"))
        for person in ref.get("named_people", []):
            expected.add((person["name"], ref["id"], "named"))
    served = {
        (person["name"], citation["ref"], citation["role"])
        for person in people.payload()["people"]
        for citation in person["citations"]
    }
    assert served == expected
    assert len(expected) > 0


def test_each_card_carries_its_authors_in_the_order_of_the_citation() -> None:
    raw = {ref["id"]: ref for ref in _raw()["references"]}
    for org in people.payload()["organizations"]:
        for card in org["references"]:
            assert card["authors"] == raw[card["id"]].get("authors", [])
            named = [{"name": p["name"], "role": p["role"]} for p in card["named_people"]]
            assert named == raw[card["id"]].get("named_people", [])
            for person in card["named_people"]:
                assert f"«{person['role']}»" in person["role_text"]
            date = raw[card["id"]]["date"]
            assert card["year"] == (date[:4] if date is not None else None)


def test_the_route_is_derived_from_the_registry_on_each_request(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = _raw()
    extra = copy.deepcopy(next(r for r in raw["references"] if r["id"] == "basner-2011-pvt-b"))
    extra["id"] = "ficha-de-prueba"
    extra["organization"] = "Organización de prueba"
    extra["source"] = "Prueba AB, Basner M. Revista de prueba 2011"
    extra["authors"] = ["Prueba AB", "Basner M"]
    raw["references"].append(extra)
    patched = registry.parse(raw)
    monkeypatch.setattr(registry, "registry", lambda: patched)
    body = client.get("/api/people").json()
    names = {org["name"] for org in body["organizations"]}
    assert "Organización de prueba" in names
    by_name = {person["name"]: person for person in body["people"]}
    assert [c["ref"] for c in by_name["Prueba AB"]["citations"]] == ["ficha-de-prueba"]
    assert "ficha-de-prueba" in [c["ref"] for c in by_name["Basner M"]["citations"]]
    monkeypatch.undo()
    body = client.get("/api/people").json()
    assert "Organización de prueba" not in {org["name"] for org in body["organizations"]}
    assert "Prueba AB" not in {person["name"] for person in body["people"]}


def test_a_card_without_organization_is_listed_apart_and_under_no_organization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Las fichas reales que ya no tienen organización (filiación sin leer) siguen apartadas.
    before = {r["id"] for r in people.payload()["without_organization"]}
    assert "nasa-tlx-1986" not in before
    raw = _raw()
    card = next(r for r in raw["references"] if r["id"] == "nasa-tlx-1986")
    card["organization"] = None
    patched = registry.parse(raw)
    monkeypatch.setattr(registry, "registry", lambda: patched)
    served = people.payload()
    assert {r["id"] for r in served["without_organization"]} == before | {"nasa-tlx-1986"}
    for org in served["organizations"]:
        assert "nasa-tlx-1986" not in {r["id"] for r in org["references"]}
    # Quien la firma sigue saliendo, con la ficha sin organización.
    (hart,) = next(p for p in served["people"] if p["name"] == "Hart SG")["citations"]
    assert hart["organization"] is None


def test_an_et_al_outside_the_list_of_authors_does_not_cut_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = _raw()
    card = next(r for r in raw["references"] if r["id"] == "basner-2011-pvt-b")
    card["source"] = "Basner M, Mollicone D, Dinges DF. Acta Astronaut. 2011; ver Otro X et al."
    # Y una firma copiada de la nota, con una cita que abrevia a otros: no es la lista de la cita.
    orion = next(r for r in raw["references"] if r["id"] == "nasa-orion-radiation-protection")
    orion["source"] = "NASA (22 de septiembre de 2016), sobre Otro X et al."
    # Una lista que mezcla la cita y la nota tampoco es la de la cita, aunque la cita abrevie.
    mixed = next(r for r in raw["references"] if r["id"] == "basner-2011-pvt-metrics")
    mixed["source"] = "Basner M et al. Sleep. 2011"
    mixed["notes"] += " Ploutz-Snyder R."
    mixed["authors"] = ["Basner M", "Ploutz-Snyder R"]
    patched = registry.parse(raw)
    monkeypatch.setattr(registry, "registry", lambda: patched)
    served = {r["id"]: r for org in people.payload()["organizations"] for r in org["references"]}
    assert served["basner-2011-pvt-b"]["et_al"] is False
    assert served["nasa-orion-radiation-protection"]["et_al"] is False
    assert served["basner-2011-pvt-metrics"]["et_al"] is False
    assert served["thiel-2017-macrophage-microgravity"]["et_al"] is True


def test_a_name_with_an_accent_sorts_with_its_letter() -> None:
    key = people._sort_key
    assert key("Ébert X") < key("Fraser KS") < key("Zwart SR")


def test_the_route_serves_offline_and_reads_no_crew_state(client: TestClient) -> None:
    response = client.get("/api/people")
    assert response.status_code == 200
    assert response.json() == json.loads(json.dumps(people.payload()))
    for word in ('"subject"', '"level"', '"alerts"', '"risk_score"'):
        assert word not in response.text


# --------------------------------------------------------------------------- #
# El papel de cada persona, como lo da la ficha
# --------------------------------------------------------------------------- #


def _person(name: str) -> dict[str, Any]:
    return next(person for person in people.payload()["people"] if person["name"] == name)


def test_an_author_says_their_place_in_the_citation() -> None:
    assert [c["role_text"] for c in _person("Mollicone D")["citations"]] == ["firma (2.ª de 3)"]
    hart = [c["role_text"] for c in _person("Hart SG")["citations"]]
    assert hart == ["firma (única firma en la ficha)"]


def test_a_citation_cut_with_et_al_does_not_claim_a_total() -> None:
    (ullrich,) = _person("Ullrich O")["citations"]
    assert "et al." in ullrich["role_text"] and " de 4" not in ullrich["role_text"]
    (kerstman,) = _person("Kerstman")["citations"]
    assert "et al." in kerstman["role_text"] and "única" not in kerstman["role_text"]


def test_a_byline_copied_from_the_note_is_served_as_the_card_s() -> None:
    # La firma del artículo de Orion está en la nota, no en la cita: el registro la admite ahí.
    roles = {c["ref"]: c["role_text"] for c in _person("Mark A. Garcia")["citations"]}
    assert roles["nasa-orion-radiation-protection"] == "firma (única firma en la ficha)"
    assert set(roles) == {
        "nasa-orion-radiation-protection", "nasa-iss-blog-2026-07-08", "nasa-iss-blog-2026-09-28",
    }


def test_a_named_person_keeps_the_role_of_the_source_and_its_year() -> None:
    (lee,) = _person("Kerry Lee")["citations"]
    assert lee["role"] == "named"
    assert "«radiation system manager for Orion»" in lee["role_text"]
    assert "2016" in lee["role_text"] and lee["year"] == "2016"
    (vos,) = _person("Jessica Vos")["citations"]
    assert "«deputy health and medical technical authority for Orion»" in vos["role_text"]


def test_a_named_person_without_a_date_says_so() -> None:
    ref = registry.get("nasa-orion-radiation-protection")
    undated = registry.parse({"references": [{**_raw_card(ref.id), "date": None}]})[ref.id]
    text = people._named_role(undated, "radiation system manager for Orion")
    assert "no da" in text and "None" not in text


def test_the_same_spelling_is_one_person_and_another_spelling_is_another() -> None:
    assert {c["ref"] for c in _person("Basner M")["citations"]} == {
        "basner-2011-pvt-b", "basner-2011-pvt-metrics", "basner-2015-cognition-battery",
        "tu-2022-pvt-prediction-iss",
    }
    # «Dinges DF» firma; «Dinges, David» es como lo escribe la tarea del Roadmap. No se juntan.
    assert _person("Dinges DF")["citations"] != _person("Dinges, David")["citations"]


def test_the_organization_of_a_person_is_the_card_s_and_said_as_such() -> None:
    # Bell ST firma un artículo cuya organización es la de la primera autora: no se le atribuye.
    # Desde la decimoséptima ronda (U10) firma también el resumen de Sirius-21, de la misma autora.
    citations = {c["ref"]: c for c in _person("Bell ST")["citations"]}
    assert set(citations) == {"douglas-2025-iss-food-acceptability", "ntrs-20220014371"}
    bell = citations["douglas-2025-iss-food-acceptability"]
    assert bell["organization"] == "NASA Johnson Space Center"
    payload = people.payload()
    assert "no es la afiliación de cada firmante" in payload["affiliation_rule"]


def test_the_texts_pass_the_language_filter() -> None:
    payload = people.payload()
    texts = [payload["note"], payload["affiliation_rule"], payload["same_person_rule"],
             payload["no_organization"], payload["no_year"]]
    texts += [c["role_text"] for person in payload["people"] for c in person["citations"]]
    for text in texts:
        assert check(text) == [], text


def test_nothing_served_looks_like_contact_data() -> None:
    payload = people.payload()
    for person in payload["people"]:
        assert not re.search(r"@|\d", person["name"]), person["name"]
    assert "mailto:" not in json.dumps(payload)


# --------------------------------------------------------------------------- #
# El registro no admite una persona que la ficha no escriba
# --------------------------------------------------------------------------- #


def _raw_card(ref_id: str) -> dict[str, Any]:
    return copy.deepcopy(next(r for r in _raw()["references"] if r["id"] == ref_id))


def _author_not_written(card: dict[str, Any]) -> None:
    card["authors"].append("Inventado X")


def _author_with_digits(card: dict[str, Any]) -> None:
    card["source"] += " · Basner 555 123 456"
    card["authors"].append("Basner 555 123 456")


def _author_email(card: dict[str, Any]) -> None:
    card["notes"] += " basner@example.org"
    card["authors"].append("basner@example.org")


def _author_repeated(card: dict[str, Any]) -> None:
    card["authors"].append(card["authors"][0])


def _authors_empty(card: dict[str, Any]) -> None:
    card["authors"] = []


def _authors_not_a_list(card: dict[str, Any]) -> None:
    card["authors"] = "Basner M"


def _author_not_a_string(card: dict[str, Any]) -> None:
    card["authors"].append(7)


def _named_role_not_written(card: dict[str, Any]) -> None:
    card["notes"] += " La nombra: Kerry Lee."
    card["named_people"] = [{"name": "Kerry Lee", "role": "director de hoy"}]


def _named_name_not_written(card: dict[str, Any]) -> None:
    card["notes"] += " Dice «chief scientist»."
    card["named_people"] = [{"name": "Nadie Z", "role": "chief scientist"}]


def _named_role_of_someone_else(card: dict[str, Any]) -> None:
    # Los dos están en la nota, pero el cargo es de otra persona.
    card["notes"] += " La nombra a Kerry Lee. Y a Jessica Vos, radiation lead."
    card["named_people"] = [{"name": "Kerry Lee", "role": "radiation lead"}]


def _author_inside_another_name(card: dict[str, Any]) -> None:
    # «Dinges D» está dentro de «Dinges DF», pero no es lo que escribe la cita.
    card["authors"] = ["Dinges D"]


def _author_inside_a_word(card: dict[str, Any]) -> None:
    card["authors"] = ["Basn"]


def _two_authors_in_one(card: dict[str, Any]) -> None:
    card["authors"] = ["Basner M, Mollicone D"]


def _named_contact(card: dict[str, Any]) -> None:
    card["notes"] += " Kerry Lee, kerry.lee@nasa.gov"
    card["named_people"] = [{"name": "Kerry Lee", "role": "kerry.lee@nasa.gov"}]


def _named_phone(card: dict[str, Any]) -> None:
    card["notes"] += " Kerry Lee, phone 281 483 0123"
    card["named_people"] = [{"name": "Kerry Lee", "role": "phone 281 483 0123"}]


def _named_name_email(card: dict[str, Any]) -> None:
    card["notes"] += " kerry.lee@nasa.gov, radiation lead"
    card["named_people"] = [{"name": "kerry.lee@nasa.gov", "role": "radiation lead"}]


def _named_extra_field(card: dict[str, Any]) -> None:
    card["notes"] += " Kerry Lee, radiation lead"
    card["named_people"] = [{"name": "Kerry Lee", "role": "radiation lead", "email": "x"}]


def _named_also_author(card: dict[str, Any]) -> None:
    card["notes"] += " Basner M, radiation lead"
    card["named_people"] = [{"name": "Basner M", "role": "radiation lead"}]


def _named_repeated(card: dict[str, Any]) -> None:
    card["notes"] += " Kerry Lee, radiation lead"
    card["named_people"] = [{"name": "Kerry Lee", "role": "radiation lead"}] * 2


def _named_empty(card: dict[str, Any]) -> None:
    card["named_people"] = []


def _affiliation_of_nobody(card: dict[str, Any]) -> None:
    card["notes"] += " Nadie Z, University of Nowhere."
    card["affiliations"] = [{"name": "Nadie Z", "organization": "University of Nowhere"}]


def _affiliation_not_written_together(card: dict[str, Any]) -> None:
    # Los dos están en la nota, pero no juntos: sería atribuirle la de otro.
    card["notes"] += " Firma Basner M. La afiliación de Dinges DF es University of Nowhere."
    card["affiliations"] = [{"name": "Basner M", "organization": "University of Nowhere"}]


def _affiliation_contact(card: dict[str, Any]) -> None:
    card["notes"] += " Basner M, basner@nowhere.edu."
    card["affiliations"] = [{"name": "Basner M", "organization": "basner@nowhere.edu"}]


def _affiliation_repeated(card: dict[str, Any]) -> None:
    card["notes"] += " Basner M, University of Nowhere."
    card["affiliations"] = [{"name": "Basner M", "organization": "University of Nowhere"}] * 2


def _affiliation_extra_field(card: dict[str, Any]) -> None:
    card["notes"] += " Basner M, University of Nowhere."
    card["affiliations"] = [{"name": "Basner M", "organization": "University of Nowhere", "x": 1}]


def _affiliations_empty(card: dict[str, Any]) -> None:
    card["affiliations"] = []


def _organization_not_written_together(card: dict[str, Any]) -> None:
    card["notes"] += " Nombra a Acme Corp. Y dice «payload operations» de otra."
    card["named_organizations"] = [{"name": "Acme Corp", "role": "payload operations"}]


def _organization_contact(card: dict[str, Any]) -> None:
    card["notes"] += " Acme Corp, www.acme.example."
    card["named_organizations"] = [{"name": "Acme Corp", "role": "www.acme.example"}]


def _organization_name_contact(card: dict[str, Any]) -> None:
    card["notes"] += " acme@example.org, payload operations."
    card["named_organizations"] = [{"name": "acme@example.org", "role": "payload operations"}]


def _organization_name_not_a_name(card: dict[str, Any]) -> None:
    card["notes"] += " <Acme> Corp, payload operations."
    card["named_organizations"] = [{"name": "<Acme> Corp", "role": "payload operations"}]


def _organization_name_website(card: dict[str, Any]) -> None:
    card["notes"] += " www.acme.org, payload operations."
    card["named_organizations"] = [{"name": "www.acme.org", "role": "payload operations"}]


def _organization_name_phone(card: dict[str, Any]) -> None:
    card["notes"] += " 600 000 000, payload operations."
    card["named_organizations"] = [{"name": "600 000 000", "role": "payload operations"}]


def _organization_is_the_card_s(card: dict[str, Any]) -> None:
    card["notes"] += " University of Pennsylvania School of Medicine, payload operations."
    card["named_organizations"] = [
        {"name": "University of Pennsylvania School of Medicine", "role": "payload operations"}
    ]


def _organization_repeated(card: dict[str, Any]) -> None:
    card["notes"] += " Acme Corp, payload operations."
    card["named_organizations"] = [{"name": "Acme Corp", "role": "payload operations"}] * 2


def _organization_extra_field(card: dict[str, Any]) -> None:
    card["notes"] += " Acme Corp, payload operations."
    card["named_organizations"] = [{"name": "Acme Corp", "role": "payload operations", "x": 1}]


def _organizations_empty(card: dict[str, Any]) -> None:
    card["named_organizations"] = []


@pytest.mark.parametrize(
    ("spoil", "reason"),
    [
        (_affiliation_of_nobody, "no firma la ficha ni la fuente la nombra"),
        (_affiliation_not_written_together, "escritos juntos en la nota"),
        (_affiliation_contact, "datos de contacto"),
        (_affiliation_repeated, "repetida"),
        (_affiliation_extra_field, "sin más campos"),
        (_affiliations_empty, "al menos una persona"),
        (_organization_not_written_together, "escritos juntos en la nota"),
        (_organization_contact, "datos de contacto"),
        (_organization_name_contact, "no es el nombre de una organización"),
        (_organization_name_not_a_name, "no es el nombre de una organización"),
        (_organization_name_website, "no es el nombre de una organización"),
        (_organization_name_phone, "no es el nombre de una organización"),
        (_organization_is_the_card_s, "es ya la organización de la ficha"),
        (_organization_repeated, "repetida"),
        (_organization_extra_field, "sin más campos"),
        (_organizations_empty, "al menos una"),
    ],
)
def test_the_registry_rejects_an_affiliation_or_an_organization_the_card_does_not_write(
    spoil: Callable[[dict[str, Any]], None], reason: str
) -> None:
    card = _raw_card("basner-2011-pvt-b")
    registry.parse({"references": [copy.deepcopy(card)]})
    spoil(card)
    with pytest.raises(registry.RegistryError, match=reason):
        registry.parse({"references": [card]})


def test_an_affiliation_and_a_named_organization_well_written_load() -> None:
    card = _raw_card("basner-2011-pvt-b")
    card["notes"] += (
        " La portada da la afiliación: Basner M, University of Nowhere. Y nombra a quien operaba el"
        " laboratorio: Acme Corp, operates the laboratory."
    )
    card["affiliations"] = [{"name": "Basner M", "organization": "University of Nowhere"}]
    card["named_organizations"] = [{"name": "Acme Corp", "role": "operates the laboratory"}]
    ref = registry.parse({"references": [card]})["basner-2011-pvt-b"]
    assert ref.affiliations[0].organization == "University of Nowhere"
    assert ref.named_organizations[0].role == "operates the laboratory"


@pytest.mark.parametrize(
    ("spoil", "reason"),
    [
        (_author_not_written, "no está escrito"),
        (_author_with_digits, "no es un nombre"),
        (_author_email, "no es un nombre"),
        (_author_repeated, "repetido"),
        (_authors_empty, "al menos un nombre"),
        (_authors_not_a_list, "al menos un nombre"),
        (_author_not_a_string, "no es un nombre"),
        (_named_role_not_written, "escritos juntos en la nota"),
        (_named_name_not_written, "escritos juntos en la nota"),
        (_named_role_of_someone_else, "escritos juntos en la nota"),
        (_author_inside_another_name, "no está escrito"),
        (_author_inside_a_word, "no está escrito"),
        (_two_authors_in_one, "no es un nombre"),
        (_named_contact, "datos de contacto"),
        (_named_phone, "datos de contacto"),
        (_named_name_email, "no es un nombre"),
        (_named_extra_field, "sin más campos"),
        (_named_also_author, "ya entre quienes firman"),
        (_named_repeated, "repetido"),
        (_named_empty, "al menos una persona"),
    ],
)
def test_the_registry_rejects_a_person_the_card_does_not_write(
    spoil: Callable[[dict[str, Any]], None], reason: str
) -> None:
    card = _raw_card("basner-2011-pvt-b")
    registry.parse({"references": [copy.deepcopy(card)]})  # sin estropear, carga
    spoil(card)
    with pytest.raises(registry.RegistryError, match=reason):
        registry.parse({"references": [card]})


def test_a_role_with_a_span_of_years_is_not_contact_data() -> None:
    card = _raw_card("basner-2011-pvt-b")
    card["notes"] += " Kerry Lee, Chief Medical Officer 2014-2018."
    card["named_people"] = [{"name": "Kerry Lee", "role": "Chief Medical Officer 2014-2018"}]
    ref = registry.parse({"references": [card]})["basner-2011-pvt-b"]
    assert ref.named_people[0].role == "Chief Medical Officer 2014-2018"


def test_the_role_can_come_before_the_name_and_a_name_can_be_surname_comma_name() -> None:
    (dinges,) = registry.get("hrr-task-1651-pvt").named_people
    assert (dinges.name, dinges.role) == ("Dinges, David", "investigador principal")


def test_the_people_fields_do_not_change_the_shape_of_a_citation() -> None:
    # Las citas del resto de la API (y sus ficheros de referencia) no ganan campos.
    shape = registry.get("basner-2011-pvt-b").to_dict()
    assert "authors" not in shape and "named_people" not in shape
    shape = registry.get("ntrs-20200000567").to_dict()
    assert "affiliations" not in shape and "named_organizations" not in shape


# --------------------------------------------------------------------------- #
# El documento no cita fichas que no existen (la lista completa es la ruta, no él)
# --------------------------------------------------------------------------- #


def test_every_card_the_document_cites_exists() -> None:
    doc = DOC.read_text(encoding="utf-8")
    cited = set(re.findall(r"`([a-z0-9]+(?:-[a-z0-9]+)+)`", doc))
    known = set(registry.registry())
    assert cited, "el documento no cita ninguna ficha"
    assert cited - known == set()
