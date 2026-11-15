/**
 * Las marcas de una anotación del diario o de una sesión PVT: dónde cae respecto al estado y si
 * consta quién la anotó.
 *
 * Por qué está aparte del panel: el panel escribía el glifo y la clase de color en línea
 * (`△`, `◌`, `c-yellow`, `c-gray`) y una prueba los fijaba como caracteres. Aquí cada estado del
 * backend tiene su marca una sola vez, con la forma común (`lib/marks.ts`), y la palabra que la
 * acompaña sigue siendo la del backend (`position_note`, `recorded_by_display`). La PVT tenía su
 * copia del triángulo en línea y sin la posición descriptiva; desde §5.39.11 pinta con esta tabla.
 *
 * - `after-reference`: el estado la aparta del análisis → triángulo y amarillo, como toda
 *   lectura que el análisis no usa.
 * - `descriptive`: el estado no la lee ni dentro ni fuera de su ventana → el guion de «no
 *   aplica», sin color: no es un aviso sobre la persona.
 * - `not-analysed-by-type` (§5.39.11): una lectura inferida o predicha, firmada en el registro,
 *   que el estado no lee por su tipo → «no disponible» para el estado (gris con el círculo
 *   tachado, `UNAVAILABLE_MARK`, tabla F.5-1). No es cian: el dato existe y no ha caducado; ni
 *   amarillo: no hay nada que mirar en la persona. El tipo lo dice la frase del backend.
 * - `current` y `earlier`: solo la palabra del backend; no había forma y no se añade ninguna.
 * - Quien no consta va con la marca de «no disponible» (tabla F.5-1): gris con el círculo
 *   tachado, la de toda la interfaz (`UNAVAILABLE_MARK`). Hasta la segunda pasada llevaba el
 *   anillo punteado en gris, que es el dibujo de «dato ausente»: dos dibujos para «no
 *   disponible» y uno para dos conceptos. No en cian, que diría «dato caducado». Esa marca
 *   (`recordedByMark`) la usan también los descriptivos y vive en `lib/marks.ts` (§5.33.12).
 */

import type { EntryPosition } from "../lib/api";
import { NO_MARK, type StateMark, UNAVAILABLE_MARK, mark } from "../lib/marks";

const POSITION_MARKS: Readonly<Record<EntryPosition, StateMark>> = {
  "after-reference": mark("shape-triangle", "yellow"),
  descriptive: mark("dash", null),
  "not-analysed-by-type": UNAVAILABLE_MARK,
  current: NO_MARK,
  earlier: NO_MARK,
};

/**
 * La marca de la posición de una anotación. El tipo es el de la API; `hasOwn` es la defensa
 * frente al JSON de un backend más nuevo: una posición que esta interfaz no conoce va sin marca.
 */
export function positionMark(position: EntryPosition): StateMark {
  return Object.hasOwn(POSITION_MARKS, position) ? POSITION_MARKS[position] : NO_MARK;
}
