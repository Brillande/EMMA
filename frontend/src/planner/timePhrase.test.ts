import { describe, expect, it } from "vitest";

import { timePhrase } from "./timePhrase";

describe("timePhrase: la tabla de Marplanner, literal (tests/client/time-announcements-phrases.test.ts)", () => {
  const cases: Array<[number, number, string]> = [
    [0, 0, "Es medianoche"],
    [12, 0, "Es mediodía"],
    [1, 0, "Es la una"],
    [5, 0, "Son las cinco"],
    [1, 15, "Es la una y cuarto"],
    [5, 15, "Son las cinco y cuarto"],
    [1, 30, "Es la una y media"],
    [5, 30, "Son las cinco y media"],
    [1, 45, "Son las dos menos cuarto"],
    [5, 45, "Son las seis menos cuarto"],
    [5, 10, "Son las cinco y diez"],
    [5, 50, "Son las seis menos diez"],
  ];
  for (const [hour, minute, expected] of cases) {
    it(`${hour}:${String(minute).padStart(2, "0")} → «${expected}»`, () => {
      expect(timePhrase(hour, minute)).toBe(expected);
    });
  }
  it("una hora imposible falla en vez de decirse", () => {
    expect(() => timePhrase(24, 0)).toThrow(RangeError);
    expect(() => timePhrase(7, 60)).toThrow(RangeError);
  });
});
