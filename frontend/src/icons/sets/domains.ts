/**
 * Pictogramas de los dominios clínicos y de los peligros RIDGE.
 *
 * Las claves son las del `Domain` y el `Ridge` del backend (`app/ingest/codes.py`), con el
 * prefijo `domain-` o `ridge-`: `domains.test.ts` lee el fichero de Python y exige un dibujo por
 * valor del enum. Cada dibujo es distinto del de cualquier familia de indicadores
 * (`indicators.ts`): el dominio nombra un área, la familia una medida, y no se confunden.
 *
 * Dibujos: corazón; cabeza con una onda; trébol dentro de un círculo; hueso; escudo; ojo de
 * frente; gota; columna de vértebras; manzana. RIDGE: sol con rayos (radiación); un punto
 * solo en un marco (aislamiento); dos cuerpos con un trazo discontinuo entre ellos (distancia);
 * flecha que cae sobre el suelo (gravedad); nube (entorno cerrado y hostil).
 */

import type { PictogramSet } from "../types";

/** Contorno de un corazón, común al dominio cardiovascular y a la familia del pulso. */
export const HEART_OUTLINE = {
  kind: "path",
  d: "M12 20l-6.5-6.6a4.2 4.2 0 0 1 5.7-5.7l.8.8.8-.8a4.2 4.2 0 0 1 5.7 5.7z",
} as const;

export const domains = {
  "domain-cardiovascular": { elements: [HEART_OUTLINE] },
  // Cabeza separada de los hombros (hueco de 1,5 unidades) y una onda de cuatro vértices dentro.
  "domain-behavioral": {
    elements: [
      { kind: "circle", cx: 12, cy: 7.5, r: 5 },
      { kind: "path", d: "M5 21a7 7 0 0 1 14 0" },
      { kind: "polyline", points: "8.5,7.5 10.5,5.5 13.5,9.5 15.5,7.5" },
    ],
  },
  "domain-radiation": {
    elements: [
      { kind: "circle", cx: 12, cy: 12, r: 9.5 },
      { kind: "path", d: "M10.7 9.75L9 6.8A6 6 0 0 1 15 6.8L13.3 9.75A2.6 2.6 0 0 0 10.7 9.75Z", fill: true },
      { kind: "path", d: "M14.6 12L18 12A6 6 0 0 1 15 17.2L13.3 14.25A2.6 2.6 0 0 0 14.6 12Z", fill: true },
      { kind: "path", d: "M10.7 14.25L9 17.2A6 6 0 0 1 6 12L9.4 12A2.6 2.6 0 0 0 10.7 14.25Z", fill: true },
    ],
  },
  // Silueta de hueso: cuatro discos y una barra, todo relleno.
  "domain-bone": {
    elements: [
      { kind: "circle", cx: 6.5, cy: 9.5, r: 2.5, fill: true },
      { kind: "circle", cx: 6.5, cy: 14.5, r: 2.5, fill: true },
      { kind: "circle", cx: 17.5, cy: 9.5, r: 2.5, fill: true },
      { kind: "circle", cx: 17.5, cy: 14.5, r: 2.5, fill: true },
      { kind: "rect", x: 6.5, y: 10, width: 11, height: 4, fill: true },
    ],
  },
  "domain-immune": {
    elements: [{ kind: "path", d: "M12 3l8 3v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6z" }],
  },
  // Ojo de frente con la pupila; la familia de visión es el globo ocular desde arriba.
  "domain-neuro-ocular": {
    elements: [
      { kind: "path", d: "M2 12s4-6 10-6 10 6 10 6-4 6-10 6S2 12 2 12z" },
      { kind: "circle", cx: 12, cy: 12, r: 2.5, fill: true },
    ],
  },
  "domain-genitourinary": {
    elements: [{ kind: "path", d: "M12 3s6 7 6 11.5a6 6 0 0 1-12 0C6 10 12 3 12 3z" }],
  },
  "domain-musculoskeletal": {
    elements: [
      { kind: "rect", x: 9, y: 3, width: 6, height: 4 },
      { kind: "rect", x: 9, y: 10, width: 6, height: 4 },
      { kind: "rect", x: 9, y: 17, width: 6, height: 4 },
    ],
  },
  "domain-nutrition": {
    elements: [
      { kind: "path", d: "M12 8c-1.5-1.5-6-1.5-6 3.5S9 21 12 21s6-4.5 6-9.5-4.5-5-6-3.5z" },
      { kind: "line", x1: 12, y1: 8, x2: 12, y2: 4 },
      { kind: "path", d: "M12 6c1-2 3-2.5 4.5-2" },
    ],
  },
  "ridge-radiation": {
    elements: [
      { kind: "circle", cx: 12, cy: 12, r: 3.5 },
      { kind: "line", x1: 12, y1: 2.5, x2: 12, y2: 5.5 },
      { kind: "line", x1: 12, y1: 18.5, x2: 12, y2: 21.5 },
      { kind: "line", x1: 2.5, y1: 12, x2: 5.5, y2: 12 },
      { kind: "line", x1: 18.5, y1: 12, x2: 21.5, y2: 12 },
      { kind: "line", x1: 5.3, y1: 5.3, x2: 7.4, y2: 7.4 },
      { kind: "line", x1: 16.6, y1: 16.6, x2: 18.7, y2: 18.7 },
      { kind: "line", x1: 5.3, y1: 18.7, x2: 7.4, y2: 16.6 },
      { kind: "line", x1: 16.6, y1: 7.4, x2: 18.7, y2: 5.3 },
    ],
  },
  "ridge-isolation": {
    elements: [
      { kind: "rect", x: 3, y: 3, width: 18, height: 18 },
      { kind: "circle", cx: 12, cy: 12, r: 2, fill: true },
    ],
  },
  "ridge-distance": {
    elements: [
      { kind: "circle", cx: 5.5, cy: 17, r: 3 },
      { kind: "circle", cx: 18.5, cy: 6.5, r: 2.5 },
      { kind: "path", d: "M8 15L16 8.5", dashed: true },
    ],
  },
  "ridge-gravity": {
    elements: [
      { kind: "line", x1: 12, y1: 3, x2: 12, y2: 15 },
      { kind: "polyline", points: "7,10 12,15 17,10" },
      { kind: "line", x1: 4, y1: 20, x2: 20, y2: 20 },
    ],
  },
  "ridge-environment": {
    elements: [{ kind: "path", d: "M7 18h10a4 4 0 0 0 0-8 5.5 5.5 0 0 0-10.5 1.5A3.5 3.5 0 0 0 7 18z" }],
  },
} as const satisfies PictogramSet;
