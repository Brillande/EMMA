/**
 * El trabajador de Vosk como fichero del propio origen, no como `blob:`.
 *
 * Por qué existe: `vosk-browser` 0.0.8 lleva su trabajador (Kaldi y Vosk compilados a
 * WebAssembly con Emscripten) en base64 dentro de `dist/vosk.js`, y lo arranca desde un `blob:`.
 * Un trabajador `blob:` hereda la CSP de la página, y el código de enlace de Emscripten (embind,
 * `craftInvokerFunction` y `createNamedFunction`) crea funciones con `new Function`: con la CSP
 * del paquete (`script-src 'self' 'wasm-unsafe-eval'`, sin `'unsafe-eval'`) no arrancaría. Dar
 * `'unsafe-eval'` a toda la consola por un trabajador sería abrir `eval` a todo el código de la
 * página. En su lugar, el plugin de `vite.config.ts` saca ese mismo código del paquete, sin
 * tocarle una letra, y lo sirve como `vosk/vosk-worker.js`; `listener.ts` hace que `vosk-browser`
 * arranque ese fichero en vez del `blob:`. Un trabajador servido desde una dirección lleva la CSP
 * de su propia respuesta, no la de la página.
 *
 * Sin CSP propia, lo que impide que el trabajador salga a la red es lo que va delante de su
 * código (`WORKER_GUARD`): `fetch` y `XMLHttpRequest` a otro origen fallan sin salir del equipo,
 * como `blockForeignFetch` en la página. El código de Vosk, leído (0.0.8), solo pide el modelo
 * que se le da (del propio origen) y su WebAssembly, que va dentro como `data:`; no usa
 * `WebSocket`, `importScripts` ni `sendBeacon`.
 *
 * Aquí no hay nada del navegador: lo usa `vite.config.ts` en node, y lo prueba vitest.
 */

/** Huella SHA-256 de `node_modules/vosk-browser/dist/vosk.js` 0.0.8, la versión leída. */
export const VOSK_JS_SHA256 = "29504515526e974f4cb053cf08811c4de5fb2a74007c0a5a957db50eaa8d5d0c";

/**
 * La CSP propia del trabajador, para quien sirva el fichero con cabeceras (el servidor de
 * desarrollo de Vite la pone): `new Function` y WebAssembly sí, red solo al propio origen y a
 * `data:`. El paquete servido por FastAPI no la lleva todavía; ahí queda la guarda.
 */
export const WORKER_CSP =
  "default-src 'none'; script-src 'self' 'unsafe-eval' 'wasm-unsafe-eval'; connect-src 'self' data: blob:";

/** Dónde se sirve el trabajador, bajo la base de la aplicación. */
export const WORKER_PATH = "vosk/vosk-worker.js";

/**
 * Lo que va delante del código de Vosk: el trabajador no habla con otro origen. Se escribe en
 * JavaScript de los de antes, sin módulos, porque es un trabajador clásico.
 */
export const WORKER_GUARD = `/* EMMA: este trabajador no sale a la red (frontend/src/assistant/wake/voskWorker.ts). */
(function () {
  "use strict";
  var origin = self.location.origin;
  function foreign(raw) {
    var url;
    try { url = new URL(String(raw), self.location.href); } catch (e) { return false; }
    return (url.protocol === "http:" || url.protocol === "https:") && url.origin !== origin;
  }
  var originalFetch = self.fetch;
  self.fetch = function (input, init) {
    var raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (foreign(raw)) return Promise.reject(new TypeError("EMMA no sale a la red"));
    return originalFetch.call(self, input, init);
  };
  var originalOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    if (foreign(url)) throw new TypeError("EMMA no sale a la red");
    return originalOpen.apply(this, arguments);
  };
})();
`;

/**
 * El código del trabajador tal como `vosk-browser` lo arrancaría: el base64 de
 * `createBase64WorkerFactory`, decodificado, sin su primera línea (lo mismo que hace su
 * `createURL`). Falla si no lo encuentra: otra versión del paquete se revisa antes de usarse.
 */
export function extractVoskWorker(voskJs: string): string {
  const found = /createBase64WorkerFactory\('([A-Za-z0-9+/=]+)'/.exec(voskJs);
  if (found === null || found[1] === undefined) {
    throw new Error("vosk-browser: no se encuentra el trabajador en dist/vosk.js");
  }
  // Como `atob` en `vosk-browser`: un carácter por byte. Al servirlo se escribe en UTF-8, igual que
  // el `Blob` de su `createURL`, así que el fichero sale con los mismos bytes que su `blob:`.
  const source = Buffer.from(found[1], "base64").toString("latin1");
  const start = source.indexOf("\n", 10) + 1;
  return source.substring(start);
}

/** El fichero que se sirve: la guarda y, detrás, el código de Vosk sin cambios. */
export function voskWorkerFile(voskJs: string): string {
  return `${WORKER_GUARD}${extractVoskWorker(voskJs)}`;
}
