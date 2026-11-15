/**
 * «Peligros y alertas» en inglés (`lib/i18n.ts`): los rótulos que escribe la interfaz se leen en
 * inglés y no queda el castellano; lo que viene del backend (aquí, textos de ejemplo en castellano)
 * se pinta tal cual. Las reglas de forma y de color las fijan las pruebas en castellano de cada
 * pieza; aquí solo lo que cambia con el idioma.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textLines } from "../advisor/visibleText";
import type { Alert, AlertCounts } from "../lib/alerts";
import type { AlertDetail, AlertState, CrewStatus, Framework, RoutineState, WaitingView } from "../lib/api";
import { language } from "../lib/i18n";
import { AlertDetailView } from "./AlertDetailView";
import { type AlertActions, AlertRow } from "./AlertRow";
import { AlertTally, DomainLevelTally, HazardCardsView } from "./HazardCards";
import { SummaryTiles } from "./SummaryTiles";
import { RoutineList, WaitingBody } from "./TimelinePieces";

const text = (html: string) => textLines(html).join(" ");

describe("«Peligros y alertas» en inglés", () => {
  it("este fichero corre en inglés", () => {
    expect(language()).toBe("en");
  });

  it("las fichas del resumen: rótulos y unidades en inglés, sin el castellano", () => {
    const status = {
      mission: { mission_day: 40.25, duration_days: 180, phase_display: "FASE-DEL-BACKEND" },
      comms: { one_way_minutes: 4.2, round_trip_minutes: 8.4 },
      comms_data_age: "hace 2 h",
      freshness: { comms: { state: "fresh" } },
      dose: { cumulative_msv: null, limit_msv: 600, fraction: null },
      data: { observations: 1234 },
    } as unknown as CrewStatus;
    const html = renderToStaticMarkup(createElement(SummaryTiles, { status, alerts: 3 }));
    expect(html).toContain('aria-label="Summary"');
    for (const word of ["Day", "of 180", "Delay to Earth", "one way", "Active alerts", "Career dose", "no data", "Readings analysed"]) {
      expect(html, word).toContain(word);
    }
    for (const word of ["Resumen", "Día", "Retardo con Tierra", "Alertas activas", "Dosis de carrera", "sin datos", "Lecturas analizadas"]) {
      expect(html, word).not.toContain(word);
    }
    // El decimal, con punto (F.5.6).
    expect(html).toContain("40.3");
  });

  const RIDGE: Framework["ridge"] = {
    cardiovascular: { hazard: "gravity", display: "gravity fields" },
    nutrition: { hazard: "distance", display: "distance from Earth" },
  };
  const hazards = (oneWay: number | null) =>
    ({
      comms: oneWay === null ? null : { one_way_minutes: oneWay },
      comms_status: { state: "missing", word: "PALABRA-DEL-BACKEND", text: "FRASE-DEL-BACKEND" },
      domains: {
        cardiovascular: { level: "concern", score: 2, drivers: [] },
        nutrition: { level: "nominal", score: 0, drivers: [] },
      },
    }) as unknown as CrewStatus;

  it("los cinco peligros: título, retardo y recuento de dominios", () => {
    const html = renderToStaticMarkup(createElement(HazardCardsView, { ridge: RIDGE, status: hazards(4.2) }));
    expect(html).toContain('aria-label="The five hazards"');
    expect(text(html)).toContain("One-way delay 4.2 min");
    expect(text(html)).toContain("1 domain");
    expect(html).not.toContain("Los cinco peligros");
    expect(html).not.toContain("Retardo de ida");
    expect(html).not.toContain("dominio");
    const none = renderToStaticMarkup(createElement(HazardCardsView, { ridge: RIDGE, status: hazards(null) }));
    expect(text(none)).toContain("Delay to Earth: no ephemeris");
  });

  it("los recuentos del tablero", () => {
    const counts: AlertCounts = { warning: 0, caution: 2, advisory: 1, unacknowledged: 1, suppressed: 2, inhibited: 1 };
    const tally = renderToStaticMarkup(createElement(AlertTally, { counts }));
    expect(tally).toContain('aria-label="Alert counts"');
    expect(text(tally)).toContain("unacknowledged 1");
    expect(text(tally)).toContain("suppressed 2");
    expect(text(tally)).toContain("inhibited 1");
    expect(tally).not.toMatch(/sin reconocer|suprimidas|inhibidas/);
    const domains = { bone: { level: "nominal", score: 0, drivers: [] }, raro: { level: "elevated", score: 1, drivers: [] } };
    const levels = renderToStaticMarkup(createElement(DomainLevelTally, { domains: domains as never }));
    expect(levels).toContain('aria-label="Domains by level"');
    expect(text(levels)).toContain("no level 1");
    expect(text(levels)).toContain("2 domains");
    expect(levels).not.toMatch(/sin nivel|dominios/);
  });

  const alert: Alert = { id: "behavioral:watch", domain: "behavioral", level: "watch", drivers: ["frase del motor"] };
  const rowStatus = (comms: CrewStatus["comms"]) =>
    ({ data: { reference_time: "2026-11-13T04:00:00+00:00" }, mission: { start: "2026-11-01" }, comms }) as unknown as CrewStatus;
  const state = (over: Partial<AlertState>): AlertState =>
    ({
      annunciation: "normal",
      acknowledged: false,
      acknowledged_by: null,
      silenced_until: null,
      silenced_by: null,
      silenced_reason: null,
      ...over,
    }) as unknown as AlertState;
  const row = (shown: AlertState) =>
    renderToStaticMarkup(
      createElement(AlertRow, {
        alert,
        state: shown,
        status: rowStatus({ one_way_minutes: 14 } as unknown as NonNullable<CrewStatus["comms"]>),
        operator: "CDR",
        actions: {} as AlertActions,
      }),
    );

  it("una alerta: los mandos, su estado y lo que el retardo significa para ella", () => {
    const fresh = row(state({}));
    for (const word of ["Acknowledge", "Suppress…", "Inhibit…"]) expect(fresh, word).toContain(word);
    expect(fresh).not.toMatch(/Reconocer|Suprimir|Inhibir/);
    expect(text(fresh)).toMatch(/Earth will know at MET \S+ · its reply cannot arrive before MET \S+/);
    expect(fresh).not.toContain("Tierra lo sabrá");
    // La frase del motor es del backend: tal cual.
    expect(fresh).toContain("frase del motor");

    const seen = row(state({ acknowledged: true, acknowledged_by: "CDR" }));
    expect(text(seen)).toContain("Acknowledged by CDR");
    for (const word of ["Detected", "Being fixed", "Dismiss…"]) expect(seen, word).toContain(word);
    expect(seen).not.toMatch(/Reconocida|Detectada|En arreglo|Descartar/);

    const silenced = row(state({ annunciation: "suppressed", silenced_by: "CDR", silenced_reason: "sensor" }));
    expect(text(silenced)).toMatch(/Suppressed until — by CDR: sensor/);
    expect(silenced).toContain("Enable…");
    expect(silenced).not.toMatch(/Suprimida|Habilitar|hasta/);
  });

  it("el detalle de una alerta: las preguntas en inglés, las respuestas del backend tal cual", () => {
    const detail = {
      domain: "behavioral",
      onset: null,
      onset_basis: "BASE-DEL-INICIO",
      changed: [],
      trends: [],
      relevance: "RELEVANCIA-DEL-BACKEND",
      relevance_evidence: null,
      concordance: { statement: "CONCORDANCIA", indicators: [], trigger_basis: "", basis: "" },
      persistence: { statement: "PERSISTENCIA", indicators: [], basis: "" },
      confidence: { statement: "CONFIANZA", indicators: [], trend_note: null, note: "", basis: "" },
      checks: { items: [], statement: "SIN-COMPROBACIONES" },
      evidence: { items: [], statement: "SIN-EVIDENCIA" },
    } as unknown as AlertDetail;
    const html = renderToStaticMarkup(
      createElement(AlertDetailView, {
        detail,
        level: "watch",
        status: rowStatus(null),
        alertTime: { acknowledged_after_minutes: 12, countermeasure_after_minutes: null, basis: "BASE-DEL-TIEMPO" } as never,
      }),
    );
    for (const word of [
      "Detail: what changed, since when and why",
      "What changed",
      "no readings outside the expected in the window",
      "Since when",
      "Against which baseline",
      "Agreement between signals",
      "Persistence",
      "Confidence in the readings",
      "Time to action",
      "What context changed",
      "Why it may matter",
      "What to check",
      "Which step it is at",
      "What depends on these data",
      "Evidence",
    ]) {
      expect(html, word).toContain(word);
    }
    expect(text(html)).toContain("acknowledged after 12 min · countermeasure pending");
    expect(html).not.toMatch(/Qué cambió|Desde cuándo|Frente a qué base|Tiempo hasta la acción|Qué comprobar|reconocida|pendiente/);
    for (const word of ["BASE-DEL-INICIO", "RELEVANCIA-DEL-BACKEND", "CONCORDANCIA", "SIN-EVIDENCIA", "BASE-DEL-TIEMPO"]) {
      expect(html, word).toContain(word);
    }
  });

  it("las medidas periódicas y lo que espera por una persona", () => {
    const routine = (key: string, stateOf: RoutineState["state"]): RoutineState =>
      ({ key, display_es: `MEDIDA-${key}`, state: stateOf, last_run: null, period_hours: 24, basis: "BASE" }) as unknown as RoutineState;
    const html = renderToStaticMarkup(
      createElement(RoutineList, {
        items: [routine("a", "al-dia"), routine("b", "nunca-corrio"), routine("c", "atrasada")],
        met: (iso: string) => `MET(${iso})`,
      }),
    );
    expect(html).toContain("1 of 3 measurements on time");
    expect(html).toContain('aria-label="Measurements by state"');
    expect(html).toContain("on time");
    expect(text(html)).toContain("· last — · every 24 h (BASE)");
    expect(text(html)).toContain("1 measurements with no reading");
    expect(html).not.toMatch(/al día|sin ninguna lectura|última|cada|Medidas/);

    const waiting = renderToStaticMarkup(
      createElement(WaitingBody, {
        view: {
          incongruences: [{ sample: "M1", key: "ferritin" }],
          waiting: [{ kind: "ack", title: "TITULO-DEL-BACKEND", days: 4 }],
          threshold_days: 3,
        } as unknown as WaitingView,
      }),
    );
    expect(text(waiting)).toContain("ferritin, M1: two reports do not match");
    expect(text(waiting)).toContain("TITULO-DEL-BACKEND · 4 days");
    expect(text(waiting)).toContain("Only what has been waiting 3 days or more.");
    expect(waiting).not.toMatch(/días|dos informes/);
  });
});
