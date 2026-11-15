"""La historia de las alertas ya cerradas, recalculada (especificación §3 `Alert`, §10).

Qué fijan estas pruebas:
- que los pasos contiguos por encima de nominal se juntan en un episodio con su nivel máximo, y
  que un paso nominal en medio parte dos episodios;
- que la respuesta dice siempre lo que es (un recálculo de hoy, con las reglas de hoy) y lo que
  no es, y declara su tope y lo que quedó sin mirar;
- que el paso actual es el del estado y el anterior es el de `_previous_levels`: el mismo motor;
- que respeta `until` y el sujeto, y pone al lado lo firmado sin mezclarlo;
- y las que importan (invariantes 4 y 5): pedir la historia no escribe ningún asiento —tampoco
  instantáneas de predicción— y `/api/status` devuelve lo mismo antes y después.
"""

import datetime as dt
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import timeline
from app.analysis import alert_history
from app.analysis.alert_history import Step, attach_signed, bounds, describe, episodes, walk
from app.analysis.baseline import Baseline, Deviation, Severity, SeverityBasis
from app.analysis.risk import RiskEngine, RiskLevel
from app.api import alert_history as api_history
from app.api import routes
from app.api.routes import get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.core.versioning import rules_version
from app.environment.donki import EventType, SolarEvent
from app.environment.donki import Severity as SolarSeverity
from app.ingest.codes import Domain
from app.main import app
from app.text_guard import check

T0 = dt.datetime(2026, 12, 1, 12, 0, tzinfo=dt.UTC)
WINDOW = dt.timedelta(days=2)
N, W, C, K = RiskLevel.NOMINAL, RiskLevel.WATCH, RiskLevel.CONCERN, RiskLevel.CRITICAL


def _steps(series: dict[Domain, list[RiskLevel]]) -> list[Step]:
    """Pasos a partir de niveles escritos del más reciente (índice 0) al más antiguo."""
    count = len(next(iter(series.values())))
    return [
        Step(index, T0 - (index + 1) * WINDOW, T0 - index * WINDOW,
             {domain: levels[index] for domain, levels in series.items()})
        for index in range(count)
    ]


# --------------------------------------------------------------------------- #
# El cálculo, sin API
# --------------------------------------------------------------------------- #


def test_steps_go_back_to_the_first_reading_and_no_further() -> None:
    found = bounds(T0, T0 - dt.timedelta(days=5), WINDOW)
    assert found == [
        (T0 - dt.timedelta(days=2), T0),
        (T0 - dt.timedelta(days=4), T0 - dt.timedelta(days=2)),
        (T0 - dt.timedelta(days=6), T0 - dt.timedelta(days=4)),
    ]


def test_steps_stop_at_the_cap() -> None:
    found = bounds(T0, T0 - dt.timedelta(days=400), WINDOW, max_steps=4)
    assert len(found) == 4
    assert len(bounds(T0, T0 - dt.timedelta(days=400), WINDOW)) == alert_history.MAX_STEPS


def test_walk_asks_the_engine_once_per_step() -> None:
    asked: list[tuple[dt.datetime, dt.datetime]] = []

    def level_at(start: dt.datetime, end: dt.datetime) -> dict[Domain, RiskLevel]:
        asked.append((start, end))
        return {Domain.BEHAVIORAL: W}

    steps = walk(T0, T0 - dt.timedelta(days=3), WINDOW, level_at)
    assert asked == bounds(T0, T0 - dt.timedelta(days=3), WINDOW)
    assert [step.index for step in steps] == [0, 1]
    assert all(step.levels == {Domain.BEHAVIORAL: W} for step in steps)


def test_contiguous_steps_join_and_a_nominal_step_splits() -> None:
    # Del más reciente al más antiguo: N, W, C, N, W, N
    steps = _steps({Domain.BEHAVIORAL: [N, W, C, N, W, N]})
    found = episodes(steps, examined_all=True)

    assert [item["steps"] for item in found] == [2, 1]
    recent, old = found
    assert recent["peak_level"] == "concern" and recent["peak_level_display"] == C.label
    assert recent["first_step_start"] == (T0 - 3 * WINDOW).isoformat()
    assert recent["last_step_end"] == (T0 - WINDOW).isoformat()
    assert [level["level"] for level in recent["levels"]] == ["concern", "watch"]
    assert old["peak_level"] == "watch"
    assert not recent["open"] and not old["open"]
    assert not recent["start_unknown"] and not old["start_unknown"]
    assert recent["id"] != old["id"]


