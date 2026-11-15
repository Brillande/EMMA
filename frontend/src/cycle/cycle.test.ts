import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, taggedPictogram, visibleText } from "../advisor/visibleText";
import type { BaselinePersonalData, DescriptiveIndicator, FhirObservation } from "../lib/api";
import type { CrewSex } from "../lib/crewSexApi";
import { CYCLE_KEYS, type CycleRecord, cycleIndicators, cycleRow, readingOf } from "../lib/cycleApi";
import { FAILURE_MARK, type RequestOutcome } from "../lib/marks";
import { cssVar, palette, type Token } from "../lib/palette";
import { uiPictogram } from "../lib/uiMarks";
import { CycleView, HOW_TO_DECLARE, NOT_APPLICABLE } from "./CyclePanel";
import { SexFormView } from "./SexForm";

/**
 * El panel del ciclo y el formulario del sexo (lote «ciclo», unidad B4). Los textos del backend
 * son marcadores, no frases de verdad: si la interfaz redactara algo en su sitio, el marcador no
 * saldría.
 */

const UNDECLARED: CrewSex = { subject: "crew-01", declared: false, sex: null, status: "PALABRA-NO-DECLARADO", values: ["female", "male"] };
const declared = (sex: "female" | "male"): CrewSex => ({
  subject: "crew-01",
  declared: true,
  sex,
  declared_by: "QUIEN-DECLARA",
  recorded: "2026-11-14T08:30:00+00:00",
  ledger_index: 4321,
  values: ["female", "male"],
});

const indicator = (overrides: Partial<DescriptiveIndicator> = {}): DescriptiveIndicator => ({
  key: "menstrual-flow",
  display: "Menstrual flow",
  display_es: "NOMBRE-FLUJO",
  domain: "genitourinary",
  domain_display: "DOMINIO",
  unit: "{score}",
  unit_display: "puntos",
  decimals: 0,
  range_text: "RANGO",
  system: "https://emma.mission/codes",
  system_display: "código propio de EMMA",
  code: "menstrual-flow",
  code_basis: { kind: "own", text: "POR-QUE", loinc: null, searched: null },
  equipment: null,
  how_recorded: { route: "/api/diary/entries", text: "COMO" },
  instrument: {
    instrument: "HealthKit",
    language: "en",
    scope: "ALCANCE",
    statements: [],
    categories: [
      { value: 0, literal: "CATEGORIA-CERO", statement: "s0" },
      { value: 2, literal: "CATEGORIA-DOS", statement: "s2" },
    ],
    numbering: "NUMERACION",
    sources: [],
    not_found: [],
  },
  count: 1,
  shown: 1,
  readings: [],
  ...overrides,
});

const BASAL = indicator({
  key: "basal-body-temperature",
  display_es: "NOMBRE-BASAL",
  unit: "Cel",
  unit_display: "°C",
  decimals: 2,
  instrument: null,
});

const RECORDS: CycleRecord[] = [
  { indicator: indicator(), latest: { effective: "2026-11-14T07:05:00+00:00", value: 2 } },
  { indicator: BASAL, latest: { effective: "2026-11-14T06:40:00+00:00", value: 36.625 } },
  { indicator: indicator({ key: "ovulation-test", display_es: "NOMBRE-OVULACION" }), latest: null },
];

const FAILED: RequestOutcome = { mark: FAILURE_MARK, text: "MOTIVO" };

const cycle = (
  sex: CrewSex | null,
  records: CycleRecord[] | null = null,
  options: { unavailable?: RequestOutcome | null; ground?: boolean; phaseBaseline?: string | null } = {},
) =>
  renderToStaticMarkup(
    createElement(CycleView, {
      sex,
      records,
      unavailable: options.unavailable ?? null,
      ground: options.ground ?? false,
      phaseBaseline: options.phaseBaseline,
    }),
  );

const PERSONAL: BaselinePersonalData = {
  no_field: ["edad"],
  statement: "FRASE-QUE-SE-GUARDA",
  cycle: "FRASE-SOLO-EL-CICLO",
  radiation: "R",
  elsewhere: "E",
  privacy: "FRASE-PRIVACIDAD-Y-BORRADO",
  source: { id: "x", title: "T", url: null, relevance: null },
};

