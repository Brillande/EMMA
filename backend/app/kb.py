# SPDX-License-Identifier: AGPL-3.0-or-later
"""Buscar en la documentación de EMMA con `kb` de Polaris tal cual (SQLite FTS5, sin red).

Por qué existe: lo que justifica cada decisión de EMMA está escrito —gestión de riesgos,
integridad del registro, interfaz, especificación del equipo, decisiones sobre Polaris—, pero
repartido en decenas de ficheros. A bordo, con Tierra a minutos de luz, "¿por qué hace esto el
sistema?" se tiene que poder contestar con la cita exacta, sin internet.

`kb.build()` indexa lo que haya bajo `BTP_REPO/00_FUENTE-DE-VERDAD` y `kb.retrieve()` devuelve
pasajes con su fichero y su sección. El adaptador apunta `BTP_REPO` al estado de EMMA; aquí se
copia en esa carpeta la documentación de EMMA (`compliance/`, `docs/`, el README). Copias, no
enlaces: Windows no los crea sin privilegio. Se reindexa solo si algo cambió.

Capa vectorial (`kb_embed`, decisión del usuario 2026-10-04): el modelo e5-small en ONNX
(`scripts/install_kb_embed.py`, SHA-256 comprobado) vive en `app/data/kb-model/` y viaja en el
instalador. `kb_embed` lo busca junto a su propio fichero; aquí se le apuntan sus rutas
(`MODEL_DIR`, `MODEL_FILE`, `TOKENIZER_FILE`), que lee al cargar: la copia no se toca. Sin el
modelo, cae solo a BM25, sin red. Si la capa aparece o desaparece, el índice se rehace.
Su muro de sensibilidad (lo `_privado_` no sale en el ámbito `internal`) se queda como está.

Licencia y origen (AGPL §5a): usa `polaris/tools/kb.py` y `polaris/tools/kb_embed.py` de la copia
literal de Polaris, sin modificarla (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la
autora de Polaris, «Beyond the Protocol»); `kb` se carga con `app.polaris.load` y trae a
`kb_embed`. De EMMA: la documentación que se indexa y las rutas del modelo que se le apuntan.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import sys
import threading
import time
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Any

from app import polaris
from app.polaris import console

# Protege las rutas que se le apuntan a `kb` (`_point_at`). Se toma ANTES que el de consola
# (`app/polaris/console.py`), nunca al revés; el de entre procesos (`_across_processes`), entre
# los dos.
_LOCK = threading.Lock()
CORPUS = "00_FUENTE-DE-VERDAD"
MAX_PASSAGE = 700

MODEL = Path(__file__).resolve().parent / "data" / "kb-model"
# El repositorio en desarrollo; en el escritorio congelado, la copia que lleva el paquete.
_HERE = Path(__file__).resolve()
_DOC_ROOTS = (_HERE.parents[2], Path(getattr(sys, "_MEIPASS", _HERE.parents[1])) / "emma-docs")


@cache
def _tool() -> Any:
    return polaris.load("kb")


def docs_root() -> Path | None:
    for candidate in _DOC_ROOTS:
        if (candidate / "compliance").is_dir():
            return candidate
    return None


def sources(root: Path) -> list[Path]:
    """Lo que se indexa: documentación del proyecto, no código ni datos."""
    found = [root / "README.md"] if (root / "README.md").is_file() else []
    for folder in ("compliance", "docs"):
        found += sorted((root / folder).rglob("*.md"))
    return found


VECTORS, WORDS = ":vectores", ":bm25"
# Con el modelo, pero los vectores no se pudieron calcular: el índice es solo de palabras.
VECTORS_FAILED = ":vectores-fallidos"
STAMP = ".emma-fingerprint"
# Cerrojo entre procesos del corpus: no es el de `kb` (`.kb_index.db.lock`), que `build()` toma
# sin esperar y que, si ya lo tiene otro, da por bueno el índice ajeno («se sale en verde»).
REFRESH_LOCK = ".emma-refresh.lock"
# Cuánto espera, EN TOTAL, una actualización del índice: al cerrojo de hilos (otra búsqueda de este
# proceso que reindexa) y al de entre procesos (otro proceso con el corpus). Sin tope (§5.37.11,
# «Queda») una búsqueda podía quedarse colgada para siempre detrás de un proceso atascado, y con
# ella las demás búsquedas del mismo proceso, en cola en el cerrojo de hilos. Es un valor de
# diseño, no medido: holgado frente a una reindexación entera con vectores en una máquina cargada,
# y finito. Pasado, `RefreshBusyError`, que la API da como 503.
REFRESH_WAIT_S = 300.0
_POLL_S = 0.05


class RefreshBusyError(RuntimeError):
    """El índice lo tiene otro (proceso o búsqueda) más de lo que se le espera (`REFRESH_WAIT_S`).

    No es un `OSError` (ni un `TimeoutError`, que lo es): quien trate un fallo de disco como «no
    disponible» no debe tragarse «ocupado»."""


def _fingerprint(contents: list[tuple[str, bytes]]) -> str:
    """La huella de lo que se copia, fichero a fichero (ruta relativa y bytes)."""
    digest = hashlib.sha256()
    for relative, data in contents:
        digest.update(relative.encode())
        digest.update(data)
    return digest.hexdigest()


def _signature(path: Path) -> tuple[int, int] | None:
    """Con qué fichero está el índice ahora: cambia cuando `build()` lo sustituye."""
    try:
        found = path.stat()
    except FileNotFoundError:
        return None
    return found.st_ino, found.st_mtime_ns


def _try_lock(handle: Any) -> bool:
    """Toma el cerrojo del fichero sin esperar; False si lo tiene otro proceso."""
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(handle: Any) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def _across_processes(path: Path, deadline: float) -> Iterator[None]:
    """Exclusivo entre procesos que comparten el estado (`data/cache/polaris`), esperando hasta
    `deadline` (`time.monotonic`); pasado, `RefreshBusyError` sin haber tocado nada.

    El cerrojo de hilos (`_LOCK`) no ve a otro proceso: dos suites a la vez, o el servidor y una
    prueba, borraban y copiaban el mismo corpus mientras el otro lo indexaba. Lo suelta el
    sistema si el proceso muere. En Unix también se pide sin bloquear (`LOCK_NB`): con `flock` a
    secas la espera no tendría tope.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        while not _try_lock(handle):
            if time.monotonic() >= deadline:
                # Sin la ruta entera: va al 503 de la API, y la carpeta dice el usuario del equipo.
                raise RefreshBusyError(
                    f"otro proceso tiene el índice de la documentación (cerrojo {path.name}) y no "
                    f"lo ha soltado en {REFRESH_WAIT_S:g} s; se reintenta en la próxima búsqueda"
                )
            time.sleep(_POLL_S)
        try:
            yield
        finally:
            _unlock(handle)


