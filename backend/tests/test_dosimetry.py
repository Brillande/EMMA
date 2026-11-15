"""Conversion de dosis absorbida a equivalente.

La version anterior usaba Q = 1 y subestimaba la dosis unas dos veces y media.
Estas pruebas fijan tanto la formula estandar como la propiedad que evita repetir
el error: una cifra de dosis nunca viaja sin decir como se obtuvo.
"""

import datetime as dt
import json
import math
from typing import Any

import pytest

from app.core.cache import CachedPayload
from app.environment.dosimetry import (
    ICRP60_HIGH_LET,
    ICRP60_LOW_LET,
    MEAN_QUALITY_FACTORS,
    QualityFactorModel,
    effective_dose,
    icrp60_quality_factor,
)
from app.environment.radlab import DoseSample

NOW = dt.datetime(2022, 4, 1, tzinfo=dt.UTC)


def series(rates: list[float], equivalent: list[float] | None = None) -> list[DoseSample]:
    """Serie horaria de dosimetria."""
    return [
        DoseSample(
            timestamp=NOW + dt.timedelta(hours=i),
            instrument="DosTel1",
            spacecraft="ISS",
            absorbed_dose_rate=rate,
            dose_equivalent_rate=equivalent[i] if equivalent else None,
        )
        for i, rate in enumerate(rates)
    ]


# --------------------------------------------------------------------------- #
# ICRP 60 Q(L)
# --------------------------------------------------------------------------- #


def test_low_let_radiation_has_unit_quality_factor() -> None:
    assert icrp60_quality_factor(0.0) == 1.0
    assert icrp60_quality_factor(ICRP60_LOW_LET - 0.001) == 1.0


def test_intermediate_let_uses_the_linear_branch() -> None:
    """Q = 0,32 L - 2,2 para 10 <= L <= 100 keV/um."""
    assert icrp60_quality_factor(50.0) == pytest.approx(0.32 * 50 - 2.2)
    # A 100 keV/um la rama lineal da 29,8 — no 30, que es el redondeo de cabeza
    # en el que es facil caer.
    assert icrp60_quality_factor(ICRP60_HIGH_LET) == pytest.approx(29.8)


def test_high_let_uses_the_inverse_square_root_branch() -> None:
    """Q = 300 / sqrt(L) para L > 100 keV/um."""
    assert icrp60_quality_factor(400.0) == pytest.approx(300.0 / 20.0)


def test_quality_factor_is_continuous_at_the_low_boundary() -> None:
    """A 10 keV/um las dos primeras ramas se encuentran: 0,32*10-2,2 = 1,0."""
    assert icrp60_quality_factor(ICRP60_LOW_LET) == pytest.approx(1.0)


def test_quality_factor_is_nearly_continuous_at_the_high_boundary() -> None:
    """ICRP 60 no empalma exacto a 100 keV/um: 29,8 frente a 30,0.

    La discontinuidad es del propio estandar, no de la implementacion. Se fija
    aqui para que nadie la 'arregle' desviandose de la norma.
    """
    linear_end = 0.32 * ICRP60_HIGH_LET - 2.2
    sqrt_start = 300.0 / math.sqrt(ICRP60_HIGH_LET)

    assert linear_end == pytest.approx(29.8)
    assert sqrt_start == pytest.approx(30.0)
    assert icrp60_quality_factor(ICRP60_HIGH_LET) == pytest.approx(linear_end)


def test_quality_factor_decreases_above_the_peak() -> None:
    assert icrp60_quality_factor(1000.0) < icrp60_quality_factor(200.0)
    assert icrp60_quality_factor(200.0) < icrp60_quality_factor(ICRP60_HIGH_LET)


def test_negative_let_is_rejected() -> None:
    with pytest.raises(ValueError, match="negativa"):
        icrp60_quality_factor(-1.0)


# --------------------------------------------------------------------------- #
# Dosis efectiva
# --------------------------------------------------------------------------- #


def test_measured_dose_equivalent_is_preferred_over_estimation() -> None:
    """Si el instrumento da H medida, no se estima."""
    estimate = effective_dose(series([10.0] * 5, equivalent=[24.0] * 5))

    assert estimate.is_measured
    assert estimate.model is QualityFactorModel.MEASURED
    # 24 uSv/h durante 4 h = 96 uSv = 0,096 mSv
    assert estimate.value_msv == pytest.approx(0.096)
    assert "medida" in estimate.describe()


