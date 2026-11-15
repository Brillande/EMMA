/**
 * EMMA toma la iniciativa: lo que dice sin que se lo pidan, cuándo y en qué orden.
 *
 * Por qué existe: el usuario pidió (2026-11-03) una EMMA «tipo Jarvis» que, entre otras cosas,
 * hable por iniciativa propia. La consola ya leía el estado a petición y avisaba de cada alerta
 * nueva (`lib/speech.ts`, `lib/announce.ts`), pero quien tiene las manos y la vista en otra cosa
 * no se enteraba de que una medida periódica se había atrasado, de que había cambiado el nivel de
 * misión o de que empezaba un evento solar, salvo yendo a mirar la pestaña donde se ve.
 *
 * **Sin modelo de lenguaje.** Lo que se dice son rótulos de navegación fijos («Hola, soy EMMA.»,
 * «Alerta nueva:», «Medida periódica:», «Nivel de misión:») y el texto del backend tal cual (el
 * resumen del estado, la frase de cada alerta de `lib/announce.ts`, el nombre de cada medida y las
 * frases del evento solar y del nivel de misión de `/api/timeline/routines`). Un aviso que nace
 * sin que nadie pregunte tiene que ser exactamente lo que la pantalla ya dice: si lo redactara un
 * modelo (Clase C, invariante 6), sería un texto clínico sin validar llegando al oído sin que la
 * persona lo haya pedido. La interfaz no redacta texto clínico (`CLAUDE.md`).
 *
 * **Las alertas, con el criterio de `lib/announce.ts`**, no con uno propio: una vez, la escalada
 * es otra alerta, la que vuelve se dice otra vez, lo suprimido o inhibido no se dice (F.6.4,
 * *Annunciation State*), por ámbito (consola y tripulante) y con la privacidad sin motivos. Aquí
 * solo se traduce su urgencia a prioridad.
 *
 * **Lo demás, comparando sondeos que la consola ya hace.** Las medidas periódicas, el nivel de
 * misión y el evento solar salen de `/api/timeline/routines`, que el panel de medidas ya pide con
 * cada estado nuevo: con este modo se pide una vez más con cada estado (una sola lectura, al ritmo
 * del sondeo de siempre, y solo en la consola de a bordo), porque el panel vive en una pestaña que
 * puede no estar montada. La primera lectura de un ámbito es la línea de partida: no se dice nada
 * de ella, solo de lo que cambia después.
 *
 * **Tope y orden (parámetros de diseño de EMMA, sin fuente):** no más de un aviso no crítico cada
 * `NOTICE_GAP_MS`; los que esperan van en cola por prioridad (`PRIORITY_ORDER`). Las alertas no
 * se caen de la cola (con este modo, el modo voz deja de decirlas: perderlas sería callarlas); el
 * resto, como mucho `QUEUE_LIMIT` y durante `QUEUE_TTL_MS` (un aviso viejo describe una pantalla
 * que ya no es). El saludo y lo crítico no cuentan para el tope: no retrasan el aviso siguiente.
 * Lo crítico —una alerta que `lib/announce.ts` diría asertiva: clases W y C sin reconocer— pasa
 * siempre, sin esperar turno, y corta lo que se esté diciendo.
 *
 * **Silencio** (`silenceFor`): calla lo no crítico durante un rato y vacía la cola; lo que llega
 * mientras tanto no se guarda para después (sigue en pantalla). Apagar el modo quita el silencio:
 * al volver a encenderlo, saluda. **Lo crítico no se silencia**:
 * F.6.4 da a la persona *Suppress* e *Inhibit* sobre una alerta concreta, con su motivo en el
 * ledger y con límites (§2.4 del estado del arte: una crítica se suprime una hora como mucho y no
 * se inhibe nunca, y una escalada rompe siempre el silencio). Un silencio general de la voz que
 * callara una alerta crítica sería una supresión sin firma, sin motivo y sin límite: justo lo que
 * esos límites impiden. Para callar una alerta concreta está suprimirla, y entonces tampoco se dice.
 *
 * **Quién habla.** Este módulo lo dice con la voz de la consola (`useSpeaker`) y, además, lo emite
 * al canal del asistente (`assistant/bus.ts`) como `{kind: "say", text}` para que el hilo de la
 * conversación lo enseñe. El `say` del canal ya está dicho en voz alta: quien lo escuche lo pone
 * en el hilo y no lo vuelve a decir. Así se oye igual con el hilo montado o sin él, y una sola vez.
 *
 * Aquí va lo que se prueba sin navegador; lo que pide al backend y toca la voz, en `useProactive`.
 */

