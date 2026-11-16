"""API HTTP de EMMA.

Dos principios que se ven en todas las respuestas:

  1. **Todo dato externo declara su antiguedad.** En una mision, una lectura de
     meteorologia espacial de hace seis horas y una de hace seis dias exigen
     decisiones distintas; ocultar la diferencia es peligroso.
  2. **Toda escritura queda auditada.** No hay endpoint que guarde una
     observacion sin pasar por el ledger encadenado.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
import threading
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from starlette.responses import Response as StarletteResponse

from app import anatomy, pain_on_skeleton
from app.advisor.effects import with_effects
from app.advisor.followup import followups, with_decisions
from app.advisor.prior_response import with_prior_response
from app.advisor.recommendations import Advisor, Recommendation
from app.analysis import alert_context, alert_flow, densitometry, exercise_summary
from app.analysis import location as location_rules
from app.analysis.alert_support import ANALYSED_RULE, TYPE_WORDS, typed_readings
from app.analysis.baseline import BaselineEngine, Deviation
from app.analysis.context import Stay
from app.analysis.cycle_phase import PhaseOffset, without_phase
from app.analysis.data_quality import describe as describe_quality
from app.analysis.episode import CLOSED_EPISODE_RULE, closing
from app.analysis.explain import detail as explain_detail
from app.analysis.forecast_check import HORIZON as FORECAST_HORIZON
from app.analysis.forecast_check import daily_mean, hindcast, matured
from app.analysis.forecast_check import summary as forecast_summary
from app.analysis.inferred import bone_density_band
from app.analysis.location import Whereabouts
from app.analysis.radiation import mission_dose, mission_projection
from app.analysis.radiation import scales as radiation_scales
from app.analysis.recovery_state import trajectories
from app.analysis.risk import CrewHealthStatus, RiskEngine, RiskLevel
from app.analysis.staleness import BASIS as STALENESS_BASIS
from app.analysis.staleness import ExternalSource
from app.analysis.staleness import describe as describe_freshness
from app.analysis.time_to_action import time_to_action_of
from app.analysis.trend import TREND_WINDOW, Trend, projection, trends_by_indicator
from app.analysis.wording import level_labels, with_wording
from app.api.console_header import console_post
from app.api.cycle_phase import CycleGate
from app.api.cycle_phase import gate as cycle_gate
from app.core import display, i18n, identities, mission_profile_changes
from app.core import resources as resource_rules
from app.core.cache import CachedPayload, OfflineDataUnavailable
from app.core.config import Settings, get_settings
from app.core.ledger import (
    FORMER_AUTHORITY_IDS,
    Identity,
    LedgerEntry,
    RedactionAuthority,
    UntrustedSigner,
    canonical_bytes,
)
from app.core.mission import context as mission_context
from app.core.mission import mission_day, phase_at
from app.core.storage import (
    DISMISSAL_NOTE_REQUIRED,
    DISMISSAL_REASONS,
    RULES_VERSION_FIELD,
    AmendmentMismatch,
    ObservationStore,
    dismissal_problem,
    seed_from_simulator,
)
from app.core.versioning import decided_with, rules_version
from app.environment import comms_status, conjunction, ephemeris_coverage
from app.environment import systems as habitat_systems
from app.environment.donki import DonkiClient, EventType, SnapshotPayload, SolarEvent
from app.environment.dosimetry import QualityFactorModel, effective_dose
from app.environment.ephemeris import (
    CommsWindow,
    EphemerisClient,
    PreloadInProgress,
    utc_today,
)
from app.environment.habitat import DEFAULT_MODULE as DEFAULT_HABITAT_MODULE
from app.environment.habitat import MODULES as HABITAT_MODULES
from app.environment.habitat import excursions as habitat_excursions
from app.environment.radlab import RadLabClient
from app.evidence import credibility, design_hypotheses, mission_profiles, nasa_framework
from app.evidence import registry as evidence_registry
from app.evidence.links import EIMO_DESCRIPTION, amcl_alignment, evidence_for
from app.ingest import category_fit, names_es
from app.ingest.codes import CATALOG, DESCRIPTIVE_ONLY, Domain, VitalCode, get
from app.ingest.cost import cost as measurement_cost
from app.ingest.fhir import (
    FULL_CONFIDENCE,
    CatalogUnit,
    Context,
    EvidenceContext,
    ObservationType,
    VitalObservation,
    deployed,
    from_device,
    observation,
    require_catalog_unit,
)

# Con nombre propio: `ObservationIn` tiene un campo que se llama como el módulo.
from app.ingest.food_item import FIELD_MAX_LENGTH as FOOD_ITEM_FIELD_MAX_LENGTH
from app.ingest.food_item import accept as accept_food_item
from app.ingest.habitat_simulator import HabitatSimulator
from app.ingest.pvt import InsufficientTrials, score, to_observations
from app.ingest.simulator import (
    ENVIRONMENTAL_SCENARIOS,
    CrewMember,
    MenstrualCycle,
    PhysiologicalSimulator,
    Scenario,
    evidence_report,
)
from app.ingest.wearable import BLE_RR_WINDOW, EARLIEST_IMPORTED_READING, WearableAdapter
from app.volumes.samples import catalog as sample_catalog

router = APIRouter()

# Ventana de lecturas que define el estado "actual". El historial anterior lo
# interpreta el analisis de tendencia, no la deteccion de desviacion.
CURRENT_WINDOW = dt.timedelta(days=2)

# SOLO LO MEDIDO DECIDE (especificacion §2 «Uncertainty first», §10 y §14; decision del usuario
# del 2026-10-26).
#
# `POST /api/observations` acepta lecturas `inferred` y `predicted`, y el estado las metia en la
# linea base, la tendencia y el riesgo como si fueran de un sensor: una deriva extrapolada podia
# moverse a si misma la base contra la que se juzga, y una estimacion de modelo sostener una
# alerta que el detalle presentaba como medida. Ahora la linea base, la tendencia y el riesgo
# leen solo los tipos de aqui; lo demas se firma en el ledger igual y se ensena rotulado, sin
# decidir. Es una regla que cambia alertas: entra en `rules_version` (`core/versioning.py`).
ANALYSED_TYPES: tuple[ObservationType, ...] = (ObservationType.MEASURED,)


# LA DOSIS EFECTIVA ES INFERIDA POR DEFINICION, Y EL LIMITE DE CARRERA SE DEFINE SOBRE ELLA.
#
# La dosis efectiva sale de la absorbida por el factor de calidad y los pesos de tejido: EMMA la
# rotula INFERIDA siempre (`dose.observation_type`, H23 de `risk-management-file.md`). Si el
# limite de carrera solo leyera dosis medidas, una dosis bien rotulada no llegaria nunca a el y
# volveria el fallo que cerro «LA DOSIS REGISTRADA CUENTA» (`_assess`). Por eso el limite lee la
# dosis acumulada medida o inferida, nunca la predicha (una proyeccion no es dosis recibida). No
# es una linea base ni una tendencia: es un acumulado frente a un limite normativo. Excepcion
# declarada a `ANALYSED_TYPES`, pendiente de que el usuario la confirme (§5.37.1), y en la huella.
# Todos menos el predicho (medida e inferida). Se escribe asi y no nombrando la inferida: la
# regla lee un rotulo, no lo pone (`tests/test_credibility.py` cuenta quien rotula una cifra).
DOSE_TYPES: tuple[ObservationType, ...] = tuple(
    kind for kind in ObservationType if kind is not ObservationType.PREDICTED
)
CUMULATIVE_DOSE = "cumulative-dose"


def is_analysed_type(observation: VitalObservation) -> bool:
    """Si el tipo de la lectura (medida, inferida, predicha) es de los que deciden."""
    return observation.observation_type in ANALYSED_TYPES


def analysed_type_words() -> str:
    """Los tipos que deciden, en palabras («medidas»), para las frases que los nombran.

    Las frases que dicen lo que el estado aparta por su tipo (el habitat, el diario y las
    sesiones PVT, §5.39.11) se componen con esto y no con la palabra escrita a mano: si un dia
    `ANALYSED_TYPES` cambia, cambian con ella en vez de quedarse mintiendo.

    En inglés, la palabra de cada tipo es la que registre su dueño (`analysis/alert_support.py`).
    """
    if i18n.current() == "en":
        return " or ".join(i18n.loc(TYPE_WORDS[str(kind)][1]) for kind in ANALYSED_TYPES)
    return " o ".join(TYPE_WORDS[str(kind)][1] for kind in ANALYSED_TYPES)


def decides(observation: VitalObservation) -> bool:
    """Si una lectura entra en el analisis del estado: no descriptiva y de un tipo que decide.

    Quien sitúe lecturas con el «ahora» del estado no la llama: pide ese «ahora» a
    `state_reference`, que aparta con esto antes de fijarlo (§5.38.7). Un filtro con `decides`
    seguido de una referencia propia es otra regla del «ahora», la que ya se partió una vez.
    """
    return observation.key not in DESCRIPTIVE_ONLY and is_analysed_type(observation)


# EL "AHORA" DEL ESTADO NO PUEDE DECIDIRLO UNA SOLA LECTURA.
#
# La ventana actual se contaba desde la lectura mas reciente. Una sola mal
# fechada —un reloj de dispositivo roto, una importacion con la zona horaria
# equivocada— la movia: un peso fechado en 2099 dejaba fuera todas las
# desviaciones de hoy, y una arritmia en CONCERN pasaba a WATCH con la
# integridad en verde. Una del año 1 tumbaba el endpoint.
#
# No basta con validar la ingesta: el ledger es de solo anadir, y una lectura
# asi, una vez dentro, se queda. El analisis tiene que sobrevivirla.
#
# La referencia es la lectura mas reciente que **no llega sola tras un hueco
# anomalo**. Lo que cae despues, o antes de `_EARLIEST_PLAUSIBLE`, no se analiza,
# y la respuesta dice cuantas y por que.
#
# "Anomalo" se mide contra los huecos tipicos de esos mismos datos, no contra un
# reloj fijo. La primera version exigia `_REFERENCE_SUPPORT` lecturas dentro de
# `CURRENT_WINDOW`, y **reproducia el fallo que arreglaba** con datos de baja
# cadencia: con un peso cada cinco dias ninguna lectura reune tres en dos dias,
# ninguna corrobora, y la referencia recaia otra vez en la ultima sin corroborar.
# Lo encontro una revision adversaria; funcionaba solo porque los datos de prueba
# eran densos.
#
# Dos limites declarados. Un **lote** mal fechado si mueve la referencia: un
# reloj roto que emite durante dias es indistinguible de datos buenos sin un
# reloj de mision independiente. Y con menos de `_REFERENCE_SUPPORT` lecturas en
# total no hay con que juzgar: se toma la ultima y se dice que no se comprobo.
_REFERENCE_SUPPORT = 3
# Cuanto mayor que lo habitual tiene que ser un hueco para aislar a lo que venga
# detras. Diez veces el hueco tipico: un wearable que calla unas horas sigue
# siendo el mismo flujo; una lectura fechada decadas despues, no.
_GAP_FACTOR = 10
# La misma cota que la ingesta: lo que hoy no entraria, tampoco se analiza.
_EARLIEST_PLAUSIBLE = EARLIEST_IMPORTED_READING


def _uncontested_time(times: Sequence[dt.datetime]) -> dt.datetime:
    """La ultima marca temporal que no llega sola tras un hueco anomalo.

    Los datos se parten en grupos alli donde el hueco entre lecturas consecutivas
    supera `separacion`, que sale de los huecos tipicos de esos mismos datos: asi
    vale igual para un wearable continuo que para un peso semanal. Un grupo final
    con menos de `_REFERENCE_SUPPORT` lecturas se descarta y se prueba con el
    anterior; si no queda nada mas, se acepta, porque ya no hay con que compararlo.
    """
    if len(times) < _REFERENCE_SUPPORT:
        return times[-1]  # sin datos para juzgar: se toma la ultima y se declara

    gaps = sorted(later - earlier for earlier, later in zip(times, times[1:], strict=False))
    # Mediana BAJA. Con la alta, dos lecturas seguidas y una tercera fechada en 2099 daban
    # un hueco "tipico" de 73 anos: nada parecia anomalo, la de 2099 pasaba a ser el
    # "ahora" y la alerta real salia de la ventana. Con pocos huecos, el mayor no puede
    # decidir que es normal.
    typical = gaps[(len(gaps) - 1) // 2]
    separation = max(CURRENT_WINDOW, _GAP_FACTOR * typical)

    end = len(times)
    while end > 0:
        start = end - 1
        while start > 0 and times[start] - times[start - 1] <= separation:
            start -= 1
        if end - start >= _REFERENCE_SUPPORT or start == 0:
            return times[end - 1]
        end = start
    return times[-1]


def _analysable(
    observations: Sequence[VitalObservation],
) -> tuple[list[VitalObservation], dt.datetime, dict[str, int]]:
    """Lecturas que entran en el analisis, la referencia del "ahora" y lo apartado."""
    plausible = [o for o in observations if o.effective >= _EARLIEST_PLAUSIBLE]
    ignored = {"implausibly_old": len(observations) - len(plausible), "after_reference": 0}
    if not plausible:
        return [], _EARLIEST_PLAUSIBLE, ignored

    times = sorted(o.effective for o in plausible)
    reference = _uncontested_time(times)

    kept = [o for o in plausible if o.effective <= reference]
    ignored["after_reference"] = len(plausible) - len(kept)
    return kept, reference, ignored


# UN SOLO «AHORA» PARA LO QUE DECIDE (decimoctava ronda, §5.38.7).
#
# Cada vía que situaba lecturas con el «ahora» del estado escribía su propio filtro antes de
# `_analysable`, y la fusión de la ronda 17 los dejó distintos: la radiación del hábitat lo
# calculaba con TODAS las lecturas (una predicha fechada en el futuro movía su «ahora», y su
# «última tasa de dosis» podía ser inferida o predicha), y las rutinas y las sesiones PVT
# apartaban lo no medido pero no lo descriptivo. Ahora el filtro va dentro: quien quiera el
# «ahora» del estado lo pide aquí, y nadie más llama a `_analysable`
# (`tests/test_state_reference.py` lo vigila en el código).
def state_reference(
    readings: Sequence[VitalObservation],
) -> tuple[list[VitalObservation], dt.datetime, dict[str, int]]:
    """Lo que el estado analiza de `readings`, su «ahora» y lo apartado por la fecha.

    Primero lo que decide (`decides`: ni descriptivo ni inferido o predicho) y, de eso, las
    fechas analizables (`_analysable`). Es la regla de `_assess`, dicha una vez.
    """
    return _analysable([item for item in readings if decides(item)])


def _now() -> dt.datetime:
    """El reloj real. Aparte para poder fijarlo en las pruebas."""
    return dt.datetime.now(dt.UTC)


# Un evento solar deja de ser una amenaza activa pasado este tiempo.
SOLAR_EVENT_RELEVANCE = dt.timedelta(days=3)


# --------------------------------------------------------------------------- #
# Dependencias
# --------------------------------------------------------------------------- #

_store: ObservationStore | None = None
_store_lock = threading.Lock()
_identities: dict[str, Identity] = {}


def get_store() -> ObservationStore:
    """Almacen unico del proceso.

    En vuelo seria un fichero persistente; aqui se resuelve por configuracion
    para que las pruebas usen uno aislado.
    """
    global _store
    # Bajo cerrojo: las primeras peticiones simultaneas creaban almacenes distintos, y
    # las lecturas confirmadas con 201 en los que se perdian desaparecian sin rastro.
    with _store_lock:
        if _store is None:
            _store = new_store()
        return _store


def new_store() -> ObservationStore:
    """Almacen en memoria abierto con la autoridad de redaccion de este proceso.

    La autoridad es efimera, como el almacen: vive lo que vive el proceso. Un almacen
    en fichero necesitaria una clave de redaccion aprovisionada y persistente, o las
    lapidas anteriores dejarian de verificar al reiniciar
    (`compliance/record-integrity.md` §3.6).
    """
    return ObservationStore.in_memory(RedactionAuthority.of(audit_identity()))


def reset_store(store: ObservationStore | None = None) -> None:
    """Punto de sustitucion para pruebas y arranque."""
    global _store
    with _store_lock:
        _store = store


def identity_for(source: str) -> Identity:
    """Clave de firma por fuente de datos.

    En produccion cada wearable trae su clave aprovisionada; aqui se genera una
    por fuente y se mantiene estable durante el proceso.

    `emma-audit` (y su nombre anterior, `halo-audit`) esta reservado. Si una fuente pudiera
    llamarse asi, sus lecturas
    saldrian firmadas por el sistema de auditoria, y la clave generada para ella
    quedaria fijada en el registro: la siguiente redaccion chocaria con esa clave y
    fallaria. Cualquiera podia bloquear las rectificaciones enviando una lectura.
    """
    if source == AUDIT_IDENTITY or source in FORMER_AUTHORITY_IDS[AUDIT_IDENTITY]:
        raise HTTPException(
            status_code=422, detail=f"'{source}' es una identidad reservada"
        )
    # Comprobar y asignar bajo cerrojo: dos primeras peticiones simultaneas de la
    # misma fuente generaban dos claves, y la que perdia chocaba con la ya fijada.
    with _identities_lock:
        if source not in _identities:
            _identities[source] = Identity.generate(source)
        return _identities[source]


AUDIT_IDENTITY = "emma-audit"

# Los nombres que firmaban antes de que HALO pasara a llamarse EMMA (2026-11-02). Ninguna fuente
# puede usarlos: firmaria como el sistema de entonces.
FORMER_SYSTEM_SOURCES = ("halo-audit", "halo-forecast")


def _is_reserved_source(source: str) -> bool:
    """Fuentes que la ingesta publica no puede usar.

    Una lectura real firmada como `simulator:...` la descartaria un cambio de escenario;
    firmada como la consola, podria reconocer o silenciar alertas; como `ultrasound` o
    `pain-report`, se mezclaria con lecturas que exigen su procedencia o su informe. Solo
    el propio sistema firma asi. `crew-diary` y `console-pvt` son las fuentes del registro
    diario y de la PVT hecha en pantalla: las fija su propia ruta (`api/diary.py`,
    `api/pvt_console.py`), que exige el nombre de quien teclea; por aqui entrarian sin el.
    `console-cognition`, la de las puntuaciones de la bateria Cognition anotadas en pantalla
    (`api/cognition.py`), igual.
    """
    return source.split(":", 1)[0] == _SIMULATOR_SOURCE or source in {
        AUDIT_IDENTITY, CONSOLE_IDENTITY, "interpretation-local", "ultrasound", "pain-report",
        "segmentation-local", FORECAST_SIGNER, EPHEMERIS_SIGNER, *FORMER_SYSTEM_SOURCES,
        "crew-diary", "console-pvt", "console-cognition",
        # Firma las notas de Tierra (`api/ground_notes.py`): una lectura firmada así se haría
        # pasar por Tierra.
        GROUND_IDENTITY,
        # Firma los lotes de lecturas de las anclas de módulo (`api/location_anchors.py`): una
        # lectura firmada así se mezclaría con lo que oyó un receptor (2026-11-10).
        identities.ANCHOR_IDENTITY,
        # Firma las transacciones de Marplanner (`api/planner.py`, 2026-11-12).
        identities.PLANNER_IDENTITY,
    }
_audit_signer: Identity | None = None
_identities_lock = threading.Lock()


def audit_identity() -> Identity:
    """La autoridad de redaccion: la unica identidad que firma lapidas.

    El sistema da fe de que se redacto; quien lo pidio queda declarado dentro de la
    propia lapida (ver `RedactionIn`). El almacen se abre con su clave publica
    (`new_store`) y no acepta lapidas de nadie mas.
    """
    global _audit_signer
    with _identities_lock:
        if _audit_signer is None:
            _audit_signer = Identity.generate(AUDIT_IDENTITY)
        return _audit_signer


SettingsDep = Annotated[Settings, Depends(get_settings)]
StoreDep = Annotated[ObservationStore, Depends(get_store)]


# --------------------------------------------------------------------------- #
# Modelos de entrada
# --------------------------------------------------------------------------- #


class ObservationIn(BaseModel):
    """Alta manual de una lectura.

    `model_config` prohibe campos extra a proposito. Antes los descartaba en
    silencio, y eso escondia dos agujeros: `context` y `confidence` **no
    existian** en este modelo, asi que un cliente que los enviara veia un 201 y
    su lectura entraba como contexto desconocido y confianza plena. La
    estratificacion por contexto y el tope de baja confianza —el nucleo de la
    reduccion de falsas alarmas— eran inalcanzables desde aqui. Un campo mal
    escrito ahora es un 422, no una perdida muda.
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="Clave del catálogo, p. ej. 'heart-rate'")
    value: float
    # Un sujeto vacio se aceptaba y la lectura se archivaba bajo un tripulante
    # inexistente: no aparecia en el estado de nadie y no daba ningun error. Una
    # constante vital que desaparece en silencio es el peor fallo posible aqui.
    subject: str = Field(default="crew-01", min_length=1)
    source: str = Field(default="manual", min_length=1)
    effective: dt.datetime | None = None
    context: Context = Context.UNKNOWN
    confidence: float = Field(default=FULL_CONFIDENCE, ge=0.0, le=1.0)
    # Especificacion del equipo §5: medido / inferido / predicho, entorno y modelo.
    # Sin `evidence_context`, vale el del despliegue. Un valor no medido sin
    # `model_version` es un 422: no se puede auditar de donde sale.
    observation_type: ObservationType = ObservationType.MEASURED
    evidence_context: EvidenceContext | None = None
    model_version: str | None = Field(default=None, min_length=1, max_length=128)
    # LA UNIDAD UCUM EN QUE VIENE `value`, SI QUIEN ENVIA LA CONOCE (especificacion §5:
    # «unidades y procedencia explicitas»; invariante 2; plan de la decimosexta ronda).
    #
    # Antes no existia: la cifra se guardaba en la unidad del catalogo sin preguntar, y una
    # vitamina D en nmol/L entraba como si fuera ng/mL. Ahora, si viene y no es la del catalogo,
    # es un 422 sin asiento y sin conversion (`_unit_or_422`). Es OPCIONAL para no romper a
    # quien ya enviaba sin ella: si falta se asume la del catalogo y la respuesta lo dice
    # (`unit_assumed`). No se firma: el asiento guarda la cifra, que siempre esta en la unidad
    # del catalogo (`record-integrity.md` §3.14 quater).
    #
    # Vacia o de mas de `UNIT_MAX_LENGTH` caracteres tambien es un 422, pero lo da
    # `_unit_or_422` y no el esquema: el esquema respondia con la lista de errores de Pydantic, en
    # ingles, y las demas unidades rechazadas con el motivo en espanol.
    unit: str | None = None
    # DE QUÉ PLATO ES LA LECTURA, si quien envía lo sabe (decimonovena ronda, 2026-10-31). Solo lo
    # admiten la aceptabilidad de la comida y la fracción rechazada (`ingest/food_item.py`); en
    # cualquier otro indicador es un 422 sin asiento, y uno que no cumple la regla, también. Es
    # OPCIONAL aquí incluso en la valoración: por esta ruta entra lo que no conoce el plato (el
    # simulador, un cliente antiguo), que se sigue contando «sin alimento declarado»; el registro
    # diario sí lo exige. Hasta esta ronda la ruta no tenía el campo y, con `extra="forbid"`,
    # enviarlo era un 422: lo que entraba por aquí no podía decir de qué plato era. Se firma como
    # el del diario (`record-integrity.md` §3.14 quinquies); el tope solo evita leer un texto
    # enorme antes de aplicar la regla.
    food_item: str | None = Field(default=None, max_length=FOOD_ITEM_FIELD_MAX_LENGTH)

    @field_validator("source")
    @classmethod
    def _not_reserved(cls, value: str) -> str:
        if _is_reserved_source(value):
            raise ValueError(f"'{value}' es una identidad reservada del sistema")
        return value


