"""La respuesta previa a una contramedida (base de conocimiento, hipótesis H5).

Cuando EMMA vuelve a recomendar una contramedida que el tripulante ya adoptó, la tarjeta dice
qué pasó la otra vez. Estas pruebas fijan lo que ese bloque es y, sobre todo, lo que no es: lee
la evaluación que el seguimiento ya calculó (no evalúa), no dice que nada «funcionara», no da
por final un seguimiento abierto, respeta el corte de Tierra y las firmas que cuentan, y no
cambia qué se recomienda ni ningún nivel o alerta (invariante 5).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.advisor import countermeasures
from app.advisor.followup import CAUSALITY_NOTE, followups
from app.advisor.prior_response import (
    CAVEAT,
    EVALUATION_BASIS,
    LABEL_AT_CLOSE,
    LABEL_CURRENT_STATE,
    NO_PRIOR,
    OPEN_NO_EVALUATION,
    describe,
    with_prior_response,
)
from app.analysis.risk import RiskLevel
from app.api import routes
from app.core.ledger import Identity
from app.ingest.codes import get
from app.ingest.fhir import VitalObservation

T0 = dt.datetime(2026, 12, 1, 8, 0, tzinfo=dt.UTC)
SLEEP = "bh-protect-sleep"  # ventana de seguimiento de 48 h, una medida que repetir
REASON = "sueño recuperado tras dos noches"
# Lo que ningún texto de este bloque puede decir: sería afirmar una causa o una tasa.
FORBIDDEN = ("eficaz", "eficacia", "funcion", "respondió bien", "éxito", "exito", "%", "mejor con")


def _decision(index: int, action: str, when: dt.datetime, ident: str = SLEEP, **extra: str) -> dict:
    return {
        "ledger_index": index, "action": action, "countermeasure_id": ident,
        "domain": "behavioral", "level": "concern", "reference_time": when.isoformat(),
        "decided_by": "CDR", "reason": "", "adoption_index": "", **extra,
    }


def _followups(decisions: list[dict], now: dt.datetime, level: RiskLevel) -> list[dict[str, Any]]:
    return followups(decisions, {"behavioral": level}, [], now)


def _texts(block: dict[str, Any]) -> str:
    parts = [block["text"], block["caveat"], block["evaluation_basis"] or ""]
    for item in block["adoptions"]:
        parts += [item["adopted_text"], item["state_text"], item["checks_text"]]
        parts.append(item["evaluation_text"] or "")
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Lógica pura
# --------------------------------------------------------------------------- #


def test_no_prior_adoption_is_said_not_left_blank() -> None:
    block = describe(SLEEP, [])
    assert (block["state"], block["count"], block["last"], block["adoptions"]) == (
        "none", 0, None, [])
    assert block["text"] == NO_PRIOR
    assert block["text"] == "Sin adopciones anteriores de esta contramedida para este tripulante."
    # La advertencia viaja también cuando no hay historia.
    assert block["caveat"] == CAVEAT


def test_the_caveat_says_what_happened_after_is_not_proof() -> None:
    assert "lo que pasó después, no una prueba de que fuera por la contramedida" in CAVEAT
    assert "no hay grupo de control" in CAVEAT
    assert "con una o dos adopciones no hay patrón" in CAVEAT


def test_a_closed_adoption_carries_the_followup_evaluation_word_for_word() -> None:
    decisions = [
        _decision(5, "adopted", T0),
        _decision(9, "closed", T0, adoption_index="5", reason=REASON),
    ]
    now = T0 + dt.timedelta(days=10)
    derived = _followups(decisions, now, RiskLevel.WATCH)
    block = describe(SLEEP, derived)

    assert (block["state"], block["count"]) == ("closed", 1)
    assert block["text"] == (
        "Se ha adoptado 1 vez para este tripulante; el 2026-12-01 08:00 UTC (CDR)."
    )
    last = block["last"]
    assert last == block["adoptions"][0]
    assert last["adopted_text"] == "Adoptada el 2026-12-01 08:00 UTC (CDR)."
    assert last["state_text"] == f"Se cerró (CDR): {REASON}"
    assert (last["closed_by"], last["closed_reason"]) == ("CDR", REASON)
    assert (last["adoption_index"], last["level_at_adoption"]) == (5, "concern")
    # La evaluación es EL MISMO objeto que da el seguimiento, no otra calculada aquí.
    assert last["evaluation"] is derived[0]["evaluation"]
    # Con sus mismas palabras, tras el rótulo de con qué compara: este cierre (como todos los
    # anteriores al 2026-10-13) no guardó el nivel (`tests/test_close_level.py`).
    assert last["evaluation_text"] == (
        f"{LABEL_CURRENT_STATE} {derived[0]['evaluation']['text']}"
    )
    # Y se dice con qué compara, porque no es el nivel del cierre.
    assert block["evaluation_basis"] == EVALUATION_BASIS
    assert block["caveat"] == CAVEAT


def test_the_evaluation_keeps_the_followup_causality_note_when_checks_were_repeated() -> None:
    decisions = [
        _decision(5, "adopted", T0),
        _decision(9, "closed", T0, adoption_index="5", reason=REASON),
    ]
    derived = _followups(decisions, T0 + dt.timedelta(days=10), RiskLevel.NOMINAL)
    # Sin repetir la medida, el seguimiento dice que no hay con qué evaluar; se repite tal cual.
    last = describe(SLEEP, derived)["last"]
    assert last["evaluation"]["outcome"] == "no_repeat"
    assert last["repeated_checks_display"] == []
    assert last["checks_text"].endswith("No se repitió ninguna después de adoptarla.")

    reading = VitalObservation(
        code=get("sleep-duration"), value=7.0, effective=T0 + dt.timedelta(hours=30),
        subject="crew-01", source="simulator",
    )
    derived = followups(
        decisions, {"behavioral": RiskLevel.NOMINAL}, [reading], T0 + dt.timedelta(days=10)
    )
    last = describe(SLEEP, derived)["last"]
    assert last["evaluation_text"].endswith(CAUSALITY_NOTE)
    assert last["repeated_checks_display"] == last["followup_checks_display"] != []
    assert last["checks_text"].endswith("Se repitió después de adoptarla.")


@pytest.mark.parametrize(
    ("hours", "fragment"),
    [(10, "su ventana termina el 2026-12-03 08:00 UTC"),
     (100, "su ventana terminó el 2026-12-03 08:00 UTC y está sin cerrar")],
)
def test_an_open_adoption_is_in_followup_and_gives_no_evaluation(hours: int, fragment: str) -> None:
    derived = _followups(
        [_decision(5, "adopted", T0)], T0 + dt.timedelta(hours=hours), RiskLevel.NOMINAL
    )
    block = describe(SLEEP, derived)
    last = block["last"]
    assert (block["state"], last["state"]) == ("open", "open")
    assert last["state_text"].startswith("Sigue en seguimiento: ")
    assert fragment in last["state_text"]
    # Fuera de ventana el seguimiento YA tiene una evaluación provisional: aquí no se da.
    assert (derived[0]["evaluation"] is not None) == (hours == 100)
    assert last["evaluation"] is None
    assert last["evaluation_text"] == OPEN_NO_EVALUATION
    assert (last["closed_by"], last["closed_reason"]) == (None, None)


def test_several_adoptions_are_counted_and_the_last_is_by_ledger_order() -> None:
    later = T0 + dt.timedelta(days=20)
    decisions = [
        _decision(30, "adopted", later),
        _decision(5, "adopted", T0),
        _decision(9, "closed", T0, adoption_index="5", reason=REASON),
        # Otra contramedida: no cuenta para esta.
        _decision(12, "adopted", T0, "bh-circadian-lighting"),
        # Un «no» no es una adopción.
        _decision(14, "declined", T0, reason="no esta semana"),
    ]
    derived = _followups(decisions, later + dt.timedelta(hours=1), RiskLevel.CONCERN)
    block = describe(SLEEP, derived)
    assert block["count"] == 2
    assert [item["adoption_index"] for item in block["adoptions"]] == [5, 30]
    assert block["last"]["adoption_index"] == 30 and block["state"] == "open"
    # «La última» es la del ledger, lleguen los seguimientos en el orden que lleguen.
    assert describe(SLEEP, list(reversed(derived))) == block
    assert block["text"] == (
        "Se ha adoptado 2 veces para este tripulante; la última, el 2026-12-21 08:00 UTC (CDR)."
    )
    # La primera, cerrada, conserva su cierre y su evaluación.
    assert block["adoptions"][0]["state_text"] == f"Se cerró (CDR): {REASON}"
    assert block["adoptions"][0]["evaluation"] is not None
    assert describe("bh-circadian-lighting", derived)["count"] == 1
    assert describe("bh-repeat-pvt", derived)["text"] == NO_PRIOR


def test_no_text_claims_a_cause_a_rate_or_gives_an_order() -> None:
    later = T0 + dt.timedelta(days=20)
    decisions = [
        _decision(5, "adopted", T0),
        _decision(9, "closed", T0, adoption_index="5", reason="cerrado"),
        _decision(30, "adopted", later),
    ]
    for level in RiskLevel:
        for now in (later + dt.timedelta(hours=1), later + dt.timedelta(days=9)):
            text = _texts(describe(SLEEP, _followups(decisions, now, level))).lower()
            for word in (*FORBIDDEN, "debe ", "deben ", "hay que"):
                assert word not in text, (word, text)
    for word in FORBIDDEN:
        assert word not in _texts(describe(SLEEP, [])).lower()


def test_annotating_only_adds_a_field_in_the_same_order() -> None:
    recommendations = [
        {"domain": "behavioral", "action": "a", "urgency": "soon",
         "countermeasure": {"id": SLEEP}, "decision": None},
        {"domain": "behavioral", "action": "b", "urgency": "routine",
         "countermeasure": {"id": "bh-repeat-pvt"}, "decision": None},
        {"domain": "radiation", "action": "c", "urgency": "immediate",
         "countermeasure": None, "decision": None},
    ]
    derived = _followups([_decision(5, "adopted", T0)], T0, RiskLevel.CONCERN)
    annotated = with_prior_response(recommendations, derived)
    assert [
        {key: value for key, value in item.items() if key != "prior_response"}
        for item in annotated
    ] == recommendations
    assert annotated[0]["prior_response"]["count"] == 1
    assert annotated[1]["prior_response"]["text"] == NO_PRIOR
    # Sin contramedida no hay historia que contar: `None`, no un bloque vacío.
    assert annotated[2]["prior_response"] is None


# --------------------------------------------------------------------------- #
# API: el estado
# --------------------------------------------------------------------------- #


@pytest.fixture
def insomnia(client: TestClient) -> dict[str, Any]:
    assert client.post(
        "/api/simulate", params={"scenario": "progressive-insomnia", "days": 40}
    ).status_code == 201
    status: dict[str, Any] = client.get("/api/status").json()
    return status


def _adopt(client: TestClient, status: dict[str, Any], ident: str) -> int:
    response = client.post("/api/countermeasures/adopt", json={
        "countermeasure_id": ident, "reference_time": status["data"]["reference_time"],
        "adopted_by": "CDR",
    })
    assert response.status_code == 201, response.text
    return int(response.json()["ledger_index"])


def _close(client: TestClient, index: int) -> None:
    assert client.post("/api/countermeasures/close", json={
        "adoption_index": index, "reason": REASON, "closed_by": "CDR",
    }).status_code == 201


def _by_measure(status: dict[str, Any]) -> dict[str, Any]:
    return {
        item["countermeasure"]["id"]: item["prior_response"]
        for item in status["recommendations"] if item["countermeasure"]
    }


def test_the_status_says_there_is_no_prior_adoption(insomnia: dict[str, Any]) -> None:
    assert insomnia["recommendations"]
    for item in insomnia["recommendations"]:
        if item["countermeasure"] is None:
            assert item["prior_response"] is None
        else:
            assert item["prior_response"]["text"] == NO_PRIOR
            assert item["prior_response"]["caveat"] == CAVEAT


def test_a_recommendation_made_again_brings_what_happened_last_time(
    client: TestClient, insomnia: dict[str, Any]
) -> None:
    chosen = insomnia["recommendations"][0]["countermeasure"]["id"]
    index = _adopt(client, insomnia, chosen)

    open_status = client.get("/api/status").json()
    block = _by_measure(open_status)[chosen]
    assert (block["state"], block["count"]) == ("open", 1)
    assert block["last"]["state_text"].startswith("Sigue en seguimiento: ")
    assert block["last"]["evaluation"] is None

    _close(client, index)
    status = client.get("/api/status").json()
    # Sigue recomendándose, y ahora trae lo de la otra vez.
    block = _by_measure(status)[chosen]
    assert (block["state"], block["count"]) == ("closed", 1)
    assert block["last"]["adoption_index"] == index
    # El cierre guardó el instante de su estado: el de los datos, que es el de `insomnia`.
    closed = dt.datetime.fromisoformat(insomnia["data"]["reference_time"])
    assert block["last"]["state_text"] == (
        f"Se cerró el {closed:%Y-%m-%d %H:%M} UTC (CDR): {REASON}"
    )
    assert block["caveat"] == CAVEAT
    # La evaluación es la que el estado ya sirve en `followups`, con sus mismas palabras: la del
    # cierre, porque este cierre guardó el nivel.
    [follow] = status["followups"]
    assert block["last"]["evaluation"] == follow["evaluation_at_close"]
    assert block["last"]["evaluation_text"] == (
        f"{LABEL_AT_CLOSE} {follow['evaluation_at_close']['text']}"
    )
    # Las demás contramedidas no heredan la historia de esta.
    assert all(
        other["text"] == NO_PRIOR for ident, other in _by_measure(status).items()
        if ident != chosen
    )


def _without_block(status: dict[str, Any]) -> dict[str, Any]:
    return {
        **status,
        "recommendations": [
            {key: value for key, value in item.items() if key != "prior_response"}
            for item in status["recommendations"]
        ],
    }


def test_the_block_changes_nothing_else_on_the_same_ledger(
    client: TestClient, insomnia: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invariante 5: mismo ledger, con la pieza y sin ella. Solo difiere `prior_response`."""
    assert insomnia["alerts"]
    chosen = insomnia["recommendations"][0]["countermeasure"]["id"]
    _close(client, _adopt(client, insomnia, chosen))
    _adopt(client, insomnia, chosen)
    # Un corte fijo (el de los datos): el estado de Tierra no firma instantáneas ni mira el reloj.
    params = {"until": insomnia["data"]["reference_time"]}

    with_block = client.get("/api/status", params=params).json()
    assert _by_measure(with_block)[chosen]["count"] == 2

    monkeypatch.setattr(routes, "with_prior_response", lambda recs, _followups: list(recs))
    without = client.get("/api/status", params=params).json()
    assert all("prior_response" not in item for item in without["recommendations"])

    # Mismas recomendaciones en el mismo orden, mismos niveles, alertas y seguimientos…
    assert [item["action"] for item in with_block["recommendations"]] == [
        item["action"] for item in without["recommendations"]]
    assert with_block["overall_level"] == without["overall_level"]
    assert with_block["domains"] == without["domains"]
    assert with_block["alerts"] == without["alerts"]
    assert with_block["followups"] == without["followups"]
    # …y, de hecho, el estado entero.
    assert _without_block(with_block) == without


