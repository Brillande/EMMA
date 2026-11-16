# SPDX-License-Identifier: AGPL-3.0-or-later
"""La única salida de EMMA a internet.

Por qué existe: cada cliente salía por su cuenta (DONKI, RadLab, JPL Horizons, los registros de
citas) y comprobaba el modo sin red a mano, cada uno a su manera. Así no hay forma de decir
"ahora no sale nada" (modo seguro), ni de asegurar que no salga un dato de salud en una consulta,
ni de saber qué salió. Aquí pasa toda petición, y aquí se decide:

1. **Lista blanca**: cada propósito tiene sus hosts. Un host fuera de lista es un error de
   programación y falla ruidosamente (`EgressNotAllowed`), no se degrada en silencio.
2. **Sin red y modo seguro**: con `offline` o con el modo seguro activo (`safe-mode` firmado en el
   ledger), no sale nada (`EgressBlocked`, que es un `httpx.HTTPError`: los clientes ya saben
   degradar a la caché con eso).
3. **Lo que sale**: la URL y la consulta pasan por `borde.egress_check` de Polaris (copia en
   `polaris/tools/`) hacia un destino no confiable. Ningún dato de salud ni ningún canario sale.
   Nunca escala a su código rojo (`escalar=False`): ese avisa por Telegram y apaga demonios de
   macOS, cosas que en EMMA no existen.
4. **Reintentos corteses**: `_net.with_retries` de Polaris, tal cual (429/5xx y fallos de red,
   con espera exponencial y `Retry-After`).
5. **Traza**: una línea JSON por petición con hora, propósito, host, ruta y veredicto; nunca la
   consulta ni el cuerpo (como `salida._audit`).

Excepción declarada: `astroquery` (JPL Horizons) habla por `requests`, no por httpx. Para ella la
puerta autoriza antes de llamar (`authorize`); la llamada la hace su librería.

Licencia y origen (AGPL §5a): usa `polaris/tools/borde.py` y `polaris/tools/_net.py` de la copia
literal de Polaris, sin modificarla (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la
autora de Polaris, «Beyond the Protocol»); se cargan con `app.polaris.load`. De EMMA: la lista
blanca por propósito, el modo sin red, el modo seguro y la traza. El señuelo de `canarios.py` lo
siembra `app.polaris.seed_decoy`.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time
import urllib.error
from collections.abc import Callable
from email.message import Message
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from app import polaris
from app.core.config import Settings

# Propósito -> hosts permitidos. Lo que no esté aquí no sale.
ALLOWLIST: dict[str, frozenset[str]] = {
    "space-weather": frozenset({"api.nasa.gov"}),
    # Series de protones y viento solar (CCMC iSWA, HAPI, sin clave): `environment/iswa.py`.
    "space-weather-series": frozenset({"iswa.gsfc.nasa.gov"}),
    "radiation": frozenset({"visualization.osdr.nasa.gov"}),
    # La ficha de los estudios de OSDR que EMMA cita (`evidence/osdr_data.py`): solo sale el
    # identificador público del estudio (OSD-288…), nada de la tripulación.
    "osdr-data": frozenset({"visualization.osdr.nasa.gov"}),
    "ephemeris": frozenset({"ssd.jpl.nasa.gov", "ssd-api.jpl.nasa.gov"}),
    # Los núcleos SPICE públicos de NAIF (`scripts/fetch_spice_kernels.py`): solo la URL del
    # fichero. La aplicación calcula con ellos sin red (`environment/spice.py`).
    "spice-kernels": frozenset({"naif.jpl.nasa.gov"}),
    # Posición de la ISS para el perfil de órbita baja (SSCweb, `environment/orbit.py`).
    "orbit": frozenset({"sscweb.gsfc.nasa.gov"}),
    "citations": frozenset({
        "api.crossref.org", "api.datacite.org", "doi.org",
        "eutils.ncbi.nlm.nih.gov", "clinicaltrials.gov",
        # Informes técnicos de la NASA por su número de NTRS (`evidence/ntrs.py`).
        "ntrs.nasa.gov",
    }),
    # Solo los guiones de validación (`scripts/fetch_lifesnaps.py`): la aplicación no sale por aquí.
    "datasets": frozenset({"zenodo.org"}),
    # Marplanner (`marplanner/`, `api/planner.py`): la cita del día y las efemérides de su hoja
    # diaria. Solo sale la fecha y el idioma, nada del hogar ni de la tripulación (decisión del
    # usuario, 2026-11-12: datos que entran, sí; con red y nunca en modo sin red).
    "planner-quotes": frozenset({"zenquotes.io"}),
    "planner-onthisday": frozenset({"en.wikipedia.org", "es.wikipedia.org"}),
    # «Descargar modelos» (`app/models_download.py`): el paquete de modelos publicado como
    # ficheros de una versión de GitHub. Solo sale la URL del fichero; GitHub redirige cada
    # descarga a su almacén de ficheros, y la puerta autoriza también esa segunda petición.
    "models-pack": frozenset({
        "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com",
    }),
    # «Actualizar EMMA» (`app/app_update.py`): el manifiesto `emma-update.json` y el instalador
    # de la última versión publicada en GitHub, solo cuando la persona lo pide. Solo sale la URL
    # del fichero, nada de la tripulación; GitHub redirige la descarga a su almacén de ficheros,
    # y la puerta autoriza también esa segunda petición.
    "app-update": frozenset({
        "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com",
    }),
}
RETRY_TRIES = 3
RETRY_BASE_S = 0.25
RETRY_CAP_S = 2.0
# Tope TOTAL de una llamada con sus reintentos (`deadline` de `_net.with_retries`). Sin él, un 429
# de DONKI con `Retry-After` de horas (`DEMO_KEY` agotada) hacía esperar 2 × 120 s a cada
# `/api/status`: la consola tardaba 4 min en abrir. Si la espera no cabe, se falla ya y el cliente
# usa su caché con la edad declarada.
RETRY_BUDGET_S = 10.0


class EgressNotAllowed(RuntimeError):
    """Un host o un propósito que no está en la lista blanca: error de programación."""


class EgressBlocked(httpx.HTTPError):
    """La salida está cerrada ahora (sin red, modo seguro o contenido que no puede salir)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# Quién dice si el modo seguro está activo. Lo fija la aplicación al arrancar (el almacén vive en
