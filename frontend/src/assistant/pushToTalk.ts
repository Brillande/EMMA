/**
 * Pulsar y mantener para hablar con el asistente: la máquina de estados y la tecla, sin navegador (la grabación de verdad va en `recorder.ts`).
 *
 * Por qué pulsar y mantener: el micrófono solo está abierto mientras la persona lo pide con el
 * dedo (el botón «Hablar con EMMA» o Ctrl+Espacio), así que no hay escucha que olvidar encendida;
 * mientras lo está, la consola lo dice («Micrófono abierto», azul de aviso). El gesto de emergencia
 * (otra rama) y la palabra «EMMA» (`assistant/wake/`) llegan por el bus: el primero abre un turno
 * con tope de tiempo (`listen`), la segunda manda su trozo ya grabado.
 *
 * Se graba PCM con un `AudioWorklet` y se manda en WAV de 16 kHz mono (`recorder.ts`, `wav.ts`):
 * `MediaRecorder` no graba Ogg/Opus en Chromium ni en Electron. Sin `AudioWorklet` o sin
 * micrófono en el navegador, la voz se declara no disponible y queda el campo de texto.
 */

/** Tope de un turno mantenido: un micrófono olvidado pulsado no graba sin fin. */
export const HOLD_LIMIT_MS = 30_000;
/** Tope de un turno abierto sin mantener (gesto de emergencia, `listen`). */
export const LISTEN_LIMIT_MS = 8_000;

export type TalkMode = "hold" | "listen";

export type TalkState =
  | { phase: "idle" }
  /** Pedido un turno sin mantener mientras EMMA habla: espera a que calle para no grabarse. */
  | { phase: "waiting"; mode: "listen" }
  /** Pidiendo el micrófono; `released` si se soltó antes de tenerlo. */
  | { phase: "opening"; mode: TalkMode; released: boolean }
  | { phase: "recording"; mode: TalkMode }
  | { phase: "sending" };

export type TalkEvent =
  | { type: "press" }
  /** Abrir un turno sin mantener; `speaking` si la voz propia está hablando ahora. */
  | { type: "listen"; speaking: boolean }
  /** La voz propia ha callado. */
  | { type: "quiet" }
  | { type: "release" }
  /** El micrófono se abrió y graba. */
  | { type: "opened" }
  /** No hubo micrófono (permiso denegado, ninguno conectado). */
  | { type: "denied" }
  /** Terminó la grabación y su envío, bien o mal. */
  | { type: "done" };

export const IDLE: TalkState = { phase: "idle" };

/**
 * El paso de la máquina. Pulsar con algo en curso no hace nada (no se apilan grabaciones); soltar
 * mientras se abre deja la apertura marcada para cerrarla y descartarla en cuanto llegue; soltar
 * grabando pasa a enviar. En modo `listen`, soltar la tecla no corta: corta el tope de tiempo o
 * volver a pulsar.
 *
 * El micrófono no se abre mientras EMMA habla, o grabaría su propia voz: el gesto de emergencia
 * emite `listen` justo cuando empieza a leer. Un `listen` con la voz hablando espera (`waiting`)
 * hasta `quiet`. Pulsar sí abre al momento: quien pulsa corta la voz (lo hace `Assistant.tsx`
 * antes de mandar `press`), también si había un turno esperando.
 */
export function talkStep(state: TalkState, event: TalkEvent): TalkState {
  switch (event.type) {
    case "press":
      if (state.phase === "idle" || state.phase === "waiting") return { phase: "opening", mode: "hold", released: false };
      if (state.phase === "recording" && state.mode === "listen") return { phase: "sending" };
      return state;
    case "listen":
      if (state.phase !== "idle") return state;
      return event.speaking ? { phase: "waiting", mode: "listen" } : { phase: "opening", mode: "listen", released: false };
    case "quiet":
      return state.phase === "waiting" ? { phase: "opening", mode: "listen", released: false } : state;
    case "release":
      if (state.phase === "opening" && state.mode === "hold") return { ...state, released: true };
      if (state.phase === "recording" && state.mode === "hold") return { phase: "sending" };
      return state;
    case "opened":
      if (state.phase !== "opening") return state;
      // Soltado antes de tener micrófono: no hay nada que mandar.
      return state.released ? IDLE : { phase: "recording", mode: state.mode };
    case "denied":
      return state.phase === "opening" ? IDLE : state;
    case "done":
      return state.phase === "sending" ? IDLE : state;
  }
}

/** Si el micrófono está (o se está) abriendo: lo que enciende el aviso. */
export function micOpen(state: TalkState): boolean {
  return state.phase === "opening" || state.phase === "recording";
}

/** Lo mínimo de un `KeyboardEvent` que se mira. */
export interface TalkKey {
  readonly code: string;
  readonly key: string;
  readonly ctrlKey: boolean;
  readonly altKey: boolean;
  readonly metaKey: boolean;
  readonly repeat: boolean;
}

export const TALK_SHORTCUT = "Control+Space";

/**
 * Ctrl+Espacio mantenido: al bajar, pulsar (sin la repetición del teclado); al soltar el espacio o
 * el Control, soltar. Alt y Meta fuera: Ctrl+Alt+Espacio es de otros.
 */
export function talkKey(event: TalkKey, kind: "down" | "up"): "press" | "release" | null {
  if (kind === "down") {
    if (event.repeat || event.code !== "Space" || !event.ctrlKey || event.altKey || event.metaKey) return null;
    return "press";
  }
  return event.code === "Space" || event.key === "Control" ? "release" : null;
}
