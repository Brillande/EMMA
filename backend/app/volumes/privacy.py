# SPDX-License-Identifier: AGPL-3.0-or-later
"""Un volumen NIfTI no entra si su cabecera puede llevar datos personales.

Por qué existe: un NIfTI no es solo vóxeles. Su cabecera tiene campos de texto libre (`descrip`,
`aux_file`, `intent_name`, `db_name`) y admite extensiones, y los conversores de DICOM meten ahí
desde el protocolo hasta la cabecera DICOM entera, con nombre y fecha de nacimiento. EMMA firma
el volumen en el ledger tal como llega: lo que entre con un nombre dentro queda firmado con él, y
un registro firmado no se corrige, se redacta. La comprobación va antes de guardar.

Usa tal cual `verifica_sin_pii` y `_trozos_pii` de Polaris (`polaris/tools/visor3d.py`; el commit,
en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the Protocol»;
se cargan con `app.polaris.load`). Polaris la corre sobre el NIfTI que ella misma acaba de
limpiar, como red de seguridad antes de sacarlo a Colab; EMMA la corre sobre lo que sube el
operador, como puerta de entrada. Lo que pone EMMA alrededor, sin tocar la copia:
  * La función pide una ruta: los bytes recibidos se escriben en una carpeta temporal.
  * Aborta con `SystemExit`: aquí se recoge y se convierte en un motivo. Su mensaje nombra el
    campo, nunca el valor; aun así se comprueba que no repite la identidad antes de devolverlo.
  * Los valores a buscar salen en Polaris de la serie DICOM; aquí, de la identidad que el
    tripulante declaró en el ledger (`crew-identity`, como en `reports/identity.py`). Sin
    identidad declarada se comprueba igual lo estructural: texto y extensiones.
  * No se le redirige la consola: la función no escribe en ella. Si un día lo hiciera, se captura
    con `app.polaris.console.captured()`, el cerrojo único de consola, no con un
    `redirect_stdout` propio: la consola es de todo el proceso y dos capturas con cerrojos
    distintos se cruzan (pasaba entre `export.py`, `kb.py` y `volumes/spine.py`).

Tres reglas de EMMA encima, porque como puerta de entrada de ficheros ajenos el original se queda
corto en tres sitios (medido; `docs/polaris-divergencias.md`):
  * **El hueco entre la cabecera y los vóxeles.** El original lee `vox_offset` bytes, pero de una
    cabecera cargada con nibabel, que pone ese campo a cero: solo mira los 352 primeros. En sus
    propios ficheros no hay más; en uno ajeno puede haber un hueco con lo que sea. Aquí se lee el
    `vox_offset` del fichero y, si hay algo que no sea ceros en ese hueco, no entra.
  * **Tildes, eñes y mayúsculas.** El original compara en minúsculas ASCII y en UTF-8: «MUÑOZ» en
    mayúsculas, o en Latin-1 (lo habitual en DICOM), no lo encuentra. Aquí se busca además cada
    trozo en mayúsculas, sin tildes y en las dos codificaciones.
  * **El envoltorio gzip.** `gzip fichero.nii` guarda dentro el nombre que tenía el fichero, y los
    ficheros de un paciente suelen llamarse como él. Va fuera del NIfTI, así que el original no lo
    ve (ella escribe los suyos con nombre fijo); EMMA firma el `.gz` entero. Con nombre,
    comentario o campo extra en el envoltorio, no entra.

No se limpia en silencio: sin pedirlo, lo guardado es lo que el operador subió, con su huella, y
el motivo dice cómo limpiarlo fuera y volver a subirlo.

**Limpiar aquí, si el operador lo pide (2026-10-07).** La puerta rechaza también un `descrip`
técnico inocuo de un conversor de DICOM, y la puerta no se ablanda: no hay lista de textos
permitidos. Lo que se ofrece es vaciar la cabecera dentro de EMMA (`clean`), solo con la petición
explícita del operador. Se hace con `nifti_limpio` de Polaris —la misma función con la que ella
escribe los suyos—, llamada con los vóxeles tal como están en el fichero y su afín; devuelve una
cabecera nueva, sin texto ni extensiones. Reglas de EMMA alrededor, porque `nifti_limpio` se
escribió para volúmenes que ella misma calcula y aquí hay que devolver EL MISMO estudio:
  * **La geometría y la escala del original se reponen** (`CONSERVED`): `nifti_limpio` pone
    `sform` y `qform` al mismo afín con código 1 y deja `pixdim`, las unidades y `scl_slope`/
    `scl_inter` de fábrica; con eso un TAC guardado en crudo perdería sus HU y un volumen con
    `qform` propio, su orientación. Solo se reponen campos numéricos; ninguno de texto.
  * **El fichero se escribe aquí**, cabecera y vóxeles seguidos: nibabel, al guardar, recalcula
    la escala. Así tampoco queda hueco tras la cabecera ni nada detrás de los vóxeles, y el gzip
    sale sin nombre, comentario ni fecha.
  * **Se comprueba antes de devolverlo**: los vóxeles escritos son, bit a bit, los recibidos, y
    cada campo conservado vale lo mismo. Si no, no hay limpieza.
  * **Vuelve a pasar la misma puerta** (`ensure_clean`), con la misma identidad. Si un valor del
    tripulante siguiera en un campo numérico conservado, no entra.
De lo que se vació solo salen de aquí NOMBRES de campo: nunca su contenido.

Qué NO mira ni limpia: los vóxeles. Un nombre quemado en la imagen, o una cara reconstruible de
un TAC de cabeza, pasan esta puerta (`compliance/risk-management-file.md`, H18).
"""

