import type { BodyPixels } from "../dashboard/referenceBody.generated";
import { BODY_HEIGHT } from "./bodyModel";

/**
 * Los colores de cámara térmica del cuerpo de «Inicio» sobre el cuerpo 3D (decisión del usuario,
 * 2026-11-10: «Todo, colores incluidos»). El cuerpo de «Inicio» es un render 2D de frente; aquí se
 * proyecta tal cual sobre la malla, de frente: cada punto toma el color del píxel que tiene delante
 * en la imagen, según su x y su altura. Es adorno, como el de «Inicio» (§2.5 de
 * `compliance/hmi-state-of-the-art.md`): el verde, el amarillo y el rojo del tórax no dicen nada.
 * Lo que sí es dato —la zona marcada y la del puntero— se pinta aparte, con la paleta.
 *
 * Este módulo es puro (sin WebGL ni lienzo) para poder probarlo: la proyección y la dilatación.
 * Los píxeles se importan aparte y perezosos (`BodyMap.tsx`): son ~1,5 MB que la consola no debe
 * cargar hasta que se abre el mapa.
 */

/**
 * Correspondencia de la imagen con el cuerpo, medida sobre la silueta de `BODY_ONE`. Coordenadas de
 * la imagen continuas: el píxel de la columna `c` va de `c` a `c + 1` y su centro es `c + 0,5`.
 * Está en una constante para retocarla cuando cambie la forma del cuerpo 3D, sin tocar el código.
 */
export const THERMAL_PROJECTION = {
  /** Tamaño de `BODY_ONE` (`BODY_W`, `BODY_H`); la prueba comprueba que casan. */
  width: 152,
  height: 310,
  /** Centro de la fila 9, la coronilla. */
  topRow: 9.5,
  /** La coronilla del render a la altura de la del cuerpo 3D: si esa cambia, la imagen la sigue. */
  topHeight: BODY_HEIGHT,
  /** Centro de la fila 301, la planta de los pies. */
  bottomRow: 301.5,
  bottomHeight: 0,
  /** Columna del eje del cuerpo (x = 0): la 73, no la 76 del centro de la imagen. */
  centerColumn: 73.5,
  /**
   * Píxeles del borde de la silueta que no cuentan al dilatar: el render tiene un contorno claro de
   * unos 3 px, y si se estirara hacia fuera, lo que cae fuera de la silueta 2D saldría blanquecino.
   * El contorno luminoso del 3D ya lo pone el Fresnel.
   */
  inset: 3,
  /** Radio, en píxeles, de la copia borrosa para los costados y la espalda (`blur`). */
  blurRadius: 4,
} as const;

export type ThermalProjection = { readonly [K in keyof typeof THERMAL_PROJECTION]: number };

/** La proyección como dos rectas: u = u0 + uScale·x y v = v0 + vScale·y (lo que usa el sombreador). */
export interface ThermalCoefficients {
  u0: number;
  uScale: number;
  v0: number;
  vScale: number;
}

export function thermalCoefficients(projection: ThermalProjection = THERMAL_PROJECTION): ThermalCoefficients {
  const { width, height, topRow, topHeight, bottomRow, bottomHeight, centerColumn } = projection;
  // Píxeles por metro, el mismo en las dos direcciones: la imagen no está estirada.
  const perMeter = (bottomRow - topRow) / (topHeight - bottomHeight);
  // La izquierda de la imagen es la derecha del tripulante (−x), como en el 3D visto de frente.
  // v = 0 es la fila de arriba: la textura se sube sin voltear.
  return {
    u0: centerColumn / width,
    uScale: perMeter / width,
    v0: (bottomRow + bottomHeight * perMeter) / height,
    vScale: -perMeter / height,
  };
}

/** De un punto del cuerpo (x lateral, y altura, en m) a la coordenada (u, v) de la imagen, en [0, 1]. */
export function projectThermal(
  x: number,
  y: number,
  projection: ThermalProjection = THERMAL_PROJECTION,
): [u: number, v: number] {
  const { u0, uScale, v0, vScale } = thermalCoefficients(projection);
  return [u0 + uScale * x, v0 + vScale * y];
}

/**
 * Los píxeles de `BODY_ONE` en RGBA (alfa 0 o 255): la misma lectura que `paintBody` de
 * `ReferenceBody.tsx`, pero sin lienzo. Devuelve el tamaño real (con `scale`), que es el que vale
 * para dilatar y para la textura.
 */
