"""Calco del cuerpo de la maqueta: píxel a píxel a 100 % y vectorial (capas de color) con zoom.

Lee el recorte del cuerpo de la maqueta, aísla el cuerpo (máscara) y escribe dos cosas:

- 1x: sus píxeles como datos (paleta + tramos por fila) con los colores exactos del render, que la página
  pinta en un `canvas` a 100 % (píxel exacto; aprobado por el usuario).
- Vectorial: para zoom y HiDPI, un SVG de capas de color apiladas trazadas con curvas a partir de la imagen
  ampliada ×4 por Real-ESRGAN (`referenceBodyUpscale.py`; pesos y salida en `data/upscale/`, fuera de git;
  sin ella, Lanczos). Cada capa cubre sus píxeles y los de todas las capas que van encima (de oscuro a
  claro), así ningún borde entre colores deja costura: lo que asoma es otra capa, nunca el fondo. Es lo que
  pidió el usuario (2026-11-07): «como svg de resolución», nítido a cualquier zoom. Un mosaico de
  rectángulos (fases 14-39) daba grano fuera del 100 %, y un lienzo (fases 40-44) se ablanda al ampliar.

Los colores son los del propio render (decisión del usuario, 2026-11-07: solo en esta página provisional;
la consola sigue con la paleta). Escribe los datos y el CSS que la página monta.

Uso: referenceBodyMosaic.py <maqueta> <datos ts> <css> [cuerpo 4x png]

Escribe `referenceBody.generated.ts` (solo datos, exportados); el componente que los pinta es
`ReferenceBody.tsx`, escrito a mano y cargado perezoso desde el tablero.
"""

import os
import sys

import cv2
import numpy as np
from PIL import Image

MOCKUP, OUT_TSX, OUT_CSS = sys.argv[1:4]
FINE = sys.argv[4] if len(sys.argv) > 4 else None
CROP = (866, 200, 1018, 510)
FINE_SCALE = 4
VECTOR_COLORS = 192
PRECISION = 2  # medias unidades del lienzo 4x = 1/8 de píxel css


def prepare(scale: int, source: str | None = None) -> tuple[int, int, np.ndarray, np.ndarray]:
    """El recorte a una escala y la máscara del cuerpo: (ancho css, alto css, rgb, máscara).

    `source` es una imagen ya ampliada a `scale` (la de Real-ESRGAN) que sustituye al reescalado Lanczos.
    """
    src = Image.open(MOCKUP).convert("RGB")
    crop = src.crop(CROP)
    css_w, css_h = crop.size
    rgb = np.array(crop, dtype=np.uint8)
    if source:
        rgb = np.array(Image.open(source).convert("RGB"), dtype=np.uint8)
        assert rgb.shape[:2] == (css_h * scale, css_w * scale), rgb.shape
    elif scale > 1:
        rgb = cv2.resize(rgb, (css_w * scale, css_h * scale), interpolation=cv2.INTER_LANCZOS4)
    h, w = rgb.shape[:2]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    value = hsv[:, :, 2].astype(int)
    sat = hsv[:, :, 1].astype(int)

    # Máscara del cuerpo con su filo luminoso; cierre pequeño para no perder dedos; huecos rellenos.
    mask = ((rgb.max(axis=2) > 80) & ((sat > 60) | (value > 150))).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    mask = (labels == largest).astype(np.uint8) * 255
    flood = mask.copy()
    cv2.floodFill(flood, np.zeros((h + 2, w + 2), np.uint8), (0, 0), 255)
    mask = mask | cv2.bitwise_not(flood)
    # La gráfica de la maqueta pisa la esquina inferior izquierda, pero la mano izquierda del render está
    # dibujada encima, intacta: no se sustituye nada; solo se apartan de la máscara, en esa esquina, los
    # píxeles de la gráfica (líneas amarillas o cian y texto blanco) que no son del cuerpo azul. La mano
    # acaba en y≈184 y el panel empieza en y≈191 (1x): en las escalas grandes la limpieza empieza en 188,
    # porque el filo blanco de la mano no pasa el criterio azul y salía picoteado. A 1x se conserva el
    # recorte de la fase 37, aprobado por el usuario.
    corner = np.zeros_like(mask, dtype=bool)
    corner[(168 if scale == 1 else 188) * scale :, : 36 * scale] = True
    r_, g_, b_ = (rgb[:, :, i].astype(int) for i in range(3))
    mask[corner & ~((b_ > r_ + 25) & (b_ >= g_ - 15))] = 0
    # Los puntos oscuros de dentro (sombras del render, huecos sellados) se rellenan con el color vecino,
    # no se vacían: vaciarlos dejaba agujeros y bordes picoteados en manos y brazos.
    dark = ((mask > 0) & (rgb.max(axis=2) < 70)).astype(np.uint8)
    rgb = cv2.inpaint(rgb, dark, 2 * scale, cv2.INPAINT_TELEA)
    # Borde limpio: los píxeles del contorno que sigan oscuros salen de la máscara (una pasada por escala).
    for _ in range(scale):
        edge = (mask > 0) & (cv2.erode(mask, np.ones((3, 3), np.uint8)) == 0)
        mask[edge & (rgb.max(axis=2) < 110)] = 0
    ys, xs = np.where(mask > 0)
    print(f"{scale}x máscara", xs.min(), ys.min(), xs.max(), ys.max(), "píxeles", int((mask > 0).sum()))
    return css_w, css_h, rgb, mask


