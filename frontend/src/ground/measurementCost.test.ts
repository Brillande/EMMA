import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { isPictogramName } from "../icons/registry";
import type { CostDimension, CostReading, CostSummary, Indicator } from "../lib/api";
import { UNKNOWN_MARK, mark } from "../lib/marks";
import {
  CLASSIFIED_STYLE,
  DISCREPANCY_STYLE,
  GROUND_PICTOGRAM,
  MODE_PICTOGRAMS,
  SOURCE_STYLE,
  UNCLASSIFIED_STYLE,
  VALUE_PICTOGRAMS,
  cellText,
  countRows,
  coverages,
  dimensionCells,
  groundRows,
  groupByMode,
  modePictogram,
  readRules,
  searchedRows,
  splitCells,
  valueMark,
} from "./measurementCost";

// Como lo escribe el backend (`app/ingest/cost.py`): la consola no lo redacta.
const SUMMARY: CostSummary = {
  indicators: 3,
  kb_coverage: { display: "Lo que pide la base de conocimiento §9", origin: "§9", terms: [] },
  conversation_coverage: {
    display: "Lo que pide la conversación de ideación",
    origin: "conversación",
    terms: [
      { term: "valor clínico", field: null, kind: "excluded", display: "No entra en EMMA", note: "juicio clínico" },
    ],
  },
  deduced_display: "deducción de EMMA, no una lectura",
  deduced_note: "nota de la deducción",
  dimensions: [
    {
      key: "processing",
      display: "Dónde se procesa",
      deduced: false,
      values: [
        { value: "on-device", display: "a bordo, en el propio dispositivo", count: 1 },
        { value: "onboard-analyzer", display: "a bordo, con analizador", count: 0 },
      ],
      unclassified: 2,
    },
    {
      key: "consumables",
      display: "Consumibles",
      deduced: false,
      values: [{ value: "none", display: "no gasta consumibles", count: 0 }],
      unclassified: 3,
    },
  ],
  unclassified: 5,
  fully_classified: 0,
  unclassified_value: "unclassified",
  unclassified_display: "sin clasificar",
  unclassified_note: "nota del backend",
  reading_display: { sources: "lo que la sostiene", discrepancies: "lo que la matiza" },
  searched_display: "Buscado y no encontrado",
  searched: [
    {
      keys: ["a", "fuera-del-catalogo"],
      dimensions: ["consumables"],
      dimensions_display: ["Consumibles"],
      searched: "dónde se buscó",
      searched_on: "2026-10-21",
    },
  ],
  ground_dependence: {
    display: "Hoy se sabe después",
    note: "nota del backend",
    origin: "conversación",
    value: "ground-or-return",
    value_display: "requiere retorno de la muestra o análisis en Tierra",
    no_source: "EMMA no tiene fuente",
    rules: ["g"],
    indicators: [
      { key: "a", rule: "g", inherited_from: null, result: "diferido" },
      { key: "q", rule: "g", inherited_from: ["a"], result: "diferido" },
    ],
    profiles: [],
  },
  rules: [
    { id: "r1", basis: "texto que la sostiene", indicators: 1, sources: [], discrepancies: [] },
  ],
};

const reading = (quote: string, note?: string): CostReading => ({
  ref: "ficha",
  title: "título",
  source: "cita",
  url: null,
  quote,
  where: "resumen",
  read_on: "2026-10-14",
  ...(note === undefined ? {} : { note }),
});

const FIRST = SUMMARY.dimensions[0] as CostSummary["dimensions"][number];

const classified: CostDimension = {
  value: "on-device",
  display: "a bordo, en el propio dispositivo",
  basis: "texto que la sostiene",
  rule: "r1",
  inherited_from: null,
  figure: null,
};
const unclassified: CostDimension = {
  value: "unclassified",
  display: "sin clasificar",
  basis: null,
  rule: null,
  inherited_from: null,
  figure: null,
};

const indicator = (
  key: string,
  mode: string,
  dimensions: Record<string, CostDimension> | null,
): Indicator => ({
  key,
  display: key,
  display_es: key,
  display_es_origin: "emma",
  display_es_origin_display: "nombre de EMMA, no de LOINC",
  unit: "1",
  domain: "immune",
  system: "https://emma.mission/codes",
  is_standard_code: false,
  reference_low: null,
  reference_high: null,
  reference_basis: "design",
  critical_low: null,
  critical_high: null,
  decimals: 0,
  measurement_cost:
    dimensions === null
      ? null
      : {
          mode,
          mode_display: `clase ${mode}`,
          equipment: "equipo",
          crew_time_minutes: null,
          crew_time_basis: "sin fuente",
          dimensions,
        },
});

const COST_PATH = fileURLToPath(new URL("../../../backend/app/ingest/cost.py", import.meta.url));

