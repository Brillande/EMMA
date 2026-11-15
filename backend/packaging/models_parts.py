"""Parte el paquete de modelos en trozos para publicarlo y descargarlo desde EMMA.

Por qué existe: decisión del usuario (2026-11-15) de que los modelos se puedan descargar con el
programa («Descargar modelos», `app/models_download.py`), todo junto o pieza a pieza. El paquete
que deja `models_pack.py` son unos 55 000 ficheros y decenas de GB: así no se publica. GitHub
admite como mucho 2 GB por fichero en una versión publicada y unos cientos de ficheros; por eso
cada pieza (`ollama`, `voice`, `segmentation`, `tesseract`) va en un único `tar` sin comprimir
(los pesos no se comprimen) cortado en trozos de menos de 2 GB.

Qué deja en `--out`:
  * `emma-modelos-<pieza>.tar.NNN`: los trozos, en orden.
  * `emma-modelos-partes.json`: el índice. Por pieza, el tamaño instalado y cada trozo con su
    tamaño y SHA-256; y la huella del `MANIFIESTO.json`, que dice el tamaño y la huella de cada
    fichero instalado. La descarga comprueba los dos niveles: el trozo al bajarlo y el fichero al
    sacarlo del `tar`.
  * `MANIFIESTO.json`, `LEEME.txt`, `instalar.cmd`, `instalar.ps1`: copiados tal cual del paquete.

El `tar` solo lleva ficheros normales (nunca enlaces, aunque en el paquete lo sean: ver
`models_pack.py`), con rutas relativas `pieza/...` y en el orden del manifiesto. Quien
descarga solo saca los que el manifiesto nombra para esa pieza, así que una ruta rara en el `tar`
no puede escribir fuera de la carpeta.

Publicar (subir los ficheros de `--out` a una versión de `github.com/Brillande/EMMA`) es decisión
del usuario y no lo hace este guion.

Uso (con el Python de EMMA; no necesita red):
    .venv/Scripts/python.exe packaging/models_parts.py [--pack DIR] [--out DIR] [--part-mb N]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_PACK = BACKEND / "build" / "emma-modelos"
DEFAULT_OUT = BACKEND / "build" / "emma-modelos-partes"
INDEX_NAME = "emma-modelos-partes.json"
MANIFEST_NAME = "MANIFIESTO.json"
# Los ficheros de la raíz del paquete que viajan sueltos (pequeños, comprobados por el manifiesto).
ROOT_FILES = ("MANIFIESTO.json", "LEEME.txt", "instalar.cmd", "instalar.ps1")
# Por debajo del límite de 2 GiB por fichero de GitHub, con margen.
DEFAULT_PART_MB = 1900
INDEX_VERSION = 1
CHUNK = 1 << 20


def part_name(component: str, index: int) -> str:
    return f"emma-modelos-{component}.tar.{index:03d}"


class _PartWriter:
    """Un fichero de escritura que en realidad son trozos de `limit` bytes, con su huella."""

    def __init__(self, out: Path, component: str, limit: int) -> None:
        self.out = out
        self.component = component
        self.limit = limit
        self.parts: list[dict[str, Any]] = []
        self._handle: BinaryIO | None = None
        self._hash = hashlib.sha256()
        self._size = 0

    def _open(self) -> None:
        name = part_name(self.component, len(self.parts))
        self._handle = (self.out / name).open("wb")
        self._hash = hashlib.sha256()
        self._size = 0
        self.parts.append({"name": name})

    def _close(self) -> None:
        if self._handle is None:
            return
        self._handle.close()
        self._handle = None
        self.parts[-1].update(size=self._size, sha256=self._hash.hexdigest())

    def write(self, data: bytes) -> int:
        view = memoryview(data)
        while view:
            if self._handle is None or self._size >= self.limit:
                self._close()
                self._open()
            assert self._handle is not None
            take = min(len(view), self.limit - self._size)
            chunk = view[:take]
            self._handle.write(chunk)
            self._hash.update(chunk)
            self._size += take
            view = view[take:]
        return len(data)

    def close(self) -> None:
        self._close()


def components_of(manifest: dict[str, Any]) -> dict[str, list[str]]:
    """Pieza -> sus ficheros, en el orden del manifiesto."""
    files: dict[str, list[str]] = {name: [] for name in manifest["components"]}
    for rel in manifest["files"]:
        head = rel.split("/", 1)[0]
        if head in files and "/" in rel:
            files[head].append(rel)
    return files


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def write_component(pack: Path, out: Path, component: str, files: list[str],
                    manifest_files: dict[str, Any], limit: int) -> dict[str, Any]:
    writer = _PartWriter(out, component, limit)
    installed = 0
    # `w|`: escritura en flujo, sin volver atrás, que es lo que permite cortar en trozos.
    with tarfile.open(fileobj=writer, mode="w|", format=tarfile.PAX_FORMAT) as tar:  # type: ignore[call-overload]
        for rel in files:
            source = pack / rel
            size = int(manifest_files[rel][0])
            info = tarfile.TarInfo(rel)
            # Fichero normal siempre: `gettarinfo` convertiría en enlace duro un fichero que
            # comparta inodo con otro del paquete (`models_pack.py` enlaza en vez de copiar).
            info.type = tarfile.REGTYPE
            info.size = size
            info.mode = 0o644
            info.mtime = int(source.stat().st_mtime)
            with source.open("rb") as handle:
                tar.addfile(info, handle)
            installed += size
    writer.close()
    return {"installed_size": installed, "files": len(files), "parts": writer.parts}


def build(pack: Path, out: Path, part_bytes: int) -> dict[str, Any]:
    manifest_path = pack / MANIFEST_NAME
    if not manifest_path.is_file():
        raise SystemExit(f"no hay {MANIFEST_NAME} en {pack}: construye antes el paquete")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name in ROOT_FILES:
        shutil.copyfile(pack / name, out / name)
    index: dict[str, Any] = {
        "emma_models_parts": INDEX_VERSION,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "pack_created": manifest["created"],
        "manifest": {"name": MANIFEST_NAME, "size": manifest_path.stat().st_size,
                     "sha256": _sha256(manifest_path)},
        "components": {},
    }
    for component, files in components_of(manifest).items():
        if not files:
            continue
        print(f"-> {component} ({len(files)} ficheros)", flush=True)
        index["components"][component] = write_component(
            pack, out, component, files, manifest["files"], part_bytes
        )
    (out / INDEX_NAME).write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    return index


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--part-mb", type=int, default=DEFAULT_PART_MB)
    args = parser.parse_args(argv)
    index = build(args.pack, args.out, args.part_mb * 1024 * 1024)
    parts = sum(len(c["parts"]) for c in index["components"].values())
    print(f"listo: {parts} trozos de {len(index['components'])} piezas en {args.out}")


if __name__ == "__main__":
    sys.exit(main())
