/**
 * Pictogramas de las fuentes que firman lecturas en el ledger (`backend/app/analysis/data_quality.py`,
 * `_SOURCE_LABELS` y `_SOURCE_PREFIXES`): la columna «Fuente» de la calidad del dato y la fuente
 * de cada vínculo sensor-tripulante (`dashboard/readingSources.ts`).
 *
 * El nombre describe el dibujo; qué fuente es lo dice el nombre que firmó, que va al lado. Un
 * dibujo por fuente, por el canal del dato y no por lo que mide: reloj de pulsera (wearable BLE);
 * teléfono con un corazón y teléfono con un trazo de pulso (las dos aplicaciones de salud del
 * móvil, que no se distinguen por marca sino por dibujo); lápiz (alta manual); tableta con un
 * punto y monitor con un punto (el estímulo del test PVT, en un dispositivo externo o en esta
 * consola); monitor con cuatro casillas (las puntuaciones de la batería Cognition copiadas en
 * esta consola); cuaderno (registro diario); sonda con dos arcos (ecografía); hoja con un rayo (informe
 * de dolor); hoja con líneas (analítica de un informe escaneado). El simulador va con la onda
 * generada del entorno «simulado» (`provenance.ts`): es el mismo origen.
 *
 * Varias de estas fuentes son el canal de un panel con conjunto propio (diario, PVT, ecografía,
 * dolor, informes), y la misma cosa lleva un solo dibujo: el lápiz, el cuaderno, la sonda con
 * arcos y la hoja con líneas están en `common` porque esos paneles también los usan.
 */

import type { PictogramSet } from "../types";

/** Teléfono: rectángulo alto de esquinas redondeadas. */
const PHONE = {
  kind: "path",
  d: "M8 2.5h8a2 2 0 0 1 2 2v15a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2v-15a2 2 0 0 1 2-2z",
} as const;

/** Hoja con la esquina doblada: común a los dibujos de documento. */
const SHEET = [
  { kind: "path", d: "M6 2.5h8l5 5V21.5H6z" },
  { kind: "path", d: "M14 2.5v5h5" },
] as const;

export const sources = {
  wristwatch: {
    elements: [
      { kind: "circle", cx: 12, cy: 12, r: 5.5 },
      { kind: "rect", x: 9, y: 2, width: 6, height: 4 },
      { kind: "rect", x: 9, y: 18, width: 6, height: 4 },
      { kind: "line", x1: 12, y1: 12, x2: 12, y2: 9.5 },
    ],
  },
  "phone-heart": {
    elements: [PHONE, { kind: "path", d: "M12 15.5L8.8 12.2a2.3 2.3 0 0 1 3.2-3.2A2.3 2.3 0 0 1 15.2 12.2Z" }],
  },
  "phone-pulse": {
    elements: [PHONE, { kind: "polyline", points: "8,12 10,12 11,9.5 13,14.5 14,12 16,12" }],
  },
  // Con la barra de inicio abajo y el punto subido: el rectángulo de 16 × 18 con el punto en el
  // centro era, a unas décimas, el marco con el punto del aislamiento (`ridge-isolation`), y la
  // prueba de dibujos casi iguales lo cazó (§5.33.12).
  "tablet-dot": {
    elements: [
      { kind: "rect", x: 5, y: 3, width: 14, height: 18 },
      { kind: "circle", cx: 12, cy: 10.5, r: 2, fill: true },
      { kind: "line", x1: 10.5, y1: 18, x2: 13.5, y2: 18 },
    ],
  },
  "monitor-dot": {
    elements: [
      { kind: "rect", x: 3, y: 4, width: 18, height: 12 },
      { kind: "line", x1: 12, y1: 16, x2: 12, y2: 20 },
      { kind: "line", x1: 8, y1: 20, x2: 16, y2: 20 },
      { kind: "circle", cx: 12, cy: 10, r: 2, fill: true },
    ],
  },
  // El mismo monitor con cuatro casillas en vez del punto: las pruebas de la batería Cognition,
  // copiadas en esta consola (2026-11-03). Con el punto sería la PVT.
  "monitor-grid": {
    elements: [
      { kind: "rect", x: 3, y: 4, width: 18, height: 12 },
      { kind: "line", x1: 12, y1: 16, x2: 12, y2: 20 },
      { kind: "line", x1: 8, y1: 20, x2: 16, y2: 20 },
      { kind: "rect", x: 7, y: 6.5, width: 4, height: 3 },
      { kind: "rect", x: 13, y: 6.5, width: 4, height: 3 },
      { kind: "rect", x: 7, y: 10.5, width: 4, height: 3 },
      { kind: "rect", x: 13, y: 10.5, width: 4, height: 3 },
    ],
  },
  "sheet-bolt": {
    elements: [...SHEET, { kind: "polygon", points: "13,9 9,14.5 12,14.5 11,19.5 16,13 13,13" }],
  },
} as const satisfies PictogramSet;
