"""La batería Cognition de NASA en la consola (`app/ingest/cognition.py`, `app/api/cognition.py`).

Lo que se fija: las diez pruebas van en su orden con la frase leída de qué mide cada una (y de la
PVT se dice que no la hay y se remite a su consola); una sesión entra firmada con su fuente y con
quién teclea, por el ledger y entera o nada; la ingesta genérica no puede usar la fuente; y
anotar una sesión no mueve el veredicto ni la huella de reglas (descriptivo, invariante 5).
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import cognition as cognition_api
from app.api.cognition import CONSOLE_SOURCE, PVT_PROTOCOL, SUBMIT_TO
from app.api.routes import CONSOLE_IDENTITY, _is_reserved_source, get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.core.versioning import rules_version
from app.evidence import registry
from app.ingest import cognition
from app.ingest.codes import (
    CATALOG,
    COGNITION_CODES,
    COGNITION_KEYS,
    COGNITION_TESTS,
    DESCRIPTIVE_ONLY,
)
from app.ingest.fhir import EvidenceContext
from app.main import app
from app.text_guard import check

OPERATOR = "CDR"
T = dt.datetime(2026, 11, 3, 9, 0, tzinfo=dt.UTC)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
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


def _full() -> dict[str, float]:
    """Una sesión entera: un valor dentro del rango para cada puntuación de las nueve pruebas."""
    return {
        code.key: (850.0 if code.unit == "ms" else 0.75) for code in COGNITION_CODES
    }


def _body(**extra: Any) -> dict[str, Any]:
    return {"scores": _full(), "subject": "crew-01", "recorded_by": OPERATOR, **extra}


def _payloads() -> list[dict[str, Any]]:
    return [dict(entry.payload) for entry in get_store().ledger.entries]


def _protocol(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/cognition/protocol")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _verdict(client: TestClient) -> tuple[Any, ...]:
    status = client.get("/api/status").json()
    return (
        status["overall_level"],
        {key: (item["level"], item["score"]) for key, item in status["domains"].items()},
        [(item["id"], item["level"]) for item in status["alerts"]],
    )


def _texts(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _texts(item)
    elif isinstance(value, list):
        for item in value:
            yield from _texts(item)


# --------------------------------------------------------------------------- #
# El protocolo: las diez pruebas, con lo leído de cada una
# --------------------------------------------------------------------------- #


def test_the_ten_tests_go_in_the_published_order_of_administration(client: TestClient) -> None:
    tests = _protocol(client)["tests"]
    assert [item["sigla"] for item in tests] == [
        "MPT", "VOLT", "F2B", "AM", "LOT", "ERT", "MRT", "DSST", "BART", "PVT",
    ]
    assert [item["order"] for item in tests] == list(range(1, 11))
    # El orden es el que escribe la fuente (Basner et al. 2015, pie de la figura 1).
    [order] = [
        item for item in _protocol(client)["battery"] if item["id"] == "basner-standard-order"
    ]
    quote = order["quote"]
    positions = [quote.index(f"({item['sigla'] if item['sigla'] != 'MPT' else 'MP'})")
                 for item in tests]
    assert positions == sorted(positions)


def test_each_of_the_nine_says_what_it_measures_with_its_read_statement(
    client: TestClient,
) -> None:
    nine = _protocol(client)["tests"][:9]
    for item, test in zip(nine, COGNITION_TESTS, strict=True):
        measures = item["measures"]
        assert measures["id"] == f"cog-test-{test.abbrev}"
        assert measures["ref"] == "dev-2024-cognition-iss"
        assert f"({test.sigla})" in measures["quote"]
        # La ficha existe en el registro de evidencia y se sirve con su cita.
        assert registry.get(measures["ref"]).url == measures["url"]
        assert measures["read_on"] and measures["where"]
        assert (item["recorded_here"], item["measures_note"], item["console"]) == (
            True, None, None)


def test_the_pvt_has_no_read_statement_here_and_points_to_its_console(
    client: TestClient,
) -> None:
    pvt = _protocol(client)["tests"][-1]
    assert (pvt["measures"], pvt["recorded_here"], pvt["fields"]) == (None, False, [])
    assert "no hay ninguna" in pvt["measures_note"]
    assert pvt["console"] == PVT_PROTOCOL
    assert client.get(pvt["console"]).status_code == 200


def test_the_fields_are_exactly_the_catalogue_codes_with_their_ranges(
    client: TestClient,
) -> None:
    tests = _protocol(client)["tests"]
    fields = [item for test in tests for item in test["fields"]]
    assert [item["key"] for item in fields] == [code.key for code in COGNITION_CODES]
    for item in fields:
        code = CATALOG[item["key"]]
        assert (item["physical_min"], item["physical_max"], item["unit"]) == (
            code.physical_min, code.physical_max, code.unit)
        assert item["display_es"] == code.display_es
        assert item["statement"]["quote"]
    # La MPT no tiene precisión, y lo dice con su frase; la BART da riesgo, no precisión.
    mpt, bart = tests[0], tests[8]
    assert [item["measure"] for item in mpt["fields"]] == ["speed"]
    assert mpt["no_accuracy"]["id"] == "cog-mpt-no-accuracy"
    assert [item["measure"] for item in bart["fields"]] == ["speed", "risk"]
    assert bart["fields"][1]["statement"]["id"] == "cog-bart-risk"
    # El F2B y el LOT, con la frase de su proporción; las otras cinco, con la común.
    by_key = {item["key"]: item["statement"]["id"] for item in fields}
    assert by_key["cognition-f2b-accuracy"] == "cog-f2b-accuracy"
    assert by_key["cognition-lot-accuracy"] == "cog-lot-accuracy"
    assert by_key["cognition-dsst-accuracy"] == "cog-accuracy-proportion"
    assert by_key["cognition-volt-speed"] == "cog-speed-definition"


def test_the_texts_neither_prescribe_nor_claim_validation(client: TestClient) -> None:
    protocol = _protocol(client)
    own = [
        protocol["title"], protocol["identity"], protocol["scope"], *protocol["limits"],
        protocol["provenance"]["effective_note"], protocol["tests"][-1]["measures_note"],
        protocol["tests"][-1]["console_note"],
    ]
    for text in own:
        assert check(text) == [], text
        assert "valida" not in text.lower() and "certific" not in text.lower(), text
    assert "no pasa las pruebas" in protocol["identity"]
    assert "ninguna norma" in protocol["scope"]


def test_the_provenance_is_the_one_the_route_signs_with(client: TestClient) -> None:
    protocol = _protocol(client)
    provenance = protocol["provenance"]
    assert provenance["source"] == CONSOLE_SOURCE == "console-cognition" != CONSOLE_IDENTITY
    assert provenance["source_display"] == "batería Cognition en la consola"
    assert (provenance["observation_type"], provenance["evidence_context"]) == (
        "measured", "ground")
    assert protocol["submit_to"] == SUBMIT_TO
    assert protocol["recorded_by"]["required"] is True
    assert protocol["not_found"], "lo buscado y no leído se dice"


# --------------------------------------------------------------------------- #
# Registrar una sesión: firmada, por el ledger, entera o nada
# --------------------------------------------------------------------------- #


def test_a_session_is_signed_with_its_source_and_operator_and_read_back(
    client: TestClient,
) -> None:
    started = dt.datetime.now(dt.UTC)
    response = client.post(SUBMIT_TO, json=_body())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["keys"] == [code.key for code in COGNITION_CODES]
    assert (body["source"], body["recorded_by"]) == (CONSOLE_SOURCE, OPERATOR)

    audit = client.get("/api/audit", params={"limit": 500}).json()
    assert audit["total_entries"] == len(COGNITION_CODES)
    assert audit["integrity_ok"] is True
    assert {entry["signer"] for entry in audit["entries"]} == {CONSOLE_SOURCE}
    assert sorted(body["recorded"]) == sorted(entry["index"] for entry in audit["entries"])
    payloads = _payloads()
    assert {(p["source"], p["subject"], p["recorded_by"]) for p in payloads} == {
        (CONSOLE_SOURCE, "crew-01", OPERATOR)}

    sessions = client.get("/api/cognition/sessions").json()
    assert sessions["count"] == 1
    [session] = sessions["sessions"]
    assert [item["key"] for item in session["values"]] == body["keys"]
    assert (session["recorded_by"], session["position"]) == (OPERATOR, "descriptive")
    assert session["source_display"] == "batería Cognition en la consola"
    assert session["values"][0]["value_text"] == "850 ms"
    received = dt.datetime.fromisoformat(session["effective"])
    assert started <= received <= dt.datetime.now(dt.UTC)


def test_a_session_may_bring_fewer_tests_but_each_one_whole(client: TestClient) -> None:
    scores = {"cognition-mpt-speed": 640.0, "cognition-bart-speed": 1200.0,
              "cognition-bart-risk": 0.4}
    response = client.post(SUBMIT_TO, json=_body(scores=scores))
    assert response.status_code == 201, response.text
    # En el orden del catálogo, no en el que llegaron.
    assert response.json()["keys"] == list(scores)
    assert [p["key"] for p in _payloads()] == list(scores)


@pytest.mark.parametrize(
    ("body", "said"),
    [
        ({"scores": _full(), "subject": "crew-01"}, "recorded_by"),
        (_body(recorded_by=""), "recorded_by"),
        (_body(recorded_by="..."), "recorded_by"),
        (_body(source="nasa-app"), "source"),
        (_body(effective="2026-09-01T08:00:00+00:00"), "effective"),
        (_body(subject=""), "subject"),
        (_body(scores={}), "scores"),
        (_body(scores={"cognition-mpt-speed": "rápido"}), "scores"),
        (_body(scores={"cognition-mpt-speed": True}), "no es una cifra"),
        (_body(scores={"cognition-mpt-speed": 0}), "fuera del rango"),
        (_body(scores={"cognition-mpt-speed": 60001}), "fuera del rango"),
        (_body(scores={**_full(), "cognition-volt-accuracy": 1.2}), "fuera del rango"),
        (_body(scores={**_full(), "cognition-bart-risk": -0.1}), "fuera del rango"),
        (_body(scores={"cognition-volt-speed": 900}), "todas sus puntuaciones"),
        (_body(scores={"cognition-mpt-accuracy": 0.5}), "no es una puntuación"),
        (_body(scores={**_full(), "pvt-mean-rt": 280}), "/api/pvt/console"),
        (_body(scores={**_full(), "heart-rate": 60}), "no es una puntuación"),
    ],
)
def test_an_invalid_session_is_refused_and_leaves_nothing(
    client: TestClient, body: dict[str, Any], said: str
) -> None:
    response = client.post(SUBMIT_TO, json=body)
    assert response.status_code == 422, body
    assert said in response.text
    assert client.get("/api/audit").json()["total_entries"] == 0


def test_a_non_finite_score_is_refused(client: TestClient) -> None:
    raw = json.dumps(_body(scores={"cognition-mpt-speed": float("nan")}))
    response = client.post(SUBMIT_TO, content=raw, headers={"content-type": "application/json"})
    assert response.status_code == 422
    assert client.get("/api/audit").json()["total_entries"] == 0


def test_every_reason_is_said_at_once(client: TestClient) -> None:
    scores = {"cognition-volt-speed": 0, "cognition-f2b-speed": 500, "x": 1}
    detail = client.post(SUBMIT_TO, json=_body(scores=scores)).json()["detail"]
    assert "VOLT" in detail and "F2B" in detail and "x:" in detail and "fuera del rango" in detail


def test_the_generic_ingest_cannot_sign_as_this_console(client: TestClient) -> None:
    assert _is_reserved_source(CONSOLE_SOURCE)
    response = client.post(
        "/api/observations",
        json={"key": "cognition-mpt-speed", "value": 600, "source": CONSOLE_SOURCE},
    )
    assert response.status_code == 422
    assert client.get("/api/audit").json()["total_entries"] == 0


def test_it_signs_with_the_deployment_context(client: TestClient, tmp_path: Path) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, deployment_context=EvidenceContext.ISS
    )
    assert client.post(SUBMIT_TO, json=_body()).status_code == 201
    assert {p["evidence_context"] for p in _payloads()} == {"iss"}


# --------------------------------------------------------------------------- #
# Las sesiones del registro
# --------------------------------------------------------------------------- #


def test_sessions_are_grouped_newest_first_and_keep_their_source(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    for hours in (30, 2, 80):
        moment = T - dt.timedelta(hours=hours)
        monkeypatch.setattr(cognition_api, "_received", lambda moment=moment: moment)
        assert client.post(SUBMIT_TO, json=_body()).status_code == 201
    # Una lectura de la batería por la ingesta genérica, con otra fuente: otra sesión, sin
    # quién la tecleó.
    assert client.post(
        "/api/observations",
        json={"key": "cognition-mpt-speed", "value": 610, "source": "manual",
              "effective": T.isoformat()},
    ).status_code == 201
    monkeypatch.setattr(cognition_api, "_received", lambda: T)
    assert client.post(SUBMIT_TO, json=_body(subject="crew-02")).status_code == 201

    payload = client.get("/api/cognition/sessions").json()
    assert payload["count"] == 4
    hours_ago = [
        round((T - dt.datetime.fromisoformat(item["effective"])).total_seconds() / 3600)
        for item in payload["sessions"]
    ]
    assert hours_ago == [0, 2, 30, 80]
    manual = payload["sessions"][0]
    assert (manual["source"], manual["recorded_by"], manual["recorded_by_display"]) == (
        "manual", None, "no consta")
    assert len(payload["sessions"][1]["values"]) == len(COGNITION_CODES)
    limited = client.get("/api/cognition/sessions", params={"limit": 1}).json()
    assert (limited["count"], len(limited["sessions"])) == (4, 1)
    assert client.get(
        "/api/cognition/sessions", params={"subject": "crew-02"}).json()["count"] == 1


def test_sessions_of_an_empty_store(client: TestClient) -> None:
    assert client.get("/api/cognition/sessions").json() == {
        "subject": "crew-01", "count": 0, "reference_time": None, "sessions": [],
    }


# --------------------------------------------------------------------------- #
# Invariante 5: descriptivo, fuera del veredicto y de la huella
# --------------------------------------------------------------------------- #


def test_every_score_is_descriptive() -> None:
    assert COGNITION_KEYS <= DESCRIPTIVE_ONLY
    assert {item.key for item in cognition.FIELDS} == COGNITION_KEYS


def test_a_session_does_not_move_the_verdict_nor_the_rules(
    seeded: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = dt.datetime.fromisoformat(
        seeded.get("/api/status").json()["data"]["reference_time"]
    )
    before, version = _verdict(seeded), rules_version()
    assert before[2], "el escenario tiene que dejar alguna alerta que comparar"
    # Con la hora de los datos, dentro de la ventana del estado: si el estado las leyera, aquí.
    worst = {
        code.key: float(code.physical_max if code.concerning == "high" else code.physical_min)
        for code in COGNITION_CODES
        if code.physical_max is not None and code.physical_min is not None
    }
    monkeypatch.setattr(cognition_api, "_received", lambda: reference - dt.timedelta(hours=1))
    assert seeded.post(SUBMIT_TO, json=_body(scores=worst)).status_code == 201
    assert _verdict(seeded) == before
    assert rules_version() == version
    assert seeded.get("/api/cognition/protocol").status_code == 200
    # La lista de sesiones solo cuenta la batería, no las lecturas simuladas de alrededor.
    sessions = seeded.get("/api/cognition/sessions").json()
    assert sessions["count"] == 1
    assert {item["key"] for item in sessions["sessions"][0]["values"]} == set(worst)


@pytest.mark.parametrize(
    ("scores", "said"),
    [
        ({}, "ninguna puntuación"),
        ({"cognition-mpt-speed": True}, "no es una cifra"),
        ({"cognition-mpt-speed": "600"}, "no es una cifra"),
        ({"cognition-mpt-speed": float("nan")}, "no es una cifra finita"),
        ({"cognition-mpt-speed": float("inf")}, "no es una cifra finita"),
        (
            {"cognition-mpt-speed": 0.5},
            "fuera del rango físico del catálogo, desde 1 y hasta 60 000 ms",
        ),
    ],
)
def test_the_ingest_rule_refuses_on_its_own(scores: dict[str, Any], said: str) -> None:
    """La regla de la ingesta no cuenta con que el modelo de la ruta ya filtró."""
    found = cognition.problems(scores)
    assert any(said in line for line in found), found
    with pytest.raises(cognition.InvalidSession):
        cognition.to_observations(scores, "crew-01", T, CONSOLE_SOURCE)


def test_the_ingest_builds_catalogue_observations_in_catalogue_order() -> None:
    scores = {"cognition-bart-risk": 0.3, "cognition-bart-speed": 900.0,
              "cognition-mpt-speed": 500}
    built = cognition.to_observations(scores, "crew-01", T, CONSOLE_SOURCE)
    assert [item.key for item in built] == [
        "cognition-mpt-speed", "cognition-bart-speed", "cognition-bart-risk"]
    assert {(item.source, item.subject, item.effective) for item in built} == {
        (CONSOLE_SOURCE, "crew-01", T)}
    assert built[0].value == 500.0


def test_the_module_writes_only_through_its_own_route() -> None:
    paths = app.openapi()["paths"]
    assert {path for path in paths if path.startswith("/api/cognition")} == {
        "/api/cognition/protocol", "/api/cognition/console", "/api/cognition/sessions",
    }
    assert set(paths["/api/cognition/protocol"]) == {"get"}
    assert set(paths["/api/cognition/sessions"]) == {"get"}
    assert set(paths["/api/cognition/console"]) == {"post"}