import type { Alert } from "../lib/alerts";
import type { RoutineState, RoutinesView } from "../lib/api";
import { type AnnouncerState, INITIAL_ANNOUNCER, planAnnouncements } from "../lib/announce";
import { tr } from "../lib/i18n";
import { ROUTINE_WORDS } from "../lib/routineWords";
import { NEW_ALERT_LABEL, sentence, statusSpeech } from "../lib/speech";

// --- Parámetros de diseño de EMMA, sin fuente ---------------------------------------------------

/** Como mucho un aviso no crítico cada tanto: el sondeo es de 30 s, así que uno por sondeo. */
export const NOTICE_GAP_MS = 30_000;
/** Cuántos avisos esperan turno; si llegan más, se queda lo más importante. */
export const QUEUE_LIMIT = 5;
/** Cuánto vale un aviso en cola: más tarde ya describe una pantalla que no es la de ahora. */
export const QUEUE_TTL_MS = 120_000;
/** El silencio que pone el mando de la consola. */
export const DEFAULT_SILENCE_MS = 15 * 60_000;

/**
 * Prioridad, de más a menos. `critical` pasa siempre; `entry` (el saludo y el estado al abrir o al
 * cambiar de consola o tripulante) no espera turno, porque es la pantalla que se acaba de pedir,
 * pero sí respeta el silencio. Después, alertas no críticas, el nivel de misión, el evento solar y
 * las medidas periódicas: lo que cambia cómo se vigila antes que lo que falta por medir.
 */
export const PRIORITY_ORDER = ["critical", "entry", "alert", "mission", "solar", "routine"] as const;
export type Priority = (typeof PRIORITY_ORDER)[number];

export interface Notice {
  /** Un aviso por clave: el mismo aviso que llega dos veces ocupa un solo sitio en la cola. */
  key: string;
  /** El ámbito (consola y tripulante) del que habla. */
  scope: string;
  priority: Priority;
  /** Lo que se dice, en trozos: cada uno es un enunciado de la síntesis. */
  chunks: string[];
  /** Cuándo nació, para caducar en la cola. */
  at: number;
}

const rank = (priority: Priority) => PRIORITY_ORDER.indexOf(priority);

// --- Lo que se dice ----------------------------------------------------------------------------

export const GREETING = tr("Hola, soy EMMA.", "Hello, I am EMMA.");
/** El mismo rótulo que dice el modo voz (`lib/speech.ts`): una sola fuente. */
export const NEW_ALERT = NEW_ALERT_LABEL;
export const ROUTINE_LABEL = tr("Medida periódica:", "Periodic measurement:");
export const MISSION_LABEL = tr("Nivel de misión:", "Mission level:");

/**
 * Lo que se dice al entrar en un ámbito: el saludo (solo la primera vez), la consola, de quién es
 * —sin el nombre con la privacidad, como `statusSpeech`—, el resumen del backend y las alertas que
 * hay, con la frase de `lib/announce.ts`.
 */
export function entrySpeech({
  greet,
  console: consoleName,
  subject,
  summary,
  alerts,
  privacy,
}: {
  greet: boolean;
  console: string;
  subject: string;
  summary: string;
  /** Las frases de las alertas que hay, ya con la privacidad aplicada (`announcementText`). */
  alerts: readonly string[];
  privacy: boolean;
}): string[] {
  const [head = ""] = statusSpeech({ console: consoleName, subject, summary, alerts: [], privacy });
  const chunks = [greet ? `${GREETING} ${head}` : head];
  for (const text of alerts) chunks.push(sentence(text));
  return chunks.filter((chunk) => chunk.trim() !== "");
}

// --- Diferencias entre sondeos -------------------------------------------------------------------

/** Lo que se recuerda de las medidas, el nivel y el evento para el sondeo siguiente. */
export interface RoutineMemory {
  /** Estado de cada medida; `suspendida` si el nivel de misión no la espera. */
  states: ReadonlyMap<string, string>;
  level: string | null;
  event: string | null;
  /** El evento en curso llegó con su frase: solo entonces se dice que acaba. */
  eventNoted: boolean;
}

/** El estado de cada medida tal como cuenta para avisar: lo suspendido no se debe. */
function routineStates(routines: readonly RoutineState[]): Map<string, string> {
  return new Map(routines.map((item) => [item.key, item.suspended === true ? "suspendida" : item.state]));
}

function eventId(view: RoutinesView): string | null {
  const id = view.active_event?.event_id;
  // Un evento sin identificador sigue siendo un evento en curso: cuenta para «empieza» y «acaba».
  return typeof id === "string" ? id : view.active_event == null ? null : "en-curso";
}

