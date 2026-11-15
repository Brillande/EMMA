/**
 * La ficha de una fuente en inglés (`lib/i18n.ts`): los rótulos «Alcance», «Tipo», «población»,
 * «Nivel» y los del plegable. Las palabras de cada campo (tipo, población, nivel) son del backend.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { EvidenceItem } from "../lib/api";
import { EvidenceEntry, READING_NOTE_SUMMARY, SCOPE_AND_READING_SUMMARY } from "./EvidenceEntry";

const card = (over: Partial<EvidenceItem> = {}) =>
  ({
    id: "ficha",
    title: "TITULO-DE-LA-FUENTE",
    source: "NASA OSDR",
    url: null,
    date: null,
    evidence_type: "dataset",
    evidence_type_display: "TIPO-DEL-BACKEND",
    evidence_context: null,
    population: "animal",
    population_display: "POBLACION-DEL-BACKEND",
    not_applicable: [],
    outside_enum: [],
    outside_enum_display: [],
    unverified: [],
    unverified_display: [],
    relevance: null,
    scope_caveat: "NOTA-ENTERA",
    scope_in_view: "ALCANCE-CORTO",
    grade: { source: "", pmid: null, basis: "none", tier: "desconocido", label: "NIVEL-DEL-BACKEND", preclinical: false, reason: "" },
    ...over,
  }) as unknown as EvidenceItem;

const render = (item: EvidenceItem) => renderToStaticMarkup(createElement(EvidenceEntry, { item }));

describe("la ficha de una fuente en inglés", () => {
  it("los rótulos en inglés y las palabras del backend, tal cual", () => {
    const html = render(card());
    expect(html).toContain("Scope: ALCANCE-CORTO");
    expect(html).toContain("Type: TIPO-DEL-BACKEND");
    expect(html).toContain("population: POBLACION-DEL-BACKEND");
    expect(html).toContain("Level: NIVEL-DEL-BACKEND");
    expect(html).toContain(READING_NOTE_SUMMARY);
    expect(html).not.toMatch(/Alcance|Tipo:|población|Nivel:|Nota de lectura/);
  });

  it("los dos rótulos del plegable", () => {
    expect(READING_NOTE_SUMMARY).toBe("Full reading note: what was read from the source and when");
    expect(SCOPE_AND_READING_SUMMARY).toBe("Scope and reading note: what was read from the source and when");
    expect(render(card({ scope_in_view: null }))).toContain(SCOPE_AND_READING_SUMMARY);
  });

  it("lo que queda fuera del enumerado y lo que está sin verificar", () => {
    const html = render(
      card({ outside_enum: ["population"], outside_enum_display: ["CAMPO-A"], unverified: ["date"], unverified_display: ["CAMPO-B"] }),
    );
    expect(html).toContain("outside the enumeration: CAMPO-A");
    expect(html).toContain("unverified: CAMPO-B");
    expect(html).not.toMatch(/fuera del enumerado|sin verificar/);
  });
});
