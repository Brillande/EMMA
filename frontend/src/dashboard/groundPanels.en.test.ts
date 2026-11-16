/**
 * Las proyecciones, la línea base personal, las preguntas de los gemelos y «qué se comparte» en
 * inglés (`lib/i18n.ts`): solo los rótulos que escribe la interfaz; las frases son del backend.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { CrewStatus, Sharing } from "../lib/api";
import { BaselineProfileView } from "./BaselineProfilePanel";
import { Predictions } from "./Predictions";
import { SharingPanel, SharingView } from "./SharingPanel";
import { TwinQuestionsView } from "./TwinQuestions";

const render = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element);

describe("paneles de Tierra del tablero, en inglés", () => {
  it("las proyecciones: la frase entera en inglés, con el nombre y la base del backend", () => {
    const predictions = [
      { key: "heart-rate", display: "Heart rate", display_es: "NOMBRE-A", unit: "/min", decimals: 1, horizon_weeks: 4, projected_change: 3, projected_change_low: 1, projected_change_high: 5, concerning: true, basis: "BASE-DEL-BACKEND" },
      { key: "sleep-duration", display: "Sleep", display_es: "NOMBRE-B", unit: "h", decimals: 1, horizon_weeks: 4, projected_change: -0.5, projected_change_low: -1, projected_change_high: 0, concerning: false, basis: "BASE-DEL-BACKEND" },
    ] as unknown as CrewStatus["predictions"];
    const html = render(createElement(Predictions, { predictions }));
    expect(html).toContain('aria-label="Projections"');
    expect(html).toContain('<span class="num">up 3.0</span>');
    expect(html).toContain('<span class="num">down 0.5</span>');
    expect(html).toMatch(/in <span class="num">4<\/span> weeks/);
    expect(html).toContain("(margin ");
    expect(html).toContain("NOMBRE-A");
    expect(html).not.toMatch(/Proyecciones|sube|baja|semanas|margen/);

    const few = render(createElement(Predictions, { predictions, onlyConcerning: true }));
    expect(few).toContain("more drifts, real but not worrying; they are shown in the Earth console.");
    expect(few).not.toContain("derivas");
  });

  it("la línea base personal y las preguntas de los gemelos: su título, mientras cargan", () => {
    const baseline = render(createElement(BaselineProfileView, { data: null, unavailable: null }));
    expect(baseline).toContain('aria-label="Personal baseline"');
    expect(baseline).not.toContain("Línea base");
    const twins = render(createElement(TwinQuestionsView, { data: null, unavailable: null }));
    expect(twins).toContain('aria-label="The twins&#x27; five questions"');
    expect(twins).not.toContain("gemelos");
  });

  it("qué se comparte: título, espera y los rótulos de cada ficha", () => {
    const waiting = render(createElement(SharingPanel));
    expect(waiting).toContain('aria-label="What is shared and what is not"');
    expect(waiting).toContain("Checking what is shared…");
    expect(waiting).not.toMatch(/Qué se comparte|Consultando/);

    const body = {
      note: "NOTA-DE-LA-TABLA",
      destinations: [
        { id: "internet", label: "SALE-A-INTERNET" },
        { id: "ground", label: "LO-VE-TIERRA" },
      ],
      items: [
        { id: "readings", title: "TITULO", destination: "ground", destination_text: "DESTINO", text: "TEXTO", enforcement: "partial", enforcement_text: "GRADO", limit: "LIMITE", enforced_by: ["app.modulo"] },
      ],
      internet: { offline: true, offline_text: "AHORA-SIN-RED", purposes: [{ purpose: "space-weather", what: "QUE", carries: "LLEVA", hosts: ["api.nasa.gov"] }] },
      ground_cut: { note: "NOTA-DEL-CORTE", routes: [{ path: "/api/status", direction: "down", direction_text: "BAJA" }] },
    } as unknown as Sharing;
    const html = render(createElement(SharingView, { body }));
    for (const word of ["What is left out", "Where it is enforced", "Purposes and hosts", "Routes with the delay cut", "NOTA-DE-LA-TABLA", "LO-VE-TIERRA"]) {
      expect(html, word).toContain(word);
    }
    expect(html).not.toMatch(/Qué queda fuera|Dónde se impone|Propósitos|Rutas con/);
  });
});
