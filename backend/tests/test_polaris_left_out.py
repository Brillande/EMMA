# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lo que EMMA no copia de Polaris está declarado por su nombre, y no se contradice con la copia.

Por qué existe: `polaris/ADOPTADO.txt` despachaba lo no copiado con «las demás herramientas: red,
nube, macOS…». Desde la octava ronda cada herramienta que queda fuera lleva su línea en el bloque
«NO copiado». Una lista escrita a mano junto a una copia que avanza se contradice sola: basta
copiar una herramienta más y olvidar quitarla de «fuera» para que el fichero que viaja en el
instalador diga dos cosas de la misma herramienta.

Aquí se vigila lo que se ve sin salir del repositorio: que ninguna herramienta copiada figure
como no copiada, que ninguna se nombre dos veces y que el bloque siga siendo solo comentarios.
Que TODA herramienta de Polaris esté en uno de los dos lados necesita un clon de Polaris, que no
viaja con EMMA ni cabe en una suite sin red: eso lo hace `scripts/polaris_left_out.py`, a mano,
al poner la copia al día. De ese guion aquí solo se prueba que su cuadre avisa cuando debe.

Licencia y origen (AGPL §5a): este fichero no contiene código de Polaris. Lee los nombres de la
copia literal `polaris/tools/` (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la
autora de Polaris, «Beyond the Protocol»).
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType

BACKEND = Path(__file__).resolve().parents[1]
POLARIS = BACKEND.parent / "polaris"


def _load() -> ModuleType:
    """`scripts/` no es un paquete: el guion se carga por su ruta."""
    spec = importlib.util.spec_from_file_location(
        "polaris_left_out", BACKEND / "scripts" / "polaris_left_out.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # `dataclass` busca el módulo por su nombre
    spec.loader.exec_module(module)
    return module


left_out = _load()


def adopted_text() -> str:
    return (POLARIS / "ADOPTADO.txt").read_text(encoding="utf-8")


def copied_tools() -> set[str]:
    return {path.stem for path in (POLARIS / "tools").glob("*.py")}


def test_no_copied_tool_is_also_declared_as_left_out() -> None:
    named = left_out.named(adopted_text())
    assert named, "el bloque «NO copiado» no nombra ninguna herramienta: ¿cambió su formato?"
    both = sorted(copied_tools().intersection(named))
    assert not both, f"copiadas y a la vez declaradas fuera en ADOPTADO.txt: {both}"


def test_every_left_out_tool_is_named_only_once() -> None:
    times = Counter(left_out.named(adopted_text()))
    repeated = sorted(name for name, count in times.items() if count > 1)
    assert not repeated, f"nombradas más de una vez en el bloque «NO copiado»: {repeated}"


def test_the_left_out_block_is_only_comments_and_drops_the_catch_all() -> None:
    """El bloque viaja en el instalador y lo lee `polaris_sync.py`: una línea sin `#` sería una
    orden de copia, o un error al sincronizar."""
    block = left_out.block(adopted_text())
    orders = [line for line in block.splitlines() if line.strip() and not line.startswith("#")]
    assert not orders, f"líneas del bloque «NO copiado» que no son comentario: {orders}"
    assert "las demás herramientas" not in block, "vuelve la frase genérica: nómbralas una a una"


def test_the_reckoning_reports_what_does_not_add_up() -> None:
    """El cuadre del guion, sin clon: con un Polaris inventado, cada desajuste sale por su lado."""
    text = "\n".join(
        [
            "commit abc",
            "root kb",
            "",
            "# NO copiado, por decisión del usuario:",
            "#   launchd/, hooks/ y githooks/   fontanería",
            "#   interfaces.sh                  guion de shell",
            "#   pipeline       una carpeta: aquí arriba no se leen herramientas",
            "#",
            "# Herramientas NO copiadas, por su nombre.",
            "# [nube] Cerebros",
            "#   chatgpt        cliente de OpenAI",
            "#                  sigue en otra línea, que no es una herramienta",
            "#   kb             copiada y nombrada",
            "#   chatgpt        otra vez",
            "#   ya_no_existe   Polaris la quitó",
        ]
    )
    upstream = {
        "kb.py", "chatgpt.py", "grok.py", "fonts",
        "launchd", "hooks", "githooks", "interfaces.sh", "interfaces", "config",
    }
    report = left_out.check(upstream, {"kb.py", "fonts"}, text)

    assert report.undeclared == ["grok"]
    assert report.both == ["kb"]
    assert report.stale == ["ya_no_existe"]
    assert report.repeated == ["chatgpt"]
    # `interfaces` no vale por `interfaces.sh`; `hooks` sí está, y no solo dentro de `githooks`.
    assert report.unmentioned == ["config", "interfaces"]
    assert not report.clean


def test_the_reckoning_is_clean_when_everything_is_on_one_side() -> None:
    text = "\n".join(
        [
            "# NO copiado:",
            "#   config/   personas reales",
            "# Herramientas NO copiadas, por su nombre.",
            "#   chatgpt   cliente de OpenAI",
        ]
    )
    report = left_out.check({"kb.py", "chatgpt.py", "config"}, {"kb.py"}, text)
    assert report.clean
