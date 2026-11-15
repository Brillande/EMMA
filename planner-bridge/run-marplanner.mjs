// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Punto de entrada del servidor de Marplanner en el escritorio: primero el puente, luego él.
 *
 * Por qué existe: en un `utilityProcess` de Electron el `--import` de `execArgv` no llega a cargar
 * `register.mjs` (visto el 2026-11-12: «Cannot find package 'better-sqlite3'»). Importándolo aquí
 * antes que el servidor, sus ganchos (better-sqlite3 → ledger, undici → solo loopback, fetch → puerta
 * de EMMA) están puestos cuando el servidor resuelve sus módulos. Uso: run-marplanner.mjs <server.js>
 */
import { fileURLToPath, pathToFileURL } from "node:url";

await import("./register.mjs");
const entry = process.argv[2];
if (!entry) throw new Error("falta la ruta del servidor de Marplanner");
const url = pathToFileURL(entry).href;
// Su `index.ts` solo arranca si es el programa principal: `process.argv[1] === fileURLToPath(
// import.meta.url)`. Importado desde aquí no lo sería y se quedaba quieto, sin escuchar ni decir
// nada (visto el 2026-11-12). Se le pone su propia ruta, escrita igual que la calcula él.
process.argv.splice(1, 2, fileURLToPath(url));
await import(url);
