"""El almacen bajo escritura concurrente y ante un fallo de la base.

FastAPI atiende los endpoints sincronos en un pool de hilos, y el almacen no
tenia ningun cerrojo. Reproducido con 4 hilos y 800 escrituras: 163 asientos con
indice duplicado —una cadena rota por pura concurrencia, que `verify_integrity()`
denunciaria como manipulacion— y, con la base en memoria que usa la aplicacion,
un almacen que acabo perdiendo sus tablas.
"""

import datetime as dt
import sys
import threading
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

import app.core.storage as storage
from app.core.ledger import Identity, RedactionAuthority
from app.core.storage import ObservationStore
from app.ingest.fhir import VitalObservation, observation

NOW = dt.datetime(2026, 11, 14, 8, 0, tzinfo=dt.UTC)


def _reading(i: int, subject: str = "crew-01") -> VitalObservation:
    return observation(
        "heart-rate", 60.0 + i % 5, NOW + dt.timedelta(seconds=i), subject, "t"
    )


@pytest.fixture
def frequent_thread_switches() -> Iterator[None]:
    """Cambios de hilo muy frecuentes: hace visible una carrera que ya existe."""
    previous = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    yield
    sys.setswitchinterval(previous)


def test_concurrent_writers_keep_the_chain_intact(frequent_thread_switches: None) -> None:
    store = ObservationStore.in_memory()
    errors: list[BaseException] = []

    def writer(worker: int) -> None:
        identity = Identity.generate(f"wearable-{worker}")
        for i in range(200):
            try:
                store.record(_reading(worker * 1000 + i, f"crew-0{worker}"), identity)
                if i % 25 == 0:
                    store.query(f"crew-0{worker}")
                    store.verify_integrity()
            except BaseException as exc:  # noqa: BLE001 - se reporta abajo
                errors.append(exc)

    threads = [threading.Thread(target=writer, args=(w,)) for w in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    indices = [entry.index for entry in store.ledger.entries]
    assert not errors, errors[:3]
    assert len(indices) == len(set(indices)) == 800, "indices duplicados en la cadena"
    assert store.count() == 800
    assert store.verify_integrity().ok


class _FailingSession(Session):
    """Una sesion cuyo commit falla, como una base llena o un disco que se va."""

    def commit(self) -> None:
        raise RuntimeError("fallo simulado de la base")


def test_failed_batch_leaves_nothing_behind(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un lote se escribe entero o no se escribe, y la memoria no se adelanta.

    Los asientos se anaden en memoria antes del commit. Si el commit falla y no
    se retiran, la cadena en memoria afirma registros que la base no tiene.
    """
    store = ObservationStore.in_memory()
    identity = Identity.generate("wearable-01")
    store.record(_reading(0), identity)

    monkeypatch.setattr(storage, "Session", _FailingSession)
    with pytest.raises(RuntimeError, match="fallo simulado"):
        store.record_many([_reading(i) for i in range(1, 6)], identity)
    monkeypatch.undo()

    assert len(store.ledger) == 1
    assert store.count() == 1
    assert store.verify_integrity().ok

    # Y se puede seguir escribiendo detras sin romper la cadena.
    store.record(_reading(6), identity)
    assert len(store.ledger) == 2
    assert store.verify_integrity().ok


def test_failed_redaction_is_not_half_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si la base no llega a redactar, la cadena en memoria tampoco."""
    auditor = Identity.generate("emma-audit")
    store = ObservationStore.in_memory(RedactionAuthority.of(auditor))
    store.record(_reading(0), Identity.generate("wearable-01"))

    monkeypatch.setattr(storage, "Session", _FailingSession)
    with pytest.raises(RuntimeError, match="fallo simulado"):
        store.redact(0, auditor, "motivo", "cirujano")
    monkeypatch.undo()

    assert not store.ledger[0].redacted
    assert store.ledger[0].payload is not None
    assert store.count() == 1
    # La lapida tampoco se queda en memoria.
    assert len(store.ledger) == 1
    assert store.verify_integrity().ok


def test_a_batch_is_one_transaction() -> None:
    """El contrapeso: el camino normal escribe el lote entero y verificable."""
    store = ObservationStore.in_memory()
    entries = store.record_many(
        [_reading(i) for i in range(50)], Identity.generate("simulator")
    )

    assert [entry.index for entry in entries] == list(range(50))
    assert store.count() == 50
    assert store.verify_integrity().ok
