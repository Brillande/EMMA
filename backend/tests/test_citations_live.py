# SPDX-License-Identifier: AGPL-3.0-or-later
"""Toda cita de EMMA existe en su registro. Con red: marcada `live` (invariante 3).

    .venv/Scripts/python.exe -m pytest -m live tests/test_citations_live.py

Barre todo el código de `backend/app`, el manifiesto de ecografías de ejemplo, el README y la
documentación de cumplimiento. Una cita que el registro confirma que no existe hace fallar la
prueba; una que no se pudo comprobar (red caída) no acusa, se informa.

Licencia y origen (AGPL §5a): este fichero no contiene código de Polaris. Ejerce contra los
registros reales `app/evidence/citations.py`, que declara en su cabecera qué llama de la copia
(`polaris/tools/verifica_citas.py`) y qué sigue adaptado a mano.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.evidence import links
from app.evidence.citations import NOT_FOUND, find_identifiers, verify
from app.imaging.protocols import PROTOCOLS

ROOT = Path(__file__).resolve().parents[2]


def cited() -> set[tuple[str, str]]:
    texts = [source for protocol in PROTOCOLS.values() for source in protocol.sources]
    texts += [repr(value) for value in vars(links).values()]
    patterns = (
        "README.md", "compliance/*.md", "backend/app/**/*.py",
        "backend/app/data/ultrasound_samples/*.json",
    )
    for pattern in patterns:
        texts += [path.read_text(encoding="utf-8") for path in ROOT.glob(pattern)]
    return set().union(*(find_identifiers(text) for text in texts))


@pytest.mark.live
def test_every_citation_in_emma_exists() -> None:
    identifiers = cited()
    assert identifiers
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        verdicts = verify(client, identifiers, pause=0.5)
    fabricated = [v for v in verdicts if v.status == NOT_FOUND]
    assert not fabricated, "\n".join(f"{v.kind} {v.identifier}: {v.detail}" for v in fabricated)
