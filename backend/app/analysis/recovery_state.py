"""Trayectoria de cada dominio: «recuperándose» o «empeorando» (conversacion de ideacion).

La demo de la conversacion de origen termina asi: CAUTION → RECOVERING → NOMINAL. EMMA pasaba
de «precaucion» a «nominal» sin decir que venia de un problema; quien miraba la pantalla no
sabia si el dominio llevaba semanas tranquilo o se acababa de recuperar, y eso cambia lo que
conviene vigilar.

Descriptivo y sin reglas nuevas: se compara el nivel actual de cada dominio con el que el mismo
motor daba una ventana antes (las desviaciones del motor son causales —cada lectura se juzga
contra su pasado—, asi que el nivel de entonces se reconstruye sin volver a calcular la base).
No es un nivel de riesgo ni cambia alertas o puntuaciones (invariante 5).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.analysis.risk import RiskLevel
from app.core import i18n
from app.ingest.codes import Domain

_ORDER = [RiskLevel.NOMINAL, RiskLevel.WATCH, RiskLevel.CONCERN, RiskLevel.CRITICAL]


def trajectories(
    current: dict[Domain, RiskLevel],
    previous: dict[Domain, RiskLevel],
    previous_at: dt.datetime,
) -> dict[str, dict[str, Any] | None]:
    """Para cada dominio: None si no cambio de nivel; si no, hacia donde y desde donde."""
    found: dict[str, dict[str, Any] | None] = {}
    for domain, now in current.items():
        before = previous.get(domain, RiskLevel.NOMINAL)
        delta = _ORDER.index(now) - _ORDER.index(before)
        if delta == 0:
            found[str(domain)] = None
            continue
        found[str(domain)] = {
            "direction": "recovering" if delta < 0 else "worsening",
            "from_level": str(before),
            "to_level": str(now),
            "since": previous_at.isoformat(),
            "basis": i18n.tr(
                f"nivel de {before.display} hace una ventana y de {now.display} ahora, con las "
                f"mismas reglas; describe el cambio, no lo explica",
                f"{before.display} level one window ago and {now.display} level now, under the "
                f"same rules; it describes the change, it does not explain it",
            ),
        }
    return found
