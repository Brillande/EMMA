# SPDX-License-Identifier: AGPL-3.0-or-later
"""Texto de un informe clínico escaneado, sacado a bordo y sin red.

Por qué existe: la tripulación sube a bordo informes en papel o en PDF escaneado —analíticas
previas al vuelo, informes de un especialista— que son solo píxeles. Sin texto, no se pueden
leer en la consola de Tierra con el retardo, ni buscar. El OCR corre en la nave: un informe
médico no sale de ella para que lo lea un servicio en la nube.

Usa `polaris/tools/ocr_informes.py` de la copia literal de Polaris, sin modificarla (commit en
`polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the Protocol»; se
carga con `app.polaris.load`), no reescrito: `_tsv_a_texto()` —la maquetación reconstruida desde
el TSV de tesseract: líneas reales, celdas separadas por el tamaño de letra y bloques en orden— y
sus valores (`LANGS`, `DPI`, `TEXT_LAYER_MIN_CHARS`, `CONF_MINIMA`: una página por debajo de
60/100 se marca). Un PDF que ya trae texto no se OCR-iza. Lo que es de EMMA porque Polaris no lo
tiene para Windows (AGPL §5a):
  * Windows y sin dependencias de macOS: pypdfium2 (BSD-3/Apache-2.0) rasteriza el PDF en vez de
    `pdftoppm`, y Pillow abre las imágenes en vez de `sips`.
  * No escribe ficheros al lado del original: devuelve páginas con su texto y su confianza, que
    `app/api/reports.py` firma en el ledger junto al original.

QUÉ NO HACE. No interpreta el texto ni lo pasa al análisis ni al borrador del modelo de lenguaje:
es texto libre de un tercero, y en el borrador sería la puerta de una inyección. Tampoco
des-identifica: un informe lleva nombres, y se guarda tal cual, en local, redactable.
"""

from __future__ import annotations

import io
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from app import polaris


def _original() -> Any:
    """`tools/ocr_informes.py` de Polaris, de la copia literal (`polaris/`)."""
    return polaris.load("ocr_informes")


# Los valores de Polaris, leídos de la copia: castellano con siglas en inglés, 300 ppp, un PDF con
# al menos 120 caracteres de texto real no está escaneado, y por debajo de 60/100 tesseract está
# adivinando y la página se marca.
LANGUAGES = str(_original().LANGS)
DPI = int(_original().DPI)
TEXT_LAYER_MIN_CHARS = int(_original().TEXT_LAYER_MIN_CHARS)
MIN_CONFIDENCE = float(_original().CONF_MINIMA)
MAX_PAGES = 30
# Píxeles de una página ya pintada, y de todas juntas. El cuerpo está acotado en bytes, pero un PDF
# declara el tamaño de su página (`MediaBox`) y un TIFF cuántos fotogramas trae: unos kilobytes
# pedían gigas al pintarlos (auditoría run-2, `emma:reports:pdf-render-unbounded-page-size` y
# `emma:reports:tiff-frames-before-max-pages`). Un A3 a 300 ppp son 17,4 millones.
MAX_PAGE_PIXELS = 20_000_000
MAX_TOTAL_PIXELS = 200_000_000


class PageTooLarge(ValueError):
    """Una página, o todas juntas, pasan del tope de píxeles."""


def _budget(width: float, height: float, spent: int) -> int:
    """Los píxeles gastados tras esta página; `PageTooLarge` si pasa de un tope."""
    pixels = int(width) * int(height)
    if pixels > MAX_PAGE_PIXELS:
        raise PageTooLarge(
            f"una página de {int(width)} × {int(height)} píxeles pasa del tope de {MAX_PAGE_PIXELS}"
        )
    if spent + pixels > MAX_TOTAL_PIXELS:
        raise PageTooLarge(f"las páginas juntas pasan del tope de {MAX_TOTAL_PIXELS} píxeles")
    return spent + pixels

WINDOWS_DEFAULT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")

MEDIA_TYPES = {
    "application/pdf": "pdf",
    "image/png": "image",
    "image/jpeg": "image",
    "image/tiff": "image",
}


class OcrUnavailable(RuntimeError):
    """No hay tesseract en esta máquina, o no respondió."""


