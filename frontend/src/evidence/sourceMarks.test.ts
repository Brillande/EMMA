import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, textNodes } from "../advisor/visibleText";
import { isPictogramName } from "../icons";
import type { EvidenceItem } from "../lib/api";
import { UNKNOWN_MARK } from "../lib/marks";
import { EVIDENCE_CONTEXTS, EVIDENCE_CONTEXT_PICTOGRAMS, contextPictogram } from "../lib/provenance";
import { SourceFacts } from "./SourceFacts";
import { SourceGrade } from "./SourceGrade";
import {
  EMPTY_FIELD_MARKS,
  POPULATION_MARKS,
  SCOPE_MARK,
  TIER_PICTOGRAMS,
  TYPE_PICTOGRAMS,
  emptyReason,
  gradeMark,
  populationMark,
  typeMark,
} from "./sourceMarks";

/**
 * Los dibujos de la evidencia (§5.32.5) y su paridad con los enumerados del backend: cada nivel de
 * `tier.py`, cada clase de documento de `registry.py` y cada entorno de `lib/provenance.ts` tiene
 * un dibujo, y ninguno sobra. Los colores siguen siendo los de siempre: amarillo si no mide solo
 * en personas, gris si el registro no lo sabe.
 */

const backend = (name: string): string =>
  readFileSync(fileURLToPath(new URL(`../../../backend/app/evidence/${name}`, import.meta.url)), "utf-8");

/**
 * Las claves de un diccionario de Python `NOMBRE[: tipo] = { "clave": "…", … }`, hasta la
 * primera linea que lo cierra (`}` al principio de linea). Se lee el fuente como hace
 * `icons/domains.test.ts` con `codes.py`: la paridad no tiene otra fuente de verdad hoy.
 */
function pythonKeys(source: string, name: string): string[] {
  const start = source.search(new RegExp(`^${name}\\b[^\\n=]*=\\s*\\{`, "m"));
  expect(start, `${name} no esta en el fichero`).toBeGreaterThanOrEqual(0);
  const end = source.slice(start).search(/^\}/m);
  const body = source.slice(start, end < 0 ? undefined : start + end);
  return [...body.matchAll(/^\s+"([a-z0-9_]+)":/gm)].map((match) => match[1] ?? "");
}

describe("paridad con el backend", () => {
  it("cada nivel de evidencia de tier.py tiene dibujo, y ninguno sobra", () => {
    const tiers = pythonKeys(backend("tier.py"), "LABELS");
    expect(tiers.length).toBeGreaterThan(10);
    expect(Object.keys(TIER_PICTOGRAMS).sort()).toEqual([...tiers].sort());
    for (const tier of tiers) expect(isPictogramName(TIER_PICTOGRAMS[tier] ?? ""), tier).toBe(true);
  });

  it("cada clase de documento de registry.py tiene dibujo, y ninguna sobra", () => {
    const types = pythonKeys(backend("registry.py"), "EVIDENCE_TYPES");
    expect(types.length).toBeGreaterThan(8);
    expect(Object.keys(TYPE_PICTOGRAMS).sort()).toEqual([...types].sort());
    for (const type of types) expect(isPictogramName(TYPE_PICTOGRAMS[type] ?? ""), type).toBe(true);
  });

  it("cada poblacion de registry.py tiene marca", () => {
    const populations = pythonKeys(backend("registry.py"), "POPULATIONS");
    expect(Object.keys(POPULATION_MARKS).sort()).toEqual([...populations].sort());
  });

  it("cada entorno de la evidencia tiene el dibujo de `provenance`, el mismo que la insignia de procedencia", () => {
    expect(Object.keys(EVIDENCE_CONTEXT_PICTOGRAMS).sort()).toEqual(Object.keys(EVIDENCE_CONTEXTS).sort());
    for (const name of Object.values(EVIDENCE_CONTEXT_PICTOGRAMS)) expect(isPictogramName(name)).toBe(true);
    expect(contextPictogram("iss")).toBe("station");
    // Un entorno desconocido falla como falla su palabra (`contextLabel`): la ficha no lo pinta.
    expect(() => contextPictogram("otro")).toThrow(/entorno de evidencia desconocido/);
  });
});