def _write_atomically(path: Path, text: str) -> None:
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text)
    os.replace(temporary, path)


def refresh() -> dict[str, Any]:
    """Copia la documentación al corpus de `kb` y reindexa si cambió. Idempotente."""
    root = docs_root()
    if root is None:
        return {"available": False, "note": "la documentación no viaja en esta instalación"}
    return _refresh(root, polaris.configure())


def _refresh(root: Path, state: Path) -> dict[str, Any]:
    """`refresh` con sus dos carpetas explícitas (las pruebas usan unas temporales).

    La huella escrita tiene que describir el índice que hay, no lo que se quería indexar; en el
    cierre de §5.36.10 quedó escrita con un índice que no casaba con ella (§5.37.11). Por eso:

    * Cada documento se lee UNA vez, y con esos bytes se calcula la huella y se escribe la copia.
      Antes la huella se tomaba al principio y la copia leía otra vez el fichero: un documento
      editado entre medias (aquí lo editan varias sesiones a la vez) dejaba la huella del texto
      viejo sobre el índice del nuevo, y si el texto volvía al viejo, ya no se reindexaba nunca.
    * La huella se borra antes de tocar el corpus y se escribe, de golpe, solo si `build()`
      sustituyó de verdad el índice. `build()` de Polaris devuelve 0 también cuando no hace nada
      porque otro proceso tiene su cerrojo: antes se firmaba la huella sobre un índice ajeno.
    * «Con vectores» se escribe solo si este `build()` dejó el fichero de vectores. Si calcularlos
      falla (por memoria, por ejemplo), Polaris lo dice, lo borra y deja el índice solo con
      palabras: la huella decía «vectores» y la búsqueda ordenaba por palabras para siempre. Ahora
      dice «vectores fallidos» y vale como está hasta que cambie un documento: volver a
      intentarlo en cada búsqueda rehacería el índice entero en cada consulta. La búsqueda no se
      dice semántica sin vectores en el índice (`_indexed_vectors`).
    * Rehacer va bajo un cerrojo entre procesos (`_across_processes`). Si está al día se mira
      primero sin él (una búsqueda no espera a otra de otro proceso) y otra vez dentro de él,
      antes de tocar nada. La espera a los dos cerrojos, de hilos y de procesos, tiene un solo
      tope (`REFRESH_WAIT_S`, contado desde que se pide): pasado, `RefreshBusyError`, sin haber
      tocado el corpus. Así cada búsqueda en cola espera como mucho eso, no eso por cada una que
      tenga delante.
    """
    files = sources(root)
    corpus = state / CORPUS
    stamp = corpus / STAMP
    tool = _tool()
    deadline = time.monotonic() + REFRESH_WAIT_S
    if not _LOCK.acquire(timeout=REFRESH_WAIT_S):
        raise RefreshBusyError(
            "otra búsqueda de este proceso está actualizando el índice de la documentación y no "
            f"ha terminado en {REFRESH_WAIT_S:g} s; se reintenta en la próxima búsqueda"
        )
    try:
        _point_at(tool, state)
        if _current(root, files, stamp, tool):
            return {"available": True, "documents": len(files), "rebuilt": False}
        with _across_processes(state / REFRESH_LOCK, deadline):
            if _current(root, files, stamp, tool):
                return {"available": True, "documents": len(files), "rebuilt": False}
            return _rebuild(root, files, corpus, stamp, tool)
    finally:
        _LOCK.release()


