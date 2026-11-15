# SPDX-License-Identifier: AGPL-3.0-or-later
"""Un solo cerrojo para capturar lo que Polaris escribe por consola.

Por qué existe: las herramientas de Polaris son guiones de terminal y hablan con `print`. EMMA las
llama desde un servidor, y a tres de ellas hay que quitarles la consola: `kb.build()` imprime
emojis que en Windows (cp1252) rompen el índice, `md_to_pdf_pro.main()` imprime una ruta que no le
sirve a nadie, y de `visor3d._revisa_cadena` EMMA LEE lo que imprime, porque no devuelve nada.

`contextlib.redirect_stdout` no redirige «la consola de esta llamada»: cambia `sys.stdout`, que es
de todo el proceso, y al salir repone lo que encontró al entrar. Cada adaptador lo hacía bajo su
propio cerrojo (`kb._LOCK`, `export._LOCK`, `spine._console`), y las tres rutas corren en hilos
del threadpool de FastAPI. Con cerrojos distintos, dos capturas se solapan y pasan dos cosas:

  * El texto cae en el búfer equivocado. Si un PDF se exporta mientras se revisa una cadena
    vertebral, lo que Polaris dice de la columna acaba en el búfer del PDF; el control no
    encuentra los niveles reconocidos a medias, o sale «no revisada», y ese bloque va al resumen
    FIRMADO de la segmentación.
  * La consola no vuelve. Si A entra, B entra y A sale antes que B, B repone al salir el búfer de
    A: `sys.stdout` se queda apuntando a un `StringIO` que ya nadie lee, hasta reiniciar.

Aquí hay una sola captura y un solo cerrojo. Todo adaptador que necesite quitarle la consola a
Polaris usa `captured()`; ninguno llama a `redirect_stdout`/`redirect_stderr` ni asigna
`sys.stdout` por su cuenta (lo vigila `tests/test_polaris_console.py`).

**Orden de toma de cerrojos** (para que no haya interbloqueo): primero el propio del adaptador
(`kb._LOCK`, `export._LOCK`: protegen sus sustituciones de atributos), DESPUÉS este. El de consola
es siempre el más interno: dentro de `captured()` no se toma el cerrojo de ningún adaptador ni se
llama a otro adaptador que lo tome. Es reentrante por si una función de Polaris capturada llama a
otra que EMMA también captura en el mismo hilo; en ese caso la captura interior se queda su texto
y la exterior no lo ve.

Lo que cuesta: mientras `kb` reindexa, exportar un PDF o revisar una cadena esperan. Es el precio
de que la consola sea una sola.

Lo que no cubre: un hilo que escriba por consola SIN pasar por aquí mientras otro captura (un
`print` de una herramienta de Polaris llamada sin captura, o `logging.lastResort`) deja su texto en
el búfer de quien captura. Los manejadores de log que ya guardan su flujo (los de uvicorn) no se
ven afectados.

De EMMA entero; no lleva código de Polaris.
"""

from __future__ import annotations

import contextlib
import io
import threading
from collections.abc import Iterator

_LOCK = threading.RLock()


@contextlib.contextmanager
def captured() -> Iterator[io.StringIO]:
    """Captura `stdout` y `stderr` del proceso mientras dure el bloque; da el búfer.

    El texto se lee con `getvalue()`, dentro del bloque o después. Si el bloque lanza (también
    `SystemExit`, con el que abortan las herramientas de Polaris), la consola se repone igual.
    """
    out = io.StringIO()
    with _LOCK, contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        yield out
