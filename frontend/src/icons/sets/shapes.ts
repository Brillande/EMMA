/**
 * Formas básicas: las que ya usaba la interfaz como caracteres, con el mismo dibujo.
 *
 * Nivel de riesgo (circle, diamond, triangle, square), dato ausente (ring-dotted), no disponible
 * o fallo (slash-circle, cross), hecho (check), flechas de tendencia y los marcos de los
 * desplegables. El nombre es el dibujo; el significado lo pone la palabra de al lado.
 *
 * Rejilla de 24×24, trazo de 2. Todo ocupa de 3 a 21 para que a 12 px quede un trazo de 1 px y
 * un hueco visible. `ring-dotted` se traza a trazos sobre r = 8 (perímetro 50,27): el renderizado
 * usa 12 tramos de 4,19, que cierran el anillo sin un tramo roto.
 */

import type { PictogramSet } from "../types";

/**
 * Marco cuadrado de 16 × 16 y anillo de r = 8: las medidas de los marcos y anillos de este
 * conjunto, exportadas para que los demás (`common`, `ground`, `imaging`) se alineen con ellas en
 * vez de copiarlas.
 */
export const FRAME = { kind: "rect", x: 4, y: 4, width: 16, height: 16 } as const;
export const RING = { kind: "circle", cx: 12, cy: 12, r: 8 } as const;

export const shapes = {
  "shape-circle": { elements: [RING] },
  "shape-diamond": { elements: [{ kind: "polygon", points: "12,3 21,12 12,21 3,12" }] },
  "shape-triangle": { elements: [{ kind: "polygon", points: "12,4 21,20 3,20" }] },
  "shape-square": { elements: [{ ...FRAME, fill: true }] },
  "square-outline": { elements: [FRAME] },
  "ring-dotted": { elements: [{ ...RING, dashed: true }] },
  "slash-circle": {
    elements: [RING, { kind: "line", x1: 6.34, y1: 17.66, x2: 17.66, y2: 6.34 }],
  },
  cross: {
    elements: [
      { kind: "line", x1: 5, y1: 5, x2: 19, y2: 19 },
      { kind: "line", x1: 19, y1: 5, x2: 5, y2: 19 },
    ],
  },
  check: { elements: [{ kind: "polyline", points: "4,13 9.5,18.5 20,6" }] },
  "dot-small": { elements: [{ kind: "circle", cx: 12, cy: 12, r: 1.5, fill: true }] },
  dash: { elements: [{ kind: "line", x1: 5, y1: 12, x2: 19, y2: 12 }] },
  question: {
    elements: [
      { kind: "path", d: "M9 9.5a3 3 0 1 1 4.6 2.5c-1.1.7-1.6 1.5-1.6 2.5" },
      { kind: "circle", cx: 12, cy: 18.5, r: 0.8, fill: true },
    ],
  },
  "arrow-up": {
    elements: [
      { kind: "line", x1: 12, y1: 19, x2: 12, y2: 5 },
      { kind: "polyline", points: "6,11 12,5 18,11" },
    ],
  },
  "arrow-down": {
    elements: [
      { kind: "line", x1: 12, y1: 5, x2: 12, y2: 19 },
      { kind: "polyline", points: "6,13 12,19 18,13" },
    ],
  },
  "arrow-right": {
    elements: [
      { kind: "line", x1: 5, y1: 12, x2: 19, y2: 12 },
      { kind: "polyline", points: "13,6 19,12 13,18" },
    ],
  },
  "arrow-up-right": {
    elements: [
      { kind: "line", x1: 6, y1: 18, x2: 18, y2: 6 },
      { kind: "polyline", points: "9,6 18,6 18,15" },
    ],
  },
  "arrow-down-right": {
    elements: [
      { kind: "line", x1: 6, y1: 6, x2: 18, y2: 18 },
      { kind: "polyline", points: "18,9 18,18 9,18" },
    ],
  },
  "triangle-up-filled": { elements: [{ kind: "polygon", points: "12,5 20,19 4,19", fill: true }] },
  "triangle-down-filled": { elements: [{ kind: "polygon", points: "4,5 20,5 12,19", fill: true }] },
  // Arco de 300° en sentido antihorario, abierto arriba a la derecha, con la punta en el inicio.
  refresh: {
    elements: [
      { kind: "path", d: "M17.66 6.34A8 8 0 1 0 19.73 14.07" },
      { kind: "polyline", points: "22,6.34 17.66,6.34 17.66,10.7" },
    ],
  },
  // Casilla por marcar: cuadrado mayor con las esquinas redondeadas.
  "box-empty": {
    elements: [{ kind: "path", d: "M5.5 3h13a2.5 2.5 0 0 1 2.5 2.5v13a2.5 2.5 0 0 1-2.5 2.5h-13a2.5 2.5 0 0 1-2.5-2.5v-13a2.5 2.5 0 0 1 2.5-2.5z" }],
  },
  // Marco con su contenido, y marco con el hueco del contenido: van en pareja.
  "frame-filled": { elements: [FRAME, { kind: "rect", x: 8, y: 8, width: 8, height: 8, fill: true }] },
  "frame-empty": { elements: [FRAME, { kind: "rect", x: 8.5, y: 8.5, width: 7, height: 7 }] },
} as const satisfies PictogramSet;
