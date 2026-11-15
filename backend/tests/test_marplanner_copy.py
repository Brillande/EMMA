"""La copia de Marplanner en `marplanner/` sigue siendo literal.

Por qué existe: la regla de adopción es copiar tal cual y decidir los cambios después, uno a uno y
declarados. Sin esta prueba, un retoco "pequeño" dentro de la copia pasa desapercibido y la copia
deja de ser lo que dice `NOTICE`. Lo que la copia NO debe traer (despliegue en la nube) también se
comprueba aquí: si un sync futuro lo reintrodujera, falla.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COPY = REPO / "marplanner"
EMMA_FILES = {"ADOPTADO.txt", "MANIFEST.sha256", "ORIGEN.md"}
GENERATED_DIRS = {"node_modules", "dist", ".data", "coverage"}


def _manifest() -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in (COPY / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        digest, path = line.split("  ", 1)
        entries[path] = digest
    return entries


def _left_out() -> list[str]:
    out = []
    for line in (COPY / "ADOPTADO.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split("#", 1)[0].split()
        if len(parts) == 2 and parts[0] == "fuera":
            out.append(parts[1].strip("/"))
    return out


def test_every_copied_file_is_byte_identical() -> None:
    changed = [
        path for path, digest in _manifest().items()
        if hashlib.sha256((COPY / path).read_bytes()).hexdigest() != digest
    ]
    assert changed == [], f"ficheros retocados dentro de la copia literal: {changed[:10]}"


def test_no_file_outside_the_manifest() -> None:
    manifest = _manifest()
    extra = []
    for path in COPY.rglob("*"):
        rel = path.relative_to(COPY).as_posix()
        if not path.is_file() or rel in EMMA_FILES or rel.split("/", 1)[0] in GENERATED_DIRS:
            continue
        if rel not in manifest:
            extra.append(rel)
    assert extra == [], f"ficheros en marplanner/ que no vienen del commit: {extra[:10]}"


def test_cloud_deployment_is_left_out() -> None:
    left_out = _left_out()
    assert {".github", ".do", "render.yaml", "railway.json", "infra/fly"} <= set(left_out)
    present = [x for x in left_out if (COPY / x).exists()]
    assert present == [], f"declarado fuera pero presente: {present}"


def test_mit_license_travels_with_the_copy() -> None:
    assert "MIT License" in (COPY / "LICENSE").read_text(encoding="utf-8")
    assert "Marplanner" in (REPO / "NOTICE").read_text(encoding="utf-8")
