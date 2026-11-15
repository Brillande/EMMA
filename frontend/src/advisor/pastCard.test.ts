import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { Recommendation } from "../lib/api";
import { RecommendationCard } from "./RecommendationCard";
import { RecommendationList } from "./RecommendationList";
import { TEXTS, fullRecommendation } from "./cardFixture";
import { markedHtml, visibleText } from "./visibleText";

/**
 * La tarjeta de recomendación de un momento pasado (§5.35.8): la convención «lo pasado lleva la
 * forma sin su color» del historial del hábitat. Las mismas palabras y los mismos dibujos que la
 * de ahora; sin el magenta de la automatización (rótulo y filete) ni el color de los estados de
 * recursos. Antes conservaba urgencia y colores y se leía como una recomendación vigente.
 */

const card = (item: Recommendation, past: boolean): string =>
  renderToStaticMarkup(createElement(RecommendationCard, { item, past }));

/** Lo de la tarjeta sin la evidencia: sus marcas describen la fuente, no el momento. */
const withoutEvidence = (html: string): string => {
  const at = html.indexOf('<ul class="evidence"');
  return at < 0 ? html : html.slice(0, at);
};

describe("la tarjeta de un momento pasado: su forma, sin su color", () => {
  const now = card(fullRecommendation(), false);
  const past = card(fullRecommendation(), true);

  it("dice lo mismo que la de ahora: la interfaz no quita ni añade palabras", () => {
    expect(visibleText(past)).toBe(visibleText(now));
  });

  it("el rótulo y el filete pierden el magenta de «lo propone la automatización»", () => {
    expect(now).toContain('<article class="recommendation">');
    expect(now).toContain('class="source-tag c-magenta"');
    expect(past).toContain('<article class="recommendation past">');
    expect(past).toContain('class="source-tag secondary"');
    expect(past).not.toContain("c-magenta");
    // El filete del pasado es el de las líneas, no un color con significado.
    const css = readFileSync(fileURLToPath(new URL("../styles.css", import.meta.url)), "utf-8");
    expect(css).toMatch(/\.recommendation\.past \{\s*border-left-color: var\(--c-line\);/);
  });

  it("cada estado de recursos conserva su dibujo y su palabra, sin su color", () => {
    expect(now).toMatch(markedHtml("slash-circle", `${TEXTS.unavailableWord}</span>`, "gray"));
    expect(now).toMatch(markedHtml("ring-dotted", `${TEXTS.undeclaredWord}</span>`, "cyan"));
    expect(past).toMatch(markedHtml("slash-circle", `${TEXTS.unavailableWord}</span>`));
    expect(past).toMatch(markedHtml("ring-dotted", `${TEXTS.undeclaredWord}</span>`));
    const own = withoutEvidence(past);
    for (const token of ["c-gray", "c-cyan", "c-text", "c-magenta", "c-red", "c-yellow", "c-green", "c-blue"]) {
      expect(own, token).not.toContain(token);
    }
  });

  it("la urgencia lleva sus galones también en el pasado", () => {
    expect(past).toMatch(markedHtml("chevrons-right-double", "urgencia Pronto</span>"));
  });

  it("la lista pasa `past` a cada tarjeta, y el modo anatómico se lo da en un momento pasado", () => {
    const html = renderToStaticMarkup(
      createElement(RecommendationList, {
        items: [fullRecommendation()],
        following: new Set<string>(),
        past: true,
      }),
    );
    expect(html).toContain('<article class="recommendation past">');
    const chain = readFileSync(fileURLToPath(new URL("../anatomy/RegionChain.tsx", import.meta.url)), "utf-8");
    expect(chain).toContain("past={pastUntil !== null}");
  });
});
