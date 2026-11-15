"""Enmienda anexada: la correccion que no borra (45 CFR 164.526).

La redaccion suprime, y por eso choca con 21 CFR 11.10(e) —"record changes shall not
obscure previously recorded information"—. La enmienda es la otra via: la version buena
se anexa y queda enlazada con la anterior, que sigue legible y firmada.

Estas pruebas ejecutan el ATAQUE, no la implementacion: lo que se comprueba de cada
salvaguarda es que la burla falla, no que el camino feliz pasa.
"""

import itertools
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.core.ledger import (
    AMENDMENT_ENTRY_TYPE,
    REDACTION_ENTRY_TYPE,
    HashChainLedger,
    Identity,
    LedgerEntry,
    RedactionAuthority,
    UntrustedSigner,
    canonical_bytes,
    sha256_hex,
)
from app.core.storage import AmendmentMismatch, ObservationStore
from app.environment.habitat import DEFAULT_MODULE, HabitatReading
from app.ingest.fhir import observation
from app.main import app

T0 = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)

GOOD = {"loinc": "8867-4", "value": 71, "unit": "/min", "subject": "crew-01"}


def _clock(start: datetime = T0, step: timedelta = timedelta(minutes=1)) -> Callable[[], datetime]:
    ticks = itertools.count()
    return lambda: start + step * next(ticks)


def _forge(entry: LedgerEntry, identity: Identity, **changes: Any) -> LedgerEntry:
    """Reescribe una entrada y la vuelve a firmar: el atacante tiene su propia clave."""
    forged = replace(entry, signature="", **changes)
    if "payload" in changes and changes["payload"] is not None:
        forged = replace(forged, content_hash=sha256_hex(canonical_bytes(changes["payload"])))
        forged = replace(forged, signature="")
    return replace(forged, signature=identity.sign(forged.signing_material()))


@pytest.fixture
def source() -> Identity:
    return Identity.generate("wearable-cmdr-01")


@pytest.fixture
def auditor() -> Identity:
    return Identity.generate("emma-audit")


@pytest.fixture
def ledger(source: Identity, auditor: Identity) -> HashChainLedger:
    """Tres lecturas; la primera, atribuida al tripulante equivocado."""
    chain = HashChainLedger(
        clock=_clock(), redaction_authority=RedactionAuthority.of(auditor)
    )
    chain.registry.register(source.identity_id, source.public_key_hex)
    for heart_rate, subject in ((62, "crew-02"), (68, "crew-01"), (71, "crew-01")):
        chain.append(
            "vital-signs",
            {"loinc": "8867-4", "value": heart_rate, "unit": "/min", "subject": subject},
            source,
        )
    return chain


# --------------------------------------------------------------------------- #
# Lo que la enmienda promete
# --------------------------------------------------------------------------- #


def test_the_amended_entry_stays_readable_and_signed(
    ledger: HashChainLedger, source: Identity
) -> None:
    """La diferencia con una redaccion: el dato anterior no desaparece."""
    before = ledger[0].payload

    amendment = ledger.amend(0, GOOD, source, "atribuida al tripulante equivocado")

    assert ledger[0].payload == before
    assert ledger[0].redacted is False
    assert ledger.verify()
    assert amendment.entry.entry_type == AMENDMENT_ENTRY_TYPE
    assert amendment.entry.payload is not None
    assert amendment.entry.payload["replacement"] == GOOD
    assert amendment.entry.payload["amended_by"] == source.identity_id


def test_the_amendment_says_which_version_is_current(
    ledger: HashChainLedger, source: Identity
) -> None:
    """Quien lea la cadena tiene que poder saber que version vale sin adivinarlo."""
    amendment = ledger.amend(0, GOOD, source, "mal atribuida")

    assert ledger.amendments() == {0: amendment.entry}


