"""La integridad se comprueba contra el disco, y el motor solo analiza lo firmado.

Reproducido antes de este cambio, con la aplicacion en marcha: editar en la base
una lectura de 62 a 140 lpm hacia que el motor **analizara los 140** mientras
`verify_integrity()` respondia ok, porque verificaba la copia en memoria y
`query()` leia la tabla `observations`, que no cubre ningun hash. Solo se
detectaba al reiniciar.
"""

import datetime as dt
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.ledger import HashChainLedger, Identity, RedactionAuthority
from app.core.storage import (
    LedgerRow,
    ObservationRow,
    ObservationStore,
    TamperedRecordError,
)
from app.ingest.fhir import observation

NOW = dt.datetime(2026, 11, 14, 8, 0, tzinfo=dt.UTC)
SIGNED_VALUES = [60.0, 61.0, 62.0, 63.0, 64.0]
AUDITOR = Identity.generate("emma-audit")


@pytest.fixture
def store(tmp_path: Path) -> ObservationStore:
    """Un almacen en fichero, que es lo que alguien podria editar por fuera."""
    created = ObservationStore.at(tmp_path / "emma.db", RedactionAuthority.of(AUDITOR))
    identity = Identity.generate("wearable-01")
    for minute, value in enumerate(SIGNED_VALUES):
        created.record(
            observation("heart-rate", value, NOW + dt.timedelta(minutes=minute), "crew-01", "t"),
            identity,
        )
    return created


def _edit_observation_row(session: Session) -> None:
    session.query(ObservationRow).filter_by(ledger_index=2).one().value = 140.0


def _edit_ledger_row(session: Session) -> None:
    row = session.get(LedgerRow, 2)
    assert row is not None and row.payload is not None
    payload = json.loads(row.payload)
    payload["value"] = 140.0
    row.payload = json.dumps(payload)


def _delete_observation_row(session: Session) -> None:
    session.execute(delete(ObservationRow).where(ObservationRow.ledger_index == 3))


def _insert_forged_row(session: Session) -> None:
    session.add(
        ObservationRow(
            subject="crew-01", key="heart-rate", value=150.0, effective=NOW,
            source="t", context="unknown", confidence=1.0, ledger_index=99,
        )
    )


def test_an_untouched_store_verifies_now_and_after_restart(
    store: ObservationStore, tmp_path: Path
) -> None:
    """El contrapeso, y la guarda de un fallo real de la primera version.

    Una fila de SQLAlchemy es una tupla, y `row.index` es el metodo
    `tuple.index`, no la columna: comparando por atributo, la verificacion
    fallaba en **toda** base sana. mypy lo cazo antes de ejecutarlo.
    """
    assert store.verify_integrity().ok
    assert store.verify_integrity().ok  # la segunda, por el camino incremental
    assert ObservationStore.at(tmp_path / "emma.db").verify_integrity().ok


@pytest.mark.parametrize(
    ("tamper", "failed_index"),
    [
        (_edit_observation_row, 2),
        (_edit_ledger_row, 2),
        (_delete_observation_row, 3),
        (_insert_forged_row, 99),
    ],
    ids=["editar-lectura", "editar-asiento", "borrar-fila", "fila-falsa"],
)
def test_runtime_disk_tampering_is_detected_without_restart(
    store: ObservationStore, tamper: Callable[[Session], None], failed_index: int
) -> None:
    assert store.verify_integrity().ok

    with Session(store.engine) as session:
        tamper(session)
        session.commit()

    result = store.verify_integrity()
    assert not result.ok
    assert result.failed_index == failed_index


@pytest.mark.parametrize(
    "tamper",
    [_edit_observation_row, _delete_observation_row, _insert_forged_row],
    ids=["editar-lectura", "borrar-fila", "fila-falsa"],
)
def test_the_engine_only_ever_sees_signed_values(
    store: ObservationStore, tamper: Callable[[Session], None]
) -> None:
    """Lo que se edita en la tabla no llega al analisis: se lee de la cadena."""
    with Session(store.engine) as session:
        tamper(session)
        session.commit()

    assert [obs.value for obs in store.query("crew-01")] == SIGNED_VALUES


def test_a_mutated_payload_is_refused_not_analysed(store: ObservationStore) -> None:
    """Si el contenido en memoria ya no casa con su hash firmado, no se entrega.

    Por la vista publica ya no se puede provocar: `ledger[i]` y `ledger.entries`
    devuelven copias. Se manipula el estado interno para probar la defensa de
    `query()` por si otra via llegara a hacerlo.
    """
    store.ledger._entries[2].payload["value"] = 140.0  # type: ignore[index]

    with pytest.raises(TamperedRecordError, match="asiento 2"):
        store.query("crew-01")
    assert not store.verify_integrity().ok


def test_redaction_still_verifies_against_disk(store: ObservationStore) -> None:
    store.redact(1, AUDITOR, "motivo", "cirujano")

    assert store.verify_integrity().ok
    assert [obs.value for obs in store.query("crew-01")] == [60.0, 62.0, 63.0, 64.0]


def test_skipping_known_signatures_still_checks_chain_and_content() -> None:
    """Saltarse la firma ya comprobada no es saltarse la verificacion."""
    ledger = HashChainLedger()
    identity = Identity.generate("wearable-01")
    ledger.registry.register(identity.identity_id, identity.public_key_hex)
    for i in range(4):
        ledger.append(entry_type="t", payload={"i": i}, identity=identity)
    assert ledger.verify(signatures_from=4).ok

    ledger._entries[2].payload["i"] = 99  # type: ignore[index]
    assert not ledger.verify(signatures_from=4).ok

    ledger._entries[2].payload["i"] = 2  # type: ignore[index]
    ledger._entries[3] = replace(ledger._entries[3], prev_hash="0" * 64)
    assert not ledger.verify(signatures_from=4).ok