from __future__ import annotations

import gzip
import io
import logging
import struct
import tempfile
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from app import polaris
from app.reports.identity import Declared

log = logging.getLogger(__name__)
# NIfTI-1: 348 bytes de cabecera y 4 de marca de extensiones; `vox_offset` es un float32 en el 108.
HEADER_BYTES = 352
_VOX_OFFSET_AT = 108

GZIP_MAGIC = b"\x1f\x8b"
# gzip (RFC 1952): el cuarto byte son las banderas. Estas tres marcan texto que el compresor
# guarda junto a los datos.
_GZIP_KEEPS = {
    0x08: "el nombre original del fichero",
    0x10: "un comentario",
    0x04: "un campo extra",
}

HOW_TO_CLEAN = (
    "No se ha guardado nada. Vuelve a exportarlo solo con los vóxeles y el afín (sin texto en la "
    "cabecera ni extensiones) y súbelo de nuevo; si va comprimido, que el gzip no guarde el nombre "
    "del fichero (`gzip -n`), o súbelo sin comprimir."
)
IDENTITY_FOUND = (
    "la cabecera del NIfTI contiene un valor identificativo del tripulante (no se muestra cuál)"
)
# Lo que la interfaz enseña junto al rechazo cuando limpiar aquí serviría. Lo redacta el backend.
CLEAN_LABEL = "Limpiar la cabecera y volver a comprobar"
CLEAN_OFFER = (
    "EMMA puede vaciar la cabecera por ti y volver a comprobar el volumen. Se guardaría el "
    "volumen limpio, no el fichero que has subido, y el registro firmado diría que se limpió, qué "
    "campos se vaciaron y la huella de los dos. Los vóxeles, la geometría y la escala no cambian. "
    "No se mira ni se limpia lo que esté escrito dentro de la propia imagen."
)
CLEANED_NOTE = (
    "Cabecera limpiada en EMMA a petición de quien lo registró: lo guardado no es el fichero "
    "recibido. Vóxeles, geometría y escala son los recibidos. No se miró ni se limpió lo que esté "
    "escrito dentro de la propia imagen."
)
STILL_FOUND = "Sigue sin poder guardarse después de limpiar la cabecera"

# Campos de la cabecera NIfTI-1 que la limpieza deja como estaban en el fichero recibido: lo que
# dice dónde está cada vóxel y qué vale. Todos numéricos. Lo demás queda como lo deja
# `nifti_limpio` (vacío o de fábrica) y se declara por su nombre.
CONSERVED = (
    "dim", "datatype", "bitpix", "pixdim", "xyzt_units", "scl_slope", "scl_inter",
    "qform_code", "sform_code", "quatern_b", "quatern_c", "quatern_d",
    "qoffset_x", "qoffset_y", "qoffset_z", "srow_x", "srow_y", "srow_z",
    "dim_info", "intent_code", "intent_p1", "intent_p2", "intent_p3",
    "slice_start", "slice_end", "slice_code", "slice_duration", "toffset", "cal_max", "cal_min",
)
# Lo que la limpieza quita y no es un campo de la cabecera, con el nombre con que se declara.
EXTENSIONS = "extensiones"
GAP = "hueco entre la cabecera y los vóxeles"
TRAILING = "datos detrás de los vóxeles"
GZIP_WRAPPER = "envoltorio gzip"

# Año, mes y día en los tres órdenes y con los separadores habituales; sin separador y con el año
# delante es la forma de DICOM (`PatientBirthDate`).
_DATE_ORDERS = ("%Y{0}%m{0}%d", "%d{0}%m{0}%Y", "%m{0}%d{0}%Y")
_DATE_SEPARATORS = ("", "-", "/", ".")


