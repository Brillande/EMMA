/**
 * Girar la vista siguiendo la cara de quien mira, con la cámara frontal. **Demostración, sin
 * validar.**
 *
 * Por qué existe: el giroscopio (`orientation.ts`) mide el giro de la tableta en el espacio
 * inercial, no respecto a quien la mira. Si la persona y la tableta flotan girando juntas, o la
 * estación da su vuelta por órbita con la tableta fija a la pared, el giroscopio gira la vista sin
 * motivo. Lo que dice dónde es «arriba» para quien mira es su cara: la recta entre sus dos ojos,
 * vista por la cámara que está en el plano de la pantalla. Era la idea del equipo en el audio del
 * seguimiento ocular, anotada en §5.40 de `compliance/hmi-state-of-the-art.md` como «necesita
 * hardware»; la cámara frontal de una tableta ya es ese hardware.
 *
 * Solo se usa el ángulo de esa recta. Nada de esto mide fatiga, mirada ni estado de nadie, ni
 * infiere nada de la cara: no es un dato clínico (invariante 7), no pasa por el registro firmado y
 * no sale del equipo. La parte que toca la cámara está en `faceCamera.ts`; aquí va lo puro, con
 * prueba (`faceOrientation.test.ts`).
 *
 * El ángulo se mide en la imagen tal como la da la cámara, que el navegador entrega alineada con
 * la pantalla como el sistema la tiene puesta, y sin espejo: lo que la persona tiene a su derecha
 * sale a la izquierda de la imagen. Por eso el giro de la vista es absoluto, sin la referencia de
 * «esto es arriba» que necesita el giroscopio: la cara ya es la referencia. La vista va al
 * cuadrante con la misma histéresis que con el sensor (`followQuadrant`), sin animación (WCAG
 * 2.3.1).
 */

import type { Rotation } from "../components/displayModes";
import { followQuadrant, normalizeDegrees, signedDelta } from "./orientation";

/** Un punto de la malla de la cara, en fracciones de la imagen (0 a 1), como lo da MediaPipe. */
export interface FacePoint {
  readonly x: number;
  readonly y: number;
}

/**
 * Los rabillos de cada ojo en la malla de 478 puntos de MediaPipe Face Landmarker: «derecho» e
 * «izquierdo» son los de la persona, no los de la imagen.
 */
export const RIGHT_EYE = [33, 133] as const;
export const LEFT_EYE = [263, 362] as const;

/**
 * La barbilla en la misma malla. La recta de los ojos da el giro con precisión pero no dice hacia
 * dónde está la cabeza (una cara cabeza abajo da la misma recta, al revés); de los ojos a la
 * barbilla es «abajo» para la persona, y resuelve eso aunque se hubieran confundido los dos ojos.
 */
export const CHIN = 152;

/**
 * Una recta entre los ojos más corta que esto (píxeles de la imagen) no da un ángulo fiable: cara
 * muy lejos, de perfil o mal vista. Parámetro de diseño de EMMA, sin fuente: a 320 px de ancho, una
 * cara a un brazo de distancia deja varias veces esto entre los ojos.
 */
export const MIN_EYE_SPAN_PX = 12;

/** Cada cuánto se busca la cara: cuatro veces por segundo, para no gastar. */
export const DETECTION_INTERVAL_MS = 250;

/** Lo que vio la cámara en una búsqueda. */
export type FaceReading =
  | { readonly kind: "none" }
  | { readonly kind: "several"; readonly count: number }
  | { readonly kind: "one"; readonly angle: number };

/** Cómo va el seguimiento de la cara, para decirlo en la interfaz. */
export type FaceStatus = "off" | "starting" | "noFace" | "face" | "several" | "unavailable";

/** La cámara está encendida (y lo dice el aviso permanente) en estos estados. */
export function cameraIsOn(status: FaceStatus): boolean {
  return status === "noFace" || status === "face" || status === "several";
}

function eyeCenter(face: readonly FacePoint[], [a, b]: readonly [number, number]): FacePoint | null {
  const first = face[a];
  const second = face[b];
  if (first === undefined || second === undefined) return null;
  return { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 };
}

