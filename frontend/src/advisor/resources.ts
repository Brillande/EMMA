/**
 * Lo poco que la interfaz decide por si misma de los recursos de a bordo: con que pictograma y
 * que color se pinta cada estado, que dibujo acompana al nombre de cada recurso, que se ensena
 * junto a una recomendacion y que se manda al firmar.
 *
 * Por que existe: EMMA no lleva inventario; una persona declara que un recurso esta o no esta
 * disponible y el backend lo entrega con su rotulo, sus nombres y sus frases
 * (`core/resources.py`). La interfaz no redacta nada de eso. Lo que si elige —la marca— tiene
 * reglas que merecen prueba:
 *
 * - «Sin declarar» es un dato AUSENTE (cian, anillo punteado; tabla F.5-1), nunca la marca de
 *   «disponible». De un recurso del que nadie ha dicho nada no se sabe si esta a bordo.
 * - «Declarado no disponible» va en gris, que en la tabla F.5-1 significa exactamente eso
 *   («Unavailable»). No es amarillo ni rojo: no es una alerta ni mueve ninguna, y la
 *   contramedida se sigue ofreciendo.
 * - El color nunca va solo: pictograma propio de cada estado (`lib/marks.ts`) y la palabra del
 *   backend.
 * - Un estado que esta version no conoce se pinta sin significado, con su palabra, en vez de
 *   disfrazarse de otro. Y un bloque que llega sin sus filas no se pinta: no se inventa.
 * - El bloque va plegado en la tarjeta, pero lo que falta no se pliega: el resumen lleva la marca
 *   y la palabra de todo estado que no sea «declarado disponible» (`summaryMarks`), y el rotulo
 *   del bloque lleva la forma del peor estado presente (`statusPictogram`), sin color: el color
 *   lo ponen las palabras de estado que van detras.
 * - El rotulo y la advertencia se dicen una vez por lista, no en cada tarjeta
 *   (`resourceClarification`).
 * - Cada recurso del vocabulario cerrado tiene un dibujo de familia (`resourcePictogram`): el
 *   dibujo acompana al nombre del backend, nunca lo sustituye, y una clave que esta version no
 *   conoce sale con el dibujo de «desconocido». La paridad con el vocabulario tiene prueba.
 */

import type { PictogramName } from "../icons/registry";
import type { Recommendation, ResourceRow, ResourcesOverview } from "../lib/api";
import { type StateMark, UNKNOWN_MARK, UNKNOWN_PICTOGRAM, mark } from "../lib/marks";

export type { StateMark } from "../lib/marks";

/** El dibujo de cada estado: hecho, circulo tachado, anillo punteado. Una sola vez. */
const STATE_PICTOGRAMS = {
  available: "check",
  unavailable: "slash-circle",
  undeclared: "ring-dotted",
} as const satisfies Record<string, PictogramName>;

const MARKS: Record<string, StateMark> = {
  available: mark(STATE_PICTOGRAMS.available, "text"),
  unavailable: mark(STATE_PICTOGRAMS.unavailable, "gray"),
  undeclared: mark(STATE_PICTOGRAMS.undeclared, "cyan"),
};

/** La marca de un estado. Uno desconocido no lleva significado: lo dice la palabra del backend. */
export function stateMark(state: string): StateMark {
  return MARKS[state] ?? UNKNOWN_MARK;
}

/**
 * La forma del bloque de recursos de una recomendacion (`resource_status.state`): la del peor
 * estado presente, el mismo dibujo que lleva ese estado en cada fila (derivado, no copiado). Sin
 * color aqui. «No pide recursos» es el guion de «no aplica».
 */
const STATUS_PICTOGRAMS: Record<string, PictogramName> = {
  "none-required": "dash",
  "all-available": STATE_PICTOGRAMS.available,
  "some-undeclared": STATE_PICTOGRAMS.undeclared,
  "some-unavailable": STATE_PICTOGRAMS.unavailable,
};

export function statusPictogram(state: string): PictogramName {
  return STATUS_PICTOGRAMS[state] ?? UNKNOWN_PICTOGRAM;
}

/**
 * Familia de cada recurso del vocabulario (`backend/app/data/resources.json`), por su clave. Un
 * dibujo por familia, no por recurso: las tres masas de blindaje comparten el muro, los tres
 * sensores el sensor, el operador y el medico el busto. Lo que ya tenia dibujo en otro conjunto
 * lo reutiliza: una familia, un dibujo.
 */
