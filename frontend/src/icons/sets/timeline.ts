/**
 * Pictogramas de las alertas y de la crónica (`dashboard/AlertRow.tsx`, `AlertDetailView.tsx`,
 * `TimelinePieces.tsx`; tablas en `lib/alerts.ts` y `dashboard/timelineMarks.ts`).
 *
 * Por qué están aquí y no en `shapes`: son dibujos de cosas (una campana, una llave, un casco),
 * no formas geométricas con un nivel detrás. El nombre dice qué se ve; qué significa lo dice la
 * palabra de al lado y la tabla de `compliance/hmi-state-of-the-art.md` §5.32.1. Rejilla de
 * 24×24, trazo de 2, todo entre 2,5 y 21,5 para que a 12 px quede un trazo de 1 px con hueco.
 *
 * Estados de una alerta: punto dentro de un anillo (detectada), llave inglesa (en arreglo);
 * campana tachada (suprimida) y campana dentro de un marco (inhibida: el dominio entero, con
 * puerta cerrada); pluma (reconocida: alguien firmó).
 * Tipos de hecho de la crónica (`app/timeline.py`): campana (alerta), tirita (contramedida),
 * casco (misión), casa (hábitat), punto que emite dos arcos (sensor), cubo (recurso), cuadro con
 * horizonte (imagen), engranaje (sistema: el mismo dibujo que el asiento de sistema del ledger;
 * el símbolo de encendido que la crónica dibujó para lo mismo se retiró en la segunda pasada,
 * 2026-10-21), escalera (fase), sol saliendo sobre una línea (posvuelo). Etapas (§10): tablilla
 * con pinza (prevuelo), calendario con un día marcado (día de misión), maletín con cruz
 * (intervención), lupa (seguimiento), paracaídas (posvuelo), reloj de pared (sin instante de
 * datos: la hora del ordenador). Y lo demás: chip (se recalcula solo), persona (lo revisa una
 * persona), reloj de arena (atrasada).
 *
 * Casi todo eso lo comparte con otras áreas y vive en `common` (campanas, pluma, casco, casa,
 * cubo, cuadro, escalera, tablilla, lupa, reloj, chip, persona, reloj de arena, engranaje; y desde
 * la segunda pasada la llave, la campana en su marco, la tirita, el sol saliendo y el calendario
 * con el día marcado, que nombran mandos y títulos de toda la interfaz, `lib/uiMarks.ts`); el
 * paracaídas es de `mission`, misma casa (`dashboard`). Aquí quedan la diana de «detectada», el
 * punto con arcos del sensor, el maletín de la intervención y, desde la segunda pasada (§5.33.1),
 * el árbol de puntos de «qué depende de estos datos» en el detalle de alerta.
 */

import type { PictogramSet } from "../types";

export const timeline = {
  // --- Estados de una alerta -------------------------------------------------------------
  // Punto en anillo con cuatro marcas, como una diana: «detectada». Las marcas lo distinguen de
  // `ring-dot` (elegido / actual, en `common`), que es anillo y punto sin más.
  "dot-ringed": {
    elements: [
      { kind: "circle", cx: 12, cy: 12, r: 7 },
      { kind: "circle", cx: 12, cy: 12, r: 2.5, fill: true },
      { kind: "line", x1: 12, y1: 2, x2: 12, y2: 5 },
      { kind: "line", x1: 12, y1: 19, x2: 12, y2: 22 },
      { kind: "line", x1: 2, y1: 12, x2: 5, y2: 12 },
      { kind: "line", x1: 19, y1: 12, x2: 22, y2: 12 },
    ],
  },

  // --- Tipos de hecho de la crónica ------------------------------------------------------
  // Un punto abajo a la izquierda y dos arcos que salen de él.
  "arcs-dot": {
    elements: [
      { kind: "circle", cx: 6, cy: 18, r: 1.8, fill: true },
      { kind: "path", d: "M6 12a6 6 0 0 1 6 6" },
      { kind: "path", d: "M6 7a11 11 0 0 1 11 11" },
    ],
  },

  // --- Detalle de alerta -----------------------------------------------------------------
  // Un punto lleno arriba y dos anillos debajo, unidos por dos trazos: un dato y lo que cuelga
  // de él (Polaris `cascada_mapa`), el rótulo «Qué depende de estos datos» (segunda pasada,
  // §5.33.1). Ningún concepto del vocabulario común dice «depende de»; las cadenas de `bind`
  // son vincular un aparato, otra cosa.
  "dot-tree": {
    elements: [
      { kind: "circle", cx: 12, cy: 5, r: 2.2, fill: true },
      { kind: "circle", cx: 5.5, cy: 18.5, r: 2.2 },
      { kind: "circle", cx: 18.5, cy: 18.5, r: 2.2 },
      { kind: "line", x1: 11.05, y1: 6.98, x2: 6.45, y2: 16.52 },
      { kind: "line", x1: 12.95, y1: 6.98, x2: 17.55, y2: 16.52 },
    ],
  },

  // --- Etapas ----------------------------------------------------------------------------
  "kit-case": {
    elements: [
      { kind: "rect", x: 3, y: 7, width: 18, height: 13 },
      { kind: "path", d: "M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" },
      { kind: "line", x1: 12, y1: 10.5, x2: 12, y2: 16.5 },
      { kind: "line", x1: 9, y1: 13.5, x2: 15, y2: 13.5 },
    ],
  },
} as const satisfies PictogramSet;