def test_an_amendment_can_be_amended(ledger: HashChainLedger, source: Identity) -> None:
    """Una correccion tambien puede estar mal. Cada eslabon queda atado al anterior."""
    first = ledger.amend(0, GOOD, source, "mal atribuida")
    second = ledger.amend(first.entry.index, {**GOOD, "value": 64}, source, "valor mal copiado")

    assert ledger.verify()
    assert ledger.amendments() == {0: first.entry, first.entry.index: second.entry}
    assert second.entry.payload is not None
    assert second.entry.payload["target_entry_hash"] == first.entry.entry_hash()


def test_the_returned_target_is_a_copy(ledger: HashChainLedger, source: Identity) -> None:
    """Mutar lo devuelto no puede cambiar lo registrado."""
    amendment = ledger.amend(0, GOOD, source, "mal atribuida")
    assert amendment.target.payload is not None
    amendment.target.payload["value"] = 999

    assert ledger[0].payload is not None
    assert ledger[0].payload["value"] == 62
    assert ledger.verify()


def test_the_replacement_is_copied_too(ledger: HashChainLedger, source: Identity) -> None:
    """El dict del llamante no puede seguir conectado al asiento firmado."""
    replacement = dict(GOOD)
    ledger.amend(0, replacement, source, "mal atribuida")
    replacement["value"] = 999

    assert ledger.verify()
    assert ledger[3].payload is not None
    assert ledger[3].payload["replacement"]["value"] == 71


# --------------------------------------------------------------------------- #
# Ataques: fabricar una enmienda
# --------------------------------------------------------------------------- #


def test_append_cannot_write_an_amendment(ledger: HashChainLedger, source: Identity) -> None:
    """Sin esto, una fuente de confianza declararia corregida —y fuera de las consultas—
    cualquier lectura ajena, con los campos que quisiera."""
    with pytest.raises(ValueError, match="amend"):
        ledger.append(AMENDMENT_ENTRY_TYPE, {"target_index": 0}, source)


def test_an_amendment_bound_to_another_entry_is_refused(
    ledger: HashChainLedger, source: Identity
) -> None:
    """La enmienda legitima de otro almacen, copiada aqui, no puede retirar una lectura."""
    ledger.amend(0, GOOD, source, "mal atribuida")
    amendment = ledger[3]
    assert amendment.payload is not None
    stolen = {**amendment.payload, "target_index": 1}

    ledger._entries[3] = _forge(amendment, source, payload=stolen)

    result = ledger.verify()
    assert not result.ok
    assert result.failed_index == 3
    assert result.reason == "la enmienda no corresponde a su entrada"
    assert ledger.amendments() == {}


def test_a_malformed_amendment_is_a_verification_failure_not_a_crash(
    ledger: HashChainLedger, source: Identity
) -> None:
    """Un payload basura en un asiento bien firmado no puede tumbar la verificacion."""
    ledger.amend(0, GOOD, source, "mal atribuida")
    ledger._entries[3] = _forge(ledger[3], source, payload={"target_index": "cero"})

    result = ledger.verify()
    assert not result.ok
    assert result.failed_index == 3
    assert result.reason == "enmienda mal formada"
    assert ledger.amendments() == {}


def test_an_amendment_cannot_point_forward(ledger: HashChainLedger, source: Identity) -> None:
    """Apuntar a una entrada posterior dejaria la vigencia dependiendo del orden de lectura."""
    ledger.amend(0, GOOD, source, "mal atribuida")
    amendment = ledger[3]
    assert amendment.payload is not None

    ledger._entries[3] = _forge(
        amendment, source, payload={**amendment.payload, "target_index": 3}
    )

    result = ledger.verify()
    assert not result.ok
    assert result.reason == "la enmienda apunta a una entrada inexistente o posterior"


def test_two_amendments_of_the_same_entry_are_refused(
    ledger: HashChainLedger, source: Identity
) -> None:
    """Dos correcciones vigentes del mismo dato: no habria forma de decidir cual vale."""
    ledger.amend(0, GOOD, source, "mal atribuida")

    with pytest.raises(ValueError, match="ya está enmendada"):
        ledger.amend(0, {**GOOD, "value": 99}, source, "otra versión")


