/**
 * Las cadenas de EPM y Biolab, con la marca de cada eslabón y de su estado.
 *
 * Por qué existe aparte del panel: lo que aquí se puede equivocar es lógica, no pintura. Un
 * eslabón que no se encontró pintado con la marca de lo leído diría que hay fuente donde no la
 * hay; uno leído en parte pintado como leído entero callaría su hueco. Está en un `.ts` para que
 * lo pruebe `facilities.test.ts`.
 *
 * Nada de aquí redacta: el rótulo de cada eslabón, su estado («leído en la fuente», «sin
 * verificar: buscado y no encontrado»), las frases, lo que falta y dónde se buscó son de
 * `GET /api/facilities`. Aquí solo se elige el signo (`lib/marks.ts`, `lib/uiMarks.ts`). Es un
 * inventario: nada de esto decide sobre la tripulación.
 */

import type { PictogramName } from "../icons/registry";
import { type StateMark, MISSING_MARK, UNKNOWN_MARK, UNKNOWN_PICTOGRAM, mark } from "../lib/marks";
import { type Sign, uiPictogram } from "../lib/uiMarks";

/**
 * El dibujo de las instalaciones: el matraz del laboratorio, el mismo que lleva «laboratorio» en
 * el coste de medir y en el hábitat. EPM y Biolab son laboratorios de Columbus.
 */
export const FACILITIES_PICTOGRAM: PictogramName = "flask";

/**
 * El signo de cada eslabón (`app/evidence/facilities.py`, STEPS), con el dibujo que ese mismo
 * objeto ya tiene en la interfaz: la instalación, el laboratorio; el experimento, su protocolo; el
 * equipo, un dispositivo; el parámetro, una medida; el investigador, una persona; el proveedor, la
 * procedencia; el conjunto de datos, la tabla de la clase de documento «conjunto de datos»; la
 * publicación, una hoja escrita; la aplicación, el uso (el mismo de la escalera de los bancos).
 */
export const STEP_SIGNS: Readonly<Record<string, Sign>> = {
  facility: { pictogram: FACILITIES_PICTOGRAM },
  experiment: { concept: "protocol" },
  equipment: { concept: "devices" },
  parameter: { concept: "measure" },
  investigator: { concept: "person" },
  provider: { concept: "provenance" },
  dataset: { pictogram: "table-grid" },
  publication: { concept: "document" },
  application: { concept: "systems" },
};

/** El signo de un eslabón; uno que la interfaz no conoce lleva el de «desconocido». */
export function stepSign(step: string): Sign {
  // `Object.hasOwn`, no `in`: «constructor» o «toString» no son eslabones aunque el objeto los herede.
  if (!Object.hasOwn(STEP_SIGNS, step)) return { pictogram: UNKNOWN_PICTOGRAM };
  return STEP_SIGNS[step]!;
}

/**
 * El estado de un eslabón. Leído en la fuente: el libro abierto de lo leído, sin color. Leído con
 * un hueco: la mitad rellena de «en parte» (el mismo dibujo que lo que EMMA tiene en parte de una
 * validación). Sin verificar: el cian del dato ausente (tabla F.5-1), que es lo que es: el
 * eslabón existe y no se encontró su fuente. Un estado desconocido, la marca de «desconocido».
 */
export const STATUS_MARKS: Readonly<Record<string, StateMark>> = {
  read: mark(uiPictogram("sourceText"), null),
  partial: mark("circle-half-right", null),
  not_found: MISSING_MARK,
};

export function statusMark(status: string): StateMark {
  return Object.hasOwn(STATUS_MARKS, status) ? STATUS_MARKS[status]! : UNKNOWN_MARK;
}
