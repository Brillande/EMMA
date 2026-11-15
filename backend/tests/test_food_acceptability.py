"""El criterio 6,0 de la comida, evaluado (decisión del usuario, 2026-10-15).

Cada valoración de `food-acceptability` por debajo de 6,0 se marca «por debajo del criterio de
aceptable de la comida», con la frase de NASA-STD-3001 Vol. 2 Rev F [V2 7002] y su página
(`data/instruments_read.json`, leída en el PDF oficial el 2026-10-16). Lo que se fija aquí:

- el 6,0 es el que la frase escribe, y un criterio que la frase no escribe no se adopta;
- el catálogo (guía, `reference_low=6`) y lo leído dicen la misma cifra;
- la marca es estricta («6.0 or better» es aceptable), compara el valor sin redondear y no deja
  que el redondeo a un decimal la contradiga;
- es una marca sobre la COMIDA: el motor no la conoce, la ruta no escribe nada y el veredicto
  de `menu-fatigue` es el mismo que en `main` (invariante 5).
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import datetime as dt
import inspect
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.advisor import recommendations
from app.analysis import baseline, food_acceptability, risk, trend
from app.analysis.food_acceptability import (
    APPLIES,
    MARK,
    NO_CRITERION,
    NOT_MEASURED,
    SCOPE,
    describe,
    is_below,
    value_text,
)
from app.api import nutrition, routes
from app.core import versioning
from app.evidence import instruments_read, registry
from app.evidence.instruments_read import InstrumentsError, validate
from app.ingest.codes import CATALOG, ReferenceBasis
from app.ingest.fhir import ObservationType, VitalObservation, observation
from app.text_guard import check

RAW: dict[str, Any] = json.loads(instruments_read.READ_PATH.read_text(encoding="utf-8"))
KEY = "food-acceptability"
QUOTE = (
    "A NASA food item measuring an overall acceptability rating of 6.0 or better on a 9-point "
    "hedonic scale for the duration of the mission is considered acceptable."
)
REFERENCE = dt.datetime(2026, 12, 1, 7, tzinfo=dt.UTC)


def _criterion() -> dict[str, Any]:
    found = instruments_read.scale_criterion(KEY)
    assert found is not None
    return found


def _rating(
    value: float, days: int = 0, kind: ObservationType = ObservationType.MEASURED
) -> VitalObservation:
    return observation(
        KEY, value, REFERENCE + dt.timedelta(days=days), "crew-01", "manual",
        observation_type=kind,
        model_version=None if kind is ObservationType.MEASURED else "modelo-de-prueba",
    )


# --------------------------------------------------------------------------- #
# Lo leído: la frase, su página y la cifra que escribe
# --------------------------------------------------------------------------- #


def test_the_criterion_is_the_figure_the_standard_writes() -> None:
    criterion = _criterion()
    assert (criterion["value"], criterion["literal"]) == (6.0, "6.0 or better")
    # En su idioma, sin traducir: el de la fuente de la escala.
    assert criterion["language"] == "en"
    statement = criterion["statement"]
    assert statement["quote"] == QUOTE
    assert criterion["literal"] in statement["quote"]
    assert statement["ref"] == "nasa-std-3001-vol2-rev-f"
    assert statement["url"] == registry.get("nasa-std-3001-vol2-rev-f").url
    assert statement["url"].startswith("https://www.nasa.gov/")
    # La página y el requisito, para poder ir a comprobarlo con el PDF delante.
    assert "[V2 7002]" in statement["where"] and "página 119" in statement["where"]
    assert "7.1.1.2 Food Acceptability" in statement["where"]
    # Leída otro día que el resto del fichero: lleva su fecha, y el resto sigue con la suya.
    assert statement["read_on"] == "2026-10-16"
    assert instruments_read.statement("hedonic-anchors-panel")["read_on"] == RAW["read_on"]
    assert statement["extent"] == "partial"


def test_the_catalogue_guideline_and_the_read_criterion_say_the_same_figure() -> None:
    code = CATALOG[KEY]
    assert code.reference_low == _criterion()["value"]
    # Sigue siendo una guía sobre la comida: nunca un umbral de alarma.
    assert code.reference_basis is ReferenceBasis.GUIDELINE
    assert code.critical_low is None and code.critical_high is None


def test_reading_the_criterion_did_not_add_labels_to_the_scale() -> None:
    labels = instruments_read.scale_labels(KEY)
    assert labels is not None
    # Los rótulos son los leídos (del 2 al 8, desde el 2026-10-20); el criterio no añade ninguno.
    assert [item["value"] for item in labels["labels"]] == list(range(1, 10))
    assert [item["ref"] for item in labels["sources"]] == [
        "douglas-2025-iss-food-acceptability", "ahmed-1981-high-density-foods",
        "massa-2015-leafy-greens-iss",
    ]
    assert "v2-7002-acceptable-6" not in instruments_read.scale_statement_ids(KEY)
    assert instruments_read.scale_criterion("no-existe") is None


def _hedonic_criterion(raw: dict[str, Any]) -> dict[str, Any]:
    criterion: dict[str, Any] = raw["scales"][KEY]["criterion"]
    return criterion


def _statement(raw: dict[str, Any], statement_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(
        item for item in raw["statements"] if item["id"] == statement_id
    )
    return found


@pytest.mark.parametrize(
    ("change", "message"),
    [
        # Lo que la decisión pide: si la frase no escribe el 6,0 así, no se adopta.
        (lambda raw: _hedonic_criterion(raw).update(value=6.5), "no se adopta"),
        (lambda raw: _hedonic_criterion(raw).update(value=7), "no se adopta"),
        (lambda raw: _hedonic_criterion(raw).update(literal="or better"), "no se adopta"),
        (
            lambda raw: _hedonic_criterion(raw).update(literal="7.0 or better", value=7.0),
            "no está escrito en la frase",
        ),
        (lambda raw: _hedonic_criterion(raw).update(literal=""), "no está escrito en la frase"),
        (lambda raw: _hedonic_criterion(raw).update(value=True), "es una cifra"),
        (lambda raw: _hedonic_criterion(raw).update(value="6.0"), "es una cifra"),
        (
            lambda raw: _hedonic_criterion(raw).update(statement="no-existe"),
            "no apunta a ninguna frase",
        ),
        (
            lambda raw: (
                _statement(raw, "v2-7002-acceptable-6").update(
                    quote=QUOTE.replace("6.0", "12.0")
                ),
                _hedonic_criterion(raw).update(literal="12.0 or better", value=12.0),
            ),
            "fuera del rango",
        ),
        (
            lambda raw: _statement(raw, "v2-7002-acceptable-6").update(read_on="octubre"),
            "no es una fecha",
        ),
    ],
)
def test_a_criterion_that_the_sentence_does_not_write_is_refused(change: Any, message: str) -> None:
    raw = copy.deepcopy(RAW)
    change(raw)
    with pytest.raises(InstrumentsError, match=message):
        validate(raw)


def test_a_criterion_is_refused_on_a_scale_that_does_not_watch_its_low_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Se marca lo que queda por debajo: en una escala que vigila el alto, eso sería lo bueno."""
    flipped = dataclasses.replace(CATALOG[KEY], concerning="high")
    monkeypatch.setitem(instruments_read.CATALOG, KEY, flipped)
    with pytest.raises(InstrumentsError, match="extremo bajo"):
        validate(copy.deepcopy(RAW))


