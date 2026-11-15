/**
 * El micrófono, Vosk y la grabación de la frase: la parte de navegador del modo «Escuchar
 * "EMMA"». Las reglas están en `machine.ts`; aquí solo se hacen los efectos de cada cambio de
 * estado.
 *
 * Por qué es un módulo aparte, cargado solo al encender el modo (`import()` dinámico desde
 * `useWakeWord.ts`): `vosk-browser` son ~5,8 MB de JavaScript con su WebAssembly dentro, más
 * ~40 MB de modelo, y quien no usa el modo no debe pagarlos.
 *
 * **Todo en el equipo.** El modelo (`vosk-model-small-es-0.42`, origen y huella en
 * `public/vosk/ORIGEN.txt`) se sirve desde el propio paquete; el trabajador de Vosk, también
 * (`voskWorker.ts` dice por qué no va como `blob:`). El trabajador guarda el modelo
 * descomprimido en IndexedDB de este origen para no descomprimirlo en cada arranque: es el modelo,
 * nunca audio. Antes de cargar nada, `blockForeignFetch` hace que un `fetch` a otro origen falle
 * sin salir, como con la cámara.
 *
 * **Privacidad.** El audio que oye Vosk se queda en el trabajador, en memoria, y no se guarda.
 * Solo se graba lo que viene **después** de la palabra, hasta el silencio o el tope, del mismo
 * flujo que oye Vosk: se guarda en memoria y se manda como WAV de 16 kHz (`assistant/wav.ts`;
 * el `MediaRecorder` de Chromium no graba Ogg) por el canal del asistente (`assistant/bus.ts`)
 * hacia el backend local. Lo de antes de la palabra no se graba. Mientras habla la voz propia de
 * EMMA (`speechSynthesis.speaking`) no se acepta la palabra ni se graba. Sin probar con una
 * persona ni con el ruido de una nave.
 *
 * **Un modelo por idioma (2026-11-15).** Vosk reconoce con el modelo del idioma que se habla: con
 * la interfaz en inglés se carga `vosk-model-small-en-us-0.15` (`MODEL_PATH_EN`) y la gramática
 * inglesa (`wakeGrammar` en `machine.ts`). Ese modelo **todavía no viaja en el paquete** (no se
 * descarga nada al ejecutar: lo trae quien empaqueta, con su origen y su huella anotados junto al
 * castellano) y con él **está sin verificar que se reconozca «EMMA»**. Mientras falte, el modo en
 * inglés se declara no disponible («sin modelo») en vez de fallar: antes de cargar Vosk se
 * pide al propio origen el comienzo del fichero y se mira que sea un gzip (`modelPresent`), porque
 * un servidor que contesta cualquier ruta con la página de la aplicación daría a Vosk un HTML por
 * modelo. En castellano no se pregunta nada: el camino es el de siempre.
 */

import { blockForeignFetch } from "../../lib/faceCamera";
import { type Language, language } from "../../lib/i18n";
import { WAV_RATE, downsample, encodeWav } from "../wav";
import {
  OFF,
  SILENCE,
  type SilenceTracker,
  type WakeEvent,
  type WakeState,
  type WakeUnavailable,
  readVoskResult,
  rms,
  sameState,
  silenceTracker,
  step,
  wakeGrammar,
} from "./machine";
import { WORKER_PATH } from "./voskWorker";

/** El modelo, servido desde el propio paquete (`public/vosk/`). */
export const MODEL_PATH = "vosk/vosk-model-small-es-0.42.tar.gz";
/** El del inglés: aún no está en `public/vosk/` (ver el comentario del módulo). */
export const MODEL_PATH_EN = "vosk/vosk-model-small-en-us-0.15.tar.gz";

/** El modelo del idioma de la interfaz. */
export function modelPath(lang: Language = language()): string {
  return lang === "en" ? MODEL_PATH_EN : MODEL_PATH;
}

export const MODEL_URL = `${import.meta.env.BASE_URL}${modelPath()}`;
const WORKER_URL = `${import.meta.env.BASE_URL}${WORKER_PATH}`;

/** Muestras por trozo: ~85 ms a 48 kHz. */
const CHUNK = 4096;

type VoskModel = import("vosk-browser").Model;
type VoskRecognizer = import("vosk-browser").KaldiRecognizer;

function reasonOf(error: unknown): WakeUnavailable {
  const name = error instanceof DOMException || error instanceof Error ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return "sin permiso";
  return "sin micrófono";
}

/**
 * Crea el modelo de Vosk arrancando su trabajador desde `WORKER_URL` en vez de su `blob:`. El
 * constructor de `Model` crea el trabajador al momento, así que el cambio de `Worker` dura solo
 * esa llamada.
 */
/** Lo que se espera a que cargue el modelo (descomprimir ~60 MB la primera vez) antes de rendirse. */
const LOAD_TIMEOUT_MS = 120_000;

