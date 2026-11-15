"""Lo firmado cuando el proyecto se llamaba HALO se sigue leyendo y verificando (2026-11-02).

El 2026-11-02 HALO pasó a llamarse EMMA, también en los identificadores que viajan dentro de lo
firmado: la autoridad de redacción (`halo-audit` → `emma-audit`), el firmante de las predicciones
(`halo-forecast` → `emma-forecast`) y los URI propios (`https://halo.mission/` →
`https://emma.mission/`). Lo escrito antes no se puede reescribir sin romper la cadena, así que
se lee con el nombre de hoy. Estas pruebas fijan las dos mitades: lo de antes vale, y el nombre
viejo no da para escribir nada nuevo ni para colarse como el sistema. Los ledgers grabados de
`test_contrast_phase.py` y `test_volume_redaction.py` lo comprueban con lápidas reales.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.ledger import FORMER_AUTHORITY_IDS, Identity, RedactionAuthority, UntrustedSigner
from app.core.storage import ObservationStore
from app.ingest.codes import FORMER_CODE_SYSTEMS, CodeSystem, current_system
from app.ingest.fhir import VitalObservation, observation

T = dt.datetime(2026, 11, 2, 12, 0, tzinfo=dt.UTC)
KEY = Ed25519PrivateKey.from_private_bytes(bytes([7]) * 32)


def _with_former_uris(resource: dict[str, object]) -> dict[str, object]:
    """El recurso como lo escribía HALO: los mismos datos con los URI de antes."""
    text = json.dumps(resource).replace("https://emma.mission/", "https://halo.mission/")
    loaded: dict[str, object] = json.loads(text)
    return loaded


def test_a_resource_written_with_the_former_uris_reads_as_today() -> None:
    today = observation("mood-valence", 6.0, T, "crew-01", "crew-diary")
    resource = today.to_fhir()
    assert "https://emma.mission/" in json.dumps(resource)
    assert "halo.mission" not in json.dumps(resource)

    former = _with_former_uris(resource)
    assert "https://halo.mission/codes" in json.dumps(former)
    read = VitalObservation.from_fhir(former)
    assert read == VitalObservation.from_fhir(resource)
    # Y al volver a escribirlo, sale con los de hoy.
    assert read.to_fhir() == resource


def test_only_the_former_own_system_is_translated() -> None:
    assert FORMER_CODE_SYSTEMS == {"https://halo.mission/codes": CodeSystem.EMMA}
    assert current_system("https://halo.mission/codes") == "https://emma.mission/codes"
    assert current_system(str(CodeSystem.LOINC)) == str(CodeSystem.LOINC)
    assert current_system("https://otro.example/codes") == "https://otro.example/codes"


def test_the_authority_recognises_its_former_name_only_with_its_own_key() -> None:
    assert FORMER_AUTHORITY_IDS == {"emma-audit": ("halo-audit",)}
    authority = RedactionAuthority.of(Identity("emma-audit", KEY))
    assert authority.former_ids == ("halo-audit",)
    assert authority.matches("halo-audit", authority.public_key_hex)
    assert authority.matches("emma-audit", authority.public_key_hex)
    other = Identity.generate("halo-audit")
    assert not authority.matches("halo-audit", other.public_key_hex)
    assert not authority.matches("otro", authority.public_key_hex)


def test_nothing_new_is_signed_with_the_former_name() -> None:
    authority = Identity("emma-audit", KEY)
    store = ObservationStore.in_memory(RedactionAuthority.of(authority))
    try:
        store.record(observation("heart-rate", 61.0, T, "crew-01", "wearable"),
                     Identity.generate("wearable"))
        # La misma clave con el nombre de antes no redacta: lo nuevo lleva el nombre de hoy.
        with pytest.raises(UntrustedSigner):
            store.redact(0, Identity("halo-audit", KEY), "prueba", "CMO")
        tombstone = store.redact(0, authority, "prueba", "CMO").tombstone
        assert tombstone.signer == "emma-audit"
        assert store.verify_integrity().ok
    finally:
        store.engine.dispose()


def test_the_former_authority_name_cannot_sign_clinical_data() -> None:
    authority = Identity("emma-audit", KEY)
    store = ObservationStore.in_memory(RedactionAuthority.of(authority))
    try:
        with pytest.raises(UntrustedSigner):
            store.record(observation("heart-rate", 61.0, T, "crew-01", "halo-audit"),
                         Identity("halo-audit", KEY))
    finally:
        store.engine.dispose()
