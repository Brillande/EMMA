"""Lo que el estado y la crónica leen del ledger, y que leer menos no cambia lo que dicen.

Por qué existe (decimoquinta ronda, 2026-10-22): con cuatro tripulantes sembrados `/api/status`
tardaba unos 7 s y la crónica unos 10 s. El estado verifica la cadena entera y el disco en cada
consulta, y eso no se toca (`compliance/record-integrity.md`); lo demás eran lecturas repetidas:
las decisiones sobre contramedidas tres veces, las declaraciones de sistemas dos, las tendencias
de la ventana anterior dos veces en la crónica, y la crónica entera rehacía el estado —con su
verificación y su firma de instantáneas de proyección— y luego evaluaba otra vez lo mismo para la
historia recalculada. Medido antes y después en `compliance/hmi-state-of-the-art.md` §5.35.13.

Qué fijan estas pruebas:
- que la crónica no escribe nada, tampoco instantáneas, ni verifica la cadena (eso lo dice el
  estado), y que lee las lecturas una sola vez;
- que lo que la crónica toma del estado (`routes.chronicle_status`) es, campo a campo, lo que
  enseña `/api/status`, a bordo y en varios cortes de Tierra;
- que `/api/status` sigue verificando la integridad en cada consulta y lee cada cosa una vez;
- que las tendencias de lo anterior a un instante solo ven lo anterior, y cada instante las suyas;
- y que el modo anatómico, que no comparte la lectura de sistemas del estado, sigue leyéndolas
  con el corte de Tierra.
"""

import datetime as dt
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient

from app.analysis.trend import trends_by_indicator
from app.api import routes
from app.api.routes import get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.main import app

SCENARIO = {"scenario": "spe-event", "days": 40, "crew_size": 1}


def _counting(
    monkeypatch: pytest.MonkeyPatch, store: Any, *names: str
) -> dict[str, int]:
    """Cuenta las llamadas a esos métodos del almacén, sin cambiar lo que devuelven."""
    calls = dict.fromkeys(names, 0)

    def wrap(name: str, method: Callable[..., Any]) -> Callable[..., Any]:
        def counted(*args: Any, **kwargs: Any) -> Any:
            calls[name] += 1
            return method(*args, **kwargs)

        return counted

    for name in names:
        monkeypatch.setattr(store, name, wrap(name, getattr(store, name)))
    return calls


# --------------------------------------------------------------------------- #
# La crónica no escribe ni repite
# --------------------------------------------------------------------------- #


