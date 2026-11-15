# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cada fichero de EMMA que usa o adapta Polaris lo dice en su cabecera, y dice la verdad.

Por qué existe: EMMA es AGPL porque incorpora Polaris, y la licencia pide (§5a) que cada fichero
con código suyo declare de dónde viene y qué se cambió. La regla estaba escrita en CLAUDE.md y se
cumplía a medias: adaptadores sin la línea SPDX, y cabeceras que citaban el commit que se copió
primero cuando el código ya llamaba a la copia de hoy. Un sha escrito a mano en veinte ficheros
caduca en silencio en cuanto la copia avanza.

El criterio, uno solo:
  * Quien LLAMA a la copia (`app.polaris`) lleva la línea SPDX y remite a `polaris/ADOPTADO.txt`,
    que es donde está el commit. No fija un sha.
  * Quien lleva código ADAPTADO a mano sí fija el sha exacto del que se adaptó, porque ese código
    no avanza con la copia. Son los de `ADAPTED`, uno a uno y con su motivo, y están en `NOTICE`.
  * Lo que `NOTICE` nombra como destino existe y lleva la línea SPDX.

Qué NO comprueba: que el texto de la cabecera describa bien lo que hace el cuerpo. Eso lo lee una
persona; aquí solo se vigila lo que se puede vigilar sin leer.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "backend" / "app" / "polaris"
SPDX_LINE = re.compile(r"(?:#|//) SPDX-License-Identifier: AGPL-3\.0-or-later")
# Lo que admite una línea de comentario; una carpeta o un JSON nombrados en NOTICE, no.
COMMENTABLE = {".py", ".ts", ".tsx", ".mjs"}

# El commit de Polaris que se copió primero: de él sale todo el código adaptado a mano.
FIRST_COPY = "7bf4725"
# Commits que ya no son la copia: se buscan aunque nada alrededor diga que son un commit. Al pasar
# la copia a otro commit, el que deja de serlo se añade aquí.
OLD_COMMITS = (FIRST_COPY, "e3b588d", "0e629e4")
OLD_MENTION = re.compile(r"\b(?:" + "|".join(OLD_COMMITS) + r")[0-9a-f]*\b")
# Un sha cualquiera, tal como se escribe en una cabecera: "@ 7bf47257", "commit e3b588d". Solo
# se lee así en ficheros que hablan de Polaris, y con una cifra al menos: "commit añadido" no.
COMMIT_MENTION = re.compile(r"(?:@\s*|\bcommit\s+)(?=[0-9a-f]*\d)([0-9a-f]{7,40})\b")

# Ficheros con código de Polaris ADAPTADO a mano: copiado y cambiado aquí, no llamado en la copia.
# Cada uno cita el sha del que procede. Quitar una entrada exige quitar el sha de su cabecera, es
# decir, haber pasado ese código a la copia.
ADAPTED = {
    # Léxicos y lógica de `tools/cotejo_invariante.py`; el original solo reconoce genes.
    "backend/app/interpret/cotejo.py": FIRST_COPY,
    # `segmenta()` y la exigencia de telemetría apagada de `tools/visor3d.py`.
    "backend/app/volumes/segment.py": FIRST_COPY,
    # `_fetch_pubmed` de `tools/tier_evidencia.py`, con httpx.
    "backend/scripts/grade_sources.py": FIRST_COPY,
    # El visor NiiVue de `tools/visor3d_web/main.js`, en React, para los presets sin visor suyo.
    "frontend/src/volumes/VolumeViewer.tsx": FIRST_COPY,
    # Mixtos: llaman a `visor3d` de la copia y además llevan `build()` (de `assets()`) y
    # `lesions()` (de `lesiones()`), que el original no deja llamar.
    "backend/app/volumes/assets.py": FIRST_COPY,
    "backend/app/volumes/geometry.py": FIRST_COPY,
    # Mixto: `clean_doi` va a la copia; `classify()` y las comprobaciones con httpx, adaptadas.
    "backend/app/evidence/citations.py": FIRST_COPY,
    # Mixto: limpieza y entidades van a la copia; `numbers()` y `check()`, adaptadas.
    "backend/app/evidence/support.py": FIRST_COPY,
    # Mixto: las listas completas se leen de la copia; las que bloquean (`_OVERCLAIM`, `_ACTION`,
    # `_DELIBERATE`) son subconjuntos escritos a mano.
    "backend/app/text_guard.py": FIRST_COPY,
    # `sign_draft` y `countersign_draft`: patrones de `salida.py` y `decision_alto_riesgo.py`.
    "backend/app/core/storage.py": FIRST_COPY,
}
# Sin código adaptado: cuenta en qué commit dejó de hacer falta el suyo. Es historia, no un origen.
HISTORY = {
    "backend/app/reports/deid.py": (FIRST_COPY, "e3b588d"),
}


