"""Validacion externa del motor de medida ecografica contra HC18.

Por que HC18 y que demuestra: no hay ecografias abiertas de nervio optico, yugular ni vejiga
con licencia que permita usarlas (`compliance/imaging-data-provenance.md`). HC18 si es abierto
y trae, para cada imagen, el tamano de pixel en milimetros y una medida de referencia —el
perimetro cefalico fetal— calculada por sus autores. Eso permite comprobar lo que el motor de
EMMA hace de verdad: **convertir puntos en pixeles a milimetros con la calibracion declarada**
y medir sobre ellos.

Lo que NO demuestra: nada sobre anatomia de vuelo, sobre la precision de un operador marcando
calibres, ni sobre ningun umbral clinico. Los puntos salen de la anotacion experta del dataset,
no de una mano. Es la misma regla que MMASH: valida el motor, no la fisiologia espacial.
"""

from __future__ import annotations

import csv
import io
import math
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from statistics import median

import numpy as np
from PIL import Image

from app.imaging.dicom import CalibratedRegion
from app.imaging.measure import Point, distance_mm

RECORD_URL = "https://zenodo.org/api/records/1327317"
DATASET_DOI = "10.5281/zenodo.1327317"
DATASET_LICENCE = "CC BY 4.0"
DATASET_DIR = Path(__file__).resolve().parents[3] / "data" / "hc18"

# Huellas MD5 publicadas por Zenodo para cada fichero.
FILES = {
    "training_set_pixel_size_and_HC.csv": "c0761518fece2bd2d2ad4218f2cd9777",
    "training_set.zip": "00eb8198b9a505b2b3a6dfc740382497",
}


@dataclass(frozen=True)
class Hc18Case:
    name: str
    pixel_mm: float
    reference_hc_mm: float
    # Coordenadas (x, y) de los pixeles del contorno anotado por el experto.
    outline: np.ndarray


@dataclass(frozen=True)
class Ellipse:
    cx: float
    cy: float
    semi_major: float
    semi_minor: float
    angle: float  # radianes, del semieje mayor respecto al eje x


def load_cases(directory: Path = DATASET_DIR) -> Iterator[Hc18Case]:
    """Casos del conjunto de entrenamiento: tamano de pixel, perimetro de referencia y contorno."""
    table = (directory / "training_set_pixel_size_and_HC.csv").read_text(encoding="utf-8")
    with zipfile.ZipFile(directory / "training_set.zip") as archive:
        for row in csv.DictReader(io.StringIO(table)):
            name = row["filename"]
            annotation = f"training_set/{name.replace('.png', '_Annotation.png')}"
            pixels = np.asarray(Image.open(io.BytesIO(archive.read(annotation))).convert("L"))
            ys, xs = np.nonzero(pixels > 127)
            yield Hc18Case(
                name=name,
                pixel_mm=float(row["pixel size(mm)"]),
                reference_hc_mm=float(row["head circumference (mm)"]),
                outline=np.column_stack([xs, ys]).astype(float),
            )


def fit_ellipse(points: np.ndarray) -> Ellipse:
    """Ajuste directo por minimos cuadrados que solo admite elipses (Fitzgibbon et al., 1999).

    Las coordenadas se centran y escalan antes de ajustar: con pixeles de cientos de unidades
    la matriz de diseno queda mal condicionada.
    """
    mean = points.mean(axis=0)
    scale = float(points.std())
    x, y = ((points - mean) / scale).T
    design = np.column_stack([x * x, x * y, y * y, x, y, np.ones_like(x)])
    scatter = design.T @ design
    s1, s2, s3 = scatter[:3, :3], scatter[:3, 3:], scatter[3:, 3:]
    reduction = -np.linalg.solve(s3, s2.T)
    constraint_inv = np.array([[0.0, 0.0, 0.5], [0.0, -1.0, 0.0], [0.5, 0.0, 0.0]])
    values, vectors = np.linalg.eig(constraint_inv @ (s1 + s2 @ reduction))
    vectors = np.real(vectors)
    condition = 4 * vectors[0] * vectors[2] - vectors[1] ** 2
    quadratic = vectors[:, int(np.argmax(condition > 0))]
    a, b, c = quadratic
    d, e, f = reduction @ quadratic

    # Centro y semiejes de la conica, deshaciendo el escalado.
    denominator = b * b - 4 * a * c
    cx = (2 * c * d - b * e) / denominator
    cy = (2 * a * e - b * d) / denominator
    constant = a * cx * cx + b * cx * cy + c * cy * cy + d * cx + e * cy + f
    eigen, axes = np.linalg.eigh(np.array([[a, b / 2], [b / 2, c]]))
    radii = np.sqrt(-constant / eigen)
    major = int(np.argmax(radii))
    direction = axes[:, major]
    return Ellipse(
        cx=float(cx * scale + mean[0]),
        cy=float(cy * scale + mean[1]),
        semi_major=float(radii[major] * scale),
        semi_minor=float(radii[1 - major] * scale),
        angle=float(math.atan2(direction[1], direction[0])),
    )


def caliper_pairs(ellipse: Ellipse) -> tuple[tuple[Point, Point], tuple[Point, Point]]:
    """Los dos diametros como los marcaria un operador: extremos de cada eje."""
    cos, sin = math.cos(ellipse.angle), math.sin(ellipse.angle)

    def along(radius: float, dx: float, dy: float) -> tuple[Point, Point]:
        return (
            Point(ellipse.cx - radius * dx, ellipse.cy - radius * dy),
            Point(ellipse.cx + radius * dx, ellipse.cy + radius * dy),
        )

    return along(ellipse.semi_major, cos, sin), along(ellipse.semi_minor, -sin, cos)


def circumference_mm(case: Hc18Case, scale_error: float = 0.0) -> float:
    """Perimetro a partir de los dos diametros medidos con el motor de EMMA (Ramanujan).

    `scale_error` falsea la calibracion a proposito: es el control negativo que demuestra
    que la validacion puede fallar.
    """
    pixel = case.pixel_mm * (1 + scale_error)
    region = CalibratedRegion(0, 0, 10_000, 10_000, pixel, pixel)
    major, minor = caliper_pairs(fit_ellipse(case.outline))
    a = distance_mm(*major, region) / 2
    b = distance_mm(*minor, region) / 2
    return math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))


@dataclass(frozen=True)
class Hc18Report:
    cases: int
    median_abs_error_pct: float
    p95_abs_error_pct: float
    max_abs_error_pct: float
    worst: str

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "cases": self.cases,
            "median_abs_error_pct": self.median_abs_error_pct,
            "p95_abs_error_pct": self.p95_abs_error_pct,
            "max_abs_error_pct": self.max_abs_error_pct,
            "worst": self.worst,
        }


def evaluate(cases: Iterator[Hc18Case], scale_error: float = 0.0) -> Hc18Report:
    errors: list[tuple[float, str]] = []
    for case in cases:
        measured = circumference_mm(case, scale_error)
        error = abs(measured - case.reference_hc_mm) / case.reference_hc_mm * 100
        errors.append((error, case.name))
    ordered = sorted(value for value, _ in errors)
    worst_value, worst_name = max(errors)
    return Hc18Report(
        cases=len(errors),
        median_abs_error_pct=round(median(ordered), 3),
        p95_abs_error_pct=round(ordered[int(0.95 * (len(ordered) - 1))], 3),
        max_abs_error_pct=round(worst_value, 3),
        worst=worst_name,
    )
