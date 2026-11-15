import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
// Sin los `data-ui` del asistente: estas pruebas miran el marcado del panel.
import { renderToStaticMarkup } from "../assistant/staticMarkup";
import { describe, expect, it } from "vitest";

import { LookContext } from "../components/BoardOnly";
import type { EvidenceItem, Recommendation } from "../lib/api";
import { RecommendationCard } from "./RecommendationCard";
import { RecommendationList } from "./RecommendationList";
import {
  TEXTS,
  allAvailable,
  fullRecommendation,
  measureOf,
  priorOf,
  resourceStatusOf,
  unavailableItem,
} from "./cardFixture";
import { ADVERSE_EFFECTS_PICTOGRAM, CONTRAINDICATIONS_PICTOGRAM } from "./library";
import { exposedLines, resourceClarification, resourceStatus, summaryMarks } from "./resources";
import { markedHtml, taggedPictogram, textLines, textNodes, visibleText, withoutFolded } from "./visibleText";

/**
 * La tarjeta de recomendacion plegada: que se lee SIN abrir nada y que no se ha perdido.
 *
 * La tarjeta se pinta de verdad, a HTML estatico, y se le quita lo que un `<details>` cerrado
 * esconde. Hay una prueba por cada advertencia que debe verse sin abrir, una por cada cosa que
 * pasa a estar plegada (sigue en la tarjeta: ninguna deja de ensenarse) y la medida de cuanto
 * texto queda a la vista.
 */

const noop = async () => {};

const declined = (): Recommendation =>
  fullRecommendation({
    decision: {
      action: "declined",
      ledger_index: 41,
      decided_at: "2026-12-08T10:00:00+00:00",
      decided_by: "CDR",
      reason: "sonda averiada",
      text: TEXTS.decisionText,
      meaning: TEXTS.decisionMeaning,
    },
  });

const card = (item: Recommendation, clarified = false): string =>
  renderToStaticMarkup(
    createElement(RecommendationCard, {
      item,
      operator: "CDR",
      onAdopt: noop,
      onDecline: noop,
      resourcesClarified: clarified,
    }),
  );

const list = (items: Recommendation[]): string =>
  renderToStaticMarkup(
    createElement(RecommendationList, {
      items,
      operator: "CDR",
      following: new Set<string>(),
      onAdopt: noop,
      onDecline: noop,
    }),
  );

const count = (text: string, piece: string): number => text.split(piece).length - 1;

/** La marca de un estado: pictograma SVG y palabra del backend, con el color del estado. */
const GRAY_WORD = markedHtml("slash-circle", `${TEXTS.unavailableWord}</span>`, "gray");
const CYAN_WORD = markedHtml("ring-dotted", `${TEXTS.undeclaredWord}</span>`, "cyan");

describe("con qué reglas se firmó el «no» (§5.39.9)", () => {
  const signed = "decidido con reglas@abc; misma versión que hoy";

  it("la frase del backend va, tal cual y sin color, tras lo que significa la decisión", () => {
    const base = declined();
    const html = card({
      ...base,
      decision: {
        ...base.decision!,
        rules: { rules_version: "reglas@abc", same_as_today: true, text: signed },
      },
    });
    expect(visibleText(html)).toContain(`${TEXTS.decisionMeaning} · ${signed}`);
    expect(html).not.toMatch(/c-(red|yellow|cyan)[^>]*>[^<]*decidido con/);
  });

  it("un «no» sin la frase (una versión anterior del backend) se pinta como antes", () => {
    expect(card(declined())).not.toContain("decidido con");
  });
});

