"""Instala la capa NER de la de-identificación (Polaris `deid_ner.py`) en `backend/.venv-deid`.

Por qué existe: decisión del usuario (2026-10-01) de activar la capa NER, un detector distinto de
los patrones, entrenado con historias clínicas reales en castellano. Polaris la usa desde un
entorno aparte, con el modelo ya en disco y descargas apagadas: nunca baja nada con un informe
esperando. Este script hace la única descarga, una vez, y comprueba lo que baja:

  * Entorno `backend/.venv-deid` con `torch` (CPU) y `transformers` en versiones fijadas.
  * Modelo `BSC-NLP4BIA/bsc-bio-ehr-es-contacto-anon` en la revisión que fija Polaris, en la caché
    `backend/.venv-deid/hf` (no en la carpeta personal).
  * El SHA-256 de los pesos contra `SHA256_PESOS` de `polaris/tools/deid_ner.py`, que Polaris
    declara pero no comprueba. Si no coincide, se borra la caché y falla.

No viaja en el instalador de la aplicación, como TotalSegmentator: es un programa externo opcional.

LÍMITE medido el 2026-10-01: el modelo no es público. Hugging Face responde 401 al pedirlo: hace
falta una cuenta que acepte sus condiciones y un token (`HF_TOKEN`). Sin él, el script instala el
entorno, falla en la descarga y no escribe la marca, así que la capa sigue apagada.

Uso:
    .venv/Scripts/python.exe scripts/install_deid_ner.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
VENV = BACKEND / ".venv-deid"
HF_HOME = VENV / "hf"
MARKER = VENV / "ner-ok.json"
DEID_NER = BACKEND.parent / "polaris" / "tools" / "deid_ner.py"
# Fijadas el 2026-10-01: las últimas estables para Python 3.12 en Windows.
TORCH = "torch==2.14.1+cpu"
TRANSFORMERS = "transformers==5.18.0"
TORCH_INDEX = "https://download.pytorch.org/whl/cpu"


def python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def declared() -> tuple[str, str, str]:
    """Modelo, revisión y huella tal como los fija la copia de Polaris."""
    text = DEID_NER.read_text(encoding="utf-8")

    def value(name: str) -> str:
        found = re.search(rf'^{name} = "([^"]+)"', text, re.M)
        if not found:
            raise SystemExit(f"{DEID_NER.name}: no declara {name}")
        return found.group(1)

    return value("MODELO"), value("REVISION"), value("SHA256_PESOS")


def run(*args: str, env: dict[str, str] | None = None) -> None:
    print("$", " ".join(args))
    subprocess.run(args, check=True, env=env)


def main() -> None:
    model, revision, expected = declared()
    if not python().is_file():
        run(sys.executable, "-m", "venv", str(VENV))
    run(str(python()), "-m", "pip", "install", "--upgrade", "pip")
    run(str(python()), "-m", "pip", "install", TORCH, "--index-url", TORCH_INDEX)
    run(str(python()), "-m", "pip", "install", TRANSFORMERS)

    env = {**os.environ, "HF_HOME": str(HF_HOME), "HF_HUB_DISABLE_TELEMETRY": "1"}
    download = (
        "from huggingface_hub import snapshot_download; "
        f"print(snapshot_download({model!r}, revision={revision!r}))"
    )
    done = subprocess.run(
        [str(python()), "-c", download], check=True, env=env, capture_output=True, text=True
    )
    snapshot = Path(done.stdout.strip().splitlines()[-1])
    weights = [p for p in snapshot.iterdir() if p.suffix in (".safetensors", ".bin")]
    digests = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in weights}
    if expected not in digests.values():
        shutil.rmtree(HF_HOME, ignore_errors=True)
        raise SystemExit(
            f"los pesos no coinciden con SHA256_PESOS ({expected}): {digests}. Caché borrada."
        )
    # La marca que mira el adaptador (`app/reports/deid.py`): sin ella la capa no se activa, porque
    # con el entorno pero sin el modelo cada informe se retendría entero.
    MARKER.write_text(
        json.dumps({"model": model, "revision": revision, "sha256": expected}), encoding="utf-8"
    )
    size = sum(p.stat().st_size for p in VENV.rglob("*") if p.is_file())
    print(f"capa NER lista: {model}@{revision[:7]}, pesos comprobados; "
          f"{size / 1e9:.2f} GB en {VENV}")


if __name__ == "__main__":
    main()
