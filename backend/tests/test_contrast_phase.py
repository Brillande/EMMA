"""La fase de contraste de un TAC, declarada por una persona (`volumes/contrast_phase.py`).

Qué se defiende: que es una etiqueta firmada y no una medida; que solo se firma lo que el
vocabulario cerrado deja, de un TAC vigente y con el nombre de quien lo dice; que se enseña junto
a la densidad sin tocar ninguna cifra ni lo firmado; y que no decide nada: el estado de la
evolución y `/api/status` son los mismos con y sin declaración. Sin red y sin TotalSegmentator
(se simula, como en `test_volumes.py`).
"""

from __future__ import annotations

import datetime as dt
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import text_guard
from app.api.routes import CONSOLE_IDENTITY, audit_identity, get_store, identity_for
from app.core.ledger import Identity
from app.core.storage import (
    _VOLUME_PHASE_FIELDS,
    IMAGING_FINDINGS_ENTRY_TYPE,
    VOLUME_PHASE_ENTRY_TYPE,
    ObservationStore,
    TamperedRecordError,
)
from app.volumes import contrast_phase as phases
from app.volumes import geometry
from tests.test_volumes import (  # noqa: F401 — `fake_segmenter` es una fixture
    EARLIER,
    EYE,
    LATER,
    fake_segmenter,
    nifti_bytes,
    segmented,
    synthetic_ct,
    upload,
)

T0 = dt.datetime(2026, 12, 1, 8, 0, tzinfo=dt.UTC)
FAR = "2100-01-01T00:00:00+00:00"
# Ledger con un TAC (asiento 0), su segmentación con la densidad firmada (1), una RM (2) y una
# declaración de recurso (3), escrito con el código de `main` ANTERIOR a este cambio (commit
# c408bb6, exportado con `git archive main backend/app polaris`) y guardado tal cual. Los hashes
# de contenido son los que firmó aquel código.
PRE_CHANGE_LEDGER = Path(__file__).parent / "data" / "volumes_pre_contrast_phase.db"
PRE_CHANGE_HASHES = [
    "1e11d4b9d553e1e24124b6dad1b7d210c99b2d9f760321d3af8e943eb87d96cd",
    "9f3d09136cd2d82c5412c0b5576203745eac5d45ba68e997fd9aa7b8f5064012",
    "b6f5831d1f1501151f445f5f371972a3644b239ef581e33e8bd8603a98f06fee",
    "51a005c511cc511b34d19613838c295b1142f9b8190277e725f3bbd8474d7e00",
]
STUDY = {"ledger_index": 4, "sha256": "huella", "modality": "CT", "subject": "crew-01"}


def told(index: int, phase: str, **change: Any) -> dict[str, Any]:
    """Una declaración tal y como la entrega el almacén."""
    return {
        "subject": "crew-01", "study_index": 4, "study_sha256": "huella", "phase": phase,
        "at": T0.isoformat(), "note": "", "declared_by": "CMO", "ledger_index": index,
        "recorded": (T0 + dt.timedelta(minutes=index)).isoformat(), "signer": CONSOLE_IDENTITY,
        **change,
    }


def declare(client: TestClient, study: int, phase: str = "arterial", **change: Any) -> Any:
    body = {"phase": phase, "declared_by": "CMO", **change}
    return client.post(f"/api/volumes/{study}/contrast-phase", json=body)


def listed(client: TestClient, subject: str = "crew-01") -> dict[int, dict[str, Any]]:
    studies = client.get("/api/volumes", params={"subject": subject}).json()
    return {int(study["ledger_index"]): study for study in studies}


def upload_mr(client: TestClient) -> int:
    response = client.post(
        "/api/volumes", params={"recorded_by": "CMO", "modality": "MR"},
        content=nifti_bytes(nib.Nifti1Image(np.zeros((8, 8, 8), np.int16), EYE)),
        headers={"Content-Type": "application/gzip"},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["ledger_index"])


# --------------------------------------------------------------------------- #
# El vocabulario y lo que se lee de las declaraciones
# --------------------------------------------------------------------------- #


def test_the_vocabulary_is_closed_and_undeclared_cannot_be_signed() -> None:
    assert phases.PHASES == {
        "non-contrast": "sin contraste", "arterial": "arterial",
        "portal-venous": "portal (venosa portal)", "delayed": "tardía",
        "unknown": "no se sabe",
    }
    for code in phases.PHASES:
        phases.check(code)
    # «Sin declarar» no se firma: es no haber dicho nada. Y «no se sabe» no es lo mismo.
    assert phases.UNDECLARED_DISPLAY == "sin declarar" != phases.PHASES[phases.UNKNOWN]
    for outside in ("undeclared", "sin declarar", "Arterial", "arterial ", "", "venous", "none"):
        with pytest.raises(ValueError, match="fuera del vocabulario"):
            phases.check(outside)


def test_the_latest_console_declaration_holds_and_the_earlier_ones_stay() -> None:
    view = phases.describe(
        [told(5, "arterial"), told(7, "portal-venous", declared_by="CDR", note="del informe")],
        STUDY, CONSOLE_IDENTITY,
    )
    assert view["applicable"] and view["not_applicable_reason"] is None
    assert view["current"] == {
        "code": "portal-venous", "display": "portal (venosa portal)", "declared_by": "CDR",
        "at": T0.isoformat(), "note": "del informe", "ledger_index": 7,
        "recorded": (T0 + dt.timedelta(minutes=7)).isoformat(),
    }
    assert [item["code"] for item in view["history"]] == ["arterial", "portal-venous"]
    assert view["history"][0]["note"] is None
    assert view["undeclared_display"] == "sin declarar"


