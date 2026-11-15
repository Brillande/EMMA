"""Sobre qué indicadores se ha medido la sensibilidad, en la matriz de riesgos (`GET /api/risks`).

Lo que vigilan estas pruebas: que lo publicado —qué indicador recibe un deterioro inyectado y
cuál— sea exactamente lo que construye el inyector (`validation/injection.py`), sin una segunda
lista que pueda divergir; que la fila remita a la validación externa sin copiar sus cifras; y que
el dominio sin ninguno lo diga. La referencia se construye aquí llamando a cada deterioro de
referencia, no leyendo la tabla que publica la matriz: si la tabla dejara de ser lo que se inyecta,
la prueba lo ve.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import risk_entity
from app.api import routes
from app.api.routes import new_store, reset_store
from app.core import versioning
from app.core.config import Settings, get_settings
from app.ingest.codes import Domain, evaluated_by_domain
from app.main import app
from app.text_guard import check
from app.validation import injection
from app.validation.injection import REFERENCE_INJECTIONS, Perturbation

REFERENCE = "compliance/external-validation.md"


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _risks(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/risks")
    assert response.status_code == 200
    risks: list[dict[str, Any]] = response.json()["risks"]
    return risks


def _risk(risks: list[dict[str, Any]], domain: Domain) -> dict[str, Any]:
    found: dict[str, Any] = next(item for item in risks if item["risk_id"] == str(domain))
    return found


def _injected() -> dict[str, list[tuple[str, str]]]:
    """Lo que inyecta cada deterioro de referencia, construido aquí: clave → (etiqueta, forma)."""
    onset = dt.datetime(2030, 1, 1, tzinfo=dt.UTC)
    found: dict[str, list[tuple[str, str]]] = {}
    for label, build in REFERENCE_INJECTIONS.items():
        built = build(onset)
        found.setdefault(built.key, []).append((label, str(built.kind)))
    return found


def test_each_indicator_says_whether_its_sensitivity_was_measured(client: TestClient) -> None:
    """Lo publicado por indicador es lo que inyecta el inyector, deterioro a deterioro; entre
    todos los riesgos sale cada clave inyectada una vez."""
    expected = _injected()
    seen: list[str] = []
    for item in _risks(client):
        measured = []
        for entry in item["indicators"]:
            injected = expected.get(entry["key"], [])
            assert entry["sensitivity_measured"] is bool(injected)
            assert [
                (row["label"], row["kind"]) for row in entry["sensitivity_injections"]
            ] == injected
            for row in entry["sensitivity_injections"]:
                assert row["kind_display"] == injection.PERTURBATION_DISPLAY[
                    Perturbation(row["kind"])
                ]
            if injected:
                measured.append(entry["key"])
        block = item["sensitivity"]
        assert [entry["key"] for entry in block["keys"]] == measured
        assert block["indicators"] == len(item["indicators"])
        for entry in block["keys"]:
            assert [(row["label"], row["kind"]) for row in entry["injections"]] == expected[
                entry["key"]
            ]
        seen.extend(measured)
    assert sorted(seen) == sorted(expected)
    assert list(injection.INJECTED_KEYS) == list(expected)


def test_the_injector_table_is_what_the_reference_injections_build() -> None:
    expected = _injected()
    table: dict[str, list[tuple[str, str]]] = {}
    for label, (key, kind) in injection.REFERENCE_TARGETS.items():
        table.setdefault(key, []).append((label, str(kind)))
    assert table == expected
    assert list(injection.REFERENCE_TARGETS) == list(REFERENCE_INJECTIONS)


def test_every_perturbation_has_its_word() -> None:
    assert set(injection.PERTURBATION_DISPLAY) == set(Perturbation)
    assert all(injection.PERTURBATION_DISPLAY.values())


def test_a_domain_with_injections_names_them_and_refers_to_the_validation(
    client: TestClient,
) -> None:
    row = _risk(_risks(client), Domain.CARDIOVASCULAR)
    block = row["sensitivity"]
    assert block["keys"] and block["empty"] is None
    assert block["reference"] == REFERENCE
    assert block["measures"] == injection.MEASURES
    assert block["basis"] == risk_entity.SENSITIVITY_BASIS
    statement = block["statement"]
    assert statement.startswith(
        f"Sensibilidad medida en {len(block['keys'])} de {len(row['indicators'])} indicadores"
    )
    for entry in block["keys"]:
        assert entry["display_es"] in statement
        for row_injection in entry["injections"]:
            assert row_injection["label"] in statement
    assert statement.endswith(f"Cifras en {REFERENCE}.")
    # Sin cifras de sensibilidad copiadas: ni una tasa en la frase.
    assert "%" not in statement


def test_a_domain_without_injections_says_so(client: TestClient) -> None:
    block = _risk(_risks(client), Domain.RADIATION)["sensitivity"]
    assert block["keys"] == []
    assert block["statement"] == block["empty"] == risk_entity.NO_SENSITIVITY
    assert block["measures"] is None
    assert block["reference"] == REFERENCE


def test_the_sensitivity_is_read_from_the_injector(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cambiar lo que se inyecta cambia lo publicado: no hay segunda copia."""
    monkeypatch.setattr(
        injection, "REFERENCE_TARGETS", {"deriva de prueba": ("body-weight", Perturbation.DRIFT)}
    )
    monkeypatch.setattr(injection, "INJECTED_KEYS", ("body-weight",))
    assert risk_entity.sensitivity(Domain.CARDIOVASCULAR)["keys"] == []
    block = risk_entity.sensitivity(Domain.BONE)
    assert [entry["key"] for entry in block["keys"]] == ["body-weight"]
    assert block["keys"][0]["injections"] == [
        {
            "label": "deriva de prueba",
            "kind": "drift",
            "kind_display": injection.PERTURBATION_DISPLAY[Perturbation.DRIFT],
        }
    ]
    assert block["statement"].startswith(
        f"Sensibilidad medida en 1 de {len(evaluated_by_domain(Domain.BONE))} "
    )
    assert "deriva de prueba" in block["statement"]
    payload = risk_entity.payload(routes.CURRENT_WINDOW)
    flagged = [
        entry["key"]
        for item in payload["risks"]
        for entry in item["indicators"]
        if entry["sensitivity_measured"]
    ]
    assert flagged == ["body-weight"]


def test_the_sensitivity_texts_pass_the_language_filter(client: TestClient) -> None:
    texts = [injection.MEASURES, risk_entity.SENSITIVITY_BASIS, risk_entity.NO_SENSITIVITY]
    texts += list(injection.PERTURBATION_DISPLAY.values())
    texts += [item["sensitivity"]["statement"] for item in _risks(client)]
    for text in texts:
        assert check(text) == [], text


def test_publishing_the_sensitivity_does_not_move_the_rules_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El inyector no decide nada del motor: vaciarlo no cambia la huella de las reglas (calculada
    de nuevo, no la de la caché de `rules_version`)."""
    before = versioning.fingerprint(versioning.rules())
    monkeypatch.setattr(injection, "REFERENCE_TARGETS", {})
    monkeypatch.setattr(injection, "INJECTED_KEYS", ())
    monkeypatch.setattr(injection, "MEASURES", "otra cosa")
    assert versioning.fingerprint(versioning.rules()) == before
    assert all(risk_entity.sensitivity(domain)["keys"] == [] for domain in Domain)