def test_ground_only_sees_adoptions_made_before_its_cut(
    client: TestClient, insomnia: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    chosen = insomnia["recommendations"][0]["countermeasure"]["id"]
    _close(client, _adopt(client, insomnia, chosen))
    cut = insomnia["data"]["reference_time"]

    seen = client.get("/api/status", params={"until": cut}).json()
    assert _by_measure(seen)[chosen]["count"] == 1

    # Las mismas decisiones, firmadas DESPUÉS del corte de Tierra: todavía no las puede ver.
    store = routes.get_store()
    signed = store.followup_decisions
    after = (dt.datetime.fromisoformat(cut) + dt.timedelta(minutes=5)).isoformat()
    monkeypatch.setattr(
        store, "followup_decisions",
        lambda subject: [{**item, "recorded": after} for item in signed(subject)],
    )
    past = client.get("/api/status", params={"until": cut}).json()
    assert past["followups"] == []
    assert _by_measure(past)[chosen]["text"] == NO_PRIOR


def test_an_adoption_signed_by_another_identity_is_not_prior_response(
    client: TestClient, insomnia: dict[str, Any]
) -> None:
    chosen = insomnia["recommendations"][0]["countermeasure"]["id"]
    measure = countermeasures.get(chosen)
    assert measure.domain is not None
    routes.get_store().record_followup(
        "crew-01", "adopted", chosen, str(measure.domain), "concern",
        dt.datetime.fromisoformat(insomnia["data"]["reference_time"]), "CDR",
        Identity.generate("wearable-01"),
    )
    status = client.get("/api/status").json()
    assert status["followups"] == []
    assert _by_measure(status)[chosen]["text"] == NO_PRIOR
