"""Extrae las ecografías reales de ejemplo que viajan con EMMA, desde sus datasets abiertos.

    .venv/Scripts/python.exe scripts/extract_ultrasound_samples.py

Fuentes (descargadas a `data/ultrasound-sources/`, fuera del repositorio):
  * Pulmón: Katumba A. et al., Data in Brief 62:112034 (2025). Mendeley Data,
    doi:10.17632/hb3p34ytvx.2, CC BY 4.0 (licencia leída en el registro de datos).
  * Hígado: Byra M. et al., Int J CARS (2018). Zenodo, doi:10.5281/zenodo.1009146, CC BY 4.0.

CC BY permite redistribuir con atribución: por eso unas pocas imágenes van dentro del paquete
—la demo funciona sin red— con un manifiesto que dice de dónde sale cada una. La selección es
fija y reproducible: siempre las mismas, por nombre o por índice, no "las que salgan bonitas".
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import scipy.io as sio
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
SOURCES = REPO / "data" / "ultrasound-sources"
OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "ultrasound_samples"

LUNG = {
    "name": "A Dataset of Lung Ultrasound Images for Automated AI-based "
            "Lung Disease Classification",
    "citation": "Katumba A. et al. Data in Brief 62:112034 (2025). "
                "Datos: Mendeley Data, doi:10.17632/hb3p34ytvx.2",
    "doi": "10.17632/hb3p34ytvx.2",
    "license": "CC BY 4.0",
    "url": "https://data.mendeley.com/datasets/hb3p34ytvx/2",
}
LIVER = {
    "name": "Dataset of B-mode fatty liver ultrasound images",
    "citation": "Byra M. et al. Int J Comput Assist Radiol Surg (2018), "
                "doi:10.1007/s11548-018-1843-2. Datos: Zenodo, doi:10.5281/zenodo.1009146",
    "doi": "10.5281/zenodo.1009146",
    "license": "CC BY 4.0",
    "url": "https://doi.org/10.5281/zenodo.1009146",
}
# Claves neutras a propósito: la clave viaja en la URL y en la interfaz, y un nombre como
# "higado-graso" sesgaría a quien anota los signos. La etiqueta del dataset queda en el manifiesto
# como referencia para contrastar después, fuera de la lectura.
#
# Imágenes elegidas del conjunto de prueba del dataset de pulmón, por nombre exacto.
LUNG_PICKS = {
    "lung-1": "dataset/test/healthy/image_13138945535090-10_23_52.png",
    "lung-2": "dataset/test/other/LEFT_ANT_LOWER_LONG-13_1_46.jpeg",
}
# Revisadas a ojo, una a una: ninguna lleva datos identificativos. Sí llevan texto o marcas
# quemadas en los píxeles —calibres de una medida ajena en lung-2; escala, hora y FC en las de
# hígado— y eso se declara en el DICOM (BurnedInAnnotation) en vez de callarlo.
BURNED_IN = {"lung-1": False, "lung-2": True, "liver-1": True, "liver-2": True}


def gray(image: Image.Image) -> Image.Image:
    return image.convert("L")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.iterdir():
        stale.unlink()
    samples = []

    with zipfile.ZipFile(SOURCES / "lung_katumba_2025.zip") as archive:
        for key, name in LUNG_PICKS.items():
            file = f"{key}.png"
            gray(Image.open(io.BytesIO(archive.read(name)))).save(OUT / file, optimize=True)
            samples.append({
                "key": key, "protocol": "lung", "files": [file], "original": name,
                "dataset_label": name.split("/")[2], "dataset": LUNG,
                "burned_in": BURNED_IN[key],
            })

    data = sio.loadmat(SOURCES / "liver_byra_2018.mat")["data"][0]
    # Primer paciente de cada clase del dataset: 0 = sin esteatosis, 1 = con esteatosis.
    for number, cls in ((1, 0), (2, 1)):
        patient = next(p for p in data if int(p["class"].ravel()[0]) == cls)
        frames: np.ndarray = patient["images"]
        key = f"liver-{number}"
        files = []
        for index, frame in enumerate(frames):
            file = f"{key}-{index:02d}.png"
            Image.fromarray(frame.astype(np.uint8), mode="L").save(OUT / file, optimize=True)
            files.append(file)
        samples.append({
            "key": key, "protocol": "liver", "files": files,
            "original": f"paciente id {int(patient['id'].ravel()[0])}",
            "dataset_label": "sin esteatosis" if cls == 0 else "con esteatosis",
            "dataset": LIVER, "burned_in": BURNED_IN[key],
        })

    for sample in samples:
        sample["sha256"] = {
            file: hashlib.sha256((OUT / file).read_bytes()).hexdigest() for file in sample["files"]
        }
    (OUT / "manifest.json").write_text(
        json.dumps({"samples": samples}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    size = sum(f.stat().st_size for f in OUT.iterdir())
    print(f"{len(samples)} ejemplos, {size / 1e6:.1f} MB en {OUT}")


if __name__ == "__main__":
    main()
