"""Las palabras con que se nombra un nivel y una trayectoria, para que la interfaz no las escriba.

`CLAUDE.md`: «la interfaz no redacta texto clinico: lo muestra tal cual lo da el backend». La
especificacion (§4) pide que el visor sea cliente del mismo modelo de estado, no una fuente
independiente. Se cumplia con las frases y no con las palabras sueltas: la insignia de nivel
tenia su propia tabla en `frontend/src/lib/levels.ts` y la consola escribia «recuperándose» y
«empeorando». Dos tablas se separan, y se separaron: CONCERN era «preocupación» en el resumen
del backend y «Precaución» en la insignia.

Aqui no se decide nada: se lee `RiskLevel` (que es quien nombra cada nivel) y se da en la forma
que la interfaz pinta. Lo que sigue siendo de la interfaz es el color y el glifo de cada nivel
(`palette.ts`, tabla F.5-1), que no son texto.
"""

from __future__ import annotations

from typing import Any

from app.analysis.risk import RiskLevel
from app.core import i18n

# Hacia donde va un dominio frente a una ventana antes (`recovery_state.trajectories`).
# Describe un cambio de nivel ya calculado; no es un nivel ni un pronostico.
TRAJECTORY_DISPLAY: dict[str, str] = {
    "recovering": "recuperándose",
    "worsening": "empeorando",
}
i18n.en_many({"recuperándose": "recovering", "empeorando": "worsening"})


def level_labels() -> dict[str, str]:
    """Clave de la API → palabra de la insignia, para todos los niveles."""
    return {str(level): level.label for level in RiskLevel}


def with_wording(trajectory: dict[str, Any] | None) -> dict[str, Any] | None:
    """La trayectoria de un dominio con su frase hecha; `None` si no cambio de nivel."""
    if trajectory is None:
        return None
    word = i18n.loc(TRAJECTORY_DISPLAY[trajectory["direction"]])
    before = RiskLevel(trajectory["from_level"]).label
    return {
        **trajectory,
        "direction_display": word,
        "from_level_display": before,
        "display": i18n.tr(f"{word} (antes {before})", f"{word} (was {before})"),
    }
