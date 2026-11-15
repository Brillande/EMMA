import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { EvidenceItem, RiskEntity } from "../lib/api";
import { HumanSystemRegion } from "./RisksPanel";
import { phraseRefs } from "./risks";

/**
 * «Sistema humano» en la ficha de cada riesgo (§5.37.16): bajo la frase de cada región, las fichas
 * que esa frase nombra, tal cual llegan de `GET /api/risks` y pintadas como toda cita de EMMA.
 */

type Region = RiskEntity["human_system"]["regions"][number];

const card = (id: string, title: string, caveat: string | null): EvidenceItem => ({
  id,
  title,
  source: `fuente de ${id}`,
  url: `https://example.org/${id}`,
  doi: null,
  pmid: null,
  organization: null,
  date: null,
  evidence_type: "agency_page",
  evidence_type_display: "página de agencia",
  evidence_context: null,
  population: caveat === null ? "human" : "human_and_animal",
  population_display: caveat === null ? "humano" : "humano y animal",
  notes: caveat,
  not_applicable: [],
  outside_enum: [],
  outside_enum_display: [],
  unverified: [],
  unverified_display: [],
  relevance: `para qué se cita ${id}`,
  scope_caveat: caveat,
  scope_in_view: caveat,
  grade: {
    source: "",
    pmid: null,
    basis: "none",
    tier: "desconocido",
    label: "desconocido: no clasificable desde el registro",
    preclinical: false,
    reason: "",
  },
});

const STONE_CAVEAT = "Junta datos de tripulaciones, reposo en cama, clínica y modelos.";
const STONE = card("hrp-renal-stone-evidence-report", "Evidence Report: Risk of Renal Stone Formation", STONE_CAVEAT);
const MEDLINEPLUS = card("medlineplus-liver-function-tests", "Liver Function Tests", null);

const region = (overrides: Partial<Region>): Region => ({
  key: "heart",
  display: "Corazón y circulación",
  domains: ["cardiovascular"],
  note: "Pulso, variabilidad, presión y ortostatismo.",
  note_refs: [],
  analytes_source: null,
  ...overrides,
});

const render = (item: Region) => renderToStaticMarkup(createElement(HumanSystemRegion, { region: item }));

describe("las fichas de la frase de cada región en «Sistema humano» (§5.37.16)", () => {
  it("junta las de la frase y la de la lista de analitos, en ese orden y sin copiarlas", () => {
    expect(phraseRefs(region({}))).toEqual([]);
    expect(phraseRefs(region({ note_refs: [STONE] }))).toEqual([STONE]);
    expect(phraseRefs(region({ analytes_source: MEDLINEPLUS }))).toEqual([MEDLINEPLUS]);
    expect(phraseRefs(region({ note_refs: [STONE], analytes_source: MEDLINEPLUS }))).toEqual([STONE, MEDLINEPLUS]);
  });

  it("pinta la ficha bajo la frase, con su título, para qué se cita y su salvedad", () => {
    const html = render(region({ key: "bladder", display: "Riñones, vejiga y vías urinarias", note: "Cálculos.", note_refs: [STONE] }));
    expect(html.indexOf("Cálculos.")).toBeLessThan(html.indexOf(STONE.title));
    expect(html).toContain('<ul class="evidence">');
    expect(html).toContain(STONE.relevance ?? "");
    expect(html).toContain(STONE_CAVEAT);
  });

  it("la región sin nivel propio enseña la ficha que su frase nombra", () => {
    const html = render(region({ key: "liver", display: "Hígado", domains: [], note: "Según MedlinePlus.", analytes_source: MEDLINEPLUS }));
    expect(html).toContain(MEDLINEPLUS.title);
  });

  it("una región cuya frase no nombra ninguna ficha no lleva lista vacía", () => {
    expect(render(region({}))).not.toContain('class="evidence"');
  });
});
