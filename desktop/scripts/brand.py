# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regenera los PNG, la hoja de contactos, los logotipos y `build/icon.ico` desde los SVG.

Por qué existe: el icono del instalador era el de Electron por defecto, y un .ico es un binario
que nadie puede revisar. Aquí la fuente de verdad son los SVG escritos a mano de
`build/brand/`; todo lo demás sale de ellos con este guion, en local (Chromium de Playwright
para rasterizar, Pillow para leer los PNG), sin conversores en línea. Cada tamaño del .ico se
rasteriza aparte —no se reduce el de 1024—, y el de 16 px sale de su SVG dibujado píxel a píxel
cuando existe (`emma-mark-<x>-16.svg`).

No es una dependencia de EMMA: se corre con un entorno desechable (ver `build/brand/README.md`).

    python -I -X utf8 desktop/scripts/brand.py [--font <ibm-plex-sans-latin-600-normal.woff>]
        [--icon c]
"""

from __future__ import annotations

import argparse
import base64
import io
import pathlib
import re
import struct

DESKTOP = pathlib.Path(__file__).resolve().parent.parent
BRAND = DESKTOP / "build" / "brand"
PNG = BRAND / "png"
SIZES = [16, 24, 32, 48, 64, 128, 256, 1024]
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def marks() -> list[pathlib.Path]:
    return sorted(BRAND.glob("emma-mark-?.svg"))


def source_for(mark: pathlib.Path, size: int) -> pathlib.Path:
    small = mark.with_name(f"{mark.stem}-16.svg")
    return small if size == 16 and small.exists() else mark


def uri(path: pathlib.Path) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode()


def png_uri(path: pathlib.Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def wordmarks(font_path: pathlib.Path) -> None:
    """«EMMA» en IBM Plex Sans SemiBold, en contornos: el logotipo no depende de la fuente."""
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont

    font = TTFont(str(font_path))
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    upm = font["head"].unitsPerEm
    cap_px, track, mark_px, gap = 30.0, 0.04, 48.0, 14.0
    scale = cap_px / font["OS/2"].sCapHeight
    baseline = (mark_px + cap_px) / 2
    pen = SVGPathPen(glyphs)
    x = mark_px + gap
    for char in "EMMA":
        name = cmap[ord(char)]
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        x += (glyphs[name].width + track * upm) * scale
    width = x - track * upm * scale
    outline = re.sub(r"(\d+\.\d{2})\d+", r"\1", pen.getCommands())

    for mark in marks():
        letter = mark.stem[-1]
        found = re.search(r"</title>\s*(.*)</svg>", mark.read_text(encoding="utf-8"), re.DOTALL)
        assert found, mark
        inner = found.group(1).strip()
        for suffix, color, token, ground in (("", "#EEF2F6", "text", "oscuro"), ("-claro", "#0A0D12", "bg", "claro")):
            (BRAND / f"emma-logo-{letter}{suffix}.svg").write_text(
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.2f} {mark_px:.0f}" '
                f'width="{width * 4:.0f}" height="{mark_px * 4:.0f}">\n'
                "  <!-- SPDX-License-Identifier: AGPL-3.0-or-later -->\n"
                f"  <!-- EMMA, logotipo de la candidata {letter.upper()} para fondo {ground}. Generado por\n"
                f"       desktop/scripts/brand.py: la marca es emma-mark-{letter}.svg tal cual y «EMMA» va en\n"
                "       contornos de IBM Plex Sans SemiBold (600; SIL OFL 1.1), así que no necesita la\n"
                f"       fuente instalada. Color del texto: {token} de palette.ts. -->\n"
                "  <title>EMMA</title>\n"
                f'  <g transform="scale(2)">\n    {inner}\n  </g>\n'
                f'  <path fill="{color}" d="{outline}"/>\n'
                "</svg>\n",
                encoding="utf-8",
                newline="\n",
            )


def render() -> None:
    from playwright.sync_api import sync_playwright

    PNG.mkdir(exist_ok=True)
    logos = sorted(BRAND.glob("emma-logo-*.svg"))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chromium")
        page = browser.new_page(device_scale_factor=1)
        for mark in marks():
            for size in SIZES:
                page.set_viewport_size({"width": size, "height": size})
                page.set_content(
                    '<html><body style="margin:0;background:transparent">'
                    f'<img src="{uri(source_for(mark, size))}" width="{size}" height="{size}" '
                    'style="display:block"></body></html>'
                )
                page.wait_for_timeout(50)
                page.screenshot(path=str(PNG / f"{mark.stem}-{size}.png"), omit_background=True)

        sections = []
        for bg, fg, ground in (("#0A0D12", "#EEF2F6", "oscuro"), ("#F4F6F8", "#0A0D12", "claro")):
            cells = []
            for mark in marks():
                small = PNG / f"{mark.stem}-16.png"
                row = f'<img src="{png_uri(small)}" width="16" height="16" style="margin:0 14px;vertical-align:bottom">'
                row += "".join(
                    f'<img src="{uri(mark)}" width="{s}" height="{s}" style="margin:0 14px;vertical-align:bottom">'
                    for s in (24, 32, 48, 128)
                )
                # El de 16 px ampliado ×8 sin suavizar: el pixelado real del icono.
                row += (
                    f'<img src="{png_uri(small)}" width="128" height="128" '
                    'style="image-rendering:pixelated;margin-left:24px;vertical-align:bottom">'
                )
                cells.append(
                    f'<div style="margin:18px 0"><div style="font:600 18px sans-serif;color:{fg};'
                    f'margin-bottom:8px">{mark.stem} — fondo {ground} (16, 24, 32, 48, 128; 16 ×8)</div>{row}</div>'
                )
            lockups = "".join(
                f'<img src="{uri(logo)}" height="72" style="margin:14px 28px 14px 0">'
                for logo in logos
                if ("claro" in logo.stem) == (ground == "claro")
            )
            sections.append(f'<section style="background:{bg};padding:20px 28px">{"".join(cells)}<div>{lockups}</div></section>')
        page.set_viewport_size({"width": 1100, "height": 400})
        page.set_content(f'<html><body style="margin:0">{"".join(sections)}</body></html>')
        page.wait_for_timeout(200)
        page.screenshot(path=str(BRAND / "hoja-de-contactos.png"), full_page=True)
        browser.close()


def _bmp_entry(image: object) -> bytes:
    """Una entrada BMP de 32 bits (BGRA, de abajo arriba, con máscara AND): la que lee todo."""
    from PIL import Image

    assert isinstance(image, Image.Image)
    w, h = image.size
    rgba = image.convert("RGBA")
    rows = []
    for y in range(h - 1, -1, -1):
        row = bytearray()
        for x in range(w):
            r, g, b, a = rgba.getpixel((x, y))  # type: ignore[misc]
            row += bytes((b, g, r, a))
        rows.append(bytes(row))
    mask_row = ((w + 31) // 32) * 4
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    return header + b"".join(rows) + b"\0" * (mask_row * h)


def ico(letter: str) -> None:
    """`build/icon.ico`: BMP de 16 a 128 y PNG en 256, como los iconos de Windows."""
    from PIL import Image

    entries = []
    for size in ICO_SIZES:
        path = PNG / f"emma-mark-{letter}-{size}.png"
        if size >= 256:
            entries.append((size, path.read_bytes()))
        else:
            with Image.open(path) as image:
                entries.append((size, _bmp_entry(image)))
    out = io.BytesIO()
    out.write(struct.pack("<HHH", 0, 1, len(entries)))
    offset = 6 + 16 * len(entries)
    for size, data in entries:
        dim = 0 if size >= 256 else size
        out.write(struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    for _, data in entries:
        out.write(data)
    (DESKTOP / "build" / "icon.ico").write_bytes(out.getvalue())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=pathlib.Path, help="IBM Plex Sans 600 (.woff o .ttf) para rehacer los logotipos")
    parser.add_argument("--icon", default="c", help="candidata que va al .ico (por defecto, la recomendada: c)")
    args = parser.parse_args()
    if args.font:
        wordmarks(args.font)
    render()
    ico(args.icon)
    print(f"listo: {len(marks())} candidatas, icon.ico desde la {args.icon.upper()}")


if __name__ == "__main__":
    main()
