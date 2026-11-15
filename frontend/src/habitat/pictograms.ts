/**
 * Qué dibujo acompaña a cada nombre del hábitat: parámetro de cabina, módulo, sistema, clase de
 * hipótesis y dónde estaba cada tripulante cuando la cabina se salió de su límite.
 *
 * Por qué existe: el backend da de cada cosa su clave y su palabra (`display`), y la interfaz la
 * escribe tal cual; lo único que añade es el pictograma de al lado (`icons/sets/habitat.ts`), y
 * esa elección tiene que estar en un solo sitio para que el CO2 lleve el mismo dibujo en la tabla
 * de atmósfera, en la comparación entre tripulantes y en la lista de sistemas. Una clave que esta
 * versión no conoce se enseña con su palabra y el punto de «desconocido» (`UNKNOWN_MARK`), nunca
 * con el dibujo de otra ni fallando: las listas de módulos y sistemas son del vehículo y cambian
 * al desplegar (`habitat_modules.json`, `habitat_systems.json`).
 *
 * Nombrar no es avisar: ninguno de estos lleva color. El color sigue donde ya estaba —el estado
 * declarado de un sistema (`systems.ts`), el paso del flujo (`flow.ts`), la clase de un límite— y
 * una ubicación sin declarar es un dato ausente (`MISSING_MARK`: cian, anillo punteado), como en
 * el resto de la interfaz.
 */

import type { PictogramName } from "../icons/registry";
import { type StateMark, MISSING_MARK, UNKNOWN_MARK, mark } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";

/** Lo que la interfaz no conoce: el punto, sin significado. */
const UNKNOWN: PictogramName = "dot-small";

/** Parámetros del hábitat (`environment/habitat.py`, `PARAMETERS` y `DISPLAY_ONLY`). */
export const PARAMETER_PICTOGRAMS: Readonly<Record<string, PictogramName>> = {
  "cabin-ppco2": "atoms-three",
  "cabin-ppo2": "atoms-two",
  "cabin-pressure": "gauge",
  "cabin-temperature": "thermometer",
  "cabin-humidity": "drop-half",
  "cabin-noise": "speaker-waves",
  "cabin-light": "bulb",
  "cabin-co": "atoms-two-one-filled",
  "cabin-ammonia": "molecule-hub",
  "cabin-formaldehyde": "vapor",
  // Agua potable y microbiología: se muestran y no se evalúan (`DISPLAY_ONLY`, 2026-10-22).
  "water-toc": "drop-hexagon",
  "water-silver": "ingot",
  "water-microbial": "drop-dots",
  "air-microbial": "wind-dots",
  "surface-microbial": "surface-dots",
};

/** Módulos de la lista declarada (`data/habitat_modules.json`). */
export const MODULE_PICTOGRAMS: Readonly<Record<string, PictogramName>> = {
  "habitat-principal": "house",
  laboratorio: "flask",
  camarotes: "bunk-beds",
  esclusa: "hatch",
};

/** Sistemas del vocabulario declarado (`data/habitat_systems.json`). La luz comparte dibujo con su parámetro. */
export const SYSTEM_PICTOGRAMS: Readonly<Record<string, PictogramName>> = {
  "air-revitalization": "wind",
  "pressure-control": "valve",
  "thermal-control": "snowflake",
  "contaminant-control": "funnel",
  lighting: "bulb",
  food: "fork-knife",
  exercise: "dumbbell",
  power: "battery",
  communications: "radio-waves",
  water: "tap",
};

/**
 * El aire de cabina: el título «Atmósfera de cabina» y el rótulo «Parámetro de cabina» de la
 * comparación (§5.33.4). Es el viento del sistema de revitalización de aire a propósito: el
 * sistema y lo que trata son el mismo aire, y otro dibujo sería el segundo de un concepto.
 */
export const CABIN_AIR_PICTOGRAM: PictogramName = SYSTEM_PICTOGRAMS["air-revitalization"] ?? UNKNOWN;

/**
 * El título de cada bloque de lecturas del hábitat (`environment/habitat.py`, `GROUPS`). La
 * atmósfera es el aire de cabina; el agua potable lleva el grifo de su sistema, porque el
 * sistema y lo que distribuye son la misma agua (como la luz y la iluminación); la
 * microbiología del aire y las superficies, la placa de cultivo.
 */
export const GROUP_PICTOGRAMS: Readonly<Record<string, PictogramName>> = {
  cabin: CABIN_AIR_PICTOGRAM,
  water: SYSTEM_PICTOGRAMS.water ?? UNKNOWN,
  microbiology: "petri-dish",
};

export function groupPictogram(key: string): PictogramName {
  return GROUP_PICTOGRAMS[key] ?? UNKNOWN;
}

/**
 * Los pasos del flujo de una hipótesis (especificación §7): el signo del concepto «pasos de un
 * flujo» (`lib/uiMarks.ts`), el mismo que los pasos de una alerta (§5.34.6).
 */
export const FLOW_STEPS_PICTOGRAM: PictogramName = uiPictogram("flowSteps");

export function parameterPictogram(key: string): PictogramName {
  return PARAMETER_PICTOGRAMS[key] ?? UNKNOWN;
}

export function modulePictogram(key: string): PictogramName {
  return MODULE_PICTOGRAMS[key] ?? UNKNOWN;
}

export function systemPictogram(key: string): PictogramName {
  return SYSTEM_PICTOGRAMS[key] ?? UNKNOWN;
}

/**
 * La clase de una hipótesis (`analysis/context.py`): a cuántos alcanza y si coincide con la
 * cabina. Sin color: una hipótesis no es una alerta, y el rótulo «correlación, no causa» va al lado.
 */
const HYPOTHESIS_KIND_MARKS: Readonly<Record<string, StateMark>> = {
  shared_environment: mark("stick-figures-roof", null),
  shared_unknown: mark("stick-figures-two", null),
  individual: mark("stick-figure", null),
  // La radiación registrada en la ventana (`solar_event`, §5.37.5) es un evento agudo: el dibujo
  // de la escala aguda del panel de radiación (`burst`, «la que dispara un evento solar»), el
  // mismo concepto y no un dibujo nuevo (§5.32 regla c). Sin color: una hipótesis no es una alerta.
  solar_event: mark("burst", null),
};

export function hypothesisKindMark(kind: string): StateMark {
  return HYPOTHESIS_KIND_MARKS[kind] ?? UNKNOWN_MARK;
}

/**
 * La marca del título de una hipótesis. La de un sistema declarado (`declared_system`, §5.34.4)
 * nombra ese sistema, y lleva su dibujo y no uno nuevo: es el mismo concepto que la fila del
 * sistema en `SystemsStatus` (§5.32 regla c). Sin color, como las demás clases.
 */
export function hypothesisMark(item: { kind: string; system?: { key: string } }): StateMark {
  if (item.kind === "declared_system" && item.system !== undefined) {
    return mark(systemPictogram(item.system.key), null);
  }
  return hypothesisKindMark(item.kind);
}

export type Presence = "present" | "elsewhere" | "undeclared";

/**
 * Dónde estaba cada tripulante respecto al módulo de la excursión, según la ubicación declarada.
 * Sin declarar es un dato ausente (cian); las otras dos son un hecho declarado, sin color.
 */
const PRESENCE_MARKS: Readonly<Record<Presence, StateMark>> = {
  present: mark("pin", null),
  elsewhere: mark("pin-arrow", null),
  undeclared: MISSING_MARK,
};

export function presenceMark(presence: Presence): StateMark {
  return PRESENCE_MARKS[presence];
}
