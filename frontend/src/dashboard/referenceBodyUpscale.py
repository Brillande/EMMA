"""Amplía ×4 el recorte del cuerpo de la maqueta con Real-ESRGAN (RRDBNet, pesos `RealESRGAN_x4plus.pth`).

La arquitectura va aquí mismo (es la RRDBNet de BasicSR, ~60 líneas) para no depender del paquete
`realesrgan`, que arrastra `basicsr` y rompe con versiones recientes de torch. Los pesos se cargan con
`weights_only=True`: de un fichero descargado no se ejecuta nada. Corre en CPU: la GPU está ocupada con
un entrenamiento. Uso: esrgan.py <pesos> <maqueta> <salida 4x png> [comparación png]
"""

import sys

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image

WEIGHTS, MOCKUP, OUT, CMP = (sys.argv[1:] + [None])[:4]
PAD = 8


class ResidualDenseBlock(nn.Module):
    def __init__(self, num_feat: int = 64, num_grow_ch: int = 32) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(num_feat, num_grow_ch, 3, 1, 1)
        self.conv2 = nn.Conv2d(num_feat + num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv3 = nn.Conv2d(num_feat + 2 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv4 = nn.Conv2d(num_feat + 3 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv5 = nn.Conv2d(num_feat + 4 * num_grow_ch, num_feat, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x1 = self.lrelu(self.conv1(x))
        x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
        x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
        return x5 * 0.2 + x


class RRDB(nn.Module):
    def __init__(self, num_feat: int, num_grow_ch: int = 32) -> None:
        super().__init__()
        self.rdb1 = ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb2 = ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb3 = ResidualDenseBlock(num_feat, num_grow_ch)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.rdb3(self.rdb2(self.rdb1(x)))
        return out * 0.2 + x


class RRDBNet(nn.Module):
    def __init__(self, num_in_ch: int = 3, num_out_ch: int = 3, num_feat: int = 64, num_block: int = 23, num_grow_ch: int = 32) -> None:
        super().__init__()
        self.conv_first = nn.Conv2d(num_in_ch, num_feat, 3, 1, 1)
        self.body = nn.Sequential(*[RRDB(num_feat, num_grow_ch) for _ in range(num_block)])
        self.conv_body = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_up1 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_up2 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_hr = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_last = nn.Conv2d(num_feat, num_out_ch, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        feat = self.conv_first(x)
        feat = feat + self.conv_body(self.body(feat))
        feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
        feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
        return self.conv_last(self.lrelu(self.conv_hr(feat)))


state = torch.load(WEIGHTS, map_location="cpu", weights_only=True)
state = state.get("params_ema", state.get("params", state))
model = RRDBNet()
missing, unexpected = model.load_state_dict(state, strict=True), None
model.eval()
print("pesos cargados:", len(state), "tensores")

src = Image.open(MOCKUP).convert("RGB")
crop = src.crop((866 - PAD, 200 - PAD, 1018 + PAD, 510 + PAD))
x = torch.from_numpy(np.array(crop, dtype=np.float32) / 255.0).permute(2, 0, 1).unsqueeze(0)
with torch.no_grad():
    y = model(x).clamp_(0, 1)
up = (y[0].permute(1, 2, 0).numpy() * 255.0).round().astype(np.uint8)
up = up[PAD * 4 : -PAD * 4, PAD * 4 : -PAD * 4]
print("salida", up.shape)
Image.fromarray(up).save(OUT)

if CMP:
    base = np.array(src.crop((866, 200, 1018, 510)), dtype=np.uint8)
    lanczos = cv2.resize(base, (608, 1240), interpolation=cv2.INTER_LANCZOS4)
    blur = cv2.GaussianBlur(lanczos, (0, 0), 2.0)
    sharp = np.clip(lanczos.astype(float) + 0.8 * (lanczos.astype(float) - blur.astype(float)), 0, 255).astype(np.uint8)
    boxes = [(180, 0, 428, 280), (160, 240, 448, 560), (0, 500, 208, 840)]
    tiles = []
    for img in (sharp, up):
        for box in boxes:
            tiles.append(Image.fromarray(img).crop(box))
    W = sum(t.width + 8 for t in tiles[:3])
    H = max(t.height for t in tiles) + 10
    out = Image.new("RGB", (W, H * 2), (16, 26, 38))
    for row in range(2):
        x0 = 0
        for t in tiles[row * 3 : row * 3 + 3]:
            out.paste(t, (x0, row * H))
            x0 += t.width + 8
    out.save(CMP)
    print("comparación", out.size)
