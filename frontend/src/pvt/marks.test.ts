import { describe, expect, it } from "vitest";

import { isPictogramName } from "../icons";
import { UNKNOWN_MARK, mark } from "../lib/marks";
import { basisMark, comparisonMark, phaseMark } from "./marks";
import type { Phase } from "./session";

/**
 * Las marcas de la prueba PVT: una forma por fase, por respaldo y por comparación; ninguna de
 * alerta; lo desconocido con la marca de «desconocido». Aquí no hay cifras ni texto: eso es del
 * backend y de la sesión.
 */

const ALERT = ["red", "yellow", "cyan", "magenta", "green", "blue"];

describe("fases de la sesión", () => {
  it("la espera es el cuadrado vacío y la marca el lleno: se distinguen por forma", () => {
    expect(phaseMark("waiting")).toEqual(mark("square-outline", null));
    expect(phaseMark("stimulus")).toEqual(mark("shape-square", null));
  });

  it("abandonada con el círculo, acabada con la señal de hecho, sin empezar sin forma", () => {
    expect(phaseMark("abandoned")).toEqual(mark("shape-circle", null));
    expect(phaseMark("finished")).toEqual(mark("check", null));
    expect(phaseMark("idle")).toEqual(mark(null, null));
  });

  it("ninguna fase lleva color: la marca no es una alarma, y las que tienen forma no la repiten", () => {
    const phases: Phase[] = ["idle", "waiting", "stimulus", "finished", "abandoned"];
    const drawn = phases.map((phase) => phaseMark(phase).pictogram).filter((name) => name !== null);
    expect(new Set(drawn).size).toBe(drawn.length);
    for (const phase of phases) expect(phaseMark(phase).color).toBeNull();
  });
});

describe("respaldo de un parámetro", () => {
  it("escrito en el repositorio, por diseño o leído en la fuente: tres dibujos, sin color", () => {
    expect(basisMark("repository")).toEqual(mark("sheet-lines", null));
    expect(basisMark("design")).toEqual(mark("pencil", null));
    expect(basisMark("read")).toEqual(mark("book-open", null));
    const names = ["repository", "design", "read"].map((basis) => basisMark(basis).pictogram);
    expect(new Set(names).size).toBe(3);
  });

  it("un respaldo desconocido no se disfraza de otro, ni un nombre heredado de Object", () => {
    expect(basisMark("otro")).toBe(UNKNOWN_MARK);
    expect(basisMark("constructor")).toBe(UNKNOWN_MARK);
  });
});

describe("comparación con lo publicado", () => {
  it("cinco estados, cinco formas distintas, y solo «sin valor publicado» lleva color: gris", () => {
    const statuses = [
      "same_value",
      "same_figure_different_operator",
      "different_value",
      "not_comparable",
      "not_published",
    ];
    const marks = statuses.map((status) => comparisonMark(status));
    expect(new Set(marks.map((item) => item.pictogram)).size).toBe(statuses.length);
    expect(marks.map((item) => item.color)).toEqual([null, null, null, null, "gray"]);
    expect(comparisonMark("same_figure_different_operator")).not.toEqual(comparisonMark("same_value"));
  });

  it("un estado desconocido lleva la marca de «desconocido»", () => {
    expect(comparisonMark("revisado")).toBe(UNKNOWN_MARK);
    expect(comparisonMark("toString")).toBe(UNKNOWN_MARK);
  });
});

describe("todas las marcas", () => {
  it("existen en el registro de pictogramas y ninguna es de alerta", () => {
    const all = [
      ...(["idle", "waiting", "stimulus", "finished", "abandoned"] as const).map(phaseMark),
      ...["repository", "design", "read", "otro"].map(basisMark),
      ...["same_value", "same_figure_different_operator", "different_value", "not_comparable", "not_published", "otro"].map(
        comparisonMark,
      ),
    ];
    for (const item of all) {
      if (item.pictogram !== null) expect(isPictogramName(item.pictogram)).toBe(true);
      expect(ALERT).not.toContain(item.color);
    }
  });
});
