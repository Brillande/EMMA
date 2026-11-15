"""Ecografías reales de ejemplo, de datasets abiertos, que viajan dentro de EMMA.

Por qué existen: los fantomas (`phantom.py`) sirven para medir, pero no parecen una ecografía.
Pulmón e hígado se leen por signos, no con calibres, y para practicar esa lectura hace falta
speckle, sombras y artefactos de verdad. Estas imágenes son de pacientes reales, publicadas
con licencia CC BY 4.0, que permite redistribuirlas citando. Por eso van en el paquete —la demo
funciona sin red— con un manifiesto que dice de qué dataset sale cada una y su licencia.

Lo que no son: ecografías de esta tripulación. Entran firmadas como simuladas —fuente
`simulator:dataset`— y el modo de misión lo declara igual que con el simulador de constantes.
Tampoco están calibradas: los datasets no publican la escala, y una escala inventada daría
milímetros falsos. Se pueden ver y anotar, no medir.

La etiqueta de clase del dataset ("con esteatosis", "healthy"...) no entra en el estudio. Es
la referencia para contrastar después, y mostrarla antes sesgaría la lectura. Queda en el
manifiesto, junto al nombre del fichero original, que también la delata.

Regenerar con `scripts/extract_ultrasound_samples.py`.
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from app.imaging.phantom import dicom_from_frames

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "ultrasound_samples"
SAMPLE_SOURCE = "simulator:dataset"


class SampleFileChanged(RuntimeError):
    """Una imagen del paquete ya no es la que se revisó: no se sirve."""


@dataclass(frozen=True)
class Sample:
    key: str
    protocol: str
    frames: int
    dataset: dict[str, str]
    burned_in: bool

    def as_public(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "protocol": self.protocol,
            "frames": self.frames,
            "dataset": self.dataset,
            "burned_in_annotation": self.burned_in,
        }


def _manifest(directory: Path) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = json.loads(
        (directory / "manifest.json").read_text(encoding="utf-8")
    )["samples"]
    return samples


def catalog(directory: Path = SAMPLES_DIR) -> list[Sample]:
    return [
        Sample(
            key=entry["key"],
            protocol=entry["protocol"],
            frames=len(entry["files"]),
            dataset=entry["dataset"],
            burned_in=bool(entry["burned_in"]),
        )
        for entry in _manifest(directory)
    ]


def build(key: str, directory: Path = SAMPLES_DIR) -> tuple[Sample, bytes]:
    """El ejemplo como DICOM de ecografía sin calibrar, tras comprobar la huella de cada imagen."""
    entries = {entry["key"]: entry for entry in _manifest(directory)}
    if key not in entries:
        raise KeyError(f"no hay ejemplo '{key}'")
    entry = entries[key]
    frames = []
    for file in entry["files"]:
        raw = (directory / file).read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"][file]:
            raise SampleFileChanged(f"'{file}' no coincide con su huella en el manifiesto")
        frames.append(np.asarray(Image.open(io.BytesIO(raw)).convert("L")))
    [sample] = [s for s in catalog(directory) if s.key == key]
    return sample, dicom_from_frames(frames, mm_per_px=None, burned_in=sample.burned_in)
