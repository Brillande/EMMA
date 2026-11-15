import { describe, expect, it } from "vitest";

import { addDays, dayPeriodLabel, householdDate, mealSlotLabel } from "./labels";

describe("palabras del planificador", () => {
  it("traduce las claves de Marplanner con sus propias palabras en español", () => {
    expect(dayPeriodLabel("dayPeriod.morning")).toBe("Mañana");
    expect(dayPeriodLabel("dayPeriod.evening")).toBe("Tarde");
    expect(mealSlotLabel("snack")).toBe("Merienda");
  });
  it("una clave desconocida se enseña tal cual, sin inventar palabra", () => {
    expect(dayPeriodLabel("dayPeriod.dawn")).toBe("dayPeriod.dawn");
    expect(mealSlotLabel("brunch")).toBe("brunch");
  });
});

describe("fechas del hogar", () => {
  it("el día es el de la zona del hogar, no el UTC", () => {
    expect(householdDate(new Date("2026-11-12T23:30:00Z"), "Europe/Madrid")).toBe("2026-11-13");
    expect(householdDate(new Date("2026-11-12T23:30:00Z"), "UTC")).toBe("2026-11-12");
  });
  it("suma días cruzando meses y años", () => {
    expect(addDays("2026-12-30", 6)).toBe("2027-01-05");
    expect(addDays("2026-03-28", 1)).toBe("2026-03-29");
  });
});
