import { describe, expect, it } from "vitest";

import { type BackPoint, smoothCurve } from "../backSkin";
import { BODY, surfaceOf } from "../bodyModel";
import { LEGS, LEGS_MUSCLES } from "./legs";

/**
 * Los trazos de las piernas se colocaron a ojo sobre la silueta de la malla. Si la malla cambia (la
 * pierna se abre más, el pie gira), un trazo podría quedar fuera del cuerpo y perderse sin que nada
 * avise: la proyección de espaldas solo pinta lo que cae sobre la malla.
 */

/** Los triángulos de la malla proyectados en x/y, de espaldas, como `back-preview.mjs`. */
function projectedTriangles(): number[][] {
  const triangles: number[][] = [];
  for (const item of BODY) {
    const { positions, indices } = surfaceOf(item);
    for (let t = 0; t < indices.length; t += 3) {
      const corner = (k: number) => [positions[indices[t + k]! * 3]!, positions[indices[t + k]! * 3 + 1]!];
      triangles.push([...corner(0), ...corner(1), ...corner(2)]);
    }
  }
  return triangles;
}

function inside(triangles: readonly number[][], [x, y]: BackPoint): boolean {
  return triangles.some(([ax, ay, bx, by, cx, cy]) => {
    const area = (bx! - ax!) * (cy! - ay!) - (by! - ay!) * (cx! - ax!);
    if (area === 0) return false;
    const w0 = ((bx! - x) * (cy! - y) - (by! - y) * (cx! - x)) / area;
    const w1 = ((cx! - x) * (ay! - y) - (cy! - y) * (ax! - x)) / area;
    return w0 >= 0 && w1 >= 0 && w0 + w1 <= 1;
  });
}

describe("trazos de glúteos y piernas", () => {
  it("cada trazo cae sobre la malla en todo su recorrido", () => {
    const triangles = projectedTriangles();
    // Muestras cada 1 cm de la curva ya suavizada: la curva puede salirse aunque sus puntos no.
    const outside = LEGS.flatMap((stroke, index) =>
      smoothCurve(stroke.points, stroke.closed ?? false, 0.01)
        .filter((point) => !inside(triangles, point))
        .map((point) => `trazo ${index}: (${point[0].toFixed(3)}, ${point[1].toFixed(3)})`),
    );
    expect(outside).toEqual([]);
  });

  it("cada músculo cae sobre la malla en todo su contorno", () => {
    const triangles = projectedTriangles();
    const outside = LEGS_MUSCLES.flatMap((muscle, index) =>
      smoothCurve(muscle.outline, true, 0.01)
        .filter((point) => !inside(triangles, point))
        .map((point) => `músculo ${index}: (${point[0].toFixed(3)}, ${point[1].toFixed(3)})`),
    );
    expect(outside).toEqual([]);
  });

  it("la cabeza interna de los gemelos baja más que la externa", () => {
    // Desde «Volumen 1» las dos cabezas son músculos con volumen (`LEGS_MUSCLES`), no trazos: la
    // misma comprobación, sobre sus contornos. Por dentro está la cabeza interna (x pequeña en la
    // pierna +x), y su punta es la más baja.
    const heads = LEGS_MUSCLES.filter((muscle) => muscle.outline.every(([x, y]) => x > 0 && y > 0.24 && y < 0.52));
    const lowest = (muscle: (typeof heads)[number]) => Math.min(...muscle.outline.map(([, y]) => y));
    const meanX = (muscle: (typeof heads)[number]) =>
      muscle.outline.reduce((sum, [x]) => sum + x, 0) / muscle.outline.length;
    expect(heads).toHaveLength(2);
    const [inner, outer] = [...heads].sort((a, b) => meanX(a) - meanX(b));
    expect(lowest(inner!)).toBeLessThan(lowest(outer!));
  });
});
