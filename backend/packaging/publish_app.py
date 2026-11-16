"""Publica el instalador de EMMA como versión `vX.Y.Z` de GitHub, con su manifiesto.

Por qué existe: el EMMA instalado se actualiza solo leyendo, por `egress`,
`https://github.com/Brillande/EMMA/releases/latest/download/emma-update.json` y descargando de
esa misma versión el instalador que nombra, cuyo tamaño y SHA-256 comprueba. La v0.1.4 se publicó
a mano, y a mano es fácil equivocarse en lo que el programa da por cierto:

  * El instalador local se llama `EMMA Setup X.Y.Z.exe` y GitHub cambia los espacios por puntos
    al subirlo (`EMMA.Setup.X.Y.Z.exe`). El manifiesto tiene que nombrar el fichero tal como queda
    en GitHub; por eso se sube una copia que ya lleva el nombre con puntos.
  * Un manifiesto que apunte a un instalador aún no subido rompe la actualización de todos los
    equipos que pregunten en ese momento. Por eso la versión nace como borrador, el instalador
    sube primero, el manifiesto al final, y solo entonces se publica y se marca como «latest».
  * La versión tiene que ser la misma en los cuatro sitios del repositorio
    (`backend/pyproject.toml`, `frontend/package.json`, `desktop/package.json` y el `version=`
    de FastAPI en `backend/app/main.py`); si no, el programa diría una versión y el manifiesto
    otra, y el instalado se creería siempre desactualizado. Lo vigila también
    `tests/test_versions.py`.

La versión de modelos (`modelos-1`, `publish_models.py`) no es «latest» y este guion no la toca.

Solo sube ficheros a una versión («assets»): no sube código. La rama de publicación y la «foto»
pública del código son cosa aparte y manual. Publicar es decisión del usuario (repositorio
público): este guion no lo lanza nada de EMMA ni sus pruebas, y necesita `gh` con sesión.
Las pruebas solo usan las funciones puras y un `subprocess` simulado.

Uso, desde `backend/`, después de `npm run dist` en `desktop/`:
    .venv/Scripts/python.exe packaging/publish_app.py --notes "Texto corto" [--dry-run]
    .venv/Scripts/python.exe packaging/publish_app.py --notes-file notas.md [--installer RUTA]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path
from typing import Any

REPO = "Brillande/EMMA"
MANIFEST_NAME = "emma-update.json"
SCHEMA = 1
ROOT = Path(__file__).resolve().parents[2]

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_FASTAPI_VERSION = re.compile(r'^\s*version="([^"]+)",?\s*$', re.MULTILINE)


class PublishError(Exception):
    """Algo impide publicar: se explica y no se sube nada (o no se sigue subiendo)."""


# --- Lógica pura -------------------------------------------------------------------------------


def read_versions(root: Path = ROOT) -> dict[str, str]:
    """La versión que declara cada uno de los cuatro sitios del repositorio."""
    pyproject = tomllib.loads((root / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    main_py = (root / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    found = _FASTAPI_VERSION.findall(main_py)
    if len(found) != 1:
        raise PublishError(
            f"backend/app/main.py: se esperaba un único version=\"...\" y hay {len(found)}"
        )
    return {
        "desktop/package.json": _package_version(root / "desktop" / "package.json"),
        "frontend/package.json": _package_version(root / "frontend" / "package.json"),
        "backend/pyproject.toml": str(pyproject["project"]["version"]),
        "backend/app/main.py": found[0],
    }


def _package_version(path: Path) -> str:
    return str(json.loads(path.read_text(encoding="utf-8"))["version"])


def agreed_version(versions: dict[str, str]) -> str:
    """La versión común; si los sitios discrepan o no es X.Y.Z, se detiene."""
    distinct = set(versions.values())
    if len(distinct) != 1:
        detail = ", ".join(f"{where}={v}" for where, v in versions.items())
        raise PublishError(f"la versión no coincide en el repositorio: {detail}")
    version = distinct.pop()
    if not _SEMVER.match(version):
        raise PublishError(f"versión {version!r}: se esperaba X.Y.Z")
    return version


def tag_for(version: str) -> str:
    return f"v{version}"


def local_installer_name(version: str) -> str:
    """Como lo deja electron-builder en `desktop/release/`."""
    return f"EMMA Setup {version}.exe"


def asset_name(version: str) -> str:
    """Como queda en GitHub: los espacios pasan a puntos."""
    return local_installer_name(version).replace(" ", ".")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(installer: Path, version: str, notes: str) -> dict[str, Any]:
    """El `emma-update.json` del contrato, calculado sobre el instalador que se va a subir."""
    notes = notes.strip()
    if not notes:
        raise PublishError("faltan las notas (--notes o --notes-file)")
    return {
        "schema": SCHEMA,
        "version": version,
        "installer": asset_name(version),
        "size": installer.stat().st_size,
        "sha256": sha256_of(installer),
        "notes": notes,
    }


def gh_plan(version: str, staged_exe: Path, manifest: Path, notes_file: Path) -> list[list[str]]:
    """Las órdenes de `gh`, en el orden en que deben ir.

    Borrador primero; el instalador antes que el manifiesto, para que nunca haya un manifiesto
    que apunte a un instalador que aún no está; publicar y marcar «latest» al final.
    """
    tag = tag_for(version)
    return [
        ["release", "create", tag, "--draft", "--title", f"EMMA {version}",
         "--notes-file", str(notes_file), "-R", REPO],
        ["release", "upload", tag, str(staged_exe), "--clobber", "-R", REPO],
        ["release", "upload", tag, str(manifest), "--clobber", "-R", REPO],
        ["release", "edit", tag, "--draft=false", "--latest", "-R", REPO],
    ]


# --- gh ----------------------------------------------------------------------------------------


def gh(args: list[str], *, retries: int = 5, wait: float = 30) -> None:
    """Lanza `gh` con reintentos. Solo para órdenes que se pueden repetir sin daño."""
    for attempt in range(retries):
        r = subprocess.run(["gh", *args], capture_output=True, text=True)
        if r.returncode == 0:
            return
        print(f"gh {args[:3]} falló ({attempt + 1}/{retries}): {r.stderr.strip()[:300]}",
              flush=True)
        if attempt + 1 < retries:
            time.sleep(wait)
    raise PublishError(f"gh {args[:3]} no termina")


def tag_exists(tag: str) -> bool:
    """Si la versión ya existe en GitHub. Un error que no sea «no existe» detiene: sin saberlo
    no se publica."""
    r = subprocess.run(["gh", "release", "view", tag, "-R", REPO], capture_output=True, text=True)
    if r.returncode == 0:
        return True
    if "not found" in r.stderr.lower():
        return False
    raise PublishError(f"gh release view {tag} falló: {r.stderr.strip()[:300]}")


def publish(version: str, staged_exe: Path, manifest: Path, notes_file: Path) -> None:
    tag = tag_for(version)
    if tag_exists(tag):
        raise PublishError(f"la versión {tag} ya existe en {REPO}: sube la versión antes")
    create, *rest = gh_plan(version, staged_exe, manifest, notes_file)
    # Crear no se reintenta: si llegó a crearse, el reintento fallaría por duplicado y ocultaría
    # el primer error. Subir con --clobber y editar sí se pueden repetir.
    gh(create, retries=1)
    try:
        for args in rest:
            gh(args)
    except PublishError as e:
        # Queda un borrador a medias, invisible para los EMMA instalados (no es «latest»). No se
        # reanuda solo: el paso 4 exige que la etiqueta no exista, y así no se publica nunca sobre
        # algo que no se sabe quién subió.
        raise PublishError(
            f"{e}. Queda el borrador {tag}: bórralo (gh release delete {tag} --yes "
            f"--cleanup-tag -R {REPO}) y repite"
        ) from e


# --- Entrada -----------------------------------------------------------------------------------


def _read_notes(args: argparse.Namespace) -> str:
    if args.notes_file is not None:
        return Path(args.notes_file).read_text(encoding="utf-8")
    return str(args.notes or "")


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    # La consola de Windows escribe en cp1252: unas notas con «→» tiraban el simulacro al
    # imprimir el manifiesto (pasó al publicar la 0.1.5, 2026-11-16).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Publica el instalador de EMMA en GitHub.")
    notes = p.add_mutually_exclusive_group(required=True)
    notes.add_argument("--notes", help="texto corto de la versión")
    notes.add_argument("--notes-file", help="fichero con las notas de la versión")
    p.add_argument("--installer", help="instalador a publicar (por defecto, el de desktop/release)")
    p.add_argument("--dry-run", action="store_true", help="enseña lo que haría; no llama a gh")
    args = p.parse_args(argv)

    try:
        version = agreed_version(read_versions(root))
        installer = (Path(args.installer) if args.installer
                     else root / "desktop" / "release" / local_installer_name(version))
        if not installer.is_file():
            raise PublishError(f"no está el instalador: {installer}")
        text = _read_notes(args)
        manifest = build_manifest(installer, version, text)

        with tempfile.TemporaryDirectory(prefix="emma-publish-") as tmp:
            stage = Path(tmp)
            staged_exe = stage / asset_name(version)
            manifest_path = stage / MANIFEST_NAME
            notes_path = stage / "notas.md"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                                     encoding="utf-8")
            notes_path.write_text(text.strip() + "\n", encoding="utf-8")

            print(json.dumps(manifest, ensure_ascii=False, indent=1))
            if args.dry_run:
                print(f"(simulacro) se comprobaría que {tag_for(version)} no existe y se haría:")
                for cmd in gh_plan(version, staged_exe, manifest_path, notes_path):
                    print("  " + subprocess.list2cmdline(["gh", *cmd]))
                return 0

            shutil.copyfile(installer, staged_exe)
            # La copia es lo que se sube: que sea lo que dice el manifiesto.
            if sha256_of(staged_exe) != manifest["sha256"]:
                raise PublishError("la copia del instalador no coincide con el manifiesto")
            publish(version, staged_exe, manifest_path, notes_path)
    except (PublishError, OSError, ValueError, KeyError) as e:
        # ValueError cubre JSON, TOML y UTF-8 rotos; KeyError, un `version` que falta.
        print(f"No se publica: {e!r}" if not isinstance(e, PublishError)
              else f"No se publica: {e}", file=sys.stderr)
        return 1
    print(f"PUBLICADO {tag_for(version)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
