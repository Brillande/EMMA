/**
 * Pictogramas del diario de la tripulación (`diary/`).
 *
 * Las escalas propias de la misión (ánimo, síntomas, apetito) publican dos anclas, una por
 * extremo del rango, que el backend marca como decisión de diseño sin validar. Cada ancla va con
 * un dibujo neutro: un cursor sobre una pista, en un extremo o en el otro. Es la posición en un
 * rango y nada más: ni una cara ni un signo que insinúe un instrumento que no hay. Qué extremo
 * es «bajo» o «alto» y qué significa lo dice el rótulo del backend que va al lado.
 *
 * Rejilla de 24×24, trazo de 2. La pista ocupa de 4 a 20 y el cursor es un disco de r = 3 en
 * uno de sus extremos, para que a 12 px se distinga de qué lado está.
 */

import type { PictogramSet } from "../types";

/** La pista del cursor, común a los dos extremos. */
const TRACK = { kind: "line", x1: 4, y1: 12, x2: 20, y2: 12 } as const;

export const diary = {
  "slider-left": { elements: [TRACK, { kind: "circle", cx: 6, cy: 12, r: 3, fill: true }] },
  "slider-right": { elements: [TRACK, { kind: "circle", cx: 18, cy: 12, r: 3, fill: true }] },
} as const satisfies PictogramSet;
