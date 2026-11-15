"""El inventario de a bordo: contarlo, declarar el abastecimiento y leerlo (`core/inventory.py`).

Por qué existe: la consola tiene secciones de medicamentos, alimentos, equipo médico y
abastecimiento, y la única fuente honesta de sus cifras es una persona que cuenta y firma
(decisión del usuario, 2026-11-14). Tres rutas: dos escriben UN asiento cada una, firmado por la
consola como las demás acciones del operador y con la cabecera `X-EMMA-Console` (la consola la
pone en todos sus `POST`); la tercera lee lo vigente con la autonomía calculada, y para Tierra
solo lo que ya existía en su corte. Nada de esto toca el análisis ni las alertas (invariante 5).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.api.console_header import console_post
from app.api.routes import CONSOLE_IDENTITY, StoreDep, _counts, _recorded_or_422, identity_for
from app.core import inventory

inventory_router = APIRouter()

Operator = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=inventory.MAX_OPERATOR)
]
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=inventory.MAX_NAME)
]
Unit = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=inventory.MAX_UNIT)
]
Amount = Annotated[float, Field(ge=0, allow_inf_nan=False)]


def _aware(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        raise ValueError("el instante debe llevar zona horaria")
    return value


class InventoryCountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    item: str
    name: Name
    unit: Unit
    quantity: Amount
    daily_use: Amount | None = None
    family: str | None = None
    min_days: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = None
    expires: dt.date | None = None
    # Cuándo se contó, según quien cuenta; no decide qué recuento manda (manda el último firmado).
    counted_at: dt.datetime
    declared_by: Operator

    @field_validator("counted_at")
    @classmethod
    def _counted_at_aware(cls, value: dt.datetime) -> dt.datetime:
        return _aware(value)


class InventoryResupplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    eta: dt.datetime
    capacity_kg: Amount | None = None
    declared_at: dt.datetime
    declared_by: Operator

    @field_validator("eta", "declared_at")
    @classmethod
    def _instants_aware(cls, value: dt.datetime) -> dt.datetime:
        return _aware(value)


def inventory_declarations(
    store: Any, until: dt.datetime | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Los recuentos y abastecimientos que cuentan, leídos del ledger.

    Solo los firmados por la consola y, para Tierra, los que ya existían en su corte y no se
    contaron ni declararon después de él, como `resource_declarations`.
    """
    return inventory.visible(
        [row for row in store.inventory_counts() if _counts(row, until)],
        [row for row in store.inventory_resupplies() if _counts(row, until)],
        until,
    )


@inventory_router.post("/inventory/count", status_code=201, **console_post())
def count_item(store: StoreDep, payload: InventoryCountIn) -> dict[str, Any]:
    """Firma el recuento de un artículo. 422 si no se puede firmar."""
    entry = _recorded_or_422(
        lambda: store.record_inventory_count(
            identity_for(CONSOLE_IDENTITY), **payload.model_dump()
        )
    )[0]
    return {"ledger_index": entry.index}


@inventory_router.post("/inventory/resupply", status_code=201, **console_post())
def declare_resupply(store: StoreDep, payload: InventoryResupplyIn) -> dict[str, Any]:
    """Firma el próximo abastecimiento declarado. 422 si no se puede firmar."""
    entry = _recorded_or_422(
        lambda: store.record_inventory_resupply(
            identity_for(CONSOLE_IDENTITY), **payload.model_dump()
        )
    )[0]
    return {"ledger_index": entry.index}


@inventory_router.get("/inventory")
def read_inventory(
    store: StoreDep,
    # Lo que Tierra puede tener: hasta el corte del retardo, como `/api/resources`.
    until: dt.datetime | None = None,
) -> dict[str, Any]:
    """Las tres categorías con lo contado vigente, su autonomía y el abastecimiento declarado."""
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    counts, resupplies = inventory_declarations(store, until)
    return inventory.overview(counts, resupplies)
