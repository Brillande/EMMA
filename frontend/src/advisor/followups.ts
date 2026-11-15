/**
 * Lo que el panel de seguimiento decide antes de pintar: la palabra de cada estado y el dibujo que
 * acompana a cada estado y a cada resultado de la evaluacion (§5.32.5).
 *
 * Por que existe aparte de `FollowupsPanel.tsx`: son reglas con prueba (`followups.test.ts`), no
 * detalles del JSX, como `recommendation.ts` y `resources.ts` para la tarjeta. El estado y la
 * evaluacion los calcula y redacta el backend; aqui solo se elige la senal, y un valor que esta
 * version no conoce sale con el dibujo de «desconocido» y su clave, nunca disfrazado de otro.
 */

import type { PictogramName } from "../icons/registry";
import type { Followup } from "../lib/api";
import { type StateMark, MISSING_MARK, UNKNOWN_MARK, UNKNOWN_PICTOGRAM, mark } from "../lib/marks";

export const STATE_LABEL: Record<Followup["state"], string> = {
  in_window: "en ventana",
  due: "listo para revisar",
  closed: "cerrado",
};

/** Estado del seguimiento: en curso (ventana abierta), listo para revisar y cerrado (hecho). */
export const STATE_PICTOGRAMS: Record<Followup["state"], PictogramName> = {
  in_window: "refresh",
  due: "play",
  closed: "check",
};

/** La palabra de un estado, o su clave si la interfaz no lo conoce: no se inventa otra. */
export function stateLabel(state: string): string {
  return (STATE_LABEL as Record<string, string>)[state] ?? state;
}

export function statePictogram(state: string): PictogramName {
  return (STATE_PICTOGRAMS as Record<string, PictogramName>)[state] ?? UNKNOWN_PICTOGRAM;
}

type Outcome = NonNullable<Followup["evaluation"]>["outcome"];

/**
 * Resultado de la evaluacion, con la flecha de la trayectoria de la consola: la flecha sigue al
 * nivel de riesgo, asi que «mejoro» (el nivel bajo) es la flecha que baja y «empeoro» la que
 * sube; «igual» es el guion. Sin color: historia, no alerta. «Sin repetir» es un dato ausente:
 * anillo punteado en cian, que es lo que ese color significa en la tabla F.5-1.
 */
export const OUTCOME_MARKS: Record<Outcome, StateMark> = {
  improved: mark("arrow-down-right", null),
  unchanged: mark("dash", null),
  worsened: mark("arrow-up-right", null),
  no_repeat: MISSING_MARK,
};

export function outcomeMark(outcome: string): StateMark {
  return (OUTCOME_MARKS as Record<string, StateMark>)[outcome] ?? UNKNOWN_MARK;
}
