"""Ataques contra el almacen y la API, de la segunda revision adversaria (2026-09-22).

Cada prueba reproduce un ataque o un fallo que se confirmo ejecutandolo contra la
version anterior. La primera es la que bloqueo el arreglo de la redaccion: quien
pudiera escribir en la base, sin ninguna clave privada del sistema, borraba una
lectura ya anclada y `verify_integrity()` salia en verde, tambien contra el ancla.
"""

import datetime as dt
import json
import sys
import threading
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from app.api.routes import get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.core.ledger import (
    REDACTION_ENTRY_TYPE,
    Identity,
    LedgerEntry,
    RedactionAuthority,
    UntrustedSigner,
    canonical_bytes,
    sha256_hex,
)
from app.core.storage import (
    LedgerRow,
    ObservationRow,
    ObservationStore,
    TamperedRecordError,
    TrustedKeyRow,
    _ledger_row,
)
from app.ingest.fhir import observation
from app.main import app

NOW = dt.datetime(2026, 11, 14, 8, 0, tzinfo=dt.UTC)
VALUES = [60.0, 61.0, 62.0, 190.0]
AUDITOR = Identity.generate("emma-audit")
AUTHORITY = RedactionAuthority.of(AUDITOR)


@pytest.fixture
def db(tmp_path: Path) -> Path:
    """Almacen en fichero con cuatro lecturas; la ultima, una taquicardia de 190."""
    path = tmp_path / "emma.db"
    store = ObservationStore.at(path, AUTHORITY)
    wearable = Identity.generate("wearable-01")
    for minute, value in enumerate(VALUES):
        store.record(
            observation("heart-rate", value, NOW + dt.timedelta(minutes=minute), "crew-01", "w"),
            wearable,
        )
    return path


def _reopen(db: Path) -> ObservationStore:
    return ObservationStore.at(db, AUTHORITY)


def _forged_tombstone(store: ObservationStore, target_index: int, signer: Identity) -> LedgerEntry:
    target, previous = store.ledger[target_index], store.ledger[len(store.ledger) - 1]
    payload = {
        "target_index": target_index,
        "target_entry_hash": target.entry_hash(),
        "target_content_hash": target.content_hash,
        "reason": "atribuida al tripulante equivocado",
        "requested_by": "cirujano",
    }
    tombstone = LedgerEntry(
        index=len(store.ledger),
        recorded=previous.recorded,
        entry_type=REDACTION_ENTRY_TYPE,
        content_hash=sha256_hex(canonical_bytes(payload)),
        prev_hash=previous.entry_hash(),
        signer=signer.identity_id,
        signer_public_key=signer.public_key_hex,
        signature="",
        payload=payload,
    )
    return replace(tombstone, signature=signer.sign(tombstone.signing_material()))


# --------------------------------------------------------------------------- #
# Almacen
# --------------------------------------------------------------------------- #


def test_a_forged_tombstone_cannot_erase_an_anchored_reading(db: Path) -> None:
    """El bloqueante: alta de una identidad en `trusted_keys`, lapida firmada con ella,
    payload a NULL y fila de `observations` borrada. Todo en SQLite, sin claves."""
    store = _reopen(db)
    anchor = store.anchor()
    intruder = Identity.generate("mantenimiento")
    tombstone = _forged_tombstone(store, 3, intruder)

    with Session(store.engine) as session:
        session.add(
            TrustedKeyRow(identity_id=intruder.identity_id, public_key=intruder.public_key_hex)
        )
        session.add(_ledger_row(tombstone))
        row = session.get(LedgerRow, 3)
        assert row is not None
        row.payload, row.redacted = None, True
        session.query(ObservationRow).filter_by(ledger_index=3).delete()
        session.commit()

    tampered = _reopen(db)
    assert not tampered.verify_integrity()
    assert not tampered.verify_integrity(anchor=anchor)
    with pytest.raises(TamperedRecordError, match="asiento 3"):
        tampered.query("crew-01")


