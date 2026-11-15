"""Desplazamientos de reloj (overclock) de la GPU NVIDIA, leídos del controlador con NVAPI.

Por qué existe: las medidas de energía de `medir.py` dependen de si la GPU va de serie o con
overclock. El 2026-11-11 MSI Center tenía +200 MHz en el núcleo y +200 MHz en la memoria (P0), lo que
encaja con los fallos CUDA de la segmentación; este script lo lee del propio controlador
(`NvAPI_GPU_GetPstates20`), sin permisos de administrador.

Con `--poner-a-cero` pone a 0 los desplazamientos de núcleo y memoria de P0
(`NvAPI_GPU_SetPstates20`): exige permisos de administrador (sin ellos, NVAPI devuelve -137) y es
reversible (MSI Center puede volver a aplicarlos al cambiar de escenario o al reiniciar).

Uso: python docs/apagado-progresivo/scripts/nvapi_desplazamientos.py [--poner-a-cero]
"""
import ctypes
from ctypes import c_uint32 as U, c_int32 as I, Structure, POINTER, byref

nv = ctypes.WinDLL("nvapi64.dll")
qi = nv.nvapi_QueryInterface; qi.restype = ctypes.c_void_p; qi.argtypes = [U]
def fn(id_, *args): return ctypes.CFUNCTYPE(I, *args)(qi(id_))
init = fn(0x0150E828); enum = fn(0xE5AC921F, ctypes.c_void_p * 64, POINTER(U)); get = fn(0x6FF81213, ctypes.c_void_p, ctypes.c_void_p)

class Delta(Structure): _fields_ = [("value", I), ("min", I), ("max", I)]
class Clock(Structure): _fields_ = [("domainId", U), ("typeId", U), ("editable", U), ("delta", Delta), ("data", U * 5)]
class Volt(Structure): _fields_ = [("domainId", U), ("editable", U), ("volt_uV", U), ("delta", Delta)]
class Pstate(Structure): _fields_ = [("pstateId", U), ("editable", U), ("clocks", Clock * 8), ("baseVoltages", Volt * 4)]
class Ov(Structure): _fields_ = [("numVoltages", U), ("voltages", Volt * 4)]
class Info(Structure): _fields_ = [("version", U), ("editable", U), ("numPstates", U), ("numClocks", U), ("numBaseVoltages", U), ("pstates", Pstate * 16), ("ov", Ov)]

assert init() == 0, "NvAPI_Initialize"
handles = (ctypes.c_void_p * 64)(); n = U()
assert enum(handles, byref(n)) == 0 and n.value >= 1
for ver in (2, 1):
    info = Info(); info.version = ctypes.sizeof(Info) - (0 if ver == 2 else ctypes.sizeof(Ov)) | (ver << 16)
    r = get(handles[0], ctypes.addressof(info))
    if r == 0: break
print("GetPstates20 versión", ver, "resultado", r)
dom = {0: "núcleo (graphics)", 4: "memoria"}
for p in info.pstates[: info.numPstates]:
    for c in p.clocks[: info.numClocks]:
        print(f"P{p.pstateId} {dom.get(c.domainId, c.domainId)}: desplazamiento {c.delta.value / 1000:+.0f} MHz (permitido {c.delta.min / 1000:+.0f}…{c.delta.max / 1000:+.0f}), editable={c.editable & 1}")

import sys
if "--poner-a-cero" in sys.argv:
    setp = fn(0x0F4DAE6B, ctypes.c_void_p, ctypes.c_void_p)
    p0 = next(p for p in info.pstates[: info.numPstates] if p.pstateId == 0)
    for ver in (1, 2):
        s = Info(); s.version = ctypes.sizeof(Info) - (0 if ver == 2 else ctypes.sizeof(Ov)) | (ver << 16)
        s.numPstates, s.numClocks, s.numBaseVoltages = 1, 0, 0
        s.pstates[0].pstateId = 0
        for c in p0.clocks[: info.numClocks]:
            if c.domainId in (0, 4):
                k = s.pstates[0].clocks[s.numClocks]; k.domainId, k.typeId = c.domainId, c.typeId; k.delta.value = 0
                s.numClocks += 1
        r = setp(handles[0], ctypes.addressof(s))
        print("SetPstates20 versión", ver, "resultado", r)
        if r == 0: break
