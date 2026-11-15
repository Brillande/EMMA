import { describe, expect, it } from "vitest";

import { BODY, surfaceOf } from "./bodyModel";
import type { CavitySurface } from "./cavity";
import { blendCrossings, creaseCavities, REACH } from "./crossing";

type Point = [number, number, number];

/**
 * Un trozo de plano: `origin + a·u + b·v` con a y b en [from, to] (paso `step`), y la normal fija
 * `normal`. Cada llamada es una pieza aparte (no comparte vértices con otra).
 */
function plane(
  origin: Point,
  u: Point,
  v: Point,
  normal: Point,
  [fromA, toA]: [number, number],
  [fromB, toB]: [number, number],
  step = 0.004,
): CavitySurface {
  const positions: number[] = [];
  const normals: number[] = [];
  const indices: number[] = [];
  const countA = Math.round((toA - fromA) / step);
  const countB = Math.round((toB - fromB) / step);
  for (let i = 0; i <= countA; i += 1) {
    for (let j = 0; j <= countB; j += 1) {
      const a = fromA + i * step;
      const b = fromB + j * step;
      positions.push(origin[0] + a * u[0] + b * v[0], origin[1] + a * u[1] + b * v[1], origin[2] + a * u[2] + b * v[2]);
      normals.push(...normal);
    }
  }
  const width = countB + 1;
  for (let i = 0; i < countA; i += 1) {
    for (let j = 0; j < countB; j += 1) {
      const p = i * width + j;
      indices.push(p, p + width, p + width + 1, p, p + width + 1, p + 1);
    }
  }
  return { positions, normals, indices };
}

const at = (list: ArrayLike<number>, v: number): Point => [
  list[v * 3]!,
  list[v * 3 + 1]!,
  list[v * 3 + 2]!,
];
const dot = (a: Point, b: Point) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

/**
 * Un «hombro» de prueba: el tronco, plano horizontal (normal +y), y el brazo, plano inclinado 60°
 * que lo atraviesa por la línea x = 0. Lo visible es el tronco a x > 0 y el brazo por encima.
 */
const tilt = (60 * Math.PI) / 180;
const armNormal: Point = [Math.sin(tilt), Math.cos(tilt), 0];
const armUp: Point = [-Math.cos(tilt), Math.sin(tilt), 0];
const trunk = plane([0, 0, 0], [1, 0, 0], [0, 0, 1], [0, 1, 0], [-0.08, 0.1], [-0.06, 0.06]);
// Medio paso desplazado: si la rejilla del brazo pasara por la línea del cruce, sus vértices
// coincidirían con los del tronco, se soldarían y serían una sola pieza.
const arm = plane([0, 0, 0], armUp, [0, 0, 1], armNormal, [-0.078, 0.102], [-0.06, 0.06]);