def test_a_legitimate_redaction_survives_restart_with_the_same_authority(db: Path) -> None:
    store = _reopen(db)
    anchor = store.anchor()
    store.redact(3, AUDITOR, "atribuida al tripulante equivocado", "cirujano")

    reopened = _reopen(db)
    assert reopened.verify_integrity(anchor=anchor)
    assert [obs.value for obs in reopened.query("crew-01")] == VALUES[:3]


def test_existing_tombstones_need_the_same_authority_after_restart(db: Path) -> None:
    """LIMITE DECLARADO: la autoridad tiene que ser la misma entre reinicios. Con otra,
    o sin ninguna, las lapidas anteriores no justifican sus supresiones."""
    _reopen(db).redact(3, AUDITOR, "motivo", "cirujano")
    other = RedactionAuthority.of(Identity.generate("emma-audit"))

    assert not ObservationStore.at(db, other).verify_integrity()
    assert not ObservationStore.at(db).verify_integrity()


def test_an_observation_row_pointing_at_a_tombstone_is_a_failure_not_a_crash(db: Path) -> None:
    """Llegaba a `payload["subject"]` de la lapida: KeyError y `/api/status` en 500."""
    store = _reopen(db)
    store.redact(0, AUDITOR, "motivo", "cirujano")  # la lapida queda en el 4
    with Session(store.engine) as session:
        session.query(ObservationRow).filter_by(ledger_index=1).one().ledger_index = 4
        session.commit()

    result = store.verify_integrity()

    assert not result
    assert result.failed_index == 4


def test_unreadable_values_on_disk_are_a_failure_not_a_crash(db: Path) -> None:
    store = _reopen(db)
    assert store.verify_integrity()
    with Session(store.engine) as session:
        session.execute(text("UPDATE ledger_entries SET recorded = 'basura' WHERE \"index\" = 1"))
        session.commit()

    result = store.verify_integrity()

    assert not result
    assert "ilegibles" in (result.reason or "")


def test_a_malformed_tombstone_can_still_be_shown(db: Path) -> None:
    """`_audit_view` indexaba la lapida sin defensas: una sin `reason` tumbaba
    `/api/audit` con un 500 justo cuando habia que ensenarla. La lapida se crea en
    memoria, firmada por la autoridad; el caso en disco es el de la cabecera danada."""
    store = _reopen(db)
    store.ledger._append(REDACTION_ENTRY_TYPE, {"basura": True}, AUDITOR)

    trail = store.audit_trail()

    assert trail[-1]["redaction"] == {"target_index": None, "reason": None, "requested_by": None}
    assert not store.verify_integrity()


def test_a_reading_in_another_timezone_is_not_a_false_alarm(db: Path) -> None:
    """Sin ataque: SQLite descartaba el desfase y la verificacion del disco denunciaba
    una manipulacion para siempre."""
    store = _reopen(db)
    cest = dt.timezone(dt.timedelta(hours=2))
    reading = observation(
        "heart-rate", 70.0, dt.datetime(2026, 11, 14, 10, 0, tzinfo=cest), "crew-01", "w"
    )
    store.record(reading, Identity.generate("wearable-02"))

    assert store.verify_integrity()
    assert _reopen(db).verify_integrity()


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


