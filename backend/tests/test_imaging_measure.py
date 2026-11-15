"""Medidas ecográficas: geometría con resultado conocido y rechazos con motivo.

Cada caso usa una calibración y unos puntos cuya medida real se sabe de antemano. Si el
motor se equivoca en la escala, en la fórmula o en una comprobación, el número no cuadra.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes import get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.imaging.dicom import CalibratedRegion
from app.imaging.measure import (
    MEASUREMENT_EVIDENCE,
    METHOD,
    Annotation,
    MeasurementError,
    Point,
    measure,
)
from app.ingest.codes import CATALOG, ULTRASOUND_MEASURES
from app.main import app
from tests.test_imaging import _region, ultrasound_dicom

# 0,1 mm por píxel en los dos ejes: 10 píxeles son 1 mm.
REGION = CalibratedRegion(0, 0, 1000, 1000, 0.1, 0.1)


def ann(*points: tuple[float, float], frame: int = 0) -> Annotation:
    return Annotation(frame, tuple(Point(x, y) for x, y in points))


def onsd(sheath_y: float = 130, left: float = 475, right: float = 525) -> dict[str, Annotation]:
    # Globo en y = 100; la vaina a 30 px = 3 mm por detrás; 50 px de ancho = 5 mm.
    return {"globe": ann((500, 100)), "sheath": ann((left, sheath_y), (right, sheath_y))}


# --------------------------------------------------------------------------- #
# Nervio óptico
# --------------------------------------------------------------------------- #


def test_optic_nerve_sheath_diameter_in_millimetres() -> None:
    result = measure("onsd", "right", onsd(), [REGION], frames=1)
    assert result.key == "onsd-right"
    assert result.value == pytest.approx(5.0)
    assert result.details["depth_mm"] == pytest.approx(3.0)
    assert result.details["angle_deg"] == pytest.approx(90.0)


def test_the_scale_of_each_axis_is_respected() -> None:
    """Con píxeles no cuadrados, medir en píxeles y multiplicar por una sola escala falla."""
    anisotropic = CalibratedRegion(0, 0, 1000, 1000, 0.2, 0.1)
    # 30 px en vertical = 3 mm; 25 px en horizontal = 5 mm.
    result = measure("onsd", "left", onsd(left=487.5, right=512.5), [anisotropic], frames=1)
    assert result.value == pytest.approx(5.0)


def test_a_sheath_measured_at_the_wrong_depth_is_refused() -> None:
    with pytest.raises(MeasurementError, match="5,0 mm del globo"):
        measure("onsd", "right", onsd(sheath_y=150), [REGION], frames=1)


def test_a_sheath_line_that_is_not_perpendicular_is_refused() -> None:
    oblique = {"globe": ann((500, 100)), "sheath": ann((475, 120), (525, 140))}
    with pytest.raises(MeasurementError, match="perpendiculares"):
        measure("onsd", "right", oblique, [REGION], frames=1)


def test_the_eye_has_to_be_declared() -> None:
    with pytest.raises(MeasurementError, match="lado"):
        measure("onsd", None, onsd(), [REGION], frames=1)


def test_points_in_two_calibrated_regions_are_not_a_distance() -> None:
    upper = CalibratedRegion(0, 0, 1000, 115, 0.1, 0.1)
    lower = CalibratedRegion(0, 116, 1000, 1000, 0.1, 0.1)
    with pytest.raises(MeasurementError, match="misma región"):
        measure("onsd", "right", onsd(), [upper, lower], frames=1)


def test_an_uncalibrated_study_can_be_seen_but_not_measured() -> None:
    with pytest.raises(MeasurementError, match="calibración"):
        measure("onsd", "right", onsd(), [], frames=1)


def test_missing_or_extra_annotations_are_refused() -> None:
    with pytest.raises(MeasurementError, match="exige las anotaciones"):
        measure("onsd", "right", {"globe": ann((500, 100))}, [REGION], frames=1)


def test_a_frame_outside_the_study_is_refused() -> None:
    marks = {"globe": ann((500, 100), frame=3), "sheath": ann((475, 130), (525, 130), frame=3)}
    with pytest.raises(MeasurementError, match="fotograma"):
        measure("onsd", "right", marks, [REGION], frames=2)


# --------------------------------------------------------------------------- #
# Vejiga
# --------------------------------------------------------------------------- #


def bladder(width_end: tuple[float, float] = (950, 100)) -> dict[str, Annotation]:
    # Alto 80 mm (vertical), ancho 90 mm (horizontal), largo 100 mm en otro fotograma.
    return {
        "height": ann((50, 100), (50, 900)),
        "width": ann((50, 100), width_end),
        "length": ann((0, 0), (1000, 0), frame=1),
    }


def test_bladder_volume_follows_the_loinc_formula() -> None:
    result = measure("bladder-volume", None, bladder(), [REGION], frames=2)
    assert result.key == "bladder-volume"
    # 80 × 90 × 100 mm³ × 0,57 = 410 400 mm³ = 410,4 cm³
    assert result.value == pytest.approx(410.4)
    assert result.details["height_width_angle_deg"] == pytest.approx(90.0)


def test_height_and_width_must_be_perpendicular() -> None:
    with pytest.raises(MeasurementError, match="perpendiculares"):
        measure("bladder-volume", None, bladder(width_end=(700, 700)), [REGION], frames=2)


def test_the_coefficient_is_the_one_the_code_declares() -> None:
    """15309-8 define H × W × L × 0,57. Cambiar el coeficiente exige cambiar de código."""
    assert CATALOG["bladder-volume"].code == "15309-8"
    assert METHOD["bladder_coefficient"].value == 0.57


# --------------------------------------------------------------------------- #
# Yugular
# --------------------------------------------------------------------------- #

# Un cuadrado de 100 px = 10 mm de lado, con puntos también a mitad de cada lado.
SQUARE = ((100, 100), (150, 100), (200, 100), (200, 150), (200, 200), (150, 200),
          (100, 200), (100, 150))


def test_vein_area_from_a_contour() -> None:
    result = measure("ijv-csa", "left", {"contour": ann(*SQUARE)}, [REGION], frames=1)
    assert result.key == "ijv-csa-left"
    assert result.value == pytest.approx(100.0)


def test_a_contour_that_crosses_itself_is_refused() -> None:
    bowtie = ((100, 100), (200, 200), (200, 150), (200, 100), (100, 200), (100, 150))
    with pytest.raises(MeasurementError, match="se cruza"):
        measure("ijv-csa", "left", {"contour": ann(*bowtie)}, [REGION], frames=1)


def test_a_contour_needs_enough_points() -> None:
    with pytest.raises(MeasurementError, match="al menos"):
        measure("ijv-csa", "left", {"contour": ann(*SQUARE[:4])}, [REGION], frames=1)


# --------------------------------------------------------------------------- #
# Respaldo declarado
# --------------------------------------------------------------------------- #


def test_every_method_parameter_declares_its_backing() -> None:
    for name, param in METHOD.items():
        assert param.evidence in MEASUREMENT_EVIDENCE, name
        assert param.note, name
        if param.evidence != "design":
            assert param.source, f"{name} dice tener respaldo y no lo cita"


def test_ultrasound_measures_have_no_population_alarm() -> None:
    """Sin umbral poblacional: en vuelo estas medidas cambian en gente sana."""
    for key in ULTRASOUND_MEASURES:
        code = CATALOG[key]
        assert code.critical_low is None and code.critical_high is None, key
        assert code.reference_low is None and code.reference_high is None, key


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _upload(client: TestClient, protocol: str) -> int:
    region = _region()
    region.RegionLocationMaxX1, region.RegionLocationMaxY1 = 1000, 1000
    response = client.post(
        "/api/imaging/studies",
        params={"protocol": protocol},
        content=ultrasound_dicom(regions=[region]),
        headers={"content-type": "application/dicom"},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["ledger_index"])


ONSD_BODY = {
    "measure": "onsd",
    "laterality": "right",
    "measured_by": "CMO",
    "annotations": {
        "globe": {"points": [[500, 100]]},
        "sheath": {"points": [[475, 130], [525, 130]]},
    },
}


def test_a_measurement_enters_the_catalog_with_its_provenance(client: TestClient) -> None:
    study = _upload(client, "optic-nerve")
    response = client.post(f"/api/imaging/studies/{study}/measurements", json=ONSD_BODY)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["key"] == "onsd-right" and body["value"] == pytest.approx(5.0)

    [reading] = get_store().query("crew-01", key="onsd-right")
    assert reading.value == pytest.approx(5.0)
    assert reading.effective == dt.datetime(2026, 11, 14, 7, 30, tzinfo=dt.UTC)

    [listed] = client.get(f"/api/imaging/studies/{study}/measurements").json()
    assert listed["annotations"]["sheath"]["points"] == [[475, 130], [525, 130]]
    assert listed["measured_by"] == "CMO" and listed["value"] == pytest.approx(5.0)
    assert listed["method"]["onsd_depth_mm"] == 3.0
    assert get_store().verify_integrity().ok


def test_a_measure_from_another_protocol_is_refused(client: TestClient) -> None:
    study = _upload(client, "bladder")
    response = client.post(f"/api/imaging/studies/{study}/measurements", json=ONSD_BODY)
    assert response.status_code == 422
    assert get_store().query("crew-01", key="onsd-right") == []


def test_a_bad_measurement_writes_nothing(client: TestClient) -> None:
    study = _upload(client, "optic-nerve")
    before = len(get_store().ledger)
    wrong_depth = {**ONSD_BODY, "annotations": {
        "globe": {"points": [[500, 100]]},
        "sheath": {"points": [[475, 180], [525, 180]]},
    }}
    response = client.post(f"/api/imaging/studies/{study}/measurements", json=wrong_depth)
    assert response.status_code == 422
    assert "del globo" in response.json()["detail"]
    assert len(get_store().ledger) == before


def test_no_measurement_on_a_missing_or_redacted_study(client: TestClient) -> None:
    assert client.post("/api/imaging/studies/7/measurements", json=ONSD_BODY).status_code == 404
    study = _upload(client, "optic-nerve")
    redacted = client.post(
        f"/api/audit/redact/{study}",
        json={"reason": "estudio equivocado", "requested_by": "CMO"},
    )
    assert redacted.status_code == 200, redacted.text
    response = client.post(f"/api/imaging/studies/{study}/measurements", json=ONSD_BODY)
    assert response.status_code == 404


def test_a_measurement_is_remeasured_not_amended(client: TestClient) -> None:
    study = _upload(client, "optic-nerve")
    index = client.post(
        f"/api/imaging/studies/{study}/measurements", json=ONSD_BODY
    ).json()["observation_index"]
    response = client.post(
        f"/api/audit/amend/{index}",
        json={
            "reason": "retoque del valor",
            "correction": {
                "key": "onsd-right", "value": 4.0, "subject": "crew-01",
                "source": "manual", "effective": "2026-11-14T07:30:00Z",
            },
        },
    )
    assert response.status_code == 409, response.text
    assert "se vuelve a medir" in response.json()["detail"]
    [reading] = get_store().query("crew-01", key="onsd-right")
    assert reading.value == pytest.approx(5.0)


def test_protocols_expose_their_measures_and_method(client: TestClient) -> None:
    body = client.get("/api/imaging/protocols").json()
    by_key = {p["key"]: p for p in body["protocols"]}
    assert [m["name"] for m in by_key["optic-nerve"]["measures"]] == ["onsd"]
    assert by_key["lung"]["measures"] == []  # se adquiere y se ve; aún no se mide
    assert body["method"]["bladder_coefficient"]["evidence"] == "established"