def exact_runs(rgb: np.ndarray, mask: np.ndarray) -> tuple[list[str], list[str]]:
    """Paleta con los colores exactos y tramos por fila: `índice:largo`, `-` = transparente, `n|` = hueco inicial."""
    h, w = mask.shape
    ys, xs = np.where(mask > 0)
    pix = rgb[ys, xs].astype(int)
    keys = (pix[:, 0] << 16) | (pix[:, 1] << 8) | pix[:, 2]
    uniq, inverse = np.unique(keys, return_inverse=True)
    colors = ["#%06x" % int(u) for u in uniq]
    grid = np.full((h, w), -1, dtype=int)
    grid[ys, xs] = inverse.reshape(-1)
    rows: list[str] = []
    total = 0
    for y in range(h):
        row = grid[y]
        parts: list[str] = []
        x = 0
        while x < w:
            c = int(row[x])
            start = x
            while x < w and row[x] == c:
                x += 1
            if c < 0:
                if parts:
                    parts.append(f"-:{x - start}")
            else:
                parts.append(f"{c}:{x - start}")
        while parts and parts[-1].startswith("-:"):
            parts.pop()
        lead = int(np.argmax(row >= 0)) if parts and row[0] < 0 else 0
        rows.append((f"{lead}|" if lead else "") + ",".join(parts))
        total += len(parts)
    print("1x colores", len(colors), "tramos", total)
    return colors, rows


def polyline(pts: np.ndarray) -> str:
    """Polilínea relativa con coordenadas enteras (1/PRECISION de unidad): compacta y, tras el suavizado,
    indistinguible de una curva (a 500 % un paso es ~1 píxel de pantalla)."""
    q = np.round(pts * PRECISION).astype(int)
    out = [f"M{q[0][0]} {q[0][1]}"]
    prev = q[0]
    for p in q[1:]:
        dx, dy = int(p[0] - prev[0]), int(p[1] - prev[1])
        if dx == 0 and dy == 0:
            continue
        out.append(f"h{dx}" if dy == 0 else f"v{dy}" if dx == 0 else f"l{dx} {dy}")
        prev = p
    return "".join(out) + "z"