REDACTION = {"reason": "atribuida al tripulante equivocado", "requested_by": "cirujano"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def test_redaction_without_a_provisioned_authority_is_unavailable(client: TestClient) -> None:
    reset_store(ObservationStore.in_memory())
    client.post("/api/observations", json={"key": "heart-rate", "value": 60.0})

    assert client.post("/api/audit/redact/0", json=REDACTION).status_code == 503
    assert client.get("/api/audit").json()["total_entries"] == 1


def test_an_invisible_reason_is_rejected(client: TestClient) -> None:
    client.post("/api/observations", json={"key": "heart-rate", "value": 60.0})
    invisible = {"reason": "​", "requested_by": "​"}

    assert client.post("/api/audit/redact/0", json=invisible).status_code == 422


def test_a_key_conflict_is_a_conflict_not_a_server_error(client: TestClient) -> None:
    """Una fuente cuya clave ya esta fijada llega con otra: 409, no un 500 generico."""
    get_store().registry.register("manual", Identity.generate("manual").public_key_hex)

    response = client.post("/api/observations", json={"key": "heart-rate", "value": 60.0})

    assert response.status_code == 409
    assert "firmante no autorizado" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# Tercera revision (2026-09-22)
# --------------------------------------------------------------------------- #


def _edit_row(db: Path, index: int, **changes: object) -> None:
    with Session(_reopen(db).engine) as session:
        row = session.get(LedgerRow, index)
        assert row is not None
        for column, value in changes.items():
            setattr(row, column, value)
        session.commit()


def _sql(db: Path, statement: str) -> None:
    with Session(_reopen(db).engine) as session:
        session.execute(text(statement))
        session.commit()


def _rehashed_payload(db: Path, index: int, **changes: object) -> dict[str, object]:
    """El payload del asiento con `changes`, y su `content_hash` recalculado: un
    SHA-256 no necesita ninguna clave."""
    with Session(_reopen(db).engine) as session:
        row = session.get(LedgerRow, index)
        assert row is not None and row.payload is not None
        payload: dict[str, object] = {**json.loads(row.payload), **changes}
    return {"payload": json.dumps(payload), "content_hash": sha256_hex(canonical_bytes(payload))}


@pytest.mark.parametrize(
    "tamper",
    [
        lambda db: _edit_row(db, 3, **_rehashed_payload(db, 3, subject="crew-99")),
        lambda db: _edit_row(db, 3, **_rehashed_payload(db, 3, value=72.0)),
        lambda db: _edit_row(db, 3, entry_type="vital-observation-x"),
    ],
    ids=["otro-tripulante-con-hash", "otro-valor-con-hash", "otro-tipo"],
)
def test_query_only_serves_a_chain_whose_signatures_hold(db: Path, tamper: object) -> None:
    """Tercera revision: la marca de agua comparaba el payload con un `content_hash`
    que nadie habia verificado. Recalcular el hash, o cambiar el tipo del asiento,
    hacia que `query()` omitiera la taquicardia —o la entregara como 72— sin error."""
    tamper(db)  # type: ignore[operator]

    store = _reopen(db)
    with pytest.raises(TamperedRecordError, match="asiento 3"):
        store.query("crew-01")
    with pytest.raises(TamperedRecordError, match="asiento 3"):
        store.subjects()
    assert not store.verify_integrity()


def test_a_tombstone_copied_from_another_store_justifies_nothing(
    db: Path, tmp_path: Path
) -> None:
    """Dos almacenes con la misma autoridad —como todos los de la API—: la lapida
    legitima de uno, copiada byte a byte en el otro, suprimia alli una lectura."""
    source = ObservationStore.at(tmp_path / "otro.db", AUTHORITY)
    wearable = Identity.generate("wearable-01")
    for minute, value in enumerate(VALUES):
        source.record(
            observation("heart-rate", value, NOW + dt.timedelta(minutes=minute), "crew-01", "w"),
            wearable,
        )
    tombstone = source.redact(0, AUDITOR, "motivo", "cirujano").tombstone

    with Session(_reopen(db).engine) as session:
        session.add(_ledger_row(tombstone))
        row = session.get(LedgerRow, 0)
        assert row is not None
        row.payload, row.redacted = None, True
        session.query(ObservationRow).filter_by(ledger_index=0).delete()
        session.commit()

    store = _reopen(db)
    assert 0 not in store.ledger.redacted_indices()
    with pytest.raises(TamperedRecordError, match="asiento 0"):
        store.query("crew-01")
    assert not store.verify_integrity()


def test_the_api_refuses_to_analyse_an_unsigned_chain(db: Path, tmp_path: Path) -> None:
    _edit_row(db, 3, entry_type="vital-observation-x")
    reset_store(_reopen(db))
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    try:
        client = TestClient(app)
        for path in ("/api/observations", "/api/status"):
            response = client.get(path)
            assert response.status_code == 409, path
            assert "asiento 3" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        reset_store(None)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE trusted_keys SET identity_id = X'77' WHERE identity_id = 'wearable-01'",
        "UPDATE observations SET ledger_index = 'abc' WHERE ledger_index = 1",
        "UPDATE observations SET ledger_index = 1.5 WHERE ledger_index = 1",
    ],
    ids=["clave-blob", "indice-texto", "indice-decimal"],
)
def test_odd_types_on_disk_are_a_failure_not_a_crash(db: Path, statement: str) -> None:
    """En caliente, con el almacen abierto: comparar u ordenar valores de disco de un
    tipo inesperado lanzaba TypeError fuera del `try`, y `/api/status` daba 500."""
    store = _reopen(db)
    store.record(
        observation("heart-rate", 65.0, NOW + dt.timedelta(hours=1), "crew-01", "w"),
        Identity.generate("wearable-02"),
    )
    assert store.verify_integrity()
    with Session(store.engine) as session:
        session.execute(text(statement))
        session.commit()

    assert not store.verify_integrity()
    verification, anchor, _trail, _total = store.audit_snapshot()
    assert not verification


