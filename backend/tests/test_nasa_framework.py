"""El marco de NASA, leído: `read_sources` en `/api/framework`.

Lo que vigilan estas pruebas es que lo leído no diga más de lo que se leyó: que cada frase
lleve su fuente oficial, su sección y su ficha del registro; que de cada documento se declare
cuánto se leyó; que el texto sobre EMMA no reclame conformidad con nada (invariante 6); y que
nada de esto mueva el veredicto del motor (invariante 5). **Ninguna prueba sale a la red**: la
lectura se hizo una vez, el 2026-10-13, y aquí solo se comprueba lo que quedó escrito.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.evidence import nasa_framework, read_contract, registry
from app.main import app

BACKEND = Path(__file__).resolve().parents[1]
BLOCKS = [
    "cdss", "hermes", "exmc-gaps-today", "imm-limitations", "medprat", "food-gaps",
    "food-radiation", "level-of-care", "eimo", "habitat-systems",
]
REPO = BACKEND.parent
# Lo leído después de la primera lectura, con su día: en la decimocuarta ronda, MEDPRAT e IMPACT,
# el ATCS y OCHMO-TB-002; en la decimoquinta, el memorando de 2025, las dos presentaciones de
# 2020, el resumen de AsMA de 2025 y la relectura entera de la página de resumen del IMM.
LATER_READING = {
    **dict.fromkeys((
        "ntrs-20180008706", "ntrs-20240001402", "ntrs-20250000009", "ntrs-20230015831",
        "ochmo-tb-031",
    ), "2026-11-01"),
    **dict.fromkeys(("ntrs-20205011728", "ochmo-tb-013"), "2026-10-31"),
    **dict.fromkeys((
        "ntrs-20180004678", "ntrs-20230001121", "ntrs-20230013414", "ntrs-20230014551",
        "nasa-iss-atcs-overview", "ochmo-tb-002",
    ), "2026-10-21"),
    **dict.fromkeys((
        "ntrs-20240012058", "ntrs-20200000853", "ntrs-20200000974", "nasa-imm-overview",
    ), "2026-10-22"),
    # Decimoséptima ronda (U9): el PDF del resumen de 2020, lo que el informe de alimentación de
    # 2016 dice de la radiación, la página de TRISH en nasa.gov y la recomendación del CDSS,
    # releída para copiar sus dieciséis supuestos (y comprobar contra ella las demás frases).
    # Decimoctava (U14): el resumen descargable de AsMA 2025, contra el que se comprobó su frase.
    **dict.fromkeys((
        "ntrs-20200000567", "hrp-food-system-evidence-report", "nasa-trish", "ntrs-20220017869",
        # Decimoctava ronda (U19): la página del Apéndice E, con ficha propia desde ese día y
        # releída entera para comprobar las dos frases del IMM que la citan.
        "nasa-std-3001-appendix-e",
        "ntrs-20240013005",
    ), "2026-10-26"),
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
    return copy.deepcopy(json.loads(nasa_framework.READ_PATH.read_text("utf-8")))


def _statements() -> dict[str, dict[str, Any]]:
    return {
        item["id"]: item
        for block in nasa_framework.payload()["blocks"]
        for item in block["statements"]
    }


# --------------------------------------------------------------------------- #
# Lo leído: cada frase con su fuente, y lo que la lectura corrigió
# --------------------------------------------------------------------------- #


def test_the_file_as_shipped_is_valid_and_has_its_blocks(raw: dict[str, Any]) -> None:
    assert nasa_framework.validate(raw) is raw
    assert [block["id"] for block in nasa_framework.payload()["blocks"]] == BLOCKS


def test_every_statement_carries_quote_place_official_url_and_a_registry_card() -> None:
    for item in _statements().values():
        assert item["quote"].strip() and item["where"].strip()
        assert item["url"].startswith("https://")
        assert item["url"].split("/")[2] in nasa_framework.OFFICIAL_HOSTS
        ref = registry.get(item["ref"])
        assert (item["source"], item["title"]) == (ref.source, ref.title)
        # Cada frase lleva el día en que se leyó su fuente, no el de otra lectura.
        expected = LATER_READING.get(item["ref"], "2026-10-13")
        assert item["read_on"] == expected, item["id"]
        assert item["extent_text"] == nasa_framework.EXTENTS[item["extent"]]


def test_every_source_says_how_much_of_it_was_read() -> None:
    sources = {item["ref"]: item for item in nasa_framework.payload()["sources"]}
    assert nasa_framework.cited_refs() <= set(sources)
    for item in sources.values():
        assert item["extent_text"] == nasa_framework.EXTENTS[item["extent"]]
        assert item["what"].strip()
    # De la que solo se leyó la ficha y el resumen de NTRS se dice así, con esas palabras.
    assert sources["ntrs-20200000567"]["extent"] == "record"
    assert sources["ntrs-20200000567"]["extent_text"] == (
        "leído: resumen de NTRS; el documento completo, no"
    )
    # Y la ficha del registro de cada documento leído dice en `notes` cuánto se leyó y cuándo:
    # el mismo día que declara la fuente.
    assert nasa_framework.payload()["read_on"] == "2026-10-13"
    assert {
        ref: item["read_on"] for ref, item in sources.items() if item["read_on"] != "2026-10-13"
    } == LATER_READING
    for ref_id, item in sources.items():
        notes = registry.get(ref_id).notes
        assert notes is not None and (item["read_on"] in notes), ref_id


def test_the_four_functions_and_the_constraints_come_in_the_words_of_the_source() -> None:
    statements = _statements()
    assert statements["cdss-functions"]["quote"] == (
        "The crew will need to autonomously detect, diagnose, treat, and prevent medical events."
    )
    constraints = [statements[f"cdss-constraint-{number}"] for number in range(1, 5)]
    assert all(item["where"] == "§6.2 Constraints, p. 16" for item in constraints)
    assert all(item["ref"] == "ntrs-20220017869" for item in constraints)
    assert "cloud services will not be an option" in constraints[1]["quote"]
    assert "mass, volume, power, crew time" in statements["cdss-mission-constraints"]["quote"]


def test_what_the_reading_corrected_is_served_as_read() -> None:
    """Med07 cerrado, Food-0x divididos, la norma sin niveles: lo dice la fuente, no EMMA."""
    statements = _statements()
    assert "Status: Closed" in statements["gap-med07-closed"]["where"]
    assert statements["gap-medical-701-open"]["quote"] == "Status: Open"
    for number in range(1, 5):
        item = statements[f"food-0{number}-split"]
        assert item["quote"] == "This Gap was split into the following Gaps:"
        assert item["ref"] == "hrr-gaps" and "FN-" in item["note"]
    assert "Levels of Care have been replaced" in statements["loc-standard-today"]["quote"]
    # Los niveles IV y V salen del memorando que cita la norma, no de memoria.
    for key in ("loc-iv-definition", "loc-v-definition"):
        assert statements[key]["ref"] == "ntrs-20170004345"


def test_the_declared_limitations_of_the_imm_are_nasa_words() -> None:
    statements = _statements()
    for key in ("imm-iss-baseline", "imm-clinical-optimism", "imm-resource-limits"):
        assert statements[key]["where"] == "«Model Assumptions & Limitations»"
        assert statements[key]["ref"] == "nasa-imm-overview"
    # Dos páginas de NASA que no dicen lo mismo: se sirven las dos, y se dice.
    assert "no dicen lo mismo" in statements["imm-count-overview"]["note"]
    assert "more than 100" in statements["imm-count-page"]["quote"]


def test_each_block_says_apart_what_emma_does_and_what_was_not_read() -> None:
    for block in nasa_framework.payload()["blocks"]:
        assert block["emma"].startswith(("EMMA ", "/api/framework "))
        assert block["not_read"], block["id"]
        assert not read_contract.claims(block["emma"], nasa_framework.CLAIM_WORDS)


# --------------------------------------------------------------------------- #
# La carga rechaza lo que no se sostiene con la fuente delante
# --------------------------------------------------------------------------- #


def test_a_statement_without_quote_place_or_source_is_rejected(raw: dict[str, Any]) -> None:
    for field in ("quote", "where", "ref"):
        broken = copy.deepcopy(raw)
        broken["blocks"][0]["statements"][0][field] = " "
        with pytest.raises(nasa_framework.FrameworkError, match=f"falta `{field}`"):
            nasa_framework.validate(broken)


def test_a_statement_without_its_own_url_is_read_at_the_address_of_its_card(
    raw: dict[str, Any],
) -> None:
    """La dirección no se escribe dos veces: sin `url` propia, vale la de la ficha."""
    assert raw["blocks"][0]["statements"][0]["url"] is None
    served = _statements()
    assert served["cdss-functions"]["url"] == registry.get("ntrs-20220017869").url
    # Y la página concreta de un hueco del Roadmap sí lleva la suya.
    assert served["gap-med07-closed"]["url"].endswith("/Gaps/gap.aspx?i=639")


def test_a_url_that_is_not_an_official_nasa_source_is_rejected(raw: dict[str, Any]) -> None:
    for url in (
        "https://en.wikipedia.org/wiki/Clinical_decision_support_system",
        "http://ntrs.nasa.gov/citations/20220017869",
        "https://ntrs.nasa.gov.example.org/citations/20220017869",
    ):
        broken = copy.deepcopy(raw)
        broken["blocks"][0]["statements"][0]["url"] = url
        with pytest.raises(nasa_framework.FrameworkError, match="no es una fuente oficial"):
            nasa_framework.validate(broken)


def test_a_source_that_is_not_in_the_registry_is_rejected(raw: dict[str, Any]) -> None:
    raw["sources"]["ntrs-00000000"] = {"extent": "full", "what": "inventada"}
    # Con el error del cargador y el motivo del registro (el contrato común, `read_contract`).
    with pytest.raises(
        nasa_framework.FrameworkError, match="ntrs-00000000: .*no está en el registro"
    ) as caught:
        nasa_framework.validate(raw)
    assert isinstance(caught.value.__cause__, registry.RegistryError)


def test_a_source_without_how_much_was_read_is_rejected(raw: dict[str, Any]) -> None:
    undeclared = copy.deepcopy(raw)
    del undeclared["sources"]["ntrs-20220017869"]
    with pytest.raises(nasa_framework.FrameworkError, match="no se declara cuánto se leyó"):
        nasa_framework.validate(undeclared)

    raw["sources"]["ntrs-20220017869"]["extent"] = "leído por encima"
    with pytest.raises(nasa_framework.FrameworkError, match="falta cuánto se leyó"):
        nasa_framework.validate(raw)


def test_a_reading_without_date_is_rejected(raw: dict[str, Any]) -> None:
    raw["read_on"] = "hace poco"
    with pytest.raises(nasa_framework.FrameworkError, match="read_on"):
        nasa_framework.validate(raw)


@pytest.mark.parametrize("value", ["hace poco", None, "21/10/2026"])
def test_a_source_read_on_another_day_needs_a_real_date(
    raw: dict[str, Any], value: object
) -> None:
    raw["sources"]["ntrs-20180004678"]["read_on"] = value
    with pytest.raises(nasa_framework.FrameworkError, match="ntrs-20180004678: `read_on`"):
        nasa_framework.validate(raw)


def test_a_source_cannot_be_read_before_the_first_reading(raw: dict[str, Any]) -> None:
    raw["sources"]["ntrs-20180004678"]["read_on"] = "2025-10-21"
    with pytest.raises(nasa_framework.FrameworkError, match="anterior a la primera lectura"):
        nasa_framework.validate(raw)


def test_a_gap_status_carries_the_date_its_roadmap_page_was_read(
    raw: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si se relee la página del Roadmap otro día, el estado del hueco lleva ese día."""
    raw["sources"]["hrr-gaps"]["read_on"] = "2026-10-21"
    monkeypatch.setattr(nasa_framework, "read", lambda: nasa_framework.validate(raw))
    assert nasa_framework.gap_status("Med07")["read_on"] == "2026-10-21"