describe("el nivel se agrupa por el diseno del estudio", () => {
  it("sintesis, ensayo, cohorte, caso, preclinico, sin revisar y desconocido: siete dibujos", () => {
    expect(new Set(Object.values(TIER_PICTOGRAMS)).size).toBe(7);
    expect(TIER_PICTOGRAMS.metaanalisis).toBe(TIER_PICTOGRAMS.guia_clinica);
    expect(TIER_PICTOGRAMS.rct).toBe(TIER_PICTOGRAMS.ensayo_clinico);
    expect(TIER_PICTOGRAMS.modelo_animal).toBe(TIER_PICTOGRAMS.in_vitro);
    expect(TIER_PICTOGRAMS.desconocido).toBe("question");
  });

  it("amarillo si el backend lo marca preclinico, gris si es desconocido, sin color si no", () => {
    expect(gradeMark({ tier: "modelo_animal", preclinical: true })).toEqual({
      pictogram: "flask",
      color: "yellow",
      className: "c-yellow",
    });
    expect(gradeMark({ tier: "desconocido", preclinical: false })).toEqual({
      pictogram: "question",
      color: "gray",
      className: "c-gray",
    });
    expect(gradeMark({ tier: "rct", preclinical: false })).toEqual({
      pictogram: "bars-two",
      color: null,
      className: undefined,
    });
    // Lo preclinico lo decide el backend, no el dibujo.
    expect(gradeMark({ tier: "rct", preclinical: true }).color).toBe("yellow");
    expect(gradeMark({ tier: "nuevo", preclinical: false }).pictogram).toBe(UNKNOWN_MARK.pictogram);
  });

  it("la insignia pintada: pictograma, palabra del backend, color en la clase y motivo en el title", () => {
    const html = renderToStaticMarkup(
      createElement(SourceGrade, {
        grade: { source: "", pmid: "1", basis: "record", tier: "rct", label: "ensayo aleatorizado", preclinical: false, reason: "r" },
      }),
    );
    expect(html).toMatch(markedHtml("bars-two", "Nivel: ensayo aleatorizado</span>", null, "secondary"));
    expect(html).toContain('<span class="mark secondary" title="r">');
    expect(textNodes(html)).toEqual(["Nivel: ensayo aleatorizado"]);
    const preclinical = renderToStaticMarkup(
      createElement(SourceGrade, {
        grade: { source: "", pmid: null, basis: "text", tier: "modelo_animal", label: "modelo animal", preclinical: true, reason: "" },
      }),
    );
    expect(preclinical).toMatch(markedHtml("flask", "Nivel: modelo animal</span>", "yellow"));
  });
});