def test_falls_back_to_quality_factor_when_no_measurement() -> None:
    """El caso real: RadLab nunca publica dosis equivalente para la ISS."""
    estimate = effective_dose(series([10.0] * 5))

    assert not estimate.is_measured
    assert estimate.model is QualityFactorModel.MISSION_AVERAGE
    # 10 uGy/h durante 4 h = 40 uGy = 0,04 mGy; x 2,38 = 0,0952 mSv
    assert estimate.value_msv == pytest.approx(0.04 * 2.38)
    assert "estimada" in estimate.describe()


def test_unit_quality_factor_underestimates_by_the_mission_average() -> None:
    """Es el error que tenia la version anterior, fijado como regresion."""
    samples = series([10.0] * 5)
    unit = effective_dose(samples, model=QualityFactorModel.UNIT)
    mission = effective_dose(samples, model=QualityFactorModel.MISSION_AVERAGE)

    assert mission.value_msv / unit.value_msv == pytest.approx(2.38)


def test_galactic_cosmic_is_harsher_than_trapped() -> None:
    samples = series([10.0] * 5)
    trapped = effective_dose(samples, model=QualityFactorModel.TRAPPED)
    gcr = effective_dose(samples, model=QualityFactorModel.GALACTIC_COSMIC)

    assert gcr.value_msv > trapped.value_msv


def test_integration_is_trapezoidal_over_real_gaps() -> None:
    """RadLab tiene huecos: no se puede asumir cadencia fija."""
    sparse = [
        DoseSample(NOW, "DosTel1", "ISS", 10.0),
        DoseSample(NOW + dt.timedelta(hours=10), "DosTel1", "ISS", 10.0),
    ]
    estimate = effective_dose(sparse, model=QualityFactorModel.UNIT)

    assert estimate.hours_covered == pytest.approx(10.0)
    assert estimate.value_msv == pytest.approx(0.1)  # 100 uGy = 0,1 mGy


def test_per_day_projection() -> None:
    estimate = effective_dose(series([10.0] * 13), model=QualityFactorModel.UNIT)
    assert estimate.hours_covered == pytest.approx(12.0)
    assert estimate.per_day_msv == pytest.approx(estimate.value_msv * 2)


def test_single_sample_yields_no_dose() -> None:
    assert effective_dose(series([10.0])).value_msv == 0.0
    assert effective_dose([]).value_msv == 0.0


def test_estimate_always_declares_its_provenance() -> None:
    """La propiedad que impide repetir el error: nunca una cifra pelada."""
    payload = effective_dose(series([10.0] * 5)).to_dict()

    assert payload["measured"] is False
    assert payload["quality_factor"] == 2.38
    assert payload["source"]
    assert "estimada" in payload["description"]


def test_measured_estimate_reports_no_quality_factor_and_stays_json() -> None:
    """No hay Q que declarar cuando la dosis equivalente viene medida: `None`, no NaN.

    Lógica 1 (2026-11-11): el NaN de antes no cabe en JSON estricto, y `/api/radiation/dose`
    caía con un 500 justo en el caso que el módulo dice preferir.
    """
    estimate = effective_dose(series([10.0] * 5, equivalent=[24.0] * 5))
    assert estimate.quality_factor is None
    payload = estimate.to_dict()
    json.dumps(payload, allow_nan=False)
    assert payload["quality_factor"] is None and payload["measured"] is True


class _Series:
    """Un RadLab sin red que devuelve la serie que se le dé."""

    samples: list[DoseSample] = []

    def __init__(self, settings: Any) -> None:
        pass

    def dose_series(self, start: dt.date, end: dt.date) -> CachedPayload:
        return CachedPayload(
            data=self.samples, fetched_at=dt.datetime.now(dt.UTC), source="prueba",
            from_cache=True,
        )


def _dose_route(monkeypatch: pytest.MonkeyPatch, samples: list[DoseSample]) -> Any:
    from fastapi.testclient import TestClient

    from app.api import routes
    from app.main import app

    monkeypatch.setattr(_Series, "samples", samples)
    monkeypatch.setattr(routes, "RadLabClient", _Series)
    return TestClient(app).get(
        "/api/radiation/dose", params={"start": "2022-04-01", "end": "2022-04-02"}
    )


