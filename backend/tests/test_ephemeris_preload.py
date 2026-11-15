"""Precarga de las efemérides de toda la misión (decimosexta ronda, E6).

Lo que no se puede romper:

1. **La lectura diaria aprovecha la precarga sin cambios**: misma clave, mismo formato, misma
   verificación cruzada y mismo filtro de la elongación. Sin red, un día precargado se sirve
   igual que uno pedido el día que hizo falta.
2. **Una consulta por tramo seguido que falte**, solo de lo que falta, y lo que ya estaba no se
   reescribe.
3. **Por la puerta de salida**: sin red, en modo seguro o con una red caída, no sale nada, se
   dice, y la caché queda como estaba. Una tabla incoherente tampoco escribe nada.
4. **La cobertura dice qué días de la misión hay y cuáles no**, solo mirando el disco.

Sin red (invariante 3): astroquery habla por `requests`, no por httpx, y `respx` no vería su
petición; se intercepta su `_request` con una respuesta de Horizons en el CSV que pide astroquery
(`tests/data/horizons/mars_2026-11-01_05.txt`, cifras de la API leídas el 2026-10-23), como en
`test_conjunction.py`.
"""

from __future__ import annotations

import ast
import datetime as dt
import importlib.util
import json
import os
import shutil
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import requests
from astropy.table import MaskedColumn, Table
from astroquery.jplhorizons import HorizonsClass
from astroquery.utils.mocks import MockResponse
from fastapi.testclient import TestClient

from app.api.routes import new_store, reset_store
from app.core import cache as cache_module
from app.core import egress
from app.core.cache import FileCache, OfflineDataUnavailable
from app.core.config import Settings, get_settings
from app.environment import ephemeris as ephemeris_module
from app.environment import ephemeris_coverage
from app.environment.ephemeris import (
    PRELOAD_BRIDGE_DAYS,
    CommsWindow,
    EphemerisCacheWriteError,
    EphemerisClient,
    HorizonsResponseError,
    cache_key,
    day_runs,
)
from app.main import app
from app.text_guard import check as check_text

DATA = Path(__file__).parent / "data" / "horizons"
FIXTURE = DATA / "mars_2026-11-01_05.txt"
BACKEND = Path(__file__).resolve().parents[1]
START = dt.date(2026, 11, 1)
DAYS = [START + dt.timedelta(days=n) for n in range(5)]
# Lo que dio la API de Horizons el 2026-10-23 para el 1 y el 5 de noviembre de 2026.
FIRST = {"delta": 1.43251012108556, "lt": 11.91382339, "elong": 79.9592}
LAST = {"delta": 1.39978223224787, "lt": 11.64163384, "elong": 81.9755}


def _settings(tmp_path: Path, *, offline: bool = False, days: int = 4) -> Settings:
    return Settings(cache_dir=tmp_path, offline=offline, mission_start=START, mission_days=days)


class Horizons:
    """Lo que astroquery pidió y lo que se le contesta, sin salir a la red."""

    def __init__(self) -> None:
        self.asked: list[dict[str, Any]] = []
        self.body = FIXTURE.read_bytes()
        self.error: BaseException | None = None

    def request(self, _self: object, method: str, url: str, **kwargs: Any) -> MockResponse:
        self.asked.append(dict(kwargs.get("params") or {}))
        if self.error is not None:
            raise self.error
        return MockResponse(content=self.body, url=url)


@pytest.fixture
def horizons(monkeypatch: pytest.MonkeyPatch) -> Horizons:
    fake = Horizons()
    monkeypatch.setattr(
        HorizonsClass, "_request",
        lambda self, method, url, **kwargs: fake.request(self, method, url, **kwargs),
    )
    return fake


def _client(settings: Settings) -> EphemerisClient:
    return EphemerisClient(settings=settings)


def _files(settings: Settings) -> dict[str, bytes]:
    root = Path(settings.cache_dir) / "ephemeris"
    return {path.name: path.read_bytes() for path in root.glob("*.json")}


# --- 1. La lectura diaria aprovecha la precarga ------------------------------------------------


def test_each_day_is_written_where_and_how_the_daily_read_looks_for_it(
    tmp_path: Path, horizons: Horizons
) -> None:
    online = _settings(tmp_path)
    result = _client(online).preload(DAYS[0], DAYS[-1], "499")
    assert result.written == tuple(DAYS)
    assert result.rows_received == 5 and result.already_cached == 0

    # Sin red, la consulta diaria de siempre sirve cada día de la caché.
    offline = _client(_settings(tmp_path, offline=True))
    first = offline.comms_window(DAYS[0], "499")
    last = offline.comms_window(DAYS[-1], "499")
    assert first.from_cache and last.from_cache
    assert first.source == "JPL Horizons"
    assert first.data.distance_au == FIRST["delta"]
    assert first.data.one_way_minutes == pytest.approx(FIRST["lt"])
    assert first.data.solar_elongation_deg == pytest.approx(FIRST["elong"])
    assert first.data.solar_elongation_flag == "/L"
    assert last.data.distance_au == LAST["delta"]
    assert last.data.one_way_minutes == pytest.approx(LAST["lt"])
    assert last.data.solar_elongation_deg == pytest.approx(LAST["elong"])
    assert {window.data.epoch for window in (first, last)} == {DAYS[0], DAYS[-1]}


def test_a_preloaded_day_is_the_same_window_the_daily_query_would_have_saved(
    tmp_path: Path, horizons: Horizons
) -> None:
    daily = _client(_settings(tmp_path / "daily")).comms_window(DAYS[0], "499")
    _client(_settings(tmp_path / "preload")).preload(DAYS[0], DAYS[-1], "499")
    preloaded = _client(_settings(tmp_path / "preload", offline=True)).comms_window(DAYS[0], "499")
    assert preloaded.data == daily.data
    # El mismo fichero, con el mismo contenido salvo la hora de obtención.
    [daily_file] = (tmp_path / "daily" / "ephemeris").glob("*.json")
    preload_file = tmp_path / "preload" / "ephemeris" / daily_file.name
    stored = [json.loads(path.read_text(encoding="utf-8")) for path in (daily_file, preload_file)]
    for entry in stored:
        entry.pop("fetched_at")
    assert stored[0] == stored[1]
    assert stored[0]["key"] == cache_key("499", "500@399", DAYS[0])


# --- 2. Una consulta, solo de lo que falta -------------------------------------------------------


def test_the_whole_range_goes_in_one_query_with_a_one_day_step(
    tmp_path: Path, horizons: Horizons
) -> None:
    _client(_settings(tmp_path)).preload(DAYS[0], DAYS[-1], "499")
    assert len(horizons.asked) == 1
    [params] = horizons.asked
    assert params["START_TIME"] == '"2026-11-01"'
    assert params["STOP_TIME"] == '"2026-11-05"'
    assert params["STEP_SIZE"] == '"1d"'
    assert params["COMMAND"] == '"499"' and params["CENTER"] == "'500@399'"


