import { describe, expect, it } from "vitest";

import { isPictogramName } from "../icons/registry";
import { domains } from "../icons/sets/domains";
import { indicators } from "../icons/sets/indicators";
import {
  FAMILY_KEYS,
  INDICATOR_FAMILIES,
  hasIndicatorFamily,
  indicatorFamily,
  indicatorKeys,
} from "./indicatorFamily";

/**
 * Lo que la tabla promete por si misma. La paridad con el catalogo del backend (ni una clave de
 * mas ni de menos) la vigila `backend/tests/test_indicator_families.py`, que lee esta tabla y la
 * compara con `CATALOG`: aqui no se guarda una copia del catalogo que haya que mantener.
 */

describe("la tabla de familias", () => {
  it("resuelve cada clave que lista, y una sola vez", () => {
    const keys = indicatorKeys();
    expect(keys.length).toBeGreaterThan(0);
    expect(new Set(keys).size).toBe(keys.length);
    for (const key of keys) {
      expect(hasIndicatorFamily(key)).toBe(true);
      expect(FAMILY_KEYS[indicatorFamily(key)]).toContain(key);
    }
  });

  it("una clave desconocida falla en vez de suponerle un dibujo, y se puede preguntar antes", () => {
    expect(hasIndicatorFamily("inventado")).toBe(false);
    expect(() => indicatorFamily("inventado")).toThrow(RangeError);
    expect(() => indicatorFamily("")).toThrow(RangeError);
  });

  it("los dos lados de un par (derecha, izquierda) van a la misma familia: la lateralidad va en el texto", () => {
    expect(indicatorFamily("onsd-right")).toBe(indicatorFamily("onsd-left"));
    expect(indicatorFamily("ijv-csa-right")).toBe(indicatorFamily("ijv-csa-left"));
    expect(indicatorFamily("grip-strength-right")).toBe(indicatorFamily("grip-strength-left"));
  });

  it("los autoinformes no llevan el tubo de muestra", () => {
    expect(indicatorFamily("symptom-burden")).toBe(indicatorFamily("mood-valence"));
    expect(indicatorFamily("symptom-burden")).not.toBe(indicatorFamily("cortisol-salivary"));
  });
});

describe("cada familia es un pictograma distinto", () => {
  it("existe en el registro y en el conjunto de indicadores, y no esta vacia", () => {
    for (const family of INDICATOR_FAMILIES) {
      expect(isPictogramName(family), family).toBe(true);
      expect(family in indicators, family).toBe(true);
      expect(FAMILY_KEYS[family].length, family).toBeGreaterThan(0);
    }
    expect(new Set(INDICATOR_FAMILIES).size).toBe(Object.keys(indicators).length);
  });

  it("ninguna familia repite el dibujo de otra ni el de un dominio", () => {
    const drawings = new Map<string, string>();
    for (const [name, def] of [...Object.entries(domains), ...Object.entries(indicators)]) {
      const key = JSON.stringify(def.elements);
      expect(drawings.has(key), `«${name}» dibuja lo mismo que «${drawings.get(key)}»`).toBe(false);
      drawings.set(key, name);
    }
  });
});
