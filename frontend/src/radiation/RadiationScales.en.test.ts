/**
 * Las tres escalas de radiación, el historial misión a misión y la tripulación ante un evento solar,
 * en inglés (`lib/i18n.ts`). Las bases, los avisos y las frases de lo que falta son del backend y se
 * siguen pintando tal cual; aquí solo lo que la interfaz rotula.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, textNodes } from "../advisor/visibleText";
import type { CrewRadiation as View, CrewStatus, MissionHistory, RadiationScales as Scales } from "../lib/api";
import { CrewRadiationView } from "./CrewRadiation";
import { MissionHistoryView } from "./MissionHistory";
import { RadiationScales } from "./RadiationScales";

const text = (html: string) => textNodes(html).join(" ");

const status = (over: Partial<Scales> = {}): CrewStatus =>
  ({
    subject: "crew-01",
    mission: { start: "2026-01-01" },
    radiation: {
      acute: { active_event: null, time_to_action: null },
      mission: null,
      career: { value_msv: 121.25, basis: "BASE-DE-CARRERA", limit_msv: 600, limit_source: "FUENTE-LIMITE" },
      ...over,
    },
  }) as unknown as CrewStatus;

const scales = (crew: CrewStatus) =>
  renderToStaticMarkup(createElement(RadiationScales, { status: crew, operator: "CDR", onDeclareProfile: () => Promise.resolve() }));

const event: NonNullable<Scales["acute"]["time_to_action"]> = {
  detected_at: "2026-01-02T01:00:00Z",
  shelter_ready_by: "2026-01-02T02:00:00Z",
  max_stay_until: "2026-01-03T01:00:00Z",
  elapsed_minutes: 30,
  elapsed_note: null,
  basis: "BASE-DEL-PROCEDIMIENTO",
  source: { title: "TITULO", source: "FUENTE-ORION", url: "https://example.invalid/orion" },
};

describe("<RadiationScales> en inglés", () => {
  it("las tres escalas con su forma y su nombre inglés", () => {
    const html = scales(status());
    expect(html).toContain('aria-label="Radiation on three scales"');
    expect(html).toMatch(markedHtml("burst", "Acute"));
    expect(html).toMatch(markedHtml("trefoil", "This mission"));
    expect(html).toMatch(markedHtml("bar-capped", "Career"));
    expect(html).toContain('<span class="secondary">no active solar event</span>');
    expect(text(html)).toContain("no dose rate recorded");
    expect(text(html)).not.toMatch(/Aguda|Esta misión|Carrera|sin evento/);
  });

  it("la carrera: «de» es «of», la cifra con punto y la base del backend tal cual", () => {
    const html = scales(status());
    expect(html).toContain('<span class="num">121.3</span> of <span class="num">600</span> mSv');
    expect(html).toContain("BASE-DE-CARRERA");
    expect(html).toContain("Career: dose against the career limit");
  });

  it("con evento: detección, refugio y permanencia en inglés, en tiempo de misión", () => {
    const html = scales(status({ acute: { active_event: { event_type: "SEP" }, time_to_action: event } } as Partial<Scales>));
    expect(html).toContain('event detected at <span class="num">MET 1/01:00:00</span>');
    expect(html).toMatch(markedHtml("house-door", "shelter"));
    expect(html).toMatch(/shelter<\/span> set up before <span class="num">MET 1\/02:00:00<\/span>/);
    expect(html).toContain('stay until <span class="num">MET 2/01:00:00</span>');
    expect(html).not.toMatch(/evento detectado|montado antes|permanencia/);
  });

  it("el formulario del perfil se rotula en inglés", () => {
    const words = text(scales(status()));
    expect(words).toContain("Declare crew member history");
    expect(words).toContain("Prior missions");
    expect(words).toContain("Prior career dose (mSv, blank if unknown)");
    expect(words).not.toMatch(/Misiones previas|Declarar/);
  });
});

const limits = { missions: 20, name_length: 80 };

const declared: MissionHistory = {
  subject: "crew-01",
  declared: true,
  scope: "ALCANCE-DEL-BACKEND",
  limits,
  days_basis: "BASE-DE-LOS-DIAS",
  text: "DECLARADAS-DOS",
  missions: [
    { name: "Expedición 1", start: "2021-04-01", end: "2021-10-01", days: 183, dose_msv: 80.25 },
    { name: "Artemis II", start: "2024-03-01", end: "2024-03-11", days: 10, dose_msv: null },
  ],
  dose_sum_msv: 80.25,
  missions_without_dose: 1,
  declared_by: "CDR",
  recorded: "2026-10-22T10:00:00+00:00",
  ledger_index: 7,
  checks: [],
};

const history = (data: MissionHistory) =>
  renderToStaticMarkup(createElement(MissionHistoryView, { data, unavailable: null, operator: "CDR", onDeclare: () => Promise.resolve() }));

describe("<MissionHistoryView> en inglés", () => {
  it("el pliegue, la tabla y el pie; el nombre de la misión no se traduce", () => {
    const html = history(declared);
    const words = text(html);
    expect(words).toContain("Mission-by-mission history (2)");
    for (const head of ["Mission", "Start", "End", "Days", "Dose (mSv)"]) expect(words).toContain(head);
    expect(words).toContain("80.25");
    expect(words).toContain("no dose declared");
    expect(words).toContain("Days: BASE-DE-LOS-DIAS.");
    expect(words).toContain("Declared by CDR.");
    expect(words).toContain("Expedición 1");
    expect(words).toContain("Add mission");
    expect(words).toContain("Declare history");
    expect(words).not.toMatch(/Historial|Inicio|Dosis|Declarado por|Añadir|Quitar/);
  });

  it("sin filas, el mando dice lo que se firmaría", () => {
    const html = history({ ...declared, declared: false, missions: [], text: "SIN-HISTORIAL" } as unknown as MissionHistory);
    expect(text(html)).toContain("Mission-by-mission history");
    expect(text(html)).toContain("Declare: no prior missions");
    expect(text(html)).toContain("SIN-HISTORIAL");
  });
});

const crewView: View = {
  display: "TITULO (backend)",
  basis: "BASE (backend)",
  reference_time: "2026-12-01T05:00:00+00:00",
  solar_event: {
    display: "EVENTO (backend)",
    state: "none",
    text: "SIN EVENTO (backend)",
    event: null,
    source: "NASA DONKI",
    data_age: "hace 4 min",
    data_age_seconds: 240,
    freshness: {
      source: "space-weather",
      state: "fresh",
      display: "al día",
      is_current: true,
      age_seconds: 60,
      stale_after_seconds: 21600,
      stale_after_display: "6 h",
    },
    basis: "BASE DEL EVENTO (backend)",
  },
  shelter: null,
  shelter_missing_text: "SIN REFUGIO (backend)",
  location_basis: "BASE DE LA UBICACIÓN (backend)",
  crew: [
    {
      subject: "crew-01",
      location: null,
      location_state: "missing",
      location_missing_text: "SIN UBICACIÓN (backend)",
      mission: {
        value_msv: 1.2345, absorbed_mgy: 0.5, quality_factor: 2.38, hours_covered: 5,
        observation_type: "inferred", model_version: "dosis-mision@1", basis: "b",
      },
      mission_missing_text: null,
      career: {
        value_msv: 121.23, prior_msv: 120, fraction: 0.2, basis: "b",
        limit_msv: 600, limit_source: "NASA-STD-3001 [V1 4030]", observation_type: "inferred",
      },
      state_missing_text: null,
    },
  ],
  shielding: "BLINDAJE (backend)",
  note: "NOTA (backend)",
} as unknown as View;

describe("<CrewRadiationView> en inglés", () => {
  it("las columnas y el refugio se rotulan en inglés; las frases del backend, tal cual", () => {
    const html = renderToStaticMarkup(createElement(CrewRadiationView, { view: crewView, met: (iso: string) => `MET ${iso.slice(11, 16)}` }));
    const words = text(html);
    for (const head of ["Shelter", "Crew member", "Location", "This mission", "Career"]) expect(words).toContain(head);
    expect(html).toContain('<span class="num">121.2</span> of <span class="num">600</span> mSv');
    expect(html).toContain("Career of crew-01: dose against the career limit");
    expect(words).toContain("SIN REFUGIO (backend)");
    expect(words).not.toMatch(/Refugio|Tripulante|Ubicación|Esta misión|Carrera/);
  });
});