@pytest.mark.parametrize(
    ("column", "value"),
    [("signature", b"\x00"), ("content_hash", b"\x00"), ("signer", b"\x00")],
)
def test_binary_header_fields_are_a_failure_not_a_crash(
    db: Path, column: str, value: bytes
) -> None:
    """Tras reabrir: un campo de cabecera en BLOB llegaba a `signing_material()` y
    lanzaba TypeError; con `signer`, reventaba el calculo del ancla en `/api/audit`."""
    _edit_row(db, 1, **{column: value})

    store = _reopen(db)
    result = store.verify_integrity()
    assert not result
    assert result.failed_index == 1
    verification, anchor, _trail, _total = store.audit_snapshot()
    assert not verification
    assert anchor is None
    with pytest.raises(ValueError, match="no se puede anclar"):
        store.anchor()
    with pytest.raises(TamperedRecordError, match="asiento 1"):
        store.query("crew-01")


def test_a_damaged_tombstone_header_is_a_failure_not_a_crash(db: Path) -> None:
    _reopen(db).redact(0, AUDITOR, "motivo", "cirujano")
    _edit_row(db, 4, prev_hash=b"\x00")

    store = _reopen(db)
    # Falla en el 0, no en la lapida: con la cabecera danada la lapida deja de
    # justificar la supresion, y ese es el primer asiento que no se sostiene.
    with pytest.raises(TamperedRecordError, match="asiento 0"):
        store.query("crew-01")
    assert store.verify_integrity().failed_index == 0


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE ledger_entries SET recorded = 'basura' WHERE \"index\" = 1",
        "UPDATE ledger_entries SET payload = '{roto' WHERE \"index\" = 1",
        "UPDATE trusted_keys SET public_key = 'zz'",
    ],
    ids=["fecha-ilegible", "json-roto", "clave-no-hex"],
)
def test_a_corrupted_store_still_opens_and_says_so(db: Path, statement: str) -> None:
    """Una base corrupta en reposo impedia arrancar. Un monitor de salud tiene que
    abrir y declarar la integridad rota: la tripulacion sigue necesitandolo."""
    _sql(db, statement)

    store = _reopen(db)
    assert not store.verify_integrity()
    with pytest.raises(TamperedRecordError):
        store.query("crew-01")


def test_redaction_cannot_launder_a_tampered_entry(db: Path) -> None:
    """La autoridad firmaba una lapida sobre un asiento que ya no verificaba, y
    `verify()` pasaba a verde: la prueba de la manipulacion quedaba sustituida por una
    rectificacion de apariencia legitima."""
    store = _reopen(db)
    store.ledger._entries[2].payload["value"] = 72.0  # type: ignore[index]
    assert not store.verify_integrity()

    with pytest.raises(ValueError, match="no verifica"):
        store.redact(2, AUDITOR, "motivo", "cirujano")
    assert not store.verify_integrity()
    assert len(store.ledger) == len(VALUES)


