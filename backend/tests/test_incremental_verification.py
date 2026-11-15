"""La verificación incremental no deja de ver nada de lo que veía la completa.

Por qué existe (2026-11-03): con 40 días simulados, `/api/status` tardaba ~3,7-10 s y el 75 % era
`verify_integrity()` recalculando el hash de contenido de ~94 000 asientos y releyendo la base
entera en cada consulta. Ahora, si la anterior salió bien, se verifica a fondo solo lo nuevo, y lo
ya verificado se da por intacto solo si se sabe sin releerlo: en memoria, porque la lista y los
payloads vigilados cuentan cada cambio; en disco, porque los contadores de SQLite no se han movido
salvo por las escrituras del propio almacén (`compliance/record-integrity.md` §3.5 bis).

Qué fijan estas pruebas, cada una ejecutando el ataque entre dos verificaciones:
- una edición del disco sobre una fila ya verificada se detecta en la siguiente, por la misma
  conexión, por otra conexión o con una escritura propia en medio;
- lo añadido legítimamente se verifica, y solo eso;
- una mutación de la memoria —payload, asiento, lista, registro— se detecta;
- una lápida o una enmienda nuevas, o un ancla, devuelven a la verificación completa;
- y que copiar un payload no se confunde con mutarlo.
"""

import copy
import datetime as dt
import json
import sqlite3
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core import ledger as ledger_module
from app.core import storage as storage_module
from app.core.ledger import (
    REDACTION_ENTRY_TYPE,
    HashChainLedger,
    Identity,
    KeyRegistry,
    RedactionAuthority,
)
from app.core.storage import LedgerRow, ObservationRow, ObservationStore
from app.ingest.fhir import observation

NOW = dt.datetime(2026, 11, 14, 8, 0, tzinfo=dt.UTC)
AUDITOR = Identity.generate("emma-audit")
AUTHORITY = RedactionAuthority.of(AUDITOR)
WEARABLE = Identity.generate("wearable-01")


def _record(store: ObservationStore, values: list[float], offset: int = 0) -> None:
    store.record_many(
        [
            observation(
                "heart-rate", value, NOW + dt.timedelta(minutes=offset + minute), "crew-01", "t"
            )
            for minute, value in enumerate(values)
        ],
        WEARABLE,
    )


