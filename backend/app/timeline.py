# SPDX-License-Identifier: AGPL-3.0-or-later
"""Crónica, "esta semana" y "qué depende de este dato": tres piezas de Polaris con datos de EMMA.

Por qué existe: la especificación pide una línea temporal (preflight → misión → intervención →
seguimiento) y que todo sea trazable. Polaris ya tiene las tres piezas; aquí se les dan los datos
de EMMA en vez de los de su autora (decisión del usuario, 2026-10-01: en las consolas).

* **Crónica** (`cronica.py`): sus eventos tienen la forma `{fecha, tipo, que, quien, fuente,
  clave, externo}`, con una clave estable para no repetir. Sus cosechadores leen el git y las
  carpetas de su autora; aquí los eventos salen del ledger de EMMA (reconocimientos, estados y
  silencios de alertas, contramedidas, eventos de misión, ubicaciones declaradas, estado
  declarado de los sistemas del hábitat, vínculos sensor-tripulante declarados, recursos
  declarados, fases de contraste declaradas de un TAC, modo seguro y, desde el 2026-11-03,
  cambios de nivel de misión),
  con el número de asiento como clave (`ledger:<asiento>`) y, desde el 2026-10-07, también del
  estado ya calculado, de las fases de misión y de la cabina, con clave propia; desde el
  2026-10-14, también las tomas posvuelo frente al prevuelo propio (`analysis/recovery.py`;
  desde el 2026-10-16, un evento por indicador y día tras el regreso, clave
  `recovery:<indicador>:R+<día>`); desde el 2026-10-23, las misiones previas del historial
  declarado (`core/mission_history.py`), en una etapa «carrera» antes del prevuelo, clave
  `ledger:<asiento>:mission:<n>`. Se sanean como
  en `cronica.cosechar` y se escriben con su `_linea_bitacora`.
* **Esta semana** (`anticipa.py`): `esta_semana()` proyecta hoy..+N días sobre los asuntos de
  `seguimiento.recopilar()` y el foco de `cumbre`. Aquí, durante la llamada, `recopilar()` devuelve
  lo datado de EMMA (fin de la ventana de seguimiento de cada contramedida, horizonte de cada
  proyección, eventos de misión futuros) y `cumbre.foco()` nada: la cadena "hacia NED" es del caso
  de su autora, no de una misión. También se sustituye su `date` por uno cuyo `today()` es el día
  de los datos: `anticipa` lee el reloj del ordenador, que no es el de una misión simulada.
* **Qué depende de este dato** (`cascada_mapa.py`): su `afectados()` es el cierre transitivo sobre
  un mapa dato → dependientes. Aquí el mapa es el de EMMA: indicador → dominio de riesgo, región
  anatómica, contramedidas cuyo seguimiento lo mide, línea base y proyección.

Las sustituciones son temporales y bajo cerrojo, como en `reports/identity.py`: la copia no se
toca.

Licencia y origen (AGPL §5a): usa `polaris/tools/cronica.py`, `polaris/tools/anticipa.py`,
`polaris/tools/cascada_mapa.py`, `polaris/tools/seguimiento.py` y `polaris/tools/cumbre.py` de la
copia literal de Polaris, sin modificarla (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later,
© 2026 la autora de Polaris, «Beyond the Protocol»); se cargan con `app.polaris.load`. De EMMA:
los eventos del ledger y del estado, los asuntos datados y el mapa de dependencias que se les
dan, y las sustituciones temporales de arriba.
"""

from __future__ import annotations

import datetime as dt
import math
import re
import threading
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import cache
from typing import Any, Self

from app import anatomy, polaris
from app.advisor import countermeasures
from app.analysis import recovery
from app.core import display, i18n, mission_history, mission_modes, mission_profile_changes
from app.core import resources as declared_resources
from app.core import shift as shift_event
from app.core.identities import CONSOLE_IDENTITY, action_counts
from app.core.mission import MissionPhase, mission_day, phase_at
from app.core.storage import (
    _MISSION_MODE_FIELDS,
    _MISSION_MODE_OPTIONAL,
    _MISSION_PROFILE_FIELDS,
    DISMISSAL_REASONS,
    MISSION_MODE_ENTRY_TYPE,
    MISSION_MODE_SUBJECT,
    MISSION_PROFILE_ENTRY_TYPE,
    MISSION_PROFILE_SUBJECT,
    RULES_VERSION_FIELD,
    TamperedRecordError,
)
from app.core.versioning import decided_with
from app.environment import systems as habitat_systems
from app.environment.habitat import LIMIT_KINDS, excursions, latest_by_parameter, parameter
from app.ingest import bindings as sensor_bindings
from app.ingest import inspiration4
from app.ingest.codes import CATALOG, DESCRIPTIVE_ONLY
from app.ingest.fhir import VitalObservation
from app.volumes import contrast_phase

_LOCK = threading.Lock()


@cache
def _tool(name: str) -> Any:
    return polaris.load(name)


# --------------------------------------------------------------------------- #
# El "ahora" de la línea temporal
# --------------------------------------------------------------------------- #
#
# Una misión simulada, o una real que se revisa meses después, vive en el tiempo de sus datos y
# no en el del ordenador. Con `date.today()`, "esta semana" de una misión que despega en
# noviembre no enseñaba nada en octubre, y la crónica fechaba cada hecho con la hora a la que
# alguien pulsó un botón. El ahora de la línea temporal es el que ya tiene todo EMMA: el instante
# de referencia de `/api/status` (`data.reference_time`, la última lectura analizable, o la última
# que Tierra tiene). Este módulo no lee ningún reloj: se lo da quien lo llama, y solo se usa si
# no hay lecturas. De dónde sale el ahora va siempre en la respuesta.

_AS_OF_BASIS = {
    "data": "última lectura analizada: el instante de referencia de /api/status",
    "cut": "sin lecturas analizables hasta el corte pedido: el propio corte",
    "clock": "sin lecturas analizables: reloj real del sistema",
}
i18n.en_many({
    _AS_OF_BASIS["data"]: "last reading analysed: the reference instant of /api/status",
    _AS_OF_BASIS["cut"]: "no analysable readings up to the requested cut-off: the cut-off itself",
    _AS_OF_BASIS["clock"]: "no analysable readings: the real system clock",
})


@dataclass(frozen=True, slots=True)
class AsOf:
    """El ahora de la línea temporal y de dónde sale (`data`, `cut` o `clock`)."""

    moment: dt.datetime
    source: str

    def to_dict(self) -> dict[str, str]:
        return {
            "as_of": self.moment.isoformat(),
            "as_of_source": self.source,
            "as_of_basis": i18n.loc(_AS_OF_BASIS[self.source]),
        }


def as_of(status: dict[str, Any], until: dt.datetime | None, clock: dt.datetime) -> AsOf:
    """El ahora: el del estado si hay lecturas; si no, el corte de Tierra o, al final, `clock`."""
    reference = (status.get("data") or {}).get("reference_time")
    if reference:
        return AsOf(_instant(reference), "data")
    if until is not None:
        return AsOf(until.astimezone(dt.UTC), "cut")
    return AsOf(clock.astimezone(dt.UTC), "clock")


