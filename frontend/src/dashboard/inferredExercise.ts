/**
 * Como se presenta el ejercicio MEDIDO que acompaña a la banda osea inferida
 * (`app/analysis/exercise_summary.py`), y con que dibujo va la banda.
 *
 * Existe para que el panel no decida nada: las frases las da el backend, y aqui solo se fija con
 * que señal se pinta lo que falta y de que entorno son las lecturas. La tabla F.5-1 de
 * NASA-STD-3001 Vol 2 reserva el cian para "Missing or stale data": un indicador sin lecturas en
 * la semana, o una semana sin registro, es eso, y lleva su pictograma ademas del color (F.5.10 e).
 * "Hay registro y es 0" SI es un dato: no va en cian. Un indicador con lecturas lleva el dibujo
 * de su familia (`lib/indicatorFamily.ts`: la mancuerna del ejercicio), sin color; cuando falta,
 * la señal de ausencia ocupa su sitio, porque es lo que hay que ver.
 */

import type { PictogramName } from "../icons/registry";
import type { ExerciseIndicator, ExerciseMeasured, ExerciseRecordState } from "../lib/api";
import { hasIndicatorFamily, indicatorFamily } from "../lib/indicatorFamily";
import { type StateMark, MISSING_MARK, UNKNOWN_MARK, mark } from "../lib/marks";
import { contextLabel } from "../lib/provenance";
import { type PictogramTable, pictogramFor } from "./pictogramTable";

const PRESENT: StateMark = mark(null, null);

const RECORD_STYLES: Record<ExerciseRecordState, StateMark> = {
  recorded: PRESENT,
  recorded_zero: PRESENT,
  no_record: MISSING_MARK,
};

/** Un estado que la interfaz no conoce no se pinta como "hay registro": se dice. */
export function recordStyle(state: string): StateMark {
  if (!(state in RECORD_STYLES)) throw new RangeError(`estado de registro desconocido: ${state}`);
  return RECORD_STYLES[state as ExerciseRecordState];
}

/**
 * Con lecturas, el dibujo de la familia del indicador (la misma regla que `IndicatorName`: una
 * clave sin familia lleva el de «desconocido»); sin ellas, la señal de dato ausente.
 */
export function indicatorStyle(indicator: Pick<ExerciseIndicator, "key" | "readings">): StateMark {
  if (indicator.readings <= 0) return MISSING_MARK;
  const family = hasIndicatorFamily(indicator.key) ? indicatorFamily(indicator.key) : UNKNOWN_MARK.pictogram;
  return mark(family, null);
}

/**
 * El dibujo de cada estado inferido, junto a su nombre: la banda de densidad mineral osea lleva
 * el hueso del dominio. Uno que la interfaz no conoce va con su nombre y el de «desconocido».
 */
const BAND_PICTOGRAMS: PictogramTable = {
  "bone-mineral-density-loss": "domain-bone",
};

export function bandPictogram(key: string): PictogramName | null {
  return pictogramFor(BAND_PICTOGRAMS, key);
}

/**
 * El entorno de las lecturas, para el rotulo MEDIDO: uno solo si todas son del mismo; `null` si
 * no hay lecturas o vienen de varios (entonces no se afirma ninguno en el rotulo).
 */
export function singleContext(exercise: Pick<ExerciseMeasured, "indicators">): string | null {
  const contexts = new Set(
    exercise.indicators.flatMap((item) =>
      Object.entries(item.evidence_context)
        .filter(([, count]) => count > 0)
        .map(([context]) => context),
    ),
  );
  const [only] = [...contexts];
  if (contexts.size !== 1 || only === undefined) return null;
  contextLabel(only);
  return only;
}

/** Las frases de un indicador que el backend da ademas de la principal, en su orden. */
export function indicatorNotes(indicator: ExerciseIndicator): string[] {
  return [indicator.baseline?.statement, indicator.trend_statement].filter(
    (text): text is string => typeof text === "string" && text !== "",
  );
}
