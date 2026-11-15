"""Lo leído en las fuentes de los límites de cabina: la luz y lo que la norma escribe de cada uno.

El 2026-10-13 se leyeron, en su PDF oficial, NASA-STD-3001 Vol 2 Rev F y JSC 20584 Rev C
(fichas `nasa-std-3001-vol2-rev-f` y `jsc-20584-rev-c` del registro de evidencia). De ahí sale:

- La luz (§8.7): la norma fija niveles POR TAREA y POR PERIODO, no un límite de toda la cabina.
  EMMA no sabe qué tarea se hace: la luz sigue sin evaluarse, y junto a la lectura se enseñan
  los requisitos leídos, cada uno con su condición.
- Lo que cada documento escribe junto al límite de los ocho parámetros que no son el CO2: la
  justificación del requisito o la fila de la tabla de SMAC, con su frase literal.

Lo que estas pruebas NO pueden comprobar es que la frase esté de verdad en el documento: eso se
cotejó a mano y con un guion contra el texto del PDF el día de la lectura. Lo acotan por el otro
lado: una cita, una cifra o una fila que cambie sin volver a leer la fuente rompe la huella de
abajo, y nada de esto puede mover lo que decide el motor (invariante 5). Sin red.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import context
from app.analysis.context import LIMIT_ONLY, annotate, correlate
from app.core import versioning
from app.environment import habitat
from app.environment.habitat import (
    DEFAULT_MODULE,
    DISPLAY_ONLY,
    LIGHT_REQUIREMENTS,
    PARAMETERS,
    Excursion,
    HabitatReading,
    excursions,
)
from app.evidence import registry
from app.evidence.registry import RegistryError
from app.text_guard import check

T0 = dt.datetime(2026, 12, 1, 0, 0, tzinfo=dt.UTC)
WINDOW = dt.timedelta(hours=48)
LIGHT = "cabin-light"
STANDARD, SMAC = "nasa-std-3001-vol2-rev-f", "jsc-20584-rev-c"
NOT_CO2 = sorted(set(PARAMETERS) - {"cabin-ppco2"})
CO2_SCENARIO = {"scenario": "co2-fatigue", "days": 10}

# Huella de todo lo que se copió de las fuentes el 2026-10-13: cada cita con su requisito y su
# sección, y cada fila de las tablas de iluminación con sus cifras. Si cambia, es que alguien ha
# tocado un texto leído: se vuelve a abrir el documento, se coteja y solo entonces se pone la
# huella nueva. No se actualiza «para que pase». Cambió el 2026-10-14 por una segunda lectura de
# la norma: la nota **** de la tabla 6.2-1 y los vértices de la figura 6.2-2, cada una con su
# fecha (`read_on`); las citas del 2026-10-13 siguen iguales.
READ_FINGERPRINT = "52f1b4953193bb79"


def _what_was_read() -> str:
    quotes = sorted(
        (key, item.ref, item.requirement, item.locator, item.quote, item.read_on or "")
        for key, (_, sources) in context._STANDARD_KNOWLEDGE.items()
        for item in sources
    )
    rows = [
        (item.requirement, item.table, item.source_row, item.low, item.high, item.stated,
         item.unit, item.same_quantity)
        for item in LIGHT_REQUIREMENTS
    ]
    text = json.dumps([quotes, rows, context.SOURCES_READ_ON], ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _excursion(key: str) -> Excursion:
    # El primer límite de salud: el rango objetivo del O2 va antes y no es uno.
    limit = next(item for item in PARAMETERS[key].limits if item.kind == "health")
    worst = limit.high + 1.0 if limit.high is not None else (limit.low or 0.0) - 1.0
    return Excursion(
        DEFAULT_MODULE, key, "health", limit.requirement, T0 - dt.timedelta(hours=6), T0, worst
    )


def _hypothesis(key: str) -> dict[str, Any]:
    crew = {"crew-01": "watch", "crew-02": "concern"}
    [item] = correlate(crew, [_excursion(key)], T0, WINDOW)["hypotheses"]
    return item


# --------------------------------------------------------------------------- #
# Las fuentes leídas
# --------------------------------------------------------------------------- #

def test_what_was_copied_from_the_sources_has_not_changed_since_it_was_read() -> None:
    assert _what_was_read() == READ_FINGERPRINT


def test_both_documents_have_their_entry_with_what_was_read_and_what_was_not() -> None:
    standard, smac = registry.get(STANDARD), registry.get(SMAC)
    assert "Revision F" in standard.source and standard.date == "2026-07-14"
    assert "Rev C" in smac.source and smac.date == "2024-06-13"
    for ref in (standard, smac):
        assert ref.url is not None and ref.url.startswith("https://")
        assert ".nasa.gov/" in ref.url
        assert ref.notes is not None and context.SOURCES_READ_ON in ref.notes
        # Una norma no tiene DOI, entorno de estudio ni población: no aplica, no «sin verificar».
        assert set(ref.not_applicable) == {"doi", "evidence_context", "population"}
        # Desde el 2026-10-13 el registro tiene la clase «norma técnica» y las dos la llevan.
        assert ref.evidence_type == "technical_standard" and not ref.unverified
    assert habitat.STANDARD_REF == STANDARD and context.SMAC_REF == SMAC


# --------------------------------------------------------------------------- #
# La luz: requisitos por tarea, a la vista y sin evaluar
# --------------------------------------------------------------------------- #

def test_light_stays_unevaluated_and_says_the_standard_gives_levels_per_task() -> None:
    assert LIGHT in DISPLAY_ONLY and LIGHT not in PARAMETERS
    spec = DISPLAY_ONLY[LIGHT]
    assert spec.limits == ()
    note = spec.limit_note or ""
    assert note == habitat.LIGHT_NO_GENERAL_LIMIT and note != habitat.NO_VERIFIED_LIMIT
    for said in ("Sin límite general", "por tarea", "[V2 8051]", "[V2 8055]", "no se evalúa"):
        assert said in note
    assert not check(note) and not check(habitat.REFERENCE_LABEL)

    published = spec.to_dict()
    assert published["limits"] == [] and published["source"] is None
    assert published["reference_label"] == "requisito por tarea; EMMA no conoce la tarea"
    assert published["reference_source"] == {
        "id": STANDARD, "title": habitat.STANDARD_TITLE, "read_on": "2026-10-13",
    }
    assert len(published["reference_requirements"]) == len(LIGHT_REQUIREMENTS) == 7
    for item in published["reference_requirements"]:
        assert item["evaluated"] is False
        assert item["condition"].strip() and not check(item["condition"])
        assert not check(item["label"])


def test_each_light_requirement_carries_the_figure_of_the_row_it_was_read_from() -> None:
    by_row = {item.source_row.split(" | ")[0]: item for item in LIGHT_REQUIREMENTS}
    assert len(by_row) == len(LIGHT_REQUIREMENTS)
    # Tabla 8.7-1: iluminancia, con el comparador que escribe la tabla.
    for name, low, high in (
        ("Translation & Stowage", 108.0, None),
        ("General Horizontal Ambient Lighting", 350.0, None),
        ("General Vertical Ambient Lighting", 200.0, None),
        ("Medical/Technical/Maintenance/Repair/PhotoTV Lighting", 750.0, None),
        ("Crew Sleep", None, 0.02),
    ):
        item = by_row[name]
        assert (item.low, item.high, item.stated) == (low, high, None), name
        assert item.requirement == "[V2 8051]" and item.table == "Tabla 8.7-1"
        assert item.unit == "lx" and item.same_quantity
        comparator, figure = re.fullmatch(
            r".* \| (>=|<=) ?([\d.]+) \| [\d, ]+", item.source_row
        ).groups()  # type: ignore[union-attr]
        assert float(figure) == (low if comparator == ">=" else high)
    # Tabla 8.7-2: otra magnitud (EDI melanópica), y el valor sin comparador no gana uno.
    wake, presleep = by_row["General Ambient Lighting"], by_row["Crew Pre-Sleep"]
    assert (wake.low, wake.high, wake.stated) == (None, None, 250.0)
    assert wake.source_row.endswith("Melanopic EDI Lux: 250")
    assert (presleep.low, presleep.high, presleep.stated) == (6.0, 10.0, None)
    assert presleep.source_row.endswith("Melanopic EDI Lux: 8 +/- 2")
    for item in (wake, presleep):
        assert item.requirement == "[V2 8055]" and item.table == "Tabla 8.7-2"
        assert not item.same_quantity and "no es la iluminancia que lee EMMA" in item.condition


@pytest.mark.parametrize("value", [0.0, 0.01, 5.0, 100.0, 300.0, 349.0, 800.0, 100_000.0])
def test_no_light_reading_is_an_excursion_whatever_the_requirements_say(value: float) -> None:
    # 300 lx (el valor de diseño del simulador) queda por debajo de los 350 lx del ambiente
    # general horizontal y por encima de los 0,02 lx del sueño: sin saber la tarea ni el
    # periodo, ninguna de las dos cosas es un incumplimiento, y no se señala.
    readings = [
        HabitatReading(DEFAULT_MODULE, LIGHT, value, T0 + dt.timedelta(minutes=15 * index),
                       "simulator:habitat")
        for index in range(12)
    ]
    assert excursions(readings) == []


def test_the_requirements_shown_are_not_limits_and_do_not_enter_the_rules() -> None:
    assert LIGHT not in versioning.rules()["habitat"]
    # Lo evaluado no lleva requisitos «de referencia»: se leerían como un segundo límite.
    for spec in PARAMETERS.values():
        published = spec.to_dict()
        assert spec.reference_requirements == ()
        assert published["reference_requirements"] == []
        assert published["reference_label"] is None and published["reference_source"] is None


# --------------------------------------------------------------------------- #
# Lo que la norma escribe de cada parámetro que no es CO2
# --------------------------------------------------------------------------- #

def test_all_eight_parameters_have_what_their_source_writes_and_co2_is_untouched() -> None:
    assert sorted(context._STANDARD_KNOWLEDGE) == NOT_CO2 and len(NOT_CO2) == 8
    assert "cabin-ppco2" in context._KNOWLEDGE
    from_smac = {"cabin-co", "cabin-ammonia", "cabin-formaldehyde"}
    for key, (text, sources) in context._STANDARD_KNOWLEDGE.items():
        assert not check(text), key
        assert sources and all(item.quote.strip() and item.locator.strip() for item in sources)
        refs = {item.ref for item in sources}
        assert refs == ({SMAC} if key in from_smac else {STANDARD}), key
        # El texto nombra el documento y, si es de la norma, el requisito del límite evaluado.
        if key in from_smac:
            assert "JSC 20584 Rev C" in text and "no implica un daño seguro" in text
        else:
            # El código del requisito, sin el rótulo que distingue los límites del O2.
            requirement = PARAMETERS[key].limits[0].requirement.split("]")[0] + "]"
            assert requirement in text and "NASA-STD-3001 Vol 2 Rev F" in text
            assert {item.requirement for item in sources} == {requirement}


def test_where_the_standard_describes_no_effect_the_text_says_so() -> None:
    oxygen, _ = context._STANDARD_KNOWLEDGE["cabin-ppo2"]
    pressure, _ = context._STANDARD_KNOWLEDGE["cabin-pressure"]
    assert "no describe un efecto por salir de él" in oxygen and "se desconocen" in oxygen
    # El requisito es de oxígeno inspirado; lo que EMMA lee es la presión parcial de cabina.
    assert "PIO2" in oxygen and "presión parcial de la cabina" in oxygen
    assert "no describe qué efecto tiene salir de él" in pressure


@pytest.mark.parametrize("key", NOT_CO2)
def test_a_hypothesis_gets_the_text_its_quotes_and_the_document_cited(key: str) -> None:
    hypothesis = _hypothesis(key)
    decided = json.dumps(hypothesis, sort_keys=True, default=str)
    # `correlate` no cambia: lo que la norma escribe se añade después, al anotar.
    assert hypothesis["what_is_known"] is None and len(hypothesis["evidence"]) == 1
    annotate(hypothesis)

    text, sources = context._STANDARD_KNOWLEDGE[key]
    assert hypothesis["what_is_known"] == text and hypothesis["knowledge_note"] is None
    assert hypothesis["what_is_known_basis"] == context.KNOWLEDGE_BASIS
    assert "no es un estudio sobre esta tripulación ni un diagnóstico" in context.KNOWLEDGE_BASIS
    assert hypothesis["what_is_known_sources"] == [
        {"ref": item.ref, "requirement": item.requirement, "locator": item.locator,
         "quote": item.quote, "read_on": item.read_on or "2026-10-13"}
        for item in sources
    ]
    # La cita del límite sigue la primera; detrás, una ficha por documento leído.
    cited = [item["id"] for item in hypothesis["evidence"]]
    assert cited == ["ochmo-tb-002", *dict.fromkeys(item.ref for item in sources)]
    assert all(item["url"] for item in hypothesis["evidence"])
    assert hypothesis["flow"][3]["detail"] == f"{len(cited)} fuentes citadas."

    # Solo texto y citas: lo demás de la hipótesis queda como lo dejó `correlate`.
    added = ("what_is_known", "what_is_known_basis", "what_is_known_sources", "evidence",
             "knowledge_note", "flow")
    before = json.loads(decided)
    after = json.loads(json.dumps(hypothesis, sort_keys=True, default=str))
    assert {k: v for k, v in after.items() if k not in added} == {
        k: v for k, v in before.items() if k not in added
    }
    # Anotar dos veces no duplica nada.
    once = json.dumps(hypothesis, sort_keys=True, default=str)
    annotate(hypothesis)
    assert json.dumps(hypothesis, sort_keys=True, default=str) == once


def test_co2_keeps_its_own_text_and_a_parameter_without_source_keeps_the_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    co2 = _hypothesis("cabin-ppco2")
    known, cited = co2["what_is_known"], [item["id"] for item in co2["evidence"]]
    annotate(co2)
    assert co2["what_is_known"] == known and "Law" in known
    assert [item["id"] for item in co2["evidence"]] == cited
    assert co2["what_is_known_basis"] is None and co2["what_is_known_sources"] == []

    monkeypatch.delitem(context._STANDARD_KNOWLEDGE, "cabin-noise")
    noise = _hypothesis("cabin-noise")
    annotate(noise)
    assert noise["what_is_known"] is None and noise["knowledge_note"] == LIMIT_ONLY
    assert noise["what_is_known_basis"] is None and noise["what_is_known_sources"] == []
    assert len(noise["evidence"]) == 1


# --------------------------------------------------------------------------- #
# Invariante 5 y la vista de la API
# --------------------------------------------------------------------------- #

def _verdict(client: TestClient) -> dict[str, Any]:
    """Lo que decide el motor: niveles, alertas, excursiones y el orden de las hipótesis."""
    crew = client.get("/api/crew").json()
    cabin = client.get("/api/habitat").json()
    decided: dict[str, Any] = {
        "crew": crew["crew"],
        "excursions": cabin["excursions"],
        "active": cabin["active"],
        "hypotheses": [
            {
                "kind": item["kind"], "title": item["title"], "affected": item["affected"],
                "excursion": item["excursion"], "checks": item["checks"],
                "countermeasures": [m["id"] for m in item.get("countermeasures", [])],
                "states": [step["state"] for step in item["flow"]],
            }
            for item in crew["correlation"]["hypotheses"]
        ],
    }
    for member in crew["crew"]:
        status = client.get("/api/status", params={"subject": member["subject"]}).json()
        decided[member["subject"]] = {
            key: status[key]
            for key in (
                "overall_level", "summary", "domains", "alerts", "recommendations",
                "rules_version", "predictions",
            )
        }
    return decided


def _scenario_with_oxygen_out_of_limit(client: TestClient) -> None:
    client.post("/api/simulate", params=CO2_SCENARIO)
    reference = client.get("/api/crew").json()["reference_time"]
    assert client.post("/api/habitat", json={
        "parameter": "cabin-ppo2", "value": 120.0, "effective": reference,
    }).status_code == 201


def test_the_engine_decides_the_same_with_and_without_what_was_read(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _scenario_with_oxygen_out_of_limit(client)
    with_sources = _verdict(client)
    assert with_sources["active"] and len(with_sources["hypotheses"]) == 2
    assert any(
        status["alerts"] for key, status in with_sources.items() if key.startswith("crew-")
    )
    crew = client.get("/api/crew").json()
    [oxygen] = [
        item for item in crew["correlation"]["hypotheses"]
        if item["excursion"]["parameter"] == "cabin-ppo2"
    ]
    assert "[V2 6003]" in oxygen["what_is_known"] and oxygen["knowledge_note"] is None
    assert oxygen["what_is_known_sources"][0]["quote"].startswith("Since physiological limits")
    assert [item["id"] for item in oxygen["evidence"]] == ["ochmo-tb-002", STANDARD]

    published = client.get("/api/habitat/parameters").json()
    # La luz va la primera; detrás, el agua y la microbiología (`test_habitat_water.py`).
    light = published["display_only"][0]
    assert light["key"] == LIGHT and light["limits"] == []
    assert "sin límite general" in light["limit_note"].lower()
    assert [item["requirement"] for item in light["reference_requirements"]] == (
        ["[V2 8051]"] * 5 + ["[V2 8055]"] * 2
    )
    cabin = client.get("/api/habitat").json()
    assert any(item["parameter"] == LIGHT for item in cabin["latest"])
    assert all(item["parameter"] != LIGHT for item in cabin["excursions"])

    # Sin nada de lo leído: ni texto de la norma ni requisitos junto a la luz.
    monkeypatch.setattr(context, "_STANDARD_KNOWLEDGE", {})
    monkeypatch.setitem(
        habitat.DISPLAY_ONLY, LIGHT,
        habitat._display_only(LIGHT, "Iluminación de cabina (iluminancia)", "lx", 0.0, 1e6),
    )
    without = _verdict(client)
    plain = client.get("/api/crew").json()["correlation"]["hypotheses"]
    assert all(
        item["what_is_known"] is None
        for item in plain if item["excursion"]["parameter"] == "cabin-ppo2"
    )
    assert client.get("/api/habitat/parameters").json()["display_only"][0][
        "reference_requirements"
    ] == []
    assert without == with_sources


def test_each_evaluated_limit_cites_its_document_by_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El ruido se leyó en el resumen técnico de acústica (OCHMO-TB-035), no en el del ECLSS: su
    parámetro cita esa ficha por identificador, la URL sale del registro y nada de esto entra en
    la huella de reglas (decimonovena ronda, U3, 2026-10-31)."""
    noise = habitat.parameter("cabin-noise")
    assert noise.source.id == habitat.NOISE_SOURCE.id == "ochmo-tb-035"
    others = {spec.source.id for key, spec in PARAMETERS.items() if key != "cabin-noise"}
    assert others == {habitat.LIMITS_SOURCE.id} == {"ochmo-tb-002"}
    brief = registry.get("ochmo-tb-035")
    assert brief.evidence_type == "technical_brief" and brief.date == "2023-10-06"
    assert not brief.unverified and brief.url is not None
    notes = brief.notes or ""
    for said in ("2026-10-31", "[V2 6077]", "85 dBA", "regardless of time duration", "Rev D"):
        assert said in notes, said
    # La API da la ficha con su URL del registro, para el ruido y para el catálogo.
    assert noise.to_dict()["source"] == {
        "id": "ochmo-tb-035", "title": habitat.NOISE_SOURCE.title, "read_on": "2026-10-31",
        "url": brief.url,
    }
    co2 = habitat.parameter("cabin-ppco2").to_dict()["source"]
    assert (co2["id"], co2["url"]) == ("ochmo-tb-002", registry.get("ochmo-tb-002").url)
    assert {"ochmo-tb-002", "ochmo-tb-035"} <= habitat.cited_refs()
    # El límite es el de antes y la ficha no entra en la huella de reglas.
    [limit] = noise.limits
    assert (limit.high, limit.requirement, limit.kind) == (85.0, "[V2 6077]", "health")
    assert "ochmo" not in json.dumps(versioning.rules()["habitat"], ensure_ascii=False)
    # Una ficha que no existe, o sin URL, no arranca el módulo.
    invented = replace(
        noise, limit_source=habitat.ReferenceSource("no-existe", "inventada", "2026-10-31"),
    )
    with pytest.raises(RegistryError, match="no está en el registro"):
        habitat._check_sources({"cabin-noise": invented})
    monkeypatch.setattr(habitat.registry, "get", lambda ref_id: SimpleNamespace(url=None))
    with pytest.raises(ValueError, match="no tiene URL"):
        habitat._check_sources({"cabin-noise": noise})