describe("lo que se ve sin abrir nada: una prueba por advertencia", () => {
  const html = card(declined());
  const seen = visibleText(html);

  it.each([
    ["el rotulo: es una recomendacion del sistema, y hay que informar a Tierra", "Recomendación del sistema"],
    ["el rotulo dice que se informa a Tierra", "informar a Tierra"],
    ["la accion", TEXTS.action],
    ["el motivo", `Motivo: ${TEXTS.rationale}`],
    ["la nota de lo decidido", TEXTS.decisionText],
    ["que significa lo decidido: la recomendacion sigue vigente", TEXTS.decisionMeaning],
    ["el respaldo: es demo", "demo: solo la respalda el riesgo del dominio"],
    ["el eje RIDGE del respaldo", `RIDGE: ${TEXTS.ridge}`],
    ["las contraindicaciones, tambien si estan pendientes", TEXTS.contraindications],
    ["los efectos a tener en cuenta", TEXTS.adverse],
    ["que consta de los recursos, con la frase del backend", TEXTS.resourceText],
    ["la palabra del recurso declarado no disponible", TEXTS.unavailableWord],
    ["la palabra del recurso sin declarar", TEXTS.undeclaredWord],
    ["quien declara los recursos: EMMA no lleva inventario", TEXTS.label],
    ["sin declarar no es disponible, y la contramedida se ofrece igual", TEXTS.resourceCaveat],
    ["el resumen de la respuesta previa", `Respuesta previa: ${TEXTS.priorSummary}`],
    ["la advertencia de la respuesta previa: no prueba una causa", TEXTS.priorCaveat],
    ["adoptar", "Adoptar y seguir"],
    ["no adoptar", "No adoptar"],
  ])("%s", (_name, text) => {
    expect(seen).toContain(text);
  });

  it("lo no disponible se ve con pictograma, palabra y su color (gris), y lo sin declarar en cian", () => {
    const open = withoutFolded(html);
    expect(open).toMatch(GRAY_WORD);
    expect(open).toMatch(CYAN_WORD);
    // El nombre de lo que falta tambien: no basta con decir que falta algo.
    expect(seen).toMatch(/no disponible: ecógrafo/);
  });

  it("el rotulo lleva el dominio con su dibujo, la urgencia con sus galones y la antena de Tierra", () => {
    const tag = html.slice(html.indexOf('<span class="source-tag'), html.indexOf("<p>"));
    expect(tag).toMatch(markedHtml("chevrons-right-double", "urgencia Pronto</span>"));
    expect(tag).toMatch(markedHtml("antenna-dish", "informar a Tierra</span>"));
    // El dominio del accesorio (`sans`) no tiene dibujo propio: sale con su clave y el de «desconocido».
    expect(tag).toMatch(markedHtml("dot-small", "sans</span>"));
    expect(textLines(tag)).toEqual(["Recomendación del sistema · sans · urgencia Pronto · informar a Tierra"]);
    // Sin informar a Tierra, sin antena.
    const quiet = card(fullRecommendation({ notify_ground: false }));
    expect(quiet).not.toContain('data-pictogram="antenna-dish"');
  });

  it("una urgencia que esta version no conoce no tumba la tarjeta: su clave y el dibujo de «desconocido»", () => {
    const odd = card(fullRecommendation({ urgency: "urgent" as unknown as Recommendation["urgency"] }));
    expect(odd).toMatch(markedHtml("dot-small", "urgencia urgent</span>"));
    expect(visibleText(odd)).toContain(TEXTS.action);
  });

  it("la nota de lo decidido, el respaldo y el eje RIDGE llevan su dibujo junto al texto del backend", () => {
    expect(html).toMatch(markedHtml("slash-circle", "No adoptada el 2026-12-08"));
    expect(html).toMatch(markedHtml("dash", "demo: solo la respalda el riesgo del dominio</span>"));
    expect(html).toMatch(markedHtml("ridge-gravity", "RIDGE: Campos de gravedad</span>"));
    const backed = card(
      fullRecommendation({ countermeasure: measureOf({ basis: "evidence-backed", ridge: "otro-eje" }) }),
    );
    expect(backed).toMatch(markedHtml("sheet-lines", "protocolo o fuente propia</span>"));
    expect(backed).toMatch(markedHtml("dot-small", "RIDGE: Campos de gravedad</span>"));
    // Un respaldo que esta version no conoce tampoco tumba la ficha.
    const odd = card(
      fullRecommendation({ countermeasure: measureOf({ basis: "otro" as unknown as "demo" }) }),
    );
    expect(odd).toMatch(markedHtml("dot-small", "demo: solo la respalda el riesgo del dominio</span>"));
  });

  it("la advertencia de la respuesta previa va FUERA de su desplegable", () => {
    const start = html.indexOf('<section role="group" aria-label="Respuesta previa">');
    expect(start).toBeGreaterThanOrEqual(0);
    const section = html.slice(start);
    // Hasta la advertencia: si va fuera del desplegable, todo `<details>` abierto antes ya se cerró.
    const block = section.slice(0, section.indexOf(TEXTS.priorCaveat) + TEXTS.priorCaveat.length);
    expect(block).toContain(TEXTS.priorCaveat);
    expect(block.split("<details").length).toBe(block.split("</details>").length);
    expect(block.indexOf(TEXTS.priorCaveat)).toBeGreaterThan(block.lastIndexOf("</details>"));
    expect(block).not.toMatch(/class="[^"]*\bc-[a-z]+/);
  });

  it("una adopcion ya en seguimiento se dice sin abrir, con la marca de hecho", () => {
    const adopted = renderToStaticMarkup(
      createElement(RecommendationCard, { item: fullRecommendation(), adopted: true, onAdopt: noop }),
    );
    expect(visibleText(adopted)).toContain("Adoptada: en seguimiento");
    expect(adopted).toMatch(markedHtml("check", "Adoptada: en seguimiento.</span>", null, "secondary"));
  });

  it("ningun bloque de la tarjeta usa un color de alerta", () => {
    expect(html).not.toMatch(/\bc-(red|yellow)\b/);
  });
});

