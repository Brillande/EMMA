"""El estado del retardo dicho una vez (`environment/comms_status.py`) y la discrepancia firmada.

Lo que no se puede romper (decisión del usuario, 2026-11-11):

1. **«Sin efemérides» solo cuando de verdad no hay dato.** Con SPICE cubriendo el día, el retardo
   está disponible aunque Horizons no tenga caché, y se dice la fuente. Un perfil sin objetivo de
   efemérides «no aplica»: no es un dato que falte.
2. **Una discrepancia SPICE-Horizons se avisa y se firma**: el aviso en `/api/status`, y un solo
   asiento `ephemeris-discrepancy` por día aunque el estado se pida muchas veces. Coincidiendo,
   nada.
3. **El corte de Tierra se respeta**: con `until` no se firma nada, y solo cuenta lo firmado hasta
   él.
4. **No es clínico**: el asiento no mueve niveles ni alertas.

Sin red (invariante 3): Horizons y SPICE se sustituyen como en `test_spice.py`.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from astroquery.jplhorizons import HorizonsClass
from fastapi.testclient import TestClient

from app.api.routes import EPHEMERIS_SIGNER, _is_reserved_source, new_store, reset_store
from app.core.config import get_settings
from app.core.storage import EPHEMERIS_DISCREPANCY_ENTRY_TYPE, ObservationStore
from app.environment import comms_status, ephemeris_coverage, spice
from app.environment.ephemeris import SOURCE
from app.main import app
from tests.test_spice import LABEL, START, FakeSpice, Horizons, _horizons_day, _settings


@pytest.fixture
def fake_spice(monkeypatch: pytest.MonkeyPatch) -> FakeSpice:
    """SPICE «disponible» que calcula un retardo fijo (`test_spice.FakeSpice`)."""
    fake = FakeSpice()
    monkeypatch.setattr(spice, "window", fake.window)
    return fake


@pytest.fixture
def horizons(monkeypatch: pytest.MonkeyPatch) -> Horizons:
    """Horizons sin salir a la red (`test_spice.Horizons`)."""
    fake = Horizons()
    monkeypatch.setattr(
        HorizonsClass, "_request",
        lambda self, method, url, **kwargs: fake.request(self, method, url, **kwargs),
    )
    return fake


@pytest.fixture
def store() -> Iterator[ObservationStore]:
    store = new_store()
    reset_store(store)
    yield store
    reset_store(None)


def _client(tmp_path: Path, **over: Any) -> TestClient:
    settings = _settings(tmp_path, days=180).model_copy(update=over)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


@pytest.fixture
def api(tmp_path: Path, store: ObservationStore) -> Iterator[TestClient]:
    client = _client(tmp_path)
    client.post("/api/simulate", params={"days": 3})
    yield client
    app.dependency_overrides.clear()


def _status(api: TestClient, **params: str) -> dict[str, Any]:
    response = api.get("/api/status", params={"epoch": START.isoformat(), **params})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _discrepant(tmp_path: Path, fake_spice: FakeSpice) -> None:
    reference = _horizons_day(tmp_path)
    # 0,2 s de tiempo de luz: por encima del error declarado (0,1 s).
    fake_spice.windows[START] = replace(
        reference, source=LABEL, one_way_minutes=reference.one_way_minutes + 0.2 / 60,
    )


def _signed(store: ObservationStore) -> list[Any]:
    return [
        entry for entry in store.ledger.entries
        if entry.entry_type == EPHEMERIS_DISCREPANCY_ENTRY_TYPE
    ]


def test_spice_covering_the_day_without_horizons_cache_is_available(
    api: TestClient, fake_spice: FakeSpice
) -> None:
    said = _status(api)["comms_status"]
    assert said["state"] == comms_status.AVAILABLE
    assert said["source"] == comms_status.SPICE
    assert said["source_text"] == "calculado en local (SPICE)"
    assert said["discrepancy"] is None
    assert "Sin efemérides" not in said["word"]


def test_without_spice_cache_or_network_it_is_missing(api: TestClient) -> None:
    said = _status(api)["comms_status"]
    assert said["state"] == comms_status.MISSING
    assert said["word"] == "Sin efemérides"
    assert said["source"] is None and said["discrepancy"] is None


def test_from_the_horizons_cache_the_source_is_horizons(
    tmp_path: Path, api: TestClient, horizons: Horizons
) -> None:
    _horizons_day(tmp_path)
    said = _status(api)["comms_status"]
    assert said["state"] == comms_status.AVAILABLE
    assert said["source"] == comms_status.HORIZONS and said["source_text"] == SOURCE


def test_a_profile_without_target_is_not_applicable(
    tmp_path: Path, store: ObservationStore, fake_spice: FakeSpice
) -> None:
    client = _client(tmp_path, mission_profile="leo")
    try:
        client.post("/api/simulate", params={"days": 3})
        body = _status(client)
    finally:
        app.dependency_overrides.clear()
    said = body["comms_status"]
    assert said["state"] == comms_status.NOT_APPLICABLE
    assert said["word"] == "No aplica" and "Sin efemérides" not in said["text"]
    assert body["comms"] is None
    assert fake_spice.asked == []  # sin objetivo no se calcula nada


def test_a_discrepancy_is_said_and_signed_once(
    tmp_path: Path, api: TestClient, store: ObservationStore, horizons: Horizons,
    fake_spice: FakeSpice,
) -> None:
    _discrepant(tmp_path, fake_spice)
    first = _status(api)
    for _ in range(3):
        again = _status(api)
    said = first["comms_status"]
    assert said["state"] == comms_status.AVAILABLE and said["source"] == comms_status.HORIZONS
    discrepancy = said["discrepancy"]
    assert discrepancy is not None and discrepancy["word"] == comms_status.DISCREPANCY_WORD
    assert "discrepa" in discrepancy["text"] and discrepancy["epoch"] == START.isoformat()
    assert discrepancy["used"] == SOURCE
    entries = _signed(store)
    assert len(entries) == 1  # uno por día de efeméride, no uno por consulta
    entry = entries[0]
    assert entry.signer == EPHEMERIS_SIGNER
    payload = entry.payload
    assert payload["epoch"] == START.isoformat() and payload["target"] == "499"
    assert payload["local"] == LABEL and payload["reference"] == SOURCE
    assert payload["used"] == SOURCE
    assert float(payload["one_way_seconds_difference"]) == pytest.approx(0.2, abs=1e-6)
    assert float(payload["one_way_seconds_tolerance"]) == pytest.approx(0.1)
    assert float(payload["elongation_deg_tolerance"]) == pytest.approx(0.01)
    assert discrepancy["signed"] == {
        "ledger_index": entry.index, "recorded": entry.recorded.isoformat(),
    }
    assert again["comms_status"]["discrepancy"]["signed"] == discrepancy["signed"]
    # No es clínico: nada de lo que decide cambia por haberlo firmado.
    for key in ("overall_level", "isolation_factor", "domains", "alerts"):
        assert again[key] == first[key]
    assert store.verify_integrity().ok


def test_an_agreeing_contrast_signs_nothing(
    tmp_path: Path, api: TestClient, store: ObservationStore, horizons: Horizons,
    fake_spice: FakeSpice,
) -> None:
    reference = _horizons_day(tmp_path)
    fake_spice.windows[START] = replace(
        reference, source=LABEL, one_way_minutes=reference.one_way_minutes + 0.05 / 60,
    )
    said = _status(api)["comms_status"]
    assert said["source"] == comms_status.SPICE and said["discrepancy"] is None
    assert _signed(store) == []


def test_the_ground_cut_does_not_sign_and_sees_only_what_was_signed_before_it(
    tmp_path: Path, api: TestClient, store: ObservationStore, horizons: Horizons,
    fake_spice: FakeSpice,
) -> None:
    _discrepant(tmp_path, fake_spice)
    later = (dt.datetime.now(dt.UTC) + dt.timedelta(days=1)).isoformat()
    ground = _status(api, until=later)["comms_status"]["discrepancy"]
    assert ground is not None and ground["signed"] is None
    assert _signed(store) == []  # Tierra no firma
    before = dt.datetime.now(dt.UTC)
    _status(api)
    assert len(_signed(store)) == 1
    earlier = (before - dt.timedelta(seconds=1)).isoformat()
    assert _status(api, until=earlier)["comms_status"]["discrepancy"]["signed"] is None
    seen = _status(api, until=later)["comms_status"]["discrepancy"]["signed"]
    assert seen is not None and seen["ledger_index"] == _signed(store)[0].index
    assert len(_signed(store)) == 1


def test_the_signer_is_reserved() -> None:
    assert _is_reserved_source(EPHEMERIS_SIGNER)


def test_a_malformed_discrepancy_is_not_signed(store: ObservationStore) -> None:
    from app.api.routes import identity_for

    with pytest.raises(ValueError):
        store.record_ephemeris_discrepancy({"epoch": "2026-11-01"}, identity_for(EPHEMERIS_SIGNER))
    assert _signed(store) == []


def test_the_coverage_says_the_offline_truth_of_the_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin caché de Horizons y con SPICE cubriendo, el día del estado no es «sin efemérides»."""
    settings = _settings(tmp_path, days=4)
    span = (START + dt.timedelta(days=1), START + dt.timedelta(days=10))
    state = spice.Availability(True, None, "t", ())
    monkeypatch.setattr(
        spice, "covered_days",
        lambda s, days, target: ([span[0] <= d <= span[1] for d in days], state, span),
    )
    later = START + dt.timedelta(days=2)
    covered = ephemeris_coverage.coverage(settings, target="499", day=later)
    assert covered["state"] == ephemeris_coverage.NONE  # la caché de Horizons, vacía
    assert covered["offline_state"] == ephemeris_coverage.PARTIAL
    day = covered["day"]
    assert day["covered"] is False and day["offline_covered"] is True
    assert day["served_by"] == ephemeris_coverage.SPICE_SERVED
    assert day["served_text"] == "calculado en local (SPICE)"
    alone = ephemeris_coverage.coverage(settings, target="499", day=START)
    assert alone["day"]["offline_covered"] is False and alone["day"]["served_by"] is None
    everything = (START, START + dt.timedelta(days=10))
    monkeypatch.setattr(
        spice, "covered_days",
        lambda s, days, target: ([True for _ in days], state, everything),
    )
    full = ephemeris_coverage.coverage(settings, target="499", day=START)
    assert full["offline_state"] == ephemeris_coverage.COMPLETE
