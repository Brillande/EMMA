"""Historial misión a misión del tripulante (decimoquinta ronda, D19; decisión del usuario 4).

La especificación pone `mission_history` en el astronauta (§3). EMMA tenía en el perfil dos cifras
sueltas —cuántas misiones previas y la dosis de carrera previa—. Desde este cambio una persona
declara además, misión a misión, nombre, fechas y dosis. Estas pruebas fijan lo que eso es y lo
que no:

* es un asiento propio (`crew-mission-history`), encadenado y firmado por la consola en un solo
  `commit`; las reglas valen en la API (422) y en el almacén, y lo rechazado no escribe nada;
* un ledger escrito ANTES del cambio sigue verificando y se lee igual (invariante 4);
* la dosis de carrera y su proyección siguen leyendo solo la dosis previa del perfil: el estado
  es idéntico con y sin historial, aunque su suma no case;
* si la suma o el número de misiones no casa con el perfil, se dice; no se corrige ni se elige;
* sin dosis no es cero, y los días salen de las fechas.
"""

from __future__ import annotations

import datetime as dt
import shutil
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import export, text_guard
from app.api.mission import latest_mission_history, latest_profile
from app.api.routes import get_store, identity_for
from app.core import mission_history
from app.core.config import Settings, get_settings
from app.core.ledger import Identity
from app.core.mission_history import PriorMission, check, decode, describe, encode
from app.core.storage import ObservationStore, TamperedRecordError
from app.main import app

D = dt.date
FAR = "2100-01-01T00:00:00+00:00"
EXP = PriorMission("Expedición 1", D(2021, 4, 1), D(2021, 10, 1), 80.25)
ARTEMIS = PriorMission("Artemis II", D(2024, 3, 1), D(2024, 3, 11), 40.25)

# Ledger con dos perfiles, escrito con el código de `main` ANTERIOR a este cambio (commit
# fa6e1b8, `ObservationStore.record_profile` de entonces) y guardado tal cual. Los hashes de
# contenido son los que firmó aquel código.
PRE_CHANGE_LEDGER = Path(__file__).parent / "data" / "profile_pre_mission_history.db"
PRE_CHANGE_HASHES = [
    "2ff81c3d76f0f9720d98fc7b01d2a82116e59128018cf62c8655ece459f8424a",
    "54ab5d39acbaa0e31ef22e176b56a537207956112dbe8ddb060209eb58edaaef",
]


def _wire(*missions: PriorMission) -> list[dict[str, Any]]:
    return [
        {"name": item.name, "start": item.start.isoformat(), "end": item.end.isoformat(),
         "dose_msv": item.dose_msv}
        for item in missions
    ]


def _declare(client: TestClient, *missions: PriorMission, **extra: Any) -> Any:
    return client.post("/api/crew/mission-history", json={
        "missions": _wire(*missions), "declared_by": "CDR", **extra,
    })


def _profile(client: TestClient, missions: int, dose: float | None) -> None:
    assert client.post("/api/crew/profile", json={
        "prior_missions": missions, "prior_career_dose_msv": dose, "declared_by": "CDR",
    }).status_code == 201


