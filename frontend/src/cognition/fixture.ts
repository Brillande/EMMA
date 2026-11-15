/**
 * Un protocolo de la batería Cognition con textos de relleno, para las pruebas: cada texto que
 * la interfaz enseña es reconocible y viene «del backend», así se ve que ninguno se redacta aquí.
 */
import type { CognitionField, CognitionProtocol, InstrumentStatement } from "../lib/api";

export function statement(id: string): InstrumentStatement {
  return {
    id,
    label: `ROTULO-${id}`,
    quote: `QUOTE-${id}`,
    ref: "dev-2024-cognition-iss",
    source: "FUENTE-CITADA",
    title: "TITULO-FUENTE",
    url: "https://example.org/fuente",
    where: "SECCION",
    read_on: "2026-10-31",
    extent: "partial",
    extent_text: "LEIDO-EN-PARTE",
  };
}

export function field(key: string, measure: CognitionField["measure"]): CognitionField {
  const speed = measure === "speed";
  return {
    key,
    measure,
    measure_display: `MEDIDA-${measure}`,
    display: `DISPLAY-${key}`,
    display_es: `NOMBRE-${key}`,
    unit: speed ? "ms" : "1",
    unit_display: speed ? "ms" : "",
    decimals: speed ? 0 : 2,
    physical_min: speed ? 1 : 0,
    physical_max: speed ? 60000 : 1,
    range_text: speed ? "RANGO-MS" : "RANGO-PROPORCION",
    statement: statement(`frase-${key}`),
  };
}

export const protocol: CognitionProtocol = {
  title: "TITULO-DEL-BACKEND",
  identity: "IDENTIDAD-DEL-BACKEND",
  scope: "ALCANCE-DEL-BACKEND",
  limits: ["LIMITE-1", "LIMITE-2"],
  battery: [statement("bateria")],
  tests: [
    {
      order: 1,
      abbrev: "mpt",
      sigla: "MPT",
      name: "Motor Praxis Task",
      measures: statement("cog-test-mpt"),
      measures_note: null,
      recorded_here: true,
      fields: [field("cognition-mpt-speed", "speed")],
      no_accuracy: statement("cog-mpt-no-accuracy"),
      console: null,
      console_note: null,
    },
    {
      order: 2,
      abbrev: "volt",
      sigla: "VOLT",
      name: "Visual Object Learning Task",
      measures: statement("cog-test-volt"),
      measures_note: null,
      recorded_here: true,
      fields: [field("cognition-volt-speed", "speed"), field("cognition-volt-accuracy", "accuracy")],
      no_accuracy: null,
      console: null,
      console_note: null,
    },
    {
      order: 3,
      abbrev: "pvt",
      sigla: "PVT",
      name: "Psychomotor Vigilance",
      measures: null,
      measures_note: "SIN-FRASE-LEIDA",
      recorded_here: false,
      fields: [],
      no_accuracy: null,
      console: "/api/pvt/protocol",
      console_note: "NOTA-DE-LA-PVT",
    },
  ],
  not_found: ["NO-ENCONTRADO-1"],
  provenance: {
    source: "console-cognition",
    source_display: "batería Cognition en la consola",
    observation_type: "measured",
    evidence_context: "ground",
    effective_note: "NOTA-DE-HORA",
  },
  recorded_by: {
    required: true,
    label: "ROTULO-DE-QUIEN-ANOTA",
    note: "NOTA-DE-QUIEN-ANOTA",
    missing_display: "no consta",
  },
  submit_to: "/api/cognition/console",
};
