"""Los remates de backend de la decimonovena ronda (`compliance/hmi-state-of-the-art.md` §5.39.19).

Seis «Queda» de §5.37 y §5.38. Ninguno cambia una regla: la última prueba lo fija con la huella.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import risk_entity, timeline, waiting
from app.analysis.radiation import SHELTER_NOT_STARTED, time_to_action
from app.api import routes
from app.core import identities
from app.core.storage import CREW_SUBJECT, GROUND_NOTE_ENTRY_TYPE
from app.core.versioning import rules_version
from app.ingest.category_fit import fields, misfits
from app.ingest.codes import CATALOG
from app.ingest.fhir import fhir_category
from app.text_guard import check
from tests.test_api import alerting, client  # noqa: F401 — fixtures

T0 = dt.datetime(2026, 3, 1, 12, 0, tzinfo=dt.UTC)


__all__ = ["alerting", "client"]


# --------------------------------------------------------------------------- #
# 1. La categoría FHIR, expuesta y declarada
# --------------------------------------------------------------------------- #


def test_every_indicator_shows_the_category_of_its_fhir_resource(client: TestClient) -> None:
    rows = client.get("/api/indicators").json()["indicators"]
    assert len(rows) == len(CATALOG)
    for row in rows:
        category = fhir_category(CATALOG[row["key"]])
        assert row["category"] == (category[0] if category else None)
        assert row["category_display"] == (category[1] if category else None)
    by_key = {row["key"]: row for row in rows}
    assert by_key["heart-rate"]["category"] == "vital-signs"
    assert by_key["heart-rate"]["category_display"] == "Vital Signs"
    # Sin categoría es `null` en las dos, no el texto "None".
    assert by_key["energy-intake-daily"]["category"] is None
    assert by_key["energy-intake-daily"]["category_display"] is None


def test_the_misfits_are_declared_with_the_category_they_really_carry(client: TestClient) -> None:
    declared = client.get("/api/indicators").json()["category_fit"]
    assert {item["key"]: item["category"] for item in declared} == {
        "hrv-sdnn": "vital-signs",
        "hrv-rmssd": "vital-signs",
        "orthostatic-drop": "vital-signs",
        "absorbed-dose-rate": "exam",
        "cumulative-dose": "exam",
        "circadian-shift": "survey",
    }
    for item in declared:
        # Cada frase nombra la categoría de la que habla.
        assert f"«{item['category']}»" in item["reason"]
        assert check(item["reason"]) == []
    assert declared == misfits()


def test_a_real_vital_sign_is_not_declared_as_a_misfit() -> None:
    declared = {item["key"] for item in misfits()}
    assert not declared & {"heart-rate", "body-weight", "systolic-bp"}


def test_a_resource_without_category_has_no_fields_to_invent() -> None:
    assert fields(CATALOG["fluid-intake-24h"]) == {"category": None, "category_display": None}


# --------------------------------------------------------------------------- #
# 2. El tiempo transcurrido del refugio
# --------------------------------------------------------------------------- #


def test_before_the_event_there_is_no_elapsed_time_and_it_says_why() -> None:
    shelter = time_to_action(T0, T0 - dt.timedelta(hours=1))
    assert shelter is not None
    assert shelter["elapsed_minutes"] is None
    assert shelter["elapsed_note"] == SHELTER_NOT_STARTED
    assert "después del corte de Tierra" in SHELTER_NOT_STARTED
    assert check(SHELTER_NOT_STARTED) == []
    # El resto del procedimiento no depende del instante de referencia.
    assert shelter["shelter_ready_by"] == (T0 + dt.timedelta(hours=1)).isoformat()


def test_a_second_before_the_event_is_not_rounded_into_a_started_shelter() -> None:
    shelter = time_to_action(T0, T0 - dt.timedelta(seconds=1))
    assert shelter is not None
    assert shelter["elapsed_minutes"] is None


def test_at_the_event_and_after_it_the_elapsed_time_counts_without_a_note() -> None:
    at = time_to_action(T0, T0)
    later = time_to_action(T0, T0 + dt.timedelta(minutes=20))
    assert at is not None and later is not None
    assert (at["elapsed_minutes"], at["elapsed_note"]) == (0, None)
    assert (later["elapsed_minutes"], later["elapsed_note"]) == (20, None)


# --------------------------------------------------------------------------- #
# 3. Las notas de Tierra, en una pasada
# --------------------------------------------------------------------------- #


def _sign(client: TestClient, subject: str, text: str) -> None:
    response = client.post("/api/ground-notes", json={
        "subject": subject, "kind": "information", "text": text, "signed_by": "Dra. Ruiz",
    })
    assert response.status_code == 201


def _crew_with_notes(client: TestClient) -> None:
    for subject in ("crew-01", "crew-02"):
        response = client.post(
            "/api/observations", json={"key": "heart-rate", "value": 60.0, "subject": subject}
        )
        assert response.status_code in {200, 201}
    _sign(client, "crew-01", "Recibido el registro de sueño de ayer.")
    _sign(client, CREW_SUBJECT, "Conferencia con toda la tripulación el jueves.")
    _sign(client, "crew-02", "Recibida la ecografía de ayer.")
    _sign(client, "crew-01", "Lo revisamos en la conferencia del jueves.")


@pytest.mark.parametrize("subject", ["crew-01", "crew-02", CREW_SUBJECT])
def test_one_pass_gives_the_same_notes_as_the_two_it_replaces(
    client: TestClient, subject: str,
) -> None:
    _crew_with_notes(client)
    store = routes.get_store()
    # Las dos pasadas de antes, sobre el mismo ledger.
    before = store.ground_notes(subject)
    if subject != CREW_SUBJECT:
        before = [*before, *store.ground_notes(CREW_SUBJECT)]
    now = store.ground_notes(subject, CREW_SUBJECT)
    assert sorted(now, key=lambda note: note["ledger_index"]) == sorted(
        before, key=lambda note: note["ledger_index"]
    )
    assert now == sorted(now, key=lambda note: note["ledger_index"])


def test_the_route_walks_the_ledger_once_and_shows_only_what_is_addressed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _crew_with_notes(client)
    store = routes.get_store()
    walked: list[Any] = []
    walk = store._actions

    def counted(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        walked.append(args)
        return walk(*args, **kwargs)

    monkeypatch.setattr(store, "_actions", counted)
    body = client.get("/api/ground-notes", params={"subject": "crew-01"}).json()
    assert len(walked) == 1
    assert [note["addressed_to"] for note in body["notes"]] == [
        "crew-01", CREW_SUBJECT, "crew-01",
    ]


def test_one_recipient_still_gets_only_their_own_notes(client: TestClient) -> None:
    _crew_with_notes(client)
    assert {note["subject"] for note in routes.get_store().ground_notes("crew-02")} == {"crew-02"}


def test_every_other_action_still_compares_the_whole_subject(client: TestClient) -> None:
    # Las demás lecturas pasan un texto: «crew-01» no es un trozo de «crew-011».
    _crew_with_notes(client)
    store = routes.get_store()
    assert store._actions("crew-011", GROUND_NOTE_ENTRY_TYPE, ("subject",)) == []
    assert len(store._actions("crew-01", GROUND_NOTE_ENTRY_TYPE, ("subject",))) == 2


# --------------------------------------------------------------------------- #
# 4. La regla de detección lee la función del motor
# --------------------------------------------------------------------------- #


def test_the_risk_matrix_no_longer_reads_the_engine_tables() -> None:
    tree = ast.parse(Path(risk_entity.__file__).read_text(encoding="utf-8"))
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not {"_QUANTILE_THRESHOLDS", "_SAMPLES_FOR_SEVERITY"} & attributes
    assert "cut_rules" in attributes


def test_the_detection_rule_sentence_is_the_one_it_was() -> None:
    rule = risk_entity.detection_rule(
        routes.CURRENT_WINDOW, risk_entity.severity_schema(), risk_entity.isolation_curve()
    )
    # La frase y las cifras exactas de antes del cambio (`main` = 6372fad): de leve a grave.
    step = next(item for item in rule["steps"] if item["key"] == "deviation")
    assert step["values"]["quantiles"] == [
        {"severity": "mild", "display": "leve", "quantile": 0.99, "min_samples": 100},
        {"severity": "moderate", "display": "moderada", "quantile": 0.995, "min_samples": 200},
        {"severity": "severe", "display": "grave", "quantile": 0.999, "min_samples": 1000},
    ]
    assert (
        "leve si cae en el 1 % más extremo de su base por ese lado (con 100 lecturas de base o "
        "más), moderada si cae en el 0,5 % más extremo de su base por ese lado (con 200 lecturas "
        "de base o más), grave si cae en el 0,1 % más extremo de su base por ese lado (con 1000 "
        "lecturas de base o más)."
    ) in str(step)


# --------------------------------------------------------------------------- #
# 5. `concerning` fuera de sus tres valores
# --------------------------------------------------------------------------- #


def test_an_unknown_concerning_side_does_not_load() -> None:
    with pytest.raises(ValueError, match="`concerning` 'alto'"):
        dataclasses.replace(CATALOG["heart-rate"], concerning="alto")


@pytest.mark.parametrize("side", ["high", "low", "both"])
def test_the_three_sides_load(side: str) -> None:
    assert dataclasses.replace(CATALOG["heart-rate"], concerning=side).concerning == side


def test_the_whole_catalog_declares_one_of_the_three() -> None:
    assert {code.concerning for code in CATALOG.values()} <= {"high", "low", "both"}


# --------------------------------------------------------------------------- #
# 6. La identidad de la consola y la regla, en `core/`
# --------------------------------------------------------------------------- #


def _action(**extra: Any) -> dict[str, Any]:
    return {"signer": identities.CONSOLE_IDENTITY, "recorded": T0.isoformat(), **extra}


def test_the_routes_give_the_same_constant_and_the_same_function() -> None:
    assert routes.CONSOLE_IDENTITY == identities.CONSOLE_IDENTITY == "crew-console"
    assert routes._counts is identities.action_counts


def test_an_action_counts_only_if_the_console_signed_it_and_it_had_arrived() -> None:
    assert identities.action_counts(_action(), None)
    assert identities.action_counts(_action(), T0)
    assert not identities.action_counts(_action(), T0 - dt.timedelta(seconds=1))
    assert not identities.action_counts(_action(signer="ground-console"), None)
    assert not identities.action_counts({"recorded": T0.isoformat()}, None)


@pytest.mark.parametrize("module", [timeline, waiting])
def test_the_chronicle_and_the_threads_no_longer_ask_the_routes_for_the_rule(module: Any) -> None:
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "app.api.routes"
        for alias in node.names
    }
    assert not {"_counts", "CONSOLE_IDENTITY"} & imported


# --------------------------------------------------------------------------- #
# Ninguna regla se ha movido
# --------------------------------------------------------------------------- #


def test_the_rules_version_is_the_one_of_main() -> None:
    # 2026-11-02: el cambio de nombre HALO -> EMMA reescribe textos de `countermeasures.json`
    # («diseño EMMA»), y la huella toma el SHA-256 del fichero entero: pasa de
    # reglas@c89d7ebf4d5f4aa9 a esta. Ningún valor que decide ha cambiado (mismos parámetros,
    # catálogo y hábitat; comprobado volcando `rules()` antes y después).
    # 2026-11-02: los periodos de las rutinas, los de siempre y los de un evento solar, entran en
    # la huella (`versioning._routine_periods`): pasa de reglas@252624293917ba27 a esta. Sin la
    # clave `routines`, `rules()` da la de antes (comprobado).
    # 2026-11-04 (commit 0d4a452, «Evento solar en la demo sin red…»): los disparadores que
    # acortan las rutinas de `during_event` entran en la huella
    # (`_routine_periods()["during_event_triggers"] = ["solar-event", "dose"]`; el commit lo
    # declara: «Disparadores en `rules_version`»). Pasa de reglas@2e4bc7bfbe2f754a a esta. Es lo
    # único que cambia: volcado `rules()` en c631ab7 y en 0d4a452, el diff es solo esa clave
    # (mismos parámetros, catálogo, hábitat, contramedidas y periodos). Sin riesgo ni alertas.
    assert rules_version() == "reglas@ba875cb7f892f089"
