"""El adaptador del contrato JSON de §5 de la especificación: `POST /api/import/observations`.

§5 define una observación con sus propios nombres (`timestamp`, `subject_id`, `variable_id`,
`quality`…) y §13 pide un adaptador de «archivos/demo»; EMMA solo tenía el alta manual con nombres
propios y la correspondencia escrita en `record-integrity.md` §3.14 quater. Estas pruebas fijan lo
que hace el adaptador (`api/spec5.py`): traduce con esa correspondencia, entra por las mismas
comprobaciones que `POST /api/observations` y firma el lote entero o nada; una unidad distinta de
la del catálogo, un campo que §5 no tiene o un `variable_id` desconocido son un 422 que dice la
lectura, el campo y el motivo, y al ledger no llega nada.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.api.routes as routes
from app.api import spec5
from app.api.routes import ObservationIn, get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.ingest.codes import CATALOG, LAB_REPORT_ONLY, get
from app.ingest.fhir import EvidenceContext, ObservationType
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "contexto" / "especificacion-tecnica-v1.1.md"
SAMPLE = ROOT / "backend" / "app" / "data" / "samples" / "spec5_observations.json"
ROUTE = "/api/import/observations"
JSON = {"content-type": "application/json"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _sample() -> list[dict[str, Any]]:
    return list(json.loads(SAMPLE.read_text(encoding="utf-8")))


def _spec_fields() -> set[str]:
    text = SPEC.read_text(encoding="utf-8")
    section = text.split("# 5. Contratos de datos", 1)[1].split("\n# ", 1)[0]
    sample = next(line for line in section.splitlines() if line.lstrip().startswith("{"))
    return set(json.loads(sample))


def _reading(**extra: Any) -> dict[str, Any]:
    base = {
        "timestamp": "2026-03-14T08:00:00Z", "subject_id": "crew-02",
        "variable_id": "heart-rate", "value": 64.0, "source": "demo-file",
    }
    return {**base, **extra}


def _post(client: TestClient, batch: Any) -> Any:
    return client.post(ROUTE, json=batch)


def _audit(client: TestClient) -> Any:
    return client.get("/api/audit").json()


# --------------------------------------------------------------------------- #
# La muestra entra entera, auditada, y es lo que §5 describe
# --------------------------------------------------------------------------- #


def test_the_sample_imports_whole_and_audited(client: TestClient) -> None:
    response = client.post(ROUTE, content=SAMPLE.read_bytes(), headers=JSON)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["imported"] == 3
    assert body["by_indicator"] == {"heart-rate": 1, "hrv-rmssd": 1, "vitamin-d-25oh": 1}
    assert body["ledger_first"] == 0 and body["ledger_last"] == 2
    # La unidad: declarada en la constante y en la analítica, asumida en la que no la trae.
    assert body["units"] == {
        "heart-rate": {"unit": "/min", "declared": 1, "assumed": 0},
        "hrv-rmssd": {"unit": "ms", "declared": 0, "assumed": 1},
        "vitamin-d-25oh": {"unit": "ng/mL", "declared": 1, "assumed": 0},
    }
    audit = _audit(client)
    assert audit["total_entries"] == 3 and audit["integrity_ok"] is True
    # Lo traducido, campo a campo: `quality` es la confianza, `timestamp` el instante…
    rmssd = get_store().query("crew-01", key="hrv-rmssd")[0]
    assert rmssd.value == 42.1
    assert rmssd.confidence == 0.94
    assert rmssd.source == "demo-file"
    assert rmssd.effective == dt.datetime(2026, 3, 14, 8, tzinfo=dt.UTC)
    assert rmssd.evidence is EvidenceContext.SIMULATED
    assert rmssd.observation_type is ObservationType.MEASURED
    assert rmssd.model_version is None
    # Y el estado se calcula con ellas sin tropezar.
    assert client.get("/api/status").status_code == 200


@pytest.mark.parametrize(
    ("field", "value", "said"),
    [
        ("source", "   ", "en blanco"),
        ("subject_id", "  ", "en blanco"),
        ("source", "x" * 129, "128 caracteres"),
        ("timestamp", "2099-01-01T00:00:00Z", "en el futuro"),
    ],
)
def test_a_reading_that_says_nothing_or_comes_from_the_future_is_refused(
    client: TestClient, field: str, value: str, said: str
) -> None:
    """Lo vio la revisión de código: 201 y firmado, a nombre de nadie o en 2099."""
    response = _post(client, [{**_reading(), field: value}])
    assert response.status_code == 422, response.text
    assert said in response.json()["detail"]
    assert _audit(client)["total_entries"] == 0


def test_the_sample_has_the_shape_of_section_5() -> None:
    """La muestra es §5 literal: solo sus campos, indicadores del catálogo, una analítica con su
    unidad."""
    sample = _sample()
    assert len(sample) == 3
    fields = _spec_fields()
    for item in sample:
        assert set(item) <= fields, item
        assert set(spec5.REQUIRED) <= set(item), item
        assert item["variable_id"] in CATALOG, item["variable_id"]
        assert item["model_version"] is None  # el literal `null` de §5
    with_unit = {item["variable_id"]: item["unit"] for item in sample if "unit" in item}
    assert all(get(key).unit == unit for key, unit in with_unit.items())
    # Una analítica con su unidad (la vitamina D de la invariante 2) y una constante con la suya.
    assert with_unit == {"vitamin-d-25oh": "ng/mL", "heart-rate": "/min"}
    assert len({item["source"] for item in sample}) == 1


def test_fields_cover_exactly_section_5_and_land_in_the_manual_schema() -> None:
    assert set(spec5.FIELDS) == _spec_fields()
    assert set(spec5.FIELDS.values()) <= set(ObservationIn.model_fields)
    assert set(spec5.FIELDS) >= spec5.REQUIRED
    # Lo que EMMA firma y §5 no tiene no entra por aquí.
    for emma_only in ("context", "device", "recorded_by", "food"):
        assert emma_only not in spec5.FIELDS.values()


def test_the_route_declares_the_fields_of_section_5_in_openapi() -> None:
    body = app.openapi()["paths"][ROUTE]["post"]["requestBody"]["content"]["application/json"]
    schema = body["schema"]
    assert schema["type"] == "array"
    assert set(schema["items"]["properties"]) == set(spec5.FIELDS)
    assert set(schema["items"]["required"]) == spec5.REQUIRED
    assert schema["items"]["additionalProperties"] is False


# --------------------------------------------------------------------------- #
# El mismo camino que el alta manual
# --------------------------------------------------------------------------- #


def test_the_same_reading_signs_the_same_bytes_as_the_manual_route(client: TestClient) -> None:
    """La traducción no añade ni pierde nada: mismo asiento y firma que `POST /api/observations`."""
    imported = _post(client, [_reading(
        subject_id="crew-01", quality=0.8, evidence_context="analog_bedrest", unit="/min",
    )])
    assert imported.status_code == 201, imported.text
    manual = client.post("/api/observations", json={
        "key": "heart-rate", "value": 64.0, "subject": "crew-02", "source": "demo-file",
        "effective": "2026-03-14T08:00:00Z", "confidence": 0.8,
        "evidence_context": "analog_bedrest",
    })
    assert manual.status_code == 201, manual.text
    first, second = get_store().ledger[0], get_store().ledger[1]
    assert first.signer == second.signer == "demo-file"
    assert first.payload is not None and second.payload is not None
    skip = {"subject", "_salt"}
    assert {k: v for k, v in first.payload.items() if k not in skip} == {
        k: v for k, v in second.payload.items() if k not in skip
    }
    assert first.payload["subject"] == "crew-01" and second.payload["subject"] == "crew-02"


def test_a_reading_in_another_unit_refuses_the_whole_batch(client: TestClient) -> None:
    batch = _sample()
    batch[1]["unit"] = "s"
    response = _post(client, batch)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail.startswith("lectura 2 de 3: ")
    assert "'s'" in detail and "'ms'" in detail and "no convierte" in detail
    # Entero o nada: la primera lectura era válida y tampoco entró.
    assert _audit(client)["total_entries"] == 0
    assert get_store().query("crew-01", key="heart-rate") == []
    # La misma comparación literal que el alta manual: ni mayúsculas ni espacios.
    for unit in ("MS", " ms", ""):
        batch[1]["unit"] = unit
        assert _post(client, batch).status_code == 422, unit
    assert _audit(client)["total_entries"] == 0


def test_a_null_optional_is_an_absent_one(client: TestClient) -> None:
    """§5 escribe `"model_version": null`; un nulo en cualquier opcional es «sin declarar»."""
    response = _post(client, [
        _reading(unit=None, quality=None, observation_type=None, evidence_context=None),
        _reading(unit="/min"),
    ])
    assert response.status_code == 201, response.text
    assert response.json()["units"] == {"heart-rate": {"unit": "/min", "declared": 1, "assumed": 1}}
    reading = get_store().query("crew-02", key="heart-rate")[0]
    assert reading.confidence == 1.0
    assert reading.observation_type is ObservationType.MEASURED
    assert reading.evidence is EvidenceContext.GROUND  # el del despliegue por defecto


def test_a_pain_intensity_in_the_middle_leaves_nothing_written(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lo que el ledger rechaza al firmar también para el lote entero: no queda media tanda."""
    # Sin la comprobación previa del adaptador, quien lo para es `record_many`.
    monkeypatch.setattr(spec5, "_only_elsewhere", lambda key: None)
    batch = [
        _reading(),
        _reading(variable_id="pain-intensity", value=4),
        _reading(variable_id="respiratory-rate", value=14),
    ]
    response = _post(client, batch)
    assert response.status_code == 422
    assert "informe de dolor" in response.json()["detail"]
    assert _audit(client)["total_entries"] == 0


