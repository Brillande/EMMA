/**
 * Pictogramas del mapa corporal de dolor (`pain/`).
 *
 * Un dibujo por carácter del catálogo del backend (`app/pain/catalog.py`): la palabra
 * («Punzante», «Quemante»…) va siempre al lado, y `pain/characters.ts` dice cuál acompaña a cada
 * clave. Ninguno lleva color de alerta: la intensidad y el carácter del dolor no son una alerta
 * validada (`compliance/hmi-state-of-the-art.md` §5.2), así que estos dibujos van siempre en el
 * color del texto. Lo que comparte con otras áreas vive en `common`: el micrófono de la nota
 * dictada y revisada (también el del asistente), la estrella de cuatro puntas (punzante; en Tierra, una hipótesis
 * ejercitada a fondo), la pluma (nota escrita; en las alertas, reconocida), el signo igual y el
 * anillo con punto (`ring-dot`) del cambio y de la cifra elegida.
 *
 * El nombre es el dibujo, no la sensación: `flame`, no «quemante». Rejilla de 24×24, trazo de 2,
 * dentro de 3..21 para leerse a 12 px.
 */

import type { PictogramSet } from "../types";

export const pain = {
  // Sordo: óvalo tendido, sin ángulos.
  oval: {
    elements: [{ kind: "path", d: "M12 7c6 0 9 2.2 9 5s-3 5-9 5-9-2.2-9-5 3-5 9-5z" }],
  },
  // Quemante: llama.
  flame: {
    elements: [
      {
        kind: "path",
        d: "M12 21c-4 0-6.5-2.5-6.5-6 0-3 2-5 3.5-7.5.5 2 1.5 3 2.5 3.5 0-3 1-6 3-8 1 3 4 5.5 4.5 9.5.5 4-2.5 8.5-7 8.5z",
      },
    ],
  },
  // Opresivo: dos flechas que empujan hacia una barra central.
  "arrows-inward": {
    elements: [
      { kind: "line", x1: 12, y1: 6, x2: 12, y2: 18 },
      { kind: "line", x1: 3, y1: 12, x2: 9, y2: 12 },
      { kind: "polyline", points: "6,9 9,12 6,15" },
      { kind: "line", x1: 21, y1: 12, x2: 15, y2: 12 },
      { kind: "polyline", points: "18,9 15,12 18,15" },
    ],
  },
  // Pulsátil: punto con dos anillos concéntricos, como una onda que sale.
  "rings-concentric": {
    elements: [
      { kind: "circle", cx: 12, cy: 12, r: 2, fill: true },
      { kind: "circle", cx: 12, cy: 12, r: 5.5 },
      { kind: "circle", cx: 12, cy: 12, r: 9 },
    ],
  },
  // Calambre: espiral que se aprieta hacia el centro.
  spiral: {
    elements: [
      {
        kind: "path",
        d: "M12 12a1.5 1.5 0 0 1 1.5 1.5 3 3 0 0 1-3 3 4.5 4.5 0 0 1-4.5-4.5 6 6 0 0 1 6-6 7.5 7.5 0 0 1 7.5 7.5 9 9 0 0 1-2.6 6.3",
      },
    ],
  },
  // Hormigueo: puntos sueltos, repartidos.
  "dots-scattered": {
    elements: [
      { kind: "circle", cx: 6, cy: 7, r: 1.5, fill: true },
      { kind: "circle", cx: 13, cy: 5, r: 1.5, fill: true },
      { kind: "circle", cx: 18, cy: 9, r: 1.5, fill: true },
      { kind: "circle", cx: 8, cy: 13, r: 1.5, fill: true },
      { kind: "circle", cx: 15, cy: 14, r: 1.5, fill: true },
      { kind: "circle", cx: 11, cy: 19, r: 1.5, fill: true },
      { kind: "circle", cx: 19, cy: 18, r: 1.5, fill: true },
    ],
  },
} as const satisfies PictogramSet;
