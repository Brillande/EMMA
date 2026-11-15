# SPDX-License-Identifier: AGPL-3.0-or-later
"""Almacen append-only de observaciones, con auditoria encadenada.

Toda escritura pasa por el ledger de `core/ledger.py`. Eso convierte el requisito
de 21 CFR 11.10(e) —audit trail seguro, con marca de tiempo, que registre de
forma independiente las acciones que crean o modifican registros— en una
propiedad que el codigo **impone**, no en una promesa del documento de
cumplimiento.

No hay via publica para escribir una observacion sin auditarla: `record()` es la
unica entrada, y falla si no se le da una identidad firmante.

La cadena se persiste junto a los datos y se reconstruye al abrir el almacen, de
modo que `verify_integrity()` detecta manipulaciones hechas entre sesiones —
incluidas las que se hagan editando el fichero SQLite por fuera.

Licencia y origen (AGPL §5a): este fichero no carga la copia de Polaris; adapta a mano dos
patrones suyos (github.com/BeyondTheProtocol/polaris @ 7bf47257, el commit que se copió primero;
AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the Protocol»). De `tools/salida.py`, la
aprobación con `nonce`: en `sign_draft` la firma cita la huella SHA-256 del texto leído, no un
`nonce`. De `tools/decision_alto_riesgo.py`, el acta a dos voces: en `countersign_draft` las voces
son personas de la tripulación, no agentes, y el acta queda en el ledger. El disparador de alto
riesgo sí se llama en la copia, desde `app/decision_risk.py`. De Polaris son también, citados donde
se usan, los nombres de los estados de una alerta (`tools/salud.py`) y la regla del modo seguro
(`tools/codigo_rojo.py`).
"""

from __future__ import annotations

import base64
import binascii
import copy
import datetime as dt
import hashlib
import json
import threading
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    LargeBinary,
    String,
    Text,
    create_engine,
    event,
    select,
    type_coerce,
)
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool

from app.core import ground_notes as ground_note_rules
from app.core import help_requests as help_rules
from app.core import i18n
from app.core import inventory as inventory_rules
from app.core import link_sync as link_rules
from app.core import mission_history as history_rules
from app.core import mission_modes as mission_mode_rules
from app.core import mission_profile_changes as mission_profile_rules
from app.core import resources as resource_rules
from app.core.identities import action_counts
from app.core.ledger import (
    AMENDMENT_ENTRY_TYPE,
    MAX_JSON_DEPTH,
    REDACTION_ENTRY_TYPE,
    SALT_FIELD,
    Amendment,
    Anchor,
    HashChainLedger,
    Identity,
    KeyRegistry,
    LedgerEntry,
    MemoryMark,
    Redaction,
    RedactionAuthority,
    UntrustedSigner,
    VerificationResult,
    canonical_bytes,
    sha256_hex,
)
from app.countersign_rule import NOT_APPLICABLE, CountersignRefused, refusal
from app.decision_risk import trigger
from app.environment import systems as habitat_systems
from app.environment.habitat import MODULES, HabitatReading
from app.ingest import bindings as binding_rules
from app.ingest import location_anchors as anchor_rules
from app.ingest.codes import LAB_REPORT_ONLY, SELF_REPORTED_ONLY, ULTRASOUND_MEASURES, get
from app.ingest.fhir import (
    FULL_CONFIDENCE,
    Context,
    EvidenceContext,
    ObservationType,
    VitalObservation,
)
from app.volumes import contrast_phase as phase_rules

OBSERVATION_ENTRY_TYPE = "vital-observation"

# La version de las reglas con que se firmo una decision humana sobre una alerta o una
# contramedida (especificacion §12; `record-integrity.md` §3.26; decision del plan, 2026-10-31).
# La huella (`core/versioning.rules_version`) iba en el estado y en las instantaneas de
# proyeccion, no en estos asientos; y como la historia de alertas se recalcula con las reglas de
# hoy, no se podia saber con que reglas salio la alerta que alguien firmo. Es un campo OPCIONAL de
# los asientos de decision (reconocimiento, estado declarado, descarte y las tres acciones del
# seguimiento): lo pone la ruta al firmar, con la huella vigente, nunca el cliente; los asientos
# firmados antes no lo llevan y siguen verificandose. Este modulo no calcula la huella (no importa
# `versioning`, que importa el analisis): recibe el texto y lo guarda.
RULES_VERSION_FIELD = "rules_version"
_DECIDED_WITH_OPTIONAL = (RULES_VERSION_FIELD,)


def _decided_with(rules_version: str | None) -> dict[str, str]:
    """El campo opcional de la version, o nada: sin el, el asiento es el de antes del cambio."""
    if rules_version is None:
        return {}
    if not rules_version.strip():
        raise ValueError("la versión de las reglas, si se firma, no va vacía")
    return {RULES_VERSION_FIELD: rules_version}


# Asiento que registra que alguien reconocio una alerta. No es un dato clinico: no
# entra en `observations` ni en el analisis. Existe porque reconocer una alerta es
# una accion con consecuencias —detiene el parpadeo— y una accion asi tiene que
# quedar registrada, firmada y con su autor, como cualquier escritura del sistema.
ACKNOWLEDGEMENT_ENTRY_TYPE = "alert-acknowledgement"

_ACKNOWLEDGEMENT_FIELDS = ("subject", "domain", "level", "reference_time", "acknowledged_by")

# Lo que pasa con una alerta después de reconocerla. Estados de Polaris `salud.py` (el acuse
# "visto, en ello"): `detectado` es la alerta sin más; `en_arreglo` alguien se está ocupando;
# `resuelto` quien se ocupaba lo da por resuelto. No cambia el cálculo: una alerta "resuelta"
# cuyos datos siguen fuera de rango sigue en la lista, y se ve que sigue.
RESOLUTION_ENTRY_TYPE = "alert-resolution"
RESOLUTION_STATES = ("en_arreglo", "resuelto")
_RESOLUTION_FIELDS = (
    "subject", "domain", "level", "reference_time", "state", "note", "declared_by",
)

# Una persona dice que una alerta concreta no le parece real o ya la explica algo (la «HUMAN
# DECISION / Accept / Dismiss / Investigate» de la conversación de ideación, L161-162; decisión
# del usuario, 2026-10-26). Es un tipo aparte de `alert-resolution` porque lleva un motivo de un
# vocabulario cerrado, y un campo nuevo en aquel tipo dejaría por mal formados los asientos ya
# firmados. No cambia el cálculo ni el anuncio: la alerta sigue en la lista, marcada como
# descartada, y una alerta posterior del mismo dominio no llega descartada (`record-integrity.md`
# §3.20 bis). La palabra de cada motivo es de aquí, no de la interfaz.
DISMISSAL_ENTRY_TYPE = "alert-dismissal"
DISMISSAL_REASONS: dict[str, str] = {
    "sensor_artifact": "artefacto del sensor",
    "explained_by_context": "explicada por el contexto",
    "other": "otro motivo",
}
# El inglés de la palabra que se enseña, registrado para quien la sirve con `i18n.loc`. El asiento
# firmado lleva la clave del motivo, nunca la palabra: no cambia ningún byte firmado.
i18n.en_many({
    DISMISSAL_REASONS["sensor_artifact"]: "sensor artifact",
    DISMISSAL_REASONS["explained_by_context"]: "explained by the context",
    DISMISSAL_REASONS["other"]: "other reason",
})
# El motivo que no dice nada por sí mismo exige que la nota lo diga.
DISMISSAL_NOTE_REQUIRED = ("other",)
_DISMISSAL_FIELDS = (
    "subject", "domain", "level", "reference_time", "reason", "note", "declared_by",
)


def dismissal_problem(reason: str, note: str, declared_by: str) -> str | None:
    """Por qué no se puede firmar (o no se respeta) un descarte; `None` si se puede.

    Una sola regla para quien escribe (`record_alert_dismissal`) y para quien lee lo firmado
    (`api.routes._acceptable_dismissal`): un descarte firmado por fuera de la API no vale más que
    uno firmado por ella.
    """
    if reason not in DISMISSAL_REASONS:
        return f"motivo de descarte desconocido: {reason!r}; uno de {tuple(DISMISSAL_REASONS)}"
    if reason in DISMISSAL_NOTE_REQUIRED and not note.strip():
        return "descartar una alerta por otro motivo exige decir cuál en la nota"
    if not any(char.isalpha() for char in declared_by):
        return "una alerta la descarta una persona con nombre"
    return None


# Telemetria de cabina (especificacion del equipo §3, HabitatState). Pasa por el ledger como
# toda observacion (invariante 4), pero no es una lectura de una persona: no entra en
# `observations` ni en el analisis fisiologico. La interpreta `environment/habitat.py`.
HABITAT_ENTRY_TYPE = "habitat-reading"

# Proyeccion firmada el dia que se hace, para comprobarla cuando llegue su horizonte
# (`analysis/forecast_check.py`). La firma el propio sistema; no es un dato clinico.
SNAPSHOT_ENTRY_TYPE = "prediction-snapshot"
_SNAPSHOT_FIELDS = (
    "subject", "key", "made_at", "horizon_at", "anchor_value", "projected_change",
    "projected_change_low", "projected_change_high", "model_version", "rules_version",
)

# Perfil declarado de un tripulante (especificacion §3, Astronaut): misiones previas y dosis de
# carrera previa. Lo declara una persona; alimenta la escala de carrera de la radiacion.
PROFILE_ENTRY_TYPE = "crew-profile"
_PROFILE_FIELDS = ("subject", "prior_missions", "prior_career_dose_msv", "declared_by")

# Historial misión a misión de un tripulante (especificación §3, Astronaut `mission_history`;
# decisión del usuario, 2026-10-22): nombre, fechas y dosis de cada misión previa, declarado por
# una persona. Es un asiento APARTE del perfil, no un campo más de `crew-profile`: los perfiles ya
# firmados siguen siendo los mismos asientos, y la dosis de carrera (`analysis/radiation.py`) sigue
# leyendo solo `prior_career_dose_msv` del perfil. El historial no la sustituye ni la corrige: si
# su suma no casa con ella, se dice (`core/mission_history.describe`). `missions` es la lista
# entera, como texto JSON con todos sus valores también como texto (§3.8 de `record-integrity.md`:
# todos los campos como texto); vale el último declarado, como el perfil.
MISSION_HISTORY_ENTRY_TYPE = "crew-mission-history"
_MISSION_HISTORY_FIELDS = ("subject", "missions", "declared_by")

# Identidad del tripulante (nombre de pila, apellidos, fecha de nacimiento), aparte del perfil
# para que el perfil siga sin datos personales y esto se pueda redactar solo. La usa el cotejo de
# identidad de los informes (`reports/identity.py`, de Polaris `identidad_paciente.py`).
CREW_IDENTITY_ENTRY_TYPE = "crew-identity"
# Sexo declarado del tripulante (decisión del usuario, 2026-11-14, lote «ciclo»: revierte la
# §5.36.19 de `hmi-state-of-the-art.md`). Un tipo APARTE, ni un campo de `crew-profile` ni de
# `crew-identity`: un campo obligatorio más en `_PROFILE_FIELDS` dejaría por mal formados los
# perfiles ya firmados (`_actions`), y en un asiento propio se puede redactar solo, sin tocar el
# perfil ni la identidad. Lo da el propio tripulante (`declared_by`); sin asiento vigente, la API
# dice «no declarado», nunca un valor por omisión. Solo lo lee `api/`: ninguna regla de
# `analysis/`, `advisor/` ni `ingest/` (lo vigila `test_no_rule_of_emma_reads_sex_or_age`).
CREW_SEX_ENTRY_TYPE = "crew-sex"
CREW_SEX_VALUES = ("female", "male")
_CREW_SEX_FIELDS = ("subject", "sex", "declared_by")
# Modo seguro (regla de Polaris `codigo_rojo.py`: lo activa cualquiera con motivo, lo levanta solo
# una persona). En EMMA corta la salida a internet (`core/egress.py`); la IA es local y sigue.
SAFE_MODE_ENTRY_TYPE = "safe-mode"
SAFE_MODE_SUBJECT = "sistema"
_SAFE_MODE_FIELDS = ("subject", "active", "reason", "declared_by")

# Nivel de misión (desconexión progresiva, `core/mission_modes.py`): qué medidas se siguen
# esperando cuando escasean los recursos. Bajar lo firma cualquiera con nombre y motivo, y puede
# saltar niveles; subir, una persona con nombre, un nivel cada vez. No toca la ingesta, el
# análisis, las alertas ni el modo seguro. Si cita la energía o las comunicaciones, se firma el
# estado declarado que constaba al firmar (`cited_state`): opcionales, solo con cita.
MISSION_MODE_ENTRY_TYPE = "mission-mode"
MISSION_MODE_SUBJECT = "sistema"
_MISSION_MODE_FIELDS = ("subject", "level", "reason", "declared_by")
_MISSION_MODE_OPTIONAL = ("cited_system", "cited_state")

# Entorno de la misión (`core/mission_profile_changes.py`): qué perfil de misión se describe. La
# configuración da el de partida; cada cambio lo firma una persona con nombre, con motivo
# opcional, y lleva el entorno que dejaba atrás (`previous`). Descriptivo: no toca la ingesta, el
# análisis, el riesgo ni las alertas.
MISSION_PROFILE_ENTRY_TYPE = "mission-profile"
MISSION_PROFILE_SUBJECT = "sistema"
_MISSION_PROFILE_FIELDS = ("subject", "profile", "previous", "reason", "declared_by")

# La época de cada almacén abierto (§5.38.13): la versión del modo seguro cuenta asientos de UN
# almacén y vuelve a 0 con otro (cambiar de escenario lo sustituye, `routes.simulate`; reiniciar el
# backend abre uno nuevo en memoria). La consola compara primero la época y luego la versión: sin
# ella, tras un cambio de almacén descartaba como viejo todo lo del nuevo. Microsegundos desde
# 1970 (caben enteros en el `number` de JavaScript), y estrictamente crecientes en el proceso.
_epoch_lock = threading.Lock()
_last_epoch = 0


