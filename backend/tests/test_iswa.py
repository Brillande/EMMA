"""CCMC iSWA por HAPI (`environment/iswa.py`, `GET /api/space-weather/series`).

Sin red: respx intercepta httpx. Las respuestas de `tests/data/iswa/` son reales (HAPI de iSWA,
SPE del 2024-05-11), grabadas tal cual en el spike; para la ruta se les mueve la hora a ahora,
porque la ruta solo enseña las últimas horas. La prueba `live` comprueba el contrato real.
"""

from __future__ import annotations

import copy
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
from app.environment import iswa
from app.main import app

DATA = Path(__file__).parent / "data" / "iswa"
DATA_URL = f"{iswa.BASE_URL}/data"


def _recorded(dataset_id: str) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(
        (DATA / f"{dataset_id}_2024-05-11.json").read_text(encoding="utf-8")
    )
    return body


def _shifted(dataset_id: str) -> dict[str, Any]:
    """La respuesta grabada, con la última fila hace 10 min (el retraso real de la serie)."""
    body = copy.deepcopy(_recorded(dataset_id))
    rows = body["data"]
    last = iswa._parse_time(rows[-1][0])
    shift = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=10) - last
    for row in rows:
        row[0] = iswa._hapi_time(iswa._parse_time(row[0]) + shift)
    return body


def _by_dataset(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=_shifted(request.url.params["id"]))


@pytest.fixture
def online(tmp_path: Path) -> Settings:
    return Settings(cache_dir=tmp_path, offline=False, assistant_warmup=False)


@pytest.fixture
def api(online: Settings) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: online
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


# --------------------------------------------------------------------------- #
# Lectura de la respuesta HAPI
# --------------------------------------------------------------------------- #


def test_a_real_response_is_read_with_its_units_and_origin() -> None:
    rows = iswa.parse(
        iswa.DATASETS[iswa.Series.PROTONS], _recorded("goesp_part_flux_P5M")
    )
    assert len(rows) == 12
    assert rows[0] == {
        "time": "2024-05-11T08:00:00+00:00", "flux_ge_10mev": 63.51814270019531,
        "origin": "GOES-18",
    }


def test_solar_wind_columns_are_read_by_name_not_by_position() -> None:
    """La ficha pone la densidad antes que la velocidad, sea cual sea el orden pedido."""
    rows = iswa.parse(
        iswa.DATASETS[iswa.Series.SOLAR_WIND], _recorded("swpc_rtsw_plasma_P1M")
    )
    assert rows[0]["speed"] == 707.3
    assert rows[0]["density"] == 16.04
    assert rows[0]["temperature"] == 190913
    assert rows[0]["origin"] == "DSCOVR"


def test_a_fill_value_is_a_gap_not_a_zero() -> None:
    body = _recorded("goesp_part_flux_P5M")
    body["data"][3][1] = -100000
    rows = iswa.parse(iswa.DATASETS[iswa.Series.PROTONS], body)
    assert rows[3]["flux_ge_10mev"] is None
    assert rows[2]["flux_ge_10mev"] is not None


def test_a_missing_parameter_is_a_broken_body_not_a_series_of_gaps() -> None:
    """iSWA ignora en silencio un parámetro desconocido y devuelve solo la hora (spike)."""
    body = _recorded("goesp_part_flux_P5M")
    body["parameters"] = [body["parameters"][0]]
    body["data"] = [[row[0]] for row in body["data"]]
    with pytest.raises(iswa.HapiBodyError, match="P10"):
        iswa.parse(iswa.DATASETS[iswa.Series.PROTONS], body)


def test_a_different_unit_is_not_relabelled_as_pfu() -> None:
    body = _recorded("goesp_part_flux_P5M")
    body["parameters"][1]["units"] = "MeV/cm^2 - s^-1 - sr"
    with pytest.raises(iswa.HapiBodyError, match="no se reetiqueta"):
        iswa.parse(iswa.DATASETS[iswa.Series.PROTONS], body)


def test_a_hapi_error_status_is_a_broken_body() -> None:
    body = {"HAPI": "2.0", "status": {"code": 1406, "message": "unknown dataset id"}, "data": []}
    with pytest.raises(iswa.HapiBodyError, match="1200"):
        iswa.parse(iswa.DATASETS[iswa.Series.PROTONS], body)


# --------------------------------------------------------------------------- #
# Cliente: caché, edad y sin red
# --------------------------------------------------------------------------- #


@respx.mock
def test_a_good_response_is_stored_and_served_live(online: Settings) -> None:
    route = respx.get(DATA_URL).mock(side_effect=_by_dataset)
    payload = iswa.IswaClient(settings=online).series(iswa.Series.PROTONS)
    assert not payload.from_cache
    assert len(payload.data) == 12
    params = route.calls.last.request.url.params
    assert params["id"] == "goesp_part_flux_P5M"
    assert params["parameters"] == "P10,satelliteProton"
    assert params["format"] == "json"


