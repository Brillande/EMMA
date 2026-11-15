/**
 * Con que pictograma va cada palabra de la cronica y de sus piezas (`TimelinePieces.tsx`).
 *
 * Existe para que la vista no elija dibujos: aqui esta, en tablas, que forma acompaña a cada
 * clave que da el backend (`app/timeline.py`: el `tipo` de un hecho y la etapa de §10; Polaris
 * `estado_rutina`: el estado de una medida periodica; `cascada_mapa`: quien recalcula). La
 * palabra sigue siendo la del backend o el rotulo que ya existia; el dibujo lo da
 * `icons/sets/timeline.ts`, y el significado de cada uno, `compliance/hmi-state-of-the-art.md`
 * §5.32.1.
 *
 * Los tipos y las etapas llegan como texto libre (`string`): una clave que la interfaz no conoce
 * se enseña con su palabra y el dibujo de «desconocido» (`UNKNOWN_MARK`), no tumba la cronica
 * entera ni se disfraza de otra. Las señales con color son las de siempre (tabla F.5-1): el
 * triangulo amarillo del limite normativo o de lo que no cuadra, el rombo azul de la zona de
 * confort o del rango objetivo, el anillo punteado en cian de un ahora que no sale de los datos, y
 * el circulo tachado en gris («no disponible», `UNAVAILABLE_MARK`) de lo que nunca corrio.
 */

import type { DependsView, RoutineState, TimelineAsOf } from "../lib/api";
import type { PictogramName } from "../icons/registry";
import { type StateMark, MISSING_MARK, UNAVAILABLE_MARK, UNKNOWN_MARK, UNKNOWN_PICTOGRAM, mark } from "../lib/marks";

/** Un hecho de la cronica, por su `tipo` (los de `app/timeline.py`). Sin color: no es una señal. */
export const EVENT_KIND_MARKS: Readonly<Record<string, StateMark>> = {
  alerta: mark("bell", null),
  contramedida: mark("bandage", null),
  mision: mark("helmet", null),
  habitat: mark("house", null),
  sensor: mark("arcs-dot", null),
  recurso: mark("cube", null),
  imagen: mark("picture", null),
  sistema: mark("gear", null),
  fase: mark("stairs", null),
  posvuelo: mark("sunrise", null),
  // Una misión previa declarada (historial misión a misión): el cohete de «vuelo espacial».
  carrera: mark("rocket", null),
};

/** Las etapas de la especificacion (§10), con las claves de `STAGES` en `app/timeline.py`. */
export const STAGE_MARKS: Readonly<Record<string, StateMark>> = {
  // La carrera de antes de esta misión: «mirar atrás», el signo de lo anterior (`previous`), el
  // mismo de la columna «Misión» del historial misión a misión.
  career: mark("clock-rewind", null),
  preflight: mark("clipboard", null),
  "mission-day": mark("calendar-day", null),
  intervention: mark("kit-case", null),
  followup: mark("magnifier", null),
  postflight: mark("parachute", null),
  unplaced: mark("clock", null),
};

/**
 * La clase del limite de cabina de una excursion (`ChronicleEvent.severity`): el amarillo con
 * triangulo del limite normativo, el azul con rombo de la zona de confort o del rango objetivo,
 * como en el panel del habitat.
 */
export const SEVERITY_MARKS: Readonly<Record<"health" | "performance" | "target", StateMark>> = {
  health: mark("shape-triangle", "yellow"),
  performance: mark("shape-diamond", "blue"),
  target: mark("shape-diamond", "blue"),
};

/**
 * Medidas periodicas (Polaris `estado_rutina`). La que va a su ritmo no lleva señal; la atrasada,
 * un reloj de arena sin color (informacion, no alarma); la rota, el triangulo amarillo de "falta
 * un dato, hay que mirarlo" (F.5-1); la que nunca corrio, la marca de "no disponible" de toda la
 * interfaz, el circulo tachado en gris (`UNAVAILABLE_MARK`: en un escenario sin esas medidas es lo
 * esperado). Hasta la segunda pasada (§5.33.1) llevaba el anillo punteado en gris: el anillo es
 * de lo ausente o caducado (cian), y el gris de lo no disponible tiene su propio dibujo.
 */
export const ROUTINE_MARKS: Readonly<Record<RoutineState["state"], StateMark>> = {
  "al-dia": mark(null, null),
  atrasada: mark("hourglass", null),
  rota: mark("shape-triangle", "yellow"),
  "nunca-corrio": UNAVAILABLE_MARK,
};

/**
 * La racha de una medida periodica (`routines.streaks`): la fila de puntos de «periodica» (la misma
 * del modo `periodic-noninvasive` de lo que cuesta medir), sin color. Es un recuento, no una señal:
 * la tabla F.5-1 no tiene un color de «premio», y no se le inventa.
 */
export const STREAK_MARK: StateMark = mark("dots-row", null);

/** Quien se ocupa si cambia un dato (Polaris `cascada_mapa`): el sistema solo, o una persona. */
export const DEPENDS_MODE_MARKS: Readonly<Record<DependsView["affected"][number]["mode"], StateMark>> = {
  auto: mark("chip", null),
  humano: mark("person", null),
};

/** Lo que no cuadra entre dos informes (Polaris `atascos`): amarillo con triangulo. */
export const INCONGRUENCE_MARK: StateMark = mark("shape-triangle", "yellow");

function lookup(table: Readonly<Record<string, StateMark>>, key: string): StateMark {
  return Object.hasOwn(table, key) ? (table[key] ?? UNKNOWN_MARK) : UNKNOWN_MARK;
}

export function eventKindMark(kind: string): StateMark {
  return lookup(EVENT_KIND_MARKS, kind);
}

export function stageMark(key: string): StateMark {
  return lookup(STAGE_MARKS, key);
}

/**
 * El dibujo del título de una etapa (`PanelTitle` exige uno): el de su marca, y el de
 * «desconocido» si la marca no lo tuviera. Todas las etapas tienen dibujo; esto solo estrecha el tipo.
 */
export function stagePictogram(key: string): PictogramName {
  return stageMark(key).pictogram ?? UNKNOWN_PICTOGRAM;
}

export function routineMark(state: string): StateMark {
  return lookup(ROUTINE_MARKS, state);
}

export function dependsModeMark(mode: string): StateMark {
  return lookup(DEPENDS_MODE_MARKS, mode);
}

/**
 * El ahora de una pieza: si sale de las lecturas no hay nada que señalar; si sale del corte de
 * Tierra o del reloj real es que faltan lecturas, y va como dato ausente (anillo punteado, cian).
 */
export function asOfMark(source: TimelineAsOf["as_of_source"]): StateMark {
  return source === "data" ? mark(null, null) : MISSING_MARK;
}
