/**
 * Las fuentes del contexto del equipo, con la marca y el orden de cada una.
 *
 * Por qué existe aparte del panel: lo que aquí se puede equivocar es lógica, no pintura. Una fuente
 * no leída pintada como leída diría que se contrastó lo que nadie abrió, y es justo lo que
 * `app/evidence/context_sources.py` evita; pintada en rojo o en amarillo, sería una alarma, y no lo
 * es: es un dato que falta (cian, tabla F.5-1). Está en un `.ts` para que lo pruebe
 * `contextSources.test.ts`.
 *
 * Nada de aquí redacta: el estado (`status_text`), el motivo y el uso son de
 * `GET /api/context-sources`. Aquí solo se elige la marca y el orden. Es un inventario: nada de esto
 * decide sobre la tripulación.
 */

import type { ContextSource, ContextSourceList } from "../lib/api";
import { type StateMark, MISSING_MARK, UNAVAILABLE_MARK, mark } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";

/**
 * Las claves de `STATUSES` del backend. Leída: el libro abierto de lo leído,
 * sin color. En parte: la mitad rellena, sin color, como un eslabón de EPM y Biolab leído con un
 * hueco. No leída: el cian del dato ausente con su anillo, sin color de alerta.
 */
export const STATUS_MARKS: Readonly<Record<string, StateMark>> = {
  not_read: MISSING_MARK,
  partial: mark("circle-half-right", null),
  read: mark(uiPictogram("sourceText"), null),
};

/** De menos a más leído. */
const STATUS_ORDER: readonly string[] = ["not_read", "partial", "read"];

/** Un estado que la interfaz no conoce: gris, «no disponible», y la palabra del backend al lado. */
export function statusMark(status: string): StateMark {
  // `Object.hasOwn`, no `in`: «constructor» no es un estado aunque el objeto lo herede.
  return Object.hasOwn(STATUS_MARKS, status) ? STATUS_MARKS[status]! : UNAVAILABLE_MARK;
}

/** Lo que menos se leyó, primero; lo que no se sabe qué es, antes que nada: no se esconde al final. */
function rank(status: string): number {
  return STATUS_ORDER.indexOf(status);
}

/** Las fuentes por estado; dentro de cada estado, en el orden del backend. No toca la lista. */
export function sortedSources<T extends Pick<ContextSource, "status">>(sources: readonly T[]): T[] {
  return [...sources].sort((a, b) => rank(a.status) - rank(b.status));
}

export interface StatusCount {
  status: string;
  text: string;
  count: number;
}

/** Cuántas fuentes hay en cada estado, en el mismo orden y con la palabra del backend. */
export function statusCounts(sources: readonly Pick<ContextSource, "status" | "status_text">[]): StatusCount[] {
  const counts = new Map<string, StatusCount>();
  for (const source of sortedSources(sources)) {
    const known = counts.get(source.status);
    if (known === undefined) {
      counts.set(source.status, { status: source.status, text: source.status_text, count: 1 });
    } else {
      known.count += 1;
    }
  }
  return [...counts.values()];
}

/** Las listas del equipo en las que aparece una fuente; un identificador sin lista no se inventa. */
export function namedLists(
  ids: readonly string[],
  lists: readonly ContextSourceList[],
): (ContextSourceList | string)[] {
  return ids.map((id) => lists.find((list) => list.id === id) ?? id);
}
