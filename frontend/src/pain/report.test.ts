import { describe, expect, it } from "vitest";

import { missingIntensities, toBody, toggleCharacter, toggleZone, withIntensity } from "./report";

describe("formulario de dolor", () => {
  it("una zona marcada no tiene intensidad hasta que el tripulante la elige", () => {
    const form = toggleZone([], "knee-left");
    expect(form).toEqual([{ zone: "knee-left", intensity: null, characters: [] }]);
    expect(missingIntensities(form)).toBe(1);
    expect(toBody(form, "cmdr")).toBeNull();
  });

  it("un segundo clic en la misma zona la desmarca", () => {
    expect(toggleZone(toggleZone([], "head"), "head")).toEqual([]);
  });

  it("sin nombre de quien informa no se envia", () => {
    const form = withIntensity(toggleZone([], "head"), "head", 4);
    expect(toBody(form, "   ")).toBeNull();
    expect(toBody(form, " cmdr ")?.reported_by).toBe("cmdr");
  });

  it("sin zonas es un informe de sin dolor, no un formulario incompleto", () => {
    expect(toBody([], "cmdr")).toEqual({ zones: [], reported_by: "cmdr" });
  });

  it("los tipos de dolor se marcan y desmarcan por zona", () => {
    let form = toggleZone(toggleZone([], "head"), "lower-back");
    form = toggleCharacter(form, "lower-back", "dull");
    form = toggleCharacter(form, "lower-back", "sharp");
    form = toggleCharacter(form, "lower-back", "dull");
    expect(form[0]?.characters).toEqual([]);
    expect(form[1]?.characters).toEqual(["sharp"]);
  });

  it("envia las zonas en el orden en que se marcaron", () => {
    let form = toggleZone(toggleZone([], "lower-back"), "knee-left");
    form = withIntensity(withIntensity(form, "knee-left", 3), "lower-back", 6);
    expect(toBody(form, "cmdr")?.zones.map((zone) => [zone.zone, zone.intensity])).toEqual([
      ["lower-back", 6],
      ["knee-left", 3],
    ]);
  });
});
