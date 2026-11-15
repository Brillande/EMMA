/**
 * «Inicio» en inglés (`lib/i18n.ts`): los rótulos de las tarjetas, los accesos («Open …») y la
 * tarjeta de ayuda urgente se leen en inglés; lo del backend (nombres de peligro, resumen, acciones)
 * se pinta tal cual. La forma de cada pieza la fijan sus pruebas en castellano.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { CrewStatus } from "../lib/api";
import { language } from "../lib/i18n";
import { RouteArt } from "./HomeArt";
import {
  HomeCrewColumn,
  HomeDivider,
  HomeEssential,
  HomeFooter,
  HomeGlobal,
  type HomeLinks,
  HomeQuickHazards,
  HomeRiskColumn,
  HomeRoutes,
  type useHomeData,
} from "./HomeBoard";
import { Ring } from "./HomeCharts";

type HomeData = ReturnType<typeof useHomeData>;

const status = {
  subject: "CM-1",
  summary: "RESUMEN-DEL-BACKEND",
  overall_level: "watch",
  comms: null,
  domains: { radiation: { level: "nominal" }, cardiovascular: { level: "watch" } },
  followups: [
    {
      adoption_index: 3,
      countermeasure: { id: "cm-a", action: "ACCION-EN-SEGUIMIENTO" },
      domain: "cardiovascular",
      window_ends: "2026-11-12T00:00:00Z",
      state: "in_window",
    },
  ],
  recommendations: [{ domain: "radiation", action: "ACCION-RECOMENDADA" }],
  predictions: [],
  dose: { cumulative_msv: null },
  data: { reference_time: "2026-11-09T00:00:00Z" },
  mission: { start: "2026-11-01", phase_display: "FASE-DEL-BACKEND", profile: null, mission_day: 8, duration_days: 180, gravity_display: "GRAVEDAD-DEL-BACKEND" },
} as unknown as CrewStatus;

const home = {
  status,
  reference: Date.parse("2026-11-09T00:00:00Z"),
  ridge: { state: "ready", value: {} },
  groups: [{ hazard: "radiation", display: "PELIGRO-DEL-BACKEND", domains: ["radiation"] }],
  indicators: { state: "ready", value: [] },
  catalog: new Map(),
  seriesOf: () => ({ state: "ready", value: [] }),
  readingsFor: () => [],
  diary: { state: "ready", value: [] },
  matrix: { profiles: [] },
  matrixFailure: null,
  shownRoute: null,
  setRoute: () => undefined,
  declaredShort: null,
  anatomy: { state: null, error: null, stale: false },
  region: null,
  setRegion: () => undefined,
  lowest: "nominal",
  atLowest: 1,
  domainCount: 2,
  overall: "watch",
  overallStyle: null,
  elapsed: 0,
} as unknown as HomeData;

const NAMES: Record<string, string> = { hazards: "Hazards and alerts", routines: "SECCION-RUTINAS", body: "SECCION-CUERPO", mission: "SECCION-MISION" };
const links: HomeLinks = { openSection: () => undefined, sectionName: (key) => NAMES[key] ?? null };

const render = (node: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(node);

describe("«Inicio» en inglés", () => {
  it("este fichero corre en inglés", () => {
    expect(language()).toBe("en");
  });

  it("el marco global: títulos, vitales y accesos", () => {
    const html = render(createElement(HomeGlobal, { home, links }));
    for (const word of [
      'aria-label="Crew global panel"',
      "Global panel: crew",
      "Data as of",
      "Mission status",
      "RIDGE hazards (global)",
      'aria-label="1 of 2 domains"',
      "domains at ",
      "Vital signs ",
      "no readings",
      "Trend (24 h) ",
      'aria-label="Open SECCION-MISION: mission status"',
      'aria-label="Open Hazards and alerts: PELIGRO-DEL-BACKEND"',
      'aria-label="Open SECCION-CUERPO: vital signs"',
      'aria-label="Open SECCION-CUERPO: 24-hour trend"',
      ">HR<",
      ">RR<",
    ]) {
      expect(html, word).toContain(word);
    }
    expect(html).not.toMatch(/Panel global|Datos a|Estado de la misión|Peligros RIDGE|Signos vitales|sin lecturas|Tendencia|Abrir |>FC<|>FR</);
    expect(html).toContain("RESUMEN-DEL-BACKEND");
  });

  it("la columna del tripulante y la de riesgo", () => {
    const crew = render(createElement(HomeCrewColumn, { home, links }));
    for (const word of ["Crew member: ", ">Status<", ">Phase<", ">Time<", "RIDGE hazards (individual)", "Notes / logbook (", "No diary entries."]) {
      expect(crew, word).toContain(word);
    }
    expect(crew).toContain("FASE-DEL-BACKEND");
    expect(crew).not.toMatch(/Tripulante|>Estado<|>Fase<|>Tiempo<|bitácora|Sin entradas/);

    const risk = render(createElement(HomeRiskColumn, { home, links }));
    for (const word of ["Risk status", "Current overall level", "Next actions", "ACCION-EN-SEGUIMIENTO", "ACCION-RECOMENDADA"]) {
      expect(risk, word).toContain(word);
    }
    expect(risk).toMatch(/aria-label="Open SECCION-RUTINAS: ACCION-EN-SEGUIMIENTO" title="[^"]*\nUntil MET /);
    expect(risk).not.toMatch(/Estado de riesgo|Nivel global actual|Próximas acciones|Hasta /);
  });

  it("un fin de seguimiento ilegible no tumba el tablero: sale la raya de «sin dato»", () => {
    const broken = {
      ...home,
      status: { ...status, followups: [{ ...status.followups[0], window_ends: "no es una fecha" }] },
    } as unknown as HomeData;
    const html = render(createElement(HomeRiskColumn, { home: broken, links }));
    expect(html).toContain("Until —");
  });

  it("el acceso rápido, las rutas y el pie", () => {
    const quick = render(createElement(HomeQuickHazards, { home, links }));
    expect(quick).toContain("RIDGE hazards: quick access");
    expect(quick).toContain("View indicators in detail");
    expect(quick).not.toMatch(/acceso rápido|Ver indicadores/);

    const routes = render(createElement(HomeRoutes, { home }));
    for (const word of ["Space routes: health impact", ">Route<", "Day", "Distance", "Delay", "Dose", "not provided", "Gravity", "Status projections ", "No projections for this crew member.", "Route analysis", "No mission profile declared and no route chosen."]) {
      expect(routes, word).toContain(word);
    }
    expect(routes).toContain("GRAVEDAD-DEL-BACKEND");
    expect(routes).not.toMatch(/Rutas espaciales|>Ruta<|Distancia|Retardo|Dosis|no facilitada|Gravedad|Proyecciones|Análisis/);

    const footer = render(createElement(HomeFooter, { home, links, essential: false }));
    expect(footer).toContain("Social connection and outreach");
    expect(footer).toContain("Extension: Earth and communities");
    expect(footer).not.toMatch(/divulgación|Extensión/);
  });

  it("la raya de lo secundario y la tarjeta de ayuda urgente", () => {
    const open = render(createElement(HomeDivider, { open: true, onToggle: () => undefined }));
    expect(open).toContain("Hide the secondary content");
    expect(open).toContain("Space routes, outreach and extension");
    const closed = render(createElement(HomeDivider, { open: false, onToggle: () => undefined, name: "the reserves" }));
    expect(closed).toContain("Show the reserves");
    expect(open + closed).not.toMatch(/Ocultar|Mostrar|lo secundario/);

    const help = render(createElement(HomeEssential, { home, links }));
    expect(help).toContain('aria-label="Urgent help"');
    expect(help).toContain("One touch alerts the crew at once, whoever is closest first, and Earth, which receives it one light time later.");
    expect(help).toContain("Request help");
    expect(help).not.toMatch(/Ayuda urgente|Un toque|Pedir ayuda/);
  });

  it("los dibujos con nombre: la ruta y el anillo", () => {
    expect(render(createElement(RouteArt, { target: "DESTINO", targetId: "mars-transit" }))).toContain('aria-label="Route from Earth to DESTINO"');
    expect(render(createElement(Ring, { done: 3, total: 12, label: "X", children: null }))).toContain('aria-label="3 of 12 X"');
  });
});