def test_quality_becomes_confidence_and_provenance_is_kept(client: TestClient) -> None:
    response = _post(client, [_reading(
        quality=0.4, observation_type="inferred", model_version="calibracion@2",
        evidence_context="analog_bedrest",
    )])
    assert response.status_code == 201, response.text
    reading = get_store().query("crew-02", key="heart-rate")[0]
    assert reading.confidence == 0.4
    assert reading.observation_type is ObservationType.INFERRED
    assert reading.model_version == "calibracion@2"
    assert reading.evidence is EvidenceContext.ANALOG_BEDREST
    # Un valor no medido sin modelo no se puede auditar: 422, como en el alta manual.
    refused = _post(client, [_reading(observation_type="predicted")])
    assert refused.status_code == 422
    assert "model_version" in refused.json()["detail"]
    # Fuera de 0-1 no es una calidad; el campo se nombra como lo escribe §5.
    out_of_range = _post(client, [_reading(quality=2)])
    assert out_of_range.status_code == 422
    assert "campo 'quality'" in out_of_range.json()["detail"]


def test_the_iss_literal_of_section_5_is_the_iss_code(client: TestClient) -> None:
    assert _post(client, [_reading(evidence_context="ISS")]).status_code == 201
    assert get_store().query("crew-02", key="heart-rate")[0].evidence is EvidenceContext.ISS
    # Es un alias, no una normalización: nada más se pasa a minúsculas.
    for context in ("Iss", "GROUND", "Simulated"):
        refused = _post(client, [_reading(evidence_context=context)])
        assert refused.status_code == 422, context
        assert "campo 'evidence_context'" in refused.json()["detail"]
    # Los otros códigos de EMMA entran con su nombre.
    assert _post(client, [_reading(evidence_context="spaceflight")]).status_code == 201


