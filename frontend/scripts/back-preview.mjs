// Vista previa de la textura trasera del mapa de dolor, sin navegador.
//
// Por qué existe: la espalda del cuerpo 3D se dibuja a mano en `src/pain/backAnatomy/` (calor,
// músculos, huesos y trazos en metros, formato en `src/pain/backSkin.ts`). Para colocar un trazo hay que ver dónde cae
// sobre el cuerpo, y abrir la app, girar el cuerpo y capturar es lento. Este guion rasteriza la
// textura tal cual la usa la app y le pone encima la silueta de la malla, en un PNG.
//
// Uso, desde `frontend/`:
//   node scripts/back-preview.mjs [--out fichero.png] [--scale N] [--crop x0,y0,x1,y1] [--front-side]
//   npm run preview:back -- [las mismas opciones]
//
// - `--out`: dónde escribir el PNG (por defecto, `emma-back-preview.png` en la carpeta temporal).
// - `--scale`: aumento entero, píxel a píxel (por defecto 1; la textura mide 512×1024).
// - `--crop`: recorte en metros del cuerpo, x0,y0,x1,y1 (p. ej. `-0.3,0.9,0.3,1.5` para la espalda
//   alta). Con un recorte, `--scale 3` o `4` deja ver el grosor de cada línea.
// - `--front-side`: sin voltear. Por defecto la imagen sale volteada para verse COMO EN LA APP DE
//   ESPALDAS: la izquierda del tripulante (+x) a la izquierda de la imagen.
// - `--regions`: encima, el contorno de cada músculo (magenta), su vientre si lo tiene (`shape`,
//   puntos magenta) y la cresta de cada hueso (naranja), en línea fina: para ver qué es cada cosa.
//
// Qué se ve:
// - la textura dentro de la silueta y, fuera, oscurecida: el calor, los músculos con su volumen y
//   su surco, los huesos con su sombra y los contornos y trazos (capas en `backSkin.ts`);
// - la silueta de la malla en blanco (todas las zonas proyectadas en x/y, de espaldas);
// - una rejilla cada 0,1 m (más marcada cada 0,5 m) y el eje x = 0, para leer coordenadas: cuenta
//   las rayas desde el eje y desde los pies (y = 0 es la raya marcada de abajo).
//
// Carga los módulos TypeScript con Vite (`runnerImport`), así que lee el dibujo actual sin compilar.

import { writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { crc32, deflateSync } from "node:zlib";
import { fileURLToPath } from "node:url";
import { runnerImport } from "vite";

const root = fileURLToPath(new URL("..", import.meta.url));

function option(name, fallback) {
  const at = process.argv.indexOf(`--${name}`);
  return at >= 0 ? process.argv[at + 1] : fallback;
}
const outPath = option("out", join(tmpdir(), "emma-back-preview.png"));
const scale = Math.round(Number(option("scale", "1")));
if (!Number.isFinite(scale) || scale < 1 || scale > 16) throw new Error("--scale espera un entero de 1 a 16");
const crop = option("crop", undefined)?.split(",").map(Number);
const flip = !process.argv.includes("--front-side");
const regions = process.argv.includes("--regions");
if (crop !== undefined && (crop.length !== 4 || crop.some((n) => !Number.isFinite(n)))) {
  throw new Error("--crop espera x0,y0,x1,y1 en metros");
}

const load = async (path) =>
  (await runnerImport(join(root, path), { root, configFile: false, logLevel: "error" })).module;
const skin = await load("src/pain/backSkin.ts");
const { BACK_ART } = await load("src/pain/backAnatomy/index.ts");
const { BODY, surfaceOf } = await load("src/pain/bodyModel.ts");

const projection = skin.BACK_PROJECTION;
const { width, height } = projection;
const started = performance.now();
const texture = skin.rasterizeBack(BACK_ART, projection);
const elapsed = performance.now() - started;
const step = skin.metersPerPixel(projection);
const toPixel = (x, y) => [x / step + width / 2, (projection.top - y) / step];

// Silueta: los triángulos de todas las zonas, proyectados en x/y, rellenos.
const mask = new Uint8Array(width * height);
for (const item of BODY) {
  const { positions, indices } = surfaceOf(item);
  for (let t = 0; t < indices.length; t += 3) {
    const corners = [0, 1, 2].map((k) => toPixel(positions[indices[t + k] * 3], positions[indices[t + k] * 3 + 1]));
    const xs = corners.map((p) => p[0]);
    const ys = corners.map((p) => p[1]);
    const [[ax, ay], [bx, by], [cx, cy]] = corners;
    const area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
    if (area === 0) continue;
    for (let row = Math.max(0, Math.floor(Math.min(...ys))); row <= Math.min(height - 1, Math.ceil(Math.max(...ys))); row += 1) {
      for (let column = Math.max(0, Math.floor(Math.min(...xs))); column <= Math.min(width - 1, Math.ceil(Math.max(...xs))); column += 1) {
        const px = column + 0.5;
        const py = row + 0.5;
        const w0 = ((bx - px) * (cy - py) - (by - py) * (cx - px)) / area;
        const w1 = ((cx - px) * (ay - py) - (cy - py) * (ax - px)) / area;
        if (w0 >= 0 && w1 >= 0 && w0 + w1 <= 1) mask[row * width + column] = 1;
      }
    }
  }
}

const image = new Uint8Array(width * height * 3);
for (let i = 0; i < width * height; i += 1) {
  const keep = mask[i] ? 1 : 0.22;
  for (let c = 0; c < 3; c += 1) image[i * 3 + c] = Math.round(texture[i * 4 + c] * keep);
}
const blend = (i, rgb, share) => {
  for (let c = 0; c < 3; c += 1) image[i * 3 + c] = Math.round(image[i * 3 + c] * (1 - share) + rgb[c] * share);
};
// Rejilla cada 0,1 m; más marcada cada 0,5 m y en el eje.
for (let k = -10; k <= 20; k += 1) {
  const strong = k % 5 === 0;
  const [column] = toPixel(k * 0.1, 0);
  const [, row] = toPixel(0, k * 0.1);
  const share = k === 0 ? 0.55 : strong ? 0.35 : 0.16;
  if (k >= -5 && k <= 5 && column >= 0 && column < width) {
    for (let r = 0; r < height; r += 1) blend(r * width + Math.floor(column), [255, 255, 255], share);
  }
  if (row >= 0 && row < height) {
    for (let c = 0; c < width; c += 1) blend(Math.floor(row) * width + c, [255, 255, 255], share);
  }
}
// Con `--regions`: el contorno de cada músculo en magenta, su vientre (`shape`) como puntos y la
// cresta de cada hueso en naranja, finos y encima de todo, para ver qué es cada cosa al colocarla.
if (regions) {
  const dot = (x, y, rgb) => {
    const [column, row] = toPixel(x, y).map(Math.floor);
    if (column >= 0 && column < width && row >= 0 && row < height) blend(row * width + column, rgb, 0.9);
  };
  const trace = (points, closed, rgb) => {
    for (const [x, y] of skin.smoothCurve(points, closed, step / 2)) dot(x, y, rgb);
  };
  for (const muscle of BACK_ART.muscles ?? []) {
    trace(muscle.outline, true, [255, 40, 220]);
    for (const [x, y] of muscle.shape ?? []) {
      for (const [dx, dy] of [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1]]) dot(x + dx * step, y + dy * step, [255, 40, 220]);
    }
  }
  for (const bone of BACK_ART.bones ?? []) trace(bone.points, bone.closed ?? false, [255, 150, 0]);
}

