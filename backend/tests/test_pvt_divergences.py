"""Las divergencias de la PVT con la fuente leída se declaran; los valores que puntúan no cambian.

`GET /api/pvt/protocol` lleva desde el 2026-10-14 `divergences`: cuatro diferencias entre lo que
hace EMMA y lo que dice Basner et al. 2011 (leído el 2026-10-13, `data/instruments_read.json`),
cada una con la frase que la sostiene. Declararlas no es corregirlas (invariante 5): esta prueba
fija los valores con que se puntúa y que lo que se declara sale del código que puntúa.
"""

import dataclasses
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import pvt_console
from app.api.routes import new_store, reset_store
from app.core import display
from app.core.config import Settings, get_settings
from app.ingest.pvt import (
    FALSE_START_THRESHOLD_MS,
    LAPSE_THRESHOLD_MS,
    MIN_TRIALS,
    InsufficientTrials,
    PvtResult,
    is_lapse,
    score,
)
from app.main import app

BASNER = {"basner-2011-pvt-b", "basner-2011-pvt-metrics"}


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _divergences(client: TestClient) -> dict[str, dict[str, Any]]:
    response = client.get("/api/pvt/protocol")
    assert response.status_code == 200
    body = response.json()["divergences"]
    assert "no se corrigen" in body["note"]
    return {item["key"]: item for item in body["items"]}


def test_the_scoring_values_are_the_same_ones() -> None:
    """Invariante 5: declarar las divergencias no mueve ningún valor que puntúa."""
    assert LAPSE_THRESHOLD_MS == 500.0
    assert FALSE_START_THRESHOLD_MS == 100.0
    assert MIN_TRIALS == 10
    assert pvt_console.ABANDON_AFTER_MS == 10_000.0
    # En el umbral exacto, EMMA no cuenta lapso; un pelo por encima, sí.
    assert is_lapse(500.0) is False and is_lapse(500.01) is True
    result = score([250.0] * 7 + [500.0, 500.01, 99.9])
    assert (result.lapses, result.false_starts, result.valid_trials) == (1, 1, 9)
    with pytest.raises(InsufficientTrials):
        score([250.0] * (MIN_TRIALS - 1))


def test_the_four_divergences_are_declared_with_their_source(client: TestClient) -> None:
    items = _divergences(client)
    assert list(items) == ["lapse_operator", "lapse_threshold_version", "no_response", "min_trials"]
    assert {key: item["status"] for key, item in items.items()} == {
        "lapse_operator": "differs", "lapse_threshold_version": "differs",
        "no_response": "differs", "min_trials": "not_published",
    }
    for item in items.values():
        assert item["kept"] == pvt_console.KEPT
        assert item["status_display"] == pvt_console.DIVERGENCE_STATUS[item["status"]]
        assert all(source["ref"] in BASNER for source in item["sources"])
        assert all(source["read_on"] and source["quote"] for source in item["sources"])
    # Lo que se dice de la fuente está escrito, tal cual, en la frase que se cita.
    quotes = lambda key: " ".join(source["quote"] for source in items[key]["sources"])  # noqa: E731
    assert "≥ 500 ms" in quotes("lapse_operator")
    assert "≥ 355 ms" in quotes("lapse_threshold_version")
    assert "30 s" in quotes("no_response")
    # Sin valor publicado: ninguna frase, y lo que se buscó y no se encontró.
    assert items["min_trials"]["sources"] == []
    assert items["min_trials"]["not_found"] and "mínimo" in items["min_trials"]["not_found"][0]


def test_what_emma_does_is_read_from_the_scoring_code(client: TestClient) -> None:
    items = _divergences(client)
    assert pvt_console.lapse_operator() == ">"
    assert "> 500 ms" in items["lapse_operator"]["emma"]
    assert "≥ 500 ms" in items["lapse_operator"]["published"]
    assert "exactamente 500 ms" in items["lapse_operator"]["consequence"]
    assert "355 ms" in items["lapse_threshold_version"]["published"]
    abandon = f"{display.number(pvt_console.ABANDON_AFTER_MS, 0)} {display.unit('ms')}"
    assert abandon in items["no_response"]["emma"]
    assert "30 s" in items["no_response"]["published"]
    assert "10 estímulos" in items["min_trials"]["emma"]


