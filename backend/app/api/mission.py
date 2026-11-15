"""Perfil del tripulante, eventos del plan de mision y revision humana de hipotesis.

Tres decisiones humanas que la especificacion del equipo pide registrar (§3 Astronaut y
MissionContext, §7 confirmacion humana). Van por el ledger, firmadas por la consola, con el
patron de las demas acciones del operador (`routes.py`, `countermeasures.py`).

Desde la decimoquinta ronda (D19), tambien el historial mision a mision (§3 Astronaut
`mission_history`), al lado del perfil y sin sustituir su dosis previa (`core/mission_history.py`).

Desde el lote «ciclo» (2026-11-14, decisión del usuario que revierte la §5.36.19), también el sexo
declarado (`crew-sex`): un asiento propio, que se borra solo con la redacción y que Tierra lee con
su corte. Es el único sitio que lo lee; ninguna regla del análisis lo recibe.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.analysis.context import CONSOLE_LOCATION, Stay
from app.analysis.location import Anchor, Sighting, Whereabouts, estimate
from app.api.routes import (
    CONSOLE_IDENTITY,
    SettingsDep,
    StoreDep,
    _counts,
    _recorded_or_422,
    identity_for,
)
from app.core import mission_history
from app.core import shift as shift_event
from app.core.identities import ANCHOR_IDENTITY
from app.core.storage import (
    CREW_SEX_VALUES,
    HYPOTHESIS_DECISIONS,
    LOCATION_EVENT_KIND,
    MISSION_EVENT_KINDS,
    TamperedRecordError,
)
from app.environment.habitat import MODULES
from app.reports.identity import Declared

mission_router = APIRouter()

Operator = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


def _aware(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        raise ValueError("el instante debe llevar zona horaria")
    return value


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(default="crew-01", min_length=1)
    prior_missions: int = Field(ge=0, le=20)
    # None: no se conoce. No es cero (ver `analysis/radiation.py`).
    prior_career_dose_msv: float | None = Field(default=None, ge=0, le=2000)
    declared_by: Operator


class PriorMissionIn(BaseModel):
    """Una mision previa: nombre, fechas y, si se conoce, su dosis. Los dias los calcula EMMA."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=mission_history.MAX_NAME_LENGTH)
    start: dt.date
    end: dt.date
    # None: no se conoce. No es cero, como la dosis previa del perfil.
    dose_msv: float | None = Field(default=None, ge=0, le=2000)


class MissionHistoryIn(BaseModel):
    """El historial entero: se declara la lista completa y vale la ultima declarada."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(default="crew-01", min_length=1)
    missions: list[PriorMissionIn] = Field(max_length=mission_history.MAX_PRIOR_MISSIONS)
    declared_by: Operator


class IdentityIn(BaseModel):
    """Nombre y fecha de nacimiento del tripulante, para cotejar que un informe es suyo."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(default="crew-01", min_length=1)
    given_name: str = Field(min_length=1, max_length=80)
    surnames: str = Field(default="", max_length=120)
    birth_date: dt.date
    declared_by: Operator


