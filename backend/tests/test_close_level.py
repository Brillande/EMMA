"""El nivel, al cerrar una adopción (decisión del usuario, 2026-10-13).

El cierre de una contramedida no guardaba el nivel del dominio, así que de una adopción cerrada
hace tiempo solo se podía decir «cómo está hoy frente a entonces». Desde ese día el asiento de
cierre lleva, como campos OPCIONALES, el nivel del dominio en el estado del instante del cierre.
Estas pruebas fijan lo que eso es y lo que no:

* lo calcula el backend, no lo manda el cliente, y va por el ledger en el asiento de siempre;
* un cierre firmado antes del cambio sigue verificándose (invariante 4) y de él se dice que no
  guardó el nivel: no se le inventa;
* la evaluación «frente al estado que se mira» no cambia; la del cierre se añade AL LADO;
* es una copia de lo que el motor ya calculó: no mueve niveles, alertas ni recomendaciones
  (invariante 5), y sigue siendo la comparación de dos niveles, no una valoración (invariante 7).
"""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.advisor.followup import CAUSALITY_NOTE, followups
from app.advisor.prior_response import (
    AT_CLOSE,
    CAVEAT,
    CURRENT_STATE,
    EVALUATION_BASIS,
    EVALUATION_BASIS_AT_CLOSE,
    EVALUATION_BASIS_MIXED,
    LABEL_AT_CLOSE,
    LABEL_CURRENT_STATE,
    describe,
)
from app.analysis.risk import RiskLevel
from app.api import routes
from app.core import storage
from app.core.ledger import Identity
from app.core.storage import _FOLLOWUP_FIELDS, _FOLLOWUP_OPTIONAL, ObservationStore
from app.ingest.codes import Domain, get
from app.ingest.fhir import VitalObservation

T0 = dt.datetime(2026, 12, 1, 8, 0, tzinfo=dt.UTC)
CLOSED_AT = T0 + dt.timedelta(days=3)
NOW = T0 + dt.timedelta(days=30)
SLEEP = "bh-protect-sleep"  # una medida de seguimiento que repetir: la duración del sueño
REASON = "sueño recuperado tras dos noches"
BEHAVIORAL = Domain.BEHAVIORAL.display
# Lo que ningún texto puede decir: sería afirmar una causa, una eficacia o una tasa.
FORBIDDEN = ("eficaz", "eficacia", "funcion", "respondió bien", "éxito", "exito", "%", "mejor con")
# Ledger con una adopción y su cierre, escrito con el código de `main` ANTERIOR a este cambio
# (commit 7efaf69, exportado con `git archive main backend/app polaris`) y guardado tal cual.
# Los hashes de contenido son los que firmó aquel código.
PRE_CHANGE_LEDGER = Path(__file__).parent / "data" / "followup_pre_close_level.db"
PRE_CHANGE_HASHES = [
    "e6778d9dabb103d6834ea864feecc64e84727a6b9f4e06f2dbddaa5aa5562c64",
    "063d2dd3bfea42f9034ebb7bd2d55f3ab71dc3bf45a054fbbb6b11a855e2157a",
]


def _decision(index: int, action: str, when: dt.datetime = T0, **extra: str) -> dict[str, Any]:
    return {
        "ledger_index": index, "action": action, "countermeasure_id": SLEEP,
        "domain": "behavioral", "level": "concern", "reference_time": when.isoformat(),
        "decided_by": "CDR", "reason": "", "adoption_index": "", **extra,
    }


def _closure(index: int, adoption: int, level: str | None = None, **extra: str) -> dict[str, Any]:
    """Un cierre; con `level`, como los firmados desde el cambio."""
    at_close = (
        {"level_at_close": level, "closed_reference_time": CLOSED_AT.isoformat()}
        if level is not None else {}
    )
    return _decision(
        index, "closed", adoption_index=str(adoption), reason=REASON,
        recorded="2026-12-04T09:30:00+00:00", **{**at_close, **extra},
    )


