"""La prueba PVT hecha en la consola (`app/api/pvt_console.py`).

Los parámetros y los textos los da el backend, lo que no tiene fuente escrita se declara
diseño de EMMA, la prueba entra puntuada, firmada y en el ledger, y describirla no mueve el
veredicto.

Desde el 2026-10-13 la consola firma con su fuente propia y con quién teclea por su ruta
(`tests/test_recorded_by.py`). Aquí, lo que lleva una hora elegida entra por la ruta de
siempre (`POST /api/pvt`, fuente `pvt-test`): son las pruebas que la lista tiene que seguir
enseñando.
"""

import datetime as dt
import inspect
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import pvt_console
from app.api.pvt_console import (
    ABANDON_AFTER_MS,
    CONSOLE_SOURCE,
    DESIGN,
    FOREPERIOD_MAX_MS,
    FOREPERIOD_MIN_MS,
    PREMATURE_RESPONSE_MS,
    PVT_SOURCE,
    RECORDED_KEYS,
    SESSION_TRIALS,
)
from app.api.routes import CONSOLE_IDENTITY, _is_reserved_source, new_store, reset_store
from app.core.config import Settings, get_settings
from app.ingest.codes import CATALOG
from app.ingest.fhir import EvidenceContext
from app.ingest.pvt import (
    FALSE_START_THRESHOLD_MS,
    LAPSE_THRESHOLD_MS,
    MIN_TRIALS,
    score,
)
from app.ingest.simulator import LITERATURE
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


