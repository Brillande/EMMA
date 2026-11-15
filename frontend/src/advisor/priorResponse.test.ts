import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { PriorAdoption, PriorResponse, Recommendation } from "../lib/api";
import { RecommendationCard } from "./RecommendationCard";
import { priorResponse } from "./recommendation";
import { markedHtml } from "./visibleText";

/**
 * La respuesta previa en la tarjeta (KB H5). La tarjeta se pinta de verdad, a HTML estatico, para
 * comprobar que los textos son los del backend, que la advertencia va siempre con la historia y
 * que el bloque no lleva ningun color: es historia, no un aviso.
 */

const CAVEAT = "Es lo que pasó después, no una prueba de que fuera por la contramedida.";
const BASIS = "La evaluación es la del seguimiento.";
const NO_PRIOR = "Sin adopciones anteriores de esta contramedida para este tripulante.";

const adoption = (index: number, override: Partial<PriorAdoption> = {}): PriorAdoption => ({
  adoption_index: index,
  adopted_at: "2026-12-01T08:00:00+00:00",
  adopted_by: "CDR",
  adopted_text: `Adoptada el 2026-12-0${index} 08:00 UTC (CDR).`,
  level_at_adoption: "concern",
  state: "closed",
  state_text: `Se cerró (CDR): motivo ${index}`,
  closed_by: "CDR",
  closed_reason: `motivo ${index}`,
  followup_checks_display: ["Duración del sueño"],
  repeated_checks_display: ["Duración del sueño"],
  checks_text: "Seguía Duración del sueño. Se repitió después de adoptarla.",
  evaluation: { outcome: "unchanged", text: `Texto de evaluación ${index}.` },
  evaluation_text: `Texto de evaluación ${index}.`,
  ...override,
});

const open = (index: number): PriorAdoption =>
  adoption(index, {
    state: "open",
    state_text: "Sigue en seguimiento: su ventana termina el 2026-12-09 08:00 UTC.",
    closed_by: null,
    closed_reason: null,
    evaluation: null,
    evaluation_text: "Sin evaluación final: el seguimiento sigue abierto.",
  });

const prior = (adoptions: PriorAdoption[]): PriorResponse => {
  const last = adoptions[adoptions.length - 1] ?? null;
  return {
    state: last === null ? "none" : last.state,
    count: adoptions.length,
    text: last === null ? NO_PRIOR : "Se ha adoptado antes para este tripulante.",
    caveat: CAVEAT,
    evaluation_basis: last === null ? null : BASIS,
    last,
    adoptions,
  };
};

const recommendation = (response: PriorResponse | null | undefined): Recommendation => ({
  domain: "behavioral",
  action: "Proteger el periodo de sueño.",
  rationale: "Sueño por debajo de lo habitual.",
  urgency: "soon",
  notify_ground: false,
  evidence: [],
  countermeasure: null,
  decision: null,
  ...(response === undefined ? {} : { prior_response: response }),
});

const render = (item: Recommendation): string =>
  renderToStaticMarkup(createElement(RecommendationCard, { item }));

