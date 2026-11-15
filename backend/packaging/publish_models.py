"""Parte y sube el paquete de modelos a una versión de GitHub, pieza a pieza.

Por qué existe: el paquete entero (`models_pack.py`) pesa unos 33 GB y en el equipo que lo crea no
cabe dos veces. Aquí cada componente se corta en trozos (`models_parts.py`), cada trozo se sube con
`gh` y se borra antes de cortar el siguiente; `hecho.json` recuerda lo subido para reanudar. Primero
lo pequeño (Tesseract, voz), para que lo útil esté arriba aunque algo falle.

Orden: borrador -> trozos -> índice (`emma-modelos-partes.json`, el que lee
`app/models_download.py`) -> publicar sin marcarla como «latest» del código.

Subir es decisión del usuario (repositorio público): este script no lo lanza nada de EMMA ni sus
pruebas, y necesita `gh` con sesión. Antes de publicar, repasar las licencias del paquete
(`models_release_notes.md`).

Uso, desde `backend/`: `python packaging/publish_models.py`.
"""
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO = "Brillande/EMMA"
TAG = "modelos-1"
BACKEND = Path(__file__).resolve().parents[1]
PACK = BACKEND / "build" / "emma-modelos"
OUT = BACKEND / "build" / "emma-modelos-partes"
NOTES = Path(__file__).with_name("models_release_notes.md")

spec = importlib.util.spec_from_file_location(
    "models_parts", BACKEND / "packaging" / "models_parts.py"
)
mp = importlib.util.module_from_spec(spec)
sys.modules["models_parts"] = mp
spec.loader.exec_module(mp)


def gh(*args: str) -> None:
    for attempt in range(5):
        r = subprocess.run(["gh", *args], capture_output=True, text=True)
        if r.returncode == 0:
            return
        print(f"gh {args[:3]} falló ({attempt + 1}/5): {r.stderr.strip()[:300]}", flush=True)
        time.sleep(30)
    raise SystemExit("gh no termina")


def upload(path: Path) -> None:
    t = time.time()
    gh("release", "upload", TAG, str(path), "--clobber", "-R", REPO)
    mb = path.stat().st_size / 1e6
    rate = mb / max(time.time() - t, 1)
    print(f"  subido {path.name} ({mb:.0f} MB, {rate:.1f} MB/s)", flush=True)


manifest_path = PACK / mp.MANIFEST_NAME
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
OUT.mkdir(parents=True, exist_ok=True)

r = subprocess.run(["gh", "release", "view", TAG, "-R", REPO], capture_output=True, text=True)
if r.returncode != 0:
    gh("release", "create", TAG, "--draft", "--latest=false", "-R", REPO,
       "--title", "Paquete de modelos de EMMA (modelos-1)", "--notes-file", str(NOTES))

for name in mp.ROOT_FILES:
    shutil.copyfile(PACK / name, OUT / name)
    upload(OUT / name)

index = {
    "emma_models_parts": mp.INDEX_VERSION,
    "created": datetime.now(UTC).isoformat(timespec="seconds"),
    "pack_created": manifest["created"],
    "manifest": {"name": mp.MANIFEST_NAME, "size": manifest_path.stat().st_size,
                 "sha256": mp._sha256(manifest_path)},
    "components": {},
}
done_file = OUT / "hecho.json"
done = json.loads(done_file.read_text(encoding="utf-8")) if done_file.exists() else {}
# Primero lo pequeño: si algo falla, lo útil ya está arriba.
order = ["tesseract", "voice", "segmentation", "ollama"]
groups = mp.components_of(manifest)
for comp in order:
    if comp in done:
        index["components"][comp] = done[comp]
        print(f"-> {comp}: ya subido", flush=True)
        continue
    print(f"-> {comp}: partiendo", flush=True)
    piece = mp.write_component(
        PACK, OUT, comp, groups[comp], manifest["files"], mp.DEFAULT_PART_MB * 1024 * 1024
    )
    for part in piece["parts"]:
        upload(OUT / part["name"])
        (OUT / part["name"]).unlink()
    index["components"][comp] = piece
    done[comp] = piece
    done_file.write_text(json.dumps(done), encoding="utf-8")

index_path = OUT / mp.INDEX_NAME
index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
upload(index_path)
gh("release", "edit", TAG, "--draft=false", "--latest=false", "-R", REPO)
print("PUBLICADO", flush=True)
