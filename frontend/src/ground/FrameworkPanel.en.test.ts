/**
 * «Marco de NASA e hipótesis de diseño» en inglés (`lib/i18n.ts`): los rótulos propios del panel,
 * de la credibilidad y de la cobertura del HRP. El texto del backend va tal cual (aquí, en
 * mayúsculas de relleno); lo que se prueba es que ningún rótulo de la interfaz queda en castellano
 * y que las negaciones («no leído», «no demuestra», «sin evaluar») se dicen igual de claras.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { LookContext } from "../components/BoardOnly";
import type { Credibility, Framework, HrpCoverage } from "../lib/api";
import { CredibilityView } from "./CredibilityView";
import { FrameworkPanel, FrameworkView } from "./FrameworkPanel";
import { HrpCoverage as HrpCoveragePanel, HrpCoverageView } from "./HrpCoverage";

const board = (element: Parameters<typeof renderToStaticMarkup>[0]) =>
  renderToStaticMarkup(createElement(LookContext.Provider, { value: "reference" }, element));

const gapStatus = { id: "X-1", status: "closed", status_text: "ESTADO", source: "S", where: "W", read_on: "2026-10-13", url: "U" };

const framework = {
  exmc_gaps: {
    note: "NOTA",
    source: "FUENTE",
    url: "https://example.org",
    med07: { label: "HUECO-A", gap: "g", status: gapStatus, emma: "e" },
    med10: { label: "HUECO-B", gap: "g", status: gapStatus, merged_into: null, emma: "e" },
  },
  imm: { what: "w", not_duplicated: "n", url: "u" },
  design_hypotheses: {
    note: "n",
    source: { document: "d", section: "1", title: "t" },
    statuses: [{ id: "simulated", text: "PALABRA" }],
    hypotheses: [
      {
        id: "h1",
        label: "H1",
        statement: "s",
        status: "simulated",
        status_text: "PALABRA",
        real_data: "rd",
        touches: [],
        scenario: "sc",
        documents: ["d.md"],
        not_demonstrated: "nd",
      },
    ],
    unread_anchors: [],
  },
  read_sources: {
    note: "n",
    sources: [{ ref: "r", title: "t", extent: "full", extent_text: "E", read_on: "2026-10-13", what: "w" }],
    blocks: [
      {
        id: "b1",
        title: "BLOQUE",
        about: "a",
        question: { text: "q", answer: "a", rests_on: [] },
        statements: [
          { id: "s1", label: "l", quote: "q", note: null, source: "s", where: "w", extent: "full", extent_text: "E", read_on: "2026-10-13", url: "u" },
        ],
        emma: "e",
        not_read: ["x"],
        coverage: { about: "a", counts: {}, rows: [] },
      },
    ],
    coverages: [],
  },
  ridge: { cardiovascular: { hazard: "gravity", display: "G" } },
  credibility: null,
} as unknown as Framework;

describe("el marco de NASA en inglés", () => {
  it("sin respuesta todavía, el título y la espera", () => {
    const html = renderToStaticMarkup(createElement(FrameworkPanel));
    expect(html).toContain('aria-label="NASA framework and design hypotheses"');
    expect(html).toContain("Loading the framework…");
    expect(html).not.toMatch(/Marco de NASA|Consultando/);
  });

  it("los apartados y sus rótulos", () => {
    const html = board(createElement(FrameworkView, { framework }));
    for (const label of [
      "MDA gaps (ExMC): 2020 statement and status today",
      "Design hypotheses",
      "What was read in NASA&#x27;s sources",
      "RIDGE hazard of each domain",
      "Specification anchors not read",
      "Documents read",
      "Real data and scope",
      "EMMA components",
      "Simulated scenario",
      "Question",
      "What the reading answers",
      "Point by point: what EMMA does",
    ]) {
      expect(html).toContain(label);
    }
    expect(html).not.toMatch(/Huecos del MDA|Hipótesis|Lo leído|Peligro RIDGE|Anclajes|Piezas de EMMA|Pregunta|Punto por punto/);
  });

  it("lo que no hay se dice igual de claro: no demuestra, no leído, ninguna pieza, no interviene", () => {
    const html = board(createElement(FrameworkView, { framework }));
    expect(html).toContain("EMMA does not demonstrate");
    expect(html).toContain("Not read or not found");
    expect(html).toContain("Credibility of each layer: unavailable");
    expect(html).toContain("None declared. What remains unread of each source is in its block, above.");
    expect(html).toMatch(/>none</);
    expect(html).toContain("It plays no part in the crew&#x27;s status or in any alert.");
    expect(html).not.toMatch(/EMMA no demuestra|No leído|no disponible|Ninguno declarado|No interviene/);
  });

  it("los mandos de detalle cuentan en inglés, con su singular", () => {
    const html = board(createElement(FrameworkView, { framework }));
    expect(html).toContain("Show detail: where they come from and 1 hypothesis");
    expect(html).toContain("Show detail: 1 document read");
    expect(html).toContain("Show detail: 1 statement read");
    expect(html).toContain("Show detail: statement, status and what was read");
    expect(html).not.toMatch(/de dónde salen|documento leído|frase leída|enunciado/);
  });
});

const credibility = {
  title: "TITULO",
  about: "a",
  note: "n",
  sources: [],
  statements: [],
  not_assessed: "na",
  emma: "e",
  groups: [],
  layers: [
    {
      id: "l1",
      display: "CAPA",
      observation_type: "inferred",
      observation_type_text: "PALABRA",
      model_version: "v1",
      model_note: null,
      sites: [],
      served_in: [],
      tests: [],
      factors: [],
      criticality: [],
    },
  ],
  out_of_scope: [],
  not_read: [],
  criticality: { title: "CRITICIDAD", about: "a", read_on: "2026-10-20", statements: [], not_applied: "x", axes: [] },
} as unknown as Credibility;

describe("la credibilidad de cada capa en inglés", () => {
  const html = board(createElement(CredibilityView, { credibility }));

  it("lo que no se ha hecho: sin evaluar, sin aplicar, fuera de las fichas, no leído", () => {
    for (const label of ["Not assessed", "Not applied", "Outside these records", "Not read or not found"]) {
      expect(html).toContain(label);
    }
    expect(html).not.toMatch(/Sin evaluar|Sin aplicar|Fuera de estas fichas|No leído/);
  });

  it("los rótulos de la ficha de una capa y de lo leído de la norma", () => {
    for (const label of [
      "The eleven factors of the standard",
      "The two axes of the matrix",
      "Where it is labeled and served",
      ">Model<",
      ">Tests<",
      "Read on ",
      "Show detail: what was read of the standard and 1 layer",
    ]) {
      expect(html).toContain(label);
    }
    expect(html).not.toMatch(/Los once factores|Los dos ejes|Dónde se rotula|Modelo|Pruebas|Leído el|capa</);
  });
});

const coverage = {
  count: 1,
  summary: "s",
  counts: {},
  coverage_display: {},
  note: "n",
  risks: [
    {
      hrr_id: "1",
      short_title: "CORTO",
      title: "t",
      coverage: "partial",
      coverage_statement: "FRASE",
      reason: "r",
      ridge: { category: "gravity", display: "G", basis_display: "b", note: "n" },
      hrp_element: "e",
      status_display: "sd",
      last_published: "2026-01-01",
      url: "u",
      domains: [{ key: "cardiovascular", display: "D", scope: "sc" }],
      refs: [],
      in_catalog: [{ key: "k", display_es: "X", system_display: "S", code: "c", unit_display: null, descriptive_display: null }],
      pending: ["p"],
    },
  ],
  pending_note: "pn",
  in_catalog_note: "icn",
  ridge_note: "rn",
  element_basis: "eb",
  listing: { source: { title: "t" }, count_quote: "cq", updates: "u" },
  read_on: "2026-10-20",
} as unknown as HrpCoverage;

describe("los riesgos del HRP en inglés", () => {
  it("sin respuesta, la espera", () => {
    const html = renderToStaticMarkup(createElement(HrpCoveragePanel));
    expect(html).toContain("Loading the HRP risks…");
    expect(html).not.toContain("Consultando");
  });

  it("el plegable y sus listas", () => {
    const html = renderToStaticMarkup(createElement(HrpCoverageView, { body: coverage }));
    for (const label of [
      'aria-label="HRP risks"',
      "HRP risks and EMMA coverage",
      'aria-label="Count by coverage"',
      'aria-label="Coverage of each risk"',
      "Scope of each domain",
      'aria-label="Catalog measures and analytes"',
      'aria-label="Pending measures and analytes"',
    ]) {
      expect(html).toContain(label);
    }
    // La frase de la cobertura es del backend y pasa tal cual.
    expect(html).toContain("FRASE");
    expect(html).not.toMatch(/Riesgos del HRP|Recuento|Cobertura de cada|Alcance de cada|Medidas y analitos/);
  });
});
