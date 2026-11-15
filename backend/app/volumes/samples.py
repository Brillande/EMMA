"""TAC reales de ejemplo, ya segmentados, que viajan con EMMA para que el visor 3D se vea sin red.

Por qué existen: segmentar necesita TotalSegmentator, que no va en el instalador. Para que el visor
funcione en cualquier equipo, unos pocos TAC del dataset abierto de TotalSegmentator (Wasserthal
et al., Radiol AI 2023; Zenodo doi:10.5281/zenodo.10047292, **CC BY 4.0**) viajan con su
segmentación ya hecha por el mismo TotalSegmentator, recortados a la región y a 2 mm.

Lo que no son: TAC de un tripulante. Entran firmados como simulados (`simulator:dataset`), y su
segmentación sigue siendo automática y sin validar. Generados con `scripts/build_volume_samples.py`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "volume_samples"
SAMPLE_SOURCE = "simulator:dataset"


class SampleFileChanged(RuntimeError):
    """Un fichero del paquete ya no es el que se generó: no se sirve."""


@dataclass(frozen=True)
class Sample:
    key: str
    display: str
    preset: str
    modality: str
    dataset: dict[str, str]

    def as_public(self) -> dict[str, Any]:
        return {"key": self.key, "nombre": self.display, "preset": self.preset,
                "modalidad": self.modality, "dataset": self.dataset}


def _manifest() -> list[dict[str, Any]]:
    path = SAMPLES_DIR / "manifest.json"
    if not path.is_file():
        return []
    samples: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))["samples"]
    return samples


def catalog() -> list[Sample]:
    return [
        Sample(entry["key"], entry["nombre"], entry["preset"], entry["modalidad"],
               entry["dataset"])
        for entry in _manifest()
    ]


def load_sample(key: str) -> tuple[Sample, bytes, bytes]:
    """(muestra, TAC recortado, zip del visor), tras comprobar sus huellas."""
    entries = {entry["key"]: entry for entry in _manifest()}
    if key not in entries:
        raise KeyError(f"no hay ejemplo {key!r}")
    entry = entries[key]
    blobs = []
    for name in ("ct.nii.gz", "visor.zip"):
        raw = (SAMPLES_DIR / key / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"][name]:
            raise SampleFileChanged(f"{key}/{name} no coincide con su huella en el manifiesto")
        blobs.append(raw)
    [sample] = [s for s in catalog() if s.key == key]
    return sample, blobs[0], blobs[1]
