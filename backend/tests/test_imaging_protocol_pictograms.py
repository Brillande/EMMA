"""Cada protocolo ecográfico tiene pictograma en la interfaz, y ninguno sobra.

La tabla vive en `frontend/src/imaging/protocols.ts` (rediseño pictográfico, 2026-10-20): cada
clave de `PROTOCOLS` con su dibujo. Si el registro gana un protocolo y la tabla no, su nombre
saldría en cinco sitios (selector, lista de estudios, fantomas, ejemplos, tabla de Tierra) con la
marca de «desconocido» sin que ninguna prueba lo dijera; si la tabla nombra una clave que el
registro ya no tiene, describe algo que no existe. Como `test_indicator_families.py` con las
familias: dos tablas, una por lado, y esta prueba dice si divergen.
"""

import re
from pathlib import Path

from app.imaging.protocols import PROTOCOLS

FRONTEND_TABLE = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "imaging" / "protocols.ts"
)


def _pictograms() -> dict[str, str]:
    source = FRONTEND_TABLE.read_text(encoding="utf-8")
    block = re.search(r"export const PROTOCOL_PICTOGRAMS[^=]*=\s*\{(.*?)\n\};", source, re.S)
    assert block is not None, "no se encuentra PROTOCOL_PICTOGRAMS en protocols.ts"
    body = re.sub(r"//[^\n]*", "", block.group(1))
    table = dict(re.findall(r'"?([a-z0-9-]+)"?:\s*"([a-z0-9-]+)"', body))
    assert table, "PROTOCOL_PICTOGRAMS no tiene protocolos"
    return table


def test_every_protocol_has_a_pictogram_and_none_is_spare() -> None:
    table = _pictograms()
    assert set(table) == set(PROTOCOLS), (
        f"sin pictograma: {sorted(set(PROTOCOLS) - set(table))}; "
        f"sobran: {sorted(set(table) - set(PROTOCOLS))}"
    )


def test_no_two_protocols_share_a_pictogram() -> None:
    table = _pictograms()
    assert len(set(table.values())) == len(table), "dos protocolos con el mismo dibujo"
