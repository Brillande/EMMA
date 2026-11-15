// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * El resumen de Tierra como servicio local, para el instalador de escritorio.
 *
 * Por qué existe: en el instalador `EMMA.exe` tiene apagado a propósito el fusible `runAsNode`
 * (no puede usarse como intérprete de Node cualquiera), así que el backend no puede lanzar el
 * resumen como un proceso de Node. Decisión del usuario (2026-11-12): sin tocar el fusible, con un
 * `utilityProcess` de Electron. Este servicio corre en uno, escucha solo en loopback y calcula cada
 * resumen en un hilo nuevo (`summary-worker.mjs`), para que ningún corte herede el estado del
 * anterior. Lo llama `backend/app/planner_ground.py` con `EMMA_PLANNER_SUMMARY_URL`.
 *
 * Solo `POST /summary` con la entrada de `ground-summary.mjs`; nada más. Tope de cuerpo y de tiempo.
 */
import http from "node:http";
import { Worker } from "node:worker_threads";

const HOST = "127.0.0.1";
const PORT = Number(process.env.EMMA_PLANNER_SUMMARY_PORT ?? 0);
const MAX_BODY = 64 * 1024 * 1024;
const TIMEOUT_MS = 120_000;

function summarize(input) {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL("./summary-worker.mjs", import.meta.url), { workerData: input });
    const timer = setTimeout(() => {
      void worker.terminate();
      reject(new Error("el resumen tardó demasiado"));
    }, TIMEOUT_MS);
    worker.once("message", (msg) => {
      clearTimeout(timer);
      void worker.terminate();
      if (msg.ok) resolve(msg.result);
      else reject(new Error(msg.error));
    });
    worker.once("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
  });
}

const server = http.createServer((req, res) => {
  const reply = (status, body) => {
    res.writeHead(status, { "content-type": "application/json" });
    res.end(JSON.stringify(body));
  };
  if (req.method !== "POST" || req.url !== "/summary") return reply(404, { error: "solo POST /summary" });
  const chunks = [];
  let size = 0;
  req.on("data", (chunk) => {
    size += chunk.length;
    if (size > MAX_BODY) {
      reply(413, { error: "entrada demasiado grande" });
      req.destroy();
    } else chunks.push(chunk);
  });
  req.on("end", () => {
    if (res.writableEnded) return;
    let input;
    try {
      input = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    } catch {
      return reply(400, { error: "la entrada no es JSON" });
    }
    summarize(input).then(
      (result) => reply(200, result),
      (err) => reply(500, { error: String(err?.message ?? err) }),
    );
  });
});

server.listen(PORT, HOST, () => {
  const { port } = server.address();
  // El proceso principal de Electron lee el puerto de aquí (`desktop/main.cjs`).
  process.parentPort?.postMessage({ summaryPort: port });
  if (!process.parentPort) console.log(`resumen de Tierra en http://${HOST}:${port}/summary`);
});