def test_a_second_amendment_smuggled_into_the_chain_fails_verification(
    ledger: HashChainLedger, source: Identity
) -> None:
    """Y si se inserta a mano saltandose `amend()`, la verificacion lo rechaza."""
    first = ledger.amend(0, GOOD, source, "mal atribuida").entry
    assert first.payload is not None
    ledger.amend(1, {**GOOD, "value": 68}, source, "otra lectura")

    duplicate = {**first.payload, "replacement": {**GOOD, "value": 99}}
    ledger._entries[4] = _forge(ledger[4], source, payload=duplicate)

    result = ledger.verify()
    assert not result.ok
    assert result.failed_index == 4
    assert result.reason == "enmienda duplicada de la misma entrada"


def test_a_tampered_replacement_breaks_the_chain(
    ledger: HashChainLedger, source: Identity
) -> None:
    """Editar la correccion sin rehacer el hash: el ataque clasico sobre el contenido."""
    ledger.amend(0, GOOD, source, "mal atribuida")
    stored = ledger._entries[3].payload  # `ledger[3]` da una copia: mutarla no ataca nada
    assert stored is not None
    stored["replacement"]["value"] = 180

    result = ledger.verify()
    assert not result.ok
    assert result.failed_index == 3
    assert result.reason == "el contenido no coincide con content_hash"


def test_an_amendment_with_a_broken_signature_supersedes_nothing(
    ledger: HashChainLedger, source: Identity
) -> None:
    """`amendments()` responde sin verificar la cadena entera: comprueba la firma."""
    ledger.amend(0, GOOD, source, "mal atribuida")
    ledger._entries[3] = replace(ledger[3], signature="00" * 64)

    assert ledger.amendments() == {}


def test_the_redaction_authority_cannot_amend(
    ledger: HashChainLedger, auditor: Identity
) -> None:
    """Una clave pensada para rectificar no puede fabricar datos clinicos."""
    with pytest.raises(UntrustedSigner):
        ledger.amend(0, GOOD, auditor, "mal atribuida")


def test_an_unregistered_identity_cannot_amend(ledger: HashChainLedger) -> None:
    intruder = Identity.generate("mantenimiento")

    with pytest.raises(UntrustedSigner):
        ledger.amend(0, GOOD, intruder, "mal atribuida")


def test_an_amendment_needs_a_reason(ledger: HashChainLedger, source: Identity) -> None:
    """U+200B pasaba `strip()`: el motivo tiene que tener algo legible."""
    with pytest.raises(ValueError, match="motivo"):
        ledger.amend(0, GOOD, source, "​  ")


def test_an_empty_correction_is_refused(ledger: HashChainLedger, source: Identity) -> None:
    """Escribirla dejaria la cadena en rojo: `_amendment_problem` la da por invalida."""
    with pytest.raises(ValueError, match="versión corregida"):
        ledger.amend(0, {}, source, "sin contenido")


def test_the_caller_cannot_fix_the_salt(ledger: HashChainLedger, source: Identity) -> None:
    """Fijar la sal permitiria reproducir el hash de un contenido conocido."""
    with pytest.raises(ValueError, match="reservado"):
        ledger.amend(0, {**GOOD, "_salt": "00" * 16}, source, "mal atribuida")


def test_amend_out_of_range_is_refused(ledger: HashChainLedger, source: Identity) -> None:
    """`-1` no es 'la ultima': es un indice fuera de la cadena."""
    for index in (-1, 3, 99):
        with pytest.raises(IndexError):
            ledger.amend(index, GOOD, source, "mal atribuida")


def test_a_damaged_entry_is_not_amended(ledger: HashChainLedger, source: Identity) -> None:
    """Enmendar sobre una entrada manipulada le daria apariencia de dato corregido."""
    stored = ledger._entries[0].payload
    assert stored is not None
    stored["value"] = 180

    with pytest.raises(ValueError, match="no verifica"):
        ledger.amend(0, GOOD, source, "mal atribuida")


# --------------------------------------------------------------------------- #
# Enmienda y redaccion, juntas
# --------------------------------------------------------------------------- #


