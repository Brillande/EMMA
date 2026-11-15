"""Los avisos de licencia de los paquetes Python que viajan dentro del backend congelado.

Por qué existe: el instalador llevaba los avisos de EMMA, Polaris y Marplanner, y no los de los
paquetes que PyInstaller mete en el ejecutable (FastAPI, numpy, cryptography, pydicom...). Casi
todas sus licencias (MIT, BSD, Apache-2.0) piden que su texto acompañe a la redistribución,
también en forma binaria. Lo encontró la revisión de fuentes del 2026-11-14
(`docs/fuentes-y-procedencia.md`, «Resumen de huecos», punto 2).

Qué escribe: por cada distribución instalada en el entorno de empaquetado, salvo las herramientas
de construcción (`BUILD_ONLY`) y lo que `freeze.py` excluye, su nombre, versión, la licencia que
declaran sus metadatos y el texto de los ficheros de licencia y aviso que trae su `dist-info`. No
interpreta ni resume licencias: copia lo que el paquete declara. Un paquete sin fichero de licencia
se lista igual, y lo dice.

Corre en el entorno de empaquetado (`build/venv-desktop`), desde `freeze.py`, después de
PyInstaller.
"""

from __future__ import annotations

import importlib.metadata as metadata
import re
from collections.abc import Iterable
from pathlib import Path

# Herramientas que construyen el ejecutable y no viajan en él. PyInstaller deja su cargador
# (bootloader) dentro, pero su licencia (GPLv2+ con excepción) lo permite sin arrastrar la GPL.
BUILD_ONLY = frozenset({
    "pip", "setuptools", "wheel", "pyinstaller", "pyinstaller-hooks-contrib", "altgraph",
    "pefile", "pywin32-ctypes", "packaging",
})

# Ficheros de un `dist-info` que llevan texto de licencia o aviso.
_LICENSE_FILE = re.compile(r"(^|/)(licen[cs]e|copying|notice|authors)[^/]*$", re.IGNORECASE)

HEADER = (
    "Avisos de licencia de los paquetes Python incluidos en el backend de EMMA\n"
    "========================================================================\n\n"
    "Generado al congelar el backend (backend/packaging/third_party.py). Cada paquete conserva su\n"
    "licencia; aquí va el texto que el propio paquete distribuye. La licencia de EMMA está en\n"
    "LICENSE y sus avisos en NOTICE, en la carpeta de recursos de la aplicación.\n"
)


def _name(dist: metadata.Distribution) -> str:
    return (dist.metadata["Name"] or "").strip()


def _declared(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return expression.strip()
    text = (meta.get("License") or "").strip()
    if text and "\n" not in text and len(text) <= 120:
        return text
    classifiers = [
        c.split("::")[-1].strip() for c in (meta.get_all("Classifier") or [])
        if c.startswith("License ::")
    ]
    return "; ".join(classifiers) or "no declarada en los metadatos"


def _license_texts(dist: metadata.Distribution) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for file in dist.files or []:
        path = str(file).replace("\\", "/")
        if ".dist-info/" not in path or not _LICENSE_FILE.search(path):
            continue
        try:
            text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if text.strip():
            found.append((path.split(".dist-info/", 1)[1], text.strip()))
    return found


def notices(
    dists: Iterable[metadata.Distribution] | None = None, excluded: Iterable[str] = (),
) -> str:
    """El texto completo del fichero de avisos, ordenado por nombre de paquete."""
    skip = {n.lower() for n in BUILD_ONLY} | {n.lower() for n in excluded}
    chosen: dict[str, metadata.Distribution] = {}
    for dist in dists if dists is not None else metadata.distributions():
        name = _name(dist)
        if name and name.lower() not in skip:
            chosen.setdefault(name.lower(), dist)
    parts = [HEADER]
    for key in sorted(chosen):
        dist = chosen[key]
        parts.append("\n" + "-" * 72 + "\n")
        parts.append(f"{_name(dist)} {dist.version}\nLicencia declarada: {_declared(dist)}\n")
        texts = _license_texts(dist)
        if not texts:
            parts.append("(El paquete no trae fichero de licencia en su dist-info.)\n")
        for path, text in texts:
            parts.append(f"\n[{path}]\n{text}\n")
    return "".join(parts)


def write(folder: Path, excluded: Iterable[str] = ()) -> Path:
    """Escribe `THIRD_PARTY_LICENSES.txt` en `folder` y devuelve su ruta."""
    target = folder / "THIRD_PARTY_LICENSES.txt"
    target.write_text(notices(excluded=excluded), encoding="utf-8", newline="\n")
    return target
