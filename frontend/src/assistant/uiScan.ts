/**
 * Lo que las dos consolas montan, leído de sus `.tsx`: cada panel (`<section>`), cada pliegue
 * (`<details>`, `<Fold>`) y en qué pestaña de qué consola acaba cada uno. Solo lo usan las pruebas
 * (`uiInventory.test.ts`), con Node: no viaja en el paquete.
 *
 * Por qué existe: el asistente llega a una parte de la interfaz por el inventario
 * (`backend/app/data/assistant_ui.json`), y un inventario escrito a mano se queda atrás en cuanto
 * otra unidad añade un panel. Esto lo rehace desde el código, como `timelineMarks.test.ts` lee
 * `timeline.py`: un panel nuevo sin entrada, o una entrada de un panel que ya no está, hacen
 * fallar las pruebas.
 *
 * Cómo: desde las tablas `sección → paneles` de `CrewConsole.tsx` y `GroundConsole.tsx`, sigue
 * cada `<Componente` hasta el fichero que lo define (importaciones relativas) y cada componente
 * hereda las pestañas donde se usa. Lo que va fuera de la tabla (el carril, la cabecera del
 * retardo) queda en la sección `null`: a la vista con cualquier pestaña. Las pestañas de entorno
 * (`environmentSections`) son una sola, `env-*`: las pone el backend, una por perfil de misión.
 */

import { existsSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";

export type ConsoleId = "crew" | "ground";

export interface Place {
  console: ConsoleId;
  /** La clave de la pestaña; `env-*` las de entorno; `null` fuera de las pestañas (el carril). */
  section: string | null;
}

export interface FoundElement {
  /** Ruta desde `frontend/src`, con `/`. */
  file: string;
  line: number;
  /** `section`, `details` o `Fold`. */
  tag: string;
  /** El texto entero de la etiqueta de apertura. */
  opening: string;
  /** El valor literal de `data-ui`, o `null` si no lo lleva o no es un literal. */
  uiId: string | null;
  /** El componente (o la función de primer nivel) que lo contiene. */
  unit: string;
  places: Place[];
}

interface Unit {
  file: string;
  name: string;
  start: number;
  end: number;
}

const SRC = resolve(dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")), "..");
const ROOTS: Record<ConsoleId, { file: string; unit: string }> = {
  crew: { file: "dashboard/CrewConsole.tsx", unit: "CrewConsole" },
  ground: { file: "ground/GroundConsole.tsx", unit: "GroundConsole" },
};
/** Las etiquetas que el inventario cuenta: paneles y pliegues. */
export const TRACKED_TAGS = ["section", "details", "Fold"] as const;
export const ENV_SECTION = "env-*";

const sources = new Map<string, string>();

export function source(file: string): string {
  let text = sources.get(file);
  if (text === undefined) {
    text = withoutComments(readFileSync(join(SRC, file), "utf8").replace(/\r\n/g, "\n"));
    sources.set(file, text);
  }
  return text;
}

/**
 * El texto con los comentarios en blanco (mismas posiciones y líneas): un `<details>` que se nombra
 * en un comentario no es un pliegue. Las cadenas se respetan: `"http://…"` no empieza un comentario.
 */
export function withoutComments(text: string): string {
  let out = "";
  let index = 0;
  let quote: string | null = null;
  const blank = (piece: string) => piece.replace(/[^\n]/g, " ");
  while (index < text.length) {
    const char = text[index] ?? "";
    if (quote !== null) {
      out += char;
      if (char === "\\") {
        out += text[index + 1] ?? "";
        index += 2;
        continue;
      }
      if (char === quote || (char === "\n" && quote !== "`")) quote = null;
      index += 1;
      continue;
    }
    if (char === "/" && text[index + 1] === "*") {
      const end = text.indexOf("*/", index + 2);
      const stop = end < 0 ? text.length : end + 2;
      out += blank(text.slice(index, stop));
      index = stop;
      continue;
    }
    if (char === "/" && text[index + 1] === "/") {
      const end = text.indexOf("\n", index);
      const stop = end < 0 ? text.length : end;
      out += blank(text.slice(index, stop));
      index = stop;
      continue;
    }
    if (char === '"' || char === "'" || char === "`") quote = char;
    out += char;
    index += 1;
  }
  return out;
}

/** Las funciones y constantes de primer nivel de un fichero, con su tramo de texto. */
function unitsOf(file: string): Unit[] {
  const text = source(file);
  const starts = [...text.matchAll(/^(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\s+(\w+)|const\s+(\w+)\s*[:=])/gm)];
  return starts.map((match, index) => ({
    file,
    name: match[1] ?? match[2] ?? "",
    start: match.index ?? 0,
    end: starts[index + 1]?.index ?? text.length,
  }));
}

/** Nombre importado → fichero `.tsx` de donde viene (solo importaciones relativas). */
const importCache = new Map<string, Map<string, string>>();

function importsOf(file: string): Map<string, string> {
  const cached = importCache.get(file);
  if (cached !== undefined) return cached;
  const text = source(file);
  const out = new Map<string, string>();
  importCache.set(file, out);
  for (const match of text.matchAll(/import\s+(?:(\w+)\s*,?\s*)?(?:\{([^}]*)\})?\s*from\s+"(\.[^"]+)"/g)) {
    const target = resolveModule(file, match[3] ?? "");
    if (target === null || !target.endsWith(".tsx")) continue;
    if (match[1] !== undefined) out.set(match[1], target);
    for (const raw of (match[2] ?? "").split(",")) {
      const item = raw.trim().replace(/^type\s+/, "");
      if (item === "" || raw.trim().startsWith("type ")) continue;
      const [original, alias] = item.split(/\s+as\s+/);
      out.set((alias ?? original ?? "").trim(), target);
    }
  }
  return out;
}

