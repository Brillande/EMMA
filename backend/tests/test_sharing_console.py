"""Qué se comparte y qué no: lo que la tabla dice de la interfaz, contra los ficheros del frontend.

Aparte de `test_sharing.py` porque lee `frontend/`, que la campaña de mutantes no copia. Dos
comprobaciones:

- cada fichero de la consola que cita una fila existe y lleva el trozo citado (el `audio: false`
  de la cámara, el `localStorage` de las preferencias…): si alguien lo quita, la fila miente;
- cada panel que una fila dice que la consola de Tierra no monta no se alcanza desde
  `ground/GroundConsole.tsx` siguiendo sus `import` relativos. Es lo que la consola de Tierra
  pide, no lo que el backend deja pedir: eso la tabla lo dice en su límite.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from app import sharing

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "frontend" / "src"
GROUND = SRC / "ground" / "GroundConsole.tsx"
# `import … from "./x"`, `export … from "./x"` e `import("./x")`: solo los relativos, que son el
# código de EMMA (los paquetes de `node_modules` no montan paneles de EMMA).
_IMPORT = re.compile(
    r"""(?:import|export)\b[^'"]*?\bfrom\s*['"](\.[^'"]+)['"]"""
    r"""|import\(\s*['"](\.[^'"]+)['"]\s*\)"""
)


def _resolve(origin: Path, spec: str) -> Path | None:
    base = origin.parent / spec
    for candidate in (base, Path(f"{base}.ts"), Path(f"{base}.tsx"), base / "index.ts"):
        if candidate.is_file():
            return candidate.resolve()
    return None


def reachable(entry: Path) -> set[Path]:
    seen: set[Path] = set()
    pending = [entry.resolve()]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        for match in _IMPORT.finditer(current.read_text(encoding="utf-8")):
            found = _resolve(current, match.group(1) or match.group(2))
            if found is not None:
                pending.append(found)
    return seen


def test_the_walk_finds_what_the_ground_console_does_mount() -> None:
    """Sin esto, un recorrido roto daría por «no montado» cualquier panel."""
    seen = reachable(GROUND)
    for mounted in ("ground/AuditPanel.tsx", "imaging/ImagingHistory.tsx", "lib/crew.ts"):
        assert (SRC / mounted).resolve() in seen, mounted


@pytest.mark.parametrize(
    "cited",
    [entry for row in sharing.read()["items"] for entry in row["console"]],
    ids=lambda entry: f"{entry['file']}:{entry['contains'][:30]}",
)
def test_every_cited_console_file_says_what_the_row_relies_on(cited: dict[str, Any]) -> None:
    source = (REPO / cited["file"]).read_text(encoding="utf-8")
    assert cited["contains"] in source


@pytest.mark.parametrize(
    "panel", [path for row in sharing.read()["items"] for path in row["ground_absent"]]
)
def test_a_panel_ground_does_not_mount_is_not_reached_from_its_console(panel: str) -> None:
    target = REPO / panel
    assert target.is_file(), panel
    assert target.resolve() not in reachable(GROUND)
