"""Cada parámetro de cabina, módulo y sistema del hábitat tiene pictograma en la interfaz.

Y ninguno sobra. Las tablas viven en `frontend/src/habitat/pictograms.ts` (rediseño
pictográfico, unidad de hábitat, 2026-10-20): una clave del backend por dibujo. Si
`environment/habitat.py` gana un
parámetro, `habitat_modules.json` un módulo o `habitat_systems.json` un sistema y la tabla no,
su nombre saldría con el punto de «desconocido»; si la tabla nombra una clave que el backend ya no
tiene, describe algo que no existe. Como `test_indicator_families.py` con el catálogo: dos tablas,
una por lado, y esta prueba dice si divergen. Se lee desde los objetos de Python, no desde el
fuente, para que una clave escrita de otra forma no pase desapercibida.
"""

import re
from pathlib import Path

from app.environment.habitat import DISPLAY_ONLY, MODULES, PARAMETERS
from app.environment.systems import SYSTEMS

FRONTEND_TABLE = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "habitat" / "pictograms.ts"
)


def _table(name: str) -> dict[str, str]:
    source = FRONTEND_TABLE.read_text(encoding="utf-8")
    block = re.search(rf"export const {name}[^=]*=\s*\{{(.*?)\n\}};", source, re.S)
    assert block is not None, f"no se encuentra {name} en pictograms.ts"
    table = dict(re.findall(r'"?([a-z0-9-]+)"?:\s*"([a-z0-9-]+)"', block.group(1)))
    assert table, f"{name} esta vacia"
    return table


def _check(name: str, expected: set[str]) -> dict[str, str]:
    table = _table(name)
    assert set(table) == expected, (
        f"{name}: sin pictograma: {sorted(expected - set(table))}; "
        f"sobran: {sorted(set(table) - expected)}"
    )
    return table


def test_every_cabin_parameter_has_its_own_pictogram() -> None:
    table = _check("PARAMETER_PICTOGRAMS", set(PARAMETERS) | set(DISPLAY_ONLY))
    assert len(set(table.values())) == len(table), "dos parametros comparten dibujo"


def test_every_module_has_its_own_pictogram() -> None:
    table = _check("MODULE_PICTOGRAMS", set(MODULES))
    assert len(set(table.values())) == len(table), "dos modulos comparten dibujo"


def test_every_system_has_its_own_pictogram() -> None:
    table = _check("SYSTEM_PICTOGRAMS", set(SYSTEMS))
    assert len(set(table.values())) == len(table), "dos sistemas comparten dibujo"
