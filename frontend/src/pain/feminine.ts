/**
 * Variante femenina del cuerpo 3D de Dolor: el mismo cuerpo de `bodyModel.ts`, deformado.
 *
 * Por qué existe (petición del usuario, 2026-11-14): «respetar el estilo gráfico de los cuerpos 3D y 2D y
 * colores, pero también un avatar femenino». No es un modelo nuevo: las zonas, sus piezas, sus juntas y
 * sus centros (los que usa el backend, `pain_points.json`) son los del cuerpo de partida; solo se mueven
 * los vértices al dibujar. Así el clic cae en la misma zona y ninguna prueba de anclaje cambia.
 *
 * La deformación es **la misma** que la del 2D (`dashboard/referenceBodyFemale.py`), pasada a metros con la
 * proyección térmica (`thermalSkin.ts`): por altura, una escala lateral del tronco (hombros y cintura más
 * estrechos, caderas y muslos más anchos) que fuera del tronco se vuelve desplazamiento, para que los
 * brazos acompañen al costado. Como la piel se proyecta de frente desde la imagen 2D, los colores de la
 * variante femenina caen en su sitio sin calibrar nada: misma deformación a los dos lados.
 * Encima, el volumen que el 2D no tiene (es de frente): pecho hacia delante y algo de cadera detrás.
 *
 * Datos y funciones puras, sin three.js, como `bodyModel.ts`: se prueban sin navegador.
 */

import type { Surface, Vec3 } from "./bodyModel";
import { THERMAL_PROJECTION } from "./thermalSkin";

/** Píxeles 1x del render por metro (los de la proyección térmica). */
const PER_METER =
  (THERMAL_PROJECTION.bottomRow - THERMAL_PROJECTION.topRow) /
  (THERMAL_PROJECTION.topHeight - THERMAL_PROJECTION.bottomHeight);
/** El 2D se deforma sobre la ampliación ×4. */
const FINE = 4;

/** Fila del 4x → altura en metros. */
const heightOf = (row4: number) =>
  THERMAL_PROJECTION.bottomHeight + (THERMAL_PROJECTION.bottomRow - row4 / FINE) / PER_METER;
/** Píxeles del 4x → metros. */
const metersOf = (px4: number) => px4 / FINE / PER_METER;

/**
 * El perfil de `referenceBodyFemale.py` (`PROFILE`): fila del 4x, escala lateral del tronco y semiancho
 * del tronco en el 4x. Una prueba comprueba que sigue siendo el mismo que el del script.
 */
export const FEMININE_PROFILE: readonly (readonly [row4: number, scale: number, half4: number])[] = [
  [0, 0.95, 60],
  [150, 0.93, 62],
  [215, 0.9, 46],
  [245, 0.88, 92],
  [290, 0.86, 175],
  [360, 0.9, 180],
  [400, 0.92, 117],
  [450, 0.86, 104],
  [490, 0.85, 100],
  [540, 0.95, 100],
  [590, 1.08, 110],
  [640, 1.1, 121],
  [690, 1.08, 130],
  [780, 1.04, 120],
  [880, 1.0, 112],
  [1240, 1.0, 112],
];

/** Ancho, en el 4x, del tramo donde la escala del tronco pasa a desplazamiento (el del script). */
const BLEND4 = 24;
/** El script suaviza el perfil con una media de 31 filas del 4x; aquí, la misma anchura en metros. */
const SMOOTH = metersOf(15);

/** Nudos en metros, de abajo arriba (la altura crece al subir la fila). */
const KNOTS = FEMININE_PROFILE.map(([row, scale, half]) => ({ y: heightOf(row), scale, half: metersOf(half) })).sort(
  (a, b) => a.y - b.y,
);

function linear(y: number, key: "scale" | "half"): number {
  const first = KNOTS[0]!;
  const last = KNOTS[KNOTS.length - 1]!;
  if (y <= first.y) return first[key];
  if (y >= last.y) return last[key];
  for (let i = 1; i < KNOTS.length; i += 1) {
    const b = KNOTS[i]!;
    if (y > b.y) continue;
    const a = KNOTS[i - 1]!;
    return a[key] + ((b[key] - a[key]) * (y - a.y)) / (b.y - a.y);
  }
  return last[key];
}

/** Perfil a una altura, con la media móvil del script (cinco muestras en su ventana). */
export function profileAt(y: number): { scale: number; half: number } {
  let scale = 0;
  let half = 0;
  for (let k = -2; k <= 2; k += 1) {
    scale += linear(y + (k * SMOOTH) / 2, "scale");
    half += linear(y + (k * SMOOTH) / 2, "half");
  }
  return { scale: scale / 5, half: half / 5 };
}

const smoothstep01 = (t: number) => {
  const c = Math.min(1, Math.max(0, t));
  return c * c * (3 - 2 * c);
};

/** Dónde acaba lateralmente un punto a distancia `a` del eje: escala dentro del tronco, desplaza fuera. */
export function lateral(a: number, scale: number, half: number): number {
  const inner = a * scale;
  const outer = a + (scale - 1) * half;
  const t = smoothstep01((a - half) / metersOf(BLEND4) + 0.5);
  return (1 - t) * inner + t * outer;
}