def _read(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/api/crew/mission-history", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _checks(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["key"]: item for item in body["checks"]}


# --------------------------------------------------------------------------- #
# Las reglas: lo que no puede ser verdad de una persona
# --------------------------------------------------------------------------- #


def test_the_list_is_ordered_by_start_and_reads_back_the_same() -> None:
    ordered = check([ARTEMIS, EXP])
    assert ordered == [EXP, ARTEMIS]
    assert decode(encode(ordered)) == ordered
    # Todo como texto dentro del JSON, también la dosis; vacía si no se conoce.
    unknown = PriorMission("STS-1", D(2019, 1, 1), D(2019, 1, 3))
    assert '"dose_msv":""' in encode([unknown])
    assert decode(encode([unknown]))[0].dose_msv is None


def test_days_come_from_the_dates_and_are_not_declared() -> None:
    assert EXP.days == 183 and ARTEMIS.days == 10
    assert PriorMission("Suborbital", D(2020, 5, 5), D(2020, 5, 5)).days == 0
    assert "days" not in encode([EXP])


@pytest.mark.parametrize(
    ("missions", "message"),
    [
        ([PriorMission("  ", D(2020, 1, 1), D(2020, 1, 2))], "necesita un nombre"),
        ([PriorMission("x" * 81, D(2020, 1, 1), D(2020, 1, 2))], "como mucho 80"),
        ([PriorMission("A", D(2020, 1, 2), D(2020, 1, 1))], "termina antes de empezar"),
        ([PriorMission("A", D(2020, 1, 1), D(2020, 1, 2), -1.0)], "no puede ser negativa"),
        ([PriorMission("A", D(2020, 1, 1), D(2020, 1, 2), float("nan"))], "no puede ser negativa"),
        ([PriorMission("A", D(2020, 1, 1), D(2020, 3, 1)),
          PriorMission("B", D(2020, 2, 1), D(2020, 4, 1))], "se solapan"),
        # Dos el mismo día, aunque duren cero días: son la misma, o se solapan.
        ([PriorMission("Soyuz", D(2020, 1, 1), D(2020, 1, 1)),
          PriorMission("Soyuz", D(2020, 1, 1), D(2020, 1, 1))], "se solapan"),
        ([PriorMission("A", D(2020, 1, 1), D(2020, 3, 1)),
          PriorMission("B", D(2020, 1, 1), D(2020, 1, 5))], "se solapan"),
        ([PriorMission(f"M{i}", D(2000 + i, 1, 1), D(2000 + i, 1, 2)) for i in range(21)],
         "como mucho 20"),
        ([PriorMission("Futura", D(2026, 1, 1), D(2026, 10, 23))], "termina después de hoy"),
    ],
)
def test_what_cannot_be_true_of_a_person_is_refused(
    missions: list[PriorMission], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        check(missions, today=D(2026, 10, 22))


def test_back_to_back_missions_are_not_an_overlap() -> None:
    first = PriorMission("A", D(2020, 1, 1), D(2020, 3, 1))
    second = PriorMission("B", D(2020, 3, 1), D(2020, 4, 1))
    assert check([second, first]) == [first, second]


def test_a_prior_mission_can_end_today_and_today_is_the_clock_by_default() -> None:
    ends_today = PriorMission("Hoy", D(2026, 1, 1), D(2026, 10, 22))
    assert check([ends_today], today=D(2026, 10, 22)) == [ends_today]
    tomorrow = dt.datetime.now(dt.UTC).date() + dt.timedelta(days=1)
    with pytest.raises(ValueError, match="termina después de hoy"):
        check([PriorMission("Mañana", D(2020, 1, 1), tomorrow)])


def test_with_the_mission_under_way_a_prior_one_cannot_overlap_it() -> None:
    # §5.36.4: con la misión ya empezada, «antes de hoy» dejaba pasar una previa que se solapa.
    started, today = D(2026, 9, 1), D(2026, 10, 22)
    overlaps = PriorMission("Solapada", D(2026, 8, 1), D(2026, 9, 2))
    assert check([overlaps], today=today) == [overlaps]
    with pytest.raises(ValueError, match="después del inicio de la misión en curso"):
        check([overlaps], today=today, current_start=started)
    # Puede acabar el día en que empieza la actual, como dos previas seguidas.
    back_to_back = PriorMission("Seguida", D(2026, 8, 1), started)
    assert check([back_to_back], today=today, current_start=started) == [back_to_back]
    # Con la misión aún por empezar, manda «hoy», como antes.
    later_start = D(2026, 12, 1)
    with pytest.raises(ValueError, match="termina después de hoy"):
        check([PriorMission("Futura", D(2026, 10, 1), D(2026, 11, 1))], today=today,
              current_start=later_start)


def test_the_route_refuses_a_prior_mission_that_overlaps_the_current_one(
    client: TestClient, tmp_path: Path,
) -> None:
    started = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=30)
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, mission_start=started,
    )
    store = get_store()
    size = len(store.ledger)
    overlapping = PriorMission("Solapada", started - dt.timedelta(days=10), started + D.resolution)
    refused = _declare(client, overlapping)
    assert refused.status_code == 422, refused.text
    assert "misión en curso" in refused.json()["detail"]
    assert len(store.ledger) == size
    # El almacén impone lo mismo si se le pasa el inicio, sin escribir nada.
    with pytest.raises(ValueError, match="misión en curso"):
        store.record_mission_history(
            "crew-01", [overlapping], "CDR", identity_for("crew-console"), current_start=started,
        )
    assert len(store.ledger) == size
    ends_at_start = PriorMission("Seguida", started - dt.timedelta(days=10), started)
    assert _declare(client, ends_at_start).status_code == 201
    assert len(store.ledger) == size + 1


