"""Bajar los trozos del paquete de modelos tan rápido como dé la línea, midiendo.

Por qué existe: GitHub limita cada conexión (medido el 2026-11-15: unos 3 MB/s con una, 27 con 16
y 41 con 32), y lo que da una línea no se sabe de antemano. Un número fijo de conexiones o se
queda corto (la 0.1.1 bajaba la voz a 6 MB/s con 4) o satura una línea lenta. Aquí el número se
ajusta midiendo: empieza con `START_CONNECTIONS` y, mientras abrir más hace subir la velocidad más
de un `GAIN`, abre más; cuando ya no sube, vuelve al número que dio lo mejor y se queda, y cada
`PROBE_EVERY` segundos prueba con alguna más por si la línea se ha liberado. Nunca pasa de
`MAX_CONNECTIONS`.

Cada trozo se reparte en bloques de `BLOCK` bytes que se piden con `Range` y se escriben en su
sitio de un fichero `.partial` del tamaño del trozo. Lo hecho se anota bloque a bloque en
`<trozo>.bloques.json`: una descarga cortada sigue por los bloques que faltan. Con todos los
bloques, el trozo se comprueba entero con su SHA-256 antes de entregarlo; si no casa, se vuelve a
bajar una vez desde cero. Los trozos se entregan en orden y solo `window` por delante del que se
está sacando ocupan disco.

Toda petición sale por el cliente de la puerta (`core/egress.py`) que recibe: aquí no se crea
ningún cliente HTTP.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
from collections import deque
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.core import egress

BLOCK = 32 * 1024 * 1024
START_CONNECTIONS = 8
MAX_CONNECTIONS = 64
# Cada cuánto se mide, cuánto tiene que subir la velocidad para seguir abriendo y cada cuánto se
# vuelve a probar con más tras pararse.
MEASURE_EVERY = 4.0
GAIN = 1.10
PROBE_EVERY = 30.0
# Un bloque que falla tantas veces seguidas para la descarga (la red no vuelve).
BLOCK_TRIES = 4
READ = 1 << 20
TIMEOUT = httpx.Timeout(60.0, connect=30.0)


class FetchError(RuntimeError):
    """Un fallo con su código (los de `models_download.PackError`)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class FetchCancelled(Exception):
    pass


@dataclass
class _Part:
    name: str
    size: int
    sha: str
    url: str
    final: Path
    partial: Path
    record: Path
    blocks: list[tuple[int, int]]
    done: set[int] = field(default_factory=set)
    pending: deque[int] = field(default_factory=deque)
    failures: dict[int, int] = field(default_factory=dict)
    retried: bool = False
    active: bool = False
    ready: threading.Event = field(default_factory=threading.Event)


class Controller:
    """Cuántas conexiones abrir según lo que se mide. Puro: el reloj y la medida vienen de fuera."""

    def __init__(self, start: int = START_CONNECTIONS, top: int = MAX_CONNECTIONS) -> None:
        self.target = start
        self.top = top
        self.best_rate = 0.0
        self.best_target = start
        self.holding_since: float | None = None

    def update(self, rate: float, now: float) -> int:
        if self.holding_since is not None:
            if now - self.holding_since < PROBE_EVERY:
                return self.target
            # Se vuelve a probar: lo de ahora es la referencia, y se abre algo más.
            self.holding_since = None
            self.best_rate = rate
            self.best_target = self.target
            self.target = min(self.top, math.ceil(self.target * 1.25))
            return self.target
        if rate >= self.best_rate * GAIN:
            self.best_rate = rate
            self.best_target = self.target
            if self.target < self.top:
                self.target = min(self.top, math.ceil(self.target * 1.5))
            else:
                self.holding_since = now
        else:
            # Abrir más ya no ayudó: al número que dio lo mejor, y a esperar.
            self.target = self.best_target
            self.holding_since = now
        return self.target


