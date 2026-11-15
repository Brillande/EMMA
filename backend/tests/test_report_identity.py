"""¿El informe es de este tripulante? `identidad_paciente` de Polaris, con la identidad de EMMA.

Sin red ni OCR real: el texto de la página se simula como en `test_reports.py`.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.reports import identity, ocr
from app.reports.identity import Declared
from tests.test_reports import REPORT, png, upload

MARIA = Declared("María José", "Pérez Gómez", dt.date(1985, 4, 3))
LUCIA = Declared("Lucía", "Pérez Gómez", dt.date(1990, 1, 1))


def test_the_report_of_this_crew_member_matches() -> None:
    result = identity.check(REPORT, MARIA)
    assert result["verdict"] == "coincide" and result["usable"] is True


def test_the_report_of_someone_else_is_not_used_and_not_repeated() -> None:
    result = identity.check(REPORT, LUCIA)  # mismo apellido, otra persona: no basta
    assert result["verdict"] == "otro_paciente" and result["usable"] is False
    assert "María" not in result["explanation"] and "1985" not in result["explanation"]


def test_without_a_declared_identity_nothing_is_certified() -> None:
    result = identity.check(REPORT, None)
    assert result["verdict"] == "sin_identidad" and result["usable"] is True


def test_the_upload_records_whose_report_it_is(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "tesseract.exe"
    fake.write_bytes(b"")
    monkeypatch.setattr(ocr, "find_tesseract", lambda configured=None: str(fake))
    monkeypatch.setattr(ocr, "version", lambda executable: "tesseract 5.5.0")
    monkeypatch.setattr(ocr, "ocr_image", lambda executable, image: (REPORT, 91.0, 40))
    declared = {
        "given_name": "Lucía", "surnames": "Pérez Gómez", "birth_date": "1990-01-01",
        "declared_by": "CMO",
    }
    assert client.post("/api/crew/identity", json=declared).status_code == 201
    assert client.get("/api/crew/identity").json()["declared"] is True
    upload(client, png())
    [report] = client.get("/api/reports").json()
    assert report["identity"]["verdict"] == "otro_paciente"
    assert report["identity"]["usable"] is False


def test_if_the_report_names_the_crew_member_elsewhere_it_is_ambiguous_not_foreign() -> None:
    """Regla de Polaris: si el documento la nombra en alguna parte, se usa con aviso."""
    ana = Declared("Ana", "Pérez Gómez", dt.date(1990, 1, 1))  # "Dra. Ana López" firma el informe
    assert identity.check(REPORT, ana)["verdict"] == "ambiguo"
