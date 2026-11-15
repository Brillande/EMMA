/**
 * La entidad Riesgo (especificación §3), ordenada para leerla.
 *
 * Por qué existe aparte del panel: lo que aquí se puede equivocar es lógica. El esquema de
 * niveles es una leyenda —desde qué puntuación empieza cada nivel—, no el estado de nadie: si
 * se pintara con el color de alarma de su nivel, un inventario parecería una alerta. Y una
 * ficha con campos sin verificar, pintada como las demás, pasaría por evidencia completa.
 *
 * Nada de aquí redacta: el nombre de cada nivel, la frase de la incertidumbre, el grado de cada
 * ficha y con qué se evalúa el dominio son los de `GET /api/risks`. Aquí solo se elige la marca
 * (el pictograma del nivel, `icons/sets/shapes.ts`; las demás, `lib/marks.ts`), se calcula hasta
 * dónde llega cada tramo y se cuenta.
 */

import { basisPictogram } from "../advisor/recommendation";
import { emptyReason, populationMark, typeMark } from "../evidence/sourceMarks";
import type { PictogramName } from "../icons/registry";
import type {
  AnatomyRegion,
  EvidenceItem,
  RiskEntity,
  RiskMatrixRef,
  RiskSensitivity,
  RiskSeveritySchema,
  RiskValidation,
} from "../lib/api";
import { LEVELS, isLevel } from "../lib/levels";
import {
  type StateMark,
  EMPTY_MARK,
  MISSING_MARK,
  UNKNOWN_MARK,
  UNKNOWN_PICTOGRAM,
  mark,
} from "../lib/marks";
import type { Sign } from "../lib/uiMarks";

export interface LevelRow {
  level: string;
  /** La palabra del backend para el nivel. */
  label: string;
  /** El pictograma del nivel, sin su color: es una leyenda, no un estado. */
  pictogram: PictogramName;
  /** Puntuación desde la que empieza; `null` en el nivel que no tiene umbral. */
  from: number | null;
  /** Puntuación en la que empieza el siguiente; `null` en el último. */
  below: number | null;
}

/** Un nivel que la interfaz no conoce se enseña con su palabra y sin suponerle forma. */
export const UNKNOWN_LEVEL_PICTOGRAM: PictogramName = "question";

/** Los tramos del esquema, en el orden del backend: cada uno acaba donde empieza el siguiente. */
export function levelRows(schema: RiskSeveritySchema): LevelRow[] {
  return schema.levels.map((item, index) => ({
    level: item.level,
    label: item.label,
    pictogram: isLevel(item.level) ? LEVELS[item.level].pictogram : UNKNOWN_LEVEL_PICTOGRAM,
    from: item.min_score,
    below: schema.levels[index + 1]?.min_score ?? null,
  }));
}

/** Ficha con todo lo que pide §3 verificado: un cuadrado pequeño, texto normal. */
export const VERIFIED_STYLE: StateMark = mark("square-small", null);
/** Ficha con campos sin verificar: dato ausente, anillo punteado en cian (F.5-1). */
export const UNVERIFIED_STYLE: StateMark = MISSING_MARK;

export function referenceStyle(reference: { unverified: string[] }): StateMark {
  return reference.unverified.length > 0 ? UNVERIFIED_STYLE : VERIFIED_STYLE;
}

/**
 * Con qué se evalúa un dominio: medido y calculado llevan las formas de «medido» e «inferido»
 * (`lib/provenance.ts`), que es lo que son. Sin indicadores no hay con qué evaluar: gris de «no
 * disponible».
 */
const EVALUATION_MARKS: Record<string, StateMark> = {
  measured: mark("dot-filled", null),
  "calculated-only": mark("dot-half", null),
  none: mark("slash-circle", "gray"),
};

/** Una clase que la interfaz no conoce se enseña con su frase y la marca única de «desconocido». */
export const UNKNOWN_EVALUATION: StateMark = UNKNOWN_MARK;

export function evaluationStyle(kind: string): StateMark {
  return EVALUATION_MARKS[kind] ?? UNKNOWN_EVALUATION;
}

/**
 * La incertidumbre nunca se enseña como cifra propia: si una respuesta dijera que está
 * cuantificada, este panel no sabe pintarla y lo dice en vez de callarlo.
 */
export function quantifiedUnexpectedly(risks: RiskEntity[]): string[] {
  return risks.filter((item) => item.uncertainty.quantified).map((item) => item.risk_id);
}

// --------------------------------------------------------------------------------------------
// La matriz de riesgos (conversación de ideación): peligro, efecto, variable, dato, detección y
// contramedida, una fila por dominio. Las palabras de cada eslabón, cada frase de la detección y
// cada contramedida son del backend; aquí solo se elige el signo de cada columna y de cada paso.
// --------------------------------------------------------------------------------------------

