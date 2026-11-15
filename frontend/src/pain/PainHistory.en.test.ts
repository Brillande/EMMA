/**
 * «Dolor referido» (consola de Tierra) en inglés (`lib/i18n.ts`). Las zonas y los tipos de dolor
 * son palabras del backend; las claves del cambio (`sube`, `baja`…) no son texto y no cambian.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { PainCatalog, PainReport } from "../lib/api";
import { CHANGES, PainEvolution, PainHistory, ReceivedPainBoard } from "./PainHistory";

const CATALOG: PainCatalog = {
  system: "https://emma.mission/pain",
  scale: { min: 1, max: 10, unit: "{score}" },
  zones: [{ key: "lower-back", display: "ZONA-LUMBAR", side: null }],
  characters: [{ key: "dull", display: "PALABRA-SORDO" }],
};

const report = (effective: string, intensity: number | null) =>
  ({
    subject: "crew-01",
    effective,
    reported_by: "cmdr",
    zones: intensity === null ? [] : [{ zone: "lower-back", intensity, characters: ["dull"] }],
    intensity: intensity ?? 0,
    ledger_index: 0,
    recorded: effective,
    discuss: { reasons: [], note: null },
  }) as unknown as PainReport;

const render = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element);

describe("el dolor referido en inglés", () => {
  it("el panel: su título", () => {
    const html = render(createElement(PainHistory, { subject: "crew-01", oneWayMinutes: 10 }));
    expect(html).toContain('aria-label="Reported pain"');
    expect(html).not.toContain("Dolor referido");
  });

  it("la evolución: la línea del último informe, las cabeceras y el cambio", () => {
    const reports = [report("2026-09-20T08:00:00Z", 4), report("2026-09-21T08:00:00Z", 6)];
    const html = render(createElement(PainEvolution, { catalog: CATALOG, reports }));
    expect(html).toContain("Latest report: 2026-09-21 08:00 UTC, by cmdr");
    expect(html).toMatch(/maximum <span class="num">6<\/span> of <span class="num">10<\/span>/);
    expect(html).toMatch(/<span class="num">2<\/span> reports/);
    for (const head of ["Zone", "Now", "Previous", "Change", "Type (latest)"]) expect(html, head).toContain(head);
    expect(html).toContain("ZONA-LUMBAR");
    expect(html).toContain("PALABRA-SORDO");
    expect(html).toMatch(/>up<\/span>/);
    expect(html).not.toMatch(/Último informe|máximo|informes|Zona|Ahora|Anterior|Cambio|sube/);
  });

  it("sin informes y sin dolor", () => {
    expect(render(createElement(PainEvolution, { catalog: CATALOG, reports: [] }))).toContain("No pain reports recorded.");
    const html = render(createElement(PainEvolution, { catalog: CATALOG, reports: [report("2026-09-21T08:00:00Z", null)] }));
    expect(html).toContain("no pain");
    expect(html).not.toContain("sin dolor");
  });

  it("las palabras del cambio, con sus claves de siempre", () => {
    expect(Object.keys(CHANGES)).toEqual(["sube", "baja", "igual", "nueva"]);
    expect(Object.values(CHANGES).map((item) => item.word)).toEqual(["up", "down", "same", "first time"]);
  });

  it("las fichas del tablero", () => {
    const html = render(
      createElement(ReceivedPainBoard, { reports: [report("2026-10-22T08:00:00Z", 6)], catalog: CATALOG, stale: false }),
    );
    expect(html).toContain('aria-label="Latest pain report received"');
    for (const word of ["Maximum intensity", "of 10", "Zones", "Reports"]) expect(html, word).toContain(word);
    expect(html).not.toMatch(/Intensidad|Zonas|Informes/);
  });
});
