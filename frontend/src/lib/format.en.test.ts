/**
 * Las cifras en inglés (`lib/i18n.ts`): punto decimal, el de F.5.6, y el mismo espacio fino en los
 * millares. Las reglas de forma de `format.test.ts` no cambian con el idioma; aquí solo lo que sí.
 */
import "../test/english";

import { describe, expect, it } from "vitest";

import { decimalMark, displayUnit, formatAge, formatField, formatHouseholdTime, formatMinutes, formatNumber } from "./format";
import { language, tr } from "./i18n";

describe("las cifras en inglés", () => {
  it("este fichero corre en inglés", () => {
    expect(language()).toBe("en");
    expect(tr("hola", "hello")).toBe("hello");
  });

  it("el decimal es un punto", () => {
    expect(decimalMark()).toBe(".");
    expect(formatNumber(0.25, 2)).toBe("0.25");
    expect(formatNumber(-0.5, 1)).toBe("-0.5");
    expect(formatNumber(36.6, 1)).toBe("36.6");
    expect(formatMinutes(4.3)).toBe("4.3 min");
    expect(formatAge(150)).toBe("2.5 h");
  });

  it("los millares siguen con espacio fino: una cifra no se lee de dos formas", () => {
    expect(formatNumber(12345)).toBe("12 345");
    expect(formatNumber(12345.5, 1)).toBe("12 345.5");
    expect(formatNumber(1234)).toBe("1234");
  });

  it("un campo desbordado conserva su punto", () => {
    expect(formatField(12345.6, 1, 4)).toEqual({ text: "**.*", overflow: true });
  });

  it("las unidades con una palabra castellana se leen en inglés; las demás, igual", () => {
    expect(displayUnit("mL/(24.h)")).toBe("mL/day");
    expect(displayUnit("{count}")).toBe("count");
    expect(displayUnit("{score}")).toBe("points");
    expect(displayUnit("{CFU}/m3")).toBe("CFU/m³");
    expect(displayUnit("u[IU]/mL")).toBe("µIU/mL");
    expect(displayUnit("Cel")).toBe("°C");
    expect(displayUnit("mSv")).toBe("mSv");
    expect(() => displayUnit("furlong")).toThrow(RangeError);
  });

  it("la hora del hogar se escribe a 24 horas, como en castellano", () => {
    expect(formatHouseholdTime("2026-11-15T17:30:00Z", "UTC")).toBe("17:30");
  });
});
