import { describe, expect, it } from "vitest";

import type {
  DesignHypotheses,
  DesignHypothesis,
  Framework,
  GapStatus,
  ReadBlock,
  ReadSources,
} from "../lib/api";
import { isPictogramName } from "../icons/registry";
import { LEVELS, LEVEL_ORDER } from "../lib/levels";
import { UNKNOWN_MARK } from "../lib/marks";
import {
  UNKNOWN_STATUS,
  BLOCK_BESIDE,
  UNREAD_STYLE,
  countByStatus,
  coverageDisplay,
  extentStyle,
  gapRows,
  gapStatusStyle,
  placeBlocks,
  ridgeGroups,
  ridgePictogram,
  routeText,
  statusStyle,
} from "./framework";
import { coverageMark, coverageRows } from "./hrpCoverageMarks";

/** Las formas de los cuatro niveles (`lib/levels.ts`): ningún estado de Tierra puede llevar una. */
const LEVEL_PICTOGRAMS: readonly string[] = LEVEL_ORDER.map((level) => LEVELS[level].pictogram);
/** Las marcas de «hecho» y de «medido»: tampoco las lleva un estado de inventario. */
const DONE_OR_MEASURED = ["check", "dot-filled"];

const gapStatus = (id: string, status: string, statusText: string): GapStatus => ({
  id,
  status,
  status_text: statusText,
  statement: `frase-${id}`,
  quote: "Status: x",
  where: "cabecera",
  url: "https://humanresearchroadmap.nasa.gov/Gaps/gap.aspx?i=1",
  source: "Human Research Roadmap",
  read_on: "2026-10-13",
});

// Como los escribe el backend (`app/evidence/design_hypotheses.py`): la consola no los redacta.
const STATUSES = [
  { id: "architecture", text: "hipótesis: EMMA la soporta en su arquitectura y no la prueba" },
  { id: "simulated", text: "hipótesis: con una pieza que la ejercita sobre datos simulados; no la prueba" },
  { id: "partly-real-data", text: "hipótesis: contrastada en parte con datos reales; no probada" },
  { id: "outside", text: "hipótesis: fuera de EMMA" },
];

const hypothesis = (label: string, status: string): DesignHypothesis => ({
  id: `KB-${label}`,
  label,
  statement: `enunciado de ${label}`,
  status,
  status_text: STATUSES.find((item) => item.id === status)?.text ?? `hipótesis: ${status}`,
  real_data: null,
  scenario: null,
  documents: [],
  touches: [],
  not_demonstrated: "lo que no demuestra",
});

const inventory = (hypotheses: DesignHypothesis[]): DesignHypotheses => ({
  source: { document: "docs/contexto/knowledge-base-v1.md", section: "13", title: "Hipótesis" },
  note: "nota del backend",
  statuses: STATUSES,
  hypotheses,
  unread_anchors: [],
});

// Como los escribe el backend (`app/evidence/nasa_framework.py`): la consola no los redacta.
const EXTENTS = [
  { id: "full", text: "leído entero" },
  { id: "partial", text: "leído en parte" },
  { id: "record", text: "leído: resumen de NTRS; el documento completo, no" },
];
// Las coberturas de la tabla del CDSS, como las escribe el backend (`COVERAGES`).
const COVERAGES = [
  { id: "covered", text: "cubre" },
  { id: "partial", text: "en parte" },
  { id: "outside", text: "no" },
];

const block = (id: string): ReadBlock => ({
  id,
  title: `título de ${id}`,
  about: "de qué va",
  statements: [],
  question: null,
  coverage: null,
  emma: "EMMA hace esto.",
  not_read: ["esto no se leyó"],
});

const readSources = (ids: string[]): ReadSources => ({
  note: "nota del backend",
  read_on: "2026-10-13",
  extents: EXTENTS,
  gap_statuses: [],
  coverages: COVERAGES,
  sources: [],
  blocks: ids.map(block),
});

