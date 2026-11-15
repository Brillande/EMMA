import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { CrewStatus, Indicator, ProfileMatrix, VolumeSegmentation, VolumeStudy } from "../lib/api";
import { type Token, cssVar, palette } from "../lib/palette";
import type { HomeData, HomeLinks } from "./HomeBoard";
import { FAILURE_MARK } from "../lib/marks";
import {
  DIAGNOSTICS_CLOSED,
  type DiagnosticsAction,
  type DiagnosticsData,
  type DiagnosticsUi,
  HomeDiagnosticsView,
  diagnosticsReducer,
  viewerKeyAction,
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

  it("cada prueba es un mando que se despliega, haya o no accesos de la consola", () => {
    for (const html of [render({}), render({ links })]) {
      for (const key of ["ultrasound", "biomarkers", "lab-reports", "other"]) {
        expect(html).toMatch(new RegExp(`data-test="${key}"><button type="button" class="dx-test" aria-expanded="false"`));
      }
      // Ya no llevan a las pestañas apartadas de esta versión.
      expect(html).not.toMatch(/Abrir (Imagen e informes|Cuerpo|Diario y pruebas)/);
    }
    expect(render({ links })).toContain('aria-label="Abrir Peligros y alertas: detalle del análisis"');
  });

  it("los recuentos dicen lo que hay o que no hay nada", () => {
    const html = render({ data: data({ reports: { state: "ready", value: [{ kind: "analitica" }, { kind: "alta" }] as never } }) });
    expect(html).toMatch(/<span class="num">1<\/span> informe</);
    expect(html).toContain("sin estudios");
  });
});

/** Pulsar: la acción que manda el mando, por el reductor, y la vista con lo que queda abierto. */
const press = (ui: DiagnosticsUi, action: DiagnosticsAction) => diagnosticsReducer(ui, action);
const renderOpen = (ui: DiagnosticsUi, over: Partial<DiagnosticsData> = {}) =>
  renderToStaticMarkup(createElement(HomeDiagnosticsView, { home: home(), data: data(over), ui }));