def test_the_file_as_it_is_passes_and_a_statement_without_a_date_takes_the_files() -> None:
    validate(copy.deepcopy(RAW))
    raw = copy.deepcopy(RAW)
    del _statement(raw, "v2-7002-acceptable-6")["read_on"]
    validate(raw)


# --------------------------------------------------------------------------- #
# La marca
# --------------------------------------------------------------------------- #


def test_six_is_acceptable_and_anything_below_is_marked() -> None:
    assert not is_below(6.0, 6.0)
    assert is_below(5.999, 6.0)
    assert not is_below(9.0, 6.0)
    block = describe(
        "crew-01", [_rating(v, days) for days, v in enumerate([5.0, 6.0, 7.0, 5.96])],
        _criterion(), 10,
    )
    assert (block["rated"], block["below"]) == (4, 2)
    # La última primero.
    assert [item["value"] for item in block["ratings"]] == [5.96, 7.0, 6.0, 5.0]
    assert [item["below"] for item in block["ratings"]] == [True, False, False, True]
    assert [item["mark"] for item in block["ratings"]] == [MARK, None, None, MARK]
    assert block["statement"] == (
        "2 de 4 valoraciones de la comida en el registro de crew-01 quedan "
        f"{MARK} (6,0)."
    )


def test_rounding_never_hides_which_side_of_the_criterion_a_rating_falls_on() -> None:
    # Con el decimal del catálogo, 5,96 se leería «6,0» junto a la marca de «por debajo».
    assert value_text(5.96, 6.0) == "5,96 puntos"
    assert value_text(5.999, 6.0) == "5,999 puntos"
    assert value_text(5.94, 6.0) == "5,9 puntos"
    assert value_text(6.0, 6.0) == "6,0 puntos"
    assert value_text(6.04, 6.0) == "6,0 puntos"
    assert value_text(7.25, 6.0) == "7,2 puntos"
    # Sin criterio no hay lado que proteger: los decimales del catálogo.
    assert value_text(5.96, None) == "6,0 puntos"


