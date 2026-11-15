/**
 * Manos libres con la palabra «EMMA»: lo que se puede decidir sin navegador.
 *
 * Por qué existe: en una nave la persona puede tener las manos ocupadas (un experimento, un
 * ejercicio, un guante) o no estar delante de la pantalla, y pulsar un botón para hablar no
 * siempre es posible. Con este modo la consola oye la palabra «EMMA» y graba solo la frase que
 * sigue, hasta que la persona calla, para el asistente (`assistant/bus.ts`). El reconocimiento de
 * voz de Chrome no sirve: manda el audio a Google (invariante 3 bis). Se usa Vosk dentro del
 * navegador, con una gramática cerrada que solo sabe la palabra y la frase de apagar
 * (`listener.ts`), y aquí viven las reglas que tienen que cumplirse siempre:
 *
 * - la máquina de estados: apagado, cargando, escuchando la palabra, grabando la frase, enviando
 *   y no disponible; lo de antes de la palabra no se graba;
 * - el detector de silencio por energía que cierra la frase;
 * - qué resultado de Vosk cuenta como la palabra y cuál como «EMMA, deja de escuchar»;
 * - qué apaga el modo.
 *
 * Los umbrales del detector de silencio (energía, 1 s de silencio, 10 s de tope, 3 s de espera
 * a que empiece a hablar) son **parámetros de diseño sin fuente**: elegidos para una consola en
 * una sala tranquila, sin medir con el ruido de una nave ni con personas.
 *
 * **Dos idiomas (2026-11-15).** La palabra, la frase de apagar y la gramática salen del idioma de
 * la interfaz (`WAKE_VOCABULARY`, `wakeGrammar`), porque cada idioma lleva su modelo de Vosk
 * (`listener.ts`). En castellano son las de siempre: «emma» y «emma deja de escuchar». En inglés,
 * «emma» y «emma stop listening». **Que el modelo inglés reconozca «EMMA» ESTÁ SIN VERIFICAR**: el
 * modelo no está en el repositorio y no se ha probado. Una gramática de Vosk solo admite palabras
 * del vocabulario del modelo; una que no está la descarta con un aviso en la consola y el modo se
 * queda escuchando sin oír nunca la palabra. Por eso las formas inglesas de la palabra son una
 * lista declarada (`ENGLISH_WAKE_FORMS`) que se ajusta al probar el modelo real, sin tocar nada
 * más: cada forma es una o varias palabras del vocabulario que suenan como «EMMA».
 */

import { type Language, language, tr } from "../../lib/i18n";

/** Por qué no se puede escuchar, dicho para la interfaz. */
export type WakeUnavailable = "sin micrófono" | "sin permiso" | "sin modelo" | "sin audio del navegador";

export type WakeState =
  | { kind: "off" }
  | { kind: "loading" }
  | { kind: "unavailable"; reason: WakeUnavailable }
  /**
   * Oyendo por si llega la palabra. `armed` es falso justo después de una frase: los resultados
   * parciales de Vosk de esa misma frase siguen diciendo «emma» hasta su resultado final, y no
   * deben abrir otra grabación.
   */
  | { kind: "listening"; armed: boolean }
  /**
   * Grabando la frase, o enviándola. `settled` dice si ya llegó el resultado final de Vosk de la
   * frase que abrió la grabación: al volver a escuchar, la palabra se acepta de nuevo solo si llegó.
   */
  | { kind: "recording"; settled: boolean }
  | { kind: "sending"; settled: boolean };

export type WakeEvent =
  | { type: "enable" }
  | { type: "ready" }
  | { type: "unavailable"; reason: WakeUnavailable }
  /** Un resultado de Vosk: `partial` mientras se habla, `final` al cerrar cada frase. */
  | { type: "heard"; text: string; final: boolean; speaking?: boolean }
  /**
   * La voz propia de EMMA (`lib/speech.ts`) habla. Lo que dice sale por el altavoz y entra por el
   * micrófono: «Hola, soy EMMA» no puede abrir una grabación ni grabarse. Mientras habla, cada
   * `heard` llega con `speaking`, y este evento tira una grabación que estuviera abierta.
   */
  | { type: "speaking" }
  /** El detector de silencio cerró la frase (`end`) o no llegó a empezar (`empty`). */
  | { type: "phrase"; outcome: "end" | "empty" }
  | { type: "sent" }
  | { type: "disable" };

