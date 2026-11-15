"""El evento solar en la demo sin red, y la vuelta a la normalidad (2026-11-04).

Tres piezas, cada una con su prueba:

* **La instantánea fechada de DONKI** (`environment/donki.py`). Sin red y sin caché, con
  `donki_snapshot`, el cliente sirve la instantánea del paquete: su edad es la de la descarga y
  se dice «instantánea de DONKI del <fecha>, no en vivo»; nunca tapa una caché ni un dato en vivo
  y no se escribe en la caché. Sus eventos llevan su fecha real: no es un evento vigente, y el
  hábitat dice que no lo es y que los datos no cubren los últimos días. Aquí la instantánea es un
  fichero de prueba con la forma de DONKI, en `tmp_path`: la suite no lee la red ni depende de
  que el paquete lleve una.
* **La dosis de a bordo acorta los periodos** (`app/routines.py`): sin evento de DONKI, la última
  tasa de dosis por encima de su límite de peligro; con él, manda el de DONKI.
* **`spe-event-recovery`** (`ingest/simulator.py`): el pico empieza antes y la dosis vuelve a su
  fondo; la línea temporal ve el comienzo, el periodo intensificado y la vuelta.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app import routines, text_guard
from app.api import routes
from app.api.routes import new_store, reset_store
from app.core.cache import FileCache, OfflineDataUnavailable
from app.core.config import Settings, get_settings
from app.environment import donki
from app.environment.donki import DonkiClient, EventType, SnapshotPayload, SolarEvent
from app.environment.donki import Severity as SolarSeverity
from app.environment.habitat import SOLAR_UNKNOWN
from app.ingest.fhir import observation
from app.ingest.simulator import LITERATURE, PhysiologicalSimulator, Scenario
from app.main import app

# Un mes antes de hoy en la suite: caducada siempre (el plazo de DONKI es de 6 h).
RETRIEVED = dt.datetime(2026, 10, 4, 12, 0, tzinfo=dt.UTC)
WINDOW = (dt.date(2025, 11, 4), dt.date(2026, 11, 4))


def _snapshot_body(events: list[dict[str, object]]) -> dict[str, object]:
    return {
        "event_type": "SEP",
        "source_url": "https://api.nasa.gov/DONKI/SEP?startDate=2025-11-04&endDate=2026-11-04",
        "retrieved_at": RETRIEVED.isoformat(),
        "window": {"startDate": "2025-11-04", "endDate": "2026-11-04"},
        "licence": donki.SNAPSHOT_LICENCE,
        "raw": events,
    }


def _sep(sep_id: str, when: str) -> dict[str, object]:
    """Un SEP con los campos que DONKI devuelve y el cliente lee (datos de prueba)."""
    return {
        "sepID": sep_id,
        "eventTime": when,
        "instruments": [{"displayName": "GOES-18: SEISS >10 MeV"}],
        "linkedEvents": [{"activityID": "2026-05-01T10:00:00-CME-001"}],
        "link": f"https://webtools.ccmc.gsfc.nasa.gov/DONKI/view/SEP/{sep_id}/1",
    }


@pytest.fixture
def snapshot_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "donki_snapshot.json"
    body = _snapshot_body([
        _sep("2026-05-02T08:00:00-SEP-001", "2026-05-02T08:00Z"),
        _sep("2025-01-01T00:00:00-SEP-001", "2025-01-01T00:00Z"),  # fuera de la ventana
    ])
    path.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setattr(donki, "SNAPSHOT", path)
    donki.load_snapshot.cache_clear()
    yield path
    donki.load_snapshot.cache_clear()


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(cache_dir=tmp_path / "cache", **{"offline": True, **overrides})  # type: ignore[arg-type]


def _guarded(text: str) -> list[text_guard.Finding]:
    """El filtro de lenguaje (invariante 7), salvo «dosis» en «tasa de dosis»: es la magnitud
    física del dosímetro, no la dosis de un fármaco, como en el resto de textos de radiación."""
    return [
        item for item in text_guard.check(text)
        if not (item.category == "dosing" and item.match == "dosis"
                and "tasa de dosis" in text_guard.normalize(text))
    ]


# --------------------------------------------------------------------------- #
# La instantánea
# --------------------------------------------------------------------------- #


def test_offline_without_cache_serves_the_snapshot_and_says_it_is_not_live(
    tmp_path: Path, snapshot_file: Path
) -> None:
    payload = DonkiClient(settings=_settings(tmp_path, donki_snapshot=True)).events(
        EventType.SEP, *WINDOW
    )
    assert isinstance(payload, SnapshotPayload)
    assert payload.from_cache is True
    assert payload.fetched_at == RETRIEVED  # su edad es la de la descarga
    assert "instantánea de DONKI del 2026-10-04, no en vivo" in payload.describe_age()
    assert "no en vivo" in payload.source
    assert payload.snapshot["live"] is False
    assert payload.snapshot["licence"] == donki.SNAPSHOT_LICENCE
    assert payload.snapshot["source_url"].startswith("https://api.nasa.gov/DONKI/SEP")
    # Solo lo de la ventana pedida, con su fecha real.
    events: list[SolarEvent] = payload.data
    assert [event.event_id for event in events] == ["2026-05-02T08:00:00-SEP-001"]
    assert events[0].time == dt.datetime(2026, 5, 2, 8, 0, tzinfo=dt.UTC)
    # No se escribe en la caché: al leerla después parecería una consulta a DONKI.
    assert not list((tmp_path / "cache").rglob("*.json"))


def test_without_the_setting_offline_is_still_an_explicit_failure(
    tmp_path: Path, snapshot_file: Path
) -> None:
    with pytest.raises(OfflineDataUnavailable):
        DonkiClient(settings=_settings(tmp_path)).events(EventType.SEP, *WINDOW)


def test_a_cache_always_wins_over_the_snapshot(tmp_path: Path, snapshot_file: Path) -> None:
    settings = _settings(tmp_path, donki_snapshot=True)
    cache = FileCache(settings.cache_dir / "donki")
    key = f"donki:{EventType.SEP}:{WINDOW[0].isoformat()}:{WINDOW[1].isoformat()}"
    cache.put(key, [], source="NASA DONKI /SEP")
    payload = DonkiClient(settings=settings, cache=cache).events(EventType.SEP, *WINDOW)
    assert not isinstance(payload, SnapshotPayload)
    assert payload.data == []


@respx.mock
def test_a_network_failure_without_cache_falls_back_to_the_snapshot(
    tmp_path: Path, snapshot_file: Path
) -> None:
    respx.get(url__startswith=donki.BASE_URL).mock(side_effect=httpx.ConnectError("sin ruta"))
    payload = DonkiClient(
        settings=_settings(tmp_path, offline=False, donki_snapshot=True)
    ).events(EventType.SEP, *WINDOW)
    assert isinstance(payload, SnapshotPayload)


def _earlier_query(cache: FileCache, fetched_at: dt.datetime) -> None:
    """Una consulta guardada de otra ventana de 365 días (la de ayer), sin eventos."""
    cache.put(
        donki._latest_key(EventType.SEP, *WINDOW),
        {
            "start": (WINDOW[0] - dt.timedelta(days=1)).isoformat(),
            "end": (WINDOW[1] - dt.timedelta(days=1)).isoformat(),
            "fetched_at": fetched_at.isoformat(), "events": [],
        },
        source="NASA DONKI /SEP",
    )


@pytest.mark.parametrize("offline", [True, False])
@respx.mock
def test_an_older_saved_query_does_not_hide_a_newer_snapshot(
    tmp_path: Path, snapshot_file: Path, offline: bool
) -> None:
    """Lógica 1 (2026-11-11): sin la consulta exacta se usa la más reciente de las dos.

    Una consulta de hace meses en la caché tapaba la instantánea de un paquete instalado después.
    """
    respx.get(url__startswith=donki.BASE_URL).mock(side_effect=httpx.ConnectError("sin ruta"))
    settings = _settings(tmp_path, offline=offline, donki_snapshot=True)
    cache = FileCache(settings.cache_dir / "donki")
    _earlier_query(cache, RETRIEVED - dt.timedelta(days=90))
    payload = DonkiClient(settings=settings, cache=cache).events(EventType.SEP, *WINDOW)
    assert isinstance(payload, SnapshotPayload)


def test_a_newer_saved_query_wins_over_the_snapshot(tmp_path: Path, snapshot_file: Path) -> None:
    settings = _settings(tmp_path, donki_snapshot=True)
    cache = FileCache(settings.cache_dir / "donki")
    newer = RETRIEVED + dt.timedelta(days=20)
    _earlier_query(cache, newer)
    payload = DonkiClient(settings=settings, cache=cache).events(EventType.SEP, *WINDOW)
    assert not isinstance(payload, SnapshotPayload)
    assert payload.fetched_at == newer and payload.data == []


@respx.mock
def test_live_data_is_never_replaced_by_the_snapshot(tmp_path: Path, snapshot_file: Path) -> None:
    respx.get(url__startswith=donki.BASE_URL).mock(return_value=httpx.Response(200, json=[]))
    payload = DonkiClient(
        settings=_settings(tmp_path, offline=False, donki_snapshot=True)
    ).events(EventType.SEP, *WINDOW)
    assert not isinstance(payload, SnapshotPayload)
    assert payload.from_cache is False


def test_the_shipped_snapshot_if_any_is_a_dated_donki_answer_with_its_licence() -> None:
    """La del paquete, si viaja: URL de DONKI sin la clave, fecha de descarga y licencia."""
    donki.load_snapshot.cache_clear()
    snapshot = donki.load_snapshot(donki.SNAPSHOT)
    if snapshot is None:
        pytest.skip("el paquete aún no lleva instantánea (scripts/fetch_donki_snapshot.py)")
    assert snapshot.source_url.startswith(f"{donki.BASE_URL}/SEP?")
    assert "api_key" not in snapshot.source_url
    assert snapshot.licence == donki.SNAPSHOT_LICENCE
    assert snapshot.retrieved_at.tzinfo is not None
    for item in snapshot.raw:
        donki.normalize(EventType.SEP, item)


@pytest.fixture
def offline_client(tmp_path: Path, snapshot_file: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path / "cache", offline=True, assistant_warmup=False, donki_snapshot=True
    )
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def test_space_weather_declares_the_snapshot(offline_client: TestClient) -> None:
    body = offline_client.get("/api/space-weather").json()
    assert body["live"] is False
    assert body["snapshot"]["live"] is False
    assert "no en vivo" in body["source"]
    assert "instantánea de DONKI del 2026-10-04" in body["data_age"]
    assert [item["event_id"] for item in body["events"]] == ["2026-05-02T08:00:00-SEP-001"]


def test_the_status_and_the_habitat_show_the_snapshot_as_stale_and_not_in_force(
    offline_client: TestClient,
) -> None:
    assert offline_client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 20, "replace": True}
    ).status_code == 201
    status = offline_client.get("/api/status").json()
    assert status["active_solar_event"] is None
    assert "no en vivo" in status["solar_data_age"]
    assert status["freshness"]["solar"]["is_current"] is False
    space = {item["key"]: item for item in status["monitoring"]["capabilities"]}["space-weather"]
    # Una instantánea no vigila lo que pasa ahora: la capacidad no se da por disponible.
    assert space["available"] is False
    assert "caducados" in space["consequence"]

    solar = offline_client.get("/api/habitat").json()["radiation"]["solar_event"]
    assert solar["state"] == SOLAR_UNKNOWN
    assert "caducados" in solar["text"] and "no se sabe" in solar["text"]
    assert "no en vivo" in solar["data_age"]
    latest = solar["latest_recorded"]
    assert latest["event_id"] == "2026-05-02T08:00:00-SEP-001"
    assert "2026-05-02 08:00 UTC" in latest["text"] and "no está vigente" in latest["text"]
    for text in (solar["text"], latest["text"], space["consequence"]):
        assert _guarded(text) == [], text


# --------------------------------------------------------------------------- #
# La dosis de a bordo acorta los periodos
# --------------------------------------------------------------------------- #

NOW = dt.datetime(2026, 12, 1, 12, 0, tzinfo=dt.UTC)


def _dose(value: float, hours_ago: float, confidence: float = 1.0):  # type: ignore[no-untyped-def]
    return observation(
        "absorbed-dose-rate", value, NOW - dt.timedelta(hours=hours_ago), "crew-01", "t",
        confidence=confidence,
    )


def _routine(result: dict, key: str) -> dict:  # type: ignore[type-arg]
    return next(item for item in result["routines"] if item["key"] == key)


def test_a_dose_above_its_danger_limit_shortens_the_event_routines() -> None:
    result = routines.evaluate([_dose(12.0, 3), _dose(800.0, 0.5)], now=NOW)
    assert result["active_event"] is None  # no es un evento de DONKI
    trigger = result["active_trigger"]
    assert trigger["kind"] == routines.DOSE_TRIGGER and trigger["value"] == 800.0
    dose = _routine(result, "absorbed-dose-rate")
    assert dose["period_hours"] == 1 and dose["period_source"] == routines.EVENT
    assert dose["trigger"] == routines.DOSE_TRIGGER and dose["event_id"] is None
    assert result["routines"][0]["key"] == "absorbed-dose-rate"
    assert result["event_over_note"] is None
    assert "límite de peligro" in result["event_note"]
    for text in (result["event_note"], dose["period_note"], routines.DOSE_OVER_NOTE):
        assert _guarded(text) == [], text
    # Lo que acorta no se llama «evento solar»: una tasa de dosis alta no dice que lo hubo.
    assert "evento solar" not in result["event_note"] + dose["period_note"]


def test_back_under_the_limit_the_design_periods_return() -> None:
    result = routines.evaluate([_dose(800.0, 5), _dose(14.0, 0.5)], now=NOW)
    assert result["active_trigger"] is None
    assert _routine(result, "absorbed-dose-rate")["period_hours"] == 6
    assert result["event_over_note"] == routines.DOSE_OVER_NOTE
    assert result["event_note"] is None


def test_a_future_or_low_confidence_dose_does_not_shorten_anything() -> None:
    future = observation(
        "absorbed-dose-rate", 900.0, NOW + dt.timedelta(hours=1), "crew-01", "t"
    )
    assert routines.evaluate([_dose(12.0, 1), future], now=NOW)["active_trigger"] is None
    low = _dose(900.0, 0.2, confidence=0.1)
    assert routines.evaluate([_dose(12.0, 1), low], now=NOW)["active_trigger"] is None


def test_with_a_donki_event_the_event_rules_and_not_the_dose() -> None:
    event = SolarEvent(
        "SEP-PRUEBA", EventType.SEP, NOW - dt.timedelta(hours=2), SolarSeverity.HIGH,
        (), (), None, "",
    )
    result = routines.evaluate([_dose(800.0, 0.5)], now=NOW, event=event)
    assert result["active_trigger"]["kind"] == routines.SOLAR_TRIGGER
    assert _routine(result, "absorbed-dose-rate")["event_id"] == "SEP-PRUEBA"


# --------------------------------------------------------------------------- #
# spe-event-recovery
# --------------------------------------------------------------------------- #


def _doses(scenario: Scenario) -> list[tuple[float, float]]:
    sim = PhysiologicalSimulator(scenario=scenario, seed=3)
    start = dt.datetime.combine(sim.mission_start, dt.time(0, 0), tzinfo=dt.UTC)
    return [
        ((item.effective - start).total_seconds() / 86400, item.value)
        for item in sim.generate(days=40, keys=["absorbed-dose-rate"])
    ]


def test_the_recovery_scenario_peaks_and_returns_to_its_background() -> None:
    onset = 40 - LITERATURE["spe_recovery_onset_days_before_end"].value
    series = _doses(Scenario.SPE_EVENT_RECOVERY)
    before = [value for day, value in series if day < onset]
    peak = max(value for day, value in series)
    last_day = [value for day, value in series if day >= 39]
    assert max(before) < 100  # antes del evento, el fondo
    assert peak > 1000  # el mismo pico que `spe-event`
    assert max(last_day) < 30  # al final, de vuelta cerca del fondo (12 µGy/h)
    # `spe-event` sigue como estaba: el pico al final de la ventana.
    spe = _doses(Scenario.SPE_EVENT)
    assert max(value for day, value in spe if day >= 39) > 1000


def test_its_parameters_are_declared_and_classified() -> None:
    for name in ("spe_dose_rise_days", "spe_dose_decay_days", "spe_recovery_onset_days_before_end"):
        assert LITERATURE[name].evidence == "design", name


def test_the_timeline_shows_start_intensified_period_and_return(client: TestClient) -> None:
    """Con el corte de Tierra (`until`), la misma serie vista en tres momentos."""
    assert client.post(
        "/api/simulate", params={"scenario": "spe-event-recovery", "replace": True}
    ).status_code == 201
    start = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)

    def at(day: float) -> tuple[dict, dict]:  # type: ignore[type-arg]
        until = (start + dt.timedelta(days=day)).isoformat()
        return (
            client.get("/api/status", params={"until": until}).json(),
            client.get("/api/timeline/routines", params={"until": until}).json(),
        )

    status, rows = at(27.5)  # antes
    assert status["domains"]["radiation"]["level"] == "nominal"
    assert rows["active_trigger"] is None
    status, rows = at(29.0)  # durante: monitorización intensificada
    assert status["domains"]["radiation"]["level"] != "nominal"
    assert rows["active_trigger"]["kind"] == routines.DOSE_TRIGGER
    assert _routine(rows, "absorbed-dose-rate")["period_hours"] == 1
    # Ahora: de vuelta a la normalidad.
    now = client.get("/api/status").json()
    assert now["overall_level"] == "nominal" and now["alerts"] == []
    rows = client.get("/api/timeline/routines").json()
    assert rows["active_trigger"] is None
    assert _routine(rows, "absorbed-dose-rate")["period_hours"] == 6


def test_the_scenario_is_listed_for_the_console(client: TestClient) -> None:
    keys = {item["key"] for item in client.get("/api/scenarios").json()["scenarios"]}
    assert "spe-event-recovery" in keys
    assert routes.SOLAR_EVENT_RELEVANCE  # el evento de DONKI caduca igual; esto no lo toca
