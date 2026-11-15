// SPDX-License-Identifier: AGPL-3.0-or-later
// Escribe `dist/THIRD_PARTY_LICENSES.txt`: los avisos de licencia de los paquetes npm que viajan en
// la interfaz compilada.
//
// Por qué existe: Vite mete en `dist/` el código de React, three, NiiVue, uPlot, MediaPipe, Vosk...
// y el instalador no llevaba sus avisos. Casi todas sus licencias (MIT, BSD, Apache-2.0, OFL) piden
// que el texto acompañe a la redistribución. Lo encontró la revisión de fuentes del 2026-11-14
// (`docs/fuentes-y-procedencia.md`, «Resumen de huecos», punto 2). Es el mismo remedio que ya usa
// Marplanner (`scripts/bundled-licenses.mjs`).
//
// Qué lista: los paquetes de `package-lock.json` que no son de desarrollo (`dev`/`devOptional`) y que
// están instalados, con la licencia que declara su `package.json` y el texto de sus ficheros de
// licencia y aviso. No interpreta licencias: copia lo que el paquete trae. Los modelos de `public/`
// (MediaPipe, Vosk) y las fuentes llevan además su licencia y su ORIGEN.txt al lado.
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const LICENSE_FILE = /^(licen[cs]e|copying|notice|authors)/i;

export const HEADER =
  "Avisos de licencia de los paquetes npm incluidos en la interfaz de EMMA\n" +
  "=====================================================================\n\n" +
  "Generado al compilar la interfaz (frontend/scripts/third-party.mjs). Cada paquete conserva su\n" +
  "licencia; aquí va el texto que el propio paquete distribuye. La licencia de EMMA está en\n" +
  "LICENSE y sus avisos en NOTICE, en la carpeta de recursos de la aplicación.\n";

/** Los paquetes de producción del lockfile que están en disco, ordenados por nombre. */
export function productionPackages(lock, root) {
  const out = [];
  for (const [key, info] of Object.entries(lock.packages ?? {})) {
    if (!key.startsWith("node_modules/") || info.dev || info.devOptional) continue;
    const dir = join(root, key);
    if (!existsSync(join(dir, "package.json"))) continue; // opcional de otra plataforma
    const name = key.slice(key.lastIndexOf("node_modules/") + "node_modules/".length);
    out.push({ name, dir, version: info.version, license: info.license });
  }
  return out.sort((a, b) => a.name.localeCompare(b.name) || a.dir.localeCompare(b.dir));
}

function declared(pkg, manifest) {
  const value = manifest.license ?? manifest.licenses ?? pkg.license;
  if (!value) return "no declarada en package.json";
  if (typeof value === "string") return value;
  return [].concat(value).map((item) => item.type ?? JSON.stringify(item)).join(" OR ");
}

export function notices(lock, root) {
  const parts = [HEADER];
  for (const pkg of productionPackages(lock, root)) {
    const manifest = JSON.parse(readFileSync(join(pkg.dir, "package.json"), "utf8"));
    parts.push("\n" + "-".repeat(72) + "\n");
    parts.push(`${pkg.name} ${manifest.version ?? pkg.version}\nLicencia declarada: ${declared(pkg, manifest)}\n`);
    const files = readdirSync(pkg.dir).filter((file) => LICENSE_FILE.test(file)).sort();
    if (files.length === 0) parts.push("(El paquete no trae fichero de licencia.)\n");
    for (const file of files) {
      const text = readFileSync(join(pkg.dir, file), "utf8").trim();
      if (text) parts.push(`\n[${file}]\n${text}\n`);
    }
  }
  return parts.join("");
}

const isMain = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  const lock = JSON.parse(readFileSync(join(root, "package-lock.json"), "utf8"));
  const target = join(root, "dist", "THIRD_PARTY_LICENSES.txt");
  writeFileSync(target, notices(lock, root), "utf8");
  console.log(`Avisos de terceros: ${target}`);
}
