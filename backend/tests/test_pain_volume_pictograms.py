"""Cada carácter del dolor y cada fase de contraste tienen pictograma, y ninguno sobra.

Las tablas viven en `frontend/src/pain/characters.ts` y `frontend/src/volumes/marks.ts` (rediseño
pictográfico, unidad P9, 2026-10-20): cada clave del backend con el dibujo que acompaña a su
palabra. Si el catálogo gana un carácter o el vocabulario una fase y la tabla no, su palabra
saldría con el dibujo de «desconocido»; si la tabla nombra una clave que el backend ya no tiene,
describe algo que no existe. Como `test_indicator_families.py`: dos tablas, una por lado, y esta
prueba dice si divergen.
"""

import re
from pathlib import Path

from app.pain.catalog import CHARACTERS
from app.volumes.contrast_phase import PHASES

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _keys(path: Path, table: str) -> list[str]:
    """Las claves de una tabla `const <table> ... = { clave: mark(...), ... };` de TypeScript."""
    source = path.read_text(encoding="utf-8")
    block = re.search(rf"const {table}\b[^=]*=\s*\{{(.*?)\n\}};", source, re.S)
    assert block is not None, f"no se encuentra {table} en {path.name}"
    keys = re.findall(r'^\s+"?([a-z0-9-]+)"?:\s*mark\(', block.group(1), re.M)
    assert keys, f"{table} no tiene claves"
    return keys


def test_every_pain_character_has_a_pictogram() -> None:
    keys = _keys(FRONTEND / "pain" / "characters.ts", "CHARACTER_MARKS")
    assert len(keys) == len(set(keys)), "un carácter está dos veces"
    assert set(keys) == set(CHARACTERS), (
        f"sin dibujo: {sorted(set(CHARACTERS) - set(keys))}; "
        f"sobran: {sorted(set(keys) - set(CHARACTERS))}"
    )


def test_every_contrast_phase_has_a_pictogram() -> None:
    keys = _keys(FRONTEND / "volumes" / "marks.ts", "PHASE_MARKS")
    assert len(keys) == len(set(keys)), "una fase está dos veces"
    assert set(keys) == set(PHASES), (
        f"sin dibujo: {sorted(set(PHASES) - set(keys))}; sobran: {sorted(set(keys) - set(PHASES))}"
    )
