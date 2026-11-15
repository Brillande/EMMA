/**
 * La última fila de «Distancia y nodos» en inglés (`lib/i18n.ts`), con las otras dos piezas de la
 * pestaña que solo llevan unos rótulos (`NodesEmergencyKit`, `NodesFit`). Las cifras —el r pasa por
 * `formatNumber` y aquí sale con punto decimal—, las marcas y las frases del backend las vigila
 * `NodesOutlook.test.ts`; aquí, el idioma de lo que pone la interfaz.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { CrewStatus, ProfileMatrix } from "../lib/api";
import type { CorrelationPair, Correlations } from "../lib/outlookApi";
import type { Fetched, HomeData, HomeLinks } from "./HomeBoard";
import { EmergencyKitList, type KitRow } from "./NodesEmergencyKit";
import { NodesFit } from "./NodesFit";
import { CHALLENGES, NodesOutlookView } from "./NodesOutlook";

const REFERENCE = "2026-11-14T12:00:00Z";

const matrix = {
  no_source: "EMMA has no source",
  profiles: [
    { id: "leo", display: "low orbit", declared: true, cells: [{ key: "comm_delay", label: "delay", text: "Backend sentence." }] },
    { id: "mars-transit", display: "transit to Mars", declared: false, cells: [] },
  ],
} as unknown as ProfileMatrix;

const statusOf = (over: Record<string, unknown> = {}): CrewStatus =>
  ({
    subject: "crew-01",
    summary: "Summary.",
    overall_level: "watch",
    domains: { radiation: { score: 0, level: "nominal", drivers: [] } },
    data: { reference_time: REFERENCE, observations: 10 },
    comms: { one_way_minutes: 3, distance_au: 0.36 },
    freshness: { comms: { state: "fresh" } },
    mission: {
      gravity_display: "Microgravity (backend)",
      profile: { ephemeris: { state: "consistent" } },
      available_resources: {
        declared: [
          { key: "a", state: "available" },
          { key: "c", state: "unavailable" },
        ],
        undeclared_count: 9,
      },
    },
    radiation: {
      career: { value_msv: 120, limit_msv: 600, limit_source: "NASA-STD-3001", basis: "Basis." },
      projection: null,
    },
    predictions: [
      { key: "body-weight", display: "w", display_es: "WEIGHT", unit: "kg", decimals: 1, horizon_weeks: 4, projected_change: 1.5, concerning: false, basis: "B" },
    ],
    forecast_checks: { checked: 5, within_margin: 4, checks: [], basis: "Retrospective." },
    recommendations: [{ domain: "behavioral", action: "Backend action.", rationale: "Why." }],
    ...over,
  }) as unknown as CrewStatus;

const home = (status: CrewStatus = statusOf(), over: Partial<HomeData> = {}): HomeData =>
  ({
    status,
    reference: Date.parse(REFERENCE),
    groups: [
      { hazard: "radiation", display: "radiation", domains: ["radiation"] },
      { hazard: "isolation", display: "isolation", domains: [] },
    ],
    matrix,
    matrixFailure: null,
    shownRoute: "leo",
    lowest: "nominal",
    ...over,
  }) as unknown as HomeData;

const pair = (over: Partial<CorrelationPair> = {}): CorrelationPair => ({
  x: { key: "sleep-duration", display_es: "SLEEP", unit: "h", decimals: 1 },
  y: { key: "pvt-mean-rt", display_es: "REACTION", unit: "ms", decimals: 0 },
  theme: "sleep and performance",
  state: "computed",
  n: 12,
  r: 0.78,
  ci_low: 0.37,
  ci_high: 0.94,
  points: [{ day: "2026-11-01", x: 6, y: 300 }],
  simulated: false,
  text: "Backend pair sentence.",
  ...over,
});

const correlations = (pairs: CorrelationPair[]): Fetched<Correlations> => ({
  state: "ready",
  value: {
    subject: "crew-01",
    reference_time: REFERENCE,
    window_days: 30,
    min_days: 10,
    method: "M",
    method_version: "v",
    scope: "Backend scope.",
    multiple: "Backend caveat.",
    pairs_basis: "P",
    simulated_text: "S",
    pairs,
  },
});

const links: HomeLinks = {
  openSection: () => undefined,
  sectionName: (key) => ({ hazards: "Hazards and alerts" })[key] ?? null,
};

const render = (props: { home?: HomeData; pairs?: CorrelationPair[]; profileId?: string | null } = {}) =>
  renderToStaticMarkup(
    createElement(NodesOutlookView, {
      home: props.home ?? home(),
      correlations: correlations(props.pairs ?? [pair()]),
      links,
      profileId: props.profileId,
    }),
  );

describe("«Riesgos y retos de la distancia» en inglés", () => {
  it("el título, el perfil y los cinco retos", () => {
    const html = render();
    expect(html).toContain('aria-label="Risks and challenges of distance"');
    expect(html).toContain("(Low Earth orbit)");
    expect(CHALLENGES.map((item) => item.label)).toEqual([
      "Accumulated radiation",
      "Isolation and confinement",
      "Gravity fields",
      "Communication latency",
      "Resource availability",
    ]);
    for (const text of [
      "</span> of <span",
      'aria-label="Open Hazards and alerts: levels by hazard"',
      "View levels by hazard",
      "one way",
      "no figure of its own",
      "no level",
      "available",
      "not available",
      "not declared",
    ]) {
      expect(html).toContain(text);
    }
    expect(html).not.toMatch(/Riesgos y retos|Radiación acumulada|Órbita baja|sin nivel|sin cifra|disponibles|sin declarar|Abrir|>ida</);
  });

  it("lo que falta, en inglés: dosis, gravedad de otro perfil, recursos y perfil", () => {
    const status = statusOf({
      radiation: { career: { value_msv: null, limit_msv: 600, limit_source: "x", basis: "b" }, projection: null },
    });
    (status.mission as { available_resources?: unknown }).available_resources = null;
    const html = render({ home: home(status), profileId: "mars-transit" });
    expect(html).toContain("no career dose");
    expect(html).toContain("declared profile only");
    expect(html).toContain("not available");
    expect(html).toContain("(Mars transit)");
    expect(html).toContain("For the crew member on the declared mission: the chosen route does not change them.");
    expect(render({ profileId: null })).toContain("No mission profile declared and no route chosen.");
  });
});

describe("«Correlación de variables» en inglés", () => {
  it("el título con su ventana y el r con punto decimal", () => {
    const html = render();
    expect(html).toContain('aria-label="Variable correlation"');
    expect(html).toContain("(last 30 d)");
    expect(html).toContain('aria-label="Pairs"');
    expect(html).toContain("r = 0.78");
    expect(html).toContain("Scatter of SLEEP against REACTION: 1 day");
    expect(html).toContain("Backend pair sentence.");
    expect(html).not.toMatch(/Correlación|últimos|Pares|Dispersión|0,78/);
  });

  it("los pares sin r y el mando de ver todos", () => {
    const pairs = [
      pair(),
      pair({ x: { ...pair().x, key: "a" }, state: "constant", r: null, points: [] }),
      pair({ x: { ...pair().x, key: "b" }, state: "insufficient", r: null, n: 4 }),
      pair({ x: { ...pair().x, key: "c" }, state: "constant", r: null }),
    ];
    const html = render({ pairs });
    expect(html).toContain("Show all 4 pairs (1 more)");
    expect(html).toContain("no variation");
    expect(html).not.toMatch(/Ver los|sin variación/);
    expect(render({ pairs: [pair({ state: "constant", r: null, points: [] })] })).toContain("no days with both series");
  });
});

describe("«Escenarios y predicción» en inglés", () => {
  it("las proyecciones, los hechos y el acceso; la recomendación es la del backend", () => {
    const html = render();
    for (const text of [
      'aria-label="Scenarios and prediction"',
      "in <span",
      "</span> wk",
      "Dose at end of mission",
      "no dose to extend",
      "Projections checked",
      "within margin",
      "Backend action.",
      'aria-label="Open Hazards and alerts: scenarios and recommendations"',
      "View scenarios and recommendations",
    ]) {
      expect(html).toContain(text);
    }
    expect(html).not.toMatch(/Escenarios|sem\.|Dosis|Proyecciones|dentro del margen|Ver escenarios/);
  });

  it("sin proyecciones ni comprobaciones", () => {
    const status = statusOf({ predictions: [], forecast_checks: { checked: 0, within_margin: 0, checks: [], basis: "b" } });
    const html = render({ home: home(status) });
    expect(html).toContain("No projections for this crew member.");
    expect(html).toContain("none yet");
  });
});

describe("las otras piezas de la pestaña en inglés", () => {
  it("los recursos de emergencia: unidad, sin dato y sin declarar", () => {
    const rows: KitRow[] = [
      { key: "medications", label: "Medications", count: { state: "ready", value: 3 }, unit: "kinds" },
      { key: "equipment", label: "Medical equipment", count: { state: "ready", value: null }, unit: "kinds" },
      { key: "guides", label: "Measurement guides", count: { state: "failed", outcome: { mark: { pictogram: null, color: null }, text: "why" } as never }, unit: "" },
    ];
    const html = renderToStaticMarkup(createElement(EmergencyKitList, { rows }));
    expect(html).toContain('aria-label="Resources for responding to an emergency"');
    expect(html).toContain("</span> kinds");
    expect(html).toContain("not declared");
    expect(html).toContain("no data");
    expect(html).not.toMatch(/Recursos para|sin declarar|sin dato/);
  });

  it("«Ajustar a pantalla»", () => {
    const html = renderToStaticMarkup(createElement(NodesFit, { active: false }));
    expect(html).toContain("Fit to screen");
    expect(html).toContain("The tab shrinks to fit the window; the text ends up smaller than the legibility rule");
    expect(html).not.toMatch(/Ajustar|pestaña/);
  });
});
