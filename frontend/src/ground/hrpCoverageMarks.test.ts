import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { EvidenceItem, HrpCoverage, HrpCoverageRisk, RiskMatrixRef } from "../lib/api";
import { UNAVAILABLE_MARK, UNKNOWN_MARK } from "../lib/marks";
import { HrpCoverage as HrpCoveragePanel, HrpCoverageView } from "./HrpCoverage";
import { addressesIn } from "../lib/urlWrapMarkup";
import { statusMark as facilityStatusMark } from "./facilities";
import { statusStyle } from "./framework";
import { coverageMark, coverageRows } from "./hrpCoverageMarks";

/**
 * La cobertura de los riesgos del HRP (§5.36.9): tres respuestas, tres marcas, y ninguna palabra
 * escrita por la interfaz. Se pinta sin red, con un cuerpo como el del backend.
 */

const REF: RiskMatrixRef = {
  id: "hrp-risk-renal-stone",
  title: "Risk of Renal Stone Formation",
  url: "https://humanresearchroadmap.nasa.gov/Risks/risk.aspx?i=81",
  evidence_type: "hrp_risk",
  evidence_type_display: "riesgo del HRP",
  population: null,
  population_display: "no aplica",
  not_applicable: ["doi"],
  outside_enum: [],
};

// Las fichas de cada fila, con la forma de toda cita: se pintan con `EvidenceList`.
const CARD: EvidenceItem = {
  ...REF,
  id: "hrp-renal-stone-evidence-report",
  title: "Evidence Report: Risk of Renal Stone Formation",
  url: "https://humanresearchroadmap.nasa.gov/Evidence/other/2024%20Renal%20Evidence%20Report_Final.pdf",
  source: "NASA Human Research Program",
  doi: null,
  pmid: null,
  organization: "NASA Human Research Program",
  date: "2024-09-23",
  evidence_type: "evidence_report",
  evidence_type_display: "informe de evidencia",
  evidence_context: null,
  population: "human_and_animal",
  notes: "salvedad de alcance del backend",
  outside_enum_display: [],
  unverified: [],
  unverified_display: [],
  relevance: null,
  scope_caveat: "salvedad de alcance del backend",
  scope_in_view: "salvedad de alcance del backend",
  grade: {
    source: "",
    pmid: null,
    basis: "none",
    tier: "desconocido",
    label: "nivel del backend",
    preclinical: false,
    reason: "",
  },
};

function risk(hrr_id: number, coverage: string, extra: Partial<HrpCoverageRisk> = {}): HrpCoverageRisk {
  return {
    hrr_id,
    url: `https://humanresearchroadmap.nasa.gov/Risks/risk.aspx?i=${hrr_id}`,
    title: `Título del riesgo ${hrr_id}`,
    short_title: `Corto ${hrr_id}`,
    status: "active",
    status_display: "activo del backend",
    hrp_element: "Exploration Medical Capability (ExMC)",
    last_published: "2025-05-13",
    ridge: {
      category: "gravity",
      display: "campos gravitatorios",
      basis: "source",
      basis_display: "lo nombra una fuente del backend",
      note: `nota RIDGE ${hrr_id}`,
    },
    coverage,
    coverage_display: `palabra ${coverage}`,
    coverage_statement: `frase ${coverage}`,
    domains: [],
    reason: `motivo ${hrr_id}`,
    refs: [],
    in_catalog: [],
    pending: [],
    ...extra,
  };
}

const BODY: HrpCoverage = {
  note: "nota del backend",
  read_on: "2026-10-23",
  listing: {
    source: { ...REF, id: "hrr-risks", title: "HRR - Risks" },
    count_quote: "Risks 1 - 22 ( of 22 )",
    element_quote: "assigned to an Element",
    updates: "sin fecha del listado",
  },
  count: 3,
  counts: { covered: 1, partial: 1, outside: 1 },
  summary: "resumen del backend",
  coverage_display: { covered: "cubierto", partial: "en parte", outside: "fuera" },
  element_basis: "base del elemento",
  ridge_note: "nota del eje",
  ridge_source: REF,
  pending_note: "pendientes del backend",
  in_catalog_note: "analitos del catálogo del backend",
  risks: [
    risk(77, "covered", {
      domains: [{ key: "bone", display: "óseo", scope: "alcance del dominio óseo" }],
    }),
    risk(81, "partial", {
      domains: [{ key: "genitourinary", display: "genitourinario", scope: "alcance genitourinario" }],
      refs: [CARD],
      in_catalog: [
        {
          key: "urine-calcium-24h",
          display_es: "Calcio en orina de 24 horas (masa por día)",
          code: "6874-2",
          system: "http://loinc.org",
          system_display: "LOINC",
          is_standard_code: true,
          unit: "mg/(24.h)",
          unit_display: "mg/día",
          descriptive_only: true,
          descriptive_display: "descriptivo del backend",
        },
        {
          key: "urine-caox-supersaturation-24h",
          display_es: "Sobresaturación del backend",
          code: "urine-caox-supersaturation-24h",
          system: "https://emma.mission/codes",
          system_display: "código propio del backend",
          is_standard_code: false,
          unit: "1",
          unit_display: "",
          descriptive_only: true,
          descriptive_display: "descriptivo del backend",
        },
      ],
      pending: ["brushita pendiente"],
    }),
    risk(88, "outside"),
  ],
};

