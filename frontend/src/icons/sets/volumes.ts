/**
 * Pictogramas de los volúmenes TAC/RM, sus fases de contraste y sus lesiones (`volumes/`).
 *
 * Qué hay: la modalidad del estudio (anillo de gantry para el TAC, imán para la RM), una forma por
 * fase de contraste del vocabulario del backend (`volumes/contrast_phase.py`: gota tachada para
 * «sin contraste», vaso con pulso para la arterial, vaso que se ramifica para la portal-venosa;
 * el reloj de arena de la tardía y el signo igual de dos fases que coinciden están en `common`,
 * que los comparte con la crónica, Tierra, la PVT y el dolor; «no se sabe» usa `question` y «sin
 * declarar» `ring-dotted`, del conjunto básico). La goma de borrar de la cabecera limpiada al
 * entrar (`eraser`) vive en `common` desde la segunda pasada (2026-10-21): es también el mando de
 * quitar una zona (`lib/uiMarks.ts`). `volumes/marks.ts` dice qué dibujo acompaña a qué palabra.
 *
 * Segunda pasada (2026-10-21, §5.33.9): los signos de lo propio de este panel que no tiene concepto
 * en el vocabulario de la interfaz (`lib/uiMarks.ts`): la pila de cortes de un volumen de ejemplo,
 * el marco con la cruz del visor de Polaris y la esfera sombreada de su render, y en las tablas la
 * mancha de la lesión candidata, el cuadrado rayado de la densidad (HU) y los dos puntos unidos a
 * trazos de la distancia entre una lesión y su emparejada.
 *
 * Hoy no vuela ningún TAC: estos dibujos rotulan imagen de referencia previa al vuelo o de Tierra,
 * no diagnóstico a bordo. El nombre es el dibujo, no la fase ni la modalidad. Rejilla de 24×24,
 * trazo de 2, dentro de 3..21.
 */

import type { PictogramSet } from "../types";

export const volumes = {
  // TAC: anillo del gantry con la mesa debajo.
  gantry: {
    elements: [
      { kind: "circle", cx: 12, cy: 11, r: 7 },
      { kind: "circle", cx: 12, cy: 11, r: 2.5 },
      { kind: "line", x1: 3, y1: 21, x2: 21, y2: 21 },
    ],
  },
  // RM: imán en herradura, con las dos marcas de los polos.
  magnet: {
    elements: [
      { kind: "path", d: "M7 4v8a5 5 0 0 0 10 0V4" },
      { kind: "line", x1: 5, y1: 8, x2: 9, y2: 8 },
      { kind: "line", x1: 15, y1: 8, x2: 19, y2: 8 },
    ],
  },
  // Sin contraste: gota tachada.
  "drop-slash": {
    elements: [
      { kind: "path", d: "M12 3.5c3.5 4.5 6 7.5 6 11a6 6 0 0 1-12 0c0-3.5 2.5-6.5 6-11z" },
      { kind: "line", x1: 5, y1: 20, x2: 19, y2: 6 },
    ],
  },
  // Arterial: vaso con el trazo del pulso dentro.
  "tube-wave": {
    elements: [
      { kind: "line", x1: 3, y1: 6, x2: 21, y2: 6 },
      { kind: "line", x1: 3, y1: 18, x2: 21, y2: 18 },
      { kind: "polyline", points: "3,12 8,12 10,8 13,16 15,12 21,12" },
    ],
  },
  // Portal-venosa: tronco que se ramifica en dos, y cada rama otra vez.
  branches: {
    elements: [
      { kind: "line", x1: 12, y1: 21, x2: 12, y2: 11 },
      { kind: "path", d: "M12 11C12 7 8 6 5 4" },
      { kind: "path", d: "M12 11C12 7 16 6 19 4" },
      { kind: "line", x1: 8.5, y1: 7.5, x2: 6, y2: 11 },
      { kind: "line", x1: 15.5, y1: 7.5, x2: 18, y2: 11 },
    ],
  },

  // --- Segunda pasada: los signos propios del panel (§5.33.9) ---------------------------------
  // Volumen de ejemplo: tres cortes apilados, el de arriba entero y los de debajo por su canto.
  "slices-stacked": {
    elements: [
      { kind: "polygon", points: "3,8 9,4 21,4 15,8" },
      { kind: "polyline", points: "3,13 15,13 21,9" },
      { kind: "polyline", points: "3,18 15,18 21,14" },
    ],
  },
  // Visor de Polaris: marco con la cruz del cursor, abierta en el centro.
  "frame-crosshair": {
    elements: [
      { kind: "rect", x: 4, y: 4, width: 16, height: 16 },
      { kind: "line", x1: 12, y1: 7, x2: 12, y2: 10 },
      { kind: "line", x1: 12, y1: 14, x2: 12, y2: 17 },
      { kind: "line", x1: 7, y1: 12, x2: 10, y2: 12 },
      { kind: "line", x1: 14, y1: 12, x2: 17, y2: 12 },
    ],
  },
  // Render de Polaris: esfera con su sombra en media luna abajo a la derecha.
  "sphere-shaded": {
    elements: [
      { kind: "circle", cx: 12, cy: 12, r: 8 },
      { kind: "path", d: "M17.66 6.34A8 8 0 0 1 6.34 17.66A10 10 0 0 0 17.66 6.34z", fill: true },
    ],
  },
  // Lesión candidata: una mancha de contorno irregular, con dos entrantes para que a 14 px no se
  // lea como un círculo (la primera versión, casi redonda, se confundía con `shape-circle`).
  blob: {
    elements: [
      {
        kind: "path",
        d: "M9 4.5c2.5-1.5 4.5.5 6.5 0s4.5 2 4 5-1.5 3 0 5.5-2 5.5-5 4.5-3.5 1-6.5-.5S3 15 4.5 12 5.5 6.5 9 4.5z",
      },
    ],
  },
  // Densidad (HU): cuadrado rayado en diagonal.
  "square-hatched": {
    elements: [
      { kind: "rect", x: 4, y: 4, width: 16, height: 16 },
      { kind: "line", x1: 4, y1: 12, x2: 12, y2: 4 },
      { kind: "line", x1: 4, y1: 20, x2: 20, y2: 4 },
      { kind: "line", x1: 12, y1: 20, x2: 20, y2: 12 },
    ],
  },
  // Distancia del emparejado: dos puntos unidos por un trazo discontinuo.
  "dots-dashed-line": {
    elements: [
      { kind: "circle", cx: 6, cy: 18, r: 2, fill: true },
      { kind: "circle", cx: 18, cy: 6, r: 2, fill: true },
      { kind: "path", d: "M8 16L16 8", dashed: true },
    ],
  },
} as const satisfies PictogramSet;
