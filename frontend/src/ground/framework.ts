/**
 * El marco de NASA y las hipótesis de diseño, ordenados para leerlos.
 *
 * Por qué existe aparte del panel: lo que aquí se puede equivocar es lógica, no pintura. Una
 * hipótesis pintada con el pictograma o el color de «conforme» diría que está probada, y ninguna
 * lo está; un anclaje que nadie ha leído, pintado como un dato cualquiera, pasaría por evidencia.
 * Está en un `.ts` para que lo pruebe `framework.test.ts`.
 *
 * Nada de aquí redacta: el enunciado, la frase de cada estado, lo que EMMA no demuestra y los
 * textos del marco son los de `GET /api/framework`. Aquí solo se eligen pictograma y color
 * (`lib/marks.ts`), se agrupa y se cuenta. Es un inventario, no un estado clínico: nada de esto
 * decide sobre la tripulación.
 */

import type { PictogramName } from "../icons/registry";
import type {
  DesignHypotheses,
  DesignHypothesisTouch,
  Framework,
  GapStatus,
  ReadBlock,
  ReadSources,
} from "../lib/api";
import { type StateMark, MISSING_MARK, UNKNOWN_MARK, mark, prefixedPictogram } from "../lib/marks";

/**
 * Un pictograma por estado, para distinguirlos sin color (F.5.10 e). Ninguno es el de un nivel
 * de riesgo (`lib/levels.ts`) ni una marca de «hecho»: son grados de cuánto se ha ejercitado una
 * hipótesis —un marco vacío, un cuarto, la mitad— y el más alto sigue sin ser «probada».
 *
 * Solo «fuera de EMMA» lleva color, el gris de «no disponible»: aquí no hay pieza que mirar.
 */
const STATUS_MARKS: Record<string, StateMark> = {
  architecture: mark("parallelogram", null),
  simulated: mark("circle-quarter", null),
  "partly-real-data": mark("circle-half-right", null),
  outside: mark("slash-circle", "gray"),
};

/**
 * Un estado que la interfaz no conoce se enseña con su frase y la marca única de «desconocido»
 * (`lib/marks.ts`: punto, texto normal), la misma que un dominio, un peligro o un indicador sin
 * dibujo: no se le supone grado.
 */
export const UNKNOWN_STATUS: StateMark = UNKNOWN_MARK;

export function statusStyle(status: string): StateMark {
  return STATUS_MARKS[status] ?? UNKNOWN_STATUS;
}

/** «Sin leer» es un dato que falta: cian (F.5-1, *missing or stale data*), con su anillo punteado. */
export const UNREAD_STYLE: StateMark = MISSING_MARK;

export interface StatusCount {
  id: string;
  text: string;
  count: number;
}

/**
 * Cuántas hipótesis hay en cada estado, en el orden del backend y sin callar los vacíos: que
 * ningún estado diga «probada» se ve en la lista entera, no solo en los que tienen alguna.
 * Una hipótesis con un estado que el backend no declara se cuenta aparte, con su propia frase.
 */
export function countByStatus(inventory: DesignHypotheses): StatusCount[] {
  const counts: StatusCount[] = inventory.statuses.map(({ id, text }) => ({ id, text, count: 0 }));
  for (const item of inventory.hypotheses) {
    let row = counts.find((candidate) => candidate.id === item.status);
    if (row === undefined) {
      row = { id: item.status, text: item.status_text, count: 0 };
      counts.push(row);
    }
    row.count += 1;
  }
  return counts;
}

export interface RidgeGroup {
  hazard: string;
  display: string;
  /** Claves de dominio de la API, en el orden en que las da el backend. */
  domains: string[];
}

/** Los dominios de cada peligro RIDGE, en el orden en que el backend los nombra por primera vez. */
export function ridgeGroups(ridge: Framework["ridge"]): RidgeGroup[] {
  const groups: RidgeGroup[] = [];
  for (const [domain, { hazard, display }] of Object.entries(ridge)) {
    let group = groups.find((candidate) => candidate.hazard === hazard);
    if (group === undefined) {
      group = { hazard, display, domains: [] };
      groups.push(group);
    }
    group.domains.push(domain);
  }
  return groups;
}

/**
 * El pictograma de un peligro RIDGE (`icons/sets/domains.ts`, `ridge-<clave>`), para ponerlo junto
 * a su nombre, que es el del backend. Un peligro que la interfaz no conoce lleva el dibujo de
 * «desconocido», no uno supuesto.
 */
export function ridgePictogram(hazard: string): PictogramName {
  return prefixedPictogram("ridge", hazard);
}

export interface GapRow {
  /** Clave del hueco en la API. */
  key: string;
  /** Nombre del hueco tal como lo da el backend; la interfaz no lo escribe. */
  label: string;
  gap: string;
  /** Estado leído en el Human Research Roadmap: va siempre junto al nombre. */
  status: GapStatus;
  /** El hueco en que se fusionó, con su propio estado; `null` si no se fusionó en ninguno. */
  mergedInto: GapStatus | null;
  emma: string;
}

