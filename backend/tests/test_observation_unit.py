"""La unidad en el alta manual, y el contrato de §5 de la especificación en FHIR R4.

La especificación del equipo (§5) pide «un esquema canónico de observación con unidades y
procedencia explícitas», y la invariante 2 dice que la unidad sigue a la propiedad LOINC. La vía
FHIR ya rechazaba una unidad ajena al catálogo; el alta manual (`POST /api/observations`) no tenía
campo de unidad y una cifra en nmol/L entraba como si fuera ng/mL. Estas pruebas fijan la regla
(`compliance/record-integrity.md` §3.14 quater): unidad opcional; distinta, 422 sin asiento y sin
conversión; ausente, la del catálogo y la respuesta lo dice. Y comparan con el código la tabla de
ese apartado, campo de §5 → elemento FHIR → dónde lo pone EMMA → cómo lo llama la ingesta (la
correspondencia que aplica el adaptador de §5, `api/spec5.py`).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Iterator
from enum import Enum
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.routes import get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.core.storage import _to_payload
from app.environment.habitat import parameter as habitat_parameter
from app.evidence import registry
from app.ingest.codes import get
from app.ingest.fhir import (
    UCUM_REF,
    EvidenceContext,
    ObservationType,
    VitalObservation,
    observation,
    require_catalog_unit,
)
from app.main import app
from app.reports.labs import confirmed_value

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "contexto" / "especificacion-tecnica-v1.1.md"
RECORD_INTEGRITY = ROOT / "compliance" / "record-integrity.md"
SECTION = "### 3.14 quater"
NOW = dt.datetime(2026, 11, 14, 8, 0, tzinfo=dt.UTC)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _post(client: TestClient, **extra: Any) -> Any:
    body = {"key": "vitamin-d-25oh", "value": 31.4, **extra}
    return client.post("/api/observations", json=body)


# --------------------------------------------------------------------------- #
# La regla
# --------------------------------------------------------------------------- #


def test_the_catalog_unit_is_accepted_and_the_response_says_it_was_declared(
    client: TestClient,
) -> None:
    response = _post(client, unit="ng/mL")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["unit"] == "ng/mL"
    assert body["unit_assumed"] is False
    assert len(get_store().ledger) == 1
    assert get_store().query("crew-01", key="vitamin-d-25oh")[0].value == 31.4


def test_without_unit_the_catalog_one_is_assumed_and_the_response_says_so(
    client: TestClient,
) -> None:
    response = _post(client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["unit"] == get("vitamin-d-25oh").unit
    assert body["unit_assumed"] is True
    assert len(get_store().ledger) == 1


def test_another_unit_is_a_422_without_entry_and_without_conversion(client: TestClient) -> None:
    response = _post(client, value=78.4, unit="nmol/L")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "nmol/L" in detail and "ng/mL" in detail
    assert "no convierte" in detail
    # Ni asiento ni lectura: el ledger sigue vacío y no hay vitamina D de nadie.
    assert len(get_store().ledger) == 0
    assert get_store().query("crew-01", key="vitamin-d-25oh") == []


def test_the_comparison_is_literal_and_case_sensitive(client: TestClient) -> None:
    for unit in ("ng/ml", " ng/mL", "ng/mL ", "NG/ML"):
        assert _post(client, unit=unit).status_code == 422, unit
    assert len(get_store().ledger) == 0


def test_an_empty_unit_is_not_an_absent_one(client: TestClient) -> None:
    """`""` no puede pasar por «no la declaró»: se asumiría la del catálogo en silencio."""
    response = _post(client, unit="")
    assert response.status_code == 422
    # El motivo en español, como las demás unidades rechazadas; no la lista de Pydantic.
    detail = response.json()["detail"]
    assert isinstance(detail, str)
    assert "unidad vacía para vitamin-d-25oh" in detail and "'ng/mL'" in detail
    assert len(get_store().ledger) == 0
    # El mismo motivo por la vía FHIR: la regla es de la comparación compartida.
    resource = observation("vitamin-d-25oh", 31.4, NOW, "crew-01", "manual").to_fhir()
    resource["valueQuantity"]["code"] = ""
    with pytest.raises(ValueError) as from_fhir:
        VitalObservation.from_fhir(resource)
    assert str(from_fhir.value) == detail


def test_a_giant_unit_does_not_come_back_whole(client: TestClient) -> None:
    response = _post(client, unit="x" * 64)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "x" * 41 not in detail
    # El corte se marca: no parece una unidad recibida entera.
    assert "'" + "x" * 39 + "…," in detail
    # Pasado el tope, el motivo en español y sin repetir la unidad: ni se compara.
    longer = _post(client, unit="x" * 65)
    assert longer.status_code == 422
    assert longer.json()["detail"] == (
        "unidad de 65 caracteres para vitamin-d-25oh: no se admite más de 64; el catálogo "
        "define 'ng/mL'"
    )
    huge = _post(client, unit="x" * 100_000)
    assert huge.status_code == 422
    assert "xx" not in huge.json()["detail"]
    assert len(get_store().ledger) == 0
    # Una que cabe vuelve entera y sin marca.
    assert "llega 'nmol/L', " in _post(client, unit="nmol/L").json()["detail"]
    # Por la vía FHIR la unidad puede no ser texto: una lista enorme tampoco vuelve entera.
    with pytest.raises(ValueError) as caught:
        require_catalog_unit(get("vitamin-d-25oh"), ["x" * 1000])
    assert "x" * 41 not in str(caught.value)


def test_the_manual_route_and_the_fhir_route_share_one_comparison(client: TestClient) -> None:
    """El mismo motivo, carácter a carácter, en las dos vías: no hay dos comparaciones."""
    code = get("vitamin-d-25oh")
    with pytest.raises(ValueError) as caught:
        require_catalog_unit(code, "nmol/L")
    assert _post(client, unit="nmol/L").json()["detail"] == str(caught.value)

    resource = observation("vitamin-d-25oh", 31.4, NOW, "crew-01", "manual").to_fhir()
    resource["valueQuantity"]["code"] = "nmol/L"
    with pytest.raises(ValueError) as from_fhir:
        VitalObservation.from_fhir(resource)
    assert str(from_fhir.value) == str(caught.value)


def test_the_amendment_follows_the_same_rule(client: TestClient) -> None:
    created = _post(client, unit="ng/mL").json()
    index = created["ledger_index"]
    refused = client.post(
        f"/api/audit/amend/{index}",
        json={
            "reason": "cifra copiada del informe en otra unidad",
            "correction": {"key": "vitamin-d-25oh", "value": 78.4, "unit": "nmol/L"},
        },
    )
    assert refused.status_code == 422
    assert "no convierte" in refused.json()["detail"]
    assert len(get_store().ledger) == 1

    accepted = client.post(
        f"/api/audit/amend/{index}",
        json={
            "reason": "cifra mal tecleada",
            "correction": {"key": "vitamin-d-25oh", "value": 32.1},
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["unit"] == "ng/mL"
    assert accepted.json()["unit_assumed"] is True


def test_the_amendment_keeps_the_provenance_its_correction_declares(client: TestClient) -> None:
    """La enmienda no firma como medida lo que su corrección declara inferido."""
    index = _post(client).json()["ledger_index"]
    without_model = client.post(
        f"/api/audit/amend/{index}",
        json={
            "reason": "valor recalculado",
            "correction": {"key": "vitamin-d-25oh", "value": 30.0, "observation_type": "inferred"},
        },
    )
    assert without_model.status_code == 422
    assert "model_version" in without_model.json()["detail"]

    accepted = client.post(
        f"/api/audit/amend/{index}",
        json={
            "reason": "valor recalculado",
            "correction": {
                "key": "vitamin-d-25oh", "value": 30.0, "observation_type": "inferred",
                "model_version": "calibracion@2", "evidence_context": "iss",
            },
        },
    )
    assert accepted.status_code == 200, accepted.text
    current = get_store().query("crew-01", key="vitamin-d-25oh")[0]
    assert current.observation_type is ObservationType.INFERRED
    assert current.model_version == "calibracion@2"
    assert current.evidence is EvidenceContext.ISS


def test_the_amendment_without_context_keeps_the_deployment_one(
    client: TestClient, tmp_path: Path
) -> None:
    """Corregir una errata en la ISS no pasa la lectura a Tierra: vale el entorno desplegado."""
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, deployment_context=EvidenceContext.ISS
    )
    index = _post(client).json()["ledger_index"]
    assert get_store().query("crew-01", key="vitamin-d-25oh")[0].evidence is EvidenceContext.ISS
    accepted = client.post(
        f"/api/audit/amend/{index}",
        json={
            "reason": "cifra mal tecleada",
            "correction": {"key": "vitamin-d-25oh", "value": 32.1},
        },
    )
    assert accepted.status_code == 200, accepted.text
    current = get_store().query("crew-01", key="vitamin-d-25oh")[0]
    assert current.value == 32.1
    assert current.evidence is EvidenceContext.ISS


def test_the_amendment_reports_an_empty_unit_in_spanish_too(client: TestClient) -> None:
    index = _post(client).json()["ledger_index"]
    for unit, expected in (("", "unidad vacía"), ("x" * 65, "no se admite más de 64")):
        refused = client.post(
            f"/api/audit/amend/{index}",
            json={
                "reason": "cifra mal tecleada",
                "correction": {"key": "vitamin-d-25oh", "value": 32.1, "unit": unit},
            },
        )
        assert refused.status_code == 422
        assert expected in refused.json()["detail"]
    assert len(get_store().ledger) == 1


# --------------------------------------------------------------------------- #
# La misma regla en la lectura de cabina manual y en la analítica escaneada
# --------------------------------------------------------------------------- #


def _cabin(client: TestClient, **extra: Any) -> Any:
    body = {"parameter": "cabin-ppco2", "value": 2.4, **extra}
    return client.post("/api/habitat", json=body)


def test_a_cabin_reading_with_its_unit_is_recorded_and_says_it_was_declared(
    client: TestClient,
) -> None:
    response = _cabin(client, unit="mm[Hg]")
    assert response.status_code == 201, response.text
    assert response.json()["unit"] == "mm[Hg]"
    assert response.json()["unit_assumed"] is False
    assert len(get_store().ledger) == 1


def test_a_cabin_reading_without_unit_assumes_the_parameter_one(client: TestClient) -> None:
    response = _cabin(client)
    assert response.status_code == 201, response.text
    assert response.json()["unit"] == habitat_parameter("cabin-ppco2").unit
    assert response.json()["unit_assumed"] is True


def test_a_cabin_reading_in_another_unit_is_a_422_without_entry(client: TestClient) -> None:
    response = _cabin(client, value=0.32, unit="kPa")
    assert response.status_code == 422
    detail = response.json()["detail"]
    with pytest.raises(ValueError) as caught:
        require_catalog_unit(habitat_parameter("cabin-ppco2"), "kPa")
    # La misma comparación y el mismo motivo que una lectura de un tripulante.
    assert detail == str(caught.value)
    assert "no convierte" in detail
    for unit in ("", "mm[hg]", "x" * 65):
        assert _cabin(client, unit=unit).status_code == 422, unit
    assert len(get_store().ledger) == 0


def test_an_unknown_cabin_parameter_is_still_a_422(client: TestClient) -> None:
    response = client.post("/api/habitat", json={"parameter": "cabin-x", "value": 1, "unit": "%"})
    assert response.status_code == 422
    assert "desconocido" in response.json()["detail"]


def test_a_scanned_lab_compares_the_unit_like_every_other_route() -> None:
    """La analítica no tiene comparación propia: el motivo empieza por el de la ingesta."""
    reading = {"key": "calcium", "value": 2.3, "requires_correction": True}
    with pytest.raises(ValueError) as shared:
        require_catalog_unit(get("calcium"), "mmol/L")
    with pytest.raises(ValueError) as from_lab:
        confirmed_value(reading, 2.3, "mmol/L")
    assert str(from_lab.value).startswith(str(shared.value))
    assert "convierte el valor leído en el papel" in str(from_lab.value)
    assert confirmed_value(reading, 9.2, "mg/dL") == 9.2
    with pytest.raises(ValueError):
        confirmed_value(reading, 9.2, "mg/dl")


def test_a_declared_unit_does_not_change_what_is_signed(client: TestClient) -> None:
    """La unidad no es un campo del asiento: con o sin ella, el mismo contenido firmado."""
    when = NOW.isoformat()
    _post(client, effective=when, unit="ng/mL")
    _post(client, effective=when, subject="crew-02")
    first, second = get_store().query("crew-01")[0], get_store().query("crew-02")[0]
    a, b = _to_payload(first), _to_payload(second)
    assert "unit" not in a
    assert {k: v for k, v in a.items() if k != "subject"} == {
        k: v for k, v in b.items() if k != "subject"
    }


# --------------------------------------------------------------------------- #
# La tabla de §3.14 quater, contra la especificación y el código
# --------------------------------------------------------------------------- #


def _spec_fields() -> set[str]:
    text = SPEC.read_text(encoding="utf-8")
    section = text.split("# 5. Contratos de datos", 1)[1].split("\n# ", 1)[0]
    sample = next(line for line in section.splitlines() if line.lstrip().startswith("{"))
    return set(json.loads(sample))


# Columnas de la tabla: campo de §5, elemento FHIR, atributo de `VitalObservation`, campo del
# asiento firmado y, desde la decimonovena ronda, el nombre en la ingesta (`ObservationIn`), que
# es la correspondencia que aplica el adaptador de §5 (`api/spec5.FIELDS`).
COLUMNS = 5


def _table() -> list[tuple[str, str, str, str, str]]:
    text = RECORD_INTEGRITY.read_text(encoding="utf-8")
    assert text.count(SECTION) == 1
    section = text.split(SECTION, 1)[1].split("\n### ", 1)[0]
    rows = []
    for line in section.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != COLUMNS or not cells[0].startswith("`"):
            continue
        rows.append(tuple(cell.strip("`") for cell in cells))
    assert rows, "la tabla de §3.14 quater no se encontró con sus columnas"
    return rows  # type: ignore[return-value]


_EXTENSION = re.compile(r"^extension\('([^']+)'\)\.(\w+)$")
_STEP = re.compile(r"^(\w+)(?:\[(\d+)\])?$")


def _fhir_at(resource: dict[str, Any], path: str) -> Any:
    """Resuelve una ruta del JSON FHIR: `a.b[0].c` o `extension('<url>').valueX`."""
    match = _EXTENSION.match(path)
    if match:
        url, element = match.groups()
        found = [item for item in resource["extension"] if item["url"] == url]
        assert len(found) == 1, f"la extensión {url} no está una vez"
        return found[0][element]
    node: Any = resource
    for step in path.split("."):
        parsed = _STEP.match(step)
        assert parsed, step
        name, index = parsed.groups()
        node = node[name]
        if index is not None:
            node = node[int(index)]
    return node


def _attribute(reading: VitalObservation, path: str) -> Any:
    node: Any = reading
    for step in path.split("."):
        node = getattr(node, step)
    if isinstance(node, Enum):
        return node.value
    if isinstance(node, dt.datetime):
        return node.isoformat()
    return node


# Lo que FHIR añade alrededor del atributo; declarado en la «Lecturas de la tabla» del apartado.
_FHIR_PREFIX = {"subject.reference": "Patient/"}


def _sample() -> VitalObservation:
    # Todos los campos de §5 con un valor propio (un inferido para tener `model_version`).
    return observation(
        "vitamin-d-25oh", 31.4, NOW, "crew-03", "laboratorio-tierra", confidence=0.94,
        observation_type=ObservationType.INFERRED, evidence_context=EvidenceContext.GROUND,
        model_version="calibracion@2",
    )


def test_the_table_has_exactly_the_fields_of_section_5() -> None:
    fields = [row[0] for row in _table()]
    assert len(fields) == len(set(fields))
    assert set(fields) == _spec_fields()


def test_each_fhir_element_carries_the_attribute_the_table_names() -> None:
    reading = _sample()
    resource = reading.to_fhir()
    for field, fhir_path, attribute, _signed, _ingest in _table():
        expected = _attribute(reading, attribute)
        assert expected is not None, field
        if fhir_path in _FHIR_PREFIX:
            expected = _FHIR_PREFIX[fhir_path] + str(expected)
        assert _fhir_at(resource, fhir_path) == expected, field


def test_each_signed_field_is_in_the_entry_and_the_unit_is_not() -> None:
    payload = _to_payload(_sample())
    for field, _fhir_path, _attribute_path, signed, _ingest in _table():
        if signed == "—":
            assert field not in payload, field
        else:
            assert signed in payload, field


def test_the_ingest_column_is_the_correspondence_the_adapter_applies() -> None:
    """La tabla copia `api/spec5.FIELDS`, campo a campo; la fuente única es el código."""
    from app.api import spec5
    from app.api.routes import ObservationIn

    in_table = {field: ingest for field, _f, _a, _s, ingest in _table()}
    assert in_table == dict(spec5.FIELDS)
    assert list(in_table) == list(spec5.FIELDS), "el mismo orden que el JSON de §5"
    for field, ingest in in_table.items():
        assert ingest in ObservationIn.model_fields, field


def test_the_unit_row_is_the_catalog_unit_in_ucum() -> None:
    resource = _sample().to_fhir()
    assert resource["valueQuantity"]["system"] == "http://unitsofmeasure.org"
    assert resource["valueQuantity"]["unit"] == resource["valueQuantity"]["code"] == "ng/mL"


def test_the_ucum_reading_behind_the_literal_comparison_is_a_registered_card() -> None:
    card = registry.get(UCUM_REF)
    assert card.evidence_type == "technical_standard"
    assert card.notes is not None and "case sensitive variant the liter" in card.notes
