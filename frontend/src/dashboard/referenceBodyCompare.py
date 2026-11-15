"""Compara el cuerpo de nuestra captura con el de la maqueta: alinea por caja del cuerpo y mide por zonas."""

import sys

import cv2
import numpy as np
from PIL import Image

mockup, capture = sys.argv[1], sys.argv[2]


def body_box(img: np.ndarray) -> tuple[int, int, int, int]:
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    mask = ((img.max(axis=2) > 96) & ((hsv[:, :, 1] > 70) | (hsv[:, :, 2] > 170))).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    ys, xs = np.where(labels == largest)
    return xs.min(), ys.min(), xs.max(), ys.max()


ref = np.array(Image.open(mockup).convert("RGB").crop((866, 200, 1006, 510)))
ours = np.array(Image.open(capture).convert("RGB").crop((900, 224, 1070, 526)))
rb, ob = body_box(ref), body_box(ours)
size = (rb[2] - rb[0] + 1, rb[3] - rb[1] + 1)
ref_body = ref[rb[1] : rb[3] + 1, rb[0] : rb[2] + 1]
ours_body = cv2.resize(ours[ob[1] : ob[3] + 1, ob[0] : ob[2] + 1], size, interpolation=cv2.INTER_AREA)
print("caja maqueta", rb, "caja nuestra", ob)

h = size[1]
zones = {"cabeza": (0.0, 0.17), "pecho": (0.17, 0.38), "vientre": (0.38, 0.55), "piernas": (0.55, 1.0)}
ref_hsv = cv2.cvtColor(ref_body, cv2.COLOR_RGB2HSV).astype(float)
ours_hsv = cv2.cvtColor(ours_body, cv2.COLOR_RGB2HSV).astype(float)
inside = ref_body.max(axis=2) > 60
for name, (a, b) in zones.items():
    sl = slice(int(a * h), int(b * h))
    m = inside[sl]
    r, o = ref_body[sl][m].astype(float), ours_body[sl][m].astype(float)
    rh, oh = ref_hsv[sl][m], ours_hsv[sl][m]
    print(f"{name:8s} RGB maq {r.mean(axis=0).round(0)} nos {o.mean(axis=0).round(0)} | S maq {rh[:,1].mean():.0f} nos {oh[:,1].mean():.0f} | V maq {rh[:,2].mean():.0f} nos {oh[:,2].mean():.0f} | dif abs {np.abs(r - o).mean():.1f}")
diff = np.abs(ref_body.astype(int) - ours_body.astype(int)).mean(axis=2)
print("diferencia media global", diff[inside].mean().round(1))
cv2.imwrite(sys.argv[3], cv2.resize(np.clip(diff * 2, 0, 255).astype(np.uint8), (size[0] * 3, size[1] * 3), interpolation=cv2.INTER_NEAREST))
