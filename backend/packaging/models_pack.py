"""Construye el paquete de modelos de EMMA: lo que el instalador no lleva, para instalarlo sin red.

Por qué existe: decisión del usuario (2026-11-15) de que los modelos se instalen con EMMA, como un
**paquete aparte** que se copia desde disco o USB, sin red. El instalador de la aplicación sigue
sin llevarlos (pesan decenas de GB y se actualizan a otro ritmo); este paquete es la otra mitad.

Qué lleva (cada pieza es la que está probada en la máquina que lo construye, no una descarga nueva):
  * `ollama/`: el programa de Ollama y solo los modelos que EMMA tiene configurados
    (`llm_model`, `llm_verifiers`, `assistant_model`), más los que se pidan con `--ollama-model`.
  * `voice/`: Whisper `base` con su PyTorch, sobre una copia de Python.
  * `segmentation/`: TotalSegmentator con sus pesos (`home/`) y la telemetría apagada.
  * `tesseract/`: el OCR con sus idiomas.
  * `MANIFIESTO.json`: tamaño y SHA-256 de cada fichero, versiones, origen y licencia por pieza.
  * `instalar.cmd` / `instalar.ps1`: comprueban cada fichero y lo copian a `%LOCALAPPDATA%`.

NO lleva la capa NER del BSC (`.venv-deid`): su repositorio no es público (Hugging Face responde
401) y no consta una licencia que permita redistribuirla (`docs/fuentes-y-procedencia.md`).

Por qué una copia de Python y no los `.venv-*`: un venv apunta al Python de la máquina que lo creó
(`pyvenv.cfg: home`) y sus lanzadores `.exe` llevan esa ruta escrita; en otra máquina no arrancan.
La copia lleva un `python312._pth`, que la aísla del PATH, del registro y del Python del sistema.

Por defecto los ficheros se ENLAZAN (enlaces duros de NTFS) en vez de copiarse: el paquete no
ocupa disco de más mientras está en la misma unidad; al copiarlo a un USB salen ficheros normales.
Los blobs de Ollama y los pesos no se modifican nunca, así que compartirlos es seguro.
OJO: por eso mismo NO SE EDITA NADA dentro de la carpeta construida: un fichero enlazado ES el de
Ollama, el del venv o el de Tesseract, y cambiarlo los cambia a ellos. Para probar algo a mano,
`--copy`, o sobre la carpeta ya instalada (`instalar.ps1` copia, no enlaza).

Uso (con el Python de EMMA; no necesita red):
    .venv/Scripts/python.exe packaging/models_pack.py [--out DIR] [--copy] [--ollama-model NOMBRE]
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_OUT = BACKEND / "build" / "emma-modelos"
HERE = Path(__file__).resolve().parent

# De una instalación de Python solo hace falta el intérprete y su biblioteca estándar. Fuera:
# los paquetes del sistema (`Lib/site-packages`: los pone el entorno), sus lanzadores, la
# documentación, las cabeceras y Tcl/Tk (sin interfaz gráfica).
PYTHON_LEFT_OUT = frozenset({"Scripts", "Doc", "include", "libs", "tcl", "share", "NEWS.txt"})
# Del programa de Ollama, el servidor y sus bibliotecas; no la aplicación de la bandeja (busca
# actualizaciones en internet) ni el desinstalador.
OLLAMA_LEFT_OUT = frozenset({"ollama app.exe", "app.ico", "unins000.dat", "unins000.exe",
                             "unins000.msg"})


# --- Copiar ------------------------------------------------------------------------------------

def place(source: Path, target: Path, link: bool) -> None:
    """Un fichero en el paquete: enlace duro si se puede, copia si no."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    if link:
        try:
            os.link(source, target)
            return
        except OSError:
            pass  # otra unidad, o un sistema de ficheros sin enlaces: se copia
    shutil.copy2(source, target)


def place_tree(source: Path, target: Path, link: bool, left_out: Iterable[str] = ()) -> None:
    """Un árbol entero, sin las entradas de primer nivel de `left_out` ni los `__pycache__`."""
    skip = set(left_out)
    for entry in source.iterdir():
        if entry.name in skip:
            continue
        if entry.is_dir():
            for path in entry.rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    place(path, target / entry.name / path.relative_to(entry), link)
        elif entry.is_file():
            place(entry, target / entry.name, link)


