"""Cada indicador del catálogo tiene familia de pictograma en la interfaz, y ninguna sobra.

La tabla vive en `frontend/src/lib/indicatorFamily.ts` (rediseño pictográfico, 2026-10-20):
cada clave del catálogo en una familia, cada familia un dibujo. Si el catálogo gana un indicador
y la tabla no, su nombre saldría sin pictograma o con uno supuesto; si la tabla nombra una clave
que el catálogo ya no tiene, describe algo que no existe. Como `test_display.py` con las unidades:
dos tablas, una por lado, y esta prueba dice si divergen.
"""

import re
from pathlib import Path

from app.ingest.codes import CATALOG

FRONTEND_TABLE = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "indicatorFamily.ts"
)


def _families() -> dict[str, list[str]]:
    source = FRONTEND_TABLE.read_text(encoding="utf-8")
    block = re.search(r"export const FAMILY_KEYS[^=]*=\s*\{(.*?)\n\};", source, re.S)
    assert block is not None, "no se encuentra FAMILY_KEYS en indicatorFamily.ts"
    families: dict[str, list[str]] = {}
    for name, body in re.findall(r'"?([a-z0-9-]+)"?:\s*\[(.*?)\]', block.group(1), re.S):
        families[name] = re.findall(r'"([^"]+)"', body)
    assert families, "FAMILY_KEYS no tiene familias"
    return families


def test_every_catalog_key_has_exactly_one_family() -> None:
    families = _families()
    listed = [key for keys in families.values() for key in keys]
    assert len(listed) == len(set(listed)), "una clave esta en dos familias"
    assert set(listed) == set(CATALOG), (
        f"sin familia: {sorted(set(CATALOG) - set(listed))}; "
        f"sobran: {sorted(set(listed) - set(CATALOG))}"
    )


def test_no_family_is_empty() -> None:
    for name, keys in _families().items():
        assert keys, f"la familia {name} no tiene ningun indicador"


def test_vitamin_d_shares_the_family_of_the_bone_minerals() -> None:
    """La vitamina D 25-OH (descriptiva, 2026-10-22) va con el calcio: el mismo dibujo, el hueso."""
    families = _families()
    family = next(name for name, keys in families.items() if "vitamin-d-25oh" in keys)
    assert family == "crystal"
    assert {"calcium", "phosphate", "ntx-telopeptide"} <= set(families[family])
