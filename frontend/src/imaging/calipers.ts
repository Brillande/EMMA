/**
 * Calibres guiados: que marca toca ahora, cuantos puntos lleva, y la peticion que resulta.
 *
 * Por que es logica aparte y no estado del componente: el orden de las marcas y cuando una
 * esta completa deciden que medida se envia. Aqui se prueba sin navegador. La interfaz no
 * valida la medida —profundidad, perpendicularidad, region calibrada—: eso lo hace el
 * backend, que es quien la firma, y su motivo de rechazo se muestra tal cual.
 */

import type { MarkedAnnotation, MeasureSpec, MeasurementRequest } from "../lib/api";

export interface CaliperStep {
  label: string;
  /** Puntos exactos, o `null` si es un contorno que el operador cierra. */
  exact: number | null;
  minimum: number;
  instruction: string;
}

export interface CaliperState {
  steps: CaliperStep[];
  /** Indice de la marca en curso; igual a `steps.length` cuando todo esta marcado. */
  current: number;
  marks: Record<string, MarkedAnnotation>;
}

/** Las marcas de una medida, en el orden en que las declara el backend. */
export function stepsFor(spec: MeasureSpec, minContourPoints: number): CaliperStep[] {
  return Object.entries(spec.annotations).map(([label, count]) => ({
    label,
    exact: count > 0 ? count : null,
    minimum: count > 0 ? count : minContourPoints,
    instruction: spec.instructions[label] ?? "",
  }));
}

export function startCalipers(steps: CaliperStep[]): CaliperState {
  return { steps, current: 0, marks: {} };
}

export function currentStep(state: CaliperState): CaliperStep | null {
  return state.steps[state.current] ?? null;
}

export function isComplete(state: CaliperState): boolean {
  return state.current >= state.steps.length;
}

/**
 * Anade un punto a la marca en curso. Los puntos de una marca van en un solo fotograma:
 * si el operador cambia de fotograma a mitad de marca, la marca empieza de nuevo en el
 * nuevo, en vez de mezclar puntos de dos imagenes distintas.
 */
export function addPoint(state: CaliperState, point: [number, number], frame: number): CaliperState {
  const step = currentStep(state);
  if (step === null) return state;
  const previous = state.marks[step.label];
  const points = previous !== undefined && previous.frame === frame ? previous.points : [];
  const updated = { frame, points: [...points, point] };
  const marks = { ...state.marks, [step.label]: updated };
  const done = step.exact !== null && updated.points.length >= step.exact;
  return { ...state, marks, current: done ? state.current + 1 : state.current };
}

/** Cierra un contorno si ya tiene los puntos minimos. Una marca de puntos exactos no se cierra. */
export function closeContour(state: CaliperState): CaliperState {
  const step = currentStep(state);
  if (step === null || step.exact !== null) return state;
  const count = state.marks[step.label]?.points.length ?? 0;
  return count >= step.minimum ? { ...state, current: state.current + 1 } : state;
}

/** Quita el ultimo punto; si la marca en curso esta vacia, vuelve a la anterior. */
export function undo(state: CaliperState): CaliperState {
  let index = Math.min(state.current, state.steps.length - 1);
  let step = state.steps[index];
  if (step !== undefined && (state.marks[step.label]?.points.length ?? 0) === 0 && index > 0) {
    index -= 1;
    step = state.steps[index];
  }
  if (step === undefined) return state;
  const mark = state.marks[step.label];
  if (mark === undefined || mark.points.length === 0) return { ...state, current: index };
  const points = mark.points.slice(0, -1);
  const marks = { ...state.marks };
  if (points.length === 0) {
    delete marks[step.label];
  } else {
    marks[step.label] = { frame: mark.frame, points };
  }
  return { ...state, marks, current: index };
}

export function toRequest(
  state: CaliperState,
  measure: string,
  laterality: "right" | "left" | null,
  measuredBy: string,
): MeasurementRequest {
  if (!isComplete(state)) throw new Error("faltan marcas por completar");
  return { measure, laterality, annotations: state.marks, measured_by: measuredBy };
}

/**
 * Un clic en pantalla, en pixeles de la imagen original. La imagen se muestra escalada
 * para caber en el panel; medir en pixeles de pantalla daria milimetros falsos.
 */
export function toImagePoint(
  clientX: number,
  clientY: number,
  box: { left: number; top: number; width: number; height: number },
  imageWidth: number,
  imageHeight: number,
): [number, number] {
  const x = ((clientX - box.left) / box.width) * imageWidth;
  const y = ((clientY - box.top) / box.height) * imageHeight;
  const clamp = (value: number, max: number) => Math.min(Math.max(value, 0), max);
  return [round1(clamp(x, imageWidth)), round1(clamp(y, imageHeight))];
}

/** Decimas de pixel: mas fino no lo pone ninguna mano. */
function round1(value: number): number {
  return Math.round(value * 10) / 10;
}
