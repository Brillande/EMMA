"""Rachas de las medidas periódicas (`routines.streaks`): la gamificación del reto, sin juicio.

Una cifra, «N periodos seguidos», contada con las mismas lecturas y el mismo ahora que el estado
de las rutinas. No es adherencia (no hay pauta prescrita) y no entra en el riesgo. Sin red.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import routines, text_guard
from app.ingest.fhir import observation

T0 = dt.datetime(2026, 11, 10, 12, tzinfo=dt.UTC)
APP = Path(routines.__file__).resolve().parent


def _hr(hours_ago: float, confidence: float = 1.0, subject: str = "crew-01"):  # type: ignore[no-untyped-def]
    # Pulso: periodo de diseño de 6 h.
    return observation("heart-rate", 60.0, T0 - dt.timedelta(hours=hours_ago), subject, "x",
                       confidence=confidence)


def _streak(result: dict, key: str = "heart-rate") -> tuple[int, int]:  # type: ignore[type-arg]
    [found] = [item for item in result["routines"] if item["key"] == key]
    return found["current"], found["longest"]


def test_without_readings_every_streak_is_zero() -> None:
    result = routines.streaks([], now=T0)
    assert {(item["current"], item["longest"]) for item in result["routines"]} == {(0, 0)}
    assert len(result["routines"]) == len(routines.load()["routines"])


def test_one_good_reading_per_period_makes_a_streak_of_n() -> None:
    # Cuatro lecturas a 6 h justas (el periodo): abarcan cuatro periodos.
    readings = [_hr(1), _hr(7), _hr(13), _hr(19)]
    assert _streak(routines.streaks(readings, now=T0)) == (4, 4)
    # Dos en el mismo periodo no hacen dos.
    assert _streak(routines.streaks([_hr(1), _hr(2)], now=T0)) == (1, 1)


def test_the_edges_follow_estado_rutina() -> None:
    # La última justo en P sigue contando («justo en P sigue al día»); un instante después, no.
    assert _streak(routines.streaks([_hr(6)], now=T0)) == (1, 1)
    assert _streak(routines.streaks([_hr(6.01)], now=T0)) == (0, 1)
    # Un hueco de P justo no corta; uno mayor sí, aunque las dos caigan en periodos contiguos:
    # durante ese hueco el estado de la rutina ya era «atrasada».
    assert _streak(routines.streaks([_hr(0), _hr(6)], now=T0)) == (2, 2)
    assert _streak(routines.streaks([_hr(0.5), _hr(11.5)], now=T0)) == (1, 1)


def test_a_gap_cuts_the_streak_and_the_longest_survives() -> None:
    # Serie vigente de dos (1 h y 7 h), hueco de 12 h, serie antigua de tres (19, 25, 31 h).
    readings = [_hr(1), _hr(7), _hr(19), _hr(25), _hr(31)]
    assert _streak(routines.streaks(readings, now=T0)) == (2, 3)
    # Si la última buena tiene más de P, la racha vigente es 0 aunque la de antes fuera larga.
    assert _streak(routines.streaks([_hr(7), _hr(13)], now=T0)) == (0, 2)


def test_the_longest_does_not_move_with_now() -> None:
    readings = [_hr(h) for h in range(1, 40, 6)]
    seen = {_streak(routines.streaks(readings, now=T0 + dt.timedelta(hours=k)))[1]
            for k in range(0, 48, 1)}
    assert seen == {7}


def test_a_low_confidence_reading_does_not_count() -> None:
    # Entre las dos buenas solo hay una de confianza baja: no tapa el hueco de 12 h, porque
    # para `evaluate` no es un éxito.
    readings = [_hr(1), _hr(7, confidence=0.2), _hr(13)]
    assert _streak(routines.streaks(readings, now=T0)) == (1, 1)


def test_a_reading_after_now_is_not_a_streak() -> None:
    assert _streak(routines.streaks([_hr(-3)], now=T0)) == (0, 0)


def test_the_streak_belongs_to_one_crew_member() -> None:
    with pytest.raises(ValueError, match="tripulante"):
        routines.streaks([_hr(1), _hr(1, subject="crew-02")], now=T0)


def test_the_text_is_neutral_and_passes_the_language_filter() -> None:
    result = routines.streaks([_hr(1)], now=T0)
    texts = [result["label"], result["note"], result["longest_label"]]
    texts += sorted({item["unit"] for item in result["routines"]})
    for text in texts:
        assert text_guard.check(text) == [], text
    joined = " ".join(texts).lower()
    assert "ritmo de diseño" in joined
    assert "adherencia" in joined  # dice que NO lo es
    for praise in ("bien hecho", "enhorabuena", "felicidades", "excelente", "%"):
        assert praise not in joined
    units = {item["key"]: item["unit"] for item in result["routines"]}
    assert units["heart-rate"] == "periodo seguido"
    assert units["body-weight"] == "periodos seguidos"  # 0, en plural


def test_the_risk_engine_and_the_alerts_do_not_read_streaks() -> None:
    """Fuera del riesgo, de las alertas y del asesor: ningún módulo que decide las lee."""
    for folder in ("analysis", "advisor", "core", "validation"):
        for path in (APP / folder).rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert "streaks" not in source and "STREAK_TEXT" not in source, path


def test_the_endpoint_serves_streaks_and_honours_the_ground_cut(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "nominal", "days": 10})
    body = client.get("/api/timeline/routines").json()
    streaks = body["streaks"]
    assert streaks["label"].startswith("Ritmo de diseño")
    current, longest = _streak(streaks)
    # Diez días de pulso continuo con periodo de 6 h: unos 40 periodos seguidos.
    assert 30 <= current == longest <= 41
    # Tierra, con un corte tres días después de su última lectura: la racha vigente se cortó.
    late = (dt.datetime.fromisoformat(body["now"]) + dt.timedelta(days=3)).isoformat()
    cut = client.get("/api/timeline/routines", params={"until": late}).json()
    assert _streak(cut["streaks"])[0] == 0
    # La más larga sigue ahí: solo depende de las lecturas.
    assert _streak(cut["streaks"])[1] == longest
    # Un corte en mitad de la misión: solo cuenta lo que Tierra tenía.
    middle = (dt.datetime.fromisoformat(body["now"]) - dt.timedelta(days=5)).isoformat()
    half = client.get("/api/timeline/routines", params={"until": middle}).json()
    assert 0 < _streak(half["streaks"])[0] < current
