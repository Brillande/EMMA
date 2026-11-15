# SPDX-License-Identifier: AGPL-3.0-or-later
"""El dosier de evidencia de EMMA, comprobado con las reglas de Polaris.

Por qué existe: la evidencia de EMMA vive en tres JSON (`countermeasures.json`,
`measurement_cost.json`, `evidence_tiers.json`) que valida cada uno su cargador, a su manera.
Nadie comprobaba lo que Polaris exige a un dosier: piezas con un esquema cerrado, ninguna
contradicción (dos piezas vivas con el mismo id), "alta" solo con fuente, y **frescura**: una
pieza revisada hace más de su vigencia no puede respaldar nada.

Se usan tal cual, desde la copia (`polaris/tools/`): `dosier_invariantes._schema_pieza` y
`_invariantes` y `frescura_dosier.evaluar_frescura`. No se usa `dosier_invariantes.evaluar()`
entero: arrastra el cotejo y la elegibilidad de ensayos del caso oncológico de su autora.

El canario de `guardian_evals` (un dosier malo conocido que tiene que salir siempre no entregable)
no se carga aquí: lo usa la prueba (`tests/test_evidence_dossier.py`) para comprobar que
`evaluate` lo bloquea. En ejecución el dosier no se comprueba a sí mismo con él.

La traducción a piezas es de EMMA. `ttl_dias` (vigencia de una revisión) es un parámetro de
diseño: 365 días.

Licencia y origen (AGPL §5a): usa `polaris/tools/dosier_invariantes.py` y
`polaris/tools/frescura_dosier.py` de la copia literal de Polaris, sin modificarla (commit en
`polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the Protocol»); se
cargan con `app.polaris.load`. El canario de `polaris/tools/guardian_evals.py` lo carga su prueba
(`tests/test_evidence_dossier.py`), no este módulo. De EMMA: la traducción de los tres JSON a
piezas y la vigencia `ttl_dias`.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from app import polaris
from app.evidence import registry

DATA = Path(__file__).resolve().parents[1] / "data"
TTL_DAYS = 365
_REVIEWED = re.compile(r"Revisado el (\d{4}-\d{2}-\d{2})")


@cache
def _rules() -> Any:
    return polaris.load("dosier_invariantes")


@cache
def _freshness() -> Any:
    return polaris.load("frescura_dosier")


def _reviewed(note: str) -> str | None:
    match = _REVIEWED.search(note or "")
    return f"{match.group(1)}T00:00:00Z" if match else None


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((DATA / name).read_text(encoding="utf-8"))
    return data


def pieces() -> list[dict[str, Any]]:
    """La evidencia de EMMA como piezas del dosier de Polaris."""
    out: list[dict[str, Any]] = []
    library = _load("countermeasures.json")
    reviewed = _reviewed(str(library.get("_nota", "")))
    for item in library["countermeasures"]:
        cited = item.get("protocol_ref")
        url = registry.get(cited["ref"]).url if cited else None
        out.append({
            "id": f"contramedida:{item['id']}",
            "bloque": item["domain"],
            "afirmacion": f"{item['action']} — {item['indication']}",
            "fuentes": [url] if url else [],
            # "evidence-backed": un protocolo respalda la acción concreta. Sin firma clínica,
            # media; "demo" solo la respalda el riesgo del dominio: baja.
            "confianza": "media" if item.get("basis") == "evidence-backed" else "baja",
            "status": "vivo",
            "confirmado_en": reviewed,
            "ttl_dias": TTL_DAYS,
        })
    costs = _load("measurement_cost.json")
    reviewed = _reviewed(str(costs.get("_nota", "")))
    for key, item in costs["indicators"].items():
        basis = item.get("crew_time_basis") or "sin fuente"
        out.append({
            "id": f"coste:{key}",
            "bloque": "coste-de-medir",
            "afirmacion": f"{item['mode']} · {item.get('equipment') or 'sin equipo'}",
            "fuentes": [] if basis == "sin fuente" else [basis],
            "confianza": "baja" if basis == "sin fuente" else "media",
            "status": "vivo",
            "confirmado_en": reviewed,
            "ttl_dias": TTL_DAYS,
        })
    tiers = _load("evidence_tiers.json")
    for pmid, record in tiers["records"].items():
        out.append({
            "id": f"pmid:{pmid}",
            "bloque": "nivel-de-evidencia",
            "afirmacion": str(record.get("title") or pmid),
            "fuentes": [f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"],
            "confianza": "media",
            "status": "vivo",
            "confirmado_en": record.get("retrieved"),
            "ttl_dias": TTL_DAYS,
        })
    return out


def evaluate(items: list[dict[str, Any]], now: dt.datetime | None = None) -> dict[str, Any]:
    """Esquema, invariantes y frescura, con las funciones de Polaris. No decide nada clínico."""
    rules, freshness = _rules(), _freshness()
    schema = [
        f"«{item.get('id', '(sin id)')}»: {problem}"
        for item in items for problem in rules._schema_pieza(item)
    ]
    crossed = list(rules._invariantes(items, invariantes_dominio=[]))
    results, _fresh, stale = freshness.evaluar_frescura(items, ahora=now)
    states: dict[str, int] = {}
    for result in results:
        states[result["estado"]] = states.get(result["estado"], 0) + 1
    blocked = [*schema, *crossed, *stale]
    return {
        "pieces": len(items),
        "deliverable": not blocked,
        "by_state": states,
        "blocked": blocked,
        "ttl_days": TTL_DAYS,
    }


def status(now: dt.datetime | None = None) -> dict[str, Any]:
    """El estado del dosier de EMMA hoy (para la API, solo lectura)."""
    return evaluate(pieces(), now)
