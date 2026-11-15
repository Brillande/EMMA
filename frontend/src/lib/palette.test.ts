import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  BACKGROUNDS,
  COMMAND_TEXT_TOKENS,
  HIGH_CONTRAST_MIN,
  HIGH_CONTRAST_TEXT_MIN,
  MIN_CONTRAST,
  MIN_NON_TEXT_CONTRAST,
  MIN_SIGNAL_DISTANCE,
  SIGNAL_TOKENS,
  TEXT_TOKENS,
  type Token,
  anatomy,
  applyPalette,
  contrast,
  cssVar,
  highContrast,
  palette,
  rgbDistance,
} from "./palette";

describe("NASA-STD-3001 Vol 2, F.5.10: contraste de 6:1 o mas", () => {
  for (const bg of BACKGROUNDS) {
    for (const fg of TEXT_TOKENS) {
      it(`${fg} sobre ${bg}`, () => {
        expect(contrast(palette[fg], palette[bg])).toBeGreaterThanOrEqual(MIN_CONTRAST);
      });
    }
  }

  for (const fg of COMMAND_TEXT_TOKENS) {
    it(`${fg} sobre el fondo de mando`, () => {
      expect(contrast(palette[fg], palette.command)).toBeGreaterThanOrEqual(MIN_CONTRAST);
    });
  }

  it("el texto principal alcanza el 10:1 preferido en todos los fondos", () => {
    for (const bg of BACKGROUNDS) {
      expect(contrast(palette.text, palette[bg])).toBeGreaterThanOrEqual(10);
    }
  });
});

/** Matiz en grados (0-360) de un color `#rrggbb`; `null` si es un gris puro. */
function hue(hex: string): number | null {
  const n = Number.parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255] as [number, number, number];
  const max = Math.max(r, g, b);
  const d = max - Math.min(r, g, b);
  if (d === 0) return null;
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return (h * 60 + 360) % 360;
}

describe("alto contraste (deslumbramiento): WCAG 1.4.6 y 1.4.11 sobre la tabla F.5-1", () => {
  for (const bg of BACKGROUNDS) {
    for (const fg of TEXT_TOKENS) {
      it(`${fg} sobre ${bg}: 7:1 o más`, () => {
        expect(contrast(highContrast[fg], highContrast[bg])).toBeGreaterThanOrEqual(HIGH_CONTRAST_MIN);
      });
    }
    it(`el texto principal sobre ${bg}: 12:1 o más`, () => {
      expect(contrast(highContrast.text, highContrast[bg])).toBeGreaterThanOrEqual(HIGH_CONTRAST_TEXT_MIN);
    });
    it(`los bordes se ven sobre ${bg}: 3:1 o más`, () => {
      expect(contrast(highContrast.line, highContrast[bg])).toBeGreaterThanOrEqual(MIN_NON_TEXT_CONTRAST);
    });
  }

  for (const fg of COMMAND_TEXT_TOKENS) {
    it(`${fg} sobre el fondo de mando: 7:1 o más`, () => {
      expect(contrast(highContrast[fg], highContrast.command)).toBeGreaterThanOrEqual(HIGH_CONTRAST_MIN);
    });
  }

  it("sube el contraste de cada pareja respecto a la paleta de siempre", () => {
    for (const bg of BACKGROUNDS) {
      for (const fg of TEXT_TOKENS) {
        expect(contrast(highContrast[fg], highContrast[bg]), `${fg}/${bg}`).toBeGreaterThan(
          contrast(palette[fg], palette[bg]),
        );
      }
    }
  });

  it("cada color con significado conserva su matiz: el mismo significado, el mismo color", () => {
    for (const token of SIGNAL_TOKENS) {
      const [was, now] = [hue(palette[token]), hue(highContrast[token])];
      expect(was === null, token).toBe(now === null);
      if (was === null || now === null) continue;
      const turn = Math.abs(was - now);
      expect(Math.min(turn, 360 - turn), token).toBeLessThanOrEqual(10);
    }
  });

  it("rojo, amarillo, azul, gris y cian siguen distintos, y el secundario no es el gris", () => {
    const meanings = [highContrast.red, highContrast.yellow, highContrast.blue, highContrast.gray, highContrast.cyan];
    expect(new Set(meanings).size).toBe(meanings.length);
    expect(highContrast.textSecondary).not.toBe(highContrast.gray);
  });

  it("ningún color anatómico se parece a una señal de alto contraste", () => {
    for (const [name, color] of Object.entries(anatomy)) {
      for (const signal of SIGNAL_TOKENS) {
        expect(rgbDistance(color, highContrast[signal]), `${name} ~ ${signal}`).toBeGreaterThanOrEqual(
          MIN_SIGNAL_DISTANCE,
        );
      }
    }
  });

  it("aplicarla cambia los valores y no los nombres", () => {
    const set = new Map<string, string>();
    const root = { style: { setProperty: (name: string, value: string) => set.set(name, value) } };
    applyPalette(root as unknown as HTMLElement, "highContrast");
    expect([...set.keys()].sort()).toEqual(Object.keys(palette).map((token) => cssVar(token as Token)).sort());
    expect(set.get("--c-bg")).toBe(highContrast.bg);
    applyPalette(root as unknown as HTMLElement);
    expect(set.get("--c-bg")).toBe(palette.bg);
  });
});

