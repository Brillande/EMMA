import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, taggedPictogram } from "../advisor/visibleText";
import { isPictogramName } from "../icons/registry";
import type { TestbedRidgeCell, Testbeds } from "../lib/api";
import { EMPTY_MARK, UNAVAILABLE_MARK, UNKNOWN_MARK, mark } from "../lib/marks";
import { EVIDENCE_CONTEXTS } from "../lib/provenance";
import { TestbedsPanel, TestbedsView } from "./TestbedsPanel";
import { addressesIn } from "../lib/urlWrapMarkup";
import {
  COLUMN_CONCEPTS,
  EMMA_STATUS_MARKS,
  NOT_FOUND_MARK,
  RIDGE_STATUS_MARKS,
  TESTBEDS_PICTOGRAM,
  VALIDATION_PICTOGRAMS,
  bankNames,
  columnPictogram,
  contextCell,
  emmaStatusMark,
  leftOutMark,
  ridgeStatusMark,
  validationMark,
} from "./testbeds";

// Las claves que declara el backend (`app/evidence/testbeds.py`): una validación nueva sin dibujo
// saldría con la marca de «desconocido», y esta prueba lo dice antes.
const BACKEND = readFileSync(fileURLToPath(new URL("../../../backend/app/evidence/testbeds.py", import.meta.url)), "utf-8");

function backendKeys(block: string): string[] {
  const body = new RegExp(`${block} = \\{([^}]*)\\}`).exec(BACKEND)?.[1] ?? "";
  return [...body.matchAll(/"([a-z_]+)":/g)].map((match) => match[1]!);
}

// Una fila de la matriz RIDGE como la sirve el backend: deducida salvo donde la ficha nombra el peligro.
const HAZARDS = [
  { id: "radiation", display: "radiación" },
  { id: "isolation", display: "aislamiento y confinamiento" },
  { id: "distance", display: "distancia de la Tierra" },
  { id: "gravity", display: "campos gravitatorios" },
  { id: "environment", display: "entorno hostil y cerrado" },
];
const STATUS_TEXT = { reproduces: "lo reproduce", partial: "en parte", leaves_out: "lo deja fuera", unknown: "no se sabe" };

function ridgeRow(statuses: (keyof typeof STATUS_TEXT)[], sourced: string | null = null): TestbedRidgeCell[] {
  return HAZARDS.map((hazard, index) => {
    const status = statuses[index]!;
    const fromSource = hazard.id === sourced;
    return {
      hazard: hazard.id,
      hazard_display: hazard.display,
      status,
      status_text: STATUS_TEXT[status],
      basis: fromSource ? "source" : "deduced",
      basis_text: fromSource ? "lo nombra una página del banco" : "lo deduce EMMA",
      why: fromSource ? null : `Motivo de ${hazard.display}.`,
      cited: fromSource
        ? {
            quote: "Isolation and Confinement",
            where: "ficha de la misión, «HAZARDS»",
            read_on: "2026-10-23",
            ref: "nasa-hera-mission",
            source: "NASA · HERA (ficha de la misión)",
            url: "https://www.nasa.gov/mission/hera/",
            organization: "NASA",
            date: null,
            unverified_display: ["fecha"],
          }
        : null,
    };
  });
}

