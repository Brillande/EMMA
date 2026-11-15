"""Fantomas: la imagen dibujada casa con la medida que declaran, y entran como simulados."""

from __future__ import annotations

import io
import math
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.routes import get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.imaging.dicom import read_ultrasound
from app.imaging.measure import Annotation, Point, measure
from app.imaging.phantom import PHANTOM_SOURCE, build
from app.imaging.render import frame_png
from app.main import app


def ann(*points: tuple[float, float], frame: int = 0) -> Annotation:
    return Annotation(frame, tuple(Point(x, y) for x, y in points))


def pixels(data: bytes, frame: int = 0) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(frame_png(data, frame)))).astype(int)


def test_the_optic_nerve_phantom_measures_what_it_declares() -> None:
    phantom = build("optic-nerve")
    study = read_ultrasound(phantom.data)
    result = measure(
        "onsd", "right",
        {"globe": ann((200, 110)), "sheath": ann((145, 170), (255, 170))},
        study.regions, study.frames,
    )
    assert result.value == pytest.approx(phantom.truth["onsd"]) == pytest.approx(5.5)
    # Y la imagen es la que dice: vaina brillante dentro de esos bordes, tejido fuera.
    image = pixels(phantom.data)
    assert image[170, 146] == 170 and image[170, 254] == 170
    assert image[170, 144] != 170 and image[170, 256] != 170


def test_the_bladder_phantom_measures_what_it_declares() -> None:
    phantom = build("bladder")
    study = read_ultrasound(phantom.data)
    # 0,25 mm/px: alto 60 mm = 240 px, ancho 80 mm = 320 px, largo 90 mm = 360 px.
    result = measure(
        "bladder-volume", None,
        {
            "height": ann((240, 60), (240, 300)),
            "width": ann((80, 180), (400, 180)),
            "length": ann((60, 180), (420, 180), frame=1),
        },
        study.regions, study.frames,
    )
    assert result.value == pytest.approx(phantom.truth["bladder-volume"], abs=0.1)
    transverse, sagittal = pixels(phantom.data, 0), pixels(phantom.data, 1)
    assert transverse[180, 82] == 10 and transverse[180, 78] != 10  # borde del ancho
    assert sagittal[180, 62] == 10 and sagittal[180, 58] != 10  # borde del largo


def test_the_jugular_phantom_measures_what_it_declares() -> None:
    phantom = build("jugular-vein")
    study = read_ultrasound(phantom.data)
    image = pixels(phantom.data)
    lumen = image == 20
    # El área dibujada, contando píxeles, casa con la declarada.
    assert lumen.sum() * 0.05**2 == pytest.approx(phantom.truth["ijv-csa"], rel=0.01)
    # Y contorneada con el motor, también.
    ys, xs = np.nonzero(lumen)
    a, b = (xs.max() - xs.min() + 1) / 2, (ys.max() - ys.min() + 1) / 2
    contour = [
        (200 + a * math.cos(t), 150 + b * math.sin(t))
        for t in np.linspace(0, 2 * math.pi, 48, endpoint=False)
    ]
    result = measure("ijv-csa", "left", {"contour": ann(*contour)}, study.regions, study.frames)
    assert result.value == pytest.approx(phantom.truth["ijv-csa"], rel=0.02)


def test_the_same_seed_draws_the_same_phantom() -> None:
    first, second = build("optic-nerve"), build("optic-nerve")
    assert pixels(first.data).tolist() == pixels(second.data).tolist()


def test_protocols_without_a_measure_have_no_phantom() -> None:
    with pytest.raises(KeyError):
        build("lung")


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


def test_a_phantom_enters_as_simulated_and_so_do_its_measurements(client: TestClient) -> None:
    response = client.post("/api/imaging/phantom", params={"protocol": "optic-nerve"})
    assert response.status_code == 201, response.text
    index = response.json()["ledger_index"]

    [study] = client.get("/api/imaging/studies").json()
    assert study["synthetic"] is True and study["source"] == PHANTOM_SOURCE
    assert study["ground_truth"] == {"onsd": pytest.approx(5.5)}

    measured = client.post(
        f"/api/imaging/studies/{index}/measurements",
        json={
            "measure": "onsd", "laterality": "right", "measured_by": "demo",
            "annotations": {
                "globe": {"points": [[200, 110]]},
                "sheath": {"points": [[145, 170], [255, 170]]},
            },
        },
    )
    assert measured.status_code == 201, measured.text
    [reading] = get_store().query("crew-01", key="onsd-right")
    assert reading.source == PHANTOM_SOURCE
    assert get_store().reading_signers() == {"simulator"}


def test_a_phantom_never_blocks_switching_scenario(client: TestClient) -> None:
    """Lo simulado se puede descartar: al contrario que una ecografía real."""
    client.post("/api/imaging/phantom", params={"protocol": "bladder"})
    response = client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 1, "replace": "true"}
    )
    assert response.status_code == 201, response.text


def test_no_phantom_for_a_protocol_without_measure(client: TestClient) -> None:
    assert client.post("/api/imaging/phantom", params={"protocol": "lung"}).status_code == 422


def test_a_phantom_is_dated_inside_the_simulated_timeline(client: TestClient) -> None:
    """Con la hora real caía antes del inicio de la misión y el MET salía negativo."""
    client.post("/api/imaging/phantom", params={"protocol": "optic-nerve"})
    [first] = client.get("/api/imaging/studies").json()
    assert first["acquired"] == "2026-11-01T00:00:00+00:00"  # sin lecturas: inicio de misión

    client.post("/api/simulate", params={"scenario": "nominal", "days": 2})
    last_reading = get_store().query("crew-01", limit=1)[-1].effective
    client.post("/api/imaging/phantom", params={"protocol": "bladder"})
    second = client.get("/api/imaging/studies").json()[-1]
    assert second["acquired"] == last_reading.isoformat()

