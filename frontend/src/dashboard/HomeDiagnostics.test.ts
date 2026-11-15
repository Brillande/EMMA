import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { CrewStatus, Indicator, ProfileMatrix, VolumeSegmentation, VolumeStudy } from "../lib/api";
import { type Token, cssVar, palette } from "../lib/palette";
import type { HomeData, HomeLinks } from "./HomeBoard";
import {
  type DiagnosticsData,
  HomeDiagnosticsView,
  type LabSeries,
  TREND_ROWS,
  TREND_WINDOW_MS,
  labTrends,
  laboratoryKeys,
  latestVolume,
  previewPictogram,
} from "./HomeDiagnostics";

/**
 * «Diagnóstico integrado» de «Inicio» (lote «reservas», 2026-11-14). Sin DOM ni red: la lógica se
 * prueba sola y la vista se pinta con `renderToStaticMarkup` sobre lo recibido. Lo que vigila:
 * todo dato sale del backend (rótulos de volumen, resumen, causas, series), lo que falta se dice
 * con su marca, el visor pesado no entra en «Inicio» y no hay rótulos de «IA» ni veredictos
 * inventados.
 */

const REFERENCE = "2026-11-14T12:00:00Z";
const REF_MS = Date.parse(REFERENCE);
const DAY = 24 * 3600 * 1000;

const indicator = (key: string, over: Partial<Indicator> = {}): Indicator =>
  ({
    key,
    display: key,
    display_es: key.toUpperCase(),
    unit: "U/L",
    domain: "nutrition",
    decimals: 0,
    measurement_cost: { mode: "laboratory" },
    ...over,
  }) as unknown as Indicator;

const segmentation = (over: Partial<VolumeSegmentation> = {}): VolumeSegmentation =>
  ({
    ledger_index: 20,
    recorded: "2026-11-10T08:00:00Z",
    preset: "higado",
    preset_nombre: "Hígado",
    estado: "segmentación automática sin validar",
    modalidad: "CT",
    ventana_hu: [-100, 200],
    estructuras: [{ key: "liver", nombre: "hígado", etiqueta: 1, malla: null, volumen_ml: 1532.46 }],
    lesiones: [],
    volumen_organo_ml: 1532.46,
    ...over,
  }) as VolumeSegmentation;

const study = (over: Partial<VolumeStudy> = {}): VolumeStudy =>
  ({
    ledger_index: 10,
    recorded: "2026-11-09T08:00:00Z",
    subject: "crew-01",
    modality: "CT",
    shape: [512, 512, 100],
    voxel_mm: [1, 1, 1],
    source: "upload",
    recorded_by: "CMO",
    segmentations: [],
    ...over,
  }) as VolumeStudy;

const status = {
  subject: "crew-01",
  summary: "Resumen redactado por el backend.",
  overall_level: "watch",
  domains: {
    radiation: { score: 0, level: "nominal", drivers: [] },
    cardiovascular: { score: 1, level: "watch", drivers: ["Causa del backend número uno", "otra"] },
  },
  data: { reference_time: REFERENCE, observations: 100 },
  mission: { start: "2026-10-01T00:00:00Z" },
} as unknown as CrewStatus;

const matrix = {
  profiles: [
    {
      id: "mars-transit",
      display: "tránsito a Marte",
      declared: true,
      cells: [{ key: "medical_capability", label: "capacidad o autonomía médica", text: "Frase leída en la fuente." }],
    },
  ],
} as unknown as ProfileMatrix;

const alt = indicator("alt");
const ast = indicator("ast");

const home = (over: Partial<HomeData> = {}): HomeData =>
  ({
    status,
    reference: REF_MS,
    indicators: { state: "ready", value: [alt, ast] },
    catalog: new Map([
      ["alt", alt],
      ["ast", ast],
    ]),
    matrix,
    matrixFailure: null,
    shownRoute: "mars-transit",
    lowest: "nominal",
    ...over,
  }) as unknown as HomeData;

