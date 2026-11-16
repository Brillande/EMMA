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

# LO QUE SE CONSERVA, no lo que se quita (2026-11-16). Hasta entonces se borraba una lista de
# atributos de la tabla E.1-1 de PS3.15, y todo lo que no estuviera en ella pasaba: otros campos de
# la tabla, nombres y texto libre dentro de `ContentSequence`, comentarios de superposición (60xx),
# UID no listados y el título AE de la cabecera de fichero, bajo un sello «PS3.15 Basic Profile»
# (auditoría run-2, `emma:imaging:deid-profile-incomplete`). Ahora en la raíz solo queda lo que EMMA
# necesita para mostrar, medir y fechar la imagen; todo lo demás se quita, sea cual sea su nombre.
_KEPT = frozenset(
    {
        # Identidad del objeto (los UID de instancia se sustituyen abajo) y su clase.
        "SOPClassUID", "SOPInstanceUID", "StudyInstanceUID", "SeriesInstanceUID",
        "FrameOfReferenceUID", "SpecificCharacterSet", "ImageType", "Modality", "SeriesNumber",
        "InstanceNumber", "PatientOrientation", "Laterality", "ImageLaterality",
        # Tiempo: la opción de retener fechas completas (código DCM 113106).
        "AcquisitionDateTime", "AcquisitionDate", "AcquisitionTime", "ContentDate", "ContentTime",
        "StudyDate", "StudyTime", "SeriesDate", "SeriesTime", "TimezoneOffsetFromUTC",
        # Módulo de píxel y su presentación.
        "Rows", "Columns", "NumberOfFrames", "SamplesPerPixel", "PhotometricInterpretation",
        "PlanarConfiguration", "BitsAllocated", "BitsStored", "HighBit", "PixelRepresentation",
        "PixelData", "PixelAspectRatio", "PixelSpacing", "SmallestImagePixelValue",
        "LargestImagePixelValue", "WindowCenter", "WindowWidth", "RescaleSlope",
        "RescaleIntercept", "RedPaletteColorLookupTableDescriptor",
        "GreenPaletteColorLookupTableDescriptor", "BluePaletteColorLookupTableDescriptor",
        "RedPaletteColorLookupTableData", "GreenPaletteColorLookupTableData",
        "BluePaletteColorLookupTableData", "LossyImageCompression", "LossyImageCompressionRatio",
        "LossyImageCompressionMethod",
        # Cine.
        "FrameTime", "FrameTimeVector", "FrameIncrementPointer", "CineRate",
        "RecommendedDisplayFrameRate", "ActualFrameDuration", "StartTrim", "StopTrim",
        "PreferredPlaybackSequencing", "FrameDelay",
        # Ecografía: la calibración, y lo que el equipo declara de texto quemado.
        "SequenceOfUltrasoundRegions", "BurnedInAnnotation", "RecognizableVisualFeatures",
        # Volumen de ecografía (Enhanced US Volume) y referencias entre imágenes.
        "SharedFunctionalGroupsSequence", "PerFrameFunctionalGroupsSequence",
        "DimensionOrganizationSequence", "DimensionIndexSequence", "DimensionOrganizationType",
        "ReferencedImageSequence", "SourceImageSequence",
    }
)
# Dentro de una secuencia conservada no se mira el nombre (hay cientos posibles), sino la clase de
# valor: lo que puede llevar un nombre o texto libre se quita. Quedan números, códigos, fechas,
# UID (sustituidos) y secuencias, que se recorren con la misma regla.
_TEXT_VRS = frozenset({"PN", "LO", "LT", "SH", "ST", "UT", "UC", "UR", "AE", "AS", "OB", "UN"})
# Raíz de los UID del propio estándar (clases SOP, sintaxis de transferencia, esquemas de códigos):
# no son del paciente y se quedan. Todo otro UID se sustituye, coherente dentro del fichero.
_STANDARD_UID_ROOT = "1.2.840.10008."

# PS3.3 C.8.5.5.1: RegionSpatialFormat 1 = imagen 2D; unidad física 3 = centímetros.
_SPATIAL_2D = 1
_CENTIMETRES = 3


# Topes de lo que la imagen ocupa ya descodificada. El cuerpo de la petición está acotado
# (`MAX_IMAGING_BYTES`), pero un RLE de 838 bytes puede declarar 65 535 × 65 535 píxeles y
# pydicom reserva el fotograma entero al descodificarlo (auditoría run-2,
# `emma:imaging:rle-frame-preallocation-unbounded-dims`). Una ecografía real ronda
# 1024 × 768 × 3 (2,4 MB por fotograma); un cine largo, unos cientos de fotogramas.
MAX_FRAME_BYTES = 64 * 1024 * 1024
MAX_STUDY_PIXEL_BYTES = 1024 * 1024 * 1024
# Deflated Explicit VR Little Endian: el conjunto entero va comprimido con zlib y pydicom lo
# infla sin tope al leerlo (`emma:imaging:dicom-deflate-unbounded`). Ningún ecógrafo lo usa
# para exportar imagen; se rechaza antes de inflar nada.
DEFLATED_TRANSFER_SYNTAX = "1.2.840.10008.1.2.1.99"