/**
 * Las claves de `MODES` y los valores de cada dimensión de `DIMENSIONS`, leídos de `cost.py`. Sin
 * depender de la sangría: una clave seguida de `{` abre una dimensión (o su bloque `values`), y
 * dentro de `values` cada clave seguida de una cadena, o de un paréntesis que la parte en varias
 * líneas, es un valor.
 */
function backendVocabulary(): { modes: string[]; values: Record<string, string[]> } {
  const source = readFileSync(COST_PATH, "utf8");
  const modesBlock = /^MODES = \{([\s\S]*?)^\}/m.exec(source)?.[1] ?? "";
  const modes = [...modesBlock.matchAll(/^\s*"([^"]+)":\s*"/gm)].map((match) => match[1] ?? "");
  const dimensionsBlock = /^DIMENSIONS\b[^=]*= \{([\s\S]*?)^\}/m.exec(source)?.[1] ?? "";
  const values: Record<string, string[]> = {};
  let current: string | null = null;
  let inValues = false;
  for (const line of dimensionsBlock.split("\n")) {
    const opened = /^\s*"([^"]+)":\s*\{/.exec(line)?.[1];
    if (opened === "values") {
      inValues = true;
      continue;
    }
    if (opened !== undefined) {
      current = opened;
      inValues = false;
      continue;
    }
    if (/^\s*\},?\s*$/.test(line)) {
      inValues = false;
      continue;
    }
    // Una palabra larga se escribe entre paréntesis en varias líneas: la clave abre con `(`.
    const value = /^\s*"([^"]+)":\s*["(]/.exec(line)?.[1];
    if (inValues && current !== null && value !== undefined) (values[current] ??= []).push(value);
  }
  if (modes.length === 0 || Object.keys(values).length === 0) {
    throw new Error("no se leyó el vocabulario de cost.py");
  }
  return { modes, values };
}

describe("coste de medir: el vocabulario del backend, con un pictograma por valor", () => {
  const vocabulary = backendVocabulary();

  it("se lee de cost.py, no de una lista vacía", () => {
    expect(vocabulary.modes).toContain("continuous-passive");
    expect(vocabulary.values["processing"]).toContain("on-device");
    // Las tres de la novena ronda, las cinco de la base de conocimiento §9 (decimosexta) y las
    // tres de la conversación de ideación (decimonovena).
    expect(Object.keys(vocabulary.values).length).toBe(11);
    expect(vocabulary.values["mass"]).toContain("stated");
    expect(vocabulary.values["automation"]).toContain("passive");
  });

  it("cada clase de medida tiene su pictograma, distinto, y ninguno sobra", () => {
    expect(Object.keys(MODE_PICTOGRAMS).sort()).toEqual([...vocabulary.modes].sort());
    const pictograms = Object.values(MODE_PICTOGRAMS);
    expect(new Set(pictograms).size).toBe(pictograms.length);
    for (const name of pictograms) expect(isPictogramName(name), name).toBe(true);
    expect(modePictogram("inventada")).toBe(UNKNOWN_MARK.pictogram);
  });

  it("cada valor de cada dimensión tiene su pictograma, distinto dentro de la dimensión, y ninguno sobra", () => {
    expect(Object.keys(VALUE_PICTOGRAMS).sort()).toEqual(Object.keys(vocabulary.values).sort());
    for (const [dimension, values] of Object.entries(vocabulary.values)) {
      const table = VALUE_PICTOGRAMS[dimension] ?? {};
      expect(Object.keys(table).sort(), dimension).toEqual([...values].sort());
      expect(new Set(Object.values(table)).size).toBe(values.length);
      for (const name of Object.values(table)) expect(isPictogramName(name), name).toBe(true);
    }
  });
});

