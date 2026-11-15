"""El dosier de evidencia de EMMA con las reglas de Polaris: esquema cerrado, sin contradicciones,
"alta" solo con fuente y frescura. Sin red.
"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from app import polaris
from app.evidence import dossier

# El «hoy» de la prueba, fijo para que salga lo mismo cualquier día. Tiene que caer después de la
# última consulta guardada (`retrieved` de `evidence_tiers.json`: una pieza confirmada en el futuro
# es NO_VERIFICABLE y bloquea) y antes de que caduque la revisión más antigua (las de 2026-09-26,
# con `TTL_DAYS`). Era 2026-10-01; la decimoctava ronda (§5.38.20) gradúa con
# `scripts/grade_sources.py` el 2026-10-26 y lo mueve al 2026-11-01, con margen para que el cierre
# de la ronda vuelva a correr el guion. Correrlo después de esa fecha obliga a moverlo otra vez.
NOW = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)


def test_emma_evidence_is_a_deliverable_dossier_today() -> None:
    result = dossier.evaluate(dossier.pieces(), NOW)
    assert result["deliverable"], result["blocked"][:5]
    assert result["pieces"] >= 70


def test_polaris_canary_is_never_deliverable() -> None:
    """El canario de `guardian_evals` (dos piezas vivas con el mismo id) verifica al verificador."""
    canary = polaris.load("guardian_evals")._canario(NOW)
    assert not dossier.evaluate(canary, NOW)["deliverable"]


def test_a_review_older_than_its_validity_blocks() -> None:
    later = NOW + dt.timedelta(days=dossier.TTL_DAYS * 2)
    result = dossier.evaluate(dossier.pieces(), later)
    assert not result["deliverable"] and result["by_state"].get("CADUCADO")


def test_an_unknown_field_or_high_confidence_without_source_blocks() -> None:
    [piece] = dossier.pieces()[:1]
    assert not dossier.evaluate([{**piece, "inventado": 1}], NOW)["deliverable"]
    assert not dossier.evaluate([{**piece, "confianza": "alta", "fuentes": []}], NOW)["deliverable"]


def test_the_api_reports_the_dossier(client: TestClient) -> None:
    body = client.get("/api/dossier").json()
    assert body["pieces"] >= 70 and "deliverable" in body
