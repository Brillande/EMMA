"""Rutas de la biblioteca de contramedidas y de su seguimiento.

Modulo aparte por lo mismo que el dolor: tiene su asiento propio en el ledger. Lo que comparte
con las alertas —el estado en un instante, la identidad de la consola, el 409 si se actua
sobre algo que no existe— se reutiliza de `routes.py`, no se copia.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.advisor import countermeasures, effects
from app.advisor.followup import (
    ADOPTED,
    CLOSED,
    DECLINE_MEANING,
    DECLINED,
    decision_note,
    open_adoption,
    standing_declines,
)
from app.api.routes import (
    CONSOLE_IDENTITY,
    SettingsDep,
    StoreDep,
    _assess,
    _counts,
    _recorded_or_422,
    crew_status,
    identity_for,
)
from app.core import i18n
from app.core.versioning import rules_version
from app.evidence import research_countermeasures

countermeasures_router = APIRouter(prefix="/countermeasures")

Operator = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


def _aware(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        raise ValueError("el instante debe llevar zona horaria")
    return value


class AdoptionIn(BaseModel):
    """Una persona declara que la tripulacion adopta una contramedida recomendada."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(default="crew-01", min_length=1)
    countermeasure_id: str = Field(min_length=1)
    # El instante del estado que vio quien decide: la recomendacion tiene que existir en el.
    reference_time: dt.datetime
    adopted_by: Operator

    _tz = field_validator("reference_time")(_aware)