@pytest.mark.parametrize("change", [
    {"signer": "simulator"},  # no la firmó la consola
    {"study_index": 9},  # habla de otro estudio
    {"study_sha256": "otra-huella"},  # cita otro volumen que el firmado en ese asiento
    {"phase": "venous"},  # la ruta no la habría firmado
    {"declared_by": "123"},  # sin nombre
])
def test_a_declaration_that_does_not_count_is_as_if_nobody_had_said_anything(
    change: dict[str, Any],
) -> None:
    view = phases.describe([{**told(5, "arterial"), **change}], STUDY, CONSOLE_IDENTITY)
    assert view["current"] is None and view["history"] == []
    # …y no tapa a la que sí cuenta, aunque sea posterior.
    both = phases.describe(
        [told(5, "delayed"), {**told(6, "arterial"), **change}], STUDY, CONSOLE_IDENTITY
    )
    assert both["current"]["code"] == "delayed" and len(both["history"]) == 1


def test_outside_a_ct_the_phase_does_not_apply() -> None:
    view = phases.describe([told(5, "arterial")], {**STUDY, "modality": "MR"}, CONSOLE_IDENTITY)
    assert not view["applicable"] and view["current"] is None and view["history"] == []
    assert view["not_applicable_reason"] == phases.NOT_CT.format(modality="MR")
    with pytest.raises(ValueError, match="solo se declara en un TAC"):
        phases.check_modality("MR")
    phases.check_modality("CT")


# --------------------------------------------------------------------------- #
# Junto a la densidad: la fase, y ni una cifra distinta
# --------------------------------------------------------------------------- #


def _measured() -> dict[str, Any]:
    return {
        "preset": "higado",
        "lesiones": [{"id": 1, "densidad": {"valorable": True, "mediana_hu": 20.0}}],
        "densidad": {
            "disponible": True, "fase_contraste": None,
            "referencia": {"nombre": "parénquima", "mediana_hu": 60.0},
            "notas": [geometry.DENSITY_NOTE, geometry.PHASE_UNDECLARED],
        },
    }


def _annotated(segmentation: dict[str, Any], current: dict[str, Any] | None) -> dict[str, Any]:
    return phases.annotate(
        segmentation, current, geometry.DENSITY_KEY, geometry.PHASE_UNDECLARED
    )


def test_the_declared_phase_goes_next_to_the_density_and_touches_no_figure() -> None:
    segmentation = _measured()
    current = phases.describe([told(5, "arterial")], STUDY, CONSOLE_IDENTITY)["current"]
    shown = _annotated(segmentation, current)
    block = shown["densidad"]
    assert block["fase_contraste"] == current
    # La nota de «no declara» se va; la que dice que la densidad es descriptiva, no.
    assert geometry.PHASE_UNDECLARED not in block["notas"]
    assert block["notas"][0] == geometry.DENSITY_NOTE
    assert block["notas"][-1] == phases.DECLARED_NOTE.format(
        declared_by="CMO", display="arterial"
    )
    # Ninguna cifra cambia, y lo recibido no se toca.
    assert shown["lesiones"] == segmentation["lesiones"]
    assert block["referencia"] == segmentation["densidad"]["referencia"]
    assert segmentation == _measured()


def test_someone_who_looked_and_does_not_know_is_not_the_same_as_nobody_saying() -> None:
    current = phases.describe([told(5, "unknown")], STUDY, CONSOLE_IDENTITY)["current"]
    block = _annotated(_measured(), current)["densidad"]
    assert block["fase_contraste"]["code"] == "unknown"
    assert block["notas"][-1] == phases.UNKNOWN_NOTE.format(declared_by="CMO", display="")
    assert geometry.PHASE_UNDECLARED not in block["notas"]


def test_without_a_declaration_or_without_density_nothing_changes() -> None:
    segmentation = _measured()
    assert _annotated(segmentation, None) is segmentation
    current = phases.describe([told(5, "arterial")], STUDY, CONSOLE_IDENTITY)["current"]
    for bare in (
        {"preset": "esqueleto"},
        {"densidad": geometry.no_density(geometry.NOT_CT.format(modality="MR"))},
    ):
        assert _annotated(bare, current) is bare


# --------------------------------------------------------------------------- #
# La comparación de dos estudios: se dice lo que consta, sin veredicto
# --------------------------------------------------------------------------- #


def _phase(code: str | None, modality: str = "CT") -> dict[str, Any]:
    declarations = [] if code is None else [told(5, code)]
    return phases.describe(declarations, {**STUDY, "modality": modality}, CONSOLE_IDENTITY)


@pytest.mark.parametrize(("before", "after", "state"), [
    ("arterial", "arterial", phases.SAME),
    ("non-contrast", "non-contrast", phases.SAME),
    ("arterial", "portal-venous", phases.DIFFERENT),
    ("delayed", "non-contrast", phases.DIFFERENT),
    (None, None, phases.MISSING),
    ("arterial", None, phases.MISSING),
    (None, "arterial", phases.MISSING),
    # Dos estudios de los que no se sabe la fase no están «en la misma».
    ("unknown", "unknown", phases.MISSING),
    ("unknown", "arterial", phases.MISSING),
])
def test_two_phases_are_the_same_only_if_both_are_known_and_equal(
    before: str | None, after: str | None, state: str
) -> None:
    block = phases.compare(_phase(before), _phase(after))
    assert block["estado"] == state
    assert block["antes"] == _phase(before)["current"]
    assert block["despues"] == _phase(after)["current"]
    if state == phases.SAME:
        assert "misma fase" in block["texto"] and "sin veredicto" in block["texto"]
    else:
        assert "no se pueden poner una junto a otra como iguales" in block["texto"]
    for code in (before, after):
        name = phases.UNDECLARED_DISPLAY if code is None else phases.PHASES[code]
        assert name in block["texto"]


