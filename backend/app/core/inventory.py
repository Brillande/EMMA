"""El inventario de a bordo, tal y como lo cuenta y lo firma una persona.

POR QUÉ EXISTE
--------------
La consola enseña «Recursos e inventario», «Medicamentos», «Alimentación» y «Abastecimiento», y
la maqueta lo llenaba de cifras. Ninguna de esas cifras se puede sacar de EMMA: no lee ningún
sistema de estiba ni ningún botiquín. El usuario eligió (2026-11-14) un «inventario real
firmado»: una persona cuenta lo que hay y lo declara en la consola, el recuento queda firmado en
el registro (invariante 4) y la autonomía se calcula de ahí. Sin recuentos, «sin declarar»: ni
una existencia ni un consumo de ejemplo viajan en el paquete.

Es distinto de `core/resources.py`, que declara si un recurso del vocabulario de las
contramedidas está o no disponible, sin cantidades. Aquí hay cantidades, pero solo las que una
persona firmó.

LO QUE SE CALCULA, Y LO QUE NO
------------------------------
* `autonomy_days = quantity / daily_use`, solo con un consumo diario declarado y mayor que cero.
  Sin consumo no hay autonomía: no se supone uno.
* `critical` = la autonomía no llega a `min_days`. Si falta la autonomía o el umbral, `None`:
  EMMA no inventa un umbral, y «no crítico» no es lo mismo que «no se sabe».
* `alternatives` = los demás artículos de la misma `family` que constan con cantidad. Es una
  lista de lo que hay, no una equivalencia clínica: si sustituye o no lo valora una persona
  (invariante 7).

QUÉ RECUENTO VALE
-----------------
El último firmado por la consola para cada artículo (`item`, único en todo el inventario). Se
corrige contando de nuevo; no hay borrado y los anteriores se conservan en el registro. Del
abastecimiento vale la última declaración.

NO DECIDE NADA
--------------
Nada de esto entra en el análisis, en los niveles, en las alertas ni en las recomendaciones
(invariante 5). Un artículo crítico no levanta ninguna alerta: se enseña como dato declarado.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.core import i18n

SUBJECT = "mision"


@dataclass(frozen=True, slots=True)
class Category:
    id: str
    label: str


# El vocabulario de categorías es cerrado: son las tres secciones de la consola, y nada más.
CATEGORIES: tuple[Category, ...] = (
    Category("medications", "Medicamentos"),
    Category("food", "Alimentos"),
    Category("medical-equipment", "Equipo médico"),
)
CATEGORY_IDS = tuple(item.id for item in CATEGORIES)
_CATEGORY_EN = {
    "medications": "Medications", "food": "Food", "medical-equipment": "Medical equipment",
}
i18n.en_many({item.label: _CATEGORY_EN[item.id] for item in CATEGORIES})

LABEL = "contado y declarado por una persona, firmado en el registro"
NOTE = (
    "EMMA no lee ningún sistema de estiba: estas existencias son las que una persona contó y "
    "declaró en la consola. Lo que nadie ha contado está sin declarar, no a cero."
)
RULE = (
    "Vale el último recuento firmado por la consola para cada artículo; los anteriores se "
    "conservan. No hay borrado: se corrige contando de nuevo."
)
AUTONOMY_RULE = (
    "Autonomía = existencias / consumo diario declarado, solo si el consumo se declaró y es "
    "mayor que cero. Crítico = la autonomía no llega al mínimo declarado; sin mínimo o sin "
    "autonomía, sin determinar."
)
ALTERNATIVES_RULE = (
    "Alternativas: otros artículos de la misma familia que constan con existencias. Es lo que "
    "hay a bordo, no una equivalencia: si sustituye lo valora una persona."
)
SCOPE = (
    "El inventario no cambia el análisis, los niveles, las alertas ni las recomendaciones."
)
UNDECLARED_DISPLAY = "sin declarar"
i18n.en(LABEL, "counted and declared by a person, signed in the ledger")
i18n.en(
    NOTE,
    "EMMA does not read any stowage system: these stocks are the ones a person counted and "
    "declared in the console. What nobody has counted is undeclared, not zero.",
)
i18n.en(
    RULE,
    "The last count signed by the console for each item is the one in force; earlier ones are "
    "kept. Nothing is deleted: it is corrected by counting again.",
)
i18n.en(
    AUTONOMY_RULE,
    "Autonomy = stock / declared daily use, only if the use was declared and is greater than "
    "zero. Critical = the autonomy does not reach the declared minimum; without a minimum or "
    "without autonomy, undetermined.",
)
i18n.en(
    ALTERNATIVES_RULE,
    "Alternatives: other items of the same family that are on record with stock. It is what is "
    "on board, not an equivalence: whether it can substitute is for a person to judge.",
)
i18n.en(
    SCOPE,
    "The inventory does not change the analysis, the levels, the alerts or the "
    "recommendations.",
)

# Lo que se firma de un recuento, siempre; y lo que solo va si se declaró.
COUNT_FIELDS = (
    "subject", "category", "item", "name", "unit", "quantity", "counted_at", "declared_by",
)
COUNT_OPTIONAL = ("daily_use", "family", "min_days", "expires")
RESUPPLY_FIELDS = ("subject", "name", "eta", "declared_at", "declared_by")
RESUPPLY_OPTIONAL = ("capacity_kg",)

MAX_NAME = 120
MAX_UNIT = 16
MAX_OPERATOR = 64

_KEY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def _utc_text(moment: dt.datetime, what: str) -> str:
    if moment.tzinfo is None:
        raise ValueError(f"{what}: el instante debe llevar zona horaria")
    return moment.astimezone(dt.UTC).isoformat()


def number_text(value: float, what: str, *, positive: bool = False) -> str:
    """Una cifra declarada, como texto firmado: finita, no negativa y sin notación rara.

    Se firma como texto (como todos los campos de una acción, `_actions`): un entero sale sin
    decimales y el resto con `repr`, que reproduce el mismo `float` al leerlo.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what}: no es un número")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{what}: no es un número finito")
    if number < 0 or (positive and number == 0):
        raise ValueError(f"{what}: debe ser {'mayor que cero' if positive else 'cero o más'}")
    return str(int(number)) if number.is_integer() and abs(number) < 1e15 else repr(number)