const sexForm = (sex: CrewSex | null, options: { readOnly?: boolean; unavailable?: RequestOutcome | null } = {}) =>
  renderToStaticMarkup(
    createElement(SexFormView, {
      subject: "crew-01",
      sex,
      personal: PERSONAL,
      unavailable: options.unavailable ?? null,
      readOnly: options.readOnly ?? false,
    }),
  );

/** Las clases de color que lleva un HTML: solo pueden ser tokens de la paleta. */
const colors = (html: string) => html.match(/\bc-[a-zA-Z]+/g) ?? [];

describe("las claves del ciclo son las del catálogo del backend", () => {
  it("CYCLE_KEYS sigue a CYCLE_RECORDS de codes.py, en su orden", () => {
    const codes = readFileSync(
      fileURLToPath(new URL("../../../backend/app/ingest/codes.py", import.meta.url)),
      "utf8",
    );
    const tuple = /CYCLE_RECORDS: tuple\[VitalCode, \.\.\.\] = \(([\s\S]*?)\)/.exec(codes);
    expect(tuple).not.toBeNull();
    const names = (tuple?.[1] ?? "").split(",").map((name) => name.trim()).filter((name) => name !== "");
    // Los cinco registros del ciclo nacen de `_cycle_record("clave", …)`; la temperatura basal, de
    // `_c(key="clave", …)`.
    const keys = names.map(
      (name) => new RegExp(`^${name} = _(?:cycle_record\\(\\s*|c\\(\\s*key=)"([^"]+)"`, "m").exec(codes)?.[1],
    );
    expect(keys).toEqual([...CYCLE_KEYS]);
  });

  it("del catálogo descriptivo se quedan las del ciclo, en su orden", () => {
    const other = indicator({ key: "vo2-peak" });
    const picked = cycleIndicators([BASAL, other, indicator()]);
    expect(picked.map((item) => item.key)).toEqual(["menstrual-flow", "basal-body-temperature"]);
  });
});

describe("la fila de un registro", () => {
  it("la palabra de la fuente para su número, con el número de EMMA al lado", () => {
    const row = cycleRow(RECORDS[0] as CycleRecord);
    expect(row).toMatchObject({ empty: false, word: "CATEGORIA-DOS", language: "en", figure: "2", when: "2026-11-14 07:05 UTC" });
  });

  it("un número que la fuente no nombra es una cifra, sin palabra inventada", () => {
    const row = cycleRow({ indicator: indicator(), latest: { effective: "2026-11-14T07:05:00+00:00", value: 1 } });
    expect(row).toMatchObject({ word: null, figure: "1 puntos" });
  });

  it("una magnitud, con sus decimales y su unidad, por format", () => {
    expect(cycleRow(RECORDS[1] as CycleRecord)).toMatchObject({ word: null, figure: "36,63 °C" });
  });

  it("una lectura sin fecha o sin valor no se completa", () => {
    expect(readingOf(undefined)).toBeNull();
    expect(readingOf({ effectiveDateTime: "2026-11-14T07:05:00+00:00", valueQuantity: {} } as unknown as FhirObservation)).toBeNull();
    // Una fecha ilegible tampoco: `formatUtc` lanzaría desde el render.
    expect(readingOf({ effectiveDateTime: "ayer", valueQuantity: { value: 1, unit: "{score}" } } as FhirObservation)).toBeNull();
  });
});

describe("panel del ciclo: sexo sin declarar", () => {
  const html = cycle(UNDECLARED);

  it("no aplica, con la palabra del backend en gris («no disponible») y cómo se declara", () => {
    expect(html).toMatch(markedHtml("slash-circle", "PALABRA-NO-DECLARADO", "gray"));
    expect(html).toContain(`${NOT_APPLICABLE}.`);
    expect(html).toContain(HOW_TO_DECLARE.crew);
    expect(html).toContain('data-cycle="not-applicable"');
    expect(colors(html)).toEqual(["c-gray"]);
  });

  it("en Tierra, el mismo panel dice que lo declara el tripulante", () => {
    const ground = cycle(UNDECLARED, null, { ground: true });
    expect(ground).toContain(HOW_TO_DECLARE.ground);
    expect(ground).not.toContain(HOW_TO_DECLARE.crew);
  });

  it("no se esconde: lleva su título con su signo", () => {
    expect(html).toMatch(taggedPictogram("h2", uiPictogram("descriptive"), "Ciclo menstrual</h2>"));
    expect(html).toContain('aria-label="Ciclo menstrual"');
  });
});

