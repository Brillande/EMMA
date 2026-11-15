/**
 * Medido / inferido / predicho y entorno del dato (especificacion del equipo §2, §10).
 *
 * "Etiquetar siempre los datos como MEASURED / INFERRED / PREDICTED." La etiqueta no
 * lleva color propio: la tabla F.5-1 ya reparte los colores (alerta, caducado, no
 * disponible), y pintar un dato predicho en cian diria "caducado". Se distingue por
 * palabra y pictograma (`icons/sets/provenance.ts`), como el nivel (F.5.10 e). Las
 * palabras son rotulos de interfaz, no texto clinico: el backend decide el tipo, aqui
 * solo se nombra.
 */

import type { PictogramName } from "../icons/registry";
import { tr } from "./i18n";
import type { Token } from "./palette";

export type ObservationType = "measured" | "inferred" | "predicted";

export type EvidenceContext =
  | "iss"
  | "spaceflight"
  | "analog_bedrest"
  | "analog_isolation"
  | "ground"
  | "simulated";

export interface TypeStyle {
  word: string;
  pictogram: PictogramName;
  /** Para el lector de pantalla y el `title`. */
  meaning: string;
}

export const OBSERVATION_TYPES: Record<ObservationType, TypeStyle> = {
  measured: {
    word: tr("MEDIDO", "MEASURED"),
    pictogram: "dot-filled",
    meaning: tr("lectura directa de sensor, test o autoinforme", "direct reading from a sensor, test or self-report"),
  },
  inferred: {
    word: tr("INFERIDO", "INFERRED"),
    pictogram: "dot-half",
    meaning: tr("calculado por un modelo a partir de otras medidas", "computed by a model from other measurements"),
  },
  predicted: {
    word: tr("PREDICHO", "PREDICTED"),
    pictogram: "play",
    meaning: tr("proyectado hacia el futuro; no es un dato recogido", "projected into the future; not collected data"),
  },
};

export const EVIDENCE_CONTEXTS: Record<EvidenceContext, string> = {
  iss: "ISS",
  spaceflight: tr("vuelo real", "actual spaceflight"),
  analog_bedrest: tr("análogo: reposo en cama", "analog: bed rest"),
  analog_isolation: tr("análogo: aislamiento", "analog: isolation"),
  ground: tr("Tierra", "Earth"),
  simulated: tr("simulado", "simulated"),
};

/**
 * El dibujo de cada entorno (`icons/sets/provenance.ts`), junto a su palabra: estacion con
 * paneles, cohete, cama, puerta cerrada, globo y onda generada. Sin color: el entorno describe.
 */
export const EVIDENCE_CONTEXT_PICTOGRAMS: Record<EvidenceContext, PictogramName> = {
  iss: "station",
  spaceflight: "rocket",
  analog_bedrest: "bed",
  analog_isolation: "door-closed",
  ground: "globe",
  simulated: "wave-zigzag",
};

export const OBSERVATION_TYPE_ORDER: ObservationType[] = ["measured", "inferred", "predicted"];

/** Tipo de un valor desconocido: falla en vez de pintarlo como medida. */
export function typeStyle(type: string): TypeStyle {
  if (!(type in OBSERVATION_TYPES)) throw new Error(`tipo de observación desconocido: ${type}`);
  return OBSERVATION_TYPES[type as ObservationType];
}

export function contextLabel(context: string): string {
  if (!(context in EVIDENCE_CONTEXTS)) throw new Error(`entorno de evidencia desconocido: ${context}`);
  return EVIDENCE_CONTEXTS[context as EvidenceContext];
}

/** El dibujo de un entorno; uno desconocido falla igual que su palabra. */
export function contextPictogram(context: string): PictogramName {
  if (!(context in EVIDENCE_CONTEXT_PICTOGRAMS)) {
    throw new Error(`entorno de evidencia desconocido: ${context}`);
  }
  return EVIDENCE_CONTEXT_PICTOGRAMS[context as EvidenceContext];
}

