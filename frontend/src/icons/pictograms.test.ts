import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textLines, textNodes } from "../advisor/visibleText";
import { Mark } from "../components/Mark";
import { Pictogram } from "./Pictogram";
import { UI_PICTOGRAMS } from "../lib/uiMarks";
import { PICTOGRAMS, SETS, isPictogramName, pictogram, pictogramNames } from "./registry";
import type { PictogramDef } from "./types";

/**
 * Las reglas de los pictogramas (`compliance/hmi-state-of-the-art.md` §5.32), como prueba.
 *
 * Un pictograma es geometria sin color ni significado propio: el color lo pone la clase `c-*` del
 * elemento que lo contiene y el significado la palabra de al lado. Aqui se comprueba que cada
 * conjunto cumple eso (nombre por el dibujo, primitivas acotadas, sin estilos), que el componente
 * emite exactamente lo prometido, que nadie escribe `<svg>` fuera de `icons/` y que todo nombre
 * usado en la interfaz existe.
 */

const NAME = /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/;

/**
 * Palabras de nivel, fase, trayectoria o color: un nombre que las lleve nombra un significado.
 * Se buscan al principio de un tramo del kebab-case (`red-dot`, `dot-red`), no como subcadena:
 * `bordered-square` o `centered-dot` describen un dibujo.
 */
const MEANING =
  /(^|-)(nominal|watch|concern|critical|cr[ií]tico|vigilancia|precauci|preocupaci|prevuelo|adaptaci|regreso|posvuelo|recuper|empeor|red|yellow|blue|gray|cyan|magenta|green|rojo|amarillo|azul|gris|cian|verde)/;

const KINDS = ["path", "circle", "rect", "line", "polygon", "polyline"];
const PATH_D = /^[MmLlHhVvCcSsQqTtAaZz0-9 ,.\-]+$/;
const POINTS = /^[0-9 ,.\-]+$/;

const render = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element);

/**
 * Parejas de dibujos casi iguales a proposito, con su motivo: la prueba de «casi iguales» las deja
 * pasar. La clave son los dos nombres en orden alfabetico, unidos por « ~ ».
 */
const NEAR_ALLOWED: Readonly<Record<string, string>> = {
  "circle-half-right ~ dot-half":
    "la mitad rellena a la derecha (un grado de las hipotesis de Tierra) y a la izquierda (inferido): " +
    "difieren solo en el sentido del arco, que es todo el dibujo; anotado en §5.33.12 para revisarlo",
};