def _sleep_reading(when: dt.datetime) -> VitalObservation:
    return VitalObservation(
        code=get("sleep-duration"), value=7.0, effective=when, subject="crew-01",
        source="simulator",
    )


def _one(decisions: list[dict[str, Any]], level: RiskLevel, *readings: VitalObservation) -> dict:
    [follow] = followups(decisions, {"behavioral": level}, list(readings), NOW)
    return follow


# --------------------------------------------------------------------------- #
# El seguimiento: la comparación al cierre, AL LADO de la de siempre
# --------------------------------------------------------------------------- #


def test_a_closure_that_saved_the_level_gives_a_second_comparison() -> None:
    reading = _sleep_reading(T0 + dt.timedelta(hours=30))
    follow = _one(
        [_decision(5, "adopted"), _closure(9, 5, "watch")], RiskLevel.CRITICAL, reading
    )
    assert follow["state"] == "closed"
    assert follow["level_at_adoption"] == "concern"
    assert follow["level_at_close"] == "watch"
    assert follow["closed_at"] == CLOSED_AT.isoformat()
    assert follow["closed_recorded_at"] == "2026-12-04T09:30:00+00:00"
    # Al cierre: de precaución a vigilancia, aunque HOY el dominio esté en crítico.
    assert follow["evaluation_at_close"] == {
        "outcome": "improved",
        "text": (
            f"El dominio {BEHAVIORAL} pasó de {RiskLevel.CONCERN.display} a "
            f"{RiskLevel.WATCH.display} entre la adopción y el cierre. {CAUSALITY_NOTE}"
        ),
    }
    # Y la de siempre, frente al estado que se mira, sigue diciendo lo de hoy.
    assert follow["evaluation"]["outcome"] == "worsened"


@pytest.mark.parametrize("current", list(RiskLevel))
def test_the_comparison_at_close_does_not_move_with_the_current_state(
    current: RiskLevel,
) -> None:
    decisions = [_decision(5, "adopted"), _closure(9, 5, "watch")]
    reading = _sleep_reading(T0 + dt.timedelta(hours=30))
    reference = _one(decisions, RiskLevel.NOMINAL, reading)
    follow = _one(decisions, current, reading)
    assert follow["evaluation_at_close"] == reference["evaluation_at_close"]
    assert (follow["level_at_close"], follow["closed_at"]) == ("watch", CLOSED_AT.isoformat())


@pytest.mark.parametrize("current", list(RiskLevel))
@pytest.mark.parametrize("saved", ["nominal", "watch", "concern", "critical"])
def test_the_evaluation_against_the_state_looked_at_is_the_same_with_and_without_the_field(
    current: RiskLevel, saved: str
) -> None:
    """Lo que ya existía no cambia: mismo seguimiento, salvo los cuatro campos del cierre."""
    reading = _sleep_reading(T0 + dt.timedelta(hours=30))
    new = _one([_decision(5, "adopted"), _closure(9, 5, saved)], current, reading)
    old = _one([_decision(5, "adopted"), _closure(9, 5)], current, reading)
    added = {"closed_at", "level_at_close", "evaluation_at_close"}
    assert {key: value for key, value in new.items() if key not in added} == {
        key: value for key, value in old.items() if key not in added
    }
    assert (old["closed_at"], old["level_at_close"], old["evaluation_at_close"]) == (
        None, None, None)


def test_a_closure_signed_before_the_change_has_no_level_and_none_is_invented() -> None:
    follow = _one([_decision(5, "adopted"), _closure(9, 5)], RiskLevel.NOMINAL)
    assert follow["state"] == "closed"
    assert (follow["closed_by"], follow["closed_reason"]) == ("CDR", REASON)
    assert follow["level_at_close"] is None
    assert follow["closed_at"] is None
    assert follow["evaluation_at_close"] is None
    # Cuándo se firmó sí consta: lo lleva todo asiento.
    assert follow["closed_recorded_at"] == "2026-12-04T09:30:00+00:00"
    assert follow["evaluation"] is not None


