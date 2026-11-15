import { describe, expect, it } from "vitest";

import { isPictogramName } from "../icons/registry";
import type { ReportKind } from "../lib/api";
import { UNKNOWN_MARK } from "../lib/marks";
import { KIND_PICTOGRAMS, identityMark, kindPictogram, readingMark } from "./marks";

/** Las marcas de los informes: una por clase, una por veredicto, una por estado de lectura. */

const KINDS: ReportKind[] = ["analitica", "informe-especialista", "alta", "otro"];

describe("la clase de informe", () => {
  it("cada clase del backend tiene su hoja, y las cuatro son distintas", () => {
    expect(Object.keys(KIND_PICTOGRAMS).sort()).toEqual([...KINDS].sort());
    for (const kind of KINDS) expect(isPictogramName(kindPictogram(kind)), kind).toBe(true);
    expect(new Set(KINDS.map(kindPictogram)).size).toBe(KINDS.length);
  });
});

describe("el veredicto de identidad (Polaris `identidad_paciente`)", () => {
  it("ambiguo, otro paciente y sin overlay piden mirar: triangulo y amarillo", () => {
    for (const verdict of ["ambiguo", "otro_paciente", "sin_overlay"]) {
      expect(identityMark(verdict), verdict).toEqual({ pictogram: "shape-triangle", color: "yellow", className: "c-yellow" });
    }
  });

  it("coincide acredita (hecho), parcial acredita la mitad, y lo que falta es un dato ausente; sin color", () => {
    expect(identityMark("coincide")).toEqual({ pictogram: "check", color: null, className: undefined });
    expect(identityMark("parcial")).toEqual({ pictogram: "circle-half-dashed", color: null, className: undefined });
    // `no_textual` es el veredicto de cada informe en una instalacion sin tesseract: no es raro.
    for (const verdict of ["no_consta", "no_textual", "sin_identidad"]) {
      expect(identityMark(verdict), verdict).toEqual({ pictogram: "ring-dotted", color: null, className: undefined });
    }
  });

  it("todos los veredictos de Polaris y el de EMMA tienen marca; uno que no existe, la de desconocido", () => {
    const polaris = ["coincide", "otro_paciente", "parcial", "no_consta", "ambiguo", "no_textual", "sin_overlay"];
    for (const verdict of [...polaris, "sin_identidad"]) {
      expect(identityMark(verdict), verdict).not.toBe(UNKNOWN_MARK);
    }
    expect(identityMark("inventado")).toBe(UNKNOWN_MARK);
  });

  it("coincide, parcial y otro paciente no comparten dibujo", () => {
    const names = ["coincide", "parcial", "otro_paciente"].map((verdict) => identityMark(verdict).pictogram);
    expect(new Set(names).size).toBe(3);
  });
});

describe("el estado de una cifra leida (`app/reports/labs.py`)", () => {
  it("por confirmar es la casilla por marcar; confirmada, el hecho; sin color", () => {
    expect(readingMark("por_confirmar")).toEqual({ pictogram: "box-empty", color: null, className: undefined });
    expect(readingMark("confirmada")).toEqual({ pictogram: "check", color: null, className: undefined });
  });

  it("un estado desconocido no se disfraza de confirmado", () => {
    expect(readingMark("otro")).toBe(UNKNOWN_MARK);
  });
});
