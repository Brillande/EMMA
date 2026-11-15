import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { PriorAdoption, PriorResponse, Recommendation } from "../lib/api";
import { RecommendationCard } from "./RecommendationCard";
import { priorResponse } from "./recommendation";

/**
 * El nivel, al cerrar una adopcion (2026-10-13). El cierre guarda ahora el nivel del dominio y la
 * respuesta previa compara con el; de un cierre anterior dice que no lo guardo y compara con el
 * estado actual. Con que compara cada evaluacion lo ROTULA el backend. Aqui se fija que la
 * tarjeta pinta esos textos tal cual, cada uno con su adopcion, y que la interfaz no escribe
 * ningun rotulo ni elige entre las dos comparaciones.
 */

// Textos como los compone el backend (`advisor/prior_response.py`); aqui son solo cadenas.
const AT_CLOSE_TEXT = "Al cierre: Texto de la comparación con el cierre.";
const CURRENT_TEXT =
  "Este cierre no guardó el nivel: se compara con el estado actual. Texto de la comparación con hoy.";
const CAVEAT = "Es lo que pasó después, no una prueba de que fuera por la contramedida.";
const BASIS_MIXED = "Cada evaluación dice con qué compara el nivel del dominio cuando se adoptó.";

const closedWithLevel = (index: number): PriorAdoption => ({
  adoption_index: index,
  adopted_at: "2026-12-05T08:00:00+00:00",
  adopted_by: "CDR",
  adopted_text: "Adoptada el 2026-12-05 08:00 UTC (CDR).",
  level_at_adoption: "concern",
  state: "closed",
  state_text: "Se cerró el 2026-12-08 08:00 UTC (CDR): motivo nuevo",
  closed_by: "CDR",
  closed_reason: "motivo nuevo",
  closed_at: "2026-12-08T08:00:00+00:00",
  closed_recorded_at: "2026-12-08T09:30:00+00:00",
  level_at_close: "watch",
  followup_checks_display: ["Duración del sueño"],
  repeated_checks_display: ["Duración del sueño"],
  checks_text: "Seguía Duración del sueño. Se repitió después de adoptarla.",
  evaluation: { outcome: "improved", text: "Texto de la comparación con el cierre." },
  evaluation_basis: "at_close",
  evaluation_text: AT_CLOSE_TEXT,
});

const closedBefore = (index: number): PriorAdoption => ({
  ...closedWithLevel(index),
  adopted_text: "Adoptada el 2026-12-01 08:00 UTC (CDR).",
  state_text: "Se cerró (CDR): motivo antiguo",
  closed_reason: "motivo antiguo",
  closed_at: null,
  level_at_close: null,
  evaluation: { outcome: "unchanged", text: "Texto de la comparación con hoy." },
  evaluation_basis: "current_state",
  evaluation_text: CURRENT_TEXT,
});

const prior = (adoptions: PriorAdoption[], basis: string): PriorResponse => ({
  state: "closed",
  count: adoptions.length,
  text: "Se ha adoptado antes para este tripulante.",
  caveat: CAVEAT,
  evaluation_basis: basis,
  last: adoptions[adoptions.length - 1] ?? null,
  adoptions,
});

const recommendation = (response: PriorResponse): Recommendation => ({
  domain: "behavioral",
  action: "Proteger el periodo de sueño.",
  rationale: "Sueño por debajo de lo habitual.",
  urgency: "soon",
  notify_ground: false,
  evidence: [],
  countermeasure: null,
  decision: null,
  prior_response: response,
});

const mixed = recommendation(prior([closedBefore(1), closedWithLevel(2)], BASIS_MIXED));

describe("la respuesta previa con el nivel del cierre", () => {
  it("da de cada adopcion su evaluacion rotulada y su cierre, tal cual llegan", () => {
    const view = priorResponse(mixed);
    expect(view?.last?.lines).toEqual([
      "Se cerró el 2026-12-08 08:00 UTC (CDR): motivo nuevo",
      "Seguía Duración del sueño. Se repitió después de adoptarla.",
      AT_CLOSE_TEXT,
    ]);
    expect(view?.earlier.map((item) => item.lines)).toEqual([
      [
        "Adoptada el 2026-12-01 08:00 UTC (CDR).",
        "Se cerró (CDR): motivo antiguo",
        "Seguía Duración del sueño. Se repitió después de adoptarla.",
        CURRENT_TEXT,
      ],
    ]);
    // Con que compara el bloque lo dice el backend; la advertencia de siempre va con el.
    expect(view?.basis).toBe(BASIS_MIXED);
    expect(view?.caveat).toBe(CAVEAT);
  });

  it("la tarjeta pinta los dos rotulos, cada uno con su adopcion, y la advertencia", () => {
    const html = renderToStaticMarkup(createElement(RecommendationCard, { item: mixed }));
    const block = html.slice(html.indexOf("<section"), html.indexOf("</section>"));
    // El bloque entero va plegado (el resumen queda a la vista); dentro, las adopciones
    // anteriores tienen su propio desplegable.
    const details = block.slice(block.lastIndexOf("<details"), block.indexOf("</details>"));
    // La ultima (cierre con nivel) va fuera del desplegable de las anteriores; la antigua, dentro.
    expect(block.indexOf(AT_CLOSE_TEXT)).toBeGreaterThan(block.indexOf("<details"));
    expect(block.indexOf(AT_CLOSE_TEXT)).toBeLessThan(block.lastIndexOf("<details"));
    expect(details).toContain(CURRENT_TEXT);
    expect(details).not.toContain(AT_CLOSE_TEXT);
    expect(block).toContain("Se cerró el 2026-12-08 08:00 UTC (CDR): motivo nuevo");
    expect(block).toContain(BASIS_MIXED);
    expect(block.indexOf(CAVEAT)).toBeGreaterThan(block.lastIndexOf("</details>"));
    // Historia, no resultado: sin color y sin el nivel suelto como insignia.
    expect(block).not.toMatch(/class="[^"]*\bc-[a-z]+/);
    expect(block).not.toContain("style=");
  });

  it("no cambia nada si el backend no manda los campos del cierre", () => {
    const legacy = closedBefore(1);
    delete legacy.closed_at;
    delete legacy.closed_recorded_at;
    delete legacy.level_at_close;
    delete legacy.evaluation_basis;
    const view = priorResponse(recommendation(prior([legacy], "Base.")));
    expect(view?.last?.lines).toEqual([
      "Se cerró (CDR): motivo antiguo",
      "Seguía Duración del sueño. Se repitió después de adoptarla.",
      CURRENT_TEXT,
    ]);
    expect(view?.basis).toBe("Base.");
  });
});

describe("quien rotula con que se compara", () => {
  const source = (name: string): string =>
    readFileSync(fileURLToPath(new URL(name, import.meta.url)), "utf8");

  it("no es la interfaz: ni el rotulo ni la eleccion entre las dos comparaciones", () => {
    for (const name of ["./recommendation.ts", "./RecommendationCard.tsx"]) {
      // Sin comentarios: lo que se busca es que no haya ni una cadena ni una regla en el codigo.
      const code = source(name)
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/^\s*\/\/.*$/gm, "");
      for (const fragment of [
        "Al cierre",
        "no guardó el nivel",
        "estado actual",
        "evaluation_at_close",
        "level_at_close",
        "at_close",
        "current_state",
      ]) {
        expect(code, `${name}: ${fragment}`).not.toContain(fragment);
      }
    }
  });
});
