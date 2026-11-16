"""Reproducción de datos reales publicados: hoy, las analíticas de Inspiration4.

Por qué es una ruta aparte del simulador: el simulador genera series; esto no genera nada.
Coloca en la línea de tiempo de EMMA lecturas que existieron, con su procedencia. Van firmadas
como simuladas —no son lecturas de esta tripulación— para que el modo de misión lo declare y
un cambio de escenario las pueda descartar.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException

from app.analysis.recovery import BASIS as RECOVERY_BASIS
from app.analysis.recovery import flight, split
from app.api.console_header import console_post
from app.api.routes import _SIMULATOR_SOURCE, SettingsDep, StoreDep, identity_for
from app.core import i18n
from app.core.storage import seed_from_simulator
from app.ingest import inspiration4

replay_router = APIRouter(prefix="/replay")

CITATION = (
    "Data are courtesy of the NASA Open Science Data Repository (https://osdr.nasa.gov/bio/repo). "
    "OSD-569: Whole Blood Measurements from the SpaceX Inspiration4 Mission."
)


@replay_router.post("/inspiration4", status_code=201, **console_post())
def replay_inspiration4(store: StoreDep, settings: SettingsDep) -> dict[str, Any]:
    """Añade el hemograma real de los cuatro tripulantes de Inspiration4 (crew-01 a crew-04).

    El lanzamiento se coloca en el inicio de misión configurado y el regreso tres días
    después. Las muestras incoherentes en origen se apartan y se devuelven con su motivo.
    """
    launch = dt.datetime.combine(settings.mission_start, dt.time(0, 0), tzinfo=dt.UTC)
    try:
        replay = inspiration4.load(launch)
    except inspiration4.DataFileChanged as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    count = seed_from_simulator(store, replay.observations, identity_for(_SIMULATOR_SOURCE))
    return {
        "recorded": count,
        "subjects": sorted(inspiration4.CREW.values()),
        "excluded": replay.excluded,
        "source": inspiration4.STUDY_URL,
        "citation": CITATION,
    }


@replay_router.get("/recovery")
def postflight_recovery(
    store: StoreDep, settings: SettingsDep, subject: str = "crew-01"
) -> dict[str, Any]:
    """Recuperacion posvuelo de un tripulante: prevuelo → regreso → R+n (especificacion §10).

    Con el hemograma de Inspiration4, el regreso es tres dias despues del lanzamiento; con
    otros datos, al final de la mision configurada.
    """
    observations = store.query(subject)
    launch, landing, real_flight = flight(
        observations, settings.mission_start, settings.mission_days
    )
    ranged, unranged = split(observations, launch, landing)
    return {
        "subject": subject,
        "launch": launch.isoformat(),
        "landing": landing.isoformat(),
        "indicators": ranged,
        # Los que tienen tomas posvuelo y no rango prevuelo propio: se dicen, no se suponen.
        "without_preflight_range": unranged,
        "basis": i18n.loc(RECOVERY_BASIS),
        "source": inspiration4.STUDY_URL if real_flight else None,
    }
