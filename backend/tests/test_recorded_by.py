"""Quién anota: fuente propia y operador firmado en el registro diario y en la PVT de consola.

Decisión del usuario, 2026-10-13.

Hasta entonces el diario firmaba como «alta manual» y la PVT hecha en pantalla como cualquier
PVT que llegara por la API, y la lectura decía de qué tripulante era el dato pero no quién lo
había tecleado. Estas pruebas fijan lo que la pieza nueva es y lo que no puede romper:

  * la fuente la pone el backend en una ruta propia; la ingesta genérica no puede usarla, y
    `crew-console` sigue sin poder firmar una lectura;
  * el operador es un campo OPCIONAL de la lectura: sin él se firma byte a byte como antes, y lo
    firmado antes del cambio sigue verificándose y enseñándose («no consta», no se rellena);
  * invariante 5: los mismos valores dan el mismo estado con una fuente o con la otra;
  * el nombre se firma en el ledger y no se escribe en el log.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import logging
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import data_quality
from app.api import diary as diary_module
from app.api import pvt_console
from app.api.diary import DIARY_SOURCE, LEGACY_SOURCE, NOT_RECORDED
from app.api.pvt_console import CONSOLE_SOURCE, PVT_SOURCE, RECORDED_KEYS, SESSION_TRIALS
from app.api.routes import CONSOLE_IDENTITY, get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.core.ledger import SALT_FIELD, Identity, canonical_bytes, sha256_hex
from app.core.storage import ObservationStore, _from_payload, _to_payload
from app.core.versioning import rules_version
from app.ingest.fhir import EvidenceContext, VitalObservation, annotated_by, observation
from app.main import app

T = dt.datetime(2026, 9, 1, 8, 0, tzinfo=dt.UTC)
OPERATOR = "Itziar Olabarria"
# Ledger con dos anotaciones del diario (`manual`) y una PVT (`pvt-test`), escrito con el
# código ANTERIOR a este cambio (commit 82ea87d, exportado con `git archive` a una carpeta
# aparte) y guardado tal cual. Los hashes son los que firmó aquel código; el `.fhir.json` es
# lo que aquel código serializaba.
DATA = Path(__file__).parent / "data"
PRE_CHANGE_LEDGER = DATA / "diary_pvt_pre_recorded_by.db"
PRE_CHANGE_FHIR = DATA / "diary_pvt_pre_recorded_by.fhir.json"
PRE_CHANGE_HASHES = [
    "9b811159482399e605188a084b2d967a8cb2da9b0ca63f736f3339345ba04b8a",
    "8bc2f50ef563249468c00e5ec80e9041ad3f9eef0b88b15376af081bc6f381c8",
    "4bd38ed82615468543a52729ec1b1cf16e8ee754ac4cd7a02c57149d23a2ca4e",
    "8574dc0a79d70e65aad09b2c4d14d65157430d54bd158d4f9d9f333f5cd4796d",
]
TIMES = [250.0] * (SESSION_TRIALS - 3) + [620.0, 700.0, 0.0]


def _reading(recorded_by: str | None = None, minute: int = 0) -> VitalObservation:
    return observation(
        "mood-valence", 6.5, T + dt.timedelta(minutes=minute), "crew-02", DIARY_SOURCE,
        recorded_by=recorded_by,
    )


def _signed_payloads(store: ObservationStore) -> list[dict[str, Any]]:
    return [dict(entry.payload) for entry in store.ledger.entries]


@pytest.fixture
def pre_change(tmp_path: Path) -> Iterator[ObservationStore]:
    path = tmp_path / "emma.db"
    shutil.copyfile(PRE_CHANGE_LEDGER, path)
    store = ObservationStore.at(path)
    yield store
    store.engine.dispose()


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _entry(key: str = "mood-valence", value: float = 6.5, **extra: Any) -> dict[str, Any]:
    """Lo que envía el panel del diario: sin fuente ni hora, y con quién anota."""
    return {"key": key, "value": value, "subject": "crew-01", "recorded_by": OPERATOR, **extra}


def _test(**extra: Any) -> dict[str, Any]:
    """Lo que envía el panel de la PVT al acabar una prueba."""
    return {
        "reaction_times_ms": TIMES, "subject": "crew-01", "recorded_by": OPERATOR, **extra,
    }


# --------------------------------------------------------------------------- #
# Lo ya firmado
# --------------------------------------------------------------------------- #


def test_what_was_signed_before_the_field_still_verifies(pre_change: ObservationStore) -> None:
    assert pre_change.verify_integrity().ok
    assert [e["content_hash"] for e in pre_change.audit_trail()] == PRE_CHANGE_HASHES
    readings = pre_change.query("crew-01")
    assert [(obs.key, obs.source) for obs in readings] == [
        ("mood-valence", "manual"), ("appetite-rating", "manual"),
        ("pvt-mean-rt", "pvt-test"), ("pvt-lapses", "pvt-test"),
    ]
    assert all(obs.recorded_by is None for obs in readings)


def test_a_reading_nobody_annotated_serializes_byte_for_byte_as_before(
    pre_change: ObservationStore,
) -> None:
    """Con el código de ahora, cada lectura antigua produce los bytes que firmó el de antes."""
    payloads = _signed_payloads(pre_change)
    assert len(payloads) == 4
    for payload, signed in zip(payloads, PRE_CHANGE_HASHES, strict=True):
        obs = _from_payload(payload, dt.datetime.fromisoformat(payload["effective"]))
        again = _to_payload(obs)
        assert "recorded_by" not in again
        assert list(again) == [key for key in payload if key != SALT_FIELD]
        assert sha256_hex(canonical_bytes({**again, SALT_FIELD: payload[SALT_FIELD]})) == signed

    # Y el FHIR: lo que serializaba `main`, carácter a carácter (también el orden de claves).
    # Lo de antes se exporta con los URI de hoy: hasta 2026-11-02 eran `https://halo.mission/`
    # (el fixture los conserva tal cual se grabaron) y el FHIR los traduce al leer.
    expected = json.loads(
        PRE_CHANGE_FHIR.read_text(encoding="utf-8").replace(
            "https://halo.mission/", "https://emma.mission/")
    )
    readings = pre_change.query("crew-01")
    assert [json.dumps(obs.to_fhir(), ensure_ascii=False) for obs in readings] == expected
    assert all("performer" not in obs.to_fhir() for obs in readings)


def test_new_annotated_readings_chain_after_the_old_ones(
    pre_change: ObservationStore, tmp_path: Path
) -> None:
    pre_change.record_many(
        [_reading(OPERATOR, 5), _reading(None, 6)], Identity.generate(DIARY_SOURCE)
    )
    assert pre_change.verify_integrity().ok
    pre_change.engine.dispose()

    reopened = ObservationStore.at(tmp_path / "emma.db")
    try:
        assert reopened.verify_integrity().ok
        assert [e["content_hash"] for e in reopened.audit_trail()][:4] == PRE_CHANGE_HASHES
        assert [obs.recorded_by for obs in reopened.query("crew-02")] == [OPERATOR, None]
    finally:
        reopened.engine.dispose()


def test_the_old_entries_are_still_listed_with_their_source_and_no_annotator(
    client: TestClient, tmp_path: Path
) -> None:
    """Por la API, sobre el ledger antiguo: se enseñan, dicen su fuente, y «no consta»."""
    path = tmp_path / "old.db"
    shutil.copyfile(PRE_CHANGE_LEDGER, path)
    store = ObservationStore.at(path)
    reset_store(store)
    try:
        entries = client.get("/api/diary/entries").json()
        assert entries["count"] == 2
        assert [
            (item["key"], item["value"], item["source"], item["source_display"])
            for item in entries["entries"]
        ] == [
            ("appetite-rating", 4.0, "manual", "alta manual"),
            ("mood-valence", 6.5, "manual", "alta manual"),
        ]
        assert all(item["recorded_by"] is None for item in entries["entries"])
        assert all(item["recorded_by_display"] == "no consta" for item in entries["entries"])

        sessions = client.get("/api/pvt/sessions").json()
        assert sessions["count"] == 1
        [session] = sessions["sessions"]
        assert (session["source"], session["source_display"]) == ("pvt-test", "test PVT")
        assert (session["recorded_by"], session["recorded_by_display"]) == (None, "no consta")
        assert [item["key"] for item in session["values"]] == list(RECORDED_KEYS)

        # Y lo nuevo se anexa detrás, en la misma cadena, con su fuente y su operador.
        assert client.post("/api/diary/entries", json=_entry()).status_code == 201
        assert client.post("/api/pvt/console", json=_test()).status_code == 201
        audit = client.get("/api/audit", params={"limit": 50}).json()
        assert audit["integrity_ok"] is True
        assert [e["content_hash"] for e in store.audit_trail()][:4] == PRE_CHANGE_HASHES
        listed = client.get("/api/diary/entries").json()["entries"]
        assert [(item["source"], item["recorded_by_display"]) for item in listed] == [
            (DIARY_SOURCE, OPERATOR), ("manual", "no consta"), ("manual", "no consta"),
        ]
        tests = client.get("/api/pvt/sessions").json()["sessions"]
        assert [(item["source"], item["recorded_by_display"]) for item in tests] == [
            (CONSOLE_SOURCE, OPERATOR), ("pvt-test", "no consta"),
        ]
    finally:
        reset_store(None)
        store.engine.dispose()


# --------------------------------------------------------------------------- #
# El campo
# --------------------------------------------------------------------------- #


def test_the_annotator_is_signed_only_when_it_exists() -> None:
    without, with_name = _to_payload(_reading()), _to_payload(_reading(OPERATOR))
    assert "recorded_by" not in without
    assert with_name == {**without, "recorded_by": OPERATOR}
    # Es parte de lo firmado: otro nombre, otro hash.
    assert canonical_bytes(with_name) != canonical_bytes(without)
    assert canonical_bytes(with_name) != canonical_bytes(_to_payload(_reading("otra persona")))
    # Y no es el sujeto: de quién es el dato y quién lo teclea son dos claves distintas.
    assert (with_name["subject"], with_name["recorded_by"]) == ("crew-02", OPERATOR)


def test_fhir_carries_it_as_a_performer_with_a_name_and_no_invented_identifier() -> None:
    plain, named = _reading().to_fhir(), _reading(OPERATOR).to_fhir()
    assert "performer" not in plain
    # Solo `display`: ni `reference` a un recurso que no existe, ni `identifier` con sistema.
    assert named["performer"] == [{"display": OPERATOR}]
    assert {key: value for key, value in named.items() if key != "performer"} == plain
    assert named["subject"] == {"reference": "Patient/crew-02"}
    assert VitalObservation.from_fhir(named).recorded_by == OPERATOR
    assert VitalObservation.from_fhir(plain).recorded_by is None
    assert VitalObservation.from_fhir(named) == _reading(OPERATOR)
    # El recurso sigue validando contra el esquema FHIR R4B real.
    assert _reading(OPERATOR).validates()


@pytest.mark.parametrize("bad", ["", "   ", 7])
def test_an_empty_or_non_text_name_is_not_an_annotator(bad: object) -> None:
    with pytest.raises(ValueError, match="quien anota"):
        _reading(bad)  # type: ignore[arg-type]


def test_annotated_by_names_every_reading_of_the_batch() -> None:
    batch = [_reading(), _reading(minute=1)]
    named = annotated_by(batch, OPERATOR)
    assert [obs.recorded_by for obs in named] == [OPERATOR, OPERATOR]
    assert [obs.recorded_by for obs in batch] == [None, None]
    assert [(o.key, o.value, o.effective, o.source) for o in named] == [
        (o.key, o.value, o.effective, o.source) for o in batch
    ]


def test_the_annotator_survives_the_store_and_is_read_from_what_was_signed(
    tmp_path: Path,
) -> None:
    store = ObservationStore.at(tmp_path / "emma.db")
    try:
        store.record_many(
            [_reading(OPERATOR), _reading(None, 1)], Identity.generate(DIARY_SOURCE)
        )
        assert store.verify_integrity().ok
        assert [obs.recorded_by for obs in store.query("crew-02")] == [OPERATOR, None]
        assert [("recorded_by" in p) for p in _signed_payloads(store)] == [True, False]
    finally:
        store.engine.dispose()


# --------------------------------------------------------------------------- #
# El diario: fuente propia, puesta por el backend, y quién anota
# --------------------------------------------------------------------------- #


def test_a_diary_entry_is_signed_with_its_own_source_and_its_annotator(
    client: TestClient,
) -> None:
    started = dt.datetime.now(dt.UTC)
    response = client.post("/api/diary/entries", json=_entry(recorded_by=f"  {OPERATOR} "))
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["source"], body["source_display"]) == ("crew-diary", "registro diario")
    assert body["recorded_by"] == OPERATOR

    [payload] = _signed_payloads(get_store())
    assert (payload["source"], payload["subject"], payload["recorded_by"]) == (
        "crew-diary", "crew-01", OPERATOR)
    assert (payload["key"], payload["value"]) == ("mood-valence", 6.5)
    assert (payload["observation_type"], payload["evidence_context"]) == ("measured", "ground")
    # La hora es la de recepción: la consola no envía ninguna.
    assert started <= dt.datetime.fromisoformat(payload["effective"]) <= dt.datetime.now(dt.UTC)

    audit = client.get("/api/audit").json()
    assert audit["integrity_ok"] is True
    [entry] = audit["entries"]
    assert (entry["index"], entry["signer"]) == (body["ledger_index"], "crew-diary")
    assert entry["signer"] != CONSOLE_IDENTITY

    [listed] = client.get("/api/diary/entries").json()["entries"]
    assert (listed["source"], listed["source_display"]) == ("crew-diary", "registro diario")
    assert (listed["recorded_by"], listed["recorded_by_display"]) == (OPERATOR, OPERATOR)
    # Y sale en el FHIR que entrega la API, como quien responde de la observación.
    [fhir] = client.get("/api/observations").json()["observations"]
    assert fhir["performer"] == [{"display": OPERATOR}]
    assert fhir["device"] == {"display": "crew-diary"}


def test_the_diary_says_who_must_annotate_and_how_a_missing_one_is_named(
    client: TestClient,
) -> None:
    catalog = client.get("/api/diary").json()
    assert catalog["submit_to"] == "/api/diary/entries"
    assert (catalog["provenance"]["source"], catalog["provenance"]["source_display"]) == (
        "crew-diary", "registro diario")
    told = catalog["recorded_by"]
    assert told["required"] is True
    assert told["missing_display"] == NOT_RECORDED == "no consta"
    assert "no autentica" in told["note"]
    assert "«alta manual»" in told["legacy_note"]
    assert any("con el nombre de quien lo anota" in note for note in catalog["notes"])


@pytest.mark.parametrize(
    "body",
    [
        {"key": "mood-valence", "value": 6.5, "subject": "crew-01"},
        _entry(recorded_by=""),
        _entry(recorded_by="   "),
        _entry(recorded_by="—"),
        _entry(recorded_by="x" * 65),
        _entry(recorded_by=None),
        # La fuente, la hora y el tipo los pone el backend: enviarlos es un 422, no se ignoran.
        _entry(source="manual"),
        _entry(source="crew-console"),
        _entry(effective="2026-09-01T08:00:00+00:00"),
        _entry(observation_type="inferred"),
        # Solo indicadores del diario; y de un tripulante dicho.
        _entry(key="heart-rate", value=61),
        _entry(key="pain-intensity", value=3),
        _entry(key="no-existe"),
        _entry(subject=""),
        {"key": "mood-valence", "value": 6.5, "recorded_by": OPERATOR},
        _entry(value=11),
    ],
)
def test_a_diary_entry_without_a_named_annotator_or_out_of_its_lane_is_refused(
    client: TestClient, body: dict[str, Any]
) -> None:
    assert client.post("/api/diary/entries", json=body).status_code == 422, body
    assert client.get("/api/audit").json()["total_entries"] == 0


@pytest.mark.parametrize("source", [DIARY_SOURCE, CONSOLE_SOURCE, CONSOLE_IDENTITY])
def test_the_generic_ingestion_cannot_sign_as_the_console_sources(
    client: TestClient, source: str
) -> None:
    """Ni las fuentes nuevas (entrarían sin anotador) ni la identidad de la consola."""
    refused = client.post(
        "/api/observations", json={"key": "mood-valence", "value": 6.5, "source": source}
    )
    assert refused.status_code == 422
    assert "identidad reservada" in refused.text
    # La ruta genérica tampoco admite el campo: nadie se nombra anotador por ahí.
    extra = client.post(
        "/api/observations", json={"key": "mood-valence", "value": 6.5, "recorded_by": "X"}
    )
    assert extra.status_code == 422
    assert client.get("/api/audit").json()["total_entries"] == 0


def test_a_manual_entry_still_goes_in_and_carries_no_annotator(client: TestClient) -> None:
    """El resto de la ingesta no lleva el campo, y el diario la enseña como lo que es."""
    assert client.post(
        "/api/observations", json={"key": "mood-valence", "value": 4.0}
    ).status_code == 201
    [payload] = _signed_payloads(get_store())
    assert payload["source"] == LEGACY_SOURCE == "manual"
    assert "recorded_by" not in payload
    [listed] = client.get("/api/diary/entries").json()["entries"]
    assert (listed["source_display"], listed["recorded_by_display"]) == (
        "alta manual", "no consta")


def test_an_amended_diary_entry_is_a_manual_correction_without_annotator(
    client: TestClient,
) -> None:
    """Límite declarado (§3.14 ter): la enmienda la firma su propia fuente, sin anotador."""
    index = client.post("/api/diary/entries", json=_entry()).json()["ledger_index"]
    amended = client.post(
        f"/api/audit/amend/{index}",
        json={
            "reason": "valor mal tecleado",
            "correction": {
                "key": "mood-valence", "value": 5.5, "effective": T.isoformat(),
            },
        },
    )
    assert amended.status_code == 200, amended.text
    [listed] = client.get("/api/diary/entries").json()["entries"]
    assert (listed["value"], listed["source"], listed["recorded_by_display"]) == (
        5.5, "manual", "no consta")
    # La original, con su fuente y su operador, sigue firmada en la cadena.
    original = _signed_payloads(get_store())[index]
    assert (original["source"], original["recorded_by"]) == ("crew-diary", OPERATOR)


# --------------------------------------------------------------------------- #
# La PVT hecha en pantalla
# --------------------------------------------------------------------------- #


def test_a_console_pvt_is_signed_with_its_own_source_and_its_operator(
    client: TestClient,
) -> None:
    response = client.post("/api/pvt/console", json=_test())
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["source"], body["source_display"]) == ("console-pvt", "test PVT en la consola")
    assert body["recorded_by"] == OPERATOR
    # La misma puntuación que la ruta de siempre da a los mismos tiempos.
    plain = client.post("/api/pvt", json={"reaction_times_ms": TIMES, "subject": "crew-02"})
    assert plain.json()["result"] == body["result"]

    payloads = _signed_payloads(get_store())
    console, generic = payloads[:2], payloads[2:]
    assert [p["key"] for p in console] == list(RECORDED_KEYS)
    assert {(p["source"], p["subject"], p["recorded_by"]) for p in console} == {
        ("console-pvt", "crew-01", OPERATOR)}
    # `POST /api/pvt` no cambia: su fuente de siempre y ningún operador.
    assert {p["source"] for p in generic} == {PVT_SOURCE} == {"pvt-test"}
    assert all("recorded_by" not in p for p in generic)
    signers = [entry["signer"] for entry in client.get("/api/audit").json()["entries"]]
    assert sorted(set(signers)) == ["console-pvt", "pvt-test"]

    [session] = client.get("/api/pvt/sessions").json()["sessions"]
    assert (session["source"], session["recorded_by"]) == ("console-pvt", OPERATOR)
    [other] = client.get("/api/pvt/sessions", params={"subject": "crew-02"}).json()["sessions"]
    assert (other["source"], other["recorded_by"], other["recorded_by_display"]) == (
        "pvt-test", None, "no consta")


def test_the_protocol_says_who_must_be_named(client: TestClient) -> None:
    protocol = client.get("/api/pvt/protocol").json()
    assert protocol["submit_to"] == "/api/pvt/console"
    # La procedencia que anuncia es la que su ruta firma, no la de la ruta de siempre.
    assert (protocol["provenance"]["source"], protocol["provenance"]["source_display"]) == (
        "console-pvt", "test PVT en la consola")
    told = protocol["recorded_by"]
    assert (told["required"], told["missing_display"]) == (True, "no consta")
    assert "«test PVT»" in told["legacy_note"]


@pytest.mark.parametrize(
    "body",
    [
        {"reaction_times_ms": TIMES, "subject": "crew-01"},
        _test(recorded_by=""),
        _test(recorded_by="  "),
        _test(recorded_by="..."),
        _test(recorded_by="x" * 65),
        _test(source="pvt-test"),
        _test(effective="2026-09-01T08:00:00+00:00"),
        _test(subject=""),
        {"reaction_times_ms": TIMES, "recorded_by": OPERATOR},
        _test(reaction_times_ms=[]),
        _test(reaction_times_ms=[250.0] * 3),
    ],
)
def test_a_console_pvt_without_a_named_operator_is_refused(
    client: TestClient, body: dict[str, Any]
) -> None:
    assert client.post("/api/pvt/console", json=body).status_code == 422, body
    assert client.get("/api/audit").json()["total_entries"] == 0


def test_two_tests_at_the_same_instant_from_different_sources_are_two_sessions(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pvt_console, "_received", lambda: T)
    assert client.post("/api/pvt/console", json=_test()).status_code == 201
    assert client.post(
        "/api/pvt", json={"reaction_times_ms": TIMES, "effective": T.isoformat()}
    ).status_code == 201
    payload = client.get("/api/pvt/sessions").json()
    assert payload["count"] == 2
    assert sorted(item["source"] for item in payload["sessions"]) == ["console-pvt", "pvt-test"]
    assert all(len(item["values"]) == len(RECORDED_KEYS) for item in payload["sessions"])


def test_both_console_routes_sign_with_the_deployment_context(
    client: TestClient, tmp_path: Path
) -> None:
    """El entorno lo pone el despliegue, como en la ingesta de siempre: no se queda en Tierra."""
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, deployment_context=EvidenceContext.ISS
    )
    assert client.post("/api/diary/entries", json=_entry()).status_code == 201
    assert client.post("/api/pvt/console", json=_test()).status_code == 201
    payloads = _signed_payloads(get_store())
    assert [p["source"] for p in payloads] == ["crew-diary", "console-pvt", "console-pvt"]
    assert {p["evidence_context"] for p in payloads} == {"iss"}


# --------------------------------------------------------------------------- #
# Privacidad: el nombre se firma en el ledger y no se escribe en el log
# --------------------------------------------------------------------------- #


def test_the_name_is_signed_and_never_logged(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    assert client.post("/api/diary/entries", json=_entry()).status_code == 201
    assert client.post("/api/pvt/console", json=_test()).status_code == 201
    # También los caminos de rechazo, que es donde se suele anotar lo recibido.
    assert client.post("/api/diary/entries", json=_entry(value=99)).status_code == 422
    assert client.post("/api/diary/entries", json=_entry(key="heart-rate")).status_code == 422
    assert client.post(
        "/api/pvt/console", json=_test(reaction_times_ms=[250.0])
    ).status_code == 422
    assert client.get("/api/diary/entries").status_code == 200
    assert client.get("/api/pvt/sessions").status_code == 200
    assert client.get("/api/status").status_code == 200

    assert sum("recorded_by" in p for p in _signed_payloads(get_store())) == 3
    logged = "\n".join(
        f"{record.getMessage()} {record.args!r} {record.exc_text or ''}"
        for record in caplog.records
    )
    assert OPERATOR not in logged
    assert "Olabarria" not in logged


# --------------------------------------------------------------------------- #
# Invariante 5: ni la fuente ni el operador entran en el análisis
# --------------------------------------------------------------------------- #

# Lo único que puede diferir entre un estado y otro: cómo se llama la fuente.
_SOURCE_WORDS = {
    DIARY_SOURCE: LEGACY_SOURCE,
    CONSOLE_SOURCE: PVT_SOURCE,
    data_quality.source_label(DIARY_SOURCE): data_quality.source_label(LEGACY_SOURCE),
    data_quality.source_label(CONSOLE_SOURCE): data_quality.source_label(PVT_SOURCE),
}
# Una serie que SOLO tiene lo anotado en la consola, para que el veredicto dependa de ello:
# una anotación de ánimo y una PVT cada dos horas, las suficientes para que la línea base
# quede establecida, y al final un ánimo hundido y pruebas llenas de lapsos.
_STEPS = 150
_BAD = 12
_SLOW = [900.0] * (SESSION_TRIALS - 2) + [250.0, 0.0]


def _series(step: int) -> tuple[dt.datetime, float, list[float]]:
    bad = step >= _STEPS - _BAD
    mood = 0.5 if bad else 7.0 + (step % 5) * 0.25
    times = _SLOW if bad else [250.0] * (SESSION_TRIALS - 1) + [250.0 + (step % 7) * 10]
    return T + dt.timedelta(hours=2 * step), mood, times


def _run(client: TestClient, monkeypatch: pytest.MonkeyPatch, console: bool) -> dict[str, Any]:
    """Los mismos valores, a las mismas horas, por las rutas nuevas o por las de siempre."""
    reset_store(new_store())
    for step in range(_STEPS):
        moment, mood, times = _series(step)
        monkeypatch.setattr(diary_module, "_received", lambda moment=moment: moment)
        monkeypatch.setattr(pvt_console, "_received", lambda moment=moment: moment)
        if console:
            sent = [
                client.post("/api/diary/entries", json=_entry(value=mood)),
                client.post("/api/pvt/console", json=_test(reaction_times_ms=times)),
            ]
        else:
            when = moment.isoformat()
            sent = [
                client.post("/api/observations", json={
                    "key": "mood-valence", "value": mood, "source": "manual",
                    "effective": when}),
                client.post("/api/pvt", json={"reaction_times_ms": times, "effective": when}),
            ]
        assert [item.status_code for item in sent] == [201, 201]
    return _without_store_epoch(client.get("/api/status").json(), get_store().epoch)


def _without_store_epoch(value: Any, epoch: int) -> Any:
    """El estado sin `store_epoch`, tras comprobar que es la época de SU almacén.

    `store_epoch` dice de qué almacén es una declaración (la hora en que se abrió, `_next_epoch`;
    `record-integrity.md` §3.20 y §3.28): cada `_run` abre uno nuevo, así que difiere entre las dos
    pasadas sin que la fuente tenga nada que ver. Entra en el estado con la declaración del
    entorno de misión (3b7233b, 2026-11-04). Se comprueba que es exactamente la de ese almacén y
    se quita; todo lo demás se sigue comparando entero.
    """
    if isinstance(value, dict):
        if "store_epoch" in value:
            assert value["store_epoch"] == epoch
        return {
            key: _without_store_epoch(item, epoch)
            for key, item in value.items() if key != "store_epoch"
        }
    if isinstance(value, list):
        return [_without_store_epoch(item, epoch) for item in value]
    return value


def _same_but_for_source_names(value: Any) -> Any:
    """El estado con cada nombre de fuente nueva cambiado por el de la antigua."""
    if isinstance(value, dict):
        merged: dict[str, Any] = {}
        for key, item in value.items():
            name = _SOURCE_WORDS.get(key, key)
            item = _same_but_for_source_names(item)
            # Dos fuentes que pasan a llamarse igual: sus cuentas se suman.
            merged[name] = merged[name] + item if name in merged else item
        return merged
    if isinstance(value, list):
        items = [_same_but_for_source_names(item) for item in value]
        # Solo una lista de nombres de fuente se reordena (el estado las da por orden
        # alfabético); cualquier otra lista se compara en su orden.
        names = set(_SOURCE_WORDS.values())
        if items and all(isinstance(item, str) and item in names for item in items):
            return sorted(items)
        return items
    if isinstance(value, str):
        return _SOURCE_WORDS.get(value, value)
    return value


def test_the_same_values_give_the_same_status_with_either_source(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _run(client, monkeypatch, console=False)
    new = _run(client, monkeypatch, console=True)

    # El veredicto, campo a campo: niveles, puntuaciones, alertas y recomendaciones.
    assert new["overall_level"] == old["overall_level"]
    assert new["domains"] == old["domains"]
    assert new["alerts"] == old["alerts"]
    assert new["recommendations"] == old["recommendations"]
    assert new["rules_version"] == old["rules_version"] == rules_version()
    assert new["data"]["reference_time"] == old["data"]["reference_time"]
    assert new["data"]["readings_ignored"] == old["data"]["readings_ignored"]
    # Lo anotado SÍ pesa (si no, la comparación no probaría nada): la serie no tiene otra
    # cosa, y deja un dominio fuera de nominal, una alerta y recomendaciones.
    assert old["overall_level"] != "nominal"
    assert old["domains"]["behavioral"]["level"] == old["overall_level"]
    assert old["domains"]["behavioral"]["score"] > 0
    assert old["alerts"] and old["recommendations"]

    # Y el estado ENTERO es el mismo salvo el nombre de la fuente: se compara todo, tras
    # llamar a cada fuente nueva como a la antigua.
    assert sorted(old["mission"]["sources"]) == [LEGACY_SOURCE, PVT_SOURCE]
    assert sorted(new["mission"]["sources"]) == [CONSOLE_SOURCE, DIARY_SOURCE]
    assert new != old
    assert _same_but_for_source_names(new) == _same_but_for_source_names(old)


def test_no_module_that_decides_reads_the_annotator_or_names_these_sources() -> None:
    backend = Path(__file__).resolve().parents[1]
    names = {DIARY_SOURCE, CONSOLE_SOURCE, LEGACY_SOURCE, PVT_SOURCE}
    for folder in ("analysis", "advisor"):
        for path in sorted((backend / "app" / folder).glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            used = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
            assert "recorded_by" not in used, path.name
            literals = {
                node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            }
            # Solo la tabla de rótulos de la calidad del dato nombra una fuente, para pintarla.
            if path.name != "data_quality.py":
                assert not literals & names, path.name
    # Y en esa tabla son rótulos: ninguna comparación `source == "…"` en el módulo.
    quality = ast.parse((backend / "app" / "analysis" / "data_quality.py").read_text("utf-8"))
    compared = {
        item.value
        for node in ast.walk(quality) if isinstance(node, ast.Compare)
        for item in [node.left, *node.comparators]
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    }
    assert not compared & names
