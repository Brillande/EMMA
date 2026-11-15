/**
 * Qué alerta se anuncia al lector de pantalla, cuándo y con qué urgencia (§5.41).
 *
 * Por qué existe: la franja cuenta las alertas y la fila parpadea, pero las dos cosas son para
 * los ojos. Una persona ciega con NVDA o el Narrador no se enteraba de una alerta nueva hasta
 * recorrer la lista: la consola se refresca cada 30 s y el lector no anuncia lo que cambia fuera
 * de donde está el foco si no hay una región viva. Y una región viva mal alimentada es peor que
 * ninguna: si se rellena con la lista entera en cada sondeo, repite las mismas alertas cada 30 s
 * y la persona deja de escucharlas, que es la fatiga de alarmas que F.6.4 intenta evitar con
 * suprimir e inhibir.
 *
 * Las reglas, aquí y con prueba (`announce.test.ts`), no en el componente:
 *
 * - **Una vez.** Cada alerta se anuncia la primera vez que aparece; el sondeo siguiente no la
 *   repite. La clave es la de la alerta (`dominio:nivel`), así que una escalada es otra alerta y
 *   se anuncia. Si deja de estar activa y vuelve, se anuncia otra vez.
 * - **Por ámbito (consola y tripulante).** Lo visto es del ámbito en pantalla. Al entrar en otro
 *   (abrir la consola, cambiar de consola o de tripulante) se dicen las alertas que hay, todas
 *   **corteses**: no son alertas nuevas, es el estado de la pantalla que la persona acaba de
 *   pedir, y no debe llegar como una ráfaga de interrupciones. Desde ahí, lo que aparece mientras
 *   se sigue en ese ámbito va con su urgencia. Volver a un ámbito es entrar otra vez: se dice lo
 *   que hay, así que no se pierde la alerta que se fue y volvió mientras se miraba otro.
 * - **Lo silenciado no se anuncia.** Una alerta suprimida o inhibida (F.6.4, *Annunciation
 *   State*) ya no reclama atención en la pantalla; tampoco en el lector. Si se vuelve a habilitar,
 *   se anuncia.
 * - **Urgencia por clase.** Asertiva (`role="alert"`, interrumpe lo que el lector esté diciendo)
 *   solo para las clases W y C de F.6.4, `critical` y `concern`, las dos que en la tabla F.5-1 son
 *   «emergency, warning» y «caution [...] attention required». La clase A (`watch`, *advisory*) va
 *   cortés (`role="status"`, espera a que el lector calle). Una alerta que alguien ya reconoció
 *   también va cortés: ya la vio una persona; se dice, pero no interrumpe.
 * - **Sin redactar.** La frase es la palabra del nivel que da el backend (`level_labels`), el
 *   nombre del dominio de la interfaz (el mismo rótulo de navegación de la fila) y los motivos
 *   del backend tal cual (`drivers`). Aquí solo se juntan; ningún texto clínico nace aquí.
 * - **Privacidad.** Con la privacidad puesta se dicen el nivel y el dominio, sin los motivos: los
 *   motivos llevan cifras del tripulante, y lo que se dice en voz alta llega más lejos que la
 *   pantalla. Siguen en la fila de la alerta, a la vista y al alcance del lector.
 */

import type { Alert } from "./alerts";
import { LEVELS, domainLabel } from "./levels";

export type Urgency = "assertive" | "polite";

export interface Announcement {
  /** La alerta (`dominio:nivel`). */
  key: string;
  text: string;
  urgency: Urgency;
}

/** Lo que se lleva de un sondeo al siguiente: de qué ámbito es y qué alertas ya se dijeron. */
export interface AnnouncerState {
  scope: string | null;
  seen: ReadonlySet<string>;
}

export const INITIAL_ANNOUNCER: AnnouncerState = { scope: null, seen: new Set() };

