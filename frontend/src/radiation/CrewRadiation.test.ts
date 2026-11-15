import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, taggedPictogram, textLines, thSign } from "../advisor/visibleText";
import type { CrewRadiation as View, CrewRadiationMember } from "../lib/api";
import { CrewRadiationView } from "./CrewRadiation";

/**
 * La tripulación ante un evento solar (§5.38.8): por tripulante, la ubicación declarada y la dosis
 * de misión y de carrera de su estado, con su rótulo de tipo; el evento y el refugio, una vez. Se
 * muestra y no se evalúa: ningún color de aviso; lo que falta, en cian con su anillo. Toda frase y
 * toda cifra salen del backend; las cifras, por `format.ts`.
 */

const met = (iso: string) => `MET ${iso.slice(11, 16)}`;
const render = (view: View) => renderToStaticMarkup(createElement(CrewRadiationView, { view, met }));

const freshness = (state: "fresh" | "stale" | "missing") => ({
  source: "space-weather",
  state,
  display: { fresh: "al día", stale: "caducado", missing: "sin dato" }[state],
  is_current: state === "fresh",
  age_seconds: state === "missing" ? null : 60,
  stale_after_seconds: 21600,
  stale_after_display: "6 h",
});

const located: CrewRadiationMember = {
  subject: "crew-01",
  location: {
    module: "laboratorio", display: "Laboratorio", start: "2026-12-01T00:00:00+00:00",
    end: "2026-12-02T00:00:00+00:00", ledger_index: 7, source: "console", last_seen: null,
  },
  location_state: "declared",
  location_missing_text: null,
  mission: {
    value_msv: 1.2345, absorbed_mgy: 0.5, quality_factor: 2.38, hours_covered: 5,
    observation_type: "inferred", model_version: "dosis-mision@1", basis: "integral: texto del backend",
  },
  mission_missing_text: null,
  career: {
    value_msv: 121.23, prior_msv: 120, fraction: 0.2, basis: "previa más misión: texto del backend",
    limit_msv: 600, limit_source: "NASA-STD-3001 [V1 4030]", observation_type: "inferred",
  },
  state_missing_text: null,
};

const unknown: CrewRadiationMember = {
  subject: "crew-02",
  location: null,
  location_state: "missing",
  location_missing_text: "ubicación sin declarar: texto del backend",
  mission: null,
  mission_missing_text: "sin dosis de esta misión: texto del backend",
  career: { value_msv: null, basis: "sin dosis previa declarada: texto del backend", limit_msv: 600, limit_source: "NASA-STD-3001 [V1 4030]" },
  state_missing_text: null,
};

const stateless: CrewRadiationMember = {
  subject: "crew-03",
  location: null,
  location_missing_text: "ubicación sin declarar: texto del backend",
  mission: null,
  mission_missing_text: null,
  career: null,
  state_missing_text: "sin dosis: sin estado analizable, texto del backend",
};

const given = (overrides: Partial<View> = {}): View => ({
  display: "La tripulación ante un evento solar",
  basis: "por tripulante: texto del backend",
  reference_time: "2026-12-01T05:00:00+00:00",
  solar_event: {
    display: "Evento solar vigente",
    state: "active",
    text: "SEP SEP-HOY, del 2026-12-01 00:00 UTC, según NASA DONKI.",
    event: { event_id: "SEP-HOY", event_type: "SEP", time: "2026-12-01T00:00:00+00:00", link: "https://example.invalid/sep" },
    source: "NASA DONKI, eventos de partículas solares (SEP)",
    data_age: "hace 4 min",
    data_age_seconds: 240,
    freshness: freshness("fresh"),
    basis: "el mismo que da la escala aguda",
  },
  shelter: {
    detected_at: "2026-12-01T00:00:00+00:00",
    shelter_ready_by: "2026-12-01T01:00:00+00:00",
    max_stay_until: "2026-12-02T00:00:00+00:00",
    elapsed_minutes: 300,
    elapsed_note: null,
    basis: "procedimiento de Orion: texto del backend",
    source: { title: "Orion", source: "NASA, Orion radiation protection", url: "https://example.invalid/orion" },
  },
  shelter_missing_text: null,
  location_basis: "la ubicación declarada: texto del backend",
  crew: [located, unknown, stateless],
  shielding: "Sin factores de blindaje: texto del backend.",
  evaluated: false,
  note: "Se muestra y no se evalúa: texto del backend.",
  ...overrides,
});