def test_a_redacted_entry_cannot_be_amended(
    ledger: HashChainLedger, source: Identity, auditor: Identity
) -> None:
    ledger.redact(0, auditor, "dato de otro tripulante", "cirujano de vuelo")

    with pytest.raises(ValueError, match="redactada"):
        ledger.amend(0, GOOD, source, "mal atribuida")


def test_a_tombstone_cannot_be_amended(
    ledger: HashChainLedger, source: Identity, auditor: Identity
) -> None:
    tombstone = ledger.redact(0, auditor, "dato de otro tripulante", "cirujano").tombstone

    with pytest.raises(ValueError, match="lápida"):
        ledger.amend(tombstone.index, GOOD, source, "mal atribuida")


def test_an_amendment_survives_the_redaction_of_what_it_corrected(
    ledger: HashChainLedger, source: Identity, auditor: Identity
) -> None:
    """Redactar el original no deshace la correccion: el hash y el entry_hash no cambian."""
    amendment = ledger.amend(0, GOOD, source, "mal atribuida")

    ledger.redact(0, auditor, "dato de otro tripulante", "cirujano de vuelo")

    assert ledger.verify()
    assert ledger[0].payload is None
    assert ledger.amendments() == {0: amendment.entry}


def test_redacting_a_correction_before_its_original_is_refused(
    ledger: HashChainLedger, source: Identity, auditor: Identity
) -> None:
    """Si no, el valor equivocado que la enmienda corrigio volveria a estar vigente."""
    amendment = ledger.amend(0, GOOD, source, "mal atribuida")

    with pytest.raises(ValueError, match="resucitar"):
        ledger.redact(amendment.entry.index, auditor, "borrar la corrección", "cirujano")


def test_both_versions_can_be_erased_in_the_right_order(
    ledger: HashChainLedger, source: Identity, auditor: Identity
) -> None:
    """Primero el original, despues su correccion: no resucita ninguna version."""
    amendment = ledger.amend(0, GOOD, source, "mal atribuida")

    ledger.redact(0, auditor, "dato de otro tripulante", "cirujano de vuelo")
    ledger.redact(amendment.entry.index, auditor, "y su corrección", "cirujano de vuelo")

    assert ledger.verify()
    assert ledger.amendments() == {}
    assert ledger[0].payload is None
    assert ledger[amendment.entry.index].payload is None
    assert ledger.redacted_indices() == frozenset({0, amendment.entry.index})


def test_a_tombstone_over_a_chain_of_corrections_keeps_verifying(
    ledger: HashChainLedger, source: Identity, auditor: Identity
) -> None:
    """Cadena de dos correcciones, borradas de abajo arriba."""
    first = ledger.amend(0, GOOD, source, "mal atribuida").entry
    second = ledger.amend(first.index, {**GOOD, "value": 64}, source, "valor mal copiado").entry

    ledger.redact(0, auditor, "dato de otro tripulante", "cirujano")
    ledger.redact(first.index, auditor, "y su corrección", "cirujano")
    ledger.redact(second.index, auditor, "y la corrección de la corrección", "cirujano")

    assert ledger.verify()
    assert ledger.amendments() == {}
    assert all(
        entry.entry_type == REDACTION_ENTRY_TYPE or entry.payload is None
        for entry in ledger.entries[:1] + ledger.entries[3:]
    )


# --------------------------------------------------------------------------- #
# En el almacen: lo que el motor acaba analizando
# --------------------------------------------------------------------------- #

NOW = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)


@pytest.fixture
def store(source: Identity, auditor: Identity) -> ObservationStore:
    """Una lectura de 180 lpm atribuida a crew-01: el valor esta mal y el tripulante tambien."""
    store = ObservationStore.in_memory(RedactionAuthority.of(auditor))
    store.record(observation("heart-rate", 180.0, NOW, "crew-01", "wearable-01"), source)
    return store


def test_the_engine_analyses_the_corrected_value(
    store: ObservationStore, source: Identity
) -> None:
    """Lo que importa de toda esta maquinaria: el motor no puede seguir viendo los 180."""
    store.amend(0, observation("heart-rate", 72.0, NOW, "crew-01", "wearable-01"), source, "mal")

    readings = store.query("crew-01")

    assert [reading.value for reading in readings] == [72.0]