def test_a_source_without_its_own_date_takes_the_date_of_the_reading(
    raw: dict[str, Any],
) -> None:
    assert "read_on" not in raw["sources"]["ntrs-20160012678"]
    assert nasa_framework.read_on(raw, "ntrs-20160012678") == raw["read_on"]
    assert nasa_framework.read_on(raw, "ochmo-tb-002") == "2026-10-21"
    served = {item["ref"]: item for item in nasa_framework.payload()["sources"]}
    assert served["ochmo-tb-002"]["read_on"] == "2026-10-21"
    assert served["ntrs-20160012678"]["read_on"] == "2026-10-13"
    # El estado de un hueco lleva el día de la lectura de su página, no otro.
    assert nasa_framework.gap_status("Med07")["read_on"] == "2026-10-13"


# --------------------------------------------------------------------------- #
# MEDPRAT, el ATCS y OCHMO-TB-002 (decimocuarta ronda)
# --------------------------------------------------------------------------- #


def _block(block_id: str) -> dict[str, Any]:
    return next(b for b in nasa_framework.payload()["blocks"] if b["id"] == block_id)


def test_medprat_is_read_as_the_line_after_the_imm_and_emma_does_not_duplicate_it() -> None:
    statements = _statements()
    assert "MEDPRAT" in statements["medprat-purpose"]["quote"]
    assert "mimics that of the IMM" in statements["medprat-mimics-imm"]["quote"]
    assert "successor to the Integrated Medical Model" in statements["impact-successor"]["quote"]
    assert "will soon replace" in statements["impact-will-replace-imm"]["quote"]
    assert "within MEDPRAT" in statements["impact-runs-on-medprat"]["quote"]
    block = _block("medprat")
    # Lo que EMMA no hace, con esas palabras: no estima probabilidades ni duplica la herramienta.
    assert "no usa MEDPRAT, IMPACT ni el IMM" in block["emma"]
    assert "No estima la frecuencia ni las consecuencias de eventos médicos" in block["emma"]
    # Una fecha de la sustitución no se ha encontrado, y se dice.
    assert any("no encontrada" in line for line in block["not_read"])


