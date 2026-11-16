/**
 * «Entornos» y el perfil de misión en inglés (`lib/i18n.ts`): los rótulos propios de la interfaz
 * salen en inglés; el nombre de cada perfil, sus frases, sus notas y el estado de cada aspecto son
 * del backend y se pintan tal cual.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { EphemerisCoverage, MissionProfile, ProfileMatrix, ProfileMatrixCell } from "../lib/api";
import { language } from "../lib/i18n";
import { REFUSED_MARK } from "../lib/marks";
import { setFoldOpen } from "../components/SecondaryFold";
import { ActiveEnvironment, ENV_FOLD, ENVIRONMENTS_GROUP, EnvironmentView, environmentSections } from "./Environments";
import { AspectStatus, EphemerisCoverageView, MissionBoardWarnings, ReadDates } from "./MissionProfileView";
import { routeFigures } from "./missionProfile";

const cell = (over: Partial<ProfileMatrixCell> = {}): ProfileMatrixCell => ({
  key: "comm_delay",
  label: "rotulo",
  status: "read",
  status_text: "ESTADO-DEL-BACKEND",
  statement: "frase del backend",
  citations: [],
  discrepancy: null,
  searched: null,
  emma_note: null,
  text: "FRASE-DEL-BACKEND",
  reused_from: [],
  ...over,
});

const matrix: ProfileMatrix = {
  note: "NOTA-MATRIZ",
  declared_id: "perfil-b",
  declared_note: "NOTA-DECLARADO",
  declared_text: null,
  no_source: "sin fuente segun el backend",
  aspects: [
    { key: "comm_delay", label: "ASPECTO-A", reused_only: false },
    { key: "medical_capability", label: "ASPECTO-B", reused_only: true },
  ],
  profiles: [
    { id: "perfil-a", display: "PERFIL-A", declared: false, cells: [cell()] },
    { id: "perfil-b", display: "PERFIL-B", declared: true, cells: [cell()] },
  ],
  reused_note: "NOTA-REUTILIZADA",
  medical_note: "NOTA-MEDICA",
  pages_read: [{ title: "Pagina", url: null, read_on: ["2026-10-13", "2026-10-14"] }],
};

describe("«Entornos» en inglés", () => {
  it("este fichero corre en inglés", () => {
    expect(language()).toBe("en");
  });

  it("el grupo de pestañas se llama en inglés; cada pestaña, como la llama el backend", () => {
    expect(ENVIRONMENTS_GROUP).toBe("Environments");
    const sections = environmentSections({ matrix, failure: null });
    expect(sections.map((section) => section.label)).toEqual(["PERFIL-A", "PERFIL-B"]);
    expect(sections.every((section) => section.group === "Environments")).toBe(true);
    expect(renderToStaticMarkup(createElement("div", null, sections[1]?.note))).toContain("Declared profile");
  });

  it("mientras llegan los perfiles, y si no llegan", () => {
    const [loading] = environmentSections({ matrix: null, failure: null });
    expect(loading?.label).toBe("Environments");
    const waiting = renderToStaticMarkup(createElement("div", null, ...((loading?.panels ?? []) as never[])));
    expect(waiting).toContain('aria-label="Mission environments"');
    expect(waiting).toContain("Fetching the mission profiles…");
    const [failed] = environmentSections({ matrix: null, failure: { mark: REFUSED_MARK, text: "MOTIVO" } });
    const html = renderToStaticMarkup(createElement("div", null, ...((failed?.panels ?? []) as never[])));
    expect(html).toContain("Mission profiles unavailable: MOTIVO");
    expect(waiting + html).not.toMatch(/Entornos|Consultando|no disponibles/);
  });

  it("la vista de un entorno: lo propio en inglés y lo del backend tal cual", () => {
    // Las notas de la matriz van bajo la raya de lo secundario (lote «plegar»): desplegada, para leerlas.
    setFoldOpen(ENV_FOLD, true);
    const html = renderToStaticMarkup(createElement(EnvironmentView, { matrix, profileId: "perfil-a", declare: async () => {} }));
    // El recuento («1 de 2») lo antepone el anillo, que no es de esta unidad; aquí, su rótulo.
    expect(html).toContain('aspects read in a source"');
    expect(html).toContain('aria-label="Aspects by state"');
    expect(html).toContain("Pages read");
    expect(html).toContain("unavailable");
    expect(html).toContain("Declare as the mission environment");
    expect(html).toContain("Who");
    expect(html).toContain("Reason");
    expect(html).toContain("2026-10-13</span></span><span> and <span");
    for (const backend of ["NOTA-MATRIZ", "ASPECTO-A", "ESTADO-DEL-BACKEND", "FRASE-DEL-BACKEND", "NOTA-MEDICA"]) expect(html).toContain(backend);
    expect(html).not.toMatch(/Páginas leídas|leídos|no disponible|Declarar|Quién|Motivo|Aspectos por estado/);
    const declared = renderToStaticMarkup(createElement(EnvironmentView, { matrix, profileId: "perfil-b" }));
    expect(declared).toContain("Declared profile");
    expect(declared).not.toContain("Perfil declarado");
  });

  it("el entorno de la misión en la consola de Tierra", () => {
    const html = renderToStaticMarkup(createElement(ActiveEnvironment, { profile: { id: "perfil-a", display: "PERFIL-A" } as MissionProfile }));
    expect(html).toContain("Mission environment");
    expect(html).toContain("PERFIL-A");
  });
});

describe("el perfil de misión en inglés", () => {
  it("las cifras de la ruta que no se enseñan dicen por qué", () => {
    expect(routeFigures(false, true, "fresh", "consistent")).toMatchObject({ word: "declared profile only" });
    expect(routeFigures(true, false, "missing", "no_target")).toMatchObject({ word: "no ephemeris target" });
    expect(routeFigures(true, false, "missing", "consistent")).toMatchObject({ word: "no ephemeris" });
    expect(routeFigures(true, true, "fresh", "mismatch")).toMatchObject({ word: "profile and ephemeris do not match" });
  });

  it("un estado de aspecto que la interfaz no conoce se dice, con su clave tal cual", () => {
    const html = renderToStaticMarkup(createElement(AspectStatus, { status: "proven", children: "FRASE-RARA" }));
    expect(html).toContain("(state not recognized by the interface: «proven»)");
    expect(html).toContain("FRASE-RARA");
  });

  it("varias fechas de lectura se unen con «and»", () => {
    const html = renderToStaticMarkup(createElement(ReadDates, { dates: ["2026-10-13", "2026-10-14", "2026-10-15"] }));
    expect(html).toContain(" and ");
    expect(html).not.toContain(" y ");
  });

  const coverage: EphemerisCoverage = {
    state: "partial",
    target: "000",
    observer: "399",
    start: "2026-11-01",
    end: "2026-11-10",
    days: 10,
    covered_days: 7,
    missing_days: 3,
    covered: [{ start: "2026-11-01", end: "2026-11-07", days: 7 }],
    missing: [{ start: "2026-11-08", end: "2026-11-10", days: 3 }],
    day: { date: "2026-11-09", in_mission: false, covered: false },
    text: "FRASE-DE-COBERTURA",
    how_to_preload: "COMO-PRECARGAR",
    note: "NOTA-DE-COBERTURA",
    citations: [],
  };

  it("la cobertura de efemérides: tramos, día del estado y la frase del backend", () => {
    const html = renderToStaticMarkup(createElement(EphemerisCoverageView, { coverage }));
    expect(html).toContain("Cached ephemeris");
    expect(html).toContain("Status day:");
    expect(html).toContain("no cached ephemeris");
    expect(html).toContain(" · outside the mission days");
    expect(html).toContain(">cached<");
    expect(html).toContain("no ephemeris");
    expect(html).toMatch(/<span class="num">3<\/span> days\)/);
    expect(html).toContain("FRASE-DE-COBERTURA");
    expect(html).not.toMatch(/caché|efemérides|Día del estado|días/);
  });

  it("los avisos del tablero de misión", () => {
    const html = renderToStaticMarkup(createElement(MissionBoardWarnings, { profile: null, coverage }));
    expect(html).toContain('aria-label="Profile, conjunction and ephemeris"');
    expect(html).toContain("cached ephemeris");
    expect(html).toMatch(/<span class="num">7<\/span> of <span class="num">10<\/span> days/);
    expect(html).toContain("status day without cached ephemeris");
    expect(html).not.toMatch(/efemérides|días/);
  });
});
