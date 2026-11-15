"""Verificacion del ledger de integridad.

Cada prueba corresponde a una fila de la matriz de `compliance/record-integrity.md`.
Ninguna necesita red: la propiedad de autonomia se verifica por construccion.

REGLA DE ESTA SUITE: una prueba de seguridad ejecuta el ATAQUE, no la implementacion.
La version anterior tenia `test_signature_rejects_wrong_key`, que cambiaba la firma
pero conservaba la clave publica original: probaba el unico camino que el codigo ya
detectaba, mientras el ataque real —cambiar tambien la clave— pasaba en verde. Las
pruebas marcadas B1..M6 reproducen cada ataque de la revision adversaria del
2026-09-21 tal y como se ejecuto contra la version vulnerable.
"""

import hashlib
import itertools
import sys
import threading
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.core.ledger import (
    GENESIS_PREV_HASH,
    MERKLE_ALGORITHM,
    REDACTION_ENTRY_TYPE,
    Anchor,
    HashChainLedger,
    Identity,
    KeyConflict,
    LedgerEntry,
    RedactionAuthority,
    UntrustedSigner,
    canonical_bytes,
    leaf_hash,
    merkle_proof_of,
    merkle_root_of,
    sha256_hex,
    verify_merkle_proof,
)

T0 = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)


def _clock(start: datetime = T0, step: timedelta = timedelta(minutes=1)) -> Callable[[], datetime]:
    """Reloj determinista: cada lectura avanza `step`."""
    ticks = itertools.count()
    return lambda: start + step * next(ticks)


def _ledger_for(
    *identities: Identity,
    clock: Callable[[], datetime] | None = None,
    authority: Identity | None = None,
) -> HashChainLedger:
    chain = HashChainLedger(
        clock=clock or _clock(),
        redaction_authority=RedactionAuthority.of(authority) if authority else None,
    )
    for identity in identities:
        chain.registry.register(identity.identity_id, identity.public_key_hex)
    return chain


def _unsalted(payload: dict[str, Any] | None) -> dict[str, Any]:
    """El payload sin la sal aleatoria que el ledger anade a cada contenido."""
    assert payload is not None
    return {key: value for key, value in payload.items() if key != "_salt"}


def _forge(entry: LedgerEntry, identity: Identity, **changes: Any) -> LedgerEntry:
    """Reescribe una entrada y la vuelve a firmar con `identity`."""
    forged = replace(entry, signature="", **changes)
    return replace(forged, signature=identity.sign(forged.signing_material()))


@pytest.fixture
def identity() -> Identity:
    return Identity.generate("wearable-cmdr-01")


@pytest.fixture
def auditor() -> Identity:
    return Identity.generate("emma-audit")


@pytest.fixture
def ledger(identity: Identity, auditor: Identity) -> HashChainLedger:
    """Cadena con tres observaciones de signos vitales."""
    chain = _ledger_for(identity, authority=auditor)
    for heart_rate in (62, 68, 71):
        chain.append(
            "vital-signs", {"loinc": "8867-4", "value": heart_rate, "unit": "/min"}, identity
        )
    return chain


# --------------------------------------------------------------------------- #
# Encadenamiento y contenido
# --------------------------------------------------------------------------- #


def test_chain_verifies_when_intact(ledger: HashChainLedger) -> None:
    assert ledger.verify()
    assert len(ledger) == 3
    assert ledger[0].prev_hash == GENESIS_PREV_HASH
    assert ledger[1].prev_hash == ledger[0].entry_hash()
    assert ledger[2].prev_hash == ledger[1].entry_hash()


def test_ledger_detects_tampering(ledger: HashChainLedger) -> None:
    """21 CFR 11.10(a): discernir registros alterados."""
    tampered = replace(ledger[1], payload={"loinc": "8867-4", "value": 999, "unit": "/min"})
    ledger._entries[1] = tampered

    result = ledger.verify()

    assert not result
    assert result.failed_index == 1
    assert "content_hash" in (result.reason or "")


def test_tampering_with_content_hash_breaks_the_chain(ledger: HashChainLedger) -> None:
    """Recalcular el content_hash para encubrir la edicion tampoco cuela."""
    forged_payload = {"loinc": "8867-4", "value": 999, "unit": "/min"}
    ledger._entries[1] = replace(
        ledger[1],
        payload=forged_payload,
        content_hash=sha256_hex(canonical_bytes(forged_payload)),
    )

    result = ledger.verify()

    # La firma ya no cubre el nuevo content_hash: se detecta en la propia entrada 1.
    assert not result
    assert result.failed_index == 1
    assert result.reason == "firma inválida"


