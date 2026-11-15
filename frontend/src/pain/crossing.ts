/**
 * Luz y sombra continuas donde se cruzan dos piezas del cuerpo.
 *
 * Por qué existe (hombro B, 2026-11-10). Ellande: «la fusión de hombro con el tronco no está bien
 * hecha; colores bien, pero los hombros con el tronco siguen viéndose de quita y pon». El cuerpo
 * no es una piel sola: son piezas (el tronco con el cuello y la cabeza, cada brazo, cada pierna, cada
 * pie, cada dedo, cada oreja) que se meten unas en otras sin compartir vértices. En la línea donde se cruzan, cada tubo trae su
 * normal, que puede diferir 90° o más de la del otro: la luz, el contorno Fresnel y el paso del
 * frente a la espalda de la textura cambian de golpe, y el brazo se lee encajado en el tronco como
 * el de un muñeco. La cavidad (`cavity.ts`) tampoco lo ve: suelda por posición y aquí no hay nada
 * que soldar, así que el pliegue de la axila o de la ingle no hace sombra.
 *
 * Qué se hace, una sola vez al montar el mapa:
 * 1. Piezas: los vértices soldados (`weldSurfaces`) se agrupan por conectividad de la malla. Cada
 *    tubo sale como una pieza aunque esté repartido en varias zonas (comparten borde), y dos tubos
 *    que se cruzan salen como dos.
 * 2. Para cada vértice, en una rejilla espacial, el vértice más cercano de otra
 *    pieza y la normal media de esa pieza a su alrededor. Con su normal se sabe si el vértice queda
 *    dentro de la otra pieza (escondido).
 * 3. Distancia al cruce: desde un vértice que queda fuera, el vértice escondido más cercano de su
 *    misma pieza (escondido en la misma pieza vecina), interpolada al punto donde cambia de lado. Es
 *    lo que separa un cruce de verdad de dos piezas que solo pasan cerca, como un dedo junto a otro
 *    o el brazo junto al costado: sin vértices escondidos cerca, no hay cruce y no se toca nada.
 * 4. En la franja del cruce, la normal se mezcla con la de la pieza vecina, con un peso que vale ½
 *    en la línea del cruce y cae a 0 en el ancho de la franja: en la línea las dos piezas llevan la
 *    misma normal, y la luz pasa de una a otra sin corte. Lejos, la normal es exactamente la de
 *    antes. El ancho es `REACH`, salvo si una de las dos piezas es pequeña (`SIZE_SHARE`).
 * 5. El pliegue: un valor en [0, 1] que crece con el ángulo entre las dos piezas y cae con la
 *    distancia al cruce, para que la cavidad lo oscurezca como un surco ancho y tenue
 *    (`creaseCavities`), no como una raya.
 *
 * Coste lineal en el número de vértices: cada uno mira las 125 celdas de medio `REACH` de su
 * alrededor, y en ellas solo los vértices de las otras piezas. No toca posiciones, índices ni zonas: el clic, el `<select>` y el
 * raycast ven la misma malla.
 */

import { weldSurfaces, type CavitySurface, type Welded } from "./cavity";

/**
 * Ancho de la franja del cruce, en metros: hasta aquí llega la mezcla de normales. Cuatro y no dos
 * o tres centímetros (hombro B, 2026-11-10): con tres, el arco claro que dibujaba la cabeza del
 * deltoides sobre el pecho se quedaba a medias en la vista de tres cuartos; el deltoides es una
 * curva ancha y su paso al tronco también.
 */
export const REACH = 0.04;
/**
 * Parte del tamaño de la pieza más pequeña del cruce (su medida intermedia) que puede ocupar la
 * franja. Con una oreja o un dedo, cuatro centímetros de franja teñían de su normal media cabeza o
 * media palma: un halo alrededor de la oreja y la palma ahuecada. Así, unos dos centímetros en la
 * oreja y en los dedos, y los cuatro enteros en el hombro y la cadera.
 */
