/**
 * El sexo declarado del tripulante tal como lo sirve el backend (`GET /api/crew/sex`) y su
 * declaración (`POST /api/crew/sex`).
 *
 * Por qué existe aparte de `lib/api.ts`: el lote «ciclo» (2026-11-14) lo trabajan varias unidades a
 * la vez y `api.ts` lo editan muchas sesiones; el contrato vive aquí para no chocar. Reutiliza de
 * `api.ts` lo que exporta: la cabecera de la consola (`withConsoleHeader`) y el error con el motivo
 * del backend (`ApiError`), como `inventoryApi.ts`.
 *
 * Decisión del usuario (2026-11-14, revierte la §5.36.19): el sexo lo declara el propio tripulante,
 * queda en un asiento firmado propio (`crew-sex`) y se borra solo, con la redacción
 * (`POST /api/audit/redact/{ledger_index}`). Sin declaración vigente el backend dice «no declarado»
 * (`declared: false`, `sex: null`); aquí no se completa ni se supone nada.
 */
import { ApiError, withConsoleHeader } from "./api";

/** Los dos valores que el backend acepta (`CREW_SEX_VALUES` de `core/storage.py`). */
export const CREW_SEX_VALUES = ["female", "male"] as const;
export type CrewSexValue = (typeof CREW_SEX_VALUES)[number];

/** `GET /api/crew/sex` con declaración vigente. */
export interface CrewSexDeclared {
  subject: string;
  declared: true;
  sex: CrewSexValue;
  declared_by: string;
  recorded: string;
  /** El asiento vigente: el que se redacta para borrarlo. */
  ledger_index: number;
  values: CrewSexValue[];
}

/** `GET /api/crew/sex` sin declaración vigente: nunca un valor por omisión. */
export interface CrewSexUndeclared {
  subject: string;
  declared: false;
  sex: null;
  /** La palabra del backend («no declarado»); la interfaz la enseña tal cual. */
  status: string;
  values: CrewSexValue[];
}

export type CrewSex = CrewSexDeclared | CrewSexUndeclared;

/** `POST /api/crew/sex`. */
export interface CrewSexBody {
  subject: string;
  sex: CrewSexValue;
  declared_by: string;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, withConsoleHeader(init));
  if (!response.ok) {
    let detail = response.statusText;
    let integrityBroken = false;
    try {
      const body = (await response.json()) as { detail?: unknown; integrity_ok?: unknown };
      if (body.detail !== undefined) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
      integrityBroken = body.integrity_ok === false;
    } catch {
      // cuerpo no JSON: se queda el texto de estado
    }
    throw new ApiError(response.status, detail, integrityBroken);
  }
  return (await response.json()) as T;
}

/** El tripulante por omisión de las rutas del backend (`subject = "crew-01"`). */
export const DEFAULT_SUBJECT = "crew-01";

/** La ruta de lectura; con `until`, lo declarado hasta ese instante (el corte de reloj de Tierra). */
export function crewSexPath(until?: Date, subject: string = DEFAULT_SUBJECT): string {
  const base = `/crew/sex?subject=${encodeURIComponent(subject)}`;
  return until === undefined ? base : `${base}&until=${encodeURIComponent(until.toISOString())}`;
}

/** Lo declarado vigente; con `until`, lo que Tierra ya tiene en su corte. */
export function getCrewSex(until?: Date, subject: string = DEFAULT_SUBJECT): Promise<CrewSex> {
  return call<CrewSex>(crewSexPath(until, subject));
}

/** Firma una declaración. Va con la cabecera de la consola (`withConsoleHeader` la pone en todo POST). */
export function declareCrewSex(body: CrewSexBody): Promise<{ ledger_index: number }> {
  return call<{ ledger_index: number }>("/crew/sex", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
