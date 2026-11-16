"""API: contrato de respuesta, ingesta auditada y degradacion sin red.

Se fuerza el modo offline en todas las pruebas: si alguna tocara la red,
fallaria. Eso verifica de paso la propiedad de autonomia del sistema.
"""

import datetime as dt
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.advisor.recommendations import Advisor, Urgency
from app.analysis.risk import RiskEngine
from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.evidence.links import OSD_288, evidence_for
from app.ingest.codes import Domain
from app.main import app


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True
    )
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


@pytest.fixture
def seeded(client: TestClient) -> TestClient:
    client.post("/api/simulate", params={"scenario": "nominal", "days": 40})
    return client


# --------------------------------------------------------------------------- #
# Lectura basica
# --------------------------------------------------------------------------- #


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_indicators_declare_code_provenance(client: TestClient) -> None:
    """La API debe decir que codigos son LOINC de verdad y cuales son propios."""
    payload = client.get("/api/indicators").json()

    # El total sale del catalogo: una cifra fija aqui rompia con cada indicador nuevo.
    from app.ingest.codes import CATALOG

    assert payload["count"] == len(CATALOG) == len(payload["indicators"])
    by_key = {item["key"]: item for item in payload["indicators"]}
    assert by_key["heart-rate"]["is_standard_code"] is True
    assert by_key["heart-rate"]["system"] == "http://loinc.org"
    assert by_key["pvt-mean-rt"]["is_standard_code"] is False


def test_scenarios(client: TestClient) -> None:
    keys = {item["key"] for item in client.get("/api/scenarios").json()["scenarios"]}
    assert {"nominal", "spe-event"} <= keys


# --------------------------------------------------------------------------- #
# Ingesta
# --------------------------------------------------------------------------- #


def test_record_observation_is_audited(client: TestClient) -> None:
    """21 CFR 11.10(e): no existe escritura sin rastro."""
    response = client.post(
        "/api/observations",
        json={"key": "heart-rate", "value": 64.0, "subject": "crew-01"},
    )
    assert response.status_code == 201
    assert response.json()["ledger_index"] == 0

    audit = client.get("/api/audit").json()
    assert audit["total_entries"] == 1
    assert audit["integrity_ok"] is True
    assert len(audit["merkle_root"]) == 64


def test_unknown_indicator_is_rejected(client: TestClient) -> None:
    response = client.post("/api/observations", json={"key": "no-existe", "value": 1.0})
    assert response.status_code == 422


def test_pvt_submission_scores_and_records(client: TestClient) -> None:
    times = [250.0] * 18 + [620.0, 700.0]  # dos lapsos
    response = client.post("/api/pvt", json={"reaction_times_ms": times})

    assert response.status_code == 201
    result = response.json()["result"]
    assert result["lapses"] == 2
    assert result["valid_trials"] == 20
    assert len(response.json()["recorded"]) == 2  # media y lapsos

    stored = client.get("/api/observations", params={"key": "pvt-lapses"}).json()
    assert stored["count"] == 1


def test_pvt_rejects_too_few_trials(client: TestClient) -> None:
    response = client.post("/api/pvt", json={"reaction_times_ms": [250.0] * 5})
    assert response.status_code == 422
    assert "interpretable" in response.json()["detail"]


def test_ble_frame_ingestion(client: TestClient) -> None:
    """Trama GATT real: flags con R-R, pulso 60, cuatro intervalos.

    Cuatro latidos no son HRV: la HRV sale de la ventana de varias tramas
    (`tests/test_ble_hrv_window.py`), y una trama sola registra el pulso.
    """
    frame = bytes([0b0001_0000, 60])
    for ms in (1000, 1010, 990, 1005):
        frame += int(ms / 1000 * 1024).to_bytes(2, "little")

    response = client.post("/api/wearable/ble", json={"frame_hex": frame.hex()})

    assert response.status_code == 201
    assert response.json()["indicators"] == ["heart-rate"]
    assert response.json()["hrv"] is None
    assert client.get("/api/audit").json()["total_entries"] == 1


def test_ble_rejects_malformed_frame(client: TestClient) -> None:
    assert client.post("/api/wearable/ble", json={"frame_hex": "zz"}).status_code == 422
    # Anuncia pulso de 16 bits y no lo trae.
    assert client.post("/api/wearable/ble", json={"frame_hex": "01"}).status_code == 422


def test_simulate_loads_audited_data(client: TestClient) -> None:
    response = client.post("/api/simulate", params={"scenario": "nominal", "days": 2})
    assert response.status_code == 201
    assert response.json()["recorded"] > 0
    assert client.get("/api/audit").json()["integrity_ok"] is True


# --------------------------------------------------------------------------- #
# Estado
# --------------------------------------------------------------------------- #


def test_status_without_data_refuses_to_invent(client: TestClient) -> None:
    """Un panel clinico con cifras sin origen es peor que uno que dice no saber."""
    response = client.get("/api/status")
    assert response.status_code == 404
    assert "no hay observaciones" in response.json()["detail"]


def test_status_without_network(seeded: TestClient) -> None:
    """El nucleo de decision debe funcionar sin enlace con la Tierra."""
    payload = seeded.get("/api/status").json()

    assert payload["subject"] == "crew-01"
    assert set(payload["domains"]) == {str(domain) for domain in Domain}
    # Sin red no hay efemerides, y el sistema lo dice en vez de inventarlas.
    assert payload["comms"] is None
    assert payload["data"]["integrity_ok"] is True


def test_nominal_scenario_is_quiet(seeded: TestClient) -> None:
    payload = seeded.get("/api/status").json()
    assert payload["overall_level"] == "nominal"
    assert payload["recommendations"] == []
    assert "nominal" in payload["summary"].lower()


def test_insomnia_scenario_surfaces_behavioral_recommendations(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "progressive-insomnia", "days": 40})
    payload = client.get("/api/status").json()

    assert payload["domains"]["behavioral"]["level"] != "nominal"
    behavioral = [r for r in payload["recommendations"] if r["domain"] == "behavioral"]
    assert behavioral, "un dominio en alerta debe traer acciones concretas"
    assert all(item["evidence"] for item in behavioral), "toda acción lleva su evidencia"