const SIZE_SHARE = 0.5;
/**
 * Margen para dar un vértice por escondido en la otra pieza, en metros. Dos trozos de un mismo
 * tubo que no soldaran (si los hubiera) se continúan el uno al otro y, con la curvatura, el primer
 * vértice del otro queda unas décimas de milímetro por debajo de su plano tangente: eso no es un
 * cruce.
 */
const INSIDE = 5e-4;
/**
 * Por debajo de este coseno entre las dos normales, la mezcla se apaga: dos normales casi opuestas
 * se anulan al sumarse y la dirección que sale no significa nada. En la axila el ángulo es muy
 * cerrado (coseno ≈ −0,9) y sí se mezcla: la normal del fondo del pliegue mira hacia fuera de él.
 */
const OPPOSED_FROM = -0.985;
const OPPOSED_TO = -0.93;
/** Cuánto ahonda el pliegue la cavidad, como mucho (la cavidad va de −1 a 1). */
const CREASE_DEPTH = 0.55;

/** Paso suave de 0 (en `from`) a 1 (en `to`), sin pendiente en los extremos. */
export function smoothstep(from: number, to: number, value: number): number {
  const t = Math.max(0, Math.min(1, (value - from) / (to - from)));
  return t * t * (3 - 2 * t);
}

/** Resultado por superficie, en el orden de sus vértices. */
export interface Crossings {
  /** Normales con la franja de cada cruce mezclada; fuera de ella, las de entrada tal cual. */
  normals: Float32Array[];
  /** Hondura del pliegue en [0, 1]: 0 lejos de todo cruce. */
  crease: Float32Array[];
}

/** Las piezas: componentes conexas de la malla soldada (unión por rango con compresión). */
function piecesOf(
  surfaces: readonly CavitySurface[],
  welded: readonly Int32Array[],
  total: number,
): { piece: Int32Array; count: number } {
  const parent = new Int32Array(total);
  for (let id = 0; id < total; id += 1) parent[id] = id;
  const root = (id: number): number => {
    let r = id;
    while (parent[r] !== r) r = parent[r]!;
    let k = id;
    while (parent[k] !== r) {
      const next = parent[k]!;
      parent[k] = r;
      k = next;
    }
    return r;
  };
  const join = (a: number, b: number) => {
    const ra = root(a);
    const rb = root(b);
    if (ra !== rb) parent[Math.max(ra, rb)] = Math.min(ra, rb);
  };
  surfaces.forEach((surface, s) => {
    const map = welded[s]!;
    for (let t = 0; t + 2 < surface.indices.length; t += 3) {
      const a = map[surface.indices[t]!]!;
      join(a, map[surface.indices[t + 1]!]!);
      join(a, map[surface.indices[t + 2]!]!);
    }
  });
  // Numeradas de 0 en adelante, para poder llevar una suma por pieza en un arreglo.
  const piece = new Int32Array(total);
  const number = new Map<number, number>();
  for (let id = 0; id < total; id += 1) {
    const r = root(id);
    let n = number.get(r);
    if (n === undefined) {
      n = number.size;
      number.set(r, n);
    }
    piece[id] = n;
  }
  return { piece, count: number.size };
}

/**
 * Mezcla las normales en la franja donde se cruzan dos piezas y mide el pliegue. Las superficies
 * de entrada no se tocan. `weld` es la soldadura de esas mismas superficies, si ya se tiene (la
 * cavidad la hace igual): así no se suelda dos veces.
 */
