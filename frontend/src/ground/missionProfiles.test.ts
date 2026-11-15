import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textNodes } from "../advisor/visibleText";
import { aspectPictogram } from "../dashboard/missionPictograms";
import type { ProfileCitation, ProfileMatrix, ProfileMatrixCell } from "../lib/api";
import { formatNumber, formatSourceDate } from "../lib/format";
import { UNKNOWN_MARK } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { MissionProfilesView } from "./MissionProfilesPanel";

/*
 * Los perfiles lado a lado se MUESTRAN: cada frase, rótulo y nota es del backend
 * (`evidence/mission_profiles.py`, `compare`). Se comprueba pintando un ejemplo y buscando cada
 * frase tal cual, y leyendo la fuente del panel para ver que no redacta nada de lo que dice un
 * perfil ni decide nada.
 */

const read = (file: string) =>
  readFileSync(fileURLToPath(new URL(file, import.meta.url)), "utf-8").replace(/\r\n/g, "\n");

// Las claves de aspecto que declara el backend: una nueva sin dibujo saldría con «desconocido».
const BACKEND = read("../../../backend/app/evidence/mission_profiles.py");
const backendAspects = (): string[] => {
  const body = /ASPECTS: dict\[str, str\] = \{([^}]*)\}/.exec(BACKEND)?.[1] ?? "";
  return [...body.matchAll(/"([a-z_]+)":/g)].map((match) => match[1]!);
};

const citation = (over: Partial<ProfileCitation> = {}): ProfileCitation => ({
  ref: "ficha-de-prueba",
  title: "Pagina de prueba",
  url: "https://www.nasa.gov/prueba/",
  section: "apartado de prueba",
  quote: "A literal sentence read on the page.",
  read_on: "2026-10-13",
  ...over,
});

const cell = (over: Partial<ProfileMatrixCell> = {}): ProfileMatrixCell => ({
  key: "comm_delay",
  label: "rotulo del backend",
  status: "read",
  status_text: "leido segun el backend",
  statement: "frase del backend",
  citations: [citation()],
  discrepancy: null,
  searched: null,
  emma_note: null,
  text: "frase del backend",
  reused_from: [],
  ...over,
});

const ASPECTS = [
  { key: "comm_delay", label: "retardo segun el backend", reused_only: false },
  { key: "medical_capability", label: "capacidad medica segun el backend", reused_only: true },
];

const matrix = (over: Partial<ProfileMatrix> = {}): ProfileMatrix => ({
  note: "nota del backend: descriptivo",
  declared_id: "mars-transit",
  declared_note: "nota de configuracion segun el backend",
  declared_text: null,
  no_source: "sin fuente segun el backend",
  aspects: ASPECTS,
  profiles: [
    {
      id: "leo",
      display: "estacion segun el backend",
      declared: false,
      cells: [
        cell({ text: "retardo de la estacion", statement: "retardo de la estacion" }),
        cell({
          key: "medical_capability",
          text: "capacidad de la estacion",
          statement: "capacidad de la estacion",
          citations: [citation({ quote: "Real-time guidance from Mission Control." })],
          reused_from: ["sitio uno segun el backend", "sitio dos segun el backend"],
        }),
      ],
    },
    {
      id: "lunar-surface",
      display: "luna segun el backend",
      declared: false,
      cells: [
        cell({
          text: "retardo de la luna",
          statement: "retardo de la luna",
          discrepancy: {
            text: "discrepancia segun el backend",
            citations: [citation({ quote: "Another page says otherwise.", read_on: "2026-10-21" })],
          },
          emma_note: "nota de EMMA segun el backend",
        }),
        cell({
          key: "medical_capability",
          status: "unverified",
          status_text: "sin verificar",
          statement: null,
          citations: [],
          searched: "lo que el backend dice que se busco",
          text: "sin fuente segun el backend",
        }),
      ],
    },
    {
      id: "mars-transit",
      display: "marte segun el backend",
      declared: true,
      // Al reves que las filas: la casilla se busca por clave, no por posicion.
      cells: [
        cell({ key: "medical_capability", text: "capacidad de marte", statement: "capacidad de marte" }),
        cell({ text: "retardo de marte", statement: "retardo de marte" }),
      ],
    },
  ],
  reused_note: "nota de reutilizadas segun el backend",
  medical_note: "nota de EMMA sobre los niveles segun el backend",
  pages_read: [
    { title: "Pagina de prueba", url: "https://www.nasa.gov/prueba/", read_on: ["2026-10-13", "2026-10-21"] },
  ],
  ...over,
});

const render = (value: ProfileMatrix) => renderToStaticMarkup(createElement(MissionProfilesView, { matrix: value }));

/** El texto de cada casilla de una fila, en el orden de las columnas. */
const rowCells = (html: string, label: string): string[] => {
  const row = new RegExp(`<tr><th scope="row">.*?${label}.*?</th>(.*?)</tr>`).exec(html)?.[1] ?? "";
  return [...row.matchAll(/<td>(.*?)<\/td>/g)].map((match) => match[1]!);
};

