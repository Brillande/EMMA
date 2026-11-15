/**
 * Lo publicado sobre la prueba, ordenado para pintarlo junto a lo que hace EMMA.
 *
 * Por qué está aparte del panel: la prueba de 10 minutos y su versión breve dan valores
 * distintos para lo mismo, y lo que no puede pasar es que la pantalla los junte, enseñe un
 * valor sin su frase o deje de decir cuál de los dos es el de EMMA. Eso se comprueba aquí,
 * sin navegador.
 *
 * Aquí no se redacta nada ni se decide nada: qué versión, qué valor, si coincide con el de
 * EMMA y en qué difiere lo dice el backend (`GET /api/pvt/protocol`). Las frases de la fuente
 * van en su idioma, tal cual.
 */
import type { PvtParameter, PvtProtocol, InstrumentStatement } from "../lib/api";
import { formatSourceDate } from "../lib/format";
import type { StateMark } from "../lib/marks";
import { comparisonMark } from "./marks";

/** Una frase leída, lista para pintar: la cita y de dónde sale. */
export interface Cited {
  id: string;
  label: string;
  quote: string;
  /** Sección · cita de la fuente · cuánto se leyó · fecha de lectura. */
  origin: string;
  url: string | null;
}

export function cited(statement: InstrumentStatement): Cited {
  return {
    id: statement.id,
    label: statement.label,
    quote: statement.quote,
    origin: [
      statement.where,
      statement.source,
      statement.extent_text,
      `leído el ${formatSourceDate(statement.read_on)}`,
    ].join(" · "),
    url: statement.url,
  };
}

export interface PublishedValueRow {
  key: string;
  /** De qué versión publicada de la prueba es el valor. Nunca se pinta un valor sin ella. */
  variant: string;
  literal: string;
  /** Si el valor de EMMA es ese mismo (cifra y operador): lo dice el backend. */
  same: boolean;
  /**
   * La marca que se pinta junto al valor, con glifo y palabra, tal cual la da el backend
   * («= es el valor de EMMA», «≠ misma cifra, distinto operador…»). `null`: sin marca.
   */
  marker: string | null;
  cited: Cited;
}

export interface PublishedRow {
  key: string;
  display: string;
  emmaValue: string;
  /** El parámetro entra en la puntuación de una prueba. */
  scores: boolean;
  status: string;
  /** La forma que acompaña a `status` (`marks.ts`): igual, distinto, misma cifra, no comparable… */
  statusMark: StateMark;
  /** Falso si EMMA y la fuente no miden lo mismo (estímulos frente a minutos): sin «=» ni «≠». */
  comparable: boolean;
  values: PublishedValueRow[];
  seeAlso: Cited[];
  difference: string;
}

/** Los parámetros que traen comparación con lo publicado, en el orden del backend. */
export function publishedRows(parameters: readonly PvtParameter[]): PublishedRow[] {
  const rows: PublishedRow[] = [];
  for (const item of parameters) {
    const published = item.published;
    if (published === undefined) continue;
    rows.push({
      key: item.key,
      display: item.display,
      emmaValue: item.value_text,
      scores: item.scores === true,
      status: published.status_display,
      statusMark: comparisonMark(published.status),
      comparable: published.status !== "not_comparable",
      values: published.values.map((value) => ({
        key: `${item.key}-${value.variant}`,
        variant: value.variant_display,
        literal: value.literal,
        same: value.same,
        // Sin marca del backend no hay marca: la interfaz no la redacta por su cuenta.
        marker: value.marker_display ?? null,
        cited: cited(value.statement),
      })),
      seeAlso: published.see_also.map(cited),
      difference: published.difference,
    });
  }
  return rows;
}

export interface PublishedContext {
  note: string;
  outcomesNote: string;
  context: Cited[];
  sources: { key: string; text: string; url: string | null }[];
  notFound: string[];
}

/** Lo leído que no es de un solo parámetro. `null` si el backend no lo da. */
export function publishedContext(protocol: PvtProtocol): PublishedContext | null {
  const published = protocol.published;
  if (published === undefined) return null;
  return {
    note: published.note,
    outcomesNote: published.outcomes_note,
    context: published.context.map(cited),
    sources: published.sources.map((source) => ({
      key: source.ref,
      text: `${source.source} · ${source.extent_text}: ${source.what}`,
      url: source.url,
    })),
    notFound: published.not_found,
  };
}