def test_only_measured_ratings_of_the_food_count() -> None:
    readings = [
        _rating(4.0),
        _rating(4.0, 1, ObservationType.INFERRED),
        observation("appetite-rating", 2.0, REFERENCE, "crew-01", "manual"),
    ]
    block = describe("crew-01", readings, _criterion(), 10)
    assert (block["rated"], block["below"], block["not_measured_excluded"]) == (1, 1, 1)
    assert block["not_measured_note"] == NOT_MEASURED


def test_the_count_covers_every_rating_and_the_list_shows_the_last_ones() -> None:
    readings = [_rating(5.0, days) for days in range(10)]
    block = describe("crew-01", readings, _criterion(), 3)
    assert (block["rated"], block["below"], block["shown"]) == (10, 10, 3)
    assert len(block["ratings"]) == 3
    assert block["ratings"][0]["effective"] == (REFERENCE + dt.timedelta(days=9)).isoformat()


def test_without_a_read_criterion_nothing_is_marked_and_it_says_so() -> None:
    block = describe("crew-01", [_rating(2.0)], None, 10)
    assert block["criterion"] is None and block["below"] is None
    assert [(item["below"], item["mark"]) for item in block["ratings"]] == [(None, None)]
    assert NO_CRITERION in block["statement"]


def test_no_ratings_is_said_not_counted_as_zero_below() -> None:
    block = describe("crew-01", [], _criterion(), 10)
    assert (block["rated"], block["below"], block["ratings"]) == (0, 0, [])
    assert block["statement"] == "Sin valoraciones de la comida en el registro de crew-01."


def test_every_text_of_the_mark_passes_the_language_guard() -> None:
    texts = [MARK, SCOPE, APPLIES, NO_CRITERION, NOT_MEASURED]
    for block in (
        describe("crew-01", [_rating(5.0), _rating(7.0, 1)], _criterion(), 10),
        describe("crew-01", [_rating(5.0)], None, 10),
        describe("crew-01", [], _criterion(), 10),
    ):
        texts.append(block["statement"])
        if block["criterion"] is not None:
            texts += [block["criterion"]["rule"], block["criterion"]["applies_to"]]
    assert len(set(texts)) > 8, "la prueba tiene que mirar textos de verdad"
    assert [(text, check(text)) for text in texts if check(text)] == []
    # Habla de la comida, no de la persona.
    assert "persona" in SCOPE and "comida" in MARK


# --------------------------------------------------------------------------- #
# La ruta, y lo que no toca (invariante 5)
# --------------------------------------------------------------------------- #


def test_menu_fatigue_leaves_19_of_its_40_ratings_below_the_criterion(client: TestClient) -> None:
    """Medido el 2026-10-16: 40 valoraciones (una al día durante 40 días) y 19 por debajo."""
    assert client.post("/api/simulate", params={"scenario": "menu-fatigue"}).status_code == 201
    body = client.get("/api/nutrition/food-acceptability", params={"limit": 500}).json()
    assert (body["rated"], body["below"], body["shown"]) == (40, 19, 40)
    assert sum(item["mark"] == MARK for item in body["ratings"]) == 19
    assert all(
        (item["value"] < 6.0) is item["below"] for item in body["ratings"]
    )
    assert body["criterion"]["statement"]["quote"] == QUOTE
    assert body["criterion"]["scope"] == SCOPE
    assert {item["source_display"] for item in body["ratings"]} == {"simulador (menu-fatigue)"}


