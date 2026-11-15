"""Redactar un TAC redacta también sus segmentaciones (`ObservationStore.redact`).

Por qué existe: el binario firmado de una segmentación (`record-integrity.md` §3.13) lleva un
volumen recortado del estudio —sus píxeles—, además de etiquetas y mallas. Hasta la duodécima
ronda, redactar el estudio borraba su volumen y dejaba ese recorte en la base, firmado y servible
por su índice. Decisión del usuario (2026-10-15): se redacta con el estudio, en el mismo
`commit`, cada una con su lápida, el mismo solicitante y el motivo «redactado con el estudio del
asiento N: <motivo>», y su binario se borra como el del estudio; si una falla, nada.

Qué se defiende: eso; que lo de otro estudio no se toca; que una segmentación se sigue pudiendo
redactar sola, sin tocar el estudio; y que un ledger escrito antes del cambio sigue verificando
con sus hashes, ahora redacta en cascada y, reabierto, no guarda ni el binario ni nada que
identifique. Sin red y sin TotalSegmentator (se simula, como en `test_volumes.py`).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import audit_identity, get_store
from app.core.ledger import RedactionAuthority
from app.core.storage import ImagingBlobRow, ObservationStore
from tests.test_contrast_phase import _seeded, _signed_text, declare, listed
from tests.test_volumes import (  # noqa: F401 — `fake_segmenter` es una fixture
    EARLIER,
    LATER,
    fake_segmenter,
    segmented,
    wait,
)

REASON = "estudio de otro tripulante"


def segment_again(client: TestClient, study: int) -> int:
    """Otra segmentación del mismo estudio; devuelve su asiento."""
    done = wait(client, client.post(f"/api/volumes/{study}/segment").json()["job"])
    assert done["state"] == "done", done
    return int(done["ledger_index"])


def stored_blobs(store: ObservationStore) -> list[int]:
    """Los asientos que aún tienen binario en la base."""
    with Session(store.engine) as session:
        return sorted(session.scalars(select(ImagingBlobRow.ledger_index)).all())


def study_of(store: ObservationStore, segmentation: int) -> int:
    return int(store.segmentation_blob(segmentation)[0]["study_index"])


# --------------------------------------------------------------------------- #
# La cascada
# --------------------------------------------------------------------------- #


def test_redacting_a_ct_redacts_its_segmentations_each_with_its_tombstone(
    client: TestClient, fake_segmenter: None, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    store = get_store()
    first = segmented(client, monkeypatch, EARLIER)
    study = study_of(store, first)
    second = segment_again(client, study)
    declared = declare(client, study, declared_by="Dra. Ana Pérez").json()["ledger_index"]
    elsewhere = segmented(client, monkeypatch, LATER)
    other = study_of(store, elsewhere)
    # Las huellas de sus segmentaciones. La del estudio no: los dos TAC subidos tienen los mismos
    # vóxeles (`ct_with_lesions` solo cambia las máscaras), y su huella coincide con la del otro
    # cuando el gzip de los dos cae en el mismo segundo. Esa se mira con el ledger de antes.
    fingerprints = [store.segmentation_blob(index)[0]["sha256"] for index in (first, second)]
    assert not {store.segmentation_blob(elsewhere)[0]["sha256"]} & set(fingerprints)
    assert stored_blobs(store) == sorted([study, first, second, other, elsewhere])
    size = len(store.ledger)

    response = client.post(f"/api/audit/redact/{study}",
                           json={"reason": REASON, "requested_by": "CMO"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["redacted_index"] == study and body["chain_still_valid"]
    # Una lápida por asiento, en el mismo `commit` y en el orden de la cadena.
    assert len(store.ledger) == size + 4
    assert body["dependent_redactions"] == [
        {"redacted_index": first, "redaction_entry_index": size + 1},
        {"redacted_index": second, "redaction_entry_index": size + 2},
        {"redacted_index": declared, "redaction_entry_index": size + 3},
    ]
    for item in body["dependent_redactions"]:
        tombstone = store.ledger.entries[item["redaction_entry_index"]].payload
        assert tombstone["target_index"] == item["redacted_index"]
        assert tombstone["requested_by"] == "CMO"
        assert tombstone["reason"] == f"redactado con el estudio del asiento {study}: {REASON}"
    for index in (study, first, second, declared):
        assert store.ledger.entries[index].payload is None
    # El binario de cada segmentación se borra como el del estudio; los del otro, no.
    assert stored_blobs(store) == sorted([other, elsewhere])
    for index in (first, second):
        with pytest.raises(KeyError):
            store.segmentation_blob(index)
        served = client.get(f"/api/volumes/segmentations/{index}/files/ct.nii.gz")
        assert served.status_code == 404
    signed = _signed_text(store)
    assert "Pérez" not in signed and not any(value in signed for value in fingerprints)
    shown = listed(client)
    assert list(shown) == [other]
    assert [item["ledger_index"] for item in shown[other]["segmentations"]] == [elsewhere]
    assert store.segmentation_blob(elsewhere)[1]
    assert store.verify_integrity().ok


@pytest.mark.parametrize("failing", ["segmentation", "declaration"])
def test_a_failed_cascade_writes_nothing_and_keeps_every_binary(
    client: TestClient, fake_segmenter: None, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
    failing: str,
) -> None:
    """Todo o nada. Si falla la última, la segmentación ya estaba redactada dentro de la
    transacción, y su binario borrado en la sesión: nada de eso llega a escribirse."""
    store = get_store()
    segmentation = segmented(client, monkeypatch, EARLIER)
    study = study_of(store, segmentation)
    declared = declare(client, study).json()["ledger_index"]
    target = {"segmentation": segmentation, "declaration": declared}[failing]
    size, original = len(store.ledger), store.ledger.redact

    def broken(index: int, *args: Any) -> Any:
        if index == target:
            raise RuntimeError("fallo a mitad")
        return original(index, *args)

    monkeypatch.setattr(store.ledger, "redact", broken)
    with pytest.raises(RuntimeError):
        store.redact(study, audit_identity(), "motivo", "CMO")
    monkeypatch.undo()

    assert len(store.ledger) == size
    for index in (study, segmentation, declared):
        assert store.ledger.entries[index].payload is not None
    assert stored_blobs(store) == [study, segmentation]
    assert store.volume_blob(study)[1] and store.segmentation_blob(segmentation)[1]
    assert store.verify_integrity().ok
    # Y después, sin el fallo, se redacta entero.
    redaction = store.redact(study, audit_identity(), "motivo", "CMO")
    assert [item.target.index for item in redaction.dependents] == [segmentation, declared]
    assert stored_blobs(store) == []


def test_redacting_a_segmentation_alone_leaves_the_study(
    client: TestClient, fake_segmenter: None, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    store = get_store()
    segmentation = segmented(client, monkeypatch, EARLIER)
    study = study_of(store, segmentation)

    redaction = store.redact(segmentation, audit_identity(), "segmentación repetida", "CMO")

    assert redaction.dependents == ()
    assert store.volume_blob(study)[1]
    assert stored_blobs(store) == [study]
    assert listed(client)[study]["segmentations"] == []
    # Redactar después el estudio ya no la arrastra: no le queda contenido que quitar.
    assert store.redact(study, audit_identity(), REASON, "CMO").dependents == ()
    assert stored_blobs(store) == []
    assert store.verify_integrity().ok


# --------------------------------------------------------------------------- #
# Un ledger escrito antes del cambio
# --------------------------------------------------------------------------- #

# Escrito con el código de `main` ANTERIOR a este cambio (commit 1923077), con
# `scratchpad/g1/make_pre_db.py` de la duodécima ronda (unidad G1), que registra con
# `_study_payload` y `_record_segmentation` de `app/api/volumes.py`: un TAC (0) con su
# segmentación (1) y la fase que declaró «Dra. Ana Pérez» (2); otro TAC (3) con su segmentación
# (4), redactado con la regla de entonces (lápida 5), que dejó la segmentación firmada y con su
# binario. TAC sintéticos de 40³ vóxeles. Claves fijas: la autoridad de redacción es la semilla
# 7, la consola la 9 y el segmentador la 11. Los hashes de contenido son los que firmó aquel código.
PRE_CHANGE_LEDGER = Path(__file__).parent / "data" / "volumes_pre_segmentation_redaction.db"
PRE_CHANGE_HASHES = [
    "75e60c0d125076a77bc2d755a03cb9433b4e631c5959b2a3af43c4b5b2bdb72e",
    "b6f9269e659ac2d77ce45b71ebd98da77794d8a59f4c2f4e37b5eb8651439bc6",
    "61ef221a14a182f282e8e6686d5a4a967fd6e83d7754de9eb59344f0c105b7a0",
    "9dacdeeae3cb2ba1c0c5e33c174c342fce55376671270df8597d59ff69f89c87",
    "cc0bc88eeb1d359cedf7cd420ca30860c2f60e21fd0c224bb9b07b5c21ecf4f8",
    "4a05e33c0cdba64c1b1c4d0f843f1c502406a8398c56f98f860f34583986aa7c",
]


def test_a_ledger_signed_before_the_change_still_verifies_and_now_redacts_its_segmentations(
    tmp_path: Path,
) -> None:
    path = tmp_path / "emma.db"
    shutil.copyfile(PRE_CHANGE_LEDGER, path)
    authority = _seeded("emma-audit", 7)
    store = ObservationStore.at(path, RedactionAuthority.of(authority))
    try:
        assert store.verify_integrity().ok
        assert [entry["content_hash"] for entry in store.audit_trail()] == PRE_CHANGE_HASHES
        [ct] = store.volume_studies("crew-01")
        [segmentation] = store.volume_segmentations(0)
        assert (ct["ledger_index"], segmentation["ledger_index"]) == (0, 1)
        # La segmentación del TAC redactado antes de esta regla sigue firmada, con su binario, y
        # verifica; ninguna vista la enseña, porque todas parten de los estudios vigentes.
        orphan, orphan_bytes = store.segmentation_blob(4)
        assert orphan["study_index"] == 3 and orphan_bytes
        assert stored_blobs(store) == [0, 1, 4]
        identifying = [
            ct["sha256"], segmentation["sha256"], orphan["sha256"], orphan["study_sha256"],
        ]
        pixels = [store.volume_blob(0)[1], store.segmentation_blob(1)[1], orphan_bytes]

        # Ahora, redactar el TAC vigente redacta su segmentación y su fase, en ese orden.
        redaction = store.redact(0, authority, REASON, "CMO")
        assert [item.target.index for item in redaction.dependents] == [1, 2]
        assert [item.tombstone.payload["reason"] for item in redaction.dependents] == [
            f"redactado con el estudio del asiento 0: {REASON}"] * 2
        assert stored_blobs(store) == [4]
        assert store.verify_integrity().ok
        assert [e["content_hash"] for e in store.audit_trail()][:6] == PRE_CHANGE_HASHES
        # Y la segmentación huérfana de antes se redacta por su índice, como cualquier asiento.
        assert store.redact(4, authority, "segmentación de un estudio ya redactado",
                            "CMO").dependents == ()
        assert stored_blobs(store) == []
        assert store.verify_integrity().ok
    finally:
        store.engine.dispose()

    # Reabierta: la cadena verifica y no queda ni el binario ni nada que identifique.
    reopened = ObservationStore.at(path, RedactionAuthority.of(authority))
    try:
        assert reopened.verify_integrity().ok
        assert len(reopened.ledger) == len(PRE_CHANGE_HASHES) + 4
        assert reopened.volume_studies("crew-01") == []
        assert reopened.volume_segmentations(0) == reopened.volume_segmentations(3) == []
        assert stored_blobs(reopened) == []
        signed = _signed_text(reopened)
        assert "Pérez" not in signed and not any(value in signed for value in identifying)
    finally:
        reopened.engine.dispose()
    # Ni en el fichero: `secure_delete` pone a cero lo borrado (§3.6).
    raw = path.read_bytes()
    assert "Pérez".encode() not in raw
    assert not any(value.encode() in raw for value in identifying)
    assert not any(blob[len(blob) // 2:len(blob) // 2 + 64] in raw for blob in pixels)
