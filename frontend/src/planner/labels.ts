/**
 * Las palabras del planificador en la consola de EMMA.
 *
 * Por qué existe: Marplanner (`marplanner/`) manda claves (`dayPeriod.morning`, `lunch`), no
 * palabras; su propio cliente las traduce. Aquí van las suyas en español, copiadas de
 * `marplanner/src/client/i18n/messages.ts` (MIT, © 2026 Diego Mariño). Una clave que no esté se
 * enseña tal cual, sin inventar una palabra.
 */

const DAY_PERIODS: Record<string, string> = {
  "dayPeriod.morning": "Mañana",
  "dayPeriod.afternoon": "Mediodía",
  "dayPeriod.evening": "Tarde",
  "dayPeriod.night": "Noche",
};

const MEAL_SLOTS: Record<string, string> = {
  breakfast: "Desayuno",
  lunch: "Comida",
  snack: "Merienda",
  dinner: "Cena",
};

/** Orden de las comidas en el día, el de Marplanner. */
export const MEAL_SLOT_ORDER = ["breakfast", "lunch", "snack", "dinner"] as const;

export function dayPeriodLabel(key: string): string {
  return DAY_PERIODS[key] ?? key;
}

export function mealSlotLabel(slot: string): string {
  return MEAL_SLOTS[slot] ?? slot;
}

/** Fecha local del hogar en AAAA-MM-DD (la que piden las rutas de Marplanner). */
export function householdDate(at: Date, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone,
  }).formatToParts(at);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

/** Suma días a una fecha AAAA-MM-DD, sin pasar por la hora local del navegador. */
export function addDays(iso: string, days: number): string {
  const at = new Date(`${iso}T12:00:00Z`);
  at.setUTCDate(at.getUTCDate() + days);
  return at.toISOString().slice(0, 10);
}