def test_an_open_adoption_has_nothing_of_a_closure() -> None:
    [follow] = followups([_decision(5, "adopted")], {"behavioral": RiskLevel.WATCH}, [], NOW)
    assert follow["state"] == "due"
    assert (
        follow["closed_at"], follow["closed_recorded_at"], follow["level_at_close"],
        follow["evaluation_at_close"],
    ) == (None, None, None, None)


def test_the_same_level_at_both_ends_is_said_as_unchanged_in_the_past() -> None:
    follow = _one(
        [_decision(5, "adopted"), _closure(9, 5, "concern")], RiskLevel.NOMINAL,
        _sleep_reading(T0 + dt.timedelta(hours=30)),
    )
    assert follow["evaluation_at_close"] == {
        "outcome": "unchanged",
        "text": (
            f"El dominio {BEHAVIORAL} siguió en {RiskLevel.CONCERN.display} entre la adopción "
            f"y el cierre. {CAUSALITY_NOTE}"
        ),
    }


def test_a_level_that_went_up_before_the_closure_is_said_too() -> None:
    follow = _one(
        [_decision(5, "adopted"), _closure(9, 5, "critical")], RiskLevel.NOMINAL,
        _sleep_reading(T0 + dt.timedelta(hours=30)),
    )
    assert follow["evaluation_at_close"]["outcome"] == "worsened"
    assert follow["evaluation"]["outcome"] == "improved"


def test_what_was_repeated_counts_up_to_the_closure_to_compare_like_with_like() -> None:
    decisions = [_decision(5, "adopted"), _closure(9, 5, "nominal")]
    # Repetida DESPUÉS del cierre: hoy hay con qué evaluar; al cierre no lo había.
    late = _one(decisions, RiskLevel.NOMINAL, _sleep_reading(CLOSED_AT + dt.timedelta(hours=1)))
    assert late["evaluation"]["outcome"] == "improved"
    assert late["evaluation_at_close"]["outcome"] == "no_repeat"
    assert late["evaluation_at_close"]["text"] == (
        f"No se había repetido la medida de seguimiento ({get('sleep-duration').display_es}) "
        f"entre la adopción y el cierre: no hay con qué evaluar."
    )
    # Una lectura anterior a la adopción tampoco es una repetición.
    early = _one(decisions, RiskLevel.NOMINAL, _sleep_reading(T0 - dt.timedelta(hours=1)))
    assert early["evaluation_at_close"]["outcome"] == "no_repeat"
    # En el instante mismo del estado del cierre, sí: es la última lectura que vio quien cerró.
    exact = _one(decisions, RiskLevel.NOMINAL, _sleep_reading(CLOSED_AT))
    assert exact["evaluation_at_close"]["outcome"] == "improved"


@pytest.mark.parametrize(
    "broken",
    [
        {"level_at_close": "verde"},
        {"closed_reference_time": "ayer"},
        # Un instante sin zona horaria es ambiguo: no se sitúa.
        {"closed_reference_time": "2026-12-04T08:00:00"},
    ],
)
def test_an_unreadable_copy_is_treated_as_not_saved_and_never_breaks_the_state(
    broken: dict[str, str],
) -> None:
    follow = _one([_decision(5, "adopted"), _closure(9, 5, "watch", **broken)], RiskLevel.WATCH)
    assert follow["state"] == "closed"
    assert (follow["level_at_close"], follow["closed_at"], follow["evaluation_at_close"]) == (
        None, None, None)
    assert follow["evaluation"] is not None


# --------------------------------------------------------------------------- #
# La respuesta previa: con qué compara, dicho
# --------------------------------------------------------------------------- #


