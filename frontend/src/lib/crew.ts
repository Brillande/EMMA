/**
 * A quien se mira: las reglas del selector de tripulante.
 *
 * La consola solo pedia el estado de `crew-01`, asi que con cuatro tripulantes en el almacen
 * tres no se podian ver. Elegir a quien se mira parece un desplegable y poco mas, pero un
 * sistema clinico que ensena los datos de una persona bajo el nombre de otra, o que firma un
 * reconocimiento en el registro equivocado, falla de la peor manera: en silencio y con buen
 * aspecto. Por eso lo que decide aqui son funciones puras con su prueba, y no logica suelta
 * dentro de un componente.
 *
 * Por la misma razon viven aqui el corte de Tierra (que ve de ese tripulante la consola de
 * Tierra: `groundCut`, `arrivalCut`) y cuando volver a pedir sus cinco preguntas
 * (`twinsRefreshKey`): un corte calculado de dos maneras, o una clave escrita a mano en cada
 * consola, tambien falla en silencio (§5.37.17).
 */

import type { CrewStatus, LinkSync } from "./api";

/** El tripulante por defecto: el mismo que el backend da cuando no se indica ninguno. */
export const DEFAULT_SUBJECT = "crew-01";

/**
 * Las opciones del selector: la tripulacion conocida y, si aun no figura en ella, el elegido.
 *
 * En la consola de Tierra la lista solo trae a quien ya tiene lecturas llegadas. El elegido
 * puede no estar todavia: se conserva en el control para que nunca muestre un nombre que no
 * es el que se esta pidiendo.
 */
export function crewOptions(members: readonly string[], selected: string): string[] {
  return members.includes(selected) ? [...members] : [...members, selected].sort();
}

/**
 * A quien pasar cuando el elegido no tiene ninguna lectura y otros si (se ha cargado otro
 * escenario, o datos de otra tripulacion). Sin esto la consola ofreceria "cargar datos" como
 * si el almacen estuviera vacio. `null` es quedarse: el elegido tiene datos, o no los tiene nadie.
 *
 * `membersAfterChoice` dice si la lista se pidio despues de elegir. Una de antes no confirma nada:
 * al elegir a un tripulante recien aparecido (la banda de pulso escribe su primera lectura en
 * `real-01` y la consola pasa a el), la lista vieja no lo trae, y la consola lo devolvia al primero
 * de la lista antes de que la nueva llegara.
 */
export function fallbackSubject(
  members: readonly string[],
  selected: string,
  selectedIsEmpty: boolean,
  membersAfterChoice = true,
): string | null {
  if (!selectedIsEmpty || !membersAfterChoice || members.includes(selected)) return null;
  return members[0] ?? null;
}

/**
 * El corte de Tierra: un instante de a bordo menos el tiempo de luz de ida. Lo posterior esta en
 * transito y Tierra no puede conocerlo. `null` sin efemerides: no hay retardo que aplicar.
 *
 * Es la unica cuenta del corte en la interfaz (§5.37.17). La consola de Tierra la hacia ademas a
 * mano (`mission.start + receivedUntil`, en segundos de mision) para el habitat, la linea base y
 * los documentos; y las ecografias, el dolor y el historial repetian cada uno la del reloj. Lo que
 * cambia de un panel a otro es el instante de partida, no la cuenta:
 * - con el estado (`App.tsx`, las cinco preguntas, el habitat, la linea base, los documentos), la
 *   ultima lectura de a bordo (`reference_time`): lo que Tierra tiene de las constantes;
 * - con lo que viaja al firmarse (ecografias, dolor, historial mision a mision), el reloj de ahora
 *   (`arrivalCut`): una declaracion viaja cuando se firma, haya o no telemetria nueva.
 */
export function groundCut(reference: string | number, oneWayMinutes: number | null): Date | null {
  if (oneWayMinutes === null) return null;
  const instant = typeof reference === "number" ? reference : Date.parse(reference);
  if (!Number.isFinite(instant)) {
    throw new RangeError(`instante de referencia no valido: ${reference}`);
  }
  return new Date(instant - oneWayMinutes * 60_000);
}

/**
 * El corte de Tierra con el enlace simulado (`GET /api/link-sync`, `core/link_sync.py`): el que da
 * el backend a partir del corte por tiempo de luz (`light`, el de `groundCut`). Con el enlace caído,
 * Tierra tiene hasta la caída; sin enlace declarado, el del tiempo de luz.
 *
 * La cuenta es del backend; aquí solo se defiende lo que no puede pasar: el corte nunca queda por
 * delante del tiempo de luz ni, con el enlace reteniéndolo, de la caída. Sin respuesta del enlace
 * (`sync` null) se queda el del tiempo de luz. `null` es «todo lo de a bordo»: sin efemérides y con
 * el enlace arriba.
 */
export function linkedCut(light: Date | null, sync: Pick<LinkSync, "cut" | "held" | "held_since"> | null): Date | null {
  if (sync === null) return light;
  const candidates = [light, sync.cut, sync.held ? sync.held_since : null]
    .map((value) => (value === null ? null : typeof value === "string" ? Date.parse(value) : value.getTime()))
    .filter((value): value is number => value !== null && Number.isFinite(value));
  return candidates.length === 0 ? null : new Date(Math.min(...candidates));
}

/**
 * El corte de lo que viaja al firmarse: el reloj (`now`, en milisegundos) menos un tiempo de luz.
 * `undefined` sin efemerides, que es como lo piden las rutas (`until` ausente: todo lo de a bordo).
 */
export function arrivalCut(oneWayMinutes: number | null, now: number): Date | undefined {
  return groundCut(now, oneWayMinutes) ?? undefined;
}

/**
 * Cuando volver a pedir las cinco preguntas de los gemelos (§5.36.3), en las dos consolas: al
 * cambiar la ultima lectura, el numero de lecturas, los reconocimientos, los seguimientos, las
 * decisiones o las fuentes (otro escenario con la misma fecha final). En Tierra, ademas, el dia
 * (UTC) del corte, que es el «hoy» con que el registro cuenta sus dias de espera; no el corte
 * entero, que se mueve con cada tiempo de luz y haria pedir sin que cambie nada.
 *
 * Antes cada consola escribia la suya a mano, y la de tripulacion no llevaba las fuentes.
 */
export function twinsRefreshKey(status: CrewStatus, cut: Date | null = null): string {
  return [
    cut?.toISOString().slice(0, 10) ?? "",
    status.data.reference_time,
    status.data.observations,
    status.alerts.filter((item) => item.acknowledged).length,
    status.followups.length,
    status.recommendations.filter((item) => item.decision != null).length,
    status.mission.sources.join(","),
  ].join("|");
}

/**
 * Cuándo volver a leer el perfil de línea base (§5.38.12), en las dos consolas: al cambiar la
 * última lectura, el número de lecturas o las fuentes (otro escenario con la misma fecha final).
 * Es la parte de `twinsRefreshKey` que habla de las lecturas: el perfil no depende de los
 * reconocimientos, los seguimientos ni las decisiones. En Tierra el corte va aparte (`until`).
 *
 * Antes cada consola la escribía a mano; en Tierra con `received`, en tripulación con el estado.
 */
export function baselineRefreshKey(status: CrewStatus): string {
  return [status.data.reference_time, status.data.observations, status.mission.sources.join(",")].join("|");
}
