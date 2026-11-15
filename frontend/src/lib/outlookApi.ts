/**
 * `GET /api/correlations` (`backend/app/analysis/correlations.py`): la correlación de Pearson de
 * los pares declarados de un tripulante, para «Correlación de variables» de la pestaña «Distancia y
 * nodos».
 *
 * Por qué existe aparte: los tipos de esta ruta no están en `lib/api.ts`, y ese fichero lo editan
 * otras sesiones (instrucciones del lote «reservas»); van aquí con su propia petición, como
 * `lib/inventoryApi.ts`. Todo texto (método, alcance, salvedades, la frase de cada par) es del
 * backend; la interfaz solo elige la marca y dibuja los puntos.
 */

import { ApiError, withConsoleHeader } from "./api";

export type CorrelationState = "computed" | "insufficient" | "constant";

/** Un lado del par: su clave del catálogo, su nombre, su unidad y sus decimales. */
export interface CorrelationSide {
  key: string;
  display_es: string;
  unit: string;
  decimals: number;
}

/** Un día con las dos medias diarias. */
export interface CorrelationPoint {
  day: string;
  x: number;
  y: number;
}

export interface CorrelationPair {
  x: CorrelationSide;
  y: CorrelationSide;
  /** El tema de la maqueta del que sale el par («nutrición y desempeño»). */
  theme: string;
  state: CorrelationState;
  /** Días emparejados en la ventana. */
  n: number;
  /** `null` salvo con `state === "computed"`. */
  r: number | null;
  ci_low: number | null;
  ci_high: number | null;
  points: CorrelationPoint[];
  /** Alguna lectura de la ventana es simulada: el r es el del modelo, no fisiología. */
  simulated: boolean;
  /** La frase del backend: el r con su intervalo y su n, o por qué no hay r. */
  text: string;
}

export interface Correlations {
  subject: string;
  reference_time: string;
  window_days: number;
  min_days: number;
  method: string;
  method_version: string;
  scope: string;
  multiple: string;
  pairs_basis: string;
  simulated_text: string;
  pairs: CorrelationPair[];
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (body.detail !== undefined) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // cuerpo no JSON: se queda el texto de estado
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

/** La búsqueda automática (`GET /api/correlations/search`): los pares de mayor |r|, y cuántos se miraron. */
export interface CorrelationSearch extends Correlations {
  domain: string | null;
  tested: number;
}

/**
 * La lectura del modelo local sobre la búsqueda (`POST /api/correlations/reading`): un borrador de
 * Clase C, no revisado, que no se guarda. `text` es `null` si no hay modelo o si una barrera la
 * bloqueó (`blocked` dice por qué); la interfaz enseña el texto tal cual, con su `label`.
 */
export interface CorrelationReading {
  subject: string;
  model: string;
  label: string;
  facts_sha256: string;
  pairs: number;
  available: boolean;
  text: string | null;
  blocked: string[];
  note: string | null;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(
    `/api${path}`,
    withConsoleHeader({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  );
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const parsed = (await response.json()) as { detail?: unknown };
      if (parsed.detail !== undefined) detail = typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
    } catch {
      // cuerpo no JSON: se queda el texto de estado
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export const outlookApi = {
  /** Con `until` (la referencia del estado), la ventana acaba ahí. */
  correlations: (subject: string, until: string | null) => {
    const params = new URLSearchParams({ subject });
    if (until !== null) params.set("until", until);
    return get<Correlations>(`/correlations?${params.toString()}`);
  },
  /** La búsqueda automática; con `domain`, solo los pares que tocan ese dominio. */
  search: (subject: string, until: string | null, domain: string | null) => {
    const params = new URLSearchParams({ subject });
    if (until !== null) params.set("until", until);
    if (domain !== null) params.set("domain", domain);
    return get<CorrelationSearch>(`/correlations/search?${params.toString()}`);
  },
  /** Pide la lectura al modelo local: las cifras se recalculan en el backend, no se envían. */
  reading: (subject: string, until: string | null, domain: string | null) =>
    post<CorrelationReading>("/correlations/reading", { subject, until, domain }),
};
