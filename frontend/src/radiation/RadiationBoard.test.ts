import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textNodes } from "../advisor/visibleText";
import type { CrewStatus, RiskEntity, SpaceWeatherSeries } from "../lib/api";
import type { HomeData } from "../dashboard/HomeBoard";
import {
  RadDosimetry,
  RadEffects,
  RadHistory,
  RadNav,
  RadRecommendations,
  RadRoute,
  RadSpaceWeather,
  RadSpectrum,
  RadWeatherNow,
  type RadiationData,
  WeekBars,
} from "./RadiationBoard";

/**
 * La sección «Radiación» (maqueta del 2026-11-14 con el estilo de «Inicio»). Lo que se prueba es lo
 * que la maqueta inventaba y aquí no se puede inventar: la dosis sale del estado con su tipo
 * (inferida o PREDICHA), sin dosis previa no se supone cero, la referencia S1 se enseña sin evaluar,
 * los efectos son la frase del backend y el espectro no lleva cifras.
 */

const REFERENCE = "2026-12-10T23:00:00+00:00";

function status(overrides: Partial<CrewStatus["radiation"]> = {}, recommendations: CrewStatus["recommendations"] = []): CrewStatus {
  return {
    subject: "crew-01",
    domains: { radiation: { score: 0, level: "nominal", drivers: [], trajectory: null } },
    alerts: [],
    recommendations,
    provenance: { observation_type: { measured: 3 }, evidence_context: {} },
    data: { reference_time: REFERENCE },
    mission: { phase_display: "fase estable", mission_day: 40, duration_days: 180, phase: "stable", phases: [{ key: "stable", display: "fase estable" }], profile: { id: "mars-transit", display: "tránsito a Marte" } },
    radiation: {
      acute: { active_event: null, time_to_action: null },
      mission: {
        value_msv: 27.485,
        absorbed_mgy: 11.549,
        quality_factor: 2.38,
        hours_covered: 959,
        observation_type: "inferred",
        model_version: "m@1",
        basis: "integral de la tasa (backend)",
      },
      career: { value_msv: null, basis: "sin dosis previa declarada (backend)", limit_msv: 600, limit_source: "NASA-STD-3001 [V1 4030]" },
      projection: {
        observation_type: "predicted",
        model_version: "p@1",
        mission_end: "2027-04-30",
        end_day: 180,
        scope: "se muestra",
        value_msv: 123.814,
        basis: "tasa media constante (backend)",
      },
      ...overrides,
    },
  } as unknown as CrewStatus;
}

function data(value: CrewStatus, extra: Partial<RadiationData> = {}): RadiationData {
  const home = {
    status: value,
    reference: Date.parse(REFERENCE),
    groups: [],
    matrix: null,
    matrixFailure: null,
  } as unknown as HomeData;
  return {
    home,
    weather: { state: "loading" },
    crew: { state: "loading" },
    history: { state: "loading" },
    risk: { state: "loading" },
    doseRate: { state: "ready", value: [] },
    imm: { state: "loading" },
    latest: { state: "loading" },
    ...extra,
  };
}

const render = (component: (props: { rad: RadiationData }) => unknown, rad: RadiationData) =>
  renderToStaticMarkup(createElement(component as never, { rad }));
const text = (html: string) => textNodes(html).join(" ");

describe("Radiación: dosimetría", () => {
  it("la dosis de misión con su tipo inferido, y sin dosis previa no se supone cero", () => {
    const html = render(RadDosimetry, data(status()));
    const words = text(html);
    expect(words).toContain("27,5");
    expect(html).toMatch(/INFERIDO|inferid/i);
    expect(words).toContain("sin dosis previa declarada");
    expect(words).not.toMatch(/carrera 0/);
  });

  it("sin dosis de misión, la marca de lo que falta y ningún anillo", () => {
    const html = render(RadDosimetry, data(status({ mission: null })));
    expect(text(html)).toContain("sin dosis que integrar");
    expect(html).not.toContain("ref-ring-fill");
    expect(html).toContain("c-cyan");
  });
});

