"""Copia Marplanner literal a `marplanner/` según `marplanner/ADOPTADO.txt`.

Por qué existe: adoptar código de terceros en EMMA es **copiarlo tal cual** y decidir los cambios
después, uno a uno (la regla nació con Polaris, cuyo visor 3D se "adaptó" al portarlo y quedó peor).
Marplanner son más de mil ficheros; copiarlos a mano es la forma segura de dejarse uno o retocar
otro sin querer. Se lee de los objetos de git del commit (`git archive`), no de una copia de
trabajo: en Windows una copia de trabajo sale en CRLF y deja de ser literal. Lo que no se copia
se declara en ADOPTADO.txt con su motivo (`fuera`). Escribe el manifiesto de huellas que vigila
`tests/test_marplanner_copy.py`. Es idempotente.

Uso:
    .venv/Scripts/python.exe scripts/marplanner_sync.py <clon local de Marplanner>
"""

from __future__ import annotations

import hashlib
import io
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TARGET = REPO / "marplanner"
LIST = TARGET / "ADOPTADO.txt"
MANIFEST = TARGET / "MANIFEST.sha256"
# Ficheros propios de EMMA dentro de la copia; no vienen de Marplanner.
EMMA_FILES = {"ADOPTADO.txt", "MANIFEST.sha256", "ORIGEN.md"}
# Lo que se genera al instalar o compilar y nunca forma parte de la copia.
GENERATED_DIRS = {"node_modules", "dist", ".data", "coverage"}


def read_list() -> tuple[str, list[str]]:
    commit = ""
    left_out: list[str] = []
    for line in LIST.read_text(encoding="utf-8").splitlines():
        body, _, reason = line.partition("#")
        parts = body.split()
        if not parts:
            continue
        if len(parts) != 2:
            raise SystemExit(f"ADOPTADO.txt: entrada mal formada {line!r}")
        kind, value = parts
        if kind == "commit":
            commit = value
        elif kind == "fuera":
            if not reason.strip():
                raise SystemExit(f"ADOPTADO.txt: `fuera {value}` sin motivo")
            left_out.append(value.strip("/"))
        else:
            raise SystemExit(f"ADOPTADO.txt: tipo desconocido {kind!r}")
    if len(commit) != 40:
        raise SystemExit("ADOPTADO.txt: falta `commit <sha completo>`")
    return commit, left_out


def is_left_out(path: str, left_out: list[str]) -> bool:
    return any(path == x or path.startswith(x + "/") for x in left_out)


def archive(clone: Path, commit: str) -> dict[str, bytes]:
    raw = subprocess.run(
        ["git", "-C", str(clone), "archive", "--format=tar", commit],
        check=True, capture_output=True,
    ).stdout
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        for member in tar.getmembers():
            if member.isfile():
                handle = tar.extractfile(member)
                assert handle is not None
                files[member.name] = handle.read()
            elif member.issym() or member.islnk():
                raise SystemExit(f"enlace en el commit, no soportado: {member.name}")
    return files


def manifest_lines(files: dict[str, bytes]) -> list[str]:
    return [f"{hashlib.sha256(files[p]).hexdigest()}  {p}" for p in sorted(files)]


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    clone = Path(argv[0]).resolve()
    commit, left_out = read_list()
    files = {p: b for p, b in archive(clone, commit).items() if not is_left_out(p, left_out)}
    for path, _ in sorted(files.items()):
        if path.split("/", 1)[0] in EMMA_FILES:
            raise SystemExit(f"el commit trae un fichero con nombre reservado de EMMA: {path}")

    # Borra lo que sobra (copiado antes y ya no pedido) sin tocar lo generado ni lo de EMMA.
    for existing in sorted(TARGET.rglob("*"), reverse=True):
        rel = existing.relative_to(TARGET).as_posix()
        if rel in EMMA_FILES or rel.split("/", 1)[0] in GENERATED_DIRS:
            continue
        if existing.is_file() and rel not in files:
            existing.unlink()
        elif existing.is_dir() and not any(existing.iterdir()):
            existing.rmdir()

    for path, data in files.items():
        dest = TARGET / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or dest.read_bytes() != data:
            dest.write_bytes(data)

    MANIFEST.write_text(
        f"# commit {commit}\n" + "\n".join(manifest_lines(files)) + "\n",
        encoding="utf-8", newline="\n",
    )
    fuera = ", ".join(left_out)
    print(f"marplanner/: {len(files)} ficheros del commit {commit[:7]}; fuera: {fuera}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
