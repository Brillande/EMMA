"""Descarga sujetos sueltos del dataset de TotalSegmentator, sin bajar sus 23,6 GB.

    .venv/Scripts/python.exe scripts/fetch_ct_samples.py s0048 s0249 s0289 ...

Fuente: Wasserthal J. et al., "TotalSegmentator: Robust Segmentation of 104 Anatomic Structures in
CT Images", Radiology: Artificial Intelligence 2023;5(5):e230024. Datos: Zenodo,
doi:10.5281/zenodo.10047292 (v2.0.1), **CC BY 4.0** (licencia leída en el registro de Zenodo).

Por qué por rangos: el dataset es un único zip de 23,6 GB. El índice de un zip está al final, y
cada miembro se puede leer pidiendo solo sus bytes (cabecera HTTP `Range`). Así se baja un TAC
(pocos MB) y sus máscaras de referencia, no el conjunto entero.

Guarda en `data/ct-sources/<sujeto>/` (fuera del repositorio): `ct.nii.gz`, las máscaras de
referencia que pide el visor, la fila de `meta.csv` y un `manifest.json` con la huella SHA-256 de
cada fichero. Es lo único que toca la red; la suite no lo usa.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "https://zenodo.org/api/records/10047292/files/Totalsegmentator_dataset_v201.zip/content"
DOI = "10.5281/zenodo.10047292"
OUT = Path(__file__).resolve().parents[2] / "data" / "ct-sources"
# Máscaras de referencia (hechas por expertos) que se guardan junto al TAC, para medir después la
# segmentación automática contra ellas.
REFERENCE_MASKS = (
    "liver", "portal_vein_and_splenic_vein", "inferior_vena_cava", "gallbladder",
    "aorta", "spleen", "brain", "skull",
)


class RangeFile(io.RawIOBase):
    """Un fichero remoto que se lee por rangos HTTP."""

    def __init__(self, url: str) -> None:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD")) as response:
            self.url = response.url
            self.size = int(response.headers["Content-Length"])
        self.pos = 0

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = self.size - self.pos
        if size == 0 or self.pos >= self.size:
            return b""
        end = min(self.pos + size, self.size) - 1
        request = urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        with urllib.request.urlopen(request) as response:
            data: bytes = response.read()
        self.pos += len(data)
        return data

    def readinto(self, buffer: bytearray) -> int:  # type: ignore[override]
        data = self.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)


def main(subjects: list[str]) -> None:
    archive = zipfile.ZipFile(io.BufferedReader(RangeFile(URL), buffer_size=1 << 20))
    names = set(archive.namelist())
    meta = {
        row["image_id"]: row
        for row in csv.DictReader(
            io.StringIO(archive.read("meta.csv").decode("utf-8-sig")), delimiter=";"
        )
    }
    for subject in subjects:
        target = OUT / subject
        (target / "segmentations").mkdir(parents=True, exist_ok=True)
        wanted = [f"{subject}/ct.nii.gz"] + [
            f"{subject}/segmentations/{mask}.nii.gz" for mask in REFERENCE_MASKS
        ]
        hashes: dict[str, str] = {}
        for member in wanted:
            if member not in names:
                continue
            data = archive.read(member)
            relative = member.split("/", 1)[1]
            (target / relative).write_bytes(data)
            hashes[relative] = hashlib.sha256(data).hexdigest()
        (target / "manifest.json").write_text(
            json.dumps(
                {"subject": subject, "dataset_doi": DOI, "license": "CC BY 4.0",
                 "meta": meta.get(subject, {}), "sha256": hashes},
                ensure_ascii=False, indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        size = sum(p.stat().st_size for p in target.rglob("*") if p.is_file())
        print(f"{subject}: {len(hashes)} ficheros, {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main(sys.argv[1:])
