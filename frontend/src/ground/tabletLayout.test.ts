import { describe, expect, it } from "vitest";

/**
 * La consola de Tierra en tableta (§5.40): los huecos y la maqueta van en `styles.css`, no en línea,
 * y toda tabla de un panel de Tierra se desplaza dentro de una caja que el teclado alcanza y el
 * lector nombra. Una tabla suelta empujaba la página hacia los lados en vertical.
 */
const SOURCES = import.meta.glob<string>("/src/ground/*.tsx", { query: "?raw", import: "default", eager: true });

describe("consola de Tierra en tableta", () => {
  it("ningún componente de Tierra lleva estilo en línea", () => {
    expect(Object.keys(SOURCES).length).toBeGreaterThan(10);
    const inline = Object.entries(SOURCES).filter(([, source]) => /\bstyle=\{/.test(source));
    expect(inline.map(([path]) => path)).toEqual([]);
  });

  it("cada tabla va en una caja desplazable con nombre y foco", () => {
    for (const [path, source] of Object.entries(SOURCES)) {
      for (const match of source.matchAll(/<table\b/g)) {
        // La caja es la etiqueta que abre justo antes de la tabla, sin nada en medio: una caja
        // anterior ya cerrada no cuenta.
        const before = source.slice(0, match.index);
        const box = /<div\b([^>]*)>\s*$/.exec(before)?.[1] ?? "";
        expect(box, `${path}: la tabla no va justo dentro de su caja`).toMatch(
          /className="[^"]*\btable-scroll\b[^"]*"/,
        );
        expect(box, path).toContain('role="region"');
        expect(box, path).toContain("tabIndex={0}");
        // El nombre, escrito tal cual o con su inglés al lado (`tr("…", "…")`, `lib/i18n.ts`).
        expect(box, path).toMatch(/aria-label=(?:"[^"]+"|\{tr\("[^"]+", "[^"]+"\)\})/);
      }
    }
  });
});
