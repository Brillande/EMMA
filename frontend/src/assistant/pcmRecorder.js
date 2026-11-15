/**
 * El procesador del `AudioWorklet` que toma las muestras del micrófono para el asistente
 * (`recorder.ts`). Va en un fichero propio porque el worklet se carga como módulo aparte
 * (`audioWorklet.addModule`), servido por la propia consola: la CSP (`script-src 'self'`) no deja
 * cargarlo de otro sitio ni desde un `blob:`. Solo copia el primer canal y lo pasa al hilo
 * principal; no escribe nada a la salida (sale silencio).
 */
class EmmaPcmRecorder extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length > 0) this.port.postMessage(channel.slice(0));
    return true;
  }
}

registerProcessor("emma-pcm-recorder", EmmaPcmRecorder);
