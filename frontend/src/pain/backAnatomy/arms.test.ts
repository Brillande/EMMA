import { describe, expect, it } from "vitest";
import { BODY, surfaceOf } from "../bodyModel";
import { smoothCurve } from "../backSkin";
import { ARMS, ARMS_BONES, ARMS_MUSCLES } from "./arms";

/**
 * Los trazos del brazo se colocan a mano sobre la silueta de la malla vista de espaldas, y el brazo
 * es estrecho (la mano mide 0,05 m de ancho): si alguien mueve el eje del brazo en `bodyModel.ts`,
 * un trazo puede acabar pintado fuera del cuerpo, donde la textura no se ve, sin que nada falle.
 * Esta prueba lo avisa.
 */

/** Los triángulos de toda la malla, proyectados en x/y (lo que se ve de espaldas). */
function silhouette(): number[][] {
  const triangles: number[][] = [];
  for (const item of BODY) {
    const { positions, indices } = surfaceOf(item);
    for (let t = 0; t < indices.length; t += 3) {
      const corners: number[] = [];
      for (let k = 0; k < 3; k += 1) {
        const at = indices[t + k]! * 3;
        corners.push(positions[at]!, positions[at + 1]!);
      }
      triangles.push(corners);
    }
  }
  return triangles;
}

function inside(triangles: readonly number[][], x: number, y: number): boolean {
  return triangles.some(([ax, ay, bx, by, cx, cy]) => {
    const area = (bx! - ax!) * (cy! - ay!) - (by! - ay!) * (cx! - ax!);
    if (area === 0) return false;
    const w0 = ((bx! - x) * (cy! - y) - (by! - y) * (cx! - x)) / area;
    const w1 = ((cx! - x) * (ay! - y) - (cy! - y) * (ax! - x)) / area;
    return w0 >= 0 && w1 >= 0 && w0 + w1 <= 1;
  });
}

describe("trazos de los brazos por detrás", () => {
  it("cada punto de paso cae sobre la silueta de la malla, en los dos brazos", () => {
    const triangles = silhouette();
    const outside = ARMS.flatMap((stroke) => stroke.points.filter(([x, y]) => !inside(triangles, x, y)));
    expect(outside).toEqual([]);
  });

  it("los músculos y huesos del brazo caen sobre la silueta en toda su curva, en los dos brazos", () => {
    const triangles = silhouette();
    // La curva ya suavizada, cada centímetro: un contorno cerrado puede salirse aunque sus puntos no.
    const points = [
      ...ARMS_MUSCLES.flatMap((muscle) => [...smoothCurve(muscle.outline, true, 0.01), ...(muscle.shape ?? [])]),
      ...ARMS_BONES.flatMap((bone) => smoothCurve(bone.points, bone.closed ?? false, 0.01)),
    ];
    expect(points.length).toBeGreaterThan(0);
    expect(points.filter(([x, y]) => !inside(triangles, x, y))).toEqual([]);
  });

  it("se dibujan los dos brazos, en espejo", () => {
    const left = ARMS.filter((stroke) => stroke.points[0]![0] > 0).length;
    const right = ARMS.filter((stroke) => stroke.points[0]![0] < 0).length;
    expect(left).toBeGreaterThan(0);
    expect(right).toBe(left);
  });
});