def _next_epoch() -> int:
    global _last_epoch
    with _epoch_lock:
        _last_epoch = max(_last_epoch + 1, time.time_ns() // 1000)
        return _last_epoch


_IDENTITY_FIELDS = ("subject", "given_name", "surnames", "birth_date", "declared_by")

# Evento del plan de mision (especificacion §3, MissionContext): EVA, bloque de trabajo o
# ubicacion ("location": en que modulo esta el tripulante en ese intervalo). La ubicacion lleva
# ademas `module`, que solo existe en ese tipo: por eso es un campo opcional al leer y no uno
# mas de `_MISSION_EVENT_FIELDS`, que dejaria por mal formados los asientos ya firmados.
# Desde la decimoctava ronda (U4), tambien el cambio de turno o de horario de sueño ("shift"):
# los mismos campos que una EVA, sin ninguno nuevo; que es y en que se distingue de un bloque de
# trabajo lo dice `core/shift.py`.
MISSION_EVENT_ENTRY_TYPE = "mission-event"
LOCATION_EVENT_KIND = "location"
SHIFT_EVENT_KIND = "shift"
MISSION_EVENT_KINDS = ("eva", "workload", LOCATION_EVENT_KIND, SHIFT_EVENT_KIND)
_MISSION_EVENT_FIELDS = ("subject", "kind", "start", "end", "label", "declared_by")
_MISSION_EVENT_OPTIONAL = ("module",)

# Revision humana de una hipotesis de causa compartida (especificacion §7: "confirmacion
# humana"). Es de la tripulacion, no de un tripulante: su sujeto es `CREW_SUBJECT`.
HYPOTHESIS_ENTRY_TYPE = "hypothesis-review"
HYPOTHESIS_DECISIONS = ("confirmed", "discarded")
CREW_SUBJECT = "tripulacion"
_HYPOTHESIS_FIELDS = (
    "subject", "decision", "parameter", "excursion_start", "reason", "decided_by",
)

# Estado de un sistema del habitat DECLARADO por una persona (especificacion §3, HabitatState
# `system_status`). EMMA no lee el estado de ningun sistema: esto es lo que alguien dijo en la
# consola. No es de un tripulante: su sujeto es `SYSTEM_STATUS_SUBJECT`. No entra en
# `observations` ni en el analisis. `module` solo lo lleva la declaracion que habla de un modulo.
SYSTEM_STATUS_ENTRY_TYPE = "system-status"
SYSTEM_STATUS_SUBJECT = "habitat"
_SYSTEM_STATUS_FIELDS = ("subject", "system", "state", "at", "note", "declared_by")
_SYSTEM_STATUS_OPTIONAL = ("module",)

# Vinculo sensor-tripulante DECLARADO por una persona (especificacion §3, Astronaut `sensor
# bindings`). EMMA no comprueba quien lleva puesto un dispositivo: esto es lo que alguien dijo en
# la consola (`ingest/bindings.py`). Es de la tripulacion: su sujeto es `CREW_SUBJECT`. `device`
# solo lo lleva el vinculo de un identificador concreto, y `crew` solo la declaracion que vincula
# (la que retira no nombra a nadie). No entra en `observations` ni en el analisis.
SENSOR_BINDING_ENTRY_TYPE = "sensor-binding"
_SENSOR_BINDING_FIELDS = ("subject", "source", "action", "since", "note", "declared_by")
_SENSOR_BINDING_OPTIONAL = ("device", "crew")

# Base de datos de Marplanner (`marplanner/`, decision del usuario 2026-11-12): su SQLite deja de
# ser un fichero y pasa a ser este ledger. Cada transaccion suya es UN asiento con el changeset de
# SQLite (sesiones de `node:sqlite`) en base64 y su huella; Marplanner reconstruye su base en
# memoria reproduciendolos en orden. No es de un tripulante ni entra en el analisis: su sujeto es
# `PLANNER_SUBJECT`. No hay borrado: un cambio se deshace con otro changeset, como en la app.
PLANNER_ENTRY_TYPE = "planner-changeset"
PLANNER_SUBJECT = "planner"
_PLANNER_FIELDS = ("subject", "changeset", "sha256", "written_by")
# Tope de un changeset: la siembra inicial de Marplanner cabe de sobra; algo mayor es un error.
PLANNER_MAX_CHANGESET_BYTES = 8 * 1024 * 1024


class PlannerConflict(ValueError):
    """Quien escribe no ha visto todos los changesets anteriores: su base va atrasada."""


# Ancla de modulo DECLARADA por una persona (`analysis/location.py`): un emisor fijo de la nave
# que una persona dice que esta en un modulo de la lista desde un instante. Es del habitat: su
# sujeto es `ANCHOR_SUBJECT`. No hay borrado: se corrige declarando de nuevo y vale la ultima.
LOCATION_ANCHOR_ENTRY_TYPE = "location-anchor"
ANCHOR_SUBJECT = "habitat"
_LOCATION_ANCHOR_FIELDS = ("subject", "anchor_id", "module", "since", "declared_by")

# Lo que oyo el receptor de un tripulante de las anclas de modulo: UN asiento por lote, firmado
# por `location-anchors` (invariante 4). `sightings` es una lista de `{anchor_id, rssi_dbm, at}`;
# `device` solo si quien envia lo pone. No entra en `observations` ni en el analisis
# fisiologico. Si cuenta como registro real para un cambio de escenario (`_CLINICAL_ENTRY_TYPES`).
LOCATION_SIGHTINGS_ENTRY_TYPE = "location-sightings"

# Disponibilidad de un recurso de a bordo DECLARADA por una persona (especificacion §3,
# MissionContext `available_resources`). EMMA no lleva inventario: esto es lo que alguien dijo en
# la consola (`core/resources.py`), de un recurso del vocabulario cerrado y sin cantidades. Es de
# la mision, no de un tripulante: su sujeto es `RESOURCE_SUBJECT`. No entra en `observations` ni
# en el analisis.
RESOURCE_ENTRY_TYPE = "resource-availability"
RESOURCE_SUBJECT = "mision"
_RESOURCE_FIELDS = ("subject", "resource", "state", "since", "note", "declared_by")

# Inventario de a bordo CONTADO y declarado por una persona (`core/inventory.py`, decision del
# usuario 2026-11-14): un recuento por articulo, con cantidades, y el proximo abastecimiento. Es
# de la mision (`inventory.SUBJECT`). Todos los campos como texto; los opcionales solo si se
# declararon. No entra en `observations` ni en el analisis, los niveles o las alertas.
INVENTORY_COUNT_ENTRY_TYPE = "inventory-count"
INVENTORY_RESUPPLY_ENTRY_TYPE = "inventory-resupply"

# Decision humana sobre una contramedida recomendada: adoptarla, cerrar su seguimiento o dejar
# dicho, con motivo, que no se adopta (especificacion del equipo §2, §7, §14). No es un dato
# clinico: no entra en `observations` ni
# en el analisis. El estado del seguimiento se deriva de estos asientos (`advisor/followup.py`).
FOLLOWUP_ENTRY_TYPE = "countermeasure-followup"
_FOLLOWUP_FIELDS = (
    "subject", "action", "countermeasure_id", "domain", "level", "reference_time",
    "decided_by", "reason", "adoption_index",
)
# Solo en un cierre, y solo desde 2026-10-13: el nivel del dominio en el estado del instante en
# que se cerro, y ese instante. Son una COPIA de lo que el motor ya habia calculado, para que la
# respuesta previa compare con el dia del cierre y no con hoy; no deciden nada. Opcionales: los
# cierres firmados antes no los llevan y siguen verificandose (`record-integrity.md` §3.15 ter).
_FOLLOWUP_OPTIONAL = ("level_at_close", "closed_reference_time")

# Asiento que cambia si se ANUNCIAN las alertas de un dominio: suprimirlas, inhibirlas
# o volver a habilitarlas (NASA-STD-3001 Vol 2, F.6.4). Silenciar una alarma clinica es
# la decision mas delicada de la interfaz: por eso deja asiento firmado con su motivo.
ANNUNCIATION_ENTRY_TYPE = "alert-annunciation"
ANNUNCIATION_ACTIONS = ("suppress", "inhibit", "enable")

_ANNUNCIATION_FIELDS = (
    "subject", "action", "domain", "level", "reference_time", "until", "reason", "requested_by",
)

# Asiento de un estudio de imagen (una ecografia). El ledger solo admite JSON, asi que el
# binario no va en el asiento: va en `imaging_blobs`, y el asiento firma su SHA-256. Lo que
# se protege es el binario entero, no una descripcion de el: cambiar un pixel cambia el hash.
IMAGING_STUDY_ENTRY_TYPE = "imaging-study"
# Informe clínico escaneado (papel o foto) con su OCR local (`app/reports/`, de Polaris).
SCANNED_REPORT_ENTRY_TYPE = "scanned-report"
# Volumen TAC/RM (NIfTI) y su segmentación automática (`app/volumes/`, visor 3D de Polaris). La
# segmentación es un asiento derivado: sus ficheros del visor (volumen recortado, etiquetas,
# mallas) van como binario firmado, y su resumen, sin validar, en el asiento.
VOLUME_STUDY_ENTRY_TYPE = "volume-study"
VOLUME_SEGMENTATION_ENTRY_TYPE = "volume-segmentation"
# Asientos que guardan un binario firmado por su hash: se coteja en cada entrega y al verificar.
BLOB_ENTRY_TYPES = (
    IMAGING_STUDY_ENTRY_TYPE, SCANNED_REPORT_ENTRY_TYPE, VOLUME_STUDY_ENTRY_TYPE,
    VOLUME_SEGMENTATION_ENTRY_TYPE,
)
# Fase de contraste de un TAC DECLARADA por una persona (`volumes/contrast_phase.py`). EMMA no la
# propone ni la mira en la imagen: es lo que alguien dijo en la consola, de un vocabulario
# cerrado. Asiento aparte: el del estudio no se toca. Cita el estudio por su indice y por la
# huella de su volumen, y copia su sujeto. No es una lectura: no entra en `observations` ni en
# el analisis, y solo acompana a la densidad, que es descriptiva.
VOLUME_PHASE_ENTRY_TYPE = "volume-contrast-phase"
_VOLUME_PHASE_FIELDS = ("subject", "study_sha256", "phase", "at", "note", "declared_by")
# Lo que se redacta con un estudio volumetrico, en el mismo `commit` (`ObservationStore.redact`):
# la fase declarada lleva el nombre de quien hablo de el, y la segmentacion lleva en su binario
# firmado un volumen recortado del estudio, sus pixeles. Sin esto, ambos seguian ahi despues de
# quitar el estudio (decision del usuario, 2026-10-15, para la segmentacion).
_CARRIED_WITH_STUDY = (VOLUME_PHASE_ENTRY_TYPE, VOLUME_SEGMENTATION_ENTRY_TYPE)

# Asiento que dice de donde sale una medida ecografica: que estudio, que puntos, con que
# metodo. El valor no va aqui sino en la lectura (`vital-observation`) que se escribe en el
# mismo `commit`: asi redactar la lectura quita el dato clinico sin dejar una copia.
IMAGING_MEASUREMENT_ENTRY_TYPE = "imaging-measurement"

# Signos que el operador anota en un estudio (pulmon, FAST, higado) y su lista de calidad.
# Son observaciones de una persona sobre una imagen firmada, no lecturas: no entran en el
# analisis ni en la linea base.
IMAGING_FINDINGS_ENTRY_TYPE = "imaging-findings"

# Borrador de interpretacion redactado por el modelo local, y la firma humana que lo acepta
# o lo rechaza. Ninguno de los dos es una lectura: no entran en el analisis.
DRAFT_ENTRY_TYPE = "draft-interpretation"
DRAFT_SIGNOFF_ENTRY_TYPE = "draft-signoff"
# Segunda firma de una decisión de alto riesgo (`app/decision_risk.py`, patrón de Polaris).
DRAFT_COUNTERSIGN_ENTRY_TYPE = "draft-countersign"
DRAFT_DECISIONS = ("accepted", "rejected")

# Informe de dolor del tripulante: que zonas, con que intensidad y de que tipo. La cifra
# que entra en el analisis (la intensidad maxima) va en la lectura `vital-observation` del
# mismo `commit`, y este asiento la cita por indice, como la procedencia de una medida
# ecografica. Redactar la lectura retira el informe entero: no queda un dolor sin cifra.
PAIN_REPORT_ENTRY_TYPE = "pain-report"

# Confirmación humana de una cifra leída en una analítica escaneada (`app/reports/labs.py`). La
# cifra va en la lectura `vital-observation` del mismo `commit`; este asiento cita el informe y
# qué lectura suya es, y quién la confirmó. Una lectura se confirma una sola vez.
LAB_CONFIRMATION_ENTRY_TYPE = "lab-confirmation"

# Nota firmada en Tierra para la tripulación (`core/ground_notes.py`; decisión del usuario,
# 2026-10-26; `record-integrity.md` §3.25). La única escritura que sube: informa o pregunta, nunca
# prescribe. No es una lectura: no entra en `observations` ni en el análisis, y no cambia ningún
# nivel, alerta ni `rules_version`. `subject` es un tripulante o `CREW_SUBJECT` (toda la
# tripulación). La hora de firma es la del asiento (`recorded`): a bordo se ve un tiempo de luz
# después.
GROUND_NOTE_ENTRY_TYPE = "ground-note"
_GROUND_NOTE_FIELDS = ("subject", "kind", "text", "signed_by")

# Petición de ayuda urgente firmada a bordo, y su cierre (`core/help_requests.py`; decisión del
# usuario, 2026-11-14; `record-integrity.md` §3.32). La tripulación la ve al firmarse; Tierra, un
# tiempo de luz después. `at` es el instante de la misión en que se pidió (el de los datos), con el
# que se busca dónde estaba cada tripulante. No es una lectura ni una alerta del motor: no entra en
# `observations` ni en el análisis, y no cambia ningún nivel ni `rules_version`. El cierre cita la
# petición por índice (`request_index`, en texto) y no la borra.
HELP_REQUEST_ENTRY_TYPE = "help-request"
_HELP_REQUEST_FIELDS = ("subject", "signed_by", "reason", "at")
HELP_CLOSE_ENTRY_TYPE = "help-request-close"
_HELP_CLOSE_FIELDS = ("subject", "request_index", "signed_by")

# Enlace con Tierra SIMULADO (`core/link_sync.py`, `record-integrity.md` §3.29): una persona declara
# a bordo «caído» o «restablecido» desde un instante (`at`, el de los datos). Solo lo leen el corte
# de Tierra y la cola de lo pendiente; no es la declaración del sistema Comunicaciones, que sigue
# siendo solo texto. No entra en `observations` ni en el análisis.
LINK_ENTRY_TYPE = "simulated-link"
LINK_SUBJECT = "sistema"
_LINK_FIELDS = ("subject", "state", "at", "note", "declared_by")

# Discrepancia del cálculo local (SPICE) con la efeméride de JPL Horizons en caché de un mismo día,
# por encima del error declarado (`environment/comms_status.py`, `record-integrity.md` §3.30). La
# firma el propio sistema (`emma-ephemeris`), como mucho una vez por día de efeméride, objetivo y
# observador. No es una observación clínica: no entra en `observations`, ni en el análisis, ni en
# el riesgo ni en las alertas.
EPHEMERIS_DISCREPANCY_ENTRY_TYPE = "ephemeris-discrepancy"
EPHEMERIS_DISCREPANCY_SUBJECT = "sistema"
EPHEMERIS_DISCREPANCY_FIELDS = (
    "subject", "epoch", "target", "observer", "local", "reference", "reference_fetched_at",
    "one_way_seconds_difference", "elongation_deg_difference", "one_way_seconds_tolerance",
    "elongation_deg_tolerance", "used", "text",
)

# Los tipos cuyo instante es el de los datos (`effective`), no la hora de su firma: lo que la
# consola de Tierra corta por su hora (`query`, `habitat_readings`).
_EFFECTIVE_ENTRY_TYPES = frozenset({OBSERVATION_ENTRY_TYPE, HABITAT_ENTRY_TYPE})


class LabReadingConflict(ValueError):
    """La lectura no se puede confirmar en el estado del informe (ya confirmada, ajena)."""


class SafeModeConflict(ValueError):
    """El cambio pide el estado que ya tiene el modo seguro: un conflicto, no un dato malo.

    Es `ValueError` para quien ya captura los motivos de `record_safe_mode`; la API la separa de
    los demás (activar sin motivo, levantar sin nombre, lo que el ledger no puede firmar), que
    son del dato y van con 422, como en el modo de misión y el enlace.
    """


class AmendmentMismatch(ValueError):
    """La correccion no es del indicador de la lectura que corrige: un dato malo, no un conflicto.

    Es `ValueError` para quien ya captura los motivos de `amend`; la API la separa de los
    demas (409) y responde 422, como a una unidad equivocada.
    """


# Tipos de asiento que son registros clinicos de una fuente, reales o simulados.
_CLINICAL_ENTRY_TYPES = (
    OBSERVATION_ENTRY_TYPE, AMENDMENT_ENTRY_TYPE, IMAGING_STUDY_ENTRY_TYPE,
    SCANNED_REPORT_ENTRY_TYPE, VOLUME_STUDY_ENTRY_TYPE,
    # Telemetria real de cabina tambien impide sustituir el almacen por un escenario.
    HABITAT_ENTRY_TYPE,
    # Y lo que oyo de las anclas de modulo el receptor de un tripulante: el simulador no lo
    # firma nunca, asi que siempre es real (2026-11-10).
    LOCATION_SIGHTINGS_ENTRY_TYPE,
)


def _sighting_row(row: Any) -> bool:
    """Si una lectura de ancla leida del ledger tiene la forma con que se firma."""
    if not isinstance(row, dict) or not isinstance(row.get("anchor_id"), str):
        return False
    rssi = row.get("rssi_dbm")
    if isinstance(rssi, bool) or not isinstance(rssi, (int, float)):
        return False
    if not isinstance(row.get("at"), str):
        return False
    try:
        return dt.datetime.fromisoformat(row["at"]).tzinfo is not None
    except ValueError:
        return False


def _utc_text(moment: dt.datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("los instantes de una acción deben llevar zona horaria")
    return _as_utc(moment).isoformat()


class Base(DeclarativeBase):
    pass


class ObservationRow(Base):
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String(64), index=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[float] = mapped_column(Float)
    effective: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(128))
    # CONTEXTO Y CONFIANZA SE PERDIAN AL PERSISTIR.
    #
    # Sin estas dos columnas, toda lectura que pasaba por la base volvia como
    # `unknown / 1.0`. Eso apagaba en silencio los dos controles que mas bajaron
    # la falsa alarma: la estratificacion por contexto (comparar el pulso de
    # sueno contra la base de sueno, no contra la de vigilia) y el tope de
    # severidad por baja confianza (una lectura sin contacto de sensor no puede
    # disparar una alerta grave).
    #
    # Funcionaban en las listas en memoria del simulador y del banco de
    # validacion, y **no funcionaban por el camino real** de la API. Las cifras
    # se median sobre un motor que el sistema desplegado no ejecutaba.
    context: Mapped[str] = mapped_column(String(16), default=Context.UNKNOWN.value)
    confidence: Mapped[float] = mapped_column(Float, default=FULL_CONFIDENCE)
    ledger_index: Mapped[int] = mapped_column(Integer, unique=True)


class LedgerRow(Base):
    __tablename__ = "ledger_entries"

    index: Mapped[int] = mapped_column(Integer, primary_key=True)
    recorded: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    entry_type: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    prev_hash: Mapped[str] = mapped_column(String(64))
    signer: Mapped[str] = mapped_column(String(64))
    signer_public_key: Mapped[str] = mapped_column(String(64))
    signature: Mapped[str] = mapped_column(String(128))
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    redacted: Mapped[bool] = mapped_column(Boolean, default=False)


class TrustedKeyRow(Base):
    """Registro de claves de confianza, en su propia tabla.

    NO se reconstruye a partir de los asientos: si se derivara de ellos, reescribir
    todas las entradas de una fuente con una clave nueva reescribiria tambien su
    confianza, que es justo el ataque que el registro impide. Quien pueda editar
    esta tabla y la cadena a la vez puede falsificar la parte no anclada; la anclada
    no (ver `compliance/record-integrity.md` §3.2).
    """

    __tablename__ = "trusted_keys"

    identity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    public_key: Mapped[str] = mapped_column(String(64))


class ImagingBlobRow(Base):
    """El binario de un estudio de imagen, en la misma base que su asiento.

    En la misma base y no en ficheros sueltos por tres motivos: asiento y binario entran en
    un solo `commit` —no puede quedar un asiento que apunte a un fichero que no llego a
    escribirse—; funciona igual con la base en memoria; y redactar borra el binario con el
    mismo `secure_delete` que borra el resto del contenido clinico.
    """

    __tablename__ = "imaging_blobs"

    ledger_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64))
    data: Mapped[bytes] = mapped_column(LargeBinary)


def _to_payload(observation: VitalObservation) -> dict[str, Any]:
    return {
        "subject": observation.subject,
        "key": observation.key,
        "value": observation.value,
        "effective": observation.effective.isoformat(),
        "source": observation.source,
        # La confianza cambia como se interpreta la lectura, asi que forma parte
        # del registro clinico, no es metadato de transporte. Un asiento de
        # auditoria que la omite no reproduce la decision que se tomo con ella.
        "context": observation.context.value,
        "confidence": observation.confidence,
        # Que clase de afirmacion es y en que entorno se obtuvo (especificacion §2,
        # §14). Son parte del registro: una dosis inferida que el ledger guardara
        # como si fuera medida reproduciria una decision distinta de la tomada.
        "observation_type": observation.observation_type.value,
        "evidence_context": observation.evidence.value,
        **({"model_version": observation.model_version} if observation.model_version else {}),
        # El dispositivo que la envio, SOLO si quien envia lo puso (`record-integrity.md` §3.14
        # bis). Sin el no se escribe la clave: una lectura sin dispositivo produce los mismos
        # bytes canonicos, y por tanto el mismo hash, que antes de existir el campo.
        **({"device": observation.device} if observation.device is not None else {}),
        # Quien tecleo el valor en la consola, SOLO si lo anoto una persona (§3.14 ter). Misma
        # regla que `device`: sin anotador no se escribe la clave y los bytes son los de antes.
        **(
            {"recorded_by": observation.recorded_by}
            if observation.recorded_by is not None else {}
        ),
        # De qué alimento es una valoración de la comida, SOLO si lo lleva (§3.14 quinquies).
        # Misma regla: sin alimento no se escribe la clave y los bytes son los de antes.
        **({"food": observation.food} if observation.food is not None else {}),
    }


class TamperedRecordError(RuntimeError):
    """Una lectura cuyo contenido ya no coincide con su hash firmado.

    Se lanza en vez de devolverla: entregar al motor un dato que no respalda
    ninguna firma es exactamente lo que la cadena existe para impedir.
    """


def _from_payload(payload: dict[str, Any], effective: dt.datetime) -> VitalObservation:
    return VitalObservation(
        code=get(payload["key"]),
        value=payload["value"],
        effective=effective,
        subject=payload["subject"],
        source=payload["source"],
        # Asientos anteriores a que el payload llevara contexto y confianza.
        context=Context(payload.get("context", Context.UNKNOWN.value)),
        confidence=payload.get("confidence", FULL_CONFIDENCE),
        # Asientos anteriores a la especificacion del equipo: eran todos medidas, y su
        # contexto se deduce de la fuente como entonces (`evidence_context_for`).
        observation_type=ObservationType(
            payload.get("observation_type", ObservationType.MEASURED.value)
        ),
        evidence_context=(
            EvidenceContext(payload["evidence_context"])
            if "evidence_context" in payload
            else None
        ),
        model_version=payload.get("model_version"),
        # Asientos anteriores al campo, y toda lectura sin dispositivo: no lo llevan.
        device=payload.get("device"),
        # Idem: lo anterior al campo y lo que no anoto una persona no lo llevan.
        recorded_by=payload.get("recorded_by"),
        # Idem: lo anterior al campo y toda lectura que no es la valoración de un alimento.
        food=payload.get("food"),
    )


def _ledger_row(entry: LedgerEntry) -> LedgerRow:
    return LedgerRow(
        index=entry.index,
        recorded=entry.recorded,
        entry_type=entry.entry_type,
        content_hash=entry.content_hash,
        prev_hash=entry.prev_hash,
        signer=entry.signer,
        signer_public_key=entry.signer_public_key,
        signature=entry.signature,
        # `is not None`, no veracidad: un payload vacio `{}` se guardaba como NULL
        # y al recargar parecia un contenido suprimido.
        payload=json.dumps(entry.payload) if entry.payload is not None else None,
        redacted=entry.redacted,
    )


def _trusted_key_row(identity: Identity) -> TrustedKeyRow:
    return TrustedKeyRow(identity_id=identity.identity_id, public_key=identity.public_key_hex)


def _shown(value: Any) -> Any:
    """Un valor tal cual si es JSON; si no —un BLOB metido en la base—, su repr.

    Un texto con un sustituto UTF-16 suelto es un `str`, pero no se puede codificar:
    tumbaba `/api/audit` al serializar la respuesta. Se muestra escapado.
    """
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return ascii(value)
        return value
    return value if value is None or isinstance(value, (int, float, bool)) else repr(value)


def _audit_view(entry: LedgerEntry) -> dict[str, Any]:
    """Un asiento legible. Tiene que poder mostrarse aunque este manipulado: es
    justo entonces cuando hace falta verlo, y un 500 en `/api/audit` lo impedia."""
    view: dict[str, Any] = {
        "index": _shown(entry.index),
        "recorded": entry.recorded.isoformat(),
        "entry_type": _shown(entry.entry_type),
        "signer": _shown(entry.signer),
        "content_hash": _shown(entry.content_hash),
        "redacted": _shown(entry.redacted),
    }
    # Una lapida dice que se quito, por que y a peticion de quien: lo que ISO 27789
    # pide de cada accion sobre la historia clinica.
    if entry.entry_type == REDACTION_ENTRY_TYPE and isinstance(entry.payload, dict):
        view["redaction"] = {
            field: _shown(entry.payload.get(field))
            for field in ("target_index", "reason", "requested_by")
        }
    # Una enmienda dice que corrige, por que y quien: lo mismo que la lapida, pero de
    # una correccion que no borro nada. Sin esto, la auditoria mostraria un asiento mas
    # sin decir que version del dato deja de estar vigente.
    if entry.entry_type == AMENDMENT_ENTRY_TYPE and isinstance(entry.payload, dict):
        view["amendment"] = {
            field: _shown(entry.payload.get(field))
            for field in ("target_index", "reason", "amended_by")
        }
    return view


def _reading_payload(entry: LedgerEntry) -> Any:
    """El dato clinico que un asiento pone en circulacion, o `None` si no pone ninguno.

    Una observacion aporta el suyo; una enmienda, el de su correccion. Lo que devuelve
    no se supone bien formado: si viene de un asiento manipulado, quien lo use tiene que
    tratarlo como sospechoso —en `query()`, un 409 y no un 500—.
    """
    payload = entry.payload
    if payload is None:
        return None
    if entry.entry_type == OBSERVATION_ENTRY_TYPE:
        return payload
    if entry.entry_type == AMENDMENT_ENTRY_TYPE:
        return payload.get("replacement") if isinstance(payload, dict) else None
    return None


# Instante de un asiento cuya fecha no se pudo leer. Su firma no casara con el, y la
# verificacion senalara el asiento en vez de impedir que el almacen abra.
_UNREADABLE_MOMENT = dt.datetime.min.replace(tzinfo=dt.UTC)


def _loaded_recorded(raw: Any) -> dt.datetime:
    try:
        return _as_utc(dt.datetime.fromisoformat(raw))
    except (TypeError, ValueError):
        return _UNREADABLE_MOMENT


def _loaded_payload(raw: Any) -> Any:
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, RecursionError):
        # Un contenido que no casa con ningun hash: falla en su asiento.
        return {"_ilegible": repr(raw)[:200]}
    # Anidado mas alla del limite, agotaba la pila al copiarlo, mostrarlo o verificarlo.
    if _nesting_exceeds(payload, MAX_JSON_DEPTH):
        return {"_ilegible": "anidamiento excesivo"}
    return payload


def _nesting_exceeds(value: Any, limit: int) -> bool:
    """Profundidad de un JSON sin recursion: justo lo que no se puede usar aqui."""
    pending: list[tuple[Any, int]] = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > limit:
            return True
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return False


def _same_person(first: str, second: str) -> bool:
    return " ".join(first.split()).casefold() == " ".join(second.split()).casefold()


def _cited(source: str, source_check: dict[str, Any] | None) -> dict[str, Any]:
    """La fuente que cita una firma y si existe en su registro (`evidence/source_check.py`).

    Solo si la firma cita algo: las firmas de antes no llevan estos campos y siguen igual.
    """
    if not source.strip():
        return {}
    return {"source": source.strip(), "source_check": dict(source_check or {})}


def _quoted(
    quote: dict[str, Any] | None, seen: dict[str, Any] | None, strict: bool = False
) -> dict[str, Any]:
    """La frase literal del informe citado, tal como la da la bóveda al firmar (`vault.locate`).

    Quien firma la ve antes y devuelve lo que vio (`seen`: estado, frase y huella del texto de la
    bóveda). Es el patrón de `text_sha256`: se firma lo que se vio. Si la bóveda da hoy otra frase
    u otra huella, no hay asiento. `vista` deja dicho si la firma declaró haberla visto.

    `strict` es la segunda firma (`app/countersign_rule.py`): desde el 2026-10-13, si la cita no
    se localiza o la firma no declara haber visto la frase, `CountersignRefused` y no hay asiento;
    desde el 2026-10-15, también si no cita un informe guardado (`quote` None: no cita nada;
    `no_aplica`: cita otra cosa), porque no hay frase que cotejar. La primera firma no es
    estricta: sin informe, el asiento dice `no_aplica` o no lleva el campo, como siempre.

    Las firmas de antes no llevan el campo, o lo llevan con `no_localizada`, `vista: false` o
    `no_aplica`: siguen igual, nada se reescribe.
    """
    if quote is not None and quote.get("estado") != NOT_APPLICABLE and seen is not None:
        if any(seen.get(key) != quote.get(key) for key in ("estado", "frase")):
            raise ValueError("la frase que se vio no es la que hoy da la bóveda: vuelve a verla")
        if seen.get("sha256") != quote.get("sha256"):
            raise ValueError("el informe citado no es el texto que se vio: vuelve a ver la frase")
    if strict:
        refused = refusal(quote, seen)
        if refused is not None:
            raise CountersignRefused(refused)
    if quote is None:
        return {}
    if quote.get("estado") == NOT_APPLICABLE:
        return {"source_quote": dict(quote)}
    return {"source_quote": {**quote, "vista": seen is not None}}


def _decision_record(
    signoff: dict[str, Any] | None, countersign: dict[str, Any] | None
) -> dict[str, Any]:
    """El acta de una firma: si hacía falta segunda firma, si está y si las dos coinciden."""
    required = bool(signoff and dict(signoff.get("high_risk") or {}).get("applies"))
    complete = required and countersign is not None
    return {
        "second_signature_required": required,
        "complete": (signoff is not None) and (not required or complete),
        "disagreement": bool(
            complete and signoff and countersign
            and signoff.get("decision") != countersign.get("decision")
        ),
    }


def _text_sha256(draft: dict[str, Any]) -> str:
    """Huella del texto de un borrador, la que cita su firma."""
    return hashlib.sha256(str(draft.get("text", "")).encode("utf-8")).hexdigest()


