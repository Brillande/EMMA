"""Lectura de estudios ecográficos DICOM, des-identificados antes de guardarse.

Por qué existe: un ecógrafo exporta DICOM, y un DICOM trae mucho más que la imagen —nombre,
fecha de nacimiento, centro, operador, números de serie— y a veces lo esconde en secuencias
anidadas o en etiquetas privadas del fabricante. Lo que entra en el ledger no se puede
borrar sin dejar lápida, así que lo identificativo tiene que quitarse **antes**.

Y trae algo que sí hace falta y que es fácil perder: la calibración física. Sin ella, una
distancia en píxeles no es una distancia; medir la vaina del nervio óptico con una escala
supuesta daría milímetros falsos con apariencia de medida. Aquí se lee la calibración que
declara el propio equipo y, si no la declara, se registra que no la hay. No se inventa.

Des-identificación: perfil básico de confidencialidad de DICOM PS3.15 (anexo E) con la opción
de conservar la información temporal longitudinal con fechas completas (código DCM 113106).
Se conservan las fechas porque la tendencia sobre la línea base es justo lo que se busca; el
tripulante va seudonimizado por el `subject` de EMMA, no por su nombre.

Límite que se declara, no se oculta: los datos **quemados en los píxeles** (texto dibujado
en la imagen por el ecógrafo) no se pueden quitar leyendo cabeceras. Se registra lo que el
equipo declara en `BurnedInAnnotation` para que la interfaz lo advierta.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import math
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pydicom
from pydicom.dataelem import DataElement
from pydicom.dataset import Dataset
from pydicom.errors import InvalidDicomError
from pydicom.sequence import Sequence as DicomSequence
from pydicom.uid import generate_uid
from pydicom.valuerep import DA, DT, TM

# Clases SOP de ecografía (PS3.4 anexo B.5): imagen, multiframe (cine) y volumen 3D.
ULTRASOUND_SOP_CLASSES = frozenset(
    {
        "1.2.840.10008.5.1.4.1.1.6.1",  # Ultrasound Image Storage
        "1.2.840.10008.5.1.4.1.1.3.1",  # Ultrasound Multi-frame Image Storage
        "1.2.840.10008.5.1.4.1.1.6.2",  # Enhanced US Volume Storage
    }
)

# Atributos que el perfil básico de PS3.15 (tabla E.1-1) quita o vacía y que aparecen en
# ecografía. Se buscan a cualquier profundidad, no solo en el nivel raíz.
_REMOVED = frozenset(
    {
        "AccessionNumber", "AdditionalPatientHistory", "AdmissionID",
        "AdmittingDiagnosesDescription",
        "ContentCreatorName", "DerivationDescription", "DeviceSerialNumber", "EthnicGroup",
        "FrameComments", "ImageComments", "InstitutionAddress", "InstitutionName",
        "InstitutionalDepartmentName", "IssuerOfPatientID", "MedicalRecordLocator",
        "MilitaryRank", "NameOfPhysiciansReadingStudy", "Occupation", "OperatorsName",
        "OtherPatientIDs", "OtherPatientIDsSequence", "OtherPatientNames", "PatientAddress",
        "PatientAge", "PatientBirthDate", "PatientBirthName", "PatientBirthTime",
        "PatientComments", "PatientID", "PatientMotherBirthName", "PatientName",
        "PatientSex", "PatientSize", "PatientTelephoneNumbers", "PatientWeight",
        "PerformedProcedureStepDescription", "PerformedProcedureStepID",
        "PerformingPhysicianName", "PhysiciansOfRecord", "ProtocolName",
        "ReferencedPatientSequence", "ReferringPhysicianAddress", "ReferringPhysicianName",
        "ReferringPhysicianTelephoneNumbers", "RequestAttributesSequence",
        "RequestingPhysician", "ResponsiblePerson", "ScheduledProcedureStepID",
        "SeriesDescription", "StationName", "StudyDescription", "StudyID",
        # También de la tabla E.1-1 y posibles en un DICOM de ecografía; faltaban, y el fichero
        # se rotulaba «PS3.15 Basic Profile» (código DCM 113100) llevándolos dentro.
        "AcquisitionComments", "Allergies", "CountryOfResidence", "CurrentPatientLocation",
        "ImagingServiceRequestComments", "InstitutionCodeSequence", "MedicalAlerts",
        "OperatorIdentificationSequence", "OrderCallbackPhoneNumber", "OrderEnteredBy",
        "OrderEntererLocation", "PatientInsurancePlanCodeSequence",
        "PatientReligiousPreference", "PatientState", "PerformedLocation",
        "PerformedStationName", "PerformingPhysicianIdentificationSequence",
        "PhysiciansOfRecordIdentificationSequence",
        "PhysiciansReadingStudyIdentificationSequence", "ReasonForTheRequestedProcedure",
        "ReferringPhysicianIdentificationSequence", "RegionOfResidence",
        "RequestedProcedureComments", "RequestedProcedureDescription", "RequestedProcedureID",
        "ScheduledPerformingPhysicianName", "ScheduledProcedureStepLocation", "SpecialNeeds",
        "StudyComments", "VisitComments",
        "AcquisitionDeviceProcessingDescription", "ConsultingPhysicianName",
        "PerformedStationAETitle", "ReasonForStudy", "RequestingService",
        "ScheduledProcedureStepDescription", "ScheduledStationAETitle", "ScheduledStationName",
        "VerifyingObserverName",
    }
)

# UIDs de instancia que el perfil sustituye (acción U de la tabla E.1-1), a cualquier
# profundidad: un UID de estudio enlaza con el sistema del hospital, y el mismo UID repetido en
# una secuencia de referencias (`ReferencedSOPInstanceUID` de una imagen previa del mismo PACS)
# enlaza igual. Hasta 2026-11-11 solo se cambiaban los cuatro de la raíz. La sustitución es
# coherente dentro del fichero: el mismo UID original recibe el mismo nuevo en todas partes, así
# que una referencia interna sigue apuntando a lo mismo. Los UID de CLASE (`SOPClassUID`,
# `ReferencedSOPClassUID`) son del estándar, no del paciente, y se quedan.
_REPLACED_UIDS = frozenset(
    {
        "StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID", "FrameOfReferenceUID",
        "ReferencedSOPInstanceUID", "ReferencedFrameOfReferenceUID",
        "RelatedFrameOfReferenceUID", "InstanceCreatorUID", "ConcatenationUID",
        "DimensionOrganizationUID", "IrradiationEventUID",
        "SynchronizationFrameOfReferenceUID", "StorageMediaFileSetUID", "DeviceUID",
        "UID", "ReferencedSOPInstanceUIDInFile", "FiducialUID", "TargetUID",
        "ObservationUID", "TrackingUID", "SpecimenUID", "TransactionUID",
        "PaletteColorLookupTableUID",
    }
)

# PS3.3 C.8.5.5.1: RegionSpatialFormat 1 = imagen 2D; unidad física 3 = centímetros.
_SPATIAL_2D = 1
_CENTIMETRES = 3


class NotUltrasoundError(ValueError):
    """El fichero no es un DICOM de ecografía que EMMA sepa guardar."""


@dataclass(frozen=True)
class CalibratedRegion:
    """Zona de la imagen con escala física declarada por el ecógrafo.

    Una imagen puede tener varias (p. ej. modo B y un Doppler al lado), cada una con su
    escala. Una medida solo vale si sus dos puntos caen en la misma región.
    """

    x0: int
    y0: int
    x1: int
    y1: int
    mm_per_px_x: float
    mm_per_px_y: float

    def as_payload(self) -> dict[str, Any]:
        return {
            "x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1,
            "mm_per_px_x": self.mm_per_px_x, "mm_per_px_y": self.mm_per_px_y,
        }


@dataclass(frozen=True)
class UltrasoundStudy:
    """Un estudio ya des-identificado: los bytes que se guardan y lo que se sabe de ellos."""

    data: bytes
    sha256: str
    acquired: dt.datetime | None
    frames: int
    rows: int
    columns: int
    regions: tuple[CalibratedRegion, ...]
    # "YES", "NO" o "" si el equipo no lo declara.
    burned_in_annotation: str
    removed_elements: int


def read_ultrasound(raw: bytes) -> UltrasoundStudy:
    """Valida, des-identifica y describe un DICOM de ecografía."""
    try:
        ds = pydicom.dcmread(io.BytesIO(raw))
    except (InvalidDicomError, EOFError, ValueError, TypeError, OSError) as exc:
        raise NotUltrasoundError(f"no es un fichero DICOM legible: {exc}") from exc

    sop_class = str(ds.get("SOPClassUID", ""))
    if ds.get("Modality") != "US" or sop_class not in ULTRASOUND_SOP_CLASSES:
        raise NotUltrasoundError(
            f"no es una ecografía (modalidad {ds.get('Modality')!r}, clase SOP {sop_class!r})"
        )
    if "PixelData" not in ds:
        raise NotUltrasoundError("el DICOM no contiene imagen")
    rows, columns = _positive_int(ds, "Rows"), _positive_int(ds, "Columns")
    frames = _positive_int(ds, "NumberOfFrames") if "NumberOfFrames" in ds else 1

    acquired = _acquisition_time(ds)
    regions = _calibrated_regions(ds)
    burned_in = str(ds.get("BurnedInAnnotation", "")).upper()
    removed = _deidentify(ds)

    buffer = io.BytesIO()
    pydicom.dcmwrite(buffer, ds, enforce_file_format=True)
    data = buffer.getvalue()
    return UltrasoundStudy(
        data=data,
        sha256=hashlib.sha256(data).hexdigest(),
        acquired=acquired,
        frames=frames,
        rows=rows,
        columns=columns,
        regions=regions,
        burned_in_annotation=burned_in if burned_in in {"YES", "NO"} else "",
        removed_elements=removed,
    )


def _positive_int(ds: Dataset, keyword: str) -> int:
    try:
        value = int(ds.get(keyword))
    except (TypeError, ValueError) as exc:
        raise NotUltrasoundError(f"{keyword} ausente o no numérico") from exc
    if value <= 0:
        raise NotUltrasoundError(f"{keyword} tiene que ser positivo")
    return value


def _acquisition_time(ds: Dataset) -> dt.datetime | None:
    """Instante de adquisición con zona horaria, o `None` si el DICOM no la fija.

    DICOM guarda la hora local sin zona salvo que declare `TimezoneOffsetFromUTC`, o que
    `AcquisitionDateTime` lleve el desfase. Adivinar la zona desplazaría la lectura horas
    en la tendencia, así que sin zona se devuelve `None` y quien importa tiene que darla.
    """
    offset = _utc_offset(ds.get("TimezoneOffsetFromUTC"))
    raw_dt = ds.get("AcquisitionDateTime")
    if raw_dt:
        try:
            moment = DT(str(raw_dt))
        except ValueError:
            moment = None
        if moment is not None:
            if moment.tzinfo is not None:
                return moment.astimezone(dt.UTC)
            if offset is not None:
                return moment.replace(tzinfo=offset).astimezone(dt.UTC)
    for date_kw, time_kw in (("ContentDate", "ContentTime"), ("StudyDate", "StudyTime")):
        if offset is None or not ds.get(date_kw) or not ds.get(time_kw):
            continue
        try:
            day, clock = DA(str(ds.get(date_kw))), TM(str(ds.get(time_kw)))
        except ValueError:
            continue
        if day is None or clock is None:
            continue
        return dt.datetime.combine(day, clock, tzinfo=offset).astimezone(dt.UTC)
    return None


def _utc_offset(raw: Any) -> dt.timezone | None:
    """`+HHMM` / `-HHMM` (PS3.3 C.12.1.1.8)."""
    text = str(raw or "")
    if len(text) != 5 or text[0] not in "+-" or not text[1:].isdigit():
        return None
    hours, minutes = int(text[1:3]), int(text[3:])
    if hours > 14 or minutes > 59:
        return None
    sign = 1 if text[0] == "+" else -1
    return dt.timezone(sign * dt.timedelta(hours=hours, minutes=minutes))


def _calibrated_regions(ds: Dataset) -> tuple[CalibratedRegion, ...]:
    """Regiones 2D con escala en centímetros, pasadas a mm/píxel.

    Una región con otra unidad (segundos, hercios: un Doppler espectral) no mide distancias
    y se omite. Una región con escala imposible —cero, negativa, no finita— también: medir
    con ella daría un número sin significado.
    """
    found: list[CalibratedRegion] = []
    for item in ds.get("SequenceOfUltrasoundRegions", []) or []:
        try:
            if int(item.get("RegionSpatialFormat", -1)) != _SPATIAL_2D:
                continue
            if int(item.get("PhysicalUnitsXDirection", -1)) != _CENTIMETRES:
                continue
            if int(item.get("PhysicalUnitsYDirection", -1)) != _CENTIMETRES:
                continue
            dx, dy = float(item.PhysicalDeltaX), float(item.PhysicalDeltaY)
            x0, y0, x1, y1 = (int(item.get(k)) for k in (
                "RegionLocationMinX0", "RegionLocationMinY0",
                "RegionLocationMaxX1", "RegionLocationMaxY1",
            ))
        except (AttributeError, TypeError, ValueError):
            continue
        # El signo de PhysicalDeltaY indica el sentido del eje; la distancia usa su valor
        # absoluto.
        dx, dy = abs(dx), abs(dy)
        if not (math.isfinite(dx) and math.isfinite(dy)) or dx == 0 or dy == 0:
            continue
        if x0 > x1 or y0 > y1:
            continue
        found.append(CalibratedRegion(x0, y0, x1, y1, dx * 10.0, dy * 10.0))
    return tuple(found)


def _deidentify(ds: Dataset) -> int:
    """Aplica el perfil básico con retención temporal. Devuelve cuántos elementos quitó."""
    removed = 0
    # Sin `list()`: el recorrido es perezoso y baja a un anidado después de que su padre pasó
    # por aquí, así que los elementos de una secuencia ya quitada no se cuentan otra vez.
    for container in _datasets(ds):
        for keyword in _REMOVED:
            if keyword in container:
                del container[keyword]
                removed += 1
    private = sum(1 for container in _datasets(ds) for elem in container if elem.tag.is_private)
    ds.remove_private_tags()  # recorre también las secuencias anidadas
    removed += private

    replaced: dict[str, str] = {}

    def _new(original: str) -> str:
        return replaced.setdefault(original, generate_uid())

    for container in list(_datasets(ds)):
        for keyword in _REPLACED_UIDS:
            if keyword not in container:
                continue
            value = container[keyword].value
            if isinstance(value, str):  # `UID` es un `str`
                setattr(container, keyword, _new(str(value)) if value else value)
            elif value:  # multivalor
                setattr(container, keyword, [_new(str(item)) for item in value])
    if "SOPInstanceUID" in ds:
        ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID

    ds.PatientIdentityRemoved = "YES"
    ds.DeidentificationMethod = "PS3.15 Basic Profile; Retain Longitudinal Full Dates (EMMA)"
    ds.DeidentificationMethodCodeSequence = DicomSequence(
        [_code("113100", "Basic Application Confidentiality Profile"),
         _code("113106", "Retain Longitudinal Temporal Information Full Dates Option")]
    )
    return removed


def _datasets(ds: Dataset) -> Iterator[Dataset]:
    """El dataset y todos los anidados en sus secuencias, sin recursión de Python."""
    pending = [ds]
    while pending:
        current = pending.pop()
        yield current
        for elem in current:
            if isinstance(elem, DataElement) and elem.VR == "SQ":
                pending.extend(item for item in elem.value if isinstance(item, Dataset))


def _code(value: str, meaning: str) -> Dataset:
    item = Dataset()
    item.CodeValue = value
    item.CodingSchemeDesignator = "DCM"
    item.CodeMeaning = meaning
    return item
