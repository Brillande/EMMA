/**
 * El registro de pictogramas: todos los conjuntos en un solo mapa, con su nombre como tipo.
 *
 * Por qué existe aparte de `Pictogram.tsx`: lo importan tablas de `lib/` (`levels.ts`,
 * `provenance.ts`, `marks.ts`) que no son React y no deben arrastrarlo. Y por qué los conjuntos
 * están separados por área: cada unidad del rediseño añade los suyos sin tocar los de las demás,
 * y `SETS` deja comprobar que un nombre no se repite entre dos áreas y que un dibujo de área solo
 * se usa desde la suya (`pictograms.test.ts`). Los del núcleo (`shapes`, `common`, `provenance`,
 * `domains`, `indicators`, `ui`) los usa cualquiera; `ui` es el mobiliario de la interfaz (títulos,
 * plegables, mandos y cabeceras), con su tabla concepto → dibujo en `lib/uiMarks.ts`.
 *
 * `PictogramName` es la unión de todas las claves: escribir un nombre que no existe no compila,
 * y `pictogram()` falla en tiempo de ejecución si llega como cadena desde fuera.
 */

import { advisor } from "./sets/advisor";
import { common } from "./sets/common";
import { diary } from "./sets/diary";
import { domains } from "./sets/domains";
import { evidence } from "./sets/evidence";
import { ground } from "./sets/ground";
import { habitat } from "./sets/habitat";
import { imaging } from "./sets/imaging";
import { indicators } from "./sets/indicators";
import { mission } from "./sets/mission";
import { pain } from "./sets/pain";
import { provenance } from "./sets/provenance";
import { pvt } from "./sets/pvt";
import { radiation } from "./sets/radiation";
import { reports } from "./sets/reports";
import { shapes } from "./sets/shapes";
import { shell } from "./sets/shell";
import { sources } from "./sets/sources";
import { timeline } from "./sets/timeline";
import { ui } from "./sets/ui";
import { volumes } from "./sets/volumes";
import type { PictogramDef } from "./types";

/** Los conjuntos, del núcleo y por área, para comprobar que un nombre no se repite entre dos. */
export const SETS = {
  shapes,
  common,
  provenance,
  domains,
  indicators,
  ui,
  timeline,
  mission,
  sources,
  habitat,
  advisor,
  evidence,
  ground,
  diary,
  pvt,
  radiation,
  pain,
  imaging,
  volumes,
  reports,
  shell,
} as const;

export const PICTOGRAMS = {
  ...shapes,
  ...common,
  ...provenance,
  ...domains,
  ...indicators,
  ...ui,
  ...timeline,
  ...mission,
  ...sources,
  ...habitat,
  ...advisor,
  ...evidence,
  ...ground,
  ...diary,
  ...pvt,
  ...radiation,
  ...pain,
  ...imaging,
  ...volumes,
  ...reports,
  ...shell,
} as const;

export type PictogramName = keyof typeof PICTOGRAMS;

export function pictogramNames(): readonly PictogramName[] {
  return Object.keys(PICTOGRAMS) as PictogramName[];
}

export function isPictogramName(value: string): value is PictogramName {
  return Object.hasOwn(PICTOGRAMS, value);
}

/** El dibujo de un pictograma. Un nombre desconocido falla: no se pinta otro en su lugar. */
export function pictogram(name: string): PictogramDef {
  if (!isPictogramName(name)) throw new RangeError(`pictograma desconocido: ${name}`);
  return PICTOGRAMS[name];
}