// Contorno de la silueta: píxel dentro con un vecino fuera.
for (let row = 1; row < height - 1; row += 1) {
  for (let column = 1; column < width - 1; column += 1) {
    const i = row * width + column;
    if (mask[i] && (!mask[i - 1] || !mask[i + 1] || !mask[i - width] || !mask[i + width])) blend(i, [255, 255, 255], 0.9);
  }
}

// Recorte (en metros) y volteo.
let [c0, r0, c1, r1] = [0, 0, width, height];
if (crop !== undefined) {
  const [xa, ya, xb, yb] = crop;
  const [pa, qa] = toPixel(Math.min(xa, xb), Math.max(ya, yb));
  const [pb, qb] = toPixel(Math.max(xa, xb), Math.min(ya, yb));
  [c0, r0, c1, r1] = [Math.max(0, Math.floor(pa)), Math.max(0, Math.floor(qa)), Math.min(width, Math.ceil(pb)), Math.min(height, Math.ceil(qb))];
  if (c1 <= c0 || r1 <= r0) {
    const span = `x de ${(-width / 2) * step} a ${(width / 2) * step} m, y de ${projection.bottom} a ${projection.top} m`;
    throw new Error(`--crop queda fuera de la textura (${span})`);
  }
}
const outWidth = (c1 - c0) * scale;
const outHeight = (r1 - r0) * scale;
const raw = Buffer.alloc((outWidth * 3 + 1) * outHeight);
for (let y = 0; y < outHeight; y += 1) {
  raw[y * (outWidth * 3 + 1)] = 0;
  const row = r0 + Math.floor(y / scale);
  for (let x = 0; x < outWidth; x += 1) {
    const local = Math.floor(x / scale);
    const column = flip ? c1 - 1 - local : c0 + local;
    const source = (row * width + column) * 3;
    raw.set(image.subarray(source, source + 3), y * (outWidth * 3 + 1) + 1 + x * 3);
  }
}

function chunk(type, data) {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body) >>> 0);
  return Buffer.concat([length, body, crc]);
}
const header = Buffer.alloc(13);
header.writeUInt32BE(outWidth, 0);
header.writeUInt32BE(outHeight, 4);
header[8] = 8; // bits por canal
header[9] = 2; // RGB
writeFileSync(
  outPath,
  Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]),
);
console.log(
  `${outPath} (${outWidth}×${outHeight}; ${BACK_ART.muscles?.length ?? 0} músculos, ${BACK_ART.bones?.length ?? 0} huesos, ` +
    `${BACK_ART.strokes.length} trazos, ${BACK_ART.heat.spots.length} manchas; ` +
    `rasterizado en ${Math.round(elapsed)} ms; ${flip ? "visto de espaldas, como en la app" : "sin voltear"})`,
);