export function blendCrossings(
  surfaces: readonly CavitySurface[],
  weld: Welded = weldSurfaces(surfaces),
): Crossings {
  const { welded, px, py, pz, nx, ny, nz, oriented, total } = weld;
  const { piece, count: pieceCount } = piecesOf(surfaces, welded, total);
  // Tamaño de cada pieza: la medida intermedia de su caja (el grosor de un dedo o lo ancho de una
  // oreja, no lo largo).
  const low = new Float64Array(pieceCount * 3).fill(Infinity);
  const high = new Float64Array(pieceCount * 3).fill(-Infinity);
  for (let id = 0; id < total; id += 1) {
    const at = piece[id]! * 3;
    low[at] = Math.min(low[at]!, px[id]!);
    low[at + 1] = Math.min(low[at + 1]!, py[id]!);
    low[at + 2] = Math.min(low[at + 2]!, pz[id]!);
    high[at] = Math.max(high[at]!, px[id]!);
    high[at + 1] = Math.max(high[at + 1]!, py[id]!);
    high[at + 2] = Math.max(high[at + 2]!, pz[id]!);
  }
  const size = new Float64Array(pieceCount);
  for (let n = 0; n < pieceCount; n += 1) {
    const extents = [0, 1, 2].map((axis) => high[n * 3 + axis]! - low[n * 3 + axis]!).sort((a, b) => a - b);
    size[n] = extents[1]!;
  }

  // Rejilla densa de celdas de medio REACH: todo lo que queda a menos de REACH de un vértice cae en
  // las 5 × 5 × 5 celdas de su alrededor. Con celdas de un REACH entero (3 × 3 × 3) se recorría casi
  // el doble de volumen para nada. En cada celda, los vértices van ordenados por pieza, y `runEnd`
  // dice dónde acaba el tramo de la misma pieza: así se salta de golpe el de la propia.
  const cell = REACH / 2;
  // La caja de todo, de las cajas de las piezas.
  let minX = Infinity;
  let minY = Infinity;
  let minZ = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  let maxZ = -Infinity;
  for (let n = 0; n < pieceCount; n += 1) {
    minX = Math.min(minX, low[n * 3]!);
    minY = Math.min(minY, low[n * 3 + 1]!);
    minZ = Math.min(minZ, low[n * 3 + 2]!);
    maxX = Math.max(maxX, high[n * 3]!);
    maxY = Math.max(maxY, high[n * 3 + 1]!);
    maxZ = Math.max(maxZ, high[n * 3 + 2]!);
  }
  const dimX = total > 0 ? Math.floor((maxX - minX) / cell) + 1 : 0;
  const dimY = total > 0 ? Math.floor((maxY - minY) / cell) + 1 : 0;
  const dimZ = total > 0 ? Math.floor((maxZ - minZ) / cell) + 1 : 0;
  const cellCount = dimX * dimY * dimZ;
  const cellX = new Int32Array(total);
  const cellY = new Int32Array(total);
  const cellZ = new Int32Array(total);
  const cellOf = new Int32Array(total);
  for (let id = 0; id < total; id += 1) {
    cellX[id] = Math.floor((px[id]! - minX) / cell);
    cellY[id] = Math.floor((py[id]! - minY) / cell);
    cellZ[id] = Math.floor((pz[id]! - minZ) / cell);
    cellOf[id] = (cellX[id]! * dimY + cellY[id]!) * dimZ + cellZ[id]!;
  }
  // Primero por pieza y luego, estable, por celda: dentro de cada celda quedan agrupados por pieza.
  const byPiece = new Int32Array(pieceCount + 1);
  for (let id = 0; id < total; id += 1) byPiece[piece[id]! + 1]! += 1;
  for (let n = 0; n < pieceCount; n += 1) byPiece[n + 1]! += byPiece[n]!;
  const ordered = new Int32Array(total);
  for (let id = 0; id < total; id += 1) {
    ordered[byPiece[piece[id]!]!] = id;
    byPiece[piece[id]!]! += 1;
  }
  const begin = new Int32Array(cellCount + 1);
  for (let id = 0; id < total; id += 1) begin[cellOf[id]! + 1]! += 1;
  for (let c = 0; c < cellCount; c += 1) begin[c + 1]! += begin[c]!;
  const members = new Int32Array(total);
  const fill = begin.slice(0, cellCount);
  for (const id of ordered) {
    members[fill[cellOf[id]!]!] = id;
    fill[cellOf[id]!]! += 1;
  }
  const runEnd = new Int32Array(total);
  // Si en la celda hay una sola pieza, cuál; −1 si hay varias; −2 si está vacía.
  const only = new Int32Array(cellCount).fill(-2);
  for (let c = 0; c < cellCount; c += 1) {
    const first = begin[c]!;
    const last = begin[c + 1]!;
    for (let k = last - 1; k >= first; k -= 1) {
      runEnd[k] = k + 1 < last && piece[members[k + 1]!] === piece[members[k]!] ? runEnd[k + 1]! : k + 1;
    }
    if (last > first) only[c] = runEnd[first] === last ? piece[members[first]!]! : -1;
  }
  // Las celdas no vacías alrededor de un vértice, en `around`; devuelve cuántas son.
  const around = new Int32Array(125);
  const cellsAround = (id: number): number => {
    let count = 0;
    for (let x = Math.max(0, cellX[id]! - 2); x <= Math.min(dimX - 1, cellX[id]! + 2); x += 1) {
      for (let y = Math.max(0, cellY[id]! - 2); y <= Math.min(dimY - 1, cellY[id]! + 2); y += 1) {
        const row = (x * dimY + y) * dimZ;
        for (let z = Math.max(0, cellZ[id]! - 2); z <= Math.min(dimZ - 1, cellZ[id]! + 2); z += 1) {
          if (only[row + z] !== -2) {
            around[count] = row + z;
            count += 1;
          }
        }
      }
    }
    return count;
  };

  // 2. Pieza vecina más cercana, normal media de esa pieza alrededor y lado (dentro o fuera).
  const target = new Int32Array(total).fill(-1);
  const side = new Float32Array(total);
  const ox = new Float32Array(total);
  const oy = new Float32Array(total);
  const oz = new Float32Array(total);
  const reach2 = REACH * REACH;
  const sums = new Float64Array(pieceCount * 3);
  const touched: number[] = [];
  for (let i = 0; i < total; i += 1) {
    if (oriented[i] !== 1) continue;
    const own = piece[i]!;
    const count = cellsAround(i);
    // En una pasada: el vértice más cercano de otra pieza y, por cada pieza vecina, su normal media
    // con un peso que cae suave hasta REACH (un campo sin saltos de un vértice al siguiente, aunque
    // la rejilla de la otra pieza sea más gruesa). Después se queda la de la pieza más cercana.
    let best = -1;
    let bestD2 = reach2;
    for (let n = 0; n < count; n += 1) {
      const c = around[n]!;
      if (only[c] === own) continue;
      for (let k = begin[c]!; k < begin[c + 1]!; ) {
        const j = members[k]!;
        if (piece[j] === own) {
          k = runEnd[k]!;
          continue;
        }
        k += 1;
        if (oriented[j] !== 1) continue;
        const dx = px[i]! - px[j]!;
        const dy = py[i]! - py[j]!;
        const dz = pz[i]! - pz[j]!;
        const d2 = dx * dx + dy * dy + dz * dz;
        if (d2 >= reach2) continue;
        if (d2 < bestD2) {
          bestD2 = d2;
          best = j;
        }
        const q = 1 - d2 / reach2;
        const weight = q * q;
        const at = piece[j]! * 3;
        if (sums[at] === 0 && sums[at + 1] === 0 && sums[at + 2] === 0) touched.push(at);
        sums[at]! += weight * nx[j]!;
        sums[at + 1]! += weight * ny[j]!;
        sums[at + 2]! += weight * nz[j]!;
      }
    }
    if (best < 0) continue;
    const other = piece[best]!;
    const sx = sums[other * 3]!;
    const sy = sums[other * 3 + 1]!;
    const sz = sums[other * 3 + 2]!;
    for (const at of touched) sums.fill(0, at, at + 3);
    touched.length = 0;
    const length = Math.hypot(sx, sy, sz);
    if (length < 1e-6) continue;
    target[i] = other;
    ox[i] = sx / length;
    oy[i] = sy / length;
    oz[i] = sz / length;
    side[i] =
      (px[i]! - px[best]!) * nx[best]! + (py[i]! - py[best]!) * ny[best]! + (pz[i]! - pz[best]!) * nz[best]!;
  }

  // 3. Distancia al cruce: 0 en lo escondido; fuera, hasta el escondido más cercano de la misma
  // pieza en la misma vecina, interpolada donde el lado cambia de signo. Solo se miran las celdas
  // con algo escondido, que son pocas: las de los cruces.
  const hidden = new Uint8Array(cellCount);
  for (let id = 0; id < total; id += 1) {
    if (target[id]! >= 0 && side[id]! < -INSIDE) hidden[cellOf[id]!] = 1;
  }
  const distance = new Float32Array(total).fill(Infinity);
  for (let i = 0; i < total; i += 1) {
    const other = target[i]!;
    if (other < 0) continue;
    if (side[i]! < -INSIDE) {
      distance[i] = 0;
      continue;
    }
    const own = piece[i]!;
    const outside = Math.max(0, side[i]!);
    let nearest = Infinity;
    const count = cellsAround(i);
    for (let n = 0; n < count; n += 1) {
      const c = around[n]!;
      if (hidden[c] !== 1 || (only[c] !== -1 && only[c] !== own)) continue;
      for (let k = begin[c]!; k < begin[c + 1]!; ) {
        const j = members[k]!;
        if (piece[j] !== own) {
          k = runEnd[k]!;
          continue;
        }
        k += 1;
        if (target[j] !== other || side[j]! >= -INSIDE) continue;
        const dx = px[i]! - px[j]!;
        const dy = py[i]! - py[j]!;
        const dz = pz[i]! - pz[j]!;
        const along = Math.sqrt(dx * dx + dy * dy + dz * dz);
        const crossing = (along * outside) / (outside - side[j]!);
        if (crossing < nearest) nearest = crossing;
      }
    }
    distance[i] = nearest;
  }

  // 4 y 5. Mezcla y pliegue por vértice de cada superficie: lejos de un cruce, la normal de
  // entrada exacta (la de cada copia, no la media soldada).
  const normals: Float32Array[] = [];
  const crease: Float32Array[] = [];
  surfaces.forEach((surface, s) => {
    const map = welded[s]!;
    const out = Float32Array.from(surface.normals);
    const fold = new Float32Array(map.length);
    for (let v = 0; v < map.length; v += 1) {
      const id = map[v]!;
      if (target[id]! < 0) continue;
      const reach = Math.min(REACH, SIZE_SHARE * Math.min(size[piece[id]!]!, size[target[id]!]!));
      const near = 1 - smoothstep(0, reach, distance[id]!);
      if (near <= 0) continue;
      const ax = surface.normals[v * 3]!;
      const ay = surface.normals[v * 3 + 1]!;
      const az = surface.normals[v * 3 + 2]!;
      const cosine = ax * ox[id]! + ay * oy[id]! + az * oz[id]!;
      const usable = smoothstep(OPPOSED_FROM, OPPOSED_TO, cosine);
      const weight = 0.5 * near * usable;
      const bx = (1 - weight) * ax + weight * ox[id]!;
      const by = (1 - weight) * ay + weight * oy[id]!;
      const bz = (1 - weight) * az + weight * oz[id]!;
      const length = Math.hypot(bx, by, bz);
      if (length > 1e-6) {
        out[v * 3] = bx / length;
        out[v * 3 + 1] = by / length;
        out[v * 3 + 2] = bz / length;
      }
      // Pliegue: nada si las dos piezas siguen la misma dirección, todo si se doblan del todo.
      fold[v] = near * usable * Math.max(0, Math.min(1, (1 - cosine) / 2));
    }
    normals.push(out);
    crease.push(fold);
  });
  return { normals, crease };
}

/**
 * Ahonda la cavidad con el pliegue de los cruces, en el sitio: un surco ancho (toda la franja) y
 * tenue (como mucho `CREASE_DEPTH`), recortado a [−1, 1] como el resto de la cavidad.
 */
export function creaseCavities(values: readonly Float32Array[], crease: readonly Float32Array[]): void {
  values.forEach((out, s) => {
    const fold = crease[s]!;
    for (let v = 0; v < out.length; v += 1) {
      if (fold[v]! > 0) out[v] = Math.min(1, out[v]! + CREASE_DEPTH * fold[v]!);
    }
  });
}