def test_reading_says_a_prior_mission_overlaps_the_current_one_without_refusing() -> None:
    # §5.37.11, «Queda»: con `EMMA_MISSION_START` adelantado después de firmar, un historial firmado
    # puede quedar solapado. Al leer se dice; no se rechaza ni se corrige.
    second = PriorMission("Segunda", D(2022, 1, 1), D(2022, 3, 1), 10.0)
    history = {"missions": [EXP, second], "declared_by": "CDR", "recorded": "x",
               "ledger_index": 0}
    profile = {"prior_missions": 2, "prior_career_dose_msv": 90.25}
    clean = describe(history, profile, current_start=D(2022, 3, 1))
    assert set(_checks(clean)) == {"missions", "dose"}, "acabar el día en que empieza no solapa"
    assert set(_checks(describe(history, profile, current_start=None))) == {"missions", "dose"}
    one = _checks(describe(history, profile, current_start=D(2022, 2, 28)))["overlap"]
    assert one["matches"] is False
    assert one["text"].startswith(
        "La misión «Segunda» (termina el 2022-03-01) termina después del inicio de la misión en "
        "curso (2022-02-28): se solapa con ella.")
    assert "Expedición 1" not in one["text"]
    both = describe(history, profile, current_start=D(2021, 9, 30))
    assert both["declared"] is True and len(both["missions"]) == 2, "se lee igual"
    assert _checks(both)["overlap"]["text"].startswith(
        "Las misiones «Expedición 1» (termina el 2021-10-01), «Segunda» (termina el 2022-03-01) "
        "terminan después del inicio de la misión en curso (2021-09-30): se solapan con ella.")
    # El aviso no toca los cotejos con el perfil.
    assert _checks(both)["dose"] == _checks(clean)["dose"]


def test_the_route_reads_an_overlapping_history_with_the_configured_start(
    client: TestClient, tmp_path: Path,
) -> None:
    started = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=30)
    overlapping = PriorMission("Solapada", started - dt.timedelta(days=10), started + D.resolution)
    # Firmado cuando la misión aún no había empezado (la configuración por defecto, o antes de
    # adelantar `EMMA_MISSION_START`): entonces no se solapaba con nada.
    get_store().record_mission_history(
        "crew-01", [overlapping], "CDR", identity_for("crew-console"), current_start=None,
    )
    assert "overlap" not in _checks(_read(client))
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, mission_start=started,
    )
    body = _read(client)
    assert body["declared"] is True and body["missions"][0]["name"] == "Solapada"
    overlap = _checks(body)["overlap"]
    assert overlap["matches"] is False and started.isoformat() in overlap["text"]


@pytest.mark.parametrize(
    "text",
    [
        "no es json", "{}", '[{"name":"A"}]', '[["A"]]',
        '[{"dose_msv":1,"end":"2020-01-02","name":"A","start":"2020-01-01"}]',
        '[{"dose_msv":"","end":"2020-01-02","name":"A","start":"2020-01-01","x":""}]',
        '[{"dose_msv":"x","end":"2020-01-02","name":"A","start":"2020-01-01"}]',
        '[{"dose_msv":"nan","end":"2020-01-02","name":"A","start":"2020-01-01"}]',
        '[{"dose_msv":"","end":"ayer","name":"A","start":"2020-01-01"}]',
    ],
)
def test_a_list_without_its_shape_is_refused(text: str) -> None:
    with pytest.raises(ValueError):
        decode(text)


def test_reading_asks_for_the_shape_and_not_for_todays_rules() -> None:
    # Una regla más estricta mañana no deja ilegible lo firmado hoy: al leer solo cuenta la forma.
    later = encode([PriorMission("A", D(2020, 1, 2), D(2020, 1, 1))])
    assert decode(later) == [PriorMission("A", D(2020, 1, 2), D(2020, 1, 1))]


# --------------------------------------------------------------------------- #
# El asiento: firmado, aparte del perfil, y rechazado sin escribir nada
# --------------------------------------------------------------------------- #