class PvtSubmission(BaseModel):
    reaction_times_ms: list[float] = Field(min_length=1)
    subject: str = Field(default="crew-01", min_length=1)
    effective: dt.datetime | None = None


class BleFrame(BaseModel):
    frame_hex: str = Field(description="Trama GATT Heart Rate Measurement en hexadecimal")
    subject: str = Field(default="crew-01", min_length=1)
    effective: dt.datetime | None = None
    # Opcional: que dispositivo envia, si quien envia lo sabe. Solo sirve para el aviso del
    # vinculo sensor-tripulante (`ingest/bindings.py`); sin el, la lectura entra igual.
    device: str | None = None


class RedactionIn(BaseModel):
    """Solicitud de rectificacion. Motivo y solicitante quedan en la lapida firmada.

    La API **no autentica** a quien la pide: `requested_by` es lo que declara. Queda
    registrado y firmado por el sistema, pero no demuestra identidad. La autenticacion
    de operadores esta pendiente (`compliance/record-integrity.md` §5).

    `strip_whitespace` porque "   " pasaba la longitud minima y llegaba al ledger como
    un motivo vacio.
    """

    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    requested_by: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
    ]

    @field_validator("reason", "requested_by")
    @classmethod
    def _has_text(cls, value: str) -> str:
        # `strip_whitespace` no quita U+200B: un motivo invisible pasaba como valido.
        if not any(character.isalnum() for character in value):
            raise ValueError("debe contener al menos una letra o una cifra")
        return value


class AmendmentIn(BaseModel):
    """Correccion de una lectura ya registrada, sin borrar la anterior.

    Es la via de 45 CFR 164.526: la version buena se anexa y queda enlazada con la
    que corrige, que sigue registrada y visible en `/api/audit`. La redaccion, que
    borra, queda para el dato que nunca debio existir.

    Como en `RedactionIn`, la API **no autentica** a quien corrige: `amended_by` sera
    la fuente que firme, y eso no demuestra identidad.
    """

    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    correction: ObservationIn

    @field_validator("reason")
    @classmethod
    def _has_text(cls, value: str) -> str:
        if not any(character.isalnum() for character in value):
            raise ValueError("debe contener al menos una letra o una cifra")
        return value


class AcknowledgementIn(BaseModel):
    """Reconocimiento de una alerta: queda firmado en el ledger.

    `reference_time` es el `data.reference_time` del estado que vio quien reconoce.
    Como en `RedactionIn`, la API **no autentica**: `acknowledged_by` es lo que se
    declara, queda registrado y firmado por la consola, y no demuestra identidad.
    """

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(default="crew-01", min_length=1, max_length=64)
    domain: Domain
    level: RiskLevel
    reference_time: dt.datetime
    acknowledged_by: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
    ]

    @field_validator("level")
    @classmethod
    def _is_an_alert(cls, value: RiskLevel) -> RiskLevel:
        if value is RiskLevel.NOMINAL:
            raise ValueError("nominal no es una alerta: no hay nada que reconocer")
        return value

    @field_validator("reference_time")
    @classmethod
    def _has_timezone(cls, value: dt.datetime) -> dt.datetime:
        if value.tzinfo is None:
            raise ValueError("debe llevar zona horaria")
        return value

    @field_validator("acknowledged_by")
    @classmethod
    def _has_text(cls, value: str) -> str:
        if not any(character.isalnum() for character in value):
            raise ValueError("debe contener al menos una letra o una cifra")
        return value


class _AnnunciationBase(BaseModel):
    """Lo comun a suprimir, inhibir y habilitar: sobre que, cuando, por que y quien.

    Silenciar una alarma clinica exige un motivo: sin el, el registro diria que se
    silencio, pero no por que, y eso no sirve para revisar la decision despues.
    """

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(default="crew-01", min_length=1, max_length=64)
    domain: Domain
    reference_time: dt.datetime
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    requested_by: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
    ]

    @field_validator("reference_time")
    @classmethod
    def _has_timezone(cls, value: dt.datetime) -> dt.datetime:
        if value.tzinfo is None:
            raise ValueError("debe llevar zona horaria")
        return value

    @field_validator("reason", "requested_by")
    @classmethod
    def _has_text(cls, value: str) -> str:
        if not any(character.isalnum() for character in value):
            raise ValueError("debe contener al menos una letra o una cifra")
        return value


class SuppressionIn(_AnnunciationBase):
    """Suprimir **una alerta concreta**: la de este dominio a este nivel."""

    level: RiskLevel
    duration_minutes: int = Field(ge=15, le=12 * 60)

    @field_validator("level")
    @classmethod
    def _is_an_alert(cls, value: RiskLevel) -> RiskLevel:
        if value is RiskLevel.NOMINAL:
            raise ValueError("nominal no es una alerta: no hay nada que suprimir")
        return value


class InhibitionIn(_AnnunciationBase):
    """Inhibir un dominio **hasta un nivel**, incluidas alertas que aun no existen."""

    level: RiskLevel
    duration_hours: int = Field(ge=1, le=7 * 24)

    @field_validator("level")
    @classmethod
    def _below_critical(cls, value: RiskLevel) -> RiskLevel:
        if value is RiskLevel.NOMINAL:
            raise ValueError("nominal no es una alerta: no hay nada que inhibir")
        if value is RiskLevel.CRITICAL:
            raise ValueError(
                "un dominio en crítico no se puede inhibir: dejaría de anunciarse "
                "cualquier alerta suya. Se puede suprimir, como mucho una hora"
            )
        return value


class EnableIn(_AnnunciationBase):
    """Volver a anunciar las alertas del dominio: anula supresion e inhibicion."""


# QUE SE PUEDE SILENCIAR, Y CUANTO.
#
# Suprimir es "ya lo se y lo estoy atendiendo": una alerta concreta, horas como mucho.
# Una critica, una hora: pasado ese tiempo, si sigue critica, vuelve a reclamar
# atencion. Inhibir es "este sensor no es fiable": todo el dominio hasta un nivel,
# dias como mucho, y nunca en critico. En los dos casos **una escalada se anuncia
# siempre**: lo silenciado era un nivel, y otro distinto es otra alerta.
MAX_CRITICAL_SUPPRESSION = dt.timedelta(hours=1)
_LEVEL_RANK = {RiskLevel.WATCH: 1, RiskLevel.CONCERN: 2, RiskLevel.CRITICAL: 3}


# Viven en `core/identities.py`, para que la crónica y los hilos en espera los lean sin importar
# las rutas. Se quedan con su nombre aquí para el resto de la API.
CONSOLE_IDENTITY = identities.CONSOLE_IDENTITY
_counts = identities.action_counts

# Identidad con que firma la consola de Tierra sus notas a bordo (`api/ground_notes.py`). Es otra
# clave que la de a bordo: una nota firmada con la de tripulación no se enseña como de Tierra, y la
# de Tierra no puede reconocer, silenciar ni descartar una alerta (el estado solo cuenta las
# acciones firmadas por `CONSOLE_IDENTITY`). La clave dice por qué ruta entró, no desde qué
# máquina: la API no autentica (`record-integrity.md` §7.5), y cualquier cliente que llegue a
# `POST /api/ground-notes` firma como Tierra, igual que cualquiera que llegue a reconocer una
# alerta firma como la consola de a bordo.
GROUND_IDENTITY = "ground-console"


def _recorded_or_422(write: Callable[[], LedgerEntry | list[LedgerEntry]]) -> list[LedgerEntry]:
    """Escribe en el almacen y traduce el rechazo del ledger a un 422.

    El ledger rechaza con ValueError lo que no puede registrar tal cual —un texto con
    un sustituto UTF-16 suelto, un anidamiento excesivo—. Sin traducirlo salia como un
    500: el cliente veia "error del servidor" donde el fallo era de su dato. La
    transaccion ya se ha deshecho: no queda nada a medias.
    """
    try:
        written = write()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return written if isinstance(written, list) else [written]


def _when(value: dt.datetime | None) -> dt.datetime:
    """El instante de una lectura: el recibido o ahora, siempre con zona horaria.

    Por abajo se acota como en la importacion: una lectura del ano 1 entraba con un 201 y
    dejaba el estado del tripulante sin analizar, y con un desfase de +23:59 desbordaba y
    daba 500. Por arriba no se acota, porque las pruebas y el simulador usan la fecha de
    la mision; de las lecturas futuras se defiende el analisis de `/api/status`.
    """
    if value is None:
        return dt.datetime.now(dt.UTC)
    moment = value if value.tzinfo else value.replace(tzinfo=dt.UTC)
    try:
        utc = moment.astimezone(dt.UTC)
    except OverflowError as exc:
        raise HTTPException(status_code=422, detail="instante fuera de rango") from exc
    if utc < EARLIEST_IMPORTED_READING:
        raise HTTPException(
            status_code=422,
            detail=f"instante {utc.isoformat()} anterior a {EARLIEST_IMPORTED_READING.date()}",
        )
    return moment


# --------------------------------------------------------------------------- #
# Lectura
# --------------------------------------------------------------------------- #


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/framework")
def framework() -> dict[str, Any]:
    """Marco de NASA en que se inscribe el sistema."""
    return {
        "eimo": i18n.loc(EIMO_DESCRIPTION),
        "amcl_alignment": {
            str(domain): i18n.loc(amcl_alignment(domain)) for domain in Domain
        },
        "standard": i18n.tr(
            "NASA-STD-3001 Vol 1 Rev C — requisito central [V1 3004] h",
            "NASA-STD-3001 Vol 1 Rev C — core requirement [V1 3004] h",
        ),
        # Los dos huecos de ExMC de los que parte el diseño (especificacion §16), con su
        # enunciado de 2020 (NTRS, leido el 2026-09-28) y el estado que publica hoy el Human
        # Research Roadmap, tomado de lo leido (app/evidence/nasa_framework.py): ninguno de los
        # dos figura abierto, y el texto no los presenta como huecos que EMMA cierre.
        "exmc_gaps": {
            "source": "Krihak et al., Medical Data Architecture Prototype Development, "
                      "NTRS 20200000567 (2020)",
            "url": evidence_registry.get("ntrs-20200000567").url,
            "note": i18n.tr(
                    "Enunciados de 2020, de los que parte el diseño del equipo. Hoy no "
                    "figuran como huecos abiertos: cada uno lleva el estado que publica el "
                    "Human Research Roadmap, con la fecha en que se leyó. Lo que dice EMMA es "
                    "a qué pregunta del enunciado responde su prototipo, no que lo cierre.",
                    "Statements from 2020, the starting point of the team's design. Today they "
                    "are not listed as open gaps: each carries the status published by the "
                    "Human Research Roadmap, with the date it was read. What EMMA states is "
                    "which question of the statement its prototype responds to, not that it "
                    "closes the gap.",
            ),
            "med07": {
                "label": "Med 07",
                "gap": "We do not have the capability to comprehensively process "
                       "medically-relevant information to support medical operations during "
                       "exploration missions",
                "status": nasa_framework.gap_status("Med07"),
                "emma": i18n.tr(
                        "Responde a la pregunta del enunciado —reunir y procesar a bordo la "
                        "información médica— integrando constantes, autoinformes, ecografía, "
                        "hábitat, radiación y misión en un registro firmado y un único estado "
                        "por tripulante. NASA da el hueco por cerrado con su propia capacidad; "
                        "EMMA no ha contribuido a ese cierre ni se ha evaluado frente a ella.",
                        "It responds to the question in the statement — gathering and processing "
                        "medical information on board — by integrating vital signs, self-reports, "
                        "ultrasound, habitat, radiation and mission data into a signed record and "
                        "a single status per crew member. NASA considers the gap closed with its "
                        "own capability; EMMA has not contributed to that closure and has not "
                        "been evaluated against that capability.",
                ),
            },
            "med10": {
                "label": "Med 10",
                "gap": "We do not have the capability to provide computed medical decision "
                       "support during exploration missions",
                "status": nasa_framework.gap_status("Med10"),
                "merged_into": nasa_framework.gap_status("Medical-701"),
                "emma": i18n.tr(
                        "Responde a la pregunta del enunciado —apoyo a la decisión computado "
                        "durante la misión— con apoyo a la decisión a bordo, sin red, con "
                        "evidencia y contramedidas estructuradas; no diagnostica ni prescribe. "
                        "El hueco se fusionó en Medical-701, que figura abierto; EMMA no forma "
                        "parte del trabajo de ExMC sobre él.",
                        "It responds to the question in the statement — computed decision support "
                        "during the mission — with on-board decision support, without a network, "
                        "with structured evidence and countermeasures; it does not diagnose or "
                        "prescribe. The gap was merged into Medical-701, which is listed as open; "
                        "EMMA is not part of ExMC's work on it.",
                ),
            },
        },
        "imm": {
            "url": evidence_registry.get("nasa-imm").url,
            "what": i18n.tr(
                    "Modelo de NASA que, con simulaciones de Monte Carlo y la base iMED, "
                    "pronostica riesgos médicos antes del lanzamiento.",
                    "NASA model that, with Monte Carlo simulations and the iMED database, "
                    "forecasts medical risks before launch.",
            ),
            "not_duplicated": i18n.tr(
                              "EMMA no pronostica la misión antes de volar: vigila a cada "
                              "tripulante durante el vuelo frente a su propia línea base.",
                              "EMMA does not forecast the mission before flight: it monitors "
                              "each crew member during flight against their own baseline.",
            ),
        },
        # Peligro RIDGE de cada dominio (NASA, "The Human Body in Space").
        "ridge": {
            str(domain): {
                "hazard": str(domain.ridge), "display": i18n.loc(domain.ridge.display)
            }
            for domain in Domain
        },
        # Hipotesis H1-H7 de la base de conocimiento (§13) y anclajes de la especificacion
        # (§16) sin leer. Inventario: ninguna figura como probada, y no entra en el analisis.
        "design_hypotheses": design_hypotheses.payload(),
        # Lo leido en las fuentes oficiales el 2026-10-13 (arquitectura CDSS, Med 07 cerrado y
        # Med 10 fusionado, limitaciones del IMM, huecos de alimentacion, niveles de asistencia):
        # la frase exacta con su cita y, aparte, que hace EMMA. Citar no es implementar
        # (invariante 6).
        "read_sources": nasa_framework.payload(),
        # Decimosexta ronda (E10): cada cifra INFERIDA o PREDICHA con los once factores de
        # credibilidad de NASA-STD-7009B, en palabras y sin nivel (app/evidence/credibility.py);
        # null si el fichero no pasa su contrato, sin tumbar el resto del marco.
        "credibility": credibility.served(),
    }


@router.get("/anatomy")
def anatomy_map() -> dict[str, Any]:
    """Region del cuerpo → dominios que la cubren (especificacion §10). Solo presentacion."""
    return {"regions": anatomy.describe()}


@router.get("/anatomy/skeleton")
def anatomy_skeleton() -> dict[str, Any]:
    """Esqueleto de referencia (BodyParts3D, CC BY 4.0): centroide de cada hueso en la imagen."""
    return anatomy.skeleton()


@router.get("/anatomy/skeleton.png")
def anatomy_skeleton_image() -> StarletteResponse:
    """La imagen del esqueleto de referencia, vista anterior. Solo lectura, viaja con la app."""
    return StarletteResponse(
        anatomy.skeleton_png(), media_type="image/png",
        headers={"Cache-Control": "max-age=86400"},
    )


@router.get("/anatomy/skeleton/own")
def anatomy_own_skeleton(store: StoreDep, subject: str = "crew-01") -> dict[str, Any]:
    """El esqueleto que se enseña de un tripulante: el de su TAC si tiene una segmentación del
    esqueleto vigente (`volumes/skeleton_view.py`); si no, el de referencia. La respuesta dice
    cuál es (`source`), de qué asiento sale y qué huesos no trae. Se calcula al servir."""
    return anatomy.subject_skeleton(store, subject)


@router.get("/anatomy/skeleton/own/{ledger_index}.png")
def anatomy_own_skeleton_image(store: StoreDep, ledger_index: int) -> StarletteResponse:
    """La vista anterior de la segmentación del esqueleto de ese asiento. Sale del binario
    firmado, comprobado en cada entrega; no se guarda en caché del navegador: un estudio
    retirado deja de verse."""
    try:
        image = anatomy.subject_skeleton_png(store, ledger_index)
    except anatomy.SkeletonUnavailable as failed:
        raise HTTPException(status_code=404, detail=failed.reason) from failed
    return StarletteResponse(
        image, media_type="image/png", headers={"Cache-Control": "no-store"}
    )


@router.get("/anatomy/pain-on-skeleton")
def pain_on_skeleton_view(store: StoreDep, subject: str = "crew-01") -> dict[str, Any]:
    """Zonas con dolor referido en los últimos días, colocadas con el ajuste de Polaris
    (`app/pain_on_skeleton.py`) sobre el esqueleto que se enseña de ese tripulante —el de su TAC
    o el de referencia; la respuesta dice cuál—, y su error residual."""
    return pain_on_skeleton.overlay(
        store.pain_reports(subject), figure=anatomy.subject_skeleton(store, subject)
    )


def _declared_resources(store: ObservationStore, until: dt.datetime | None) -> Any:
    """Los recursos de a bordo declarados que cuentan: firmados por la consola y, para Tierra,
    existentes en su corte. Una sola lectura para `/status` y para el modo anatomico: con dos
    copias, una podia contar declaraciones que la otra no."""
    return resource_rules.visible(
        [item for item in store.resource_declarations() if _counts(item, until)], until
    )


def _decorate_recommendations(
    recommendations: Sequence[Recommendation],
    decisions: Sequence[dict[str, Any]],
    followup_items: Sequence[dict[str, Any]],
    declared_resources: Any,
) -> list[dict[str, Any]]:
    """Cada recomendacion con lo que va a su lado, en un solo sitio para `/status` y el modo
    anatomico: lo que una persona decidio sobre ella (`decision`), la respuesta previa
    (`prior_response`), los recursos declarados (`resource_status`) y los efectos de su
    contramedida con la co-adopcion (`effects`). Cada funcion solo ANADE su campo: ninguna quita,
    reordena ni toca la urgencia, y ninguna decide nada. Antes la cadena se repetia a mano en las
    dos rutas y una se quedo sin un campo (lo cazo `tests/test_anatomy.py`, que las compara)."""
    decorated = with_decisions([item.to_dict() for item in recommendations], decisions)
    decorated = with_prior_response(decorated, followup_items)
    decorated = resource_rules.with_resources(decorated, declared_resources)
    return with_effects(decorated, followup_items)