describe("lo que pasa a estar plegado sigue en la tarjeta", () => {
  const html = card(declined());
  const seen = visibleText(html);
  const everything = textLines(html).join("\n");

  it.each([
    ["los recursos que pide la contramedida", TEXTS.resourcesAsked],
    ["de donde sale el tiempo de tripulacion", TEXTS.crewTimeBasis],
    ["de donde sale la ventana de seguimiento", `— ${TEXTS.followupBasis}`],
    ["la nota de quien declaro el recurso", TEXTS.declarerNote],
    ["como acabo la ultima adopcion", TEXTS.lastState],
    ["que se repitio en la ultima adopcion", TEXTS.lastChecks],
    ["la evaluacion de la ultima adopcion", TEXTS.lastEvaluation],
    ["la adopcion anterior", TEXTS.earlierAdopted],
    ["la evaluacion de la adopcion anterior", TEXTS.earlierEvaluation],
    ["con que compara la evaluacion", TEXTS.priorBasis],
  ])("%s", (_name, text) => {
    expect(everything).toContain(text);
    expect(seen).not.toContain(text);
  });

  it("cada desplegable es un <details> nativo con su <summary>: se abre con teclado", () => {
    expect(count(html, "<details")).toBe(count(html, "<summary"));
    expect(html).not.toMatch(/<details[^>]*\sopen/);
    for (const label of ["Coste y seguimiento", "Recursos a bordo", "Respuesta previa:", "Adopciones anteriores (1)"]) {
      expect(html).toMatch(new RegExp(`<summary[^>]*>(?:(?!</summary>)[\\s\\S])*${label.replace(/[()]/g, "\\$&")}`));
    }
  });

  it("ningun texto de la recomendacion deja de ensenarse", () => {
    for (const [name, text] of Object.entries(TEXTS)) {
      expect(everything, name).toContain(text);
    }
  });

  it("la nota de por que no lista recursos sigue en la ficha", () => {
    const item = fullRecommendation({
      countermeasure: measureOf({ resources: [], resources_note: "no requiere recursos" }),
      resource_status: null,
    });
    expect(textLines(card(item)).join("\n")).toContain("no requiere recursos");
  });
});

