/**
 * Ninguna fuente de la interfaz escribe ya un glifo de texto: la forma es un pictograma SVG.
 *
 * Por que existe: el rediseño pictografico (§5.32 del estado del arte) paso las formas de la
 * interfaz (○ ◇ △ ■, ● ◐ ▷, ◌, ⊘ ✕, ✓, flechas…) de caracteres a SVG propios, porque IBM Plex
 * (subconjunto latino) no cubre esos bloques y cada sistema operativo los dibujaba con otra fuente.
 * Once unidades migraron cada una su area; esta prueba es el barrido final y la guardia: lee todas
 * las fuentes de `src/` (fuera de `icons/`, que dibuja, y de las pruebas, que los nombran) y falla
 * si una escribe un caracter de los bloques de flechas, operadores, tecnicos, recuadros, formas,
 * simbolos, dingbats o flechas suplementarias (U+2190–U+2BFF), la viñeta o un emoji, fuera de un
 * comentario, tambien escrito como escape (`△`, `\u{25B3}`) o como entidad HTML en JSX
 * (`&#x25B3;`, `&#9651;`). Lo que queda escrito a proposito esta en `DECLARED`, cada cosa con su
 * motivo, y una excepcion que ya no hace falta tambien hace fallar la prueba.
 *
 * Fuera quedan la raya (—), el semirraya (–), los puntos suspensivos (…) y el punto medio (·),
 * que IBM Plex si dibuja y que son puntuacion, no una forma con significado. Los «≤ ≥» que llegan
 * del backend dentro de un texto no estan en el fuente y no cuentan; los dos que si lo estan van
 * declarados.
 */

import { describe, expect, it } from "vitest";

/**
 * El bloque entero de flechas, operadores, tecnicos, recuadros, formas, simbolos, dingbats y
 * flechas suplementarias (U+2190–U+2BFF), la viñeta (•) y todo pictograma de emoji.
 */
const TEXT_GLYPH = /[•←-⯿]|\p{Extended_Pictographic}/u;

/**
 * Un caracter escrito sin escribirlo: escape de JavaScript (`\uXXXX`, `\u{X…}`) o entidad
 * numerica de HTML en JSX (`&#xHEX;`, `&#DEC;`). Se decodifica y se mira igual que el caracter.
 */
const ESCAPE = /\\u\{([0-9a-fA-F]{1,6})\}|\\u([0-9a-fA-F]{4})|&#x([0-9a-fA-F]{1,6});|&#([0-9]{1,7});/g;

function decoded(code: string): string {
  return code.replace(ESCAPE, (_, braced: string | undefined, plain: string | undefined, hex: string | undefined, dec: string | undefined) => {
    const point = braced !== undefined || plain !== undefined || hex !== undefined
      ? Number.parseInt(braced ?? plain ?? hex ?? "0", 16)
      : Number.parseInt(dec ?? "0", 10);
    return point <= 0x10ffff ? String.fromCodePoint(point) : "";
  });
}

interface Declared {
  text: string;
  why: string;
}

const DECLARED: Record<string, Declared[]> = {
  "/src/About.tsx": [
    {
      text: "(© 2026 la autora de Polaris",
      why: "el signo de copyright del aviso de licencia (AGPL §5a): puntuacion legal, no una forma de estado; IBM Plex lo dibuja (U+00A9)",
    },
  ],
  "/src/habitat/flow.ts": [
    {
      text: "`≤ ${formatNumber(high, decimalsFor(high))}`",
      why: "el operador de un limite numerico sin cota inferior, delante de la cifra: no es una forma de estado, y sustituirlo exigiria redactar texto nuevo («como maximo»)",
    },
    {
      text: "`≥ ${formatNumber(low ?? 0, decimalsFor(low ?? 0))}`",
      why: "el operador de un limite numerico sin cota superior, delante de la cifra: idem",
    },
  ],
};

/**
 * Sin comentarios de bloque ni de linea, conservando los saltos de linea para que el `path:linea`
 * de un hallazgo apunte a la linea del fichero. Un `//` solo se recorta si lo precede un espacio
 * (o el principio de la linea) y no hay ninguna comilla antes en esa linea: asi no se come lo que
 * sigue a una URL o a un `//` dentro de una cadena.
 */
function withoutComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (block) => block.replace(/[^\n]/g, " "))
    .replace(/^([^"'`\n]*?)\s\/\/.*$/gm, "$1")
    .replace(/^\s*\/\/.*$/gm, "");
}

/** Lo que queda de un fichero tras quitar comentarios y excepciones declaradas, con los escapes decodificados. */
function scannable(path: string, source: string): string {
  let code = withoutComments(source.replace(/\r\n/g, "\n"));
  for (const item of DECLARED[path] ?? []) code = code.split(item.text).join(" ");
  return decoded(code);
}

function findings(path: string, source: string): string[] {
  const found: string[] = [];
  scannable(path, source)
    .split("\n")
    .forEach((line, index) => {
      const hit = TEXT_GLYPH.exec(line);
      if (hit !== null) found.push(`${path}:${index + 1}: «${hit[0]}»`);
    });
  return found;
}

const SOURCES = Object.entries(
  import.meta.glob("/src/**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }),
)
  .map(([path, source]) => [path, String(source)] as const)
  .filter(([path]) => !/\.test\.tsx?$/.test(path) && !path.startsWith("/src/icons/"));

describe("el barrido de glifos", () => {
  it("lee las fuentes de la interfaz, sin icons/ ni pruebas", () => {
    const paths = SOURCES.map(([path]) => path);
    expect(paths.length).toBeGreaterThan(50);
    for (const expected of ["/src/App.tsx", "/src/ground/GroundConsole.tsx", "/src/dashboard/CrewConsole.tsx"]) {
      expect(paths).toContain(expected);
    }
    expect(paths.some((path) => path.startsWith("/src/icons/"))).toBe(false);
  });

  it("caza un glifo en codigo, tambien escapado o como entidad, y deja en paz los comentarios y lo que sigue a una comilla", () => {
    expect(findings("/x.ts", 'const a = "⏳ en tránsito";')).toHaveLength(1);
    expect(findings("/x.tsx", "<span>⟶</span>")).toHaveLength(1);
    expect(findings("/x.ts", '"• punto"')).toHaveLength(1);
    expect(findings("/x.ts", 'const a = "\\u25B3";')).toHaveLength(1);
    expect(findings("/x.ts", 'const a = "\\u{25B3}";')).toHaveLength(1);
    expect(findings("/x.tsx", "<span>&#x25B3; fuera de rango</span>")).toHaveLength(1);
    expect(findings("/x.tsx", "<span>&#9651; fuera de rango</span>")).toHaveLength(1);
    expect(findings("/x.ts", 'const a = "— rango · referencia… 3–5 \\u00e9 &#233;";')).toEqual([]);
    expect(findings("/x.ts", "// ◌ comentario\nconst a = 1; // ▌\n")).toEqual([]);
    expect(findings("/x.ts", 'const u = "https://x"; // ◌\n')).toHaveLength(1);
    expect(findings("/x.tsx", "{/* ◇ */}\n")).toEqual([]);
  });

  it("la linea del hallazgo es la del fichero, tambien tras un comentario de bloque de varias lineas", () => {
    expect(findings("/x.ts", "/**\n * cabecera\n */\nconst a = 1;\nconst b = \"△\";\n")).toEqual(["/x.ts:5: «△»"]);
  });
});

describe("ninguna fuente de la interfaz escribe un glifo de texto", () => {
  it("no hay ninguno fuera de los declarados", () => {
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
