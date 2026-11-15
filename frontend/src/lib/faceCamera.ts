/**
 * La cámara frontal y el detector de caras de MediaPipe (Face Landmarker), para girar la vista
 * siguiendo la cara (`faceOrientation.ts`). **Demostración, sin validar con una tableta real.**
 *
 * Por qué es un módulo aparte, cargado solo al encender el modo (`import()` dinámico desde
 * `DisplayControls.tsx`): el detector son ~150 kB de JavaScript, ~15 MB de WebAssembly y ~3,7 MB de
 * modelo, y quien no usa el modo no debe pagarlos.
 *
 * Todo viaja en el paquete; en ejecución no se descarga nada. El WebAssembly y su cargador salen de
 * `node_modules/@mediapipe/tasks-vision` (los importa Vite con `?url` y los deja en `dist/`) y el
 * modelo está en `public/mediapipe/`, con su origen, fecha y huella en `ORIGEN.txt` al lado.
 *
 * **Privacidad.** La cámara se enciende solo con el modo y se apaga al pararlo. El vídeo va a un
 * `<video>` que no entra en el documento: ningún fotograma se dibuja, se guarda ni se manda, y del
 * detector solo se usa el ángulo de la recta entre los ojos. Se pide vídeo sin audio.
 *
 * **Sin red.** La biblioteca de MediaPipe lleva dentro un registro de uso que manda estadísticas por
 * `fetch` a un servidor de Google (`odml.pa.googleapis.com`) cada minuto y al cerrarse, sin opción
 * para apagarlo. En la aplicación compilada ya lo para la CSP (`connect-src 'self'`); en desarrollo
 * no hay CSP, así que antes de cargar la biblioteca `blockForeignFetch` hace que todo `fetch` a
 * otro origen falle sin salir del equipo. La biblioteca lo toma como un fallo del registro y deja
 * de intentarlo. Solo cubre `fetch`, que es lo que usa ese registro (leído en `vision_bundle.mjs`
 * 1.2.2); `XMLHttpRequest` y `sendBeacon` los sigue parando solo la CSP. Se queda instalado para
 * toda la sesión: un `fetch` a otro origen que la interfaz añadiera después fallaría, y la CSP del
 * paquete ya lo haría fallar igual.
 */

import wasmBinaryUrl from "@mediapipe/tasks-vision/vision_wasm_internal.wasm?url";
import wasmLoaderUrl from "@mediapipe/tasks-vision/vision_wasm_internal.js?url";

import { DETECTION_INTERVAL_MS, type FaceReading, readFaces } from "./faceOrientation";

/** El modelo, servido desde el propio paquete (`public/mediapipe/`). */
export const MODEL_URL = `${import.meta.env.BASE_URL}mediapipe/face_landmarker.task`;

/** Por qué no hay cámara, dicho para la interfaz. */
export type FaceUnavailable = "sin cámara" | "sin permiso" | "sin modelo";

let fetchGuarded = false;

/**
 * Hace que `fetch` a otro origen (http o https) falle sin salir del equipo; el mismo origen, `blob:`
 * y `data:` siguen igual. Es lo que la CSP del paquete ya impone (`connect-src 'self' blob:
 * data:`), puesto también donde no hay CSP. Se instala una vez y se queda.
 */
export function blockForeignFetch(target: { fetch: typeof fetch; location: { origin: string; href: string } }): void {
  if (fetchGuarded) return;
  fetchGuarded = true;
  const original = target.fetch.bind(target);
  target.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    let url: URL | null = null;
    try {
      url = new URL(raw, target.location.href);
    } catch {
      url = null;
    }
    if (url !== null && (url.protocol === "http:" || url.protocol === "https:") && url.origin !== target.location.origin) {
      return Promise.reject(new TypeError(`EMMA no sale a la red: ${url.origin}`));
    }
    return original(input, init);
  };
}

function reasonOf(error: unknown): FaceUnavailable {
  const name = error instanceof DOMException || error instanceof Error ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return "sin permiso";
  return "sin cámara";
}

/**
 * Carga el detector, enciende la cámara y busca la cara cuatro veces por segundo. Devuelve con qué
 * pararlo todo (la cámara se apaga en el acto). `started` avisa cuando la cámara ya está encendida;
 * `unavailable`, una vez, si no hay cámara, permiso o modelo. Sin probar con una tableta real.
 */
export function watchFace(handlers: {
  started: () => void;
  reading: (reading: FaceReading) => void;
  unavailable: (why: FaceUnavailable) => void;
}): () => void {
  let stopped = false;
  let declared = false;
  let stream: MediaStream | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;
  let landmarker: { close(): void } | null = null;
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;

  const unavailable = (why: FaceUnavailable) => {
    if (stopped || declared) return;
    declared = true;
    stop();
    handlers.unavailable(why);
  };

  function stop(): void {
    if (timer !== null) clearInterval(timer);
    timer = null;
    for (const track of stream?.getTracks() ?? []) track.stop();
    stream = null;
    video.srcObject = null;
    try {
      landmarker?.close();
    } catch {
      // Cerrar un detector que no llegó a arrancar no es un fallo de la consola.
    }
    landmarker = null;
  }

  async function start(): Promise<void> {
    if (typeof navigator === "undefined" || navigator.mediaDevices?.getUserMedia === undefined) {
      return unavailable("sin cámara");
    }
    blockForeignFetch(window);
    let detector: import("@mediapipe/tasks-vision").FaceLandmarker;
    try {
      const { FaceLandmarker } = await import("@mediapipe/tasks-vision");
      detector = await FaceLandmarker.createFromOptions(
        { wasmLoaderPath: wasmLoaderUrl, wasmBinaryPath: wasmBinaryUrl },
        {
          baseOptions: { modelAssetPath: MODEL_URL, delegate: "CPU" },
          runningMode: "VIDEO",
          // Dos, para saber que hay más de una cara y no girar para nadie.
          numFaces: 2,
          outputFaceBlendshapes: false,
          outputFacialTransformationMatrixes: false,
        },
      );
    } catch {
      return unavailable("sin modelo");
    }
    if (stopped) {
      detector.close();
      return;
    }
    landmarker = detector;

    // La cámara, al final: se enciende solo cuando ya se puede usar.
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: "user", width: { ideal: 320 }, height: { ideal: 240 }, frameRate: { ideal: 10 } },
      });
      if (stopped) {
        for (const track of media.getTracks()) track.stop();
        return;
      }
      stream = media;
      // Con la pista viva la cámara ya está encendida: el aviso sale ya, antes de reproducir nada.
      handlers.started();
      video.srcObject = media;
      await video.play();
    } catch (error) {
      return unavailable(reasonOf(error));
    }
    if (stopped) return;

    timer = setInterval(() => {
      if (stopped || video.readyState < 2 || video.videoWidth === 0) return;
      let faces: readonly (readonly { x: number; y: number }[])[];
      try {
        faces = detector.detectForVideo(video, performance.now()).faceLandmarks;
      } catch {
        return;
      }
      handlers.reading(readFaces(faces, video.videoWidth, video.videoHeight));
    }, DETECTION_INTERVAL_MS);
  }

  void start();
  return () => {
    stopped = true;
    stop();
  };
}
