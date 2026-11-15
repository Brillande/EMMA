/**
 * Formulario del registro diario: qué se envía y qué no.
 *
 * Ningún campo tiene valor por defecto: un ánimo de 5 precargado se enviaría sin que nadie
 * lo hubiera dicho. Lo que se puede anotar, su rango y su procedencia los da el backend
 * (`GET /api/diary`); aquí solo se comprueba lo tecleado contra ese rango antes de enviarlo.
 * El backend lo rechaza igual: esta comprobación ahorra el viaje, no lo sustituye.
 *
 * No se interpreta lo anotado: ni «bajo», ni «normal», ni color según el valor.
 *
 * Desde el 2026-10-26 la aceptabilidad de la comida lleva el alimento valorado (`food_item` del
 * indicador): sin él no se envía, y un alimento sin su valoración tampoco se pierde en silencio.
 * La regla completa (caracteres, filtro de lenguaje) la aplica el backend; aquí solo lo vacío y
 * el tope de longitud, para ahorrar el viaje. Desde el 2026-10-31 la fracción rechazada lo admite
 * opcional (`food_item.required` en falso): vacío, se envía sin él; escrito, se envía con él.
 */
import type { DiaryCatalog, DiaryIndicator, DiaryObservationBody } from "../lib/api";
import { tr } from "../lib/i18n";
import { type RequestOutcome, requestOutcome } from "../lib/marks";

/** Lo tecleado en cada campo, por clave de indicador. Vacío: no se anota. */
export type Draft = Record<string, string>;

export type Check =
  | { state: "empty" }
  | { state: "ok"; value: number }
  | { state: "invalid"; reason: string };

// Solo cifras, con coma o punto decimal. «1e3», «0x10» o «7 puntos» no son una anotación.
const NUMBER = /^-?\d+(?:[.,]\d+)?$/;

/** La cifra tecleada, o `null` si no es una cifra. La coma decimal es la de la consola. */
export function parseValue(text: string): number | null {
  const trimmed = text.trim();
  if (!NUMBER.test(trimmed)) return null;
  const value = Number(trimmed.replace(",", "."));
  return Number.isFinite(value) ? value : null;
}

/** Lo que hace falta de un indicador para comprobar un campo: su rango y cómo se dice. */
export type Ranged = Pick<DiaryIndicator, "physical_min" | "physical_max" | "range_text">;

/**
 * Un campo contra el rango físico del catálogo. La usan el diario y las puntuaciones de la
 * batería Cognition (`cognition/draft.ts`): una sola regla para leer y acotar una cifra tecleada.
 */
export function check(indicator: Ranged, text: string): Check {
  if (text.trim() === "") return { state: "empty" };
  const value = parseValue(text);
  if (value === null) return { state: "invalid", reason: tr("No es una cifra.", "Not a number.") };
  const { physical_min: low, physical_max: high } = indicator;
  if ((low !== null && value < low) || (high !== null && value > high)) {
    return { state: "invalid", reason: tr(`Fuera del rango: ${indicator.range_text}.`, `Out of range: ${indicator.range_text}.`) };
  }
  return { state: "ok", value };
}

/**
 * El nombre de quien teclea, recortado, o `null` si no vale como nombre: vacío, o sin una
 * letra ni una cifra. Es la regla del backend, que lo rechaza igual; aquí ahorra el viaje.
 */
export function operatorName(operator: string): string | null {
  const name = operator.trim();
  return /[\p{L}\p{N}]/u.test(name) ? name : null;
}

/** Lo tecleado como alimento valorado, por clave de indicador. Vacío: no hay alimento. */
export type Items = Record<string, string>;