/**
 * Los dos huecos del MDA, con su enunciado de 2020, su estado leído y lo que EMMA dice de ellos.
 *
 * Undécima ronda: el nombre de cada hueco se escribía aquí y su estado no viajaba con él, así que
 * la pantalla los presentaba como abiertos aunque el Roadmap publica uno cerrado y otro
 * fusionado. Ahora nombre y estado llegan juntos del backend.
 */
export function gapRows(gaps: Framework["exmc_gaps"]): GapRow[] {
  return [
    { key: "med07", ...gaps.med07, mergedInto: null },
    {
      key: "med10",
      label: gaps.med10.label,
      gap: gaps.med10.gap,
      status: gaps.med10.status,
      mergedInto: gaps.med10.merged_into,
      emma: gaps.med10.emma,
    },
  ];
}

/**
 * Un pictograma por estado de hueco, para distinguirlos sin color (F.5.10 e): anillo doble,
 * anillo barrado, flecha con horquilla, rectángulo tendido y horca. Ninguno lleva color: el estado
 * de un hueco de NASA no es un dato caducado ni un nivel de riesgo, y ninguno es una marca de
 * «hecho» que se pudiera leer como mérito de EMMA.
 */
const GAP_STATUS_MARKS: Record<string, StateMark> = {
  open: mark("circle-double", null),
  closed: mark("circle-backslash", null),
  merged: mark("arrow-right-forked", null),
  archived: mark("rect-wide", null),
  split: mark("pitchfork", null),
};

/** Un estado de hueco que la interfaz no conoce se enseña con su frase, sin suponerlo abierto. */
export function gapStatusStyle(status: string): StateMark {
  return GAP_STATUS_MARKS[status] ?? UNKNOWN_STATUS;
}

/**
 * Cuánto se leyó de un documento: el marco con su contenido, con la mitad, o vacío. Solo «la
 * ficha y el resumen» lleva color, el cian de dato ausente (F.5-1): del documento falta casi
 * todo. Ninguno es una marca de «conforme»: haber leído una fuente no dice nada de EMMA.
 */
const EXTENT_MARKS: Record<string, StateMark> = {
  full: mark("frame-filled", null),
  partial: mark("square-half", null),
  record: mark("frame-empty", "cyan"),
};

/** Un alcance que la interfaz no conoce se enseña con su frase y sin suponerle una lectura entera. */
export function extentStyle(extent: string): StateMark {
  return EXTENT_MARKS[extent] ?? UNKNOWN_STATUS;
}

/**
 * Dónde va cada bloque de lo leído. Los que completan un apartado que el panel ya tenía se
 * pintan junto a él; **todo lo demás va después, en el orden del backend**, también un bloque
 * que la interfaz no conozca: lo leído no se pierde por no tener sitio asignado.
 */
export const BLOCK_BESIDE = {
  gaps: "exmc-gaps-today",
  imm: "imm-limitations",
  /** MEDPRAT e IMPACT, lo que vino después del IMM: va detrás de sus limitaciones. */
  medprat: "medprat",
} as const;

export interface PlacedBlocks {
  gaps: ReadBlock | null;
  imm: ReadBlock | null;
  medprat: ReadBlock | null;
  rest: ReadBlock[];
}

export function placeBlocks(read: ReadSources): PlacedBlocks {
  const find = (id: string) => read.blocks.find((block) => block.id === id) ?? null;
  const beside: string[] = Object.values(BLOCK_BESIDE);
  return {
    gaps: find(BLOCK_BESIDE.gaps),
    imm: find(BLOCK_BESIDE.imm),
    medprat: find(BLOCK_BESIDE.medprat),
    rest: read.blocks.filter((block) => !beside.includes(block.id)),
  };
}

/**
 * La palabra de cada cobertura de una tabla de lo leído (decimoséptima ronda: el CDSS de ExMC,
 * punto por punto), como la da el backend, para `coverageRows` de `hrpCoverageMarks.ts`: la
 * marca es la misma que en los riesgos del HRP —«cubre», la diana; «en parte», la mitad; «no», el
 * gris tachado de fuera de EMMA—, para no darle a un dibujo un segundo significado. Una clave
 * repetida no pisa la primera.
 */
export function coverageDisplay(read: Pick<ReadSources, "coverages">): Record<string, string> {
  const display: Record<string, string> = {};
  for (const { id, text } of read.coverages) {
    if (!Object.hasOwn(display, id)) display[id] = text;
  }
  return display;
}

/** «GET /api/status», o `null` si la pieza no tiene ruta: no se inventa una. */
export function routeText(touch: DesignHypothesisTouch): string | null {
  return touch.route === null || touch.method === null ? null : `${touch.method} ${touch.route}`;
}