def _read(root: Path, files: list[Path]) -> list[tuple[str, bytes]]:
    return [(str(path.relative_to(root)), path.read_bytes()) for path in files]


def _current(root: Path, files: list[Path], stamp: Path, tool: Any) -> bool:
    """¿Describe ya la huella escrita el índice que hay para estos documentos?

    Una huella «con vectores» no vale sin su fichero de vectores.
    """
    fingerprint = _fingerprint(_read(root, files))
    if tool.kb_embed.disponible():
        # Con el modelo vale el índice con vectores, o el de un intento fallido de calcularlos.
        accepted = {fingerprint + VECTORS, fingerprint + VECTORS_FAILED}
    else:
        accepted = {fingerprint + WORDS}
    try:
        written = stamp.read_text()
    except FileNotFoundError:
        return False
    if written not in accepted or not Path(tool.DB).is_file():
        return False
    return not written.endswith(VECTORS) or Path(tool.VEC).is_file()


def _rebuild(
    root: Path, files: list[Path], corpus: Path, stamp: Path, tool: Any,
) -> dict[str, Any]:
    """Copia lo leído, reindexa y escribe la huella de lo que quedó. Bajo los dos cerrojos."""
    contents = _read(root, files)
    fingerprint = _fingerprint(contents)
    tried_vectors = bool(tool.kb_embed.disponible())
    vectors = Path(tool.VEC)
    stamp.unlink(missing_ok=True)
    if corpus.is_dir():
        for old in corpus.rglob("*.md"):
            old.unlink()
    for relative, data in contents:
        target = corpus / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    before, vectors_before = _signature(Path(tool.DB)), _signature(vectors)
    # Su salida va a la consola con emojis; en Windows (cp1252) imprimirla rompe el índice.
    # La consola es de todo el proceso: se captura bajo el cerrojo común.
    with console.captured():
        result = tool.build()
    if result not in (None, 0):
        return {"available": False, "note": "no se pudo indexar la documentación"}
    after = _signature(Path(tool.DB))
    if after is None or after == before:
        # `build()` salió en verde sin sustituir el índice: otro proceso (fuera de EMMA) tiene su
        # cerrojo. Se sirve el índice que haya, sin huella: la siguiente vez se reintenta.
        return {
            "available": after is not None, "documents": len(files), "rebuilt": False,
            "note": "otro proceso estaba reindexando la documentación",
        }
    vectors_after = _signature(vectors)
    if vectors_after is not None and vectors_after != vectors_before:
        built = fingerprint + VECTORS
    else:
        built = fingerprint + (VECTORS_FAILED if tried_vectors else WORDS)
    _write_atomically(stamp, built)
    return {"available": True, "documents": len(files), "rebuilt": True,
            "semantic": built.endswith(VECTORS)}


