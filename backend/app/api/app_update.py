"""«Actualizar EMMA»: el estado de la actualización y las órdenes de comprobar, bajar e instalar.

La consulta y la descarga están en `app/app_update.py`.

Por qué existe: la consola tiene que poder decir qué versión corre, si hay otra publicada y
cuánto pesa, y bajarla e instalarla cuando la persona lo pida (decisión del usuario, 2026-11-16).
Nada de esto ocurre solo: no hay comprobación al arrancar. El texto que se ve lo compone aquí el
backend, en el idioma de cada petición: la descarga corre en otro hilo y solo deja códigos.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.console_header import console_post
from app.api.routes import SettingsDep
from app.app_update import (
    UpdateError,
    install_request,
    is_newer,
    parse_version,
    ready,
    updater,
)
from app.core.config import Settings
from app.core.i18n import tr

app_update_router = APIRouter(prefix="/app-update")

# Código de error -> estado HTTP de la orden que lo da.
_HTTP = {
    "offline": 503, "blocked": 503,
    "network": 502, "not-published": 502, "installer-missing": 502,
    "bad-manifest": 502, "bad-hash": 502,
    "busy": 409, "same-version": 409, "not-ready": 409, "safe-mode": 423,
    "no-space": 507, "disk": 500,
}


def _message(code: str, detail: str) -> str:
    messages = {
        "offline": tr("EMMA está en modo sin red: no se puede buscar ni bajar una versión nueva",
                      "EMMA is in offline mode: a new version cannot be searched for or "
                      "downloaded"),
        "blocked": tr("No sale nada a internet ahora", "Nothing goes out to the internet now"),
        "network": tr("No se pudo conectar con el servidor de versiones",
                      "Could not reach the release server"),
        "not-published": tr("La última versión publicada no trae manifiesto de actualización",
                            "The latest published release has no update manifest"),
        "installer-missing": tr(
            "La versión publicada no trae el instalador que nombra su manifiesto",
            "The published release does not carry the installer its manifest names",
        ),
        "bad-manifest": tr("El manifiesto publicado no es válido",
                           "The published manifest is not valid"),
        "bad-hash": tr("El instalador descargado no coincide con su huella",
                       "The downloaded installer does not match its fingerprint"),
        "no-space": tr("No hay espacio suficiente en el disco", "There is not enough disk space"),
        "not-ready": tr("No hay ningún instalador descargado y comprobado",
                        "There is no downloaded and verified installer"),
        "same-version": tr("La versión publicada no es más nueva que la instalada",
                           "The published version is not newer than the installed one"),
        "busy": tr("Ya hay una descarga en curso", "A download is already running"),
        "safe-mode": tr("El modo seguro está activo: no se instala una versión nueva hasta "
                        "desactivarlo",
                        "Safe mode is on: a new version is not installed until it is turned off"),
        "disk": tr("No se pudo escribir en el disco", "Could not write to disk"),
    }
    text = messages.get(code, code)
    return f"{text}: {detail}" if detail else text


def _state(settings: Settings) -> dict[str, Any]:
    snap = updater.snapshot()
    job, manifest, error = snap["job"], snap["manifest"], snap["error"]
    done = ready(settings)
    request = install_request(settings)
    newer = is_newer(manifest["version"], settings.app_version) if manifest else None
    if job["state"] == "running":
        state = "downloading"
    elif error is not None:
        # Antes que «ready»: un fallo nuevo no se esconde tras un instalador anterior listo.
        state = "error"
    elif done is not None:
        state = "ready"
    elif manifest is not None:
        state = "up-to-date" if newer is False else "available"
    else:
        state = "idle"
    return {
        "state": state,
        "phase": job.get("phase"),
        "current_version": settings.app_version,
        "available": None if manifest is None else {
            "version": manifest["version"], "size": manifest["size"], "notes": manifest["notes"],
        },
        # Si la versión que corre se conoce (y entonces se puede comparar con la publicada).
        "comparable": parse_version(settings.app_version) is not None,
        "done_bytes": int(job.get("done_bytes", 0)),
        "total_bytes": int(job.get("total_bytes", 0)),
        "ready": None if done is None else {"version": done["version"]},
        "install_requested": done is not None and request is not None
        and request.get("version") == done["version"],
        "error": None if error is None else {"code": error[0],
                                             "message": _message(error[0], error[1])},
        "network": not settings.offline,
        "network_note": None if not settings.offline else tr(
            "EMMA está en modo sin red: no busca ni baja versiones nuevas. Una versión nueva se "
            "puede instalar con su instalador desde un USB.",
            "EMMA is in offline mode: it does not search for or download new versions. A new "
            "version can be installed with its installer from a USB drive.",
        ),
        "restart_note": tr(
            "La versión nueva se instala al cerrar EMMA y se usa al volver a abrirla.",
            "The new version is installed when EMMA closes and is used when it opens again.",
        ),
    }


def _http(exc: UpdateError) -> HTTPException:
    return HTTPException(status_code=_HTTP.get(exc.code, 502),
                         detail=_message(exc.code, exc.detail))


@app_update_router.get("")
def read_app_update(settings: SettingsDep) -> dict[str, Any]:
    """La versión que corre y, si ya se consultó, la publicada. No sale a la red."""
    return _state(settings)


@app_update_router.post("/check", **console_post())
def check_app_update(settings: SettingsDep) -> dict[str, Any]:
    """Consulta la última versión publicada (sale por la puerta, propósito `app-update`)."""
    try:
        updater.check(settings)
    except UpdateError as exc:
        raise _http(exc) from exc
    return _state(settings)


@app_update_router.post("/download", status_code=202, **console_post())
def download_app_update(settings: SettingsDep) -> dict[str, Any]:
    try:
        updater.start(settings)
    except UpdateError as exc:
        raise _http(exc) from exc
    return _state(settings)


@app_update_router.post("/cancel", **console_post())
def cancel_app_update(settings: SettingsDep) -> dict[str, Any]:
    updater.cancel()
    return _state(settings)


@app_update_router.post("/install", **console_post())
def install_app_update(settings: SettingsDep) -> dict[str, Any]:
    """Deja la instalación pedida (`instalar.json`); la hace la aplicación de escritorio."""
    try:
        updater.request_install(settings)
    except UpdateError as exc:
        raise _http(exc) from exc
    return _state(settings)
