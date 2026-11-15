/**
 * Los riesgos y el coste de medir en inglés (`lib/i18n.ts`): los rótulos de la ficha de un riesgo,
 * de la matriz y del esquema de niveles. Las palabras de cada nivel, eslabón y frase son del
 * backend (aquí, relleno en mayúsculas): la interfaz no escribe ninguna.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { LookContext } from "../components/BoardOnly";
import type { Indicator, RisksResponse } from "../lib/api";
import { MeasurementCostPanel } from "./MeasurementCostPanel";
import { RisksPanel, RisksView } from "./RisksPanel";

const dataset = {
  id: "d",
  title: "MMASH",
  evidence_type: "dataset",
  evidence_type_display: "x",
  population: "human",
  population_display: "p",
  outside_enum: [],
  not_applicable: [],
};

const risk = {
  risk_id: "cardiovascular",
  display: "DOMINIO",
  ridge: { category: "gravity", display: "G", source: { title: "t", url: null } },
  human_system: { regions: [], basis: "b" },
  effect: { statement: "s", basis: "b", source: null },
  amcl_alignment: "a",
  indicators: [],
  equipment: { groups: [], basis: "b" },
  data_sources: { datasets: [], datasets_empty: "de", documents: [], documents_empty: "do" },
  detection: { summary: "s", danger_limits: [], isolation_statement: "i", environment: [], basis: "b" },
  validation: { keys: [], validates: null, empty: "VACIO", statement: "s", note: null, basis: "b" },
  sensitivity: { keys: [], measures: null, empty: "VACIO", statement: "s", reference: "r", basis: "b" },
  countermeasures: { items: [], empty: "e", basis: "b" },
  uncertainty: {
    quantified: true,
    statement: "u",
    evidence: { references: [{ id: "r1", title: "t", grade: "g", unverified: ["doi"], unverified_display: ["DOI"] }] },
    countermeasures: { note: "n" },
    evaluation: {
      evaluated_with: "measured",
      evaluated_with_display: "ed",
      calculated: [],
      calculated_display: "cd",
      inferred_states: [],
      basis: "b",
    },
  },
};

const body = {
  uncertainty_statement: "U",
  severity_schema: {
    levels: [
      { level: "a", label: "PRIMERO", min_score: null },
      { level: "b", label: "SEGUNDO", min_score: 3 },
    ],
    basis: "b",
    rules_version: "v",
  },
  chain: { basis: "cb", links: [{ key: "hazard", display: "ESLABON" }] },
  detection_rule: {
    display: "REGLA",
    steps: [],
    validated_with: { display: "VW", dataset, scope: null, statement: "s", keys: [], note: "n", keys_basis: "kb" },
    basis: "b",
    rules_version: "v",
  },
  risks: [risk],
} as unknown as RisksResponse;

const board = (element: Parameters<typeof renderToStaticMarkup>[0]) =>
  renderToStaticMarkup(createElement(LookContext.Provider, { value: "reference" }, element));

describe("los riesgos en inglés", () => {
  it("sin respuesta todavía, el título y la espera", () => {
    const html = renderToStaticMarkup(createElement(RisksPanel));
    expect(html).toContain('aria-label="Risks"');
    expect(html).toContain("Loading the risks…");
    expect(html).not.toMatch(/Riesgos|Consultando/);
  });

  const html = board(createElement(RisksView, { body }));

  it("los rótulos de la ficha de un riesgo", () => {
    for (const label of [
      'aria-label="Risk DOMINIO"',
      "Human system",
      ">Scope<",
      ">Indicators<",
      "Evidence cited",
      "Countermeasures",
      ">Evaluated<",
      "Uncertainty",
      'aria-label="Risk matrix"',
    ]) {
      expect(html).toContain(label);
    }
    expect(html).not.toMatch(/Sistema humano|Alcance|Indicadores|Evidencia citada|Contramedidas|Se evalúa|Incertidumbre|Matriz/);
  });

  it("el esquema de niveles es una leyenda: desde y por debajo de, con la palabra del backend", () => {
    expect(html).toContain("Level scheme");
    expect(html).toMatch(/PRIMERO.*below <span class="num">3<\/span> points/);
    expect(html).toMatch(/SEGUNDO.*from <span class="num">3<\/span> points/);
    expect(html).not.toMatch(/Esquema de niveles|desde|por debajo de|puntos/);
  });

  it("lo que falta se dice: sin indicadores de MMASH, sensibilidad sin medir, sin conjunto, sin verificar", () => {
    expect(html).toContain("Without MMASH indicators");
    expect(html).toContain("Sensitivity not measured");
    expect(html).toContain("No dataset cited");
    expect(html).toContain("not verified: DOI");
    expect(html).toContain("This console does not show a quantified uncertainty:");
    // Un recuento a cero no se pinta: ningún riesgo de este cuerpo tiene indicadores de MMASH.
    expect(html).not.toContain("With MMASH indicators");
    expect(html).not.toMatch(/Sin indicadores|sin medir|Sin conjunto|sin verificar|Esta consola/);
  });

  it("el mando de detalle cuenta las fichas", () => {
    expect(html).toContain("Show detail: matrix, rule and 1 record");
  });
});

describe("el coste de medir en inglés", () => {
  it("el título del plegable", () => {
    const indicators = [
      {
        key: "heart-rate",
        display_es: "FC",
        measurement_cost: {
          mode: "continuous-passive",
          mode_display: "CLASE",
          equipment: "eq",
          crew_time_minutes: null,
          crew_time_basis: "b",
          dimensions: {},
        },
      },
    ] as unknown as Indicator[];
    const html = renderToStaticMarkup(createElement(MeasurementCostPanel, { indicators }));
    expect(html).toContain('aria-label="Measurement cost"');
    expect(html).toContain('<h2 class="inline">Measurement cost</h2>');
    // La clase de medida es palabra del backend.
    expect(html).toContain("CLASE");
    expect(html).not.toContain("Coste de medir");
  });
});
