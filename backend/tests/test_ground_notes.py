"""Notas de Tierra a bordo (la «↕ optional synchronization» de la conversación de ideación, L190).

Un asiento firmado `ground-note` con la clave de la consola de Tierra: información o pregunta,
nunca una orden (invariante 7). A bordo se ve solo lo firmado antes del corte (el reloj menos un
tiempo de luz), y lo que va en camino no se cuenta. No toca niveles, alertas ni `rules_version`
(`record-integrity.md` §3.25).

Las pruebas rápidas van primero: la campaña de mutantes (`tests/mutants/ground_notes.json`) corre
este fichero una vez por mutante y para en el primer fallo.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import ground_notes as api_notes
from app.api import routes
from app.core import ground_notes as rules
from app.core.storage import CREW_SUBJECT, GROUND_NOTE_ENTRY_TYPE, ObservationStore
from tests.test_api import alerting, client  # noqa: F401 — fixtures

__all__ = ["alerting", "client"]

QUESTION = "¿Puede repetir la medida de presión esta tarde y contarnos cómo ha dormido?"
INFORMATION = "Recibido el registro de sueño de ayer. Lo revisamos en la conferencia del jueves."


# --------------------------------------------------------------------------- #
# Rápidas: qué se puede decir desde Tierra
# --------------------------------------------------------------------------- #


def test_information_and_questions_pass() -> None:
    assert rules.problem("information", INFORMATION, "Dra. Ruiz") is None
    assert rules.problem("question", QUESTION, "Dra. Ruiz") is None
    # La deliberación como pregunta es justo lo que una pregunta tiene que poder decir.
    assert rules.problem("question", "¿Conviene repetir la medida mañana?", "Dra. Ruiz") is None
    # «Tiene que ver» no manda; una subordinada con subjuntivo de un verbo que no es pauta tampoco.
    assert rules.problem("information", "Esto no tiene que ver con la alerta.", "CAPCOM") is None
    assert rules.problem("information", "Cuando vuelva el enlace, hablamos.", "CAPCOM") is None


@pytest.mark.parametrize(
    "text",
    [
        "Repita la medida de presión.",
        "Debe descansar esta tarde.",
        "Tiene que dormir más.",
        "Hay que bajar el ritmo de ejercicio.",
        "Es obligatorio hacer la ecografía hoy.",
        "Es necesario que descanse.",
        "Tome agua cada hora.",
        "Evite el ejercicio intenso.",
        # Una orden con una coletilla de pregunta sigue siendo una orden (revisión, 2026-10-26).
        "Repita la medida esta tarde, ¿vale?",
        "Debe descansar hoy, ¿de acuerdo?",
        "No haga ejercicio hoy; ¿cómo se encuentra?",
        "Repita la medida esta tarde, vale?",
        # Con el pronombre pegado, y los verbos de pauta que faltaban.
        "Tómese la tensión esta tarde.",
        "Hágase una ecografía mañana.",
        "Repítala esta tarde.",
        "Duerma ocho horas esta noche.",
        # Segunda pasada de la revisión: un «¿» suelto no tapa lo que sigue a su frase, dos
        # pronombres pegados siguen siendo imperativo, y un «?» sin «¿» no vuelve pregunta una
        # pauta en imperativo.
        "¿Hola. Repita la medida esta tarde y descanse. Vale?",
        "Tómeselo esta noche.",
        "Hágaselo mañana.",
        "Repita la medida esta tarde vale?",
        "Por favor repita la medida?",
        "Debe descansar hoy, vale?",
    ],
)
def test_a_mandate_outside_a_question_is_refused(text: str) -> None:
    found = rules.problem("information", text, "Dra. Ruiz")
    assert found is not None and "no da órdenes" in found


def test_a_mandate_inside_a_question_is_a_question() -> None:
    assert rules.problem("question", "¿Debe repetirse la medida?", "Dra. Ruiz") is None
    assert rules.mandate_findings("¿Repite la medida? Repita la medida.") == ["repita"]
    # De «¿» a «?», con sus comas dentro, es una sola pregunta.
    assert rules.mandate_findings("¿Debe, en su opinión, repetirse la medida?") == []
    # Con «¿», un imperativo de pauta dentro de la pregunta sigue sin contar; sin «¿», sí.
    assert rules.mandate_findings("¿Repita la medida esta tarde?") == []
    # Sin «¿», la pregunta va desde la última coma: «debe repetir la medida?» es la pregunta.
    assert rules.mandate_findings("Si no mejora, debe repetir la medida?") == []


@pytest.mark.parametrize(
    "text",
    [
        "Administre 10 mg de ibuprofeno.",  # dosis
        "¿Ha tomado 2 comprimidos?",  # dosis, también en una pregunta
        "Es compatible con un SANS.",  # diagnóstico
        "Sin duda no es nada.",  # certeza
        "Inicie tratamiento.",  # orden
        "Conviene repetir la medida.",  # deliberación afirmada
        "Nunca pasa nada con esto.",  # absoluto
    ],
)
def test_what_the_language_filter_blocks_is_refused(text: str) -> None:
    found = rules.problem("information", text, "Dra. Ruiz")
    assert found is not None and "filtro de lenguaje" in found


def test_kind_question_signer_and_length() -> None:
    assert "clase de nota" in (rules.problem("order", INFORMATION, "Dra. Ruiz") or "")
    assert "«?»" in (rules.problem("question", INFORMATION, "Dra. Ruiz") or "")
    assert "persona" in (rules.problem("information", INFORMATION, "42") or "")
    assert "palabras" in (rules.problem("information", "  12  ", "Dra. Ruiz") or "")
    long = "Recibido. " * (rules.MAX_TEXT // 10 + 1)
    assert "como mucho" in (rules.problem("information", long, "Dra. Ruiz") or "")
    assert rules.problem("information", long[: rules.MAX_TEXT], "Dra. Ruiz") is None


def test_the_store_refuses_what_the_api_refuses() -> None:
    store: Any = ObservationStore.__new__(ObservationStore)
    ground = routes.identity_for(routes.GROUND_IDENTITY)
    with pytest.raises(ValueError, match="no da órdenes"):
        store.record_ground_note("crew-01", "information", "Repita la medida.", "Dra.", ground)
    with pytest.raises(ValueError, match="tripulante"):
        store.record_ground_note("  ", "information", INFORMATION, "Dra. Ruiz", ground)


def _signed(**extra: Any) -> dict[str, Any]:
    return {"ledger_index": 3, "subject": "crew-01", "kind": "information", "text": INFORMATION,
            "signed_by": "Dra. Ruiz", "recorded": "2026-10-27T10:00:00+00:00",
            "signer": routes.GROUND_IDENTITY, **extra}


def test_only_ground_signed_acceptable_notes_are_shown() -> None:
    assert api_notes._shown(_signed())
    assert not api_notes._shown(_signed(signer=routes.CONSOLE_IDENTITY))
    assert not api_notes._shown(_signed(text="Repita la medida."))
    assert not api_notes._shown(_signed(kind="order"))


def test_the_ground_identity_is_reserved() -> None:
    assert routes._is_reserved_source(routes.GROUND_IDENTITY)
    assert routes.GROUND_IDENTITY != routes.CONSOLE_IDENTITY


# --------------------------------------------------------------------------- #
# Por la API
# --------------------------------------------------------------------------- #


@pytest.fixture
def crew(client: TestClient) -> TestClient:
    """Un tripulante con una lectura: basta para ser destinatario (sin simular una misión)."""
    client.post("/api/observations", json={"key": "heart-rate", "value": 60.0})
    return client


def _sign(client: TestClient, **overrides: Any) -> Any:
    body = {"subject": "crew-01", "kind": "question", "text": QUESTION, "signed_by": "Dra. Ruiz",
            **overrides}
    return client.post("/api/ground-notes", json=body)


def test_a_note_is_signed_by_the_ground_console(crew: TestClient) -> None:
    client = crew
    response = _sign(client)
    assert response.status_code == 201, response.text
    entry = client.get("/api/audit", params={"limit": 1}).json()["entries"][-1]
    assert entry["entry_type"] == GROUND_NOTE_ENTRY_TYPE
    assert entry["signer"] == routes.GROUND_IDENTITY
    assert entry["index"] == response.json()["ledger_index"]
    assert client.get("/api/audit").json()["integrity_ok"] is True


def test_on_board_only_after_the_light_time(crew: TestClient) -> None:
    client = crew
    signed = _sign(client).json()
    signed_at = dt.datetime.fromisoformat(signed["signed_at"])
    _sign(client, subject=CREW_SUBJECT, kind="information", text=INFORMATION)

    # Antes del tiempo de luz: ni se entrega ni se cuenta (a bordo no se sabe que viene).
    before = client.get("/api/ground-notes", params={
        "subject": "crew-01", "until": (signed_at - dt.timedelta(seconds=1)).isoformat()}).json()
    assert before["notes"] == [] and before["withheld"] == 0
    assert "in_transit" not in before

    # Pasado: la suya y la de toda la tripulación, en el orden en que se firmaron.
    later = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=1)
    after = client.get("/api/ground-notes", params={
        "subject": "crew-01", "until": later.isoformat()}).json()
    assert [note["kind"] for note in after["notes"]] == ["question", "information"]
    first, second = after["notes"]
    assert (first["text"], first["signed_by"], first["signed_at"]) == (
        QUESTION, "Dra. Ruiz", signed["signed_at"])
    assert (first["kind_display"], second["addressed_to_display"]) == (
        "pregunta", api_notes.CREW_DISPLAY)

    # Otro tripulante ve la de toda la tripulación, no la de crew-01.
    other = client.get("/api/ground-notes", params={"subject": "crew-02"}).json()
    assert [note["addressed_to"] for note in other["notes"]] == [CREW_SUBJECT]


def test_an_order_is_refused_and_nothing_is_written(crew: TestClient) -> None:
    client = crew
    last = client.get("/api/audit", params={"limit": 1}).json()["entries"][-1]["index"]
    response = _sign(client, kind="information", text="Repita la medida de presión ahora.")
    assert response.status_code == 422
    assert "no da órdenes" in response.json()["detail"]
    assert _sign(client, text="Inicie tratamiento.").status_code == 422
    assert client.get("/api/audit", params={"limit": 1}).json()["entries"][-1]["index"] == last


def test_an_unknown_addressee_is_refused(crew: TestClient) -> None:
    client = crew
    response = _sign(client, subject="crew-1")
    assert response.status_code == 422 and "destinatario" in response.json()["detail"]


def test_until_needs_a_timezone(client: TestClient) -> None:
    response = client.get("/api/ground-notes", params={"until": "2026-10-27T10:00:00"})
    assert response.status_code == 422


def test_a_note_signed_with_another_key_is_withheld(crew: TestClient) -> None:
    client = crew
    store = routes.get_store()
    store.record_ground_note("crew-01", "information", INFORMATION, "Dra. Ruiz",
                             routes.identity_for(routes.CONSOLE_IDENTITY))
    listed = client.get("/api/ground-notes", params={"subject": "crew-01"}).json()
    assert listed["notes"] == [] and listed["withheld"] == 1 and listed["withheld_note"]


def test_a_note_changes_no_level_alert_or_rules_version(alerting: tuple[TestClient, dict]) -> None:
    client, status = alerting
    assert _sign(client).status_code == 201
    after = client.get("/api/status").json()
    for key in ("overall_level", "rules_version", "domains", "summary"):
        assert after[key] == status[key], key
    assert [(a["domain"], a["level"], a["acknowledged"]) for a in after["alerts"]] == [
        (a["domain"], a["level"], a["acknowledged"]) for a in status["alerts"]]
    assert after["data"]["observations"] == status["data"]["observations"]


def test_the_rules_come_from_the_backend(client: TestClient) -> None:
    body = client.get("/api/ground-notes/rules").json()
    assert [kind["code"] for kind in body["kinds"]] == list(rules.GROUND_NOTE_KINDS)
    assert body["max_length"] == rules.MAX_TEXT and body["crew_subject"] == CREW_SUBJECT
    assert body["basis"] == rules.BASIS and body["refused"] == rules.REFUSED
