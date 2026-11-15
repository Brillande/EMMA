/**
 * Pictogramas de la misión y de la vigilancia: fases, gravedad del momento, eventos declarados,
 * perfil de misión y sus aspectos, capacidades del sistema (`dashboard/MissionTimeline.tsx`,
 * `dashboard/MissionProfileView.tsx`, `MonitoringPanel` de `dashboard/CrewConsole.tsx`).
 *
 * El nombre describe el dibujo; qué fase, qué aspecto o qué capacidad es lo dice la palabra del
 * backend que va al lado (`dashboard/missionPictograms.ts`, `dashboard/monitoring.ts`). Dibujos,
 * en el orden en que se usan:
 *
 * - Fases: cohete de pie sobre su rampa; onda que se amortigua hasta quedar plana; nivel de
 *   burbuja; paracaídas con su carga (también la etapa posvuelo de la crónica: misma casa,
 *   `dashboard`); figura (cabeza y torso) de pie sobre el suelo.
 * - Gravedad: bola apoyada en el suelo (solo cuando el backend dice que se está en Tierra; en
 *   vuelo la frase es texto libre de configuración y va sola, sin un dibujo que la contradiga).
 * - Eventos: casco con visera y chincheta de mapa (`helmet`, `pin`, en `common`); maletín; y,
 *   desde la decimoctava ronda (U4), el cambio de turno: una luna creciente sobre una flecha
 *   horizontal (el sueño que se mueve de hora). No es la luna con «z» de los indicadores de
 *   sueño (`moon-z`): aquí no se mide nada, se declara que el horario se desplazó.
 * - Perfiles: planeta con un satélite en arco; luna con cráteres; arco hasta un planeta;
 *   bandera sobre un planeta; y, desde el 2026-11-03, la Tierra y la Luna con un lazo que la
 *   rodea (espacio cislunar).
 * - Aspectos propios de aquí (2026-11-03): granos sobre el suelo (polvo de superficie) y un sol
 *   junto a una creciente (ciclo de día y noche).
 * - Aspectos, todos de `common`: punto que emite dos arcos (`signal-arcs`); flecha en U
 *   (`arrow-u-turn`); bandeja con flecha que entra (`tray-arrow-down`); reloj de arena
 *   (`hourglass`). (La gravedad y la distancia reutilizan los dibujos de los peligros RIDGE: son
 *   el mismo concepto, y un concepto no lleva dos dibujos.)
 * - Capacidades: sol con tres chorros; y de `common` la tarjeta de identidad, los dos eslabones,
 *   el calendario y la campana. (El retardo con Tierra es el mismo dibujo que el retardo de
 *   comunicaciones del perfil, y la dosis de carrera el trébol de la familia de dosis.) Los cinco
 *   que nacieron aquí (señal, flecha en U, bandeja, tarjeta, eslabones) pasaron a `common` en la
 *   segunda pasada (2026-10-21): nombran títulos y mandos de toda la interfaz (`lib/uiMarks.ts`).
 *
 * - Conjunción solar (decimoquinta ronda, D6): el Sol, con cuatro rayos cortos en diagonal, entre
 *   dos puntos alineados con él (la Tierra y el objetivo). No es el retardo (las ondas) ni los
 *   eventos solares (el sol con chorros).
 *
 * Rejilla de 24×24, trazo de 2, pensado para leerse a 12 px: los detalles pequeños (ventanas,
 * costuras) se han quitado a propósito. Revisado sobre captura (2026-10-20): la primera versión
 * del cohete con torre parecía una montaña con bandera, la línea entre bandas un menú, el
 * paracaídas sin cuerda inferior una bombilla y la figura de palo un ancla; de ahí los dibujos
 * de ahora.
 */

import type { PictogramSet } from "../types";