function createModel(Model: typeof import("vosk-browser").Model): Promise<VoskModel> {
  const Original = window.Worker;
  let workerFailed: (() => void) | null = null;
  class SameOriginWorker extends Original {
    constructor(url: string | URL, options?: WorkerOptions) {
      if (String(url).startsWith("blob:")) URL.revokeObjectURL(String(url));
      super(WORKER_URL, options);
      // Un trabajador que no llega a arrancar (404, un error al cargarlo) no manda ningún mensaje
      // de Vosk: sin esto la consola diría «Preparando la escucha» para siempre.
      this.addEventListener("error", () => workerFailed?.());
    }
  }
  let model: VoskModel;
  window.Worker = SameOriginWorker;
  try {
    // Dirección absoluta: el trabajador resuelve la del modelo contra la suya.
    model = new Model(new URL(MODEL_URL, window.location.href).href, -1);
  } finally {
    window.Worker = Original;
  }
  return new Promise((resolve, reject) => {
    let settled = false;
    const fail = () => {
      // Un error de Vosk con el modelo ya cargado no es de la carga: lo ignora aquí.
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try {
        model.terminate();
      } catch {
        // Ya parado.
      }
      reject(new Error("modelo no cargado"));
    };
    const timer = setTimeout(fail, LOAD_TIMEOUT_MS);
    workerFailed = fail;
    model.on("load", (message) => {
      if (settled) return;
      if (message.event === "load" && message.result) {
        settled = true;
        clearTimeout(timer);
        resolve(model);
      } else fail();
    });
    model.on("error", fail);
  });
}

/**
 * Si lo que el propio origen contesta por la ruta del modelo empieza como un gzip (1f 8b), que es
 * lo que abre el trabajador de Vosk. El servidor de desarrollo y el de la aplicación contestan una
 * ruta que no existe con la página de la consola, con un 200: el tipo que declaren no dice nada.
 */
export function startsLikeGzip(bytes: Uint8Array): boolean {
  return bytes.length >= 2 && bytes[0] === 0x1f && bytes[1] === 0x8b;
}

/**
 * Pide el modelo al propio origen y mira solo su comienzo: en cuanto hay dos bytes, se corta la
 * descarga. Solo se usa fuera del castellano.
 */
async function modelPresent(): Promise<boolean> {
  try {
    const response = await fetch(new URL(MODEL_URL, window.location.href).href);
    if (!response.ok || response.body === null) return false;
    const reader = response.body.getReader();
    let head = new Uint8Array(0);
    while (head.length < 2) {
      const { value, done } = await reader.read();
      if (done || value === undefined) break;
      head = Uint8Array.from([...head, ...value.subarray(0, 2)]);
    }
    void reader.cancel().catch(() => undefined);
    return startsLikeGzip(head);
  } catch {
    return false;
  }
}

function isSpeaking(): boolean {
  try {
    return typeof window !== "undefined" && window.speechSynthesis?.speaking === true;
  } catch {
    return false;
  }
}

/** Cuánto se espera al resultado final de Vosk antes de mandar la frase (por si era «deja de escuchar»). */
const SETTLE_MS = 600;

