import { describe, expect, it } from "vitest";

import { eventBody, zonedToUtc } from "./forms";

const FORM = { title: "Revisión del filtro", date: "2026-11-13", allDay: false, start: "18:00", end: "19:30" };

describe("zonedToUtc", () => {
  it("lee la hora en la zona del hogar, también con horario de verano", () => {
    expect(zonedToUtc("2026-11-13", "18:00", "Europe/Madrid")).toBe("2026-11-13T17:00:00.000Z");
    expect(zonedToUtc("2026-07-13", "18:00", "Europe/Madrid")).toBe("2026-07-13T16:00:00.000Z");
    expect(zonedToUtc("2026-11-13", "18:00", "UTC")).toBe("2026-11-13T18:00:00.000Z");
  });
});

describe("eventBody", () => {
  it("un evento con hora lleva sus instantes UTC y la zona", () => {
    expect(eventBody(FORM, "Europe/Madrid")).toEqual({
      title: "Revisión del filtro",
      allDay: false,
      startUtc: "2026-11-13T17:00:00.000Z",
      endUtc: "2026-11-13T18:30:00.000Z",
      tzid: "Europe/Madrid",
    });
  });
  it("un evento de día entero termina al día siguiente (fin exclusivo de Marplanner)", () => {
    expect(eventBody({ ...FORM, allDay: true }, "UTC")).toEqual({
      title: "Revisión del filtro",
      allDay: true,
      startDate: "2026-11-13",
      endDate: "2026-11-14",
    });
  });
  it("dice por qué no se puede crear todavía", () => {
    expect(eventBody({ ...FORM, title: "  " }, "UTC")).toBe("falta el título");
    expect(eventBody({ ...FORM, date: "" }, "UTC")).toBe("falta el día");
    expect(eventBody({ ...FORM, end: "17:00" }, "UTC")).toMatch(/posterior/);
  });
});