/** El trozo de una prueba: desde su `<li>` hasta la prueba siguiente o el final de la tarjeta. */
const detailOf = (html: string, key: string) =>
  html.split(`data-test="${key}"`)[1]?.split(/data-test="|<\/article>/)[0] ?? "";

const sessions = (values: { effective: string; text: string }[]) => ({
  state: "ready" as const,
  value: {
    subject: "crew-01",
    count: values.length,
    reference_time: null,
    sessions: values.map(({ effective, text }) => ({
      effective,
      values: [{ key: "k", display: "Mean", display_es: "Media", value: 1, value_text: text }],
    })),
  } as never,
});

describe("las pruebas se despliegan", () => {
  it("pulsar una la abre, pulsar otra cambia, pulsar la misma la pliega", () => {
    let ui = press(DIAGNOSTICS_CLOSED, { type: "toggle-test", test: "ultrasound" });
    expect(ui.test).toBe("ultrasound");
    ui = press(ui, { type: "toggle-test", test: "other" });
    expect(ui.test).toBe("other");
    ui = press(ui, { type: "toggle-test", test: "other" });
    expect(ui.test).toBeNull();
  });

  it("cerrada no enseña detalle; abierta, `aria-expanded` y la lista con su id", () => {
    expect(render({})).not.toContain("dx-detail");
    const html = renderOpen({ test: "ultrasound", viewer: false });
    const part = detailOf(html, "ultrasound");
    expect(part).toContain('aria-expanded="true"');
    const id = part.match(/aria-controls="([^"]+)"/)?.[1];
    expect(id).toBeDefined();
    expect(part).toContain(`id="${id}"`);
  });

  it("ecografía: los estudios con el nombre de protocolo del backend, el más reciente primero", () => {
    const studies = [
      { ledger_index: 1, recorded: "2026-11-01T08:00:00Z", protocol: "lung", frames: 1 },
      { ledger_index: 2, recorded: "2026-11-12T08:00:00Z", protocol: "fast", frames: 40, synthetic: true },
    ] as never;
    const protocols = { state: "ready" as const, value: { protocols: [{ key: "fast", display: "FAST del backend" }] } as never };
    const part = detailOf(renderOpen({ test: "ultrasound", viewer: false }, { ultrasound: { state: "ready", value: studies }, protocols }), "ultrasound");
    expect(part.indexOf("FAST del backend")).toBeLessThan(part.indexOf("lung"));
    expect(part).toContain("fotogramas");
    expect(part).toContain("fantoma simulado");
    expect(part).toMatch(/<span class="num">1<\/span> fotograma</);
  });

  it("sin nada registrado lo dice en gris, prueba a prueba", () => {
    expect(detailOf(renderOpen({ test: "ultrasound", viewer: false }), "ultrasound")).toMatch(
      /class="secondary dx-detail-empty".*sin registro de ecografía/,
    );
    expect(detailOf(renderOpen({ test: "biomarkers", viewer: false }), "biomarkers")).toContain("sin registro en 30 d");
    expect(detailOf(renderOpen({ test: "lab-reports", viewer: false }), "lab-reports")).toContain("sin registro de analíticas");
  });

  it("biomarcadores: todas las series de 30 días con su cifra del catálogo, sin el tope de las tendencias", () => {
    const keys = ["a", "b", "c", "d", "e", "f"];
    const catalog = new Map(keys.map((key) => [key, indicator(key)]));
    const series = keys.map((key, index) => ({ key, readings: [{ at: REF_MS - (index + 1) * DAY, value: index + 10 }] }));
    const html = renderToStaticMarkup(
      createElement(HomeDiagnosticsView, {
        home: home({ catalog }),
        data: data({ labs: { state: "ready", value: series } }),
        ui: { test: "biomarkers", viewer: false },
      }),
    );
    const part = detailOf(html, "biomarkers");
    expect((part.match(/data-detail-row/g) ?? []).length).toBe(5);
    expect(part).toMatch(/y <span class="num">1<\/span> más/);
    expect(part).toContain("U/L");
    // Las tendencias siguen con su tope.
    expect((html.match(/data-lab="/g) ?? []).length).toBe(TREND_ROWS);
  });

  it("analíticas: solo los informes que son analíticas, con páginas y cifras leídas", () => {
    const reports = [
      { ledger_index: 1, recorded: "2026-11-10T08:00:00Z", kind: "analitica", pages: 2, lab_readings: { date: null, readings: [{}, {}, {}] } },
      { ledger_index: 2, recorded: "2026-11-11T08:00:00Z", kind: "alta", pages: 9 },
    ] as never;
    const part = detailOf(renderOpen({ test: "lab-reports", viewer: false }, { reports: { state: "ready", value: reports } }), "lab-reports");
    expect((part.match(/data-detail-row/g) ?? []).length).toBe(1);
    expect(part).toMatch(/<span class="num">2<\/span> páginas/);
    expect(part).toMatch(/<span class="num">3<\/span> cifras leídas/);
  });

  it("otras pruebas: lo último de PVT, cognición y dolor con las palabras del backend; lo que falta, en gris", () => {
    const others = {
      pvt: sessions([
        { effective: "2026-11-01T08:00:00Z", text: "vieja" },
        { effective: "2026-11-12T08:00:00Z", text: "312 ms del backend" },
      ]),
      cognition: sessions([]),
      pain: { state: "ready" as const, value: [{ effective: "2026-11-13T08:00:00Z", intensity: 4, zones: [{}, {}] }] as never },
    };
    const part = detailOf(renderOpen({ test: "other", viewer: false }, { others }), "other");
    expect(part).toContain("Media: 312 ms del backend");
    expect(part).not.toContain("vieja");
    expect(part).toMatch(/data-other="cognition">.*sin registro/);
    expect(part).toMatch(/intensidad máxima <span class="num">4<\/span>/);
    expect(part).toMatch(/<span class="num">2<\/span> zonas/);
    // Sin pedir todavía: cargando, no «sin registro».
    expect(detailOf(renderOpen({ test: "other", viewer: false }), "other")).toContain("Cargando");
  });

  it("una fecha ilegible del backend no tumba el bloque: «sin fecha» en cian", () => {
    const reports = [{ ledger_index: 1, recorded: "", kind: "analitica", pages: 1 }] as never;
    const part = detailOf(renderOpen({ test: "lab-reports", viewer: false }, { reports: { state: "ready", value: reports } }), "lab-reports");
    expect(part).toMatch(/c-cyan[^>]*>.*sin fecha/);
  });

  it("una petición que falla lo dice con su motivo, no como vacío", () => {
    const failed = { state: "failed" as const, outcome: { mark: FAILURE_MARK, text: "motivo del backend", detail: null } as never };
    const part = detailOf(renderOpen({ test: "lab-reports", viewer: false }, { reports: failed }), "lab-reports");
    expect(part).toContain("motivo del backend");
    expect(part).not.toContain("sin registro");
  });
});

describe("la ventana del visor completo", () => {
  const withLiver = data({ volumes: { state: "ready", value: [study({ segmentations: [segmentation()] })] } });

  it("abrir y Escape: el reductor la abre y la tecla Escape (y solo ella) la cierra", () => {
    const open = press(DIAGNOSTICS_CLOSED, { type: "open-viewer" });
    expect(open.viewer).toBe(true);
    const escape = viewerKeyAction("Escape");
    expect(escape).toEqual({ type: "close-viewer" });
    expect(press(open, escape as DiagnosticsAction).viewer).toBe(false);
    expect(viewerKeyAction("Enter")).toBeNull();
    expect(viewerKeyAction("a")).toBeNull();
  });

  it("el mando «Abrir visor completo» está, sin depender de las pestañas apartadas", () => {
    const html = render({ data: withLiver });
    expect(html).toContain("Abrir visor completo");
    expect(html).toContain('aria-haspopup="dialog"');
    expect(html).toContain('aria-expanded="false"');
    expect(render({ data: data({ volumes: { state: "ready", value: [study()] } }) })).toContain("Abrir volúmenes");
    // Sin volúmenes no hay nada que abrir.
    expect(render({})).not.toMatch(/Abrir volúmenes|Abrir visor/);
  });

  it("abierta con el hígado: el visor de Polaris (su iframe), el título, «Cerrar» y la salvedad", () => {
    const html = renderToStaticMarkup(createElement(HomeDiagnosticsView, { home: home(), data: withLiver, ui: { test: null, viewer: true } }));
    expect(html).toMatch(/role="dialog" aria-modal="true" aria-labelledby="[^"]+" tabindex="-1"/);
    expect(html).toContain("<iframe");
    expect(html).toContain("/api/volumes/segmentations/20/polaris/index.html");
    expect(html).toContain("Cerrar");
    expect(html.split('role="dialog"')[1]).toContain("No es un diagnóstico a bordo.");
  });

  it("abierta sin volúmenes: lo dice y da el «no disponible» del backend, sin visor", () => {
    const html = renderOpen({ test: null, viewer: true });
    const dialog = html.split('role="dialog"')[1] ?? "";
    expect(dialog).toContain("Sin volúmenes registrados.");
    expect(dialog).toMatch(/c-gray[^>]*>.*Motivo del backend: no hay segmentador\./);
    expect(dialog).not.toContain("<iframe");
  });

  it("abierta con un volumen sin segmentar: la lista de volúmenes y que no hay segmentación", () => {
    const dialog =
      renderOpen({ test: null, viewer: true }, { volumes: { state: "ready", value: [study()] } }).split('role="dialog"')[1] ?? "";
    expect(dialog).toContain("Sin segmentación: el volumen está registrado y firmado.");
    expect(dialog).toContain('data-volume="10"');
    expect(dialog).toContain("512×512×100");
  });

  it("un preset que Polaris no pinta va al visor propio, cargado a demanda (mientras, «Cargando…»)", () => {
    const eyes = data({ volumes: { state: "ready", value: [study({ segmentations: [segmentation({ preset: "ojos", preset_nombre: "Ojos" })] })] } });
    const dialog =
      renderToStaticMarkup(createElement(HomeDiagnosticsView, { home: home(), data: eyes, ui: { test: null, viewer: true } })).split(
        'role="dialog"',
      )[1] ?? "";
    expect(dialog).not.toContain("<iframe");
    expect(dialog).toContain("Cargando");
  });
});

describe("el módulo y su hoja", () => {
  const source = readFileSync(fileURLToPath(new URL("./HomeDiagnostics.tsx", import.meta.url)), "utf8");
  const css = readFileSync(fileURLToPath(new URL("./homeDiagnostics.css", import.meta.url)), "utf8");

  it("nada del borrador de interpretación; el visor pesado (NiiVue) solo a demanda", () => {
    expect(source).not.toMatch(/from "[^"]*interpret|import\("[^"]*interpret/);
    expect(source).not.toMatch(/from "[^"]*VolumeViewer"/);
    expect([...source.matchAll(/import\("([^"]+)"\)/g)].map((match) => match[1])).toEqual(["../volumes/VolumeViewer"]);
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
