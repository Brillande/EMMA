/**
 * La interfaz no redacta: las palabras de nivel, de fase y de trayectoria son del backend.
 *
 * `CLAUDE.md`: «la interfaz no redacta texto clinico: lo muestra tal cual lo da el backend».
 * Se cumplia con las frases y no con las palabras sueltas: la insignia de nivel, la tira de
 * fases y la trayectoria de un dominio tenian su propia tabla aqui, y las tres se habian
 * separado de la del backend (CONCERN con dos nombres, «regreso» frente a «preparación del
 * regreso»). Esta prueba lee todas las fuentes de `src` y falla si una de esas palabras
 * vuelve a escribirse en un literal o en el texto de un componente.
 *
 * Los comentarios no cuentan, ni las claves de la API (`"nominal"`). Lo que queda escrito a
 * proposito esta en `DECLARED`, cada cosa con su motivo, y una excepcion que ya no hace falta
 * tambien hace fallar la prueba.
 */

import { describe, expect, it } from "vitest";

/** Palabras con que el backend nombra niveles, fases y trayectorias. Sin acentos se cazan igual. */
const FORBIDDEN: Record<string, RegExp> = {
  nivel: /nominal|vigilancia|precauci[oó]n|preocupaci[oó]n|cr[ií]tico/gi,
  fase: /prevuelo|adaptaci[oó]n|fase estable|regreso|posvuelo/gi,
  trayectoria: /recuper[aá]ndose|empeorando/gi,
};

/** La clave de la API coincide con una palabra: como clave no es texto para la tripulacion. */
const API_KEYS = /"nominal"|\bnominal:/g;

interface Declared {
  text: string;
  /**
   * `otro-concepto`: la misma palabra para otra cosa. `pendiente`: texto de la interfaz que
   * nombra un nivel y deberia venir del backend; esta en un fichero que no era de este cambio.
   */
  kind: "otro-concepto" | "pendiente";
  why: string;
}

const DECLARED: Record<string, Declared[]> = {
  "/src/App.tsx": [
    {
      text: 'nominal: "Nominal"',
      kind: "otro-concepto",
      why: "nombre del escenario del simulador en el selector, no un nivel de riesgo",
    },
  ],
  "/src/components/StatusStrip.tsx": [
    {
      text: 'tr("Vigilancia", "Monitoring")',
      kind: "otro-concepto",
      why: "capacidad de vigilancia del sistema (F.6.2), no el nivel WATCH",
    },
  ],
  "/src/dashboard/timelineMarks.ts": [
    {
      text: "posvuelo: mark(",
      kind: "otro-concepto",
      why: "clave del `tipo` de hecho de la crónica (`app/timeline.py`), como las de la API: no la fase de la misión",
    },
  ],
  // El panel de vigilancia vive en su fichero desde el tablero por secciones (2026-11-07).
  "/src/dashboard/MonitoringBasis.tsx": [
    {
      text: 'aria-label="Capacidad de vigilancia"',
      kind: "otro-concepto",
      why: "capacidad de vigilancia del sistema (F.6.2), no el nivel WATCH",
    },
    {
      text: 'Vigilancia{" "}',
      kind: "otro-concepto",
      why: "titulo del panel de capacidad de vigilancia (F.6.2), no el nivel WATCH",
    },
  ],
  "/src/dashboard/CrewConsole.tsx": [
    {
      text: "Ningún dominio fuera de lo nominal.",
      kind: "pendiente",
      why: "frase de la interfaz para la lista de alertas vacia: nombra el nivel",
    },
  ],
  "/src/habitat/HypothesisReview.tsx": [
    {
      text: "siguen fuera de nominal",
      kind: "pendiente",
      why: "frase de la interfaz sobre la recuperacion de una hipotesis: nombra el nivel",
    },
    {
      text: "sigue fuera de nominal",
      kind: "pendiente",
      why: "frase de la interfaz sobre la recuperacion de una hipotesis: nombra el nivel",
    },
  ],
  "/src/ground/RecoveryPanel.tsx": [
    {
      text: "Recuperación posvuelo",
      kind: "otro-concepto",
      why: "titulo del informe de recuperacion tras el vuelo, no la fase de la mision en curso",
    },
    {
      text: 'tr("Prevuelo", "Preflight")',
      kind: "otro-concepto",
      why: "columna de las tomas de antes del vuelo en ese informe, no la fase",
    },
    {
      text: 'tr("Posvuelo (días tras el regreso)", "Postflight (days after return)")',
      kind: "otro-concepto",
      why: "columna de las tomas de despues del vuelo en ese informe, no la fase",
    },
  ],
};

function withoutComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (block) => block.replace(/[^\n]/g, " "))
    .replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");
}

/**
 * El inglés de un `tr(castellano, inglés)` (`lib/i18n.ts`): el segundo argumento, cuando es un
 * literal. Las palabras castellanas de arriba no se buscan en él —«nominal» también es una palabra
 * inglesa corriente—, pero un literal inglés que sea, entero, una palabra de nivel es la misma
 * tabla propia escrita en otro idioma, y se caza.
 */