export function routineMemory(view: RoutinesView): RoutineMemory {
  const event = eventId(view);
  const noted = event !== null && view.event_note != null && view.event_note.trim() !== "";
  return { states: routineStates(view.routines), level: view.mission_level ?? null, event, eventNoted: noted };
}

/**
 * Los avisos de una lectura de medidas frente a la anterior del mismo ámbito. Sin anterior (`null`)
 * es la línea de partida: no se avisa de nada. Se avisa de:
 *
 * - una medida que pasa a atrasada o a sin lectura buena (de cualquier otro estado, también de
 *   una a la otra); la que vuelve a su ritmo no se dice, se ve en el panel;
 * - el nivel de misión que cambia, con su nombre del backend y su frase si suspende medidas; sin
 *   el nombre del backend no se dice (la clave interna no es una palabra para nadie);
 * - el evento solar que empieza (o es otro) y el que acaba, con la frase del backend; sin frase
 *   del backend no se dice nada, porque aquí no se redacta, y no se dice que acaba uno cuyo
 *   comienzo no se dijo.
 */
export function routineNotices(
  previous: RoutineMemory | null,
  view: RoutinesView,
  scope: string,
  now: number,
): { notices: Notice[]; memory: RoutineMemory } {
  const memory = routineMemory(view);
  if (previous === null) return { notices: [], memory };
  const notices: Notice[] = [];
  const make = (key: string, priority: Priority, chunks: string[]): Notice => ({
    key: `${scope}|${key}`,
    scope,
    priority,
    chunks: chunks.filter((chunk) => chunk !== ""),
    at: now,
  });
  const name = view.mission_level_display?.trim() ?? "";
  if (memory.level !== null && previous.level !== null && memory.level !== previous.level && name !== "") {
    notices.push(make(`mission:${memory.level}`, "mission", [
      sentence(`${MISSION_LABEL} ${name}`),
      sentence(view.suspended_note ?? ""),
    ]));
  }
  if (memory.event !== previous.event) {
    const note = memory.event === null ? (previous.eventNoted ? view.event_over_note : null) : view.event_note;
    if (note != null && note.trim() !== "") {
      notices.push(make(`solar:${memory.event ?? "none"}`, "solar", [sentence(note)]));
    }
  }
  for (const item of view.routines) {
    const state = memory.states.get(item.key);
    if (state !== "atrasada" && state !== "rota") continue;
    const before = previous.states.get(item.key);
    // Una medida que no estaba en la lectura anterior es nueva en la lista: su estado es la
    // línea de partida, como en la primera lectura.
    if (before === undefined || before === state) continue;
    notices.push(make(`routine:${item.key}:${state}`, "routine", [
      sentence(`${ROUTINE_LABEL} ${item.display_es}, ${ROUTINE_WORDS[state]}`),
    ]));
  }
  return { notices, memory };
}

/** Lo que el sondeo de estado deja dicho: el plan de alertas de `lib/announce.ts` y el saludo. */
export interface AlertMemory {
  announcer: AnnouncerState;
  greeted: boolean;
}

export const INITIAL_ALERT_MEMORY: AlertMemory = { announcer: INITIAL_ANNOUNCER, greeted: false };

/**
 * Los avisos de un estado nuevo. Las alertas las decide `planAnnouncements` (el mismo criterio que
 * el lector de pantalla); al entrar en un ámbito, todas van dentro del aviso de entrada, después
 * del resumen; desde ahí, cada alerta nueva es un aviso, crítico si `announce.ts` la diría asertiva.
 */
export function statusNotices(
  previous: AlertMemory,
  input: {
    scope: string;
    console: string;
    subject: string;
    summary: string;
    alerts: readonly Alert[];
    annunciation: ReadonlyMap<string, string>;
    acknowledged: ReadonlySet<string>;
    privacy: boolean;
    now: number;
  },
): { notices: Notice[]; memory: AlertMemory } {
  const plan = planAnnouncements(previous.announcer, input);
  if (plan.entered) {
    const entry: Notice = {
      key: `${input.scope}|entry`,
      scope: input.scope,
      priority: "entry",
      chunks: entrySpeech({
        greet: !previous.greeted,
        console: input.console,
        subject: input.subject,
        summary: input.summary,
        alerts: plan.announce.map((item) => item.text),
        privacy: input.privacy,
      }),
      at: input.now,
    };
    return { notices: [entry], memory: { announcer: plan.state, greeted: true } };
  }
  const notices = plan.announce.map(
    (item): Notice => ({
      key: `${input.scope}|alert:${item.key}`,
      scope: input.scope,
      priority: item.urgency === "assertive" ? "critical" : "alert",
      chunks: [`${NEW_ALERT} ${sentence(item.text)}`],
      at: input.now,
    }),
  );
  return { notices, memory: { announcer: plan.state, greeted: previous.greeted } };
}

