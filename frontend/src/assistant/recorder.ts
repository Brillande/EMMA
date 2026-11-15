/**
 * La grabación de verdad: `getUserMedia` y un `AudioWorklet` que toma las muestras PCM, que al
 * terminar se bajan a 16 kHz y se envuelven en WAV (`wav.ts`). Lo que se decide sin navegador
 * (cuándo abrir y cerrar) está en `pushToTalk.ts`.
 *
 * Por qué no `MediaRecorder`: en Chromium y Electron no graba Ogg/Opus, y el backend no acepta
 * WebM (medido en el recorrido con Playwright, `compliance/hmi-state-of-the-art.md` §5.43).
 *
 * El micrófono se abre al empezar cada turno y se suelta al terminarlo (se paran sus pistas y se
 * cierra el contexto de audio): no queda abierto entre turnos. Lo grabado vive en memoria hasta
 * mandarse al backend en loopback y no se guarda en el navegador.
 */

import { WAV_RATE, downsample, encodeWav } from "./wav";

/** El módulo del worklet, servido por la propia consola (Vite lo copia al paquete). */
const WORKLET_URL = new URL("./pcmRecorder.js", import.meta.url);
const PROCESSOR = "emma-pcm-recorder";

/** Si este navegador puede grabar para el asistente. */
export function browserCanRecord(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof AudioContext !== "undefined" &&
    typeof AudioWorkletNode !== "undefined" &&
    typeof navigator !== "undefined" &&
    navigator.mediaDevices?.getUserMedia !== undefined
  );
}

export interface Recording {
  /** Termina y da lo grabado, en WAV de 16 kHz mono. */
  stop: () => Promise<Blob>;
  /** Termina y lo tira. */
  cancel: () => void;
}

/** Une los trozos que manda el worklet. */
export function joinChunks(chunks: readonly Float32Array[]): Float32Array {
  const out = new Float32Array(chunks.reduce((total, chunk) => total + chunk.length, 0));
  let at = 0;
  for (const chunk of chunks) {
    out.set(chunk, at);
    at += chunk.length;
  }
  return out;
}

export async function startRecording(): Promise<Recording> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    video: false,
  });
  const context = new AudioContext();
  const release = () => {
    stream.getTracks().forEach((track) => track.stop());
    void context.close();
  };
  let node: AudioWorkletNode;
  try {
    await context.audioWorklet.addModule(WORKLET_URL);
    node = new AudioWorkletNode(context, PROCESSOR, { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1 });
  } catch (error) {
    release();
    throw error;
  }
  const chunks: Float32Array[] = [];
  node.port.onmessage = (event: MessageEvent<Float32Array>) => chunks.push(event.data);
  const source = context.createMediaStreamSource(stream);
  source.connect(node);
  // El nodo escribe silencio; conectado a la salida para que el contexto lo procese.
  node.connect(context.destination);
  const rate = context.sampleRate;
  const end = () => {
    node.port.onmessage = null;
    source.disconnect();
    node.disconnect();
    release();
  };
  return {
    stop: async () => {
      end();
      return encodeWav(downsample(joinChunks(chunks), rate, WAV_RATE), WAV_RATE);
    },
    cancel: end,
  };
}
