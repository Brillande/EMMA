"""Avatar femenino del cuerpo de la maqueta: el mismo render deformado, no un dibujo nuevo.

Por qué existe (petición del usuario, 2026-11-14): «queremos respetar el estilo gráfico de los cuerpos 3D
y 2D y colores, pero queremos también un avatar femenino». La maqueta solo trae un varón; pintar una mujer
aparte cambiaría el estilo. Aquí se reutilizan los propios píxeles del render (el calor, los filos, las
líneas) y solo se mueve la geometría con un deformado suave:

- por filas, una escala horizontal alrededor del eje del cuerpo: hombros y cintura más estrechos, caderas y
  muslos más anchos, cabeza y cuello algo más finos. Fuera del tronco no se escala sino que se desplaza
  igual que el borde del tronco: los brazos acompañan al costado sin estirarse ni chocar con él;
- dos lupas suaves bajo los pectorales que redondean el pecho (solo forma: los colores son los de ahí).

Escribe la ampliación ×4 deformada y una «maqueta» sintética con el 1x deformado en el recorte que lee
`referenceBodyMosaic.py`, que es quien genera los datos (`referenceBodyFemale.generated.ts`): mismo
camino, mismo trazado, mismo estilo. Es adorno (§2.5 de `compliance/hmi-state-of-the-art.md`), no dato.

Uso: referenceBodyFemale.py <cuerpo 4x png> <salida 4x png> <salida maqueta png>
"""

import sys

import cv2
import numpy as np
from PIL import Image

SRC, OUT_FINE, OUT_MOCKUP = sys.argv[1:4]
CROP = (866, 200, 1018, 510)  # el de `referenceBodyMosaic.py`
SCALE = 4
CENTER = 297.0  # eje del cuerpo en el 4x (medio del tronco y de la cabeza)

# (fila 4x, escala horizontal del tronco, semiancho del tronco en el 4x). Entre nudos, interpolación suave.
PROFILE = [
    (0, 0.95, 60),
    (150, 0.93, 62),  # cabeza: cara algo más fina
    (215, 0.90, 46),  # mandíbula y cuello
    (245, 0.88, 92),  # arranque del hombro
    (290, 0.86, 175),  # hombros: la mitad del cambio está aquí
    (360, 0.90, 180),
    (400, 0.92, 117),  # pecho, bajo la axila: ya solo el tronco
    (450, 0.86, 104),  # cintura
    (490, 0.85, 100),
    (540, 0.95, 100),
    (590, 1.08, 110),  # caderas
    (640, 1.10, 121),
    (690, 1.08, 130),  # arranque del muslo (dos piernas: semiancho del par)
    (780, 1.04, 120),
    (880, 1.00, 112),  # rodillas, como estaban
    (1240, 1.00, 112),
]

# Lupas: (centro x 4x relativo al eje, fila, radio, fuerza). Fuerza > 0 amplía (el pecho, que redondea
# los pectorales del render); < 0 encoge (el bulto de la entrepierna del varón, que se recoge).
BUSTS = [(-56, 385, 64, 0.42), (56, 385, 64, 0.42), (0, 640, 44, -0.55)]

# Pelo: media melena del mismo holograma. Colores tomados de la cabeza del render (sombra y luz de la
# cabeza, filo del contorno): el pelo es un tramo más del cuerpo, no un color nuevo.
HAIR_DARK = np.array([48, 140, 222], float)
HAIR_LIGHT = np.array([96, 204, 252], float)
HAIR_STRAND = np.array([120, 222, 255], float)
RIM = np.array([200, 255, 255], float)
LINE = np.array([232, 246, 0], float)  # el amarillo de la línea del esternón


def smooth_profile(h: int) -> tuple[np.ndarray, np.ndarray]:
    ys = np.array([p[0] for p in PROFILE], float)
    s = np.interp(np.arange(h), ys, [p[1] for p in PROFILE])
    w = np.interp(np.arange(h), ys, [p[2] for p in PROFILE])
    k = np.ones(31) / 31
    pad = lambda a: np.concatenate([np.full(15, a[0]), a, np.full(15, a[-1])])  # noqa: E731
    return np.convolve(pad(s), k, "valid"), np.convolve(pad(w), k, "valid")


