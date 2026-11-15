"""Cálculo local del retardo con SPICE (`environment/spice.py`) y su sitio frente a JPL Horizons.

Lo que no se puede romper:

1. **Sin `spiceypy` o sin núcleos, todo sigue como antes** (Horizons y su caché) y se dice por qué.
2. **Un núcleo que no es el fijado no se carga**: tamaño, SHA-256 fijado y MD5 publicado.
3. **Precedencia** (decisión del usuario, 2026-11-11): SPICE primero, sin salir a la red; la
   caché de Horizons del mismo día lo contrasta, y si discrepa por encima del error declarado se
   dice y se usa Horizons. Sin SPICE (o un día que no calcula), lo de antes: la caché de
   Horizons y después Horizons en vivo. Cada ventana dice de dónde sale, y lo de SPICE nunca se
   escribe en la caché de Horizons.
4. **La cobertura dice qué días cubre SPICE**, y su frase deja de decir «sin dato» de ellos.
5. **La descarga de los núcleos solo lleva la URL pública**: ni tripulación, ni usuario, ni
   proyecto (aclaración del usuario, 2026-11-11). Se inspeccionan las peticiones.
6. **La geometría es la que se pide**: con un núcleo diminuto hecho aquí (cuerpos quietos en
   posiciones conocidas), la distancia, el tiempo de luz, la elongación y su marca son las de la
   cuenta a mano. Esas pruebas necesitan `spiceypy` (extra `[spice]`) y se saltan sin él.

Sin red (invariante 3): Horizons se intercepta como en `test_ephemeris_preload.py` y la descarga
con `respx`. Ninguna prueba usa los núcleos de `data/spice` (`conftest.py` fija otra carpeta).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import math
import sys
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import respx
from astroquery.jplhorizons import HorizonsClass
from astroquery.utils.mocks import MockResponse
from fastapi.testclient import TestClient

from app.api.routes import new_store, reset_store
from app.core import egress
from app.core.cache import OfflineDataUnavailable
from app.core.config import Settings, get_settings
from app.environment import ephemeris_coverage, spice
from app.environment.ephemeris import (
    LIGHT_SECONDS_PER_AU,
    SOURCE,
    CommsWindow,
    EphemerisClient,
)
from app.main import app

BACKEND = Path(__file__).resolve().parents[1]
HORIZONS_FIXTURE = BACKEND / "tests" / "data" / "horizons" / "mars_2026-11-01_05.txt"
START = dt.date(2026, 11, 1)
LABEL = f"SPICE local, núcleo {spice.spk_name()}"


def _settings(tmp_path: Path, *, offline: bool = True, days: int = 4) -> Settings:
    # La caché en una subcarpeta: los núcleos de cada prueba van en su propia carpeta.
    return Settings(
        cache_dir=tmp_path / "cache", offline=offline, mission_start=START, mission_days=days,
        assistant_warmup=False,
    )


def _window(epoch: dt.date, target: str = "499", minutes: float = 11.0) -> CommsWindow:
    return CommsWindow(
        epoch=epoch, distance_au=minutes * 60 / LIGHT_SECONDS_PER_AU, one_way_minutes=minutes,
        target=target, solar_elongation_deg=80.0, solar_elongation_flag="/L", source=LABEL,
    )


class FakeSpice:
    """SPICE «disponible» que calcula un retardo fijo (o el que se le dé por día), o que no puede
    con los días de `unavailable`: para probar dónde entra, no la geometría."""

    def __init__(self) -> None:
        self.asked: list[dt.date] = []
        self.windows: dict[dt.date, CommsWindow] = {}
        self.unavailable: set[dt.date] = set()

    def window(self, settings: Settings, epoch: dt.date, target: str) -> CommsWindow:
        self.asked.append(epoch)
        if epoch in self.unavailable:
            raise spice.SpiceUnavailable(f"SPICE no pudo calcular el {epoch}: fuera del núcleo")
        return self.windows.get(epoch) or _window(epoch, target)


@pytest.fixture
def fake_spice(monkeypatch: pytest.MonkeyPatch) -> FakeSpice:
    fake = FakeSpice()
    monkeypatch.setattr(spice, "window", fake.window)
    return fake


class Horizons:
    """Lo que astroquery pidió, sin salir a la red (como en `test_ephemeris_preload.py`)."""

    def __init__(self) -> None:
        self.asked = 0
        self.body = HORIZONS_FIXTURE.read_bytes()
        self.error: BaseException | None = None

    def request(self, _self: object, method: str, url: str, **kwargs: Any) -> MockResponse:
        self.asked += 1
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


@pytest.fixture
def kernels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    folder = tmp_path / "spice"
    folder.mkdir()
    monkeypatch.setattr(spice, "KERNEL_DIR", folder)
    yield folder
    spice._unload()


def _pin(folder: Path, files: dict[str, bytes], md5: dict[str, str] | None = None
         ) -> tuple[spice.Kernel, ...]:
    """Escribe ficheros y devuelve los `Kernel` fijados con su tamaño y su huella."""
    pinned = []
    for name, content in files.items():
        (folder / name).write_bytes(content)
        pinned.append(spice.Kernel(
            name=name, url=f"https://{spice.NAIF_HOST}/pub/naif/generic_kernels/{name}",
            kind="SPK" if name.endswith(".bsp") else "LSK", size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            md5=(md5 or {}).get(name), integrity_source="prueba", covers="prueba",
        ))
    return tuple(pinned)


# --- 1. Sin spiceypy o sin núcleos, como antes ------------------------------------------------


def test_without_spiceypy_it_says_so_and_offline_is_as_before(
    tmp_path: Path, kernels: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spice, "_spiceypy", lambda: None)
    settings = _settings(tmp_path)
    state = spice.availability(settings)
    assert not state.available and state.reason is not None
    assert state.reason.startswith("SPICE no instalado")
    with pytest.raises(OfflineDataUnavailable) as raised:
        EphemerisClient(settings).comms_window(START, "499")
    # El motivo de siempre, y el de SPICE detrás.
    assert "no cacheadas" in str(raised.value) and "SPICE no instalado" in str(raised.value)
    assert spice.coverage_span(settings, "499") is None


def test_without_kernels_it_says_which_and_how_to_get_them(
    tmp_path: Path, kernels: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spice, "_spiceypy", lambda: SimpleNamespace(__version__="9.9.9"))
    state = spice.availability(_settings(tmp_path))
    assert not state.available and state.version == "9.9.9"
    assert state.reason is not None and "Núcleos SPICE ausentes" in state.reason
    assert "fetch_spice_kernels.py" in state.reason
    assert [row["present"] for row in state.kernels] == [False, False]


# --- 2. Integridad de los núcleos ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("tamper", "says"),
    [
        (lambda content: content + b"x", "mide"),
        (lambda content: content[:-1] + bytes([content[-1] ^ 1]), "SHA-256"),
    ],
)
def test_a_kernel_that_is_not_the_pinned_one_is_not_loaded(
    tmp_path: Path, kernels: Path, monkeypatch: pytest.MonkeyPatch, tamper: Any, says: str
) -> None:
    pinned = _pin(kernels, {"a.tls": b"lsk de prueba", "b.bsp": b"spk de prueba"})
    monkeypatch.setattr(spice, "KERNELS", pinned)
    monkeypatch.setattr(spice, "_spiceypy", lambda: SimpleNamespace(__version__="t"))
    assert spice.availability(_settings(tmp_path)).available
    (kernels / "b.bsp").write_bytes(tamper(b"spk de prueba"))
    state = spice.availability(_settings(tmp_path))
    assert not state.available and state.reason is not None and says in state.reason
    assert [row["verified"] for row in state.kernels] == [True, False]


def test_the_md5_published_by_naif_is_checked_too(
    tmp_path: Path, kernels: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pinned = _pin(kernels, {"a.tls": b"lsk", "b.bsp": b"spk"}, md5={"b.bsp": "0" * 32})
    monkeypatch.setattr(spice, "KERNELS", pinned)
    assert spice.check_kernel(pinned[1], kernels / "b.bsp") == (
        "la huella MD5 de b.bsp no es la publicada por NAIF"
    )
    assert spice.check_kernel(pinned[0], kernels / "a.tls") is None


def test_the_pinned_kernels_are_the_generic_ones_of_naif() -> None:
    """Los núcleos fijados salen de NAIF y el SPK tiene el MD5 que publica NAIF."""
    assert [kernel.name for kernel in spice.KERNELS] == ["naif0012.tls", "de432s.bsp"]
    for kernel in spice.KERNELS:
        assert kernel.url.startswith(f"https://{spice.NAIF_HOST}/pub/naif/generic_kernels/")
        assert len(kernel.sha256) == 64
    assert spice.KERNELS[1].md5 == "d66c2153188958472fec67016b4b4e7a"
    assert egress.ALLOWLIST[spice.PURPOSE] == frozenset({spice.NAIF_HOST})


# --- 3. Precedencia y origen ------------------------------------------------------------------


def test_offline_without_cache_the_day_comes_from_spice_and_says_so(
    tmp_path: Path, fake_spice: FakeSpice
) -> None:
    settings = _settings(tmp_path)
    payload = EphemerisClient(settings).comms_window(START, "499")
    assert payload.source == LABEL and payload.data.source == LABEL
    assert payload.from_cache is False
    assert payload.data.to_dict()["source"] == LABEL
    # Sin efeméride de Horizons en caché no hay contraste, y se dice con un nulo, no con un cero.
    assert payload.data.contrast is None and payload.data.to_dict()["contrast"] is None
    # No se escribe en la caché de Horizons.
    assert not (Path(settings.cache_dir) / "ephemeris").exists() or not list(
        (Path(settings.cache_dir) / "ephemeris").glob("*.json")
    )
    assert not EphemerisClient(settings).is_cached(START, "499")


@respx.mock
def test_with_spice_horizons_is_not_asked_even_online(
    tmp_path: Path, horizons: Horizons, fake_spice: FakeSpice
) -> None:
    """SPICE primero: con red y sin caché, el día sale de SPICE y no sale nada a internet.

    `respx.mock` sin rutas hace fallar cualquier salida por httpx, y astroquery (que sale por
    `requests`) está interceptado y contado: ninguna de las dos se usa.
    """
    settings = _settings(tmp_path, offline=False)
    payload = EphemerisClient(settings).comms_window(START, "499")
    assert payload.data.source == LABEL and fake_spice.asked == [START]
    assert horizons.asked == 0 and not respx.calls
    # Ni siquiera se pidió permiso a la puerta de salida para Horizons.
    audit = (Path(settings.cache_dir) / "egress").glob("audit-*.jsonl")
    assert not [line for path in audit for line in path.read_text("utf-8").splitlines()]


def _horizons_day(tmp_path: Path) -> CommsWindow:
    """La efeméride de Horizons del primer día, precargada en la caché desde la tabla de prueba."""
    EphemerisClient(_settings(tmp_path, offline=False)).preload(START, START, "499")
    found = EphemerisClient(_settings(tmp_path)).cached(START, "499")
    assert found is not None
    return found[1]


def test_a_contrast_that_agrees_serves_spice_and_says_so(
    tmp_path: Path, horizons: Horizons, fake_spice: FakeSpice
) -> None:
    reference = _horizons_day(tmp_path)
    assert reference.solar_elongation_deg is not None
    # SPICE a 0,05 s y 0,005° de Horizons: dentro del error declarado (0,1 s y 0,01°).
    fake_spice.windows[START] = replace(
        reference, source=LABEL, one_way_minutes=reference.one_way_minutes + 0.05 / 60,
        solar_elongation_deg=reference.solar_elongation_deg + 0.005,
    )
    asked = horizons.asked
    payload = EphemerisClient(_settings(tmp_path)).comms_window(START, "499")
    assert horizons.asked == asked  # el contraste es con la caché: no se pide nada en vivo
    assert payload.source == LABEL and payload.data.source == LABEL and not payload.from_cache
    contrast = payload.data.contrast
    assert contrast is not None and contrast.agrees and contrast.used == LABEL
    assert contrast.reference == SOURCE and contrast.local == LABEL
    assert contrast.one_way_seconds_difference == pytest.approx(0.05, abs=1e-6)
    assert contrast.elongation_deg_difference == pytest.approx(0.005, abs=1e-6)
    said = payload.data.to_dict()["contrast"]
    assert said["agrees"] is True and said["declared_max_error"] == spice.DECLARED_MAX_ERROR
    assert said["text"].startswith("Contrastado con JPL Horizons (en caché)")


def test_a_contrast_that_disagrees_serves_horizons_and_says_so(
    tmp_path: Path, horizons: Horizons, fake_spice: FakeSpice, caplog: pytest.LogCaptureFixture
) -> None:
    reference = _horizons_day(tmp_path)
    # SPICE a 0,2 s de Horizons: por encima del error declarado. Se usa Horizons, la referencia.
    fake_spice.windows[START] = replace(
        reference, source=LABEL, one_way_minutes=reference.one_way_minutes + 0.2 / 60,
    )
    with caplog.at_level(logging.ERROR, logger="app.environment.ephemeris"):
        payload = EphemerisClient(_settings(tmp_path)).comms_window(START, "499")
    assert payload.source == SOURCE and payload.data.source == SOURCE and payload.from_cache
    assert payload.data.one_way_minutes == reference.one_way_minutes
    contrast = payload.data.contrast
    assert contrast is not None and not contrast.agrees and contrast.used == SOURCE
    assert contrast.one_way_seconds_difference == pytest.approx(0.2, abs=1e-6)
    said = payload.data.to_dict()["contrast"]
    assert said["agrees"] is False and "discrepa" in said["text"]
    assert "se usa JPL Horizons" in said["text"]
    assert any("SPICE discrepa" in record.getMessage() for record in caplog.records)


def test_an_elongation_beyond_the_declared_error_is_a_discrepancy(
    tmp_path: Path, horizons: Horizons, fake_spice: FakeSpice
) -> None:
    reference = _horizons_day(tmp_path)
    assert reference.solar_elongation_deg is not None
    fake_spice.windows[START] = replace(
        reference, source=LABEL, solar_elongation_deg=reference.solar_elongation_deg + 0.02,
    )
    payload = EphemerisClient(_settings(tmp_path)).comms_window(START, "499")
    assert payload.data.source == SOURCE
    assert payload.data.contrast is not None and not payload.data.contrast.agrees


def test_a_missing_elongation_is_not_compared(
    tmp_path: Path, horizons: Horizons, fake_spice: FakeSpice
) -> None:
    """Una entrada de caché anterior a leer la elongación: se contrasta solo el tiempo de luz."""
    reference = _horizons_day(tmp_path)
    fake_spice.windows[START] = replace(reference, source=LABEL, solar_elongation_deg=None)
    payload = EphemerisClient(_settings(tmp_path)).comms_window(START, "499")
    contrast = payload.data.contrast
    assert payload.data.source == LABEL
    assert contrast is not None and contrast.agrees and contrast.elongation_deg_difference is None


def test_a_day_spice_cannot_calculate_is_asked_to_horizons_as_before(
    tmp_path: Path, horizons: Horizons, fake_spice: FakeSpice
) -> None:
    fake_spice.unavailable.add(START)
    payload = EphemerisClient(_settings(tmp_path, offline=False)).comms_window(START, "499")
    assert payload.data.source == SOURCE and horizons.asked == 1
    assert payload.data.contrast is None


def test_a_day_spice_cannot_calculate_comes_from_the_horizons_cache(
    tmp_path: Path, horizons: Horizons, fake_spice: FakeSpice
) -> None:
    _horizons_day(tmp_path)
    fake_spice.unavailable.add(START)
    asked = horizons.asked
    payload = EphemerisClient(_settings(tmp_path)).comms_window(START, "499")
    assert payload.from_cache and payload.data.source == SOURCE and horizons.asked == asked


def test_a_day_spice_cannot_calculate_and_horizons_unreachable_says_both(
    tmp_path: Path, horizons: Horizons, fake_spice: FakeSpice
) -> None:
    import requests

    fake_spice.unavailable.add(START)
    horizons.error = requests.ConnectionError("red caída")
    with pytest.raises(OfflineDataUnavailable) as raised:
        EphemerisClient(_settings(tmp_path, offline=False)).comms_window(START, "499")
    assert "inaccesible" in str(raised.value) and "fuera del núcleo" in str(raised.value)


def test_without_spice_the_horizons_cache_serves_as_before(
    tmp_path: Path, kernels: Path, horizons: Horizons
) -> None:
    _horizons_day(tmp_path)
    payload = EphemerisClient(_settings(tmp_path)).comms_window(START, "499")
    assert payload.from_cache and payload.data.source == SOURCE
    assert payload.data.contrast is None


def test_without_spice_online_horizons_is_asked_as_before(
    tmp_path: Path, kernels: Path, horizons: Horizons
) -> None:
    payload = EphemerisClient(_settings(tmp_path, offline=False)).comms_window(START, "499")
    assert payload.data.source == SOURCE and horizons.asked == 1 and not payload.from_cache


def test_a_broken_horizons_answer_without_spice_is_the_error_of_before(
    tmp_path: Path, kernels: Path, horizons: Horizons
) -> None:
    horizons.body = b"$$SOE\nnada que leer\n$$EOE\n"
    with pytest.raises(ValueError):
        EphemerisClient(_settings(tmp_path, offline=False)).comms_window(START, "499")


def test_a_cached_entry_cannot_claim_to_be_spice(tmp_path: Path) -> None:
    """La caché es solo de Horizons: una entrada tocada a mano no cambia el origen."""
    settings = _settings(tmp_path)
    client = EphemerisClient(settings)
    raw = {**_window(START).to_dict(), "source": LABEL}
    client.cache.put(f"horizons:499:{settings.observer_body}:{START}", raw, source=SOURCE)
    assert client.comms_window(START, "499").data.source == SOURCE


# --- 4. Cobertura y estado ----------------------------------------------------------------------


def test_the_coverage_says_which_days_spice_covers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, days=4)
    span = (START + dt.timedelta(days=1), START + dt.timedelta(days=10))
    state = spice.Availability(True, None, "t", ())
    monkeypatch.setattr(
        spice, "covered_days",
        lambda s, days, target: ([span[0] <= d <= span[1] for d in days], state, span),
    )
    body = ephemeris_coverage.coverage(settings, target="499", day=START)
    assert body["state"] == ephemeris_coverage.NONE  # la caché de Horizons sigue vacía
    assert body["spice"]["available"] and body["spice"]["source"] == LABEL
    assert body["spice"]["covered_days"] == 4 and body["spice"]["local_only_days"] == 4
    assert body["spice"]["day_covered"] is False
    assert body["offline_covered_days"] == 4
    assert body["offline_missing"] == [
        {"start": START.isoformat(), "end": START.isoformat(), "days": 1}
    ]
    assert body["served_by"] == {"spice": 4, "horizons_cache": 0, "none": 1}
    assert body["spice"]["contrast_days"] == 0
    assert body["spice"]["contrast_policy"] == spice.CONTRAST_POLICY
    assert body["text"] == (
        "Sin red, el retardo y la conjunción solar de 4 días de los 5 días de la misión (del "
        "2026-11-01 al 2026-11-05, lanzamiento y regreso incluidos) se calculan en local "
        f"({LABEL}); los de 1 día salen sin dato. JPL Horizons no tiene ningún día en caché: el "
        "cálculo local va sin contraste."
    )
    # SPICE no cubre toda la misión: precargar Horizons sigue haciendo falta.
    assert body["how_to_preload"] == ephemeris_coverage.HOW_TO_PRELOAD


def test_with_spice_first_the_horizons_cache_is_contrast_and_fallback(
    tmp_path: Path, horizons: Horizons, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SPICE cubre del 2.º día en adelante; Horizons tiene en caché los dos primeros: el 1.º sale
    de Horizons (SPICE no lo calcula), el 2.º de SPICE con contraste, el resto de SPICE."""
    settings = _settings(tmp_path, days=4)
    EphemerisClient(_settings(tmp_path, offline=False, days=4)).preload(
        START, START + dt.timedelta(days=1), "499"
    )
    span = (START + dt.timedelta(days=1), START + dt.timedelta(days=10))
    state = spice.Availability(True, None, "t", ())
    monkeypatch.setattr(
        spice, "covered_days",
        lambda s, days, target: ([span[0] <= d <= span[1] for d in days], state, span),
    )
    body = ephemeris_coverage.coverage(settings, target="499", day=START)
    assert body["served_by"] == {"spice": 4, "horizons_cache": 1, "none": 0}
    assert body["spice"]["contrast_days"] == 1 and body["covered_days"] == 2
    assert "; los de 1 día salen de la caché de JPL Horizons." in body["text"]
    assert body["text"].endswith(
        "JPL Horizons tiene 2 días en caché; 1 día sirve de contraste del cálculo local."
    )


