/**
 * El hábitat en inglés (`lib/i18n.ts`): las palabras propias de la interfaz —«sin dato», «fuera
 * de …», los rótulos de los formularios— salen en inglés, y lo que da el backend (nombres,
 * requisitos, frases) se pinta tal cual. Los asertos castellanos siguen en sus ficheros de siempre.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { CrewHypothesis, CrewOverview, HabitatExcursion, HabitatParameter, HabitatReading, LocationAnchors } from "../lib/api";
import { language } from "../lib/i18n";
import { HabitatBoard, HabitatRow, HypothesisPlaceLine } from "./HabitatPanel";
import { HypothesisReview } from "./HypothesisReview";
import { EMPTY_ANCHOR_FORM, LocationAnchorsView } from "./LocationAnchors";
import { LocationSource } from "./LocationSource";
import { healthRange } from "./flow";

const ppco2: HabitatParameter = {
  key: "cabin-ppco2",
  display: "NOMBRE-DEL-BACKEND",
  unit: "mm[Hg]",
  limits: [{ low: null, high: 3, requirement: "[V2 6004]", kind: "health", averaging_minutes: 60 }],
  averaging_minutes: 60,
  source: { id: "ochmo-tb-002", title: "OCHMO-TB-002", url: "https://www.nasa.gov/", read_on: "2026-10-21" },
};

const excursion = (kind: HabitatExcursion["kind"], requirement: string): HabitatExcursion => ({
  module: "habitat-principal",
  parameter: "cabin-ppco2",
  display: ppco2.display,
  unit: ppco2.unit,
  kind,
  requirement,
  start: "2026-11-10T00:00:00+00:00",
  end: "2026-11-10T02:00:00+00:00",
  worst: 5.3,
});

const row = (value: number | null, active: HabitatExcursion | null = null, comfort: HabitatExcursion | null = null) =>
  renderToStaticMarkup(createElement("dl", null, createElement(HabitatRow, { spec: ppco2, value, active, comfort })));

describe("el hábitat en inglés", () => {
  it("este fichero corre en inglés", () => {
    expect(language()).toBe("en");
  });

  it("la fila de atmósfera: «no data», «outside …» con el requisito tal cual y punto decimal", () => {
    expect(row(null)).toContain("no data");
    expect(row(null)).not.toContain("sin dato");
    const health = row(5.3, excursion("health", "[V2 6004]"));
    expect(health).toContain("outside [V2 6004]");
    expect(health).toContain(">5.3<");
    expect(health).not.toContain("fuera de");
    expect(row(2.1, null, excursion("performance", "[V2 6013]"))).toContain("outside the comfort zone [V2 6013]");
    expect(row(2.1, null, excursion("target", "[V2 6003]"))).toContain("outside [V2 6003]");
    // El nombre del parámetro es del backend: no se toca.
    expect(health).toContain("NOMBRE-DEL-BACKEND");
    expect(row(2.1)).toContain("limit ≤ 3.0 mmHg ([V2 6004])");
  });

  it("el tablero: las píldoras y la baldosa sin lectura", () => {
    const reading: HabitatReading = {
      module: "hab",
      parameter: "o2",
      value: 150,
      unit: "mm[Hg]",
      effective: "2026-11-08T00:00:00+00:00",
      source: "simulado",
      evidence_context: "",
    };
    const html = renderToStaticMarkup(
      createElement(HabitatBoard, {
        habitat: { active: [], excursions: [{ ...excursion("health", "REQ"), module: "hab" }] },
        crew: { crew: [], correlation: { hypotheses: [{}, {}] } } as unknown as CrewOverview,
        specs: [
          { key: "cabin-ppco2", display: "PRIMERO", unit: "mm[Hg]" },
          { key: "o2", display: "SEGUNDO", unit: "mm[Hg]" },
        ],
        cabinLatest: [reading],
        measured: ["hab"],
        moduleName: (key: string) => key,
      }),
    );
    expect(html).toContain('aria-label="Crew and habitat at a glance"');
    expect(html).toContain('System hypotheses</span> <span class="num">2</span>');
    expect(html).toContain("limit excursions in the window");
    expect(html).toMatch(/PRIMERO[^]*?no data/);
    expect(html).not.toMatch(/Hipótesis|salidas del límite|sin dato/);
  });

  it("dónde señala una hipótesis y quién estaba allí", () => {
    const item = {
      excursion: excursion("health", "[V2 6004]"),
      location: { present: ["crew-01"], elsewhere: ["crew-02"], undeclared: ["crew-03"] },
    } as unknown as CrewHypothesis;
    const html = renderToStaticMarkup(createElement(HypothesisPlaceLine, { item, moduleName: (key: string) => key }));
    expect(html).toContain("Measured in:");
    expect(html).toContain("were there");
    expect(html).toContain("in another module");
    expect(html).toContain("no declared location");
    expect(html).not.toMatch(/Medida en|estaban allí|en otro módulo/);
  });

  it("la revisión de una hipótesis: los mandos y lo que queda tras confirmarla", () => {
    const hypothesis = {
      excursion: excursion("health", "[V2 6004]"),
      review: {
        decision: "confirmed",
        decided_by: "CMO",
        reason: "MOTIVO-ESCRITO",
        recovery: { habitat_within_limit: true, still_affected: ["crew-02"] },
      },
    } as unknown as CrewHypothesis;
    const html = renderToStaticMarkup(createElement(HypothesisReview, { hypothesis, operator: "CMO", onReviewed: () => undefined }));
    expect(html).toContain("Confirmed");
    expect(html).toContain("by CMO: MOTIVO-ESCRITO");
    expect(html).toContain("habitat back within limit");
    expect(html).toContain("still off nominal: crew-02");
    expect(html).toContain('aria-label="Reason for the review"');
    expect(html).toContain(">Confirm<");
    expect(html).toContain(">Discard<");
    expect(html).not.toMatch(/Confirmada|Descartar|hábitat|siguen fuera/);
  });

  it("las anclas de módulo: la lista, el formulario y la base del backend tal cual", () => {
    const anchors = {
      anchors: [
        { anchor_id: "ancla-1", module: "nodo", display: "MODULO-DEL-BACKEND", since: "2026-11-01T10:00:00+00:00", ledger_index: 7 },
      ],
      basis: "BASE-DEL-BACKEND",
    } as unknown as LocationAnchors;
    const view = (given: LocationAnchors) =>
      renderToStaticMarkup(
        createElement(LocationAnchorsView, {
          anchors: given,
          modules: null,
          met: (iso: string) => `MET ${iso.slice(0, 10)}`,
          operator: "CMO",
          form: EMPTY_ANCHOR_FORM,
          onForm: () => undefined,
          since: "2026-11-02T00:00:00+00:00",
          onDeclare: () => undefined,
          error: null,
        }),
      );
    const html = view(anchors);
    expect(html).toContain('aria-label="Module anchors"');
    expect(html).toContain("ledger entry");
    expect(html).toContain("Declare anchor");
    expect(html).toContain("signed by CMO");
    expect(html).toContain('placeholder="anchor identifier"');
    expect(html).toContain("BASE-DEL-BACKEND");
    expect(html).toContain("MODULO-DEL-BACKEND");
    expect(html).not.toMatch(/Anclas de módulo|asiento|Declarar ancla|firma/);
    expect(view({ ...anchors, anchors: [] })).toContain("No anchor declared");
  });

  it("de dónde sale una ubicación: declarada o estimada, con su antigüedad", () => {
    const source = (location: { source: string; last_seen?: string | null }) =>
      renderToStaticMarkup(
        createElement(LocationSource, {
          location: location as Parameters<typeof LocationSource>[0]["location"],
          state: "known" as Parameters<typeof LocationSource>[0]["state"],
          reference: "2026-11-08T00:30:00+00:00",
        }),
      );
    expect(source({ source: "console" })).toContain("declared");
    expect(source({ source: "anchors", last_seen: null })).toContain("estimated");
    const aged = source({ source: "anchors", last_seen: "2026-11-08T00:00:00+00:00" });
    expect(aged).toMatch(/estimated · .+ ago/);
    expect(aged).not.toMatch(/estimada|hace/);
  });

  it("un límite que depende de la humedad lo dice en inglés, con su figura", () => {
    const text = healthRange({
      unit: "Cel",
      limits: [
        {
          low: 18,
          high: 27,
          requirement: "[V2 6012]",
          kind: "health",
          averaging_minutes: 60,
          figure: { name: "Figure 6.2-2", vertices: [[18, 25]] },
        },
      ],
    } as unknown as HabitatParameter);
    expect(text).toContain("depending on the simultaneous humidity ([V2 6012], Figure 6.2-2:");
    expect(text).not.toContain("según");
  });
});