class BlockFetcher:
    def __init__(
        self,
        client: httpx.Client,
        base: str,
        folder: Path,
        parts: list[dict[str, Any]],
        *,
        window: int,
        on_bytes: Callable[[int], None],
        cancelled: Callable[[], bool],
        on_connections: Callable[[int, float], None] = lambda _n, _rate: None,
        block: int | None = None,
        start: int = START_CONNECTIONS,
        top: int = MAX_CONNECTIONS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        block = BLOCK if block is None else block
        self._window = max(1, window)
        self._on_bytes = on_bytes
        self._cancelled = cancelled
        self._on_connections = on_connections
        self._clock = clock
        self._controller = Controller(start, top)
        self._cond = threading.Condition()
        self._running = 0
        self._stop = False
        self._fatal: FetchError | None = None
        self._consumed = 0
        self._bytes = 0
        self._top = top
        self._parts: list[_Part] = []
        for item in parts:
            size = int(item["size"])
            name = str(item["name"])
            final = folder / name
            self._parts.append(_Part(
                name=name, size=size, sha=str(item["sha256"]), url=f"{base}/{name}",
                final=final, partial=folder / (name + ".partial"),
                record=folder / (name + ".bloques.json"),
                blocks=[(s, min(s + block, size)) for s in range(0, size, block)] or [(0, 0)],
            ))

    # --- lo que ve quien saca los trozos ----------------------------------------------------

    def parts(self) -> Generator[Path, None, None]:
        """Los trozos comprobados, en orden. Al cerrarse (o fallar), para todo."""
        workers = [threading.Thread(target=self._work, name=f"emma-bloque-{i}", daemon=True)
                   for i in range(self._top)]
        watcher = threading.Thread(target=self._watch, name="emma-medida", daemon=True)
        try:
            with self._cond:
                self._activate()
            for worker in workers:
                worker.start()
            watcher.start()
            for index, part in enumerate(self._parts):
                while not part.ready.wait(0.25):
                    self._check()
                self._check()
                yield part.final
                with self._cond:
                    self._consumed = index + 1
                    self._activate()
                    self._cond.notify_all()
        finally:
            with self._cond:
                self._stop = True
                self._cond.notify_all()
            for worker in workers:
                if worker.is_alive():
                    worker.join()
            if watcher.is_alive():
                watcher.join()

    def _check(self) -> None:
        if self._cancelled():
            raise FetchCancelled
        if self._fatal is not None:
            raise self._fatal

    # --- organización -------------------------------------------------------------------

    def _activate(self) -> None:
        """Con el cerrojo: los trozos dentro de la ventana, listos para pedir sus bloques."""
        for part in self._parts[self._consumed:self._consumed + self._window]:
            if part.active:
                continue
            part.active = True
            if part.final.exists() and part.final.stat().st_size == part.size \
                    and _sha256(part.final) == part.sha:
                self._on_bytes(part.size)
                part.ready.set()
                continue
            part.done = self._resume(part)
            self._on_bytes(sum(part.blocks[i][1] - part.blocks[i][0] for i in part.done))
            part.pending = deque(i for i in range(len(part.blocks)) if i not in part.done)
            if not part.pending:
                self._finish_later(part)

    def _resume(self, part: _Part) -> set[int]:
        """Los bloques ya hechos de una vez anterior; si no casa nada, se empieza de cero."""
        for leftover in part.final.parent.glob(part.name + ".tramo*"):
            leftover.unlink(missing_ok=True)  # restos de la 0.1.1-0.1.2
        try:
            record = json.loads(part.record.read_text(encoding="utf-8"))
            done = {int(i) for i in record["done"]}
            ok = (record["size"] == part.size and record["sha256"] == part.sha
                  and record["block"] == part.blocks[0][1] - part.blocks[0][0]
                  and part.partial.stat().st_size == part.size
                  and all(0 <= i < len(part.blocks) for i in done))
        except (OSError, ValueError, KeyError, TypeError):
            ok, done = False, set()
        if ok:
            return done
        with part.partial.open("wb") as handle:
            handle.truncate(part.size)
        self._save(part, set())
        return set()

    def _save(self, part: _Part, done: set[int]) -> None:
        record = {"size": part.size, "sha256": part.sha,
                  "block": part.blocks[0][1] - part.blocks[0][0], "done": sorted(done)}
        tmp = part.record.with_name(part.record.name + ".tmp")
        tmp.write_text(json.dumps(record), encoding="utf-8")
        os.replace(tmp, part.record)

    def _next_block(self) -> tuple[_Part, int] | None:
        for part in self._parts[self._consumed:self._consumed + self._window]:
            if part.active and part.pending:
                return part, part.pending.popleft()
        return None

    # --- los que bajan ------------------------------------------------------------------

    def _work(self) -> None:
        while True:
            with self._cond:
                while True:
                    if self._stop or self._fatal is not None:
                        return
                    if self._running < self._controller.target:
                        job = self._next_block()
                        if job is not None:
                            break
                    self._cond.wait(0.5)
                self._running += 1
            part, index = job
            try:
                self._fetch_block(part, index)
            except FetchCancelled:
                with self._cond:
                    part.pending.appendleft(index)
                    self._running -= 1
                    self._cond.notify_all()
                return
            except Exception as exc:  # noqa: BLE001 — un hilo muerto en silencio colgaría todo
                failure = exc if isinstance(exc, FetchError) else FetchError("network", repr(exc))
                with self._cond:
                    self._running -= 1
                    tries = part.failures.get(index, 0) + 1
                    part.failures[index] = tries
                    if failure.code in {"blocked", "not-published", "no-range"} \
                            or tries >= BLOCK_TRIES:
                        self._fatal = self._fatal or failure
                    else:
                        part.pending.append(index)
                    self._cond.notify_all()
                continue
            with self._cond:
                self._running -= 1
                part.done.add(index)
                part.failures.pop(index, None)
                self._save(part, part.done)
                complete = len(part.done) == len(part.blocks)
                self._cond.notify_all()
            if complete:
                try:
                    self._verify(part)
                except OSError as exc:
                    with self._cond:
                        self._fatal = self._fatal or FetchError("disk", str(exc))
                        self._cond.notify_all()

    def _fetch_block(self, part: _Part, index: int) -> None:
        start, end = part.blocks[index]
        length = end - start
        if length == 0:
            return
        got = 0
        try:
            with self._client.stream("GET", part.url,
                                     headers={"Range": f"bytes={start}-{end - 1}"},
                                     timeout=TIMEOUT) as response:
                if response.status_code == 404:
                    raise FetchError("not-published", part.name)
                whole = response.status_code == 200 and start == 0 and end == part.size
                if response.status_code != 206 and not whole:
                    if response.status_code == 200:
                        raise FetchError("no-range", part.name)
                    raise FetchError("network", f"HTTP {response.status_code}")
                with part.partial.open("r+b") as handle:
                    handle.seek(start)
                    for chunk in response.iter_bytes(READ):
                        if self._cancelled() or self._stop:
                            raise FetchCancelled
                        take = chunk[: length - got]
                        handle.write(take)
                        got += len(take)
                        self._count(len(take))
                        if got >= length:
                            break
        except egress.EgressBlocked as exc:
            self._count(-got)
            raise FetchError("blocked", exc.reason) from exc
        except httpx.HTTPError as exc:
            self._count(-got)
            raise FetchError("network", str(exc)) from exc
        except (FetchError, FetchCancelled):
            self._count(-got)
            raise
        if got != length:
            self._count(-got)
            raise FetchError("network", f"{part.name}: bloque {index} incompleto")

    def _count(self, amount: int) -> None:
        with self._cond:
            self._bytes += amount
        self._on_bytes(amount)

    def _finish_later(self, part: _Part) -> None:
        threading.Thread(target=self._verify, args=(part,), daemon=True).start()

    def _verify(self, part: _Part) -> None:
        if _sha256(part.partial) == part.sha:
            os.replace(part.partial, part.final)
            part.record.unlink(missing_ok=True)
            part.ready.set()
            return
        with self._cond:
            if part.retried:
                self._fatal = self._fatal or FetchError("bad-part", part.name)
            else:
                # Dañado o de otra versión: una vez más desde cero.
                part.retried = True
                self._on_bytes(-part.size)
                part.done = set()
                self._save(part, set())
                part.pending = deque(range(len(part.blocks)))
            self._cond.notify_all()

    # --- la medida ----------------------------------------------------------------------

    def _watch(self) -> None:
        last_time = self._clock()
        with self._cond:
            last_bytes = self._bytes
        self._on_connections(self._controller.target, 0.0)
        while True:
            with self._cond:
                self._cond.wait(MEASURE_EVERY)
                if self._stop or self._fatal is not None:
                    return
                now = self._clock()
                if now - last_time < MEASURE_EVERY * 0.9:
                    continue
                rate = (self._bytes - last_bytes) / (now - last_time)
                last_time, last_bytes = now, self._bytes
                # Sin bloques que pedir (final de una pieza), la medida no dice nada de la línea.
                if self._next_block_waiting():
                    self._controller.update(rate, now)
                target = self._controller.target
                self._cond.notify_all()
            self._on_connections(target, rate)

    def _next_block_waiting(self) -> bool:
        return any(part.active and part.pending
                   for part in self._parts[self._consumed:self._consumed + self._window])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(READ):
            digest.update(chunk)
    return digest.hexdigest()