# --- Python ------------------------------------------------------------------------------------

def venv_home(venv: Path) -> Path:
    """La instalación de Python sobre la que se creó un venv (`pyvenv.cfg: home`)."""
    for line in (venv / "pyvenv.cfg").read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "home":
            return Path(value.strip())
    raise SystemExit(f"{venv}: pyvenv.cfg sin 'home'")


def pth_file(home: Path) -> tuple[str, str]:
    """El `pythonXY._pth` que aísla la copia: solo sus rutas, y `site` para los `.pth`."""
    dll = next(home.glob("python3?*.dll"), None)
    if dll is None:
        raise SystemExit(f"{home}: no hay pythonXY.dll")
    name = dll.stem + "._pth"
    return name, "\n".join(["DLLs", "Lib", r"Lib\site-packages", "import site", ""])


def python_copy(venv: Path, target: Path, link: bool) -> None:
    """Python de la instalación base + los paquetes del venv, en una carpeta que se puede mover."""
    home = venv_home(venv)
    place_tree(home, target, link, PYTHON_LEFT_OUT)
    site = target / "Lib" / "site-packages"
    if site.exists():
        shutil.rmtree(site)
    place_tree(venv / "Lib" / "site-packages", site, link)
    name, text = pth_file(home)
    (target / name).write_text(text, encoding="utf-8")


def python_check(python: Path, code: str, env: dict[str, str] | None = None) -> str:
    """Corre `code` con la copia, desde fuera de la carpeta y sin variables de Python heredadas."""
    clean = {k: v for k, v in os.environ.items() if not k.upper().startswith("PYTHON")}
    clean["PYTHONNOUSERSITE"] = "1"
    result = subprocess.run([str(python), "-c", code], capture_output=True, text=True,
                            env={**clean, **(env or {})}, cwd=python.anchor, check=False)
    if result.returncode != 0:
        raise SystemExit(f"{python}: la comprobación falló\n{result.stderr[-2000:]}")
    return result.stdout.strip()


# --- Ollama ------------------------------------------------------------------------------------

def ollama_models_dir() -> Path:
    configured = os.environ.get("OLLAMA_MODELS")
    return Path(configured) if configured else Path.home() / ".ollama" / "models"


def ollama_program_dir() -> Path:
    found = shutil.which("ollama")
    if found:
        return Path(found).resolve().parent
    default = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama"
    if (default / "ollama.exe").is_file():
        return default
    raise SystemExit("no se encuentra Ollama instalado")


def split_name(model: str) -> tuple[str, str]:
    """`gemma4:e4b` -> (`gemma4`, `e4b`); sin etiqueta, `latest`, como Ollama."""
    name, _, tag = model.partition(":")
    return name, tag or "latest"


def manifest_files(models_dir: Path, model: str) -> list[Path]:
    """Los manifiestos de un modelo, en los dos formatos de carpeta que usa Ollama."""
    name, tag = split_name(model)
    namespace = name if "/" in name else f"library/{name}"
    candidates = [
        models_dir / "manifests" / "registry.ollama.ai" / namespace / tag,
        models_dir / "manifests-v2" / "ollama.com" / namespace / tag,
    ]
    return [path for path in candidates if path.is_file()]


def digests(document: object) -> Iterator[str]:
    """Todos los `digest` de un manifiesto de Ollama (lista de manifiestos, capas, config)."""
    if isinstance(document, dict):
        for key, value in document.items():
            if key == "digest" and isinstance(value, str):
                yield value
            else:
                yield from digests(value)
    elif isinstance(document, list):
        for item in document:
            yield from digests(item)


def blob_path(models_dir: Path, digest: str) -> Path:
    return models_dir / "blobs" / digest.replace(":", "-")


