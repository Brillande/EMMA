// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Toda salida de Marplanner a internet pasa por la puerta de EMMA, o no sale.
 *
 * Por qué existe: en EMMA toda salida a internet pasa por `backend/app/core/egress.py`
 * (invariante 3 bis): lista blanca por propósito, modo sin red, modo seguro, traza. Marplanner es
 * Node y sale con `fetch` y con `undici` por su cuenta. Decisión del usuario (2026-11-12): lo que
 * saca datos nuestros no sale (Open-Meteo lleva las coordenadas del hogar; UniFi, una clave y el
 * control de la red), y lo que solo trae datos sale solo con red.
 *
 * Aquí:
 *   - `fetch` global: a esta máquina (loopback), tal cual; a un host con propósito de Marplanner
 *     (`PURPOSES`), por `POST /api/planner/fetch` de EMMA, que decide; a cualquier otro, error.
 *   - `undici` (calendarios ICS, UniFi): solo loopback. Los calendarios ICS remotos quedan sin red
 *     hasta que tengan propósito en la puerta (`marplanner/ORIGEN.md`).
 * Solo GET y sin cuerpo: una petición que lleve algo nuestro no sale ni hacia un host permitido.
 */

const LOOPBACK = new Set(["127.0.0.1", "localhost", "[::1]", "::1"]);

// Host -> propósito de `egress.ALLOWLIST`. Cualquier otro host no tiene salida.
const PURPOSES = [
  [/^zenquotes\.io$/i, "planner-quotes"],
  [/^(en|es)\.wikipedia\.org$/i, "planner-onthisday"],
];

export class EgressRefused extends TypeError {
  constructor(message) {
    // TypeError, como el de un `fetch` que no llega: Marplanner ya degrada con eso.
    super(message);
    this.name = "EgressRefused";
  }
}

export function isLoopback(url) {
  return LOOPBACK.has(new URL(url).hostname);
}

export function purposeFor(url) {
  const { protocol, hostname } = new URL(url);
  if (protocol !== "https:") return null;
  for (const [pattern, purpose] of PURPOSES) if (pattern.test(hostname)) return purpose;
  return null;
}

function gateUrl() {
  const ledger = process.env.EMMA_PLANNER_LEDGER ?? "";
  if (!/^https?:\/\//.test(ledger)) return null;
  return ledger.replace(/\/$/, "").replace(/\/planner$/, "/planner/fetch");
}

function targetOf(input) {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input?.url;
}

export function guardFetch(original) {
  return async function emmaFetch(input, init = {}) {
    const url = targetOf(input);
    if (isLoopback(url)) return original(input, init);
    const method = (init.method ?? input?.method ?? "GET").toUpperCase();
    if (method !== "GET" || init.body != null) {
      throw new EgressRefused(`no sale: ${method} con cuerpo a ${new URL(url).hostname}`);
    }
    const purpose = purposeFor(url);
    if (!purpose) throw new EgressRefused(`no sale: ${new URL(url).hostname} no tiene propósito en EMMA`);
    const gate = gateUrl();
    if (!gate) throw new EgressRefused("no sale: sin puerta de EMMA (EMMA_PLANNER_LEDGER no es HTTP)");
    const res = await original(gate, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ purpose, url }),
      signal: init.signal,
    });
    if (!res.ok) throw new EgressRefused(`no sale (${res.status}): ${await res.text()}`);
    const out = await res.json();
    return new Response(out.status === 204 ? null : out.body, {
      status: out.status,
      headers: out.content_type ? { "content-type": out.content_type } : {},
    });
  };
}

export function guardUndiciFetch(original) {
  return function emmaUndiciFetch(input, init) {
    const url = targetOf(input);
    if (!isLoopback(url)) {
      return Promise.reject(new EgressRefused(`no sale: ${new URL(url).hostname} (undici, sin propósito en EMMA)`));
    }
    return original(input, init);
  };
}