describe("coverageMark", () => {
  it("fuera del alcance es «no disponible», y lo cubierto y lo parcial no llevan color", () => {
    expect(coverageMark("outside")).toEqual(UNAVAILABLE_MARK);
    expect(coverageMark("covered").color).toBeNull();
    expect(coverageMark("partial").color).toBeNull();
  });

  it("cada cobertura lleva el dibujo que su idea ya tiene en Tierra", () => {
    // La diana del rótulo «Alcance» de cada riesgo; la mitad de «en parte» de los conjuntos de
    // datos, las instalaciones y las hipótesis; el tachado de «fuera de EMMA» de las hipótesis.
    expect(coverageMark("covered").pictogram).toBe("crosshair");
    expect(coverageMark("partial")).toEqual(facilityStatusMark("partial"));
    expect(coverageMark("outside")).toEqual(statusStyle("outside"));
  });

  it("no reutiliza los dibujos de «medido» y «calculado» de la procedencia", () => {
    const pictograms = ["covered", "partial", "outside"].map((kind) => coverageMark(kind).pictogram);
    expect(new Set(pictograms).size).toBe(3);
    expect(pictograms).not.toContain("dot-filled");
    expect(pictograms).not.toContain("dot-half");
  });

  it("una cobertura que la interfaz no conoce lleva la marca de «desconocido»", () => {
    expect(coverageMark("total")).toBe(UNKNOWN_MARK);
    expect(coverageMark("constructor")).toBe(UNKNOWN_MARK);
  });
});

describe("coverageRows", () => {
  it("son los recuentos del backend con su palabra, en su orden", () => {
    expect(coverageRows({ outside: 8, covered: 7, partial: 7 }, BODY.coverage_display)).toEqual([
      { coverage: "covered", display: "cubierto", count: 7 },
      { coverage: "partial", display: "en parte", count: 7 },
      { coverage: "outside", display: "fuera", count: 8 },
    ]);
  });

  it("una clave heredada no se toma por palabra ni por recuento", () => {
    const rows = coverageRows({ constructor: 1 }, {});
    expect(rows).toEqual([{ coverage: "constructor", display: "constructor", count: 1 }]);
    expect(coverageRows({}, { toString: "palabra" })).toEqual([
      { coverage: "toString", display: "palabra", count: 0 },
    ]);
  });

  it("un recuento sin palabra del backend va con su clave, no se pierde", () => {
    const rows = coverageRows({ ...BODY.counts, total: 2 }, BODY.coverage_display);
    expect(rows.at(-1)).toEqual({ coverage: "total", display: "total", count: 2 });
  });
});

describe("<HrpCoverage>", () => {
  it("mientras consulta lo dice, sin pintar nada más", () => {
    const html = renderToStaticMarkup(createElement(HrpCoveragePanel));
    expect(html).toContain("Consultando los riesgos del HRP…");
  });

  it("pinta cada riesgo con las palabras del backend", () => {
    const html = renderToStaticMarkup(createElement(HrpCoverageView, { body: BODY }));
    for (const text of [
      "resumen del backend",
      "nota del backend",
      "frase covered",
      "frase partial",
      "frase outside",
      "alcance genitourinario",
      "motivo 81",
      "nota RIDGE 88",
      "lo nombra una fuente del backend",
      "Evidence Report: Risk of Renal Stone Formation",
      // La salvedad de alcance va con la ficha, como en el resto de EMMA (`EvidenceList`).
      "salvedad de alcance del backend",
      "pendientes del backend",
      "brushita pendiente",
      // Los analitos que el catálogo ya tiene, con su código, su unidad leída y la frase de
      // descriptivo, todo del backend.
      "analitos del catálogo del backend",
      "Calcio en orina de 24 horas (masa por día)",
      "6874-2",
      "mg/día",
      "descriptivo del backend",
      "código propio del backend",
      "sin fecha del listado",
      "base del elemento",
      "2026-10-23",
      // La página de cada riesgo se lee en el inventario, para poder contrastarlo.
      "https://humanresearchroadmap.nasa.gov/Risks/risk.aspx?i=88",
    ]) {
      expect(html).toContain(text);
    }
    expect(html.match(/<li>/g)?.length).toBeGreaterThanOrEqual(3 + 3 + 1);
  });

  it("el alcance de los dominios no lleva la diana de «cubierto»", () => {
    // Solo la fila cubierta lleva la diana; la parcial, la mitad de «en parte» y nada más.
    const partial = { ...BODY, risks: [BODY.risks[1]!] };
    const html = renderToStaticMarkup(createElement(HrpCoverageView, { body: partial }));
    const row = html.slice(html.indexOf('aria-label="Cobertura de cada riesgo"'));
    expect(row).not.toContain("crosshair");
    expect(row).toContain("circle-half-right");
  });

  it("un riesgo sin pendientes no pinta la lista de analitos", () => {
    const body = { ...BODY, risks: [risk(88, "outside")] };
    const html = renderToStaticMarkup(createElement(HrpCoverageView, { body }));
    expect(html).not.toContain("pendientes del backend");
  });
});

// Lo pintado, no el código: toda dirección en monoespaciada lleva `url` y se parte (§5.38.12).
describe("cobertura del HRP: las direcciones pintadas se parten", () => {
  it("ningún `.num` sin `url` encierra una dirección", () => {
    const { inNum, unwrapped } = addressesIn(renderToStaticMarkup(createElement(HrpCoverageView, { body: BODY })));
    expect(inNum).toBeGreaterThan(0);
    expect(unwrapped).toEqual([]);
  });
});
