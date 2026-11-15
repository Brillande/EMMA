/**
 * Las cuentas de la banda de ayuda urgente (`components/HelpBanner.tsx`), aparte para probarlas sin
 * navegador. Decisión del usuario (2026-11-14): «Tierra está muy lejos; tiene que alertar a quien
 * tengas más cerca y, obviamente, a Tierra». La tripulación la ve al firmarse; Tierra, un tiempo de
 * luz después, y la consola de a bordo dice cuándo, para que nadie espere de Tierra lo que aún no
 * puede saber.
 */

import type { HelpRequest, HelpRequests, LinkSync } from "./api";
import { arrivalCut, linkedCut } from "./crew";
import { tr } from "./i18n";

/** Lo que dispara la consola al pedir ayuda: la banda vuelve a pedir la lista sin esperar a su ritmo. */
export const HELP_REQUESTED_EVENT = "emma:help-requested";

/** Cada cuánto vuelve a pedir la banda: una petición de ayuda no espera al estado (30 s). */
export const HELP_REFRESH_MS = 3_000;

/** Lo que lleva el aviso de la consola que pide: lo que el backend ya confirmó al firmar. */
export interface HelpRequestedDetail {
  ledger_index: number;
  subject: string;
  signed_by: string;
  at: string;
  signed_at: string;
}

/** Lo que se enseña mientras el backend busca dónde está cada uno: la banda no espera a la lista. */
export const LOCATING = tr("localizando…", "locating…");

/**
 * La lista con la petición recién firmada delante, sin esperar a releerla (en una página que carga
 * todo lo demás, la relectura tardaba ~5 s). Ubicación y cercanía llegan con la siguiente lectura.
 * Si ya estaba, no se toca.
 */
export function withProvisional(data: HelpRequests | null, detail: HelpRequestedDetail, headline: string): HelpRequests {
  const base: HelpRequests = data ?? { until: null, headline, basis: "", open: [] };
  if (base.open.some((item) => item.ledger_index === detail.ledger_index)) return base;
  const provisional: HelpRequest = {
    ledger_index: detail.ledger_index,
    subject: detail.subject,
    signed_by: detail.signed_by === "" ? null : detail.signed_by,
    reason: null,
    at: detail.at,
    signed_at: detail.signed_at,
    location_display: LOCATING,
    nearby: [],
    nearby_note: null,
  };
  return { ...base, open: [provisional, ...base.open] };
}

/** Cuándo le llega a Tierra lo firmado a bordo: la firma más un tiempo de luz; sin efemérides, no se sabe. */
export function groundArrival(signedAt: string, oneWayMinutes: number | null): Date | null {
  if (oneWayMinutes === null || !Number.isFinite(oneWayMinutes)) return null;
  const signed = Date.parse(signedAt);
  return Number.isFinite(signed) ? new Date(signed + oneWayMinutes * 60_000) : null;
}

/**
 * El corte de reloj con que Tierra pide la lista: el reloj menos un tiempo de luz, y con el enlace
 * simulado caído, la caída (`linkedCut`, la misma cuenta que el resto de Tierra). Sin efemérides y
 * con el enlace arriba, `undefined`: todo lo firmado.
 */
export function groundHelpCut(oneWayMinutes: number | null, sync: LinkSync | null, now: number): Date | undefined {
  return linkedCut(arrivalCut(oneWayMinutes, now) ?? null, sync) ?? undefined;
}

/** Las peticiones que no estaban la vez anterior: son las que se leen en voz alta. */
export function freshRequests(seen: ReadonlySet<number>, open: readonly HelpRequest[]): HelpRequest[] {
  return open.filter((item) => !seen.has(item.ledger_index));
}

/** Lo que se lee en voz alta de una petición, con las palabras del backend. */
export function spokenRequest(headline: string, item: HelpRequest): string {
  const nearest = item.nearby[0];
  const parts = [`${headline}: ${item.subject}`, item.location_display];
  if (nearest !== undefined) parts.push(`${nearest.subject}, ${nearest.proximity_display}`);
  return parts.join(". ");
}
