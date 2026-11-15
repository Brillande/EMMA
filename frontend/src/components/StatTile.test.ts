import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, pictogramSvg, textNodes } from "../advisor/visibleText";
import { formatNumber } from "../lib/format";
import { MISSING_MARK } from "../lib/marks";
import { StatTile, type StatTileProps, StatTiles } from "./StatTile";

/** Fichas con cifra (§5.33): rótulo con signo, cifra por `formatNumber`, estado con su marca. */

const tile = (props: StatTileProps) => renderToStaticMarkup(createElement(StatTile, props));

describe("<StatTile>", () => {
  it("rótulo con su signo, cifra con formato de F.5.6 y unidad", () => {
    const html = tile({ concept: "radiation", label: "Dosis", value: 12345.678, decimals: 1, unit: "mSv" });
    expect(html).toMatch(new RegExp(`<span class="stat-label">${pictogramSvg("trefoil")}Dosis</span>`));
    const figure = formatNumber(12345.678, 1);
    expect(figure).toMatch(/^12.345,7$/);
    expect(html).toContain(`<span class="num">${figure}</span> <span class="stat-unit">mSv</span>`);
    expect(textNodes(html)).toEqual(["Dosis", figure, "mSv"]);
  });

  it("una cadena es la del backend, tal cual; sin unidad no hay hueco", () => {
    const html = tile({ pictogram: "bell", label: "Alertas", value: "3 de 5" });
    expect(html).toContain('<span class="stat-value"><span class="num">3 de 5</span></span>');
  });

  it("sin valor, el estado dice por qué; sin estado, lanza en vez de pintar un hueco", () => {
    const html = tile({ pictogram: "bell", label: "Alertas", value: null, status: { mark: MISSING_MARK, word: "Sin dato" } });
    expect(html).not.toContain("stat-value");
    expect(html).toMatch(markedHtml("ring-dotted", "Sin dato", "cyan"));
    expect(() => tile({ pictogram: "bell", label: "Alertas", value: null })).toThrow(/sin valor/);
  });

  it("lo que cuelga bajo la cifra (un medidor, una curva) va al final de la ficha", () => {
    const html = tile({ pictogram: "bell", label: "A", value: 1, children: createElement("em", null, "bajo") });
    expect(html).toMatch(/<span class="num">1<\/span><\/span><em>bajo<\/em><\/div>$/);
  });

  it("caducada, en cursiva: la clase stale en la ficha", () => {
    expect(tile({ pictogram: "bell", label: "A", value: 1, stale: true })).toMatch(/^<div class="stat-tile stale">/);
    expect(tile({ pictogram: "bell", label: "A", value: 1 })).toMatch(/^<div class="stat-tile">/);
  });
});

describe("<StatTiles>", () => {
  it("agrupa con role group y nombre accesible", () => {
    const html = renderToStaticMarkup(createElement(StatTiles, { label: "Resumen", children: "x" }));
    expect(html).toBe('<div class="stat-tiles" role="group" aria-label="Resumen">x</div>');
  });
});