@dataclass(frozen=True)
class PageText:
    page: int
    text: str
    confidence: float | None  # None: texto de la capa del PDF, no de OCR
    words: int

    @property
    def low_confidence(self) -> bool:
        return self.confidence is not None and self.confidence < MIN_CONFIDENCE

    def as_payload(self) -> dict[str, object]:
        return {
            "page": self.page,
            "text": self.text,
            "confidence": self.confidence,
            "words": self.words,
            "low_confidence": self.low_confidence,
        }


def find_tesseract(configured: str | None = None) -> str | None:
    """El ejecutable de tesseract: el configurado, el del PATH o el de la instalación típica."""
    for candidate in (configured, shutil.which("tesseract"), str(WINDOWS_DEFAULT)):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def version(executable: str) -> str:
    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OcrUnavailable(f"tesseract no responde: {exc}") from exc
    first = (result.stdout or result.stderr or "").splitlines()
    return first[0].strip() if first else "tesseract"


def page_images(data: bytes, media_type: str) -> list[Image.Image]:
    """Las páginas como imágenes, a 300 ppp si son de un PDF."""
    kind = MEDIA_TYPES.get(media_type)
    spent = 0
    if kind == "image":
        image = Image.open(io.BytesIO(data))
        frames = []
        # Solo las primeras `MAX_PAGES`: antes se convertían todos y luego se cortaba la lista.
        for index in range(min(getattr(image, "n_frames", 1), MAX_PAGES)):
            image.seek(index)
            spent = _budget(*image.size, spent)
            frames.append(image.convert("RGB"))
        return frames
    if kind == "pdf":
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(data)
        pages = []
        for index in range(min(len(document), MAX_PAGES)):
            page = document[index]
            width, height = page.get_size()  # en puntos: 72 por pulgada
            spent = _budget(width * DPI / 72, height * DPI / 72, spent)
            pages.append(page.render(scale=DPI / 72).to_pil().convert("RGB"))
        return pages
    raise ValueError(f"tipo no admitido: {media_type!r}")


def text_layer(data: bytes) -> list[str] | None:
    """El texto que ya trae un PDF, página a página; None si parece escaneado."""
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(data)
    pages = [
        document[index].get_textpage().get_text_range()
        for index in range(min(len(document), MAX_PAGES))
    ]
    real = sum(len(page.strip()) for page in pages)
    return pages if real >= TEXT_LAYER_MIN_CHARS else None


def tsv_to_text(tsv: str) -> tuple[str, float, int]:
    """TSV de tesseract -> (texto con la maquetación, confianza media 0-100, palabras).

    Es `_tsv_a_texto()` de Polaris, llamado en la copia literal: se agrupa por línea real
    (bloque/párrafo/línea) y se ordena por posición; un hueco horizontal de más de 1,5 veces la
    altura de letra es una celda, no un espacio, y se marca con «  ·  »; entre bloques, una línea
    en blanco.
    """
    text, confidence, words = _original()._tsv_a_texto(tsv)
    return str(text), float(confidence), int(words)


def ocr_image(executable: str, image: Image.Image) -> tuple[str, float, int]:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    try:
        result = subprocess.run(
            [executable, "stdin", "stdout", "-l", LANGUAGES, "tsv"],
            input=buffer.getvalue(),
            capture_output=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OcrUnavailable(f"tesseract no responde: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()[:200]
        raise OcrUnavailable(f"tesseract falló: {detail}")
    return tsv_to_text(result.stdout.decode("utf-8", "replace"))


def read(data: bytes, media_type: str, executable: str | None) -> list[PageText]:
    """Texto de cada página. Un PDF con capa de texto no pasa por OCR."""
    if MEDIA_TYPES.get(media_type) == "pdf":
        layer = text_layer(data)
        if layer is not None:
            return [
                PageText(n + 1, text.strip(), None, len(text.split()))
                for n, text in enumerate(layer)
            ]
    if executable is None:
        raise OcrUnavailable("no hay tesseract instalado en esta máquina")
    pages = []
    for number, image in enumerate(page_images(data, media_type), start=1):
        text, confidence, words = ocr_image(executable, image)
        pages.append(PageText(number, text, confidence, words))
    return pages
