"""Analíticas escaneadas → observaciones: ninguna cifra leída entra hasta que una persona la
confirma, y entra por el ledger (invariante 4). Extractor de Polaris `biomarcadores` tal cual; OCR
simulado como en `test_reports.py`. Sin red.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes import CONSOLE_IDENTITY, UNIT_MAX_LENGTH, get_store, identity_for
from app.ingest.codes import LAB_REPORT_ONLY, CodeSystem, get
from app.ingest.fhir import observation
from app.reports import labs, ocr
from tests.test_reports import png, upload

LAB = """Hemoglobina 13,9 g/dL 12,0 - 16,0
Glucosa <70 mg/dL 70 - 110
Calcio 2,3 mmol/L 2,1 - 2,6
"""


@pytest.fixture
def report(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> int:
    fake = tmp_path / "tesseract.exe"
    fake.write_bytes(b"")
    monkeypatch.setattr(ocr, "find_tesseract", lambda configured=None: str(fake))
    monkeypatch.setattr(ocr, "version", lambda executable: "tesseract 5.5.0")
    monkeypatch.setattr(ocr, "ocr_image", lambda executable, image: (LAB, 95.0, 30))
    body = upload(client, png())
    assert body["lab_readings"] == 3
    index = body["ledger_index"]
    assert isinstance(index, int)
    return index


def _readings(client: TestClient) -> list[dict]:  # type: ignore[type-arg]
    [found] = client.get("/api/reports").json()
    readings: list[dict] = found["lab_readings"]["readings"]  # type: ignore[type-arg]
    return readings


def test_every_lab_key_has_a_catalogue_code_with_its_unit() -> None:
    for polaris_key, key in labs.LAB_KEYS.items():
        code = get(key)
        assert code.unit, polaris_key
        if code.system is CodeSystem.LOINC:
            assert code.code[0].isdigit() and "-" in code.code, key
    assert set(LAB_REPORT_ONLY) <= set(labs.LAB_KEYS.values())


def test_each_lab_indicator_has_one_spanish_name_the_one_its_reading_carries() -> None:
    # Un indicador de EMMA por analito de Polaris: con dos, su nombre dependería del orden.
    assert len(set(labs.LAB_KEYS.values())) == len(labs.LAB_KEYS)
    names = labs.names()
    assert set(names) == set(labs.LAB_KEYS.values())
    # El mismo que lleva la lectura extraída (también el del cociente derivado): la crónica
    # posvuelo nombra así el indicador (`timeline.py`).
    text = "Leucocitos 6,2 x10^3/uL\nLinfocitos 1,9 x10^3/uL\nUrea 40 mg/dL\nCreatinina 0,9 mg/dL"
    readings = labs.extract(text)["readings"]
    assert {item["key"] for item in readings} == {
        "leukocytes", "lymphocytes", "urea", "creatinine", "bun-creatinine-ratio"}
    for item in readings:
        assert names[item["key"]] == item["name"], item["key"]
    # Lo que no sale de una analítica no tiene nombre en español en EMMA: no se le inventa.
    assert "heart-rate" not in names


def test_readings_wait_for_a_person(client: TestClient, report: int) -> None:
    readings = _readings(client)
    assert [item["key"] for item in readings] == ["hemoglobin", "glucose", "calcium"]
    assert all(item["status"] == "por_confirmar" for item in readings)
    # Nada leído está en el análisis todavía.
    status = client.get("/api/status")
    assert status.status_code == 404 or "hemoglobin" not in status.json().get("latest", {})


def test_a_confirmed_reading_enters_signed_once(client: TestClient, report: int) -> None:
    confirm = {"reading_index": 0, "confirmed_by": "CMO", "effective_date": "2026-03-12"}
    response = client.post(f"/api/reports/{report}/labs/confirm", json=confirm)
    assert response.status_code == 201, response.text
    observation_index = response.json()["observation_index"]
    readings = _readings(client)
    assert readings[0]["status"] == "confirmada"
    assert readings[0]["confirmation"]["confirmed_by"] == "CMO"
    assert readings[0]["confirmation"]["observation_index"] == observation_index
    assert readings[1]["status"] == "por_confirmar"
    # Dos veces no: duplicaría la cifra en la serie.
    assert client.post(f"/api/reports/{report}/labs/confirm", json=confirm).status_code == 409
    audit = client.get("/api/audit").json()
    assert audit["integrity_ok"] is True, (audit["failed_index"], audit["failure_reason"])
    kinds = [entry["entry_type"] for entry in audit["entries"]]
    assert "lab-confirmation" in kinds and "vital-observation" in kinds


def test_an_unreliable_reading_needs_a_correction_in_the_catalogue_unit(
    client: TestClient, report: int
) -> None:
    url = f"/api/reports/{report}/labs/confirm"
    base = {"confirmed_by": "CMO", "effective_date": "2026-03-12"}
    # «<70» y calcio en mmol/L (otra familia): no se confirman tal cual.
    assert client.post(url, json={**base, "reading_index": 1}).status_code == 422
    assert client.post(url, json={**base, "reading_index": 2}).status_code == 422
    # Con la unidad equivocada tampoco: EMMA no convierte por su cuenta (invariante 2).
    wrong = {**base, "reading_index": 2, "value": 2.3, "unit": "mmol/L"}
    assert client.post(url, json=wrong).status_code == 422
    fixed = {**base, "reading_index": 2, "value": 9.2, "unit": get("calcium").unit}
    assert client.post(url, json=fixed).status_code == 201


def test_a_long_unit_is_refused_with_its_reason_in_spanish_not_pydantic_errors(
    client: TestClient, report: int
) -> None:
    """La unidad tenía `max_length=32` en el esquema: pasado, la lista de errores de Pydantic, en
    inglés. Ahora el tope de toda la API (`UNIT_MAX_LENGTH`) con el motivo de las demás vías, y
    sin escribir nada (decimoctava ronda, §5.38.9)."""
    url = f"/api/reports/{report}/labs/confirm"
    base = {"confirmed_by": "CMO", "effective_date": "2026-03-12", "reading_index": 2,
            "value": 9.2}
    before = len(client.get("/api/audit").json()["entries"])
    response = client.post(url, json={**base, "unit": "x" * (UNIT_MAX_LENGTH + 1)})
    assert response.status_code == 422
    assert response.json()["detail"] == (
        f"unidad de {UNIT_MAX_LENGTH + 1} caracteres para calcium: no se admite más de "
        f"{UNIT_MAX_LENGTH}; el catálogo define 'mg/dL'"
    )
    # Por debajo del tope, la comparación de siempre, con lo que puede hacer quien lee el papel.
    within = client.post(url, json={**base, "unit": "x" * 33})
    assert within.status_code == 422
    assert isinstance(within.json()["detail"], str)
    assert "convierte el valor leído en el papel" in within.json()["detail"]
    assert len(client.get("/api/audit").json()["entries"]) == before
    assert client.post(url, json={**base, "unit": "mg/dL"}).status_code == 201


def test_a_reading_needs_a_person_a_date_and_must_exist(client: TestClient, report: int) -> None:
    url = f"/api/reports/{report}/labs/confirm"
    assert client.post(url, json={"reading_index": 0, "confirmed_by": "123",
                                  "effective_date": "2026-03-12"}).status_code == 422
    # El informe simulado no trae fecha legible: hay que darla.
    assert client.post(url, json={"reading_index": 0, "confirmed_by": "CMO"}).status_code == 422
    assert client.post(url, json={"reading_index": 9, "confirmed_by": "CMO",
                                  "effective_date": "2026-03-12"}).status_code == 404
    missing = {"reading_index": 0, "confirmed_by": "CMO", "effective_date": "2026-03-12"}
    assert client.post("/api/reports/99999/labs/confirm", json=missing).status_code == 404


def test_a_lab_only_analyte_cannot_bypass_the_report(client: TestClient) -> None:
    key = sorted(LAB_REPORT_ONLY)[0]
    store = get_store()
    with pytest.raises(ValueError, match="analítica escaneada"):
        store.record_many(
            [observation(key, 1.0, dt.datetime(2026, 3, 12, tzinfo=dt.UTC), "crew-01", "x")],
            identity_for(CONSOLE_IDENTITY),
        )


def test_what_the_store_returns_is_a_copy_of_the_signed_entry(
    client: TestClient, report: int
) -> None:
    """Anotar un informe devuelto (como hace la lista de informes) no cambia su asiento."""
    store = get_store()
    [listed] = store.scanned_reports("crew-01")
    listed["lab_readings"]["readings"][0]["status"] = "manipulado"
    payload, _ = store.report_blob(report)
    payload["ocr"]["pages"].clear()
    assert client.get("/api/audit").json()["integrity_ok"] is True

