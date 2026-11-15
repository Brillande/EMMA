"""La tripulación ante un evento solar, de un vistazo (decimoctava ronda, U8, §5.38.8).

`GET /api/crew/radiation` pone juntas, por tripulante, la ubicación declarada y la dosis de misión
y de carrera que ya calcula su estado, con el evento solar que elige el estado y el procedimiento
de refugio de su escala aguda. Lo que estas pruebas fijan: cada cifra es la de `GET /api/status`
(si el estado cambia cómo la calcula, esta vista no se queda atrás); la ubicación es la de
`GET /api/crew`; el evento es uno para toda la respuesta, el del estado; lo que falta se dice; el
corte de Tierra; sin factores de blindaje; y nada de esto firma ni decide nada. Sin red.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import location, radiation
from app.api import crew_radiation, routes
from app.api.routes import get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.core.versioning import FINGERPRINTED
from app.environment import habitat
from app.environment.donki import EventType, SolarEvent
from app.environment.donki import Severity as SolarSeverity
from app.main import app
from app.text_guard import check
from tests.test_habitat_sources import _verdict

T0 = dt.datetime(2026, 12, 1, 0, 0, tzinfo=dt.UTC)


def _dose(client: TestClient, subject: str, value: float, at: dt.datetime) -> None:
    response = client.post("/api/observations", json={
        "key": "absorbed-dose-rate", "value": value, "subject": subject, "source": "dosimeter",
        "effective": at.isoformat(),
    })
    assert response.status_code == 201, response.text


def _locate(client: TestClient, subject: str, module: str, start: dt.datetime,
            end: dt.datetime) -> None:
    response = client.post("/api/mission/events", json={
        "subject": subject, "kind": "location", "module": module,
        "start": start.isoformat(), "end": end.isoformat(), "declared_by": "CDR",
    })
    assert response.status_code == 201, response.text


def _profile(client: TestClient, subject: str, dose_msv: float) -> None:
    response = client.post("/api/crew/profile", json={
        "subject": subject, "prior_missions": 1, "prior_career_dose_msv": dose_msv,
        "declared_by": "CMO",
    })
    assert response.status_code == 201, response.text


def _event(event_id: str, at: dt.datetime) -> SolarEvent:
    return SolarEvent(
        event_id=event_id, event_type=EventType.SEP, time=at, severity=SolarSeverity.HIGH,
        instruments=(), linked_event_ids=(), flare_class=None,
        link=f"https://example.invalid/{event_id}",
    )


def _view(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/api/crew/radiation", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _by_subject(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["subject"]: item for item in body["crew"]}


def test_each_member_has_the_dose_of_their_own_state_and_their_declared_location(
    client: TestClient,
) -> None:
    for hour in range(6):
        _dose(client, "crew-01", 10.0 + hour, T0 + dt.timedelta(hours=hour))
        _dose(client, "crew-02", 150.0, T0 + dt.timedelta(hours=hour))
    _profile(client, "crew-01", 120.0)
    _locate(client, "crew-02", "laboratorio", T0, T0 + dt.timedelta(days=1))

    body = _view(client)
    crew = _by_subject(body)
    assert list(crew) == ["crew-01", "crew-02"]
    for subject, member in crew.items():
        status = client.get("/api/status", params={"subject": subject}).json()
        # La misma cifra que el estado, con su tipo tal cual: no se recalcula aquí.
        assert member["mission"] == status["radiation"]["mission"]
        assert member["career"] == status["radiation"]["career"]
        assert member["mission"]["observation_type"] == "inferred"
        assert member["mission_missing_text"] is None
    assert crew["crew-01"]["career"]["value_msv"] is not None
    assert crew["crew-01"]["career"]["observation_type"] == "inferred"
    # Sin dosis previa declarada no se supone cero: lo dice la escala del estado.
    assert crew["crew-02"]["career"]["value_msv"] is None
    assert "no se supone cero" in crew["crew-02"]["career"]["basis"]

    # La ubicación es la de la vista de tripulación, en el mismo instante de referencia.
    overview = client.get("/api/crew").json()
    assert body["reference_time"] == overview["reference_time"]
    located = {item["subject"]: item["location"] for item in overview["crew"]}
    assert crew["crew-02"]["location"] == located["crew-02"]
    assert crew["crew-02"]["location"]["module"] == "laboratorio"
    assert crew["crew-02"]["location_missing_text"] is None
    assert crew["crew-01"]["location"] is None
    # Sin anclas de módulo declaradas, la medida no está disponible (2026-11-10).
    assert crew["crew-01"]["location_missing_text"] == location.LOCATION_UNAVAILABLE
    assert crew["crew-01"]["location_state"] == "unavailable"
    assert crew["crew-02"]["location_state"] == "declared"


def test_with_the_scenario_every_figure_is_the_one_of_each_state(client: TestClient) -> None:
    client.post(
        "/api/simulate",
        params={"scenario": "spe-event", "days": 5, "crew_size": 3, "replace": True},
    )
    _profile(client, "crew-03", 40.0)
    crew = _by_subject(_view(client))
    assert list(crew) == ["crew-01", "crew-02", "crew-03"]
    for subject, member in crew.items():
        radiation = client.get("/api/status", params={"subject": subject}).json()["radiation"]
        assert (member["mission"], member["career"]) == (
            radiation["mission"], radiation["career"],
        )
        assert member["mission"]["value_msv"] > 0


def test_without_two_dose_readings_the_mission_dose_is_said_to_be_missing(
    client: TestClient,
) -> None:
    _dose(client, "crew-01", 12.0, T0)
    [member] = _view(client)["crew"]
    assert member["mission"] is None
    assert member["mission_missing_text"] == crew_radiation.MISSION_MISSING


def test_the_event_is_the_one_the_state_chooses_with_the_orion_shelter(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    detected = now - dt.timedelta(hours=5)
    monkeypatch.setattr(
        routes, "_fetch_solar_events",
        lambda settings: ([_event("SEP-HOY", detected)], ("hace 4 min", 240)),
    )
    # Las lecturas, después del evento: `T0` es fija y el evento va con el reloj real.
    first = now - dt.timedelta(hours=2)
    _dose(client, "crew-01", 12.0, first)
    _dose(client, "crew-02", 12.0, first + dt.timedelta(hours=1))

    body = _view(client)
    status = client.get("/api/status", params={"subject": "crew-01"}).json()
    solar = body["solar_event"]
    assert solar["state"] == habitat.SOLAR_ACTIVE
    assert solar["event"] == status["active_solar_event"]
    # La misma frase y el mismo bloque que la radiación del hábitat.
    assert solar == client.get("/api/habitat").json()["radiation"]["solar_event"]
    shelter = body["shelter"]
    acute = status["radiation"]["acute"]["time_to_action"]
    for key in ("detected_at", "shelter_ready_by", "max_stay_until", "basis", "source"):
        assert shelter[key] == acute[key]
    assert shelter["shelter_ready_by"] == (detected + dt.timedelta(hours=1)).isoformat()
    assert shelter["max_stay_until"] == (detected + dt.timedelta(hours=24)).isoformat()
    # Contado hasta el instante de referencia de la tripulación (la lectura más reciente).
    reference = first + dt.timedelta(hours=1)
    assert body["reference_time"] == reference.isoformat()
    assert shelter["elapsed_minutes"] == round((reference - detected).total_seconds() / 60)
    assert shelter["elapsed_note"] is None
    assert body["shelter_missing_text"] is None


def test_on_earth_an_event_after_the_cut_has_no_elapsed_time_and_says_why(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    detected = now - dt.timedelta(hours=5)
    monkeypatch.setattr(
        routes, "_fetch_solar_events",
        lambda settings: ([_event("SEP-HOY", detected)], ("hace 4 min", 240)),
    )
    reading = detected - dt.timedelta(hours=3)
    _dose(client, "crew-01", 12.0, reading)
    # El refugio empieza después del corte de Tierra: nada de minutos negativos.
    cut = (reading + dt.timedelta(minutes=1)).isoformat()
    ground = client.get("/api/status", params={"subject": "crew-01", "until": cut}).json()
    for shelter in (_view(client, until=cut)["shelter"],
                    ground["radiation"]["acute"]["time_to_action"]):
        assert shelter["elapsed_minutes"] is None
        assert shelter["elapsed_note"] == radiation.SHELTER_NOT_STARTED


def test_one_event_for_the_whole_answer_even_if_donki_changes_between_calls(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = dt.datetime.now(dt.UTC)
    first = _event("SEP-ESTADO", now - dt.timedelta(hours=2))
    later = _event("SEP-OTRA", now - dt.timedelta(hours=1))
    calls: list[int] = []

    def fetch(settings: Any) -> tuple[list[SolarEvent], tuple[str, int]]:
        calls.append(1)
        return ([first] if len(calls) == 1 else [later]), ("ahora", 0)

    monkeypatch.setattr(routes, "_fetch_solar_events", fetch)
    _dose(client, "crew-01", 12.0, T0)
    _dose(client, "crew-02", 12.0, T0)
    body = _view(client)
    assert body["solar_event"]["event"]["event_id"] == "SEP-ESTADO"
    assert body["shelter"]["detected_at"] == first.time.isoformat()


def test_without_donki_it_is_not_known_and_there_is_no_shelter_to_count(
    client: TestClient,
) -> None:
    _dose(client, "crew-01", 12.0, T0)
    body = _view(client)
    # Modo sin red y sin caché: no se sabe, y no se dice que no haya evento.
    assert body["solar_event"]["state"] == habitat.SOLAR_UNKNOWN
    assert body["solar_event"]["text"] == habitat.SOLAR_UNAVAILABLE
    assert body["shelter"] is None
    assert body["shelter_missing_text"] == crew_radiation.NO_EVENT_SHELTER


def test_no_shielding_factor_and_no_module_changes_any_figure(client: TestClient) -> None:
    for hour in range(4):
        _dose(client, "crew-01", 100.0, T0 + dt.timedelta(hours=hour))
    before = _by_subject(_view(client))["crew-01"]
    _locate(client, "crew-01", "camarotes", T0, T0 + dt.timedelta(days=1))
    after = _view(client)
    member = _by_subject(after)["crew-01"]
    assert member["location"]["module"] == "camarotes"
    # Declarar otro módulo no corrige ni reparte ninguna cifra.
    assert (member["mission"], member["career"]) == (before["mission"], before["career"])
    assert after["shielding"] == crew_radiation.NO_SHIELDING
    assert after["evaluated"] is False
    assert all("shield" not in key for key in member)


def test_the_ground_sees_only_what_reached_it(tmp_path: Path) -> None:
    # Una misión que empezó en enero: el corte de Tierra puede caer antes de que la consola
    # declarase (hoy) la ubicación y el perfil.
    start = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, mission_start=start.date(),
    )
    try:
        client = TestClient(app)
        for hour in range(8):
            _dose(client, "crew-01", 10.0, start + dt.timedelta(hours=hour))
        _profile(client, "crew-01", 100.0)
        _locate(client, "crew-01", "esclusa", start, start + dt.timedelta(days=2))

        cut = (start + dt.timedelta(hours=3)).isoformat()
        ground = _by_subject(_view(client, until=cut))["crew-01"]
        status = client.get("/api/status", params={"subject": "crew-01", "until": cut}).json()
        assert ground["mission"] == status["radiation"]["mission"]
        assert ground["career"] == status["radiation"]["career"]
        assert ground["mission"]["samples"] == 4
        # Lo declarado hoy no existía en un corte de enero.
        assert ground["location"] is None
        assert ground["career"]["value_msv"] is None

        onboard = _by_subject(_view(client))["crew-01"]
        assert onboard["mission"]["samples"] == 8
        assert onboard["location"]["module"] == "esclusa"
        assert onboard["career"]["value_msv"] is not None

        naive = client.get("/api/crew/radiation", params={"until": "2026-01-01T03:00:00"})
        assert naive.status_code == 422
    finally:
        app.dependency_overrides.clear()
        reset_store(None)


def test_a_member_without_an_analysable_state_keeps_their_row_and_location(
    client: TestClient,
) -> None:
    for hour in range(3):
        _dose(client, "crew-01", 10.0, T0 + dt.timedelta(hours=hour))
    # crew-02 solo tiene una lectura inferida: su estado da 404, y sigue en la vista.
    response = client.post("/api/observations", json={
        "key": "absorbed-dose-rate", "value": 12.0, "subject": "crew-02", "source": "modelo",
        "effective": T0.isoformat(), "observation_type": "inferred", "model_version": "modelo@1",
    })
    assert response.status_code == 201, response.text
    _locate(client, "crew-02", "esclusa", T0, T0 + dt.timedelta(days=1))
    assert client.get("/api/status", params={"subject": "crew-02"}).status_code == 404

    crew = _by_subject(_view(client))
    assert list(crew) == ["crew-01", "crew-02"]
    member = crew["crew-02"]
    assert member["location"]["module"] == "esclusa"
    assert member["mission"] is None and member["career"] is None
    assert member["state_missing_text"] == crew_radiation.STATE_MISSING
    assert crew["crew-01"]["state_missing_text"] is None


def test_one_member_with_unreadable_dates_does_not_hide_the_crew(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    for subject in ("crew-01", "crew-02"):
        for hour in range(3):
            _dose(client, subject, 10.0, T0 + dt.timedelta(hours=hour))
    real = crew_radiation._assess

    def assess(settings: Any, store: Any, subject: str, *args: Any) -> Any:
        # La 422 de `_assess` cuando ninguna lectura tiene fecha analizable (como en
        # test_waiting.py): es de ese tripulante, no de la petición.
        if subject == "crew-02":
            raise routes.HTTPException(status_code=422, detail="ninguna lectura analizable")
        return real(settings, store, subject, *args)

    monkeypatch.setattr(crew_radiation, "_assess", assess)
    crew = _by_subject(_view(client))
    assert crew["crew-01"]["mission"] is not None
    assert crew["crew-02"]["state_missing_text"] == crew_radiation.STATE_MISSING


def test_another_failure_of_a_state_is_not_disguised_as_missing_readings(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    for subject in ("crew-01", "crew-02"):
        for hour in range(3):
            _dose(client, subject, 10.0, T0 + dt.timedelta(hours=hour))
    real = crew_radiation._assess

    def assess(settings: Any, store: Any, subject: str, *args: Any) -> Any:
        if subject == "crew-02":
            raise routes.HTTPException(status_code=503, detail="otro fallo")
        return real(settings, store, subject, *args)

    monkeypatch.setattr(crew_radiation, "_assess", assess)
    assert TestClient(app, raise_server_exceptions=False).get(
        "/api/crew/radiation"
    ).status_code == 503


def test_the_ground_does_not_list_a_member_whose_readings_have_not_reached_it(
    client: TestClient,
) -> None:
    for hour in range(3):
        _dose(client, "crew-01", 10.0, T0 + dt.timedelta(hours=hour))
    # crew-02 solo tiene lecturas posteriores al corte: en Tierra aún no existe.
    for hour in range(5, 8):
        _dose(client, "crew-02", 10.0, T0 + dt.timedelta(hours=hour))
    cut = (T0 + dt.timedelta(hours=3)).isoformat()
    assert list(_by_subject(_view(client, until=cut))) == ["crew-01"]
    assert list(_by_subject(_view(client))) == ["crew-01", "crew-02"]


def test_without_crew_data_it_says_so(client: TestClient) -> None:
    response = client.get("/api/crew/radiation")
    assert response.status_code == 404


def test_it_signs_nothing_and_decides_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.post("/api/simulate", params={"scenario": "spe-event", "days": 10, "crew_size": 2})
    event = _event("SEP-HOY", dt.datetime.now(dt.UTC))
    monkeypatch.setattr(routes, "_fetch_solar_events", lambda settings: ([event], ("ahora", 0)))
    _locate(client, "crew-01", "laboratorio", T0 - dt.timedelta(days=40), T0)
    before = _verdict(client)
    size = len(get_store().ledger)

    body = _view(client)
    assert body["solar_event"]["state"] == habitat.SOLAR_ACTIVE
    assert len(get_store().ledger) == size, "enseñar la vista no firma nada"
    assert _verdict(client) == before
    # Ni la vista ni su módulo entran en la huella de las reglas (`rules_version` de cada
    # tripulante ya va en el veredicto de arriba).
    assert "app.api.crew_radiation" not in FINGERPRINTED


def test_nothing_written_here_sounds_like_an_order() -> None:
    texts = [
        crew_radiation.DISPLAY, crew_radiation.BASIS, crew_radiation.LOCATION_BASIS,
        location.LOCATION_MISSING, location.LOCATION_UNAVAILABLE, crew_radiation.MISSION_MISSING,
        crew_radiation.NO_SHIELDING, crew_radiation.NOT_EVALUATED,
        crew_radiation.NO_EVENT_SHELTER, crew_radiation.STATE_MISSING,
    ]
    for text in texts:
        # «dosis» es aquí de radiación, no de un fármaco (como en test_radiation_read.py).
        found = [
            finding for finding in check(text)
            if (finding.category, finding.match.lower()) != ("dosing", "dosis")
        ]
        assert found == [], text