/**
 * El giro de la cara sobre el plano de la pantalla, en grados en el sentido del reloj, el de
 * `rotate()` de CSS: el giro al que hay que poner la vista para que quede derecha para esa cara.
 * Cara derecha delante de la pantalla, 0; cabeza hacia el borde derecho de la pantalla, 90.
 *
 * La imagen de la cámara frontal no lleva espejo: la x de la imagen va al revés que la de la
 * pantalla vista por la persona. En coordenadas de la pantalla, la derecha de la persona apunta
 * de su ojo izquierdo a su ojo derecho, y eso es (xᵢ − x_d, y_d − yᵢ) en la imagen. Las fracciones
 * se pasan a píxeles con el tamaño de la imagen, que no es cuadrada. `null` si falta un ojo o la
 * recta es demasiado corta.
 *
 * Si está la barbilla (`CHIN`), el sentido sale de ella: «abajo» de la persona va de entre los
 * ojos a la barbilla, (x_b − xₘ, y_b − yₘ) en la imagen, y su giro es atan2(Δx, Δy). Si la recta de
 * los ojos apunta a más de 90° de eso, se le da la vuelta.
 */
export function eyeLineAngle(face: readonly FacePoint[], width: number, height: number): number | null {
  if (!(width > 0) || !(height > 0)) return null;
  const right = eyeCenter(face, RIGHT_EYE);
  const left = eyeCenter(face, LEFT_EYE);
  if (right === null || left === null) return null;
  const dx = (left.x - right.x) * width;
  const dy = (right.y - left.y) * height;
  if (!Number.isFinite(dx) || !Number.isFinite(dy) || Math.hypot(dx, dy) < MIN_EYE_SPAN_PX) return null;
  const angle = normalizeDegrees((Math.atan2(dy, dx) * 180) / Math.PI);
  const chin = face[CHIN];
  if (chin === undefined) return angle;
  const downX = (chin.x - (left.x + right.x) / 2) * width;
  const downY = (chin.y - (left.y + right.y) / 2) * height;
  if (!Number.isFinite(downX) || !Number.isFinite(downY) || Math.hypot(downX, downY) < MIN_EYE_SPAN_PX) return angle;
  const down = (Math.atan2(downX, downY) * 180) / Math.PI;
  return Math.abs(signedDelta(angle, down)) > 90 ? normalizeDegrees(angle + 180) : angle;
}

/**
 * Lo que vio la cámara: ninguna cara (o una que no se ve bien), varias, o una con su ángulo. Con
 * varias no se elige a nadie: la vista no sabe para quién girar.
 */
export function readFaces(faces: readonly (readonly FacePoint[])[], width: number, height: number): FaceReading {
  if (faces.length > 1) return { kind: "several", count: faces.length };
  const face = faces[0];
  if (face === undefined) return { kind: "none" };
  const angle = eyeLineAngle(face, width, height);
  return angle === null ? { kind: "none" } : { kind: "one", angle };
}

export function faceStatusOf(reading: FaceReading): FaceStatus {
  return reading.kind === "one" ? "face" : reading.kind === "several" ? "several" : "noFace";
}

/** El giro que toca: solo una cara lo mueve, y con histéresis; sin cara o con varias, se queda. */
export function faceRotation(current: Rotation, reading: FaceReading): Rotation {
  return reading.kind === "one" ? followQuadrant(current, reading.angle) : current;
}

/**
 * Con los dos modos encendidos, ¿manda la cara? Sí mientras la cámara ve una cara o varias (con
 * varias, para dejar la vista quieta): el giroscopio no gira nada y cada búsqueda le fija su
 * «arriba» en la vista de ese momento. Si la cámara no ve a nadie, o no está, sigue el giroscopio
 * desde ahí, sin salto. Así la cara corrige además la deriva del giroscopio.
 */
export function faceHoldsView(status: FaceStatus): boolean {
  return status === "face" || status === "several";
}
