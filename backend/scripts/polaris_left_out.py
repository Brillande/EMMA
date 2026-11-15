# SPDX-License-Identifier: AGPL-3.0-or-later
"""Comprueba que cada herramienta de Polaris está o copiada o declarada fuera por su nombre.

Por qué existe: durante siete rondas, lo que EMMA no copiaba de Polaris lo cubría una frase de
`polaris/ADOPTADO.txt` («las demás herramientas: red, nube, macOS…»). Una frase así no se puede
contrastar: una herramienta nueva de Polaris quedaba «fuera» sin que nadie la hubiera mirado, y
una local y útil se perdía entre las de nube. Desde la octava ronda cada herramienta no copiada
lleva su línea en el bloque «NO copiado», y este guion es quien lo cuadra contra Polaris.

Hay dos comprobaciones y solo una cabe en la suite:
  * que ninguna herramienta copiada figure a la vez como no copiada, y que ninguna se nombre dos
    veces, se ve con lo que hay en el repositorio: `tests/test_polaris_left_out.py`;
  * que TODA herramienta de Polaris esté en uno de los dos lados necesita el árbol de Polaris en
    el commit adoptado, y el clon no viaja con EMMA. Por eso es un guion y no una prueba: se pasa
    a mano al poner la copia al día, junto a `polaris_sync.py`.

Uso:
    .venv/Scripts/python.exe scripts/polaris_left_out.py <clon de Polaris>

Qué NO comprueba: que el motivo escrito junto a cada nombre sea cierto. Es lectura de la
docstring de cada herramienta, hecha por una persona; aquí solo se cuadran los nombres.

Licencia y origen (AGPL §5a): este fichero no contiene código de Polaris. Lee los nombres de
`tools/` de un clon suyo y los compara con la copia literal `polaris/tools/` (commit en
`polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the Protocol»).
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TARGET = REPO / "polaris"
LIST = TARGET / "ADOPTADO.txt"

# Dónde empieza el bloque entero y dónde su parte de herramientas, una por línea.
BLOCK_MARK = "# NO copiado"
TOOLS_MARK = "# Herramientas NO copiadas, por su nombre"
# `#   nombre   qué es`: tres espacios, el nombre del módulo y al menos dos espacios antes del
# texto. Las cabeceras de grupo (`# [nube] …`) y las líneas de continuación (más sangría) no casan.
TOOL_LINE = re.compile(r"^#   ([A-Za-z_][A-Za-z0-9_]*) {2,}\S")


def block(text: str) -> str:
    """El bloque «NO copiado» de `ADOPTADO.txt`, desde su marca hasta el final del fichero."""
    start = re.search(rf"^{re.escape(BLOCK_MARK)}", text, re.MULTILINE)
    if start is None:
        raise SystemExit(f"ADOPTADO.txt no lleva el bloque {BLOCK_MARK!r}")
    return text[start.start() :]


def named(text: str) -> list[str]:
    """Las herramientas que `ADOPTADO.txt` declara no copiadas, en su orden y con repeticiones."""
    lines = block(text).splitlines()
    starts = [index for index, line in enumerate(lines) if line.startswith(TOOLS_MARK)]
    if not starts:
        raise SystemExit(f"ADOPTADO.txt no lleva la parte {TOOLS_MARK!r}")
    found = (TOOL_LINE.match(line) for line in lines[starts[0] + 1 :])
    return [match.group(1) for match in found if match]


def mentions(text: str, entry: str) -> bool:
    """¿Nombra el bloque esta carpeta o fichero, como palabra entera y no dentro de otra?

    `hooks` no vale por `githooks`, ni `interfaces` por `interfaces.sh`.
    """
    whole = rf"(?<![\w.-]){re.escape(entry)}(?![\w-]|\.\w)"
    return re.search(whole, block(text)) is not None


@dataclass
class Report:
    """Lo que no cuadra entre Polaris, la copia y el bloque «NO copiado»."""

    undeclared: list[str] = field(default_factory=list)  # ni copiada ni nombrada
    both: list[str] = field(default_factory=list)  # copiada y además nombrada como fuera
    stale: list[str] = field(default_factory=list)  # nombrada, pero Polaris ya no la tiene
    repeated: list[str] = field(default_factory=list)  # nombrada más de una vez
    unmentioned: list[str] = field(default_factory=list)  # carpeta o fichero sin nombrar

    @property
    def clean(self) -> bool:
        return not (
            self.undeclared or self.both or self.stale or self.repeated or self.unmentioned
        )


def check(upstream: set[str], copied: set[str], text: str) -> Report:
    """Cuadra las entradas de `tools/` de Polaris con las copiadas y con el bloque.

    `upstream` y `copied` son nombres de primer nivel de `tools/` (`kb.py`, `fonts`). Los módulos
    `.py` se exigen uno a uno en la parte de herramientas; el resto (carpetas, guiones de shell,
    datos) basta con que el bloque lo nombre.
    """
    names = named(text)
    declared = set(names)
    tools = {entry[:-3] for entry in upstream if entry.endswith(".py")}
    copied_tools = {entry[:-3] for entry in copied if entry.endswith(".py")}
    others = {entry for entry in upstream - copied if not entry.endswith(".py")}
    return Report(
        undeclared=sorted(tools - copied_tools - declared),
        both=sorted(copied_tools & declared),
        stale=sorted(declared - tools),
        repeated=sorted(name for name, times in Counter(names).items() if times > 1),
        unmentioned=sorted(entry for entry in others if not mentions(text, entry)),
    )


def adopted_commit(text: str) -> str:
    commits = [line.split()[1] for line in text.splitlines() if line.startswith("commit ")]
    if len(commits) != 1:
        raise SystemExit("ADOPTADO.txt no declara un único commit de origen")
    return commits[0]


def upstream_entries(clone: Path, commit: str) -> set[str]:
    """Los nombres de primer nivel de `tools/` en ese commit del clon (solo lee objetos de git)."""
    listed = subprocess.run(
        ["git", "-C", str(clone), "ls-tree", "--name-only", commit, "tools/"],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if listed.returncode != 0:
        raise SystemExit(f"el clon no tiene el commit {commit}: {listed.stderr.strip()}")
    return {line.removeprefix("tools/") for line in listed.stdout.splitlines() if line}


def copied_entries() -> set[str]:
    return {path.name for path in (TARGET / "tools").iterdir() if path.name != "__pycache__"}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    text = LIST.read_text(encoding="utf-8")
    commit = adopted_commit(text)
    upstream = upstream_entries(Path(sys.argv[1]).resolve(), commit)
    copied = copied_entries()
    report = check(upstream, copied, text)
    tools = sum(entry.endswith(".py") for entry in upstream)
    print(
        f"Polaris {commit[:7]}: {tools} herramientas; {sum(e.endswith('.py') for e in copied)} "
        f"copiadas, {len(set(named(text)))} declaradas fuera por su nombre"
    )
    problems = (
        ("ni copiadas ni nombradas", report.undeclared),
        ("copiadas y a la vez nombradas como no copiadas", report.both),
        ("nombradas, pero Polaris no las tiene en ese commit", report.stale),
        ("nombradas más de una vez", report.repeated),
        ("carpetas o ficheros de tools/ sin copiar y sin nombrar", report.unmentioned),
    )
    for label, items in problems:
        if items:
            print(f"  {label}: {', '.join(items)}")
    if not report.clean:
        raise SystemExit(1)
    print("  todo cuadra")


if __name__ == "__main__":
    main()
