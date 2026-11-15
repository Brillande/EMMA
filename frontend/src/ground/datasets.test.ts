import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, taggedPictogram, textNodes } from "../advisor/visibleText";
import { isPictogramName } from "../icons/registry";
import type { DatasetCatalog, DatasetQuote, HumanDataset, HumanDatasets } from "../lib/api";
import { EMPTY_MARK, UNAVAILABLE_MARK, UNKNOWN_MARK, mark } from "../lib/marks";
import { DatasetsPanel, DatasetsView } from "./DatasetsPanel";
import { addressesIn } from "../lib/urlWrapMarkup";
import {
  ACCESS_MARKS,
  CATALOG_PICTOGRAM,
  CONTROL_STATUS_MARKS,
  DATASETS_PICTOGRAM,
  NOT_FOUND_MARK,
  PHASE_STATUS_MARKS,
  accessMark,
  cellMark,
  controlStatusMark,
  emmaUseMark,
  phaseStatusMark,
} from "./datasets";

// Las claves que declara el backend (`app/evidence/human_datasets.py`): un estado o un acceso nuevo
// sin dibujo saldría con la marca de «desconocido», y esta prueba lo dice antes.
const BACKEND = readFileSync(
  fileURLToPath(new URL("../../../backend/app/evidence/human_datasets.py", import.meta.url)),
  "utf-8",
);

function backendKeys(block: string): string[] {
  const body = new RegExp(`${block} = \\{([^}]*)\\}`).exec(BACKEND)?.[1] ?? "";
  return [...body.matchAll(/"([a-z_]+)":/g)].map((match) => match[1]!);
}

const quote = (text: string, ref = "osd-343", readOn = "2026-10-22"): DatasetQuote => ({
  quote: text,
  where: "descripción del estudio",
  read_on: readOn,
  ref,
  source: "NASA OSDR · OSD-343",
  url: "https://osdr.nasa.gov/bio/repo/data/studies/OSD-343",
  unverified_display: [],
});

const notFound = {
  status: "not_found",
  status_text: "buscado y no encontrado",
  labels: [],
  cited: [],
  why: null,
  searched: "descripción y protocolos de osd/meta/343",
};

const SEGMENTS = [
  { label: "L-30 → Flight", phase: "pre" },
  { label: "Flight → R+0", phase: "inflight" },
  { label: "R+0 → R+7", phase: "post" },
];

// Como lo escribe el backend: la consola no lo redacta.
const OSD_343: HumanDataset = {
  id: "osd-343",
  name: "OSD-343",
  ref: "osd-343",
  title: "Comprehensive multi-omics analysis",
  source: "NASA OSDR · OSD-343",
  url: "https://osdr.nasa.gov/bio/repo/data/studies/OSD-343",
  population: "human_and_animal",
  population_display: "humano y animal",
  evidence_context: null,
  outside_enum_text: "fuera del enumerado",
  open_population: "animal",
  open_population_display: "animal",
  open_population_note: "Los ficheros que deposita en OSDR son de ratón.",
  kb_row: "OSD-343 | integración multi-ómica/humana según estudio | relaciones longitudinales",
  kb_where: "§8",
  subjects: [quote("human metrics from 59 astronauts, and confirmatory data from NASA's Twin Study")],
  variables: [{ what: "Multi-ómica", ...quote("a multi-omics, systems biology approach") }],
  areas: null,
  phases: { pre: notFound, inflight: notFound, post: notFound },
  analog_schedule: null,
  controls: {
    status: "listed",
    status_text: "con controles",
    items: [
      {
        kind: "ground",
        kind_text: "control en Tierra",
        population: "animal",
        population_display: "animal",
        ...quote("ground-based habitat controls placed within in environmental chambers", "osd-343", "2026-10-23"),
      },
    ],
    absent: [],
    why: null,
    searched: null,
  },
  ladder: SEGMENTS.map((segment) => ({
    segment: segment.label,
    phase: segment.phase,
    labels: [],
    status: "not_found",
    text: "buscado y no encontrado",
  })),
  access: {
    level: "open",
    level_text: "abierto",
    basis: "deduced",
    basis_text: "lo deduce EMMA; la fuente no lo dice",
    cited: [],
    path: null,
    why: "La ficha de OSDR lista los ficheros sin pedir solicitud.",
    searched: null,
  },
  emma_use: {
    used: true,
    used_text: "en uso",
    text: "Respaldo de mecanismo.",
    where: "backend/app/evidence/links.py",
    cites: "osd-343",
  },
  role: {
    level: "KNOWLEDGE",
    level_text: "evidencia histórica o mecanística",
    level_why: "Multi-ómica de datos ya recogidos: evidencia mecanística.",
    fitness: "contextualize",
    fitness_text: "solo contextualizar",
    fitness_why: "Sus ficheros abiertos son de ratón: nada que contrastar con el motor.",
    basis_text: "deducción de EMMA sobre lo leído",
  },
  caveat: "Los ficheros abiertos son de ratón.",
};

