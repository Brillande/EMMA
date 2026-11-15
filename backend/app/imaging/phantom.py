"""Fantomas ecográficos sintéticos con la medida real conocida.

Por qué existen: para nervio óptico, yugular y vejiga no hay ecografías abiertas que se puedan
usar (`compliance/imaging-data-provenance.md`), y una demo necesita algo que medir. Un fantoma
es una imagen dibujada con geometría exacta: quien mide sabe cuánto tiene que salir, y puede
comprobar a mano lo que HC18 comprueba en automático.

Lo que no son: pacientes, ni imágenes realistas. No hay speckle físico, sombras ni artefactos;
el contraste es el de un dibujo. Entran firmados como simulados —fuente `simulator:phantom`—
y así los declara la interfaz y el modo de misión. No sirven para validar nada clínico.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import UID, ExplicitVRLittleEndian, generate_uid

from app.core.display import number
from app.imaging.measure import METHOD

PHANTOM_SOURCE = "simulator:phantom"
MULTIFRAME = UID("1.2.840.10008.5.1.4.1.1.3.1")


@dataclass(frozen=True)
class Phantom:
    data: bytes
    # La medida que tiene que salir, por medida del registro: {"onsd": 5.5}
    truth: dict[str, float]
    note: str


# Valores por defecto. Solo el de la yugular sale de la literatura; los demás son geometría
# cómoda de medir, no valores clínicos de referencia.
DEFAULT_ONSD_MM = 5.5
# Media en vuelo de 11 tripulantes de la ISS (Marshall-Goebel et al., JAMA Netw Open 2019).
DEFAULT_IJV_AREA_MM2 = 70.3
DEFAULT_BLADDER_MM = (60.0, 80.0, 90.0)  # alto, ancho, largo


def build(protocol: str, seed: int = 20261114) -> Phantom:
    """El fantoma de un protocolo con medida. Determinista: la misma semilla, la misma imagen."""
    rng = np.random.default_rng(seed)
    if protocol == "optic-nerve":
        return _optic_nerve(rng)
    if protocol == "jugular-vein":
        return _jugular(rng)
    if protocol == "bladder":
        return _bladder(rng)
    raise KeyError(f"no hay fantoma para '{protocol}': solo para protocolos con medida")


def _tissue(rng: np.random.Generator, rows: int, columns: int) -> np.ndarray:
    return 90 + rng.normal(0, 12, (rows, columns))


def _optic_nerve(rng: np.random.Generator) -> Phantom:
    rows, columns, mm_per_px = 300, 400, 0.05
    half_sheath = round(DEFAULT_ONSD_MM / mm_per_px / 2)  # 55 px: 5,5 mm exactos
    yy, xx = np.mgrid[0:rows, 0:columns]
    frames = []
    for shift in range(3):  # un píxel por fotograma, para que el cine se note
        image = _tissue(rng, rows, columns)
        globe = (xx - 200 - shift) ** 2 + (yy + 40) ** 2 < 150**2  # borde posterior en y = 110
        sheath = (abs(xx - 200 - shift) < half_sheath) & (yy > 110) & ~globe
        nerve = (abs(xx - 200 - shift) < half_sheath * 0.55) & (yy > 110) & ~globe
        image[globe], image[sheath], image[nerve] = 15, 170, 45
        frames.append(image)
    depth = METHOD["onsd_depth_mm"].value
    return Phantom(
        dicom_from_frames(frames, mm_per_px),
        {"onsd": 2 * half_sheath * mm_per_px},
        f"Vaina de {number(DEFAULT_ONSD_MM, 1)} mm; "
        f"medir {number(depth, 0)} mm por detrás del globo.",
    )


def _jugular(rng: np.random.Generator) -> Phantom:
    rows, columns, mm_per_px = 300, 400, 0.05
    aspect = 1.4  # una yugular en corte transversal suele ser algo ovalada
    semi_minor = math.sqrt(DEFAULT_IJV_AREA_MM2 / (math.pi * aspect))
    a_px, b_px = semi_minor * aspect / mm_per_px, semi_minor / mm_per_px
    yy, xx = np.mgrid[0:rows, 0:columns]
    image = _tissue(rng, rows, columns)
    wall = ((xx - 200) / (a_px + 6)) ** 2 + ((yy - 150) / (b_px + 6)) ** 2 < 1
    lumen = ((xx - 200) / a_px) ** 2 + ((yy - 150) / b_px) ** 2 < 1
    image[wall], image[lumen] = 160, 20
    return Phantom(
        dicom_from_frames([image], mm_per_px),
        {"ijv-csa": round(math.pi * a_px * b_px * mm_per_px**2, 1)},
        "Luz de la vena elíptica; su área es la media en vuelo de Marshall-Goebel (2019).",
    )


def _bladder(rng: np.random.Generator) -> Phantom:
    rows, columns, mm_per_px = 360, 480, 0.25
    height, width, length = DEFAULT_BLADDER_MM
    yy, xx = np.mgrid[0:rows, 0:columns]
    transverse = _tissue(rng, rows, columns)
    transverse[
        ((xx - 240) / (width / 2 / mm_per_px)) ** 2 + ((yy - 180) / (height / 2 / mm_per_px)) ** 2
        < 1
    ] = 10
    sagittal = _tissue(rng, rows, columns)
    sagittal[
        ((xx - 240) / (length / 2 / mm_per_px)) ** 2 + ((yy - 180) / (height / 2 / mm_per_px)) ** 2
        < 1
    ] = 10
    volume = height * width * length * METHOD["bladder_coefficient"].value / 1000
    return Phantom(
        dicom_from_frames([transverse, sagittal], mm_per_px),
        {"bladder-volume": round(volume, 1)},
        f"Fotograma 1 transversal (alto {number(height, 0)} mm, ancho {number(width, 0)} mm); "
        f"fotograma 2 sagital (largo {number(length, 0)} mm).",
    )


def dicom_from_frames(
    frames: list[np.ndarray], mm_per_px: float | None, burned_in: bool = False
) -> bytes:
    """Un DICOM de ecografía multifotograma en escala de grises.

    Sin `mm_per_px` no lleva región calibrada: se puede ver, no medir en mm.
    """
    pixels = np.stack([np.clip(frame, 0, 255).astype(np.uint8) for frame in frames])
    count, rows, columns = pixels.shape
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = MULTIFRAME
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = Dataset()
    ds.file_meta = meta
    ds.SOPClassUID = MULTIFRAME
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID, ds.SeriesInstanceUID = generate_uid(), generate_uid()
    ds.Modality = "US"
    ds.BurnedInAnnotation = "YES" if burned_in else "NO"
    if mm_per_px is not None:
        ds.SequenceOfUltrasoundRegions = Sequence([_region(rows, columns, mm_per_px)])
    ds.NumberOfFrames, ds.Rows, ds.Columns = count, rows, columns
    ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 8, 8, 7, 0
    ds.PixelData = pixels.tobytes()
    buffer = io.BytesIO()
    pydicom.dcmwrite(buffer, ds, enforce_file_format=True)
    return buffer.getvalue()


def _region(rows: int, columns: int, mm_per_px: float) -> Dataset:
    region = Dataset()
    region.RegionSpatialFormat, region.RegionDataType, region.RegionFlags = 1, 1, 0
    region.RegionLocationMinX0, region.RegionLocationMinY0 = 0, 0
    region.RegionLocationMaxX1, region.RegionLocationMaxY1 = columns - 1, rows - 1
    region.PhysicalUnitsXDirection = region.PhysicalUnitsYDirection = 3  # cm
    region.PhysicalDeltaX = region.PhysicalDeltaY = mm_per_px / 10
    return region
