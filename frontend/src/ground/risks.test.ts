import { describe, expect, it } from "vitest";

import { basisPictogram } from "../advisor/recommendation";
import { typeMark } from "../evidence/sourceMarks";
import type {
  RiskEntity,
  RiskMatrixRef,
  RiskSensitivity,
  RiskSeveritySchema,
  RiskValidation,
} from "../lib/api";
import { LEVELS } from "../lib/levels";
import { EMPTY_MARK, mark } from "../lib/marks";
import { OBSERVATION_TYPES } from "../lib/provenance";
import { pictogram } from "../icons/registry";
import { signPictogram, uiPictogram } from "../lib/uiMarks";
import {
  CHAIN_SIGNS,
  DETECTION_STEP_SIGNS,
  SENSITIVITY_MARK,
  UNKNOWN_EVALUATION,
  UNKNOWN_LEVEL_PICTOGRAM,
  UNKNOWN_SIGN,
  UNVERIFIED_STYLE,
  VERIFIED_STYLE,
  chainSign,
  countermeasureMark,
  dataMark,
  dataPopulationMark,
  evaluationStyle,
  levelRows,
  linkLabel,
  quantifiedUnexpectedly,
  referenceStyle,
  sensitivityMark,
  stepSign,
  validationMark,
} from "./risks";

// Las palabras son las que da el backend en cada respuesta; aquí van de relleno a propósito.
const SCHEMA: RiskSeveritySchema = {
  levels: [
    { level: "nominal", display: "palabra-0", label: "Palabra-0", min_score: null },
    { level: "watch", display: "palabra-1", label: "Palabra-1", min_score: 20 },
    { level: "concern", display: "palabra-2", label: "Palabra-2", min_score: 45 },
    { level: "critical", display: "palabra-3", label: "Palabra-3", min_score: 70 },
  ],
  basis: "base del backend",
  rules_version: "reglas@0",
};

const risk = (id: string, quantified: boolean): RiskEntity =>
  ({ risk_id: id, uncertainty: { quantified } }) as RiskEntity;

describe("entidad Riesgo", () => {
  it("cada tramo acaba donde empieza el siguiente, y el último no acaba", () => {
    expect(levelRows(SCHEMA).map((row) => [row.from, row.below])).toEqual([
      [null, 20],
      [20, 45],
      [45, 70],
      [70, null],
    ]);
  });

  it("el nombre de cada nivel es el del backend, no uno de aquí", () => {
    expect(levelRows(SCHEMA).map((row) => row.label)).toEqual([
      "Palabra-0",
      "Palabra-1",
      "Palabra-2",
      "Palabra-3",
    ]);
  });

  it("la leyenda lleva la forma de cada nivel y ningún color de alarma", () => {
    const rows = levelRows(SCHEMA);
    expect(rows.map((row) => row.pictogram)).toEqual([
      LEVELS.nominal.pictogram,
      LEVELS.watch.pictogram,
      LEVELS.concern.pictogram,
      LEVELS.critical.pictogram,
    ]);
    for (const row of rows) expect(row).not.toHaveProperty("color");
  });

  it("si el motor mueve un umbral, la leyenda lo sigue", () => {
    const moved = {
      ...SCHEMA,
      levels: SCHEMA.levels.map((item) => (item.level === "critical" ? { ...item, min_score: 71 } : item)),
    };
    expect(levelRows(moved).map((row) => row.below)).toEqual([20, 45, 71, null]);
  });

  it("un nivel desconocido se enseña sin suponerle forma", () => {
    const odd = { ...SCHEMA, levels: [{ level: "otro", display: "x", label: "X", min_score: null }] };
    expect(levelRows(odd)).toEqual([
      { level: "otro", label: "X", pictogram: UNKNOWN_LEVEL_PICTOGRAM, from: null, below: null },
    ]);
  });

  it("una ficha con campos sin verificar es un dato ausente: cian y pictograma propio", () => {
    expect(referenceStyle({ unverified: ["date"] })).toBe(UNVERIFIED_STYLE);
    expect(referenceStyle({ unverified: [] })).toBe(VERIFIED_STYLE);
    expect(UNVERIFIED_STYLE.color).toBe("cyan");
    expect(UNVERIFIED_STYLE.pictogram).toBe("ring-dotted");
    expect(UNVERIFIED_STYLE.pictogram).not.toBe(VERIFIED_STYLE.pictogram);
  });

  it("un dominio sin indicadores va en gris; los demás, sin color", () => {
    expect(evaluationStyle("none").color).toBe("gray");
    expect(evaluationStyle("measured").color).toBeNull();
    expect(evaluationStyle("calculated-only").color).toBeNull();
    const pictograms = ["measured", "calculated-only", "none"].map((kind) => evaluationStyle(kind).pictogram);
    expect(new Set(pictograms).size).toBe(3);
    // Medido y calculado llevan las formas de «medido» e «inferido» de la procedencia: son eso.
    expect(evaluationStyle("measured").pictogram).toBe(OBSERVATION_TYPES.measured.pictogram);
    expect(evaluationStyle("calculated-only").pictogram).toBe(OBSERVATION_TYPES.inferred.pictogram);
    expect(evaluationStyle("inventada")).toBe(UNKNOWN_EVALUATION);
  });

  it("avisa si un riesgo llegara diciendo que su incertidumbre está cuantificada", () => {
    expect(quantifiedUnexpectedly([risk("bone", false), risk("immune", false)])).toEqual([]);
    expect(quantifiedUnexpectedly([risk("bone", true), risk("immune", false)])).toEqual(["bone"]);
  });
});