@respx.mock
def test_the_request_carries_nothing_of_ours(online: Settings, tmp_path: Path) -> None:
    """Solo salen el conjunto público, fechas, parámetros y formato, con User-Agent genérico.

    Ni tripulante, ni usuario, ni proyecto, ni rutas locales: la serie es la misma para todos.
    """
    store = new_store()
    reset_store(store)
    try:
        route = respx.get(DATA_URL).mock(side_effect=_by_dataset)
        client = iswa.IswaClient(settings=online)
        for which in iswa.Series:
            client.series(which)
    finally:
        reset_store(None)
    assert route.call_count == 2
    for call in route.calls:
        request = call.request
        assert set(request.url.params.keys()) == {
            "id", "time.min", "time.max", "parameters", "format"
        }
        assert request.url.params["id"] in {d.dataset_id for d in iswa.DATASETS.values()}
        for key in ("time.min", "time.max"):
            iswa._parse_time(request.url.params[key])  # una fecha y nada más
        text = str(request.url) + " " + " ".join(f"{k}: {v}" for k, v in request.headers.items())
        lowered = text.lower()
        for forbidden in ("emma", "crew", "tripul", "astronaut", "patient", "ellande",
                          str(tmp_path).lower(), str(Path.home()).lower(), "c:\\", "/users/"):
            assert forbidden not in lowered, forbidden
        assert request.content == b""
        assert "cookie" not in request.headers and "authorization" not in request.headers
        assert request.headers["user-agent"].startswith("python-httpx/")


@respx.mock
def test_a_recent_query_is_reused_without_going_out(online: Settings) -> None:
    route = respx.get(DATA_URL).mock(side_effect=_by_dataset)
    client = iswa.IswaClient(settings=online)
    client.series(iswa.Series.PROTONS)
    again = client.series(iswa.Series.PROTONS)
    assert again.from_cache
    assert route.call_count == 1


@respx.mock
def test_a_stale_query_goes_out_again(online: Settings, tmp_path: Path) -> None:
    route = respx.get(DATA_URL).mock(side_effect=_by_dataset)
    client = iswa.IswaClient(settings=online)
    client.series(iswa.Series.PROTONS)
    _age_cache(tmp_path, iswa.FRESH_FOR + dt.timedelta(minutes=1))
    assert not client.series(iswa.Series.PROTONS).from_cache
    assert route.call_count == 2


def _age_cache(tmp_path: Path, by: dt.timedelta) -> None:
    for path in (tmp_path / "iswa").glob("*.json"):
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["fetched_at"] = (dt.datetime.fromisoformat(raw["fetched_at"]) - by).isoformat()
        path.write_text(json.dumps(raw), encoding="utf-8")


@respx.mock
def test_offline_serves_the_stored_series_with_its_age(tmp_path: Path) -> None:
    respx.get(DATA_URL).mock(side_effect=_by_dataset)
    iswa.IswaClient(settings=Settings(cache_dir=tmp_path)).series(iswa.Series.PROTONS)
    _age_cache(tmp_path, dt.timedelta(hours=3))
    route = respx.get(DATA_URL)
    payload = iswa.IswaClient(settings=Settings(cache_dir=tmp_path, offline=True)).series(
        iswa.Series.PROTONS
    )
    assert payload.from_cache
    assert payload.describe_age() == "hace 3 h"
    assert route.call_count == 1  # solo la primera, con red


def test_offline_without_cache_is_unavailable_not_invented(tmp_path: Path) -> None:
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(DATA_URL)
        with pytest.raises(OfflineDataUnavailable, match="modo sin red"):
            iswa.IswaClient(settings=Settings(cache_dir=tmp_path, offline=True)).series(
                iswa.Series.PROTONS
            )
        assert route.call_count == 0


@respx.mock
def test_a_broken_body_without_cache_is_unavailable(online: Settings) -> None:
    respx.get(DATA_URL).mock(return_value=httpx.Response(200, text="<html>error</html>"))
    with pytest.raises(OfflineDataUnavailable, match="sin JSON"):
        iswa.IswaClient(settings=online).series(iswa.Series.PROTONS)


@respx.mock
def test_an_http_error_falls_back_to_the_stored_series(
    online: Settings, tmp_path: Path
) -> None:
    respx.get(DATA_URL).mock(side_effect=_by_dataset)
    client = iswa.IswaClient(settings=online)
    client.series(iswa.Series.PROTONS)
    _age_cache(tmp_path, dt.timedelta(hours=1))
    respx.get(DATA_URL).mock(return_value=httpx.Response(404, json={"status": {"code": 1406}}))
    payload = client.series(iswa.Series.PROTONS)
    assert payload.from_cache
    assert payload.describe_age() == "hace 1 h"


@respx.mock
def test_an_http_error_without_cache_is_unavailable(online: Settings) -> None:
    respx.get(DATA_URL).mock(return_value=httpx.Response(404, json={"status": {"code": 1406}}))
    with pytest.raises(OfflineDataUnavailable, match="iSWA inaccesible"):
        iswa.IswaClient(settings=online).series(iswa.Series.PROTONS)


