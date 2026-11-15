import type { PictogramName } from "../icons/registry";
import type { GuideStep, MeasurementGuide } from "../lib/api";
import { formatDay, formatNumber } from "../lib/format";
import { hasIndicatorFamily, indicatorFamily } from "../lib/indicatorFamily";
import { tr } from "../lib/i18n";

/**
 * Lo que el panel de guías calcula a partir de lo que llega, sin escribir nada clínico: los
 * rótulos de estructura («En vuelo», «Buscado y no encontrado») y la cuenta de pasos. Los pasos,
 * las definiciones y su origen son del backend (`backend/app/guides.py`) y se enseñan tal cual.
 */

/** Rótulos de estructura del panel: dicen qué hay debajo, no lo resumen. */
export const GUIDES_LABELS = {
  panel: tr("Cómo medir y glosario", "How to measure and glossary"),
  inFlight: tr("En vuelo", "In flight"),
  notFound: tr("Buscado y no encontrado", "Searched and not found"),
  sources: tr("Fuente de este paso", "Source of this step"),
  glossary: tr("Glosario", "Glossary"),
  indicators: tr("Indicadores", "Indicators"),
} as const;

/** El rótulo plegado de una guía: su título y cuántos pasos tiene, con la cifra formateada. */
export function guideSummary(guide: MeasurementGuide): string {
  return `${guide.title} · ${guideStepsWord(guide)}`;
}

/** Cuántos pasos con fuente tiene una guía, con la cifra formateada; o que no tiene ninguno. */
export function guideStepsWord(guide: MeasurementGuide): string {
  const steps = guide.steps.length;
  if (steps === 0) return tr("sin pasos con fuente", "no sourced steps");
  return `${formatNumber(steps)} ${steps === 1 ? tr("paso", "step") : tr("pasos", "steps")}`;
}

/**
 * El dibujo de una guía en el tablero: el de la familia de su primer indicador que tenga familia
 * (`lib/indicatorFamily.ts`, el mismo que acompaña su nombre en toda la consola). Sin ninguno, null:
 * el panel pone el de «medir» y no supone otro.
 */
export function guidePictogram(guide: MeasurementGuide): PictogramName | null {
  const known = guide.indicators.find((item) => hasIndicatorFamily(item.key));
  return known === undefined ? null : indicatorFamily(known.key);
}

/** Los indicadores de una guía en una línea: el nombre en español y, si se sabe, su equipo. */
export function indicatorsLine(guide: MeasurementGuide): string {
  return guide.indicators
    .map((item) => (item.equipment === null ? item.display_es : `${item.display_es} (${item.equipment})`))
    .join(" · ");
}

/** Dónde y cuándo se leyó la frase que sostiene un paso; el día, validado por `format.ts`. */
export function basisCaption(basis: GuideStep["basis"][number]): string {
  return `${basis.citation.source}, ${basis.where} · ${tr("leído el", "read on")} ${formatDay(basis.read_on)}`;
}