describe("coste de medir: dimensiones", () => {
  it("«sin clasificar» es un dato ausente: cian y con el anillo punteado", () => {
    expect(valueMark("processing", unclassified.value, SUMMARY)).toBe(UNCLASSIFIED_STYLE);
    expect(UNCLASSIFIED_STYLE.color).toBe("cyan");
    expect(UNCLASSIFIED_STYLE.pictogram).toBe("ring-dotted");
    expect(UNCLASSIFIED_STYLE.pictogram).not.toBe(CLASSIFIED_STYLE.pictogram);
  });

  it("un valor conocido lleva su pictograma sin color; uno que la interfaz no conoce, la marca de clase asignada", () => {
    expect(valueMark("processing", classified.value, SUMMARY)).toEqual(
      mark(VALUE_PICTOGRAMS["processing"]?.["on-device"] ?? null, null),
    );
    expect(valueMark("processing", "valor-nuevo", SUMMARY)).toBe(CLASSIFIED_STYLE);
    expect(valueMark("dimension-nueva", "on-device", SUMMARY)).toBe(CLASSIFIED_STYLE);
    expect(CLASSIFIED_STYLE.color).toBeNull();
  });

  it("qué es «sin clasificar» lo dice la clave del backend, no una palabra de aquí", () => {
    const other = { ...SUMMARY, unclassified_value: "por-decidir" };
    expect(valueMark("processing", unclassified.value, other)).toBe(CLASSIFIED_STYLE);
    expect(valueMark("processing", "por-decidir", other)).toBe(UNCLASSIFIED_STYLE);
  });

  it("las dimensiones salen en el orden y con el nombre del backend", () => {
    const item = indicator("a", "m", { consumables: unclassified, processing: classified });
    const cells = dimensionCells(item, SUMMARY);
    expect(cells.map((cell) => cell.label)).toEqual(["Dónde se procesa", "Consumibles"]);
    expect(cells.map((cell) => cell.style.pictogram)).toEqual(["chip", UNCLASSIFIED_STYLE.pictogram]);
    expect(cells[0]?.entry.basis).toBe("texto que la sostiene");
  });

  it("una dimensión que el indicador no trae no se inventa", () => {
    const item = indicator("a", "m", { processing: classified });
    expect(dimensionCells(item, SUMMARY).map((cell) => cell.key)).toEqual(["processing"]);
    expect(dimensionCells(indicator("b", "m", null), SUMMARY)).toEqual([]);
  });

  it("el recuento enseña «sin clasificar» siempre, y las clases vacías también", () => {
    const rows = countRows(FIRST, SUMMARY);
    expect(rows.map((row) => [row.display, row.count])).toEqual([
      ["a bordo, en el propio dispositivo", 1],
      ["a bordo, con analizador", 0],
      ["sin clasificar", 2],
    ]);
    expect(rows.at(-1)?.style).toBe(UNCLASSIFIED_STYLE);
    expect(rows.slice(0, -1).map((row) => row.style.pictogram)).toEqual(["chip", "box-slot"]);
    const none = countRows({ ...FIRST, unclassified: 0 }, SUMMARY);
    expect(none.at(-1)?.count).toBe(0);
  });

  it("agrupa por clase de medida en el orden de llegada, con su clave, y deja fuera lo que no tiene coste", () => {
    const groups = groupByMode([
      indicator("a", "x", {}),
      indicator("b", "y", {}),
      indicator("c", "x", {}),
      indicator("d", "z", null),
    ]);
    expect(groups.map((group) => [group.mode, group.label, group.items.map((item) => item.key)])).toEqual([
      ["x", "clase x", ["a", "c"]],
      ["y", "clase y", ["b"]],
    ]);
  });
});

describe("coste de medir: lo leído", () => {
  it("una regla sin lectura no sale: su texto ya va con cada indicador", () => {
    expect(readRules(SUMMARY)).toEqual([]);
  });

  it("lo que sostiene va antes que lo que matiza, con los rótulos del backend", () => {
    const rule = {
      id: "r2",
      basis: "leído",
      indicators: 3,
      sources: [reading("blood samples are returned")],
      discrepancies: [reading("real-time hematology", "una demostración")],
    };
    const [read] = readRules({ ...SUMMARY, rules: [...SUMMARY.rules, rule] });
    expect(read?.rule.id).toBe("r2");
    expect(read?.sections.map((section) => [section.label, section.style])).toEqual([
      ["lo que la sostiene", SOURCE_STYLE],
      ["lo que la matiza", DISCREPANCY_STYLE],
    ]);
    expect(read?.sections[1]?.items[0]?.note).toBe("una demostración");
  });

  it("una regla que solo tiene lo que la matiza no lo esconde", () => {
    const rule = {
      id: "r3",
      basis: "x",
      indicators: 1,
      sources: [],
      discrepancies: [reading("q", "n")],
    };
    const [read] = readRules({ ...SUMMARY, rules: [rule] });
    expect(read?.sections.map((section) => section.kind)).toEqual(["discrepancies"]);
  });

  it("una discrepancia no lleva color de estado: la tabla F.5-1 no le da ninguno", () => {
    expect(DISCREPANCY_STYLE.color).toBeNull();
    expect(DISCREPANCY_STYLE.pictogram).toBe("not-equal");
    expect(DISCREPANCY_STYLE.pictogram).not.toBe(UNCLASSIFIED_STYLE.pictogram);
    expect(DISCREPANCY_STYLE.pictogram).not.toBe(SOURCE_STYLE.pictogram);
  });
});

