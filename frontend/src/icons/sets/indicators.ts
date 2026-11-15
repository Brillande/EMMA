/**
 * Pictogramas de las familias de indicadores del catálogo.
 *
 * Una familia por dibujo; `lib/indicatorFamily.ts` dice a qué familia va cada clave del catálogo
 * (y el backend comprueba que no falta ninguna). El nombre describe el dibujo; lo que mide lo dice
 * `display_es`, que va al lado. La lateralidad (derecha, izquierda) va en ese texto, no en el
 * pictograma. Ninguno repite el dibujo de un dominio (`domains.ts`).
 */

import { HEART_OUTLINE } from "./domains";
import type { PictogramSet } from "../types";

export const indicators = {
  // Ritmo y variabilidad: corazón con el trazo del pulso.
  "heart-pulse": {
    elements: [HEART_OUTLINE, { kind: "polyline", points: "8,13 10.5,13 11.5,10.5 12.5,15 13.5,13 16,13" }],
  },
  // Presión: manómetro.
  gauge: {
    elements: [
      { kind: "path", d: "M4 16a8 8 0 0 1 16 0" },
      { kind: "line", x1: 12, y1: 16, x2: 16, y2: 9 },
      { kind: "circle", cx: 12, cy: 16, r: 1.2, fill: true },
      { kind: "line", x1: 3, y1: 20, x2: 21, y2: 20 },
    ],
  },
  // Respiración y oxígeno: dos lóbulos y la tráquea.
  lungs: {
    elements: [
      { kind: "path", d: "M11 8c-3 0-6 4-6 9a2 2 0 0 0 2 2c3-1 4-3 4-6z" },
      { kind: "path", d: "M13 8c3 0 6 4 6 9a2 2 0 0 1-2 2c-3-1-4-3-4-6z" },
      { kind: "line", x1: 12, y1: 3, x2: 12, y2: 9 },
    ],
  },
  thermometer: {
    elements: [
      { kind: "path", d: "M9.5 14.6V5.5a2.5 2.5 0 0 1 5 0v9.1a4 4 0 1 1-5 0z" },
      { kind: "circle", cx: 12, cy: 18, r: 1.5, fill: true },
    ],
  },
  // Masa: balanza de dos platos.
  balance: {
    elements: [
      { kind: "line", x1: 12, y1: 4, x2: 12, y2: 20 },
      { kind: "line", x1: 8, y1: 20, x2: 16, y2: 20 },
      { kind: "line", x1: 5, y1: 8, x2: 19, y2: 8 },
      { kind: "path", d: "M2 13l3-5 3 5a3 3 0 0 1-6 0z" },
      { kind: "path", d: "M16 13l3-5 3 5a3 3 0 0 1-6 0z" },
    ],
  },
  // Sueño: luna con una zeta.
  "moon-z": {
    elements: [
      { kind: "path", d: "M19.5 14.5A8 8 0 1 1 9.5 4.5a6.5 6.5 0 0 0 10 10z" },
      { kind: "polyline", points: "15,3 19,3 15,7 19,7" },
    ],
  },
  // Tiempo de reacción (PVT): cronómetro.
  stopwatch: {
    elements: [
      { kind: "circle", cx: 12, cy: 13.5, r: 7.5 },
      { kind: "line", x1: 10, y1: 2.5, x2: 14, y2: 2.5 },
      { kind: "line", x1: 12, y1: 2.5, x2: 12, y2: 6 },
      { kind: "line", x1: 12, y1: 13.5, x2: 15.5, y2: 10 },
    ],
  },
  // Ánimo y carga de trabajo: cara neutra.
  "face-neutral": {
    elements: [
      { kind: "circle", cx: 12, cy: 12, r: 8 },
      { kind: "circle", cx: 9, cy: 10, r: 1, fill: true },
      { kind: "circle", cx: 15, cy: 10, r: 1, fill: true },
      { kind: "line", x1: 9, y1: 15, x2: 15, y2: 15 },
    ],
  },
  // Síntomas, saliva y virus latente: tubo de muestra.
  vial: {
    elements: [
      { kind: "path", d: "M10 3v14a2 2 0 0 0 4 0V3" },
      { kind: "line", x1: 8, y1: 3, x2: 16, y2: 3 },
      { kind: "line", x1: 10, y1: 12, x2: 14, y2: 12 },
    ],
  },
  // Dosis: trébol de tres aspas con el punto central.
  trefoil: {
    elements: [
      { kind: "path", d: "M10.25 8.97L8 5.07A8 8 0 0 1 16 5.07L13.75 8.97A3.5 3.5 0 0 0 10.25 8.97Z", fill: true },
      { kind: "path", d: "M15.5 12L20 12A8 8 0 0 1 16 18.93L13.75 15.03A3.5 3.5 0 0 0 15.5 12Z", fill: true },
      { kind: "path", d: "M10.25 15.03L8 18.93A8 8 0 0 1 4 12L8.5 12A3.5 3.5 0 0 0 10.25 15.03Z", fill: true },
      { kind: "circle", cx: 12, cy: 12, r: 1, fill: true },
    ],
  },
  // Ejercicio, carga y forma física: mancuerna.
  dumbbell: {
    elements: [
      { kind: "rect", x: 3, y: 7, width: 4, height: 10, fill: true },
      { kind: "rect", x: 17, y: 7, width: 4, height: 10, fill: true },
      { kind: "line", x1: 7, y1: 12, x2: 17, y2: 12 },
    ],
  },
  // Recambio óseo y minerales: cristal.
  crystal: {
    elements: [
      { kind: "polygon", points: "12,3 19.8,7.5 19.8,16.5 12,21 4.2,16.5 4.2,7.5" },
      { kind: "line", x1: 12, y1: 3, x2: 12, y2: 21 },
    ],
  },
  // Nervio óptico y visión: ojo pequeño, a la izquierda, con el nervio saliendo del rabillo. El
  // dominio es el ojo grande y centrado, con la pupila llena.
  "eye-nerve": {
    elements: [
      { kind: "path", d: "M2 10s3.5-5 7-5 7 5 7 5-3.5 5-7 5S2 10 2 10z" },
      { kind: "circle", cx: 9, cy: 10, r: 2 },
      { kind: "path", d: "M16 10c2.5 0 4 2.5 5.5 8" },
    ],
  },
  // Yugular: vaso con células que pasan.
  "vessel-flow": {
    elements: [
      { kind: "line", x1: 3, y1: 8, x2: 21, y2: 8 },
      { kind: "line", x1: 3, y1: 16, x2: 21, y2: 16 },
      { kind: "circle", cx: 8, cy: 12, r: 1.5, fill: true },
      { kind: "circle", cx: 15, cy: 12, r: 1.5, fill: true },
    ],
  },
  // Vejiga, orina e hidratación: vejiga con los dos uréteres.
  bladder: {
    elements: [
      { kind: "path", d: "M6 8c-2 2-2 9 2 11h8c4-2 4-9 2-11" },
      { kind: "line", x1: 8, y1: 8, x2: 8, y2: 4 },
      { kind: "line", x1: 16, y1: 8, x2: 16, y2: 4 },
      { kind: "line", x1: 12, y1: 19, x2: 12, y2: 21 },
    ],
  },
  // Hemograma e inflamación: células.
  cells: {
    elements: [
      { kind: "circle", cx: 8, cy: 9, r: 3.5 },
      { kind: "circle", cx: 16, cy: 9, r: 3.5 },
      { kind: "circle", cx: 12, cy: 16, r: 3.5 },
    ],
  },
  // Función renal y electrolitos: dos riñones.
  kidneys: {
    elements: [
      { kind: "path", d: "M9 4c-4 0-6 3.5-6 8s2 8 6 8c2 0 2-2 2-3V7c0-1 0-3-2-3z" },
      { kind: "path", d: "M15 4c4 0 6 3.5 6 8s-2 8-6 8c-2 0-2-2-2-3V7c0-1 0-3 2-3z" },
    ],
  },
  // Hígado y metabolismo: hígado.
  liver: {
    elements: [{ kind: "path", d: "M3 9c0-3 3-5 7-5h6c3 0 5 2 5 4 0 4-3 6-6 7l-6 2c-4 1-6-1-6-5z" }],
  },
  // Hormonas: molécula.
  molecule: {
    elements: [
      { kind: "circle", cx: 6, cy: 16, r: 2.5 },
      { kind: "circle", cx: 12, cy: 7, r: 2.5 },
      { kind: "circle", cx: 18, cy: 16, r: 2.5 },
      { kind: "line", x1: 7.5, y1: 13.8, x2: 10.5, y2: 9.2 },
      { kind: "line", x1: 13.5, y1: 9.2, x2: 16.5, y2: 13.8 },
      { kind: "line", x1: 8.5, y1: 16, x2: 15.5, y2: 16 },
    ],
  },
  // Marcadores tumorales: banderín.
  flag: {
    elements: [
      { kind: "line", x1: 6, y1: 21, x2: 6, y2: 3 },
      { kind: "path", d: "M6 4h12l-3 4 3 4H6z" },
    ],
  },
  // Comida y apetito: tenedor y cuchillo.
  "fork-knife": {
    elements: [
      { kind: "path", d: "M5 3v5a2 2 0 0 0 4 0V3" },
      { kind: "line", x1: 7, y1: 10, x2: 7, y2: 21 },
      { kind: "path", d: "M17 3c-2.5 3-2.5 8 0 10v8" },
    ],
  },
  // Dolor: rayo.
  bolt: { elements: [{ kind: "polygon", points: "13,2 5,13 11,13 10,22 19,10 13,10" }] },
  // Registros del ciclo menstrual y la anticoncepción (descriptivos, 2026-11-14): una gota
  // pequeña, llena, dentro de una flecha que vuelve sobre sí misma. No es la gota de contorno del
  // dominio genitourinario: la flecha dice «ciclo».
  "drop-cycle": {
    elements: [
      { kind: "path", d: "M19.5 12a7.5 7.5 0 1 1-2.2-5.3" },
      { kind: "polyline", points: "17.6,3.2 17.6,6.9 13.9,6.9" },
      { kind: "path", d: "M12 8.5s2.8 3.2 2.8 5.2a2.8 2.8 0 0 1-5.6 0c0-2 2.8-5.2 2.8-5.2z", fill: true },
    ],
  },
} as const satisfies PictogramSet;
