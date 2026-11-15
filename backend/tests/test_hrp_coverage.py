"""Los riesgos del Human Research Program, todos, y qué hace EMMA con cada uno.

Lo que vigilan estas pruebas es que la cobertura no diga más de lo que EMMA tiene (invariante 6):
«cubierto» solo para el riesgo que cita un dominio en `HRP_RISKS`, y siempre para él (también
cuando lo que cita es un informe de evidencia, que no tiene dirección de página que buscar),
ningún dominio inexistente, ningún dominio de EMMA sin un riesgo del listado, cada ficha en el
registro, en una sola fila y la de cada página en la suya, y el total que declara el listado. Y
que el riesgo de cálculos renales, citado ahora por el dominio genitourinario y por la frase de su
región, no cambie lo que decide nada: el riesgo propio del dominio sigue siendo el mismo.
**Ninguna prueba sale a la red**: las páginas se leyeron el 2026-10-23.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import anatomy, text_guard
from app.advisor import countermeasures, recommendations
from app.api import descriptive
from app.core import display
from app.evidence import hrp_coverage, links, registry
from app.evidence.hrp_coverage import RISK_PAGE, CoverageError
from app.evidence.links import ADDITIONAL_HRP_RISKS, HRP_RISKS, evidence_for
from app.ingest.codes import CATALOG, COGNITION_KEYS, DESCRIPTIVE_ONLY, Domain

RAW: dict[str, Any] = json.loads(hrp_coverage.COVERAGE_PATH.read_text(encoding="utf-8"))
# Los riesgos que cita hoy cada dominio en `HRP_RISKS`, por la página del Roadmap de su fila.
COVERED = {
    99: "behavioral", 77: "bone", 179: "cardiovascular", 85: "immune", 176: "nutrition",
    96: "radiation", 105: "neuro-ocular",
}
RENAL_STONE_PAGE = 81
# Las dos filas que desde el 2026-10-31 nombran medidas descriptivas del catálogo, con ellas en el
# orden del catálogo: la sensoriomotora (dos pruebas funcionales de Standard Measures) y la de
# músculo y capacidad aeróbica (VO2 pico, prensión, masa magra por DXA y tracción isométrica).
SENSORIMOTOR_PAGE = 88
MUSCLE_AEROBIC_PAGE = 180
SENSORIMOTOR_KEYS = ("tandem-walk-correct-steps", "recovery-from-fall-time")
MUSCLE_AEROBIC_KEYS = (
    "vo2-peak", "grip-strength-right", "grip-strength-left", "dxa-lean-mass", "imtp-peak-force",
)
# Las páginas de los riesgos de salud conductual, de equipo y de sueño (U14, 2026-10-31).
BEHAVIORAL_PAGE, TEAM_PAGE, SLEEP_PAGE = 99, 101, 100
# Las tres afirmaciones de cohesión del cuestionario de fin de día, en el orden de la Tabla 3.
COHESION_KEYS = ("team-cohesion-cared", "team-cohesion-task-focus", "team-cohesion-shared-purpose")
# Cómo nombra cada analito del informe de cálculos renales el nombre largo de su código.
URINE_CHEMISTRY = (
    "calcium", "oxalate", "urate", "citrate", "ph", "sodium", "osmolality", "supersaturation",
)
# Los ocho, en el catálogo desde el 2026-10-26 (decisión del usuario), en el orden de la fuente.
URINE_KEYS = (
    "urine-calcium-24h", "urine-oxalate-24h", "urine-urate-24h", "urine-citrate-24h",
    "urine-ph-24h", "urine-sodium-24h", "urine-osmolality-24h", "urine-caox-supersaturation-24h",
)


def _row(raw: dict[str, Any], hrr_id: int) -> dict[str, Any]:
    return next(item for item in raw["risks"] if item["hrr_id"] == hrr_id)


def test_the_file_loads_and_lists_every_risk_the_roadmap_declares() -> None:
    raw = hrp_coverage.load()
    assert len(raw["risks"]) == 22
    assert "( of 22 )" in raw["listing"]["count_quote"]
    assert raw["read_on"] == "2026-10-23"


def test_covered_is_exactly_the_risk_each_domain_cites() -> None:
    raw = hrp_coverage.load()
    covered = {
        item["hrr_id"]: item["domains"][0] for item in raw["risks"] if item["coverage"] == "covered"
    }
    assert covered == COVERED
    for hrr_id, domain in covered.items():
        assert HRP_RISKS[Domain(domain)].id in _row(raw, hrr_id)["refs"]


def test_no_row_points_to_a_domain_emma_does_not_have() -> None:
    names = {str(item) for item in Domain}
    for item in hrp_coverage.load()["risks"]:
        assert set(item["domains"]) <= names, item["hrr_id"]
        if item["coverage"] == "outside":
            assert item["domains"] == []
        else:
            assert item["domains"], item["hrr_id"]


def test_every_domain_watches_at_least_one_risk_of_the_listing() -> None:
    watched = {name for item in hrp_coverage.load()["risks"] for name in item["domains"]}
    assert watched == {str(item) for item in Domain}


def test_a_risk_page_card_is_the_page_of_its_row() -> None:
    for item in hrp_coverage.load()["risks"]:
        for ref_id in item["refs"]:
            ref = registry.get(ref_id)
            if ref.evidence_type == "hrp_risk":
                assert ref.url == RISK_PAGE.format(item["hrr_id"]), ref_id


def test_the_texts_pass_the_language_filter() -> None:
    for item in hrp_coverage.load()["risks"]:
        for name in ("ridge_note", "reason"):
            assert text_guard.check(item[name]) == [], (item["hrr_id"], name)
    payload = hrp_coverage.payload()
    for text in (payload["note"], payload["summary"], payload["element_basis"],
                 payload["ridge_note"], payload["pending_note"], payload["in_catalog_note"]):
        assert text_guard.check(text) == []
    assert text_guard.check(links.RENAL_STONE.relevance or "") == []
    assert text_guard.check(anatomy.RENAL_STONE_SOURCE.relevance or "") == []


def test_the_payload_is_what_the_file_says_and_counts_add_up() -> None:
    payload = hrp_coverage.payload()
    assert payload["count"] == 22 == sum(payload["counts"].values())
    # Desde el 2026-10-31 la fila sensoriomotora es «en parte» (dos pruebas descriptivas); la de
    # equipo sigue «fuera del alcance»: registrar la cohesión no es vigilar el riesgo (U14).
    assert payload["counts"] == {"covered": 7, "partial": 8, "outside": 7}
    assert str(payload["counts"]["outside"]) in payload["summary"]
    renal = next(item for item in payload["risks"] if item["hrr_id"] == RENAL_STONE_PAGE)
    assert renal["coverage"] == "partial"
    assert renal["coverage_display"] == hrp_coverage.COVERAGE["partial"]
    assert [entry["key"] for entry in renal["domains"]] == ["genitourinary"]
    # El alcance de cada dominio es la frase del marco de ExMC, leída de su sitio.
    assert renal["domains"][0]["scope"] == links.amcl_alignment(Domain.GENITOURINARY)
    assert renal["url"] == RISK_PAGE.format(RENAL_STONE_PAGE)
    assert {ref["id"] for ref in renal["refs"]} == {
        "hrp-risk-renal-stone", "hrp-renal-stone-evidence-report",
        "hrp-renal-stone-conops-appendix-b",
    }
    assert [item["key"] for item in renal["in_catalog"]] == list(URINE_KEYS)
    assert payload["in_catalog_note"] == hrp_coverage.IN_CATALOG_NOTE
    assert renal["ridge"]["category"] == "gravity" and renal["ridge"]["basis"] == "source"
    assert payload["listing"]["source"]["id"] == "hrr-risks"
    # El listado no declara fecha: la ficha la lista como pendiente, no se rellena.
    assert "date" in payload["listing"]["source"]["unverified"]


def test_each_row_says_its_coverage_with_its_domains_by_name() -> None:
    rows = {item["hrr_id"]: item for item in hrp_coverage.payload()["risks"]}
    assert rows[99]["coverage_statement"] == "cubierto por el dominio conductual"
    assert rows[81]["coverage_statement"] == "en parte, por el dominio genitourinario"
    assert rows[180]["coverage_statement"] == (
        "en parte, por los dominios cardiovascular y musculoesquelético"
    )
    assert rows[88]["coverage_statement"] == "en parte, por el dominio musculoesquelético"
    assert rows[82]["coverage_statement"] == "fuera del alcance de EMMA"
    for item in rows.values():
        assert text_guard.check(item["coverage_statement"]) == []


def test_the_urine_analytes_of_the_renal_risk_are_in_the_catalog_and_out_of_pending() -> None:
    """Los ocho analitos de orina del informe están en el catálogo, y la fila lo dice.

    Hasta el 2026-10-26 eran pendientes sin código. Cada uno sale de `pending` y entra en
    `in_catalog`, con su clave; el nombre largo de su código nombra el analito y la orina. Lo que
    queda pendiente (la sobresaturación de la brushita) no está en el catálogo.
    """
    renal = _row(hrp_coverage.load(), RENAL_STONE_PAGE)
    assert renal["in_catalog"] == list(URINE_KEYS)
    for key, word in zip(URINE_KEYS, URINE_CHEMISTRY, strict=True):
        display = CATALOG[key].display.lower()
        assert "urine" in display and re.search(rf"\b{word}\b", display), key
        assert key in DESCRIPTIVE_ONLY, key
        assert CATALOG[key].domain is Domain.GENITOURINARY, key
    assert renal["pending"] == [
        "sobresaturación calculada de la brushita (fosfato cálcico) en orina de 24 horas"
    ]
    displays = [code.display.lower() for code in CATALOG.values()]
    assert not any(
        "brushite" in display or "phosphate dihydrate" in display for display in displays
    )
    # Ninguna otra fila tiene medidas del catálogo salvo las dos de sensoriomotor y músculo y la
    # de salud conductual (la batería Cognition), desde el 2026-10-31, con su propia prueba.
    others = [
        item for item in hrp_coverage.load()["risks"]
        if item["hrr_id"] not in (
            RENAL_STONE_PAGE, SENSORIMOTOR_PAGE, MUSCLE_AEROBIC_PAGE, BEHAVIORAL_PAGE,
        )
    ]
    assert all(item["in_catalog"] == [] for item in others)


def test_the_sensorimotor_risk_is_partial_by_two_descriptive_functional_tests() -> None:
    """Hasta el 2026-10-31 la fila decía «fuera del alcance»: ningún indicador medía el equilibrio
    ni la coordinación. Las dos pruebas funcionales de Standard Measures la pasan a «en parte»
    por el dominio musculoesquelético, donde se agrupan sin que el estado las lea; lo que sigue
    sin medirse (la posturografía, el mareo) queda en `pending`, sin código."""
    row = _row(hrp_coverage.load(), SENSORIMOTOR_PAGE)
    assert (row["coverage"], row["domains"]) == ("partial", ["musculoskeletal"])
    assert row["in_catalog"] == list(SENSORIMOTOR_KEYS)
    for key in SENSORIMOTOR_KEYS:
        assert key in DESCRIPTIVE_ONLY and CATALOG[key].domain is Domain.MUSCULOSKELETAL, key
    assert "vestibular" in row["reason"] and "posturografía" in row["reason"]
    assert any("Sensory Organization Test" in item for item in row["pending"])
    assert any("mareo" in item for item in row["pending"])
    served = next(
        item for item in hrp_coverage.payload()["risks"] if item["hrr_id"] == SENSORIMOTOR_PAGE
    )
    assert [item["key"] for item in served["in_catalog"]] == list(SENSORIMOTOR_KEYS)
    for item in served["in_catalog"]:
        assert item["descriptive_only"] is True and item["is_standard_code"] is False
        assert item["descriptive_display"] == hrp_coverage.DESCRIPTIVE_DISPLAY
        assert item["unit_display"] == display.unit(CATALOG[item["key"]].unit)


def test_the_muscle_and_aerobic_risk_names_its_five_descriptive_measures() -> None:
    """La fila nombra lo que el catálogo tiene de la fuente: VO2 pico y prensión (de antes) y, desde
    el 2026-10-31, la masa magra por DXA y la tracción isométrica; el par isocinético de rodilla
    sigue pendiente, sin código, porque su protocolo no es público."""
    row = _row(hrp_coverage.load(), MUSCLE_AEROBIC_PAGE)
    assert row["coverage"] == "partial"
    assert row["in_catalog"] == list(MUSCLE_AEROBIC_KEYS)
    for key in MUSCLE_AEROBIC_KEYS:
        assert key in DESCRIPTIVE_ONLY, key
        assert str(CATALOG[key].domain) in row["domains"], key
    assert any("isocinético" in item for item in row["pending"])
    displays = [code.display.lower() for code in CATALOG.values()]
    assert not any("isokinetic" in item for item in displays)
    served = next(
        item for item in hrp_coverage.payload()["risks"] if item["hrr_id"] == MUSCLE_AEROBIC_PAGE
    )
    standard = {item["key"]: item["is_standard_code"] for item in served["in_catalog"]}
    assert standard == {
        "vo2-peak": True, "grip-strength-right": True, "grip-strength-left": True,
        "dxa-lean-mass": False, "imtp-peak-force": False,
    }


def test_descriptive_cohesion_items_do_not_turn_the_team_risk_into_watched() -> None:
    """La fila del riesgo de equipo (U14, 2026-10-31) sigue «fuera del alcance»: las tres
    afirmaciones de cohesión son descriptivas, el estado no las lee y no vigilan nada; constan en
    el motivo. La de salud conductual lleva las nueve pruebas de la batería Cognition que su
    informe nombra, sin cambiar lo que cita el dominio ni su cobertura «cubierto»."""
    team = _row(hrp_coverage.load(), TEAM_PAGE)
    assert (team["coverage"], team["domains"]) == ("outside", [])
    assert team["in_catalog"] == []
    for key in COHESION_KEYS:
        assert key in team["reason"], key
        assert key in DESCRIPTIVE_ONLY and CATALOG[key].domain is Domain.BEHAVIORAL, key
        assert "team cohesion" in CATALOG[key].display.lower(), key
    assert team["pending"] and all("cooperación" in line for line in team["pending"])
    behavioral = _row(hrp_coverage.load(), BEHAVIORAL_PAGE)
    assert behavioral["coverage"] == "covered"
    assert set(behavioral["in_catalog"]) == set(COGNITION_KEYS)
    assert all(key.startswith("cognition-") for key in behavioral["in_catalog"])
    assert "pvt" not in " ".join(behavioral["in_catalog"])
    # El riesgo de sueño nombra escalas de somnolencia y de fatiga sin sus puntos: pendientes.
    sleep = _row(hrp_coverage.load(), SLEEP_PAGE)
    assert [line.split(":")[0] for line in sleep["pending"]] == [
        "escala de somnolencia de Karolinska (KSS)", "escala de fatiga de Samn-Perelli",
    ]
    assert sleep["in_catalog"] == []
    rows = {item["hrr_id"]: item for item in hrp_coverage.payload()["risks"]}
    assert rows[TEAM_PAGE]["coverage_statement"] == hrp_coverage.COVERAGE["outside"]
    for item in rows[BEHAVIORAL_PAGE]["in_catalog"]:
        assert item["descriptive_only"] is True and item["is_standard_code"] is False
        assert item["descriptive_display"] == hrp_coverage.DESCRIPTIVE_DISPLAY
    # Lo que cita cada dominio no se movió: el conductual sigue citando su riesgo, y solo ese.
    assert HRP_RISKS[Domain.BEHAVIORAL].id == "hrp-risk-behavioral"
    assert Domain.BEHAVIORAL not in ADDITIONAL_HRP_RISKS


def test_the_served_analytes_say_they_are_descriptive_with_their_code() -> None:
    row = next(
        item for item in hrp_coverage.payload()["risks"] if item["hrr_id"] == RENAL_STONE_PAGE
    )
    for item in row["in_catalog"]:
        code = CATALOG[item["key"]]
        assert (item["code"], item["unit"], item["display_es"]) == (
            code.code, code.unit, code.display_es,
        )
        assert item["descriptive_only"] is True
        assert item["descriptive_display"] == hrp_coverage.DESCRIPTIVE_DISPLAY
        assert item["is_standard_code"] is (item["key"] != "urine-caox-supersaturation-24h")
        assert text_guard.check(item["descriptive_display"]) == []
        # El sistema, con las mismas palabras que el panel de descriptivos.
        assert item["system_display"] == descriptive.SYSTEM_DISPLAY[code.system]
        assert item["unit_display"] == display.unit(code.unit)


def test_recommendations_keep_citing_what_they_cited() -> None:
    """El detalle de una alerta rotula esa evidencia «riesgo del dominio»: la de cálculos, no."""
    cited = [item.id for item in links.countermeasure_evidence(Domain.GENITOURINARY)]
    assert cited == ["hrr-urinary-retention"]
    for domain in Domain:
        assert links.countermeasure_evidence(domain) == [
            item for item in evidence_for(domain)
            if item not in ADDITIONAL_HRP_RISKS.get(domain, ())
        ]


def test_the_recommendations_of_the_domain_do_not_carry_the_renal_risk() -> None:
    measure = next(
        item for item in countermeasures.library().values()
        if item.domain is Domain.GENITOURINARY and item.protocol_ref is None
    )
    assert "hrp-risk-renal-stone" not in {cited.id for cited in recommendations._evidence(measure)}


def test_what_load_gives_cannot_change_what_is_served() -> None:
    hrp_coverage.load()["risks"].clear()
    assert len(hrp_coverage.load()["risks"]) == 22


def test_the_renal_stone_risk_is_cited_without_changing_the_domain_risk() -> None:
    # El riesgo propio del dominio sigue siendo la retención urinaria.
    assert HRP_RISKS[Domain.GENITOURINARY].id == "hrr-urinary-retention"
    cited = [item.id for item in evidence_for(Domain.GENITOURINARY)]
    assert cited == ["hrr-urinary-retention", "hrp-risk-renal-stone"]
    assert [item.id for item in ADDITIONAL_HRP_RISKS[Domain.GENITOURINARY]] == [
        "hrp-risk-renal-stone"
    ]
    # Ningún otro dominio cambia lo que cita.
    for domain in Domain:
        if domain is not Domain.GENITOURINARY:
            assert domain not in ADDITIONAL_HRP_RISKS


def test_the_bladder_phrase_carries_the_renal_stone_report() -> None:
    bladder = next(region for region in anatomy.REGIONS if region.key == "bladder")
    assert "cálculos" in bladder.note
    shown = bladder.to_dict()["note_refs"]
    assert [item["id"] for item in shown] == ["hrp-renal-stone-evidence-report"]
    # Las demás regiones no llevan fichas en su frase.
    for region in anatomy.REGIONS:
        if region.key != "bladder":
            assert region.to_dict()["note_refs"] == []


def test_the_route_serves_the_coverage(client: TestClient) -> None:
    response = client.get("/api/risks/hrp-coverage")
    assert response.status_code == 200
    body = response.json()
    assert body == json.loads(json.dumps(hrp_coverage.payload()))
    # `/risks` sigue siendo un riesgo por dominio.
    assert client.get("/api/risks").json()["count"] == len(Domain)


# --------------------------------------------------------------------------- #
# Lo que `validate` rechaza: cada defensa, con su fichero roto
# --------------------------------------------------------------------------- #


def _set(path: list[str], value: Any) -> Callable[[dict[str, Any]], None]:
    def change(raw: dict[str, Any]) -> None:
        node: Any = raw
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    return change


def _risk(hrr_id: int, field: str, value: Any) -> Callable[[dict[str, Any]], None]:
    def change(raw: dict[str, Any]) -> None:
        _row(raw, hrr_id)[field] = value

    return change


def _drop_row(hrr_id: int) -> Callable[[dict[str, Any]], None]:
    def change(raw: dict[str, Any]) -> None:
        raw["risks"] = [item for item in raw["risks"] if item["hrr_id"] != hrr_id]

    return change


def _duplicate_row(raw: dict[str, Any]) -> None:
    raw["risks"][1] = copy.deepcopy(raw["risks"][0])


def _extra_field(raw: dict[str, Any]) -> None:
    raw["risks"][0]["inventado"] = 1


def _missing_field(raw: dict[str, Any]) -> None:
    del raw["risks"][0]["pending"]


def _bone_row_without_its_card(raw: dict[str, Any]) -> None:
    """La fila del riesgo que cita el dominio óseo, sin su ficha y rebajada a «en parte»."""
    row = _row(raw, 77)
    row["refs"], row["coverage"] = [], "partial"


def _bone_row_moved(raw: dict[str, Any]) -> None:
    """La página del riesgo que cita el dominio óseo ya no está en el listado."""
    row = _row(raw, 77)
    row["hrr_id"], row["refs"], row["coverage"] = 9999, [], "partial"


def _renal_row_on_nutrition(raw: dict[str, Any]) -> None:
    """La fila de los cálculos, de nutrición en vez de genitourinaria, y sin sus analitos."""
    row = _row(raw, 81)
    row["domains"], row["in_catalog"] = ["nutrition"], []


def _report_on_another_row(raw: dict[str, Any]) -> None:
    """El informe de cálculos renales, copiado en la fila de condiciones médicas."""
    _row(raw, 95)["refs"].append("hrp-renal-stone-evidence-report")


def _nutrition_row_without_its_report(raw: dict[str, Any]) -> None:
    """La fila del riesgo que cita la nutrición por su informe, sin el informe y rebajada."""
    row = _row(raw, 176)
    row["refs"], row["coverage"] = ["hrr-risk-food-nutrition"], "partial"


def _sans_row_outside(raw: dict[str, Any]) -> None:
    """La fila del riesgo que cita el dominio neuro-ocular, sacada del alcance de EMMA."""
    row = _row(raw, 105)
    row["coverage"], row["domains"], row["refs"] = "outside", [], []


def _sans_report_on_the_nutrition_row(raw: dict[str, Any]) -> None:
    """El informe de SANS, movido a una fila «cubierta» por otro dominio."""
    sans = _row(raw, 105)
    sans["coverage"], sans["refs"] = "partial", []
    _row(raw, 176)["refs"].append("hrp-sans-evidence-report")


def _sans_report_on_the_sensorimotor_row(raw: dict[str, Any]) -> None:
    """El informe de SANS en la fila sensoriomotora, dicha «cubierta» por el dominio neuro-ocular,
    y la de SANS fuera del alcance (tercera revisión de código: así pasaba)."""
    sans = _row(raw, 105)
    sans["coverage"], sans["domains"], sans["refs"] = "outside", [], []
    other = _row(raw, 88)
    other["coverage"], other["domains"] = "covered", ["neuro-ocular"]
    other["refs"] = ["hrp-sans-evidence-report"]


def _retention_card_on_the_sans_row(raw: dict[str, Any]) -> None:
    """La ficha que cita el dominio genitourinario (una condición médica, sin fila propia), en la
    fila de SANS, que está «cubierta» por el dominio neuro-ocular: no la cubre él."""
    _row(raw, 105)["refs"].append("hrr-urinary-retention")


def _same_card_on_two_rows(raw: dict[str, Any]) -> None:
    """Una ficha que no es del Roadmap (un estudio de OSDR), en dos filas."""
    _row(raw, 80)["refs"].append("osd-288")
    _row(raw, 85)["refs"].append("osd-288")


def _no_domain_watches_bone(raw: dict[str, Any]) -> None:
    for item in raw["risks"]:
        if "bone" in item["domains"]:
            item["domains"] = [name for name in item["domains"] if name != "bone"]
            if not item["domains"]:
                item["coverage"], item["refs"] = "outside", []


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (_risk(81, "coverage", "covered"), "cita otro"),
        (_risk(99, "domains", ["behavioural"]), "dominio que EMMA no tiene"),
        (_risk(81, "domains", ["genitourinary", "genitourinary"]), "repetido"),
        (_risk(99, "domains", ["behavioral", "immune"]), "solo uno"),
        (_risk(80, "domains", []), "sin dominio"),
        (_risk(82, "domains", ["immune"]), "fuera del alcance"),
        (_risk(82, "coverage", "total"), "cobertura desconocida"),
        (_risk(99, "refs", ["hrp-risk-immune"]), "página de otro riesgo"),
        (_risk(81, "refs", ["no-existe"]), "sin registrar"),
        (_risk(81, "refs", "hrp-risk-renal-stone"), "lista de fichas"),
        (_risk(81, "status", "retired"), "estado desconocido"),
        (_risk(81, "last_published", "05/13/25"), "ISO"),
        # Con forma ISO pero sin existir: la interfaz no la puede enseñar.
        (_risk(81, "last_published", "2025-13-05"), "ISO"),
        (_risk(81, "pending", ["Sin duda el oxalato."]), "filtro de lenguaje"),
        (_bone_row_without_its_card, "no dice cubierto"),
        (_bone_row_moved, "no está en el listado"),
        (_risk(81, "ridge", "vacuum"), "RIDGE desconocido"),
        (_risk(81, "ridge_basis", "intuición"), "eje RIDGE"),
        (_risk(81, "reason", "  "), "vacío"),
        (_risk(81, "hrp_element", ""), "vacío"),
        (_risk(81, "hrr_id", 0), "número de la página"),
        (_risk(81, "hrr_id", True), "número de la página"),
        (_risk(81, "pending", [""]), "analitos pendientes"),
        (_risk(81, "reason", "Confirma el diagnóstico de litiasis."), "filtro de lenguaje"),
        (_risk(81, "ridge_note", "Sin duda es por la gravedad."), "filtro de lenguaje"),
        # El riesgo que el dominio cita además del suyo no puede quedar sin ese dominio en su fila
        # (sin sus analitos del catálogo, que son del dominio y lo dirían antes).
        (_renal_row_on_nutrition, "no lo nombra"),
        # Los analitos del catálogo de una fila: claves suyas, una vez, de un dominio de la fila.
        (_risk(81, "in_catalog", "urine-calcium-24h"), "claves del catálogo"),
        (_risk(81, "in_catalog", [["urine-calcium-24h"]]), "claves del catálogo"),
        (_risk(81, "in_catalog", ["urine-calcium"]), "no es un indicador del catálogo"),
        (_risk(81, "in_catalog", ["urine-ph-24h", "urine-ph-24h"]), "repetido"),
        (_risk(81, "in_catalog", ["calcium"]), "dominio que la fila no nombra"),
        (_risk(82, "in_catalog", ["urine-ph-24h"]), "dominio que la fila no nombra"),
        # El informe de descompresión e hipoxia va en sus dos filas; otro informe, en una sola.
        (_risk(84, "refs", ["hrp-dcs-hypoxia-evidence-report"]), "no es el de este riesgo"),
        # Y está en las dos: quitarlo de una deja esa fila sin lo que su página enlaza.
        (_risk(173, "refs", []), "falta en la fila 173"),
        (_risk(173, "refs", ["hrp-eva-evidence-report"]), "no es el de este riesgo"),
        (_risk(81, "refs", ["hrp-renal-stone-evidence-report"]), "no lo nombra"),
        # Un riesgo citado por su dominio no se rebaja a «en parte».
        (_risk(77, "coverage", "partial"), "no dice cubierto"),
        # También cuando lo que cita el dominio es un informe, sin dirección de página que buscar.
        (_nutrition_row_without_its_report, "no está en el listado"),
        (_sans_row_outside, "no está en el listado"),
        (_risk(105, "coverage", "partial"), "no dice cubierto"),
        (_retention_card_on_the_sans_row, "no dice cubierto por él"),
        # Un informe va en la fila de su riesgo, y en ninguna otra.
        (_sans_report_on_the_nutrition_row, "no es el de este riesgo"),
        (_sans_report_on_the_sensorimotor_row, "no es el de este riesgo"),
        (_report_on_another_row, "no es el de este riesgo"),
        # Una ficha respalda una fila, y una vez.
        (_same_card_on_two_rows, "dos filas"),
        # Un valor que no es texto se rechaza como los demás, no con `TypeError`.
        (_risk(81, "status", ["active"]), "estado desconocido"),
        (_risk(81, "ridge", ["gravity"]), "RIDGE desconocido"),
        (_risk(81, "ridge_basis", {"source": 1}), "eje RIDGE"),
        (_risk(81, "domains", [["genitourinary"]]), "dominio que EMMA no tiene"),
        (_risk(81, "refs", [["hrp-risk-renal-stone"]]), "lista de fichas"),
        (_risk(81, "refs", ["hrp-risk-renal-stone", "hrp-risk-renal-stone"]), "ficha repetida"),
        (_risk(81, "pending", ["pH de la orina", "pH de la orina"]), "pendiente repetido"),
        (_drop_row(78), "el listado declara"),
        (_duplicate_row, "repetida"),
        (_extra_field, "desconocidos"),
        (_missing_field, "faltan"),
        (_no_domain_watches_bone, "dominios sin ningún riesgo"),
        (_set(["read_on"], "ayer"), "read_on"),
        (_set(["read_on"], "2026-02-30"), "read_on"),
        (_set(["listing", "updates"], "Sin duda no se actualiza."), "filtro de lenguaje"),
        (_set(["listing", "count_quote"], "Risks 1 - 22"), "total que declara"),
        (_set(["listing", "ref"], "no-existe"), "sin registrar"),
        (_set(["listing", "updates"], ""), "vacío"),
        (_set(["ridge_source"], "no-existe"), "sin registrar"),
    ],
)
def test_the_coverage_rejects_what_breaks_its_contract(
    change: Callable[[dict[str, Any]], None], reason: str
) -> None:
    broken = copy.deepcopy(RAW)
    change(broken)
    with pytest.raises(CoverageError, match=reason):
        hrp_coverage.validate(broken)


def test_the_unbroken_file_passes_the_same_validation() -> None:
    assert hrp_coverage.validate(copy.deepcopy(RAW))["risks"] == RAW["risks"]


# Los informes cuya portada no lleva un título «Risk of …»: el anexo de operaciones del renal y el
# libro de nutrición que la página de evidencias rotula «Evidence Report-Nutrition».
NOT_TITLED_AS_A_RISK = {"hrp-renal-stone-conops-appendix-b", "hrp-nutrition-human-adaptation-2020"}


def test_every_evidence_report_sits_on_the_row_of_its_risk() -> None:
    """Cada informe de `REPORT_RISK` es una ficha de informe registrada, cuyo título nombra un
    riesgo, y está en la fila de los riesgos que lo enlazan; y no hay en el fichero un informe sin
    riesgo."""
    for ref_id, rows in hrp_coverage.REPORT_RISK.items():
        card = registry.get(ref_id)
        assert card.evidence_type == "evidence_report", ref_id
        assert ("Risk of" in card.title) is (ref_id not in NOT_TITLED_AS_A_RISK), ref_id
        for hrr_id in rows:
            assert ref_id in _row(RAW, hrr_id)["refs"], ref_id
    reports = {
        ref_id for item in RAW["risks"] for ref_id in item["refs"]
        if registry.get(ref_id).evidence_type == "evidence_report"
    }
    assert reports == set(hrp_coverage.REPORT_RISK)
    # Solo el de descompresión e hipoxia está en dos filas: lo enlazan las dos páginas.
    shared = {ref_id for ref_id, rows in hrp_coverage.REPORT_RISK.items() if len(rows) > 1}
    assert shared == {"hrp-dcs-hypoxia-evidence-report"}
    assert hrp_coverage.REPORT_RISK["hrp-dcs-hypoxia-evidence-report"] == (168, 173)


# Lo que nombra la portada de cada informe leído el 2026-10-26 como su elemento (`None`: ninguno),
# copiado de la portada. La cita de la ficha (`source`) lo lleva cuando la portada lo da.
COVER_ELEMENT: dict[str, str | None] = {
    "hrp-ivd-evidence-book": "Human Health Countermeasures",
    "hrp-bmed-evidence-report": "Human Factors and Behavioral Performance",
    "hrp-medical-conditions-evidence-report": "Exploration Medical Capabilities",
    "hrp-microhost-evidence-report": "Human Health Countermeasures",
    "hrp-dust-evidence-report": "Space Human Factors and Habitability",
    "hrp-hsia-evidence-report": "Human Factors and Behavioral Performance",
    "hrp-sensorimotor-evidence-report": "Human Health Countermeasures",
    "hrp-bone-fracture-evidence-report": "Human Health Countermeasures",
    "hrp-cardiovascular-evidence-report": "Human Health and Countermeasures",
    "hrp-immune-evidence-report": "Human Health Countermeasures",
    "hrp-dynamic-loads-evidence-report": "Human Factors and Behavioral Performance",
    "hrp-team-evidence-report": "Behavioral Health and Performance",
    "hrp-pharm-evidence-report-2023": "Exploration Medical Capability (ExMC)",
    "hrp-pharm-evidence-report-2011": "Human Health Countermeasures",
    "hrp-eva-evidence-report": None,
    "hrp-dcs-hypoxia-evidence-report": None,
    "hrp-muscle-aerobic-evidence-report": "Human Health Countermeasures",
    "hrp-food-nutrition-evidence-report-2024": "Human Health Countermeasures",
    "hrp-nutrition-human-adaptation-2020": None,
    "hrp-sleep-evidence-report": "Behavioral Health and Performance",
    "hrp-carcinogenesis-evidence-report": "Space Radiation",
    "hrp-sans-evidence-report-2022": "Human Health Countermeasures",
    "hrp-renal-stone-conops-appendix-b": "Exploration Medical Capability (ExMC)",
}
# Las portadas cuyo elemento no es el que da hoy la página de su riesgo, como lo dice
# `ELEMENT_BASIS` (además de las que no nombran ninguno).
ELEMENT_DIFFERS = {
    "hrp-dust-evidence-report", "hrp-team-evidence-report", "hrp-sleep-evidence-report",
    "hrp-pharm-evidence-report-2011", "hrp-cardiovascular-evidence-report",
}


def _page_element(hrp_element: str) -> str:
    """«Human Health Countermeasures (HHC)» → «Human Health Countermeasures»."""
    return re.sub(r"\s*\([^)]*\)$", "", hrp_element)


def test_each_cover_names_the_element_its_card_cites_and_the_differences_are_declared() -> None:
    """Las portadas, leídas: la cita de cada ficha lleva el elemento que nombra, y las que no
    coinciden con la página de su riesgo son las que dice `ELEMENT_BASIS`, ni una más."""
    assert set(COVER_ELEMENT) == set(hrp_coverage.REPORT_RISK) - {
        "hrp-sans-evidence-report", "hrp-food-system-evidence-report",
        "hrp-renal-stone-evidence-report",
    }
    differs: set[str] = set()
    for ref_id, element in COVER_ELEMENT.items():
        card = registry.get(ref_id)
        assert card.notes is not None and "2026-10-26" in card.notes, ref_id
        assert card.date is None or card.date[:4] in card.source, ref_id
        if element is None:
            continue
        assert element in card.source, ref_id
        for hrr_id in hrp_coverage.REPORT_RISK[ref_id]:
            page = _page_element(_row(RAW, hrr_id)["hrp_element"])
            # «Exploration Medical Capabilities» de una portada es la «Capability» de la página.
            if not _page_element(element).startswith(page.rstrip("y")):
                differs.add(ref_id)
    assert differs == ELEMENT_DIFFERS
    basis = hrp_coverage.ELEMENT_BASIS
    for name in ("Space Human Factors and Habitability", "Behavioral Health and Performance",
                 "Human Health and Countermeasures", "2026-10-26"):
        assert name in basis


def test_the_sans_row_carries_both_reports_and_the_domain_keeps_citing_2017() -> None:
    row = _row(RAW, 105)
    assert row["refs"] == ["hrp-sans-evidence-report", "hrp-sans-evidence-report-2022"]
    assert HRP_RISKS[Domain.NEURO_OCULAR].id == "hrp-sans-evidence-report"
    assert registry.get("hrp-sans-evidence-report").date == "2017-11-30"
    newer = registry.get("hrp-sans-evidence-report-2022")
    assert newer.date == "2022-04-07"
    # La versión de 2022 no repite el cuestionario de visión del que EMMA lee el cambio de visión.
    assert newer.notes is not None and "«questionnaire» no aparece" in newer.notes
    assert "cuestionario de visión" in row["reason"]
