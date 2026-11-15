import { describe, expect, it } from "vitest";

import { dueRule, householdClock } from "./announcements";

const RULE = { id: "r1", time: "07:00", weekDays: ["mon", "tue", "wed", "thu", "fri"], isActive: true };
// Jueves 12 de noviembre de 2026, 06:00 UTC = 07:00 en Madrid.
const AT = new Date("2026-11-12T06:00:20Z");

describe("householdClock", () => {
  it("lee la hora, el día y la fecha en la zona del hogar", () => {
    expect(householdClock(AT, "Europe/Madrid")).toEqual({ time: "07:00", weekday: "thu", date: "2026-11-12" });
    expect(householdClock(new Date("2026-11-12T23:30:00Z"), "Europe/Madrid").weekday).toBe("fri");
  });
});

describe("dueRule", () => {
  it("toca a su hora, en sus días, una vez por minuto", () => {
    const due = dueRule([RULE], AT, "Europe/Madrid", new Set());
    expect(due?.rule.id).toBe("r1");
    expect(dueRule([RULE], AT, "Europe/Madrid", new Set([due!.key]))).toBeNull();
  });
  it("no toca en UTC, ni otro día, ni pausada", () => {
    expect(dueRule([RULE], AT, "UTC", new Set())).toBeNull();
    expect(dueRule([{ ...RULE, weekDays: ["sat"] }], AT, "Europe/Madrid", new Set())).toBeNull();
    expect(dueRule([{ ...RULE, isActive: false }], AT, "Europe/Madrid", new Set())).toBeNull();
  });
});
