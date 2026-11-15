import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { MissionMilestones } from "../lib/api";
import { MilestonesBasis } from "./AnatomyPanel";

/**
 * La base de los hitos del selector «Momento» (decimosexta ronda, §5.36.13): la frase del backend
 * y, debajo, cada fuente con lo que cubre, tal cual llega. Que la densitometría es solo del hueso
 * lo dice su ficha en la pantalla, no solo la frase.
 */

const BONE_SCOPE =
  "Solo del hueso: son tomas de densitometría (DXA), no un calendario de todos los indicadores.";

const milestones: MissionMilestones = {
  read: [0, 1, 7, 30, 180, 365, 730, 1095],
  design: [90],
  basis: "Hitos posvuelo: frase del backend.",
  sources: [
    {
      days: [0, 1, 7, 30],
      source: { id: "hardy", title: "Standard Measures", url: "https://example.org/hardy", relevance: null },
      scope: "El calendario de Spaceflight Standard Measures, no el de todos los indicadores.",
    },
    {
      days: [180, 365, 730, 1095],
      source: { id: "ochmo", title: "OCHMO-MTB-013", url: null, relevance: null },
      scope: BONE_SCOPE,
    },
  ],
};

const render = (value: MissionMilestones) => renderToStaticMarkup(createElement(MilestonesBasis, { milestones: value }));

describe("la base de los hitos", () => {
  it("dice la frase del backend y cada fuente con su alcance, con enlace si lo tiene", () => {
    const html = render(milestones);
    expect(html).toContain("Hitos posvuelo: frase del backend.");
    expect(html).toContain('<a href="https://example.org/hardy" target="_blank" rel="noreferrer">Standard Measures</a>');
    expect(html).toContain(`<li data-milestone-source="ochmo">OCHMO-MTB-013 — ${BONE_SCOPE}</li>`);
  });

  it("con un backend anterior, sin `sources`, solo la frase", () => {
    const { sources: _omitted, ...old } = milestones;
    const html = render(old);
    expect(html).toBe('<p class="secondary">Hitos posvuelo: frase del backend.</p>');
  });
});
