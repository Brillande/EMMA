/**
 * Otra persona delante de la pantalla, vista por la cámara de «Seguir la cara (demo)»: EMMA
 * propone la privacidad o, si se le ha pedido, la pone sola. **Demostración, sin validar.**
 *
 * Por qué existe: las notas de voz del equipo piden «poder tapar lo personal cuando hay otra
 * persona delante», y la idea 16 de `docs/contexto/prioridades-evento.md` («sensor de presencia
 * con modo incógnito») quedó fuera por necesitar hardware. La cámara frontal que ya usa
 * `faceOrientation.ts` cuenta caras: con dos o más, hay alguien más mirando. No hace falta otro
 * sensor, solo no confundir un parpadeo del detector con una persona.
 *
 * Solo se usa **cuántas caras** ve la cámara. No se reconoce a nadie, no se distingue quién es
 * quién ni se infiere nada de la cara: no es un dato clínico (invariante 7), no pasa por el
 * registro firmado y ningún fotograma se guarda ni sale del equipo (`faceCamera.ts`). La privacidad
 * es la de siempre (§5.40 de `compliance/hmi-state-of-the-art.md`): ponerla apaga la cámara, así
 * que después de ponerse sola nadie ve si la otra persona se ha ido; la quita quien mira, y la
 * cámara no vuelve a encenderse sola.
 *
 * Aquí va lo puro, con prueba (`faceCompany.test.ts`): la histéresis que separa una persona de un
 * fallo del detector, y qué aviso queda en pantalla con cada suceso.
 */

import type { FaceReading } from "./faceOrientation";
import { tr } from "./i18n";

/**
 * Cuánto tiene que verse más de una cara, seguido, para contar como otra persona delante. Parámetro
 * de diseño de EMMA, sin fuente: seis búsquedas de `DETECTION_INTERVAL_MS` (250 ms); lo bastante
 * para que una cara de un cartel o un reflejo que el detector ve un instante no lo dispare, y lo
 * bastante corto para que la privacidad llegue antes de que la otra persona lea la pantalla.
 */
export const COMPANY_ARRIVE_MS = 1500;

/**
 * Un hueco más corto que esto sin la segunda cara no rompe la racha: el detector pierde una cara
 * en una búsqueda suelta (giro de cabeza, mano delante). Dos búsquedas y algo. Sin fuente.
 */
export const COMPANY_GAP_MS = 600;

/**
 * Cuánto tiene que dejar de verse la segunda cara para dar a la otra persona por ida. Más largo que
 * la llegada a propósito (histéresis): el aviso no aparece y desaparece con cada parpadeo del
 * detector. Sin fuente.
 */
export const COMPANY_LEAVE_MS = 3000;

/** Lo que se lleva de una búsqueda a la siguiente. Tiempos en ms de un reloj que solo avanza. */
export interface CompanyState {
  /** Ya se da por hecho que hay otra persona delante. */
  readonly present: boolean;
  /** Desde cuándo dura la racha de varias caras (sin `present`). */
  readonly since: number | null;
  /** La última búsqueda que vio varias caras. */
  readonly lastSeveral: number | null;
}

export const NO_COMPANY: CompanyState = { present: false, since: null, lastSeveral: null };

/** Lo que pasa con una búsqueda: llega otra persona, se va, o nada. */
export type CompanyEvent = "arrived" | "left" | null;

/**
 * Una búsqueda más. Sin nadie más delante: la racha de «varias caras» empieza con la primera que
 * las ve, aguanta huecos de menos de `COMPANY_GAP_MS` y, cuando dura `COMPANY_ARRIVE_MS`, llega
 * otra persona. Con ella delante: se va cuando pasan `COMPANY_LEAVE_MS` sin ver varias caras. Un
 * reloj que va hacia atrás (no debería con `performance.now`) vuelve a empezar sin suceso.
 */
export function companyStep(
  state: CompanyState,
  reading: FaceReading,
  now: number,
): { state: CompanyState; event: CompanyEvent } {
  const several = reading.kind === "several";
  if (state.lastSeveral !== null && now < state.lastSeveral) {
    return { state: several ? { present: false, since: now, lastSeveral: now } : NO_COMPANY, event: null };
  }
  if (state.present) {
    if (several) return { state: { ...state, lastSeveral: now }, event: null };
    if (state.lastSeveral === null || now - state.lastSeveral >= COMPANY_LEAVE_MS) {
      return { state: NO_COMPANY, event: "left" };
    }
    return { state, event: null };
  }
  if (several) {
    const continues = state.since !== null && state.lastSeveral !== null && now - state.lastSeveral < COMPANY_GAP_MS;
    const since = continues ? (state.since as number) : now;
    if (now - since >= COMPANY_ARRIVE_MS) return { state: { present: true, since: null, lastSeveral: now }, event: "arrived" };
    return { state: { present: false, since, lastSeveral: now }, event: null };
  }
  if (state.lastSeveral !== null && now - state.lastSeveral >= COMPANY_GAP_MS) return { state: NO_COMPANY, event: null };
  return { state, event: null };
}

/**
 * El aviso de la franja: EMMA propone la privacidad (`proposed`) o dice que la ha puesto sola
 * (`protected`). Sin aviso, `null`.
 */
export type PresenceNotice = "proposed" | "protected" | null;

/** Lo que mueve el aviso. */
export type PresenceInput =
  | { readonly kind: "arrived"; readonly auto: boolean }
  | { readonly kind: "left" }
  /** La persona pulsa «Activar la privacidad» o «No, seguir». */
  | { readonly kind: "accepted" }
  | { readonly kind: "dismissed" }
  /** La cámara se apaga (modo quitado, privacidad puesta, ventana oculta). */
  | { readonly kind: "cameraOff" }
  /** La privacidad se quita. */
  | { readonly kind: "privacyOff" };

/**
 * El aviso después de un suceso. Al llegar otra persona: con «Privacidad automática con otra cara»,
 * `protected` (quien llama pone la privacidad); sin él, `proposed`. La propuesta se va si la otra
 * persona se va, si se contesta o si la cámara se apaga (ya no se sabe quién hay). Lo de
 * `protected` se queda mientras la privacidad siga puesta: dice por qué está, y lo quita quitarla.
 * Contestar «no» a la propuesta no la vuelve a sacar hasta que la otra persona se vaya y vuelva.
 */
export function presenceNotice(current: PresenceNotice, input: PresenceInput): PresenceNotice {
  switch (input.kind) {
    case "arrived":
      return input.auto ? "protected" : "proposed";
    case "left":
    case "cameraOff":
    case "accepted":
    case "dismissed":
      return current === "proposed" ? null : current;
    case "privacyOff":
      return current === "protected" ? null : current;
  }
}

/** La pregunta de la propuesta, la que se ve y la que oye el lector de pantalla. */
export const PROPOSAL_TEXT = tr(
  "Hay otra persona delante: ¿activo la privacidad?",
  "Someone else is in front of the screen: shall I turn privacy on?",
);

/** Lo que se dice al ponerla sola. */
export const PROTECTED_TEXT = tr(
  "Hay otra persona delante: he puesto la privacidad. La cámara se ha apagado; la privacidad sigue hasta que la quites.",
  "Someone else is in front of the screen: I have turned privacy on. The camera is off; privacy stays on until you turn it off.",
);

/** La frase del aviso, para el lector de pantalla (`lib/announce.ts`). */
export function presenceText(notice: Exclude<PresenceNotice, null>): string {
  return notice === "proposed" ? PROPOSAL_TEXT : PROTECTED_TEXT;
}