def test_spe_scenario_surfaces_the_radiation_event(client: TestClient) -> None:
    """Regresion: el evento ocurria al inicio de la mision y ya habia decaido
    cuando se evaluaba el estado, asi que el escenario era invisible."""
    client.post(
        "/api/simulate",
        params={"scenario": "spe-event", "days": 20, "samples_per_day": 24},
    )
    payload = client.get("/api/status").json()

    assert payload["domains"]["radiation"]["level"] != "nominal"
    assert payload["domains"]["radiation"]["drivers"]
    assert [r for r in payload["recommendations"] if r["domain"] == "radiation"]


def test_dose_at_limit_is_critical(seeded: TestClient) -> None:
    payload = seeded.get("/api/status", params={"cumulative_dose_msv": 600}).json()
    assert payload["domains"]["radiation"]["level"] == "critical"
    assert payload["dose"]["fraction"] == pytest.approx(1.0)


def test_status_is_reproducible(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "progressive-insomnia", "days": 40, "seed": 7})
    first = client.get("/api/status").json()
    second = client.get("/api/status").json()
    assert first["domains"] == second["domains"]


# --------------------------------------------------------------------------- #
# Auditoria y rectificacion
# --------------------------------------------------------------------------- #


REDACTION = {"reason": "atribuida al tripulante equivocado", "requested_by": "cirujano"}


def test_redaction_leaves_a_signed_tombstone(client: TestClient) -> None:
    for value in (60.0, 62.0, 64.0):
        client.post("/api/observations", json={"key": "heart-rate", "value": value})
    anchor_before = client.get("/api/audit").json()["anchor"]

    response = client.post("/api/audit/redact/1", json=REDACTION)

    assert response.status_code == 200
    body = response.json()
    assert body["chain_still_valid"] is True
    assert body["redaction_entry_index"] == 3
    # La lapida es un asiento nuevo: la raiz cambia y la redaccion queda visible
    # para el ancla siguiente.
    assert body["merkle_root"] != anchor_before["root"]
    assert client.get("/api/observations").json()["count"] == 2

    audit = client.get("/api/audit").json()
    assert audit["integrity_ok"] is True
    assert audit["anchor"]["tree_size"] == 4
    tombstone = audit["entries"][-1]
    assert tombstone["entry_type"] == "redaction"
    assert tombstone["signer"] == "emma-audit"
    assert tombstone["redaction"] == {"target_index": 1, **REDACTION}


def test_redact_unknown_index(client: TestClient) -> None:
    assert client.post("/api/audit/redact/99", json=REDACTION).status_code == 404


def test_redaction_requires_reason_and_requester(client: TestClient) -> None:
    client.post("/api/observations", json={"key": "heart-rate", "value": 60.0})
    blank = {"reason": "   ", "requested_by": "cirujano"}

    assert client.post("/api/audit/redact/0").status_code == 422
    assert client.post("/api/audit/redact/0", json=blank).status_code == 422
    assert client.get("/api/audit").json()["total_entries"] == 1


def test_redacting_twice_or_a_tombstone_is_a_conflict(client: TestClient) -> None:
    client.post("/api/observations", json={"key": "heart-rate", "value": 60.0})

    assert client.post("/api/audit/redact/0", json=REDACTION).status_code == 200
    assert client.post("/api/audit/redact/0", json=REDACTION).status_code == 409
    assert client.post("/api/audit/redact/1", json=REDACTION).status_code == 409


def test_the_audit_identity_is_reserved(client: TestClient) -> None:
    """Una fuente llamada `emma-audit` fijaba otra clave con ese nombre en el
    registro, y la siguiente redaccion chocaba con ella: bloqueaba las
    rectificaciones con una sola lectura."""
    reserved = {"key": "heart-rate", "value": 60.0, "source": "emma-audit"}
    assert client.post("/api/observations", json=reserved).status_code == 422

    client.post("/api/observations", json={"key": "heart-rate", "value": 60.0})
    assert client.post("/api/audit/redact/0", json=REDACTION).status_code == 200


def test_observations_are_returned_as_fhir(client: TestClient) -> None:
    client.post("/api/observations", json={"key": "heart-rate", "value": 64.0})
    resource = client.get("/api/observations").json()["observations"][0]

    assert resource["resourceType"] == "Observation"
    assert resource["code"]["coding"][0]["code"] == "8867-4"
    assert resource["valueQuantity"]["unit"] == "/min"


# --------------------------------------------------------------------------- #
# Degradacion sin red
# --------------------------------------------------------------------------- #


def test_comms_offline_returns_503(client: TestClient) -> None:
    """Sin cache y sin red, el fallo es explicito; no se inventa una distancia."""
    response = client.get("/api/comms")
    assert response.status_code == 503
    assert "offline" in response.json()["detail"]


def test_space_weather_offline_returns_503(client: TestClient) -> None:
    assert client.get("/api/space-weather").status_code == 503


@pytest.mark.parametrize("days", [1, 37, 364, 1094])
def test_space_weather_only_takes_its_fixed_windows(client: TestClient, days: int) -> None:
    """Cada ventana distinta era otra tanda de consultas con la clave del operador (auditoría
    run-2, `emma:space-weather:lookback-quota-amplification`): se rechaza antes de salir."""
    assert client.get("/api/space-weather", params={"lookback_days": days}).status_code == 422


@pytest.mark.parametrize("days", [30, 90, 365, 1095])
def test_space_weather_fixed_windows_still_answer(client: TestClient, days: int) -> None:
    assert client.get("/api/space-weather", params={"lookback_days": days}).status_code == 503


def test_radiation_dose_offline_returns_503(client: TestClient) -> None:
    response = client.get(
        "/api/radiation/dose", params={"start": "2022-04-01", "end": "2022-04-02"}
    )
    assert response.status_code == 503


def test_radiation_dose_rejects_oversized_window(client: TestClient) -> None:
    """Sin este limite la API de RadLab llega a devolver cientos de MB."""
    response = client.get(
        "/api/radiation/dose", params={"start": "2022-01-01", "end": "2022-06-01"}
    )
    assert response.status_code == 400
    assert "excede el máximo" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# Evidencia
