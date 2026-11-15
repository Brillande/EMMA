"""Tiempo hasta la accion de una alerta: deteccion → decision → intervencion.

La conversacion de origen lo pide para cada riesgo ("Detection time → Interpretation time →
Decision time → Intervention time → Recovery"): un sistema que detecta bien pero tarde, o cuya
alerta nadie atiende, vale poco en una mision sin Tierra en tiempo real. Para la radiacion ya se
mostraba el procedimiento de Orion; aqui se mide, para cualquier alerta, lo que de verdad paso,
con lo que el ledger ya tiene.

Todo en TIEMPO DE LOS DATOS: el inicio es la primera lectura fuera de lo esperado, y cada
decision cuenta en el instante del estado que vio quien decidio (`reference_time`). Mezclar ese
reloj con el del registro daria tiempos negativos en una demo simulada. No hay umbral: es una
medida operativa, no un juicio.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any


def _first_after(
    items: Sequence[dict[str, Any]], domain: str, onset: dt.datetime
) -> dict[str, Any] | None:
    matching = [
        item for item in items
        if item.get("domain") == domain
        and dt.datetime.fromisoformat(item["reference_time"]) >= onset
    ]
    return min(matching, key=lambda item: item["reference_time"], default=None)


def _minutes(start: dt.datetime, item: dict[str, Any] | None) -> int | None:
    if item is None:
        return None
    return round((dt.datetime.fromisoformat(item["reference_time"]) - start).total_seconds() / 60)


def time_to_action_of(
    domain: str,
    onset_iso: str | None,
    acknowledgements: Sequence[dict[str, Any]],
    adoptions: Sequence[dict[str, Any]],
) -> dict[str, Any] | None:
    """Minutos desde el inicio hasta el reconocimiento y hasta la primera contramedida."""
    if onset_iso is None:
        return None
    onset = dt.datetime.fromisoformat(onset_iso)
    acknowledged = _first_after(acknowledgements, domain, onset)
    adopted = _first_after(adoptions, domain, onset)
    return {
        "onset": onset_iso,
        "acknowledged_after_minutes": _minutes(onset, acknowledged),
        "countermeasure_after_minutes": _minutes(onset, adopted),
        "basis": (
            "en tiempo de los datos: desde la primera lectura fuera de lo esperado hasta el "
            "estado que vio quien reconoció o adoptó; sin dato, está pendiente"
        ),
    }