// --- Cola, tope y silencio ---------------------------------------------------------------------

export interface Pacer {
  queue: Notice[];
  /** Cuándo se dijo el último aviso; `null` si aún ninguno. */
  lastAt: number | null;
}

export const INITIAL_PACER: Pacer = { queue: [], lastAt: null };

/** Por prioridad y, a igual prioridad, por orden de llegada. */
function byPriority(a: Notice, b: Notice): number {
  return rank(a.priority) - rank(b.priority) || a.at - b.at;
}

/** Lo que nunca se cae de la cola por tope ni por edad: lo crítico y las alertas. */
function keeps(notice: Notice): boolean {
  return notice.priority === "critical" || notice.priority === "alert";
}

/**
 * Pone avisos en la cola. Uno con la misma clave sustituye al que esperaba; uno de entrada se lleva
 * lo que esperaba de otros ámbitos (habla de otra pantalla). Con silencio, lo no crítico ni entra.
 * Si lo demás pasa de `QUEUE_LIMIT`, sale lo menos importante; lo crítico y las alertas, nunca.
 */
export function enqueue(pacer: Pacer, notices: readonly Notice[], now: number, silencedUntil: number): Pacer {
  let queue = [...pacer.queue];
  for (const notice of notices) {
    if (notice.priority !== "critical" && now < silencedUntil) continue;
    if (notice.priority === "entry") queue = queue.filter((item) => item.scope === notice.scope);
    queue = queue.filter((item) => item.key !== notice.key);
    queue.push(notice);
  }
  queue.sort(byPriority);
  const rest = new Set(queue.filter((item) => !keeps(item)).slice(0, QUEUE_LIMIT));
  return { ...pacer, queue: queue.filter((item) => keeps(item) || rest.has(item)) };
}

/**
 * Lo que toca decir ahora. Lo crítico, todo y siempre. Lo de entrada, en cuanto llega (sin
 * silencio). Lo demás, uno, y solo si han pasado `NOTICE_GAP_MS` desde el último de esos y no hay
 * silencio. Lo caducado (salvo alertas) se cae de la cola sin decirse.
 */
export function drain(
  pacer: Pacer,
  now: number,
  silencedUntil: number,
): { speak: Notice[]; interrupt: boolean; pacer: Pacer } {
  const silenced = now < silencedUntil;
  const fresh = pacer.queue.filter((item) => keeps(item) || now - item.at <= QUEUE_TTL_MS);
  const speak: Notice[] = fresh.filter((item) => item.priority === "critical");
  const rest = fresh.filter((item) => item.priority !== "critical");
  const waiting: Notice[] = [];
  let paced = false;
  for (const item of rest) {
    if (silenced) continue;
    const due = item.priority === "entry" || (!paced && (pacer.lastAt === null || now - pacer.lastAt >= NOTICE_GAP_MS));
    if (due) {
      speak.push(item);
      if (item.priority !== "entry") paced = true;
    } else {
      waiting.push(item);
    }
  }
  const interrupt = speak.some((item) => item.priority === "critical");
  return {
    speak,
    interrupt,
    pacer: { queue: waiting, lastAt: paced ? now : pacer.lastAt },
  };
}

// --- El silencio, de toda la consola --------------------------------------------------------------

let silencedUntilMs = 0;
const silenceListeners = new Set<() => void>();

function notifySilence(): void {
  for (const listener of silenceListeners) listener();
}

/**
 * Calla lo no crítico de EMMA durante `ms` desde `now`. La llaman el mando de la consola y el
 * asistente (la intención «silencio»). Un valor de 0 o menos quita el silencio. Lo crítico se
 * sigue diciendo (ver arriba, F.6.4).
 */
export function silenceFor(ms: number, now: number = Date.now()): void {
  silencedUntilMs = ms > 0 ? now + ms : 0;
  notifySilence();
}

/** Hasta cuándo dura el silencio (milisegundos de época); 0 si no hay. */
export function silencedUntil(): number {
  return silencedUntilMs;
}

/** Para `useSyncExternalStore`: avisa cuando el silencio cambia. */
export function subscribeSilence(listener: () => void): () => void {
  silenceListeners.add(listener);
  return () => silenceListeners.delete(listener);
}