class PersonalDataFound(Exception):
    """La cabecera lleva, o puede llevar, datos personales. El mensaje dice dónde, no cuáles."""


class CheckUnavailable(Exception):
    """La comprobación no pudo ejecutarse. Sin ella no se guarda (fallo cerrado)."""


@dataclass(frozen=True)
class Cleaned:
    """Un volumen ya limpio y ya pasado por la puerta. `fields` son nombres, nunca contenido."""

    data: bytes
    fields: tuple[str, ...]


@cache
def _tool() -> Any:
    return polaris.load("visor3d")


def _identity_values(declared: Declared | None) -> list[str]:
    """Lo que se busca en la cabecera, en la forma de `_trozos_pii` (trozos de 4 o más letras).

    La fecha de nacimiento va en las formas en que se escribe, con el año en cuatro cifras.
    """
    if declared is None:
        return []
    dates = {
        declared.birth_date.strftime(order.format(separator))
        for order in _DATE_ORDERS
        for separator in _DATE_SEPARATORS
    }
    values = [declared.given_name, declared.surnames, *sorted(dates)]
    return [str(chunk) for chunk in _tool()._trozos_pii(values)]


def _reason(exit_code: object, searched: list[str]) -> str:
    """El motivo de Polaris sin su prefijo. Si repitiera un valor buscado, no se devuelve."""
    text = str(exit_code or "").removeprefix("ABORTA:").strip()
    if "valor identificativo" in text:
        # Polaris dice "de la serie": la DICOM de la que ella saca los valores. Aquí salen de la
        # identidad declarada, y el operador no tiene ninguna serie delante.
        return IDENTITY_FOUND
    lowered = text.lower()
    if not text or any(value.lower() in lowered for value in searched):
        return "la cabecera del NIfTI lleva datos que pueden ser personales"
    return text


def _before_voxels(raw: bytes) -> bytes:
    """Los bytes del fichero hasta donde empiezan los vóxeles, según el `vox_offset` del fichero."""
    if raw[:2] == GZIP_MAGIC:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            head = stream.read(HEADER_BYTES)
            order = "<" if head[:4] == struct.pack("<i", 348) else ">"
            (offset,) = struct.unpack_from(f"{order}f", head, _VOX_OFFSET_AT)
            return head + stream.read(max(0, int(offset) - HEADER_BYTES))
    order = "<" if raw[:4] == struct.pack("<i", 348) else ">"
    (offset,) = struct.unpack_from(f"{order}f", raw, _VOX_OFFSET_AT)
    return raw[: max(HEADER_BYTES, int(offset))]


def _spellings(chunk: str) -> set[bytes]:
    """Un trozo de la identidad como puede venir escrito: con o sin tildes, UTF-8 o Latin-1."""
    plain = "".join(
        char for char in unicodedata.normalize("NFD", chunk) if not unicodedata.combining(char)
    )
    found = set()
    for form in (chunk.lower(), chunk.upper(), plain.lower()):
        for encoding in ("utf-8", "latin-1"):
            found.add(form.encode(encoding, "ignore").lower())
    return {needle for needle in found if len(needle) >= 4}


def _emma_rules(raw: bytes, searched: list[str]) -> None:
    """Lo que el original no ve en un fichero ajeno: el envoltorio, el hueco y las tildes."""
    if raw[:2] == GZIP_MAGIC:
        kept = [what for flag, what in _GZIP_KEEPS.items() if raw[3] & flag]
        if kept:
            raise PersonalDataFound("el envoltorio gzip guarda " + " y ".join(kept))
    region = _before_voxels(raw)
    if region[HEADER_BYTES:].strip(b"\x00"):
        raise PersonalDataFound("el NIfTI lleva datos entre la cabecera y los vóxeles")
    lowered = region.lower()
    if any(needle in lowered for chunk in searched for needle in _spellings(chunk)):
        raise PersonalDataFound(IDENTITY_FOUND)


def ensure_clean(raw: bytes, declared: Declared | None) -> None:
    """Pasa en silencio si la cabecera está limpia; si no, dice por qué no se guarda."""
    try:
        tool = _tool()
        searched = _identity_values(declared)
        suffix = ".nii.gz" if raw[:2] == GZIP_MAGIC else ".nii"
        with tempfile.TemporaryDirectory(prefix="emma_pii_") as folder:
            path = Path(folder) / f"volumen{suffix}"
            path.write_bytes(raw)
            try:
                clean = tool.verifica_sin_pii(str(path), searched)
            except SystemExit as stop:
                raise PersonalDataFound(_reason(stop.code, searched)) from None
        if clean is not True:
            raise CheckUnavailable("la comprobación de Polaris no dio el volumen por limpio")
        _emma_rules(raw, searched)
    except (PersonalDataFound, CheckUnavailable):
        raise
    except Exception as exc:
        # Solo el tipo: el texto de un error de lectura podría arrastrar bytes de la cabecera.
        log.warning("comprobación de datos personales fallida: %s", type(exc).__name__)
        raise CheckUnavailable(
            f"la comprobación de datos personales no pudo ejecutarse ({type(exc).__name__})"
        ) from None