describe("un recurso que falta no queda escondido", () => {
  it("el resumen lleva una marca por estado que no sea disponible, lo no disponible primero", () => {
    const view = resourceStatus(fullRecommendation());
    expect(view?.summaryMarks.map((item) => item.state)).toEqual(["unavailable", "undeclared"]);
    const reversed = [...(view?.lines ?? [])].reverse();
    expect(summaryMarks(reversed).map((item) => item.state)).toEqual(["unavailable", "undeclared"]);
    // Una marca por estado, no por recurso.
    expect(summaryMarks([...reversed, ...reversed])).toHaveLength(2);
  });

  it("con todo declarado disponible el resumen no lleva marca ni hay advertencia", () => {
    const item = fullRecommendation({ resource_status: allAvailable() });
    expect(resourceStatus(item)?.summaryMarks).toEqual([]);
    const seen = visibleText(card(item));
    expect(seen).toContain("Recursos a bordo — Todos los recursos que pide constan declarados disponibles.");
    expect(seen).not.toContain("Sin declarar no es disponible");
    // El rotulo si: lo «disponible» tambien es una declaracion, no un inventario.
    expect(seen).toContain(TEXTS.label);
  });

  it("un estado que esta version no conoce (agotado) se ve en el resumen con su palabra", () => {
    const depleted = {
      ...unavailableItem("gel de ecografía"),
      key: "ultrasound-gel",
      state: "depleted" as unknown as "unavailable",
      state_display: "declarado agotado",
    };
    const status = resourceStatusOf({ items: [depleted], text: "Frase que no nombra el recurso." });
    const html = card(fullRecommendation({ resource_status: status }));
    const seen = visibleText(html);
    expect(seen).toContain("declarado agotado");
    // La frase del backend no lo nombra: su linea entera sale fuera del desplegable.
    expect(seen).toContain("gel de ecografía · declarado agotado");
    // Ni el estado ni la clave del recurso tienen dibujo propio: los dos salen con el de «desconocido».
    expect(html).toMatch(markedHtml("dot-small", "gel de ecografía</span>"));
    expect(html).toMatch(markedHtml("dot-small", "declarado agotado</span>", "text"));
  });

  it("si la frase del backend no nombrara lo no disponible, su linea sale fuera del desplegable", () => {
    const lines = resourceStatus(fullRecommendation())?.lines ?? [];
    expect(exposedLines(lines, TEXTS.resourceText)).toEqual([]);
    expect(exposedLines(lines, "").map((line) => line.description)).toEqual(["ecógrafo"]);
    const status = resourceStatusOf({ text: "Falta algo." });
    const html = card(fullRecommendation({ resource_status: status }));
    expect(visibleText(html)).toContain(`ecógrafo · ${TEXTS.unavailableWord} · ${TEXTS.declarerNote}`);
    // Y con su pictograma: la linea expuesta es la misma que la de dentro del desplegable.
    expect(withoutFolded(html)).toMatch(GRAY_WORD);
  });
});

