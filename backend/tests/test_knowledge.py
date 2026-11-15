"""Buscar en la documentación (`kb` de Polaris) y exportar a PDF (`md_to_pdf_pro` de Polaris),
las dos tal cual desde la copia. Sin red.
"""

from __future__ import annotations

import datetime as dt
import io
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app import export, kb, polaris


def _text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)


def test_the_documentation_answers_with_its_file_and_section(client: TestClient) -> None:
    body = client.get("/api/kb", params={"q": "IEC 62304 clase B"}).json()
    assert body["available"] is True
    paths = [item["path"] for item in body["results"]]
    assert "compliance/software-safety-classification.md" in paths
    assert all(item["section"] and item["text"] for item in body["results"])


def test_the_index_is_rebuilt_only_when_the_documentation_changes() -> None:
    kb.refresh()
    assert kb.refresh()["rebuilt"] is False


def test_a_too_short_query_is_refused(client: TestClient) -> None:
    assert client.get("/api/kb", params={"q": "a"}).status_code == 422


def test_the_status_exports_to_pdf_with_emma_title_and_backend_text(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "arrhythmia", "days": 40})
    status = client.get("/api/status").json()
    response = client.get("/api/export/estado.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    reader = PdfReader(io.BytesIO(response.content))
    assert reader.metadata is not None and "EMMA" in str(reader.metadata.title)
    assert "Biopsia" not in str(reader.metadata.title)  # el título del caso de su autora no sale
    text = _text(response.content)
    assert "Apoyo a la decisión" in text
    alert = status["alerts"][0]
    assert f"{alert['domain']} · {alert['level']}" in text  # el apartado de la alerta, no la tabla


def test_dossier_and_chronicle_export_too(client: TestClient) -> None:
    for kind in ("dosier", "cronica"):
        response = client.get(f"/api/export/{kind}.pdf")
        assert response.status_code == 200 and response.content.startswith(b"%PDF")
    assert client.get("/api/export/otro.pdf").status_code == 422


def test_the_copy_is_restored_after_exporting() -> None:
    tool = polaris.load("md_to_pdf_pro")
    before, argv = tool.SimpleDocTemplate, list(sys.argv)
    export.to_pdf("# Prueba\n", "EMMA — prueba")
    assert tool.SimpleDocTemplate is before and sys.argv == argv


# --------------------------------------------------------------------------- #
# Búsqueda semántica (Polaris `kb_embed`, modelo e5-small en app/data/kb-model)
# --------------------------------------------------------------------------- #

QUERY = "who signs a risky decision twice"  # en inglés: los documentos están en castellano


def _finds_the_second_signature(found: dict[str, Any]) -> bool:
    return any("Segunda firma" in result["section"] for result in found["results"])


@pytest.mark.skipif(not (kb.MODEL / "model_qint8_avx512_vnni.onnx").is_file(),
                    reason="sin el modelo (scripts/install_kb_embed.py)")
def test_meaning_finds_what_words_do_not() -> None:
    found = kb.search(QUERY, k=3)
    assert found["semantic"] is True
    # Entre las tres primeras, no la primera a secas: el orden mezcla significado y palabras, y
    # el puesto exacto se mueve cuando crece la documentación indexada (pasó el 2026-10-09: bajó
    # al segundo sin que cambiara ni la sección ni la búsqueda). Lo que se prueba es la línea de
    # abajo: el significado la encuentra y las palabras solas no.
    assert _finds_the_second_signature(found)
    # Solo con palabras (BM25), esa sección no sale ni entre las seis primeras.
    tool = kb._tool()
    words_only = tool._retrieve_fts5(QUERY, 6, "internal", tool.DB)
    assert not any("Segunda firma" in title for _path, title, *_rest in words_only)


def test_without_the_model_it_falls_back_to_words(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Un índice hecho desde cero sin el modelo (como el de una instalación que aún no lo tiene).
    kb.search("IEC 62304 clase B")
    tool = kb._tool()
    (polaris.configure() / kb.CORPUS / ".emma-fingerprint").unlink(missing_ok=True)
    Path(tool.VEC).unlink(missing_ok=True)
    monkeypatch.setattr(kb, "MODEL", tmp_path / "sin-modelo")
    try:
        found = kb.search("IEC 62304 clase B")
        assert found["semantic"] is False and found["results"]
    finally:
        monkeypatch.undo()
    if (kb.MODEL / "model_qint8_avx512_vnni.onnx").is_file():
        # Con el modelo de vuelta, el índice se rehace con vectores: si no, seguiría sin ellos.
        assert _finds_the_second_signature(kb.search(QUERY, k=3))


# --------------------------------------------------------------------------- #
# Anotaciones de dolor en PDF (`/api/export/dolor.pdf`)
# --------------------------------------------------------------------------- #

WHEN = "2026-09-25T08:00:00+00:00"
KNEE = {"zone": "knee-left", "intensity": 3, "characters": ["sharp"]}
CHEST = {"zone": "chest", "intensity": 5, "characters": ["pressing"]}


def _pain(client: TestClient, *zones: dict[str, object], **extra: object) -> None:
    body = {"zones": list(zones), "reported_by": "cmdr", "effective": WHEN, **extra}
    assert client.post("/api/pain/reports", json=body).status_code == 201


def _flat(pdf: bytes) -> str:
    """El texto del PDF en una línea: reportlab parte las frases donde le cabe."""
    return " ".join(_text(pdf).split())


def test_pain_exports_to_pdf_with_what_the_ledger_holds(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "arrhythmia", "days": 40})
    _pain(client, KNEE, note="me molesta al flexionar")
    _pain(client, CHEST, note="aprieta al respirar hondo", note_origin="dictada-revisada")
    reports = client.get("/api/pain/reports").json()

    response = client.get("/api/export/dolor.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "emma-dolor-crew-01" in response.headers["content-disposition"]
    metadata = PdfReader(io.BytesIO(response.content)).metadata
    assert metadata is not None and "EMMA" in str(metadata.title)
    assert "Biopsia" not in str(metadata.title)  # el título del caso de su autora no sale
    text = _flat(response.content)
    assert "no prescripción ni diagnóstico" in text
    # Zona, tipo e intensidad con los nombres del catálogo, y cuándo en UTC y en día de misión.
    assert "Rodilla izquierda" in text and "Punzante" in text
    assert "Tórax" in text and "Opresivo" in text
    assert text.count("2026-09-25 08:00 UTC · ") == 2
    assert "Intensidad máxima: 3 de 10" in text and "Intensidad máxima: 5 de 10" in text
    # Solo el informe del pecho lleva la marca, con la frase y la nota de `app/pain/alarm.py`.
    assert reports[1]["discuss"]["reasons"] == ["opresión en el pecho"]
    assert text.count("Marca informativa, no una alerta") == 1
    assert "opresión en el pecho. Comentar con el médico de a bordo." in text
    # Las notas, literales, y la dictada declarada como transcripción de un modelo.
    assert "me molesta al flexionar" in text and "aprieta al respirar hondo" in text
    assert text.count("Nota escrita por quien informa") == 1
    assert text.count("la transcribió un modelo local") == 1
    assert text.index("la transcribió un modelo local") > text.index("me molesta al flexionar")
    # Procedencia: el asiento de cada informe y hasta dónde llegan los datos.
    for report in reports:
        assert f"asiento {report['ledger_index']} del ledger" in text
    assert "Estado de los datos: hasta el" in text


def test_a_dictated_note_is_never_presented_as_typed() -> None:
    assert "transcribió un modelo" in export._note_heading("dictada-revisada")
    assert "no la ha corregido ni verificado" in export._note_heading("dictada-revisada")
    assert "transcribió" not in export._note_heading("escrita")
    assert "sin verificar" in export._note_heading("otro-origen")


def test_no_pain_reports_is_said_not_invented(client: TestClient) -> None:
    # Sin lecturas del tripulante: lo mismo que el estado.
    assert client.get("/api/export/dolor.pdf").status_code == 404
    assert client.get("/api/export/estado.pdf").status_code == 404
    client.post("/api/simulate", params={"scenario": "arrhythmia", "days": 40})
    text = _flat(client.get("/api/export/dolor.pdf").content)
    assert "Sin anotaciones de dolor en el ledger." in text
    assert "Marca informativa" not in text and "Nota" not in text
    # Un informe sin zonas es un informe, no una ausencia.
    _pain(client)
    text = _flat(client.get("/api/export/dolor.pdf").content)
    assert "Informe sin zonas marcadas." in text and "Sin anotaciones" not in text


def test_ground_exports_only_the_pain_that_has_arrived(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "arrhythmia", "days": 40})
    _pain(client, KNEE)
    [first] = client.get("/api/pain/reports").json()
    _pain(client, CHEST)
    text = _flat(
        client.get("/api/export/dolor.pdf", params={"until": first["recorded"]}).content
    )
    assert "Rodilla izquierda" in text and "Tórax" not in text
    assert "Solo lo recibido hasta el corte" in text


def test_a_note_cannot_open_a_heading_or_a_table() -> None:
    report = {
        "effective": WHEN, "recorded": WHEN, "reported_by": "cmdr", "intensity": 3,
        "ledger_index": 7, "zones": [KNEE], "note": "uno\n# dos\n| tres |",
        "note_origin": "escrita",
    }
    markdown = export.pain_markdown(
        [report], "crew-01", dt.datetime.now(dt.UTC),
        {"as_of": WHEN, "as_of_basis": "prueba"}, dt.date(2026, 9, 1),
    )
    assert "> uno # dos | tres |" in markdown.splitlines()
    assert "UTC · día de misión 24" in markdown
    before_launch = export.pain_markdown(
        [report], "crew-01", dt.datetime.now(dt.UTC),
        {"as_of": WHEN, "as_of_basis": "prueba"}, dt.date(2026, 11, 1),
    )
    assert "UTC · antes del inicio de la misión" in before_launch
    assert "día de misión" not in before_launch


def test_the_copy_is_restored_after_exporting_pain(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "arrhythmia", "days": 40})
    tool = polaris.load("md_to_pdf_pro")
    before, argv = tool.SimpleDocTemplate, list(sys.argv)
    assert client.get("/api/export/dolor.pdf").status_code == 200
    assert tool.SimpleDocTemplate is before and sys.argv == argv
