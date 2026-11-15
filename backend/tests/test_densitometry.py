"""La densitometría medida en Tierra, junto a la banda ósea inferida.

Decisión del usuario (2026-10-26).

Qué fijan estas pruebas, sin red:
- que la comparación toma la última medida de antes del lanzamiento y la primera de después del
  regreso, por región, y dice dentro, por encima o por debajo de la banda del día de regreso,
  con la misma banda y el mismo redondeo que se sirven (`inferred.loss_band`);
- que no compara lo que no se puede: sin valor previo, con la previa de más de 180 días antes
  del lanzamiento (la de selección), sin medida posvuelo, con la primera
  posvuelo de 30 días o más tarde (incluye una recuperación que EMMA no estima) o con solo
  lecturas fechadas en vuelo, y lo dice;
- que solo lee lecturas medidas;
- que sin densitometría la banda sale idéntica, campo a campo, a la de antes;
- y la que importa (invariante 5): con densitometrías registradas, niveles, puntuaciones,
  alertas, consejo y la versión de las reglas son idénticos. Es una comprobación de la
  inferencia, no un veredicto clínico.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import densitometry
from app.analysis.densitometry import (
    IN_FLIGHT_NOTE,
    POSITION_STATEMENTS,
    POSTFLIGHT_WINDOW_DAYS,
    PRECISION_NOTE,
    PREFLIGHT_WINDOW_DAYS,
    RELATION,
    STATE_STATEMENTS,
    CheckState,
    Position,
    against_band,
)
from app.analysis.inferred import bone_density_band, loss_band
from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.core.mission import MissionPhase
from app.evidence import registry
from app.ingest.codes import DENSITOMETRY_KEYS, DESCRIPTIVE_ONLY
from app.ingest.fhir import ObservationType, VitalObservation, observation
from app.main import app
from app.text_guard import check

START = dt.date(2026, 11, 1)
RETURN_DAY = 180.0
LAUNCH = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)
SPINE, HIP = "bmd-dxa-lumbar-spine", "bmd-dxa-hip"


def _at(day: float) -> dt.datetime:
    return LAUNCH + dt.timedelta(days=day)


def _dxa(
    key: str, value: float, day: float, kind: ObservationType = ObservationType.MEASURED
) -> VitalObservation:
    return observation(
        key, value, _at(day), "crew-01", "manual", observation_type=kind,
        model_version=None if kind is ObservationType.MEASURED else "modelo@1",
    )


def _check(*readings: VitalObservation) -> dict[str, Any] | None:
    return against_band(readings, mission_start=START, return_day=RETURN_DAY)


def _region(check: dict[str, Any] | None, key: str) -> dict[str, Any]:
    assert check is not None
    return next(item for item in check["regions"] if item["key"] == key)


def test_the_two_regions_are_descriptive() -> None:
    assert {SPINE, HIP} == DENSITOMETRY_KEYS
    assert DENSITOMETRY_KEYS <= DESCRIPTIVE_ONLY


def test_without_densitometry_there_is_nothing_and_the_band_is_the_same() -> None:
    other = observation("heart-rate", 60, _at(10), "crew-01", "sim")
    assert _check() is None
    assert _check(other) is None
    before = bone_density_band(200.0, False, phase=MissionPhase.POSTFLIGHT, return_day=RETURN_DAY)
    assert bone_density_band(
        200.0, False, phase=MissionPhase.POSTFLIGHT, return_day=RETURN_DAY, densitometry=None
    ) == before
    assert "densitometry" not in before


@pytest.mark.parametrize(
    ("post", "position"),
    [
        (0.93, Position.WITHIN), (0.90, Position.ABOVE), (0.97, Position.BELOW),
        (1.02, Position.BELOW),
    ],
)
def test_the_measured_loss_is_placed_against_the_band_at_return(
    post: float, position: Position
) -> None:
    band = loss_band(RETURN_DAY)
    check = _check(_dxa(HIP, 1.0, -30), _dxa(HIP, post, RETURN_DAY + 5))
    assert check is not None
    assert check["band_day"] == RETURN_DAY
    assert check["band"] == {
        "loss_pct_low": band["loss_pct_low"], "loss_pct_high": band["loss_pct_high"]
    }
    hip = _region(check, HIP)
    assert hip["state"] == CheckState.COMPARED
    assert hip["measured_loss_pct"] == round((1.0 - post) * 100, 2)
    assert hip["position"] == position
    assert hip["statement"] == POSITION_STATEMENTS[position]
    assert hip["unit"] == "g/cm2" and hip["decimals"] == 3
    assert hip["preflight"]["label"] == densitometry.PREFLIGHT_LABEL
    assert hip["postflight"]["label"] == densitometry.POSTFLIGHT_LABEL
    assert hip["postflight"]["days_after_return"] == 5.0
    assert hip["postflight"]["when_display"] == "R+5,0 d"
    assert hip["preflight"]["when_display"] == "L-30,0 d"
    assert check["loss_label"] == densitometry.LOSS_LABEL
    assert check["band_label"] == densitometry.BAND_LABEL
    assert hip["preflight"]["days_after_return"] is None


def test_the_band_edges_count_as_within() -> None:
    band = loss_band(RETURN_DAY)
    for edge in (band["loss_pct_low"], band["loss_pct_high"]):
        post = 1.0 - edge / 100
        hip = _region(_check(_dxa(HIP, 1.0, -30), _dxa(HIP, post, RETURN_DAY + 1)), HIP)
        assert hip["measured_loss_pct"] == edge
        assert hip["position"] == Position.WITHIN


def test_it_takes_the_last_reading_before_launch_and_the_first_after_return() -> None:
    check = _check(
        _dxa(SPINE, 1.10, -180), _dxa(SPINE, 1.00, -30),
        _dxa(SPINE, 0.95, RETURN_DAY + 10), _dxa(SPINE, 0.80, RETURN_DAY + 2),
        _dxa(SPINE, 0.99, RETURN_DAY + 365),
    )
    spine = _region(check, SPINE)
    assert spine["preflight"]["value"] == 1.00
    assert spine["postflight"]["value"] == 0.80
    # Las de después de la que se compara son recuperación: se cuentan, no se comparan.
    assert spine["later_postflight"] == 2
    assert spine["measured_loss_pct"] == 20.0


@pytest.mark.parametrize(
    ("readings", "state"),
    [
        ([(1.0, -30)], CheckState.NO_POSTFLIGHT),
        ([(0.95, RETURN_DAY + 3)], CheckState.NO_PREFLIGHT),
        ([(1.0, -30), (0.95, RETURN_DAY + POSTFLIGHT_WINDOW_DAYS)], CheckState.LATE_POSTFLIGHT),
        # La de selección (L-18 meses) no es la previa de esta misión.
        ([(1.0, -PREFLIGHT_WINDOW_DAYS - 1), (0.95, RETURN_DAY + 3)], CheckState.OLD_PREFLIGHT),
        # Sin previa, lo que se dice es eso, aunque la posvuelo sea además tardía.
        ([(0.95, RETURN_DAY + 45)], CheckState.NO_PREFLIGHT),
        ([(1.0, 40), (0.95, 120)], CheckState.ONLY_IN_FLIGHT),
    ],
)
def test_what_cannot_be_compared_is_not_and_says_why(
    readings: list[tuple[float, float]], state: CheckState
) -> None:
    hip = _region(_check(*(_dxa(HIP, value, day) for value, day in readings)), HIP)
    assert hip["state"] == state
    assert hip["measured_loss_pct"] is None and hip["position"] is None
    assert hip["statement"] == STATE_STATEMENTS[state]


def test_the_preflight_window_edge_is_still_compared() -> None:
    hip = _region(
        _check(_dxa(HIP, 1.0, -PREFLIGHT_WINDOW_DAYS), _dxa(HIP, 0.93, RETURN_DAY + 1)), HIP
    )
    assert hip["state"] == CheckState.COMPARED


def test_the_day_after_return_is_shown_with_one_decimal() -> None:
    hip = _region(_check(_dxa(HIP, 1.0, -30), _dxa(HIP, 0.93, RETURN_DAY + 29.6)), HIP)
    # Se compara (menos de 30 días) y no se lee «R+30».
    assert hip["state"] == CheckState.COMPARED
    assert hip["postflight"]["when_display"] == "R+29,6 d"


def test_in_flight_readings_are_not_used() -> None:
    hip = _region(
        _check(_dxa(HIP, 1.0, -30), _dxa(HIP, 0.5, 90), _dxa(HIP, 0.93, RETURN_DAY + 1)), HIP
    )
    assert hip["preflight"]["value"] == 1.0 and hip["postflight"]["value"] == 0.93
    # Apartadas, pero dichas: una DXA de después del aterrizaje fechada antes del día de regreso
    # de la configuración no desaparece sin decirlo.
    assert hip["in_flight"] == 1
    assert hip["statement"] == f"{POSITION_STATEMENTS[Position.WITHIN]} {IN_FLIGHT_NOTE}"
    waiting = _region(_check(_dxa(HIP, 1.0, -30), _dxa(HIP, 0.93, RETURN_DAY - 0.5)), HIP)
    assert waiting["state"] == CheckState.NO_POSTFLIGHT and waiting["in_flight"] == 1
    assert waiting["statement"].endswith(IN_FLIGHT_NOTE)
    # Con solo lecturas de vuelo, la frase del estado ya lo dice: no se repite.
    only = _region(_check(_dxa(HIP, 0.93, 90)), HIP)
    assert only["state"] == CheckState.ONLY_IN_FLIGHT
    assert only["statement"] == STATE_STATEMENTS[CheckState.ONLY_IN_FLIGHT]
    clean = _region(_check(_dxa(HIP, 1.0, -30), _dxa(HIP, 0.93, RETURN_DAY + 1)), HIP)
    assert clean["in_flight"] == 0 and IN_FLIGHT_NOTE not in clean["statement"]


def test_a_preflight_that_is_not_a_density_is_not_shown() -> None:
    # El catálogo no admite una densidad de cero; si llegara, la región no enseña una previa
    # junto a la frase que dice que no la hay.
    # La validación de `observation` no la deja construir: se fuerza en la lectura ya hecha.
    zero = _dxa(HIP, 1.0, -30)
    object.__setattr__(zero, "value", 0.0)
    hip = _region(_check(zero, _dxa(HIP, 0.93, RETURN_DAY + 1)), HIP)
    assert hip["state"] == CheckState.NO_PREFLIGHT and hip["preflight"] is None


def test_only_measured_readings_count() -> None:
    inferred = _dxa(HIP, 0.5, RETURN_DAY + 1, ObservationType.INFERRED)
    assert _check(inferred) is None
    hip = _region(_check(_dxa(HIP, 1.0, -30), inferred), HIP)
    assert hip["state"] == CheckState.NO_POSTFLIGHT


def test_regions_without_readings_are_left_out_in_the_order_of_the_standard() -> None:
    check = _check(_dxa(SPINE, 1.0, -30), _dxa(HIP, 1.0, -30))
    assert check is not None
    assert [item["key"] for item in check["regions"]] == [HIP, SPINE]
    only_spine = _check(_dxa(SPINE, 1.0, -30))
    assert only_spine is not None
    assert [item["key"] for item in only_spine["regions"]] == [SPINE]


def test_the_texts_pass_the_language_guard_and_say_it_is_not_a_verdict() -> None:
    texts = [
        RELATION, PRECISION_NOTE, densitometry.LOSS_LABEL, densitometry.BAND_LABEL,
        *POSITION_STATEMENTS.values(), *STATE_STATEMENTS.values(),
    ]
    for text in texts:
        assert check(text) == [], text
    assert "no es un veredicto clínico" in RELATION
    assert set(STATE_STATEMENTS) == set(CheckState) - {CheckState.COMPARED}


def test_the_source_says_what_it_is_used_for_and_its_card_holds_the_quotes() -> None:
    assert densitometry.SOURCE.ref.id == "ochmo-mtb-013"
    notes = registry.get("ochmo-mtb-013").notes or ""
    assert "R+ < 30 days" in notes
    assert "no system to date measures bone density in-flight" in notes


# --------------------------------------------------------------------------- #
# Por la API: servida con la banda, y sin mover el estado
# --------------------------------------------------------------------------- #

MISSION_DAYS = 30


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, mission_days=MISSION_DAYS
    )
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _verdict(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "overall": status["overall_level"],
        "domains": {
            key: (value["score"], value["level"], value["drivers"])
            for key, value in status["domains"].items()
        },
        "alerts": [(alert["id"], alert["level"]) for alert in status["alerts"]],
        "recommendations": [
            (item["domain"], item["urgency"], item["notify_ground"])
            for item in status["recommendations"]
        ],
        "rules_version": status["rules_version"],
        "reference_time": status["data"]["reference_time"],
        "observations": status["data"]["observations"],
    }


def _post(client: TestClient, key: str, value: float, when: dt.datetime) -> None:
    response = client.post(
        "/api/observations",
        json={"key": key, "value": value, "subject": "crew-01", "effective": when.isoformat()},
    )
    assert response.status_code == 201, response.text


def test_the_status_serves_it_beside_the_band_and_the_verdict_does_not_move(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/simulate",
        params={"scenario": "cardiovascular-deconditioning", "days": 40, "crew_size": 1},
    )
    assert response.status_code == 201, response.text
    before = client.get("/api/status").json()
    assert "densitometry" not in before["inferred"][0]
    _post(client, HIP, 1.000, _at(-30))
    _post(client, HIP, 0.988, _at(MISSION_DAYS + 5))
    _post(client, SPINE, 1.100, _at(-30))
    after = client.get("/api/status").json()
    assert _verdict(after) == _verdict(before)
    [band] = after["inferred"]
    check = band["densitometry"]
    assert check["band_day"] == float(MISSION_DAYS)
    assert check["band"]["loss_pct_low"] == band["now"]["loss_pct_low"]
    assert check["band"]["loss_pct_high"] == band["now"]["loss_pct_high"]
    hip = _region(check, HIP)
    assert hip["state"] == CheckState.COMPARED and hip["position"] == Position.WITHIN
    assert hip["measured_loss_pct"] == 1.2
    assert _region(check, SPINE)["state"] == CheckState.NO_POSTFLIGHT
    # La banda sigue siendo la misma: la densitometría va al lado.
    assert {key: value for key, value in band.items() if key != "densitometry"} == before[
        "inferred"
    ][0]
