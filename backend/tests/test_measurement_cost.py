"""Las dimensiones del coste de medir (`app/ingest/cost.py`, `GET /api/measurement-cost`).

Vocabulario cerrado, cada clase con la regla y el texto que la sostienen, y lo que no se deduce
queda sin clasificar y se cuenta. Desde la undécima ronda, las reglas de muestras citan la frase
leída y enseñan lo leído que las matiza. Nada de esto cambia qué se mide ni el veredicto.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.advisor import check_cost
from app.api.routes import new_store, reset_store
from app.core import versioning
from app.core.config import Settings, get_settings
from app.evidence import mission_profiles, registry
from app.ingest import cost as cost_module
from app.ingest.codes import CATALOG, DENSITOMETRY_KEYS, RENAL_URINE_CHEMISTRY
from app.ingest.cost import (
    DIMENSIONS,
    UNCLASSIFIED,
    UNCLASSIFIED_DISPLAY,
    classify,
    cost,
    costs,
    dimensions,
    summary,
)
from app.main import app

RAW: dict[str, dict[str, Any]] = {
    "a": {"mode": "continuous-passive", "equipment": "wearable"},
    "b": {"mode": "laboratory", "equipment": "extracción de sangre y analizador"},
    "c": {"mode": "derived", "equipment": "cálculo"},
}
BLOOD = "extracción de sangre y analizador"
ULTRASOUND = "ecógrafo y operador entrenado"
# Escritas a mano, no con el filtro de la regla: un indicador nuevo con otro rótulo de equipo
# tiene que hacer fallar la prueba, no quedarse fuera de las dos a la vez.
SCANS = {"onsd-left", "onsd-right", "ijv-csa-left", "ijv-csa-right", "bladder-volume"}
RED_SERIES = {"erythrocytes", "hemoglobin", "hematocrit", "mcv", "mch", "mchc", "platelets"}
# Decimoctava ronda (U18), también escritas a mano: lo que se lleva puesto, el actígrafo, la
# fórmula leucocitaria y el dosímetro.
WORN = {"heart-rate", "hrv-sdnn", "hrv-rmssd", "respiratory-rate"}
ACTIGRAPHY = {"sleep-duration", "sleep-efficiency", "circadian-shift"}
WHITE_CELLS = {
    "leukocytes", "lymphocytes", "neutrophils", "lymphocytes-percent", "neutrophils-percent",
}
DOSE = {"absorbed-dose-rate", "cumulative-dose"}
RULE: dict[str, Any] = {
    "id": "r1", "match": {"mode": "continuous-passive"},
    "set": {"processing": "on-device"}, "basis": "clase «continuo y pasivo»",
}


def _searched_by(notes: list[dict[str, Any]], dimension: str) -> dict[str, dict[str, Any]]:
    """Lo buscado de cada indicador sobre una dimensión (un indicador puede tener varias notas)."""
    found: dict[str, dict[str, Any]] = {}
    for item in notes:
        if dimension in item["dimensions"]:
            for key in item["keys"]:
                assert key not in found, (key, dimension)
                found[key] = item
    return found


def _rule(ident: str) -> dict[str, Any]:
    return next(rule for rule in summary()["rules"] if rule["id"] == ident)


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def test_every_indicator_has_the_three_dimensions_within_the_vocabulary() -> None:
    assert set(dimensions()) == set(CATALOG)
    for key, item in dimensions().items():
        assert set(item) == set(DIMENSIONS), key
        for name, entry in item.items():
            allowed = {**DIMENSIONS[name]["values"], UNCLASSIFIED: UNCLASSIFIED_DISPLAY}
            assert entry["display"] == allowed[entry["value"]], (key, name)


def test_a_classification_always_says_where_it_comes_from() -> None:
    rules = {rule["id"]: rule["basis"] for rule in cost_module._rules()}
    for key, item in dimensions().items():
        for name, entry in item.items():
            if entry["value"] == UNCLASSIFIED:
                assert entry["basis"] is None and entry["rule"] is None, (key, name)
                assert entry["inherited_from"] is None, (key, name)
            elif entry["inherited_from"] is not None:
                # Heredado: dice de qué entradas, por qué se enlazan y la regla de ellas.
                inputs = costs()[key]["inputs"]
                assert entry["inherited_from"] == inputs, (key, name)
                assert costs()[key]["inputs_basis"] in entry["basis"], (key, name)
                assert all(
                    dimensions()[source][name]["value"] == entry["value"] for source in inputs
                ), (key, name)
            else:
                assert entry["basis"] == rules[entry["rule"]], (key, name)
                assert entry["basis"].strip(), (key, name)


def test_what_no_rule_reaches_stays_unclassified() -> None:
    found = classify(RAW, [RULE])
    assert found["a"]["processing"]["value"] == "on-device"
    assert found["a"]["processing"]["rule"] == "r1"
    assert found["a"]["result"]["value"] == UNCLASSIFIED
    assert all(entry["value"] == UNCLASSIFIED for entry in found["b"].values())
    assert all(entry["display"] == UNCLASSIFIED_DISPLAY for entry in found["c"].values())


def test_a_rule_needs_every_condition_it_names() -> None:
    both = {**RULE, "match": {"mode": "continuous-passive", "equipment": ["wearable", "otro"]}}
    assert classify(RAW, [both])["a"]["processing"]["value"] == "on-device"
    wrong = {**RULE, "match": {"mode": "laboratory", "keys": ["a", "b"]}}
    found = classify(RAW, [wrong])
    assert found["b"]["processing"]["value"] == "on-device"
    assert found["a"]["processing"]["value"] == UNCLASSIFIED


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"set": {"processing": "en órbita"}}, "fuera del vocabulario"),
        ({"set": {"processing": UNCLASSIFIED}}, "fuera del vocabulario"),
        ({"set": {"where": "on-device"}}, "dimensión desconocida"),
        ({"set": {}}, "sin `set`"),
        ({"basis": "  "}, "sin `basis`"),
        ({"basis": None}, "sin `basis`"),
        ({"match": {}}, "sin `match`"),
        ({"match": {"domain": "immune"}}, "campos desconocidos"),
        ({"match": {"mode": "guessed"}}, "clase de medida desconocida"),
        ({"match": {"keys": ["no-existe"]}}, "no están en el coste"),
        ({"match": {"mode": "periodic-invasive"}}, "no alcanza a ningún indicador"),
        ({"id": ""}, "sin `id`"),
    ],
)
def test_a_bad_rule_is_refused_at_load(change: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        classify(RAW, [{**RULE, **change}])


def test_two_rules_cannot_disagree_or_share_an_id() -> None:
    other = {**RULE, "id": "r2", "set": {"processing": "ground-or-return"}}
    with pytest.raises(ValueError, match="dos valores"):
        classify(RAW, [RULE, other])
    with pytest.raises(ValueError, match="duplicado"):
        classify(RAW, [RULE, RULE])
    same = {**RULE, "id": "r2"}
    assert classify(RAW, [RULE, same])["a"]["processing"]["rule"] == "r1"


def test_the_dimensions_add_fields_and_leave_the_old_ones_alone() -> None:
    base = {"mode", "equipment", "crew_time_minutes", "crew_time_basis"}
    for key, item in costs().items():
        # Solo un calculado añade de qué se calcula (decimocuarta ronda).
        extra = {"inputs", "inherits", "inputs_basis"} if item["mode"] == "derived" else set()
        assert set(item) == base | extra, key
        published = cost(key)
        assert published is not None
        assert {name: published[name] for name in item} == item
        assert published["dimensions"] == dimensions()[key]


def test_the_summary_counts_add_up_and_show_what_is_unclassified() -> None:
    body = summary()
    assert body["indicators"] == len(CATALOG)
    total = 0
    for row in body["dimensions"]:
        held = [item[row["key"]]["value"] for item in dimensions().values()]
        assert row["unclassified"] == held.count(UNCLASSIFIED)
        assert [entry["value"] for entry in row["values"]] == list(
            DIMENSIONS[row["key"]]["values"]
        )
        for entry in row["values"]:
            assert entry["count"] == held.count(entry["value"])
        assert sum(e["count"] for e in row["values"]) + row["unclassified"] == len(CATALOG)
        total += row["unclassified"]
    assert body["unclassified"] == total > 0
    assert body["fully_classified"] == sum(
        1 for item in dimensions().values()
        if UNCLASSIFIED not in {entry["value"] for entry in item.values()}
    )
    assert "sin clasificar" in body["unclassified_note"].lower()
    assert all(rule["indicators"] > 0 and rule["basis"] for rule in body["rules"])


def test_no_analyzer_is_said_to_fly_without_a_source() -> None:
    # Lo leído de analizadores a bordo son demostraciones y una sesión de estudio: van como
    # discrepancias de la regla de sangre, no como clase de ningún indicador.
    held = [item["processing"]["value"] for item in dimensions().values()]
    assert "onboard-analyzer" not in held


def test_the_blood_count_is_decided_by_what_was_read_and_says_what_disagrees() -> None:
    for key in ("leukocytes", "lymphocytes", "neutrophils"):
        item = dimensions()[key]
        assert item["processing"]["value"] == "ground-or-return"
        assert item["result"]["value"] == "deferred"
        assert item["processing"]["rule"] == "leucocitos-en-tierra"
        # Decimocuarta ronda: el recuento tomado en vuelo iba en un tubo EDTA (Crucian 2015).
        assert item["consumables"]["rule"] == "hemograma-leucocitos-en-tubo-edta"
    rule = _rule("leucocitos-en-tierra")
    assert any("unmet need" in source["quote"] for source in rule["sources"])
    assert any("within 48 h" in source["quote"] for source in rule["sources"])
    tube = _rule("hemograma-leucocitos-en-tubo-edta")
    assert any("(EDTA) anticoagulated" in source["quote"] for source in tube["sources"])
    # Al lado, el protocolo de 2025: EDTA solo antes y después del vuelo, y por qué.
    said = " ".join(item["quote"] for item in tube["discrepancies"])
    assert "a 3 mL EDTA tube" in said
    assert "cannot be measured in samples that have been frozen" in said
    assert all(item["note"].strip() for item in tube["discrepancies"])
    # La demostración que sí contó leucocitos a bordo se enseña al lado, no se calla.
    assert any("real-time hematology" in item["quote"] for item in rule["discrepancies"])
    assert all(item["note"].strip() for item in rule["discrepancies"])


def test_every_blood_draw_is_returned_to_earth_with_the_onboard_analyses_beside() -> None:
    blood = [k for k, item in costs().items() if item["equipment"] == BLOOD]
    assert blood
    for key in blood:
        assert dimensions()[key]["processing"]["value"] == "ground-or-return", key
        assert dimensions()[key]["result"]["value"] == "deferred", key
    assert dimensions()["sodium"]["processing"]["rule"] == "sangre-en-tierra"
    rule = _rule("sangre-en-tierra")
    assert any("frozen and returned" in source["quote"] for source in rule["sources"])
    assert any("red blood cell count" in item["quote"] for item in rule["discrepancies"])


def test_saliva_and_laboratory_urine_cite_what_was_read() -> None:
    for key in ("cortisol-salivary", "latent-virus-shedding"):
        assert dimensions()[key]["processing"]["rule"] == "saliva-en-tierra"
    assert dimensions()["ntx-telopeptide"]["processing"]["rule"] == "orina-de-laboratorio-en-tierra"
    # La densidad no la alcanza ninguna frase leída (se buscó el 2026-10-20): sigue sin clasificar,
    # salvo la automatización, que EMMA deduce de la clase de medida (decimonovena ronda).
    item = dimensions()["urine-specific-gravity"]
    assert all(
        entry["value"] == UNCLASSIFIED for name, entry in item.items() if name != "automation"
    )
    assert item["automation"]["value"] == "sample-and-analysis"


def test_the_24h_urine_volume_is_measured_on_earth_from_the_lithium_in_each_bag() -> None:
    # Decimotercera ronda (leído el 2026-10-20): el volumen se calcula en Tierra por el litio.
    item = dimensions()["urine-volume-24h"]
    assert item["processing"]["value"] == "ground-or-return"
    assert item["result"]["value"] == "deferred"
    assert item["processing"]["rule"] == item["result"]["rule"] == "orina-24h-en-tierra"
    rule = _rule("orina-24h-en-tierra")
    assert any("to determine void volume" in source["quote"] for source in rule["sources"])
    assert any("later ground analysis" in source["quote"] for source in rule["sources"])
    # El equipo que lo mediría a bordo y el protocolo vigente sin orina en vuelo, al lado.
    said = {item["ref"]: item["quote"] for item in rule["discrepancies"]}
    assert "real-time in-flight volume data" in said["ntrs-20090007818"]
    assert "launched" in said["ntrs-20110008547"]
    assert said["hardy-2025-spaceflight-standard-measures"] == (
        "There are no inflight urine collections."
    )
    # Y los mismos matices al lado de lo que gasta: no se callan en otra dimensión.
    bags = {item["ref"] for item in _rule("orina-en-bolsas-con-trazador")["discrepancies"]}
    assert bags == {"ntrs-20110008547", "hardy-2025-spaceflight-standard-measures"}


def test_what_a_sample_consumes_is_what_was_read_and_nothing_more() -> None:
    # Cada medida con muestra gasta el material que la frase leída nombra: tubo, bolsa, papel o
    # algodón. La densidad de la orina no: nada leído dice cómo se mide.
    # El hemograma va en sangre entera, no en el suero de los tubos leídos: no gasta por ellos.
    # Los leucocitos y su fórmula, sí, por el tubo EDTA del estudio de 2015; la serie roja, los
    # índices y las plaquetas, por el tubo EDTA del estudio de 2017 (decimoquinta ronda).
    # Y la ecografía, sin muestra, gasta el gel que el inventario de la ISS lista como consumible.
    leukocytes = {
        "leukocytes", "lymphocytes", "neutrophils", "lymphocytes-percent", "neutrophils-percent",
    }
    hemogram = leukocytes | RED_SERIES
    serum = {k for k, item in costs().items() if item["equipment"] == BLOOD} - hemogram
    expected = {
        "sangre-en-tubos": serum,
        "hemograma-leucocitos-en-tubo-edta": leukocytes,
        "hemograma-serie-roja-en-tubo-edta": RED_SERIES,
        "orina-en-bolsas-con-trazador": {"urine-volume-24h", "ntx-telopeptide"},
        "saliva-cortisol-en-papel-de-filtro": {"cortisol-salivary"},
        "saliva-virus-en-salivette": {"latent-virus-shedding"},
        "ecografia-con-gel": SCANS,
        # El glucómetro tira la lanceta y la tira tras cada medida (CDC, 2026-11-04).
        "glucometro-tira-y-lanceta": {"glucose-capillary"},
    }
    found: dict[str, set[str]] = {}
    for key, item in dimensions().items():
        if item["consumables"]["value"] == "consumes":
            found.setdefault(str(item["consumables"]["rule"]), set()).add(key)
    # Lo que gasta es exactamente lo leído: ni un indicador más ni una regla sin frase.
    assert found == expected
    assert any("7.5 mL SSTs" in source["quote"] for source in _rule("sangre-en-tubos")["sources"])
    # Lo que no se encontró sigue sin clasificar: la densidad de la orina y las medidas sin
    # muestra cuyo equipo no nombra consumibles (wearable, tensiómetro, masa, VO2, dinamómetro).
    unread = (
        "urine-specific-gravity", "heart-rate", "systolic-bp", "body-weight", "vo2-peak",
        "grip-strength-right",
    )
    for key in unread:
        assert dimensions()[key]["consumables"]["value"] == UNCLASSIFIED, key


def test_what_was_read_resolves_to_a_registry_card() -> None:
    body = summary()
    assert set(body["reading_display"]) == {"sources", "discrepancies"}
    seen = set()
    for rule in body["rules"]:
        for kind in ("sources", "discrepancies"):
            for item in rule[kind]:
                ref = registry.get(item["ref"])
                assert (item["title"], item["source"], item["url"]) == (
                    ref.title, ref.source, ref.url
                )
                assert item["quote"].strip() and item["where"].strip()
                # El día de lectura es el que la ficha del registro declara en sus notas.
                assert item["read_on"] in (ref.notes or ""), (rule["id"], item["ref"])
                seen.add(item["ref"])
    assert seen == cost_module.cited_refs()
    # Las reglas que se apoyan en el repositorio, y no en una lectura, no fingen fuente.
    assert _rule("sin-muestra-continuo")["sources"] == []


@pytest.mark.parametrize(
    ("kind", "change", "message"),
    [
        ("sources", {"quote": " "}, "vacío"),
        ("sources", {"ref": "no-existe"}, "no está en el registro"),
        ("sources", {"read_on": "octubre"}, "read_on"),
        ("sources", {"note": "sobra"}, "exactamente"),
        ("discrepancies", {}, "exactamente"),
        ("discrepancies", {"note": ""}, "vacío"),
    ],
)
def test_a_reading_without_its_parts_is_refused_at_load(
    kind: str, change: dict[str, Any], message: str
) -> None:
    item = {
        "ref": "ntrs-20130000839", "quote": "frase", "where": "resumen", "read_on": "2026-10-14",
        **change,
    }
    with pytest.raises(ValueError, match=message):
        classify(RAW, [{**RULE, kind: [item]}])
    with pytest.raises(ValueError, match="lista"):
        classify(RAW, [{**RULE, kind: item}])


# --------------------------------------------------------------------------------------------
# Decimocuarta ronda: entradas de los calculados, lo buscado y no encontrado, y «hoy se sabe
# después» (conversación de ideación ~643 y ~754).
# --------------------------------------------------------------------------------------------

DERIVED: dict[str, dict[str, Any]] = {
    "x": {"mode": "laboratory", "equipment": "e"},
    "y": {"mode": "laboratory", "equipment": "e"},
    "z": {"mode": "continuous-passive", "equipment": "w"},
    "q": {
        "mode": "derived", "equipment": "cálculo", "inputs": ["x", "y"], "inherits": True,
        "inputs_basis": "sale del mismo informe",
    },
}
GROUND = {
    "id": "g", "match": {"keys": ["x", "y"]},
    "set": {"processing": "ground-or-return", "result": "deferred"}, "basis": "leído",
}


def _validated(item: dict[str, Any]) -> dict[str, Any]:
    base = {"crew_time_minutes": None, "crew_time_basis": "sin fuente"}
    raw = {key: {**base, **value} for key, value in DERIVED.items()}
    raw["q"] = {**base, **item}
    return cost_module.validate(raw)


def test_two_derived_ratios_inherit_from_their_analytes_and_the_dose_does_not() -> None:
    expected = {
        "neutrophil-lymphocyte-ratio": (["neutrophils", "lymphocytes"], "leucocitos-en-tierra"),
        "bun-creatinine-ratio": (["urea", "creatinine"], "sangre-en-tierra"),
    }
    for key, (inputs, rule) in expected.items():
        assert costs()[key]["inputs"] == inputs and costs()[key]["inherits"] is True
        for name in ("processing", "result"):
            entry = dimensions()[key][name]
            assert entry["inherited_from"] == inputs and entry["rule"] == rule, (key, name)
            assert entry["value"] == dimensions()[inputs[0]][name]["value"]
        # Lo que gasta no se hereda: el cálculo no vuelve a gastar el tubo de sus analitos.
        assert dimensions()[key]["consumables"]["rule"] == "calculo"
    # La dosis acumulada llega registrada en EMMA, no se calcula de la tasa: no hereda, y dice
    # por qué (el modelo NASA Q necesita un espectro que ninguna fuente de EMMA publica).
    dose = costs()["cumulative-dose"]
    assert dose["inputs"] == ["absorbed-dose-rate"] and dose["inherits"] is False
    # Lo heredado lleva la regla de sus entradas, pero no cuenta como alcanzado por ella.
    assert _rule("leucocitos-en-tierra")["indicators"] == 5
    assert "NASA Q" in dose["inputs_basis"] and "dosimetry.py" in dose["inputs_basis"]
    for name in ("processing", "result"):
        assert dimensions()["cumulative-dose"][name]["value"] == UNCLASSIFIED


def test_inheritance_needs_every_input_to_agree() -> None:
    found = classify(DERIVED, [GROUND])
    assert found["q"]["processing"]["value"] == "ground-or-return"
    assert found["q"]["processing"]["inherited_from"] == ["x", "y"]
    assert found["q"]["processing"]["rule"] == "g"
    assert found["q"]["consumables"]["value"] == UNCLASSIFIED
    # Una entrada sin clasificar: no se elige la otra.
    half = {**GROUND, "match": {"keys": ["x"]}}
    assert classify(DERIVED, [half])["q"]["processing"]["value"] == UNCLASSIFIED
    # Dos entradas que discrepan: tampoco.
    other = {**GROUND, "id": "h", "match": {"keys": ["y"]}, "set": {"processing": "on-device"}}
    assert classify(DERIVED, [half, other])["q"]["processing"]["value"] == UNCLASSIFIED
    # Mismo valor por reglas distintas: hereda, sin atribuirlo a una de ellas.
    twin = {**GROUND, "id": "h", "match": {"keys": ["y"]}}
    both = classify(DERIVED, [half, twin])["q"]["processing"]
    assert both["value"] == "ground-or-return" and both["rule"] is None
    assert "g, h" in both["basis"]
    # Todas las entradas sin clasificar: no se hereda «sin clasificar» como si fuera una clase.
    elsewhere = {**GROUND, "match": {"keys": ["z"]}}
    alone = classify(DERIVED, [elsewhere])["q"]["processing"]
    assert alone["value"] == UNCLASSIFIED and alone["inherited_from"] is None
    # Sin `inherits`, nada.
    still = {**DERIVED, "q": {**DERIVED["q"], "inherits": False}}
    assert classify(still, [GROUND])["q"]["processing"]["value"] == UNCLASSIFIED


def test_inheritance_cannot_contradict_a_rule() -> None:
    direct = {**GROUND, "id": "d", "match": {"keys": ["q"]}, "set": {"processing": "on-device"}}
    with pytest.raises(ValueError, match="sus entradas dan dos valores"):
        classify(DERIVED, [GROUND, direct])
    agree = {**direct, "set": {"processing": "ground-or-return"}}
    assert classify(DERIVED, [GROUND, agree])["q"]["processing"]["rule"] == "d"


@pytest.mark.parametrize(
    ("item", "message"),
    [
        ({"mode": "derived", "equipment": "c"}, "dice de qué se calcula"),
        ({**DERIVED["q"], "inputs": []}, "lista de indicadores"),
        ({**DERIVED["q"], "inputs": ["x", "x"]}, "lista de indicadores"),
        ({**DERIVED["q"], "inputs": [{"x": 1}]}, "lista de indicadores"),
        ({**DERIVED["q"], "inputs": ["no-existe"]}, "no están en el coste"),
        ({**DERIVED["q"], "inputs": ["x", "q"]}, "también son calculadas"),
        ({**DERIVED["q"], "inherits": "sí"}, "sí o no"),
        ({**DERIVED["q"], "inputs_basis": " "}, "sin `inputs_basis`"),
        ({**DERIVED["q"], "mode": "laboratory"}, "solo un calculado"),
    ],
)
def test_bad_inputs_are_refused_at_load(item: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _validated(item)


def test_what_was_searched_and_not_found_is_declared_on_unclassified_pairs_only() -> None:
    body = summary()
    assert body["searched_display"] == "Buscado y no encontrado"
    by_key = _searched_by(body["searched"], "consumables")
    # Las tres dimensiones de antes de la decimosexta ronda: de la orina no se buscó la masa.
    assert set(by_key["urine-specific-gravity"]["dimensions"]) == {
        "processing", "result", "consumables",
    }
    assert "NTRS" in by_key["urine-specific-gravity"]["searched"]
    assert by_key["vo2-peak"]["dimensions"] == ["consumables"]
    # La serie roja salió de la lista al leerse su tubo (decimoquinta ronda).
    assert "platelets" not in by_key
    for item in body["searched"]:
        assert item["dimensions_display"] == [DIMENSIONS[d]["display"] for d in item["dimensions"]]
        for key in item["keys"]:
            for name in item["dimensions"]:
                assert dimensions()[key][name]["value"] == UNCLASSIFIED, (key, name)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"searched": " "}, "qué se buscó"),
        ({"searched_on": "hoy"}, "searched_on"),
        ({"keys": []}, "al menos"),
        ({"keys": "z"}, "al menos"),
        ({"dimensions": "consumables"}, "al menos"),
        ({"keys": ["no-existe"]}, "no están"),
        ({"dimensions": ["where"]}, "desconocidas"),
        ({"keys": ["x"], "dimensions": ["processing"]}, "ya clasificados"),
        ({"extra": 1}, "exactamente"),
    ],
)
def test_a_bad_search_note_is_refused_at_load(change: dict[str, Any], message: str) -> None:
    item = {
        "keys": ["z"], "dimensions": ["consumables"], "searched": "NTRS",
        "searched_on": "2026-10-21", **change,
    }
    with pytest.raises(ValueError, match=message):
        cost_module.check_searched([item], classify(DERIVED, [GROUND]))
    with pytest.raises(ValueError, match="lista"):
        cost_module.check_searched(item, classify(DERIVED, [GROUND]))


def test_what_depends_on_earth_today_is_set_beside_what_each_profile_source_says() -> None:
    ground = summary()["ground_dependence"]
    # Lo que depende de Tierra es lo que las reglas dicen, heredados incluidos; nada más.
    assert [item["key"] for item in ground["indicators"]] == [
        key for key, item in dimensions().items()
        if item["processing"]["value"] == "ground-or-return"
    ]
    keys = {item["key"]: item for item in ground["indicators"]}
    assert keys["neutrophil-lymphocyte-ratio"]["inherited_from"] == ["neutrophils", "lymphocytes"]
    assert keys["urine-volume-24h"]["rule"] == "orina-24h-en-tierra"
    assert "urine-specific-gravity" not in keys and "heart-rate" not in keys
    assert {item["rule"] for item in ground["indicators"]} <= set(ground["rules"])
    # Cada perfil, con lo que dice SU fuente, leída del catálogo de perfiles (no una copia).
    catalog = mission_profiles.catalog()["profiles"]
    assert [p["id"] for p in ground["profiles"]] == [p["id"] for p in catalog]
    for shown, source in zip(ground["profiles"], catalog, strict=True):
        assert [a["key"] for a in shown["aspects"]] == ["resupply", "return_or_evacuation"]
        for aspect in shown["aspects"]:
            raw = source["aspects"][aspect["key"]]
            assert aspect["label"] == mission_profiles.ASPECTS[aspect["key"]]
            if raw["status"] == mission_profiles.READ:
                assert aspect["text"] == raw["statement"] and aspect["citations"]
                assert aspect["searched"] is None
            else:
                # Si la fuente del perfil no lo dice, no se deduce: EMMA no tiene fuente.
                assert aspect["text"] == "EMMA no tiene fuente" == ground["no_source"]
                assert aspect["searched"] == raw["searched"] and not aspect["citations"]
            for cite in aspect["citations"]:
                assert cite["title"] == registry.get(cite["ref"]).title
    assert "no deduce" in ground["note"]
    assert "hoy lo sabemos después" in ground["origin"]


def test_a_profile_aspect_its_source_does_not_cover_says_emma_has_no_source() -> None:
    """Con un hueco en el perfil, «EMMA no tiene fuente» y lo que se buscó; nada se deduce.

    Los perfiles leídos ya no tienen huecos en estos dos aspectos (decimocuarta ronda, C8), así
    que la rama se prueba con un aspecto fabricado: sin él, enseñar un hueco como leído pasaría.
    """
    gap = {
        "status": mission_profiles.UNVERIFIED, "statement": "FRASE-QUE-NO-DEBE-SALIR",
        "citations": [], "discrepancy": None, "searched": "BUSCADO-EN-NTRS",
    }
    shown = cost_module._ground_aspect("resupply", gap)
    assert shown["status"] == mission_profiles.UNVERIFIED
    assert shown["text"] == "EMMA no tiene fuente" == summary()["ground_dependence"]["no_source"]
    assert shown["searched"] == "BUSCADO-EN-NTRS" and shown["citations"] == []
    assert shown["label"] == mission_profiles.ASPECTS["resupply"]
    read = {**gap, "status": mission_profiles.READ}
    assert cost_module._ground_aspect("resupply", read)["text"] == "FRASE-QUE-NO-DEBE-SALIR"
    assert cost_module._ground_aspect("resupply", read)["searched"] is None


# --------------------------------------------------------------------------------------------
# Decimoquinta ronda: el material de las medidas sin muestra. Lo que una ficha no nombra no se da
# por «no gasta»; lo que se leyó gastar lleva su frase.
# --------------------------------------------------------------------------------------------


def test_every_ultrasound_scan_consumes_the_gel_the_station_inventory_lists() -> None:
    assert {key for key, item in costs().items() if item["equipment"] == ULTRASOUND} == SCANS
    for key in sorted(SCANS):
        entry = dimensions()[key]["consumables"]
        assert (entry["value"], entry["rule"]) == ("consumes", "ecografia-con-gel"), key
    rule = _rule("ecografia-con-gel")
    said = {item["quote"]: item for item in rule["sources"]}
    assert "Echo Gel" in said and "Consumables" in said["Echo Gel"]["where"]
    assert any("Ultrasound 2" in quote for quote in said)
    # Lo que la frase no dice se dice en la regla: ni cuánto gel ni qué equipo hay hoy a bordo.
    assert "no dice cuánto gel" in rule["basis"] and "2016" in rule["basis"]


def test_the_red_series_tube_is_read_from_the_study_that_measured_it_in_flight() -> None:
    for key in sorted(RED_SERIES):
        entry = dimensions()[key]["consumables"]
        assert (entry["value"], entry["rule"]) == ("consumes", "hemograma-serie-roja-en-tubo-edta")
        # Dónde se procesa no cambia: sigue siendo la regla de la sangre.
        assert dimensions()[key]["processing"]["rule"] == "sangre-en-tierra", key
    rule = _rule("hemograma-serie-roja-en-tubo-edta")
    quotes = " ".join(item["quote"] for item in rule["sources"])
    assert "(EDTA) spray-coated" in quotes and "In-flight, samples were collected" in quotes
    # Los índices calculados salen del mismo tubo: la frase lo dice, no se supone.
    assert "All other parameters are calculated from these measurements." in quotes
    assert {item["ref"] for item in rule["sources"]} == {"kunz-2017-hematologic-indices-iss"}
    # Al lado, el protocolo de 2025 (el tubo EDTA solo antes y después del vuelo) y lo que el
    # mismo estudio leyó de la espera: no todo índice aguanta 48 h.
    said = {item["ref"]: item for item in rule["discrepancies"]}
    assert "a 3 mL EDTA tube" in said["hardy-2025-spaceflight-standard-measures"]["quote"]
    assert "remained stable for 48 h" in said["kunz-2017-hematologic-indices-iss"]["quote"]
    assert all(item["note"].strip() for item in rule["discrepancies"])


def test_consumes_nothing_is_only_said_of_what_the_measure_itself_is() -> None:
    # «No gasta» lo asigna una regla que lo dice de la medida (cálculo, anotación, prueba en
    # pantalla); nunca la falta de una frase sobre el equipo.
    allowed = {
        "calculo", "anotacion-del-tripulante", "prueba-de-reaccion-en-pantalla",
        "bateria-cognitiva-en-portatil",
    }
    held = {
        str(item["consumables"]["rule"]) for item in dimensions().values()
        if item["consumables"]["value"] == "none"
    }
    assert held == allowed
    for key in ("pvt-mean-rt", "pvt-lapses"):
        entry = dimensions()[key]["consumables"]
        assert (entry["value"], entry["rule"]) == ("none", "prueba-de-reaccion-en-pantalla")
    rule = _rule("prueba-de-reaccion-en-pantalla")
    # Se apoya en el repositorio, no en una lectura: no finge fuente.
    assert rule["sources"] == [] and rule["discrepancies"] == []
    assert "ingest/pvt.py" in rule["basis"] and "POST /api/pvt" in rule["basis"]


def test_the_wearable_rule_shows_that_the_station_analyses_its_data_on_earth() -> None:
    rule = _rule("sin-muestra-continuo")
    assert rule["sources"] == []
    (discrepancy,) = rule["discrepancies"]
    assert discrepancy["ref"] == "csa-bio-monitor"
    assert "downloads the data to Earth" in discrepancy["quote"]
    # La regla alcanza también al dosímetro y al registro de ejercicio: la nota dice que la frase
    # no habla de ellos.
    assert "dosímetro" in discrepancy["note"] and "no habla de ellos" in discrepancy["note"]
    # La clase no cambia por el matiz: se enseña al lado.
    assert dimensions()["heart-rate"]["processing"]["value"] == "on-device"


def test_what_the_equipment_cards_do_not_say_is_declared_as_searched() -> None:
    by_key = _searched_by(summary()["searched"], "consumables")
    sensorless = (
        "heart-rate", "oxygen-saturation", "sleep-duration", "systolic-bp", "orthostatic-drop",
        "body-weight", "vo2-peak", "grip-strength-left",
    )
    for key in sensorless:
        assert dimensions()[key]["consumables"]["value"] == UNCLASSIFIED, key
        assert "consumables" in by_key[key]["dimensions"], key
        assert "Research Explorer" in by_key[key]["searched"] or "ISS Medical Project" in (
            by_key[key]["searched"]
        ), key
    # La dosis acumulada: dos dosímetros en la ISS, y EMMA no dice de cuál llega la suya.
    dose = _searched_by(summary()["searched"], "processing")["cumulative-dose"]
    assert set(dose["dimensions"]) == {"processing", "result"}
    assert "Crew Active Dosimeters" in dose["searched"] and "a ojo" in dose["searched"]
    assert "2026-10-22" in costs()["cumulative-dose"]["inputs_basis"]
    # La densidad de la orina, buscada otra vez.
    assert by_key["urine-specific-gravity"]["searched_on"] == "2026-10-22"


def test_the_cost_of_measuring_is_not_part_of_the_rules_version() -> None:
    # Inventario: el fichero no entra en la huella de las reglas (`core/versioning.py`).
    source = Path(versioning.__file__).read_text(encoding="utf-8")
    assert "measurement_cost" not in source and "ingest.cost" not in source
    assert "measurement" not in str(versioning.rules().keys())


def test_the_route_publishes_dimensions_and_the_unclassified_total(client: TestClient) -> None:
    response = client.get("/api/measurement-cost")
    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == summary()
    assert [item["key"] for item in body["indicators"]] == list(CATALOG)
    for item in body["indicators"]:
        assert item["dimensions"] == dimensions()[item["key"]]
        assert item["equipment"] == costs()[item["key"]]["equipment"]
    catalog = client.get("/api/indicators").json()["indicators"]
    assert all(
        item["measurement_cost"]["dimensions"] == dimensions()[item["key"]] for item in catalog
    )


def test_describing_the_cost_does_not_move_the_verdict(client: TestClient) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "progressive-insomnia", "days": 30}
    ).status_code == 201

    def verdict() -> tuple[Any, ...]:
        body = client.get("/api/status").json()
        return (
            body["overall_level"],
            {key: (value["level"], value["score"]) for key, value in body["domains"].items()},
            body["alerts"],
            body["rules_version"],
        )

    before = verdict()
    assert before[0] != "nominal"
    assert client.get("/api/measurement-cost").status_code == 200
    assert verdict() == before


# --- Decimosexta ronda (E17): las dimensiones que nombra la base de conocimiento §9 ---

KB = Path(__file__).resolve().parents[2] / "docs" / "contexto" / "knowledge-base-v1.md"
NEW_DIMENSIONS = ("mass", "volume", "power", "calibration", "training")
FIGURE_REF = "nasa-hrp-roi-iss-facilities-2023"
FIGURE_RULE: dict[str, Any] = {
    "id": "f1", "match": {"mode": "continuous-passive"},
    "set": {"mass": {"figure": "10.32", "unit": "lbs"}}, "basis": "leído",
    "sources": [{
        "ref": FIGURE_REF, "quote": "16.2 x 10.1 x 6.5 inches, 10.32 lbs",
        "where": "diapositiva 8", "read_on": "2026-10-23",
    }],
}


def _kb_terms() -> list[str]:
    """La lista literal de la base de conocimiento §9, leída del documento del equipo."""
    text = KB.read_text(encoding="utf-8")
    section = text.split("# 9. Instalaciones y equipamiento: coste de medir", 1)[1]
    listed = section.split("coste de medición”: ", 1)[1].split(". Esto", 1)[0]
    head, _, last = listed.rpartition(" y ")
    return [*head.split(", "), last]


def test_every_term_of_the_knowledge_base_list_has_its_place() -> None:
    # La lista del documento, en su orden: si el documento añade un término, falla aquí.
    assert [term for term, _ in cost_module.KB_TERMS] == _kb_terms()
    coverage = summary()["kb_coverage"]
    assert coverage["display"] and "§9" in coverage["origin"]
    for item, (term, field) in zip(coverage["terms"], cost_module.KB_TERMS, strict=True):
        assert (item["term"], item["field"]) == (term, field)
        if item["kind"] == "dimension":
            assert item["display"] == DIMENSIONS[field]["display"]
        else:
            assert item["display"] == cost_module.KB_FIELDS[field]
    # Las cinco que faltaban son dimensiones; un término sin sitio no se publica tapado.
    assert set(NEW_DIMENSIONS) <= set(DIMENSIONS)
    # Las cifras: masa, volumen y potencia y, desde la decimonovena ronda, el volumen de datos.
    assert set(cost_module.QUANTITIES) == {"mass", "volume", "power", "storage"}


def test_a_term_without_a_place_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cost_module, "KB_TERMS", (("masa", "weight"),))
    with pytest.raises(ValueError, match="no tiene"):
        cost_module.kb_coverage()
    # Y falla al cargar las dimensiones, no en la primera petición del resumen.
    with pytest.raises(ValueError, match="no tiene"):
        cost_module.dimensions.__wrapped__()


def test_a_field_term_is_looked_up_in_the_entries_not_only_in_its_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # «hardware» apunta a `equipment`: si una entrada lo pierde, la lista no lo publica tapado.
    entries = {key: dict(item) for key, item in cost_module.costs().items()}
    del next(iter(entries.values()))["equipment"]
    monkeypatch.setattr(cost_module, "costs", lambda: entries)
    with pytest.raises(ValueError, match="no tiene"):
        cost_module.kb_coverage()
    # El tiempo de tripulación es el campo que existe, no un nombre inventado.
    assert ("crew time", "crew_time_minutes") in cost_module.KB_TERMS


def test_a_figure_is_copied_with_its_unit_from_what_was_read() -> None:
    found = classify(RAW, [FIGURE_RULE])["a"]["mass"]
    assert found["value"] == cost_module.STATED and found["rule"] == "f1"
    # La cifra en español (F.5.6) y su unidad tal cual se leyó.
    assert found["display"] == "10,32 lbs"
    assert found["figure"] == {"amount": 10.32, "decimals": 2, "unit": "lbs", "figure": "10.32"}
    assert classify(RAW, [FIGURE_RULE])["b"]["mass"]["figure"] is None


@pytest.mark.parametrize(
    ("assigned", "sources", "message"),
    [
        ({"mass": {"figure": "10.3", "unit": "lbs"}}, None, "no está en ninguna frase"),
        ({"mass": {"figure": "10.32", "unit": "kg"}}, None, "no está en ninguna frase"),
        ({"mass": {"figure": "0.32", "unit": "lbs"}}, None, "no está en ninguna frase"),
        ({"mass": {"figure": "10.32", "unit": "stone"}}, None, "unidad"),
        ({"mass": {"figure": "diez", "unit": "lbs"}}, None, "tal cual"),
        # En inglés la coma separa miles: «1,000» no se lee como uno.
        ({"mass": {"figure": "10,32", "unit": "lbs"}}, None, "tal cual"),
        ({"mass": {"figure": "0", "unit": "lbs"}}, None, "positiva"),
        ({"mass": {"figure": 10.32, "unit": "lbs"}}, None, "tal cual"),
        ({"mass": {"figure": "10.32", "unit": "lbs", "extra": 1}}, None, "exactamente"),
        ({"mass": "stated"}, None, "no a secas"),
        ({"mass": ["10.32", "lbs"]}, None, "ni una palabra"),
        ({"processing": {"figure": "10.32", "unit": "lbs"}}, None, "no es una cifra"),
        ({"mass": {"figure": "10.32", "unit": "lbs"}}, [], "no está en ninguna frase"),
    ],
)
def test_a_figure_without_its_sentence_is_refused(
    assigned: dict[str, Any], sources: list[Any] | None, message: str
) -> None:
    rule = {**FIGURE_RULE, "set": assigned}
    if sources is not None:
        # Lo que matiza no sostiene una cifra: la frase en `discrepancies` no basta.
        rule["discrepancies"] = [{**FIGURE_RULE["sources"][0], "note": "matiza"}]
        rule["sources"] = sources
    with pytest.raises(ValueError, match=message):
        classify(RAW, [rule])


def test_two_rules_cannot_give_two_figures() -> None:
    quote = "16.2 x 10.1 x 6.5 lbs, 10.32 lbs"
    first = {**FIGURE_RULE, "sources": [{**FIGURE_RULE["sources"][0], "quote": quote}]}
    second = {**first, "id": "f2", "set": {"mass": {"figure": "6.5", "unit": "lbs"}}}
    with pytest.raises(ValueError, match="dos cifras"):
        classify(RAW, [first, second])
    same = {**first, "id": "f2"}
    assert classify(RAW, [first, same])["a"]["mass"]["rule"] == "f1"


def test_no_equipment_figure_is_published_without_a_source_today() -> None:
    # Lo leído no da masa, volumen ni potencia de ningún equipo de EMMA: ni una cifra.
    for item in dimensions().values():
        for name in cost_module.QUANTITIES:
            assert item[name]["value"] != cost_module.STATED
            assert item[name]["figure"] is None
    # Y lo que se buscó se declara, con el tope del rack, que no se escribe como potencia.
    power = _searched_by(summary()["searched"], "power")
    for key in (*SCANS, "body-weight", "vo2-peak", "sleep-duration", "systolic-bp"):
        assert key in power, key
    assert "500 W" in power["onsd-left"]["searched"] and "tope" in power["onsd-left"]["searched"]


def test_only_the_two_ratios_add_no_equipment_of_their_own() -> None:
    held = {
        key for key, item in dimensions().items()
        if any(item[name]["value"] == "no-own-equipment" for name in NEW_DIMENSIONS)
    }
    assert held == {"neutrophil-lymphocyte-ratio", "bun-creatinine-ratio"}
    for key in held:
        assert all(
            dimensions()[key][name]["rule"] == "calculo-sin-equipo-propio"
            for name in NEW_DIMENSIONS
        )
    # La dosis acumulada llega registrada: no se dice que no tenga equipo.
    dose = dimensions()["cumulative-dose"]
    assert all(dose[name]["value"] == UNCLASSIFIED for name in NEW_DIMENSIONS)


def test_calibration_is_only_said_of_what_was_read_to_be_calibrated() -> None:
    held = {
        key: item["calibration"]["rule"] for key, item in dimensions().items()
        if item["calibration"]["value"] == "required"
    }
    assert held == {
        "body-weight": "masa-corporal-con-brazo-de-calibracion",
        "vo2-peak": "prueba-de-esfuerzo-con-gas-de-calibracion",
        # Decimoctava ronda: el dosímetro de la nave, la serie roja y el actígrafo.
        "absorbed-dose-rate": "dosimetro-de-nave-calibrado",
        **dict.fromkeys(RED_SERIES, "hemograma-serie-roja-con-analizador-calibrado"),
        **dict.fromkeys(ACTIGRAPHY, "actigrafo-con-recalibracion-del-fabricante"),
    }
    slammd = _rule("masa-corporal-con-brazo-de-calibracion")
    assert any("Calibration Mass" in item["quote"] for item in slammd["sources"])
    assert "cada cuánto" in slammd["basis"]
    gas = _rule("prueba-de-esfuerzo-con-gas-de-calibracion")
    assert any("PPFS Calibration Gas" in item["quote"] for item in gas["sources"])
    # El gas de calibración no se convierte aquí en consumible de la prueba.
    assert dimensions()["vo2-peak"]["consumables"]["value"] == UNCLASSIFIED


def test_the_left_jugular_scan_is_guided_from_earth_and_the_rest_is_not_said() -> None:
    entry = dimensions()["ijv-csa-left"]["training"]
    assert (entry["value"], entry["rule"]) == (
        "ground-guided", "ecografia-yugular-guiada-desde-tierra",
    )
    (source,) = _rule("ecografia-yugular-guiada-desde-tierra")["sources"]
    assert source["ref"] == "marshall-goebel-2019-ijv"
    assert "guided in real time by investigators on the ground" in source["quote"]
    training = _searched_by(summary()["searched"], "training")
    for key in ("onsd-left", "onsd-right", "ijv-csa-right", "bladder-volume"):
        assert dimensions()[key]["training"]["value"] == UNCLASSIFIED, key
        assert key in training, key


def test_the_periodic_rule_shows_what_the_station_does_with_an_ultrasound() -> None:
    rule = _rule("sin-muestra-periodico")
    said = {(item["ref"], item["quote"]) for item in rule["discrepancies"]}
    assert any(ref == FIGURE_REF and "real-time downlink" in quote for ref, quote in said)
    assert any(
        ref == "marshall-goebel-2019-ijv" and "manually delineated" in quote
        for ref, quote in said
    )
    assert all(item["note"].strip() for item in rule["discrepancies"])
    # La clase no cambia por el matiz: se enseña al lado.
    assert dimensions()["ijv-csa-left"]["processing"]["value"] == "on-device"


def test_the_alert_check_cost_carries_the_new_dimensions() -> None:
    row = check_cost._indicator_cost("ijv-csa-left")
    facts = {fact["key"]: fact for fact in row["facts"]}
    assert facts["training"]["display"] == DIMENSIONS["training"]["values"]["ground-guided"]
    assert facts["training"]["missing"] is False
    assert facts["mass"]["display"] == UNCLASSIFIED_DISPLAY and facts["mass"]["missing"]
    # La cifra viaja con el dato para que la interfaz la formatee; hoy no hay ninguna.
    assert all(fact["figure"] is None for fact in row["facts"])



def test_what_the_station_did_is_not_said_of_emma_and_earth_dependence_names_it() -> None:
    # La guía desde Tierra es de la estación (el estudio de 2019), no de la consola de EMMA.
    assert "en la estación" in DIMENSIONS["training"]["values"]["ground-guided"]
    (earth,) = [
        item for item in summary()["kb_coverage"]["terms"]
        if item["term"] == "dependencia de Tierra"
    ]
    assert DIMENSIONS["training"]["display"] in earth["note"]
    # Lo que se dice de «sin clasificar» nombra también las dimensiones nuevas.
    assert "energía" in cost_module.UNCLASSIFIED_NOTE
    assert "calibrar" in cost_module.UNCLASSIFIED_NOTE


# --------------------------------------------------------------------------- #
# Decimoctava ronda (U18): calibración y formación de lo que se lleva puesto, del dosímetro y
# del laboratorio
# --------------------------------------------------------------------------- #

NEW_DOSE_REFS = {"berger-2017-dosis-3d-dostel", "nasa-srag-protect-astronauts"}


def test_the_ship_dosimeter_is_calibrated_and_the_cumulative_dose_is_not_said() -> None:
    entry = dimensions()["absorbed-dose-rate"]["calibration"]
    assert (entry["value"], entry["rule"]) == ("required", "dosimetro-de-nave-calibrado")
    rule = _rule("dosimetro-de-nave-calibrado")
    assert {item["ref"] for item in rule["sources"]} == NEW_DOSE_REFS
    assert any("calibrated before launch" in item["quote"] for item in rule["sources"])
    assert any("area monitoring" in item["quote"] for item in rule["sources"])
    # Dice de qué dosímetros es lo leído y lo que no dice; EMMA no nombra el suyo.
    for said in ("DosTel", "no dicen cada cuánto", "EMMA no dice cuál"):
        assert said in rule["basis"], said
    # La dosis acumulada llega de un dosímetro sin nombre: ni calibración ni formación.
    dose = dimensions()["cumulative-dose"]
    assert dose["calibration"]["value"] == dose["training"]["value"] == UNCLASSIFIED
    searched = summary()["searched"]
    assert "Crew Active Dosimeters" in _searched_by(searched, "calibration")["cumulative-dose"][
        "searched"
    ]
    for key in DOSE:
        assert key in _searched_by(searched, "training"), key


def test_the_red_series_analyzers_are_calibrated_on_earth_not_aboard() -> None:
    rule = _rule("hemograma-serie-roja-con-analizador-calibrado")
    (source,) = rule["sources"]
    assert source["ref"] == "kunz-2017-hematologic-indices-iss"
    assert source["quote"].startswith("All CBCs were performed using calibrated, automated")
    assert "Tierra" in rule["basis"] and "no la de un equipo de a bordo" in rule["basis"]
    held = {
        key for key, item in dimensions().items()
        if item["calibration"]["rule"] == "hemograma-serie-roja-con-analizador-calibrado"
    }
    assert held == RED_SERIES
    # Los leucocitos se contaron en otro estudio, que no nombra la calibración.
    calibration = _searched_by(summary()["searched"], "calibration")
    for key in WHITE_CELLS:
        assert dimensions()[key]["calibration"]["value"] == UNCLASSIFIED, key
        assert key in calibration, key
    assert "standard clinical hematology analyzer" in calibration["leukocytes"]["searched"]


def test_the_actigraph_calibration_is_the_manufacturer_s_and_leaves_its_not_found() -> None:
    rule = _rule("actigrafo-con-recalibracion-del-fabricante")
    refs = {item["ref"] for item in rule["sources"]}
    assert refs == {"nasa-issmp-on-orbit-hardware-2016", "philips-actiwatch-service-offerings-2016"}
    assert any("Modified commercial-off-the-shelf" in item["quote"] for item in rule["sources"])
    assert any("light sensor calibration" in item["quote"] for item in rule["sources"])
    # Lo que la regla no dice: que la unidad de la estación se recalibrara, ni qué actígrafo
    # es el de EMMA.
    assert "no dice que la unidad de la estación" in rule["basis"]
    assert "EMMA no dice qué actígrafo es el suyo" in rule["basis"]
    searched = summary()["searched"]
    for key in ACTIGRAPHY:
        assert dimensions()[key]["calibration"]["rule"] == rule["id"], key
        # Sale del «no encontrado» de la calibración y sigue en el de la masa.
        assert key not in _searched_by(searched, "calibration"), key
        assert key in _searched_by(searched, "mass"), key
    # La hoja del fabricante no es de ninguna clase del registro, y lo dice.
    card = registry.get("philips-actiwatch-service-offerings-2016")
    assert card.evidence_type is None and card.outside_enum == ("evidence_type",)


def test_training_before_the_mission_says_who_and_where_in_the_word_itself() -> None:
    held = {
        key: (item["training"]["value"], item["training"]["rule"])
        for key, item in dimensions().items()
        if item["training"]["value"] in {"station-trained", "analog-trained"}
    }
    assert held == {
        **dict.fromkeys(
            WHITE_CELLS, ("station-trained", "leucocitos-extraccion-instruida-antes-de-la-mision")
        ),
        **dict.fromkeys(WORN, ("analog-trained", "wearable-con-formacion-previa-en-analogo")),
    }
    # El sitio va en la palabra: donde no sale la regla (el detalle de alerta, los recuentos),
    # lo leído en un análogo en Tierra no se enseña ni se cuenta como de vuelo.
    station = DIMENSIONS["training"]["values"]["station-trained"]
    analog = DIMENSIONS["training"]["values"]["analog-trained"]
    assert "en la estación" in station and "antes de la misión" in station
    assert "análogo en Tierra" in analog and "estación" not in analog
    counts = {
        item["value"]: item["count"]
        for row in summary()["dimensions"] if row["key"] == "training"
        for item in row["values"]
    }
    assert (counts["station-trained"], counts["analog-trained"]) == (
        len(WHITE_CELLS), len(WORN),
    )
    blood = _rule("leucocitos-extraccion-instruida-antes-de-la-mision")
    (source,) = blood["sources"]
    assert source["ref"] == "crucian-2015-adaptive-immunity-iss"
    assert "instructed in phlebotomy prior to mission start" in source["quote"]
    worn = _rule("wearable-con-formacion-previa-en-analogo")
    assert {item["ref"] for item in worn["sources"]} == {"ntrs-20190000238"}
    assert any("Human Exploration Research Analog" in item["quote"] for item in worn["sources"])
    assert "análogo en Tierra, no la estación" in worn["basis"]
    assert "EMMA no dice que su wearable sea ese" in worn["basis"]
    assert registry.get("ntrs-20190000238").evidence_context == "analog_isolation"
    # El pulsioxímetro, el sensor de temperatura y el acelerómetro llevan otro equipo en EMMA:
    # se dice lo que se buscó, no se les pasa la formación de la camiseta.
    training = _searched_by(summary()["searched"], "training")
    for key in ("oxygen-saturation", "body-temperature", "loading-impacts", *ACTIGRAPHY):
        assert dimensions()[key]["training"]["value"] == UNCLASSIFIED, key
        assert key in training, key


def test_worn_sensors_dosimeter_and_laboratory_are_decided_or_searched() -> None:
    # Lo que la ronda tenía que buscar: cada par está decidido con su regla o declarado como
    # buscado y no encontrado. Ninguno queda sin clasificar y sin aviso.
    sampled = {
        key for key, item in costs().items()
        if item["mode"] in {"laboratory", "periodic-invasive"}
    }
    # Lo continuo y pasivo menos lo que no se lleva puesto: el registro de ejercicio, que no es de
    # la ronda, y el dosímetro de la nave, que va con la dosis acumulada.
    continuous = {key for key, item in costs().items() if item["mode"] == "continuous-passive"}
    worn = continuous - {"exercise-minutes"} - DOSE
    assert worn == WORN | ACTIGRAPHY | {"oxygen-saturation", "body-temperature", "loading-impacts"}
    # La química de la orina de 24 horas del riesgo renal (U5) y la densitometría (U3) entraron en
    # la misma ronda después de esta búsqueda, que no las miró, y la masa magra por DXA
    # (decimonovena ronda, U13) una ronda después: quedan fuera de su alcance, sin clasificar y
    # sin aviso, como el registro de ejercicio (lo comprueba el bucle de abajo).
    renal = {code.key for code in RENAL_URINE_CHEMISTRY} | DENSITOMETRY_KEYS | {"dxa-lean-mass"}
    scope = (worn | sampled | DOSE) - renal
    searched = summary()["searched"]
    for dimension in ("calibration", "training"):
        found = _searched_by(searched, dimension)
        for key in scope:
            entry = dimensions()[key][dimension]
            if entry["value"] == UNCLASSIFIED:
                assert key in found, (key, dimension)
            else:
                assert entry["rule"] is not None, (key, dimension)
    # Lo que no era de la ronda (el registro de ejercicio, lo que se anota en la consola) sigue
    # sin clasificar y sin aviso: no se buscó, y no se dice que se buscara.
    for dimension in ("calibration", "training"):
        assert "exercise-minutes" not in _searched_by(searched, dimension), dimension
        assert not renal & set(_searched_by(searched, dimension)), dimension


def test_the_kb_list_says_what_calibration_and_training_leave_to_each_rule() -> None:
    notes = {item["term"]: item["note"] for item in summary()["kb_coverage"]["terms"]}
    # La calibración leída no dice cada cuánto ni quién; la formación no dice dónde.
    assert "no cada cuánto" in notes["calibración"]
    assert DIMENSIONS["calibration"]["values"]["required"] in notes["calibración"]
    assert "análogo en Tierra" in notes["entrenamiento"]
    assert DIMENSIONS["training"]["display"] in notes["entrenamiento"]
    assert "cuánto duró" in notes["entrenamiento"]


def test_the_alert_check_cost_shows_the_training_word_as_the_backend_writes_it() -> None:
    row = check_cost._indicator_cost("leukocytes")
    facts = {fact["key"]: fact for fact in row["facts"]}
    word = DIMENSIONS["training"]["values"]["station-trained"]
    assert (facts["training"]["display"], facts["training"]["missing"]) == (word, False)
    assert facts["calibration"]["display"] == UNCLASSIFIED_DISPLAY
    assert facts["calibration"]["missing"] is True
    # Lo leído en un análogo llega al detalle de alerta diciendo que es de un análogo.
    worn = {fact["key"]: fact for fact in check_cost._indicator_cost("heart-rate")["facts"]}
    assert "análogo en Tierra" in worn["training"]["display"]


# --------------------------------------------------------------------------- #
# Decimonovena ronda (U18): las dimensiones de la conversación de ideación (~673): almacenamiento,
# frecuencia posible y capacidad de automatización. «Valor clínico» no entra, y la lista lo dice.
# --------------------------------------------------------------------------- #

CONVERSATION = (
    Path(__file__).resolve().parents[2] / "docs" / "contexto" / "conversacion-ideacion-v1.md"
)
CONVERSATION_DIMENSIONS = ("storage", "frequency", "automation")
SALIVA = {"cortisol-salivary", "latent-virus-shedding"}
RENAL = {code.key for code in RENAL_URINE_CHEMISTRY}
RATIOS = {"neutrophil-lymphocyte-ratio", "bun-creatinine-ratio"}
PVT = {"pvt-mean-rt", "pvt-lapses"}
URINE_SAMPLES = {"urine-volume-24h", "ntx-telopeptide"}


def _serum() -> set[str]:
    """Lo que EMMA mide en suero: la sangre menos el hemograma (escrito a mano arriba)."""
    blood = {k for k, item in costs().items() if item["equipment"] == BLOOD}
    return blood - WHITE_CELLS - RED_SERIES


def _conversation_terms() -> list[str]:
    """La lista literal de la conversación de ideación, leída del documento del equipo."""
    line = next(
        line for line in CONVERSATION.read_text(encoding="utf-8").splitlines()
        if line.startswith("valor clínico / ") and "capacidad de automatización" in line
    )
    return [term.strip() for term in line.rstrip(".").split(" / ")]


def _held(dimension: str) -> dict[str, set[str]]:
    """Qué indicadores tiene cada par valor-regla de una dimensión (lo sin clasificar, fuera)."""
    held: dict[str, set[str]] = {}
    for key, item in dimensions().items():
        entry = item[dimension]
        if entry["value"] != UNCLASSIFIED:
            held.setdefault(f"{entry['value']}|{entry['rule']}", set()).add(key)
    return held


def test_every_term_of_the_conversation_has_its_place_or_says_it_does_not_enter() -> None:
    # La lista del documento, en su orden: si la conversación cambia, falla aquí.
    assert [term for term, _ in cost_module.CONVERSATION_TERMS] == _conversation_terms()
    coverage = summary()["conversation_coverage"]
    assert "conversación" in coverage["display"].lower()
    assert "valor clínico / tiempo de astronauta" in coverage["origin"]
    for item, (term, field) in zip(coverage["terms"], cost_module.CONVERSATION_TERMS, strict=True):
        assert (item["term"], item["field"]) == (term, field)
        if field is cost_module.EXCLUDED:
            assert (item["kind"], item["display"]) == ("excluded", cost_module.EXCLUDED_DISPLAY)
        elif item["kind"] == "dimension":
            assert item["display"] == DIMENSIONS[field]["display"]
        else:
            assert item["display"] == cost_module.KB_FIELDS[field]
    assert set(CONVERSATION_DIMENSIONS) <= set(DIMENSIONS)
    # Las tres nuevas llevan nota con lo que son; la dependencia de Tierra, la misma que en KB §9.
    notes = {item["term"]: item["note"] for item in coverage["terms"]}
    assert "muestra" in notes["almacenamiento"] and "volumen de datos" in notes["almacenamiento"]
    assert "No se deduce" in notes["frecuencia posible"]
    assert "deducción de EMMA" in notes["capacidad de automatización"]
    assert notes["dependencia de Tierra"] == cost_module.KB_NOTES["dependencia de Tierra"]
    # Y la lista de KB §9 sigue entera, con la misma función.
    kb = summary()["kb_coverage"]
    assert [item["term"] for item in kb["terms"]] == [term for term, _ in cost_module.KB_TERMS]
    assert all(item["kind"] != "excluded" for item in kb["terms"])


def test_clinical_value_is_declared_out_with_its_reason() -> None:
    (clinical,) = [
        item for item in summary()["conversation_coverage"]["terms"]
        if item["term"] == "valor clínico"
    ]
    assert clinical["kind"] == "excluded" and clinical["field"] is None
    assert "juicio clínico" in clinical["note"] and "C6" in clinical["note"]
    assert "no puntúa" in clinical["note"]


def test_a_conversation_term_without_a_place_or_a_reason_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cost_module, "CONVERSATION_TERMS", (("almacenamiento", "storage_"),))
    with pytest.raises(ValueError, match="Conversación de ideación: «almacenamiento».*no tiene"):
        cost_module.conversation_coverage()
    # Y falla al cargar las dimensiones, no en la primera petición del resumen.
    with pytest.raises(ValueError, match="no tiene"):
        cost_module.dimensions.__wrapped__()
    # Un término que no entra sin motivo no se publica: lo que se deja fuera se dice.
    monkeypatch.setattr(cost_module, "CONVERSATION_TERMS", (("coste moral", None),))
    with pytest.raises(ValueError, match="no dice por qué"):
        cost_module.conversation_coverage()


def test_automation_is_a_deduction_from_the_class_and_every_word_says_so() -> None:
    expected = {
        "continuous-passive": "passive", "periodic-noninvasive": "operator",
        "periodic-invasive": "sample-and-analysis", "laboratory": "sample-and-analysis",
        "derived": "computed",
    }
    # Donde la clase no decide, la deducción no alcanza: la DXA es de «laboratorio» y no toma
    # muestra (tampoco la de la masa magra, la misma máquina), y la dosis acumulada es «calculada»
    # y EMMA no la calcula. El glucómetro toma muestra pero la analiza en el propio aparato (CDC):
    # «con muestra y análisis» dice que se analiza aparte, y la clase no decide. Igual el test
    # casero de ovulación: la tira cambia de color o enseña el signo ella misma (MedlinePlus,
    # releída el 2026-11-15, en su nota de `searched_not_found`).
    undecided = {
        *DENSITOMETRY_KEYS, "dxa-lean-mass", "cumulative-dose", "glucose-capillary",
        "ovulation-test",
    }
    for key, item in costs().items():
        entry = dimensions()[key]["automation"]
        if key in undecided:
            assert entry["value"] == UNCLASSIFIED, key
            continue
        assert entry["value"] == expected[item["mode"]], key
        assert cost_module.DEDUCED_MARK in entry["display"], key
        assert cost_module.DEDUCED_MARK in entry["basis"], key
        assert str(entry["rule"]).startswith("automatizacion-"), key
    # La deducción alcanza a todos, y la fila del resumen dice que es deducida; las demás, no.
    rows = {row["key"]: row for row in summary()["dimensions"]}
    assert rows["automation"]["deduced"] is True
    assert rows["automation"]["unclassified"] == len(undecided)
    assert all(row["deduced"] is False for key, row in rows.items() if key != "automation")
    assert summary()["deduced_display"] == cost_module.DEDUCED_DISPLAY
    assert "no sale de una frase leída" in summary()["deduced_note"]
    words = DIMENSIONS["automation"]["values"].values()
    assert all(cost_module.DEDUCED_MARK in word for word in words)
    # Las reglas de la deducción no fingen fuente.
    for rule in summary()["rules"]:
        if rule["id"].startswith("automatizacion-"):
            assert rule["sources"] == [] and rule["discrepancies"] == []


def test_a_deduction_cannot_cite_a_reading() -> None:
    reading = {"ref": "csa-bio-monitor", "quote": "x", "where": "y", "read_on": "2026-10-31"}
    rule = {
        **RULE, "set": {"automation": "passive"}, "basis": "lo deduce EMMA", "sources": [reading],
    }
    with pytest.raises(ValueError, match="deducción de EMMA y la regla cita lecturas"):
        classify(RAW, [rule])


def test_a_data_rate_is_not_a_data_volume() -> None:
    def rule(quote: str) -> dict[str, Any]:
        reading = {"ref": "csa-bio-monitor", "quote": quote, "where": "y", "read_on": "2026-10-31"}
        return {
            **RULE, "set": {"storage": {"figure": "1", "unit": "MB"}}, "basis": "leído",
            "sources": [reading],
        }

    for rate in ("records 1 MB/s", "records 1 MB / day", "records 1 MB per day"):
        with pytest.raises(ValueError, match="no está en ninguna frase leída"):
            classify(RAW, [rule(rate)])
    assert classify(RAW, [rule("stores 1 MB of data")])["a"]["storage"]["value"] == "stated"


def test_a_deduction_that_does_not_say_so_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    rule = {**RULE, "set": {"automation": "passive"}, "basis": "clase «continuo y pasivo»"}
    with pytest.raises(ValueError, match="deducción de EMMA y el `basis` no lo dice"):
        classify(RAW, [rule])
    said = {**rule, "basis": "clase «continuo y pasivo»: lo deduce EMMA"}
    assert classify(RAW, [said])["a"]["automation"]["value"] == "passive"
    # Una dimensión leída no pide la marca.
    assert classify(RAW, [RULE])["a"]["processing"]["value"] == "on-device"
    # Y una palabra de la dimensión deducida que no diga quién la deduce tampoco se carga.
    spec = {
        **DIMENSIONS["automation"],
        "values": {**DIMENSIONS["automation"]["values"], "passive": "pasiva: el sensor registra"},
    }
    monkeypatch.setitem(cost_module.DIMENSIONS, "automation", spec)
    with pytest.raises(ValueError, match="no dice que la deduce EMMA"):
        classify(RAW, [said])


def test_frequency_is_only_the_calendar_a_protocol_gave() -> None:
    assert _held("frequency") == {
        "continuous|wearable-medida-continua": WORN,
        "continuous-in-periods|actigrafia-24-7-en-periodos-de-14-dias": ACTIGRAPHY,
        "mission-timepoints|sangre-del-protocolo-en-sesiones-de-vuelo": _serum(),
        "mission-timepoints|leucocitos-en-tres-sesiones-de-vuelo": WHITE_CELLS,
        "mission-timepoints|serie-roja-en-tres-sesiones-de-vuelo": RED_SERIES,
        "mission-timepoints|saliva-en-siete-sesiones": SALIVA,
        "mission-timepoints|orina-de-vuelo-en-cinco-tomas": URINE_SAMPLES,
        "mission-timepoints|prueba-de-reaccion-en-las-sesiones-del-protocolo": PVT,
        "ground-only|perfil-litiasico-anual-y-posvuelo": RENAL,
        "ground-only|densitometria-antes-y-despues-del-vuelo": DENSITOMETRY_KEYS,
        "no-own-schedule|calculo-sin-almacen-ni-calendario-propios": RATIOS,
    }
    standard = _rule("sangre-del-protocolo-en-sesiones-de-vuelo")
    quotes = " ".join(source["quote"] for source in standard["sources"])
    assert "during the first month, at mid-flight, and during the last month" in quotes
    assert "5 times during flight" in quotes
    # La regla dice de quién es el calendario y que no es el de cada analito.
    assert "no el de cada analito" in standard["basis"]
    assert "marcadores tumorales" in standard["basis"]
    worn = _rule("wearable-medida-continua")
    assert any("continuously measuring physiological data" in s["quote"] for s in worn["sources"])
    assert "EMMA no dice que su wearable sea ese" in worn["basis"]
    acti = _rule("actigrafia-24-7-en-periodos-de-14-dias")
    assert any("14-day periods" in s["quote"] for s in acti["sources"])
    assert any("24/7" in s["quote"] for s in acti["sources"])
    urine = _rule("orina-de-vuelo-en-cinco-tomas")
    assert {d["ref"] for d in urine["discrepancies"]} == {
        "hardy-2025-spaceflight-standard-measures", "mehta-2017-latent-virus-iss",
    }
    pvt = _rule("prueba-de-reaccion-en-las-sesiones-del-protocolo")
    assert any("psychomotor vigilance test" in s["quote"] for s in pvt["sources"])
    # La frase que pone la batería en vuelo está entre las fuentes, no solo en la regla.
    assert any("occurred during flight" in s["quote"] for s in pvt["sources"])
    assert "PVT-B" in pvt["basis"]
    # Un negativo («sin toma en vuelo») lleva la frase que lo dice, y su matiz al lado.
    renal = _rule("perfil-litiasico-anual-y-posvuelo")
    assert any("no inflight urine collections" in s["quote"] for s in renal["sources"])
    assert any("5 times during flight" in d["quote"] for d in renal["discrepancies"])
    # La palabra del actígrafo dice sola las pausas: viaja sin la regla al detalle de alerta.
    assert "entre periodos no" in DIMENSIONS["frequency"]["values"]["continuous-in-periods"]
    # Lo que ningún calendario leído alcanza queda sin clasificar y, si se buscó, con su aviso.
    searched = _searched_by(summary()["searched"], "frequency")
    for key in (
        "oxygen-saturation", "body-temperature", "loading-impacts", "body-weight", "systolic-bp",
        "orthostatic-drop", "vo2-peak", "urine-specific-gravity",
    ):
        assert dimensions()[key]["frequency"]["value"] == UNCLASSIFIED, key
        assert key in searched, key
    assert "periodically in flight" in searched["body-weight"]["searched"]
    # Las ecografías, el dinamómetro, la dosimetría, el ejercicio y lo anotado en la consola no se
    # buscaron: sin clasificar y sin aviso.
    for key in (
        *SCANS, "grip-strength-left", "absorbed-dose-rate", "cumulative-dose", "mood-valence",
        "exercise-minutes",
    ):
        assert dimensions()[key]["frequency"]["value"] == UNCLASSIFIED, key
        assert key not in searched, key


def test_storage_is_the_fate_of_the_sample_each_study_read() -> None:
    assert _held("storage") == {
        "sample-frozen-aboard|suero-congelado-a-bordo": _serum(),
        "sample-ambient-aboard|leucocitos-devueltos-a-temperatura-ambiente": WHITE_CELLS,
        "sample-ambient-aboard|serie-roja-en-bolsas-a-temperatura-ambiente": RED_SERIES,
        "sample-ambient-aboard|saliva-virus-a-temperatura-ambiente": {"latent-virus-shedding"},
        "sample-ambient-aboard|saliva-cortisol-secada-a-temperatura-ambiente": {
            "cortisol-salivary",
        },
        "nothing-aboard|perfil-litiasico-anual-y-posvuelo": RENAL,
        "nothing-aboard|densitometria-antes-y-despues-del-vuelo": DENSITOMETRY_KEYS,
        "no-own-storage|calculo-sin-almacen-ni-calendario-propios": RATIOS,
    }
    frozen = _rule("suero-congelado-a-bordo")
    assert any("-96 °C ISS freezer" in s["quote"] for s in frozen["sources"])
    assert any("frozen and returned" in s["quote"] for s in frozen["sources"])
    red = _rule("serie-roja-en-bolsas-a-temperatura-ambiente")
    assert any("customized blood pouches" in s["quote"] for s in red["sources"])
    # Lo que matiza se enseña: una sangre a temperatura ambiente devuelta del espacio es rara.
    (rare,) = red["discrepancies"]
    assert "rarely returned from space" in rare["quote"] and rare["note"].strip()
    virus = _rule("saliva-virus-a-temperatura-ambiente")
    (frozen_saliva,) = virus["discrepancies"]
    assert "stored frozen until processing" in frozen_saliva["quote"]
    assert "no dice si a bordo" in frozen_saliva["note"]
    # El volumen de datos es una cifra, y hoy ninguna frase leída la da: ni una.
    assert "storage" in cost_module.QUANTITIES
    assert all(item["storage"]["figure"] is None for item in dimensions().values())
    searched = _searched_by(summary()["searched"], "storage")
    for key in (
        *WORN, *ACTIGRAPHY, "oxygen-saturation", "urine-volume-24h", "ntx-telopeptide",
        "urine-specific-gravity",
    ):
        assert dimensions()[key]["storage"]["value"] == UNCLASSIFIED, key
        assert key in searched, key
    assert "records vital sign data" in searched["heart-rate"]["searched"]
    assert "frozen until return to Earth" in searched["urine-volume-24h"]["searched"]


def test_a_data_volume_figure_follows_the_same_rule_as_the_mass() -> None:
    rule = {
        **FIGURE_RULE, "set": {"storage": {"figure": "1", "unit": "MB"}},
        "sources": [{**FIGURE_RULE["sources"][0], "quote": "an internal memory of 1 MB"}],
    }
    found = classify(RAW, [rule])["a"]["storage"]
    assert found["value"] == cost_module.STATED and found["display"] == "1 MB"
    assert found["figure"] == {"amount": 1.0, "decimals": 0, "unit": "MB", "figure": "1"}
    with pytest.raises(ValueError, match="no está en ninguna frase"):
        classify(RAW, [{**rule, "set": {"storage": {"figure": "2", "unit": "MB"}}}])
    with pytest.raises(ValueError, match="unidad"):
        classify(RAW, [{**rule, "set": {"storage": {"figure": "1", "unit": "L"}}}])
    # La frecuencia es vocabulario: no admite cifra.
    with pytest.raises(ValueError, match="no es una cifra"):
        classify(RAW, [{**rule, "set": {"frequency": {"figure": "1", "unit": "MB"}}}])


def test_the_unclassified_note_and_the_alert_detail_carry_the_new_dimensions() -> None:
    assert "muestra o el dato" in cost_module.UNCLASSIFIED_NOTE
    assert "cuando se quiera" in cost_module.UNCLASSIFIED_NOTE
    row = check_cost._indicator_cost("heart-rate")
    facts = {fact["key"]: fact for fact in row["facts"]}
    # La deducción llega al detalle de alerta diciendo que lo es, en la propia palabra.
    assert cost_module.DEDUCED_MARK in facts["automation"]["display"]
    assert facts["automation"]["missing"] is False
    assert facts["frequency"]["display"] == DIMENSIONS["frequency"]["values"]["continuous"]
    assert facts["storage"]["display"] == UNCLASSIFIED_DISPLAY and facts["storage"]["missing"]
    body = summary()
    assert body["unclassified"] == sum(row["unclassified"] for row in body["dimensions"])
    assert len(body["dimensions"]) == len(DIMENSIONS) == 11