def test_a_comparison_with_a_study_that_is_not_a_ct_says_so() -> None:
    block = phases.compare(_phase(None, "MR"), _phase("arterial"))
    assert (block["estado"], block["texto"]) == (
        phases.NOT_APPLICABLE, phases.NOT_APPLICABLE_TEXT)


def test_what_is_said_about_the_phase_describes_and_neither_orders_nor_classifies() -> None:
    """Invariantes 6 y 7: ni orden, ni diagnóstico, ni «realce», ni el nombre de una lesión."""
    vocabulary = phases.vocabulary()
    shown = [
        *phases.PHASES.values(), phases.UNDECLARED_DISPLAY, phases.DECLARED_LABEL,
        phases.DECLARED_NOTE.format(declared_by="CMO", display="arterial"),
        phases.UNKNOWN_NOTE.format(declared_by="CMO"), phases.NOT_CT.format(modality="MR"),
        phases.NO_NAME, phases.NOT_APPLICABLE_TEXT, vocabulary["basis"], vocabulary["rule"],
        vocabulary["scope"],
        *(phases.compare(_phase(a), _phase(b))["texto"] for a, b in (
            ("arterial", "arterial"), ("arterial", "delayed"), (None, "unknown"))),
    ]
    for text in shown:
        assert text_guard.check(text) == [], text
        lowered = text.lower()
        for word in ("realce", "realza", "capta", "hipervascular", "hipodens", "hiperdens",
                     "quiste", "metást", "benign", "malign", "tumor", "hemangioma", "lavado"):
            assert word not in lowered, text
    assert "no la propone" in phases.DECLARED_NOTE and "sin fuente" in vocabulary["basis"]
    assert [item["code"] for item in vocabulary["phases"]] == list(phases.PHASES)
    assert vocabulary["undeclared_display"] == phases.UNDECLARED_DISPLAY


# --------------------------------------------------------------------------- #
# El almacén: un asiento firmado más, y el del estudio no se toca
# --------------------------------------------------------------------------- #


def test_a_declaration_is_one_signed_entry_and_the_study_entry_is_untouched(
    client: TestClient,
) -> None:
    study = upload(client, synthetic_ct()[0])
    store = get_store()
    signed_study, size = store.volume_blob(study)[0], len(store.ledger)
    study_hash = store.ledger.entries[study].content_hash

    entry = store.record_contrast_phase(
        study, "arterial", T0, "  del informe  ", " CMO ", identity_for(CONSOLE_IDENTITY)
    )

    assert len(store.ledger) == size + 1 and entry.index == size
    assert (entry.entry_type, entry.signer) == ("volume-contrast-phase", "crew-console")
    assert entry.entry_type == VOLUME_PHASE_ENTRY_TYPE
    payload = {k: v for k, v in dict(entry.payload).items() if not k.startswith("_")}
    assert payload == {
        "subject": "crew-01", "study_index": study, "study_sha256": signed_study["sha256"],
        "phase": "arterial", "at": "2026-12-01T08:00:00+00:00", "note": "del informe",
        "declared_by": "CMO",
    }
    assert store.verify_integrity().ok
    assert store.volume_blob(study)[0] == signed_study
    assert store.ledger.entries[study].content_hash == study_hash
    [read] = store.contrast_phase_declarations("crew-01")
    assert read == {
        **payload, "ledger_index": entry.index, "recorded": entry.recorded.isoformat(),
        "signer": "crew-console",
    }
    assert store.contrast_phase_declarations("crew-02") == []
    # No es una lectura ni un indicador del catálogo: no entra en `observations`.
    assert store.query("crew-01") == []


def test_an_instant_without_time_zone_is_not_signed(client: TestClient) -> None:
    study = upload(client, synthetic_ct()[0])
    size = len(get_store().ledger)
    with pytest.raises(ValueError, match="zona horaria"):
        get_store().record_contrast_phase(
            study, "delayed", dt.datetime(2026, 12, 1, 8, 0), "", "CMO",
            identity_for(CONSOLE_IDENTITY),
        )
    assert len(get_store().ledger) == size


def test_the_store_refuses_what_cannot_be_signed(client: TestClient) -> None:
    store, console = get_store(), identity_for(CONSOLE_IDENTITY)
    study, mr = upload(client, synthetic_ct()[0]), upload_mr(client)
    store.record_resource_availability("ared", "unavailable", T0, "", "CDR", console)
    not_a_study, size = len(store.ledger) - 1, len(store.ledger)

    for phase in ("undeclared", "Arterial", ""):
        with pytest.raises(ValueError, match="fuera del vocabulario"):
            store.record_contrast_phase(study, phase, T0, "", "CMO", console)
    for nobody in ("", "  ", "123", "—"):
        with pytest.raises(ValueError, match="persona con nombre"):
            store.record_contrast_phase(study, "arterial", T0, "", nobody, console)
    with pytest.raises(ValueError, match="solo se declara en un TAC"):
        store.record_contrast_phase(mr, "arterial", T0, "", "CMO", console)
    for missing in (not_a_study, size, 999, -1):
        with pytest.raises(KeyError):
            store.record_contrast_phase(missing, "arterial", T0, "", "CMO", console)
    assert len(store.ledger) == size
    assert store.contrast_phase_declarations("crew-01") == []


