"""Mapa corporal de dolor: catálogo, informe firmado y su paso al análisis.

Lo que se protege aquí: que la cifra que analiza el motor de riesgo sea la del informe
que la explica, que el informe no se pueda falsificar por la ingesta genérica y que
un informe retirado desaparezca entero.
"""

import datetime as dt
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.core.ledger import Identity
from app.core.storage import ObservationStore
from app.ingest.fhir import observation
from app.main import app
from app.pain.catalog import CHARACTERS, ZONES, validate_zones

WHEN = "2026-09-25T08:00:00+00:00"


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True
    )
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _report(*zones: dict[str, object], **extra: object) -> dict[str, object]:
    return {"zones": list(zones), "reported_by": "cmdr", "effective": WHEN, **extra}


LUMBAR = {"zone": "lower-back", "intensity": 6, "characters": ["dull"]}
KNEE = {"zone": "knee-left", "intensity": 3, "characters": ["sharp", "throbbing"]}


# --------------------------------------------------------------------------- #
# Catálogo
# --------------------------------------------------------------------------- #


def test_paired_zones_exist_on_both_sides_with_patient_laterality() -> None:
    for key, zone in ZONES.items():
        if zone.side is None:
            continue
        assert key.endswith(f"-{zone.side}")
        other = "right" if zone.side == "left" else "left"
        assert f"{key.rsplit('-', 1)[0]}-{other}" in ZONES
        word = "izquierd" if zone.side == "left" else "derech"
        assert word in zone.display


def test_the_body_model_draws_exactly_the_declared_zones() -> None:
    """Una zona sin forma no se puede marcar; una forma sin zona daría un 422 al enviar.

    Hay dos listas —este catálogo y el cuerpo de `frontend/src/pain/bodyModel.ts`— porque
    cada lado las necesita sin llamar al otro. Como con las unidades, se comprueba que casan.
    """
    source = (
        Path(__file__).resolve().parents[2] / "frontend" / "src" / "pain" / "bodyModel.ts"
    ).read_text(encoding="utf-8")
    central_block, _, paired_block = source.partition("const LEFT")
    central = re.findall(r'zone: "([a-z-]+)"', central_block)
    paired = re.findall(r'zone: "([a-z-]+)"', paired_block.split("export const BODY")[0])
    drawn = {*central, *(f"{base}-{side}" for base in paired for side in ("left", "right"))}
    assert central and paired
    assert drawn == set(ZONES)


def test_catalog_route_declares_zones_characters_and_scale(client: TestClient) -> None:
    body = client.get("/api/pain/catalog").json()
    assert {zone["key"] for zone in body["zones"]} == set(ZONES)
    assert {c["key"] for c in body["characters"]} == set(CHARACTERS)
    assert body["scale"] == {"min": 0, "max": 10, "unit": "{score}"}


def test_validation_names_every_problem() -> None:
    problems = validate_zones(
        [("elbow-up", 3, []), ("knee-left", 0, []), ("knee-left", 4, ["itchy", "sharp"])]
    )
    assert any("zona desconocida" in p for p in problems)
    assert any("de 1 a 10" in p for p in problems)
    assert any("dos veces" in p for p in problems)
    assert any("itchy" in p for p in problems)


# --------------------------------------------------------------------------- #
# Registro
# --------------------------------------------------------------------------- #


def test_report_records_the_peak_and_the_signed_report(client: TestClient) -> None:
    response = client.post("/api/pain/reports", json=_report(LUMBAR, KNEE))

    assert response.status_code == 201
    assert response.json()["intensity"] == 6
    reading = client.get("/api/observations", params={"key": "pain-intensity"}).json()
    assert reading["count"] == 1

    [report] = client.get("/api/pain/reports").json()
    assert report["intensity"] == 6
    assert report["reported_by"] == "cmdr"
    assert [z["zone"] for z in report["zones"]] == ["lower-back", "knee-left"]
    assert report["zones"][1]["characters"] == ["sharp", "throbbing"]
    audit = client.get("/api/audit").json()
    assert [e["entry_type"] for e in audit["entries"]][-2:] == ["vital-observation", "pain-report"]
    assert audit["entries"][-1]["signer"] == "pain-report"


def test_no_pain_is_an_explicit_zero(client: TestClient) -> None:
    assert client.post("/api/pain/reports", json=_report()).status_code == 201
    [report] = client.get("/api/pain/reports").json()
    assert report["intensity"] == 0
    assert report["zones"] == []