export interface AnnouncementPlan {
  /** Lo que hay que decir ahora, en el orden de la lista (lo más grave primero). */
  announce: Announcement[];
  /** El estado después de decirlo: lo que se pasa al sondeo siguiente. */
  state: AnnouncerState;
  /** Se ha entrado en otro ámbito: lo dicho antes es de otra pantalla. */
  entered: boolean;
}

export interface PlanInput {
  scope: string;
  alerts: readonly Alert[];
  /** Estado de anuncio de cada alerta según el ledger: `normal`, `suppressed`, `inhibited`. */
  annunciation: ReadonlyMap<string, string>;
  acknowledged: ReadonlySet<string>;
  privacy: boolean;
}

/** Asertiva para W y C (crítico y precaución), cortés para A; cortés si ya está reconocida. */
export function alertUrgency(alert: Alert, acknowledged: boolean): Urgency {
  if (acknowledged) return "polite";
  const cls = LEVELS[alert.level].alertClass;
  return cls === "W" || cls === "C" ? "assertive" : "polite";
}

/**
 * Junta las piezas con un punto entre ellas, salvo si la pieza ya acaba en signo de cierre: no se
 * le añade nada al texto del backend, solo una pausa entre frase y frase para el lector.
 */
function joinSentences(parts: readonly string[]): string {
  let text = "";
  for (const raw of parts) {
    const part = raw.trim();
    if (part === "") continue;
    if (text !== "") text += /[.!?:;…]$/.test(text) ? " " : ". ";
    text += part;
  }
  return text;
}

/**
 * La frase de una alerta: «<nivel>: <dominio>. <motivo>. <motivo>», sin redactar nada. Con la
 * privacidad, sin los motivos.
 */
export function announcementText(alert: Alert, privacy = false): string {
  const head = `${LEVELS[alert.level].label}: ${domainLabel(alert.domain)}`;
  return joinSentences(privacy ? [head] : [head, ...alert.drivers]);
}

/** El plan de un sondeo: qué alertas decir, con qué urgencia, y qué queda visto. */
export function planAnnouncements(previous: AnnouncerState, input: PlanInput): AnnouncementPlan {
  const entered = previous.scope !== input.scope;
  const before = entered ? new Set<string>() : previous.seen;
  const live = input.alerts.filter((alert) => (input.annunciation.get(alert.id) ?? "normal") === "normal");
  // Lo visto es lo que se anuncia ahora: lo que dejó de anunciarse se olvida y, si vuelve, se dice.
  const seen = new Set(live.map((alert) => alert.id));
  const announce: Announcement[] = live
    .filter((alert) => !before.has(alert.id))
    .map((alert) => ({
      key: alert.id,
      text: announcementText(alert, input.privacy),
      urgency: entered ? "polite" : alertUrgency(alert, input.acknowledged.has(alert.id)),
    }));
  return { announce, state: { scope: input.scope, seen }, entered };
}

/** Cuántos mensajes guarda cada región viva: lo justo para releerlos, no un historial. */
export const LIVE_REGION_KEEP = 5;

export interface LiveMessage {
  id: number;
  text: string;
}

/**
 * Añade mensajes nuevos a una región viva. Cada mensaje es un nodo nuevo con su `id`: el lector
 * anuncia lo añadido (`aria-relevant` por defecto, con `aria-atomic="false"`), así que la misma
 * frase dicha dos veces —una alerta que vuelve— se anuncia las dos. Se quedan los últimos
 * `LIVE_REGION_KEEP` de antes, pero nunca se recorta lo que llega en este sondeo: un mensaje que
 * no llega a la página no se dice, y los primeros de la lista son los más graves.
 */
export function appendMessages(
  current: readonly LiveMessage[],
  texts: readonly string[],
  firstId: number,
): LiveMessage[] {
  const added = texts.map((text, index) => ({ id: firstId + index, text }));
  return [...current, ...added].slice(-Math.max(LIVE_REGION_KEEP, added.length));
}
