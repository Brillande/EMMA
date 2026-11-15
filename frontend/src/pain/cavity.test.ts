import { describe, expect, it } from "vitest";

import { BODY, surfaceOf } from "./bodyModel";
import { cavityOf, fadeCavities, type CavitySurface } from "./cavity";

/**
 * Una rejilla de altura `height(x, z)` sobre el plano y = 0, con normales hacia +y aproximadas.
 * `from`/`to` recortan las columnas en x, para partirla en dos superficies que comparten borde.
 */
function sheet(
  height: (x: number, z: number) => number,
  from: number,
  to: number,
  size = 40,
  step = 0.005,
): CavitySurface {
  const positions: number[] = [];
  const normals: number[] = [];
  const indices: number[] = [];
  const width = to - from + 1;
  for (let i = 0; i <= size; i += 1) {
    for (let j = from; j <= to; j += 1) {
      const x = (j - size / 2) * step;
      const z = (i - size / 2) * step;
      const e = 1e-4;
      const gx = (height(x + e, z) - height(x - e, z)) / (2 * e);
      const gz = (height(x, z + e) - height(x, z - e)) / (2 * e);
      const n = Math.hypot(gx, 1, gz);
      positions.push(x, height(x, z), z);
      normals.push(-gx / n, 1 / n, -gz / n);
    }
  }
  for (let i = 0; i < size; i += 1) {
    for (let j = 0; j < width - 1; j += 1) {
      const a = i * width + j;
      const b = (i + 1) * width + j;
      indices.push(a, b, b + 1, a, b + 1, a + 1);
    }
  }
  return { positions, normals, indices };
}

/** Un surco a lo largo de z en x = 0 entre dos lomos. */
const groove = (x: number) => -0.01 * Math.exp(-(x * x) / (2 * 0.01 * 0.01));

describe("cavityOf", () => {
  it("oscurece el surco y aclara el lomo, dentro de [−1, 1]", () => {
    const [values] = cavityOf([sheet(groove, 0, 40)]);
    const at = (i: number, j: number) => values![i * 41 + j]!;
    // Centro del surco (columna 20) frente a la zona plana lejana.
    expect(at(20, 20)).toBeGreaterThan(0.5);
    expect(at(20, 20)).toBeGreaterThan(at(20, 5));
    for (const value of values!) {
      expect(value).toBeGreaterThanOrEqual(-1);
      expect(value).toBeLessThanOrEqual(1);
    }
    // El lomo (curvatura convexa a ambos lados del surco) sale por debajo de cero.
    expect(Math.min(at(20, 16), at(20, 24))).toBeLessThan(0);
  });

  it("da el mismo valor a los dos lados de una costura entre superficies", () => {
    const whole = cavityOf([sheet(groove, 0, 40)])[0]!;
    const [left, right] = cavityOf([sheet(groove, 0, 20), sheet(groove, 20, 40)]);
    for (let i = 0; i <= 40; i += 1) {
      // Columna 20: la última de la izquierda (ancho 21) y la primera de la derecha.
      const a = left![i * 21 + 20]!;
      const b = right![i * 21]!;
      expect(a).toBe(b);
      expect(a).toBeCloseTo(whole[i * 41 + 20]!, 5);
    }
  });

  it("devuelve ceros si no hay relieve (plano)", () => {
    const [values] = cavityOf([sheet(() => 0, 0, 40)]);
    expect(values!.every((value) => value === 0)).toBe(true);
  });

  it("suelda dos copias de un vértice que caen a un lado y otro del borde de la celda", () => {
    // 1e-5 m es el lado de la celda: 0,5e-5 queda justo en el borde del redondeo.
    const nudge = (surface: CavitySurface, dx: number): CavitySurface => ({
      ...surface,
      positions: Array.from(surface.positions, (value, k) => (k % 3 === 0 ? value + dx : value)),
    });
    const [left, right] = cavityOf([
      nudge(sheet(groove, 0, 20), 0.5e-5 - 1e-9),
      nudge(sheet(groove, 20, 40), 0.5e-5 + 1e-9),
    ]);
    for (let i = 0; i <= 40; i += 1) expect(left![i * 21 + 20]!).toBe(right![i * 21]!);
  });

  it("cubre cada vértice del cuerpo con un valor finito, en poco tiempo", () => {
    const surfaces = BODY.map(surfaceOf);
    const begin = performance.now();
    const values = cavityOf(surfaces);
    // Holgado a propósito (hoy, unas decenas de milisegundos): avisa si el coste se dispara.
    expect(performance.now() - begin).toBeLessThan(2000);
    values.forEach((list, k) => {
      expect(list.length).toBe(surfaces[k]!.positions.length / 3);
      expect(list.every(Number.isFinite)).toBe(true);
    });
    // Hay surcos y crestas, no todo un tono.
    const flat = values.flatMap((list) => Array.from(list));
    expect(flat.some((value) => value > 0.5)).toBe(true);
    expect(flat.some((value) => value < -0.5)).toBe(true);
  });
});

describe("fadeCavities", () => {
  it("atenúa según la posición, recorta el factor a [0, 1] y deja igual la costura", () => {
    const surfaces = [sheet(groove, 0, 20), sheet(groove, 20, 40)];
    const values = cavityOf(surfaces);
    const before = values.map((list) => Float32Array.from(list));
    // Mitad de sombra a la derecha de x = 0 y toda a la izquierda; fuera de rango se recorta.
    fadeCavities(values, surfaces, (x) => (x > 0 ? 0.5 : x < 0 ? 3 : -1));
    values.forEach((list, s) => {
      list.forEach((value, v) => {
        const x = surfaces[s]!.positions[v * 3]!;
        const expected = x > 0 ? before[s]![v]! * 0.5 : x < 0 ? before[s]![v]! : 0;
        expect(value).toBeCloseTo(expected, 6);
      });
    });
    for (let i = 0; i <= 40; i += 1) expect(values[0]![i * 21 + 20]!).toBe(values[1]![i * 21]!);
  });
});
