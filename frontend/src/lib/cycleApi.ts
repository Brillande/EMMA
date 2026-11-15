/**
 * El último registro de cada indicador del ciclo y la anticoncepción, preparado para el panel del
 * ciclo (`cycle/CyclePanel.tsx`).
 *
 * Por qué existe aparte de `lib/api.ts`: el lote «ciclo» (2026-11-14) lo trabajan varias unidades a
 * la vez y `api.ts` lo editan muchas sesiones; lo del panel vive aquí para no chocar, como
 * `crewSexApi.ts`. Reutiliza lo que `api.ts` ya exporta.
 *
 * De dónde sale cada cosa, sin redactar nada:
 * - El nombre, la unidad y la palabra de cada número (`instrument.categories`, en el idioma de la
 *   fuente) los da el catálogo descriptivo (`GET /api/indicators/descriptive`, unidad A3).
 * - La lectura, `GET /api/observations?key=…&limit=1`, la misma ruta para las dos consolas: es la
 *   que admite `until`, el corte del retardo de Tierra (la de descriptivos no lo admite, y filtrar
 *   en la interfaz las diez últimas perdería lecturas anteriores al corte).
 * - Un número que la fuente no nombra (el 0 del sangrado intermenstrual, por ejemplo) se enseña
 *   como cifra, por `lib/format.ts`, nunca con una palabra puesta aquí.
 *
 * Caducado: ningún plazo de caducidad de estas lecturas vive en el backend, y la regla de cuándo
 * caduca un dato no se escribe en la interfaz (`lib/staleness.ts`). Así que «caducado» es lo que
 * la interfaz sí sabe: la última lectura del panel falló y lo pintado es lo de antes (cian, anillo
 * punteado y cursiva, tabla F.5-1). Un indicador sin ninguna lectura lleva la marca de dato ausente.
 */
import {
  type DescriptiveIndicator,
  type FhirObservation,
  api,
  indicatorsApi,
} from "./api";
import { formatNumber, formatUtc } from "./format";

/**
 * Las claves del ciclo, en el orden de `CYCLE_RECORDS` de `backend/app/ingest/codes.py` (unidad
 * A3). `cycle.test.ts` lo compara con ese fichero: una clave nueva allí hace fallar la prueba.
 */
export const CYCLE_KEYS = [
  "menstrual-flow",
  "menstruation-start",
  "intermenstrual-bleeding",
  "ovulation-test",
  "contraceptive-in-use",
  "basal-body-temperature",
] as const;
export type CycleKey = (typeof CYCLE_KEYS)[number];

/** La última lectura firmada de un indicador, tal como la sirve `/api/observations`. */
export interface CycleReading {
  effective: string;
  value: number;
}

/** Lo que el panel tiene de un indicador del ciclo: su ficha del catálogo y su última lectura. */
export interface CycleRecord {
  indicator: DescriptiveIndicator;
  latest: CycleReading | null;
}

/** Lo que pinta una fila del panel. */
export interface CycleRow {
  key: string;
  name: string;
  /** La palabra de la fuente para ese número; `null` si la fuente no lo nombra. */
  word: string | null;
  /** El idioma de la palabra (BCP 47), para marcarla en el HTML: no se traduce. */
  language: string | null;
  /** La cifra con su unidad, por `lib/format.ts`; con palabra, solo la cifra (el número de EMMA). */
  figure: string;
  /** El instante de la lectura, por `lib/format.ts`. */
  when: string;
}

export type CycleRowView = { key: string; name: string; empty: true } | ({ empty: false } & CycleRow);

/** `null` si la lectura no trae lo mínimo (fecha y valor): no se completa nada. */
export function readingOf(observation: FhirObservation | undefined): CycleReading | null {
  if (observation === undefined) return null;
  const value = observation.valueQuantity?.value;
  const effective = observation.effectiveDateTime;
  if (typeof value !== "number" || typeof effective !== "string") return null;
  // Una fecha ilegible no se pinta como hora (`formatUtc` lanzaría desde un render): falta.
  if (Number.isNaN(new Date(effective).getTime())) return null;
  return { effective, value };
}

/** La fila de un indicador: la palabra de su categoría si la fuente la da, y si no, la cifra. */
export function cycleRow(record: CycleRecord): CycleRowView {
  const { indicator, latest } = record;
  if (latest === null) return { key: indicator.key, name: indicator.display_es, empty: true };
  const category = indicator.instrument?.categories.find((item) => item.value === latest.value) ?? null;
  const number = formatNumber(latest.value, indicator.decimals);
  const unit = category === null ? indicator.unit_display : "";
  return {
    key: indicator.key,
    name: indicator.display_es,
    empty: false,
    word: category?.literal ?? null,
    language: category === null ? null : (indicator.instrument?.language ?? null),
    figure: unit === "" ? number : `${number} ${unit}`,
    when: formatUtc(new Date(latest.effective)),
  };
}

/** Las fichas del catálogo descriptivo que son del ciclo, en el orden de `CYCLE_KEYS`. */
export function cycleIndicators(indicators: readonly DescriptiveIndicator[]): DescriptiveIndicator[] {
  const byKey = new Map(indicators.map((item) => [item.key, item]));
  return CYCLE_KEYS.flatMap((key) => {
    const item = byKey.get(key);
    return item === undefined ? [] : [item];
  });
}

/** Las fichas del ciclo del catálogo descriptivo (no dependen del corte de Tierra). */
export async function loadCycleCatalog(subject: string): Promise<DescriptiveIndicator[]> {
  // `limit=1`: de aquí solo se usa el catálogo; las lecturas salen de `/observations`.
  const catalog = await indicatorsApi.descriptive(subject, 1);
  return cycleIndicators(catalog.indicators);
}

/**
 * La última lectura de cada indicador, todas a la vez; con `until`, lo que Tierra ya tiene en su
 * corte. Una petición que falla hace fallar el conjunto: medio panel con lo de antes y medio con
 * lo nuevo no diría cuál es cuál.
 */
export async function loadCycleRecords(
  subject: string,
  indicators: readonly DescriptiveIndicator[],
  until?: Date,
): Promise<CycleRecord[]> {
  const cut = until?.toISOString();
  return Promise.all(
    indicators.map(async (indicator) => {
      const body = await api.observations(indicator.key, 1, subject, cut);
      return { indicator, latest: readingOf(body.observations[0]) };
    }),
  );
}