# --------------------------------------------------------------------------- #


def test_evidence_endpoint_carries_scope_caveat(client: TestClient) -> None:
    """OSD-288 es un estudio de raton y la API debe decirlo."""
    payload = client.get("/api/evidence/immune").json()
    osdr = [item for item in payload["evidence"] if "OSD-288" in item["source"]]

    assert osdr, "el dominio inmune debe enlazar OSD-288"
    assert "murino" in osdr[0]["scope_caveat"]
    assert "NO mide signos vitales humanos" in osdr[0]["scope_caveat"]


def test_every_domain_has_evidence() -> None:
    for domain in Domain:
        assert evidence_for(domain), f"{domain} sin respaldo documentado"


def test_osd_288_is_not_overstated() -> None:
    assert OSD_288.scope_caveat is not None
    # 12 ratones lanzados, 9 muestras en el conjunto: la ficha no cuenta datos que no hay.
    assert "9 muestras de bazo" in OSD_288.scope_caveat
    assert "Modelo murino, n = 12" not in OSD_288.scope_caveat


# --------------------------------------------------------------------------- #
# Recomendaciones (sin HTTP)
# --------------------------------------------------------------------------- #


def test_solar_event_recommendation_is_shelter_and_immediate() -> None:
    from app.environment.donki import EventType, Severity, SolarEvent

    event = SolarEvent(
        event_id="X-1", event_type=EventType.SEP,
        time=dt.datetime(2026, 11, 14, tzinfo=dt.UTC),
        severity=Severity.SEVERE, instruments=(), linked_event_ids=(),
        flare_class=None, link="",
    )
    status = RiskEngine().assess("crew-01", [], solar_events=[event])
    recommendations = Advisor().recommend(status)

    assert recommendations[0].urgency is Urgency.IMMEDIATE
    assert "Refugiarse" in recommendations[0].action
    assert recommendations[0].notify_ground


def test_nominal_status_yields_no_recommendations() -> None:
    status = RiskEngine().assess("crew-01", [])
    assert Advisor().recommend(status) == []
    assert "nominal" in Advisor().summarize(status).lower()


def test_critical_urgency_offers_one_action_not_a_list() -> None:
    """Ante una emergencia, una lista larga de opciones es ruido."""
    status = RiskEngine(dose_limit_msv=600).assess("crew-01", [], cumulative_dose_msv=900.0)
    radiation = [r for r in Advisor().recommend(status) if r.domain is Domain.RADIATION]
    assert len(radiation) == 1


# --------------------------------------------------------------------------- #
# Entrada degradada: rechazo limpio, nunca un 500 ni una perdida muda
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("caso", "cuerpo"),
    [
        ("pulso negativo", {"key": "heart-rate", "value": -60}),
        ("pulso imposible", {"key": "heart-rate", "value": 5000}),
        ("pulso de cero", {"key": "heart-rate", "value": 0}),
        ("saturación del 500 %", {"key": "oxygen-saturation", "value": 500}),
        ("confianza mayor que uno", {"key": "heart-rate", "value": 70, "confidence": 3.0}),
        ("confianza negativa", {"key": "heart-rate", "value": 70, "confidence": -1.0}),
        ("contexto inventado", {"key": "heart-rate", "value": 70, "context": "buceando"}),
        ("sujeto vacío", {"key": "heart-rate", "value": 70, "subject": ""}),
        ("campo mal escrito", {"key": "heart-rate", "value": 70, "contexto": "sleep"}),
    ],
)
def test_degraded_input_is_rejected_cleanly(
    client: TestClient, caso: str, cuerpo: dict[str, object]
) -> None:
    """Cada uno de estos entraba o reventaba. Ninguno debe hacer ninguna cosa.

    Los tres modos de fallo que habia aqui:

      - un valor imposible salia como **500**: el tripulante que teclea 5000 de
        pulso recibia "error del servidor" en vez de "eso no es posible";
      - `context` y `confidence` **no existian** en el modelo de entrada, asi que
        se descartaban en silencio y la lectura entraba como contexto desconocido
        y confianza plena;
      - `subject` vacio se aceptaba y la lectura se archivaba bajo un tripulante
        inexistente: no aparecia en el estado de nadie y no daba ningun error.

    Una constante vital que desaparece sin protestar es el peor fallo posible en
    un sistema de vigilancia.
    """
    response = client.post("/api/observations", json=cuerpo)
    assert response.status_code == 422, f"{caso}: HTTP {response.status_code}"


def test_context_and_confidence_round_trip_through_the_api(client: TestClient) -> None:
    """El contrapeso: lo que se envia tiene que llegar entero al analisis."""
    created = client.post(
        "/api/observations",
        json={"key": "heart-rate", "value": 52, "context": "sleep", "confidence": 0.4},
    )
    assert created.status_code == 201

    stored = client.get("/api/observations", params={"key": "heart-rate"}).json()
    extensiones = {
        item["url"].rsplit("/", 1)[-1]: item
        for item in stored["observations"][0]["extension"]
    }
    assert extensiones["context"]["valueCode"] == "sleep"
    assert extensiones["confidence"]["valueDecimal"] == 0.4


# --------------------------------------------------------------------------- #
# El camino desplegado tiene que ejercitar el motor, no su rama mas debil
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("scenario", "domain"),
    [
        ("arrhythmia", "cardiovascular"),
        ("progressive-insomnia", "behavioral"),
    ],
)
def test_demo_path_detects_each_scenario(
    client: TestClient, scenario: str, domain: str
) -> None:
    """Con el muestreo por defecto, `simulate` -> `status` debe ver el deterioro.

    Antes no lo veia. `samples_per_day` valia 4, y con eso la ventana movil de 14
    dias reune 56 lecturas frente a las 100 que exige `MIN_SAMPLES`: **0 % de uso
    de base personal** y el escenario de arritmia devolviendo "nominal" sobre un
    tripulante con arritmia. La demo ensenaba la rama mas debil del motor.
    """
    client.post("/api/simulate", params={"scenario": scenario, "days": 40})
    status = client.get("/api/status").json()

    flagged = [
        name for name, risk in status["domains"].items() if risk["level"] != "nominal"
    ]
    assert flagged == [domain], f"{scenario}: dominios marcados {flagged}"