def _derived(*decisions: dict[str, Any], level: RiskLevel = RiskLevel.CRITICAL) -> list[dict]:
    reading = _sleep_reading(T0 + dt.timedelta(hours=30))
    return followups(list(decisions), {"behavioral": level}, [reading], NOW)


def test_prior_response_uses_the_comparison_at_close_and_says_so() -> None:
    derived = _derived(_decision(5, "adopted"), _closure(9, 5, "watch"))
    block = describe(SLEEP, derived)
    last = block["last"]
    # EL MISMO objeto que da el seguimiento: aquí no se evalúa nada.
    assert last["evaluation"] is derived[0]["evaluation_at_close"]
    assert last["evaluation_basis"] == AT_CLOSE == "at_close"
    assert last["evaluation_text"] == (
        f"{LABEL_AT_CLOSE} {derived[0]['evaluation_at_close']['text']}"
    )
    assert last["evaluation_text"].startswith("Al cierre: El dominio ")
    assert (last["level_at_close"], last["closed_at"]) == ("watch", CLOSED_AT.isoformat())
    assert last["closed_recorded_at"] == "2026-12-04T09:30:00+00:00"
    assert last["state_text"] == f"Se cerró el 2026-12-04 08:00 UTC (CDR): {REASON}"
    assert block["evaluation_basis"] == EVALUATION_BASIS_AT_CLOSE
    assert "con el que el cierre dejó guardado, no con el de este estado" in (
        block["evaluation_basis"])
    # La advertencia de siempre, sin tocar.
    assert block["caveat"] == CAVEAT
    assert "lo que pasó después, no una prueba de que fuera por la contramedida" in CAVEAT


def test_an_old_closure_is_compared_with_the_current_state_and_labelled_as_such() -> None:
    derived = _derived(_decision(5, "adopted"), _closure(9, 5))
    block = describe(SLEEP, derived)
    last = block["last"]
    assert last["evaluation"] is derived[0]["evaluation"]
    assert last["evaluation_basis"] == CURRENT_STATE == "current_state"
    assert LABEL_CURRENT_STATE == (
        "Este cierre no guardó el nivel: se compara con el estado actual."
    )
    assert last["evaluation_text"] == f"{LABEL_CURRENT_STATE} {derived[0]['evaluation']['text']}"
    assert (last["level_at_close"], last["closed_at"]) == (None, None)
    # Sin instante del estado del cierre no se le pone fecha al texto: no se inventa.
    assert last["state_text"] == f"Se cerró (CDR): {REASON}"
    assert block["evaluation_basis"] == EVALUATION_BASIS
    assert "porque el cierre no lo guardó" in block["evaluation_basis"]
    assert block["caveat"] == CAVEAT


def test_a_block_with_both_kinds_of_closure_says_each_one_tells_its_own() -> None:
    later = T0 + dt.timedelta(days=10)
    derived = _derived(
        _decision(5, "adopted"), _closure(9, 5),
        _decision(20, "adopted", later), _closure(24, 20, "watch"),
        _decision(30, "adopted", later),
    )
    block = describe(SLEEP, derived)
    assert [item["evaluation_basis"] for item in block["adoptions"]] == [
        CURRENT_STATE, AT_CLOSE, None]
    assert block["evaluation_basis"] == EVALUATION_BASIS_MIXED
    # Sin ninguna adopción cerrada no hay evaluación, y no se dice con qué compara.
    assert describe(SLEEP, _derived(_decision(5, "adopted")))["evaluation_basis"] is None


