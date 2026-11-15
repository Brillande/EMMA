import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { blockForeignFetch } from "../../lib/faceCamera";
import { VOSK_JS_SHA256, WORKER_GUARD, WORKER_PATH, extractVoskWorker, voskWorkerFile } from "./voskWorker";

/**
 * Lo que el modo «Escuchar "EMMA"» promete sin navegador: que el modelo y la biblioteca que viajan
 * son los anotados, que todo se carga del propio paquete y que nada sale a la red.
 */

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const read = (...parts: string[]) => readFileSync(join(FRONTEND, ...parts));
const code = (source: string) => source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

describe("el modelo", () => {
  it("es el anotado en ORIGEN.txt: misma huella SHA-256 y mismo tamaño", () => {
    const model = read("public", "vosk", "vosk-model-small-es-0.42.tar.gz");
    const origin = read("public", "vosk", "ORIGEN.txt").toString("utf8");
    expect(origin).toContain(`SHA-256: ${createHash("sha256").update(model).digest("hex")}`);
    const size = String(model.length).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    expect(origin).toContain(`Tamaño: ${size} bytes`);
    expect(origin).toContain("Apache License, Version 2.0");
    // Gzip: lo abre el trabajador de Vosk.
    expect(Array.from(model.subarray(0, 2))).toEqual([0x1f, 0x8b]);
  });

  it("el modelo inglés es el anotado en ORIGEN.txt, y es el que pide la escucha en inglés", () => {
    const model = read("public", "vosk", "vosk-model-small-en-us-0.15.tar.gz");
    const origin = read("public", "vosk", "ORIGEN.txt").toString("utf8");
    expect(origin).toContain(`SHA-256: ${createHash("sha256").update(model).digest("hex")}`);
    const size = String(model.length).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    expect(origin).toContain(`Tamaño: ${size} bytes`);
    expect(Array.from(model.subarray(0, 2))).toEqual([0x1f, 0x8b]);
    // No se afirma lo que no se ha probado: reconocer «EMMA» con este modelo está por comprobar.
    expect(origin).toContain("SIN PROBAR");
    expect(read("src", "assistant", "wake", "listener.ts").toString("utf8")).toContain(
      'MODEL_PATH_EN = "vosk/vosk-model-small-en-us-0.15.tar.gz"',
    );
    expect(read("..", "NOTICE").toString("utf8")).toContain("vosk-model-small-en-us-0.15");
  });

  it("el texto de la licencia viaja al lado (Apache-2.0 §4(a))", () => {
    const license = read("public", "vosk", "LICENSE-Apache-2.0.txt").toString("utf8");
    expect(license).toContain("Version 2.0, January 2004");
    expect(license).toContain("4. Redistribution.");
  });

  it("NOTICE nombra el modelo y la biblioteca, con su licencia", () => {
    const notice = read("..", "NOTICE").toString("utf8");
    expect(notice).toContain("vosk-browser 0.0.8");
    expect(notice).toContain("vosk-model-small-es-0.42");
  });
});

describe("el trabajador de Vosk", () => {
  const voskJs = read("node_modules", "vosk-browser", "dist", "vosk.js");

  it("vosk.js es la versión revisada", () => {
    expect(createHash("sha256").update(voskJs).digest("hex")).toBe(VOSK_JS_SHA256);
  });

  it("se saca del paquete sin cambiarlo y se sirve con la guarda delante", () => {
    const worker = extractVoskWorker(voskJs.toString("utf8"));
    expect(worker).toContain("class RecognizerWorker");
    expect(worker).toContain("downloadAndExtract");
    // El WebAssembly va dentro como data:, no se pide a ningún sitio.
    expect(worker).toContain('wasmBinaryFile="data:application/octet-stream;base64,');
    const file = voskWorkerFile(voskJs.toString("utf8"));
    expect(file.startsWith(WORKER_GUARD)).toBe(true);
    expect(file.slice(WORKER_GUARD.length)).toBe(worker);
    expect(WORKER_PATH).toBe("vosk/vosk-worker.js");
    expect(() => extractVoskWorker("nada")).toThrow(/no se encuentra el trabajador/);
  });

  it("el código del trabajador no tiene más salidas que fetch y XMLHttpRequest, que la guarda cubre", () => {
    const worker = extractVoskWorker(voskJs.toString("utf8"));
    for (const channel of ["WebSocket", "sendBeacon", "importScripts(", "EventSource", "RTCPeerConnection"]) {
      expect(worker).not.toContain(channel);
    }
    expect(WORKER_GUARD).toContain("self.fetch = function");
    expect(WORKER_GUARD).toContain("XMLHttpRequest.prototype.open = function");
  });

  it("la guarda del trabajador deja el propio origen, blob: y data:, y para lo de fuera", async () => {
    const calls: string[] = [];
    const opened: string[] = [];
    class FakeXhr {
      open(_method: string, url: string) {
        opened.push(url);
      }
    }
    const self = {
      location: { origin: "http://127.0.0.1:8000", href: "http://127.0.0.1:8000/vosk/vosk-worker.js" },
      fetch: (input: string) => {
        calls.push(input);
        return Promise.resolve("ok");
      },
    };
    new Function("self", "XMLHttpRequest", "URL", WORKER_GUARD)(self, FakeXhr, URL);
    await expect(self.fetch("https://alphacephei.com/vosk/models/x.zip")).rejects.toThrow(/EMMA no sale a la red/);
    await self.fetch("http://127.0.0.1:8000/vosk/vosk-model-small-es-0.42.tar.gz");
    await self.fetch("data:application/octet-stream;base64,AA==");
    expect(calls).toEqual(["http://127.0.0.1:8000/vosk/vosk-model-small-es-0.42.tar.gz", "data:application/octet-stream;base64,AA=="]);
    const xhr = new FakeXhr();
    expect(() => xhr.open("GET", "http://example.org/")).toThrow(/EMMA no sale a la red/);
    xhr.open("GET", "/vosk/x");
    expect(opened).toEqual(["/vosk/x"]);
  });
});

describe("sin red", () => {
  it("el código del modo no escribe ninguna dirección de fuera fuera de los comentarios", () => {
    for (const name of ["listener.ts", "machine.ts", "useWakeWord.ts"]) {
      expect(code(read("src", "assistant", "wake", name).toString("utf8"))).not.toMatch(/https?:\/\//);
    }
  });

  it("no usa el reconocimiento de voz del navegador, que manda el audio fuera", () => {
    for (const name of ["listener.ts", "machine.ts", "useWakeWord.ts"]) {
      expect(code(read("src", "assistant", "wake", name).toString("utf8"))).not.toMatch(/SpeechRecognition/);
    }
  });

  it("el modelo y el trabajador se piden al propio origen, y antes se para el fetch de fuera", () => {
    const listener = read("src", "assistant", "wake", "listener.ts").toString("utf8");
    expect(listener).toContain('export const MODEL_PATH = "vosk/vosk-model-small-es-0.42.tar.gz";');
    expect(listener).toContain("import.meta.env.BASE_URL");
    expect(code(listener)).toMatch(/blockForeignFetch\(window\);[\s\S]*import\("vosk-browser"\)/);
    expect(typeof blockForeignFetch).toBe("function");
  });

  it("la CSP del paquete sigue sin 'unsafe-eval' y sin conectar fuera", () => {
    const config = read("vite.config.ts").toString("utf8");
    expect(config).toContain("connect-src 'self' blob: data:;");
    expect(config).not.toMatch(/script-src[^;]*'unsafe-eval'/);
    expect(config).toContain("voskWorker()");
  });
});
