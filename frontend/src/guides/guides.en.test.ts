/**
 * «Cómo medir y glosario» en inglés (`lib/i18n.ts`): los rótulos del panel y las palabras que
 * cuenta la interfaz. Los pasos, las citas y las definiciones son del backend.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { MeasurementGuide } from "../lib/api";
import { GuidesCounts, GuidesPanel } from "./GuidesPanel";
import { GUIDES_LABELS, guideStepsWord, guideSummary } from "./guides";

const guide = (steps: number) =>
  ({ id: "g", title: "TITULO-DEL-BACKEND", indicators: [], steps: Array.from({ length: steps }, () => ({ text: "PASO", basis: [] })), in_flight: [], not_found: [] }) as unknown as MeasurementGuide;

describe("las guías en inglés", () => {
  it("los rótulos del panel", () => {
    expect(GUIDES_LABELS).toEqual({
      panel: "How to measure and glossary",
      inFlight: "In flight",
      notFound: "Searched and not found",
      sources: "Source of this step",
      glossary: "Glossary",
      indicators: "Indicators",
    });
  });

  it("cuántos pasos lleva una guía, en singular, en plural y sin ninguno", () => {
    expect(guideStepsWord(guide(1))).toBe("1 step");
    expect(guideStepsWord(guide(2))).toBe("2 steps");
    expect(guideStepsWord(guide(0))).toBe("no sourced steps");
    expect(guideSummary(guide(2))).toBe("TITULO-DEL-BACKEND · 2 steps");
  });

  it("el panel mientras carga y las fichas del tablero", () => {
    const panel = renderToStaticMarkup(createElement(GuidesPanel));
    expect(panel).toContain('aria-label="How to measure and glossary"');
    expect(panel).not.toContain("Cómo medir");
    const counts = renderToStaticMarkup(createElement(GuidesCounts, { guides: 10, terms: 14 }));
    expect(counts).toContain('aria-label="Guides and glossary"');
    for (const word of ["Guides", "Glossary", "terms"]) expect(counts, word).toContain(word);
    expect(counts).not.toMatch(/Guías|Glosario|términos/);
    const waiting = renderToStaticMarkup(createElement(GuidesCounts, { guides: "loading", terms: "failed" }));
    expect(waiting).toContain("loading");
    expect(waiting).toContain("not available");
    expect(waiting).not.toMatch(/cargando|no disponible/);
  });
});
