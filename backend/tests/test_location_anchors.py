"""Las anclas de módulo: sus rutas, su asiento firmado y la estimación del módulo (2026-11-10).

Lo que fijan estas pruebas, sin red y sin radio:
- declarar un ancla es UN asiento firmado por la consola; manda la última y no se borra nada;
- un lote de lecturas es UN asiento firmado como `location-anchors` (invariante 4), con la
  ventana de fechas de un wearable; un ancla desconocida se guarda y se dice, pero no se usa;
- la estimación (`analysis.location.estimate`) es pura: módulo por la señal más fuerte, con
  margen, histéresis, indeterminación entre módulos y caducidad;
- `context.prevailing`: la consola sobre las anclas aunque sea anterior.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis.context import Stay, prevailing
from app.analysis.location import (
    LOCATION_BASIS,
    Anchor,
    Sensing,
    Sighting,
    Whereabouts,
    estimate,
    module_of,
    sensing,
    view,
)
from app.api.mission import crew_whereabouts
from app.api.routes import get_store, identity_for
from app.core.identities import ANCHOR_IDENTITY, CONSOLE_IDENTITY
from app.core.storage import TamperedRecordError

T0 = dt.datetime(2026, 11, 5, 12, 0, tzinfo=dt.UTC)
SINCE = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)
PARAMS = Sensing(
    window_s=10, margin_db=6, min_dwell_s=20, stale_after_s=120, min_rssi_dbm=-95,
    evidence="unsupported", evidence_note="", not_coded="", basis=(),
)
ANCHORS = [
    Anchor("lab", "laboratorio", SINCE, 1),
    Anchor("cam", "camarotes", SINCE, 2),
]


def _at(seconds: float) -> dt.datetime:
    return T0 + dt.timedelta(seconds=seconds)


def _series(
    start: int, stop: int, lab: float, cam: float, step: int = 2, order: int = 10
) -> list[Sighting]:
    return [
        item
        for second in range(start, stop, step)
        for item in (
            Sighting("lab", lab, _at(second), order),
            Sighting("cam", cam, _at(second), order),
        )
    ]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def _declare(client: TestClient, **changes: Any) -> Any:
    return client.post("/api/location/anchors", json={
        "anchor_id": "LAB-01", "module": "laboratorio", "since": SINCE.isoformat(),
        "declared_by": "CDR", **changes,
    })


# --------------------------------------------------------------------------- #
# La estimación, función pura
# --------------------------------------------------------------------------- #


def test_the_strongest_module_by_the_margin_is_the_estimate() -> None:
    stays, undecided = estimate(_series(0, 30, -55, -75), ANCHORS, PARAMS)
    [stay] = stays
    assert (stay.module, stay.source, undecided) == ("laboratorio", "anchors", [])
    assert stay.start == _at(0) and stay.last_seen == _at(28)
    # Vale hasta que caduca: la última lectura más `stale_after_s`.
    assert stay.end == _at(28 + PARAMS.stale_after_s)


def test_the_same_readings_give_the_same_estimate() -> None:
    sightings = _series(0, 30, -55, -75) + _series(30, 90, -80, -50)
    assert estimate(sightings, ANCHORS, PARAMS) == estimate(sightings[::-1], ANCHORS, PARAMS)


def test_a_brief_change_shorter_than_the_dwell_moves_nobody() -> None:
    # Diez segundos en que el camarote gana (un cuerpo tapa el ancla): no basta.
    sightings = (
        _series(0, 40, -55, -75) + _series(40, 50, -80, -55) + _series(50, 90, -55, -75)
    )
    [stay] = estimate(sightings, ANCHORS, PARAMS)[0]
    assert stay.module == "laboratorio"


def test_a_change_that_lasts_the_dwell_moves_to_the_other_module() -> None:
    sightings = _series(0, 40, -55, -75) + _series(40, 100, -80, -55)
    lab, cam = estimate(sightings, ANCHORS, PARAMS)[0]
    assert (lab.module, cam.module) == ("laboratorio", "camarotes")
    # El cambio empieza cuando empezó a desviarse, y ahí acaba lo anterior.
    assert lab.end == cam.start
    assert _at(40) <= cam.start <= _at(50)


def test_a_change_counts_only_while_it_goes_to_the_same_module() -> None:
    # Diecinueve segundos de camarote y una sola lectura de esclusa: ni lo uno ni lo otro dura la
    # permanencia, y el tripulante sigue en el laboratorio.
    anchors = [*ANCHORS, Anchor("esc", "esclusa", SINCE, 3)]
    sightings = (
        _series(0, 40, -55, -75)
        + _series(40, 59, -80, -55)
        + [Sighting("esc", -40, _at(60), 10)]
        + _series(62, 90, -55, -75)
    )
    [stay] = estimate(sightings, anchors, PARAMS)[0]
    assert stay.module == "laboratorio"


def test_while_another_module_is_heard_the_estimate_does_not_go_stale() -> None:
    # Con una permanencia más larga que la caducidad, oír otro módulo sin parar no es silencio.
    slow = dataclasses.replace(PARAMS, min_dwell_s=200)
    sightings = _series(0, 20, -55, -75) + _series(20, 300, -80, -55)
    lab, cam = estimate(sightings, ANCHORS, slow)[0]
    # Sin hueco ni solape: el laboratorio acaba donde empieza el camarote, en cuanto se oye solo
    # el camarote (la ventana arrastra el laboratorio unos segundos).
    assert lab.end == cam.start
    assert _at(20) <= cam.start <= _at(20 + PARAMS.window_s)


def test_balanced_modules_are_undecided_and_not_forced() -> None:
    stays, [undecided] = estimate(_series(0, 30, -60, -62), ANCHORS, PARAMS)
    assert stays == []
    assert undecided.modules == ("camarotes", "laboratorio")


def test_with_no_readings_for_the_stale_time_the_estimate_ends() -> None:
    sightings = _series(0, 20, -55, -75) + _series(400, 420, -80, -55)
    lab, cam = estimate(sightings, ANCHORS, PARAMS)[0]
    assert lab.end == _at(18 + PARAMS.stale_after_s)
    # Tras el hueco se empieza de nuevo, sin permanencia que esperar.
    assert cam.start == _at(400)


def test_an_unknown_anchor_or_a_weak_signal_is_not_used() -> None:
    sightings = [
        Sighting("nadie", -40, _at(0), 1),
        Sighting("cam", -99, _at(0), 1),
        Sighting("lab", -70, _at(0), 1),
    ]
    [stay] = estimate(sightings, ANCHORS, PARAMS)[0]
    assert stay.module == "laboratorio"
    assert estimate([Sighting("nadie", -40, _at(0), 1)], ANCHORS, PARAMS) == ([], [])
    # Por debajo de `min_rssi_dbm` no es una lectura con la que estimar, aunque sea la única.
    assert estimate([Sighting("lab", -99, _at(0), 1)], ANCHORS, PARAMS) == ([], [])


def test_a_reading_is_judged_with_the_anchor_that_held_at_its_instant() -> None:
    moved = [*ANCHORS, Anchor("lab", "esclusa", _at(100), 3)]
    assert module_of(moved, "lab", _at(50)) == "laboratorio"
    assert module_of(moved, "lab", _at(100)) == "esclusa"
    assert module_of(moved, "lab", SINCE - dt.timedelta(days=1)) is None


def test_the_console_prevails_over_the_anchors_even_when_earlier() -> None:
    console = Stay("camarotes", _at(0), _at(100), 1, source="console")
    anchors = Stay("laboratorio", _at(0), _at(100), 9, source="anchors")
    later_console = Stay("esclusa", _at(0), _at(100), 5, source="console")
    assert prevailing([anchors, console]) is console
    assert prevailing([console, anchors, later_console]) is later_console
    assert prevailing([anchors, Stay("esclusa", _at(0), _at(1), 3, source="anchors")]) is anchors


def test_the_view_states() -> None:
    stays, undecided = estimate(_series(0, 30, -55, -75), ANCHORS, PARAMS)
    found = Whereabouts(stays=stays, undecided=undecided, anchors=True)
    assert view(found, _at(20))["location_state"] == "estimated"
    stale = view(found, _at(28 + PARAMS.stale_after_s + 1))
    assert stale["location_state"] == "stale" and stale["location"]["module"] == "laboratorio"
    assert view(found, _at(-10))["location_state"] == "missing"
    assert view(Whereabouts(), _at(0))["location_state"] == "unavailable"
    assert view(found, _at(20))["location_basis"] == LOCATION_BASIS


def test_the_parameters_are_classified_as_unsupported() -> None:
    params = sensing()
    assert params.evidence == "unsupported"
    assert "calibrar en cada nave" in params.evidence_note
    assert params.lookback > dt.timedelta(seconds=params.stale_after_s)
    # Lo no verificado se dice como tal.
    assert any(item["status"] == "no verificado" for item in params.basis)


# --------------------------------------------------------------------------- #
# Las rutas y su asiento
# --------------------------------------------------------------------------- #


def test_declaring_an_anchor_is_one_entry_signed_by_the_console(client: TestClient) -> None:
    response = _declare(client)
    assert response.status_code == 201, response.text
    store = get_store()
    entry = store.ledger.entries[response.json()["ledger_index"]]
    assert (entry.entry_type, entry.signer) == ("location-anchor", CONSOLE_IDENTITY)
    assert entry.payload["anchor_id"] == "lab-01"
    assert store.verify_integrity().ok
    # Una corrección es otra declaración: manda la última, la anterior se conserva.
    assert _declare(client, module="esclusa").status_code == 201
    body = client.get("/api/location/anchors").json()
    [anchor] = body["anchors"]
    assert (anchor["anchor_id"], anchor["module"]) == ("lab-01", "esclusa")
    assert body["basis"] == LOCATION_BASIS
    assert body["parameters"]["evidence"] == "unsupported"
    assert len(store.location_anchors()) == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"module": "puente"},
        {"anchor_id": "con espacio"},
        {"since": "2026-11-01T00:00:00"},
        {"declared_by": "123"},
    ],
)
def test_what_cannot_be_signed_as_an_anchor_is_a_422_and_writes_nothing(
    client: TestClient, changes: dict[str, Any]
) -> None:
    before = len(get_store().ledger)
    assert _declare(client, **changes).status_code == 422
    assert len(get_store().ledger) == before


def test_an_anchor_declared_for_later_is_not_listed_yet(client: TestClient) -> None:
    _declare(client)
    later = (_now() + dt.timedelta(days=1)).isoformat()
    assert _declare(client, module="esclusa", since=later).status_code == 201
    [anchor] = client.get("/api/location/anchors").json()["anchors"]
    assert anchor["module"] == "laboratorio"


def test_earth_sees_only_the_anchors_of_its_cut(client: TestClient) -> None:
    cut = _now()
    _declare(client)
    assert client.get("/api/location/anchors", params={"until": cut.isoformat()}).json()[
        "anchors"
    ] == []
    assert len(client.get("/api/location/anchors").json()["anchors"]) == 1


def test_a_batch_is_one_entry_signed_as_the_anchors_and_unknowns_are_said(
    client: TestClient,
) -> None:
    _declare(client)
    now = _now()
    response = client.post("/api/location/sightings", json={
        "subject": "crew-01", "device": "Pasarela-1",
        "sightings": [
            {"anchor_id": "LAB-01", "rssi_dbm": -60, "at": now.isoformat()},
            {"anchor_id": "nadie", "rssi_dbm": -70, "at": now.isoformat()},
        ],
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["accepted"], body["unknown_anchors"]) == (2, ["nadie"])
    store = get_store()
    entry = store.ledger.entries[body["ledger_index"]]
    assert (entry.entry_type, entry.signer) == ("location-sightings", ANCHOR_IDENTITY)
    assert entry.payload["device"] == "pasarela-1"
    assert [row["anchor_id"] for row in entry.payload["sightings"]] == ["lab-01", "nadie"]
    assert store.verify_integrity().ok
    # El ancla desconocida se guarda, pero no se usa al estimar.
    found = crew_whereabouts(store, "crew-01")
    assert [stay.module for stay in found.stays] == ["laboratorio"]


@pytest.mark.parametrize(
    "sightings",
    [
        [],
        [{"anchor_id": "lab-01", "rssi_dbm": -60, "at": "2099-01-01T00:00:00+00:00"}],
        [{"anchor_id": "lab-01", "rssi_dbm": -60, "at": "1999-01-01T00:00:00+00:00"}],
        [{"anchor_id": "lab-01", "rssi_dbm": -60, "at": "2026-11-05T00:00:00"}],
        [{"anchor_id": "lab-01", "rssi_dbm": 40, "at": "2026-11-05T00:00:00+00:00"}],
        [{"anchor_id": "lab-01", "rssi_dbm": True, "at": "2026-11-05T00:00:00+00:00"}],
        [{"anchor_id": "lab 01", "rssi_dbm": -60, "at": "2026-11-05T00:00:00+00:00"}],
        [{"anchor_id": "lab-01", "rssi_dbm": -60, "at": "2026-11-05T00:00:00+00:00"}] * 501,
    ],
)
def test_what_is_not_a_plausible_batch_is_a_422_and_writes_nothing(
    client: TestClient, sightings: list[dict[str, Any]]
) -> None:
    before = len(get_store().ledger)
    response = client.post(
        "/api/location/sightings", json={"subject": "crew-01", "sightings": sightings}
    )
    assert response.status_code == 422
    assert len(get_store().ledger) == before


def test_earth_does_not_use_a_batch_signed_after_its_cut(client: TestClient) -> None:
    _declare(client)
    store = get_store()
    cut = dt.datetime.now(dt.UTC)
    # El reloj de Windows avanza a saltos de ~15 ms: que el lote quede firmado DESPUÉS del corte.
    while dt.datetime.now(dt.UTC) <= cut:
        pass
    store.record_location_sightings(
        "crew-01", [("lab-01", -50.0, cut - dt.timedelta(minutes=1))],
        identity_for(ANCHOR_IDENTITY),
    )
    assert crew_whereabouts(store, "crew-01", until=cut).stays == []
    assert [stay.module for stay in crew_whereabouts(store, "crew-01").stays] == ["laboratorio"]


def test_the_store_refuses_a_boolean_rssi_even_from_outside_the_api(client: TestClient) -> None:
    store = get_store()
    before = len(store.ledger)
    with pytest.raises(ValueError):
        store.record_location_sightings(
            "crew-01", [("lab-01", True, _now())], identity_for(ANCHOR_IDENTITY)
        )
    assert len(store.ledger) == before


def test_a_batch_signed_by_anyone_else_is_not_used(client: TestClient) -> None:
    _declare(client)
    store = get_store()
    store.record_location_sightings(
        "crew-01", [("lab-01", -50.0, _now())], identity_for("otra-fuente")
    )
    assert crew_whereabouts(store, "crew-01").stays == []


def test_a_malformed_batch_in_the_ledger_is_a_409_not_one_reading_less(
    client: TestClient,
) -> None:
    store = get_store()
    store._record_action(
        "location-sightings", {"subject": "crew-01", "sightings": [{"anchor_id": "x"}]},
        identity_for(ANCHOR_IDENTITY),
    )
    with pytest.raises(TamperedRecordError):
        store.location_sightings("crew-01")