def test_no_text_about_the_closure_claims_a_cause_a_rate_or_gives_an_order() -> None:
    for saved in ("nominal", "watch", "concern", "critical", None):
        for level in RiskLevel:
            for readings in ([], [_sleep_reading(T0 + dt.timedelta(hours=30))]):
                derived = followups(
                    [_decision(5, "adopted"), _closure(9, 5, saved)],
                    {"behavioral": level}, readings, NOW,
                )
                block = describe(SLEEP, derived)
                parts = [block["text"], block["caveat"], block["evaluation_basis"] or ""]
                for item in block["adoptions"]:
                    parts += [item["state_text"].replace(REASON, ""), item["evaluation_text"]]
                at_close = derived[0]["evaluation_at_close"]
                parts.append(at_close["text"] if at_close else "")
                text = " ".join(parts).lower()
                for word in (*FORBIDDEN, "debe ", "deben ", "hay que"):
                    assert word not in text, (word, text)


# --------------------------------------------------------------------------- #
# Ledger: campos opcionales del asiento de siempre; lo ya firmado sigue verificándose
# --------------------------------------------------------------------------- #


def _public(payload: dict[str, Any]) -> set[str]:
    return {key for key in payload if not key.startswith("_")}


def test_only_a_closure_carries_the_level_and_without_it_the_entry_is_the_old_one() -> None:
    store = ObservationStore.in_memory()
    console = Identity.generate("crew-console")
    adoption = store.record_followup(
        "crew-01", "adopted", SLEEP, "behavioral", "concern", T0, "CDR", console
    )
    assert _public(adoption.payload) == set(_FOLLOWUP_FIELDS)
    # Dicho en otra zona horaria: es el mismo instante, y el seguimiento lo da en UTC.
    local = CLOSED_AT.astimezone(dt.timezone(dt.timedelta(hours=2)))
    closure = store.record_followup(
        "crew-01", "closed", SLEEP, "behavioral", "concern", T0, "CDR", console,
        reason=REASON, adoption_index=adoption.index,
        level_at_close="watch", closed_reference_time=local,
    )
    assert _FOLLOWUP_OPTIONAL == ("level_at_close", "closed_reference_time")
    assert _public(closure.payload) == {*_FOLLOWUP_FIELDS, *_FOLLOWUP_OPTIONAL}
    assert closure.payload["level_at_close"] == "watch"
    assert dt.datetime.fromisoformat(closure.payload["closed_reference_time"]) == CLOSED_AT
    # El nivel al ADOPTAR sigue en `level`: el cierre no lo pisa.
    assert closure.payload["level"] == "concern"
    # Un cierre sin la copia es, campo por campo, el de antes del cambio.
    second = store.record_followup(
        "crew-01", "adopted", SLEEP, "behavioral", "concern", T0, "CDR", console
    )
    bare = store.record_followup(
        "crew-01", "closed", SLEEP, "behavioral", "concern", T0, "CDR", console,
        reason=REASON, adoption_index=second.index,
    )
    assert _public(bare.payload) == set(_FOLLOWUP_FIELDS)
    assert store.verify_integrity().ok

    read = store.followup_decisions("crew-01")
    assert [("level_at_close" in item, "closed_reference_time" in item) for item in read] == [
        (False, False), (True, True), (False, False), (False, False)]
    assert read[1]["level_at_close"] == "watch"
    follow = followups(read, {"behavioral": RiskLevel.WATCH}, [], NOW)[0]
    assert follow["closed_at"] == CLOSED_AT.isoformat() == "2026-12-04T08:00:00+00:00"


def test_the_store_refuses_half_a_copy_or_a_level_at_close_outside_a_closure() -> None:
    store = ObservationStore.in_memory()
    console = Identity.generate("crew-console")
    closing = ("crew-01", "closed", SLEEP, "behavioral", "concern", T0, "CDR", console)
    with pytest.raises(ValueError, match="van juntos"):
        store.record_followup(*closing, reason=REASON, adoption_index=0, level_at_close="watch")
    with pytest.raises(ValueError, match="van juntos"):
        store.record_followup(
            *closing, reason=REASON, adoption_index=0, closed_reference_time=CLOSED_AT
        )
    for action, reason in (("adopted", ""), ("declined", REASON)):
        with pytest.raises(ValueError, match="solo lo lleva un cierre"):
            store.record_followup(
                "crew-01", action, SLEEP, "behavioral", "concern", T0, "CDR", console,
                reason=reason, level_at_close="watch", closed_reference_time=CLOSED_AT,
            )
    assert store.followup_decisions("crew-01") == []