# la capa de API); sin proveedor, el modo seguro está apagado.
_safe_mode: Callable[[], str | None] | None = None
_audit_lock = threading.Lock()


def set_safe_mode_provider(provider: Callable[[], str | None] | None) -> None:
    """`provider()` devuelve el motivo si el modo seguro está activo, o None."""
    global _safe_mode
    _safe_mode = provider


def safe_mode_reason() -> str | None:
    """El motivo del modo seguro si está activo, o None.

    Para lo que el modo seguro también para sin salir a internet: instalar una versión nueva de
    EMMA ya descargada (`app_update.Updater.request_install`).
    """
    return _safe_mode() if _safe_mode is not None else None


_border_lock = threading.Lock()
_border_module: Any = None


def _border() -> Any:
    """El borde de Polaris, con su señuelo sembrado: una sola vez, también con varios hilos.

    Iba bajo `@cache`, que recuerda el resultado pero no impide que dos hilos entren a la vez la
    primera vez; y la primera vez es cuando arranca la consola y pide DONKI, RadLab y efemérides
    casi a la par. Los dos sembraban, y `canarios._escribir` usa un `.tmp` de nombre fijo: en
    Windows el segundo `os.replace` da `PermissionError` y esa petición fallaba sin motivo.
    """
    global _border_module
    if _border_module is None:
        with _border_lock:
            if _border_module is None:
                border = polaris.load("borde")
                # El señuelo, la primera vez que se carga la puerta: sin él, el control de
                # canarios del borde no tiene nada que buscar (Polaris lo vio el 24-sep: un
                # tripwire que no podía dispararse).
                polaris.seed_decoy()
                _border_module = border  # solo si se sembró: si falla, la siguiente reintenta
    return _border_module


def halt_state() -> dict[str, Any]:
    """Si el freno por fichero está puesto, dónde y desde cuándo, para enseñarlo junto al modo
    seguro.

    `since` existe porque un freno olvidado no se nota: el `CHANGELOG.md` de Polaris cuenta una
    rutina parada semanas por un `HALT` que nadie recordaba haber puesto. Es la fecha de
    modificación del fichero (UTC, ISO 8601), o None si no está puesto. **No es un asiento
    firmado**: el freno no es el modo seguro, EMMA no lo crea ni lo firma, y esa fecha la pone el
    sistema de ficheros; quien copie o toque el fichero la cambia. Vale para saber cuánto lleva
    ahí, no como prueba de quién lo puso ni cuándo. El aviso que pinta la consola lo compone
    `api/safe_mode.halt_notice` a partir de esto.

    Solo mira el disco: no carga el borde (leer el estado no debe depender de que importe).
    """
    path = polaris.halt_file()
    state: dict[str, Any] = {"active": path.exists(), "file": str(path), "since": None}
    if state["active"]:
        try:
            modified = path.stat().st_mtime
        except OSError:
            # Lo borraron entre mirar y leer su fecha (levantar el freno es borrarlo): ya no está
            # puesto, y esta lectura no puede fallar por eso.
            state["active"] = False
        else:
            state["since"] = dt.datetime.fromtimestamp(modified, dt.UTC).isoformat(
                timespec="seconds"
            )
    return state


@cache
def _net() -> Any:
    return polaris.load("_net")


