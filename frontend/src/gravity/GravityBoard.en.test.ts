/**
 * La sección «Gravedad» en inglés (`lib/i18n.ts`): títulos, nombres cortos de las medidas, frases
 * de lo que falta y los campos gravitatorios. La fase y su base son del backend y no se tocan.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textNodes } from "../advisor/visibleText";
import type { HomeData } from "../dashboard/HomeBoard";
import {
  FIELDS,
  GRAVITY_KEYS,
  GravExercises,
  GravExposure,
  GravFields,
  type GravityData,
  GravPrediction,
  GravRisk,
  GravTests,
  GravTransition,
  GravTransitionRisks,
  TRANSITION_RISKS,
  fieldOf,
} from "./GravityBoard";

const REFERENCE = "2026-12-10T23:00:00+00:00";

function data(gravityNow = "microgravedad"): GravityData {
  const home = {
    status: {
      subject: "crew-01",
      domains: {},
      alerts: [],
      predictions: [],
      recommendations: [],
      data: { reference_time: REFERENCE },
      mission: {
        gravity_now: gravityNow,
        phase: "stable",
        phase_display: "FASE (backend)",
        phase_basis: "BASE DE LA FASE (backend)",
        phases: [{ key: "stable", display: "FASE (backend)" }],
        mission_day: 40,
        duration_days: 180,
      },
    },
    reference: Date.parse(REFERENCE),
    catalog: new Map(),
  } as unknown as HomeData;
  return {
    home,
    series: { state: "ready", value: Object.fromEntries(GRAVITY_KEYS.map((key) => [key, []])) as never },
    risks: { state: "ready", value: [] },
    links: undefined,
  };
}

const render = (component: (props: never) => unknown, grav: GravityData, extra: object = {}) =>
  renderToStaticMarkup(createElement(component as never, { grav, ...extra }));
const text = (html: string) => textNodes(html).join(" ");

describe("Gravedad en inglés", () => {
  it("la exposición: título, campos y día de misión", () => {
    const html = render(GravExposure, data());
    const words = text(html);
    expect(html).toContain('aria-label="Gravity: gravitational health"');
    expect(words).toContain("Gravity: gravitational health (RIDGE)");
    expect(words).toContain("data as of");
    for (const label of ["Earth", "Orbit (ISS)", "Moon", "Mars", "Mission day", "(now)"]) expect(words).toContain(label);
    expect(words).not.toMatch(/Gravedad|Tierra|Luna|Marte|Día de misión|ahora/);
  });

  it("la fase es la del backend; lo que queda se dice en inglés", () => {
    const words = text(render(GravTransition, data()));
    expect(words).toContain("Phase and transition");
    expect(words).toMatch(/Remaining:\s+140 d\s+of mission/);
    expect(words).toContain("BASE DE LA FASE (backend)");
    expect(words).not.toMatch(/Quedan|de misión/);
  });

  it("sin dominios, pruebas sin hacer y sin extrapolaciones: frases en inglés con su marca", () => {
    expect(text(render(GravRisk, data()))).toContain("the status does not include these domains");
    const tests = text(render(GravTests, data(), { links: undefined }));
    expect(tests).toContain("Tests and assessments");
    expect(tests).toContain("Lean mass (DXA)");
    expect(tests).toContain("not done");
    expect(tests).not.toMatch(/Pruebas|sin hacer|Masa magra/);
    const prediction = text(render(GravPrediction, data()));
    expect(prediction).toContain("No extrapolations for these indicators.");
    expect(prediction).toContain("Linear extrapolation of the trend; not a clinical forecast.");
    const exercises = text(render(GravExercises, data()));
    expect(exercises).toContain("Countermeasures (library)");
    expect(exercises).toContain("No recommendations: nothing requires action.");
  });

  it("la comparativa de campos y los riesgos de transición", () => {
    const fields = text(render(GravFields, data()));
    expect(fields).toContain("Gravity field comparison");
    expect(fields).toContain("Exposure (d)");
    expect(fields).toContain("Surface gravity (NASA Planetary Fact Sheet). Exposure: this mission only.");
    const html = render(GravTransitionRisks, data());
    const risks = text(html);
    for (const label of ["Transition risks", "Loss of balance", "Hand-eye coordination", "Space motion sickness", "no indicator", "no data"]) {
      expect(risks).toContain(label);
    }
    expect(html).toContain('title="Measured with the tandem walk (correct steps)."');
    expect(risks).not.toMatch(/Riesgos|equilibrio|Mareo|sin dato/);
  });

  it("las tablas del módulo también están en inglés, y el entorno se reconoce en los dos idiomas", () => {
    expect(FIELDS.map((field) => field.label)).toEqual(["Earth", "Orbit (ISS)", "Moon", "Mars"]);
    expect(TRANSITION_RISKS.map((risk) => risk.label)).toEqual(["Loss of balance", "Hand-eye coordination", "Space motion sickness"]);
    expect(fieldOf("en Tierra (gravedad terrestre)")?.id).toBe("earth");
    expect(fieldOf("on Earth (Earth gravity)")?.id).toBe("earth");
    expect(fieldOf("microgravedad")?.id).toBe("iss");
    expect(fieldOf("microgravity")?.id).toBe("iss");
    expect(fieldOf("gravedad marciana")?.id).toBe("mars");
    expect(fieldOf("Martian gravity")?.id).toBe("mars");
    expect(fieldOf("lunar gravity")?.id).toBe("moon");
    expect(fieldOf("otra cosa")).toBeNull();
  });
});
