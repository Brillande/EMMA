import { describe, expect, it } from "vitest";

import { SETS, isPictogramName } from "../icons/registry";
import { OBSERVATION_TYPES } from "./provenance";
import {
  type Sign,
  UI_PICTOGRAMS,
  UI_SYNONYMS,
  type UiConcept,
  signPictogram,
  uiPictogram,
  withoutSign,
} from "./uiMarks";

/**
 * El vocabulario de signos de la interfaz (§5.32 c, §5.33) como prueba: un concepto, un dibujo,
 * el mismo en todo el sistema; los dibujos compartidos, declarados; y todo de los conjuntos del
 * núcleo, porque esta tabla la usa cualquier área.
 */

const CORE = ["shapes", "common", "provenance", "domains", "indicators", "ui"] as const;
const coreNames = new Set<string>(CORE.flatMap((set) => Object.keys(SETS[set])));
const entries = Object.entries(UI_PICTOGRAMS) as [UiConcept, string][];

/** Concepto agrupado por dibujo. */
function byDrawing(): Map<string, UiConcept[]> {
  const groups = new Map<string, UiConcept[]>();
  for (const [concept, name] of entries) groups.set(name, [...(groups.get(name) ?? []), concept]);
  return groups;
}

describe("la tabla concepto → dibujo", () => {
  it("cada dibujo existe y es de un conjunto del núcleo", () => {
    for (const [concept, name] of entries) {
      expect(isPictogramName(name), `${concept}: «${name}»`).toBe(true);
      expect(coreNames.has(name), `${concept}: «${name}» es de un área`).toBe(true);
    }
  });

  it("cada dibujo de `ui` tiene su concepto: ninguno huérfano", () => {
    const used = new Set<string>(Object.values(UI_PICTOGRAMS));
    for (const name of Object.keys(SETS.ui)) expect(used.has(name), name).toBe(true);
    // Veintiuno de la segunda pasada, seis del carril y los modos de pantalla (§5.40) y dos de la
    // vista que sigue la cara (la cabeza con la recta de los ojos y la cámara encendida), y el
    // micrófono con ondas de escuchar «EMMA»; y el cuadrado partido en diagonal del alto contraste.
    expect(Object.keys(SETS.ui)).toHaveLength(31);
  });

  it("todo dibujo compartido está declarado como sinónimo, y nada declarado deja de serlo", () => {
    const shared = [...byDrawing().values()]
      .filter((group) => group.length > 1)
      .map((group) => [...group].sort().join(" "))
      .sort();
    const declared = UI_SYNONYMS.map((group) => [...group.concepts].sort().join(" ")).sort();
    expect(declared).toEqual(shared);
  });

  it("cada grupo de sinónimos dice por qué, y un concepto no está en dos grupos", () => {
    const seen = new Set<UiConcept>();
    for (const group of UI_SYNONYMS) {
      expect(group.why.trim().length, group.concepts.join(" ")).toBeGreaterThan(0);
      for (const concept of group.concepts) {
        expect(seen.has(concept), concept).toBe(false);
        seen.add(concept);
      }
    }
  });

  it("lo inferido, lo predicho y lo medido llevan a propósito el dibujo de su procedencia", () => {
    expect(UI_PICTOGRAMS.inferred).toBe(OBSERVATION_TYPES.inferred.pictogram);
    expect(UI_PICTOGRAMS.predictions).toBe(OBSERVATION_TYPES.predicted.pictogram);
    expect(UI_PICTOGRAMS.measured).toBe(OBSERVATION_TYPES.measured.pictogram);
  });

  it("«elegido» es el anillo con punto de §5.32.3, y ningún área lo escribe a mano (§5.33.12)", () => {
    expect(UI_PICTOGRAMS.chosen).toBe("ring-dot");
    const sources = Object.entries(
      import.meta.glob("/src/**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }),
    ).filter(([path]) => !/\.test\.tsx?$/.test(path) && !path.startsWith("/src/icons/") && path !== "/src/lib/uiMarks.ts");
    for (const [path, source] of sources) {
      const code = String(source).replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
      expect(code.includes('"ring-dot"'), path).toBe(false);
    }
  });

  it("los que fija la decisión del usuario (2026-10-21)", () => {
    expect(UI_PICTOGRAMS.alerts).toBe("bell");
    expect(UI_PICTOGRAMS.docs).toBe("book-open");
    expect(UI_PICTOGRAMS.systems).toBe("gear");
    expect(UI_PICTOGRAMS.evidence).toBe("sheet-lines");
    expect(UI_PICTOGRAMS.divergences).toBe("not-equal");
    expect(UI_PICTOGRAMS.add).toBe("plus");
    expect(UI_PICTOGRAMS.cancel).toBe("cross");
  });
});

describe("el signo de una pieza", () => {
  it("un concepto da su dibujo de la tabla; un pictograma directo, ese mismo", () => {
    expect(uiPictogram("history")).toBe("clock-rewind");
    expect(signPictogram({ concept: "export" })).toBe("tray-arrow-down");
    expect(signPictogram({ pictogram: "domain-bone" })).toBe("domain-bone");
  });

  it("withoutSign quita el signo y deja el resto", () => {
    const props: Sign & { open: boolean } = { concept: "detail", open: true };
    expect(withoutSign(props)).toEqual({ open: true });
    const direct: Sign & { id: string } = { pictogram: "bell", id: "x" };
    expect(withoutSign(direct)).toEqual({ id: "x" });
  });
});
