// Los avisos de terceros de la interfaz (scripts/third-party.mjs): lo que viaja en dist/ lleva su
// licencia (revisión de fuentes del 2026-11-14, docs/fuentes-y-procedencia.md, «Resumen de huecos»).
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { HEADER, type LockFile, notices, productionPackages } from "../../scripts/third-party.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const lock = JSON.parse(readFileSync(join(root, "package-lock.json"), "utf8")) as LockFile;

describe("avisos de terceros de la interfaz", () => {
  it("lista las dependencias de producción y ninguna de desarrollo", () => {
    const names = productionPackages(lock, root).map((pkg) => pkg.name);
    for (const name of ["react", "react-dom", "three", "@niivue/niivue", "uplot", "@mediapipe/tasks-vision", "vosk-browser"]) {
      expect(names).toContain(name);
    }
    for (const dev of ["vite", "vitest", "typescript"]) expect(names).not.toContain(dev);
  });

  it("copia el texto de licencia que trae cada paquete", () => {
    const text = notices(lock, root);
    expect(text.startsWith(HEADER)).toBe(true);
    expect(text).toMatch(/\nreact \d+\.\d+\.\d+\nLicencia declarada: MIT\n/);
    expect(text).toMatch(/\n@niivue\/niivue [\d.]+\nLicencia declarada: BSD-2-Clause\n/);
    // React distribuye su LICENSE: el texto MIT tiene que ir entero, no solo el nombre.
    expect(text).toContain("Permission is hereby granted, free of charge");
  });
});