def test_the_chronicle_writes_nothing_and_reads_the_readings_once(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invariante 4 y §3.18: solo el estado de a bordo firma instantáneas. Va con un almacén
    recién sembrado, sin ningún estado pedido: si la crónica firmara, se vería aquí."""
    assert client.post("/api/simulate", params={**SCENARIO, "days": 14}).status_code == 201
    store = get_store()
    before = len(store.ledger)
    calls = _counting(
        monkeypatch, store, "query", "verify_integrity", "record_prediction_snapshots"
    )

    assert client.get("/api/timeline/chronicle").status_code == 200
    assert len(store.ledger) == before
    assert store.prediction_snapshots("crew-01") == []
    assert calls == {"query": 1, "verify_integrity": 0, "record_prediction_snapshots": 0}

    # El estado sí firma las del día y verifica: la escritura es suya, no de la crónica.
    assert client.get("/api/status").status_code == 200
    assert len(store.ledger) > before
    assert calls["verify_integrity"] == 1


def test_the_status_verifies_every_time_and_reads_each_thing_once(
    decided: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    decided.get("/api/status")  # deja firmadas las instantáneas del día
    store = get_store()
    calls = _counting(
        monkeypatch, store, "query", "verify_integrity", "followup_decisions",
        "system_statuses", "prediction_snapshots", "mission_events", "location_anchors",
        "location_sightings",
    )

    body = decided.get("/api/status").json()
    assert body["alerts"], "el escenario tiene alertas, que leen el contexto de sistemas"
    assert body["data"]["integrity_ok"] is True
    # La verificación no se toca: una por consulta. Lo demás, una lectura por respuesta (las
    # instantáneas se releen solo si se firmó alguna, y hoy ya están firmadas). Los eventos de
    # misión, dos: los del estado y su contexto, y dónde estaba el tripulante (`crew_whereabouts`),
    # que desde el 2026-11-09 lee el estado una vez para `mission.location` y pasa a ese contexto.
    # Las anclas de módulo, una (2026-11-10); sin ninguna declarada, sus lecturas no se leen.
    assert calls == {
        "query": 1, "verify_integrity": 1, "followup_decisions": 1, "system_statuses": 1,
        "prediction_snapshots": 1, "mission_events": 2, "location_anchors": 1,
        "location_sightings": 0,
    }


# --------------------------------------------------------------------------- #
# Lo que la crónica toma del estado es lo que el estado enseña
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def _decided(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[TestClient, Any, Settings]]:
    """Cuarenta días con evento de partículas y una persona que actúa sobre lo que ve."""
    cache: Path = tmp_path_factory.mktemp("cache")
    settings = Settings(cache_dir=cache, offline=True)
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    assert client.post("/api/simulate", params=SCENARIO).status_code == 201
    status = client.get("/api/status").json()
    reference = status["data"]["reference_time"]
    alert = status["alerts"][0]
    assert client.post("/api/alerts/acknowledge", json={
        "domain": alert["domain"], "level": alert["level"], "reference_time": reference,
        "acknowledged_by": "CDR",
    }).status_code == 201
    measure = next(
        item["countermeasure"] for item in status["recommendations"] if item["countermeasure"]
    )
    assert client.post("/api/countermeasures/adopt", json={
        "countermeasure_id": measure["id"], "reference_time": reference, "adopted_by": "CDR",
    }).status_code == 201
    start = dt.datetime.fromisoformat(reference) - dt.timedelta(days=3)
    assert client.post("/api/mission/events", json={
        "kind": "eva", "start": start.isoformat(),
        "end": (start + dt.timedelta(hours=6)).isoformat(), "label": "EVA 1",
        "declared_by": "CDR",
    }).status_code == 201
    yield client, get_store(), settings
    app.dependency_overrides.clear()
    reset_store(None)


@pytest.fixture
def decided(_decided: tuple[TestClient, Any, Settings]) -> TestClient:
    """El almacén y la configuración de `_decided`, puestos otra vez antes de cada prueba: una
    prueba con el `client` de `conftest.py` los sustituye y los quita al acabar."""
    client, store, settings = _decided
    reset_store(store)
    app.dependency_overrides[get_settings] = lambda: settings
    return client


def _settings() -> Settings:
    """La configuración con que responde la API: la misma caché, el mismo contexto externo."""
    settings: Settings = app.dependency_overrides[get_settings]()
    return settings


def _what_the_chronicle_reads(status: dict[str, Any]) -> dict[str, Any]:
    """Del estado, lo que lee `app/timeline.py`; de cada alerta, todo menos contexto y flujo."""
    return {
        "subject": status["subject"],
        "rules_version": status["rules_version"],
        "reference_time": status["data"]["reference_time"],
        "trajectories": {name: item["trajectory"] for name, item in status["domains"].items()},
        "alerts": [
            {
                **{key: value for key, value in alert.items() if key != "detail"},
                "detail": {
                    key: value for key, value in alert["detail"].items()
                    if key not in ("context", "flow")
                },
            }
            for alert in status["alerts"]
        ],
        "followups": status["followups"],
        "events": status["mission"]["events"],
    }


def _chronicle_status(until: dt.datetime | None) -> dict[str, Any]:
    settings = _settings()
    store = get_store()
    assessed = routes._assess(settings, store, "crew-01", None, None, until)
    found: dict[str, Any] = jsonable_encoder(
        routes.chronicle_status(settings, store, "crew-01", until, assessed)
    )
    assert set(found) == {
        "subject", "rules_version", "domains", "alerts", "followups", "mission", "data",
    }
    return found


def test_what_the_chronicle_takes_from_the_status_is_what_the_status_shows(
    decided: TestClient,
) -> None:
    status = decided.get("/api/status").json()
    reference = dt.datetime.fromisoformat(status["data"]["reference_time"])
    shown = _what_the_chronicle_reads(status)
    assert shown == _what_the_chronicle_reads(_chronicle_status(None))
    assert shown["alerts"] and shown["followups"] and shown["events"]
    assert any(alert["acknowledged"] for alert in shown["alerts"])

    # Y en cortes de Tierra, cada dos días hacia atrás, con lo que había en cada uno: al menos
    # tres, y hasta dar con uno en que algún dominio cambió de nivel (su trayectoria se compara).
    compared = moved = 0
    for days in range(0, 40, 2):
        if compared >= 3 and moved:
            break
        cut = reference - dt.timedelta(days=days, hours=1)
        ground = decided.get("/api/status", params={"until": cut.isoformat()})
        if ground.status_code != 200:
            continue
        expected = _what_the_chronicle_reads(ground.json())
        assert expected == _what_the_chronicle_reads(_chronicle_status(cut)), cut
        compared += 1
        moved += sum(1 for item in expected["trajectories"].values() if item)
    assert compared >= 3 and moved, "ningún corte con un cambio de nivel que comparar"


def test_the_chronicle_tells_the_alerts_and_follow_ups_of_the_status(
    decided: TestClient,
) -> None:
    status = decided.get("/api/status").json()
    chronicle = decided.get("/api/timeline/chronicle").json()
    assert chronicle["as_of"] == status["data"]["reference_time"]
    onsets = {event["clave"] for event in chronicle["events"]
              if event["fact"] in ("alert-onset", "alert-active")}
    assert onsets == {
        f"alert-onset:{alert['domain']}:{alert['level']}:"
        f"{alert['detail']['onset'] or 'sin-lectura'}"
        for alert in status["alerts"]
    }


# --------------------------------------------------------------------------- #
# Las tendencias de lo anterior a un instante
# --------------------------------------------------------------------------- #


def test_the_trends_before_an_instant_see_only_what_came_before_and_each_its_own(
    decided: TestClient,
) -> None:
    assessed = routes._assess(_settings(), get_store(), "crew-01", None, None, None)
    recent = assessed.latest - routes.CURRENT_WINDOW
    older = assessed.latest - dt.timedelta(days=12)

    def fresh(end: dt.datetime) -> dict[str, Any]:
        return trends_by_indicator([obs for obs in assessed.observations if obs.effective < end])

    # Que la prueba distinga algo: con todo dentro, o con otro instante, salen otras.
    assert fresh(recent) != fresh(older)
    assert fresh(recent) != trends_by_indicator(assessed.observations)
    assert assessed.trends_before(recent) == fresh(recent)
    assert assessed.trends_before(older) == fresh(older)
    # La segunda vez es la misma respuesta, sin recalcular.
    assert assessed.trends_before(recent) is assessed.trends_before(recent)


# --------------------------------------------------------------------------- #
# El modo anatómico lee los sistemas declarados con su corte
# --------------------------------------------------------------------------- #


def test_the_anatomy_context_reads_the_declared_systems_with_the_ground_cut(
    client: TestClient,
) -> None:
    """`/status` da al contexto las declaraciones que ya leyó para el enlace; el modo anatómico no
    las tiene y el constructor las lee él, con el mismo corte que el resto."""
    client.post("/api/simulate", params={"scenario": "co2-fatigue", "days": 10, "crew_size": 1})
    reference = dt.datetime.fromisoformat(
        client.get("/api/status").json()["data"]["reference_time"]
    )
    assert client.post("/api/habitat/systems/status", json={
        "system": "air-revitalization", "state": "degraded", "at": reference.isoformat(),
        "declared_by": "CDR",
    }).status_code == 201

    def sources(**params: Any) -> set[tuple[str, int]]:
        response = client.get("/api/anatomy/state", params=params)
        assert response.status_code == 200, response.text
        return {
            (source["status"], source["found"])
            for region in response.json()["regions"] if region["context"]
            for source in region["context"]["sources"] if source["kind"] == "system_status"
        }

    on_board = sources()
    assert on_board and on_board <= {("with_data", 0), ("with_data", 1)}
    assert sources(until=(reference - dt.timedelta(hours=1)).isoformat()) == {("no_data", 0)}
