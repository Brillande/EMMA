import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { UNKNOWN_MARK, mark } from "../lib/marks";
import { AVAILABLE_MARK, capabilityPictogram, causeMark, isKnownCause, reducedMark } from "./monitoring";

/*
 * La capacidad de vigilancia (F.6.2) se pinta con la palabra del backend y, al lado, el dibujo de
 * cada capacidad y la señal de su estado. Las capacidades se leen de `api/routes.py` para que una
 * nueva del backend no se quede sin dibujo; la señal de la causa es la de la tabla F.5-1.
 */

const ROUTES = readFileSync(
  fileURLToPath(new URL("../../../backend/app/api/routes.py", import.meta.url)),
  "utf-8",
);

/** Las claves de las capacidades del backend: las cadenas con guion que abren cada tupla. */
function backendCapabilities(): string[] {
  const start = ROUTES.indexOf("capabilities = [");
  const end = ROUTES.indexOf("manual = {", start);
  expect(start, "la lista de capacidades en routes.py").toBeGreaterThan(-1);
  expect(end).toBeGreaterThan(start);
  return [...ROUTES.slice(start, end).matchAll(/^\s*"([a-z]+(?:-[a-z]+)+)",$/gm)].map((m) => m[1] ?? "");
}

describe("capacidad de vigilancia: dibujos y señales", () => {
  it("cada capacidad del backend tiene su dibujo, y ninguno se repite", () => {
    const keys = backendCapabilities();
    expect(keys).toContain("personal-baseline");
    expect(keys).toContain("record-integrity");
    const drawn = new Set<string>();
    for (const key of keys) {
      const pictogram = capabilityPictogram(key);
      expect(pictogram, key).not.toBe(UNKNOWN_MARK.pictogram);
      drawn.add(String(pictogram));
    }
    expect(drawn.size).toBe(keys.length);
  });

  it("una capacidad que la interfaz no conoce va con su palabra y el dibujo de desconocido", () => {
    expect(capabilityPictogram("telepathy")).toBe(UNKNOWN_MARK.pictogram);
  });

  it("disponible es hecho sin color; sin datos es dato ausente en cian; manual es precaucion en amarillo", () => {
    expect(AVAILABLE_MARK).toEqual(mark("check", null));
    expect(causeMark("missing")).toEqual(mark("ring-dotted", "cyan"));
    expect(causeMark("manual")).toEqual(mark("shape-triangle", "yellow"));
    expect(isKnownCause("missing")).toBe(true);
    expect(isKnownCause("manual")).toBe(true);
  });

  it("una causa que la interfaz no conoce lleva la marca de desconocido, no la de otra ni un fallo", () => {
    // Este panel es el que dice que no se vigila: no puede ser el que tumbe la consola.
    for (const odd of ["budget", "", "toString"]) {
      expect(causeMark(odd), odd).toEqual(UNKNOWN_MARK);
      expect(isKnownCause(odd), odd).toBe(false);
    }
  });

  it("«reducida» lleva la marca de su causa: dato ausente si falta alguno, manual si solo hay de esas", () => {
    const at = (...causes: ("missing" | "manual" | null)[]) => causes.map((cause) => ({ cause }));
    expect(reducedMark(at(null, "manual", "missing"))).toEqual(causeMark("missing"));
    expect(reducedMark(at(null, "manual"))).toEqual(causeMark("manual"));
    expect(reducedMark(at(null))).toEqual(UNKNOWN_MARK);
    expect(reducedMark([])).toEqual(UNKNOWN_MARK);
  });

  it("la franja y el panel de vigilancia sacan «reducida» de la misma funcion (un concepto, un dibujo)", () => {
    for (const file of ["./MonitoringBasis.tsx", "../components/StatusStrip.tsx"]) {
      const source = readFileSync(fileURLToPath(new URL(file, import.meta.url)), "utf-8");
      expect(source, file).toContain("reducedMark(monitoring.capabilities)");
      expect(source, file).not.toContain('causeMark("missing");');
    }
  });

  it("los paneles de vigilancia y de base usan estas tablas y no escriben ningun glifo de texto", () => {
    // Los dos paneles viven en su fichero desde el tablero por secciones (2026-11-07).
    const source = readFileSync(fileURLToPath(new URL("./MonitoringBasis.tsx", import.meta.url)), "utf-8");
    const start = source.indexOf("function MonitoringPanel(");
    expect(start).toBeGreaterThan(-1);
    const panels = source.slice(start);
    for (const used of [
      "capabilityPictogram(item.key)",
      "causeMark(",
      "isKnownCause(",
      "AVAILABLE_MARK",
      "contextPictogram(key)",
    ]) {
      expect(panels).toContain(used);
    }
    expect(panels).not.toMatch(/[✓△◌●◐▷↗↘]/);
  });
});