def test_a_declaration_is_one_signed_entry_apart_from_the_profile(client: TestClient) -> None:
    store, console = get_store(), identity_for("crew-console")
    size = len(store.ledger)
    entry = store.record_mission_history(
        "crew-01", [ARTEMIS, EXP], " CDR ", console, current_start=None
    )
    assert (entry.index, len(store.ledger)) == (size, size + 1)
    assert (entry.entry_type, entry.signer) == ("crew-mission-history", "crew-console")
    assert {k: v for k, v in entry.payload.items() if k != "_salt"} == {
        "subject": "crew-01", "missions": encode([EXP, ARTEMIS]), "declared_by": "CDR",
    }
    assert store.verify_integrity().ok
    [read] = store.mission_histories("crew-01")
    assert read["missions"] == encode([EXP, ARTEMIS]) and read["signer"] == "crew-console"
    latest = latest_mission_history(store, "crew-01")
    assert latest is not None and latest["missions"] == [EXP, ARTEMIS]
    # El perfil no se toca: ni un asiento más ni uno menos.
    assert store.profiles("crew-01") == []
    assert store.mission_histories("crew-02") == []


def test_the_store_refuses_what_cannot_be_signed(client: TestClient) -> None:
    store, console = get_store(), identity_for("crew-console")
    size = len(store.ledger)
    with pytest.raises(ValueError, match="se solapan"):
        store.record_mission_history("crew-01", [
            PriorMission("A", D(2020, 1, 1), D(2020, 3, 1)),
            PriorMission("B", D(2020, 2, 1), D(2020, 4, 1)),
        ], "CDR", console, current_start=None)
    with pytest.raises(ValueError, match="una persona con nombre"):
        store.record_mission_history("crew-01", [EXP], " 12 ", console, current_start=None)
    assert len(store.ledger) == size
    assert store.mission_histories("crew-01") == []


def test_a_malformed_entry_is_a_409_not_a_history(client: TestClient) -> None:
    store = get_store()
    store._record_action("crew-mission-history", {
        "subject": "crew-01", "missions": '[{"name":"A"}]', "declared_by": "CDR",
    }, identity_for("crew-console"))
    with pytest.raises(TamperedRecordError, match="historial de misiones mal formado"):
        latest_mission_history(store, "crew-01")
    assert client.get("/api/crew/mission-history").status_code == 409
    # Un historial bien formado firmado después es el vigente: el mal formado ya no se lee.
    assert _declare(client, EXP).status_code == 201
    assert _read(client)["missions"][0]["name"] == "Expedición 1"


def test_until_without_a_time_zone_is_a_422(client: TestClient) -> None:
    response = client.get("/api/crew/mission-history", params={"until": "2026-10-01T00:00:00"})
    assert response.status_code == 422
    assert "zona horaria" in response.json()["detail"]


def test_the_route_writes_one_entry_and_refuses_with_422_writing_nothing(
    client: TestClient,
) -> None:
    store = get_store()
    size = len(store.ledger)
    refused = [
        _declare(client, PriorMission("A", D(2020, 1, 2), D(2020, 1, 1))),
        _declare(client, PriorMission("A", D(2020, 1, 1), D(2020, 3, 1)),
                 PriorMission("B", D(2020, 2, 1), D(2020, 4, 1))),
        _declare(client, PriorMission("A", D(2020, 1, 1), D(2020, 1, 2), -1.0)),
        _declare(client, PriorMission("A", D(2020, 1, 1), D(2020, 1, 2), 2001.0)),
        _declare(client, PriorMission("Futura", D(2020, 1, 1), D(2100, 1, 1))),
        _declare(client, EXP, declared_by=""),
        client.post("/api/crew/mission-history", json={
            "missions": [{**_wire(EXP)[0], "days": 183}], "declared_by": "CDR"}),
        client.post("/api/crew/mission-history", json={"declared_by": "CDR"}),
    ]
    assert [response.status_code for response in refused] == [422] * len(refused)
    assert len(store.ledger) == size

    created = _declare(client, EXP, ARTEMIS)
    assert created.status_code == 201, created.text
    assert created.json()["ledger_index"] == size
    assert len(store.ledger) == size + 1
    assert store.verify_integrity().ok


# --------------------------------------------------------------------------- #
# Lo que vale y lo que se dice
# --------------------------------------------------------------------------- #


def test_nothing_declared_is_not_no_missions(client: TestClient) -> None:
    body = _read(client)
    assert body["declared"] is False and body["missions"] == [] and body["checks"] == []
    assert body["text"] == "Sin historial misión a misión declarado."
    assert _declare(client).status_code == 201
    empty = _read(client)
    assert empty["declared"] is True and empty["missions"] == []
    assert empty["text"] == "Declarado: ninguna misión previa."


