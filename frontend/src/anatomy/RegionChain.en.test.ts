/**
 * La cadena de una región, la silueta y la figura del esqueleto, en inglés (`lib/i18n.ts`): los
 * títulos de cada eslabón y las frases de lo que falta. El nombre de la región, su nota y todo lo
 * demás que redacta el backend se pintan tal cual.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textNodes } from "../advisor/visibleText";
import { ApiError, type AnatomyRegionState, type CrewStatus, type SubjectSkeleton } from "../lib/api";
import { requestOutcome } from "../lib/marks";
import { BodySilhouette } from "./BodySilhouette";
import { NO_STATE } from "./chain";
import { RegionChain, StateBadge } from "./RegionChain";
import { sourceTone } from "./skeleton";
import type { AnatomyView } from "./useAnatomyState";

const text = (html: string) => textNodes(html).join(" ");

const status = {
  subject: "crew-01",
  mission: { start: "2026-11-01" },
  data: { reference_time: "2026-12-11T00:00:00+00:00", trend_window_days: 21 },
  inferred: [],
} as unknown as CrewStatus;

const region = {
  key: "liver",
  display: "REGIÓN (backend)",
  note: "NOTA (backend)",
  note_refs: [],
  function: null,
  function_note: "SIN FUNCIÓN (backend)",
  function_refs: [],
  data_note: null,
  level: null,
  level_of: null,
  level_note: null,
  level_risk: null,
  domains: [],
  state: [],
  variables: [],
  unmeasured: [],
  evidence: [],
  analytes_source: null,
  research: null,
  recommendations_note: null,
  recommendations: [],
  context: null,
} as unknown as AnatomyRegionState;

describe("<RegionChain> en inglés", () => {
  const html = renderToStaticMarkup(
    createElement(RegionChain, { region, status, operator: "CDR", following: new Set<string>(), onAdopt: () => Promise.resolve() }),
  );
  const words = text(html);

  it("cada eslabón lleva su título y su nombre accesible en inglés", () => {
    for (const title of ["Function", "State", "Variables", "Evidence", "Trend", "Risk", "Countermeasure", "External context"]) {
      expect(html).toContain(`aria-label="${title}"`);
      expect(words).toContain(title);
    }
    expect(html).not.toMatch(/aria-label="(Función|Estado|Evidencia|Tendencia|Riesgo|Contramedida|Contexto externo)"/);
  });

  it("lo que falta se dice en inglés; lo del backend, tal cual", () => {
    expect(words).toContain("No readings: there is no series to look at.");
    expect(words).toContain("No external context in the response.");
    expect(words).toContain("REGIÓN (backend)");
    expect(words).toContain("NOTA (backend)");
    expect(words).toContain("SIN FUNCIÓN (backend)");
    expect(words).not.toMatch(/Sin lecturas|Sin contexto externo/);
  });

  it("sin nivel, «No data» en cian con su anillo: nunca un nivel", () => {
    expect(NO_STATE.label).toBe("No data");
    const badge = renderToStaticMarkup(createElement(StateBadge, { level: null }));
    expect(text(badge)).toContain("No data");
    expect(badge).toContain("c-cyan");
    expect(badge).toContain('data-pictogram="ring-dotted"');
  });
});

describe("la silueta y el esqueleto en inglés", () => {
  it("la silueta dice en inglés que no pudo leer el estado, con el motivo del backend", () => {
    const view: AnatomyView = { state: null, error: requestOutcome(new ApiError(503, "MOTIVO (backend)")), stale: true } as AnatomyView;
    const html = renderToStaticMarkup(createElement(BodySilhouette, { view, selected: null, onSelect: () => undefined }));
    expect(html).toContain('aria-label="Body regions"');
    expect(text(html)).toContain("Could not get the state by region:");
    expect(text(html)).toContain("MOTIVO (backend)");
    expect(text(html)).toContain("The state by region is older than the one the console shows; it is updating.");
    expect(text(html)).not.toMatch(/No se pudo|se está actualizando/);
  });

  it("de dónde sale la figura del esqueleto", () => {
    const own = { source: "own-ct", simulated: false, fallback_kind: null } as unknown as SubjectSkeleton;
    expect(sourceTone(own).word).toBe("Crew member's CT");
    expect(sourceTone({ ...own, simulated: true }).word).toBe("Sample CT");
    expect(sourceTone({ ...own, source: "reference" } as unknown as SubjectSkeleton).word).toBe("Reference");
  });
});
