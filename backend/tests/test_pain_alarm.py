"""Marca "comentar con el médico" del informe de dolor (portada de Polaris `sintomas.py`).

No es una alerta: no toca el riesgo (invariante 5). Sin red.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.main import app
from app.pain.alarm import DISCUSS_NOTE, discuss, is_alarm
from app.text_guard import check


def report(*zones: tuple[str, int, list[str]]) -> dict[str, Any]:
    return {"zones": [{"zone": z, "intensity": i, "characters": c} for z, i, c in zones]}


@pytest.mark.parametrize(
    ("zones", "expected"),
    [
        ((("chest", 3, ["pressing"]),), ["opresión en el pecho"]),
        ((("chest", 2, []),), ["dolor en el pecho"]),
        ((("head", 7, []),), ["dolor de cabeza intenso"]),
        ((("head", 6, []),), []),  # moderado según Serlin 1995: no se marca
        ((("lower-back", 8, ["dull"]),), ["dolor de espalda intenso"]),
        ((("hand-left", 2, ["tingling"]),), ["hormigueo de un lado"]),
        ((("hand-left", 2, ["tingling"]), ("hand-right", 2, ["tingling"])), []),
        ((("knee-right", 9, ["sharp"]),), []),
        ((), []),
    ],
)
def test_what_gets_flagged(
    zones: tuple[tuple[str, int, list[str]], ...], expected: list[str]
) -> None:
    assert discuss(report(*zones)) == expected


def test_the_polaris_matcher_ignores_accents_and_case() -> None:
    assert is_alarm("OPRESIÓN EN EL PECHO")
    assert not is_alarm("calambre en la pierna")


def test_the_note_is_support_not_an_order() -> None:
    assert check(DISCUSS_NOTE) == []


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def test_the_flag_is_computed_on_read_and_does_not_alert(client: TestClient) -> None:
    body = {
        "zones": [{"zone": "chest", "intensity": 4, "characters": ["pressing"]}],
        "reported_by": "crew-01",
    }
    response = client.post("/api/pain/reports", json=body)
    assert response.status_code == 201, response.text
    assert response.json()["discuss"] == {
        "reasons": ["opresión en el pecho"], "note": DISCUSS_NOTE,
    }
    [listed] = client.get("/api/pain/reports").json()
    assert listed["discuss"]["reasons"] == ["opresión en el pecho"]
