"""Potencia de la CPU en vatios desde el «Energy Meter» de Windows (contadores RAPL), sin administrador.

Por qué existe: los primeros datos de `medir.py` solo tenían el % de uso de la CPU, no vatios. Windows 11
publica los contadores RAPL del procesador como contadores de rendimiento («Energy Meter», en español
«Medidor de energía»), en milivatios: `RAPL_Package0_PKG` (paquete entero), `RAPL_Package0_PP0`
(núcleos), `RAPL_Package0_PP1` (gráfica integrada) y `RAPL_Package0_DRAM` (memoria). Se leen con PDH
(`PdhAddEnglishCounterW`, nombres en inglés en cualquier idioma de Windows). En el portátil de
desarrollo, PP1 y DRAM dan 0: no los expone o la gráfica integrada está apagada.

Es lo que el propio procesador estima de su consumo (RAPL), no un vatímetro externo.

Uso suelto:  python cpu_rapl.py <segundos> <salida.csv>   (una fila cada 0,5 s: t, pkg_w, nucleos_w, igpu_w, dram_w)
Uso desde `medir.py`: `Rapl().read()` devuelve el último valor de cada contador en W.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

_pdh = ctypes.WinDLL("pdh.dll")
_COUNTERS = {"cpu_pkg_w": "RAPL_Package0_PKG", "cpu_nucleos_w": "RAPL_Package0_PP0",
             "cpu_igpu_w": "RAPL_Package0_PP1", "cpu_dram_w": "RAPL_Package0_DRAM"}
_PDH_FMT_DOUBLE = 0x00000200


class _Value(ctypes.Structure):
    _fields_ = [("status", wintypes.DWORD), ("value", ctypes.c_double)]


class Rapl:
    def __init__(self) -> None:
        self.query = ctypes.c_void_p()
        if _pdh.PdhOpenQueryW(None, None, ctypes.byref(self.query)) != 0:
            raise OSError("PdhOpenQuery")
        self.handles: dict[str, ctypes.c_void_p] = {}
        for key, instance in _COUNTERS.items():
            h = ctypes.c_void_p()
            path = f"\\Energy Meter({instance})\\Power"
            if _pdh.PdhAddEnglishCounterW(self.query, path, None, ctypes.byref(h)) == 0:
                self.handles[key] = h
        if not self.handles:
            raise OSError("este Windows no publica el Energy Meter (RAPL)")
        _pdh.PdhCollectQueryData(self.query)

    def read(self) -> dict[str, float | None]:
        _pdh.PdhCollectQueryData(self.query)
        out: dict[str, float | None] = {}
        for key in _COUNTERS:
            h = self.handles.get(key)
            v = _Value()
            ok = h is not None and _pdh.PdhGetFormattedCounterValue(h, _PDH_FMT_DOUBLE, None, ctypes.byref(v)) == 0
            out[key] = round(v.value / 1000.0, 3) if ok else None  # mW → W
        return out


if __name__ == "__main__":
    seconds, path = float(sys.argv[1]), sys.argv[2]
    r = Rapl()
    with open(path, "w", encoding="utf-8") as f:
        f.write("t," + ",".join(_COUNTERS) + "\n")
        end = time.time() + seconds
        while time.time() < end:
            time.sleep(0.5)
            v = r.read()
            f.write(f"{time.time():.3f}," + ",".join("" if v[k] is None else str(v[k]) for k in _COUNTERS) + "\n")
            f.flush()
