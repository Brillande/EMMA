import { describe, expect, it } from "vitest";

import { plannerCut } from "./GroundPlannerPanel";

describe("plannerCut", () => {
  it("es la hora real menos el retardo, redondeada hacia atrás a cinco minutos", () => {
    const now = Date.parse("2026-11-12T15:43:20Z");
    expect(plannerCut(11, now)?.toISOString()).toBe("2026-11-12T15:30:00.000Z");
  });
  it("sin retardo conocido no hay corte", () => {
    expect(plannerCut(null, Date.now())).toBeNull();
  });
});