export const OFF: WakeState = { kind: "off" };

/** Las palabras que reconoce Vosk en castellano; cualquier otra cosa sale como `[unk]`. */
export const WAKE_WORD = "emma";
/** Lo que sigue a la palabra para apagar, en castellano: una sola fuente para la frase y la tabla. */
const SPANISH_STOP = "deja de escuchar";
export const STOP_PHRASE = `${WAKE_WORD} ${SPANISH_STOP}`;
export const GRAMMAR: readonly string[] = [WAKE_WORD, STOP_PHRASE, "[unk]"];

/**
 * Las formas de la palabra «EMMA» para el modelo inglés (`vosk-model-small-en-us-0.15`), en
 * minúsculas. SIN VERIFICAR con el modelo en disco (ver el comentario del módulo). Si «emma» no
 * está en su vocabulario, aquí se pone lo que sí esté y suene igual, probándolo: candidatas, «em
 * ma», «emmer», «ema». Cada forma de más es también una vía más de disparo en falso: se deja la
 * lista tan corta como el modelo permita.
 */
export const ENGLISH_WAKE_FORMS: readonly string[] = ["emma"];

/** Lo que cada idioma dice a Vosk: las formas de la palabra y lo que sigue a ella para apagar. */
export interface WakeVocabulary {
  /** Cada forma, una o varias palabras en minúsculas separadas por un espacio. */
  readonly wake: readonly string[];
  /** Lo que se dice tras la palabra para apagar el modo. */
  readonly stop: string;
}

export const WAKE_VOCABULARY: Record<Language, WakeVocabulary> = {
  es: { wake: [WAKE_WORD], stop: SPANISH_STOP },
  en: { wake: ENGLISH_WAKE_FORMS, stop: "stop listening" },
};

/** Las frases de apagar de un idioma: cada forma de la palabra seguida de lo que apaga. */
export function stopPhrases(lang: Language = language()): string[] {
  const { wake, stop } = WAKE_VOCABULARY[lang];
  return wake.map((form) => `${form} ${stop}`);
}

/**
 * La gramática cerrada de un idioma, construida como la castellana de siempre: las formas de la
 * palabra, las frases de apagar y `[unk]`. En castellano es `GRAMMAR`, tal cual.
 */
export function wakeGrammar(lang: Language = language()): string[] {
  return [...WAKE_VOCABULARY[lang].wake, ...stopPhrases(lang), "[unk]"];
}

/** Las palabras de un resultado de Vosk, en minúsculas y sin `[unk]` ni signos. */
export function wordsOf(text: string): string[] {
  return text
    .toLowerCase()
    .normalize("NFC")
    .split(/[^\p{L}\p{N}[\]]+/u)
    .filter((word) => word !== "" && word !== "[unk]");
}

/** Si lo oído lleva esas palabras seguidas y enteras (no como trozo de otra palabra). */
function says(text: string, phrase: string): boolean {
  return ` ${wordsOf(text).join(" ")} `.includes(` ${phrase} `);
}

/** Si el resultado dice la palabra «EMMA» (en una de las formas del idioma), sola o con algo más. */
export function heardWakeWord(text: string): boolean {
  return WAKE_VOCABULARY[language()].wake.some((form) => says(text, form));
}

/**
 * Si el resultado dice «EMMA, deja de escuchar» («EMMA, stop listening» en inglés), con todas sus
 * palabras seguidas.
 */
export function heardStop(text: string): boolean {
  return stopPhrases().some((phrase) => says(text, phrase));
}