def _text(value: str, what: str, limit: int) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{what}: vacío")
    if len(cleaned) > limit:
        raise ValueError(f"{what}: más de {limit} caracteres")
    return cleaned


def _operator(value: str) -> str:
    cleaned = _text(value, "declared_by", MAX_OPERATOR)
    if not any(char.isalpha() for char in cleaned):
        raise ValueError("el inventario lo declara una persona con nombre")
    return cleaned


def _key(value: str, what: str) -> str:
    if not _KEY.fullmatch(value):
        raise ValueError(f"{what}: clave no válida ({value!r}); minúsculas, cifras y guiones")
    return value


def count_payload(
    *, category: str, item: str, name: str, unit: str, quantity: float,
    counted_at: dt.datetime, declared_by: str, daily_use: float | None = None,
    family: str | None = None, min_days: float | None = None, expires: dt.date | None = None,
) -> dict[str, str]:
    """El asiento `inventory-count`, validado. Lo usa el almacén: nadie más lo escribe."""
    if category not in CATEGORY_IDS:
        raise ValueError(
            f"categoría desconocida: {category}; una de {', '.join(CATEGORY_IDS)}"
        )
    payload = {
        "subject": SUBJECT,
        "category": category,
        "item": _key(item, "item"),
        "name": _text(name, "name", MAX_NAME),
        "unit": _text(unit, "unit", MAX_UNIT),
        "quantity": number_text(quantity, "quantity"),
        "counted_at": _utc_text(counted_at, "counted_at"),
        "declared_by": _operator(declared_by),
    }
    if daily_use is not None:
        payload["daily_use"] = number_text(daily_use, "daily_use")
    if family is not None:
        payload["family"] = _key(family, "family")
    if min_days is not None:
        payload["min_days"] = number_text(min_days, "min_days", positive=True)
    if expires is not None:
        if isinstance(expires, dt.datetime) or not isinstance(expires, dt.date):
            raise ValueError("expires: una fecha AAAA-MM-DD")
        payload["expires"] = expires.isoformat()
    return payload


def resupply_payload(
    *, name: str, eta: dt.datetime, declared_at: dt.datetime, declared_by: str,
    capacity_kg: float | None = None,
) -> dict[str, str]:
    """El asiento `inventory-resupply`, validado: el próximo abastecimiento que se declara."""
    payload = {
        "subject": SUBJECT,
        "name": _text(name, "name", MAX_NAME),
        "eta": _utc_text(eta, "eta"),
        "declared_at": _utc_text(declared_at, "declared_at"),
        "declared_by": _operator(declared_by),
    }
    if capacity_kg is not None:
        payload["capacity_kg"] = number_text(capacity_kg, "capacity_kg")
    return payload