def _same(left: Any, right: Any) -> bool:
    """Dos valores de un campo de cabecera, iguales. El texto, sin su relleno de ceros."""
    import numpy as np

    a, b = np.asarray(left), np.asarray(right)
    if a.dtype.kind in "SV" or b.dtype.kind in "SV":
        return bool(a.tobytes().rstrip(b"\x00") == b.tobytes().rstrip(b"\x00"))
    return bool(np.array_equal(a, b, equal_nan=a.dtype.kind in "fc"))


def _rebuilt(raw: bytes) -> Cleaned:
    """El mismo estudio con la cabecera que deja `nifti_limpio`, y los nombres de lo que cambió."""
    import nibabel as nib
    import numpy as np

    zipped = raw[:2] == GZIP_MAGIC
    plain = gzip.decompress(raw) if zipped else raw
    # La cabecera, del fichero: la de una imagen cargada con nibabel ya trae `vox_offset` y la
    # escala a su valor de fábrica.
    reader: Any = nib.Nifti1Header
    received = reader.from_fileobj(io.BytesIO(plain))
    image: Any = nib.Nifti1Image.from_bytes(plain)
    voxels = np.asanyarray(image.dataobj.get_unscaled())
    emptied = _tool().nifti_limpio(voxels, image.affine, voxels.dtype)
    header = emptied.header
    for name in CONSERVED:
        header[name] = received[name]
    header["vox_offset"] = HEADER_BYTES
    stored = np.asanyarray(emptied.dataobj)
    stored = stored.astype(stored.dtype.newbyteorder(header.endianness), copy=False)
    body = stored.tobytes(order="F")
    # Bit a bit contra los bytes recibidos, no contra lo que nibabel interpreta de ellos. Con el
    # orden de bytes cambiado (un fichero big-endian) se comparan los mismos valores, uno a uno.
    start = int(image.dataobj.offset)
    was = plain[start : start + len(body)]
    if received.endianness != header.endianness:
        was = np.frombuffer(was, voxels.dtype).astype(stored.dtype).tobytes()
    if was != body or not all(_same(header[name], received[name]) for name in CONSERVED):
        raise CheckUnavailable("la limpieza habría cambiado la imagen, y no se hace")

    fields = [
        name for name in received.structarr.dtype.names
        if name != "vox_offset" and not _same(header[name], received[name])
    ]
    extensions = image.header.extensions
    if len(extensions):
        fields.append(EXTENSIONS)
    declared_end = HEADER_BYTES + sum(int(item.get_sizeondisk()) for item in extensions)
    if plain[declared_end:start].strip(b"\x00"):
        fields.append(GAP)
    if len(plain) > start + len(body):
        fields.append(TRAILING)
    if zipped and any(raw[3] & flag for flag in _GZIP_KEEPS):
        fields.append(GZIP_WRAPPER)
    clean = header.binaryblock + b"\x00\x00\x00\x00" + body
    # `mtime=0`: el gzip no guarda ni nombre ni comentario, y así tampoco la hora de la limpieza.
    return Cleaned(gzip.compress(clean, mtime=0) if zipped else clean, tuple(fields))


def clean(raw: bytes, declared: Declared | None) -> Cleaned:
    """El volumen con la cabecera vaciada, SOLO si después pasa la misma puerta que el original.

    Quien llama decide si limpiar (lo pide el operador, nunca EMMA por su cuenta); aquí se
    garantiza que lo que se devuelve ya está comprobado. `PersonalDataFound` si ni limpio pasa;
    `CheckUnavailable` si no se pudo limpiar o comprobar.
    """
    try:
        cleaned = _rebuilt(raw)
    except CheckUnavailable:
        raise
    except Exception as exc:
        # Solo el tipo, como en `ensure_clean`: el texto del error podría arrastrar la cabecera.
        log.warning("limpieza de la cabecera fallida: %s", type(exc).__name__)
        raise CheckUnavailable(f"la cabecera no se pudo limpiar ({type(exc).__name__})") from None
    ensure_clean(cleaned.data, declared)
    return cleaned
