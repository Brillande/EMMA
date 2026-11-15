"""Descarga el modelo de la búsqueda semántica (Polaris `kb_embed.py`) en `app/data/kb-model/`.

Por qué existe: decisión del usuario (2026-10-04) de activar la capa vectorial del buscador de la
documentación. Polaris usa `intfloat/multilingual-e5-small` en ONNX int8, en CPU y sin red al
consultar; la descarga es un paso único de instalación. Este script lo hace una vez y comprueba
lo que baja:

  * El repositorio en el commit fijado (`REVISION`), no `main`: lo que se comprobó es lo que viaja.
  * El SHA-256 de cada fichero contra el que declara Hugging Face para ese commit (sus `oid` de
    LFS). Si no coincide, se borra y falla.
  * Licencia MIT (la del modelo, en su ficha): viaja en el instalador con su aviso en `NOTICE`.

Es público: no hace falta cuenta ni token.

Uso:
    .venv/Scripts/python.exe scripts/install_kb_embed.py
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
TARGET = BACKEND / "app" / "data" / "kb-model"
REPO = "intfloat/multilingual-e5-small"
REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
# Nombre local (el que espera `kb_embed`) → (ruta en el repositorio, SHA-256 declarado, bytes).
FILES = {
    "model_qint8_avx512_vnni.onnx": (
        "onnx/model_qint8_avx512_vnni.onnx",
        "dd476dd0c2514e9b9be83aeb3853fac0763e0bdf4a71645407587d77c48a2d88", 118346824,
    ),
    "tokenizer.json": (
        "onnx/tokenizer.json",
        "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39", 17082730,
    ),
}


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    for name, (path, expected, size) in FILES.items():
        url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{path}"
        print("descargando", url)
        with urllib.request.urlopen(url, timeout=300) as response:  # noqa: S310 — URL fija
            data = response.read()
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected or len(data) != size:
            raise SystemExit(f"{name}: SHA-256 {digest} ({len(data)} B) no es el declarado")
        (TARGET / name).write_bytes(data)
    (TARGET / "MODELO.json").write_text(json.dumps({
        "repo": REPO, "revision": REVISION, "licencia": "MIT",
        "ficheros": {name: sha for name, (_p, sha, _s) in FILES.items()},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(path.stat().st_size for path in TARGET.iterdir())
    print(f"modelo de la búsqueda semántica listo: {total / 1e6:.0f} MB en {TARGET}")


if __name__ == "__main__":
    main()
