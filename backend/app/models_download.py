"""«Descargar modelos»: el paquete de modelos bajado desde el propio EMMA, todo junto o por piezas.

Por qué existe: decisión del usuario (2026-11-15). El paquete de modelos (Ollama con sus modelos,
Whisper, TotalSegmentator, Tesseract) se instala aparte, desde disco o USB
(`packaging/models_pack.py`). Quien no tiene el USB tiene que poder bajarlo desde el programa.
`packaging/models_parts.py` lo publica en trozos; aquí se bajan, se comprueban y se instalan en la
misma carpeta que mira la aplicación de escritorio (`desktop/main.cjs: modelsDir`).

Lo que no se negocia:

* **Sale por la puerta** (`core/egress.py`, propósito `models-pack`): en modo sin red, con el
  modo seguro o con el freno de Polaris no se baja nada, y queda en su traza.
* **Dos comprobaciones**: cada trozo, con su tamaño y SHA-256 del índice, antes de usarlo; cada
  fichero, con los del `MANIFIESTO.json`, al sacarlo. Solo se escriben los ficheros que el
  manifiesto nombra para esa pieza: una ruta del `tar` que no esté ahí es un paquete alterado y
  la pieza no se instala.
* **Nada a medias**: la pieza se saca en una carpeta aparte y solo se cambia por la instalada
  cuando todos sus ficheros han casado. `instalado.json`, que es lo que activa el paquete, se
  escribe al final de cada pieza.
* **Se reanuda**: un trozo cortado se sigue por donde iba (`Range`); los trozos ya usados se
  borran según se sacan, para no ocupar el doble de disco.
* **Muchas conexiones a la vez**: GitHub limita cada conexión (medido el 2026-11-15: unos
  3 MB/s con una, 31 MB/s con 16). Se bajan `PARALLEL_PARTS` trozos por delante del que se saca,
  siempre en orden, y cada trozo en `SEGMENTS_PER_PART` tramos (`Range`) que se reanudan cada uno
  por su lado. Cuesta, como mucho, ese número de trozos en disco a la espera.

Lo que se instala se usa la próxima vez que se abre EMMA: la aplicación de escritorio arranca el
Ollama del paquete y pasa sus rutas al backend al arrancar.

No es una vía de datos de salud: no toca el ledger ni el almacén.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import threading
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

import httpx

from app.core import egress
from app.core.config import Settings

PURPOSE = "models-pack"
INDEX_NAME = "emma-modelos-partes.json"
MANIFEST_NAME = "MANIFIESTO.json"
INSTALLED_NAME = "instalado.json"
ROOT_FILES = ("LEEME.txt", "instalar.cmd", "instalar.ps1")
INDEX_VERSION = 1
CHUNK = 1 << 20
# Margen de disco sobre lo que ocupa la pieza instalada más un trozo en curso.
DISK_MARGIN = 512 * 1024 * 1024
# Trozos que se bajan a la vez, y tramos (`Range`) en que se parte cada uno: 4 × 4 = 16
# conexiones. Medido el 2026-11-15 contra GitHub: 3 MB/s con una conexión, 9 con 4, 24 con 8 y 31
# con 16 (ya casi la línea entera). Un trozo pequeño (menos de `SEGMENT_MIN`) va en un solo tramo.
PARALLEL_PARTS = 4
SEGMENTS_PER_PART = 4
SEGMENT_MIN = 64 * 1024 * 1024
# Timeout de lectura por trozo de red, no de la descarga entera (un trozo son casi 2 GB).
DOWNLOAD_TIMEOUT = httpx.Timeout(60.0, connect=30.0)


class PackError(RuntimeError):
    """Un fallo con su código, para que el texto se componga en el idioma de quien lo lee."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class Cancelled(Exception):
    pass


def models_dir(settings: Settings) -> Path:
    """La carpeta del paquete: la misma regla que `desktop/main.cjs: modelsDir`."""
    if settings.models_dir is not None:
        return Path(settings.models_dir)
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return base / "EMMA-modelos"