def model_files(models_dir: Path, model: str) -> list[Path]:
    """Manifiestos y blobs de un modelo. Un manifiesto que apunta a otro se sigue.

    La lista de manifiestos de Ollama nombra variantes que no siempre están en disco (la `mlx`
    de Apple junto a la `gguf`): se lleva lo que hay; si no queda ningún blob de pesos, falla.
    """
    manifests = manifest_files(models_dir, model)
    if not manifests:
        raise SystemExit(f"Ollama no tiene el modelo {model!r} (ollama pull {model})")
    files: list[Path] = list(manifests)
    pending = [json.loads(path.read_text(encoding="utf-8")) for path in manifests]
    seen: set[str] = set()
    while pending:
        for digest in digests(pending.pop()):
            if digest in seen:
                continue
            seen.add(digest)
            blob = blob_path(models_dir, digest)
            if not blob.is_file():
                continue
            files.append(blob)
            if blob.stat().st_size < 1_000_000:  # un manifiesto o una config, no unos pesos
                with contextlib.suppress(UnicodeDecodeError, ValueError):
                    pending.append(json.loads(blob.read_text(encoding="utf-8")))
    if not any(path.stat().st_size >= 1_000_000 for path in files):
        raise SystemExit(f"{model!r}: no están sus pesos en {models_dir / 'blobs'}")
    return files


