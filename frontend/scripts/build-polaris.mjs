// SPDX-License-Identifier: AGPL-3.0-or-later
// Compila el visor web de Polaris copiado tal cual en `polaris/tools/visor3d_web/` (raiz del repo), con el mismo
// esbuild y las mismas opciones que `visor3d.py visor` de Polaris (commit en polaris/ADOPTADO.txt), y lo deja
// en `backend/app/data/polaris_web/`, desde donde el backend lo sirve junto a los datos.
// Las dependencias son las del `package-lock.json` de Polaris (npm ci): el esbuild de Polaris
// (0.25.10) no convive con el que pide Vite en la raíz.
//
// Se compila FUERA de la copia, en una carpeta temporal del sistema: `npm ci` dentro de
// `polaris/tools/visor3d_web/` dejaba ahí `node_modules/`, y la prueba que vigila que `polaris/`
// sea copia literal tenía que eximirlo por ruta. Una copia literal no recibe nada: aquí solo se lee.
import { execFileSync } from "node:child_process";
import { copyFileSync, cpSync, existsSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const web = join(root, "..", "polaris", "tools", "visor3d_web");
const out = join(root, "..", "backend", "app", "data", "polaris_web");
const shell = process.platform === "win32";
// Restos de cuando se compilaba dentro de la copia: no se usan ni se llevan a la carpeta temporal.
const LEFTOVERS = ["node_modules", "dist"];

// Sin su package.json, `npm ci` sube hasta el primero que encuentre y vacia sus node_modules (paso
// con el de frontend/).
if (!existsSync(join(web, "package.json")) || !existsSync(join(web, "package-lock.json"))) {
  throw new Error(`falta la copia de Polaris en ${web}: corre backend/scripts/polaris_sync.py`);
}
for (const name of LEFTOVERS) {
  if (existsSync(join(web, name))) {
    console.warn(`aviso: ${join(web, name)} es un resto de una compilacion anterior; no se usa. Borralo: la copia de Polaris no lleva nada generado.`);
  }
}

const work = mkdtempSync(join(tmpdir(), "emma-polaris-web-"));
try {
  cpSync(web, work, { recursive: true, filter: (source) => !LEFTOVERS.includes(basename(source)) });
  // `--prefer-offline`: con la cache de npm poblada se compila sin red.
  execFileSync("npm", ["ci", "--no-audit", "--no-fund", "--prefer-offline"], { cwd: work, stdio: "inherit", shell });
  const esbuild = join(work, "node_modules", ".bin", shell ? "esbuild.cmd" : "esbuild");
  // Los paquetes salen a la carpeta temporal y solo se llevan a `out` si se compilaron los dos:
  // un fallo a medias no deja un visor mezclado de dos compilaciones.
  const built = join(work, "emma-out");
  const bundles = [["main.js", "bundle.js"], ["render.js", "render.bundle.js"]];
  for (const [entry, bundle] of bundles) {
    execFileSync(
      esbuild,
      [entry, "--bundle", "--format=esm", "--minify", `--outfile=${join("emma-out", bundle)}`],
      { cwd: work, stdio: "inherit", shell },
    );
  }
  mkdirSync(out, { recursive: true });
  for (const [, bundle] of bundles) copyFileSync(join(built, bundle), join(out, bundle));
  for (const page of ["index.html", "render.html"]) copyFileSync(join(web, page), join(out, page));
} finally {
  rmSync(work, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}
console.log(`visor de Polaris -> ${out}`);
