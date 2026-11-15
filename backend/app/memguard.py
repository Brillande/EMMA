# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lanzar un proceso pesado con techo de memoria: `guarda_memoria.corre` de Polaris.

Por qué existe: una segmentación o una transcripción que se come la memoria no falla sola, ahoga
la máquina entera (a Polaris le pasó con el esqueleto: 20 GB en un Mac de 16). Su guarda vigila el
árbol de procesos ENTERO, no el hijo directo, y lo mata si pasa del techo dos muestreos seguidos
(código 99). En Windows sus lecturas de macOS se sustituyen por las del sistema
(`app/polaris/compat/memguard.py`); la decisión es la suya.

La salida del proceso no se captura (su `corre` no lo hace): va al registro del backend.

Licencia y origen (AGPL §5a): usa `polaris/tools/guarda_memoria.py` de la copia literal de Polaris,
sin modificarla (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris,
«Beyond the Protocol»); se carga con `app.polaris.load`. De EMMA: las lecturas de Windows que se le
sustituyen (`app/polaris/compat/memguard.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Any

from app import polaris
from app.polaris.compat import memguard as windows

KILLED_FOR_MEMORY = 99
HUNG = 98


@dataclass(frozen=True)
class Outcome:
    code: int
    peak_gb: float

    @property
    def killed_for_memory(self) -> bool:
        return self.code == KILLED_FOR_MEMORY


@cache
def _tool() -> Any:
    return windows.install(polaris.load("guarda_memoria"))


def run(command: list[str], ceiling_gb: float, env: dict[str, str] | None = None,
        interval_s: float = 2.0, idle_s: float | None = None) -> Outcome:
    """El comando con su techo; código y pico de memoria del árbol.

    Con `idle_s`, también se mata si el árbol pasa ese tiempo sin gastar CPU (código 98): Polaris
    lo añadió tras ver a nnU-Net interbloqueado ocho minutos al 0 % (25-sep-2026).
    """
    code, peak = _tool().corre(command, ceiling_gb, intervalo=interval_s, verbose=True, env=env,
                               inactivo_s=idle_s)
    return Outcome(int(code if code is not None else -1), float(peak))
