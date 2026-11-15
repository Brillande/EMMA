/**
 * La cobertura de los riesgos del HRP (`GET /api/risks/hrp-coverage`), ordenada para leerla.
 *
 * Por qué existe aparte del panel: lo que aquí se puede equivocar es la marca. «Cubierto», «en
 * parte» y «fuera del alcance de EMMA» son tres respuestas distintas a la misma pregunta, y si se
 * pintaran igual el inventario diría que EMMA vigila todos los riesgos. Cada una lleva el dibujo que
 * ya tiene su idea en la consola de Tierra, para no darle a un dibujo un segundo significado: lo
 * cubierto, la diana del alcance (la del rótulo «Alcance» de cada riesgo); lo parcial, la mitad
 * rellena de «en parte» (conjuntos de datos, instalaciones, hipótesis); lo de fuera, el gris con el
 * círculo tachado de «no disponible» (tabla F.5-1), como «fuera de EMMA» en las hipótesis. Solo
 * esa lleva color, y no es de alarma: no es el estado de nadie.
 *
 * Las palabras y los recuentos son los del backend; una cobertura que la interfaz no conoce se
 * enseña con su palabra y la marca de «desconocido», nunca disfrazada de otra.
 */

import { type StateMark, UNKNOWN_MARK, mark } from "../lib/marks";
import { statusMark } from "./facilities";
import { statusStyle } from "./framework";

// «En parte» y «fuera de EMMA» se toman de donde ya significan eso, no se copian: si su dibujo
// cambia allí, cambia aquí.
export const COVERAGE_MARKS: Readonly<Record<string, StateMark>> = {
  covered: mark("crosshair", null),
  partial: statusMark("partial"),
  outside: statusStyle("outside"),
};

export function coverageMark(coverage: string): StateMark {
  // `Object.hasOwn`, no `in`: «constructor» no es una cobertura aunque el objeto lo herede.
  return Object.hasOwn(COVERAGE_MARKS, coverage) ? COVERAGE_MARKS[coverage]! : UNKNOWN_MARK;
}

/**
 * Los recuentos del backend, con su palabra, en el orden en que da las palabras; un recuento de
 * una cobertura sin palabra va detrás con su clave. Aquí no se cuenta nada.
 */
export function coverageRows(
  counts: Readonly<Record<string, number>>,
  display: Readonly<Record<string, string>>,
): { coverage: string; display: string; count: number }[] {
  const keys = new Set([...Object.keys(display), ...Object.keys(counts)]);
  return [...keys].map((coverage) => ({
    coverage,
    // `Object.hasOwn`, como en `coverageMark`: una clave heredada no es una palabra ni un recuento.
    display: Object.hasOwn(display, coverage) ? display[coverage]! : coverage,
    count: Object.hasOwn(counts, coverage) ? counts[coverage]! : 0,
  }));
}
