/**
 * La sección «Entorno» en inglés (`lib/i18n.ts`): los rótulos propios del tablero salen en inglés
 * y lo que da el backend (nombres de sistema, requisitos, notas) se pinta tal cual.
 */
import "../test/english";

import { type FunctionComponent, createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { language } from "../lib/i18n";
import {
  EnvAir,
  EnvCorrelations,
  EnvGlobal,
  EnvHeader,
  EnvIndex,
  EnvLight,
  EnvNoise,
  EnvRisk,
  EnvSystems,
  EnvThermal,
  EnvWater,
  type EnvironmentData,
} from "./EnvironmentBoard";

const REFERENCE = Date.parse("2026-11-08T12:00:00Z");
const at = (hoursAgo: number) => new Date(REFERENCE - hoursAgo * 3600 * 1000).toISOString();

const reading = (parameter: string, value: number, unit: string, hoursAgo = 1) => ({
  module: "hab",
  parameter,
  value,
  unit,
  effective: at(hoursAgo),
  source: "simulado",
  evidence_context: "",
});

const source = { id: "x", title: "X", url: "https://www.nasa.gov/", read_on: "2026-10-21" };

const temperature = {
  key: "cabin-temperature",
  display: "TEMPERATURA-DEL-BACKEND",
  unit: "Cel",
  limits: [
    { low: 18, high: 27, requirement: "[V2 6012]", kind: "health", averaging_minutes: 60 },
    { low: 20, high: 25, requirement: "[V2 6013]", kind: "performance", averaging_minutes: 60 },
  ],
  averaging_minutes: 60,
  source,
};
const noise = {
  key: "cabin-noise",
  display: "RUIDO-DEL-BACKEND",
  unit: "dB(A)",
  limits: [{ low: null, high: 60, requirement: "[V2 6078]", kind: "health", averaging_minutes: 60 }],
  averaging_minutes: 60,
  source,
};

const excursion = {
  module: "hab",
  parameter: "cabin-noise",
  display: noise.display,
  unit: "dB(A)",
  kind: "health",
  requirement: "[V2 6078]",
  start: at(5),
  end: at(1),
  worst: 66,
};

const ready = <T,>(value: T) => ({ state: "ready" as const, value });

const env = {
  home: {
    reference: REFERENCE,
    catalog: new Map(),
    status: {
      subject: "crew-01",
      mission: { profile: { display: "PERFIL-DEL-BACKEND" }, mission_day: 12.5, gravity_display: "REGIMEN-DEL-BACKEND" },
      domains: {},
      data: { reference_time: at(0) },
    },
  },
  habitat: ready({
    latest: [reading("cabin-temperature", 22.5, "Cel"), reading("cabin-noise", 66, "dB(A)")],
    readings: [reading("cabin-temperature", 22.5, "Cel"), reading("cabin-noise", 66, "dB(A)")],
    active: [excursion],
    excursions: [excursion],
  }),
  parameters: ready({
    parameters: [temperature, noise],
    display_only: [{ key: "water-microbial", display: "MICROBIOS-DEL-BACKEND", unit: "{CFU}/mL", limit_note: "NOTA-DEL-BACKEND" }],
  }),
  systems: ready({
    systems: [{ key: "water", display: "SISTEMA-DEL-BACKEND", description: "", statuses: [{ module: null, declared: false }] }],
    note: "",
    summary: "RESUMEN-DEL-BACKEND",
  }),
  sleep: ready([]),
  correlations: ready({ pairs: [], tested: 3, multiple: "", simulated_text: "" }),
} as unknown as EnvironmentData;

const render = (piece: FunctionComponent<{ env: EnvironmentData }>) => renderToStaticMarkup(createElement(piece, { env }));

describe("la sección «Entorno» en inglés", () => {
  it("este fichero corre en inglés", () => {
    expect(language()).toBe("en");
  });

  it("la cabecera: el título, la hora de los datos y los bloques con su estado", () => {
    const html = render(EnvHeader);
    expect(html).toContain('aria-label="Spacecraft environment"');
    expect(html).toContain("Data as of");
    for (const chip of ["Air", "Temperature", "Light", "Noise", "Water", "Microbes"]) expect(html).toContain(`<span>${chip}</span>`);
    expect(html).toContain("1 outside");
    expect(html).toContain("no reading");
    expect(html).not.toMatch(/Entorno de la nave|Datos a|Ruido|sin lectura|fuera/);
  });

  it("el estado global y el recuento de parámetros dentro de límites", () => {
    const global = render(EnvGlobal);
    expect(global).toContain("Overall environmental status");
    expect(global).toContain("1 reading outside");
    expect(global).toContain("Noise: [V2 6078]");
    const index = render(EnvIndex);
    expect(index).toContain("Parameters within limits");
    expect(index).toContain("within");
    expect(index).toContain("outside [V2 6078]");
    expect(index).toContain("Not an index: it counts readings within the backend&#x27;s limits.");
    expect(global + index).not.toMatch(/Estado ambiental|lectura fuera|dentro|fuera de/);
  });

  it("las salidas de límite y la atmósfera", () => {
    const risk = render(EnvRisk);
    expect(risk).toContain("Limit excursions (72 h)");
    expect(risk).toContain("excursions in 72 h");
    expect(risk).toContain("Comfort or target");
    expect(risk).toContain("no excursions");
    expect(risk).toContain("Normative limit");
    const air = render(EnvAir);
    expect(air).toContain("Atmosphere and air quality");
    expect(air).toContain("Oxygen (pO₂)");
    expect(air).toContain("Carbon monoxide");
    expect(risk + air).not.toMatch(/Salidas|Confort|Atmósfera|Oxígeno|sin lectura/);
  });

  it("temperatura, luz y ruido: rótulos en inglés y cifras con punto decimal", () => {
    const thermal = render(EnvThermal);
    expect(thermal).toContain("Temperature and thermal comfort");
    expect(thermal).toContain("22.5 °C");
    expect(thermal).toContain("Comfort:");
    expect(thermal).toContain("Comfort zone");
    expect(thermal).toContain("Lower limit");
    expect(thermal).toContain("Upper limit");
    const light = render(EnvLight);
    expect(light).toContain("Light and circadian cycle");
    expect(light).toContain("Lighting (latest)");
    expect(light).toContain("24 h mean");
    // El signo menos es el de F.5.6, un guion, y no un glifo.
    expect(light).toContain("<span>-24 h</span>");
    expect(light).toContain("<span>now</span>");
    expect(light).toContain("Sleep (last night)");
    expect(light).toContain("no data");
    const cabinNoise = render(EnvNoise);
    expect(cabinNoise).toContain("Cabin noise");
    expect(cabinNoise).toContain("24 h maximum");
    expect(thermal + light + cabinNoise).not.toMatch(/Temperatura|Límite|Iluminación|ahora|Sueño|sin dato|Ruido|Máximo/);
  });

  it("agua, sistemas y correlaciones: la nota, el nombre y el resumen del backend, tal cual", () => {
    const water = render(EnvWater);
    expect(water).toContain("Drinking water");
    expect(water).toContain("Total organic carbon");
    expect(water).toContain("Not evaluated: NOTA-DEL-BACKEND");
    const systems = render(EnvSystems);
    expect(systems).toContain("Environmental control: systems");
    expect(systems).toContain("not declared");
    expect(systems).toContain("SISTEMA-DEL-BACKEND");
    expect(systems).toContain("RESUMEN-DEL-BACKEND");
    const correlations = render(EnvCorrelations);
    expect(correlations).toContain("Analysis and correlations");
    expect(correlations).toContain("No pairs with enough days.");
    expect(correlations).toContain("Correlation, not cause · 3 pairs examined.");
    expect(water + systems + correlations).not.toMatch(/Agua potable|No se evalúa|sin declarar|Correlación|pares mirados/);
  });
});
