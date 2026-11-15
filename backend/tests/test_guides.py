"""Las guías de medida y el glosario: cada paso con su frase leída, y nada que suene a orden.

Lo que vigilan estas pruebas:

- cada guía nombra indicadores del catálogo y cada paso lleva al menos una frase leída, con su
  ficha del registro resuelta tal cual (`registry.cite`);
- ningún texto en español de las guías ni del glosario lo bloquea el filtro de lenguaje
  (invariante 7), y ningún paso dice qué hacer ante una cifra;
- el peso en vuelo dice que no hay báscula, con la fuente (SLAMMD y BMMD);
- cada definición dice su origen, y la de EMMA nombra un fichero que existe;
- el cargador rechaza lo mal formado.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import guides, text_guard
from app.evidence import registry
from app.guides import GuideError
from app.ingest.codes import CATALOG
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
RAW_GUIDES: dict[str, Any] = json.loads(guides.GUIDES_PATH.read_text(encoding="utf-8"))
RAW_GLOSSARY: dict[str, Any] = json.loads(guides.GLOSSARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _basis(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for guide in payload["guides"]:
        for step in (*guide["steps"], *guide["in_flight"]):
            out.extend(step["basis"])
    return out


# --------------------------------------------------------------------------- #
# Las guías
# --------------------------------------------------------------------------- #


def test_the_guides_cover_the_measurements_the_challenge_names(client: TestClient) -> None:
    payload = client.get("/api/guides").json()
    keys = {item["key"] for guide in payload["guides"] for item in guide["indicators"]}
    # Tensión, temperatura, saturación, peso, frecuencia y variabilidad del wearable, y la PVT.
    assert {
        "systolic-bp", "diastolic-bp", "body-temperature", "oxygen-saturation", "body-weight",
        "heart-rate", "hrv-sdnn", "pvt-mean-rt", "pvt-lapses",
    } <= keys
    assert keys <= CATALOG.keys()
    for guide in payload["guides"]:
        for item in guide["indicators"]:
            # El nombre en español del catálogo, no el de LOINC.
            assert item["display_es"] and item["display_es"] != CATALOG[item["key"]].display


def test_every_step_carries_a_quote_and_its_registry_card(client: TestClient) -> None:
    payload = client.get("/api/guides").json()
    for guide in payload["guides"]:
        assert guide["steps"] or guide["in_flight"], guide["id"]
        for step in (*guide["steps"], *guide["in_flight"]):
            assert step["text"].strip()
            assert step["basis"], f"{guide['id']}: paso sin fuente: {step['text']}"
    for item in _basis(payload):
        assert item["quote"].strip() and item["where"].strip()
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", item["read_on"])
        # La ficha, la del registro sin retocar.
        assert item["citation"] == registry.cite(item["citation"]["id"]).to_dict()


def test_the_pvt_reuses_what_was_read_instead_of_copying_it(client: TestClient) -> None:
    pvt = next(guide for guide in RAW_GUIDES["guides"] if guide["id"] == "pvt")
    for step in pvt["steps"]:
        assert all(item.keys() == {"statement"} for item in step["basis"])
    served = next(g for g in client.get("/api/guides").json()["guides"] if g["id"] == "pvt")
    assert {item["citation"]["id"] for step in served["steps"] for item in step["basis"]} == {
        "basner-2011-pvt-b"
    }


def test_the_hrv_quotes_are_the_ones_its_card_records() -> None:
    """Las frases de la norma de la VFC salen de la lectura que guarda su ficha, letra a letra."""
    notes = registry.get("task-force-hrv-1996").notes or ""
    quotes = [
        item["quote"] for guide in RAW_GUIDES["guides"] for step in guide["steps"]
        for item in step["basis"] if item.get("ref") == "task-force-hrv-1996"
    ]
    assert quotes
    for quote in quotes:
        assert quote in notes, quote


def test_in_flight_body_mass_is_not_a_scale_and_says_so_with_its_source(
    client: TestClient,
) -> None:
    guide = next(g for g in client.get("/api/guides").json()["guides"] if g["id"] == "body-mass")
    text = " ".join(step["text"] for step in guide["in_flight"])
    assert "SLAMMD" in text and "BMMD" in text and "báscula" in text
    cited = {item["citation"]["id"] for step in guide["in_flight"] for item in step["basis"]}
    assert cited == {"zwart-2014-body-mass"}
    # Sin procedimiento leído del SLAMMD no hay pasos: lo dice lo no encontrado.
    assert guide["steps"] == []
    assert any("SLAMMD" in item for item in guide["not_found"])


def test_the_guides_link_the_ultrasound_protocols_instead_of_repeating_them(
    client: TestClient,
) -> None:
    payload = client.get("/api/guides").json()
    routes = {item["route"] for item in payload["elsewhere"]}
    assert "/api/imaging/protocols" in routes
    # Lo que se enlaza existe: la ruta responde y el módulo está en el repositorio.
    for item in payload["elsewhere"]:
        assert client.get(item["route"]).status_code == 200, item["route"]
        assert (ROOT / item["module"]).is_file(), item["module"]
    assert all(guide["id"] != "ultrasound" for guide in payload["guides"])


def test_the_cost_of_measuring_comes_from_the_cost_table(client: TestClient) -> None:
    from app.ingest import cost

    payload = client.get("/api/guides").json()
    for guide in payload["guides"]:
        for item in guide["indicators"]:
            measured = cost.cost(item["key"])
            assert item["equipment"] == (measured["equipment"] if measured else None)


# --------------------------------------------------------------------------- #
# Lo que dice: cómo medir, no qué hacer
# --------------------------------------------------------------------------- #


def test_no_text_of_the_guides_or_the_glossary_is_blocked_by_the_language_filter() -> None:
    for text in guides.displayed_texts():
        assert text_guard.check(text) == [], text


def test_no_step_tells_what_to_do_with_a_result() -> None:
    """Instrucciones de medida: ni un rango, ni una conducta ante una cifra (invariante 7)."""
    conditional = re.compile(
        r"\bsi (?:sale|da|marca|la (?:lectura|cifra)|el resultado|tienes|notas)\b|\bmm ?hg\b|°"
    )
    for guide in RAW_GUIDES["guides"]:
        for step in (*guide["steps"], *guide["in_flight"]):
            assert not conditional.search(text_guard.normalize(step["text"])), step["text"]


# --------------------------------------------------------------------------- #
# El glosario
# --------------------------------------------------------------------------- #


def test_the_glossary_defines_the_terms_the_console_uses(client: TestClient) -> None:
    payload = client.get("/api/glossary").json()
    ids = {term["id"] for term in payload["terms"]}
    assert {
        "baseline", "trend", "deviation", "false-alarm-rate", "sensitivity",
        "solar-particle-event", "light-time", "ridge", "signed-ledger", "safe-mode",
        "measured", "inferred", "predicted",
    } <= ids


def test_every_definition_says_where_it_comes_from(client: TestClient) -> None:
    for term in client.get("/api/glossary").json()["terms"]:
        assert term["origin_display"] == guides.ORIGIN_DISPLAY[term["origin"]]
        if term["origin"] == "emma":
            # El fichero que sostiene la definición existe en el repositorio.
            assert (ROOT / term["document"]).is_file(), term["document"]
        else:
            assert term["document"] is None and term["basis"]
        for item in term["basis"]:
            assert item["citation"] == registry.cite(item["citation"]["id"]).to_dict()


# --------------------------------------------------------------------------- #
# El cargador
# --------------------------------------------------------------------------- #


def _guide_with(change: Any) -> dict[str, Any]:
    raw = copy.deepcopy(RAW_GUIDES)
    change(raw["guides"][0])
    return raw


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda g: g["steps"][0].update(basis=[]), "sin `basis`"),
        (lambda g: g["steps"][0]["basis"][0].update(ref="no-existe"), "no está en el registro"),
        (lambda g: g["steps"][0]["basis"][0].update(quote=" "), "vacío"),
        (lambda g: g["steps"][0]["basis"][0].update(read_on="ayer"), "día de lectura"),
        (lambda g: g["steps"][0]["basis"][0].pop("where"), "exactamente"),
        (lambda g: g["steps"][0].update(basis=[{"statement": "no-existe"}]), "no es una frase"),
        (lambda g: g.update(indicators=["no-existe"]), "no están en el catálogo"),
        (lambda g: g["steps"][0].update(text="Debe tomar la pastilla antes de medir."), "filtro"),
        (lambda g: g.update(steps=[], in_flight=[]), "guía vacía"),
        (lambda g: g.update(steps=[], in_flight=g["steps"][:1], not_found=[]), "no se encontró"),
        (lambda g: g.update(extra=1), "exactamente"),
    ],
)
def test_the_guides_loader_rejects_what_breaks_its_contract(change: Any, reason: str) -> None:
    with pytest.raises(GuideError, match=reason):
        guides.validate_guides(_guide_with(change))


def test_a_repeated_guide_is_rejected() -> None:
    raw = copy.deepcopy(RAW_GUIDES)
    raw["guides"].append(copy.deepcopy(raw["guides"][0]))
    with pytest.raises(GuideError, match="repetido"):
        guides.validate_guides(raw)


def _term_with(index: int, change: Any) -> dict[str, Any]:
    raw = copy.deepcopy(RAW_GLOSSARY)
    change(raw["terms"][index])
    return raw


def _index(origin: str) -> int:
    return next(i for i, term in enumerate(RAW_GLOSSARY["terms"]) if term["origin"] == origin)


@pytest.mark.parametrize(
    ("origin", "change", "reason"),
    [
        ("emma", lambda t: t.pop("document"), "nombra su documento"),
        ("emma", lambda t: t.update(document="../fuera.md"), "nombra su documento"),
        ("emma", lambda t: t.update(origin="otro"), "`origin`"),
        ("source", lambda t: t.pop("basis"), "sin `basis`"),
        ("source", lambda t: t.update(document="backend/app/guides.py"), "no nombra documento"),
        ("source", lambda t: t["basis"][0].update(ref="no-existe"), "no está en el registro"),
        ("emma", lambda t: t.update(definition="Sin duda es lo mejor."), "filtro"),
        ("emma", lambda t: t.update(definition=" "), "sin `definition`"),
    ],
)
def test_the_glossary_loader_rejects_what_breaks_its_contract(
    origin: str, change: Any, reason: str,
) -> None:
    with pytest.raises(GuideError, match=reason):
        guides.validate_glossary(_term_with(_index(origin), change))


def test_the_new_cards_are_cited_and_read_on_the_day_their_quotes_say() -> None:
    """Las cuatro fichas de MedlinePlus de esta unidad las cita una guía, y su nota fecha la
    lectura el mismo día que las frases."""
    cited = guides.guides_cited_refs()
    for ref_id in (
        "medlineplus-blood-pressure-measurement", "medlineplus-temperature-measurement",
        "medlineplus-pulse-oximetry", "medlineplus-pulse",
    ):
        assert ref_id in cited
        days = {
            item["read_on"] for guide in RAW_GUIDES["guides"]
            for step in (*guide["steps"], *guide["in_flight"]) for item in step["basis"]
            if item.get("ref") == ref_id
        }
        assert days and all(day in (registry.get(ref_id).notes or "") for day in days)


def test_sleep_is_the_actigraphy_emma_ingests_and_says_what_it_did_not_read(
    client: TestClient,
) -> None:
    """El sueño de EMMA es el del actígrafo (`sleep-duration`, `sleep-efficiency`): la guía cuenta
    cómo se registra en vuelo con Standard Measures y no se inventa pasos de colocación."""
    guide = next(
        g for g in client.get("/api/guides").json()["guides"] if g["id"] == "sleep-actigraphy"
    )
    assert {item["key"] for item in guide["indicators"]} == {"sleep-duration", "sleep-efficiency"}
    assert guide["steps"] == []
    cited = {item["citation"]["id"] for step in guide["in_flight"] for item in step["basis"]}
    assert cited == {"hardy-2025-spaceflight-standard-measures"}
    assert any("manual de su fabricante" in item for item in guide["not_found"])


def test_the_sleep_card_records_the_new_reading() -> None:
    """Las frases del sueño se leyeron el 2026-11-03 en Hardy et al. 2025: la nota de la ficha
    deja constancia de esa lectura y de quién la cita."""
    notes = registry.get("hardy-2025-spaceflight-standard-measures").notes or ""
    days = {
        item["read_on"] for guide in RAW_GUIDES["guides"]
        for step in (*guide["steps"], *guide["in_flight"]) for item in step["basis"]
        if item.get("ref") == "hardy-2025-spaceflight-standard-measures"
    }
    assert days and all(day in notes for day in days)
    assert "data/measurement_guides.json" in notes


def test_mood_says_its_anchors_are_emma_s_unvalidated_decision(client: TestClient) -> None:
    """La escala de ánimo es propia (`codes.OWN_SCALE_ANCHORS`): sin fuente no hay pasos, y la
    guía dice sus anclas tal cual las decidió EMMA, y que están sin validar."""
    from app.ingest.codes import OWN_SCALE_ANCHORS

    guide = next(
        g for g in client.get("/api/guides").json()["guides"] if g["id"] == "mood-self-report"
    )
    assert [item["key"] for item in guide["indicators"]] == ["mood-valence"]
    assert guide["steps"] == []
    anchors = OWN_SCALE_ANCHORS["mood-valence"]
    said = " ".join(guide["not_found"])
    assert f"«{anchors.low}»" in said and f"«{anchors.high}»" in said
    assert "decisión de diseño de EMMA sin validar" in said
    # Lo leído de vuelo es de otro instrumento y lo dice: no se presenta como el de EMMA.
    text = " ".join(step["text"] for step in guide["in_flight"])
    assert "otro instrumento" in text and "El ánimo no está" in text
    cited = {item["citation"]["id"] for step in guide["in_flight"] for item in step["basis"]}
    assert cited == {"jones-2022-sleep-pvt-iss"}


def test_no_guide_points_capillary_glucose_at_the_serum_code() -> None:
    """La glucosa de laboratorio (2345-7) es de suero o plasma. Una guía de glucómetro capilar
    apuntada a ella mentiría sobre la muestra (invariante 2): ninguna guía la nombra, y la del
    glucómetro nombra la glucosa capilar (41653-7), con su muestra y su método en el código."""
    assert CATALOG["glucose"].code == "2345-7"
    assert all("glucose" not in guide["indicators"] for guide in RAW_GUIDES["guides"])
    glucometer = next(g for g in RAW_GUIDES["guides"] if g["id"] == "capillary-glucose")
    assert glucometer["indicators"] == ["glucose-capillary"]
    capillary = CATALOG["glucose-capillary"]
    assert capillary.code == "41653-7" and capillary.unit == "mg/dL"
    assert "Capillary blood by Glucometer" in capillary.display


def test_the_capillary_glucose_guide_cites_what_was_read_and_says_what_was_not(
    client: TestClient,
) -> None:
    """Cada paso, de los CDC o de MedlinePlus; sin frase leída de vuelo, lo dice `not_found`."""
    guide = next(
        g for g in client.get("/api/guides").json()["guides"] if g["id"] == "capillary-glucose"
    )
    cited = {item["citation"]["id"] for step in guide["steps"] for item in step["basis"]}
    assert cited == {"cdc-monitoring-blood-sugar", "medlineplus-blood-sugar-test"}
    assert guide["in_flight"] == []
    assert any("ISS" in line for line in guide["not_found"])
    assert any("microgravedad" in line for line in guide["not_found"])
    # Ningún paso copia un objetivo de glucosa: la guía dice cómo se mide, no qué hacer con él.
    text = " ".join(step["text"] for step in guide["steps"])
    assert "mg/dL" not in text and not re.search(r"\d{2,3}", text)
    for ref_id in cited:
        days = {
            item["read_on"] for step in guide["steps"] for item in step["basis"]
            if item["citation"]["id"] == ref_id
        }
        assert days and all(day in (registry.get(ref_id).notes or "") for day in days)


# --------------------------------------------------------------------------- #
# La batería Cognition (2026-11-03)
# --------------------------------------------------------------------------- #


def _cognition(payload: dict[str, Any]) -> dict[str, Any]:
    return next(g for g in payload["guides"] if g["id"] == "cognition-battery")


def test_the_cognition_guide_covers_the_ten_tests_of_the_battery(client: TestClient) -> None:
    """Las diez pruebas: cada una con su paso y sus indicadores del catálogo (la PVT, los suyos)."""
    from app.ingest.codes import COGNITION_KEYS, COGNITION_TESTS

    guide = _cognition(client.get("/api/guides").json())
    keys = {item["key"] for item in guide["indicators"]}
    assert COGNITION_KEYS | {"pvt-mean-rt", "pvt-lapses"} == keys
    texts = [step["text"] for step in guide["steps"]]
    siglas = [test.sigla for test in COGNITION_TESTS] + ["PVT"]
    assert len(siglas) == 10
    for number, sigla in enumerate(siglas, start=1):
        # Un paso por prueba, numerado en el orden estándar de la fuente.
        assert any(text.startswith(f"{number}. {sigla} (") for text in texts), sigla
    assert guide["in_flight"], "sin lo leído de cómo se pasa en vuelo"


def test_the_cognition_guide_cites_only_the_battery_cards(client: TestClient) -> None:
    guide = _cognition(client.get("/api/guides").json())
    cited = {
        item["citation"]["id"]
        for step in (*guide["steps"], *guide["in_flight"]) for item in step["basis"]
    }
    assert cited <= {
        "basner-2015-cognition-battery", "dev-2024-cognition-iss",
        "hardy-2025-spaceflight-standard-measures", "hrp-bmed-evidence-report",
    }
    assert "basner-2015-cognition-battery" in cited and "dev-2024-cognition-iss" in cited


def test_the_cognition_quotes_copied_here_are_dated_in_their_card() -> None:
    """Las frases copiadas en esta guía con su día de lectura: la ficha anota ese día."""
    raw = next(g for g in RAW_GUIDES["guides"] if g["id"] == "cognition-battery")
    readings = [
        item for step in (*raw["steps"], *raw["in_flight"]) for item in step["basis"]
        if "ref" in item
    ]
    assert readings
    for item in readings:
        notes = registry.get(item["ref"]).notes or ""
        assert item["read_on"] in notes, item["quote"]


def test_the_cognition_guide_gives_no_threshold_or_reading_of_the_result() -> None:
    """Cómo se pasa, no qué significa: ni la puntuación de 0 a 1000 del programa ni el umbral de
    lapso de la PVT, ni un «mejor» o «peor» (invariante 7)."""
    raw = next(g for g in RAW_GUIDES["guides"] if g["id"] == "cognition-battery")
    texts = [step["text"] for step in (*raw["steps"], *raw["in_flight"])] + raw["not_found"]
    forbidden = re.compile(
        r"\b1000\b|\b355\b|\b500 ?ms\b|umbral|\bnormal|anormal|mejor|peor|deterioro|"
        r"diagnost|\bdsm\b"
    )
    for text in texts:
        assert not forbidden.search(text_guard.normalize(text)), text


def test_the_dsm_is_declined_as_a_scope_decision_and_written_where_it_is_read() -> None:
    """Por qué no el DSM-5-TR: decisión de alcance, dicha en la nota de las guías y en el contexto
    de producto («No se adopta, y por qué»), sin citarlo como fuente leída."""
    assert "DSM-5-TR" in RAW_GUIDES["_nota"] and "invariante 7" in RAW_GUIDES["_nota"]
    readme = (ROOT / "docs" / "contexto" / "README.md").read_text(encoding="utf-8")
    declined = readme.split("### No se adopta, y por qué", 1)[1].split("### Pendiente", 1)[0]
    assert "DSM-5-TR" in declined
    assert all("dsm" not in ref_id for ref_id in registry.registry())
