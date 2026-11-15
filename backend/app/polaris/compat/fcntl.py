# SPDX-License-Identifier: AGPL-3.0-or-later
"""`fcntl.flock` para Windows, solo para el código de Polaris copiado tal cual.

Por qué existe: `borde.py` de Polaris importa `fcntl` (de Unix) para un único cerrojo de fichero, y
con él caen todas las herramientas que lo importan, entre ellas `ia.py` (el enrutador que EMMA
apunta a Ollama) y `deid.py`. La regla del proyecto impide tocar la copia, así que el hueco se
llena desde fuera: el adaptador pone esta carpeta en `sys.path` **solo en Windows** y Polaris
encuentra un `fcntl` con lo único que usa (`flock` con `LOCK_EX`, `LOCK_UN` y `LOCK_NB`,
comprobado sobre la copia). El cerrojo es de `msvcrt` sobre el primer byte del fichero: exclusivo
entre procesos, como `flock` exclusivo.

Licencia y origen (AGPL §5a): este fichero no contiene código de Polaris. Es un `fcntl` de EMMA
para que `polaris/tools/borde.py` de la copia literal (commit en `polaris/ADOPTADO.txt`;
AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the Protocol») importe en Windows sin
modificarla.
"""

from __future__ import annotations

import contextlib
import msvcrt
import os
import time
from typing import IO

LOCK_SH = 1
LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8
_RETRY_S = 0.05


def _fd(target: int | IO[bytes] | IO[str]) -> int:
    return target if isinstance(target, int) else target.fileno()


def flock(target: int | IO[bytes] | IO[str], operation: int) -> None:
    fd = _fd(target)
    position = os.lseek(fd, 0, os.SEEK_CUR)
    os.lseek(fd, 0, os.SEEK_SET)
    try:
        if operation & LOCK_UN:
            # Como flock: soltar un cerrojo que no se tiene no es un error.
            with contextlib.suppress(OSError):
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            return
        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError as exc:
                if operation & LOCK_NB:
                    raise BlockingIOError(exc.errno, "el fichero está bloqueado") from exc
                time.sleep(_RETRY_S)
    finally:
        os.lseek(fd, position, os.SEEK_SET)
