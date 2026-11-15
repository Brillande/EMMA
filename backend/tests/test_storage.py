"""Almacen: persistencia, auditoria obligatoria e integridad entre sesiones."""

import datetime as dt
import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ledger import Identity, RedactionAuthority
from app.core.storage import LedgerRow, ObservationStore, seed_from_simulator
from app.ingest.fhir import Context, observation
from app.ingest.simulator import PhysiologicalSimulator, Scenario

NOW = dt.datetime(2026, 11, 14, 8, 0, tzinfo=dt.UTC)


@pytest.fixture
def identity() -> Identity:
    return Identity.generate("wearable-01")


@pytest.fixture
def store() -> ObservationStore:
    return ObservationStore.in_memory()


def test_record_and_query(store: ObservationStore, identity: Identity) -> None:
    store.record(observation("heart-rate", 62.0, NOW, "crew-01", "wearable-01"), identity)
    results = store.query("crew-01")

    assert len(results) == 1
    assert results[0].value == 62.0
    assert results[0].effective == NOW


def test_every_write_is_audited(store: ObservationStore, identity: Identity) -> None:
    """21 CFR 11.10(e): no debe existir escritura sin rastro de auditoria."""
    for index in range(5):
        store.record(
            observation("heart-rate", 60.0 + index, NOW, "crew-01", "w"), identity
        )

    assert len(store.ledger) == 5
    assert store.count() == 5
    assert store.verify_integrity()


def test_query_filters(store: ObservationStore, identity: Identity) -> None:
    store.record(observation("heart-rate", 62.0, NOW, "crew-01", "w"), identity)
    store.record(
        observation("hrv-sdnn", 90.0, NOW + dt.timedelta(hours=1), "crew-01", "w"), identity
    )
    store.record(observation("heart-rate", 70.0, NOW, "crew-02", "w"), identity)

    assert len(store.query("crew-01")) == 2
    assert len(store.query("crew-01", key="heart-rate")) == 1
    assert len(store.query("crew-01", since=NOW + dt.timedelta(minutes=30))) == 1
    assert set(store.subjects()) == {"crew-01", "crew-02"}


def test_unknown_indicator_is_rejected(store: ObservationStore, identity: Identity) -> None:
    from app.ingest.codes import VitalCode
    from app.ingest.fhir import VitalObservation

    fake = VitalObservation(
        code=VitalCode(
            key="inventado", code="x", display="x", unit="x",
            system="http://loinc.org", domain="cardiovascular",  # type: ignore[arg-type]
        ),
        value=1.0, effective=NOW, subject="crew-01", source="w",
    )
    with pytest.raises(KeyError):
        store.record(fake, identity)


# --------------------------------------------------------------------------- #
# Integridad entre sesiones
# --------------------------------------------------------------------------- #


def test_chain_survives_reopening(tmp_path: Path, identity: Identity) -> None:
    db = tmp_path / "emma.db"
    first = ObservationStore.at(db)
    for index in range(4):
        first.record(observation("heart-rate", 60.0 + index, NOW, "crew-01", "w"), identity)
    root_before = first.merkle_root()

    reopened = ObservationStore.at(db)

    assert len(reopened.ledger) == 4
    assert reopened.verify_integrity()
    assert reopened.merkle_root() == root_before


def test_detects_tampering_done_outside_the_application(
    tmp_path: Path, identity: Identity
) -> None:
    """El caso que importa: alguien edita el SQLite por fuera entre sesiones."""
    db = tmp_path / "emma.db"
    store = ObservationStore.at(db)
    for index in range(4):
        store.record(observation("heart-rate", 60.0 + index, NOW, "crew-01", "w"), identity)

    # Manipulacion directa del fichero, sin pasar por la aplicacion.
    tampered = ObservationStore.at(db)
    with Session(tampered.engine) as session:
        row = session.scalars(select(LedgerRow).where(LedgerRow.index == 1)).one()
        payload = json.loads(row.payload or "{}")
        payload["value"] = 999.0
        row.payload = json.dumps(payload)
        session.commit()

    reopened = ObservationStore.at(db)
    result = reopened.verify_integrity()

    assert not result
    assert result.failed_index == 1


