"""«Descargar modelos»: el estado del paquete de modelos y la orden de bajarlo.

La descarga en sí está en `app/models_download.py`.

Por qué existe: la consola tiene que poder decir qué piezas del paquete hay instaladas, qué hay
publicado y cuánto pesa, y bajarlo todo junto o por piezas (decisión del usuario, 2026-11-15).
El texto que se ve lo compone aquí el backend, en el idioma de cada petición: la descarga corre en
otro hilo y solo deja códigos.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.console_header import console_post
from app.api.routes import SettingsDep
from app.core.config import Settings
from app.core.i18n import tr
from app.models_download import PackError, downloader, installed, models_dir

models_pack_router = APIRouter(prefix="/models-pack")


class DownloadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # None: todo lo que falte («todo junto»).
    components: list[str] | None = Field(default=None, max_length=16)


def _label(name: str) -> str:
    labels = {
        "ollama": tr("Modelos de lenguaje (Ollama)", "Language models (Ollama)"),
        "voice": tr("Transcripción de voz (Whisper)", "Speech transcription (Whisper)"),
        "segmentation": tr("Segmentación de TAC (TotalSegmentator)",
                           "CT segmentation (TotalSegmentator)"),
        "tesseract": tr("Lectura de informes escaneados (Tesseract)",
                        "Scanned report reading (Tesseract)"),
    }
    return labels.get(name, name)


def _message(code: str, detail: str) -> str:
    messages = {
        "blocked": tr("No sale nada a internet ahora", "Nothing goes out to the internet now"),
        "network": tr("No se pudo conectar con el servidor de descarga",
                      "Could not reach the download server"),
        "not-published": tr("El paquete de modelos todavía no está publicado",
                            "The model pack is not published yet"),
        "bad-index": tr("El índice publicado no es válido", "The published index is not valid"),
        "bad-part": tr("Un trozo descargado no coincide con su huella",
                       "A downloaded part does not match its fingerprint"),
        "bad-archive": tr("El paquete trae un fichero que el manifiesto no nombra",
                          "The pack carries a file the manifest does not list"),
        "bad-file": tr("Un fichero no coincide con el manifiesto",
                       "A file does not match the manifest"),
        "no-space": tr("No hay espacio suficiente en el disco", "There is not enough disk space"),
        "in-use": tr("La pieza está en uso: cierra EMMA y vuelve a intentarlo desde el USB",
                     "The piece is in use: close EMMA and install it from the USB"),
        "foreign-dir": tr("La carpeta de destino ya existe y no es del paquete de modelos",
                          "The destination folder exists and is not a model pack"),
        "unknown-component": tr("Pieza desconocida", "Unknown piece"),
        "busy": tr("Ya hay una descarga en curso", "A download is already running"),
        "disk": tr("No se pudo escribir en el disco", "Could not write to disk"),
    }
    text = messages.get(code, code)
    return f"{text}: {detail}" if detail else text


def _state(settings: Settings) -> dict[str, Any]:
    dest = models_dir(settings)
    snap = downloader.snapshot()
    catalog = snap["catalog"]
    have = installed(dest)
    pieces: list[dict[str, Any]] = []
    published = catalog["components"] if catalog is not None else {}
    for name in dict.fromkeys([*published, *have]):
        piece = published.get(name)
        pieces.append({
            "name": name,
            "label": _label(name),
            "installed": name in have,
            "current": catalog is not None and have.get(name) == catalog["pack_created"],
            "published": piece is not None,
            "download_bytes": sum(int(p["size"]) for p in piece["parts"]) if piece else None,
            "installed_bytes": int(piece["installed_size"]) if piece else None,
        })
    job = snap["job"]
    if job.get("state") == "error":
        job["message"] = _message(str(job.get("error")), str(job.get("detail", "")))
    if job.get("component"):
        job["component_label"] = _label(str(job["component"]))
    return {
        "folder": str(dest),
        "source": settings.models_url,
        "network": not settings.offline,
        "network_note": None if not settings.offline else tr(
            "EMMA está en modo sin red: la descarga no puede salir. Se puede instalar desde el USB "
            "con instalar.cmd.",
            "EMMA is in offline mode: the download cannot go out. It can be installed from the USB "
            "with instalar.cmd.",
        ),
        "checked": catalog is not None,
        "pack_created": catalog["pack_created"] if catalog is not None else None,
        "pieces": pieces,
        "job": job,
        "restart_note": tr(
            "Lo instalado se usa la próxima vez que se abre EMMA.",
            "What is installed is used the next time EMMA opens.",
        ),
    }


@models_pack_router.get("")
def read_models_pack(settings: SettingsDep) -> dict[str, Any]:
    """Lo instalado y, si ya se consultó, lo publicado. No sale a la red."""
    return _state(settings)


@models_pack_router.post("/check", **console_post())
def check_models_pack(settings: SettingsDep) -> dict[str, Any]:
    """Consulta qué hay publicado (sale por la puerta, propósito `models-pack`)."""
    try:
        downloader.check(settings)
    except PackError as exc:
        raise HTTPException(status_code=502, detail=_message(exc.code, exc.detail)) from exc
    return _state(settings)


@models_pack_router.post("/download", status_code=202, **console_post())
def download_models_pack(settings: SettingsDep, payload: DownloadIn) -> dict[str, Any]:
    try:
        downloader.start(settings, payload.components)
    except PackError as exc:
        raise HTTPException(status_code=409, detail=_message(exc.code, exc.detail)) from exc
    return _state(settings)


@models_pack_router.post("/cancel", **console_post())
def cancel_models_pack(settings: SettingsDep) -> dict[str, Any]:
    downloader.cancel()
    return _state(settings)


def autostart(settings: Settings) -> bool:
    """La descarga pedida en el instalador: el paquete entero, si no hay ninguna pieza instalada.

    Solo con `models_autodownload` (lo pone la aplicación de escritorio) y con red: en modo sin
    red no se intenta, y el panel «Modelos de IA» lo dice. Devuelve si la ha lanzado.
    """
    if not settings.models_autodownload or settings.offline:
        return False
    if installed(models_dir(settings)):
        return False
    try:
        downloader.start(settings, None)
    except PackError:
        return False
    return True
