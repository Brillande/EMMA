import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it } from "vitest";

import type { PreferenceStore } from "./displayModes";
import { FoldDivider, Folded, foldKey, readFold, resetFoldsForTests, setFoldOpen, writeFold } from "./SecondaryFold";

/**
 * La raya plegable de cada pestaña (2026-11-15): plegada por defecto como «Inicio», recordada por
 * equipo y tolerante a un almacén roto; un panel plegado no pinta nada.
 */

function memoryStore(): PreferenceStore & { values: Map<string, string> } {
  const values = new Map<string, string>();
  return { values, getItem: (key) => values.get(key) ?? null, setItem: (key, value) => void values.set(key, value) };
}

const broken: PreferenceStore = {
  getItem: () => {
    throw new Error("sin acceso");
  },
  setItem: () => {
    throw new Error("sin acceso");
  },
};

beforeEach(() => resetFoldsForTests());

describe("preferencia de la raya", () => {
  it("sin nada guardado, sin almacén o con almacén roto, plegada", () => {
    expect(readFold(memoryStore(), "crew.x")).toBe(false);
    expect(readFold(null, "crew.x")).toBe(false);
    expect(readFold(broken, "crew.x")).toBe(false);
    expect(() => writeFold(broken, "crew.x", true)).not.toThrow();
  });

  it("guarda y relee por id", () => {
    const store = memoryStore();
    writeFold(store, "crew.x", true);
    expect(store.values.get(foldKey("crew.x"))).toBe("true");
    expect(readFold(store, "crew.x")).toBe(true);
    expect(readFold(store, "crew.y")).toBe(false);
  });
});

describe("FoldDivider y Folded", () => {
  const panel = createElement("p", null, "panel secundario");

  it("plegado: la raya ofrece mostrar y el panel no se pinta", () => {
    const divider = renderToStaticMarkup(createElement(FoldDivider, { id: "crew.t", what: "Lo de abajo" }));
    expect(divider).toContain('aria-expanded="false"');
    expect(divider).toContain("Mostrar lo secundario");
    expect(divider).toContain("Lo de abajo");
    expect(renderToStaticMarkup(createElement(Folded, { id: "crew.t", children: panel }))).toBe("");
  });

  it("desplegado: ofrece ocultar y el panel se pinta; otra raya no se entera", () => {
    setFoldOpen("crew.t", true);
    expect(renderToStaticMarkup(createElement(FoldDivider, { id: "crew.t", what: "x" }))).toContain("Ocultar lo secundario");
    expect(renderToStaticMarkup(createElement(Folded, { id: "crew.t", children: panel }))).toContain("panel secundario");
    expect(renderToStaticMarkup(createElement(Folded, { id: "crew.u", children: panel }))).toBe("");
  });
});
