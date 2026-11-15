import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml } from "../advisor/visibleText";
import { StatusStrip } from "../components/StatusStrip";
import { GroundNotesOnBoard } from "../dashboard/GroundNotesPanel";
import { EphemerisCoverageView, MissionBoardWarnings } from "../dashboard/MissionProfileView";
import { SummaryTiles } from "../dashboard/SummaryTiles";
import type { AlertCounts } from "./alerts";
import type { CrewStatus, EphemerisCoverage } from "./api";
import { type CommsStatus, DISCREPANCY_MARK, commsMark, commsStatusOf } from "./commsStatus";
import { MISSING_MARK, NO_MARK, UNAVAILABLE_MARK, mark } from "./marks";

/*
 * El estado del retardo lo dice el backend (`comms_status`, decisión del usuario, 2026-11-11), y la
 * interfaz solo le pone la marca de la tabla F.5-1: «Sin efemérides» en cian solo si de verdad
 * falta; con un perfil sin objetivo de efemérides, «No aplica» en gris; con retardo, su fuente; y la
 * discrepancia SPICE-Horizons con el triángulo en amarillo, en la franja de las dos consolas.
 */

const said = (over: Partial<CommsStatus> = {}): CommsStatus => ({
  state: "available",
  source: "spice",
  source_text: "FUENTE-DEL-BACKEND",
  word: "PALABRA-DEL-BACKEND",
  text: "FRASE-DEL-BACKEND",
  discrepancy: null,
  ...over,
});

const status = (comms: CommsStatus | undefined, over: Record<string, unknown> = {}): CrewStatus =>
  ({
    data: { reference_time: "2026-03-02T00:00:00Z", integrity_ok: true, observations: 10 },
    mission: { start: "2026-03-01", mode: "simulation", mission_day: 1, duration_days: 180, phase_display: "F" },
    monitoring: { level: "full", capabilities: [] },
    freshness: { comms: { state: "fresh" }, solar: { state: "fresh" }, basis: "" },
    comms: comms?.state === "available" || comms === undefined ? { one_way_minutes: 4, round_trip_minutes: 8 } : null,
    comms_data_age: "hace 1 s",
    declared_link: { state: "undeclared", attention: false, headline: null, sentence: "S" },
    dose: { cumulative_msv: 1, limit_msv: 600, fraction: 0.002, observation_type: "inferred" },
    ...(comms === undefined ? {} : { comms_status: comms }),
    ...over,
  }) as unknown as CrewStatus;

const none: AlertCounts = { warning: 0, caution: 0, advisory: 0, unacknowledged: 0, suppressed: 0, inhibited: 0 };
const strip = (value: CrewStatus) =>
  renderToStaticMarkup(createElement(StatusStrip, { status: value, loading: false, counts: none, consoleTitle: "T" }));
const tiles = (value: CrewStatus) => renderToStaticMarkup(createElement(SummaryTiles, { status: value, alerts: 0 }));

const discrepancy = {
  word: "DISCREPANCIA-DEL-BACKEND",
  text: "FRASE-DE-LA-DISCREPANCIA",
  epoch: "2026-11-01",
  used: "JPL Horizons",
  signed: { ledger_index: 7, recorded: "2026-11-01T00:00:00+00:00" },
};

