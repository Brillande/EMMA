"""El inventario de a bordo, contado y firmado por una persona (lote «reservas», 2026-11-14).

Lo que se fija: sin recuentos no hay nada que enseñar (`declared: false`, categorías vacías,
ni un dato de ejemplo); la autonomía solo sale de un consumo declarado; «crítico» solo con un
mínimo declarado; las alternativas son los demás de la misma familia con existencias; manda el
último recuento; cada declaración es UN asiento firmado por la consola y verificable
(invariante 4); los POST piden `X-EMMA-Console`; Tierra no ve lo posterior a su corte; y nada
de esto mueve el estado, los niveles ni las alertas (invariante 5).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.console_header import CONSOLE_HEADER
from app.api.routes import get_store, identity_for
from app.core import inventory
from app.core.storage import TamperedRecordError

T0 = dt.datetime(2026, 11, 14, 8, 0, tzinfo=dt.UTC)
FAR = "2100-01-01T00:00:00+00:00"


def _count(client: TestClient, item: str = "amoxicillin", quantity: float = 12,
           **extra: Any) -> Any:
    body = {
        "category": "medications", "item": item, "name": item.capitalize(), "unit": "u.",
        "quantity": quantity, "counted_at": T0.isoformat(), "declared_by": "CMO",
        **extra,
    }
    return client.post("/api/inventory/count", json=body)


def _read(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/api/inventory", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _items(body: dict[str, Any], category: str = "medications") -> dict[str, dict[str, Any]]:
    (found,) = [item for item in body["categories"] if item["id"] == category]
    return {item["id"]: item for item in found["items"]}


def _totals(body: dict[str, Any], category: str = "medications") -> dict[str, Any]:
    (found,) = [item for item in body["categories"] if item["id"] == category]
    totals: dict[str, Any] = found["totals"]
    return totals


# --------------------------------------------------------------------------- #
# Sin declarar
# --------------------------------------------------------------------------- #


def test_without_counts_nothing_is_declared_and_nothing_is_filled_in(client: TestClient) -> None:
    body = _read(client)
    assert body["declared"] is False and body["resupply"] is None
    assert [(c["id"], c["label"]) for c in body["categories"]] == [
        ("medications", "Medicamentos"), ("food", "Alimentos"),
        ("medical-equipment", "Equipo médico"),
    ]
    for category in body["categories"]:
        assert category["items"] == []
        assert category["totals"] == {
            "units": 0, "kinds": 0, "critical": 0, "available": 0, "undeclared_use": 0,
            "min_autonomy_days": None,
        }
    assert body["undeclared_display"] == "sin declarar"


# --------------------------------------------------------------------------- #
# Autonomía, crítico y alternativas
# --------------------------------------------------------------------------- #


def test_autonomy_is_quantity_over_declared_daily_use(client: TestClient) -> None:
    assert _count(client, quantity=12, daily_use=0.33).status_code == 201
    assert _count(client, "ibuprofen", quantity=40).status_code == 201
    assert _count(client, "paracetamol", quantity=10, daily_use=0).status_code == 201
    items = _items(_read(client))
    assert items["amoxicillin"]["autonomy_days"] == 36.4
    assert items["amoxicillin"]["quantity"] == 12 and items["amoxicillin"]["daily_use"] == 0.33
    # Sin consumo, o con consumo cero, no hay autonomía: no se supone una.
    assert items["ibuprofen"]["autonomy_days"] is None
    assert items["ibuprofen"]["daily_use"] is None
    assert items["paracetamol"]["autonomy_days"] is None
    totals = _totals(_read(client))
    assert totals["kinds"] == 3 and totals["units"] == 62
    assert totals["undeclared_use"] == 1 and totals["min_autonomy_days"] == 36.4


def test_critical_only_with_a_declared_minimum(client: TestClient) -> None:
    _count(client, "amoxicillin", quantity=12, daily_use=0.5, min_days=30)   # 24 d < 30
    _count(client, "cefalexin", quantity=60, daily_use=1, min_days=30)       # 60 d
    _count(client, "ibuprofen", quantity=5, daily_use=1)                     # sin mínimo
    _count(client, "naproxen", quantity=5, min_days=30)                      # sin consumo
    items = _items(_read(client))
    assert items["amoxicillin"]["critical"] is True
    assert items["cefalexin"]["critical"] is False
    # Sin umbral o sin autonomía no se sabe: ni crítico ni no crítico.
    assert items["ibuprofen"]["critical"] is None and items["ibuprofen"]["min_days"] is None
    assert items["naproxen"]["critical"] is None
    assert _totals(_read(client))["critical"] == 1


def test_alternatives_are_the_same_family_with_stock(client: TestClient) -> None:
    _count(client, "amoxicillin", quantity=0, family="antibiotic")
    _count(client, "cefalexin", quantity=20, family="antibiotic")
    _count(client, "azithromycin", quantity=6, family="antibiotic")
    _count(client, "ibuprofen", quantity=30, family="analgesic")
    _count(client, "loratadine", quantity=8)
    items = _items(_read(client))
    assert items["amoxicillin"]["alternatives"] == ["azithromycin", "cefalexin"]
    # Una sin existencias no es alternativa de nadie.
    assert items["cefalexin"]["alternatives"] == ["azithromycin"]
    assert items["ibuprofen"]["alternatives"] == []
    assert items["loratadine"]["alternatives"] == [] and items["loratadine"]["family"] is None
    assert _totals(_read(client))["available"] == 4


def test_the_last_count_of_an_item_wins(client: TestClient) -> None:
    _count(client, quantity=12, daily_use=1, min_days=10)
    _count(client, quantity=4, counted_at="2026-11-01T00:00:00+00:00")
    items = _items(_read(client))
    # El último firmado manda aunque diga contado antes: sin consumo ni mínimo, ya no los hay.
    assert items["amoxicillin"]["quantity"] == 4
    assert items["amoxicillin"]["daily_use"] is None and items["amoxicillin"]["critical"] is None
    assert len(items) == 1
    assert len(get_store().inventory_counts()) == 2


def test_resupply_shows_the_last_declaration(client: TestClient) -> None:
    for name, kg in (("Cygnus NG-30", 1200), ("Dragon CRS-40", None)):
        response = client.post("/api/inventory/resupply", json={
            "name": name, "eta": "2026-12-01T12:00:00+00:00", "capacity_kg": kg,
            "declared_at": T0.isoformat(), "declared_by": "CDR",
        })
        assert response.status_code == 201, response.text
    body = _read(client)
    assert body["declared"] is True
    resupply = body["resupply"]
    assert resupply["name"] == "Dragon CRS-40" and resupply["capacity_kg"] is None
    assert resupply["eta"] == "2026-12-01T12:00:00+00:00" and resupply["declared_by"] == "CDR"


# --------------------------------------------------------------------------- #
# Lo que no se firma
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("change", [
    {"category": "tools"},
    {"item": "Amoxicilina con espacios"},
    {"quantity": -1},
    {"daily_use": -0.5},
    {"min_days": 0},
    {"family": "Antibiótico"},
    {"declared_by": " 12 "},
    {"counted_at": "2026-11-14T08:00:00"},
    {"expires": "2027-02-30"},
    {"extra": "nada"},
])
def test_what_cannot_be_signed_is_a_422_and_writes_nothing(
    client: TestClient, change: dict[str, Any]
) -> None:
    body = {
        "category": "medications", "item": "amoxicillin", "name": "Amoxicilina", "unit": "u.",
        "quantity": 12, "counted_at": T0.isoformat(), "declared_by": "CMO", **change,
    }
    response = client.post("/api/inventory/count", json=body)
    assert response.status_code == 422, (change, response.text)
    assert len(get_store().ledger) == 0


def test_the_store_refuses_what_cannot_be_signed(client: TestClient) -> None:
    store, console = get_store(), identity_for("crew-console")
    good: dict[str, Any] = {
        "category": "food", "item": "rice", "name": "Arroz", "unit": "kg", "quantity": 3.5,
        "counted_at": T0, "declared_by": "CDR",
    }
    for change, message in (
        ({"category": "tools"}, "categoría desconocida"),
        ({"quantity": float("nan")}, "finito"),
        ({"counted_at": T0.replace(tzinfo=None)}, "zona horaria"),
        ({"declared_by": "42"}, "una persona con nombre"),
    ):
        with pytest.raises(ValueError, match=message):
            store.record_inventory_count(console, **{**good, **change})
    assert len(store.ledger) == 0


# --------------------------------------------------------------------------- #
# La cabecera y el registro
# --------------------------------------------------------------------------- #


def test_the_posts_without_the_console_header_are_refused(client: TestClient) -> None:
    del client.headers[CONSOLE_HEADER]
    assert _count(client).status_code == 403
    assert client.post("/api/inventory/resupply", json={
        "name": "Cygnus", "eta": FAR, "declared_at": T0.isoformat(), "declared_by": "CDR",
    }).status_code == 403
    assert len(get_store().ledger) == 0
    # La lectura no la pide.
    assert client.get("/api/inventory").status_code == 200


def test_a_count_is_one_signed_entry_in_the_ledger_and_verifies(client: TestClient) -> None:
    store = get_store()
    response = _count(client, quantity=12, daily_use=0.33, family="antibiotic", min_days=30,
                      expires="2027-06-30", name="  Amoxicilina ")
    assert response.status_code == 201, response.text
    index = response.json()["ledger_index"]
    assert len(store.ledger) == 1
    entry = store.ledger._view()[index]
    assert (entry.entry_type, entry.signer) == ("inventory-count", "crew-console")
    assert {k: v for k, v in entry.payload.items() if k != "_salt"} == {
        "subject": "mision", "category": "medications", "item": "amoxicillin",
        "name": "Amoxicilina", "unit": "u.", "quantity": "12", "daily_use": "0.33",
        "family": "antibiotic", "min_days": "30", "expires": "2027-06-30",
        "counted_at": "2026-11-14T08:00:00+00:00", "declared_by": "CMO",
    }
    resupply = client.post("/api/inventory/resupply", json={
        "name": "Cygnus", "eta": FAR, "capacity_kg": 1200, "declared_at": T0.isoformat(),
        "declared_by": "CDR",
    })
    assert resupply.status_code == 201
    entry = store.ledger._view()[resupply.json()["ledger_index"]]
    assert (entry.entry_type, entry.signer) == ("inventory-resupply", "crew-console")
    assert store.verify_integrity().ok
    assert client.get("/api/audit").status_code == 200


def test_a_malformed_entry_is_not_delivered(client: TestClient) -> None:
    store = get_store()
    store._record_action("inventory-count", {
        "subject": "mision", "category": "food", "item": "rice", "name": "Arroz", "unit": "kg",
        "quantity": 3, "counted_at": T0.isoformat(), "declared_by": "CDR",
    }, identity_for("crew-console"))
    with pytest.raises(TamperedRecordError, match="acción mal formada"):
        store.inventory_counts()


def test_what_the_console_did_not_sign_does_not_count(client: TestClient) -> None:
    get_store().record_inventory_count(
        identity_for("wearable-ble"), category="food", item="rice", name="Arroz", unit="kg",
        quantity=3, counted_at=T0, declared_by="nadie",
    )
    assert _read(client)["declared"] is False


# --------------------------------------------------------------------------- #
# Tierra y su corte
# --------------------------------------------------------------------------- #


def test_ground_does_not_see_what_is_after_its_cut(client: TestClient) -> None:
    # Contado antes del corte, pero firmado ahora: en ese corte no existía.
    assert _count(client, counted_at="2020-06-01T00:00:00+00:00").status_code == 201
    assert _read(client, until="2021-01-01T00:00:00+00:00")["declared"] is False
    # Firmado ya, pero contado después del corte: tampoco.
    assert _count(client, "cefalexin", counted_at="2199-01-01T00:00:00+00:00").status_code == 201
    client.post("/api/inventory/resupply", json={
        "name": "Cygnus", "eta": "2199-02-01T00:00:00+00:00",
        "declared_at": "2199-01-01T00:00:00+00:00", "declared_by": "CDR",
    })
    seen = _read(client, until=FAR)
    assert set(_items(seen)) == {"amoxicillin"} and seen["resupply"] is None
    assert set(_items(_read(client))) == {"amoxicillin", "cefalexin"}
    assert client.get("/api/inventory", params={"until": "2026-11-14T08:00:00"}).status_code == 422


# --------------------------------------------------------------------------- #
# Nada cambia el análisis
# --------------------------------------------------------------------------- #


def test_the_inventory_does_not_move_the_status(client: TestClient) -> None:
    """Invariante 5: el mismo ledger de lecturas, con inventario y sin él, da el mismo estado."""
    assert client.post(
        "/api/simulate", params={"scenario": "progressive-insomnia", "days": 40}
    ).status_code == 201
    before = client.get("/api/status", params={"until": FAR}).json()
    assert before["alerts"]
    _count(client, quantity=1, daily_use=1, min_days=30)   # crítico
    _count(client, "rice", category="food", quantity=0)
    client.post("/api/inventory/resupply", json={
        "name": "Cygnus", "eta": FAR, "declared_at": T0.isoformat(), "declared_by": "CDR",
    })
    assert _totals(_read(client))["critical"] == 1
    after = client.get("/api/status", params={"until": FAR}).json()
    assert after == before


def test_the_texts_pass_the_language_filter() -> None:
    from app.text_guard import check

    for text in (inventory.LABEL, inventory.NOTE, inventory.RULE, inventory.AUTONOMY_RULE,
                 inventory.ALTERNATIVES_RULE, inventory.SCOPE):
        assert check(text) == [], text
