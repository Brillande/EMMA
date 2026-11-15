# SPDX-License-Identifier: AGPL-3.0-or-later
"""El candado entre procesos de Polaris (`_lock.py`) en Windows: una sonda de proceso de verdad.

Por qué existe: `_lock.lock` es un directorio que se crea con `mkdir` y que guarda el PID de su
dueño. Quien espera pregunta si el dueño sigue vivo (`_dueno_vivo`) para reclamar en el acto el
candado de un proceso muerto y respetar el de uno vivo. Polaris lo pregunta con `os.kill(pid, 0)`,
que en Unix es una sonda inocua. En Windows no lo es, y el candado no aguantaba por dos motivos,
los dos medidos en esta máquina con las pruebas del propio Polaris (`test_lock_dueno`,
`test_seguimiento_carrera`) y fijados en `tests/test_polaris_windows_reds.py`:

* **La sonda.** En Windows la señal 0 es `CTRL_C_EVENT`: `os.kill(pid, 0)` no pregunta nada, pide
  a la consola un Ctrl-C para ese grupo de procesos. Con un PID muerto nunca da
  `ProcessLookupError`: o da otro `OSError` y `_dueno_vivo` contesta «no lo sé», o no da ninguno
  (si alguien guarda todavía un asa del proceso) y contesta «vive». En los dos casos el candado
  de un muerto se espera en vez de reclamarse. Aquí se pregunta con `OpenProcess` y
  `WaitForSingleObject`: el proceso existe y no ha terminado, o no. No se manda nada a nadie.
* **Soltarlo mientras otro lo mira.** Windows no deja borrar un fichero que otro proceso tiene
  abierto (WinError 32). Quien espera abre `dueno` para leer el PID; si en ese instante el dueño
  suelta, su `os.remove` falla, `_lock` se lo calla, el `rmdir` falla detrás y el candado queda
  a nombre de un proceso vivo que ya no lo tiene: nadie más entra hasta el tope duro de `_lock`.
  Aquí ese borrado se reintenta un momento, con un `os` propio para `_lock` (el de verdad, con
  `remove` ajustado), como hace `compat/memguard.py` con `guarda_memoria`.

Lo que NO arregla: es el candado, no los ficheros que protege. `seguimiento._write_atomic` acaba en
`os.replace`, que en Windows falla si otro proceso tiene abierto el destino, y un lector no toma
el candado (`tests/test_polaris_windows_reds.py` lo fija). Tampoco cierra la ventana que `_lock`
tiene también en Unix entre juzgar muerto a un dueño y quitarle el candado (`_reclamar`).

Cómo se activa: `install(module)` sobre el `_lock` ya importado; con cualquier otro módulo no hace
nada, para poder llamarla desde un gancho de importación. Las pruebas de Polaris corren en
procesos aparte, sin EMMA: para ellas `compat/sitecustomize.py` llama a `hook()`.

Licencia y origen (AGPL §5a): este fichero no contiene código de Polaris. Las funciones de aquí son
de EMMA y sustituyen, con el mismo nombre y contrato, a `_dueno_vivo` de `polaris/tools/_lock.py`
de la copia literal (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de
Polaris, «Beyond the Protocol»), que no se modifica.
"""

from __future__ import annotations

import ctypes
import importlib.abc
import os
import sys
import threading
import time
from collections.abc import Sequence
from importlib.machinery import ModuleSpec
from types import ModuleType
from typing import Any

_SYNCHRONIZE = 0x00100000
_QUERY_LIMITED = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
_WAIT_OBJECT_0 = 0x0
_WAIT_TIMEOUT = 0x102
_ACCESS_DENIED = 5
_SHARING_VIOLATION = 32
_INVALID_PARAMETER = 87  # lo que da OpenProcess con un PID que no es de ningún proceso
# Cuánto se insiste en borrar `dueno` si otro proceso lo tiene abierto. Quien lo tiene abierto solo
# lee un PID: es un instante. Un segundo es de sobra y queda muy por debajo de cualquier plazo.
RETRY_S = 1.0
_STEP_S = 0.005


