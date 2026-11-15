# SPDX-License-Identifier: AGPL-3.0-or-later
"""Qué hay de Polaris en esta instalación: qué carga, para qué sirve, qué usa EMMA y qué se cambió.

Por qué existe: la copia viaja como ficheros que se importan en ejecución, y en el backend
congelado nada garantiza que carguen igual que en desarrollo (faltaría un módulo de la
biblioteca estándar que PyInstaller no vio). Esta ruta de solo lectura lo dice en la máquina
donde corre, y es la prueba de humo del instalador. Para decirlo importa cada herramienta, menos
las que hacen algo solo con importarse (`polaris.NOT_IMPORTED`): esas salen como «no se importa»,
con su motivo, porque una ruta de solo lectura no puede lanzar nada.

Y porque es código de terceros dentro de un sistema de salud: quien opera EMMA tiene que poder
ver, sin abrir el repositorio, de qué commit se copió, qué piezas llama EMMA de verdad y cuáles
solo viajan con ellas, y qué se modificó respecto del original (AGPL §5a). Todo sale de los
ficheros de la copia tal cual (`ADOPTADO.txt`, `tools/fichas/`, `CAMBIOS.json`): aquí no se
redacta ni se resume nada. Lo que falte se dice en `faltan` en vez de romper: el instalador no
lleva las fichas ni `ADOPTADO.txt` (`packaging/freeze.py`), y la ruta tiene que responder igual.
Un fichero que está pero no se deja leer (JSON roto, `ADOPTADO.txt` sin su línea `commit <sha>`)
cuenta como que falta: lo que no se puede enseñar tal cual no se enseña a medias.

«En uso» es un dato declarado, `EMMA_USES`, y no una lectura de las fuentes en ejecución: en el
backend congelado `app/` va compilado y no hay `.py` que leer. La lista viaja como código y
`tests/test_polaris_bridge.py` la ata, con `ast`, a los `load("…")` reales de `backend/app`: una
herramienta nueva sin declarar, o declarada sin usarse, hace fallar la prueba.

Licencia y origen (AGPL §5a): este fichero no contiene código de Polaris. Enseña el inventario de
la copia literal `polaris/tools/` (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la
autora de Polaris, «Beyond the Protocol») que da `app.polaris.inventory`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from app import polaris
from app.core import i18n

polaris_router = APIRouter(prefix="/polaris")

# Las herramientas de la copia que el código de EMMA pide por su nombre (`polaris.load("…")`, y
# `load`/`_tool` dentro de sus envoltorios). Las demás viajan porque alguna de estas las importa
# o porque se copiaron con su grupo (`polaris/ADOPTADO.txt`), pero EMMA no las llama.
EMMA_USES: tuple[str, ...] = (
    "_net",
    "anticipa",
    "atascos",
    "biomarcadores",
    "borde",
    "canarios",
    "cascada_mapa",
    "cronica",
    "cumbre",
    "decision_alto_riesgo",
    "deid",
    "dosier_invariantes",
    "estado_rutina",
    "frescura_dosier",
    "fuente_clinica",
    "guarda_memoria",
    "honestidad_lint",
    "identidad_paciente",
    "incongruencias_caso",
    "kb",
    "local",
    "md_to_pdf_pro",
    "ocr_informes",
    "paso_consolidacion",
    "score_local",
    "seguimiento",
    "sintomas",
    "soporte_cita",
    "tier_evidencia",
    "verifica_citas",
    "visor3d",
    "visor3d_superpone_focos",
)


def _copy_root() -> Path:
    """La copia cuyos ficheros de procedencia se enseñan (`ADOPTADO.txt`, fichas, cambios)."""
    return polaris.root()


def _read_json(path: Path) -> Any:
    """El JSON de un fichero opcional de la copia, o `None` si falta o no se puede leer."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _adopted_commit(root: Path) -> str | None:
    """El commit de Polaris del que se copió: la línea `commit <sha>` de `ADOPTADO.txt`."""
    try:
        lines = (root / "ADOPTADO.txt").read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return None
    for line in lines:
        parts = line.split()
        if len(parts) == 2 and parts[0] == "commit":
            return parts[1]
    return None


def _card(root: Path, name: str) -> dict[str, str] | None:
    """La ficha de una herramienta tal cual la escribió su autora, o `None` si no tiene."""
    card = _read_json(root / "tools" / "fichas" / f"{name}.py.json")
    if not isinstance(card, dict):
        return None
    return {str(key): value for key, value in card.items() if isinstance(value, str)}


def _changes(root: Path) -> list[dict[str, Any]] | None:
    """Los cambios decididos sobre la copia (`CAMBIOS.json`): dónde, cuándo y por qué."""
    changes = _read_json(root / "CAMBIOS.json")
    if not isinstance(changes, list):
        return None
    listed = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        replacements = change.get("reemplazos")
        listed.append(
            {
                "ruta": change.get("ruta"),
                "fecha": change.get("fecha"),
                "motivo": change.get("motivo"),
                "reemplazos": len(replacements) if isinstance(replacements, list) else 0,
            }
        )
    return listed


def _state(tool: polaris.ToolStatus) -> str:
    """El estado de una herramienta, con las palabras que la consola enseña tal cual.

    Tres y no dos: de la que el inventario no importa (`polaris.NOT_IMPORTED`) no se sabe si
    cargaría, y llamarla «no carga» sería afirmar un fallo que nadie ha visto.
    """
    if i18n.current() == "en":
        if not tool.imported:
            return "not imported"
        return "loads" if tool.loads else "does not load"
    if not tool.imported:
        return "no se importa"
    return "carga" if tool.loads else "no carga"


@polaris_router.get("/estado")
def status() -> dict[str, Any]:
    tools = polaris.inventory()
    failing = [tool for tool in tools if tool.imported and not tool.loads]
    skipped = [tool for tool in tools if not tool.imported]
    root = _copy_root()
    commit, changes = _adopted_commit(root), _changes(root)
    missing = [
        label
        for label, absent in (
            ("polaris/ADOPTADO.txt", commit is None),
            ("polaris/tools/fichas", not (root / "tools" / "fichas").is_dir()),
            ("polaris/CAMBIOS.json", changes is None),
        )
        if absent
    ]
    return {
        "origen": "polaris/ORIGEN.md",
        "commit": commit,
        # Los tres recuentos suman `total`: cargan, no cargan y no se importan.
        "cargan": len(tools) - len(failing) - len(skipped),
        "total": len(tools),
        "en_uso": sum(1 for tool in tools if tool.name in EMMA_USES),
        "no_cargan": [{"herramienta": t.name, "motivo": t.reason} for t in failing],
        "no_se_importan": [{"herramienta": t.name, "motivo": t.reason} for t in skipped],
        "herramientas": [
            {
                "herramienta": tool.name,
                # `None`: no se ha intentado importar, así que no hay un sí ni un no que dar.
                "carga": tool.loads if tool.imported else None,
                "estado": _state(tool),
                "motivo": tool.reason,
                "en_uso": tool.name in EMMA_USES,
                "ficha": _card(root, tool.name),
            }
            for tool in tools
        ],
        "cambios": changes or [],
        "faltan": missing,
    }