const RESOURCE_PICTOGRAMS: Record<string, PictogramName> = {
  "treadmill-or-cycle-ergometer": "dumbbell",
  ared: "dumbbell",
  "intake-log": "notebook",
  "clinical-diary": "notebook",
  "same-sensor": "sensor-arcs",
  "second-sensor-or-manual-instrument": "sensor-arcs",
  "second-co2-sensor-or-portable-analyzer": "sensor-arcs",
  "shift-planning": "calendar-grid",
  "activity-replanning": "calendar-grid",
  "adjustable-module-lighting": "bulb",
  "onboard-pvt-test": "stopwatch",
  "comms-window": "antenna-dish",
  "shielded-area": "wall-bricks",
  "stowage-water-food-as-shielding": "wall-bricks",
  "module-with-more-shielding-mass": "wall-bricks",
  "personal-dosimeter": "badge-dot",
  accelerometer: "arrows-three-axes",
  "cleaning-supplies": "spray-bottle",
  "saliva-sample-kit": "vial",
  "ultrasound-scanner": "probe-arcs",
  "trained-operator": "person",
  "onboard-physician": "person",
  "pain-body-map": "figure-dot",
  "onboard-drinking-water": "cup-line",
  "urine-24h-collection": "bottle-marks",
  "onboard-food-inventory": "fork-knife",
  "environmental-control-system": "wind-curls",
};

/** El dibujo de familia de un recurso. Una clave desconocida sale con el de «desconocido». */
export function resourcePictogram(key: string): PictogramName {
  return RESOURCE_PICTOGRAMS[key] ?? UNKNOWN_PICTOGRAM;
}

/** Las claves con dibujo propio, para la prueba de paridad con el vocabulario del backend. */
export function resourceKeysWithPictogram(): readonly string[] {
  return Object.keys(RESOURCE_PICTOGRAMS);
}

export interface ResourceLine {
  key: string;
  /** La clave del estado, tal y como la da el backend. */
  state: string;
  /** El texto con que la contramedida nombra el recurso, tal y como lo da el backend. */
  description: string;
  /** El dibujo de familia del recurso, que acompana a `description`. */
  pictogram: PictogramName;
  /** «sin declarar», «declarado no disponible»…: palabra del backend. */
  stateDisplay: string;
  mark: StateMark;
  /** La nota de quien lo declaro, si la hay. */
  note: string | null;
}

export interface ResourceStatusView {
  /** «declarado por una persona; EMMA no lleva inventario». Va SIEMPRE con el bloque. */
  label: string;
  /** Que consta como no disponible o sin declarar, en una frase del backend. */
  text: string;
  /** La forma del peor estado presente, para el rotulo del bloque plegado. */
  statusPictogram: PictogramName;
  lines: ResourceLine[];
  /** Sin declarar no es disponible, y la contramedida se ofrece igual. `null` si no aplica. */
  caveat: string | null;
  /**
   * Lo que el resumen del bloque plegado ensena SIN abrirlo: la marca y la palabra de cada estado
   * que no sea «declarado disponible», lo no disponible primero.
   */
  summaryMarks: SummaryMark[];
  /**
   * Los recursos que no constan ni disponibles ni sin declarar y que la frase del resumen no
   * nombra: se pintan fuera del desplegable. Con el backend de hoy esta vacio (la frase nombra
   * todo lo no disponible); existe para que un recurso que falta no dependa de esa frase.
   */
  exposed: ResourceLine[];
}

export interface SummaryMark {
  state: string;
  /** La palabra del backend para ese estado. */
  stateDisplay: string;
  mark: StateMark;
}

const AVAILABLE = "available";
const UNAVAILABLE = "unavailable";
const UNDECLARED = "undeclared";

/**
 * Una marca por cada estado presente que no sea «declarado disponible». Lo declarado no
 * disponible va primero y lo sin declarar al final; un estado que esta version no conoce
 * (un «agotado» futuro) se ensena tambien, con su palabra: lo que falta no se pliega.
 */
export function summaryMarks(lines: readonly ResourceLine[]): SummaryMark[] {
  const rank = (state: string) => (state === UNAVAILABLE ? 0 : state === UNDECLARED ? 2 : 1);
  const seen = new Map<string, SummaryMark>();
  for (const line of lines) {
    if (line.state === AVAILABLE || seen.has(line.state)) continue;
    seen.set(line.state, { state: line.state, stateDisplay: line.stateDisplay, mark: line.mark });
  }
  return [...seen.values()]
    .map((item, index) => ({ item, index }))
    .sort((a, b) => rank(a.item.state) - rank(b.item.state) || a.index - b.index)
    .map(({ item }) => item);
}

/** Lo que falta (ni disponible ni sin declarar) y la frase del backend no nombra. */
export function exposedLines(lines: readonly ResourceLine[], text: string): ResourceLine[] {
  return lines.filter(
    (line) =>
      line.state !== AVAILABLE && line.state !== UNDECLARED && !text.includes(line.description),
  );
}

