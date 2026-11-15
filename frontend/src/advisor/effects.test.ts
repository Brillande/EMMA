import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { isPictogramName } from "../icons/registry";
import type { CountermeasureLibrary } from "../lib/api";
import {
  EFFECTS_TEXTS,
  TEXTS,
  conditionalCoAdoption,
  effectsOf,
  fullRecommendation,
  measureOf,
  notDeclaredEffects,
} from "./cardFixture";
import {
  ADVERSE_EFFECTS_PICTOGRAM,
  CO_ADOPTION_PICTOGRAM,
  CONTRAINDICATIONS_PICTOGRAM,
  FAMILY_PICTOGRAMS,
} from "./library";
import { LibraryBody } from "./LibraryPanel";
import { effectsView } from "./recommendation";
import { RecommendationCard } from "./RecommendationCard";
import { taggedPictogram, visibleText } from "./visibleText";

/**
 * Efectos e interacciones de contramedidas (§5.39.17): la tarjeta y la biblioteca enseñan tal cual
 * lo que el backend dice —sobre qué se espera el beneficio, dónde cae cada efecto adverso declarado
 * o que no está declarado, y con qué otra está adoptada a la vez— sin color de alerta y sin
 * inventar nada cuando el backend no lo manda.
 */

const noop = async () => {};
const card = (effects: ReturnType<typeof effectsOf> | null | undefined) =>
  renderToStaticMarkup(
    createElement(RecommendationCard, {
      item: effects === undefined ? fullRecommendation() : fullRecommendation({ effects }),
      operator: "CDR",
      onAdopt: noop,
      onDecline: noop,
    }),
  );

/** El bloque de la ficha de la contramedida, donde van los efectos. */
const facts = (html: string): string => {
  const start = html.indexOf('<dl class="kv countermeasure">');
  const end = html.indexOf("</dl>", start);
  return html.slice(start, end);
};

describe("effectsView", () => {
  it("sin ficha, o sin la frase del beneficio, no se pinta nada: la interfaz no la inventa", () => {
    expect(effectsView(null)).toBeNull();
    expect(effectsView(undefined)).toBeNull();
    expect(effectsView(effectsOf({ benefit: { ...effectsOf().benefit, text: "  " } }))).toBeNull();
  });

  it("ordena lo que se pinta sin resumir ni colorear: beneficio, dónde cae cada efecto, co-adopción", () => {
    const view = effectsView(effectsOf());
    expect(view).not.toBeNull();
    expect(view?.benefit).toBe(EFFECTS_TEXTS.benefit);
    expect(view?.adverse).toEqual([
      { key: "indicator:iop:0", display: EFFECTS_TEXTS.adverseWhere, text: EFFECTS_TEXTS.adverseEffectText, basis: EFFECTS_TEXTS.adverseBasis },
    ]);
    expect(view?.adverseText).toBeNull();
    expect(view?.coAdopted).toEqual([{ key: "bh-protect-sleep:7", text: EFFECTS_TEXTS.coAdopted, adopted: true }]);
    expect(view?.coAdoptionBasis).toBe(EFFECTS_TEXTS.coAdoptionBasis);
  });

  it("declarados pero sin ninguna línea legible: el hueco se ve con la marca del registro vacío", () => {
    const hollow = effectsView(effectsOf({ adverse: [{ ...effectsOf().adverse[0]!, text: "  " }], adverse_text: null }));
    expect(hollow?.adverse).toEqual([]);
    expect(hollow?.adverseEmpty).toBe(true);
    expect(effectsView(effectsOf())?.adverseEmpty).toBe(false);
    expect(effectsView(notDeclaredEffects())?.adverseEmpty).toBe(false);
    const html = card(effectsOf({ adverse: [{ ...effectsOf().adverse[0]!, text: "  " }], adverse_text: null }));
    expect(html).toContain("nada escrito");
  });

  it("«no declarado» es la frase del backend; en blanco, no hay frase", () => {
    expect(effectsView(notDeclaredEffects())?.adverseText).toBe(EFFECTS_TEXTS.notDeclared);
    expect(effectsView(notDeclaredEffects())?.adverse).toEqual([]);
    expect(effectsView(effectsOf({ adverse_declared: false, adverse: [], adverse_text: " " }))?.adverseText).toBeNull();
  });
});

