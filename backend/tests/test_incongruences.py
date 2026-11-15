"""Analíticas de la misma extracción que no dicen lo mismo (`incongruencias_caso` de Polaris)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import polaris
from app.reports import incongruences, ocr
from tests.test_reports import png, upload


def _report(index: int, day: str | None, **values: float) -> dict:  # type: ignore[type-arg]
    readings = [{"key": key, "value": value, "comparator": None} for key, value in values.items()]
    return {"ledger_index": index, "lab_readings": {"date": day, "readings": readings}}


def test_the_same_draw_with_different_values_is_flagged() -> None:
    found = incongruences.find([
        _report(1, "2026-03-12", glucose=92, creatinine=0.9),
        _report(2, "2026-03-12", glucose=92, creatinine=1.3),
    ])
    assert [item["key"] for item in found] == ["creatinine"]
    assert {r["report"] for r in found[0]["readings"]} == {"informe:1", "informe:2"}


def test_different_days_are_physiology_not_a_contradiction() -> None:
    assert incongruences.find([
        _report(1, "2026-03-12", creatinine=0.9), _report(2, "2026-03-20", creatinine=1.5),
    ]) == []


def test_rounding_between_labs_is_not_an_incongruence() -> None:
    # Con la comparación original de Polaris, «92» frente a «92.4» saldría distinto.
    assert polaris.load("incongruencias_caso")._distintos("92", "92.4") is True
    assert incongruences.find([
        _report(1, "2026-03-12", glucose=92), _report(2, "2026-03-12", glucose=92.4),
    ]) == []


def test_undated_reports_are_counted_not_compared() -> None:
    reports = [_report(1, None, glucose=92), _report(2, None, glucose=150)]
    assert incongruences.find(reports) == [] and incongruences.undated(reports) == 2


def test_the_copy_is_restored() -> None:
    tool = polaris.load("incongruencias_caso")
    before = (tool.muestra_de, tool.extraer, tool._distintos)
    incongruences.find([_report(1, "2026-03-12", glucose=92), _report(2, "2026-03-12", glucose=99)])
    after = (tool.muestra_de, tool.extraer, tool._distintos)
    assert all(now is then for now, then in zip(after, before, strict=True))


def test_the_endpoint_crosses_uploaded_reports(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "tesseract.exe"
    fake.write_bytes(b"")
    monkeypatch.setattr(ocr, "find_tesseract", lambda configured=None: str(fake))
    monkeypatch.setattr(ocr, "version", lambda executable: "tesseract 5.5.0")
    for value in ("13,9", "11,2"):
        # El formato de fecha que reconoce `biomarcadores.fecha_de` (el de los laboratorios de
        # su autora); con otro, el informe queda sin fecha y no se cruza.
        text = f"Fecha Recepción: 12/03/2026\nHemoglobina {value} g/dL 12,0 - 16,0\n"
        monkeypatch.setattr(ocr, "ocr_image", lambda executable, image, t=text: (t, 95.0, 10))
        upload(client, png())
    body = client.get("/api/reports/incongruences").json()
    assert [item["key"] for item in body["incongruences"]] == ["hemoglobin"]