# --------------------------------------------------------------------------- #
# B1 — procedencia: la confianza no puede venir de la propia entrada
# --------------------------------------------------------------------------- #


def test_signature_that_does_not_match_the_declared_key_fails(ledger: HashChainLedger) -> None:
    """Una firma que no corresponde a la clave declarada en la entrada.

    Es el caso facil, y NO demuestra que suplantar falle: aqui la clave declarada
    sigue siendo la legitima. El ataque real es el de la prueba siguiente.
    """
    impostor = Identity.generate("wearable-cmdr-01")
    entry = ledger[2]
    ledger._entries[2] = replace(entry, signature=impostor.sign(entry.signing_material()))

    result = ledger.verify()

    assert not result
    assert result.failed_index == 2
    assert result.reason == "firma inválida"


def test_impersonation_by_rewriting_the_whole_chain_fails(ledger: HashChainLedger) -> None:
    """B1 — 45 CFR 164.312(c)(1): suplantar la identidad de origen falla.

    El ataque que pasaba: generar una clave con el mismo `identity_id`, reescribir
    las tres entradas con la clave propia (payload alterado, hashes y enlaces
    recalculados) y firmarlas todas. La entrada se certificaba a si misma.
    """
    impostor = Identity.generate("wearable-cmdr-01")
    prev_hash = GENESIS_PREV_HASH
    for index in range(3):
        entry = ledger._entries[index]
        payload = {"seq": 999} if index == 1 else entry.payload
        forged = _forge(
            entry,
            impostor,
            payload=payload,
            content_hash=sha256_hex(canonical_bytes(payload)),
            prev_hash=prev_hash,
            signer_public_key=impostor.public_key_hex,
        )
        ledger._entries[index] = forged
        prev_hash = forged.entry_hash()

    result = ledger.verify()

    assert not result
    assert result.failed_index == 0
    assert result.reason == "firmante no autorizado"


def test_an_identity_cannot_be_repinned_to_another_key(ledger: HashChainLedger) -> None:
    impostor = Identity.generate("wearable-cmdr-01")
    with pytest.raises(KeyConflict):
        ledger.registry.register(impostor.identity_id, impostor.public_key_hex)
    with pytest.raises(UntrustedSigner):
        ledger.append("vital-signs", {"value": 1}, impostor)


def test_unregistered_signer_cannot_append() -> None:
    with pytest.raises(UntrustedSigner):
        HashChainLedger().append("vital-signs", {"value": 1}, Identity.generate("nadie"))


# --------------------------------------------------------------------------- #
# B2 — redaccion: el contenido se va, la constancia se queda
# --------------------------------------------------------------------------- #


def test_redaction_leaves_a_signed_tombstone(
    ledger: HashChainLedger, identity: Identity, auditor: Identity
) -> None:
    """B2 — 21 CFR 11.10(e): borrar tambien es una accion auditada.

    El escenario de la revision: redactar una alerta critica dejaba la cadena en
    verde, la raiz anclada identica y ningun rastro de que la alerta existio.
    """
    ledger.append("clinical-alert", {"spo2": 84, "severity": "critical"}, identity)
    alert = ledger[3]

    redaction = ledger.redact(3, auditor, "atribuida al tripulante equivocado", "cirujano")

    assert ledger.verify()
    assert redaction.target.payload is None and redaction.target.redacted
    tombstone = redaction.tombstone
    assert tombstone.index == 4
    assert tombstone.entry_type == REDACTION_ENTRY_TYPE
    assert tombstone.signer == "emma-audit"
    assert tombstone.payload == {
        "target_index": 3,
        "target_entry_hash": alert.entry_hash(),
        "target_content_hash": alert.content_hash,
        "reason": "atribuida al tripulante equivocado",
        "requested_by": "cirujano",
    }


def test_suppressing_content_without_a_tombstone_is_detected(ledger: HashChainLedger) -> None:
    """B2: vaciar el payload a mano, como hacia `redact()` antes, ya no cuela."""
    ledger._entries[1] = replace(ledger._entries[1], payload=None, redacted=True)

    result = ledger.verify()

    assert not result
    assert result.failed_index == 1
    assert result.reason == "contenido suprimido sin redacción registrada"