describe("perfiles lado a lado: lo que se pinta", () => {
  it("cada frase, rotulo y nota del backend tal cual", () => {
    const html = render(matrix());
    for (const text of [
      "nota del backend: descriptivo",
      "retardo segun el backend",
      "capacidad medica segun el backend",
      "estacion segun el backend",
      "luna segun el backend",
      "marte segun el backend",
      "capacidad de la estacion",
      "Real-time guidance from Mission Control.",
      "discrepancia segun el backend",
      "Another page says otherwise.",
      "nota de EMMA segun el backend",
      "lo que el backend dice que se busco",
      "nota de reutilizadas segun el backend",
      "nota de configuracion segun el backend",
      "nota de EMMA sobre los niveles segun el backend",
      "sitio uno segun el backend · sitio dos segun el backend",
    ]) {
      expect(html).toContain(text);
    }
    expect(html).toContain('href="https://www.nasa.gov/prueba/"');
  });

  it("una fila por aspecto en el orden del backend, y cada casilla en la columna de su perfil", () => {
    const html = render(matrix());
    expect(html.indexOf("retardo segun el backend")).toBeLessThan(html.indexOf("capacidad medica segun el backend"));
    const delay = rowCells(html, "retardo segun el backend");
    expect(delay).toHaveLength(3);
    expect(delay[0]).toContain("retardo de la estacion");
    expect(delay[1]).toContain("retardo de la luna");
    expect(delay[2]).toContain("retardo de marte");
    expect(rowCells(html, "capacidad medica segun el backend")[2]).toContain("capacidad de marte");
  });

  it("la casilla sin frase lleva la palabra del backend en cian con el anillo punteado", () => {
    const html = render(matrix());
    expect(html).toMatch(
      /<span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted"[^>]*>.*?<\/svg>sin fuente segun el backend<\/span>/,
    );
    // Lo leido no lleva señal. En la tabla: las píldoras del tablero, delante, llevan el cian del
    // recuento de casillas sin fuente (segunda ronda del lote «muestra»).
    const table = html.slice(html.indexOf("<table"));
    expect(table).not.toMatch(/c-cyan[^>]*>.*?capacidad de la estacion/);
  });

  it("solo la columna del perfil declarado lleva el signo de elegido", () => {
    const html = render(matrix());
    const chosen = uiPictogram("chosen");
    // En la tabla, una vez; en el tablero, otra en la píldora del perfil declarado, delante.
    const table = html.slice(html.indexOf("<table"));
    expect(table.match(new RegExp(`data-pictogram="${chosen}"`, "g"))).toHaveLength(1);
    const pills = html.slice(0, html.indexOf("<table"));
    expect(pills.match(new RegExp(`data-pictogram="${chosen}"`, "g"))).toHaveLength(1);
    expect(html).toMatch(new RegExp(`marte segun el backend</span><div class="secondary"><span class="mark"><svg [^>]*data-pictogram="${chosen}"`));
  });

  it("un perfil declarado que no esta en el catalogo se dice con la marca de dato ausente", () => {
    const html = render(
      matrix({
        declared_text: "el declarado no esta segun el backend",
        profiles: matrix().profiles.map((profile) => ({ ...profile, declared: false })),
      }),
    );
    expect(html).toMatch(/<span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted"[^>]*>.*?<\/svg>el declarado no esta segun el backend/);
    expect(html).not.toContain(`data-pictogram="${uiPictogram("chosen")}"`);
  });

  it("las citas van plegadas con su cuenta y su dia de lectura por format.ts", () => {
    const html = render(matrix());
    expect(html).toContain(`Frases leídas (<span class="num">${formatNumber(1)}</span>)`);
    expect(html).toContain(`<span class="num">${formatSourceDate("2026-10-21")}</span>`);
    // Sin citas, sin plegable.
    expect(rowCells(html, "capacidad medica segun el backend")[1]).not.toContain("<details");
  });

  it("cada aspecto lleva su dibujo junto a su rotulo; la capacidad medica, el maletin", () => {
    const html = render(matrix());
    expect(html).toMatch(/<svg [^>]*data-pictogram="kit-case"[^>]*>.*?<\/svg>capacidad medica segun el backend<\/span>/);
    for (const key of backendAspects()) {
      expect(aspectPictogram(key), key).not.toBe(UNKNOWN_MARK.pictogram);
    }
    expect(backendAspects()).toContain("medical_capability");
  });

  it("ningun texto visible queda vacio", () => {
    for (const text of textNodes(render(matrix()))) expect(text.trim().length).toBeGreaterThan(0);
  });
});

describe("perfiles lado a lado: la fuente del panel", () => {
  const source = read("./MissionProfilesPanel.tsx");
  // El código sin sus comentarios: el comentario de cabecera nombra la palabra del backend.
  const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

  it("no redacta lo que dice un perfil ni lee niveles, alertas ni riesgo", () => {
    // La casilla pinta la palabra que da el backend, sea la frase o «sin fuente».
    expect(code).toContain("{cell.text}");
    for (const forbidden of ["EMMA no tiene fuente", "Nota de EMMA", "level", "alert", "risk", "isolation"]) {
      expect(code).not.toContain(forbidden);
    }
  });

  it("los fallos de la consulta van por requestOutcome", () => {
    expect(source).toContain("requestOutcome(reason)");
  });

  it("la consola de Tierra lo monta, sin quitar el panel del marco", () => {
    const ground = read("./GroundConsole.tsx");
    expect(ground).toContain("<MissionProfilesPanel />");
    expect(ground.indexOf("<FrameworkPanel />")).toBeLessThan(ground.indexOf("<MissionProfilesPanel />"));
  });
});
