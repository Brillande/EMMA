/**
 * «Diagnóstico integrado» en inglés (`lib/i18n.ts`): los rótulos de la interfaz y, sobre todo, la
 * salvedad del volumen, que tiene que seguir diciendo lo mismo (minas de `CLAUDE.md`): imagen de
 * referencia previa al vuelo o de Tierra, no un diagnóstico a bordo. Lo demás lo vigila
 * `HomeDiagnostics.test.ts`.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { CrewStatus, Indicator, ProfileMatrix, VolumeSegmentation, VolumeStudy } from "../lib/api";
import type { HomeData, HomeLinks } from "./HomeBoard";
import { type DiagnosticsData, HomeDiagnosticsView } from "./HomeDiagnostics";

const REFERENCE = "2026-11-14T12:00:00Z";
const REF_MS = Date.parse(REFERENCE);

const alt = {
  key: "alt",
  display: "alt",
  display_es: "ALT",
  unit: "U/L",
  domain: "nutrition",
  decimals: 0,
  measurement_cost: { mode: "laboratory" },
} as unknown as Indicator;

const status = {
  subject: "crew-01",
  summary: "Summary written by the backend.",
  overall_level: "watch",
  domains: { radiation: { score: 0, level: "nominal", drivers: [] } },
  data: { reference_time: REFERENCE, observations: 100 },
  mission: { start: "2026-10-01T00:00:00Z" },
} as unknown as CrewStatus;

const matrix = {
  profiles: [{ id: "mars-transit", display: "transit to Mars", declared: true, cells: [] }],
} as unknown as ProfileMatrix;

const home = {
  status,
  reference: REF_MS,
  indicators: { state: "ready", value: [alt] },
  catalog: new Map([["alt", alt]]),
  matrix,
  matrixFailure: null,
  shownRoute: "mars-transit",
  lowest: "nominal",
} as unknown as HomeData;

const data = (over: Partial<DiagnosticsData> = {}): DiagnosticsData => ({
  volumes: { state: "ready", value: [] },
  segmenter: { state: "ready", value: { available: true, note: null } },
  ultrasound: { state: "ready", value: [] },
  reports: { state: "ready", value: [] },
  labs: { state: "ready", value: [] },
  ...over,
});

const links: HomeLinks = {
  openSection: () => undefined,
  sectionName: (key) => ({ imaging: "Imaging and reports", body: "Body", log: "Log and tests", hazards: "Hazards and alerts" })[key] ?? null,
};

const render = (over: Partial<DiagnosticsData> = {}, withLinks = true) =>
  renderToStaticMarkup(createElement(HomeDiagnosticsView, { home, data: data(over), links: withLinks ? links : undefined }));

const study = (over: Partial<VolumeStudy> = {}): VolumeStudy =>
  ({
    ledger_index: 10,
    recorded: "2026-11-09T08:00:00Z",
    subject: "crew-01",
    modality: "CT",
    segmentations: [],
    ...over,
  }) as unknown as VolumeStudy;

describe("«Diagnóstico integrado» en inglés", () => {
  it("el título, el perfil corto y las cuatro tarjetas", () => {
    const html = render();
    for (const text of [
      'aria-label="Integrated diagnostics: tests and visualization"',
      "(Mars transit)",
      'aria-label="Tests"',
      'aria-label="Polaris 3D viewer"',
      "3D viewer",
      'aria-label="Status analysis"',
      'aria-label="Key trends over 30 days"',
      "Key trends",
    ]) {
      expect(html).toContain(text);
    }
    expect(html).not.toMatch(/Diagnóstico integrado|Pruebas|Visor 3D|Análisis del estado|Tendencias clave/);
  });

  it("las pruebas, sus recuentos vacíos y el acceso a su sección", () => {
    const html = render();
    for (const text of [
      "Ultrasound",
      "no studies",
      "Biomarkers",
      "no readings in 30 d",
      "Lab tests (blood/urine)",
      "no reports",
      "Other tests (PVT, cognition, pain)",
      'aria-label="Open Imaging and reports: Ultrasound"',
      'title="Open Body"',
      'aria-label="Open Hazards and alerts: analysis detail"',
      "View detail",
      "no lab tests in the last 30 days",
    ]) {
      expect(html).toContain(text);
    }
    expect(html).not.toMatch(/Ecografía|Biomarcadores|Analíticas|sin estudios|sin informes|Abrir|Ver detalle/);
  });

  it("los recuentos concuerdan en número", () => {
    const one = render({ ultrasound: { state: "ready", value: [{}] as never } });
    expect(one).toMatch(/<span class="num">1<\/span> study</);
    const two = render({ ultrasound: { state: "ready", value: [{}, {}] as never } });
    expect(two).toMatch(/<span class="num">2<\/span> studies</);
  });

  it("la salvedad del volumen dice lo mismo: referencia previa al vuelo o de Tierra, no diagnóstico a bordo", () => {
    const html = render();
    expect(html).toContain(
      "Not an on-board diagnosis. Reference imaging from before flight or from Earth: no CT scanner flies today.",
    );
    expect(html).toContain("No volumes recorded.");
    // Ni «vuela un TAC» ni «nunca volará», ni palabras de certificación.
    expect(html).not.toMatch(/will never|never fly|certified|validated/i);
    expect(html).not.toMatch(/No es un diagnóstico|ningún TAC/);
  });

  it("un volumen sin segmentar y uno de dataset público", () => {
    const html = render({ volumes: { state: "ready", value: [study({ dataset: "public" } as never)] } });
    expect(html).toContain("No segmentation: the volume is recorded and signed.");
    expect(html).toContain("Real CT from a public dataset, not from this crew member.");
    expect(html).toContain('aria-label="Open Imaging and reports: full viewer"');
    expect(html).toContain("Open volumes");
    expect(html).not.toMatch(/Sin segmentación|dataset público|Abrir volúmenes/);
  });

  it("el estado de la segmentación es el del backend; la interfaz no añade «validated»", () => {
    const segmentation = {
      ledger_index: 20,
      recorded: "2026-11-10T08:00:00Z",
      preset: "higado",
      preset_nombre: "Liver",
      estado: "BACKEND STATE",
      estructuras: [{ key: "liver", nombre: "liver", etiqueta: 1, malla: null, volumen_ml: 1532.46 }],
      lesiones: [],
    } as unknown as VolumeSegmentation;
    const html = render({ volumes: { state: "ready", value: [study({ segmentations: [segmentation] })] } });
    expect(html).toContain("Liver (Polaris)");
    expect(html).toContain("BACKEND STATE");
    expect(html).not.toMatch(/validated/i);
  });

  it("la edad de la última lectura va detrás de la cifra: «… ago»", () => {
    const labs = { state: "ready" as const, value: [{ key: "alt", readings: [{ at: REF_MS - 3 * 3600 * 1000, value: 28 }] }] };
    const html = render({ labs });
    expect(html).toMatch(/ago<\/small>/);
    expect(html).toContain('title="Age of the last reading relative to the status reference"');
    expect(html).not.toMatch(/hace /);
  });
});