def test_concurrent_first_requests_share_one_store() -> None:
    """Las primeras peticiones simultaneas creaban almacenes distintos, y las lecturas
    confirmadas con 201 en los que se perdian desaparecian sin que nada lo detectara."""
    previous = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    reset_store(None)
    stores: list[ObservationStore] = []
    try:
        threads = [threading.Thread(target=lambda: stores.append(get_store())) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sys.setswitchinterval(previous)
        reset_store(None)

    assert len({id(store) for store in stores}) == 1


# --------------------------------------------------------------------------- #
# Cuarta revision (2026-09-22)
# --------------------------------------------------------------------------- #

WEARABLE = Identity.generate("wearable-01")
SOURCES = {WEARABLE.identity_id: WEARABLE.public_key_hex}
# La taquicardia en el asiento 1, que no es el ultimo: truncar la cola no basta.
TACHY = [60.0, 190.0, 61.0, 62.0]


def _provisioned(path: Path) -> ObservationStore:
    return ObservationStore.at(path, AUTHORITY, trusted_sources=SOURCES)


def _seed(store: ObservationStore) -> None:
    for minute, value in enumerate(TACHY):
        store.record(
            observation("heart-rate", value, NOW + dt.timedelta(minutes=minute), "crew-01", "w"),
            WEARABLE,
        )


@pytest.fixture
def provisioned_db(tmp_path: Path) -> Path:
    path = tmp_path / "emma.db"
    _seed(_provisioned(path))
    return path


def _rechain_without_the_tachycardia(
    path: Path, opener: Callable[[Path], ObservationStore]
) -> None:
    """El ataque de la cuarta revision, sin ninguna clave del sistema: borrar desde la
    taquicardia en adelante y volver a encadenar las lecturas inocuas con una identidad
    nueva dada de alta en `trusted_keys`."""
    store = opener(path)
    head, keep = store.ledger[0], [store.ledger[2], store.ledger[3]]
    intruder = Identity.generate("wearable-01-cal")
    with Session(store.engine) as session:
        session.execute(delete(ObservationRow).where(ObservationRow.ledger_index >= 1))
        session.execute(delete(LedgerRow).where(LedgerRow.index >= 1))
        session.add(
            TrustedKeyRow(identity_id=intruder.identity_id, public_key=intruder.public_key_hex)
        )
        previous = head
        for index, original in enumerate(keep, start=1):
            forged = replace(
                original,
                index=index,
                prev_hash=previous.entry_hash(),
                signer=intruder.identity_id,
                signer_public_key=intruder.public_key_hex,
                signature="",
            )
            forged = replace(forged, signature=intruder.sign(forged.signing_material()))
            session.add(_ledger_row(forged))
            payload = original.payload
            assert payload is not None
            session.add(
                ObservationRow(
                    subject=payload["subject"], key=payload["key"], value=payload["value"],
                    effective=dt.datetime.fromisoformat(payload["effective"]).astimezone(dt.UTC),
                    source=payload["source"], context=payload["context"],
                    confidence=payload["confidence"], ledger_index=index,
                )
            )
            previous = forged
        session.commit()


def test_a_provisioned_store_rejects_rechaining_with_a_new_identity(provisioned_db: Path) -> None:
    """Cuarta revision: con el registro aprendido de la base, reencadenar con una
    identidad nueva hacia desaparecer la taquicardia con la verificacion en verde."""
    _rechain_without_the_tachycardia(provisioned_db, _provisioned)

    store = _provisioned(provisioned_db)
    result = store.verify_integrity()
    assert not result
    assert result.failed_index == 1
    with pytest.raises(TamperedRecordError, match="asiento 1"):
        store.query("crew-01")


def test_without_provisioning_rechaining_is_invisible(tmp_path: Path) -> None:
    """LIMITE DECLARADO. Sin fuentes aprovisionadas, el registro se aprende de la base y
    quien escribe en ella puede reencadenar la cola con una identidad nueva. La prueba
    existe para que nadie afirme lo contrario: el remedio es aprovisionar, o un ancla."""
    path = tmp_path / "emma.db"
    _seed(ObservationStore.at(path, AUTHORITY))
    _rechain_without_the_tachycardia(path, lambda p: ObservationStore.at(p, AUTHORITY))

    reopened = ObservationStore.at(path, AUTHORITY)
    assert reopened.verify_integrity()
    assert [obs.value for obs in reopened.query("crew-01")] == [60.0, 61.0, 62.0]


def test_a_provisioned_store_accepts_no_new_signers(provisioned_db: Path) -> None:
    store = _provisioned(provisioned_db)
    stranger = Identity.generate("wearable-02")

    with pytest.raises(UntrustedSigner):
        store.record(observation("heart-rate", 70.0, NOW, "crew-01", "w"), stranger)
    with pytest.raises(UntrustedSigner):
        store.registry.register(stranger.identity_id, stranger.public_key_hex)
    assert store.verify_integrity()


def test_an_extra_trusted_key_on_disk_is_a_failure(provisioned_db: Path) -> None:
    intruder = Identity.generate("mantenimiento")
    with Session(_provisioned(provisioned_db).engine) as session:
        session.add(
            TrustedKeyRow(identity_id=intruder.identity_id, public_key=intruder.public_key_hex)
        )
        session.commit()

    assert not _provisioned(provisioned_db).verify_integrity()


def _statements(db: Path, *statements: str) -> None:
    with Session(_reopen(db).engine) as session:
        for statement in statements:
            session.execute(text(statement))
        session.commit()


def test_undecodable_text_while_running_is_a_failure_not_a_crash(db: Path) -> None:
    """Texto que no es UTF-8 hacia que SQLite lanzara OperationalError al leer: 500 en
    `/api/status`, `/api/audit` y en la redaccion."""
    store = _reopen(db)
    assert store.verify_integrity()
    with Session(store.engine) as session:
        session.execute(
            text("UPDATE observations SET subject = CAST(X'FF' AS TEXT) WHERE ledger_index = 1")
        )
        session.commit()

    assert not store.verify_integrity()
    verification, _anchor, _trail, _total = store.audit_snapshot()
    assert not verification


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE ledger_entries SET signer = CAST(X'FF' AS TEXT) WHERE \"index\" = 1",
        "UPDATE trusted_keys SET public_key = CAST(X'FF' AS TEXT)",
    ],
    ids=["firmante", "clave"],
)
def test_undecodable_text_at_rest_still_opens(db: Path, statement: str) -> None:
    _statements(db, statement)

    store = _reopen(db)
    assert not store.verify_integrity()
    with pytest.raises(TamperedRecordError):
        store.query("crew-01")