def test_without_evidence_context_the_deployment_one_applies(
    client: TestClient, tmp_path: Path
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, deployment_context=EvidenceContext.ISS
    )
    assert _post(client, [_reading()]).status_code == 201
    assert get_store().query("crew-02", key="heart-rate")[0].evidence is EvidenceContext.ISS


# --------------------------------------------------------------------------- #
# Los rechazos: la lectura, el campo y el motivo, en español, y sin asiento
# --------------------------------------------------------------------------- #


def test_an_unknown_field_names_the_field_and_the_reading(client: TestClient) -> None:
    batch = _sample()
    batch[0]["foo"] = 1
    response = _post(client, batch)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail.startswith("lectura 1 de 3: campo desconocido 'foo': los campos de §5 son ")
    assert detail.endswith(", ".join(spec5.FIELDS))
    # Los nombres de EMMA no son los de §5: por aquí se habla §5.
    for emma_name in ("key", "subject", "effective", "confidence", "context", "device", "food"):
        refused = _post(client, [_reading(**{emma_name: "x"})])
        assert refused.status_code == 422, emma_name
        assert f"campo desconocido '{emma_name}'" in refused.json()["detail"]
    assert _audit(client)["total_entries"] == 0


def test_a_variable_outside_the_catalog_names_the_field(client: TestClient) -> None:
    batch = _sample()
    batch[2]["variable_id"] = "hrv_rmssd"  # el guion bajo del ejemplo de §5; EMMA usa guion
    response = _post(client, batch)
    assert response.status_code == 422
    assert response.json()["detail"] == (
        "lectura 3 de 3, campo 'variable_id': indicador desconocido: 'hrv_rmssd'"
    )
    assert _audit(client)["total_entries"] == 0


