"""Las cinco preguntas de los gemelos (base de conocimiento §10, `app/twins.py`). Sin red.

Tres cosas se vigilan: que las preguntas sean las del documento, literales; que cada respuesta salga
de lo que el estado ya calculó y lo diga; y que pedirlas no firme nada que el estado no firmara ya.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import twins
from app.api import twins as twins_api
from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.core.storage import ObservationStore
from app.main import app
from app.text_guard import check

KNOWLEDGE_BASE = Path(__file__).resolve().parents[2] / "docs" / "contexto" / "knowledge-base-v1.md"


@pytest.fixture(scope="module")
def loaded(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[TestClient, ObservationStore]]:
    """CO2 de cabina fuera de límite para dos tripulantes: hay hipótesis compartida."""
    store = new_store()
    reset_store(store)
    cache = tmp_path_factory.mktemp("twins")
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=cache, offline=True)
    client = TestClient(app)
    client.post("/api/simulate", params={"scenario": "co2-fatigue", "days": 40, "crew_size": 2})
    yield client, store
    app.dependency_overrides.clear()
    reset_store(None)


def _kb_rows() -> list[tuple[str, str, str]]:
    text = KNOWLEDGE_BASE.read_text("utf-8")
    section = text.split("# 10. Arquitectura conceptual consolidada", 1)[1].split("\n# 11.", 1)[0]
    rows = [
        tuple(cell.strip() for cell in line.strip().strip("|").split("|"))
        for line in section.splitlines()
        if line.startswith("|")
    ]
    assert rows[0] == ("Twin / capa", "Contenido", "Pregunta")
    return [(row[0], row[1], row[2]) for row in rows[1:]]


# --------------------------------------------------------------------------- #
# Las preguntas son las del documento
# --------------------------------------------------------------------------- #


def test_the_five_layers_are_the_table_of_the_knowledge_base_word_for_word() -> None:
    assert [(layer.twin, layer.content, layer.question) for layer in twins.LAYERS] == _kb_rows()


def test_the_endpoint_asks_the_five_questions_in_the_order_of_the_document(
    loaded: tuple[TestClient, ObservationStore],
) -> None:
    client, _ = loaded
    body = client.get("/api/twins", params={"subject": "crew-01"}).json()
    assert [item["question"] for item in body["questions"]] == [row[2] for row in _kb_rows()]
    assert [item["key"] for item in body["questions"]] == [
        "human", "habitat", "mission", "countermeasure", "decision",
    ]
    assert "§10" in body["source"]
    # Cada respuesta dice de dónde sale, y nombra una ruta que existe.
    for item in body["questions"]:
        assert item["sources"], item["key"]
        assert all(re.match(r"GET /api/[a-z/]+ → ", source) for source in item["sources"])
        assert item["state"] in {twins.ANSWERED, twins.NOTHING, twins.UNAVAILABLE}
        assert item["answer"]


# --------------------------------------------------------------------------- #
# Cada respuesta sale de lo que ya está calculado
# --------------------------------------------------------------------------- #


def test_each_answer_is_what_the_state_and_the_crew_view_already_say(
    loaded: tuple[TestClient, ObservationStore],
) -> None:
    client, _ = loaded
    status = client.get("/api/status", params={"subject": "crew-01"}).json()
    crew = client.get("/api/crew").json()
    body = client.get("/api/twins", params={"subject": "crew-01"}).json()
    human, habitat, mission, countermeasure, decision = body["questions"]

    assert human["answer"] == status["summary"]
    changing = [key for key, value in status["domains"].items() if value["level"] != "nominal"]
    assert len(human["items"]) == len(changing)
    for key in changing:
        assert any(
            all(driver in item["text"] for driver in status["domains"][key]["drivers"])
            for item in human["items"]
        )

    mine = [h for h in crew["correlation"]["hypotheses"] if "crew-01" in h["affected"]]
    assert mine, "con el CO2 fuera de límite para todos, hay una hipótesis que incluye a crew-01"
    assert habitat["state"] == twins.ANSWERED
    assert mine[0]["title"] in habitat["answer"]
    for hypothesis, item in zip(mine, habitat["items"], strict=False):
        assert item["text"].startswith(f"{hypothesis['title']} ({hypothesis['label']}).")

    assert status["mission"]["phase_display"] in mission["answer"]
    assert status["declared_link"]["sentence"] in [item["text"] for item in mission["items"]]

    actions = [rec["action"] for rec in status["recommendations"]]
    assert len(countermeasure["items"]) >= len(actions)
    for action, item in zip(actions, countermeasure["items"], strict=False):
        assert item["text"].startswith(action)
    assert twins.NO_EFFECT_MODEL in countermeasure["notes"]

    assert f"El veredicto se apoya en: {status['data']['basis']}." in decision["notes"]


def test_nothing_composed_here_sounds_like_a_medical_order(
    loaded: tuple[TestClient, ObservationStore],
) -> None:
    client, _ = loaded
    body = client.get("/api/twins", params={"subject": "crew-01"}).json()
    # Lo que redacta este módulo: sus frases fijas y la respuesta de cada capa. Las partes y las
    # reservas copian frases de otros paneles tal cual (la de la dosis de carrera, por ejemplo, la
    # caza `dosing` por la palabra «dosis», que ahí es de radiación): se juzgan donde se escriben.
    texts = [body["note"], body["source"], twins.NO_EFFECT_MODEL]
    texts += [item["answer"] for item in body["questions"]]
    for text in texts:
        assert check(text) == [], text


def test_asking_the_questions_signs_nothing_the_state_did_not_already_sign(
    loaded: tuple[TestClient, ObservationStore],
) -> None:
    client, store = loaded
    client.get("/api/status", params={"subject": "crew-01"})
    before = len(store.prediction_snapshots("crew-01"))
    ledger = client.get("/api/audit").json()
    client.get("/api/twins", params={"subject": "crew-01"})
    client.get("/api/twins", params={"subject": "crew-01"})
    assert len(store.prediction_snapshots("crew-01")) == before
    assert client.get("/api/audit").json() == ledger


def test_the_state_is_the_same_with_and_without_the_questions(
    loaded: tuple[TestClient, ObservationStore],
) -> None:
    client, _ = loaded

    def verdict() -> dict[str, Any]:
        status = client.get("/api/status", params={"subject": "crew-02"}).json()
        return {
            "overall": status["overall_level"],
            "domains": {key: (v["level"], v["score"]) for key, v in status["domains"].items()},
            "alerts": [(a["id"], a["level"]) for a in status["alerts"]],
        }

    first = verdict()
    client.get("/api/twins", params={"subject": "crew-02"})
    assert verdict() == first


def test_for_the_ground_every_answer_is_cut_where_its_state_is_and_nothing_later_leaks(
    loaded: tuple[TestClient, ObservationStore],
) -> None:
    # La consola de Tierra (§5.36.3): las cinco respuestas con lo llegado hasta el corte.
    client, store = loaded
    now = client.get("/api/status", params={"subject": "crew-01"}).json()
    reference = dt.datetime.fromisoformat(now["data"]["reference_time"])
    cut = (reference - dt.timedelta(days=15)).isoformat()
    snapshots = len(store.prediction_snapshots("crew-01"))
    ledger = client.get("/api/audit").json()
    body = client.get("/api/twins", params={"subject": "crew-01", "until": cut}).json()
    assert client.get("/api/audit").json() == ledger
    assert len(store.prediction_snapshots("crew-01")) == snapshots

    ground = client.get("/api/status", params={"subject": "crew-01", "until": cut}).json()
    crew = client.get("/api/crew", params={"until": cut}).json()
    pending = client.get("/api/timeline/waiting", params={"subject": "crew-01", "until": cut})
    assert body["until"] == cut
    assert body["reference_time"] == ground["data"]["reference_time"]
    assert dt.datetime.fromisoformat(body["reference_time"]) <= dt.datetime.fromisoformat(cut)
    assert body["reference_time"] != now["data"]["reference_time"]
    assert body["note"] == f"{twins.NOTE} {twins.GROUND_NOTE}"
    # Cada respuesta es la que compone el estado de Tierra, con la tripulación y lo que espera
    # cortados en el mismo instante: ni una sola parte sale del estado de a bordo. Tampoco la
    # radiación del hábitat (§5.37.4), la de `/api/habitat` en el mismo corte.
    radiation = client.get("/api/habitat", params={"until": cut}).json()["radiation"]
    expected = twins.compose(
        ground, crew, pending.json(), dt.datetime.fromisoformat(cut), radiation
    )
    assert body["questions"] == expected["questions"]
    assert body["questions"] != client.get(
        "/api/twins", params={"subject": "crew-01"}
    ).json()["questions"]


def test_the_ground_questions_hand_their_cut_to_what_waits(
    loaded: tuple[TestClient, ObservationStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Con el simulador nada del registro es posterior al corte: la respuesta entera no siempre
    # cambia si lo que espera no se corta. Se mira qué corte le llega.
    client, _ = loaded
    seen: list[dt.datetime | None] = []
    real = twins_api.waiting_for

    def spy(status: Any, store: Any, subject: str, until: dt.datetime | None = None) -> Any:
        seen.append(until)
        return real(status, store, subject, until)

    monkeypatch.setattr(twins_api, "waiting_for", spy)
    status = client.get("/api/status", params={"subject": "crew-01"}).json()
    cut = dt.datetime.fromisoformat(status["data"]["reference_time"]) - dt.timedelta(days=15)
    client.get("/api/twins", params={"subject": "crew-01", "until": cut.isoformat()})
    assert seen == [cut]


def test_the_ground_questions_refuse_an_instant_without_time_zone(
    loaded: tuple[TestClient, ObservationStore],
) -> None:
    client, _ = loaded
    response = client.get("/api/twins", params={"subject": "crew-01",
                                                "until": "2026-11-20T00:00:00"})
    assert response.status_code == 422


def test_before_any_reading_reaches_the_ground_there_are_no_answers(
    loaded: tuple[TestClient, ObservationStore],
) -> None:
    client, _ = loaded
    response = client.get("/api/twins", params={"subject": "crew-01",
                                                "until": "2020-01-01T00:00:00+00:00"})
    assert response.status_code == 404


def test_on_board_the_answers_carry_no_cut_and_the_plain_note() -> None:
    body = twins.compose(_status(), None, None)
    assert body["until"] is None and body["note"] == twins.NOTE


def test_for_the_ground_the_answers_carry_their_cut_and_say_what_is_in_transit() -> None:
    cut = dt.datetime(2026, 11, 3, 12, tzinfo=dt.UTC)
    body = twins.compose(_status(), None, None, cut)
    assert body["until"] == "2026-11-03T12:00:00+00:00"
    assert body["note"] == f"{twins.NOTE} {twins.GROUND_NOTE}"
    assert check(twins.GROUND_NOTE) == []


def test_without_readings_there_are_no_answers(tmp_path: Path) -> None:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    try:
        response = TestClient(app).get("/api/twins", params={"subject": "crew-09"})
    finally:
        app.dependency_overrides.clear()
        reset_store(None)
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Lo que no se sabe se dice, y lo que no hay también
# --------------------------------------------------------------------------- #


def _status(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "subject": "crew-01",
        "summary": "Todos los dominios en nominal.",
        "level_labels": {"nominal": "Nominal", "watch": "Vigilancia", "concern": "Precaución",
                         "critical": "Crítico"},
        "domains": {"cardiovascular": {"level": "nominal", "drivers": [], "trajectory": None}},
        "alerts": [],
        "recommendations": [],
        "followups": [],
        "mission": {"mission_day": 3.0, "duration_days": 180, "phase_display": "adaptación",
                    "gravity_display": "microgravedad", "events": [], "profile": {}},
        "comms": None,
        "declared_link": {"sentence": "Nadie ha declarado el estado del enlace."},
        "monitoring": {"capabilities": []},
        "data": {"reference_time": "2026-11-04T00:00:00+00:00", "basis": "línea base personal",
                 "quality": {"summary": "Sin lecturas dudosas."}},
        "rules_version": "reglas@prueba",
    }
    return base | overrides


def test_a_nominal_person_has_nothing_changing_and_says_it_with_the_summary() -> None:
    answer = twins.human(_status())
    assert answer["state"] == twins.NOTHING
    assert answer["answer"] == "Todos los dominios en nominal."
    assert answer["items"] == []


def test_what_changes_goes_from_the_most_to_the_least_severe_with_its_causes() -> None:
    answer = twins.human(_status(domains={
        "immune": {"level": "watch", "drivers": ["síntomas subiendo"], "trajectory": None},
        "radiation": {"level": "critical", "drivers": ["dosis alta"],
                      "trajectory": {"display": "empeorando (antes Vigilancia)"}},
        "bone": {"level": "nominal", "drivers": [], "trajectory": None},
    }))
    assert [item["level"] for item in answer["items"]] == ["critical", "watch"]
    assert answer["items"][0]["text"] == (
        "Radiación: dosis alta. Frente a una ventana antes: empeorando (antes "
        "Vigilancia)."
    )
    assert answer["items"][1]["text"] == "Inmune: síntomas subiendo."


def test_without_the_crew_view_the_habitat_answer_is_unavailable_not_empty() -> None:
    answer = twins.habitat(_status(), None)
    assert answer["state"] == twins.UNAVAILABLE


def test_a_person_outside_the_affected_gets_no_hypothesis_and_is_told_why() -> None:
    crew = {"correlation": {"affected": ["crew-02"], "assumption": "habitat compartido",
                            "hypotheses": [{"title": "Cambio individual en crew-02",
                                            "label": "correlación, no causa",
                                            "affected": ["crew-02"]}]}}
    answer = twins.habitat(_status(), crew)
    assert answer["state"] == twins.NOTHING
    assert "no tiene ningún dominio fuera de nominal" in answer["answer"]
    assert answer["notes"] == ["habitat compartido"]


def test_a_less_likely_hypothesis_says_why() -> None:
    crew = {"correlation": {"affected": ["crew-01", "crew-02"], "hypotheses": [
        {"title": "CO2 fuera de límite", "label": "correlación, no causa",
         "affected": ["crew-01", "crew-02"], "likelihood": "less_likely",
         "likelihood_reason": "crew-01 no estaba en ese módulo."},
    ]}}
    answer = twins.habitat(_status(), crew)
    assert answer["items"][0]["text"] == (
        "CO2 fuera de límite (correlación, no causa). Menos probable: crew-01 no estaba en ese "
        "módulo."
    )


def test_without_the_waiting_view_the_decision_says_it_and_keeps_the_confidence() -> None:
    alert = {"domain": "immune", "level": "watch", "acknowledged": False}
    answer = twins.decision(_status(alerts=[alert]), None)
    assert answer["state"] == twins.UNAVAILABLE
    assert answer["answer"] == (
        "No se pudo leer lo que lleva días esperando a una persona; sin reconocer: 1 alerta."
    )
    assert "El veredicto se apoya en: línea base personal." in answer["notes"]


def test_an_unacknowledged_alert_waits_for_a_person_even_before_three_days() -> None:
    fresh = {"domain": "immune", "level": "watch", "acknowledged": False}
    seen = {"domain": "bone", "level": "watch", "acknowledged": True}
    answer = twins.decision(
        _status(alerts=[fresh, seen]), {"threshold_days": 3, "waiting": [], "incongruences": []}
    )
    assert answer["state"] == twins.ANSWERED
    assert answer["answer"] == "Espera a una persona: 1 alerta sin reconocer."
    assert answer["items"] == [{"text": "Alerta inmune sin reconocer.", "level": "watch"}]


def test_nothing_waits_when_everything_is_acknowledged_and_nothing_is_old() -> None:
    answer = twins.decision(_status(), {"threshold_days": 3, "waiting": [], "incongruences": []})
    assert answer["state"] == twins.NOTHING
    assert answer["answer"] == (
        "Nada espera a una persona: ninguna alerta sin reconocer y nada con 3 días o más de "
        "espera."
    )


def test_what_waits_for_a_person_is_listed_with_its_days_and_not_twice() -> None:
    old = {"domain": "immune", "level": "concern", "acknowledged": False}
    answer = twins.decision(_status(alerts=[old]), {
        "threshold_days": 3,
        # `app/waiting.py` titula con el nombre del dominio; aquí la alerta lleva además su nivel.
        "waiting": [{"title": "Alerta inmune sin reconocer", "kind": "reconocer",
                     "days": 9, "since": "2026-11-01"},
                    {"title": "Borrador 7 sin firmar", "kind": "firmar", "days": 4,
                     "since": "2026-11-06"},
                    {"title": "Alerta musculoesquelético en arreglo", "kind": "resolver", "days": 5,
                     "since": "2026-11-05"}],
        "incongruences": [],
    })
    assert answer["state"] == twins.ANSWERED
    assert answer["answer"] == (
        "Espera a una persona: 1 alerta sin reconocer; 3 asuntos con 3 días o más de espera."
    )
    assert answer["items"] == [
        {"text": "Alerta inmune sin reconocer: 9 días esperando.", "level": "concern"},
        {"text": "Borrador 7 sin firmar: 4 días esperando.", "level": None},
        {"text": "Alerta musculoesquelético en arreglo: 5 días esperando.", "level": None},
    ]


def test_no_recommendation_is_nothing_and_the_effect_is_never_predicted() -> None:
    answer = twins.countermeasure(_status())
    assert answer["state"] == twins.NOTHING
    assert twins.NO_EFFECT_MODEL in answer["notes"]


def test_a_closed_followup_is_not_an_open_one() -> None:
    followup = {"countermeasure": {"action": "Dormir más."}, "state": "closed", "evaluation": None}
    answer = twins.countermeasure(_status(followups=[followup]))
    assert answer["state"] == twins.NOTHING
    due = {**followup, "state": "due", "evaluation": {"text": "El dominio siguió en vigilancia."}}
    answer = twins.countermeasure(_status(followups=[due]))
    assert answer["items"][0]["text"] == (
        "Seguimiento de «Dormir más.»: ventana cumplida, lista para revisar y cerrar. El dominio "
        "siguió en vigilancia."
    )


def test_without_ephemeris_the_mission_says_what_is_lost() -> None:
    answer = twins.mission(_status(monitoring={"capabilities": [
        {"key": "light-time", "available": False,
         "consequence": "Sin efemérides: los umbrales no se ajustan por aislamiento."},
    ]}))
    assert answer["answer"] == "Día de misión 3,0 de 180, adaptación, microgravedad."
    assert (
        "Retardo con Tierra: sin dato. Sin efemérides: los umbrales no se ajustan por aislamiento."
        in [item["text"] for item in answer["items"]]
    )


def test_the_lost_light_time_is_told_once_in_the_mission_not_again_in_the_decision() -> None:
    monitoring = {"capabilities": [
        {"key": "light-time", "label": "Retardo con Tierra", "available": False,
         "consequence": "Sin efemérides: los umbrales no se ajustan por aislamiento."},
        {"key": "space-weather", "label": "Meteorología espacial", "available": False,
         "consequence": "Sin datos de NASA DONKI."},
    ]}
    notes = twins.decision(_status(monitoring=monitoring), None)["notes"]
    assert "Meteorología espacial, no disponible. Sin datos de NASA DONKI." in notes
    assert not any("efemérides" in note for note in notes)
