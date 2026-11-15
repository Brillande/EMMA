import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml } from "../advisor/visibleText";
import { ABOVE_SCALE_MARK, BELOW_SCALE_MARK, UNAVAILABLE_MARK, mark } from "../lib/marks";
import { Meter, type MeterProps } from "./Meter";

/**
 * El medidor neutro (§5.33): barra sin color con significado, banda de referencia opcional, y el
 * patrón de Open MCT para lo que se sale de la escala: no se dibuja recortado, se señala.
 */

const meter = (props: MeterProps) => renderToStaticMarkup(createElement(Meter, props));
const OUT = { mark: mark("arrow-up", null), word: "POR-ENCIMA-DE-LA-ESCALA" };

describe("<Meter>", () => {
  it("dentro de escala: role meter con sus valores y el relleno proporcional", () => {
    const html = meter({ value: 25, max: 200, label: "Dosis" });
    expect(html).toMatch(/^<div class="meter-block"><div class="meter" role="meter"/);
    expect(html).toContain('<div class="meter" role="meter" aria-label="Dosis" aria-valuemin="0" aria-valuemax="200" aria-valuenow="25">');
    expect(html).toContain('<div class="meter-fill" style="width:12.5%"></div>');
    expect(html).not.toContain("meter-band");
  });

  it("con mínimo propio y banda de referencia", () => {
    const html = meter({ value: 60, min: 40, max: 140, label: "FC", band: { low: 50, high: 100 } });
    expect(html).toContain('<div class="meter-band" style="left:10%;width:50%"></div>');
    expect(html).toContain('style="width:20%"');
  });

  it("fuera de escala: sin relleno, borde discontinuo y la marca con su palabra al lado", () => {
    const html = meter({ value: 250, max: 200, label: "Dosis", outOfRange: OUT });
    expect(html).toContain('class="meter meter-oor"');
    expect(html).not.toContain("meter-fill");
    // ARIA: el valor ahora cae dentro de la escala (el extremo que se pasó); la palabra, en valuetext.
    expect(html).toContain('aria-valuenow="200"');
    expect(html).toContain('aria-valuetext="POR-ENCIMA-DE-LA-ESCALA"');
    expect(html).toMatch(markedHtml("arrow-up", "POR-ENCIMA-DE-LA-ESCALA"));
  });

  it("sin marca propia, la flecha la elige el medidor contra su escala, también con mínimo propio", () => {
    const above = meter({ value: 150, min: 40, max: 140, label: "FC", outOfRange: { word: "ARRIBA" } });
    expect(above).toMatch(markedHtml("arrow-up", "ARRIBA"));
    expect(above).toContain('aria-valuenow="140"');
    // Por debajo de un mínimo que no es cero: con la regla anterior (`value < 0`) salía hacia arriba.
    const below = meter({ value: 30, min: 40, max: 140, label: "FC", outOfRange: { word: "ABAJO" } });
    expect(below).toMatch(markedHtml("arrow-down", "ABAJO"));
    expect(below).toContain('aria-valuenow="40"');
    expect(meter({ value: -1, max: 10, label: "x", outOfRange: { word: "W" } })).toMatch(markedHtml("arrow-down", "W"));
    expect(ABOVE_SCALE_MARK).toEqual(mark("arrow-up", null));
    expect(BELOW_SCALE_MARK).toEqual(mark("arrow-down", null));
  });

  it("fuera de escala sin marca, o sin escala, lanza", () => {
    expect(() => meter({ value: -1, max: 200, label: "Dosis" })).toThrow(/fuera de escala/);
    expect(() => meter({ value: 1, min: 5, max: 5, label: "Dosis" })).toThrow(RangeError);
    expect(() => meter({ value: Number.NaN, max: 5, label: "Dosis" })).toThrow(RangeError);
    expect(() => meter({ value: 1, max: 5, label: "Dosis", band: { low: 4, high: 2 } })).toThrow(/al revés/);
  });

  it("caducado: cursiva en el bloque, que alcanza a la palabra de fuera de escala", () => {
    expect(meter({ value: 1, max: 2, label: "x", stale: true })).toMatch(/^<div class="meter-block stale">/);
    expect(meter({ value: 1, max: 2, label: "x" })).not.toContain("stale");
    const out = meter({ value: 9, max: 2, label: "x", stale: true, outOfRange: { mark: UNAVAILABLE_MARK, word: "W" } });
    expect(out).toMatch(/^<div class="meter-block stale"><div class="meter meter-oor"/);
    expect(out).toMatch(markedHtml("slash-circle", "W", "gray"));
  });

  it("sin colores con significado: ninguna clase c-* propia", () => {
    expect(meter({ value: 1, max: 2, label: "x", band: { low: 0, high: 1 } })).not.toMatch(/c-[a-z]/);
  });
});
