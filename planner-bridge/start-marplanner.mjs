// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Arranca Marplanner junto a EMMA: su servidor, en loopback, con su base en el ledger de EMMA.
 *
 * Por qué existe: arrancar Marplanner a mano exige recordar cinco cosas que, si se olvidan, lo
 * dejan escribiendo en un fichero, escuchando en la red o pidiendo el tiempo a internet. Aquí van
 * fijas:
 *   - `--import register.mjs`: su `better-sqlite3` es el puente al ledger (sin él no arranca);
 *   - `HOST=127.0.0.1`: solo esta máquina;
 *   - `EMMA_PLANNER_LEDGER`: el ledger del backend de EMMA (por defecto http://127.0.0.1:8000);
 *   - `WEATHER_ENABLED=0` y sin claves de UniFi: lo que saca datos nuestros, apagado
 *     (decisión del usuario, 2026-11-12);
 *   - `SCHEDULER_DISABLED` NO se pone: sus avisos de hora y su hoja diaria son locales.
 *
 * Credenciales: las de Marplanner (`MP_ACCESS_TOKEN`, `MP_BOOTSTRAP_KEY`, `MP_ADMIN_PIN`) se leen
 * del entorno; si faltan, se usan las de ejemplo de su `.env.example` y se avisa.
 *
 * Uso: node planner-bridge/start-marplanner.mjs [--port 8790] [--emma http://127.0.0.1:8000]
 */
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs } from "node:util";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "..");
const marplanner = path.join(repo, "marplanner");

const { values } = parseArgs({
  options: {
    port: { type: "string", default: process.env.MARPLANNER_PORT ?? "8790" },
    emma: { type: "string", default: process.env.EMMA_URL ?? "http://127.0.0.1:8000" },
    data: { type: "string", default: path.join(repo, "data", "marplanner") },
  },
});

const EXAMPLE = {
  MP_ACCESS_TOKEN: "mpg-local-change-me",
  MP_BOOTSTRAP_KEY: "mpk-local-bootstrap-change-me",
  MP_ADMIN_PIN: "1234",
};
const missing = Object.keys(EXAMPLE).filter((k) => !process.env[k]);
if (missing.length) {
  console.warn(`[marplanner] sin ${missing.join(", ")}: se usan las credenciales de ejemplo`);
}

fs.mkdirSync(values.data, { recursive: true });
const env = {
  ...process.env,
  ...Object.fromEntries(missing.map((k) => [k, EXAMPLE[k]])),
  HOST: "127.0.0.1",
  PORT: values.port,
  DATA_DIR: values.data,
  DATABASE_PATH: "marplanner.db",
  EMMA_PLANNER_LEDGER: `${values.emma.replace(/\/$/, "")}/api/planner`,
  WEATHER_ENABLED: "0",
  MP_SEED_ON_EMPTY: process.env.MP_SEED_ON_EMPTY ?? "true",
};
for (const key of ["UNIFI_API_KEY", "UNIFI_SITE_ID", "UNIFI_HOST", "UNIFI_CONSOLE_ID"]) delete env[key];

const child = spawn(
  process.execPath,
  ["--import", pathToFileURL(path.join(here, "register.mjs")).href, "--import", "tsx", "src/server/index.ts"],
  { cwd: marplanner, env, stdio: "inherit" }
);
child.on("exit", (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => child.kill(sig));
