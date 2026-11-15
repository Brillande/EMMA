import { describe, expect, it } from "vitest";

import type { DiaryIndicator, InstrumentStatement } from "../lib/api";
import { designAnchors, scaleLabels } from "./labels";

/**
 * Solo salen los rótulos que el backend entrega con su frase. Una escala propia de la misión
 * no gana ninguno, y nada se traduce ni se completa.
 */
const statement: InstrumentStatement = {
  id: "anclas",
  label: "ROTULO-DE-LA-FRASE",
  quote: "FRASE (1 = Dislike Extremely; 9 = Like Extremely).",
  ref: "ficha",
  source: "CITA-DE-LA-FUENTE",
  title: "TITULO",
  url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC0/",
  where: "Introduction",
  read_on: "2026-10-13",
  extent: "partial",
  extent_text: "leído en parte",
};

const base: DiaryIndicator = {
  key: "food-acceptability",
  display: "Food acceptability, 9-point hedonic scale",
  display_es: "Aceptabilidad de la comida en la escala hedónica de 9 puntos",
  unit: "{score}",
  unit_display: "puntos",
  domain: "nutrition",
  decimals: 1,
  physical_min: 1,
  physical_max: 9,
  range_text: "de 1,0 a 9,0",
  equipment: "autoinforme",
  mode_display: "periódico, no invasivo",
  scale: {
    described_as: "DESCRIPCION-DEL-CATALOGO",
    labels: [
      { value: 1, label: "Dislike Extremely", statement },
      { value: 9, label: "Like Extremely", statement },
    ],
    labels_status: "read",
    labels_language: "en",
    labels_note: "NOTA-DE-ROTULOS",
    labels_sources: [
      {
        ref: "ficha",
        title: "TITULO",
        source: "CITA",
        url: null,
        extent: "partial",
        extent_text: "leído en parte",
        what: "QUE-SE-LEYO",
      },
    ],
    labels_see_also: [{ ...statement, id: "tripulacion", quote: "OTRA-FRASE" }],
    labels_not_found: ["NO-ENCONTRADO"],
    concerning: "low",
    concerning_note: null,
  },
};

const own: DiaryIndicator = {
  ...base,
  key: "mood-valence",
  scale: {
    described_as: "escala breve de autoinforme propia de la misión",
    labels: null,
    labels_status: "own",
    labels_language: null,
    labels_note: "NOTA-DE-ESCALA-PROPIA",
    labels_sources: [],
    labels_see_also: [],
    labels_not_found: [],
    design_anchors: {
      status: "design",
      status_display: "MARCA-DEL-BACKEND",
      decided_on: "2026-10-15",
      why: "POR-QUE-DEL-BACKEND",
      anchors: [
        { value: 0, label: "ANCLA-BAJA" },
        { value: 10, label: "ANCLA-ALTA" },
      ],
      between: "ENTRE-DEL-BACKEND",
      reference: "REFERENCIA-DEL-BACKEND",
    },
    concerning: "low",
    concerning_note: null,
  },
};

describe("rótulos de una escala de autoinforme", () => {
  it("salen solo los que el backend entrega, en el idioma de la fuente y sin traducir", () => {
    const labels = scaleLabels(base);
    expect(labels?.language).toBe("en");
    expect(labels?.anchors.map((item) => [item.point, item.label])).toEqual([
      ["1", "Dislike Extremely"],
      ["9", "Like Extremely"],
    ]);
    // Del 2 al 8 el backend no da nada, y aquí no aparece nada.
    expect(labels?.anchors).toHaveLength(2);
  });

  it("cada rótulo lleva su frase y de dónde sale", () => {
    const first = scaleLabels(base)!.anchors[0]!;
    expect(first.cited.quote).toContain("1 = Dislike Extremely");
    expect(first.cited.origin).toBe(
      "Introduction · CITA-DE-LA-FUENTE · leído en parte · leído el 2026-10-13",
    );
  });

  it("da la fuente con cuánto se leyó, y lo que no se encontró", () => {
    const labels = scaleLabels(base);
    expect(labels?.sources).toEqual([
      { key: "ficha", text: "CITA · leído en parte: QUE-SE-LEYO", url: null },
    ]);
    expect(labels?.notFound).toEqual(["NO-ENCONTRADO"]);
    expect(labels?.seeAlso.map((item) => item.quote)).toEqual(["OTRA-FRASE"]);
    // Los dos rótulos salen de la misma frase: se enseña una vez, y luego la que acompaña.
    expect(labels?.quotes.map((item) => item.id)).toEqual(["anclas", "tripulacion"]);
  });

  it("una escala propia de la misión no gana rótulos", () => {
    expect(scaleLabels(own)).toBeNull();
  });

  it("una magnitud física no tiene escala que rotular", () => {
    expect(scaleLabels({ ...base, scale: null })).toBeNull();
  });

  it("rótulos sin idioma declarado no se pintan", () => {
    const scale = { ...base.scale!, labels_language: null };
    expect(scaleLabels({ ...base, scale })).toBeNull();
    const { labels_language: _dropped, ...older } = base.scale!;
    expect(scaleLabels({ ...base, scale: older })).toBeNull();
  });
});

