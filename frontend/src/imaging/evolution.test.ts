import { describe, expect, it } from "vitest";

import type { FhirObservation } from "../lib/api";
import { previousReading } from "./evolution";

const obs = (value: number, effectiveDateTime: string): FhirObservation => ({
  code: { coding: [], text: "" },
  effectiveDateTime,
  valueQuantity: { value, unit: "mm" },
});

describe("evolucion de una medida", () => {
  it("toma la mas reciente anterior, no la mas alta ni la ultima de la lista", () => {
    const readings = [
      obs(5.9, "2026-11-20T08:00:00+00:00"), // la propia medida: no es anterior
      obs(5.1, "2026-11-06T08:00:00+00:00"),
      obs(6.0, "2026-10-01T08:00:00+00:00"),
    ];
    expect(previousReading(readings, "2026-11-20T08:00:00+00:00")).toEqual({
      value: 5.1,
      effective: "2026-11-06T08:00:00+00:00",
    });
  });

  it("la primera medida no tiene anterior", () => {
    expect(previousReading([obs(5.5, "2026-11-20T08:00:00+00:00")], "2026-11-20T08:00:00+00:00")).toBeNull();
  });
});