def visible(
    counts: Sequence[dict[str, Any]], resupplies: Sequence[dict[str, Any]],
    until: dt.datetime | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Lo que Tierra puede tener en su corte: nada contado ni declarado después de él."""
    if until is None:
        return list(counts), list(resupplies)
    return (
        [row for row in counts if dt.datetime.fromisoformat(row["counted_at"]) <= until],
        [row for row in resupplies if dt.datetime.fromisoformat(row["declared_at"]) <= until],
    )


def _number(row: dict[str, Any], field: str) -> float | None:
    value = row.get(field)
    return None if value is None else float(value)


def _whole(value: float) -> float | int:
    return int(value) if value.is_integer() else value


def in_force(counts: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """El recuento vigente de cada artículo: el último firmado (por orden del registro)."""
    held: dict[str, dict[str, Any]] = {}
    for row in sorted(counts, key=lambda entry: entry["ledger_index"]):
        held[row["item"]] = row
    return held


def _item(row: dict[str, Any], held: dict[str, dict[str, Any]]) -> dict[str, Any]:
    quantity = float(row["quantity"])
    daily_use = _number(row, "daily_use")
    min_days = _number(row, "min_days")
    autonomy = quantity / daily_use if daily_use is not None and daily_use > 0 else None
    critical = None if autonomy is None or min_days is None else autonomy < min_days
    family = row.get("family")
    alternatives = (
        [] if family is None else sorted(
            key for key, other in held.items()
            if key != row["item"] and other.get("family") == family
            and float(other["quantity"]) > 0
        )
    )
    return {
        "id": row["item"],
        "name": row["name"],
        "family": family,
        "unit": row["unit"],
        "quantity": _whole(quantity),
        "daily_use": None if daily_use is None else _whole(daily_use),
        "autonomy_days": None if autonomy is None else round(autonomy, 1),
        "min_days": None if min_days is None else _whole(min_days),
        "critical": critical,
        "alternatives": alternatives,
        "counted_at": row["counted_at"],
        "declared_by": row["declared_by"],
        "expires": row.get("expires"),
        "ledger_index": row["ledger_index"],
        "recorded": row["recorded"],
    }


def _totals(items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    autonomies = [item["autonomy_days"] for item in items if item["autonomy_days"] is not None]
    return {
        "units": _whole(float(sum(item["quantity"] for item in items))),
        "kinds": len(items),
        "critical": sum(1 for item in items if item["critical"] is True),
        "available": sum(1 for item in items if item["quantity"] > 0),
        "undeclared_use": sum(1 for item in items if item["daily_use"] is None),
        "min_autonomy_days": min(autonomies) if autonomies else None,
    }


def _resupply(rows: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    last = max(rows, key=lambda entry: entry["ledger_index"])
    capacity = _number(last, "capacity_kg")
    return {
        "name": last["name"],
        "eta": last["eta"],
        "capacity_kg": None if capacity is None else _whole(capacity),
        "declared_at": last["declared_at"],
        "declared_by": last["declared_by"],
        "ledger_index": last["ledger_index"],
        "recorded": last["recorded"],
    }


def overview(
    counts: Sequence[dict[str, Any]], resupplies: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """Las tres categorías con lo vigente, sus totales y el último abastecimiento declarado.

    `counts` y `resupplies` son los asientos tal y como los entrega el almacén, ya filtrados
    (firmados por la consola y, para Tierra, dentro de su corte). Sin nada, las tres categorías
    salen vacías y `declared` es falso: nada se rellena.
    """
    held = in_force(counts)
    categories = []
    for category in CATEGORIES:
        items = sorted(
            (_item(row, held) for row in held.values() if row["category"] == category.id),
            key=lambda item: (item["name"].casefold(), item["id"]),
        )
        categories.append({
            "id": category.id, "label": i18n.loc(category.label), "items": items,
            "totals": _totals(items),
        })
    return {
        "categories": categories,
        "resupply": _resupply(resupplies),
        "declared": bool(held) or bool(resupplies),
        "label": i18n.loc(LABEL),
        "note": i18n.loc(NOTE),
        "rule": i18n.loc(RULE),
        "autonomy_rule": i18n.loc(AUTONOMY_RULE),
        "alternatives_rule": i18n.loc(ALTERNATIVES_RULE),
        "scope": i18n.loc(SCOPE),
        # Con `tr` y no con el registro: «sin declarar» lo dicen también otros módulos.
        "undeclared_display": i18n.tr(UNDECLARED_DISPLAY, "undeclared"),
    }