def test_an_episode_touching_the_current_step_is_open() -> None:
    found = episodes(_steps({Domain.IMMUNE: [K, W, N]}), examined_all=True)
    assert len(found) == 1
    assert found[0]["open"] and found[0]["peak_level"] == "critical"
    assert found[0]["state_display"] == "sigue abierto"


def test_an_episode_at_the_horizon_does_not_claim_a_start() -> None:
    steps = _steps({Domain.IMMUNE: [N, W, W]})
    cut = episodes(steps, examined_all=False)[0]
    assert cut["start_unknown"] is True
    assert cut["start_note"] == alert_history.START_UNKNOWN and check(cut["start_note"]) == []
    assert episodes(steps, examined_all=True)[0]["start_note"] is None
    # Si se miró toda la serie, el primer paso sí es el principio.
    assert episodes(steps, examined_all=True)[0]["start_unknown"] is False


def test_every_domain_keeps_its_own_episodes() -> None:
    steps = _steps({Domain.IMMUNE: [N, W, N], Domain.BONE: [N, W, W]})
    found = episodes(steps, examined_all=True)
    assert {item["domain"]: item["steps"] for item in found} == {"immune": 1, "bone": 2}


def test_the_answer_says_what_it_is_and_what_it_is_not() -> None:
    steps = _steps({Domain.BEHAVIORAL: [N, W, N]})
    payload = describe(steps, steps[-1].start, WINDOW, "reglas@abc")

    assert payload["label"] == "Recalculado con las reglas de hoy"
    assert payload["rules_version"] == "reglas@abc"
    text = " ".join(payload["basis"])
    assert "reglas de hoy" in text and "No es lo que el sistema enseñó entonces" in text
    assert "no en un instante" in text
    assert "asientos firmados" in text
    assert "No se guarda ni se firma" in text
    assert payload["complete"] is True
    assert "toda la serie" in payload["coverage"]
    assert payload["max_steps"] == alert_history.MAX_STEPS
    assert "diseño de EMMA" in payload["max_steps_basis"]
    assert payload["none_display"] is None
    # Invariante 7: nada de esto suena a orden ni a diagnóstico.
    for sentence in [*payload["basis"], payload["coverage"], payload["label"]]:
        assert check(sentence) == [], sentence


def test_what_was_left_unexamined_is_declared() -> None:
    steps = _steps({Domain.BEHAVIORAL: [N, N, N]})
    payload = describe(steps, T0 - dt.timedelta(days=90), WINDOW, "reglas@abc", max_steps=3)

    assert payload["complete"] is False
    assert "últimos 6 días" in payload["coverage"]
    assert "antes de eso no se ha recalculado" in payload["coverage"]
    assert payload["examined_from"] == (T0 - 3 * WINDOW).isoformat()
    assert payload["first_reading"] == (T0 - dt.timedelta(days=90)).isoformat()
    assert payload["max_steps"] == 3
    assert payload["episodes"] == []
    assert payload["none_display"] and check(payload["none_display"]) == []


def test_signed_entries_sit_beside_their_episode_only() -> None:
    found = episodes(_steps({Domain.BEHAVIORAL: [N, W, N, W, N]}), examined_all=True)
    recent, old = found

    def entry(index: int, domain: str, at: dt.datetime) -> dict[str, Any]:
        return {"ledger_index": index, "kind": "acknowledgement", "kind_display": "x",
                "domain": domain, "by": "CMO", "reference_time": at.isoformat()}

    inside_recent = T0 - WINDOW - dt.timedelta(hours=3)
    attach_signed(found, [
        entry(9, "behavioral", inside_recent),
        entry(7, "behavioral", inside_recent),
        entry(8, "immune", inside_recent),  # otro dominio
        entry(6, "behavioral", T0 - 2 * WINDOW - dt.timedelta(hours=3)),  # paso nominal
    ])
    assert [item["ledger_index"] for item in recent["signed"]] == [7, 9]
    assert old["signed"] == []
    # Lo firmado va aparte: no cambia nada del episodio.
    assert recent["peak_level"] == "watch" and recent["steps"] == 1


# --------------------------------------------------------------------------- #
# La ruta, contra el motor
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    """Cuarenta días con evento de partículas: deja episodios cerrados y alertas activas."""
    cache: Path = tmp_path_factory.mktemp("cache")
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=cache, offline=True)
    client = TestClient(app)
    response = client.post("/api/simulate", params={"scenario": "spe-event", "days": 40})
    assert response.status_code == 201
    yield client
    app.dependency_overrides.clear()
    reset_store(None)


