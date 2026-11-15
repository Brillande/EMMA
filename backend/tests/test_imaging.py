"""Ecografía: des-identificación, calibración y paso por el ledger.

Los DICOM de estas pruebas se construyen aquí, en memoria: no hay ficheros de pacientes en
el repositorio ni se descarga nada (invariante 3). Llevan a propósito lo que un ecógrafo
real exporta y no debe guardarse —nombre, fecha de nacimiento, centro, una etiqueta privada
del fabricante y un nombre escondido en una secuencia anidada—.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
from collections.abc import Iterator
from pathlib import Path

import pydicom
import pytest
from fastapi.testclient import TestClient
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence as DicomSequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.core.ledger import Identity, RedactionAuthority
from app.core.storage import ImagingBlobRow, ObservationStore, TamperedRecordError
from app.imaging.dicom import NotUltrasoundError, read_ultrasound
from app.ingest.fhir import observation
from app.main import app

US_IMAGE = "1.2.840.10008.5.1.4.1.1.6.1"
ORIGINAL_STUDY_UID = generate_uid()
AUDITOR = Identity.generate("emma-audit")


def _region(units: int = 3, delta_cm: float = 0.01) -> Dataset:
    region = Dataset()
    region.RegionSpatialFormat = 1
    region.RegionDataType = 1
    region.RegionFlags = 0
    region.RegionLocationMinX0, region.RegionLocationMinY0 = 0, 0
    region.RegionLocationMaxX1, region.RegionLocationMaxY1 = 15, 15
    region.PhysicalUnitsXDirection = units
    region.PhysicalUnitsYDirection = units
    region.PhysicalDeltaX = delta_cm
    region.PhysicalDeltaY = -delta_cm  # el signo es el sentido del eje, no la escala
    return region


def ultrasound_dicom(
    *,
    modality: str = "US",
    acquisition: str | None = "20261114083000+0100",
    regions: list[Dataset] | None = None,
    pixels: bool = True,
) -> bytes:
    """Un DICOM de ecografía mínimo, con PII dentro para comprobar que sale."""
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = US_IMAGE
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = Dataset()
    ds.file_meta = meta
    ds.SOPClassUID = US_IMAGE
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = ORIGINAL_STUDY_UID
    ds.SeriesInstanceUID = generate_uid()
    ds.Modality = modality
    ds.PatientName = "Doe^Jane"
    ds.PatientID = "HOSP-123456"
    ds.PatientBirthDate = "19850301"
    ds.InstitutionName = "Johnson Space Center"
    ds.OperatorsName = "Smith^John"
    referenced = Dataset()
    referenced.PatientName = "Escondido^EnSecuencia"
    ds.ReferencedImageSequence = DicomSequence([referenced])
    ds.add_new(0x00091010, "LO", "numero de serie del fabricante")
    if acquisition is not None:
        ds.AcquisitionDateTime = acquisition
    ds.BurnedInAnnotation = "NO"
    ds.SequenceOfUltrasoundRegions = DicomSequence(
        regions if regions is not None else [_region()]
    )
    ds.Rows, ds.Columns = 16, 16
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated, ds.BitsStored, ds.HighBit = 8, 8, 7
    ds.PixelRepresentation = 0
    if pixels:
        ds.PixelData = bytes(range(256))

    buffer = io.BytesIO()
    pydicom.dcmwrite(buffer, ds, enforce_file_format=True)
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# Lectura y des-identificación
# --------------------------------------------------------------------------- #


def test_identifying_data_does_not_survive_ingestion() -> None:
    study = read_ultrasound(ultrasound_dicom())
    stored = pydicom.dcmread(io.BytesIO(study.data))

    for keyword in ("PatientName", "PatientID", "PatientBirthDate", "InstitutionName",
                    "OperatorsName"):
        assert keyword not in stored, keyword
    assert "PatientName" not in stored.ReferencedImageSequence[0]
    assert not any(elem.tag.is_private for elem in stored)
    assert b"Doe^Jane" not in study.data and b"Escondido" not in study.data
    assert b"HOSP-123456" not in study.data and b"fabricante" not in study.data
    # Un UID de estudio puede enlazar con el sistema del hospital: se sustituye.
    assert stored.StudyInstanceUID != ORIGINAL_STUDY_UID
    assert stored.file_meta.MediaStorageSOPInstanceUID == stored.SOPInstanceUID
    assert stored.PatientIdentityRemoved == "YES"
    codes = {item.CodeValue for item in stored.DeidentificationMethodCodeSequence}
    assert codes == {"113100", "113106"}
    assert study.removed_elements >= 7


def test_nested_instance_uids_and_the_rest_of_table_e1_1_do_not_survive() -> None:
    """El fichero se rotula «PS3.15 Basic Profile» (DCM 113100): tiene que serlo también dentro.

    Solo se sustituían los cuatro UID de la raíz, así que el `ReferencedSOPInstanceUID` de una
    imagen previa del mismo PACS, el `InstanceCreatorUID` o el operador identificado en su
    secuencia llegaban al ledger tal cual. La sustitución es coherente: una referencia a la
    propia instancia sigue apuntando a ella.
    """
    original = pydicom.dcmread(io.BytesIO(ultrasound_dicom()))
    own_uid = str(original.SOPInstanceUID)
    prior_uid, creator_uid = generate_uid(), generate_uid()
    prior, itself = Dataset(), Dataset()
    prior.ReferencedSOPClassUID, prior.ReferencedSOPInstanceUID = US_IMAGE, prior_uid
    itself.ReferencedSOPClassUID, itself.ReferencedSOPInstanceUID = US_IMAGE, own_uid
    original.SourceImageSequence = DicomSequence([prior, itself])
    original.InstanceCreatorUID = creator_uid
    operator = Dataset()
    operator.PersonIdentificationCodeSequence = DicomSequence()
    operator.InstitutionName = "Johnson Space Center"
    original.OperatorIdentificationSequence = DicomSequence([operator])
    original.RequestedProcedureDescription = "Eco orbitaria de Jane Doe"
    original.AcquisitionComments = "paciente HOSP-123456"
    buffer = io.BytesIO()
    pydicom.dcmwrite(buffer, original, enforce_file_format=True)

    study = read_ultrasound(buffer.getvalue())
    stored = pydicom.dcmread(io.BytesIO(study.data))

    for uid in (prior_uid, creator_uid, own_uid):
        assert uid.encode() not in study.data, uid
    for keyword in ("OperatorIdentificationSequence", "RequestedProcedureDescription",
                    "AcquisitionComments"):
        assert keyword not in stored, keyword
    assert b"HOSP-123456" not in study.data and b"Jane Doe" not in study.data
    # Coherente: la referencia a sí misma lleva el UID nuevo de la instancia; la clase se queda.
    assert stored.SourceImageSequence[1].ReferencedSOPInstanceUID == stored.SOPInstanceUID
    assert stored.SourceImageSequence[0].ReferencedSOPClassUID == US_IMAGE


def test_a_removed_sequence_counts_once_not_once_per_nested_element() -> None:
    """`removed_elements` va al ledger: dice cuánto se quitó del fichero guardado.

    El recorrido tomaba antes una foto de todos los anidados y, quitada una secuencia, seguía
    quitando (y contando) lo que había dentro de sus elementos, que ya no estaban en el fichero.
    """
    base = read_ultrasound(ultrasound_dicom()).removed_elements
    original = pydicom.dcmread(io.BytesIO(ultrasound_dicom()))
    operator = Dataset()
    operator.InstitutionName = "Johnson Space Center"
    operator.InstitutionAddress = "2101 E NASA Pkwy"
    original.OperatorIdentificationSequence = DicomSequence([operator])
    buffer = io.BytesIO()
    pydicom.dcmwrite(buffer, original, enforce_file_format=True)

    assert read_ultrasound(buffer.getvalue()).removed_elements == base + 1


def test_every_deidentified_keyword_is_a_dicom_keyword() -> None:
    """Un nombre mal escrito en las listas no quitaría nada, y nadie lo notaría."""
    from pydicom.datadict import tag_for_keyword

    from app.imaging.dicom import _REMOVED, _REPLACED_UIDS

    assert [k for k in (*_REMOVED, *_REPLACED_UIDS) if tag_for_keyword(k) is None] == []


def test_the_image_itself_is_kept_intact() -> None:
    stored = pydicom.dcmread(io.BytesIO(read_ultrasound(ultrasound_dicom()).data))
    assert stored.PixelData == bytes(range(256))


def test_calibration_is_read_in_millimetres() -> None:
    study = read_ultrasound(ultrasound_dicom())
    assert len(study.regions) == 1
    region = study.regions[0]
    assert region.mm_per_px_x == pytest.approx(0.1)
    # El signo negativo de PhysicalDeltaY es orientación: la escala es positiva.
    assert region.mm_per_px_y == pytest.approx(0.1)


def test_regions_that_do_not_measure_distance_are_not_calibration() -> None:
    doppler = _region(units=4)  # segundos: un Doppler espectral
    broken = _region(delta_cm=0.0)
    study = read_ultrasound(ultrasound_dicom(regions=[doppler, broken]))
    assert study.regions == ()


def test_without_calibration_the_study_is_stored_but_declared_uncalibrated() -> None:
    study = read_ultrasound(ultrasound_dicom(regions=[]))
    assert study.regions == ()


def test_acquisition_time_is_converted_to_utc() -> None:
    study = read_ultrasound(ultrasound_dicom())
    assert study.acquired == dt.datetime(2026, 11, 14, 7, 30, tzinfo=dt.UTC)


def test_a_local_time_without_zone_is_not_guessed() -> None:
    study = read_ultrasound(ultrasound_dicom(acquisition="20261114083000"))
    assert study.acquired is None


@pytest.mark.parametrize(
    "raw",
    [
        ultrasound_dicom(modality="CT"),
        ultrasound_dicom(pixels=False),
        b"no soy un dicom",
        b"",
    ],
)
def test_only_ultrasound_images_are_accepted(raw: bytes) -> None:
    with pytest.raises(NotUltrasoundError):
        read_ultrasound(raw)


# --------------------------------------------------------------------------- #
# Almacén: el binario queda cubierto por la firma
# --------------------------------------------------------------------------- #


def _payload(data: bytes, subject: str = "crew-01") -> dict[str, object]:
    study = read_ultrasound(data)
    return {
        "subject": subject,
        "protocol": "optic-nerve",
        "acquired": "2026-11-14T07:30:00+00:00",
        "source": "ultrasound",
        "sha256": study.sha256,
        "size_bytes": len(study.data),
    }


@pytest.fixture
def file_store(tmp_path: Path) -> tuple[ObservationStore, bytes]:
    store = ObservationStore.at(tmp_path / "emma.db", RedactionAuthority.of(AUDITOR))
    study = read_ultrasound(ultrasound_dicom())
    payload = _payload(ultrasound_dicom())
    payload["sha256"], payload["size_bytes"] = study.sha256, len(study.data)
    store.record_imaging_study(payload, study.data, Identity.generate("ultrasound"))
    return store, study.data


def test_a_study_round_trips_through_the_ledger(
    file_store: tuple[ObservationStore, bytes],
) -> None:
    store, data = file_store
    [listed] = store.imaging_studies("crew-01")
    assert listed["protocol"] == "optic-nerve"
    assert "_salt" not in listed
    payload, served = store.imaging_blob(listed["ledger_index"])
    assert served == data and payload["sha256"] == listed["sha256"]
    assert store.verify_integrity().ok
    assert store.imaging_studies("crew-02") == []


def test_a_hash_that_is_not_of_these_bytes_is_refused() -> None:
    store = ObservationStore.in_memory()
    payload = _payload(ultrasound_dicom())
    with pytest.raises(ValueError, match="sha256"):
        store.record_imaging_study(payload, b"otros bytes", Identity.generate("ultrasound"))
    assert len(store.ledger) == 0


def test_an_image_edited_on_disk_is_detected_and_never_served(
    file_store: tuple[ObservationStore, bytes],
) -> None:
    store, data = file_store
    with Session(store.engine) as session:
        session.execute(update(ImagingBlobRow).values(data=data[:-1] + b"\x00"))
        session.commit()
    result = store.verify_integrity()
    assert not result.ok and result.failed_index == 0
    with pytest.raises(TamperedRecordError):
        store.imaging_blob(0)


def test_rewriting_the_hash_column_along_with_the_image_is_detected(
    file_store: tuple[ObservationStore, bytes],
) -> None:
    store, _ = file_store
    forged = b"imagen falsificada"
    with Session(store.engine) as session:
        session.execute(
            update(ImagingBlobRow).values(data=forged, sha256=hashlib.sha256(forged).hexdigest())
        )
        session.commit()
    assert not store.verify_integrity().ok


def test_a_deleted_image_is_detected(file_store: tuple[ObservationStore, bytes]) -> None:
    store, _ = file_store
    with Session(store.engine) as session:
        session.execute(delete(ImagingBlobRow))
        session.commit()
    result = store.verify_integrity()
    assert not result.ok and result.failed_index == 0


def test_redacting_a_study_deletes_the_image(
    file_store: tuple[ObservationStore, bytes],
) -> None:
    store, _ = file_store
    store.redact(0, AUDITOR, "estudio de otro tripulante", "medico de a bordo")
    assert store.imaging_studies("crew-01") == []
    with Session(store.engine) as session:
        assert session.get(ImagingBlobRow, 0) is None
    with pytest.raises(KeyError):
        store.imaging_blob(0)
    assert store.verify_integrity().ok


def test_a_study_cannot_be_amended_into_a_reading(
    file_store: tuple[ObservationStore, bytes],
) -> None:
    store, _ = file_store
    reading = observation(
        "heart-rate", 60.0, dt.datetime(2026, 11, 14, tzinfo=dt.UTC), "crew-01", "t"
    )
    with pytest.raises(ValueError, match="estudio de imagen"):
        store.amend(0, reading, Identity.generate("wearable"), "corrección")


def test_a_study_counts_as_a_real_record(file_store: tuple[ObservationStore, bytes]) -> None:
    """Si no contara, cambiar de escenario simulado borraría la ecografía sin avisar."""
    store, _ = file_store
    assert "ultrasound" in store.reading_signers()


def test_studies_survive_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "emma.db"
    store = ObservationStore.at(path, RedactionAuthority.of(AUDITOR))
    study = read_ultrasound(ultrasound_dicom())
    payload = _payload(ultrasound_dicom())
    payload["sha256"], payload["size_bytes"] = study.sha256, len(study.data)
    store.record_imaging_study(payload, study.data, Identity.generate("ultrasound"))

    reopened = ObservationStore.at(path, RedactionAuthority.of(AUDITOR))
    assert reopened.verify_integrity().ok
    assert reopened.imaging_blob(0)[1] == study.data


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _upload(client: TestClient, raw: bytes, **params: str) -> object:
    return client.post(
        "/api/imaging/studies",
        params={"protocol": "optic-nerve", **params},
        content=raw,
        headers={"content-type": "application/dicom"},
    )


def test_upload_list_and_download(client: TestClient) -> None:
    response = _upload(client, ultrasound_dicom())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["calibrated"] is True and body["burned_in_annotation"] == "NO"

    [study] = client.get("/api/imaging/studies").json()
    assert study["acquired"] == "2026-11-14T07:30:00+00:00"
    assert study["calibration"][0]["mm_per_px_x"] == pytest.approx(0.1)

    download = client.get(f"/api/imaging/studies/{study['ledger_index']}/dicom")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/dicom"
    assert b"Doe^Jane" not in download.content
    assert download.headers["x-content-sha256"] == study["sha256"]


def test_the_zone_is_asked_for_when_the_dicom_does_not_fix_it(client: TestClient) -> None:
    raw = ultrasound_dicom(acquisition="20261114083000")
    assert _upload(client, raw).status_code == 422
    accepted = _upload(client, raw, acquired="2026-11-14T08:30:00+01:00")
    assert accepted.status_code == 201
    [study] = client.get("/api/imaging/studies").json()
    assert study["acquired"] == "2026-11-14T07:30:00+00:00"


@pytest.mark.parametrize(
    ("raw", "params"),
    [
        (ultrasound_dicom(), {"protocol": "inventado"}),
        (ultrasound_dicom(modality="CT"), {}),
        (b"no soy un dicom", {}),
        (ultrasound_dicom(acquisition=None), {"acquired": "2026-11-14T08:30:00"}),
    ],
)
def test_bad_uploads_are_rejected_without_writing(
    client: TestClient, raw: bytes, params: dict[str, str]
) -> None:
    assert _upload(client, raw, **params).status_code == 422
    assert client.get("/api/imaging/studies").json() == []


def test_a_study_is_not_lost_by_switching_scenario(client: TestClient) -> None:
    assert _upload(client, ultrasound_dicom()).status_code == 201
    response = client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 2, "replace": "true"}
    )
    assert response.status_code == 409
    assert len(client.get("/api/imaging/studies").json()) == 1


def test_unknown_or_non_image_entries_are_404(client: TestClient) -> None:
    assert client.get("/api/imaging/studies/0/dicom").status_code == 404
    client.post(
        "/api/observations",
        json={"key": "heart-rate", "value": 60, "subject": "crew-01", "source": "manual"},
    )
    assert client.get("/api/imaging/studies/0/dicom").status_code == 404


def test_protocols_declare_why_they_exist(client: TestClient) -> None:
    protocols = client.get("/api/imaging/protocols").json()["protocols"]
    assert {p["key"] for p in protocols} >= {"optic-nerve", "jugular-vein", "bladder"}
    assert all(p["rationale"] for p in protocols)
