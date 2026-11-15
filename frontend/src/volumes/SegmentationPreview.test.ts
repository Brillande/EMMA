import { describe, expect, it } from "vitest";

import { TURN_MS, spinAt } from "./SegmentationPreview";

describe("la vuelta del hígado en la vista previa", () => {
  it("da una vuelta entera en horizontal cada TURN_MS y vuelve a empezar", () => {
    expect(spinAt(0).y).toBe(0);
    expect(spinAt(TURN_MS / 2).y).toBeCloseTo(Math.PI, 6);
    expect(spinAt(TURN_MS * 0.75).y).toBeCloseTo(1.5 * Math.PI, 6);
    expect(spinAt(TURN_MS).y).toBe(0);
  });

  it("cabecea como Polaris: 9° ± 4°", () => {
    const deg = (rad: number) => (rad * 180) / Math.PI;
    expect(deg(spinAt(0).x)).toBeCloseTo(9, 6);
    expect(deg(spinAt(TURN_MS / 4).x)).toBeCloseTo(13, 6);
    expect(deg(spinAt((TURN_MS * 3) / 4).x)).toBeCloseTo(5, 6);
  });

  it("gira despacio: una vuelta tarda más de 10 s", () => {
    expect(TURN_MS).toBeGreaterThan(10_000);
  });
});
