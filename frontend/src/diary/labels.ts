/**
 * Los rótulos de una escala de autoinforme, tal como los da el backend.
 *
 * Por qué está aparte del panel: el riesgo de una escala es rotularla de memoria. Aquí solo
 * salen los rótulos que el backend entrega con su frase leída —hoy, los nueve de la escala
 * hedónica, en inglés: los extremos de NASA en 2025 y los intermedios de un informe de JSC de
 * 1981— y una escala propia de la misión no gana ninguno. No se traduce, no se completa un
 * punto que el backend no dé y no se ordena por parecido.
 *
 * Las escalas propias llevan otra cosa, y por otra función: las anclas que decidió EMMA
 * (`designAnchors`), con la marca del backend de que son decisión de diseño sin validar.
 */
import type { PictogramName } from "../icons/registry";
import { type InstrumentView, instrumentView } from "../indicators/descriptive";
import type { DiaryIndicator } from "../lib/api";
import { formatNumber } from "../lib/format";
import { type Cited, cited } from "../pvt/published";

export interface Anchor {
  key: string;
  /** El punto de la escala, como cifra. */
  point: string;
  /** El rótulo en el idioma de la fuente, sin traducir. */
  label: string;
  cited: Cited;
}

export interface ScaleLabels {
  /** Idioma de los rótulos (BCP 47), para marcarlo en el HTML. */
  language: string;
  anchors: Anchor[];
  /** Las frases que sostienen los rótulos y las que los acompañan, cada una una sola vez. */
  quotes: Cited[];
  seeAlso: Cited[];
  sources: { key: string; text: string; url: string | null }[];
  notFound: string[];
}

/** Los rótulos leídos de una escala, o `null` si el backend no entrega ninguno. */
export function scaleLabels(indicator: DiaryIndicator): ScaleLabels | null {
  const scale = indicator.scale;
  if (scale === null || scale.labels === null || scale.labels.length === 0) return null;
  // Sin idioma declarado no se sabe en qué idioma están: no se pintan como si fueran de aquí.
  if (typeof scale.labels_language !== "string" || scale.labels_language === "") return null;
  const anchors = scale.labels.map((item) => ({
    key: `${indicator.key}-${item.value}`,
    point: formatNumber(item.value, 0),
    label: item.label,
    cited: cited(item.statement),
  }));
  const seeAlso = (scale.labels_see_also ?? []).map(cited);
  // Dos rótulos pueden salir de la misma frase: se enseña una vez.
  const quotes: Cited[] = [];
  for (const item of [...anchors.map((anchor) => anchor.cited), ...seeAlso]) {
    if (!quotes.some((other) => other.id === item.id)) quotes.push(item);
  }
  return {
    language: scale.labels_language,
    anchors,
    quotes,
    seeAlso,
    sources: (scale.labels_sources ?? []).map((source) => ({
      key: source.ref,
      text: `${source.source} · ${source.extent_text}: ${source.what}`,
      url: source.url,
    })),
    notFound: scale.labels_not_found ?? [],
  };
}

/**
 * Lo leído del instrumento publicado de un indicador descriptivo (desde el 2026-10-16), o `null`.
 *
 * Su fuente no escribe un rótulo junto a cada número, así que no se pinta como rótulos: va con
 * sus frases y, si la fuente da categorías con palabras, cada una tal cual, con la nota del
 * backend de que su número es de EMMA. Una escala con rótulos leídos o propia no lo lleva.
 */
export function diaryInstrument(indicator: DiaryIndicator): InstrumentView | null {
  const scale = indicator.scale;
  if (scale === null || scale.labels_status !== "instrument") return null;
  const measure = scale.instrument;
  if (measure === undefined || measure === null || measure.statements.length === 0) return null;
  return instrumentView(measure, indicator.key);
}

export interface DecidedAnchor {
  key: string;
  point: string;
  label: string;
  /**
   * Un cursor en el extremo de una pista: a la izquierda en el ancla más baja, a la derecha en
   * la más alta. Es la posición en el rango, nada más; un ancla intermedia (hoy no hay) va sin
   * dibujo. Sin caras ni signos: una escala propia no se dibuja como un instrumento.
   */
  pictogram: PictogramName | null;
}

export interface DecidedAnchors {
  /** La marca del backend: de quién es la decisión y que no está validada. */
  mark: string;
  anchors: DecidedAnchor[];
  why: string;
  between: string;
  reference: string;
}

/**
 * Las anclas de una escala propia de la misión, o `null`.
 *
 * Van aparte de los rótulos leídos y nunca se mezclan con ellos: una escala que trae rótulos
 * leídos no enseña anclas decididas. Sin la marca del backend no se pintan: unas anclas sin
 * «de quién y sin validar» se leerían como rótulos de una fuente.
 */
export function designAnchors(indicator: DiaryIndicator): DecidedAnchors | null {
  const scale = indicator.scale;
  if (scale === null || (scale.labels !== null && scale.labels.length > 0)) return null;
  const decided = scale.design_anchors;
  if (decided === undefined || decided === null || decided.status !== "design") return null;
  if (decided.status_display.trim() === "" || decided.anchors.length === 0) return null;
  const values = decided.anchors.map((item) => item.value);
  const lowest = Math.min(...values);
  const highest = Math.max(...values);
  const endPictogram = (value: number): PictogramName | null => {
    // Con una sola ancla no hay extremos que distinguir.
    if (lowest === highest) return null;
    if (value === lowest) return "slider-left";
    if (value === highest) return "slider-right";
    return null;
  };
  return {
    mark: decided.status_display,
    anchors: decided.anchors.map((item) => ({
      key: `${indicator.key}-${item.value}`,
      point: formatNumber(item.value, 0),
      label: item.label,
      pictogram: endPictogram(item.value),
    })),
    why: decided.why,
    between: decided.between,
    reference: decided.reference,
  };
}
