import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, pictogramSvg } from "../advisor/visibleText";
import { LookContext } from "../components/BoardOnly";
import type { CrewStatus } from "../lib/api";
import { formatMinutes, formatNumber } from "../lib/format";
import { uiPictogram } from "../lib/uiMarks";
import { SummaryTiles } from "./SummaryTiles";

/*
 * Las fichas del resumen (§5.33.2): las cifras que la consola ya daba en frases, con el rótulo que
 * ya tenían y el signo de su concepto. Lo que falta se dice con la marca de dato ausente y nunca
 * como cero; lo caducado conserva la cifra, en cursiva y con la edad de las efemérides. Desde el
 * tablero (2026-11-07), bajo la concha de la maqueta el día y la dosis llevan su medidor con la
 * escala del backend; en la clásica, no.
 */

const status = (over: Partial<CrewStatus> = {}): CrewStatus =>
  ({
    mission: { mission_day: 40.25, duration_days: 180, phase_display: "FASE-DEL-BACKEND" },
    comms: { one_way_minutes: 4.2, round_trip_minutes: 8.4 },
    comms_data_age: "hace 2 h",
    freshness: { comms: { state: "fresh" } },
    dose: { cumulative_msv: 12.34, limit_msv: 600, fraction: 0.02, observation_type: "inferred" },
    data: { observations: 1234 },
    ...over,
  }) as unknown as CrewStatus;

const render = (value: CrewStatus, alerts = 3) =>
  renderToStaticMarkup(createElement(SummaryTiles, { status: value, alerts }));

const label = (concept: Parameters<typeof uiPictogram>[0], word: string) =>
  new RegExp(`<span class="stat-label">${pictogramSvg(uiPictogram(concept))}${word}</span>`);

describe("fichas del resumen", () => {
  it("cinco cifras, cada una con el rótulo que ya existía y el signo de su concepto", () => {
    const html = render(status());
    expect(html).toContain('role="group" aria-label="Resumen"');
    expect(html).toMatch(label("missionDay", "Día"));
    expect(html).toMatch(label("lightTime", "Retardo con Tierra"));
    expect(html).toMatch(label("alerts", "Alertas activas"));
    expect(html).toMatch(label("radiation", "Dosis de carrera"));
    expect(html).toMatch(label("value", "Lecturas analizadas"));
    expect(html).toContain(`<span class="num">${formatNumber(40.25, 1)}</span> <span class="stat-unit">de 180</span>`);
    expect(html).toContain(`<span class="num">${formatMinutes(4.2)}</span> <span class="stat-unit">ida</span>`);
    expect(html).toContain(`<span class="num">${formatNumber(12.34, 1)}</span> <span class="stat-unit">mSv</span>`);
    expect(html).toContain(`<span class="num">${formatNumber(1234)}</span>`);
    // Sin color propio: ni una clase de la paleta cuando nada falta ni caduca.
    expect(html).not.toMatch(/c-(cyan|yellow|red|green|blue|gray)/);
    expect(html).not.toContain("stale");
  });

  it("sin efemérides no hay retardo, y sin dosis facilitada no hay dosis: nunca un cero", () => {
    const html = render(
      status({
        comms: null,
        dose: { cumulative_msv: null, limit_msv: 600, fraction: null, observation_type: "inferred" },
      }),
    );
    expect(html).toMatch(markedHtml("ring-dotted", "Sin efemérides", "cyan"));
    expect(html).toMatch(markedHtml("ring-dotted", "sin datos", "cyan"));
    expect(html).not.toContain("mSv");
    expect(html.match(/class="stat-value"/g)).toHaveLength(3);
  });

  it("con efemérides caducadas la cifra se queda, en cursiva y con su edad", () => {
    const html = render(status({ freshness: { comms: { state: "stale" } } as CrewStatus["freshness"] }));
    expect(html).toMatch(/<div class="stat-tile stale"><span class="stat-label">[\s\S]*?Retardo con Tierra/);
    expect(html).toContain(formatMinutes(4.2));
    expect(html).toMatch(markedHtml("ring-dotted", "efemérides hace 2 h", "cyan"));
  });

  it("bajo la concha nueva, el día y la dosis llevan su medidor con la escala que dio el backend", () => {
    const html = render(status());
    expect(html.match(/role="meter"/g)).toHaveLength(2);
    expect(html).toMatch(
      /role="meter" aria-label="Día de misión sobre la duración prevista" aria-valuemin="0" aria-valuemax="180" aria-valuenow="40.25"/,
    );
    expect(html).toMatch(
      /role="meter" aria-label="Dosis acumulada sobre el límite de carrera" aria-valuemin="0" aria-valuemax="600" aria-valuenow="12.34"/,
    );
    expect(html).not.toContain("meter-oor");
  });

  it("sin fracción de dosis no hay medidor de dosis; fuera de la duración prevista, el del día dice la fase del backend", () => {
    const noFraction = render(
      status({ dose: { cumulative_msv: 12.34, limit_msv: 600, fraction: null, observation_type: "inferred" } }),
    );
    expect(noFraction.match(/role="meter"/g)).toHaveLength(1);
    expect(noFraction).toContain("mSv");
    const preflight = render(status({ mission: { mission_day: -3, duration_days: 180, phase_display: "FASE-DEL-BACKEND" } } as never));
    expect(preflight).toMatch(/class="meter meter-oor" role="meter" aria-label="Día de misión[^"]*"[^>]*aria-valuetext="FASE-DEL-BACKEND"/);
    expect(preflight).toContain(">FASE-DEL-BACKEND</span>");
  });

  it("en la concha clásica no hay medidores: las fichas son las de antes", () => {
    const html = renderToStaticMarkup(
      createElement(LookContext.Provider, { value: "classic" }, createElement(SummaryTiles, { status: status(), alerts: 3 })),
    );
    expect(html).not.toContain('role="meter"');
    expect(html.match(/class="stat-value"/g)).toHaveLength(5);
  });

  it("la consola de tripulación las monta justo después del resumen", () => {
    const source = readFileSync(fileURLToPath(new URL("./CrewConsole.tsx", import.meta.url)), "utf-8");
    const summary = source.indexOf("<p>{status.summary}</p>");
    const tiles = source.indexOf("<SummaryTiles status={status} alerts={alerts.length} />");
    expect(summary).toBeGreaterThan(-1);
    expect(tiles).toBeGreaterThan(summary);
    expect(source.slice(summary, tiles)).not.toContain("<section");
  });
});