const SOMA: HumanDataset = {
  ...OSD_343,
  id: "inspiration4-soma",
  name: "Inspiration4 / SOMA",
  population: "human",
  population_display: "humano",
  evidence_context: "spaceflight",
  outside_enum_text: null,
  open_population: "human",
  open_population_display: "humano",
  open_population_note: null,
  phases: {
    pre: { ...notFound, status: "labels", status_text: "tomas con día", labels: ["L-3"], searched: null },
    inflight: {
      ...notFound,
      status: "labels",
      status_text: "tomas con día",
      labels: ["FD1", "FD2", "FD3"],
      searched: null,
      cited: [quote("three in-flight (flight day 1 (FD1), FD2 and FD3)", "overbey-2024-soma")],
    },
    post: { ...notFound, status: "labels", status_text: "tomas con día", labels: ["R+45"], searched: null },
  },
  ladder: [
    { segment: "L-30 → Flight", phase: "pre", labels: ["L-3"], status: "labels", text: null },
    { segment: "Flight → R+0", phase: "inflight", labels: ["FD1", "FD2", "FD3"], status: "labels", text: null },
    { segment: "R+0 → R+7", phase: "post", labels: [], status: "labels", text: "sin toma en este tramo" },
  ],
  access: {
    level: "mixed",
    level_text: "abierto en parte; lo sensible, de acceso controlado",
    basis: "source",
    basis_text: "lo dice la fuente",
    cited: [quote("as well as controlled access to more sensitive data", "overbey-2024-soma")],
    path: null,
    why: null,
    searched: null,
  },
  emma_use: { used: false, used_text: "sin uso", text: "Ninguno: de esta misión EMMA usa solo el hemograma.", where: null, cites: null },
  controls: {
    status: "listed",
    status_text: "con controles",
    items: [
      {
        kind: "own_baseline",
        kind_text: "cada sujeto, su propio control antes del vuelo",
        population: "human",
        population_display: "humano",
        ...quote("serve as their own controls (within-subjects design)", "jones-2024-inspiration4", "2026-10-23"),
      },
    ],
    absent: [quote("This study did not have age- and sex-matched controls on Earth", "jones-2024-inspiration4", "2026-10-23")],
    why: null,
    searched: null,
  },
};

const notApplicable = {
  status: "not_applicable",
  status_text: "no procede",
  labels: [],
  cited: [],
  why: "Sin vuelo: reposo en cama en Tierra.",
  searched: null,
};

