/**
 * Lo tecleado de una sesión de la batería Cognition: qué se envía y qué no.
 *
 * Las puntuaciones las da el programa de la batería, que es de NASA; aquí solo se copian. Qué
 * pruebas hay, qué puntuaciones lleva cada una y su rango los da el backend
 * (`GET /api/cognition/protocol`). Lo tecleado se comprueba contra ese rango antes de enviarlo,
 * con la misma regla que el backend aplica igual (una prueba va con todas sus puntuaciones):
 * esta comprobación ahorra el viaje, no lo sustituye.
 *
 * Ningún campo tiene valor por defecto, y no se interpreta lo anotado: ni «bajo», ni «normal»,
 * ni color según el valor.
 */
import { type Check, check as checkRanged, operatorName } from "../diary/entry";
import type {
  CognitionField,
  CognitionProtocol,
  CognitionSubmissionBody,
  CognitionTestSpec,
} from "../lib/api";

/** Lo tecleado en cada campo, por clave de indicador. Vacío: no se anota. */
export type Draft = Record<string, string>;

/** Un campo contra el rango físico del catálogo: la misma regla que el diario. */
export function check(field: CognitionField, text: string): Check {
  return checkRanged(field, text);
}

/** Si una prueba está a medias: alguna puntuación escrita y otra vacía. */
export function incomplete(test: CognitionTestSpec, draft: Draft): boolean {
  const filled = test.fields.filter((field) => (draft[field.key] ?? "").trim() !== "");
  return filled.length > 0 && filled.length < test.fields.length;
}

export interface Prepared {
  /** Lo que se enviaría, o `null` si algo lo impide. */
  body: CognitionSubmissionBody | null;
  /** Cuántos campos no son una cifra en rango. */
  invalid: number;
  /** Las siglas de las pruebas a medias. */
  partial: string[];
  /** Ninguna puntuación escrita. */
  empty: boolean;
  /** Falta el nombre de quien teclea. */
  unnamed: boolean;
}

/** Lo que se enviaría con lo tecleado, y por qué no se puede si no se puede. */
export function prepare(
  protocol: CognitionProtocol,
  draft: Draft,
  subject: string,
  operator: string,
): Prepared {
  const scores: Record<string, number> = {};
  let invalid = 0;
  const partial: string[] = [];
  for (const test of protocol.tests) {
    if (!test.recorded_here) continue;
    if (incomplete(test, draft)) partial.push(test.sigla);
    for (const field of test.fields) {
      const result = check(field, draft[field.key] ?? "");
      if (result.state === "invalid") invalid += 1;
      if (result.state === "ok") scores[field.key] = result.value;
    }
  }
  const name = operatorName(operator);
  const empty = Object.keys(scores).length === 0 && invalid === 0;
  const blocked = invalid > 0 || partial.length > 0 || empty;
  return {
    body: blocked || name === null ? null : { scores, subject, recorded_by: name },
    invalid,
    partial,
    empty,
    unnamed: name === null,
  };
}