describe("lo leído en las fuentes de NASA", () => {
  it("cada alcance de lectura tiene su pictograma, y ninguno es una marca de conforme ni un nivel", () => {
    const pictograms = EXTENTS.map(({ id }) => extentStyle(id).pictogram);
    expect(new Set(pictograms).size).toBe(EXTENTS.length);
    for (const { id } of EXTENTS) {
      const style = extentStyle(id);
      expect(style.pictogram).not.toBeNull();
      expect([...DONE_OR_MEASURED, ...LEVEL_PICTOGRAMS]).not.toContain(style.pictogram);
      expect(["red", "yellow", "blue", "green", "magenta"]).not.toContain(style.color);
    }
    // Leído entero, en parte y solo la ficha: marco lleno, marco a medias, marco vacío.
    expect(pictograms).toEqual(["frame-filled", "square-half", "frame-empty"]);
  });

  it("solo «la ficha y el resumen» va en cian: del documento falta casi todo", () => {
    expect(EXTENTS.filter(({ id }) => extentStyle(id).color !== null).map(({ id }) => id)).toEqual([
      "record",
    ]);
    expect(extentStyle("record").color).toBe("cyan");
    // Y no se confunde con el «sin leer» de un anclaje, que es otro dibujo.
    expect(extentStyle("record").pictogram).not.toBe(UNREAD_STYLE.pictogram);
  });

  it("un alcance que la interfaz no conoce no pasa por una lectura entera", () => {
    expect(extentStyle("leído por encima")).toBe(UNKNOWN_STATUS);
    expect(extentStyle("leído por encima")).not.toEqual(extentStyle("full"));
  });

  it("los bloques que completan un apartado van junto a él y el resto, en el orden del backend", () => {
    const placed = placeBlocks(
      readSources([
        "cdss",
        "exmc-gaps-today",
        "imm-limitations",
        "medprat",
        "food-gaps",
        "level-of-care",
        "habitat-systems",
      ]),
    );
    expect(placed.gaps?.id).toBe(BLOCK_BESIDE.gaps);
    expect(placed.imm?.id).toBe(BLOCK_BESIDE.imm);
    // MEDPRAT e IMPACT van junto al IMM, del que son la continuación.
    expect(placed.medprat?.id).toBe(BLOCK_BESIDE.medprat);
    expect(placed.rest.map((item) => item.id)).toEqual([
      "cdss",
      "food-gaps",
      "level-of-care",
      "habitat-systems",
    ]);
  });

  it("ningún bloque se pierde ni se pinta dos veces, tampoco uno que la interfaz no conozca", () => {
    const ids = ["bloque-nuevo", "imm-limitations", "cdss"];
    const placed = placeBlocks(readSources(ids));
    const shown = [placed.gaps, placed.imm, placed.medprat, ...placed.rest].filter(
      (item) => item !== null,
    );
    expect(shown.map((item) => item.id).sort()).toEqual([...ids].sort());
    expect(placed.gaps).toBeNull();
    expect(placed.medprat).toBeNull();
    expect(placed.rest.map((item) => item.id)).toEqual(["bloque-nuevo", "cdss"]);
  });

  it("no retoca lo que el backend escribe sobre EMMA ni lo que no se leyó", () => {
    const placed = placeBlocks(readSources(["cdss"]));
    expect(placed.rest[0]).toEqual(block("cdss"));
  });

  it("HERMES y la radiación del alimento van con el resto, en el orden del backend", () => {
    const placed = placeBlocks(readSources(["cdss", "hermes", "food-gaps", "food-radiation"]));
    expect(placed.rest.map((item) => item.id)).toEqual(["cdss", "hermes", "food-gaps", "food-radiation"]);
  });
});