describe("el registro", () => {
  it("tiene pictogramas, y los conjuntos del nucleo no estan vacios", () => {
    expect(pictogramNames().length).toBeGreaterThan(20);
    expect(Object.keys(SETS.shapes).length).toBeGreaterThan(0);
    expect(Object.keys(SETS.common).length).toBeGreaterThan(0);
    expect(Object.keys(SETS.provenance).length).toBeGreaterThan(0);
  });

  it("ningun nombre se repite entre dos conjuntos", () => {
    const seen = new Map<string, string>();
    for (const [setName, set] of Object.entries(SETS)) {
      for (const name of Object.keys(set)) {
        expect(seen.has(name), `«${name}» esta en ${seen.get(name)} y en ${setName}`).toBe(false);
        seen.set(name, setName);
      }
    }
    expect(seen.size).toBe(pictogramNames().length);
  });

  it("cada nombre va en kebab-case y describe el dibujo, no un nivel, una fase ni un color", () => {
    for (const name of pictogramNames()) {
      expect(name, name).toMatch(NAME);
      expect(MEANING.test(name), `«${name}» nombra un significado`).toBe(false);
    }
    // La regla caza la palabra al principio de un tramo, y deja en paz a quien la contiene.
    for (const bad of ["red-dot", "dot-red", "nominal-ring", "triangle-critico", "verde"]) {
      expect(MEANING.test(bad), bad).toBe(true);
    }
    for (const fine of ["bordered-square", "centered-dot", "shape-triangle", "bed"]) {
      expect(MEANING.test(fine), fine).toBe(false);
    }
  });

  it("solo las seis primitivas, con numeros finitos dentro de la rejilla", () => {
    for (const [name, def] of Object.entries(PICTOGRAMS) as [string, PictogramDef][]) {
      expect(def.elements.length, name).toBeGreaterThan(0);
      if (def.strokeWidth !== undefined) expect(def.strokeWidth).toBeGreaterThan(0);
      for (const element of def.elements) {
        expect(KINDS, `${name}: ${element.kind}`).toContain(element.kind);
        for (const [key, value] of Object.entries(element)) {
          if (typeof value === "number") {
            expect(Number.isFinite(value), `${name}.${key}`).toBe(true);
            expect(value, `${name}.${key}`).toBeGreaterThanOrEqual(-1);
            expect(value, `${name}.${key}`).toBeLessThanOrEqual(25);
          }
        }
        if (element.kind === "path") expect(element.d, name).toMatch(PATH_D);
        if (element.kind === "polygon" || element.kind === "polyline") {
          expect(element.points, name).toMatch(POINTS);
        }
      }
    }
  });

  it("ningun pictograma lleva color ni estilo propio", () => {
    for (const [name, def] of Object.entries(PICTOGRAMS)) {
      const text = JSON.stringify(def);
      expect(text, name).not.toMatch(/#|rgb|url\(|style/);
    }
  });

  it("dos nombres no comparten el mismo dibujo", () => {
    const drawings = new Map<string, string>();
    for (const [name, def] of Object.entries(PICTOGRAMS) as [string, PictogramDef][]) {
      const key = JSON.stringify(def.elements);
      expect(drawings.has(key), `«${name}» dibuja lo mismo que «${drawings.get(key)}»`).toBe(false);
      drawings.set(key, name);
    }
  });

  it("dos dibujos de la misma hechura no difieren solo en unas unidades: a 14 px serian el mismo", () => {
    // La prueba de arriba solo caza dos dibujos identicos. Esta caza los casi iguales: mismas
    // primitivas en el mismo orden, mismos comandos de trazo y mismos rellenos, con todas las
    // cifras a NEAR unidades o menos (una unidad de la rejilla es 0,6 px a 14 px). Asi estaban
    // `tablet-dot` (la tableta de la PVT) y `ridge-isolation` (el aislamiento del RIDGE): un
    // rectangulo de 16 × 18 y un cuadrado de 18 con el mismo punto (limpieza, §5.33.12).
    const NEAR = 2;
    const shape = (def: PictogramDef): { form: string; numbers: number[] } => {
      const numbers: number[] = [];
      const parts = def.elements.map((element) =>
        Object.entries(element)
          .map(([key, value]) => {
            if (typeof value === "number") {
              numbers.push(value);
              return key;
            }
            if (typeof value === "string" && key !== "kind") {
              for (const match of value.matchAll(/-?\d*\.?\d+/g)) numbers.push(Number(match[0]));
              return `${key}:${value.replace(/-?\d*\.?\d+/g, "#").replace(/[\s,]+/g, "")}`;
            }
            return `${key}=${String(value)}`;
          })
          .join("|"),
      );
      return { form: `${parts.join(";")}|${def.strokeWidth ?? ""}`, numbers };
    };
    const all = Object.entries(PICTOGRAMS) as [string, PictogramDef][];
    const near: string[] = [];
    for (let i = 0; i < all.length; i += 1) {
      for (let j = i + 1; j < all.length; j += 1) {
        const [nameA, defA] = all[i]!;
        const [nameB, defB] = all[j]!;
        const a = shape(defA);
        const b = shape(defB);
        if (a.form !== b.form || a.numbers.length !== b.numbers.length) continue;
        const gap = Math.max(...a.numbers.map((value, k) => Math.abs(value - (b.numbers[k] ?? Infinity))));
        const pair = [nameA, nameB].sort().join(" ~ ");
        if (gap <= NEAR && !Object.hasOwn(NEAR_ALLOWED, pair)) near.push(`${pair} (a ${gap} unidades)`);
      }
    }
    expect(near).toEqual([]);
    // Y cada excepcion declarada sigue existiendo: si un dibujo cambia, la excepcion sobra.
    for (const pair of Object.keys(NEAR_ALLOWED)) {
      for (const name of pair.split(" ~ ")) expect(isPictogramName(name), pair).toBe(true);
    }
  });

  it("un nombre desconocido falla en vez de pintar otro", () => {
    expect(() => pictogram("nope")).toThrow(RangeError);
    expect(() => pictogram("nope")).toThrow(/pictograma desconocido: nope/);
    expect(isPictogramName("nope")).toBe(false);
    expect(isPictogramName("shape-circle")).toBe(true);
    // Las propiedades heredadas de Object no son pictogramas.
    expect(isPictogramName("toString")).toBe(false);
  });
});

describe("el componente", () => {
  it("emite exactamente los atributos prometidos y nada de texto", () => {
    const html = render(createElement(Pictogram, { name: "shape-circle" }));
    expect(html).toContain(
      '<svg class="pictogram" viewBox="0 0 24 24" width="1em" height="1em" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" data-pictogram="shape-circle">',
    );
    expect(html).toContain('<circle cx="12" cy="12" r="8"></circle>');
    expect(textNodes(html)).toEqual([]);
    expect(html).not.toContain("<title");
    expect(html).not.toContain("<desc");
  });

  it("la clase extra se anade a `pictogram`: asi parpadea solo el dibujo", () => {
    const html = render(createElement(Pictogram, { name: "shape-square", className: "flash" }));
    expect(html).toContain('class="pictogram flash"');
  });

  it("relleno con currentColor cuando el dibujo lo pide, y a trazos cuando es un anillo punteado", () => {
    expect(render(createElement(Pictogram, { name: "shape-square" }))).toContain('fill="currentColor"');
    expect(render(createElement(Pictogram, { name: "shape-circle" }))).not.toContain('fill="currentColor"');
    const dotted = render(createElement(Pictogram, { name: "ring-dotted" }));
    expect(dotted).toContain("stroke-dasharray=");
    expect(render(createElement(Pictogram, { name: "shape-circle" }))).not.toContain("stroke-dasharray");
  });

  it("todos los pictogramas se pintan sin fallar", () => {
    for (const name of pictogramNames()) {
      expect(render(createElement(Pictogram, { name }))).toContain(`data-pictogram="${name}"`);
    }
  });
});

const SOURCES = Object.entries(
  import.meta.glob("/src/**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }),
)
  .map(([path, source]) => [path, String(source)] as const)
  .filter(([path]) => !/\.test\.tsx?$/.test(path));

/**
 * El tablero «Inicio» (la maqueta de 2026-11-06, consola real por decision del usuario del
 * 2026-11-07): sus dibujos de datos (anillo y curvas, `HomeCharts`), su adorno (planetas, Tierra,
 * astronauta, estrellas, `HomeArt`) y el cuerpo de la maqueta (`BodyArt`, el varón y su variante femenina) se dibujan a mano.
 * No son pictogramas, y viven en sus tres ficheros para que todo trazo este localizado.
 */
const HOME_DRAWINGS = ["/src/dashboard/HomeCharts.tsx", "/src/dashboard/HomeArt.tsx", "/src/dashboard/BodyArt.tsx"];

/**
 * El calibre de la ecografia dibuja medidas sobre la imagen: no es un pictograma. La silueta
 * corporal (`icons/Silhouette.tsx`) es un dibujo propio con su lienzo de 200×480, no un
 * pictograma de 24×24 que acompane a una palabra: vive en `icons/` para que todo trazo este
 * aqui, y no entra en el registro.
 */
const SVG_ALLOWED = [
  "/src/icons/Pictogram.tsx",
  "/src/icons/Silhouette.tsx",
  "/src/imaging/UltrasoundPanel.tsx",
  ...HOME_DRAWINGS,
];

describe("en las fuentes de la interfaz", () => {
  it("todo nombre de pictograma escrito en un componente o una tabla existe", () => {
    const patterns = [
      /<Pictogram\b[^>]*?\bname="([^"]+)"/g,
      /<Mark\b[^>]*?\bpictogram="([^"]+)"/g,
      /\bpictogram:\s*"([^"]+)"/g,
    ];
    let found = 0;
    for (const [path, source] of SOURCES) {
      for (const pattern of patterns) {
        for (const match of source.matchAll(pattern)) {
          found += 1;
          const name = match[1] ?? "";
          expect(isPictogramName(name), `${path}: «${name}»`).toBe(true);
        }
      }
    }
    expect(found).toBeGreaterThan(0);
  });

  it("`<svg` solo se escribe en el componente y en el calibre de la ecografia", () => {
    // Un `<svg` de JSX va seguido de un atributo (espacio o salto de linea); el que menciona
    // `visibleText.ts` para quitarlo del texto es una expresion regular, no un elemento.
    const writers = SOURCES.filter(([, source]) => /<svg\s/.test(source)).map(([path]) => path);
    expect(writers.sort()).toEqual([...SVG_ALLOWED].sort());
  });

  it("ningun trazo (<path, <polygon, <polyline) fuera de icons/, salvo el calibre", () => {
    for (const [path, source] of SOURCES) {
      if (path.startsWith("/src/icons/") || path === "/src/imaging/UltrasoundPanel.tsx" || HOME_DRAWINGS.includes(path)) continue;
      expect(/<(path|polygon|polyline)\b/.test(source), path).toBe(false);
    }
  });

  it("icons/ no importa la paleta: el color no es suyo", () => {
    for (const [path, source] of SOURCES) {
      if (!path.startsWith("/src/icons/")) continue;
      expect(/palette/.test(source), path).toBe(false);
    }
  });

  it("los conjuntos no llevan texto para la tripulacion", () => {
    for (const [path, source] of SOURCES) {
      if (!path.startsWith("/src/icons/sets/")) continue;
      const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
      expect(/[áéíóúñÁÉÍÓÚÑ¿¡]/.test(code), `${path} lleva texto en español fuera de un comentario`).toBe(false);
    }
  });
});

