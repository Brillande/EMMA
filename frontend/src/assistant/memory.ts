/**
 * La memoria de la conversación con el asistente: los últimos turnos de esta sesión y nada más.
 *
 * Por qué así: una pregunta de seguimiento («¿y ayer?») necesita lo que se acaba de hablar, pero
 * lo hablado con el asistente es de salud de una persona. Vive solo en el estado de React —nunca
 * en `localStorage` ni en el backend—, se manda como `history` en cada turno y se borra al cambiar
 * de consola o de tripulante y al poner la privacidad (`memoryScope`). Las cifras de un
 * seguimiento las da el backend con sus datos, no lo que recuerde el modelo: esto solo le dice de
 * qué se hablaba.
 */

import type { AssistantHistoryItem, AssistantTurn } from "../lib/api";

/** Cuántos turnos se recuerdan y se mandan: el tope del contrato del backend. */
export const MEMORY_LIMIT = 8;

/** Un turno del hilo a la vista: lo que se dijo y, del asistente, quién lo redactó. */
export interface ThreadItem extends AssistantHistoryItem {
  /** Del asistente: `model`, `backend` o `fixed` del backend; `console` es un rótulo de la consola. */
  source?: AssistantTurn["reply_source"] | "console";
  /** El rótulo del backend cuando lo redactó el modelo («sin validar»). */
  label?: string | null;
  /** Clave estable en pantalla: con el tope, el primero sale y los demás no cambian de clave. */
  id?: number;
}

let nextId = 0;

/** Añade un turno y se queda con los últimos `MEMORY_LIMIT`. No muta el hilo de antes. */
export function remember(thread: readonly ThreadItem[], item: ThreadItem): ThreadItem[] {
  if (item.text.trim() === "") return [...thread];
  nextId += 1;
  return [...thread, { ...item, id: nextId }].slice(-MEMORY_LIMIT);
}

/** Lo que se manda como `history`: rol y texto, sin los rótulos de pantalla. */
export function historyOf(thread: readonly ThreadItem[]): AssistantHistoryItem[] {
  return thread.slice(-MEMORY_LIMIT).map(({ role, text }) => ({ role, text }));
}

/**
 * De qué es la memoria: consola, tripulante y privacidad. Si cambia cualquiera, la memoria se
 * borra: poner la privacidad borra lo hablado antes (puede haber otra persona delante), y
 * quitarla no devuelve lo hablado con ella puesta.
 */
export function memoryScope(console: string, subject: string, privacy: boolean): string {
  return `${console}|${subject}|${privacy ? "privacidad" : "abierta"}`;
}