describe("la tabla de cobertura del CDSS, punto por punto", () => {
  it("cada cobertura lleva la palabra del backend y la marca de la de los riesgos del HRP", () => {
    expect(coverageDisplay(readSources([]))).toEqual({ covered: "cubre", partial: "en parte", outside: "no" });
    const marks = COVERAGES.map(({ id }) => coverageMark(id));
    expect(new Set(marks.map((item) => item.pictogram)).size).toBe(COVERAGES.length);
    // «No» es el gris tachado de «fuera de EMMA»; ninguna cobertura es un nivel ni lleva alarma.
    expect(coverageMark("outside")).toEqual(statusStyle("outside"));
    for (const item of marks) {
      expect(LEVEL_PICTOGRAMS).not.toContain(item.pictogram);
      expect(["red", "yellow", "blue", "green", "magenta"]).not.toContain(item.color);
    }
  });

  it("una palabra repetida no pisa la primera, y los recuentos sin palabra van con su clave", () => {
    const display = coverageDisplay({ coverages: [...COVERAGES, { id: "covered", text: "lo cubre todo" }] });
    expect(display["covered"]).toBe("cubre");
    expect(coverageRows({ covered: 2, raro: 1 }, display)).toEqual([
      { coverage: "covered", display: "cubre", count: 2 },
      { coverage: "partial", display: "en parte", count: 0 },
      { coverage: "outside", display: "no", count: 0 },
      { coverage: "raro", display: "raro", count: 1 },
    ]);
    expect(coverageMark("raro")).toBe(UNKNOWN_MARK);
  });
});