def test_redaction_preserves_the_chain(tmp_path: Path, identity: Identity) -> None:
    db = tmp_path / "emma.db"
    auditor = Identity.generate("emma-audit")
    authority = RedactionAuthority.of(auditor)
    store = ObservationStore.at(db, authority)
    for index in range(4):
        store.record(observation("heart-rate", 60.0 + index, NOW, "crew-01", "w"), identity)
    anchor = store.anchor()

    redaction = store.redact(1, auditor, "mal atribuida", "cirujano")

    assert store.verify_integrity(), "la cadena debe seguir verificando tras redactar"
    assert store.verify_integrity(anchor=anchor), "el ancla enviada a Tierra sigue válida"
    assert store.count() == 3, "el dato clínico desaparece"
    assert len(store.ledger) == 5, "y la lápida queda como asiento propio"
    # Y sobrevive a reabrir con la misma autoridad, que llega de fuera de la base.
    reopened = ObservationStore.at(db, authority)
    assert reopened.verify_integrity(anchor=anchor)
    assert reopened.ledger[redaction.tombstone.index].payload == redaction.tombstone.payload


def test_audit_trail_is_readable(store: ObservationStore, identity: Identity) -> None:
    store.record(observation("heart-rate", 62.0, NOW, "crew-01", "w"), identity)
    trail = store.audit_trail()

    assert len(trail) == 1
    assert trail[0]["entry_type"] == "vital-observation"
    assert trail[0]["signer"] == "wearable-01"
    # El rastro no expone el contenido clinico, solo su hash.
    assert "value" not in trail[0]


def test_simulator_data_has_no_privileges(store: ObservationStore) -> None:
    """Los datos simulados entran por la misma puerta y quedan firmados."""
    simulator = PhysiologicalSimulator(scenario=Scenario.NOMINAL)
    count = seed_from_simulator(
        store, simulator.generate(days=1, samples_per_day=2, keys=["heart-rate"])
    )

    assert count == 2
    assert len(store.ledger) == 2
    assert store.verify_integrity()
    assert all(entry.signer == "simulator" for entry in store.ledger.entries)


# --------------------------------------------------------------------------- #
# Contexto y confianza deben sobrevivir a la persistencia
# --------------------------------------------------------------------------- #


def test_context_and_confidence_survive_persistence(
    store: ObservationStore, identity: Identity
) -> None:
    """Se perdian al guardar, y con ellos los dos controles de falsa alarma.

    Toda lectura que pasaba por la base volvia como `unknown / 1.0`. Eso apagaba
    la estratificacion por contexto y el tope de severidad por baja confianza
    **solo por el camino real**: en las listas en memoria del simulador y del
    banco de validacion seguian funcionando. Las cifras publicadas se median
    sobre un motor que el sistema desplegado no ejecutaba.
    """
    casos = [
        (Context.SLEEP, 0.4),
        (Context.ACTIVE, 1.0),
        (Context.WORK, 0.55),
        (Context.UNKNOWN, 1.0),
        (Context.MEAL, 0.0),
    ]
    for minuto, (contexto, confianza) in enumerate(casos):
        store.record(
            observation(
                "heart-rate", 70.0 + minuto,
                dt.datetime(2026, 11, 14, 8, minuto, tzinfo=dt.UTC),
                "crew-01", "manual", contexto, confianza,
            ),
            identity,
        )

    recuperado = [(obs.context, obs.confidence) for obs in store.query("crew-01")]
    assert recuperado == casos


def test_audit_payload_records_confidence(
    store: ObservationStore, identity: Identity
) -> None:
    """La confianza cambia como se lee el dato, luego es registro clinico.

    Un asiento de auditoria que la omite no permite reproducir la decision que se
    tomo con esa lectura, que es justo lo que 21 CFR 11.10(e) pide poder hacer.
    """
    store.record(
        observation(
            "heart-rate", 70.0, dt.datetime(2026, 11, 14, 8, 0, tzinfo=dt.UTC),
            "crew-01", "manual", Context.SLEEP, 0.4,
        ),
        identity,
    )
    payload = store.ledger.entries[0].payload
    assert payload is not None
    assert payload["context"] == "sleep"
    assert payload["confidence"] == 0.4