def test_a_ledger_signed_before_the_change_still_verifies_and_accepts_a_closure_with_level(
    tmp_path: Path,
) -> None:
    path = tmp_path / "emma.db"
    shutil.copyfile(PRE_CHANGE_LEDGER, path)
    store = ObservationStore.at(path)

    assert store.verify_integrity().ok
    old = store.followup_decisions("crew-01")
    assert [item["action"] for item in old] == ["adopted", "closed"]
    assert [entry["content_hash"] for entry in store.audit_trail()] == PRE_CHANGE_HASHES
    assert all(field not in item for item in old for field in _FOLLOWUP_OPTIONAL)
    # Se lee como antes —una adopción cerrada, con su evaluación frente al estado que se mira—
    # y de su cierre se dice lo que se puede afirmar: que no guardó el nivel.
    [follow] = followups(old, {"behavioral": RiskLevel.WATCH}, [], NOW)
    assert (follow["state"], follow["closed_reason"]) == ("closed", REASON)
    assert follow["evaluation"] is not None
    assert (follow["level_at_close"], follow["closed_at"], follow["evaluation_at_close"]) == (
        None, None, None)
    assert follow["closed_recorded_at"] == old[1]["recorded"]
    last = describe(SLEEP, [follow])["last"]
    assert last["evaluation_basis"] == CURRENT_STATE
    assert last["evaluation_text"].startswith(LABEL_CURRENT_STATE)

    # Sobre esa misma cadena, una adopción nueva y su cierre CON el nivel.
    console = Identity.generate("otra-consola")
    adoption = store.record_followup(
        "crew-01", "adopted", SLEEP, "behavioral", "concern", CLOSED_AT, "CDR", console
    )
    store.record_followup(
        "crew-01", "closed", SLEEP, "behavioral", "concern", CLOSED_AT, "CDR", console,
        reason="otra vez", adoption_index=adoption.index,
        level_at_close="nominal", closed_reference_time=NOW,
    )
    assert store.verify_integrity().ok
    store.engine.dispose()

    reopened = ObservationStore.at(path)
    assert reopened.verify_integrity().ok
    assert [entry["content_hash"] for entry in reopened.audit_trail()][:2] == PRE_CHANGE_HASHES
    decisions = reopened.followup_decisions("crew-01")
    assert [item.get("level_at_close") for item in decisions] == [None, None, None, "nominal"]
    first, second = followups(decisions, {"behavioral": RiskLevel.WATCH}, [], NOW)
    assert (first["level_at_close"], second["level_at_close"]) == (None, "nominal")
    reopened.engine.dispose()


# --------------------------------------------------------------------------- #
# API: la ruta de cierre y el estado
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


def _close(client: TestClient, index: int, **extra: Any) -> Any:
    return client.post("/api/countermeasures/close", json={
        "adoption_index": index, "reason": REASON, "closed_by": "CDR", **extra,
    })


def _levels(status: dict[str, Any]) -> dict[str, str]:
    return {name: item["level"] for name, item in status["domains"].items()}


def _chosen(status: dict[str, Any]) -> dict[str, Any]:
    first: dict[str, Any] = next(
        item for item in status["recommendations"] if item["countermeasure"]
    )
    return first