/**
 * El estado de los recursos que pide la contramedida de una recomendacion (`resource_status`).
 *
 * Aqui solo se ordena lo que se pinta. `null` (no se pinta nada) si la recomendacion no lleva
 * el bloque, si la contramedida no pide recursos, o si el bloque llega sin su rotulo: lo
 * declarado sin decir que es una declaracion se leeria como un inventario.
 */
export function resourceStatus(item: Recommendation): ResourceStatusView | null {
  const status = item.resource_status ?? null;
  if (status === null || status.items.length === 0) return null;
  const label = status.label?.trim() ?? "";
  if (label === "") return null;
  const lines = status.items.map((row) => ({
    key: row.key,
    state: row.state,
    description: row.description,
    pictogram: resourcePictogram(row.key),
    stateDisplay: row.state_display,
    mark: stateMark(row.state),
    note: row.note,
  }));
  return {
    label,
    text: status.text,
    statusPictogram: statusPictogram(status.state),
    lines,
    caveat: status.caveat,
    summaryMarks: summaryMarks(lines),
    exposed: exposedLines(lines, status.text),
  };
}

export interface ResourceClarification {
  /** «declarado por una persona; EMMA no lleva inventario». */
  labels: string[];
  /** «Sin declarar no es disponible… La contramedida se ofrece igual…». */
  caveats: string[];
}

/**
 * La aclaracion de los recursos, UNA vez para toda una lista de recomendaciones.
 *
 * Por que existe: el rotulo y la advertencia son los mismos en cada tarjeta, y repetidos enteros
 * en todas hacian de la consola una pared de texto. Se dicen una vez en la cabecera de la lista.
 * Se recogen los textos DISTINTOS que manda el backend, no «el primero»: si un dia una
 * recomendacion trae otra advertencia, tambien se ve. `null` si ninguna lleva bloque de recursos.
 */
export function resourceClarification(items: readonly Recommendation[]): ResourceClarification | null {
  const labels = new Set<string>();
  const caveats = new Set<string>();
  for (const item of items) {
    const view = resourceStatus(item);
    if (view === null) continue;
    labels.add(view.label);
    const caveat = view.caveat?.trim() ?? "";
    if (caveat !== "") caveats.add(caveat);
  }
  if (labels.size === 0) return null;
  return { labels: [...labels], caveats: [...caveats] };
}

export interface PanelRow {
  resource: ResourceRow;
  /** El dibujo de familia, que acompana al nombre del recurso. */
  pictogram: PictogramName;
  mark: StateMark;
}

/**
 * Las filas del panel: primero lo declarado no disponible, despues lo declarado disponible y
 * al final lo que esta sin declarar, cada grupo en el orden del vocabulario.
 */
export function panelRows(overview: Pick<ResourcesOverview, "resources">): PanelRow[] {
  const rank = (state: string) => (state === "unavailable" ? 0 : state === "available" ? 1 : 2);
  return overview.resources
    .map((resource, index) => ({ resource, index }))
    .sort((a, b) => rank(a.resource.state) - rank(b.resource.state) || a.index - b.index)
    .map(({ resource }) => ({
      resource,
      pictogram: resourcePictogram(resource.key),
      mark: stateMark(resource.state),
    }));
}

export interface HistoryRow {
  item: ResourcesOverview["history"][number];
  /** El dibujo de familia del recurso declarado. */
  pictogram: PictogramName;
  /** La marca del estado que se declaro. */
  mark: StateMark;
}

/** El historial de declaraciones, en el orden del backend, cada una con sus dibujos. */
export function historyRows(overview: Pick<ResourcesOverview, "history">): HistoryRow[] {
  return overview.history.map((item) => ({
    item,
    pictogram: resourcePictogram(item.resource),
    mark: stateMark(item.state),
  }));
}

export interface ResourceForm {
  resource: string;
  state: string;
  note: string;
}

export const EMPTY_FORM: ResourceForm = { resource: "", state: "", note: "" };

/** Se puede firmar con un recurso, un estado y el nombre de quien declara. La nota es opcional. */
export function canDeclare(form: ResourceForm, operator: string | undefined): boolean {
  return form.resource !== "" && form.state !== "" && (operator ?? "").trim() !== "";
}

export interface ResourceBody {
  resource: string;
  state: string;
  since: string;
  note: string;
  declared_by: string;
}

/** El cuerpo de la declaracion. Sin cantidades: no hay campo para ellas. */
export function declarationBody(form: ResourceForm, operator: string, since: string): ResourceBody {
  return {
    resource: form.resource,
    state: form.state,
    since,
    note: form.note.trim(),
    declared_by: operator.trim(),
  };
}

/**
 * El instante desde el que vale la declaracion: el de los datos si lo hay, porque una mision
 * simulada no vive en el reloj del ordenador; si no, ahora.
 */
export function declarationInstant(referenceTime: string | null, now: Date): string {
  return referenceTime ?? now.toISOString();
}
