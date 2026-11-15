"""Las distancias por perfil (`environment/distances.py`, `GET /api/distances`), sin red.

Los núcleos SPICE no están en la suite (`conftest._no_local_spice_kernels`): sin ellos todo se
dice «sin dato» con el motivo, no se falla ni se inventa. Con SPICE se finge la medida para probar
dónde entra, no la geometría (la geometría ya se validó contra Horizons en el spike de SPICE).
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.environment import distances, spice
from app.environment.ephemeris import LIGHT_SECONDS_PER_AU, CommsWindow
from app.evidence import mission_profiles

DAY = dt.date(2026, 12, 10)
MOON_KM = 384_400.0
MARS_KM = 164_000_000.0


def _seconds(km: float) -> float:
    return km / spice.AU_KM * LIGHT_SECONDS_PER_AU


@pytest.fixture
def measured(monkeypatch: pytest.MonkeyPatch) -> dict[str, float]:
    """SPICE «disponible» que da una distancia fija por cuerpo, y el retardo de Marte fingido."""
    km = {"301": MOON_KM, "4": MARS_KM}

    def measure(settings: Settings, epoch: dt.date, code: str) -> tuple[float, float]:
        return km[code], _seconds(km[code])

    def window(settings: Settings, epoch: dt.date, target: str) -> CommsWindow:
        return CommsWindow(
            epoch=epoch, distance_au=MARS_KM / spice.AU_KM,
            one_way_minutes=_seconds(MARS_KM) / 60, target=target,
            solar_elongation_deg=80.0, solar_elongation_flag="/L", source=spice.source_label(),
        )

    monkeypatch.setattr(distances, "_measure", measure)
    monkeypatch.setattr(spice, "window", window)
    return km


def test_without_kernels_every_figure_is_missing_with_its_reason(client: TestClient) -> None:
    body = client.get("/api/distances", params={"profile": "mars-transit",
                                                "epoch": DAY.isoformat()}).json()
    assert body["known"] is True
    assert body["spice"]["available"] is False and body["spice"]["reason"]
    for row in body["bodies"]:
        assert row["state"] == distances.MISSING
        assert row["distance_km"] is None and row["one_way_seconds"] is None
        assert row["text"]
    # Marte es su objetivo, pero ni SPICE ni la caché de Horizons: «sin dato», sin salir a la red.
    link = body["earth_link"]
    assert link["state"] == distances.MISSING and link["one_way_seconds"] is None
    assert "no sale a la red" in link["text"]


@pytest.mark.parametrize("profile", ["leo", "cislunar", "lunar-surface"])
def test_a_profile_without_target_says_not_applicable(client: TestClient, profile: str) -> None:
    link = client.get("/api/distances", params={"profile": profile}).json()["earth_link"]
    assert link["state"] == distances.NOT_APPLICABLE
    assert link["text"] == mission_profiles.NO_TARGET_TEXT
    assert link["one_way_seconds"] is None


def test_with_spice_the_bodies_and_the_link_have_figures(
    client: TestClient, measured: dict[str, float]
) -> None:
    body = client.get("/api/distances", params={"profile": "mars-surface",
                                                "epoch": DAY.isoformat()}).json()
    rows = {row["id"]: row for row in body["bodies"]}
    assert rows["moon"]["state"] == distances.AVAILABLE
    assert rows["moon"]["distance_km"] == pytest.approx(MOON_KM)
    assert rows["mars"]["one_way_seconds"] == pytest.approx(_seconds(MARS_KM))
    link = body["earth_link"]
    assert link["state"] == distances.AVAILABLE and link["target"] == "499"
    assert link["distance_km"] == pytest.approx(MARS_KM)
    assert body["crew_place"]["body"] == "mars"


def test_the_lunar_surface_shows_the_moon_but_its_delay_stays_not_applicable(
    client: TestClient, measured: dict[str, float]
) -> None:
    """La distancia Tierra-Luna es geometría: no convierte la Luna en objetivo de efemérides."""
    body = client.get("/api/distances", params={"profile": "lunar-surface"}).json()
    assert body["crew_place"]["body"] == "moon"
    assert body["earth_link"]["state"] == distances.NOT_APPLICABLE
    assert {row["id"]: row["state"] for row in body["bodies"]}["moon"] == distances.AVAILABLE


@pytest.mark.parametrize("profile", ["cislunar", "mars-transit"])
def test_en_route_the_crew_place_is_not_estimated(client: TestClient, profile: str) -> None:
    place = client.get("/api/distances", params={"profile": profile}).json()["crew_place"]
    assert place == {"body": None, "text": distances.EN_ROUTE_TEXT}


def test_a_light_time_that_does_not_match_the_distance_is_not_served(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        distances, "_measure", lambda settings, epoch, code: (MOON_KM, _seconds(MOON_KM) + 5)
    )
    rows = client.get("/api/distances", params={"profile": "leo"}).json()["bodies"]
    assert all(row["state"] == distances.MISSING for row in rows)
    assert "discrepancia" in rows[0]["text"]


def test_an_unknown_profile_is_not_guessed(client: TestClient) -> None:
    body = client.get("/api/distances", params={"profile": "venus"}).json()
    assert body["known"] is False and body["bodies"] == [] and body["earth_link"] is None
    assert "venus" in body["unknown_text"]


def test_without_profile_it_is_the_declared_one(client: TestClient) -> None:
    body = client.get("/api/distances").json()
    assert body["profile"] == body["declared_profile"]


def test_every_profile_of_the_catalog_has_a_declared_place() -> None:
    ids = {item["id"] for item in mission_profiles.catalog()["profiles"]}
    assert set(distances.CREW_PLACE) == ids
    assert {place for place in distances.CREW_PLACE.values() if place} <= set(
        distances.CREW_PLACE_TEXT
    )


def test_neither_analysis_nor_advisor_imports_it() -> None:
    """Descriptivo: no escala el riesgo ni mueve alertas (invariante 5)."""
    root = Path(distances.__file__).resolve().parents[1]
    for folder in ("analysis", "advisor"):
        for path in (root / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    names = [node.module or ""] + [alias.name for alias in node.names]
                    assert not any("distances" in name for name in names), path
                elif isinstance(node, ast.Import):
                    assert not any("distances" in a.name for a in node.names), path