def _instant(text: str) -> dt.datetime:
    """Un instante del ledger o del estado, en UTC (el que venga sin zona se toma como UTC)."""
    moment = dt.datetime.fromisoformat(text)
    return (moment if moment.tzinfo else moment.replace(tzinfo=dt.UTC)).astimezone(dt.UTC)


# --------------------------------------------------------------------------- #
# Crónica
# --------------------------------------------------------------------------- #
#
# Cuenta lo que pasó, no solo lo que hizo el operador, y no decide nada: cada hecho sale de algo
# que EMMA ya tiene.
#
#   * del ledger, lo firmado: reconocimientos, estados y silencios de una alerta, contramedidas
#     adoptadas y cerradas, eventos del plan de misión, modo seguro y nivel de misión, con la
#     regla con que el
#     estado los cuenta: lo que firma la consola (`action_counts`; desde el 2026-10-26, antes
#     cualquier firmante);
#   * del estado ya calculado (`/api/status`): desde cuándo está cada alerta activa (`onset`),
#     qué dominio cambió de nivel frente a una ventana antes (su trayectoria; es el único cierre
#     de una alerta que el análisis conoce) y el fin de cada ventana de seguimiento;
#   * de `core/mission.py`, los cambios de fase, y de `environment/habitat.py`, las excursiones;
#   * de `analysis/recovery.py`, las tomas posvuelo de cada día frente al rango prevuelo del
#     tripulante.
#
# De una alerta que empezó y acabó hace más de una ventana solo quedaba rastro si alguien actuó: el
# análisis no guarda historia. Desde el 2026-10-10 se vuelve a calcular el pasado al pedir la
# crónica (`analysis/alert_history.py`) y sus episodios cerrados se cuentan, marcados como lo que
# son —un recálculo de hoy con las reglas de hoy, no lo que se enseñó entonces— y sin firmar nada.
#
# DOS RELOJES, Y SE DICE CUÁL. Un hecho va en el tiempo de los datos: el de su lectura o, si es
# una decisión, el del estado sobre el que se tomó (`reference_time`, como en el tiempo hasta la
# acción de cada alerta). Un asiento que no declara ningún instante de datos —declarar un evento,
# el modo seguro— solo tiene su hora de firma, que es la del ordenador: va aparte, no se mezcla.
#
# Nada de lo calculado es posterior al ahora. Lo firmado sí se cuenta siempre: ya pasó.

# Las etapas de la especificación (§10): preflight → día de misión → intervención → seguimiento
# → postflight. La última no es suya: es donde va lo que no se puede situar en la misión. La
# primera tampoco (2026-10-23): la carrera de antes, las misiones previas que declaró una persona
# (§3 `mission_history`; «Career baseline → Mission 1 → Recovery → Mission 2 → …» de la
# conversación de ideación).
STAGES: tuple[tuple[str, str], ...] = (
    ("career", "carrera: misiones previas declaradas"),
    ("preflight", MissionPhase.PREFLIGHT.display),
    ("mission-day", "día de misión"),
    ("intervention", "intervención"),
    ("followup", "seguimiento"),
    ("postflight", MissionPhase.POSTFLIGHT.display),
    ("unplaced", "sin instante de datos: hora de firma del asiento"),
)
# El inglés de las etapas propias (`core/i18n.py`). Las dos que son una fase de misión toman su
# nombre de `MissionPhase` al servir (`_stage_display`), no de lo que se copió aquí al importar.
i18n.en_many({
    "carrera: misiones previas declaradas": "career: declared prior missions",
    "día de misión": "mission day",
    "intervención": "intervention",
    "seguimiento": "follow-up",
    "sin instante de datos: hora de firma del asiento": (
        "no data instant: signing time of the entry"
    ),
})
_STAGE_PHASES = {"preflight": MissionPhase.PREFLIGHT, "postflight": MissionPhase.POSTFLIGHT}


def _stage_display(key: str, text: str) -> str:
    """El rótulo de una etapa en el idioma de la petición; las claves no se traducen."""
    phase = _STAGE_PHASES.get(key)
    return i18n.loc(phase.display if phase is not None else text)


# Los relojes de un hecho, en el orden en que se cuentan (`chronicle`): la fecha que declaró una
# persona para su carrera, el instante de los datos y, si no hay otro, la hora de firma.
_CLOCK_ORDER = {"declared": 0, "data": 1, "recorded": 2}

# Quién firma lo que nadie firmó: lo que sale del análisis, del calendario o de la cabina.
_SYSTEM = "EMMA"

_EXCURSION_KIND = LIMIT_KINDS
_ANNUNCIATION = {"suppress": "suprimido", "inhibit": "inhibido", "enable": "rehabilitado"}
i18n.en_many({"suprimido": "suppressed", "inhibido": "inhibited", "rehabilitado": "re-enabled"})
# Una ubicación declarada (`mission-event` de tipo `location`) llega con los eventos de misión.
# Es un hecho firmado y se cuenta, con su nombre. Pero no es un evento del plan: dice dónde
# estaba el tripulante, y su intervalo no es algo que «empiece» y «termine» en la crónica ni un
# asunto de los próximos días. Sin esto salía «location declarada: Laboratorio», «location:
# Laboratorio, inicio» y «location: Laboratorio» entre lo que viene esta semana.
_LOCATION_KIND = "location"


@dataclass(frozen=True, slots=True)
class _Mission:
    """El calendario de la misión y el ahora: lo que hace falta para situar un hecho."""

    start: dt.date
    duration_days: int
    now: AsOf

    def stage(self, at: dt.datetime, basis: str, in_flight: str) -> str:
        """Antes del despegue y tras el regreso manda la fecha; en vuelo, la clase de hecho.

        Una fecha declarada (`declared`, la carrera) no se sitúa con el calendario de esta
        misión: va en la etapa que se le da. Lo que solo tiene hora de firma, aparte.
        """
        if basis == "declared":
            return in_flight
        if basis != "data":
            return "unplaced"
        phase = phase_at(at, self.start, self.duration_days)
        if phase is MissionPhase.PREFLIGHT:
            return "preflight"
        if phase is MissionPhase.POSTFLIGHT:
            return "postflight"
        return in_flight


def _event(
    mission: _Mission, at: dt.datetime, kind: str, fact: str, what: str, who: str, source: str,
    key: str, *, stage: str = "mission-day", basis: str = "data", recorded: str | None = None,
    level: str | None = None, severity: str | None = None, recomputed: bool = False,
) -> dict[str, Any]:
    """Un evento con la forma de `cronica.py`, saneado como en su `cosechar`, y lo de EMMA."""
    # UTC es el reloj de la misión: una lectura firmada con otro desfase no cambia de día.
    at = at.astimezone(dt.UTC)
    return {
        "fecha": at.date().isoformat(),
        "tipo": kind,
        "que": re.sub(r"\s+", " ", what).strip()[:280],
        "quien": re.sub(r"\s+", " ", who or "—").strip()[:60],
        "fuente": source,
        "clave": key,
        "externo": False,
        # Lo que EMMA añade a la forma de Polaris: el instante entero y de qué reloj sale, la
        # hora de firma si es un asiento, el día de misión, la etapa de §10, qué hecho es y, si
        # lo hay, el nivel de la alerta o la clase del límite de cabina.
        "at": at.isoformat(),
        "time_basis": basis,
        "recorded": recorded,
        "mission_day": math.floor(mission_day(at, mission.start)) if basis == "data" else None,
        "stage": mission.stage(at, basis, stage),
        "fact": fact,
        "level": level,
        "severity": severity,
        # Ni firmado ni leído del estado: recalculado hoy (`analysis/alert_history.py`).
        "recomputed": recomputed,
    }


