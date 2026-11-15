"""La interfaz no redacta: niveles, fases, trayectoria y caducidad los da el backend.

Lo que vigilan estas pruebas:

- cada nivel tiene UNA palabra, y CONCERN es «precaución» en el resumen, en los motivos y en la
  insignia (decisión del usuario, 2026-10-09); «preocupación» no vuelve como nombre de nivel;
- `/status` lleva lo que la interfaz antes escribía: la palabra de cada nivel, la tira de fases
  y la frase de la trayectoria;
- la regla de caducidad vive en el backend, con los MISMOS plazos que tenía la interfaz
  (7 d / 6 h / 7 d), y entra en `rules_version`;
- y la que importa (invariante 5): niveles, puntuaciones y alertas son idénticos con otras
  palabras y con otros plazos de caducidad. Esto nombra y rotula; no decide.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import risk, staleness, wording
from app.analysis.recovery_state import trajectories
from app.analysis.risk import RiskLevel
from app.analysis.staleness import STALE_AFTER, ExternalSource, Freshness, describe, freshness
from app.api import routes
from app.api.routes import new_store, reset_store
from app.core import mission
from app.core.cache import CachedPayload
from app.core.config import Settings, get_settings
from app.core.mission import MissionPhase
from app.core.versioning import FINGERPRINTED, fingerprint, rules
from app.environment.ephemeris import CommsWindow
from app.ingest.codes import Domain
from app.main import app

HOUR = 3600
DAY = 24 * HOUR


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _simulate(client: TestClient, scenario: str) -> dict[str, Any]:
    client.post("/api/simulate", params={"scenario": scenario, "days": 40, "crew_size": 1})
    payload: dict[str, Any] = client.get("/api/status").json()
    return payload


# --------------------------------------------------------------------------- #
# Niveles: una palabra, y la dice el backend
# --------------------------------------------------------------------------- #


def test_concern_is_called_precaucion_everywhere_the_backend_names_it() -> None:
    assert RiskLevel.CONCERN.display == "precaución"
    assert RiskLevel.CONCERN.label == "Precaución"
    assert wording.level_labels()["concern"] == "Precaución"


def test_every_level_has_one_word_and_the_label_is_that_word() -> None:
    labels = wording.level_labels()
    assert set(labels) == {str(level) for level in RiskLevel}
    assert len(set(labels.values())) == len(labels)
    for level in RiskLevel:
        # La insignia y la frase usan la misma palabra: solo cambia la mayúscula inicial.
        assert level.label.lower() == level.display.lower()
        assert level.label[0].isupper()


def test_no_python_source_names_a_level_preocupacion() -> None:
    """«preocupación» no puede volver como nombre de nivel por otra puerta.

    Se leen las fuentes de `app/`: la palabra solo puede aparecer en este comentario de
    `risk.py` que cuenta el cambio, nunca en un literal.
    """
    import ast

    root = Path(routes.__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and "preocupaci" in node.value.lower()
            ):
                offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    assert offenders == []


def test_a_concern_status_says_precaucion_in_summary_level_and_drivers(
    client: TestClient,
) -> None:
    status = _simulate(client, "progressive-insomnia")
    concern = [key for key, item in status["domains"].items() if item["level"] == "concern"]
    assert status["overall_level"] == "concern" and concern, "el escenario tiene que dar CONCERN"

    assert status["level_labels"]["concern"] == "Precaución"
    assert "(precaución)" in status["summary"]
    rationales = " ".join(item["rationale"] for item in status["recommendations"])
    assert "(precaución)" in rationales
    assert "preocupaci" not in client.get("/api/status").text.lower()


# --------------------------------------------------------------------------- #
# Fases y trayectoria
# --------------------------------------------------------------------------- #


def test_status_lists_every_phase_in_order_with_the_backend_name(client: TestClient) -> None:
    found = _simulate(client, "nominal")["mission"]
    assert [item["key"] for item in found["phases"]] == [str(phase) for phase in MissionPhase]
    assert [item["display"] for item in found["phases"]] == [p.display for p in MissionPhase]
    # La fase actual es una de la lista, con el mismo nombre que ya daba `phase_display`.
    current = next(item for item in found["phases"] if item["key"] == found["phase"])
    assert current["display"] == found["phase_display"]
    # El nombre que la interfaz acortaba: es el del backend.
    assert MissionPhase.RETURN.display == "preparación del regreso"


def test_phase_list_does_not_depend_on_the_moment() -> None:
    start = dt.date(2026, 1, 1)
    early = mission.context(dt.datetime(2026, 1, 2, tzinfo=dt.UTC), start, 180, "microgravedad")
    late = mission.context(dt.datetime(2026, 9, 2, tzinfo=dt.UTC), start, 180, "microgravedad")
    assert early["phases"] == late["phases"]
    assert early["phase"] != late["phase"]


def _trajectory(before: RiskLevel, now: RiskLevel) -> dict[str, Any] | None:
    found = trajectories(
        {Domain.CARDIOVASCULAR: now},
        {Domain.CARDIOVASCULAR: before},
        dt.datetime(2026, 3, 1, tzinfo=dt.UTC),
    )
    return wording.with_wording(found[str(Domain.CARDIOVASCULAR)])


def test_trajectory_carries_its_words() -> None:
    better = _trajectory(RiskLevel.CONCERN, RiskLevel.NOMINAL)
    worse = _trajectory(RiskLevel.NOMINAL, RiskLevel.CONCERN)
    assert better is not None and worse is not None
    assert better["direction_display"] == "recuperándose"
    assert better["from_level_display"] == "Precaución"
    assert better["display"] == "recuperándose (antes Precaución)"
    assert worse["display"] == "empeorando (antes Nominal)"
    # Lo que ya había sigue igual: solo se añade texto.
    assert better["direction"] == "recovering" and worse["direction"] == "worsening"
    assert "precaución" in better["basis"] and "preocupaci" not in better["basis"]


def test_no_level_change_has_no_trajectory_wording() -> None:
    assert _trajectory(RiskLevel.WATCH, RiskLevel.WATCH) is None


def test_status_trajectory_is_worded_when_a_domain_changed(client: TestClient) -> None:
    status = _simulate(client, "spe-event")
    changed = [item["trajectory"] for item in status["domains"].values() if item["trajectory"]]
    assert changed, "el escenario tiene que cambiar de nivel para que la prueba diga algo"
    for item in changed:
        assert item["direction_display"] == wording.TRAJECTORY_DISPLAY[item["direction"]]
        assert item["from_level_display"] == status["level_labels"][item["from_level"]]
        before = item["from_level_display"]
        assert item["display"] == f"{item['direction_display']} (antes {before})"


# --------------------------------------------------------------------------- #
# Caducidad: la regla vive en el backend, con los mismos plazos
# --------------------------------------------------------------------------- #


def test_thresholds_are_the_ones_the_interface_had() -> None:
    """7 d / 6 h / 7 d, leídos de `frontend/src/lib/staleness.ts` antes de quitarlos de allí."""
    assert {str(key): value.total_seconds() for key, value in STALE_AFTER.items()} == {
        "ephemeris": 7 * DAY,
        "space-weather": 6 * HOUR,
        "dosimetry": 7 * DAY,
    }


@pytest.mark.parametrize("source", list(ExternalSource))
def test_stale_only_past_the_limit(source: ExternalSource) -> None:
    limit = STALE_AFTER[source].total_seconds()
    assert freshness(source, 0) is Freshness.FRESH
    assert freshness(source, limit) is Freshness.FRESH  # justo en el plazo, al día
    assert freshness(source, limit + 1) is Freshness.STALE


def test_space_weather_expires_before_ephemeris() -> None:
    a_bit_over_six_hours = 6 * HOUR + 60
    assert freshness(ExternalSource.SPACE_WEATHER, a_bit_over_six_hours) is Freshness.STALE
    assert freshness(ExternalSource.EPHEMERIS, a_bit_over_six_hours) is Freshness.FRESH


@pytest.mark.parametrize("age", [None, float("nan"), float("inf")])
def test_no_age_is_missing_never_current(age: float | None) -> None:
    found = describe(ExternalSource.EPHEMERIS, age)
    assert found["state"] == "missing"
    assert found["is_current"] is False
    assert found["age_seconds"] is None
    assert found["display"] == "sin dato"


def test_describe_says_the_limit_it_applied() -> None:
    found = describe(ExternalSource.SPACE_WEATHER, 7 * HOUR)
    assert found == {
        "source": "space-weather",
        "state": "stale",
        "display": "caducado",
        "is_current": False,
        "age_seconds": 7 * HOUR,
        "stale_after_seconds": 6 * HOUR,
        "stale_after_display": "6 h",
    }
    assert describe(ExternalSource.EPHEMERIS, 60)["stale_after_display"] == "7 d"
    assert describe(ExternalSource.EPHEMERIS, 60)["is_current"] is True


def test_the_basis_declares_design_without_source() -> None:
    assert "diseño de EMMA, sin fuente" in staleness.BASIS


def test_staleness_thresholds_are_in_the_rules_version(monkeypatch: pytest.MonkeyPatch) -> None:
    assert FINGERPRINTED["app.analysis.staleness"] == ("STALE_AFTER",)
    before = fingerprint(rules())
    monkeypatch.setitem(STALE_AFTER, ExternalSource.SPACE_WEATHER, dt.timedelta(days=6))
    assert fingerprint(rules()) != before


def _mars(age_seconds: int) -> Any:
    window = CommsWindow(
        epoch=dt.date(2026, 10, 1), distance_au=2.5, one_way_minutes=20.8, target="Mars"
    )
    return lambda settings, epoch, target: (window, ("hace un rato", age_seconds))


def test_status_without_external_data_says_missing(client: TestClient) -> None:
    found = _simulate(client, "nominal")["freshness"]
    assert found["comms"]["state"] == found["solar"]["state"] == "missing"
    assert found["comms"]["source"] == "ephemeris"
    assert found["solar"]["source"] == "space-weather"
    assert "diseño de EMMA, sin fuente" in found["basis"]


@pytest.mark.parametrize(
    ("age", "state"), [(6 * DAY, "fresh"), (7 * DAY, "fresh"), (7 * DAY + 1, "stale")]
)
def test_status_says_whether_the_ephemeris_is_stale(
    age: int, state: str, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes, "_fetch_comms", _mars(age))
    status = _simulate(client, "nominal")
    assert status["freshness"]["comms"]["state"] == state
    assert status["freshness"]["comms"]["age_seconds"] == age == status["comms_data_age_seconds"]


@pytest.mark.parametrize(("age_days", "state"), [(6, "fresh"), (8, "stale")])
def test_dose_series_says_whether_the_dosimetry_is_stale(
    age_days: int, state: str, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Dosimetry:
        def __init__(self, settings: Settings) -> None:
            pass

        def dose_series(self, start: dt.date, end: dt.date) -> CachedPayload:
            fetched = dt.datetime.now(dt.UTC) - dt.timedelta(days=age_days)
            return CachedPayload(data=[], fetched_at=fetched, source="prueba", from_cache=True)

    monkeypatch.setattr(routes, "RadLabClient", Dosimetry)
    monkeypatch.setattr(
        routes, "effective_dose",
        lambda data, model: SimpleNamespace(
            to_dict=lambda: {}, hours_covered=1.0, is_measured=False
        ),
    )
    found = client.get(
        "/api/radiation/dose", params={"start": "2022-04-01", "end": "2022-04-02"}
    ).json()
    assert found["freshness"]["source"] == "dosimetry"
    assert found["freshness"]["state"] == state
    assert found["freshness"]["stale_after_display"] == "7 d"
    assert "diseño de EMMA, sin fuente" in found["freshness"]["basis"]


# --------------------------------------------------------------------------- #
# Invariante 5: nada de esto mueve el veredicto
# --------------------------------------------------------------------------- #


def _verdict(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "overall_level": status["overall_level"],
        "domains": {
            key: {"score": item["score"], "level": item["level"]}
            for key, item in status["domains"].items()
        },
        "alerts": [
            {key: alert[key] for key in ("id", "domain", "level", "annunciation", "acknowledged")}
            for alert in status["alerts"]
        ],
        "recommendations": [
            (item["domain"], item["action"], item["urgency"])
            for item in status["recommendations"]
        ],
    }


SCENARIOS = [
    "nominal", "progressive-insomnia", "spe-event", "co2-fatigue", "dehydration", "arrhythmia",
]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_verdict_is_identical_with_other_words_and_other_staleness_limits(
    scenario: str, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Con efemérides de Marte, para que el factor de aislamiento y la caducidad estén en juego.
    monkeypatch.setattr(routes, "_fetch_comms", _mars(3 * DAY))
    full = _simulate(client, scenario)
    assert full["freshness"]["comms"]["state"] == "fresh"
    if scenario != "nominal":
        assert full["alerts"], "el escenario tiene que alertar para que la prueba diga algo"

    # Sin la pieza: todo dato externo caducado al instante y los niveles con otros nombres.
    for source in ExternalSource:
        monkeypatch.setitem(STALE_AFTER, source, dt.timedelta(0))
    for level in RiskLevel:
        monkeypatch.setitem(risk._LEVEL_DISPLAY, level, f"otra-{level}")
    monkeypatch.setattr(routes, "level_labels", lambda: {})
    monkeypatch.setattr(routes, "with_wording", lambda item: item)
    bare = client.get("/api/status").json()

    assert bare["freshness"]["comms"]["state"] == "stale"
    assert bare["level_labels"] == {}
    assert _verdict(bare) == _verdict(full)
