/**
 * Que el inglés no retroceda (`lib/i18n.ts`, 2026-11-15).
 *
 * La interfaz se traduce por partes, fichero a fichero, poniendo `tr(castellano, inglés)` donde
 * había un literal castellano. Dos cosas se vigilan leyendo las fuentes:
 *
 * 1. Todo `tr()` lleva un inglés que no está vacío.
 * 2. El número de líneas con castellano suelto de cada fichero no sube. `i18nBaseline.json` guarda
 *    cuántas tenía cada uno al empezar: una unidad que traduce un fichero las baja, y un fichero
 *    nuevo, que no está en la lista, empieza en cero. El recuento es una heurística (tildes, eñes y
 *    signos de apertura fuera de los comentarios y de los `tr`): no ve el castellano sin tilde, y
 *    por eso es un tope que no sube, no una prueba de que no quede nada.
 *
 * La línea base solo se reescribe a propósito, al fusionar: `EMMA_I18N_BASELINE=write npx vitest
 * run src/test/i18nGuard.test.ts`. Una unidad no la toca.
 */

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const BASELINE_PATH = fileURLToPath(new URL("./i18nBaseline.json", import.meta.url));

const SOURCES = Object.entries(
  import.meta.glob("/src/**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }),
)
  .map(([path, source]) => [path, String(source).replace(/\r\n/g, "\n")] as const)
  // Las pruebas fijan el castellano a propósito; los ficheros generados no llevan texto.
  .filter(([path]) => !/\.test\.tsx?$/.test(path) && !/\.generated\.ts$/.test(path) && !path.startsWith("/src/test/"));

const LITERAL = [/"(?:[^"\\\n]|\\.)*"/, /'(?:[^'\\\n]|\\.)*'/, /`(?:[^`\\]|\\.)*`/].map((r) => r.source).join("|");
const TR_CALL = new RegExp(`\\btr\\(\\s*(${LITERAL})\\s*,\\s*(${LITERAL})\\s*,?\\s*\\)`, "g");
const SPANISH = /[áéíóúñÁÉÍÓÚÑ¿¡]/;

function withoutComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (block) => block.replace(/[^\n]/g, " "))
    .replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");
}

/** Los `tr()` de un fichero cuyo inglés está vacío. */
function emptyEnglish(path: string, source: string): string[] {
  const found: string[] = [];
  for (const match of withoutComments(source).matchAll(TR_CALL)) {
    if ((match[2] ?? "").slice(1, -1).trim() === "") found.push(`${path}: tr(${match[1]}, …) sin inglés`);
  }
  return found;
}

/** Líneas con castellano suelto: fuera de los comentarios y de los `tr(…)`. */
function looseSpanish(source: string): number {
  const code = withoutComments(source).replace(TR_CALL, (call) => "\n".repeat(call.split("\n").length - 1));
  return code.split("\n").filter((line) => SPANISH.test(line)).length;
}

const counts = Object.fromEntries(
  SOURCES.map(([path, source]) => [path, looseSpanish(source)] as const).filter(([, count]) => count > 0),
);

if (process.env.EMMA_I18N_BASELINE === "write") {
  const sorted = Object.fromEntries(Object.entries(counts).sort(([a], [b]) => a.localeCompare(b)));
  writeFileSync(BASELINE_PATH, `${JSON.stringify({ files: sorted }, null, 1)}\n`, "utf8");
}

const BASELINE = (
  existsSync(BASELINE_PATH) ? JSON.parse(readFileSync(BASELINE_PATH, "utf8")) : { files: {} }
) as { files: Record<string, number> };

describe("el buscador de castellano suelto", () => {
  it("lee las fuentes de la interfaz, no una lista vacía", () => {
    expect(SOURCES.length).toBeGreaterThan(200);
    expect(Object.keys(BASELINE.files).length).toBeGreaterThan(50);
  });

  it("cuenta lo que está fuera de un `tr` y de un comentario, y nada más", () => {
    expect(looseSpanish('const a = "Presión";')).toBe(1);
    expect(looseSpanish("<p>¿Seguro?</p>")).toBe(1);
    expect(looseSpanish('const a = tr("Presión", "Pressure");')).toBe(0);
    expect(looseSpanish('const a = tr(\n  "Presión",\n  "Pressure",\n);')).toBe(0);
    expect(looseSpanish("// la presión de la cabina\nconst a = 1;")).toBe(0);
    expect(looseSpanish("/** Presión. */\nconst a = `${x} día`;")).toBe(1);
  });

  it("ve un `tr` sin inglés", () => {
    expect(emptyEnglish("/x.ts", 'tr("Presión", "")')).toHaveLength(1);
    expect(emptyEnglish("/x.ts", "tr('Presión', '  ')")).toHaveLength(1);
    expect(emptyEnglish("/x.ts", 'tr("Presión", "Pressure")')).toEqual([]);
  });
});

describe("el inglés de la interfaz no retrocede", () => {
  it("todo `tr()` lleva su inglés", () => {
    expect(SOURCES.flatMap(([path, source]) => emptyEnglish(path, source))).toEqual([]);
  });

  it("ningún fichero tiene más castellano suelto que al empezar; uno nuevo, ninguno", () => {
    const worse = Object.entries(counts)
      .filter(([path, count]) => count > (BASELINE.files[path] ?? 0))
      .map(([path, count]) => `${path}: ${count} líneas (tope ${BASELINE.files[path] ?? 0})`);
    expect(worse).toEqual([]);
  });
});
