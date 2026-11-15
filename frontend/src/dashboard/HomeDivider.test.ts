import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { HOME_SECONDARY_KEY, type PreferenceStore, readHomeSecondary, writeHomeSecondary } from "../components/displayModes";
import { HomeDivider, hasNewAlert } from "./HomeBoard";

/**
 * La raya de «Inicio» que separa lo principal (de RIDGE para arriba) de lo secundario (rutas y pie),
 * con el mando que lo pliega (2026-11-14). El mando dice qué hará y qué pliega, lleva su dibujo y su
 * estado (`aria-expanded`); la preferencia sale plegada si no hay nada guardado o el almacén falla.
 */

const render = (open: boolean) => renderToStaticMarkup(createElement(HomeDivider, { open, onToggle: () => undefined }));

function memoryStore(): PreferenceStore & { values: Map<string, string> } {
  const values = new Map<string, string>();
  return { values, getItem: (key) => values.get(key) ?? null, setItem: (key, value) => void values.set(key, value) };
}

describe("HomeDivider", () => {
  it("abierto: ofrece ocultar, con aria-expanded y lo que pliega", () => {
    const html = render(true);
    expect(html).toContain('class="ref-divider"');
    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain("Ocultar lo secundario");
    expect(html).toContain("Rutas espaciales, divulgación y extensión");
    expect(html).not.toContain("modo esencial");
    expect(html).toContain('class="command ref-divider-go"');
  });

  it("plegado: ofrece mostrar", () => {
    const html = render(false);
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain("Mostrar lo secundario");
  });
});

describe("preferencia de lo secundario de «Inicio»", () => {
  it("sin nada guardado, sin almacén o con almacén roto, plegado", () => {
    expect(readHomeSecondary(memoryStore())).toBe(false);
    expect(readHomeSecondary(null)).toBe(false);
    const broken: PreferenceStore = {
      getItem: () => {
        throw new Error("sin acceso");
      },
      setItem: () => {
        throw new Error("sin acceso");
      },
    };
    expect(readHomeSecondary(broken)).toBe(false);
    expect(() => writeHomeSecondary(broken, false)).not.toThrow();
  });

  it("guarda y relee el plegado", () => {
    const store = memoryStore();
    writeHomeSecondary(store, false);
    expect(store.values.get(HOME_SECONDARY_KEY)).toBe("false");
    expect(readHomeSecondary(store)).toBe(false);
    writeHomeSecondary(store, true);
    expect(readHomeSecondary(store)).toBe(true);
  });
});

describe("una alerta nueva pliega lo secundario", () => {
  it("solo cuenta la que no estaba la vez anterior", () => {
    expect(hasNewAlert(new Set(), [])).toBe(false);
    expect(hasNewAlert(new Set(), ["a"])).toBe(true);
    expect(hasNewAlert(new Set(["a"]), ["a"])).toBe(false);
    expect(hasNewAlert(new Set(["a", "b"]), ["a"])).toBe(false);
    expect(hasNewAlert(new Set(["a"]), ["a", "b"])).toBe(true);
  });
});