def _entry_types() -> list[str]:
    return [entry["entry_type"] for entry in get_store().audit_trail(limit=10**9)]


def test_asking_for_history_writes_nothing_not_even_snapshots(seeded: TestClient) -> None:
    """Invariante 4. Va la primera: el almacén aún no tiene instantáneas de predicción, así
    que si el recálculo las disparase se vería aquí."""
    store = get_store()
    before = len(store.ledger)
    assert store.prediction_snapshots("crew-01") == []

    assert seeded.get("/api/alerts/history").status_code == 200
    assert seeded.get("/api/alerts/history", params={"until": T_CUT.isoformat()}).status_code == 200

    assert len(store.ledger) == before
    assert store.prediction_snapshots("crew-01") == []

    # Y con el estado ya consultado (que sí firma instantáneas), tampoco añade ninguna.
    seeded.get("/api/status")
    after_status = len(store.ledger)
    types = _entry_types()
    assert after_status > before, "la consulta de estado firma sus instantáneas"
    seeded.get("/api/alerts/history")
    assert len(store.ledger) == after_status
    assert _entry_types() == types


T_CUT = dt.datetime(2026, 11, 25, 23, 0, tzinfo=dt.UTC)


def test_status_is_identical_with_and_without_the_history(seeded: TestClient) -> None:
    """Invariante 5: niveles, alertas y todo lo demás de `/api/status`, byte a byte."""
    seeded.get("/api/status")  # deja firmadas las instantáneas del día
    before = seeded.get("/api/status").json()
    cut_before = seeded.get("/api/status", params={"until": T_CUT.isoformat()}).json()

    seeded.get("/api/alerts/history")
    seeded.get("/api/alerts/history", params={"until": T_CUT.isoformat()})

    assert seeded.get("/api/status").json() == before
    assert seeded.get("/api/status", params={"until": T_CUT.isoformat()}).json() == cut_before
    assert before["alerts"], "el escenario tiene alertas activas que comparar"


def test_the_current_step_is_the_status_and_open_episodes_are_its_alerts(
    seeded: TestClient,
) -> None:
    status = seeded.get("/api/status").json()
    history = seeded.get("/api/alerts/history").json()

    open_now = {item["domain"]: item["levels"][-1]["level"]
                for item in history["episodes"] if item["open"]}
    assert open_now == {alert["domain"]: alert["level"] for alert in status["alerts"]}
    assert history["examined_until"] == status["data"]["reference_time"]
    assert history["rules_version"] == status["rules_version"] == rules_version()
    assert history["window_hours"] == status["data"]["deviation_window_days"] * 24


def test_a_past_step_is_what_the_engine_says_for_that_window(seeded: TestClient) -> None:
    """El paso anterior al actual, sin evento solar ni dosis, es `_previous_levels`: el mismo
    motor, llamado y no copiado."""
    settings = Settings(offline=True)
    assessed = routes._assess(settings, get_store(), "crew-01", None, None, None)
    assert assessed.solar_events == [] and not assessed.cumulative_dose_msv
    level_at = api_history._level_at(settings, assessed)
    window = routes.CURRENT_WINDOW

    current = level_at(assessed.latest - window, assessed.latest)
    assert current == {d: risk.level for d, risk in assessed.status.domains.items()}

    previous, cutoff = routes._previous_levels(settings, assessed)
    assert level_at(cutoff - window, cutoff) == previous


def test_the_scenario_leaves_closed_episodes_and_says_so(seeded: TestClient) -> None:
    history = seeded.get("/api/alerts/history").json()

    closed = [item for item in history["episodes"] if not item["open"]]
    assert closed, "cuarenta días dejan al menos un episodio que empezó y terminó"
    for item in closed:
        assert item["state_display"] == "cerrado"
        assert item["last_step_end"] < history["examined_until"]
        assert item["first_step_start"] < item["last_step_end"]
        assert item["peak_level"] != "nominal"
        assert len(item["levels"]) == item["steps"]
    assert history["label"] == alert_history.LABEL
    assert history["complete"] is True and history["steps_examined"] == 20
    assert any("sin eventos solares" in line for line in history["basis"])
    for sentence in [*history["basis"], history["coverage"]]:
        assert check(sentence) == [], sentence