def test_clearing_the_redacted_flag_is_detected(
    ledger: HashChainLedger, auditor: Identity
) -> None:
    """B2: la marca no estaba firmada; borrarla dejaba la entrada como si nunca
    hubiera tenido contenido."""
    ledger.redact(1, auditor, "motivo", "cirujano")
    ledger._entries[1] = replace(ledger._entries[1], redacted=False)

    result = ledger.verify()

    assert not result
    assert result.failed_index == 1


def test_restoring_redacted_content_is_detected(
    ledger: HashChainLedger, auditor: Identity
) -> None:
    """Deshacer una rectificacion es tambien una alteracion."""
    original = ledger[1].payload
    ledger.redact(1, auditor, "motivo", "cirujano")
    ledger._entries[1] = replace(ledger._entries[1], payload=original, redacted=False)

    result = ledger.verify()

    assert not result
    assert result.failed_index == 1
    assert result.reason == "redacción registrada pero el contenido sigue presente"


def test_a_tombstone_cannot_be_redacted_nor_an_entry_twice(
    ledger: HashChainLedger, auditor: Identity
) -> None:
    redaction = ledger.redact(1, auditor, "motivo", "cirujano")
    with pytest.raises(ValueError, match="lápida"):
        ledger.redact(redaction.tombstone.index, auditor, "ocultar la redacción", "x")
    with pytest.raises(ValueError, match="ya está redactada"):
        ledger.redact(1, auditor, "otra vez", "x")
    assert ledger.verify()


def test_redaction_requires_reason_and_requester(
    ledger: HashChainLedger, auditor: Identity
) -> None:
    with pytest.raises(ValueError):
        ledger.redact(1, auditor, "   ", "cirujano")
    with pytest.raises(ValueError):
        ledger.redact(1, auditor, "motivo", "")
    with pytest.raises(ValueError):  # U+200B: `strip()` no lo quita
        ledger.redact(1, auditor, "\u200b", "cirujano")
    assert len(ledger) == 3


def test_the_redaction_entry_type_is_reserved(ledger: HashChainLedger, identity: Identity) -> None:
    """Una lapida escrita con `append()` podria justificar una supresion falsa."""
    with pytest.raises(ValueError):
        ledger.append(REDACTION_ENTRY_TYPE, {"target_index": 0}, identity)


def test_anchor_taken_before_redaction_still_verifies(
    ledger: HashChainLedger, auditor: Identity
) -> None:
    """§3.3: el ancla enviada a Tierra sigue siendo valida tras una redaccion.

    Y la redaccion queda visible para el ancla siguiente: la raiz completa cambia
    porque la lapida es una entrada nueva.
    """
    anchor = ledger.anchor()
    ledger.redact(0, auditor, "motivo", "cirujano")

    assert ledger.verify(anchor=anchor)
    assert ledger.merkle_root(size=anchor.tree_size) == anchor.root
    assert ledger.merkle_root() != anchor.root


# --------------------------------------------------------------------------- #
# B3 — Merkle, RFC 6962
# --------------------------------------------------------------------------- #


def _rfc6962_mth(entry_hashes: list[str]) -> str:
    """MTH de RFC 6962 §2.1, recursivo y literal. Independiente del codigo probado."""
    n = len(entry_hashes)
    if n == 0:
        return hashlib.sha256(b"").hexdigest()
    if n == 1:
        return hashlib.sha256(b"\x00" + bytes.fromhex(entry_hashes[0])).hexdigest()
    k = 1
    while k * 2 < n:
        k *= 2
    left = _rfc6962_mth(entry_hashes[:k])
    right = _rfc6962_mth(entry_hashes[k:])
    return hashlib.sha256(b"\x01" + bytes.fromhex(left) + bytes.fromhex(right)).hexdigest()


_HASHES = [sha256_hex(str(i).encode()) for i in range(40)]


@pytest.mark.parametrize("size", range(0, 34))
def test_merkle_root_matches_an_independent_rfc6962_implementation(size: int) -> None:
    """B3: la raiz es la de la RFC, comprobada contra su definicion recursiva."""
    assert merkle_root_of(_HASHES[:size]) == _rfc6962_mth(_HASHES[:size])


def test_duplicating_the_odd_leaf_changes_the_root() -> None:
    """B3 — CVE-2012-2459: `[a, b, c]` y `[a, b, c, c]` compartian raiz."""
    a, b, c = _HASHES[:3]
    assert merkle_root_of([a, b, c]) != merkle_root_of([a, b, c, c])


