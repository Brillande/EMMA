// SPDX-License-Identifier: AGPL-3.0-or-later
// Un hilo por resumen (`summary-server.mjs`): sus propios módulos de Marplanner, con la base de su
// corte, y su propio `process.env`. Primero el puente (better-sqlite3, undici), luego el cálculo.
import { parentPort, workerData } from "node:worker_threads";

await import("./register.mjs");
const { runSummary } = await import("./ground-summary.mjs");
try {
  parentPort.postMessage({ ok: true, result: await runSummary(workerData) });
} catch (err) {
  parentPort.postMessage({ ok: false, error: String(err?.message ?? err) });
}
