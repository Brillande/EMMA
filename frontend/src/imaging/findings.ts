/**
 * Formulario de signos: cuando esta completo, como se lee lo registrado y con que marca.
 *
 * Un signo sin elegir no es "ausente": el formulario no se puede enviar hasta que cada signo
 * de cada ventana tiene un valor, "no valorable" incluido. El backend lo exige igual; esto
 * evita que el operador se entere solo al enviar.
 *
 * La marca de cada valor (`signValueMark`) esta aqui y no en los paneles porque el mismo valor
 * se lee a bordo y en Tierra: la ventana con algo dentro (`fan-dot`) para lo que se vio, la
 * ventana vacia (`fan-dash`) para lo que no, y «no disponible» (`slash-circle`, gris) para lo
 * no valorable. Los valores que comparan y no dicen presencia (mayor, igual, menor) van con su
 * palabra sola: un dibujo les supondria un sentido que no tienen.
 */

import type { RecordedFindings, UltrasoundProtocol } from "../lib/api";
import { type StateMark, mark } from "../lib/marks";

export type FindingsForm = Record<string, Record<string, string>>;

export const NOT_ASSESSABLE = "no-valorable";

export function missingSigns(protocol: UltrasoundProtocol, form: FindingsForm): number {
  let missing = 0;
  for (const view of protocol.views) {
    for (const sign of view.signs) {
      const value = form[view.key]?.[sign.key];
      if (value === undefined || !(value in sign.values)) missing += 1;
    }
  }
  return missing;
}

export function withValue(
  form: FindingsForm,
  view: string,
  sign: string,
  value: string,
): FindingsForm {
  return { ...form, [view]: { ...(form[view] ?? {}), [sign]: value } };
}

export interface ReadableFinding {
  view: string;
  sign: string;
  /** El valor tal como lo guardo el backend (`presente`, `no-valorable`…): con el se elige la marca. */
  code: string;
  /** El valor como lo lee una persona: la palabra del protocolo. */
  value: string;
  assessable: boolean;
}

/** Lo registrado con los nombres que lee una persona, en el orden del protocolo. */
export function readable(protocol: UltrasoundProtocol, record: RecordedFindings): ReadableFinding[] {
  const rows: ReadableFinding[] = [];
  for (const view of protocol.views) {
    for (const sign of view.signs) {
      const value = record.findings[view.key]?.[sign.key];
      if (value === undefined) continue;
      rows.push({
        view: view.display,
        sign: sign.display,
        code: value,
        value: sign.values[value] ?? value,
        assessable: value !== NOT_ASSESSABLE,
      });
    }
  }
  return rows;
}

/** Algo se vio en la ventana (el abanico de la imagen): presente, visto, lineas B aisladas o multiples. */
export const SEEN_MARK: StateMark = mark("fan-dot", null);
/** Nada en la ventana: ausente, no visto, ninguna linea B. */
export const NOT_SEEN_MARK: StateMark = mark("fan-dash", null);
/** La ventana no se pudo valorar: no disponible, gris (tabla F.5-1). */
export const NOT_ASSESSABLE_MARK: StateMark = mark("slash-circle", "gray");
/** Un valor que compara (mayor, igual, menor) o que la interfaz no conoce: la palabra sola. */
export const WORD_ONLY_MARK: StateMark = mark(null, null);

const SEEN = new Set(["presente", "visto", "aisladas", "multiples"]);
const NOT_SEEN = new Set(["ausente", "no-visto", "ninguna"]);

/** La marca con la que se lee el valor de un signo. La palabra la da el protocolo del backend. */
export function signValueMark(code: string): StateMark {
  if (code === NOT_ASSESSABLE) return NOT_ASSESSABLE_MARK;
  if (SEEN.has(code)) return SEEN_MARK;
  if (NOT_SEEN.has(code)) return NOT_SEEN_MARK;
  return WORD_ONLY_MARK;
}