const data = (over: Partial<DiagnosticsData> = {}): DiagnosticsData => ({
  volumes: { state: "ready", value: [] },
  segmenter: { state: "ready", value: { available: false, note: "Motivo del backend: no hay segmentador." } },
  ultrasound: { state: "ready", value: [] },
  reports: { state: "ready", value: [] },
  labs: { state: "ready", value: [] },
  ...over,
});

const links: HomeLinks = {
  openSection: () => undefined,
  sectionName: (key) =>
    ({ imaging: "Imagen e informes", body: "Cuerpo", log: "Diario y pruebas", hazards: "Peligros y alertas" })[key] ?? null,
};

const render = (props: { home?: HomeData; data?: DiagnosticsData; links?: HomeLinks; profileId?: string | null }) =>
  renderToStaticMarkup(
    createElement(HomeDiagnosticsView, {
      home: props.home ?? home(),
      data: props.data ?? data(),
      links: props.links,
      profileId: props.profileId,
    }),
  );

describe("el último volumen", () => {
  it("es la segmentación más reciente de cualquier estudio", () => {
    const older = study({ ledger_index: 1, segmentations: [segmentation({ ledger_index: 2, recorded: "2026-11-01T00:00:00Z" })] });
    const newer = study({ ledger_index: 3, recorded: "2026-10-01T00:00:00Z", segmentations: [segmentation({ ledger_index: 4 })] });
    const found = latestVolume([older, newer]);
    expect(found?.study.ledger_index).toBe(3);
    expect(found?.segmentation?.ledger_index).toBe(4);
  });

  it("sin segmentaciones, el estudio más reciente; sin estudios, nada", () => {
    const found = latestVolume([study({ ledger_index: 1 }), study({ ledger_index: 2, recorded: "2026-11-12T00:00:00Z" })]);
    expect(found?.study.ledger_index).toBe(2);
    expect(found?.segmentation).toBeNull();
    expect(latestVolume([])).toBeNull();
  });

  it("el dibujo del hígado solo para el preset que lo segmenta", () => {
    expect(previewPictogram("higado")).toBe("liver");
    expect(previewPictogram("esqueleto")).toBe("picture");
    expect(previewPictogram(undefined)).toBe("picture");
  });
});

describe("las tendencias de laboratorio", () => {
  it("son los indicadores del catálogo medidos en laboratorio", () => {
    expect(laboratoryKeys([alt, indicator("heart-rate", { measurement_cost: { mode: "continuous" } as Indicator["measurement_cost"] })])).toEqual([
      "alt",
    ]);
  });

  it("solo lecturas de los 30 días hasta la referencia, la medida más reciente primero", () => {
    const series: LabSeries[] = [
      { key: "alt", readings: [{ at: REF_MS - 40 * DAY, value: 30 }, { at: REF_MS - 5 * DAY, value: 28 }] },
      { key: "ast", readings: [{ at: REF_MS - 1 * DAY, value: 24 }] },
      { key: "ggt", readings: [{ at: REF_MS - 1 * DAY, value: 9 }] }, // sin ficha: no se enseña
      { key: "old", readings: [{ at: REF_MS - TREND_WINDOW_MS - DAY, value: 1 }] },
    ];
    const rows = labTrends(series, home().catalog, REF_MS);
    expect(rows.map((row) => row.indicator.key)).toEqual(["ast", "alt"]);
    expect(rows[1]?.readings).toHaveLength(1);
    expect(rows[1]?.last.value).toBe(28);
  });

  it("como mucho las que caben", () => {
    const keys = ["a", "b", "c", "d", "e", "f"];
    const catalog = new Map(keys.map((key) => [key, indicator(key)]));
    const series = keys.map((key, index) => ({ key, readings: [{ at: REF_MS - index * DAY, value: index }] }));
    expect(labTrends(series, catalog, REF_MS)).toHaveLength(TREND_ROWS);
  });
});

