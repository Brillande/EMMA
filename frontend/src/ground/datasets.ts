/**
 * El mapa de conjuntos de datos humanos y CIPHER, con la marca de cada cosa.
 *
 * Por qué existe aparte del panel: lo que aquí se puede equivocar es lógica, no pintura. Un tramo
 * de la escalera sin días pintado igual que uno buscado y no encontrado diría que se sabe que no
 * hay tomas cuando solo no se encontraron; un conjunto de ratones pintado con la persona diría que
 * mide astronautas; un acceso controlado con el candado abierto, que se puede descargar. Está en un
 * `.ts` para que lo pruebe `datasets.test.ts`.
 *
 * Nada de aquí redacta: los nombres, las frases, los días, el estado de cada fase, el acceso y el
 * uso en EMMA son de `GET /api/human-datasets`. Aquí solo se elige pictograma y color
 * (`lib/marks.ts`, `evidence/sourceMarks.ts` para la población, `testbeds.ts` para el entorno). Es
 * un inventario: nada de esto decide sobre la tripulación.
 */

import type { PictogramName } from "../icons/registry";
import type { DatasetEmmaUse, DatasetLadderCell } from "../lib/api";
import { type StateMark, EMPTY_MARK, UNAVAILABLE_MARK, UNKNOWN_MARK, mark } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";

/** El dibujo del mapa: el cilindro del almacén de datos de un estudio. */
export const DATASETS_PICTOGRAM: PictogramName = "cylinder-stack";

/** Buscado y no encontrado: la lupa, en cian porque el dato está ausente (tabla F.5-1). */
export const NOT_FOUND_MARK: StateMark = mark(uiPictogram("searchedNotFound"), "cyan");

/**
 * Lo que se sabe de las tomas de una fase (`app/evidence/human_datasets.py`, PHASE_STATUS). Con
 * día, el calendario; dicho sin día, el libro abierto de lo leído; sin tomas, el anillo punteado
 * sin color de «nada registrado»; no procede, el gris de «no disponible»; y buscado sin
 * encontrarlo, la lupa en cian. Ninguna es la marca de «hecho».
 */
export const PHASE_STATUS_MARKS: Readonly<Record<string, StateMark>> = {
  labels: mark(uiPictogram("date"), null),
  stated: mark(uiPictogram("sourceText"), null),
  none: EMPTY_MARK,
  not_applicable: UNAVAILABLE_MARK,
  not_found: NOT_FOUND_MARK,
};

export function phaseStatusMark(status: string): StateMark {
  return PHASE_STATUS_MARKS[status] ?? UNKNOWN_MARK;
}

/**
 * Un tramo de la escalera. Con días, el calendario; una fase con días pero ninguno en este tramo,
 * el anillo punteado de «nada registrado aquí» (no la lupa: se leyó y no hay); sin días, la marca
 * del estado de su fase.
 */
export function cellMark(cell: Pick<DatasetLadderCell, "labels" | "status">): StateMark {
  if (cell.labels.length > 0) return phaseStatusMark("labels");
  if (cell.status === "labels") return EMPTY_MARK;
  return phaseStatusMark(cell.status);
}

/**
 * El acceso (ACCESS_LEVELS del backend): el candado abierto si los ficheros se descargan, la mitad
 * rellena de «en parte» si lo sensible es controlado, la llave si hace falta un permiso (controlado
 * o por solicitud: dos palabras para lo mismo visto desde la fuente) y la lupa en cian si no se
 * encontró. Sin color salvo lo no encontrado: el acceso no es un estado de la tripulación.
 */
export const ACCESS_MARKS: Readonly<Record<string, StateMark>> = {
  open: mark("padlock-open", null),
  // Solo el fichero que EMMA tiene: el mismo candado, y la palabra dice que no se extiende al resto.
  file_open: mark("padlock-open", null),
  mixed: mark("circle-half-right", null),
  controlled: mark("key-bit", null),
  request: mark("key-bit", null),
  // A petición a sus autores: también hace falta pedirlo.
  authors: mark("key-bit", null),
  not_found: NOT_FOUND_MARK,
};

export function accessMark(level: string): StateMark {
  return ACCESS_MARKS[level] ?? UNKNOWN_MARK;
}

/** El uso en EMMA: el engranaje del sistema si lo hay; el anillo punteado si todavía no. */
export function emmaUseMark(use: Pick<DatasetEmmaUse, "used">): StateMark {
  return use.used ? mark(uiPictogram("systems"), null) : EMPTY_MARK;
}

/** El dibujo de los catálogos de §8 (ISS Research Explorer, data.nasa.gov): una hoja con renglones. */
export const CATALOG_PICTOGRAM: PictogramName = uiPictogram("evidence");

/**
 * Lo que se sabe de los controles de un conjunto (CONTROL_STATUS del backend): con controles, las
 * dos barras de la comparación; sin controles, el anillo punteado; no procede, el gris; buscado y
 * no encontrado, la lupa en cian. Ninguna es la marca de «hecho».
 */
export const CONTROL_STATUS_MARKS: Readonly<Record<string, StateMark>> = {
  listed: mark(uiPictogram("comparison"), null),
  none: EMPTY_MARK,
  not_applicable: UNAVAILABLE_MARK,
  not_found: NOT_FOUND_MARK,
};

export function controlStatusMark(status: string): StateMark {
  return CONTROL_STATUS_MARKS[status] ?? UNKNOWN_MARK;
}