def test_the_latest_declaration_holds(client: TestClient) -> None:
    assert _declare(client, EXP).status_code == 201
    assert _declare(client, EXP, ARTEMIS).status_code == 201
    body = _read(client)
    assert [item["name"] for item in body["missions"]] == ["Expedición 1", "Artemis II"]
    assert body["missions"][0] == {
        "name": "Expedición 1", "start": "2021-04-01", "end": "2021-10-01", "days": 183,
        "dose_msv": 80.25,
    }
    assert body["days_basis"] == mission_history.DAYS_BASIS
    assert body["scope"] == mission_history.SCOPE
    assert body["declared_by"] == "CDR" and body["text"] == "Declaradas 2 misiones previas."
    assert body["dose_sum_msv"] == pytest.approx(120.5)
    assert body["missions_without_dose"] == 0
    # Los topes los da el backend: el formulario no los copia.
    assert body["limits"] == {"missions": 20, "name_length": 80}
    assert _read(client, subject="crew-02")["limits"] == body["limits"]
    assert len(get_store().mission_histories("crew-01")) == 2


def test_a_sum_that_matches_the_profile_is_said_as_matching(client: TestClient) -> None:
    _profile(client, 2, 120.5)
    assert _declare(client, EXP, ARTEMIS).status_code == 201
    checks = _checks(_read(client))
    assert checks["missions"]["matches"] is True
    assert checks["missions"]["text"] == (
        "El historial declara 2 misiones, las mismas que el perfil.")
    assert checks["dose"]["matches"] is True
    assert checks["dose"]["text"] == (
        "La suma de las dosis del historial (120,50 mSv) casa con la dosis de carrera previa del "
        "perfil (120,50 mSv)."
    )


def test_a_sum_that_does_not_match_is_said_and_nothing_is_corrected(client: TestClient) -> None:
    _profile(client, 3, 200.0)
    assert _declare(client, EXP, ARTEMIS).status_code == 201
    checks = _checks(_read(client))
    assert checks["missions"]["matches"] is False
    assert checks["missions"]["text"].startswith(
        "El historial declara 2 misiones y el perfil, 3 misiones. No se corrige ninguno")
    assert checks["dose"]["matches"] is False
    assert checks["dose"]["text"].startswith(
        "La suma de las dosis del historial (120,50 mSv) no casa con la dosis de carrera previa "
        "del perfil (200,00 mSv). La escala de carrera sigue usando la del perfil")
    # Ni el perfil cambia ni se escribe nada al leer.
    assert client.get("/api/crew/profile").json()["prior_career_dose_msv"] == 200.0


def test_floating_point_is_not_a_mismatch() -> None:
    # 0,1 + 0,2 no es 0,3 en coma flotante; la consola declara centésimas.
    history = {"missions": [PriorMission("A", D(2020, 1, 1), D(2020, 1, 2), 0.1),
                            PriorMission("B", D(2021, 1, 1), D(2021, 1, 2), 0.2)],
               "declared_by": "CDR", "recorded": "x", "ledger_index": 0}
    profile = {"prior_missions": 2, "prior_career_dose_msv": 0.3}
    assert _checks(describe(history, profile, current_start=None))["dose"]["matches"] is True
    off = {**profile, "prior_career_dose_msv": 0.31}
    assert _checks(describe(history, off, current_start=None))["dose"]["matches"] is False


def test_a_mission_without_dose_is_not_zero_and_the_sum_is_not_compared(
    client: TestClient,
) -> None:
    _profile(client, 2, 80.25)
    unknown = PriorMission("Artemis II", D(2024, 3, 1), D(2024, 3, 11))
    assert _declare(client, EXP, unknown).status_code == 201
    body = _read(client)
    assert body["missions"][1]["dose_msv"] is None
    assert body["missions_without_dose"] == 1
    # La suma de las conocidas casa con el perfil, pero es incompleta: no se dice que casa.
    dose = _checks(body)["dose"]
    assert dose["matches"] is None
    assert dose["text"].startswith("1 misión del historial sin dosis declarada")
    assert "Sin dosis no es cero." in dose["text"]
    none_known = describe(
        {"missions": [unknown], "declared_by": "CDR", "recorded": "x", "ledger_index": 0},
        {"prior_missions": 1, "prior_career_dose_msv": None}, current_start=None,
    )
    assert none_known["dose_sum_msv"] is None


def test_without_a_profile_there_is_nothing_to_compare_with(client: TestClient) -> None:
    assert _declare(client, EXP).status_code == 201
    checks = _checks(_read(client))
    assert checks["missions"]["matches"] is None
    assert checks["dose"]["matches"] is None
    assert "la suma no la sustituye" in checks["dose"]["text"]


