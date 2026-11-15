"""Lógica 1 (2026-11-11): contradicciones del entorno entre piezas que no se veían por separado.

1. **El «hoy» de las efemérides es el de UT.** Cada efeméride es la de las 00:00 UT de su día y
   la misión empieza a las 00:00 UTC, pero el retardo, su cobertura y DONKI leían el día del reloj
   local. Se fija con un reloj falso en que el día local ya es mañana y el UT todavía es hoy.
2. **Olvidar un fichero de la caché de efemérides toma el cerrojo** de lo recordado, como
   recordarlo: sin él, un `/api/status` que olvida mientras otro recorre lo recordado tumbaba el
   segundo con «dictionary changed size during iteration».

Sin red (invariante 3): ningún cliente sale; el retardo se pide a un cliente de prueba.
"""

from __future__ import annotations

import datetime as dt
import threading
import types
from pathlib import Path
from typing import Any

import pytest

from app.api import routes
from app.core.cache import CachedPayload
from app.core.config import Settings
from app.environment import ephemeris, ephemeris_coverage
from app.environment.ephemeris import CommsWindow, EphemerisClient

# 00:30 del 12 en Madrid (UTC+1) son las 23:30 del 11 en UT.
UT_DAY = dt.date(2026, 11, 11)
LOCAL_DAY = dt.date(2026, 11, 12)


class _LocalAheadDate(dt.date):
    @classmethod
    def today(cls) -> _LocalAheadDate:
        return cls(LOCAL_DAY.year, LOCAL_DAY.month, LOCAL_DAY.day)


class _UtcBehindDatetime(dt.datetime):
    @classmethod
    def now(cls, tz: dt.tzinfo | None = None) -> _UtcBehindDatetime:
        moment = cls(2026, 11, 11, 23, 30, tzinfo=dt.UTC)
        return moment if tz is None else moment.astimezone(tz)


def _clock() -> types.ModuleType:
    """Un `datetime` cuyo día local va un día por delante del de UT."""
    fake = types.ModuleType("datetime")
    fake.__dict__.update(vars(dt))
    fake.__dict__.update(date=_LocalAheadDate, datetime=_UtcBehindDatetime)
    return fake


@pytest.fixture
def local_ahead(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _clock()
    for module in (routes, ephemeris, ephemeris_coverage):
        monkeypatch.setattr(module, "dt", fake)


def test_the_comms_of_today_ask_for_the_ut_day(
    local_ahead: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El retardo del estado (`_fetch_comms`) pide la efeméride del día UT, no la del local."""
    asked: list[dt.date] = []

    class Recording:
        def __init__(self, settings: Settings) -> None:
            pass

        def comms_window(self, epoch: dt.date, target: str) -> CachedPayload:
            asked.append(epoch)
            return CachedPayload(
                data=CommsWindow(epoch, 1.3, 10.8, "499"),
                fetched_at=dt.datetime(2026, 11, 1, tzinfo=dt.UTC), source="prueba",
                from_cache=True,
            )

    monkeypatch.setattr(routes, "EphemerisClient", Recording)
    window, _ = routes._fetch_comms(Settings(cache_dir=tmp_path, offline=True), None, "499")
    assert asked == [UT_DAY]
    assert window is not None and window.epoch == UT_DAY


def test_the_coverage_says_today_in_ut(local_ahead: None, tmp_path: Path) -> None:
    settings = Settings(cache_dir=tmp_path, offline=True)
    served = ephemeris_coverage.coverage(settings, EphemerisClient(settings=settings), target="499")
    assert served["day"]["date"] == UT_DAY.isoformat()


def test_forgetting_a_cache_file_waits_for_the_lock_of_what_is_remembered(
    tmp_path: Path,
) -> None:
    client = EphemerisClient(settings=Settings(cache_dir=tmp_path, offline=True))
    done = threading.Event()
    results: list[Any] = []

    def ask() -> None:
        results.append(client.is_cached(dt.date(2026, 11, 20), "499"))
        results.append(client.cached_days([dt.date(2026, 11, 21)], "499"))
        done.set()

    with ephemeris._LOADABLE_LOCK:
        worker = threading.Thread(target=ask)
        worker.start()
        # Con el cerrojo tomado por «otro hilo que recuerda», olvidar tiene que esperar.
        assert not done.wait(0.3), "olvidó un fichero sin tomar el cerrojo de lo recordado"
    worker.join(timeout=5)
    assert done.is_set() and results == [False, [False]]
