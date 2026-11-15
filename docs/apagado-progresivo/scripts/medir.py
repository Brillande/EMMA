"""Mide cuánto gasta cada función de EMMA en este equipo, fase a fase, y guarda TODAS las muestras.

Por qué existe: el inventario del apagado progresivo (`docs/apagado-progresivo-inventario.md` §F) da
cifras de consumo, y cada una tiene que poder rehacerse y comprobarse. Este script es el montaje con
el que salen: muestrea cada 0,5 s y escribe cada muestra en un CSV, con la fase en la que cayó, y un
resumen por fase en JSON. Las cifras del inventario son las medias de esos CSV.

Qué mide y con qué (solo Windows; NVIDIA para la GPU):
  * GPU: potencia de la placa en vatios, % de uso y VRAM, con `nvidia-smi --query-gpu=...`. Es la
    lectura del propio controlador de NVIDIA, no un vatímetro.
  * CPU del sistema: % de uso de todos los núcleos, con `GetSystemTimes` de Windows (kernel32).
  * CPU de un proceso y sus hijos (fase del backend): `GetProcessTimes`, en segundos de CPU.
  * CPU en vatios: contadores RAPL del «Energy Meter» de Windows (`cpu_rapl.py`), sin administrador:
    paquete (`cpu_pkg_w`), núcleos, gráfica integrada y memoria.

Uso, desde la raíz del repositorio y con el Python del backend (necesita `app` para algunas fases):
    backend/.venv/Scripts/python.exe docs/apagado-progresivo/scripts/medir.py llm
    backend/.venv/Scripts/python.exe docs/apagado-progresivo/scripts/medir.py backend
    backend/.venv/Scripts/python.exe docs/apagado-progresivo/scripts/medir.py herramientas
    backend/.venv/Scripts/python.exe docs/apagado-progresivo/scripts/medir.py segmentacion
Salida: `docs/apagado-progresivo/datos/<plan>-<fecha>.csv` (muestras) y `.json` (resumen).
"""

from __future__ import annotations

import csv
import ctypes
import datetime as dt
import io
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
OUT = REPO / "docs" / "apagado-progresivo" / "datos"


class _FT(ctypes.Structure):
    _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]


def _ft(f: _FT) -> int:
    return (f.hi << 32) | f.lo


def _system_times() -> tuple[int, int]:
    idle, kernel, user = _FT(), _FT(), _FT()
    ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
    return _ft(idle), _ft(kernel) + _ft(user)


def _process_cpu_s(pid: int) -> float:
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    c, e, k, u = _FT(), _FT(), _FT(), _FT()
    ctypes.windll.kernel32.GetProcessTimes(handle, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k),
                                           ctypes.byref(u))
    ctypes.windll.kernel32.CloseHandle(handle)
    return (_ft(k) + _ft(u)) / 1e7


def tree_cpu_s(pid: int) -> float:
    """Segundos de CPU de un proceso y de sus hijos directos (el lanzador del venv crea uno)."""
    out = subprocess.run(["powershell", "-NoProfile", "-c",
                          f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}' | % ProcessId"],
                         capture_output=True, text=True).stdout
    return sum(_process_cpu_s(int(x)) for x in out.split() if x.strip().isdigit()) + _process_cpu_s(pid)