def test_only_what_the_console_signed_counts(client: TestClient) -> None:
    store = get_store()
    store.record_mission_history(
        "crew-01", [EXP], "nadie", identity_for("wearable-ble"), current_start=None
    )
    assert len(store.mission_histories("crew-01")) == 1
    assert _read(client)["declared"] is False


def test_ground_only_sees_what_existed_at_its_cut(client: TestClient) -> None:
    assert _declare(client, EXP).status_code == 201
    assert _read(client, until="2021-01-01T00:00:00+00:00")["declared"] is False
    assert _read(client, until=FAR)["declared"] is True


def test_no_text_sounds_like_an_order() -> None:
    # Invariante 7: ni órdenes ni correcciones; lo que no casa se dice para una persona.
    texts = [mission_history.SCOPE, mission_history.DAYS_BASIS]
    history = {"missions": [EXP], "declared_by": "CDR", "recorded": "x", "ledger_index": 0}
    for profile in ({"prior_missions": None, "prior_career_dose_msv": None},
                    {"prior_missions": 1, "prior_career_dose_msv": 80.25},
                    {"prior_missions": 4, "prior_career_dose_msv": 1.0}):
        body = describe(history, profile, current_start=D(2021, 6, 1))
        texts += [body["text"], *(item["text"] for item in body["checks"])]
    assert "overlap" in _checks(body), "el aviso de solape también se lee aquí"
    joined = " ".join(texts).casefold()
    for word in ("debe", "corrija", "corrige la", "se sustituye por", "obligatori", "hay que"):
        assert word not in joined, word


# --------------------------------------------------------------------------- #
# La dosis de carrera no lo lee
# --------------------------------------------------------------------------- #


@pytest.fixture
def spe(client: TestClient) -> dict[str, Any]:
    assert client.post(
        "/api/simulate", params={"scenario": "spe-event", "days": 20}
    ).status_code == 201
    _profile(client, 1, 120.0)
    status: dict[str, Any] = client.get("/api/status", params={"until": FAR}).json()
    return status


def test_the_career_dose_reads_only_the_profile(client: TestClient, spe: dict[str, Any]) -> None:
    assert spe["radiation"]["career"]["prior_msv"] == 120.0
    # Un historial que suma otra cosa (300 mSv en dos misiones, no una).
    assert _declare(
        client,
        PriorMission("A", D(2020, 1, 1), D(2020, 6, 1), 100.0),
        PriorMission("B", D(2022, 1, 1), D(2022, 6, 1), 200.0),
    ).status_code == 201
    assert _checks(_read(client))["dose"]["matches"] is False
    after = client.get("/api/status", params={"until": FAR}).json()
    assert after["radiation"] == spe["radiation"]
    assert after["radiation"]["career"]["prior_msv"] == 120.0
    # Y el estado entero: niveles, alertas, recomendaciones y reglas, idénticos.
    assert after == spe


def test_a_history_without_a_profile_does_not_make_up_a_career_dose(
    client: TestClient,
) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "spe-event", "days": 20}
    ).status_code == 201
    before = client.get("/api/status", params={"until": FAR}).json()
    assert before["radiation"]["career"]["value_msv"] is None
    assert _declare(client, EXP, ARTEMIS).status_code == 201
    after = client.get("/api/status", params={"until": FAR}).json()
    assert after["radiation"]["career"]["value_msv"] is None
    assert after == before


# --------------------------------------------------------------------------- #
# La crónica: la etapa «carrera» (decimosexta ronda, E4, §5.36.4)
# --------------------------------------------------------------------------- #


