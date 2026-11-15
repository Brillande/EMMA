/**
 * Que pictograma acompaña a cada palabra de la mision: fases, gravedad del momento, eventos
 * declarados, perfil y sus aspectos, conjuncion solar (`icons/sets/mission.ts`).
 *
 * Existe para que los paneles no elijan dibujos: las palabras las da el backend y aqui solo se
 * dice que forma va junto a cada clave de la API. Una clave que la interfaz no conoce se enseña
 * con su palabra y el dibujo de «desconocido» (`pictogramTable.ts`): un backend con una fase, un
 * evento o un perfil nuevo no tumba la consola ni le supone un dibujo.
 *
 * La gravedad del momento solo lleva dibujo cuando el backend la fija el mismo: con los datos de
 * despues del vuelo su frase dice que se esta en Tierra (`core/mission.py`), y va la bola apoyada
 * en el suelo. El resto del tiempo la frase es la gravedad de configuracion, texto libre (puede
 * ser la de una orbita o la de una superficie), y un dibujo que afirmara que se flota podria
 * contradecir a la palabra: va la palabra sola. Nada de aqui lee esa configuracion ni compone
 * texto: la frase es `gravity_display`, tal cual.
 */

import type { PictogramName } from "../icons/registry";
import { uiPictogram } from "../lib/uiMarks";
import { type PictogramTable, pictogramFor } from "./pictogramTable";

const PHASES: PictogramTable = {
  preflight: "rocket-pad",
  adaptation: "wave-damped",
  stable: "bubble-level",
  return: "parachute",
  postflight: "figure-standing",
};

const EVENTS: PictogramTable = {
  eva: "helmet",
  workload: "briefcase",
  location: "pin",
  shift: "crescent-arrow",
};

const PROFILES: PictogramTable = {
  leo: "globe-satellite",
  "cislunar": "earth-moon-loop",
  "lunar-surface": "moon-craters",
  "mars-transit": "arc-planet",
  "mars-surface": "planet-flag",
};

/**
 * La gravedad, la distancia y el entorno de radiación llevan el dibujo de su peligro RIDGE
 * (`icons/sets/domains.ts`): son el mismo concepto, y un concepto no tiene dos dibujos. El retardo de comunicaciones es el mismo
 * que el de la capacidad «retardo con Tierra» (`monitoring.ts`), por lo mismo. La capacidad o
 * autonomía médica (§5.36.7) lleva el maletín con la cruz de la etapa «intervención» de la
 * cronología (`timelineMarks.ts`): no había otro dibujo de asistencia médica y no se añade uno.
 * El polvo de superficie y el ciclo de día y noche (2026-11-03) no tenían dibujo en ninguna parte
 * de la interfaz, y llevan uno propio de `icons/sets/mission.ts`.
 */
const ASPECTS: PictogramTable = {
  comm_delay: uiPictogram("lightTime"),
  gravity_regime: "ridge-gravity",
  return_or_evacuation: "arrow-u-turn",
  resupply: "tray-arrow-down",
  typical_duration: "hourglass",
  distance: "ridge-distance",
  radiation_environment: "ridge-radiation",
  surface_dust: "grains-over-line",
  day_night_cycle: "sun-and-crescent",
  medical_capability: "kit-case",
};

/**
 * La conjuncion solar: el Sol entre dos puntos alineados (la Tierra y el objetivo). Es su propio
 * concepto: no es el retardo (`lightTime`, que sigue igual en conjuncion) ni el sol de los eventos
 * solares (`sun-streams`), que es meteorologia espacial.
 */
const CONJUNCTION: PictogramName = "dot-sun-dot";

export function conjunctionPictogram(): PictogramName {
  return CONJUNCTION;
}

export function phasePictogram(key: string): PictogramName | null {
  return pictogramFor(PHASES, key);
}

export function eventPictogram(kind: string): PictogramName | null {
  return pictogramFor(EVENTS, kind);
}

export function profilePictogram(id: string): PictogramName | null {
  return pictogramFor(PROFILES, id);
}

export function aspectPictogram(key: string): PictogramName | null {
  return pictogramFor(ASPECTS, key);
}

/** La gravedad del momento: en Tierra tras el vuelo; el resto, la palabra sola (ver cabecera). */
export function gravityPictogram(phase: string): PictogramName | null {
  return phase === "postflight" ? "ball-on-line" : null;
}