/** Por qué el alimento de un indicador no se puede enviar, o `null` si se puede. */
export function itemProblem(
  indicator: DiaryIndicator,
  value: Check,
  item: string,
): string | null {
  const rule = indicator.food_item;
  if (rule === null || rule === undefined) return null;
  const name = item.trim();
  // «La cifra» y no «la valoración»: en la fracción rechazada lo que falta es la fracción.
  if (value.state === "empty") {
    return name === "" ? null : tr(`${rule.label}: falta la cifra.`, `${rule.label}: the number is missing.`);
  }
  // Donde el backend lo exige (la valoración), sin alimento no se envía; donde lo admite sin más
  // (la fracción rechazada), un alimento vacío es no decir el plato, y se envía sin él.
  if (name === "") return rule.required ? tr(`Falta: ${rule.label}.`, `Missing: ${rule.label}.`) : null;
  // Nunca más estricto que el backend, que cuenta en forma NFC y con los espacios de dentro
  // reducidos a uno: una tilde escrita descompuesta (letra + marca) no cuenta dos. Sin las
  // marcas la cuenta no pasa nunca de la del backend; lo que quede por encima lo dice él.
  if ([...name.replace(/\s+/gu, " ").replace(/\p{M}/gu, "")].length > rule.max_length) {
    return tr(`${rule.label}: pasa del tope de caracteres.`, `${rule.label}: over the character limit.`);
  }
  return null;
}

export interface Prepared {
  /** Una observación por campo relleno, en el orden del catálogo. */
  bodies: DiaryObservationBody[];
  /** Campos rellenos que no se pueden enviar, con su motivo. */
  problems: { key: string; reason: string }[];
  /** Falta decir quién anota: sin nombre no se envía nada. */
  unnamed: boolean;
}

/**
 * Lo que se enviaría. Con un solo campo inválido no se envía ninguno: cada valor es un
 * asiento firmado que no se borra, y medio registro guardado no se puede deshacer. Sin el
 * nombre de quien anota tampoco: el backend lo firma con cada valor y lo exige.
 */
export function prepare(
  catalog: DiaryCatalog,
  subject: string,
  draft: Draft,
  operator: string,
  items: Items = {},
): Prepared {
  const name = operatorName(operator);
  const bodies: DiaryObservationBody[] = [];
  const problems: Prepared["problems"] = [];
  for (const indicator of catalog.indicators) {
    const result = check(indicator, draft[indicator.key] ?? "");
    const item = items[indicator.key] ?? "";
    const itemIssue = itemProblem(indicator, result, item);
    if (result.state === "invalid") {
      problems.push({ key: indicator.key, reason: result.reason });
    } else if (itemIssue !== null) {
      problems.push({ key: indicator.key, reason: itemIssue });
    } else if (result.state === "ok" && name !== null) {
      // Ni fuente, ni tipo, ni entorno, ni hora: los pone el backend, y enviarlos es un 422.
      const body: DiaryObservationBody = {
        key: indicator.key,
        value: result.value,
        subject,
        recorded_by: name,
      };
      // El alimento va tal como se tecleó: lo normaliza y lo firma el backend. Vacío, no va: en
      // la fracción rechazada es opcional, y en la valoración ya lo ha parado `itemProblem`.
      if (indicator.food_item && item.trim() !== "") body.food = item;
      bodies.push(body);
    }
  }
  return { bodies, problems, unnamed: name === null };
}

export function canSubmit(prepared: Prepared): boolean {
  return !prepared.unnamed && prepared.problems.length === 0 && prepared.bodies.length > 0;
}

export interface Outcome {
  /** Claves cuyo valor quedó firmado. */
  saved: string[];
  /**
   * El primero que no entró, con el motivo del backend tal cual y la marca de lo que fue (un «no»
   * del backend o una petición caída, `requestOutcome`, §5.34.14). Los siguientes no se envían.
   */
  failed: { key: string; outcome: RequestOutcome } | null;
}

/**
 * Envía uno a uno y se detiene en el primer rechazo. Lo ya guardado se queda guardado (el
 * registro es de solo añadir), así que el resultado dice qué entró y qué no.
 */
export async function submitAll(
  bodies: DiaryObservationBody[],
  send: (body: DiaryObservationBody) => Promise<unknown>,
): Promise<Outcome> {
  const saved: string[] = [];
  for (const body of bodies) {
    try {
      await send(body);
      saved.push(body.key);
    } catch (reason) {
      return { saved, failed: { key: body.key, outcome: requestOutcome(reason) } };
    }
  }
  return { saved, failed: null };
}

/** El borrador tras un envío: se vacía lo guardado y se conserva lo que no entró. */
export function afterSubmit(draft: Draft, outcome: Outcome): Draft {
  return Object.fromEntries(Object.entries(draft).filter(([key]) => !outcome.saved.includes(key)));
}
