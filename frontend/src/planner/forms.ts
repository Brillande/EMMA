/**
 * Lo que se teclea en los formularios del planificador, convertido a lo que pide Marplanner.
 *
 * Por qué existe aparte del panel: la conversión de un día y unas horas del hogar a instantes UTC
 * es donde se equivoca uno (el fin de un evento de día entero es EXCLUSIVO en Marplanner; una hora
 * se lee en la zona del hogar, no en UTC). Aquí se prueba sin pintar nada (`forms.test.ts`).
 */

import { addDays } from "./labels";
import type { NewEvent } from "./plannerApi";

export interface EventForm {
  title: string;
  date: string;
  allDay: boolean;
  start: string;
  end: string;
}

const DAY = /^\d{4}-\d{2}-\d{2}$/;
const TIME = /^([01]\d|2[0-3]):[0-5]\d$/;

/** El instante UTC de un día y una hora del reloj de la zona dada. */
export function zonedToUtc(date: string, time: string, timeZone: string): string {
  const [y, mo, d] = date.split("-").map(Number);
  const [h, mi] = time.split(":").map(Number);
  const guess = Date.UTC(y!, mo! - 1, d!, h!, mi!);
  // Lo que marca el reloj de la zona en ese instante, para corregir el desfase (dos pasadas: el
  // desfase puede cambiar justo en el salto de hora).
  const offsetAt = (ms: number) => {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).formatToParts(new Date(ms));
    const get = (type: string) => Number(parts.find((p) => p.type === type)?.value);
    return Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute")) - ms;
  };
  let at = guess - offsetAt(guess);
  at = guess - offsetAt(at);
  return new Date(at).toISOString();
}

/** El cuerpo para Marplanner, o el motivo por el que todavía no se puede crear. */
export function eventBody(form: EventForm, timeZone: string): NewEvent | string {
  const title = form.title.trim();
  if (title === "") return "falta el título";
  if (!DAY.test(form.date)) return "falta el día";
  if (form.allDay) {
    return { title, allDay: true, startDate: form.date, endDate: addDays(form.date, 1) };
  }
  if (!TIME.test(form.start) || !TIME.test(form.end)) return "faltan las horas";
  if (form.end <= form.start) return "la hora de fin tiene que ser posterior a la de inicio";
  return {
    title,
    allDay: false,
    startUtc: zonedToUtc(form.date, form.start, timeZone),
    endUtc: zonedToUtc(form.date, form.end, timeZone),
    tzid: timeZone,
  };
}