describe("panel del ciclo: sexo declarado masculino", () => {
  const html = cycle(declared("male"));

  it("no aplica, con lo declarado y sin color", () => {
    expect(html).toContain("masculino");
    expect(html).toContain(`${NOT_APPLICABLE}.`);
    expect(html).not.toContain("data-cycle-record");
    expect(colors(html)).toEqual([]);
  });

  it("si la última lectura falló, lo declarado de antes va caducado: cian y cursiva", () => {
    const old = cycle(declared("male"), null, { unavailable: FAILED });
    expect(old).toMatch(/<span class="mark stale c-cyan"><svg[^>]*>[\s\S]*?<\/svg>masculino<\/span>/);
  });
});

describe("panel del ciclo: sexo declarado femenino", () => {
  const html = cycle(declared("female"), RECORDS);

  it("el último registro de cada indicador, con la palabra de la fuente en su idioma y la hora por format", () => {
    expect(html).toContain('data-cycle="applies"');
    expect(html).toContain("NOMBRE-FLUJO");
    expect(html).toContain('<span lang="en">CATEGORIA-DOS</span>');
    expect(html).toContain('<span class="num secondary">(2)</span>');
    expect(html).toContain('<span class="num">36,63 °C</span>');
    expect(html).toContain('<span class="num">2026-11-14 07:05 UTC</span>');
    expect(html).not.toContain("NOTA-PROPIA");
  });

  it("un indicador sin lecturas lleva la marca de dato ausente (cian)", () => {
    expect(html).toMatch(markedHtml("ring-dotted", "Sin lecturas", "cyan"));
  });

  it("sin la frase de la base por fase: «no disponible» en gris, nunca un valor supuesto", () => {
    expect(html).toContain('data-cycle-phase="unavailable"');
    expect(html).toMatch(markedHtml("slash-circle", "no disponible", "gray"));
    // Lo único con color: lo que falta (cian) y lo no disponible (gris). Un registro no avisa.
    expect(new Set(colors(html))).toEqual(new Set(["c-cyan", "c-gray"]));
  });

  it("con la frase del backend, tal cual y sin color", () => {
    const given = cycle(declared("female"), RECORDS, { phaseBaseline: "FRASE-BASE-POR-FASE" });
    expect(given).toContain("<span>FRASE-BASE-POR-FASE</span>");
    expect(given).toContain('data-cycle-phase="given"');
    expect(colors(given)).toEqual(["c-cyan"]);
  });

  it("sin datos en ningún indicador: cada uno con su marca de dato ausente", () => {
    const empty = cycle(declared("female"), RECORDS.map((record) => ({ ...record, latest: null })));
    expect(empty.match(/Sin lecturas/g)).toHaveLength(3);
    expect(empty).not.toContain("UTC");
  });

  it("si la última lectura falló, lo de antes va caducado: cian, anillo punteado y cursiva", () => {
    const old = cycle(declared("female"), RECORDS, { unavailable: FAILED });
    expect(old).toMatch(markedHtml("cross", "Sin datos: MOTIVO", "red"));
    expect(old).toMatch(/<span class="mark stale c-cyan"><svg[^>]*>[\s\S]*?<\/svg><span lang="en">CATEGORIA-DOS<\/span>/);
    expect(old).toContain('<span class="secondary stale"><span class="num">2026-11-14 07:05 UTC</span>');
    expect(html).not.toContain("stale");
  });
});

describe("panel del ciclo: cargando y sin respuesta", () => {
  it("cargando, la flecha que gira; sin respuesta, el motivo", () => {
    expect(cycle(null)).toMatch(markedHtml("refresh", "Cargando…"));
    expect(cycle(null, null, { unavailable: FAILED })).toMatch(markedHtml("cross", "Sin datos: MOTIVO", "red"));
  });
});