@pytest.mark.parametrize("field", sorted(spec5.REQUIRED))
def test_a_required_field_cannot_be_omitted_or_null(client: TestClient, field: str) -> None:
    omitted = _reading()
    del omitted[field]
    for item in (omitted, _reading(**{field: None})):
        response = _post(client, [item])
        assert response.status_code == 422, item
        assert f"lectura 1 de 1: falta el campo '{field}', obligatorio" in response.json()["detail"]
    assert _audit(client)["total_entries"] == 0


def test_a_wrong_type_names_the_field_in_section_5_words(client: TestClient) -> None:
    for field, value in (("value", "x"), ("timestamp", "ayer"), ("subject_id", "")):
        response = _post(client, [_reading(**{field: value})])
        assert response.status_code == 422, field
        assert response.json()["detail"].startswith(f"lectura 1 de 1: campo '{field}': ")
    assert _audit(client)["total_entries"] == 0


def test_the_types_are_strict_unlike_the_manual_route(client: TestClient) -> None:
    """En un fichero, `true` no es 1.0, "64" no es 64 y un entero no es un instante."""
    for field, value in (
        ("value", True), ("value", "64"), ("timestamp", 1_700_000_000), ("quality", "0.9"),
        ("observation_type", "MEASURED"),
    ):
        response = _post(client, [_reading(**{field: value})])
        assert response.status_code == 422, (field, value)
        assert response.json()["detail"].startswith(f"lectura 1 de 1: campo '{field}': ")
    assert _audit(client)["total_entries"] == 0
    # Un entero sí es un número: 64 vale como 64.0.
    assert _post(client, [_reading(value=64)]).status_code == 201
    # El alta manual, con una persona delante, sigue aceptando la conversión de Pydantic.
    lax = client.post("/api/observations", json={"key": "heart-rate", "value": "64"})
    assert lax.status_code == 201, lax.text


def test_a_timestamp_before_the_import_floor_is_refused_with_its_reading(
    client: TestClient,
) -> None:
    response = _post(client, [_reading(), _reading(timestamp="1999-12-31T23:00:00Z")])
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail.startswith("lectura 2 de 2: ") and "anterior a 2000-01-01" in detail
    assert _audit(client)["total_entries"] == 0


def test_a_timestamp_without_zone_is_refused_not_taken_for_utc(client: TestClient) -> None:
    """El alta manual lo toma por UTC; en un fichero serían horas de error firmadas."""
    response = _post(client, [_reading(), _reading(timestamp="2026-03-14T08:00:00")])
    assert response.status_code == 422
    assert response.json()["detail"].startswith(
        "lectura 2 de 2: campo 'timestamp': sin zona horaria"
    )
    assert _audit(client)["total_entries"] == 0
    # Con desfase sí: se guarda el mismo instante, en UTC.
    assert _post(client, [_reading(timestamp="2026-03-14T10:00:00+02:00")]).status_code == 201
    reading = get_store().query("crew-02", key="heart-rate")[0]
    assert reading.effective == dt.datetime(2026, 3, 14, 8, tzinfo=dt.UTC)


