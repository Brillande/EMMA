/**
 * Pictogramas de la ecografía: protocolos, signos anotados y borrador (`imaging/`).
 *
 * Los protocolos que miden un órgano del catálogo (nervio óptico, yugular, vejiga, pulmón,
 * hígado) comparten dibujo con la familia de su indicador (`icons/sets/indicators.ts`): es el
 * mismo significado y por eso no se dibuja dos veces. Aquí van los que no tienen familia y los
 * estados propios de la ecografía:
 *
 *   - `probe-fan`: la sonda con su haz en abanico (el título de los paneles de ecografía).
 *   - `circle-quartered`: un círculo dividido en cuatro cuadrantes, para el FAST de cuatro ventanas.
 *   - `fan-dot` / `fan-dash`: la ventana ecográfica —el sector en abanico de la imagen, el mismo
 *     haz que sale de `probe-fan`— con algo dentro y vacía: un signo presente y un signo ausente.
 *     Hasta la limpieza del rediseño (2026-10-21) la ventana era un círculo (`circle-dot`), que a
 *     12 px no se distinguía del anillo con punto de «elegido» (`ring-dot`, `common`); el abanico
 *     es la ventana de verdad y se lee como tal. «No valorable» usa `slash-circle` (no
 *     disponible), de `shapes`.
 *   - La lista de calidad de la adquisición (`list-check`) vive en `common` desde la segunda pasada
 *     (2026-10-21): es el título de «calidad» en toda la interfaz (`lib/uiMarks.ts`).
 *   - `triangle-right-filled`: el paso que toca ahora en la medida guiada (era «▸»).
 *   - `page-dashed`: una hoja con el borde a trazos: el borrador del modelo local, que se ve como
 *     borrador y nunca como un hallazgo (segregación Clase C, invariante 6).
 *   - `guillemets`: «», la frase literal del informe citado, localizada en su registro.
 *   - `polygon-dots`: un contorno cerrado de cinco tramos con un punto en cada vertice: el mando
 *     «Cerrar contorno» de la medida guiada (segunda pasada, 2026-10-21). Es lo que dibuja el
 *     calibre sobre la imagen —puntos unidos por una linea— con el ultimo tramo ya cerrado.
 *
 * Como en el resto del registro: rejilla de 24×24, trazo de 2, de 3 a 21, sin color propio. El
 * nombre es el dibujo; el significado lo pone la palabra de al lado.
 */

import type { PictogramSet } from "../types";
import { RING } from "./shapes";

/**
 * La ventana ecográfica: un sector con el vértice arriba (12, 3,5) que se abre 70° hacia abajo y
 * cierra con el arco de r = 14,7 centrado en el vértice (el fondo del arco queda en y = 18,2).
 */
const FAN = { kind: "path", d: "M12 3.5L3.5 15.5A14.7 14.7 0 0 0 20.5 15.5z" } as const;

export const imaging = {
  "probe-fan": {
    elements: [
      // Mango de la sonda, arriba; el haz se abre hacia abajo como un sector.
      { kind: "path", d: "M9 3h6v5H9z" },
      { kind: "path", d: "M9.5 8L4 19a12 12 0 0 0 16 0L14.5 8" },
      { kind: "path", d: "M8 15a6 6 0 0 0 8 0" },
    ],
  },
  "circle-quartered": {
    elements: [
      RING,
      { kind: "line", x1: 12, y1: 4, x2: 12, y2: 20 },
      { kind: "line", x1: 4, y1: 12, x2: 20, y2: 12 },
    ],
  },
  // Dentro del abanico, a la altura en que ya es ancho (y = 13,5): un punto o una raya.
  "fan-dot": { elements: [FAN, { kind: "circle", cx: 12, cy: 13.5, r: 2.5, fill: true }] },
  "fan-dash": { elements: [FAN, { kind: "line", x1: 8.5, y1: 13.5, x2: 15.5, y2: 13.5 }] },
  "triangle-right-filled": { elements: [{ kind: "polygon", points: "8,6 18,12 8,18", fill: true }] },
  // Perimetro 58,66 = 7 pares de tramo y hueco de 4,19: el borde a trazos cierra sin munon.
  "page-dashed": {
    elements: [
      { kind: "path", d: "M6.34 3h11.33v18H6.34z", dashed: true },
      { kind: "line", x1: 9.5, y1: 10, x2: 14.5, y2: 10 },
      { kind: "line", x1: 9.5, y1: 14, x2: 14.5, y2: 14 },
    ],
  },
  // Irregular a proposito: con cinco lados iguales y los puntos en las puntas se leia como una
  // estrella a 14 px (hoja de contactos, 2026-10-21). Con los puntos, de 3 a 21.
  "polygon-dots": {
    elements: [
      { kind: "polygon", points: "4.5,13 9,5 18,5.5 19.5,15 10,19" },
      { kind: "circle", cx: 4.5, cy: 13, r: 1.5, fill: true },
      { kind: "circle", cx: 9, cy: 5, r: 1.5, fill: true },
      { kind: "circle", cx: 18, cy: 5.5, r: 1.5, fill: true },
      { kind: "circle", cx: 19.5, cy: 15, r: 1.5, fill: true },
      { kind: "circle", cx: 10, cy: 19, r: 1.5, fill: true },
    ],
  },
  guillemets: {
    elements: [
      { kind: "polyline", points: "6,8 3,12 6,16" },
      { kind: "polyline", points: "10,8 7,12 10,16" },
      { kind: "polyline", points: "14,8 17,12 14,16" },
      { kind: "polyline", points: "18,8 21,12 18,16" },
    ],
  },
} as const satisfies PictogramSet;
