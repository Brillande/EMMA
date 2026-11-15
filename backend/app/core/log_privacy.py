"""Lo que EMMA escribe en el log no lleva contenido personal.

Por qué existe: la especificación del equipo (§12) pide «evitar guardar contenido personal
innecesario en los logs», y el log de EMMA no es efímero. La aplicación de escritorio vuelca la
salida del backend a `backend.log`, en el perfil del usuario, y ese fichero sobrevive a la sesión
y no pasa por el ledger ni por la des-identificación: lo que caiga ahí queda en claro. Las pocas
líneas propias ya eran prudentes (`volumes/privacy.py` anota solo el tipo de la excepción), pero
la regla dependía de que cada autor se acordara, y los dos caminos con más riesgo no los escribe
EMMA: la traza de una excepción y la línea de acceso de uvicorn.

INVENTARIO (auditado el 2026-10-09; la prueba de guardia de `tests/test_logs_privacy.py` falla si
aparece una línea de log nueva que no encaje en él)

  1. Trazas de excepción. `log.exception` en `api/volumes.py` (trabajo de segmentación),
     `volumes/geometry.py`, `volumes/spine.py` (dos) y `volumes/skeleton_view.py`; y, sobre todo,
     la de uvicorn para cualquier excepción no prevista de cualquier ruta («Exception in ASGI
     application»). Una traza estándar acaba con el MENSAJE de la excepción, y el mensaje repite
     el dato que falló: un error de validación de pydantic cita el valor recibido, uno de
     nibabel puede citar un campo de la cabecera, uno de E/S cita la ruta (con el nombre de
     usuario de Windows dentro). Las rutas de fichero de cada marco llevan ese mismo nombre.
  2. Líneas de acceso de uvicorn (nivel INFO): método, ruta y CADENA DE CONSULTA. En EMMA la
     consulta lleva `subject` (el tripulante), `recorded_by` (quién registra, texto libre) y `q`
     (lo que se busca en la base de conocimiento, texto libre). La aplicación de escritorio
     arranca uvicorn en nivel `warning` (`desktop_entry.py`) y no las escribe; en desarrollo
     (`python -m uvicorn`) sí salen.
  3. Mensajes propios con argumentos: el identificador de un trabajo de segmentación, un índice
     de asiento del ledger, un tiempo en milisegundos y el tipo de una excepción. Ninguno es
     contenido personal.
  4. Lo que NO llega al log por ningún camino propio: el cuerpo de una petición, el texto de un
     informe, la identidad declarada del tripulante, su sexo declarado (`crew-sex`, desde el
     2026-11-14: va en el cuerpo del `POST` y en la respuesta del `GET /api/crew/sex`, nunca en
     su ruta ni en su consulta, que solo llevan `subject` y `until`), el valor de una
     observación. No hay nombres de fichero subidos: las subidas mandan el binario en el
     cuerpo, sin nombre.

QUÉ SE HACE, EN UN SOLO SITIO

`install()` envuelve la fábrica de registros de `logging`: todo registro del proceso —de EMMA, de
uvicorn, de una biblioteca— pasa por `scrub` antes de llegar a ningún manejador.

  * La traza se reduce a tipo y lugar: fichero (sus dos últimos componentes), línea y función de
    cada marco, y el TIPO de la excepción y de sus causas. El mensaje no se registra. Es lo
    necesario para diagnosticar dónde falló y qué clase de fallo fue; lo que se pierde es el
    porqué concreto cuando estaba en el mensaje. De un `OSError` se conserva el `errno`, que es
    un número del sistema. La excepción se suelta del registro (`exc_info = None`): un
    formateador propio no puede volver a sacar el mensaje.
  * Un argumento que sea una excepción se cambia por su tipo.
  * A la línea de acceso se le quita la cadena de consulta y se deja dicho que la había.

Por eso los cinco `log.exception` del inventario se quedan como están: caso por caso, lo que
aportan es la traza (dónde), y el mensaje —lo único que podía llevar un dato— ya no sale.

LO QUE NO CUBRE (dicho, no escondido)

  * Un texto que alguien meta ya formateado en el mensaje (`log.info(f"...{dato}")`): eso lo
    impide la prueba de guardia sobre el código de EMMA, no esta fábrica. Una biblioteca de
    terceros que lo haga no está cubierta.
  * Lo que se escribe sin `logging`: un `print`, o la traza de un fallo al importar la aplicación
    (antes de que exista ninguna petición, así que sin datos de nadie). La prueba de guardia
    prohíbe `print` en `app/`.
  * Un fallo del arranque (`lifespan`) llega a uvicorn como texto ya formateado; EMMA no tiene
    hoy `lifespan`.
  * La ruta sí se registra, con sus índices de asiento. No lleva identificadores de tripulante.
"""

