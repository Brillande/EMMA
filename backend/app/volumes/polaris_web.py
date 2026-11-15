# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sirve el visor web de Polaris, copiado tal cual, con los datos de una segmentación de EMMA.

El visor de Polaris (`polaris/tools/visor3d_web/`, con sus colores y textos cambiados) lee rutas
relativas: `./indice.json`, `./<fecha>/estudio.json` y los volúmenes y mallas de esa carpeta. En
Polaris las monta `visor3d.py visor` en disco; aquí salen del binario firmado del ledger, así que
el visor ve exactamente lo que el ledger guarda. Este módulo es solo ese pegamento: traduce el
resumen de EMMA (que heredó el formato de Polaris y renombró dos campos) al `estudio.json` que
espera `main.js`, sin tocar el código copiado.

Licencia y origen (AGPL §5a): este fichero no contiene código de Polaris. Sirve el visor de
`polaris/tools/visor3d_web/` de la copia (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later,
© 2026 la autora de Polaris, «Beyond the Protocol»), compilado en `app/data/polaris_web/` por
`frontend/scripts/build-polaris.mjs`. Los cambios decididos a ese visor (colores y textos) están
en `polaris/CAMBIOS.json`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

WEB_DIR = Path(__file__).resolve().parents[1] / "data" / "polaris_web"
# Una sola "fecha" por segmentación: el visor la muestra en su selector y en el resumen.
FOLDER = "estudio"
STATIC = {
    "index.html": "text/html; charset=utf-8",
    "bundle.js": "text/javascript; charset=utf-8",
    "render.html": "text/html; charset=utf-8",
    "render.bundle.js": "text/javascript; charset=utf-8",
}


def index() -> dict[str, Any]:
    return {"fechas": [FOLDER]}


def study(summary: dict[str, Any], ledger_index: int) -> dict[str, Any]:
    """El `estudio.json` de Polaris a partir del resumen de EMMA.

    Renombres: `region` → `segmento` en cada lesión, `estructuras` → `mallas` (clave → fichero),
    `volumen_organo_ml` → `volumen_higado_ml`, `volumen_lesiones_ml` → `volumen_tumoral_ml`.
    """
    meshes = {
        item["key"]: item["malla"]
        for item in summary.get("estructuras", [])
        if item.get("malla")
    }
    lesions = [
        {**lesion, "segmento": lesion.get("region")} for lesion in summary.get("lesiones", [])
    ]
    return {
        "fecha": f"asiento {ledger_index}",
        "modalidad": summary.get("modalidad", "CT"),
        "voxel_mm": summary.get("voxel_mm"),
        "ventana_hu": summary["ventana_hu"],
        "volumen_higado_ml": summary.get("volumen_organo_ml"),
        "volumen_tumoral_ml": summary.get("volumen_lesiones_ml"),
        "lesiones": lesions,
        "mallas": meshes,
    }
