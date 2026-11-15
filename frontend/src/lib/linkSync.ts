/**
 * Lo poco que la interfaz decide del enlace con Tierra simulado (`core/link_sync.py`): qué marca
 * lleva cada cosa, desde qué instante se declara y qué se firma.
 *
 * Por qué existe: el backend da el corte, las colas y las frases, y la interfaz no redacta nada de
 * eso. Lo que sí elige tiene reglas que merecen prueba:
 *
 * - «Caído» lleva la marca del enlace fuera de servicio (círculo tachado en amarillo, «off-nominal,
 *   attention required»), la misma que el estado declarado del sistema Comunicaciones: un dibujo
 *   por concepto (§5.33). No es rojo: no es una alerta ni mueve ninguna.
 * - Lo que Tierra todavía no tiene (lo pendiente de enviar, lo que falta por llegar, un corte
 *   retenido) es dato caducado o ausente: cian con el anillo punteado (tabla F.5-1).
 * - Arriba y sin nada pendiente, sin marca de estado: no hay nada que señalar.
 * - El instante se declara en la hora de los datos (la última lectura de a bordo, como los demás
 *   asientos declarados) y solo hacia atrás, por pasos fijos: el backend rechaza un cambio anterior
 *   al último, y aquí no se ofrece ninguno posterior a la lectura de a bordo.
 */

import type { LinkChange, LinkSync } from "./api";
import { MISSING_MARK, type StateMark, mark } from "./marks";

/** La marca del enlace caído: la del sistema Comunicaciones «fuera de servicio» (`habitat/systems.ts`). */
export const LINK_DOWN_MARK: StateMark = mark("slash-circle", "yellow");

/** Desde cuándo se puede declarar: horas antes de la última lectura de a bordo. */
export const LINK_OFFSETS_HOURS = [0, 1, 6, 24] as const;

/** El instante de un cambio: la última lectura de a bordo menos `hoursAgo` horas (o ahora, sin lecturas). */
export function linkInstant(referenceTime: string | null, hoursAgo: number, now: Date): string {
  if (!Number.isFinite(hoursAgo) || hoursAgo < 0) throw new RangeError(`horas no válidas: ${hoursAgo}`);
  const base = referenceTime === null ? now.getTime() : Date.parse(referenceTime);
  if (!Number.isFinite(base)) throw new RangeError(`instante de referencia no válido: ${referenceTime}`);
  return new Date(base - hoursAgo * 3_600_000).toISOString();
}

/** El cambio que ofrece el mando: el contrario del vigente. */
export function linkChange(sync: Pick<LinkSync, "state">, at: string, operator: string, note: string): LinkChange {
  return { state: sync.state === "down" ? "up" : "down", at, note: note.trim(), declared_by: operator.trim() };
}

/** La marca de lo que espera: cian si hay algo que Tierra aún no tiene, ninguna si no. */
export function backlogMark(count: number): StateMark | null {
  return count > 0 ? MISSING_MARK : null;
}

/** La marca del aviso de Tierra: cian con el corte retenido por el enlace caído; si no, ninguna. */
export function groundLinkMark(sync: Pick<LinkSync, "held">): StateMark | null {
  return sync.held ? MISSING_MARK : null;
}
