import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textNodes } from "../advisor/visibleText";
import { LookContext } from "../components/BoardOnly";
import type { Indicator } from "../lib/api";
import { displayUnit, formatNumber } from "../lib/format";
import { type Point, TrendChart, receivedInWindow, windowExtent } from "./TrendChart";

/*
 * La tira de cifras de cada gráfica de Tierra (tablero, 2026-11-07): sale de lo mismo que se dibuja
 * —lo recibido dentro de la ventana—, con los decimales y la unidad del catálogo. Lo que está a
 * bordo y no ha llegado no cuenta; sin lecturas, la marca de dato ausente y nunca un cero; solo bajo
 * la concha de la maqueta y solo en Tierra. El lienzo de uPlot no se monta aquí (sin efectos).
 */

const indicator = {
  key: "heart_rate",
  display: "Heart rate",
  display_es: "NOMBRE-DEL-BACKEND",
  display_es_origin: "emma",
  display_es_origin_display: "EMMA",
  unit: "/min",
  domain: "cardio",
  system: "http://loinc.org",
  is_standard_code: true,
  reference_low: 50,
  reference_high: 90,
  reference_basis: null,
  critical_low: null,
  critical_high: null,
  decimals: 1,
  measurement_cost: null,
} as Indicator;

const points: Point[] = [
  { met: 50, value: 99, confidence: 1 }, // antes de la ventana
  { met: 120, value: 61.25, confidence: 0.2 },
  { met: 300, value: 72.5, confidence: 0.9 },
  { met: 200, value: 58, confidence: null },
  { met: 900, value: 120, confidence: 1 }, // a bordo, aún no recibido
];

const render = (over: Record<string, unknown> = {}, look: "classic" | "reference" = "reference") =>
  renderToStaticMarkup(
    createElement(
      LookContext.Provider,
      { value: look },
      createElement(TrendChart, {
        indicator,
        points,
        receivedUntil: 400,
        onboardUntil: 1000,
        windowSeconds: 900,
        lowConfidence: { threshold: 0.5, label: "PALABRA-DUDOSA" },
        ...over,
      }),
    ),
  );

const strip = (html: string) => /<dl class="ref-stats trend-stats"[\s\S]*?<\/dl>/.exec(html)?.[0] ?? "";

describe("cifras de la ventana", () => {
  it("solo lo recibido dentro de la ventana; la última por tiempo de misión, no por orden", () => {
    const received = receivedInWindow(points, 100, 400);
    expect(received.map((p) => p.met)).toEqual([120, 300, 200]);
    expect(windowExtent(received)).toEqual({ last: points[2], low: points[3], high: points[2] });
    expect(windowExtent([])).toBeNull();
    // Un valor que no es una cifra no entra: formatearlo rompería la consola entera.
    expect(windowExtent([{ met: 10, value: Number.NaN }, { met: 5, value: 3 }])).toEqual({
      last: { met: 5, value: 3 },
      low: { met: 5, value: 3 },
      high: { met: 5, value: 3 },
    });
    expect(windowExtent([{ met: 10, value: Number.POSITIVE_INFINITY }])).toBeNull();
  });

  it("la última, el mínimo o el máximo de baja confianza llevan el triángulo, como en la gráfica", () => {
    const html = strip(render({ points: [...points, { met: 350, value: 80, confidence: 0.1 }] }));
    const doubtful = new RegExp(
      `<span class="mark c-yellow" title="PALABRA-DUDOSA"><svg[^>]*data-pictogram="shape-triangle"[^>]*>.*?</svg><span class="num">${formatNumber(80, 1)}</span></span>`,
      "g",
    );
    // Es la última y el máximo: dos veces.
    expect(html.match(doubtful)).toHaveLength(2);
    expect(html).toContain(`<span class="num">${formatNumber(58, 1)}</span> `);
  });

  it("la tira dice la última lectura, cuántas hay, las dudosas y el mínimo y el máximo, con la unidad", () => {
    const html = strip(render());
    const unit = displayUnit("/min");
    expect(html).toContain('role="group" aria-label="Cifras de la ventana"');
    expect(textNodes(html)).toEqual([
      "Último recibido",
      formatNumber(72.5, 1),
      unit,
      "Lecturas",
      "3",
      "PALABRA-DUDOSA",
      "1",
      "Mínimo",
      formatNumber(58, 1),
      unit,
      "Máximo",
      formatNumber(72.5, 1),
      unit,
    ]);
    expect(html).toContain(`<span class="num">${formatNumber(72.5, 1)}</span> ${unit}`);
    // Las dudosas llevan el triángulo amarillo de la leyenda; la cifra dice cuántas.
    expect(html).toMatch(/<span class="mark c-yellow"><svg[^>]*data-pictogram="shape-triangle"/);
  });

  it("sin dudosas, la cifra sola y sin amarillo; sin umbral del backend, la casilla no aparece", () => {
    const none = strip(render({ points: points.map((p) => ({ ...p, confidence: 1 })) }));
    expect(textNodes(none)).toContain("PALABRA-DUDOSA");
    expect(none).not.toContain("c-yellow");
    const unknown = strip(render({ lowConfidence: null }));
    expect(textNodes(unknown)).not.toContain("PALABRA-DUDOSA");
  });

  it("sin lecturas recibidas: cero lecturas y el dato ausente en cian, nunca un cero por valor", () => {
    const html = strip(render({ points: [] }));
    const words = textNodes(html);
    expect(words.filter((word) => word === "sin dato")).toHaveLength(3);
    expect(html.match(/class="mark c-cyan"/g)).toHaveLength(3);
    expect(words).toContain("0");
  });

  it("ni en la consola clásica ni a bordo", () => {
    expect(strip(render({}, "classic"))).toBe("");
    expect(strip(render({ onboard: true }))).toBe("");
  });
});