/**
 * Las anclas de una escala propia las decidió EMMA: salen aparte de los rótulos leídos, con la
 * marca del backend, y nunca en una escala que trae rótulos leídos.
 */
describe("anclas de una escala propia de la misión", () => {
  it("salen con la marca, el porqué, lo de en medio y la referencia del backend", () => {
    const decided = designAnchors(own);
    expect(decided?.mark).toBe("MARCA-DEL-BACKEND");
    expect(decided?.anchors.map((item) => [item.point, item.label])).toEqual([
      ["0", "ANCLA-BAJA"],
      ["10", "ANCLA-ALTA"],
    ]);
    expect(decided?.why).toBe("POR-QUE-DEL-BACKEND");
    expect(decided?.between).toBe("ENTRE-DEL-BACKEND");
    expect(decided?.reference).toBe("REFERENCIA-DEL-BACKEND");
  });

  it("cada extremo lleva el cursor de su lado de la pista, y nada más", () => {
    expect(designAnchors(own)?.anchors.map((item) => item.pictogram)).toEqual([
      "slider-left",
      "slider-right",
    ]);
    // El orden lo decide el valor, no la posición en la lista.
    const decided = own.scale!.design_anchors!;
    const reversed = { ...decided, anchors: [...decided.anchors].reverse() };
    const scale = { ...own.scale!, design_anchors: reversed };
    expect(designAnchors({ ...own, scale })?.anchors.map((item) => item.pictogram)).toEqual([
      "slider-right",
      "slider-left",
    ]);
    // Un ancla intermedia no es un extremo; con una sola no hay extremos.
    const three = { ...decided, anchors: [...decided.anchors, { value: 5, label: "MEDIA" }] };
    expect(
      designAnchors({ ...own, scale: { ...own.scale!, design_anchors: three } })?.anchors.map((item) => item.pictogram),
    ).toEqual(["slider-left", "slider-right", null]);
    const one = { ...decided, anchors: [decided.anchors[0]!] };
    expect(
      designAnchors({ ...own, scale: { ...own.scale!, design_anchors: one } })?.anchors.map((item) => item.pictogram),
    ).toEqual([null]);
  });

  it("no se cuelan entre los rótulos leídos", () => {
    expect(scaleLabels(own)).toBeNull();
  });

  it("una escala con rótulos leídos no enseña anclas decididas, aunque las traiga", () => {
    const scale = { ...base.scale!, design_anchors: own.scale!.design_anchors! };
    expect(designAnchors({ ...base, scale })).toBeNull();
    expect(designAnchors(base)).toBeNull();
  });

  it("sin la marca, o sin ser de diseño, no se pintan", () => {
    const decided = own.scale!.design_anchors!;
    for (const changed of [
      { ...decided, status_display: "  " },
      { ...decided, status: "validated" as unknown as "design" },
      { ...decided, anchors: [] },
    ]) {
      const scale = { ...own.scale!, design_anchors: changed };
      expect(designAnchors({ ...own, scale })).toBeNull();
    }
    expect(designAnchors({ ...own, scale: { ...own.scale!, design_anchors: null } })).toBeNull();
    const { design_anchors: _dropped, ...older } = own.scale!;
    expect(designAnchors({ ...own, scale: older })).toBeNull();
    expect(designAnchors({ ...own, scale: null })).toBeNull();
  });
});