def test_a_value_that_overflows_is_refused_by_the_canonical_model(client: TestClient) -> None:
    """`1e999` es JSON válido y `json.loads` da infinito: no pasa como cifra."""
    body = (
        b'[{"timestamp":"2026-03-14T08:00:00Z","subject_id":"crew-02",'
        b'"variable_id":"heart-rate","value":1e999,"source":"demo-file"}]'
    )
    response = client.post(ROUTE, content=body, headers=JSON)
    assert response.status_code == 422
    assert response.json()["detail"].startswith("lectura 1 de 1: heart-rate: valor no finito")
    assert _audit(client)["total_entries"] == 0


def test_a_lone_surrogate_is_a_reason_without_a_field(client: TestClient) -> None:
    """Un sustituto suelto no se puede firmar: el esquema lo rechaza sin nombrar ningún campo."""
    body = (
        rb'[{"timestamp":"2026-03-14T08:00:00Z","subject_id":"crew-02\ud800",'
        rb'"variable_id":"heart-rate","value":60,"source":"demo-file"}]'
    )
    response = client.post(ROUTE, content=body, headers=JSON)
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail.startswith("lectura 1 de 1: ") and "campo ''" not in detail
    assert _audit(client)["total_entries"] == 0


def test_a_numeric_text_is_not_an_instant(client: TestClient) -> None:
    """Pydantic toma «1700000000» por segundos desde 1970, y ya con zona: no pasa como fecha."""
    for text in ("1700000000", "1773500000000", "2026-03-14 08:00:00Z"):
        response = _post(client, [_reading(timestamp=text)])
        assert response.status_code == 422, text
        assert response.json()["detail"].startswith(
            "lectura 1 de 1: campo 'timestamp': no es un instante ISO-8601"
        )
    assert _audit(client)["total_entries"] == 0


def test_a_repeated_key_is_refused_not_resolved_to_the_last(client: TestClient) -> None:
    """`json.loads` se queda con la última: 61 y 180 entrarían como 180 sin decir nada."""
    body = (
        b'[{"timestamp":"2026-03-14T08:00:00Z","subject_id":"crew-02",'
        b'"variable_id":"heart-rate","value":61,"value":180,"source":"demo-file"}]'
    )
    response = client.post(ROUTE, content=body, headers=JSON)
    assert response.status_code == 422
    assert response.json()["detail"].startswith("lectura 1 de 1: campo repetido 'value': ")
    assert _audit(client)["total_entries"] == 0


@pytest.mark.parametrize(
    ("key", "reason"),
    [
        ("pain-intensity", "informe de dolor"),
        (sorted(LAB_REPORT_ONLY)[0], "analítica escaneada"),
    ],
)
def test_a_key_of_another_route_names_its_reading(
    client: TestClient, key: str, reason: str
) -> None:
    response = _post(client, [_reading(), _reading(variable_id=key, value=4)])
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail.startswith("lectura 2 de 2, campo 'variable_id': ") and reason in detail
    assert _audit(client)["total_entries"] == 0


def test_a_rejection_does_not_echo_the_size_of_the_request(client: TestClient) -> None:
    long = "x" * 200_000
    for batch in (
        [_reading(**{long: 1})],
        [_reading(variable_id=long)],
        [_reading(source=f"fuente-{n}") for n in range(2_000)],
    ):
        response = _post(client, batch)
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert len(detail) <= spec5.MAX_DETAIL_CHARS + 30
        assert detail.endswith("(motivo recortado)")
    # Uno corto queda entero.
    assert "recortado" not in _post(client, [_reading(foo=1)]).json()["detail"]