@router.get("/anatomy/state")
def anatomy_state(
    settings: SettingsDep,
    store: StoreDep,
    subject: str = "crew-01",
    epoch: dt.date | None = None,
    cumulative_dose_msv: float | None = Query(default=None, ge=0.0),
    until: dt.datetime | None = None,
) -> dict[str, Any]:
    """La cadena del modo anatómico (especificación §10) con el mismo análisis que `/status`.

    Mismos parámetros y misma evaluación (`_assess`): el nivel de una región no puede salir de
    otra regla que el del dominio que la cubre. `app/anatomy.py` solo compone. Con `until`, el
    estado en ese instante, recalculado ahora y sin asiento (`moment`); `moments` dice qué
    instantes de la misión se pueden pedir.
    """
    assessed = _assess(settings, store, subject, epoch, cumulative_dose_msv, until)
    cutoff = assessed.latest - CURRENT_WINDOW
    recommendations = Advisor().recommend(assessed.status, _driver_keys(assessed))
    decisions = [item for item in store.followup_decisions(subject) if _counts(item, until)]
    # El contexto externo de cada region (KB «ASTRONAUT TWIN ↔ HABITAT TWIN») sale del mismo
    # constructor que el de las alertas de `/status`, con las mismas adopciones.
    context_around = _alert_context_builder(
        settings, store, subject, until, assessed,
        [item for item in decisions if item["action"] == "adopted"],
    )
    regions = anatomy.state(
        assessed.status,
        # La dosis inferida que valoro el limite (`DOSE_TYPES`) se ensena tambien, rotulada: el
        # valor que se enseña es el que se valoro.
        [*assessed.observations, *(item for item in assessed.doses if not is_analysed_type(item))],
        [dev for dev in assessed.deviations if dev.effective >= cutoff],
        assessed.trends,
        recommendations,
        dose_from_reading=assessed.dose_source == "observation",
        context_around=context_around,
    )
    # Las recomendaciones de cada region son las de `/status`, con lo mismo al lado
    # (`_decorate_recommendations`: la misma cadena, en el mismo orden). No decide nada: solo
    # copia lo que el estado ya ensena.
    decorated = _decorate_recommendations(
        recommendations,
        decisions,
        followups(
            decisions,
            {str(domain): risk.level for domain, risk in assessed.status.domains.items()},
            assessed.observations,
            assessed.latest,
        ),
        _declared_resources(store, until),
    )
    for region in regions:
        region["recommendations"] = [
            item for item in decorated if item["domain"] in region["domains"]
        ]
    return {
        "subject": assessed.status.subject,
        "reference_time": assessed.latest.isoformat(),
        "rules_version": rules_version(),
        "regions": regions,
        # Qué es este estado si se pidió en un momento pasado, y qué momentos hay que pedir. Los
        # momentos solo los da el estado de ahora: con `until` las lecturas ya están cortadas y
        # la lista saldría mermada (sin los R+ ni el regreso posteriores), así que no se da.
        "moment": anatomy.moment(until),
        "moments": (
            anatomy.moments(assessed.observations, settings.mission_start, settings.mission_days)
            if until is None else None
        ),
    }


@router.get("/indicators")
def indicators() -> dict[str, Any]:
    """Catalogo completo, declarando que codigos son LOINC reales y cuales no."""
    return {
        "count": len(CATALOG),
        "indicators": [
            {
                "key": code.key,
                "display": code.display,
                # El nombre con que lo lee la tripulación, y de dónde sale: ninguno es de LOINC
                # (`ingest/names_es.py`).
                **names_es.fields(code.key),
                "unit": code.unit,
                "domain": str(code.domain),
                "system": str(code.system),
                "is_standard_code": code.is_standard,
                # La categoría FHIR del recurso que se sirve, tal cual (`ingest/category_fit.py`).
                **category_fit.fields(code),
                # Descriptivo: se registra y se ensena, pero el estado no lo lee
                # (`codes.DESCRIPTIVE_ONLY`; panel en /api/indicators/descriptive).
                "descriptive_only": code.key in DESCRIPTIVE_ONLY,
                "reference_low": code.reference_low,
                "reference_high": code.reference_high,
                # Un consumidor tiene que poder distinguir "aqui esta la gente
                # sana" de "aqui conviene estar": solo el primero sirve para
                # juzgar si alguien se sale de lo normal. Sin rango, `null`: no hay base que
                # declarar. Va el enum tal cual (sale su valor); `str()` daria "None".
                "reference_basis": code.reference_basis,
                "critical_low": code.critical_low,
                "critical_high": code.critical_high,
                # F.5.6 c: los decimales que necesita quien lee. Se decide una vez, en
                # `core/display.py`, y la interfaz los usa en vez de repetir la tabla.
                "decimals": display.DECIMALS[code.key],
                # Que hace falta para obtenerlo y cuanto tiempo cuesta (KB §9).
                "measurement_cost": measurement_cost(code.key),
            }
            for code in CATALOG.values()
        ],
        # Las categorías que se quedan como están y no casan bien con ninguna de las nueve.
        "category_fit": category_fit.misfits(),
    }


@router.get("/evidence/{domain}")
def evidence(domain: Domain) -> dict[str, Any]:
    """Respaldo cientifico de la vigilancia de un dominio."""
    return {
        "domain": str(domain),
        # Vocabulario de NASA: situa el dominio dentro del marco de ExMC y
        # declara que parte de la condicion cubre el sistema y cual no.
        "amcl_alignment": i18n.loc(amcl_alignment(domain)),
        "evidence": [item.to_dict() for item in evidence_for(domain)],
    }


@router.get("/scenarios")
def scenarios() -> dict[str, Any]:
    return {
        "scenarios": [
            {"key": str(scenario), "label": str(scenario).replace("-", " ").capitalize()}
            for scenario in Scenario
        ]
    }


@router.get("/comms")
def comms(settings: SettingsDep, store: StoreDep, epoch: dt.date | None = None) -> dict[str, Any]:
    """Ventana de comunicacion con la Tierra: el parametro que exige autonomia.

    Con ella, lo que una persona declaro del enlace (`declared_link`, KB §2.1: la perdida de
    comunicaciones). Solo texto: el tiempo de luz sigue saliendo de las efemerides y nada de
    lo que decide lee la declaracion. Sin efemerides la respuesta es el 503 de siempre; la
    declaracion se lee entonces en `/api/status` y en `/api/habitat/systems`.

    El objetivo es el del perfil vigente (`mission_profiles.ephemeris_target`, 2026-11-11). Un
    perfil sin objetivo no tiene ventana que calcular: 404 que lo dice, sin consultar Horizons ni
    la cache (no es el 503 de «sin efemerides»: no falta nada).
    """
    chosen = _ephemeris_target(settings, store, None)
    if chosen.target is None:
        raise HTTPException(status_code=404, detail=_no_target_detail(chosen))
    try:
        payload = EphemerisClient(settings=settings).comms_window(
            epoch or utc_today(), chosen.target
        )
    except OfflineDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        # Horizons respondio con algo inservible, o su tiempo de luz no cuadra con
        # la distancia: la fuente contesto mal, no es que falte la red.
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        **payload.data.to_dict(),
        "data_age": payload.describe_age(),
        "data_age_seconds": payload.age_seconds,
        "from_cache": payload.from_cache,
        "source": payload.source,
        "declared_link": habitat_systems.earth_link(_system_declarations(store, None)),
        # La conjuncion solar del mismo dia (D6): solo se dice; nada de lo que decide la lee.
        "solar_conjunction": conjunction.describe(payload.data, chosen.target),
    }


def _profile_and_target(
    settings: Settings, store: ObservationStore, until: dt.datetime | None
) -> tuple[dict[str, Any], mission_profiles.EphemerisTarget]:
    """El perfil vigente hasta `until` (el firmado, o el configurado) y su objetivo de efemerides.

    Todo lo que consulta efemerides en la API lo pide aqui: el estado, `/comms`, la precarga y
    la cobertura usan el mismo perfil que sirve `mission.profile`. El estado lo lee una vez, en
    `_assess`, y sirve ese mismo (`_Assessment.mission_profile`): un cambio firmado entre medias
    no puede describir un objetivo distinto del que escalo el riesgo.
    """
    state = store.mission_profile(until, settings.mission_profile)
    return state, mission_profiles.ephemeris_target(str(state["id"]), settings)


def _ephemeris_target(
    settings: Settings, store: ObservationStore, until: dt.datetime | None
) -> mission_profiles.EphemerisTarget:
    """El objetivo de efemerides del perfil vigente hasta `until` (`_profile_and_target`)."""
    return _profile_and_target(settings, store, until)[1]


def _no_target_detail(chosen: mission_profiles.EphemerisTarget) -> str:
    return (
        f"el perfil de misión vigente ({chosen.profile_id!r}) no tiene objetivo de efemérides: "
        "el retardo no se calcula y no se consulta JPL Horizons ni su caché"
    )


@router.post(
    "/comms/preload",
    # Sin cuerpo: una petición simple de otra página lo dispararía (`api/console_header.py`).
    **console_post(),
)
def preload_comms(settings: SettingsDep, store: StoreDep) -> dict[str, Any]:
    """Precarga las efemerides de toda la mision, del lanzamiento al fin configurado (E6).

    La misma precarga que `scripts/preload_ephemeris.py`, pero dentro del proceso que sirve la
    consola: aqui la puerta de salida ve el modo seguro firmado en el ledger de este proceso, que
    el guion, con su propio proceso, no ve. Una consulta a Horizons por cada tramo de dias que
    falta (`ephemeris.day_runs`; dos tramos separados por `PRELOAD_BRIDGE_DAYS` dias en cache o
    menos van en una), y todas antes de escribir nada; lo ya cacheado no se reescribe. Sin red,
    en modo seguro o con el freno HALT, 503 con el motivo; una respuesta inservible de Horizons,
    502. Con otra precarga en curso en este proceso, espera a que acabe y mira lo que sigue
    faltando; si no acaba dentro del tope, 409 sin pedir nada. No toca el ledger: una efemeride
    no es una observacion.

    Se precarga hacia el objetivo del perfil vigente; con un perfil sin objetivo no hay nada que
    precargar: 409 que lo dice, sin pedir nada.

    Con SPICE primero (2026-11-11), si el calculo local cubre toda la mision esta precarga ya no
    hace falta para el retardo sin red: sirve de contraste y de respaldo, y la respuesta lo dice
    (`coverage.preload_role`). No se quita por eso.
    """
    chosen = _ephemeris_target(settings, store, None)
    if chosen.target is None:
        raise HTTPException(
            status_code=409, detail=f"{_no_target_detail(chosen)}; no hay nada que precargar"
        )
    start, end = ephemeris_coverage.mission_span(settings)
    if end < start:
        # Una configuracion sin dias no es culpa de Horizons (502): se dice que es la
        # configuracion, y no se pide nada.
        raise HTTPException(
            status_code=500,
            detail=(
                f"configuración: EMMA_MISSION_DAYS={settings.mission_days} no deja ningún día de "
                "misión; no se pide nada a JPL Horizons"
            ),
        )
    client = EphemerisClient(settings=settings)
    try:
        result = client.preload(start, end, chosen.target)
    except OfflineDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except PreloadInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        **result.to_dict(),
        "coverage": ephemeris_coverage.coverage(settings, client, target=chosen.target),
    }


def _system_declarations(
    store: ObservationStore, until: dt.datetime | None
) -> list[dict[str, Any]]:
    """Las declaraciones de sistemas que cuentan (`api/systems.py`), leidas una vez por respuesta.

    La importacion va aqui dentro porque `api/systems.py` importa este modulo.
    """
    from app.api.systems import system_declarations

    return system_declarations(store, until)


LOOKBACK_WINDOWS = (30, 90, 365, 1095)


@router.get("/space-weather")
def space_weather(
    settings: SettingsDep,
    # Solo estas ventanas (auditoría run-2, `emma:space-weather:lookback-quota-amplification`):
    # con cualquier número de 1 a 1095, cada valor era otra clave de caché y otra tanda de hasta
    # 19 consultas a api.nasa.gov con la clave del operador, y un GET de otra página la elegía.
    # La consola usa la de por defecto.
    lookback_days: int = Query(default=365, json_schema_extra={"enum": list(LOOKBACK_WINDOWS)}),
) -> dict[str, Any]:
    """Eventos solares recientes.

    La ventana por defecto es de un ano porque los eventos de particulas solares
    son escasos: pedir "los ultimos 30 dias" devuelve cero la mayoria del tiempo.
    """
    if lookback_days not in LOOKBACK_WINDOWS:
        raise HTTPException(
            status_code=422,
            detail=f"lookback_days tiene que ser uno de {list(LOOKBACK_WINDOWS)}",
        )
    end = utc_today()  # DONKI fecha en UTC, como las efemérides
    try:
        payload = DonkiClient(settings=settings).events(
            EventType.SEP, end - dt.timedelta(days=lookback_days), end
        )
    except OfflineDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    events = sorted(payload.data, key=lambda event: event.time, reverse=True)
    return {
        "events": [event.to_dict() for event in events[:25]],
        "total": len(events),
        "data_age": payload.describe_age(),
        "data_age_seconds": payload.age_seconds,
        "from_cache": payload.from_cache,
        "source": payload.source,
        # Sin red y sin cache, la instantanea fechada del paquete (`environment/donki.py`): de
        # donde salio, cuando y con que licencia. Nunca es un dato en vivo.
        "live": not payload.from_cache,
        "snapshot": payload.snapshot if isinstance(payload, SnapshotPayload) else None,
    }


@router.get("/radiation/dose")
def radiation_dose(
    settings: SettingsDep,
    start: dt.date,
    end: dt.date,
    quality_model: QualityFactorModel = QualityFactorModel.MISSION_AVERAGE,
) -> dict[str, Any]:
    """Dosis acumulada integrada de dosimetria real de la ISS.

    La respuesta declara si la dosis equivalente esta **medida** o **estimada**,
    y con que factor de calidad. Una cifra de dosis sin esa distincion no es
    interpretable.
    """
    if quality_model is QualityFactorModel.MEASURED:
        # «measured» no es un factor de calidad: es lo que se usa solo cuando la serie trae dosis
        # equivalente medida. Pedido como modelo caía con un `KeyError` y un 500 (Lógica 1).
        raise HTTPException(
            status_code=422,
            detail=(
                "«measured» no es un modelo de factor de calidad: la dosis equivalente medida se "
                "usa sola cuando la serie la trae. Elige el factor para la dosis absorbida: "
                + ", ".join(
                    model.value for model in QualityFactorModel
                    if model is not QualityFactorModel.MEASURED
                )
            ),
        )
    try:
        payload = RadLabClient(settings=settings).dose_series(start, end)
    except OfflineDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    estimate = effective_dose(payload.data, model=quality_model)
    if estimate.hours_covered <= 0:
        # Menos de dos muestras no cubren ningún intervalo: no hay dosis que integrar. Antes salía
        # «0 mSv» con su Q, como si la tripulación no hubiera recibido nada (Lógica 1). Como el
        # estado con el almacén vacío, 404 en vez de una cifra sin origen.
        raise HTTPException(
            status_code=404,
            detail=(
                f"la serie de dosis de RadLab del {start.isoformat()} al {end.isoformat()} trae "
                f"{len(payload.data)} muestra(s) utilizable(s): hacen falta dos para integrar una "
                "dosis, y no se da ninguna cifra"
            ),
        )
    return {
        "dose": estimate.to_dict(),
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "data_age": payload.describe_age(),
        "data_age_seconds": payload.age_seconds,
        # Si esta caducada lo dice el backend, con su plazo (diseno de EMMA).
        "freshness": {
            **describe_freshness(ExternalSource.DOSIMETRY, payload.age_seconds),
            "basis": i18n.loc(STALENESS_BASIS),
        },
        "from_cache": payload.from_cache,
        "source": payload.source,
        # La advertencia dice lo que se hizo con ESTA serie: con dosis equivalente medida no se
        # aplicó ningún Q medio, y decirlo sería falso (Lógica 1).
        "caveat": (
            i18n.tr(
            "NASA-STD-3001 [V1 4030] especifica el modelo NASA Q, que necesita espectro de "
            "partículas. Esta serie trae dosis equivalente medida por el instrumento y la cifra "
            "es esa, sin factor de calidad aplicado por EMMA. No es un resultado dosimétrico de "
            "grado operacional.",
            "NASA-STD-3001 [V1 4030] specifies the NASA Q model, which needs the particle "
            "spectrum. This series carries dose equivalent measured by the instrument and the "
            "figure is that one, with no quality factor applied by EMMA. It is not an "
            "operational-grade dosimetry result.",
            )
            if estimate.is_measured else
            i18n.tr(
            "NASA-STD-3001 [V1 4030] especifica el modelo NASA Q, que necesita "
            "espectro de partículas. OSDR RadLab no lo publica (ni LET ni dosis "
            "equivalente poblada), así que esta cifra aplica un factor de calidad "
            "medio medido en vuelo. No es un resultado dosimétrico de grado "
            "operacional.",
            "NASA-STD-3001 [V1 4030] specifies the NASA Q model, which needs the particle "
            "spectrum. OSDR RadLab does not publish it (neither LET nor populated dose "
            "equivalent), so this figure applies a mean quality factor measured in flight. It "
            "is not an operational-grade dosimetry result.",
            )
        ),
    }


@router.get("/observations")
def list_observations(
    store: StoreDep,
    subject: str = "crew-01",
    key: str | None = None,
    limit: int = Query(default=200, ge=1, le=5000),
    # Las `limit` más recientes HASTA ese instante: la serie de una variable en un momento pasado
    # del modo anatómico. Sin él, las más recientes de todas, y de un momento lejano no llegaba
    # ninguna.
    until: dt.datetime | None = None,
) -> dict[str, Any]:
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    results = store.query(subject, key=key, until=until, limit=limit)
    return {
        "subject": subject,
        "count": len(results),
        "observations": [item.to_fhir() for item in results],
    }


@router.get("/audit")
def audit(store: StoreDep, limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
    """Registro de auditoria y estado de integridad de la cadena."""
    # Una sola instantanea: por separado, el ancla podia cubrir asientos que la
    # verificacion no llego a ver.
    verification, anchor, entries, total = store.audit_snapshot(limit)
    return {
        "entries": entries,
        "total_entries": total,
        "merkle_root": anchor.root if anchor else None,
        # Lo que se enviaria a Tierra. La raiz sola no basta: sin el tamano que
        # cubre, borrar las ultimas entradas pasaria desapercibido. Con la cadena
        # rota no hay ancla: no hay nada fiable que anclar.
        "anchor": (
            {"tree_size": anchor.tree_size, "root": anchor.root, "algorithm": anchor.algorithm}
            if anchor
            else None
        ),
        "integrity_ok": verification.ok,
        "failed_index": verification.failed_index,
        "failure_reason": verification.reason,
    }


# --------------------------------------------------------------------------- #
# Ingesta — toda escritura queda auditada
# --------------------------------------------------------------------------- #


# La unidad mas larga que se admite declarar. Ninguna del catalogo pasa de unos pocos
# caracteres; el tope es el que tenia el esquema, para que una unidad gigante no se compare.
UNIT_MAX_LENGTH = 64


def _unit_or_422(code: CatalogUnit, unit: str | None) -> dict[str, Any]:
    """La unidad de un alta manual: la declarada si es la del catalogo, o la del catalogo.

    Va antes de construir la observacion: una unidad distinta es un 422 y no llega al ledger
    nada. La comparacion es la de la via FHIR (`ingest.fhir.require_catalog_unit`), no otra.
    Lo devuelto viaja en la respuesta, para que quien no la declaro sepa que se asumio.

    La usan el alta de una lectura y su enmienda (contra el indicador) y la lectura de cabina
    (`api/habitat.py`, contra el parametro). Una unidad vacia no es una ausente: la rechaza la
    comparacion compartida, con su motivo. El tope de longitud es de esta API, no de la
    comparacion: pasado, ni se compara.
    """
    if unit is not None:
        _unit_length_or_422(code, unit)
        try:
            require_catalog_unit(code, unit)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"unit": code.unit, "unit_assumed": unit is None}


def _unit_length_or_422(code: CatalogUnit, unit: str) -> None:
    """El tope de longitud de una unidad declarada en esta API: pasado, ni se compara ni se repite.

    Lo comparten el alta y su enmienda, la lectura de cabina y la confirmacion de una analitica
    (`api/reports.py`, decimoctava ronda): la confirmacion lo tenia en su esquema
    (`max_length=32`) y respondia con la lista de errores de Pydantic, en ingles, en vez del
    motivo en espanol que dan las demas unidades rechazadas.
    """
    if len(unit) > UNIT_MAX_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=(
                f"unidad de {len(unit)} caracteres para {code.key}: no se admite más de "
                f"{UNIT_MAX_LENGTH}; el catálogo define {code.unit!r}"
            ),
        )


def _food_item_or_422(key: str, food: str | None) -> str | None:
    """El plato normalizado que se firmará con la lectura, o el 422 con su motivo, sin asiento.

    La regla es la de `ingest/food_item.py`, la misma que aplica el registro diario; aquí no se
    exige el alimento donde es obligatorio (`require=False`): por esta ruta entra tambien lo que
    no lo conoce, que se cuenta «sin alimento declarado».
    """
    try:
        return accept_food_item(key, food, require=False)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _catalog_or_422(key: str) -> VitalCode:
    """El indicador del catalogo que nombra un alta, o 422 con el motivo.

    El motivo es el del catalogo tal cual (`args[0]`): `str()` de un `KeyError` es la `repr` de
    su mensaje, y el detalle salia con unas comillas de mas alrededor.
    """
    try:
        return get(key)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc.args[0])) from exc


