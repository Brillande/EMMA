"""SSCweb: posición de la ISS y contorno de la SAA (`environment/orbit.py`, `api/orbit.py`).

Sin red: respx intercepta httpx y la respuesta grabada (`tests/data/sscweb_iss_locations.json`,
ISS 2026-11-11 12:00-15:00 UTC, descargada tal cual el 2026-11-11) hace de SSCweb. La prueba
`live` comprueba el contrato contra el servicio real.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.api.routes import new_store, reset_store
from app.core.cache import FileCache, OfflineDataUnavailable
from app.core.config import Settings, get_settings
from app.environment import orbit
from app.environment.orbit import (
    BASE_URL,
    CACHE_KEY,
    OrbitClient,
    OrbitDataError,
    OrbitSample,
    describe,
    in_saa_region,
    parse_locations,
)
from app.main import app

RECORDED = Path(__file__).parent / "data" / "sscweb_iss_locations.json"
URL_PATTERN = rf"^{BASE_URL}/locations/iss/\d{{8}}T\d{{6}}Z,\d{{8}}T\d{{6}}Z/geo/$"
# Dentro de la ventana grabada; a las 12:30 la ISS va por el Atlántico Sur (ver la grabación).
NOW = dt.datetime(2026, 11, 11, 12, 30, tzinfo=dt.UTC)


def recorded() -> Any:
    return json.loads(RECORDED.read_text(encoding="utf-8"))


@pytest.fixture
def online(tmp_path: Path) -> Settings:
    return Settings(cache_dir=tmp_path, offline=False)


@pytest.fixture
def offline(tmp_path: Path) -> Settings:
    return Settings(cache_dir=tmp_path, offline=True)


def test_the_recorded_response_parses_with_longitude_in_minus180_180() -> None:
    samples = parse_locations(recorded())
    assert len(samples) == 181
    assert samples[0].time == dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.UTC)
    assert all(-180.0 <= sample.longitude <= 180.0 for sample in samples)
    assert all(-90.0 <= sample.latitude <= 90.0 for sample in samples)
    assert all(6600 < sample.radial_km < 7000 for sample in samples)  # órbita baja


@pytest.mark.parametrize(
    ("lat", "lon", "inside"),
    [
        (-25.0, -45.0, True),   # sobre Brasil
        (-25.0, 315.0, True),   # lo mismo en 0..360, como lo da SSCweb
        (-15.0, -45.0, True),   # el contorno sube por el norte de Brasil
        (-50.0, -40.0, True),
        (-28.19, -53.63, True),  # un vértice: bordes incluidos
        (-21.08, 0.0, True),     # sobre el borde norte del lóbulo este
        (-21.0, 0.0, False),     # justo al norte de ese borde
        (-10.0, 0.0, False),     # el lóbulo este no llega tan al norte
        (-5.0, -80.0, False),    # dentro de la caja de 1996, fuera del contorno de NICER
        (-50.0, 20.0, False),    # ídem, por el sureste
        (-55.0, -40.0, False),   # al sur del contorno
        (-25.0, 140.0, False),   # el otro lado del mundo
    ],
)
def test_saa_region(lat: float, lon: float, inside: bool) -> None:
    assert in_saa_region(lat, lon) is inside


def test_the_saa_region_declares_its_source_and_limits() -> None:
    region = orbit.SAA_REGION
    source = region["source"]
    # Verificado en la fuente primaria (2026-11-11): el contorno SAACONT de la CALDB de NICER.
    assert source["status"] == "verified" and source["read_on"] == "2026-11-11"
    assert source["url"].startswith("https://heasarc.gsfc.nasa.gov/FTP/caldb/data/nicer/")
    assert "nixtisaareg20170601v003" in source["url"]
    polygon = region["polygon"]
    assert len(polygon) == 14 and polygon[0] == polygon[-1]  # cerrado, como en el fichero
    assert all(-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0 for lon, lat in polygon)
    assert len(region["limits"]) >= 4
    assert any("no un contorno de dosis" in limit for limit in region["limits"])
    # La caja de 1996 consta como sustituida, con su fuente leída y su altura (500 km).
    old = region["superseded"]
    assert old["status"] == "verified" and old["altitude_km"] == 500
    assert old["url"] == "https://imagine.gsfc.nasa.gov/ask_astro/earth.html"


@respx.mock
def test_a_good_response_gives_the_position_now(online: Settings) -> None:
    route = respx.get(url__regex=URL_PATTERN).mock(
        return_value=httpx.Response(200, json=recorded())
    )
    payload = OrbitClient(online).samples(NOW)
    assert route.called and not payload.from_cache
    view = describe(payload, NOW)
    assert view["available"] is True
    assert view["position"]["time"] == NOW.isoformat()
    assert view["in_saa_region"] is in_saa_region(
        view["position"]["latitude"], view["position"]["longitude"]
    )
    assert view["age"] and view["fetched_at"]
    assert "no telemetría" in view["kind"]


@respx.mock
def test_the_request_carries_nothing_of_ours(online: Settings, tmp_path: Path) -> None:
    """Solo salen el identificador público de la ISS, dos instantes y `geo`; nada de la tripulación,
    del usuario, del proyecto ni rutas locales (aclaración del usuario, 2026-11-11)."""
    route = respx.get(url__regex=URL_PATTERN).mock(
        return_value=httpx.Response(200, json=recorded())
    )
    OrbitClient(online).samples(NOW)
    request = route.calls.last.request
    assert request.url.host == "sscweb.gsfc.nasa.gov"
    assert request.url.query == b""
    assert request.url.path.startswith("/WS/sscr/2/locations/iss/")
    assert request.method == "GET" and request.content == b""
    sent = (str(request.url) + " " + " ".join(f"{k}: {v}" for k, v in request.headers.items()))
    lowered = sent.lower()
    for forbidden in (
        str(tmp_path).lower(), "c:\\", "/users/", "emma", "crew", "tripul", "astronaut",
        "polaris", "ellande", "cookie", "authorization", "@",
    ):
        assert forbidden not in lowered, forbidden
    assert request.headers["accept"] == "application/json"
    assert request.headers["user-agent"].startswith("python-httpx/")  # genérico


@respx.mock
def test_a_recent_cache_is_used_without_going_out(online: Settings) -> None:
    route = respx.get(url__regex=URL_PATTERN).mock(
        return_value=httpx.Response(200, json=recorded())
    )
    client = OrbitClient(online)
    client.samples(NOW)
    again = client.samples(NOW + dt.timedelta(minutes=5))
    assert route.call_count == 1 and again.from_cache


@respx.mock
def test_a_stale_cache_is_refreshed_when_there_is_network(online: Settings) -> None:
    route = respx.get(url__regex=URL_PATTERN).mock(
        return_value=httpx.Response(200, json=recorded())
    )
    client = OrbitClient(online)
    client.samples(NOW)
    path = client.cache.path_for(CACHE_KEY)
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["fetched_at"] = (dt.datetime.now(dt.UTC) - orbit.FRESH_FOR * 2).isoformat()
    path.write_text(json.dumps(stored), encoding="utf-8")
    again = client.samples(NOW)
    assert route.call_count == 2 and not again.from_cache


@respx.mock
def test_offline_serves_the_cache_with_its_age_and_never_goes_out(
    online: Settings, offline: Settings
) -> None:
    respx.get(url__regex=URL_PATTERN).mock(return_value=httpx.Response(200, json=recorded()))
    OrbitClient(online).samples(NOW)
    respx.reset()
    route = respx.get(url__regex=URL_PATTERN)
    later = NOW + dt.timedelta(hours=2)  # sigue dentro de la ventana grabada
    payload = OrbitClient(offline).samples(later)
    assert not route.called
    assert payload.from_cache
    view = describe(payload, later)
    assert view["available"] and view["position"]["time"] == later.isoformat()
    assert view["age_seconds"] >= 0 and view["age"]


def test_offline_without_cache_is_unavailable(offline: Settings) -> None:
    with pytest.raises(OfflineDataUnavailable):
        OrbitClient(offline).samples(NOW)


@respx.mock
def test_offline_never_extrapolates_past_the_cached_window(
    online: Settings, offline: Settings
) -> None:
    respx.get(url__regex=URL_PATTERN).mock(return_value=httpx.Response(200, json=recorded()))
    OrbitClient(online).samples(NOW)
    with pytest.raises(OfflineDataUnavailable):
        OrbitClient(offline).samples(NOW + dt.timedelta(hours=3, minutes=5))


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>no es JSON</html>"),
        httpx.Response(200, json={"inesperado": True}),
        httpx.Response(500, text="error"),
        httpx.Response(404, text="<html>Error report</html>"),
    ],
    ids=["no-json", "forma-rara", "http-500", "http-404"],
)
def test_a_broken_answer_without_cache_is_unavailable(
    online: Settings, response: httpx.Response
) -> None:
    respx.get(url__regex=URL_PATTERN).mock(return_value=response)
    with pytest.raises(OfflineDataUnavailable):
        OrbitClient(online).samples(NOW)


@respx.mock
def test_a_broken_answer_falls_back_to_a_cache_that_covers_now(online: Settings) -> None:
    respx.get(url__regex=URL_PATTERN).mock(return_value=httpx.Response(200, json=recorded()))
    OrbitClient(online).samples(NOW)
    respx.reset()
    respx.get(url__regex=URL_PATTERN).mock(side_effect=httpx.ConnectError("sin enlace"))
    later = NOW + dt.timedelta(hours=1)
    # La caché tiene más de `FRESH_FOR` para ese instante: se intenta salir, falla y se usa.
    cache = FileCache(online.cache_dir / "sscweb")
    stored = json.loads(cache.path_for(CACHE_KEY).read_text(encoding="utf-8"))
    stored["fetched_at"] = (dt.datetime.now(dt.UTC) - dt.timedelta(hours=2)).isoformat()
    cache.path_for(CACHE_KEY).write_text(json.dumps(stored), encoding="utf-8")
    payload = OrbitClient(online).samples(later)
    assert payload.from_cache and payload.age >= dt.timedelta(hours=2)


def test_an_error_status_is_not_no_data() -> None:
    body = ["gov.nasa.gsfc.sscweb.schema.Response", {"Result": [
        "gov.nasa.gsfc.sscweb.schema.DataResult",
        {"StatusCode": "ERROR", "StatusSubCode": "INVALID_SATELLITE",
         "StatusText": ["java.util.ArrayList", ["Invalid satellite name 'nosuchsat'"]]},
    ]}]
    with pytest.raises(OrbitDataError, match="INVALID_SATELLITE|Invalid satellite"):
        parse_locations(body)


@respx.mock
def test_a_window_without_ephemeris_is_unavailable_not_empty(online: Settings) -> None:
    body = ["gov.nasa.gsfc.sscweb.schema.Response", {"Result": [
        "gov.nasa.gsfc.sscweb.schema.DataResult",
        {"StatusCode": "SUCCESS", "StatusSubCode": "SUCCESS"},
    ]}]
    assert parse_locations(body) == []
    respx.get(url__regex=URL_PATTERN).mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(OfflineDataUnavailable):
        OrbitClient(online).samples(NOW)


def test_the_next_entry_is_the_first_sample_inside_after_now() -> None:
    samples = parse_locations(recorded())
    outside = next(s for s in samples if not in_saa_region(s.latitude, s.longitude))
    entry = orbit.next_saa_entry(samples, outside.time)
    assert entry is not None and entry > outside.time
    hit = next(s for s in samples if s.time == entry)
    assert in_saa_region(hit.latitude, hit.longitude)
    before = [s for s in samples if outside.time < s.time < entry]
    assert not any(in_saa_region(s.latitude, s.longitude) for s in before)


# --------------------------------------------------------------------------- ruta


@pytest.fixture
def route_client(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    reset_store(new_store())
    yield TestClient(app), tmp_path
    app.dependency_overrides.clear()
    reset_store(None)


def _use(settings: Settings) -> None:
    app.dependency_overrides[get_settings] = lambda: settings


@respx.mock
def test_route_does_not_apply_outside_leo_and_does_not_go_out(
    route_client: tuple[TestClient, Path],
) -> None:
    client, tmp = route_client
    _use(Settings(cache_dir=tmp, offline=False, mission_profile="mars-transit"))
    route = respx.get(url__regex=URL_PATTERN)
    body = client.get("/api/orbit/iss").json()
    assert body["applies"] is False and body["available"] is False
    assert "no aplica" in body["reason"]
    assert not route.called


def test_route_in_leo_offline_without_cache_says_unavailable(
    route_client: tuple[TestClient, Path],
) -> None:
    client, tmp = route_client
    _use(Settings(cache_dir=tmp, offline=True, mission_profile="leo"))
    response = client.get("/api/orbit/iss")
    assert response.status_code == 200
    body = response.json()
    assert body["applies"] is True and body["available"] is False
    assert body["saa_region"]["source"]["status"] == "verified"


def test_route_in_leo_offline_serves_the_cache_with_its_age(
    route_client: tuple[TestClient, Path],
) -> None:
    client, tmp = route_client
    settings = Settings(cache_dir=tmp, offline=True, mission_profile="leo")
    now = dt.datetime.now(dt.UTC).replace(second=0, microsecond=0)
    samples = [
        OrbitSample(now + dt.timedelta(minutes=step), -25.0, -45.0 + step, 6790.0).to_dict()
        for step in range(-5, 60)
    ]
    FileCache(tmp / "sscweb").put(CACHE_KEY, samples, source=orbit.SOURCE)
    _use(settings)
    body = client.get("/api/orbit/iss").json()
    assert body["applies"] and body["available"]
    assert body["in_saa_region"] is True
    assert body["from_cache"] is True and body["age"]
    assert body["scope"].startswith("descriptivo")


@pytest.mark.live
def test_live_sscweb_contract(tmp_path: Path) -> None:
    """Contrato contra SSCweb real: la ISS tiene efemérides para ahora y en órbita baja."""
    settings = Settings(cache_dir=tmp_path, offline=False)
    now = dt.datetime.now(dt.UTC)
    payload = OrbitClient(settings).samples(now)
    view = describe(payload, now)
    assert view["available"] is True
    assert 6500 < view["position"]["radial_km"] < 7000
    assert isinstance(view["in_saa_region"], bool)
