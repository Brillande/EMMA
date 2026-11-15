"""Fotogramas como PNG: se ve lo que está firmado, y tal como lo adquirió el ecógrafo."""

from __future__ import annotations

import datetime as dt
import io
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pydicom
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.encaps import encapsulate
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.api.routes import get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.core.storage import ImagingBlobRow
from app.imaging.render import UnrenderableError, frame_png
from app.main import app
from tests.test_imaging import ultrasound_dicom

MULTIFRAME = "1.2.840.10008.5.1.4.1.1.3.1"
JPEG_LS_LOSSLESS = "1.2.840.10008.1.2.4.80"


def dicom(
    pixels: np.ndarray,
    photometric: str = "MONOCHROME2",
    syntax: str = ExplicitVRLittleEndian,
) -> bytes:
    """Un DICOM de ecografía con los píxeles dados: (fotogramas, filas, columnas[, 3])."""
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = MULTIFRAME
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = syntax
    ds = Dataset()
    ds.file_meta = meta
    ds.SOPClassUID = MULTIFRAME
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.Modality = "US"
    frames, rows, columns = pixels.shape[:3]
    ds.NumberOfFrames, ds.Rows, ds.Columns = frames, rows, columns
    ds.SamplesPerPixel = 3 if pixels.ndim == 4 else 1
    if pixels.ndim == 4:
        ds.PlanarConfiguration = 0
    ds.PhotometricInterpretation = photometric
    bits = pixels.dtype.itemsize * 8
    ds.BitsAllocated, ds.BitsStored, ds.HighBit = bits, bits, bits - 1
    ds.PixelRepresentation = 0
    if syntax == ExplicitVRLittleEndian:
        ds.PixelData = pixels.tobytes()
    else:
        ds.PixelData = encapsulate([b"no es jpeg-ls"] * frames)
    buffer = io.BytesIO()
    pydicom.dcmwrite(buffer, ds, enforce_file_format=True)
    return buffer.getvalue()


def decoded(png: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png)))


def test_each_frame_of_a_cine_is_served_as_it_was_acquired() -> None:
    cine = np.stack([np.full((4, 5), value, dtype=np.uint8) for value in (10, 120, 250)])
    data = dicom(cine)
    for index, value in enumerate((10, 120, 250)):
        image = decoded(frame_png(data, index))
        assert image.shape == (4, 5)
        # Sin estirar el contraste: el gris 10 sigue siendo 10, no negro ni blanco.
        assert (image == value).all()


def test_monochrome1_is_inverted_to_be_seen_as_it_is() -> None:
    image = decoded(frame_png(dicom(np.full((1, 2, 2), 30, np.uint8), "MONOCHROME1"), 0))
    assert (image == 225).all()


def test_sixteen_bit_pixels_keep_a_fixed_scale() -> None:
    image = decoded(frame_png(dicom(np.full((1, 2, 2), 0x8000, np.uint16)), 0))
    assert (image == 128).all()


def test_colour_frames_stay_in_colour() -> None:
    rgb = np.zeros((1, 2, 2, 3), np.uint8)
    rgb[..., 0] = 200
    image = decoded(frame_png(dicom(rgb, "RGB"), 0))
    assert image.shape == (2, 2, 3) and (image[..., 0] == 200).all()


def test_a_frame_that_does_not_exist_is_an_index_error() -> None:
    with pytest.raises(IndexError):
        frame_png(dicom(np.zeros((2, 2, 2), np.uint8)), 2)


def test_an_unsupported_compression_is_said_not_hidden() -> None:
    with pytest.raises(UnrenderableError, match="compresión"):
        frame_png(dicom(np.zeros((1, 2, 2), np.uint8), syntax=JPEG_LS_LOSSLESS), 0)


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


def _upload(client: TestClient) -> int:
    response = client.post(
        "/api/imaging/studies", params={"protocol": "optic-nerve"},
        content=ultrasound_dicom(), headers={"content-type": "application/dicom"},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["ledger_index"])


def test_the_frame_route_serves_a_png(client: TestClient) -> None:
    study = _upload(client)
    response = client.get(f"/api/imaging/studies/{study}/frames/0")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert decoded(response.content).shape == (16, 16)
    assert client.get(f"/api/imaging/studies/{study}/frames/1").status_code == 404
    assert client.get("/api/imaging/studies/99/frames/0").status_code == 404


def test_a_tampered_image_is_not_shown(client: TestClient) -> None:
    study = _upload(client)
    with Session(get_store().engine) as session:
        session.execute(update(ImagingBlobRow).values(data=b"otra imagen"))
        session.commit()
    assert client.get(f"/api/imaging/studies/{study}/frames/0").status_code == 409


def test_earth_only_lists_what_had_been_recorded_by_its_cutoff(client: TestClient) -> None:
    _upload(client)
    past = (dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)).isoformat()
    future = (dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)).isoformat()
    assert client.get("/api/imaging/studies", params={"until": past}).json() == []
    assert len(client.get("/api/imaging/studies", params={"until": future}).json()) == 1
    naive = client.get("/api/imaging/studies", params={"until": "2026-11-14T08:00:00"})
    assert naive.status_code == 422


def test_protocols_carry_instructions_and_say_they_do_not_alert_yet(client: TestClient) -> None:
    body = client.get("/api/imaging/protocols").json()
    [onsd] = next(p for p in body["protocols"] if p["key"] == "optic-nerve")["measures"]
    assert set(onsd["instructions"]) == set(onsd["annotations"])
    assert body["alerting"]["active"] is False
    assert "no significa que la medida sea normal" in body["alerting"]["note"]