/**
 * Qué resultado de Vosk interesa, leído del mensaje tal cual llega del trabajador: `partial`
 * (`{result: {partial}}`) o `final` (`{result: {text}}`). Cualquier otra forma no es nada.
 */
export function readVoskResult(message: unknown): { text: string; final: boolean } | null {
  if (typeof message !== "object" || message === null) return null;
  const result = (message as { result?: unknown }).result;
  if (typeof result !== "object" || result === null) return null;
  const { partial, text } = result as { partial?: unknown; text?: unknown };
  if (typeof text === "string") return { text, final: true };
  if (typeof partial === "string") return { text: partial, final: false };
  return null;
}

/** Si dos estados son el mismo: un resultado de Vosk que no cambia nada no repinta la consola. */
export function sameState(a: WakeState, b: WakeState): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === "listening" && b.kind === "listening") return a.armed === b.armed;
  if ((a.kind === "recording" || a.kind === "sending") && (b.kind === "recording" || b.kind === "sending")) {
    return a.settled === b.settled;
  }
  if (a.kind === "unavailable" && b.kind === "unavailable") return a.reason === b.reason;
  return true;
}

/** Si el micrófono está abierto en este estado: es cuando sale «Micrófono escuchando». */
export function microphoneOpen(state: WakeState): boolean {
  return state.kind === "listening" || state.kind === "recording" || state.kind === "sending";
}

/**
 * El paso de la máquina. Pura: los efectos (abrir el micrófono, empezar o parar la grabación,
 * emitir la frase) los hace `listener.ts` al ver el cambio de estado.
 */
export function step(state: WakeState, event: WakeEvent): WakeState {
  if (event.type === "disable") return OFF;
  switch (state.kind) {
    case "off":
      return event.type === "enable" ? { kind: "loading" } : state;
    case "unavailable":
      return state;
    case "loading":
      if (event.type === "ready") return { kind: "listening", armed: true };
      if (event.type === "unavailable") return { kind: "unavailable", reason: event.reason };
      return state;
    case "listening":
      if (event.type === "unavailable") return { kind: "unavailable", reason: event.reason };
      if (event.type !== "heard") return state;
      // Mientras habla la voz propia nada de lo oído cuenta, ni la palabra ni la frase de apagar.
      // Sus parciales desarman: hasta el final de esa frase, la palabra no abre nada.
      if (event.speaking === true) return { kind: "listening", armed: event.final };
      if (event.final && heardStop(event.text)) return OFF;
      // Un final con la palabra que ningún parcial dio a tiempo también abre la grabación.
      if (state.armed && heardWakeWord(event.text)) return { kind: "recording", settled: event.final };
      return event.final ? { kind: "listening", armed: true } : state;
    case "recording":
    case "sending":
      if (event.type === "unavailable") return { kind: "unavailable", reason: event.reason };
      // La voz propia empieza a hablar con la grabación abierta: se tira, no se manda.
      if (state.kind === "recording" && event.type === "speaking") return { kind: "listening", armed: false };
      if (event.type === "heard" && event.speaking === true) return state;
      if (event.type === "heard" && event.final) {
        // «EMMA, deja de escuchar» mientras se graba o se envía: se tira la frase y se apaga.
        if (heardStop(event.text)) return OFF;
        return { ...state, settled: true };
      }
      if (state.kind === "recording" && event.type === "phrase") {
        return event.outcome === "end"
          ? { kind: "sending", settled: state.settled }
          : { kind: "listening", armed: state.settled };
      }
      if (state.kind === "sending" && event.type === "sent") return { kind: "listening", armed: state.settled };
      return state;
  }
}

// --- Detector de silencio -------------------------------------------------------------------

