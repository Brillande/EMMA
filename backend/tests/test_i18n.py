"""El idioma por petición (`app/core/i18n.py`): quién lo decide, qué cambia y qué no."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.assistant import catalog
from app.core import display, i18n
from app.ingest import names_es
from app.ingest.codes import CATALOG
from tests.conftest import ENGLISH_HEADERS


def test_the_suite_runs_in_spanish() -> None:
    assert i18n.current() == "es"
    assert i18n.tr("hola", "hello") == "hola"


def test_use_changes_the_language_and_puts_it_back() -> None:
    with i18n.use("en"):
        assert i18n.tr("hola", "hello") == "hello"
        with i18n.record_language():
            assert i18n.tr("hola", "hello") == "hola"
        assert i18n.current() == "en"
    assert i18n.current() == "es"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("en", "en"), ("EN", "en"), ("en-GB", "en"), (" es ", "es"),
        ("fr", None), ("", None), (None, None),
    ],
)
def test_parse_only_knows_two_languages(raw: str | None, expected: str | None) -> None:
    assert i18n.parse(raw) == expected


def test_header_wins_over_cookie_and_cookie_over_default() -> None:
    cookie = (b"cookie", b"otra=1; emma_lang=en")
    assert i18n.request_language([cookie]) == "en"
    assert i18n.request_language([cookie, (b"x-emma-lang", b"es")]) == "es"
    assert i18n.request_language([(b"X-EMMA-Lang", b"en")]) == "en"
    assert i18n.request_language([]) is None
    assert i18n.request_language([(b"cookie", b"emma_lang=klingon")]) is None


def test_a_registered_constant_reads_in_the_request_language() -> None:
    label = "frase de prueba de i18n, solo castellano"
    i18n.en(label, "i18n test sentence")
    assert i18n.loc(label) == label
    with i18n.use("en"):
        assert i18n.loc(label) == "i18n test sentence"
        assert i18n.loc("sin registrar") == "sin registrar"


def test_two_englishes_for_one_spanish_is_a_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(i18n, "_conflicts", [])
    monkeypatch.setattr(i18n, "_registry", {})
    i18n.en("una", "one")
    i18n.en("una", "one")
    assert i18n.conflicts() == []
    i18n.en("una", "a")
    assert i18n.conflicts() == [("una", "one", "a")]
    with i18n.use("en"):
        assert i18n.loc("una") == "one"


def test_lang_cache_keeps_one_entry_per_language() -> None:
    calls: list[str] = []

    @i18n.lang_cache
    def greeting(name: str) -> str:
        calls.append(i18n.current())
        return i18n.tr(f"hola, {name}", f"hello, {name}")

    assert greeting("Ana") == "hola, Ana"
    assert greeting("Ana") == "hola, Ana"
    with i18n.use("en"):
        assert greeting("Ana") == "hello, Ana"
        assert greeting("Ana") == "hello, Ana"
    assert calls == ["es", "en"]


def test_overlay_translates_values_and_never_keys(tmp_path: Path) -> None:
    source = tmp_path / "cosas.json"
    data = {"título": "título", "items": [{"label": "uno", "id": "uno-id"}, ("dos",)], "n": 3}
    (tmp_path / "cosas.en.json").write_text(
        json.dumps({"strings": {"título": "title", "uno": "one", "dos": "two"}}), encoding="utf-8"
    )
    assert i18n.localized(data, source) is data
    with i18n.use("en"):
        shown = i18n.localized(data, source)
    items = [{"label": "one", "id": "uno-id"}, ("two",)]
    assert shown == {"título": "title", "items": items, "n": 3}
    assert data["título"] == "título"
    assert i18n.missing(source, data) == ["uno-id"]
    assert i18n.missing(source, data, skip=lambda text: text.endswith("-id")) == []


def test_a_file_without_overlay_is_served_as_it_is(tmp_path: Path) -> None:
    source = tmp_path / "solo.json"
    with i18n.use("en"):
        assert i18n.localized({"a": "texto"}, source) == {"a": "texto"}


def test_numbers_use_a_point_in_english_and_keep_the_thin_space() -> None:
    assert display.number(12345.5, 1) == "12 345,5"
    assert display.quantity("body-temperature", 36.6, "Cel") == "36,6 °C"
    assert display.rate_per_week("heart-rate", 0.4, "/min") == "0,4 /min/semana"
    with i18n.use("en"):
        assert display.number(12345.5, 1) == "12 345.5"
        assert display.number(-0.25, 2) == "-0.25"
        assert display.quantity("body-temperature", 36.6, "Cel") == "36.6 °C"
        assert display.rate_per_week("heart-rate", 0.4, "/min") == "0.4 /min/week"
        assert display.unit("{count}") == "count"
        assert display.unit("mL/(24.h)") == "mL/day"
        assert display.percent(0.125) == "12.5 %"


def test_every_english_unit_replaces_a_spanish_one() -> None:
    assert set(display.UNITS_EN) <= set(display.UNITS)
    spanish_words = ("día", "recuento", "puntos", "UI/", "UFC")
    for ucum, written in display.UNITS.items():
        if any(word in written for word in spanish_words):
            assert ucum in display.UNITS_EN, ucum


def test_indicator_names_follow_the_language() -> None:
    assert names_es.name_es("heart-rate") == names_es.spanish_name("heart-rate").text
    assert names_es.fields("heart-rate")["display_es_origin"] in {"emma", "polaris"}
    with i18n.use("en"):
        assert names_es.name_es("heart-rate") == CATALOG["heart-rate"].display
        assert CATALOG["heart-rate"].display_es == CATALOG["heart-rate"].display
        shown = names_es.fields("heart-rate")
        assert shown["display_es_origin"] == "catalog"
        assert "LOINC" in shown["display_es_origin_display"]
        with pytest.raises(KeyError):
            names_es.name_es("no-existe")


def test_the_api_answers_in_the_language_asked(client: TestClient) -> None:
    spanish = client.get("/api/indicators").json()
    english = client.get("/api/indicators", headers=ENGLISH_HEADERS).json()
    by_cookie = client.get("/api/indicators", headers={"Cookie": "emma_lang=en"}).json()
    assert english == by_cookie
    assert english != spanish
    assert CATALOG["heart-rate"].display in json.dumps(english, ensure_ascii=False)
    assert names_es.spanish_name("heart-rate").text in json.dumps(spanish, ensure_ascii=False)
    # El idioma de una petición no se queda puesto para la siguiente.
    assert client.get("/api/indicators").json() == spanish


def test_set_aside_tabs_leave_the_assistant_catalogue() -> None:
    full = catalog.catalog()
    assert "log" in full.section_keys("crew")
    try:
        catalog.use_set_aside(True)
        shown = catalog.catalog()
        assert shown.section_keys("crew")[:7] == [
            "home", "radiation", "isolation", "gravity", "environment", "nodes", "hazards",
        ]
        aside = {"routines", "body", "mission", "data", "log", "imaging", "planner", "library"}
        assert not aside & set(shown.section_keys("crew"))
        # Tierra no aparta nada: su «Biblioteca» sigue.
        assert shown.section_keys("ground") == full.section_keys("ground")
        assert len(shown.panels) < len(full.panels)
        for panel in shown.panels.values():
            assert panel.places
            assert not any(p.console == "crew" and p.section in aside for p in panel.places)
        assert "alerts" in shown.panels
        every = json.loads(catalog.EXAMPLES_PATH.read_text(encoding="utf-8"))["examples"]
        assert 0 < len(catalog.examples()) <= len(every)
    finally:
        catalog.use_set_aside(False)
    assert catalog.catalog().section_keys("crew") == full.section_keys("crew")


def test_the_inventory_marks_exactly_the_tabs_set_aside() -> None:
    raw = json.loads(catalog.UI_PATH.read_text(encoding="utf-8"))
    crew = [item["key"] for item in raw["sections"]["crew"] if item.get("set_aside") is True]
    assert crew == ["routines", "body", "mission", "data", "log", "imaging", "planner", "library"]
    assert [item["key"] for item in raw["sections"]["ground"] if item.get("set_aside")] == []