@pytest.fixture(params=["fichero", "memoria"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> ObservationStore:
    """Las dos bases: la de fichero, que otro proceso puede editar, y la de memoria, que es la que
    usa la API y solo se edita por la misma conexión."""
    if request.param == "fichero":
        created = ObservationStore.at(tmp_path / "emma.db", AUTHORITY)
    else:
        created = ObservationStore.in_memory(AUTHORITY)
    _record(created, [60.0, 61.0, 62.0, 63.0, 64.0])
    return created


@pytest.fixture
def file_store(tmp_path: Path) -> ObservationStore:
    created = ObservationStore.at(tmp_path / "emma.db", AUTHORITY)
    _record(created, [60.0, 61.0, 62.0, 63.0, 64.0])
    return created


@pytest.fixture
def checked(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Los índices cuyo contenido recalcula `verify()`: lo que se verifica a fondo."""
    seen: list[int] = []
    original = ledger_module._check_content

    def spy(entry: Any, tombstone: Any) -> str | None:
        seen.append(entry.index)
        return original(entry, tombstone)

    monkeypatch.setattr(ledger_module, "_check_content", spy)
    return seen


def _edit_ledger_payload(session: Session) -> None:
    row = session.get(LedgerRow, 2)
    assert row is not None and row.payload is not None
    payload = json.loads(row.payload)
    payload["value"] = 140.0
    row.payload = json.dumps(payload)


def _edit_observation_value(session: Session) -> None:
    session.query(ObservationRow).filter_by(ledger_index=1).one().value = 141.0


def _edit_signature(session: Session) -> None:
    row = session.get(LedgerRow, 0)
    assert row is not None
    row.signature = "0" * 128


# --------------------------------------------------------------------------- #
# El disco
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "tamper",
    [_edit_ledger_payload, _edit_observation_value, _edit_signature],
    ids=["asiento", "lectura", "firma"],
)
def test_editing_a_verified_row_by_the_same_connection_is_detected(
    store: ObservationStore, tamper: Callable[[Session], None]
) -> None:
    """Por la conexión del almacén: con la base en memoria es la única que existe, y lo que
    escribe no mueve `data_version`. Lo ve `total_changes`."""
    assert store.verify_integrity().ok
    assert store.verify_integrity().ok

    with Session(store.engine) as session:
        tamper(session)
        session.commit()

    assert not store.verify_integrity().ok


def test_editing_the_file_from_another_connection_is_detected(
    file_store: ObservationStore, tmp_path: Path
) -> None:
    """Otro proceso con cualquier cliente de SQLite: lo ve `data_version`."""
    assert file_store.verify_integrity().ok

    other = sqlite3.connect(tmp_path / "emma.db")
    other.execute("UPDATE observations SET value = 141.0 WHERE ledger_index = 1")
    other.commit()
    other.close()

    result = file_store.verify_integrity()
    assert not result.ok
    assert result.failed_index == 1


def test_a_schema_change_is_detected(store: ObservationStore) -> None:
    """Borrar y rehacer una tabla no cuenta en `total_changes`; lo ve `schema_version`.

    Con `observations`, cuyas filas ya verificadas no se releen por el camino corto: vaciada así,
    solo la verificación completa echa en falta las lecturas.
    """
    assert store.verify_integrity().ok
    with store.engine.begin() as connection:
        ddl = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'observations'"
        ).scalar_one()
        connection.exec_driver_sql("DROP TABLE observations")
        connection.exec_driver_sql(ddl)

    result = store.verify_integrity()
    assert not result.ok
    assert result.failed_index == 0


def test_an_edit_followed_by_an_own_write_is_not_absorbed(store: ObservationStore) -> None:
    """La escritura propia mueve `total_changes`: si se anotara sin mirar antes, la edición ajena
    de en medio quedaría dentro de esa subida."""
    assert store.verify_integrity().ok
    with Session(store.engine) as session:
        _edit_ledger_payload(session)
        session.commit()

    _record(store, [65.0], offset=10)

    result = store.verify_integrity()
    assert not result.ok
    assert result.failed_index == 2


def test_another_connection_writing_during_an_own_write_is_not_absorbed(
    file_store: ObservationStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Al terminar la escritura propia solo se anota `total_changes`: un `data_version` movido
    no es de esta escritura y no se da por bueno."""
    assert file_store.verify_integrity().ok
    original = storage_module._ledger_row

    def edit_meanwhile(entry: Any) -> Any:
        other = sqlite3.connect(tmp_path / "emma.db")
        other.execute("UPDATE observations SET value = 141.0 WHERE ledger_index = 1")
        other.commit()
        other.close()
        return original(entry)

    monkeypatch.setattr(storage_module, "_ledger_row", edit_meanwhile)
    _record(file_store, [65.0], offset=10)
    monkeypatch.setattr(storage_module, "_ledger_row", original)

    result = file_store.verify_integrity()
    assert not result.ok
    assert result.failed_index == 1


# --------------------------------------------------------------------------- #
# Lo nuevo, y solo lo nuevo
# --------------------------------------------------------------------------- #


def test_legitimate_appends_are_verified_and_only_they(
    store: ObservationStore, checked: list[int]
) -> None:
    assert store.verify_integrity().ok
    assert checked == list(range(5))  # la primera, entera

    checked.clear()
    _record(store, [65.0, 66.0], offset=10)
    assert store.verify_integrity().ok
    assert checked == [5, 6]

    checked.clear()
    assert store.verify_integrity().ok
    assert checked == []


def test_a_write_rejected_before_touching_the_base_keeps_the_short_path(
    store: ObservationStore, checked: list[int]
) -> None:
    """Una fuente que reintenta una lectura inválida no devuelve cada consulta a la completa."""
    assert store.verify_integrity().ok
    stranger = Identity.generate("wearable-01")  # mismo nombre, otra clave: se rechaza
    with pytest.raises(ledger_module.KeyConflict):
        store.record(observation("heart-rate", 70.0, NOW, "crew-01", "t"), stranger)

    checked.clear()
    assert store.verify_integrity().ok
    assert checked == []


def test_an_unreadable_mark_falls_back_to_the_full_check(
    store: ObservationStore, checked: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si SQLite no da sus contadores, no hay camino corto, ni un 500."""
    assert store.verify_integrity().ok
    monkeypatch.setattr(store, "_disk_mark", lambda: None)
    checked.clear()
    assert store.verify_integrity().ok
    assert checked == list(range(5))


def test_a_new_row_that_disagrees_with_its_entry_is_detected(store: ObservationStore) -> None:
    """Lo nuevo se coteja con el disco igual que antes: la fila de la lectura nueva, también."""
    assert store.verify_integrity().ok
    _record(store, [65.0], offset=10)
    with Session(store.engine) as session:
        session.query(ObservationRow).filter_by(ledger_index=5).one().value = 165.0
        session.commit()

    result = store.verify_integrity()
    assert not result.ok
    assert result.failed_index == 5


def test_status_with_new_data_still_reads_the_whole_reading_set(store: ObservationStore) -> None:
    """La consulta del motor no cambia: todas las lecturas, también tras el camino corto."""
    assert store.verify_integrity().ok
    _record(store, [65.0], offset=10)
    assert store.verify_integrity().ok
    assert [reading.value for reading in store.query("crew-01")] == [
        60.0, 61.0, 62.0, 63.0, 64.0, 65.0,
    ]


def test_a_redaction_or_an_amendment_goes_back_to_the_full_check(
    store: ObservationStore, checked: list[int]
) -> None:
    """Las dos dependen de un asiento anterior, y redactar reescribe la memoria."""
    assert store.verify_integrity().ok
    corrected = observation("heart-rate", 71.0, NOW + dt.timedelta(minutes=1), "crew-01", "t")
    store.amend(1, corrected, WEARABLE, "lectura mal transcrita")
    checked.clear()
    assert store.verify_integrity().ok
    assert checked[0] == 0

    store.redact(3, AUDITOR, "atribuida al tripulante equivocado", "cirujano")
    checked.clear()
    assert store.verify_integrity().ok
    assert checked[0] == 0


def test_an_anchor_always_gets_the_full_check(
    store: ObservationStore, checked: list[int]
) -> None:
    assert store.verify_integrity().ok
    anchor = store.ledger.anchor()
    checked.clear()
    assert store.verify_integrity(anchor).ok
    assert checked == list(range(5))


# --------------------------------------------------------------------------- #
# La memoria
# --------------------------------------------------------------------------- #


def _mutate_value(store: ObservationStore) -> None:
    store.ledger._entries[2].payload["value"] = 140.0  # type: ignore[index]


def _pop_salt(store: ObservationStore) -> None:
    store.ledger._entries[2].payload.pop("_salt")  # type: ignore[union-attr]


def _update_payload(store: ObservationStore) -> None:
    store.ledger._entries[2].payload.update(value=140.0)  # type: ignore[union-attr]


def _replace_entry(store: ObservationStore) -> None:
    entry = store.ledger._entries[2]
    store.ledger._entries[2] = replace(entry, payload={**(entry.payload or {}), "value": 140.0})


def _swap_the_list(store: ObservationStore) -> None:
    """Otra lista vigilada, sin reescrituras propias: solo la identidad la delata."""
    swapped = ledger_module._EntryList()
    swapped.extend(
        replace(entry, payload={**(entry.payload or {}), "value": 140.0})
        if entry.index == 2 else entry
        for entry in store.ledger._entries
    )
    store.ledger._entries = swapped


def _unpin_the_key(store: ObservationStore) -> None:
    store.registry._keys.pop(WEARABLE.identity_id)


@pytest.mark.parametrize(
    "tamper",
    [_mutate_value, _pop_salt, _update_payload, _replace_entry, _swap_the_list, _unpin_the_key],
    ids=["valor", "pop", "update", "asiento", "lista", "registro"],
)
def test_mutating_verified_memory_is_detected(
    store: ObservationStore, tamper: Callable[[ObservationStore], None]
) -> None:
    assert store.verify_integrity().ok
    assert store.verify_integrity().ok

    tamper(store)

    assert not store.verify_integrity().ok


def test_a_list_that_is_not_watched_is_never_trusted(store: ObservationStore) -> None:
    """Una lista normal en el sitio de la vigilada verifica, pero no deja nada por intacto:
    lo que se cambie en ella después no deja rastro."""
    store.ledger._entries = list(store.ledger._entries)
    assert store.verify_integrity().ok

    store.ledger._entries[2] = replace(
        store.ledger._entries[2], payload={**(store.ledger._entries[2].payload or {}), "value": 1.0}
    )

    assert not store.verify_integrity().ok


def _bare_ledger(authority: RedactionAuthority | None = None) -> HashChainLedger:
    ledger = HashChainLedger(KeyRegistry(), redaction_authority=authority)
    ledger.registry.register(WEARABLE.identity_id, WEARABLE.public_key_hex)
    for position in range(3):
        ledger.append("t", {"i": position}, WEARABLE)
    return ledger


def test_an_unpinned_key_is_seen_by_the_bare_ledger() -> None:
    """Sin almacén no hay tabla de claves que comparar: el registro va en la marca."""
    ledger = _bare_ledger()
    verified = (len(ledger), ledger.memory_mark())
    assert ledger.verify(trusted_prefix=verified).ok

    ledger.registry._keys[WEARABLE.identity_id] = Identity.generate("x").public_key_hex

    assert not ledger.verify(trusted_prefix=verified).ok


def test_another_authority_is_seen_by_the_bare_ledger() -> None:
    """Una lápida ya verificada deja de valer con otra autoridad, y eso no lo cuenta la lista."""
    ledger = _bare_ledger(AUTHORITY)
    ledger.redact(1, AUDITOR, "atribuida al tripulante equivocado", "cirujano")
    verified = (len(ledger), ledger.memory_mark())
    assert ledger.verify(trusted_prefix=verified).ok

    ledger.redaction_authority = RedactionAuthority.of(Identity.generate("emma-audit"))

    assert not ledger.verify(trusted_prefix=verified).ok


def test_a_nested_mutation_is_detected() -> None:
    """Lo anidado también está vigilado: la lista dentro de un payload, por ejemplo."""
    ledger = HashChainLedger(KeyRegistry())
    ledger.registry.register(WEARABLE.identity_id, WEARABLE.public_key_hex)
    for position in range(3):
        ledger.append("t", {"series": [position, {"k": [1, 2]}]}, WEARABLE)
    assert ledger.verify().ok
    verified = (len(ledger), ledger.memory_mark())
    assert ledger.verify(trusted_prefix=verified).ok

    ledger._entries[1].payload["series"][1]["k"].append(3)  # type: ignore[index]

    assert ledger.reusable_prefix(verified, ledger._view()) == 0
    assert not ledger.verify(trusted_prefix=verified).ok


def test_a_tombstone_slipped_behind_verified_entries_is_not_trusted() -> None:
    """Una lápida nueva apunta a un asiento ya verificado: hay que mirar ese asiento otra vez.

    Aquí se cuela sin pasar por `redact()`, que es lo que haría vaciar el contenido de la diana:
    con la diana intacta, la verificación completa dice "redacción registrada pero el contenido
    sigue presente", y la incremental, si no volviera atrás, no lo vería.
    """
    ledger = HashChainLedger(KeyRegistry(), redaction_authority=AUTHORITY)
    ledger.registry.register(WEARABLE.identity_id, WEARABLE.public_key_hex)
    for position in range(3):
        ledger.append("t", {"i": position}, WEARABLE)
    verified = (len(ledger), ledger.memory_mark())
    assert ledger.verify(trusted_prefix=verified).ok
    target = ledger._entries[1]
    ledger._append(
        REDACTION_ENTRY_TYPE,
        {
            "target_index": 1,
            "target_entry_hash": target.entry_hash(),
            "target_content_hash": target.content_hash,
            "reason": "colada",
            "requested_by": "nadie",
        },
        AUDITOR,
    )

    result = ledger.verify(trusted_prefix=verified)
    assert not result.ok
    assert result.failed_index == 1


def test_copies_of_a_payload_are_not_mutations(store: ObservationStore) -> None:
    """Copiar un payload guardado da un `dict` normal: cambiar la copia no es cambiar el
    asiento, y no devuelve a la verificación completa ni a recalcular lecturas."""
    assert store.verify_integrity().ok
    mark = store.ledger.memory_mark()
    payload = store.ledger._entries[2].payload
    for duplicate in (copy.copy(payload), copy.deepcopy(payload), dict(payload or {})):
        assert type(duplicate) is dict
        duplicate["value"] = 140.0
    assert store.ledger.unchanged_since(mark)
    assert store.ledger[2].payload is not None and store.ledger[2].payload["value"] == 62.0


def test_watched_payloads_serialise_and_hash_as_before(store: ObservationStore) -> None:
    """La clase vigilada no cambia los bytes canónicos: el hash es el mismo que el firmado."""
    entry = store.ledger._entries[2]
    assert entry.payload is not None
    assert type(entry.payload) is not dict
    assert ledger_module.canonical_bytes(entry.payload) == ledger_module.canonical_bytes(
        dict(entry.payload)
    )
    assert ledger_module.sha256_hex(ledger_module.canonical_bytes(entry.payload)) == (
        entry.content_hash
    )


def test_a_reopened_store_watches_what_it_loaded(tmp_path: Path) -> None:
    """Lo cargado de disco entra vigilado igual que lo escrito."""
    created = ObservationStore.at(tmp_path / "emma.db", AUTHORITY)
    _record(created, [60.0, 61.0, 62.0])
    reopened = ObservationStore.at(tmp_path / "emma.db", AUTHORITY)
    assert reopened.verify_integrity().ok
    assert reopened.verify_integrity().ok

    reopened.ledger._entries[1].payload["value"] = 140.0  # type: ignore[index]

    assert not reopened.verify_integrity().ok


def test_query_rechecks_readings_after_a_memory_mutation(store: ObservationStore) -> None:
    """El atajo de `query()` —no recalcular lo comprobado— se cae con la primera mutación."""
    assert store.verify_integrity().ok
    assert len(store.query("crew-01")) == 5

    _mutate_value(store)

    with pytest.raises(storage_module.TamperedRecordError, match="asiento 2"):
        store.query("crew-01")
