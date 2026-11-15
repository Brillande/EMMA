"""Contrato con NTRS de verdad. Con red: marcado `live` (invariante 3).

    .venv/Scripts/python.exe -m pytest -m live tests/test_ntrs_live.py

Sale por la puerta de EMMA (`core/egress.py`, propósito `citations`), como la aplicación.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings
from app.evidence import ntrs, registry
from app.evidence.citations import EXISTS, NOT_IN_NTRS

# Fichas cuyo número NTRS no tiene hoy, con lo que se vio (spike del 2026-11-11). No se acusan:
# se declaran, y un número nuevo que desaparezca hace fallar la prueba para que alguien mire.
KNOWN_NOT_IN_NTRS = {
    # Cita «NTRS 20230009091», el número que imprime la portada del PDF de junio de 2023 de
    # nasa.gov («NF-1676 20230009091»), que es el documento leído y citado. NTRS no tiene ficha
    # pública con ese número (404; la búsqueda, 0 resultados; comprobado el 2026-11-11) y no consta
    # si existió y se retiró. La revisión anterior, de agosto de 2022, sí está: 20210013701.
    "nasa-hrp-roi-iss-facilities-2023",
}


@pytest.mark.live
def test_the_earlier_revision_of_the_roi_overview_is_in_ntrs(client: ntrs.NtrsClient) -> None:
    """La ficha de 2023 remite a la revisión de 2022 en NTRS; si desaparece, hay que decirlo."""
    result = client.lookup("20210013701")
    assert result.status == EXISTS, result.detail
    assert result.record is not None
    assert result.record.title == (
        "HRP Research Operations and Integration (ROI) ISS Facilities Overview"
    )


@pytest.mark.live
def test_every_known_discrepancy_with_ntrs_is_still_the_one_explained(
    client: ntrs.NtrsClient,
) -> None:
    """Las diferencias revisadas siguen igual; una nueva sale como «difiere», no se esconde."""
    summary = ntrs.check_all(client, network=True)
    explained = set(summary["with_explained_differences"])
    assert explained == set(ntrs.EXPLAINED_DIFFERENCES), explained
    assert summary["with_differences"] == [], summary["with_differences"]


@pytest.fixture
def client(tmp_path: Path) -> ntrs.NtrsClient:
    return ntrs.NtrsClient(Settings(cache_dir=tmp_path, offline=False))


@pytest.mark.live
def test_the_ntrs_record_keeps_its_shape(client: ntrs.NtrsClient) -> None:
    result = client.lookup("20170004345")
    assert result.status == EXISTS, result.detail
    assert result.record is not None
    fields = ntrs.compare(registry.get("ntrs-20170004345"), result.record)
    assert {field["state"] for field in fields.values()} == {ntrs.MATCH}


@pytest.mark.live
def test_an_unknown_number_is_not_in_ntrs(client: ntrs.NtrsClient) -> None:
    assert client.lookup("20999999999").status == NOT_IN_NTRS


@pytest.mark.live
def test_every_ntrs_reference_of_emma_is_in_ntrs(client: ntrs.NtrsClient) -> None:
    summary = ntrs.check_all(client, network=True)
    missing = {
        item["ref_id"] for item in summary["references"] if item["status"] != EXISTS
    }
    assert missing <= KNOWN_NOT_IN_NTRS, missing
