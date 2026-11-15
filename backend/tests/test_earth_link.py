"""El enlace con Tierra declarado caído o degradado (KB §2.1: la pérdida de comunicaciones).

El vocabulario de sistemas dejaba firmar «Comunicaciones: fuera de servicio» y nadie lo leía.
Estas pruebas fijan la lectura: solo cuenta la declaración del sistema entero, se señala lo que
no es «nominal», la frase lleva quién, desde cuándo y el rótulo de lo declarado, Tierra ve lo de
su corte, y —decisión del usuario, solo texto— no mueve el retardo, el factor de aislamiento,
las recomendaciones, `notify_ground` ni ningún nivel o alerta.
"""

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.api.routes import get_store, identity_for
from app.core.cache import CachedPayload
from app.environment import systems
from app.environment.ephemeris import CommsWindow, EphemerisClient

LINK = "communications"
LABEL = "declarado por una persona, no telemetría"
T0 = dt.datetime(2026, 11, 8, 12, 0, tzinfo=dt.UTC)
MARS = CommsWindow(epoch=dt.date(2026, 10, 1), distance_au=2.5, one_way_minutes=20.8, target="Mars")


def _told(
    index: int, state: str, hours: float = 0.0, *, system: str = LINK, module: str | None = None,
    note: str = "", by: str = "CDR",
) -> dict[str, Any]:
    """Un asiento como los entrega el almacén."""
    return {
        "system": system, "state": state, "at": (T0 + dt.timedelta(hours=hours)).isoformat(),
        "note": note, "declared_by": by, "ledger_index": index, "recorded": T0.isoformat(),
        "signer": "crew-console",
    } | ({} if module is None else {"module": module})


def _declare(client: TestClient, state: str, at: dt.datetime = T0, **extra: Any) -> Any:
    response = client.post("/api/habitat/systems/status", json={
        "system": LINK, "state": state, "at": at.isoformat(), "declared_by": "CDR", **extra,
    })
    assert response.status_code == 201, response.text
    return response


# --------------------------------------------------------------------------- #
# La lectura
# --------------------------------------------------------------------------- #


def test_the_link_system_is_in_the_vocabulary_and_nominal_is_a_state() -> None:
    assert systems.LINK_SYSTEM in systems.SYSTEMS
    assert systems.NOMINAL in systems.DECLARABLE_STATES


def test_nothing_declared_is_unknown_not_a_working_link() -> None:
    link = systems.earth_link([])
    assert (link["state"], link["declared"], link["attention"]) == ("undeclared", False, False)
    assert link["headline"] is None and link["since"] is None and link["declared_by"] is None
    assert link["sentence"] == (
        "Nadie ha declarado el estado del enlace con Tierra (sistema Comunicaciones): no se sabe "
        "si funciona. EMMA no mide el enlace: el retardo sale de las efemérides y no cambia con "
        "esta declaración."
    )
    assert link["label"] == LABEL


@pytest.mark.parametrize(
    ("state", "display"), [("out-of-service", "fuera de servicio"), ("degraded", "degradado")]
)
def test_down_or_degraded_is_said_with_who_since_when_and_the_label(
    state: str, display: str
) -> None:
    link = systems.earth_link([_told(4, state, note="sin portadora en banda Ka")])
    assert (link["state"], link["state_display"]) == (state, display)
    assert (link["declared"], link["attention"]) == (True, True)
    assert (link["since"], link["declared_by"], link["ledger_index"]) == (T0.isoformat(), "CDR", 4)
    told = f"«{display}» desde 2026-11-08 12:00 UTC por CDR ({LABEL})"
    assert link["headline"] == f"Enlace declarado {told}"
    assert link["sentence"] == (
        f"Enlace con Tierra declarado {told}. EMMA no mide el enlace: el retardo sale de las "
        "efemérides y no cambia con esta declaración. Nota de quien lo declaró: sin portadora "
        "en banda Ka"
    )


def test_declared_nominal_is_said_but_not_flagged() -> None:
    link = systems.earth_link([_told(1, "out-of-service"), _told(2, "nominal", 5)])
    assert (link["state"], link["declared"], link["attention"]) == ("nominal", True, False)
    assert link["headline"] is None
    assert link["sentence"].startswith(
        f"Enlace con Tierra declarado «nominal» desde 2026-11-08 17:00 UTC por CDR ({LABEL})."
    )