const TYPE_URL = "https://emma.mission/fhir/observation-type";
const CONTEXT_URL = "https://emma.mission/fhir/evidence-context";

/** Tipo y entorno de un recurso FHIR del backend (extensiones propias). */
export function fhirProvenance(resource: {
  extension?: { url: string; valueCode?: string }[];
}): { type: ObservationType; context: EvidenceContext | null } {
  const find = (url: string) => resource.extension?.find((item) => item.url === url)?.valueCode;
  const type = find(TYPE_URL) ?? "measured";
  typeStyle(type);
  const context = find(CONTEXT_URL) ?? null;
  if (context !== null) contextLabel(context);
  return { type: type as ObservationType, context: context as EvidenceContext | null };
}

/**
 * Confianza de la lectura (especificacion §2 y §10: "mostrar confidence/quality").
 *
 * Va aqui, junto al tipo y al entorno, porque responde a la misma pregunta: que clase
 * de dato es este y cuanto se puede afirmar con el. El estado y su palabra los decide
 * el backend (`data.quality` de `/api/status`); aqui solo se elige la senal.
 *
 * - Baja confianza: amarillo con triangulo. Tabla F.5-1, *"off-nominal [...] attention
 *   required"*: la medida esta fuera de lo nominal y pide mirar el sensor. Es el mismo
 *   signo que ya lleva una pagina de OCR poco fiable. No es cian: la lectura ni falta
 *   ni esta caducada. No es gris: esta disponible.
 * - Declarada y no declarada: solo la palabra, sin color ni pictograma, porque no hay nada
 *   que senalar. "No declarada" tampoco va en cian: el registro no distingue una fuente
 *   que calla de una que declara confianza plena, y el cian afirmaria que falta un dato.
 */
export type QualityState = "low" | "declared" | "undeclared";

export interface QualityStyle {
  /** Forma que acompana al color (F.5.10 e); `null` si el estado no lleva senal. */
  pictogram: PictogramName | null;
  /** Token de la paleta; `null` si el estado no lleva color con significado. */
  color: Token | null;
}

export const QUALITY_STATES: Record<QualityState, QualityStyle> = {
  low: { pictogram: "shape-triangle", color: "yellow" },
  declared: { pictogram: null, color: null },
  undeclared: { pictogram: null, color: null },
};

/** Un estado que la interfaz no conoce falla: no se pinta como dato fiable. */
export function qualityStyle(state: string): QualityStyle {
  if (!(state in QUALITY_STATES)) throw new Error(`estado de calidad desconocido: ${state}`);
  return QUALITY_STATES[state as QualityState];
}

/**
 * Si un indicador pide atencion por la calidad de sus lecturas: su ultima lectura es
 * de baja confianza o lo es alguna de las recientes. Estado y recuento son del backend.
 */
export function hasDoubtfulReadings(item: {
  latest: { state: string };
  recent: { low_confidence: number };
}): boolean {
  return item.latest.state === "low" || item.recent.low_confidence > 0;
}

const CONFIDENCE_URL = "https://emma.mission/fhir/confidence";

/** Confianza de un recurso FHIR del backend; `null` si el recurso no la trae. */
export function fhirConfidence(resource: {
  extension?: { url: string; valueDecimal?: number }[];
}): number | null {
  const value = resource.extension?.find((item) => item.url === CONFIDENCE_URL)?.valueDecimal;
  return value === undefined || !Number.isFinite(value) ? null : value;
}

/**
 * Si una lectura es de baja confianza, con el umbral que da el backend
 * (`data.quality.low_confidence_threshold`): la interfaz no tiene uno propio. Por debajo
 * estricto, como en el motor. Sin confianza no se afirma que sea baja.
 */
export function isLowConfidence(confidence: number | null | undefined, threshold: number): boolean {
  if (confidence === null || confidence === undefined) return false;
  return confidence < threshold;
}