def _internal_node(left_entry: str, right_entry: str) -> str:
    left, right = leaf_hash(left_entry), leaf_hash(right_entry)
    return hashlib.sha256(b"\x01" + bytes.fromhex(left) + bytes.fromhex(right)).hexdigest()


def test_a_phantom_duplicated_leaf_has_no_valid_proof() -> None:
    """B3: la prueba de inclusion de una cuarta hoja fantasma validaba contra el ancla."""
    a, b, c = _HASHES[:3]
    root = merkle_root_of([a, b, c])
    phantom_proof = [(leaf_hash(c), False), (_internal_node(a, b), True)]
    assert not verify_merkle_proof(c, phantom_proof, root)


def test_an_internal_node_cannot_pass_as_an_entry() -> None:
    """B3: sin prefijos hoja/nodo, un nodo interno validaba como hoja con una prueba corta."""
    a, b, c = _HASHES[:3]
    root = merkle_root_of([a, b, c])
    assert not verify_merkle_proof(_internal_node(a, b), [(leaf_hash(c), False)], root)


def test_merkle_proof_roundtrip(ledger: HashChainLedger) -> None:
    """45 CFR 164.312(c)(2): corroborar que un registro no fue alterado."""
    root = ledger.merkle_root()
    assert len(root) == 64

    for index, entry_hash in enumerate(ledger.entry_hashes()):
        proof = ledger.merkle_proof(index)
        assert HashChainLedger.verify_merkle_proof(entry_hash, proof, root), (
            f"la prueba de la entrada {index} no válida contra la raíz"
        )


def test_merkle_proof_rejects_foreign_leaf(ledger: HashChainLedger) -> None:
    proof = ledger.merkle_proof(0)
    assert not HashChainLedger.verify_merkle_proof("f" * 64, proof, ledger.merkle_root())


def test_merkle_root_changes_when_entry_added(
    ledger: HashChainLedger, identity: Identity
) -> None:
    root_before = ledger.merkle_root()
    ledger.append("vital-signs", {"loinc": "8867-4", "value": 75}, identity)
    assert ledger.merkle_root() != root_before


@pytest.mark.parametrize("size", [1, 2, 3, 4, 5, 7, 8, 9, 16, 17])
def test_merkle_proofs_hold_for_any_chain_length(identity: Identity, size: int) -> None:
    """Arboles impares suben el ultimo nodo sin hermano: hay que probar ambos casos."""
    chain = _ledger_for(identity)
    for i in range(size):
        chain.append("vital-signs", {"seq": i}, identity)

    root = chain.merkle_root()
    for index, entry_hash in enumerate(chain.entry_hashes()):
        proof = chain.merkle_proof(index)
        assert verify_merkle_proof(entry_hash, proof, root), (
            f"fallo con cadena de {size} entradas, índice {index}"
        )


def test_empty_ledger() -> None:
    chain = HashChainLedger()
    assert chain.verify()
    # La raiz de un arbol vacio es la de la RFC, no el centinela de genesis:
    # antes eran el mismo valor y un ancla de "cadena vacia" era ambigua.
    assert chain.merkle_root() == hashlib.sha256(b"").hexdigest() != GENESIS_PREV_HASH
    assert chain.anchor() == Anchor(tree_size=0, root=chain.merkle_root())
    with pytest.raises(IndexError):
        chain.merkle_proof(0)


# --------------------------------------------------------------------------- #
# B4 — concurrencia
# --------------------------------------------------------------------------- #


@pytest.fixture
def frequent_thread_switches() -> Iterator[None]:
    """Cambios de hilo muy frecuentes: hace visible una carrera que ya existe."""
    previous = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    yield
    sys.setswitchinterval(previous)