/** Pecho: dos volúmenes hacia delante, en los mismos centros que las lupas del 2D (`BUSTS`). */
const BUST = { x: metersOf(56) * 0.92, y: heightOf(385), sigma: 0.05, depth: 0.045, lift: 0.012 };
/** La entrepierna del relieve de partida, que se aplana (la lupa que encoge del 2D, `BUSTS[2]`). */
const CROTCH = { y: heightOf(650), sx: 0.04, sy: 0.045, depth: 0.03 };
/** Cadera detrás: un poco más de volumen en los glúteos, en la altura de las caderas del perfil. */
const HIPS = { y: heightOf(640), sigma: 0.07, depth: 0.018 };

/** Un vértice del cuerpo de partida, en su sitio de la variante femenina. */
export function feminize([x, y, z]: Vec3): Vec3 {
  const { scale, half } = profileAt(y);
  const nx = Math.sign(x) * lateral(Math.abs(x), scale, half);
  let nz = z;
  let ny = y;
  // Solo el tronco por delante (lo que queda dentro del semiancho), ni brazos ni espalda.
  if (z > 0 && Math.abs(x) < half * 1.05) {
    const bx = Math.abs(nx) - BUST.x;
    const by = y - BUST.y;
    const w = Math.exp(-(bx * bx + by * by) / (2 * BUST.sigma * BUST.sigma));
    // El volumen cae algo: más abajo empuja más que arriba (la parte superior sale casi plana).
    const sag = by < 0 ? 1 : Math.exp(-(by * by) / (2 * (BUST.sigma * 0.7) ** 2));
    nz += BUST.depth * w * sag * smoothstep01(z / 0.06);
    ny -= BUST.lift * w * sag * smoothstep01(z / 0.06) * 0.3;
  }
  // La entrepierna, lisa: el relieve de partida marca un bulto que en el 2D femenino ya se recogió.
  if (z > 0) {
    const cy = y - CROTCH.y;
    nz -= CROTCH.depth * Math.exp(-(x * x) / (2 * CROTCH.sx ** 2) - (cy * cy) / (2 * CROTCH.sy ** 2));
  }
  if (z < 0 && Math.abs(x) < half * 1.05) {
    const hy = y - HIPS.y;
    nz -= HIPS.depth * Math.exp(-(hy * hy) / (2 * HIPS.sigma * HIPS.sigma)) * smoothstep01(-z / 0.06);
  }
  return [nx, ny, nz];
}

/** Una superficie deformada (copia; la del cuerpo de partida, que `surfaceOf` guarda, no se toca). */
export function feminizeSurface(surface: Surface): Surface {
  const positions = new Float32Array(surface.positions.length);
  for (let i = 0; i < positions.length; i += 3) {
    const [x, y, z] = feminize([surface.positions[i]!, surface.positions[i + 1]!, surface.positions[i + 2]!]);
    positions[i] = x;
    positions[i + 1] = y;
    positions[i + 2] = z;
  }
  return { positions, normals: surface.normals, indices: surface.indices };
}

/**
 * Media melena del 3D, la del 2D (`add_hair` de `referenceBodyFemale.py`): una capa sobre el cráneo que baja
 * recta por los lados y la nuca hasta la mandíbula, abierta delante en la cara, con flequillo ladeado. No
 * es una zona: no se toca (el clic la atraviesa y cae en la cabeza) y no la ve el backend. Sigue el
 * contorno de la cabeza del cuerpo de partida con un hueco de 1-2 cm y lleva la misma deformación.
 */
export const HAIR = {
  /** Altura más baja de la melena, junto a la cara (la mandíbula, la fila 236 del 4x del 2D); en la nuca, 3 cm más arriba. */
  bottom: 1.47,
  /** Por debajo, la melena cae recta: el contorno de la cabeza a esta altura. */
  straightBelow: 1.6,
  /** Raya del flequillo, en grados del contorno del tronco (90 es delante; más, hacia la derecha del tripulante). */
  part: 100,
  /** Media abertura de la cara, en grados. */
  faceHalf: 44,
  /** Línea del pelo en la frente, en el centro de la cara. */
  hairline: 1.675,
} as const;

type HeadPoint = (height: number, degrees: number) => Vec3;