describe("la vista", () => {
  it("sin volumen: lo dice, con el motivo del backend del segmentador en gris", () => {
    const html = render({});
    expect(html).toContain("Sin volúmenes registrados.");
    expect(html).toContain("Motivo del backend: no hay segmentador.");
    expect(html).toMatch(/c-gray[^>]*>.*Motivo del backend/);
    expect(html).toContain("No es un diagnóstico a bordo.");
  });

  it("con segmentación: sus rótulos del backend, sin cargar el visor de Polaris", () => {
    const html = render({ data: data({ volumes: { state: "ready", value: [study({ segmentations: [segmentation()] })] } }) });
    expect(html).toContain("Hígado (Polaris)");
    expect(html).toContain("segmentación automática sin validar");
    expect(html).toContain("1532,5");
    expect(html).not.toContain("<iframe");
    expect(html).not.toContain("/polaris/");
  });

  it("el análisis es el del backend: nivel, resumen y causas, sin «IA» ni veredictos inventados", () => {
    const html = render({});
    expect(html).toContain("Resumen redactado por el backend.");
    expect(html).toContain("Causa del backend número uno");
    expect(html).not.toMatch(/\bIA\b|Sin anomalías|correlaci/i);
  });

  it("se adapta a la ubicación: el perfil en el título y su capacidad médica del backend", () => {
    const html = render({});
    expect(html).toContain("(Tránsito a Marte)");
    expect(html).toContain("Frase leída en la fuente.");
    expect(render({ profileId: "leo" })).not.toContain("Frase leída en la fuente.");
  });

  it("las tendencias con sus cifras del catálogo; sin ninguna, la marca de dato ausente", () => {
    const html = render({ data: data({ labs: { state: "ready", value: [{ key: "alt", readings: [{ at: REF_MS - DAY, value: 28 }] }] } }) });
    expect(html).toContain('data-lab="alt"');
    expect(html).toContain("U/L");
    expect(render({})).toMatch(/c-cyan[^>]*>.*sin analíticas en los últimos 30 días/);
  });

  it("con los accesos de la consola, cada prueba lleva a su sección; sin ellos, ningún botón", () => {
    const html = render({ links });
    expect(html).toContain('aria-label="Abrir Imagen e informes: Ecografía / ultrasonido"');
    expect(html).toContain('aria-label="Abrir Cuerpo: Biomarcadores"');
    expect(html).toContain('aria-label="Abrir Diario y pruebas: Otras pruebas (PVT, cognición, dolor)"');
    expect(html).toContain('aria-label="Abrir Peligros y alertas: detalle del análisis"');
    expect(render({})).not.toContain("<button");
  });

  it("los recuentos dicen lo que hay o que no hay nada", () => {
    const html = render({ data: data({ reports: { state: "ready", value: [{ kind: "analitica" }, { kind: "alta" }] as never } }) });
    expect(html).toMatch(/<span class="num">1<\/span> informe</);
    expect(html).toContain("sin estudios");
  });
});

describe("el módulo y su hoja", () => {
  const source = readFileSync(fileURLToPath(new URL("./HomeDiagnostics.tsx", import.meta.url)), "utf8");
  const css = readFileSync(fileURLToPath(new URL("./homeDiagnostics.css", import.meta.url)), "utf8");

  it("no trae el visor pesado ni nada del borrador de interpretación", () => {
    expect(source).not.toMatch(/from "[^"]*(PolarisViewer|VolumeViewer|interpret)/);
    // Ni perezoso: «Inicio» no carga el visor ni a demanda.
    expect(source).not.toMatch(/import\(/);
  });

  it("solo usa colores de la paleta", () => {
    const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, "");
    expect(withoutComments).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/);
    const known = new Set(Object.keys(palette).map((token) => cssVar(token as Token)));
    for (const name of new Set(css.match(/--c-[a-z-]+/g) ?? [])) expect(known.has(name), name).toBe(true);
  });

  it("ninguna letra por debajo del suelo de 0,875 rem", () => {
    const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, "");
    for (const [, value] of withoutComments.matchAll(/font-size:\s*([^;}]+)/g)) {
      const match = (value ?? "").trim().match(/^([\d.]+)rem$/);
      expect(match, value).not.toBeNull();
      expect(Number(match?.[1])).toBeGreaterThanOrEqual(0.875);
    }
  });
});
