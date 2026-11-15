import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { parseAvatar } from "../lib/avatar";
import { BODY, surfaceOf } from "./bodyModel";
import { FEMININE_PROFILE, feminize, feminizeSurface, lateral, profileAt } from "./feminine";

/**
 * La variante femenina (petición del usuario, 2026-11-14): el mismo cuerpo deformado igual que el 2D, sin
 * tocar zonas ni centros.
 */
describe("avatar femenino del 3D", () => {
  it("usa el mismo perfil que el script que deforma el 2D", () => {
    // Si no casan, los colores térmicos del 2D femenino caen fuera de su sitio en el 3D.
    const script = readFileSync(fileURLToPath(new URL("../dashboard/referenceBodyFemale.py", import.meta.url)), "utf8");
    const block = /PROFILE = \[([\s\S]*?)\n\]/.exec(script)?.[1] ?? "";
    const rows = [...block.matchAll(/\((\d+), ([\d.]+), (\d+)\)/g)].map((m) => [Number(m[1]), Number(m[2]), Number(m[3])]);
    expect(rows).toEqual(FEMININE_PROFILE.map((row) => [...row]));
  });

  it("estrecha hombros y cintura y ensancha caderas", () => {
    const shoulders = profileAt(1.43).scale;
    const waist = profileAt(1.08).scale;
    const hips = profileAt(0.85).scale;
    expect(shoulders).toBeLessThan(0.92);
    expect(waist).toBeLessThan(0.9);
    expect(hips).toBeGreaterThan(1.05);
    // Las rodillas y los pies, como estaban.
    expect(profileAt(0.4).scale).toBeCloseTo(1, 5);
    expect(feminize([0.1, 0.05, 0.02])).toEqual([0.1, 0.05, 0.02]);
  });

  it("fuera del tronco desplaza sin estirar: el brazo conserva su grosor", () => {
    const { scale, half } = profileAt(1.08);
    const a = half + 0.08;
    const b = half + 0.12;
    expect(lateral(b, scale, half) - lateral(a, scale, half)).toBeCloseTo(b - a, 6);
    // Y es monótona: ningún punto adelanta a otro más alejado del eje.
    let last = -Infinity;
    for (let x = 0; x < 0.5; x += 0.002) {
      const now = lateral(x, scale, half);
      expect(now).toBeGreaterThan(last);
      last = now;
    }
  });

  it("no toca la superficie del cuerpo de partida ni sus índices", () => {
    const surface = surfaceOf(BODY[0]!);
    const before = Float32Array.from(surface.positions);
    const moved = feminizeSurface(surface);
    expect(surface.positions).toEqual(before);
    expect(moved.indices).toBe(surface.indices);
    expect(moved.positions.length).toBe(before.length);
  });

  it("el avatar guardado es tolerante: cualquier otra cosa es el de partida", () => {
    expect(parseAvatar("female")).toBe("female");
    expect(parseAvatar("male")).toBe("male");
    expect(parseAvatar(null)).toBe("male");
    expect(parseAvatar("otra")).toBe("male");
  });
});