def test_demo_path_stays_quiet_on_a_healthy_crew(client: TestClient) -> None:
    """El contrapeso: subir el muestreo no puede comprarse con falsas alarmas."""
    client.post("/api/simulate", params={"scenario": "nominal", "days": 40})
    status = client.get("/api/status").json()

    assert status["overall_level"] == "nominal"
    assert not [r for r in status["domains"].values() if r["level"] != "nominal"]


def test_status_declares_what_its_verdict_rests_on(client: TestClient) -> None:
    """"Nominal" sin base personal no significa lo mismo que con ella.

    Sin base personal solo se comprueban limites de peligro absoluto, asi que
    "nominal" quiere decir "no ha cruzado nada grave", no "esta como siempre".
    Un panel que no distingue las dos cosas afirma mas de lo que sabe.
    """
    client.post(
        "/api/simulate",
        params={"scenario": "nominal", "days": 40, "samples_per_day": 4},
    )
    escaso = client.get("/api/status").json()["data"]
    assert escaso["personal_baseline_fraction"] == 0.0
    assert "límites de peligro" in escaso["basis"]

    reset_store(new_store())
    client.post("/api/simulate", params={"scenario": "nominal", "days": 40})
    suficiente = client.get("/api/status").json()["data"]
    assert suficiente["personal_baseline_fraction"] >= 0.5
    assert suficiente["basis"] == "línea base personal"
    # Y sobre que ventana mira cada via: la tendencia ya no es toda la mision.
    assert suficiente["deviation_window_days"] == 2
    assert suficiente["trend_window_days"] == 21
    assert suficiente["window_days"] > suficiente["trend_window_days"]


def test_observations_limit_returns_the_most_recent(client: TestClient) -> None:
    """`limit=N` devolvia las N lecturas mas antiguas."""
    for hour, value in ((8, 60.0), (9, 61.0), (10, 62.0)):
        client.post(
            "/api/observations",
            json={
                "key": "heart-rate",
                "value": value,
                "effective": f"2026-09-01T{hour:02d}:00:00Z",
            },
        )

    observations = client.get("/api/observations", params={"limit": 2}).json()["observations"]

    assert [item["valueQuantity"]["value"] for item in observations] == [61.0, 62.0]


def test_an_empty_subject_is_rejected_everywhere(client: TestClient) -> None:
    pvt = {"reaction_times_ms": [250.0], "subject": ""}
    assert client.post("/api/pvt", json=pvt).status_code == 422
    frame = {"frame_hex": "0048", "subject": ""}
    assert client.post("/api/wearable/ble", json=frame).status_code == 422


def test_a_deeply_nested_request_is_a_422_not_a_crash(client: TestClient) -> None:
    """El manejador de validacion devolvia el dato recibido; anidado a cientos de niveles,
    serializarlo agotaba la pila y el 422 acababa en 500."""
    nested = "[" * 900 + "]" * 900
    body = ('{"key": "heart-rate", "value": 60.0, "subject": ' + nested + "}").encode()
    response = client.post(
        "/api/observations", content=body, headers={"content-type": "application/json"}
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "effective", ["0001-01-01T00:00:00Z", "0001-01-01T00:00:00+23:59", "1999-12-31T23:59:59Z"]
)
def test_an_implausibly_old_reading_is_rejected(client: TestClient, effective: str) -> None:
    """Una lectura del ano 1 entraba con un 201; con un desfase de +23:59, daba 500."""
    reading = {"key": "heart-rate", "value": 60.0, "effective": effective}
    assert client.post("/api/observations", json=reading).status_code == 422
    assert client.get("/api/audit").json()["total_entries"] == 0


# --------------------------------------------------------------------------- #
# Lo que necesita la interfaz (NASA-STD-3001 Vol 2, Apendice F)
# --------------------------------------------------------------------------- #


def test_status_declares_simulated_data_as_such(seeded: TestClient) -> None:
    """F.4.2: el modo simulacion tiene que poder distinguirse del de mision."""
    mission = seeded.get("/api/status").json()["mission"]

    assert mission["mode"] == "simulation"
    assert all(source.startswith("simulator:") for source in mission["sources"])


def test_real_readings_are_declared_as_mission(client: TestClient) -> None:
    for hour in range(3):
        client.post(
            "/api/observations",
            json={
                "key": "heart-rate",
                "value": 62.0 + hour,
                "effective": f"2026-11-14T0{hour}:00:00+00:00",
                "source": "wearable-ble",
            },
        )

    assert client.get("/api/status").json()["mission"]["mode"] == "mission"


def test_a_real_reading_among_simulated_ones_is_declared_as_mixed(seeded: TestClient) -> None:
    """Una lectura real entre simuladas no debe pasar por simulada, ni al reves."""
    reference = seeded.get("/api/status").json()["data"]["reference_time"]
    seeded.post(
        "/api/observations",
        json={"key": "heart-rate", "value": 64.0, "effective": reference, "source": "manual"},
    )

    mission = seeded.get("/api/status").json()["mission"]
    assert mission["mode"] == "mixed"
    assert "manual" in mission["sources"]


def test_status_gives_the_mission_time_origin(seeded: TestClient) -> None:
    """F.6.1: sin el origen, la interfaz no puede mostrar el MET."""
    payload = seeded.get("/api/status").json()
    start = dt.date.fromisoformat(payload["mission"]["start"])
    reference = dt.datetime.fromisoformat(payload["data"]["reference_time"])

    # El simulador arranca en el mismo origen que declara el estado.
    assert start == Settings().mission_start
    assert reference.date() >= start


def test_external_data_ages_come_as_numbers_too(seeded: TestClient) -> None:
    """Sin red no hay dato externo, y la antiguedad numerica tampoco se inventa."""
    payload = seeded.get("/api/status").json()

    assert payload["comms_data_age_seconds"] is None
    assert payload["solar_data_age_seconds"] is None