export function decodeBody(
  pixels: BodyPixels,
  width: number,
  height: number,
): { data: Uint8Array; width: number; height: number } {
  const scaledWidth = width * pixels.scale;
  const scaledHeight = height * pixels.scale;
  const data = new Uint8Array(scaledWidth * scaledHeight * 4);
  const rgb = pixels.palette.map((hex) => [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ]);
  pixels.rows.forEach((row, y) => {
    if (!row) return;
    const bar = row.indexOf("|");
    const runs = bar >= 0 ? row.slice(bar + 1) : row;
    let x = bar >= 0 ? Number(row.slice(0, bar)) : 0;
    for (const token of runs.split(",")) {
      const [index, length] = token.split(":");
      const count = Number(length);
      const color = index === "-" ? undefined : rgb[Number(index)];
      if (color !== undefined) {
        for (let k = 0; k < count; k += 1) {
          const offset = (y * scaledWidth + x + k) * 4;
          data[offset] = color[0]!;
          data[offset + 1] = color[1]!;
          data[offset + 2] = color[2]!;
          data[offset + 3] = 255;
        }
      }
      x += count;
    }
  });
  return { data, width: scaledWidth, height: scaledHeight };
}

/**
 * Rellena lo transparente con el color del píxel opaco más cercano (búsqueda en anchura desde todos
 * los opacos a la vez). Hace falta porque el cuerpo 3D no casa píxel a píxel con la silueta 2D: lo
 * que se sale de ella (un brazo algo más abierto, el costado) tomaría negro o transparente, y así
 * toma el color del borde más próximo. `inset` descarta antes como fuente los píxeles opacos a menos
 * de ese número de píxeles de uno transparente (el contorno claro del render), que se rellenan
 * también desde dentro. Devuelve una copia, opaca entera.
 */
export function dilate(rgba: Uint8Array, width: number, height: number, inset = 0): Uint8Array {
  const total = width * height;
  const out = new Uint8Array(rgba);
  // Fuente: opaco y lejos del borde. Se mide la distancia al transparente con otra anchura.
  const toEdge = new Int32Array(total).fill(-1);
  const queue = new Int32Array(total);
  let head = 0;
  let tail = 0;
  for (let i = 0; i < total; i += 1) {
    if (rgba[i * 4 + 3] === 0) {
      toEdge[i] = 0;
      queue[tail++] = i;
    }
  }
  if (tail === 0 || tail === total) {
    // Todo opaco: nada que rellenar. Todo transparente: no hay de dónde sacar color.
    for (let i = 0; i < total; i += 1) out[i * 4 + 3] = 255;
    return out;
  }
  const neighbours = (i: number, visit: (j: number) => void) => {
    const x = i % width;
    if (x > 0) visit(i - 1);
    if (x < width - 1) visit(i + 1);
    if (i >= width) visit(i - width);
    if (i < total - width) visit(i + width);
  };
  while (head < tail) {
    const i = queue[head++]!;
    if (toEdge[i]! >= inset) continue;
    neighbours(i, (j) => {
      if (toEdge[j] === -1) {
        toEdge[j] = toEdge[i]! + 1;
        queue[tail++] = j;
      }
    });
  }
  // Si el borde se come la figura entera, se usa lo opaco sin recortar.
  let threshold = inset;
  const anySource = () => toEdge.some((d) => d === -1 || d > threshold);
  while (threshold > 0 && !anySource()) threshold -= 1;
  const filled = new Uint8Array(total);
  head = 0;
  tail = 0;
  for (let i = 0; i < total; i += 1) {
    const d = toEdge[i]!;
    if (d === -1 || d > threshold) {
      filled[i] = 1;
      queue[tail++] = i;
    }
  }
  while (head < tail) {
    const i = queue[head++]!;
    neighbours(i, (j) => {
      if (filled[j] === 1) return;
      filled[j] = 1;
      out[j * 4] = out[i * 4]!;
      out[j * 4 + 1] = out[i * 4 + 1]!;
      out[j * 4 + 2] = out[i * 4 + 2]!;
      queue[tail++] = j;
    });
  }
  for (let i = 0; i < total; i += 1) out[i * 4 + 3] = 255;
  return out;
}

/**
 * Desenfoque de caja separable, con el borde repetido. La proyección de frente, vista de lado, estira
 * cada píxel del borde en una raya horizontal, y vista de espalda repite los dibujos del pecho (el
 * corazón); en esas caras el sombreador mezcla hacia esta copia borrosa, que deja el color y quita el
 * dibujo. Devuelve una copia; el alfa no se toca.
 */
export function blur(rgba: Uint8Array, width: number, height: number, radius: number): Uint8Array {
  const pass = (source: Uint8Array, horizontal: boolean): Uint8Array => {
    const target = new Uint8Array(source);
    const length = horizontal ? width : height;
    const lines = horizontal ? height : width;
    const at = (line: number, k: number) =>
      (horizontal ? line * width + k : k * width + line) * 4;
    for (let line = 0; line < lines; line += 1) {
      for (let k = 0; k < length; k += 1) {
        for (let channel = 0; channel < 3; channel += 1) {
          let sum = 0;
          for (let d = -radius; d <= radius; d += 1) {
            const clamped = Math.max(0, Math.min(length - 1, k + d));
            sum += source[at(line, clamped) + channel]!;
          }
          target[at(line, k) + channel] = Math.round(sum / (2 * radius + 1));
        }
      }
    }
    return target;
  };
  return pass(pass(rgba, true), false);
}