def _content_matches(entry: LedgerEntry) -> bool:
    try:
        return sha256_hex(canonical_bytes(entry.payload)) == entry.content_hash
    except (TypeError, ValueError, RecursionError):  # p. ej. un NaN cargado de disco
        return False


_IMAGING_TEXT_FIELDS = ("subject", "protocol", "sha256", "acquired", "source")


_REPORT_TEXT_FIELDS = ("subject", "kind", "media_type", "sha256", "source")
_VOLUME_TEXT_FIELDS = ("subject", "modality", "media_type", "sha256", "source")


def _check_imaging_payload(payload: dict[str, Any], data: bytes) -> None:
    """Lo minimo que un asiento de imagen tiene que traer, y que case con los bytes."""
    _check_blob_payload(payload, data, _IMAGING_TEXT_FIELDS, "un estudio de imagen")


def _check_blob_payload(
    payload: dict[str, Any], data: bytes, fields: tuple[str, ...], what: str
) -> None:
    if not isinstance(data, bytes) or not data:
        raise ValueError(f"{what} exige su binario")
    for field in fields:
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise ValueError(f"{what} exige '{field}' como texto")
    if payload["sha256"] != sha256_hex(data):
        raise ValueError("el sha256 del asiento no es el del binario")
    size = payload.get("size_bytes")
    if isinstance(size, bool) or size != len(data):
        raise ValueError("size_bytes no es el tamaño del binario")


def _signed_imaging_payload(entry: LedgerEntry) -> dict[str, Any]:
    """El payload de un estudio, comprobado contra su hash y con sus campos basicos."""
    payload = entry.payload
    if not _content_matches(entry):
        raise TamperedRecordError(
            f"asiento {entry.index}: el contenido no coincide con su hash firmado"
        )
    if not isinstance(payload, dict) or any(
        not isinstance(payload.get(field), str) for field in _IMAGING_TEXT_FIELDS
    ):
        raise TamperedRecordError(f"asiento {entry.index}: estudio de imagen mal formado")
    return payload


def _observation_row(observation: VitalObservation, ledger_index: int) -> ObservationRow:
    return ObservationRow(
        subject=observation.subject,
        key=observation.key,
        value=observation.value,
        # En UTC: SQLite descarta el desfase, y una lectura en +02:00 se releia como
        # UTC, dos horas desplazada. La verificacion de disco la denunciaba como
        # manipulacion para siempre: una falsa alarma de integridad sin ataque.
        effective=observation.effective.astimezone(dt.UTC),
        source=observation.source,
        context=observation.context.value,
        confidence=observation.confidence,
        ledger_index=ledger_index,
    )


def _as_utc(moment: dt.datetime) -> dt.datetime:
    """SQLite no conserva la zona horaria; se reimpone al leer."""
    if not isinstance(moment, dt.datetime):  # un NULL o un valor ajeno puesto en la base
        raise TypeError(f"se esperaba un instante y hay {type(moment).__name__}")
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.UTC)


def _decode_text(raw: bytes) -> str | bytes:
    """Texto de SQLite: UTF-8 si lo es; si no, los bytes tal cual.

    Con el decodificador por defecto, un texto que no era UTF-8 hacia que SQLite
    lanzara OperationalError al leer la fila: 500 en caliente, y un almacen que no
    abria en reposo. Como bytes, falla en `_header_problem` o en el cotejo.
    """
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw


def _configure_connection(dbapi_connection: Any, _record: Any) -> None:
    dbapi_connection.text_factory = _decode_text
    # BORRAR ES BORRAR.
    #
    # Sin esto, redactar dejaba la lectura en el fichero: SQLite marca el espacio como
    # libre sin sobrescribirlo, y la celda con el valor, el instante y la fuente seguia
    # ahi. `secure_delete` pone a cero lo que se borra.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA secure_delete = ON")
    cursor.close()


@dataclass(frozen=True, eq=False)
class _DiskMark:
    """Los contadores con los que SQLite dice si la base cambio, sin leerla.

    - `data_version` (PRAGMA): cambia si **otra** conexion —de este proceso o de otro, con
      cualquier cliente de SQLite— ha confirmado un cambio desde la ultima vez que esta
      conexion lo miro. No cambia con lo que confirma esta misma conexion.
    - `total_changes`: filas insertadas, cambiadas o borradas por **esta** conexion desde que
      se abrio, triggers incluidos. Cubre lo que el anterior no ve: quien edite la base por la
      misma conexion que usa el almacen (la unica que hay con la base en memoria).
    - `schema_version` (PRAGMA): cambia con cualquier cambio de esquema —crear, borrar o alterar
      una tabla—, que `total_changes` no cuenta.
    - `connection`: los tres son de una conexion concreta. Si el pool da otra, o la reabre, no
      se puede comparar nada y se verifica entero.

    Lo que ninguno ve: bytes del fichero escritos sin pasar por SQLite (un editor
    hexadecimal), y las API de bajo nivel de la propia conexion (`blobopen`, `deserialize`,
    copia de seguridad) usadas desde dentro del proceso. Ver `record-integrity.md` §3.5 bis.
    """

    connection: Any
    data_version: int
    total_changes: int
    schema_version: int

    def same_as(self, other: _DiskMark) -> bool:
        return self.same_but_own_writes(other) and self.total_changes == other.total_changes

    def same_but_own_writes(self, other: _DiskMark) -> bool:
        """Igual salvo `total_changes`, que es lo unico que mueve una escritura propia."""
        return (
            self.connection is other.connection
            and self.data_version == other.data_version
            and self.schema_version == other.schema_version
        )


@dataclass(frozen=True, eq=False)
class _Verified:
    """Lo que dejo una `verify_integrity()` que salio bien: hasta donde, y con que marcas."""

    size: int
    memory: MemoryMark
    disk: _DiskMark