def _chronicle(client: TestClient, **params: str) -> dict[str, Any]:
    response = client.get("/api/timeline/chronicle", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _career(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [event for event in body["events"] if event["stage"] == "career"]


def test_each_prior_mission_is_a_fact_of_the_career_stage(client: TestClient) -> None:
    assert _declare(client, ARTEMIS, EXP).status_code == 201
    index = get_store().mission_histories("crew-01")[0]["ledger_index"]
    body = _chronicle(client)
    # La etapa nueva va antes del prevuelo, con su rótulo.
    assert body["stages"][0] == {
        "key": "career", "display": "carrera: misiones previas declaradas", "count": 2}
    assert [stage["key"] for stage in body["stages"]][1] == "preflight"
    career = _career(body)
    # En orden de inicio, con la fecha que da el asiento y en su propio reloj, sin día de misión.
    assert [event["fecha"] for event in career] == ["2021-04-01", "2024-03-01"]
    assert [event["at"] for event in career] == [
        "2021-04-01T00:00:00+00:00", "2024-03-01T00:00:00+00:00"]
    for number, event in enumerate(career, start=1):
        assert event["time_basis"] == "declared" and event["mission_day"] is None
        assert (event["tipo"], event["fact"], event["quien"]) == (
            "carrera", "prior-mission-declared", "CDR")
        # De dónde sale: el asiento y que nadie lo ha comprobado.
        assert event["fuente"] == f"asiento {index}: {mission_history.CHRONICLE_SOURCE}"
        assert event["clave"] == f"ledger:{index}:mission:{number}"
        # Sin veredicto: ni nivel ni clase de límite.
        assert event["level"] is None and event["severity"] is None
        assert event["recomputed"] is False
    assert career[0]["que"] == (
        "misión previa «Expedición 1», del 2021-04-01 al 2021-10-01 (183 días entre fechas); "
        "exposición a radiación declarada 80,25 mSv"
    )
    assert career[0]["recorded"] is not None
    # También en la bitácora de Polaris, con la misma frase.
    assert any("misión previa «Artemis II»" in line for line in body["lines"])
    # Y en el documento exportado, con su etapa y su día, sin una hora que nadie declaró.
    markdown = export.chronicle_markdown(body, "crew-01", dt.datetime(2026, 10, 23, tzinfo=dt.UTC))
    assert "## carrera: misiones previas declaradas" in markdown
    # La cabecera de esa etapa dice que es un día declarado, no un instante en UTC.
    career_table = markdown.split("## carrera: misiones previas declaradas")[1].split("## ")[0]
    assert "| Día declarado | Día de misión |" in career_table
    assert "Instante (UTC)" not in career_table
    assert "| 2021-04-01 | — | misión previa «Expedición 1»" in markdown
    assert "2021-04-01 00:00" not in markdown


def test_a_mission_without_dose_is_told_as_not_declared_not_zero() -> None:
    sentence = mission_history.chronicle_sentence(
        PriorMission("Soyuz", D(2020, 5, 5), D(2020, 5, 6)))
    assert sentence == (
        "misión previa «Soyuz», del 2020-05-05 al 2020-05-06 (1 día entre fechas); sin "
        "exposición a radiación declarada (no es cero)"
    )


def test_the_career_comes_first_and_the_mission_keeps_its_stages(
    client: TestClient, spe: dict[str, Any]
) -> None:
    before = _chronicle(client, until=FAR)
    assert _career(before) == []
    assert _declare(client, EXP, ARTEMIS).status_code == 201
    after = _chronicle(client, until=FAR)
    # Lo anterior a todo va primero; los demás hechos no cambian ni de etapa ni de orden.
    assert [event["stage"] for event in after["events"][:2]] == ["career", "career"]
    assert after["events"][2:] == before["events"]
    assert after["lines"][2:] == before["lines"]
    others = {stage["key"]: stage["count"] for stage in after["stages"] if stage["key"] != "career"}
    assert others == {
        stage["key"]: stage["count"] for stage in before["stages"] if stage["key"] != "career"}


def test_only_the_history_in_force_enters_the_chronicle(client: TestClient) -> None:
    assert _declare(client, EXP, ARTEMIS).status_code == 201
    assert _declare(client, ARTEMIS).status_code == 201
    [only] = _career(_chronicle(client))
    latest = get_store().mission_histories("crew-01")[-1]["ledger_index"]
    assert "Artemis II" in only["que"] and only["clave"] == f"ledger:{latest}:mission:1"
    # «Ninguna misión previa» es una declaración, y no deja hechos de carrera.
    assert _declare(client).status_code == 201
    body = _chronicle(client)
    assert _career(body) == [] and body["stages"][0]["count"] == 0
    # Otro tripulante no tiene la carrera de este.
    assert _declare(client, EXP).status_code == 201
    assert _career(_chronicle(client, subject="crew-02")) == []


def test_the_chronicle_counts_only_what_the_console_signed(client: TestClient) -> None:
    get_store().record_mission_history(
        "crew-01", [EXP], "nadie", identity_for("wearable-ble"), current_start=None
    )
    assert _career(_chronicle(client)) == []


def test_ground_only_sees_the_career_signed_before_its_cut(client: TestClient) -> None:
    """Lo firmado después del corte de Tierra no aparece, ni en la ruta ni en la crónica."""
    assert _declare(client, EXP).status_code == 201
    first = get_store().mission_histories("crew-01")[0]["recorded"]
    # Que la segunda declaración se firme en un instante posterior a la primera: se espera a
    # que el reloj pase, a pasos cortos y con tope (un reloj de Windows avanza a saltos).
    for _ in range(1000):
        if dt.datetime.now(dt.UTC) > dt.datetime.fromisoformat(first):
            break
        time.sleep(0.005)
    assert _declare(client, EXP, ARTEMIS).status_code == 201
    second = get_store().mission_histories("crew-01")[1]["recorded"]
    assert second > first

    assert _career(_chronicle(client, until="2021-01-01T00:00:00+00:00")) == []
    assert _read(client, until="2021-01-01T00:00:00+00:00")["declared"] is False
    # En el corte entre las dos, Tierra tiene la primera: la corrección está en tránsito.
    at_first = _chronicle(client, until=first)
    assert [event["que"].split("»")[0] for event in _career(at_first)] == [
        "misión previa «Expedición 1"]
    assert [item["name"] for item in _read(client, until=first)["missions"]] == ["Expedición 1"]
    # Con el corte después de la segunda, las dos.
    assert len(_career(_chronicle(client, until=second))) == 2
    assert len(_career(_chronicle(client, until=FAR))) == 2


def test_the_chronicle_reads_the_history_once_and_writes_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "spe-event", "days": 14}
    ).status_code == 201
    assert _declare(client, EXP, ARTEMIS).status_code == 201
    store = get_store()
    size = len(store.ledger)
    calls = {"mission_histories": 0, "profiles": 0}

    def counting(name: str, method: Any) -> Any:
        def counted(*args: Any) -> Any:
            calls[name] += 1
            return method(*args)

        return counted

    for name in calls:
        monkeypatch.setattr(store, name, counting(name, getattr(store, name)))
    assert len(_career(_chronicle(client))) == 2
    # Una lectura del historial; el perfil no se lee: la crónica no coteja ni suma dosis.
    assert calls == {"mission_histories": 1, "profiles": 0}
    assert len(store.ledger) == size


