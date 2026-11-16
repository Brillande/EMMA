"""Solo se habla con EMMA por loopback: nombre de host y origen de quien escribe.

POR QUÉ EXISTE
--------------
El backend escucha en 127.0.0.1 y no tiene usuarios: la frontera es «estar en esta máquina».
Una página cualquiera del navegador de la tripulación puede saltarla con *DNS rebinding*: su
nombre (`ataque.example`) pasa a resolver a 127.0.0.1 y, para el navegador, sus peticiones son
de mismo origen. Puede leer las respuestas y poner `X-EMMA-Console`, así que la cabecera de
consola (`api/console_header.py`) no la frena: podía pedir `/api/app-update/check`, `/download` e
`/install` (instalar la última versión y reiniciar EMMA) o activar el modo seguro. Hallazgo
`emma:api:dns-rebinding-no-host-allowlist` de la auditoría run-2, cerrado por orden de Ellande
(2026-11-16: «busca fallos … para arreglar lo que encuentres»).

Dos comprobaciones, en este orden, antes que nada más:

1. **Host.** La cabecera `Host` tiene que nombrar loopback (`127.0.0.1`, `localhost`, `[::1]`;
   cualquier puerto) o el host fijo de las pruebas (`testserver`). Con rebinding el navegador
   manda el nombre del atacante: se rechaza con 400. Es lo que decide; lo demás es defensa en
   profundidad.
2. **Origin en lo que escribe.** Un método que no sea GET, HEAD u OPTIONS que llegue con
   `Origin` ajeno a loopback se rechaza con 403. Sin `Origin` pasa: así llaman el arranque de
   escritorio (`desktop/main.cjs`), el puente de Marplanner y `curl`, que no son navegadores.

Va como ASGI puro y por fuera de CORS, para que una petición rechazada no llegue a ninguna ruta.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any
from urllib.parse import urlsplit

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
App = Callable[[Scope, Receive, Send], Awaitable[None]]

# Los nombres con que se llega a EMMA en esta máquina. `testserver` es el que pone el
# `TestClient` de Starlette: solo existe dentro del proceso de pruebas.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "testserver"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def host_name(value: str) -> str | None:
    """El nombre de `host[:puerto]` (IPv6 entre corchetes), en minúsculas; mal formado, None."""
    value = value.strip().lower()
    if not value:
        return None
    if value.startswith("["):
        end = value.find("]")
        if end < 0:
            return None
        rest = value[end + 1:]
        if rest and not (rest.startswith(":") and rest[1:].isdigit()):
            return None
        return value[1:end]
    name, sep, port = value.partition(":")
    if sep and not port.isdigit():
        return None
    return name or None


def is_loopback_host(value: str) -> bool:
    return host_name(value) in LOOPBACK_HOSTS


def is_loopback_origin(value: str) -> bool:
    """`Origin` de una página servida por loopback (la consola, Vite en :5173)."""
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and is_loopback_host(parts.netloc)


class HostGuardMiddleware:
    def __init__(self, app: App) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1").lower(): val.decode("latin-1")
            for key, val in scope.get("headers", [])
        }
        if not is_loopback_host(headers.get("host", "")):
            await _refuse(send, scope, 400, "Host no permitido: EMMA solo atiende por loopback")
            return
        origin = headers.get("origin")
        method = str(scope.get("method", "GET")).upper()
        is_write = scope["type"] == "websocket" or method not in SAFE_METHODS
        if origin is not None and is_write and not is_loopback_origin(origin):
            await _refuse(send, scope, 403, "Origen no permitido para escribir en EMMA")
            return
        await self.app(scope, receive, send)


async def _refuse(send: Send, scope: Scope, status: int, detail: str) -> None:
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": 1008})
        return
    body = ('{"detail":"' + detail + '"}').encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
    })
    await send({"type": "http.response.body", "body": body})