def inverse_x(dst_dx: np.ndarray, s: float, w: float) -> np.ndarray:
    """Para cada x de destino (relativo al eje), la x de origen. Dentro del tronco escala; fuera, desplaza
    lo que se desplazó el borde, con un tramo de transición de 24 px para no dejar quiebro."""
    a = np.abs(dst_dx)
    edge = w * s
    inner = a / s
    outer = a - edge + w
    t = np.clip((a - edge) / 24.0 + 0.5, 0, 1)
    t = t * t * (3 - 2 * t)
    return np.sign(dst_dx) * ((1 - t) * inner + t * outer)


def warp(rgb: np.ndarray, background: np.ndarray) -> np.ndarray:
    h, w = rgb.shape[:2]
    s, half = smooth_profile(h)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    map_x = np.empty_like(xx)
    for y in range(h):
        map_x[y] = CENTER + inverse_x(xx[y] - CENTER, float(s[y]), float(half[y]))
    map_y = yy.copy()
    for bx, by, r, k in BUSTS:
        cx = CENTER + bx * float(s[by])
        dx, dy = map_x - cx, map_y - by
        d = np.sqrt(dx * dx + dy * dy) / r
        f = np.where(d < 1, 1 - k * (1 - d * d) ** 2, 1.0)  # lupa: el centro se toma de más cerca
        map_x = cx + dx * f
        map_y = by + dy * f
    out = cv2.remap(rgb, map_x, map_y, cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=background.tolist())
    # La entrepierna, lisa: tras encogerla, el dibujo del bulto del varón aún se leía. Se funde con su
    # entorno muy desenfocado (mismos colores del render, sin la forma), en un óvalo de borde suave.
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    blend = np.exp(-(((xx - CENTER) / 26) ** 2 + ((yy - 642) / 30) ** 2) ** 2)[..., None]
    soft = cv2.GaussianBlur(out, (0, 0), 14).astype(np.float32)
    out = (out.astype(np.float32) * (1 - blend) + soft * blend).astype(np.uint8)
    return out