describe("la tarjeta de recomendación", () => {
  const html = card(effectsOf());
  const seen = visibleText(html);

  it.each([
    ["el beneficio esperado", EFFECTS_TEXTS.benefit],
    ["dónde cae el efecto adverso declarado", `${EFFECTS_TEXTS.adverseWhere}: ${EFFECTS_TEXTS.adverseEffectText}`],
    ["de dónde sale", EFFECTS_TEXTS.adverseBasis],
    ["la nota de co-adopción", EFFECTS_TEXTS.coAdopted],
    ["de dónde sale la nota de co-adopción", EFFECTS_TEXTS.coAdoptionBasis],
    // La nota de la biblioteca sigue ahí: los efectos la acompañan, no la sustituyen.
    ["la nota de efectos de la biblioteca", TEXTS.adverse],
  ])("enseña sin abrir nada %s", (_name, text) => {
    expect(seen).toContain(text);
  });

  it("los efectos van bajo la misma clave y el mismo dibujo que la nota de la biblioteca", () => {
    expect(html).toMatch(taggedPictogram("dt", ADVERSE_EFFECTS_PICTOGRAM, "Efectos a tener en cuenta</dt>"));
    expect(html.match(/Efectos a tener en cuenta<\/dt>/g)).toHaveLength(1);
  });

  it("la co-adopción lleva su propia clave con los dos círculos que se solapan", () => {
    expect(html).toMatch(taggedPictogram("dt", CO_ADOPTION_PICTOGRAM, "Con otras en seguimiento</dt>"));
  });

  it("es información, no un aviso: ningún color de alerta en la ficha", () => {
    expect(facts(html)).not.toMatch(/c-(red|yellow|cyan|magenta)/);
  });

  it("sin efecto declarado, la frase de «no declarado» del backend; sin otra adoptada, sin clave de co-adopción", () => {
    const plain = card(notDeclaredEffects());
    expect(visibleText(plain)).toContain(EFFECTS_TEXTS.notDeclared);
    expect(plain).not.toContain("Con otras en seguimiento");
    expect(plain).not.toContain(EFFECTS_TEXTS.adverseEffectText);
  });

  it("una recomendación sin adoptar lleva la nota en condicional, tal cual la da el backend", () => {
    expect(visibleText(card(conditionalCoAdoption()))).toContain(EFFECTS_TEXTS.coAdoptedConditional);
  });

  it("un backend anterior (sin `effects`) deja la tarjeta como estaba", () => {
    const before = card(undefined);
    expect(before).not.toContain("Beneficio esperado");
    expect(before).not.toContain("Con otras en seguimiento");
    expect(before).toContain(TEXTS.adverse);
    expect(card(null)).toBe(before);
  });

  it("si la ficha va dentro de la contramedida (la biblioteca), también se pinta", () => {
    const item = fullRecommendation({ countermeasure: measureOf({ effects: notDeclaredEffects() }) });
    const body = renderToStaticMarkup(createElement(RecommendationCard, { item, operator: "CDR", onAdopt: noop }));
    expect(visibleText(body)).toContain(EFFECTS_TEXTS.notDeclared);
  });

  it("sin nota de la biblioteca ni ficha, la clave de efectos no aparece; con ficha y sin nota, sí", () => {
    const bare = fullRecommendation({ countermeasure: measureOf({ adverse_effects_note: null }) });
    expect(renderToStaticMarkup(createElement(RecommendationCard, { item: bare }))).not.toContain(
      "Efectos a tener en cuenta",
    );
    const withCard = fullRecommendation({
      countermeasure: measureOf({ adverse_effects_note: null }),
      effects: notDeclaredEffects(),
    });
    const body = renderToStaticMarkup(createElement(RecommendationCard, { item: withCard }));
    expect(body).toContain("Efectos a tener en cuenta");
    expect(visibleText(body)).toContain(EFFECTS_TEXTS.notDeclared);
  });
});

