/**
 * Las notas de Tierra a bordo (§5.38.1): cuándo está a bordo una nota y con qué signo va su clase.
 *
 * Por qué existe: lo que sube de Tierra tarda un tiempo de luz, como lo que baja. La consola de
 * tripulación pide las notas con el corte del reloj (`arrivalCut`, la misma cuenta con que la
 * consola de Tierra corta lo que baja) y la de Tierra dice de cada nota firmada si ya está a bordo
 * o cuándo llegará. Si cada consola hiciera su cuenta, una nota podría verse a bordo mientras
 * Tierra la da en tránsito: aquí hay una sola, con el mismo corte que aplica el backend
 * (`recorded <= until`), y su prueba.
 */

import type { GroundNote } from "./api";
import { arrivalCut } from "./crew";
import { type StateMark, UNKNOWN_MARK, mark } from "./marks";

/** Dónde está una nota firmada: a bordo, en camino o sin saberlo (sin efemérides). */
export type NoteTransit =
  | { readonly state: "on-board"; readonly at: Date }
  | { readonly state: "in-transit"; readonly at: Date }
  | { readonly state: "unknown" };

/**
 * Una nota está a bordo si se firmó antes del corte de ahora (el reloj menos un tiempo de luz);
 * `at` es cuando llegó o llegará: la firma más un tiempo de luz. Sin efemérides no hay tiempo de
 * luz y no se sabe: la consola de a bordo, sin retardo que aplicar, la enseña ya.
 */
export function noteTransit(signedAt: string, oneWayMinutes: number | null, now: number): NoteTransit {
  const signed = Date.parse(signedAt);
  if (!Number.isFinite(signed)) {
    throw new RangeError(`hora de firma no valida: ${signedAt}`);
  }
  const cut = arrivalCut(oneWayMinutes, now);
  if (cut === undefined || oneWayMinutes === null) return { state: "unknown" };
  const at = new Date(signed + oneWayMinutes * 60_000);
  return signed <= cut.getTime() ? { state: "on-board", at } : { state: "in-transit", at };
}

/**
 * El signo de la clase de una nota, sin color: una nota no es una alerta. La palabra la da el
 * backend (`kind_display`); una clase que la interfaz no conoce, con la marca de desconocido.
 */
export function noteKindMark(kind: GroundNote["kind"] | string): StateMark {
  if (kind === "question") return mark("question", null);
  if (kind === "information") return mark("circle-i", null);
  return UNKNOWN_MARK;
}