def _observation_or_422(
    code: VitalCode, payload: ObservationIn, settings: Settings
) -> tuple[VitalObservation, dict[str, Any]]:
    """Lo que un alta manual comprueba antes de firmar, en este orden: unidad y modelo canonico.

    Lo comparten `POST /api/observations` y el adaptador del contrato de §5 (`api/spec5.py`):
    una lectura traducida de §5 pasa por estas mismas comprobaciones, no por una copia. La
    unidad va primero, antes de construir nada: una distinta es un 422 y al ledger no llega
    nada (`record-integrity.md` §3.14 quater). Devuelve la lectura y lo que la respuesta dice
    de la unidad (`unit`, `unit_assumed`).
    """
    unit = _unit_or_422(code, payload.unit)
    food = _food_item_or_422(payload.key, payload.food_item)

    # El modelo canonico rechaza en la frontera lo que no es una medida: NaN,
    # infinito y valores fisicamente imposibles. Sin traducirlo, ese rechazo
    # salia por la API como un 500: un tripulante que teclea 5000 de pulso
    # recibia "error del servidor" en vez de "eso no es posible". Se construye con el
    # indicador ya resuelto, no por su clave: no hay una segunda busqueda en el catalogo.
    try:
        recorded = VitalObservation(
            code=code, value=payload.value, effective=_when(payload.effective),
            subject=payload.subject, source=payload.source, context=payload.context,
            confidence=payload.confidence, observation_type=payload.observation_type,
            evidence_context=payload.evidence_context or settings.deployment_context,
            model_version=payload.model_version,
            food=food,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return recorded, unit


@router.post("/observations", status_code=201)
def record_observation(
    store: StoreDep, settings: SettingsDep, payload: ObservationIn
) -> dict[str, Any]:
    code = _catalog_or_422(payload.key)
    recorded, unit = _observation_or_422(code, payload, settings)
    entry = _recorded_or_422(lambda: store.record(recorded, identity_for(payload.source)))[0]
    # El plato tal como quedó firmado (`None` si la lectura no lo lleva): quien envía ve lo que
    # se normalizó, como en el diario.
    return {
        "ledger_index": entry.index, "content_hash": entry.content_hash, **unit,
        "food": recorded.food,
    }


@router.post("/pvt", status_code=201)
def submit_pvt(
    store: StoreDep, settings: SettingsDep, payload: PvtSubmission
) -> dict[str, Any]:
    """Puntua una sesion de PVT y registra sus observaciones."""
    try:
        result = score(payload.reaction_times_ms)
    except InsufficientTrials as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    when = _when(payload.effective)
    observations = deployed(
        to_observations(result, payload.subject, when), settings.deployment_context
    )
    entries = _recorded_or_422(lambda: store.record_many(observations, identity_for("pvt-test")))

    return {
        "result": result.to_dict(),
        "recorded": [entry.index for entry in entries],
    }


# El vinculo sensor-tripulante (`ingest/bindings.py`) en las tres rutas de ingesta de wearables.
# Lo unico que hacen aqui es ADJUNTAR un aviso a su respuesta: ninguna rechaza una lectura por
# el vinculo, y el aviso se compone con las lecturas ya registradas (decision del usuario,
# 2026-10-09: no se bloquea; decide una persona). Desde el 2026-10-13 ademas GUARDAN el
# identificador que ya recibian, dentro de cada lectura firmada (`VitalObservation.device`):
# asi el aviso se puede reconstruir despues y el estado lo ensena (`bindings.in_readings`).


def _device_or_422(device: str | None) -> str | None:
    """El identificador que llega con una ingesta, normalizado como el de una declaracion.

    Uno sin forma de identificador es un fallo de la peticion, no un desacuerdo con un vinculo:
    422 antes de registrar nada, y el detalle no repite lo recibido.
    """
    from app.ingest import bindings

    try:
        return bindings.device_key(device)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _binding_notice(
    store: ObservationStore, source: str, device: str | None, subject: str,
    observations: Sequence[VitalObservation],
) -> dict[str, Any] | None:
    """El aviso que acompana a una ingesta YA registrada, o `None` si no hay nada que decir.

    Cada lectura se juzga contra el vinculo que valia en su instante, y solo cuentan los
    vinculos firmados por la consola. Si el registro de vinculos no se puede leer con garantias,
    se dice eso: las lecturas ya estan en el ledger y su respuesta no pasa a ser un error.
    """
    from app.core.storage import TamperedRecordError
    from app.ingest import bindings

    try:
        declared = [item for item in store.sensor_bindings() if _counts(item, None)]
    except TamperedRecordError:
        return bindings.unavailable(source, device, subject, len(observations))
    return bindings.notice(
        declared, source, device, subject, [item.effective for item in observations]
    )


def _bindings_for_status(
    store: ObservationStore, until: dt.datetime | None
) -> list[dict[str, Any]] | None:
    """Los vinculos con que el estado compara sus lecturas recientes; `None` si no son de fiar.

    Los mismos que ensena `/api/sensor-bindings`: firmados por la consola y, para Tierra, los
    que ya existian en su corte. Un registro de vinculos danado no convierte el estado en un
    error: el bloque dice que no se ha comparado.
    """
    from app.api.sensor_bindings import binding_declarations
    from app.core.storage import TamperedRecordError

    try:
        return binding_declarations(store, until)
    except TamperedRecordError:
        return None


@router.post("/wearable/ble", status_code=201)
def submit_ble_frame(
    store: StoreDep, settings: SettingsDep, payload: BleFrame
) -> dict[str, Any]:
    """Ingiere una trama GATT Heart Rate Measurement de un pulsometro real."""
    try:
        frame = bytes.fromhex(payload.frame_hex)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"hexadecimal inválido: {exc}") from exc

    device = _device_or_422(payload.device)
    adapter = WearableAdapter(subject=payload.subject)
    try:
        # La HRV sale de la ventana de R-R de varias tramas (`BLE_RR_WINDOW`): una trama
        # sola trae uno o dos latidos.
        reading = adapter.read_ble_frame(
            frame, _when(payload.effective), BLE_RR_WINDOW, device
        )
        observations = deployed(reading.observations, settings.deployment_context)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # La trama se firma con el identificador que puso quien la envia, si puso alguno.
    observations = from_device(observations, device)
    entries = _recorded_or_422(
        lambda: store.record_many(observations, identity_for("wearable-ble"))
    )
    measurement = reading.measurement
    contact = {True: "detected", False: "not_detected", None: "unsupported"}
    return {
        "recorded": [entry.index for entry in entries],
        "indicators": [item.key for item in observations],
        "binding_notice": _binding_notice(
            store, "wearable-ble", device, payload.subject, observations
        ),
        # La trama tal cual se decodifico, para que la consola la ensene en vivo. La
        # energia (kJ, GATT) no se registra: no tiene codigo LOINC verificado ni propio.
        "frame": {
            "heart_rate": measurement.heart_rate,
            "rr_ms": [round(value, 1) for value in measurement.rr_intervals_ms],
            "sensor_contact": contact[measurement.sensor_contact],
            "energy_kj": measurement.energy_expended,
        },
        # Solo si esta peticion registro HRV (una por minuto como maximo).
        "hrv": (
            {"rmssd_ms": reading.hrv.rmssd_ms, "sdnn_ms": reading.hrv.sdnn_ms}
            if reading.hrv is not None
            else None
        ),
    }


# Topes de una importacion. El cuerpo se lee por trozos y se corta al pasar el tope, sin
# cargarlo entero antes. Un export completo de Apple Health puede pasar de cientos de
# megas: para mas, exportar un rango de fechas.
MAX_IMPORT_BYTES = 25 * 1024 * 1024
# Lecturas por importacion. Sin tope, 230 000 registros pequenos cabian en 22 MB, tardaban
# 28 s y retenian el cerrojo del almacen todo ese tiempo.
MAX_IMPORT_RECORDS = 50_000

# CUANTAS IMPORTACIONES A LA VEZ, QUE ES LO QUE EL TOPE DE TAMANO NO ACOTA.
#
# Parsear un export cuesta en memoria unas 4 veces su tamano —el texto decodificado, su
# copia en el stream y el buffer del parser; medido en `ingest/wearable.py`—, asi que una
# importacion en el tope ronda los 100 MB. Starlette atiende los endpoints sincronos en un
# pool de hasta 40 hilos: cuarenta importaciones simultaneas serian varios GB, y el tope
# por peticion no lo impide. Dos a la vez sobran para una tripulacion y acotan el pico a
# unos 200 MB. Se espera aqui, en la corrutina, sin ocupar un hilo del pool mientras tanto.
MAX_CONCURRENT_IMPORTS = 2
_import_slots = asyncio.Semaphore(MAX_CONCURRENT_IMPORTS)
# Cuantos motivos de descarte se devuelven. El recuento va siempre completo.
MAX_REPORTED_REJECTIONS = 20

_XML_DECLARED_ENCODING = re.compile(r"""^\s*<\?xml[^>]*?encoding\s*=\s*["']([^"']+)["']""")


class _RejectionLog(list[str]):
    """Cuenta todos los descartes y guarda solo los primeros motivos.

    Un export con millones de registros inutilizables no puede llenar la memoria con sus
    motivos. El recuento, en cambio, va siempre completo.
    """

    def __init__(self) -> None:
        super().__init__()
        self.total = 0

    def append(self, reason: str) -> None:
        self.total += 1
        if len(self) < MAX_REPORTED_REJECTIONS:
            # Y truncado, no solo contado: un motivo que arrastre un atributo entero del
            # export devolvia al cliente una respuesta del tamano de su peticion. Veinte
            # motivos de 500 KB eran 9,5 MB de JSON. Quien truncaba era cada mensaje por
            # su cuenta; esto es la red debajo.
            super().append(reason if len(reason) <= 300 else reason[:300] + "…")


async def _read_capped(request: Request, limit: int | None = None) -> bytes:
    """El cuerpo, leido por trozos y cortado al pasar `limit` (`MAX_IMPORT_BYTES` si no se da).

    Antes el tope se comprobaba con el cuerpo ya entero en memoria: 300 MB respondian 413
    despues de haberse leido, y un JSON de Google Fit de 140 MB se parseaba completo
    antes de rechazarlo.

    El tope por defecto se lee al llamar, no al definir la funcion: fijado como valor por
    defecto del parametro, cambiar `MAX_IMPORT_BYTES` en marcha no tenia efecto.
    """
    if limit is None:
        limit = MAX_IMPORT_BYTES
    too_big = HTTPException(status_code=413, detail=f"el cuerpo supera {limit} bytes")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise too_big
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise too_big
    return bytes(body)


def _capped(readings: Iterable[VitalObservation]) -> list[VitalObservation]:
    kept: list[VitalObservation] = []
    for reading in readings:
        kept.append(reading)
        if len(kept) > MAX_IMPORT_RECORDS:
            raise HTTPException(
                status_code=413, detail=f"más de {MAX_IMPORT_RECORDS} lecturas en una importación"
            )
    return kept


# Una declaración de atributo con valor literal (`"…"`/`'…'`, también tras `#FIXED`): el valor
# por defecto que el parser copia en cada elemento. Las enumeraciones van entre paréntesis.
_ATTLIST_DEFAULT = re.compile(r"<!ATTLIST\b[^>]*?[\"']")


def _xml_text(export: bytes) -> str:
    """El export como texto UTF-8, sin bytes nulos y sin declaraciones de entidad.

    Expat corta la expansion exponencial de entidades (*billion laughs*), pero admite
    hasta 100x de amplificacion lineal: 24 MB de XML con una entidad repetida llevaban el
    proceso a 2,9 GB. Un export de Apple no declara entidades, asi que no se admite
    ninguna. Y se exige UTF-8, que es lo que exporta Apple, para que la comprobacion no
    se esquive con otra codificacion; UTF-16 o UTF-7, ademas, tumbaban el parser con un
    500.
    """
    try:
        text = export.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="el export tiene que estar en UTF-8") from exc
    declared = _XML_DECLARED_ENCODING.match(text)
    if declared and declared.group(1).lower().replace("_", "-") not in {"utf-8", "utf8"}:
        raise HTTPException(
            status_code=422,
            detail=f"el export declara la codificación {declared.group(1)!r}: solo se admite UTF-8",
        )
    if "\x00" in text:
        raise HTTPException(status_code=422, detail="el export contiene bytes nulos")
    if "<!ENTITY" in text:
        raise HTTPException(status_code=422, detail="el export declara entidades: no se admiten")
    if _ATTLIST_DEFAULT.search(text):
        # Un valor por defecto se copia en cada elemento que no trae el atributo: 25 MB de
        # `<a/>` con un defecto de 8 KB amplifican como una entidad (auditoría run-2,
        # `emma:ingest:apple-health-attlist-default-amplification`). El DTD de Apple declara
        # sus atributos `#REQUIRED`/`#IMPLIED`, sin valor: ese sigue pasando.
        raise HTTPException(
            status_code=422,
            detail="el export declara atributos con valor por defecto: no se admiten",
        )
    return text


def _not_json(constant: str) -> Any:
    # Infinity y NaN no son JSON. El decodificador de Python los aceptaba, y un instante
    # infinito acababa en OverflowError.
    raise ValueError(f"{constant} no es un valor JSON")


def _json_or_422(
    body: bytes, object_pairs_hook: Callable[[list[tuple[str, Any]]], Any] | None = None
) -> Any:
    """El cuerpo de una importacion como JSON, o 422 con el motivo.

    Lo comparten Google Fit y el adaptador del contrato de §5 (`api/spec5.py`): un
    endurecimiento del parseo vale para las dos importaciones, no para la que lo recibio.
    """
    try:
        return json.loads(body, parse_constant=_not_json, object_pairs_hook=object_pairs_hook)
    except (ValueError, RecursionError) as exc:
        raise HTTPException(status_code=422, detail=f"JSON no válido: {exc}") from exc


@router.post(
    "/import/apple-health",
    status_code=201,
    # Lee el cuerpo tal cual, sin mirar su tipo (`_read_capped`): una petición simple con
    # `text/plain` lo ejecutaría. La cabecera de la consola, como en los POST sin cuerpo.
    **console_post(
        requestBody={
            "required": True,
            "content": {"application/xml": {"schema": {"type": "string"}}},
        }
    ),
)
async def import_apple_health(
    request: Request,
    store: StoreDep,
    settings: SettingsDep,
    subject: Annotated[str, Query(min_length=1)] = "crew-01",
    device: str | None = None,
) -> dict[str, Any]:
    """Importa un export de Apple Health (Salud > exportar datos > `export.xml`).

    El XML llega de fuera, asi que se parsea con cuidado: nada de entidades declaradas
    (`_xml_text`), y ElementTree no resuelve entidades externas, asi que un XML no puede
    leer ficheros del sistema. Cada registro trae su unidad, que se convierte a la del
    catalogo o se descarta, y una fecha que tiene que ser creible. Hay pruebas de todo.
    """
    device = _device_or_422(device)
    export = await _read_capped(request)
    async with _import_slots:
        return await run_in_threadpool(
            _import_apple_health, store, export, subject, settings.deployment_context, device
        )


def _import_apple_health(
    store: ObservationStore, export: bytes, subject: str, where: EvidenceContext,
    device: str | None = None,
) -> dict[str, Any]:
    text = _xml_text(export)
    rejected = _RejectionLog()
    adapter = WearableAdapter(subject=subject, source="apple-health")
    try:
        observations = _capped(adapter.from_apple_health_export(text, rejected))
    except (ET.ParseError, ValueError, LookupError) as exc:
        raise HTTPException(status_code=422, detail=f"XML no válido: {exc}") from exc
    return _imported(
        store, deployed(observations, where), rejected, "apple-health", subject, device
    )


@router.post(
    "/import/google-fit",
    status_code=201,
    # Como la de Apple Health: cuerpo leído tal cual, cabecera de la consola.
    **console_post(
        requestBody={
            "required": True,
            "content": {"application/json": {"schema": {"type": "object"}}},
        }
    ),
)
async def import_google_fit(
    request: Request,
    store: StoreDep,
    settings: SettingsDep,
    subject: Annotated[str, Query(min_length=1)] = "crew-01",
    device: str | None = None,
) -> dict[str, Any]:
    """Importa la respuesta de `users.dataSources.datasets.get` de Google Fit."""
    device = _device_or_422(device)
    body = await _read_capped(request)
    async with _import_slots:
        return await run_in_threadpool(
            _import_google_fit, store, body, subject, settings.deployment_context, device
        )


def _import_google_fit(
    store: ObservationStore, body: bytes, subject: str, where: EvidenceContext,
    device: str | None = None,
) -> dict[str, Any]:
    dataset = _json_or_422(body)
    points = dataset.get("point") if isinstance(dataset, dict) else None
    if not isinstance(points, list):
        raise HTTPException(status_code=422, detail="se esperaba un objeto con una lista 'point'")
    rejected = _RejectionLog()
    adapter = WearableAdapter(subject=subject, source="google-fit")
    observations = _capped(adapter.from_google_fit(dataset, rejected))
    return _imported(
        store, deployed(observations, where), rejected, "google-fit", subject, device
    )


def _imported(
    store: ObservationStore,
    observations: list[VitalObservation],
    rejected: _RejectionLog,
    source: str,
    subject: str,
    device: str | None = None,
) -> dict[str, Any]:
    """Registra una importacion entera en un solo lote auditado, y dice lo descartado.

    Una constante vital que desaparece en silencio es el peor fallo posible aqui: cada
    lectura que no se pudo importar vuelve contada, con su motivo.
    """
    if not observations:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "no hay ninguna lectura importable",
                "rejected": rejected.total,
                "rejections": list(rejected),
            },
        )
    # La importacion se firma con el identificador que puso quien la envia, si puso alguno.
    observations = from_device(observations, device)
    entries = _recorded_or_422(lambda: store.record_many(observations, identity_for(source)))
    return {
        "imported": len(entries),
        "by_indicator": dict(Counter(item.key for item in observations)),
        "rejected": rejected.total,
        "rejections": list(rejected),
        "binding_notice": _binding_notice(store, source, device, subject, observations),
    }


@router.post(
    "/simulate",
    status_code=201,
    # Solo parámetros de consulta: una petición simple de otra página lo dispararía
    # (`api/console_header.py`).
    **console_post(),
)
def load_simulation(
    store: StoreDep,
    settings: SettingsDep,
    scenario: Scenario = Scenario.NOMINAL,
    days: int = Query(default=40, ge=1, le=365),
    # 4 MUESTRAS AL DIA NO DAN PARA UNA LINEA BASE PERSONAL.
    #
    # Con 4/dia, la ventana movil de 14 dias reune 56 lecturas, por debajo de las
    # 100 que exige `MIN_SAMPLES`, y estratificadas por contexto muchas menos.
    # Resultado medido sobre 40 dias: **0 % de uso de base personal**, todo por el
    # camino poblacional —que desde el diseno actual solo alerta por limite de
    # peligro absoluto— y **el escenario de arritmia sin detectar**.
    #
    # Es decir: la demo por defecto ensenaba la rama mas debil del motor y daba
    # "nominal" sobre un tripulante con arritmia. Medido por frecuencia:
    #
    #     muestras/dia    base personal    arritmia
    #          4              0,0 %        NO detectada
    #          8              0,0 %        detectada
    #         12             45,0 %        NO detectada
    #         24             55,3 %        detectada
    #         48             80,0 %        detectada
    #
    # 24/dia es ademas lo realista: un wearable no mide cuatro veces al dia.
    samples_per_day: int = Query(default=24, ge=1, le=96),
    seed: int = 20261114,
    # CAMBIAR DE ESCENARIO SIN CERRAR LA APLICACION.
    #
    # El almacen es de solo anadir y no hay endpoint que lo vacie: un registro
    # clinico no se borra. Cargar un segundo escenario encima mezclaba las dos
    # series. Con `replace`, se construye un almacen nuevo con el escenario pedido
    # y sustituye al anterior: lo mismo que cerrar y abrir la aplicacion, que ya
    # tiraba el almacen en memoria.
    #
    # Solo si **todo** lo que hay es simulado. Una sola lectura de otra fuente
    # —un wearable, una entrada manual— es un registro real, y descartarlo seria
    # borrarlo: 409.
    replace: bool = False,
    # TRIPULACION, NO UN TRIPULANTE.
    #
    # La correlacion con el habitat compartido (especificacion §7) solo tiene sentido con
    # varios tripulantes. Sin indicarlo: 4 en un escenario ambiental (le pasa a todos) y 1
    # en el resto, como siempre. Con varios en un escenario no ambiental, solo crew-01 lo
    # sufre y los demas quedan nominales: el contraste que distingue lo individual.
    crew_size: int | None = Query(default=None, ge=1, le=6),
    # Cuantos modulos de la lista declarada llevan telemetria. Por defecto uno, como siempre;
    # la excursion ocurre solo en el primero (supuesto de diseno, `habitat_simulator.py`).
    habitat_modules: int = Query(default=1, ge=1, le=len(HABITAT_MODULES)),
    # CON CICLO MENSTRUAL (lote «ciclo», B3). Apagado por defecto: el nominal sigue siendo el
    # de siempre. Encendido, crew-01 lleva el ciclo del simulador (`MenstrualCycle`, empezando el
    # primer dia de la regla) para ver en la consola el ajuste por fase. El simulador no firma
    # inicios de regla ni el sexo: se declaran aparte, como los declararia la tripulante.
    cycle: bool = False,
    # TAC DE EJEMPLO PRECARGADO (decisión del usuario, 2026-11-15: el hígado «tiene que salir
    # precargado» en «Distancia y nodos»). Una clave de `GET /api/volumes/samples`: se registra
    # para crew-01, con su segmentación, dentro del mismo almacén que el escenario; así un cambio
    # de escenario no lo pierde. Sin ella, como siempre: ningún volumen.
    volume_sample: str | None = Query(default=None, min_length=1),
) -> dict[str, Any]:
    """Carga una serie simulada en el almacen, o lo sustituye por una nueva.

    Los datos del simulador no tienen privilegios: entran por la misma puerta
    auditada y quedan firmados con una identidad que los declara simulados. El habitat
    se simula siempre (nominal, o con el CO2 fuera de limite en su escenario).
    """
    size = crew_size or (4 if scenario in ENVIRONMENTAL_SCENARIOS else 1)
    simulators = [
        PhysiologicalSimulator(
            scenario=(
                scenario if index == 0 or scenario in ENVIRONMENTAL_SCENARIOS
                else Scenario.NOMINAL
            ),
            seed=seed + index,
            mission_start=settings.mission_start,
            crew=CrewMember(
                subject_id=f"crew-{index + 1:02d}",
                cycle=MenstrualCycle() if cycle and index == 0 else None,
            ),
        )
        for index in range(size)
    ]
    simulator = simulators[0]
    cabin = HabitatSimulator(
        co2_excursion=scenario is Scenario.CO2_FATIGUE, seed=seed,
        mission_start=settings.mission_start,
        extra_modules=[
            key for key in HABITAT_MODULES if key != DEFAULT_HABITAT_MODULE
        ][: habitat_modules - 1],
    )

    def seed_all(target: ObservationStore) -> tuple[int, int]:
        identity = identity_for(_SIMULATOR_SOURCE)
        count = sum(
            seed_from_simulator(
                target, item.generate(days=days, samples_per_day=samples_per_day), identity
            )
            for item in simulators
        )
        cabin_count = len(target.record_habitat(list(cabin.generate(days=days)), identity))
        if volume_sample is not None:
            # Importado aquí: `api/volumes.py` importa este módulo.
            from app.api.volumes import record_sample

            record_sample(target, volume_sample, simulator.crew.subject_id)
        return count, cabin_count

    if volume_sample is not None and volume_sample not in {s.key for s in sample_catalog()}:
        # Antes de sembrar nada: una clave mala no deja el almacén a medias.
        raise HTTPException(status_code=404, detail=f"no hay ejemplo {volume_sample!r}")

    described = {
        **simulator.describe(),
        "crew": [item.crew.subject_id for item in simulators],
        "habitat": cabin.describe(),
    }
    if not replace:
        count, cabin_count = seed_all(store)
        return {
            "recorded": count, "habitat_recorded": cabin_count,
            "simulation": described, "replaced": False,
        }

    _refuse_if_real(store)
    # Atomico: el almacen nuevo se siembra aparte y solo al final sustituye al
    # anterior. Si algo falla por el camino, el anterior sigue intacto.
    size_before = len(store.ledger)
    fresh = new_store()
    count, cabin_count = seed_all(fresh)
    with _store_lock:
        # Sembrar lleva segundos. Si mientras tanto entro algo en el almacen viejo
        # —una lectura real, un reconocimiento—, sustituirlo lo perderia.
        if len(store.ledger) != size_before:
            raise HTTPException(
                status_code=409,
                detail="llegaron registros nuevos durante el cambio de escenario: "
                "no se sustituye el almacén. Vuelva a intentarlo",
            )
        _refuse_if_real(store)
        global _store
        _store = fresh
    return {
        "recorded": count,
        "habitat_recorded": cabin_count,
        "simulation": described,
        "replaced": True,
        "discarded_entries": size_before,
    }


