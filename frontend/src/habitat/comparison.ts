/**
 * De la respuesta de `/crew/compare` a lo que se dibuja: una grafica por tripulante.
 *
 * Por que existe aparte del componente: lo que hace comparable a dos personas se decide aqui, y
 * es facil estropearlo sin que se note en pantalla.
 *
 * - **Una escala vertical para todos.** Con una escala por grafica, una oscilacion de 2 /min en
 *   un tripulante llenaria su grafica igual que una de 20 en otro: se verian "iguales".
 * - **Se dibuja la diferencia con la linea base propia, no la lectura.** 70 /min es mucho para
 *   quien tiene su base en 55 y nada para quien la tiene en 68. Una lectura sin base personal
 *   no tiene diferencia que dibujar, y no se inventa (el backend la manda como `null`).
 * - **Nadie se distingue por color.** Todos los colores de `lib/palette.ts` significan algo
 *   (tabla F.5-1 de NASA-STD-3001 Vol 2): un tripulante en amarillo se leeria como precaucion.
 *   Cada uno va en su grafica, con su nombre encima.
 *
 * Aqui no se decide nada clinico: quien se desvia y con que palabras lo dice el backend.
 */

import type { ChartLine, Point, Span } from "../ground/TrendChart";
import type { CrewCompare, CrewOverview, HabitatExcursion, HabitatParameter } from "../lib/api";
import { missionElapsedSeconds } from "../lib/format";

/** Margen de la escala comun por arriba y por abajo, como fraccion de su amplitud. */
const PADDING = 0.08;

export interface CrewSeries {
  subject: string;
  /** Sin dato, sin lecturas en la ventana, dentro de lo esperado o desviandose. */
  state: CrewCompare["series"][number]["state"];
  /** Texto del backend para ese estado. */
  stateText: string;
  /** Texto del backend si ninguna lectura del tramo tiene linea base personal. */
  baselineText: string | null;
  /** Las frases que el estado de ese tripulante da como motivo, tal cual. */
  drivers: string[];
  /** Primera lectura fuera de lo esperado, en segundos de mision. Una deriva no tiene instante. */
  onsetMet: number | null;
  origins: { type: string; context: string | null }[];
  /** Texto del backend que cuenta lo inferido o predicho que no decide; null si no hay. */
  setAsideText: string | null;
  /** Lectura menos la mediana de su propia base. Vacia si no hay diferencia que dibujar. */
  points: Point[];
}

export interface CabinSeries {
  parameter: HabitatParameter;
  /** Texto del backend si no hay lecturas de cabina en el tramo. */
  stateText: string | null;
  evidenceContexts: string[];
  points: Point[];
  /** Sus limites normativos (`health`), con su requisito: cruzarlos es precaucion. */
  limits: ChartLine[];
  limitRequirements: string[];
  /** Tramos fuera de un limite normativo, y de cual. */
  excursions: Span[];
  excursionRequirements: string[];
}

export interface Comparison {
  /** Ultima lectura del indicador en la tripulacion, en segundos de mision. null: nadie tiene. */
  referenceMet: number | null;
  /** La escala vertical de todos los tripulantes. null si nadie tiene nada que dibujar. */
  range: [number, number] | null;
  crew: CrewSeries[];
  cabin: CabinSeries | null;
}

export function prepareComparison(compare: CrewCompare, missionStart: string): Comparison {
  const met = (iso: string) => missionElapsedSeconds(missionStart, new Date(iso));

  const crew: CrewSeries[] = compare.series.map((series) => ({
    subject: series.subject,
    state: series.state,
    stateText: series.state_text,
    baselineText: series.baseline_text,
    drivers: series.drivers,
    onsetMet: series.onset === null ? null : met(series.onset),
    origins: series.origins,
    setAsideText: series.set_aside_text ?? null,
    points: series.points.flatMap((point) =>
      point.delta === null ? [] : [{ met: met(point.effective), value: point.delta }],
    ),
  }));

  return {
    referenceMet: compare.reference_time === null ? null : met(compare.reference_time),
    range: commonRange(crew),
    crew,
    cabin: compare.habitat === null ? null : cabinSeries(compare.habitat, met),
  };
}

/**
 * La misma escala para todos, con el cero —la linea base de cada uno— siempre dentro. Sin el
 * cero a la vista no se sabria hacia que lado se aparta cada serie.
 */
function commonRange(crew: readonly CrewSeries[]): [number, number] | null {
  let low = 0;
  let high = 0;
  let any = false;
  for (const member of crew) {
    for (const point of member.points) {
      any = true;
      if (point.value < low) low = point.value;
      if (point.value > high) high = point.value;
    }
  }
  if (!any) return null;
  // Todas las series planas sobre su base: una amplitud de 1 evita una escala de altura cero.
  const pad = (high - low || 1) * PADDING;
  return [low - pad, high + pad];
}

function cabinSeries(
  habitat: NonNullable<CrewCompare["habitat"]>,
  met: (iso: string) => number,
): CabinSeries {
  // Solo los limites normativos: son los unicos que cuentan como excursion para una causa
  // compartida. La zona de confort ya la da la tabla de atmosfera de cabina.
  const health = habitat.parameter.limits.filter((limit) => limit.kind === "health");
  const limits: ChartLine[] = health.flatMap((limit) =>
    [limit.low, limit.high].flatMap((value) =>
      value === null ? [] : [{ value, tone: "yellow" as const, dashed: false }],
    ),
  );
  const out = habitat.excursions.filter((item) => item.kind === "health");
  return {
    parameter: habitat.parameter,
    stateText: habitat.state_text,
    evidenceContexts: habitat.evidence_contexts,
    points: habitat.points.map((point) => ({ met: met(point.effective), value: point.value })),
    limits,
    limitRequirements: [...new Set(health.map((limit) => limit.requirement))],
    excursions: out.map((item) => ({ from: met(item.start), to: met(item.end) })),
    excursionRequirements: [...new Set(out.map((item) => item.requirement))],
  };
}

/** En cuantos tripulantes da hallazgo cada indicador, segun `/crew`. */
export function findingCounts(crew: CrewOverview["crew"]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const member of crew) {
    for (const key of member.indicators) counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}

/**
 * Que comparar primero: el indicador con hallazgo en mas tripulantes —lo que mas se parece a
 * un cambio compartido—; a igualdad, el que va antes en el catalogo. Sin hallazgos, el primero
 * del catalogo. `null` mientras no hay catalogo.
 */
export function suggestedIndicator(
  crew: CrewOverview["crew"],
  catalog: readonly string[],
): string | null {
  const counts = findingCounts(crew);
  let best: string | null = null;
  for (const key of catalog) {
    const count = counts.get(key) ?? 0;
    if (count > 0 && (best === null || count > (counts.get(best) ?? 0))) best = key;
  }
  return best ?? catalog[0] ?? null;
}

/**
 * Que parametro de cabina poner al lado: el de una excursion de limite normativo vigente, que
 * es lo primero que habria que mirar. Sin excursion no se propone ninguno.
 */
export function suggestedParameter(
  excursions: readonly HabitatExcursion[],
  known: readonly string[],
): string | null {
  return excursions.find((item) => known.includes(item.parameter))?.parameter ?? null;
}