def _audit(settings: Settings, purpose: str, url: str, verdict: str, reason: str) -> None:
    parts = urlsplit(url)
    line = {
        "ts": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "purpose": purpose,
        "host": parts.hostname,
        "path": parts.path,
        "verdict": verdict,
        "reason": reason,
    }
    folder = Path(settings.cache_dir) / "egress"
    with _audit_lock:
        folder.mkdir(parents=True, exist_ok=True)
        day = dt.datetime.now(dt.UTC).date().isoformat()
        with (folder / f"audit-{day}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")


def authorize(settings: Settings, purpose: str, url: str, query: str = "") -> None:
    """Deja salir `url` con este propósito, o lanza. Se llama antes de cada petición."""
    hosts = ALLOWLIST.get(purpose)
    host = urlsplit(url).hostname or ""
    if hosts is None or host not in hosts:
        _audit(settings, purpose, url, "deny", "fuera de la lista blanca")
        raise EgressNotAllowed(f"{host!r} no está permitido para {purpose!r}")
    if settings.offline:
        _audit(settings, purpose, url, "deny", "modo sin red")
        raise EgressBlocked("el sistema está en modo sin red")
    reason = safe_mode_reason()
    if reason is not None:
        _audit(settings, purpose, url, "deny", "modo seguro")
        raise EgressBlocked(f"modo seguro activo: {reason}")
    border = _border()
    # El freno por fichero de Polaris, confinado al estado de EMMA (`polaris.halt_file` dice qué
    # es y en qué se distingue del modo seguro). El borde ya lo negaría, pero con un "HALT activo"
    # a secas: quien lo lea tiene que saber que no es el modo seguro y qué fichero borrar.
    if border.halted():
        # Lo que mira el borde de verdad, no lo que debería mirar: si algún día no coinciden, el
        # error sigue diciendo qué fichero es.
        watched = [str(path) for path in border.HALT_FILES]
        found = [path for path in watched if os.path.exists(path)] or watched
        _audit(settings, purpose, url, "deny", "freno HALT de Polaris (fichero)")
        raise EgressBlocked(
            f"freno HALT activo (no es el modo seguro): existe {', '.join(found)}; "
            "la salida vuelve cuando una persona lo borra"
        )
    verdict = border.egress_check(
        f"{url} {query}".strip(), destino=f"externo:{purpose}", escalar=False, consulta=True
    )
    if not verdict.permitido:
        _audit(settings, purpose, url, "deny", str(verdict.motivo))
        raise EgressBlocked(f"no sale: {verdict.motivo}")
    _audit(settings, purpose, url, "allow", "ok")


def _retrying(send: Callable[[], httpx.Response], url: str) -> httpx.Response:
    """`_net.with_retries` de Polaris sobre httpx: traduce a los errores de urllib que espera."""
    net = _net()

    def attempt() -> httpx.Response:
        try:
            response = send()
        except httpx.TransportError as exc:
            raise urllib.error.URLError(exc) from exc
        if response.status_code in net.RETRY_STATUS:
            headers = Message()
            for key, value in response.headers.items():
                headers[key] = value
            raise urllib.error.HTTPError(url, response.status_code, "reintentable", headers, None)
        return response

    try:
        result: httpx.Response = net.with_retries(
            attempt, tries=RETRY_TRIES, base=RETRY_BASE_S, cap=RETRY_CAP_S,
            deadline=time.monotonic() + RETRY_BUDGET_S,
        )
        return result
    except urllib.error.HTTPError as exc:
        request = httpx.Request("GET", url)
        raise httpx.HTTPStatusError(
            f"{exc.code} tras reintentar", request=request,
            response=httpx.Response(exc.code, request=request),
        ) from exc
    except urllib.error.URLError as exc:
        raise httpx.ConnectError(str(exc.reason)) from exc


Params = dict[str, Any] | list[tuple[str, Any]]


def get(
    settings: Settings, purpose: str, url: str, *, params: Params | None = None,
) -> httpx.Response:
    """GET autorizado, con reintentos corteses. Sustituye a `httpx.get` en los clientes."""
    pairs = list(params.items()) if isinstance(params, dict) else list(params or [])
    # La clave de la API no es contenido que clasificar (y no debe acabar en la traza del borde).
    authorize(settings, purpose, url, " ".join(
        f"{key}={value}" for key, value in pairs if key != "api_key"
    ))
    return _retrying(
        lambda: httpx.get(url, params=params, timeout=settings.request_timeout), url
    )


def client(settings: Settings, purpose: str) -> httpx.Client:
    """Un `httpx.Client` que pasa cada petición por la puerta (para el comprobador de citas)."""

    def check(request: httpx.Request) -> None:
        authorize(settings, purpose, str(request.url.copy_with(query=None)),
                  request.url.query.decode("ascii", "replace"))

    return httpx.Client(
        timeout=settings.request_timeout, follow_redirects=True,
        event_hooks={"request": [check]},
    )