describe("priorResponse", () => {
  it("no pinta nada sin bloque: ni lo inventa ni deja un titulo vacio", () => {
    expect(priorResponse(recommendation(null))).toBeNull();
    expect(priorResponse(recommendation(undefined))).toBeNull();
    expect(render(recommendation(null))).not.toContain("Respuesta previa");
  });

  it("dice que no hay adopciones anteriores, con su advertencia", () => {
    const view = priorResponse(recommendation(prior([])));
    expect(view).toEqual({
      pictogram: "dash",
      summary: NO_PRIOR,
      last: null,
      earlier: [],
      basis: null,
      caveat: CAVEAT,
    });
    const html = render(recommendation(prior([])));
    expect(html).toContain(NO_PRIOR);
    expect(html).toContain(CAVEAT);
    // El guion de «no aplica» junto al resumen: no hay historia que contar.
    expect(html).toMatch(markedHtml("dash", "Respuesta previa: Sin adopciones"));
  });

  it("el dibujo del resumen es el del estado de la ultima adopcion: en curso o cerrada", () => {
    expect(priorResponse(recommendation(prior([open(1)])))?.pictogram).toBe("refresh");
    expect(priorResponse(recommendation(prior([adoption(1), adoption(2)])))?.pictogram).toBe("check");
    const html = render(recommendation(prior([open(1)])));
    expect(html).toMatch(markedHtml("refresh", "Respuesta previa: "));
    expect(html).toContain('<summary class="lead"><span class="mark"><svg');
    expect(html).not.toContain("↺");
  });

  it("da la ultima adopcion con los textos del backend, en su orden", () => {
    const view = priorResponse(recommendation(prior([adoption(1)])));
    // Cuando y quien ya lo dice el resumen: de la ultima no se repite.
    expect(view?.last?.lines).toEqual([
      "Se cerró (CDR): motivo 1",
      "Seguía Duración del sueño. Se repitió después de adoptarla.",
      "Texto de evaluación 1.",
    ]);
    expect(view?.earlier).toEqual([]);
    expect(view?.basis).toBe(BASIS);
  });

  it("ordena las anteriores de la mas reciente a la mas antigua", () => {
    const view = priorResponse(recommendation(prior([adoption(1), adoption(2), open(3)])));
    expect(view?.last?.key).toBe(3);
    expect(view?.earlier.map((item) => item.key)).toEqual([2, 1]);
    // Las anteriores si llevan su fecha: el resumen solo da la de la ultima.
    expect(view?.earlier[0]?.lines[0]).toBe("Adoptada el 2026-12-02 08:00 UTC (CDR).");
  });

  it("de una adopcion abierta no da evaluacion ni con que se compara", () => {
    const view = priorResponse(recommendation(prior([open(1)])));
    expect(view?.last?.lines).toContain("Sin evaluación final: el seguimiento sigue abierto.");
    expect(view?.basis).toBeNull();
    const html = render(recommendation(prior([open(1)])));
    expect(html).toContain("Sigue en seguimiento");
    expect(html).not.toContain(BASIS);
    expect(html).toContain(CAVEAT);
  });

  it("sin la advertencia no se pinta la historia", () => {
    const bare = { ...prior([adoption(1)]), caveat: "  " };
    expect(priorResponse(recommendation(bare))).toBeNull();
    expect(render(recommendation(bare))).not.toContain("Texto de evaluación 1.");
  });
});

describe("la tarjeta con respuesta previa", () => {
  const html = render(recommendation(prior([adoption(1), adoption(2)])));
  const block = html.slice(html.indexOf("<section"), html.indexOf("</section>"));

  it("pinta la historia tal cual y la advertencia fuera del desplegable", () => {
    expect(block).toContain("Respuesta previa: Se ha adoptado antes para este tripulante.");
    expect(block).toContain("Texto de evaluación 2.");
    expect(block).toContain("Adopciones anteriores (1)");
    expect(block).toContain("Texto de evaluación 1.");
    expect(block.indexOf(CAVEAT)).toBeGreaterThan(block.lastIndexOf("</details>"));
    expect(block).toContain(BASIS);
  });

  it("no lleva ningun color: es historia, no un aviso ni un resultado", () => {
    expect(block).not.toMatch(/class="[^"]*\bc-[a-z]+/);
    expect(block).not.toContain("style=");
  });

  it("no anade ninguna palabra de resultado que el backend no haya escrito", () => {
    const own = block
      .replace(/Texto de evaluación \d\./g, "")
      .replace(CAVEAT, "")
      .toLowerCase();
    for (const word of ["eficaz", "funcion", "éxito", "%", "mejor"]) {
      expect(own).not.toContain(word);
    }
  });

  it("sigue pintando la recomendacion entera", () => {
    expect(html).toContain("Proteger el periodo de sueño.");
    expect(html).toContain("Motivo: Sueño por debajo de lo habitual.");
  });
});