# --------------------------------------------------------------------------- #
# La pregunta del bloque de MEDPRAT: ¿ha sustituido IMPACT al IMM? (decimoquinta ronda)
# --------------------------------------------------------------------------- #


def _raw_block(raw: dict[str, Any], block_id: str) -> dict[str, Any]:
    return next(b for b in raw["blocks"] if b["id"] == block_id)


def test_the_2025_memorandum_is_read_and_still_calls_the_imm_the_standard() -> None:
    """NASA/TM-20240012058, leído entero: el IMM sigue siendo la referencia y no nombra a IMPACT."""
    statements = _statements()
    for key in ("medprat-evolution-2025", "imm-accepted-standard-2025", "medprat-comparable-2025"):
        assert statements[key]["ref"] == "ntrs-20240012058"
        assert statements[key]["extent"] == "full"
    assert statements["imm-accepted-standard-2025"]["quote"].startswith(
        "IMM is the currently accepted standard"
    )
    assert "no nombra a IMPACT" in statements["imm-accepted-standard-2025"]["note"]
    evolution = statements["medprat-evolution-2025"]["quote"]
    assert "evolution of the Integrated Medical Model" in evolution
    assert "is anticipated to produce" in statements["impact-anticipated-2025"]["quote"]
    assert "used by NASA" in statements["imm-used-2026"]["quote"]
    # Las dos presentaciones de 2020 que estaban «vistas y no leídas», leídas.
    assert statements["medprat-sel-2020"]["ref"] == "ntrs-20200000853"
    assert statements["medprat-sin-2020"]["ref"] == "ntrs-20200000974"
    block = _block("medprat")
    assert not any("20200000853" in line or "20200000974" in line for line in block["not_read"])
    assert not any("pasa del tamaño" in line for line in block["not_read"])