def _refuse_if_real(store: ObservationStore) -> None:
    real = sorted(
        signer
        for signer in store.reading_signers()
        if signer.split(":", 1)[0] != _SIMULATOR_SOURCE
    )
    if real:
        raise HTTPException(
            status_code=409,
            detail=(
                "el almacén contiene lecturas reales (firmadas por "
                f"{', '.join(real)}): sustituirlo las borraría. Solo se cambia de "
                "escenario cuando todo lo registrado es simulado"
            ),
        )


def _require_alert(
    settings: Settings,
    store: ObservationStore,
    subject: str,
    domain: str,
    level: str,
    reference_time: dt.datetime,
) -> None:
    """409 si en el estado de `reference_time` no hay esa alerta.

    Reconocer o suprimir una alerta que no existe dejaba un asiento que silenciaba de
    antemano la que llegara despues con el mismo dominio y nivel.
    """
    try:
        status = crew_status(
            settings, store, subject=subject, epoch=None, cumulative_dose_msv=None,
            until=reference_time,
        )
    except HTTPException as exc:
        raise HTTPException(
            status_code=409,
            detail="no hay estado en ese instante: no hay alerta sobre la que actuar",
        ) from exc
    if not any(
        alert["domain"] == domain and alert["level"] == level for alert in status["alerts"]
    ):
        raise HTTPException(
            status_code=409,
            detail=f"no hay alerta {domain}:{level} en el estado de {reference_time.isoformat()}",
        )


@router.post("/alerts/acknowledge", status_code=201)
def acknowledge_alert(
    store: StoreDep, settings: SettingsDep, payload: AcknowledgementIn
) -> dict[str, Any]:
    """Reconoce una alerta. Detiene su parpadeo; no la oculta ni la resuelve.

    El reconocimiento queda en el ledger, firmado y con su autor declarado: una
    alerta que se deja de anunciar tiene que tener detras quien lo decidio. Y con la
    version de las reglas vigente al firmar (`record-integrity.md` §3.26): la pone
    esta ruta, no el cliente (`AcknowledgementIn` rechaza campos que sobran).
    """
    _require_alert(
        settings, store, payload.subject, str(payload.domain), str(payload.level),
        payload.reference_time,
    )
    entry = _recorded_or_422(
        lambda: store.acknowledge(
            payload.subject,
            str(payload.domain),
            str(payload.level),
            payload.reference_time,
            payload.acknowledged_by,
            identity_for(CONSOLE_IDENTITY),
            rules_version=rules_version(),
        )
    )[0]
    return {"ledger_index": entry.index, "content_hash": entry.content_hash}