def test_only_the_missing_days_are_asked_and_the_cached_ones_are_not_rewritten(
    tmp_path: Path, horizons: Horizons
) -> None:
    settings = _settings(tmp_path)
    cache = FileCache(tmp_path / "ephemeris")
    kept = CommsWindow(DAYS[0], 1.0, 8.32, "499")
    cache.put(cache_key("499", "500@399", DAYS[0]), kept.to_dict(), source="JPL Horizons")
    cache.put(cache_key("499", "500@399", DAYS[1]), kept.to_dict(), source="JPL Horizons")
    before = _files(settings)

    result = _client(settings).preload(DAYS[0], DAYS[-1], "499")
    assert horizons.asked[0]["START_TIME"] == '"2026-11-03"'
    assert result.requested == (DAYS[2], DAYS[-1])
    assert result.already_cached == 2 and result.written == tuple(DAYS[2:])
    after = _files(settings)
    assert {name: after[name] for name in before} == before


def test_with_everything_cached_nothing_goes_out_even_offline(
    tmp_path: Path, horizons: Horizons
) -> None:
    _client(_settings(tmp_path)).preload(DAYS[0], DAYS[-1], "499")
    horizons.asked.clear()
    result = _client(_settings(tmp_path, offline=True)).preload(DAYS[0], DAYS[-1], "499")
    assert result.requested is None and result.written == () and result.already_cached == 5
    assert horizons.asked == []


def test_a_single_day_range_still_asks_horizons_for_a_window(
    tmp_path: Path, horizons: Horizons
) -> None:
    """Horizons no da tabla con inicio igual a fin (`spikes/HALLAZGOS.md`)."""
    result = _client(_settings(tmp_path)).preload(DAYS[0], DAYS[0], "499")
    assert horizons.asked[0]["STOP_TIME"] == '"2026-11-02"'
    assert result.requested == (DAYS[0], DAYS[1])  # lo que se pidió, tal cual
    assert result.written == (DAYS[0],)  # la fila del día siguiente no se guarda
    assert result.not_received == ()


def test_an_empty_range_is_an_error(tmp_path: Path, horizons: Horizons) -> None:
    with pytest.raises(ValueError, match="rango vacío"):
        _client(_settings(tmp_path)).preload(DAYS[1], DAYS[0], "499")
    assert horizons.asked == []


# --- 3. La puerta de salida, y nada a medias ----------------------------------------------------


def test_offline_it_refuses_says_so_and_asks_nothing(tmp_path: Path, horizons: Horizons) -> None:
    settings = _settings(tmp_path, offline=True)
    with pytest.raises(OfflineDataUnavailable, match="modo sin red"):
        _client(settings).preload(DAYS[0], DAYS[-1], "499")
    assert horizons.asked == []
    assert _files(settings) == {}


def test_safe_mode_cuts_the_preload(
    tmp_path: Path, horizons: Horizons, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(egress, "_safe_mode", lambda: "sospecha de fuga por la red")
    with pytest.raises(OfflineDataUnavailable, match="modo seguro"):
        _client(_settings(tmp_path)).preload(DAYS[0], DAYS[-1], "499")
    assert horizons.asked == []


def test_a_network_failure_is_offline_and_writes_nothing(
    tmp_path: Path, horizons: Horizons
) -> None:
    horizons.error = requests.ConnectionError("red caída")
    settings = _settings(tmp_path)
    with pytest.raises(OfflineDataUnavailable, match="inaccesible"):
        _client(settings).preload(DAYS[0], DAYS[-1], "499")
    assert _files(settings) == {}


def test_a_light_time_mismatch_in_any_row_writes_nothing(
    tmp_path: Path, horizons: Horizons
) -> None:
    horizons.body = horizons.body.replace(b"11.77829269", b"12.77829269")
    settings = _settings(tmp_path)
    with pytest.raises(ValueError, match="discrepancia en tiempo de luz para 2026-11-03"):
        _client(settings).preload(DAYS[0], DAYS[-1], "499")
    assert _files(settings) == {}


def test_a_row_off_midnight_is_not_saved_under_a_day(
    tmp_path: Path, horizons: Horizons
) -> None:
    """Ni bajo su día ni bajo otro; y desde la decimoséptima ronda no tumba las demás filas."""
    horizons.body = horizons.body.replace(b"2461347.500000000", b"2461347.750000000")
    settings = _settings(tmp_path)
    result = _client(settings).preload(DAYS[0], DAYS[-1], "499")
    assert result.written == (DAYS[0], DAYS[1], DAYS[3], DAYS[4])
    assert result.not_received == (DAYS[2],)
    assert result.rows_unusable == 1 and result.to_dict()["rows_unusable"] == 1
    assert not _client(settings).is_cached(DAYS[2], "499")
    assert len(_files(settings)) == 4


def test_a_table_without_distance_is_a_bad_answer_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = Table({"datetime_jd": [2461345.5], "lighttime": [11.91382339]})

    class Query:
        def ephemerides(self) -> Table:
            return table

    monkeypatch.setattr(EphemerisClient, "_range_query", lambda self, a, b, t: Query())
    settings = _settings(tmp_path)
    with pytest.raises(HorizonsResponseError, match="no trae la distancia"):
        _client(settings).preload(DAYS[0], DAYS[-1], "499")
    assert _files(settings) == {}
    # La consulta diaria igual: una respuesta inservible (502), no un error del servidor.
    with pytest.raises(HorizonsResponseError, match="no trae la distancia"):
        _client(settings).comms_window(DAYS[0], "499")


@pytest.mark.parametrize(
    ("column", "values"),
    [
        ("delta", MaskedColumn([FIRST["delta"]], mask=[True])),  # un hueco de Horizons
        ("lighttime", MaskedColumn([FIRST["lt"]], mask=[True])),
        ("delta", [float("nan")]),
        ("lighttime", [float("inf")]),
    ],
)
def test_a_gap_in_distance_or_light_time_is_a_bad_answer_not_a_nan_delay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, column: str, values: Any
) -> None:
    """Un hueco convertido da NaN, y NaN pasa la verificación cruzada: no se guarda nada.

    Antes se habría escrito `{distance_au: NaN}` y, sin red, la consola habría dicho «Consulta
    con Tierra disponible (~nan min)» mientras la cobertura daba el día por ausente.
    """
    table = Table(
        {"datetime_jd": [2461345.5], "delta": [FIRST["delta"]], "lighttime": [FIRST["lt"]]}
    )
    table[column] = values

    class Query:
        def ephemerides(self) -> Table:
            return table

    monkeypatch.setattr(EphemerisClient, "_range_query", lambda self, a, b, t: Query())
    settings = _settings(tmp_path)
    with pytest.raises(HorizonsResponseError, match=f"trae {column} sin valor utilizable"):
        _client(settings).preload(DAYS[0], DAYS[0], "499")
    with pytest.raises(HorizonsResponseError, match=f"trae {column} sin valor utilizable"):
        _client(settings).comms_window(DAYS[0], "499")
    assert _files(settings) == {}


