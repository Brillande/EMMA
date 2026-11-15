import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, taggedPictogram, textNodes } from "../advisor/visibleText";
import { LookContext } from "../components/BoardOnly";
import type { CrewStatus } from "../lib/api";
import { DoseMeter } from "./DoseMeter";

/**
 * El dosímetro de carrera: la cifra y el límite son del backend; sin dosis se dice que falta, en
 * cian y con su anillo, y no se pinta un cero. El trébol acompaña al título, sin color. La barra
 * es el medidor neutro del núcleo (§5.33): sin color, y el nivel lo decide el backend en su
 * dominio, no la barra. En el tablero (la concha de la maqueta, que es la de las pruebas) la cifra
 * va en una ficha grande con el medidor debajo; en la clásica sigue el párrafo de siempre.
 */

const render = (dose: CrewStatus["dose"]) => renderToStaticMarkup(createElement(DoseMeter, { dose }));
const renderClassic = (dose: CrewStatus["dose"]) =>
  renderToStaticMarkup(createElement(LookContext.Provider, { value: "classic" }, createElement(DoseMeter, { dose })));

const given: CrewStatus["dose"] = {
  cumulative_msv: 150,
  limit_msv: 600,
  fraction: 0.25,
  source: "observation",
  observation_type: "inferred",
};

describe("<DoseMeter>", () => {
  it("el título lleva el trébol junto a la palabra, y la cifra su rótulo INFERIDO", () => {
    const html = render(given);
    expect(html).toMatch(taggedPictogram("h2", "trefoil", "Dosis de carrera"));
    expect(html).toContain('data-pictogram="dot-half"');
    const heading = html.split("<h2>")[1]!.split("</h2>")[0]!;
    expect(textNodes(heading)).toEqual(["Dosis de carrera", "INFERIDO"]);
  });

  it("la barra es neutra y dice la cifra sobre el límite", () => {
    const html = render(given);
    // La ficha del tablero: la cifra con su unidad, el tanto por ciento y el medidor colgando.
    expect(html).toMatch(
      /<span class="num">150,0<\/span> <span class="stat-unit">mSv<\/span><\/span><span class="secondary num">\(25,0 %\)<\/span><div class="meter-block">/,
    );
    expect(html).toContain(
      '<div class="meter" role="meter" aria-label="Dosis acumulada sobre el límite de carrera" aria-valuemin="0" aria-valuemax="600" aria-valuenow="150">',
    );
    expect(html).toContain('<div class="meter-fill" style="width:25%"></div>');
    // Neutra: ni una clase de color en todo el panel con la dosis dentro del límite.
    expect(html).not.toMatch(/c-(red|yellow|blue|gray|cyan|magenta|green|text)/);
  });

  it("por encima del límite no se dibuja llena: barra vacía, la flecha con la cifra, sin color", () => {
    const html = render({ ...given, cumulative_msv: 650, fraction: 650 / 600 });
    expect(html).toContain('class="meter meter-oor"');
    expect(html).not.toContain("meter-fill");
    expect(html).toMatch(markedHtml("arrow-up", "108,3 %"));
    // La cifra una vez: junto a la flecha, y no también entre paréntesis tras los mSv (§5.33.12).
    expect(html).not.toContain("(108,3 %)");
    // (la otra vez que aparece es el `aria-valuetext` de la barra, que no se ve).
    expect(html.match(/>[^<]*108,3 %/g)).toHaveLength(1);
    expect(html).toMatch(/<span class="num">650,0<\/span> <span class="stat-unit">mSv<\/span><\/span><div class="meter-block">/);
    expect(html).not.toMatch(/c-(red|yellow|blue|gray|cyan|magenta|green|text)/);
  });

  it("sin límite positivo no hay escala: queda la cifra, y el medidor no lanza", () => {
    const html = render({ ...given, limit_msv: 0 });
    expect(html).toContain('<span class="num">150,0</span> <span class="stat-unit">mSv</span>');
    expect(html).not.toContain('role="meter"');
  });

  it("en la concha clásica sigue el párrafo de siempre, sin ficha", () => {
    const html = renderClassic(given);
    expect(html).toMatch(/<p><span class="num">150,0<\/span> mSv <span class="secondary num">\(25,0 %\)<\/span><\/p><div class="meter-block">/);
    expect(html).not.toContain("stat-tile");
    const over = renderClassic({ ...given, cumulative_msv: 650, fraction: 650 / 600 });
    expect(over).toMatch(/<p><span class="num">650,0<\/span> mSv<\/p>/);
    expect(renderClassic({ ...given, limit_msv: 0 })).not.toContain('role="meter"');
  });

  it("sin dosis facilitada: cian con el anillo punteado, sin barra, sin rótulo y sin cero", () => {
    const html = render({ ...given, cumulative_msv: null, fraction: null });
    expect(html).toMatch(
      /<p><span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted"[^>]*>[\s\S]*?<\/svg>Sin dato de dosis acumulada: no se ha facilitado, y no se supone cero\.<\/span><\/p>/,
    );
    expect(html).not.toContain('role="meter"');
    expect(html).not.toContain("INFERIDO");
    expect(html).not.toContain("0 de 600");
    // El límite se dice igual: es del backend, no de la dosis.
    expect(html).toContain('<span class="num">600</span> mSv.');
  });

  it("ningún carácter de forma ni trazo queda escrito: toda forma es un pictograma junto a su palabra", () => {
    const source = readFileSync(fileURLToPath(new URL("./DoseMeter.tsx", import.meta.url)), "utf8");
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    expect(code).not.toMatch(/[○◇△■□●◐▷◌⊘✕✓≠≈]/);
    expect(code).not.toMatch(/<svg|<path|aria-hidden/);
  });
});
