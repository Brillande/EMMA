"""La banda ósea inferida se detiene en el día de regreso (decisión del usuario, 2026-10-21).

Qué fijan estas pruebas:
- que fuera del posvuelo la banda sale idéntica, campo a campo, a la de antes;
- que en posvuelo se congela en el día de regreso que da `core/mission.py`, no proyecta y lo
  dice, con la frase de la recuperación respaldada por una ficha leída (`ochmo-mtb-013`);
- que esa frase no dice más que la ficha: las dos citas que la sostienen están en sus notas;
- que todo el texto nuevo pasa el linter de lenguaje (invariante 7);
- y la que importa (invariante 5): con la banda cortada, niveles, puntuaciones, alertas y consejo
  son idénticos. La banda es inferida: no puntúa ni alerta.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import inferred
from app.analysis.inferred import (
    RECOVERY_SOURCE,
    RECOVERY_STATEMENT,
    RETURN_CUT_BASIS,
    RETURN_CUT_LABEL,
    bone_density_band,
)
from app.api import routes
from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.core.mission import MissionPhase
from app.evidence import registry
from app.main import app
from app.text_guard import check

RETURN_DAY = 180.0
IN_FLIGHT_OR_BEFORE = [item for item in MissionPhase if item is not MissionPhase.POSTFLIGHT]


@pytest.mark.parametrize("phase", IN_FLIGHT_OR_BEFORE)
@pytest.mark.parametrize("day", [0.0, 40.0, 179.5])
def test_outside_postflight_the_band_is_the_same_as_before(phase: MissionPhase, day: float) -> None:
    before = bone_density_band(day, exercise_logged=False)
    assert bone_density_band(
        day, exercise_logged=False, phase=phase, return_day=RETURN_DAY
    ) == before
    assert "cut" not in before


@pytest.mark.parametrize("day", [180.0, 200.0, 400.0])
def test_in_postflight_the_band_stops_at_the_return_day(day: float) -> None:
    band = bone_density_band(
        day, exercise_logged=False, phase=MissionPhase.POSTFLIGHT, return_day=RETURN_DAY
    )
    at_return = bone_density_band(RETURN_DAY, exercise_logged=False)
    assert band["now"] == at_return["now"]
    assert band["now"]["mission_day"] == RETURN_DAY
    # La tasa de vuelo no se proyecta en Tierra: ni el día 365 de una misión de 180.
    assert band["trajectory"] == []
    assert band["observation_type"] == "inferred"
    cut = band["cut"]
    assert cut["phase"] == "postflight"
    assert cut["label"] == RETURN_CUT_LABEL
    assert cut["basis"] == RETURN_CUT_BASIS
    assert cut["recovery"] == RECOVERY_STATEMENT
    assert cut["recovery_source"]["id"] == "ochmo-mtb-013"
    assert cut["recovery_source"]["url"]
    # La base y la nota del ejercicio siguen siendo las de siempre: solo se añade el corte.
    assert band["basis"] == at_return["basis"]
    assert band["exercise_note"] == at_return["exercise_note"]


def test_postflight_without_a_return_day_is_refused() -> None:
    with pytest.raises(ValueError, match="día de regreso"):
        bone_density_band(200.0, exercise_logged=False, phase=MissionPhase.POSTFLIGHT)


def test_the_recovery_sentence_says_no_more_than_the_card() -> None:
    notes = registry.get("ochmo-mtb-013").notes or ""
    # Las dos frases leídas que la sostienen (páginas 2 y 20), literales en la ficha.
    assert "trabecular bone may fail to recover" in notes
    assert "3 years post-flight or until recovered" in notes
    assert RECOVERY_SOURCE.id == "ochmo-mtb-013"
    # Sin tasa de recuperación en la fuente, la banda no baja y se dice.
    assert "no estima la recuperación" in RECOVERY_STATEMENT


def test_the_new_text_passes_the_language_guard() -> None:
    for text in (RETURN_CUT_LABEL, RETURN_CUT_BASIS, RECOVERY_STATEMENT):
        assert check(text) == [], text


def _client(tmp_path: Path, mission_days: int) -> TestClient:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, mission_days=mission_days
    )
    return TestClient(app)


@pytest.fixture
def cleanup() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()
    reset_store(None)


def _verdict(status: dict[str, Any]) -> dict[str, Any]:
    """Todo lo que el estado decide: niveles, puntuaciones, motivos, alertas y consejo."""
    return {
        "overall": status["overall_level"],
        "domains": {
            key: (value["score"], value["level"], value["drivers"])
            for key, value in status["domains"].items()
        },
        "alerts": [
            (alert["id"], alert["level"], alert["annunciation"]) for alert in status["alerts"]
        ],
        "recommendations": [
            (item["domain"], item["urgency"], item["notify_ground"])
            for item in status["recommendations"]
        ],
    }


def _status(tmp_path: Path, mission_days: int) -> dict[str, Any]:
    client = _client(tmp_path, mission_days)
    response = client.post(
        "/api/simulate", params={"scenario": "cardiovascular-deconditioning", "days": 40,
                                 "crew_size": 1},
    )
    assert response.status_code == 201, response.text
    status: dict[str, Any] = client.get("/api/status").json()
    return status


def test_the_status_cuts_the_band_in_postflight_and_the_verdict_does_not_move(
    tmp_path: Path, cleanup: None
) -> None:
    flying = _status(tmp_path / "a", 180)
    returned = _status(tmp_path / "b", 30)
    assert flying["mission"]["phase"] == "stable"
    assert returned["mission"]["phase"] == "postflight"
    [band] = returned["inferred"]
    assert band["now"]["mission_day"] == 30.0
    assert band["trajectory"] == []
    assert band["cut"]["recovery_source"]["id"] == "ochmo-mtb-013"
    [before] = flying["inferred"]
    assert "cut" not in before and before["now"]["mission_day"] > 30.0
    # La banda es inferida: cortarla no mueve ningún nivel, alerta ni recomendación.
    assert _verdict(returned) == _verdict(flying)


def test_the_band_does_not_score_or_alert(
    tmp_path: Path, cleanup: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = _status(tmp_path / "a", 30)

    def absurd(*args: Any, **kwargs: Any) -> dict[str, Any]:
        band = inferred.bone_density_band(*args, **kwargs)
        band["now"] = {"mission_day": 30.0, "loss_pct_low": 99.0, "loss_pct_high": 99.9}
        return band

    monkeypatch.setattr(routes, "bone_density_band", absurd)
    faked = _status(tmp_path / "b", 30)
    assert faked["inferred"][0]["now"]["loss_pct_low"] == 99.0
    assert _verdict(faked) == _verdict(real)
