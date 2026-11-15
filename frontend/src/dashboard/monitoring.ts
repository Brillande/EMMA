/**
 * Como se presenta la capacidad de vigilancia del sistema (`/api/status` → `monitoring`, F.6.2):
 * que dibujo acompaña a cada capacidad y con que señal se pinta la que falta.
 *
 * Existe para que el panel no decida nada: las capacidades, sus nombres y lo que se pierde los
 * da el backend (`api/routes.py`), y aqui solo se fija la forma junto a cada palabra
 * (`icons/sets/mission.ts`). La causa de que falte si es un estado: un dato que no llega es «dato
 * ausente» (anillo punteado, cian: tabla F.5-1, "Missing or stale data") y una decision de la
 * tripulacion es una precaucion sobre la configuracion (triangulo, amarillo, "manual override").
 * Una capacidad o una causa que la interfaz no conoce se enseña con su palabra y el dibujo de
 * «desconocido» (`pictogramTable.ts`): este panel es el que dice que no se vigila, y no puede ser
 * el que tumbe la consola; lo que se pierde lo sigue diciendo la frase del backend.
 */

import type { PictogramName } from "../icons/registry";
import { type StateMark, MISSING_MARK, OK_MARK, UNKNOWN_MARK, mark } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { type PictogramTable, pictogramFor } from "./pictogramTable";

/**
 * Cada capacidad que es un concepto de la interfaz lleva el dibujo de ese concepto
 * (`lib/uiMarks.ts`), sacado de la tabla y no escrito aquí: la línea base personal, los pilares de
 * «Base personal»; el retardo con Tierra, los arcos de la franja y del perfil; la dosis de
 * carrera, el trébol de la radiación; las fechas de las lecturas, el calendario; el anuncio de
 * alertas, la campana; la integridad del registro, el candado del registro firmado. Un concepto
 * no tiene dos dibujos: hasta la limpieza (§5.33.12) la línea base llevaba la tarjeta de
 * identidad (que es «identidad») y la integridad los eslabones (que es «vincular»).
 */
const CAPABILITIES: PictogramTable = {
  "personal-baseline": uiPictogram("baseline"),
  "light-time": uiPictogram("lightTime"),
  "space-weather": "sun-streams",
  "career-dose": uiPictogram("radiation"),
  "reading-dates": uiPictogram("date"),
  "alert-annunciation": uiPictogram("alerts"),
  "record-integrity": uiPictogram("signedLedger"),
};

export function capabilityPictogram(key: string): PictogramName | null {
  return pictogramFor(CAPABILITIES, key);
}

/** Una capacidad disponible: hecho, sin color (la marca de «hecho» de toda la interfaz). */
export const AVAILABLE_MARK: StateMark = OK_MARK;

const CAUSES: Readonly<Record<string, StateMark>> = {
  missing: MISSING_MARK,
  manual: mark("shape-triangle", "yellow"),
};

/** La señal de una causa; una que la interfaz no conoce, la marca de «desconocido». */
export function causeMark(cause: string): StateMark {
  return Object.hasOwn(CAUSES, cause) ? (CAUSES[cause] ?? UNKNOWN_MARK) : UNKNOWN_MARK;
}

export function isKnownCause(cause: string): boolean {
  return Object.hasOwn(CAUSES, cause);
}

/**
 * La marca de «reducida»: la de su causa. La del dato ausente si falta alguno, la de la decision
 * manual si solo hay de esas, y la de «desconocido» si la causa no se conoce. La franja y el panel
 * de vigilancia la sacan de aqui los dos: hasta la limpieza (§5.33.12) el panel pintaba siempre
 * la del dato ausente, y «reducida por decision manual» tenia dos dibujos.
 */
export function reducedMark(capabilities: readonly { readonly cause?: string | null | undefined }[]): StateMark {
  const causes = new Set(capabilities.map((item) => item.cause));
  if (causes.has("missing")) return causeMark("missing");
  if (causes.has("manual")) return causeMark("manual");
  return UNKNOWN_MARK;
}
