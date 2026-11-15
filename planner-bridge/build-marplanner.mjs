// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Compila Marplanner para el instalador de escritorio de EMMA, fuera de la copia.
 *
 * Por qué no su `npm run build`: su `scripts/build-server.mjs` empaqueta el servidor con esbuild
 * y deja fuera solo los módulos nativos. `undici` iría DENTRO del paquete, y el sustituto de
 * `planner-bridge/undici.mjs` (que solo deja llegar a esta máquina) no lo interceptaría: los
 * calendarios ICS saldrían a internet sin pasar por la puerta de EMMA. Aquí se empaqueta igual
 * que ellos, con `undici` también externo, y nada se escribe dentro de `marplanner/`.
 *
 * Sale `desktop/build/marplanner/`:
 *   server/index.js            el servidor (y sus fuentes, emojis y estilos, como en su build)
 *   summary-modules.js         lo que usa `ground-summary.mjs` (miembros, tablero, calendario…)
 *   drizzle/                   las migraciones (`migrate.ts` las lee de `cwd/drizzle`)
 *   node_modules/              SOLO los externos y sus dependencias, copiados de la instalación
 *                              (sin red): argon2, undici, @resvg/*, harfbuzzjs
 *   package.json               `type: module`, para que `register.mjs` resuelva `undici` aquí
 *   LICENSE, THIRD_PARTY_*     la licencia MIT de Marplanner y las de lo empaquetado
 *
 * Uso: node planner-bridge/build-marplanner.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "..");
const src = path.join(repo, "marplanner");
const out = path.join(repo, "desktop", "build", "marplanner");
const require = createRequire(path.join(src, "package.json"));
const { build } = require("esbuild");
const scripts = pathToFileURL(path.join(src, "scripts")).href;
const { resolveBuildInfo } = await import(`${scripts}/build-info.mjs`);
const { assertNoPrivateInputs, seedBundlePlugin } = await import(`${scripts}/seed-bundle-plugin.mjs`);
const { writeLicenses } = await import(`${scripts}/bundled-licenses.mjs`);

const RESVG_EXTERNALS = ["@resvg/resvg-js", "@resvg/resvg-wasm", "harfbuzzjs"];
// Lo de Marplanner más `undici`: tiene que resolverse en tiempo de ejecución para que el gancho
// de `register.mjs` lo sustituya.
const EXTERNALS = ["argon2", "better-sqlite3", "undici", ...RESVG_EXTERNALS];
const BANNER = { js: "import { createRequire as __cr } from 'node:module'; const require = __cr(import.meta.url);" };
const COMMON = { absWorkingDir: src, bundle: true, platform: "node", format: "esm", target: "node24", external: EXTERNALS, banner: BANNER };

fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(path.join(out, "server"), { recursive: true });
process.chdir(src); // las rutas relativas de su configuración (seeds, define) son desde su raíz

const server = await build({
  ...COMMON,
  entryPoints: ["src/server/index.ts"],
  outfile: path.join(out, "server", "index.js"),
  define: { __MP_BUILD__: JSON.stringify(resolveBuildInfo()) },
  plugins: [seedBundlePlugin()],
  metafile: true,
});
assertNoPrivateInputs(server.metafile);
const serverOut = Object.keys(server.metafile.outputs).find((k) => k.endsWith("index.js"));
writeLicenses(
  path.join(out, "server", "THIRD_PARTY_LICENSES.txt"),
  "Marplanner server bundle (EMMA desktop build) — third-party licences",
  Object.keys(server.metafile.outputs[serverOut].inputs),
);
const copy = (from, to) => fs.cpSync(path.join(src, from), path.join(out, to), { recursive: true });
copy("src/server/modules/daily-briefing/render/fonts/jetbrains-mono", "server/fonts/jetbrains-mono");
copy("src/shared/noto", "server/noto");
copy("src/server/modules/daily-briefing/corpora/NOTICE.txt", "server/CORPORA-NOTICE.txt");
copy("src/client/styles/tokens.css", "server/ui-tokens.css");
copy("drizzle", "drizzle");
copy("LICENSE", "LICENSE");
copy("THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md");

// Los módulos del resumen de Tierra, en un solo fichero (sin tsx en el instalador).
await build({
  ...COMMON,
  stdin: {
    contents: [
      'export * as members from "./src/server/modules/members/index.ts";',
      'export * as routines from "./src/server/modules/routines/index.ts";',
      'export * as calendar from "./src/server/modules/calendar/index.ts";',
      'export * as messages from "./src/server/modules/daily-messages/index.ts";',
      'export * as reminders from "./src/server/modules/reminders/index.ts";',
      'export * as briefing from "./src/server/modules/daily-briefing/index.ts";',
      'export * as briefingSettings from "./src/server/modules/daily-briefing/settings.ts";',
    ].join("\n"),
    resolveDir: src,
    loader: "ts",
  },
  outfile: path.join(out, "summary-modules.js"),
  define: { __MP_BUILD__: JSON.stringify(resolveBuildInfo()) },
});

// Las dependencias en tiempo de ejecución: los externos y su cierre, copiados de node_modules.
const needed = new Set();
const visit = (name, fromDir) => {
  const req = createRequire(path.join(fromDir, "package.json"));
  let pkgJson;
  try {
    pkgJson = req.resolve(`${name}/package.json`);
  } catch {
    return; // opcional que no está (otra plataforma)
  }
  const dir = path.dirname(pkgJson);
  if (needed.has(dir)) return;
  needed.add(dir);
  const pkg = JSON.parse(fs.readFileSync(pkgJson, "utf8"));
  for (const dep of Object.keys({ ...pkg.dependencies, ...pkg.optionalDependencies })) visit(dep, dir);
};
for (const name of ["argon2", "undici", ...RESVG_EXTERNALS]) visit(name, src);
const modulesRoot = path.join(src, "node_modules");
for (const dir of needed) {
  const rel = path.relative(modulesRoot, dir);
  if (rel.startsWith("..")) throw new Error(`dependencia fuera de node_modules: ${dir}`);
  fs.cpSync(dir, path.join(out, "node_modules", rel), { recursive: true });
}
fs.writeFileSync(
  path.join(out, "package.json"),
  `${JSON.stringify({ name: "marplanner-emma-runtime", private: true, type: "module" }, null, 2)}\n`,
);
console.log(`marplanner → ${path.relative(repo, out)} (${needed.size} paquetes en tiempo de ejecución)`);