def test_closing_saves_the_level_the_backend_computed_not_one_sent_by_the_client(
    client: TestClient, insomnia: dict[str, Any]
) -> None:
    offered = _chosen(insomnia)
    ident, domain = offered["countermeasure"]["id"], offered["domain"]
    index = _adopt(client, insomnia, ident)

    # El cliente no puede mandarlo: el cuerpo no tiene ese campo y rechaza los que sobran.
    for extra in ({"level_at_close": "nominal"}, {"closed_reference_time": T0.isoformat()}):
        assert _close(client, index, **extra).status_code == 422
    assert [
        item["action"]
        for item in client.get("/api/countermeasures/decisions").json()["decisions"]
    ] == ["adopted"]

    response = _close(client, index)
    assert response.status_code == 201, response.text
    closure = client.get("/api/countermeasures/decisions").json()["decisions"][-1]
    assert closure["ledger_index"] == response.json()["ledger_index"]
    assert (closure["action"], closure["adoption_index"]) == ("closed", str(index))
    # El nivel de ESE dominio en el estado de ese instante, y ese instante.
    assert closure["level_at_close"] == _levels(insomnia)[domain]
    assert dt.datetime.fromisoformat(closure["closed_reference_time"]) == (
        dt.datetime.fromisoformat(insomnia["data"]["reference_time"])
    )
    # El nivel al adoptar sigue donde estaba.
    assert closure["level"] == _levels(insomnia)[domain]
    assert routes.get_store().verify_integrity().ok

    status = client.get("/api/status").json()
    [follow] = status["followups"]
    assert follow["level_at_close"] == closure["level_at_close"]
    assert follow["closed_at"] == insomnia["data"]["reference_time"]
    assert follow["closed_recorded_at"] == closure["recorded"]
    assert follow["evaluation_at_close"]["outcome"] in (
        "unchanged", "improved", "worsened", "no_repeat")
    assert follow["evaluation"] is not None

    # La respuesta previa compara con el cierre, y lo dice.
    block = next(
        item["prior_response"] for item in status["recommendations"]
        if (item["countermeasure"] or {}).get("id") == ident
    )
    assert block["last"]["evaluation"] == follow["evaluation_at_close"]
    assert block["last"]["evaluation_basis"] == AT_CLOSE
    assert block["last"]["evaluation_text"] == (
        f"{LABEL_AT_CLOSE} {follow['evaluation_at_close']['text']}"
    )
    assert block["last"]["level_at_close"] == closure["level_at_close"]
    assert block["evaluation_basis"] == EVALUATION_BASIS_AT_CLOSE
    assert block["caveat"] == CAVEAT

    # `/anatomy/state` sirve las recomendaciones con lo mismo que `/status`.
    anatomy = client.get("/api/anatomy/state").json()
    served = [
        item["prior_response"] for region in anatomy["regions"]
        for item in region["recommendations"]
        if (item["countermeasure"] or {}).get("id") == ident
    ]
    assert served and all(item == block for item in served)


def test_the_level_saved_is_the_one_of_the_closing_state_not_the_one_at_adoption(
    client: TestClient, insomnia: dict[str, Any]
) -> None:
    """Adoptada cuando el dominio estaba más bajo y cerrada hoy: el cierre guarda el de hoy."""
    now = dt.datetime.fromisoformat(insomnia["data"]["reference_time"])
    earlier = (now - dt.timedelta(days=20)).isoformat()
    then = client.get("/api/status", params={"until": earlier}).json()
    offered = _chosen(then)
    ident, domain = offered["countermeasure"]["id"], offered["domain"]
    before, at_close = _levels(then)[domain], _levels(insomnia)[domain]
    # El escenario empeora con los días: si dejara de hacerlo, esta prueba no probaría nada.
    assert before != at_close
    # Y el dominio no es el primero del estado ni comparte nivel con él.
    assert next(iter(_levels(insomnia).values())) != at_close

    response = client.post("/api/countermeasures/adopt", json={
        "countermeasure_id": ident, "reference_time": earlier, "adopted_by": "CDR",
    })
    assert response.status_code == 201, response.text
    assert _close(client, int(response.json()["ledger_index"])).status_code == 201

    closure = client.get("/api/countermeasures/decisions").json()["decisions"][-1]
    assert (closure["level"], closure["level_at_close"]) == (before, at_close)
    assert dt.datetime.fromisoformat(closure["closed_reference_time"]) == now

    [follow] = client.get("/api/status").json()["followups"]
    assert (follow["level_at_adoption"], follow["level_at_close"]) == (before, at_close)
    assert follow["evaluation_at_close"]["outcome"] == "worsened"
    assert follow["evaluation_at_close"]["text"] == (
        f"El dominio {Domain(domain).display} pasó de {RiskLevel(before).display} a "
        f"{RiskLevel(at_close).display} entre la adopción y el cierre. {CAUSALITY_NOTE}"
    )
    # Cerrar no movió ningún nivel.
    assert _levels(client.get("/api/status").json()) == _levels(insomnia)