const AGBRESA: HumanDataset = {
  ...OSD_343,
  id: "agbresa",
  name: "AGBRESA (reposo en cama)",
  ref: "clement-2022-agbresa",
  population: "human",
  population_display: "humano",
  evidence_context: "analog_bedrest",
  outside_enum_text: null,
  open_population: null,
  open_population_display: null,
  open_population_note: null,
  kb_row: ":envihab / bed rest | -6° head-down tilt | fisiología controlada y prueba de contramedidas",
  kb_where: "§3.1",
  phases: { pre: notApplicable, inflight: notApplicable, post: notApplicable },
  ladder: SEGMENTS.map((segment) => ({
    segment: segment.label,
    phase: segment.phase,
    labels: [],
    status: "not_applicable",
    text: "no procede",
  })),
  analog_schedule: [
    { stages: ["RECOVERY"], ...quote("a 14-days recovery (R+) phase (R+0 through R+13)", "clement-2022-agbresa", "2026-10-23") },
  ],
  controls: {
    status: "listed",
    status_text: "con controles",
    items: [
      {
        kind: "analog_control",
        kind_text: "grupo del análogo sin la contramedida",
        population: "human",
        population_display: "humano",
        ...quote("a passive control (Ctrl) group not exposed to centrifugation", "clement-2022-agbresa", "2026-10-23"),
      },
    ],
    absent: [],
    why: null,
    searched: null,
  },
  access: {
    level: "authors",
    level_text: "a petición a sus autores",
    basis: "source",
    basis_text: "lo dice la fuente",
    cited: [quote("will be made available by the authors", "clement-2022-agbresa", "2026-10-23")],
    path: null,
    why: null,
    searched: null,
  },
};

const TWINS: HumanDataset = {
  ...SOMA,
  id: "twins-study",
  name: "NASA Twins Study",
  areas: {
    count: 2,
    cited: quote("split into 2 investigations", "nasa-twins-study-research", "2026-10-23"),
    items: [
      { name: "Metabolomics", what: "Metabolómica", ...quote("Metabolomic and Genomic Markers", "nasa-twins-study-research", "2026-10-23") },
      { name: "Immunome", what: "Inmunoma", ...quote("Characterizing Personalized Changes", "nasa-twins-study-research", "2026-10-23") },
    ],
  },
};

const CATALOG: DatasetCatalog = {
  id: "data-nasa-gov",
  name: "data.nasa.gov",
  ref: "nasa-open-data-portal",
  title: "Welcome - NASA Open Data Portal",
  source: "NASA · Open Data Portal (data.nasa.gov)",
  url: "https://data.nasa.gov/",
  kb_row: "data.nasa.gov | catálogo de metadatos | descubrimiento sistemático",
  kb_where: "§8",
  what: [quote("Data.nasa.gov describes NASA datasets rather than hosting the data itself.", "nasa-open-data-portal", "2026-10-23")],
  access: { ...AGBRESA.access, level: "open", level_text: "abierto", cited: [] },
  emma_use: { used: false, used_text: "sin uso", text: "Ninguno.", where: null, cites: null },
  caveat: "Un catálogo de metadatos: no aloja los datos.",
};