class Meter:
    """Muestreo en segundo plano; `phase()` marca a qué fase pertenece cada muestra."""

    def __init__(self) -> None:
        self.samples: list[dict[str, object]] = []
        self.phases: list[dict[str, object]] = []
        self.current = "arranque-del-medidor"
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        sys.path.insert(0, str(Path(__file__).parent))
        from cpu_rapl import Rapl
        rapl = Rapl()
        prev = _system_times()
        while not self._stop:
            out = subprocess.run(["nvidia-smi", "--query-gpu=power.draw,utilization.gpu,memory.used",
                                  "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout
            watts, util, vram = (float(x) for x in out.strip().split(","))
            cur = _system_times()
            idle, total = cur[0] - prev[0], cur[1] - prev[1]
            prev = cur
            self.samples.append({"t": round(time.time(), 3), "fase": self.current, "gpu_w": watts,
                                 "gpu_uso_pct": util, "vram_mb": vram,
                                 "cpu_sistema_pct": round(100 * (1 - idle / total), 2) if total else 0.0,
                                 **rapl.read()})
            time.sleep(0.5)

    def __enter__(self) -> Meter:
        self._thread.start()
        time.sleep(1)
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop = True
        self._thread.join()

    def phase(self, name: str, fn, pid: int | None = None) -> object:  # type: ignore[no-untyped-def]
        cpu0 = tree_cpu_s(pid) if pid else None
        self.current = name
        t0 = time.time()
        result = fn()
        t1 = time.time()
        self.current = "entre-fases"
        row: dict[str, object] = {"fase": name, "inicio": round(t0, 3), "fin": round(t1, 3),
                                  "duracion_s": round(t1 - t0, 2), "resultado": result}
        if pid:
            row["cpu_proceso_s"] = round(tree_cpu_s(pid) - (cpu0 or 0.0), 2)
        self.phases.append(row)
        print(json.dumps(row, ensure_ascii=False, default=str), flush=True)
        return result

    def save(self, plan: str) -> Path:
        OUT.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y-%m-%dT%H%M")
        base = OUT / f"{plan}-{stamp}"
        with open(base.with_suffix(".csv"), "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.samples[0]))
            writer.writeheader()
            writer.writerows(self.samples)
        summary = []
        for p in self.phases:
            s = [x for x in self.samples if x["fase"] == p["fase"]]
            mean = (lambda k: round(sum(float(x[k]) for x in s) / len(s), 2)) if s else (lambda k: None)
            summary.append({**p, "muestras": len(s), "gpu_w_media": mean("gpu_w"),
                            "gpu_w_max": max((float(x["gpu_w"]) for x in s), default=None),
                            "gpu_uso_pct_media": mean("gpu_uso_pct"), "vram_mb_media": mean("vram_mb"),
                            "cpu_sistema_pct_media": mean("cpu_sistema_pct"),
                            "cpu_pkg_w_media": mean("cpu_pkg_w"), "cpu_nucleos_w_media": mean("cpu_nucleos_w"),
                            "cpu_pkg_julios": round(mean("cpu_pkg_w") * float(p["duracion_s"]), 1) if s else None,
                            "gpu_julios": round(mean("gpu_w") * float(p["duracion_s"]), 1) if s else None})
        equipo = {
            "fecha": dt.datetime.now().isoformat(timespec="seconds"),
            "gpu": subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
                                  capture_output=True, text=True).stdout.strip(),
            "hilos_cpu": os.cpu_count(),
            "desplazamientos_reloj_gpu": subprocess.run(
                [sys.executable, str(Path(__file__).with_name("nvapi_desplazamientos.py"))],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                env=dict(os.environ, PYTHONIOENCODING="utf-8")).stdout.strip().splitlines()[1:3],
            "nota": "Portátil de desarrollo, no hardware de vuelo. GPU en W según nvidia-smi; CPU en % y en W (RAPL, Energy Meter de Windows).",
        }
        base.with_suffix(".json").write_text(json.dumps({"equipo": equipo, "fases": summary}, ensure_ascii=False,
                                                        indent=1, default=str), encoding="utf-8")
        return base


def wait(seconds: float):  # type: ignore[no-untyped-def]
    return lambda: time.sleep(seconds)


def http(url: str, post: bool = False):  # type: ignore[no-untyped-def]
    def go() -> dict[str, object]:
        t = time.time()
        req = urllib.request.Request(url, data=b"" if post else None, headers={"X-EMMA-Console": "1"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                r.read()
            return {"ok": True, "s": round(time.time() - t, 2)}
        except Exception as exc:  # se registra el fallo, no se para la medida
            return {"ok": False, "error": str(exc)[:120]}
    return go


def ollama(body: dict[str, object]):  # type: ignore[no-untyped-def]
    def go() -> dict[str, object]:
        req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            d = json.load(r)
        return {k: d.get(k) for k in ("load_duration", "eval_count", "eval_duration", "total_duration")}
    return go


def plan_llm(m: Meter, model: str = "qwen3.5:9b") -> None:
    m.phase("reposo", wait(20))
    m.phase("cargar_modelo", ollama({"model": model, "prompt": "", "keep_alive": "10m", "stream": False}))
    m.phase("modelo_cargado_reposo", wait(20))
    m.phase("generar_300_tokens", ollama({"model": model, "stream": False, "keep_alive": "10m", "think": False,
                                          "prompt": "Explica en español qué es la variabilidad de la frecuencia cardiaca.",
                                          "options": {"num_predict": 300}}))
    m.phase("descargar_modelo", ollama({"model": model, "prompt": "", "keep_alive": 0, "stream": False}))
    m.phase("reposo_final", wait(15))


def plan_backend(m: Meter) -> None:
    env = dict(os.environ, EMMA_OFFLINE="true", EMMA_ASSISTANT_WARMUP="false")
    proc = subprocess.Popen([str(BACKEND / ".venv/Scripts/python.exe"), "-m", "uvicorn", "app.main:app",
                             "--port", "8011"], cwd=BACKEND, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:8011"

    def up() -> dict[str, object]:
        t = time.time()
        while time.time() - t < 120:
            try:
                urllib.request.urlopen(base + "/api/indicators", timeout=2).read()
                return {"listo_s": round(time.time() - t, 1)}
            except Exception:
                time.sleep(0.3)
        return {"listo_s": None}
    try:
        m.phase("arrancar_backend", up, pid=proc.pid)
        m.phase("backend_reposo_sin_datos", wait(20), pid=proc.pid)
        m.phase("simular_mision", http(base + "/api/simulate", post=True), pid=proc.pid)
        m.phase("status_x5", lambda: [http(base + "/api/status")() for _ in range(5)], pid=proc.pid)
        m.phase("backend_reposo_con_datos", wait(20), pid=proc.pid)
        m.phase("busqueda_semantica_1", http(base + "/api/kb?q=por%20que%20no%20se%20sube%20nada"), pid=proc.pid)
        m.phase("busqueda_semantica_2", http(base + "/api/kb?q=dosis%20de%20radiacion"), pid=proc.pid)
        m.phase("backend_reposo_final", wait(15), pid=proc.pid)
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)


def plan_herramientas(m: Meter) -> None:
    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)
    from PIL import Image, ImageDraw, ImageFont

    from app import voice
    from app.assistant import audio
    from app.reports import ocr

    m.phase("reposo", wait(15))
    img = Image.new("L", (1654, 2339), 255)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("arial.ttf", 28)
    for i in range(45):
        draw.text((120, 120 + i * 46), f"Hemoglobina {12 + i % 5},{i % 10} g/dL   Leucocitos {5 + i % 4},{i % 7} "
                  f"x10^3/uL   Glucosa {80 + i} mg/dL", fill=0, font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    exe = ocr.find_tesseract(None)
    for n in (1, 2):
        m.phase(f"ocr_pagina_A4_{n}", lambda: {"caracteres": sum(len(p.text) for p in
                                                                 ocr.read(buf.getvalue(), "image/png", exe))})
    wav = OUT.parent / "datos" / "dictado.wav"
    if voice.ready() and wav.exists():
        ogg = audio.to_ogg(wav.read_bytes())
        for n in (1, 2):
            m.phase(f"whisper_dictado_{n}", lambda: {"texto": voice.transcribe(ogg)[:80]})
    m.phase("reposo_final", wait(15))


def plan_segmentacion(m: Meter) -> None:
    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)
    import tempfile

    from app.volumes import assets, segment

    exe = str(BACKEND / ".venv-seg/Scripts/TotalSegmentator.exe")
    ct = Path("app/data/volume_samples/higado-1/ct.nii.gz")
    m.phase("reposo", wait(15))
    for device in ("gpu", "cpu"):
        def go(device: str = device) -> dict[str, object]:
            with tempfile.TemporaryDirectory() as out:
                masks = segment.run(exe, ct, Path(out), assets.PRESETS["higado"], device=device)
            return {"mascaras": len(masks)}
        m.phase(f"segmentar_higado_{device}", go)
        m.phase(f"reposo_tras_{device}", wait(15))


def plan_pantalla(m: Meter) -> None:
    """Reposo con la pantalla encendida, apagada (SC_MONITORPOWER) y otra vez encendida.

    Solo tiene sentido desenchufado y cruzado con `bateria.ps1`: la diferencia de descarga entre
    pantalla encendida y apagada es lo que gasta el panel. Se enciende de nuevo moviendo el ratón un
    píxel (SendInput), que es lo que Windows atiende; el mensaje de encender no basta en Windows 11.
    """
    user32 = ctypes.windll.user32

    def off() -> None:
        user32.SendMessageTimeoutW(0xFFFF, 0x0112, 0xF170, 2, 0x0002, 2000, None)  # HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, apagar

    def on() -> None:
        user32.mouse_event(0x0001, 1, 0, 0, 0)  # MOUSEEVENTF_MOVE
        time.sleep(0.2)
        user32.mouse_event(0x0001, -1 & 0xFFFFFFFF, 0, 0, 0)

    m.phase("pantalla_encendida_1", wait(60))
    off()
    time.sleep(3)
    m.phase("pantalla_apagada", wait(60))
    on()
    time.sleep(3)
    m.phase("pantalla_encendida_2", wait(60))


def _brillo(nivel: int | None = None) -> int:
    """Pone el brillo de la pantalla (WmiSetBrightness) si se da `nivel`; devuelve el que Windows dice."""
    if nivel is not None:
        subprocess.run(["powershell", "-NoProfile", "-c",
                        f"(Get-CimInstance -Namespace root\\wmi -ClassName WmiMonitorBrightnessMethods) | "
                        f"Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=0; Brightness={nivel}}}"],
                       capture_output=True)
        time.sleep(2)
    out = subprocess.run(["powershell", "-NoProfile", "-c",
                          "(Get-CimInstance -Namespace root\\wmi -ClassName WmiMonitorBrightness).CurrentBrightness"],
                         capture_output=True, text=True).stdout
    return int(out.strip())


def plan_brillo(m: Meter) -> None:
    """Reposo con el brillo al 100 %, al 0 % y al 100 %; al final, el brillo de antes.

    Como `plan_pantalla`, solo vale desenchufado y cruzado con `bateria.ps1`. A diferencia de apagar la
    pantalla, el brillo que queda puesto se lee de Windows, así que cada fase dice el que tuvo de verdad.
    La diferencia entre 100 % y 0 % es lo que gasta la retroiluminación.
    """
    antes = _brillo()
    try:
        for nombre, nivel in (("brillo_100_1", 100), ("brillo_0", 0), ("brillo_100_2", 100)):
            real = _brillo(nivel)
            m.phase(nombre, lambda real=real: (time.sleep(60), {"brillo_leido": real})[1])
    finally:
        _brillo(antes)


PLANS = {"brillo": plan_brillo, "pantalla": plan_pantalla, "llm": plan_llm, "backend": plan_backend, "herramientas": plan_herramientas,
         "segmentacion": plan_segmentacion}

if __name__ == "__main__":
    plan = sys.argv[1]
    with Meter() as meter:
        PLANS[plan](meter)
    print("guardado en", meter.save(plan))