def test_a_malformed_entry_is_not_delivered(client: TestClient) -> None:
    store, console = get_store(), identity_for(CONSOLE_IDENTITY)
    study = upload(client, synthetic_ct()[0])
    whole = {
        "subject": "crew-01", "study_index": study, "study_sha256": "x", "phase": "arterial",
        "at": T0.isoformat(), "note": "", "declared_by": "CMO",
    }
    assert set(_VOLUME_PHASE_FIELDS) | {"study_index"} == set(whole)
    store._record_action(VOLUME_PHASE_ENTRY_TYPE, whole, console)
    assert len(store.contrast_phase_declarations("crew-01")) == 1
    for broken in (
        {k: v for k, v in whole.items() if k != "note"},
        {k: v for k, v in whole.items() if k != "study_index"},
        {**whole, "study_index": str(study)},
        {**whole, "study_index": True},
    ):
        other = ObservationStore.in_memory()
        other._record_action(VOLUME_PHASE_ENTRY_TYPE, broken, console)
        with pytest.raises(TamperedRecordError, match="acción mal formada"):
            other.contrast_phase_declarations("crew-01")


@pytest.fixture
def pre_change(tmp_path: Path) -> Iterator[ObservationStore]:
    path = tmp_path / "emma.db"
    shutil.copyfile(PRE_CHANGE_LEDGER, path)
    store = ObservationStore.at(path)
    yield store
    store.engine.dispose()


def test_a_ledger_signed_before_the_change_still_verifies_and_accepts_a_declaration(
    pre_change: ObservationStore,
) -> None:
    """Invariante 4: el tipo de asiento es nuevo y no cambia la lectura de lo ya firmado."""
    store = pre_change
    assert store.verify_integrity().ok
    assert [entry["content_hash"] for entry in store.audit_trail()] == PRE_CHANGE_HASHES
    [ct, mr] = store.volume_studies("crew-01")
    assert (ct["ledger_index"], ct["modality"], mr["modality"]) == (0, "CT", "MR")
    [segmentation] = store.volume_segmentations(0)
    # La densidad firmada entonces lleva la fase vacía y la nota de «no declara».
    signed = segmentation["densidad"]
    assert signed["disponible"] and signed["fase_contraste"] is None
    assert geometry.PHASE_UNDECLARED in signed["notas"]
    assert store.contrast_phase_declarations("crew-01") == []
    assert len(store.resource_declarations()) == 1
    assert phases.describe([], ct, "otra-consola")["current"] is None

    # Sobre esa misma cadena, una declaración: se firma, se lee y nada de lo anterior cambia.
    console = Identity.generate("otra-consola")
    store.record_contrast_phase(0, "portal-venous", T0, "", "CMO", console)
    with pytest.raises(ValueError, match="solo se declara en un TAC"):
        store.record_contrast_phase(2, "arterial", T0, "", "CMO", console)
    assert store.verify_integrity().ok
    assert [e["content_hash"] for e in store.audit_trail()][:4] == PRE_CHANGE_HASHES
    assert store.volume_segmentations(0) == [segmentation]
    current = phases.describe(
        store.contrast_phase_declarations("crew-01"), ct, "otra-consola"
    )["current"]
    assert (current["code"], current["ledger_index"]) == ("portal-venous", 4)
    shown = _annotated(segmentation, current)
    assert shown["densidad"]["fase_contraste"] == current
    assert shown["lesiones"] == segmentation["lesiones"]


# --------------------------------------------------------------------------- #
# Las rutas
# --------------------------------------------------------------------------- #


def test_the_console_reads_the_vocabulary_from_the_backend(client: TestClient) -> None:
    body = client.get("/api/volumes/contrast-phases").json()
    assert body == phases.vocabulary()
    assert {item["display"] for item in body["phases"]} == set(phases.PHASES.values())


def test_declaring_writes_one_console_entry_and_the_latest_holds(client: TestClient) -> None:
    study = upload(client, synthetic_ct()[0])
    view = listed(client)[study]["contrast_phase"]
    assert view["applicable"] and view["current"] is None and view["history"] == []
    assert view["undeclared_display"] == "sin declarar"

    size = len(get_store().ledger)
    first = declare(client, study, "arterial", note="  según el informe  ")
    assert first.status_code == 201, first.text
    entry = get_store().ledger.entries[first.json()["ledger_index"]]
    assert (entry.entry_type, entry.signer) == ("volume-contrast-phase", "crew-console")
    assert len(get_store().ledger) == size + 1
    current = listed(client)[study]["contrast_phase"]["current"]
    assert (current["code"], current["display"], current["declared_by"], current["note"]) == (
        "arterial", "arterial", "CMO", "según el informe")
    assert current["at"] == entry.payload["at"] and current["recorded"]

    # Se corrige declarando de nuevo: vale la última y la anterior se conserva.
    second = declare(
        client, study, "unknown", declared_by="CDR", at="2026-12-02T09:00:00+01:00"
    )
    assert second.status_code == 201, second.text
    view = listed(client)[study]["contrast_phase"]
    assert (view["current"]["code"], view["current"]["display"]) == ("unknown", "no se sabe")
    assert view["current"]["at"] == "2026-12-02T09:00:00+01:00"
    assert [item["code"] for item in view["history"]] == ["arterial", "unknown"]
    assert get_store().verify_integrity().ok
    assert get_store().query("crew-01") == []