def _staging(dest: Path) -> Path:
    # Junto al destino: misma unidad, así que el cambio final es un renombrado.
    return dest.with_name(dest.name + ".descarga")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def installed(dest: Path) -> dict[str, str]:
    """Pieza instalada -> fecha del paquete del que salió.

    `instalar.ps1` (desde USB) instala el paquete entero y no dice piezas: entonces cuenta cada
    carpeta de pieza que esté presente, con la fecha del paquete.
    """
    record = _read_json(dest / INSTALLED_NAME)
    if record is None:
        return {}
    pieces = record.get("components")
    if isinstance(pieces, dict):
        return {str(k): str(v) for k, v in pieces.items() if (dest / str(k)).is_dir()}
    created = str(record.get("pack_created", ""))
    manifest = _read_json(dest / MANIFEST_NAME) or {}
    names = manifest.get("components", {})
    return {str(name): created for name in names if (dest / str(name)).is_dir()}


def _check_index(index: Any) -> dict[str, Any]:
    if not isinstance(index, dict) or index.get("emma_models_parts") != INDEX_VERSION:
        raise PackError("bad-index")
    try:
        manifest = index["manifest"]
        int(manifest["size"])
        str(manifest["sha256"])
        for name, piece in index["components"].items():
            if not name or "/" in name or "\\" in name or name.startswith("."):
                raise PackError("bad-index", name)
            for part in piece["parts"]:
                if "/" in part["name"] or "\\" in part["name"]:
                    raise PackError("bad-index", part["name"])
                int(part["size"])
                str(part["sha256"])
            int(piece["installed_size"])
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise PackError("bad-index") from exc
    return index