def test_status_until_gives_the_state_earth_can_have(seeded: TestClient) -> None:
    """Tierra ve lo que habia a bordo hace un tiempo de luz, no lo de ahora."""
    now = seeded.get("/api/status").json()
    reference = dt.datetime.fromisoformat(now["data"]["reference_time"])
    earlier = (reference - dt.timedelta(hours=3)).isoformat()

    delayed = seeded.get("/api/status", params={"until": earlier}).json()

    assert dt.datetime.fromisoformat(delayed["data"]["reference_time"]) <= reference - dt.timedelta(
        hours=3
    )
    assert delayed["data"]["observations"] < now["data"]["observations"]


def test_status_until_without_timezone_is_rejected(seeded: TestClient) -> None:
    response = seeded.get("/api/status", params={"until": "2026-11-20T08:00:00"})
    assert response.status_code == 422


def test_status_until_before_any_reading_refuses_to_invent(seeded: TestClient) -> None:
    response = seeded.get("/api/status", params={"until": "2020-01-01T00:00:00+00:00"})
    assert response.status_code == 404


def test_status_without_dose_says_it_has_none(seeded: TestClient) -> None:
    """Sin dosis facilitada no hay "0 mSv": una cifra sin origen no es una medida."""
    dose = seeded.get("/api/status").json()["dose"]

    assert dose["cumulative_msv"] is None
    assert dose["fraction"] is None
    assert dose["limit_msv"] == 600.0


def test_status_with_dose_reports_it(seeded: TestClient) -> None:
    dose = seeded.get("/api/status", params={"cumulative_dose_msv": 150}).json()["dose"]

    assert dose["cumulative_msv"] == 150
    assert dose["fraction"] == 0.25


# --------------------------------------------------------------------------- #
# /comms: cada fallo con su codigo
# --------------------------------------------------------------------------- #


@pytest.fixture
def online_client(tmp_path) -> Iterator[TestClient]:
    """Sin modo offline, pero con `_fetch` sustituido: sigue sin tocar la red."""
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=False)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _fail_with(exc: BaseException):
    def fetch(self: object, epoch: dt.date, target: str) -> None:
        raise exc

    return fetch