describe("la aclaracion de los recursos se dice una vez", () => {
  const three = [
    fullRecommendation(),
    fullRecommendation({ action: "Segunda acción." }),
    fullRecommendation({ action: "Tercera acción.", resource_status: allAvailable() }),
  ];

  it("en una lista de varias tarjetas, una sola vez y a la vista", () => {
    const seen = visibleText(list(three));
    expect(count(seen, TEXTS.label)).toBe(1);
    expect(count(seen, TEXTS.resourceCaveat)).toBe(1);
    // Va en la cabecera: antes de la primera tarjeta.
    expect(seen.indexOf(TEXTS.label)).toBeLessThan(seen.indexOf("Recomendación del sistema"));
    // Y cada tarjeta sigue diciendo lo suyo.
    expect(count(seen, TEXTS.resourceText)).toBe(2);
    expect(count(seen, "Tercera acción.")).toBe(1);
  });

  it("en una lista de una sola tarjeta (una region del modo anatomico), tambien una vez", () => {
    const seen = visibleText(list([fullRecommendation()]));
    expect(count(seen, TEXTS.label)).toBe(1);
    expect(count(seen, TEXTS.resourceCaveat)).toBe(1);
  });

  it("una tarjeta suelta la lleva ella: usarla fuera de la lista no la hace desaparecer", () => {
    const seen = visibleText(card(fullRecommendation()));
    expect(count(seen, TEXTS.label)).toBe(1);
    expect(count(seen, TEXTS.resourceCaveat)).toBe(1);
  });

  it("sin ningun bloque de recursos no se pinta: no se aclara lo que no se ensena", () => {
    const bare = fullRecommendation({ resource_status: null });
    expect(resourceClarification([bare])).toBeNull();
    expect(list([bare])).not.toContain(TEXTS.label);
    expect(card(bare)).not.toContain(TEXTS.label);
  });

  it("si el backend mandara dos advertencias distintas, se ven las dos", () => {
    const other = resourceStatusOf({ caveat: "Otra advertencia del backend." });
    const found = resourceClarification([
      fullRecommendation(),
      fullRecommendation({ resource_status: other }),
    ]);
    expect(found?.labels).toEqual([TEXTS.label]);
    expect(found?.caveats).toEqual([TEXTS.resourceCaveat, "Otra advertencia del backend."]);
  });

  const source = (path: string): string =>
    readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf-8");

  it("la consola y el modo anatomico pintan sus tarjetas por la lista, que es quien aclara", () => {
    for (const path of ["../dashboard/CrewConsole.tsx", "../anatomy/RegionChain.tsx"]) {
      const code = source(path);
      expect(code, path).toContain("<RecommendationList");
      expect(code, path).not.toContain("<RecommendationCard");
    }
  });

  it("el panel del habitat no ensena recursos declarados: solo la ficha, y no necesita aclaracion", () => {
    const code = source("../habitat/HabitatPanel.tsx");
    expect(code).toContain("<CountermeasureFacts");
    expect(code).not.toContain("ResourceStatusBlock");
    expect(code).not.toContain("<RecommendationCard");
  });
});

describe("el signo de cada cosa de la tarjeta (§5.33.5)", () => {
  const evidence = {
    id: "ficha",
    title: "Una fuente",
    source: "NASA",
    url: null,
    date: null,
    scope_caveat: null,
    scope_in_view: null,
    relevance: null,
    evidence_type: "dataset",
    evidence_type_display: "conjunto de datos",
    evidence_context: null,
    population: "human",
    population_display: "humano",
    not_applicable: [],
    outside_enum: [],
    outside_enum_display: [],
    unverified: [],
    unverified_display: [],
    grade: { tier: "rct", label: "ensayo", preclinical: false, reason: "" },
  } as unknown as EvidenceItem;
  const html = card({ ...declined(), evidence: [evidence, evidence] });

  it("cada plegable de concepto lleva su dibujo delante del rotulo", () => {
    expect(html).toMatch(taggedPictogram("summary", "sheet-lines", "Evidencia (2)</summary>"));
    expect(html).toMatch(taggedPictogram("summary", "coins", "Coste y seguimiento</summary>"));
    expect(html).toMatch(taggedPictogram("summary", "clock-rewind", "Adopciones anteriores (1)</summary>"));
    expect(count(html, "<details")).toBe(count(html, "<summary"));
  });

  it("los dos resumenes con estado siguen con la marca del estado, sin un segundo dibujo delante", () => {
    // Recursos a bordo y Respuesta previa: el dibujo del rotulo es el del estado (cambia), como un
    // mando cuyo dibujo es un estado (§5.33): va en su `<Mark>`, no en un `Fold`.
    expect(html).toMatch(/<summary class="lead"><span class="mark"><svg[^>]*data-pictogram="slash-circle"/);
    expect(html).toMatch(/<summary class="lead"><span class="mark"><svg[^>]*data-pictogram="check"[^>]*>(?:(?!<\/svg>)[\s\S])*<\/svg>Respuesta previa:/);
  });

  it("las claves de la ficha llevan su signo, también contraindicaciones y efectos", () => {
    expect(html).toMatch(taggedPictogram("dt", "book-open", "Respaldo</dt>"));
    expect(html).toMatch(taggedPictogram("dt", "cube", "Recursos</dt>"));
    expect(html).toMatch(taggedPictogram("dt", "stopwatch", "Tiempo de tripulación</dt>"));
    expect(html).toMatch(taggedPictogram("dt", "magnifier", "Seguimiento</dt>"));
    // «Contraindicaciones» y «efectos» no tienen concepto en `uiMarks.ts`: llevan los dibujos de
    // las cabeceras de la biblioteca (§5.36.19), los mismos.
    expect(html).toMatch(taggedPictogram("dt", CONTRAINDICATIONS_PICTOGRAM, "Contraindicaciones</dt>"));
    expect(html).toMatch(taggedPictogram("dt", ADVERSE_EFFECTS_PICTOGRAM, "Efectos a tener en cuenta</dt>"));
  });

  it("el motivo y los dos mandos llevan su signo", () => {
    expect(html).toMatch(markedHtml("bubble-lines", `Motivo: ${TEXTS.rationale}</span>`));
    expect(html).toMatch(taggedPictogram("button", "check", "Adoptar y seguir</button>", ' class="command"'));
    expect(html).toMatch(/<button class="command" type="submit"[^>]*><svg[^>]*data-pictogram="slash-circle"/);
  });
});