@pytest.mark.parametrize(
    "zones",
    [
        [{"zone": "tail", "intensity": 4}],
        [{"zone": "knee-left", "intensity": 0}],
        [{"zone": "knee-left", "intensity": 11}],
        [{"zone": "knee-left", "intensity": 5.5}],
        [KNEE, KNEE],
        [{"zone": "knee-left", "intensity": 4, "characters": ["itchy"]}],
    ],
)
def test_malformed_reports_are_rejected_and_nothing_is_written(
    client: TestClient, zones: list[dict[str, object]]
) -> None:
    assert client.post("/api/pain/reports", json=_report(*zones)).status_code == 422
    assert client.get("/api/audit").json()["entries"] == []


def test_a_report_needs_who_reports(client: TestClient) -> None:
    body = _report(LUMBAR)
    body["reported_by"] = "   "
    assert client.post("/api/pain/reports", json=body).status_code == 422


def test_intensity_cannot_enter_through_generic_ingest(client: TestClient) -> None:
    """Sin informe no se sabe dónde duele: la cifra suelta no entra."""
    response = client.post("/api/observations", json={"key": "pain-intensity", "value": 8})
    assert response.status_code == 422
    assert "informe de dolor" in response.json()["detail"]


def test_nobody_else_can_sign_as_the_pain_report(client: TestClient) -> None:
    response = client.post(
        "/api/observations", json={"key": "heart-rate", "value": 60, "source": "pain-report"}
    )
    assert response.status_code == 422


def test_store_refuses_a_reading_that_is_not_the_report_peak() -> None:
    store = ObservationStore.in_memory()
    reading = observation(
        "pain-intensity", 2.0,
        effective=dt.datetime.fromisoformat(WHEN),
        subject="crew-01", source="pain-report",
    )
    report = {"subject": "crew-01", "zones": [LUMBAR]}
    with pytest.raises(ValueError, match="máxima"):
        store.record_pain_report(reading, report, Identity.generate("pain-report"))
    assert store.count() == 0


# --------------------------------------------------------------------------- #
# Rectificación
# --------------------------------------------------------------------------- #


def test_redacting_the_reading_withdraws_the_whole_report(client: TestClient) -> None:
    [reading_index, _] = client.post("/api/pain/reports", json=_report(LUMBAR)).json()[
        "recorded"
    ]
    response = client.post(
        f"/api/audit/redact/{reading_index}",
        json={"reason": "registrado en el tripulante equivocado", "requested_by": "cirujano"},
    )
    assert response.status_code == 200
    assert client.get("/api/pain/reports").json() == []
    assert client.get("/api/observations", params={"key": "pain-intensity"}).json()["count"] == 0


def test_an_intensity_is_not_amended(client: TestClient) -> None:
    [reading_index, _] = client.post("/api/pain/reports", json=_report(LUMBAR)).json()[
        "recorded"
    ]
    response = client.post(
        f"/api/audit/amend/{reading_index}",
        json={
            "reason": "me equivoqué de cifra",
            "correction": {"key": "heart-rate", "value": 60},
        },
    )
    # Como una medida ecográfica: el almacén lo rechaza y la API lo trata como conflicto.
    assert response.status_code == 409
    assert "informe nuevo" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# Análisis y retardo
# --------------------------------------------------------------------------- #


def test_pain_is_analysed_under_its_own_domain(client: TestClient) -> None:
    client.post("/api/pain/reports", json=_report(LUMBAR))
    status = client.get("/api/status").json()
    assert "musculoskeletal" in status["domains"]


def test_ground_only_sees_what_has_arrived(client: TestClient) -> None:
    client.post("/api/pain/reports", json=_report(LUMBAR))
    [report] = client.get("/api/pain/reports").json()
    arrived = client.get(
        "/api/pain/reports", params={"until": "2000-01-01T00:00:00+00:00"}
    ).json()
    assert arrived == []
    everything = client.get(
        "/api/pain/reports", params={"until": report["recorded"]}
    ).json()
    assert len(everything) == 1


# --------------------------------------------------------------------------- #
# Borrador del modelo local
# --------------------------------------------------------------------------- #


def test_the_draft_reads_pain_as_legible_input_facts() -> None:
    """Entra con los nombres que lee una persona y la cifra como la escribe la consola."""
    from app.api.routes import get_store
    from app.interpret.draft import pain_history

    store = new_store()
    reset_store(store)
    try:
        with TestClient(app) as local:
            local.post("/api/pain/reports", json=_report(LUMBAR, KNEE))
            local.post("/api/pain/reports", json=_report())
        [first, second] = pain_history(get_store(), "crew-01")
    finally:
        reset_store(None)

    assert first["fecha"] == WHEN[:10]
    assert first["zonas"][0] == {"zona": "Zona lumbar", "intensidad": "6 puntos", "tipo": ["Sordo"]}
    assert first["zonas"][1]["tipo"] == ["Punzante", "Pulsátil"]
    assert second["zonas"] == "sin dolor"
