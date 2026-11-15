/**
 * Qué aviso de hora toca ahora: las reglas de Marplanner (`/api/time-announcements`) contra el
 * reloj del hogar.
 *
 * Por qué aparte: es la parte que se equivoca sin hacer ruido (día de la semana en la zona del
 * hogar, no en UTC; un aviso por regla y minuto, aunque el reloj se mire varias veces en ese
 * minuto). Se prueba sin navegador (`announcements.test.ts`); lo que habla está en
 * `TimeAnnouncer.tsx`.
 */

export interface TimeRule {
  id: string;
  time: string;
  weekDays: string[];
  isActive: boolean;
}

const WEEKDAY_KEYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"] as const;

/** La hora del hogar (`HH:MM`), su día de la semana (`mon`…) y su fecha, en la zona dada. */
export function householdClock(at: Date, timeZone: string): { time: string; weekday: string; date: string } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    weekday: "short",
  }).formatToParts(at);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  const weekday = get("weekday").toLowerCase().slice(0, 3);
  if (!(WEEKDAY_KEYS as readonly string[]).includes(weekday)) throw new RangeError(`día no leído: ${weekday}`);
  return { time: `${get("hour")}:${get("minute")}`, weekday, date: `${get("year")}-${get("month")}-${get("day")}` };
}

/**
 * La regla que toca en este minuto y la clave con que se recuerda que ya se dijo, o `null`.
 * `said` son las claves ya dichas: la misma regla no se repite en el mismo minuto.
 */
export function dueRule(
  rules: readonly TimeRule[],
  at: Date,
  timeZone: string,
  said: ReadonlySet<string>,
): { rule: TimeRule; key: string } | null {
  const clock = householdClock(at, timeZone);
  for (const rule of rules) {
    if (!rule.isActive || rule.time !== clock.time || !rule.weekDays.includes(clock.weekday)) continue;
    const key = `${rule.id}|${clock.date}|${clock.time}`;
    if (!said.has(key)) return { rule, key };
  }
  return null;
}