@pytest.mark.parametrize("depth", [1200, 3000])
def test_a_deeply_nested_payload_is_a_failure_not_a_crash(db: Path, depth: int) -> None:
    """Un payload anidado a mil niveles agotaba la pila: RecursionError al verificar, y
    a partir de ~3000 niveles el almacen ni siquiera abria."""
    _edit_row(db, 1, payload="[" * depth + "]" * depth)

    store = _reopen(db)
    assert not store.verify_integrity()
    with pytest.raises(TamperedRecordError, match="asiento 1"):
        store.query("crew-01")
    store.audit_trail()


def test_an_unencodable_reason_can_still_be_shown(db: Path) -> None:
    """Una lapida con un sustituto UTF-16 suelto en el motivo tumbaba `/api/audit` al
    serializar la respuesta."""
    tombstone = json.dumps(
        {
            "target_index": 0,
            "target_entry_hash": "",
            "target_content_hash": "",
            "reason": "\ud800",
            "requested_by": "x",
        }
    )
    _edit_row(db, 1, entry_type=REDACTION_ENTRY_TYPE, payload=tombstone)

    store = _reopen(db)
    json.dumps(store.audit_trail(), ensure_ascii=False).encode("utf-8")
    assert not store.verify_integrity()


def test_a_null_on_disk_is_a_failure_not_a_crash(db: Path) -> None:
    store = _reopen(db)
    assert store.verify_integrity()
    with Session(store.engine) as session:
        for statement in (
            "CREATE TABLE observations_copy AS SELECT * FROM observations",
            "DROP TABLE observations",
            "ALTER TABLE observations_copy RENAME TO observations",
            "UPDATE observations SET effective = NULL WHERE ledger_index = 1",
        ):
            session.execute(text(statement))
        session.commit()

    assert not store.verify_integrity()