def test_the_saved_level_decides_nothing_on_the_same_ledger(
    client: TestClient, insomnia: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invariante 5: mismo ledger, leído con el campo y sin él. Solo difiere lo descriptivo."""
    assert insomnia["alerts"] and insomnia["recommendations"]
    ident = _chosen(insomnia)["countermeasure"]["id"]
    assert _close(client, _adopt(client, insomnia, ident)).status_code == 201
    _adopt(client, insomnia, ident)
    # Un corte fijo (el de los datos): el estado de Tierra no firma instantáneas ni mira el reloj.
    params = {"until": insomnia["data"]["reference_time"]}

    with_field = client.get("/api/status", params=params).json()
    assert with_field["followups"][0]["level_at_close"] is not None

    # El mismo ledger, leído como lo leía el código anterior: sin los campos opcionales.
    monkeypatch.setattr(storage, "_FOLLOWUP_OPTIONAL", ())
    without = client.get("/api/status", params=params).json()
    assert without["followups"][0]["level_at_close"] is None
    assert without["followups"][0]["evaluation_at_close"] is None

    assert with_field["overall_level"] == without["overall_level"]
    assert with_field["domains"] == without["domains"]
    assert with_field["alerts"] == without["alerts"]

    def bare(item: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in item.items() if key != "prior_response"}

    # Las mismas recomendaciones, en el mismo orden, con todo lo demás igual.
    assert [bare(item) for item in with_field["recommendations"]] == [
        bare(item) for item in without["recommendations"]]
    # Y el estado entero no difiere en nada más que en los seguimientos y la respuesta previa.
    described = ("followups", "recommendations")
    assert {key: value for key, value in with_field.items() if key not in described} == {
        key: value for key, value in without.items() if key not in described
    }
    # En los seguimientos, la evaluación de siempre es la misma.
    added = {"closed_at", "level_at_close", "evaluation_at_close"}
    assert [
        {key: value for key, value in item.items() if key not in added}
        for item in with_field["followups"]
    ] == [
        {key: value for key, value in item.items() if key not in added}
        for item in without["followups"]
    ]
    # Y el estado inicial tenía esos mismos niveles: cerrar no movió ninguno.
    assert _levels(with_field) == _levels(insomnia)


def test_closing_without_a_state_to_copy_still_closes_and_says_nothing_of_the_level(
    client: TestClient,
) -> None:
    """Cerrar es una decisión humana: no se bloquea porque falte una copia descriptiva."""
    store = routes.get_store()
    adoption = store.record_followup(
        "crew-01", "adopted", SLEEP, "behavioral", "concern", T0, "CDR",
        routes.identity_for(routes.CONSOLE_IDENTITY),
    )
    assert client.get("/api/status").status_code == 404
    response = _close(client, adoption.index)
    assert response.status_code == 201, response.text
    closure = client.get("/api/countermeasures/decisions").json()["decisions"][-1]
    assert closure["action"] == "closed"
    assert "level_at_close" not in closure and "closed_reference_time" not in closure
    assert store.verify_integrity().ok
