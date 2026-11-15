"""El idioma del texto que lee la tripulación: castellano o inglés, por petición.

POR QUÉ EXISTE
--------------
EMMA se escribió en castellano de punta a punta: el backend redacta las frases y la interfaz las
enseña tal cual (invariante 7 de CLAUDE.md). Para enseñarla a un jurado anglófono hacía falta el
inglés sin perder el castellano (decisión del usuario, 2026-11-15: dos idiomas con selector), y
sin tocar tres cosas que dependen de los bytes del texto castellano: las pruebas que lo fijan, las
campañas de mutantes (cada `old` tiene que aparecer una sola vez en la fuente) y las huellas
(`rules_version()` hace hash de `countermeasures.json`).

Por eso **el literal castellano no se mueve**: el inglés se pone al lado.

- Dentro de una función, `tr("texto", "text")`.
- Una constante de módulo se queda como está y su inglés se registra aparte, `en(CONST, "text")`;
  donde se sirve, `loc(CONST)`. Así la línea de la constante sigue idéntica y quien la importa
  desde otro módulo no cambia.
- Un JSON de `app/data/` lleva un hermano `<nombre>.en.json` con `{"strings": {castellano:
  inglés}}`, que `localized()` aplica al servir. Los bytes del original no cambian.

EL IDIOMA DEL REGISTRO
----------------------
Lo que EMMA firma en el ledger no depende de quién lo lea: se escribe siempre en `RECORD_LANG`
(`record_language()`), y los identificadores y las claves no se traducen nunca
(`compliance/record-integrity.md`, «Idioma del registro»).

DOS TRAMPAS
-----------
`tr` y `loc` leen el idioma de la petición en curso: llamadas a nivel de módulo, o dentro de una
función con `functools.cache`, congelarían el idioma del primero que pasó. Para lo cacheado está
`lang_cache`. Las dos cosas las vigila `tests/test_i18n_guard.py`.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Awaitable, Callable, Iterator, Mapping, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, Literal, ParamSpec, TypeVar, cast

Lang = Literal["es", "en"]

LANGS: tuple[Lang, ...] = ("es", "en")
# El idioma en que EMMA escribe lo que firma. No es una preferencia: cambiarlo cambia los bytes
# firmados de los asientos nuevos.
RECORD_LANG: Lang = "es"
# Cómo dice su idioma una petición: la cabecera (curl, pruebas) manda sobre la cookie (la consola,
# que así no tiene que tocar ninguno de sus `fetch`, ni las imágenes ni las descargas).
HEADER = "X-EMMA-Lang"
COOKIE = "emma_lang"

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")

_default: Lang = "es"
_current: ContextVar[Lang | None] = ContextVar("emma_lang", default=None)
# Castellano → inglés de las constantes de módulo (`en`). Una cadena, un solo inglés.
_registry: dict[str, str] = {}
_conflicts: list[tuple[str, str, str]] = []


def parse(raw: str | None) -> Lang | None:
    """`es` o `en` de lo que llega en una cabecera o una cookie; otra cosa no es un idioma."""
    if raw is None:
        return None
    value = raw.strip().lower()[:2]
    return next((lang for lang in LANGS if lang == value), None)


def set_default(lang: Lang) -> None:
    """El idioma de quien no dice ninguno (`EMMA_LANG`). La suite lo fija en castellano."""
    global _default
    _default = lang


def default() -> Lang:
    return _default


def current() -> Lang:
    """El idioma de la petición en curso, o el que hay por defecto fuera de una petición."""
    return _current.get() or _default


@contextmanager
def use(lang: Lang) -> Iterator[None]:
    token = _current.set(lang)
    try:
        yield
    finally:
        _current.reset(token)


def record_language() -> Any:
    """Dentro de este bloque se escribe en el idioma del registro: lo que se va a firmar."""
    return use(RECORD_LANG)


def tr(es: str, en: str) -> str:
    """El texto en el idioma de la petición. El castellano va primero y no se toca."""
    return en if current() == "en" else es


def en(es: str, english: str) -> None:
    """Registra el inglés de una constante de módulo. Dos ingleses para un castellano, conflicto."""
    known = _registry.get(es)
    if known is not None and known != english:
        _conflicts.append((es, known, english))
        return
    _registry[es] = english


def en_many(pairs: Mapping[str, str]) -> None:
    for es, english in pairs.items():
        en(es, english)


def loc(text: str) -> str:
    """Una constante registrada con `en`, en el idioma de la petición; sin registrar, tal cual."""
    if current() != "en":
        return text
    return _registry.get(text, text)


def conflicts() -> list[tuple[str, str, str]]:
    """Castellanos registrados con dos ingleses distintos: (castellano, primero, segundo)."""
    return list(_conflicts)


def lang_cache(fn: Callable[P, R]) -> Callable[P, R]:
    """`functools.cache` con el idioma en la clave: una entrada por idioma y argumentos."""

    @functools.cache
    def keyed(_lang: Lang, *args: Any, **kwargs: Any) -> R:
        return fn(*args, **kwargs)

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return keyed(current(), *args, **kwargs)  # type: ignore[arg-type]

    wrapper.cache_clear = keyed.cache_clear  # type: ignore[attr-defined]
    return wrapper


def overlay_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}.en.json")


@functools.cache
def overlay(path: Path) -> Mapping[str, str]:
    """El inglés de un JSON de datos: su hermano `<nombre>.en.json`. Sin hermano, nada."""
    sibling = overlay_path(path)
    if not sibling.is_file():
        return {}
    strings = json.loads(sibling.read_text(encoding="utf-8"))["strings"]
    if not isinstance(strings, dict):
        raise ValueError(f"{sibling.name}: `strings` no es un objeto")
    return {str(es): str(english) for es, english in strings.items()}


def _replace(value: Any, strings: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return strings.get(value, value)
    if isinstance(value, dict):
        return {key: _replace(item, strings) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace(item, strings) for item in value]
    if isinstance(value, tuple):
        return tuple(_replace(item, strings) for item in value)
    return value


def localized(value: T, path: Path) -> T:
    """`value` (lo leído de `path`, o lo servido a partir de él) con sus cadenas en el idioma de la
    petición. Devuelve una copia: lo cacheado en castellano no se toca. Solo cambian los valores
    que son, enteros, una cadena del hermano inglés; las claves no se traducen.
    """
    if current() != "en":
        return value
    strings = overlay(path)
    if not strings:
        return value
    return cast(T, _replace(value, strings))


def missing(path: Path, value: Any, skip: Callable[[str], bool] = lambda _text: False) -> list[str]:
    """Las cadenas de `value` sin inglés en el hermano de `path`: lo que le falta a una unidad."""
    strings = overlay(path)
    found: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, str):
            if item not in strings and not skip(item) and item not in found:
                found.append(item)
        elif isinstance(item, dict):
            for inner in item.values():
                walk(inner)
        elif isinstance(item, (list, tuple)):
            for inner in item:
                walk(inner)

    walk(value)
    return found


Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def request_language(headers: list[tuple[bytes, bytes]]) -> Lang | None:
    """El idioma que pide una petición: la cabecera `X-EMMA-Lang`, o la cookie `emma_lang`."""
    cookie: str | None = None
    for name, value in headers:
        lowered = name.lower()
        if lowered == HEADER.lower().encode():
            asked = parse(value.decode("latin-1"))
            if asked is not None:
                return asked
        elif lowered == b"cookie":
            cookie = value.decode("latin-1")
    if cookie is None:
        return None
    try:
        morsel = SimpleCookie(cookie).get(COOKIE)
    except Exception:  # una cookie ajena mal escrita no decide el idioma ni tumba la petición
        return None
    return parse(morsel.value) if morsel is not None else None


class LanguageMiddleware:
    """Fija el idioma de cada petición. ASGI puro: el `ContextVar` se pone en la misma tarea que
    atiende la petición, y de ahí pasa al hilo de las rutas síncronas.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        asked = request_language(scope.get("headers") or [])
        if asked is None:
            await self.app(scope, receive, send)
            return
        with use(asked):
            await self.app(scope, receive, send)
