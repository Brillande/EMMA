# SPDX-License-Identifier: AGPL-3.0-or-later
"""Escribe `polaris/ESTADO.md`: qué herramientas copiadas de Polaris cargan en esta máquina.

Por qué existe: la copia es literal, así que lo que no funcione aquí (Unix, dependencias
opcionales) no se arregla tocándola; se declara, y los cambios se deciden aparte. Este fichero es
esa declaración, sacada de `app.polaris.inventory()` y no escrita a mano. Lo que el inventario no
importa a propósito (`polaris.NOT_IMPORTED`) va en su propia tabla, con su motivo: no es un fallo
de carga.

Lo mismo con el pegamento de Windows: qué pone EMMA desde fuera se lee de la carpeta
`app/polaris/compat/` (cada módulo, con la primera línea de su docstring), no de una frase. La
frase que había solo nombraba `compat/fcntl.py` cuando la carpeta ya tenía más módulos
(2026-10-08); `tests/test_polaris_texts.py` falla si la lista y la carpeta dejan de coincidir.

Licencia y origen (AGPL §5a): este fichero no contiene código de Polaris. Lista, por
`app.polaris.inventory`, las herramientas de la copia literal `polaris/tools/` (commit en
`polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the Protocol»).
"""

from __future__ import annotations

import ast
import platform
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import polaris  # noqa: E402

COMPAT = Path(polaris.__file__).resolve().parent / "compat"
COMPAT_NAME = "backend/app/polaris/compat"


def compat_lines() -> list[str]:
    """Una línea por módulo de `compat/`: su ruta y lo que su propio docstring dice que es."""
    lines = []
    for path in sorted(COMPAT.glob("*.py")):
        doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
        said = doc.strip().splitlines()[0].strip() if doc.strip() else "sin descripción."
        lines.append(f"- `{COMPAT_NAME}/{path.name}`: {said}")
    return lines


def skipped_lines(skipped: Sequence[polaris.ToolStatus]) -> list[str]:
    """La tabla de las que el inventario no importa (`polaris.NOT_IMPORTED`), si hay alguna.

    Va aparte de la de «no cargan» porque dice otra cosa: de estas no se sabe si cargarían, se ha
    decidido no importarlas para contarlas.
    """
    if not skipped:
        return []
    return [
        f"**No se importan para hacer este inventario: {len(skipped)}.** Hacen algo solo con "
        "importarse (la lista es",
        "`NOT_IMPORTED`, en `backend/app/polaris/__init__.py`), así que no se sabe si cargarían:",
        "",
        "| Herramienta | Por qué no se importa |",
        "|---|---|",
        *[f"| `{status.name}` | {status.reason} |" for status in skipped],
        "",
    ]


def render(statuses: Sequence[polaris.ToolStatus]) -> str:
    loads = [status for status in statuses if status.loads]
    fails = [status for status in statuses if status.imported and not status.loads]
    skipped = [status for status in statuses if not status.imported]
    lines = [
        "# Estado de la copia de Polaris en esta máquina",
        "",
        f"Generado por `backend/scripts/polaris_estado.py` en {platform.system()} "
        f"{platform.release()}, Python {platform.python_version()}. No se edita a mano.",
        "",
        f"**{len(loads)} de {len(statuses)} herramientas cargan.** Las que no, y por qué:",
        "",
        "| Herramienta | Motivo |",
        "|---|---|",
        *[f"| `{status.name}` | {status.reason} |" for status in fails],
        "",
        *skipped_lines(skipped),
        "Las herramientas no se modifican (la copia es literal): lo que falta aquí se instala o",
        "se decide aparte (`docs/polaris-divergencias.md`). Lo que a la copia le falta en Windows",
        f"lo pone EMMA desde fuera de ella, en `{COMPAT_NAME}/`:",
        "",
        *compat_lines(),
        "",
        "Cargan: " + ", ".join(f"`{status.name}`" for status in loads) + ".",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    statuses = polaris.inventory()
    text = render(statuses)
    (polaris.root() / "ESTADO.md").write_text(text, encoding="utf-8", newline="\n")
    loading = sum(1 for status in statuses if status.loads)
    skipped = sum(1 for status in statuses if not status.imported)
    print(f"{loading}/{len(statuses)} cargan; {skipped} no se importan")


if __name__ == "__main__":
    main()
