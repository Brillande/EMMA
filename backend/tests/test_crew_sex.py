"""Sexo declarado del tripulante (lote «ciclo», 2026-11-14; revierte la §5.36.19).

Ellande decidió añadir el sexo declarado para llegar a una línea base consciente de la fase del
ciclo. Estas pruebas fijan lo que el dato es y lo que no:

* un asiento propio (`crew-sex`), firmado por la consola en un solo `commit`, no un campo del
  perfil ni de la identidad: los perfiles ya firmados siguen leyéndose igual;
* sin declaración vigente la respuesta dice «no declarado»; nunca hay un valor por omisión;
* se borra solo, con la redacción: tras redactarlo, «no declarado» otra vez, y el perfil y la
  identidad siguen intactos;
* Tierra lo lee con su corte (`until`);
* las reglas valen en la API (422) y en el almacén, y lo rechazado no escribe nada;
* el estado del tripulante es el mismo con y sin sexo declarado: ninguna regla lo lee.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.mission import CREW_SEX_UNDECLARED, latest_crew_sex
from app.api.routes import get_store, identity_for
from app.core.storage import CREW_SEX_ENTRY_TYPE, CREW_SEX_VALUES, TamperedRecordError

FAR = "2100-01-01T00:00:00+00:00"
PAST = "2021-01-01T00:00:00+00:00"


def _declare(client: TestClient, sex: str = "female", **extra: Any) -> Any:
    return client.post("/api/crew/sex", json={"sex": sex, "declared_by": "Ane", **extra})


def _read(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/api/crew/sex", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_undeclared_says_so_and_carries_no_default(client: TestClient) -> None:
    body = _read(client)
    assert body["declared"] is False
    assert body["sex"] is None
    assert body["status"] == CREW_SEX_UNDECLARED
    assert body["values"] == list(CREW_SEX_VALUES)


def test_a_declaration_is_its_own_signed_entry(client: TestClient) -> None:
    store = get_store()
    response = _declare(client)
    assert response.status_code == 201, response.text
    index = response.json()["ledger_index"]
    entry = store.ledger._view()[index]
    assert entry.entry_type == CREW_SEX_ENTRY_TYPE
    assert entry.signer == "crew-console"
    payload = dict(entry.payload)
    # Con sal, como todo asiento: con dos valores posibles, el hash firmado sin ella lo delataría
    # aun redactado el contenido.
    assert payload.pop("_salt")
    assert payload == {"subject": "crew-01", "sex": "female", "declared_by": "Ane"}
    assert store.verify_integrity().ok

    body = _read(client)
    assert body["declared"] is True
    assert body["sex"] == "female"
    assert body["declared_by"] == "Ane"
    assert body["ledger_index"] == index
    # No es un campo del perfil ni de la identidad: ninguno de los dos cambia.
    assert client.get("/api/crew/profile").json()["prior_missions"] is None
    assert client.get("/api/crew/identity").json()["declared"] is False


def test_the_last_declaration_is_the_one_that_counts(client: TestClient) -> None:
    assert _declare(client, "female").status_code == 201
    assert _declare(client, "male").status_code == 201
    assert _read(client)["sex"] == "male"
    assert _read(client, subject="crew-02")["declared"] is False


def test_redacting_it_leaves_it_undeclared_and_touches_nothing_else(client: TestClient) -> None:
    assert client.post("/api/crew/profile", json={
        "prior_missions": 1, "prior_career_dose_msv": 12.5, "declared_by": "CDR",
    }).status_code == 201
    assert client.post("/api/crew/identity", json={
        "given_name": "Ane", "surnames": "Zubiri", "birth_date": "1985-03-07",
        "declared_by": "CMO",
    }).status_code == 201
    index = _declare(client).json()["ledger_index"]

    redacted = client.post(
        f"/api/audit/redact/{index}",
        json={"reason": "lo retira el tripulante", "requested_by": "Ane"},
    )
    assert redacted.status_code == 200, redacted.text
    assert redacted.json()["redacted_index"] == index

    body = _read(client)
    assert body["declared"] is False and body["sex"] is None
    store = get_store()
    assert store.crew_sexes("crew-01") == []
    assert store.ledger._view()[index].payload is None
    assert store.verify_integrity().ok
    assert client.get("/api/crew/profile").json()["prior_missions"] == 1
    assert client.get("/api/crew/identity").json()["declared"] is True


def test_redacting_the_current_one_falls_back_to_the_previous_left(client: TestClient) -> None:
    """Se borra asiento a asiento: lo que queda sin redactar sigue siendo lo declarado."""
    assert _declare(client, "female").status_code == 201
    second = _declare(client, "male").json()["ledger_index"]
    assert client.post(
        f"/api/audit/redact/{second}", json={"reason": "error", "requested_by": "Ane"}
    ).status_code == 200
    assert _read(client)["sex"] == "female"


def test_ground_only_sees_what_existed_at_its_cut(client: TestClient) -> None:
    assert _declare(client).status_code == 201
    assert _read(client, until=PAST)["declared"] is False
    assert _read(client, until=FAR)["sex"] == "female"


def test_until_without_a_time_zone_is_a_422(client: TestClient) -> None:
    response = client.get("/api/crew/sex", params={"until": "2026-10-01T00:00:00"})
    assert response.status_code == 422
    assert "zona horaria" in response.json()["detail"]


def test_the_route_refuses_with_422_writing_nothing(client: TestClient) -> None:
    store = get_store()
    size = len(store.ledger)
    refused = [
        _declare(client, "unknown"),
        _declare(client, ""),
        _declare(client, "Female"),
        client.post("/api/crew/sex", json={"sex": "female"}),
        client.post("/api/crew/sex", json={"declared_by": "Ane"}),
        _declare(client, "female", gender="female"),
        _declare(client, "female", declared_by="  "),
    ]
    assert [response.status_code for response in refused] == [422] * len(refused)
    assert len(store.ledger) == size


def test_the_store_refuses_what_cannot_be_signed(client: TestClient) -> None:
    store, console = get_store(), identity_for("crew-console")
    size = len(store.ledger)
    with pytest.raises(ValueError, match="sexo desconocido"):
        store.record_crew_sex("crew-01", "other", "Ane", console)
    with pytest.raises(ValueError, match="una persona con nombre"):
        store.record_crew_sex("crew-01", "female", " 12 ", console)
    assert len(store.ledger) == size


def test_only_what_the_console_signed_counts(client: TestClient) -> None:
    store = get_store()
    store.record_crew_sex("crew-01", "female", "nadie", identity_for("wearable-ble"))
    assert len(store.crew_sexes("crew-01")) == 1
    assert _read(client)["declared"] is False


def test_a_malformed_entry_is_a_409(client: TestClient) -> None:
    store = get_store()
    store._record_action(
        CREW_SEX_ENTRY_TYPE,
        {"subject": "crew-01", "sex": "x", "declared_by": "Ane"},
        identity_for("crew-console"),
    )
    with pytest.raises(TamperedRecordError, match="sexo declarado mal formado"):
        latest_crew_sex(store, "crew-01")
    assert client.get("/api/crew/sex").status_code == 409
    # Una declaración bien formada firmada después es la vigente.
    assert _declare(client).status_code == 201
    assert _read(client)["sex"] == "female"


def test_the_status_is_the_same_with_and_without_a_declared_sex(client: TestClient) -> None:
    """Ninguna regla lo lee: el estado entero —niveles, alertas, recomendaciones y reglas— es
    idéntico al declararlo, sea cual sea.

    Salvo la frase de la puerta del ajuste por fase (`cycle_phase`, lote «ciclo», B3), que dice
    qué le falta para abrirse: el sexo solo abre esa puerta junto con un ciclo regular declarado
    e inicios de regla, y sin ellos el ajuste no se aplica (`tests/test_cycle_nuisance.py`)."""
    assert client.post("/api/simulate", params={"days": 20}).status_code == 201

    def status() -> dict[str, Any]:
        body: dict[str, Any] = client.get("/api/status", params={"until": FAR}).json()
        assert body["cycle_phase"]["applied"] is False
        return {key: value for key, value in body.items() if key != "cycle_phase"}

    before = status()
    assert _declare(client, "female").status_code == 201
    assert status() == before
    assert _declare(client, "male").status_code == 201
    assert status() == before


def test_reading_it_does_not_write(client: TestClient) -> None:
    assert _declare(client).status_code == 201
    store = get_store()
    size = len(store.ledger)
    _read(client)
    _read(client, until=FAR)
    _read(client, until=dt.datetime.now(dt.UTC).isoformat())
    assert len(store.ledger) == size