def test_the_replacement_is_not_dated_and_the_answer_rests_on_the_newest_source() -> None:
    question = _block("medprat")["question"]
    assert question["text"] == "¿Ha sustituido IMPACT al IMM, y desde cuándo?"
    assert question["answer"].startswith("Lo leído no fecha ninguna sustitución.")
    rests_on = [item["id"] for item in question["rests_on"]]
    # En el orden del bloque, con la fecha del documento: lo último es la página de 2026.
    assert rests_on == [
        "impact-will-replace-imm", "imm-accepted-standard-2025", "impact-anticipated-2025",
        "imm-used-2026",
    ]
    assert [item["date"] for item in question["rests_on"]] == [
        "2024-02-13", "2025-02", "2025-06-01", "2026-09-16",
    ]
    labels = {item["id"]: item["label"] for item in _block("medprat")["statements"]}
    assert all(item["label"] == labels[item["id"]] for item in question["rests_on"])
    # Los demás bloques no llevan pregunta: se sirve null, no se omite.
    others = [b for b in nasa_framework.payload()["blocks"] if b["id"] != "medprat"]
    assert others and all(b["question"] is None for b in others)


def test_an_answer_that_ignores_the_newest_source_of_its_block_is_rejected(
    raw: dict[str, Any],
) -> None:
    """Responder con el resumen de 2024 cuando el bloque guarda la página de 2026 no se sirve."""
    _raw_block(raw, "medprat")["question"]["rests_on"].remove("imm-used-2026")
    with pytest.raises(nasa_framework.FrameworkError, match="no mira la fuente más reciente"):
        nasa_framework.validate(raw)


def _dated(monkeypatch: pytest.MonkeyPatch, dates: dict[str, str | None]) -> None:
    """Las fichas del registro con otra fecha, para probar la comparación sin tocar el fichero."""
    real = registry.get

    def get(ref_id: str) -> registry.EvidenceRef:
        ref = real(ref_id)
        return dataclasses.replace(ref, date=dates[ref_id]) if ref_id in dates else ref

    monkeypatch.setattr(registry, "get", get)


