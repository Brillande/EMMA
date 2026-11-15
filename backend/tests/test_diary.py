"""Registro diario del tripulante (`app/api/diary.py`).

Qué se puede anotar lo decide el backend desde el coste de medir, cada valor entra firmado
en el ledger y describir el registro no mueve el veredicto.

Desde el 2026-10-13 el diario firma con su fuente propia y con quién anota por su ruta
(`tests/test_recorded_by.py`). Aquí, lo que lleva una hora elegida entra como entraba antes
—`POST /api/observations`, fuente `manual`—: son las anotaciones antiguas, que el diario
tiene que seguir enseñando.
"""

import datetime as dt
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import diary as diary_module
from app.api.diary import (
    DIARY_EQUIPMENT,
    DIARY_SOURCE,
    LEGACY_SOURCE,
    SCALE_INSTRUMENT_ANCHORED,
    SCALE_UNLABELLED,
    SOURCE_NUMBERED_ANCHORS,
    diary_keys,
)
from app.api.routes import CONSOLE_IDENTITY, _is_reserved_source, new_store, reset_store
from app.core.config import Settings, get_settings
from app.ingest.codes import CATALOG, SELF_REPORTED_ONLY
from app.ingest.cost import costs
from app.ingest.fhir import EvidenceContext
from app.main import app


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


@pytest.fixture
def seeded(client: TestClient) -> TestClient:
    assert client.post(
        "/api/simulate", params={"scenario": "progressive-insomnia", "days": 30}
    ).status_code == 201
    return client


