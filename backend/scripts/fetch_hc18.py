"""Descarga HC18 para la validacion externa del motor de medida ecografica.

    .venv/Scripts/python.exe scripts/fetch_hc18.py

HC18 (Zenodo, doi:10.5281/zenodo.1327317) es CC BY 4.0. Citar: van den Heuvel et al.,
PLoS ONE 13(8): e0200412, 2018. Los ficheros (~133 MB) no se versionan: ver `.gitignore` y
`compliance/imaging-data-provenance.md`. Se comprueba la huella MD5 que publica Zenodo: un
fichero a medio bajar o cambiado en origen no debe validar nada.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import httpx

from app.validation.hc18 import DATASET_DIR, FILES, RECORD_URL


def fetch(name: str, md5: str) -> bool:
    destination = DATASET_DIR / name
    if destination.exists() and _md5(destination) == md5:
        print(f"ya descargado: {destination}")
        return True
    url = f"{RECORD_URL}/files/{name}/content"
    print(f"descargando {url}")
    digest = hashlib.md5()  # noqa: S324 — es la huella que publica Zenodo, no seguridad
    total = 0
    try:
        with httpx.stream("GET", url, timeout=600, follow_redirects=True) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_bytes(1 << 20):
                    handle.write(chunk)
                    digest.update(chunk)
                    total += len(chunk)
                    print(f"\r  {total / 1e6:6.1f} MB", end="", flush=True)
    except httpx.HTTPError as exc:
        print(f"\nfallo la descarga: {exc}")
        destination.unlink(missing_ok=True)
        return False
    print()
    if digest.hexdigest() != md5:
        print(f"la huella no coincide ({digest.hexdigest()} != {md5}): se descarta")
        destination.unlink(missing_ok=True)
        return False
    return True


def _md5(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    print("licencia: CC BY 4.0 (van den Heuvel et al., PLoS ONE 2018)")
    ok = all(fetch(name, md5) for name, md5 in FILES.items())
    if ok:
        print("ejecutar la validacion:  pytest -m external -k hc18")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