def add_hair(rgb: np.ndarray) -> np.ndarray:
    """Media melena: por detrás de la cabeza (asoma a los lados hasta la mandíbula) y un casquete con raya
    sobre el cráneo. Degradado de la cabeza, mechones con la luz del render y filo como el del contorno."""
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    dx = xx - CENTER
    # Cabeza (tras el deformado): lo claro o azul por encima del cuello, componente central.
    head = ((rgb.max(axis=2) > 80) & (yy < 222) & (np.abs(dx) < 110)).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(head)
    head = (labels == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))).astype(float)
    # Detrás: óvalo de la cabeza algo mayor, que baja recto a los lados hasta la mandíbula y se redondea.
    # Bajo la mandíbula solo los dos mechones de los lados: el cuello queda a la vista.
    oval = (dx / 76) ** 2 + ((yy - 112) / 86) ** 2 < 1
    sides = (np.abs(dx) < 76 - 0.04 * np.clip(yy - 200, 0, None) ** 1.5) & (yy > 112) & (yy < 238)
    back = (oval | sides) & ~((yy > 186) & (np.abs(dx) < 40 + 0.25 * (yy - 186)))
    # Casquete: el cráneo por encima de la raya del pelo (flequillo ladeado, más bajo a la derecha de la
    # cara) y, a los lados, las orejas tapadas por el pelo.
    u = dx + 14
    hairline = 70 + 40 * np.clip(np.abs(u) / 56, 0, 1.3) ** 2 + 16 * np.clip(-u / 56, 0, 1) - 5 * np.exp(-((u / 5) ** 2))
    cap = head * ((yy < hairline) | ((np.abs(dx) > 50) & (yy < 190)))
    alpha = np.clip(back * (1 - head) + cap, 0, 1).astype(np.float32)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 1.6)
    # Degradado de arriba (luz) abajo (sombra) y de dentro a fuera, como la cabeza del render.
    t = np.clip((yy - 30) / 200, 0, 1)[..., None]
    side = np.clip(np.abs(dx) / 80, 0, 1)[..., None]
    color = HAIR_LIGHT * (1 - t) * (1 - 0.4 * side) + HAIR_DARK * (t + 0.4 * side * (1 - t))
    # Mechones: curvas suaves que salen de la raya y caen por los lados (líneas de nivel de un campo que se
    # abre con la altura), finas y tenues, con la luz de las líneas del render.
    flow = u / (12 + 0.55 * np.clip(yy - 40, 0, None)) + 0.0004 * (yy - 40) * np.sign(u)
    strands = np.clip((np.cos(flow * 9.0) - 0.9) / 0.1, 0, 1)[..., None] * (yy > 50)[..., None]
    color = color * (1 - 0.4 * strands) + HAIR_STRAND * 0.4 * strands
    out = rgb.astype(float) * (1 - alpha[..., None]) + color * alpha[..., None]
    # Filo luminoso en el borde exterior del pelo (no sobre la cara).
    shape = (alpha > 0.5).astype(np.uint8)
    rim = (cv2.dilate(shape, np.ones((5, 5), np.uint8)) - shape).astype(np.float32)
    rim *= 1 - cv2.dilate(head.astype(np.uint8), np.ones((3, 3), np.uint8)) * (yy >= hairline)
    rim = cv2.GaussianBlur(rim, (0, 0), 1.0)[..., None]
    out = out * (1 - rim) + RIM * rim
    # El contorno inferior del pecho, con el trazo amarillo de las líneas anatómicas del render (el que
    # ya marca el esternón y los pectorales): arcos bajo cada lupa del pecho.
    lines = np.zeros((h, w), np.float32)
    for bx, by, r, k in BUSTS[:2]:
        cv2.ellipse(lines, (int(CENTER + bx * 0.92), by + 6), (r - 10, r - 18), 0, 25 if bx > 0 else 35, 145 if bx > 0 else 155, 1.0, 3, cv2.LINE_AA)
    lines = cv2.GaussianBlur(lines, (0, 0), 1.1)[..., None] * 0.7
    out = out * (1 - lines) + LINE * lines
    return np.clip(out, 0, 255).astype(np.uint8)


src = np.array(Image.open(SRC).convert("RGB"), dtype=np.uint8)
assert src.shape[:2] == ((CROP[3] - CROP[1]) * SCALE, (CROP[2] - CROP[0]) * SCALE), src.shape
bg = np.median(src[:30, :30].reshape(-1, 3), axis=0).astype(np.uint8)
# La gráfica de la maqueta (esquina inferior izquierda) no es del cuerpo: se borra antes de deformar, para
# que el deformado no la arrastre hacia la mano.
r_, g_, b_ = (src[:, :, i].astype(int) for i in range(3))
corner = np.zeros(src.shape[:2], bool)
corner[188 * SCALE :, : 36 * SCALE] = True
src[corner & ~((b_ > r_ + 25) & (b_ >= g_ - 15))] = bg
# El marco del panel (columna 583-589 del 4x) tampoco: se aparta y se vuelve a poner tal cual.
frame = src[:, 560:].copy()
src[:, 560:] = bg
fine = add_hair(warp(src, bg))
fine[:, 560:] = frame
Image.fromarray(fine).save(OUT_FINE)

one = cv2.resize(fine, (CROP[2] - CROP[0], CROP[3] - CROP[1]), interpolation=cv2.INTER_AREA)
mockup = np.zeros((CROP[3] + 10, CROP[2] + 10, 3), np.uint8)
mockup[:] = bg
mockup[CROP[1] : CROP[3], CROP[0] : CROP[2]] = one
Image.fromarray(mockup).save(OUT_MOCKUP)
print("hecho", OUT_FINE, OUT_MOCKUP)
