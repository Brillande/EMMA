"""Crónica, "esta semana" y "qué depende de este dato", de solo lectura (`app/timeline.py`)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException

from app import anatomy, routines, timeline, waiting
from app.analysis.risk import active_solar_event
from app.api import routes
from app.api.alert_history import history_view
from app.api.mission import latest_mission_history
from app.api.routes import SettingsDep, StoreDep, crew_status
from app.core import i18n, mission_modes
from app.core.config import Settings
from app.core.storage import ObservationStore
from app.environment.donki import SolarEvent
from app.reports import incongruences

timeline_router = APIRouter(prefix="/timeline")

# UN SOLO AHORA.
#
# Todo lo de este módulo se cuenta desde el instante de referencia de `/api/status` (la última
# lectura analizable, o la última que Tierra tiene), no desde el reloj del ordenador: con una
# misión simulada los datos van meses por delante o por detrás de él. El reloj real solo entra
# si no hay lecturas, es el mismo que ya usa `/api/status` (`routes._now`, que las pruebas
# pueden fijar) y la respuesta dice que se usó.


def _aware(until: dt.datetime | None) -> None:
    if until is not None and until.tzinfo is None:
        # Misma regla que `/api/status`: un instante sin zona horaria es ambiguo.
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")


def _status(
    settings: Settings, store: ObservationStore, subject: str, until: dt.datetime | None
) -> dict[str, Any]:
    """El estado de `/api/status`, o nada si no hay lecturas que analizar."""
    _aware(until)
    try:
        return crew_status(
            settings, store, subject=subject, epoch=None, cumulative_dose_msv=None, until=until
        )
    except HTTPException:
        return {}


def chronicle_view(
    settings: Settings, store: ObservationStore, subject: str, until: dt.datetime | None = None
) -> dict[str, Any]:
    """La crónica con su ahora: la misma para la consola y para el PDF.

    UNA EVALUACIÓN Y NINGUNA ESCRITURA (2026-10-22). Pedía el estado entero (`crew_status`) y,
    aparte, la historia recalculada, que evaluaba otra vez lo mismo: con cuatro tripulantes
    sembrados, unos 6 s (1,5 s ahora), y sin `until` firmaba instantáneas de proyección que la
    crónica no enseña. Ahora se evalúa una vez (`routes._assess`, sin época ni dosis, como
    antes), y de esa evaluación salen lo que la crónica lee del estado (`routes.chronicle_status`,
    con las mismas piezas que `/status`), la historia y las lecturas del posvuelo.

    La carrera (2026-10-23): el historial misión a misión vigente en el corte, leído una vez y con
    la misma regla que `/crew/mission-history` (solo lo firmado por la consola y, para Tierra, lo
    que ya existía en su corte). No pasa por la evaluación: no es un dato del estado.
    """
    # Antes que nada: la 422 de `_assess` por la misma razón quedaría tragada abajo.
    _aware(until)
    assessed: routes._Assessment | None
    try:
        assessed = routes._assess(settings, store, subject, None, None, until)
        status = routes.chronicle_status(settings, store, subject, until, assessed)
    except HTTPException:
        # Sin lecturas que analizar no hay estado ni nada que recalcular.
        assessed, status = None, {}
    now = timeline.as_of(status, until, routes._now())
    # Los episodios ya cerrados, recalculados sin escribir nada (`analysis/alert_history.py`).
    try:
        history = history_view(settings, store, subject, until, assessed) if assessed else None
    except HTTPException:
        history = None
    return timeline.chronicle(
        store, subject, status, now, settings.mission_start, settings.mission_days, until,
        history, _moments(settings, assessed) if assessed and until is None else None,
        assessed.stored if assessed else None,
        latest_mission_history(store, subject, until),
    )


def _moments(settings: Settings, assessed: routes._Assessment) -> dict[str, Any]:
    """Los momentos de `/anatomy/state`, para enlazar la crónica con ellos.

    Con las lecturas que el estado analiza, tal cual las dejó su evaluación
    (`routes._Assessment.observations`: sin los descriptivos y sin las de fecha no analizable),
    para que la clave que lleva un hecho sea la de un momento que «Cuerpo» ofrece; una prueba
    compara las dos listas. Antes se volvían a filtrar aquí, con una copia del filtro de
    `routes._assess`, las lecturas sin apartar nada (`assessed.stored`, §5.37.13): lo que se
    aparta lo decide la evaluación, una sola vez. Solo los de ahora: con `until` (Tierra) no hay
    momentos, como en `/anatomy/state`, y Tierra no monta «Cuerpo».
    """
    return anatomy.moments(assessed.observations, settings.mission_start, settings.mission_days)


def _routines(
    store: ObservationStore,
    subject: str,
    until: dt.datetime | None,
    event: SolarEvent | None = None,
) -> dict[str, Any]:
    """Las medidas periódicas, juzgadas con las lecturas y el ahora del estado, y de dónde sale.

    `routines.py` ya cuenta desde los datos y no desde el reloj. Lo que faltaba: su ahora era la
    última lectura a secas, así que una sola fechada en 2099 daba para siempre todas las demás
    por rotas, y sin lecturas caía al reloj real sin decirlo. Aquí se le dan las lecturas que
    analiza `/api/status` y su misma referencia (`routes.state_reference`, que aparta esa lectura
    y lo dice en el estado). Tierra cuenta desde su corte: para ella el tiempo pasa aunque no llegue
    nada.

    `event` es el evento solar que el estado da por activo (2026-11-02): con él, las rutinas de
    evento se juzgan con su periodo acortado. Se juzga en el mismo ahora, así que con `until` un
    evento posterior al corte de Tierra no acorta nada (`routines.event_in_force`).
    """
    _aware(until)
    # Lo que decide el estado (`routes.state_reference`): una lectura predicha no es una medida
    # hecha, y fechada en el futuro moveria el «ahora» con que se juzga cada rutina; una
    # descriptiva, que el estado no lee, tampoco lo mueve (§5.38.7).
    readings = store.query(subject, until=until)
    kept, reference, _ = routes.state_reference(readings)
    if until is not None:
        now, source = until, "cut"
    elif kept:
        now, source = reference, "data"
    else:
        now, source = routes._now(), "clock"
    body = {**routines.evaluate(kept, now=now, event=event), "now_source": source}
    # Las rachas (`routines.streaks`), con las mismas lecturas y el mismo ahora: para Tierra,
    # contadas desde su corte. Campo nuevo; los de antes no cambian.
    body["streaks"] = routines.streaks(kept, now=now)
    # El nivel de misión firmado hasta este corte (`core/mission_modes.py`): lo que suspende no se
    # da por atrasado ni roto. Solo marca y recuenta; el riesgo no lo lee.
    level = store.mission_mode(until)["level"]
    # El nombre del nivel, en el idioma de quien lee: su inglés puede venir del hermano
    # `mission_modes.en.json` o de un registro `i18n.en` de su dueño; aquí valen los dos.
    level_display = i18n.loc(
        i18n.localized(mission_modes.vocabulary().levels[level].display, mission_modes.MODES_PATH)
    )
    return routines.with_mission_level(
        body, level, level_display,
        mission_modes.suspended_measurements(level),
    )


@timeline_router.get("/chronicle")
def read_chronicle(
    store: StoreDep,
    settings: SettingsDep,
    subject: str = "crew-01",
    # Lo que Tierra puede tener: hasta el corte del retardo, como `/api/status`.
    until: dt.datetime | None = None,
) -> dict[str, Any]:
    """Lo que pasó y lo que se decidió, en el tiempo de los datos, con su `as_of`."""
    return chronicle_view(settings, store, subject, until)


@timeline_router.get("/week")
def read_week(
    store: StoreDep, settings: SettingsDep, subject: str = "crew-01", days: int = 7
) -> dict[str, Any]:
    """Lo datado que viene: fin de seguimientos, horizontes firmados y eventos de misión."""
    status = _status(settings, store, subject, None)
    dated = {
        "followups": status.get("followups") or [],
        # Las proyecciones con fecha son las instantáneas firmadas (`prediction-snapshot`).
        "predictions": store.prediction_snapshots(subject),
        "mission": status.get("mission") or {"events": []},
    }
    now = timeline.as_of(status, None, routes._now())
    return timeline.this_week(dated, now, max(1, min(days, 31)))


@timeline_router.get("/depends/{key}")
def read_depends(key: str) -> dict[str, Any]:
    try:
        return timeline.depends_on(key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"indicador desconocido: {key}") from exc


@timeline_router.get("/routines")
def read_routines(
    store: StoreDep,
    settings: SettingsDep,
    subject: str = "crew-01",
    until: dt.datetime | None = None,
) -> dict[str, Any]:
    """Si cada medida periódica llega a su ritmo (Polaris `estado_rutina`). Con `until`, lo que
    Tierra puede saber.

    Con los eventos solares que lee el estado (`routes._fetch_solar_events`) y su mismo criterio
    de evento activo: sin DONKI no hay evento y la respuesta es la de siempre."""
    _aware(until)
    events, _ = routes._fetch_solar_events(settings)
    return _routines(store, subject, until, active_solar_event(events))


# Lo que responde el estado (`routes._assess`) cuando no hay nada que analizar: ninguna lectura,
# o solo descriptivos (404), o ninguna con fecha analizable (422). La otra 422 de `_assess`, un
# `until` sin zona horaria, ya la ha dado `_aware` antes de pedir el estado.
_NOTHING_TO_ANALYSE = frozenset({404, 422})


@timeline_router.get("/waiting")
def read_waiting(
    store: StoreDep,
    settings: SettingsDep,
    subject: str = "crew-01",
    until: dt.datetime | None = None,
) -> dict[str, Any]:
    """Lo que lleva días esperando a una persona (Polaris `atascos`) y lo que no cuadra. Con
    `until`, lo que Tierra puede saber en su corte.

    Sin lecturas que analizar (`_NOTHING_TO_ANALYSE`) no espera nada. Cualquier otro error del
    estado sale con su código: antes se tragaba toda `HTTPException` y un fallo se servía como
    «nada espera» (§5.37.13)."""
    _aware(until)
    try:
        status = crew_status(
            settings, store, subject=subject, epoch=None, cumulative_dose_msv=None, until=until
        )
    except HTTPException as exc:
        if exc.status_code not in _NOTHING_TO_ANALYSE:
            raise
        return {"threshold_days": None, "waiting": [], "incongruences": []}
    return waiting_for(status, store, subject, until)


def waiting_for(
    status: dict[str, Any],
    store: ObservationStore,
    subject: str,
    until: dt.datetime | None = None,
) -> dict[str, Any]:
    """Lo que espera a una persona sobre un estado YA calculado: lo comparten esta ruta y las
    cinco preguntas de los gemelos (`api/twins.py`), que no deben pedir el estado otra vez.

    Con `until`, el estado ya viene cortado; aquí se cortan con él las rutinas, los informes de
    los que salen las incongruencias y lo firmado en el registro (`app/waiting.py`). Los informes
    se cortan una vez y sirven a las dos cosas: las incongruencias y las cifras sin confirmar.

    Las rutinas, con el evento solar de ESE estado (`active_solar_event`): el mismo de su
    respuesta, sin volver a preguntar a DONKI."""
    reports = waiting.reports_known(store, subject, until)
    active = status.get("active_solar_event")
    event = SolarEvent.from_dict(active) if active else None
    return waiting.waiting(
        status, store, _routines(store, subject, until, event), subject,
        incongruences.find(reports),
        until=until, reports=reports,
    )