const BODY: HumanDatasets = {
  note: "Qué conjuntos de datos humanos hay.",
  read_on: "2026-10-22",
  task: { text: "Twins Study + OSD-343 + datasets humanos", where: "knowledge-base-v1.md §15 (P0)" },
  rule: { text: "La estrategia de datos debe separar INPUT, KNOWLEDGE y CONTEXT.", where: "knowledge-base-v1.md §8" },
  fitness_rule: {
    text: "y si sirven para entrenar, validar o simplemente contextualizar nuestro modelo.",
    where: "conversacion-ideacion-v1.md",
  },
  phases: { pre: "antes del vuelo", inflight: "en vuelo", post: "después del vuelo" },
  milestones: { text: "L-30 → Flight → R+0", where: "conversación", segments: SEGMENTS },
  analog_pattern: {
    text: "PRE → EXPOSURE → COUNTERMEASURE → POST → RECOVERY",
    where: "knowledge-base-v1.md §3.2",
    points: ["PRE", "EXPOSURE", "COUNTERMEASURE", "POST", "RECOVERY"],
  },
  controls_rule: {
    points: ["Flight sample", "In-flight control", "Ground control", "Pre-flight", "Post-flight"],
    where: "conversación (Biolab)",
  },
  datasets: [SOMA, OSD_343, AGBRESA, TWINS],
  catalogs: [CATALOG],
  cipher: {
    name: "CIPHER",
    full_name: "Complement of Integrated Protocols for Human Exploration Research",
    what: quote("This suite of 14 studies", "nasa-cipher"),
    studies: ["Bone Health", "Spaceflight Standard Measures"],
    studies_where: "lista de estudios de la página",
    cohort: quote("study up to 30 astronauts", "nasa-cipher-experiments-2023"),
    ladder: [{ id: "short", ...quote("Short (less than 3.5 months in space)", "nasa-cipher-experiments-2023") }],
    phases: {
      pre: {
        status: "stated",
        status_text: "la fuente dice que hay tomas, sin día",
        labels: [],
        cited: [quote("This information is gathered before, during, and after missions", "nasa-cipher")],
        why: null,
        searched: "ninguna página da días L- de las tomas",
      },
    },
    ladder_cells: [
      { segment: "L-30 → Flight", phase: "pre", labels: [], status: "stated", text: "la fuente dice que hay tomas, sin día" },
    ],
    access: {
      level: "not_found",
      level_text: "buscado y no encontrado",
      basis: "not_found",
      basis_text: "buscado y no encontrado",
      cited: [],
      path: null,
      why: null,
      searched: "ninguna dice cómo se accede",
    },
    emma_study: "Spaceflight Standard Measures",
    emma_use: {
      used: true,
      used_text: "en uso",
      text: "En el coste de medir.",
      where: "backend/app/data/measurement_cost.json",
      cites: "hardy-2025-spaceflight-standard-measures",
    },
    role: {
      level: "KNOWLEDGE",
      level_text: "evidencia histórica o mecanística",
      level_why: "Catorce estudios del HRP: evidencia histórica cuando se publique.",
      fitness: "contextualize",
      fitness_text: "solo contextualizar",
      fitness_why: "Sin datos accesibles leídos, solo contextualiza.",
      basis_text: "deducción de EMMA sobre lo leído",
    },
  },
  not_found: ["Una API pública de constantes vitales de astronautas: no existe."],
};

describe("las marcas del mapa de conjuntos de datos", () => {
  it("cada estado de fase y cada acceso que declara el backend tiene su dibujo, y existe", () => {
    expect(Object.keys(PHASE_STATUS_MARKS).sort()).toEqual(backendKeys("PHASE_STATUS").sort());
    expect(Object.keys(ACCESS_MARKS).sort()).toEqual(backendKeys("ACCESS_LEVELS").sort());
    for (const style of [...Object.values(PHASE_STATUS_MARKS), ...Object.values(ACCESS_MARKS)]) {
      expect(isPictogramName(style.pictogram ?? ""), String(style.pictogram)).toBe(true);
      // Ninguna es la marca de «hecho».
      expect(style.pictogram).not.toBe("check");
    }
    expect(isPictogramName(DATASETS_PICTOGRAM)).toBe(true);
    expect(phaseStatusMark("otro")).toEqual(UNKNOWN_MARK);
    expect(accessMark("otro")).toEqual(UNKNOWN_MARK);
  });

  it("cada estado de los controles que declara el backend tiene su dibujo, y no es el de «hecho»", () => {
    expect(Object.keys(CONTROL_STATUS_MARKS).sort()).toEqual(backendKeys("CONTROL_STATUS").sort());
    for (const style of Object.values(CONTROL_STATUS_MARKS)) {
      expect(isPictogramName(style.pictogram ?? ""), String(style.pictogram)).toBe(true);
      expect(style.pictogram).not.toBe("check");
    }
    expect(controlStatusMark("not_found")).toEqual(NOT_FOUND_MARK);
    expect(controlStatusMark("not_applicable")).toEqual(UNAVAILABLE_MARK);
    expect(controlStatusMark("none")).toEqual(EMPTY_MARK);
    expect(controlStatusMark("otro")).toEqual(UNKNOWN_MARK);
    expect(isPictogramName(CATALOG_PICTOGRAM)).toBe(true);
  });

  it("buscado y no encontrado no es lo mismo que «no hay» ni que «no procede»", () => {
    expect(phaseStatusMark("not_found")).toEqual(NOT_FOUND_MARK);
    expect(NOT_FOUND_MARK.color).toBe("cyan");
    expect(phaseStatusMark("none")).toEqual(EMPTY_MARK);
    expect(phaseStatusMark("not_applicable")).toEqual(UNAVAILABLE_MARK);
    expect(new Set([NOT_FOUND_MARK, EMPTY_MARK, UNAVAILABLE_MARK].map((style) => style.pictogram)).size).toBe(3);
  });

  it("un tramo con días lleva el calendario; una fase con días, pero no en ese tramo, nada registrado", () => {
    expect(cellMark({ labels: ["R+1"], status: "labels" })).toEqual(phaseStatusMark("labels"));
    expect(cellMark({ labels: [], status: "labels" })).toEqual(EMPTY_MARK);
    expect(cellMark({ labels: [], status: "not_found" })).toEqual(NOT_FOUND_MARK);
  });

  it("el candado abierto solo para lo abierto; lo que pide permiso, la llave", () => {
    expect(accessMark("open")).toEqual(mark("padlock-open", null));
    expect(accessMark("file_open")).toEqual(mark("padlock-open", null));
    expect(accessMark("controlled")).toEqual(accessMark("request"));
    expect(accessMark("controlled").pictogram).not.toBe("padlock-open");
    expect(accessMark("mixed").pictogram).not.toBe("padlock-open");
    // A petición a sus autores también hay que pedirlo: la llave, no el candado abierto.
    expect(accessMark("authors")).toEqual(accessMark("request"));
  });

  it("sin uso en EMMA es nada registrado, no la marca del sistema", () => {
    expect(emmaUseMark({ used: false })).toEqual(EMPTY_MARK);
    expect(emmaUseMark({ used: true }).pictogram).toBe("gear");
  });
});

