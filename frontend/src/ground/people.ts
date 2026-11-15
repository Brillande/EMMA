/**
 * Personas y organizaciones de las fuentes: lo que el panel decide, separado de lo que pinta.
 *
 * Por qué existe aparte del panel: lo que aquí se puede equivocar es lógica, no pintura. Un año
 * que la ficha no da, pintado sin marca, parecería un dato; una lista de firmantes que la cita
 * abrevia, enseñada entera, diría que no firma nadie más. Está en un `.ts` para que lo pruebe
 * `people.test.ts`.
 *
 * Nada de aquí redacta: los nombres, los cargos, el papel de cada persona en una ficha
 * (`role_text`) y las reglas de lectura son de `GET /api/people`, que las deriva del registro de
 * evidencia. Aquí solo se elige dibujo y color (`lib/marks.ts`) y se cuentan cosas con
 * `lib/format.ts`. Es un inventario de quién produjo lo que EMMA usa: nada de esto decide sobre la
 * tripulación.
 */

import type { PeopleReference } from "../lib/api";
import { formatNumber, formatSourceDate } from "../lib/format";
import { MISSING_MARK, NO_MARK, type StateMark } from "../lib/marks";
import type { UiConcept } from "../lib/uiMarks";

/** El signo del panel y de cada persona: la persona del núcleo (`common`). */
export const PEOPLE_CONCEPT: UiConcept = "person";

/**
 * El signo de cada organización: el sello de la procedencia. La organización de una ficha dice
 * de dónde sale la fuente, no a quién pertenece cada firmante.
 */
export const ORGANIZATION_CONCEPT: UiConcept = "provenance";

export interface YearCell {
  text: string;
  mark: StateMark;
}

/**
 * El año de una ficha, por `formatSourceDate`. Sin fecha, la frase del backend con el anillo cian
 * del dato ausente: no es un dato vacío, es uno que la ficha no tiene.
 */
export function yearCell(year: string | null, noYear: string): YearCell {
  if (year === null) return { text: noYear, mark: MISSING_MARK };
  return { text: formatSourceDate(year), mark: NO_MARK };
}

/**
 * Quien firma una ficha, en el orden de la cita. Si la cita abrevia con «et al.», se dice: la lista
 * no es entera. Sin firmantes, `null` (la ficha no los da; no es «nadie»).
 */
export function authorsLine(ref: Pick<PeopleReference, "authors" | "et_al">): string | null {
  if (ref.authors.length === 0) return null;
  const names = ref.authors.join(", ");
  return ref.et_al ? `${names}, et al.` : names;
}

/** «1 ficha», «12 fichas»: la cifra por `formatNumber`, la palabra en singular o plural. */
export function countOf(n: number, one: string, many: string): string {
  return `${formatNumber(n)} ${n === 1 ? one : many}`;
}
