/**
 * Qué pictograma acompaña a cada carácter del dolor del catálogo del backend.
 *
 * Por qué existe: el catálogo (`app/pain/catalog.py`) da la clave y la palabra de cada carácter
 * («sharp» → «Punzante»), y ningún campo dice con qué dibujo se enseña. Inventarlo en cada panel
 * daría un dibujo distinto en el selector y en la evolución; aquí está una vez, y los dos lo leen.
 * La palabra sigue siendo la del backend y va siempre al lado; el dibujo solo la acompaña.
 *
 * Sin color (`mark(pictogram, null)`): el carácter y la intensidad del dolor no son una alerta
 * validada, y nunca van en rojo ni amarillo (`compliance/hmi-state-of-the-art.md` §5.2). Un
 * carácter que esta interfaz no conoce (un backend con uno nuevo) se enseña con su palabra y la
 * marca de «desconocido», sin suponerle un dibujo ni tumbar el panel.
 */

import { type StateMark, UNKNOWN_MARK, mark } from "../lib/marks";

const CHARACTER_MARKS: Readonly<Record<string, StateMark>> = {
  sharp: mark("star-four", null),
  dull: mark("oval", null),
  burning: mark("flame", null),
  pressing: mark("arrows-inward", null),
  throbbing: mark("rings-concentric", null),
  cramping: mark("spiral", null),
  tingling: mark("dots-scattered", null),
};

/** Las claves con dibujo propio, en el orden del catálogo. */
export const KNOWN_CHARACTERS: readonly string[] = Object.keys(CHARACTER_MARKS);

export function characterMark(key: string): StateMark {
  return CHARACTER_MARKS[key] ?? UNKNOWN_MARK;
}