class ObservationStore:
    """Persistencia de observaciones con auditoria obligatoria."""

    def __init__(
        self,
        url: str = "sqlite:///emma.db",
        redaction_authority: RedactionAuthority | None = None,
        trusted_sources: Mapping[str, str] | None = None,
    ) -> None:
        # SQLite abre una conexion por hilo con el pool por defecto, y FastAPI
        # atiende los endpoints sincronos en hilos de trabajo. Con una base en
        # memoria eso significa que cada hilo ve **su propia base vacia**: las
        # tablas creadas aqui no existirian al atender la peticion.
        #
        # `StaticPool` fuerza una unica conexion compartida, y
        # `check_same_thread=False` permite usarla desde otro hilo. Para un
        # fichero en disco el pool normal vale, pero la comprobacion de hilo hay
        # que levantarla igual.
        # Qué almacén es este, para que la consola no confunda su versión del modo seguro con la
        # de otro (`_next_epoch`).
        self.epoch = _next_epoch()
        connect_args: dict[str, Any] = {"check_same_thread": False}
        kwargs: dict[str, Any] = {"connect_args": connect_args, "future": True}
        if url in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["poolclass"] = StaticPool

        self.engine = create_engine(url, **kwargs)
        event.listen(self.engine, "connect", _configure_connection)
        Base.metadata.create_all(self.engine)
        # FUENTES APROVISIONADAS.
        #
        # Sin ellas, el registro se aprende de `trusted_keys`, en la misma base que la
        # cadena: quien escribiera en ella daba de alta una identidad nueva y con ella
        # reencadenaba la cola, con la verificacion en verde. Con ellas, el registro
        # llega de fuera —como la autoridad de redaccion—, no admite altas, y una fila
        # de `trusted_keys` que no este aprovisionada es un fallo de verificacion.
        self._provisioned = trusted_sources is not None
        self.registry = (
            KeyRegistry(trusted_sources, fixed=True) if trusted_sources is not None
            else KeyRegistry()
        )
        # La autoridad de redaccion llega de fuera y nunca se guarda en esta base:
        # si se guardara, quien editara la base podria autorizarse a si mismo.
        self.ledger = HashChainLedger(self.registry, redaction_authority=redaction_authority)
        # UN SOLO ESCRITOR A LA VEZ, Y UN SOLO USO DE LA CONEXION A LA VEZ.
        #
        # No habia ningun cerrojo, y FastAPI atiende los endpoints sincronos en
        # un pool de hilos. `HashChainLedger.append` lee el indice y el hash
        # anterior, firma, y solo entonces anade: dos peticiones simultaneas
        # pueden coger el mismo indice. Reproducido con 4 hilos y 800 escrituras:
        # **163 asientos con indice duplicado**, una cadena rota por pura
        # concurrencia que `verify_integrity()` denunciaria como manipulacion.
        #
        # Con la base en memoria —la que usa la aplicacion— era peor: la unica
        # conexion compartida acabo reseteada y el almacen **perdio sus tablas**
        # ("no such table: observations"). Peticiones concurrentes podian borrar
        # todo lo registrado.
        #
        # Reentrante porque `record()` delega en `record_many()`. Serializar es
        # suficiente: una tripulacion escribe a un ritmo que un solo escritor
        # atiende de sobra.
        self._lock = threading.RLock()
        # Serializa la comprobacion de `expected` con el anexado de un changeset de Marplanner.
        self._planner_lock = threading.Lock()
        # Hasta que indice se han comprobado ya las firmas Ed25519. Empieza en 0:
        # lo que se carga de disco se verifica entero la primera vez.
        self._signatures_verified = 0
        # Hasta que indice se ha comprobado ya el contenido que lee `query()`.
        self._content_verified = 0
        # La memoria tal y como estaba cuando se comprobo ese contenido: mientras no cambie
        # (`HashChainLedger.unchanged_since`), los lectores no lo recalculan asiento a asiento.
        self._content_mark: MemoryMark | None = None
        # Lo que dejo la ultima `verify_integrity()` que salio bien, para que la siguiente
        # verifique a fondo solo lo nuevo (`record-integrity.md` §3.5 bis). `None`: completa.
        self._verified: _Verified | None = None
        self._load_ledger()
        if self._provisioned:
            self._record_provisioned_keys()

    @classmethod
    def in_memory(
        cls,
        redaction_authority: RedactionAuthority | None = None,
        trusted_sources: Mapping[str, str] | None = None,
    ) -> ObservationStore:
        return cls("sqlite://", redaction_authority, trusted_sources)

    @classmethod
    def at(
        cls,
        path: Path,
        redaction_authority: RedactionAuthority | None = None,
        trusted_sources: Mapping[str, str] | None = None,
    ) -> ObservationStore:
        return cls(f"sqlite:///{path}", redaction_authority, trusted_sources)

    def _record_provisioned_keys(self) -> None:
        """Deja constancia en `trusted_keys` de las fuentes aprovisionadas que falten.

        Solo anade. Antes solo escribia con la tabla vacia, asi que dar de alta una fuente
        nueva en una base existente dejaba la verificacion en rojo para siempre —y las
        redacciones bloqueadas—: una falsa alarma de integridad por una operacion
        legitima. Anadir no le da nada a un atacante, porque en este modo la tabla no es
        la fuente de la confianza, solo su reflejo; una fila ajena, o con otra clave,
        sigue siendo un fallo de verificacion.

        Consecuencia que hay que saber: la lista aprovisionada tiene que conservar para
        siempre las claves de todas las fuentes que han escrito, y una identidad no
        puede cambiar de clave.
        """
        with Session(self.engine) as session:
            present = set(session.scalars(select(TrustedKeyRow.identity_id)).all())
            missing = [(i, key) for i, key in self.registry.items() if i not in present]
            for identity_id, public_key in missing:
                session.add(TrustedKeyRow(identity_id=identity_id, public_key=public_key))
            if missing:
                session.commit()

    # ------------------------------------------------------------------ #

    def _load_ledger(self) -> None:
        """Reconstruye la cadena desde disco, sin recalcular firmas.

        Se cargan tal cual estan: si alguien edito el fichero por fuera,
        `verify_integrity()` tiene que poder verlo.

        LO ILEGIBLE NO IMPIDE ARRANCAR.
        -------------------------------
        Una fecha que SQLAlchemy no sabia decodificar, un payload con el JSON roto o
        una clave que no era hexadecimal lanzaban al abrir, y el almacen no arrancaba.
        Un monitor de salud tiene que abrir y declarar la integridad rota: la
        tripulacion sigue necesitandolo. Lo ilegible se carga de forma que falle en su
        propio asiento, y una clave ilegible no se admite en el registro.
        """
        with Session(self.engine) as session:
            keys = session.execute(
                select(TrustedKeyRow.identity_id, TrustedKeyRow.public_key)
            ).all()
            # `recorded` como texto: con el tipo DateTime, una fecha ilegible lanzaba
            # al leer la fila, antes de que nadie pudiera tratarla.
            rows = session.execute(
                select(
                    LedgerRow.index, type_coerce(LedgerRow.recorded, String),
                    LedgerRow.entry_type, LedgerRow.content_hash, LedgerRow.prev_hash,
                    LedgerRow.signer, LedgerRow.signer_public_key, LedgerRow.signature,
                    LedgerRow.payload, LedgerRow.redacted,
                ).order_by(LedgerRow.index)
            ).all()

        # Aprovisionado, el registro no se aprende de la base: nada que cargar de ella.
        for identity_id, public_key in [] if self._provisioned else keys:
            if not isinstance(identity_id, str) or not isinstance(public_key, str):
                continue
            try:
                self.registry.register(identity_id, public_key)
            except (ValueError, UntrustedSigner):  # clave ilegible o identidad repetida
                continue  # sus asientos fallaran como firmante no autorizado
        self.ledger.load(
            LedgerEntry(
                index=index,
                recorded=_loaded_recorded(recorded),
                entry_type=entry_type,
                content_hash=content_hash,
                prev_hash=prev_hash,
                signer=signer,
                signer_public_key=signer_public_key,
                signature=signature,
                payload=_loaded_payload(payload),
                redacted=redacted,
            )
            for (
                index, recorded, entry_type, content_hash, prev_hash, signer,
                signer_public_key, signature, payload, redacted,
            ) in rows
        )

    # ------------------------------------------------------------------ #

    def record(self, observation: VitalObservation, identity: Identity) -> LedgerEntry:
        """Guarda una observacion. Es la unica via de escritura, y siempre audita."""
        return self.record_many([observation], identity)[0]

    def record_many(
        self, observations: Iterable[VitalObservation], identity: Identity
    ) -> list[LedgerEntry]:
        """Guarda un lote en una sola transaccion: entero o nada.

        Antes cada observacion abria su sesion y hacia su propio `commit`. Aparte
        de lento —sembrar 21 120 observaciones tardaba 23 s, de los que menos de
        1 s era firmar y encadenar—, un fallo a mitad de lote dejaba escrita
        media tanda.

        EL LEDGER EN MEMORIA NUNCA DIVERGE DE LA BASE.
        ----------------------------------------------
        Los asientos se anaden en memoria antes del `commit`, porque la fila de
        la base necesita su hash y su firma. Si el `commit` falla, esos asientos
        se retiran. No es reescribir historia: nunca llegaron a existir en disco,
        y bajo el cerrojo nadie mas ha podido encadenar detras de ellos. Sin esta
        retirada, la cadena en memoria afirmaria registros que la base no tiene.

        Lo mismo vale para una identidad nueva: se fija en el registro y se guarda
        en `trusted_keys` en el mismo `commit`. Si el lote falla, la clave no se
        queda fijada en memoria sin estarlo en disco.
        """
        batch = list(observations)
        for observation in batch:
            get(observation.key)  # valida el lote entero antes de escribir nada
            if observation.key in SELF_REPORTED_ONLY:
                # Una intensidad de dolor sin su informe no dice donde duele: solo entra
                # por `record_pain_report`, que escribe las dos cosas juntas.
                raise ValueError(
                    f"'{observation.key}' solo se registra con su informe de dolor"
                )
            if observation.key in LAB_REPORT_ONLY:
                # Un analito sale de una analítica que alguien ha confirmado: solo entra por
                # `record_lab_reading`, que escribe la cifra y su confirmación juntas.
                raise ValueError(
                    f"'{observation.key}' solo se registra confirmando una analítica escaneada"
                )

        with self._lock:
            start = len(self.ledger)
            self._before_own_write()
            try:
                with self.ledger.transaction():
                    new_key = self.registry.register(
                        identity.identity_id, identity.public_key_hex
                    )
                    entries = [
                        self.ledger.append(
                            entry_type=OBSERVATION_ENTRY_TYPE,
                            payload=_to_payload(observation),
                            identity=identity,
                        )
                        for observation in batch
                    ]
                    with Session(self.engine) as session:
                        if new_key:
                            session.add(_trusted_key_row(identity))
                        for entry, observation in zip(entries, batch, strict=True):
                            session.add(_ledger_row(entry))
                            session.add(_observation_row(observation, entry.index))
                        session.commit()
            except BaseException:
                self._after_failed_write(start)
                raise
            else:
                self._advance_after_own_write(start)
        return entries

    def record_imaging_study(
        self, payload: dict[str, Any], data: bytes, identity: Identity
    ) -> LedgerEntry:
        """Guarda un estudio de imagen: asiento firmado y binario, en un solo `commit`.

        El asiento lleva el SHA-256 y el tamano del binario; aqui se comprueba que casan
        antes de escribir nada. Un asiento que firmara un hash de otros bytes seria una
        auditoria de algo que no se guardo.
        """
        _check_imaging_payload(payload, data)
        return self._record_blob(IMAGING_STUDY_ENTRY_TYPE, payload, data, identity)

    def record_scanned_report(
        self, payload: dict[str, Any], data: bytes, identity: Identity
    ) -> LedgerEntry:
        """Un informe escaneado: asiento firmado con su OCR y el original, en un solo `commit`."""
        _check_blob_payload(payload, data, _REPORT_TEXT_FIELDS, "un informe escaneado")
        return self._record_blob(SCANNED_REPORT_ENTRY_TYPE, payload, data, identity)

    def _record_blob(
        self, entry_type: str, payload: dict[str, Any], data: bytes, identity: Identity
    ) -> LedgerEntry:
        with self._lock:
            start = len(self.ledger)
            self._before_own_write()
            try:
                with self.ledger.transaction():
                    new_key = self.registry.register(
                        identity.identity_id, identity.public_key_hex
                    )
                    entry = self.ledger.append(entry_type, payload, identity)
                    with Session(self.engine) as session:
                        if new_key:
                            session.add(_trusted_key_row(identity))
                        session.add(_ledger_row(entry))
                        session.add(
                            ImagingBlobRow(
                                ledger_index=entry.index, sha256=payload["sha256"], data=data
                            )
                        )
                        session.commit()
            except BaseException:
                self._after_failed_write(start)
                raise
            else:
                self._advance_after_own_write(start)
        return entry

    def record_measurement(
        self,
        observation: VitalObservation,
        provenance: dict[str, Any],
        identity: Identity,
    ) -> tuple[LedgerEntry, LedgerEntry]:
        """Guarda una medida ecografica: la lectura y su procedencia, en un solo `commit`.

        `provenance` tiene que nombrar un estudio vigente (`study_index`) con su
        `study_sha256`: una medida sobre una imagen que ya no es la firmada, o que se
        redacto, no se registra. La procedencia se escribe **despues** de la lectura y la
        cita por indice, asi que queda atada a ella.
        """
        get(observation.key)
        if observation.key not in ULTRASOUND_MEASURES:
            raise ValueError(f"'{observation.key}' no es una medida ecográfica")
        study_index = provenance.get("study_index")
        if isinstance(study_index, bool) or not isinstance(study_index, int):
            raise ValueError("la procedencia exige 'study_index' entero")

        with self._lock:
            study_payload, _ = self.imaging_blob(study_index)  # vigente y sin manipular
            if provenance.get("study_sha256") != study_payload["sha256"]:
                raise ValueError("la medida cita otra imagen que la firmada en el estudio")
            if study_payload["subject"] != observation.subject:
                raise ValueError("la medida y el estudio son de tripulantes distintos")
            start = len(self.ledger)
            self._before_own_write()
            try:
                with self.ledger.transaction():
                    new_key = self.registry.register(
                        identity.identity_id, identity.public_key_hex
                    )
                    reading = self.ledger.append(
                        OBSERVATION_ENTRY_TYPE, _to_payload(observation), identity
                    )
                    origin = self.ledger.append(
                        IMAGING_MEASUREMENT_ENTRY_TYPE,
                        {**provenance, "observation_index": reading.index},
                        identity,
                    )
                    with Session(self.engine) as session:
                        if new_key:
                            session.add(_trusted_key_row(identity))
                        session.add(_ledger_row(reading))
                        session.add(_observation_row(observation, reading.index))
                        session.add(_ledger_row(origin))
                        session.commit()
            except BaseException:
                self._after_failed_write(start)
                raise
            else:
                self._advance_after_own_write(start)
        return reading, origin

    def measurements(self, study_index: int) -> list[dict[str, Any]]:
        """Medidas vigentes hechas sobre un estudio, con su valor y su procedencia."""
        with self._lock:
            entries = self.ledger._view()
            self._check_unverified_content(entries)
            superseded = self.ledger.amendments(entries)

        found: list[dict[str, Any]] = []
        for entry in entries:
            if entry.entry_type != IMAGING_MEASUREMENT_ENTRY_TYPE:
                continue
            if not _content_matches(entry) or not isinstance(entry.payload, dict):
                raise TamperedRecordError(
                    f"asiento {entry.index}: el contenido no coincide con su hash firmado"
                )
            origin = entry.payload
            if origin.get("study_index") != study_index:
                continue
            index = origin.get("observation_index")
            if isinstance(index, bool) or not isinstance(index, int):
                raise TamperedRecordError(f"asiento {entry.index}: procedencia mal formada")
            if not 0 <= index < entry.index:
                raise TamperedRecordError(f"asiento {entry.index}: cita una lectura inexistente")
            reading = entries[index]
            # Una lectura redactada deja la procedencia sin dato: no hay medida que mostrar.
            if index in superseded or reading.payload is None:
                continue
            found.append(
                {
                    **{k: v for k, v in origin.items() if k != SALT_FIELD},
                    "key": reading.payload.get("key"),
                    "value": reading.payload.get("value"),
                    "ledger_index": entry.index,
                    "recorded": entry.recorded.isoformat(),
                }
            )
        return found

    def record_pain_report(
        self,
        observation: VitalObservation,
        report: dict[str, Any],
        identity: Identity,
    ) -> tuple[LedgerEntry, LedgerEntry]:
        """Guarda un informe de dolor: la intensidad y el informe, en un solo `commit`.

        La lectura lleva la intensidad maxima del informe; si no coinciden, el analisis
        veria un dolor distinto del que se informo, y eso no se escribe.
        """
        get(observation.key)
        if observation.key not in SELF_REPORTED_ONLY:
            raise ValueError(f"'{observation.key}' no es una intensidad de dolor")
        zones = report.get("zones")
        if not isinstance(zones, list):
            raise ValueError("el informe de dolor exige la lista 'zones'")
        peak = max((float(zone["intensity"]) for zone in zones), default=0.0)
        if peak != observation.value:
            raise ValueError("la intensidad registrada no es la máxima del informe")
        if report.get("subject") != observation.subject:
            raise ValueError("la lectura y el informe son de tripulantes distintos")

        with self._lock:
            start = len(self.ledger)
            self._before_own_write()
            try:
                with self.ledger.transaction():
                    new_key = self.registry.register(
                        identity.identity_id, identity.public_key_hex
                    )
                    reading = self.ledger.append(
                        OBSERVATION_ENTRY_TYPE, _to_payload(observation), identity
                    )
                    origin = self.ledger.append(
                        PAIN_REPORT_ENTRY_TYPE,
                        {**report, "observation_index": reading.index},
                        identity,
                    )
                    with Session(self.engine) as session:
                        if new_key:
                            session.add(_trusted_key_row(identity))
                        session.add(_ledger_row(reading))
                        session.add(_observation_row(observation, reading.index))
                        session.add(_ledger_row(origin))
                        session.commit()
            except BaseException:
                self._after_failed_write(start)
                raise
            else:
                self._advance_after_own_write(start)
        return reading, origin

    def record_lab_reading(
        self,
        observation: VitalObservation,
        confirmation: dict[str, Any],
        identity: Identity,
    ) -> tuple[LedgerEntry, LedgerEntry]:
        """Una cifra de analítica confirmada: la lectura y su confirmación, en un solo `commit`.

        `confirmation` nombra el informe (`report_index`) y la lectura (`reading_index`). Bajo el
        cerrojo se comprueba que el informe sigue vigente y sin manipular, que es del mismo
        tripulante y acreditado como suyo, que la lectura existe y es de ese analito, y que nadie
        la ha confirmado ya: una segunda confirmación duplicaría la cifra en la serie.
        """
        get(observation.key)
        report_index = confirmation.get("report_index")
        reading_index = confirmation.get("reading_index")
        if not isinstance(report_index, int) or not isinstance(reading_index, int) or any(
            isinstance(i, bool) for i in (report_index, reading_index)
        ):
            raise ValueError("la confirmación exige 'report_index' y 'reading_index' enteros")
        if not any(char.isalpha() for char in str(confirmation.get("confirmed_by", ""))):
            raise ValueError("una lectura la confirma una persona con nombre")

        with self._lock:
            report, _ = self.report_blob(report_index)  # vigente y sin manipular
            if report.get("subject") != observation.subject:
                raise ValueError("la lectura y el informe son de tripulantes distintos")
            if not report.get("identity", {}).get("usable", False):
                raise LabReadingConflict(
                    "el informe no está acreditado como de este tripulante: no se usa"
                )
            readings = report.get("lab_readings", {}).get("readings", [])
            if not 0 <= reading_index < len(readings):
                raise KeyError(f"el informe {report_index} no tiene la lectura {reading_index}")
            if readings[reading_index].get("key") != observation.key:
                raise ValueError("la lectura confirmada es de otro analito")
            if any(
                item["reading_index"] == reading_index
                for item in self.lab_confirmations(report_index)
            ):
                raise LabReadingConflict("esa lectura ya está confirmada")
            start = len(self.ledger)
            self._before_own_write()
            try:
                with self.ledger.transaction():
                    new_key = self.registry.register(
                        identity.identity_id, identity.public_key_hex
                    )
                    reading = self.ledger.append(
                        OBSERVATION_ENTRY_TYPE, _to_payload(observation), identity
                    )
                    origin = self.ledger.append(
                        LAB_CONFIRMATION_ENTRY_TYPE,
                        {
                            **confirmation,
                            "subject": observation.subject,
                            "observation_index": reading.index,
                        },
                        identity,
                    )
                    with Session(self.engine) as session:
                        if new_key:
                            session.add(_trusted_key_row(identity))
                        session.add(_ledger_row(reading))
                        session.add(_observation_row(observation, reading.index))
                        session.add(_ledger_row(origin))
                        session.commit()
            except BaseException:
                self._after_failed_write(start)
                raise
            else:
                self._advance_after_own_write(start)
        return reading, origin

    def lab_confirmations(self, report_index: int) -> list[dict[str, Any]]:
        """Las confirmaciones de las lecturas de un informe, también las de lecturas redactadas.

        Redactar la cifra no reabre la lectura: lo confirmado y retirado queda en la auditoría,
        y volver a confirmarla sería escribir dos veces la misma medida.
        """
        with self._lock:
            entries = self.ledger._view()
            self._check_unverified_content(entries)
        found: list[dict[str, Any]] = []
        for entry in entries:
            if entry.entry_type != LAB_CONFIRMATION_ENTRY_TYPE or entry.payload is None:
                continue
            if not _content_matches(entry) or not isinstance(entry.payload, dict):
                raise TamperedRecordError(
                    f"asiento {entry.index}: el contenido no coincide con su hash firmado"
                )
            if entry.payload.get("report_index") != report_index:
                continue
            found.append(
                {
                    **{k: v for k, v in entry.payload.items() if k != SALT_FIELD},
                    "ledger_index": entry.index,
                    "recorded": entry.recorded.isoformat(),
                }
            )
        return found

    def pain_reports(self, subject: str) -> list[dict[str, Any]]:
        """Informes de dolor vigentes de un tripulante, del mas antiguo al mas reciente.

        Un informe cuya lectura se redacto no aparece: su lapida sigue en la auditoria.
        """
        with self._lock:
            entries = self.ledger._view()
            self._check_unverified_content(entries)
            superseded = self.ledger.amendments(entries)

        found: list[dict[str, Any]] = []
        for entry in entries:
            if entry.entry_type != PAIN_REPORT_ENTRY_TYPE or entry.payload is None:
                continue
            if not _content_matches(entry) or not isinstance(entry.payload, dict):
                raise TamperedRecordError(
                    f"asiento {entry.index}: el contenido no coincide con su hash firmado"
                )
            report = entry.payload
            if report.get("subject") != subject:
                continue
            index = report.get("observation_index")
            if isinstance(index, bool) or not isinstance(index, int):
                raise TamperedRecordError(f"asiento {entry.index}: informe mal formado")
            if not 0 <= index < entry.index:
                raise TamperedRecordError(f"asiento {entry.index}: cita una lectura inexistente")
            reading = entries[index]
            if index in superseded or reading.payload is None:
                continue
            found.append(
                {
                    **{k: v for k, v in report.items() if k != SALT_FIELD},
                    "intensity": reading.payload.get("value"),
                    "ledger_index": entry.index,
                    "recorded": entry.recorded.isoformat(),
                }
            )
        return found

    def record_findings(self, payload: dict[str, Any], identity: Identity) -> LedgerEntry:
        """Signos y lista de calidad de un estudio vigente, atados a su binario por el hash."""
        study_index = payload.get("study_index")
        if isinstance(study_index, bool) or not isinstance(study_index, int):
            raise ValueError("los hallazgos exigen 'study_index' entero")
        with self._lock:
            study, _ = self.imaging_blob(study_index)  # vigente y sin manipular
            if payload.get("study_sha256") != study["sha256"]:
                raise ValueError("los hallazgos citan otra imagen que la firmada en el estudio")
            return self._record_action(IMAGING_FINDINGS_ENTRY_TYPE, payload, identity)

    def findings(self, study_index: int) -> list[dict[str, Any]]:
        """Hallazgos anotados en un estudio, tal y como estan firmados."""
        with self._lock:
            entries = self.ledger._view()
            self._check_unverified_content(entries)
        found: list[dict[str, Any]] = []
        for entry in entries:
            if entry.entry_type != IMAGING_FINDINGS_ENTRY_TYPE or entry.payload is None:
                continue
            if not _content_matches(entry) or not isinstance(entry.payload, dict):
                raise TamperedRecordError(
                    f"asiento {entry.index}: el contenido no coincide con su hash firmado"
                )
            if entry.payload.get("study_index") != study_index:
                continue
            found.append(
                {
                    **{k: v for k, v in entry.payload.items() if k != SALT_FIELD},
                    "ledger_index": entry.index,
                    "recorded": entry.recorded.isoformat(),
                }
            )
        return found

    def record_draft(self, payload: dict[str, Any], identity: Identity) -> LedgerEntry:
        """Un borrador del modelo local, o la constancia de que se bloqueo."""
        if payload.get("status") not in ("unvalidated", "blocked"):
            raise ValueError("un borrador nace 'unvalidated' o 'blocked'")
        study_index = payload.get("study_index")
        if isinstance(study_index, bool) or not isinstance(study_index, int):
            raise ValueError("un borrador exige 'study_index' entero")
        return self._record_action(DRAFT_ENTRY_TYPE, payload, identity)

    def sign_draft(
        self,
        draft_index: int,
        decision: str,
        signed_by: str,
        comment: str,
        identity: Identity,
        text_sha256: str,
        source: str = "",
        source_check: dict[str, Any] | None = None,
        source_quote: dict[str, Any] | None = None,
        seen_quote: dict[str, Any] | None = None,
    ) -> LedgerEntry:
        """La firma humana de un borrador: una sola, y solo de uno que se pudo leer.

        Aceptar o rechazar es la unica forma de que un borrador deje de ser "sin validar". Un
        borrador bloqueado no se firma: nadie lo ha podido leer.

        La firma cita la huella del texto que se leyo (`text_sha256`, la que da `drafts()`), y
        la huella queda en el asiento. Patron de Polaris (`tools/salida.py`: un borrador solo se
        aprueba con el `nonce` que se entrego con el): se firma lo que se vio, no lo que haya en
        ese indice cuando llegue la peticion.

        Si cita un informe y quien firma pidio ver la frase literal, el asiento puede llevarla
        (`source_quote`, opcional, los mismos campos que en la segunda firma). Aqui no bloquea:
        una cita no localizada se firma y queda dicha. Solo la segunda firma es estricta.
        """
        if decision not in DRAFT_DECISIONS:
            raise ValueError(f"decision desconocida: {decision!r}")
        if not any(character.isalnum() for character in signed_by):
            raise ValueError("una firma exige quien firma")
        with self._lock:
            draft = self._signed_entry(draft_index, DRAFT_ENTRY_TYPE)
            if draft.get("status") != "unvalidated":
                raise ValueError("solo se firma un borrador que se pudo leer")
            if text_sha256 != _text_sha256(draft):
                raise ValueError("la firma cita un texto distinto del borrador registrado")
            already = [
                entry.index for entry in self.ledger._view()
                if entry.entry_type == DRAFT_SIGNOFF_ENTRY_TYPE
                and isinstance(entry.payload, dict)
                and entry.payload.get("draft_index") == draft_index
            ]
            if already:
                raise ValueError(f"el borrador {draft_index} ya está firmado")
            self._require_cited_report(source_quote)
            return self._record_action(
                DRAFT_SIGNOFF_ENTRY_TYPE,
                {
                    "draft_index": draft_index,
                    "decision": decision,
                    "signed_by": signed_by,
                    "comment": comment,
                    "text_sha256": text_sha256,
                    # Si el comentario registra una decisión clínica de alto riesgo, la firma
                    # queda pendiente de una segunda (`countersign_draft`).
                    "high_risk": trigger(comment, deciding=True).to_dict(),
                    **_cited(source, source_check),
                    **_quoted(source_quote, seen_quote, strict=False),
                },
                identity,
            )

    def countersign_draft(
        self,
        draft_index: int,
        decision: str,
        signed_by: str,
        comment: str,
        identity: Identity,
        text_sha256: str,
        source: str = "",
        source_check: dict[str, Any] | None = None,
        source_quote: dict[str, Any] | None = None,
        seen_quote: dict[str, Any] | None = None,
    ) -> LedgerEntry:
        """La segunda firma de una decisión de alto riesgo, de otra persona.

        Patrón de Polaris (`tools/decision_alto_riesgo.py`): una decisión clínica de alto riesgo
        no sale de una sola voz. La segunda persona lee el mismo texto (misma huella) y firma su
        propia decisión; si no coincide con la primera, el acta lo muestra como discrepancia.

        Si cita un informe, el asiento lleva la frase literal que la bóveda da para su cita
        (`source_quote`), su puntero y la huella del texto; `seen_quote` es lo que vio antes de
        firmar, y tiene que ser eso mismo (`_quoted`). Desde el 2026-10-13 es obligatorio verla:
        con la cita no localizada, o sin declarar haberla visto, `CountersignRefused` y no hay
        asiento (`app/countersign_rule.py`). Desde el 2026-10-15 es obligatorio citar un informe
        guardado: otra fuente, o ninguna, no se puede cotejar y se rechaza igual. El rechazo va
        después de las comprobaciones de siempre (409: primera firma de alto riesgo, otra
        persona, misma huella, sin segunda firma previa), que no cambian.
        """
        if decision not in DRAFT_DECISIONS:
            raise ValueError(f"decision desconocida: {decision!r}")
        if not any(character.isalnum() for character in signed_by):
            raise ValueError("una firma exige quien firma")
        with self._lock:
            draft = self._signed_entry(draft_index, DRAFT_ENTRY_TYPE)
            if text_sha256 != _text_sha256(draft):
                raise ValueError("la firma cita un texto distinto del borrador registrado")
            entries = self.ledger._view()
            first = [
                e.payload for e in entries
                if e.entry_type == DRAFT_SIGNOFF_ENTRY_TYPE
                and isinstance(e.payload, dict) and e.payload.get("draft_index") == draft_index
            ]
            if not first:
                raise ValueError("la segunda firma exige una primera")
            if not dict(first[0].get("high_risk") or {}).get("applies"):
                raise ValueError("esta firma no registró una decisión de alto riesgo")
            if _same_person(str(first[0].get("signed_by", "")), signed_by):
                raise ValueError("la segunda firma tiene que ser de otra persona")
            if any(
                e.entry_type == DRAFT_COUNTERSIGN_ENTRY_TYPE
                and isinstance(e.payload, dict) and e.payload.get("draft_index") == draft_index
                for e in entries
            ):
                raise ValueError(f"el borrador {draft_index} ya tiene segunda firma")
            self._require_cited_report(source_quote)
            return self._record_action(
                DRAFT_COUNTERSIGN_ENTRY_TYPE,
                {
                    "draft_index": draft_index,
                    "decision": decision,
                    "signed_by": signed_by,
                    "comment": comment,
                    "text_sha256": text_sha256,
                    **_cited(source, source_check),
                    **_quoted(source_quote, seen_quote, strict=True),
                },
                identity,
            )

    def _require_cited_report(self, source_quote: dict[str, Any] | None) -> None:
        """El informe del que sale la frase que se firma sigue vigente. Bajo cerrojo.

        La frase se leyó de la bóveda antes de tomar el cerrojo del almacén: si entretanto el
        informe se redactó, no se firma una frase de un informe que ya no está.
        """
        if source_quote is not None and source_quote.get("frase"):
            try:
                self.report_blob(int(source_quote["asiento"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    "el informe citado ya no está vigente: vuelve a ver la frase"
                ) from exc

    def draft_subject(self, draft_index: int) -> str:
        """El tripulante de un borrador: el de su estudio de imagen."""
        with self._lock:
            draft = self._signed_entry(draft_index, DRAFT_ENTRY_TYPE)
        study, _ = self.imaging_blob(int(draft["study_index"]))
        return str(study["subject"])

    def drafts(self, study_index: int) -> list[dict[str, Any]]:
        """Borradores de un estudio con su firma, si la tienen, tal y como estan firmados."""
        with self._lock:
            entries = self.ledger._view()
            self._check_unverified_content(entries)

        signoffs: dict[int, dict[str, Any]] = {}
        countersigns: dict[int, dict[str, Any]] = {}
        found: list[dict[str, Any]] = []
        kinds = (DRAFT_ENTRY_TYPE, DRAFT_SIGNOFF_ENTRY_TYPE, DRAFT_COUNTERSIGN_ENTRY_TYPE)
        for entry in entries:
            if entry.entry_type not in kinds:
                continue
            if entry.payload is None:
                continue  # redactado: su lapida lo dice
            if not _content_matches(entry) or not isinstance(entry.payload, dict):
                raise TamperedRecordError(
                    f"asiento {entry.index}: el contenido no coincide con su hash firmado"
                )
            clean = {k: v for k, v in entry.payload.items() if k != SALT_FIELD}
            if entry.entry_type in (DRAFT_SIGNOFF_ENTRY_TYPE, DRAFT_COUNTERSIGN_ENTRY_TYPE):
                target = clean.get("draft_index")
                if isinstance(target, int) and not isinstance(target, bool):
                    first = entry.entry_type == DRAFT_SIGNOFF_ENTRY_TYPE
                    into = signoffs if first else countersigns
                    into[target] = {**clean, "recorded": entry.recorded.isoformat()}
            elif clean.get("study_index") == study_index:
                found.append(
                    {
                        **clean,
                        "text_sha256": _text_sha256(clean),
                        "ledger_index": entry.index,
                        "recorded": entry.recorded.isoformat(),
                    }
                )
        for draft in found:
            index = int(draft["ledger_index"])
            draft["signoff"] = signoffs.get(index)
            draft["countersign"] = countersigns.get(index)
            draft["record"] = _decision_record(draft["signoff"], draft["countersign"])
        return found

    def _signed_entry(self, index: int, entry_type: str) -> dict[str, Any]:
        """El payload de un asiento del tipo pedido, comprobado contra su hash. Bajo cerrojo."""
        entries = self.ledger._view()
        self._check_unverified_content(entries)
        if not 0 <= index < len(entries) or entries[index].entry_type != entry_type:
            raise KeyError(f"no hay {entry_type} en el asiento {index}")
        entry = entries[index]
        if entry.payload is None:
            raise KeyError(f"el asiento {index} está redactado")
        if not _content_matches(entry) or not isinstance(entry.payload, dict):
            raise TamperedRecordError(
                f"asiento {index}: el contenido no coincide con su hash firmado"
            )
        return entry.payload

    def imaging_studies(self, subject: str) -> list[dict[str, Any]]:
        """Los estudios de imagen vigentes de un tripulante, tal y como estan firmados.

        Sin el binario: para eso esta `imaging_blob()`. Un estudio redactado no aparece;
        su lapida sigue en la auditoria.
        """
        with self._lock:
            entries = self.ledger._view()
            self._check_unverified_content(entries)

        found: list[dict[str, Any]] = []
        for entry in entries:
            if entry.entry_type != IMAGING_STUDY_ENTRY_TYPE or entry.payload is None:
                continue
            payload = _signed_imaging_payload(entry)
            if payload["subject"] != subject:
                continue
            found.append(
                {
                    **{k: v for k, v in payload.items() if k != SALT_FIELD},
                    "ledger_index": entry.index,
                    "recorded": entry.recorded.isoformat(),
                }
            )
        return found

    def scanned_reports(self, subject: str) -> list[dict[str, Any]]:
        """Informes escaneados vigentes de un tripulante, sin el binario."""
        return self._blob_entries(SCANNED_REPORT_ENTRY_TYPE, "subject", subject)

    def record_volume_study(
        self, payload: dict[str, Any], data: bytes, identity: Identity
    ) -> LedgerEntry:
        """Un volumen TAC/RM (NIfTI): asiento firmado y binario, en un solo `commit`."""
        _check_blob_payload(payload, data, _VOLUME_TEXT_FIELDS, "un estudio volumétrico")
        return self._record_blob(VOLUME_STUDY_ENTRY_TYPE, payload, data, identity)

    def record_volume_segmentation(
        self, payload: dict[str, Any], data: bytes, identity: Identity
    ) -> LedgerEntry:
        """La segmentación de un estudio vigente: resumen sin validar y ficheros del visor."""
        study_index = payload.get("study_index")
        if isinstance(study_index, bool) or not isinstance(study_index, int):
            raise ValueError("una segmentación exige 'study_index' entero")
        _check_blob_payload(payload, data, ("sha256", "preset", "estado"), "una segmentación")
        with self._lock:
            study, _ = self.volume_blob(study_index)  # vigente y sin manipular
            if payload.get("study_sha256") != study["sha256"]:
                raise ValueError("la segmentación cita otro volumen que el firmado en el estudio")
            return self._record_blob(VOLUME_SEGMENTATION_ENTRY_TYPE, payload, data, identity)

    def volume_studies(self, subject: str) -> list[dict[str, Any]]:
        return self._blob_entries(VOLUME_STUDY_ENTRY_TYPE, "subject", subject)

    def volume_segmentations(self, study_index: int) -> list[dict[str, Any]]:
        return self._blob_entries(VOLUME_SEGMENTATION_ENTRY_TYPE, "study_index", study_index)

    def record_contrast_phase(
        self, study_index: int, phase: str, at: dt.datetime, note: str, declared_by: str,
        identity: Identity,
    ) -> LedgerEntry:
        """Firma la fase de contraste que una persona declara de un TAC vigente.

        Solo una fase del vocabulario cerrado (`volumes/contrast_phase.py`), solo de un estudio
        que sigue vigente y es un TAC, y solo con el nombre de quien lo dice. El asiento del
        estudio no se toca: esto es otro asiento que lo cita. No hay borrado: se corrige
        declarando de nuevo, y vale el ultimo.
        """
        phase_rules.check(phase)
        if not any(char.isalpha() for char in declared_by):
            raise ValueError(phase_rules.NO_NAME)
        with self._lock:
            study = self._signed_entry(study_index, VOLUME_STUDY_ENTRY_TYPE)
            phase_rules.check_modality(study.get("modality"))
            payload = {
                "subject": study["subject"], "study_index": study_index,
                "study_sha256": study["sha256"], "phase": phase, "at": _utc_text(at),
                "note": note.strip(), "declared_by": declared_by.strip(),
            }
            return self._record_action(VOLUME_PHASE_ENTRY_TYPE, payload, identity)

    def contrast_phase_declarations(self, subject: str) -> list[dict[str, Any]]:
        """Las fases de contraste declaradas de los estudios de un tripulante, tal y como estan
        firmadas. Mismas garantias que `_actions`, mas el indice del estudio, que es un entero."""
        with self._lock:
            entries = self.ledger._view()
        cited = {
            entry.index: entry.payload.get("study_index")
            for entry in entries
            if entry.entry_type == VOLUME_PHASE_ENTRY_TYPE and isinstance(entry.payload, dict)
        }
        found = self._actions(subject, VOLUME_PHASE_ENTRY_TYPE, _VOLUME_PHASE_FIELDS)
        for item in found:
            study_index = cited.get(item["ledger_index"])
            if isinstance(study_index, bool) or not isinstance(study_index, int):
                raise TamperedRecordError(f"asiento {item['ledger_index']}: acción mal formada")
            item["study_index"] = study_index
        return found

    def volume_blob(self, ledger_index: int) -> tuple[dict[str, Any], bytes]:
        return self._blob(ledger_index, VOLUME_STUDY_ENTRY_TYPE, "un estudio volumétrico")

    def segmentation_blob(self, ledger_index: int) -> tuple[dict[str, Any], bytes]:
        return self._blob(ledger_index, VOLUME_SEGMENTATION_ENTRY_TYPE, "una segmentación")

    def _blob_entries(self, entry_type: str, field: str, value: Any) -> list[dict[str, Any]]:
        """Asientos vigentes con binario de un tipo, filtrados por un campo; sin el binario."""
        with self._lock:
            entries = self.ledger._view()
            self._check_unverified_content(entries)
        found: list[dict[str, Any]] = []
        for entry in entries:
            if entry.entry_type != entry_type or entry.payload is None:
                continue
            if not _content_matches(entry) or not isinstance(entry.payload, dict):
                raise TamperedRecordError(
                    f"asiento {entry.index}: el contenido no coincide con su hash firmado"
                )
            if entry.payload.get(field) != value:
                continue
            found.append(
                {
                    # Copia profunda, como en `_blob`: lo devuelto no es el asiento firmado.
                    **copy.deepcopy({k: v for k, v in entry.payload.items() if k != SALT_FIELD}),
                    "ledger_index": entry.index,
                    "recorded": entry.recorded.isoformat(),
                }
            )
        return found

    def report_blob(self, ledger_index: int) -> tuple[dict[str, Any], bytes]:
        """El original de un informe escaneado, solo si sigue siendo el que firma su asiento."""
        return self._blob(ledger_index, SCANNED_REPORT_ENTRY_TYPE, "un informe escaneado")

    def imaging_blob(self, ledger_index: int) -> tuple[dict[str, Any], bytes]:
        """El binario de un estudio, solo si sigue siendo el que firma su asiento.

        Se recalcula el hash en cada entrega. Es lo que impide mostrar a la tripulacion, o
        medir, una imagen cambiada en disco: la verificacion periodica la denunciaria, pero
        entre dos verificaciones la imagen ya se habria visto.
        """
        return self._blob(ledger_index, IMAGING_STUDY_ENTRY_TYPE, "un estudio de imagen")

    def _blob(
        self, ledger_index: int, entry_type: str, what: str
    ) -> tuple[dict[str, Any], bytes]:
        with self._lock:
            entries = self.ledger._view()
            self._check_unverified_content(entries)
            if not 0 <= ledger_index < len(entries):
                raise KeyError(f"no hay asiento {ledger_index}")
            entry = entries[ledger_index]
            if entry.entry_type != entry_type or entry.payload is None:
                raise KeyError(f"el asiento {ledger_index} no es {what} vigente")
            if entry_type == IMAGING_STUDY_ENTRY_TYPE:
                payload = _signed_imaging_payload(entry)
            elif _content_matches(entry) and isinstance(entry.payload, dict):
                payload = entry.payload
            else:
                raise TamperedRecordError(
                    f"asiento {entry.index}: el contenido no coincide con su hash firmado"
                )
            with Session(self.engine) as session:
                row = session.get(ImagingBlobRow, ledger_index)
                data = row.data if row is not None else None
        if not isinstance(data, bytes) or sha256_hex(data) != payload.get("sha256"):
            raise TamperedRecordError(
                f"asiento {ledger_index}: el binario no coincide con el hash firmado"
            )
        # Copia profunda: el asiento en memoria es el firmado, y quien anotara lo devuelto en sitio
        # cambiaría su contenido sin pasar por el ledger (pasó con las lecturas de analítica).
        return copy.deepcopy({k: v for k, v in payload.items() if k != SALT_FIELD}), data

    def _advance_after_own_write(self, start: int) -> None:
        """Lo que acaba de escribir este proceso lo construyo el propio ledger —con la
        confianza comprobada, el hash calculado y la firma hecha—, asi que si todo lo
        anterior estaba verificado, esto tambien. Lo cargado de disco no: eso lo
        verifica `_check_unverified_content` antes del primer uso."""
        if self._content_verified == start:
            self._content_verified = len(self.ledger)
        self._after_own_write()

    # Las marcas de disco y la escritura propia. Bajo el cerrojo del almacen, que es el de
    # todas las escrituras: entre `_before_own_write` y `_after_own_write` solo escribe esta.

    def _disk_mark(self) -> _DiskMark | None:
        """La marca de la base ahora, o `None` si no se puede tomar (base danada, bloqueada).

        Sin marca no hay camino corto: la verificacion es la completa, que convierte una base
        ilegible en un fallo de verificacion y no en un 500.

        Con la base en fichero y el pool por defecto, la marca puede salir de una conexion y la
        escritura ir por otra: entonces la identidad o `data_version` no casan y se verifica
        entero. Es mas lento, no menos seguro; la API usa la base en memoria, de una conexion.
        """
        try:
            with self.engine.connect() as connection:
                data_version = connection.exec_driver_sql("PRAGMA data_version").scalar_one()
                schema_version = connection.exec_driver_sql(
                    "PRAGMA schema_version"
                ).scalar_one()
                raw = connection.connection.dbapi_connection
                return _DiskMark(raw, data_version, raw.total_changes, schema_version)  # type: ignore[union-attr]
        except DBAPIError:
            return None

    def _before_own_write(self) -> None:
        """Si alguien ha escrito en la base desde la ultima verificacion, se olvida esta.

        Despues de escribir, `total_changes` sube por lo propio; sin mirar antes, una edicion
        ajena hecha por la misma conexion quedaria absorbida en esa subida.
        """
        state = self._verified
        if state is not None:
            current = self._disk_mark()
            if current is None or not state.disk.same_as(current):
                self._verified = None

    def _after_own_write(self) -> None:
        """La escritura propia mueve `total_changes`, y solo eso: se anota.

        Los otros dos no se toman de nuevo: si `data_version` o el esquema se han movido, no
        lo ha hecho esta escritura, y absorberlo seria dar por buena una edicion ajena. Lo que
        no se distingue es otro hilo escribiendo por la misma conexion sin el cerrojo del
        almacen mientras tanto: es codigo del propio proceso (`record-integrity.md` §3.5 bis).
        """
        state = self._verified
        if state is None:
            return
        current = self._disk_mark()
        if current is not None and current.same_but_own_writes(state.disk):
            self._verified = replace(state, disk=current)
        else:
            self._verified = None

    def _after_failed_write(self, start: int) -> None:
        """Una escritura fallida: si llego a tocar la base —un `rollback`, filas a medias—, no
        se distingue de una edicion ajena y la siguiente verificacion es completa. Si se
        rechazo antes de escribir nada (una firma desconocida, un JSON invalido), la marca
        sigue igual y no se pierde nada: una fuente que reintenta algo invalido no devuelve
        cada consulta a la verificacion completa."""
        self._signatures_verified = min(self._signatures_verified, start)
        self._content_verified = min(self._content_verified, start)
        state = self._verified
        if state is not None:
            current = self._disk_mark()
            if current is None or not state.disk.same_as(current):
                self._verified = None

    def _content_trusted(self) -> int:
        """Hasta que indice el contenido esta comprobado y la memoria no ha cambiado desde
        entonces: ahi `_content_matches` daria cierto, y no hace falta recalcularlo."""
        mark = self._content_mark
        if mark is not None and self.ledger.unchanged_since(mark):
            return self._content_verified
        return 0

    # ------------------------------------------------------------------ #

    def query(
        self,
        subject: str,
        key: str | None = None,
        since: dt.datetime | None = None,
        until: dt.datetime | None = None,
        limit: int | None = None,
    ) -> list[VitalObservation]:
        """Lecturas de un tripulante, **tal y como estan firmadas en la cadena**.

        EL MOTOR SOLO ANALIZA DATOS CUBIERTOS POR UNA FIRMA.
        ---------------------------------------------------
        Antes esto leia la tabla `observations`, que no cubre ningun hash: es una
        copia de conveniencia. Reproducido con la aplicacion en marcha: editar en
        disco una lectura de 62 a 140 lpm hacia que el motor **analizara los
        140**, mientras `verify_integrity()` respondia ok. Solo se detectaba al
        reiniciar.

        Ahora cada lectura sale del `payload` de su asiento, y se comprueba que
        ese contenido sigue coincidiendo con el `content_hash` firmado antes de
        entregarla. La tabla queda como indice para inspeccion por SQL, y
        `verify_integrity()` vigila que no se aparte de la cadena.

        DE UN DATO CORREGIDO SE ENTREGA LA VERSION VIGENTE, Y SOLO ESA.
        --------------------------------------------------------------
        Una enmienda (45 CFR 164.526) no borra la lectura que corrige: la deja
        registrada y la sustituye. El motor tiene que analizar la version buena, y
        **una sola vez** —entregar las dos contaria dos veces el mismo dato en la
        linea base—. Asi que la enmendada se omite y la correccion ocupa su sitio.
        La version anterior sigue en la cadena y en `/api/audit`, que es justo lo
        que 21 CFR 11.10(e) exige y la redaccion no puede dar.
        """
        with self._lock:
            entries = self.ledger._view()
            self._check_unverified_content(entries)
            # Sobre la misma foto de la cadena: pedirla dos veces podria dejar una
            # lectura fuera de las dos.
            superseded = self.ledger.amendments(entries)
            # Lo comprobado con la memoria intacta desde entonces no se recalcula: era el
            # ~10 % de `/api/status`. Una mutacion en sitio lo devuelve todo a comprobar.
            trusted = self._content_trusted()

        selected: list[VitalObservation] = []
        for entry in entries:
            if entry.index in superseded:
                continue
            payload = _reading_payload(entry)
            if payload is None:
                continue
            # Un asiento bien firmado puede traer una lectura mal formada: en modo
            # aprendido basta con que alguien de alta una identidad en la base. Eso tiene
            # que salir como integridad comprometida (409), no como un KeyError (500).
            try:
                if payload["subject"] != subject or (key is not None and payload["key"] != key):
                    continue
                effective = _as_utc(dt.datetime.fromisoformat(payload["effective"]))
                if (since is not None and effective < since) or (
                    until is not None and effective > until
                ):
                    continue
                reading = _from_payload(payload, effective)
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                raise TamperedRecordError(
                    f"asiento {entry.index}: lectura mal formada ({type(exc).__name__})"
                ) from exc
            if entry.index >= trusted and not _content_matches(entry):
                raise TamperedRecordError(
                    f"asiento {entry.index}: el contenido no coincide con su hash firmado"
                )
            selected.append(reading)

        selected.sort(key=lambda obs: obs.effective)
        # Las `limit` mas recientes. Antes devolvia las mas antiguas.
        if limit is not None:
            return selected[-limit:] if limit > 0 else []
        return selected

    def subjects(self) -> list[str]:
        """Tripulantes con lecturas vigentes, segun la cadena firmada.

        Con la version corregida, no la enmendada: una lectura mal atribuida y ya
        rectificada no puede seguir inventando un tripulante que no existe.
        """
        with self._lock:
            entries = self.ledger._view()
            self._check_unverified_content(entries)
            superseded = self.ledger.amendments(entries)
            subjects: set[str] = set()
            for entry in entries:
                if entry.index in superseded:
                    continue
                payload = _reading_payload(entry)
                if payload is None:
                    continue
                subject = payload.get("subject") if isinstance(payload, dict) else None
                if not isinstance(subject, str):
                    raise TamperedRecordError(f"asiento {entry.index}: lectura sin tripulante")
                subjects.add(subject)
            return sorted(subjects)

    def _check_unverified_content(self, entries: Sequence[LedgerEntry]) -> None:
        """Antes de filtrar por un campo, que el contenido este respaldado. Bajo cerrojo.

        `query()` filtraba por `subject` y `effective` antes de comprobar el hash: una
        edicion en reposo que moviera una lectura a otro tripulante la sacaba de la
        consulta en silencio, y el motor emitia un veredicto sin ella. Una supresion
        sin lapida valida tampoco daba error: la lectura desaparecia sin mas. Una
        constante vital que se esfuma sin aviso es el peor fallo posible aqui.

        Y no basta con el hash del payload: la version anterior lo comparaba con un
        `content_hash` que nadie habia verificado. Un SHA-256 no necesita clave: tras
        reabrir, recalcularlo —o cambiar `entry_type`— hacia que `query()` omitiera una
        lectura o la entregara alterada sin error. Lo que no se ha verificado se
        verifica entero: firma, firmante, encadenamiento, contenido y lapidas.

        La memoria del ledger es privada del proceso: lo verificado una vez no cambia,
        y lo que este proceso escribe lo construye el ledger. Asi que esto solo cuesta
        tras abrir un almacen en fichero, una vez.
        """
        if self._content_verified >= len(entries):
            return
        mark = self.ledger.memory_mark()
        result = self.ledger.verify(signatures_from=self._signatures_verified)
        if not result.ok:
            raise TamperedRecordError(f"asiento {result.failed_index}: {result.reason}")
        self._signatures_verified = self._content_verified = len(entries)
        self._content_mark = mark

    def count(self) -> int:
        with self._lock, Session(self.engine) as session:
            return len(session.scalars(select(ObservationRow.id)).all())

    # ------------------------------------------------------------------ #

    def verify_integrity(self, anchor: Anchor | None = None) -> VerificationResult:
        """Verifica la cadena, y que lo que hay en disco sigue siendo esa cadena.

        Antes solo verificaba la copia en memoria, aunque el docstring decia "tal
        y como esta en disco". Con la aplicacion en marcha, una edicion de la base
        no se detectaba hasta reiniciar, y `/api/status` publicaba
        `integrity_ok: true` junto a un analisis hecho sobre el dato alterado.

        Dos partes:

        1. **La cadena en memoria**: encadenamiento y hash de contenido de todas
           las entradas; firma Ed25519 solo de las que aun no se comprobaron.
           Lo que entra desde disco al arrancar se verifica entero.
        2. **El disco contra la cadena**: cada asiento guardado, cada fila de
           `observations` y cada clave de `trusted_keys` deben coincidir con la
           cadena y el registro verificados. La memoria no la puede editar otro
           proceso; el fichero si.

        Con `anchor` se comprueba ademas contra el testigo externo: es lo unico que
        detecta que falten las ultimas entradas, o una reescritura hecha por quien
        controle a la vez la cadena y el registro.

        A FONDO, SOLO LO NUEVO (2026-11-03; `record-integrity.md` §3.5 bis)
        ----------------------------------------------------------------
        Las dos partes recorrian la cadena entera en cada llamada: con 40 dias simulados,
        ~94 000 asientos y ~2,6 s por `/api/status`. Ahora, si la anterior salio bien, se
        repite a fondo solo lo anadido desde entonces, y lo ya verificado se da por intacto
        solo si se puede saber que lo esta sin releerlo:

        - en memoria, porque nada lo ha reescrito ni mutado (`HashChainLedger.unchanged_since`:
          la lista y los payloads guardados cuentan cada cambio);
        - en disco, porque SQLite no ha visto ninguna escritura salvo las de este almacen
          (`_DiskMark`: `data_version`, `total_changes` y `schema_version`, anotados al
          verificar y al terminar cada escritura propia, y comparados antes de cada una).

        Si cualquiera de las dos cosas falla, o entre lo nuevo hay una lapida o una
        enmienda, o se pide con `anchor`, la verificacion es la completa de siempre. Lo que
        la marca de disco no ve —bytes del fichero escritos sin pasar por SQLite— se dice en
        `_DiskMark`.
        """
        with self._lock:
            state, self._verified = self._verified, None
            memory = self.ledger.memory_mark()
            disk = self._disk_mark()
            entries = self.ledger._view()
            start = 0
            if (
                anchor is None
                and state is not None
                and disk is not None
                and state.disk.same_as(disk)
            ):
                start = self.ledger.reusable_prefix((state.size, state.memory), entries)
            result = self.ledger.verify(
                signatures_from=self._signatures_verified,
                anchor=anchor,
                trusted_prefix=(start, state.memory) if start and state is not None else None,
            )
            if not result.ok:
                return result
            self._signatures_verified = self._content_verified = len(entries)
            self._content_mark = memory
            result = self._verify_disk_matches_chain(entries, start)
            if result.ok and disk is not None:
                self._verified = _Verified(size=len(entries), memory=memory, disk=disk)
            return result

    def _verify_disk_matches_chain(
        self, entries: Sequence[LedgerEntry], start: int = 0
    ) -> VerificationResult:
        """El disco contra la cadena: entero, o desde `start` si lo anterior esta intacto."""
        try:
            ledger_rows, key_rows, observation_rows = self._read_disk(start)
            result = self._compare_disk(entries, ledger_rows, key_rows, observation_rows, start)
            return result if not result.ok else self._compare_blobs(entries, start)
        except (ValueError, TypeError, KeyError, AttributeError, DBAPIError) as exc:
            # Un valor que SQLAlchemy no sabe decodificar —una fecha 'basura'—, o que no
            # se puede comparar —un BLOB donde iba texto—, es una edicion del disco y
            # tiene que salir como fallo de verificacion. Como excepcion tumbaba
            # `/api/status` entero con un 500.
            return VerificationResult(
                ok=False,
                failed_index=None,
                reason=f"el disco contiene valores ilegibles: {exc}",
            )

    def _read_disk(
        self, start: int = 0
    ) -> tuple[Sequence[Any], Sequence[Any], Sequence[Any]]:
        """Las filas de los asientos desde `start`, sus lecturas, y todas las claves.

        Con `start` > 0 lo anterior no se lee: la marca de disco dice que nadie lo ha
        tocado, y lo que escribe el almacen solo anade filas de sus asientos nuevos (lo que
        toca filas antiguas —lapidas y enmiendas— fuerza la verificacion completa).
        """
        with Session(self.engine) as session:
            # Las diez columnas. Antes se omitian `recorded`, `entry_type` y
            # `signer`: editarlas en disco no se veia hasta reiniciar, y con las
            # lapidas `entry_type` decide que asiento justifica una supresion.
            ledger_query = select(
                LedgerRow.index, LedgerRow.recorded, LedgerRow.entry_type,
                LedgerRow.content_hash, LedgerRow.prev_hash, LedgerRow.signer,
                LedgerRow.signer_public_key, LedgerRow.signature,
                LedgerRow.payload, LedgerRow.redacted,
            ).order_by(LedgerRow.index)
            observation_query = select(
                ObservationRow.ledger_index, ObservationRow.subject,
                ObservationRow.key, ObservationRow.value,
                ObservationRow.effective, ObservationRow.source,
                ObservationRow.context, ObservationRow.confidence,
            )
            if start:
                ledger_query = ledger_query.where(LedgerRow.index >= start)
                observation_query = observation_query.where(
                    ObservationRow.ledger_index >= start
                )
            ledger_rows = session.execute(ledger_query).all()
            key_rows = session.execute(
                select(TrustedKeyRow.identity_id, TrustedKeyRow.public_key)
            ).all()
            observation_rows = session.execute(observation_query).all()
        return ledger_rows, key_rows, observation_rows

    def _compare_disk(
        self,
        entries: Sequence[LedgerEntry],
        ledger_rows: Sequence[Any],
        key_rows: Sequence[Any],
        observation_rows: Sequence[Any],
        start: int = 0,
    ) -> VerificationResult:
        """Las filas leidas contra la cadena. Con `start`, las de los asientos desde ahi."""
        # Como conjuntos, no ordenando: ordenar un BLOB junto a un texto lanzaba.
        if {(identity_id, key) for identity_id, key in key_rows} != set(self.registry.items()):
            return VerificationResult(
                ok=False,
                failed_index=None,
                reason="el registro de claves en disco no coincide con el de confianza",
            )
        fresh = entries[start:]
        if len(ledger_rows) != len(fresh):
            return VerificationResult(
                ok=False,
                failed_index=start + min(len(ledger_rows), len(fresh)),
                reason="el número de asientos en disco no coincide con la cadena",
            )
        # Por posicion y no por atributo: una fila de SQLAlchemy es una tupla, y
        # `row.index` es el metodo `tuple.index`, no la columna. Asi escrito, la
        # comparacion fallaba siempre y denunciaba manipulacion en toda base sana.
        for stored_entry, entry in zip(ledger_rows, fresh, strict=True):
            index, recorded, *columns = tuple(stored_entry)
            stored = (index, _as_utc(recorded), *columns)
            expected = (
                entry.index, entry.recorded, entry.entry_type, entry.content_hash,
                entry.prev_hash, entry.signer, entry.signer_public_key, entry.signature,
                json.dumps(entry.payload) if entry.payload is not None else None,
                entry.redacted,
            )
            if stored != expected:
                return VerificationResult(
                    ok=False,
                    failed_index=entry.index,
                    reason="el asiento en disco no coincide con la cadena firmada",
                )

        # Una fila por lectura vigente: la observacion que nadie ha corregido, o la
        # enmienda que la sustituye. La tabla es el indice de lo que `query()` entrega;
        # si guardara ademas la version corregida, una inspeccion por SQL leeria un dato
        # que el motor ya no usa.
        superseded = self.ledger.amendments(entries)
        expected_rows = {
            entry.index
            for entry in fresh
            if entry.index not in superseded and _reading_payload(entry) is not None
        }
        seen: set[int] = set()
        for (
            ledger_index, subject, key, value, effective, source, context, confidence
        ) in observation_rows:
            if isinstance(ledger_index, bool) or not isinstance(ledger_index, int):
                return VerificationResult(
                    ok=False,
                    failed_index=None,
                    reason="fila de observations con un índice que no es entero",
                )
            backing = entries[ledger_index] if 0 <= ledger_index < len(entries) else None
            # El asiento tiene que poner una lectura en circulacion: una fila que
            # apuntara a una lapida llegaba a `payload["subject"]` y lanzaba KeyError.
            # Y no puede apuntar a una version ya corregida: seria una lectura viva en
            # la tabla que `query()` no entrega.
            payload = _reading_payload(backing) if backing is not None else None
            if (
                backing is None
                or not isinstance(payload, dict)
                or ledger_index in superseded
                or ledger_index in seen
            ):
                return VerificationResult(
                    ok=False,
                    failed_index=ledger_index,
                    reason="fila de observations sin asiento firmado que la respalde",
                )
            seen.add(ledger_index)
            stored_row = (
                subject, key, value, _as_utc(effective), source, context, confidence,
            )
            expected_row = (
                payload["subject"], payload["key"], payload["value"],
                _as_utc(dt.datetime.fromisoformat(payload["effective"])),
                payload["source"],
                payload.get("context", Context.UNKNOWN.value),
                payload.get("confidence", FULL_CONFIDENCE),
            )
            if stored_row != expected_row:
                return VerificationResult(
                    ok=False,
                    failed_index=ledger_index,
                    reason="la fila de observations no coincide con su asiento firmado",
                )
        if seen != expected_rows:
            missing = min(expected_rows - seen)
            return VerificationResult(
                ok=False,
                failed_index=missing,
                reason="falta en observations una lectura que la cadena si registra",
            )
        return VerificationResult(ok=True)

    def _compare_blobs(
        self, entries: Sequence[LedgerEntry], start: int = 0
    ) -> VerificationResult:
        """Cada estudio vigente tiene su binario, y el binario es el que firma el asiento.

        Se recalcula el SHA-256 de cada binario. Cuesta leerlos todos en cada
        verificacion —del orden de un segundo por gigabyte—, pero comparar solo con la
        columna `sha256` no detectaria nada: esa columna se edita igual que el dato. Los
        binarios se leen de uno en uno para no tenerlos todos en memoria a la vez. Con
        `start`, solo los de los asientos desde ahi (`_read_disk`).
        """
        expected = {
            entry.index: entry
            for entry in entries[start:]
            if entry.entry_type in BLOB_ENTRY_TYPES and entry.payload is not None
        }
        with Session(self.engine) as session:
            stored = session.execute(
                select(ImagingBlobRow.ledger_index, ImagingBlobRow.sha256).where(
                    ImagingBlobRow.ledger_index >= start
                )
            ).all()
            stored_indices = [index for index, _ in stored]
            if sorted(stored_indices) != sorted(expected):
                missing = set(expected) - set(stored_indices)
                return VerificationResult(
                    ok=False,
                    failed_index=min(missing) if missing else None,
                    reason="los binarios de imagen en disco no coinciden con los estudios firmados",
                )
            for index, column_hash in stored:
                signed = expected[index].payload
                content = session.scalar(
                    select(ImagingBlobRow.data).where(ImagingBlobRow.ledger_index == index)
                )
                if (
                    not isinstance(signed, dict)
                    or column_hash != signed.get("sha256")
                    or not isinstance(content, bytes)
                    or sha256_hex(content) != signed.get("sha256")
                ):
                    return VerificationResult(
                        ok=False,
                        failed_index=index,
                        reason="el binario de imagen no coincide con su hash firmado",
                    )
        return VerificationResult(ok=True)

    def _carried_with_study(self, ledger_index: int) -> list[int]:
        """Las fases de contraste y las segmentaciones aun con contenido que citan este
        estudio, en el orden de la cadena.

        Por el indice que citan, sin mirar la huella ni quien los firmo: lo que se protege es
        el nombre de quien hablo de ese estudio y los pixeles del estudio que van en el binario
        de su segmentacion, y uno que no habria contado en la consola tambien los lleva. Una
        cadena anterior a estas reglas puede tener la fase o la segmentacion de un estudio ya
        redactado: sigue verificando, no se enseña en ninguna vista (todas parten de los
        estudios vigentes) y se puede redactar por su indice.
        """
        chain = self.ledger._view()
        if not (0 <= ledger_index < len(chain)) or (
            chain[ledger_index].entry_type != VOLUME_STUDY_ENTRY_TYPE
        ):
            return []
        return [
            entry.index for entry in chain
            if entry.entry_type in _CARRIED_WITH_STUDY
            and isinstance(entry.payload, dict)
            and entry.payload.get("study_index") == ledger_index
            and not isinstance(entry.payload.get("study_index"), bool)
        ]

    def _redact_one(
        self, session: Session, ledger_index: int, identity: Identity, reason: str,
        requested_by: str,
    ) -> Redaction:
        """Una redaccion dentro de la transaccion de `redact`: lapida, fila y binario."""
        redaction = self.ledger.redact(ledger_index, identity, reason, requested_by)
        session.add(_ledger_row(redaction.tombstone))
        row = session.get(LedgerRow, ledger_index)
        if row is not None:
            row.payload = None
            row.redacted = True
        observation_row = session.scalars(
            select(ObservationRow).where(ObservationRow.ledger_index == ledger_index)
        ).one_or_none()
        if observation_row is not None:
            session.delete(observation_row)
        # Redactar un estudio de imagen es borrar la imagen: el hash firmado sin los bytes no
        # revela nada; los bytes si.
        blob = session.get(ImagingBlobRow, ledger_index)
        if blob is not None:
            session.delete(blob)
        return redaction

    def redact(
        self, ledger_index: int, identity: Identity, reason: str, requested_by: str
    ) -> Redaction:
        """Suprime el contenido clinico de un registro y deja constancia firmada.

        Via de rectificacion de 45 CFR 164.312(c)(1). El dato desaparece de la
        cadena y de `observations`; una lapida firmada registra que existio, cual
        era su hash, por que se quito y quien lo pidio. Lapida, supresion y borrado
        de la fila van en un solo `commit`: si falla, la transaccion del ledger
        retira la lapida y devuelve el contenido.

        `identity` tiene que ser la autoridad de redaccion con que se abrio el
        almacen. No se registra en `trusted_keys`: la autoridad no se aprende.

        No se redacta sobre una cadena que no verifica. La autoridad firmaba una lapida
        para un asiento ya manipulado, y `verify()` pasaba a verde: la prueba de la
        alteracion quedaba sustituida por una rectificacion de apariencia legitima.

        Redactar un TAC redacta tambien, en el mismo `commit` y cada una con su lapida, las
        fases de contraste declaradas de el (`record_contrast_phase`), que llevan el nombre de
        quien las declaro y una nota libre sobre ese estudio, y sus segmentaciones
        (`record_volume_segmentation`), cuyo binario firmado lleva un volumen recortado del
        estudio y se borra como el suyo. Sin esto seguian en la cadena despues de quitar el
        estudio. Van en `dependents`, en el orden de la cadena; si una falla, no se escribe
        ninguna.
        """
        with self._lock:
            verification = self.verify_integrity()
            if not verification.ok:
                raise ValueError(
                    f"la cadena no verifica (asiento {verification.failed_index}: "
                    f"{verification.reason}): no se redacta sobre ella"
                )
            cited = self._carried_with_study(ledger_index)
            start = len(self.ledger)
            self._before_own_write()
            try:
                with self.ledger.transaction():
                    with Session(self.engine) as session:
                        redaction = self._redact_one(
                            session, ledger_index, identity, reason, requested_by
                        )
                        dependents = tuple(
                            self._redact_one(
                                session, index, identity,
                                f"redactado con el estudio del asiento {ledger_index}: {reason}",
                                requested_by,
                            )
                            for index in cited
                        )
                        session.commit()
                    redaction = replace(redaction, dependents=dependents)
            except BaseException:
                self._after_failed_write(start)
                raise
            else:
                self._advance_after_own_write(start)

        return redaction

    def amend(
        self,
        ledger_index: int,
        observation: VitalObservation,
        identity: Identity,
        reason: str,
    ) -> Amendment:
        """Corrige una lectura anexando la version buena, sin borrar la anterior.

        Es la via normal de correccion —45 CFR 164.526— y la que no choca con el
        mandato de 21 CFR 11.10(e) de que un cambio no oculte lo registrado antes.
        La redaccion queda para el dato que nunca debio existir.

        Quien firma es una fuente del registro, no la autoridad de redaccion: el
        contenido corregido es un dato clinico, y la clave de rectificar no debe
        poder fabricarlos.

        En la tabla `observations` la fila de la lectura corregida se sustituye por
        la nueva. No es perder nada: la anterior sigue en la cadena, firmada y
        legible en `/api/audit`; la tabla es el indice de lo vigente.

        Tampoco se enmienda sobre una cadena que no verifica, por lo mismo que no se
        redacta: la correccion daria apariencia de dato revisado a un registro
        manipulado.
        """
        get(observation.key)  # el indicador existe en el catalogo, antes de escribir

        with self._lock:
            chain = self.ledger._view()
            target_payload = (
                chain[ledger_index].payload if 0 <= ledger_index < len(chain) else None
            )
            if (
                isinstance(target_payload, dict)
                and target_payload.get("key") in ULTRASOUND_MEASURES
            ) or observation.key in ULTRASOUND_MEASURES:
                # Una medida ecografica sale de unos puntos sobre una imagen. Enmendar el
                # numero lo separaria de los puntos que dice su procedencia: se vuelve a
                # medir, y la medida equivocada se redacta si no debio existir.
                raise ValueError(
                    "una medida ecográfica no se enmienda: se vuelve a medir sobre el estudio"
                )
            if (
                isinstance(target_payload, dict)
                and target_payload.get("key") in SELF_REPORTED_ONLY
            ) or observation.key in SELF_REPORTED_ONLY:
                # La intensidad es la maxima de las zonas de su informe. Cambiar la cifra
                # la separaria del informe: se registra un informe nuevo, y el erroneo se
                # redacta si no debio existir.
                raise ValueError(
                    "una intensidad de dolor no se enmienda: se registra un informe nuevo"
                )
            if (
                0 <= ledger_index < len(chain)
                and chain[ledger_index].entry_type in BLOB_ENTRY_TYPES
            ):
                # Una enmienda sustituye un dato por otro del mismo tipo. Enmendar una
                # imagen con una lectura escalar la retiraria de la consola sin borrarla ni
                # dejar lapida: un estudio que desaparece sin rastro legible.
                raise ValueError(
                    f"el asiento {ledger_index} es un estudio de imagen: no se enmienda "
                    "con una lectura; si no debió registrarse, se redacta"
                )
            target = chain[ledger_index] if 0 <= ledger_index < len(chain) else None
            # Una enmienda corrige el valor de una lectura, o a quien se atribuyo, no el
            # indicador: cambiarlo retiraria del motor la lectura de uno y pondria en su lugar la
            # de otro que nadie midio en su sitio, con la serie del primero sin su dato y sin
            # lapida que lo explique. El tripulante si puede cambiar, a proposito: reasignar una
            # lectura mal atribuida es el control del peligro H3 (`risk-management-file.md`).
            # La comprobacion es de la escritura, no de `verify()`: un ledger ya escrito con
            # una enmienda de otro indicador sigue verificando. Lo redactado, las lapidas y lo
            # ya enmendado los rechaza el ledger con su motivo (409): un conflicto de estado
            # no se disfraza de dato malo. Va antes de verificar la cadena entera, como las
            # de arriba: es una consulta a un asiento.
            if (
                target is not None
                and target.payload is not None
                and target.entry_type != REDACTION_ENTRY_TYPE
                and ledger_index not in self.ledger.amendments(chain)
            ):
                reading = _reading_payload(target)
                corrected_key = reading.get("key") if isinstance(reading, dict) else None
                if corrected_key is None:
                    raise AmendmentMismatch(
                        f"el asiento {ledger_index} ({target.entry_type}) no es la lectura de "
                        "un indicador: no se enmienda con una"
                    )
                if corrected_key != observation.key:
                    raise AmendmentMismatch(
                        f"el asiento {ledger_index} es una lectura de '{corrected_key}' y la "
                        f"corrección es de '{observation.key}': una enmienda corrige esa lectura "
                        "(su valor, su instante, su tripulante), no el indicador; la de otro "
                        "indicador se da de alta aparte"
                    )
                # El alimento (§3.14 quinquies) dice de qué plato es la lectura, no su valor. Si
                # la corrección no trae `food_item`, se conserva: sin pasarlo, la versión corregida
                # —la única que se lee— salía del plato y se contaba como «sin alimento
                # declarado», sin que nada lo dijera.
                carried = reading.get("food")
                if observation.food is None and isinstance(carried, str):
                    observation = replace(observation, food=carried)
            verification = self.verify_integrity()
            if not verification.ok:
                raise ValueError(
                    f"la cadena no verifica (asiento {verification.failed_index}: "
                    f"{verification.reason}): no se enmienda sobre ella"
                )
            start = len(self.ledger)
            self._before_own_write()
            try:
                with self.ledger.transaction():
                    new_key = self.registry.register(identity.identity_id, identity.public_key_hex)
                    amendment = self.ledger.amend(
                        ledger_index, _to_payload(observation), identity, reason
                    )
                    with Session(self.engine) as session:
                        if new_key:
                            session.add(_trusted_key_row(identity))
                        session.add(_ledger_row(amendment.entry))
                        corrected = session.scalars(
                            select(ObservationRow).where(
                                ObservationRow.ledger_index == ledger_index
                            )
                        ).one_or_none()
                        if corrected is not None:
                            session.delete(corrected)
                        session.add(_observation_row(observation, amendment.entry.index))
                        session.commit()
            except BaseException:
                self._after_failed_write(start)
                raise
            else:
                self._advance_after_own_write(start)

        return amendment

    def acknowledge(
        self,
        subject: str,
        domain: str,
        level: str,
        reference_time: dt.datetime,
        acknowledged_by: str,
        identity: Identity,
        rules_version: str | None = None,
    ) -> LedgerEntry:
        """Registra el reconocimiento de una alerta, firmado, en la cadena.

        `reference_time` es el instante de la ultima lectura del estado que vio quien
        reconoce: el reconocimiento se refiere a esa alerta concreta, no a cualquier
        alerta futura del mismo dominio. `acknowledged_by` es lo que se declara: la
        API no autentica operadores (record-integrity.md §7.5). `rules_version` es la
        huella con que se decidio (§3.26), la que pone la ruta; sin ella el asiento es
        el de antes del campo.
        """
        return self._record_action(
            ACKNOWLEDGEMENT_ENTRY_TYPE,
            {
                "subject": subject,
                "domain": domain,
                "level": level,
                "reference_time": _utc_text(reference_time),
                "acknowledged_by": acknowledged_by,
                **_decided_with(rules_version),
            },
            identity,
        )

    def acknowledgements(self, subject: str) -> list[dict[str, Any]]:
        """Los reconocimientos de un tripulante, tal y como estan firmados."""
        return self._actions(
            subject, ACKNOWLEDGEMENT_ENTRY_TYPE, _ACKNOWLEDGEMENT_FIELDS, _DECIDED_WITH_OPTIONAL
        )

    def record_alert_resolution(
        self, subject: str, domain: str, level: str, reference_time: dt.datetime,
        state: str, note: str, declared_by: str, identity: Identity,
        rules_version: str | None = None,
    ) -> LedgerEntry:
        """"En arreglo" o "resuelto" para una alerta concreta, firmado y con quién lo dice."""
        if state not in RESOLUTION_STATES:
            raise ValueError(f"estado desconocido: {state!r}")
        if not any(char.isalpha() for char in declared_by):
            raise ValueError("el estado de una alerta lo declara una persona con nombre")
        return self._record_action(
            RESOLUTION_ENTRY_TYPE,
            {
                "subject": subject,
                "domain": domain,
                "level": level,
                "reference_time": _utc_text(reference_time),
                "state": state,
                "note": note.strip(),
                "declared_by": declared_by.strip(),
                **_decided_with(rules_version),
            },
            identity,
        )

    def alert_resolutions(self, subject: str) -> list[dict[str, Any]]:
        return self._actions(
            subject, RESOLUTION_ENTRY_TYPE, _RESOLUTION_FIELDS, _DECIDED_WITH_OPTIONAL
        )

    def record_alert_dismissal(
        self, subject: str, domain: str, level: str, reference_time: dt.datetime,
        reason: str, note: str, declared_by: str, identity: Identity,
        rules_version: str | None = None,
    ) -> LedgerEntry:
        """«Descartada» para una alerta concreta, con su motivo y quién lo dice, firmado.

        Las reglas que dependen del estado (que la alerta exista) las aplica la API; aquí, las
        que no dependen de nada: un motivo del vocabulario, nota si el motivo es «otro» y una
        persona con nombre.
        """
        problem = dismissal_problem(reason, note, declared_by)
        if problem is not None:
            raise ValueError(problem)
        return self._record_action(
            DISMISSAL_ENTRY_TYPE,
            {
                "subject": subject,
                "domain": domain,
                "level": level,
                "reference_time": _utc_text(reference_time),
                "reason": reason,
                "note": note.strip(),
                "declared_by": declared_by.strip(),
                **_decided_with(rules_version),
            },
            identity,
        )

    def alert_dismissals(self, subject: str) -> list[dict[str, Any]]:
        """Los descartes de un tripulante, tal y como están firmados."""
        return self._actions(
            subject, DISMISSAL_ENTRY_TYPE, _DISMISSAL_FIELDS, _DECIDED_WITH_OPTIONAL
        )

    def set_annunciation(
        self,
        subject: str,
        action: str,
        domain: str,
        level: str | None,
        reference_time: dt.datetime,
        until: dt.datetime | None,
        reason: str,
        requested_by: str,
        identity: Identity,
    ) -> LedgerEntry:
        """Suprime, inhibe o vuelve a habilitar el anuncio de alertas de un dominio.

        Las reglas —que se puede silenciar, cuanto tiempo, que rompe el silencio— las
        aplica la API; aqui se registra la decision, firmada, con su motivo. Nada de
        esto toca las lecturas ni el analisis: cambia si una alerta **se anuncia**, no
        si **existe**.
        """
        if action not in ANNUNCIATION_ACTIONS:
            raise ValueError(f"accion de anuncio desconocida: {action}")
        return self._record_action(
            ANNUNCIATION_ENTRY_TYPE,
            {
                "subject": subject,
                "action": action,
                "domain": domain,
                "level": level or "",
                "reference_time": _utc_text(reference_time),
                "until": _utc_text(until) if until is not None else "",
                "reason": reason,
                "requested_by": requested_by,
            },
            identity,
        )

    def annunciation_changes(self, subject: str) -> list[dict[str, Any]]:
        """Supresiones, inhibiciones y rehabilitaciones, tal y como estan firmadas."""
        return self._actions(subject, ANNUNCIATION_ENTRY_TYPE, _ANNUNCIATION_FIELDS)

    def record_followup(
        self,
        subject: str,
        action: str,
        countermeasure_id: str,
        domain: str,
        level: str,
        reference_time: dt.datetime,
        decided_by: str,
        identity: Identity,
        reason: str = "",
        adoption_index: int | None = None,
        level_at_close: str | None = None,
        closed_reference_time: dt.datetime | None = None,
        rules_version: str | None = None,
    ) -> LedgerEntry:
        """Adopta una contramedida, cierra su seguimiento o deja dicho que no se adopta.

        Las reglas (que la recomendacion exista, que el cierre apunte a una adopcion
        abierta) las aplica la API; aqui se registra la decision con su autor declarado.
        "declined" es un tercer valor de `action`, no un tipo de asiento ni un campo nuevo
        (`record-integrity.md` §3.15 bis): su motivo va en `reason`, que deja de poder ir vacio.
        `rules_version` es la huella con que se decidio (§3.26), en las tres acciones; la pone
        la ruta.
        """
        if action not in ("adopted", "closed", "declined"):
            raise ValueError(f"accion de seguimiento desconocida: {action}")
        if action == "declined":
            if not reason.strip():
                raise ValueError("decidir no adoptar una contramedida exige su motivo")
            if adoption_index is not None:
                raise ValueError("decidir no adoptar no apunta a ninguna adopción")
        # El nivel al cerrar y su instante van juntos y solo en un cierre: un nivel sin el
        # instante del estado del que se copio no se podria situar, y en una adopcion o en un
        # «no» ese nivel ya es `level`.
        if (level_at_close is None) != (closed_reference_time is None):
            raise ValueError("el nivel al cerrar y el instante de su estado van juntos")
        if level_at_close is not None and action != "closed":
            raise ValueError("el nivel al cerrar solo lo lleva un cierre")
        at_close: dict[str, str] = {}
        if level_at_close is not None and closed_reference_time is not None:
            at_close = {
                "level_at_close": level_at_close,
                "closed_reference_time": _utc_text(closed_reference_time),
            }
        return self._record_action(
            FOLLOWUP_ENTRY_TYPE,
            {
                "subject": subject,
                "action": action,
                "countermeasure_id": countermeasure_id,
                "domain": domain,
                "level": level,
                "reference_time": _utc_text(reference_time),
                "decided_by": decided_by,
                "reason": reason,
                # Texto, como todos los campos de una accion (`_actions` lo exige).
                "adoption_index": str(adoption_index) if adoption_index is not None else "",
                # Sin ellos el asiento es, campo por campo, el de antes del cambio.
                **at_close,
                **_decided_with(rules_version),
            },
            identity,
        )

    def record_habitat(
        self, readings: Sequence[HabitatReading], identity: Identity
    ) -> list[LedgerEntry]:
        """Registra lecturas de cabina, firmadas, en un solo `commit` (como `record_many`)."""
        return self._record_batch(
            HABITAT_ENTRY_TYPE, [reading.to_payload() for reading in readings], identity
        )

    def record_prediction_snapshots(
        self, payloads: Sequence[dict[str, str]], identity: Identity
    ) -> list[LedgerEntry]:
        """Firma las proyecciones del dia para comprobarlas cuando llegue su horizonte."""
        for payload in payloads:
            if set(payload) != set(_SNAPSHOT_FIELDS) or any(
                not isinstance(value, str) for value in payload.values()
            ):
                raise ValueError("instantánea de proyección mal formada")
        return self._record_batch(SNAPSHOT_ENTRY_TYPE, list(payloads), identity)

    def prediction_snapshots(self, subject: str) -> list[dict[str, Any]]:
        return self._actions(subject, SNAPSHOT_ENTRY_TYPE, _SNAPSHOT_FIELDS)

    def _record_batch(
        self, entry_type: str, payloads: Sequence[dict[str, Any]], identity: Identity
    ) -> list[LedgerEntry]:
        """Varios asientos del mismo tipo en un solo `commit`, con el cuidado de `record_many`."""
        with self._lock:
            start = len(self.ledger)
            self._before_own_write()
            try:
                with self.ledger.transaction():
                    new_key = self.registry.register(
                        identity.identity_id, identity.public_key_hex
                    )
                    entries = [
                        self.ledger.append(entry_type, payload, identity)
                        for payload in payloads
                    ]
                    with Session(self.engine) as session:
                        if new_key:
                            session.add(_trusted_key_row(identity))
                        session.add_all(_ledger_row(entry) for entry in entries)
                        session.commit()
            except BaseException:
                self._after_failed_write(start)
                raise
            else:
                self._advance_after_own_write(start)
        return entries

    def habitat_readings(
        self, until: dt.datetime | None = None, since: dt.datetime | None = None
    ) -> list[HabitatReading]:
        """Lecturas de cabina con las garantias de `query()`: solo lo que casa con su hash."""
        with self._lock:
            entries = self.ledger._view()
            self._check_unverified_content(entries)
            trusted = self._content_trusted()
        found: list[HabitatReading] = []
        for entry in entries:
            if entry.entry_type != HABITAT_ENTRY_TYPE or not isinstance(entry.payload, dict):
                continue
            if entry.index >= trusted and not _content_matches(entry):
                raise TamperedRecordError(
                    f"asiento {entry.index}: el contenido no coincide con su hash firmado"
                )
            try:
                reading = HabitatReading.from_payload(entry.payload)
            except (KeyError, TypeError, ValueError) as exc:
                raise TamperedRecordError(
                    f"asiento {entry.index}: lectura de hábitat mal formada"
                ) from exc
            if until is not None and reading.effective > until:
                continue
            if since is not None and reading.effective < since:
                continue
            found.append(reading)
        return found

    def record_profile(
        self, subject: str, prior_missions: int, prior_career_dose_msv: float | None,
        declared_by: str, identity: Identity,
    ) -> LedgerEntry:
        """Declara el historial de un tripulante. Vale el ultimo declarado."""
        if prior_missions < 0 or (prior_career_dose_msv is not None and prior_career_dose_msv < 0):
            raise ValueError("un historial no puede ser negativo")
        return self._record_action(
            PROFILE_ENTRY_TYPE,
            {
                "subject": subject,
                "prior_missions": str(prior_missions),
                "prior_career_dose_msv": (
                    "" if prior_career_dose_msv is None else repr(prior_career_dose_msv)
                ),
                "declared_by": declared_by,
            },
            identity,
        )

    def profiles(self, subject: str) -> list[dict[str, Any]]:
        return self._actions(subject, PROFILE_ENTRY_TYPE, _PROFILE_FIELDS)

    def record_mission_history(
        self, subject: str, missions: Sequence[history_rules.PriorMission], declared_by: str,
        identity: Identity, *, current_start: dt.date | None,
    ) -> LedgerEntry:
        """Declara el historial misión a misión de un tripulante, entero. Vale el último.

        Un asiento propio, al lado del perfil: no toca `crew-profile` ni lo que lee la dosis de
        carrera. Las reglas (`core/mission_history.check`) valen también llamado desde aquí.
        `current_start`, el inicio de la misión en curso, impide además una previa que se solape
        con ella (la API lo toma de la configuración). Es obligatorio a propósito: quien llame
        tiene que decir cuál es, o `None` si de verdad no lo conoce; un valor por omisión dejaría
        que una vía nueva se saltara la regla sin saberlo.
        """
        if not any(char.isalpha() for char in declared_by):
            raise ValueError("el historial lo declara una persona con nombre")
        return self._record_action(
            MISSION_HISTORY_ENTRY_TYPE,
            {
                "subject": subject,
                "missions": history_rules.encode(
                    history_rules.check(missions, current_start=current_start)
                ),
                "declared_by": declared_by.strip(),
            },
            identity,
        )

    def mission_histories(self, subject: str) -> list[dict[str, Any]]:
        """Los historiales declarados, con `missions` como texto (lo lee `mission_history`)."""
        return self._actions(subject, MISSION_HISTORY_ENTRY_TYPE, _MISSION_HISTORY_FIELDS)

    def record_crew_identity(
        self, subject: str, given_name: str, surnames: str, birth_date: dt.date,
        declared_by: str, identity: Identity,
    ) -> LedgerEntry:
        """Declara la identidad de un tripulante para cotejar sus informes. Vale la última."""
        if not any(char.isalpha() for char in given_name):
            raise ValueError("la identidad exige el nombre de pila")
        return self._record_action(
            CREW_IDENTITY_ENTRY_TYPE,
            {
                "subject": subject,
                "given_name": given_name.strip(),
                "surnames": surnames.strip(),
                "birth_date": birth_date.isoformat(),
                "declared_by": declared_by,
            },
            identity,
        )

    def crew_identities(self, subject: str) -> list[dict[str, Any]]:
        return self._actions(subject, CREW_IDENTITY_ENTRY_TYPE, _IDENTITY_FIELDS)

    def record_crew_sex(
        self, subject: str, sex: str, declared_by: str, identity: Identity
    ) -> LedgerEntry:
        """Declara el sexo de un tripulante. Vale el último; se borra con `redact`, uno a uno.

        La regla vale también llamado desde fuera de la API: un valor fuera de `CREW_SEX_VALUES`
        o una declaración sin nombre no se firman (`ValueError`, sin escribir nada).
        """
        if sex not in CREW_SEX_VALUES:
            raise ValueError(f"sexo desconocido; uno de {CREW_SEX_VALUES}")
        if not any(char.isalpha() for char in declared_by):
            raise ValueError("el sexo lo declara una persona con nombre")
        return self._record_action(
            CREW_SEX_ENTRY_TYPE,
            {"subject": subject, "sex": sex, "declared_by": declared_by.strip()},
            identity,
        )

    def crew_sexes(self, subject: str) -> list[dict[str, Any]]:
        """Las declaraciones sin redactar, con las garantías de `_actions`."""
        return self._actions(subject, CREW_SEX_ENTRY_TYPE, _CREW_SEX_FIELDS)

    def record_safe_mode(
        self, active: bool, reason: str, declared_by: str, identity: Identity
    ) -> LedgerEntry:
        """Activa o levanta el modo seguro. Activarlo pide motivo; levantarlo, una persona."""
        return self._change_safe_mode(active, reason, declared_by, identity)[0]

    def change_safe_mode(
        self, active: bool, reason: str, declared_by: str, identity: Identity
    ) -> dict[str, Any]:
        """Como `record_safe_mode`, y devuelve el estado que dejó ESTE cambio, con su versión.

        Es la respuesta de `POST /api/safe-mode` (§5.38.13): si otro cambio se firma justo
        después, esta respuesta sigue diciendo la versión de este, no la del otro.
        """
        return self._change_safe_mode(active, reason, declared_by, identity)[1]

    def _change_safe_mode(
        self, active: bool, reason: str, declared_by: str, identity: Identity
    ) -> tuple[LedgerEntry, dict[str, Any]]:
        """Mirar el estado vigente y firmar el asiento van bajo el mismo cerrojo (§5.38.13).

        Dos cambios cruzados se firman uno detrás de otro, cada uno con su versión, y no pueden
        pasar los dos la regla de «ya está activo» antes de que el otro se firme. La versión del
        cambio sale de la del estado que se acaba de mirar, sin volver a recorrer los asientos.
        """
        if active and not any(char.isalnum() for char in reason):
            raise ValueError("activar el modo seguro exige un motivo")
        if not any(char.isalpha() for char in declared_by):
            raise ValueError("el modo seguro lo activa o lo levanta una persona con nombre")
        with self._lock:
            current = self.safe_mode()
            if current["active"] == active:
                raise SafeModeConflict(
                    "el modo seguro ya está " + ("activo" if active else "levantado")
                )
            entry = self._record_action(
                SAFE_MODE_ENTRY_TYPE,
                {
                    "subject": SAFE_MODE_SUBJECT,
                    "active": "true" if active else "false",
                    "reason": reason.strip(),
                    "declared_by": declared_by.strip(),
                },
                identity,
            )
            version = current["version"] + 1
        return entry, {
            "active": active,
            "reason": reason.strip() or None,
            "declared_by": declared_by.strip(),
            "since": entry.recorded.isoformat(),
            "ledger_index": entry.index,
            "version": version,
            "store_epoch": self.epoch,
        }

    def safe_mode(self) -> dict[str, Any]:
        """El estado vigente: el último asiento manda. Sin asientos, apagado.

        `version` es cuántos asientos de modo seguro hay. Sube en uno con cada cambio y nunca
        baja (el ledger solo crece), así que la consola sabe, sin volver a preguntar, cuál de dos
        respuestas es la más nueva aunque lleguen al revés (§5.38.13). No es un campo firmado: se
        cuenta sobre los asientos firmados, y un asiento alterado es un 409 antes de contarlo. No
        es `ledger_index`, que también crece: este falta sin asientos y salta con los asientos de
        otros tipos; la versión existe desde 0 y va de uno en uno. Cuenta asientos de este
        almacén: `store_epoch` dice cuál es (`_next_epoch`).
        """
        entries = self._actions(SAFE_MODE_SUBJECT, SAFE_MODE_ENTRY_TYPE, _SAFE_MODE_FIELDS)
        if not entries:
            return {
                "active": False, "reason": None, "declared_by": None, "since": None,
                "version": 0, "store_epoch": self.epoch,
            }
        last = max(entries, key=lambda item: item["ledger_index"])
        return {
            "active": last["active"] == "true",
            "reason": last["reason"] or None,
            "declared_by": last["declared_by"],
            "since": last.get("recorded"),
            "ledger_index": last["ledger_index"],
            "version": len(entries),
            "store_epoch": self.epoch,
        }

    def change_simulated_link(
        self, state: str, at: dt.datetime, note: str, declared_by: str, identity: Identity
    ) -> LedgerEntry:
        """Firma «enlace con Tierra simulado: caído/restablecido» desde `at` (§3.29).

        Mirar los cambios vigentes y firmar van bajo el mismo cerrojo: dos declaraciones cruzadas
        se firman una detrás de otra y no pasan las dos la regla de «no se repite el estado».
        Las reglas son las de `link_sync.check_change`: el estado no se repite y un cambio no se
        refiere a un instante anterior al del último, así que los tramos quedan en orden.
        """
        with self._lock:
            link_rules.check_change(
                link_rules.transitions(self.simulated_link_entries()), state, at, declared_by
            )
            return self._record_action(
                LINK_ENTRY_TYPE,
                {
                    "subject": LINK_SUBJECT, "state": state, "at": _utc_text(at),
                    "note": note.strip(), "declared_by": declared_by.strip(),
                },
                identity,
            )

    def simulated_link_entries(self) -> list[dict[str, Any]]:
        """Los cambios del enlace simulado, tal y como están firmados (con su firmante).

        Uno con un estado fuera de `link_sync.STATES` o un instante ilegible es un 409, como
        cualquier acción mal formada: el corte de Tierra no se calcula con él.
        """
        entries = self._actions(LINK_SUBJECT, LINK_ENTRY_TYPE, _LINK_FIELDS)
        for item in entries:
            try:
                moment = dt.datetime.fromisoformat(item["at"])
            except ValueError as exc:
                raise TamperedRecordError(
                    f"asiento {item['ledger_index']}: instante del enlace ilegible"
                ) from exc
            if item["state"] not in link_rules.STATES or moment.tzinfo is None:
                raise TamperedRecordError(
                    f"asiento {item['ledger_index']}: cambio del enlace mal formado"
                )
        return entries

    # --- Discrepancia SPICE-Horizons (§3.30) ---------------------------------------------- #

    def record_ephemeris_discrepancy(
        self, payload: dict[str, str], identity: Identity
    ) -> LedgerEntry | None:
        """Firma la discrepancia de un día de efeméride, si ese día aún no la tiene firmada.

        Un asiento por día de efeméride, objetivo y observador, no uno por consulta: mirar lo
        firmado y firmar van bajo el mismo cerrojo, y dos consultas cruzadas no firman las dos.
        Devuelve el asiento nuevo, o `None` si ese día ya constaba.
        """
        if set(payload) != set(EPHEMERIS_DISCREPANCY_FIELDS) or any(
            not isinstance(value, str) for value in payload.values()
        ):
            raise ValueError("discrepancia de efemérides mal formada")
        with self._lock:
            day = (payload["epoch"], payload["target"], payload["observer"])
            if any(
                (item["epoch"], item["target"], item["observer"]) == day
                for item in self.ephemeris_discrepancies()
            ):
                return None
            return self._record_action(EPHEMERIS_DISCREPANCY_ENTRY_TYPE, payload, identity)

    def ephemeris_discrepancies(
        self, until: dt.datetime | None = None
    ) -> list[dict[str, Any]]:
        """Las discrepancias firmadas, tal y como están firmadas; con `until`, las firmadas hasta
        ese instante (lo que ya tiene Tierra en su corte, por la hora de su firma)."""
        found = self._actions(
            EPHEMERIS_DISCREPANCY_SUBJECT, EPHEMERIS_DISCREPANCY_ENTRY_TYPE,
            EPHEMERIS_DISCREPANCY_FIELDS,
        )
        if until is None:
            return found
        return [item for item in found if dt.datetime.fromisoformat(item["recorded"]) <= until]

    def link_snapshot(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Los cambios del enlace y los instantes de una misma instantánea, bajo un solo cerrojo:
        entre las dos lecturas no entra un asiento que una cuente y la otra no."""
        with self._lock:
            return self.simulated_link_entries(), self.ledger_instants()

    def ledger_instants(self) -> list[dict[str, Any]]:
        """El instante de cada asiento, para contar lo pendiente de bajar a Tierra (§3.29).

        El de una lectura (y de una lectura de cabina) es su hora (`effective`); el de cualquier
        otro asiento, la hora de su firma. Es la regla con que Tierra corta lo que pide. No entrega
        contenido, pero con las garantías de `_actions`: un asiento cuyo contenido no coincide con
        su hash es un 409 antes de contarlo, porque una hora alterada movería la cuenta.
        """
        with self._lock:
            entries = self.ledger._view()
            self._check_unverified_content(entries)
            trusted = self._content_trusted()
        found: list[dict[str, Any]] = []
        for entry in entries:
            if entry.index >= trusted and isinstance(entry.payload, dict) and not _content_matches(
                entry
            ):
                raise TamperedRecordError(
                    f"asiento {entry.index}: el contenido no coincide con su hash firmado"
                )
            instant = entry.recorded
            basis = "recorded"
            payload = entry.payload
            if entry.entry_type in _EFFECTIVE_ENTRY_TYPES and isinstance(payload, dict):
                try:
                    instant = _as_utc(dt.datetime.fromisoformat(str(payload["effective"])))
                except (KeyError, ValueError) as exc:
                    raise TamperedRecordError(
                        f"asiento {entry.index}: lectura sin hora legible"
                    ) from exc
                basis = "effective"
            found.append({
                "index": entry.index, "entry_type": entry.entry_type, "signer": entry.signer,
                "instant": _as_utc(instant).isoformat(), "basis": basis,
            })
        return found

    def record_mission_mode(
        self, level: str, reason: str, declared_by: str, identity: Identity,
        cited_system: str | None = None,
    ) -> LedgerEntry:
        """Firma un cambio de nivel de misión. Bajar pide motivo; subir, un nivel cada vez."""
        return self._change_mission_mode(level, reason, declared_by, identity, cited_system)[0]

    def change_mission_mode(
        self, level: str, reason: str, declared_by: str, identity: Identity,
        cited_system: str | None = None,
    ) -> dict[str, Any]:
        """Como `record_mission_mode`, y devuelve el estado que dejó ESTE cambio, con su versión.

        Es la respuesta de `POST /api/mission-mode`, con la misma garantía que la del modo seguro
        (§5.38.13): si otro cambio se firma justo después, esta sigue diciendo la versión de este.
        """
        return self._change_mission_mode(level, reason, declared_by, identity, cited_system)[1]

    def _change_mission_mode(
        self, level: str, reason: str, declared_by: str, identity: Identity,
        cited_system: str | None,
    ) -> tuple[LedgerEntry, dict[str, Any]]:
        """Mirar el nivel vigente, leer el sistema citado y firmar van bajo el mismo cerrojo.

        Dos cambios cruzados se firman uno detrás de otro, cada uno con su versión, y no pueden
        pasar los dos la regla de «no se repite el nivel» o «se sube de uno en uno» antes de que
        el otro se firme. El estado citado es el último declarado por la consola del sistema
        entero (`mission_modes.cited_state`); el cliente no lo manda.
        """
        mission_mode_rules.check_cited(cited_system)
        with self._lock:
            current = self.mission_mode()
            mission_mode_rules.check_change(current["level"], level, reason, declared_by)
            payload = {
                "subject": MISSION_MODE_SUBJECT,
                "level": level,
                "reason": reason.strip(),
                "declared_by": declared_by.strip(),
            }
            if cited_system is not None:
                declarations = [
                    item for item in self.system_statuses() if action_counts(item, None)
                ]
                payload["cited_system"] = cited_system
                payload["cited_state"] = mission_mode_rules.cited_state(
                    declarations, cited_system
                )
            entry = self._record_action(MISSION_MODE_ENTRY_TYPE, payload, identity)
            version = current["version"] + 1  # la de este asiento, no la de uno posterior
        return entry, {
            "level": level,
            "reason": reason.strip() or None,
            "declared_by": declared_by.strip(),
            "since": entry.recorded.isoformat(),
            "ledger_index": entry.index,
            "cited_system": payload.get("cited_system"),
            "cited_state": payload.get("cited_state"),
            "version": version,
            "store_epoch": self.epoch,
        }

    def mission_mode(self, until: dt.datetime | None = None) -> dict[str, Any]:
        """El nivel vigente: el último asiento firmado por la consola. Sin asientos, nominal.

        Cuenta lo firmado por la consola y, para Tierra, lo que ya existía en su corte
        (`identities.action_counts`), como toda acción del operador. `version` es cuántos de esos
        asientos hay, con la misma regla que la del modo seguro: sube en uno con cada cambio, no
        baja, y se cuenta sobre lo firmado (uno alterado es un 409 antes de contarlo). Con
        `until`, la versión es la del corte. `store_epoch` dice de qué almacén es.
        """
        entries = [
            item for item in self._actions(
                MISSION_MODE_SUBJECT, MISSION_MODE_ENTRY_TYPE, _MISSION_MODE_FIELDS,
                _MISSION_MODE_OPTIONAL,
            )
            if action_counts(item, until)
        ]
        if not entries:
            return {
                "level": mission_mode_rules.NOMINAL, "reason": None, "declared_by": None,
                "since": None, "ledger_index": None, "cited_system": None, "cited_state": None,
                "version": 0, "store_epoch": self.epoch,
            }
        for item in entries:
            # Firmado, pero fuera del vocabulario: no se adivina qué quiso decir, y tampoco se
            # cuenta en la versión como si fuera un cambio válido.
            problem = mission_mode_rules.entry_problem(item)
            if problem is not None:
                raise TamperedRecordError(f"asiento {item['ledger_index']}: {problem}")
        last = max(entries, key=lambda item: item["ledger_index"])
        return {
            "level": last["level"],
            "reason": last["reason"] or None,
            "declared_by": last["declared_by"],
            "since": last["recorded"],
            "ledger_index": last["ledger_index"],
            "cited_system": last.get("cited_system"),
            "cited_state": last.get("cited_state"),
            "version": len(entries),
            "store_epoch": self.epoch,
        }

    def record_mission_profile(
        self, profile: str, reason: str, declared_by: str, identity: Identity, configured: str,
    ) -> LedgerEntry:
        """Firma un cambio de entorno de la misión. `configured` es el de la configuración."""
        return self._change_mission_profile(profile, reason, declared_by, identity, configured)[0]

    def change_mission_profile(
        self, profile: str, reason: str, declared_by: str, identity: Identity, configured: str,
    ) -> dict[str, Any]:
        """Como `record_mission_profile`, y devuelve el estado que dejó ESTE cambio, con su
        versión (la respuesta de `POST /api/mission/profile`, como `change_mission_mode`)."""
        return self._change_mission_profile(profile, reason, declared_by, identity, configured)[1]

    def _change_mission_profile(
        self, profile: str, reason: str, declared_by: str, identity: Identity, configured: str,
    ) -> tuple[LedgerEntry, dict[str, Any]]:
        """Mirar el entorno vigente y firmar van bajo el mismo cerrojo.

        Dos cambios cruzados al mismo entorno se firman uno y chocan el otro: no pueden pasar los
        dos la regla de «no se repite el vigente» antes de que el otro se firme. El asiento lleva
        el entorno vigente al firmar (`previous`), que en el primer cambio es el de la
        configuración.
        """
        with self._lock:
            current = self.mission_profile(None, configured)
            mission_profile_rules.check_change(current["id"], profile, declared_by)
            payload = {
                "subject": MISSION_PROFILE_SUBJECT,
                "profile": profile,
                "previous": current["id"],
                "reason": reason.strip(),
                "declared_by": declared_by.strip(),
            }
            entry = self._record_action(MISSION_PROFILE_ENTRY_TYPE, payload, identity)
            version = current["version"] + 1  # la versión de este asiento
        return entry, {
            "id": profile,
            "previous": current["id"],
            "reason": reason.strip() or None,
            "declared_by": declared_by.strip(),
            "since": entry.recorded.isoformat(),
            "ledger_index": entry.index,
            "source": mission_profile_rules.REGISTRY,
            "configured": configured,
            "version": version,
            "store_epoch": self.epoch,
        }

    def mission_profile(
        self, until: dt.datetime | None, configured: str
    ) -> dict[str, Any]:
        """El entorno vigente: el último asiento firmado por la consola; sin asientos, el de la
        configuración (`configured`).

        Cuenta lo firmado por la consola y, para Tierra, lo que ya existía en su corte
        (`identities.action_counts`), como el nivel de misión. `version` es cuántos de esos
        asientos hay; uno firmado fuera del catálogo es un 409, sea el último o uno anterior.
        """
        entries = [
            item for item in self._actions(
                MISSION_PROFILE_SUBJECT, MISSION_PROFILE_ENTRY_TYPE, _MISSION_PROFILE_FIELDS,
            )
            if action_counts(item, until)  # lo de la consola y, con `until`, hasta el corte
        ]
        for item in entries:
            problem = mission_profile_rules.entry_problem(item)
            if problem:
                raise TamperedRecordError(f"asiento {item['ledger_index']}: {problem}")
        if not entries:
            return {
                "id": configured, "previous": None, "reason": None, "declared_by": None,
                "since": None, "ledger_index": None, "source": mission_profile_rules.CONFIGURATION,
                "configured": configured, "version": 0, "store_epoch": self.epoch,
            }
        last = max(entries, key=lambda item: item["ledger_index"])
        return {
            "id": last["profile"],
            "previous": last["previous"],
            "reason": last["reason"] or None,
            "declared_by": last["declared_by"],
            "since": last["recorded"],
            "ledger_index": last["ledger_index"],
            "source": mission_profile_rules.REGISTRY,
            "configured": configured,
            "version": len(entries),
            "store_epoch": self.epoch,
        }

    def record_mission_event(
        self, subject: str, kind: str, start: dt.datetime, end: dt.datetime, label: str,
        declared_by: str, identity: Identity, module: str | None = None,
    ) -> LedgerEntry:
        """Registra una EVA, un bloque de trabajo, un cambio de turno o donde esta el tripulante.

        La ubicacion es una declaracion de una persona, no una medida, y solo admite un modulo
        de la lista declarada: con un nombre libre, "Laboratorio" y "laboratorio" serian dos
        sitios y la correlacion con el habitat daria por ausente a quien estaba alli.
        """
        if kind not in MISSION_EVENT_KINDS:
            raise ValueError(f"tipo de evento de misión desconocido: {kind}")
        if end <= start:
            raise ValueError("un evento tiene que terminar después de empezar")
        payload = {
            "subject": subject, "kind": kind, "start": _utc_text(start),
            "end": _utc_text(end), "label": label, "declared_by": declared_by,
        }
        if kind == LOCATION_EVENT_KIND:
            if module not in MODULES:
                raise ValueError(
                    f"módulo desconocido: {module}; uno de {', '.join(MODULES)}"
                )
            payload["module"] = module
        elif module is not None:
            raise ValueError("solo una declaración de ubicación lleva módulo")
        return self._record_action(MISSION_EVENT_ENTRY_TYPE, payload, identity)

    def mission_events(self, subject: str) -> list[dict[str, Any]]:
        return self._actions(
            subject, MISSION_EVENT_ENTRY_TYPE, _MISSION_EVENT_FIELDS, _MISSION_EVENT_OPTIONAL
        )

    def record_hypothesis_review(
        self, decision: str, parameter: str, excursion_start: dt.datetime, reason: str,
        decided_by: str, identity: Identity,
    ) -> LedgerEntry:
        """Confirma o descarta una hipotesis de causa compartida, con motivo."""
        if decision not in HYPOTHESIS_DECISIONS:
            raise ValueError(f"decisión desconocida: {decision}")
        return self._record_action(
            HYPOTHESIS_ENTRY_TYPE,
            {
                "subject": CREW_SUBJECT, "decision": decision, "parameter": parameter,
                "excursion_start": _utc_text(excursion_start), "reason": reason,
                "decided_by": decided_by,
            },
            identity,
        )

    def hypothesis_reviews(self) -> list[dict[str, Any]]:
        return self._actions(CREW_SUBJECT, HYPOTHESIS_ENTRY_TYPE, _HYPOTHESIS_FIELDS)

    def record_system_status(
        self, system: str, state: str, at: dt.datetime, note: str, declared_by: str,
        identity: Identity, module: str | None = None,
    ) -> LedgerEntry:
        """Firma lo que una persona declara del estado de un sistema del habitat.

        Solo un sistema y un estado del vocabulario declarado (`environment/systems.py`), y
        solo con el nombre de quien lo dice: con texto libre, "degradado" y "Degradado" serian
        dos estados, y una declaracion sin autor no es una declaracion. No hay borrado: se
        corrige declarando de nuevo, y vale el ultimo asiento.
        """
        habitat_systems.check(system, state, module)
        if not any(char.isalpha() for char in declared_by):
            raise ValueError("el estado de un sistema lo declara una persona con nombre")
        payload = {
            "subject": SYSTEM_STATUS_SUBJECT, "system": system, "state": state,
            "at": _utc_text(at), "note": note.strip(), "declared_by": declared_by.strip(),
        }
        if module is not None:
            payload["module"] = module
        return self._record_action(SYSTEM_STATUS_ENTRY_TYPE, payload, identity)

    def system_statuses(self) -> list[dict[str, Any]]:
        """Las declaraciones de estado de sistemas, tal y como estan firmadas."""
        return self._actions(
            SYSTEM_STATUS_SUBJECT, SYSTEM_STATUS_ENTRY_TYPE, _SYSTEM_STATUS_FIELDS,
            _SYSTEM_STATUS_OPTIONAL,
        )

    def record_sensor_binding(
        self, source: str, action: str, since: dt.datetime, note: str, declared_by: str,
        identity: Identity, crew: str | None = None, device: str | None = None,
    ) -> LedgerEntry:
        """Firma lo que una persona declara de quien lleva un dispositivo, o que ya no lo lleva.

        Solo una fuente de wearable que la ingesta distingue y un identificador con forma de
        identificador (`ingest/bindings.py`), y solo con el nombre de quien lo dice. No hay
        borrado: se retira o se corrige declarando de nuevo, y vale el ultimo asiento.
        """
        key = binding_rules.check(source, action, crew, device)
        if not any(char.isalpha() for char in declared_by):
            raise ValueError("un vínculo lo declara una persona con nombre")
        payload = {
            "subject": CREW_SUBJECT, "source": source, "action": action,
            "since": _utc_text(since), "note": note.strip(), "declared_by": declared_by.strip(),
        }
        if key is not None:
            payload["device"] = key
        if crew is not None:
            payload["crew"] = crew.strip()
        return self._record_action(SENSOR_BINDING_ENTRY_TYPE, payload, identity)

    def sensor_bindings(self) -> list[dict[str, Any]]:
        """Las declaraciones de vinculo sensor-tripulante, tal y como estan firmadas."""
        return self._actions(
            CREW_SUBJECT, SENSOR_BINDING_ENTRY_TYPE, _SENSOR_BINDING_FIELDS,
            _SENSOR_BINDING_OPTIONAL,
        )

    def record_location_anchor(
        self, anchor_id: str, module: str, since: dt.datetime, declared_by: str,
        identity: Identity,
    ) -> LedgerEntry:
        """Firma lo que una persona declara: esta ancla esta en este modulo desde `since`.

        Solo un identificador con forma de identificador, un modulo de la lista y el nombre de
        quien lo dice (`ingest/location_anchors.check_anchor`). No hay borrado: vale la ultima.
        """
        key = anchor_rules.check_anchor(anchor_id, module, declared_by)
        anchor_rules.aware(since)
        payload = {
            "subject": ANCHOR_SUBJECT, "anchor_id": key, "module": module,
            "since": _utc_text(since), "declared_by": declared_by.strip(),
        }
        return self._record_action(LOCATION_ANCHOR_ENTRY_TYPE, payload, identity)

    def location_anchors(self) -> list[dict[str, Any]]:
        """Las declaraciones de anclas de modulo, tal y como estan firmadas."""
        return self._actions(
            ANCHOR_SUBJECT, LOCATION_ANCHOR_ENTRY_TYPE, _LOCATION_ANCHOR_FIELDS
        )

    def record_location_sightings(
        self, subject: str, sightings: Sequence[tuple[str, float, dt.datetime]],
        identity: Identity, device: str | None = None,
    ) -> LedgerEntry:
        """Firma un lote de lo que oyo el receptor de un tripulante: UN asiento por lote.

        Cada lectura es `(anchor_id, rssi_dbm, at)`. Un ancla que nadie ha declarado se guarda
        igual (no se usa al estimar). Lo que no tiene forma de lectura se rechaza sin escribir.
        """
        anchor_rules.check_batch(subject, len(sightings))
        rows = [
            {
                "anchor_id": anchor_rules.anchor_key(anchor_id),
                "rssi_dbm": anchor_rules.check_rssi(rssi_dbm),
                "at": _utc_text(anchor_rules.aware(at)),
            }
            for anchor_id, rssi_dbm, at in sightings
        ]
        payload: dict[str, Any] = {"subject": subject.strip(), "sightings": rows}
        if device is not None:
            payload["device"] = device
        return self._record_action(LOCATION_SIGHTINGS_ENTRY_TYPE, payload, identity)

    def location_sightings(
        self, subject: str, since: dt.datetime | None = None
    ) -> list[dict[str, Any]]:
        """Las lecturas de anclas de un tripulante con `at` ≥ `since`, con las garantias de
        `_actions`: un asiento alterado o mal formado es un 409, no una lectura menos.

        Cada una lleva el asiento de su lote (`ledger_index`), cuando se firmo y quien lo firmo.
        """
        with self._lock:
            entries = self.ledger._view()
            self._check_unverified_content(entries)
            trusted = self._content_trusted()
        found: list[dict[str, Any]] = []
        for entry in entries:
            if entry.entry_type != LOCATION_SIGHTINGS_ENTRY_TYPE:
                continue
            if entry.index >= trusted and not _content_matches(entry):
                raise TamperedRecordError(
                    f"asiento {entry.index}: el contenido no coincide con su hash firmado"
                )
            payload = entry.payload
            rows = payload.get("sightings") if isinstance(payload, dict) else None
            if (
                not isinstance(payload, dict)
                or not isinstance(payload.get("subject"), str)
                or not isinstance(rows, list)
                or any(not _sighting_row(row) for row in rows)
            ):
                raise TamperedRecordError(f"asiento {entry.index}: lote de lecturas mal formado")
            if payload["subject"] != subject:
                continue
            for row in rows:
                at = dt.datetime.fromisoformat(row["at"])
                if since is not None and at < since:
                    continue
                found.append({
                    "anchor_id": row["anchor_id"], "rssi_dbm": float(row["rssi_dbm"]),
                    "at": at, "ledger_index": entry.index,
                    "recorded": entry.recorded.isoformat(), "signer": entry.signer,
                })
        return found

    def record_resource_availability(
        self, resource: str, state: str, since: dt.datetime, note: str, declared_by: str,
        identity: Identity,
    ) -> LedgerEntry:
        """Firma lo que una persona declara de si un recurso esta disponible a bordo.

        Solo un recurso del vocabulario cerrado y uno de los dos estados que se pueden firmar
        (`core/resources.py`; «sin declarar» no se firma), y solo con el nombre de quien lo
        dice. Sin cantidades. No hay borrado: se corrige declarando de nuevo, y vale el ultimo.
        """
        resource_rules.check(resource, state)
        if not any(char.isalpha() for char in declared_by):
            raise ValueError("la disponibilidad de un recurso la declara una persona con nombre")
        payload = {
            "subject": RESOURCE_SUBJECT, "resource": resource, "state": state,
            "since": _utc_text(since), "note": note.strip(), "declared_by": declared_by.strip(),
        }
        return self._record_action(RESOURCE_ENTRY_TYPE, payload, identity)

    def resource_declarations(self) -> list[dict[str, Any]]:
        """Las declaraciones de disponibilidad de recursos, tal y como estan firmadas."""
        return self._actions(RESOURCE_SUBJECT, RESOURCE_ENTRY_TYPE, _RESOURCE_FIELDS)

    def record_inventory_count(
        self, identity: Identity, **declared: Any
    ) -> LedgerEntry:
        """Firma el recuento de un articulo del inventario, tal y como lo declara una persona.

        `declared` son los argumentos de `inventory.count_payload`, que valida y normaliza: la
        regla esta en la escritura del asiento, no solo en la ruta. Se corrige contando de
        nuevo; vale el ultimo.
        """
        payload = inventory_rules.count_payload(**declared)
        return self._record_action(INVENTORY_COUNT_ENTRY_TYPE, payload, identity)

    def inventory_counts(self) -> list[dict[str, Any]]:
        """Los recuentos del inventario, tal y como estan firmados."""
        return self._actions(
            inventory_rules.SUBJECT, INVENTORY_COUNT_ENTRY_TYPE, inventory_rules.COUNT_FIELDS,
            optional=inventory_rules.COUNT_OPTIONAL,
        )

    def record_inventory_resupply(
        self, identity: Identity, **declared: Any
    ) -> LedgerEntry:
        """Firma el proximo abastecimiento declarado (`inventory.resupply_payload`)."""
        payload = inventory_rules.resupply_payload(**declared)
        return self._record_action(INVENTORY_RESUPPLY_ENTRY_TYPE, payload, identity)

    def inventory_resupplies(self) -> list[dict[str, Any]]:
        """Los abastecimientos declarados, tal y como estan firmados."""
        return self._actions(
            inventory_rules.SUBJECT, INVENTORY_RESUPPLY_ENTRY_TYPE,
            inventory_rules.RESUPPLY_FIELDS, optional=inventory_rules.RESUPPLY_OPTIONAL,
        )

    def followup_decisions(self, subject: str) -> list[dict[str, Any]]:
        """Adopciones, cierres y decisiones de no adoptar, tal y como estan firmados."""
        return self._actions(
            subject, FOLLOWUP_ENTRY_TYPE, _FOLLOWUP_FIELDS,
            (*_FOLLOWUP_OPTIONAL, *_DECIDED_WITH_OPTIONAL),
        )

    # --- Notas de Tierra a bordo (§5.38.1) ------------------------------------------------- #

    def record_ground_note(
        self, subject: str, kind: str, text: str, signed_by: str, identity: Identity
    ) -> LedgerEntry:
        """Firma una nota de Tierra para un tripulante o para toda la tripulación.

        Las reglas que no dependen de nada (`ground_notes.problem`: clase, filtro de lenguaje,
        formas de mandato, persona con nombre); que el destinatario exista lo mira la API. No hay
        borrado ni edición: una nota equivocada se corrige con otra.
        """
        problem = ground_note_rules.problem(kind, text, signed_by)
        if problem is not None:
            raise ValueError(problem)
        if not subject.strip():
            raise ValueError("una nota de Tierra va a un tripulante o a toda la tripulación")
        return self._record_action(
            GROUND_NOTE_ENTRY_TYPE,
            {
                "subject": subject.strip(),
                "kind": kind,
                "text": text.strip(),
                "signed_by": signed_by.strip(),
            },
            identity,
        )

    def ground_notes(self, *subjects: str) -> list[dict[str, Any]]:
        """Las notas de Tierra a uno o más destinatarios, tal y como están firmadas.

        Una sola pasada del ledger, en orden de asiento: el tripulante y toda la tripulación se
        reparten en el mismo recorrido (`GET /api/ground-notes`).
        """
        return self._actions(frozenset(subjects), GROUND_NOTE_ENTRY_TYPE, _GROUND_NOTE_FIELDS)

    def record_help_request(
        self, subject: str, signed_by: str, reason: str, at: dt.datetime, identity: Identity
    ) -> LedgerEntry:
        """Firma una petición de ayuda urgente de un tripulante (`core/help_requests.py`).

        Las reglas que no dependen de nada (longitudes; ni nombre ni motivo son obligatorios);
        que el tripulante exista lo mira la API. El motivo no pasa el filtro de lenguaje, a
        propósito: son las palabras de quien pide ayuda, no un texto de EMMA.
        """
        problem = help_rules.problem(signed_by, reason)
        if problem is not None:
            raise ValueError(problem)
        if not subject.strip():
            raise ValueError("una petición de ayuda es de un tripulante")
        if at.tzinfo is None:
            raise ValueError("el instante de una petición de ayuda lleva zona horaria")
        return self._record_action(
            HELP_REQUEST_ENTRY_TYPE,
            {
                "subject": subject.strip(),
                "signed_by": signed_by.strip(),
                "reason": reason.strip(),
                "at": at.astimezone(dt.UTC).isoformat(),
            },
            identity,
        )

    def record_help_close(
        self, request_index: int, signed_by: str, identity: Identity
    ) -> LedgerEntry:
        """Da por atendida una petición de ayuda abierta, citándola por su índice.

        Una petición que no existe, o ya atendida, no se cierra: el cierre diría algo falso.
        """
        problem = help_rules.close_problem(signed_by)
        if problem is not None:
            raise ValueError(problem)
        # Comprobar y firmar bajo el mismo cerrojo (reentrante): dos cierres a la vez darían dos
        # asientos para una sola petición.
        with self._lock:
            requests_, closes = self.help_requests()
            requests = {item["ledger_index"]: item for item in requests_}
            if request_index not in requests:
                raise ValueError(f"no hay ninguna petición de ayuda en el asiento {request_index}")
            if str(request_index) in {item["request_index"] for item in closes}:
                raise ValueError(
                    f"la petición de ayuda del asiento {request_index} ya está atendida"
                )
            return self._record_action(
                HELP_CLOSE_ENTRY_TYPE,
                {
                    "subject": requests[request_index]["subject"],
                    "request_index": str(request_index),
                    "signed_by": signed_by.strip(),
                },
                identity,
            )

    def help_requests(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Las peticiones de ayuda y sus cierres de toda la tripulación, tal y como se firmaron."""
        subjects = frozenset(self.subjects())
        return (
            self._actions(subjects, HELP_REQUEST_ENTRY_TYPE, _HELP_REQUEST_FIELDS),
            self._actions(subjects, HELP_CLOSE_ENTRY_TYPE, _HELP_CLOSE_FIELDS),
        )

    def record_planner_changeset(
        self, changeset_b64: str, expected: int, written_by: str, identity: Identity
    ) -> LedgerEntry:
        """Anexa una transaccion de Marplanner, solo si quien escribe esta al dia.

        `expected` es cuantos changesets habia reproducido quien escribe. Si no coincide con
        los que hay, su base en memoria no es la del ledger y aplicar su cambio encima daria
        una base que nadie ha visto: se rechaza (`PlannerConflict`) y tiene que releer.
        """
        try:
            raw = base64.b64decode(changeset_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("el changeset no es base64 válido") from exc
        if not raw:
            raise ValueError("changeset vacío: una transacción sin cambios no se anota")
        if len(raw) > PLANNER_MAX_CHANGESET_BYTES:
            raise ValueError(f"changeset de {len(raw)} bytes, tope {PLANNER_MAX_CHANGESET_BYTES}")
        if not any(char.isalpha() for char in written_by):
            raise ValueError("el changeset lo firma un escritor con nombre")
        payload = {
            "subject": PLANNER_SUBJECT,
            "changeset": base64.b64encode(raw).decode("ascii"),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "written_by": written_by.strip(),
        }
        with self._planner_lock:
            seen = len(self.planner_changesets())
            if expected != seen:
                raise PlannerConflict(f"hay {seen} changesets y quien escribe vio {expected}")
            return self._record_action(PLANNER_ENTRY_TYPE, payload, identity)

    def planner_changesets(self, after: int = 0) -> list[dict[str, Any]]:
        """Los changesets de Marplanner en orden, desde el numero `after`, comprobados.

        Ademas del hash firmado del asiento (`_actions`), se comprueba que el changeset sea la
        huella que dice: base64 alterado en disco con su `sha256` intacto no llega a reproducirse.
        """
        if after < 0:
            raise ValueError("`after` no puede ser negativo")
        items = self._actions(PLANNER_SUBJECT, PLANNER_ENTRY_TYPE, _PLANNER_FIELDS)
        out = []
        for seq, item in enumerate(items, start=1):
            if seq <= after:
                continue
            raw = base64.b64decode(item["changeset"])
            if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise TamperedRecordError(
                    f"asiento {item['ledger_index']}: el changeset no es el de su huella"
                )
            out.append({"seq": seq, **{k: item[k] for k in (
                "changeset", "sha256", "written_by", "ledger_index", "recorded", "signer"
            )}})
        return out

    def _record_action(
        self, entry_type: str, payload: dict[str, Any], identity: Identity
    ) -> LedgerEntry:
        """Una accion del operador, al ledger y al disco en un solo `commit`.

        Mismo cuidado que `record_many`: si el `commit` falla, el asiento se retira de
        la cadena en memoria, y una identidad nueva no queda fijada sin estar en disco.
        """
        with self._lock:
            start = len(self.ledger)
            self._before_own_write()
            try:
                with self.ledger.transaction():
                    new_key = self.registry.register(
                        identity.identity_id, identity.public_key_hex
                    )
                    entry = self.ledger.append(entry_type, payload, identity)
                    with Session(self.engine) as session:
                        if new_key:
                            session.add(_trusted_key_row(identity))
                        session.add(_ledger_row(entry))
                        session.commit()
            except BaseException:
                self._after_failed_write(start)
                raise
            else:
                self._advance_after_own_write(start)
        return entry

    def _actions(
        self, subject: str | frozenset[str], entry_type: str, fields: tuple[str, ...],
        optional: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        """Las acciones de un tipo, con las mismas garantias que `query()`.

        `subject` puede ser un conjunto: las de todos ellos, en una sola pasada.

        Solo se entrega lo que coincide con su hash firmado. Una accion fabricada o
        alterada en disco no puede silenciar una alerta: se detecta y es un 409.

        `optional` son campos que solo llevan algunos asientos del tipo (el modulo de una
        ubicacion): si estan, tienen que ser texto como los demas; si no, no se entregan.
        """
        wanted = {subject} if isinstance(subject, str) else subject
        with self._lock:
            entries = self.ledger._view()
            self._check_unverified_content(entries)
            trusted = self._content_trusted()

        found: list[dict[str, Any]] = []
        for entry in entries:
            if entry.entry_type != entry_type or not isinstance(entry.payload, dict):
                continue
            if entry.index >= trusted and not _content_matches(entry):
                raise TamperedRecordError(
                    f"asiento {entry.index}: el contenido no coincide con su hash firmado"
                )
            payload = entry.payload
            if any(not isinstance(payload.get(field), str) for field in fields):
                raise TamperedRecordError(f"asiento {entry.index}: acción mal formada")
            present = [field for field in optional if field in payload]
            if any(not isinstance(payload[field], str) for field in present):
                raise TamperedRecordError(f"asiento {entry.index}: acción mal formada")
            if payload["subject"] not in wanted:
                continue
            found.append(
                {
                    **{field: payload[field] for field in (*fields, *present)},
                    "ledger_index": entry.index,
                    "recorded": entry.recorded.isoformat(),
                    # Quien firmo la accion: el estado solo respeta las de la consola.
                    "signer": entry.signer,
                }
            )
        return found

    def reading_signers(self) -> set[str]:
        """Quien firmo las lecturas de la cadena, incluidas redactadas y enmiendas.

        Sirve para saber si el almacen contiene algun registro real. Una lectura real
        redactada sigue siendo un registro real: la lapida da fe de ella. Por eso se
        mira el firmante del asiento, que se conserva aunque se suprima el contenido.
        """
        with self._lock:
            entries = self.ledger._view()
        # Los estudios de imagen cuentan: una ecografia real es un registro real, y
        # cambiar de escenario simulado la borraria junto con el almacen.
        return {entry.signer for entry in entries if entry.entry_type in _CLINICAL_ENTRY_TYPES}

    def audit_trail(self, limit: int = 50) -> list[dict[str, Any]]:
        """Registro de auditoria legible, para inspeccion y exportacion."""
        with self._lock:
            entries: Sequence[LedgerEntry] = self.ledger._view()[-limit:]
        return [_audit_view(entry) for entry in entries]

    def merkle_root(self) -> str:
        """Los 32 bytes que se transmiten a Tierra para anclar la cadena."""
        with self._lock:
            return self.ledger.merkle_root()

    def anchor(self) -> Anchor:
        """Lo que viajaria a Tierra: la raiz, cuantas entradas cubre y el algoritmo."""
        with self._lock:
            return self.ledger.anchor()

    def audit_snapshot(
        self, limit: int = 50
    ) -> tuple[VerificationResult, Anchor | None, list[dict[str, Any]], int]:
        """Verificacion, ancla y traza de un mismo instante, bajo un solo cerrojo.

        Hechas por separado, entre la verificacion y el ancla podia entrar un asiento, y
        se publicaba un ancla que cubria entradas sin verificar. Con la cadena rota no
        hay ancla: no hay nada fiable que anclar, y calcularla sobre una cabecera danada
        lanzaba justo cuando `/api/audit` tenia que mostrar el fallo.
        """
        with self._lock:
            verification = self.verify_integrity()
            return (
                verification,
                self.anchor() if verification.ok else None,
                self.audit_trail(limit),
                len(self.ledger),
            )


# Una sola identidad de simulador por proceso: el registro fija cada identidad a su
# primera clave, y generar una nueva en cada siembra chocaria con la anterior.
_simulator_identity: Identity | None = None


def _default_simulator_identity() -> Identity:
    global _simulator_identity
    if _simulator_identity is None:
        _simulator_identity = Identity.generate("simulator")
    return _simulator_identity


def seed_from_simulator(
    store: ObservationStore,
    observations: Iterable[VitalObservation],
    identity: Identity | None = None,
) -> int:
    """Carga una serie simulada en el almacen, auditada como cualquier otra.

    El simulador no tiene privilegios: sus datos entran por la misma puerta y
    quedan firmados con una identidad que los declara como simulados.
    """
    signer = identity or _default_simulator_identity()
    return len(store.record_many((replace(obs) for obs in observations), signer))
