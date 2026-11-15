/**
 * La marca de la vuelta al rango de un indicador tras el vuelo (§5.37.7).
 *
 * Por qué existe: el backend dice, por indicador, en qué R+ vuelve la toma dentro del rango
 * previo propio, si se mantiene y si la última sigue fuera (`recovery.return_to_range`), con su
 * frase. La interfaz no la redacta; solo le pone la marca, y la marca tiene que ser la de cada
 * toma del mismo panel: la última dentro, el anillo sin color; la última fuera, el rombo azul de
 * aviso; sin rango con que comparar, el cian del dato ausente (F.5-1). Un estado que la interfaz
 * no conoce sale con la marca de «desconocido», no con una supuesta.
 */

import type { RecoveryReport } from "../lib/api";
import { MISSING_MARK, type StateMark, UNKNOWN_MARK, mark } from "../lib/marks";

type ReturnState =
  | RecoveryReport["indicators"][number]["return_to_range"]["state"]
  | RecoveryReport["without_preflight_range"][number]["return_to_range"]["state"];

/** Las mismas dos marcas que cada toma del panel: dentro y fuera. */
export const INSIDE_MARK: StateMark = mark("shape-circle", null);
export const OUTSIDE_MARK: StateMark = mark("shape-diamond", "blue");

export const RETURN_MARKS: Record<ReturnState, StateMark> = {
  within: INSIDE_MARK,
  "back-again": INSIDE_MARK,
  "not-back": OUTSIDE_MARK,
  "no-preflight-range": MISSING_MARK,
};

export function returnMark(state: string): StateMark {
  return Object.hasOwn(RETURN_MARKS, state) ? RETURN_MARKS[state as ReturnState] : UNKNOWN_MARK;
}