const LITERAL = [/"(?:[^"\\\n]|\\.)*"/, /'(?:[^'\\\n]|\\.)*'/, /`(?:[^`\\]|\\.)*`/].map((r) => r.source).join("|");
const TR_ENGLISH = new RegExp(`(\\btr\\(\\s*(?:${LITERAL})\\s*,\\s*)(${LITERAL})`, "g");
const ENGLISH_LEVEL = /^\s*(nominal|watch|caution|concern|critical)\s*$/i;

/** Lo que queda de un fichero tras quitar comentarios, excepciones declaradas, claves e inglés. */
function scannable(path: string, source: string): string {
  let code = withoutComments(source.replace(/\r\n/g, "\n"));
  for (const item of DECLARED[path] ?? []) code = code.split(item.text).join(" ");
  code = code.replace(TR_ENGLISH, (_whole: string, head: string, english: string) => {
    // Una palabra de nivel inglesa deja en su sitio una castellana, que el buscador encuentra.
    const kept = ENGLISH_LEVEL.test(english.slice(1, -1)) ? '"vigilancia"' : '""';
    return head + kept + "\n".repeat(english.split("\n").length - 1);
  });
  return code.replace(API_KEYS, " ");
}

function findings(path: string, source: string): string[] {
  const found: string[] = [];
  scannable(path, source)
    .split("\n")
    .forEach((line, index) => {
      for (const [what, pattern] of Object.entries(FORBIDDEN)) {
        for (const match of line.match(pattern) ?? []) {
          found.push(`${path}:${index + 1}: «${match}» (${what})`);
        }
      }
    });
  return found;
}

const SOURCES = Object.entries(
  import.meta.glob("/src/**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }),
)
  .map(([path, source]) => [path, String(source)] as const)
  .filter(([path]) => !/\.test\.tsx?$/.test(path));

describe("el buscador de palabras", () => {
  it("lee las fuentes de la interfaz, no una lista vacia", () => {
    const paths = SOURCES.map(([path]) => path);
    expect(paths.length).toBeGreaterThan(50);
    for (const expected of ["/src/lib/levels.ts", "/src/dashboard/CrewConsole.tsx", "/src/App.tsx"]) {
      expect(paths).toContain(expected);
    }
  });

  it("caza una palabra en un literal y en el texto de un componente, con o sin acento", () => {
    expect(findings("/x.ts", 'const label = "Precaución";')).toHaveLength(1);
    expect(findings("/x.ts", "const label = 'precaucion';")).toHaveLength(1);
    expect(findings("/x.tsx", "<li>fase estable</li>")).toHaveLength(1);
    expect(findings("/x.tsx", '{up ? "↗ empeorando" : "↘ recuperándose"}')).toHaveLength(2);
    expect(findings("/x.ts", 'const word = "Nominal";')).toHaveLength(1);
  });

  it("no busca las palabras castellanas en el inglés de un `tr`, pero sí una palabra de nivel inglesa", () => {
    expect(findings("/x.tsx", '<p>{tr("Sin cambios", "Nothing outside nominal limits")}</p>')).toEqual([]);
    expect(findings("/x.ts", 'const a = tr("fuera de rango",\n  "critical limit reached");')).toEqual([]);
    expect(findings("/x.ts", 'const a = tr("Atención", "Caution");')).toHaveLength(1);
    expect(findings("/x.ts", "const a = tr('Atención', 'Watch');")).toHaveLength(1);
    // El castellano de un `tr` se sigue leyendo como siempre.
    expect(findings("/x.ts", 'const a = tr("Precaución", "Heads up");')).toHaveLength(1);
  });

  it("no cuenta los comentarios ni las claves de la API", () => {
    expect(findings("/x.ts", "// el amarillo de precaucion\nconst a = 1;")).toEqual([]);
    expect(findings("/x.ts", "/** nunca nominal:\n * ni critico */\nconst a = 1;")).toEqual([]);
    expect(findings("/x.tsx", "{/* fase estable */}")).toEqual([]);
    expect(findings("/x.ts", 'if (level === "nominal") return { nominal: 1 };')).toEqual([]);
    // Una URL dentro de un literal no es un comentario: lo que sigue en la linea se lee.
    expect(findings("/x.ts", 'const a = ["http://x", "Vigilancia"];')).toHaveLength(1);
  });
});

describe("ninguna fuente de la interfaz escribe una palabra de nivel, fase o trayectoria", () => {
  it("no hay ninguna fuera de las declaradas", () => {
    expect(SOURCES.flatMap(([path, source]) => findings(path, source))).toEqual([]);
  });

  it("cada excepcion declarada sigue existiendo y tiene motivo", () => {
    const sources = new Map(SOURCES);
    for (const [path, items] of Object.entries(DECLARED)) {
      const source = sources.get(path);
      expect(source, `${path} no existe`).toBeDefined();
      for (const item of items) {
        expect(source?.includes(item.text), `${path}: ya no contiene «${item.text}»`).toBe(true);
        expect(item.why.trim()).not.toBe("");
      }
    }
  });

  it("una excepcion declarada se necesita: sin ella, la prueba cazaria algo", () => {
    for (const [path, items] of Object.entries(DECLARED)) {
      for (const item of items) {
        expect(findings("/sin-excepciones", item.text), `${path}: «${item.text}»`).not.toEqual([]);
      }
    }
  });
});
