// SPDX-License-Identifier: AGPL-3.0-or-later
// Hilo que hace la petición HTTP al ledger y despierta al que espera (ver ledger-client.mjs).
import { parentPort, workerData } from "node:worker_threads";

const { shared, port } = workerData;
parentPort.on("message", async ({ method, url, body, timeout }) => {
  let reply;
  try {
    const res = await fetch(url, {
      method,
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(timeout),
    });
    reply = { status: res.status, text: await res.text() };
  } catch (err) {
    reply = { error: String(err?.message ?? err) };
  }
  port.postMessage(reply);
  Atomics.store(shared, 0, 1);
  Atomics.notify(shared, 0);
});
