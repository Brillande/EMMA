/**
 * Pictogramas del hábitat: parámetros de cabina, módulos, sistemas, clase de hipótesis y dónde
 * estaba cada tripulante (`habitat/`).
 *
 * El nombre describe el dibujo; a qué clave del backend acompaña cada uno lo dice
 * `habitat/pictograms.ts`, y la palabra del backend va siempre al lado. Lo que ya tenía dibujo en
 * otro conjunto no se repite: la presión de cabina va con el manómetro (`gauge`) y la temperatura
 * con el termómetro (`thermometer`) de los indicadores, porque significan lo mismo; la ubicación
 * sin declarar con el anillo punteado (`ring-dotted`) de dato ausente.
 *
 * Dibujos. Cabina: dos átomos unidos (O2) y tres en fila con el del centro lleno (CO2); dos
 * átomos con el primero lleno (CO: la misma familia que O2 y CO2, un átomo de carbono y uno de
 * oxígeno); gota con la mitad inferior llena (humedad); altavoz con ondas (ruido); bombilla (luz,
 * y también el sistema de iluminación: es la misma cosa); molécula de centro lleno con tres
 * satélites (amoníaco); tres ondas verticales que suben (formaldehído, vapor que desprenden los
 * materiales). Agua y microbiología (2026-10-22): la gota con un anillo de seis lados (carbono
 * orgánico del agua), un lingote (plata), la gota con tres colonias (bacterias del agua), dos
 * líneas de aire con tres colonias (del aire), una superficie con tres colonias encima (de las
 * superficies) y una placa de cultivo (el bloque de microbiología); el bloque del agua lleva el
 * grifo de su sistema. Módulos: casa (hábitat principal), matraz (laboratorio), literas (camarotes),
 * escotilla con volante (esclusa). Sistemas: viento (revitalización de aire), válvula sobre una
 * tubería (control de presión), copo de nieve (control térmico), embudo (control de
 * contaminantes), batería (energía), ondas de radio (comunicaciones), grifo (agua). Hipótesis: una
 * figura (individual), dos figuras (compartida sin causa identificada), dos figuras bajo un tejado
 * (compartida con el hábitat). Ubicación: chincheta (estaba allí), chincheta con flecha (en otro
 * módulo). Dos cajas con una flecha de la una a la otra: los pasos del flujo de una hipótesis
 * (especificación §7). Barra llena: la muestra del sombreado de una gráfica en su leyenda. La bombilla, la
 * casa, el matraz, la chincheta y el altavoz con ondas (también la voz de la consola, §5.40) los
 * comparten otras áreas y viven en `common`.
 */

import type { PictogramSet } from "../types";

/** Una figura de palo (cabeza, tronco, brazos y piernas) con la cabeza en (x, y). */
function stickFigure(x: number, y: number, r: number, torso: number, arm: number, leg: number) {
  const neck = y + r;
  const hip = neck + torso;
  return [
    { kind: "circle", cx: x, cy: y, r },
    { kind: "line", x1: x, y1: neck, x2: x, y2: hip },
    { kind: "line", x1: x - arm, y1: neck + torso * 0.4, x2: x + arm, y2: neck + torso * 0.4 },
    { kind: "line", x1: x, y1: hip, x2: x - leg * 0.6, y2: hip + leg },
    { kind: "line", x1: x, y1: hip, x2: x + leg * 0.6, y2: hip + leg },
  ] as const;
}