def _catalog(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/diary")
    assert response.status_code == 200
    return response.json()


def _body(catalog: dict[str, Any], key: str, value: float, **extra: Any) -> dict[str, Any]:
    """Un alta manual como las que enviaba el panel antes de tener ruta propia."""
    return {
        "key": key,
        "value": value,
        "subject": "crew-01",
        "source": LEGACY_SOURCE,
        "observation_type": catalog["provenance"]["observation_type"],
        **extra,
    }


def _food(item: dict[str, Any]) -> dict[str, Any]:
    """El alimento valorado, en el indicador que lo exige (desde el 2026-10-26)."""
    return {"food": "lentejas"} if item["food_item"] is not None else {}


def _entry(key: str, value: float, **extra: Any) -> dict[str, Any]:
    """El cuerpo que envía el panel ahora: sin fuente ni hora, y con quién anota."""
    return {"key": key, "value": value, "subject": "crew-01", "recorded_by": "CDR", **extra}


def _verdict(client: TestClient) -> tuple[Any, ...]:
    status = client.get("/api/status").json()
    return (
        status["overall_level"],
        {key: (item["level"], item["score"]) for key, item in status["domains"].items()},
        [(item["id"], item["level"]) for item in status["alerts"]],
    )


# --------------------------------------------------------------------------- #
# Qué entra: lo decide el coste de medir, no una lista
# --------------------------------------------------------------------------- #


def test_diary_offers_exactly_the_self_recorded_indicators_of_the_cost_table() -> None:
    expected = [
        key for key in CATALOG
        if costs().get(key, {}).get("equipment") in DIARY_EQUIPMENT
    ]
    assert diary_keys() == expected
    # Los que el contexto nombra: ánimo, síntomas, apetito, aceptabilidad e ingesta.
    assert {
        "mood-valence", "symptom-burden", "appetite-rating", "food-acceptability",
        "fluid-intake-24h", "energy-intake-daily",
    } <= set(expected)


def test_diary_leaves_out_what_is_not_recorded_by_hand() -> None:
    keys = set(diary_keys())
    # El dolor va con su informe; un pulso o un cortisol no los anota nadie a mano.
    assert not keys & SELF_REPORTED_ONLY
    assert not keys & {"heart-rate", "cortisol-salivary", "exercise-minutes", "pvt-mean-rt"}


def test_an_indicator_that_needs_its_report_is_not_offered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aunque la tabla de costes lo llamara autoinforme: la ingesta genérica lo rechazaría."""
    monkeypatch.setattr(
        diary_module, "cost", lambda key: {"equipment": "autoinforme", "mode_display": ""}
    )
    assert "pain-intensity" not in diary_keys()
    assert "mood-valence" in diary_keys()


def test_each_indicator_comes_with_the_catalogue_range_and_no_invented_labels(
    client: TestClient,
) -> None:
    payload = _catalog(client)
    assert [item["key"] for item in payload["indicators"]] == diary_keys()
    for item in payload["indicators"]:
        code = CATALOG[item["key"]]
        assert item["display"] == code.display
        assert item["unit"] == code.unit
        assert (item["physical_min"], item["physical_max"]) == (
            code.physical_min, code.physical_max
        )
        if code.unit == "{score}" and item["scale"]["labels_status"] != "read":
            # Sin fuente leída no hay rótulos. Los leídos (décima ronda: los dos extremos de
            # la escala hedónica; desde el 2026-10-20, también del 2 al 8) tienen su prueba en
            # `tests/test_pvt_sources.py`.
            assert item["scale"]["labels"] is None
            if item["key"] in SOURCE_NUMBERED_ANCHORS:
                assert item["scale"]["labels_note"] == SCALE_INSTRUMENT_ANCHORED
            else:
                assert item["scale"]["labels_note"].startswith(SCALE_UNLABELLED)
        elif code.unit == "{score}":
            assert item["key"] == "food-acceptability"
        else:
            assert item["scale"] is None
    by_key = {item["key"]: item for item in payload["indicators"]}
    assert by_key["mood-valence"]["range_text"] == "de 0,0 a 10,0"
    assert by_key["food-acceptability"]["physical_min"] == 1
    assert by_key["fluid-intake-24h"]["scale"] is None


def test_provenance_is_a_measured_diary_entry_in_the_deployment_context(
    client: TestClient, tmp_path
) -> None:
    provenance = _catalog(client)["provenance"]
    assert provenance == {
        "source": DIARY_SOURCE,
        "source_display": "registro diario",
        "observation_type": "measured",
        "evidence_context": "ground",
    }
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, deployment_context=EvidenceContext.ISS
    )
    assert _catalog(client)["provenance"]["evidence_context"] == "iss"


def test_diary_source_is_its_own_and_only_its_route_can_sign_with_it(
    client: TestClient,
) -> None:
    # No es la identidad de la consola, que reconoce y silencia alertas.
    assert DIARY_SOURCE == "crew-diary" != CONSOLE_IDENTITY
    # La ingesta genérica no puede usarla: por ahí entraría sin decir quién anota.
    assert _is_reserved_source(DIARY_SOURCE)
    assert not _is_reserved_source(LEGACY_SOURCE)
    catalog = _catalog(client)
    assert catalog["submit_to"] == "/api/diary/entries"
    refused = client.post(
        "/api/observations",
        json={**_body(catalog, "mood-valence", 5.0), "source": DIARY_SOURCE},
    )
    assert refused.status_code == 422
    assert client.get("/api/audit").json()["total_entries"] == 0


# --------------------------------------------------------------------------- #
# Cada valor entra por la ingesta de siempre: firmado y en el ledger
# --------------------------------------------------------------------------- #


def test_every_offered_indicator_is_accepted_and_signed_in_the_ledger(
    client: TestClient,
) -> None:
    catalog = _catalog(client)
    before = client.get("/api/audit").json()["total_entries"]
    for item in catalog["indicators"]:
        response = client.post(
            "/api/diary/entries",
            json=_entry(item["key"], item["physical_max"], **_food(item)),
        )
        assert response.status_code == 201, (item["key"], response.text)

    audit = client.get("/api/audit", params={"limit": 500}).json()
    assert audit["total_entries"] == before + len(catalog["indicators"])
    assert audit["integrity_ok"] is True
    assert {entry["signer"] for entry in audit["entries"]} == {DIARY_SOURCE}


def test_out_of_range_is_rejected_by_the_backend_too(client: TestClient) -> None:
    catalog = _catalog(client)
    before = client.get("/api/audit").json()["total_entries"]
    for item in catalog["indicators"]:
        for value in (item["physical_max"] + 1, item["physical_min"] - 1):
            response = client.post(
                "/api/diary/entries", json=_entry(item["key"], value, **_food(item))
            )
            assert response.status_code == 422, (item["key"], value)
            assert "físicamente posible" in response.json()["detail"]
    assert client.get("/api/audit").json()["total_entries"] == before


def test_an_old_manual_entry_is_read_back_with_its_provenance(seeded: TestClient) -> None:
    catalog = _catalog(seeded)
    reference = dt.datetime.fromisoformat(
        seeded.get("/api/status").json()["data"]["reference_time"]
    )
    moment = reference - dt.timedelta(hours=1)
    assert seeded.post(
        "/api/observations",
        json=_body(catalog, "mood-valence", 6.5, effective=moment.isoformat()),
    ).status_code == 201

    payload = seeded.get("/api/diary/entries").json()
    assert payload["count"] == 1
    entry = payload["entries"][0]
    assert entry["key"] == "mood-valence"
    assert entry["value"] == 6.5
    assert entry["value_text"] == "6,5 puntos"
    assert dt.datetime.fromisoformat(entry["effective"]) == moment
    assert entry["source"] == LEGACY_SOURCE
    assert entry["source_display"] == "alta manual"
    # No llevaba quién la anotó, y no se rellena.
    assert (entry["recorded_by"], entry["recorded_by_display"]) == (None, "no consta")
    assert entry["observation_type"] == "measured"
    assert entry["evidence_context"] == "ground"
    assert entry["position"] == "current"

    # Y aparece en el estado como cualquier otra lectura.
    status = seeded.get("/api/status").json()
    assert LEGACY_SOURCE in status["mission"]["sources"]
    assert status["provenance"]["evidence_context"]["ground"] == 1


def test_entries_are_only_the_hand_recorded_ones_newest_first(seeded: TestClient) -> None:
    catalog = _catalog(seeded)
    # Lo simulado tiene ánimo de sobra, y no es del diario.
    assert seeded.get("/api/diary/entries").json()["entries"] == []
    assert seeded.get("/api/diary/entries").json()["reference_time"] is not None

    reference = dt.datetime.fromisoformat(
        seeded.get("/api/status").json()["data"]["reference_time"]
    )
    for hours, value in ((30, 3.0), (2, 5.0)):
        seeded.post(
            "/api/observations",
            json=_body(
                catalog, "appetite-rating", value,
                effective=(reference - dt.timedelta(hours=hours)).isoformat(),
            ),
        )
    # Un alta manual de algo que no es del diario no se cuenta como entrada suya.
    seeded.post(
        "/api/observations",
        json=_body(catalog, "heart-rate", 61, effective=reference.isoformat()),
    )
    # Ni lo que anota otro tripulante.
    seeded.post(
        "/api/observations",
        json={**_body(catalog, "appetite-rating", 9.0), "subject": "crew-02"},
    )

    payload = seeded.get("/api/diary/entries").json()
    assert [item["value"] for item in payload["entries"]] == [5.0, 3.0]
    assert payload["count"] == 2
    assert seeded.get("/api/diary/entries", params={"limit": 1}).json()["count"] == 2
    assert len(seeded.get("/api/diary/entries", params={"limit": 1}).json()["entries"]) == 1


def test_entry_says_where_it_falls_against_the_analysed_data(seeded: TestClient) -> None:
    catalog = _catalog(seeded)
    reference = dt.datetime.fromisoformat(
        seeded.get("/api/status").json()["data"]["reference_time"]
    )
    for delta in (dt.timedelta(days=-10), dt.timedelta(days=400)):
        seeded.post(
            "/api/observations",
            json=_body(
                catalog, "symptom-burden", 1.0, effective=(reference + delta).isoformat()
            ),
        )
    entries = seeded.get("/api/diary/entries").json()["entries"]
    assert [item["position"] for item in entries] == ["after-reference", "earlier"]
    # Lo mismo que dice el estado: una sola lectura tras un hueco anómalo queda apartada.
    status = seeded.get("/api/status").json()
    assert status["data"]["readings_ignored"]["after_reference"] == 1


def test_entries_of_an_empty_store(client: TestClient) -> None:
    payload = client.get("/api/diary/entries").json()
    assert payload == {
        "subject": "crew-01", "count": 0, "reference_time": None, "entries": [],
    }


# --------------------------------------------------------------------------- #
# Invariante 5: describir el registro no mueve el veredicto
# --------------------------------------------------------------------------- #


def test_reading_the_diary_does_not_change_the_verdict(seeded: TestClient) -> None:
    before = _verdict(seeded)
    assert before[2], "el escenario tiene que dejar alguna alerta que comparar"
    ledger = seeded.get("/api/audit").json()["total_entries"]

    assert seeded.get("/api/diary").status_code == 200
    assert seeded.get("/api/diary/entries").status_code == 200

    assert _verdict(seeded) == before
    # Y no escribe nada: ni una lectura ni un asiento.
    assert seeded.get("/api/audit").json()["total_entries"] == ledger


def test_the_only_diary_route_that_writes_is_the_one_that_signs_an_entry() -> None:
    methods = {
        (path, method)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/diary")
        for method in operations
    }
    assert methods == {
        ("/api/diary", "get"), ("/api/diary/entries", "get"), ("/api/diary/entries", "post"),
    }