def _signed(
    mission: _Mission, until: dt.datetime | None, item: dict[str, Any], field: str | None,
    kind: str, fact: str, what: str, who: str, stage: str = "mission-day",
    level: str | None = None, *, decided: bool = False,
) -> Iterator[dict[str, Any]]:
    """Un asiento, en el instante de datos que declara (`field`) o, si no declara, en su firma.

    Para Tierra (`until`) solo existe lo ya firmado en su corte, que es la regla de
    `/api/status`, y cuyo instante de datos tampoco lo pasa. Lo firmado después del corte lo
    quita antes quien llama, con la regla del estado (`action_counts`); aquí queda el instante
    de datos, y con él el modo seguro, que no declara otro que su firma. Desde el 2026-10-26
    (§5.38.10) no se repite aquí la comparación de la firma: con las dos, ninguna prueba podía
    distinguir que faltara una.

    Con `decided`, el asiento es una decisión sobre una alerta o una contramedida y su fuente
    dice además con qué reglas se firmó, frente a las de hoy (`record-integrity.md` §3.26):
    «asiento 12; decidido con reglas@…; misma versión que hoy», o «sin versión registrada» si
    el asiento es anterior al campo. Leído del asiento; aquí no se recalcula nada.
    """
    recorded = _instant(item["recorded"])
    at = _instant(item[field]) if field else recorded
    if until is not None and at > until:
        return
    index = item["ledger_index"]
    source = i18n.tr(f"asiento {index}", f"entry {index}")
    if decided:
        source = f"{source}; {decided_with(item.get(RULES_VERSION_FIELD))['text']}"
    yield _event(
        mission, at, kind, fact, what, who, source,
        key=f"ledger:{index}",
        stage=stage, basis="data" if field else "recorded", recorded=recorded.isoformat(),
        level=level,
    )