export interface SilenceOptions {
  /** Energía (RMS, muestras en -1..1) por encima de la cual un trozo cuenta como voz. */
  threshold: number;
  /** Silencio seguido, después de hablar, que cierra la frase. */
  silenceMs: number;
  /** Espera a que empiece a hablar tras la palabra; sin voz en ese tiempo, no hay frase. */
  leadMs: number;
  /** Tope de la frase. */
  maxMs: number;
  /**
   * Lo primero que se graba es la cola de la propia palabra (el parcial de Vosk llega mientras
   * se dice «-ma»): durante este tiempo la energía no cuenta como haber empezado a hablar.
   */
  graceMs: number;
}

/** Parámetros de diseño sin fuente (ver el comentario del módulo). ~-40 dBFS de umbral. */
export const SILENCE: SilenceOptions = { threshold: 0.01, silenceMs: 1000, leadMs: 3000, maxMs: 10_000, graceMs: 400 };

/** Energía RMS de un trozo de audio. */
export function rms(samples: ArrayLike<number>): number {
  if (samples.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < samples.length; i++) {
    const value = samples[i] ?? 0;
    sum += value * value;
  }
  return Math.sqrt(sum / samples.length);
}

export interface SilenceTracker {
  /**
   * Un trozo más de `durationMs` con energía `energy`. Devuelve `end` si la frase se cierra
   * (silencio tras hablar o tope), `empty` si no llegó a empezar y `null` si sigue.
   */
  push(energy: number, durationMs: number): "end" | "empty" | null;
}

export function silenceTracker(options: SilenceOptions = SILENCE): SilenceTracker {
  let elapsed = 0;
  let quiet = 0;
  let spoke = false;
  let done = false;
  return {
    push(energy, durationMs) {
      if (done) return null;
      elapsed += durationMs;
      if (elapsed <= options.graceMs) {
        // La cola de «EMMA»: ni voz ni silencio.
      } else if (energy >= options.threshold) {
        spoke = true;
        quiet = 0;
      } else {
        quiet += durationMs;
      }
      let outcome: "end" | "empty" | null = null;
      if (elapsed >= options.maxMs) outcome = spoke ? "end" : "empty";
      else if (spoke && quiet >= options.silenceMs) outcome = "end";
      else if (!spoke && elapsed >= options.leadMs) outcome = "empty";
      if (outcome !== null) done = true;
      return outcome;
    },
  };
}

// --- Qué apaga el modo ----------------------------------------------------------------------

/**
 * Si el micrófono puede estar abierto: el modo puesto, sin la privacidad (delante puede haber
 * otra persona) y con la ventana a la vista. Fuera de esto el modo se apaga, no se queda en
 * pausa: volver a la ventana no reabre el micrófono sin que nadie lo pida.
 */
export function wakeAllowed(input: { wakeWord: boolean; privacy: boolean; visible: boolean }): boolean {
  return input.wakeWord && !input.privacy && input.visible;
}

/** El motivo con palabras: la clave es la del estado (se compara en el código) y no se traduce. */
function wakeProblem(reason: WakeUnavailable): string {
  switch (reason) {
    case "sin permiso":
      return tr("sin permiso", "no permission");
    case "sin modelo":
      return tr("sin modelo", "no model");
    case "sin audio del navegador":
      return tr("sin audio del navegador", "no browser audio");
    default:
      return tr("sin micrófono", "no microphone");
  }
}

/** Qué hay que decir en el rótulo del modo según el estado, sin texto clínico. */
export function wakeLabel(state: WakeState): string {
  switch (state.kind) {
    case "off":
      return "";
    case "loading":
      return tr("Preparando la escucha", "Preparing to listen");
    case "unavailable":
      return tr(
        `Escucha no disponible: ${wakeProblem(state.reason)}`,
        `Listening unavailable: ${wakeProblem(state.reason)}`,
      );
    case "listening":
      return tr(
        "Di «EMMA» y lo que quieras; «EMMA, deja de escuchar» lo apaga",
        "Say “EMMA” and what you want; “EMMA, stop listening” turns it off",
      );
    case "recording":
      return tr("Te escucho", "I'm listening");
    case "sending":
      return tr("Enviando lo dicho al asistente", "Sending what was said to the assistant");
  }
}
