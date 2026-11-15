import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/*
 * La base táctil de la hoja de estilos (§5.40.1): el tamaño de lo que se pulsa, la letra mínima y
 * el zoom libre. Se prueba sobre el texto de la hoja, como el resto de reglas de la interfaz.
 */
const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const css = read("../styles.css").replace(/\/\*[\s\S]*?\*\//g, "");
const html = read("../../index.html");

describe("base táctil", () => {
  it("44 px con ratón y 48 px con el dedo", () => {
    expect(css).toMatch(/:root \{[^}]*--touch: 44px;/);
    expect(css).toMatch(/@media \(pointer: coarse\) \{\s*:root \{\s*--touch: 48px;/);
  });

  it("el mando, el selector y los campos de texto tienen esa altura", () => {
    expect(css).toMatch(/button\.command \{[^}]*min-height: var\(--touch\);/);
    expect(css).toMatch(/:where\(\s*select,\s*textarea,\s*input:not\([^)]*\)\s*\) \{[^}]*min-height: var\(--touch\);/);
  });

  it("ninguna letra por debajo de 0,875 rem", () => {
    const sizes = [...css.matchAll(/font-size:\s*([^;}]+)/g)].map(([, value]) => value?.trim() ?? "");
    expect(sizes.length).toBeGreaterThan(10);
    for (const size of sizes) {
      if (size === "inherit") continue;
      const match = size.match(/^([\d.]+)(rem|px|em|%)$/);
      // Solo tamaños sencillos: un `calc()`, una palabra (`smaller`) o algo nuevo se mira a mano.
      expect(match, size).not.toBeNull();
      const [, value, unit] = match ?? [];
      const number = Number(value);
      // En `em` o `%` el tamaño es relativo al de fuera: solo puede crecer, nunca encoger.
      const floor = unit === "px" ? 14 : unit === "rem" ? 0.875 : unit === "em" ? 1 : 100;
      expect(number, size).toBeGreaterThanOrEqual(floor);
    }
    // El atajo `font:` solo hereda: un tamaño escrito ahí se saltaría la comprobación.
    for (const [, value] of css.matchAll(/[{;\s]font:\s*([^;}]+)/g)) expect(value?.trim()).toBe("inherit");
  });

  it("el cuerpo a 17 px con el dedo", () => {
    const coarse = [...css.matchAll(/@media \(pointer: coarse\) \{((?:[^{}]*\{[^{}]*\})*)\s*\}/g)].map(([, body]) => body);
    expect(coarse.some((body) => /html,\s*body \{\s*font-size: 17px;/.test(body ?? ""))).toBe(true);
  });

  it("el zoom no se bloquea y el contenido respeta los bordes de la pantalla", () => {
    const viewport = html.match(/<meta name="viewport" content="([^"]*)"/)?.[1] ?? "";
    expect(viewport).toContain("width=device-width");
    expect(viewport).toContain("viewport-fit=cover");
    expect(viewport).not.toMatch(/user-scalable\s*=\s*no|maximum-scale/);
  });
});