// Como lo escribe el backend: la consola no lo redacta.
const TESTBEDS: Testbeds = {
  note: "Ningún banco de prueba reproduce una misión a Marte entera.",
  rule: { text: "Cada dato debe conservar el contexto experimental.", where: "knowledge-base-v1.md §3.1" },
  principle: { text: "Scientific validation ≠ Operational validation.", where: "conversación" },
  ridge: {
    note: "Qué peligro RIDGE reproduce cada banco. Es una deducción de EMMA.",
    hazards: HAZARDS,
    statuses: Object.entries(STATUS_TEXT).map(([id, text]) => ({ id, text })),
  },
  ladder: {
    title: "Escalera de evidencia y validación: Tierra → ISS → Luna → Marte",
    where: "knowledge-base-v1.md §3",
    rungs: [
      { id: "ground", environment: "Análogos terrestres", strength: "control", limitation: "no todo", use: "relaciones", banks: ["hera", "nsrl"] },
      { id: "mars", environment: "Marte", strength: "caso objetivo integrado", limitation: "no existe banco de prueba completo", use: "requisitos", banks: [] },
    ],
  },
  validations: [
    {
      id: "scientific",
      name: "Validación científica",
      what: "La relación fisiológica.",
      banks: ["nsrl"],
      emma: [
        {
          id: "mmash",
          ref: "mmash",
          context: "ground",
          bank: null,
          what: "Motor de medida y tasa de falsa alarma en Tierra.",
          does_not_show: "No valida fisiología espacial.",
          figures_in: "compliance/external-validation.md, «El resultado»",
          source: "PhysioNet · MMASH",
          url: "https://physionet.org/files/mmash/1.0.0/MMASH.zip",
        },
      ],
      emma_status: { status: "partial", text: "Validación científica de EMMA: en parte." },
      not_covered: "Ni reposo en cama ni ISS.",
    },
    {
      id: "operational",
      name: "Validación operacional",
      what: "Que una tripulación use el sistema sola.",
      banks: ["hera"],
      emma: [],
      emma_status: { status: "none", text: "Validación operacional de EMMA: ninguna." },
      not_covered: "EMMA no ha pasado por HERA.",
    },
  ],
  banks: [
    {
      id: "hera",
      name: "HERA",
      full_name: "Human Exploration Research Analog",
      where: "Johnson Space Center, Houston",
      read_on: "2026-10-21",
      rung: "ground",
      validation: "operational",
      validation_text: "operacional",
      evidence_context: "analog_isolation",
      outside_enum_text: null,
      context_basis: "Aislamiento y confinamiento en Tierra.",
      reproduces: [
        {
          quote: "Missions through HERA test how humans withstand prolonged isolation and confinement",
          where: "lista de análogos",
          read_on: "2026-10-21",
          ref: "nasa-hrp-step1-analogs",
          source: "NASA · Step 1, Earth",
          url: "https://www.nasa.gov/humans-in-space/step-1-earth-analogs-help-advance-missions-to-moon-mars/",
          organization: "NASA",
          date: "2021-02-25",
          unverified_display: [],
        },
      ],
      leaves_out: [{ what: "microgravedad", basis: "deduced", basis_text: "lo deduce EMMA", why: "En Tierra.", cited: null }],
      columns: [
        {
          id: "participants",
          label: "Participantes",
          read_on: "2026-10-22",
          quotes: [
            {
              quote: "Four dedicated explorers",
              where: "primera frase",
              read_on: "2026-10-22",
              ref: "nasa-hera-45-day-2024",
              source: "NASA · Mission Success (2024-07-02)",
              url: "https://www.nasa.gov/",
              organization: "NASA",
              date: "2024-07-02",
              unverified_display: [],
            },
          ],
          not_found: null,
        },
        {
          id: "data",
          label: "Datos disponibles",
          read_on: "2026-10-22",
          quotes: [],
          not_found: "Ninguna página leída de HERA dice dónde quedan los datos.",
        },
      ],
      ridge_read_on: "2026-10-23",
      ridge: ridgeRow(["leaves_out", "reproduces", "partial", "leaves_out", "partial"], "isolation"),
      variables_kb: "aislamiento, confinamiento",
      emma_use: "EMMA no ha pasado por HERA.",
    },
    {
      id: "nsrl",
      name: "NSRL",
      full_name: "NASA Space Radiation Laboratory",
      where: "Brookhaven",
      read_on: "2026-10-21",
      rung: "ground",
      validation: "scientific",
      validation_text: "científica",
      evidence_context: null,
      outside_enum_text: "fuera del enumerado",
      context_basis: "Muestras y equipos; ningún valor del enumerado lo cubre.",
      reproduces: [
        {
          quote: "NASA and Brookhaven National Lab have established a joint lab",
          where: "cuerpo de la página",
          read_on: "2026-10-21",
          ref: "bnl-nsrl",
          source: "Brookhaven National Laboratory · NSRL",
          url: "https://www.bnl.gov/nsrl/",
          organization: "Brookhaven National Laboratory",
          date: null,
          unverified_display: ["fecha"],
        },
      ],
      leaves_out: [
        {
          what: "personas",
          basis: "source",
          basis_text: "lo dice la fuente",
          why: null,
          cited: {
            quote: "assess the effects on biological samples and equipment",
            where: "lista de análogos",
            read_on: "2026-10-21",
            ref: "nasa-hrp-step1-analogs",
            source: "NASA · Step 1, Earth",
            url: "https://www.nasa.gov/",
            organization: "NASA",
            date: "2021-02-25",
            unverified_display: [],
          },
        },
      ],
      columns: [],
      ridge_read_on: "2026-10-23",
      ridge: ridgeRow(["reproduces", "leaves_out", "leaves_out", "leaves_out", "unknown"]),
      variables_kb: null,
      emma_use: "EMMA no usa datos de NSRL.",
    },
  ],
  not_found: ["La página no dice que ningún sitio reproduzca Marte entero."],
};

