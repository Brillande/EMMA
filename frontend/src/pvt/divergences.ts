/**
 * Las divergencias de la prueba con la fuente leída, ordenadas para pintarlas bajo el protocolo.
 *
 * Por qué existe: desde el 2026-10-14 el backend declara en `GET /api/pvt/protocol` cuatro cosas
 * en que EMMA cuenta distinto de lo publicado (cómo se cuenta un lapso en el umbral, de qué
 * versión es el umbral, qué pasa con un estímulo sin respuesta, el mínimo de estímulos), pero la
 * consola no las enseñaba: quien hacía la prueba no veía que su cuenta de lapsos no es la de la
 * fuente. Aquí se preparan para el panel, y lo que no puede pasar se comprueba sin navegador:
 *
 * - Una divergencia no es una alerta. «Difiere» y «coincide» van sin color, con pictograma y la
 *   palabra del backend; «sin valor publicado» va en gris, que en la tabla F.5-1 es «no
 *   disponible». Nunca rojo ni amarillo: declarar no es avisar de un fallo.
 * - Un estado que esta versión no conoce no se disfraza de otro: sin color y con su palabra.
 * - Cada frase va con su ubicación, su cita, cuánto se leyó y cuándo (`cited`), y lo que se
 *   buscó y no se encontró se dice; sin frase no se inventa una.
 * - Lo que no se cambió se dice una vez si es lo mismo para todas, no cuatro veces.
 * - Aquí no se redacta ni se calcula nada: qué hace EMMA, qué dice la fuente, si difieren y qué
 *   consecuencia tiene lo da el backend, tal cual.
 */
import type { PvtDivergence, PvtProtocol } from "../lib/api";
import { formatNumber } from "../lib/format";
import { type StateMark, UNKNOWN_MARK } from "../lib/marks";
import { comparisonMark } from "./marks";
import { type Cited, cited } from "./published";

/**
 * Las formas de «≠», «=» y «⊘» de antes de pasar a pictogramas, con el mismo dibujo (§5.32): las
 * mismas que «Lo publicado» da a valor distinto, mismo valor y sin valor publicado (`marks.ts`),
 * para que un cambio allí no deje a las divergencias con otra forma para lo mismo.
 */
const MARKS: Readonly<Record<string, StateMark>> = {
  differs: comparisonMark("different_value"),
  matches: comparisonMark("same_value"),
  not_published: comparisonMark("not_published"),
};

/** La marca de un estado. Uno desconocido no lleva significado: lo dice la palabra del backend. */
export function divergenceMark(status: string): StateMark {
  return Object.hasOwn(MARKS, status) ? MARKS[status]! : UNKNOWN_MARK;
}

export interface DivergenceRow {
  key: string;
  display: string;
  emma: string;
  published: string;
  statusDisplay: string;
  mark: StateMark;
  consequence: string;
  scores: boolean;
  /** Lo que no se cambió, si no se dice ya una vez para todas (`DivergencesView.kept`). */
  kept: string | null;
  sources: Cited[];
  notFound: string[];
}

export interface DivergencesView {
  note: string;
  /** Cuántas declara el backend, ya con el formato de `lib/format.ts`. */
  count: string;
  /** Lo que no se cambió, una vez, cuando es el mismo texto para todas; si no, `null`. */
  kept: string | null;
  rows: DivergenceRow[];
}

/** Las divergencias que declara el backend, en su orden. `null` si no da ninguna. */
export function divergencesView(protocol: PvtProtocol): DivergencesView | null {
  const declared = protocol.divergences;
  if (declared === undefined || declared.items.length === 0) return null;
  const items: readonly PvtDivergence[] = declared.items;
  const keptTexts = new Set(items.map((item) => item.kept));
  const shared = keptTexts.size === 1 ? items[0]!.kept : null;
  return {
    note: declared.note,
    count: formatNumber(items.length),
    kept: shared,
    rows: items.map((item) => ({
      key: item.key,
      display: item.display,
      emma: item.emma,
      published: item.published,
      statusDisplay: item.status_display,
      mark: divergenceMark(item.status),
      consequence: item.consequence,
      scores: item.scores === true,
      kept: shared === null ? item.kept : null,
      sources: item.sources.map(cited),
      notFound: item.not_found,
    })),
  };
}
