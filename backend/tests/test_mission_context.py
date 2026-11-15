"""Fase de misión y detalle de alerta (especificación del equipo §3, §10).

La fase se calcula y se muestra, pero no entra en el análisis (invariante 5); sus límites son
de diseño y lo dicen. El detalle de alerta responde a "qué cambió, desde cuándo y frente a
qué", con la base de cada cifra.
"""

import datetime as dt
from pathlib import Path

from fastapi.testclient import TestClient

from app.analysis.baseline import Baseline, Deviation, Severity, SeverityBasis
from app.analysis.explain import detail
from app.core.mission import (
    ADAPTATION_DAYS,
    EARTH_GRAVITY,
    MISSION_GRAVITY_LABEL,
    MissionPhase,
    context,
    phase_at,
)
from app.ingest.codes import Domain
from app.text_guard import check

START = dt.date(2026, 11, 1)
T0 = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)


def test_phases_follow_the_mission_calendar() -> None:
    at = lambda days: phase_at(T0 + dt.timedelta(days=days), START, 180)  # noqa: E731
    assert at(-1) is MissionPhase.PREFLIGHT
    assert at(0) is MissionPhase.ADAPTATION
    assert at(ADAPTATION_DAYS) is MissionPhase.STABLE
    assert at(175) is MissionPhase.RETURN
    assert at(181) is MissionPhase.POSTFLIGHT


def test_the_phase_limits_declare_they_are_design() -> None:
    described = context(T0 + dt.timedelta(days=40), START, 180, "microgravity")
    assert described["phase"] == "stable"
    assert described["mission_day"] == 40.0
    assert "diseño EMMA" in described["phase_basis"]
    assert "no cambia el análisis" in described["phase_basis"]


# --------------------------------------------------------------------------- #
# Gravedad del momento y de la misión (decisión del usuario, 2026-10-20)
# --------------------------------------------------------------------------- #


def test_after_landing_the_gravity_of_the_moment_is_earths_and_the_missions_is_kept() -> None:
    # El día 180 ya es posvuelo: la misión configurada dura 180 días.
    for days in (180, 181, 400):
        described = context(T0 + dt.timedelta(days=days), START, 180, "microgravedad")
        assert described["phase"] == "postflight"
        assert described["gravity_now"] == EARTH_GRAVITY == "en Tierra (gravedad terrestre)"
        assert described["gravity_mission"] == "microgravedad"
        # «1 g» lo lee el filtro de lenguaje como una dosis (ver la cabecera de `core/mission`).
        assert check(described["gravity_display"]) == []
        assert described["gravity_mission_label"] == MISSION_GRAVITY_LABEL
        assert described["gravity_display"] == (
            "en Tierra (gravedad terrestre); "
            "gravedad de la misión, declarada por configuración: microgravedad"
        )
        # Lo que ya servía la API se queda como estaba: la configurada.
        assert described["gravity_regime"] == "microgravedad"


def test_outside_postflight_the_gravity_of_the_moment_is_the_missions() -> None:
    seen = set()
    for days in (-30, -0.5, 0, ADAPTATION_DAYS, 40, 175, 179.9):
        described = context(T0 + dt.timedelta(days=days), START, 180, "gravedad lunar")
        seen.add(described["phase"])
        assert described["gravity_now"] == described["gravity_mission"] == "gravedad lunar"
        assert described["gravity_display"] == "gravedad lunar"
    assert seen == {str(phase) for phase in MissionPhase} - {"postflight"}


def test_no_analysis_module_reads_the_gravity() -> None:
    """Solo texto (invariante 5): el motor no lee la gravedad. La frase del contexto de una
    alerta es la única que la usa, y no vuelve al nivel."""
    analysis = Path(__file__).resolve().parents[1] / "app" / "analysis"
    readers = sorted(
        path.name for path in analysis.glob("*.py")
        if "gravity_" in path.read_text(encoding="utf-8")
    )
    assert readers == ["alert_context.py"]


def _deviation(hours: int, value: float, severity: Severity) -> Deviation:
    baseline = Baseline(
        key="heart-rate", center=60.0, spread=4.0, samples=200,
        sorted_values=tuple(float(v) for v in range(52, 69)),
    )
    return Deviation(
        subject="crew-01", key="heart-rate", value=value,
        effective=T0 + dt.timedelta(hours=hours), z_score=3.0, severity=severity,
        direction="high", baseline=baseline, used_population_range=False,
        basis=SeverityBasis.PERSONAL_PERCENTILE,
    )


def test_the_detail_says_since_when_and_against_what() -> None:
    current = [
        _deviation(1, 61.0, Severity.NONE),
        _deviation(3, 82.0, Severity.MILD),
        _deviation(5, 88.0, Severity.MODERATE),
    ]
    result = detail(Domain.CARDIOVASCULAR, current, [])
    assert result["onset"] == (T0 + dt.timedelta(hours=3)).isoformat()
    [changed] = result["changed"]
    assert changed["value"] == 88.0
    assert changed["baseline_median"] == 60.0
    assert changed["compared_with"] == "línea base personal"
    assert result["ridge"] == "gravity"


def test_without_a_deviation_there_is_no_onset_and_it_says_why() -> None:
    result = detail(Domain.RADIATION, [], [])
    assert result["onset"] is None
    assert "evento externo" in result["onset_basis"]


def test_the_status_carries_mission_context_and_alert_detail(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "progressive-insomnia", "days": 40})
    status = client.get("/api/status").json()
    mission = status["mission"]
    assert mission["phase"] == "stable"
    assert 39 <= mission["mission_day"] <= 40
    [alert] = [item for item in status["alerts"] if item["domain"] == "behavioral"]
    assert alert["detail"]["onset"] is not None
    assert alert["detail"]["changed"]
    assert alert["detail"]["ridge"] == "isolation"


def test_bone_loss_is_an_inferred_band_that_grows_with_the_mission() -> None:
    from app.analysis.inferred import bone_density_band

    early = bone_density_band(30.0, exercise_logged=False)
    late = bone_density_band(120.0, exercise_logged=True)
    assert early["observation_type"] == "inferred" and early["model_version"]
    assert early["now"]["loss_pct_low"] < early["now"]["loss_pct_high"]
    assert late["now"]["loss_pct_low"] > early["now"]["loss_pct_low"]
    assert all(item["mission_day"] > 120 for item in late["trajectory"])
    # El ejercicio se menciona pero no estrecha la banda: su efecto no tiene magnitud citable.
    assert bone_density_band(120.0, exercise_logged=False)["now"] == late["now"]
    assert "no es una medida" in early["basis"]