describe("la respuesta previa plegada", () => {
  it("sin adopciones no hay desplegable vacio, y la advertencia sigue", () => {
    const item = fullRecommendation({ prior_response: priorOf(0), countermeasure: null, resource_status: null });
    const html = card(item);
    expect(html).not.toContain("<details");
    expect(html).toContain("Sin adopciones anteriores de esta contramedida.");
    expect(html).toContain(TEXTS.priorCaveat);
  });
});

describe("cuanto texto queda a la vista", () => {
  /**
   * La misma recomendacion (`fullRecommendation`: recursos y respuesta previa de dos adopciones),
   * la misma medida (`visibleText.ts`), antes y despues de plegar. «Antes» se midio con esta
   * prueba sobre la tarjeta del commit 82ea87d, antes de tocarla.
   *
   * Con los pictogramas (§5.32.5) las lineas son las mismas: un dibujo no es texto. Hay tres nodos
   * mas porque el rotulo, que era un solo texto, lleva ahora el dominio y la urgencia como marcas
   * separadas; y seis caracteres menos, los de los glifos de texto (⊘, ◌, ↺) que ya no se escriben.
   */
  const BEFORE = { nodes: 40, lines: 29, characters: 1404 };
  /*
   * Con el mosaico del tablero (2026-11-08) hay un nodo, una línea y 37 caracteres más: el mando
   * «Ver detalle: ficha y respuesta previa» (`BoardDetail`). Esta medida solo quita lo que
   * esconde un `<details>`; la ficha tras ese mando sigue contándose, porque su región `hidden`
   * sigue en el DOM y la clásica (`#clasica`) la pinta a la vista, como antes.
   */

  const measure = (html: string) => {
    const seen = withoutFolded(html);
    const lines = textLines(seen);
    return { nodes: textNodes(seen).length, lines: lines.length, characters: lines.join("").length };
  };

  it("una tarjeta suelta, con la aclaracion dentro", () => {
    const after = measure(card(fullRecommendation()));
    expect(after).toEqual({ nodes: 30, lines: 18, characters: 1065 });
    expect(after.lines).toBeLessThan(BEFORE.lines);
  });

  it("una tarjeta dentro de una lista, con la aclaracion en la cabecera", () => {
    const after = measure(card(fullRecommendation(), true));
    expect(after).toEqual({ nodes: 28, lines: 16, characters: 799 });
    expect(after.lines).toBeLessThan(BEFORE.lines);
  });

  it("ningun pictograma anade texto: lo que se lee es lo mismo con y sin ellos", () => {
    const html = card(fullRecommendation());
    const stripped = html.replace(/<svg[\s>][\s\S]*?<\/svg>/g, "");
    expect(textLines(withoutFolded(stripped))).toEqual(textLines(withoutFolded(html)));
    expect(html).not.toMatch(/[⊘◌↺✓▶]/);
  });
});

