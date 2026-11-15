/**
 * El estado del retardo con Tierra tal y como lo dice el backend (`/api/status` → `comms_status`,
 * `app/environment/comms_status.py`), y con qué marca se pinta.
 *
 * Por qué existe (decisión del usuario, 2026-11-11): cada vista deducía «Sin efemérides» por su
 * cuenta de `comms === null` o de la caché de JPL Horizons, y con SPICE primero eso mentía: un día
 * que SPICE calcula en local salía sin efemérides si Horizons no lo tenía en caché, y un perfil sin
 * objetivo de efemérides (órbita baja, cislunar, superficie lunar) salía en cian, como un dato que
 * falta, cuando el retardo no se calcula por diseño. Ahora el backend da un estado y su palabra, y
 * aquí solo se fija la marca de la tabla F.5-1 de NASA-STD-3001 Vol 2:
 *
 * - `available`: hay retardo; sin señal (la frescura sigue en `freshness.comms`).
 * - `not_applicable`: «no disponible», gris con el círculo tachado (F.5-1 *unavailable*): no falta nada.
 * - `missing`: «dato ausente», cian con el anillo punteado (F.5-1 *missing or stale data*).
 *
 * La discrepancia del cálculo local con Horizons (`discrepancy`) es un dato contradictorio: algo
 * que mirar, el triángulo en amarillo (F.5-1 *off-nominal, attention required*), la misma marca que
 * las firmas que discrepan y las analíticas que no coinciden (`hmi-state-of-the-art.md` §5.32.10).
 * No es una alerta clínica: el día discrepante ya se sirve con Horizons, la referencia.
 *
 * Los tipos van aquí y no en `lib/api.ts` porque ese fichero lo edita otra sesión; al volver a él,
 * `CrewStatus` debe llevar `comms_status: CommsStatus`.
 */

import type { CrewStatus } from "./api";
import { tr } from "./i18n";
import { type StateMark, MISSING_MARK, NO_MARK, UNAVAILABLE_MARK, mark } from "./marks";

export type CommsState = "available" | "not_applicable" | "missing";

export interface CommsDiscrepancy {
  word: string;
  text: string;
  epoch: string;
  used: string;
  /** Dónde quedó firmada en el registro (`ephemeris-discrepancy`), o `null` si aún no consta en el corte. */
  signed: { ledger_index: number; recorded: string } | null;
}

export interface CommsStatus {
  state: CommsState;
  source: "spice" | "horizons" | null;
  source_text: string | null;
  word: string;
  text: string;
  discrepancy: CommsDiscrepancy | null;
}

/** Dato contradictorio: el triángulo en amarillo (F.5-1, *attention required*). */
export const DISCREPANCY_MARK: StateMark = mark("shape-triangle", "yellow");

const STATE_MARKS: Record<CommsState, StateMark> = {
  available: NO_MARK,
  not_applicable: UNAVAILABLE_MARK,
  missing: MISSING_MARK,
};

/** La marca de un estado del retardo; uno que la interfaz no conoce va «no disponible», no «al día». */
export function commsMark(state: string): StateMark {
  return Object.hasOwn(STATE_MARKS, state) ? STATE_MARKS[state as CommsState] : UNAVAILABLE_MARK;
}

/**
 * El estado del retardo de una respuesta de `/api/status`. Con un backend anterior, sin
 * `comms_status`, lo de antes: sin `comms`, «Sin efemérides».
 */
export function commsStatusOf(status: Pick<CrewStatus, "comms">): CommsStatus {
  const given = (status as { comms_status?: CommsStatus | null }).comms_status;
  if (given != null) return given;
  const missing = tr("Sin efemérides", "No ephemeris");
  return status.comms === null
    ? { state: "missing", source: null, source_text: null, word: missing, text: missing, discrepancy: null }
    : { state: "available", source: null, source_text: null, word: "", text: "", discrepancy: null };
}