@pytest.mark.parametrize("change", [
    {"declared_by": None}, {"declared_by": ""}, {"declared_by": "   "}, {"declared_by": "123"},
    {"declared_by": "x" * 65}, {"phase": None}, {"phase": "venous"}, {"phase": "Arterial"},
    {"phase": "undeclared"}, {"phase": ""}, {"at": "2026-12-01T08:00:00"}, {"note": "x" * 501},
    {"study": 3}, {"subject": "crew-02"},
])
def test_what_cannot_be_signed_is_a_422_and_writes_nothing(
    client: TestClient, change: dict[str, Any]
) -> None:
    study = upload(client, synthetic_ct()[0])
    size = len(get_store().ledger)
    body = {"phase": "arterial", "declared_by": "CMO", **change}
    body = {key: value for key, value in body.items() if value is not None}
    response = client.post(f"/api/volumes/{study}/contrast-phase", json=body)
    assert response.status_code == 422, (change, response.text)
    assert len(get_store().ledger) == size
    assert listed(client)[study]["contrast_phase"]["current"] is None


def test_a_study_that_is_not_a_ct_is_a_422_with_its_reason(client: TestClient) -> None:
    mr = upload_mr(client)
    size = len(get_store().ledger)
    response = declare(client, mr)
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == phases.NOT_CT.format(modality="MR")
    assert len(get_store().ledger) == size
    view = listed(client)[mr]["contrast_phase"]
    assert not view["applicable"] and view["not_applicable_reason"] == response.json()["detail"]


def test_a_study_that_does_not_exist_is_a_404(client: TestClient) -> None:
    study = upload(client, synthetic_ct()[0])
    declared = declare(client, study).json()["ledger_index"]
    size = len(get_store().ledger)
    # Ni un índice sin asiento, ni un asiento que no es un estudio (la propia declaración).
    for missing in (size, 999, declared):
        assert declare(client, missing).status_code == 404, missing
    assert len(get_store().ledger) == size


def test_a_redacted_study_takes_no_more_declarations_and_shows_none(client: TestClient) -> None:
    study = upload(client, synthetic_ct()[0])
    assert declare(client, study, "arterial").status_code == 201
    get_store().redact(study, audit_identity(), "estudio de otro tripulante", "CMO")
    size = len(get_store().ledger)
    assert declare(client, study, "delayed").status_code == 404
    assert len(get_store().ledger) == size
    # Redactar el estudio redacta también su declaración: no queda nada que enseñar.
    assert listed(client) == {}
    assert get_store().contrast_phase_declarations("crew-01") == []
    assert get_store().verify_integrity().ok


# --------------------------------------------------------------------------- #
# Redactar el estudio redacta a quien declaró su fase
# --------------------------------------------------------------------------- #


def _signed_text(store: ObservationStore) -> str:
    """Todo lo que guardan la cadena en memoria y la tabla del ledger en la base."""
    from sqlalchemy import text

    with store.engine.connect() as connection:
        rows = connection.execute(text("SELECT payload FROM ledger_entries")).all()
    return str([entry.payload for entry in store.ledger.entries]) + str(rows)