def test_the_cap_is_applied_and_declared(
    seeded: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(alert_history, "MAX_STEPS", 5)
    history = seeded.get("/api/alerts/history").json()

    assert history["steps_examined"] == 5 and history["max_steps"] == 5
    assert history["complete"] is False
    assert "últimos 10 días" in history["coverage"]
    assert "antes de eso no se ha recalculado" in history["coverage"]
    assert history["first_reading"] < history["examined_from"]
    oldest = [item for item in history["episodes"]
              if item["first_step_start"] == history["examined_from"]]
    assert oldest and all(item["start_unknown"] for item in oldest)


def test_until_gives_only_what_ground_has(seeded: TestClient) -> None:
    full = seeded.get("/api/alerts/history").json()
    cut = seeded.get("/api/alerts/history", params={"until": T_CUT.isoformat()}).json()

    assert cut["until"] == T_CUT.isoformat()
    assert cut["examined_until"] <= T_CUT.isoformat() < full["examined_until"]
    assert all(item["last_step_end"] <= cut["examined_until"] for item in cut["episodes"])
    status = seeded.get("/api/status", params={"until": T_CUT.isoformat()}).json()
    assert {item["domain"] for item in cut["episodes"] if item["open"]} == {
        alert["domain"] for alert in status["alerts"]
    }


def test_until_without_timezone_and_unknown_subject_are_refused(seeded: TestClient) -> None:
    naive = seeded.get("/api/alerts/history", params={"until": "2026-11-25T23:00:00"})
    assert naive.status_code == 422
    assert seeded.get("/api/alerts/history", params={"subject": "nadie"}).status_code == 404


def test_a_past_step_only_sees_the_deviations_of_its_own_window() -> None:
    """Un paso pasado es su ventana y nada más, como el estado: con todo lo anterior dentro, un
    episodio no terminaría nunca."""
    reference = Baseline(
        key="pvt-mean-rt", center=50.0, spread=5.0, samples=200,
        sorted_values=tuple(float(value) for value in range(40, 61)),
    )
    old_start = T0 - 3 * WINDOW
    deviations = [
        Deviation(
            subject="crew-01", key="pvt-mean-rt", value=70.0 + hour,
            effective=old_start + dt.timedelta(hours=hour), z_score=3.0,
            severity=Severity.MODERATE, direction="high", baseline=reference,
            used_population_range=False, basis=SeverityBasis.PERSONAL_PERCENTILE,
        )
        for hour in range(10)
    ]
    settings = Settings(offline=True)
    engine = RiskEngine(dose_limit_msv=settings.career_dose_limit_msv)
    assessed = routes._Assessment(
        status=engine.assess(subject="crew-01", deviations=[]), observations=[], latest=T0,
        ignored={}, deviations=deviations, trends={}, cumulative_dose_msv=None,
        dose_source=None, comms_window=None, comms_age=None, solar_age=None, solar_events=[],
    )
    level_at = api_history._level_at(settings, assessed)

    assert level_at(old_start, old_start + WINDOW)[Domain.BEHAVIORAL] is not N
    assert level_at(old_start + WINDOW, old_start + 2 * WINDOW)[Domain.BEHAVIORAL] is N
    assert level_at(old_start - WINDOW, old_start)[Domain.BEHAVIORAL] is N


class _SignedOnly:
    """Un almacén que solo tiene lo firmado sobre alertas: lo que lee `_signed`."""

    def __init__(self, recorded: dt.datetime) -> None:
        base = {"domain": "behavioral", "level": "watch", "recorded": recorded.isoformat(),
                "reference_time": (T0 - dt.timedelta(days=1)).isoformat()}
        self._acks = [
            {**base, "ledger_index": 1, "signer": routes.CONSOLE_IDENTITY, "acknowledged_by": "A"},
            # Firmado con la clave de un wearable: no cuenta, como en el estado.
            {**base, "ledger_index": 2, "signer": "wearable-01", "acknowledged_by": "B"},
        ]
        self._states = [
            {**base, "ledger_index": 3, "signer": routes.CONSOLE_IDENTITY, "state": "resuelto",
             "declared_by": "C"},
        ]
        self._changes = [
            {**base, "ledger_index": 4, "signer": routes.CONSOLE_IDENTITY, "action": "suppress",
             "until": (T0 - dt.timedelta(hours=20)).isoformat(), "requested_by": "D"},
            # Treinta días de supresión: la API no lo habría aceptado, y no se respeta.
            {**base, "ledger_index": 5, "signer": routes.CONSOLE_IDENTITY, "action": "suppress",
             "until": (T0 + dt.timedelta(days=30)).isoformat(), "requested_by": "E"},
        ]

    def acknowledgements(self, subject: str) -> list[dict[str, Any]]:
        return self._acks

    def alert_resolutions(self, subject: str) -> list[dict[str, Any]]:
        return self._states

    def annunciation_changes(self, subject: str) -> list[dict[str, Any]]:
        return self._changes

    def alert_dismissals(self, subject: str) -> list[dict[str, Any]]:
        base = {"domain": "behavioral", "level": "watch", "recorded": self._acks[0]["recorded"],
                "reference_time": self._acks[0]["reference_time"],
                "signer": routes.CONSOLE_IDENTITY, "declared_by": "F"}
        return [
            {**base, "ledger_index": 6, "reason": "sensor_artifact", "note": ""},
            # «Otro» sin nota: la API no lo habría aceptado, y no se enseña.
            {**base, "ledger_index": 7, "reason": "other", "note": ""},
        ]


def test_which_signatures_count_is_decided_as_in_the_status() -> None:
    store: Any = _SignedOnly(recorded=T0)

    found = api_history._signed(store, "crew-01", None)
    assert [(item["ledger_index"], item["kind"], item["by"]) for item in found] == [
        (1, "acknowledgement", "A"), (3, "resolution", "C"), (6, "dismissal", "F"),
        (4, "annunciation", "D"),
    ]
    assert [item["kind_display"] for item in found] == [
        "alerta reconocida", "alerta declarada resuelta",
        "alerta descartada: artefacto del sensor", "anuncio suprimido",
    ]
    assert all(check(item["kind_display"]) == [] for item in found)
    # Para Tierra, lo firmado después de su corte todavía no existe.
    assert api_history._signed(store, "crew-01", T0 - dt.timedelta(minutes=1)) == []
    assert len(api_history._signed(store, "crew-01", T0)) == 4


# --------------------------------------------------------------------------- #
# La crónica
# --------------------------------------------------------------------------- #


def _chronicle(history: dict[str, Any] | None) -> dict[str, Any]:
    now = timeline.AsOf(T0, "data")
    return timeline.chronicle(
        new_store(), "crew-01", {}, now, dt.date(2026, 11, 1), 180, None, history
    )


def test_the_chronicle_tells_closed_episodes_marked_as_a_recomputation() -> None:
    steps = _steps({Domain.BEHAVIORAL: [W, N, C, W, N], Domain.IMMUNE: [N, N, N, N, N]})
    history = describe(steps, steps[-1].start, WINDOW, "reglas@abc")
    chronicle = _chronicle(history)

    told = [event for event in chronicle["events"] if event["recomputed"]]
    # Un episodio cerrado: su principio y su final. El abierto es la alerta activa: no se repite.
    assert [event["fact"] for event in told] == [
        "recomputed-episode-start", "recomputed-episode-end"
    ]
    start, end = told
    assert start["at"] == (T0 - 4 * WINDOW).isoformat()
    assert end["at"] == (T0 - 2 * WINDOW).isoformat()
    for event in told:
        assert event["que"].startswith("recalculado con las reglas de hoy: ")
        assert Domain.BEHAVIORAL.display in event["que"] and C.label in event["que"]
        assert "no es un asiento firmado" in event["fuente"] and "reglas@abc" in event["fuente"]
        # Sin la insignia de una alerta activa: es historia.
        assert event["level"] is None
        assert event["time_basis"] == "data" and event["recorded"] is None
        assert not event["clave"].startswith("ledger:")
        assert check(event["que"]) == [], event["que"]
    assert start["clave"] != end["clave"]
    assert chronicle["recomputed"] is history
    assert any("recalculado con las reglas de hoy" in line for line in chronicle["lines"])


def test_an_episode_without_a_known_start_does_not_claim_one_in_the_chronicle() -> None:
    steps = _steps({Domain.BEHAVIORAL: [N, W, W]})
    history = describe(steps, T0 - dt.timedelta(days=90), WINDOW, "reglas@abc", max_steps=3)
    start = next(event for event in _chronicle(history)["events"]
                 if event["fact"] == "recomputed-episode-start")
    assert "ya estaba por encima" in start["que"]
    assert "más antiguo recalculado" in start["que"]


def test_without_history_the_chronicle_is_the_one_it_was() -> None:
    chronicle = _chronicle(None)
    assert chronicle["recomputed"] is None
    assert not any(event["recomputed"] for event in chronicle["events"])
    assert chronicle["events"], "las fases de misión se siguen contando"


def test_the_chronicle_route_carries_the_history_and_keeps_signed_facts_apart(
    seeded: TestClient,
) -> None:
    seeded.get("/api/status")  # las instantáneas del día, ya firmadas
    store = get_store()
    before = len(store.ledger)
    chronicle = seeded.get("/api/timeline/chronicle").json()
    assert len(store.ledger) == before

    history = seeded.get("/api/alerts/history").json()
    assert chronicle["recomputed"] == history
    closed = [item for item in history["episodes"] if not item["open"]]
    told = [event for event in chronicle["events"] if event["recomputed"]]
    assert len(told) == 2 * len(closed) > 0
    assert {event["clave"] for event in told} == {
        f"{item['id']}:{edge}" for item in closed for edge in ("start", "end")
    }
    # Lo firmado y lo que dice el estado no llevan la marca.
    assert all(
        not event["recomputed"] for event in chronicle["events"]
        if event["clave"].startswith(("ledger:", "alert-onset:", "level-change:", "phase:"))
    )
    # Para Tierra, la historia es la de su corte.
    cut = seeded.get("/api/timeline/chronicle", params={"until": T_CUT.isoformat()}).json()
    assert cut["recomputed"]["until"] == T_CUT.isoformat()
    assert all(event["at"] <= T_CUT.isoformat() for event in cut["events"] if event["recomputed"])


def test_what_someone_signed_sits_beside_the_episode(seeded: TestClient) -> None:
    """Va la última del módulo: firma un reconocimiento en el almacén compartido."""
    status = seeded.get("/api/status").json()
    alert = status["alerts"][0]
    response = seeded.post("/api/alerts/acknowledge", json={
        "subject": "crew-01", "domain": alert["domain"], "level": alert["level"],
        "reference_time": status["data"]["reference_time"], "acknowledged_by": "CMO Ruiz",
    })
    assert response.status_code == 201, response.text

    history = seeded.get("/api/alerts/history").json()
    episode = next(item for item in history["episodes"]
                   if item["open"] and item["domain"] == alert["domain"])
    assert [(item["kind"], item["by"]) for item in episode["signed"]] == [
        ("acknowledgement", "CMO Ruiz")
    ]
    assert episode["signed"][0]["ledger_index"] == response.json()["ledger_index"]
    # Para Tierra, antes de que se firmara, ese reconocimiento no existe.
    cut = seeded.get("/api/alerts/history", params={"until": T_CUT.isoformat()}).json()
    assert all(item["signed"] == [] for item in cut["episodes"])


# Va al final del fichero: usa su propio almacén (`client`), y esa fixture, al acabar, quita
# el almacén del proceso, que es el que comparten las pruebas de `seeded`.
def test_todays_solar_event_and_todays_dose_are_not_attributed_to_the_past(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con el contexto de hoy en cada paso, un evento solar de hoy o la dosis de hoy darían un
    episodio de radiación tan largo como la historia. El paso actual sí los lleva: es el estado."""
    client.post("/api/simulate", params={"scenario": "nominal", "days": 12})
    quiet = client.get("/api/alerts/history").json()

    def radiation(history: dict[str, Any], is_open: bool) -> list[tuple[str, int, str]]:
        return [(item["id"], item["steps"], item["peak_level"]) for item in history["episodes"]
                if item["domain"] == "radiation" and item["open"] is is_open]

    assert radiation(quiet, True) == []

    event = SolarEvent(
        event_id="SEP-HOY", event_type=EventType.SEP, time=dt.datetime.now(dt.UTC),
        severity=SolarSeverity.SEVERE, instruments=(), linked_event_ids=(), flare_class=None,
        link="",
    )
    monkeypatch.setattr(routes, "_fetch_solar_events", lambda settings: ([event], None))
    stormy = client.get("/api/alerts/history").json()
    [(_, steps, _)] = radiation(stormy, True)
    assert steps == 1, "el evento de hoy solo está en el paso de hoy"
    assert radiation(stormy, False) == radiation(quiet, False)
    monkeypatch.undo()

    # La dosis de carrera, registrada ahora en el límite: crítica hoy, y solo hoy.
    reference = quiet["examined_until"]
    response = client.post("/api/observations", json={
        "key": "cumulative-dose", "value": 600.0, "source": "dosimeter", "effective": reference,
    })
    assert response.status_code == 201, response.text
    dosed = client.get("/api/alerts/history").json()
    [(_, steps, peak)] = radiation(dosed, True)
    assert steps == 1 and peak == "critical"
    assert radiation(dosed, False) == radiation(quiet, False)
