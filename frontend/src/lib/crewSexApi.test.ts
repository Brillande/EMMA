import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { CREW_SEX_VALUES, crewSexPath } from "./crewSexApi";

/**
 * Los valores del sexo declarado se leen del propio `storage.py` (`CREW_SEX_VALUES`): si el backend
 * cambia la lista, esta prueba lo dice antes de que el tipo de la interfaz se quede atrás.
 */
const STORAGE = fileURLToPath(new URL("../../../backend/app/core/storage.py", import.meta.url));

function backendValues(): string[] {
  const match = readFileSync(STORAGE, "utf8").match(/^CREW_SEX_VALUES = \(([^)]*)\)/m);
  if (match === null) throw new Error("no se encuentra CREW_SEX_VALUES en storage.py");
  return [...(match[1] ?? "").matchAll(/"([^"]+)"/g)].map((value) => value[1] ?? "");
}

describe("crewSexApi", () => {
  it("acepta exactamente los valores del backend", () => {
    expect([...CREW_SEX_VALUES]).toEqual(backendValues());
  });

  it("lleva el corte de Tierra solo si se pide", () => {
    expect(crewSexPath()).toBe("/crew/sex?subject=crew-01");
    expect(crewSexPath(new Date("2026-11-14T00:00:00Z"), "crew-02")).toBe(
      "/crew/sex?subject=crew-02&until=2026-11-14T00%3A00%3A00.000Z",
    );
  });
});