describe("formulario del sexo", () => {
  it("sin declarar: la palabra del backend con la marca gris de «no disponible»", () => {
    const html = sexForm(UNDECLARED);
    expect(html).toMatch(markedHtml("slash-circle", "PALABRA-NO-DECLARADO", "gray"));
    expect(html).toContain('data-crew-sex-state="undeclared"');
  });

  it("declarado: qué, quién, cuándo (por format) y el asiento, sin color", () => {
    const html = sexForm(declared("female"));
    expect(html).toContain('data-crew-sex-state="female"');
    expect(html).toContain("<dd>femenino</dd>");
    expect(html).toContain("<dd>QUIEN-DECLARA</dd>");
    expect(html).toContain('<span class="num">2026-11-14 08:30 UTC</span>');
    expect(html).toContain('<span class="num">4321</span>');
    expect(colors(html)).toEqual([]);
  });

  it("el formulario: un grupo con su leyenda, dos opciones con su etiqueta, sin ninguna elegida, y firmar desactivado", () => {
    const html = sexForm(UNDECLARED);
    expect(html).toContain('<form class="cycle-sex-form" aria-label="Declarar el sexo">');
    expect(html).toMatch(/<fieldset><legend><svg[^>]*>[\s\S]*?<\/svg>Declarar<\/legend>/);
    expect(html.match(/type="radio"/g)).toHaveLength(2);
    expect(html).not.toContain("checked");
    expect(html).toMatch(/<label class="cycle-choice"><input type="radio"[^>]*value="female"[^>]*\/>femenino<\/label>/);
    expect(html).toMatch(/<label[^>]*for="[^"]+-by"[^>]*>/);
    expect(html).toMatch(/<button class="command" type="submit" disabled="">/);
    expect(sexForm(declared("male"))).toContain("Cambiar lo declarado");
  });

  it("qué se guarda, para qué y cómo se borra: las frases del backend, plegadas", () => {
    const html = sexForm(declared("female"));
    const fold = /<details data-ui="crew-sex-privacy">[\s\S]*?<\/details>/.exec(html)?.[0] ?? "";
    for (const text of ["FRASE-QUE-SE-GUARDA", "FRASE-SOLO-EL-CICLO", "FRASE-PRIVACIDAD-Y-BORRADO"]) {
      expect(fold).toContain(text);
    }
  });

  it("en Tierra solo se lee: sin formulario", () => {
    const html = sexForm(declared("female"), { readOnly: true });
    expect(html).not.toContain("<form");
    expect(html).toContain("<dd>femenino</dd>");
  });

  it("si la última lectura falló, lo declarado de antes va en cursiva, con el motivo", () => {
    const html = sexForm(declared("female"), { unavailable: FAILED });
    expect(html).toContain('<dl class="cycle-facts stale"');
    expect(html).toMatch(markedHtml("cross", "Sin datos: MOTIVO", "red"));
  });
});

describe("sin texto clínico propio (invariante 7)", () => {
  // Lo visible que no es marcador del backend: los rótulos de la interfaz. Ninguno es una pauta.
  const pages = [
    cycle(UNDECLARED),
    cycle(declared("male"), null, { ground: true }),
    cycle(declared("female"), RECORDS),
    sexForm(UNDECLARED),
    sexForm(declared("female")),
  ];
  const ORDERS = /\b(debe|deber[íi]a|tome|tomar|acuda|consulte|suspend|administr|dosis|tratamiento|diagn[óo]stic|recomend|hormon|embaraz|anticoncepci[óo]n de emergencia)/i;

  it("ningún rótulo de la interfaz suena a orden médica ni nombra un diagnóstico", () => {
    for (const html of pages) {
      expect(visibleText(html)).not.toMatch(ORDERS);
    }
  });
});

describe("la hoja del ciclo solo usa colores de la paleta", () => {
  const css = readFileSync(fileURLToPath(new URL("./cycle.css", import.meta.url)), "utf8");

  it("no hay ningún color escrito a mano", () => {
    expect(css.replace(/\/\*[\s\S]*?\*\//g, "")).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/);
  });

  it("cada variable de color que usa existe en la paleta", () => {
    const known = new Set(Object.keys(palette).map((token) => cssVar(token as Token)));
    for (const name of new Set(css.match(/--c-[a-z-]+/g) ?? [])) {
      expect(known.has(name), name).toBe(true);
    }
  });

  it("las clases de color de los componentes son tokens de la paleta", () => {
    const tokens = new Set(Object.keys(palette).map((token) => `c-${token}`));
    for (const html of [cycle(declared("female"), RECORDS, { unavailable: FAILED }), sexForm(UNDECLARED)]) {
      for (const name of colors(html)) expect(tokens.has(name), name).toBe(true);
    }
  });
});