def test_comms_without_network_is_503_not_500(
    online_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import requests

    from app.environment.ephemeris import EphemerisClient

    monkeypatch.setattr(EphemerisClient, "_fetch", _fail_with(requests.ConnectionError("red")))
    response = online_client.get("/api/comms")

    assert response.status_code == 503
    assert "inaccesible" in response.json()["detail"]


def test_comms_with_a_broken_answer_is_502(
    online_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from astroquery.exceptions import RemoteServiceError

    from app.environment.ephemeris import EphemerisClient

    monkeypatch.setattr(EphemerisClient, "_fetch", _fail_with(RemoteServiceError("x")))
    assert online_client.get("/api/comms").status_code == 502


def test_status_degrades_when_horizons_answers_badly(
    online_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El estado no cae por una efemeride inservible: la declara ausente."""
    from astroquery.exceptions import RemoteServiceError

    from app.environment.donki import DonkiClient
    from app.environment.ephemeris import EphemerisClient

    monkeypatch.setattr(EphemerisClient, "_fetch", _fail_with(RemoteServiceError("x")))
    monkeypatch.setattr(DonkiClient, "_fetch", lambda self, *a: [])
    online_client.post("/api/simulate", params={"scenario": "nominal", "days": 10})
    payload = online_client.get("/api/status").json()

    assert payload["comms"] is None
    assert payload["comms_data_age_seconds"] is None


# --------------------------------------------------------------------------- #
# F.6.2: con que capacidad vigila el sistema
# --------------------------------------------------------------------------- #


def _capabilities(payload: dict) -> dict[str, dict]:
    return {item["key"]: item for item in payload["monitoring"]["capabilities"]}


def test_offline_monitoring_is_declared_reduced_and_says_what_is_lost(seeded: TestClient) -> None:
    """Sin red ni dosis, "nominal" no significa lo mismo: el estado lo dice."""
    payload = seeded.get("/api/status").json()
    capabilities = _capabilities(payload)

    assert payload["monitoring"]["level"] == "reduced"
    assert capabilities["light-time"]["available"] is False
    assert "aislamiento" in capabilities["light-time"]["consequence"]
    assert capabilities["space-weather"]["available"] is False
    assert capabilities["career-dose"]["available"] is False
    # Lo que si funciona no lleva consecuencia.
    assert capabilities["record-integrity"]["available"] is True
    assert capabilities["record-integrity"]["consequence"] is None


def test_monitoring_is_full_only_when_nothing_is_missing(
    online_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.environment.donki import DonkiClient
    from app.environment.ephemeris import CommsWindow, EphemerisClient

    window = CommsWindow(
        epoch=dt.date(2026, 11, 14), distance_au=1.3244, one_way_minutes=11.01, target="499"
    )
    monkeypatch.setattr(EphemerisClient, "_fetch", lambda self, epoch, target: window)
    monkeypatch.setattr(DonkiClient, "_fetch", lambda self, *a: [])
    online_client.post("/api/simulate", params={"scenario": "nominal", "days": 40})

    full = online_client.get("/api/status", params={"cumulative_dose_msv": 10}).json()
    assert full["monitoring"]["level"] == "full", _capabilities(full)

    without_dose = online_client.get("/api/status").json()
    assert without_dose["monitoring"]["level"] == "reduced"


def test_a_thin_history_is_declared_as_no_personal_baseline(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "nominal", "days": 3})
    capability = _capabilities(client.get("/api/status").json())["personal-baseline"]

    assert capability["available"] is False
    assert "límites de peligro absoluto" in capability["consequence"]


# --------------------------------------------------------------------------- #
# Reconocimiento de alertas: una accion con consecuencias, al ledger
# --------------------------------------------------------------------------- #


@pytest.fixture
def alerting(client: TestClient) -> tuple[TestClient, dict]:
    client.post("/api/simulate", params={"scenario": "arrhythmia", "days": 40})
    return client, client.get("/api/status").json()


def _ack(client: TestClient, status: dict, **overrides: object):
    alert = status["alerts"][0]
    body = {
        "domain": alert["domain"],
        "level": alert["level"],
        "reference_time": status["data"]["reference_time"],
        "acknowledged_by": "comandante",
        **overrides,
    }
    return client.post("/api/alerts/acknowledge", json=body)


def test_an_alert_starts_unacknowledged(alerting: tuple[TestClient, dict]) -> None:
    _, status = alerting
    assert status["alerts"], "el escenario de arritmia debe alertar"
    assert all(alert["acknowledged"] is False for alert in status["alerts"])


def test_an_acknowledgement_is_signed_in_the_ledger(alerting: tuple[TestClient, dict]) -> None:
    client, status = alerting
    response = _ack(client, status)
    assert response.status_code == 201

    after = client.get("/api/status").json()
    alert = after["alerts"][0]
    assert alert["acknowledged"] is True
    assert alert["acknowledged_by"] == "comandante"
    assert after["data"]["integrity_ok"] is True

    audit = client.get("/api/audit", params={"limit": 1}).json()
    assert audit["entries"][-1]["entry_type"] == "alert-acknowledgement"
    assert audit["entries"][-1]["signer"] == "crew-console"


def test_an_acknowledgement_does_not_touch_the_analysis(
    alerting: tuple[TestClient, dict],
) -> None:
    client, status = alerting
    _ack(client, status)
    after = client.get("/api/status").json()

    assert after["data"]["observations"] == status["data"]["observations"]
    assert after["domains"] == status["domains"]


def test_a_different_level_is_a_new_alert(alerting: tuple[TestClient, dict]) -> None:
    client, status = alerting
    other = "critical" if status["alerts"][0]["level"] != "critical" else "watch"
    _ack(client, status, level=other)

    assert client.get("/api/status").json()["alerts"][0]["acknowledged"] is False


def test_an_old_acknowledgement_does_not_cover_a_relapse(
    alerting: tuple[TestClient, dict],
) -> None:
    """Fuera de la ventana de calculo, la alerta se apoya en lecturas nuevas."""
    client, status = alerting
    reference = dt.datetime.fromisoformat(status["data"]["reference_time"])
    _ack(client, status, reference_time=(reference - dt.timedelta(days=3)).isoformat())

    assert client.get("/api/status").json()["alerts"][0]["acknowledged"] is False


def test_nominal_cannot_be_acknowledged(alerting: tuple[TestClient, dict]) -> None:
    client, status = alerting
    assert _ack(client, status, level="nominal").status_code == 422


def test_an_acknowledgement_needs_a_timezone(alerting: tuple[TestClient, dict]) -> None:
    client, status = alerting
    assert _ack(client, status, reference_time="2026-12-10T23:00:00").status_code == 422


def test_an_acknowledgement_needs_an_author(alerting: tuple[TestClient, dict]) -> None:
    client, status = alerting
    assert _ack(client, status, acknowledged_by="   ").status_code == 422


def test_a_tampered_acknowledgement_cannot_silence_an_alert(
    alerting: tuple[TestClient, dict],
) -> None:
    """Cambiar en disco a quien o que se reconocio rompe su hash firmado: 409."""
    from dataclasses import replace

    from app.api.routes import get_store

    client, status = alerting
    index = _ack(client, status).json()["ledger_index"]
    store = get_store()
    entry = store.ledger._entries[index]
    store.ledger._entries[index] = replace(
        entry, payload={**entry.payload, "acknowledged_by": "otra persona"}
    )

    assert client.get("/api/status").status_code == 409


# --------------------------------------------------------------------------- #
# F.6.4: suprimir, inhibir y habilitar. Silenciar una alarma clinica, con limites
# --------------------------------------------------------------------------- #


def _silence(client: TestClient, status: dict, action: str, **overrides: object):
    alert = status["alerts"][0]
    body: dict[str, object] = {
        "domain": alert["domain"],
        "reference_time": status["data"]["reference_time"],
        "reason": "sensor de pulso con mal contacto",
        "requested_by": "comandante",
    }
    if action == "suppress":
        body |= {"level": alert["level"], "duration_minutes": 120}
    elif action == "inhibit":
        body |= {"level": alert["level"], "duration_hours": 24}
    body |= overrides
    return client.post(f"/api/alerts/{action}", json=body)


def _alert(client: TestClient) -> dict:
    return client.get("/api/status").json()["alerts"][0]


def test_a_suppressed_alert_stays_visible_with_its_state(
    alerting: tuple[TestClient, dict],
) -> None:
    """Suprimir no borra la alerta: F.6.4 exige mostrar su estado de anuncio."""
    client, status = alerting
    assert _silence(client, status, "suppress").status_code == 201

    alert = _alert(client)
    assert alert["annunciation"] == "suppressed"
    assert alert["silenced_by"] == "comandante"
    assert alert["silenced_reason"] == "sensor de pulso con mal contacto"
    assert alert["level"] == status["alerts"][0]["level"]


def test_a_suppression_expires_by_itself(alerting: tuple[TestClient, dict]) -> None:
    client, status = alerting
    reference = dt.datetime.fromisoformat(status["data"]["reference_time"])
    _silence(
        client, status, "suppress",
        reference_time=(reference - dt.timedelta(hours=1)).isoformat(), duration_minutes=15,
    )
    assert _alert(client)["annunciation"] == "normal"


def test_an_escalation_breaks_a_suppression(alerting: tuple[TestClient, dict]) -> None:
    """Lo suprimido era un nivel: otro nivel es otra alerta y se anuncia."""
    client, status = alerting
    current = status["alerts"][0]["level"]
    lower = "watch" if current != "watch" else None
    assert lower is not None, "el escenario debe alertar por encima de vigilancia"
    _silence(client, status, "suppress", level=lower)

    assert _alert(client)["annunciation"] == "normal"


def test_a_critical_alert_is_suppressed_one_hour_at_most(client: TestClient) -> None:
    # Hace falta una alerta critica que exista: solo se suprime lo que esta alertando. La
    # dosis de carrera registrada en el limite la da sin depender de rafagas de lecturas.
    client.post(
        "/api/observations",
        json={"key": "cumulative-dose", "value": 600.0, "source": "dosimeter"},
    )
    status = client.get("/api/status").json()
    [alert] = [a for a in status["alerts"] if a["domain"] == "radiation"]
    assert alert["level"] == "critical"
    body = {
        "domain": "radiation", "level": "critical",
        "reference_time": status["data"]["reference_time"],
        "reason": "dosimetro en revision", "requested_by": "comandante",
    }
    too_long = client.post("/api/alerts/suppress", json={**body, "duration_minutes": 61})
    assert too_long.status_code == 422
    one_hour = client.post("/api/alerts/suppress", json={**body, "duration_minutes": 60})
    assert one_hour.status_code == 201


def test_silencing_needs_a_reason(alerting: tuple[TestClient, dict]) -> None:
    client, status = alerting
    assert _silence(client, status, "suppress", reason="   ").status_code == 422
    assert _silence(client, status, "inhibit", reason="").status_code == 422


def test_an_inhibition_is_declared_as_reduced_monitoring(
    alerting: tuple[TestClient, dict],
) -> None:
    client, status = alerting
    assert _silence(client, status, "inhibit").status_code == 201

    after = client.get("/api/status").json()
    assert after["alerts"][0]["annunciation"] == "inhibited"
    capability = _capabilities(after)["alert-annunciation"]
    assert capability["available"] is False
    assert "comandante" in capability["consequence"]
    # Es una decision de la tripulacion, no un dato que falte.
    assert capability["cause"] == "manual"
    assert _capabilities(after)["career-dose"]["cause"] == "missing"
    assert after["monitoring"]["level"] == "reduced"


def test_a_critical_domain_cannot_be_inhibited(alerting: tuple[TestClient, dict]) -> None:
    client, status = alerting
    response = _silence(client, status, "inhibit", level="critical")
    assert response.status_code == 422


def test_an_escalation_breaks_an_inhibition_but_monitoring_still_says_it(
    alerting: tuple[TestClient, dict],
) -> None:
    client, status = alerting
    if status["alerts"][0]["level"] == "watch":
        pytest.skip("hace falta una alerta por encima de vigilancia")
    _silence(client, status, "inhibit", level="watch")

    after = client.get("/api/status").json()
    assert after["alerts"][0]["annunciation"] == "normal"
    assert _capabilities(after)["alert-annunciation"]["available"] is False


def test_enable_undoes_suppression_and_inhibition(alerting: tuple[TestClient, dict]) -> None:
    client, status = alerting
    _silence(client, status, "inhibit")
    assert _silence(client, status, "enable", reason="sensor recolocado").status_code == 201

    after = client.get("/api/status").json()
    assert after["alerts"][0]["annunciation"] == "normal"
    assert _capabilities(after)["alert-annunciation"]["available"] is True


def test_every_silencing_is_signed_in_the_ledger(alerting: tuple[TestClient, dict]) -> None:
    client, status = alerting
    _silence(client, status, "suppress")
    _silence(client, status, "enable", reason="ya atendido")

    entries = client.get("/api/audit", params={"limit": 2}).json()["entries"]
    assert [entry["entry_type"] for entry in entries] == ["alert-annunciation"] * 2
    assert {entry["signer"] for entry in entries} == {"crew-console"}


def test_earth_does_not_see_a_silencing_decided_after_its_data(
    alerting: tuple[TestClient, dict],
) -> None:
    """El estado de hace un tiempo de luz no puede mostrar lo silenciado despues."""
    client, status = alerting
    _silence(client, status, "suppress")
    reference = dt.datetime.fromisoformat(status["data"]["reference_time"])
    earlier = (reference - dt.timedelta(minutes=30)).isoformat()

    past = client.get("/api/status", params={"until": earlier}).json()
    assert all(alert["annunciation"] == "normal" for alert in past["alerts"])


def test_a_tampered_silencing_cannot_hide_an_alert(alerting: tuple[TestClient, dict]) -> None:
    from dataclasses import replace

    from app.api.routes import get_store

    client, status = alerting
    index = _silence(client, status, "suppress").json()["ledger_index"]
    store = get_store()
    entry = store.ledger._entries[index]
    store.ledger._entries[index] = replace(
        entry, payload={**entry.payload, "until": "2099-01-01T00:00:00+00:00"}
    )

    assert client.get("/api/status").status_code == 409


# --------------------------------------------------------------------------- #
# Cambiar de escenario sin cerrar la aplicacion
# --------------------------------------------------------------------------- #


def test_replace_switches_the_scenario_without_mixing(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "arrhythmia", "days": 10})
    before = client.get("/api/status").json()

    response = client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 10, "replace": True}
    )
    assert response.status_code == 201
    assert response.json()["replaced"] is True

    after = client.get("/api/status").json()
    assert after["mission"]["sources"] == ["simulator:nominal"]
    # Las mismas lecturas que un solo escenario: no se han sumado las dos series.
    assert after["data"]["observations"] == before["data"]["observations"]


def test_replace_never_discards_a_real_reading(client: TestClient) -> None:
    """Una lectura real es un registro clinico: sustituir el almacen la borraria."""
    client.post("/api/simulate", params={"scenario": "nominal", "days": 10})
    reference = client.get("/api/status").json()["data"]["reference_time"]
    client.post(
        "/api/observations",
        json={"key": "heart-rate", "value": 61.0, "effective": reference, "source": "wearable-ble"},
    )
    total = client.get("/api/audit").json()["total_entries"]

    response = client.post(
        "/api/simulate", params={"scenario": "arrhythmia", "days": 10, "replace": True}
    )
    assert response.status_code == 409
    assert "wearable-ble" in response.json()["detail"]
    # El almacen sigue intacto.
    assert client.get("/api/audit").json()["total_entries"] == total


def test_acknowledgements_of_simulated_alerts_do_not_block_a_switch(
    alerting: tuple[TestClient, dict],
) -> None:
    client, status = alerting
    _ack(client, status)
    response = client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 10, "replace": True}
    )
    assert response.status_code == 201


# --------------------------------------------------------------------------- #
# Revision adversaria (Codex, 2026-09-23), tanda 1: fallos altos reproducidos
# --------------------------------------------------------------------------- #


def _real_concern(client: TestClient, minutes_ago: int = 30) -> dict:
    """Dos pulsos de 120 en reposo, recientes, de un wearable: una alerta real."""
    now = dt.datetime.now(dt.UTC)
    for offset in (minutes_ago + 1, minutes_ago):
        client.post(
            "/api/observations",
            json={
                "key": "heart-rate", "value": 120.0, "context": "rest", "source": "wearable-ble",
                "effective": (now - dt.timedelta(minutes=offset)).isoformat(),
            },
        )
    status = client.get("/api/status").json()
    assert status["alerts"], "dos pulsos de 120 en reposo deben alertar"
    return status


@pytest.mark.parametrize(
    "source",
    ["simulator", "simulator:nominal", "crew-console", "emma-audit", "halo-audit", "halo-forecast",
     "emma-forecast"],
)
def test_public_ingest_cannot_use_a_reserved_identity(client: TestClient, source: str) -> None:
    """Una lectura real firmada como simulada la descartaria un cambio de escenario."""
    response = client.post(
        "/api/observations", json={"key": "heart-rate", "value": 61.0, "source": source}
    )
    assert response.status_code == 422


def test_a_third_reading_dated_in_2099_cannot_hide_an_alert(client: TestClient) -> None:
    before = _real_concern(client)
    client.post(
        "/api/observations",
        json={"key": "body-weight", "value": 72.0, "effective": "2099-01-01T00:00:00+00:00"},
    )
    after = client.get("/api/status").json()

    assert after["overall_level"] == before["overall_level"]
    assert after["data"]["readings_ignored"]["after_reference"] == 1


def test_an_alert_that_does_not_exist_cannot_be_suppressed(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "nominal", "days": 10})
    status = client.get("/api/status").json()
    response = client.post(
        "/api/alerts/suppress",
        json={
            "domain": "cardiovascular", "level": "critical", "duration_minutes": 60,
            "reference_time": status["data"]["reference_time"],
            "reason": "preventivo", "requested_by": "comandante",
        },
    )
    assert response.status_code == 409


def test_an_alert_that_does_not_exist_cannot_be_acknowledged(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "nominal", "days": 10})
    status = client.get("/api/status").json()
    response = client.post(
        "/api/alerts/acknowledge",
        json={
            "domain": "cardiovascular", "level": "critical",
            "reference_time": status["data"]["reference_time"], "acknowledged_by": "comandante",
        },
    )
    assert response.status_code == 409


def test_a_suppression_expires_with_the_clock_even_without_new_readings(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si el sensor calla, una supresion de una hora no puede durar para siempre."""
    import app.api.routes as routes

    status = _real_concern(client, minutes_ago=5)
    alert = status["alerts"][0]
    client.post(
        "/api/alerts/suppress",
        json={
            "domain": alert["domain"], "level": alert["level"], "duration_minutes": 60,
            "reference_time": status["data"]["reference_time"],
            "reason": "en valoración", "requested_by": "comandante",
        },
    )
    assert client.get("/api/status").json()["alerts"][0]["annunciation"] == "suppressed"

    later = dt.datetime.now(dt.UTC) + dt.timedelta(hours=3)
    monkeypatch.setattr(routes, "_now", lambda: later)
    assert client.get("/api/status").json()["alerts"][0]["annunciation"] == "normal"


def test_a_silencing_signed_by_a_data_source_is_ignored(alerting: tuple[TestClient, dict]) -> None:
    """Con la clave de un wearable no se puede inhibir nada, ni saltarse los limites."""
    from app.api.routes import get_store, identity_for

    client, status = alerting
    alert = status["alerts"][0]
    get_store().set_annunciation(
        "crew-01", "inhibit", alert["domain"], "critical",
        dt.datetime.fromisoformat(status["data"]["reference_time"]),
        dt.datetime(2099, 1, 1, tzinfo=dt.UTC),
        "falsificado", "nadie", identity_for("wearable-ble"),
    )
    get_store().acknowledge(
        "crew-01", alert["domain"], alert["level"],
        dt.datetime.fromisoformat(status["data"]["reference_time"]), "nadie",
        identity_for("wearable-ble"),
    )
    after = client.get("/api/status").json()["alerts"][0]
    assert after["annunciation"] == "normal"
    assert after["acknowledged"] is False


def test_a_console_silencing_beyond_its_limits_is_ignored(
    alerting: tuple[TestClient, dict],
) -> None:
    """Aunque lo firme la consola: una inhibicion critica hasta 2099 no se respeta."""
    from app.api.routes import CONSOLE_IDENTITY, get_store, identity_for

    client, status = alerting
    alert = status["alerts"][0]
    get_store().set_annunciation(
        "crew-01", "inhibit", alert["domain"], "critical",
        dt.datetime.fromisoformat(status["data"]["reference_time"]),
        dt.datetime(2099, 1, 1, tzinfo=dt.UTC),
        "falsificado", "nadie", identity_for(CONSOLE_IDENTITY),
    )
    assert client.get("/api/status").json()["alerts"][0]["annunciation"] == "normal"


def test_a_recorded_career_dose_triggers_the_limit(client: TestClient) -> None:
    client.post(
        "/api/observations",
        json={"key": "cumulative-dose", "value": 600.0, "source": "dosimeter"},
    )
    status = client.get("/api/status").json()

    assert status["domains"]["radiation"]["level"] == "critical"
    assert status["dose"]["cumulative_msv"] == 600.0
    assert status["dose"]["source"] == "observation"


def test_earth_does_not_see_an_action_decided_after_its_cutoff(client: TestClient) -> None:
    """Lectura a las T, accion a las T+20 min, Tierra con datos hasta T+10 min."""
    status = _real_concern(client, minutes_ago=20)
    alert = status["alerts"][0]
    client.post(
        "/api/alerts/suppress",
        json={
            "domain": alert["domain"], "level": alert["level"], "duration_minutes": 120,
            "reference_time": status["data"]["reference_time"],
            "reason": "en valoración", "requested_by": "comandante",
        },
    )
    cutoff = (dt.datetime.now(dt.UTC) - dt.timedelta(minutes=10)).isoformat()
    earth = client.get("/api/status", params={"until": cutoff}).json()

    assert earth["alerts"][0]["annunciation"] == "normal"