describe("<CrewRadiationView>", () => {
  it("una fila por tripulante: dónde está declarado y su dosis con su tipo, sin color de aviso", () => {
    const html = render(given());
    expect(html).toMatch(taggedPictogram("h3", "trefoil", "La tripulación ante un evento solar"));
    for (const [pictogram, word] of <[string, string][]>[
      ["person", "Tripulante"], ["house", "Ubicación"], ["trefoil", "Esta misión"], ["bar-capped", "Carrera"],
    ]) {
      expect(html).toMatch(thSign(pictogram, word, " scope=\"col\""));
    }
    const text = textLines(html).join(" ");
    expect(text).toContain("Laboratorio (de MET 00:00 a MET 00:00)");
    // Cifras por `format.ts`, con los decimales de la escala del estado.
    expect(text).toContain("1,23 mSv");
    expect(text).toContain("121,2 de 600 mSv");
    // El medidor neutro del estado hasta el límite de carrera, con su fuente.
    expect(html).toContain('aria-label="Carrera de crew-01: dosis sobre el límite de carrera"');
    expect(text).toContain("(NASA-STD-3001 [V1 4030])");
    expect(html.match(/data-pictogram="dot-half"/g)?.length).toBe(2);
    expect(text).toContain("INFERIDO");
    for (const color of ["c-red", "c-yellow", "c-blue"]) expect(html).not.toContain(color);
  });

  it("lo que falta se dice en cian, con la frase del backend", () => {
    const html = render(given());
    for (const missing of [
      "ubicación sin declarar: texto del backend",
      "sin dosis de esta misión: texto del backend",
      "sin dosis previa declarada: texto del backend",
      "sin dosis: sin estado analizable, texto del backend",
    ]) {
      expect(html).toMatch(markedHtml("ring-dotted", missing, "cyan"));
    }
  });

  it("el evento con su ficha y su fuente, y el refugio con el procedimiento y los tiempos de misión", () => {
    const html = render(given());
    expect(html).toMatch(markedHtml("ridge-radiation", "Evento solar vigente"));
    expect(html).toMatch(markedHtml("house-door", "refugio"));
    const text = textLines(html).join(" ");
    expect(text).toContain("SEP SEP-HOY, del 2026-12-01 00:00 UTC, según NASA DONKI.");
    expect(html).toContain('href="https://example.invalid/sep"');
    expect(text).toContain("NASA DONKI, eventos de partículas solares (SEP) · hace 4 min");
    expect(text).toContain("evento detectado en MET 00:00 · refugio montado antes de MET 01:00 · permanencia hasta MET 00:00");
    expect(text).toContain("procedimiento de Orion: texto del backend.");
    expect(html).toContain('href="https://example.invalid/orion"');
  });

  it("sin DONKI se dice en cian, y sin evento no hay tiempos de refugio", () => {
    const html = render(given({
      solar_event: {
        ...given().solar_event, state: "unavailable", text: "Sin datos de NASA DONKI.", event: null,
        data_age: null, data_age_seconds: null, freshness: freshness("missing"),
      },
      shelter: null,
      shelter_missing_text: "sin evento solar vigente: texto del backend",
    }));
    expect(html).toMatch(markedHtml("ring-dotted", "Sin datos de NASA DONKI.", "cyan"));
    expect(textLines(html)).toContain("sin evento solar vigente: texto del backend");
    // Con su propio término, no como parte de la frase del evento.
    expect(html).toMatch(markedHtml("house-door", "Refugio"));
    expect(html).not.toContain("montado antes");

    const stale = render(given({ solar_event: { ...given().solar_event, freshness: freshness("stale") } }));
    expect(stale).toMatch(markedHtml("ring-dotted", "hace 4 min (caducado)", "cyan"));
  });

  it("una ubicación estimada por las anclas no pasa por declarada; sin anclas, gris «no disponible»", () => {
    const estimated: CrewRadiationMember = {
      ...located,
      subject: "crew-04",
      location: {
        module: "laboratorio", display: "Laboratorio", start: "2026-12-01T04:30:00+00:00",
        end: "2026-12-01T05:00:00+00:00", ledger_index: 9, source: "anchors", last_seen: "2026-12-01T04:48:00+00:00",
      },
      location_state: "estimated",
    };
    const unmeasured: CrewRadiationMember = {
      ...unknown,
      subject: "crew-05",
      location_state: "unavailable",
      location_missing_text: "sin anclas declaradas: texto del backend",
    };
    const html = render(given({ crew: [estimated, unmeasured] }));
    // 12 min desde la última lectura de anclas hasta la referencia de la tripulación (05:00).
    expect(html).toMatch(markedHtml("dot-half", "estimada · hace 12 min"));
    expect(html).not.toContain(">declarada<");
    expect(html).toMatch(markedHtml("slash-circle", "sin anclas declaradas: texto del backend", "gray"));
  });

  it("el blindaje, la nota y las bases los dice el backend; la interfaz no redacta ninguna frase de radiación", () => {
    const lines = textLines(render(given()));
    expect(lines).toContain("Sin factores de blindaje: texto del backend.");
    expect(lines).toContain("Se muestra y no se evalúa: texto del backend.");
    expect(lines).toContain("la ubicación declarada: texto del backend.");
    const source = readFileSync(fileURLToPath(new URL("./CrewRadiation.tsx", import.meta.url)), "utf-8");
    for (const field of [
      "view.shielding", "view.note", "view.basis", "view.location_basis", "view.shelter_missing_text",
      "member.location_missing_text", "member.mission_missing_text", "member.state_missing_text", "career.basis",
      // El evento y el refugio, con las piezas que ya los dibujan (no copias).
      "<SolarEventFacts solar={solar} />", "<ShelterTimeline action={shelter} met={met} />",
    ]) {
      expect(source).toContain(field);
    }
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
    for (const written of ["sin declarar", "blindaje", "DONKI", "no se evalúa", "no se supone"]) {
      expect(code).not.toContain(written);
    }
  });
});
