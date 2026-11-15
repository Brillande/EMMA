/**
 * Pictogramas de la carcasa de la aplicación: franja común, navegación, modo seguro y «acerca
 * de» (`App.tsx`, `components/StatusStrip.tsx`, `components/SafeMode.tsx`, `About.tsx`).
 *
 * Por qué están aquí y no en `shapes`: son dibujos de cosas (un candado, una antena, una puerta),
 * no formas de nivel ni de estado. Lo que la carcasa dice con formas de nivel o de dato ausente
 * (△ del modo seguro, ◌ del dato caducado, ✓ ✕ del registro firmado) sigue saliendo de `shapes`;
 * lo que dice con un entorno (Tierra, vuelo real, onda simulada) sale de `provenance`; lo que
 * dice con un dominio o una familia de indicador (los escenarios del simulador) sale de
 * `domains` e `indicators`; y lo que comparte con la crónica y la misión (casco, cabeza y
 * hombros, reloj, campana y campana tachada, cubo) sale de `common`. Aquí solo va lo que ningún
 * otro conjunto tiene.
 *
 * El nombre es el dibujo; el significado lo pone la palabra de al lado. Rejilla de 24×24, trazo
 * de 2, todo entre 3 y 21 salvo lo que asoma a propósito: la hoja de la puerta (hasta 22,5) y la
 * onda de `wave-dot`, que empieza en x = 2 como la de `wave-zigzag` de la que es media.
 *
 * Dibujos: onda generada seguida de un punto medido (modo mezcla: simulado y real); mástil con
 * ondas (la red); puerta con la hoja abierta (red abierta, levantar el modo seguro); vaso con la
 * línea del agua baja (deshidratación); mando giratorio con tres marcas (el rótulo «Modo» de la
 * franja, segunda pasada). El candado del registro firmado y el círculo con una i de
 * «acerca de» pasaron a `common` en la segunda pasada (2026-10-21): son títulos de toda la
 * interfaz (`lib/uiMarks.ts`).
 */

import type { PictogramSet } from "../types";

export const shell = {
  // Media onda de `wave-zigzag` y el disco lleno de `dot-filled`: lo simulado y lo medido juntos.
  "wave-dot": {
    elements: [
      { kind: "polyline", points: "2,12 5,6 8,18 11,12" },
      { kind: "circle", cx: 17.5, cy: 12, r: 3.5, fill: true },
    ],
  },
  // Mástil sobre una base, el emisor y dos ondas concéntricas hacia arriba (r = 4 y r = 7).
  antenna: {
    elements: [
      { kind: "line", x1: 12, y1: 10.5, x2: 12, y2: 21 },
      { kind: "line", x1: 7, y1: 21, x2: 17, y2: 21 },
      { kind: "circle", cx: 12, cy: 9, r: 1.5, fill: true },
      { kind: "path", d: "M9.17 6.17a4 4 0 0 1 5.66 0" },
      { kind: "path", d: "M7.05 4.05a7 7 0 0 1 9.9 0" },
    ],
  },
  // Marco sin el lado de abajo y la hoja girada hacia fuera, con su pomo; `door-closed` es el
  // rectángulo cerrado con el pomo dentro.
  "door-open": {
    elements: [
      { kind: "path", d: "M6 21V3h12v18" },
      { kind: "polygon", points: "10,4.5 17,6.5 17,22.5 10,20.5" },
      { kind: "circle", cx: 15, cy: 14, r: 0.9, fill: true },
    ],
  },
  // Vaso visto de frente, abierto por arriba, con la línea del agua cerca del fondo.
  "glass-waterline": {
    elements: [
      { kind: "polyline", points: "5,3 7,21 17,21 19,3" },
      { kind: "line", x1: 7, y1: 17, x2: 17, y2: 17 },
    ],
  },
  // Mando giratorio de un selector: el pomo (r = 6), su aguja apuntando a la posición de la
  // izquierda y tres marcas fuera del pomo, a 150°, 90° y 30° (de r = 8 a r = 10).
  "knob-ticks": {
    elements: [
      { kind: "circle", cx: 12, cy: 14, r: 6 },
      { kind: "line", x1: 12, y1: 14, x2: 8.5, y2: 12 },
      { kind: "line", x1: 3.4, y1: 9, x2: 5.1, y2: 10 },
      { kind: "line", x1: 12, y1: 4, x2: 12, y2: 6 },
      { kind: "line", x1: 18.9, y1: 10, x2: 20.6, y2: 9 },
    ],
  },
} as const satisfies PictogramSet;
