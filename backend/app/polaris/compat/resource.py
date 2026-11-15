# SPDX-License-Identifier: AGPL-3.0-or-later
"""`resource.getrusage` para Windows, solo para las pruebas de Polaris copiadas tal cual.

Por qué existe: `app/volumes/geometry.py` hace las mallas con `visor3d._malla` de Polaris, que
recorta a la caja de la máscara antes de suavizar. Ese recorte es un freno de memoria (sin él, una
lesión pequeña en un estudio grande pedía 16 GB) y Polaris lo fija con una prueba,
`test_visor3d_malla_recorte`, que mide el pico con `resource.getrusage`. `resource` es de Unix: en
Windows la prueba caía en el `import` y el freno quedaba sin comprobar justo en la máquina donde
EMMA corre. La herramienta no importa `resource`; solo la prueba. Así que el hueco se llena como
el de `fcntl`, fuera de la copia: `scripts/polaris_tests.py` pone esta carpeta en `PYTHONPATH`.

Lo único que usa la copia (lo vigila `tests/test_polaris_compat_resource.py`): `RUSAGE_SELF` y
`getrusage(RUSAGE_SELF).ru_maxrss`. Se da con el pico del conjunto de trabajo del proceso
(`PeakWorkingSetSize`), en **bytes**, que es la convención de macOS y la que asume la prueba (en
Linux serían kilobytes).

Solo existe para una prueba de Polaris. El adaptador también pone esta carpeta al final de
`sys.path` dentro de EMMA (por `fcntl`), y hay bibliotecas que prueban `import resource` para
saber si están en Unix y, si importa, le piden `getrlimit` o `setrlimit`. Para ellas este módulo
no debe existir: fuera de un `polaris/tests/test_*.py` el `import` falla con el mismo
`ModuleNotFoundError` que daría Windows sin él.

Licencia y origen (AGPL §5a): este fichero no contiene código de Polaris. Es un `resource` de EMMA
para que `polaris/tests/test_visor3d_malla_recorte.py` de la copia literal (commit en
`polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the Protocol»)
corra en Windows sin modificarla.
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from typing import Any


def _is_polaris_test(main_file: str | None) -> bool:
    """¿El proceso es una prueba de la copia (`…/polaris/tests/test_*.py`)?"""
    if not main_file:
        return False
    path = os.path.abspath(main_file)
    folder = os.path.dirname(path)
    return (
        os.path.basename(path).startswith("test_")
        and os.path.basename(folder) == "tests"
        and os.path.basename(os.path.dirname(folder)) == "polaris"
    )


if not _is_polaris_test(getattr(sys.modules.get("__main__"), "__file__", None)):
    raise ModuleNotFoundError("No module named 'resource'", name="resource")

RUSAGE_SELF = 0


class _Counters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


class struct_rusage:
    """Lo que la copia lee de `getrusage`: el pico de memoria física del proceso, en bytes."""

    def __init__(self, ru_maxrss: int) -> None:
        self.ru_maxrss = ru_maxrss


def getrusage(who: int) -> struct_rusage:
    if who != RUSAGE_SELF:
        raise ValueError("solo RUSAGE_SELF: es lo único que usa la copia de Polaris")
    kernel: Any = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi: Any = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    counters = _Counters()
    counters.cb = ctypes.sizeof(_Counters)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters),
                                      counters.cb):
        # Sin lectura no hay medida: un 0 haría pasar «el pico se queda en megas» sin medir nada.
        raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo no devolvió el pico")
    return struct_rusage(int(counters.PeakWorkingSetSize))
