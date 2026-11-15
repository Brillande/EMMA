"""Copia Polaris literal a `polaris/` según `polaris/ADOPTADO.txt`.

Por qué existe: la regla del proyecto es que adoptar Polaris es **copiarlo tal cual** y decidir los
cambios después (la primera adopción del visor 3D se "adaptó" al portarla y quedó peor que el
original). Copiar a mano cientos de ficheros que se importan entre sí es la forma segura de dejarse
uno o de retocar otro sin querer. Este script calcula el cierre de imports de las herramientas
pedidas, elige las pruebas de Polaris que solo usan lo copiado, copia cada fichero byte a byte y
escribe el manifiesto de huellas que vigila `tests/test_polaris_copy.py`. Es idempotente: pasarlo
dos veces no cambia nada.

Uso:
    .venv/Scripts/python.exe scripts/polaris_sync.py <copia de Polaris>
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TARGET = REPO / "polaris"
LIST = TARGET / "ADOPTADO.txt"
MANIFEST = TARGET / "MANIFEST.sha256"
CHANGES = TARGET / "CAMBIOS.json"
# Lo que no forma parte de la copia: instalables, cachés y los ficheros propios de EMMA.
SKIP_DIRS = {"node_modules", "__pycache__", "state", "dist"}
EMMA_FILES = {
    "ADOPTADO.txt", "MANIFEST.sha256", "ORIGEN.md", "ESTADO.md", "PRUEBAS.md", "CAMBIOS.json",
}
# Lo que se saca del commit. `tests/`, `evals/` y `docs/` solo si ADOPTADO.txt los pide.
ARCHIVED = ("tools", "tests", "evals", "docs")


@dataclass
class Adopted:
    commit: str = ""
    roots: list[str] = field(default_factory=list)
    data: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    tests: bool = False
    named_tests: list[str] = field(default_factory=list)
    cards: bool = False


def read_list() -> Adopted:
    adopted = Adopted()
    for line in LIST.read_text(encoding="utf-8").splitlines():
        parts = line.split("#", 1)[0].split()
        if not parts:
            continue
        if len(parts) != 2:
            # Antes se saltaba en silencio: un `root a b` o un `root` suelto dejaba esa
            # herramienta sin copiar, y `sync` la borraba de la copia como si sobrara.
            raise SystemExit(f"ADOPTADO.txt: entrada desconocida (mal formada) {line!r}")
        kind, value = parts
        if kind == "commit":
            adopted.commit = value
        elif kind == "root":
            adopted.roots.append(value)
        elif kind == "data":
            adopted.data.append(value)
        elif kind == "extra":
            adopted.extra.append(value)
        elif kind == "tests" and value == "auto":
            adopted.tests = True
        elif kind == "test":
            adopted.named_tests.append(value)
        elif kind == "fichas" and value == "auto":
            adopted.cards = True
        else:
            raise SystemExit(f"ADOPTADO.txt: entrada desconocida {line!r}")
    if not adopted.commit:
        raise SystemExit("ADOPTADO.txt no declara el commit de origen")
    return adopted


def imported_roots(source: str) -> set[str]:
    """Los módulos de primer nivel que un fuente importa, también dentro de sus funciones.

    Con el árbol sintáctico y no con una expresión regular: la que había solo veía el primer nombre
    de `import a, b`, así que una herramienta importada en segundo lugar se habría quedado fuera
    del cierre sin avisar, y la copia habría fallado al importarla.
    """
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def imports_of(path: Path) -> set[str]:
    return imported_roots(path.read_text(encoding="utf-8"))


def closure(tools: Path, roots: list[str]) -> set[str]:
    """Los módulos de `tools/` que hacen falta para importar las raíces (imports directos)."""
    local = {path.stem for path in tools.glob("*.py")}
    missing = [root for root in roots if root not in local]
    if missing:
        raise SystemExit(f"no existen en Polaris: {missing}")
    seen: set[str] = set()
    pending = list(roots)
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        pending.extend(m for m in imports_of(tools / f"{name}.py") if m in local and m not in seen)
    return seen


def _importable(name: str) -> bool:
    try:
        return name in sys.stdlib_module_names or find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def eligible_tests(source: Path, modules: set[str]) -> list[str]:
    """Pruebas de Polaris que solo usan lo copiado.

    Una prueba entra si cada módulo que importa es de la biblioteca estándar, está instalado, es
    una herramienta copiada o un ayudante de `tests/`, y si cada herramienta que nombra como
    `x.py` está copiada. Las que importan algo de fuera (los ganchos de `.claude/` de su autora,
    herramientas sin copiar) se quedan fuera: fallarían por lo que falta, no por lo que prueban.
    """
    tools = {path.stem for path in (source / "tools").glob("*.py")}
    helpers = {path.stem for path in (source / "tests").glob("*.py")
               if not path.name.startswith("test_")}
    chosen = []
    for path in sorted((source / "tests").glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        named = {m for m in re.findall(r"[\"'/]([\w_]+)\.py[\"']", text) if m in tools}
        used = imports_of(path)
        if not (named | (used & tools)):
            continue  # no prueba ninguna herramienta
        if (named | (used & tools)) - modules:
            continue
        if any(m not in tools and m not in helpers and not _importable(m) for m in used):
            continue
        chosen.append(path.name)
    return chosen


def named_tests(source: Path, names: list[str]) -> list[str]:
    """Pruebas pedidas por su nombre en `ADOPTADO.txt` (`test <fichero>`).

    `eligible_tests` reconoce una prueba por las herramientas `x.py` que nombra entre comillas. Se
    le escapan las que prueban algo copiado que no es eso: un `.js` del visor web, una lista de
    módulos importados en un subproceso, o el árbol entero. Esas se piden a mano, una a una.
    """
    missing = [name for name in names if not (source / "tests" / name).is_file()]
    if missing:
        raise SystemExit(f"no existen en Polaris: {missing}")
    return names


def test_support(source: Path, tests: list[str], modules: set[str]) -> list[Path]:
    """Ayudantes, fixtures y campañas de mutantes que acompañan a las pruebas elegidas."""
    root = source / "tests"
    text = "\n".join((root / name).read_text(encoding="utf-8") for name in tests)
    out = [path.relative_to(source) for path in sorted(root.glob("*.py"))
           if not path.name.startswith("test_")]
    for path in sorted((root / "fixtures").rglob("*")):
        if path.is_file() and path.name in text:
            out.append(path.relative_to(source))
    for path in sorted((root / "mutantes").glob("*.json")):
        target = Path(json.loads(path.read_text(encoding="utf-8")).get("objetivo", "")).stem
        if target in modules:
            out.append(path.relative_to(source))
    return out


def cards_for(source: Path, copied: list[Path]) -> list[Path]:
    """La ficha de Polaris (`tools/fichas/<pieza>.json`) de cada herramienta copiada, y la lista
    de las heredadas. Solo de lo copiado: las de lo que no se adopta no explican nada aquí."""
    cards = source / "tools" / "fichas"
    out = [
        Path("tools") / "fichas" / f"{path.name}.json"
        for path in copied
        if path.parent == Path("tools") and (cards / f"{path.name}.json").is_file()
    ]
    if (cards / "_heredadas.txt").is_file():
        out.append(Path("tools") / "fichas" / "_heredadas.txt")
    return out


def files_of(source: Path, adopted: Adopted) -> tuple[list[Path], set[str], list[str]]:
    """Rutas relativas a la raíz de Polaris de todo lo que se copia."""
    tools = source / "tools"
    modules = closure(tools, adopted.roots)
    out = [Path("tools") / f"{name}.py" for name in sorted(modules)]
    for entry in [f"tools/{d}" for d in adopted.data] + adopted.extra:
        path = source / entry
        if path.is_file():
            out.append(Path(entry))
        elif path.is_dir():
            out.extend(
                item.relative_to(source) for item in sorted(path.rglob("*"))
                if item.is_file() and not SKIP_DIRS.intersection(item.relative_to(source).parts)
            )
        else:
            raise SystemExit(f"no existe en Polaris: {entry}")
    tests = eligible_tests(source, modules) if adopted.tests else []
    tests = sorted({*tests, *named_tests(source, adopted.named_tests)})
    if tests:
        out.extend(Path("tests") / name for name in tests)
        out.extend(test_support(source, tests, modules))
    if adopted.cards:
        out.extend(cards_for(source, out))
    return out, modules, tests


def extract(repo: Path, commit: str, into: Path, extra: list[str]) -> Path:
    """Las carpetas de Polaris tal como están en el commit, sacadas de los objetos de git.

    No se lee la copia de trabajo, y `git archive` va con `core.autocrlf=false`: en Windows ese
    ajuste convierte a CRLF (también al archivar) y la copia dejaría de ser byte a byte el
    original (pasó con la primera copia del visor web).
    """
    # Además de las carpetas, lo que `extra` pida de la raíz (LICENSE, NOTICE, CITATION.cff…).
    paths = [*ARCHIVED, *sorted({e.split("/")[0] for e in extra} - set(ARCHIVED))]
    tar = subprocess.run(
        ["git", "-C", str(repo), "-c", "core.autocrlf=false",
         "archive", "--format=tar", commit, *paths],
        capture_output=True, check=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as archive:
        archive.extractall(into, filter="data")
    return into


def decided_changes() -> dict[str, list[dict[str, str]]]:
    """Los cambios que el usuario decidió hacer a la copia (`polaris/CAMBIOS.json`, AGPL §5a)."""
    if not CHANGES.is_file():
        return {}
    entries = json.loads(CHANGES.read_text(encoding="utf-8"))
    for entry in entries:
        if not all(entry.get(key) for key in ("ruta", "fecha", "motivo", "reemplazos")):
            raise SystemExit(f"CAMBIOS.json: falta ruta, fecha, motivo o reemplazos en {entry}")
    return {entry["ruta"]: entry["reemplazos"] for entry in entries}


def apply_changes(target: Path, replacements: list[dict[str, str]]) -> None:
    """Cada `viejo` tiene que estar una sola vez: si Polaris cambia, se nota, no se adivina."""
    text = target.read_bytes().decode("utf-8")
    for item in replacements:
        count = text.count(item["viejo"])
        if count != 1:
            raise SystemExit(f"{target.name}: el texto a cambiar aparece {count} veces: "
                             f"{item['viejo'][:80]!r}")
        text = text.replace(item["viejo"], item["nuevo"])
    target.write_bytes(text.encode("utf-8"))


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    adopted = read_list()
    with tempfile.TemporaryDirectory() as scratch:
        source = extract(Path(sys.argv[1]).resolve(), adopted.commit, Path(scratch), adopted.extra)
        sync(source, adopted)


def sync(source: Path, adopted: Adopted) -> None:
    wanted, modules, tests = files_of(source, adopted)

    # Lo que sobra de una copia anterior se quita (salvo los ficheros de EMMA e instalables).
    wanted_set = {path.as_posix() for path in wanted}
    for path in sorted(TARGET.rglob("*"), reverse=True):
        rel = path.relative_to(TARGET)
        if SKIP_DIRS.intersection(rel.parts) or rel.as_posix() in EMMA_FILES:
            continue
        if path.is_file() and rel.as_posix() not in wanted_set:
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()

    changes = decided_changes()
    unknown = set(changes) - wanted_set
    if unknown:
        raise SystemExit(f"CAMBIOS.json cambia ficheros que no se copian: {sorted(unknown)}")
    lines = [f"# Polaris {adopted.commit}: copia literal; los cambios decididos, en CAMBIOS.json"]
    for rel in wanted:
        target = TARGET / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / rel, target)
        original = hashlib.sha256(target.read_bytes()).hexdigest()
        if rel.as_posix() in changes:
            apply_changes(target, changes[rel.as_posix()])
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            lines.append(f"{digest}  {rel.as_posix()}  # cambiado; original {original}")
        else:
            lines.append(f"{original}  {rel.as_posix()}")
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    extra = sorted(modules - set(adopted.roots))
    print(f"{len(wanted)} ficheros: {len(modules)} módulos, {len(tests)} pruebas")
    print(f"arrastrados por imports: {extra}")


if __name__ == "__main__":
    main()
