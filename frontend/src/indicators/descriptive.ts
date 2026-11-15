/**
 * Los indicadores descriptivos, preparados para pintarlos.
 *
 * Por qué existe: el usuario decidió (2026-10-15) que la salud conductual más allá del ánimo,
 * los síntomas visuales y la fuerza y la forma física entren como observaciones, pero sin entrar
 * en el riesgo. El estado no los lee, así que ninguna pantalla los enseñaba; el VO2 pico y la
 * prensión, que no se anotan en el diario, no tenían dónde verse. El backend los sirve juntos
 * (`GET /api/indicators/descriptive`) y aquí se preparan para el panel. Lo que no puede pasar se
 * comprueba sin navegador:
 *
 * - No son alertas ni niveles: sin color ni pictograma de nivel. El nombre lleva el dibujo de su
 *   familia del catálogo (ojo con su nervio, cara, mancuerna) y el dominio el suyo: nombrar no
 *   es avisar. La lateralidad de la prensión va en `display_es`, no en el dibujo.
 * - Cada uno con su código y por qué es ese (la ficha LOINC leída o lo que se buscó antes del
 *   código propio), tal como lo escribe el backend.
 * - Las frases de la fuente van en su idioma, tal cual; las categorías del cuestionario de
 *   visión, también, con la nota de que su número es de EMMA. Nada se traduce ni se completa.
 * - Las cifras pasan por `lib/format.ts`; el valor de cada lectura lo escribe el backend.
 * - Lo que falta lleva su marca de la tabla F.5-1, que no es de nivel: un indicador sin lecturas,
 *   la de dato ausente; una lectura sin quién la anotó, la de «no disponible», la misma que en el
 *   diario (`recordedByMark`, `lib/marks.ts`).
 */
import type { DescriptiveIndicator, DescriptiveIndicators, DescriptiveMeasure } from "../lib/api";
import { formatNumber, formatUtc } from "../lib/format";
import { type StateMark, recordedByMark } from "../lib/marks";
import { type Cited, cited } from "../pvt/published";

export interface InstrumentView {
  name: string;
  /** Idioma de las frases y las categorías (BCP 47), para marcarlo en el HTML. */
  language: string;
  scope: string;
  quotes: Cited[];
  /** Cada categoría como la escribe la fuente, con el número que le da EMMA. */
  categories: { key: string; point: string; literal: string }[];
  numbering: string | null;
  sources: { key: string; text: string; url: string | null }[];
  notFound: string[];
}

export function instrumentView(measure: DescriptiveMeasure, key: string): InstrumentView {
  return {
    name: measure.instrument,
    language: measure.language,
    scope: measure.scope,
    quotes: measure.statements.map(cited),
    categories: measure.categories.map((item) => ({
      key: `${key}-${item.value}`,
      point: formatNumber(item.value, 0),
      literal: item.literal,
    })),
    numbering: measure.numbering,
    sources: measure.sources.map((source) => ({
      key: source.ref,
      text: `${source.source} · ${source.extent_text}: ${source.what}`,
      url: source.url,
    })),
    notFound: measure.not_found,
  };
}

export interface DescriptiveRow {
  key: string;
  when: string;
  value: string;
  source: string;
  recordedBy: string;
  /** La marca de quien anotó, la del diario: ninguna si consta; «no disponible» si no. */
  recordedByMark: StateMark;
  observationType: string;
  evidenceContext: string;
}

export interface DescriptiveCard {
  key: string;
  title: string;
  /** La clave del dominio, para su dibujo; `domain` es la palabra del backend que va al lado. */
  domainKey: string;
  domain: string;
  /** «LOINC 94122-9» o «código propio de EMMA · vision-change». */
  code: string;
  codeBasis: string;
  /** Lo que se buscó en LOINC antes de un código propio; `null` si el código es LOINC. */
  searched: string | null;
  /** La consulta exacta de la ficha LOINC leída; `null` si el código es propio. */
  loincUrl: string | null;
  range: string;
  equipment: string | null;
  how: string;
  instrument: InstrumentView | null;
  /** «Sin lecturas» o «N lecturas», con la cifra formateada. */
  count: string;
  /** Sin ninguna lectura en el registro: el recuento va con la marca de dato ausente. */
  empty: boolean;
  /** «Las N últimas de M» si la lista no las trae todas; si no, `null`. */
  shown: string | null;
  rows: DescriptiveRow[];
}

function card(item: DescriptiveIndicator): DescriptiveCard {
  return {
    key: item.key,
    title: item.display_es,
    domainKey: item.domain,
    domain: item.domain_display,
    code:
      item.code_basis.kind === "loinc"
        ? `${item.system_display} ${item.code}`
        : `${item.system_display} · ${item.code}`,
    codeBasis: item.code_basis.text,
    searched: item.code_basis.searched,
    loincUrl: item.code_basis.loinc?.url ?? null,
    range: item.range_text,
    equipment: item.equipment,
    how: item.how_recorded.text,
    instrument: item.instrument === null ? null : instrumentView(item.instrument, item.key),
    count:
      item.count === 0
        ? "Sin lecturas"
        : `${formatNumber(item.count)} ${item.count === 1 ? "lectura" : "lecturas"}`,
    empty: item.count === 0,
    shown:
      item.shown < item.count
        ? `Las ${formatNumber(item.shown)} últimas de ${formatNumber(item.count)}.`
        : null,
    rows: item.readings.map((reading) => ({
      key: `${reading.effective}|${reading.source}|${reading.value}`,
      when: formatUtc(new Date(reading.effective)),
      value: reading.value_text,
      source: reading.source_display,
      recordedBy: reading.recorded_by_display,
      recordedByMark: recordedByMark(reading.recorded_by),
      observationType: reading.observation_type,
      evidenceContext: reading.evidence_context,
    })),
  };
}

export interface DescriptiveView {
  statement: string;
  /** Ningún indicador con lecturas: el recuento general va con la marca de dato ausente. */
  empty: boolean;
  scope: string;
  cards: DescriptiveCard[];
}

export function descriptiveView(data: DescriptiveIndicators): DescriptiveView {
  return {
    statement: data.statement,
    empty: data.indicators.every((item) => item.count === 0),
    scope: data.scope,
    cards: data.indicators.map(card),
  };
}