def test_the_dose_route_serves_a_measured_dose_and_says_no_mean_q_was_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _dose_route(monkeypatch, series([10.0] * 5, equivalent=[24.0] * 5))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dose"]["measured"] is True
    assert body["dose"]["quality_factor"] is None
    # La advertencia no dice que se aplicó un factor medio cuando no se aplicó.
    assert "factor de calidad medio" not in body["caveat"]
    assert "medida" in body["caveat"]


def test_the_dose_route_rejects_measured_as_a_quality_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lógica 1: `quality_model=measured` con solo dosis absorbida caía con un `KeyError` (500)."""
    from fastapi.testclient import TestClient

    from app.api import routes
    from app.main import app

    monkeypatch.setattr(_Series, "samples", series([10.0] * 5))
    monkeypatch.setattr(routes, "RadLabClient", _Series)
    response = TestClient(app).get(
        "/api/radiation/dose",
        params={"start": "2022-04-01", "end": "2022-04-02", "quality_model": "measured"},
    )
    assert response.status_code == 422
    assert "mission-average" in response.json()["detail"]


@pytest.mark.parametrize("count", [0, 1])
def test_the_dose_route_gives_no_zero_for_a_series_it_cannot_integrate(
    monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    """Lógica 1: con menos de dos muestras salía «0 mSv» como si fuera una medida."""
    response = _dose_route(monkeypatch, series([10.0] * count))
    assert response.status_code == 404
    assert "hacen falta dos" in response.json()["detail"]


def test_every_model_carries_a_cited_source() -> None:
    for model, factor in MEAN_QUALITY_FACTORS.items():
        assert factor.source.strip(), f"{model} sin procedencia"
        assert factor.value > 0


def test_mission_average_sits_between_trapped_and_gcr() -> None:
    """Coherencia fisica: la mision mezcla ambas componentes."""
    trapped = MEAN_QUALITY_FACTORS[QualityFactorModel.TRAPPED].value
    gcr = MEAN_QUALITY_FACTORS[QualityFactorModel.GALACTIC_COSMIC].value
    mission = MEAN_QUALITY_FACTORS[QualityFactorModel.MISSION_AVERAGE].value

    assert trapped < mission < gcr


@pytest.mark.live
def test_real_iss_dose_lands_in_the_documented_range() -> None:
    """Contraste con la literatura, usando la serie REAL de DosTel.

    La ISS recibe ~0,3-0,8 mSv/dia. Esta prueba golpea RadLab de verdad porque la
    afirmacion es sobre datos reales: reproducirla con una serie sintetica seria
    comprobar mi aritmetica, no la del mundo.
    """
    import datetime as real_dt
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from app.core.config import Settings
    from app.environment.radlab import RadLabClient

    with TemporaryDirectory() as tmp:
        client = RadLabClient(settings=Settings(cache_dir=Path(tmp)))
        payload = client.dose_series(real_dt.date(2022, 4, 1), real_dt.date(2022, 4, 2))

    unit = effective_dose(payload.data, model=QualityFactorModel.UNIT)
    mission = effective_dose(payload.data, model=QualityFactorModel.MISSION_AVERAGE)

    assert unit.hours_covered > 0
    assert unit.per_day_msv < 0.3, (
        f"con Q = 1 debería quedar por debajo del rango documentado, "
        f"dio {unit.per_day_msv:.3f} mSv/día"
    )
    assert 0.3 <= mission.per_day_msv <= 0.8, (
        f"con el factor de misión debería caer dentro de 0,3-0,8 mSv/día, "
        f"dio {mission.per_day_msv:.3f}"
    )


def test_mission_factor_scales_the_estimate_as_expected() -> None:
    """La relacion entre modelos es aritmetica pura y si se puede fijar aqui."""
    samples = series([2.0] * 25)
    unit = effective_dose(samples, model=QualityFactorModel.UNIT)
    mission = effective_dose(samples, model=QualityFactorModel.MISSION_AVERAGE)

    assert mission.per_day_msv == pytest.approx(unit.per_day_msv * 2.38)