describe("las marcas de los bancos de prueba", () => {
  it("cada validación que declara el backend tiene su dibujo, y existe", () => {
    expect(Object.keys(VALIDATION_PICTOGRAMS).sort()).toEqual(backendKeys("VALIDATIONS").sort());
    for (const name of [...Object.values(VALIDATION_PICTOGRAMS), TESTBEDS_PICTOGRAM]) {
      expect(isPictogramName(name), name).toBe(true);
    }
    expect(validationMark("scientific")).toEqual(mark("flask", null));
    expect(validationMark("clinical")).toEqual(UNKNOWN_MARK);
  });

  it("«ninguna» es nada registrado todavía, nunca la marca de hecho; «en parte», la mitad", () => {
    expect(emmaStatusMark("none")).toEqual(EMPTY_MARK);
    expect(emmaStatusMark("partial")).toEqual(mark("circle-half-right", null));
    expect(emmaStatusMark("full")).toEqual(UNKNOWN_MARK);
    for (const style of Object.values(EMMA_STATUS_MARKS)) expect(style.pictogram).not.toBe("check");
  });

  it("el entorno lleva el dibujo de la procedencia; sin entorno, el gris con la palabra del backend", () => {
    for (const [context, word] of Object.entries(EVIDENCE_CONTEXTS)) {
      const cell = contextCell({ evidence_context: context, outside_enum_text: null });
      expect(cell.word).toBe(word);
      expect(cell.mark.color).toBeNull();
    }
    expect(contextCell({ evidence_context: null, outside_enum_text: "fuera del enumerado" })).toEqual({
      word: "fuera del enumerado",
      mark: UNAVAILABLE_MARK,
    });
    // Uno que la interfaz no conoce no se pinta como el más parecido.
    expect(contextCell({ evidence_context: "analog_radiation", outside_enum_text: null })).toEqual({
      word: "analog_radiation",
      mark: UNKNOWN_MARK,
    });
    // Ni una clave que el objeto hereda.
    expect(contextCell({ evidence_context: "constructor", outside_enum_text: null })).toEqual({
      word: "constructor",
      mark: UNKNOWN_MARK,
    });
  });

  it("lo que la fuente dice y lo que EMMA deduce llevan marcas distintas", () => {
    expect(leftOutMark({ basis: "source" })).not.toEqual(leftOutMark({ basis: "deduced" }));
    expect(leftOutMark({ basis: "deduced" }).pictogram).toBe("dot-half");
  });

  it("cada columna que declara el backend tiene su dibujo; lo no encontrado, la lupa sin color", () => {
    expect(Object.keys(COLUMN_CONCEPTS).sort()).toEqual(backendKeys("COLUMNS").sort());
    for (const column of Object.keys(COLUMN_CONCEPTS)) expect(isPictogramName(columnPictogram(column))).toBe(true);
    expect(columnPictogram("budget")).toBe(UNKNOWN_MARK.pictogram);
    expect(NOT_FOUND_MARK).toEqual(mark("magnifier", null));
  });

  it("cada estado RIDGE que declara el backend tiene su marca, sin color salvo «desconocido»", () => {
    expect(Object.keys(RIDGE_STATUS_MARKS).sort()).toEqual(backendKeys("RIDGE_STATUS").sort());
    for (const [status, style] of Object.entries(RIDGE_STATUS_MARKS)) {
      if (status !== "unknown") expect(style.color, status).toBeNull();
      expect(isPictogramName(style.pictogram ?? ""), status).toBe(true);
    }
    // Las cuatro se distinguen por la forma, y ninguna es la marca de «hecho».
    expect(new Set(Object.values(RIDGE_STATUS_MARKS).map((style) => style.pictogram)).size).toBe(4);
    for (const style of Object.values(RIDGE_STATUS_MARKS)) expect(style.pictogram).not.toBe("check");
    expect(ridgeStatusMark("partial")).toEqual(mark("circle-half-right", null));
    expect(ridgeStatusMark("unknown")).toEqual(UNKNOWN_MARK);
    expect(ridgeStatusMark("simula")).toEqual(UNKNOWN_MARK);
    expect(ridgeStatusMark("constructor")).toEqual(UNKNOWN_MARK);
  });

  it("los bancos se nombran por su nombre, y uno desconocido por su clave", () => {
    expect(bankNames(["nsrl", "otro"], TESTBEDS.banks)).toEqual(["NSRL", "otro"]);
  });
});