describe("blendCrossings", () => {
  const { normals, crease } = blendCrossings([trunk, arm]);

  it("las normales de las dos piezas convergen en la línea del cruce", () => {
    // Vértices visibles junto a la línea (a 2 mm o menos de ella), en una fila central.
    const nearTrunk: Point[] = [];
    const nearArm: Point[] = [];
    for (let v = 0; v < trunk.positions.length / 3; v += 1) {
      const [x, , z] = at(trunk.positions, v);
      if (x >= 0 && x < 0.0025 && Math.abs(z) < 0.03) nearTrunk.push(at(normals[0]!, v));
    }
    for (let v = 0; v < arm.positions.length / 3; v += 1) {
      const [, y, z] = at(arm.positions, v);
      const along = y / Math.sin(tilt);
      if (along >= 0 && along < 0.0025 && Math.abs(z) < 0.03) nearArm.push(at(normals[1]!, v));
    }
    expect(nearTrunk.length).toBeGreaterThan(0);
    expect(nearArm.length).toBeGreaterThan(0);
    // Antes del cruce las normales se separan 60° (coseno 0,5); en la línea, casi una.
    expect(dot([0, 1, 0], armNormal)).toBeCloseTo(0.5, 6);
    for (const a of nearTrunk) for (const b of nearArm) expect(dot(a, b)).toBeGreaterThan(0.97);
    // Y siguen siendo unitarias.
    for (const n of [...nearTrunk, ...nearArm]) expect(Math.hypot(...n)).toBeCloseTo(1, 5);
  });

  it("no cambia nada lejos de la franja y la mezcla decrece con la distancia", () => {
    let previous = -Infinity;
    for (let v = 0; v < trunk.positions.length / 3; v += 1) {
      const [x, , z] = at(trunk.positions, v);
      const n = at(normals[0]!, v);
      if (x > REACH + 0.002) {
        expect(n).toEqual([0, 1, 0]);
        expect(crease[0]![v]).toBe(0);
      }
      // A lo largo de x (fila z = 0, visible): la normal vuelve hacia la del tronco al alejarse.
      if (Math.abs(z) < 1e-9 && x >= 0) {
        expect(n[1]).toBeGreaterThanOrEqual(previous - 1e-6);
        previous = n[1];
      }
    }
    for (let v = 0; v < arm.positions.length / 3; v += 1) {
      const [, y] = at(arm.positions, v);
      if (y / Math.sin(tilt) > REACH + 0.002) expect(at(normals[1]!, v)).toEqual(armNormal.map(Math.fround));
    }
  });

  it("mide un pliegue que es máximo en el cruce y se apaga con la distancia", () => {
    const row = (x: number) => {
      for (let v = 0; v < trunk.positions.length / 3; v += 1) {
        const p = at(trunk.positions, v);
        if (Math.abs(p[0] - x) < 1e-6 && Math.abs(p[2]) < 1e-9) return crease[0]![v]!;
      }
      throw new Error(`sin vértice en x = ${x}`);
    };
    expect(row(0)).toBeGreaterThan(0.2);
    expect(row(0.012)).toBeLessThan(row(0));
    expect(row(0.012)).toBeGreaterThan(0);
    expect(row(REACH + 0.004)).toBe(0);
  });

  it("no toca dos piezas que solo pasan cerca sin cruzarse", () => {
    // Un dedo junto a otro: dos planos paralelos enfrentados, a 1 cm.
    const below = plane([0, 0, 0], [1, 0, 0], [0, 0, 1], [0, 1, 0], [-0.05, 0.05], [-0.05, 0.05]);
    const above = plane([0, 0.01, 0], [1, 0, 0], [0, 0, 1], [0, -1, 0], [-0.05, 0.05], [-0.05, 0.05]);
    // Un brazo junto al costado: en ángulo, pero sin llegar a tocarse.
    const side = plane([0.012, 0, 0], [1, 0, 0], [0, 0, 1], [0, 1, 0], [0, 0.06], [-0.05, 0.05]);
    const wall = plane([0, 0.006, 0], [0, 1, 0], [0, 0, 1], [1, 0, 0], [0, 0.06], [-0.05, 0.05]);
    for (const surfaces of [[below, above], [side, wall]]) {
      const result = blendCrossings(surfaces);
      surfaces.forEach((surface, s) => {
        expect(Array.from(result.normals[s]!)).toEqual(Array.from(surface.normals, Math.fround));
        expect(result.crease[s]!.every((value) => value === 0)).toBe(true);
      });
    }
  });

  it("no toca las superficies de entrada", () => {
    expect(Array.from(trunk.normals).every((value, k) => value === [0, 1, 0][k % 3])).toBe(true);
  });

  it("recorre el cuerpo entero en poco tiempo, con normales unitarias y pliegues en [0, 1]", () => {
    const surfaces = BODY.map(surfaceOf);
    const begin = performance.now();
    const result = blendCrossings(surfaces);
    // Holgado a propósito: avisa si el coste se dispara (no es lineal).
    expect(performance.now() - begin).toBeLessThan(4000);
    let changed = 0;
    result.normals.forEach((list, s) => {
      expect(list.length).toBe(surfaces[s]!.normals.length);
      for (let v = 0; v < list.length / 3; v += 1) {
        expect(Math.hypot(list[v * 3]!, list[v * 3 + 1]!, list[v * 3 + 2]!)).toBeCloseTo(1, 4);
        if (list[v * 3] !== surfaces[s]!.normals[v * 3]) changed += 1;
      }
      for (const value of result.crease[s]!) {
        expect(value).toBeGreaterThanOrEqual(0);
        expect(value).toBeLessThanOrEqual(1);
      }
    });
    // Hay cruces (hombros, caderas, dedos…), pero la mayor parte de la piel no se toca.
    const vertices = surfaces.reduce((sum, surface) => sum + surface.normals.length / 3, 0);
    expect(changed).toBeGreaterThan(0);
    expect(changed).toBeLessThan(vertices * 0.5);
    // Y cada cruce que motivó esto se ve como cruce: si una retesela soldara el brazo al tronco o
    // la pierna a la pelvis, serían una sola pieza y la junta volvería a cortar la luz sin aviso.
    for (const zone of ["shoulder-left", "shoulder-right", "hip-left", "hip-right", "hand-left", "foot-left"]) {
      const s = BODY.findIndex((item) => item.zone === zone);
      const before = surfaces[s]!.normals;
      const after = result.normals[s]!;
      expect(after.some((value, k) => value !== before[k]), zone).toBe(true);
      expect(result.crease[s]!.some((value) => value > 0.3), zone).toBe(true);
    }
  });
});

describe("creaseCavities", () => {
  it("ahonda solo donde hay pliegue y recorta a 1", () => {
    const values = [Float32Array.from([0, 0.5, 0.9, -0.2])];
    creaseCavities(values, [Float32Array.from([0, 0.5, 1, 0])]);
    expect(values[0]![0]).toBe(0);
    expect(values[0]![1]).toBeGreaterThan(0.5);
    expect(values[0]![2]).toBe(1);
    expect(values[0]![3]).toBeCloseTo(-0.2, 6);
  });
});