def test_a_source_bound_to_another_crew_member_is_said_per_subject(client: TestClient) -> None:
    declared = client.post("/api/sensor-bindings", json={
        "source": "apple-health", "action": "bind", "since": "2026-01-01T00:00:00Z",
        "declared_by": "CDR", "crew": "crew-01",
    })
    assert declared.status_code == 201, declared.text
    response = _post(client, [
        _reading(source="apple-health", subject_id="crew-01"),
        _reading(source="apple-health", subject_id="crew-02"),
        _reading(source="apple-health", subject_id="crew-03"),
    ])
    assert response.status_code == 201, response.text
    notices = response.json()["binding_notices"]
    assert len(notices) == 2
    assert all(row["crew"] == "crew-01" for item in notices for row in item["bound_to"])
    # Cada aviso cuenta las lecturas de su sujeto, no las del lote.
    assert [row["readings"] for item in notices for row in item["bound_to"]] == [1, 1]
    # Sin vínculo que contradiga, no hay aviso.
    assert _post(client, [_reading()]).json()["binding_notices"] == []


def test_a_reserved_source_is_refused_in_spanish(client: TestClient) -> None:
    for source in ("simulator:nominal", "emma-audit", "crew-diary"):
        response = _post(client, [_reading(source=source)])
        assert response.status_code == 422, source
        detail = response.json()["detail"]
        assert detail.startswith("lectura 1 de 1: campo 'source': ")
        assert "reservada" in detail
    assert _audit(client)["total_entries"] == 0


def test_a_batch_is_one_source(client: TestClient) -> None:
    response = _post(client, [_reading(), _reading(source="otra")])
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "una sola fuente" in detail and "'demo-file', 'otra'" in detail
    assert _audit(client)["total_entries"] == 0


def test_the_body_must_be_a_non_empty_list_of_objects(client: TestClient) -> None:
    for body, reason in (
        (b"{}", "se esperaba una lista"),
        (b"[]", "vacía"),
        (
            b"[1]",
            "lectura 1 de 1: se esperaba un objeto JSON con los campos de §5, llega un número",
        ),
        (
            b'[[], "x"]',
            "lectura 1 de 2: se esperaba un objeto JSON con los campos de §5, llega una lista",
        ),
        (b"[null]", "llega null"),
        (b"{no es json", "JSON no válido"),
        (b"[Infinity]", "JSON no válido"),
    ):
        response = client.post(ROUTE, content=body, headers=JSON)
        assert response.status_code == 422, body
        assert reason in response.json()["detail"], body
    assert _audit(client)["total_entries"] == 0


def test_too_many_readings_are_a_413_before_anything_is_written(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes, "MAX_IMPORT_RECORDS", 2)
    response = _post(client, _sample())
    assert response.status_code == 413
    assert "más de 2 lecturas" in response.json()["detail"]
    assert _audit(client)["total_entries"] == 0


def test_an_oversized_body_is_a_413(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "MAX_IMPORT_BYTES", 50)
    assert _post(client, _sample()).status_code == 413
    assert _audit(client)["total_entries"] == 0


def test_translate_is_the_table_applied_and_nothing_else() -> None:
    item = {
        "timestamp": "2026-03-14T08:00:00Z", "subject_id": "crew-01", "variable_id": "heart-rate",
        "value": 61.0, "unit": "/min", "source": "demo-file", "quality": 0.94,
        "evidence_context": "ISS", "observation_type": "measured", "model_version": None,
    }
    assert spec5.translate(item) == {
        "effective": "2026-03-14T08:00:00Z", "subject": "crew-01", "key": "heart-rate",
        "value": 61.0, "unit": "/min", "source": "demo-file", "confidence": 0.94,
        "evidence_context": "iss", "observation_type": "measured",
    }
    with pytest.raises(ValueError, match="campo desconocido 'a', 'b'"):
        spec5.translate({**item, "a": 1, "b": 2})
    with pytest.raises(ValueError, match="falta el campo 'source', 'timestamp'"):
        spec5.translate({"subject_id": "crew-01", "variable_id": "heart-rate", "value": 1})
