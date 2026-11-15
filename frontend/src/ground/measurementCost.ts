/**
 * El coste de medir con sus dimensiones, ordenado para leerlo.
 *
 * Por qué existe aparte del panel: lo que aquí se puede equivocar es lógica. Un «sin clasificar»
 * pintado como una clase más pasaría por un dato, y es justo lo contrario: lo que el repositorio
 * no dice. Va en cian con su anillo punteado (tabla F.5-1: dato ausente), y lo decide la clave
 * que el backend declara como «sin clasificar», no una palabra escrita aquí.
 *
 * Nada de aquí redacta: el nombre de cada dimensión, el de cada clase y el texto que la sostiene
 * son los de `GET /api/measurement-cost` y `GET /api/indicators`. Aquí solo se agrupa y se elige
 * pictograma y color (`lib/marks.ts`). Cada clase de medida y cada valor de dimensión del backend
 * (`app/ingest/cost.py`: MODES, DIMENSIONS) tiene su dibujo; `measurementCost.test.ts` lee ese
 * fichero y exige uno por valor.
 */

import type { PictogramName } from "../icons/registry";
import type {
  CostDimension,
  CostKbCoverage,
  CostReading,
  CostReadingKind,
  CostRule,
  CostSummary,
  GroundDependence,
  Indicator,
} from "../lib/api";
import { costText } from "../lib/alertContext";
import { type StateMark, MISSING_MARK, UNKNOWN_PICTOGRAM, mark } from "../lib/marks";
import { UI_PICTOGRAMS } from "../lib/uiMarks";

/** Dato ausente: cian y anillo punteado (F.5-1). */
export const UNCLASSIFIED_STYLE: StateMark = MISSING_MARK;
/** Una clase asignada cuyo valor la interfaz no conoce: cuadrado pequeño, sin color que sugiera un estado. */
export const CLASSIFIED_STYLE: StateMark = mark("square-small", null);

/**
 * Un pictograma por clase de medida: onda continua (lo que un sensor registra solo), tomas
 * sueltas (periódico sin muestra), jeringa (periódico con muestra), matraz (laboratorio) y
 * sumatorio (calculado a partir de otras medidas).
 */
export const MODE_PICTOGRAMS: Readonly<Record<string, PictogramName>> = {
  "continuous-passive": "wave-smooth",
  "periodic-noninvasive": "dots-row",
  "periodic-invasive": "syringe",
  laboratory: "flask",
  derived: "sigma",
};

/** Una clase que la interfaz no conoce lleva el dibujo de «desconocido», no uno supuesto. */
export function modePictogram(mode: string): PictogramName {
  return MODE_PICTOGRAMS[mode] ?? UNKNOWN_PICTOGRAM;
}

/**
 * Un pictograma por valor de cada dimensión: dónde se procesa (chip, analizador de sobremesa,
 * globo de Tierra —el mismo que el entorno de evidencia «Tierra», porque es el mismo sitio—),
 * cuándo llega el resultado (destello, reloj de arena) y consumibles (cartucho, cartucho
 * tachado).
 */
export const VALUE_PICTOGRAMS: Readonly<Record<string, Readonly<Record<string, PictogramName>>>> = {
  processing: { "on-device": "chip", "onboard-analyzer": "box-slot", "ground-or-return": "globe" },
  result: { immediate: "star-four", deferred: "hourglass" },
  consumables: { none: "cartridge-slash", consumes: "cartridge" },
  // Decimosexta ronda (base de conocimiento §9). Una cifra leída lleva el dibujo de su magnitud
  // (bulto sobre una báscula, caja con su cota, toma de corriente); la calibración, una esfera con
  // la marca del cero; la guía desde Tierra, un trazo discontinuo que baja a un punto. Dibujos que
  // no significaban nada antes: la balanza es el peso corporal, la pesa trapezoidal una familia de
  // contramedida, y el cubo, el rayo, el manómetro y los arcos de señal ya eran otra cosa (un
  // dibujo, un significado). «No añade equipo propio» lleva el sumatorio de «calculado», porque es
  // lo mismo: se calcula de otras medidas.
  mass: { stated: "box-on-scale", "no-own-equipment": "sigma" },
  volume: { stated: "box-dimension", "no-own-equipment": "sigma" },
  power: { stated: "socket-round", "no-own-equipment": "sigma" },
  calibration: { required: "dial-needle", "no-own-equipment": "sigma" },
  // Decimoctava ronda: la formación antes de la misión, un birrete; la leída en un análogo en
  // Tierra, el mismo birrete sobre la línea del suelo, porque no es de vuelo.
  training: {
    "ground-guided": "line-dashed-to-dot",
    "station-trained": "mortarboard",
    "analog-trained": "mortarboard-on-ground",
    "no-own-equipment": "sigma",
  },
  // Decimonovena ronda (conversación de ideación ~673). El almacenamiento: el copo (la muestra se
  // congela a bordo), el tubo de muestra (espera a temperatura ambiente), el globo de Tierra (nada
  // que guardar a bordo: la medida se hace en Tierra, el mismo sitio que «requiere análisis en
  // Tierra») y el cilindro de datos (un volumen de datos leído). La frecuencia: la onda continua de
  // la clase «continuo y pasivo» (es lo mismo: registro continuo), la hoja de un día (continua por
  // periodos), el calendario (las sesiones de la misión) y el globo (solo en Tierra). La automatización, deducida de la clase: el sensor
  // (pasiva), la persona (con operador), el matraz de «laboratorio» (con muestra y análisis) y el
  // sumatorio (calculada). Lo calculado lleva el sumatorio en las tres, como en las demás.
  storage: {
    "sample-frozen-aboard": "snowflake",
    "sample-ambient-aboard": "vial",
    "nothing-aboard": "globe",
    stated: "cylinder-stack",
    "no-own-storage": "sigma",
  },
  frequency: {
    continuous: "wave-smooth",
    "continuous-in-periods": "calendar-day",
    "mission-timepoints": "calendar",
    "ground-only": "globe",
    "no-own-schedule": "sigma",
  },
  automation: {
    passive: "sensor-arcs",
    operator: "person",
    "sample-and-analysis": "flask",
    computed: "sigma",
  },
};

