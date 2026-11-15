"""Contrato contra la API real de OSDR. Con red: marcada `live` (invariante 3).

    .venv/Scripts/python.exe -m pytest -m live tests/test_osdr_data_live.py

Comprueba que la API sigue dando la forma que lee `evidence/osdr_data.py` y que la ficha de cada
estudio de OSDR que EMMA cita coincide con ella. Una discrepancia hace fallar la prueba con los dos
valores: es un hallazgo que revisar con la fuente delante, no algo que corregir a ciegas.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings
from app.evidence import osdr_data


@pytest.mark.live
def test_osdr_api_contract_and_fichas(tmp_path: Path) -> None:
    payload = osdr_data.studies(osdr_data.OsdrDataClient(Settings(cache_dir=tmp_path)))
    views = {view["id"]: view for view in payload["studies"]}
    unavailable = [view["id"] for view in views.values() if not view["available"]]
    assert not unavailable, unavailable
    osd_288 = views["osd-288"]["osdr"]
    assert osd_288["organisms"] == ["Mus musculus"] and osd_288["population"] == "animal"
    disagreements = [
        f"{view['id']} {check['label']}: EMMA {check['emma']!r} / OSDR {check['osdr']!r}"
        for view in views.values() for check in view["checks"] if check["verdict"] == "mismatch"
    ]
    assert not disagreements, "\n".join(disagreements)