/** La melena como superficie, a partir del contorno de la cabeza (`surfacePoint("column", …)`). */
export function hairSurface(head: HeadPoint, rows = 46, step = 5): Surface & { cavity: Float32Array } {
  // Coronilla: una cúpula que cierra en un punto 2 cm por encima del cráneo (sin «chimenea» abierta).
  const top = 1.755;
  const domeFrom = 1.7;
  const columns = Math.round(360 / step);
  const positions: number[] = [];
  const keep: boolean[] = [];
  const strands: number[] = [];
  for (let r = 0; r <= rows; r += 1) {
    for (let c = 0; c < columns; c += 1) {
      const deg = c * step;
      const rad = (deg * Math.PI) / 180;
      const behind = Math.max(0, -Math.sin(rad));
      const sides = Math.abs(Math.cos(rad));
      // El bajo no es un corte recto (se leía como un casco): melena en ángulo, más larga junto a la cara
      // que en la nuca, y con las puntas a capas (una ondulación suave de medio centímetro).
      const bottom = HAIR.bottom + 0.03 * behind ** 1.5 + 0.005 * Math.sin(rad * 14) * (1 - 0.5 * behind);
      const y = top - ((top - bottom) * r) / rows;
      const yc = Math.max(y, HAIR.straightBelow);
      const cz = (head(yc, 90)[2] + head(yc, 270)[2]) / 2;
      const p = head(Math.min(yc, domeFrom), deg);
      const dx = p[0];
      const dz = p[2] - cz;
      const len = Math.hypot(dx, dz) || 1e-6;
      // Hueco sobre el cráneo: fino arriba, más volumen a los lados y en la nuca; las puntas se recogen
      // hacia dentro, como un pelo que se curva al final.
      const tuck = Math.max(0, (HAIR.straightBelow - y) / (HAIR.straightBelow - bottom)) ** 3;
      const off = 0.012 + 0.022 * sides ** 1.5 + 0.016 * behind - 0.016 * tuck;
      const dome = y > domeFrom ? Math.sqrt(Math.max(0, 1 - ((y - domeFrom) / (top - domeFrom)) ** 2)) : 1;
      const radius = (len + off) * dome;
      positions.push((dx / len) * radius, y, cz + (dz / len) * radius);
      // Mechones: surcos suaves que bajan desde la raya y giran un poco hacia la nuca, como las líneas de
      // los mechones del 2D. Van por el atributo de cavidad, la misma sombra de surco que el músculo.
      const wave = Math.sin(rad * 36 + (top - y) * 22 * Math.sign(Math.cos(rad) || 1));
      strands.push(y < 1.74 ? 0.45 * Math.max(0, wave) ** 2 - 0.15 * Math.max(0, -wave) ** 4 : 0);
      const fromFace = Math.abs(deg - 90);
      const fromPart = (deg - HAIR.part) / HAIR.faceHalf;
      // Flequillo ladeado: la línea baja hacia el lado contrario a la raya.
      const line = HAIR.hairline - 0.05 * (fromFace / HAIR.faceHalf) ** 2 - 0.018 * Math.max(0, -fromPart);
      keep.push(!(fromFace < HAIR.faceHalf && y < line) && !(fromFace < HAIR.faceHalf + 14 && y < 1.53));
    }
  }
  const indices: number[] = [];
  const at = (r: number, c: number) => r * columns + (c % columns);
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < columns; c += 1) {
      const a = at(r, c);
      const b = at(r, c + 1);
      const d = at(r + 1, c);
      const e = at(r + 1, c + 1);
      if (keep[a] && keep[b] && keep[d]) indices.push(a, d, b);
      if (keep[b] && keep[d] && keep[e]) indices.push(b, d, e);
    }
  }
  const moved = new Float32Array(positions.length);
  for (let i = 0; i < positions.length; i += 3) {
    const [x, y, z] = feminize([positions[i]!, positions[i + 1]!, positions[i + 2]!]);
    moved[i] = x;
    moved[i + 1] = y;
    moved[i + 2] = z;
  }
  // Normales por vértice (suma de las caras), orientadas hacia fuera del eje de la cabeza.
  const normals = new Float32Array(moved.length);
  for (let t = 0; t < indices.length; t += 3) {
    const [i, j, k] = [indices[t]! * 3, indices[t + 1]! * 3, indices[t + 2]! * 3];
    const u = [moved[j]! - moved[i]!, moved[j + 1]! - moved[i + 1]!, moved[j + 2]! - moved[i + 2]!];
    const v = [moved[k]! - moved[i]!, moved[k + 1]! - moved[i + 1]!, moved[k + 2]! - moved[i + 2]!];
    const n = [u[1]! * v[2]! - u[2]! * v[1]!, u[2]! * v[0]! - u[0]! * v[2]!, u[0]! * v[1]! - u[1]! * v[0]!];
    for (const index of [i, j, k]) for (let q = 0; q < 3; q += 1) normals[index + q]! += n[q]!;
  }
  let outward = 0;
  for (let i = 0; i < normals.length; i += 3) outward += normals[i]! * moved[i]! + normals[i + 2]! * moved[i + 2]!;
  const sign = outward < 0 ? -1 : 1;
  if (sign < 0) for (let t = 0; t < indices.length; t += 3) [indices[t + 1], indices[t + 2]] = [indices[t + 2]!, indices[t + 1]!];
  for (let i = 0; i < normals.length; i += 3) {
    const len = Math.hypot(normals[i]!, normals[i + 1]!, normals[i + 2]!) || 1;
    for (let q = 0; q < 3; q += 1) normals[i + q] = (sign * normals[i + q]!) / len;
  }
  return { positions: moved, normals, indices: Uint32Array.from(indices), cavity: Float32Array.from(strands) };
}