describe("<TestbedsPanel>", () => {
  it("mientras consulta: la escalera en el título y la marca de cargando", () => {
    const html = renderToStaticMarkup(createElement(TestbedsPanel));
    expect(html).toMatch(taggedPictogram("h2", TESTBEDS_PICTOGRAM, "Bancos de prueba y validación"));
    expect(html).toMatch(markedHtml("refresh", "Consultando los bancos de prueba…"));
  });

  it("pinta la frase del backend sobre la validación operacional, con el anillo punteado", () => {
    const html = renderToStaticMarkup(createElement(TestbedsView, { testbeds: TESTBEDS }));
    expect(html).toMatch(markedHtml("ring-dotted", "Validación operacional de EMMA: ninguna."));
    expect(html).toMatch(markedHtml("circle-half-right", "Validación científica de EMMA: en parte."));
    expect(html).toMatch(taggedPictogram("h3", "helmet", "Validación operacional"));
    expect(html).toMatch(taggedPictogram("h3", "flask", "Validación científica"));
  });

  it("cada banco plegado con el dibujo de su entorno; NSRL, en gris y «fuera del enumerado»", () => {
    const html = renderToStaticMarkup(createElement(TestbedsView, { testbeds: TESTBEDS }));
    expect(html).toContain('data-pictogram="door-closed"');
    expect(html).toMatch(markedHtml("slash-circle", "fuera del enumerado", "gray"));
    // La fecha que la página no muestra se dice sin verificar, en cian.
    expect(html).toMatch(markedHtml("ring-dotted", "sin verificar: fecha", "cyan"));
    // El peldaño sin bancos lo dice.
    expect(html).toMatch(markedHtml("ring-dotted", "ninguno"));
    // De cuándo es la fuente lo dice su cita (el registro exige el año en ella), y cuándo se leyó.
    expect(html).toContain('<span lang="en">NASA · Step 1, Earth</span> · lista de análogos · leído el');
    // Las frases de la fuente, en su idioma.
    expect(html).toContain('<q lang="en">NASA and Brookhaven National Lab have established a joint lab</q>');
  });

  it("las columnas de la conversación: la frase leída con su día, o la lupa con dónde se buscó", () => {
    const html = renderToStaticMarkup(createElement(TestbedsView, { testbeds: TESTBEDS }));
    expect(html).toMatch(taggedPictogram("dt", "person", "Participantes"));
    expect(html).toMatch(taggedPictogram("dt", "sheet-lines", "Datos disponibles"));
    expect(html).toContain('<q lang="en">Four dedicated explorers</q>');
    expect(html).toMatch(markedHtml("magnifier", "Ninguna página leída de HERA dice dónde quedan los datos."));
    // Cada frase dice el día en que se leyó la suya, no uno común a todo el mapa.
    expect(html).toContain("primera frase · leído el <span class=\"num\">2026-10-22</span>");
  });

  it("la matriz RIDGE: un peligro por columna con su dibujo y cada celda con su estado", () => {
    const html = renderToStaticMarkup(createElement(TestbedsView, { testbeds: TESTBEDS }));
    expect(html).toContain('aria-label="Peligros RIDGE por banco"');
    // El título lleva el medio punto de lo inferido: la matriz es deducción de EMMA.
    expect(html).toMatch(
      /<h3 class="section-gap"><svg\b[^>]*data-pictogram="dot-half"[^>]*>(?:(?!<\/svg>)[\s\S])*<\/svg>Peligros RIDGE por banco<\/h3>/,
    );
    expect(html).toContain("Qué peligro RIDGE reproduce cada banco. Es una deducción de EMMA.");
    for (const hazard of HAZARDS) expect(html).toContain(`data-pictogram="ridge-${hazard.id}"`);
    // La leyenda sale de los estados que sirve el backend, con su marca: también «no se sabe».
    expect(html).toContain('aria-label="Leyenda de la matriz RIDGE"');
    expect(html).toMatch(markedHtml("dot-small", "no se sabe", "text"));
    expect(html).toMatch(markedHtml("dot-filled", "lo reproduce"));
    expect(html).toMatch(markedHtml("circle-half-right", "en parte"));
    expect(html).toMatch(markedHtml("slash-circle", "lo deja fuera"));
    // Donde la ficha nombra el peligro, la celda lo dice con el libro abierto de lo leído.
    expect(html).toMatch(markedHtml("book-open", "lo nombra una página del banco"));
    expect(html).toMatch(markedHtml("dot-half", "lo deduce EMMA"));
    expect(html).toContain('<q lang="en">Isolation and Confinement</q>');
    expect(html).toContain("Motivo de distancia de la Tierra.");
    // En el plegable, la base va en otra línea: la mitad derecha de «en parte» y el medio punto de
    // «lo deduce EMMA» juntos solo se distinguían por la palabra.
    expect(html).not.toMatch(/en parte<\/span>\s*·/);
    expect(html).toMatch(/en parte<\/span><div class="secondary"><span class="mark"><svg\b[^>]*data-pictogram="dot-half"/);
    expect(html).toContain('hecha el <span class="num">2026-10-23</span>');
  });

  it("la matriz RIDGE pone cada celda bajo su peligro, no por su posición en la lista", () => {
    const statusesOf = (testbeds: Testbeds): string[] => {
      const html = renderToStaticMarkup(createElement(TestbedsView, { testbeds }));
      // La caja de la matriz se desplaza dentro del panel y se alcanza con el teclado (§5.40).
      const matrix =
        /<div class="ridge-matrix table-scroll" role="region" tabindex="0" aria-label="Peligros RIDGE por banco">([\s\S]*?)<\/table>/.exec(
          html,
        )?.[1] ?? "";
      expect(matrix).not.toBe("");
      const row = /<th scope="row">NSRL<\/th>([\s\S]*?)<\/tr>/.exec(matrix)?.[1] ?? "";
      return [...row.matchAll(/<\/svg>([^<]+)<\/span>/g)].map((match) => match[1]!);
    };
    const shuffled: Testbeds = {
      ...TESTBEDS,
      banks: TESTBEDS.banks.map((bank) =>
        bank.name === "NSRL" ? { ...bank, ridge: [...bank.ridge].reverse() } : bank,
      ),
    };
    const expected = ["lo reproduce", "lo deja fuera", "lo deja fuera", "lo deja fuera", "no se sabe"];
    expect(statusesOf(TESTBEDS)).toEqual(expected);
    expect(statusesOf(shuffled)).toEqual(expected);
    // Una celda que falte sale con «no se sabe», no en blanco ni con la de al lado.
    const missing: Testbeds = {
      ...TESTBEDS,
      banks: TESTBEDS.banks.map((bank) =>
        bank.name === "NSRL" ? { ...bank, ridge: bank.ridge.slice(1) } : bank,
      ),
    };
    expect(statusesOf(missing)).toEqual(["no se sabe", ...expected.slice(1)]);
  });
});

// Lo pintado, no el código: toda dirección en monoespaciada lleva `url` y se parte (§5.38.12).
describe("bancos de prueba: las direcciones pintadas se parten", () => {
  it("ningún `.num` sin `url` encierra una dirección", () => {
    const { inNum, unwrapped } = addressesIn(renderToStaticMarkup(createElement(TestbedsView, { testbeds: TESTBEDS })));
    expect(inNum).toBeGreaterThan(0);
    expect(unwrapped).toEqual([]);
  });
});
