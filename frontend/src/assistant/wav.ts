/**
 * WAV PCM de 16 bits, mono, a partir de las muestras que da el micrófono: lo que manda la consola
 * al reconocimiento de voz local (`POST /api/assistant/audio`).
 *
 * Por qué WAV y no Ogg/Opus: Chromium (y por tanto Electron) no graba Ogg con `MediaRecorder`, y
 * WebM no lo acepta el backend. WAV sin comprimir lo escribe cualquiera en pocas líneas, sin
 * dependencias: las muestras se toman con un `AudioWorklet` (`pcmRecorder.js`), se bajan a 16 kHz,
 * que es lo que usa Whisper, y se envuelven aquí. Un turno de 30 s son unos 960 kB: en loopback no
 * importa.
 */

/** La frecuencia con que se manda: la que usa Whisper. */
export const WAV_RATE = 16_000;

/**
 * Baja la frecuencia de muestreo promediando cada tramo (un filtro de caja: basta para voz y evita
 * el peor solapamiento de quedarse con una muestra de cada N). Subir no se hace: con `to >= from`
 * se devuelve una copia.
 */
export function downsample(samples: Float32Array, from: number, to: number): Float32Array {
  if (!(from > 0) || !(to > 0)) throw new RangeError(`frecuencias no válidas: de ${from} a ${to}`);
  if (to >= from) return samples.slice();
  const ratio = from / to;
  const length = Math.floor(samples.length / ratio);
  const out = new Float32Array(length);
  for (let index = 0; index < length; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.min(samples.length, Math.max(start + 1, Math.floor((index + 1) * ratio)));
    let sum = 0;
    for (let at = start; at < end; at += 1) sum += samples[at] ?? 0;
    out[index] = sum / (end - start);
  }
  return out;
}

function writeText(view: DataView, offset: number, text: string): void {
  for (let index = 0; index < text.length; index += 1) view.setUint8(offset + index, text.charCodeAt(index));
}

/** El fichero WAV (RIFF, PCM de 16 bits con signo, mono, little-endian) de esas muestras. */
export function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const rate = Math.round(sampleRate);
  if (!(rate > 0)) throw new RangeError(`frecuencia no válida: ${sampleRate}`);
  const bytes = samples.length * 2;
  const buffer = new ArrayBuffer(44 + bytes);
  const view = new DataView(buffer);
  writeText(view, 0, "RIFF");
  view.setUint32(4, 36 + bytes, true);
  writeText(view, 8, "WAVE");
  writeText(view, 12, "fmt ");
  view.setUint32(16, 16, true); // tamaño del bloque fmt
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true); // bytes por segundo
  view.setUint16(32, 2, true); // bytes por muestra
  view.setUint16(34, 16, true); // bits por muestra
  writeText(view, 36, "data");
  view.setUint32(40, bytes, true);
  for (let index = 0; index < samples.length; index += 1) {
    const value = Math.max(-1, Math.min(1, samples[index] ?? 0));
    view.setInt16(44 + index * 2, value < 0 ? Math.round(value * 0x8000) : Math.round(value * 0x7fff), true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}
