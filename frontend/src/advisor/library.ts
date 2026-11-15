/**
 * Lo poco que la interfaz decide de la biblioteca de contramedidas: con qué dibujo va cada
 * familia, cómo se reparten las entradas en sus grupos RIDGE y con qué marca se dice que la
 * lectura falló.
 *
 * Por qué existe: la biblioteca entera estaba en `GET /api/countermeasures` y nadie la leía; la
 * tripulación solo veía las recomendadas (§5.34.1). El backend da las palabras —la acción, la
 * familia, el peligro RIDGE, los criterios— y el reparto por RIDGE, y la interfaz no redacta
 * nada de eso. Lo que sí elige tiene reglas con prueba:
 *
 * - Cada familia del vocabulario cerrado del backend (`FAMILIES`) tiene su dibujo, también la
 *   farmacológica, que está para decir que queda fuera. Una clave que esta versión no conoce sale
 *   con el dibujo de «desconocido» y su palabra, sin disfrazarse de otra. La paridad con el
 *   vocabulario del backend tiene prueba (`library.test.ts`).
 * - Los grupos son los del backend, en su orden; una entrada que el grupo nombra y la lista no
 *   trae no se inventa (se cuenta como ausente), y una de la lista que ningún grupo nombra sale
 *   aparte en vez de perderse.
 * - Un rechazo del backend (4xx) es amarillo con triángulo y una petición caída (5xx o sin red)
 *   rojo con cruz (decisión del usuario, 2026-10-21).
 * - El filtro por familia (§5.35.7) se hace aquí, en el cliente, sobre la lista que ya llegó: no
 *   pide nada al backend ni cambia lo que se recomienda. Se filtra por las familias que tienen
 *   alguna entrada; la que no tiene ninguna (la farmacológica, que está para decir que queda
 *   fuera) se sigue nombrando, sin mando. Filtrar no esconde nada sin decirlo: cada grupo dice
 *   cuántas de las suyas enseña, y las que un grupo nombra sin ficha (sin familia que mirar)
 *   salen siempre.
 */

import type { PictogramName } from "../icons/registry";
import type { Countermeasure, CountermeasureLibrary } from "../lib/api";
import { UNKNOWN_PICTOGRAM, prefixedPictogram } from "../lib/marks";

/** El dibujo de cada familia (`icons/sets/advisor.ts`). */
export const FAMILY_PICTOGRAMS = {
  "physical-mass": "weight-trapezoid",
  operational: "route-arrow",
  "check-surveillance": "eye-open",
  pharmacological: "capsule-split",
} as const satisfies Record<string, PictogramName>;

export function familyPictogram(family: string): PictogramName {
  return (FAMILY_PICTOGRAMS as Record<string, PictogramName>)[family] ?? UNKNOWN_PICTOGRAM;
}

/**
 * Los dibujos de las cabeceras de contraindicaciones y de efectos (`icons/sets/advisor.ts`): lo
 * que hay que saber antes de adoptar, que la tarjeta ya enseñaba y la tabla no (§5.35.7).
 */
export const CONTRAINDICATIONS_PICTOGRAM = "barrier-striped" satisfies PictogramName;
export const ADVERSE_EFFECTS_PICTOGRAM = "arrow-side-branch" satisfies PictogramName;

/**
 * El dibujo de «adoptadas a la vez» (§5.39.17): dos círculos que se solapan. Acompaña a la nota de
 * co-adopción del backend («adoptada junto con «…»: ninguna fuente leída dice cómo interactúan»),
 * que es información y no un aviso: sin color.
 */
export const CO_ADOPTION_PICTOGRAM = "circles-overlap" satisfies PictogramName;

/**
 * El dibujo de la sección de las contramedidas en investigación (§5.36.15): el matraz de `common`,
 * que en todo el sistema es «un laboratorio o un ensayo»; aquí, que lo de dentro se está
 * ensayando. No es la tirita de la biblioteca: lo de esa sección no se ofrece.
 */
export const RESEARCH_PICTOGRAM = "flask" satisfies PictogramName;