describe("el mosaico del tablero (2026-11-08) y la clásica", () => {
  // Con una fuente, para ver dónde cae la evidencia (el accesorio no trae ninguna).
  const source = {
    id: "ficha",
    title: "Una fuente",
    source: "NASA",
    url: null,
    date: null,
    scope_caveat: null,
    scope_in_view: null,
    relevance: null,
    evidence_type: "dataset",
    evidence_type_display: "conjunto de datos",
    evidence_context: null,
    population: "human",
    population_display: "humano",
    not_applicable: [],
    outside_enum: [],
    outside_enum_display: [],
    unverified: [],
    unverified_display: [],
    grade: { tier: "rct", label: "ensayo", preclinical: false, reason: "" },
  } as unknown as EvidenceItem;
  const props = { item: fullRecommendation({ evidence: [source] }), operator: "CDR", onAdopt: noop, onDecline: noop };
  const inLook = (look: "classic" | "reference"): string =>
    renderToStaticMarkup(createElement(LookContext.Provider, { value: look }, createElement(RecommendationCard, props)));
  // La región que esconde «Ver detalle» (`BoardDetail`): lo que va dentro, y lo que va antes.
  const split = (html: string): { before: string; folded: string } => {
    const at = html.indexOf('class="board-detail-body" hidden=""');
    expect(at).toBeGreaterThan(0);
    return { before: html.slice(0, at), folded: html.slice(at) };
  };

  it("a la vista: rótulo magenta, acción, motivo, marcas de los recursos, contraindicaciones y los dos mandos", () => {
    const { before } = split(inLook("reference"));
    expect(before).toContain('class="source-tag c-magenta"');
    expect(visibleText(before)).toContain(TEXTS.action);
    expect(visibleText(before)).toContain(`Motivo: ${TEXTS.rationale}`);
    expect(before).toMatch(GRAY_WORD);
    expect(before).toMatch(CYAN_WORD);
    // Lo que hay que saber antes de adoptar va encima del mando, no tras «Ver detalle».
    expect(before).toContain(TEXTS.contraindications);
    expect(before.indexOf(TEXTS.contraindications)).toBeLessThan(before.indexOf("Adoptar y seguir"));
    expect(before).toContain("Adoptar y seguir");
    expect(before).toContain("No adoptar");
  });

  it("tras «Ver detalle», con el mismo texto: la ficha, la respuesta previa con su advertencia y la evidencia", () => {
    const { folded } = split(inLook("reference"));
    // La advertencia de la respuesta previa va con su resumen: se pliegan juntos, nunca por separado.
    expect(folded).toContain(`Respuesta previa: ${TEXTS.priorSummary}`);
    expect(folded).not.toContain(TEXTS.contraindications);
    for (const text of [TEXTS.adverse, `RIDGE: ${TEXTS.ridge}`, TEXTS.priorCaveat]) {
      expect(folded).toContain(text);
    }
    expect(folded).toContain("Evidencia (");
  });

  it("el mando nombra solo lo que pliega: sin contramedida no promete una ficha", () => {
    expect(inLook("reference")).toContain("Ver detalle: ficha, respuesta previa y evidencia");
    const bare = renderToStaticMarkup(
      createElement(RecommendationCard, { item: fullRecommendation({ countermeasure: null, evidence: [source] }) }),
    );
    expect(bare).toContain("Ver detalle: respuesta previa y evidencia");
    expect(bare).not.toContain("Ver detalle: ficha");
  });

  it("la clásica no cambia: sin «Ver detalle», y la ficha antes de los mandos, como siempre", () => {
    const html = inLook("classic");
    expect(html).not.toContain("board-detail");
    expect(html.indexOf(TEXTS.contraindications)).toBeLessThan(html.indexOf("Adoptar y seguir"));
    expect(html.indexOf("Adoptar y seguir")).toBeLessThan(html.indexOf("Evidencia ("));
  });
});
