"""Instala la transcripción de audios (Polaris `transcribe_audios.py`) en `backend/.venv-voice`.

Por qué existe: decisión del usuario (2026-10-01) de transcribir audios con Whisper local. Como
TotalSegmentator y la capa NER, es un programa externo opcional: un entorno aparte, no viaja en
el instalador y la aplicación nunca descarga nada con un audio esperando. Este script hace la
única descarga, una vez:

  * Entorno `backend/.venv-voice` con `torch` (CPU), `openai-whisper` y `soundfile` fijados.
  * El modelo `base` de Whisper en `backend/.venv-voice/cache/whisper` (no en la carpeta
    personal). Whisper comprueba él mismo el SHA-256 que lleva su URL de descarga; aquí se vuelve
    a calcular y se guarda en la marca.

`app/voice.py` solo usa la transcripción si existe la marca `voice-ok.json`.

Uso:
    .venv/Scripts/python.exe scripts/install_voice.py
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
VENV = BACKEND / ".venv-voice"
CACHE = VENV / "cache"
MARKER = VENV / "voice-ok.json"
MODEL = "base"
# Fijadas el 2026-10-01: las últimas estables para Python 3.12 en Windows.
TORCH = "torch==2.14.1+cpu"
TORCH_INDEX = "https://download.pytorch.org/whl/cpu"
WHISPER = "openai-whisper==20250625"
SOUNDFILE = "soundfile==0.14.0"


def python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(*args: str, env: dict[str, str] | None = None) -> None:
    print("$", " ".join(args))
    subprocess.run(args, check=True, env=env)


def main() -> None:
    if not python().is_file():
        run(sys.executable, "-m", "venv", str(VENV))
    run(str(python()), "-m", "pip", "install", "--upgrade", "pip")
    run(str(python()), "-m", "pip", "install", TORCH, "--index-url", TORCH_INDEX)
    run(str(python()), "-m", "pip", "install", WHISPER, SOUNDFILE)

    # `whisper.load_model` guarda el modelo en $XDG_CACHE_HOME/whisper y comprueba su SHA-256.
    env = {**os.environ, "XDG_CACHE_HOME": str(CACHE)}
    run(str(python()), "-c", f"import whisper; whisper.load_model({MODEL!r})", env=env)
    weights = CACHE / "whisper" / f"{MODEL}.pt"
    digest = hashlib.sha256(weights.read_bytes()).hexdigest()
    MARKER.write_text(json.dumps({"model": MODEL, "sha256": digest, "whisper": WHISPER}),
                      encoding="utf-8")
    size = sum(p.stat().st_size for p in VENV.rglob("*") if p.is_file())
    print(f"transcripción lista: whisper {MODEL} ({digest[:12]}…); {size / 1e9:.2f} GB en {VENV}")


if __name__ == "__main__":
    main()