def test_with_spice_covering_the_mission_the_preload_is_for_contrast(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, days=4)
    span = (START - dt.timedelta(days=1), START + dt.timedelta(days=10))
    state = spice.Availability(True, None, "t", ())
    monkeypatch.setattr(
        spice, "covered_days",
        lambda s, days, target: ([span[0] <= d <= span[1] for d in days], state, span),
    )
    body = ephemeris_coverage.coverage(settings, target="499", day=START)
    assert body["served_by"] == {"spice": 5, "horizons_cache": 0, "none": 0}
    assert body["text"].startswith("Sin red, el retardo y la conjunción solar de los 5 días")
    assert body["how_to_preload"] == ephemeris_coverage.HOW_TO_PRELOAD_AS_CONTRAST
    assert body["how_to_preload"].startswith("No hace falta para el retardo sin red")
    assert body["preload_role"] == ephemeris_coverage.PRELOAD_ROLE_WITH_SPICE


def test_the_preload_script_says_what_the_preload_is_for_with_spice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import importlib.util

    loaded = importlib.util.spec_from_file_location(
        "preload_ephemeris", BACKEND / "scripts" / "preload_ephemeris.py"
    )
    assert loaded is not None and loaded.loader is not None
    script = importlib.util.module_from_spec(loaded)
    loaded.loader.exec_module(script)
    settings = _settings(tmp_path, days=4)
    monkeypatch.setattr(script, "get_settings", lambda: settings)
    state = spice.Availability(True, None, "t", ())
    monkeypatch.setattr(spice, "covered_days", lambda s, days, target: ([True] * len(days),
                                                                        state, (START, START)))
    assert script.main(["--check"]) == 3  # la caché de Horizons sigue vacía: se dice
    out = capsys.readouterr().out
    assert ephemeris_coverage.PRELOAD_ROLE_WITH_SPICE in out


