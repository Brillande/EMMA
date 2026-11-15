"""El enlace con Tierra simulado: el corte de Tierra con el enlace caído y lo pendiente de enviar.

Lo que se fija aquí (`core/link_sync.py`, `record-integrity.md` §3.29):

- el corte de Tierra **nunca queda por delante del último instante con enlace** ni del tiempo de
  luz, y crece con el reloj de a bordo: lo retenido aparece de golpe y entero, nunca a saltos;
- la cola cuenta lo de a bordo posterior a la caída, en orden, sin lo que firma Tierra;
- cada cambio es un asiento firmado por la consola, sin repetir el estado ni ir hacia atrás;
- **nada que decide lo lee**: el estado de a bordo y el de Tierra con el mismo corte son idénticos
  antes y después de declararlo (invariante 5), y ni `analysis/`, ni `advisor/`, ni el estado lo
  importan. La declaración del sistema Comunicaciones sigue siendo solo texto.

Sin red (invariante 3): el retardo no sale de las efemérides; el corte por tiempo de luz se pasa
a mano, como lo pasa la consola.
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.api.routes import CONSOLE_IDENTITY, GROUND_IDENTITY, identity_for
from app.core import link_sync
from app.core.storage import LINK_ENTRY_TYPE, LINK_SUBJECT
from tests.test_api import alerting, client, seeded  # noqa: F401 — fixtures

__all__ = ["alerting", "client", "seeded"]

APP = Path(__file__).resolve().parents[1] / "app"
T0 = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.UTC)
HOUR = dt.timedelta(hours=1)
DELAY = dt.timedelta(minutes=12)


def _change(
    index: int, state: str, at: dt.datetime, signer: str = CONSOLE_IDENTITY
) -> dict[str, Any]:
    return {
        "subject": LINK_SUBJECT, "state": state, "at": at.isoformat(), "note": "",
        "declared_by": "CMO", "ledger_index": index, "recorded": at.isoformat(), "signer": signer,
    }


def _instant(
    index: int, at: dt.datetime, signer: str = "simulator", basis: str = "effective"
) -> dict[str, Any]:
    return {
        "index": index, "entry_type": "vital-observation", "signer": signer,
        "instant": at.isoformat(), "basis": basis,
    }


def _store() -> Any:
    store = routes._store
    assert store is not None
    return store


def _reference(client: TestClient) -> dt.datetime:
    return dt.datetime.fromisoformat(client.get("/api/status").json()["data"]["reference_time"])


def _declare(client: TestClient, state: str, at: dt.datetime, **extra: Any) -> Any:
    body = {"state": state, "at": at.isoformat(), "declared_by": "CMO", **extra}
    return client.post("/api/link-sync", json=body)


def _read(client: TestClient, light_cut: dt.datetime | None) -> dict[str, Any]:
    params = {} if light_cut is None else {"light_cut": light_cut.isoformat()}
    answer = client.get("/api/link-sync", params=params)
    assert answer.status_code == 200, answer.text
    body: dict[str, Any] = answer.json()
    return body


def _readings_after(client: TestClient, after: dt.datetime) -> int:
    """Las lecturas de la cadena con hora posterior a `after`, contadas por otro camino."""
    return sum(
        1 for item in _store().ledger_instants()
        if item["basis"] == "effective" and dt.datetime.fromisoformat(item["instant"]) > after
    )


# --------------------------------------------------------------------------- #
# La cuenta, sin almacén
# --------------------------------------------------------------------------- #


def test_without_changes_the_cut_is_the_light_cut() -> None:
    assert link_sync.ground_cut(T0, []) == T0
    assert link_sync.ground_cut(None, []) is None
    assert link_sync.current_state([]) == link_sync.UP


@pytest.mark.parametrize(
    ("light_cut", "expected"),
    [
        (T0 - 2 * HOUR, T0 - 2 * HOUR),  # antes de la caída: lo que va de camino llega
        (T0, T0),  # en el instante de la caída: lo firmado entonces ya salió
        (T0 + HOUR, T0),  # con el enlace caído: hasta la caída
        (T0 + 3 * HOUR - dt.timedelta(seconds=1), T0),  # restablecido, pero aún de camino
        (T0 + 3 * HOUR, T0 + 3 * HOUR),  # lo retenido ya viajó su tiempo de luz
        (T0 + 5 * HOUR, T0 + 5 * HOUR),
    ],
)
def test_the_cut_stops_at_the_drop_until_the_restoration_has_travelled(
    light_cut: dt.datetime, expected: dt.datetime
) -> None:
    changes = [_change(1, "down", T0), _change(2, "up", T0 + 3 * HOUR)]
    assert link_sync.ground_cut(light_cut, changes) == expected


def test_an_open_drop_holds_the_cut_even_without_ephemerides() -> None:
    assert link_sync.ground_cut(None, [_change(1, "down", T0)]) == T0
    assert link_sync.ground_cut(None, [_change(1, "down", T0), _change(2, "up", T0)]) is None


def test_the_cut_is_never_ahead_of_the_light_cut_nor_of_the_last_instant_with_link() -> None:
    """Muchas secuencias y muchos cortes: el corte nunca adelanta, y crece con el reloj."""
    sequences = [
        [_change(1, "down", T0)],
        [_change(1, "down", T0), _change(2, "up", T0 + HOUR)],
        [
            _change(1, "down", T0), _change(2, "up", T0 + HOUR),
            _change(3, "down", T0 + 2 * HOUR), _change(4, "up", T0 + 4 * HOUR),
            _change(5, "down", T0 + 6 * HOUR),
        ],
        [_change(1, "down", T0), _change(2, "up", T0)],  # tramo vacío
    ]
    for changes in sequences:
        previous: dt.datetime | None = None
        for step in range(-24, 120):
            light_cut = T0 + step * dt.timedelta(minutes=5)
            cut = link_sync.ground_cut(light_cut, changes)
            assert cut is not None and cut <= light_cut
            span = link_sync.holding(light_cut, changes)
            if span is not None:
                # Dentro de un corte, Tierra tiene justo hasta la caída: ni un instante más.
                assert cut == span["start"]
            else:
                assert cut == light_cut
            if previous is not None:
                assert cut >= previous, "el corte de Tierra no retrocede con el reloj"
            previous = cut


def test_the_backlog_counts_what_follows_the_drop_in_order_and_without_ground() -> None:
    instants = [
        _instant(5, T0 + 2 * HOUR),
        _instant(3, T0),  # en el instante de la caída: ya salió
        _instant(4, T0 + HOUR, basis="recorded"),
        _instant(6, T0 + HOUR),  # misma hora que el 4: va detrás, por orden de firma
        _instant(7, T0 + 3 * HOUR, signer=GROUND_IDENTITY, basis="recorded"),  # sube, no baja
        _instant(2, T0 - HOUR),
    ]
    queue = link_sync.backlog(instants, T0)
    assert (queue["count"], queue["readings"], queue["other"]) == (3, 2, 1)
    assert (queue["first"], queue["last"], queue["first_index"]) == (
        (T0 + HOUR).isoformat(), (T0 + 2 * HOUR).isoformat(), 4,
    )
    assert link_sync.backlog(instants, None)["count"] == 0
    assert link_sync.GROUND_SIGNER == GROUND_IDENTITY


def test_only_the_board_console_changes_count() -> None:
    changes = link_sync.transitions([
        _change(2, "down", T0, signer="otra-fuente"), _change(1, "down", T0 - HOUR),
    ])
    assert [item["ledger_index"] for item in changes] == [1]


def test_the_rules_of_a_change() -> None:
    down = [_change(1, "down", T0)]
    with pytest.raises(link_sync.LinkConflict):
        link_sync.check_change([], "up", T0, "CMO")  # sin asientos ya está arriba
    with pytest.raises(link_sync.LinkConflict):
        link_sync.check_change(down, "down", T0 + HOUR, "CMO")
    with pytest.raises(link_sync.LinkConflict):
        link_sync.check_change(down, "up", T0 - dt.timedelta(seconds=1), "CMO")
    with pytest.raises(ValueError, match="persona"):
        link_sync.check_change(down, "up", T0 + HOUR, "1234")
    with pytest.raises(ValueError, match="zona"):
        link_sync.check_change(down, "up", dt.datetime(2026, 11, 10, 13), "CMO")
    link_sync.check_change(down, "up", T0, "CMO")  # el mismo instante vale: un tramo vacío


# --------------------------------------------------------------------------- #
# Por la API, con el registro
# --------------------------------------------------------------------------- #


def test_without_declarations_ground_follows_the_light_time(seeded: TestClient) -> None:
    light_cut = _reference(seeded) - DELAY
    body = _read(seeded, light_cut)
    assert (body["state"], body["declared"], body["held"]) == ("up", False, False)
    assert dt.datetime.fromisoformat(body["cut"]) == light_cut
    assert body["to_send"]["count"] == 0
    assert body["to_arrive"]["count"] == _readings_after(seeded, light_cut)
    assert "solo texto" in body["not_read_by"] and "2026-10-21" in body["not_read_by"]
    assert body["label"] == link_sync.LABEL


def test_a_declared_drop_is_one_signed_entry_and_holds_the_ground_cut(seeded: TestClient) -> None:
    reference = _reference(seeded)
    down_at = reference - 6 * HOUR
    answer = _declare(seeded, "down", down_at, note="antena principal")
    assert answer.status_code == 201, answer.text
    entries = [e for e in _store().ledger.entries if e.entry_type == LINK_ENTRY_TYPE]
    assert len(entries) == 1
    assert entries[0].signer == CONSOLE_IDENTITY
    assert {key: value for key, value in entries[0].payload.items() if key != "_salt"} == {
        "subject": LINK_SUBJECT, "state": "down", "at": down_at.isoformat(),
        "note": "antena principal", "declared_by": "CMO",
    }
    body = _read(seeded, reference - DELAY)
    assert (body["state"], body["held"]) == ("down", True)
    assert dt.datetime.fromisoformat(body["cut"]) == down_at
    pending = _readings_after(seeded, down_at)
    assert pending > 0
    assert body["to_send"]["readings"] == pending
    assert body["to_arrive"]["count"] == body["to_send"]["count"]
    assert dt.datetime.fromisoformat(body["to_send"]["first"]) > down_at
    assert "pendientes de enviar a Tierra" in body["crew_sentence"]
    assert "Faltan" in body["ground_sentence"] and "por llegar" in body["ground_sentence"]


def test_after_the_restoration_has_travelled_ground_has_everything_in_order(
    seeded: TestClient,
) -> None:
    reference = _reference(seeded)
    down_at, up_at = reference - 6 * HOUR, reference - HOUR
    assert _declare(seeded, "down", down_at).status_code == 201
    held = _read(seeded, reference - DELAY)
    assert _declare(seeded, "up", up_at).status_code == 201

    # Restablecido, pero lo retenido aún no ha viajado su tiempo de luz: Tierra sigue en la caída.
    travelling = _read(seeded, up_at - DELAY)
    assert travelling["held"] and dt.datetime.fromisoformat(travelling["cut"]) == down_at
    assert travelling["to_send"]["count"] == 0, "a bordo ya no queda nada por enviar"
    assert "Se restableció" in travelling["ground_sentence"]

    arrived = _read(seeded, reference - DELAY)
    assert not arrived["held"] and dt.datetime.fromisoformat(arrived["cut"]) == reference - DELAY
    # Lo que llegó es exactamente lo que estaba retenido, y nada se ha perdido: Tierra ve todas
    # las lecturas hasta su corte, las mismas que hay en la cadena.
    received = _store().query("crew-01", until=reference - DELAY)
    assert len(received) == _crew01_readings_until(reference - DELAY)
    assert held["to_arrive"]["count"] - arrived["to_arrive"]["count"] == sum(
        1 for item in _store().ledger_instants()
        if item["signer"] != GROUND_IDENTITY
        and down_at < dt.datetime.fromisoformat(item["instant"]) <= reference - DELAY
    )


def _crew01_readings_until(until: dt.datetime) -> int:
    """Las lecturas de crew-01 de la cadena hasta `until`, contadas sin pasar por `query`."""
    return sum(
        1 for entry in _store().ledger.entries
        if entry.entry_type == "vital-observation" and isinstance(entry.payload, dict)
        and entry.payload.get("subject") == "crew-01"
        and dt.datetime.fromisoformat(entry.payload["effective"]) <= until
    )


def test_the_api_refuses_what_breaks_the_rules(client: TestClient) -> None:
    assert _declare(client, "up", T0).status_code == 409  # ya está arriba
    assert _declare(client, "down", T0).status_code == 201
    assert _declare(client, "down", T0 + HOUR).status_code == 409
    assert _declare(client, "up", T0 - HOUR).status_code == 409  # hacia atrás
    assert _declare(client, "up", T0 + HOUR, declared_by="1234").status_code == 422
    assert _declare(client, "sideways", T0 + HOUR).status_code == 422
    naive = {"state": "up", "at": "2026-11-10T13:00:00", "declared_by": "CMO"}
    assert client.post("/api/link-sync", json=naive).status_code == 422
    assert client.post("/api/link-sync", json={**naive, "extra": 1}).status_code == 422
    naive_cut = {"light_cut": "2026-11-10T13:00:00"}
    assert client.get("/api/link-sync", params=naive_cut).status_code == 422
    assert len([e for e in _store().ledger.entries if e.entry_type == LINK_ENTRY_TYPE]) == 1


def test_a_malformed_change_is_a_409_not_a_cut(client: TestClient) -> None:
    _store()._record_action(
        LINK_ENTRY_TYPE,
        {"subject": LINK_SUBJECT, "state": "sideways", "at": T0.isoformat(), "note": "",
         "declared_by": "CMO"},
        identity_for(CONSOLE_IDENTITY),
    )
    assert client.get("/api/link-sync").status_code == 409


def test_a_change_signed_by_another_identity_does_not_hold_ground(seeded: TestClient) -> None:
    reference = _reference(seeded)
    _store()._record_action(
        LINK_ENTRY_TYPE,
        {"subject": LINK_SUBJECT, "state": "down", "at": (reference - 6 * HOUR).isoformat(),
         "note": "", "declared_by": "CMO"},
        identity_for("otra-fuente"),
    )
    body = _read(seeded, reference - DELAY)
    assert (body["state"], body["held"]) == ("up", False)


# --------------------------------------------------------------------------- #
# Nada que decide lo lee
# --------------------------------------------------------------------------- #


def test_the_status_is_identical_before_and_after_a_declared_drop(
    alerting: tuple[TestClient, dict[str, Any]],
) -> None:
    client, status = alerting
    assert status["alerts"], "el escenario de arritmia alerta"
    reference = dt.datetime.fromisoformat(status["data"]["reference_time"])
    cut = (reference - 2 * HOUR).isoformat()
    before = client.get("/api/status").json()
    before_ground = client.get("/api/status", params={"until": cut}).json()
    assert _declare(client, "down", reference - 6 * HOUR).status_code == 201
    # Niveles, puntuaciones, alertas, recomendaciones, factor de aislamiento, aviso a Tierra y
    # enlace declarado: lo mismo. Lo único que cambia es el corte que la consola pide.
    assert client.get("/api/status").json() == before
    assert client.get("/api/status", params={"until": cut}).json() == before_ground


def test_nothing_that_decides_imports_the_simulated_link() -> None:
    watched = [
        *sorted((APP / "analysis").glob("*.py")), *sorted((APP / "advisor").glob("*.py")),
        APP / "api" / "routes.py", APP / "environment" / "systems.py",
    ]
    for module in watched:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        names = {
            alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        } | {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        assert not {name for name in names if "link_sync" in name}, module.name
