"""«Actualizar EMMA»: buscar la versión nueva publicada, bajar su instalador y dejarlo listo.

Por qué existe: decisión del usuario (2026-11-16). El EMMA instalado se quedaba en la versión con
que se instaló; para la siguiente había que ir a GitHub a mano. Las versiones se publican como
releases de github.com/Brillande/EMMA (`vX.Y.Z` con `EMMA.Setup.X.Y.Z.exe` y un `emma-update.json`
que dice cuál es, cuánto pesa y su SHA-256). Aquí se consulta y se baja; instalar lo hace la
aplicación de escritorio al leer `instalar.json`.

No se usa `electron-updater`, por tres cosas que no se negocian:

* **Sale por la puerta** (`core/egress.py`, propósito `app-update`), como todo lo demás: en modo
  sin red, con el modo seguro o con el freno de Polaris no sale nada, y queda en su traza. El modo
  seguro, además, impide pedir la instalación de lo ya descargado. Un
  actualizador propio de Electron saldría por su cuenta, sin lista blanca ni modo seguro.
* **Sin red es lo nominal** (`EMMA_OFFLINE=true`): entonces no se intenta nada y el estado lo
  dice; no es una avería.
* **Nunca automático**: no hay comprobación al arrancar ni descarga sola. La persona pide
  comprobar, pide bajar y pide instalar; cada paso es una orden suya.

Lo que se baja se comprueba (tamaño y SHA-256 del manifiesto) antes de darlo por listo, con la
misma descarga reanudable de «Descargar modelos» (`models_download.fetch_verified`). El nombre del
instalador viene de fuera, así que se valida antes de usarlo como ruta: nunca sale de
`update_dir`.

No es una vía de datos de salud: no toca el ledger ni el almacén.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.core import egress
from app.core.config import Settings
from app.models_download import Cancelled, PackError, _sha256, fetch_verified

PURPOSE = "app-update"
MANIFEST_NAME = "emma-update.json"
READY_NAME = "listo.json"
INSTALL_NAME = "instalar.json"
SCHEMA = 1
# Margen de disco sobre lo que pesa el instalador.
DISK_MARGIN = 64 * 1024 * 1024
NOTES_MAX = 2000
_SEMVER = re.compile(r"(0|[1-9]\d{0,8})\.(0|[1-9]\d{0,8})\.(0|[1-9]\d{0,8})")
_SHA = re.compile(r"[0-9a-f]{64}")
# Un nombre de fichero suelto: sin separadores, sin unidad ni flujo alterno (`:`), sin `..`.
_INSTALLER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,126}\.exe")
# Nombres reservados de dispositivo en Windows, con cualquier extensión.
_DEVICES = frozenset({"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
                      *(f"COM{n}" for n in range(10)), *(f"LPT{n}" for n in range(10))})


class UpdateError(RuntimeError):
    """Un fallo con su código, para que el texto se componga en el idioma de quien lo lee."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def update_dir(settings: Settings) -> Path:
    if settings.update_dir is not None:
        return Path(settings.update_dir)
    return Path(settings.cache_dir) / "actualizacion"


def parse_version(text: object) -> tuple[int, int, int] | None:
    """`X.Y.Z` numérico, o None. Nada de prefijos ni sufijos: se compara número a número."""
    if not isinstance(text, str):
        return None
    match = _SEMVER.fullmatch(text)
    if match is None:
        return None
    return (int(match[1]), int(match[2]), int(match[3]))


def safe_installer(name: object) -> str:
    """El nombre del instalador, si es un fichero suelto `.exe`. Lanza `bad-manifest`."""
    if (not isinstance(name, str) or ".." in name or "/" in name or "\\" in name
            or _INSTALLER.fullmatch(name) is None):
        raise UpdateError("bad-manifest", "installer")
    # Windows trata `NUL.exe`, `COM1.exe`… como el dispositivo, no como un fichero.
    if name.split(".", 1)[0].rstrip(" ").upper() in _DEVICES:
        raise UpdateError("bad-manifest", "installer")
    return name


