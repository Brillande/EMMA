/**
 * Hacia dónde está «arriba» de verdad, grado a grado, para la flecha del borde de arriba
 * (`ScreenTop` en `components/DisplayControls.tsx`, §5.40).
 *
 * Por qué existe: la vista solo gira de 90 en 90 (`orientation.ts`, con histéresis y sin
 * animación, WCAG 2.3.1), así que con la tableta girada 50° el borde de arriba de la vista queda a
 * 50° del arriba real de quien mira, y en microgravedad no hay gravedad que se lo recuerde. La
 * flecha no salta de cuadrante: apunta al arriba real con lo que ya miden la cara
 * (`faceOrientation.ts`) o el giroscopio desde su «esto es arriba». Lo pidió el usuario
 * (2026-11-04): que «arriba» marque siempre lo que es arriba, esté donde esté la tableta.
 *
 * Es un almacén mínimo fuera de React: la cara mira cuatro veces por segundo y el giroscopio más,
 * y meter cada lectura en el contexto de los modos repintaría la consola entera. Solo se suscribe
 * la flecha, y solo cambia con un grado entero de diferencia.
 */

import { useSyncExternalStore } from "react";

import { normalizeDegrees, signedDelta } from "./orientation";

/** De dónde sale el ángulo: la cara, si la ve, manda sobre el giroscopio (como con la vista). */
export type UpSource = "face" | "sensor";

const angles: Record<UpSource, number | null> = { face: null, sensor: null };
let current: number | null = null;
const listeners = new Set<() => void>();

/** El ángulo al que habría que girar la vista para que quede derecha (como `viewAngle`). */
export function setUpAngle(source: UpSource, angle: number | null): void {
  angles[source] = angle === null || !Number.isFinite(angle) ? null : normalizeDegrees(Math.round(angle));
  const next = angles.face ?? angles.sensor;
  if (next === current) return;
  current = next;
  for (const listener of listeners) listener();
}

/** El ángulo de ahora, o `null` si nada lo mide. */
export function upAngle(): number | null {
  return current;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useUpAngle(): number | null {
  return useSyncExternalStore(subscribe, upAngle, () => null);
}

/**
 * Cuánto hay que girar, en el sentido del reloj, una flecha dibujada hacia el borde de arriba de la
 * vista para que apunte al arriba real: lo que le falta al giro de la vista (`rotation`) para
 * llegar a `angle`. Sin medida, la flecha va al borde de arriba de la vista (0).
 */
export function upArrowDegrees(angle: number | null, rotation: number): number {
  if (angle === null) return 0;
  return signedDelta(rotation, angle) + 0;
}