def _protocol(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/pvt/protocol")
    assert response.status_code == 200
    return response.json()


def _session(protocol: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """Un tiempo por estímulo y el tripulante: lo que admite la ruta de siempre."""
    trials = protocol["session"]["trials"]
    times = [250.0] * (trials - 3) + [620.0, 700.0, protocol["session"]["premature_response_ms"]]
    return {"reaction_times_ms": times, "subject": "crew-01", **extra}


def _console(protocol: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """Lo que envía el panel al acabar: sin hora ni fuente, y con quién teclea."""
    return {**_session(protocol), "recorded_by": "CDR", **extra}


def _verdict(client: TestClient) -> tuple[Any, ...]:
    status = client.get("/api/status").json()
    return (
        status["overall_level"],
        {key: (item["level"], item["score"]) for key, item in status["domains"].items()},
        [(item["id"], item["level"]) for item in status["alerts"]],
    )


# --------------------------------------------------------------------------- #
# Los parámetros: los de la puntuación se leen, los demás se declaran diseño
# --------------------------------------------------------------------------- #


def test_scoring_parameters_are_the_ones_the_scoring_uses(client: TestClient) -> None:
    by_key = {item["key"]: item for item in _protocol(client)["parameters"]}
    assert by_key["lapse_threshold_ms"]["value"] == LAPSE_THRESHOLD_MS
    assert by_key["false_start_threshold_ms"]["value"] == FALSE_START_THRESHOLD_MS
    assert by_key["min_trials"]["value"] == MIN_TRIALS
    assert by_key["lapse_threshold_ms"]["value_text"] == "500 ms"
    assert by_key["foreperiod_ms"]["value_text"] == "entre 2000 ms y 10 000 ms"


def test_only_the_lapse_threshold_claims_a_written_source(client: TestClient) -> None:
    parameters = _protocol(client)["parameters"]
    documented = [item for item in parameters if item["basis"] == "repository"]
    assert [item["key"] for item in documented] == ["lapse_threshold_ms"]
    # Su respaldo es el que ya declara el simulador, tal cual, y para ese mismo valor.
    entry = LITERATURE["pvt_lapse_threshold_ms"]
    assert entry.value == LAPSE_THRESHOLD_MS
    assert documented[0]["basis_display"] == entry.source
    assert documented[0]["note"] == entry.note

    design = [item for item in parameters if item["basis"] == "design"]
    # Desde la lectura de las fuentes (2026-10-13) dos valores de diseño coinciden con lo
    # publicado y lo dicen (`tests/test_pvt_sources.py`); los demás siguen sin fuente.
    assert {item["key"] for item in design} == {"min_trials", "trials", "abandon_after_ms"}
    for item in design:
        assert item["basis_display"] == DESIGN == "diseño de EMMA, sin fuente leída"


def test_session_numbers_are_the_declared_ones_and_can_be_scored(client: TestClient) -> None:
    session = _protocol(client)["session"]
    assert session == {
        "trials": SESSION_TRIALS,
        "foreperiod_min_ms": FOREPERIOD_MIN_MS,
        "foreperiod_max_ms": FOREPERIOD_MAX_MS,
        "premature_response_ms": PREMATURE_RESPONSE_MS,
        "abandon_after_ms": ABANDON_AFTER_MS,
    }
    # Una prueba entera llega al mínimo que exige la puntuación.
    assert session["trials"] >= MIN_TRIALS
    assert 0 < session["foreperiod_min_ms"] < session["foreperiod_max_ms"]


def test_a_premature_response_is_sent_as_something_the_scoring_counts_as_false_start() -> None:
    assert PREMATURE_RESPONSE_MS < FALSE_START_THRESHOLD_MS
    result = score([300.0] * (SESSION_TRIALS - 1) + [PREMATURE_RESPONSE_MS])
    assert result.false_starts == 1
    assert result.mean_rt_ms == 300.0


def test_no_response_can_exceed_what_the_catalogue_accepts(client: TestClient) -> None:
    """El tope de espera es el máximo físico del indicador: lo que se envía siempre cabe."""
    assert CATALOG["pvt-mean-rt"].physical_max == ABANDON_AFTER_MS
    slowest = [ABANDON_AFTER_MS] * SESSION_TRIALS
    assert client.post("/api/pvt", json={"reaction_times_ms": slowest}).status_code == 201


def test_texts_state_the_limit_and_never_claim_validation(client: TestClient) -> None:
    protocol = _protocol(client)
    limits = " ".join(protocol["limits"])
    assert "latencia que no está caracterizada" in limits
    assert "no es un instrumento calibrado" in limits
    assert "Una sola prueba no es una línea base" in limits
    assert DESIGN in limits
    assert len(protocol["instructions"]) >= 3
    assert set(protocol["notices"]) == {"premature", "abandoned", "no_response"}

    # Ni en la respuesta ni en el módulo se afirma un respaldo que no se ha leído: ni la
    # palabra que lo daría por comprobado ni el nombre de una variante publicada de la
    # prueba. Se componen aquí para que tampoco este fichero las lleve escritas.
    claimed = "valid" + "ad"
    variant = "pvt" + "-b"
    # Desde la lectura de las fuentes, la variante publicada se nombra solo donde se cita
    # (`published`) y en la frase que dice que esta prueba NO lo es (`identity`): ni el
    # módulo ni ningún otro texto de la respuesta la llevan. Las divergencias (2026-10-14)
    # también citan: cada una lleva la frase de la fuente y el nombre de su versión.
    own = {key: value for key, value in protocol.items()
           if key not in {"identity", "published", "divergences"}}
    own["parameters"] = [
        {key: value for key, value in item.items() if key != "published"}
        for item in protocol["parameters"]
    ]
    for word, texts in (
        (claimed, (str(protocol), inspect.getsource(pvt_console))),
        (variant, (str(own), inspect.getsource(pvt_console))),
    ):
        for text in texts:
            assert word not in text.lower(), word


def test_result_fields_name_figures_the_route_returns(client: TestClient) -> None:
    protocol = _protocol(client)
    returned = client.post("/api/pvt", json=_session(protocol)).json()["result"]
    fields = protocol["result_fields"]
    assert {item["key"] for item in fields} <= set(returned)
    for item in fields:
        assert isinstance(returned[item["key"]], int | float)
    # Lo que queda en el registro es lo que la ruta registra, y se dice cuál es cuál.
    recorded = [item["recorded_as"] for item in fields if item["recorded_as"] is not None]
    assert recorded == list(RECORDED_KEYS) == ["pvt-mean-rt", "pvt-lapses"]
    assert protocol["records"] == [
        {"key": key, "display": CATALOG[key].display, "display_es": CATALOG[key].display_es}
        for key in RECORDED_KEYS
    ]
    by_key = {item["key"]: item for item in fields}
    assert by_key["mean_rt_ms"]["unit_display"] == "ms"
    assert by_key["lapses"]["unit_display"] == ""


def test_provenance_is_the_one_the_route_signs_with(client: TestClient, tmp_path) -> None:
    provenance = _protocol(client)["provenance"]
    assert provenance["source"] == CONSOLE_SOURCE == "console-pvt" != CONSOLE_IDENTITY
    assert provenance["source_display"] == "test PVT en la consola"
    assert PVT_SOURCE == "pvt-test"
    assert provenance["observation_type"] == "measured"
    assert provenance["evidence_context"] == "ground"
    assert "hora en que el backend recibe" in provenance["effective_note"]
    # La fuente de la consola solo la pone su ruta; la de siempre sigue abierta.
    assert _is_reserved_source(CONSOLE_SOURCE)
    assert not _is_reserved_source(PVT_SOURCE)

    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, deployment_context=EvidenceContext.ISS
    )
    assert _protocol(client)["provenance"]["evidence_context"] == "iss"
    assert _protocol(client)["submit_to"] == "/api/pvt/console"


# --------------------------------------------------------------------------- #
# La prueba entra por la ruta de siempre: puntuada, firmada y en el ledger
# --------------------------------------------------------------------------- #


def test_a_console_session_is_scored_signed_and_read_back(client: TestClient) -> None:
    protocol = _protocol(client)
    before = client.get("/api/audit").json()["total_entries"]
    started = dt.datetime.now(dt.UTC)

    response = client.post("/api/pvt/console", json=_console(protocol))
    assert response.status_code == 201, response.text
    result = response.json()["result"]
    assert (result["trials"], result["valid_trials"]) == (SESSION_TRIALS, SESSION_TRIALS - 1)
    assert (result["lapses"], result["false_starts"]) == (2, 1)

    audit = client.get("/api/audit", params={"limit": 500}).json()
    assert audit["total_entries"] == before + len(RECORDED_KEYS)
    assert audit["integrity_ok"] is True
    assert {entry["signer"] for entry in audit["entries"]} == {CONSOLE_SOURCE}
    assert sorted(response.json()["recorded"]) == sorted(
        entry["index"] for entry in audit["entries"]
    )

    payload = client.get("/api/pvt/sessions").json()
    assert payload["count"] == 1
    session = payload["sessions"][0]
    assert [item["key"] for item in session["values"]] == list(RECORDED_KEYS)
    assert session["values"][0]["value"] == result["mean_rt_ms"]
    assert session["values"][1]["value"] == result["lapses"]
    assert session["values"][1]["value_text"] == "2 recuento"
    assert session["source_display"] == "test PVT en la consola"
    assert (session["recorded_by"], session["recorded_by_display"]) == ("CDR", "CDR")
    assert session["observation_type"] == "measured"
    assert session["evidence_context"] == "ground"
    # La hora es la de recepción: el panel no envía ninguna.
    received = dt.datetime.fromisoformat(session["effective"])
    assert started <= received <= dt.datetime.now(dt.UTC)


def test_the_session_shows_up_in_the_status_like_any_other_reading(
    seeded: TestClient,
) -> None:
    protocol = _protocol(seeded)
    reference = dt.datetime.fromisoformat(
        seeded.get("/api/status").json()["data"]["reference_time"]
    )
    moment = reference - dt.timedelta(hours=1)
    assert seeded.post(
        "/api/pvt", json=_session(protocol, effective=moment.isoformat())
    ).status_code == 201

    status = seeded.get("/api/status").json()
    assert PVT_SOURCE in status["mission"]["sources"]
    session = seeded.get("/api/pvt/sessions").json()["sessions"][0]
    assert dt.datetime.fromisoformat(session["effective"]) == moment
    assert session["position"] == "current"


def test_sessions_are_only_the_pvt_ones_of_that_crew_member_newest_first(
    seeded: TestClient,
) -> None:
    protocol = _protocol(seeded)
    # El simulador tiene PVT de sobra, y no son pruebas hechas en la consola.
    empty = seeded.get("/api/pvt/sessions").json()
    assert (empty["count"], empty["sessions"]) == (0, [])
    assert empty["reference_time"] is not None

    reference = dt.datetime.fromisoformat(
        seeded.get("/api/status").json()["data"]["reference_time"]
    )
    for hours in (30, 2, 80):
        moment = reference - dt.timedelta(hours=hours)
        seeded.post("/api/pvt", json=_session(protocol, effective=moment.isoformat()))
    # Un alta manual del mismo indicador no es una prueba; ni la de otro tripulante.
    seeded.post(
        "/api/observations",
        json={"key": "pvt-mean-rt", "value": 290, "effective": reference.isoformat()},
    )
    seeded.post("/api/pvt", json=_session(protocol, subject="crew-02"))

    payload = seeded.get("/api/pvt/sessions").json()
    assert payload["count"] == 3
    hours_ago = [
        round((reference - dt.datetime.fromisoformat(item["effective"])).total_seconds() / 3600)
        for item in payload["sessions"]
    ]
    assert hours_ago == [2, 30, 80]
    assert [item["position"] for item in payload["sessions"]] == [
        "current", "current", "earlier",
    ]
    limited = seeded.get("/api/pvt/sessions", params={"limit": 1}).json()
    assert (limited["count"], len(limited["sessions"])) == (3, 1)
    assert seeded.get("/api/pvt/sessions", params={"subject": "crew-02"}).json()["count"] == 1


def test_a_session_dated_after_the_data_says_the_status_sets_it_aside(
    seeded: TestClient,
) -> None:
    """Con una misión simulada, la hora real de recepción cae fuera de los datos: se dice."""
    protocol = _protocol(seeded)
    reference = dt.datetime.fromisoformat(
        seeded.get("/api/status").json()["data"]["reference_time"]
    )
    late = reference + dt.timedelta(days=400)
    seeded.post("/api/pvt", json=_session(protocol, effective=late.isoformat()))
    session = seeded.get("/api/pvt/sessions").json()["sessions"][0]
    assert session["position"] == "after-reference"
    assert "aparta" in session["position_note"]
    ignored = seeded.get("/api/status").json()["data"]["readings_ignored"]
    assert ignored["after_reference"] == len(RECORDED_KEYS)


def test_sessions_of_an_empty_store(client: TestClient) -> None:
    assert client.get("/api/pvt/sessions").json() == {
        "subject": "crew-01", "count": 0, "reference_time": None, "sessions": [],
    }


def test_malformed_sessions_are_rejected_and_leave_nothing(client: TestClient) -> None:
    before = client.get("/api/audit").json()["total_entries"]
    bad: list[dict[str, Any]] = [
        {},
        {"reaction_times_ms": []},
        {"reaction_times_ms": "rápido"},
        {"reaction_times_ms": [250.0, "x"] * 10},
        {"reaction_times_ms": [250.0] * (MIN_TRIALS - 1)},
        {"reaction_times_ms": [PREMATURE_RESPONSE_MS] * SESSION_TRIALS},
        {"reaction_times_ms": [250.0] * SESSION_TRIALS, "subject": ""},
    ]
    for body in bad:
        assert client.post("/api/pvt", json=body).status_code == 422, body
    assert client.get("/api/audit").json()["total_entries"] == before
    assert client.get("/api/pvt/sessions").json()["count"] == 0


# --------------------------------------------------------------------------- #
# Invariante 5: describir la prueba no mueve el veredicto, y este módulo no escribe
# --------------------------------------------------------------------------- #


def test_reading_the_protocol_and_the_sessions_does_not_change_the_verdict(
    seeded: TestClient,
) -> None:
    before = _verdict(seeded)
    assert before[2], "el escenario tiene que dejar alguna alerta que comparar"
    ledger = seeded.get("/api/audit").json()["total_entries"]

    assert seeded.get("/api/pvt/protocol").status_code == 200
    assert seeded.get("/api/pvt/sessions").status_code == 200

    assert _verdict(seeded) == before
    assert seeded.get("/api/audit").json()["total_entries"] == ledger


def test_the_console_module_writes_only_through_its_own_route() -> None:
    paths = app.openapi()["paths"]
    assert set(paths["/api/pvt/protocol"]) == {"get"}
    assert set(paths["/api/pvt/sessions"]) == {"get"}
    # Dos escrituras: la ruta de siempre y la de la consola, que fija fuente y operador.
    assert set(paths["/api/pvt"]) == {"post"}
    assert set(paths["/api/pvt/console"]) == {"post"}
    assert {path for path in paths if path.startswith("/api/pvt")} == {
        "/api/pvt", "/api/pvt/console", "/api/pvt/protocol", "/api/pvt/sessions",
    }


def test_scoring_is_untouched_by_this_unit() -> None:
    """La consola no puntúa: la puntuación de una sesión conocida es la de siempre."""
    result = score([250.0] * 18 + [620.0, 700.0])
    assert result.to_dict() == {
        "trials": 20, "valid_trials": 20, "mean_rt_ms": 291.0, "median_rt_ms": 250.0,
        "slowest_10pct_mean_ms": 660.0, "lapses": 2, "lapse_rate": 0.1,
        "false_starts": 0, "response_speed": 3.7521,
    }