from __future__ import annotations

import logging
import traceback
from pathlib import PurePath
from types import TracebackType
from typing import Any

ACCESS_LOGGER = "uvicorn.access"
# Posición de la ruta en los argumentos de la línea de acceso de uvicorn:
# '%s - "%s %s HTTP/%s" %d' (cliente, método, ruta con consulta, versión, estado).
ACCESS_PATH_ARG = 2
QUERY_OMITTED = "?[consulta omitida]"
TRACE_HEADER = "Traza reducida a tipo y lugar (el mensaje de la excepción no se registra):"
# Tope de excepciones encadenadas que se anotan. Diseño de EMMA: acota la traza y cualquier ciclo.
MAX_CHAIN = 5
_MARK = "_emma_log_privacy"

ExcInfo = tuple[type[BaseException] | None, BaseException | None, TracebackType | None]


def strip_query(path: str) -> str:
    """La ruta sin su cadena de consulta, diciendo que la había."""
    head, mark, _ = path.partition("?")
    return head + QUERY_OMITTED if mark else head


def _place(filename: str) -> str:
    """Los dos últimos componentes: sitúan el módulo sin la carpeta personal del usuario."""
    return "/".join(PurePath(filename).parts[-2:])


def _kind(exc: BaseException) -> str:
    name = type(exc).__name__
    errno = getattr(exc, "errno", None)
    if isinstance(exc, OSError) and isinstance(errno, int):
        return f"{name} (errno {errno})"
    return name


def _cause(exc: BaseException) -> BaseException | None:
    if exc.__cause__ is not None:
        return exc.__cause__
    return None if exc.__suppress_context__ else exc.__context__


def safe_trace(exc: BaseException) -> str:
    """Tipo y lugar de una excepción y de sus causas. Nunca su mensaje."""
    lines = [TRACE_HEADER]
    current: BaseException | None = exc
    seen: set[int] = set()
    # El tope va por vueltas, no por excepciones vistas: acota también un ciclo de causas.
    for depth in range(MAX_CHAIN):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        if depth:
            lines.append("causada por:")
        # `lookup_lines=False`: la línea de código no hace falta y obliga a leer el fichero.
        frames = traceback.StackSummary.extract(
            traceback.walk_tb(current.__traceback__), lookup_lines=False
        )
        lines.extend(
            f"  {_place(frame.filename)}:{frame.lineno} en {frame.name}" for frame in frames
        )
        lines.append(_kind(current))
        current = _cause(current)
    return "\n".join(lines)


def _safe_arg(value: Any) -> Any:
    return type(value).__name__ if isinstance(value, BaseException) else value


def scrub(record: logging.LogRecord) -> logging.LogRecord:
    """Deja el registro sin mensaje de excepción ni cadena de consulta, y lo devuelve."""
    info = record.exc_info
    if info:
        exc = info[1] if isinstance(info, tuple) else None
        if exc is not None:
            record.exc_text = safe_trace(exc)
        record.exc_info = None
    args = record.args
    if isinstance(args, tuple):
        cleaned = [_safe_arg(value) for value in args]
        if (
            record.name == ACCESS_LOGGER
            and len(cleaned) > ACCESS_PATH_ARG
            and isinstance(cleaned[ACCESS_PATH_ARG], str)
        ):
            cleaned[ACCESS_PATH_ARG] = strip_query(cleaned[ACCESS_PATH_ARG])
        record.args = tuple(cleaned)
    elif isinstance(args, dict):
        record.args = {key: _safe_arg(value) for key, value in args.items()}
    return record


def installed() -> bool:
    return bool(getattr(logging.getLogRecordFactory(), _MARK, False))


def install() -> None:
    """Hace pasar por `scrub` todo registro de log del proceso. Llamarlo dos veces no anida."""
    if installed():
        return
    previous = logging.getLogRecordFactory()

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        return scrub(previous(*args, **kwargs))

    setattr(factory, _MARK, True)
    logging.setLogRecordFactory(factory)
