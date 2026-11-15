/**
 * Las marcas de la prueba PVT: fase de la sesión, respaldo de cada parámetro y comparación con
 * lo publicado.
 *
 * Por qué existe: hasta el rediseño pictográfico (2026-10-20) el panel escribía las formas de la
 * sesión como caracteres (□ ■ ○ ✓) dentro del JSX, y el respaldo de un parámetro y su comparación
 * con la fuente iban solo con la palabra del backend, sin forma. Aquí cada estado tiene su
 * pictograma por `lib/marks.ts`, en un solo sitio y probado sin navegador, y el panel solo pinta.
 *
 * Ninguna de estas marcas es una alerta: de dónde sale un parámetro o si coincide con lo
 * publicado no es un fallo, así que van sin color (ni rojo, ni amarillo, ni cian). La única con
 * color es «sin valor publicado», en gris, que en la tabla F.5-1 es «no disponible»: no hay con
 * qué comparar. Un estado que esta versión no conoce no se disfraza de otro: `UNKNOWN_MARK`, con
 * la palabra del backend.
 *
 * Aquí no se decide nada: la fase la lleva la sesión, el respaldo y la comparación los calcula el
 * backend (`GET /api/pvt/protocol`). Esto solo elige la forma.
 */
import { type StateMark, UNKNOWN_MARK, mark } from "../lib/marks";
import type { Phase } from "./session";

/**
 * La fase de la sesión. La espera y la marca se distinguen por forma (cuadrado vacío, cuadrado
 * lleno) además de por palabra y tono; la abandonada lleva un círculo, como antes de pasar a
 * pictogramas; la acabada, la señal de hecho. Antes de empezar no hay nada que marcar.
 */
const PHASES: Readonly<Record<Phase, StateMark>> = {
  idle: mark(null, null),
  waiting: mark("square-outline", null),
  stimulus: mark("shape-square", null),
  finished: mark("check", null),
  abandoned: mark("shape-circle", null),
};

export function phaseMark(phase: Phase): StateMark {
  return PHASES[phase];
}

/** El respaldo de un parámetro (`basis`): escrito en el repositorio, por diseño, leído en la fuente. */
const BASES: Readonly<Record<string, StateMark>> = {
  repository: mark("sheet-lines", null),
  design: mark("pencil", null),
  read: mark("book-open", null),
};

export function basisMark(basis: string): StateMark {
  return Object.hasOwn(BASES, basis) ? BASES[basis]! : UNKNOWN_MARK;
}

/**
 * El valor de EMMA frente a lo publicado (`published.status`). La misma cifra con otro operador
 * no es el mismo valor (decimotercera ronda): lleva su forma propia, no la de «igual».
 */
const COMPARISONS: Readonly<Record<string, StateMark>> = {
  same_value: mark("equals", null),
  same_figure_different_operator: mark("tilde-double", null),
  different_value: mark("not-equal", null),
  not_comparable: mark("dash", null),
  // Sin valor publicado: no hay con qué comparar, que es «no disponible» (gris, F.5-1).
  not_published: mark("slash-circle", "gray"),
};

export function comparisonMark(status: string): StateMark {
  return Object.hasOwn(COMPARISONS, status) ? COMPARISONS[status]! : UNKNOWN_MARK;
}