def test_a_cached_delay_that_is_not_a_number_is_not_served(tmp_path: Path) -> None:
    """Lo que la cobertura no da por cubierto, el retardo tampoco lo lee: la misma regla."""
    cache = FileCache(tmp_path / "ephemeris")
    window = CommsWindow(DAYS[0], 1.4, 11.6, "499").to_dict()
    cache.put(
        cache_key("499", "500@399", DAYS[0]),
        {**window, "one_way_minutes": float("nan")}, source="a mano",
    )
    settings = _settings(tmp_path, offline=True, days=0)
    client = _client(settings)
    assert client.is_cached(DAYS[0], "499") is False
    with pytest.raises(OfflineDataUnavailable, match="no cacheadas"):
        client.comms_window(DAYS[0], "499")
    # Una entrada buena se sigue sirviendo igual.
    cache.put(cache_key("499", "500@399", DAYS[0]), window, source="JPL Horizons")
    assert client.comms_window(DAYS[0], "499").data.one_way_minutes == 11.6


def test_cached_days_in_the_middle_are_neither_checked_nor_rewritten(
    tmp_path: Path, horizons: Horizons
) -> None:
    """Faltan el 1 y el 5, con tres días en caché en medio: cerca (`PRELOAD_BRIDGE_DAYS`), van
    en una consulta, y una fila rara de un día ya guardado no estorba a los que faltaban."""
    settings = _settings(tmp_path)
    cache = FileCache(tmp_path / "ephemeris")
    for epoch in DAYS[1:4]:
        cache.put(
            cache_key("499", "500@399", epoch),
            CommsWindow(epoch, 1.4, 11.6, "499").to_dict(), source="JPL Horizons",
        )
    before = _files(settings)
    horizons.body = horizons.body.replace(b"11.77829269", b"12.77829269")  # fila del día 3
    result = _client(settings).preload(DAYS[0], DAYS[-1], "499")
    assert result.queries == ((DAYS[0], DAYS[-1]),) and len(horizons.asked) == 1
    assert result.requested == (DAYS[0], DAYS[-1])
    assert result.written == (DAYS[0], DAYS[-1])
    after = _files(settings)
    assert {name: after[name] for name in before} == before


def test_days_horizons_did_not_give_stay_missing(tmp_path: Path, horizons: Horizons) -> None:
    """Pedido hasta el 7 y llegan filas hasta el 5: el 6 y el 7 siguen sin efeméride."""
    settings = _settings(tmp_path, days=6)
    start, end = ephemeris_coverage.mission_span(settings)
    result = _client(settings).preload(start, end, "499")
    assert result.requested == (DAYS[0], dt.date(2026, 11, 7))
    assert result.written == tuple(DAYS)
    assert result.not_received == (dt.date(2026, 11, 6), dt.date(2026, 11, 7))
    assert result.to_dict()["not_received"] == ["2026-11-06", "2026-11-07"]
    said = ephemeris_coverage.coverage(settings, day=START, target="499")
    assert said["state"] == ephemeris_coverage.PARTIAL
    assert said["missing"] == [{"start": "2026-11-06", "end": "2026-11-07", "days": 2}]


# --- 4. La cobertura -----------------------------------------------------------------------


def test_the_mission_span_runs_from_launch_to_the_configured_end_both_included() -> None:
    settings = Settings(mission_start=START, mission_days=180)
    assert ephemeris_coverage.mission_span(settings) == (START, dt.date(2027, 4, 30))


def _day(date: str, in_mission: bool, covered: bool) -> dict[str, Any]:
    """El día del estado en la cobertura, sin SPICE (la suite no lo tiene): sin red, sale de la
    caché de Horizons o sin dato (`offline_covered`, `served_by`, 2026-11-11)."""
    served = ephemeris_coverage.HORIZONS_SERVED if covered else None
    return {
        "date": date, "in_mission": in_mission, "covered": covered, "offline_covered": covered,
        "served_by": served, "served_text": ephemeris_coverage.SERVED_TEXT[served],
    }


def test_coverage_says_which_days_are_there_and_which_are_not(tmp_path: Path) -> None:
    settings = _settings(tmp_path, days=9)  # del 1 al 10 de noviembre
    cache = FileCache(tmp_path / "ephemeris")
    for day in (2, 3, 4, 8):
        epoch = dt.date(2026, 11, day)
        cache.put(
            cache_key("499", "500@399", epoch),
            CommsWindow(epoch, 1.4, 11.6, "499").to_dict(), source="JPL Horizons",
        )
    said = ephemeris_coverage.coverage(settings, day=dt.date(2026, 11, 3), target="499")
    assert said["state"] == ephemeris_coverage.PARTIAL
    assert (said["days"], said["covered_days"], said["missing_days"]) == (10, 4, 6)
    assert said["covered"] == [
        {"start": "2026-11-02", "end": "2026-11-04", "days": 3},
        {"start": "2026-11-08", "end": "2026-11-08", "days": 1},
    ]
    assert said["missing"] == [
        {"start": "2026-11-01", "end": "2026-11-01", "days": 1},
        {"start": "2026-11-05", "end": "2026-11-07", "days": 3},
        {"start": "2026-11-09", "end": "2026-11-10", "days": 2},
    ]
    assert said["day"] == _day("2026-11-03", True, True)
    assert said["text"].startswith("4 de los 10 días de la misión")
    assert "faltan 6 días en 3 tramos" in said["text"]
    assert said["how_to_preload"] == ephemeris_coverage.HOW_TO_PRELOAD
    # Un día de la misión sin efeméride, y uno de fuera de la misión que sí la tiene.
    gap = ephemeris_coverage.coverage(settings, day=dt.date(2026, 11, 5), target="499")["day"]
    assert gap == _day("2026-11-05", True, False)
    before = dt.date(2026, 10, 31)
    cache.put(
        cache_key("499", "500@399", before),
        CommsWindow(before, 1.4, 11.6, "499").to_dict(), source="JPL Horizons",
    )
    outside = ephemeris_coverage.coverage(settings, day=before, target="499")
    assert outside["day"] == _day("2026-10-31", False, True)
    assert outside["covered_days"] == 4  # el día de antes del lanzamiento no cuenta


def test_coverage_with_nothing_and_with_everything(tmp_path: Path, horizons: Horizons) -> None:
    settings = _settings(tmp_path)
    empty = ephemeris_coverage.coverage(settings, day=dt.date(2026, 10, 23), target="499")
    assert empty["state"] == ephemeris_coverage.NONE
    assert empty["text"].startswith("Ningún día de la misión (del 2026-11-01 al 2026-11-05")
    assert empty["day"] == _day("2026-10-23", False, False)
    _client(settings).preload(DAYS[0], DAYS[-1], "499")
    full = ephemeris_coverage.coverage(settings, day=dt.date(2026, 10, 23), target="499")
    assert full["state"] == ephemeris_coverage.COMPLETE
    assert full["missing"] == [] and full["how_to_preload"] is None
    assert full["text"].startswith("Los 5 días de la misión")