export const mission = {
  // Fases de la misión. Cohete con la base plana sobre la rampa y las aletas apoyadas: el de
  // «vuelo real» (`provenance.ts`) va en el aire, sin suelo.
  "rocket-pad": {
    elements: [
      { kind: "path", d: "M12 2.5c2.5 2.5 3.5 6 3.5 10V16h-7v-3.5c0-4 1-7.5 3.5-10z" },
      { kind: "path", d: "M8.5 12.5L6 17.5h2.5" },
      { kind: "path", d: "M15.5 12.5L18 17.5h-2.5" },
      { kind: "line", x1: 3, y1: 20.5, x2: 21, y2: 20.5 },
    ],
  },
  "wave-damped": {
    elements: [{ kind: "path", d: "M3 12C3.8 5 5.2 5 6 12S8.2 18 9 12S11 8 12 12S14 15 15 12S17 10 18 12L21 12" }],
  },
  // Nivel de burbuja: el tubo, las dos marcas que lo sobresalen y la burbuja en medio.
  "bubble-level": {
    elements: [
      { kind: "rect", x: 2.5, y: 8.5, width: 19, height: 7 },
      { kind: "line", x1: 8.5, y1: 6, x2: 8.5, y2: 18 },
      { kind: "line", x1: 15.5, y1: 6, x2: 15.5, y2: 18 },
      { kind: "circle", cx: 12, cy: 12, r: 1.6, fill: true },
    ],
  },
  // Cúpula con su borde recto, dos cuerdas y la carga (que baja hasta y = 22).
  parachute: {
    elements: [
      { kind: "path", d: "M3 11a9 9 0 0 1 18 0" },
      { kind: "line", x1: 3, y1: 11, x2: 21, y2: 11 },
      { kind: "line", x1: 3, y1: 11, x2: 10.5, y2: 19 },
      { kind: "line", x1: 21, y1: 11, x2: 13.5, y2: 19 },
      { kind: "rect", x: 10, y: 19, width: 4, height: 3 },
    ],
  },
  // Cabeza y torso, de pie sobre la línea del suelo.
  "figure-standing": {
    elements: [
      { kind: "circle", cx: 12, cy: 5.5, r: 3 },
      { kind: "path", d: "M7.5 21v-6.5a4.5 4.5 0 0 1 9 0V21" },
      { kind: "line", x1: 3, y1: 21, x2: 21, y2: 21 },
    ],
  },
  // Gravedad del momento en Tierra: bola apoyada en el suelo.
  "ball-on-line": {
    elements: [
      { kind: "circle", cx: 12, cy: 15.5, r: 4.5 },
      { kind: "line", x1: 4, y1: 20, x2: 20, y2: 20 },
    ],
  },
  briefcase: {
    elements: [
      { kind: "rect", x: 3, y: 8, width: 18, height: 12 },
      { kind: "path", d: "M9 8V5h6v3" },
      { kind: "line", x1: 3, y1: 13, x2: 21, y2: 13 },
    ],
  },
  // Cambio de turno: luna creciente arriba y una flecha de lado a lado debajo.
  "crescent-arrow": {
    elements: [
      { kind: "path", d: "M15 3.5a6 6 0 1 0 4.5 9A5 5 0 0 1 15 3.5z" },
      { kind: "line", x1: 3, y1: 19.5, x2: 20, y2: 19.5 },
      { kind: "path", d: "M17 16.5l3 3-3 3" },
    ],
  },
  // Perfiles de misión: órbita baja, superficie lunar, tránsito y superficie de Marte (el del
  // espacio cislunar va después, con los dibujos añadidos el 2026-11-03).
  "globe-satellite": {
    elements: [
      { kind: "circle", cx: 12, cy: 13.5, r: 6 },
      { kind: "path", d: "M3 11a9 7.5 0 0 1 18 0" },
      { kind: "circle", cx: 12, cy: 3.5, r: 1.5, fill: true },
    ],
  },
  "moon-craters": {
    elements: [
      { kind: "circle", cx: 12, cy: 12, r: 8.5 },
      { kind: "circle", cx: 8.5, cy: 10, r: 2 },
      { kind: "circle", cx: 14.5, cy: 14.5, r: 2.8 },
      { kind: "circle", cx: 14, cy: 7.5, r: 1.2 },
    ],
  },
  "arc-planet": {
    elements: [
      { kind: "path", d: "M3 21C3 13 8 8 14.5 6.5" },
      { kind: "circle", cx: 8, cy: 13, r: 1.5, fill: true },
      { kind: "circle", cx: 18, cy: 6, r: 3 },
    ],
  },
  "planet-flag": {
    elements: [
      { kind: "path", d: "M3 21a9 9 0 0 1 18 0" },
      { kind: "line", x1: 12, y1: 12, x2: 12, y2: 3 },
      { kind: "path", d: "M12 3.5h6l-1.5 2 1.5 2h-6" },
    ],
  },
  // Espacio cislunar (2026-11-03): la Tierra a la izquierda, la Luna pequeña a la derecha y un
  // lazo que sale de la Tierra y rodea la Luna. No es el arco abierto hasta un planeta del
  // tránsito (`arc-planet`): aquí el camino vuelve.
  "earth-moon-loop": {
    elements: [
      { kind: "circle", cx: 5.5, cy: 12, r: 3.5 },
      { kind: "circle", cx: 17.5, cy: 12, r: 1.75 },
      { kind: "path", d: "M9 10.5C13 5 22.5 5 22.5 12S13 19 9 13.5" },
    ],
  },
  // Aspectos nuevos del perfil (2026-11-03). Polvo de superficie: granos sueltos sobre el suelo.
  "grains-over-line": {
    elements: [
      { kind: "circle", cx: 6, cy: 14, r: 1.25, fill: true },
      { kind: "circle", cx: 11, cy: 9, r: 1.25, fill: true },
      { kind: "circle", cx: 15, cy: 15, r: 1.25, fill: true },
      { kind: "circle", cx: 18.5, cy: 8, r: 1.25, fill: true },
      { kind: "circle", cx: 9, cy: 4.5, r: 1.25, fill: true },
      { kind: "line", x1: 3, y1: 20, x2: 21, y2: 20 },
    ],
  },
  // Ciclo de día y noche: un sol con cuatro rayos a la izquierda y una luna creciente a la
  // derecha. No es la conjunción (`dot-sun-dot`, el Sol entre dos puntos) ni el cambio de turno
  // (`crescent-arrow`, la creciente sobre una flecha).
  "sun-and-crescent": {
    elements: [
      // El sol y sus rayos, todos a la misma distancia del disco (de 4 a 5,5 desde el centro).
      { kind: "circle", cx: 6, cy: 12, r: 2.5 },
      { kind: "line", x1: 6, y1: 6.5, x2: 6, y2: 8 },
      { kind: "line", x1: 6, y1: 16, x2: 6, y2: 17.5 },
      { kind: "line", x1: 0.5, y1: 12, x2: 2, y2: 12 },
      { kind: "line", x1: 10, y1: 12, x2: 11.5, y2: 12 },
      // La creciente: arco exterior de radio 4,5 (borde izquierdo en x ≈ 14,9, sin tocar el rayo)
      // e interior de 5,5, los dos mayores que la mitad de su cuerda (4,2).
      { kind: "path", d: "M21 7.8A4.5 4.5 0 1 0 21 16.2A5.5 5.5 0 0 1 21 7.8z" },
    ],
  },
  "sun-streams": {
    elements: [
      { kind: "circle", cx: 7, cy: 12, r: 4 },
      { kind: "line", x1: 13, y1: 8, x2: 21, y2: 6 },
      { kind: "line", x1: 13, y1: 12, x2: 21, y2: 12 },
      { kind: "line", x1: 13, y1: 16, x2: 21, y2: 18 },
    ],
  },
  // Conjunción solar: los dos puntos y el Sol en una línea; los rayos, en diagonal: en vertical,
  // con los dos puntos, se leía a 14 px como una mira (captura de D6); y no horizontales hacia un
  // lado, que es «sun-streams».
  "dot-sun-dot": {
    elements: [
      { kind: "circle", cx: 3.5, cy: 12, r: 1.75, fill: true },
      { kind: "circle", cx: 12, cy: 12, r: 4 },
      { kind: "line", x1: 15.5, y1: 8.5, x2: 17.5, y2: 6.5 },
      { kind: "line", x1: 8.5, y1: 8.5, x2: 6.5, y2: 6.5 },
      { kind: "line", x1: 15.5, y1: 15.5, x2: 17.5, y2: 17.5 },
      { kind: "line", x1: 8.5, y1: 15.5, x2: 6.5, y2: 17.5 },
      { kind: "circle", cx: 20.5, cy: 12, r: 1.75, fill: true },
    ],
  },
} as const satisfies PictogramSet;