export const habitat = {
  // --- Parámetros de cabina ---------------------------------------------------------------
  "atoms-two": {
    elements: [
      { kind: "circle", cx: 7.5, cy: 12, r: 3.5 },
      { kind: "circle", cx: 16.5, cy: 12, r: 3.5 },
      { kind: "line", x1: 11, y1: 12, x2: 13, y2: 12 },
    ],
  },
  "atoms-three": {
    elements: [
      { kind: "circle", cx: 4.5, cy: 12, r: 3 },
      { kind: "circle", cx: 12, cy: 12, r: 3, fill: true },
      { kind: "circle", cx: 19.5, cy: 12, r: 3 },
      { kind: "line", x1: 7.5, y1: 12, x2: 9, y2: 12 },
      { kind: "line", x1: 15, y1: 12, x2: 16.5, y2: 12 },
    ],
  },
  // Los dos átomos de `atoms-two`, con el primero lleno: el carbono y el oxígeno del CO. Antes
  // era la llama (`flame`), que en el dolor significa «quemante»: un dibujo, un significado.
  "atoms-two-one-filled": {
    elements: [
      { kind: "circle", cx: 7.5, cy: 12, r: 3.5, fill: true },
      { kind: "circle", cx: 16.5, cy: 12, r: 3.5 },
      { kind: "line", x1: 11, y1: 12, x2: 13, y2: 12 },
    ],
  },
  // La gota del dominio genitourinario es solo el contorno; esta lleva llena la mitad de abajo.
  "drop-half": {
    elements: [
      { kind: "path", d: "M12 3s6 7 6 11.5a6 6 0 0 1-12 0C6 10 12 3 12 3z" },
      { kind: "path", d: "M6 14.5a6 6 0 0 0 12 0z", fill: true },
    ],
  },
  "molecule-hub": {
    elements: [
      { kind: "circle", cx: 12, cy: 12, r: 3, fill: true },
      { kind: "circle", cx: 12, cy: 4, r: 2 },
      { kind: "circle", cx: 5, cy: 16.5, r: 2 },
      { kind: "circle", cx: 19, cy: 16.5, r: 2 },
      { kind: "line", x1: 12, y1: 9, x2: 12, y2: 6 },
      { kind: "line", x1: 9.47, y1: 13.63, x2: 6.69, y2: 15.42 },
      { kind: "line", x1: 14.53, y1: 13.63, x2: 17.31, y2: 15.42 },
    ],
  },
  vapor: {
    elements: [
      { kind: "path", d: "M7 20c-2.5-2.5-2.5-4.5 0-7s2.5-4.5 0-7" },
      { kind: "path", d: "M12 20c-2.5-2.5-2.5-4.5 0-7s2.5-4.5 0-7" },
      { kind: "path", d: "M17 20c-2.5-2.5-2.5-4.5 0-7s2.5-4.5 0-7" },
    ],
  },
  // --- Agua potable y microbiología (decimoquinta ronda, D18) ------------------------------
  // La gota de contorno de la humedad (`drop-half`), con un anillo de seis lados dentro: el
  // carbono orgánico del agua.
  "drop-hexagon": {
    elements: [
      { kind: "path", d: "M12 3s6 7 6 11.5a6 6 0 0 1-12 0C6 10 12 3 12 3z" },
      { kind: "polygon", points: "12,11.5 14.6,13 14.6,16 12,17.5 9.4,16 9.4,13" },
    ],
  },
  // Un lingote visto de frente, con su cara de arriba: la plata.
  ingot: {
    elements: [
      { kind: "polygon", points: "3,19 21,19 18,13 6,13" },
      { kind: "polygon", points: "6,13 18,13 16,8 8,8" },
    ],
  },
  // La gota con tres colonias dentro: las bacterias del agua.
  "drop-dots": {
    elements: [
      { kind: "path", d: "M12 3s6 7 6 11.5a6 6 0 0 1-12 0C6 10 12 3 12 3z" },
      { kind: "circle", cx: 9.8, cy: 13.8, r: 1.3, fill: true },
      { kind: "circle", cx: 14.2, cy: 13.8, r: 1.3, fill: true },
      { kind: "circle", cx: 12, cy: 17.4, r: 1.3, fill: true },
    ],
  },
  // Dos líneas de aire con tres colonias detrás: las bacterias del aire.
  "wind-dots": {
    elements: [
      { kind: "path", d: "M3 7h11a2.5 2.5 0 1 0-2.5-2.5" },
      { kind: "path", d: "M3 12h8" },
      { kind: "circle", cx: 16, cy: 13, r: 1.5, fill: true },
      { kind: "circle", cx: 20, cy: 17, r: 1.5, fill: true },
      { kind: "circle", cx: 14.5, cy: 19, r: 1.5, fill: true },
    ],
  },
  // Una superficie con tres colonias encima: las bacterias de las superficies.
  "surface-dots": {
    elements: [
      { kind: "line", x1: 3, y1: 19, x2: 21, y2: 19 },
      { kind: "path", d: "M4.5 19a2.5 2.5 0 0 1 5 0" },
      { kind: "path", d: "M10 19a3.5 3.5 0 0 1 7 0" },
      { kind: "path", d: "M17 19a2 2 0 0 1 4 0" },
    ],
  },
  // Una placa de cultivo vista desde arriba, con su borde y tres colonias: el bloque de la
  // microbiología del aire y las superficies.
  "petri-dish": {
    elements: [
      { kind: "circle", cx: 12, cy: 12, r: 9 },
      { kind: "circle", cx: 12, cy: 12, r: 7, dashed: true },
      { kind: "circle", cx: 9.5, cy: 10, r: 1.5, fill: true },
      { kind: "circle", cx: 14.5, cy: 10.5, r: 1.2, fill: true },
      { kind: "circle", cx: 11.5, cy: 15, r: 1.8, fill: true },
    ],
  },
  // --- Módulos (la casa y el matraz, en `common`) -------------------------------------------
  // Dos camas una sobre otra, cada una con su almohada: la cama de un análogo (`bed`) es una sola.
  "bunk-beds": {
    elements: [
      { kind: "line", x1: 4, y1: 3, x2: 4, y2: 21 },
      { kind: "path", d: "M4 9h16v3" },
      { kind: "rect", x: 6, y: 6, width: 4, height: 3 },
      { kind: "path", d: "M4 17h16v4" },
      { kind: "rect", x: 6, y: 14, width: 4, height: 3 },
    ],
  },
  hatch: {
    elements: [
      { kind: "circle", cx: 12, cy: 12, r: 8.5 },
      { kind: "circle", cx: 12, cy: 12, r: 3.5 },
      { kind: "line", x1: 14.5, y1: 9.5, x2: 18, y2: 6 },
      { kind: "line", x1: 9.5, y1: 9.5, x2: 6, y2: 6 },
      { kind: "line", x1: 9.5, y1: 14.5, x2: 6, y2: 18 },
      { kind: "line", x1: 14.5, y1: 14.5, x2: 18, y2: 18 },
    ],
  },
  // --- Sistemas ---------------------------------------------------------------------------
  wind: {
    elements: [
      { kind: "path", d: "M3 8h11a2.5 2.5 0 1 0-2.5-2.5" },
      { kind: "path", d: "M3 12h15a2.5 2.5 0 1 1-2.5 2.5" },
      { kind: "path", d: "M3 16h9a2.5 2.5 0 1 1-2.5 2.5" },
    ],
  },
  valve: {
    elements: [
      { kind: "line", x1: 3, y1: 13, x2: 21, y2: 13 },
      { kind: "line", x1: 3, y1: 18, x2: 21, y2: 18 },
      { kind: "line", x1: 12, y1: 13, x2: 12, y2: 7 },
      { kind: "line", x1: 7, y1: 7, x2: 17, y2: 7 },
    ],
  },
  // El copo («snowflake», control térmico) vive en `common` desde la decimonovena ronda: el coste
  // de medir lo usa para la muestra que se congela a bordo, y lo compartido no se duplica.
  funnel: { elements: [{ kind: "polygon", points: "3,4 21,4 14,12 14,20 10,20 10,12" }] },
  battery: {
    elements: [
      { kind: "rect", x: 2, y: 7, width: 17, height: 10 },
      { kind: "rect", x: 19, y: 10, width: 2.5, height: 4, fill: true },
      { kind: "rect", x: 4.5, y: 9.5, width: 4, height: 5, fill: true },
      { kind: "rect", x: 10, y: 9.5, width: 4, height: 5, fill: true },
    ],
  },
  "radio-waves": {
    elements: [
      { kind: "circle", cx: 12, cy: 17, r: 1.8, fill: true },
      { kind: "path", d: "M8 13a5.5 5.5 0 0 1 8 0" },
      { kind: "path", d: "M4.5 9.5a10.5 10.5 0 0 1 15 0" },
    ],
  },
  tap: {
    elements: [
      { kind: "path", d: "M4 10h8a5 5 0 0 1 5 5v3" },
      { kind: "line", x1: 8, y1: 10, x2: 8, y2: 6 },
      { kind: "line", x1: 5, y1: 6, x2: 11, y2: 6 },
      { kind: "circle", cx: 17, cy: 21.5, r: 1, fill: true },
    ],
  },
  // --- Clase de hipótesis -----------------------------------------------------------------
  "stick-figure": { elements: stickFigure(12, 5, 2.5, 7, 5, 6.5) },
  "stick-figures-two": {
    elements: [...stickFigure(7, 5, 2.2, 6.8, 3.5, 7), ...stickFigure(17, 5, 2.2, 6.8, 3.5, 7)],
  },
  "stick-figures-roof": {
    elements: [
      { kind: "polyline", points: "2,8 12,2 22,8" },
      ...stickFigure(7, 11, 2, 4.5, 3.5, 4.5),
      ...stickFigure(17, 11, 2, 4.5, 3.5, 4.5),
    ],
  },
  // La chincheta sola (`pin`) está en `common`; con flecha, solo aquí.
  "pin-arrow": {
    elements: [
      { kind: "path", d: "M7.5 20s-5-4.7-5-8.7a5 5 0 0 1 10 0c0 4-5 8.7-5 8.7z" },
      { kind: "circle", cx: 7.5, cy: 11.3, r: 1.6, fill: true },
      { kind: "line", x1: 14, y1: 14, x2: 21.5, y2: 14 },
      { kind: "polyline", points: "18.5,11 21.5,14 18.5,17" },
    ],
  },
  // Los pasos del flujo (`squares-arrow`) subieron a `common` en la decimocuarta ronda (§5.34.6):
  // los usan también los pasos de una alerta.
  // --- Leyenda de una gráfica -------------------------------------------------------------
  "bar-filled": { elements: [{ kind: "rect", x: 7, y: 4, width: 10, height: 16, fill: true }] },
} as const satisfies PictogramSet;
