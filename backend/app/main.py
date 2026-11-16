"""Punto de entrada de la API de EMMA.

Arrancar en desarrollo:
    .venv/Scripts/python.exe -m uvicorn app.main:app --reload
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import guides, sharing
from app.advisor import effects
from app.api.alert_history import alert_history_router
from app.api.app_update import app_update_router
from app.api.assistant import assistant_router
from app.api.baseline_profile import baseline_profile_router
from app.api.cognition import cognition_router
from app.api.context_sources import context_sources_router
from app.api.correlations import correlations_router
from app.api.countermeasures import countermeasures_router
from app.api.crew_radiation import crew_radiation_router
from app.api.datasets import datasets_router
from app.api.descriptive import descriptive_router
from app.api.diary import diary_router
from app.api.distances import distances_router
from app.api.evidence import evidence_router
from app.api.facilities import facilities_router
from app.api.ground_notes import ground_notes_router
from app.api.guides import guides_router
from app.api.habitat import habitat_router
from app.api.help_requests import help_requests_router
from app.api.imaging import imaging_router
from app.api.inventory import inventory_router
from app.api.knowledge import knowledge_router
from app.api.link_sync import link_sync_router
from app.api.location_anchors import location_router
from app.api.mission import mission_router
from app.api.mission_mode import mission_mode_router
from app.api.mission_profile import mission_profile_router
from app.api.mission_profiles import mission_profiles_router
from app.api.models_pack import autostart as models_autostart
from app.api.models_pack import models_pack_router
from app.api.ntrs import ntrs_router
from app.api.nutrition import nutrition_router
from app.api.orbit import orbit_router
from app.api.osdr_data import osdr_data_router
from app.api.pain import pain_router
from app.api.people import people_router
from app.api.planner import planner_router
from app.api.polaris import polaris_router
from app.api.pvt_console import pvt_router
from app.api.replay import replay_router
from app.api.reports import reports_router
from app.api.resources import resources_router
from app.api.risks import risks_router
from app.api.routes import router
from app.api.safe_mode import safe_mode_router
from app.api.sensor_bindings import sensor_bindings_router
from app.api.sharing import sharing_router
from app.api.space_weather_series import space_weather_series_router
from app.api.spec5 import spec5_router
from app.api.spice import spice_router
from app.api.systems import systems_router
from app.api.testbeds import testbeds_router
from app.api.timeline import timeline_router
from app.api.twins import twins_router
from app.api.volumes import volumes_router
from app.assistant import catalog as assistant_catalog
from app.core import i18n, log_privacy
from app.core.config import get_settings
from app.core.host_guard import HostGuardMiddleware
from app.core.ledger import UntrustedSigner
from app.core.storage import TamperedRecordError
from app.evidence import (
    credibility,
    cycle_physiology,
    flight_direction,
    instruments_read,
    light_exposure,
    menopause_physiology,
    nasa_framework,
    research_countermeasures,
)

# Antes de servir nada: desde aquí, ninguna traza ni línea de acceso lleva contenido personal
# (especificación §12; el inventario y lo que no cubre, en `core/log_privacy.py`).
log_privacy.install()


class ReadFileError(RuntimeError):
    """Un fichero de lo leído no pasa su contrato: la aplicación no arranca."""


# Los ficheros de lo leído que sirven los cargadores de `evidence/`. Cada cargador los valida en
# su `read()`, pero `read()` corría en la primera petición: un fichero roto salía entonces como un
# 500 sin su motivo, a media misión. Se validan aquí, al importar la aplicación, como ya hacen
# `evidence/radiation_read.py` (al importar `analysis/radiation.py`) y las fichas del registro que
# cita `analysis/context.py`: un fichero roto no deja arrancar, y dice cuál y por qué.
READ_FILES: tuple[tuple[Path, Callable[[], object]], ...] = (
    (credibility.READ_PATH, credibility.read),
    (cycle_physiology.READ_PATH, cycle_physiology.read),
    (flight_direction.READ_PATH, flight_direction.read),
    (instruments_read.READ_PATH, instruments_read.read),
    (light_exposure.READ_PATH, light_exposure.read),
    (menopause_physiology.READ_PATH, menopause_physiology.read),
    (nasa_framework.READ_PATH, nasa_framework.read),
    (research_countermeasures.RESEARCH_PATH, research_countermeasures.read),
)


def check_read_files() -> None:
    """Valida cada fichero de lo leído; el primero que falle detiene el arranque con su motivo.

    También la ficha de efectos de las contramedidas (`advisor/effects.py`): no es una lectura de
    fuentes y no va en `READ_FILES`, pero la sirven el estado y la biblioteca, y un fichero roto
    tumbaría `/api/status` entero en la primera petición por un campo que no decide nada.
    """
    checked: tuple[tuple[Path, Callable[[], object]], ...] = (
        *READ_FILES,
        (effects.EFFECTS_PATH, effects.loaded),
        # Las guías de medida y el glosario (unidad 3): texto para la tripulación con sus frases.
        (guides.GUIDES_PATH, guides.guides),
        (guides.GLOSSARY_PATH, guides.glossary),
        # Qué se comparte y qué no: una tabla que dijera otra lista blanca que la de `egress` no
        # deja arrancar (`app/sharing.py`).
        (sharing.SHARING_PATH, sharing.read),
    )
    for path, read in checked:
        try:
            read()
        # El error de cada cargador es un `ValueError` (también un JSON que no se puede leer); un
        # fichero con otra forma rompe antes con un `KeyError` o un `TypeError`: todos se dicen.
        except (ValueError, LookupError, TypeError, AttributeError, OSError) as error:
            # El motivo de un cargador ya se explica solo; de lo demás, también la clase (un
            # `KeyError` dice solo la clave), y la traza encadenada lleva a la línea que falló.
            reason = str(error) if isinstance(error, ValueError) else f"{error!r}"
            raise ReadFileError(f"{path.name} no pasa su contrato: {reason}") from error


check_read_files()

app = FastAPI(
    title="EMMA — Environment and Medical Monitoring Assistant",
    description=(
        "Monitorización autónoma de salud para misiones de larga duración. "
        "Apoyo a la decisión, no prescripción: el sistema informa y recomienda, "
        "no administra terapia ni sustituye el juicio clínico."
    ),
    version="0.1.7",
)

# En vuelo no hay navegador remoto: el frontend se sirve junto al backend. Esta
# apertura es para desarrollo local, y la consola en :5173 ni la usa (Vite le hace de proxy a
# /api: mismo origen). Entre orígenes solo GET: el POST de otra página que trae comprobación
# previa se deniega aquí por el método, y el que no la trae —la petición simple— lo frena la
# cabecera `X-EMMA-Console` (`api/console_header.py`), que `allow_headers=["*"]` refleja en la
# comprobación previa. Las dos cosas tienen prueba en `tests/test_console_header.py`.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# El idioma de cada petición (`core/i18n.py`): la consola lo dice con su cookie y quien no dice
# ninguno recibe el de `EMMA_LANG`. Va por fuera de todo lo demás: también un error se redacta en
# el idioma de quien preguntó.
i18n.set_default(get_settings().lang)
assistant_catalog.use_set_aside(True)
app.add_middleware(i18n.LanguageMiddleware)
# Lo último que se añade va por fuera de todo: un `Host` que no sea loopback (DNS rebinding) o un
# `Origin` ajeno en lo que escribe no llegan a ninguna ruta (`core/host_guard.py`).
app.add_middleware(HostGuardMiddleware)

app.include_router(router, prefix="/api")
app.include_router(imaging_router, prefix="/api")
app.include_router(pain_router, prefix="/api")
app.include_router(countermeasures_router, prefix="/api")
app.include_router(habitat_router, prefix="/api")
app.include_router(crew_radiation_router, prefix="/api")
app.include_router(mission_router, prefix="/api")
app.include_router(replay_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(volumes_router, prefix="/api")
app.include_router(polaris_router, prefix="/api")
app.include_router(safe_mode_router, prefix="/api")
app.include_router(models_pack_router, prefix="/api")
app.include_router(app_update_router, prefix="/api")
app.include_router(link_sync_router, prefix="/api")
app.include_router(mission_mode_router, prefix="/api")
app.include_router(mission_profile_router, prefix="/api")
app.include_router(evidence_router, prefix="/api")
app.include_router(ntrs_router, prefix="/api")
app.include_router(timeline_router, prefix="/api")
app.include_router(knowledge_router, prefix="/api")
app.include_router(diary_router, prefix="/api")
app.include_router(nutrition_router, prefix="/api")
app.include_router(orbit_router, prefix="/api")
app.include_router(descriptive_router, prefix="/api")
app.include_router(risks_router, prefix="/api")
app.include_router(systems_router, prefix="/api")
app.include_router(planner_router, prefix="/api")
app.include_router(pvt_router, prefix="/api")
app.include_router(cognition_router, prefix="/api")
app.include_router(sensor_bindings_router, prefix="/api")
app.include_router(location_router, prefix="/api")
app.include_router(alert_history_router, prefix="/api")
app.include_router(baseline_profile_router, prefix="/api")
app.include_router(twins_router, prefix="/api")
app.include_router(resources_router, prefix="/api")
app.include_router(testbeds_router, prefix="/api")
app.include_router(facilities_router, prefix="/api")
app.include_router(datasets_router, prefix="/api")
app.include_router(osdr_data_router, prefix="/api")
app.include_router(guides_router, prefix="/api")
app.include_router(people_router, prefix="/api")
app.include_router(mission_profiles_router, prefix="/api")
app.include_router(context_sources_router, prefix="/api")
app.include_router(ground_notes_router, prefix="/api")
app.include_router(help_requests_router, prefix="/api")
app.include_router(spec5_router, prefix="/api")
app.include_router(assistant_router, prefix="/api")
app.include_router(sharing_router, prefix="/api")
app.include_router(space_weather_series_router, prefix="/api")
app.include_router(spice_router, prefix="/api")
app.include_router(distances_router, prefix="/api")
app.include_router(correlations_router, prefix="/api")
app.include_router(inventory_router, prefix="/api")


@app.exception_handler(TamperedRecordError)
async def _integrity_compromised(_: Request, exc: TamperedRecordError) -> JSONResponse:
    """Un dato sin respaldo de firma no se analiza: se dice, y se dice cual.

    Sin esto, `query()` al detectar un asiento manipulado se convertia en un 500
    generico: la tripulacion veia "error del servidor" donde deberia ver que la
    integridad del registro esta comprometida y en que asiento. No se emite
    ningun veredicto clinico sobre datos que la cadena ya no respalda.
    """
    return JSONResponse(
        status_code=409,
        content={"detail": f"integridad comprometida: {exc}", "integrity_ok": False},
    )


@app.exception_handler(RequestValidationError)
async def _invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Un 422 que siempre se puede serializar.

    El manejador por defecto devuelve en `input` el dato recibido. Con un texto que tenia
    un sustituto UTF-16 suelto, la respuesta no se podia codificar; con un JSON anidado a
    cientos de niveles, serializarlo agotaba la pila. En ambos casos el 422 acababa en
    500. Aqui se devuelve solo el tipo del dato: el cliente ya sabe lo que mando.
    """
    errors = [{**error, "input": type(error.get("input")).__name__} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


@app.exception_handler(UntrustedSigner)
async def _untrusted_signer(_: Request, exc: UntrustedSigner) -> JSONResponse:
    """Un firmante que el registro no admite es un conflicto, no un fallo del servidor.

    El caso real: una fuente cuya clave ya esta fijada en el registro llega con otra
    (`KeyConflict`). Antes salia como 500.
    """
    return JSONResponse(status_code=409, content={"detail": f"firmante no autorizado: {exc}"})


def mount_frontend(target: FastAPI, dist: Path | None) -> bool:
    """Sirve la interfaz compilada desde el mismo origen que la API.

    Es lo que hace la aplicacion de escritorio: la ventana carga
    `http://127.0.0.1:<puerto>/`, y la interfaz llama a `/api` sin cruzar origenes.
    Asi el CORS de arriba sigue siendo solo para desarrollo y no hay que abrirlo.

    Se monta despues de la API: `/api/...` nunca queda tapado por un fichero, y una
    ruta de la API que no existe sigue dando su 404 en JSON, no la pagina.
    """
    if dist is None or not (dist / "index.html").is_file():
        return False
    target.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return True


mount_frontend(app, get_settings().frontend_dist)
# «Descargar también los modelos de IA», marcado en el instalador (`desktop/installer.nsh`): la
# descarga empieza sola en segundo plano y se ve en «Modelos de IA».
models_autostart(get_settings())
