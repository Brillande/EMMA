import { describe, expect, it } from "vitest";

import type { RecordedFindings, UltrasoundProtocol } from "../lib/api";
import {
  NOT_ASSESSABLE,
  NOT_ASSESSABLE_MARK,
  NOT_SEEN_MARK,
  SEEN_MARK,
  WORD_ONLY_MARK,
  missingSigns,
  readable,
  signValueMark,
  withValue,
} from "./findings";

const LUNG: UltrasoundProtocol = {
  key: "lung",
  display: "Pulmón",
  rationale: "",
  checklist: ["Sonda perpendicular a las costillas."],
  sources: [],
  source_grades: [],
  measures: [],
  views: [
    {
      key: "derecha-anterior",
      display: "Derecha, anterior",
      signs: [
        {
          key: "deslizamiento-pleural",
          display: "Deslizamiento pleural",
          values: { presente: "Presente", ausente: "Ausente", [NOT_ASSESSABLE]: "No valorable" },
        },
        {
          key: "lineas-b",
          display: "Líneas B",
          values: { ninguna: "Ninguna", multiples: "Múltiples", [NOT_ASSESSABLE]: "No valorable" },
        },
      ],
    },
  ],
};

describe("formulario de signos", () => {
  it("un signo sin elegir cuenta como pendiente, no como ausente", () => {
    const form = withValue({}, "derecha-anterior", "deslizamiento-pleural", "ausente");
    expect(missingSigns(LUNG, form)).toBe(1);
    expect(missingSigns(LUNG, withValue(form, "derecha-anterior", "lineas-b", NOT_ASSESSABLE))).toBe(0);
  });

  it("un valor que el signo no admite sigue pendiente", () => {
    const form = withValue(
      withValue({}, "derecha-anterior", "deslizamiento-pleural", "neumotorax"),
      "derecha-anterior",
      "lineas-b",
      "ninguna",
    );
    expect(missingSigns(LUNG, form)).toBe(1);
  });

  it("lo registrado se lee con los nombres del protocolo y marca lo no valorable", () => {
    const record: RecordedFindings = {
      ledger_index: 3,
      recorded: "2026-11-14T08:00:00+00:00",
      protocol: "lung",
      checklist: [],
      recorded_by: "CMO",
      findings: { "derecha-anterior": { "deslizamiento-pleural": "ausente", "lineas-b": NOT_ASSESSABLE } },
    };
    expect(readable(LUNG, record)).toEqual([
      { view: "Derecha, anterior", sign: "Deslizamiento pleural", code: "ausente", value: "Ausente", assessable: true },
      { view: "Derecha, anterior", sign: "Líneas B", code: NOT_ASSESSABLE, value: "No valorable", assessable: false },
    ]);
  });
});

describe("la marca de cada valor de un signo", () => {
  it("lo visto lleva la ventana con algo dentro; lo no visto, la ventana vacia; sin color", () => {
    for (const code of ["presente", "visto", "aisladas", "multiples"]) {
      expect(signValueMark(code), code).toBe(SEEN_MARK);
    }
    for (const code of ["ausente", "no-visto", "ninguna"]) {
      expect(signValueMark(code), code).toBe(NOT_SEEN_MARK);
    }
    expect(SEEN_MARK).toEqual({ pictogram: "fan-dot", color: null, className: undefined });
    expect(NOT_SEEN_MARK).toEqual({ pictogram: "fan-dash", color: null, className: undefined });
  });

  it("«no valorable» es no disponible: circulo tachado y gris (tabla F.5-1)", () => {
    expect(signValueMark(NOT_ASSESSABLE)).toBe(NOT_ASSESSABLE_MARK);
    expect(NOT_ASSESSABLE_MARK).toEqual({ pictogram: "slash-circle", color: "gray", className: "c-gray" });
  });

  it("un valor que compara, o uno desconocido, va con su palabra sola: sin suponerle dibujo", () => {
    for (const code of ["mayor", "igual", "menor", "inventado"]) {
      expect(signValueMark(code), code).toBe(WORD_ONLY_MARK);
    }
    expect(WORD_ONLY_MARK).toEqual({ pictogram: null, color: null, className: undefined });
  });

  it("presente, ausente y no valorable tienen tres dibujos distintos", () => {
    const names = ["presente", "ausente", NOT_ASSESSABLE].map((code) => signValueMark(code).pictogram);
    expect(new Set(names).size).toBe(3);
  });
});