class ResolutionIn(BaseModel):
    """"En arreglo" o "resuelto" de una alerta que se ve en el estado de `reference_time`."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(default="crew-01", min_length=1, max_length=64)
    domain: Domain
    level: RiskLevel
    reference_time: dt.datetime
    state: Literal["en_arreglo", "resuelto"]
    note: str = Field(default="", max_length=300)
    declared_by: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
    ]


@router.post("/alerts/resolution", status_code=201)
def resolve_alert(
    store: StoreDep, settings: SettingsDep, payload: ResolutionIn
) -> dict[str, Any]:
    """Quién se ocupa de una alerta y cuándo la da por resuelta (estados de Polaris `salud.py`).

    No toca el cálculo: una alerta "resuelta" cuyos datos siguen fuera de rango sigue en la
    lista. Exige que la alerta exista en ese estado, como reconocer.
    """
    _require_alert(
        settings, store, payload.subject, str(payload.domain), str(payload.level),
        payload.reference_time,
    )
    entry = _recorded_or_422(
        lambda: store.record_alert_resolution(
            payload.subject, str(payload.domain), str(payload.level), payload.reference_time,
            payload.state, payload.note, payload.declared_by, identity_for(CONSOLE_IDENTITY),
            rules_version=rules_version(),
        )
    )[0]
    return {"ledger_index": entry.index}


class DismissalIn(BaseModel):
    """«Descartada» para una alerta que se ve en el estado de `reference_time`.

    El motivo es de un vocabulario cerrado (`DISMISSAL_REASONS`): un texto libre no se puede
    contar ni revisar después. «Otro» exige decir cuál en la nota.
    """

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(default="crew-01", min_length=1, max_length=64)
    domain: Domain
    level: RiskLevel
    reference_time: dt.datetime
    # El vocabulario lo impone el almacen (`dismissal_problem`): fuera de el, un 422.
    reason: str = Field(min_length=1, max_length=64)
    note: str = Field(default="", max_length=300)
    declared_by: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
    ]

    @field_validator("reference_time")
    @classmethod
    def _has_timezone(cls, value: dt.datetime) -> dt.datetime:
        if value.tzinfo is None:
            raise ValueError("debe llevar zona horaria")
        return value


# Lo que el descarte es y lo que no (lo enseña la consola junto al formulario, tal cual).
DISMISSAL_BASIS = (
    "Descartar deja dicho, firmado y con su motivo, que esta alerta concreta no se considera "
    "real o ya tiene explicación. No cambia ningún cálculo ni el anuncio: la alerta sigue en la "
    "lista, marcada como descartada. Cubre lo mismo que un reconocimiento: ese dominio a ese "
    "nivel, mientras las lecturas que la motivaron sigan en la ventana de cálculo (dos días); "
    "un cambio de nivel, o lo que alerte después de esa ventana, llega sin descartar. Declarar "
    "después «en arreglo» o «resuelta» deja el descarte atrás, sin borrarlo."
)
i18n.en(
    DISMISSAL_BASIS,
    "Dismissing leaves it stated, signed and with its reason, that this particular alert is not "
    "considered real or already has an explanation. It changes no calculation and not the "
    "annunciation: the alert stays in the list, marked as dismissed. It covers the same as an "
    "acknowledgement: that domain at that level, while the readings that prompted it remain in "
    "the calculation window (two days); a change of level, or whatever alerts after that window, "
    "arrives undismissed. Declaring “being fixed” or “resolved” afterwards leaves the dismissal "
    "behind, without erasing it.",
)


@router.get("/alerts/dismissal-reasons")
def dismissal_reasons() -> dict[str, Any]:
    """Los motivos con que se puede descartar una alerta, con su palabra (la interfaz no la
    redacta) y si exigen nota."""
    return {
        "reasons": [
            {
                "code": code, "display": i18n.loc(display),
                "note_required": code in DISMISSAL_NOTE_REQUIRED,
            }
            for code, display in DISMISSAL_REASONS.items()
        ],
        "basis": i18n.loc(DISMISSAL_BASIS),
    }


@router.post("/alerts/dismissal", status_code=201)
def dismiss_alert(
    store: StoreDep, settings: SettingsDep, payload: DismissalIn
) -> dict[str, Any]:
    """Una persona descarta una alerta concreta, con motivo, firmado en el ledger.

    No toca el cálculo ni el anuncio: la alerta sigue en la lista marcada como descartada, sus
    niveles y su riesgo son los mismos, y no deja de parpadear si nadie la ha reconocido. Exige que
    la alerta exista en ese estado, como reconocer. La nota que exige «otro» la impone el almacén
    (`record_alert_dismissal`): un 422.
    """
    _require_alert(
        settings, store, payload.subject, str(payload.domain), str(payload.level),
        payload.reference_time,
    )
    entry = _recorded_or_422(
        lambda: store.record_alert_dismissal(
            payload.subject, str(payload.domain), str(payload.level), payload.reference_time,
            payload.reason, payload.note, payload.declared_by, identity_for(CONSOLE_IDENTITY),
            rules_version=rules_version(),
        )
    )[0]
    return {"ledger_index": entry.index, "content_hash": entry.content_hash}


def _record_annunciation(
    store: ObservationStore,
    payload: _AnnunciationBase,
    action: str,
    level: RiskLevel | None,
    duration: dt.timedelta | None,
) -> dict[str, Any]:
    until = payload.reference_time + duration if duration is not None else None
    entry = _recorded_or_422(
        lambda: store.set_annunciation(
            payload.subject,
            action,
            str(payload.domain),
            str(level) if level is not None else None,
            payload.reference_time,
            until,
            payload.reason,
            payload.requested_by,
            identity_for(CONSOLE_IDENTITY),
        )
    )[0]
    return {
        "ledger_index": entry.index,
        "content_hash": entry.content_hash,
        "until": until.isoformat() if until is not None else None,
    }


@router.post("/alerts/suppress", status_code=201)
def suppress_alert(
    store: StoreDep, settings: SettingsDep, payload: SuppressionIn
) -> dict[str, Any]:
    """Suprime el anuncio de una alerta concreta durante un tiempo limitado.

    Sigue activa y visible, con su estado de anuncio; deja de parpadear y de contar
    como pendiente. Una critica, como mucho una hora.
    """
    duration = dt.timedelta(minutes=payload.duration_minutes)
    if payload.level is RiskLevel.CRITICAL and duration > MAX_CRITICAL_SUPPRESSION:
        raise HTTPException(
            status_code=422,
            detail="una alerta crítica solo se puede suprimir durante una hora como mucho",
        )
    _require_alert(
        settings, store, payload.subject, str(payload.domain), str(payload.level),
        payload.reference_time,
    )
    return _record_annunciation(store, payload, "suppress", payload.level, duration)


@router.post("/alerts/inhibit", status_code=201)
def inhibit_alerts(store: StoreDep, payload: InhibitionIn) -> dict[str, Any]:
    """Inhibe el anuncio de las alertas de un dominio hasta un nivel.

    Reduce la vigilancia, y `monitoring` lo declara mientras dure. Nunca en critico.
    """
    duration = dt.timedelta(hours=payload.duration_hours)
    return _record_annunciation(store, payload, "inhibit", payload.level, duration)


@router.post("/alerts/enable", status_code=201)
def enable_alerts(store: StoreDep, payload: EnableIn) -> dict[str, Any]:
    """Vuelve a anunciar las alertas del dominio: anula supresion e inhibicion."""
    return _record_annunciation(store, payload, "enable", None, None)


@router.post("/audit/redact/{ledger_index}")
def redact(store: StoreDep, ledger_index: int, payload: RedactionIn) -> dict[str, Any]:
    """Rectificacion: suprime el dato clinico y deja una lapida firmada.

    El contenido desaparece; la constancia de que existio, de por que se quito y de
    quien lo pidio, no. Redactar una lapida, o la misma entrada dos veces, es un 409.
    """
    if ledger_index < 0 or ledger_index >= len(store.ledger):
        raise HTTPException(status_code=404, detail=f"índice {ledger_index} inexistente")

    try:
        redaction = store.redact(
            ledger_index, audit_identity(), payload.reason, payload.requested_by
        )
    except UntrustedSigner as exc:
        # El almacen no se abrio con esta autoridad: nadie puede autorizar la
        # supresion. No es un error de quien la pide.
        raise HTTPException(status_code=503, detail=f"redacción no disponible: {exc}") from exc
    except IndexError as exc:  # el indice existia al comprobarlo, fuera del cerrojo
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    verification, anchor, _trail, _total = store.audit_snapshot(limit=1)
    return {
        "redacted_index": redaction.target.index,
        "redaction_entry_index": redaction.tombstone.index,
        # Lo que se redactó con él (las fases de contraste declaradas y las segmentaciones de un
        # TAC, en el orden de la cadena), cada una con su lápida.
        "dependent_redactions": [
            {"redacted_index": item.target.index, "redaction_entry_index": item.tombstone.index}
            for item in redaction.dependents
        ],
        "chain_still_valid": verification.ok,
        "merkle_root": anchor.root if anchor else None,
    }


@router.post("/audit/amend/{ledger_index}")
def amend(
    store: StoreDep, settings: SettingsDep, ledger_index: int, payload: AmendmentIn
) -> dict[str, Any]:
    """Correccion anexada: la version buena se registra y la anterior se conserva.

    A partir de aqui el motor analiza la version corregida —y solo esa—, mientras la
    anterior sigue firmada y legible en `/api/audit`. Es lo que pide 45 CFR 164.526 y
    lo que la redaccion no puede dar, porque borra.

    Enmendar dos veces la misma entrada, o una ya redactada, o hacerlo sobre una cadena
    que no verifica, es un 409. Una correccion de otro indicador que la lectura corregida, o
    de un asiento que no es una lectura, es un 422 (`ObservationStore.amend`). El tripulante
    si puede cambiar: reasignar una lectura mal atribuida es el control del peligro H3.
    """
    if ledger_index < 0 or ledger_index >= len(store.ledger):
        raise HTTPException(status_code=404, detail=f"índice {ledger_index} inexistente")

    correction = payload.correction
    code = _catalog_or_422(correction.key)
    unit = _unit_or_422(code, correction.unit)
    # El plato, si la correccion lo trae, con la regla de siempre. Sin el, `ObservationStore.amend`
    # conserva el de la lectura que corrige (§3.14 quinquies): la correccion es del valor, no del
    # plato. Con el, se corrige tambien el plato: antes un plato mal escrito no se podia enmendar.
    food = _food_item_or_422(correction.key, correction.food_item)

    try:
        corrected = observation(
            correction.key, correction.value, _when(correction.effective), correction.subject,
            correction.source, correction.context, correction.confidence,
            # Lo que la correccion declara de su procedencia. Antes se perdia: una correccion
            # inferida se firmaba como medida y sin su modelo. Sin entorno declarado vale el del
            # despliegue, como en el alta: deducirlo de la fuente pasaba a Tierra una lectura de
            # la ISS al corregirle una errata.
            observation_type=correction.observation_type,
            evidence_context=correction.evidence_context or settings.deployment_context,
            model_version=correction.model_version,
            food=food,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Lo que el ledger no puede registrar tal cual —un sustituto UTF-16 suelto en el
    # tripulante o en la fuente— es un 422 del dato, no un 409 de conflicto. Se
    # comprueba antes para que el `except ValueError` de abajo signifique una sola cosa.
    try:
        canonical_bytes([corrected.subject, corrected.source, corrected.key])
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        amendment = store.amend(
            ledger_index, corrected, identity_for(correction.source), payload.reason
        )
    except IndexError as exc:  # el indice existia al comprobarlo, fuera del cerrojo
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AmendmentMismatch as exc:
        # Una correccion de otro indicador es un dato malo de quien llama, no un conflicto
        # de estado: 422, como la unidad equivocada.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    verification, anchor, _trail, _total = store.audit_snapshot(limit=1)
    return {
        "amended_index": ledger_index,
        "amendment_entry_index": amendment.entry.index,
        "content_hash": amendment.entry.content_hash,
        "chain_still_valid": verification.ok,
        "merkle_root": anchor.root if anchor else None,
        **unit,
    }


# --------------------------------------------------------------------------- #
# Estado
# --------------------------------------------------------------------------- #


# Antiguedad de un dato externo: el texto para leerlo y los segundos para decidir.
_Age = tuple[str, int]


def _age(payload: CachedPayload) -> _Age:
    return payload.describe_age(), payload.age_seconds


def _fetch_comms(
    settings: Settings, epoch: dt.date | None, target: str | None
) -> tuple[CommsWindow | None, _Age | None]:
    """Efemerides, degradando en silencio si no hay enlace.

    Se capturan los fallos concretos de la consulta —sin red, red caida,
    respuesta incoherente— y no `Exception` a secas, que ocultaria errores de
    programacion detras de una degradacion silenciosa.

    `target` es el del perfil vigente (`_ephemeris_target`); sin objetivo no se consulta nada
    (ni Horizons ni la cache) y el riesgo no se escala con ningun tiempo de luz.
    """
    if target is None:
        return None, None
    try:
        payload = EphemerisClient(settings=settings).comms_window(epoch or utc_today(), target)
    except (OfflineDataUnavailable, OSError, ValueError):
        return None, None
    return payload.data, _age(payload)


def _fetch_solar_events(settings: Settings) -> tuple[list[SolarEvent], _Age | None]:
    """Eventos solares con amenaza activa: solo los de los ultimos dias."""
    end = utc_today()  # DONKI fecha en UTC, como las efemérides
    try:
        payload = DonkiClient(settings=settings).events(
            EventType.SEP, end - dt.timedelta(days=365), end
        )
    except (OfflineDataUnavailable, OSError, ValueError):
        return [], None

    cutoff = dt.datetime.now(dt.UTC) - SOLAR_EVENT_RELEVANCE
    active = [event for event in payload.data if event.time >= cutoff]
    return active, _age(payload)


def latest_solar_record(settings: Settings) -> SolarEvent | None:
    """El SEP mas reciente que hay de DONKI, vigente o no, o None sin datos (2026-11-04).

    Lo ensena la radiacion del habitat cuando no hay evento vigente: sin red, el de la
    instantanea del paquete con su fecha real. La misma consulta que `_fetch_solar_events`, pero
    sin salir a la red (cache o instantanea): si esa trajo el dato, ya esta en la cache, y si la
    red fallo, no se espera otra vez. No decide nada.
    """
    end = utc_today()  # DONKI fecha en UTC, como las efemérides
    try:
        payload = DonkiClient(settings=settings.model_copy(update={"offline": True})).events(
            EventType.SEP, end - dt.timedelta(days=365), end
        )
    except (OfflineDataUnavailable, OSError, ValueError):
        return None
    events: list[SolarEvent] = payload.data
    return max(events, key=lambda event: event.time) if events else None


@dataclass(frozen=True)
class _Assessment:
    """Lo que el estado de un tripulante necesita del analisis, sin el resto de `/status`."""

    status: CrewHealthStatus
    observations: list[VitalObservation]
    latest: dt.datetime
    ignored: dict[str, int]
    deviations: list[Deviation]
    trends: dict[str, Trend]
    cumulative_dose_msv: float | None
    dose_source: str | None
    comms_window: CommsWindow | None
    comms_age: _Age | None
    solar_age: _Age | None
    solar_events: list[SolarEvent]
    # Lo que devolvio `store.query` antes de apartar nada (descriptivos, fechas no analizables):
    # la cronica lo lee para el posvuelo, que cuenta tambien lo que el estado no analiza. Asi
    # no repite la consulta, que vuelve a hashear cada lectura que entrega. `None` si quien
    # construye la evaluacion no la tiene: entonces quien la necesite consulta el almacen.
    stored: list[VitalObservation] | None = None
    # Las lecturas no descriptivas que el analisis aparto por su tipo (`ANALYSED_TYPES`): se
    # cuentan en el estado y el detalle de cada alerta dice cuantas habia en su ventana.
    set_aside: list[VitalObservation] = field(default_factory=list)
    # Las dosis acumuladas que cuentan para el limite de carrera (`DOSE_TYPES`), por instante: la
    # historia recalculada (`api/alert_history.py`) las lee de aqui, no de `observations`.
    doses: list[VitalObservation] = field(default_factory=list)
    # El entorno de la mision con que se pidio el tiempo de luz (`_profile_and_target`): el estado
    # sirve este mismo, no uno releido. `None` si quien construye la evaluacion no lo tiene.
    mission_profile: dict[str, Any] | None = None
    # La puerta del ajuste por fase del ciclo (`api/cycle_phase.py`): el desplazamiento con que
    # se calcularon las desviaciones y las tendencias, y lo que se enseña. `None` si quien
    # construye la evaluacion no la tiene: entonces no hubo ajuste.
    cycle: CycleGate | None = None
    # La tendencia de lo anterior a un instante, calculada una vez por evaluacion
    # (`trends_before`). Vive con esta evaluacion y sale de sus lecturas, que no cambian: no es
    # una cache entre peticiones y no puede servir un estado viejo.
    _trends_before: dict[dt.datetime, dict[str, Trend]] = field(
        default_factory=dict, compare=False, repr=False
    )

    def trends_before(self, end: dt.datetime) -> dict[str, Trend]:
        """`trends_by_indicator` de las lecturas anteriores a `end`, o nada si no hay ninguna.

        La piden el nivel de una ventana antes (`_previous_levels`) y cada paso de la historia
        recalculada (`api/alert_history.py`); en la cronica coinciden en el paso anterior al
        actual, y ajustar dos veces las mismas tendencias era repetir el motor.
        """
        if end not in self._trends_before:
            before = [obs for obs in self.observations if obs.effective < end]
            self._trends_before[end] = (
                trends_by_indicator(before, phase_offset=self.phase_offset) if before else {}
            )
        return self._trends_before[end]

    @property
    def phase_offset(self) -> PhaseOffset | None:
        """El desplazamiento por fase con que se evaluo, para repetir el motor con las mismas
        reglas (la tendencia de antes, la sombra del episodio cerrado)."""
        return self.cycle.offset if self.cycle is not None else None


def _assess(
    settings: Settings,
    store: ObservationStore,
    subject: str,
    epoch: dt.date | None,
    cumulative_dose_msv: float | None,
    until: dt.datetime | None,
) -> _Assessment:
    """Lecturas → linea base → tendencia → riesgo. Compartido por `/status` y `/crew`.

    `/crew` calcula esto para cada tripulante; si repitiera el `/status` entero, verificaria
    la cadena completa una vez por tripulante (23 s con cuatro).
    """
    if until is not None and until.tzinfo is None:
        # Misma regla que la ingesta: un instante sin zona horaria es ambiguo.
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    stored: list[VitalObservation] = store.query(subject, until=until)
    observations = stored
    if not observations:
        raise HTTPException(
            status_code=404,
            detail=(
                f"no hay observaciones de {subject!r}. Cargue datos con "
                f"POST /api/simulate (cabecera X-EMMA-Console: 1) o ingiera lecturas reales."
            ),
        )

    # LOS INDICADORES DESCRIPTIVOS NO ENTRAN EN EL ESTADO (decisiones del usuario del 2026-10-15
    # y, para la vitamina D, del 2026-10-22).
    #
    # Se firman en el ledger y se ensenan en su panel, pero el estado no los lee: se apartan
    # aqui, antes de fijar el "ahora" de los datos, para que ni una lectura suya ni su hora
    # muevan una linea base, una tendencia, un nivel o una alerta (`codes.DESCRIPTIVE_ONLY`).
    analysed = [item for item in observations if item.key not in DESCRIPTIVE_ONLY]
    if not analysed:
        raise HTTPException(
            status_code=404,
            detail=(
                f"las lecturas de {subject!r} son todas de indicadores descriptivos, que el "
                f"estado no analiza (se enseñan en GET /api/indicators/descriptive). Cargue "
                f"datos con POST /api/simulate (cabecera X-EMMA-Console: 1) o ingiera lecturas "
                f"reales."
            ),
        )

    # LO INFERIDO Y LO PREDICHO NO DECIDEN (`ANALYSED_TYPES`, decision del usuario del
    # 2026-10-26). Se apartan aqui por lo mismo que los descriptivos: antes de fijar el "ahora",
    # para que una proyeccion fechada en el futuro no mueva la ventana actual.
    set_aside = [item for item in analysed if not is_analysed_type(item)]
    # Con `decides`, la regla de `state_reference`: el motivo del 404 sale de la misma regla
    # que fija el «ahora» de abajo, no de una copia.
    measured = [item for item in analysed if decides(item)]
    if not measured:
        raise HTTPException(
            status_code=404,
            detail=(
                f"las lecturas de {subject!r} son todas inferidas o predichas: se guardan en el "
                f"registro, pero la línea base, la tendencia y el riesgo solo leen lecturas "
                f"medidas. Cargue datos con POST /api/simulate (cabecera X-EMMA-Console: 1) o "
                f"ingiera lecturas medidas."
            ),
        )

    # El «ahora» con la regla compartida (`state_reference`), sobre todo lo leído: la misma que
    # usan la radiación del hábitat, las rutinas, el diario, las sesiones PVT y la comparación
    # entre tripulantes. Lo de arriba solo sirve para decir por qué no hay estado y qué se apartó.
    observations, latest, ignored = state_reference(stored)
    if not observations:
        raise HTTPException(
            status_code=422,
            detail=f"ninguna lectura de {subject!r} tiene una fecha analizable",
        )

    # LA FASE DEL CICLO, SOLO CON LA PUERTA ABIERTA (lote «ciclo», B3; `api/cycle_phase.py`).
    # Sexo declarado femenino, estado reproductivo «ciclo regular» e inicios de regla
    # suficientes; si falta algo, `offset` es `None` y el motor es el de siempre. El motor
    # recibe el desplazamiento, nunca el sexo.
    cycle = cycle_gate(store, subject, until, stored, observations, latest, is_analysed_type)

    engine = BaselineEngine()
    deviations = engine.evaluate_rolling(observations, phase_offset=cycle.offset)

    # Seleccionar por tiempo, no por `(clave, valor)`. Emparejar por valor daba
    # por actual cualquier desviacion antigua que repitiera cifra, y las cifras
    # se repiten mucho: 960 lecturas de pulso toman 36 valores distintos.
    cutoff = latest - CURRENT_WINDOW
    current = [dev for dev in deviations if dev.effective >= cutoff]
    trends = trends_by_indicator(observations, phase_offset=cycle.offset)

    # LA DOSIS REGISTRADA CUENTA.
    #
    # Solo se leia del parametro: un dosimetro que registraba 600 mSv en el ledger no
    # llegaba al limite de carrera. Si nadie la facilita por parametro, vale la ultima
    # dosis acumulada registrada; y se dice de donde sale.
    #
    # Medida o inferida (`DOSE_TYPES`), con las mismas fechas analizables que el resto: la
    # inferida se aparto arriba de la linea base y la tendencia, pero al limite si llega.
    doses = sorted(
        (
            o for o in analysed
            if o.key == CUMULATIVE_DOSE and o.observation_type in DOSE_TYPES
            and _EARLIEST_PLAUSIBLE <= o.effective <= latest
        ),
        key=lambda o: o.effective,
    )
    dose_source: str | None = "parameter" if cumulative_dose_msv is not None else None
    if cumulative_dose_msv is None and doses:
        cumulative_dose_msv = doses[-1].value
        dose_source = "observation"

    # El tiempo de luz hacia el objetivo del perfil vigente en el corte (decisión del usuario,
    # 2026-11-11): el mismo perfil que sirve `mission.profile`.
    profile_state, chosen = _profile_and_target(settings, store, until)
    comms_window, comms_age = _fetch_comms(settings, epoch, chosen.target)
    solar_events, solar_age = _fetch_solar_events(settings)

    status = RiskEngine(dose_limit_msv=settings.career_dose_limit_msv).assess(
        subject=subject,
        deviations=current,
        trends=trends,
        comms=comms_window,
        solar_events=solar_events,
        cumulative_dose_msv=cumulative_dose_msv or 0.0,
    )

    return _Assessment(
        status=status, observations=observations, latest=latest, ignored=ignored,
        deviations=deviations, trends=trends, cumulative_dose_msv=cumulative_dose_msv,
        dose_source=dose_source, comms_window=comms_window, comms_age=comms_age,
        solar_age=solar_age, solar_events=solar_events, stored=stored, set_aside=set_aside,
        doses=doses, mission_profile=profile_state, cycle=cycle,
    )


def _closed_episode_shadow(settings: Settings, assessed: _Assessment) -> dict[str, Any]:
    """Lo que haria la regla del episodio cerrado si se adoptara (§5.38.6): medido, no decide.

    El usuario decidio (2026-10-26) medir la regla sin adoptarla. El estado de arriba sigue
    calculado sin ella; esto la aplica aparte, con las mismas desviaciones, el mismo «ahora» y
    los mismos argumentos del motor de riesgo, y dice que tendencias cerraria y que niveles
    cambiarian. Nada de aqui entra en un nivel, una alerta, una proyeccion ni la historia.
    """
    shadow: dict[str, Any] = {
        "adopted": False,
        "rule": i18n.loc(CLOSED_EPISODE_RULE),
        "closed": [],
        "overall_level": str(assessed.status.overall_level),
        "domains_changed": [],
    }
    # La regla solo toca tendencias que preocupan: sin ninguna no hay nada que reajustar (y esto
    # se pide en cada sondeo del estado).
    if not any(trend.is_concerning for trend in assessed.trends.values()):
        return shadow
    settled = trends_by_indicator(
        assessed.observations, settle=closing(assessed.deviations, CURRENT_WINDOW),
        phase_offset=assessed.phase_offset,
    )
    # Las que cerraria y que el estado mostraria asi: las del estrato que gana, como al decidir.
    closed = sorted(key for key, trend in settled.items() if trend.closed_episode)
    shadow["closed"] = [{"key": key, "text": settled[key].describe()} for key in closed]
    if not closed:
        return shadow
    cutoff = assessed.latest - CURRENT_WINDOW
    status = RiskEngine(dose_limit_msv=settings.career_dose_limit_msv).assess(
        subject=assessed.status.subject,
        deviations=[dev for dev in assessed.deviations if dev.effective >= cutoff],
        trends=settled,
        comms=assessed.comms_window,
        solar_events=assessed.solar_events,
        cumulative_dose_msv=assessed.cumulative_dose_msv or 0.0,
    )
    shadow["overall_level"] = str(status.overall_level)
    shadow["domains_changed"] = [
        {
            "domain": str(domain),
            "adopted": str(assessed.status.domains[domain].level),
            "with_rule": str(risk.level),
        }
        for domain, risk in status.domains.items()
        if domain in assessed.status.domains
        and risk.level is not assessed.status.domains[domain].level
    ]
    return shadow


def _set_aside_counts(set_aside: Sequence[VitalObservation]) -> dict[str, int]:
    return dict(Counter(str(item.observation_type) for item in set_aside))


def _set_aside_dose(set_aside: Sequence[VitalObservation]) -> dict[str, Any] | None:
    """La ultima dosis acumulada que no cuenta para el limite por su tipo, o `None` si no hay."""
    doses = [
        item for item in set_aside
        if item.key == CUMULATIVE_DOSE and item.observation_type not in DOSE_TYPES
    ]
    if not doses:
        return None
    last = max(doses, key=lambda item: item.effective)
    return {
        "value_msv": last.value,
        "effective": last.effective.isoformat(),
        # El tipo con que se registro (no un rotulo de EMMA sobre una cifra suya).
        "recorded_type": str(last.observation_type),
    }


def _set_aside_notes(set_aside: Sequence[VitalObservation]) -> list[str]:
    """Lo que el estado aparto por su tipo, dicho con cifras en las notas del estado."""
    if not set_aside:
        return []
    # Cuántas de cada tipo, en palabras: las compone `analysis/alert_support.py`, en su idioma.
    typed = typed_readings(_set_aside_counts(set_aside))
    notes = [
        i18n.tr(
        f"{typed} se guardan en el registro y no entran "
        f"en la línea base, la tendencia ni el riesgo: solo deciden las medidas",
        f"{typed} are kept in the record and do not enter "
        f"the baseline, the trend or the risk: only measured readings decide",
        )
    ]
    dose = _set_aside_dose(set_aside)
    if dose is not None:
        value = display.quantity(CUMULATIVE_DOSE, dose["value_msv"], get(CUMULATIVE_DOSE).unit)
        notes.append(
            i18n.tr(
            f"La dosis acumulada registrada como {TYPE_WORDS[dose['recorded_type']][0]} "
            f"({value}) no cuenta "
            f"para el límite de carrera: el riesgo solo lee dosis medidas o inferidas",
            f"The cumulative dose recorded as {i18n.loc(TYPE_WORDS[dose['recorded_type']][0])} "
            f"({value}) does not count "
            f"towards the career limit: the risk only reads measured or inferred doses",
            )
        )
    return notes


def _previous_levels(
    settings: Settings, assessed: _Assessment
) -> tuple[dict[Domain, RiskLevel], dt.datetime]:
    """El nivel de cada dominio una ventana antes, con las mismas reglas.

    Las desviaciones de `evaluate_rolling` son causales (cada lectura contra su pasado), asi que
    las de la ventana anterior ya estan calculadas: no se repite la linea base. Las tendencias de
    lo anterior al corte salen de `trends_before`, las mismas que usa ese paso de la historia.
    """
    cutoff = assessed.latest - CURRENT_WINDOW
    earlier = [
        dev for dev in assessed.deviations
        if cutoff - CURRENT_WINDOW <= dev.effective < cutoff
    ]
    status = RiskEngine(dose_limit_msv=settings.career_dose_limit_msv).assess(
        subject=assessed.status.subject,
        deviations=earlier,
        trends=assessed.trends_before(cutoff),
        comms=assessed.comms_window,
        solar_events=assessed.solar_events,
        cumulative_dose_msv=assessed.cumulative_dose_msv or 0.0,
    )
    return {domain: risk.level for domain, risk in status.domains.items()}, cutoff


def _mission_events(
    store: ObservationStore, subject: str, until: dt.datetime | None
) -> list[dict[str, Any]]:
    from app.api.mission import mission_events

    return mission_events(store, subject, until)


def _crew_whereabouts(
    store: ObservationStore, subject: str, until: dt.datetime | None, moment: dt.datetime
) -> Whereabouts:
    """Donde estaba el tripulante, leido una vez por estado.

    Las lecturas de las anclas, solo las que pueden decir algo de `moment`
    (`Sensing.lookback` hacia atras): el estado no lee la mision entera en cada consulta. El
    contexto de una alerta que mire una excursion mas antigua no ve esas estimaciones: para el es
    un tramo sin ubicacion, que nunca exculpa al habitat.
    """
    from app.api.mission import crew_whereabouts

    return crew_whereabouts(
        store, subject, until, moment - location_rules.sensing().lookback
    )


def _latest_profile(
    store: ObservationStore, subject: str, until: dt.datetime | None
) -> dict[str, Any]:
    from app.api.mission import latest_profile

    return latest_profile(store, subject, until)


FORECAST_SIGNER = "emma-forecast"
# Firma las discrepancias SPICE-Horizons (`record-integrity.md` §3.30): identidad reservada.
EPHEMERIS_SIGNER = "emma-ephemeris"


def _snapshot_predictions(
    store: ObservationStore,
    subject: str,
    predictions: Sequence[dict[str, Any]],
    observations: Sequence[VitalObservation],
    latest: dt.datetime,
    existing: Sequence[dict[str, Any]],
) -> bool:
    """Firma, como mucho una vez por indicador y dia, las proyecciones que se muestran.

    Dice si firmo alguna: si no, las instantaneas ya leidas siguen siendo todas.

    Nada de lo que se firma aqui es texto para leer: claves, instantes, cifras y versiones. Un
    campo de frase que se anada tendria que componerse dentro de `i18n.record_language()`.
    """
    today = latest.date().isoformat()
    done = {
        (item["key"], item["made_at"][:10]) for item in existing
    }
    payloads = []
    for item in predictions:
        if (item["key"], today) in done:
            continue
        anchor = daily_mean(observations, item["key"], latest)
        if anchor is None:
            continue
        payloads.append({
            "subject": subject,
            "key": item["key"],
            "made_at": latest.isoformat(),
            "horizon_at": (latest + FORECAST_HORIZON).isoformat(),
            "anchor_value": repr(anchor),
            "projected_change": repr(item["projected_change"]),
            "projected_change_low": repr(item["projected_change_low"]),
            "projected_change_high": repr(item["projected_change_high"]),
            "model_version": item["model_version"],
            "rules_version": rules_version(),
        })
    if payloads:
        store.record_prediction_snapshots(payloads, identity_for(FORECAST_SIGNER))
    return bool(payloads)


def _ephemeris_discrepancy_view(
    settings: Settings, store: ObservationStore, window: CommsWindow | None,
    until: dt.datetime | None,
) -> dict[str, Any] | None:
    """Firma la discrepancia SPICE-Horizons del día, si la hay, y dice dónde está firmada.

    Solo el estado de a bordo firma (como las instantáneas de proyección, §3.18), y como mucho
    una vez por día de efeméride (`record_ephemeris_discrepancy`). Con `until` (Tierra) no se
    firma nada y solo cuenta un asiento firmado hasta ese corte. No es una observación clínica:
    el riesgo y las alertas ya se calcularon y no lo leen.
    """
    if window is None:
        return None
    # Lo que se firma lleva una frase (`text`): se compone en el idioma del registro, lo pida
    # quien lo pida (`record-integrity.md`, «Idioma del registro»). La vista de abajo, no.
    with i18n.record_language():
        payload = comms_status.discrepancy_payload(window, settings.observer_body)
    if payload is None:
        return None
    if until is None:
        store.record_ephemeris_discrepancy(payload, identity_for(EPHEMERIS_SIGNER))
    day = (payload["epoch"], payload["target"], payload["observer"])
    for item in store.ephemeris_discrepancies(until):
        if (item["epoch"], item["target"], item["observer"]) == day:
            return comms_status.signed_view(item)
    return None


def _with_detail(
    alert: dict[str, Any],
    deviations: Sequence[Deviation],
    trends: dict[str, Trend],
    latest: dt.datetime,
    acknowledgements: Sequence[dict[str, Any]],
    adoptions: Sequence[dict[str, Any]],
    context_around: Callable[[dt.datetime | None], dict[str, Any]] | None = None,
    recommendations: Sequence[Recommendation] = (),
    observations: Sequence[VitalObservation] = (),
    followup_items: Sequence[dict[str, Any]] = (),
    set_aside: Sequence[VitalObservation] = (),
) -> dict[str, Any]:
    """La alerta con su detalle (§10), su version de reglas y su tiempo hasta la accion."""
    window_start = latest - CURRENT_WINDOW
    detail = explain_detail(
        Domain(alert["domain"]),
        [dev for dev in deviations if dev.effective >= window_start],
        trends.values(),
        # Que comprobar, que evidencia y la confianza de las lecturas: lo ya calculado, leido.
        recommendations,
        [obs for obs in observations if obs.effective >= window_start],
        # Lo inferido o predicho de la ventana: solo se cuenta (`ANALYSED_TYPES`).
        [obs for obs in set_aside if window_start <= obs.effective <= latest],
    )
    if context_around is not None:
        # Que contexto cambio alrededor del inicio (§3 `context_correlations`). Se anade al
        # detalle ya calculado: no hay camino de vuelta hacia el nivel de la alerta.
        onset = detail["onset"]
        detail["context"] = context_around(
            dt.datetime.fromisoformat(onset) if onset is not None else None
        )
    # Por que paso del flujo de la base de conocimiento (§10) va la alerta. Lee el detalle ya
    # completo, el reconocimiento y el seguimiento: se anade al final y no vuelve al nivel.
    detail["flow"] = alert_flow.flow(alert, detail, followup_items)
    return {
        **alert,
        "rules_version": rules_version(),
        "detail": detail,
        "time_to_action": time_to_action_of(
            alert["domain"], detail["onset"], acknowledgements, adoptions
        ),
    }


def _alert_context_builder(
    settings: Settings,
    store: ObservationStore,
    subject: str,
    until: dt.datetime | None,
    assessed: _Assessment,
    adoptions: Sequence[dict[str, Any]],
    declarations: Sequence[dict[str, Any]] | None = None,
    events: Sequence[dict[str, Any]] | None = None,
    stays: Sequence[Stay] | None = None,
) -> anatomy.ContextAround:
    """El contexto de cada alerta, leyendo el habitat y los eventos una sola vez por estado.

    Perezoso: un estado sin alertas no recorre el ledger en busca de lecturas de cabina.
    Recibe lo ya evaluado y solo lee: no hay nada aqui que el motor vuelva a consultar. El modo
    anatomico lo usa tambien para el contexto externo de cada region, con `alert=False` en las
    que no tienen alerta: un solo constructor, para que las dos vistas no discrepen.

    `declarations` son las declaraciones de sistemas que cuentan si quien llama ya las leyo
    (`/status` las lee para `declared_link`), y `events` los eventos de mision que cuentan
    (`/status` los sirve en `mission.events`), y `stays` donde estaba el tripulante (`/status`
    sirve la de ahora en `mission.location`): asi la respuesta y el contexto de cada alerta salen
    de la misma lectura. Sin ellos se leen aqui, al primer uso.
    """
    # De eventos solares el estado solo guarda los de `SOLAR_EVENT_RELEVANCE`, pedidos cuando
    # dice su edad: de antes o de despues no puede decir "ninguno", y el contexto lo declara.
    solar: alert_context.SolarRecord | None = None
    if assessed.solar_age is not None:
        now = _now()
        solar = alert_context.SolarRecord(
            events=assessed.solar_events,
            known_from=now - SOLAR_EVENT_RELEVANCE,
            known_until=now - dt.timedelta(seconds=assessed.solar_age[1]),
        )
    loaded: dict[str, Any] = {}

    def build(onset: dt.datetime | None, alert: bool = True) -> dict[str, Any]:
        if not loaded:
            from app.api.systems import system_declarations

            readings = store.habitat_readings(until=until)
            loaded.update(
                habitat_readings=readings,
                habitat_excursions=habitat_excursions(readings),
                mission_events=(
                    _mission_events(store, subject, until) if events is None else events
                ),
                # Donde estaba el tripulante: para decir, de cada excursion del habitat, si
                # estaba en ese modulo. Solo texto: no vuelve al nivel. Las lecturas de las
                # anclas, con el mismo tope que el estado (`_crew_whereabouts`): asi el contexto
                # de una alerta dice lo mismo aqui y en el estado.
                stays=(
                    _crew_whereabouts(store, subject, until, assessed.latest).stays
                    if stays is None else stays
                ),
                # El ejercicio registrado (cualquier dominio): solo se lista, no se juzga.
                exercise=[
                    obs for obs in assessed.observations if obs.key in exercise_summary.KEYS
                ],
                # La ingesta de liquidos, la dieta y el sueno registrados: igual, solo se listan.
                # `assessed.observations` son ya las lecturas que deciden (`state_reference`:
                # medidas y no descriptivas), asi que aqui no se filtra otra vez por tipo.
                recorded=[
                    obs for obs in assessed.observations
                    if obs.key in alert_context.RECORDED_KEYS
                ],
                # Lo que una persona declaro del estado de los sistemas del habitat. Solo
                # texto, como la ubicacion: una fuente mas del contexto, sin vuelta al nivel.
                system_declarations=(
                    system_declarations(store, until) if declarations is None
                    else declarations
                ),
            )
        return alert_context.around(
            onset=onset,
            reference=assessed.latest,
            solar=solar,
            adoptions=adoptions,
            mission_start=settings.mission_start,
            mission_days=settings.mission_days,
            gravity_regime=settings.gravity_regime,
            alert=alert,
            **loaded,
        )

    return build


def _driver_keys(assessed: _Assessment) -> dict[Domain, set[str]]:
    """Indicadores que mueven cada dominio: lecturas actuales fuera de lo esperado y derivas."""
    cutoff = assessed.latest - CURRENT_WINDOW
    keys: dict[Domain, set[str]] = {}
    for dev in assessed.deviations:
        if dev.effective >= cutoff and dev.is_concerning:
            keys.setdefault(get(dev.key).domain, set()).add(dev.key)
    for trend in assessed.trends.values():
        if trend.is_concerning:
            keys.setdefault(get(trend.key).domain, set()).add(trend.key)
    return keys


# LAS PIEZAS DEL ESTADO QUE LEE TAMBIEN LA CRONICA (2026-10-22).
#
# `/status` y la cronica (`chronicle_status`) sacan de aqui las alertas, las trayectorias y los
# seguimientos: con dos copias, una podria contar lo que la otra no. Y cada pieza lee el ledger
# una vez por respuesta: las decisiones sobre contramedidas se leian tres veces por estado.


@dataclass(frozen=True)
class _SignedActions:
    """Lo firmado sobre las alertas y las contramedidas de un tripulante que cuenta.

    QUE ACCIONES CUENTAN. Solo las firmadas por la consola —con la clave de un wearable no se
    silencia nada—, dentro de los limites que la API impone —firmadas a mano por fuera no valen
    mas que por la API— y, para Tierra, solo las ya decididas en su corte.
    """

    # Adopciones, cierres y decisiones de no adoptar (`countermeasure-followup`).
    decisions: list[dict[str, Any]]
    adoptions: list[dict[str, Any]]
    acknowledgements: list[dict[str, Any]]
    resolutions: list[dict[str, Any]]
    # Cambios de anuncio (supresion, inhibicion, rehabilitacion) dentro de los limites.
    changes: list[dict[str, Any]]
    # Descartes (`alert-dismissal`) con un motivo que la API habria aceptado.
    dismissals: list[dict[str, Any]]


def _signed_actions(
    store: ObservationStore, subject: str, until: dt.datetime | None
) -> _SignedActions:
    """Cada tipo de accion, leido una vez del ledger y filtrado con la regla de `_counts`."""
    decisions = [item for item in store.followup_decisions(subject) if _counts(item, until)]
    return _SignedActions(
        decisions=decisions,
        adoptions=[item for item in decisions if item["action"] == "adopted"],
        acknowledgements=[
            ack for ack in store.acknowledgements(subject) if _counts(ack, until)
        ],
        resolutions=[
            item for item in store.alert_resolutions(subject) if _counts(item, until)
        ],
        changes=[
            change for change in store.annunciation_changes(subject)
            if _counts(change, until) and _within_limits(change)
        ],
        dismissals=[
            item for item in store.alert_dismissals(subject)
            if _counts(item, until) and _acceptable_dismissal(item)
        ],
    )


def _acceptable_dismissal(item: dict[str, Any]) -> bool:
    """Un descarte que la API no habria aceptado no se enseña, lo firme quien lo firme: un motivo
    fuera del vocabulario, «otro» sin nota o sin una persona con nombre detras. La regla es la
    misma con que el almacen se niega a firmarlo (`dismissal_problem`)."""
    return dismissal_problem(item["reason"], item["note"], item["declared_by"]) is None


def _dismissal_view(item: dict[str, Any]) -> dict[str, Any]:
    """El descarte vigente de una alerta, con la palabra de su motivo: no la redacta la consola."""
    return {
        "reason": item["reason"],
        "reason_display": i18n.loc(DISMISSAL_REASONS[item["reason"]]),
        "note": item["note"],
        "declared_by": item["declared_by"],
        "ledger_index": item["ledger_index"],
        "reference_time": item["reference_time"],
        # Con que reglas se firmo el descarte, frente a las de hoy (§3.26): dicho, no recalculado.
        "rules": decided_with(item.get(RULES_VERSION_FIELD)),
    }


def _domain_trajectories(settings: Settings, assessed: _Assessment) -> dict[str, Any]:
    """«Recuperandose» o «empeorando» frente a una ventana antes, por dominio (descriptivo)."""
    previous, previous_at = _previous_levels(settings, assessed)
    trajectory = trajectories(
        {domain: risk.level for domain, risk in assessed.status.domains.items()},
        previous, previous_at,
    )
    return {
        str(domain): with_wording(trajectory.get(str(domain)))
        for domain in assessed.status.domains
    }


def _followup_items(assessed: _Assessment, actions: _SignedActions) -> list[dict[str, Any]]:
    """Contramedidas adoptadas y su seguimiento (especificacion §7, §14), con lo que cuenta."""
    return followups(
        actions.decisions,
        {str(domain): risk.level for domain, risk in assessed.status.domains.items()},
        assessed.observations,
        assessed.latest,
    )


def _silencing_and_clock(
    actions: _SignedActions, assessed: _Assessment, until: dt.datetime | None
) -> tuple[dict[str, dict[str, Any]], dt.datetime]:
    """El silencio vigente de cada dominio y el reloj con que caduca.

    Una supresion caduca con el reloj, no con la ultima lectura: si el sensor calla, una hora no
    puede durar para siempre. Tierra, en cambio, ve su corte.
    """
    silencing = _silencing_by_domain(actions.changes, assessed.latest)
    clock = assessed.latest if until is not None else max(assessed.latest, _now())
    return silencing, clock


def _detailed_alerts(
    assessed: _Assessment,
    actions: _SignedActions,
    silencing: dict[str, dict[str, Any]],
    clock: dt.datetime,
    recommendations: Sequence[Recommendation],
    followup_items: Sequence[dict[str, Any]],
    context_around: Callable[[dt.datetime | None], dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Cada alerta con su detalle (especificacion §10). Lee lo que el motor ya calculo."""
    return [
        _with_detail(
            alert, assessed.deviations, assessed.trends, assessed.latest,
            actions.acknowledgements, actions.adoptions, context_around, recommendations,
            assessed.observations, followup_items, assessed.set_aside,
        )
        for alert in _alerts(
            assessed.status.domains, actions.acknowledgements, silencing, assessed.latest,
            clock, actions.resolutions, actions.dismissals,
        )
    ]