def adopted_commit() -> str:
    lines = (REPO / "polaris" / "ADOPTADO.txt").read_text(encoding="utf-8").splitlines()
    [commit] = [line.split()[1] for line in lines if line.startswith("commit ")]
    return commit


def name(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def python_sources() -> list[Path]:
    backend = REPO / "backend"
    found = [*(backend / "app").rglob("*.py"), *(backend / "scripts").rglob("*.py")]
    return sorted(path for path in found if "__pycache__" not in path.parts)


def sources() -> list[Path]:
    frontend = REPO / "frontend"
    interface = [*(frontend / "src").rglob("*.ts*"), *(frontend / "scripts").glob("*.mjs")]
    return [*python_sources(), *sorted(interface)]


def has_spdx(path: Path) -> bool:
    first_line = read(path).split("\n", 1)[0].rstrip("\r")
    return SPDX_LINE.fullmatch(first_line) is not None


def _is_bridge(module: str | None) -> bool:
    return module is not None and (module == "app.polaris" or module.startswith("app.polaris."))


def _reaches_the_bridge(node: ast.AST) -> bool:
    """Un `import` de `app.polaris` (o de algo suyo) o una llamada a `polaris.load(`."""
    if isinstance(node, ast.ImportFrom):
        names = {alias.name for alias in node.names}
        from_app = node.module == "app" and "polaris" in names
        return node.level == 0 and (from_app or _is_bridge(node.module))
    if isinstance(node, ast.Import):
        return any(_is_bridge(alias.name) for alias in node.names)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        target = node.func.value
        return node.func.attr == "load" and isinstance(target, ast.Name) and target.id == "polaris"
    return False


def uses_the_copy(path: Path) -> bool:
    """¿Es el puente (`app/polaris/`, único punto de entrada a la copia) o pasa por él?"""
    if BRIDGE in path.parents:
        return True
    return any(_reaches_the_bridge(node) for node in ast.walk(ast.parse(read(path))))


def callers() -> list[Path]:
    return [path for path in python_sources() if uses_the_copy(path)]


def fixed_commits(text: str) -> set[str]:
    """Los shas de Polaris que un texto fija, recortados a siete caracteres."""
    found = {match.group(0)[:7] for match in OLD_MENTION.finditer(text)}
    if "polaris" in text.lower():
        found |= {sha[:7] for sha in COMMIT_MENTION.findall(text)}
    return found


def allowed_commits(rel: str) -> set[str]:
    return {ADAPTED[rel]} if rel in ADAPTED else set(HISTORY.get(rel, ()))


def notice_destinations() -> list[str]:
    """Las rutas de la columna "Destino en EMMA" de cada tabla de `NOTICE`."""
    lines = (REPO / "NOTICE").read_text(encoding="utf-8").splitlines()
    found: set[str] = set()
    for start, header in enumerate(lines):
        if "Destino en EMMA" not in header:
            continue
        for row in lines[start + 1:]:
            if not row.strip():
                break
            found.update(re.findall(r"\b(?:backend|frontend)/[\w./-]*\w/?", row))
    return sorted(found)


def test_the_search_finds_the_callers() -> None:
    """Si la búsqueda dejara de encontrar, las pruebas de abajo pasarían sin mirar nada."""
    found = {name(path) for path in callers()}
    assert {
        "backend/app/polaris/__init__.py", "backend/app/polaris/compat/fcntl.py",
        "backend/app/core/egress.py", "backend/app/voice.py", "backend/scripts/mutants.py",
    } <= found
    # `app.api.polaris` es una ruta de la API, no el puente: importarla no es usar la copia.
    assert "backend/app/main.py" not in found


def test_every_file_that_calls_the_copy_carries_the_license_line() -> None:
    missing = [name(path) for path in callers() if not has_spdx(path)]
    assert not missing, f"sin SPDX en la primera línea: {missing}"


def test_every_file_with_adapted_code_carries_the_license_line() -> None:
    missing = [rel for rel in ADAPTED if not has_spdx(REPO / rel)]
    assert not missing, f"sin SPDX en la primera línea: {missing}"


def test_no_file_pins_a_commit_other_than_the_adopted_one() -> None:
    """Quien solo llama a la copia remite a `ADOPTADO.txt`; un sha a mano caduca."""
    adopted = adopted_commit()[:7]
    stale: dict[str, list[str]] = {}
    for path in sources():
        rel = name(path)
        extra = fixed_commits(read(path)) - {adopted} - allowed_commits(rel)
        if extra:
            stale[rel] = sorted(extra)
    assert not stale, f"fijan un commit de Polaris que no es el adoptado ({adopted}): {stale}"


def test_every_declared_exception_is_still_needed() -> None:
    """Una excepción que ya no hace falta es una puerta abierta: se quita de la lista."""
    unused: dict[str, list[str]] = {}
    for rel in (*ADAPTED, *HISTORY):
        extra = allowed_commits(rel) - fixed_commits(read(REPO / rel))
        if extra:
            unused[rel] = sorted(extra)
    assert not unused, f"ya no citan ese commit: {unused}"


def test_the_detector_reads_the_ways_a_commit_is_written() -> None:
    assert fixed_commits("Polaris `tools/visor3d.py` @ 7bf47257, AGPL") == {"7bf4725"}
    assert fixed_commits("copia de Polaris (commit 1a2b3c4). Hace") == {"1a2b3c4"}
    assert fixed_commits("visto en 7bf47257f563fa0942a0b73d820191a125be92a2") == {"7bf4725"}
    harmless = "Polaris: commit en `polaris/ADOPTADO.txt`; commit añadido; PMID 7659438; e230024"
    assert fixed_commits(harmless) == set()
    # El sha de otro proyecto, en un fichero que no habla de Polaris, no es asunto de esta prueba.
    assert fixed_commits("modelo e5-small, commit 614241f622f5") == set()


def test_adapted_code_is_declared_in_notice() -> None:
    """CLAUDE.md: "si portas algo más, añádelo también a `NOTICE`". Y el sha, el que NOTICE dice."""
    notice = (REPO / "NOTICE").read_text(encoding="utf-8")
    undeclared = sorted(set(ADAPTED) - set(notice_destinations()))
    assert not undeclared, f"código adaptado que NOTICE no nombra como destino: {undeclared}"
    assert re.search(rf"\b{FIRST_COPY}[0-9a-f]*\b", notice), "NOTICE no nombra el commit de origen"


@pytest.mark.parametrize("destination", notice_destinations())
def test_every_destination_in_notice_exists_and_carries_the_license_line(destination: str) -> None:
    path = REPO / destination
    assert path.exists(), f"NOTICE nombra {destination} y no existe"
    if path.suffix in COMMENTABLE:
        assert has_spdx(path), f"{destination} está en NOTICE y no lleva SPDX"