def test_a_misattributed_reading_moves_to_the_right_crew_member(
    store: ObservationStore, source: Identity
) -> None:
    """El peligro H3 del archivo de riesgos: una lectura bajo el tripulante equivocado."""
    store.amend(
        0,
        observation("heart-rate", 72.0, NOW, "crew-02", "wearable-01"),
        source,
        "era de crew-02",
    )

    assert store.query("crew-01") == []
    assert [reading.value for reading in store.query("crew-02")] == [72.0]
    assert store.subjects() == ["crew-02"]


def test_the_corrected_reading_is_not_counted_twice(
    store: ObservationStore, source: Identity
) -> None:
    """Entregar las dos versiones contaria dos veces el mismo dato en la linea base."""
    store.amend(0, observation("heart-rate", 72.0, NOW, "crew-01", "wearable-01"), source, "mal")

    assert len(store.query("crew-01")) == 1
    assert store.count() == 1, "y la tabla espejo tampoco guarda las dos"


def test_the_previous_version_stays_registered_and_auditable(
    store: ObservationStore, source: Identity
) -> None:
    """La diferencia con redactar: 21 CFR 11.10(e) exige que el cambio no oculte lo anterior."""
    before = store.ledger[0].payload

    store.amend(0, observation("heart-rate", 72.0, NOW, "crew-01", "wearable-01"), source, "mal")

    assert store.ledger[0].payload == before, "la lectura anterior sigue entera"
    assert store.ledger[0].redacted is False
    trail = store.audit_trail()
    assert trail[1]["amendment"]["target_index"] == 0
    assert trail[1]["amendment"]["reason"] == "mal"
    assert trail[1]["amendment"]["amended_by"] == source.identity_id


def test_the_amendment_survives_reopening_the_store(
    tmp_path: Path, source: Identity, auditor: Identity
) -> None:
    """Y el cotejo con el disco tiene que aceptar la tabla espejo que deja la correccion."""
    db = tmp_path / "emma.db"
    authority = RedactionAuthority.of(auditor)
    store = ObservationStore.at(db, authority)
    store.record(observation("heart-rate", 180.0, NOW, "crew-01", "wearable-01"), source)
    store.amend(0, observation("heart-rate", 72.0, NOW, "crew-01", "wearable-01"), source, "mal")
    anchor = store.anchor()

    reopened = ObservationStore.at(db, authority)

    assert reopened.verify_integrity()
    assert reopened.verify_integrity(anchor=anchor)
    assert [reading.value for reading in reopened.query("crew-01")] == [72.0]


def test_the_mirror_table_follows_the_current_version(
    store: ObservationStore, source: Identity
) -> None:
    """Una fila por lectura vigente: ni la corregida de mas, ni la correccion de menos."""
    store.amend(0, observation("heart-rate", 72.0, NOW, "crew-01", "wearable-01"), source, "mal")

    assert store.verify_integrity(), "el cotejo con el disco acepta la fila de la enmienda"
    assert store.count() == 1


def test_no_amendment_over_a_chain_that_does_not_verify(
    store: ObservationStore, source: Identity
) -> None:
    """Igual que la redaccion: daria apariencia de dato revisado a un registro manipulado."""
    stored = store.ledger._entries[0].payload
    assert stored is not None
    stored["value"] = 42.0

    with pytest.raises(ValueError, match="no verifica"):
        store.amend(
            0, observation("heart-rate", 72.0, NOW, "crew-01", "wearable-01"), source, "mal"
        )


def test_erasing_the_original_keeps_the_correction_alive(
    store: ObservationStore, source: Identity, auditor: Identity
) -> None:
    """Redactar el dato mal atribuido no puede llevarse por delante la version buena."""
    store.amend(
        0, observation("heart-rate", 72.0, NOW, "crew-02", "wearable-01"), source, "era de crew-02"
    )

    store.redact(0, auditor, "dato de otro tripulante", "cirujano de vuelo")

    assert store.verify_integrity()
    assert [reading.value for reading in store.query("crew-02")] == [72.0]
    assert store.count() == 1