def chronicle_status(
    settings: Settings,
    store: ObservationStore,
    subject: str,
    until: dt.datetime | None,
    assessed: _Assessment,
) -> dict[str, Any]:
    """Lo que la cronica lee del estado (`app/timeline.py`), sin escribir ni verificar nada.

    LA CRONICA YA NO PIDE EL ESTADO ENTERO (2026-10-22). Llamaba a `crew_status`, y con cuatro
    tripulantes sembrados tardaba unos 6 s (1,5 s ahora; `compliance/hmi-state-of-the-art.md`
    §5.35.13): verificaba la cadena entera y el disco (la mayor parte del tiempo), repetia la
    evaluacion que ya hace la historia recalculada y, sin `until`, firmaba
    instantaneas de proyeccion que la cronica no ensena. Esa escritura no era de la cronica:
    `compliance/record-integrity.md` §3.18 dice que solo la firma el estado de a bordo, por las
    proyecciones que muestra, y la cronica es de solo lectura.

    Aqui va lo que la cronica usa, con las MISMAS piezas que `/status` (las de arriba) sobre la
    misma evaluacion: el instante de referencia, la trayectoria de cada dominio, cada alerta con
    su inicio, los seguimientos y los eventos del plan. Las alertas no llevan el contexto ni el
    paso del flujo que les anade el estado: la cronica no los cuenta. No es el estado y no se
    sirve como tal; la integridad de la cadena la sigue diciendo `/api/status`, y lo que se lee
    aqui pasa por las mismas comprobaciones de hash que cualquier consulta (`core/storage.py`).
    `tests/test_status_performance.py` compara cada campo con el de `/status`.
    """
    actions = _signed_actions(store, subject, until)
    followup_items = _followup_items(assessed, actions)
    silencing, clock = _silencing_and_clock(actions, assessed, until)
    recommendations = Advisor().recommend(assessed.status, _driver_keys(assessed))
    return {
        "subject": assessed.status.subject,
        "rules_version": rules_version(),
        "domains": {
            domain: {"trajectory": change}
            for domain, change in _domain_trajectories(settings, assessed).items()
        },
        "alerts": _detailed_alerts(
            assessed, actions, silencing, clock, recommendations, followup_items, None
        ),
        "followups": followup_items,
        "mission": {"events": _mission_events(store, subject, until)},
        "data": {"reference_time": assessed.latest.isoformat()},
    }


@router.get("/status")
def crew_status(
    settings: SettingsDep,
    store: StoreDep,
    subject: str = "crew-01",
    epoch: dt.date | None = None,
    # SIN DOSIS NO HAY CERO.
    #
    # El valor por defecto era 0,0, y la respuesta devolvia "0,0 de 600 mSv": una
    # cifra sin origen presentada como medida. Ahora, si nadie facilita la dosis,
    # la respuesta dice que no la tiene (`cumulative_msv: null`). El motor sigue
    # sin sumar riesgo por dosis en ese caso, que es lo que ya hacia con el 0.
    cumulative_dose_msv: float | None = Query(default=None, ge=0.0),
    # EL ESTADO QUE PUEDE TENER TIERRA.
    #
    # Lo que se ve a bordo en un instante llega a Tierra un tiempo de luz despues.
    # Una consola de Tierra que mostrara el veredicto de ahora estaria ensenando
    # algo que Tierra todavia no puede saber. Con `until`, el estado se calcula
    # solo con las lecturas hasta ese instante: el que Tierra tiene de verdad.
    until: dt.datetime | None = None,
) -> dict[str, Any]:
    """Estado de salud completo, a partir de lo que hay en el almacen.

    Si el almacen esta vacio se devuelve 404 en vez de inventar datos: un panel
    clinico que muestra cifras sin origen es peor que uno que dice que no sabe.
    """
    assessed = _assess(settings, store, subject, epoch, cumulative_dose_msv, until)
    status = assessed.status
    observations = assessed.observations
    latest = assessed.latest
    ignored = assessed.ignored
    deviations = assessed.deviations
    trends = assessed.trends
    cumulative_dose_msv = assessed.cumulative_dose_msv
    dose_source = assessed.dose_source
    comms_window = assessed.comms_window
    comms_age = assessed.comms_age
    solar_age = assessed.solar_age

    # Lo firmado que cuenta, leido una vez: antes las decisiones sobre contramedidas se leian
    # tres veces por estado (adopciones, seguimiento y recomendaciones).
    actions = _signed_actions(store, subject, until)
    domain_trajectories = _domain_trajectories(settings, assessed)
    phase_free = without_phase(observations, assessed.phase_offset)

    predictions = [
        item for item in (projection(trend) for trend in trends.values()) if item is not None
    ]
    # Solo el estado de a bordo firma instantaneas: el de Tierra (`until`) es una vista del
    # pasado y no hace proyecciones nuevas. Se releen solo si se firmo alguna.
    snapshots = store.prediction_snapshots(subject)
    if until is None and _snapshot_predictions(
        store, subject, predictions, observations, latest, snapshots
    ):
        snapshots = store.prediction_snapshots(subject)

    advisor = Advisor()
    # Una vez: las sirve el estado y las lee el detalle de cada alerta (§10).
    recommendations = advisor.recommend(status, _driver_keys(assessed))
    verification = store.verify_integrity()
    silencing, clock = _silencing_and_clock(actions, assessed, until)
    personal_fraction = (
        sum(1 for dev in deviations if not dev.used_population_range) / len(deviations)
        if deviations
        else 0.0
    )
    # Contramedidas adoptadas y su seguimiento. Se calcula una vez: lo sirve el estado y lo lee
    # el ultimo paso del flujo de cada alerta.
    followup_items = _followup_items(assessed, actions)
    # Las declaraciones de sistemas y los eventos de mision, una vez: los sirve el estado y los
    # lee el contexto de cada alerta.
    declarations = _system_declarations(store, until)
    events = _mission_events(store, subject, until)
    # Donde estaba el tripulante, una vez: el estado sirve la de su instante de referencia
    # (`mission.location`) y el contexto de cada alerta la lee para las excursiones de cabina.
    whereabouts = _crew_whereabouts(store, subject, until, latest)

    # La dosis previa que declara el perfil: la leen la carrera y su proyeccion (C7).
    prior_career_msv = _latest_profile(store, subject, until)["prior_career_dose_msv"]
    # El entorno de la mision firmado hasta el corte, o el de la configuracion. Lo unico suyo que
    # entra en los niveles es su objetivo de efemerides, que ya uso `_assess` con este mismo corte
    # (`_ephemeris_target`); aqui se sirve con lo que hizo (`core/mission_profile_changes.py`).
    profile_state = assessed.mission_profile or store.mission_profile(
        until, settings.mission_profile
    )
    target = mission_profiles.ephemeris_target(str(profile_state["id"]), settings).target
    signed_discrepancy = _ephemeris_discrepancy_view(settings, store, comms_window, until)
    payload: dict[str, Any] = {
        "subject": status.subject,
        "summary": advisor.summarize(status),
        "overall_level": str(status.overall_level),
        # Como se nombra cada nivel: la interfaz pone el color y el glifo, no la palabra.
        "level_labels": level_labels(),
        "isolation_factor": round(status.isolation_factor, 3),
        "comms": status.comms.to_dict() if status.comms else None,
        "comms_data_age": comms_age[0] if comms_age else None,
        "comms_data_age_seconds": comms_age[1] if comms_age else None,
        # El estado del retardo dicho una vez (2026-11-11, `environment/comms_status.py`): hay
        # retardo y de qué fuente, no aplica (perfil sin objetivo) o falta de verdad; y si el
        # cálculo local discrepa de Horizons, la frase y dónde quedó firmado. La interfaz lo lee
        # en vez de deducirlo de `comms` o de la caché de Horizons. Descriptivo.
        "comms_status": comms_status.describe(
            comms_window, target, epoch or utc_today(), profile_id=str(profile_state["id"]),
            signed=signed_discrepancy,
        ),
        # Lo que una persona declaro del enlace con Tierra (KB §2.1), para la franja y la ficha
        # de Tierra. Solo texto: ni `isolation_factor` ni las recomendaciones lo leen. Para
        # Tierra, lo declarado hasta su corte, como toda accion del operador.
        "declared_link": habitat_systems.earth_link(declarations),
        "solar_data_age": solar_age[0] if solar_age else None,
        "solar_data_age_seconds": solar_age[1] if solar_age else None,
        # ¿Caducado? Lo decide el backend con plazos que entran en `rules_version`; antes
        # los fijaba la interfaz. Sin dato es «sin dato», nunca al dia (tabla F.5-1).
        "freshness": {
            "comms": describe_freshness(
                ExternalSource.EPHEMERIS, comms_age[1] if comms_age else None
            ),
            "solar": describe_freshness(
                ExternalSource.SPACE_WEATHER, solar_age[1] if solar_age else None
            ),
            "basis": i18n.loc(STALENESS_BASIS),
        },
        "active_solar_event": (
            status.active_solar_event.to_dict() if status.active_solar_event else None
        ),
        "dose": {
            "cumulative_msv": cumulative_dose_msv,
            "limit_msv": status.dose_limit_msv,
            "fraction": (
                round(status.dose_fraction, 4) if cumulative_dose_msv is not None else None
            ),
            "source": dose_source,
            # La dosis efectiva es una magnitud calculada (absorbida por factor de
            # calidad y pesos de tejido), nunca la lectura directa de un sensor.
            "observation_type": "inferred",
            # Una dosis acumulada registrada como predicha no llega al limite de carrera
            # (`DOSE_TYPES`): se dice cual es, para que no desaparezca en silencio.
            "set_aside": _set_aside_dose(assessed.set_aside),
        },
        # Derivas reales llevadas al horizonte de relevancia, rotuladas como predichas.
        "predictions": predictions,
        # ¿Acertaron? Retrospectiva e instantaneas firmadas ya maduras (descriptivo).
        "forecast_checks": forecast_summary(
            # La retrospectiva, en la escala en que proyecta el motor: sin la fase del ciclo, si
            # se ajusta. Las instantaneas firmadas guardan su ancla en bruto y se comparan en bruto.
            hindcast(phase_free, latest) + matured(snapshots, observations, latest)
        ),
        # La regla del episodio cerrado, MEDIDA Y SIN ADOPTAR (§5.38.6): que tendencias daria
        # por cerradas y que niveles cambiarian. Descriptivo: el veredicto de arriba no la usa.
        "closed_episode_shadow": _closed_episode_shadow(settings, assessed),
        # Si la linea base se ajusto por la fase del ciclo y por que (`api/cycle_phase.py`):
        # `applied`, `phase` y una frase fija del backend. El veredicto de arriba ya la usa.
        "cycle_phase": assessed.cycle.to_dict() if assessed.cycle is not None else None,
        # Con que clase de datos se hizo el veredicto: cuantas lecturas de cada tipo y
        # de cada entorno. "Nominal" sobre datos simulados no afirma lo mismo que sobre
        # lecturas de vuelo (especificacion §2).
        "provenance": {
            "observation_type": dict(Counter(str(o.observation_type) for o in observations)),
            "evidence_context": dict(Counter(str(o.evidence) for o in observations)),
            # Lo que el veredicto NO leyo por su tipo (`ANALYSED_TYPES`): firmado y sin decidir.
            "set_aside": _set_aside_counts(assessed.set_aside),
            "rule": i18n.loc(ANALYSED_RULE),
        },
        "domains": {
            str(domain): {
                "score": risk.score,
                "level": str(risk.level),
                "drivers": list(risk.drivers),
                # «Recuperandose» o «empeorando» frente a una ventana antes (descriptivo).
                "trajectory": domain_trajectories[str(domain)],
            }
            for domain, risk in status.domains.items()
        },
        # Lo que va al lado de cada una (decision, respuesta previa, recursos, efectos) se anade
        # abajo, con `_decorate_recommendations`, cuando ya estan los seguimientos y los recursos.
        "recommendations": [],
        "notes": list(status.notes)
        + _set_aside_notes(assessed.set_aside)
        + (
            [
                i18n.tr(
                f"{sum(ignored.values())} lecturas con fecha no analizable se "
                f"apartaron del análisis; revise el reloj del dispositivo",
                f"{sum(ignored.values())} readings with a date that cannot be analysed were "
                f"set aside from the analysis; the device clock may need checking",
                )
            ]
            if sum(ignored.values())
            else []
        ),
        "data": {
            "observations": len(observations),
            # Lo que abarcan los datos, no lo que mira cada via: las desviaciones
            # miran los ultimos `CURRENT_WINDOW` y la tendencia `TREND_WINDOW`.
            # Informar solo del primero hacia creer que la tendencia se ajusta
            # sobre toda la mision, y ya no es asi.
            "window_days": (latest - min(o.effective for o in observations)).days,
            "deviation_window_days": CURRENT_WINDOW.days,
            "trend_window_days": TREND_WINDOW.days,
            "reference_time": latest.isoformat(),
            "readings_ignored": ignored,
            "integrity_ok": verification.ok,
            # SOBRE QUE SE APOYA EL VEREDICTO.
            #
            # Un panel clinico que dice "nominal" sin decir que no tiene base
            # personal para juzgarlo esta afirmando mas de lo que sabe. Sin base
            # personal solo se comprueban limites de peligro absoluto, asi que
            # "nominal" significa entonces "no ha cruzado ningun limite grave",
            # no "esta como siempre". Son dos afirmaciones muy distintas.
            "personal_baseline_fraction": round(personal_fraction, 3),
            "basis": (
                i18n.tr("línea base personal", "personal baseline")
                if personal_fraction >= 0.5
                else i18n.tr(
                "principalmente límites de peligro absoluto: "
                "faltan muestras para una línea base personal",
                "mainly absolute danger limits: "
                "there are not enough samples for a personal baseline",
                )
            ),
            # CUANTO SE PUEDE CONFIAR EN CADA LECTURA (especificacion §2 y §10).
            #
            # La confianza ya decidia —una lectura dudosa no entra en la linea base ni
            # sostiene mas que un hallazgo leve— pero no se ensenaba. Solo se lee lo que
            # el motor ya calculo: este bloque no mueve ningun nivel.
            # Lleva ademas `device_bindings`: lecturas recientes de un dispositivo que en su
            # instante constaba vinculado a otro tripulante. Descriptivo, como todo el bloque.
            "quality": describe_quality(
                observations, deviations, latest, CURRENT_WINDOW,
                _bindings_for_status(store, until),
            ),
        },
        # Cada alerta con su detalle (especificacion §10): que cambio, desde cuando y frente
        # a que base. Lee lo que el motor ya calculo; no decide nada.
        # El contexto de las alertas se prepara una vez por estado, no una por alerta.
        "alerts": _detailed_alerts(
            assessed, actions, silencing, clock, recommendations, followup_items,
            _alert_context_builder(
                settings, store, subject, until, assessed, actions.adoptions, declarations,
                events, whereabouts.stays,
            ),
        ),
        # Lo que no se mide en vuelo, estimado y rotulado INFERIDO (especificacion §9).
        "inferred": [
            bone_density_band(
                mission_day(latest, settings.mission_start),
                # Una lectura de 0 minutos no es «hay registro de ejercicio»: el booleano solo
                # elegia una frase, y ahora la elige lo medido (tres casos). La banda no lo lee.
                exercise_logged=exercise["record"]["state"] == exercise_summary.RECORDED,
                exercise=exercise,
                # En posvuelo la banda se detiene en el dia de regreso (decision del usuario,
                # 2026-10-21): la fase y ese dia son los de `core/mission.py`.
                phase=phase_at(latest, settings.mission_start, settings.mission_days),
                return_day=float(settings.mission_days),
                # La densitometria MEDIDA en Tierra junto a la banda (decision del usuario,
                # 2026-10-26): es descriptiva, asi que se lee de lo almacenado, no de lo que
                # analiza el motor. Comprueba la inferencia; no la mueve ni puntua.
                densitometry=densitometry.against_band(
                    assessed.stored
                    if assessed.stored is not None
                    else store.query(subject, until=until),
                    mission_start=settings.mission_start,
                    return_day=float(settings.mission_days),
                ),
            )
            # Lo MEDIDO que acompana a la banda: lo que el motor ya calculo, sin tocarla.
            for exercise in [
                exercise_summary.measured(observations, deviations, trends, latest)
            ]
        ],
        "followups": followup_items,
        "mission": {
            **_mission(settings, observations),
            **mission_context(
                latest, settings.mission_start, settings.mission_days, settings.gravity_regime
            ),
            # EVA y bloques de trabajo declarados (especificacion §3, MissionContext).
            "events": events,
            # Donde esta el tripulante en el instante de referencia (especificacion §3,
            # MissionContext "location"): la que manda (`context.prevailing`: la consola sobre
            # las anclas), con de donde sale (`source`) y su estado (`location_state`), o null y
            # por que. Descriptiva: no entra en ningun nivel ni en ninguna alerta.
            **location_rules.view(whereabouts, latest),
            # El entorno de la mision vigente (el ultimo firmado por la consola hasta el corte, o
            # el de la configuracion), con lo que una fuente leida dice de el. Descriptivo salvo su
            # objetivo de efemerides, hacia el que se calculo el tiempo de luz real que escala el
            # riesgo (2026-11-11); los niveles ya se calcularon.
            "profile": {
                **mission_profiles.describe(
                    str(profile_state["id"]), settings,
                    # Para decir qué hizo hoy el tiempo de luz con el riesgo, ya calculado.
                    round_trip_minutes=(
                        comms_window.round_trip_minutes if comms_window is not None else None
                    ),
                    isolation_factor=status.isolation_factor,
                ),
                "declaration": mission_profile_changes.view(profile_state),
                # Si el objetivo esta en conjuncion solar ese dia (D6). Igual de descriptivo: el
                # factor de aislamiento y los niveles ya se calcularon arriba sin leerla. Un perfil
                # sin objetivo de efemerides no tiene conjuncion que decir: null, y el porque va en
                # `ephemeris.text` (no un «sin efemerides» de fallo).
                "solar_conjunction": (
                    None if target is None else conjunction.describe(comms_window, target)
                ),
            },
            # Que dias de la mision tienen efemerides en cache (E6): sin red, los que no, salen con
            # el retardo y la conjuncion «sin dato». Solo mira el disco y no decide nada. Sin
            # objetivo de efemerides no hay cache que mirar: null, dicho en `profile.ephemeris`.
            "ephemeris_coverage": (
                None if target is None
                else ephemeris_coverage.coverage(settings, day=epoch, target=target)
            ),
        },
        # Radiacion en tres escalas (KB §7): aguda con su tiempo hasta la accion, de mision
        # (inferida) y de carrera con la dosis previa declarada en el perfil.
        "radiation": radiation_scales(
            active_event=(
                status.active_solar_event.to_dict() if status.active_solar_event else None
            ),
            event_time=status.active_solar_event.time if status.active_solar_event else None,
            now=latest,
            mission=mission_dose(observations, settings.mission_start),
            prior_career_msv=prior_career_msv,
            limit_msv=status.dose_limit_msv,
            # PREDICHA al fin de mision configurado (C7): se muestra y no entra en
            # `cumulative_dose_msv` ni en ningun nivel, que ya se calcularon arriba.
            projection=mission_projection(
                observations,
                mission_start=settings.mission_start,
                mission_days=settings.mission_days,
                prior_career_msv=prior_career_msv,
                limit_msv=status.dose_limit_msv,
            ),
        ),
        # Con que reglas se decidio (especificacion §12).
        "rules_version": rules_version(),
        # Que respaldo tiene cada parametro del modelo que genero estas lecturas, o `None` si
        # no vienen del simulador. Descriptivo: no entra en ningun calculo.
        "simulation": evidence_report(o.source for o in observations),
        "monitoring": _monitoring(
            personal_fraction=personal_fraction,
            # Un perfil sin objetivo de efemerides no pierde nada: con el no se calcula el retardo
            # por diseño (2026-11-11), y decir «sin efemerides» seria anunciar un fallo que no hay.
            has_comms=comms_window is not None or target is None,
            has_solar=solar_age is not None,
            # Una instantanea o una cache caducada no vigilan lo que pasa ahora (2026-11-04).
            solar_stale_age=(
                solar_age[0] if solar_age is not None
                and not describe_freshness(ExternalSource.SPACE_WEATHER, solar_age[1])["is_current"]
                else None
            ),
            has_dose=cumulative_dose_msv is not None,
            ignored=sum(ignored.values()),
            integrity_ok=verification.ok,
            inhibitions=_active_inhibitions(silencing, clock),
        ),
    }
    # Los recursos de a bordo que una persona declaro (especificacion §3, `available_resources`;
    # `core/resources.py`) van al contexto de mision...
    declared_resources = _declared_resources(store, until)
    payload["mission"]["available_resources"] = resource_rules.available(declared_resources)
    # ...y junto a cada recomendacion, con lo demas que va a su lado: lo que una persona decidio
    # sobre ella («se decidio no adoptarla…»), la respuesta previa (KB H5: que paso las otras
    # veces que se adopto, de los seguimientos YA derivados arriba, mismas firmas y mismo corte),
    # que recursos pide y cuales constan como no disponibles o sin declarar, y los efectos de su
    # contramedida con la co-adopcion de este tripulante (`advisor/effects.py`, fuera de la
    # huella de reglas). Cada campo solo se anade: nada quita, reordena ni decide.
    payload["recommendations"] = _decorate_recommendations(
        recommendations, actions.decisions, payload["followups"], declared_resources
    )
    return payload


