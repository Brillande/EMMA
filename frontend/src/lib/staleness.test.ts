import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { FreshnessVerdict } from "./api";
import { freshnessOf } from "./staleness";

function verdict(state: string): FreshnessVerdict {
  return {
    source: "ephemeris",
    state: state as FreshnessVerdict["state"],
    display: "texto del backend",
    is_current: state === "fresh",
    age_seconds: state === "missing" ? null : 60,
    stale_after_seconds: 604_800,
    stale_after_display: "7 d",
  };
}

describe("F.4.3.1 c: indicacion de dato caducado", () => {
  it("pinta el estado que dio el backend, sin recalcularlo", () => {
    expect(freshnessOf(verdict("fresh"))).toBe("fresh");
    expect(freshnessOf(verdict("stale"))).toBe("stale");
    expect(freshnessOf(verdict("missing"))).toBe("missing");
  });

  it("no mira la antiguedad: un dato viejo que el backend da por vigente lo es", () => {
    const old = { ...verdict("fresh"), age_seconds: 10 ** 9 };
    expect(freshnessOf(old)).toBe("fresh");
    const recent = { ...verdict("stale"), age_seconds: 1 };
    expect(freshnessOf(recent)).toBe("stale");
  });

  it("sin veredicto no hay 'al dia': es ausente", () => {
    expect(freshnessOf(undefined)).toBe("missing");
    expect(freshnessOf(null)).toBe("missing");
  });

  it("un estado que la interfaz no conoce tampoco se da por vigente", () => {
    expect(freshnessOf(verdict("expired-ish"))).toBe("missing");
  });
});

describe("la regla de caducidad no vive en la interfaz", () => {
  const source = readFileSync(fileURLToPath(new URL("./staleness.ts", import.meta.url)), "utf8");
  const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

  it("no queda ningun plazo escrito: ni un numero", () => {
    expect(code).not.toMatch(/\d/);
  });
});
