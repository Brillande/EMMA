/**
 * Pictogramas de la radiación: las tres escalas y el refugio (`radiation/`).
 *
 * Por qué tres dibujos distintos: §5.11 del estado del arte separa la radiación en aguda, de
 * misión y de carrera porque se deciden cosas distintas con cada una (refugiarse en una hora,
 * seguir la dosis inferida, no pasar del límite de carrera). Un mismo trébol en las tres filas
 * diría «radiación» tres veces y no distinguiría ninguna. El nombre describe el dibujo; la
 * palabra de al lado («Aguda», «Esta misión», «Carrera», «refugio») pone el significado:
 *
 * - `burst` (en `common` desde la decimoséptima ronda, 2026-10-26: el hábitat lo usa también para
 *   el evento solar como causa común de la tripulación): rayos que salen de un punto, sin disco.
 *   Lo repentino: la escala aguda, la que dispara un evento solar. No es el sol de
 *   `ridge-radiation`, que lleva disco y rayos cortos.
 * - `trefoil` (de `indicators`): la dosis. La escala de misión.
 * - `bar-capped` (en `common` desde la segunda pasada, 2026-10-21: es también el dibujo de
 *   «límites» y «rango» en toda la interfaz, `lib/uiMarks.ts`): una barra llena a medias con un
 *   tope al final. Lo acumulado frente a un límite: la escala de carrera, el mismo dibujo que hace
 *   la barra del dosímetro.
 * - `house-door`: una casa con su puerta. El refugio contra la tormenta solar.
 *
 * El tipo (SEP, FLR, CME) y la severidad del evento no tienen dibujo: el panel no los enseña y
 * un pictograma sin palabra no existe en EMMA.
 */

import type { PictogramSet } from "../types";

export const radiation = {
  "house-door": {
    elements: [
      { kind: "path", d: "M4 11l8-7 8 7v9H4z" },
      { kind: "rect", x: 10, y: 14, width: 4, height: 6 },
    ],
  },
} as const satisfies PictogramSet;
