"""Un fotograma de un estudio, como PNG que cualquier navegador sabe mostrar.

Por qué en el backend y no en la interfaz: descodificar DICOM en el navegador exige
descodificadores en WebAssembly y trabajadores, y abrir la política de seguridad de la
interfaz para ellos. Aquí basta con pydicom y Pillow, y la interfaz solo recibe una imagen.
El PNG sale siempre de un binario cuyo hash se acaba de comprobar (`imaging_blob()`): lo que
se ve es lo que está firmado.

Lo que no se hace: ajustar brillo, contraste o ganancia. La imagen se muestra con la escala
de grises que la adquirió el ecógrafo; realzarla aquí cambiaría lo que el operador mide.
"""

from __future__ import annotations

import io

import numpy as np
import pydicom
from PIL import Image
from pydicom.pixels.utils import pixel_array


class UnrenderableError(ValueError):
    """El fotograma no se puede mostrar. El mensaje dice por qué."""


def frame_png(data: bytes, index: int) -> bytes:
    """El fotograma `index` como PNG de 8 bits, en gris o en color."""
    dataset = pydicom.dcmread(io.BytesIO(data))
    frames = int(dataset.get("NumberOfFrames", 1) or 1)
    if not 0 <= index < frames:
        raise IndexError(f"el estudio tiene {frames} fotogramas; no existe el {index}")
    try:
        # Un solo fotograma: descodificar un cine entero para mostrar uno sería lento.
        pixels = pixel_array(dataset, index=index if frames > 1 else None)
    except (NotImplementedError, RuntimeError, ValueError) as exc:
        syntax = dataset.file_meta.get("TransferSyntaxUID", "desconocida")
        raise UnrenderableError(
            f"no se puede descodificar la compresión del estudio ({syntax}): {exc}"
        ) from exc

    photometric = str(dataset.get("PhotometricInterpretation", ""))
    image = _to_8_bit(np.asarray(pixels), int(dataset.get("BitsStored", 8) or 8))
    if photometric == "MONOCHROME1":  # blanco = mínimo: se invierte para verlo como es
        image = 255 - image
    if image.ndim == 2:
        picture = Image.fromarray(image, mode="L")
    elif image.ndim == 3 and image.shape[2] == 3:
        # pydicom devuelve RGB también para YBR: la conversión de color la hace él.
        picture = Image.fromarray(image, mode="RGB")
    else:
        raise UnrenderableError(f"forma de píxel no admitida: {image.shape}")

    buffer = io.BytesIO()
    picture.save(buffer, format="PNG")
    return buffer.getvalue()


def _to_8_bit(pixels: np.ndarray, bits_stored: int) -> np.ndarray:
    """A 8 bits por escala fija, no por el mínimo y máximo del fotograma.

    Estirar cada fotograma a su propio rango haría que el mismo tejido se viera más claro
    o más oscuro de un fotograma a otro, y un cine parpadearía.
    """
    if pixels.dtype == np.uint8:
        return pixels
    values = pixels.astype(np.int64)
    if bits_stored > 8:
        values = values >> (bits_stored - 8)
    clipped: np.ndarray = np.clip(values, 0, 255).astype(np.uint8)
    return clipped
