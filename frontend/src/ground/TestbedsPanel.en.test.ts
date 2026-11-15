/**
 * Bancos de prueba, conjuntos de datos e instalaciones en inglés (`lib/i18n.ts`): los rótulos
 * propios de cada panel. Lo que estos paneles dicen que NO hay («buscado y no encontrado», «sin
 * cubrir», «eslabones sin fuente», «falta», «sin verificar») es su razón de ser: se comprueba que
 * el inglés lo dice igual de claro. Las frases del backend pasan tal cual (relleno en mayúsculas).
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { LookContext } from "../components/BoardOnly";
import type { Facilities, HumanDatasets, Testbeds } from "../lib/api";
import { DatasetsPanel, DatasetsView } from "./DatasetsPanel";
import { FacilitiesPanel, FacilitiesView } from "./FacilitiesPanel";
import { TestbedsPanel, TestbedsView } from "./TestbedsPanel";

const board = (element: Parameters<typeof renderToStaticMarkup>[0]) =>
  renderToStaticMarkup(createElement(LookContext.Provider, { value: "reference" }, element));

const quote = {
  ref: "r",
  quote: "CITA",
  source: "s",
  where: "w",
  read_on: "2026-10-20",
  url: null,
  population: null,
  population_display: null,
  unverified_display: ["DOI"],
};

const testbeds = {
  note: "n",
  principle: { text: "p", where: "w" },
  rule: { text: "t", where: "w" },
  validations: [
    {
      id: "scientific",
      name: "VALIDACION",
      what: "w",
      emma_status: { status: "partial", text: "ESTADO" },
      emma: [{ id: "p", context: "ground", what: "w", does_not_show: "d", figures_in: "f", source: "s", url: null }],
      not_covered: "nc",
      banks: ["b1"],
    },
  ],
  banks: [
    {
      id: "b1",
      name: "B1",
      full_name: null,
      evidence_context: "ground",
      outside_enum_text: null,
      context_basis: "cb",
      where: "w",
      validation: "scientific",
      validation_text: "vt",
      reproduces: [quote],
      leaves_out: [],
      columns: [{ id: "duration", label: "COLUMNA", quotes: [], not_found: "NO-HALLADO", read_on: "2026-10-20" }],
      ridge: [],
      ridge_read_on: "2026-10-20",
      variables_kb: "v",
      emma_use: "u",
    },
  ],
  ladder: {
    title: "ESCALERA",
    where: "w",
    rungs: [{ id: "r", environment: "e", strength: "s", limitation: "l", use: "u", banks: [] }],
  },
  ridge: { note: "n", statuses: [{ id: "unknown", text: "NO-SE-SABE" }], hazards: [{ id: "gravity", display: "G" }] },
  not_found: ["x"],
} as unknown as Testbeds;

describe("los bancos de prueba en inglés", () => {
  it("sin respuesta todavía, el título y la espera", () => {
    const html = renderToStaticMarkup(createElement(TestbedsPanel));
    expect(html).toContain('aria-label="Testbeds and validation"');
    expect(html).toContain("Loading the testbeds…");
    expect(html).not.toMatch(/Bancos|Consultando/);
  });

  const html = board(createElement(TestbedsView, { testbeds }));

  it("los apartados y los rótulos de la ficha de un banco", () => {
    for (const label of [
      "RIDGE hazards by testbed",
      'aria-label="Testbed B1"',
      "Evidence setting",
      ">Where<",
      "What it reproduces",
      "Variables (knowledge base §3.1)",
      "For EMMA",
      ">Strength<",
      ">Limitation<",
      "Earth",
    ]) {
      expect(html).toContain(label);
    }
    expect(html).not.toMatch(/Peligros RIDGE|Banco|Entorno de evidencia|Dónde|Qué reproduce|Fortaleza|Limitación|Tierra/);
  });

  it("lo que no hay: sin cubrir, no muestra, deja fuera, no encontrado, ninguno, sin verificar", () => {
    for (const label of [
      "Not covered",
      "Does not show",
      "What it leaves out",
      "Searched and not found",
      ">none<",
      "searched on ",
      "not verified: DOI",
    ]) {
      expect(html).toContain(label);
    }
    // La palabra de lo no encontrado y la de «no se sabe» son del backend.
    expect(html).toContain("NO-HALLADO");
    expect(html).toContain("NO-SE-SABE");
    expect(html).not.toMatch(/Sin cubrir|No muestra|Qué deja fuera|Buscado|ninguno|buscado el|sin verificar/);
  });

  it("los recuentos, con su singular", () => {
    expect(html).toContain("Show detail: 1 validation");
    expect(html).toContain("Show detail: 1 rung and the rule");
    expect(html).toContain("Show detail: 1 testbed, one per row");
    expect(html).toContain("Show detail: 1 search with no result");
    expect(html).toMatch(/<span class="num">1<\/span> testbed</);
  });
});

const access = { level: "open", level_text: "NIVEL", basis_text: "bt", why: null, searched: null, path: null, cited: [] };
const emmaUse = { used: false, used_text: "USO", text: "t", where: null };
const role = { level: "l", level_text: "lt", basis_text: "b", level_why: "w", fitness_text: "f", fitness_why: "fw" };

const datasets = {
  note: "n",
  rule: { text: "t", where: "w" },
  task: { text: "t", where: "w" },
  fitness_rule: { text: "PREGUNTA", where: "w" },
  milestones: { text: "t", where: "w", segments: [{ label: "L-180" }] },
  phases: {},
  controls_rule: { points: [], where: "w" },
  analog_pattern: { text: "t", where: "w" },
  datasets: [
    {
      id: "d1",
      name: "D1",
      population: "human",
      population_display: "POBLACION",
      open_population: "human",
      open_population_display: "ABIERTA",
      open_population_note: null,
      evidence_context: "ground",
      outside_enum_text: null,
      kb_row: "FILA",
      kb_where: "§4",
      subjects: [],
      variables: [],
      areas: null,
      phases: {},
      analog_schedule: null,
      controls: { status: "none", status_text: "cs", items: [], why: null, searched: null, absent: [quote] },
      access,
      emma_use: emmaUse,
      role,
      caveat: "c",
      source: "s",
      url: null,
      ladder: [{ segment: "L-180", labels: ["L-180"], status: "labels", text: null }],
    },
  ],
  catalogs: [
    { id: "c1", name: "C1", kb_row: null, kb_where: null, what: [], access, emma_use: emmaUse, caveat: "c", source: "s", url: null },
  ],
  cipher: {
    name: "CIPHER",
    full_name: "F",
    ladder_cells: [],
    phases: {},
    access,
    emma_use: emmaUse,
    what: quote,
    studies: [],
    studies_where: "sw",
    cohort: quote,
    ladder: [],
    role,
  },
  not_found: ["x", "y"],
} as unknown as HumanDatasets;

describe("los conjuntos de datos en inglés", () => {
  it("sin respuesta todavía, el título y la espera", () => {
    const html = renderToStaticMarkup(createElement(DatasetsPanel));
    expect(html).toContain('aria-label="Human datasets"');
    expect(html).toContain("Human datasets and CIPHER");
    expect(html).toContain("Loading the dataset map…");
    expect(html).not.toMatch(/Conjuntos|Consultando/);
  });

  const html = board(createElement(DatasetsView, { body: datasets }));

  it("los apartados y los rótulos de la ficha de un conjunto", () => {
    for (const label of [
      "Milestone ladder",
      ">Datasets<",
      ">Catalogs<",
      "CIPHER studies",
      'aria-label="Dataset D1"',
      'aria-label="Catalog C1"',
      ">Population<",
      "Open files",
      "Knowledge base §4",
      ">Controls<",
      ">Access<",
      "Use in EMMA",
      "Role and fitness",
      "Of each source, the conversation asks: «PREGUNTA»",
      "with collection days",
      "read on ",
    ]) {
      expect(html).toContain(label);
    }
    expect(html).not.toMatch(
      /Escalera de hitos|Conjunto|Catálogo|Población|Ficheros abiertos|Base de conocimiento|Controles|Acceso|Uso en EMMA|Papel y aptitud|leído el/,
    );
  });

  it("lo que no es y lo que no hay", () => {
    expect(html).toContain("What it is not");
    expect(html).toContain("What the source says is not there:");
    expect(html).toContain("Searched and not found");
    expect(html).toContain("Show detail: 2 searches with no result");
    expect(html).toContain("not verified: DOI");
    expect(html).not.toMatch(/Qué no es|no hay|Buscado|búsqueda|sin verificar/);
  });
});

const facilities = {
  note: "n",
  chain: { text: "t", where: "w" },
  read_on: "2026-10-20",
  facilities: [
    {
      id: "epm",
      name: "EPM",
      full_name: "F",
      experiment: "X",
      kb_role: { text: "t", where: "w" },
      scope_caveat: null,
      unsourced: [],
      links: [
        {
          step: "dataset",
          label: "ESLABON",
          status: "not_found",
          status_text: "ESTADO",
          quotes: [quote],
          missing: { what: "LO-QUE-FALTA", searched: ["s"] },
        },
      ],
    },
  ],
  not_found: [],
} as unknown as Facilities;

describe("las instalaciones de Columbus en inglés", () => {
  it("sin respuesta todavía, el título y la espera", () => {
    const html = renderToStaticMarkup(createElement(FacilitiesPanel));
    expect(html).toContain('aria-label="Columbus facilities: EPM and Biolab"');
    expect(html).toContain("Loading the facilities…");
    expect(html).not.toMatch(/Instalaciones|Consultando/);
  });

  it("los eslabones y lo que falta de cada uno", () => {
    const html = board(createElement(FacilitiesView, { facilities }));
    for (const label of [
      'aria-label="Facility EPM"',
      "Links with no source",
      ">none<",
      ">Missing<",
      "Searched in",
      "Searched and not found",
      "Show detail: the chain of each facility",
      "read on ",
      "not verified: DOI",
    ]) {
      expect(html).toContain(label);
    }
    // Lo que falta lo dice el backend, con su marca de dato ausente.
    expect(html).toContain("LO-QUE-FALTA");
    expect(html).not.toMatch(/Instalación|Eslabones|ninguno|Falta|Buscado|leído el|sin verificar/);
  });
});