def test_without_spice_the_coverage_text_is_the_one_of_before(tmp_path: Path) -> None:
    body = ephemeris_coverage.coverage(_settings(tmp_path), target="499", day=START)
    assert body["text"].endswith("sin red, el retardo y la conjunción solar salen sin dato.")
    assert body["spice"]["available"] is False and body["spice"]["covered_days"] == 0
    assert body["offline_covered_days"] == 0
    assert body["served_by"] == {"spice": 0, "horizons_cache": 0, "none": 5}
    assert body["how_to_preload"] == ephemeris_coverage.HOW_TO_PRELOAD
    assert body["preload_role"] is None


@pytest.fixture
def api(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: _settings(tmp_path, days=180)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def test_status_offline_takes_the_delay_from_spice(
    api: TestClient, fake_spice: FakeSpice
) -> None:
    api.post("/api/simulate", params={"days": 3})
    body = api.get("/api/status").json()
    comms = body["comms"]
    assert comms is not None and comms["source"] == LABEL and comms["contrast"] is None
    # El riesgo se escala con ese tiempo de luz (perfil de Marte: 22 min de ida y vuelta).
    assert body["isolation_factor"] > 1.0
    assert body["mission"]["ephemeris_coverage"]["spice"] is not None


def test_status_offline_without_spice_is_as_before(api: TestClient) -> None:
    api.post("/api/simulate", params={"days": 3})
    body = api.get("/api/status").json()
    assert body["comms"] is None and body["isolation_factor"] == 1.0


def test_comms_route_says_the_source(api: TestClient, fake_spice: FakeSpice) -> None:
    body = api.get("/api/comms", params={"epoch": "2026-12-01"}).json()
    assert body["source"] == LABEL and body["from_cache"] is False
    assert body["contrast"] is None


def test_the_spice_route_contrasts_with_the_horizons_cache(
    api: TestClient, tmp_path: Path, fake_spice: FakeSpice
) -> None:
    settings = _settings(tmp_path)
    client = EphemerisClient(settings)
    horizons_day = replace(_window(START), source=SOURCE, one_way_minutes=11.5)
    client.cache.put(
        f"horizons:499:{settings.observer_body}:{START}", horizons_day.to_dict(), source=SOURCE
    )
    body = api.get("/api/spice", params={"epoch": START.isoformat()}).json()
    assert body["contrast_policy"] == spice.CONTRAST_POLICY
    assert body["precedence"].startswith("SPICE primero")
    contrast = body["window"]["contrast"]
    assert contrast["agrees"] is False and contrast["used"] == SOURCE
    assert contrast["one_way_seconds_difference"] == pytest.approx(30.0)
    # Un día sin Horizons en caché: ventana de SPICE sin contraste.
    other = api.get("/api/spice", params={"epoch": "2026-12-01"}).json()
    assert other["window"]["source"] == LABEL and other["window"]["contrast"] is None


def test_the_spice_route_says_why_it_is_not_available(api: TestClient) -> None:
    body = api.get("/api/spice", params={"epoch": "2026-12-01"}).json()
    assert body["available"] is False and body["reason"]
    assert body["target"] == "499" and body["window"] is None
    assert body["window_unavailable"] == body["reason"]
    assert body["license"]["url"] == spice.RULES_URL
    assert [row["name"] for row in body["kernels"]] == ["naif0012.tls", "de432s.bsp"]


def test_spice_is_not_asked_for_a_target_it_does_not_have(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        spice, "availability", lambda s: spice.Availability(True, None, "t", ())
    )
    with pytest.raises(spice.SpiceUnavailable, match="no calcula el objetivo '301'"):
        spice.window(_settings(tmp_path), START, "301")
    topo = _settings(tmp_path).model_copy(update={"observer_body": "000@399"})
    with pytest.raises(spice.SpiceUnavailable, match="observador"):
        spice.window(topo, START, "499")


@pytest.mark.parametrize(
    ("body", "flag"),
    [
        ((-1.0, -0.2, 0.0), "/T"),  # al este del Sol (ascensión recta mayor): va detrás
        ((-1.0, 0.2, 0.0), "/L"),  # al oeste: va delante
        ((1.0, -0.01, 0.0), "/T"),  # cerca de la oposición, al este por poco
        ((1.0, 0.01, 0.0), "/L"),  # y al oeste por poco (el caso del 2027-02-20 en el spike)
    ],
)
def test_the_flag_follows_the_right_ascension_like_horizons(
    body: tuple[float, float, float], flag: str
) -> None:
    """`/T` si el objetivo está al este del Sol en ascensión recta (sale y se pone después)."""
    vectors = {"10": (-1.0, 0.0, 0.0), "4": body}
    fake = SimpleNamespace(spkpos=lambda target, et, frame, corr, obs: (vectors[target], 0.0))
    assert spice._elongation_flag(fake, 0.0, "4", "399") == flag


# --- 5. La descarga solo lleva la URL pública --------------------------------------------------

PRIVATE = ("ellande", "tidus", "emma", "crew", "tripul", "astronaut", "monitoreo", "mission")


def _fetch_module() -> Any:
    import importlib.util

    loaded = importlib.util.spec_from_file_location(
        "fetch_spice_kernels", BACKEND / "scripts" / "fetch_spice_kernels.py"
    )
    assert loaded is not None and loaded.loader is not None
    module = importlib.util.module_from_spec(loaded)
    loaded.loader.exec_module(module)
    return module


@respx.mock
def test_the_download_carries_only_the_public_url(
    tmp_path: Path, kernels: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetch = _fetch_module()
    content = b"DAF/SPK de prueba"
    kernel = _pin(tmp_path, {"de-prueba.bsp": content})[0]
    route = respx.get(kernel.url).mock(return_value=httpx.Response(200, content=content))
    fetch.download(_settings(tmp_path, offline=False), kernel, kernels)
    assert (kernels / kernel.name).read_bytes() == content
    assert route.call_count == 1
    request = route.calls[0].request
    assert request.method == "GET" and request.url.host == spice.NAIF_HOST
    assert request.url.query == b"" and request.content == b""
    # Ninguna cabecera, ni la URL, lleva nada de la tripulación, del usuario o del proyecto.
    seen = " ".join([str(request.url), *(f"{k}: {v}" for k, v in request.headers.items())])
    for word in PRIVATE:
        assert word not in seen.lower(), word
    assert request.headers["user-agent"].startswith("python-httpx/")
    assert "cookie" not in request.headers and "authorization" not in request.headers
    audit = (tmp_path / "cache" / "egress").glob("audit-*.jsonl")
    lines = [json.loads(line) for path in audit for line in path.read_text("utf-8").splitlines()]
    assert lines[-1]["purpose"] == spice.PURPOSE and lines[-1]["verdict"] == "allow"


@respx.mock
def test_a_download_that_is_not_the_pinned_kernel_is_not_kept(
    tmp_path: Path, kernels: Path
) -> None:
    fetch = _fetch_module()
    kernel = _pin(tmp_path, {"de-prueba.bsp": b"el bueno"})[0]
    respx.get(kernel.url).mock(return_value=httpx.Response(200, content=b"el malo!"))
    with pytest.raises(fetch.IntegrityError):
        fetch.download(_settings(tmp_path, offline=False), kernel, kernels)
    assert list(kernels.iterdir()) == []


@respx.mock
def test_offline_the_download_does_not_go_out(tmp_path: Path, kernels: Path) -> None:
    fetch = _fetch_module()
    kernel = _pin(tmp_path, {"de-prueba.bsp": b"x"})[0]
    route = respx.get(kernel.url)
    with pytest.raises(egress.EgressBlocked):
        fetch.download(_settings(tmp_path, offline=True), kernel, kernels)
    assert route.call_count == 0 and list(kernels.iterdir()) == []


# --- 6. La geometría, con un núcleo diminuto hecho aquí ---------------------------------------

AU = spice.AU_KM
# Cuerpos quietos respecto al baricentro del sistema solar: el Sol en el origen, la Tierra a 1 UA
# en +X y el baricentro de Marte a 1,5 UA en +Y. Quietos, ni el tiempo de luz ni la aberración
# mueven las posiciones aparentes, y todo se cuenta a mano.
BODIES = {10: (0.0, 0.0, 0.0), 399: (AU, 0.0, 0.0), 4: (0.0, 1.5 * AU, 0.0)}
# Un LSK de prueba (no es el de NAIF): los segundos intercalares de hoy desde 2017.
TEST_LSK = """KPL/LSK
\\begindata
DELTET/DELTA_T_A = 32.184
DELTET/K = 1.657D-3
DELTET/EB = 1.671D-2
DELTET/M = ( 6.239996D0 1.99096871D-7 )
DELTET/DELTA_AT = ( 37, @2017-JAN-1 )
\\begintext
"""


@pytest.fixture
def tiny_kernels(kernels: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    sp = pytest.importorskip("spiceypy")
    lsk = kernels / "prueba.tls"
    lsk.write_text(TEST_LSK, encoding="ascii")
    sp.kclear()
    sp.furnsh(str(lsk))
    first = sp.str2et("2026-10-31 12:00:00 UTC")
    last = sp.str2et("2026-11-10 12:00:00 UTC")
    sp.kclear()
    spk = kernels / "prueba.bsp"
    handle = sp.spkopn(str(spk), "prueba", 0)
    for body, position in BODIES.items():
        states = [[*position, 0.0, 0.0, 0.0] for _ in range(11)]
        sp.spkw08(handle, body, 0, "J2000", first, last, f"cuerpo {body}", 3, 11, states,
                  first, (last - first) / 10)
    sp.spkcls(handle)
    pinned = _pin(kernels, {"prueba.tls": lsk.read_bytes(), "prueba.bsp": spk.read_bytes()})
    monkeypatch.setattr(spice, "KERNELS", pinned)
    spice._unload()
    return kernels


def test_the_geometry_is_the_one_counted_by_hand(tmp_path: Path, tiny_kernels: Path) -> None:
    window = spice.window(_settings(tmp_path), dt.date(2026, 11, 3), "499")
    distance = math.hypot(1.0, 1.5)
    assert window.distance_au == pytest.approx(distance, rel=1e-9)
    assert window.one_way_minutes == pytest.approx(distance * LIGHT_SECONDS_PER_AU / 60, rel=1e-6)
    assert window.solar_elongation_deg == pytest.approx(math.degrees(math.atan(1.5)), abs=1e-6)
    # Visto desde la Tierra el Sol está en ascensión recta 180° y Marte en 123,7°: al oeste del
    # Sol, sale y se pone antes, va delante.
    assert window.solar_elongation_flag == "/L"
    assert window.source == "SPICE local, núcleo prueba.bsp" and window.target == "499"


def test_the_span_is_the_one_of_the_kernel(tmp_path: Path, tiny_kernels: Path) -> None:
    settings = _settings(tmp_path, days=20)
    assert spice.coverage_span(settings, "499") == (dt.date(2026, 11, 1), dt.date(2026, 11, 10))
    covered, state, _ = spice.covered_days(
        settings, [dt.date(2026, 10, 31), dt.date(2026, 11, 1), dt.date(2026, 11, 11)], "499"
    )
    assert covered == [False, True, False] and state.available


def test_a_day_outside_the_kernel_is_not_a_number(tmp_path: Path, tiny_kernels: Path) -> None:
    with pytest.raises(spice.SpiceUnavailable, match="SPKINSUFFDATA"):
        spice.window(_settings(tmp_path), dt.date(2026, 12, 1), "499")


def test_offline_the_status_day_without_cache_is_calculated(
    tmp_path: Path, tiny_kernels: Path
) -> None:
    payload = EphemerisClient(_settings(tmp_path)).comms_window(dt.date(2026, 11, 3), "499")
    assert payload.source == "SPICE local, núcleo prueba.bsp"
    assert payload.data.round_trip_minutes == pytest.approx(
        2 * math.hypot(1.0, 1.5) * LIGHT_SECONDS_PER_AU / 60, rel=1e-6
    )


@pytest.mark.live
def test_live_the_naif_kernels_are_the_pinned_ones(tmp_path: Path, kernels: Path) -> None:
    """Contrato contra NAIF: los ficheros publicados siguen siendo los fijados (tamaño y huella)."""
    fetch = _fetch_module()
    settings = _settings(tmp_path, offline=False)
    for kernel in spice.KERNELS:
        fetch.download(settings, kernel, kernels)
        assert spice.check_kernel(kernel, kernels / kernel.name) is None


# --- 7. Núcleos empaquetados en la aplicación de escritorio (decisión del usuario, 2026-11-11) --
# El ejecutable congelado lleva los núcleos en `_internal/spice` (`packaging/freeze.py`). Se
# simula el congelado con `sys.frozen` y `sys._MEIPASS`, como los deja PyInstaller.


@pytest.fixture
def frozen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Un «paquete» congelado vacío; devuelve su carpeta de núcleos (aún sin crear)."""
    root = tmp_path / "_internal"
    root.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(root), raising=False)
    return root / spice.BUNDLED_SUBDIR


def _bundle(folder: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[spice.Kernel, ...]:
    """Núcleos de prueba fijados en `folder`, con un `spiceypy` de mentira «instalado»."""
    folder.mkdir()
    pinned = _pin(folder, {"a.tls": b"lsk del paquete", "b.bsp": b"spk del paquete"})
    monkeypatch.setattr(spice, "KERNELS", pinned)
    monkeypatch.setattr(spice, "_spiceypy", lambda: SimpleNamespace(__version__="t"))
    return pinned


def test_outside_the_frozen_app_there_are_no_bundled_kernels() -> None:
    assert spice.bundled_kernel_dir() is None


def test_frozen_the_bundled_kernels_are_found_after_the_configured_folder(
    tmp_path: Path, kernels: Path, frozen: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pinned = _bundle(frozen, monkeypatch)
    settings = _settings(tmp_path)
    assert spice.kernel_sources(settings) == [("configured", kernels), ("bundled", frozen)]
    # La carpeta configurada está vacía: salen del paquete, y se dice.
    state = spice.availability(settings)
    assert state.available and state.origin == "bundled" and state.folder == frozen
    body = state.to_dict()
    assert body["kernel_origin"] == "bundled"
    assert body["kernel_origin_label"] == spice.ORIGINS["bundled"]
    assert "kernel_dir" not in body and str(frozen) not in json.dumps(body)
    assert [row["present"] and row["verified"] for row in body["kernels"]] == [True, True]
    # Con los fijados también en la carpeta configurada, mandan esos.
    for kernel in pinned:
        (kernels / kernel.name).write_bytes((frozen / kernel.name).read_bytes())
    state = spice.availability(settings)
    assert state.available and state.origin == "configured" and state.folder == kernels


def test_frozen_a_tampered_bundled_kernel_is_not_loaded(
    tmp_path: Path, kernels: Path, frozen: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bundle(frozen, monkeypatch)
    (frozen / "b.bsp").write_bytes(b"spk del paquete, cambiado")
    state = spice.availability(_settings(tmp_path))
    assert not state.available and state.origin is None and state.folder == kernels
    assert state.reason is not None
    assert "los empaquetados con la aplicación tampoco valen" in state.reason
    assert "b.bsp mide" in state.reason


def test_frozen_the_day_is_calculated_with_the_bundled_kernels(
    tmp_path: Path, tiny_kernels: Path, frozen: Path
) -> None:
    # Los núcleos diminutos, movidos de la carpeta configurada al paquete: SPICE de verdad.
    frozen.mkdir()
    for path in list(tiny_kernels.iterdir()):
        path.replace(frozen / path.name)
    spice._unload()
    settings = _settings(tmp_path)
    window = spice.window(settings, dt.date(2026, 11, 3), "499")
    assert window.distance_au == pytest.approx(math.hypot(1.0, 1.5), rel=1e-9)
    assert spice.coverage_span(settings, "499") == (dt.date(2026, 11, 1), dt.date(2026, 11, 10))
    assert spice.availability(settings).origin == "bundled"


def test_the_spice_route_says_where_the_kernels_come_from(
    api: TestClient, frozen: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bundle(frozen, monkeypatch)
    body = api.get("/api/spice").json()
    assert body["available"] is True and body["kernel_origin"] == "bundled"
    assert "kernel_dir" not in body and str(frozen) not in json.dumps(body)
    # Sin núcleos en ninguna parte, el origen es nulo, no inventado.
    for path in frozen.iterdir():
        path.unlink()
    body = api.get("/api/spice").json()
    assert body["available"] is False and body["kernel_origin"] is None
