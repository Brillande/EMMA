import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, spanWithPictogram, textNodes } from "../advisor/visibleText";
import { modulePictogram } from "../habitat/pictograms";
import type { CrewLocation, CrewStatus, LocationState } from "../lib/api";
import { formatMet, missionElapsedSeconds } from "../lib/format";
import { OBSERVATION_TYPES, contextLabel } from "../lib/provenance";
import { uiPictogram } from "../lib/uiMarks";
import { ModuleLine } from "./HomeBoard";

/**
 * La «Sububicación» de «Inicio» (2026-11-09: decía «Sin módulo: el backend no lo da»; 2026-11-10:
 * real, ya no simulada). Pinta el módulo de `mission.location` del estado con su dibujo y el nombre
 * del backend, el tramo en tiempo de misión y quién la puso: «declarada» (la consola) o «estimada ·
 * hace N min» (las anclas de módulo), con la antigüedad contada desde la referencia del estado. Sin
 * ubicación, la marca de `location_state` (gris si no se puede medir, cian si falta o caducó, la
 * interrogación si dos módulos compiten) con el texto del backend, sin redactar uno propio.
 */

const START = "2026-11-01";
const REFERENCE = "2026-11-01T10:00:00+00:00";

function mission(
  location: CrewLocation | null,
  state: LocationState,
  missing: string | null = null,
): CrewStatus["mission"] {
  return {
    start: START,
    location,
    location_state: state,
    location_missing_text: missing,
    location_basis: "de dónde sale: texto del backend",
  } as CrewStatus["mission"];
}

const lab = (source: CrewLocation["source"], lastSeen: string | null = null): CrewLocation => ({
  module: "laboratorio",
  display: "Laboratorio (backend)",
  start: "2026-11-01T00:00:00+00:00",
  end: "2026-12-01T00:00:00+00:00",
  ledger_index: 7,
  source,
  last_seen: lastSeen,
});

const render = (value: CrewStatus["mission"]) =>
  renderToStaticMarkup(createElement(ModuleLine, { mission: value, reference: REFERENCE }));
const met = (iso: string) => formatMet(missionElapsedSeconds(START, new Date(iso)));
const ESTIMATED = OBSERVATION_TYPES.inferred.pictogram;

describe("Sububicación", () => {
  it("declared: dibujo del módulo, nombre del backend, tramo y «declarada», sin color", () => {
    const html = render(mission(lab("console"), "declared"));
    expect(html).toMatch(spanWithPictogram("mark", modulePictogram("laboratorio"), "Laboratorio (backend)"));
    expect(html).toMatch(markedHtml(uiPictogram("declare"), "declarada"));
    const text = textNodes(html).join(" ");
    expect(text).toContain(met("2026-11-01T00:00:00+00:00"));
    expect(text).toContain(met("2026-12-01T00:00:00+00:00"));
    expect(text).not.toContain("estimada");
    expect(html).not.toContain("c-cyan");
  });

  it("estimated: «estimada · hace N min» con el dibujo de lo inferido; nunca pasa por declarada", () => {
    const html = render(mission(lab("anchors", "2026-11-01T09:53:00+00:00"), "estimated"));
    expect(html).toMatch(spanWithPictogram("mark", modulePictogram("laboratorio"), "Laboratorio (backend)"));
    expect(html).toMatch(markedHtml(ESTIMATED, "estimada · hace 7 min"));
    expect(html).not.toContain(">declarada<");
    expect(html).not.toContain("c-cyan");
  });

  it("estimated sin lectura conocida: «estimada», sin inventar una antigüedad", () => {
    const html = render(mission(lab("anchors"), "estimated"));
    expect(html).toMatch(markedHtml(ESTIMATED, "estimada"));
    expect(html).not.toContain("hace");
  });

  it("stale con módulo: cian y cursiva de dato caducado, con su antigüedad", () => {
    const html = render(mission(lab("anchors", "2026-11-01T07:30:00+00:00"), "stale"));
    expect(html).toMatch(markedHtml("ring-dotted", "estimada · hace 2,5 h", "cyan", "stale"));
    expect(html).toMatch(spanWithPictogram("mark stale", modulePictogram("laboratorio"), "Laboratorio (backend)"));
  });

  it("stale y missing sin módulo: la marca de lo que falta (cian) con el texto del backend", () => {
    for (const state of ["stale", "missing"] as const) {
      const html = render(mission(null, state, `sin ubicación (${state}, backend)`));
      expect(html).toMatch(markedHtml("ring-dotted", `sin ubicación (${state}, backend)`, "cyan"));
      expect(html).not.toContain(modulePictogram("laboratorio"));
    }
  });

  it("unavailable (sin anclas declaradas): gris «no disponible», no cian", () => {
    const html = render(mission(null, "unavailable", "sin anclas: no se puede medir (backend)"));
    expect(html).toMatch(markedHtml("slash-circle", "sin anclas: no se puede medir (backend)", "gray"));
    expect(html).not.toContain("c-cyan");
  });

  it("ambiguous (dos módulos compiten): la interrogación sin color, no se fuerza un módulo", () => {
    const html = render(mission(null, "ambiguous", "entre módulos (backend)"));
    expect(html).toMatch(markedHtml("question", "entre módulos (backend)"));
    expect(html).not.toContain("c-cyan");
    expect(html).not.toContain("c-gray");
    expect(html).not.toContain(modulePictogram("laboratorio"));
  });

  it("una fuente que la interfaz no conoce (un backend anterior con `simulator`): ni estimada ni declarada", () => {
    const legacy = { ...lab("anchors"), source: "simulator" } as unknown as CrewLocation;
    const html = render(mission(legacy, "declared"));
    expect(html).toMatch(markedHtml("dot-small", "simulator", "text"));
    expect(html).not.toContain("estimada");
    expect(html).not.toContain(">declarada<");
  });

  it("nada de lo simulado: ni la palabra ni la marca", () => {
    for (const html of [render(mission(lab("console"), "declared")), render(mission(lab("anchors"), "estimated"))]) {
      expect(textNodes(html).join(" ")).not.toContain(contextLabel("simulated"));
      expect(html).not.toContain("mode-tag");
    }
  });
});
