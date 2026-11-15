"""Comida plato a plato: el alimento de cada valoración (decisión del usuario, 2026-10-26).

La valoración de aceptabilidad lleva desde ese día el alimento valorado, en texto libre con una
regla de EMMA (`ingest/food_item.py`): ninguna fuente leída da un vocabulario cerrado. Con él,
la ruta de nutrición cuenta por plato cuántas veces se valoró, en cuántos días y cada valoración
en el tiempo. Lo que se fija aquí:

  * el alimento es un campo OPCIONAL de la lectura: sin él se firma byte a byte como antes, y lo
    firmado antes del campo sigue verificándose (ledger escrito con el código anterior);
  * en FHIR va en `Observation.focus`, solo con `display`;
  * la regla (normalización, longitud, letras, caracteres, filtro de lenguaje) la aplica la ruta
    que firma, con su motivo y sin asiento; el modelo solo exige lo estructural;
  * por plato es descriptivo: ni umbral ni veredicto, y ningún módulo que decide lo lee
    (invariante 5); `rules_version` no cambia.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import food_acceptability
from app.analysis.food_acceptability import MARK, NO_FOOD, REPETITION_NOTE, WITHOUT_FOOD_NOTE
from app.api import diary as diary_module
from app.api.routes import get_store, new_store, reset_store
from app.core.ledger import SALT_FIELD, Identity, canonical_bytes, sha256_hex
from app.core.storage import ObservationStore, _from_payload, _to_payload
from app.core.versioning import rules_version
from app.evidence import instruments_read, registry
from app.ingest import fhir, food_item
from app.ingest.fhir import ObservationType, VitalObservation, observation
from app.text_guard import check

KEY = "food-acceptability"
REJECTED = "food-rejected-fraction"
T = dt.datetime(2026, 9, 3, 12, 0, tzinfo=dt.UTC)
OPERATOR = "Itziar Olabarria"

# Ledger con dos valoraciones del diario (`crew-diary`, con anotador) y una de alta manual,
# escrito con el código ANTERIOR a este campo (commit 2972d93, exportado con `git archive` a una
# carpeta aparte para que no pudiera firmarlo el código nuevo) y guardado tal cual. Los hashes
# son los que firmó aquel código; el `.fhir.json` es lo que aquel código serializaba.
DATA = Path(__file__).parent / "data"
PRE_CHANGE_LEDGER = DATA / "food_pre_item.db"
PRE_CHANGE_FHIR = DATA / "food_pre_item.fhir.json"
PRE_CHANGE_HASHES = [
    "80c8bd9198828d9a7d6b9640c50ba5b32430bf9a996435a67a160036913a4794",
    "d0aaf6f1dcad3683f34986d7229de9d46641a912b451ddda27016d617deb5bef",
    "96477dffc440244dc963128480729bfa17c0b54468309305fccb183cf7650b93",
]


def _rating(
    value: float, food: str | None = None, hours: float = 0, subject: str = "crew-01"
) -> VitalObservation:
    return observation(
        KEY, value, T + dt.timedelta(hours=hours), subject, "crew-diary",
        recorded_by=OPERATOR, food=food,
    )


def _entry(value: float, food: str | None = "lentejas", **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "key": KEY, "value": value, "subject": "crew-01", "recorded_by": OPERATOR, **extra,
    }
    if food is not None:
        body["food"] = food
    return body


@pytest.fixture
def pre_change(tmp_path: Path) -> Iterator[ObservationStore]:
    path = tmp_path / "emma.db"
    shutil.copyfile(PRE_CHANGE_LEDGER, path)
    store = ObservationStore.at(path)
    yield store
    store.engine.dispose()


def _entries(client: TestClient) -> int:
    return int(client.get("/api/audit").json()["total_entries"])


# --------------------------------------------------------------------------- #
# Lo ya firmado
# --------------------------------------------------------------------------- #


def test_what_was_signed_before_the_field_still_verifies(pre_change: ObservationStore) -> None:
    assert pre_change.verify_integrity().ok
    assert [e["content_hash"] for e in pre_change.audit_trail()] == PRE_CHANGE_HASHES
    readings = pre_change.query("crew-01")
    assert [(obs.key, obs.source, obs.food) for obs in readings] == [
        (KEY, "crew-diary", None), (KEY, "crew-diary", None), (KEY, "manual", None),
    ]


def test_a_rating_without_food_serializes_byte_for_byte_as_before(
    pre_change: ObservationStore,
) -> None:
    payloads = [dict(entry.payload) for entry in pre_change.ledger.entries]
    assert len(payloads) == 3
    for payload, signed in zip(payloads, PRE_CHANGE_HASHES, strict=True):
        obs = _from_payload(payload, dt.datetime.fromisoformat(payload["effective"]))
        again = _to_payload(obs)
        assert "food" not in again
        assert list(again) == [key for key in payload if key != SALT_FIELD]
        assert sha256_hex(canonical_bytes({**again, SALT_FIELD: payload[SALT_FIELD]})) == signed
    # Lo de antes se exporta con los URI de hoy: hasta 2026-11-02 eran `https://halo.mission/`
    # (el fixture los conserva tal cual se grabaron) y el FHIR los traduce al leer.
    expected = json.loads(
        PRE_CHANGE_FHIR.read_text(encoding="utf-8").replace(
            "https://halo.mission/", "https://emma.mission/")
    )
    readings = pre_change.query("crew-01")
    assert [json.dumps(obs.to_fhir(), ensure_ascii=False) for obs in readings] == expected
    assert all("focus" not in obs.to_fhir() for obs in readings)


def test_new_ratings_with_food_chain_after_the_old_ones(
    pre_change: ObservationStore, tmp_path: Path
) -> None:
    # Otra identidad: la del diario ya está fijada en ese ledger a la clave con que se escribió.
    pre_change.record_many(
        [_rating(6.0, "lentejas", 48), _rating(4.0, None, 49)], Identity.generate("food-test")
    )
    assert pre_change.verify_integrity().ok
    pre_change.engine.dispose()
    reopened = ObservationStore.at(tmp_path / "emma.db")
    try:
        assert reopened.verify_integrity().ok
        assert [e["content_hash"] for e in reopened.audit_trail()][:3] == PRE_CHANGE_HASHES
        assert [obs.food for obs in reopened.query("crew-01")] == [
            None, None, None, "lentejas", None,
        ]
    finally:
        reopened.engine.dispose()


def test_the_food_is_signed_only_when_it_exists() -> None:
    without = _to_payload(_rating(6.0))
    with_food = _to_payload(_rating(6.0, "lentejas"))
    assert "food" not in without and with_food["food"] == "lentejas"
    assert canonical_bytes(with_food) != canonical_bytes(without)
    assert canonical_bytes(with_food) != canonical_bytes(_to_payload(_rating(6.0, "arroz")))
    # Lo leído del asiento es lo firmado.
    assert _from_payload(with_food, T).food == "lentejas"


# --------------------------------------------------------------------------- #
# FHIR
# --------------------------------------------------------------------------- #


def test_fhir_carries_it_as_the_focus_with_only_a_name() -> None:
    reading = _rating(6.0, "crema de cacahuete")
    resource = reading.to_fhir()
    assert resource["focus"] == [{"display": "crema de cacahuete"}]
    assert reading.validates()
    assert VitalObservation.from_fhir(resource).food == "crema de cacahuete"
    assert VitalObservation.from_fhir(_rating(6.0).to_fhir()).food is None
    # La ficha de la definición leída existe y es la que nombra el módulo.
    card = registry.get(fhir.FOCUS_REF)
    assert card.url == "https://hl7.org/fhir/R4B/observation-definitions.html"
    assert "the subject's diet" in (card.notes or "")


@pytest.mark.parametrize("bad", ["", " lentejas", "lentejas ", 7])
def test_the_model_refuses_a_food_that_is_not_a_trimmed_text(bad: object) -> None:
    with pytest.raises(ValueError, match="alimento"):
        _rating(6.0, bad)  # type: ignore[arg-type]


def test_only_the_food_rating_carries_a_food() -> None:
    with pytest.raises(ValueError, match="solo la aceptabilidad"):
        observation("appetite-rating", 5.0, T, "crew-01", "crew-diary", food="lentejas")


# --------------------------------------------------------------------------- #
# La regla (decisión de diseño de EMMA)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("text", "signed"),
    [
        ("lentejas", "lentejas"),
        ("  Arroz   con\tpollo ", "Arroz con pollo"),
        ("Café (descafeinado)", "Café (descafeinado)"),
        ("Café", "Café"),  # la forma descompuesta se firma compuesta (NFC)
        ("té verde/menta", "té verde/menta"),
        ("pan d’Avila", "pan d’Avila"),
        ("ラーメン", "ラーメン"),
        ("x" * food_item.MAX_LENGTH, "x" * food_item.MAX_LENGTH),
    ],
)
def test_a_good_name_is_normalized_and_passes(text: str, signed: str) -> None:
    assert food_item.problem(text) is None
    assert food_item.normalize(text) == signed


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "vacío"),
        ("   ", "vacío"),
        ("x" * (food_item.MAX_LENGTH + 1), "pasa de 64"),
        ("123", "al menos una letra"),
        # «º» es una letra para Unicode y está entre los signos admitidos: sola no nombra nada.
        ("º.", "al menos una letra"),
        ("<b>pasta</b>", "caracteres que la regla no admite"),
        ("pasta 🍝", "caracteres que la regla no admite"),
        ("pasta\x00", "caracteres que la regla no admite"),
        ("pasta: ver nota", "caracteres que la regla no admite"),
        ("arroz 100 g", "filtro de lenguaje"),
        ("sopa con medicamento", "filtro de lenguaje"),
    ],
)
def test_a_bad_name_is_refused_with_its_reason(text: str, reason: str) -> None:
    found = food_item.problem(text)
    assert found is not None and reason in found


def test_dishes_group_without_case_and_with_normalized_spaces() -> None:
    assert food_item.group_key("Arroz con Pollo") == food_item.group_key(" arroz  con pollo")
    assert food_item.group_key("arroz con pollo") != food_item.group_key("arroz pollo")


def test_the_rule_says_it_is_emmas_and_what_it_rests_on() -> None:
    described = food_item.describe(KEY)
    assert described["status"] == "design" and described["required"] is True
    assert described["requirement_note"] == food_item.REQUIRED_NOTE
    assert "EMMA" in described["status_display"] and "sin validar" in described["status_display"]
    assert [item["id"] for item in described["basis"]] == list(food_item.BASIS)
    crew = instruments_read.statement("hedonic-anchors-crew")
    assert "rated each food or beverage" in crew["quote"]
    assert "A NASA food item" in instruments_read.statement("v2-7002-acceptable-6")["quote"]
    # La fracción rechazada lleva la misma regla, pero el plato es opcional (decimonovena ronda).
    optional = food_item.describe(REJECTED)
    assert optional["required"] is False
    # Y con su rótulo: ahí el alimento no se valora, es del que se deja la fracción.
    assert optional["label"] == food_item.REJECTED_LABEL != described["label"]
    assert set(food_item.LABELS) == food_item.KEYS
    assert optional["requirement_note"] == food_item.OPTIONAL_NOTE
    assert optional["rule"] == described["rule"]
    with pytest.raises(KeyError):
        food_item.describe("appetite-rating")
    texts = [
        food_item.RULE, food_item.WHY_FREE_TEXT, food_item.GROUPING, food_item.MISSING,
        food_item.NOT_ALLOWED_HERE, food_item.REQUIRED_NOTE, food_item.OPTIONAL_NOTE,
        food_item.REJECTED_LABEL, described["status_display"],
    ]
    assert [(text, check(text)) for text in texts if check(text)] == []


# --------------------------------------------------------------------------- #
# La regla en un solo sitio: `accept` (decimonovena ronda, 2026-10-31)
# --------------------------------------------------------------------------- #


def test_accept_applies_the_whole_rule_and_knows_where_the_food_is_required() -> None:
    assert food_item.accept(KEY, "  Arroz   con pollo ", require=True) == "Arroz con pollo"
    assert food_item.accept(REJECTED, "arroz", require=True) == "arroz"
    # Sin alimento: obligatorio solo en la valoración, y solo si la ruta lo exige.
    with pytest.raises(ValueError, match="Falta el alimento"):
        food_item.accept(KEY, None, require=True)
    assert food_item.accept(KEY, None, require=False) is None
    assert food_item.accept(REJECTED, None, require=True) is None
    # En un indicador que no lo admite, el alimento es un error aunque no se exija.
    with pytest.raises(ValueError, match="Solo la aceptabilidad"):
        food_item.accept("appetite-rating", "arroz", require=False)
    assert food_item.accept("appetite-rating", None, require=True) is None
    # Y la regla del nombre, con su motivo.
    with pytest.raises(ValueError, match="filtro de lenguaje"):
        food_item.accept(REJECTED, "arroz 100 g", require=False)
    with pytest.raises(ValueError, match="al menos una letra"):
        food_item.accept(KEY, "123", require=False)


# --------------------------------------------------------------------------- #
# La ruta que firma: el registro diario
# --------------------------------------------------------------------------- #


def test_the_diary_offers_the_food_field_on_the_rating_and_the_rejected_fraction(
    client: TestClient,
) -> None:
    indicators = client.get("/api/diary").json()["indicators"]
    with_field = {item["key"]: item["food_item"] for item in indicators}
    assert {key for key, value in with_field.items() if value is not None} == {KEY, REJECTED}
    assert with_field[KEY]["label"] == food_item.LABEL
    assert with_field[KEY]["max_length"] == food_item.MAX_LENGTH
    assert with_field[KEY]["rule"] == food_item.RULE
    # Obligatorio en la valoración; opcional en la fracción rechazada, y cada uno lo dice.
    assert with_field[KEY]["required"] is True
    assert with_field[KEY]["requirement_note"] == food_item.REQUIRED_NOTE
    assert with_field[REJECTED]["required"] is False
    assert with_field[REJECTED]["requirement_note"] == food_item.OPTIONAL_NOTE
    assert with_field[REJECTED]["label"] == food_item.REJECTED_LABEL


def test_the_diary_signs_the_rejected_fraction_with_or_without_its_dish(
    client: TestClient,
) -> None:
    body = {"key": REJECTED, "value": 30.0, "subject": "crew-01", "recorded_by": OPERATOR}
    without = client.post("/api/diary/entries", json=body)
    assert without.status_code == 201, without.text
    assert without.json()["food"] is None
    with_dish = client.post("/api/diary/entries", json={**body, "food": "  Arroz  con pollo "})
    assert with_dish.status_code == 201, with_dish.text
    assert with_dish.json()["food"] == "Arroz con pollo"
    # La regla es la misma que en la valoración: con su motivo y sin asiento.
    before = _entries(client)
    refused = client.post("/api/diary/entries", json={**body, "food": "arroz 100 g"})
    assert refused.status_code == 422 and "filtro de lenguaje" in refused.json()["detail"]
    assert _entries(client) == before
    assert [entry["food"] for entry in client.get("/api/diary/entries").json()["entries"]] == [
        "Arroz con pollo", None,
    ]


def test_a_rating_is_signed_with_its_normalized_food(client: TestClient) -> None:
    response = client.post("/api/diary/entries", json=_entry(5.5, "  Arroz  con pollo "))
    assert response.status_code == 201, response.text
    assert response.json()["food"] == "Arroz con pollo"
    payloads = [dict(entry.payload) for entry in get_store().ledger.entries]
    assert payloads[-1]["food"] == "Arroz con pollo"
    entries = client.get("/api/diary/entries").json()["entries"]
    assert [(item["key"], item["food"]) for item in entries] == [(KEY, "Arroz con pollo")]
    # Un indicador sin alimento lo dice con `None`, no con un texto.
    assert client.post(
        "/api/diary/entries",
        json={"key": "appetite-rating", "value": 5, "subject": "crew-01", "recorded_by": "CMO"},
    ).status_code == 201
    entries = client.get("/api/diary/entries").json()["entries"]
    assert {item["key"]: item["food"] for item in entries}["appetite-rating"] is None


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (_entry(6.0, None), food_item.MISSING),
        (_entry(6.0, "arroz 100 g"), "filtro de lenguaje"),
        (_entry(6.0, "<script>"), "caracteres que la regla no admite"),
        (_entry(6.0, "x" * 65), "pasa de 64"),
        (
            {"key": "appetite-rating", "value": 5, "subject": "crew-01",
             "recorded_by": "CMO", "food": "lentejas"},
            food_item.NOT_ALLOWED_HERE,
        ),
    ],
)
def test_a_bad_or_missing_food_is_refused_without_an_entry(
    client: TestClient, body: dict[str, Any], reason: str
) -> None:
    before = _entries(client)
    response = client.post("/api/diary/entries", json=body)
    assert response.status_code == 422
    assert reason in response.json()["detail"]
    assert _entries(client) == before


def test_an_amendment_keeps_the_food_of_the_rating_it_corrects(client: TestClient) -> None:
    """La corrección (por la ingesta genérica, sin el campo) es del valor, no del plato.

    Antes la versión corregida, la única que se lee, salía del plato sin que nada lo dijera.
    """
    assert client.post("/api/diary/entries", json=_entry(4.0, "Arroz con pollo")).status_code == 201
    index = _entries(client) - 1
    response = client.post(
        f"/api/audit/amend/{index}",
        json={
            "reason": "errata al teclear",
            "correction": {"key": KEY, "value": 5.0, "source": "manual"},
        },
    )
    assert response.status_code == 200, response.text
    payloads = [dict(entry.payload) for entry in get_store().ledger.entries]
    assert payloads[-1]["replacement"]["food"] == "Arroz con pollo"
    body = client.get("/api/nutrition/food-acceptability").json()
    assert [(d["food"], d["times"]) for d in body["dishes"]] == [("Arroz con pollo", 1)]
    assert [item["value"] for item in body["dishes"][0]["series"]] == [5.0]
    assert body["without_food"] == 0


# --------------------------------------------------------------------------- #
# La ingesta genérica y la enmienda: `food_item` (decimonovena ronda, 2026-10-31)
# --------------------------------------------------------------------------- #


def _ingest(client: TestClient, key: str, value: float, **extra: Any) -> Any:
    return client.post(
        "/api/observations",
        json={"key": key, "value": value, "source": "manual", "subject": "crew-01", **extra},
    )


def test_the_generic_ingestion_signs_the_dish_with_the_same_rule(client: TestClient) -> None:
    """Hasta esta ronda el campo no existía: lo que entraba por aquí no podía decir su plato."""
    response = _ingest(client, KEY, 6.0, food_item="  Lentejas   con chorizo ")
    assert response.status_code == 201, response.text
    assert response.json()["food"] == "Lentejas con chorizo"
    left = _ingest(client, REJECTED, 25.0, food_item="lentejas con chorizo")
    assert left.status_code == 201, left.text
    assert left.json()["food"] == "lentejas con chorizo"
    # Firmado como el del diario: en el asiento y en FHIR (`Observation.focus`).
    payloads = [dict(entry.payload) for entry in get_store().ledger.entries]
    assert [item.get("food") for item in payloads] == [
        "Lentejas con chorizo", "lentejas con chorizo",
    ]
    fhir_resources = client.get("/api/observations", params={"key": REJECTED}).json()
    assert fhir_resources["observations"][0]["focus"] == [{"display": "lentejas con chorizo"}]
    body = client.get("/api/nutrition/food-acceptability").json()
    assert [(d["food"], d["times"], d["rejected"]["times"]) for d in body["dishes"]] == [
        ("Lentejas con chorizo", 1, 1),
    ]


def test_the_generic_ingestion_does_not_require_the_dish(client: TestClient) -> None:
    """Por aquí entra lo que no conoce el plato: sigue contándose «sin alimento declarado»."""
    assert _ingest(client, KEY, 6.0).status_code == 201
    assert _ingest(client, REJECTED, 10.0).status_code == 201
    body = client.get("/api/nutrition/food-acceptability").json()
    assert (body["dishes"], body["without_food"]) == ([], 1)


@pytest.mark.parametrize(
    ("key", "food", "reason"),
    [
        ("appetite-rating", "lentejas", "Solo la aceptabilidad"),
        (KEY, "arroz 100 g", "filtro de lenguaje"),
        (REJECTED, "123", "al menos una letra"),
        (KEY, "", "vacío"),
    ],
)
def test_the_generic_ingestion_refuses_a_bad_dish_without_an_entry(
    client: TestClient, key: str, food: str, reason: str
) -> None:
    before = _entries(client)
    response = _ingest(client, key, 5.0, food_item=food)
    assert response.status_code == 422, response.text
    assert reason in response.json()["detail"]
    assert _entries(client) == before


def test_the_old_field_name_is_still_a_422(client: TestClient) -> None:
    """`food` es el nombre del diario; en la genérica el campo es `food_item`."""
    before = _entries(client)
    assert _ingest(client, KEY, 6.0, food="lentejas").status_code == 422
    assert _entries(client) == before


def test_an_amendment_can_correct_the_dish_with_the_same_rule(client: TestClient) -> None:
    """Con `food_item`, la corrección es también del plato; sin él, conserva el de antes."""
    assert client.post("/api/diary/entries", json=_entry(4.0, "Arroz con polo")).status_code == 201
    index = _entries(client) - 1
    bad = client.post(
        f"/api/audit/amend/{index}",
        json={
            "reason": "errata en el plato",
            "correction": {
                "key": KEY, "value": 4.0, "source": "manual", "food_item": "arroz 100 g",
            },
        },
    )
    assert bad.status_code == 422 and "filtro de lenguaje" in bad.json()["detail"]
    good = client.post(
        f"/api/audit/amend/{index}",
        json={
            "reason": "errata en el plato",
            "correction": {
                "key": KEY, "value": 4.0, "source": "manual", "food_item": " Arroz  con pollo ",
            },
        },
    )
    assert good.status_code == 200, good.text
    payloads = [dict(entry.payload) for entry in get_store().ledger.entries]
    assert payloads[-1]["replacement"]["food"] == "Arroz con pollo"
    body = client.get("/api/nutrition/food-acceptability").json()
    assert [(d["food"], d["times"]) for d in body["dishes"]] == [("Arroz con pollo", 1)]


# --------------------------------------------------------------------------- #
# De la primera a la última, y la fracción rechazada al lado (decimonovena ronda)
# --------------------------------------------------------------------------- #


def _left(value: float, food: str | None, hours: float = 0) -> VitalObservation:
    return observation(
        REJECTED, value, T + dt.timedelta(hours=hours), "crew-01", "crew-diary",
        recorded_by=OPERATOR, food=food,
    )


def test_each_dish_says_from_its_first_to_its_last_rating_with_their_days() -> None:
    criterion = instruments_read.scale_criterion(KEY)
    readings = [
        _rating(7.0, "lentejas", 0), _rating(5.0, "Lentejas", 6), _rating(4.0, "LENTEJAS", 7 * 24),
        _rating(8.0, "arroz", 24),
        _rating(6.0, "pasta", 0), _rating(6.5, "pasta", 3),
    ]
    block = food_acceptability.describe("crew-01", readings, criterion, 10)
    change = {dish["food"]: dish["change"] for dish in block["dishes"]}
    assert change["LENTEJAS"]["statement"] == (
        "De 7,0 puntos a 4,0 puntos entre el 2026-09-03 y el 2026-09-10."
    )
    assert (change["LENTEJAS"]["first"]["value"], change["LENTEJAS"]["last"]["value"]) == (7.0, 4.0)
    assert change["LENTEJAS"]["first"]["effective"] == T.isoformat()
    assert change["arroz"]["statement"] == "Una sola valoración: 8,0 puntos, el 2026-09-04."
    assert change["pasta"]["statement"] == "De 6,0 puntos a 6,5 puntos, el 2026-09-03."
    # Sin criterio leído la cifra se escribe igual: la comparación no depende de la marca.
    without = food_acceptability.describe("crew-01", readings, None, 10)
    assert {d["food"]: d["change"]["statement"] for d in without["dishes"]} == {
        k: v["statement"] for k, v in change.items()
    }
    assert block["change_note"] == food_acceptability.CHANGE_NOTE


def test_the_day_of_a_rating_is_its_utc_day() -> None:
    """Un instante escrito con otro desfase es el mismo día que su equivalente en UTC."""
    minus_five = dt.timezone(dt.timedelta(hours=-5))
    first = observation(KEY, 7.0, dt.datetime(2026, 9, 3, 21, 0, tzinfo=minus_five), "crew-01",
                        "crew-diary", food="arroz")  # 2026-09-04 02:00 UTC
    last = observation(KEY, 5.0, dt.datetime(2026, 9, 5, 12, 0, tzinfo=dt.UTC), "crew-01",
                       "crew-diary", food="arroz")
    block = food_acceptability.describe("crew-01", [last, first], None, 10)
    assert block["dishes"][0]["change"]["statement"] == (
        "De 7,0 puntos a 5,0 puntos entre el 2026-09-04 y el 2026-09-05."
    )


def test_the_rejected_fraction_of_a_dish_sits_beside_its_ratings() -> None:
    readings = [
        _rating(7.0, "lentejas", 0), _rating(4.0, "lentejas", 48),
        _rating(8.0, "arroz", 24),
        _left(10.0, "LENTEJAS", 1), _left(60.0, "lentejas", 49),
        _left(5.0, "pasta", 2),  # un plato que nadie valoró: no hace plato
        _left(20.0, None, 3),  # de la comida en general: no es de ningún plato
        observation(REJECTED, 99.0, T, "crew-01", "emma-forecast", food="lentejas",
                    observation_type=ObservationType.PREDICTED, model_version="x"),  # no medida
    ]
    block = food_acceptability.describe("crew-01", readings, None, 10)
    by_food = {dish["food"]: dish for dish in block["dishes"]}
    assert set(by_food) == {"lentejas", "arroz"}
    left = by_food["lentejas"]["rejected"]
    assert left["times"] == 2
    assert [point["value"] for point in left["series"]] == [10.0, 60.0]
    assert left["statement"] == (
        "Fracción rechazada declarada 2 veces: de 10 % a 60 % entre el 2026-09-03 y el "
        "2026-09-05."
    )
    assert by_food["lentejas"]["rejected_display"] == left["statement"]
    assert by_food["arroz"]["rejected"] is None
    assert by_food["arroz"]["rejected_display"] == food_acceptability.NO_REJECTED
    assert block["rejected_note"] == food_acceptability.REJECTED_NOTE
    # Las fracciones no cuentan como valoraciones: ni en el plato ni en el total.
    assert (by_food["lentejas"]["times"], block["rated"], block["without_food"]) == (2, 3, 0)
    one = food_acceptability.describe(
        "crew-01", [_rating(7.0, "arroz"), _left(15.0, "arroz", 2)], None, 10,
    )
    assert one["dishes"][0]["rejected"]["statement"] == (
        "Fracción rechazada declarada una vez: 15 %, el 2026-09-03."
    )


def test_the_new_texts_pass_the_language_guard() -> None:
    block = food_acceptability.describe(
        "crew-01",
        [_rating(7.0, "lentejas"), _rating(4.0, "lentejas", 48), _left(10.0, "lentejas", 1),
         _left(60.0, "lentejas", 49), _rating(8.0, "arroz", 24)],
        instruments_read.scale_criterion(KEY), 10,
    )
    texts = [
        food_acceptability.CHANGE_NOTE, food_acceptability.REJECTED_NOTE,
        food_acceptability.NO_REJECTED,
        *(dish["change"]["statement"] for dish in block["dishes"]),
        *(dish["rejected_display"] for dish in block["dishes"]),
    ]
    assert [(text, check(text)) for text in texts if check(text)] == []
    for text in (food_acceptability.CHANGE_NOTE, food_acceptability.REJECTED_NOTE):
        assert "veredicto" in text and "umbral" in text


# --------------------------------------------------------------------------- #
# Plato a plato, descriptivo
# --------------------------------------------------------------------------- #


def test_dishes_count_times_days_and_keep_each_rating_in_time() -> None:
    criterion = instruments_read.scale_criterion(KEY)
    # Desordenadas a propósito: la serie de cada plato se ordena, no se toma como llega.
    readings = [
        _rating(4.5, "LENTEJAS", 48),
        _rating(7.0, "Lentejas", 0),
        _rating(5.0, "lentejas", 6),  # mismo día, otro rato
        _rating(8.0, "arroz", 24),
        _rating(6.0, "arroz", 72),
        _rating(6.5, "pasta", 96),
        _rating(3.0, None, 1),
    ]
    block = food_acceptability.describe("crew-01", readings, criterion, 2)
    dishes = block["dishes"]
    assert [(d["food"], d["times"], d["distinct_days"], d["below"]) for d in dishes] == [
        ("LENTEJAS", 3, 2, 2), ("arroz", 2, 2, 0), ("pasta", 1, 1, 0),
    ]
    # Cada valoración del plato, de la primera a la última; sobre todas, no solo las `limit`.
    assert [item["value"] for item in dishes[0]["series"]] == [7.0, 5.0, 4.5]
    assert [item["mark"] for item in dishes[0]["series"]] == [None, MARK, MARK]
    assert dishes[0]["first_effective"] == T.isoformat()
    assert dishes[0]["last_effective"] == (T + dt.timedelta(hours=48)).isoformat()
    assert dishes[0]["statement"] == (
        f"Valorado 3 veces, en 2 días distintos. 2 de 3 quedan {MARK} (6,0)."
    )
    assert dishes[2]["statement"] == f"Valorado 1 vez, en 1 día. 0 de 1 quedan {MARK} (6,0)."
    assert (block["without_food"], block["rated"], block["shown"]) == (1, 7, 2)
    assert block["dishes_statement"] == (
        "3 platos en 6 valoraciones con alimento; 1 sin alimento declarado."
    )
    shown = block["ratings"]
    assert [(item["food"], item["food_display"]) for item in shown] == [
        ("pasta", "pasta"), ("arroz", "arroz"),
    ]
    assert food_acceptability.describe("crew-01", [_rating(3.0)], criterion, 5)["ratings"][0][
        "food_display"
    ] == NO_FOOD


def test_a_tie_in_times_puts_the_last_rated_dish_first() -> None:
    readings = [_rating(7.0, "arroz", 0), _rating(7.0, "pasta", 24)]
    block = food_acceptability.describe("crew-01", readings, None, 10)
    assert [dish["food"] for dish in block["dishes"]] == ["pasta", "arroz"]
    # Sin criterio leído no se cuenta «por debajo»: no se compara.
    assert block["dishes"][0]["below"] is None
    assert block["dishes"][0]["statement"] == "Valorado 1 vez, en 1 día."
    assert block["dishes"][0]["series"][0]["below"] is None


def test_a_tie_is_broken_by_the_instant_not_by_its_text() -> None:
    """Con desfases horarios distintos, el texto ISO no va en el orden del tiempo."""
    minus_five = dt.timezone(dt.timedelta(hours=-5))
    later = dt.datetime(2026, 9, 3, 10, 0, tzinfo=minus_five)  # 15:00 UTC
    earlier = dt.datetime(2026, 9, 3, 12, 0, tzinfo=dt.UTC)
    readings = [
        observation(KEY, 7.0, earlier, "crew-01", "crew-diary", food="arroz"),
        observation(KEY, 7.0, later, "crew-01", "crew-diary", food="pasta"),
    ]
    block = food_acceptability.describe("crew-01", readings, None, 10)
    assert [dish["food"] for dish in block["dishes"]] == ["pasta", "arroz"]


def test_one_rating_is_written_in_the_singular() -> None:
    block = food_acceptability.describe("crew-01", [_rating(7.0, "arroz")], None, 10)
    assert block["dishes_statement"] == (
        "1 plato en 1 valoración con alimento; 0 sin alimento declarado."
    )


def test_every_new_text_passes_the_language_guard() -> None:
    block = food_acceptability.describe(
        "crew-01", [_rating(5.0, "lentejas"), _rating(7.0, "lentejas", 30), _rating(6.0)],
        instruments_read.scale_criterion(KEY), 10,
    )
    texts = [
        REPETITION_NOTE, WITHOUT_FOOD_NOTE, NO_FOOD, block["dishes_statement"],
        block["grouping"], *(dish["statement"] for dish in block["dishes"]),
    ]
    assert [(text, check(text)) for text in texts if check(text)] == []
    assert "veredicto" in REPETITION_NOTE and "fatiga de menú" in REPETITION_NOTE


def test_the_route_serves_dishes_from_the_signed_ratings(client: TestClient) -> None:
    for value, food in ((7.0, "lentejas"), (5.0, "Lentejas"), (8.0, "arroz")):
        assert client.post("/api/diary/entries", json=_entry(value, food)).status_code == 201
    before = _entries(client)
    body = client.get("/api/nutrition/food-acceptability").json()
    assert [(d["food"], d["times"]) for d in body["dishes"]] == [("Lentejas", 2), ("arroz", 1)]
    assert body["without_food"] == 0
    assert _entries(client) == before


def test_simulated_ratings_have_no_food_and_are_counted_apart(client: TestClient) -> None:
    assert client.post("/api/simulate", params={"scenario": "menu-fatigue"}).status_code == 201
    body = client.get("/api/nutrition/food-acceptability", params={"limit": 5}).json()
    assert body["dishes"] == []
    assert body["without_food"] == body["rated"] == 40


# --------------------------------------------------------------------------- #
# Invariante 5: el alimento no decide nada
# --------------------------------------------------------------------------- #


def test_no_module_that_decides_reads_the_food() -> None:
    backend = Path(__file__).resolve().parents[1]
    for folder in ("analysis", "advisor"):
        for path in sorted((backend / "app" / folder).glob("*.py")):
            if path.name == "food_acceptability.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            used = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
            assert "food" not in used, path.name
            imported = {
                f"{node.module}" for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module
            }
            assert "app.ingest.food_item" not in imported, path.name


def _status(client: TestClient, with_food: bool) -> dict[str, Any]:
    reset_store(new_store())
    assert client.post("/api/simulate", params={"scenario": "menu-fatigue"}).status_code == 201
    reference = dt.datetime.fromisoformat(
        client.get("/api/status").json()["data"]["reference_time"]
    )
    foods = ["lentejas", "arroz", "lentejas", "pasta"]
    get_store().record_many(
        [
            observation(
                KEY, value, reference - dt.timedelta(hours=hours), "crew-01", "crew-diary",
                recorded_by=OPERATOR, food=food if with_food else None,
            )
            for value, hours, food in zip((2.0, 3.0, 2.5, 8.0), (30, 20, 10, 2), foods, strict=True)
        ],
        Identity.generate(diary_module.DIARY_SOURCE),
    )
    status: dict[str, Any] = client.get("/api/status").json()
    return status


def test_the_same_values_give_the_same_status_with_or_without_food(client: TestClient) -> None:
    without = _status(client, with_food=False)
    with_food = _status(client, with_food=True)
    for field in ("overall_level", "domains", "alerts", "recommendations", "rules_version"):
        assert with_food[field] == without[field], field
    assert with_food["data"] == without["data"]
    assert with_food["rules_version"] == rules_version()


def test_two_rejected_fractions_on_one_day_do_not_repeat_the_date() -> None:
    """Un plato comido dos veces el mismo día: un «entre» de un día consigo mismo no dice nada."""
    day = dt.datetime(2026, 9, 3, 7, tzinfo=dt.UTC)
    key = food_acceptability.REJECTED_KEY
    left = food_acceptability._rejected([
        observation(key, 10.0, day, "crew-01", "crew-diary", food="lentejas"),
        observation(
            key, 60.0, day + dt.timedelta(hours=5), "crew-01", "crew-diary", food="lentejas"
        ),
    ])
    assert left is not None
    assert left["statement"] == (
        "Fracción rechazada declarada 2 veces: de 10 % a 60 %, el 2026-09-03."
    )


def test_the_rejected_fraction_does_not_cite_what_only_backs_the_rating() -> None:
    assert food_item.describe("food-acceptability")["basis"]
    assert food_item.describe("food-rejected-fraction")["basis"] == []
