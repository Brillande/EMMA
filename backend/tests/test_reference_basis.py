"""Sin rango de referencia no hay base: `reference_basis` es `None`, y hay rango <=> hay base.

Decisión del usuario (2026-10-20). Antes todo indicador heredaba `ReferenceBasis.OBSERVED` por
defecto, tuviera rango o no: `/api/indicators` y la huella de reglas decían "medido en población
sana" de una escala decidida por EMMA sin rango (`appetite-rating`) y de las analíticas, cuyo rango
lo trae el laboratorio en su informe. Aquí se fija, sin red:

- el catálogo no carga con rango sin base ni con base sin rango;
- `/api/indicators` y la huella dan `null` donde no hay rango, y la base donde lo hay;
- el motor solo distingue `guideline`, así que quitar la base a quien no tiene rango no mueve
  ningún veredicto (eso se midió aparte con los 9 escenarios y 4 tripulantes; aquí, el lector).
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.routes import new_store, reset_store
from app.core import versioning
from app.core.config import Settings, get_settings
from app.ingest.codes import (
    CATALOG,
    DESCRIPTIVE_ONLY,
    CodeSystem,
    Domain,
    ReferenceBasis,
    VitalCode,
)
from app.main import app


def _has_range(code: VitalCode) -> bool:
    return code.reference_low is not None or code.reference_high is not None


def _code(**overrides: object) -> VitalCode:
    fields: dict[str, object] = {
        "key": "prueba", "code": "prueba", "display": "prueba", "unit": "{score}",
        "system": CodeSystem.EMMA, "domain": Domain.BEHAVIORAL,
    }
    fields.update(overrides)
    return VitalCode(**fields)  # type: ignore[arg-type]


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def test_the_catalog_has_a_basis_exactly_where_it_has_a_range() -> None:
    for code in CATALOG.values():
        if _has_range(code):
            assert isinstance(code.reference_basis, ReferenceBasis), code.key
        else:
            assert code.reference_basis is None, code.key
    # El caso que destapó el hueco: una escala propia sin rango no se presenta como observada.
    assert CATALOG["appetite-rating"].reference_basis is None


def test_a_range_without_basis_does_not_load() -> None:
    with pytest.raises(ValueError, match="no declara su base"):
        _code(reference_low=0, reference_high=10)
    # Medio rango también es rango: ese extremo sale de algún sitio.
    with pytest.raises(ValueError, match="no declara su base"):
        _code(reference_low=1)


def test_a_basis_without_range_does_not_load() -> None:
    with pytest.raises(ValueError, match="sin rango de referencia"):
        _code(reference_basis=ReferenceBasis.OBSERVED)


def test_a_code_without_range_loads_without_basis() -> None:
    assert _code().reference_basis is None
    assert _code(reference_high=5, reference_basis=ReferenceBasis.DESIGN).reference_basis is (
        ReferenceBasis.DESIGN
    )


def test_the_api_says_null_where_there_is_no_range(client: TestClient) -> None:
    body = client.get("/api/indicators").json()
    by_key = {item["key"]: item for item in body["indicators"]}
    assert set(by_key) == set(CATALOG)
    for key, code in CATALOG.items():
        item = by_key[key]
        if _has_range(code):
            assert item["reference_basis"] == str(code.reference_basis), key
        else:
            # `null`, no el texto "None" ni una base por defecto.
            assert item["reference_basis"] is None, key
    assert by_key["appetite-rating"]["reference_basis"] is None
    assert by_key["heart-rate"]["reference_basis"] == "observed"


def test_the_rules_fingerprint_says_null_where_there_is_no_range() -> None:
    catalog = versioning.rules()["catalog"]
    for key, row in catalog.items():
        code = CATALOG[key]
        assert row[6] == (str(code.reference_basis) if _has_range(code) else None), key
    assert "None" not in catalog["appetite-rating"]
    # Lo descriptivo no entra en la huella: ni con base ni sin ella.
    assert not set(catalog) & DESCRIPTIVE_ONLY