const ref = (overrides: Partial<RiskMatrixRef>): RiskMatrixRef => ({
  id: "x",
  title: "título del backend",
  url: null,
  evidence_type: "dataset",
  evidence_type_display: "palabra del backend",
  population: "human",
  population_display: "palabra del backend",
  not_applicable: [],
  outside_enum: [],
  ...overrides,
});

describe("matriz de riesgos", () => {
  it("cada eslabón lleva el signo de su campo en la ficha, y no hay dos con el mismo", () => {
    const keys = ["hazard", "effect", "variables", "data", "detection", "countermeasures"];
    const drawings = keys.map((key) => signPictogram(chainSign(key)));
    expect(new Set(drawings).size).toBe(keys.length);
    expect(signPictogram(chainSign("hazard"))).toBe("pentagon");
    expect(signPictogram(chainSign("effect"))).toBe(uiPictogram("body"));
    expect(signPictogram(chainSign("data"))).toBe(uiPictogram("evidence"));
    expect(signPictogram(chainSign("countermeasures"))).toBe(uiPictogram("recommendations"));
    expect(Object.keys(CHAIN_SIGNS)).toEqual(keys);
    expect(chainSign("inventado")).toBe(UNKNOWN_SIGN);
  });

  it("la palabra de cada eslabón es la del backend; sin ella, la clave", () => {
    const links = [{ key: "data", display: "palabra-dato" }];
    expect(linkLabel(links, "data")).toBe("palabra-dato");
    expect(linkLabel(links, "effect")).toBe("effect");
  });

  it("cada paso de la detección tiene signo propio, y uno desconocido el de «desconocido»", () => {
    const keys = ["baseline", "deviation", "persistence", "trend", "points", "levels"];
    const drawings = keys.map((key) => signPictogram(stepSign(key)));
    expect(new Set(drawings).size).toBe(keys.length);
    expect(Object.keys(DETECTION_STEP_SIGNS)).toEqual(keys);
    expect(stepSign("otro")).toBe(UNKNOWN_SIGN);
  });

  it("un conjunto de datos y un artículo llevan la marca de su clase de documento", () => {
    expect(dataMark(ref({ evidence_type: "dataset" }))).toEqual(typeMark("dataset"));
    expect(dataMark(ref({ evidence_type: "journal_article" }))).toEqual(typeMark("journal_article"));
    expect(dataMark(ref({ evidence_type: "dataset" })).pictogram).not.toBe(
      dataMark(ref({ evidence_type: "journal_article" })).pictogram,
    );
    // Sin clase: gris, con la marca de por qué está vacía.
    expect(dataMark(ref({ evidence_type: null })).color).toBe("gray");
  });

  it("un conjunto de datos de ratón lleva la advertencia de alcance", () => {
    expect(dataPopulationMark(ref({ population: "animal" })).color).toBe("yellow");
    expect(dataPopulationMark(ref({ population: "human" })).color).toBeNull();
  });

  it("el respaldo de una contramedida es el dibujo de su tarjeta, sin color", () => {
    expect(countermeasureMark("evidence-backed")).toEqual(mark(basisPictogram("evidence-backed"), null));
    expect(countermeasureMark("demo").pictogram).toBe(basisPictogram("demo"));
    expect(countermeasureMark("demo").color).toBeNull();
  });

  it("un riesgo con claves de MMASH lleva la marca del conjunto; sin ninguna, la de «vacío»", () => {
    const dataset = ref({ evidence_type: "dataset" });
    const validation = (keys: RiskValidation["keys"]): RiskValidation => ({
      dataset_id: "mmash",
      keys,
      indicators: 3,
      statement: "frase del backend",
      validates: keys.length > 0 ? "alcance del backend" : null,
      note: keys.length > 0 ? "nota del backend" : null,
      empty: keys.length > 0 ? null : "frase del backend",
      basis: "base del backend",
    });
    const key = { key: "k", display_es: "K", domain: "d", source: "s", source_display: "S" };
    expect(validationMark(validation([key]), dataset)).toEqual(dataMark(dataset));
    expect(validationMark(validation([]), dataset)).toBe(EMPTY_MARK);
  });

  it("un riesgo con sensibilidad medida lleva la serie que salta, sin color; sin ninguna, la de «vacío»", () => {
    const sensitivity = (keys: RiskSensitivity["keys"]): RiskSensitivity => ({
      keys,
      indicators: 3,
      statement: "frase del backend",
      measures: keys.length > 0 ? "alcance del backend" : null,
      reference: "referencia del backend",
      empty: keys.length > 0 ? null : "frase del backend",
      basis: "base del backend",
    });
    const key: RiskSensitivity["keys"][number] = {
      key: "k",
      display_es: "K",
      injections: [{ label: "deterioro", kind: "step", kind_display: "forma" }],
    };
    expect(sensitivityMark(sensitivity([key]))).toBe(SENSITIVITY_MARK);
    expect(sensitivityMark(sensitivity([]))).toBe(EMPTY_MARK);
    // El dibujo existe, no lleva color con significado y no es ni la jeringa del coste de medir ni
    // la marca de «vacío» ni la de MMASH.
    expect(SENSITIVITY_MARK.pictogram).not.toBeNull();
    expect(() => pictogram(SENSITIVITY_MARK.pictogram ?? "")).not.toThrow();
    expect(SENSITIVITY_MARK.color).toBeNull();
    expect(SENSITIVITY_MARK.pictogram).not.toBe("syringe");
    expect(SENSITIVITY_MARK.pictogram).not.toBe(EMPTY_MARK.pictogram);
    expect(SENSITIVITY_MARK.pictogram).not.toBe(dataMark(ref({ evidence_type: "dataset" })).pictogram);
  });
});
