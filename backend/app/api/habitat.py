"""Rutas del habitat y de la vista de tripulacion (especificacion del equipo §3, §7, §10).

Modulo aparte por lo mismo que el dolor y las contramedidas: tiene su asiento propio en el
ledger. Lo compartido —almacen, identidades, estado de cada tripulante— se reutiliza de
`routes.py`, no se copia.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.advisor.recommendations import Advisor
from app.analysis.alert_support import ANALYSED_RULE, typed_readings
from app.analysis.baseline import BaselineEngine, Deviation
from app.analysis.context import (
    DOSE_KEY,
    RadiationRecord,
    annotate,
    coincidence,
    correlate,
)
from app.analysis.cycle_phase import LUTEAL_OFFSETS, PhaseOffset
from app.analysis.location import view as location_view
from app.analysis.risk import RiskEngine, RiskLevel, representative_deviation
from app.analysis.staleness import ExternalSource
from app.analysis.staleness import describe as describe_freshness
from app.analysis.trend import Trend, trends_by_indicator
from app.api import routes
from app.api.cycle_phase import gate as cycle_gate
from app.api.mission import crew_stays, crew_whereabouts
from app.api.routes import (
    CURRENT_WINDOW,
    SOLAR_EVENT_RELEVANCE,
    SettingsDep,
    StoreDep,
    _assess,
    _counts,
    _is_reserved_source,
    _recorded_or_422,
    _set_aside_counts,
    _unit_or_422,
    _when,
    analysed_type_words,
    identity_for,
    is_analysed_type,
    state_reference,
)
from app.api.systems import system_declarations
from app.core import i18n
from app.core.config import Settings
from app.core.storage import ObservationStore
from app.environment.donki import FRESH_FOR, SolarEvent
from app.environment.habitat import (
    DEFAULT_MODULE,
    DISPLAY_ONLY,
    DOSE_RATE_KEY,
    MODULES,
    PARAMETERS,
    Excursion,
    HabitatReading,
    cabin_readings,
    excursions,
    latest_by_parameter,
    modules_basis,
    radiation_state,
)
from app.environment.habitat import parameter as habitat_parameter
from app.evidence import light_exposure
from app.ingest.codes import DESCRIPTIVE_ONLY
from app.ingest.codes import get as indicator
from app.ingest.fhir import EvidenceContext, VitalObservation

habitat_router = APIRouter()


class HabitatReadingIn(BaseModel):
    """Una lectura de cabina de un sensor real."""

    model_config = ConfigDict(extra="forbid")

    parameter: str
    value: float
    module: str = Field(default=DEFAULT_MODULE, min_length=1, max_length=64)
    source: str = Field(default="habitat-telemetry", min_length=1, max_length=64)
    effective: dt.datetime | None = None
    evidence_context: EvidenceContext | None = None
    # La unidad UCUM en que viene `value`, si quien envia la conoce: la misma regla que el alta
    # de una lectura (`record-integrity.md` §3.14 quater), contra la unidad del parametro. Si no
    # es la suya, 422 sin asiento y sin conversion; si falta, se asume y la respuesta lo dice
    # (`unit_assumed`). No se firma: el asiento guarda la cifra en la unidad del parametro.
    unit: str | None = None

    @field_validator("source")
    @classmethod
    def _not_reserved(cls, value: str) -> str:
        if _is_reserved_source(value):
            raise ValueError(f"'{value}' es una identidad reservada del sistema")
        return value

    @field_validator("module")
    @classmethod
    def _declared_module(cls, value: str) -> str:
        # Mismo criterio que la ubicacion de un tripulante: con un nombre libre, la lectura y
        # la persona podrian estar en "el mismo sitio" escrito de dos maneras.
        if value not in MODULES:
            raise ValueError(f"módulo desconocido; uno de {tuple(MODULES)}")
        return value


@habitat_router.get("/habitat/parameters")
def habitat_parameters() -> dict[str, Any]:
    """Que se vigila en cabina, con su limite normativo y por que no es un codigo LOINC."""
    return {
        "parameters": [item.to_dict() for item in PARAMETERS.values()],
        # Lo que se muestra y no se evalua (la luz): la norma no da un limite general, y lo dice.
        "display_only": [_display_only(key) for key in DISPLAY_ONLY],
    }


# La lectura de cabina a la que se arrima lo leido sobre la luz que recibe cada persona.
LIGHT_KEY = "cabin-light"


def _display_only(key: str) -> dict[str, Any]:
    """Un parametro de solo mostrar; la luz lleva ademas lo leido sobre la exposicion personal.

    Va junto a la luz de cabina porque es donde se mira, pero es otra pregunta (la de la
    persona) y otra magnitud: no se compara con la lectura y lo dice (`evaluated` en falso).
    """
    item = DISPLAY_ONLY[key].to_dict()
    item["personal_exposure"] = light_exposure.summary() if key == LIGHT_KEY else None
    return item


@habitat_router.get("/habitat/modules")
def habitat_modules() -> dict[str, Any]:
    """La lista declarada de modulos y su base: es de diseno, no la de una nave concreta."""
    return {
        "modules": [item.to_dict() for item in MODULES.values()],
        "default": DEFAULT_MODULE,
        "basis": modules_basis(),
    }


@habitat_router.post("/habitat", status_code=201)
def record_habitat(
    store: StoreDep, settings: SettingsDep, payload: HabitatReadingIn
) -> dict[str, Any]:
    # La unidad va antes de construir la lectura, como en el alta de una observacion: una
    # unidad ajena no llega al ledger.
    try:
        declared = habitat_parameter(payload.parameter)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc.args[0])) from exc
    unit = _unit_or_422(declared, payload.unit)
    try:
        reading = HabitatReading(
            module=payload.module, parameter=payload.parameter, value=payload.value,
            effective=_when(payload.effective), source=payload.source,
            evidence_context=payload.evidence_context or settings.deployment_context,
        )
    except ValueError as exc:  # el parametro ya se resolvio arriba
        raise HTTPException(status_code=422, detail=str(exc.args[0])) from exc
    entry = _recorded_or_422(
        lambda: store.record_habitat([reading], identity_for(payload.source))
    )[0]
    return {"ledger_index": entry.index, "content_hash": entry.content_hash, **unit}


# El evento solar que da la escala aguda y la edad de la consulta a DONKI.
SolarNow = tuple[SolarEvent | None, tuple[str, float] | None]


def solar_now(settings: Settings) -> SolarNow:
    """El evento solar vigente con las mismas piezas que el estado: los eventos de
    `routes._fetch_solar_events` (leido del modulo en cada llamada, para que habitat y estado no
    puedan ver eventos distintos) y la regla de `RiskEngine.assess` —no se escribe otra aqui—.
    """
    events, age = routes._fetch_solar_events(settings)
    return RiskEngine._active_solar_event(events), age


# LO QUE EL HABITAT APARTA POR SU TIPO SE DICE, COMO YA LO DICE LA COMPARACION (§5.39.11).
#
# Desde §5.38.7 la ultima tasa de dosis de cada tripulante es la medida que lee su estado. Un
# tripulante cuya tasa de dosis solo llega inferida (modelada desde RadLab, por ejemplo)
# desaparecia de la lista sin una nota que dijera por que: la especificacion pide decir lo que
# falta o no cuenta (§2 «Uncertainty first», §10). Aqui se cuenta como lo cuenta `/crew/compare`
# (quien, cuantas lecturas y de que tipo, sobre todo el registro hasta el corte) y la frase se
# redacta aqui, no en la interfaz. Dos frases, segun el tripulante tenga ademas una lectura de
# un tipo que decide que enseñar o no tenga ninguna: la segunda es la que faltaba. `{analysed}`
# son los tipos que deciden, en palabras (`routes.analysed_type_words`), no escritos a mano.
DOSE_RATE_SET_ASIDE_SHOWN = (
    "{typed} de tasa de dosis se guardan en el registro y no entran aquí: se enseña solo la "
    "última de las {analysed}, la que lee el estado"
)
DOSE_RATE_SET_ASIDE_ONLY = (
    "{typed} de tasa de dosis se guardan en el registro y no entran aquí; sin ninguna lectura de "
    "las que deciden no hay última tasa de dosis que enseñar: el estado solo lee lecturas "
    "{analysed}"
)
# Las mismas dos frases en ingles, con los mismos huecos: `{typed}` y `{analysed}` los redacta
# quien conoce la regla, en el idioma de la peticion.
i18n.en_many({
    DOSE_RATE_SET_ASIDE_SHOWN: (
        "{typed} of dose rate are kept in the ledger and are not used here: only the latest of "
        "the {analysed} ones is shown, the one the status reads"
    ),
    DOSE_RATE_SET_ASIDE_ONLY: (
        "{typed} of dose rate are kept in the ledger and are not used here; without any reading "
        "of a type that decides there is no latest dose rate to show: the status only reads "
        "{analysed} readings"
    ),
})


def _dose_rate_set_aside(subject: str, counts: dict[str, int], shown: bool) -> dict[str, Any]:
    """Lo apartado de un tripulante, con quien, cuantas, de que tipo y la frase que lo dice."""
    template = DOSE_RATE_SET_ASIDE_SHOWN if shown else DOSE_RATE_SET_ASIDE_ONLY
    template = i18n.loc(template)
    return {
        "subject": subject,
        "counts": counts,
        # Si ademas tiene una lectura que decide en `readings`; en falso, no sale en la lista.
        "shown": shown,
        "text": template.format(typed=typed_readings(counts), analysed=analysed_type_words()),
    }


def habitat_radiation(
    store: ObservationStore,
    settings: Settings,
    until: dt.datetime | None,
    solar: SolarNow | None = None,
) -> dict[str, Any]:
    """La radiacion del estado del habitat (`environment/habitat.py`, `radiation_state`).

    La ultima tasa de dosis de cada tripulante, de lo que su estado analiza hasta `until`
    (`routes.state_reference`, sobre TODAS sus lecturas, como en su estado): la ultima es la
    misma que el estado lee. Con solo las de dosis, una lectura suelta con el reloj mal se
    tomaria por la ultima; con todas sin filtrar, una predicha fechada en el futuro movia el
    «ahora» y la ultima podia ser inferida o predicha (§5.38.7). La tasa de dosis no es la dosis
    acumulada: la excepcion de `DOSE_TYPES` (medida o inferida) es del limite de carrera, y la
    tasa la lee el estado solo medida, como cualquier otro indicador. Lo que cada tripulante
    tiene de tasa de dosis y el estado no lee por su tipo se cuenta y se dice (`set_aside`,
    §5.39.11). Y el evento solar que elige el motor de riesgo (`solar_now`), o el que ya trae
    quien llama (`/api/twins` le pasa el de su estado: una sola consulta y el mismo evento en
    toda la respuesta). El evento NO se corta en `until`: es el del reloj real, como en el
    estado. Solo lee: no firma nada.
    """
    latest: list[VitalObservation] = []
    set_aside: list[dict[str, Any]] = []
    for subject in sorted(store.subjects()):
        stored = store.query(subject, until=until)
        observations, _, _ = state_reference(stored)
        doses = [item for item in observations if item.key == DOSE_RATE_KEY]
        if doses:
            latest.append(doses[-1])
        # Con la cuenta de `/crew/compare`: lo de este indicador que no es de un tipo que decide,
        # sobre todo el registro hasta el corte (Tierra no cuenta lo que no le ha llegado).
        counts = _set_aside_counts(
            [item for item in stored if item.key == DOSE_RATE_KEY and not is_analysed_type(item)]
        )
        if counts:
            set_aside.append(_dose_rate_set_aside(subject, counts, shown=bool(doses)))
    return _radiation_with_event(
        latest, solar if solar is not None else solar_now(settings), set_aside,
        routes.latest_solar_record(settings),
    )


def solar_event_block(solar: SolarNow) -> dict[str, Any]:
    """Solo el bloque del evento solar de la radiación del hábitat, con el evento que se le pasa.

    Para quien ya trae el evento de su estado y no necesita la tasa de cada dosímetro
    (`api/crew_radiation.py`, §5.38.8): la misma frase, sin recorrer las lecturas de nadie.
    """
    block: dict[str, Any] = _radiation_with_event([], solar)["solar_event"]
    return block


def _radiation_with_event(
    latest: list[VitalObservation],
    solar: SolarNow,
    set_aside: Sequence[dict[str, Any]] = (),
    latest_recorded: SolarEvent | None = None,
) -> dict[str, Any]:
    """`radiation_state` con un evento ya elegido: una sola redacción para las dos llamadas."""
    active, age = solar
    return radiation_state(
        latest,
        active,
        # Un evento vigente es un dato conocido aunque faltara la edad de su consulta.
        solar_known=age is not None or active is not None,
        solar_age=age,
        solar_freshness=describe_freshness(
            ExternalSource.SPACE_WEATHER, age[1] if age else None
        ),
        relevance=routes.SOLAR_EVENT_RELEVANCE,
        set_aside=set_aside,
        # La misma regla, con las mismas palabras, que el estado da en `provenance.rule`.
        set_aside_rule=ANALYSED_RULE,
        latest_recorded=latest_recorded,
    )


@habitat_router.get("/habitat")
def habitat_state(
    store: StoreDep,
    settings: SettingsDep,
    until: dt.datetime | None = None,
    hours: Annotated[int, Query(ge=1, le=24 * 400)] = 72,
) -> dict[str, Any]:
    """Serie reciente, ultima lectura y excursiones de cada parametro de cabina, y la radiacion.

    `until` da el habitat que Tierra puede conocer, como `/status`. `radiation` (2026-10-26) se
    muestra y no se evalua: no entra en `excursions` ni en `active`.
    """
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    readings = store.habitat_readings(until=until)
    radiation = habitat_radiation(store, settings, until)
    if not readings:
        return {
            "readings": [], "latest": [], "excursions": [], "active": [], "reference_time": None,
            "radiation": radiation,
        }
    # El "ahora" es el de la cabina (`cabin_readings`): una muestra de agua o un recuento
    # microbiano declarados despues de su ultima lectura no pueden dar por cerrada una excursion
    # vigente (`active`) ni mover la ventana. Por eso `readings` y `latest` pueden traer una
    # muestra posterior a `reference_time`: es el ahora de la cabina, no el de cada muestra, que
    # lleva su propio `effective`. Solo sin ninguna lectura de cabina cuenta lo demas.
    judged = cabin_readings(readings) or readings
    reference = max(item.effective for item in judged)
    since = reference - dt.timedelta(hours=hours)
    recent = [item for item in readings if item.effective >= since]
    found = excursions(readings)
    return {
        "reference_time": reference.isoformat(),
        "readings": [item.to_payload() for item in recent],
        "latest": [item.to_payload() for item in latest_by_parameter(readings).values()],
        "excursions": [item.to_dict() for item in found if item.end >= since],
        # Fuera de limite AHORA: la ultima excursion de salud sigue abierta en la ultima lectura.
        "active": [
            item.to_dict() for item in found
            if item.kind == "health" and item.end >= reference - dt.timedelta(hours=1)
        ],
        "radiation": radiation,
    }


@habitat_router.get("/crew")
def crew_overview(
    store: StoreDep, settings: SettingsDep, until: dt.datetime | None = None
) -> dict[str, Any]:
    """Estado resumido de cada tripulante y la correlacion con el habitat compartido.

    Es la vista tripulacion frente a habitat (especificacion §10): para ver si un cambio es
    de una persona o de todos.
    """
    # Antes de evaluar a nadie: el 422 de `_assess` para un `until` sin zona se tragaba
    # tripulante a tripulante y la ruta acababa en «no hay tripulantes con datos» (§5.37.11).
    _aware(until)
    crew: list[dict[str, Any]] = []
    # La dosimetria de cada tripulante, de las lecturas que ya leyo su estado (con el corte de
    # Tierra), y lo que el estado tiene de NASA DONKI: la radiacion que `correlate` compara con la
    # ventana (base de conocimiento §6 y §2.1).
    doses: dict[str, list[VitalObservation]] = {}
    # Los SEP de DONKI y la edad en segundos de esos datos (None: no hubo dato).
    solar: tuple[Sequence[SolarEvent], int | None] | None = None
    for subject in sorted(store.subjects()):
        try:
            assessed = _assess(settings, store, subject, None, None, until)
        except HTTPException:
            continue
        doses[subject] = [obs for obs in assessed.observations if obs.key == DOSE_KEY]
        if solar is None:
            # DONKI es el mismo para toda la tripulacion: basta lo que trajo el primer estado.
            age = assessed.solar_age
            solar = (assessed.solar_events, None if age is None else age[1])
        status = assessed.status
        crew.append({
            "subject": subject,
            "overall_level": str(status.overall_level),
            "summary": Advisor().summarize(status),
            "reference_time": assessed.latest.isoformat(),
            "domains": {
                str(domain): {"level": str(risk.level), "drivers": list(risk.drivers)}
                for domain, risk in status.domains.items()
                if risk.level is not RiskLevel.NOMINAL
            },
            "indicators": _finding_keys(assessed.deviations, assessed.trends, assessed.latest),
        })
    if not crew:
        raise HTTPException(status_code=404, detail="no hay tripulantes con datos")
    reference = max(dt.datetime.fromisoformat(item["reference_time"]) for item in crew)
    found = excursions(store.habitat_readings(until=until))
    # Ubicacion (especificacion §3): la declarada por la consola y la estimada por las anclas de
    # modulo, del ledger; las lecturas, solo las de la ventana de la correlacion. Solo ordena
    # hipotesis; los niveles de `crew` ya estan calculados y no se tocan.
    since = reference - CURRENT_WINDOW
    where = {
        item["subject"]: crew_whereabouts(store, item["subject"], until, since) for item in crew
    }
    stays = {subject: found.stays for subject, found in where.items()}
    for item in crew:
        shown = location_view(where[item["subject"]], reference)
        item["location"] = shown["location"]
        item["location_state"] = shown["location_state"]
        item["location_missing_text"] = shown["location_missing_text"]
    correlation = correlate(
        {item["subject"]: item["overall_level"] for item in crew},
        found,
        reference,
        CURRENT_WINDOW,
        stays,
        # Lo declarado del estado de los sistemas (base de conocimiento §6): un sistema de
        # soporte vital fuera de lo nominal entra como coincidencia en el tiempo. Tampoco
        # toca los niveles de `crew`; para Tierra, solo lo que existia en su corte.
        system_declarations(store, until),
        _radiation(doses, solar),
    )
    reviews = [item for item in store.hypothesis_reviews() if _counts(item, until)]
    affected_now = set(correlation["affected"])
    for hypothesis in correlation["hypotheses"]:
        hypothesis["review"] = _review_of(hypothesis, reviews, found, reference, affected_now)
        annotate(hypothesis)
    return {"crew": crew, "reference_time": reference.isoformat(), "correlation": correlation}


def _radiation(
    doses: Mapping[str, Sequence[VitalObservation]],
    solar: tuple[Sequence[SolarEvent], int | None] | None,
) -> RadiationRecord:
    """La dosimetria de la tripulacion y los eventos solares de DONKI, con lo que cubren.

    De DONKI el estado guarda solo los SEP de `SOLAR_EVENT_RELEVANCE`, pedidos cuando dice su
    edad (`routes._fetch_solar_events`): el mismo intervalo conocido que el contexto de una
    alerta (`routes._alert_context_builder` y `alert_context._solar`, que suma alli `FRESH_FOR`;
    aqui se suma al construirlo). Sin edad no hubo dato, y no se dice «ningun evento».
    """
    events, age_seconds = solar or ((), None)
    if age_seconds is None:
        return RadiationRecord(doses)
    now = routes._now()
    return RadiationRecord(
        doses,
        events,
        (
            now - SOLAR_EVENT_RELEVANCE,
            now - dt.timedelta(seconds=age_seconds) + FRESH_FOR,
        ),
    )


def _finding_keys(
    deviations: Sequence[Deviation], trends: Mapping[str, Trend], latest: dt.datetime
) -> list[str]:
    """Indicadores que dan un hallazgo en el estado de un tripulante.

    Los mismos dos caminos que `RiskEngine.assess`: lecturas persistentes fuera de lo esperado
    en la ventana actual, o una deriva que preocupa. Sirve para proponer QUE comparar: sin
    ello, la vista de comparacion abria en un indicador cualquiera y habia que buscar a mano,
    entre todo el catalogo, el que se mueve.
    """
    cutoff = latest - CURRENT_WINDOW
    current: dict[str, list[Deviation]] = {}
    for item in deviations:
        if item.effective >= cutoff:
            current.setdefault(item.key, []).append(item)
    keys = {
        key for key, series in current.items() if representative_deviation(series) is not None
    }
    keys.update(key for key, trend in trends.items() if trend.is_concerning)
    return sorted(keys)


def _review_of(
    hypothesis: dict[str, Any],
    reviews: list[dict[str, Any]],
    found: list[Excursion],
    reference: dt.datetime,
    affected_now: set[str],
) -> dict[str, Any] | None:
    """La ultima revision humana de esta hipotesis y, si se confirmo, como va la recuperacion.

    Recuperacion descriptiva (especificacion §7, "monitorizacion de la recuperacion"): si el
    parametro ha vuelto a su limite y quien sigue fuera de nominal de los afectados.
    """
    excursion = hypothesis.get("excursion")
    if excursion is None:
        return None
    start = dt.datetime.fromisoformat(excursion["start"])
    matching = [
        item for item in reviews
        if item["parameter"] == excursion["parameter"]
        and dt.datetime.fromisoformat(item["excursion_start"]) == start
    ]
    if not matching:
        return None
    last = max(matching, key=lambda item: item["ledger_index"])
    review: dict[str, Any] = {
        "decision": last["decision"],
        "reason": last["reason"],
        "decided_by": last["decided_by"],
        "ledger_index": last["ledger_index"],
    }
    if last["decision"] == "confirmed":
        still_out = any(
            item.parameter == excursion["parameter"] and item.kind == "health"
            and item.end >= reference - dt.timedelta(hours=1)
            for item in found
        )
        review["recovery"] = {
            "habitat_within_limit": not still_out,
            "still_affected": sorted(affected_now & set(hypothesis["affected"])),
        }
    return review


# --------------------------------------------------------------------------- #
# Comparacion entre tripulantes (especificacion §10)
# --------------------------------------------------------------------------- #
#
# POR QUE EXISTE. `/crew` dice el nivel de cada tripulante y propone hipotesis, pero no deja
# VER la misma variable en todos a la vez, que es lo que la especificacion pide "para detectar
# posibles causas ambientales compartidas". Y compararla en valores absolutos engaña: 70 lpm es
# mucho para quien tiene su base en 55 y nada para quien la tiene en 68. Aqui cada serie va
# contra SU PROPIA linea base —la misma ventana movil que usa `/status`, sin otro umbral— y
# todas sobre el mismo eje temporal, con el parametro de cabina al lado si se pide.
#
# QUIEN "SE DESVIA" LO DECIDEN LAS REGLAS DEL ESTADO, NO OTRAS. Un tripulante cuenta si el
# indicador le daria un hallazgo en `/status`: lecturas persistentes fuera de lo esperado
# (`representative_deviation`) o una deriva que preocupa (`Trend.is_concerning`). La primera
# version solo miraba las lecturas, y en el escenario de CO2 —donde lo que mueve a los cuatro
# es una deriva de la carga de sintomas— respondia "nadie se aparta" mientras `/crew` decia
# que estaban los cuatro afectados. Dos respuestas distintas a la misma pregunta.
#
# Solo lee: no firma nada y no mueve niveles ni alertas (invariante 5).

# Tramo de serie que se entrega por defecto: la ventana de la linea base movil.
COMPARE_HOURS = 24 * 14

NO_DATA = "sin dato"
NO_RECENT = "sin lecturas en la ventana comparada"
WITHIN = "dentro de lo esperado"
OUT_OF_EXPECTED = "lecturas fuera de lo esperado"
DRIFTING = "deriva sostenida"
NO_BASELINE = "sin línea base personal establecida en este tramo"
BASELINE_BASIS = (
    "cada lectura menos la mediana de la línea base personal móvil de ese tripulante en el "
    "mismo estado (reposo, sueño…)"
)
# El "ahora" de la comparacion es el del indicador, no el del tripulante: un analisis semanal
# se compara en su ultima toma aunque el pulso tenga lecturas mas recientes. Se declara.
WINDOW_BASIS = (
    f"las {CURRENT_WINDOW.total_seconds() / 3600:.0f} h anteriores a la última lectura de este "
    "indicador en la tripulación"
)
i18n.en_many({
    NO_DATA: "no data",
    NO_RECENT: "no readings in the compared window",
    WITHIN: "within the expected range",
    OUT_OF_EXPECTED: "readings outside the expected range",
    DRIFTING: "sustained drift",
    NO_BASELINE: "no personal baseline established in this span",
    BASELINE_BASIS: (
        "each reading minus the median of that crew member's rolling personal baseline in the "
        "same state (rest, sleep…)"
    ),
    WINDOW_BASIS: (
        f"the {CURRENT_WINDOW.total_seconds() / 3600:.0f} h before the latest reading of this "
        "indicator in the crew"
    ),
})


def _aware(until: dt.datetime | None) -> None:
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")


@habitat_router.get("/crew/members")
def crew_members(store: StoreDep, until: dt.datetime | None = None) -> dict[str, Any]:
    """Quienes forman la tripulacion conocida, para elegir a quien se mira.

    Sin analisis: `/crew` evalua a cada uno y tarda; un selector solo necesita los nombres.
    Con `until`, solo quien ya tiene alguna lectura llegada a Tierra.
    """
    _aware(until)
    subjects = sorted(store.subjects())
    if until is not None:
        subjects = [item for item in subjects if store.query(item, until=until, limit=1)]
    return {"crew": [{"subject": item} for item in subjects]}


@dataclass(frozen=True, slots=True)
class _Compared:
    """La serie de un tripulante y lo que el resumen necesita de ella."""

    payload: dict[str, Any]
    # Tiene lecturas en la ventana comparada: solo entonces cuenta, se desvie o no.
    counted: bool
    onset: dt.datetime | None
    drifting: bool


def _no_data(subject: str) -> _Compared:
    """Se dice que falta: un tripulante sin lecturas no es un tripulante "normal"."""
    payload: dict[str, Any] = {
        "subject": subject, "state": "no_data", "state_text": i18n.loc(NO_DATA),
        "baseline_text": None,
        "deviating": False, "onset": None, "drivers": [], "latest": None, "origins": [],
        "points": [],
    }
    return _Compared(payload, counted=False, onset=None, drifting=False)


def _origins(observations: Iterable[VitalObservation]) -> list[dict[str, str | None]]:
    """Tipo (medido, inferido, predicho) y entorno de las lecturas de una serie, sin repetir.

    Comparar a dos personas es poner sus datos en la misma vista: si una serie es simulada y
    la otra sale de un sensor real, tiene que verse (especificacion §2, "no mezclar contextos
    sin `evidence_context`"; §10, rotular siempre el tipo de dato).
    """
    seen = {
        (
            str(item.observation_type),
            item.evidence_context.value if item.evidence_context is not None else None,
        )
        for item in observations
    }
    return [
        {"type": kind, "context": context}
        for kind, context in sorted(seen, key=lambda pair: (pair[0], pair[1] or ""))
    ]


def _compared(
    subject: str,
    key: str,
    observations: list[VitalObservation],
    reference: dt.datetime,
    since: dt.datetime,
    phase_offset: PhaseOffset | None = None,
) -> _Compared:
    """Un tripulante contra su propia base, con las mismas reglas que deciden su estado.

    Tambien el ajuste por fase del ciclo (`api/cycle_phase.py`, lote «ciclo»): si su puerta esta
    abierta, la base y la tendencia se juzgan con el, como en `/api/status`.
    """
    deviations = sorted(
        BaselineEngine().evaluate_rolling(observations, phase_offset=phase_offset),
        key=lambda item: item.effective,
    )
    current = [item for item in deviations if item.effective >= reference - CURRENT_WINDOW]
    # La regla de persistencia del estado: una lectura suelta fuera de lo esperado es ruido.
    finding = representative_deviation(current)
    trend = trends_by_indicator(
        observations, now=reference, phase_offset=phase_offset
    ).get(key)
    onset = (
        min(item.effective for item in current if item.is_concerning)
        if finding is not None else None
    )

    points: list[dict[str, Any]] = []
    for item in deviations:
        if item.effective < since:
            continue
        # Sin base personal la lectura se juzgo contra el rango poblacional: no hay "su base"
        # que restar, y no se inventa una.
        own = None if item.used_population_range or item.baseline is None else item.baseline
        points.append({
            "effective": item.effective.isoformat(),
            "value": item.value,
            "baseline": round(own.center, 4) if own is not None else None,
            "delta": round(item.value - own.center, 4) if own is not None else None,
            "concerning": item.is_concerning,
        })

    # Las mismas frases que el estado de ese tripulante da como motivo, y por las mismas vias.
    labels: list[str] = []
    drivers: list[str] = []
    drifting = False
    if not current:
        # Tiene lecturas, pero no en la ventana: ni se desvia ni esta "dentro de lo esperado".
        state, text = (
            ("no_recent", i18n.loc(NO_RECENT)) if points else ("no_data", i18n.loc(NO_DATA))
        )
    else:
        if finding is not None:
            labels.append(i18n.loc(OUT_OF_EXPECTED))
            drivers.append(finding.describe())
        if trend is not None and trend.is_concerning:
            drifting = True
            labels.append(i18n.loc(DRIFTING))
            drivers.append(trend.describe())
        state, text = (
            ("deviating", i18n.tr(" y ", " and ").join(labels)) if labels
            else ("within", i18n.loc(WITHIN))
        )
    has_baseline = any(point["delta"] is not None for point in points)
    payload: dict[str, Any] = {
        "subject": subject,
        "state": state,
        "state_text": text,
        "baseline_text": None if has_baseline or not points else i18n.loc(NO_BASELINE),
        "deviating": state == "deviating",
        "onset": onset.isoformat() if onset is not None else None,
        "drivers": drivers,
        "latest": deviations[-1].effective.isoformat(),
        "origins": _origins(item for item in observations if item.effective >= since),
        "points": points,
    }
    return _Compared(payload, counted=bool(current), onset=onset, drifting=drifting)


@habitat_router.get("/crew/compare")
def crew_compare(
    store: StoreDep,
    key: str,
    parameter: str | None = None,
    until: dt.datetime | None = None,
    hours: Annotated[int, Query(ge=1, le=24 * 400)] = COMPARE_HOURS,
) -> dict[str, Any]:
    """El mismo indicador en cada tripulante, cada uno contra su propia linea base.

    `parameter` añade un parametro de cabina sobre el mismo eje. `until` da lo que Tierra puede
    conocer, como `/status`. El resumen cuenta quien se desvia a la vez y desde cuando, y lo
    rotula "coincidencia temporal, no causa". Cada serie declara tipo y entorno de sus lecturas.
    """
    try:
        code = indicator(key)
        cabin = habitat_parameter(parameter) if parameter is not None else None
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    _aware(until)
    if code.key in DESCRIPTIVE_ONLY:
        # El estado no lee los descriptivos (`codes.DESCRIPTIVE_ONLY`): no tienen linea base con
        # la que juzgarlos, y compararlos aqui seria juzgarlos con una que el estado no usa.
        raise HTTPException(
            status_code=422,
            detail=(
                f"{code.display_es} es un indicador descriptivo: el estado no lo juzga contra una "
                f"línea base personal y no se compara entre tripulantes (se enseña en "
                f"GET /api/indicators/descriptive)"
            ),
        )

    subjects = sorted(store.subjects())
    readings_of: dict[str, list[VitalObservation]] = {}
    set_aside_of: dict[str, dict[str, int]] = {}
    latest: list[dt.datetime] = []
    for subject in subjects:
        # Con la regla del estado (`routes.state_reference`): una lectura inferida o predicha no
        # entra en la base propia ni mueve el «ahora». Y se cuenta, como la cuenta el estado.
        readings = store.query(subject, key=key, until=until)
        observations, last, _ = state_reference(readings)
        set_aside_of[subject] = _set_aside_counts(
            [item for item in readings if not is_analysed_type(item)]
        )
        if observations:
            readings_of[subject] = observations
            latest.append(last)
    if until is not None:
        # Tierra no conoce todavia a quien no le ha llegado ninguna lectura, de nada.
        subjects = [
            item for item in subjects
            if item in readings_of or store.query(item, until=until, limit=1)
        ]
    if not subjects:
        raise HTTPException(status_code=404, detail="no hay tripulantes con datos")

    stored = store.habitat_readings(until=until)
    found = excursions(stored)
    # Un solo "ahora" para todos: sin el, "a la vez" compararia ventanas distintas.
    reference = max(latest) if latest else None
    since = reference - dt.timedelta(hours=hours) if reference is not None else None

    def phase_of(subject: str, now: dt.datetime) -> PhaseOffset | None:
        """La puerta del ajuste por fase del tripulante, con lo que hay hasta el corte."""
        if code.key not in LUTEAL_OFFSETS:
            return None  # el ajuste no toca este indicador: no hace falta leer nada más
        everything = store.query(subject, until=until)
        return cycle_gate(
            store, subject, until, everything, readings_of[subject], now, is_analysed_type
        ).offset

    compared = [
        _compared(
            subject, code.key, readings_of[subject], reference, since,
            phase_of(subject, reference),
        )
        if subject in readings_of and reference is not None and since is not None
        else _no_data(subject)
        for subject in subjects
    ]
    # Lo que no decidio por su tipo, contado en cada serie como lo cuenta el estado
    # (`provenance.set_aside`), con la frase dicha aqui y no en la interfaz.
    for item in compared:
        counts = set_aside_of.get(item.payload["subject"], {})
        item.payload["set_aside"] = counts
        item.payload["set_aside_text"] = (
            i18n.tr(
                f"{typed_readings(counts)} de este indicador se guardan en el registro y no "
                f"entran en la comparación: solo deciden las medidas",
                f"{typed_readings(counts)} of this indicator are kept in the ledger and are not "
                f"used in the comparison: only measured readings decide",
            )
            if counts else None
        )

    # El eje lo fija el indicador. Si nadie tiene lecturas de el no hay eje, y la serie de
    # cabina sola —que ya da `/habitat`— no se entrega.
    habitat: dict[str, Any] | None = None
    if cabin is not None and since is not None:
        shown = [
            item for item in stored
            if item.parameter == cabin.key and item.effective >= since
        ]
        habitat = {
            "parameter": cabin.to_dict(),
            "state": "ok" if shown else "no_data",
            "state_text": None if shown else i18n.loc(NO_DATA),
            "evidence_contexts": sorted({item.evidence.value for item in shown}),
            "points": [
                {"effective": item.effective.isoformat(), "value": item.value,
                 "module": item.module}
                for item in shown
            ],
            "excursions": [
                item.to_dict() for item in found
                if item.parameter == cabin.key and item.end >= since
            ],
        }

    # Si alguno de los comparados ha declarado donde estaba dentro de lo que se mira, el
    # resumen no puede seguir diciendo que EMMA no registra la ubicacion: dice que esta
    # comparacion no la usa. Solo cambia esa frase.
    located = False
    if reference is not None and since is not None:
        earliest = min(since, reference - CURRENT_WINDOW)
        located = any(
            stay.end >= earliest and stay.start <= reference
            for item in compared
            for stay in crew_stays(store, item.payload["subject"], until, earliest)
        )

    return {
        "key": code.key,
        "display": code.display,
        "display_es": code.display_es,
        "unit": code.unit,
        "reference_time": reference.isoformat() if reference is not None else None,
        "since": since.isoformat() if since is not None else None,
        "baseline_basis": i18n.loc(BASELINE_BASIS),
        "series": [item.payload for item in compared],
        "habitat": habitat,
        "summary": {
            **coincidence(
                code.display_es,
                {item.payload["subject"]: item.onset for item in compared if item.counted},
                {item.payload["subject"] for item in compared if item.drifting},
                # Sin lecturas de nadie no hay ventana que mirar: tampoco excursiones.
                found if reference is not None else [],
                reference or dt.datetime.now(dt.UTC),
                CURRENT_WINDOW,
                located,
            ),
            "window_basis": i18n.loc(WINDOW_BASIS),
        },
    }
