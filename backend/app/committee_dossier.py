# SPDX-License-Identifier: AGPL-3.0-or-later
"""El comité de verificadores en un solo dosier: `paso_consolidacion.consolidar` de Polaris.

Por qué existe: un borrador lo revisan varios modelos locales y las barreras deterministas. Quien
firma recibía sus objeciones sueltas, una lista por modelo, y tenía que juntarlas. Polaris escribió
el consolidador para lo mismo con sus subagentes: ordena por impacto, pone lo que pasa del tope en
"diferidas" (a la vista, nunca se tira) y avisa de cada decisión sin fuente trazable.

Se usa su `consolidar()` tal cual. Lo que EMMA le da:
* una contribución por verificador (el modelo), y una de "barreras deterministas" (cifras que no
  están en los hechos, lenguaje bloqueado, secciones vacías);
* cada objeción que cuenta (cita una frase del borrador): impacto `critica`, fuente = la cita;
* cada objeción descartada (sin cita válida): `media`, fuente "?", que su consolidador marca como
  SIN fuente trazable.

No se usa su `render()`: escribe en la voz de su autora ("TL;DR", "acciones para ti",
"recomendación"), que en EMMA sonaría a orden. La interfaz enseña la estructura. Es el borrador
de Clase C: no entra en el análisis ni en una alerta (invariante 6).

Licencia y origen (AGPL §5a): usa `polaris/tools/paso_consolidacion.py` de la copia literal de
Polaris, sin modificarla (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de
Polaris, «Beyond the Protocol»); se carga con `app.polaris.load`. De EMMA: las contribuciones que
se le dan y la decisión de no usar su `render()`.
"""

from __future__ import annotations

from functools import cache
from typing import Any

from app import polaris

DETERMINISTIC = "barreras deterministas"


@cache
def _tool() -> Any:
    return polaris.load("paso_consolidacion")


def dossier(draft: dict[str, Any]) -> dict[str, Any] | None:
    """El dosier de un borrador guardado, o None si es de antes de guardar las objeciones."""
    objections = draft.get("objections")
    if not isinstance(objections, list):
        return None
    by_model: dict[str, list[dict[str, Any]]] = {}
    for item in objections:
        by_model.setdefault(str(item.get("model") or "?"), []).append({
            "titulo": str(item.get("reason") or "(sin motivo)"),
            "impacto": "critica" if item.get("counted") else "media",
            "porque": str(item.get("quote") or ""),
            "fuente": str(item.get("quote") or "") if item.get("counted") else "?",
        })
    contributions = [{"agente": model, "decisiones": items} for model, items in by_model.items()]
    barriers = [
        reason for reason in draft.get("reasons") or []
        if not str(reason).startswith("el verificador ")
    ]
    if barriers:
        contributions.append({
            "agente": DETERMINISTIC,
            "decisiones": [{"titulo": str(reason), "impacto": "critica", "fuente": DETERMINISTIC}
                           for reason in barriers],
        })
    _intent, head, deferred, _actions, warnings, orphans = _tool().consolidar(
        {"intencion": "revisión del borrador", "contribuciones": contributions}
    )

    def plain(item: dict[str, Any]) -> dict[str, Any]:
        return {"title": item.get("titulo"), "impact": item.get("impacto"),
                "quote": item.get("porque") or None, "source": item.get("_fuente")}

    return {
        "committee": list(draft.get("committee") or []),
        "head": [plain(item) for item in head],
        "deferred": [plain(item) for item in deferred],
        "warnings": list(warnings),
        "untraceable": bool(orphans),
    }
