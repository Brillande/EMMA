/**
 * La sección «Radiación» en inglés (`lib/i18n.ts`): los rótulos, las frases de lo que falta y las
 * cifras con punto decimal. Lo que redacta el backend no se traduce aquí y se sigue viendo tal cual.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textNodes } from "../advisor/visibleText";
import type { CrewStatus } from "../lib/api";
import type { HomeData } from "../dashboard/HomeBoard";
import {
  RadDosimetry,
  RadLimits,
  RadNav,
  RadRecommendations,
  RadRoute,
  RadSpectrum,
  RadWeatherNow,
  type RadiationData,
  WeekBars,
} from "./RadiationBoard";

const REFERENCE = "2026-12-10T23:00:00+00:00";

function status(overrides: Partial<CrewStatus["radiation"]> = {}): CrewStatus {
  return {
    subject: "crew-01",
    domains: { radiation: { score: 0, level: "nominal", drivers: [], trajectory: null } },
    alerts: [],
    recommendations: [],
    provenance: { observation_type: { measured: 3 }, evidence_context: {} },
    data: { reference_time: REFERENCE },
    mission: {
      phase_display: "FASE (backend)",
      mission_day: 40,
      duration_days: 180,
      phase: "stable",
      phases: [{ key: "stable", display: "FASE (backend)" }],
      profile: { id: "mars-transit", display: "PERFIL (backend)" },
    },
    radiation: {
      acute: { active_event: null, time_to_action: null },
      mission: {
        value_msv: 27.485,
        absorbed_mgy: 11.549,
        quality_factor: 2.38,
        hours_covered: 959,
        observation_type: "inferred",
        model_version: "m@1",
        basis: "BASE (backend)",
      },
      career: { value_msv: null, basis: "BASE DE CARRERA (backend)", limit_msv: 600, limit_source: "NASA-STD-3001 [V1 4030]" },
      projection: {
        observation_type: "predicted",
        model_version: "p@1",
        mission_end: "2027-04-30",
        end_day: 180,
        scope: "se muestra",
        value_msv: 123.814,
        basis: "BASE DE LA PROYECCIÓN (backend)",
      },
      ...overrides,
    },
  } as unknown as CrewStatus;
}

function data(value: CrewStatus): RadiationData {
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
  };
}

const render = (component: (props: { rad: RadiationData }) => unknown, rad: RadiationData) =>
  renderToStaticMarkup(createElement(component as never, { rad }));
const text = (html: string) => textNodes(html).join(" ");

describe("Radiación en inglés", () => {
  it("el espectro: título, bandas y la frase de las partículas", () => {
    const html = renderToStaticMarkup(createElement(RadSpectrum));
    const words = text(html);
    expect(html).toContain('aria-label="Electromagnetic spectrum"');
    expect(words).toContain("Electromagnetic spectrum and radiation types");
    expect(words).toContain("Gamma rays");
    expect(words).toContain("Non-ionizing");
    expect(words).toContain("which are not on this spectrum");
    expect(words).not.toMatch(/Espectro|Rayos|Ionizante|partículas/);
  });

  it("la dosimetría: rótulos en inglés, cifras con punto y sin dosis previa no se supone cero", () => {
    const words = text(render(RadDosimetry, data(status())));
    expect(words).toContain("Dosimetry and monitoring");
    expect(words).toContain("Absorbed dose rate");
    expect(words).toContain("no readings");
    expect(words).toContain("27.5");
    expect(words).toContain("of 600 mSv career limit");
    expect(words).toContain("no prior dose declared");
    expect(words).not.toMatch(/Dosimetría|sin lecturas|de carrera|27,5/);
  });

  it("sin dosis de misión lo dice en inglés, con la marca de lo que falta", () => {
    const html = render(RadDosimetry, data(status({ mission: null })));
    expect(text(html)).toContain("no dose to integrate");
    expect(html).toContain("c-cyan");
  });

  it("la ruta: los tramos y la dosis proyectada, con la fase del backend tal cual", () => {
    const words = text(render(RadRoute, data(status())));
    expect(words).toContain("Space route and estimated exposure");
    // Sin matriz de perfiles, el nombre del perfil es el del backend.
    expect(words).toContain("Route: PERFIL (backend)");
    expect(words).toContain("To date");
    expect(words).toContain("End of mission");
    expect(words).toContain("123.8 mSv");
    expect(words).toContain("FASE (backend)");
    expect(words).not.toMatch(/Hasta hoy|Fin de misión|Tramo/);
    expect(text(render(RadRoute, data(status({ projection: null }))))).toContain("no projection");
  });

  it("las anclas y la misión en curso", () => {
    const html = render(RadNav, data(status()));
    const words = text(html);
    expect(html).toContain('aria-label="Radiation sections"');
    for (const label of ["Radiation", "Exposure", "Health effects", "Prevention", "Prediction", "History"]) {
      expect(words).toContain(label);
    }
    expect(words).toMatch(/day\s+40\s+of\s+180/);
    expect(words).not.toMatch(/Radiación|Historial|día/);
  });

  it("los límites, el entorno que carga, las recomendaciones vacías y las barras de la semana", () => {
    const limits = text(render(RadLimits, data(status())));
    expect(limits).toContain("Limits (NASA-STD-3001)");
    expect(limits).toContain("Career (effective dose)");
    expect(limits).toContain("the backend gives no short-term limits");
    expect(text(render(RadWeatherNow, data(status())))).toContain("Particle environment (now)");
    expect(text(render(RadRecommendations, data(status())))).toContain("No radiation recommendations: nothing requires action.");
    const week = render(WeekBars, data(status()));
    expect(text(week)).toContain("Onboard dose rate, daily mean (7 days observed)");
    expect(text(week)).toContain("today");
    expect(week).toContain('title="no readings"');
  });
});
