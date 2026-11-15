/**
 * Las marcas de los informes escaneados: clase de informe, veredicto de identidad y estado de una
 * cifra leída (`app/reports`).
 *
 * Por qué existe aparte del panel: lo que aquí se puede equivocar es lógica. Un veredicto de
 * identidad pintado como el de al lado haría pasar por acreditado un informe que no lo está; una
 * cifra sin confirmar que se viera como confirmada entraría en el análisis sin que nadie la
 * mirase. Está en un `.ts` para que lo pruebe `marks.test.ts`.
 *
 * Nada de aquí redacta: la palabra es siempre la del backend (`explanation`, `name`, `status`) o
 * el rótulo que ya tenía el panel. Un veredicto que la interfaz no conoce se enseña con su
 * explicación y la marca de «desconocido»: no se disfraza de otro.
 */

import type { PictogramName } from "../icons/registry";
import type { ReportKind } from "../lib/api";
import { type StateMark, UNKNOWN_MARK, mark } from "../lib/marks";

/**
 * Clase de informe → hoja que la distingue (`icons/sets/reports.ts`; la hoja escrita del informe
 * de especialista es la de `common`, la misma de toda hoja escrita de la interfaz).
 */
export const KIND_PICTOGRAMS: Readonly<Record<ReportKind, PictogramName>> = {
  analitica: "page-grid",
  "informe-especialista": "sheet-lines",
  alta: "page-arrow-right",
  otro: "page-blank",
};

export function kindPictogram(kind: ReportKind): PictogramName {
  return KIND_PICTOGRAMS[kind];
}

/**
 * Veredictos de `identidad_paciente` de Polaris (`VEREDICTOS` y `SIRVE` de
 * `polaris/tools/identidad_paciente.py`, más `sin_identidad` de `app/reports/identity.py`). Solo
 * «ambiguo», «otro paciente» y «sin overlay» piden mirar (amarillo con triángulo: una filiación
 * que no es la suya o un documento que no se puede leer); «coincide» acredita (hecho); «parcial»
 * acredita la mitad; «no consta», «no textual» (sin OCR el texto está vacío: es el veredicto de
 * cada informe en una instalación sin tesseract) y «sin identidad» son un dato que falta, en el
 * informe o en el tripulante. Ninguno es un juicio clínico: sin más color.
 */
const IDENTITY_MARKS: Readonly<Record<string, StateMark>> = {
  coincide: mark("check", null),
  parcial: mark("circle-half-dashed", null),
  no_consta: mark("ring-dotted", null),
  no_textual: mark("ring-dotted", null),
  sin_identidad: mark("ring-dotted", null),
  ambiguo: mark("shape-triangle", "yellow"),
  otro_paciente: mark("shape-triangle", "yellow"),
  sin_overlay: mark("shape-triangle", "yellow"),
};

export function identityMark(verdict: string): StateMark {
  return IDENTITY_MARKS[verdict] ?? UNKNOWN_MARK;
}

/**
 * Estado de una cifra leída (`app/reports/labs.py`): a la espera de una persona (casilla por
 * marcar) o confirmada (hecho). Sin color: confirmar no es interpretar.
 */
const READING_MARKS: Readonly<Record<string, StateMark>> = {
  por_confirmar: mark("box-empty", null),
  confirmada: mark("check", null),
};

export function readingMark(status: string): StateMark {
  return READING_MARKS[status] ?? UNKNOWN_MARK;
}
