import { type ComponentType, createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DAY_SECONDS, ImpactBar, LevelPill, RangeBar, Ring, Segments, Sparkline, levelTint, levelToken } from "./HomeCharts";

/**
 * Las piezas del tablero que las secciones montan con sus datos (2026-11-07): cada una dice lo suyo
 * con texto, no inventa escala y lanza antes que dibujar algo falso.
 */

const html = (type: ComponentType<never>, props: object) =>
  renderToStaticMarkup(createElement(type as ComponentType<object>, props));

describe("Ring", () => {
  it("dice cuántos de cuántos y de qué", () => {
    const out = html(Ring, { done: 3, total: 9, label: "medidas al día", children: "x" });
    expect(out).toContain('role="img" aria-label="3 de 9 medidas al día"');
  });
});

describe("Sparkline", () => {
  const until = Date.UTC(2026, 10, 7);
  const readings = [
    { at: until - 3 * DAY_SECONDS * 1000, value: 1 },
    { at: until - 2 * DAY_SECONDS * 1000, value: 2 },
  ];

  it("por defecto solo dibuja las últimas 24 h; con ventana, lo que la ventana abarca", () => {
    expect(html(Sparkline, { readings, until })).not.toContain("<path");
    expect(html(Sparkline, { readings, until, windowMs: 7 * DAY_SECONDS * 1000 })).toContain("<path d=");
  });
});

describe("Segments e ImpactBar", () => {
  it("un segmento por elemento con su tono; sin nivel, gris; y son adorno", () => {
    const out = html(Segments, { tones: ["yellow", null], titles: ["Inmune", "Óseo"] });
    expect(out).toContain('aria-hidden="true"');
    expect(out).toContain('data-tone="yellow" title="Inmune"');
    expect(out).toContain('data-tone="gray" title="Óseo"');
  });

  it("la barra recorta a 0..1 y solo va amarilla si el backend lo dice; sin proporción, lanza", () => {
    expect(html(ImpactBar, { share: 2 })).toContain('style="width:100.0%"');
    expect(html(ImpactBar, { share: 0.25, concerning: true })).toContain('data-tone="yellow"');
    expect(html(ImpactBar, { share: 0.25 })).not.toContain("data-tone");
    expect(() => html(ImpactBar, { share: Number.NaN })).toThrow(/sin proporción/);
  });
});

describe("RangeBar", () => {
  it("un tramo con su marca y su texto; lanza con el tramo al revés o sin escala", () => {
    const out = html(RangeBar, { low: 2, high: 6, min: 0, max: 10, marker: 5, label: "de 2 a 6, medido 5" });
    expect(out).toContain('role="img" aria-label="de 2 a 6, medido 5"');
    expect(out).toContain('class="board-range-span" style="left:20.0%;width:40.0%"');
    expect(out).toContain('class="board-range-marker" style="left:50.0%"');
    expect(() => html(RangeBar, { low: 6, high: 2, min: 0, max: 10, label: "x" })).toThrow(RangeError);
    expect(() => html(RangeBar, { low: 1, high: 2, min: 5, max: 5, label: "x" })).toThrow(RangeError);
  });
});

describe("niveles", () => {
  it("el token es el real del nivel; desconocido, null y gris; la píldora lleva palabra y cifra", () => {
    expect(levelToken("watch")).toBe("blue");
    expect(levelToken("nominal")).toBe("text");
    expect(levelToken("otra-cosa")).toBeNull();
    expect(levelTint(undefined)).toEqual({ "--lvl": "var(--c-gray)" });
    const out = html(LevelPill, { level: "concern", count: 2 });
    expect(out).toMatch(/^<span class="ref-pill board-pill" style="--lvl:var\(--c-yellow\)">/);
    expect(out).toContain('<span class="num">2</span>');
  });
});