/**
 * Las dos listas del equipo con dónde tiene EMMA cada término: la base de conocimiento §9 y, desde
 * la decimonovena ronda, la conversación de ideación. En este orden, el del documento más antiguo;
 * las palabras son del backend.
 */
export function coverages(summary: CostSummary): CostKbCoverage[] {
  return [summary.kb_coverage, summary.conversation_coverage];
}

/**
 * La marca de un valor de dimensión: «sin clasificar» es la clave del backend y va en cian; un
 * valor conocido lleva su dibujo sin color; uno que la interfaz no conoce, la marca genérica de
 * clase asignada.
 */
export function valueMark(dimensionKey: string, value: string, summary: CostSummary): StateMark {
  if (value === summary.unclassified_value) return UNCLASSIFIED_STYLE;
  const pictogram = VALUE_PICTOGRAMS[dimensionKey]?.[value];
  return pictogram === undefined ? CLASSIFIED_STYLE : mark(pictogram, null);
}

export interface CostGroup {
  /** Clave de la clase en la API; el pictograma sale de ella. */
  mode: string;
  /** Nombre de la clase, del backend. */
  label: string;
  items: Indicator[];
}

/** Los indicadores con coste, agrupados por su clase de medida en el orden en que llegan. */
export function groupByMode(indicators: Indicator[]): CostGroup[] {
  const groups: CostGroup[] = [];
  for (const item of indicators) {
    if (item.measurement_cost === null) continue;
    const { mode, mode_display: label } = item.measurement_cost;
    let group = groups.find((candidate) => candidate.mode === mode);
    if (group === undefined) {
      group = { mode, label, items: [] };
      groups.push(group);
    }
    group.items.push(item);
  }
  return groups;
}

export interface DimensionCell {
  key: string;
  /** Nombre de la dimensión, del backend. */
  label: string;
  entry: CostDimension;
  style: StateMark;
}

/**
 * Las dimensiones de un indicador en el orden del resumen del backend. Una dimensión que el
 * indicador no trae no se inventa: se omite.
 */
export function dimensionCells(item: Indicator, summary: CostSummary): DimensionCell[] {
  const held = item.measurement_cost?.dimensions ?? {};
  const cells: DimensionCell[] = [];
  for (const dimension of summary.dimensions) {
    const entry = held[dimension.key];
    if (entry === undefined) continue;
    cells.push({
      key: dimension.key,
      label: dimension.display,
      entry,
      style: valueMark(dimension.key, entry.value, summary),
    });
  }
  return cells;
}

/**
 * Lo que se pinta de una dimensión de un indicador: una cifra leída (masa, volumen, potencia, volumen de datos) se
 * formatea aquí con `lib/format.ts`, con los decimales con que se leyó y su unidad tal cual; lo
 * demás es la palabra del backend.
 */
export function cellText(entry: CostDimension): string {
  return costText(entry);
}

/**
 * Las dimensiones de un indicador partidas en dos: las decididas, una por línea con su texto, y
 * las que siguen sin clasificar, juntas por su nombre. Con tantas dimensiones, cinco «sin clasificar»
 * en cinco líneas tapan lo que sí se sabe; juntas dicen lo mismo en una.
 */
