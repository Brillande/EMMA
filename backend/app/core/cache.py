"""Cache en disco para datos de fuentes externas.

Regla de diseno: **ningun dato externo se presenta sin su antiguedad**. En una
mision, un valor de meteorologia espacial de hace seis horas y uno de hace seis
dias exigen decisiones distintas, y ocultar la diferencia es peligroso.

Por eso `CachedPayload` siempre viaja con `fetched_at`, y la UI muestra la edad
junto al dato. Nunca se devuelve un valor "pelado".
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# En Windows, `os.replace` falla con «acceso denegado» si otro hilo tiene abierto el fichero de
# destino en ese instante (una lectura de la cobertura): se reintenta unas veces, con esperas
# cortas, antes de dar el fallo por bueno.
_REPLACE_RETRIES = (0.01, 0.02, 0.05, 0.1, 0.2)


def _umask() -> int:
    """La mascara de permisos del proceso (solo se puede leer cambiandola: se repone al momento)."""
    mask = os.umask(0)
    os.umask(mask)
    return mask


# `mkstemp` crea el temporal solo para su dueno (0600); `write_text`, como cualquier fichero, con
# 0666 menos la mascara. Se le dan esos permisos antes de sustituir, para que el guion de
# precarga y el servidor, si corren con usuarios distintos, se sigan leyendo la cache.
_FILE_MODE = 0o666 & ~_umask()


def _replace(source: str, target: Path) -> None:
    """`os.replace`, reintentado si el destino esta abierto un instante (Windows)."""
    for wait in _REPLACE_RETRIES:
        try:
            os.replace(source, target)
            return
        except PermissionError:
            time.sleep(wait)
    os.replace(source, target)


@dataclass(frozen=True, slots=True)
class CachedPayload:
    """Un dato externo junto con su procedencia y antiguedad."""

    data: Any
    fetched_at: datetime
    source: str
    from_cache: bool

    @property
    def age(self) -> timedelta:
        return datetime.now(UTC) - self.fetched_at

    def is_stale(self, max_age: timedelta) -> bool:
        return self.age > max_age

    @property
    def age_seconds(self) -> int:
        """La antiguedad en numero, para que la interfaz decida si esta caducado.

        `describe_age` es para leerlo; interpretar ese texto desde el cliente para
        pintar el dato caducado en cian (NASA-STD-3001 Vol 2, tabla F.5-1) seria
        fragil.
        """
        return int(self.age.total_seconds())

    def describe_age(self) -> str:
        """Texto legible para mostrar junto al dato en la interfaz."""
        seconds = int(self.age.total_seconds())
        if seconds < 90:
            return "ahora mismo"
        if seconds < 3600:
            return f"hace {seconds // 60} min"
        if seconds < 86400:
            return f"hace {seconds // 3600} h"
        return f"hace {seconds // 86400} d"


class FileCache:
    """Cache JSON en disco, indexada por clave arbitraria."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # La clave puede ser una URL larga: se usa su hash como nombre de fichero,
        # pero se conserva la clave dentro para poder depurar.
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self.root / f"{digest}.json"

    def path_for(self, key: str) -> Path:
        """El fichero de una clave, exista o no (para mirar su fecha sin leerlo)."""
        return self._path(key)

    def get(self, key: str) -> CachedPayload | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None  # cache corrupta: se trata como ausente, nunca como error
        return CachedPayload(
            data=raw["data"],
            fetched_at=datetime.fromisoformat(raw["fetched_at"]),
            source=raw["source"],
            from_cache=True,
        )

    def put(self, key: str, data: Any, source: str) -> CachedPayload:
        """Guarda una entrada de una vez: quien lee ve la de antes o la nueva, nunca media.

        POR QUE NO `write_text` (decimoseptima ronda): escribir encima del fichero lo deja a
        medias mientras dura la escritura, y un fallo de disco a mitad lo deja a medias para
        siempre. Una lectura simultanea (la cobertura de `/api/status` mientras precarga
        `POST /api/comms/preload`) veia JSON roto y daba ese dia por ausente. Ahora se escribe en
        un temporal de la misma carpeta (`.tmp`, que nadie lee como entrada) y se sustituye con
        `os.replace`, atomico en el mismo volumen; si algo falla, el temporal se borra y la
        entrada queda como estaba. Sin `fsync`: tras un corte de corriente una entrada vacia o
        rota se lee como ausente (`get`), no como un dato.
        """
        fetched_at = datetime.now(UTC)
        payload = {
            "key": key,
            "source": source,
            "fetched_at": fetched_at.isoformat(),
            "data": data,
        }
        text = json.dumps(payload, ensure_ascii=False)
        path = self._path(key)
        handle, temporary = tempfile.mkstemp(dir=self.root, prefix=f".{path.stem}.", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(text)
            os.chmod(temporary, _FILE_MODE)
            _replace(temporary, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
            raise
        return CachedPayload(data=data, fetched_at=fetched_at, source=source, from_cache=False)

    def clear(self) -> int:
        removed = 0
        for path in self.root.glob("*.json"):
            path.unlink()
            removed += 1
        # Los temporales que dejara un corte a mitad de `put` (un proceso matado o sin
        # corriente: ahi no llega la limpieza) no son entradas: se borran sin contarlos.
        for path in self.root.glob(".*.tmp"):
            with contextlib.suppress(OSError):
                path.unlink()
        return removed


class OfflineDataUnavailable(RuntimeError):
    """No hay red y el dato no esta en cache.

    Es un fallo explicito a proposito: preferible a una espera indefinida o a
    presentar un valor inventado.
    """