describe("estado del retardo (comms_status)", () => {
  it("cada estado con su marca de F.5-1: disponible sin señal, no aplica en gris, falta en cian, discrepancia en amarillo", () => {
    expect(commsMark("available")).toEqual(NO_MARK);
    expect(commsMark("not_applicable")).toEqual(UNAVAILABLE_MARK);
    expect(commsMark("missing")).toEqual(MISSING_MARK);
    // Un estado que la interfaz no conoce no se pinta como «al día».
    expect(commsMark("otro")).toEqual(UNAVAILABLE_MARK);
    expect(DISCREPANCY_MARK).toEqual(mark("shape-triangle", "yellow"));
  });

  it("sin `comms_status` (backend anterior) se deduce como antes", () => {
    expect(commsStatusOf({ comms: null }).state).toBe("missing");
    expect(commsStatusOf({ comms: null }).word).toBe("Sin efemérides");
    expect(commsStatusOf(status(undefined)).state).toBe("available");
  });

  it("la franja: perfil sin objetivo en gris con la palabra del backend, nunca «Sin efemérides» en cian", () => {
    const html = strip(status(said({ state: "not_applicable", source: null, source_text: null, word: "NO-APLICA" })));
    expect(html).toMatch(markedHtml("slash-circle", "NO-APLICA", "gray"));
    expect(html).not.toContain("Sin efemérides");
    expect(html).not.toContain("c-cyan");
  });

  it("la franja: sin dato de verdad, la palabra del backend en cian", () => {
    const html = strip(status(said({ state: "missing", source: null, source_text: null, word: "FALTA" })));
    expect(html).toMatch(markedHtml("ring-dotted", "FALTA", "cyan"));
  });

  it("la franja: con retardo dice la fuente, y la discrepancia va debajo en amarillo con su frase en el título", () => {
    const html = strip(status(said()));
    expect(html).toContain("FUENTE-DEL-BACKEND");
    expect(html).not.toContain("link-declared c-yellow");
    const wrong = strip(status(said({ source: "horizons", discrepancy })));
    expect(wrong).toMatch(
      /<span class="mark link-declared c-yellow" title="FRASE-DE-LA-DISCREPANCIA"><svg [^>]*data-pictogram="shape-triangle"[^>]*>.*?<\/svg>DISCREPANCIA-DEL-BACKEND/,
    );
  });

  it("las fichas: no aplica en gris, la fuente sin color y la discrepancia en amarillo", () => {
    const blind = tiles(status(said({ state: "not_applicable", source: null, source_text: null, word: "NO-APLICA" })));
    expect(blind).toMatch(markedHtml("slash-circle", "NO-APLICA", "gray"));
    expect(blind).not.toContain("Sin efemérides");
    const fine = tiles(status(said()));
    expect(fine).toContain("FUENTE-DEL-BACKEND");
    expect(fine).not.toMatch(/c-(yellow|cyan)/);
    expect(tiles(status(said({ discrepancy })))).toMatch(markedHtml("shape-triangle", "DISCREPANCIA-DEL-BACKEND", "yellow"));
    // Caducada y discrepante: lo que hay que mirar es la discrepancia.
    const both = tiles(status(said({ discrepancy }), { freshness: { comms: { state: "stale" } } }));
    expect(both).toMatch(markedHtml("shape-triangle", "DISCREPANCIA-DEL-BACKEND", "yellow"));
  });

  it("las notas de Tierra a bordo: con un perfil sin objetivo, la frase del backend en gris", () => {
    const html = renderToStaticMarkup(
      createElement(GroundNotesOnBoard, {
        data: null,
        unavailable: null,
        oneWayMinutes: null,
        comms: said({ state: "not_applicable", source: null, source_text: null, text: "SIN-OBJETIVO." }),
      }),
    );
    expect(html).toMatch(markedHtml("slash-circle", "SIN-OBJETIVO. Se muestra todo lo firmado en Tierra.", "gray"));
    expect(html).not.toContain("Sin efemérides");
  });
});

const coverage = (over: Record<string, unknown> = {}): EphemerisCoverage =>
  ({
    state: "none",
    target: "499",
    observer: "399",
    start: "2026-11-01",
    end: "2026-11-05",
    days: 5,
    covered_days: 0,
    missing_days: 5,
    covered: [],
    missing: [{ start: "2026-11-01", end: "2026-11-05", days: 5 }],
    day: { date: "2026-11-02", in_mission: true, covered: false, offline_covered: true, served_text: "SERVIDO-POR-SPICE" },
    text: "frase de la cobertura",
    how_to_preload: null,
    note: "nota",
    citations: [],
    offline_state: "complete",
    offline_covered_days: 5,
    ...over,
  }) as unknown as EphemerisCoverage;

describe("cobertura sin red (SPICE y caché de Horizons)", () => {
  it("sin caché de Horizons pero con SPICE cubriendo, ni la frase ni el día salen en cian", () => {
    const html = renderToStaticMarkup(createElement(EphemerisCoverageView, { coverage: coverage() }));
    expect(html).not.toContain("c-cyan");
    expect(html).toContain("SERVIDO-POR-SPICE");
    const pills = renderToStaticMarkup(createElement(MissionBoardWarnings, { profile: null, coverage: coverage() }));
    expect(pills).not.toContain("c-cyan");
    expect(pills).not.toContain("día del estado sin efemérides");
    expect(pills).toContain("efemérides sin red");
  });

  it("sin ninguna de las dos, el día sí sale sin efemérides en cian", () => {
    const value = coverage({
      offline_state: "none",
      offline_covered_days: 0,
      day: { date: "2026-11-02", in_mission: true, covered: false, offline_covered: false, served_text: "NADA" },
    });
    const html = renderToStaticMarkup(createElement(EphemerisCoverageView, { coverage: value }));
    expect(html).toMatch(markedHtml("ring-dotted", "NADA", "cyan"));
    const pills = renderToStaticMarkup(createElement(MissionBoardWarnings, { profile: null, coverage: value }));
    expect(pills).toMatch(markedHtml("ring-dotted", "día del estado sin efemérides", "cyan"));
  });
});