describe("el marco de NASA y las hipótesis de diseño en la consola de Tierra", () => {
  it("ningún estado de hipótesis se pinta como probado ni como un nivel de riesgo", () => {
    const alertColors = ["red", "yellow", "blue", "green", "magenta"];
    for (const { id } of STATUSES) {
      const style = statusStyle(id);
      expect(style.pictogram).not.toBeNull();
      expect([...DONE_OR_MEASURED, ...LEVEL_PICTOGRAMS]).not.toContain(style.pictogram);
      expect(alertColors).not.toContain(style.color);
    }
  });

  it("cada estado tiene su pictograma y solo «fuera de EMMA» lleva color, el gris de no disponible", () => {
    const pictograms = STATUSES.map(({ id }) => statusStyle(id).pictogram);
    expect(new Set(pictograms).size).toBe(STATUSES.length);
    // De nada a una parte: marco vacío, un cuarto, la mitad; y el anillo barrado de lo que no está aquí.
    expect(pictograms).toEqual(["parallelogram", "circle-quarter", "circle-half-right", "slash-circle"]);
    expect(STATUSES.filter(({ id }) => statusStyle(id).color !== null).map(({ id }) => id)).toEqual([
      "outside",
    ]);
    expect(statusStyle("outside").color).toBe("gray");
  });

  it("un estado que la interfaz no conoce no se disfraza de uno conocido: lleva la marca única de desconocido", () => {
    expect(statusStyle("proven")).toBe(UNKNOWN_STATUS);
    expect(STATUSES.map(({ id }) => statusStyle(id))).not.toContain(UNKNOWN_STATUS);
    expect(UNKNOWN_STATUS).toBe(UNKNOWN_MARK);
    expect(["red", "yellow", "blue", "green", "magenta", "cyan", "gray"]).not.toContain(UNKNOWN_STATUS.color);
  });

  it("«sin leer» es un dato que falta: cian y con el anillo punteado, distinto del de cualquier estado", () => {
    expect(UNREAD_STYLE.color).toBe("cyan");
    expect(UNREAD_STYLE.pictogram).toBe("ring-dotted");
    expect(STATUSES.map(({ id }) => statusStyle(id).pictogram)).not.toContain(UNREAD_STYLE.pictogram);
  });

  it("cada peligro RIDGE lleva el pictograma de su clave; uno desconocido, la marca de desconocido", () => {
    for (const hazard of ["gravity", "isolation", "radiation", "distance", "environment"]) {
      expect(ridgePictogram(hazard)).toBe(`ridge-${hazard}`);
      expect(isPictogramName(ridgePictogram(hazard) ?? "")).toBe(true);
    }
    expect(ridgePictogram("inventado")).toBe(UNKNOWN_MARK.pictogram);
  });

  it("el recuento cuadra con la lista, va en el orden del backend y no calla los estados vacíos", () => {
    const counts = countByStatus(
      inventory([
        hypothesis("H1", "architecture"),
        hypothesis("H2", "partly-real-data"),
        hypothesis("H3", "architecture"),
        hypothesis("H4", "simulated"),
      ]),
    );
    expect(counts.map((row) => [row.id, row.count])).toEqual([
      ["architecture", 2],
      ["simulated", 1],
      ["partly-real-data", 1],
      ["outside", 0],
    ]);
    expect(counts.reduce((sum, row) => sum + row.count, 0)).toBe(4);
    expect(counts[0]?.text).toBe(STATUSES[0]?.text);
  });

  it("una hipótesis con un estado no declarado se cuenta aparte, con la frase que trae", () => {
    const counts = countByStatus(inventory([hypothesis("H1", "architecture"), hypothesis("H2", "nuevo")]));
    expect(counts.at(-1)).toEqual({ id: "nuevo", text: "hipótesis: nuevo", count: 1 });
    expect(counts.reduce((sum, row) => sum + row.count, 0)).toBe(2);
  });

  it("agrupa los dominios por peligro RIDGE sin perder ninguno ni cambiar el nombre del backend", () => {
    const ridge: Framework["ridge"] = {
      cardiovascular: { hazard: "gravity", display: "Campos gravitatorios" },
      behavioral: { hazard: "isolation", display: "Aislamiento y confinamiento" },
      bone: { hazard: "gravity", display: "Campos gravitatorios" },
      radiation: { hazard: "radiation", display: "Radiación" },
    };
    const groups = ridgeGroups(ridge);
    expect(groups).toEqual([
      { hazard: "gravity", display: "Campos gravitatorios", domains: ["cardiovascular", "bone"] },
      { hazard: "isolation", display: "Aislamiento y confinamiento", domains: ["behavioral"] },
      { hazard: "radiation", display: "Radiación", domains: ["radiation"] },
    ]);
    expect(groups.flatMap((group) => group.domains).sort()).toEqual(Object.keys(ridge).sort());
  });

  it("los dos huecos del MDA salen con el nombre, el estado leído y el texto del backend, tal cual", () => {
    const closed = gapStatus("Med07", "closed", "cerrado");
    const merged = gapStatus("Med10", "merged", "fusionado en otro hueco");
    const successor = gapStatus("Medical-701", "open", "abierto");
    const rows = gapRows({
      source: "fuente",
      url: "https://ntrs.nasa.gov/citations/20200000567",
      note: "nota",
      med07: { label: "rótulo 07", gap: "gap 07", status: closed, emma: "emma 07" },
      med10: { label: "rótulo 10", gap: "gap 10", status: merged, merged_into: successor, emma: "emma 10" },
    });
    expect(rows).toEqual([
      { key: "med07", label: "rótulo 07", gap: "gap 07", status: closed, mergedInto: null, emma: "emma 07" },
      { key: "med10", label: "rótulo 10", gap: "gap 10", status: merged, mergedInto: successor, emma: "emma 10" },
    ]);
  });

  it("el estado de un hueco lleva un pictograma propio y ningún color; uno desconocido no se supone abierto", () => {
    const marks = ["open", "closed", "merged", "archived", "split"].map((status) => gapStatusStyle(status));
    expect(new Set(marks.map((style) => style.pictogram)).size).toBe(marks.length);
    expect(marks.every((style) => style.color === null)).toBe(true);
    // Ninguno es la marca de un nivel de riesgo ni de «hecho».
    expect(
      marks.some((style) => style.pictogram === null || [...LEVEL_PICTOGRAMS, ...DONE_OR_MEASURED].includes(style.pictogram)),
    ).toBe(false);
    expect(gapStatusStyle("retired")).toBe(UNKNOWN_STATUS);
    expect(gapStatusStyle("retired")).not.toEqual(gapStatusStyle("open"));
  });

  it("una pieza sin ruta no enseña ninguna", () => {
    expect(routeText({ module: "app.core.ledger", method: null, route: null, what: "x" })).toBeNull();
    expect(routeText({ module: "app.analysis.risk", method: "GET", route: "/api/status", what: "x" })).toBe(
      "GET /api/status",
    );
  });
});