export function splitCells(
  item: Indicator,
  summary: CostSummary,
): { classified: DimensionCell[]; unclassified: string[] } {
  const cells = dimensionCells(item, summary);
  return {
    classified: cells.filter((cell) => cell.entry.value !== summary.unclassified_value),
    unclassified: cells
      .filter((cell) => cell.entry.value === summary.unclassified_value)
      .map((cell) => cell.label),
  };
}

export interface CountRow {
  key: string;
  display: string;
  count: number;
  style: StateMark;
}

/** Las clases de una dimensión con su recuento, y «sin clasificar» al final, sin callarlo a cero. */
export function countRows(
  dimension: CostSummary["dimensions"][number],
  summary: CostSummary,
): CountRow[] {
  return [
    ...dimension.values.map((item) => ({
      key: item.value,
      display: item.display,
      count: item.count,
      style: valueMark(dimension.key, item.value, summary),
    })),
    {
      key: summary.unclassified_value,
      display: summary.unclassified_display,
      count: dimension.unclassified,
      style: UNCLASSIFIED_STYLE,
    },
  ];
}

/**
 * La lista de la base de conocimiento §9 es un documento del equipo: lleva el signo de la
 * documentación de la interfaz (`lib/uiMarks.ts`), no uno propio.
 */
export const KB_PICTOGRAM: PictogramName = UI_PICTOGRAMS.docs;

/**
 * «Hoy se sabe después» lleva el dibujo de «requiere retorno de la muestra o análisis en Tierra»:
 * es el mismo concepto (lo que depende de Tierra), y un concepto no tiene dos dibujos.
 */
export const GROUND_PICTOGRAM: PictogramName = VALUE_PICTOGRAMS.processing?.["ground-or-return"] ?? UNKNOWN_PICTOGRAM;

export interface NamedRow {
  key: string;
  /** Nombre en español del catálogo (`GET /api/indicators`); la clave, si el catálogo no lo trae. */
  displayEs: string;
}

export interface GroundRow extends NamedRow {
  /** Cuándo llega, palabra del backend. */
  result: string;
  /** Calculado que hereda de sus entradas: lleva el dibujo de «calculado». */
  inherited: boolean;
}

function nameOf(key: string, indicators: Indicator[]): string {
  return indicators.find((item) => item.key === key)?.display_es ?? key;
}

/** Lo que hoy depende de Tierra, en el orden del backend, con el nombre de cada indicador. */
export function groundRows(ground: GroundDependence, indicators: Indicator[]): GroundRow[] {
  return ground.indicators.map((item) => ({
    key: item.key,
    displayEs: nameOf(item.key, indicators),
    result: item.result,
    inherited: item.inherited_from !== null,
  }));
}

export interface SearchedRow {
  names: NamedRow[];
  dimensions: string;
  searched: string;
  searchedOn: string;
}

/** Lo buscado y no encontrado, con los nombres de sus indicadores. Va en cian: es lo que falta. */
export function searchedRows(summary: CostSummary, indicators: Indicator[]): SearchedRow[] {
  return summary.searched.map((item) => ({
    names: item.keys.map((key) => ({ key, displayEs: nameOf(key, indicators) })),
    dimensions: item.dimensions_display.join(" · "),
    searched: item.searched,
    searchedOn: item.searched_on,
  }));
}

/** Lo que sostiene una regla: la marca genérica de inventario, texto normal. */
export const SOURCE_STYLE: StateMark = mark("square-small", null);
/**
 * Lo que la matiza o contradice: el signo de «distinto» y SIN color. Una discrepancia leída no es
 * un estado del tripulante ni un dato caducado, y la tabla F.5-1 no le da ninguno.
 */
export const DISCREPANCY_STYLE: StateMark = mark("not-equal", null);

export interface ReadingSection {
  kind: CostReadingKind;
  /** Rótulo del backend. */
  label: string;
  style: StateMark;
  items: CostReading[];
}

export interface ReadRule {
  rule: CostRule;
  sections: ReadingSection[];
}

const READING_ORDER: CostReadingKind[] = ["sources", "discrepancies"];

/**
 * Las reglas que se apoyan en algo leído, con lo que las sostiene primero y lo que las matiza
 * después. Una regla sin lectura (se apoya en el propio repositorio) no sale aquí: su texto ya
 * va con cada indicador. Una sección vacía no se pinta, pero lo que matiza nunca se omite si
 * existe.
 */
export function readRules(summary: CostSummary): ReadRule[] {
  const out: ReadRule[] = [];
  for (const rule of summary.rules) {
    const sections = READING_ORDER.map((kind) => ({
      kind,
      label: summary.reading_display[kind],
      style: kind === "sources" ? SOURCE_STYLE : DISCREPANCY_STYLE,
      items: rule[kind] ?? [],
    })).filter((section) => section.items.length > 0);
    if (sections.length > 0) out.push({ rule, sections });
  }
  return out;
}