def alive(pid: int) -> bool | None:
    """¿Vive el proceso `pid`? `None` si Windows no deja saberlo. No le manda ninguna señal."""
    if pid <= 0:
        return False  # el 0 es el proceso inactivo del sistema: ningún candado es suyo
    kernel: Any = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.WaitForSingleObject.restype = ctypes.c_uint32
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(_SYNCHRONIZE | _QUERY_LIMITED, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error == _INVALID_PARAMETER:
            return False
        if error == _ACCESS_DENIED:
            return True  # existe, pero es de otro usuario: lo mismo que decide `_lock` en Unix
        return None
    try:
        # Un proceso terminado sigue teniendo PID mientras alguien guarde un asa suya (su padre,
        # sin ir más lejos): abrirlo no basta, hay que mirar si ya ha acabado.
        state = kernel.WaitForSingleObject(handle, 0)
    finally:
        kernel.CloseHandle(handle)
    if state == _WAIT_TIMEOUT:
        return True
    if state == _WAIT_OBJECT_0:
        return False
    return None


def owner(folder: str, name: str = "dueno") -> tuple[bool | None, int | None]:
    """Su `_dueno_vivo`: (vive, pid) del dueño que declara el candado `folder`.

    (None, None) si no declara ninguno: un candado de antes de que guardaran el PID, o tomado
    hace microsegundos y aún sin escribir.
    """
    try:
        with open(os.path.join(folder, name), encoding="utf-8") as handle:
            pid = int(handle.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None, None
    return alive(pid), pid


class _OsForLocks:
    """El `os` que ve `_lock`: el de verdad, con un `remove` que aguanta a quien mira el candado."""

    def __getattr__(self, name: str) -> Any:
        return getattr(os, name)

    @staticmethod
    def remove(path: str) -> None:
        deadline = time.monotonic() + RETRY_S
        while True:
            try:
                os.remove(path)
                return
            except PermissionError as exc:
                busy = getattr(exc, "winerror", None) in (_ACCESS_DENIED, _SHARING_VIOLATION)
                if not busy or time.monotonic() >= deadline:
                    raise
            time.sleep(_STEP_S)


_GUARD = threading.Lock()


def _is_the_lock(module: Any) -> bool:
    return (
        getattr(module, "__name__", None) == "_lock"
        and callable(getattr(module, "_dueno_vivo", None))
        and callable(getattr(module, "lock", None))
    )


def install(module: Any) -> Any:
    """Da a `_lock` la sonda y el `os` de Windows. Idempotente; con otro módulo no hace nada."""
    if sys.platform != "win32" or not _is_the_lock(module):
        return module
    with _GUARD:
        # La marca es el propio módulo, no su `id` en una lista aparte: Python reutiliza el `id`
        # de un módulo ya recogido, y un `_lock` nuevo con el `id` de uno viejo se quedaba sin
        # pegamento (pasó en las pruebas, que cargan uno por prueba).
        if isinstance(getattr(module, "os", None), _OsForLocks):
            return module
        name = str(getattr(module, "DUENO", "dueno"))
        module._dueno_vivo = lambda folder: owner(folder, name)
        module.os = _OsForLocks()
    return module


# --------------------------------------------------------------------------- #
# Para los procesos que no pasan por EMMA: las pruebas de la copia
# --------------------------------------------------------------------------- #


def _is_a_polaris_tool(origin: str | None) -> bool:
    """¿Es `…/polaris/tools/_lock.py`? Un `_lock` de otra biblioteca no se toca."""
    if not origin:
        return False
    folder = os.path.dirname(os.path.abspath(origin))
    return (
        os.path.basename(folder) == "tools"
        and os.path.basename(os.path.dirname(folder)) == "polaris"
    )


class _InstallingLoader(importlib.abc.Loader):
    """El cargador de siempre de `_lock`, que instala el pegamento al acabar de ejecutarlo."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        if name == "_inner":
            raise AttributeError(name)
        return getattr(self._inner, name)

    def create_module(self, spec: ModuleSpec) -> ModuleType | None:
        created: ModuleType | None = self._inner.create_module(spec)
        return created

    def exec_module(self, module: ModuleType) -> None:
        self._inner.exec_module(module)
        install(module)


class _LockHook(importlib.abc.MetaPathFinder):
    """Gancho de importación: el `_lock` de una copia de Polaris nace con el pegamento puesto."""

    def __init__(self) -> None:
        self._busy = threading.local()

    def find_spec(
        self, fullname: str, path: Sequence[str] | None, target: ModuleType | None = None
    ) -> ModuleSpec | None:
        # `_busy`: otro gancho que también pregunte a los demás (el del freno, en `app/polaris`)
        # volvería a entrar aquí sin fin.
        if fullname != "_lock" or getattr(self._busy, "on", False):
            return None
        self._busy.on = True
        try:
            for finder in list(sys.meta_path):
                find = getattr(finder, "find_spec", None)
                if finder is self or find is None:
                    continue
                spec: ModuleSpec | None = find(fullname, path, target)
                if spec is None:
                    continue
                loader = spec.loader
                wrapped = loader is None or isinstance(loader, _InstallingLoader)
                if not wrapped and _is_a_polaris_tool(spec.origin):
                    spec.loader = _InstallingLoader(loader)
                return spec
            return None
        finally:
            self._busy.on = False


_HOOK = _LockHook()


def hook() -> None:
    """Instala el gancho en este proceso (solo en Windows). Idempotente."""
    if sys.platform == "win32" and _HOOK not in sys.meta_path:
        sys.meta_path.insert(0, _HOOK)
