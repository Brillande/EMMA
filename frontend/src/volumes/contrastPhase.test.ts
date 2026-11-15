import { describe, expect, it } from "vitest";

import type {
  ContrastPhaseComparison,
  ContrastPhaseDeclaration,
  ContrastPhaseView,
  ContrastPhaseVocabulary,
} from "../lib/api";
import { canDeclare, comparisonPhase, declaredBy, phaseShown } from "./contrastPhase";

function declaration(index: number, changes: Partial<ContrastPhaseDeclaration> = {}): ContrastPhaseDeclaration {
  return {
    code: "arterial",
    display: "arterial",
    declared_by: "CMO",
    at: "2026-12-01T08:00:00+00:00",
    note: null,
    ledger_index: index,
    recorded: "2026-12-01T08:05:30+00:00",
    ...changes,
  };
}

function view(changes: Partial<ContrastPhaseView> = {}): ContrastPhaseView {
  return {
    applicable: true,
    not_applicable_reason: null,
    current: null,
    undeclared_display: "sin declarar",
    label: "declarada por una persona; EMMA no la propone ni la comprueba",
    history: [],
    ...changes,
  };
}

const VOCABULARY: ContrastPhaseVocabulary = {
  phases: [
    { code: "non-contrast", display: "sin contraste" },
    { code: "arterial", display: "arterial" },
    { code: "unknown", display: "no se sabe" },
  ],
  undeclared_display: "sin declarar",
  modality: "CT",
  label: "declarada por una persona; EMMA no la propone ni la comprueba",
  basis: "El vocabulario es cerrado y de diseño de EMMA.",
  rule: "Vale la última declaración firmada por la consola para cada estudio.",
  scope: "La fase declarada se enseña junto a la densidad.",
};

function compared(changes: Partial<ContrastPhaseComparison> = {}): { fase_contraste: ContrastPhaseComparison } {
  return {
    fase_contraste: {
      estado: "missing",
      texto: "No consta la fase de contraste de los dos estudios.",
      antes: null,
      despues: null,
      sin_declarar: "sin declarar",
      etiqueta: "declarada por una persona; EMMA no la propone ni la comprueba",
      ...changes,
    },
  };
}

describe("lo que consta de la fase de contraste de un estudio", () => {
  it("un backend que no la da no ensena nada", () => {
    expect(phaseShown({})).toBeNull();
    expect(phaseShown({ contrast_phase: null })).toBeNull();
  });

  it("fuera de un TAC no aplica, con el motivo del backend", () => {
    const reason = "La fase de contraste solo se declara en un TAC.";
    expect(phaseShown({ contrast_phase: view({ applicable: false, not_applicable_reason: reason }) })).toEqual({
      kind: "no-aplica",
      reason,
    });
  });

  it("sin declarar es dato ausente, con la palabra del backend", () => {
    expect(phaseShown({ contrast_phase: view() })).toEqual({
      kind: "sin-declarar",
      display: "sin declarar",
      label: view().label,
    });
  });

  it("la vigente es la que da el backend, y las anteriores van aparte, de la mas reciente a la mas antigua", () => {
    const history = [declaration(5), declaration(7, { code: "delayed", display: "tardía" }), declaration(9)];
    const shown = phaseShown({ contrast_phase: view({ current: history[2] ?? null, history }) });
    expect(shown).toEqual({
      kind: "declarada",
      declaration: history[2],
      label: view().label,
      earlier: [history[1], history[0]],
    });
  });

  it("«no se sabe» es una declaracion, no un dato ausente", () => {
    const unknown = declaration(5, { code: "unknown", display: "no se sabe" });
    expect(phaseShown({ contrast_phase: view({ current: unknown, history: [unknown] }) })?.kind).toBe("declarada");
  });

  it("quien la declaro va con la hora de firma en UTC", () => {
    expect(declaredBy(declaration(5))).toBe("CMO · 2026-12-01 08:05 UTC");
    expect(declaredBy(declaration(5, { recorded: "2026-12-01T10:05:00+02:00" }))).toBe("CMO · 2026-12-01 08:05 UTC");
  });
});

describe("cuando se puede enviar una declaracion", () => {
  const undeclared = phaseShown({ contrast_phase: view() });

  it("con una fase del vocabulario del backend y el nombre de quien declara", () => {
    expect(canDeclare(undeclared, VOCABULARY, "arterial", "CMO")).toBe(true);
    expect(canDeclare(undeclared, VOCABULARY, "unknown", " CMO ")).toBe(true);
  });

  it("no sin nombre, ni sin elegir fase, ni con una que el backend no ofrece", () => {
    expect(canDeclare(undeclared, VOCABULARY, "arterial", "")).toBe(false);
    expect(canDeclare(undeclared, VOCABULARY, "arterial", "   ")).toBe(false);
    expect(canDeclare(undeclared, VOCABULARY, "", "CMO")).toBe(false);
    expect(canDeclare(undeclared, VOCABULARY, "delayed", "CMO")).toBe(false);
    expect(canDeclare(undeclared, VOCABULARY, "undeclared", "CMO")).toBe(false);
  });

  it("no sin vocabulario, ni si el backend no dice nada, ni fuera de un TAC", () => {
    expect(canDeclare(undeclared, null, "arterial", "CMO")).toBe(false);
    expect(canDeclare(null, VOCABULARY, "arterial", "CMO")).toBe(false);
    const mr = phaseShown({ contrast_phase: view({ applicable: false, not_applicable_reason: "no es un TAC" }) });
    expect(canDeclare(mr, VOCABULARY, "arterial", "CMO")).toBe(false);
  });

  it("una fase ya declarada se puede declarar de nuevo: asi se corrige", () => {
    const declared = phaseShown({ contrast_phase: view({ current: declaration(5), history: [declaration(5)] }) });
    expect(canDeclare(declared, VOCABULARY, "non-contrast", "CDR")).toBe(true);
  });
});

describe("las fases de dos estudios en la comparacion", () => {
  it("un backend que no las da no ensena nada", () => {
    expect(comparisonPhase({})).toBeNull();
    expect(comparisonPhase({ fase_contraste: null })).toBeNull();
  });

  it("la misma fase va sin color y con el texto del backend", () => {
    const shown = comparisonPhase(
      compared({ estado: "same", texto: "Los dos estudios constan en la misma fase.", antes: declaration(5), despues: declaration(8, { declared_by: "CDR" }) }),
    );
    expect(shown).toEqual({
      tone: "igual",
      texto: "Los dos estudios constan en la misma fase.",
      antes: { kind: "declarada", code: "arterial", display: "arterial", declaredBy: "CMO" },
      despues: { kind: "declarada", code: "arterial", display: "arterial", declaredBy: "CDR" },
    });
  });

  it("fases distintas o una que falta piden atencion, y la que falta es dato ausente", () => {
    expect(comparisonPhase(compared({ estado: "different", antes: declaration(5), despues: declaration(8) }))?.tone).toBe("atencion");
    const missing = comparisonPhase(compared({ antes: declaration(5) }));
    expect(missing?.tone).toBe("atencion");
    expect(missing?.despues).toEqual({ kind: "sin-declarar", display: "sin declarar" });
  });

  it("un estado que esta interfaz no conoce no se rebaja a «igual»", () => {
    expect(comparisonPhase(compared({ estado: "algo-nuevo" }))?.tone).toBe("atencion");
  });

  it("si algun estudio no es un TAC, no aplica", () => {
    expect(comparisonPhase(compared({ estado: "not-applicable" }))?.tone).toBe("no-aplica");
  });
});