def test_an_entry_that_does_not_load_is_not_covered(tmp_path: Path) -> None:
    settings = _settings(tmp_path, days=1)
    cache = FileCache(tmp_path / "ephemeris")
    cache.put(cache_key("499", "500@399", DAYS[0]), {"epoch": "2026-11-01"}, source="a mano")
    root = tmp_path / "ephemeris"
    (root / Path(cache._path(cache_key("499", "500@399", DAYS[1]))).name).write_text(
        "{roto", encoding="utf-8"
    )
    said = ephemeris_coverage.coverage(settings, day=START, target="499")
    assert said["covered_days"] == 0
    assert said["state"] == ephemeris_coverage.NONE


def test_valid_json_without_the_cache_shape_is_not_covered_nor_a_500(tmp_path: Path) -> None:
    """JSON válido que no es una entrada de caché, o un retardo que no es un número: no cuenta.

    `FileCache.get` solo perdona el JSON roto; sin `fetched_at`, o con una lista, lanza. La
    cobertura corre en cada `/api/status`: tiene que decir «no cubierto», no tumbar el estado.
    """
    settings = _settings(tmp_path, days=3)
    cache = FileCache(tmp_path / "ephemeris")
    window = CommsWindow(DAYS[0], 1.4, 11.6, "499").to_dict()
    cache.path_for(cache_key("499", "500@399", DAYS[0])).write_text(
        json.dumps({"data": window, "source": "a mano"}), encoding="utf-8"
    )
    cache.path_for(cache_key("499", "500@399", DAYS[1])).write_text("[1, 2]", encoding="utf-8")
    cache.put(
        cache_key("499", "500@399", DAYS[2]),
        {**window, "epoch": DAYS[2].isoformat(), "one_way_minutes": "x"},
        source="a mano",
    )
    cache.put(
        cache_key("499", "500@399", DAYS[3]),
        {**window, "epoch": DAYS[3].isoformat(), "distance_au": None},
        source="a mano",
    )
    said = ephemeris_coverage.coverage(settings, day=START, target="499")
    assert said["covered_days"] == 0
    assert said["state"] == ephemeris_coverage.NONE


def test_a_rewritten_entry_is_read_again(tmp_path: Path) -> None:
    """Lo leído se recuerda por fichero, fecha y tamaño: si el fichero cambia, se vuelve a leer."""
    settings = _settings(tmp_path, days=0)
    cache = FileCache(tmp_path / "ephemeris")
    key = cache_key("499", "500@399", DAYS[0])
    cache.put(key, {"epoch": "2026-11-01"}, source="a mano")
    client = _client(settings)
    assert client.is_cached(DAYS[0], "499") is False
    assert client.is_cached(DAYS[0], "499") is False  # la segunda vez, de memoria
    cache.put(key, CommsWindow(DAYS[0], 1.4, 11.6, "499").to_dict(), source="JPL Horizons")
    assert client.is_cached(DAYS[0], "499") is True
    cache.path_for(key).unlink()
    assert client.is_cached(DAYS[0], "499") is False


