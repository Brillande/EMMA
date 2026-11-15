/**
 * La tarjeta de recomendación en inglés (`lib/i18n.ts`): los rótulos y los mandos que escribe la
 * interfaz se leen en inglés; la acción, el motivo, los recursos y la respuesta previa son del
 * backend (aquí, los textos castellanos del ejemplo) y se pintan tal cual. Qué se ve sin abrir nada
 * lo fija `foldedCard.test.ts`, en castellano.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { language } from "../lib/i18n";
import { TEXTS, fullRecommendation, measureOf } from "./cardFixture";
import { declineState } from "./recommendation";
import { BasisText, FollowupText, RecommendationCard } from "./RecommendationCard";
import { textLines } from "./visibleText";

const noop = async () => {};

const card = (operator = "CDR") =>
  renderToStaticMarkup(
    createElement(RecommendationCard, { item: fullRecommendation(), operator, onAdopt: noop, onDecline: noop }),
  );

describe("la tarjeta de recomendación en inglés", () => {
  it("este fichero corre en inglés", () => {
    expect(language()).toBe("en");
  });

  it("el rótulo, el motivo y los mandos", () => {
    const html = card();
    const text = textLines(html).join(" ");
    expect(text).toContain("System recommendation");
    expect(text).toContain("urgency Soon");
    expect(text).toContain("inform Earth");
    expect(text).toContain(`Reason: ${TEXTS.rationale}`);
    expect(html).toContain("Adopt and follow");
    expect(html).toContain("Do not adopt");
    expect(html).toContain('placeholder="reason for not adopting it"');
    expect(html).not.toMatch(/Recomendación del sistema|urgencia|informar a Tierra|Motivo|Adoptar y seguir|No adoptar/);
    // Lo del backend, tal cual.
    expect(html).toContain(TEXTS.action);
  });

  it("la ficha, los recursos y la respuesta previa", () => {
    const html = card();
    for (const word of [
      "Basis",
      "demo: backed only by the domain&#x27;s risk",
      "Contraindications",
      "Effects to keep in mind",
      "Cost and follow-up",
      "Resources",
      "Crew time",
      "Follow-up",
      'aria-label="Onboard resources"',
      'aria-label="Prior response"',
      "Prior response: ",
      "Earlier adoptions (",
    ]) {
      expect(html, word).toContain(word);
    }
    expect(html).not.toMatch(/Respaldo|Contraindicaciones|Efectos a tener en cuenta|Coste y seguimiento|Tiempo de tripulación|Recursos a bordo|Respuesta previa|Adopciones anteriores/);
    for (const word of [TEXTS.contraindications, TEXTS.resourceText, TEXTS.priorSummary, TEXTS.priorCaveat]) {
      expect(html, word).toContain(word);
    }
  });

  it("sin tripulante en consola, el mando dice qué falta", () => {
    expect(card("")).toContain('title="Enter who is at the console"');
    expect(declineState({ hasHandler: true, adopted: false, operator: "CDR", reason: " ", busy: false }).missing).toBe(
      "Enter the reason: it is signed with the decision",
    );
  });

  it("el respaldo y el seguimiento de la ficha", () => {
    const backed = measureOf({ basis: "evidence-backed", protocol_ref: { source: "FUENTE" } as never, followup_checks_display: ["A", "B"] });
    expect(renderToStaticMarkup(createElement(BasisText, { measure: backed }))).toContain("own protocol or source: FUENTE");
    const followup = textLines(renderToStaticMarkup(createElement(FollowupText, { measure: backed }))).join(" ");
    expect(followup).toContain("repeat A and B in 48 h");
    const plain = textLines(renderToStaticMarkup(createElement(FollowupText, { measure: measureOf() }))).join(" ");
    expect(plain).toContain("log entry, no measurement to repeat in 48 h");
  });
});