def test_since_is_the_first_of_the_current_run_and_the_latest_holds() -> None:
    link = systems.earth_link([
        _told(1, "degraded", 0, by="MS-2"), _told(2, "out-of-service", 2),
        _told(3, "out-of-service", 6, by="FE-1"),
    ])
    assert link["state"] == "out-of-service"
    # Confirmar que sigue caído no reinicia la cuenta. El «desde» es de quien lo declaró
    # entonces; quien lo confirma después se nombra aparte, sin atribuirle el «desde».
    assert link["since"] == (T0 + dt.timedelta(hours=2)).isoformat()
    assert (link["since_declared_by"], link["declared_by"], link["ledger_index"]) == (
        "CDR", "FE-1", 3,
    )
    assert link["headline"] == (
        f"Enlace declarado «fuera de servicio» desde 2026-11-08 14:00 UTC por CDR, confirmado "
        f"por FE-1 ({LABEL})"
    )
    # Si confirma la misma persona, no se repite.
    same = systems.earth_link([_told(1, "out-of-service"), _told(2, "out-of-service", 3)])
    assert same["headline"] == (
        f"Enlace declarado «fuera de servicio» desde 2026-11-08 12:00 UTC por CDR ({LABEL})"
    )


def test_only_the_whole_system_counts_not_a_module_nor_another_system() -> None:
    link = systems.earth_link([
        _told(1, "out-of-service", module="laboratorio"),
        _told(2, "out-of-service", system="power"),
    ])
    assert (link["state"], link["attention"], link["headline"]) == ("undeclared", False, None)
    assert "módulo" in link["scope_rule"]
    # Un módulo no pisa al sistema entero: este sigue siendo el que vale.
    link = systems.earth_link([_told(1, "degraded"), _told(2, "nominal", 1, module="laboratorio")])
    assert (link["state"], link["attention"]) == ("degraded", True)


def test_a_state_this_version_does_not_know_is_flagged_not_hidden() -> None:
    link = systems.earth_link([_told(1, "intermittent")])
    assert (link["declared"], link["attention"]) == (True, True)
    assert "«intermittent»" in link["headline"]


# --------------------------------------------------------------------------- #
# Por la API: estado de a bordo, corte de Tierra y `/comms`
# --------------------------------------------------------------------------- #


def _status(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/api/status", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_the_status_says_it_and_ground_sees_only_what_existed_at_its_cut(
    client: TestClient,
) -> None:
    client.post("/api/simulate", params={"scenario": "nominal", "days": 5})
    assert _status(client)["declared_link"]["state"] == "undeclared"
    reference = dt.datetime.fromisoformat(_status(client)["data"]["reference_time"])
    _declare(client, "out-of-service", at=reference)
    link = _status(client)["declared_link"]
    assert (link["state"], link["attention"]) == ("out-of-service", True)
    assert LABEL in link["headline"]
    # En un corte anterior al instante al que se refiere, Tierra no lo tiene.
    cut = (reference - dt.timedelta(hours=1)).isoformat()
    assert _status(client, until=cut)["declared_link"]["state"] == "undeclared"


def test_only_the_console_signs_the_link(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "nominal", "days": 5})
    get_store().record_system_status(
        LINK, "out-of-service", T0, "", "nadie", identity_for("otra-fuente")
    )
    assert _status(client)["declared_link"]["declared"] is False