def configured_models() -> list[str]:
    sys.path.insert(0, str(BACKEND))
    from app.core.config import Settings

    settings = Settings()
    return list(dict.fromkeys([settings.llm_model, *settings.llm_verifiers,
                               settings.assistant_model]))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def ollama_check(program: Path, models: Path, expected: list[str]) -> str:
    """Arranca el Ollama del paquete con sus modelos y pide la lista: tienen que estar todos."""
    port = free_port()
    env = {**os.environ, "OLLAMA_HOST": f"127.0.0.1:{port}", "OLLAMA_MODELS": str(models)}
    server = subprocess.Popen([str(program / "ollama.exe"), "serve"], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/tags", timeout=5) as r:
                    tags = json.load(r)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise SystemExit("el Ollama del paquete no respondió") from None
                time.sleep(0.5)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/version", timeout=5) as r:
            version = str(json.load(r).get("version", "?"))
    finally:
        server.kill()
        server.wait()
    listed = {split_name(m["name"]) for m in tags.get("models", [])}
    missing = [m for m in expected if split_name(m) not in listed]
    if missing:
        raise SystemExit(f"el Ollama del paquete no ve {missing}")
    return version


# --- Piezas --------------------------------------------------------------------------------------

def build_ollama(out: Path, link: bool, models: list[str]) -> dict[str, object]:
    program, source = ollama_program_dir(), ollama_models_dir()
    target = out / "ollama"
    place_tree(program, target, link, OLLAMA_LEFT_OUT)
    for model in models:
        for path in model_files(source, model):
            place(path, target / "models" / path.relative_to(source), link)
    version = ollama_check(target, target / "models", models)
    return {
        "path": "ollama", "version": version, "models": models,
        "source": "https://ollama.com (programa) y registro ollama.com (modelos, `ollama pull`)",
        "license": "Ollama: MIT. Modelos: Apache-2.0 según `ollama show --license` "
                   "(docs/fuentes-y-procedencia.md, rama 11)",
    }


def build_voice(out: Path, link: bool) -> dict[str, object]:
    venv = BACKEND / ".venv-voice"
    marker = venv / "voice-ok.json"
    if not marker.is_file():
        raise SystemExit("Whisper no está instalado (scripts/install_voice.py)")
    target = out / "voice"
    python_copy(venv, target, link)
    place_tree(venv / "cache", target / "cache", link)
    place(marker, target / "voice-ok.json", link)
    installed = json.loads(marker.read_text(encoding="utf-8"))
    weights = target / "cache" / "whisper" / f"{installed['model']}.pt"
    if sha256(weights) != installed["sha256"]:
        raise SystemExit(f"{weights}: la huella no coincide con voice-ok.json")
    python_check(target / "python.exe", "import whisper, torch, soundfile")
    return {
        "path": "voice", "version": installed["whisper"], "model": installed["model"],
        "source": "openaipublic.azureedge.net (pesos, URL fijada en el paquete whisper); "
                  "PyPI y download.pytorch.org/whl/cpu (programas)",
        "license": "openai-whisper: MIT (código); pesos sin anotar. PyTorch: BSD-3",
    }


def build_segmentation(out: Path, link: bool) -> dict[str, object]:
    venv = BACKEND / ".venv-seg"
    home = Path(os.environ.get("TOTALSEG_HOME_DIR") or Path.home() / ".totalsegmentator")
    config = json.loads((home / "config.json").read_text(encoding="utf-8"))
    if config.get("send_usage_stats") is not False:
        raise SystemExit(f"{home / 'config.json'}: la telemetría no está apagada")
    target = out / "segmentation"
    python_copy(venv, target, link)
    place_tree(home / "nnunet", target / "home" / "nnunet", link)
    # La configuración se escribe, no se enlaza: sin el identificador ni el contador de aquí.
    (target / "home").mkdir(parents=True, exist_ok=True)
    (target / "home" / "config.json").write_text(json.dumps(
        {"send_usage_stats": False, "statistics_disclaimer_shown": True}, indent=4),
        encoding="utf-8")
    version = python_check(
        target / "python.exe",
        "import importlib.metadata as m, totalsegmentator.bin.TotalSegmentator; "
        "print(m.version('totalsegmentator'))")
    tasks = sorted(p.name for p in (home / "nnunet" / "results").iterdir() if p.is_dir())
    return {
        "path": "segmentation", "version": version, "tasks": tasks,
        "source": "PyPI (totalsegmentator); pesos descargados por TotalSegmentator",
        "license": "Apache-2.0 (código y tareas usadas); PyTorch: BSD-3",
    }


def build_tesseract(out: Path, link: bool) -> dict[str, object]:
    sys.path.insert(0, str(BACKEND))
    from app.reports.ocr import find_tesseract

    found = find_tesseract(os.environ.get("EMMA_TESSERACT_CMD"))
    if found is None:
        raise SystemExit("no se encuentra tesseract")
    target = out / "tesseract"
    place_tree(Path(found).parent, target, link)
    exe = target / Path(found).name
    langs = subprocess.run([str(exe), "--list-langs"], capture_output=True, text=True,
                           check=False).stdout.split()
    if "spa" not in langs:
        raise SystemExit("al tesseract del paquete le falta el español (spa.traineddata)")
    version = subprocess.run([str(exe), "--version"], capture_output=True, text=True,
                             check=False).stdout.splitlines()[0]
    return {
        "path": "tesseract", "version": version,
        "languages": [x for x in langs if x in {"eng", "osd", "spa"}],
        "source": "Tesseract de UB Mannheim; idiomas de github.com/tesseract-ocr/tessdata_fast",
        "license": "Apache-2.0",
    }


# --- Manifiesto ----------------------------------------------------------------------------------

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_table(out: Path) -> dict[str, tuple[int, str]]:
    """Ruta relativa (con `/`) -> (tamaño, sha256), de todo salvo el propio manifiesto."""
    table: dict[str, tuple[int, str]] = {}
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "MANIFIESTO.json":
            table[path.relative_to(out).as_posix()] = (path.stat().st_size, sha256(path))
    return table


BUILDERS = ("ollama", "voice", "segmentation", "tesseract")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--copy", action="store_true", help="copiar en vez de enlazar")
    parser.add_argument("--ollama-model", action="append", default=[],
                        help="un modelo de Ollama más, además de los configurados")
    parser.add_argument("--only", choices=BUILDERS, action="append",
                        help="construir solo estas piezas")
    args = parser.parse_args(argv)
    link = not args.copy
    out: Path = args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    models = list(dict.fromkeys([*configured_models(), *args.ollama_model]))
    components: dict[str, object] = {}
    for name in args.only or BUILDERS:
        print(f"-> {name}", flush=True)
        if name == "ollama":
            components[name] = build_ollama(out, link, models)
        elif name == "voice":
            components[name] = build_voice(out, link)
        elif name == "segmentation":
            components[name] = build_segmentation(out, link)
        else:
            components[name] = build_tesseract(out, link)

    for script in ("instalar.ps1", "instalar.cmd", "LEEME.txt"):
        shutil.copy2(HERE / "models_pack" / script, out / script)
    print("-> huellas", flush=True)
    files = file_table(out)
    manifest = {
        "emma_models_pack": 1,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "components": components,
        "left_out": {"deid_ner": "BSC-NLP4BIA/bsc-bio-ehr-es-contacto-anon: repositorio no "
                                 "público (401) y sin licencia que permita redistribuirlo"},
        "files": files,
    }
    (out / "MANIFIESTO.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False),
                                         encoding="utf-8")
    total = sum(size for size, _ in files.values())
    print(f"paquete de modelos listo: {len(files)} ficheros, {total / 1e9:.1f} GB en {out}")


if __name__ == "__main__":
    main()
