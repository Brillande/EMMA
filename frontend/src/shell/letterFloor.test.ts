import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/*
 * El suelo de letra (0,875 rem, §5.40.1) también en las hojas de la concha de la maqueta. La prueba de
 * `lib/touchBase.test.ts` solo miraba `styles.css`, y el lote «muestra» (2026-11-08) dejó en las hojas
 * nuevas letras de 0,7-0,85 rem sin que nada saltara; el usuario pidió subirlas «si no rompe el
 * formato» y todas aguantaron. Esto impide que vuelvan a bajar. Las letras dentro de los dibujos SVG
 * de «Inicio» no están en estas hojas.
 */
const dir = fileURLToPath(new URL(".", import.meta.url));
const sheets = [
  ...readdirSync(dir)
    .filter((name) => name.endsWith(".css"))
    .map((name) => ({ name: `shell/${name}`, path: `${dir}${name}` })),
  { name: "consoleShell.css", path: fileURLToPath(new URL("../consoleShell.css", import.meta.url)) },
];

describe("suelo de letra en las hojas de la concha", () => {
  it.each(sheets)("$name: ninguna letra por debajo de 0,875 rem", ({ path }) => {
    const css = readFileSync(path, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    for (const [, value] of css.matchAll(/font-size:\s*([^;}]+)/g)) {
      const size = value?.trim() ?? "";
      if (size === "inherit") continue;
      const match = size.match(/^([\d.]+)(rem|px|em|%)$/);
      expect(match, size).not.toBeNull();
      const [, number, unit] = match ?? [];
      // En `em` o `%` es relativo al de fuera: solo puede crecer.
      const floor = unit === "px" ? 14 : unit === "rem" ? 0.875 : unit === "em" ? 1 : 100;
      expect(Number(number), size).toBeGreaterThanOrEqual(floor);
    }
  });
});
