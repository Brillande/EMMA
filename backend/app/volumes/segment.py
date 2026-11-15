# SPDX-License-Identifier: AGPL-3.0-or-later
"""Segmentación de un TAC con TotalSegmentator, como programa externo y local.

Por qué es un programa externo: TotalSegmentator (Wasserthal et al., Radiol AI 2023; código y
pesos de las tareas usadas bajo Apache-2.0) necesita PyTorch y varios GB de pesos. No cabe en el
instalador de EMMA; se instala aparte, con sus pesos **antes del vuelo** —su documentación explica
cómo usarlo sin conexión copiando `~/.totalsegmentator`—, como el servidor del modelo de lenguaje
o tesseract. Sin él, la segmentación se declara no disponible; los estudios se ven igual.

Código de Polaris ADAPTADO a mano (github.com/BeyondTheProtocol/polaris, `tools/visor3d.py`
@ 7bf47257, el commit que se copió primero; AGPL-3.0-or-later, © 2026 la autora de Polaris,
«Beyond the Protocol»): `segmenta()` —una pasada por tarea, `total` con subconjunto de clases— y
`exige_telemetria_apagada()`. Ninguna de las dos se llama tal cual en la copia; son divergencias
pendientes de decisión (AGPL §5a; `docs/polaris-divergencias.md`):
  * `telemetry_off()`: Polaris solo mira `~/.totalsegmentator/config.json` e ignora
    `TOTALSEG_HOME_DIR`, que TotalSegmentator sí respeta; con la telemetría encendida en esa
    carpeta, el original la da por apagada y dejaría segmentar
    (`test_segmentation_refuses_to_run_with_telemetry_on`). Aquí se mira donde la busca el propio
    TotalSegmentator, y sin configuración se da por encendida, como en Polaris.
  * `run()`: Polaris importa la API de Python de TotalSegmentator (torch, varios GB, GPU de Apple
    `mps`, salida multietiqueta y su tabla de clases); aquí va por su línea de órdenes, en un
    proceso aparte, con una máscara por clase y `cuda`/`cpu`. EMMA no lleva torch en el paquete.
    Desde el 2026-11-11, una tarea que falla en GPU se repite en CPU y las que quedan van ya a CPU.
    En el portátil de desarrollo la GPU fallaba con «CUDA error: misaligned address / illegal
    memory access» por un overclock de MSI Center (+200 MHz núcleo y memoria); de serie, 8 de 8
    bien con cuDNN (`docs/apagado-progresivo/README.md`). El paso a CPU queda por si una GPU
    inestable vuelve: la segmentación termina igual, más lenta.
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import nibabel as nib

from app import memguard
from app.volumes.assets import Preset

TIMEOUT_S = 3600


class SegmenterUnavailable(RuntimeError):
    """No hay TotalSegmentator, o no respondió, o tiene la telemetría encendida."""


def find(configured: str | None = None) -> str | None:
    """El ejecutable: el configurado o el del PATH."""
    for candidate in (configured, shutil.which("TotalSegmentator")):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def command_prefix(executable: str) -> list[str]:
    """Cómo se llama a TotalSegmentator: su lanzador, o un Python que lleva el paquete.

    El paquete de modelos (`backend/packaging/models_pack.py`) trae una copia de Python, no un
    venv: el `TotalSegmentator.exe` de un venv lleva escrita la ruta del Python de la máquina que
    lo instaló y en otra no arranca. Con un intérprete se entra por el mismo `main()` del lanzador
    (`totalsegmentator.bin.TotalSegmentator`, su `entry_points.txt`).
    """
    if Path(executable).stem.lower().startswith("python"):
        return [executable, "-m", "totalsegmentator.bin.TotalSegmentator"]
    return [executable]


def telemetry_off(executable: str) -> bool:
    """True si la telemetría está apagada. Polaris aborta si no: un TAC no genera avisos de uso.

    La configuración vive en `~/.totalsegmentator/config.json` (`send_usage_stats`), o bajo
    `TOTALSEG_HOME_DIR`, como la busca el propio TotalSegmentator. Tiene que existir apagada ANTES
    de la primera ejecución: si no, TotalSegmentator la crea encendida y ya envía esa primera.
    """
    home = os.environ.get("TOTALSEG_HOME_DIR")
    config = (Path(home) if home else Path.home() / ".totalsegmentator") / "config.json"
    try:
        return json.loads(config.read_text(encoding="utf-8")).get("send_usage_stats") is False
    except (OSError, ValueError):
        return False


def free_ram_gb() -> float | None:
    """Memoria física libre, en GiB, o None si este sistema no la dice."""
    try:
        if sys.platform == "win32":
            class _Status(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    ("total", ctypes.c_ulonglong), ("available", ctypes.c_ulonglong),
                    ("page_total", ctypes.c_ulonglong), ("page_free", ctypes.c_ulonglong),
                    ("virtual_total", ctypes.c_ulonglong), ("virtual_free", ctypes.c_ulonglong),
                    ("extended", ctypes.c_ulonglong),
                ]

            status = _Status()
            status.length = ctypes.sizeof(_Status)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            return float(status.available) / 2**30
        pages = os.sysconf("SC_AVPHYS_PAGES")
        return float(pages * os.sysconf("SC_PAGE_SIZE")) / 2**30
    except (AttributeError, OSError, ValueError):
        return None


# Margen sobre la memoria medida: otra medida del mismo tamaño no tiene por qué pedir lo mismo.
RAM_MARGIN = 1.25
WORKING_MM = 1.5  # resolución a la que TotalSegmentator remuestrea antes de segmentar


def required_ram_gb(ct_path: Path, preset: Preset) -> float | None:
    """La memoria que pedirá segmentar este TAC con este preset, por su tamaño (None: no aplica)."""
    if preset.ram_gb_per_mvoxel is None:
        return None
    # Solo la cabecera: el TAC no se carga. Sus stubs no declaran get_zooms en la base común.
    header: Any = nib.load(str(ct_path)).header
    extent = [float(n) * float(z) for n, z in zip(header.get_data_shape()[:3],
                                                  header.get_zooms()[:3], strict=True)]
    mvoxels = math.prod(e / WORKING_MM for e in extent) / 1e6
    return (preset.ram_gb_fixed + preset.ram_gb_per_mvoxel * mvoxels) * RAM_MARGIN


# Ventana sin gastar CPU tras la que una segmentación se da por colgada (la de producción de
# Polaris `guarda_memoria`, 10 min).
IDLE_S = 600.0


def _guarded(command: list[str], ceiling_gb: float, task: str) -> None:
    """La tarea con el techo de memoria de Polaris (`app/memguard.py`): se corta, no se ahoga."""
    outcome = memguard.run(command, ceiling_gb, idle_s=IDLE_S)
    if outcome.killed_for_memory:
        raise SegmenterUnavailable(
            f"TotalSegmentator se cortó en la tarea {task}: pasó de {ceiling_gb:.1f} GB "
            f"(pico {outcome.peak_gb:.1f} GB). No hay resultado a medias."
        )
    if outcome.code == memguard.HUNG:
        raise SegmenterUnavailable(
            f"TotalSegmentator se quedó colgado en la tarea {task} (sin gastar CPU "
            f"{IDLE_S / 60:.0f} min) y se cortó."
        )
    if outcome.code != 0:
        raise TaskFailed(
            f"TotalSegmentator falló en la tarea {task} (código {outcome.code}); el detalle está "
            f"en el registro del backend."
        )


def run(
    executable: str, ct_path: Path, out_dir: Path, preset: Preset, device: str = "gpu"
) -> dict[str, Path]:
    """Segmenta con cada tarea del preset. Devuelve {clase: ruta de su máscara}."""
    needed = required_ram_gb(ct_path, preset)
    if needed is not None:
        free = free_ram_gb()
        if free is None or free < needed:
            # La guarda de memoria de Polaris la cortaba a medias; aquí no se lanza.
            shown = "desconocida" if free is None else f"{free:.1f} GB"
            raise SegmenterUnavailable(
                f"{preset.display}: este TAC necesita unos {needed:.1f} GB de memoria libre y "
                f"hay {shown}. Cierra programas y vuelve a lanzarla; no se lanza para no "
                f"cortarla a medias."
            )
    if not telemetry_off(executable):
        raise SegmenterUnavailable(
            "la telemetría de TotalSegmentator está encendida: apágala antes de segmentar "
            "(totalseg_set_config --send_usage_stats false)"
        )
    masks: dict[str, Path] = {}
    for task, subset in preset.tasks:
        task_dir = out_dir / task
        try:
            _task(executable, ct_path, task_dir, task, subset, device, needed)
        except TaskFailed:
            if device != "gpu":
                raise
            # Una GPU inestable (el 2026-11-11, un overclock de MSI Center) falla con «CUDA
            # error: illegal memory access» y a veces en varias tareas seguidas. La tarea se repite
            # en CPU y las que quedan ya van a CPU: reintentar la GPU en cada una costaba ~25 s por
            # tarea y dejaba el preset más lento que la CPU sola (291 s frente a 238). Un fallo que
            # no sea de la GPU volverá a fallar aquí y se informa igual.
            shutil.rmtree(task_dir, ignore_errors=True)
            device = "cpu"
            _task(executable, ct_path, task_dir, task, subset, device, needed)
        for mask in task_dir.glob("*.nii.gz"):
            masks[mask.name.removesuffix(".nii.gz")] = mask
    return masks


class TaskFailed(SegmenterUnavailable):
    """La tarea terminó con error (no por memoria ni por quedarse colgada): se puede reintentar."""


def _task(executable: str, ct_path: Path, task_dir: Path, task: str, subset: tuple[str, ...] | None,
          device: str, needed: float | None) -> None:
    """Una tarea de TotalSegmentator en un dispositivo; sus máscaras quedan en `task_dir`."""
    command = [*command_prefix(executable), "-i", str(ct_path), "-o", str(task_dir), "-ta", task,
               "-d", device, "-q"]
    if subset:
        command += ["--roi_subset", *subset]
    if needed is not None:
        _guarded(command, needed, task)
        return
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=TIMEOUT_S, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SegmenterUnavailable(f"TotalSegmentator no respondió ({task}): {exc}") from exc
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-300:]
        raise TaskFailed(f"TotalSegmentator falló en la tarea {task}: {tail}")