def trace_mask(mask: np.ndarray, window: int = 7, eps: float = 1.0, min_area: float = 24.0) -> str:
    """Contornos (con agujeros) de una máscara, suavizados: media móvil, simplificación y polilínea."""
    contours, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    parts = []
    for c in contours:
        if abs(cv2.contourArea(c)) < min_area:
            continue
        pts = c.reshape(-1, 2).astype(float) + 0.5
        win = min(window, len(pts))
        if win >= 3:
            kern = np.ones(win) / win
            padded = np.concatenate([pts[-(win // 2) :], pts, pts[: win // 2]])
            pts = np.stack([np.convolve(padded[:, 0], kern, mode="valid"), np.convolve(padded[:, 1], kern, mode="valid")], axis=1)
        poly = cv2.approxPolyDP(pts.astype(np.float32).reshape(-1, 1, 2), eps, True).reshape(-1, 2)
        if len(poly) < 3:
            continue
        parts.append(polyline(poly))
    return "".join(parts)


def vector_layers(rgb: np.ndarray, mask: np.ndarray, k: int) -> list[tuple[str, str]]:
    """Capas apiladas de oscuro a claro: (color, trayecto); la capa i cubre sus píxeles y los de las de encima."""
    ys, xs = np.where(mask > 0)
    samples = rgb[ys, xs].astype(np.float32)
    _, assigned, centers = cv2.kmeans(samples, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5), 2, cv2.KMEANS_PP_CENTERS)
    lum = centers @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    order = np.argsort(lum)
    rank_of = np.empty(k, dtype=int)
    rank_of[order] = np.arange(k)
    grid = np.full(mask.shape, -1, dtype=int)
    grid[ys, xs] = rank_of[assigned.reshape(-1)]
    layers: list[tuple[str, str]] = []
    for rank in range(k):
        d = trace_mask((grid >= rank).astype(np.uint8))
        if not d:
            continue
        center = centers[order[rank]]
        layers.append(("#%02x%02x%02x" % tuple(int(round(float(v))) for v in center), d))
    print("vectorial capas", len(layers), "caracteres", sum(len(d) for _, d in layers))
    return layers


CSS_W, CSS_H, RGB_ONE, MASK_ONE = prepare(1)
PALETTE, ROWS = exact_runs(RGB_ONE, MASK_ONE)
_, _, RGB_FINE, MASK_FINE = prepare(FINE_SCALE, FINE)
LAYERS = vector_layers(RGB_FINE, MASK_FINE, VECTOR_COLORS)
VEC_W, VEC_H = CSS_W * FINE_SCALE * PRECISION, CSS_H * FINE_SCALE * PRECISION

with open(OUT_TSX, "w", encoding="utf-8") as f:
    f.write("/**\n")
    f.write(" * GENERADO por `referenceBodyMosaic.py`: no se edita a mano. Calco del cuerpo de la maqueta (petición del\n")
    f.write(" * usuario, 2026-11-06): los píxeles del cuerpo de su render con sus propios colores (decisión del usuario,\n")
    f.write(" * 2026-11-07: colores muestreados, solo en esta página provisional; la consola sigue con la paleta).\n")
    f.write(" * - `BODY_ONE`: a 100 %, datos de píxeles (paleta y tramos por fila: `índice:largo`, `-` = transparente,\n")
    f.write(" *   `n|` = hueco inicial) que `ReferenceBody.tsx` pinta en un lienzo, píxel exacto.\n")
    f.write(" * - `BODY_VECTOR`: con zoom o HiDPI, capas de color apiladas (de oscuro a claro, cada una cubre a las de\n")
    f.write(" *   encima: sin costuras) trazadas sobre la ampliación ×4 de Real-ESRGAN, nítidas a cualquier zoom.\n")
    f.write(" * Vive aparte y se carga al abrirse el tablero (`lazy`): son ~1,5 MB que no deben viajar con la consola.\n")
    f.write(" */\n")
    f.write(f"export const BODY_W = {CSS_W};\nexport const BODY_H = {CSS_H};\n\n")
    f.write("export interface BodyPixels {\n  readonly scale: number;\n  readonly palette: readonly string[];\n  readonly rows: readonly string[];\n}\n\n")
    f.write("export const BODY_ONE: BodyPixels = {\n  scale: 1,\n  palette: [\n")
    for i in range(0, len(PALETTE), 12):
        f.write("    " + ", ".join(f'"{c}"' for c in PALETTE[i : i + 12]) + ",\n")
    f.write("  ],\n  rows: [\n")
    for row in ROWS:
        f.write(f'    "{row}",\n')
    f.write("  ],\n};\n\n")
    f.write(f"export const BODY_VECTOR_W = {VEC_W};\nexport const BODY_VECTOR_H = {VEC_H};\n")
    f.write("/** Capas apiladas de oscuro a claro: [color, trayecto]; coordenadas en 1/8 de píxel css. */\n")
    f.write("export const BODY_VECTOR: readonly (readonly [string, string])[] = [\n")
    for color, d in LAYERS:
        f.write(f'  ["{color}", "{d}"],\n')
    f.write("];\n")

# La hoja de salida es solo suya: si ya existe y no empieza por su propia cabecera (p. ej. alguien
# pasa `referenceDashboard.css`), no se trunca (lo señaló la revisión de la unidad 10). Su bloque se
# pega a mano al final de `referenceDashboard.css`.
if os.path.exists(OUT_CSS):
    with open(OUT_CSS, encoding="utf-8") as existing:
        head = existing.read(200)
    if "generado por `referenceBodyMosaic.py`" not in head:
        sys.exit(f"{OUT_CSS} no es una hoja generada por este script: no se sobrescribe")

with open(OUT_CSS, "w", encoding="utf-8") as f:
    f.write("\n/*\n * Calco del cuerpo (petición del usuario, 2026-11-06), generado por `referenceBodyMosaic.py`: a 100 % el lienzo\n")
    f.write(" * píxel a píxel; con zoom o en HiDPI el vectorial (capas de color apiladas), nítido a cualquier zoom (petición\n")
    f.write(" * del usuario, 2026-11-07: «como svg de resolución»). Misma caja para los dos; los colores van en el TSX.\n */\n")
    f.write(".ref-body-canvas,\n.ref-body-vector {\n  position: absolute;\n  top: 50%;\n  left: 50%;\n")
    f.write(f"  width: {CSS_W}px;\n  height: {CSS_H}px;\n  transform: translate(-50%, -50%);\n  pointer-events: none;\n  z-index: 0;\n}}\n\n")
    f.write(".ref-body-vector {\n  display: none;\n}\n\n")
    f.write("@media (min-resolution: 1.05dppx) {\n  .ref-body-canvas {\n    display: none;\n  }\n\n  .ref-body-vector {\n    display: block;\n  }\n}\n")
print("hecho")