describe("Radiación: ruta", () => {
  it("lo integrado hasta hoy es inferido y el fin de misión, PREDICHO, con las cifras del backend", () => {
    const html = render(RadRoute, data(status()));
    const words = text(html);
    expect(words).toContain("27,5 mSv");
    expect(words).toContain("123,8 mSv");
    expect(words).toContain("140");
    expect(html).toMatch(/PREDICHO|predich/i);
  });

  it("sin proyección no se inventa un total", () => {
    const html = render(RadRoute, data(status({ projection: null })));
    expect(text(html)).toContain("sin proyección");
  });
});

const WEATHER: SpaceWeatherSeries = {
  series: {
    protons: {
      available: true,
      dataset: "goes",
      title: "Protones",
      channels: [{ name: "flux_ge_10mev", label: "≥10 MeV", unit: "pfu" }],
      window_hours: 24,
      samples: [],
      latest: { time: "2026-11-14T10:00:00+00:00", flux_ge_10mev: 0.246 },
      last_sample_age_seconds: 60,
      data_age: "ahora mismo",
      data_age_seconds: 60,
      from_cache: true,
      live: false,
      source: "NASA CCMC iSWA (backend)",
      reference: { label: "S1", value: 10, unit: "pfu", channel: "≥10 MeV", source: "NOAA", evaluated: false },
    },
    "solar-wind": { available: false, dataset: "rtsw", title: "Viento solar", reason: "sin red (backend)" },
  },
  scope: "Entorno en GOES y L1, no en la nave (backend).",
  licence: "licencia (backend)",
  events: "eventos (backend)",
};

describe("Radiación: entorno de partículas", () => {
  it("la referencia S1 se enseña al lado, sin evaluar; una serie caída dice «sin dato»", () => {
    const html = render(RadWeatherNow, data(status(), { weather: { state: "ready", value: WEATHER } }));
    const words = text(html);
    expect(words).toContain("0,25");
    expect(words).toContain("sin evaluar");
    expect(words).toContain("sin dato");
    expect(words).toContain("no en la nave");
  });

  it("la meteorología es lo observado: sin pronóstico y con la fuente", () => {
    const html = render(RadSpaceWeather, data(status(), { weather: { state: "ready", value: WEATHER } }));
    const words = text(html);
    expect(words).toContain("sin pronóstico");
    expect(words).toContain("NASA CCMC iSWA (backend)");
    expect(html).toContain("slash-circle");
  });
});

describe("Radiación: textos del backend", () => {
  it("los efectos son la frase de la entidad Riesgo, tal cual", () => {
    const risk = {
      risk_id: "radiation",
      effect: { source: { title: "Risk of Radiation Carcinogenesis", url: null }, statement: "FRASE DEL EFECTO (backend)", basis: "b" },
      human_system: { regions: [{ key: "whole", display: "Todo el cuerpo (backend)", domains: ["radiation"], note: "n" }] },
      amcl_alignment: "ALINEAMIENTO (backend)",
      detection: { danger_limits: [{ key: "absorbed-dose-rate", display_es: "t", statement: "LÍMITE (backend)" }], environment: [], basis: "b" },
    } as unknown as RiskEntity;
    const html = render(RadEffects, data(status(), { risk: { state: "ready", value: risk } }));
    const words = text(html);
    expect(words).toContain("FRASE DEL EFECTO (backend)");
    expect(words).toContain("Todo el cuerpo (backend)");
    expect(words).toContain("ALINEAMIENTO (backend)");
    expect(words).toContain("LÍMITE (backend)");
  });

  it("las recomendaciones son las del dominio de radiación, nada más", () => {
    const recommendations = [
      { domain: "radiation", action: "ACCIÓN DE RADIACIÓN", rationale: "r", urgency: "soon" },
      { domain: "bone", action: "ACCIÓN DE HUESO", rationale: "r", urgency: "soon" },
    ] as unknown as CrewStatus["recommendations"];
    const words = text(render(RadRecommendations, data(status({}, recommendations))));
    expect(words).toContain("ACCIÓN DE RADIACIÓN");
    expect(words).not.toContain("ACCIÓN DE HUESO");
  });

  it("el espectro es de nombres y orden: ninguna cifra", () => {
    const words = text(renderToStaticMarkup(createElement(RadSpectrum)));
    expect(words).not.toMatch(/\d/);
    expect(words).toContain("Rayos gamma");
    expect(words).toContain("Radio");
  });
});