describe("la biblioteca", () => {
  const library = (over: Partial<CountermeasureLibrary> = {}): CountermeasureLibrary => ({
    countermeasures: [
      measureOf({ id: "a", action: "Acción A.", effects: effectsOf({ co_adopted: [] }) }),
      measureOf({ id: "b", action: "Acción B.", adverse_effects_note: null, effects: notDeclaredEffects() }),
    ],
    by_ridge: [{ ridge: "gravity", ridge_display: "Campos de gravedad", count: 2, countermeasures: ["a", "b"] }],
    families: [],
    note: "nota de la biblioteca",
    family_basis: "base del vocabulario",
    ridge_basis: "base de RIDGE",
    effects_overview: {
      note: "nota de los efectos del backend",
      co_adoption_basis: EFFECTS_TEXTS.coAdoptionBasis,
      declared: 2,
      not_declared: 38,
      interactions: [],
      interactions_note: "Ninguna fuente leída dice cómo interactúan dos contramedidas de la biblioteca.",
    },
    ...over,
  });
  const html = renderToStaticMarkup(createElement(LibraryBody, { library: library() }));
  const seen = visibleText(html);

  it("cada fila lleva las mismas líneas que la tarjeta: beneficio y dónde cae cada efecto, o «no declarado»", () => {
    // Los grupos RIDGE van plegados: se mira el HTML entero, como en `library.test.ts`.
    expect(html).toContain(EFFECTS_TEXTS.benefit);
    expect(html).toContain(`${EFFECTS_TEXTS.adverseWhere}: ${EFFECTS_TEXTS.adverseEffectText}`);
    expect(html).toContain(EFFECTS_TEXTS.notDeclared);
    // Con la ficha de efectos, la frase de «no declarado» ocupa el sitio de «nada escrito».
    expect(html).not.toContain("nada escrito");
  });

  it("la cabecera dice qué son los efectos, cuántas declaran alguno y que ninguna fuente dice cómo interactúan", () => {
    expect(seen).toContain("Efectos: nota de los efectos del backend");
    expect(html).toMatch(
      /Con efecto adverso declarado: <span class="num">2<\/span> · no declarado: <span class="num">38<\/span>\./,
    );
    expect(seen).toContain("Ninguna fuente leída dice cómo interactúan dos contramedidas de la biblioteca.");
  });

  it("un resumen nulo no tumba la biblioteca: la cabecera de los efectos no se pinta", () => {
    const body = renderToStaticMarkup(createElement(LibraryBody, { library: library({ effects_overview: null }) }));
    expect(body).not.toContain("Efectos: ");
    expect(body).toContain(EFFECTS_TEXTS.benefit);
  });

  it("sin la ficha (un backend anterior) la tabla y la cabecera son las de siempre", () => {
    const before = library();
    delete before.effects_overview;
    before.countermeasures = before.countermeasures.map((item) => {
      const copy = { ...item };
      delete copy.effects;
      return copy;
    });
    const body = renderToStaticMarkup(createElement(LibraryBody, { library: before }));
    expect(body).not.toContain("Efectos: ");
    expect(body).not.toContain("Beneficio esperado");
    expect(body.match(/nada escrito/g)).toHaveLength(1);
  });
});

describe("el dibujo de la co-adopción", () => {
  it("existe y es distinto de los de contraindicaciones, efectos y familias", () => {
    expect(isPictogramName(CO_ADOPTION_PICTOGRAM)).toBe(true);
    const drawings = [CO_ADOPTION_PICTOGRAM, CONTRAINDICATIONS_PICTOGRAM, ADVERSE_EFFECTS_PICTOGRAM, ...Object.values(FAMILY_PICTOGRAMS)];
    expect(new Set(drawings).size).toBe(drawings.length);
    expect(CO_ADOPTION_PICTOGRAM).not.toBe("shape-triangle");
  });
});