type SetName = keyof typeof SETS;
type CoreSet = "shapes" | "common" | "provenance" | "domains" | "indicators" | "ui";

/**
 * Conjuntos del nucleo: sus dibujos los usa cualquier area. Los demas son de un area, y cada uno
 * de sus dibujos solo se usa desde su casa (`HOME`); el que necesita una segunda area se sube a
 * `common`, porque un dibujo que comparten dos areas no vive en ninguna de las dos. Al fusionar
 * las once unidades del rediseño, veintiseis nombres estaban dibujados en dos o mas conjuntos.
 * `ui` es el mobiliario de la interfaz (titulos, plegables, mandos, cabeceras; `lib/uiMarks.ts`):
 * del nucleo desde la segunda pasada (2026-10-21).
 */
const CORE_SETS: readonly CoreSet[] = ["shapes", "common", "provenance", "domains", "indicators", "ui"];

/** La casa de cada conjunto de area: carpetas de `src/`; los ficheros sueltos de `src/` son «app». */
const HOME: Record<Exclude<SetName, CoreSet>, readonly string[]> = {
  timeline: ["dashboard", "lib"],
  mission: ["dashboard"],
  sources: ["dashboard"],
  habitat: ["habitat"],
  advisor: ["advisor"],
  evidence: ["evidence"],
  ground: ["ground"],
  diary: ["diary"],
  pvt: ["pvt"],
  radiation: ["radiation"],
  pain: ["pain"],
  imaging: ["imaging"],
  volumes: ["volumes"],
  reports: ["reports"],
  shell: ["app", "components"],
};