def test_if_emma_counted_like_the_source_the_operator_would_say_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El estado se calcula: con «≥» en la puntuación, la primera divergencia dejaría de serlo."""
    monkeypatch.setattr(pvt_console, "is_lapse", lambda rt: rt >= LAPSE_THRESHOLD_MS)
    [operator, *_] = pvt_console.divergences()["items"]
    assert pvt_console.lapse_operator() == "≥"
    assert operator["status"] == "matches"
    # Y la tabla de lo publicado lo diría también: el valor de 10 minutos pasaría a ser el de EMMA.
    lapse = _lapse_row(pvt_console.parameters())
    assert lapse["status"] == "same_value"
    assert lapse["values"][0]["marker_display"] == pvt_console.MARKERS["same"]


# --------------------------------------------------------------------------- #
# La marca de «Lo publicado» (2026-10-20): misma cifra no es mismo valor si el operador difiere
# --------------------------------------------------------------------------- #


def _lapse_row(parameters: list[dict[str, Any]]) -> dict[str, Any]:
    found: dict[str, Any] = next(
        item["published"] for item in parameters if item["key"] == "lapse_threshold_ms")
    return found


def _published(client: TestClient) -> dict[str, dict[str, Any]]:
    response = client.get("/api/pvt/protocol")
    assert response.status_code == 200
    return {item["key"]: item["published"] for item in response.json()["parameters"]}


def test_the_lapse_figure_matches_and_its_operator_does_not(client: TestClient) -> None:
    """«≥ 500 ms» no es el valor de EMMA, que cuenta «> 500 ms»: la marca no dice «=»."""
    lapse = _published(client)["lapse_threshold_ms"]
    long, short = lapse["values"]
    assert (long["literal"], long["operator"], long["emma_operator"]) == ("≥ 500 ms", "≥", ">")
    assert (long["same_figure"], long["same"], long["match"]) == (
        True, False, "same_figure_different_operator")
    assert long["marker_display"] == (
        f"{pvt_console.MARKERS['same_figure_different_operator']} (EMMA: > 500 ms)")
    assert not long["marker_display"].startswith("=")
    assert (short["match"], short["marker_display"]) == (
        "different", pvt_console.MARKERS["different"])
    assert lapse["status"] == "same_figure_different_operator"
    assert lapse["status_display"] == "misma cifra, distinto operador que PVT de 10 minutos"


def test_the_markers_come_from_the_backend_and_follow_the_comparison(client: TestClient) -> None:
    published = _published(client)
    for key, item in published.items():
        for value in item["values"]:
            if item["status"] == "not_comparable":
                assert value["marker_display"] is None, key
            elif value["same"]:
                assert value["marker_display"] == pvt_console.MARKERS["same"], key
            else:
                assert not value["marker_display"].startswith("="), key
    # La salida en falso: misma cifra y mismo operador («< 100 ms»), y por eso «=».
    [false_start] = published["false_start_threshold_ms"]["values"]
    assert (false_start["operator"], false_start["emma_operator"]) == ("<", "<")
    assert false_start["marker_display"] == pvt_console.MARKERS["same"]
    # Donde la fuente no escribe operador, solo cuenta la cifra.
    wait = published["foreperiod_ms"]["values"]
    assert [value["operator"] for value in wait] == [None, None]
    assert [value["match"] for value in wait] == ["same", "different"]


def test_the_false_start_operator_is_read_from_the_scoring_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Como el del lapso: si la puntuación contara el umbral como salida en falso, se diría."""
    assert pvt_console.false_start_operator() == "<"

    def at_or_below(times: list[float]) -> PvtResult:
        counted = sum(1 for rt in times if rt <= FALSE_START_THRESHOLD_MS)
        return dataclasses.replace(score(times), false_starts=counted)

    monkeypatch.setattr(pvt_console, "score", at_or_below)
    assert pvt_console.false_start_operator() == "≤"
    [false_start] = next(
        item["published"]["values"] for item in pvt_console.parameters()
        if item["key"] == "false_start_threshold_ms")
    assert false_start["match"] == "same_figure_different_operator"


def test_a_published_operator_without_emma_operator_is_not_marked(client: TestClient) -> None:
    """Si la fuente escribe un operador y no se da el de EMMA, ni «=» ni «≠»: sin marca."""
    compared = pvt_console._compare("lapse_threshold_ms", LAPSE_THRESHOLD_MS, "DIFERENCIA")
    assert [value["match"] for value in compared["values"]] == ["not_comparable"] * 2
    assert [value["marker_display"] for value in compared["values"]] == [None, None]
    assert compared["status"] == "not_comparable"
    # Y en la respuesta no pasa: todo operador que escribe la fuente lleva al lado el de EMMA.
    for key, item in _published(client).items():
        if item["status"] == "not_comparable":
            continue
        for value in item["values"]:
            assert value["operator"] is None or value["emma_operator"] is not None, key
            assert value["marker_display"] is not None, key


def test_the_divergences_inform_and_do_not_order(client: TestClient) -> None:
    """Invariante 7, y 6: se dice qué difiere; no se manda nada ni se da por validado."""
    for item in _divergences(client).values():
        own = " ".join(str(item[key]) for key in ("emma", "published", "consequence", "kept"))
        lowered = own.lower()
        assert not any(word in lowered for word in (
            "debe ", "hay que", "valida", "certific", "corregido"))