def _ledger_events(
    store: Any, subject: str, mission: _Mission, until: dt.datetime | None
) -> Iterator[dict[str, Any]]:
    """Lo que decidió una persona, tal y como está firmado, si el estado lo cuenta.

    El estado solo cuenta lo que firma la consola (`identities.action_counts`), y un descarte o
    un silencio que la API no habría aceptado tampoco. La crónica, con lo mismo que lee el estado:
    lo de las alertas y las contramedidas, de `routes._signed_actions`; lo demás, con
    `action_counts`. Antes
    contaba cualquier «en arreglo», «resuelto» o descarte, lo firmara quien lo firmara, y contaba
    como cerrado un arreglo que el estado seguía viendo abierto (decisión del usuario,
    2026-10-26). Lo que no cuenta se omite, no se marca: sigue en el ledger, que lo conserva y lo
    verifica, pero un hecho de la crónica es algo que EMMA tuvo en cuenta. El modo seguro es la
    excepción porque también lo es en el estado: vale el último asiento, lo firme quien lo firme
    (`storage.safe_mode`). Las rutas importan este módulo: `_signed_actions` se lee al usarla.
    """
    from app.api.routes import _signed_actions

    def counted(items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        return [item for item in items if action_counts(item, until)]

    signed = _signed_actions(store, subject, until)
    # Las decisiones sobre alertas y contramedidas llevan en su fuente con qué reglas se firmaron
    # (`decided=True`, §3.26): el silencio y lo declarado del plan o del hábitat, no.
    for item in signed.acknowledgements:
        yield from _signed(
            mission, until, item, "reference_time", "alerta", "alert-acknowledged",
            i18n.tr(
                f"alerta {item['domain']}:{item['level']} reconocida",
                f"alert {item['domain']}:{item['level']} acknowledged",
            ),
            item["acknowledged_by"], "intervention", item["level"], decided=True)
    for item in signed.resolutions:
        working = item["state"] == "en_arreglo"
        yield from _signed(
            mission, until, item, "reference_time", "alerta",
            "alert-in-progress" if working else "alert-resolved",
            i18n.tr(
                f"alerta {item['domain']}:{item['level']} "
                f"{'en arreglo' if working else 'resuelta'}",
                f"alert {item['domain']}:{item['level']} "
                f"{'in progress' if working else 'resolved'}",
            ),
            item["declared_by"], "intervention" if working else "followup", item["level"],
            decided=True)
    for item in signed.dismissals:
        # Descartar una alerta (§3.20 bis de `record-integrity.md`): la decisión, con su motivo.
        # La nota (hasta 300 caracteres) se corta a la vista, con «…», para que quepa en el
        # hecho (280): cortada en silencio parecería entera.
        reason = i18n.loc(DISMISSAL_REASONS.get(item["reason"], item["reason"]))
        head = i18n.tr(
            f"alerta {item['domain']}:{item['level']} descartada; motivo: {reason}",
            f"alert {item['domain']}:{item['level']} dismissed; reason: {reason}",
        )
        note = re.sub(r"\s+", " ", item["note"]).strip()
        room = 280 - len(head) - len(" ()")
        if len(note) > room:
            note = note[: max(room - 1, 0)] + "…"
        yield from _signed(
            mission, until, item, "reference_time", "alerta", "alert-dismissed",
            f"{head} ({note})" if note else head,
            item["declared_by"], "intervention", item["level"], decided=True)
    for item in signed.changes:
        # Dejar de anunciar una alerta también es una decisión firmada, con su motivo.
        done = i18n.loc(_ANNUNCIATION.get(item["action"], item["action"]))
        yield from _signed(
            mission, until, item, "reference_time", "alerta", f"annunciation-{item['action']}",
            i18n.tr(
                f"anuncio de alertas de {item['domain']}: {done}; motivo: {item['reason']}",
                f"alert annunciation for {item['domain']}: {done}; reason: {item['reason']}",
            ),
            item["requested_by"], "intervention", item["level"] or None)
    for item in signed.decisions:
        adopted = item["action"] == "adopted"
        if item["action"] == "declined":
            # Decidir no actuar tambien se cuenta, con su motivo: es una decision firmada, no
            # una evaluacion, y no cierra ni silencia nada (`advisor/followup.py`).
            declined = i18n.tr(
                f"contramedida {item['countermeasure_id']}: se decidió no adoptarla; "
                f"motivo: {item['reason']}",
                f"countermeasure {item['countermeasure_id']}: it was decided not to adopt it; "
                f"reason: {item['reason']}",
            )
            yield from _signed(
                mission, until, item, "reference_time", "contramedida",
                "countermeasure-declined", declined,
                item["decided_by"], "intervention", decided=True)
            continue
        yield from _signed(
            mission, until, item, "reference_time", "contramedida",
            "countermeasure-adopted" if adopted else "countermeasure-closed",
            i18n.tr(
                f"contramedida {item['countermeasure_id']} "
                f"{'adoptada' if adopted else 'cerrada'}",
                f"countermeasure {item['countermeasure_id']} "
                f"{'adopted' if adopted else 'closed'}",
            ),
            item["decided_by"], "intervention" if adopted else "followup", decided=True)
    for item in counted(store.mission_events(subject)):
        located = item["kind"] == _LOCATION_KIND
        if located:
            what = i18n.tr(
                f"ubicación declarada: {item['label']}", f"location declared: {item['label']}"
            )
        elif item["kind"] == shift_event.KIND:
            what = i18n.tr(
                f"{_event_kind(item['kind'])} declarado: {item['label']}",
                f"{_event_kind(item['kind'])} declared: {item['label']}",
            )
        else:
            what = i18n.tr(
                f"{item['kind']} declarada: {item['label']}",
                f"{item['kind']} declared: {item['label']}",
            )
        yield from _signed(
            mission, until, item, None, "mision",
            "location-declared" if located else "mission-event-declared", what,
            item["declared_by"])
    # El estado de un sistema del hábitat que declaró una persona (`environment/systems.py`).
    # No es de un tripulante: sale en la crónica de todos, en el instante al que se refiere,
    # y la frase lleva su rótulo: es una declaración, no telemetría.
    for item in habitat_systems.history(counted(store.system_statuses())):
        yield from _signed(
            mission, until, item, "at", "habitat", "system-status-declared",
            habitat_systems.sentence(item), item["declared_by"])
    # El vínculo sensor-tripulante que declaró una persona (`ingest/bindings.py`). Es de la
    # tripulación: sale en la crónica de todos, en el instante desde el que vale, con su rótulo
    # y sin el identificador del dispositivo, que puede ser un dato personal.
    for item in sensor_bindings.history(counted(store.sensor_bindings())):
        yield from _signed(
            mission, until, item, "since", "sensor",
            "sensor-binding-declared" if item["bound"] else "sensor-binding-withdrawn",
            sensor_bindings.sentence(item), item["declared_by"])
    # La disponibilidad de un recurso de a bordo que declaró una persona (`core/resources.py`).
    # Es de la misión: sale en la crónica de todos, en el instante desde el que vale, con su
    # rótulo: es una declaración, no un inventario.
    for item in declared_resources.history(counted(store.resource_declarations())):
        yield from _signed(
            mission, until, item, "since", "recurso", "resource-availability-declared",
            declared_resources.sentence(item), item["declared_by"])
    # La fase de contraste de un TAC que declaró una persona (`volumes/contrast_phase.py`). Es
    # del tripulante del estudio, en el instante que declara, con su rótulo y sin la nota ni
    # nada del volumen. Solo de estudios vigentes y lo que la consola habría enseñado
    # (`contrast_phase.history`): un estudio redactado se lleva sus declaraciones.
    declared = store.contrast_phase_declarations(subject)
    for study in store.volume_studies(subject) if declared else []:
        previous = None
        for item in contrast_phase.history(declared, study, CONSOLE_IDENTITY):
            yield from _signed(
                mission, until, item, "at", "imagen", "contrast-phase-declared",
                contrast_phase.sentence(item, study["ledger_index"], previous),
                item["declared_by"])
            previous = item
    safe = store._actions("sistema", "safe-mode", ("subject", "active", "reason", "declared_by"))
    for item in safe:
        active = item["active"] == "true"
        yield from _signed(
            mission, until, item, None, "sistema", "safe-mode-on" if active else "safe-mode-off",
            i18n.tr("modo seguro activado: ", "safe mode turned on: ") + item["reason"]
            if active else i18n.tr("modo seguro levantado", "safe mode lifted"),
            item["declared_by"])
    # El nivel de misión (`core/mission_modes.py`, §3.27): cada cambio, con el nivel que dejaba
    # atrás y el nuevo, quién lo firmó y su motivo. Como el modo seguro, no declara instante de
    # datos y va en su hora de firma; a diferencia de él, cuenta lo que cuenta el estado
    # (`storage.mission_mode`: lo firmado por la consola y, para Tierra, lo que existía en su
    # corte). El anterior sale de esos mismos asientos: uno redactado ya no está, y el siguiente
    # cuenta desde el que quede, como la versión, que baja en uno.
    levels = counted(store._actions(
        MISSION_MODE_SUBJECT, MISSION_MODE_ENTRY_TYPE, _MISSION_MODE_FIELDS,
        _MISSION_MODE_OPTIONAL,
    ))
    try:
        changes = mission_modes.history(levels)
    except ValueError as exc:  # firmado pero inservible: un 409, como en el estado
        raise TamperedRecordError(str(exc)) from exc
    for left, change in changes:
        item = dict(change)
        yield from _signed(
            mission, until, item, None, "sistema", "mission-mode-change",
            mission_modes.chronicle_sentence(left, change), change["declared_by"])
    # El entorno de la misión (`core/mission_profile_changes.py`): cada cambio, con el que dejaba
    # atrás tal como se firmó (`previous`) y el nuevo. Como el nivel, en su hora de firma y con lo
    # que cuenta el estado (`storage.mission_profile`). Uno inservible es el mismo 409.
    for item in counted(store._actions(
        MISSION_PROFILE_SUBJECT, MISSION_PROFILE_ENTRY_TYPE, _MISSION_PROFILE_FIELDS,
    )):
        problem = mission_profile_changes.entry_problem(item)
        if problem is not None:
            raise TamperedRecordError(f"asiento {item['ledger_index']}: {problem}")
        yield from _signed(
            mission, until, item, None, "sistema", "mission-profile-change",
            mission_profile_changes.chronicle_sentence(item), item["declared_by"])


def _career_events(
    career: dict[str, Any] | None, mission: _Mission
) -> Iterator[dict[str, Any]]:
    """Las misiones previas del historial vigente, una por hecho, en la etapa «carrera».

    `career` es el historial que vale (`api/mission.latest_mission_history`: el último firmado
    por la consola y, para Tierra, el que ya existía en su corte), o None. Solo el vigente: uno
    anterior está sustituido, como el perfil. Cada misión va en su fecha de inicio declarada, que
    es un tercer reloj (`declared`): ni el de los datos ni el de la firma, y con precisión de día.
    La frase dice lo declarado y nada más; la fuente, de qué asiento sale y que nadie lo ha
    comprobado. Sin veredicto ni cotejo (eso es `/crew/mission-history`), y nada de aquí entra
    en la dosis de carrera, que sigue leyendo solo el perfil.
    """
    if career is None:
        return
    index = career["ledger_index"]
    source = f"asiento {index}: {mission_history.CHRONICLE_SOURCE}"
    if i18n.current() == "en":
        source = f"entry {index}: {i18n.loc(mission_history.CHRONICLE_SOURCE)}"
    for number, item in enumerate(career["missions"], start=1):
        start = dt.datetime.combine(item.start, dt.time(), dt.UTC)
        yield _event(
            mission, start, "carrera", "prior-mission-declared",
            mission_history.chronicle_sentence(item), career["declared_by"], source,
            key=f"ledger:{index}:mission:{number}", stage="career", basis="declared",
            recorded=_instant(career["recorded"]).isoformat(),
        )


def _analysis_source(rules: Any) -> str:
    """La fuente de un hecho que sale del estado calculado: con qué reglas."""
    return i18n.tr(f"análisis del estado, reglas {rules}", f"status analysis, rules {rules}")


def _analysis_events(status: dict[str, Any], mission: _Mission) -> Iterator[dict[str, Any]]:
    """Lo que el estado ya dice de cada alerta: desde cuándo, y qué dominio cambió de nivel."""
    for alert in status.get("alerts") or []:
        detail = alert.get("detail") or {}
        name = f"{alert['domain']}:{alert['level']}"
        onset = detail.get("onset")
        basis = detail.get("onset_basis") or "—"
        # Sin lectura que la feche (viene de una tendencia o de un evento externo) se anota en
        # el ahora, que es cuando consta que está activa: no se le inventa un inicio.
        yield _event(
            mission, _instant(onset) if onset else mission.now.moment, "alerta",
            "alert-onset" if onset else "alert-active",
            i18n.tr(
                f"inicio de la alerta {name}: {basis}", f"onset of alert {name}: {basis}"
            ) if onset
            else i18n.tr(
                f"alerta {name} activa, sin inicio que fechar: {basis}",
                f"alert {name} active, with no onset to date: {basis}",
            ),
            _SYSTEM, _analysis_source(alert.get("rules_version", "—")),
            f"alert-onset:{name}:{onset or 'sin-lectura'}", level=alert["level"])
    for domain, risk in (status.get("domains") or {}).items():
        change = risk.get("trajectory")
        if change:
            yield _event(
                mission, mission.now.moment, "alerta", "level-change",
                i18n.tr(
                    f"dominio {domain}: {change['basis']}", f"domain {domain}: {change['basis']}"
                ),
                _SYSTEM, _analysis_source(status.get("rules_version", "—")),
                f"level-change:{domain}:{change['from_level']}:{change['to_level']}:"
                f"{change['since']}", level=change["to_level"])


def _recomputed_events(
    history: dict[str, Any] | None, mission: _Mission
) -> Iterator[dict[str, Any]]:
    """Los episodios ya cerrados de la historia recalculada (`analysis/alert_history.py`).

    Son lo único de la crónica que ni está firmado ni lo dice el estado: se recalcula al
    pedirla. Por eso cada frase empieza por su rótulo, la fuente dice que no es un asiento, el
    evento lleva `recomputed` y NO lleva `level`: el nivel va en la frase, sin la insignia de una
    alerta activa. Los que siguen abiertos no se repiten aquí: son las alertas activas, que ya
    tienen su inicio fino. El instante es el borde de un paso, no el de una lectura.
    """
    if not history:
        return
    label = str(history["label"]).lower()
    nominal = history["resting_level_display"]
    source = f"recálculo de hoy, {history['rules_version']}; no es un asiento firmado"
    english = i18n.current() == "en"
    if english:
        source = f"today's recomputation, {history['rules_version']}; it is not a signed entry"
    for item in history["episodes"]:
        if item["open"]:
            continue
        name = f"{item['domain_display']} ({item['domain']})"
        began = (
            f"ya estaba por encima de {nominal} en el paso más antiguo recalculado"
            if item["start_unknown"]
            else f"pasa de {nominal} en el paso que empieza aquí"
        )
        if english:
            began = (
                f"was already above {nominal} at the oldest recomputed step"
                if bool(item["start_unknown"])
                else f"goes above {nominal} at the step that starts here"
            )
        peak = item["peak_level_display"]
        yield _event(
            mission, _instant(item["first_step_start"]), "alerta", "recomputed-episode-start",
            i18n.tr(
                f"{label}: {name} {began}; nivel máximo del episodio, {peak}",
                f"{label}: {name} {began}; peak level of the episode, {peak}",
            ),
            _SYSTEM, source, f"{item['id']}:start", recomputed=True)
        yield _event(
            mission, _instant(item["last_step_end"]), "alerta", "recomputed-episode-end",
            i18n.tr(
                f"{label}: {name} vuelve a {nominal} tras el paso que acaba aquí; "
                f"nivel máximo del episodio, {peak}",
                f"{label}: {name} returns to {nominal} after the step that ends here; "
                f"peak level of the episode, {peak}",
            ),
            _SYSTEM, source, f"{item['id']}:end", recomputed=True)


def _followup_events(status: dict[str, Any], mission: _Mission) -> Iterator[dict[str, Any]]:
    """El fin de la ventana de seguimiento de cada contramedida adoptada, si ya llegó."""
    for item in status.get("followups") or []:
        ends = item.get("window_ends")
        if ends and _instant(ends) <= mission.now.moment:
            yield _event(
                mission, _instant(ends), "contramedida", "followup-window-end",
                i18n.tr(
                    f"contramedida {_countermeasure_id(item)}: fin de la ventana de seguimiento",
                    f"countermeasure {_countermeasure_id(item)}: end of the follow-up window",
                ),
                _SYSTEM,
                i18n.tr(
                    f"seguimiento del asiento {item.get('adoption_index')}",
                    f"follow-up of entry {item.get('adoption_index')}",
                ),
                f"followup-window:{item.get('adoption_index')}", stage="followup")


def _event_kind(kind: str) -> str:
    """Como se nombra el tipo de un evento de mision en la cronica.

    EVA y bloque de trabajo se cuentan con su clave, como siempre. Un cambio de turno
    (decimoctava ronda, U4) se nombra en español: «shift declarada» no lo leeria nadie.
    En inglés, con el nombre que registre su dueño (`core/shift.py`).
    """
    if kind == shift_event.KIND and i18n.current() == "en":
        return i18n.loc(shift_event.DISPLAY).lower()
    return shift_event.DISPLAY.lower() if kind == shift_event.KIND else kind


def _plan_events(status: dict[str, Any], mission: _Mission) -> Iterator[dict[str, Any]]:
    """Inicio y fin de cada evento declarado del plan (los que cuenta el estado), si ya llegó.

    Lo declarado y todavía por venir no ha pasado: está en "próximos días". Una ubicación
    declarada no es un evento del plan (`_LOCATION_KIND`): no tiene inicio ni fin que contar.
    """
    for item in (status.get("mission") or {}).get("events") or []:
        if item["kind"] == _LOCATION_KIND:
            continue
        words = (("start", i18n.tr("inicio", "start")), ("end", i18n.tr("fin", "end")))
        for field, word in words:
            at = _instant(item[field])
            if at <= mission.now.moment:
                yield _event(
                    mission, at, "mision", f"mission-event-{field}",
                    f"{_event_kind(item['kind'])}: {item['label']}, {word}", item["declared_by"],
                    i18n.tr(f"asiento {item['ledger_index']}", f"entry {item['ledger_index']}"),
                    f"mission-event:{item['ledger_index']}:{field}")


def _phase_events(mission: _Mission) -> Iterator[dict[str, Any]]:
    """Los cambios de fase ya ocurridos. Se pregunta a `phase_at` día a día: los límites de fase
    son suyos (de diseño) y aquí no se repiten."""
    origin = dt.datetime.combine(mission.start, dt.time(0, 0, tzinfo=dt.UTC))
    previous = phase_at(origin - dt.timedelta(days=1), mission.start, mission.duration_days)
    for day in range(mission.duration_days + 1):
        moment = origin + dt.timedelta(days=day)
        if moment > mission.now.moment:
            return
        phase = phase_at(moment, mission.start, mission.duration_days)
        if phase is not previous:
            yield _event(
                mission, moment, "fase", "phase-change",
                i18n.tr(
                    f"cambio de fase de misión: {previous.display} → {phase.display}",
                    f"mission phase change: {previous.display} → {phase.display}",
                ),
                _SYSTEM,
                i18n.tr(
                    "calendario de la misión, límites de fase de diseño",
                    "mission calendar, design phase limits",
                ),
                f"phase:{phase}")
        previous = phase


def _habitat_events(store: Any, mission: _Mission) -> Iterator[dict[str, Any]]:
    """Inicio y fin de cada excursión de cabina, las que ya da `environment/habitat.py`.

    Solo con las lecturas hasta el ahora: una excursión se da por terminada si después de ella
    hay una lectura del mismo parámetro; si no, sigue abierta y no tiene fin que contar.
    """
    readings = store.habitat_readings(until=mission.now.moment)
    last = latest_by_parameter(readings)
    for item in excursions(readings):
        name = parameter(item.parameter).display
        where = i18n.tr(f"{name} en {item.module}", f"{name} in {item.module}")
        limit = f"{item.requirement} ({i18n.loc(_EXCURSION_KIND.get(item.kind, item.kind))})"
        key = f"habitat:{item.module}:{item.parameter}:{item.requirement}:{item.start.isoformat()}"
        source = i18n.tr(
            f"telemetría de cabina del ledger, {item.requirement}",
            f"cabin telemetry from the ledger, {item.requirement}",
        )
        yield _event(
            mission, item.start, "habitat", "habitat-excursion-start",
            i18n.tr(
                f"{where}: primera lectura fuera de {limit}",
                f"{where}: first reading outside {limit}",
            ),
            _SYSTEM, source, f"{key}:start", severity=item.kind)
        if last[(item.module, item.parameter)].effective > item.end:
            yield _event(
                mission, item.end, "habitat", "habitat-excursion-end",
                i18n.tr(
                    f"{where}: última lectura fuera de {limit}",
                    f"{where}: last reading outside {limit}",
                ),
                _SYSTEM, source, f"{key}:end", severity=item.kind)


def _recovery_events(
    observations: Sequence[VitalObservation], mission: _Mission
) -> Iterator[dict[str, Any]]:
    """Las tomas posvuelo frente al rango prevuelo del propio tripulante (`analysis/recovery.py`).

    La especificación (§10) acaba la línea temporal en «postflight/recovery», y hasta el
    2026-10-14 la recuperación vivía solo en su panel: la crónica del tripulante terminaba al
    aterrizar. Aquí entra lo mismo que enseña ese panel, con su misma regla de regreso
    (`recovery.flight`) y en el mismo registro: cuánto se separa cada toma de la media prevuelo y
    si cae dentro del rango prevuelo. Sin veredicto de «recuperado» ni umbral clínico, y sin
    nivel: no es una alerta.

    UN EVENTO POR INDICADOR Y DÍA (2026-10-16). El hemograma de Inspiration4 trae una toma al
    día, pero una serie que mida cada pocos minutos tras el regreso llenaba la etapa con un
    evento por lectura. Las del mismo día se juntan en uno: cuántas son, entre qué cifras y
    cuántas caen dentro de su rango prevuelo. El día es el R+ que `recovery.recovery` da a cada
    toma, el que enseña el panel: con otra regla, la misma toma caería en días distintos en un
    sitio y en el otro. Sin tope: se cuentan todas las del día, sean dos o cien. Un día con una
    sola toma se cuenta como antes, con su separación de la media. El evento va en la última
    toma del día que ya ha pasado: no cuenta nada posterior a su instante.

    El indicador va con su nombre en español (`display_es`, de `ingest/names_es.py`: el de
    Polaris para un analito de analítica, el de EMMA para el resto), como en el resto de las
    frases del backend; las cifras, con los decimales y la unidad que `core/display.py`
    declara para él (salían la media con cuatro decimales y la unidad UCUM en crudo).

    Va siempre en la etapa `postflight`, aunque el calendario configurado diga otra cosa: con el
    hemograma de Inspiration4 el regreso es el de su vuelo (tres días), no el fin de la misión
    configurada, y la fuente lo dice. Para Tierra (`until`), solo lo que ya tiene; y nada
    posterior al ahora: `observations` son las del tripulante hasta `until` (`chronicle`).
    """
    launch, landing, real = recovery.flight(observations, mission.start, mission.duration_days)
    source = (
        f"OSD-569 (Inspiration4), regreso a los {inspiration4.MISSION_DAYS} "
        f"días de su vuelo" if real else "lecturas del ledger, regreso al fin de la misión"
    ) + "; referencia: el prevuelo del propio tripulante, sin veredicto"
    if i18n.current() == "en":
        source = (
            f"OSD-569 (Inspiration4), return after the {inspiration4.MISSION_DAYS} days of "
            f"its flight" if real else "readings from the ledger, return at the end of the mission"
        ) + "; reference: the crew member's own preflight, with no verdict"
    for item in recovery.recovery(observations, launch, landing):
        days: dict[int, list[dict[str, Any]]] = {}
        for sample in item["postflight"]:
            if _instant(sample["at"]) > mission.now.moment:
                continue
            days.setdefault(sample["days_after_landing"], []).append(sample)
        for day, samples in days.items():
            event = _event(
                mission, _instant(samples[-1]["at"]), "posvuelo",
                "postflight-sample" if len(samples) == 1 else "postflight-day",
                _postflight_day(item, day, samples), _SYSTEM, source,
                f"recovery:{item['key']}:R+{day}")
            event["stage"] = "postflight"
            yield event


def _postflight_day(item: dict[str, Any], day: int, samples: list[dict[str, Any]]) -> str:
    """La frase de un indicador en un día tras el regreso: su toma, o cuántas y entre qué cifras.

    `samples` va en orden de instante (`recovery.recovery` las ordena) y no está vacía.
    """
    if i18n.current() == "en":
        return _postflight_day_en(item, day, samples)
    key, unit = item["key"], item["unit"]
    name = item["display_es"]
    before = item["preflight"]
    reference = (
        f"media prevuelo propia {_amount(key, unit, before['mean'])} "
        f"({display.number(before['samples'], 0)} tomas)")
    span = f"rango prevuelo {_amount(key, unit, before['low'], before['high'])}"
    if len(samples) == 1:
        [sample] = samples
        delta = sample["delta_pct"]
        if delta is None:
            apart = f"{reference}, sin porcentaje: la media es cero"
        elif delta == 0:
            apart = f"igual que la {reference}"
        else:
            side = "por encima" if delta > 0 else "por debajo"
            apart = f"{display.number(abs(delta), 1)} % {side} de la {reference}"
        inside = "dentro" if sample["within_preflight_range"] else "fuera"
        return (
            f"{name}: {_amount(key, unit, sample['value'])} en R+{day}; {apart}; "
            f"{inside} de su {span}")
    values = [sample["value"] for sample in samples]
    low, high = min(values), max(values)
    spread = (
        f"todas de {_amount(key, unit, low)}"
        if _amount(key, unit, low) == _amount(key, unit, high)
        else f"entre {_amount(key, unit, low, high, joint=' y ')}"
    )
    within = sum(1 for sample in samples if sample["within_preflight_range"])
    if within == len(samples):
        count = "todas dentro"
    elif within == 0:
        count = "todas fuera"
    else:
        count = (
            f"{display.number(within, 0)} dentro y "
            f"{display.number(len(samples) - within, 0)} fuera")
    return (
        f"{name}: {display.number(len(samples), 0)} tomas en R+{day}, {spread}; {count} de su "
        f"{span}; {reference}")


def _postflight_day_en(item: dict[str, Any], day: int, samples: list[dict[str, Any]]) -> str:
    """La frase de `_postflight_day`, dicha en inglés: las mismas cifras y la misma regla.

    Va aparte porque el castellano se compone por trozos («igual que la», «de su») que en inglés
    no caen en el mismo sitio. Las cifras, por `core/display.py`: con punto decimal.
    """
    key, unit, name = item["key"], item["unit"], item["display_es"]
    before = item["preflight"]
    reference = (
        f"own preflight mean {_amount(key, unit, before['mean'])} "
        f"({display.number(before['samples'], 0)} samples)")
    span = f"preflight range {_amount(key, unit, before['low'], before['high'])}"
    if len(samples) == 1:
        [sample] = samples
        delta = sample["delta_pct"]
        if delta is None:
            apart = f"{reference}, no percentage: the mean is zero"
        elif delta == 0:
            apart = f"equal to the {reference}"
        else:
            side = "above" if delta > 0 else "below"
            apart = f"{display.number(abs(delta), 1)} % {side} the {reference}"
        place = "inside" if sample["within_preflight_range"] else "outside"
        return (
            f"{name}: {_amount(key, unit, sample['value'])} at R+{day}; {apart}; "
            f"{place} their {span}")
    values = [sample["value"] for sample in samples]
    low, high = min(values), max(values)
    spread = (
        f"all at {_amount(key, unit, low)}"
        if _amount(key, unit, low) == _amount(key, unit, high)
        else f"between {_amount(key, unit, low, high, joint=' and ')}"
    )
    inside = [sample for sample in samples if sample["within_preflight_range"]]
    if len(inside) == len(samples):
        count = "all inside"
    elif not inside:
        count = "all outside"
    else:
        count = (
            f"{display.number(len(inside), 0)} inside and "
            f"{display.number(len(samples) - len(inside), 0)} outside")
    return (
        f"{name}: {display.number(len(samples), 0)} samples at R+{day}, {spread}; {count} "
        f"their {span}; {reference}")


def _amount(key: str, ucum: str, *values: float, joint: str = "–") -> str:
    """Una cifra, o dos unidas («5,4–7,0»), con los decimales de su indicador y su unidad legible.

    Las reglas son las de toda cifra que redacta el backend (`core/display.py`, F.5.6): coma
    decimal y tantos decimales como declara el indicador, ni uno de relleno. Una unidad que se
    lee vacía (un cociente) no deja un espacio colgando.
    """
    digits = display.decimals_for(key)
    figures = joint.join(display.number(value, digits) for value in values)
    return f"{figures} {display.unit(ucum)}".rstrip()


def chronicle(
    store: Any,
    subject: str,
    status: dict[str, Any],
    now: AsOf,
    mission_start: dt.date,
    mission_days: int,
    until: dt.datetime | None = None,
    history: dict[str, Any] | None = None,
    moments: dict[str, Any] | None = None,
    observations: Sequence[Any] | None = None,
    career: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lo que pasó y lo que se decidió, cada hecho con su instante y su fuente, hasta `now`.

    `status` es lo que la crónica lee del estado (vacío si no hay lecturas) y `now` su ahora
    (`as_of`). Desde el 2026-10-22 no es `/api/status` entero sino `routes.chronicle_status`:
    instante de referencia, trayectoria de cada dominio, alertas con su inicio, seguimientos y
    eventos del plan, con las mismas piezas que el estado. Un campo más que se lea de aquí tiene
    que salir también allí (`tests/test_status_performance.py` compara los dos).
    Con `until`, lo que Tierra puede tener. Cada evento lleva además su línea de bitácora de
    Polaris. `history` es la historia recalculada de las alertas (`analysis/alert_history.py`):
    sus episodios cerrados se cuentan marcados como recálculo, y viaja entera en `recomputed`
    con su rótulo, sus límites y su tope para que quien la pinte los enseñe.

    `moments` son los momentos de `/anatomy/state` (`anatomy.moments`), que quien llama saca de
    las lecturas que analiza el estado: cada hecho que sea uno de ellos (un cambio de fase, una
    toma posvuelo) lleva en `moment` su clave y su rótulo, para que pulsarlo elija ese momento en
    «Cuerpo»; los demás, `None`. Sin ellos (Tierra, o sin lecturas), ninguno lo lleva. Antes se
    daba una función de las lecturas de aquí, que obligaba a quien llama a repetir el filtro del
    estado sobre ellas (§5.37.13).

    `observations` son las lecturas del tripulante hasta `until` si quien llama ya las leyó (la
    evaluación del estado las lee igual, `routes._Assessment.stored`); sin ellas se piden aquí.

    `career` es el historial misión a misión vigente en el corte (`_career_events`), leído una vez
    por quien llama; sin él no hay etapa «carrera».
    """
    mission = _Mission(mission_start, mission_days, now)
    if observations is None:
        observations = store.query(subject, until=until)
    events = [
        *_career_events(career, mission),
        *_ledger_events(store, subject, mission, until),
        *_analysis_events(status, mission),
        *_recomputed_events(history, mission),
        *_followup_events(status, mission),
        *_plan_events(status, mission),
        *_habitat_events(store, mission),
        *_recovery_events(observations, mission),
    ]
    if now.source == "data":
        # Sin lecturas no hay tiempo de misión que contar: el calendario solo no es un hecho.
        events += _phase_events(mission)
    # Primero la carrera declarada, que es anterior a todo; luego lo que está en el tiempo de los
    # datos; lo que solo tiene hora de firma, al final: son tres relojes y ordenarlos juntos
    # sería compararlos. En un mismo instante se conserva el orden en que se generó: el inicio
    # de una excursión de una sola lectura, antes que su fin.
    events.sort(key=lambda event: (_CLOCK_ORDER[event["time_basis"]], _instant(event["at"])))
    counts: dict[str, int] = {}
    for event in events:
        counts[event["stage"]] = counts.get(event["stage"], 0) + 1
        event["moment"] = anatomy.chronicle_moment(event, moments)
    line = _tool("cronica")._linea_bitacora
    return {
        **now.to_dict(),
        "stages": [
            {"key": key, "display": _stage_display(key, text), "count": counts.get(key, 0)}
            for key, text in STAGES
        ],
        "events": events,
        "lines": [line(event) for event in events],
        "recomputed": history,
    }


# --------------------------------------------------------------------------- #
# Esta semana
# --------------------------------------------------------------------------- #


def _countermeasure_id(item: dict[str, Any]) -> Any:
    """El estado da la contramedida entera (`countermeasure`); un asunto suelto, solo su id."""
    return (item.get("countermeasure") or {}).get("id") or item.get("countermeasure_id")


def week_items(status: dict[str, Any]) -> list[dict[str, Any]]:
    """Lo datado del estado de EMMA, con la forma de un asunto de `seguimiento.json`."""
    items: list[dict[str, Any]] = []
    for item in status.get("followups") or []:
        if item.get("state") in ("closed", "cerrado"):
            continue
        items.append({
            "titulo": i18n.tr(
                f"Seguimiento de {_countermeasure_id(item)} ({item.get('domain')})",
                f"Follow-up of {_countermeasure_id(item)} ({item.get('domain')})",
            ),
            "vence": item.get("window_ends"),
            "siguiente_accion": i18n.tr(
                "repetir la medida de seguimiento", "repeating the follow-up measurement"
            ),
            "estado": "abierto",
        })
    for item in status.get("predictions") or []:
        if item.get("horizon_at"):
            items.append({
                "titulo": i18n.tr(
                    f"Horizonte de la proyección de {item.get('key')}",
                    f"Horizon of the projection of {item.get('key')}",
                ),
                "vence": item["horizon_at"],
                "siguiente_accion": i18n.tr(
                    "comprobar la proyección con lo medido",
                    "checking the projection against what was measured",
                ),
                "estado": "abierto",
            })
    for item in (status.get("mission") or {}).get("events") or []:
        if item.get("kind") == _LOCATION_KIND:
            continue  # dónde está un tripulante no es un asunto que venza (`_LOCATION_KIND`)
        items.append({
            "titulo": f"{item.get('kind')}: {item.get('label')}",
            "vence": item.get("start"),
            "siguiente_accion": "",
            "estado": "abierto",
        })
    return items


def _date_at(today: dt.date) -> type[dt.date]:
    """Un `date` cuyo `today()` es el día de los datos: el reloj que lee `anticipa`."""

    class DataDate(dt.date):
        @classmethod
        def today(cls) -> Self:
            return cls(today.year, today.month, today.day)

    return DataDate


def this_week(status: dict[str, Any], now: AsOf, days: int = 7) -> dict[str, Any]:
    """`anticipa.esta_semana()` sobre lo datado de EMMA, y los asuntos de la ventana.

    La ventana empieza en el ahora de la línea temporal (`now`), no en el reloj del ordenador.
    `anticipa` lee `date.today()`: durante la llamada su `date` es uno que responde con el día de
    los datos, y después vuelve a ser el suyo.
    """
    items = week_items(status)
    anticipa, follow, summit = _tool("anticipa"), _tool("seguimiento"), _tool("cumbre")
    today = now.moment.date()
    end = today + dt.timedelta(days=max(1, days))
    upcoming = sorted(
        (item for item in items
         if (date := anticipa._fecha(item)) is not None and today <= date <= end),
        key=lambda item: str(item["vence"]),
    )
    with _LOCK:
        saved = (follow.recopilar, summit.foco)
        saved_date = anticipa.date
        follow.recopilar = lambda *args, **kwargs: {"items": items}
        summit.foco = lambda: None
        anticipa.date = _date_at(today)
        try:
            block = anticipa.esta_semana(days)
        finally:
            follow.recopilar, summit.foco = saved
            anticipa.date = saved_date
    return {**now.to_dict(), "days": days, "items": upcoming, "block": block}


# --------------------------------------------------------------------------- #
# Qué depende de este dato
# --------------------------------------------------------------------------- #


def emma_map() -> tuple[dict[str, Any], dict[str, Any]]:
    """El mapa de EMMA con la forma de `cascada_mapa`: (MAPA, DEPENDIENTES)."""
    dependents: dict[str, Any] = {}
    data: dict[str, Any] = {}
    library = countermeasures.load().values()
    for key, code in CATALOG.items():
        if key in DESCRIPTIVE_ONLY:
            # Descriptivo: el estado no lo lee, así que de él no depende ningún dominio, línea
            # base, proyección ni región. Corregirlo no obliga a revisar nada más.
            data[key] = {"titulo": code.display_es, "dependientes": [], "gobierna_datos": []}
            continue
        domain = str(code.domain)
        deps = [f"dominio:{domain}", f"linea-base:{key}", f"proyeccion:{key}"]
        dependents[f"dominio:{domain}"] = {
            "modo": "auto", "titulo": i18n.tr(
                f"Riesgo del dominio {code.domain.display}",
                f"Risk of the {code.domain.display} domain",
            )}
        dependents[f"linea-base:{key}"] = {
            "modo": "auto", "titulo": i18n.tr(f"Línea base de {key}", f"Baseline of {key}")}
        dependents[f"proyeccion:{key}"] = {
            "modo": "auto", "titulo": i18n.tr(f"Proyección de {key}", f"Projection of {key}")}
        for region in anatomy.REGIONS:
            # La región que enseña el indicador: la de su dominio o la vista que lo lista (hígado).
            if region.shows(key):
                deps.append(f"region:{region.key}")
                dependents[f"region:{region.key}"] = {"modo": "auto", "titulo": region.display}
        for item in library:
            if key in item.followup_checks:
                deps.append(f"contramedida:{item.id}")
                dependents[f"contramedida:{item.id}"] = {
                    "modo": "humano", "titulo": i18n.tr(
                        f"Seguimiento de la contramedida {item.id}",
                        f"Follow-up of countermeasure {item.id}",
                    )}
        data[key] = {"titulo": code.display_es, "dependientes": deps, "gobierna_datos": []}
    return data, dependents


def depends_on(key: str) -> dict[str, Any]:
    """`cascada_mapa.afectados()` sobre el mapa de EMMA: qué se recalcula o se revisa."""
    if key not in CATALOG:
        raise KeyError(key)
    cascade = _tool("cascada_mapa")
    data, dependents = emma_map()
    with _LOCK:
        saved = (cascade.MAPA, cascade.DEPENDIENTES)
        cascade.MAPA, cascade.DEPENDIENTES = data, dependents
        try:
            affected = cascade.afectados(key)
            errors = cascade.validar_mapa()
        finally:
            cascade.MAPA, cascade.DEPENDIENTES = saved
    return {
        "key": key,
        "affected": [
            {"id": dep, "mode": info["modo"], "title": info["titulo"]}
            for dep, info in sorted(affected.items())
        ],
        "map_errors": errors,
    }