describe("<DatasetsPanel>", () => {
  it("mientras consulta: el cilindro en el título y la marca de cargando", () => {
    const html = renderToStaticMarkup(createElement(DatasetsPanel));
    expect(html).toMatch(taggedPictogram("h2", DATASETS_PICTOGRAM, "Conjuntos de datos humanos y CIPHER"));
    expect(html).toMatch(markedHtml("refresh", "Consultando el mapa de conjuntos de datos…"));
  });

  const html = renderToStaticMarkup(createElement(DatasetsView, { body: BODY }));

  it("la escalera: los días leídos en su tramo, y las palabras del backend donde no hay", () => {
    expect(html).toContain('<span class="num">FD1 · FD2 · FD3</span>');
    expect(html).toMatch(markedHtml("ring-dotted", "sin toma en este tramo"));
    expect(html).toMatch(markedHtml("magnifier", "buscado y no encontrado", "cyan"));
  });

  it("OSD-343: plegado con la huella de lo que no es solo humano, y ficheros abiertos de ratón", () => {
    expect(html).toContain('data-pictogram="person-paw"');
    expect(html).toMatch(markedHtml("paw", "animal", "yellow"));
    expect(textNodes(html)).toContain("Los ficheros que deposita en OSDR son de ratón.");
    expect(html).toMatch(markedHtml("slash-circle", "fuera del enumerado", "gray"));
  });

  it("el acceso y el uso en EMMA, con la palabra del backend", () => {
    expect(html).toMatch(markedHtml("padlock-open", "abierto"));
    expect(html).toMatch(markedHtml("circle-half-right", "abierto en parte; lo sensible, de acceso controlado"));
    expect(html).toMatch(markedHtml("ring-dotted", "sin uso"));
    expect(html).toMatch(markedHtml("gear", "en uso"));
  });

  it("el papel y la aptitud, tal cual los rotula el backend y sin marca: son una deducción de EMMA", () => {
    const text = textNodes(html);
    expect(html).toContain("y si sirven para entrenar, validar o simplemente contextualizar nuestro modelo.");
    expect(html).toContain('<span lang="en">KNOWLEDGE</span> · evidencia histórica o mecanística');
    expect(text).toContain("solo contextualizar");
    expect(text).toContain("Sus ficheros abiertos son de ratón: nada que contrastar con el motor.");
    expect(text).toContain("Sin datos accesibles leídos, solo contextualiza.");
    // El rótulo de deducción, junto al papel y junto a la aptitud de cada conjunto y de CIPHER, y
    // siempre en texto secundario llano: ninguna vez dentro de una marca (`span.mark`).
    const plain = html.match(/<span class="secondary"> · deducción de EMMA sobre lo leído<\/span>/g) ?? [];
    expect(plain.length).toBe(2 * (BODY.datasets.length + 1));
    expect(html.split("deducción de EMMA sobre lo leído").length - 1).toBe(plain.length);
  });

  it("CIPHER: sus estudios, y sin días ni acceso que sus páginas no den", () => {
    expect(html).toMatch(taggedPictogram("h3", "clipboard", "CIPHER ", ' class="section-gap"'));
    expect(html).toContain("Bone Health · Spaceflight Standard Measures");
    expect(html).toContain('<q lang="en">Short (less than 3.5 months in space)</q>');
    expect(html).toContain("ninguna página da días L- de las tomas");
    expect(html).toMatch(markedHtml("book-open", "la fuente dice que hay tomas, sin día"));
    expect(html).toContain("<th scope=\"row\">CIPHER</th>");
  });

  it("las frases de la fuente, en su idioma y con el día de lectura", () => {
    expect(html).toContain(
      '<q lang="en">human metrics from 59 astronauts, and confirmatory data from NASA&#x27;s Twin Study</q>',
    );
    expect(html).toContain("leído el");
  });

  it("cada frase con su día de lectura, no el del fichero", () => {
    expect(textNodes(html)).toContain("2026-10-22");
    expect(textNodes(html)).toContain("2026-10-23");
  });

  it("los controles: los de OSD-343 son animales, con la huella; Inspiration4, su propio control", () => {
    expect(html).toMatch(markedHtml("paw", "control en Tierra · animal", "yellow"));
    expect(html).toContain('<q lang="en">serve as their own controls (within-subjects design)</q>');
    expect(html).toContain('<q lang="en">This study did not have age- and sex-matched controls on Earth</q>');
    expect(html).toMatch(markedHtml("bars-two", "con controles"));
    expect(textNodes(html)).toContain("Flight sample · In-flight control · Ground control · Pre-flight · Post-flight");
  });

  it("el reposo en cama: sin días de vuelo, con su calendario y su acceso a petición de los autores", () => {
    expect(html).toContain("<th scope=\"row\">AGBRESA (reposo en cama)</th>");
    expect(html).toMatch(markedHtml("slash-circle", "no procede", "gray"));
    expect(html).toContain('<q lang="en">a 14-days recovery (R+) phase (R+0 through R+13)</q>');
    expect(textNodes(html)).toContain("Base de conocimiento §3.1");
    expect(html).toMatch(markedHtml("key-bit", "a petición a sus autores"));
  });

  it("las áreas del Twins Study, una por una, con su frase", () => {
    expect(textNodes(html)).toContain("Áreas");
    expect(html).toContain('<span lang="en">Immunome</span> · Inmunoma');
    expect(html).toContain('<q lang="en">split into 2 investigations</q>');
  });

  it("los catálogos, aparte y sin población", () => {
    expect(html).toMatch(taggedPictogram("h3", CATALOG_PICTOGRAM, "Catálogos", ' class="section-gap"'));
    expect(html).toContain('aria-label="Catálogo data.nasa.gov"');
    expect(html).toContain("Un catálogo de metadatos: no aloja los datos.");
  });
});

// Lo pintado, no el código: toda dirección en monoespaciada lleva `url` y se parte (§5.38.12).
describe("datos humanos: las direcciones pintadas se parten", () => {
  it("ningún `.num` sin `url` encierra una dirección", () => {
    const { inNum, unwrapped } = addressesIn(renderToStaticMarkup(createElement(DatasetsView, { body: BODY })));
    expect(inNum).toBeGreaterThan(0);
    expect(unwrapped).toEqual([]);
  });
});
