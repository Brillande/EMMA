import { describe, expect, it } from "vitest";

import {
  EVIDENCE_CONTEXTS,
  OBSERVATION_TYPES,
  OBSERVATION_TYPE_ORDER,
  QUALITY_STATES,
  contextLabel,
  fhirConfidence,
  fhirProvenance,
  hasDoubtfulReadings,
  isLowConfidence,
  qualityStyle,
  typeStyle,
} from "./provenance";

describe("especificacion §2 y §10: la confianza del dato se ve", () => {
  it("la baja confianza no depende solo del color: lleva pictograma (F.5.10 e)", () => {
    const low = qualityStyle("low");
    expect(low.color).toBe("yellow");
    expect(low.pictogram).toBeTruthy();
    // Ni el pictograma de un tipo de dato: un triangulo no puede leerse como "predicho".
    const typePictograms = OBSERVATION_TYPE_ORDER.map((type) => OBSERVATION_TYPES[type].pictogram);
    expect(typePictograms).not.toContain(low.pictogram);
  });

  it("solo la baja confianza lleva senal: ni cian ni gris para lo no declarado", () => {
    for (const state of ["declared", "undeclared"] as const) {
      expect(QUALITY_STATES[state]).toEqual({ pictogram: null, color: null });
    }
  });

  it("un estado desconocido falla en vez de pasar por fiable", () => {
    expect(() => qualityStyle("excellent")).toThrow();
  });

  it("baja confianza es estar por debajo del umbral del backend, no en el", () => {
    expect(isLowConfidence(0.3, 0.5)).toBe(true);
    expect(isLowConfidence(0.5, 0.5)).toBe(false);
    expect(isLowConfidence(1, 0.5)).toBe(false);
  });

  it("sin confianza no se afirma que sea baja", () => {
    expect(isLowConfidence(null, 0.5)).toBe(false);
    expect(isLowConfidence(undefined, 0.5)).toBe(false);
  });

  it("lee la confianza de la extension FHIR", () => {
    const url = "https://emma.mission/fhir/confidence";
    expect(fhirConfidence({ extension: [{ url, valueDecimal: 0.3 }] })).toBe(0.3);
    expect(fhirConfidence({})).toBeNull();
    expect(fhirConfidence({ extension: [{ url }] })).toBeNull();
  });

  it("un indicador pide atencion si su ultima lectura o alguna reciente es dudosa", () => {
    const item = (state: string, low: number) => ({
      latest: { state },
      recent: { low_confidence: low },
    });
    expect(hasDoubtfulReadings(item("low", 0))).toBe(true);
    expect(hasDoubtfulReadings(item("undeclared", 2))).toBe(true);
    expect(hasDoubtfulReadings(item("undeclared", 0))).toBe(false);
    expect(hasDoubtfulReadings(item("declared", 0))).toBe(false);
  });
});

describe("especificacion §2: medido, inferido y predicho se distinguen sin color", () => {
  it("cada tipo tiene una palabra y un pictograma propios", () => {
    const words = OBSERVATION_TYPE_ORDER.map((type) => OBSERVATION_TYPES[type].word);
    const pictograms = OBSERVATION_TYPE_ORDER.map((type) => OBSERVATION_TYPES[type].pictogram);
    expect(new Set(words).size).toBe(3);
    expect(new Set(pictograms).size).toBe(3);
  });

  it("un tipo desconocido falla en vez de pasar por medida", () => {
    expect(() => typeStyle("guessed")).toThrow();
    expect(() => contextLabel("mars")).toThrow();
  });

  it("todo entorno del backend tiene nombre", () => {
    for (const context of [
      "iss", "spaceflight", "analog_bedrest", "analog_isolation", "ground", "simulated",
    ]) {
      expect(EVIDENCE_CONTEXTS[context as keyof typeof EVIDENCE_CONTEXTS]).toBeTruthy();
    }
  });
});

describe("extensiones FHIR del backend", () => {
  it("lee tipo y entorno", () => {
    const parsed = fhirProvenance({
      extension: [
        { url: "https://emma.mission/fhir/observation-type", valueCode: "inferred" },
        { url: "https://emma.mission/fhir/evidence-context", valueCode: "iss" },
      ],
    });
    expect(parsed).toEqual({ type: "inferred", context: "iss" });
  });

  it("un recurso sin extensiones es una medida de entorno no declarado", () => {
    expect(fhirProvenance({})).toEqual({ type: "measured", context: null });
  });
});