def test_a_duplicated_trusted_key_still_opens(db: Path) -> None:
    _statements(
        db,
        "CREATE TABLE trusted_keys_copy AS SELECT * FROM trusted_keys",
        "DROP TABLE trusted_keys",
        "ALTER TABLE trusted_keys_copy RENAME TO trusted_keys",
        f"INSERT INTO trusted_keys VALUES ('wearable-01', '{WEARABLE.public_key_hex}')",
    )

    store = _reopen(db)
    assert not store.verify_integrity()


def test_redaction_leaves_no_trace_in_the_file(tmp_path: Path) -> None:
    """Cuarta revision: tras redactar, la lectura seguia en el fichero —sin
    `secure_delete`— y el hash de la lapida se invertia con un diccionario."""
    path = tmp_path / "emma.db"
    store = ObservationStore.at(path, AUTHORITY)
    wearable = Identity.generate("wearable-01")
    store.record(observation("heart-rate", 60.0, NOW, "crew-01", "w"), wearable)
    marked = store.record(
        observation("heart-rate", 187.0, NOW, "crew-01", "marcador-9f3c2a"), wearable
    )

    store.redact(marked.index, AUDITOR, "atribuida al tripulante equivocado", "cirujano")
    store.engine.dispose()

    assert b"marcador-9f3c2a" not in path.read_bytes()


def test_identical_readings_do_not_share_a_content_hash(db: Path) -> None:
    """El hash del contenido lleva una sal aleatoria: sin ella, la misma lectura daba el
    mismo hash, y la lapida permitia recuperar el dato probando candidatos."""
    store = _reopen(db)
    wearable = Identity.generate("wearable-02")
    first = store.record(observation("heart-rate", 187.0, NOW, "crew-01", "w"), wearable)
    second = store.record(observation("heart-rate", 187.0, NOW, "crew-01", "w"), wearable)

    assert first.content_hash != second.content_hash


def test_a_forged_future_timestamp_does_not_drag_the_clock(db: Path) -> None:
    """Una fecha 9999-12-31 en el ultimo asiento se heredaba en todas las escrituras
    siguientes, que quedaban firmadas con ella."""
    _statements(
        db, "UPDATE ledger_entries SET recorded = '9999-12-31 23:59:59.999999' WHERE \"index\" = 3"
    )

    store = _reopen(db)
    store.record(
        observation("heart-rate", 65.0, NOW + dt.timedelta(hours=1), "crew-01", "w"),
        Identity.generate("wearable-02"),
    )

    assert store.ledger[len(store.ledger) - 1].recorded.year < 9999
    assert store.verify_integrity().failed_index == 3


def test_storage_refuses_to_redact_over_a_disk_edit(db: Path) -> None:
    """La guarda de `ObservationStore.redact`: con una edicion del disco en caliente la
    memoria sigue intacta, asi que la comprobacion del ledger no la ve. Sin la guarda,
    redactar ese asiento borraba la prueba de la edicion."""
    store = _reopen(db)
    with Session(store.engine) as session:
        row = session.get(LedgerRow, 2)
        assert row is not None and row.payload is not None
        row.payload = json.dumps({**json.loads(row.payload), "value": 72.0})
        session.commit()

    with pytest.raises(ValueError, match="no verifica"):
        store.redact(2, AUDITOR, "motivo", "cirujano")
    assert not _reopen(db).verify_integrity()


def test_writing_before_the_first_query_does_not_bless_a_tampered_store(db: Path) -> None:
    """La condicion de `_advance_after_own_write`: reabrir una base manipulada, escribir
    y consultar entregaba el dato alterado si la marca avanzaba sin condicion."""
    _edit_row(db, 3, **_rehashed_payload(db, 3, value=72.0))

    store = _reopen(db)
    store.record(
        observation("heart-rate", 65.0, NOW + dt.timedelta(hours=1), "crew-01", "w"),
        Identity.generate("wearable-02"),
    )

    with pytest.raises(TamperedRecordError):
        store.query("crew-01")
    assert not store.verify_integrity()


