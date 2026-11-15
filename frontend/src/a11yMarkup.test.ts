import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * Lo que encontró la pasada automática con axe-core y el árbol de accesibilidad de Chromium
 * (§5.41, 2026-11-05), convertido en reglas sobre la fuente para que no vuelva. No sustituye a
 * probar con NVDA y el Narrador (`docs/entrega/prueba-narrador.md`): mira el marcado, no lo que
 * el lector dice.
 */

const SRC = fileURLToPath(new URL(".", import.meta.url));

function sources(dir: string): { file: string; text: string }[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sources(path);
    return entry.name.endsWith(".tsx") ? [{ file: path.slice(SRC.length), text: readFileSync(path, "utf8") }] : [];
  });
}

const all = sources(SRC);

/** Las etiquetas de apertura de un elemento, también las que ocupan varias líneas. */
function openingTags(text: string, tag: string): string[] {
  // Hasta el primer `>` que no es de una flecha (`=>`) ni de una comparación dentro de llaves.
  const found: string[] = [];
  const start = new RegExp(`<${tag}\\b`, "g");
  for (const match of text.matchAll(start)) {
    let depth = 0;
    let at = match.index + match[0].length;
    for (; at < text.length; at += 1) {
      const char = text[at];
      if (char === "{") depth += 1;
      else if (char === "}") depth -= 1;
      else if (char === ">" && depth === 0) break;
    }
    found.push(text.slice(match.index, at + 1));
  }
  return found;
}

describe("marcado para el lector de pantalla (§5.41)", () => {
  it("un div o un span con aria-label lleva un rol: sin él, el nombre no se anuncia (axe aria-prohibited-attr)", () => {
    const bare = all.flatMap(({ file, text }) =>
      ["div", "span"].flatMap((tag) =>
        openingTags(text, tag)
          .filter((open) => /\saria-label=/.test(open) && !/\srole=/.test(open))
          .map((open) => `${file}: ${open.replace(/\s+/g, " ").slice(0, 120)}`),
      ),
    );
    expect(bare).toEqual([]);
  });

  it("ningún role=\"option\" fuera de un listbox que lo contenga directamente (axe aria-required-parent)", () => {
    // Las regiones del cuerpo eran `option` dentro de `<li>`: ahora son botones con `aria-pressed`.
    const anatomy = all.find(({ file }) => file.replace(/\\/g, "/") === "anatomy/AnatomyPanel.tsx")?.text ?? "";
    expect(anatomy).not.toContain('role="listbox"');
    expect(anatomy).not.toContain('role="option"');
    expect(anatomy).toMatch(/className="region"\s+aria-pressed=\{isChosen\}/);
    const options = all.filter(({ text }) => text.includes('role="option"')).map(({ file }) => file);
    expect(options).toEqual([]);
  });

  it("los bloques que se repiten en cada ficha son grupos, no regiones con el mismo nombre (axe landmark-unique)", () => {
    const card = all.find(({ file }) => file.replace(/\\/g, "/") === "advisor/RecommendationCard.tsx")?.text ?? "";
    // Una `<section>` con nombre es una región para el lector; con `role="group"`, un grupo. axe
    // 4.10 sigue marcándolas en landmark-unique (mira la etiqueta), pero el árbol de Chromium las da
    // como `group` y no salen entre los puntos de referencia (§5.41).
    expect(card).toContain('<section role="group" data-ui="recommendation-prior-response" aria-label={tr("Respuesta previa", "Prior response")}>');
    expect(card).toContain('<section role="group" data-ui="recommendation-resources" aria-label={tr("Recursos a bordo", "Onboard resources")}>');
  });
});
