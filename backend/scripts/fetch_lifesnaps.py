"""Descarga LifeSnaps y lo reduce a lo que usa la validacion de la linea base de familia.

    .venv/Scripts/python.exe scripts/fetch_lifesnaps.py

LifeSnaps (Zenodo, doi:10.5281/zenodo.7229547) es Creative Commons Attribution 4.0 International.
Citar: Yfantidou S et al., Sci Data 2022;9:663. El zip pesa 615 MB y dentro hay 9,7 GB; ni el zip
ni lo normalizado se versionan (ver `.gitignore`) y no entran en el paquete. Se comprueba la huella
MD5 que publica Zenodo: un fichero a medio bajar o cambiado en origen no debe validar nada.

La descarga sale por `core/egress.py` con el proposito `datasets`. Si el archivo ya esta, no se
vuelve a bajar. Normalizar se hace una vez y lee el volcado entero.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

import httpx

from app.core import egress
from app.core.config import Settings
from app.validation.lifesnaps import (
    ARCHIVE_MD5,
    ARCHIVE_NAME,
    DATASET_CITATION,
    DATASET_LICENCE,
    RECORD_URL,
    dataset_dir,
    normalize,
)


def _md5(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 — es la huella que publica Zenodo, no seguridad
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(destination: Path) -> bool:
    url = f"{RECORD_URL}/files/{ARCHIVE_NAME}/content"
    print(f"descargando {url}")
    print(f"licencia: {DATASET_LICENCE}. Citar: {DATASET_CITATION}")
    partial = destination.with_suffix(".part")
    total = 0
    try:
        with egress.client(Settings(), "datasets") as client, client.stream(
            "GET", url, timeout=600
        ) as response:
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_bytes(1 << 20):
                    handle.write(chunk)
                    total += len(chunk)
                    print(f"\r  {total / 1e6:6.1f} MB", end="", flush=True)
    except httpx.HTTPError as exc:
        print(f"\nfallo la descarga: {exc}")
        partial.unlink(missing_ok=True)
        return False
    print()
    partial.replace(destination)
    return True


def main() -> int:
    folder = dataset_dir()
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / ARCHIVE_NAME
    if not archive.exists() and not download(archive):
        return 1
    if _md5(archive) != ARCHIVE_MD5:
        print(f"la huella de {archive} no es la que publica Zenodo: se descarta")
        archive.unlink()
        return 1
    print(f"archivo integro: {archive}")

    target = folder / "normalized"
    partial = folder / "normalized.part"
    shutil.rmtree(partial, ignore_errors=True)
    people = normalize(
        archive, partial,
        progress=lambda count: print(f"\r  {count:,} documentos", end="", flush=True),
    )
    shutil.rmtree(target, ignore_errors=True)
    partial.replace(target)
    print(f"\nlisto: {people} personas en {target}")
    print("ejecutar la medida:  pytest -m external tests/test_lifesnaps_external.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