/** Junta los trozos grabados en una sola señal. */
function joined(parts: readonly Float32Array[]): Float32Array {
  const out = new Float32Array(parts.reduce((sum, part) => sum + part.length, 0));
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

/**
 * Enciende la escucha. `state` avisa de cada cambio de estado; `utterance`, de cada frase
 * grabada tras la palabra (WAV de 16 kHz). Devuelve con qué pararlo todo: el micrófono se cierra
 * en el acto.
 */
export function watchWakeWord(handlers: {
  state: (state: WakeState) => void;
  utterance: (audio: Blob) => void;
}): () => void {
  let state: WakeState = OFF;
  let stopped = false;
  let model: VoskModel | null = null;
  let recognizer: VoskRecognizer | null = null;
  let stream: MediaStream | null = null;
  let context: AudioContext | null = null;
  let processor: ScriptProcessorNode | null = null;
  let recording: Float32Array[] = [];
  let tracker: SilenceTracker | null = null;
  let speakingTimer: ReturnType<typeof setInterval> | null = null;
  let wasSpeaking = false;

  function dispatch(event: WakeEvent): void {
    if (stopped) return;
    const previous = state;
    const next = step(state, event);
    if (sameState(next, previous)) return;
    state = next;
    effects(previous, state);
    handlers.state(state);
  }

  function effects(previous: WakeState, next: WakeState): void {
    if (next.kind === "recording" && previous.kind !== "recording") {
      recording = [];
      tracker = silenceTracker(SILENCE);
    }
    if (previous.kind === "recording" && next.kind === "sending") {
      // A 16 kHz, lo que usa Whisper (`wav.ts` no remuestrea: se baja aquí).
      const rate = context?.sampleRate ?? 48_000;
      const audio = encodeWav(downsample(joined(recording), rate, WAV_RATE), Math.min(rate, WAV_RATE));
      recording = [];
      tracker = null;
      // Fuerza el resultado final de Vosk: si la frase era «EMMA, deja de escuchar», apaga antes.
      recognizer?.retrieveFinalResult();
      void send(audio);
    }
    // Grabación tirada (frase vacía, voz propia, apagar). Pasar a «asentada» sigue grabando.
    if (previous.kind === "recording" && next.kind !== "sending" && next.kind !== "recording") {
      recording = [];
      tracker = null;
    }
    if (next.kind === "off" || next.kind === "unavailable") release();
  }

  async function send(audio: Blob): Promise<void> {
    const started = Date.now();
    while (!stopped && state.kind === "sending" && !state.settled && Date.now() - started < SETTLE_MS) {
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    if (stopped || state.kind !== "sending") return;
    handlers.utterance(audio);
    dispatch({ type: "sent" });
  }

  function release(): void {
    if (speakingTimer !== null) clearInterval(speakingTimer);
    speakingTimer = null;
    recording = [];
    if (processor !== null) {
      processor.onaudioprocess = null;
      processor.disconnect();
    }
    processor = null;
    for (const track of stream?.getTracks() ?? []) track.stop();
    stream = null;
    void context?.close().catch(() => undefined);
    context = null;
    try {
      recognizer?.remove();
    } catch {
      // Un reconocedor que no llegó a crearse no es un fallo de la consola.
    }
    recognizer = null;
    try {
      model?.terminate();
    } catch {
      // Como arriba.
    }
    model = null;
  }

  async function start(): Promise<void> {
    dispatch({ type: "enable" });
    if (typeof navigator === "undefined" || navigator.mediaDevices?.getUserMedia === undefined) {
      return dispatch({ type: "unavailable", reason: "sin micrófono" });
    }
    if (typeof AudioContext === "undefined" || typeof Worker === "undefined") {
      return dispatch({ type: "unavailable", reason: "sin audio del navegador" });
    }
    blockForeignFetch(window);
    // El modelo castellano viaja siempre; el de otro idioma puede faltar, y entonces no se carga nada.
    if (language() !== "es" && !(await modelPresent())) {
      return dispatch({ type: "unavailable", reason: "sin modelo" });
    }
    try {
      const { Model } = await import("vosk-browser");
      if (stopped) return;
      model = await createModel(Model);
    } catch {
      return dispatch({ type: "unavailable", reason: "sin modelo" });
    }
    if (stopped) return release();

    // El micrófono, al final: se abre solo cuando ya se puede usar.
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        video: false,
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      if (stopped) {
        for (const track of media.getTracks()) track.stop();
        return release();
      }
      stream = media;
    } catch (error) {
      return dispatch({ type: "unavailable", reason: reasonOf(error) });
    }

    try {
      const audio = new AudioContext();
      context = audio;
      const active = new model.KaldiRecognizer(audio.sampleRate, JSON.stringify(wakeGrammar()));
      recognizer = active;
      const heard = (message: unknown) => {
        const result = readVoskResult(message);
        if (result !== null) dispatch({ type: "heard", ...result, speaking: isSpeaking() });
      };
      active.on("partialresult", heard);
      active.on("result", heard);
      const source = audio.createMediaStreamSource(stream);
      const node = audio.createScriptProcessor(CHUNK, 1, 1);
      processor = node;
      node.onaudioprocess = (event) => {
        if (stopped) return;
        const samples = new Float32Array(event.inputBuffer.getChannelData(0));
        // Vosk se queda con su copia (se transfiere al trabajador).
        active.acceptWaveformFloat(samples.slice(), audio.sampleRate);
        if (state.kind === "recording" && tracker !== null) {
          recording.push(samples);
          const outcome = tracker.push(rms(samples), (samples.length * 1000) / audio.sampleRate);
          if (outcome !== null) dispatch({ type: "phrase", outcome });
        }
      };
      source.connect(node);
      // Sin destino, Chromium no llama a `onaudioprocess`; la salida va en silencio.
      node.connect(audio.destination);
      await audio.resume();
    } catch {
      return dispatch({ type: "unavailable", reason: "sin audio del navegador" });
    }
    if (stopped) return release();
    // La voz propia: al empezar a hablar, una grabación abierta se tira (`machine.ts`).
    speakingTimer = setInterval(() => {
      const speaking = isSpeaking();
      if (speaking && !wasSpeaking) dispatch({ type: "speaking" });
      wasSpeaking = speaking;
    }, 100);
    dispatch({ type: "ready" });
  }

  void start();
  return () => {
    if (stopped) return;
    dispatch({ type: "disable" });
    stopped = true;
    release();
  };
}
