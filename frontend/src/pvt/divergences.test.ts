import { describe, expect, it } from "vitest";

import type { InstrumentStatement, PvtDivergence, PvtProtocol } from "../lib/api";
import { UNKNOWN_MARK, mark } from "../lib/marks";
import { divergenceMark, divergencesView } from "./divergences";

/**
 * Las divergencias se enseñan como las da el backend: con su frase, su ubicación y lo que no se
 * encontró, sin color de alerta. Aquí no se decide si EMMA difiere ni se redacta la consecuencia.
 * La forma de cada estado es un pictograma de `lib/marks.ts`, el mismo dibujo que el carácter de
 * antes (≠, =, ⊘).
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

const item = (key: string, over: Partial<PvtDivergence> = {}): PvtDivergence => ({
  key,
  display: `NOMBRE-${key}`,
  emma: `EMMA-${key}`,
  published: `PUBLICADO-${key}`,
  status: "differs",
  status_display: `ESTADO-${key}`,
  consequence: `CONSECUENCIA-${key}`,
  scores: true,
  kept: "SIN-CAMBIAR",
  sources: [statement(`frase-${key}`, `FRASE-${key}`)],
  not_found: [],
  ...over,
});

const withItems = (items: PvtDivergence[]): PvtProtocol =>
  ({ divergences: { note: "NOTA-DEL-BACKEND", items } }) as unknown as PvtProtocol;

describe("divergencias de la PVT con lo publicado", () => {
  it("van en el orden del backend, con su texto tal cual", () => {
    const view = divergencesView(withItems([item("uno"), item("dos")]))!;
    expect(view.note).toBe("NOTA-DEL-BACKEND");
    expect(view.rows.map((row) => row.key)).toEqual(["uno", "dos"]);
    const [first] = view.rows;
    expect(first).toMatchObject({
      display: "NOMBRE-uno",
      emma: "EMMA-uno",
      published: "PUBLICADO-uno",
      statusDisplay: "ESTADO-uno",
      consequence: "CONSECUENCIA-uno",
      scores: true,
    });
  });

  it("cada frase va con su ubicación, su cita, cuánto se leyó y cuándo", () => {
    const [row] = divergencesView(withItems([item("uno")]))!.rows;
    expect(row!.sources).toEqual([
      {
        id: "frase-uno",
        label: "ROTULO-frase-uno",
        quote: "FRASE-uno",
        origin: "2.3 Outcome measures · CITA-DE-LA-FUENTE · leído en parte · leído el 2026-10-13",
        url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC0/",
      },
    ]);
  });

  it("sin valor publicado no gana una frase: dice lo que se buscó y no se encontró", () => {
    const missing = item("min", { status: "not_published", sources: [], not_found: ["BUSCADO"] });
    const [row] = divergencesView(withItems([missing]))!.rows;
    expect(row!.sources).toEqual([]);
    expect(row!.notFound).toEqual(["BUSCADO"]);
  });

  it("ninguna marca es de alerta: difiere y coincide sin color, sin publicar en gris", () => {
    expect(divergenceMark("differs")).toEqual(mark("not-equal", null));
    expect(divergenceMark("matches")).toEqual(mark("equals", null));
    expect(divergenceMark("not_published")).toEqual({
      pictogram: "slash-circle",
      color: "gray",
      className: "c-gray",
    });
    for (const status of ["differs", "matches", "not_published", "otro"]) {
      expect(["red", "yellow", "cyan", "magenta", "green", "blue"]).not.toContain(
        divergenceMark(status).color,
      );
    }
  });

  it("cada estado tiene su pictograma: el color nunca va solo", () => {
    const pictograms = ["differs", "matches", "not_published"].map((s) => divergenceMark(s).pictogram);
    expect(pictograms).not.toContain(null);
    expect(new Set(pictograms).size).toBe(pictograms.length);
  });

  it("un estado que esta versión no conoce no se disfraza de otro", () => {
    const unknown = divergenceMark("revisado");
    expect(unknown).toBe(UNKNOWN_MARK);
    // Ni un nombre heredado de Object se toma por estado.
    expect(divergenceMark("constructor")).toBe(unknown);
    const [row] = divergencesView(
      withItems([item("x", { status: "revisado", status_display: "PALABRA-NUEVA" })]),
    )!.rows;
    expect(row!.statusDisplay).toBe("PALABRA-NUEVA");
    expect(row!.mark).toEqual(unknown);
  });

  it("lo que no puntúa no dice que puntúa", () => {
    const [row] = divergencesView(withItems([item("x", { scores: false })]))!.rows;
    expect(row!.scores).toBe(false);
  });

  it("lo que no se cambió se dice una vez si es igual para todas", () => {
    const view = divergencesView(withItems([item("uno"), item("dos")]))!;
    expect(view.kept).toBe("SIN-CAMBIAR");
    expect(view.rows.map((row) => row.kept)).toEqual([null, null]);
  });

  it("y en cada una si el backend dice cosas distintas", () => {
    const view = divergencesView(withItems([item("uno"), item("dos", { kept: "OTRO" })]))!;
    expect(view.kept).toBeNull();
    expect(view.rows.map((row) => row.kept)).toEqual(["SIN-CAMBIAR", "OTRO"]);
  });

  it("la cuenta pasa por lib/format", () => {
    const many = Array.from({ length: 12_345 }, (_, index) => item(`k${index}`));
    // Con el espacio fino de los millares (F.5.6 j), no un espacio cualquiera.
    expect(divergencesView(withItems(many))!.count).toBe("12 345");
    expect(divergencesView(withItems([item("uno")]))!.count).toBe("1");
  });

  it("si el backend no las da, o no da ninguna, no hay nada que pintar", () => {
    expect(divergencesView({} as PvtProtocol)).toBeNull();
    expect(divergencesView(withItems([]))).toBeNull();
  });

  it("una fecha de lectura que no es una fecha falla en vez de pintarse", () => {
    const bad = item("x", { sources: [{ ...statement("f", "FRASE"), read_on: "ayer" }] });
    expect(() => divergencesView(withItems([bad]))).toThrow(RangeError);
  });
});