describe("coste de medir: hoy se sabe después y lo buscado sin encontrar", () => {
  it("lo que depende de Tierra lleva el mismo dibujo que «requiere retorno o análisis en Tierra»", () => {
    expect(GROUND_PICTOGRAM).toBe(VALUE_PICTOGRAMS["processing"]?.["ground-or-return"]);
    expect(isPictogramName(GROUND_PICTOGRAM)).toBe(true);
  });

  it("enseña lo que da el backend, en su orden, con el nombre del catálogo y el calculado marcado", () => {
    const rows = groundRows(SUMMARY.ground_dependence, [indicator("a", "laboratory", {})]);
    expect(rows).toEqual([
      { key: "a", displayEs: "a", result: "diferido", inherited: false },
      // Fuera del catálogo: la clave, no un nombre inventado.
      { key: "q", displayEs: "q", result: "diferido", inherited: true },
    ]);
  });

  it("lo buscado y no encontrado lleva sus indicadores, sus dimensiones y el día, tal cual", () => {
    const [row] = searchedRows(SUMMARY, [{ ...indicator("a", "m", {}), display_es: "Nombre de a" }]);
    expect(row?.names).toEqual([
      { key: "a", displayEs: "Nombre de a" },
      { key: "fuera-del-catalogo", displayEs: "fuera-del-catalogo" },
    ]);
    expect([row?.dimensions, row?.searched, row?.searchedOn]).toEqual([
      "Consumibles",
      "dónde se buscó",
      "2026-10-21",
    ]);
    expect(searchedRows({ ...SUMMARY, searched: [] }, [])).toEqual([]);
  });
});

describe("coste de medir: las dimensiones de la base de conocimiento §9 (decimosexta ronda)", () => {
  const twoDims: CostSummary = {
    ...SUMMARY,
    dimensions: [
      ...SUMMARY.dimensions,
      { key: "mass", display: "Masa del equipo", deduced: false, values: [], unclassified: 1 },
    ],
  };

  it("una cifra leída se formatea aquí, con sus decimales y su unidad tal cual", () => {
    const stated: CostDimension = {
      value: "stated",
      display: "10,32 lbs",
      basis: "leído",
      rule: "f1",
      inherited_from: null,
      figure: { amount: 10.32, decimals: 2, unit: "lbs", figure: "10.32" },
    };
    expect(cellText(stated)).toBe("10,32 lbs");
    const other = { amount: 1.5, decimals: 1, unit: "kg", figure: "1.5" };
    expect(cellText({ ...stated, figure: other })).toBe("1,5 kg");
    // Sin cifra, la palabra del backend.
    expect(cellText(classified)).toBe(classified.display);
  });

  it("lo sin clasificar de un indicador va junto, por su nombre; lo decidido, una línea cada uno", () => {
    const item = indicator("a", "m", { processing: classified, consumables: unclassified, mass: unclassified });
    const split = splitCells(item, twoDims);
    expect(split.classified.map((cell) => cell.key)).toEqual(["processing"]);
    expect(split.unclassified).toEqual(["Consumibles", "Masa del equipo"]);
    // Lo decide la clave del backend, no la palabra.
    const other = { ...twoDims, unclassified_value: "por-decidir" };
    expect(splitCells(item, other).unclassified).toEqual([]);
  });
});

describe("coste de medir: las dimensiones de la conversación de ideación (decimonovena ronda)", () => {
  it("las dos listas del equipo salen en orden, con sus palabras, y un término que no entra lleva su motivo", () => {
    const lists = coverages(SUMMARY);
    expect(lists.map((list) => list.display)).toEqual([
      "Lo que pide la base de conocimiento §9",
      "Lo que pide la conversación de ideación",
    ]);
    const [clinical] = lists[1]?.terms ?? [];
    expect([clinical?.kind, clinical?.field, clinical?.display, clinical?.note]).toEqual([
      "excluded",
      null,
      "No entra en EMMA",
      "juicio clínico",
    ]);
  });

  it("las tres dimensiones nuevas tienen su dibujo por valor, y lo calculado lleva el sumatorio en las tres", () => {
    for (const dimension of ["storage", "frequency", "automation"]) {
      expect(Object.keys(VALUE_PICTOGRAMS[dimension] ?? {}).length, dimension).toBeGreaterThan(0);
    }
    expect(VALUE_PICTOGRAMS["storage"]?.["no-own-storage"]).toBe("sigma");
    expect(VALUE_PICTOGRAMS["frequency"]?.["no-own-schedule"]).toBe("sigma");
    expect(VALUE_PICTOGRAMS["frequency"]?.["continuous-in-periods"]).not.toBe(VALUE_PICTOGRAMS["frequency"]?.["continuous"]);
    expect(VALUE_PICTOGRAMS["automation"]?.["computed"]).toBe("sigma");
    // Sin color: ninguna de estas clases es un estado del tripulante (F.5-1).
    for (const value of Object.keys(VALUE_PICTOGRAMS["automation"] ?? {})) {
      expect(valueMark("automation", value, SUMMARY).color).toBeNull();
    }
  });
});
