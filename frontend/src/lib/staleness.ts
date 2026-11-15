/**
 * Como se pinta un dato externo segun este al dia o no.
 *
 * F.4.3.1 c: *"There must be an indication when data are stale."* La tabla F.5-1
 * le da color propio, el cian.
 *
 * LA REGLA YA NO VIVE AQUI. Este fichero decidia a partir de cuanto caducaba cada
 * dato, con tres plazos escritos a mano: una regla que cambia lo que la tripulacion
 * ve como vigente, fuera del backend y de su version de reglas. Ahora los plazos
 * estan en `backend/app/analysis/staleness.py`, entran en `rules_version`, y cada
 * estado trae el veredicto hecho (`freshness`). Aqui solo se lee; quien lo pinta pone el cian.
 */

import type { FreshnessVerdict } from "./api";

export type Freshness = FreshnessVerdict["state"];

const KNOWN: readonly Freshness[] = ["fresh", "stale", "missing"];

/**
 * El estado que dio el backend. Sin veredicto, o con uno que la interfaz no conoce,
 * es `missing`: tabla F.5-1, *"Missing or stale data"*. Lo que no se sabe si esta al
 * dia nunca se presenta como si lo estuviera.
 */
export function freshnessOf(verdict: FreshnessVerdict | null | undefined): Freshness {
  const state = verdict?.state;
  return state !== undefined && KNOWN.includes(state) ? state : "missing";
}