/**
 * El signo de cada eslabón, el mismo que lleva ese campo en la ficha de un riesgo: el pentágono
 * del RIDGE, la figura del cuerpo para el efecto (es el efecto sobre el sistema humano), la regla
 * de los indicadores, la hoja de la evidencia, el faro de la vigilancia y el poste de las
 * contramedidas. Un eslabón que la interfaz no conoce lleva el dibujo de «desconocido».
 */
export const CHAIN_SIGNS: Readonly<Record<string, Sign>> = {
  hazard: { pictogram: "pentagon" },
  effect: { concept: "body" },
  variables: { concept: "indicator" },
  data: { concept: "evidence" },
  detection: { concept: "monitoring" },
  countermeasures: { concept: "recommendations" },
};

export const UNKNOWN_SIGN: Sign = { pictogram: UNKNOWN_PICTOGRAM };

export function chainSign(key: string): Sign {
  return CHAIN_SIGNS[key] ?? UNKNOWN_SIGN;
}

/** La palabra del backend para un eslabón; si no llega, su clave, que al menos no se inventa. */
export function linkLabel(links: readonly { key: string; display: string }[], key: string): string {
  return links.find((link) => link.key === key)?.display ?? key;
}

/**
 * El signo de cada paso de la regla de detección: los pilares de la línea base, la barra con
 * topes de los límites, el reloj de arena de lo que tiene que durar, la línea de la tendencia, la
 * almohadilla de una cifra y la escalera de los niveles. Los dibujos son los de esos conceptos en
 * el resto de la interfaz (`lib/uiMarks.ts`); ninguno es nuevo.
 */
export const DETECTION_STEP_SIGNS: Readonly<Record<string, Sign>> = {
  baseline: { concept: "baseline" },
  deviation: { concept: "limits" },
  persistence: { concept: "waiting" },
  trend: { concept: "trends" },
  points: { concept: "value" },
  levels: { concept: "ratings" },
};

export function stepSign(key: string): Sign {
  return DETECTION_STEP_SIGNS[key] ?? UNKNOWN_SIGN;
}

/** Una ficha en la columna del dato: la marca de su clase de documento (`sourceMarks.ts`). */
export function dataMark(ref: RiskMatrixRef): StateMark {
  return typeMark(ref.evidence_type, emptyReason(ref, "evidence_type"));
}

/** Sobre quién se midió una ficha: amarillo si no son solo personas (la salvedad de alcance). */
export function dataPopulationMark(ref: RiskMatrixRef): StateMark {
  return populationMark(ref.population, emptyReason(ref, "population"));
}

/** El respaldo de una contramedida: el mismo dibujo que en su tarjeta (`advisor/recommendation.ts`). */
export function countermeasureMark(basis: string): StateMark {
  return mark(basisPictogram(basis), null);
}

/**
 * Qué indicadores de un riesgo salen de MMASH: con alguno, la marca de la clase de documento del
 * conjunto (la cuadrícula del conjunto de datos, la misma de la regla); sin ninguno, la de
 * «vacío». La frase —qué valida y qué no— es del backend.
 */
export function validationMark(validation: RiskValidation, dataset: RiskMatrixRef): StateMark {
  return validation.keys.length > 0 ? dataMark(dataset) : EMPTY_MARK;
}

/**
 * Sensibilidad medida inyectando un deterioro (§5.36.2): la serie que salta (`zigzag-step`), sin
 * color, porque no es un estado de nadie ni una alarma: dice sobre qué indicadores se ha medido. No
 * es la jeringa del coste de medir, que es una extracción.
 */
export const SENSITIVITY_MARK: StateMark = mark("zigzag-step", null);

/**
 * Sobre qué indicadores de un riesgo se ha medido la sensibilidad: con alguno, la serie que salta;
 * sin ninguno, la de «vacío», como la de MMASH. La frase —cuáles, con qué deterioro y dónde están
 * las cifras— es del backend.
 */
export function sensitivityMark(sensitivity: RiskSensitivity): StateMark {
  return sensitivity.keys.length > 0 ? SENSITIVITY_MARK : EMPTY_MARK;
}

/**
 * Las fichas que nombra la frase de una región en «Sistema humano» (§5.37.16): las de `note_refs`
 * (la vejiga y el riesgo de cálculos) y, en una región sin nivel propio, la de su lista de
 * analitos (el hígado «según MedlinePlus», los pulmones «según el NHLBI»). Tal cual llegan del
 * backend y en ese orden; la capa de investigación no es de la frase y no entra.
 */
export function phraseRefs(region: Pick<AnatomyRegion, "note_refs" | "analytes_source">): EvidenceItem[] {
  return region.analytes_source === null ? region.note_refs : [...region.note_refs, region.analytes_source];
}