class Downloader:
    """Una descarga a la vez, en un hilo; el estado se lee con `snapshot`."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._catalog: dict[str, Any] | None = None
        self._state: dict[str, Any] = {"state": "idle"}

    # --- lectura ---------------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"job": dict(self._state), "catalog": self._catalog}

    def _set(self, **changes: Any) -> None:
        with self._lock:
            self._state.update(changes)

    # --- índice -----------------------------------------------------------------------------

    def _fetch_json(self, client: httpx.Client, url: str) -> Any:
        try:
            response = client.get(url)
        except egress.EgressBlocked as exc:
            raise PackError("blocked", exc.reason) from exc
        except httpx.HTTPError as exc:
            raise PackError("network", str(exc)) from exc
        if response.status_code == 404:
            raise PackError("not-published")
        if response.status_code != 200:
            raise PackError("network", f"HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise PackError("bad-index") from exc

    def check(self, settings: Settings) -> dict[str, Any]:
        """Baja el índice publicado y lo guarda como catálogo. Lanza `PackError`."""
        with egress.client(settings, PURPOSE) as client:
            index = _check_index(self._fetch_json(client, f"{settings.models_url}/{INDEX_NAME}"))
        with self._lock:
            self._catalog = index
        return index

    # --- descarga ---------------------------------------------------------------------------

    def start(self, settings: Settings, components: list[str] | None) -> None:
        """Empieza a bajar `components` (None: todas las que falten). Lanza `PackError`."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise PackError("busy")
            self._cancel.clear()
            self._state = {"state": "running", "phase": "index", "component": None,
                           "done_bytes": 0, "total_bytes": 0, "components": components,
                           "started": datetime.now(UTC).isoformat(timespec="seconds")}
            self._thread = threading.Thread(
                target=self._run, args=(settings, components), name="emma-models-download",
                daemon=True,
            )
            self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def wait(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _run(self, settings: Settings, components: list[str] | None) -> None:
        try:
            done = self._download(settings, components)
        except Cancelled:
            self._set(state="cancelled", phase=None)
        except PackError as exc:
            self._set(state="error", phase=None, error=exc.code, detail=exc.detail)
        except OSError as exc:
            self._set(state="error", phase=None, error="disk", detail=str(exc))
        else:
            self._set(state="done", phase=None, installed=done,
                      finished=datetime.now(UTC).isoformat(timespec="seconds"))

    def _download(self, settings: Settings, wanted: list[str] | None) -> list[str]:
        dest = models_dir(settings)
        if dest.exists() and any(dest.iterdir()) and not (dest / MANIFEST_NAME).exists():
            # Como `instalar.ps1`: nunca se escribe en una carpeta que no sea del paquete.
            raise PackError("foreign-dir", str(dest))
        staging = _staging(dest)
        parts_dir = staging / "partes"
        parts_dir.mkdir(parents=True, exist_ok=True)
        base = settings.models_url
        with egress.client(settings, PURPOSE) as client:
            index = _check_index(self._fetch_json(client, f"{base}/{INDEX_NAME}"))
            with self._lock:
                self._catalog = index
            names = list(index["components"])
            have = installed(dest)
            if wanted is None:
                todo = [n for n in names if have.get(n) != index["pack_created"]]
            else:
                unknown = [n for n in wanted if n not in index["components"]]
                if unknown:
                    raise PackError("unknown-component", ", ".join(unknown))
                todo = [n for n in names if n in wanted]
            total = sum(int(p["size"]) for n in todo for p in index["components"][n]["parts"])
            self._set(total_bytes=total, todo=todo)

            # El manifiesto, comprobado contra el índice: de él salen las huellas de cada fichero.
            manifest_path = staging / MANIFEST_NAME
            self._fetch_file(client, f"{base}/{MANIFEST_NAME}", manifest_path,
                             int(index["manifest"]["size"]), str(index["manifest"]["sha256"]),
                             count=False)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            files: dict[str, Any] = manifest["files"]
            roots = {}
            for name in ROOT_FILES:
                if name in files:
                    size, sha = int(files[name][0]), str(files[name][1])
                    self._fetch_file(client, f"{base}/{name}", staging / name, size, sha,
                                     count=False)
                    roots[name] = staging / name

            done: list[str] = []
            for name in todo:
                self._component(client, base, staging, parts_dir, dest, name,
                                index["components"][name], files)
                self._activate(dest, manifest_path, roots, index, name)
                done.append(name)
        shutil.rmtree(staging, ignore_errors=True)
        return done

    def _check_disk(self, where: Path, piece: dict[str, Any]) -> None:
        biggest = max((int(p["size"]) for p in piece["parts"]), default=0)
        need = int(piece["installed_size"]) + PARALLEL_PARTS * biggest + DISK_MARGIN
        free = shutil.disk_usage(where).free
        if free < need:
            raise PackError("no-space", f"{need}/{free}")

    def _component(self, client: httpx.Client, base: str, staging: Path, parts_dir: Path,
                   dest: Path, name: str, piece: dict[str, Any], files: dict[str, Any]) -> None:
        self._check_disk(staging, piece)
        expected = {rel: (int(v[0]), str(v[1])) for rel, v in files.items()
                    if rel.startswith(name + "/")}
        target = staging / name
        if target.exists():
            shutil.rmtree(target)
        self._set(component=name, phase="download")

        def fetch(part: dict[str, Any]) -> Path:
            path: Path = parts_dir / part["name"]
            url, size, sha = f"{base}/{part['name']}", int(part["size"]), str(part["sha256"])
            if size >= SEGMENT_MIN and SEGMENTS_PER_PART > 1:
                self._fetch_segmented(client, url, path, size, sha)
            else:
                self._fetch_file(client, url, path, size, sha)
            return path

        pool = ThreadPoolExecutor(max_workers=PARALLEL_PARTS, thread_name_prefix="emma-part")

        def parts() -> Iterator[Path]:
            # Como mucho PARALLEL_PARTS trozos pedidos por delante del que se está sacando.
            queue: list[Future[Path]] = []
            pending = iter(piece["parts"])
            for part in pending:
                queue.append(pool.submit(fetch, part))
                if len(queue) >= PARALLEL_PARTS:
                    break
            while queue:
                path = queue.pop(0).result()
                following = next(pending, None)
                if following is not None:
                    queue.append(pool.submit(fetch, following))
                yield path

        seen: set[str] = set()
        try:
            self._extract(parts(), target, expected, seen)
        except BaseException:
            # Un fallo o una cancelación: los trozos en vuelo se paran (quedan a medias para
            # reanudar) y no se espera a que acaben.
            self._cancel.set()
            raise
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        missing = set(expected) - seen
        if missing:
            raise PackError("bad-archive", sorted(missing)[0])
        self._install(staging, dest, name, target)

    def _extract(self, parts: Iterator[Path], target: Path,
                 expected: dict[str, tuple[int, str]], seen: set[str]) -> None:
        with _Chain(parts) as stream, tarfile.open(fileobj=stream, mode="r|") as tar:  # type: ignore[call-overload]
            for member in tar:
                self._raise_if_cancelled()
                rel = member.name
                if not member.isfile() or rel not in expected or rel in seen:
                    raise PackError("bad-archive", rel)
                size, sha = expected[rel]
                if member.size != size:
                    raise PackError("bad-file", rel)
                source = tar.extractfile(member)
                if source is None:
                    raise PackError("bad-archive", rel)
                out = target.joinpath(*rel.split("/")[1:])
                out.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with out.open("wb") as handle:
                    while chunk := source.read(CHUNK):
                        digest.update(chunk)
                        handle.write(chunk)
                if digest.hexdigest() != sha:
                    raise PackError("bad-file", rel)
                seen.add(rel)

    def _install(self, staging: Path, dest: Path, name: str, target: Path) -> None:
        self._set(phase="install")
        dest.mkdir(parents=True, exist_ok=True)
        current = dest / name
        if current.exists():
            old = staging / (name + ".anterior")
            if old.exists():
                shutil.rmtree(old)
            try:
                current.rename(old)
            except OSError as exc:
                # En Windows, una pieza en uso (el Ollama que arrancó la aplicación) no se mueve.
                raise PackError("in-use", name) from exc
            target.rename(current)
            shutil.rmtree(old, ignore_errors=True)
        else:
            target.rename(current)

    def _activate(self, dest: Path, manifest: Path, roots: dict[str, Path],
                  index: dict[str, Any], name: str) -> None:
        shutil.copyfile(manifest, dest / MANIFEST_NAME)
        for file_name, path in roots.items():
            shutil.copyfile(path, dest / file_name)
        pieces = installed(dest)
        pieces[name] = str(index["pack_created"])
        record = {
            "installed": datetime.now(UTC).isoformat(timespec="seconds"),
            "pack_created": index["pack_created"],
            "components": pieces,
            "via": "descarga",
        }
        tmp = dest / (INSTALLED_NAME + ".tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, dest / INSTALLED_NAME)

    def _raise_if_cancelled(self) -> None:
        if self._cancel.is_set():
            raise Cancelled

    def _add_done(self, amount: int) -> None:
        with self._lock:
            self._state["done_bytes"] = int(self._state.get("done_bytes", 0)) + amount

    def _fetch_segmented(self, client: httpx.Client, url: str, path: Path, size: int,
                         sha: str) -> None:
        """Un trozo en `SEGMENTS_PER_PART` tramos a la vez; se juntan y se comprueba el trozo."""
        if path.exists() and path.stat().st_size == size and _sha256(path) == sha:
            self._add_done(size)
            return
        step = -(-size // SEGMENTS_PER_PART)
        ranges = [(start, min(start + step, size)) for start in range(0, size, step)]
        pieces = [path.with_name(f"{path.name}.tramo{i}") for i in range(len(ranges))]
        for attempt in range(2):
            with ThreadPoolExecutor(max_workers=len(ranges),
                                    thread_name_prefix="emma-tramo") as pool:
                futures = [pool.submit(self._fetch_range, client, url, piece, start, end)
                           for piece, (start, end) in zip(pieces, ranges, strict=True)]
                errors: list[BaseException | None] = []
                for future in futures:
                    error = future.exception()
                    if error is not None and not self._cancel.is_set():
                        # Un tramo caído para los demás: no se sigue bajando para nada.
                        self._cancel.set()
                    errors.append(error)
            failed = next((error for error in errors if error is not None), None)
            if failed is not None:
                raise failed
            joined = path.with_name(path.name + ".partial")
            digest = hashlib.sha256()
            with joined.open("wb") as out:
                for piece in pieces:
                    with piece.open("rb") as handle:
                        while chunk := handle.read(CHUNK):
                            digest.update(chunk)
                            out.write(chunk)
            for piece in pieces:
                piece.unlink(missing_ok=True)
            if joined.stat().st_size == size and digest.hexdigest() == sha:
                os.replace(joined, path)
                return
            # Dañado o de otra versión: fuera, y una vez más desde cero.
            joined.unlink(missing_ok=True)
            self._add_done(-size)
            if attempt == 1:
                break
        raise PackError("bad-part", path.name)

    def _fetch_range(self, client: httpx.Client, url: str, piece: Path, start: int,
                     end: int) -> None:
        """Los bytes `[start, end)` de `url` en `piece`, siguiendo por lo que ya tenga."""
        length = end - start
        have = piece.stat().st_size if piece.exists() else 0
        if have > length:
            piece.unlink()
            have = 0
        self._add_done(have)
        if have == length:
            return
        try:
            with client.stream("GET", url, headers={"Range": f"bytes={start + have}-{end - 1}"},
                               timeout=DOWNLOAD_TIMEOUT) as response:
                if response.status_code == 404:
                    raise PackError("not-published", piece.name)
                if response.status_code != 206:
                    # Sin `Range` no se puede partir: un tramo no puede recibir el trozo entero.
                    raise PackError("network", f"HTTP {response.status_code} sin Range")
                with piece.open("ab") as handle:
                    for chunk in response.iter_bytes(CHUNK):
                        self._raise_if_cancelled()
                        take = chunk[: length - have]
                        handle.write(take)
                        have += len(take)
                        self._add_done(len(take))
                        if have >= length:
                            break
        except egress.EgressBlocked as exc:
            raise PackError("blocked", exc.reason) from exc
        except httpx.HTTPError as exc:
            raise PackError("network", str(exc)) from exc
        if have != length:
            raise PackError("network", f"{piece.name}: {have}/{length}")

    def _fetch_file(self, client: httpx.Client, url: str, path: Path, size: int, sha: str,
                    *, count: bool = True) -> None:
        """Deja en `path` el fichero comprobado, siguiendo un `.partial` si lo hay."""
        if path.exists() and path.stat().st_size == size and _sha256(path) == sha:
            if count:
                self._add_done(size)
            return
        partial = path.with_name(path.name + ".partial")
        have = partial.stat().st_size if partial.exists() else 0
        if have > size:
            partial.unlink()
            have = 0
        if count:
            self._add_done(have)
        for attempt in range(2):
            if have < size:
                headers = {"Range": f"bytes={have}-"} if have else {}
                try:
                    with client.stream("GET", url, headers=headers,
                                       timeout=DOWNLOAD_TIMEOUT) as response:
                        if response.status_code == 404:
                            raise PackError("not-published", path.name)
                        if have and response.status_code == 200:
                            # El servidor no reanuda: se empieza de cero.
                            if count:
                                self._add_done(-have)
                            have = 0
                        elif response.status_code not in (200, 206):
                            raise PackError("network", f"HTTP {response.status_code}")
                        with partial.open("ab" if have else "wb") as handle:
                            for chunk in response.iter_bytes(CHUNK):
                                self._raise_if_cancelled()
                                handle.write(chunk)
                                have += len(chunk)
                                if count:
                                    self._add_done(len(chunk))
                                if have > size:
                                    break
                except egress.EgressBlocked as exc:
                    raise PackError("blocked", exc.reason) from exc
                except httpx.HTTPError as exc:
                    raise PackError("network", str(exc)) from exc
            if have == size and _sha256(partial) == sha:
                os.replace(partial, path)
                return
            # Trozo dañado o de otra versión: se borra y se intenta una vez más desde cero.
            partial.unlink(missing_ok=True)
            if count:
                self._add_done(-have)
            have = 0
            if attempt == 1:
                break
        raise PackError("bad-part", path.name)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


class _Chain:
    """Los trozos, leídos seguidos como un solo fichero; cada uno se borra al acabarlo."""

    def __init__(self, parts: Iterator[Path]) -> None:
        self._parts = parts
        self._path: Path | None = None
        self._handle: IO[bytes] | None = None

    def __enter__(self) -> _Chain:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _next(self) -> bool:
        self._finish()
        try:
            self._path = next(self._parts)
        except StopIteration:
            return False
        self._handle = self._path.open("rb")
        return True

    def _finish(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
            assert self._path is not None
            self._path.unlink(missing_ok=True)
            self._path = None

    def read(self, size: int = -1) -> bytes:
        out = bytearray()
        while size < 0 or len(out) < size:
            if self._handle is None and not self._next():
                break
            assert self._handle is not None
            chunk = self._handle.read(-1 if size < 0 else size - len(out))
            if not chunk:
                self._finish()
                continue
            out += chunk
        return bytes(out)

    def close(self) -> None:
        # Si se cierra a medias (error o cancelación), el trozo abierto se deja para reanudar.
        if self._handle is not None:
            self._handle.close()
            self._handle = None


downloader = Downloader()
