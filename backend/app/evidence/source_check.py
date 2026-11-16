# SPDX-License-Identifier: AGPL-3.0-or-later
"""¿La fuente que cita una firma de alto riesgo existe de verdad?

Por qué existe: en una decisión clínica de alto riesgo, cada firma puede citar la fuente en la
que se apoya (decisión del usuario, 2026-09-29). Una cita inventada o mal copiada ("PMID 12345"
que no existe) es el fallo que Polaris llama "cita FABRICADA", y el que menos se ve al leer.

Se usa tal cual `decision_alto_riesgo._existencia_citas()` de Polaris (copia en `polaris/tools/`):
estados `confirmada`, `FABRICADA`, `no_resoluble` o `n/a` (la fuente no trae un identificador
externo: una contramedida o un procedimiento de EMMA). Lo único que cambia es quién pregunta al
registro: el comprobador de EMMA (`citations.verify`, con httpx y modo sin red) en vez de
`verifica_citas` con `curl`, para que las pruebas no salgan a internet (invariante 3).

Por qué no `evaluar()` entero: exige que cada voz sea un agente del "gabinete" de su autora (lee
su catálogo de agentes) y un comprobador de esa lista; con las firmas de personas de EMMA saldría
siempre "panel incompleto" (docs/polaris-divergencias.md §8). Y, por decisión del usuario, el
resultado **no bloquea la firma**: se guarda con ella en el ledger y se enseña.

Licencia y origen (AGPL §5a): usa `polaris/tools/decision_alto_riesgo.py` de la copia literal de
Polaris, sin modificarla (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de
Polaris, «Beyond the Protocol»); se carga con `app.polaris.load`. De EMMA: el comprobador que
pregunta al registro (`citations.verify`) y que el resultado no bloquee la firma.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from app import polaris
from app.evidence import citations

Checker = Callable[[list[str]], list[dict[str, str]]]


# Lo más que se lee de un registro de citas (PubMed, Crossref, DataCite, ClinicalTrials.gov) o de
# la página de doi.org: JSON de kilobytes o HTML de cientos. Va en `egress.client(..., max_bytes=)`.
CITATION_MAX_BYTES = 8 * 1024 * 1024


def registry_checker(client: httpx.Client) -> Checker:
    """El comprobador que espera Polaris (`[{entrada, estado}]`), hecho con el de EMMA."""

    def check(tokens: list[str]) -> list[dict[str, str]]:
        out = []
        for token in tokens:
            kind, identifier = citations.classify(token)
            [verdict] = citations.verify(client, [(kind, identifier)])
            out.append({"entrada": token, "id": identifier, "estado": verdict.status})
        return out

    return check


def offline_checker(tokens: list[str]) -> list[dict[str, str]]:
    """Sin red, nadie puede confirmar ni desmentir: todo queda `no_resoluble`, sin acusar."""
    return [{"entrada": token, "estado": citations.UNRESOLVABLE} for token in tokens]


def check_source(source: str, checker: Checker) -> dict[str, Any]:
    """El estado de la fuente de una firma, con el `_existencia_citas` de Polaris."""
    if not source.strip():
        return {"estado": "sin_fuente", "detalle": "la firma no cita fuente"}
    state, detail = polaris.load("decision_alto_riesgo")._existencia_citas(source, checker)
    return {"estado": str(state), "detalle": str(detail)}