describe("Radiación: lo añadido en la ronda 7-8", () => {
  it("la franja dice la misión, el día y la fase del backend", () => {
    const words = text(render(RadNav, data(status())));
    expect(words).toContain("Tránsito a Marte");
    expect(words).toContain("40");
    expect(words).toContain("180");
    expect(words).toContain("fase estable");
  });

  it("el historial sin misiones previas enseña la misión en curso con su dosis inferida y no supone carrera cero", () => {
    const history = { state: "ready" as const, value: { subject: "crew-01", declared: false, scope: "s", limits: {}, text: "SIN HISTORIAL (backend)", missions: [], checks: [] } };
    const html = render(RadHistory, data(status(), { history: history as unknown as RadiationData["history"] }));
    const words = text(html);
    expect(words).toContain("En curso");
    expect(words).toContain("27,5 mSv");
    expect(words).toContain("SIN HISTORIAL (backend)");
    expect(words).toContain("sin dosis previa declarada (backend)");
  });

  it("las barras de 7 días son medias de lo observado; un día sin lecturas no se rellena", () => {
    const at = Date.parse(REFERENCE);
    const readings = [
      { at: at - 1000, value: 12 },
      { at: at - 2000, value: 14 },
      { at: at - 3 * 24 * 3600 * 1000 - 1000, value: 10 },
    ];
    const words = text(render(WeekBars, data(status(), { doseRate: { state: "ready", value: readings } })));
    expect(words).toContain("13,0");
    expect(words).toContain("10,0");
    expect(words).toContain("observados");
    expect(words.match(/—/g)?.length).toBe(5);
  });
});

describe("Radiación: lo que publica el IMM", () => {
  it("«Efectos» da el síndrome agudo de radiación del perfil declarado, en tanto por mil, con la salvedad del backend", () => {
    const risk = {
      risk_id: "radiation",
      effect: { source: null, statement: "E", basis: "b" },
      human_system: { regions: [] },
      amcl_alignment: "A",
      detection: { danger_limits: [], environment: [], basis: "b" },
    } as unknown as RiskEntity;
    const imm = {
      condition: "Acute Radiation Syndrome",
      condition_display: "síndrome agudo de radiación",
      measure: "m",
      measure_quote: "q",
      caveat: "SALVEDAD (backend)",
      caveat_quote: "cq",
      source: { id: "imm-ranking-2015", title: "Ranking of Medical Conditions by Probability", source: "s", url: null, date: "2015-02-02" },
      read_on: "2026-11-14",
      drms: [{ key: "deep-space-journey-12", display: "viaje y hábitat en espacio profundo, doce meses", drm_quote: "d", table: "Table 6", row_quote: "Acute Radiation Syndrome 2.83E-03", months: 12, evas: 5, probability: 0.00283, probability_text: "2.83E-03" }],
      profiles: [{ id: "mars-transit", declared: true, drm: "deep-space-journey-12", reason: "r", probability: 0.00283, probability_text: "2.83E-03" }],
      assigned_by: "a",
      scope: "s",
    };
    const words = text(
      render(RadEffects, data(status(), { risk: { state: "ready", value: risk }, imm: { state: "ready", value: imm } as RadiationData["imm"] })),
    );
    expect(words).toContain("2,83");
    expect(words).toContain("por mil misiones de un tripulante");
    expect(words).toContain("SALVEDAD (backend)");
    expect(words).toContain("Ranking of Medical Conditions by Probability");
  });
});