def test_the_nominal_scenario_has_no_food_ratings_to_mark(client: TestClient) -> None:
    assert client.post("/api/simulate", params={"scenario": "nominal"}).status_code == 201
    body = client.get("/api/nutrition/food-acceptability").json()
    assert (body["rated"], body["below"], body["ratings"]) == (0, 0, [])


def test_a_diary_rating_below_the_criterion_is_marked_with_its_source(client: TestClient) -> None:
    for value in (5.5, 8.0):
        response = client.post(
            "/api/diary/entries",
            json={
                "key": KEY, "value": value, "subject": "crew-02", "recorded_by": "CMO",
                # Desde el 2026-10-26 la valoración lleva su alimento (`ingest/food_item.py`).
                "food": "lentejas",
            },
        )
        assert response.status_code == 201, response.text
    body = client.get("/api/nutrition/food-acceptability", params={"subject": "crew-02"}).json()
    assert (body["rated"], body["below"]) == (2, 1)
    marked = [item for item in body["ratings"] if item["below"]]
    assert [(item["value_text"], item["source"]) for item in marked] == [
        ("5,5 puntos", "crew-diary")
    ]


def _imported_names(module: object) -> set[str]:
    tree = ast.parse(inspect.getsource(module))  # type: ignore[arg-type]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            names |= {f"{node.module}.{alias.name}" for alias in node.names}
    return names


def test_the_engine_does_not_know_the_mark_and_the_mark_cannot_decide() -> None:
    for engine in (risk, baseline, trend, recommendations, routes, versioning):
        assert not [name for name in _imported_names(engine) if "food_acceptability" in name]
        assert not [name for name in _imported_names(engine) if "nutrition" in name]
    forbidden = ("RiskEngine", "BaselineEngine", "level_for", "combine_findings", "linear_trend")
    for piece in (food_acceptability, nutrition):
        reads = _imported_names(piece)
        assert not [name for name in reads if name.rsplit(".", 1)[-1] in forbidden]


def _verdict(client: TestClient) -> dict[str, Any]:
    status = client.get("/api/status").json()
    return {
        "overall_level": status["overall_level"],
        "domains": {
            key: [value["level"], value["score"], value["drivers"]]
            for key, value in status["domains"].items()
        },
        "alerts": [[item["domain"], item["level"]] for item in status["alerts"]],
        "recommendations": [
            [item["domain"], (item.get("countermeasure") or {}).get("id")]
            for item in status["recommendations"]
        ],
        "predictions": sorted(item["key"] for item in status["predictions"]),
    }


# `GET /api/status` tras `POST /api/simulate?scenario=menu-fatigue` (40 días, 24 muestras al
# día, semilla por defecto), medido en `main` (02f9c9d) antes de esta pieza, el 2026-10-16. La
# aceptabilidad cae por debajo de 6,0 en 19 valoraciones y el dominio de nutrición sigue
# «nominal»: una guía sobre la comida no alerta, y marcarla no lo cambia.
_DOMAINS = (
    "behavioral", "bone", "cardiovascular", "genitourinary", "immune", "musculoskeletal",
    "neuro-ocular", "nutrition", "radiation",
)
MENU_FATIGUE_VERDICT_ON_MAIN: dict[str, Any] = {
    "overall_level": "nominal",
    "domains": {key: ["nominal", 0.0, []] for key in _DOMAINS},
    "alerts": [],
    "recommendations": [],
    "predictions": [
        "appetite-rating", "energy-intake-daily", "food-acceptability", "hrv-rmssd",
        "ntx-telopeptide", "orthostatic-drop",
    ],
}


def test_menu_fatigue_verdict_is_the_same_as_on_main_and_the_route_writes_nothing(
    client: TestClient,
) -> None:
    assert client.post("/api/simulate", params={"scenario": "menu-fatigue"}).status_code == 201
    assert _verdict(client) == MENU_FATIGUE_VERDICT_ON_MAIN
    ledger = client.get("/api/audit").json()["total_entries"]
    assert client.get("/api/nutrition/food-acceptability").status_code == 200
    assert client.get("/api/audit").json()["total_entries"] == ledger
    assert _verdict(client) == MENU_FATIGUE_VERDICT_ON_MAIN


def test_the_only_nutrition_route_is_a_read() -> None:
    from app.main import app

    methods = {
        (path, method)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/nutrition")
        for method in operations
    }
    assert methods == {("/api/nutrition/food-acceptability", "get")}