def test_no_career_text_sounds_like_an_order_or_a_verdict() -> None:
    texts = [mission_history.CHRONICLE_SOURCE, *(
        mission_history.chronicle_sentence(item)
        for item in (EXP, PriorMission("Soyuz", D(2020, 5, 5), D(2020, 5, 5)))
    )]
    for text in texts:
        assert text_guard.check(text) == [], text
        lowered = text.casefold()
        for word in ("debe", "hay que", "casa con", "no casa", "excede", "límite", "riesgo"):
            assert word not in lowered, (word, text)


# --------------------------------------------------------------------------- #
# Un ledger escrito antes del cambio
# --------------------------------------------------------------------------- #


def test_a_ledger_written_before_the_change_still_verifies_and_reads(tmp_path: Path) -> None:
    path = tmp_path / "pre.db"
    shutil.copyfile(PRE_CHANGE_LEDGER, path)
    store = ObservationStore.at(path)

    assert store.verify_integrity().ok
    assert [entry["content_hash"] for entry in store.audit_trail()] == PRE_CHANGE_HASHES
    profiles = store.profiles("crew-01")
    assert [(p["prior_missions"], p["prior_career_dose_msv"], p["declared_by"])
            for p in profiles] == [("2", "120.5", "CDR"), ("3", "", "FE-1")]
    # El perfil vigente, el que lee la carrera, es el de antes; y no hay historial.
    assert latest_profile(store, "crew-01") == {
        "prior_missions": 3, "prior_career_dose_msv": None, "declared_by": "FE-1"}
    assert store.mission_histories("crew-01") == []
    assert latest_mission_history(store, "crew-01") is None

    # Sobre esa misma cadena, un historial nuevo.
    console = Identity.generate("otra-consola")
    store.record_mission_history("crew-01", [EXP, ARTEMIS], "CDR", console, current_start=None)
    assert store.verify_integrity().ok
    store.engine.dispose()

    reopened = ObservationStore.at(path)
    assert reopened.verify_integrity().ok
    assert [entry["content_hash"] for entry in reopened.audit_trail()][:2] == PRE_CHANGE_HASHES
    assert len(reopened.profiles("crew-01")) == 2
    [history] = reopened.mission_histories("crew-01")
    assert decode(history["missions"]) == [EXP, ARTEMIS]
    reopened.engine.dispose()
