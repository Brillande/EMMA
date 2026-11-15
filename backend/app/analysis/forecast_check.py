"""¿Acertaron las proyecciones? (conversacion de ideacion: "prediccion durante mision →
resultado → validacion → modelo mejorado").

EMMA proyecta las derivas a 4 semanas (`trend.projection`, rotuladas PREDICHAS). Una proyeccion
que nadie contrasta es una afirmacion sin respaldo. Aqui se contrastan de dos maneras:

- **Retrospectiva**: la proyeccion que el motor habria hecho hace un horizonte con los datos de
  entonces, frente a lo medido ahora. Sirve desde el primer dia en que hay historia suficiente,
  y se rotula asi: no es una prediccion que alguien viera en su momento.
- **Instantaneas**: cada proyeccion se firma en el ledger (`prediction-snapshot`) el dia que se
  hace; cuando llega su horizonte, se compara con lo medido. Es la comprobacion de verdad.

Lo que se compara: el cambio medio diario entre el dia de la proyeccion y el del horizonte,
frente al cambio proyectado y su margen. Es calibracion declarada del propio modelo, no una
prueba de validez clinica. No cambia umbrales ni alertas.
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections.abc import Sequence
from typing import Any

from app.analysis.trend import RELEVANCE_HORIZON_WEEKS, projection, trends_by_indicator
from app.core import i18n
from app.ingest.codes import CATALOG
from app.ingest.fhir import VitalObservation

HORIZON = dt.timedelta(weeks=RELEVANCE_HORIZON_WEEKS)
DAY = dt.timedelta(days=1)


def daily_mean(
    observations: Sequence[VitalObservation], key: str, end: dt.datetime
) -> float | None:
    values = [o.value for o in observations if o.key == key and end - DAY < o.effective <= end]
    return statistics.fmean(values) if values else None


def _verdict(
    key: str, anchor: float, actual: float, predicted: dict[str, Any]
) -> dict[str, Any]:
    change = actual - anchor
    return {
        "key": key,
        "display": predicted.get("display", key),
        # Una instantánea firmada guarda solo la clave: entonces el nombre se busca en el catálogo.
        "display_es": predicted.get(
            "display_es", CATALOG[key].display_es if key in CATALOG else key
        ),
        "unit": predicted.get("unit"),
        "projected_change": predicted["projected_change"],
        "projected_change_low": predicted["projected_change_low"],
        "projected_change_high": predicted["projected_change_high"],
        "actual_change": round(change, 4),
        "error": round(change - predicted["projected_change"], 4),
        "within_margin": (
            predicted["projected_change_low"] <= change <= predicted["projected_change_high"]
        ),
    }


def hindcast(
    observations: Sequence[VitalObservation], reference: dt.datetime
) -> list[dict[str, Any]]:
    """Lo que el motor habria proyectado hace un horizonte, frente a lo medido ahora."""
    cutoff = reference - HORIZON
    before = [o for o in observations if o.effective <= cutoff]
    if not before:
        return []
    results: list[dict[str, Any]] = []
    for trend in trends_by_indicator(before).values():
        predicted = projection(trend)
        if predicted is None:
            continue
        anchor = daily_mean(before, trend.key, cutoff)
        actual = daily_mean(observations, trend.key, reference)
        if anchor is None or actual is None:
            continue
        results.append({**_verdict(trend.key, anchor, actual, predicted), "kind": "hindcast"})
    return results


def matured(
    snapshots: Sequence[dict[str, Any]],
    observations: Sequence[VitalObservation],
    reference: dt.datetime,
) -> list[dict[str, Any]]:
    """Instantaneas firmadas cuyo horizonte ya llego, comparadas con lo medido."""
    results: list[dict[str, Any]] = []
    for item in snapshots:
        horizon_at = dt.datetime.fromisoformat(item["horizon_at"])
        if horizon_at > reference:
            continue
        actual = daily_mean(observations, item["key"], horizon_at)
        if actual is None:
            continue
        predicted = {
            "display": item["key"],
            "projected_change": float(item["projected_change"]),
            "projected_change_low": float(item["projected_change_low"]),
            "projected_change_high": float(item["projected_change_high"]),
        }
        results.append({
            **_verdict(item["key"], float(item["anchor_value"]), actual, predicted),
            "kind": "snapshot",
            "made_at": item["made_at"],
            "ledger_index": item["ledger_index"],
        })
    return results


def summary(checks: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "checked": len(checks),
        "within_margin": sum(1 for item in checks if item["within_margin"]),
        "checks": list(checks),
        "basis": i18n.tr(
            "cambio medio diario medido frente al proyectado y su margen; la retrospectiva es "
            "la proyección que el motor habría hecho hace 4 semanas, no una que alguien viera. "
            "Es calibración del propio modelo, no validez clínica",
            "measured mean daily change against the projected one and its margin; the hindcast "
            "is the projection the engine would have made 4 weeks ago, not one anybody saw. "
            "It is calibration of the model itself, not clinical validity",
        ),
    }