def test_an_unknown_indicator_is_refused_before_writing(
    store: ObservationStore, source: Identity
) -> None:
    """El catalogo se comprueba antes de tocar la cadena, como en `record_many`."""
    good = observation("heart-rate", 72.0, NOW, "crew-01", "wearable-01")
    unknown = replace(good, code=replace(good.code, key="frecuencia-cardiaca"))

    with pytest.raises(KeyError):
        store.amend(0, unknown, source, "mal")

    assert len(store.ledger) == 1, "no se escribio nada"


# --------------------------------------------------------------------------- #
# Por la API
# --------------------------------------------------------------------------- #


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """Almacen limpio con una lectura de 180 lpm en el asiento 0."""
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    client = TestClient(app)
    client.post(
        "/api/observations",
        json={"key": "heart-rate", "value": 180.0, "subject": "crew-01", "source": "wearable-01"},
    )
    yield client
    app.dependency_overrides.clear()
    reset_store(None)


def _correction(**changes: Any) -> dict[str, Any]:
    reading = {
        "key": "heart-rate",
        "value": 72.0,
        "subject": "crew-01",
        "source": "wearable-01",
        **changes,
    }
    return {"reason": "valor mal copiado", "correction": reading}


def test_the_api_corrects_without_erasing(client: TestClient) -> None:
    response = client.post("/api/audit/amend/0", json=_correction())

    assert response.status_code == 200
    body = response.json()
    assert body["amended_index"] == 0
    assert body["amendment_entry_index"] == 1
    assert body["chain_still_valid"] is True

    observations = client.get("/api/observations").json()["observations"]
    assert [item["valueQuantity"]["value"] for item in observations] == [72.0]
    audit = client.get("/api/audit").json()
    assert audit["total_entries"] == 2, "la lectura anterior sigue registrada"
    assert audit["integrity_ok"] is True
    assert audit["entries"][1]["amendment"]["target_index"] == 0


def test_amending_the_same_entry_twice_is_a_conflict(client: TestClient) -> None:
    assert client.post("/api/audit/amend/0", json=_correction()).status_code == 200

    response = client.post("/api/audit/amend/0", json=_correction(value=64.0))

    assert response.status_code == 409
    assert "enmendada" in response.json()["detail"]


def test_amending_an_index_that_does_not_exist_is_a_404(client: TestClient) -> None:
    for index in (-1, 7):
        assert client.post(f"/api/audit/amend/{index}", json=_correction()).status_code == 404


def test_a_correction_with_an_impossible_value_is_a_422(client: TestClient) -> None:
    """La frontera rechaza lo que no es una medida, igual que en el alta normal."""
    response = client.post("/api/audit/amend/0", json=_correction(value=5000.0))

    assert response.status_code == 422
    assert client.get("/api/audit").json()["total_entries"] == 1, "no se escribio nada"


def test_a_correction_without_a_reason_is_a_422(client: TestClient) -> None:
    body = _correction()
    body["reason"] = "\u200b  "

    assert client.post("/api/audit/amend/0", json=body).status_code == 422


def test_an_unencodable_subject_is_a_422_not_a_conflict(client: TestClient) -> None:
    """Un sustituto UTF-16 suelto es un dato malo de quien llama (422), no un conflicto
    de estado (409): el ledger no puede registrarlo tal cual."""
    raw = rb'{"reason": "mal atribuida", "correction": {"key": "heart-rate", "value": 72.0,'
    raw += rb' "subject": "crew-\ud800", "source": "wearable-01"}}'

    response = client.post(
        "/api/audit/amend/0", content=raw, headers={"content-type": "application/json"}
    )

    assert response.status_code == 422
    assert client.get("/api/audit").json()["total_entries"] == 1


