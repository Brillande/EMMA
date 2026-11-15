/**
 * El ciclo y el sexo declarado en inglés (`lib/i18n.ts`). Lo que se firma no cambia con el idioma:
 * el valor que viaja es la clave (`female`, `male`), no la palabra que se enseña.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CREW_SEX_VALUES, type CrewSex } from "../lib/crewSexApi";
import { CycleView, HOW_TO_DECLARE, NOT_APPLICABLE } from "./CyclePanel";
import { CREW_SEX_WORDS, SexFormView } from "./SexForm";

const UNDECLARED = { subject: "crew-01", declared: false, sex: null, status: "PALABRA-NO-DECLARADO", values: ["female", "male"] } as unknown as CrewSex;
const declared = (sex: "female" | "male") =>
  ({ subject: "crew-01", declared: true, sex, declared_by: "FIRMANTE", recorded: "2026-11-01T10:00:00Z", ledger_index: 7, values: ["female", "male"] }) as unknown as CrewSex;

const cycle = (sex: CrewSex | null, ground = false) =>
  renderToStaticMarkup(createElement(CycleView, { sex, records: [], unavailable: null, ground, phaseBaseline: null }));
const form = (sex: CrewSex | null, readOnly = false) =>
  renderToStaticMarkup(createElement(SexFormView, { subject: "crew-01", sex, personal: null, unavailable: null, readOnly }));

describe("el ciclo en inglés", () => {
  it("el panel: título, y cuando no aplica lo dice y explica cómo se declara", () => {
    expect(cycle(null)).toContain('aria-label="Menstrual cycle"');
    const html = cycle(declared("male"));
    expect(html).toContain("Declared sex");
    expect(html).toContain("male");
    expect(html).toContain(`${NOT_APPLICABLE}.`);
    expect(NOT_APPLICABLE).toBe("Cycle tracking does not apply");
    expect(html).toContain(HOW_TO_DECLARE.crew.replace(/“|”/g, (quote) => quote));
    expect(cycle(declared("male"), true)).toContain("The crew member declares it from their own console");
    expect(html).not.toMatch(/Ciclo menstrual|Sexo declarado|masculino|no aplica/);
  });

  it("cuando aplica: la línea base por fase y la lista sin indicadores", () => {
    const html = cycle(declared("female"));
    expect(html).toContain("Baseline by phase");
    expect(html).toContain("not available");
    expect(html).toContain("No cycle indicators in the catalog");
    expect(html).not.toMatch(/Línea base|no disponible|Sin indicadores/);
  });

  it("el sexo declarado: ficha, formulario y palabras; sin declarar, la palabra del backend", () => {
    const html = form(declared("female"));
    expect(html).toContain('aria-label="Declared sex"');
    for (const word of ["Sex", "Declared by", "Signed", "Entry", "female", "Change the declaration", "Who declares", "Sign"]) {
      expect(html, word).toContain(word);
    }
    expect(html).toContain('placeholder="name or call sign"');
    expect(html).not.toMatch(/Declarado por|Firmado|Asiento|femenino|Quién declara|Firmar/);
    const none = form(UNDECLARED);
    expect(none).toContain("PALABRA-NO-DECLARADO");
    expect(none).toContain("Declare");
    // De solo lectura (Tierra) no hay formulario.
    expect(form(declared("female"), true)).not.toContain("Who declares");
  });

  it("lo que se firma es la clave, no la palabra traducida", () => {
    expect(Object.keys(CREW_SEX_WORDS).sort()).toEqual([...CREW_SEX_VALUES].sort());
    expect(form(declared("female"))).toMatch(/type="radio"[^>]*value="female"/);
  });
});
