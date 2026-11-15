# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dos analíticas que dicen cosas distintas del mismo dato (`incongruencias_caso` de Polaris).

Por qué existe: el mismo análisis puede llegar dos veces (el informe del laboratorio y una copia
que alguien trae, o dos laboratorios de la misma extracción) y con una cifra distinta. Si nadie
las cruza, cada una se confirma por su lado y la serie tiene dos verdades del mismo día. Polaris
lo resolvió para su caso (el mismo bloque de biopsia informado tres veces con cifras distintas):
mismo dato de la misma muestra con valores distintos es una INCONGRUENCIA, y se avisa.

Se usa su `analizar()` tal cual. Lo que cambia es qué le llega, con sus propias costuras,
sustituidas durante la llamada y bajo cerrojo (la copia no se toca):

* **Muestra** (`muestra_de`): en EMMA, la sangre de un día. Dos fechas distintas no son la misma
  muestra: que la glucosa cambie de un día a otro es fisiología, no una contradicción. Su
  "heterogeneidad entre muestras" no se usa por eso.
* **Extracción** (`extraer`): las lecturas ya estructuradas del informe (`app/reports/labs.py`),
  no su texto, con la fecha de extracción que trae el informe. Un informe sin fecha legible no se
  compara (no se sabe de qué extracción es) y se cuenta aparte.
* **Diferencia** (`_distintos`): la suya da 5 **puntos** de margen solo a los porcentajes
  («45%» frente a «48%», pensada para inmunohistoquímica); cualquier otra cifra la compara como
  texto, así que «92» frente a «92.4» (dos laboratorios que redondean distinto) sería una
  incongruencia. Comprobado el 2026-10-04. Aquí, relativa al valor: más de un 5 % (parámetro de
  diseño, `RELATIVE_TOLERANCE`); creatinina 0,9 frente a 1,3 sigue avisando.

Avisa, no decide cuál es la buena: eso lo resuelve una persona con los dos papeles delante.

Licencia y origen (AGPL §5a): usa `polaris/tools/incongruencias_caso.py` de la copia literal de
Polaris, sin modificarla (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de
Polaris, «Beyond the Protocol»); se carga con `app.polaris.load`. De EMMA: las tres costuras de
arriba (`muestra_de`, `extraer`, `_distintos`), sustituidas durante la llamada.
"""

from __future__ import annotations

import threading
from functools import cache
from typing import Any

from app import polaris

_LOCK = threading.Lock()
RELATIVE_TOLERANCE = 0.05


@cache
def _tool() -> Any:
    return polaris.load("incongruencias_caso")


def _differ(a: str, b: str) -> bool:
    """Más de un 5 % de diferencia relativa (o textos distintos, si no son cifras)."""
    try:
        x, y = float(a), float(b)
    except ValueError:
        return a != b
    scale = max(abs(x), abs(y))
    return scale > 0 and abs(x - y) / scale > RELATIVE_TOLERANCE


def _documents(reports: list[dict[str, Any]]) -> tuple[
    list[tuple[str, str, bool, str]], dict[str, dict[str, str]], dict[str, str]
]:
    """Los documentos con la forma de Polaris y lo que sus costuras devolverán por documento."""
    docs: list[tuple[str, str, bool, str]] = []
    values: dict[str, dict[str, str]] = {}
    samples: dict[str, str] = {}
    for report in reports:
        found = report.get("lab_readings") or {}
        readings = found.get("readings") or []
        if not readings:
            continue
        index = int(report["ledger_index"])
        day = str(found.get("date") or "")
        if not day:
            continue  # sin fecha no se sabe de qué extracción es: no se compara
        name = f"informe:{index}"
        docs.append((name, day, False, name))
        samples[name] = f"sangre {day}"
        values[name] = {
            str(item["key"]): f"{float(item['value']):g}"
            for item in readings if item.get("comparator") is None
        }
    return docs, values, samples


def undated(reports: list[dict[str, Any]]) -> int:
    """Informes con lecturas pero sin fecha de extracción legible: no se pueden cruzar."""
    return sum(
        1 for report in reports
        if ((report.get("lab_readings") or {}).get("readings")
            and not (report.get("lab_readings") or {}).get("date"))
    )


def find(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Las incongruencias entre analíticas de la misma extracción, con su `analizar`."""
    docs, values, samples = _documents(reports)
    if len(docs) < 2:
        return []
    tool = _tool()
    with _LOCK:
        saved = (tool.muestra_de, tool.extraer, tool._distintos)
        tool.muestra_de = lambda text, name: samples[name]
        tool.extraer = lambda text: values[text]
        tool._distintos = _differ
        try:
            result = tool.analizar(docs)
        finally:
            tool.muestra_de, tool.extraer, tool._distintos = saved
    return [
        {
            "key": item["marcador"],
            "sample": item["muestra"],
            "readings": [
                {"value": float(reading["valor"]), "date": reading["fecha"],
                 "report": reading["documento"]}
                for reading in item["lecturas"]
            ],
        }
        for item in result["incongruencias"]
    ]
