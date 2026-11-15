# SPDX-License-Identifier: AGPL-3.0-or-later
"""`guarda_memoria` de Polaris en Windows: sus mediciones de macOS, con la API de Windows.

Por qué existe: Polaris vigila el árbol de procesos de una segmentación o una inferencia y lo mata
si pasa de un techo de memoria (`corre`), porque una que ahoga la máquina a medias no deja nada
útil (20 GB del esqueleto en un Mac de 16). Su lógica de decisión se usa tal cual. Lo que no
funciona fuera de macOS son sus lecturas: `ps`, `proc_pid_rusage` de `libSystem`, `vmmap`,
`sysctl` y `os.killpg`. Aquí se dan las mismas respuestas con la API de Windows, fuera de la
copia, como `compat/fcntl.py`:

* `_arbol`: el árbol de procesos con una instantánea de Toolhelp32.
* `_huella_una`: el conjunto de trabajo del proceso (memoria física que ocupa de verdad). NO la
  memoria comprometida (`PrivateUsage`): torch y CUDA comprometen mucho más de lo que tocan, y
  con ella la guarda mató una segmentación sana del esqueleto (9,3 GB comprometidos con 7,4 GB de
  memoria física bajando, 2026-10-04). Es la misma trampa que Polaris describe con Metal en macOS.
  Lo que el conjunto de trabajo no ve (lo paginado) lo vigila `_swap_gb`.
* `_rss_gb`: el conjunto de trabajo (`WorkingSetSize`), su RSS.
* `_metal_gb`: 0. Su resta de Metal existe porque en un Mac la GPU comparte la RAM; con una GPU
  dedicada (la de esta máquina), la memoria de vídeo no es RAM del sistema.
* `_swap_gb`: lo que el fichero de paginación tiene ocupado de verdad (contador del sistema
  «Paging File(_Total) % Usage» por su tamaño). Restar comprometido menos físico, como se hizo
  primero, también contaba las reservas de CUDA como swap.
* `_cpu_por_pid`: tiempo de usuario más núcleo de cada proceso (`GetProcessTimes`).
* `_mata_grupo`: `taskkill /T /F`, que mata el árbol entero.
* `_vuelca_sample`: no hay `sample` en Windows; no se vuelca traza.
* `os.getpgid` / `os.killpg`: `corre` los llama al interrumpirse (Ctrl-C) para llevarse el árbol
  por delante. En Windows no existen, el `AttributeError` se lo traga su `try/except` y el árbol
  quedaba vivo. Se le da un `os` con esos dos nombres: el "grupo" es el pid raíz y matarlo es el
  mismo `taskkill /T /F`.

`install()` las sustituye en el módulo cargado, una vez. Solo se usa por `app/memguard.py`.

Licencia y origen (AGPL §5a): este fichero no contiene código de Polaris. Las funciones de aquí son
de EMMA y sustituyen, con el mismo nombre y contrato, las de `polaris/tools/guarda_memoria.py` de
la copia literal (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris,
«Beyond the Protocol»), que no se modifica.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
from ctypes import wintypes
from typing import Any

_LOCK = threading.Lock()
_GB = float(2**30)
_TH32CS_SNAPPROCESS = 0x2
_QUERY = 0x1000 | 0x0010  # PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ


class _Entry(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260),
    ]


class _Counters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t), ("PrivateUsage", ctypes.c_size_t),
    ]


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.DWORD), ("load", wintypes.DWORD),
        ("total", ctypes.c_ulonglong), ("available", ctypes.c_ulonglong),
        ("page_total", ctypes.c_ulonglong), ("page_free", ctypes.c_ulonglong),
        ("virtual_total", ctypes.c_ulonglong), ("virtual_free", ctypes.c_ulonglong),
        ("extended", ctypes.c_ulonglong),
    ]


def _kernel() -> Any:
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _psapi() -> Any:
    return ctypes.WinDLL("psapi", use_last_error=True)


def parents() -> dict[int, int]:
    """{pid: pid del padre} de todos los procesos vivos."""
    kernel = _kernel()
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = kernel.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    found: dict[int, int] = {}
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        return found
    try:
        entry = _Entry()
        entry.dwSize = ctypes.sizeof(_Entry)
        ok = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            found[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            ok = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    return found


def tree(root: int) -> list[int]:
    """El pid raíz y todos sus descendientes vivos (su `_arbol`)."""
    children: dict[int, list[int]] = {}
    for pid, parent in parents().items():
        if pid != parent:
            children.setdefault(parent, []).append(pid)
    out: list[int] = []
    stack = [root]
    while stack:
        pid = stack.pop()
        if pid in out:
            continue
        out.append(pid)
        stack.extend(children.get(pid, []))
    return out


def _counters(pid: int) -> _Counters | None:
    kernel = _kernel()
    kernel.OpenProcess.restype = wintypes.HANDLE
    handle = kernel.OpenProcess(_QUERY, False, pid)
    if not handle:
        return None
    try:
        counters = _Counters()
        counters.cb = ctypes.sizeof(_Counters)
        if not _psapi().GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return None
        return counters
    finally:
        kernel.CloseHandle(handle)


def footprint_gb(pid: int) -> float | None:
    """Memoria física que ocupa el proceso (GB), o None si no se puede leer (su `_huella_una`)."""
    counters = _counters(pid)
    return None if counters is None else counters.WorkingSetSize / _GB


def rss_gb(pids: list[int]) -> float:
    """Suma del conjunto de trabajo (GB) de esos procesos (su `_rss_gb`)."""
    total = 0.0
    for pid in pids:
        counters = _counters(pid)
        if counters is not None:
            total += counters.WorkingSetSize / _GB
    return total


class _CounterValue(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]


def _paging_file_usage_pct() -> float | None:
    """El contador de uso del fichero de paginación del sistema (PDH), o None si no se lee."""
    pdh: Any = ctypes.WinDLL("pdh")
    query, counter = wintypes.HANDLE(), wintypes.HANDLE()
    if pdh.PdhOpenQueryW(None, 0, ctypes.byref(query)) != 0:
        return None
    try:
        if pdh.PdhAddEnglishCounterW(query, r"\Paging File(_Total)\% Usage", 0,
                                     ctypes.byref(counter)) != 0:
            return None
        if pdh.PdhCollectQueryData(query) != 0:
            return None
        value = _CounterValue()
        if pdh.PdhGetFormattedCounterValue(counter, 0x200, None, ctypes.byref(value)) != 0:
            return None  # 0x200 = PDH_FMT_DOUBLE
        return float(value.doubleValue)
    finally:
        pdh.PdhCloseQuery(query)


def swap_gb() -> float:
    """GB del fichero de paginación ocupados de verdad (su `_swap_gb`)."""
    status = _MemoryStatus()
    status.length = ctypes.sizeof(_MemoryStatus)
    usage = _paging_file_usage_pct()
    if usage is None or not _kernel().GlobalMemoryStatusEx(ctypes.byref(status)):
        return 0.0
    # El límite de compromiso es la memoria física más el fichero de paginación.
    paging_file = max(0, status.page_total - status.total)
    return usage / 100.0 * float(paging_file) / _GB


def cpu_seconds(pids: list[int]) -> dict[int, float]:
    """{pid: segundos de CPU de usuario y núcleo} de los que siguen vivos (su `_cpu_por_pid`)."""
    kernel = _kernel()
    kernel.OpenProcess.restype = wintypes.HANDLE
    out: dict[int, float] = {}
    for pid in pids:
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            continue
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if kernel.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
                kernel_t, user_t = times[2], times[3]
                ticks = sum((t.dwHighDateTime << 32) + t.dwLowDateTime for t in (kernel_t, user_t))
                out[pid] = ticks / 1e7
        finally:
            kernel.CloseHandle(handle)
    return out


def _taskkill(pid: int) -> None:
    """El proceso `pid` y todos sus descendientes, a la fuerza."""
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, check=False)


def kill_tree(proc: Any, pids: list[int]) -> None:
    """Mata el árbol entero (su `_mata_grupo`)."""
    _taskkill(proc.pid)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()


class _OsWithGroups:
    """El `os` que ve `guarda_memoria`: el de verdad, más `getpgid` y `killpg` para Windows.

    `corre` lanza al hijo con `start_new_session=True`, que en Unix lo hace líder de su grupo: el
    id del grupo es su pid. Aquí se conserva esa equivalencia y "matar el grupo" es matar el árbol
    que cuelga de ese pid. La señal se ignora: Windows no tiene SIGTERM entre procesos.
    """

    def __getattr__(self, name: str) -> Any:
        return getattr(os, name)

    @staticmethod
    def getpgid(pid: int) -> int:
        return pid

    @staticmethod
    def killpg(group: int, signal_number: int) -> None:
        _taskkill(group)


_installed: set[int] = set()


def install(module: Any) -> Any:
    """Sustituye las lecturas de macOS de `guarda_memoria` por las de Windows. Idempotente."""
    if sys.platform != "win32":
        return module
    with _LOCK:
        if id(module) in _installed:
            return module
        module._arbol = tree
        module._huella_una = footprint_gb
        module._rss_gb = rss_gb
        module._metal_gb = lambda pids: 0.0
        module._swap_gb = swap_gb
        module._cpu_por_pid = cpu_seconds
        module._mata_grupo = kill_tree
        module._vuelca_sample = lambda pids, folder, verbose=True: None
        module.os = _OsWithGroups()
        _installed.add(id(module))
    return module
