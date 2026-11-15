/**
 * El inventario de a bordo tal como lo sirve el backend (`GET /api/inventory`) y la declaración de
 * un recuento (`POST /api/inventory/count`).
 *
 * Por qué existe aparte de `lib/api.ts`: el lote «reservas» (2026-11-14) lo trabajan dos unidades a
 * la vez (la 1 el backend, la 2 el bloque de «Inicio») y `api.ts` lo editan muchas sesiones; los
 * tipos de este contrato viven aquí para no chocar. Reutiliza de `api.ts` lo que exporta: la
 * cabecera de la consola (`withConsoleHeader`) y el error con el motivo del backend (`ApiError`),
 * así un fallo se pinta con la misma marca que en el resto de la interfaz (`requestOutcome`).
 *
 * Decisión del usuario (2026-11-14): «Inventario real firmado». Las existencias las declara una
 * persona en la consola y quedan en el registro firmado (asiento `inventory-count`); la autonomía la
 * calcula el backend (`cantidad / consumo diario`, solo con consumo declarado), y lo que no se ha
 * declarado viene como `null`, nunca como cero. Aquí no se calcula ni se completa nada.
 */
import { ApiError, withConsoleHeader } from "./api";

/** Las tres categorías del contrato, en el orden de la maqueta. */
export const INVENTORY_CATEGORIES = ["medications", "food", "medical-equipment"] as const;
export type InventoryCategoryId = (typeof INVENTORY_CATEGORIES)[number];

/** Un artículo con su último recuento firmado. */
export interface InventoryItem {
  id: string;
  name: string;
  /** Familia declarada (p. ej. «antibiotic»): de ella salen las alternativas. */
  family: string | null;
  unit: string;
  quantity: number;
  /** Consumo diario declarado; `null` si nadie lo declaró. */
  daily_use: number | null;
  /** `quantity / daily_use`, del backend; `null` sin consumo declarado (o cero). */
  autonomy_days: number | null;
  /** Mínimo de días declarado para el artículo; sin él no hay umbral. */
  min_days: number | null;
  /** Autonomía por debajo del mínimo declarado; `null` si falta alguno de los dos. */
  critical: boolean | null;
  /** Otros artículos de la misma familia con existencias (sus `id`). */
  alternatives: string[];
  counted_at: string;
  declared_by: string;
  expires: string | null;
}

export interface InventoryTotals {
  units: number;
  kinds: number;
  critical: number;
  available: number;
  undeclared_use: number;
  min_autonomy_days: number | null;
}

export interface InventoryCategory {
  id: string;
  label: string;
  items: InventoryItem[];
  totals: InventoryTotals;
}

/** El próximo reabastecimiento declarado (asiento `inventory-resupply`). */
export interface InventoryResupply {
  name: string;
  eta: string;
  capacity_kg: number | null;
  declared_at: string;
  declared_by: string;
}

/** `GET /api/inventory`. */
export interface Inventory {
  categories: InventoryCategory[];
  resupply: InventoryResupply | null;
  /** Si hay al menos un recuento firmado. */
  declared: boolean;
}

/** `POST /api/inventory/count`: un recuento de un artículo, firmado por quien lo declara. */
export interface InventoryCountBody {
  category: string;
  item: string;
  name: string;
  unit: string;
  quantity: number;
  daily_use?: number;
  family?: string;
  min_days?: number;
  expires?: string;
  counted_at: string;
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

/** La ruta de lectura; con `until`, lo declarado hasta ese instante (el corte de reloj de Tierra). */
export function inventoryPath(until?: Date): string {
  return until === undefined ? "/inventory" : `/inventory?until=${encodeURIComponent(until.toISOString())}`;
}

export const inventoryApi = {
  get: (until?: Date) => call<Inventory>(inventoryPath(until)),
  /** Va con la cabecera de la consola (`withConsoleHeader` la pone en todo POST). */
  count: (body: InventoryCountBody) =>
    call<{ ledger_index: number }>("/inventory/count", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
};
