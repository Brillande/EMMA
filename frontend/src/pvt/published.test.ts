import { describe, expect, it } from "vitest";

import type { PvtParameter, PvtProtocol, InstrumentStatement, PvtPublished } from "../lib/api";
import { UNKNOWN_MARK, mark } from "../lib/marks";
import { cited, publishedContext, publishedRows } from "./published";

/**
 * Lo publicado va con su versión, con su frase y con lo que dice el backend de cómo queda
 * EMMA. Aquí no se calcula si un valor coincide ni se redacta la diferencia; solo se elige la
 * forma que acompaña al estado del backend (`marks.ts`), y ninguna es de alerta.
 */
const statement = (id: string, quote: string): InstrumentStatement => ({
  id,
  label: `ROTULO-${id}`,
  quote,
  ref: "ficha",
  source: "CITA-DE-LA-FUENTE",
  title: "TITULO",
  url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC0/",
  where: "2.3 Outcome measures",
  read_on: "2026-10-13",
  extent: "partial",
  extent_text: "leído en parte",
});

const lapse: PvtParameter = {
  key: "lapse_threshold_ms",
  display: "PARAM-LAPSO",
  value: 500,
  value_text: "500 ms",
  basis: "repository",
  basis_display: "FUENTE-ESCRITA",
  note: "NOTA",
  scores: true,
  published: {
    status: "same_value",
    status_display: "ESTADO-DEL-BACKEND",
    values: [
      {
        variant: "pvt-10",
        variant_display: "VERSION-LARGA",
        literal: "≥ 500 ms",
        value_ms: 500,
        same: false,
        same_figure: true,
        operator: "≥",
        emma_operator: ">",
        match: "same_figure_different_operator",
        marker_display: "MARCA-MISMA-CIFRA",
        statement: statement("larga", "FRASE-LARGA ≥ 500 ms"),
      },
      {
        variant: "pvt-b",
        variant_display: "VERSION-BREVE",
        literal: "≥ 355 ms",
        value_ms: 355,
        same: false,
        marker_display: "MARCA-DISTINTA",
        statement: statement("breve", "FRASE-BREVE ≥ 355 ms"),
      },
    ],
    see_also: [statement("limite", "FRASE-LIMITE")],
    difference: "DIFERENCIA-DEL-BACKEND",
  },
};

const old: PvtParameter = {
  key: "trials",
  display: "PARAM-ESTIMULOS",
  value: 20,
  value_text: "20",
  basis: "design",
  basis_display: "diseño de EMMA, sin fuente leída",
  note: "NOTA",
};

