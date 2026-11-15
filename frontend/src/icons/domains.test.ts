import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { DOMAIN_LABELS } from "../lib/levels";
import { domains } from "./sets/domains";

/**
 * Cada dominio clinico y cada peligro RIDGE del backend tiene su pictograma. Los valores se leen
 * del propio `codes.py`: si el backend gana un dominio, esta prueba lo dice antes de que un panel
 * lo pinte sin dibujo.
 */

const CODES_PATH = fileURLToPath(new URL("../../../backend/app/ingest/codes.py", import.meta.url));

/** Los valores de un `StrEnum` de `codes.py`, por el nombre de la clase. Falla si no esta. */
function enumValues(className: string): string[] {
  const source = readFileSync(CODES_PATH, "utf8");
  const block = new RegExp(`class ${className}\\(StrEnum\\):([\\s\\S]*?)\\n(?:class |_[A-Z])`).exec(source);
  if (block === null || block[1] === undefined) throw new Error(`no se encuentra class ${className} en codes.py`);
  const values = [...block[1].matchAll(/^\s+[A-Z_0-9]+ = "([^"]+)"/gm)].map((match) => match[1] ?? "");
  if (values.length === 0) throw new Error(`class ${className} no tiene valores`);
  return values;
}

describe("dominios y peligros RIDGE del backend", () => {
  it("se leen del enum, no de una lista vacia", () => {
    expect(enumValues("Domain").length).toBeGreaterThan(5);
    expect(enumValues("Ridge").length).toBe(5);
    expect(enumValues("Domain")).toContain("cardiovascular");
    expect(enumValues("Ridge")).toContain("gravity");
    expect(() => enumValues("Inventado")).toThrow(/no se encuentra/);
  });

  it("cada dominio tiene pictograma, y la tabla de nombres de la interfaz conoce los mismos", () => {
    const values = enumValues("Domain");
    for (const value of values) expect(`domain-${value}` in domains, value).toBe(true);
    expect([...values].sort()).toEqual(Object.keys(DOMAIN_LABELS).sort());
  });

  it("cada peligro RIDGE tiene pictograma", () => {
    for (const value of enumValues("Ridge")) expect(`ridge-${value}` in domains, value).toBe(true);
  });

  it("el conjunto no tiene nada que no sea un dominio o un peligro", () => {
    const known = new Set([
      ...enumValues("Domain").map((value) => `domain-${value}`),
      ...enumValues("Ridge").map((value) => `ridge-${value}`),
    ]);
    for (const name of Object.keys(domains)) expect(known.has(name), name).toBe(true);
  });
});
