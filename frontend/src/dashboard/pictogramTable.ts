/**
 * Una tabla clave de la API → dibujo, con la marca de «desconocido» para la clave que no esta.
 *
 * Existe porque las tablas de la mision, de la vigilancia, de las fuentes y de las bandas
 * inferidas resolvian lo mismo cada una a su manera. La regla es una: una clave que la interfaz
 * no conoce se enseña con su palabra y el dibujo de `UNKNOWN_MARK` (un punto, sin significado),
 * nunca con el de otra clave ni tumbando la consola. `Object.hasOwn` deja fuera lo heredado de
 * `Object` («toString» no es una capacidad).
 */

import type { PictogramName } from "../icons/registry";
import { UNKNOWN_MARK } from "../lib/marks";

export type PictogramTable = Readonly<Record<string, PictogramName>>;

export function pictogramFor(table: PictogramTable, key: string): PictogramName | null {
  return Object.hasOwn(table, key) ? (table[key] ?? null) : UNKNOWN_MARK.pictogram;
}