describe("la formula de contraste", () => {
  it("da 21:1 entre blanco y negro, y es simetrica", () => {
    expect(contrast("#FFFFFF", "#000000")).toBeCloseTo(21, 5);
    expect(contrast("#000000", "#FFFFFF")).toBeCloseTo(21, 5);
  });

  it("da 1:1 entre un color y si mismo", () => {
    expect(contrast(palette.cyan, palette.cyan)).toBeCloseTo(1, 5);
  });
});

describe("tabla F.5-1: cada significado tiene su propio color", () => {
  it("rojo, amarillo, azul, gris y cian son distintos entre si", () => {
    const meanings = [palette.red, palette.yellow, palette.blue, palette.gray, palette.cyan];
    expect(new Set(meanings).size).toBe(meanings.length);
  });

  it("el texto secundario no es el gris de 'no disponible'", () => {
    expect(palette.textSecondary).not.toBe(palette.gray);
  });
});

/**
 * Todas las hojas de la interfaz: la de siempre, la concha de la maqueta (`consoleShell.css`), las
 * piezas de «Inicio» (`referenceDashboard.css`) y las secciones adaptadas (`shell/*.css`, una por
 * unidad de trabajo del 2026-11-07). El adorno de la maqueta es una desviación declarada de F.5.10,
 * pero sus colores siguen saliendo de la paleta: mezclas con `color-mix`, nunca un valor a mano.
 */
const SHEETS: [string, string][] = [
  ["styles.css", readFileSync(fileURLToPath(new URL("../styles.css", import.meta.url)), "utf8")],
  ["consoleShell.css", readFileSync(fileURLToPath(new URL("../consoleShell.css", import.meta.url)), "utf8")],
  [
    "dashboard/referenceDashboard.css",
    readFileSync(fileURLToPath(new URL("../dashboard/referenceDashboard.css", import.meta.url)), "utf8"),
  ],
  // La sección «Radiación» con el estilo de «Inicio» (2026-11-14).
  [
    "radiation/radiationBoard.css",
    readFileSync(fileURLToPath(new URL("../radiation/radiationBoard.css", import.meta.url)), "utf8"),
  ],
  // «Reservas» y «Diagnóstico integrado» de «Inicio» (lote «reservas», 2026-11-14).
  [
    "dashboard/homeReserves.css",
    readFileSync(fileURLToPath(new URL("../dashboard/homeReserves.css", import.meta.url)), "utf8"),
  ],
  [
    "dashboard/homeDistance.css",
    readFileSync(fileURLToPath(new URL("../dashboard/homeDistance.css", import.meta.url)), "utf8"),
  ],
  [
    "dashboard/nodesOutlook.css",
    readFileSync(fileURLToPath(new URL("../dashboard/nodesOutlook.css", import.meta.url)), "utf8"),
  ],
  [
    "dashboard/nodesBoard.css",
    readFileSync(fileURLToPath(new URL("../dashboard/nodesBoard.css", import.meta.url)), "utf8"),
  ],
  [
    "dashboard/homeDiagnostics.css",
    readFileSync(fileURLToPath(new URL("../dashboard/homeDiagnostics.css", import.meta.url)), "utf8"),
  ],
  [
    "gravity/gravityBoard.css",
    readFileSync(fileURLToPath(new URL("../gravity/gravityBoard.css", import.meta.url)), "utf8"),
  ],
  ...Object.entries(import.meta.glob("/src/shell/*.css", { query: "?raw", import: "default", eager: true })).map(
    ([path, source]) => [path, String(source)] as [string, string],
  ),
];

describe.each(SHEETS)("la hoja %s solo usa colores de la paleta", (_sheet, css) => {
  it("no hay ningun color escrito a mano", () => {
    const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, "");
    expect(withoutComments).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/);
  });

  it("cada variable de color que usa existe en la paleta", () => {
    const known = new Set(Object.keys(palette).map((token) => cssVar(token as Token)));
    const used = new Set(css.match(/--c-[a-z-]+/g) ?? []);
    for (const name of used) {
      expect(known.has(name), name).toBe(true);
    }
  });
});

describe("colores de anatomía: contenido de imagen, nunca señales", () => {
  it("ningún color anatómico se parece a un color con significado (F.5-1, F.5-2)", () => {
    for (const [name, color] of Object.entries(anatomy)) {
      for (const signal of SIGNAL_TOKENS) {
        expect(
          rgbDistance(color, palette[signal]),
          `${name} se parece a ${signal}`,
        ).toBeGreaterThanOrEqual(MIN_SIGNAL_DISTANCE);
      }
    }
  });

  it("solo se usan dentro de los lienzos 3D", () => {
    const files = import.meta.glob("../**/*.tsx", { query: "?raw", import: "default", eager: true });
    const users = Object.entries(files)
      .filter(([, source]) => /\banatomy\.\w+/.test(String(source)) && /from "\.\.\/lib\/palette"/.test(String(source)))
      .map(([path]) => path);
    for (const path of users) {
      expect(path, `${path} usa colores anatómicos fuera de un lienzo 3D`).toMatch(
        /\/(volumes|anatomy|pain)\//,
      );
    }
  });
});
