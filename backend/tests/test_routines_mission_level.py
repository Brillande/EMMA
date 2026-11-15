"""Lo que el nivel de misión suspende no se da por atrasado ni roto (2026-11-03).

Con el nivel reducido o mínimo firmado (`core/mission_modes.py`), la consola seguía contando como
deudas las medidas que el propio nivel deja de esperar. `routines.with_mission_level` las marca y
las saca del recuento; el estado de cada una se calcula igual y nada llega al riesgo.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app import routines
from app.core import mission_modes
from tests.test_api import alerting, client  # noqa: F401 — fixtures
from tests.test_mission_mode import DOWN


def _body() -> dict[str, Any]:
    return {
        "now": "2026-11-03T00:00:00+00:00",
        "counts": {"rota": 2},
        "routines": [
            {"key": "heart-rate", "state": "rota"},
            {"key": "salivary-cortisol", "state": "rota"},
        ],
    }


def test_a_suspended_routine_is_marked_and_left_out_of_the_counts() -> None:
    out = routines.with_mission_level(
        _body(), "minimal", "mínimo", frozenset({"salivary-cortisol"})
    )
    assert [r["suspended"] for r in out["routines"]] == [False, True]
    # El estado de la suspendida sigue calculado: solo deja de contar como deuda.
    assert out["routines"][1]["state"] == "rota"
    assert out["counts"] == {"rota": 1}
    assert out["mission_level"] == "minimal"
    assert out["mission_level_display"] == "mínimo"
    assert out["suspended_note"] is not None and "mínimo" in out["suspended_note"]


def test_at_nominal_nothing_is_suspended_and_there_is_no_note() -> None:
    out = routines.with_mission_level(_body(), "nominal", "nominal", frozenset())
    assert not any(r["suspended"] for r in out["routines"])
    assert out["counts"] == {"rota": 2}
    assert out["suspended_note"] is None


def test_the_endpoint_follows_the_signed_level(client: TestClient) -> None:  # noqa: F811
    client.post("/api/simulate", params={"scenario": "nominal", "days": 10})
    before = client.get("/api/timeline/routines").json()
    assert before["mission_level"] == "nominal"
    assert not any(r["suspended"] for r in before["routines"])
    assert client.post("/api/mission-mode", json=DOWN).status_code == 201
    after = client.get("/api/timeline/routines").json()
    off = mission_modes.suspended_measurements("minimal")
    assert after["mission_level"] == "minimal"
    assert after["mission_level_display"] == mission_modes.vocabulary().levels["minimal"].display
    for routine in after["routines"]:
        assert routine["suspended"] is (routine["key"] in off)
    assert sum(after["counts"].values()) == sum(
        1 for routine in after["routines"] if not routine["suspended"]
    )
    # Las rachas no dependen del nivel: cuentan lo que llegó.
    assert after["streaks"] == before["streaks"]