describe("la clase de documento y la poblacion", () => {
  it("una clase sin verificar va en gris con la interrogacion; una conocida con su dibujo", () => {
    expect(typeMark(null)).toEqual({ pictogram: "question", color: "gray", className: "c-gray" });
    expect(typeMark("dataset")).toEqual({ pictogram: "table-grid", color: null, className: undefined });
    expect(typeMark("nueva")).toEqual({ pictogram: UNKNOWN_MARK.pictogram, color: null, className: undefined });
  });

  it("la poblacion: busto si es humana; huella en amarillo si no lo es solo", () => {
    expect(populationMark("human")).toEqual({ pictogram: "person", color: null, className: undefined });
    expect(populationMark("animal").color).toBe("yellow");
    expect(populationMark("human_and_animal")).toEqual({ pictogram: "person-paw", color: "yellow", className: "c-yellow" });
    expect(populationMark(null)).toEqual({ pictogram: "question", color: "gray", className: "c-gray" });
  });

  const item = (over: Partial<EvidenceItem> = {}): EvidenceItem => ({
    id: "ficha",
    title: "Una fuente",
    source: "NASA",
    url: null,
    doi: null,
    pmid: null,
    organization: null,
    date: "2017",
    evidence_type: "journal_article",
    evidence_type_display: "artículo de revista",
    evidence_context: "analog_bedrest",
    population: "human",
    population_display: "humano",
    notes: null,
    not_applicable: [],
    outside_enum: [],
    outside_enum_display: [],
    unverified: [],
    unverified_display: [],
    relevance: null,
    scope_caveat: null,
    scope_in_view: null,
    grade: { source: "", pmid: null, basis: "none", tier: "desconocido", label: "desconocido", preclinical: false, reason: "" },
    ...over,
  });

  it("la ficha pintada: cada dato con su dibujo junto a la palabra del backend, y nada mas de texto", () => {
    const html = renderToStaticMarkup(createElement(SourceFacts, { source: item() }));
    expect(html).toMatch(markedHtml("sheet-lines", "Tipo: artículo de revista</span>"));
    expect(html).toMatch(markedHtml("bed", "análogo: reposo en cama</span>"));
    expect(html).toContain('entorno: <span class="mark"><svg');
    expect(html).toMatch(markedHtml("person", "población: humano</span>"));
    expect(textNodes(html).join(" ")).toBe("Tipo: artículo de revista · 2017 · entorno: análogo: reposo en cama · población: humano");
  });

  it("lo no verificado va en gris: la clase con interrogacion, la poblacion tambien", () => {
    const html = renderToStaticMarkup(
      createElement(SourceFacts, {
        source: item({
          evidence_type: null,
          evidence_type_display: "sin clasificar",
          evidence_context: null,
          population: null,
          population_display: "sin clasificar",
          unverified: ["population"],
          unverified_display: ["población"],
        }),
      }),
    );
    expect(html).toMatch(markedHtml("question", "Tipo: sin clasificar</span>", "gray"));
    expect(html).toMatch(markedHtml("question", "población: sin clasificar</span>", "gray"));
    // Con su marca, no solo el gris (§5.33.5): la interrogacion de lo no verificado.
    expect(html).toMatch(markedHtml("question", "sin verificar: población</span>", "gray"));
    expect(html).not.toContain("entorno:");
    expect(html).not.toMatch(/<span class="c-gray">/);
  });

  it("lo fuera del enumerado lleva el circulo tachado de «no disponible», en gris", () => {
    const html = renderToStaticMarkup(
      createElement(SourceFacts, {
        source: item({ outside_enum: ["evidence_context"], outside_enum_display: ["entorno"] }),
      }),
    );
    expect(html).toMatch(markedHtml("slash-circle", "fuera del enumerado: entorno</span>", "gray"));
    expect(textNodes(html)).toContain("fuera del enumerado: entorno");
  });

  it("un campo vacio lleva la marca de POR QUE lo esta, la misma junto a su palabra y en su lista", () => {
    // La poblacion se leyo y el enumerado no la cubre: el circulo tachado, no la interrogacion de
    // lo que nadie ha leido. Un hecho, un signo (§5.33.5).
    const outside = renderToStaticMarkup(
      createElement(SourceFacts, {
        source: item({
          population: null,
          population_display: "fuera del enumerado",
          outside_enum: ["population"],
          outside_enum_display: ["población"],
        }),
      }),
    );
    expect(outside).toMatch(markedHtml("slash-circle", "población: fuera del enumerado</span>", "gray"));
    expect(outside).toMatch(markedHtml("slash-circle", "fuera del enumerado: población</span>", "gray"));
    expect(outside).not.toContain('data-pictogram="question"');
    // Una clase que no procede: el guion de «no aplica», en gris.
    const notApplicable = renderToStaticMarkup(
      createElement(SourceFacts, {
        source: item({ evidence_type: null, evidence_type_display: "no aplica", not_applicable: ["evidence_type"] }),
      }),
    );
    expect(notApplicable).toMatch(markedHtml("dash", "Tipo: no aplica</span>", "gray"));
  });

  it("emptyReason lee las listas de la ficha; sin ellas, el campo esta sin verificar", () => {
    const none = { not_applicable: [], outside_enum: [] };
    expect(emptyReason(none, "population")).toBe("unverified");
    expect(emptyReason({ ...none, not_applicable: ["population"] }, "population")).toBe("not_applicable");
    expect(emptyReason({ ...none, outside_enum: ["population"] }, "population")).toBe("outside_enum");
    expect(EMPTY_FIELD_MARKS).toEqual({
      unverified: { pictogram: "question", color: "gray", className: "c-gray" },
      not_applicable: { pictogram: "dash", color: "gray", className: "c-gray" },
      outside_enum: { pictogram: "slash-circle", color: "gray", className: "c-gray" },
    });
    expect(typeMark(null, "outside_enum")).toBe(EMPTY_FIELD_MARKS.outside_enum);
    expect(populationMark(null, "not_applicable")).toBe(EMPTY_FIELD_MARKS.not_applicable);
  });

  it("la advertencia de alcance: el triangulo en amarillo", () => {
    expect(SCOPE_MARK).toEqual({ pictogram: "shape-triangle", color: "yellow", className: "c-yellow" });
  });
});
