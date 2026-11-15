# SPDX-License-Identifier: AGPL-3.0-or-later
"""Activa el pegamento de `_lock` en los procesos de las pruebas de Polaris, en Windows.

Por qué existe: `test_lock_dueno` y `test_seguimiento_carrera` de la copia importan `_lock` en
procesos propios (y la segunda, en doce procesos hijos), sin pasar por EMMA: no hay dónde llamar a
`winlock.install`. Python importa `sitecustomize` al arrancar si lo encuentra en su ruta, y
`scripts/polaris_tests.py` ya pone esta carpeta en `PYTHONPATH` en Windows (por `fcntl` y
`resource`), que los hijos heredan. Con eso basta, sin tocar la copia ni las pruebas.

Dentro de EMMA este fichero no hace nada: `app/polaris` añade esta carpeta a `sys.path` con el
intérprete ya arrancado, cuando `sitecustomize` ya no se busca.

Licencia y origen (AGPL §5a): este fichero no contiene código de Polaris; es pegamento de EMMA
para la copia literal (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de
Polaris, «Beyond the Protocol»), que no se modifica.
"""

import sys

if sys.platform == "win32":
    import winlock

    winlock.hook()
