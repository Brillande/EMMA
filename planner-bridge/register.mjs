// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Se carga con `node --import <ruta>/planner-bridge/register.mjs` al arrancar Marplanner.
 *
 * Por qué existe: la copia de Marplanner (`marplanner/`) es literal y no se edita. Lo que EMMA le
 * cambia se cambia aquí, al cargar:
 *   - su `better-sqlite3` es `better-sqlite3.mjs`: su base es el ledger firmado de EMMA;
 *   - su `undici` y el `fetch` global pasan por `egress.mjs`: nada sale a internet si no es por la
 *     puerta de EMMA;
 *   - `compat-windows.mjs`: lo que le falta en Windows.
 * Vale para `import` y `require` (ganchos síncronos de Node ≥ 22.15).
 */
import { registerHooks } from "node:module";
import "./compat-windows.mjs";
import { guardFetch } from "./egress.mjs";

// El `undici` de verdad es el que instaló Marplanner: se resuelve desde su carpeta.
const MARPLANNER = new URL("../marplanner/package.json", import.meta.url).href;
const SHIMS = {
  "better-sqlite3": new URL("./better-sqlite3.mjs", import.meta.url).href,
  undici: new URL("./undici.mjs", import.meta.url).href,
};

registerHooks({
  resolve(specifier, context, nextResolve) {
    const shim = SHIMS[specifier];
    if (!shim) return nextResolve(specifier, context);
    // El sustituto de `undici` sí importa el de verdad.
    if (context.parentURL === shim) return nextResolve(specifier, { ...context, parentURL: MARPLANNER });
    return { url: shim, format: "module", shortCircuit: true };
  },
});

globalThis.fetch = guardFetch(globalThis.fetch);
