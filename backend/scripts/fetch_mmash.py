"""Descarga el dataset MMASH para la validacion externa.

    .venv/Scripts/python.exe scripts/fetch_mmash.py

MMASH es Open Access bajo Open Data Commons Open Database License (ODbL) v1.0.
El fichero (~25 MB) no se versiona: ver `.gitignore`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

from app.validation.mmash import DATASET_LICENCE, DATASET_URL

DESTINATION = Path(__file__).resolve().parents[2] / "data" / "mmash" / "MMASH.zip"


def main() -> int:
    if DESTINATION.exists():
        size = DESTINATION.stat().st_size / 1e6
        print(f"ya descargado: {DESTINATION} ({size:.1f} MB)")
        return 0

    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    print(f"descargando {DATASET_URL}")
    print(f"licencia: {DATASET_LICENCE}")

    total = 0
    try:
        with httpx.stream("GET", DATASET_URL, timeout=600, follow_redirects=True) as response:
            response.raise_for_status()
            with DESTINATION.open("wb") as handle:
                for chunk in response.iter_bytes(1 << 20):
                    handle.write(chunk)
                    total += len(chunk)
                    print(f"\r  {total / 1e6:6.1f} MB", end="", flush=True)
    except httpx.HTTPError as exc:
        print(f"\nfallo la descarga: {exc}")
        DESTINATION.unlink(missing_ok=True)
        return 1

    print(f"\nlisto: {DESTINATION}")
    print("ejecutar la validacion:  pytest -m external")
    return 0


if __name__ == "__main__":
    sys.exit(main())
