# SPDX-License-Identifier: AGPL-3.0-or-later
"""¿Este informe es de este tripulante? Nombre y fecha de nacimiento, leídos en el propio informe.

Por qué existe: subir un informe al expediente de un tripulante no prueba que sea suyo. Un
informe de otra persona usado como propio es de los peores errores posibles, y la única señal
fiable de a quién pertenece está dentro del documento: su cabecera de filiación.

Se usa tal cual `identidad_paciente.verificar()` de Polaris (copia en `polaris/tools/`), con sus
veredictos (`coincide`, `parcial`, `no_consta`, `ambiguo`, `otro_paciente`…), su regla de que
el apellido solo no basta y su comparación de fechas por dígitos. Lo único de EMMA es de dónde
sale la identidad: Polaris la lee de un fichero local (`tools/perfil.local.json`); aquí se le
da la que el tripulante declaró en el ledger (`crew-identity`), sin escribir datos personales en
ningún fichero suelto. Decisión del usuario (2026-09-29): si el informe no es suyo, no se usa.

Licencia y origen (AGPL §5a): usa `polaris/tools/identidad_paciente.py` de la copia literal de
Polaris, sin modificarla (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de
Polaris, «Beyond the Protocol»); se carga con `app.polaris.load`. De EMMA: de dónde sale la
identidad (el ledger, no un fichero local).
"""

from __future__ import annotations

import datetime as dt
import threading
from dataclasses import dataclass
from functools import cache
from typing import Any

from app import polaris

# `verificar()` pregunta a `titular()` del módulo; se le sustituye durante la llamada. El cerrojo
# evita que dos subidas a la vez se crucen las identidades.
_LOCK = threading.Lock()


@dataclass(frozen=True)
class Declared:
    given_name: str
    surnames: str
    birth_date: dt.date


@cache
def _original() -> Any:
    return polaris.load("identidad_paciente")


def _holder(declared: Declared) -> dict[str, Any]:
    """La identidad en la forma de `titular()` de Polaris (fecha en las dos formas habituales)."""
    date = declared.birth_date
    return {
        "nombre": declared.given_name,
        "apellidos": [part for part in declared.surnames.split() if part],
        "nacimiento": [date.strftime("%d/%m/%Y"), date.isoformat()],
        "dob_patrones": [],
    }


def check(text: str, declared: Declared | None) -> dict[str, Any]:
    """Veredicto de Polaris y si el informe se puede usar. Nunca repite datos de otra persona."""
    original = _original()
    if declared is None:
        return {
            "verdict": "sin_identidad",
            "explanation": "el tripulante no tiene nombre y fecha de nacimiento declarados: "
            "no se puede acreditar de quién es el informe",
            "usable": True,
        }
    with _LOCK:
        saved = original.titular
        original.titular = lambda: _holder(declared)
        try:
            verdict, explanation = original.verificar(text)
        finally:
            original.titular = saved
    return {
        "verdict": str(verdict),
        "explanation": str(explanation),
        "usable": bool(original.SIRVE.get(verdict, False)),
    }