def test_unencodable_text_through_the_api_is_rejected_not_a_crash(client: TestClient) -> None:
    """Un `subject` con un sustituto UTF-16 suelto llegaba al ledger y salia como 500."""
    # JSON crudo con el escape: `httpx` no sabe codificar el sustituto suelto, pero
    # cualquier cliente puede mandar la secuencia \ud800 y el servidor la decodifica asi.
    headers = {"content-type": "application/json"}
    bad_reading = rb'{"key": "heart-rate", "value": 60.0, "subject": "\ud800"}'
    response = client.post("/api/observations", content=bad_reading, headers=headers)
    assert response.status_code == 422
    bad_frame = rb'{"frame_hex": "0048", "subject": "\ud800"}'
    response = client.post("/api/wearable/ble", content=bad_frame, headers=headers)
    assert response.status_code == 422
    assert client.get("/api/audit").json()["total_entries"] == 0


# --------------------------------------------------------------------------- #
# Quinta revision (2026-09-22)
# --------------------------------------------------------------------------- #


def test_readings_keep_being_recorded_after_a_damaged_entry(db: Path) -> None:
    """`_link_hash`: sin el, escribir detras de un asiento con la cabecera danada era un
    TypeError, y las constantes vitales dejaban de registrarse (500 en la ingesta)."""
    _edit_row(db, 3, signer=b"\x00")

    store = _reopen(db)
    entry = store.record(
        observation("heart-rate", 65.0, NOW + dt.timedelta(hours=1), "crew-01", "w"),
        Identity.generate("wearable-02"),
    )

    assert entry.index == 4
    assert store.verify_integrity().failed_index == 3


def test_a_deep_payload_never_reaches_memory(db: Path) -> None:
    """`_nesting_exceeds`: un payload anidado por debajo del limite de recursion de
    `json.loads`, pero muy por encima de `MAX_JSON_DEPTH`, llegaba entero a memoria."""
    _edit_row(db, 1, payload="[" * 500 + "]" * 500)

    store = _reopen(db)

    assert store.ledger[1].payload == {"_ilegible": "anidamiento excesivo"}
    assert not store.verify_integrity()


def test_adding_a_provisioned_source_is_not_a_false_alarm(provisioned_db: Path) -> None:
    """Dar de alta una fuente nueva en una base existente dejaba la verificacion en rojo
    para siempre, y con ella las redacciones bloqueadas."""
    newcomer = Identity.generate("wearable-02")
    sources = {**SOURCES, newcomer.identity_id: newcomer.public_key_hex}

    store = ObservationStore.at(provisioned_db, AUTHORITY, trusted_sources=sources)
    assert store.verify_integrity()
    store.record(observation("heart-rate", 66.0, NOW, "crew-01", "w"), newcomer)

    reopened = ObservationStore.at(provisioned_db, AUTHORITY, trusted_sources=sources)
    assert reopened.verify_integrity()
    reopened.redact(0, AUDITOR, "motivo", "cirujano")
    assert reopened.verify_integrity()


def test_a_malformed_reading_signed_by_an_intruder_is_a_conflict_not_a_crash(db: Path) -> None:
    """Modo aprendido: una identidad dada de alta en la base firma una lectura sin
    tripulante. `query()` y `subjects()` lanzaban KeyError (500)."""
    store = _reopen(db)
    intruder = Identity.generate("mantenimiento")
    previous = store.ledger[len(store.ledger) - 1]
    payload = {"key": "heart-rate", "value": 60.0}
    forged = LedgerEntry(
        index=len(store.ledger),
        recorded=previous.recorded,
        entry_type="vital-observation",
        content_hash=sha256_hex(canonical_bytes(payload)),
        prev_hash=previous.entry_hash(),
        signer=intruder.identity_id,
        signer_public_key=intruder.public_key_hex,
        signature="",
        payload=payload,
    )
    forged = replace(forged, signature=intruder.sign(forged.signing_material()))
    with Session(store.engine) as session:
        session.add(
            TrustedKeyRow(identity_id=intruder.identity_id, public_key=intruder.public_key_hex)
        )
        session.add(_ledger_row(forged))
        session.commit()

    tampered = _reopen(db)
    with pytest.raises(TamperedRecordError, match="asiento 4"):
        tampered.query("crew-01")
    with pytest.raises(TamperedRecordError, match="asiento 4"):
        tampered.subjects()
    assert not tampered.verify_integrity()