def test_redacting_a_study_redacts_who_declared_its_phase_each_with_its_tombstone(
    client: TestClient,
) -> None:
    store = get_store()
    study, other = upload(client, synthetic_ct()[0]), upload(client, synthetic_ct()[0])
    first = declare(client, study, "arterial", declared_by="Dra. Ana Pérez",
                    note="del informe de Ana Pérez").json()["ledger_index"]
    second = declare(client, study, "unknown", declared_by="Dr. Luis Gil").json()["ledger_index"]
    kept = declare(client, other, "delayed", declared_by="CDR").json()["ledger_index"]
    size = len(store.ledger)
    assert "Pérez" in _signed_text(store)

    response = client.post(f"/api/audit/redact/{study}",
                           json={"reason": "estudio de otro tripulante", "requested_by": "CMO"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["redacted_index"] == study and body["chain_still_valid"]
    # Una lápida por asiento, en el mismo `commit`: la del estudio y una por declaración.
    assert len(store.ledger) == size + 3
    assert body["dependent_redactions"] == [
        {"redacted_index": first, "redaction_entry_index": size + 1},
        {"redacted_index": second, "redaction_entry_index": size + 2},
    ]
    for index in (study, first, second):
        assert store.ledger.entries[index].payload is None
    for item in body["dependent_redactions"]:
        tombstone = store.ledger.entries[item["redaction_entry_index"]].payload
        assert tombstone["target_index"] == item["redacted_index"]
        assert tombstone["requested_by"] == "CMO"
        assert tombstone["reason"] == (
            f"redactado con el estudio del asiento {study}: estudio de otro tripulante")
    # Ni el nombre de quien declaró ni su nota quedan en la cadena ni en la base.
    assert "Pérez" not in _signed_text(store) and "Luis Gil" not in _signed_text(store)
    # La del otro estudio no se toca.
    assert [item["ledger_index"] for item in store.contrast_phase_declarations("crew-01")] == [
        kept]
    assert listed(client)[other]["contrast_phase"]["current"]["code"] == "delayed"
    assert store.verify_integrity().ok


def test_redacting_a_declaration_alone_leaves_the_study(client: TestClient) -> None:
    store = get_store()
    study = upload(client, synthetic_ct()[0])
    declared = declare(client, study).json()["ledger_index"]
    redaction = store.redact(declared, audit_identity(), "nombre equivocado", "CMO")
    assert redaction.dependents == ()
    assert listed(client)[study]["contrast_phase"]["current"] is None
    assert store.verify_integrity().ok


def test_its_phases_and_segmentations_are_carried_along_and_nothing_else(
    client: TestClient, fake_segmenter: None, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """Cambiada a propósito en la duodécima ronda (decisión del usuario, 2026-10-15). Se llamaba
    `test_only_phase_declarations_of_that_study_are_carried_along` y afirmaba lo contrario: que
    la segmentación, que también cita el estudio por `study_index`, se quedaba. Ahora se redacta
    con él, porque su binario firmado lleva un volumen recortado del estudio (`record-integrity.md`
    §3.13 bis; el detalle, en `test_volume_redaction.py`). Lo demás sigue: otro tipo de asiento
    que cite el índice del estudio se queda, lo de otro estudio también, y redactar un asiento
    que no es un estudio no arrastra nada, aunque una fase escrita a mano lo cite."""
    store, console = get_store(), identity_for(CONSOLE_IDENTITY)
    segmentation = segmented(client, monkeypatch, EARLIER)
    elsewhere = segmented(client, monkeypatch, LATER)
    study = int(store.segmentation_blob(segmentation)[0]["study_index"])
    declared = declare(client, study).json()["ledger_index"]
    noted = store._record_action(IMAGING_FINDINGS_ENTRY_TYPE, {
        "subject": "crew-01", "study_index": study, "note": "escrito a mano",
    }, console).index
    redaction = store.redact(study, audit_identity(), "estudio de otro tripulante", "CMO")
    assert [item.target.index for item in redaction.dependents] == [segmentation, declared]
    assert store.ledger.entries[segmentation].payload is None
    assert store.ledger.entries[noted].payload is not None
    assert store.segmentation_blob(elsewhere)[1]

    resource = store.record_resource_availability(
        "ared", "unavailable", T0, "", "CDR", console).index
    stray = store._record_action(VOLUME_PHASE_ENTRY_TYPE, {
        "subject": "crew-01", "study_index": resource, "study_sha256": "x", "phase": "arterial",
        "at": T0.isoformat(), "note": "", "declared_by": "CMO",
    }, console).index
    assert store.redact(resource, audit_identity(), "motivo", "CMO").dependents == ()
    assert store.ledger.entries[stray].payload is not None
    assert store.verify_integrity().ok


def test_a_failed_cascade_writes_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Todo o nada: si la redacción de una declaración falla, el estudio sigue entero."""
    store = get_store()
    study = upload(client, synthetic_ct()[0])
    declared = declare(client, study).json()["ledger_index"]
    size, original = len(store.ledger), store.ledger.redact

    def broken(index: int, *args: Any) -> Any:
        if index == declared:
            raise RuntimeError("fallo a mitad")
        return original(index, *args)

    monkeypatch.setattr(store.ledger, "redact", broken)
    with pytest.raises(RuntimeError):
        store.redact(study, audit_identity(), "motivo", "CMO")
    monkeypatch.undo()
    assert len(store.ledger) == size
    assert store.ledger.entries[study].payload is not None
    assert store.volume_blob(study)[1]
    assert len(store.contrast_phase_declarations("crew-01")) == 1
    assert store.verify_integrity().ok


# Ledger escrito con el código de `main` ANTERIOR a que redactar un TAC redactara su fase
# (commit aa94f5a, `scratchpad/c3/make_pre_db.py` de la undécima ronda, unidad C3): dos TAC
# (0, 1), una fase de cada uno (2, 3) y el TAC 1 redactado (lápida 4) con su fase aún firmada.
# Claves fijas: la autoridad de redacción es la semilla 7 y la consola, la 9.
PRE_CASCADE_LEDGER = Path(__file__).parent / "data" / "volumes_pre_phase_redaction.db"
PRE_CASCADE_HASHES = [
    "f6ff6017f036bd97fbfb977766ad812ce05a9c68cbd2c746ef91995a96f35142",
    "2493407100528a3b3c8ee65de6c06be46b17fb0894e10c5da0d754e595d6d191",
    "52a0ed733839ae8f3616b1f7cc8eff7405710e0a03f9a1d6a572288770e42054",
    "60d96891f626055f854dd467de9eaea9abe46816b702d5b077446d50a62965ef",
    "d00de8ab380b8da3208c0fb3e2403a0d2d53d441eae3ddeec2ce29c68dc4f7fb",
]


def _seeded(identity_id: str, seed: int) -> Identity:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    return Identity(identity_id, Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32))


def test_a_ledger_signed_before_the_cascade_still_verifies_and_now_redacts_both(
    tmp_path: Path,
) -> None:
    from app.core.ledger import RedactionAuthority

    path = tmp_path / "emma.db"
    shutil.copyfile(PRE_CASCADE_LEDGER, path)
    authority = _seeded("emma-audit", 7)
    store = ObservationStore.at(path, RedactionAuthority.of(authority))
    try:
        assert store.verify_integrity().ok
        assert [entry["content_hash"] for entry in store.audit_trail()] == PRE_CASCADE_HASHES
        # La fase del TAC redactado antes de esta regla sigue firmada y verifica; ninguna vista
        # la enseña, porque todas parten de los estudios vigentes.
        [ct] = store.volume_studies("crew-01")
        assert ct["ledger_index"] == 0
        assert [item["study_index"] for item in store.contrast_phase_declarations("crew-01")] == [
            0, 1]

        # Ahora, redactar el TAC vigente redacta su fase.
        redaction = store.redact(0, authority, "estudio de otro tripulante", "CMO")
        assert [item.target.index for item in redaction.dependents] == [2]
        assert store.verify_integrity().ok
        assert [e["content_hash"] for e in store.audit_trail()][:5] == PRE_CASCADE_HASHES
        assert [item["ledger_index"] for item in store.contrast_phase_declarations("crew-01")] == [
            3]
        # Y la fase huérfana de antes se redacta por su índice, como cualquier asiento.
        assert store.redact(3, authority, "fase de un estudio ya redactado", "CMO").dependents == ()
        assert store.contrast_phase_declarations("crew-01") == []
        assert store.verify_integrity().ok
    finally:
        store.engine.dispose()
    # Lo escrito llega a disco: reabierta, la cadena verifica y no queda ninguna declaración.
    reopened = ObservationStore.at(path, RedactionAuthority.of(authority))
    try:
        assert reopened.verify_integrity().ok
        assert len(reopened.ledger) == len(PRE_CASCADE_HASHES) + 3
        assert reopened.contrast_phase_declarations("crew-01") == []
        assert "Pérez" not in _signed_text(reopened) and "Luis Gil" not in _signed_text(reopened)
    finally:
        reopened.engine.dispose()


def test_each_declaration_stays_with_its_study_and_its_crew_member(client: TestClient) -> None:
    mine = upload(client, synthetic_ct()[0])
    another = upload(client, synthetic_ct()[0])
    theirs = client.post(
        "/api/volumes", params={"recorded_by": "CMO", "subject": "crew-02"},
        content=nifti_bytes(synthetic_ct()[0]), headers={"Content-Type": "application/gzip"},
    ).json()["ledger_index"]
    assert declare(client, mine, "arterial").status_code == 201
    assert declare(client, theirs, "delayed").status_code == 201
    studies = listed(client)
    assert studies[mine]["contrast_phase"]["current"]["code"] == "arterial"
    assert studies[another]["contrast_phase"]["current"] is None
    assert listed(client, "crew-02")[theirs]["contrast_phase"]["current"]["code"] == "delayed"


# --------------------------------------------------------------------------- #
# De extremo a extremo, con densidad: se enseña al lado y no decide nada
# --------------------------------------------------------------------------- #


def _without_phase(density: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in density.items() if k not in ("fase_contraste", "notas")}


def test_the_listed_density_carries_the_declared_phase_and_the_same_figures(
    client: TestClient, fake_segmenter: None, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    index = segmented(client, monkeypatch, EARLIER)
    signed = get_store().segmentation_blob(index)[0]
    study = int(signed["study_index"])
    [before] = listed(client)[study]["segmentations"]
    assert before["densidad"]["fase_contraste"] is None
    assert geometry.PHASE_UNDECLARED in before["densidad"]["notas"]

    assert declare(client, study, "portal-venous").status_code == 201
    study_view = listed(client)[study]
    [after] = study_view["segmentations"]
    phase = after["densidad"]["fase_contraste"]
    assert phase == study_view["contrast_phase"]["current"]
    assert (phase["code"], phase["display"], phase["declared_by"]) == (
        "portal-venous", "portal (venosa portal)", "CMO")
    assert geometry.PHASE_UNDECLARED not in after["densidad"]["notas"]
    assert geometry.DENSITY_NOTE in after["densidad"]["notas"]
    # Ni una cifra distinta, ni una lesión con otro nombre.
    assert after["lesiones"] == before["lesiones"]
    assert all(item["estado"] == geometry.CANDIDATE for item in after["lesiones"])
    assert _without_phase(after["densidad"]) == _without_phase(before["densidad"])
    assert {k: v for k, v in after.items() if k != "densidad"} == {
        k: v for k, v in before.items() if k != "densidad"}
    # Lo firmado al segmentar sigue como estaba: la fase se pone al servir.
    assert get_store().segmentation_blob(index)[0] == signed
    assert signed["densidad"]["fase_contraste"] is None


def _evolution(body: dict[str, Any]) -> dict[str, Any]:
    """Lo que decide el estado de la evolución, y el estado."""
    return {
        "pares": body["pares"], "no_reencontradas": [
            {k: v for k, v in item.items() if k != "densidad"}
            for item in body["no_reencontradas"]],
        "lesiones": [
            {k: v for k, v in row.items() if k not in ("densidad", "previa")}
            for row in body["lesiones"]],
        "estado": body["estado"], "criterio": body["criterio"],
    }


def _stripped(body: dict[str, Any]) -> dict[str, Any]:
    """La comparación sin lo que esta pieza añade."""
    return {
        **{k: v for k, v in body.items() if k != "fase_contraste"},
        "densidad": {side: _without_phase(block) for side, block in body["densidad"].items()},
    }


def test_the_evolution_state_is_the_same_with_and_without_declared_phases(
    client: TestClient, fake_segmenter: None, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    before = segmented(client, monkeypatch, EARLIER)
    after = segmented(client, monkeypatch, LATER)
    studies = [int(get_store().segmentation_blob(i)[0]["study_index"]) for i in (before, after)]
    params = {"before": before, "after": after}

    bare = client.get("/api/volumes/compare", params=params).json()
    assert bare["fase_contraste"]["estado"] == phases.MISSING
    assert bare["fase_contraste"]["antes"] is None and bare["fase_contraste"]["despues"] is None
    states = {row["id"]: row["evolucion"]["estado"] for row in bare["lesiones"]}
    assert {"crece", "se reduce", "estable"} <= set(states.values())

    seen = []
    for first, second, expected in (
        ("arterial", None, phases.MISSING),
        ("arterial", "delayed", phases.DIFFERENT),
        ("arterial", "arterial", phases.SAME),
        ("unknown", "unknown", phases.MISSING),
    ):
        for study, phase in zip(studies, (first, second), strict=True):
            if phase is not None:
                assert declare(client, study, phase).status_code == 201
        body = client.get("/api/volumes/compare", params=params).json()
        block = body["fase_contraste"]
        seen.append(block["estado"])
        assert block["estado"] == expected, (first, second)
        assert block["antes"]["code"] == first
        assert (block["despues"] or {}).get("code") == second
        assert body["densidad"]["antes"]["fase_contraste"] == block["antes"]
        assert body["densidad"]["despues"]["fase_contraste"] == block["despues"]
        # La comparación no se bloquea y el estado de cada lesión es el de antes: lo decide el
        # diámetro. Todo lo demás, cifra por cifra, igual.
        assert _evolution(body) == _evolution(bare)
        assert {r["id"]: r["evolucion"]["estado"] for r in body["lesiones"]} == states
        assert _stripped(body) == _stripped(bare)
        # Nada resta ni califica las dos densidades, tampoco en la misma fase.
        for row in body["lesiones"]:
            assert not any("densidad" in key or "hu" in key for key in row["evolucion"])
    assert set(seen) == {phases.MISSING, phases.DIFFERENT, phases.SAME}
    assert get_store().query("crew-01") == []


def test_the_status_is_identical_with_and_without_a_declared_phase(
    client: TestClient, fake_segmenter: None, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """Invariante 5: la fase declarada no entra en el análisis ni en una alerta."""
    assert client.post(
        "/api/simulate", params={"scenario": "progressive-insomnia", "days": 40}
    ).status_code == 201
    index = segmented(client, monkeypatch, EARLIER)
    study = int(get_store().segmentation_blob(index)[0]["study_index"])
    without = client.get("/api/status", params={"until": FAR}).json()
    assert without["alerts"], "el escenario tiene que dar alertas para que la prueba diga algo"
    anatomy = client.get("/api/anatomy/state", params={"until": FAR}).json()

    for phase in ("arterial", "unknown", "non-contrast"):
        assert declare(client, study, phase).status_code == 201
    assert listed(client)[study]["contrast_phase"]["current"]["code"] == "non-contrast"

    after = client.get("/api/status", params={"until": FAR}).json()
    assert after["overall_level"] == without["overall_level"]
    assert after["domains"] == without["domains"]
    assert after["alerts"] == without["alerts"]
    assert after["rules_version"] == without["rules_version"]
    assert after == without
    assert client.get("/api/anatomy/state", params={"until": FAR}).json() == anatomy


# --------------------------------------------------------------------------- #
# La crónica: un hecho firmado, con su rótulo y sin la nota
# --------------------------------------------------------------------------- #


def _chronicle(client: TestClient, subject: str = "crew-01", **params: str) -> list[Any]:
    body = client.get("/api/timeline/chronicle", params={"subject": subject, **params}).json()
    return [event for event in body["events"] if event["tipo"] == "imagen"]


def test_the_chronicle_tells_each_declaration_with_its_label_and_without_the_note(
    client: TestClient,
) -> None:
    study = upload(client, synthetic_ct()[0])
    first = declare(client, study, "arterial", declared_by="CMO", at="2026-12-01T08:00:00+00:00",
                    note="del informe de Ana Pérez, nacida en 1980").json()["ledger_index"]
    second = declare(client, study, "unknown", declared_by="CDR",
                     at="2026-12-02T09:00:00+01:00").json()["ledger_index"]

    told = _chronicle(client)
    assert [event["clave"] for event in told] == [f"ledger:{first}", f"ledger:{second}"]
    assert {event["fact"] for event in told} == {"contrast-phase-declared"}
    assert [event["quien"] for event in told] == ["CMO", "CDR"]
    # En el instante que declara quien la firma, en el reloj de la misión.
    assert [event["at"] for event in told] == [
        "2026-12-01T08:00:00+00:00", "2026-12-02T08:00:00+00:00"]
    assert {event["time_basis"] for event in told} == {"data"}
    assert [event["que"] for event in told] == [
        f"fase de contraste del TAC del asiento {study}: «arterial» "
        f"(antes constaba «sin declarar»; {phases.DECLARED_LABEL})",
        f"fase de contraste del TAC del asiento {study}: «no se sabe» "
        f"(antes constaba «arterial»; {phases.DECLARED_LABEL})",
    ]
    # La nota es texto libre sobre el estudio: no se escribe en la crónica.
    assert "Pérez" not in str(told) and "1980" not in str(told)
    # Es del tripulante del estudio, no de toda la tripulación.
    assert _chronicle(client, "crew-02") == []
    # Tierra no ve lo firmado después de su corte.
    assert _chronicle(client, until="2020-01-01T00:00:00+00:00") == []


def test_the_chronicle_tells_only_what_the_console_would_show(client: TestClient) -> None:
    store = get_store()
    study = upload(client, synthetic_ct()[0])
    store.record_contrast_phase(study, "arterial", T0, "", "CMO", Identity.generate("otra"))
    assert _chronicle(client) == []
    declared = declare(client, study, "delayed").json()["ledger_index"]
    assert [event["clave"] for event in _chronicle(client)] == [f"ledger:{declared}"]
    # Redactar el estudio se lleva sus declaraciones también de la crónica.
    store.redact(study, audit_identity(), "estudio de otro tripulante", "CMO")
    assert _chronicle(client) == []