/** Una opción del filtro por familia. */
export interface FamilyOption {
  key: string;
  /** La palabra del backend (`families[].display`, o la `family_display` de una entrada). */
  display: string;
  pictogram: PictogramName;
  /** Cuántas entradas de la lista llevan esta familia: las que deja ver el filtro. */
  count: number;
  /** Con alguna entrada se puede filtrar por ella; sin ninguna solo se nombra. */
  selectable: boolean;
  /** `false` solo en la farmacológica, que se nombra en secundario. */
  inScope: boolean;
}

/**
 * Las familias por las que se puede filtrar: las del vocabulario del backend, en su orden, y
 * detrás las que alguna entrada trae y el vocabulario no (con el dibujo de «desconocido»), para
 * que ninguna entrada quede sin opción que la enseñe. La cifra es la de la lista, no la del
 * backend: es lo que el filtro deja ver.
 */
export function familyOptions(library: CountermeasureLibrary): FamilyOption[] {
  const counts = new Map<string, number>();
  const words = new Map<string, string>();
  for (const item of library.countermeasures) {
    const key = item.family ?? "";
    if (key === "") continue;
    counts.set(key, (counts.get(key) ?? 0) + 1);
    const word = item.family_display?.trim() ?? "";
    if (word !== "" && !words.has(key)) words.set(key, word);
  }
  const known = new Set(library.families.map((family) => family.key));
  const options = [
    ...library.families.map((family) => ({
      key: family.key,
      display: family.display,
      inScope: family.in_scope,
    })),
    ...[...counts.keys()]
      .filter((key) => !known.has(key))
      .map((key) => ({ key, display: words.get(key) ?? key, inScope: true })),
  ];
  return options.map((option) => {
    const count = counts.get(option.key) ?? 0;
    return { ...option, pictogram: familyPictogram(option.key), count, selectable: count > 0 };
  });
}

/**
 * Hasta cuántos caracteres la base del tiempo sin cifra va a la vista. Las bases cortas («sin
 * fuente», «… revisar la ingesta: sin fuente.») se leen en la celda; la que cita su fuente literal
 * (la de la iluminación, unos trescientos) iba a la vista y la columna estrecha la convertía en una
 * torre de treinta líneas (captura de §5.35.7), así que se pliega como la de una cifra.
 */
export const TIME_BASIS_VISIBLE_CHARS = 80;

/** Si la base del tiempo de una entrada sin cifra va plegada. Con cifra siempre lo va. */
export function timeBasisFolds(item: Countermeasure): boolean {
  return item.crew_time_minutes === null && item.crew_time_basis.trim().length > TIME_BASIS_VISIBLE_CHARS;
}

/** Si una entrada pasa el filtro: sin familia elegida, todas. */
export function matchesFamily(item: Countermeasure, family: string | null): boolean {
  return family === null || item.family === family;
}

export interface LibraryGroup {
  ridge: string;
  ridgeDisplay: string;
  pictogram: PictogramName;
  /** La cifra que da el backend para el grupo. */
  count: number;
  /** Las entradas del grupo que pasan el filtro. */
  items: Countermeasure[];
  /** Ids que el grupo nombra y la lista no trae: salen con cualquier filtro. */
  missing: string[];
}

/**
 * Los grupos RIDGE del backend con sus entradas resueltas y filtradas por familia, y las entradas
 * que ningún grupo nombra (filtradas igual). El orden es el del backend en los dos niveles.
 */
export function libraryGroups(
  library: CountermeasureLibrary,
  family: string | null = null,
): {
  groups: LibraryGroup[];
  ungrouped: Countermeasure[];
} {
  const byId = new Map(library.countermeasures.map((item) => [item.id, item]));
  const named = new Set<string>();
  const groups = library.by_ridge.map((group) => {
    const items: Countermeasure[] = [];
    const missing: string[] = [];
    for (const id of group.countermeasures) {
      named.add(id);
      const item = byId.get(id);
      if (item === undefined) missing.push(id);
      else if (matchesFamily(item, family)) items.push(item);
    }
    return {
      ridge: group.ridge,
      ridgeDisplay: group.ridge_display,
      pictogram: prefixedPictogram("ridge", group.ridge),
      count: group.count,
      items,
      missing,
    };
  });
  return {
    groups,
    ungrouped: library.countermeasures.filter((item) => !named.has(item.id) && matchesFamily(item, family)),
  };
}