def _inside(folder: Path, name: object) -> Path:
    """`folder/name`, comprobando además que de verdad cae dentro de `folder`."""
    path = (folder / safe_installer(name)).resolve()
    if path.parent != folder.resolve():
        raise UpdateError("bad-manifest", "installer")
    return path


def check_manifest(data: Any) -> dict[str, Any]:
    """El manifiesto publicado, validado con rigor. Lanza `UpdateError("bad-manifest")`."""
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise UpdateError("bad-manifest", "schema")
    version = data.get("version")
    if parse_version(version) is None:
        raise UpdateError("bad-manifest", "version")
    installer = safe_installer(data.get("installer"))
    size = data.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise UpdateError("bad-manifest", "size")
    sha = data.get("sha256")
    if not isinstance(sha, str) or _SHA.fullmatch(sha.lower()) is None:
        raise UpdateError("bad-manifest", "sha256")
    notes = data.get("notes", "")
    if not isinstance(notes, str):
        raise UpdateError("bad-manifest", "notes")
    return {"version": version, "installer": installer, "size": size, "sha256": sha.lower(),
            "notes": notes[:NOTES_MAX]}


def is_newer(published: str, current: str | None) -> bool | None:
    """Si `published` es mayor que `current`; None si la nuestra no se conoce o no se lee."""
    mine = parse_version(current)
    theirs = parse_version(published)
    if mine is None or theirs is None:
        return None
    return theirs > mine


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _write_json(path: Path, record: dict[str, Any]) -> None:
    """Escritura atómica: o el fichero entero, o el anterior."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def ready(settings: Settings) -> dict[str, Any] | None:
    """El instalador bajado y comprobado (`listo.json`), si sigue en disco y es más nuevo.

    Aquí solo se mira el tamaño (se lee en cada consulta del panel); el SHA-256 se vuelve a
    comprobar al pedir la instalación.
    """
    folder = update_dir(settings)
    record = _read_json(folder / READY_NAME)
    if record is None:
        return None
    try:
        path = _inside(folder, record.get("file"))
        version = str(record["version"])
        size = int(record["size"])
        sha = str(record["sha256"])
    except (UpdateError, KeyError, TypeError, ValueError):
        return None
    if parse_version(version) is None or _SHA.fullmatch(sha) is None:
        return None
    if is_newer(version, settings.app_version) is False:
        # Ya es la que corre (o una anterior): no hay nada que instalar y lo bajado sobra.
        clean(folder)
        return None
    try:
        if path.stat().st_size != size:
            return None
    except OSError:
        return None
    return {"version": version, "file": path.name, "sha256": sha, "size": size, "path": path}


def clean(folder: Path, keep: str | None = None) -> None:
    """Borra de `folder` los instaladores, los `.partial` y `listo.json`/`instalar.json` que no
    sean de `keep` (el nombre del instalador que se está bajando). Solo mira dentro de `folder`,
    sin bajar a subcarpetas, y solo ficheros normales."""
    if not folder.is_dir():
        return
    for path in folder.iterdir():
        if not path.is_file() or path.is_symlink():
            continue
        name = path.name
        if keep is not None and name in (keep, keep + ".partial"):
            continue
        if name.lower().endswith((".exe", ".exe.partial")):
            path.unlink(missing_ok=True)
        elif name in (READY_NAME, INSTALL_NAME):
            record = _read_json(path)
            if keep is None or record is None or record.get("file") != keep:
                path.unlink(missing_ok=True)


def install_request(settings: Settings) -> dict[str, Any] | None:
    return _read_json(update_dir(settings) / INSTALL_NAME)


class Updater:
    """Una comprobación o una descarga a la vez; el estado se lee con `snapshot`."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._manifest: dict[str, Any] | None = None
        self._job: dict[str, Any] = {"state": "idle", "phase": None, "done_bytes": 0,
                                     "total_bytes": 0}
        self._error: tuple[str, str] | None = None

    # --- lectura ---------------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"job": dict(self._job), "manifest": self._manifest, "error": self._error}

    def _set(self, **changes: Any) -> None:
        with self._lock:
            self._job.update(changes)

    def _fail(self, exc: UpdateError) -> None:
        with self._lock:
            self._error = (exc.code, exc.detail)

    def running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    # --- manifiesto ------------------------------------------------------------------------

    def _fetch_manifest(self, settings: Settings, client: httpx.Client) -> dict[str, Any]:
        try:
            response = client.get(f"{settings.update_url}/{MANIFEST_NAME}")
        except egress.EgressBlocked as exc:
            raise _blocked(settings, exc.reason) from exc
        except egress.EgressNotAllowed as exc:
            # Una redirección a un host fuera de la lista blanca: no sale, y se dice.
            raise UpdateError("blocked", str(exc)) from exc
        except httpx.HTTPError as exc:
            raise UpdateError("network", str(exc)) from exc
        if response.status_code == 404:
            raise UpdateError("not-published")
        if response.status_code != 200:
            raise UpdateError("network", f"HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise UpdateError("bad-manifest", "json") from exc
        manifest = check_manifest(data)
        with self._lock:
            self._manifest = manifest
        return manifest

    def check(self, settings: Settings) -> dict[str, Any]:
        """Baja y valida el manifiesto publicado. Lanza `UpdateError` (y lo deja en el estado)."""
        with self._lock:
            self._error = None
        try:
            with egress.client(settings, PURPOSE) as client:
                return self._fetch_manifest(settings, client)
        except UpdateError as exc:
            self._fail(exc)
            raise

    # --- descarga --------------------------------------------------------------------------

    def start(self, settings: Settings) -> None:
        """Empieza a bajar el instalador publicado, si es más nuevo. Lanza `UpdateError`."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise UpdateError("busy")
            known = self._manifest
            if known is not None and is_newer(known["version"], settings.app_version) is False:
                raise UpdateError("same-version", str(known["version"]))
            self._cancel.clear()
            self._error = None
            self._job = {"state": "running", "phase": "manifest", "done_bytes": 0,
                         "total_bytes": 0,
                         "started": datetime.now(UTC).isoformat(timespec="seconds")}
            self._thread = threading.Thread(
                target=self._run, args=(settings,), name="emma-app-update", daemon=True,
            )
            self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def wait(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _run(self, settings: Settings) -> None:
        try:
            self._download(settings)
        except Cancelled:
            self._set(state="cancelled", phase=None)
        except UpdateError as exc:
            self._fail(exc)
            self._set(state="error", phase=None)
        except OSError as exc:
            self._fail(UpdateError("disk", str(exc)))
            self._set(state="error", phase=None)
        except Exception as exc:  # el hilo nunca deja el estado en «running»
            self._fail(UpdateError("network", f"{type(exc).__name__}: {exc}"))
            self._set(state="error", phase=None)
        else:
            self._set(state="done", phase=None,
                      finished=datetime.now(UTC).isoformat(timespec="seconds"))

    def _add_done(self, amount: int) -> None:
        with self._lock:
            self._job["done_bytes"] = int(self._job.get("done_bytes", 0)) + amount

    def _download(self, settings: Settings) -> None:
        folder = update_dir(settings)
        folder.mkdir(parents=True, exist_ok=True)
        with egress.client(settings, PURPOSE) as client:
            manifest = self._fetch_manifest(settings, client)
            version = str(manifest["version"])
            # Nunca se baja una versión que no sea mayor que la que corre.
            if is_newer(version, settings.app_version) is False:
                raise UpdateError("same-version", version)
            target = _inside(folder, manifest["installer"])
            # Lo de otras versiones (instaladores, trozos, listo.json) sobra desde ya.
            clean(folder, keep=target.name)
            size, sha = int(manifest["size"]), str(manifest["sha256"])
            partial = target.with_name(target.name + ".partial")
            have = partial.stat().st_size if partial.exists() else 0
            if target.exists() and target.stat().st_size == size:
                have = size  # ya está entero: solo se vuelve a comprobar su huella
            free = shutil.disk_usage(folder).free
            if free < size - have + DISK_MARGIN:
                raise UpdateError("no-space", f"{size - have + DISK_MARGIN}/{free}")
            self._set(phase="download", total_bytes=size)
            if self._cancel.is_set():
                raise Cancelled
            try:
                fetch_verified(client, installer_url(settings, version, target.name), target,
                               size, sha, on_bytes=self._add_done, cancelled=self._cancel.is_set)
            except egress.EgressNotAllowed as exc:
                raise UpdateError("blocked", str(exc)) from exc
            except PackError as exc:
                if exc.code == "bad-part":
                    raise UpdateError("bad-hash", target.name) from exc
                if exc.code == "blocked":
                    raise _blocked(settings, exc.detail) from exc
                if exc.code == "not-published":
                    # Hay manifiesto, pero su versión no trae el instalador que nombra.
                    raise UpdateError("installer-missing", target.name) from exc
                raise UpdateError(exc.code, exc.detail) from exc
        _write_json(folder / READY_NAME, {"version": version, "file": target.name,
                                          "sha256": sha, "size": size})
        # Una petición de instalar de otra versión ya no vale; ni lo demás que quede.
        clean(folder, keep=target.name)

    # --- instalar --------------------------------------------------------------------------

    def request_install(self, settings: Settings) -> dict[str, Any]:
        """Escribe `instalar.json` para la aplicación de escritorio. Lanza `UpdateError`.

        Bajo el cerrojo: mientras se pide, no puede empezar una descarga que borre lo pedido.

        Con el modo seguro activo no se pide (decisión del usuario, 2026-11-16): cambiar de versión
        a mitad de una contingencia es justo lo que el modo seguro quiere evitar, aunque el
        instalador ya esté bajado y no haga falta red.
        """
        with self._lock:
            reason = egress.safe_mode_reason()
            if reason is not None:
                raise UpdateError("safe-mode", reason)
            if self._thread is not None and self._thread.is_alive():
                raise UpdateError("busy")
            done = ready(settings)
            if done is None:
                raise UpdateError("not-ready")
            # Se vuelve a comprobar la huella: entre la descarga y ahora el fichero pudo cambiar.
            if _sha256(Path(done["path"])) != done["sha256"]:
                (update_dir(settings) / READY_NAME).unlink(missing_ok=True)
                raise UpdateError("bad-hash", str(done["file"]))
            record = {"version": done["version"], "file": done["file"],
                      "sha256": done["sha256"],
                      "requested_at": datetime.now(UTC).isoformat(timespec="seconds")}
            _write_json(update_dir(settings) / INSTALL_NAME, record)
            return record


def installer_url(settings: Settings, version: str, name: str) -> str:
    """De dónde se baja el instalador: de la versión que dice el manifiesto, no de `latest`.

    `latest` se mueve: si se publica otra versión entre el manifiesto y la descarga (o entre
    cancelar y seguir), el instalador de la anterior ya no estaría ahí.
    """
    latest = "/releases/latest/download"
    base = settings.update_url.rstrip("/")
    if base.endswith(latest):
        base = f"{base[: -len(latest)]}/releases/download/v{version}"
    return f"{base}/{name}"


def _blocked(settings: Settings, reason: str) -> UpdateError:
    # Sin red es el modo nominal, no una avería: se dice con su propio código.
    # Sin red, el motivo de la puerta (en castellano) no añade nada al mensaje.
    return UpdateError("offline") if settings.offline else UpdateError("blocked", reason)


updater = Updater()