# Por debajo de esta fraccion de lecturas juzgadas contra base personal, el
# veredicto descansa sobre todo en limites de peligro absoluto (ver `data.basis`).
_PERSONAL_BASELINE_ENOUGH = 0.5


def _monitoring(
    *,
    personal_fraction: float,
    has_comms: bool,
    has_solar: bool,
    has_dose: bool,
    ignored: int,
    integrity_ok: bool,
    inhibitions: Sequence[dict[str, Any]] = (),
    solar_stale_age: str | None = None,
) -> dict[str, Any]:
    """Con que capacidad esta vigilando el sistema ahora mismo.

    `solar_stale_age` es la edad de los datos de DONKI cuando estan caducados: una instantanea
    del paquete o una cache vieja estan, pero no dicen nada de un evento posterior, y la
    meteorologia espacial no se da por vigilada (2026-11-04).

    NASA-STD-3001 Vol 2, F.6.2: *"The system must provide an indication of the
    current level of automation"* y *"must alert the human operator when a problem
    or situation is beyond its capability"*. Un "nominal" dicho con la mitad de las
    fuentes caidas no significa lo mismo que con todas: la tripulacion tiene que
    saber que parte de la vigilancia no esta funcionando, y que deja de hacerse.

    Cada capacidad dice si esta disponible y, si no, **que se pierde**, no solo que
    falta. El nivel es "full" solo si no falta ninguna.
    """
    capabilities = [
        (
            "personal-baseline",
            i18n.tr("Línea base personal", "Personal baseline"),
            personal_fraction >= _PERSONAL_BASELINE_ENOUGH,
            i18n.tr(
            "Faltan lecturas para una base personal: solo se vigilan los límites de "
            "peligro absoluto, y una desviación dentro de ellos no se detecta.",
            "There are not enough readings for a personal baseline: only the absolute danger "
            "limits are monitored, and a deviation within them is not detected.",
            ),
        ),
        (
            "light-time",
            i18n.tr("Retardo con Tierra", "Delay to Earth"),
            has_comms,
            i18n.tr(
            "Sin efemérides: los umbrales no se ajustan por aislamiento.",
            "No ephemeris: the thresholds are not adjusted for isolation.",
            ),
        ),
        (
            "space-weather",
            i18n.tr("Meteorología espacial", "Space weather"),
            has_solar and solar_stale_age is None,
            i18n.tr(
            "Sin datos de NASA DONKI: no se detectan eventos de partículas solares.",
            "No NASA DONKI data: solar particle events are not detected.",
            )
            if not has_solar
            else i18n.tr(
            f"Datos de NASA DONKI caducados ({solar_stale_age}): un evento de partículas "
            "solares posterior a ellos no se detecta.",
            f"Stale NASA DONKI data ({solar_stale_age}): a solar particle event later than "
            "them is not detected.",
            ),
        ),
        (
            "career-dose",
            i18n.tr("Dosis de carrera", "Career dose"),
            has_dose,
            i18n.tr(
            "Sin dosis acumulada: no se evalúa el límite de carrera de [V1 4030].",
            "No cumulative dose: the career limit of [V1 4030] is not assessed.",
            ),
        ),
        (
            "reading-dates",
            i18n.tr("Fechas de las lecturas", "Reading dates"),
            ignored == 0,
            i18n.tr(
            f"{display.number(ignored, 0)} lecturas apartadas por fecha no analizable: "
            "no entran en la evaluación.",
            f"{display.number(ignored, 0)} readings set aside because their date cannot be "
            "analysed: they do not enter the assessment.",
            ),
        ),
        (
            "alert-annunciation",
            i18n.tr("Anuncio de alertas", "Alert annunciation"),
            not inhibitions,
            i18n.tr("Alertas inhibidas: ", "Alerts inhibited: ")
            + "; ".join(
                i18n.tr(
                f"{Domain(item['domain']).display} hasta {RiskLevel(item['level']).display}"
                f" (lo pidió {item['requested_by']}: {item['reason']})",
                f"{i18n.loc(Domain(item['domain']).display)} up to "
                f"{i18n.loc(RiskLevel(item['level']).display)}"
                f" (requested by {item['requested_by']}: {item['reason']})",
                )
                for item in inhibitions
            )
            + i18n.tr(
                ". No se anuncian mientras dure la inhibición.",
                ". They are not annunciated while the inhibition lasts.",
            ),
        ),
        (
            "record-integrity",
            i18n.tr("Integridad del registro", "Record integrity"),
            integrity_ok,
            i18n.tr(
            "La cadena firmada no verifica: el veredicto no tiene respaldo de firma.",
            "The signed chain does not verify: the verdict has no signature backing.",
            ),
        ),
    ]
    # Por que falta: un dato que no llega (cian en la tabla F.5-1, "Missing or stale
    # data") o una decision de la tripulacion (amarillo, "manual override"). No son lo
    # mismo, y pintar una inhibicion como dato ausente ocultaria que alguien la decidio.
    manual = {"alert-annunciation"}
    items = [
        {
            "key": key,
            "label": label,
            "available": ok,
            "cause": None if ok else ("manual" if key in manual else "missing"),
            "consequence": None if ok else lost,
        }
        for key, label, ok, lost in capabilities
    ]
    return {
        "level": "full" if all(item["available"] for item in items) else "reduced",
        "capabilities": items,
    }


def _silencing_by_domain(
    changes: Sequence[dict[str, Any]], latest: dt.datetime
) -> dict[str, dict[str, Any]]:
    """El ultimo cambio de anuncio de cada dominio que ya existia en `latest`.

    Solo cuentan los decididos sobre un estado igual o anterior a este: la consola
    de Tierra, que pide el estado de hace un tiempo de luz, no ve silenciado algo que
    a bordo se silencio despues.
    """
    last: dict[str, dict[str, Any]] = {}
    for change in sorted(changes, key=lambda item: item["ledger_index"]):
        if dt.datetime.fromisoformat(change["reference_time"]) <= latest:
            last[change["domain"]] = change
    return last


# Topes de duracion de un silencio, los mismos que impone la API.
MAX_SUPPRESSION = dt.timedelta(hours=12)
MAX_INHIBITION = dt.timedelta(days=7)


def _within_limits(change: dict[str, Any]) -> bool:
    """Un silencio que la API no habria aceptado no se respeta, lo firme quien lo firme."""
    if change["action"] == "enable":
        return True
    try:
        level = RiskLevel(change["level"])
        duration = dt.datetime.fromisoformat(change["until"]) - dt.datetime.fromisoformat(
            change["reference_time"]
        )
    except ValueError:
        return False
    if duration <= dt.timedelta(0):
        return False
    if change["action"] == "suppress":
        limit = MAX_CRITICAL_SUPPRESSION if level is RiskLevel.CRITICAL else MAX_SUPPRESSION
        return duration <= limit
    return change["action"] == "inhibit" and level is not RiskLevel.CRITICAL and (
        duration <= MAX_INHIBITION
    )


def _silenced(change: dict[str, Any] | None, level: RiskLevel, clock: dt.datetime) -> str:
    """Estado de anuncio de una alerta a `level`: suppressed, inhibited o normal."""
    if change is None or change["action"] == "enable":
        return "normal"
    if clock > dt.datetime.fromisoformat(change["until"]):
        return "normal"  # vencido: vuelve a anunciarse sin que nadie lo pida
    silenced_level = RiskLevel(change["level"])
    if change["action"] == "suppress":
        return "suppressed" if level is silenced_level else "normal"
    # Inhibicion: hasta ese nivel. Una escalada por encima rompe el silencio.
    return "inhibited" if _LEVEL_RANK[level] <= _LEVEL_RANK[silenced_level] else "normal"


def _active_inhibitions(
    silencing: dict[str, dict[str, Any]], clock: dt.datetime
) -> list[dict[str, Any]]:
    """Inhibiciones en vigor, haya o no alerta ahora.

    Un dominio inhibido y nominal tampoco anunciaria una alerta si llegara: eso es
    vigilancia reducida aunque la lista de alertas este vacia.
    """
    return [
        change
        for change in silencing.values()
        if change["action"] == "inhibit"
        and clock <= dt.datetime.fromisoformat(change["until"])
    ]


def _alerts(
    domains: dict[Domain, Any],
    acknowledgements: Sequence[dict[str, Any]],
    silencing: dict[str, dict[str, Any]],
    latest: dt.datetime,
    clock: dt.datetime,
    resolutions: Sequence[dict[str, Any]] = (),
    dismissals: Sequence[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Las alertas activas, si alguien las ha reconocido y en qué estado las declaró.

    UN DESCARTE (`alert-dismissal`) cubre lo mismo que un reconocimiento, y vale mientras no
    haya despues un estado declarado ("en arreglo", "resuelto") de la misma alerta: lo ultimo
    que una persona dijo de ella es lo que se ve. Asi, `dismissal` no nulo quiere decir que el
    descarte es lo ultimo dicho, y `resolution` queda como el ultimo estado declarado antes de el
    (un hecho firmado, no lo vigente). No toca el reconocimiento ni el anuncio.

    QUE CUBRE UN RECONOCIMIENTO.
    ----------------------------
    El mismo dominio al mismo nivel, y solo mientras la alerta reconocida siga
    dentro de la ventana con que se calculo (`CURRENT_WINDOW`). Si valiera para
    siempre, una recaida dias despues llegaria ya reconocida, sin parpadeo. Pasada la
    ventana, las lecturas que motivaron la alerta reconocida han salido del calculo:
    lo que siga alertando se apoya en lecturas nuevas, y hay que reconocerlo otra vez.
    Un cambio de nivel es siempre una alerta nueva.
    """
    alerts: list[dict[str, Any]] = []
    for domain, risk in domains.items():
        if risk.level is RiskLevel.NOMINAL:
            continue
        covering = [
            ack
            for ack in acknowledgements
            if ack["domain"] == str(domain)
            and ack["level"] == str(risk.level)
            and latest - CURRENT_WINDOW
            <= dt.datetime.fromisoformat(ack["reference_time"])
            <= latest
        ]
        last = max(covering, key=lambda ack: ack["ledger_index"]) if covering else None
        # El estado declarado ("en arreglo", "resuelto") cubre lo mismo que un reconocimiento.
        stated = [
            item
            for item in resolutions
            if item["domain"] == str(domain)
            and item["level"] == str(risk.level)
            and latest - CURRENT_WINDOW
            <= dt.datetime.fromisoformat(item["reference_time"])
            <= latest
        ]
        state = max(stated, key=lambda item: item["ledger_index"]) if stated else None
        dismissed = [
            item
            for item in dismissals
            if item["domain"] == str(domain)
            and item["level"] == str(risk.level)
            and latest - CURRENT_WINDOW
            <= dt.datetime.fromisoformat(item["reference_time"])
            <= latest
        ]
        dismissal = max(dismissed, key=lambda item: item["ledger_index"]) if dismissed else None
        if dismissal is not None and state is not None and (
            state["ledger_index"] > dismissal["ledger_index"]
        ):
            dismissal = None
        change = silencing.get(str(domain))
        # F.6.4: "Annunciation State (Inhibit, Suppress)" de cada evento. La alerta
        # silenciada sigue en la lista: deja de reclamar atencion, no de existir.
        annunciation = _silenced(change, risk.level, clock)
        silenced = change if annunciation != "normal" else None
        alerts.append(
            {
                "id": f"{domain}:{risk.level}",
                "domain": str(domain),
                "level": str(risk.level),
                "acknowledged": last is not None,
                "acknowledged_by": last["acknowledged_by"] if last else None,
                "acknowledgement_index": last["ledger_index"] if last else None,
                # Con que reglas se firmo cada decision, frente a las de hoy (§3.26 de
                # `record-integrity.md`): se lee del asiento y se dice; no se recalcula nada.
                "acknowledgement_rules": (
                    decided_with(last.get(RULES_VERSION_FIELD)) if last else None
                ),
                # Estados de Polaris `salud.py`: detectado → en_arreglo → resuelto.
                "resolution": (
                    {"state": state["state"], "note": state["note"],
                     "declared_by": state["declared_by"], "ledger_index": state["ledger_index"],
                     "rules": decided_with(state.get(RULES_VERSION_FIELD))}
                    if state else {"state": "detectado"}
                ),
                # Descartada por una persona, con su motivo; `None` si no lo está. La alerta
                # sigue aqui: descartar no la quita de la lista ni cambia su nivel.
                "dismissal": _dismissal_view(dismissal) if dismissal else None,
                "annunciation": annunciation,
                "silenced_until": silenced["until"] if silenced else None,
                "silenced_by": silenced["requested_by"] if silenced else None,
                "silenced_reason": silenced["reason"] if silenced else None,
            }
        )
    return alerts


# Prefijo con que el simulador firma sus lecturas (`simulator:<escenario>`).
_SIMULATOR_SOURCE = "simulator"


def _mission(settings: Settings, observations: Sequence[VitalObservation]) -> dict[str, Any]:
    """Origen del tiempo de mision y si lo que se analiza es simulado.

    NASA-STD-3001 Vol 2, F.4.2: *"Displays for different modes of operation (e.g.,
    test/sim mode vs. flight/mission mode) must be visually distinct."* Para que la
    interfaz lo cumpla tiene que saber el modo, y no puede deducirlo de otra cosa
    que de quien firmo las lecturas. Una mezcla se declara como tal: una lectura
    simulada entre datos reales no debe pasar por real, ni al reves.
    """
    sources = sorted({o.source for o in observations})
    simulated = [s for s in sources if s.split(":", 1)[0] == _SIMULATOR_SOURCE]
    if not simulated:
        mode = "mission"
    elif len(simulated) == len(sources):
        mode = "simulation"
    else:
        mode = "mixed"
    return {"start": settings.mission_start.isoformat(), "mode": mode, "sources": sources}
