/**
 * Los motivos por los que un campo del diario no se envía, en inglés (`lib/i18n.ts`). Son texto de
 * pantalla: lo que se envía (clave, cifra, sujeto, quién anota, alimento) no cambia con el idioma.
 */
import "../test/english";

import { describe, expect, it } from "vitest";

import type { DiaryCatalog, DiaryIndicator } from "../lib/api";
import { check, itemProblem, prepare } from "./entry";

const mood = {
  key: "mood",
  physical_min: 1,
  physical_max: 10,
  range_text: "1–10 (backend)",
  food_item: null,
} as unknown as DiaryIndicator;

const food = {
  key: "food-acceptability",
  physical_min: 1,
  physical_max: 9,
  range_text: "1–9 (backend)",
  food_item: { label: "ALIMENTO (backend)", required: true, max_length: 5 },
} as unknown as DiaryIndicator;

describe("los motivos del diario en inglés", () => {
  it("lo que no es una cifra y lo que se sale del rango, con el rango del backend tal cual", () => {
    expect(check(mood, "siete")).toEqual({ state: "invalid", reason: "Not a number." });
    expect(check(mood, "11")).toEqual({ state: "invalid", reason: "Out of range: 1–10 (backend)." });
    expect(check(mood, "7")).toEqual({ state: "ok", value: 7 });
  });

  it("la coma y el punto decimal se leen igual en los dos idiomas", () => {
    expect(check(mood, "7,5")).toEqual({ state: "ok", value: 7.5 });
    expect(check(mood, "7.5")).toEqual({ state: "ok", value: 7.5 });
  });

  it("el alimento: falta la cifra, falta el alimento o pasa del tope, con el rótulo del backend", () => {
    expect(itemProblem(food, { state: "empty" }, "arroz")).toBe("ALIMENTO (backend): the number is missing.");
    expect(itemProblem(food, { state: "ok", value: 5 }, "")).toBe("Missing: ALIMENTO (backend).");
    expect(itemProblem(food, { state: "ok", value: 5 }, "arroz con pollo")).toBe("ALIMENTO (backend): over the character limit.");
  });

  it("lo que se envía no lleva texto traducido", () => {
    const catalog = { indicators: [mood] } as unknown as DiaryCatalog;
    const prepared = prepare(catalog, "crew-01", { mood: "7" }, "CDR");
    expect(prepared.bodies).toEqual([{ key: "mood", value: 7, subject: "crew-01", recorded_by: "CDR" }]);
    expect(prepared.problems).toEqual([]);
  });
});