def test_a_redacted_reading_cannot_be_amended_through_the_api(client: TestClient) -> None:
    redaction = client.post(
        "/api/audit/redact/0",
        json={"reason": "dato de otro tripulante", "requested_by": "cirujano"},
    )
    assert redaction.status_code == 200

    response = client.post("/api/audit/amend/0", json=_correction())

    assert response.status_code == 409
    assert "redactada" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# El mismo indicador, y el tripulante que se puede reasignar (decimoseptima ronda)
# --------------------------------------------------------------------------- #


def test_a_correction_of_another_indicator_is_refused_without_writing(
    store: ObservationStore, source: Identity
) -> None:
    """Cambiar el indicador retiraria la lectura de una serie y la pondria en otra."""
    with pytest.raises(AmendmentMismatch, match="'heart-rate'.*'respiratory-rate'"):
        store.amend(
            0, observation("respiratory-rate", 16.0, NOW, "crew-01", "wearable-01"), source, "mal"
        )

    assert len(store.ledger) == 1, "no se escribio nada"
    assert [reading.value for reading in store.query("crew-01")] == [180.0]


def test_an_amendment_is_compared_with_the_reading_it_puts_in_force(
    store: ObservationStore, source: Identity
) -> None:
    """Enmendar una enmienda se compara con su correccion, no con el asiento de la enmienda."""
    first = store.amend(
        0, observation("heart-rate", 72.0, NOW, "crew-01", "wearable-01"), source, "mal"
    )
    with pytest.raises(AmendmentMismatch):
        store.amend(
            first.entry.index,
            observation("respiratory-rate", 16.0, NOW, "crew-01", "wearable-01"),
            source,
            "otra vez",
        )
    store.amend(
        first.entry.index,
        observation("heart-rate", 70.0, NOW, "crew-01", "wearable-01"),
        source,
        "otra vez",
    )

    assert [reading.value for reading in store.query("crew-01")] == [70.0]


def test_an_entry_that_is_not_a_reading_is_not_amended_with_one(
    store: ObservationStore, source: Identity
) -> None:
    """Una lectura de cabina no tiene indicador del catalogo que corregir."""
    cabin = HabitatReading(
        module=DEFAULT_MODULE, parameter="cabin-ppco2", value=2.0, effective=NOW,
        source="habitat-telemetry",
    )
    index = store.record_habitat([cabin], source)[0].index

    with pytest.raises(AmendmentMismatch, match="no es la lectura de un indicador"):
        store.amend(
            index, observation("heart-rate", 72.0, NOW, "crew-01", "wearable-01"), source, "mal"
        )
    assert len(store.ledger) == 2


def test_the_indicator_rule_is_of_the_write_not_of_verification(
    ledger: HashChainLedger, source: Identity
) -> None:
    """Un ledger ya escrito con una enmienda de otro indicador sigue verificando."""
    ledger.amend(0, {**GOOD, "loinc": "9279-1"}, source, "escrita antes de la regla")

    assert ledger.verify()


def test_the_api_refuses_another_indicator_with_a_reason_in_spanish(client: TestClient) -> None:
    response = client.post(
        "/api/audit/amend/0", json=_correction(key="respiratory-rate", value=16.0)
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, str)
    assert "no el indicador" in detail and "'heart-rate'" in detail
    assert client.get("/api/audit").json()["total_entries"] == 1


def test_an_entry_already_amended_is_a_conflict_whatever_the_indicator(
    client: TestClient,
) -> None:
    """El conflicto de estado (409) no se disfraza de dato malo (422) por el orden de las reglas."""
    assert client.post("/api/audit/amend/0", json=_correction()).status_code == 200

    response = client.post(
        "/api/audit/amend/0", json=_correction(key="respiratory-rate", value=16.0)
    )

    assert response.status_code == 409
    assert "ya está enmendada" in response.json()["detail"]


def test_the_api_still_moves_a_reading_to_the_right_crew_member(client: TestClient) -> None:
    """El control del peligro H3 se conserva: el tripulante si se puede corregir."""
    response = client.post("/api/audit/amend/0", json=_correction(subject="crew-02"))

    assert response.status_code == 200, response.text
    assert client.get("/api/audit").json()["integrity_ok"] is True
