import { describe, expect, it } from "vitest";

import type { PainReport } from "../lib/api";
import { evolution } from "./evolution";

function report(effective: string, zones: [string, number][]): PainReport {
  return {
    subject: "crew-01",
    effective,
    reported_by: "cmdr",
    zones: zones.map(([zone, intensity]) => ({ zone, intensity, characters: [] })),
    intensity: Math.max(0, ...zones.map(([, value]) => value)),
    ledger_index: 0,
    recorded: effective,
    discuss: { reasons: [], note: null },
  };
}

describe("evolucion del dolor por zona", () => {
  it("una zona que deja de marcarse baja a 0: el informe es del cuerpo entero", () => {
    const [lumbar] = evolution([
      report("2026-09-20T08:00:00Z", [["lower-back", 6]]),
      report("2026-09-21T08:00:00Z", []),
    ]);
    expect(lumbar?.series.map((point) => point.intensity)).toEqual([6, 0]);
    expect(lumbar?.change).toBe("baja");
  });

  it("la serie de una zona empieza cuando se marca por primera vez", () => {
    const zones = evolution([
      report("2026-09-20T08:00:00Z", [["lower-back", 4]]),
      report("2026-09-21T08:00:00Z", [["lower-back", 4], ["knee-left", 3]]),
    ]);
    const knee = zones.find((item) => item.zone === "knee-left");
    expect(knee?.series).toHaveLength(1);
    expect(knee?.change).toBe("nueva");
    expect(zones.find((item) => item.zone === "lower-back")?.change).toBe("igual");
  });

  it("ordena por fecha del informe aunque lleguen desordenados", () => {
    const [lumbar] = evolution([
      report("2026-09-22T08:00:00Z", [["lower-back", 7]]),
      report("2026-09-20T08:00:00Z", [["lower-back", 2]]),
    ]);
    expect(lumbar?.latest).toBe(7);
    expect(lumbar?.previous).toBe(2);
    expect(lumbar?.change).toBe("sube");
  });

  it("primero lo que mas duele ahora", () => {
    const zones = evolution([report("2026-09-20T08:00:00Z", [["head", 2], ["knee-left", 8]])]);
    expect(zones.map((item) => item.zone)).toEqual(["knee-left", "head"]);
  });

  it("sin informes no hay evolucion", () => {
    expect(evolution([])).toEqual([]);
  });
});