function resolveModule(from: string, spec: string): string | null {
  const base = join(dirname(join(SRC, from)), spec);
  for (const candidate of [`${base}.tsx`, `${base}.ts`, join(base, "index.tsx"), join(base, "index.ts")]) {
    if (existsSync(candidate)) return relative(SRC, candidate).replace(/\\/g, "/");
  }
  return null;
}

/** Los usos de otros componentes dentro de un tramo: `<Nombre` y llamadas `nombre(`. */
function usesIn(text: string, start: number, end: number): { name: string; at: number }[] {
  const out: { name: string; at: number }[] = [];
  const slice = text.slice(start, end);
  for (const match of slice.matchAll(/<([A-Z]\w*)\b/g)) out.push({ name: match[1] ?? "", at: start + (match.index ?? 0) });
  for (const match of slice.matchAll(/\b([a-z]\w*)\(/g)) out.push({ name: match[1] ?? "", at: start + (match.index ?? 0) });
  return out;
}

/** La etiqueta de apertura que empieza en `at` (`<section …>`), respetando llaves y comillas. */
export function openingTag(text: string, at: number): string {
  let depth = 0;
  let quote: string | null = null;
  for (let index = at + 1; index < text.length; index += 1) {
    const char = text[index];
    if (quote !== null) {
      if (char === quote && text[index - 1] !== "\\") quote = null;
      continue;
    }
    if (char === '"' || char === "'" || char === "`") quote = char;
    else if (char === "{") depth += 1;
    else if (char === "}") depth -= 1;
    else if (char === ">" && depth === 0) return text.slice(at, index + 1);
  }
  return text.slice(at);
}

/** Las regiones de la tabla de una consola: cada `key: "…"` hasta el siguiente; lo demás, `null`. */
function consoleRegions(
  file: string,
  unit: Unit,
): { start: number; end: number; section: string | null; setAside: boolean }[] {
  const text = source(file);
  const body = text.slice(unit.start, unit.end);
  const table = body.indexOf("const sections");
  const tableEnd = body.indexOf("...environmentSections(", table);
  if (table < 0 || tableEnd < 0) throw new Error(`${file}: no se encuentra la tabla de secciones`);
  const keys = [...body.slice(table, tableEnd).matchAll(/\bkey: "([a-z0-9-]+)"/g)];
  return keys.map((match, index) => {
    const from = table + (match.index ?? 0);
    const to = keys[index + 1] === undefined ? tableEnd : table + (keys[index + 1]?.index ?? 0);
    return {
      start: unit.start + from,
      end: unit.start + to,
      section: match[1] ?? null,
      // Apartada de esta versión: la marca va escrita en su entrada de la tabla.
      setAside: body.slice(from, to).includes("setAside: true"),
    };
  });
}

function placeKey(place: Place): string {
  return `${place.console}:${place.section ?? ""}`;
}

export interface Scan {
  elements: FoundElement[];
  /** Las claves de pestaña de cada consola, en el orden de su tabla (sin las de entorno). */
  sections: Record<ConsoleId, string[]>;
  /** Las claves de pestaña apartadas de esta versión (`setAside: true`), en el mismo orden. */
  setAside: Record<ConsoleId, string[]>;
  /** Los ficheros que montan las consolas. */
  files: string[];
}

/** Recorre las dos consolas y devuelve cada panel y pliegue con sus pestañas. */
export function scan(): Scan {
  const units = new Map<string, Unit[]>();
  const unitsFor = (file: string) => {
    let found = units.get(file);
    if (found === undefined) {
      found = unitsOf(file);
      units.set(file, found);
    }
    return found;
  };
  const places = new Map<string, Map<string, Place>>(); // `fichero#unidad` → lugares
  const queue: { file: string; unit: string }[] = [];
  const addPlace = (file: string, unit: string, place: Place) => {
    const id = `${file}#${unit}`;
    let set = places.get(id);
    if (set === undefined) {
      set = new Map();
      places.set(id, set);
    }
    if (!set.has(placeKey(place))) {
      set.set(placeKey(place), place);
      queue.push({ file, unit });
    }
  };
  /** Un uso de `name` desde `file` lleva `place` al componente que nombra. */
  const reach = (file: string, name: string, place: Place) => {
    const local = unitsFor(file).find((unit) => unit.name === name);
    if (local !== undefined) {
      addPlace(file, name, place);
      return;
    }
    const target = importsOf(file).get(name);
    if (target !== undefined && unitsFor(target).some((unit) => unit.name === name)) addPlace(target, name, place);
  };

  const sections = { crew: [] as string[], ground: [] as string[] };
  const setAside = { crew: [] as string[], ground: [] as string[] };
  const regionsOf = new Map<string, { start: number; end: number; section: string | null }[]>();
  for (const [consoleId, root] of Object.entries(ROOTS) as [ConsoleId, { file: string; unit: string }][]) {
    const unit = unitsFor(root.file).find((item) => item.name === root.unit);
    if (unit === undefined) throw new Error(`${root.file}: falta ${root.unit}`);
    const regions = consoleRegions(root.file, unit);
    regionsOf.set(`${root.file}#${root.unit}`, regions);
    sections[consoleId] = regions.map((region) => region.section ?? "");
    setAside[consoleId] = regions.filter((region) => region.setAside).map((region) => region.section ?? "");
    const text = source(root.file);
    for (const use of usesIn(text, unit.start, unit.end)) {
      const region = regions.find((item) => use.at >= item.start && use.at < item.end);
      const section = use.name === "environmentSections" ? ENV_SECTION : (region?.section ?? null);
      reach(root.file, use.name, { console: consoleId, section });
    }
  }
  while (queue.length > 0) {
    const next = queue.shift();
    if (next === undefined) break;
    const unit = unitsFor(next.file).find((item) => item.name === next.unit);
    const here = places.get(`${next.file}#${next.unit}`);
    if (unit === undefined || here === undefined) continue;
    const text = source(next.file);
    for (const use of usesIn(text, unit.start, unit.end)) {
      if (use.name === next.unit) continue;
      for (const place of [...here.values()]) reach(next.file, use.name, place);
    }
  }

  // Las raíces siempre se recorren: sus paneles inline cuentan aunque la tabla ya no nombre ninguna
  // función local (visto el 2026-11-07, al sacar los últimos paneles inline de `CrewConsole.tsx` a
  // sus ficheros: la consola desaparecía del recorrido y con ella «Resumen», «Alertas» y
  // «Recomendaciones»).
  const roots = Object.values(ROOTS).map((root) => root.file);
  const files = [...new Set([...roots, ...[...places.keys()].map((id) => id.split("#")[0] ?? "")])].sort();
  const elements: FoundElement[] = [];
  const tagPattern = new RegExp(`<(${TRACKED_TAGS.join("|")})\\b`, "g");
  for (const file of files) {
    // `Fold.tsx` es el pliegue mismo: su `<details>` es el de cada `<Fold>`, que ya se cuenta.
    if (file === "components/Fold.tsx") continue;
    const text = source(file);
    for (const match of text.matchAll(tagPattern)) {
      const at = match.index ?? 0;
      const opening = openingTag(text, at);
      const unit = unitsFor(file).find((item) => at >= item.start && at < item.end);
      const unitName = unit?.name ?? "";
      const id = `${file}#${unitName}`;
      const regions = regionsOf.get(id);
      let found: Place[];
      if (regions !== undefined) {
        const consoleId = file === ROOTS.crew.file ? "crew" : "ground";
        const region = regions.find((item) => at >= item.start && at < item.end);
        found = [{ console: consoleId, section: region?.section ?? null }];
      } else {
        found = [...(places.get(id)?.values() ?? [])];
      }
      elements.push({
        file,
        line: text.slice(0, at).split("\n").length,
        tag: match[1] ?? "",
        opening,
        uiId: /\bdata-ui="([^"]+)"/.exec(opening)?.[1] ?? null,
        unit: unitName,
        places: found.sort((a, b) => placeKey(a).localeCompare(placeKey(b))),
      });
    }
  }
  return { elements, sections, setAside, files };
}