def test_the_texts_pass_the_language_filter(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    for text in (
        ephemeris_coverage.coverage(settings, target="499")["text"],
        ephemeris_coverage.coverage(settings, target="499")["note"],
        ephemeris_coverage.HOW_TO_PRELOAD,
    ):
        assert check_text(text) == [], text


def test_nothing_that_decides_reads_the_coverage() -> None:
    for folder in ("analysis", "advisor"):
        for path in (BACKEND / "app" / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names = {
                alias.name for node in ast.walk(tree)
                if isinstance(node, ast.Import | ast.ImportFrom)
                for alias in node.names
            } | {
                node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
            }
            assert not any("ephemeris_coverage" in name for name in names), path


# --- 5. La API ------------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path: Path) -> Iterator[dict[str, Any]]:
    """Un cliente con la configuración que cada prueba elige (sin red real en ningún caso)."""
    holder: dict[str, Any] = {"settings": _settings(tmp_path, offline=True)}
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: holder["settings"]
    holder["client"] = TestClient(app)
    yield holder
    app.dependency_overrides.clear()
    reset_store(None)


def test_the_route_refuses_offline_with_its_reason(api: dict[str, Any], horizons: Horizons) -> None:
    response = api["client"].post("/api/comms/preload")
    assert response.status_code == 503
    assert "modo sin red" in response.json()["detail"]
    assert horizons.asked == []


def test_a_mission_without_days_is_a_configuration_error_not_horizons_fault(
    api: dict[str, Any], horizons: Horizons, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`EMMA_MISSION_DAYS` negativo (la configuración no lo impide): ni 502 ni «completa»."""
    api["settings"] = settings = _settings(tmp_path, days=-1)
    response = api["client"].post("/api/comms/preload")
    assert response.status_code == 500
    assert "EMMA_MISSION_DAYS=-1" in response.json()["detail"]
    assert _script(monkeypatch, settings).main([]) == 5
    assert "EMMA_MISSION_DAYS=-1" in capsys.readouterr().err
    assert horizons.asked == []
    said = ephemeris_coverage.coverage(settings, day=START, target="499")
    assert (said["state"], said["days"]) == (ephemeris_coverage.NONE, 0)
    assert "no tiene ningún día" in said["text"]


def test_the_route_preloads_and_the_status_says_the_mission_is_covered(
    api: dict[str, Any], horizons: Horizons, tmp_path: Path
) -> None:
    client: TestClient = api["client"]
    api["settings"] = _settings(tmp_path)
    response = client.post("/api/comms/preload")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requested"] == {"start": "2026-11-01", "stop": "2026-11-05"}
    assert body["written"] == 5 and body["rows_received"] == 5
    assert body["coverage"]["state"] == ephemeris_coverage.COMPLETE

    # Sin red, el estado lo dice desde la caché.
    api["settings"] = _settings(tmp_path, offline=True)
    client.post("/api/simulate", params={"scenario": "nominal", "days": 10})
    coverage = client.get("/api/status").json()["mission"]["ephemeris_coverage"]
    assert coverage["state"] == ephemeris_coverage.COMPLETE
    assert (coverage["days"], coverage["covered_days"]) == (5, 5)
    assert coverage["citations"][0]["ref"] == "jpl-horizons-api"


def test_the_route_respects_the_signed_safe_mode(
    api: dict[str, Any], horizons: Horizons, tmp_path: Path
) -> None:
    client: TestClient = api["client"]
    activate = {"active": True, "reason": "sospecha de fuga por la red", "declared_by": "CMO"}
    assert client.post("/api/safe-mode", json=activate).status_code == 201
    api["settings"] = _settings(tmp_path)
    response = client.post("/api/comms/preload")
    assert response.status_code == 503
    assert "modo seguro" in response.json()["detail"]
    assert horizons.asked == []


def test_the_status_says_no_day_is_covered_without_a_preload(api: dict[str, Any]) -> None:
    client: TestClient = api["client"]
    client.post("/api/simulate", params={"scenario": "nominal", "days": 10})
    coverage = client.get("/api/status").json()["mission"]["ephemeris_coverage"]
    assert coverage["state"] == ephemeris_coverage.NONE
    assert coverage["missing"] == [{"start": "2026-11-01", "end": "2026-11-05", "days": 5}]
    assert coverage["how_to_preload"] == ephemeris_coverage.HOW_TO_PRELOAD


def test_the_status_speaks_of_the_day_it_shows(
    api: dict[str, Any], horizons: Horizons, tmp_path: Path
) -> None:
    """Con `epoch`, el estado enseña la efeméride de ese día, y la cobertura habla de ese día."""
    client: TestClient = api["client"]
    api["settings"] = _settings(tmp_path)
    assert client.post("/api/comms/preload").status_code == 200
    api["settings"] = _settings(tmp_path, offline=True)
    client.post("/api/simulate", params={"scenario": "nominal", "days": 10})
    shown = client.get("/api/status", params={"epoch": "2026-11-03"}).json()
    assert shown["mission"]["ephemeris_coverage"]["day"] == _day("2026-11-03", True, True)
    assert shown["comms"]["epoch"] == "2026-11-03"
    later = client.get("/api/status", params={"epoch": "2026-11-09"}).json()
    assert later["mission"]["ephemeris_coverage"]["day"]["covered"] is False
    assert later["comms"] is None


@pytest.mark.live
def test_live_a_preloaded_range_is_what_the_daily_query_gives(tmp_path: Path) -> None:
    """Contra JPL Horizons: el rango de una consulta y la consulta de un día dan lo mismo."""
    days = [dt.date(2026, 11, 13), dt.date(2026, 11, 14), dt.date(2026, 11, 15)]
    result = _client(Settings(cache_dir=tmp_path / "range")).preload(days[0], days[-1], "499")
    assert result.written == tuple(days)
    daily = _client(Settings(cache_dir=tmp_path / "daily")).comms_window(days[1], "499").data
    offline = _client(Settings(cache_dir=tmp_path / "range", offline=True))
    preloaded = offline.comms_window(days[1], "499")
    assert preloaded.data == daily
    assert daily.round_trip_minutes == pytest.approx(22.03, abs=0.05)


# --- 6. El guion ----------------------------------------------------------------------------


def _script(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> Any:
    path = BACKEND / "scripts" / "preload_ephemeris.py"
    spec = importlib.util.spec_from_file_location("preload_ephemeris", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    return module


def test_the_script_refuses_offline_and_says_so(
    tmp_path: Path, horizons: Horizons, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _script(monkeypatch, _settings(tmp_path, offline=True))
    assert script.main([]) == 2
    err = capsys.readouterr().err
    assert "No se precarga" in err and "modo sin red" in err and "EMMA_OFFLINE=true" in err
    assert horizons.asked == []


def test_the_script_says_when_horizons_left_days_out(
    tmp_path: Path, horizons: Horizons, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pedido hasta el 7 y llegan filas hasta el 5: no sale como si hubiera precargado todo."""
    assert _script(monkeypatch, _settings(tmp_path, days=6)).main([]) == 4
    err = capsys.readouterr().err
    assert "no devolvió 2 de los días que faltaban (2026-11-06 a 2026-11-07)" in err


def test_the_script_preloads_and_check_reports(
    tmp_path: Path, horizons: Horizons, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _script(monkeypatch, _settings(tmp_path, offline=True)).main(["--check"]) == 3
    assert _script(monkeypatch, _settings(tmp_path)).main([]) == 0
    out = capsys.readouterr().out
    assert "Pedido a Horizons en una consulta: 2026-11-01 a 2026-11-05" in out
    assert "5 días escritos" in out
    assert _script(monkeypatch, _settings(tmp_path, offline=True)).main(["--check"]) == 0
    assert len(horizons.asked) == 1


# --- 7. Robustez de la caché y de la precarga (decimoséptima ronda, §5.37.12) ----------------


# Del 2 al 12 de noviembre en caché: faltan el 1 y el 13-14, con once días en medio.
FAR_CACHED = [START + dt.timedelta(days=n) for n in range(1, 12)]


def test_runs_of_days_and_the_bridge_between_them() -> None:
    def day(n: int) -> dt.date:
        return dt.date(2026, 11, n)

    assert day_runs([day(1), day(2), day(4), day(5)]) == [(day(1), day(2)), (day(4), day(5))]
    assert day_runs([day(1), day(2), day(4), day(5)], bridge=1) == [(day(1), day(5))]
    assert day_runs([day(1), day(9)], bridge=PRELOAD_BRIDGE_DAYS) == [(day(1), day(9))]
    assert day_runs([day(1), day(10)], bridge=PRELOAD_BRIDGE_DAYS) == [
        (day(1), day(1)), (day(10), day(10)),
    ]
    assert day_runs([]) == []


def test_the_preload_asks_one_query_per_missing_run(
    tmp_path: Path, horizons: Horizons, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Faltan el 1 y el 13-14, con once días en caché en medio: dos consultas, no la misión
    entera (antes, del 1 al 14 en una)."""
    settings = _settings(tmp_path, days=13)
    _seed(tmp_path, FAR_CACHED)
    assert _script(monkeypatch, settings).main([]) == 4  # la respuesta interceptada acaba el 5
    assert [(asked["START_TIME"], asked["STOP_TIME"]) for asked in horizons.asked] == [
        ('"2026-11-01"', '"2026-11-02"'), ('"2026-11-13"', '"2026-11-14"'),
    ]
    out = capsys.readouterr().out
    assert (
        "Pedido a Horizons en 2 consultas, una por tramo que faltaba: "
        "2026-11-01 a 2026-11-02; 2026-11-13 a 2026-11-14" in out
    )
    assert "1 días escritos, 11 ya estaban" in out


def test_a_network_failure_on_the_second_query_writes_nothing(
    tmp_path: Path, horizons: Horizons
) -> None:
    settings = _settings(tmp_path, days=13)
    _seed(tmp_path, FAR_CACHED)
    before = _files(settings)
    answer = horizons.request

    def second_fails(_self: object, method: str, url: str, **kwargs: Any) -> MockResponse:
        if horizons.asked:
            horizons.error = requests.ConnectionError("red caída")
        return answer(_self, method, url, **kwargs)

    horizons.request = second_fails  # type: ignore[method-assign]
    start, end = ephemeris_coverage.mission_span(settings)
    with pytest.raises(OfflineDataUnavailable, match="inaccesible"):
        _client(settings).preload(start, end, "499")
    assert len(horizons.asked) == 2
    assert _files(settings) == before


def test_a_table_with_no_row_at_midnight_is_a_bad_answer(
    tmp_path: Path, horizons: Horizons
) -> None:
    """Todas las filas a otra hora no son filas raras: es la API que cambió (502, como antes)."""
    for day in range(5):
        jd = f"{2461345 + day}".encode()
        horizons.body = horizons.body.replace(jd + b".500000000", jd + b".750000000")
    settings = _settings(tmp_path)
    with pytest.raises(HorizonsResponseError, match="ninguna de las 5 filas"):
        _client(settings).preload(DAYS[0], DAYS[-1], "499")
    with pytest.raises(HorizonsResponseError, match="ninguna de las 5 filas"):
        _client(settings).comms_window(DAYS[0], "499")
    assert _files(settings) == {}


def test_an_off_midnight_row_of_a_cached_day_does_not_stop_the_others(
    tmp_path: Path, horizons: Horizons
) -> None:
    """Antes abortaba la precarga entera, aunque la fila fuera de un día ya guardado."""
    settings = _settings(tmp_path)
    _seed(tmp_path, DAYS[1:4])
    horizons.body = horizons.body.replace(b"2461346.500000000", b"2461346.750000000")
    result = _client(settings).preload(DAYS[0], DAYS[-1], "499")
    assert result.written == (DAYS[0], DAYS[-1]) and result.not_received == ()


def test_the_daily_query_takes_the_row_of_its_day_not_the_first(
    tmp_path: Path, horizons: Horizons
) -> None:
    """La respuesta interceptada empieza el 1; pedido el 3, se guarda la fila del 3."""
    settings = _settings(tmp_path)
    payload = _client(settings).comms_window(DAYS[2], "499")
    assert payload.data.epoch == DAYS[2]
    assert payload.data.one_way_minutes == pytest.approx(11.77829269)
    assert payload.data.distance_au == pytest.approx(1.41621400083797)
    # Un día que la tabla no trae no se guarda con la fila de otro.
    with pytest.raises(HorizonsResponseError, match="no trae la fila del 2026-11-09"):
        _client(settings).comms_window(dt.date(2026, 11, 9), "499")
    assert not _client(settings).is_cached(dt.date(2026, 11, 9), "499")


def _failing_put(monkeypatch: pytest.MonkeyPatch, on_call: int) -> list[str]:
    """`FileCache.put` falla como un disco lleno en la llamada `on_call` (desde 1)."""
    real = FileCache.put
    calls: list[str] = []

    def put(self: FileCache, key: str, data: Any, source: str) -> Any:
        calls.append(key)
        if len(calls) == on_call:
            raise OSError(28, "No space left on device")
        return real(self, key, data, source)

    monkeypatch.setattr(FileCache, "put", put)
    return calls


def test_a_disk_failure_while_preloading_is_unavailable_not_a_crash(
    tmp_path: Path, horizons: Horizons, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    _failing_put(monkeypatch, on_call=3)
    with pytest.raises(EphemerisCacheWriteError, match="Quedaron escritos 2 de 5") as caught:
        _client(settings).preload(DAYS[0], DAYS[-1], "499")
    assert isinstance(caught.value, OfflineDataUnavailable)
    assert "2026-11-03" in str(caught.value) and "No space left" in str(caught.value)
    # Lo escrito antes del fallo está entero y se sirve.
    assert _client(settings).cached_days(DAYS, "499") == [True, True, False, False, False]


def test_the_script_says_a_disk_failure_is_the_disk_not_the_network(
    tmp_path: Path, horizons: Horizons, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _failing_put(monkeypatch, on_call=3)
    assert _script(monkeypatch, _settings(tmp_path)).main([]) == 6
    err = capsys.readouterr().err
    assert "No se pudo guardar en la caché" in err and "Quedaron escritos 2 de 5" in err
    assert "No se precarga" not in err


def test_a_malformed_cache_entry_is_not_cached_for_the_delay_either(
    tmp_path: Path, horizons: Horizons
) -> None:
    """Sin la forma de la caché: sin red, «no cacheadas» (antes, un 500); con red, se vuelve a
    pedir y se reescribe."""
    cache = FileCache(tmp_path / "ephemeris")
    window = CommsWindow(DAYS[0], 1.4, 11.6, "499").to_dict()
    malformed = {
        DAYS[0]: json.dumps({"data": window, "source": "a mano"}),  # sin `fetched_at`
        DAYS[1]: "[1]",
        DAYS[2]: json.dumps({"key": "x", "source": "a mano",
                             "fetched_at": "2026-10-23T00:00:00+00:00", "data": {}}),
    }
    for epoch, text in malformed.items():
        cache.path_for(cache_key("499", "500@399", epoch)).write_text(text, encoding="utf-8")
    offline = _client(_settings(tmp_path, offline=True))
    for epoch in malformed:
        with pytest.raises(OfflineDataUnavailable, match="no cacheadas"):
            offline.comms_window(epoch, "499")
    fetched = _client(_settings(tmp_path)).comms_window(DAYS[1], "499")
    assert fetched.from_cache is False
    assert offline.comms_window(DAYS[1], "499").data.distance_au == pytest.approx(1.42437937425787)


def test_the_route_says_503_with_the_reason_on_a_disk_failure(
    api: dict[str, Any], horizons: Horizons, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api["settings"] = _settings(tmp_path)
    _failing_put(monkeypatch, on_call=1)
    response = api["client"].post("/api/comms/preload")
    assert response.status_code == 503
    assert "no se pudo escribir la efeméride del 2026-11-01" in response.json()["detail"]


def test_the_daily_query_serves_what_it_got_even_if_it_cannot_save_it(
    tmp_path: Path, horizons: Horizons, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _settings(tmp_path)
    _failing_put(monkeypatch, on_call=1)
    with caplog.at_level("WARNING", logger="app.environment.ephemeris"):
        payload = _client(settings).comms_window(DAYS[0], "499")
    assert payload.from_cache is False and payload.source == "JPL Horizons"
    assert payload.data.one_way_minutes == pytest.approx(FIRST["lt"])
    assert "no guardada en caché" in caplog.text
    assert _files(settings) == {}


def test_a_purpose_off_the_allowlist_is_unavailable_with_its_reason(
    api: dict[str, Any], horizons: Horizons, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`EgressNotAllowed` salía de la ruta de precarga como un 500 sin motivo.

    En la consulta diaria sigue saliendo tal cual: el estado convierte «no disponible» en un
    retardo «sin dato» mudo, y la puerta pide que este error sea ruidoso.
    """
    monkeypatch.delitem(egress.ALLOWLIST, "ephemeris")
    settings = _settings(tmp_path)
    with pytest.raises(OfflineDataUnavailable, match="la puerta de salida no lo permite"):
        _client(settings).preload(DAYS[0], DAYS[-1], "499")
    with pytest.raises(egress.EgressNotAllowed):
        _client(settings).comms_window(DAYS[0], "499")
    api["settings"] = settings
    response = api["client"].post("/api/comms/preload")
    assert response.status_code == 503
    assert "no lo permite" in response.json()["detail"]
    assert horizons.asked == []


def test_a_cache_write_replaces_the_entry_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hasta la sustitución, quien lee ve la entrada de antes entera; después, la nueva."""
    cache = FileCache(tmp_path / "c")
    cache.put("k", {"v": 1}, source="s")
    target = cache.path_for("k")
    real = os.replace
    seen: list[Any] = []

    def replace(source: Any, destination: Any) -> None:
        seen.append(json.loads(Path(destination).read_text(encoding="utf-8"))["data"])
        seen.append(json.loads(Path(source).read_text(encoding="utf-8"))["data"])
        real(source, destination)

    monkeypatch.setattr(cache_module.os, "replace", replace)
    cache.put("k", {"v": 2}, source="s")
    assert seen == [{"v": 1}, {"v": 2}]
    stored = cache.get("k")
    assert stored is not None and stored.data == {"v": 2}
    assert [path.name for path in cache.root.iterdir()] == [target.name]


def test_a_failed_cache_write_leaves_the_old_entry_and_no_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = FileCache(tmp_path / "c")
    cache.put("k", {"v": 1}, source="s")

    def replace(source: Any, destination: Any) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(cache_module.os, "replace", replace)
    with pytest.raises(OSError, match="No space left"):
        cache.put("k", {"v": 2}, source="s")
    stored = cache.get("k")
    assert stored is not None and stored.data == {"v": 1}
    assert [path.name for path in cache.root.iterdir()] == [cache.path_for("k").name]


def test_a_cache_write_waits_for_a_reader_holding_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """En Windows, sustituir un fichero que otro tiene abierto da «acceso denegado» un instante."""
    cache = FileCache(tmp_path / "c")
    real = os.replace
    refused: list[Any] = []

    def replace(source: Any, destination: Any) -> None:
        if len(refused) < 2:
            refused.append(destination)
            raise PermissionError(13, "Access is denied")
        real(source, destination)

    monkeypatch.setattr(cache_module.os, "replace", replace)
    monkeypatch.setattr(cache_module.time, "sleep", lambda seconds: None)
    cache.put("k", {"v": 1}, source="s")
    stored = cache.get("k")
    assert len(refused) == 2 and stored is not None and stored.data == {"v": 1}


def test_a_cache_entry_keeps_the_usual_file_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El temporal de `mkstemp` nace 0600; la entrada sale con 0666 menos la máscara, como con
    `write_text`, para que el guion y el servidor con usuarios distintos se lean la caché."""
    mask = os.umask(0)
    os.umask(mask)
    assert 0o666 & ~mask == cache_module._FILE_MODE
    real = os.chmod
    modes: list[int] = []

    def chmod(path: Any, mode: int) -> None:
        modes.append(mode)
        real(path, mode)

    monkeypatch.setattr(cache_module.os, "chmod", chmod)
    FileCache(tmp_path / "c").put("k", {"v": 1}, source="s")
    assert modes == [cache_module._FILE_MODE]


def test_clearing_the_cache_also_removes_leftover_temporaries(tmp_path: Path) -> None:
    """Un corte a mitad de `put` (proceso matado, sin corriente) deja el temporal."""
    cache = FileCache(tmp_path / "c")
    cache.put("k", {"v": 1}, source="s")
    (cache.root / f".{cache.path_for('k').stem}.abc.tmp").write_text("{", encoding="utf-8")
    assert cache.clear() == 1
    assert list(cache.root.iterdir()) == []


def test_what_is_remembered_survives_concurrent_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Las dos consolas piden el estado a la vez: olvidar lo más antiguo no puede fallar."""
    remembered: dict[str, Any] = {}
    monkeypatch.setattr(ephemeris_module, "_LOADABLE", remembered)
    monkeypatch.setattr(ephemeris_module, "_LOADABLE_MAX", 4)
    failures: list[BaseException] = []

    def churn(worker: int) -> None:
        try:
            for n in range(3000):
                ephemeris_module._remember(f"{worker}-{n % 50}", (n, n), True)
        except BaseException as exc:  # noqa: BLE001 - se recoge para la aserción
            failures.append(exc)

    threads = [threading.Thread(target=churn, args=(worker,)) for worker in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert failures == [] and len(remembered) <= 4


def _seed(tmp_path: Path, days: list[dt.date]) -> None:
    cache = FileCache(tmp_path / "ephemeris")
    for epoch in days:
        cache.put(
            cache_key("499", "500@399", epoch),
            CommsWindow(epoch, 1.4, 11.6, "499").to_dict(), source="JPL Horizons",
        )


def test_what_is_remembered_has_a_cap_and_forgets_missing_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remembered: dict[str, Any] = {}
    monkeypatch.setattr(ephemeris_module, "_LOADABLE", remembered)
    monkeypatch.setattr(ephemeris_module, "_LOADABLE_MAX", 3)
    _seed(tmp_path, DAYS)
    client = _client(_settings(tmp_path))
    assert [client.is_cached(day, "499") for day in DAYS] == [True] * 5
    assert len(remembered) == 3
    assert client.cached_days(DAYS, "499") == [True] * 5
    assert len(remembered) == 3
    # Un fichero que ya no está se olvida, por las dos vías.
    last = client.cache.path_for(cache_key("499", "500@399", DAYS[-1]))
    assert str(last) in remembered
    last.unlink()
    assert client.is_cached(DAYS[-1], "499") is False and str(last) not in remembered
    before = client.cache.path_for(cache_key("499", "500@399", DAYS[-2]))
    assert client.cached_days(DAYS[-2:], "499") == [True, False] and str(before) in remembered
    before.unlink()
    assert client.cached_days(DAYS[-2:], "499") == [False, False] and str(before) not in remembered


def test_cached_days_says_the_same_as_is_cached_day_by_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Buena, ausente, rota, sin forma de caché y con el retardo NaN: la misma respuesta."""
    _seed(tmp_path, [DAYS[0], DAYS[3]])
    cache = FileCache(tmp_path / "ephemeris")
    cache.path_for(cache_key("499", "500@399", DAYS[1])).write_text("{roto", encoding="utf-8")
    cache.path_for(cache_key("499", "500@399", DAYS[2])).write_text("[1]", encoding="utf-8")
    window = CommsWindow(DAYS[4], 1.4, 11.6, "499").to_dict()
    cache.put(
        cache_key("499", "500@399", DAYS[4]), {**window, "one_way_minutes": float("nan")},
        source="a mano",
    )
    client = _client(_settings(tmp_path))
    monkeypatch.setattr(ephemeris_module, "_LOADABLE", {})
    listed = client.cached_days(DAYS, "499")
    monkeypatch.setattr(ephemeris_module, "_LOADABLE", {})
    one_by_one = [client.is_cached(day, "499") for day in DAYS]
    assert listed == one_by_one == [True, False, False, True, False]


def test_a_rewritten_entry_is_read_again_from_the_listing(tmp_path: Path) -> None:
    client = _client(_settings(tmp_path, days=0))
    key = cache_key("499", "500@399", DAYS[0])
    client.cache.put(key, {"epoch": "2026-11-01"}, source="a mano")
    assert client.cached_days([DAYS[0]], "499") == [False]
    client.cache.put(key, CommsWindow(DAYS[0], 1.4, 11.6, "499").to_dict(), source="JPL Horizons")
    assert client.cached_days([DAYS[0]], "499") == [True]


def test_the_coverage_reads_the_folder_once_not_a_stat_per_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    _seed(tmp_path, DAYS[:2])

    def one_by_one(self: EphemerisClient, epoch: dt.date, target: str | None = None) -> bool:
        raise AssertionError("la cobertura de la misión mira fichero a fichero")

    monkeypatch.setattr(EphemerisClient, "is_cached", one_by_one)
    said = ephemeris_coverage.coverage(settings, day=START, target="499")
    assert (said["covered_days"], said["state"]) == (2, ephemeris_coverage.PARTIAL)


def test_a_cache_folder_that_cannot_be_read_covers_nothing(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _seed(tmp_path, DAYS)
    client = _client(settings)
    shutil.rmtree(client.cache.root)
    assert client.cached_days(DAYS, "499") == [False] * 5
    said = ephemeris_coverage.coverage(settings, client, day=START, target="499")
    assert said["state"] == ephemeris_coverage.NONE


def test_a_healthy_cache_serves_the_same_delay_and_coverage_as_before(
    tmp_path: Path, horizons: Horizons
) -> None:
    """Para una caché sana nada cambia: lo mismo que la prueba de la decimosexta ronda."""
    _client(_settings(tmp_path)).preload(DAYS[0], DAYS[-1], "499")
    offline = _client(_settings(tmp_path, offline=True))
    assert offline.cached_days(DAYS, "499") == [True] * 5
    assert offline.comms_window(DAYS[0], "499").data.one_way_minutes == pytest.approx(FIRST["lt"])
    assert offline.comms_window(DAYS[-1], "499").data.one_way_minutes == pytest.approx(LAST["lt"])
    said = ephemeris_coverage.coverage(_settings(tmp_path, offline=True), day=START, target="499")
    assert said["state"] == ephemeris_coverage.COMPLETE and said["covered_days"] == 5


# --- 8. Una precarga a la vez, y la frase en texto plano (decimoctava ronda, §5.38.9) -----------


def test_how_to_preload_is_plain_text_the_console_shows_as_is() -> None:
    """Llevaba comillas invertidas de Markdown y la consola las enseñaba tal cual."""
    text = ephemeris_coverage.HOW_TO_PRELOAD
    for mark in ("`", "**", "__", "]("):
        assert mark not in text, mark
    assert "backend/scripts/preload_ephemeris.py" in text
    assert "POST /api/comms/preload" in text


class _SpyLock:
    """El cerrojo de precarga de verdad, que avisa cuando alguien se pone a esperarlo."""

    def __init__(self, lock: threading.Lock) -> None:
        self.lock = lock
        self.waiting = threading.Event()

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        if blocking:
            self.waiting.set()
        return self.lock.acquire(blocking, timeout)

    def release(self) -> None:
        self.lock.release()


def test_two_preloads_at_once_ask_and_write_once(
    tmp_path: Path, horizons: Horizons, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La segunda espera a la primera y mira la caché después: lo que aquella escribió ya no
    falta, no se pide ni se reescribe, y su resultado lo dice."""
    settings = _settings(tmp_path)
    spy = _SpyLock(ephemeris_module._preload_lock(tmp_path / "ephemeris"))
    monkeypatch.setattr(ephemeris_module, "_preload_lock", lambda root: spy)
    asked, go_on = threading.Event(), threading.Event()
    answer = horizons.request

    def held(_self: object, method: str, url: str, **kwargs: Any) -> MockResponse:
        asked.set()
        assert go_on.wait(10)
        return answer(_self, method, url, **kwargs)

    horizons.request = held  # type: ignore[method-assign]
    writes: list[str] = []
    put = FileCache.put

    def counted(self: FileCache, key: str, data: Any, source: str) -> None:
        writes.append(key)
        put(self, key, data, source=source)

    monkeypatch.setattr(FileCache, "put", counted)
    results: dict[str, Any] = {}

    def run(name: str) -> None:
        results[name] = _client(settings).preload(DAYS[0], DAYS[-1], "499")

    first = threading.Thread(target=run, args=("first",), daemon=True)
    second = threading.Thread(target=run, args=("second",), daemon=True)
    # Los hilos acaban dentro de la prueba pase lo que pase: después se quita la respuesta
    # interceptada, y un hilo vivo saldría a la red de verdad (invariante 3).
    try:
        first.start()
        assert asked.wait(10)  # la primera está dentro de su consulta, con el cerrojo
        spy.waiting.clear()
        second.start()
        assert spy.waiting.wait(10)  # la segunda espera al cerrojo...
        assert horizons.asked == []  # ...sin haber pedido nada (la primera aún no ha vuelto)
    finally:
        go_on.set()
        first.join(10)
        second.join(10)
    assert not first.is_alive() and not second.is_alive()

    assert len(horizons.asked) == 1
    assert len(writes) == 5 and len(set(writes)) == 5
    assert results["first"].written == tuple(DAYS)
    assert results["first"].waited_for_another is False
    later = results["second"]
    assert later.waited_for_another is True
    assert (later.requested, later.written, later.already_cached) == (None, (), 5)
    assert later.to_dict()["waited_for_another"] is True


def test_a_preload_that_does_not_end_in_time_says_one_is_in_progress(
    tmp_path: Path, horizons: Horizons, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(ephemeris_module, "PRELOAD_WAIT_SECONDS", 0.05)
    lock = ephemeris_module._preload_lock(tmp_path / "ephemeris")
    assert lock.acquire(blocking=False)
    began = time.monotonic()
    try:
        with pytest.raises(ephemeris_module.PreloadInProgress, match="ya hay una precarga"):
            _client(settings).preload(DAYS[0], DAYS[-1], "499")
    finally:
        lock.release()
    # Espera lo de su tope, no más: la petición de la consola no se queda colgada.
    assert time.monotonic() - began < 2
    assert horizons.asked == [] and _files(settings) == {}
    # Suelto el cerrojo, la siguiente precarga sí pide.
    assert _client(settings).preload(DAYS[0], DAYS[-1], "499").written == tuple(DAYS)


def test_the_route_says_409_when_another_preload_does_not_end_in_time(
    api: dict[str, Any], horizons: Horizons, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api["settings"] = settings = _settings(tmp_path)
    monkeypatch.setattr(ephemeris_module, "PRELOAD_WAIT_SECONDS", 0.05)
    lock = ephemeris_module._preload_lock(tmp_path / "ephemeris")
    assert lock.acquire(blocking=False)
    try:
        response = api["client"].post("/api/comms/preload")
    finally:
        lock.release()
    assert response.status_code == 409
    assert "ya hay una precarga de efemérides en curso" in response.json()["detail"]
    assert horizons.asked == [] and _files(settings) == {}


def test_the_preload_lock_is_one_per_cache_folder(tmp_path: Path, horizons: Horizons) -> None:
    """La misma carpeta, dicha de dos maneras, comparte cerrojo; otra carpeta no espera."""
    root = tmp_path / "ephemeris"
    assert ephemeris_module._preload_lock(root) is ephemeris_module._preload_lock(
        str(tmp_path) + os.sep + "." + os.sep + "ephemeris"
    )
    other = tmp_path / "other"
    assert ephemeris_module._preload_lock(root) is not ephemeris_module._preload_lock(
        other / "ephemeris"
    )
    lock = ephemeris_module._preload_lock(root)
    assert lock.acquire(blocking=False)
    try:
        result = _client(_settings(other)).preload(DAYS[0], DAYS[-1], "499")
    finally:
        lock.release()
    assert result.written == tuple(DAYS) and result.waited_for_another is False
