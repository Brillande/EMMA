import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { isPictogramName } from "../icons/registry";
import { UNKNOWN_MARK, mark } from "../lib/marks";
import { ENTRY_GROUPS, entryMark, knownEntryTypes } from "./ledgerEntries";

/**
 * Cada tipo de asiento del ledger tiene su grupo, y cada grupo nombra solo tipos que existen. Los
 * tipos se leen de los propios ficheros de Python: si el backend gana un asiento, esta prueba lo
 * dice antes de que la tabla de auditoría lo pinte como desconocido.
 */

const BACKEND = ["../../../backend/app/core/storage.py", "../../../backend/app/core/ledger.py"].map((path) =>
  fileURLToPath(new URL(path, import.meta.url)),
);

/** Los valores de las constantes `*_ENTRY_TYPE = "..."` del backend. */
function backendEntryTypes(): string[] {
  const found = new Set<string>();
  for (const path of BACKEND) {
    const source = readFileSync(path, "utf8");
    for (const match of source.matchAll(/^[A-Z0-9_]+_ENTRY_TYPE = "([^"]+)"/gm)) found.add(match[1] ?? "");
  }
  if (found.size === 0) throw new Error("no se encuentra ningún *_ENTRY_TYPE en el backend");
  return [...found].sort();
}

describe("los tipos de asiento del registro firmado", () => {
  it("se leen del backend, no de una lista vacía", () => {
    const types = backendEntryTypes();
    expect(types.length).toBeGreaterThan(20);
    expect(types).toContain("vital-observation");
    expect(types).toContain("redaction");
  });

  it("cada tipo del backend está en un grupo, y ningún grupo nombra un tipo que no existe", () => {
    expect([...knownEntryTypes()].sort()).toEqual(backendEntryTypes());
  });

  it("ningún tipo está en dos grupos", () => {
    const all = Object.values(ENTRY_GROUPS).flat();
    expect(new Set(all).size).toBe(all.length);
  });

  it("cada grupo es un pictograma registrado y cada marca va sin color: un asiento no es una alerta", () => {
    for (const [pictogram, types] of Object.entries(ENTRY_GROUPS)) {
      if (!isPictogramName(pictogram)) throw new Error(`«${pictogram}» no es un pictograma registrado`);
      for (const type of types) expect(entryMark(type)).toEqual(mark(pictogram, null));
    }
  });

  it("una lectura lleva la forma de «medido», y la instantánea de una proyección la cámara de su comprobación", () => {
    expect(entryMark("vital-observation").pictogram).toBe("dot-filled");
    expect(entryMark("prediction-snapshot").pictogram).toBe("camera");
  });

  it("un tipo que la interfaz no conoce se enseña con la marca de desconocido, no con un grupo supuesto", () => {
    expect(entryMark("asiento-nuevo")).toBe(UNKNOWN_MARK);
  });
});