describe("un dibujo de area solo se usa desde su area", () => {
  const areaOf = (path: string): string => /^\/src\/([^/]+)\//.exec(path)?.[1] ?? "app";
  // `lib/api.ts` son los tipos de la API: nombran valores del backend («burst» es una regla de
  // alerta), nunca pictogramas, y la prueba de abajo lo comprueba.
  const usable = SOURCES.filter(([path]) => !path.startsWith("/src/icons/") && path !== "/src/lib/api.ts");
  /**
   * Un nombre de pictograma se escribe siempre entrecomillado, tambien como clave de un objeto
   * (`"bell": [...]`, no `bell: [...]`): es lo que cuenta esta guarda. Una clave sin comillas no
   * se puede distinguir de otra cosa que se llame igual (`clock: Clock` en la sesion de la PVT).
   */
  const uses = (source: string, name: string): boolean => source.includes(`"${name}"`);
  /**
   * La tabla de signos (`lib/uiMarks.ts`) nombra a proposito dibujos de toda la interfaz: no
   * cuenta como un area que los use, o cualquier dibujo de `common` pasaria la regla de abajo
   * solo por estar en ella.
   */
  const counted = usable.filter(([path]) => path !== "/src/lib/uiMarks.ts");
  const areasUsing = (name: string): string[] => [
    ...new Set(counted.filter(([, source]) => uses(source, name)).map(([path]) => areaOf(path))),
  ];

  it("lib/api.ts no nombra pictogramas: por eso queda fuera del recuento", () => {
    const api = SOURCES.find(([path]) => path === "/src/lib/api.ts");
    expect(api).toBeDefined();
    expect(api?.[1]).not.toMatch(/icons/);
  });

  it("cada conjunto es del nucleo o tiene casa", () => {
    expect([...CORE_SETS, ...Object.keys(HOME)].sort()).toEqual(Object.keys(SETS).sort());
  });

  it("ningun dibujo de un conjunto de area se usa desde otra: el compartido vive en common", () => {
    const strays: string[] = [];
    for (const [setName, home] of Object.entries(HOME) as [Exclude<SetName, CoreSet>, readonly string[]][]) {
      for (const name of Object.keys(SETS[setName])) {
        for (const [path, source] of usable) {
          if (uses(source, name) && !home.includes(areaOf(path))) {
            strays.push(`«${name}» (${setName}) se usa en ${path}`);
          }
        }
      }
    }
    expect(strays).toEqual([]);
  });

  it("y cada dibujo de common lo usan dos o mas areas: si solo lo usa una, es de esa area", () => {
    // Salvo el que es signo de un concepto de la interfaz (`UI_PICTOGRAMS`): ese es compartido por
    // definicion, aunque hoy lo pinte un area sola (segunda pasada, 2026-10-21).
    const signs = new Set<string>(Object.values(UI_PICTOGRAMS));
    for (const name of Object.keys(SETS.common)) {
      if (signs.has(name)) continue;
      const areas = areasUsing(name);
      expect(areas.length, `«${name}» solo lo usa ${areas.join(", ") || "nadie"}`).toBeGreaterThanOrEqual(2);
    }
  });

  it("las tablas con el nombre como clave lo escriben entrecomillado", () => {
    // La unica tabla asi hoy; una clave sin comillas escaparia a las dos guardas de arriba.
    const ledger = usable.find(([path]) => path === "/src/ground/ledgerEntries.ts")?.[1] ?? "";
    expect(ledger).toContain('"bell": [');
    expect(ledger).not.toMatch(/^\s+[a-z][a-z0-9-]*:\s*\[/m);
  });
});

describe("el texto visible", () => {
  it("ignora el pictograma y no parte la linea de la palabra", () => {
    const html = render(
      createElement(
        "p",
        null,
        "Texto ",
        createElement(Mark, { pictogram: "shape-circle", children: "PALABRA" }),
        " más",
      ),
    );
    expect(textLines(html)).toEqual(["Texto PALABRA más"]);
    expect(textNodes(html)).toEqual(["Texto", "PALABRA", "más"]);
  });
});