def test_a_source_dated_by_month_counts_as_possibly_newer(
    raw: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fechado «2026-09», el memorando pudo ser posterior al 16 de septiembre: no se le supone."""
    question = _raw_block(raw, "medprat")["question"]
    question["rests_on"] = [
        item for item in question["rests_on"] if item != "imm-accepted-standard-2025"
    ]
    question["answer"] = "Una respuesta que no cita el memorando."
    assert nasa_framework.validate(copy.deepcopy(raw))  # con su fecha real, febrero de 2025
    _dated(monkeypatch, {"ntrs-20240012058": "2026-09"})
    with pytest.raises(nasa_framework.FrameworkError, match="ntrs-20240012058"):
        nasa_framework.validate(raw)


def test_an_answer_dated_by_month_does_not_take_the_last_day_of_it(
    raw: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si lo más nuevo usado es «2025-02», un documento del 15 de febrero puede ser posterior."""
    block = _raw_block(raw, "medprat")
    keep = {"imm-accepted-standard-2025", "medprat-evolution-2025", "impact-anticipated-2025"}
    block["statements"] = [item for item in block["statements"] if item["id"] in keep]
    block["question"]["rests_on"] = ["imm-accepted-standard-2025"]
    block["question"]["answer"] = "El IMM sigue siendo «the currently accepted standard»."
    _dated(monkeypatch, {"ntrs-20240013005": "2025-01-31"})
    assert nasa_framework.validate(copy.deepcopy(raw))  # anterior a febrero: no es más nuevo
    _dated(monkeypatch, {"ntrs-20240013005": "2025-02-15"})
    with pytest.raises(nasa_framework.FrameworkError, match="ntrs-20240013005"):
        nasa_framework.validate(raw)


def test_another_statement_of_a_document_already_used_is_not_newer(
    raw: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Se compara por documento: la conclusión del memorando no es «más nueva» que su resumen."""
    _dated(monkeypatch, {"ntrs-20240012058": "2026-09"})
    block = _raw_block(raw, "medprat")
    assert "medprat-comparable-2025" not in block["question"]["rests_on"]
    assert nasa_framework.validate(raw) is raw


def test_a_statement_whose_card_has_no_date_is_rejected_beside_a_question(
    raw: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _dated(monkeypatch, {"ntrs-20200000974": None})
    with pytest.raises(nasa_framework.FrameworkError, match="medprat-sin-2020: su ficha no tiene"):
        nasa_framework.validate(raw)


@pytest.mark.parametrize("answer", [
    "Lo leído dice que IMPACT «has replaced» al IMM.",
    "IMPACT «is anticipated to produce» y «has produced» resultados.",
])
def test_an_answer_that_quotes_what_its_statements_do_not_say_is_rejected(
    raw: dict[str, Any], answer: str
) -> None:
    """Lo que la respuesta pone entre comillas está, letra por letra, en una frase suya."""
    _raw_block(raw, "medprat")["question"]["answer"] = answer
    with pytest.raises(nasa_framework.FrameworkError, match="cita lo que no dicen"):
        nasa_framework.validate(raw)


def test_an_answer_may_only_quote_its_own_statements(raw: dict[str, Any]) -> None:
    """«mimics that of the IMM» está en el bloque, pero no en las frases en que se apoya."""
    question = _raw_block(raw, "medprat")["question"]
    question["answer"] += " MEDPRAT «mimics that of the IMM»."
    with pytest.raises(nasa_framework.FrameworkError, match="mimics that of the IMM"):
        nasa_framework.validate(copy.deepcopy(raw))
    question["rests_on"].append("medprat-mimics-imm")
    assert nasa_framework.validate(raw) is raw


@pytest.mark.parametrize("date", ["2025-Q1", "25-02-01", "2025-13", "20250201", "2025-02-30"])
def test_a_card_date_that_is_not_iso_fails_instead_of_comparing_as_text(
    raw: dict[str, Any], monkeypatch: pytest.MonkeyPatch, date: str
) -> None:
    _dated(monkeypatch, {"ntrs-20240012058": date})
    with pytest.raises(nasa_framework.FrameworkError, match="no es una fecha de ficha"):
        nasa_framework.validate(raw)


@pytest.mark.parametrize(("change", "message"), [
    ({"answer": " "}, "sin `text` o sin `answer`"),
    ({"text": ""}, "sin `text` o sin `answer`"),
    ({"rests_on": []}, "sin las frases en que se apoya"),
    ({"rests_on": "imm-used-2026"}, "sin las frases en que se apoya"),
    ({"rests_on": [{"id": "imm-used-2026"}]}, "sin las frases en que se apoya"),
    ({"rests_on": ["imm-used-2026", "imm-used-2026"]}, "repetida"),
    ({"rests_on": ["imm-used-2026", "cdss-functions"]}, "no son del bloque"),
])
def test_a_question_without_text_answer_or_its_own_statements_is_rejected(
    raw: dict[str, Any], change: dict[str, Any], message: str
) -> None:
    _raw_block(raw, "medprat")["question"].update(change)
    with pytest.raises(nasa_framework.FrameworkError, match=message):
        nasa_framework.validate(raw)


def test_the_atcs_and_the_eclss_brief_are_read_and_the_vocabulary_says_what_they_back() -> None:
    statements = _statements()
    for key in ("eatcs-independent-loops", "eatcs-reduced-capacity", "atcs-fdir"):
        assert statements[key]["ref"] == "nasa-iss-atcs-overview"
    assert "70 kW" in statements["eatcs-capacity"]["quote"]
    assert "Common Cabin Air Assembly" in statements["atcs-cabin-air"]["quote"]
    assert statements["tb002-air-revitalization"]["ref"] == "ochmo-tb-002"
    assert "temperature and humidity" in statements["tb002-air-revitalization"]["note"]
    block = _block("habitat-systems")
    assert "no lee telemetría" in block["emma"] and "es de diseño" in block["emma"]
    # La cadena de seis pasos de la base de conocimiento no está en la fuente: se dice.
    assert any("no aparece con esas palabras" in line for line in block["not_read"])
    # El vocabulario de sistemas cita las mismas fichas que se leyeron aquí.
    systems = json.loads((BACKEND / "app" / "data" / "habitat_systems.json").read_text("utf-8"))
    assert set(systems["basis_refs"]) == {
        "ochmo-tb-002", "nasa-iss-atcs-overview", "ochmo-tb-013", "ochmo-tb-031",
    }
    assert set(systems["basis_refs"]) <= nasa_framework.cited_refs()
    assert "sin respaldo bibliográfico" not in systems["basis"]


def test_the_atcs_lesson_in_the_context_layer_is_quoted_from_its_card() -> None:
    """`analysis/context.py` invoca el ATCS: la frase que cita es la leída, con su ficha."""
    source = (BACKEND / "app" / "analysis" / "context.py").read_text(encoding="utf-8")
    docstring = source.split('"""')[1]
    assert "`nasa-iss-atcs-overview`" in docstring
    registry.get("nasa-iss-atcs-overview")
    quoted = docstring.split('dice "', 1)[1].split('"', 1)[0]
    assert " ".join(quoted.split()) in _statements()["atcs-fdir"]["quote"]


@pytest.mark.parametrize("claim", [
    "EMMA implementa la arquitectura CDSS de ExMC.",
    "EMMA está alineado con la recomendación de ExMC.",
    "EMMA es conforme a NASA-STD-3001.",
    "EMMA cumple las restricciones del documento.",
])
def test_a_emma_text_that_claims_conformance_is_rejected(raw: dict[str, Any], claim: str) -> None:
    raw["blocks"][0]["emma"] = claim
    with pytest.raises(nasa_framework.FrameworkError, match="reclama conformidad"):
        nasa_framework.validate(raw)


@pytest.mark.parametrize("claim", [
    # La negación lejos, o en otra frase, no alcanza al reclamo.
    "EMMA no usa el IMM y es conforme a NASA-STD-3001.",
    "Ninguna duda: EMMA implementa la arquitectura CDSS de ExMC.",
    "EMMA no lee telemetría; cumple las restricciones del documento.",
    # Un giro con «sin» o «no» que refuerza no niega (de la revisión de código).
    "EMMA es sin duda conforme a NASA-STD-3001.",
    "EMMA no solo implementa la arquitectura CDSS de ExMC.",
])
def test_a_negation_that_does_not_reach_the_claim_does_not_save_it(
    raw: dict[str, Any], claim: str
) -> None:
    raw["blocks"][0]["emma"] = claim
    with pytest.raises(nasa_framework.FrameworkError, match="reclama conformidad"):
        nasa_framework.validate(raw)


@pytest.mark.parametrize("honest", [
    "EMMA no implementa la arquitectura CDSS de ExMC: cita su frase.",
    "EMMA no es conforme ni dice serlo: no se ha evaluado.",
    "EMMA no cumple ni reclama la norma.",
    "Sin implementación de referencia en EMMA.",
])
def test_a_emma_text_that_denies_conformance_is_not_a_claim(
    raw: dict[str, Any], honest: str
) -> None:
    """Lo que niega no reclama: la misma regla que en las fichas de credibilidad (§5.36.10)."""
    raw["blocks"][0]["emma"] = honest
    assert nasa_framework.validate(raw)["blocks"][0]["emma"] == honest


def _gap_statement(raw: dict[str, Any], statement_id: str) -> dict[str, Any]:
    for block in raw["blocks"]:
        for item in block["statements"]:
            if item["id"] == statement_id:
                return item
    raise AssertionError(statement_id)


def test_a_gap_status_that_the_roadmap_does_not_use_is_rejected(raw: dict[str, Any]) -> None:
    """«Cerrado más o menos» no es un estado: se dice el que publica la página, o ninguno."""
    _gap_statement(raw, "gap-med07-closed")["gap"]["status"] = "addressed"
    with pytest.raises(nasa_framework.FrameworkError, match="estado de hueco"):
        nasa_framework.validate(raw)


def test_a_gap_status_without_the_gap_name_is_rejected(raw: dict[str, Any]) -> None:
    _gap_statement(raw, "gap-med07-closed")["gap"]["id"] = " "
    with pytest.raises(nasa_framework.FrameworkError, match="sin el nombre del hueco"):
        nasa_framework.validate(raw)


def test_a_gap_status_read_outside_its_roadmap_page_is_rejected(raw: dict[str, Any]) -> None:
    item = _gap_statement(raw, "gap-med07-closed")
    item["url"] = "https://ntrs.nasa.gov/citations/20200000567"
    with pytest.raises(nasa_framework.FrameworkError, match="página del Human Research Roadmap"):
        nasa_framework.validate(raw)


def test_two_statuses_for_the_same_gap_are_rejected(raw: dict[str, Any]) -> None:
    _gap_statement(raw, "gap-medical-701-open")["gap"]["id"] = "Med07"
    with pytest.raises(nasa_framework.FrameworkError, match="dos estados para el hueco Med07"):
        nasa_framework.validate(raw)


def test_each_gap_status_is_served_with_its_statement() -> None:
    served = _statements()
    assert served["gap-med07-closed"]["gap"] == {
        "id": "Med07", "status": "closed", "status_text": nasa_framework.GAP_STATUSES["closed"],
    }
    assert served["fn-205-archived"]["gap"]["status"] == "archived"
    assert served["cdss-functions"]["gap"] is None
    assert nasa_framework.gap_status("Med10")["url"].endswith("/Gaps/gap.aspx?i=642")


def test_a_block_without_what_emma_does_or_without_statements_is_rejected(
    raw: dict[str, Any],
) -> None:
    silent = copy.deepcopy(raw)
    silent["blocks"][2]["emma"] = ""
    with pytest.raises(nasa_framework.FrameworkError, match="qué hace EMMA"):
        nasa_framework.validate(silent)

    raw["blocks"][2]["statements"] = []
    with pytest.raises(nasa_framework.FrameworkError, match="sin ninguna frase"):
        nasa_framework.validate(raw)


# --------------------------------------------------------------------------- #
# La ruta, el expediente y las invariantes
# --------------------------------------------------------------------------- #


def test_framework_serves_what_was_read_and_the_dossier_lists_its_cards(
    client: TestClient,
) -> None:
    body = client.get("/api/framework").json()
    assert body["read_sources"] == nasa_framework.payload()
    # Lo que ya se servía sigue igual: el enunciado de 2020 de los dos huecos.
    assert body["exmc_gaps"]["med07"]["gap"].startswith("We do not have the capability")

    references = client.get("/api/dossier/references").json()["references"]
    listed = {item["id"]: item for item in references}
    for ref_id in nasa_framework.cited_refs():
        assert ref_id in listed
        assert listed[ref_id]["evidence_type"] is not None


def _verdict(client: TestClient) -> dict[str, Any]:
    status = client.get("/api/status").json()
    return {
        "overall": status["overall_level"],
        "domains": status["domains"],
        "alerts": status["alerts"],
        "recommendations": status["recommendations"],
    }


@pytest.mark.parametrize("scenario", ["nominal", "spe-event", "menu-fatigue"])
def test_the_engine_verdict_is_the_same_with_and_without_what_was_read(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": scenario, "days": 40}
    ).status_code == 201

    monkeypatch.setattr(nasa_framework, "payload", lambda: {})
    without = _verdict(client)
    monkeypatch.undo()

    assert client.get("/api/framework").json()["read_sources"]["blocks"]
    assert _verdict(client) == without


def test_nothing_that_decides_reads_it_and_it_does_not_go_online() -> None:
    """Análisis, recomendaciones, ingesta, entorno, validación y núcleo no lo importan."""
    for package in ("analysis", "advisor", "ingest", "environment", "validation", "core"):
        for path in (BACKEND / "app" / package).rglob("*.py"):
            assert "nasa_framework" not in path.read_text(encoding="utf-8"), path
    source = Path(nasa_framework.__file__).read_text(encoding="utf-8")
    for name in ("httpx", "requests", "urllib.request", "egress", "socket"):
        assert f"import {name}" not in source and f"from {name}" not in source


# --------------------------------------------------------------------------- #
# Decimoséptima ronda (U9): lo que pide el CDSS, punto por punto; HERMES; radiación y alimento
# --------------------------------------------------------------------------- #

# Cada frase que pide algo lleva sus filas: las cuatro funciones, los dieciséis supuestos, las
# cuatro restricciones y los temas de la hoja de ruta de 2020. Las que describen el problema o el
# documento, no.
ASKING = {
    "cdss-functions", *(f"cdss-assumption-{number}" for number in range(1, 16)),
    "cdss-validated-models", *(f"cdss-constraint-{number}" for number in range(1, 5)),
    "cdss-roadmap-2020-topics", "cdss-roadmap-2020-prototypes",
}


def _coverage(raw: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = _raw_block(raw, "cdss")["coverage"]["rows"]
    return rows


def test_the_cdss_block_carries_the_sixteen_assumptions_in_the_words_of_the_source() -> None:
    statements = _statements()
    assumptions = [statements[f"cdss-assumption-{number}"] for number in range(1, 16)]
    assumptions.append(statements["cdss-validated-models"])
    assert [item["label"] for item in assumptions] == [
        f"Supuesto {number} del diseño" for number in range(1, 17)
    ]
    assert all(item["where"] == "§6.1 Assumptions, p. 16" for item in assumptions)
    assert all(item["ref"] == "ntrs-20220017869" for item in assumptions)
    assert statements["cdss-assumption-10"]["quote"] == (
        "The mission will consist of at least 4 crew members."
    )
    assert "train AI-models in flight" in statements["cdss-assumption-14"]["quote"]
    # Ya no se dice que de los dieciséis va uno solo.
    assert statements["cdss-validated-models"]["note"] is None
    # Los temas de la hoja de ruta salen del resumen de 2020, el que ya estaba registrado.
    for key in ("cdss-roadmap-2020-topics", "cdss-roadmap-2020-prototypes"):
        assert statements[key]["ref"] == "ntrs-20200000567"
        assert statements[key]["read_on"] == "2026-10-26"
    assert "data integration and fusion" in statements["cdss-roadmap-2020-topics"]["quote"]
    assert "prediction of medical events" in statements["cdss-roadmap-2020-prototypes"]["quote"]


def test_each_coverage_row_names_files_that_exist_in_the_repository() -> None:
    """Lo que la fila nombra existe: no se cita un fichero de memoria. Lee fuera de `backend/`,
    así que no va en la campaña de mutantes (que copia solo `backend/`)."""
    rows = _block("cdss")["coverage"]["rows"]
    named = [path for row in rows for path in row["files"]]
    assert named
    for path in named:
        assert (REPO / path).is_file(), path


def test_every_request_of_the_cdss_has_its_row() -> None:
    table = _block("cdss")["coverage"]
    statements = _statements()
    assert {row["statement"] for row in table["rows"]} == ASKING
    for row in table["rows"]:
        assert row["asks"] in statements[row["statement"]]["quote"], row
        assert row["label"] == statements[row["statement"]]["label"]
        assert row["coverage_text"] == nasa_framework.COVERAGES[row["coverage"]]
        assert row["coverage"] == "outside" or row["files"], row
    counts = table["counts"]
    assert list(counts) == list(nasa_framework.COVERAGES)
    assert sum(counts.values()) == len(table["rows"])
    # Lo que la tabla no puede decir: diagnostica, trata, entrena modelos o usa modelos validados.
    outside = {
        (row["statement"], row["asks"]) for row in table["rows"] if row["coverage"] == "outside"
    }
    assert {
        ("cdss-functions", "diagnose"), ("cdss-functions", "treat"),
        ("cdss-assumption-14", "train AI-models in flight"),
        ("cdss-validated-models", "validated decision-making models"),
    } <= outside
    # «Cubre» se define en la propia tabla: no es una evaluación ni una prueba en vuelo.
    assert "no que se haya evaluado" in table["about"]
    # Los bloques sin tabla la sirven como null, y las palabras de cada cobertura van aparte.
    assert _block("medprat")["coverage"] is None
    assert nasa_framework.payload()["coverages"] == [
        {"id": key, "text": text} for key, text in nasa_framework.COVERAGES.items()
    ]


@pytest.mark.parametrize(("change", "message"), [
    ({"asks": "diagnose and cure"}, "letra por letra"),
    ({"statement": "imm-iss-baseline"}, "no es de una frase del bloque"),
    ({"coverage": "mostly"}, "cobertura 'mostly' desconocida"),
    ({"coverage": "covered", "files": []}, "sin el fichero de EMMA"),
    ({"coverage": "partial", "files": []}, "sin el fichero de EMMA"),
    ({"files": ["/etc/passwd"]}, "rutas del repositorio"),
    ({"files": ["../fuera.py"]}, "rutas del repositorio"),
    ({"files": ["backend\\app\\core\\egress.py"]}, "rutas del repositorio"),
    ({"files": "backend/app/core/egress.py"}, "rutas del repositorio"),
    ({"files": ["C:/Users/x/egress.py"]}, "rutas del repositorio"),
    ({"files": ["."]}, "rutas del repositorio"),
    ({"files": ["backend/app/"]}, "rutas del repositorio"),
    ({"coverage": ["covered"]}, "desconocida"),
    ({"emma": "EMMA cumple esta restricción."}, "reclama conformidad"),
    ({"emma": " "}, "una fila sin su frase"),
    ({"asks": None}, "una fila sin su frase"),
])
def test_a_coverage_row_that_says_more_than_there_is_is_rejected(
    raw: dict[str, Any], change: dict[str, Any], message: str
) -> None:
    row = next(item for item in _coverage(raw) if item["coverage"] == "covered")
    row.update(change)
    with pytest.raises(nasa_framework.FrameworkError, match=message):
        nasa_framework.validate(raw)


def test_an_outside_row_may_name_no_file(raw: dict[str, Any]) -> None:
    row = next(item for item in _coverage(raw) if item["coverage"] == "covered")
    row.update({"coverage": "outside", "files": []})
    assert nasa_framework.validate(raw) is raw


def test_the_same_request_cannot_have_two_rows(raw: dict[str, Any]) -> None:
    rows = _coverage(raw)
    rows.append({**rows[0], "coverage": "covered"})
    with pytest.raises(nasa_framework.FrameworkError, match="tiene dos filas"):
        nasa_framework.validate(raw)


@pytest.mark.parametrize(("table", "message"), [
    ({"rows": []}, "sin `about`"),
    ({"about": "Qué quiere decir cubrir.", "rows": []}, "sin filas"),
    ({"about": "«Cubre» es que EMMA cumple lo que pide.", "rows": [{}]}, "reclama conformidad"),
    ({"about": "Qué quiere decir cubrir."}, "sin filas"),
    (["fila"], "sin `about`"),
])
def test_a_coverage_table_without_its_meaning_or_its_rows_is_rejected(
    raw: dict[str, Any], table: Any, message: str
) -> None:
    _raw_block(raw, "cdss")["coverage"] = table
    with pytest.raises(nasa_framework.FrameworkError, match=message):
        nasa_framework.validate(raw)


def test_hermes_is_read_on_nasa_and_emma_says_it_does_not_use_it() -> None:
    block = _block("hermes")
    statements = {item["id"]: item for item in block["statements"]}
    assert "Human and Environmental Research Matrix" in statements["hermes-what"]["quote"]
    assert "informed medical decisions" in statements["hermes-aim"]["quote"]
    for item in block["statements"]:
        assert item["ref"] == "nasa-trish" and item["read_on"] == "2026-10-26"
        assert item["url"].startswith("https://www.nasa.gov/")
    assert registry.get("nasa-trish").date == "2026-05-18"
    assert block["emma"].startswith("EMMA no usa HERMES")
    # Lo que no se sabe de HERMES se dice: cómo detecta, con qué se validó, si ha volado.
    assert any("si ha volado" in line for line in block["not_read"])
    # La fila del estado del arte existe y remite a lo mismo.
    state_of_the_art = (REPO / "compliance" / "state-of-the-art.md").read_text(encoding="utf-8")
    assert "**HERMES**" in state_of_the_art


def test_radiation_and_food_stability_are_shown_as_read_and_not_modelled() -> None:
    block = _block("food-radiation")
    assert {item["ref"] for item in block["statements"]} == {"hrp-food-system-evidence-report"}
    assert all(item["read_on"] == "2026-10-26" for item in block["statements"])
    quotes = " ".join(item["quote"] for item in block["statements"])
    assert "74.53 mGy over 880 days on ISS" in quotes
    assert "in deep space are unknown" in quotes
    assert block["emma"].startswith("EMMA no modela la estabilidad del alimento")
    assert "nada de este bloque entra en el análisis" in block["emma"]
    assert any("posteriores a 2016" in line for line in block["not_read"])
    # Va justo después de los huecos de alimentación: se lee junto a ellos.
    order = [item["id"] for item in nasa_framework.payload()["blocks"]]
    assert order.index("food-radiation") == order.index("food-gaps") + 1