def test_a_corrupt_cache_entry_is_not_served(tmp_path: Path) -> None:
    cache = FileCache(tmp_path / "iswa")
    dataset = iswa.DATASETS[iswa.Series.PROTONS]
    cache.put(iswa.IswaClient._key(dataset), {"no": "es una serie"}, source="x")
    with pytest.raises(OfflineDataUnavailable):
        iswa.IswaClient(settings=Settings(cache_dir=tmp_path, offline=True)).series(
            iswa.Series.PROTONS
        )


# --------------------------------------------------------------------------- #
# Ruta
# --------------------------------------------------------------------------- #


@respx.mock
def test_route_serves_both_series_with_units_age_and_source(api: TestClient) -> None:
    respx.get(DATA_URL).mock(side_effect=_by_dataset)
    body = api.get("/api/space-weather/series", params={"hours": 2}).json()
    protons = body["series"]["protons"]
    assert protons["available"] and protons["live"]
    assert protons["channels"][0]["unit"] == "pfu"
    assert protons["channels"][0]["hapi_units"] == iswa.PFU_UNITS
    assert protons["latest"]["flux_ge_10mev"] == pytest.approx(81.27578735351562)
    assert protons["latest"]["origin"] == "GOES-18"
    # La última muestra llega con retraso: su edad se dice aparte de la de la consulta.
    assert 9 * 60 <= protons["last_sample_age_seconds"] <= 11 * 60
    assert protons["data_age_seconds"] < 60
    assert "iSWA" in protons["source"] and "NOAA SWPC" in protons["source"]
    assert protons["reference"]["value"] == 10.0
    assert protons["reference"]["evaluated"] is False
    wind = body["series"]["solar-wind"]
    assert wind["available"]
    assert {channel["unit"] for channel in wind["channels"]} == {"km/s", "p/cm³", "K"}
    assert "no se evalúa" in body["scope"]


@respx.mock
def test_route_cuts_the_window_to_the_hours_asked(api: TestClient) -> None:
    """La última fila está hace 10 min y las demás, cada 5 min antes: en 1 h caben 10.

    La de hace 60 min justos queda fuera: el corte se calcula después de mover las horas.
    """
    respx.get(DATA_URL).mock(side_effect=_by_dataset)
    body = api.get("/api/space-weather/series", params={"hours": 1}).json()
    assert len(body["series"]["protons"]["samples"]) == 10  # 08:10..08:55


def test_route_offline_without_cache_says_unavailable_and_does_not_fail(
    tmp_path: Path,
) -> None:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, assistant_warmup=False
    )
    try:
        response = TestClient(app).get("/api/space-weather/series")
    finally:
        app.dependency_overrides.clear()
        reset_store(None)
    assert response.status_code == 200
    for block in response.json()["series"].values():
        assert block["available"] is False
        assert "modo sin red" in block["reason"]


@respx.mock
def test_route_offline_with_cache_says_it_is_not_live(tmp_path: Path) -> None:
    respx.get(DATA_URL).mock(side_effect=_by_dataset)
    iswa.IswaClient(settings=Settings(cache_dir=tmp_path)).series(iswa.Series.PROTONS)
    _age_cache(tmp_path, dt.timedelta(hours=2))
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, assistant_warmup=False
    )
    try:
        body = TestClient(app).get("/api/space-weather/series").json()
    finally:
        app.dependency_overrides.clear()
        reset_store(None)
    protons = body["series"]["protons"]
    assert protons["available"] and protons["from_cache"]
    assert protons["live"] is False
    assert protons["data_age"] == "hace 2 h"
    assert body["series"]["solar-wind"]["available"] is False


@respx.mock
def test_route_one_series_failing_does_not_hide_the_other(api: TestClient) -> None:
    def only_protons(request: httpx.Request) -> httpx.Response:
        if request.url.params["id"] == "goesp_part_flux_P5M":
            return _by_dataset(request)
        return httpx.Response(500)

    respx.get(DATA_URL).mock(side_effect=only_protons)
    body = api.get("/api/space-weather/series").json()
    assert body["series"]["protons"]["available"] is True
    assert body["series"]["solar-wind"]["available"] is False


def test_route_rejects_a_window_beyond_the_stored_one(client: TestClient) -> None:
    assert client.get("/api/space-weather/series", params={"hours": 73}).status_code == 422


# --------------------------------------------------------------------------- #
# Contrato real (excluida por defecto)
# --------------------------------------------------------------------------- #


@pytest.mark.live
def test_live_iswa_contract(tmp_path: Path) -> None:
    """iSWA sigue sirviendo P10 en pfu y el viento solar, con muestras de las últimas horas."""
    client = iswa.IswaClient(settings=Settings(cache_dir=tmp_path))
    protons = client.series(iswa.Series.PROTONS)
    values = [row["flux_ge_10mev"] for row in protons.data if row["flux_ge_10mev"] is not None]
    assert values, "iSWA devolvió una serie de protones vacía"
    assert all(value >= 0 for value in values)
    newest = iswa._parse_time(protons.data[-1]["time"])
    assert dt.datetime.now(dt.UTC) - newest < dt.timedelta(hours=6)
    wind = client.series(iswa.Series.SOLAR_WIND)
    assert any(row["speed"] is not None for row in wind.data)
