/**
 * Los bancos de prueba y las dos validaciones, con la marca de cada cosa.
 *
 * Por qué existe aparte del panel: lo que aquí se puede equivocar es lógica, no pintura. Un banco
 * sin entorno del enumerado pintado con el dibujo de otro entorno diría de dónde viene un dato que
 * no tiene; una validación que EMMA no tiene, pintada con la marca de «hecho», diría que la tiene.
 * Está en un `.ts` para que lo pruebe `testbeds.test.ts`.
 *
 * Nada de aquí redacta: el nombre de cada banco, sus frases, lo que deja fuera, lo que EMMA tiene
 * de cada validación y la frase «… de EMMA: ninguna.» son de `GET /api/testbeds`. Aquí solo se
 * elige pictograma y color (`lib/marks.ts`, `lib/provenance.ts`). Es un inventario: nada de esto
 * decide sobre la tripulación.
 */

import type { PictogramName } from "../icons/registry";
import type { Testbed, TestbedLeftOut } from "../lib/api";
import {
  type StateMark,
  EMPTY_MARK,
  UNAVAILABLE_MARK,
  UNKNOWN_MARK,
  mark,
} from "../lib/marks";
import { EVIDENCE_CONTEXTS, EVIDENCE_CONTEXT_PICTOGRAMS, type EvidenceContext } from "../lib/provenance";
import { type UiConcept, uiPictogram } from "../lib/uiMarks";

/** El dibujo de los bancos de prueba: la escalera de evidencia en que se ordenan. */
export const TESTBEDS_PICTOGRAM: PictogramName = "ladder";

/**
 * Un dibujo por validación (`app/evidence/testbeds.py`, VALIDATIONS): el matraz de lo que se mide
 * en laboratorio, análogo o vuelo (científica) y el casco de la tripulación que usa el sistema
 * sola (operacional). Sin color: describen, no son un estado.
 */
export const VALIDATION_PICTOGRAMS: Readonly<Record<string, PictogramName>> = {
  scientific: "flask",
  operational: "helmet",
};

/** La marca de una validación; una que la interfaz no conoce lleva la de «desconocido». */
export function validationMark(validation: string): StateMark {
  const pictogram = VALIDATION_PICTOGRAMS[validation];
  return pictogram === undefined ? UNKNOWN_MARK : mark(pictogram, null);
}

/**
 * Lo que EMMA tiene de una validación. «Ninguna» es que aún no hay nada registrado: el anillo
 * punteado sin color (`EMPTY_MARK`), no el cian de un dato caducado ni el gris de «no disponible».
 * «En parte» es la mitad derecha rellena, el mismo dibujo que una hipótesis de diseño ejercitada
 * en parte con datos reales (`framework.ts`). Ninguna de las dos es la marca de «hecho».
 */
export const EMMA_STATUS_MARKS: Readonly<Record<string, StateMark>> = {
  none: EMPTY_MARK,
  partial: mark("circle-half-right", null),
};

export function emmaStatusMark(status: string): StateMark {
  return EMMA_STATUS_MARKS[status] ?? UNKNOWN_MARK;
}

export interface ContextCell {
  /** La palabra: el rótulo del entorno o, sin entorno, la del backend («fuera del enumerado»). */
  word: string;
  mark: StateMark;
}

/**
 * El entorno de evidencia que llevaría un dato del banco, con el dibujo de la procedencia (el
 * mismo que lleva una observación). Sin entorno, el gris de «no disponible» con la palabra del
 * backend: no se le supone el entorno más parecido. Uno que la interfaz no conoce sale con su
 * clave y la marca de «desconocido», sin tumbar el panel.
 */
export function contextCell(bank: Pick<Testbed, "evidence_context" | "outside_enum_text">): ContextCell {
  const context = bank.evidence_context;
  if (context === null) return { word: bank.outside_enum_text ?? "", mark: UNAVAILABLE_MARK };
  // `Object.hasOwn`, no `in`: «constructor» o «toString» no son entornos aunque el objeto los herede.
  if (!Object.hasOwn(EVIDENCE_CONTEXTS, context)) return { word: context, mark: UNKNOWN_MARK };
  const known = context as EvidenceContext;
  return { word: EVIDENCE_CONTEXTS[known], mark: mark(EVIDENCE_CONTEXT_PICTOGRAMS[known], null) };
}

/**
 * Cómo se sabe lo que un banco deja fuera: lo dice la fuente (el libro abierto de lo leído) o lo
 * deduce EMMA (el medio punto de lo inferido). Sin color.
 */
export function leftOutMark(item: Pick<TestbedLeftOut, "basis">): StateMark {
  if (item.basis === "source") return mark(uiPictogram("sourceText"), null);
  if (item.basis === "deduced") return mark(uiPictogram("inferred"), null);
  return UNKNOWN_MARK;
}


/**
 * El dibujo del rótulo de cada columna de la conversación de ideación (`COLUMNS` en
 * `app/evidence/testbeds.py`): el reloj de cuánto dura, la persona de quien participa, la hoja
 * escrita de los datos, el cubo de lo que pone cada proveedor u operador (el avión, el hábitat,
 * el laboratorio), la regla de lo que se mide, los arcos de sensor de los equipos, la ficha de
 * quien investiga y el portapapeles de los experimentos. Uno que la interfaz no conoce sale con el
 * signo de «desconocido».
 */
export const COLUMN_CONCEPTS: Readonly<Record<string, UiConcept>> = {
  duration: "time",
  participants: "person",
  data: "evidence",
  providers: "resources",
  parameters: "measure",
  equipment: "devices",
  investigators: "identity",
  experiments: "protocol",
};

export function columnPictogram(column: string): PictogramName {
  const concept = COLUMN_CONCEPTS[column];
  return concept === undefined ? (UNKNOWN_MARK.pictogram ?? TESTBEDS_PICTOGRAM) : uiPictogram(concept);
}

/**
 * Qué reproduce un banco de un peligro RIDGE (`RIDGE_STATUS` en `app/evidence/testbeds.py`), sin
 * color: describe un análogo, no el estado de nadie. El punto lleno de lo que lo reproduce, la
 * mitad derecha de «en parte» (la misma de una validación que EMMA tiene en parte), el círculo
 * tachado de «no, o no hay» para lo que deja fuera y el signo de «desconocido» para lo que ninguna
 * página dice. Un estado que la interfaz no conoce sale también con el de «desconocido».
 */
export const RIDGE_STATUS_MARKS: Readonly<Record<string, StateMark>> = {
  reproduces: mark("dot-filled", null),
  partial: mark("circle-half-right", null),
  leaves_out: mark(uiPictogram("decline"), null),
  unknown: UNKNOWN_MARK,
};

export function ridgeStatusMark(status: string): StateMark {
  return Object.hasOwn(RIDGE_STATUS_MARKS, status) ? RIDGE_STATUS_MARKS[status]! : UNKNOWN_MARK;
}

/** Lo que ninguna página leída da: la lupa de «buscado y no encontrado», sin color. */
export const NOT_FOUND_MARK: StateMark = mark(uiPictogram("searchedNotFound"), null);

/** Los nombres de unos bancos por su identificador, en el orden en que llegan. */
export function bankNames(ids: string[], banks: Pick<Testbed, "id" | "name">[]): string[] {
  return ids.map((id) => banks.find((bank) => bank.id === id)?.name ?? id);
}