def _point_at(tool: Any, state: Path) -> None:
    """`kb` fija sus rutas al importarse (`ROOT`, `FV`, `DB`…) con el `BTP_REPO` de ese momento.
    Si el estado de EMMA cambia después (otro almacén, otra prueba), se le vuelven a dar las de
    ahora: es su forma de calcularlas, con el estado de EMMA. La copia no se toca."""
    corpus = str(state / CORPUS)
    tool.ROOT, tool.FV = str(state), corpus
    tool.DB = str(Path(corpus) / ".kb_index.db")
    tool.IDX = str(Path(corpus) / ".kb_index.json")
    tool.VEC = str(Path(corpus) / ".kb_index.vectors.npy")
    embed = tool.kb_embed
    model_file = str(MODEL / "model_qint8_avx512_vnni.onnx")
    if model_file != embed.MODEL_FILE:
        embed.MODEL_DIR, embed.MODEL_FILE = str(MODEL), model_file
        embed.TOKENIZER_FILE = str(MODEL / "tokenizer.json")
        # Su carga es una vez por proceso: con rutas nuevas, se vuelve a intentar.
        embed._session = embed._tokenizer = embed._import_error = None


def semantic() -> bool:
    """¿Está la capa vectorial (modelo en su sitio y librerías)?"""
    tool = _tool()
    with _LOCK:
        _point_at(tool, polaris.configure())
        return bool(tool.kb_embed.disponible())


def _indexed_vectors(tool: Any) -> bool:
    """¿Ordena `retrieve` también por significado? Hace falta el modelo Y vectores en el índice:
    con el modelo y un índice solo de palabras, ordena por palabras."""
    return bool(tool.kb_embed.disponible()) and Path(tool.VEC).is_file()


def search(query: str, k: int = 6) -> dict[str, Any]:
    """Los pasajes más relevantes, con su fichero y sección; sin síntesis (la hace quien lee)."""
    state = refresh()
    if not state["available"]:
        return {**state, "results": []}
    tool = _tool()
    with _LOCK:
        _point_at(tool, polaris.configure())
        hits = tool.retrieve(query, k=k, scope="internal")
        indexed = _indexed_vectors(tool)
    return {
        "available": True,
        "semantic": indexed,
        "results": [
            {
                "path": str(path).replace("\\", "/"),
                "section": title,
                "text": text if len(text) <= MAX_PASSAGE else text[:MAX_PASSAGE] + "…",
            }
            for path, title, text, _score in hits
        ],
    }