class CrewSexIn(BaseModel):
    """El sexo que declara el tripulante: uno de `CREW_SEX_VALUES`, y quién lo declara."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(default="crew-01", min_length=1)
    sex: str
    declared_by: Operator

    @field_validator("sex")
    @classmethod
    def _known(cls, value: str) -> str:
        if value not in CREW_SEX_VALUES:
            raise ValueError(f"sexo desconocido; uno de {CREW_SEX_VALUES}")
        return value


class MissionEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(default="crew-01", min_length=1)
    kind: str
    start: dt.datetime
    end: dt.datetime
    # En una ubicacion la descripcion es opcional: sin ella, el asiento lleva el nombre del
    # modulo. En una EVA, un bloque de trabajo o un cambio de turno sigue siendo obligatoria.
    label: Text | None = None
    # Solo en `location`: un modulo de la lista declarada (`/habitat/modules`).
    module: str | None = None
    declared_by: Operator

    _tz = field_validator("start", "end")(_aware)

    @field_validator("kind")
    @classmethod
    def _known(cls, value: str) -> str:
        if value not in MISSION_EVENT_KINDS:
            raise ValueError(f"tipo desconocido; uno de {MISSION_EVENT_KINDS}")
        return value

    @model_validator(mode="after")
    def _module_only_for_a_location(self) -> MissionEventIn:
        if self.kind == LOCATION_EVENT_KIND:
            if self.module not in MODULES:
                raise ValueError(f"módulo desconocido; uno de {tuple(MODULES)}")
            if self.label is None:
                self.label = MODULES[self.module].display
        elif self.module is not None:
            raise ValueError("solo una declaración de ubicación lleva módulo")
        elif self.label is None:
            raise ValueError("un evento de misión necesita una descripción")
        return self


class HypothesisReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str
    parameter: str = Field(min_length=1)
    excursion_start: dt.datetime
    reason: Text
    decided_by: Operator

    _tz = field_validator("excursion_start")(_aware)

    @field_validator("decision")
    @classmethod
    def _known(cls, value: str) -> str:
        if value not in HYPOTHESIS_DECISIONS:
            raise ValueError(f"decisión desconocida; una de {HYPOTHESIS_DECISIONS}")
        return value


def latest_profile(store: Any, subject: str, until: dt.datetime | None = None) -> dict[str, Any]:
    """El ultimo perfil declarado por la consola, o uno vacio."""
    declared = [item for item in store.profiles(subject) if _counts(item, until)]
    if not declared:
        return {"prior_missions": None, "prior_career_dose_msv": None, "declared_by": None}
    last = max(declared, key=lambda item: item["ledger_index"])
    dose = last["prior_career_dose_msv"]
    return {
        "prior_missions": int(last["prior_missions"]),
        "prior_career_dose_msv": float(dose) if dose else None,
        "declared_by": last["declared_by"],
    }


@mission_router.post("/crew/profile", status_code=201)
def declare_profile(store: StoreDep, payload: ProfileIn) -> dict[str, Any]:
    entry = _recorded_or_422(
        lambda: store.record_profile(
            payload.subject, payload.prior_missions, payload.prior_career_dose_msv,
            payload.declared_by, identity_for(CONSOLE_IDENTITY),
        )
    )[0]
    return {"ledger_index": entry.index}


@mission_router.get("/crew/profile")
def read_profile(store: StoreDep, subject: str = "crew-01") -> dict[str, Any]:
    return {"subject": subject, **latest_profile(store, subject)}


def latest_mission_history(
    store: Any, subject: str, until: dt.datetime | None = None
) -> dict[str, Any] | None:
    """El ultimo historial declarado por la consola (para Tierra, el de su corte), o None.

    Solo se lee la lista del vigente: los anteriores no se usan. Una lista firmada que no tiene
    la forma de `encode` es un asiento mal formado, un 409 como cualquier otro (`_actions`).
    """
    declared = [item for item in store.mission_histories(subject) if _counts(item, until)]
    if not declared:
        return None
    last = max(declared, key=lambda item: item["ledger_index"])
    try:
        missions = mission_history.decode(last["missions"])
    except ValueError as exc:
        raise TamperedRecordError(
            f"asiento {last['ledger_index']}: historial de misiones mal formado"
        ) from exc
    return {**last, "missions": missions}


@mission_router.post("/crew/mission-history", status_code=201)
def declare_mission_history(
    store: StoreDep, settings: SettingsDep, payload: MissionHistoryIn
) -> dict[str, Any]:
    """Firma el historial entero. 422 si alguna misión no puede ser previa a la actual."""
    missions = [
        mission_history.PriorMission(item.name, item.start, item.end, item.dose_msv)
        for item in payload.missions
    ]
    entry = _recorded_or_422(
        lambda: store.record_mission_history(
            payload.subject, missions, payload.declared_by, identity_for(CONSOLE_IDENTITY),
            current_start=settings.mission_start,
        )
    )[0]
    return {"ledger_index": entry.index}


@mission_router.get("/crew/mission-history")
def read_mission_history(
    store: StoreDep, settings: SettingsDep, subject: str = "crew-01",
    until: dt.datetime | None = None,
) -> dict[str, Any]:
    """Lo declarado y su cotejo con el perfil. Solo se lee: la carrera no pasa por aqui.

    Con el inicio de misión de la configuración, como al firmar: una previa que se solape con la
    actual se avisa (`describe`), sin rechazar nada al leer."""
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    return {
        "subject": subject,
        **mission_history.describe(
            latest_mission_history(store, subject, until), latest_profile(store, subject, until),
            current_start=settings.mission_start,
        ),
    }


def latest_identity(store: Any, subject: str) -> Declared | None:
    """La última identidad declarada, o None."""
    declared = store.crew_identities(subject)
    if not declared:
        return None
    last = max(declared, key=lambda item: item["ledger_index"])
    return Declared(
        last["given_name"], last["surnames"], dt.date.fromisoformat(last["birth_date"])
    )


@mission_router.post("/crew/identity", status_code=201)
def declare_identity(store: StoreDep, payload: IdentityIn) -> dict[str, Any]:
    entry = _recorded_or_422(
        lambda: store.record_crew_identity(
            payload.subject, payload.given_name, payload.surnames, payload.birth_date,
            payload.declared_by, identity_for(CONSOLE_IDENTITY),
        )
    )[0]
    return {"ledger_index": entry.index}


@mission_router.get("/crew/identity")
def read_identity(store: StoreDep, subject: str = "crew-01") -> dict[str, Any]:
    declared = latest_identity(store, subject)
    if declared is None:
        return {"subject": subject, "declared": False}
    return {
        "subject": subject,
        "declared": True,
        "given_name": declared.given_name,
        "surnames": declared.surnames,
        "birth_date": declared.birth_date.isoformat(),
    }


# Lo que dice la respuesta cuando no hay declaración vigente: nunca un valor por omisión.
CREW_SEX_UNDECLARED = "no declarado"


def latest_crew_sex(
    store: Any, subject: str, until: dt.datetime | None = None
) -> dict[str, Any] | None:
    """La última declaración de sexo firmada por la consola (para Tierra, la de su corte), o None.

    Una redactada no está (`_actions` solo entrega contenido presente): si se redacta la vigente,
    vale la anterior que quede, y sin ninguna, no hay declaración. Un valor firmado fuera de
    `CREW_SEX_VALUES` es un asiento mal formado, un 409 como cualquier otro.
    """
    declared = [item for item in store.crew_sexes(subject) if _counts(item, until)]
    if not declared:
        return None
    last = max(declared, key=lambda item: item["ledger_index"])
    if last["sex"] not in CREW_SEX_VALUES:
        raise TamperedRecordError(f"asiento {last['ledger_index']}: sexo declarado mal formado")
    return dict(last)


@mission_router.post("/crew/sex", status_code=201)
def declare_crew_sex(store: StoreDep, payload: CrewSexIn) -> dict[str, Any]:
    entry = _recorded_or_422(
        lambda: store.record_crew_sex(
            payload.subject, payload.sex, payload.declared_by, identity_for(CONSOLE_IDENTITY)
        )
    )[0]
    return {"ledger_index": entry.index}


@mission_router.get("/crew/sex")
def read_crew_sex(
    store: StoreDep, subject: str = "crew-01", until: dt.datetime | None = None
) -> dict[str, Any]:
    """Lo declarado vigente, o «no declarado». Con `until`, lo que Tierra ya tiene en su corte."""
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    last = latest_crew_sex(store, subject, until)
    if last is None:
        return {
            "subject": subject, "declared": False, "sex": None,
            "status": CREW_SEX_UNDECLARED, "values": list(CREW_SEX_VALUES),
        }
    return {
        "subject": subject,
        "declared": True,
        "sex": last["sex"],
        "declared_by": last["declared_by"],
        "recorded": last["recorded"],
        # Para borrarla: `POST /api/audit/redact/{ledger_index}`.
        "ledger_index": last["ledger_index"],
        "values": list(CREW_SEX_VALUES),
    }


@mission_router.post("/mission/events", status_code=201)
def declare_mission_event(store: StoreDep, payload: MissionEventIn) -> dict[str, Any]:
    try:
        entry = _recorded_or_422(
            lambda: store.record_mission_event(
                payload.subject, payload.kind, payload.start, payload.end,
                payload.label or "", payload.declared_by, identity_for(CONSOLE_IDENTITY),
                module=payload.module,
            )
        )[0]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ledger_index": entry.index}


@mission_router.get("/mission/shift")
def shift_basis() -> dict[str, Any]:
    """Que es un cambio de turno, en que se distingue de un bloque de trabajo y su fuente leida.

    Lo enseña el formulario al declarar uno: el texto es del backend, no de la interfaz.
    """
    return shift_event.describe()


def mission_events(
    store: Any, subject: str, until: dt.datetime | None = None
) -> list[dict[str, Any]]:
    return [
        {key: item[key] for key in ("kind", "start", "end", "label", "declared_by")}
        | ({"module": item["module"]} if "module" in item else {})
        | {"ledger_index": item["ledger_index"]}
        for item in store.mission_events(subject)
        if _counts(item, until)
    ]


def crew_stays(
    store: Any, subject: str, until: dt.datetime | None = None,
    since: dt.datetime | None = None,
) -> list[Stay]:
    """Donde estaba un tripulante: lo declarado por la consola y lo estimado por las anclas.

    Lo mismo que `crew_whereabouts(...).stays`; para quien solo ordena hipotesis.
    """
    return crew_whereabouts(store, subject, until, since).stays


def anchor_declarations(store: Any, until: dt.datetime | None = None) -> list[Anchor]:
    """Las anclas de modulo que cuentan: firmadas por la consola (`_counts`) y, para Tierra, las
    que ya existian en su corte y no valen desde un instante posterior a el."""
    return [
        Anchor(
            anchor_id=item["anchor_id"], module=item["module"],
            since=dt.datetime.fromisoformat(item["since"]), order=item["ledger_index"],
        )
        for item in store.location_anchors()
        if _counts(item, until)
        and (until is None or dt.datetime.fromisoformat(item["since"]) <= until)
    ]


def crew_whereabouts(
    store: Any, subject: str, until: dt.datetime | None = None,
    since: dt.datetime | None = None,
) -> Whereabouts:
    """Todo lo que se sabe de donde estaba un tripulante, leido del ledger.

    - Lo declarado: solo los asientos de ubicacion firmados por la consola (`_counts`; para
      Tierra, los de su corte), como toda accion del operador.
    - Lo estimado por las anclas (`analysis.location.estimate`): las lecturas firmadas por
      `location-anchors` (nadie mas puede firmar un lote: `routes._is_reserved_source` y la ruta
      propia), para Tierra solo las ya firmadas en su corte, contra las anclas que cuentan. Sin
      ninguna ancla no se leen las lecturas: no hay con que estimar.

    `since` acota las lecturas que se leen (las de `at` ≥ `since`): el estado solo lee las que
    pueden decir algo de su instante (`Sensing.lookback`), no la mision entera.

    Una ubicacion en un modulo que ya no esta en la lista declarada no se usa: daria por ausente
    a alguien de un sitio que no se puede comparar. Cual manda si se solapan lo dice
    `context.prevailing`: la consola, aunque sea anterior.
    """
    stays = [
        Stay(
            module=item["module"],
            start=dt.datetime.fromisoformat(item["start"]),
            end=dt.datetime.fromisoformat(item["end"]),
            order=item["ledger_index"],
            source=CONSOLE_LOCATION,
        )
        for item in store.mission_events(subject)
        if item["kind"] == LOCATION_EVENT_KIND
        and _counts(item, until)
        and item.get("module") in MODULES
    ]
    anchors = anchor_declarations(store, until)
    if not anchors:
        return Whereabouts(stays=stays, undecided=[], anchors=False)
    sightings = [
        Sighting(
            anchor_id=item["anchor_id"], rssi_dbm=item["rssi_dbm"], at=item["at"],
            order=item["ledger_index"],
        )
        for item in store.location_sightings(subject, since)
        if item["signer"] == ANCHOR_IDENTITY
        and (until is None or dt.datetime.fromisoformat(item["recorded"]) <= until)
    ]
    estimated, undecided = estimate(sightings, anchors)
    return Whereabouts(stays=[*stays, *estimated], undecided=undecided, anchors=True)


@mission_router.post("/crew/hypotheses/review", status_code=201)
def review_hypothesis(
    store: StoreDep, settings: SettingsDep, payload: HypothesisReviewIn
) -> dict[str, Any]:
    """Confirma o descarta la hipotesis de causa compartida. 409 si no esta en el estado."""
    from app.api.habitat import crew_overview

    overview = crew_overview(store, settings, None)
    offered = [
        item for item in overview["correlation"]["hypotheses"]
        if item["excursion"] is not None
        and item["excursion"]["parameter"] == payload.parameter
        and dt.datetime.fromisoformat(item["excursion"]["start"]) == payload.excursion_start
    ]
    if not offered:
        raise HTTPException(
            status_code=409,
            detail="no hay una hipótesis con ese parámetro y esa excursión en el estado actual",
        )
    entry = _recorded_or_422(
        lambda: store.record_hypothesis_review(
            payload.decision, payload.parameter, payload.excursion_start, payload.reason,
            payload.decided_by, identity_for(CONSOLE_IDENTITY),
        )
    )[0]
    return {"ledger_index": entry.index}
