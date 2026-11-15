/**
 * Como se presenta cada nivel de riesgo del backend (`app/analysis/risk.py`).
 *
 * El color sale de la tabla F.5-1 de NASA-STD-3001 Vol 2, y nunca va solo: F.5.10 e
 * exige *"an additional cue"* cuando el color transmite informacion critica. Cada
 * nivel lleva ademas su palabra y un pictograma de forma distinta (`icons/sets/shapes.ts`),
 * para que se lea en una pantalla sin color, con daltonismo o bajo luz roja de cabina.
 *
 * LA PALABRA NO SE ESCRIBE AQUI. Esta tabla la tenia, y el backend tenia la suya: el
 * mismo nivel se llamaba de una forma en la insignia y de otra en el resumen. Ahora la
 * palabra llega en cada estado (`level_labels` de `/api/status`) y aqui solo queda lo
 * que es de la interfaz: color, pictograma, clase de alerta y parpadeo. Mientras no ha
 * llegado ningun estado, un nivel se nombra con su clave de la API: nunca se inventa
 * una palabra ni se deja el pictograma solo.
 */

import type { PictogramName } from "../icons/registry";
import type { Token } from "./palette";

export type Level = "nominal" | "watch" | "concern" | "critical";

export interface LevelStyle {
  /** Como se nombra ante la tripulacion: la palabra del backend, o la clave si aun no llego. */
  readonly label: string;
  /** Token de la paleta; `text` = sin color de alerta. */
  color: Token;
  /** Forma distinta por nivel: la senal que no depende del color. */
  pictogram: PictogramName;
  /** Clase de alerta del Apendice F (F.6.4): W, C, A, o ninguna. */
  alertClass: "W" | "C" | "A" | null;
  /** Solo lo critico parpadea: desviacion declarada, §2.2 del estado del arte. */
  flashes: boolean;
}

/** Clave de la API -> palabra, tal cual la dio el ultimo estado del backend. */
const labels = new Map<string, string>();

/**
 * Adopta las palabras de nivel de un estado. Sustituye a las anteriores: la interfaz no
 * conserva una palabra que el backend ya no da.
 */
export function adoptLevelLabels(given: Record<string, string> | null | undefined): void {
  labels.clear();
  for (const [key, word] of Object.entries(given ?? {})) {
    if (typeof word === "string" && word.trim() !== "") labels.set(key, word);
  }
}

function style(level: Level, look: Omit<LevelStyle, "label">): LevelStyle {
  return {
    ...look,
    get label() {
      return labels.get(level) ?? level;
    },
  };
}

export const LEVELS: Record<Level, LevelStyle> = {
  nominal: style("nominal", { color: "text", pictogram: "shape-circle", alertClass: null, flashes: false }),
  watch: style("watch", { color: "blue", pictogram: "shape-diamond", alertClass: "A", flashes: false }),
  concern: style("concern", { color: "yellow", pictogram: "shape-triangle", alertClass: "C", flashes: false }),
  critical: style("critical", { color: "red", pictogram: "shape-square", alertClass: "W", flashes: true }),
};

/** De menos a mas grave: para ordenar y contar. */
export const LEVEL_ORDER: readonly Level[] = ["nominal", "watch", "concern", "critical"];

export function isLevel(value: string): value is Level {
  return (LEVEL_ORDER as readonly string[]).includes(value);
}

export function levelStyle(value: string): LevelStyle {
  if (!isLevel(value)) {
    // Un nivel que la interfaz no conoce no se pinta como nominal: se dice.
    throw new RangeError(`nivel de riesgo desconocido: ${value}`);
  }
  return LEVELS[value];
}

/** Nombres de dominio ante la tripulacion; la clave es la de la API. */
export const DOMAIN_LABELS: Record<string, string> = {
  cardiovascular: "Cardiovascular",
  behavioral: "Conductual",
  radiation: "Radiación",
  bone: "Óseo",
  immune: "Inmune",
  "neuro-ocular": "Neuro-ocular",
  genitourinary: "Genitourinario",
  musculoskeletal: "Musculoesquelético",
  nutrition: "Nutrición",
};

export function domainLabel(key: string): string {
  return DOMAIN_LABELS[key] ?? key;
}
