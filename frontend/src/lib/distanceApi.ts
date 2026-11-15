/**
 * Las distancias por perfil (`GET /api/distances`, `backend/app/environment/distances.py`) y la
 * posición de la ISS (`GET /api/orbit/iss`), para la fila «Distancia y comunicaciones» de «Inicio».
 *
 * Por qué existe: los tipos de estas dos rutas no estaban en `lib/api.ts`, y ese fichero lo editan
 * otras sesiones (instrucciones del lote «reservas»): van aquí, con su propia petición, como
 * `planner/plannerApi.ts`. Todo texto (motivos, alcance, dónde pone el perfil a la tripulación) es
 * del backend; la interfaz solo elige la marca.
 */

import { ApiError } from "./api";

export type DistanceState = "available" | "not_applicable" | "missing";

/** Distancia geocéntrica de un cuerpo (centro a centro) y su tiempo de luz de ida. */
export interface BodyDistance {
  id: "moon" | "mars" | string;
  label: string;
  note: string;
  state: DistanceState;
  distance_km: number | null;
  one_way_seconds: number | null;
  source: string | null;
  /** El motivo cuando no hay cifra; `null` con cifra. */
  text: string | null;
}

/** El retardo con Tierra de un perfil: por su objetivo de efemérides, sin salir a la red. */
export interface EarthLink {
  state: DistanceState;
  target: string | null;
  distance_km: number | null;
  one_way_seconds: number | null;
  source: string | null;
  text: string;
}

export interface Distances {
  profile: string;
  declared_profile: string;
  epoch: string;
  scope: string;
  observer: string;
  spice: { available: boolean; reason: string | null; source: string | null };
  known: boolean;
  display: string | null;
  unknown_text: string | null;
  /** Dónde pone el perfil a la tripulación; `body` `null` en ruta (no se estima). */
  crew_place: { body: "earth" | "moon" | "mars" | null; text: string } | null;
  earth_link: EarthLink | null;
  bodies: BodyDistance[];
}

/** `GET /api/orbit/iss`: solo aplica con el perfil declarado `leo`; una efeméride, no telemetría. */
export interface IssOrbit {
  mission_profile: string;
  applies: boolean;
  available: boolean;
  reason?: string;
  kind?: string;
  age?: string;
  position?: { time: string; latitude: number; longitude: number; radial_km: number };
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

/** El día UTC (AAAA-MM-DD) de un instante ISO, el de las efemérides diarias; `null` si no se lee. */
export function epochOf(iso: string): string | null {
  const at = Date.parse(iso);
  return Number.isFinite(at) ? new Date(at).toISOString().slice(0, 10) : null;
}

export const distanceApi = {
  get: (profile: string, epoch: string | null) => {
    const params = new URLSearchParams({ profile });
    if (epoch !== null) params.set("epoch", epoch);
    return get<Distances>(`/distances?${params.toString()}`);
  },
  iss: () => get<IssOrbit>("/orbit/iss"),
};
