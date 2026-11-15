import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { MODEL_URL, blockForeignFetch } from "./faceCamera";

/**
 * Lo que la vista que sigue la cara (§5.40, demostración) promete sin navegador: que el modelo
 * que viaja es el anotado, que todo se carga del propio paquete y que nada sale a la red.
 */

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const read = (...parts: string[]) => readFileSync(join(FRONTEND, ...parts));

describe("el modelo", () => {
  it("es el descargado y anotado en ORIGEN.txt: misma huella SHA-256 y mismo tamaño", () => {
    const model = read("public", "mediapipe", "face_landmarker.task");
    const origin = read("public", "mediapipe", "ORIGEN.txt").toString("utf8");
    const hash = createHash("sha256").update(model).digest("hex");
    expect(origin).toContain(`SHA-256: ${hash}`);
    const size = String(model.length).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    expect(origin).toContain(`Tamaño: ${size} bytes`);
    expect(origin).toContain("Apache License, Version 2.0");
  });

  it("el texto de la licencia viaja al lado (Apache-2.0 §4(a))", () => {
    const license = read("public", "mediapipe", "LICENSE-Apache-2.0.txt").toString("utf8");
    expect(license).toContain("Apache License");
    expect(license).toContain("Version 2.0, January 2004");
    expect(license).toContain("4. Redistribution.");
  });

  it("se carga del propio paquete, no de una dirección de fuera", () => {
    expect(MODEL_URL).toBe("/mediapipe/face_landmarker.task");
  });

  it("NOTICE nombra el modelo y la biblioteca, con su licencia", () => {
    const notice = read("..", "NOTICE").toString("utf8");
    expect(notice).toContain("@mediapipe/tasks-vision");
    expect(notice).toContain("face_landmarker.task");
    expect(notice).toContain("Apache License, Version 2.0");
  });
});

describe("sin red", () => {
  it("el código de la cámara no escribe ninguna dirección de fuera fuera de los comentarios", () => {
    const source = read("src", "lib", "faceCamera.ts").toString("utf8");
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
    expect(code).not.toMatch(/https?:\/\//);
  });

  it("la CSP del paquete deja compilar WebAssembly y sigue sin dejar conectar fuera", () => {
    const config = read("vite.config.ts").toString("utf8");
    expect(config).toContain("script-src 'self' 'wasm-unsafe-eval';");
    expect(config).toContain("connect-src 'self' blob: data:;");
    expect(config).not.toMatch(/script-src[^;]*'unsafe-eval'/);
  });

  it("un fetch a otro origen falla sin salir; el mismo origen, blob: y data: pasan", async () => {
    const calls: string[] = [];
    const target = {
      location: { origin: "http://127.0.0.1:8000", href: "http://127.0.0.1:8000/" },
      fetch: ((input: RequestInfo | URL) => {
        calls.push(String(input));
        return Promise.resolve(new Response("ok"));
      }) as typeof fetch,
    };
    blockForeignFetch(target);
    await expect(target.fetch("https://odml.pa.googleapis.com/v1/log", { method: "POST" })).rejects.toThrow(
      /EMMA no sale a la red/,
    );
    await expect(target.fetch(new URL("http://example.org/x"))).rejects.toThrow(TypeError);
    await target.fetch("/mediapipe/face_landmarker.task");
    await target.fetch("http://127.0.0.1:8000/api/status");
    await target.fetch("blob:http://127.0.0.1:8000/1234");
    await target.fetch("data:text/plain,hola");
    expect(calls).toEqual([
      "/mediapipe/face_landmarker.task",
      "http://127.0.0.1:8000/api/status",
      "blob:http://127.0.0.1:8000/1234",
      "data:text/plain,hola",
    ]);
  });
});
