import type { BackArt } from "../backSkin";
import { ARMS, ARMS_BONES, ARMS_MUSCLES } from "./arms";
import { BACK_HEAT } from "./heat";
import { LEGS, LEGS_BONES, LEGS_MUSCLES } from "./legs";
import { TORSO, TORSO_BONES, TORSO_MUSCLES } from "./torso";

/**
 * El dibujo de la espalda: calor de fondo, músculos con volumen, huesos y trazos claros, por región,
 * cada una en su fichero para que se puedan dibujar a la vez sin pisarse. Formato y orden de las
 * capas en `../backSkin.ts`; vista previa sin navegador con `npm run preview:back` desde `frontend/`.
 *
 * Los músculos se pintan en este orden y el de después tapa al de antes: el tronco, luego los
 * brazos (que caen por delante de los costados) y luego las piernas.
 */
export const BACK_ART: BackArt = {
  heat: BACK_HEAT,
  muscles: [...TORSO_MUSCLES, ...ARMS_MUSCLES, ...LEGS_MUSCLES],
  bones: [...TORSO_BONES, ...ARMS_BONES, ...LEGS_BONES],
  strokes: [...TORSO, ...ARMS, ...LEGS],
};