describe("lo publicado sobre la prueba, parámetro a parámetro", () => {
  it("cada valor va con su versión y con su frase: las dos pruebas no se mezclan", () => {
    const row = publishedRows([lapse])[0]!;
    expect(row.values.map((value) => [value.variant, value.literal, value.cited.quote])).toEqual([
      ["VERSION-LARGA", "≥ 500 ms", "FRASE-LARGA ≥ 500 ms"],
      ["VERSION-BREVE", "≥ 355 ms", "FRASE-BREVE ≥ 355 ms"],
    ]);
    expect(row.values.map((value) => value.key)).toEqual([
      "lapse_threshold_ms-pvt-10",
      "lapse_threshold_ms-pvt-b",
    ]);
  });

  it("cuál es el valor de EMMA lo dice el backend, no se calcula aquí", () => {
    const row = publishedRows([lapse])[0]!;
    expect(row.values.map((value) => value.same)).toEqual([false, false]);
    // La marca, tal cual: la misma cifra con otro operador no se pinta como «=».
    expect(row.values.map((value) => value.marker)).toEqual(["MARCA-MISMA-CIFRA", "MARCA-DISTINTA"]);
    // Sin marca del backend, ninguna: la interfaz no la redacta.
    const bare = { ...lapse.published!, values: lapse.published!.values.map(
      ({ marker_display: _, ...value }) => value) };
    expect(publishedRows([{ ...lapse, published: bare }])[0]!.values.map((v) => v.marker))
      .toEqual([null, null]);
    expect(row.status).toBe("ESTADO-DEL-BACKEND");
    expect(row.difference).toBe("DIFERENCIA-DEL-BACKEND");
    expect(row.emmaValue).toBe("500 ms");
    expect(row.scores).toBe(true);
    expect(row.seeAlso.map((item) => item.quote)).toEqual(["FRASE-LIMITE"]);
  });

  it("lo que no es comparable no lleva marca de igual ni de distinto", () => {
    const published = { ...lapse.published!, status: "not_comparable" as const };
    expect(publishedRows([{ ...lapse, published }])[0]!.comparable).toBe(false);
    expect(publishedRows([lapse])[0]!.comparable).toBe(true);
  });

  it("cada estado del backend lleva su forma, y la misma cifra con otro operador no es «igual»", () => {
    const withStatus = (status: PvtPublished["status"] | "otro") =>
      publishedRows([{ ...lapse, published: { ...lapse.published!, status: status as PvtPublished["status"] } }])[0]!
        .statusMark;
    expect(withStatus("same_value")).toEqual(mark("equals", null));
    expect(withStatus("same_figure_different_operator")).toEqual(mark("tilde-double", null));
    expect(withStatus("different_value")).toEqual(mark("not-equal", null));
    expect(withStatus("not_comparable")).toEqual(mark("dash", null));
    // Sin valor publicado: gris, «no disponible».
    expect(withStatus("not_published")).toEqual(mark("slash-circle", "gray"));
    // Un estado que esta versión no conoce: su palabra, sin forma con significado.
    expect(withStatus("otro")).toBe(UNKNOWN_MARK);
    // Ninguna es una alerta, y cada una se distingue de las demás por la forma.
    const all = ["same_value", "same_figure_different_operator", "different_value", "not_comparable", "not_published"] as const;
    for (const status of all) {
      expect(["red", "yellow", "cyan", "magenta", "green", "blue"]).not.toContain(withStatus(status).color);
    }
    expect(new Set(all.map((status) => withStatus(status).pictogram)).size).toBe(all.length);
  });

  it("un parámetro sin comparación del backend no gana una inventada", () => {
    expect(publishedRows([old])).toEqual([]);
    expect(publishedRows([old, lapse]).map((row) => row.key)).toEqual(["lapse_threshold_ms"]);
  });

  it("sin marca de puntuación del backend no se da por puntuado", () => {
    const row = publishedRows([{ ...lapse, scores: undefined }])[0]!;
    expect(row.scores).toBe(false);
  });

  it("la cita dice sección, fuente, cuánto se leyó y cuándo", () => {
    const one = cited(statement("x", "FRASE"));
    expect(one.origin).toBe(
      "2.3 Outcome measures · CITA-DE-LA-FUENTE · leído en parte · leído el 2026-10-13",
    );
    expect(one.url).toBe("https://pmc.ncbi.nlm.nih.gov/articles/PMC0/");
  });

  it("una fecha de lectura que no es una fecha falla en vez de pintarse", () => {
    expect(() => cited({ ...statement("x", "FRASE"), read_on: "ayer" })).toThrow(RangeError);
  });
});

describe("lo leído que no es de un solo parámetro", () => {
  const protocol = {
    published: {
      note: "NOTA-DE-LO-LEIDO",
      read_on: "2026-10-13",
      sources: [
        {
          ref: "ficha",
          title: "TITULO",
          source: "CITA",
          url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC0/",
          extent: "partial",
          extent_text: "leído en parte",
          what: "QUE-SE-LEYO",
        },
      ],
      context: [statement("poblacion", "FRASE-POBLACION")],
      outcomes_note: "NOTA-DE-MEDIDAS",
      not_found: ["NO-ENCONTRADO"],
    },
  } as PvtProtocol;

  it("da las fuentes con cuánto se leyó, y lo que no se encontró", () => {
    const context = publishedContext(protocol);
    expect(context?.sources).toEqual([
      {
        key: "ficha",
        text: "CITA · leído en parte: QUE-SE-LEYO",
        url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC0/",
      },
    ]);
    expect(context?.notFound).toEqual(["NO-ENCONTRADO"]);
    expect(context?.context.map((item) => item.quote)).toEqual(["FRASE-POBLACION"]);
    expect(context?.note).toBe("NOTA-DE-LO-LEIDO");
    expect(context?.outcomesNote).toBe("NOTA-DE-MEDIDAS");
  });

  it("si el backend no da lo leído, no hay nada que pintar", () => {
    expect(publishedContext({} as PvtProtocol)).toBeNull();
  });
});
