// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Cliente SÍNCRONO del ledger de EMMA para la base de Marplanner.
 *
 * Por qué existe: Marplanner usa `better-sqlite3`, cuya API es síncrona, y el usuario decidió
 * (2026-11-12) que su base sea el ledger firmado de EMMA. Una transacción solo vale cuando el
 * ledger la ha anotado; para no responder antes, la petición HTTP se hace en un hilo aparte y este
 * hilo espera con `Atomics.wait` hasta su respuesta. Lento comparado con un fichero, pero en un
 * planificador doméstico las escrituras se cuentan por minutos, no por milisegundos.
 *
 * `EMMA_PLANNER_LEDGER`:
 *   - `http://127.0.0.1:<puerto>/api/planner`  el backend de EMMA (lo normal);
 *   - `memory:`  un ledger en memoria, SOLO para correr la suite de Marplanner sin EMMA.
 * Sin la variable no se arranca: no hay modo "sin ledger" que guarde en un fichero.
 */
import { MessageChannel, Worker, receiveMessageOnPort } from "node:worker_threads";

const TIMEOUT_MS = 15_000;

export class LedgerConflict extends Error {}
export class LedgerUnavailable extends Error {}

class MemoryLedger {
  constructor() { this.records = []; }
  list(after) { return this.records.slice(after).map((b64, i) => ({ seq: after + i + 1, changeset: b64 })); }
  append(b64, expected) {
    if (expected !== this.records.length) throw new LedgerConflict(`hay ${this.records.length}, se vio ${expected}`);
    this.records.push(b64);
    return this.records.length;
  }
}

/**
 * Un corte del ledger, de solo lectura: los registros que había en un instante (`ground-summary.mjs`
 * reconstruye así lo que Tierra puede saber con el retardo de la luz). Escribir en él es un error:
 * un resumen no cambia nada.
 */
export class LedgerReadOnly extends Error {}

class SnapshotLedger {
  constructor(records) { this.records = records; }
  list(after) { return this.records.slice(after).map((b64, i) => ({ seq: after + i + 1, changeset: b64 })); }
  append() { throw new LedgerReadOnly("corte del ledger de solo lectura: no se escribe"); }
}

class HttpLedger {
  constructor(base) {
    const url = new URL(base);
    if (!["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)) {
      // El ledger es el de EMMA en esta misma máquina: nada de la base sale de ella.
      throw new LedgerUnavailable(`EMMA_PLANNER_LEDGER debe ser loopback, no ${url.hostname}`);
    }
    this.base = base.replace(/\/$/, "");
    this.shared = new Int32Array(new SharedArrayBuffer(4));
    const { port1, port2 } = new MessageChannel();
    this.port = port1;
    this.worker = new Worker(new URL("./ledger-worker.mjs", import.meta.url), {
      workerData: { shared: this.shared, port: port2 }, transferList: [port2],
    });
    this.worker.unref();
  }
  call(method, path, body) {
    Atomics.store(this.shared, 0, 0);
    this.worker.postMessage({ method, url: this.base + path, body, timeout: TIMEOUT_MS });
    const waited = Atomics.wait(this.shared, 0, 0, TIMEOUT_MS + 1000);
    const reply = receiveMessageOnPort(this.port);
    if (waited === "timed-out" || !reply) throw new LedgerUnavailable("el ledger de EMMA no respondió a tiempo");
    const { status, text, error } = reply.message;
    if (error) throw new LedgerUnavailable(`ledger de EMMA inalcanzable: ${error}`);
    if (status === 409) throw new LedgerConflict(text);
    if (status < 200 || status >= 300) throw new LedgerUnavailable(`ledger de EMMA: ${status} ${text}`);
    return JSON.parse(text);
  }
  list(after) { return this.call("GET", `/changesets?after=${after}`).changesets; }
  append(b64, expected) {
    return this.call("POST", "/changesets", { changeset: b64, expected, written_by: "marplanner" }).seq;
  }
}

let http;
const memory = new Map();
/** El ledger de la base `key` (ruta absoluta). Por HTTP hay uno solo, el de EMMA; en memoria, uno
 * por ruta, para que las pruebas de Marplanner que abren bases distintas no se pisen. */
export function getLedger(key) {
  const where = process.env.EMMA_PLANNER_LEDGER;
  if (!where) throw new LedgerUnavailable("falta EMMA_PLANNER_LEDGER: la base de Marplanner es el ledger de EMMA");
  if (where === "snapshot:") {
    const records = globalThis.__EMMA_PLANNER_SNAPSHOT;
    if (!Array.isArray(records)) throw new LedgerUnavailable("modo snapshot: sin registros del corte");
    return new SnapshotLedger(records);
  }
  if (where === "memory:") {
    if (!memory.has(key)) memory.set(key, new MemoryLedger());
    return memory.get(key);
  }
  http ??= new HttpLedger(where);
  return http;
}