def test_comms_carries_the_declared_link_next_to_the_ephemeris(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = CachedPayload(
        data=MARS, fetched_at=dt.datetime.now(dt.UTC), source="test", from_cache=True
    )
    monkeypatch.setattr(EphemerisClient, "comms_window", lambda self, epoch, target: payload)
    body = client.get("/api/comms").json()
    assert body["one_way_minutes"] == 20.8
    assert body["declared_link"]["state"] == "undeclared"
    _declare(client, "degraded")
    body = client.get("/api/comms").json()
    # El tiempo de luz es el de las efemérides: la declaración no lo toca.
    assert body["one_way_minutes"] == 20.8
    assert (body["declared_link"]["state"], body["declared_link"]["attention"]) == (
        "degraded", True,
    )


def test_without_ephemeris_comms_is_still_the_503(client: TestClient) -> None:
    _declare(client, "out-of-service")
    response = client.get("/api/comms")
    assert response.status_code == 503 and "offline" in response.json()["detail"]


def test_the_systems_overview_carries_the_link_at_ground_cut(client: TestClient) -> None:
    """Antes de que llegue a Tierra ninguna lectura no hay estado recibido (404): la consola de
    Tierra lee el enlace declarado de `/api/habitat/systems` con su corte (§5.35.9). Es el mismo
    objeto que da `/api/status`, de las mismas declaraciones: las de la consola y las del corte."""
    def link(**params: Any) -> dict[str, Any]:
        response = client.get("/api/habitat/systems", params=params)
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()["declared_link"]
        return body

    assert link()["state"] == "undeclared"
    # El corte de Tierra mira también cuándo se FIRMÓ (`identities.action_counts`: `recorded`,
    # la hora de reloj del asiento), no solo el `at` declarado. Con un `at` fijo (`T0`, el
    # 2026-11-08) el corte `T0 + 2 h` quedó por detrás de la firma en cuanto el reloj pasó de esa
    # fecha y la prueba empezó a fallar sola (2026-11-11). Se declara en el ahora del reloj.
    at = dt.datetime.now(dt.UTC).replace(microsecond=0)
    _declare(client, "out-of-service", at=at, note="sin portadora")
    # Una que no firmó la consola no cuenta, tampoco aquí.
    get_store().record_system_status(
        LINK, "nominal", at + dt.timedelta(hours=1), "", "nadie", identity_for("otra-fuente")
    )
    after = link(until=(at + dt.timedelta(hours=2)).isoformat())
    assert (after["state"], after["attention"]) == ("out-of-service", True)
    assert LABEL in after["headline"] and "sin portadora" in after["sentence"]
    assert "sin portadora" not in after["headline"]
    assert link(until=(at - dt.timedelta(hours=1)).isoformat())["state"] == "undeclared"
    client.post("/api/simulate", params={"scenario": "nominal", "days": 5})
    assert link() == _status(client)["declared_link"]


# --------------------------------------------------------------------------- #
# Decisión 2: solo texto
# --------------------------------------------------------------------------- #


def _without_context(detail: dict[str, Any]) -> dict[str, Any]:
    """El detalle sin `context` ni la frase del paso «Contextualizar» del flujo de la alerta
    (§5.34.6), que repite el resumen de ese contexto; el estado de ese paso y el resto del
    flujo siguen comparándose, como en `test_system_status.py`."""
    kept = {k: v for k, v in detail.items() if k != "context"}
    if "flow" in kept:
        kept["flow"] = {
            **kept["flow"],
            "steps": [
                {**step, "detail": None} if step["key"] == "contextualize" else step
                for step in kept["flow"]["steps"]
            ],
        }
    return kept


def _decided(status: dict[str, Any]) -> dict[str, Any]:
    """Lo que decide. Del detalle de cada alerta se aparta `context`: es la capa descriptiva
    donde toda declaración de sistema aparece a propósito (`test_system_status.py`)."""
    return {
        **{
            key: status[key]
            for key in (
                "overall_level", "domains", "recommendations", "rules_version",
                "isolation_factor", "comms", "summary",
            )
        },
        "alerts": [
            {**alert, "detail": _without_context(alert["detail"])}
            for alert in status["alerts"]
        ],
    }


@pytest.mark.parametrize("scenario", ["spe-event", "co2-fatigue"])
def test_a_declared_link_moves_no_level_delay_recommendation_or_ground_notice(
    scenario: str, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        routes, "_fetch_comms", lambda settings, epoch, target: (MARS, ("hace 1 h", 3600))
    )
    response = client.post("/api/simulate", params={"scenario": scenario, "crew_size": 2})
    assert response.status_code == 201, response.text
    subjects = [item["subject"] for item in client.get("/api/crew").json()["crew"]]
    before = {subject: _decided(_status(client, subject=subject)) for subject in subjects}
    reference = dt.datetime.fromisoformat(_status(client)["data"]["reference_time"])
    _declare(client, "out-of-service", at=reference - dt.timedelta(days=1))
    after = {subject: _decided(_status(client, subject=subject)) for subject in subjects}
    assert after == before
    assert _status(client)["declared_link"]["attention"] is True
    # Y alguna recomendación existe y lleva su aviso a Tierra: lo que se compara no es vacío.
    assert any(item["recommendations"] for item in before.values())
