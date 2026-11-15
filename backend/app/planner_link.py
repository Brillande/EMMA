"""El enlace de EMMA con el servidor de Marplanner, en esta misma máquina.

Por qué existe: la consola de EMMA enseña el planificador (Marplanner, `marplanner/`) con sus
propias pantallas. Marplanner pide a cada cliente una clave de dispositivo, que se obtiene con su
clave de arranque. Si la consola las manejara, quedarían en el navegador. Aquí las guarda el
backend: se aprovisiona un dispositivo la primera vez y se reenvía cada petición con su clave. El
servidor de Marplanner solo puede estar en loopback, como el modelo local (`interpret/llm.py`): no
es una salida a internet y no pasa por `core/egress.py`.

Configuración por entorno, sin tocar `core/config.py`:
  - `EMMA_PLANNER_URL`            dónde escucha Marplanner (por defecto http://127.0.0.1:8790);
  - `EMMA_PLANNER_BOOTSTRAP_KEY`  su clave de arranque (por defecto, la de ejemplo de Marplanner).

Solo pasan rutas de su API de uso diario (`ALLOWED_PREFIXES`): ni el aprovisionamiento, ni la
gestión de complementos, ni las copias de seguridad, que son de su administración.

Los complementos que EMMA usa (`EMMA_PLUGINS`) los activa este enlace al aprovisionarse: en una
base nueva Marplanner los deja todos inactivos y sus rutas responden 503 «This plugin is
unavailable» (visto en el instalador, 2026-11-12). Los que sacan datos —`weather`,
`network-devices`— no se activan nunca. `printing` sí: Marplanner solo dibuja la imagen de la hoja
diaria con él activo, y sin ella la hoja se componía pero no se veía (409
`printable_raster_missing`, el usuario: «no me llega la hoja», 2026-11-12). En el servidor es la
cola y el dibujo, sin red ni hardware; la impresora térmica la maneja la pantalla de EMMA por
Bluetooth (`frontend/src/planner/printing/`), y por eso sus rutas pasan (2026-11-13).

Marplanner viene en inglés y la hoja diaria salía en inglés (títulos, chistes, palabra del día).
EMMA es en español y no tiene ajuste de idioma para el planificador, así que el enlace lo deja en
español al aprovisionarse (`_use_spanish`; petición del usuario, 2026-11-12).

Y los tripulantes de EMMA son los miembros del planificador (`ensure_crew`): uno por tripulante,
con su mismo nombre, creado la primera vez que se lee el planificador con ese tripulante en el
registro. Antes había que darlos de alta a mano en «Miembros» aunque la consola ya supiera quién
es crew-01 (queja del usuario, 2026-11-12). Uno archivado a mano no se vuelve a crear.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
DEFAULT_URL = "http://127.0.0.1:8790"
# La de `marplanner/.env.example`: la que usa `planner-bridge/start-marplanner.mjs` si no hay otra.
DEFAULT_BOOTSTRAP_KEY = "mpk-local-bootstrap-change-me"
DEVICE_COOKIE = "mp_device_key"
TIMEOUT_S = 10.0
MAX_BODY_BYTES = 2 * 1024 * 1024
# Fuera a propósito: `auth`, `plugins`, `backups`, `telemetry` (su administración), `weather` y
# `network-devices` (Open-Meteo y UniFi, que sacan datos nuestros).
# `printing` sí pasa: la cola de impresión de la hoja diaria. La pantalla de EMMA recoge el trabajo
# y lo manda a la impresora térmica por Bluetooth, en la nave; nada sale fuera (petición del
# usuario, 2026-11-13: «vamos a hacernos con una impresora de calor»).
ALLOWED_PREFIXES = (
    "members", "chores", "routines", "menu", "meal-entries", "meal-plans", "recipes", "calendar",
    "reminders", "daily-messages", "day-periods", "settings", "daily-briefing",
    "time-announcements", "printing",
)
METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
# Decisión del usuario (2026-11-12): «queremos todo» menos lo que saca datos fuera.
SPANISH = "es"
EMMA_PLUGINS = (
    "daily-briefing", "time-announcements", "backups", "meals-recipes", "reminders",
    "daily-messages", "printing",
)


class PlannerUnavailable(RuntimeError):
    """Marplanner no está arrancado o no responde."""


class PlannerPathRefused(ValueError):
    """Una ruta fuera de la API de uso diario de Marplanner."""


@dataclass(frozen=True)
class Reply:
    status: int
    content_type: str
    body: bytes


def base_url() -> str:
    url = os.environ.get("EMMA_PLANNER_URL", DEFAULT_URL).rstrip("/")
    host = urlsplit(url).hostname or ""
    if host not in LOOPBACK_HOSTS:
        raise PlannerUnavailable(
            f"Marplanner tiene que estar en esta máquina (loopback), no {host!r}"
        )
    return url


def check_path(path: str) -> str:
    clean = path.strip("/")
    first = clean.split("/", 1)[0]
    if ".." in clean.split("/") or first not in ALLOWED_PREFIXES:
        raise PlannerPathRefused(f"ruta de Marplanner no permitida: {path!r}")
    return clean


class PlannerLink:
    """Un dispositivo aprovisionado en Marplanner y las peticiones con su clave."""

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._lock = threading.Lock()
        self._device_key: str | None = None
        self._transport = transport
        # Tripulantes ya comprobados en Marplanner: no se pregunta en cada lectura.
        self._crew_known: set[str] = set()
        # Las pantallas piden varias cosas a la vez al abrir: sin este cerrojo, dos lecturas
        # simultáneas creaban dos crew-01.
        self._crew_lock = threading.Lock()

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=base_url(), timeout=TIMEOUT_S, transport=self._transport)

    def _provision(self, client: httpx.Client) -> str:
        key = os.environ.get("EMMA_PLANNER_BOOTSTRAP_KEY", DEFAULT_BOOTSTRAP_KEY)
        response = client.post("/api/auth/provision", headers={"Authorization": f"Bearer {key}"})
        device = response.cookies.get(DEVICE_COOKIE)
        if response.status_code >= 300 or not device:
            raise PlannerUnavailable(
                f"Marplanner no aprovisionó el dispositivo ({response.status_code})"
            )
        self._activate_plugins(client, device)
        self._use_spanish(client, device)
        return device

    def _use_spanish(self, client: httpx.Client, device: str) -> None:
        """Pone en español el idioma del hogar de Marplanner si no lo está (idempotente)."""
        headers = {"Cookie": f"{DEVICE_COOKIE}={device}"}
        current = client.get("/api/settings", headers=headers)
        locale = current.json().get("locale") if current.status_code == 200 else None
        if not isinstance(locale, dict) or locale.get("language") == SPANISH:
            return
        # El PUT reemplaza el objeto entero: se reenvía con su zona horaria y su primer día.
        response = client.put(
            "/api/settings", headers=headers,
            json={"object": "locale", "settings": {**locale, "language": SPANISH}},
        )
        if response.status_code != 200:
            raise PlannerUnavailable(f"Marplanner no aceptó el español ({response.status_code})")

    def _activate_plugins(self, client: httpx.Client, device: str) -> None:
        """Activa los complementos de `EMMA_PLUGINS` que estén inactivos (idempotente)."""
        headers = {"Cookie": f"{DEVICE_COOKIE}={device}"}
        listing = client.get("/api/plugins", headers=headers)
        if listing.status_code != 200:
            raise PlannerUnavailable(
                f"Marplanner no dio su lista de complementos ({listing.status_code})"
            )
        states = {p.get("id"): p.get("state") for p in listing.json().get("plugins", [])}
        for plugin in EMMA_PLUGINS:
            if states.get(plugin) == "active":
                continue
            response = client.post(f"/api/plugins/{plugin}/activate", headers=headers)
            if response.status_code != 200:
                raise PlannerUnavailable(
                    f"Marplanner no activó {plugin} ({response.status_code})"
                )

    def ensure_crew(self, subjects: Sequence[str]) -> None:
        """Crea en Marplanner un miembro por cada tripulante que aún no tenga (por su nombre)."""
        # Si otra lectura ya está creándolos, esta no espera: sigue y lee lo que haya. Esperar en
        # cola ocupaba hilos del backend mientras Marplanner anotaba en su ledger.
        if not self._crew_lock.acquire(blocking=False):
            return
        try:
            self._ensure_crew(subjects)
        finally:
            self._crew_lock.release()

    def _ensure_crew(self, subjects: Sequence[str]) -> None:
        pending = [s for s in subjects if s not in self._crew_known]
        if not pending:
            return
        reply = self.request("GET", "members", [("lifecycle", "all")], None, None)
        if reply.status != 200:
            return  # el planificador se lee igual; se intentará en la próxima lectura
        listing = json.loads(reply.body)
        if not isinstance(listing, list):
            return
        names = {str(m.get("displayName", "")) for m in listing if isinstance(m, dict)}
        for subject in pending:
            if subject not in names:
                body = json.dumps({"displayName": subject, "role": "parent"}).encode()
                created = self.request("POST", "members", [], body, "application/json")
                if created.status >= 300:
                    continue
            self._crew_known.add(subject)

    def request(
        self, method: str, path: str, params: Sequence[tuple[str, str]], body: bytes | None,
        content_type: str | None,
    ) -> Reply:
        if method not in METHODS:
            raise PlannerPathRefused(f"método no permitido: {method}")
        clean = check_path(path)
        try:
            with self._client() as client:
                for attempt in (1, 2):
                    with self._lock:
                        if self._device_key is None:
                            self._device_key = self._provision(client)
                        device = self._device_key
                    headers = {"Cookie": f"{DEVICE_COOKIE}={device}"}
                    if content_type:
                        headers["Content-Type"] = content_type
                    response = client.request(
                        method, f"/api/{clean}", params=httpx.QueryParams(list(params)),
                        content=body, headers=headers,
                    )
                    # Clave caducada o revocada (Marplanner sin su ledger): se pide otra, una vez.
                    if response.status_code == 401 and attempt == 1:
                        with self._lock:
                            self._device_key = None
                        continue
                    break
        except httpx.TransportError as exc:
            raise PlannerUnavailable(f"Marplanner no responde: {exc}") from exc
        content = response.content
        if len(content) > MAX_BODY_BYTES:
            raise PlannerUnavailable("respuesta de Marplanner demasiado grande")
        return Reply(response.status_code, response.headers.get("content-type", ""), content)


_link: PlannerLink | None = None
_link_lock = threading.Lock()


def get_link() -> PlannerLink:
    global _link
    with _link_lock:
        if _link is None:
            _link = PlannerLink()
        return _link


def reset_link(link: PlannerLink | None = None) -> None:
    """Punto de sustitución para pruebas."""
    global _link
    with _link_lock:
        _link = link