def test_concurrent_appends_keep_the_chain_intact(frequent_thread_switches: None) -> None:
    """B4: el ledger desnudo, sin el cerrojo del almacen.

    Sin cerrojo propio, 8 hilos x 30 escrituras dejaban indices duplicados y una
    cadena rota para siempre.
    """
    writers = [Identity.generate(f"wearable-{i}") for i in range(8)]
    chain = _ledger_for(*writers, clock=lambda: datetime.now(UTC))

    def write(identity: Identity) -> None:
        for seq in range(30):
            chain.append("vital-signs", {"seq": seq}, identity)

    threads = [threading.Thread(target=write, args=(w,)) for w in writers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    indices = [entry.index for entry in chain.entries]
    assert indices == list(range(240))
    assert chain.verify()


# --------------------------------------------------------------------------- #
# M1 — serializacion canonica estricta
# --------------------------------------------------------------------------- #


def test_canonical_serialization_is_key_order_independent() -> None:
    """Dos procesos deben producir el mismo hash para el mismo contenido."""
    assert canonical_bytes({"a": 1, "b": 2}) == canonical_bytes({"b": 2, "a": 1})


@pytest.mark.parametrize(
    "payload",
    [
        {"value": Decimal("1.5")},  # colisionaba con {"value": "1.5"}
        {"at": T0},  # colisionaba con su texto
        {1: "a"},  # colisionaba con {"1": "a"}
        {"value": (1, 2)},  # colisionaba con [1, 2]
        {"value": float("nan")},  # salia como NaN, JSON invalido
        {"value": float("inf")},
        {"value": object()},  # colapsaba a su str()
    ],
    ids=["decimal", "datetime", "int-key", "tuple", "nan", "inf", "object"],
)
def test_non_json_payloads_are_rejected(
    ledger: HashChainLedger, identity: Identity, payload: dict[Any, Any]
) -> None:
    """M1: con `default=str`, contenidos distintos compartian hash."""
    with pytest.raises((TypeError, ValueError)):
        canonical_bytes(payload)
    with pytest.raises((TypeError, ValueError)):
        ledger.append("vital-signs", payload, identity)
    assert len(ledger) == 3


# --------------------------------------------------------------------------- #
# M2 — truncado de cola
# --------------------------------------------------------------------------- #


def test_without_an_anchor_tail_truncation_is_invisible(ledger: HashChainLedger) -> None:
    """LIMITE DECLARADO, no un fallo: lo que queda tras truncar es coherente.

    Esta prueba existe para que nadie afirme lo contrario. Detectarlo exige un
    testigo externo: el ancla de la prueba siguiente.
    """
    del ledger._entries[2:]
    assert ledger.verify()


def test_tail_truncation_is_detected_against_an_anchor(ledger: HashChainLedger) -> None:
    """M2 — 21 CFR 11.10(a): borrar las ultimas entradas, justo las del incidente."""
    anchor = ledger.anchor()
    del ledger._entries[2:]

    result = ledger.verify(anchor=anchor)

    assert not result
    assert result.failed_index == 2
    assert "más corta que el ancla" in (result.reason or "")


def test_an_anchored_prefix_cannot_be_rewritten(
    ledger: HashChainLedger, identity: Identity
) -> None:
    """Ni siquiera con la clave legitima: el ancla compromete cada entrada."""
    anchor = ledger.anchor()
    entry = ledger._entries[2]
    payload = {"loinc": "8867-4", "value": 40, "unit": "/min"}
    ledger._entries[2] = _forge(
        entry, identity, payload=payload, content_hash=sha256_hex(canonical_bytes(payload))
    )

    assert ledger.verify(), "internamente coherente: lo firmo la clave legitima"
    result = ledger.verify(anchor=anchor)
    assert not result
    assert "no reproduce la raíz" in (result.reason or "")


def test_an_anchor_with_an_unknown_algorithm_is_refused(ledger: HashChainLedger) -> None:
    anchor = replace(ledger.anchor(), algorithm="sha256-dup-v1")
    assert anchor.algorithm != MERKLE_ALGORITHM
    assert not ledger.verify(anchor=anchor)


# --------------------------------------------------------------------------- #
# M3 — marca de tiempo generada por el sistema
# --------------------------------------------------------------------------- #


def test_the_ledger_sets_the_timestamp_not_the_caller(identity: Identity) -> None:
    """M3 — 21 CFR 11.10(e): audit trail "computer-generated"."""
    chain = _ledger_for(identity, clock=_clock(T0))
    entry = chain.append("vital-signs", {"value": 60}, identity)
    assert entry.recorded == T0
    with pytest.raises(TypeError):
        chain.append("vital-signs", {"value": 61}, identity, recorded=T0)  # type: ignore[call-arg]


def test_a_clock_that_goes_back_never_produces_an_earlier_entry(identity: Identity) -> None:
    moments = iter([T0, T0 - timedelta(days=365)])
    chain = _ledger_for(identity, clock=lambda: next(moments))
    chain.append("vital-signs", {"value": 60}, identity)
    chain.append("vital-signs", {"value": 61}, identity)

    assert chain[1].recorded == chain[0].recorded
    assert chain.verify()


def test_a_naive_clock_is_rejected(identity: Identity) -> None:
    chain = _ledger_for(identity, clock=lambda: datetime(2026, 11, 14, 8, 0))
    with pytest.raises(ValueError, match="zona horaria"):
        chain.append("vital-signs", {"value": 60}, identity)


def test_a_backdated_entry_is_detected_even_with_the_legitimate_key(
    ledger: HashChainLedger, identity: Identity
) -> None:
    """M3: antes se podia antedatar un asiento para situarlo antes de un evento."""
    entry = ledger._entries[2]
    ledger._entries[2] = _forge(entry, identity, recorded=ledger[0].recorded - timedelta(days=1))

    result = ledger.verify()

    assert not result
    assert result.failed_index == 2
    assert "marca de tiempo" in (result.reason or "")


# --------------------------------------------------------------------------- #
# M4 — el ledger no comparte su estado
# --------------------------------------------------------------------------- #


def test_caller_mutation_after_append_does_not_touch_the_ledger(identity: Identity) -> None:
    """M4: guardado por referencia, esto era un falso positivo de manipulacion."""
    chain = _ledger_for(identity)
    payload: dict[str, Any] = {"value": 62}
    returned = chain.append("vital-signs", payload, identity)

    payload["value"] = 999
    assert returned.payload is not None
    returned.payload["value"] = 555

    assert chain.verify()
    assert _unsalted(chain[0].payload) == {"value": 62}


def test_mutating_the_view_does_not_touch_the_ledger(ledger: HashChainLedger) -> None:
    """11.10(c): las entradas expuestas son copias; no hay via de reescritura por ahi."""
    entries = ledger.entries
    assert isinstance(entries, tuple)
    with pytest.raises((AttributeError, TypeError)):
        entries[0].payload = {"manipulado": True}  # type: ignore[misc]

    assert entries[0].payload is not None
    entries[0].payload["value"] = 1234
    view = ledger[0].payload
    assert view is not None
    view["value"] = 4321

    assert ledger.verify()
    assert _unsalted(ledger[0].payload) == {"loinc": "8867-4", "value": 62, "unit": "/min"}


# --------------------------------------------------------------------------- #
# M5, M6 y transacciones
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("index", [-1, 3, 99])
def test_redact_rejects_out_of_range_indices(
    ledger: HashChainLedger, auditor: Identity, index: int
) -> None:
    """M5: `redact(-1)` redactaba en silencio la ultima entrada."""
    with pytest.raises(IndexError):
        ledger.redact(index, auditor, "motivo", "cirujano")
    assert len(ledger) == 3
    assert all(entry.payload is not None for entry in ledger.entries)


def test_the_chain_commits_to_signatures(ledger: HashChainLedger) -> None:
    """M6: ni la cadena ni la raiz comprometian quien firmo."""
    entry = ledger[0]
    assert replace(entry, signature="00" * 64).entry_hash() != entry.entry_hash()


def test_skipping_known_signatures_still_catches_a_changed_one(ledger: HashChainLedger) -> None:
    """Con una entrada detras, cambiar una firma ya verificada rompe su enlace: el
    atajo no la oculta. La ultima no tiene detras: ver la prueba de su limite."""
    ledger._entries[0] = replace(ledger._entries[0], signature="00" * 64)

    result = ledger.verify(signatures_from=2)

    assert not result
    assert result.failed_index == 1
    assert "prev_hash" in (result.reason or "")


def test_a_failed_transaction_rolls_back_chain_redaction_and_registry(
    ledger: HashChainLedger, auditor: Identity
) -> None:
    """Lo que nunca llego a disco no puede quedarse en memoria, tampoco una clave."""
    newcomer = Identity.generate("wearable-02")
    root_before = ledger.merkle_root()

    with pytest.raises(RuntimeError), ledger.transaction():
        ledger.registry.register(newcomer.identity_id, newcomer.public_key_hex)
        ledger.append("vital-signs", {"value": 80}, newcomer)
        ledger.redact(0, auditor, "motivo", "cirujano")
        raise RuntimeError("commit fallido")

    assert len(ledger) == 3
    assert ledger[0].payload is not None
    assert "wearable-02" not in ledger.registry
    assert ledger.merkle_root() == root_before
    assert ledger.verify()


# --------------------------------------------------------------------------- #
# Segunda revision (2026-09-22): quien puede firmar una lapida
# --------------------------------------------------------------------------- #


def _forge_tombstone(ledger: HashChainLedger, target_index: int, signer: Identity) -> LedgerEntry:
    """Lapida fabricada a mano y firmada por `signer`, como la escribiria un atacante."""
    target, previous = ledger._entries[target_index], ledger._entries[-1]
    payload = {
        "target_index": target_index,
        "target_entry_hash": target.entry_hash(),
        "target_content_hash": target.content_hash,
        "reason": "lectura erronea",
        "requested_by": "cirujano",
    }
    tombstone = LedgerEntry(
        index=len(ledger._entries),
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


def _erase_with(ledger: HashChainLedger, target_index: int, signer: Identity) -> None:
    ledger._entries.append(_forge_tombstone(ledger, target_index, signer))
    ledger._entries[target_index] = replace(
        ledger._entries[target_index], payload=None, redacted=True
    )


def test_a_source_key_cannot_sign_a_tombstone(ledger: HashChainLedger, identity: Identity) -> None:
    """Cualquier clave registrada podia firmar una lapida. Con la del wearable se
    borraba una alerta critica y `verify()` salia en verde, tambien contra el ancla."""
    ledger.append("clinical-alert", {"spo2": 84, "severity": "critical"}, identity)
    anchor = ledger.anchor()

    with pytest.raises(UntrustedSigner):
        ledger.redact(3, identity, "motivo", "cirujano")
    _erase_with(ledger, 3, identity)

    for result in (ledger.verify(), ledger.verify(anchor=anchor)):
        assert not result
        assert result.failed_index == 3
        assert result.reason == "contenido suprimido sin redacción registrada"


def test_a_newly_registered_identity_cannot_authorise_a_suppression(
    ledger: HashChainLedger,
) -> None:
    """El ataque sin ninguna clave privada del sistema: dar de alta una identidad nueva
    —el registro lo admite, no suplanta a nadie— y firmar con ella la lapida."""
    anchor = ledger.anchor()
    intruder = Identity.generate("mantenimiento")
    ledger.registry.register(intruder.identity_id, intruder.public_key_hex)
    _erase_with(ledger, 2, intruder)

    assert not ledger.verify()
    assert not ledger.verify(anchor=anchor)
    assert 2 not in ledger.redacted_indices()


def test_declaring_the_authority_key_without_its_signature_does_not_count(
    ledger: HashChainLedger, auditor: Identity
) -> None:
    forger = Identity.generate("emma-audit")
    forged = replace(_forge_tombstone(ledger, 1, forger), signer_public_key=auditor.public_key_hex)
    ledger._entries.append(forged)
    ledger._entries[1] = replace(ledger._entries[1], payload=None, redacted=True)

    assert 1 not in ledger.redacted_indices()
    result = ledger.verify()
    assert not result
    assert result.failed_index == 1


def test_without_an_authority_there_are_no_redactions(
    identity: Identity, auditor: Identity
) -> None:
    chain = _ledger_for(identity)
    chain.append("vital-signs", {"value": 60}, identity)

    with pytest.raises(UntrustedSigner, match="autoridad"):
        chain.redact(0, auditor, "motivo", "cirujano")
    assert chain.verify()


def test_the_authority_cannot_sign_clinical_data(
    ledger: HashChainLedger, auditor: Identity
) -> None:
    """Una clave pensada para rectificar no fabrica lecturas, ni aunque alguien la
    meta en el registro."""
    with pytest.raises(UntrustedSigner):
        ledger.append("vital-signs", {"value": 60}, auditor)
    ledger.registry.register(auditor.identity_id, auditor.public_key_hex)
    with pytest.raises(UntrustedSigner):
        ledger.append("vital-signs", {"value": 60}, auditor)


_BAD_TOMBSTONES: list[Any] = [
    ["no", "es", "un", "dict"],
    42,
    {"target_index": 0},
    {
        "target_index": 99,
        "target_entry_hash": "",
        "target_content_hash": "",
        "reason": "m",
        "requested_by": "c",
    },
    {
        "target_index": True,
        "target_entry_hash": "",
        "target_content_hash": "",
        "reason": "m",
        "requested_by": "c",
    },
]


@pytest.mark.parametrize(
    "payload", _BAD_TOMBSTONES, ids=["lista", "entero", "incompleta", "fuera-de-rango", "bool"]
)
def test_a_malformed_tombstone_is_a_failure_not_a_crash(
    ledger: HashChainLedger, auditor: Identity, payload: Any
) -> None:
    """Una lapida basura lanzaba TypeError o IndexError en vez de devolver un fallo, y
    con ello `/api/status` daba 500."""
    tombstone = ledger._append(REDACTION_ENTRY_TYPE, payload, auditor)

    result = ledger.verify()

    assert not result
    assert result.failed_index == tombstone.index


def test_an_earlier_edit_is_reported_before_a_later_bad_tombstone(
    ledger: HashChainLedger, auditor: Identity
) -> None:
    """Las lapidas se validaban antes que nada: una basura al final tapaba en
    `failed_index` una edicion anterior."""
    ledger._append(REDACTION_ENTRY_TYPE, {"basura": True}, auditor)
    ledger._entries[1] = replace(ledger._entries[1], payload={"value": 999})

    assert ledger.verify().failed_index == 1


def test_the_signature_shortcut_trusts_process_memory(ledger: HashChainLedger) -> None:
    """LIMITE DECLARADO. `signatures_from` no lo sostiene el encadenamiento: la ultima
    entrada no tiene siguiente. Lo sostiene que la memoria es privada del proceso; por
    eso el almacen solo salta firmas que ya verifico en memoria."""
    last = len(ledger) - 1
    ledger._entries[last] = replace(ledger._entries[last], signature="00" * 64)

    assert ledger.verify(signatures_from=len(ledger)), "el atajo salta la de la última"
    assert not ledger.verify(), "sin el atajo, se ve"


def test_a_malformed_anchor_is_refused(ledger: HashChainLedger) -> None:
    """Un tamano negativo cortaba la cadena por la cola y validaba un prefijo corto."""
    assert not ledger.verify(anchor=Anchor(tree_size=-1, root=ledger.merkle_root(size=2)))
    assert not ledger.verify(anchor=Anchor(tree_size=3, root="abc"))


def _rfc6962_path(index: int, entry_hashes: list[str]) -> list[tuple[str, bool]]:
    """PATH de RFC 6962 §2.1.1, recursivo y literal, en el formato de las pruebas."""
    n = len(entry_hashes)
    if n == 1:
        return []
    k = 1
    while k * 2 < n:
        k *= 2
    if index < k:
        return [*_rfc6962_path(index, entry_hashes[:k]), (_rfc6962_mth(entry_hashes[k:]), False)]
    return [*_rfc6962_path(index - k, entry_hashes[k:]), (_rfc6962_mth(entry_hashes[:k]), True)]


@pytest.mark.parametrize("size", range(1, 34))
def test_merkle_proofs_match_an_independent_rfc6962_path(size: int) -> None:
    """Las pruebas de inclusion son las de la RFC, no las que el codigo cree correctas.

    Sustituye a una comprobacion espejo que comparaba `merkle_proof` con
    `merkle_proof_of`, que es literalmente lo que llama por dentro.
    """
    hashes = _HASHES[:size]
    for index in range(size):
        assert merkle_proof_of(hashes, index) == _rfc6962_path(index, hashes)


# --------------------------------------------------------------------------- #
# Cuarta revision (2026-09-22)
# --------------------------------------------------------------------------- #


def test_the_salt_field_is_reserved(ledger: HashChainLedger, identity: Identity) -> None:
    """La sal la pone el ledger. Un llamante que la fijara podria reproducir el hash de
    un contenido conocido, que es justo lo que la sal impide."""
    with pytest.raises(ValueError, match="_salt"):
        ledger.append("vital-signs", {"value": 60, "_salt": "fija"}, identity)


def test_the_clock_only_follows_a_previous_entry_that_verifies(
    ledger: HashChainLedger, identity: Identity
) -> None:
    """Cuarta revision: una fecha futura en un asiento manipulado se heredaba en todas las
    escrituras siguientes. El reloj solo se iguala al anterior si este verifica."""
    last = len(ledger) - 1
    ledger._entries[last] = replace(ledger._entries[last], recorded=T0 + timedelta(days=3650))

    entry = ledger.append("vital-signs", {"value": 60}, identity)

    assert entry.recorded < T0 + timedelta(days=1)


def test_a_payload_nested_beyond_the_limit_is_rejected(
    ledger: HashChainLedger, identity: Identity
) -> None:
    deep: Any = 1
    for _ in range(40):
        deep = [deep]
    with pytest.raises(ValueError, match="anidamiento"):
        ledger.append("vital-signs", {"value": deep}, identity)


def test_unencodable_text_is_rejected(ledger: HashChainLedger, identity: Identity) -> None:
    with pytest.raises(ValueError, match="UTF-8"):
        ledger.append("vital-signs", {"subject": "\ud800"}, identity)