class NotUltrasoundError(ValueError):
    """El fichero no es un DICOM de ecografía que EMMA sepa guardar."""


class PixelBudgetError(ValueError):
    """La imagen declarada, descodificada, no cabe en los topes."""


def pixel_bytes(ds: Dataset) -> tuple[int, int]:
    """(bytes de un fotograma, bytes del estudio) descodificados, según lo que declara la cabecera.

    Lanza `PixelBudgetError` si superan `MAX_FRAME_BYTES` o `MAX_STUDY_PIXEL_BYTES`, y
    `ValueError` si las dimensiones no son números.
    """
    rows, columns = int(ds.get("Rows", 0) or 0), int(ds.get("Columns", 0) or 0)
    samples = int(ds.get("SamplesPerPixel", 1) or 1)
    bits = int(ds.get("BitsAllocated", 8) or 8)
    frames = int(ds.get("NumberOfFrames", 1) or 1)
    frame = rows * columns * samples * math.ceil(bits / 8)
    total = frame * frames
    if frame > MAX_FRAME_BYTES:
        raise PixelBudgetError(
            f"un fotograma de {rows} × {columns} ocuparía {frame} bytes descodificado: el tope es "
            f"{MAX_FRAME_BYTES}"
        )
    if total > MAX_STUDY_PIXEL_BYTES:
        raise PixelBudgetError(
            f"{frames} fotogramas ocuparían {total} bytes descodificados: el tope es "
            f"{MAX_STUDY_PIXEL_BYTES}"
        )
    return frame, total


def _refuse_deflated(raw: bytes) -> None:
    """Mira la sintaxis de transferencia en la cabecera de fichero, sin leer el conjunto."""
    fp = io.BytesIO(raw)
    try:
        pydicom.filereader.read_preamble(fp, False)
        meta = pydicom.filereader._read_file_meta_info(fp)
    except (InvalidDicomError, EOFError, ValueError, TypeError, OSError, KeyError) as exc:
        raise NotUltrasoundError(f"no es un fichero DICOM legible: {exc}") from exc
    if str(meta.get("TransferSyntaxUID", "")) == DEFLATED_TRANSFER_SYNTAX:
        raise NotUltrasoundError(
            "sintaxis de transferencia «deflated» no admitida: el conjunto va comprimido entero"
        )


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
    _refuse_deflated(raw)
    try:
        ds = pydicom.dcmread(io.BytesIO(raw))
    except (InvalidDicomError, EOFError, ValueError, TypeError, OSError, MemoryError) as exc:
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
    try:
        pixel_bytes(ds)
    except (PixelBudgetError, ValueError, TypeError) as exc:
        raise NotUltrasoundError(str(exc)) from exc

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
    """Deja solo `_KEPT` en la raíz y, dentro, lo que no es texto. Devuelve cuántos quitó.

    Una secuencia quitada cuenta una vez, no una por cada elemento suyo.
    """
    removed = 0
    for elem in list(ds):
        keep = elem.keyword in _KEPT and not elem.tag.is_private
        if not keep:
            del ds[elem.tag]
            removed += 1
    pending = [
        item for elem in ds if elem.VR == "SQ" for item in elem.value if isinstance(item, Dataset)
    ]
    while pending:
        current = pending.pop()
        for elem in list(current):
            if elem.tag.is_private or elem.VR in _TEXT_VRS or _overlay_or_curve(elem.tag.group):
                del current[elem.tag]
                removed += 1
            elif elem.VR == "SQ":
                pending.extend(item for item in elem.value if isinstance(item, Dataset))

    replaced: dict[str, str] = {}

    def _new(original: str) -> str:
        if not original or original.startswith(_STANDARD_UID_ROOT):
            return original
        return replaced.setdefault(original, generate_uid())

    for container in list(_datasets(ds)):
        for elem in container:
            if elem.VR != "UI":
                continue
            if isinstance(elem.value, str):
                elem.value = _new(elem.value)
            elif elem.value:
                elem.value = [_new(str(item)) for item in elem.value]

    # La cabecera de fichero, rehecha: sin el título AE de origen ni nada más que lo que la
    # describe; pydicom repone al escribir la versión e identidad de la implementación.
    meta = ds.file_meta
    kept_meta = {
        "MediaStorageSOPClassUID", "MediaStorageSOPInstanceUID", "TransferSyntaxUID",
        "FileMetaInformationVersion",
    }
    for elem in list(meta):
        if elem.keyword not in kept_meta:
            del meta[elem.tag]
    if "SOPInstanceUID" in ds:
        meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID

    ds.PatientIdentityRemoved = "YES"
    ds.DeidentificationMethod = "PS3.15 Basic Profile; Retain Longitudinal Full Dates (EMMA)"
    ds.DeidentificationMethodCodeSequence = DicomSequence(
        [_code("113100", "Basic Application Confidentiality Profile"),
         _code("113106", "Retain Longitudinal Temporal Information Full Dates Option")]
    )
    return removed


def _overlay_or_curve(group: int) -> bool:
    """Grupos 50xx (curvas) y 60xx (superposiciones): llevan texto y no tienen nombre fijo."""
    return 0x5000 <= group <= 0x50FF or 0x6000 <= group <= 0x60FF


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
