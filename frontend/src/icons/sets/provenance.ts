/**
 * Procedencia del dato: tipo de observación y entorno de la evidencia (`lib/provenance.ts`).
 *
 * Los tres tipos conservan el dibujo que ya tenían como caracteres: disco lleno (medido), disco a
 * medias (inferido) y triángulo apuntando a la derecha (predicho, hacia adelante en el tiempo).
 * Cada entorno de evidencia del backend tiene un dibujo nombrado por lo que representa: una
 * estación con paneles, un cohete, una cama, una puerta cerrada, un globo y una onda generada.
 */

import type { PictogramSet } from "../types";

export const provenance = {
  "dot-filled": { elements: [{ kind: "circle", cx: 12, cy: 12, r: 6.5, fill: true }] },
  "dot-half": {
    elements: [
      { kind: "circle", cx: 12, cy: 12, r: 8 },
      { kind: "path", d: "M12 4a8 8 0 0 0 0 16z", fill: true },
    ],
  },
  play: { elements: [{ kind: "polygon", points: "7,4 20,12 7,20" }] },
  // Entornos de evidencia.
  station: {
    elements: [
      { kind: "rect", x: 9, y: 9, width: 6, height: 6 },
      { kind: "line", x1: 6, y1: 12, x2: 9, y2: 12 },
      { kind: "line", x1: 15, y1: 12, x2: 18, y2: 12 },
      { kind: "rect", x: 2, y: 7, width: 4, height: 10 },
      { kind: "rect", x: 18, y: 7, width: 4, height: 10 },
    ],
  },
  rocket: {
    elements: [
      { kind: "path", d: "M12 3c3 3 4 7 4 11l-4 3-4-3c0-4 1-8 4-11z" },
      { kind: "path", d: "M8 14l-3 4h3" },
      { kind: "path", d: "M16 14l3 4h-3" },
      { kind: "circle", cx: 12, cy: 10, r: 1.5 },
    ],
  },
  bed: {
    elements: [
      { kind: "line", x1: 3, y1: 19, x2: 3, y2: 7 },
      { kind: "path", d: "M3 14h18v5" },
      { kind: "rect", x: 5, y: 10, width: 5, height: 4 },
    ],
  },
  "door-closed": {
    elements: [
      { kind: "rect", x: 6, y: 3, width: 12, height: 18 },
      { kind: "circle", cx: 15, cy: 12, r: 1, fill: true },
    ],
  },
  globe: {
    elements: [
      { kind: "circle", cx: 12, cy: 12, r: 8 },
      { kind: "line", x1: 4, y1: 12, x2: 20, y2: 12 },
      { kind: "path", d: "M12 4c-3 3-3 13 0 16" },
      { kind: "path", d: "M12 4c3 3 3 13 0 16" },
    ],
  },
  "wave-zigzag": { elements: [{ kind: "polyline", points: "2,12 6,5 10,19 14,5 18,19 22,12" }] },
} as const satisfies PictogramSet;