class ClosureIn(BaseModel):
    """Una persona cierra el seguimiento de una adopcion, con su motivo."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(default="crew-01", min_length=1)
    adoption_index: int = Field(ge=0)
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    closed_by: Operator


class DeclineIn(BaseModel):
    """Una persona deja dicho que una contramedida recomendada NO se adopta, y por qué.

    Es el registro de una decisión, no una evaluación (`advisor/followup.py`). El motivo es
    texto libre de quien decide: va al asiento firmado y a la respuesta, nunca a un log.
    """

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(default="crew-01", min_length=1)
    countermeasure_id: str = Field(min_length=1)
    # El instante del estado que vio quien decide: la recomendacion tiene que existir en el.
    reference_time: dt.datetime
    reason: Annotated[str, StringConstraints(max_length=500)]
    declined_by: Operator

    _tz = field_validator("reference_time")(_aware)

    @field_validator("reason")
    @classmethod
    def _reason_given(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError(
                "el motivo no puede ir vacío: decidir no adoptar queda firmado con su porqué"
            )
        return text


@countermeasures_router.get("")
def list_countermeasures() -> dict[str, Any]:
    """La biblioteca entera: que se puede hacer, que cuesta y en que se apoya.

    Ademas de la lista, los grupos por peligro RIDGE y el vocabulario de familias con su
    criterio (`advisor/countermeasures.overview`): la interfaz pinta esas palabras, no las
    redacta. `countermeasures` conserva su forma de siempre y cada entrada lleva ademas sus
    efectos (`advisor/effects.py`): sobre que se espera el beneficio y donde cae cada efecto
    adverso declarado, sin co-adopcion (no hay tripulante). `effects_overview` dice cuantas lo
    declaran, cuantas no, y lo que una fuente leida diga de dos a la vez (hoy, nada); con otro
    nombre que la ficha de cada entrada, porque no tiene su forma.
    """
    body = countermeasures.overview()
    body["countermeasures"] = [
        {**item, "effects": effects.library_entry(item["id"])} for item in body["countermeasures"]
    ]
    body["effects_overview"] = effects.overview()
    return body


@countermeasures_router.get("/research")
def list_research_countermeasures() -> dict[str, Any]:
    """Las contramedidas en investigación, aparte: qué son, qué atacan y qué dice su fuente.

    Ruta propia y no un bloque de la biblioteca: lo que sale aquí no se ofrece, no se adopta ni
    se declina (sus ids no están en la biblioteca: declinar dice «desconocida», y adoptar, 409,
    porque el asesor nunca la recomendó), y su fichero no entra en la huella de reglas
    (`evidence/research_countermeasures.py`).
    """
    return research_countermeasures.overview()


def _offered_in(
    settings: SettingsDep, store: StoreDep, subject: str, countermeasure_id: str,
    reference_time: dt.datetime, nothing: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """El estado de ese instante y la recomendación de esa contramedida en él. 409 si no hay.

    Lo comparten adoptar y «no adoptar»: las dos decisiones son sobre una recomendación que
    existió en el estado que vio quien decide.
    """
    try:
        status = crew_status(
            settings, store, subject=subject, epoch=None, cumulative_dose_msv=None,
            until=reference_time,
        )
    except HTTPException as exc:
        raise HTTPException(
            status_code=409, detail=f"no hay estado en ese instante: {nothing}"
        ) from exc
    offered = next(
        (
            item for item in status["recommendations"]
            if (item.get("countermeasure") or {}).get("id") == countermeasure_id
        ),
        None,
    )
    if offered is None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"'{countermeasure_id}' no estaba recomendada en el estado de "
                f"{reference_time.isoformat()}"
            ),
        )
    return status, offered


@countermeasures_router.post("/adopt", status_code=201)
def adopt(store: StoreDep, settings: SettingsDep, payload: AdoptionIn) -> dict[str, Any]:
    """Registra que se adopta una contramedida. 409 si no estaba recomendada en ese estado.

    Adoptar algo que el sistema no recomendaba en ese instante dejaria un seguimiento sin
    motivo: la adopcion tiene que apuntar a una recomendacion que existio. El asiento lleva la
    version de las reglas vigente al firmar (`record-integrity.md` §3.26), como las otras dos
    decisiones de este fichero: la pone la ruta, no el cliente.
    """
    status, offered = _offered_in(
        settings, store, payload.subject, payload.countermeasure_id, payload.reference_time,
        "nada que adoptar",
    )
    domain = offered["domain"]
    entry = _recorded_or_422(
        lambda: store.record_followup(
            payload.subject, ADOPTED, payload.countermeasure_id, domain,
            status["domains"][domain]["level"], payload.reference_time, payload.adopted_by,
            identity_for(CONSOLE_IDENTITY), rules_version=rules_version(),
        )
    )[0]
    return {"ledger_index": entry.index}


def _console_decisions(store: StoreDep, subject: str) -> list[dict[str, Any]]:
    """Las decisiones que cuentan: las firmadas por la consola."""
    return [item for item in store.followup_decisions(subject) if _counts(item, None)]


@countermeasures_router.get("/decisions")
def read_decisions(store: StoreDep, subject: str = "crew-01") -> dict[str, Any]:
    """Lo decidido sobre las contramedidas de un tripulante, tal y como está firmado.

    `decisions` son los asientos en orden (adoptar, cerrar, no adoptar). `declined` es, por
    contramedida, el último «no» que sigue en pie, con el texto que acompaña a la recomendación.
    Descriptivo: no lo lee el análisis.
    """
    signed = sorted(_console_decisions(store, subject), key=lambda item: item["ledger_index"])
    return {
        "subject": subject,
        "decisions": [
            {key: value for key, value in item.items() if key != "signer"} for item in signed
        ],
        "declined": {
            ident: decision_note(item) for ident, item in standing_declines(signed).items()
        },
        "declined_meaning": i18n.loc(DECLINE_MEANING),
    }


@countermeasures_router.post("/decline", status_code=201)
def decline(store: StoreDep, settings: SettingsDep, payload: DeclineIn) -> dict[str, Any]:
    """Registra, firmado y con motivo, que una contramedida recomendada no se adopta.

    No cierra ni silencia ninguna alerta, no cambia ningún nivel y no retira la recomendación:
    solo deja dicho qué se decidió. 422 si la contramedida no existe o si está adoptada y con el
    seguimiento abierto (decir «no» a lo que se está siguiendo sería un registro que se
    contradice: lo coherente es cerrar ese seguimiento con su motivo). 409, como al adoptar, si
    no estaba recomendada en ese estado. Adoptar después de un «no» sigue siendo posible.
    """
    try:
        countermeasures.get(payload.countermeasure_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"contramedida desconocida: '{payload.countermeasure_id}' no está en la "
                f"biblioteca"
            ),
        ) from exc
    following = open_adoption(
        _console_decisions(store, payload.subject), payload.countermeasure_id
    )
    if following is not None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{payload.countermeasure_id}' está adoptada y con el seguimiento abierto "
                f"(asiento {following['ledger_index']}): no se registra «no adoptar» sobre algo "
                f"que se está siguiendo. El seguimiento se puede cerrar con su motivo."
            ),
        )
    status, offered = _offered_in(
        settings, store, payload.subject, payload.countermeasure_id, payload.reference_time,
        "nada sobre lo que decidir",
    )
    domain = offered["domain"]
    entry = _recorded_or_422(
        lambda: store.record_followup(
            payload.subject, DECLINED, payload.countermeasure_id, domain,
            status["domains"][domain]["level"], payload.reference_time, payload.declined_by,
            identity_for(CONSOLE_IDENTITY), reason=payload.reason,
            rules_version=rules_version(),
        )
    )[0]
    return {"ledger_index": entry.index}


def _level_at_close(
    settings: SettingsDep, store: StoreDep, subject: str, domain: str
) -> tuple[str, dt.datetime] | None:
    """El nivel de ese dominio en el estado de ahora, y el instante de ese estado.

    Es lo que el cierre deja guardado (2026-10-13) para que la respuesta previa compare con el
    dia del cierre y no con hoy. Lo calcula el MISMO analisis que sirve `/status` (`_assess`, sin
    corte: quien cierra lo hace a bordo, sobre lo que hay), y es una copia: no decide nada.
    `_assess` y no `crew_status`, porque el estado de a bordo firma instantaneas de proyeccion
    y cerrar un seguimiento no tiene por que escribir nada mas que su asiento.

    `None` si no hay estado que consultar o el dominio no esta en el: el cierre se firma igual,
    sin el nivel, y se dira de el lo mismo que de un cierre antiguo. Cerrar es una decision
    humana y no se bloquea porque falte una copia descriptiva.
    """
    try:
        assessed = _assess(settings, store, subject, None, None, None)
    except HTTPException:
        return None
    level = next(
        (risk.level for name, risk in assessed.status.domains.items() if str(name) == domain),
        None,
    )
    return (str(level), assessed.latest) if level is not None else None


@countermeasures_router.post("/close", status_code=201)
def close(store: StoreDep, settings: SettingsDep, payload: ClosureIn) -> dict[str, Any]:
    """Cierra el seguimiento de una adopcion abierta. 409 si no existe o ya esta cerrada.

    El asiento guarda ademas el nivel del dominio en el estado de este instante; lo calcula el
    backend, no lo manda el cliente (`ClosureIn` no tiene ese campo y rechaza los que sobran).
    """
    decisions = [
        item for item in store.followup_decisions(payload.subject)
        if item["signer"] == CONSOLE_IDENTITY
    ]
    adoption = next(
        (
            item for item in decisions
            if item["action"] == ADOPTED and item["ledger_index"] == payload.adoption_index
        ),
        None,
    )
    if adoption is None:
        raise HTTPException(
            status_code=409, detail=f"no hay adopción en el asiento {payload.adoption_index}"
        )
    if any(
        item["action"] == CLOSED and item["adoption_index"] == str(payload.adoption_index)
        for item in decisions
    ):
        raise HTTPException(status_code=409, detail="ese seguimiento ya está cerrado")
    at_close = _level_at_close(settings, store, payload.subject, adoption["domain"])
    entry = _recorded_or_422(
        lambda: store.record_followup(
            payload.subject, CLOSED, adoption["countermeasure_id"], adoption["domain"],
            adoption["level"], dt.datetime.fromisoformat(adoption["reference_time"]),
            payload.closed_by, identity_for(CONSOLE_IDENTITY), reason=payload.reason,
            adoption_index=payload.adoption_index,
            level_at_close=at_close[0] if at_close else None,
            closed_reference_time=at_close[1] if at_close else None,
            rules_version=rules_version(),
        )
    )[0]
    return {"ledger_index": entry.index}
