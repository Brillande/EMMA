import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

import { VOSK_JS_SHA256, WORKER_CSP, WORKER_PATH, voskWorkerFile } from "./src/assistant/wake/voskWorker";

// Sin recursos externos: en vuelo no hay red, y todo sale del propio paquete. Solo
// en el build: en desarrollo, Vite inyecta scripts en linea para la recarga en
// caliente y una CSP estricta la romperia.
// 'wasm-unsafe-eval' lo pide el detector de caras de MediaPipe (vista que sigue la cara, demo,
// src/lib/faceCamera.ts): compilar WebAssembly cuenta como eval para la CSP. Deja compilar solo
// WebAssembly, no `eval` ni `new Function` de JavaScript, y el .wasm sale del propio paquete
// ('self'). connect-src sigue en 'self': el registro de uso que MediaPipe manda a Google no sale.
const CSP =
  "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self' blob: data:; img-src 'self' data: blob:; " +
  // worker-src y blob:/data: los pide NiiVue (visor 3D de Polaris): carga los volumenes en
  // trabajadores y desde memoria. Es la CSP del propio visor de Polaris, sin nada mas.
  "worker-src 'self' blob:; " +
  "style-src 'self' 'unsafe-inline'; font-src 'self'; object-src 'none'; base-uri 'none'";

function contentSecurityPolicy(): Plugin {
  return {
    name: "emma-csp",
    apply: "build",
    transformIndexHtml: () => [
      {
        tag: "meta",
        attrs: { "http-equiv": "Content-Security-Policy", content: CSP },
        injectTo: "head-prepend",
      },
    ],
  };
}

// El trabajador de Vosk (escuchar la palabra «EMMA», src/assistant/wake/) como fichero del propio
// origen, en desarrollo y en el paquete. La CSP de arriba no cambia: el trabajador de Vosk necesita
// `new Function` (el enlace de Emscripten) y un trabajador `blob:` heredaria la CSP de la pagina,
// que no lo deja; dar 'unsafe-eval' a toda la pagina por el seria peor. Servido desde una direccion,
// lleva su propia guarda contra la red delante del codigo, que es el del paquete sin cambios
// (src/assistant/wake/voskWorker.ts lo explica entero). Antes de servirlo se comprueba que vosk.js
// es el que se leyo: otra version se revisa antes de usarse.
function voskWorker(): Plugin {
  let cached: string | null = null;
  const source = (): string => {
    if (cached !== null) return cached;
    const path = fileURLToPath(new URL("./node_modules/vosk-browser/dist/vosk.js", import.meta.url));
    const raw = readFileSync(path);
    const hash = createHash("sha256").update(raw).digest("hex");
    if (hash !== VOSK_JS_SHA256) throw new Error(`vosk-browser: dist/vosk.js no es el revisado (${hash})`);
    cached = voskWorkerFile(raw.toString("utf8"));
    return cached;
  };
  return {
    name: "emma-vosk-worker",
    configureServer(server) {
      server.middlewares.use(`/${WORKER_PATH}`, (_req, res) => {
        res.setHeader("Content-Type", "text/javascript; charset=utf-8");
        // En desarrollo, además, su propia CSP: deja `new Function` y WebAssembly y no conecta fuera.
        res.setHeader("Content-Security-Policy", WORKER_CSP);
        res.end(source());
      });
    },
    generateBundle() {
      this.emitFile({ type: "asset", fileName: WORKER_PATH, source: source() });
    },
  };
}

// En desarrollo, /api va al backend por el proxy: mismo origen, sin tocar el CORS
// del backend. En la aplicacion de escritorio, FastAPI sirve este mismo `dist/`.
export default defineConfig({
  plugins: [react(), contentSecurityPolicy(), voskWorker()],
  build: {
    // El worklet del micrófono del asistente (src/assistant/pcmRecorder.js) sale como fichero
    // propio, nunca en linea: Vite mete en un `data:` los ficheros pequeños, y la CSP
    // (`script-src 'self'`) no deja cargar un modulo de worklet desde `data:`.
    assetsInlineLimit: (file) => (file.endsWith("pcmRecorder.js") ? false : undefined),
  },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    include: ["src/**/*.test.ts"],
    // La suite corre en castellano; el inglés, en los `*.en.test.ts` (`src/lib/i18n.ts`).
    setupFiles: ["src/test/spanish.ts"],
  },
});
