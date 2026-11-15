import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, taggedPictogram, textLines } from "../advisor/visibleText";
import type { HabitatRadiation as Radiation } from "../lib/api";
import { HabitatRadiation } from "./HabitatRadiation";

/**
 * La radiación en el panel del hábitat (§5.37.4): la última tasa de dosis de cada dosímetro y el
 * evento solar vigente, con de dónde sale cada cifra. Se muestra y no se evalúa: ningún color de
 * aviso; el módulo sin declarar y lo que falta de DONKI, en cian con su anillo (dato ausente).
 * Toda frase sale del backend.
 */

const met = (iso: string) => `MET ${iso.slice(11, 16)}`;
const render = (radiation: Radiation) =>
  renderToStaticMarkup(createElement(HabitatRadiation, { radiation, met }));

const freshness = (state: "fresh" | "stale" | "missing") => ({
  source: "space-weather",
  state,
  display: { fresh: "al día", stale: "caducado", missing: "sin dato" }[state],
  is_current: state === "fresh",
  age_seconds: state === "missing" ? null : 60,
  stale_after_seconds: 21600,
  stale_after_display: "6 h",
});

const given = (overrides: Partial<Radiation> = {}): Radiation => ({
  display: "Radiación",
  module: null,
  module_text: "módulo sin declarar: texto del backend",
  shielding: "Sin factores de blindaje: texto del backend.",
  evaluated: false,
  note: "Se muestra y no se evalúa aquí: texto del backend.",
  dose_rate: {
    key: "absorbed-dose-rate",
    display: "Tasa de dosis absorbida",
    basis: "la última lectura de cada tripulante",
    readings: [
      {
        subject: "crew-01", value: 14.2, decimals: 1, unit: "uGy/h", effective: "2026-12-01T01:00:00+00:00",
        source: "dosimeter-a", device: null, evidence_context: "simulated",
        observation_type: "measured", origin_text: "lectura del dosímetro de crew-01 (fuente «dosimeter-a»)",
        module: null,
      },
    ],
    missing_text: null,
  },
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
  summary: "resumen",
  ...overrides,
});

describe("<HabitatRadiation>", () => {
  it("cada cifra dice de quién es el dosímetro, su fuente y su hora, sin color de aviso", () => {
    const html = render(given());
    expect(html).toMatch(taggedPictogram("h3", "trefoil", "Radiación"));
    expect(html).toMatch(markedHtml("trefoil", "Tasa de dosis absorbida"));
    const lines = textLines(html);
    expect(lines.join(" ")).toContain("crew-01 14,2 µGy/h");
    expect(lines.join(" ")).toContain("MET 01:00 lectura del dosímetro de crew-01 (fuente «dosimeter-a»)");
    expect(lines.join(" ")).toContain("MET 01:00");
    for (const color of ["c-red", "c-yellow", "c-blue"]) expect(html).not.toContain(color);
  });

  it("el módulo sin declarar es un dato ausente, y el blindaje y la nota los dice el backend", () => {
    const html = render(given());
    expect(html).toMatch(markedHtml("ring-dotted", "módulo sin declarar: texto del backend", "cyan"));
    expect(textLines(html)).toContain("Sin factores de blindaje: texto del backend.");
    expect(textLines(html)).toContain("Se muestra y no se evalúa aquí: texto del backend.");
  });

  it("el evento vigente va con la frase del backend, su ficha y la fuente con su edad", () => {
    const html = render(given());
    expect(html).toMatch(markedHtml("ridge-radiation", "Evento solar vigente"));
    expect(textLines(html).join(" ")).toContain("SEP SEP-HOY, del 2026-12-01 00:00 UTC, según NASA DONKI.");
    expect(html).toContain('href="https://example.invalid/sep"');
    expect(textLines(html).join(" ")).toContain("NASA DONKI, eventos de partículas solares (SEP) · hace 4 min");
    expect(html).not.toContain("c-cyan\"><svg data-pictogram=\"ring-dotted\"></svg>hace");
  });

  it("sin DONKI, o con su dato caducado, se dice en cian; sin lecturas, también", () => {
    const missing = given({
      dose_rate: { ...given().dose_rate, readings: [], missing_text: "Ninguna lectura de tasa de dosis registrada." },
      solar_event: {
        ...given().solar_event, state: "unavailable", text: "Sin datos de NASA DONKI.", event: null,
        data_age: null, data_age_seconds: null, freshness: freshness("missing"),
      },
    });
    const html = render(missing);
    expect(html).toMatch(markedHtml("ring-dotted", "Ninguna lectura de tasa de dosis registrada.", "cyan"));
    expect(html).toMatch(markedHtml("ring-dotted", "Sin datos de NASA DONKI.", "cyan"));

    const stale = render(given({ solar_event: { ...given().solar_event, freshness: freshness("stale") } }));
    expect(stale).toMatch(markedHtml("ring-dotted", "hace 4 min (caducado)", "cyan"));
  });

  it("sin red, la instantánea de DONKI: su edad en cian con lo que es, y el último SEP con su fecha real (2026-11-04)", () => {
    const snapshot = render(given({
      solar_event: {
        ...given().solar_event,
        state: "unavailable",
        text: "Los datos de NASA DONKI que hay están caducados: texto del backend.",
        event: null,
        data_age: "instantánea de DONKI del 2026-11-04, no en vivo (hace 10 d)",
        freshness: freshness("stale"),
        latest_recorded: {
          event_id: "SEP-REAL", event_type: "SEP", time: "2026-05-02T08:00:00+00:00",
          link: "https://example.invalid/sep-real",
          text: "Último evento de partículas solares en esos datos de NASA DONKI: texto del backend.",
        },
      },
    }));
    expect(snapshot).toMatch(markedHtml("ring-dotted", "Los datos de NASA DONKI que hay están caducados: texto del backend.", "cyan"));
    expect(snapshot).toMatch(
      markedHtml("ring-dotted", "instantánea de DONKI del 2026-11-04, no en vivo (hace 10 d) (caducado)", "cyan"),
    );
    expect(snapshot).toContain("Último evento de partículas solares en esos datos de NASA DONKI: texto del backend.");
    expect(snapshot).toContain('href="https://example.invalid/sep-real"');
    // Un backend anterior no lo da: no se pinta nada.
    expect(render(given())).not.toContain("data-solar-latest");
  });

  it("quien tiene tasa de dosis que el estado no lee por su tipo sale con su nombre, su frase y la marca de «no disponible» (§5.39.11)", () => {
    const html = render(
      given({
        dose_rate: {
          ...given().dose_rate,
          set_aside_display: "APARTADAS-DEL-BACKEND",
          set_aside: [
            { subject: "crew-02", counts: { inferred: 5 }, shown: false, text: "SIN-MEDIDA-DEL-BACKEND" },
            { subject: "crew-01", counts: { inferred: 1, predicted: 1 }, shown: true, text: "CON-MEDIDA-DEL-BACKEND" },
          ],
          set_aside_rule: "REGLA-DEL-BACKEND",
        },
      }),
    );
    const block = html.split("<div data-dose-set-aside")[1]!.split("</div>")[0]!;
    expect(textLines(block)).toContain("APARTADAS-DEL-BACKEND");
    // Gris con el círculo tachado: el dato existe (no es cian) y no avisa de nada (no es amarillo).
    expect(block).toMatch(markedHtml("slash-circle", "SIN-MEDIDA-DEL-BACKEND", "gray"));
    expect(block).toMatch(markedHtml("slash-circle", "CON-MEDIDA-DEL-BACKEND", "gray"));
    expect(block).toContain('data-dose-set-aside-shown="no"');
    expect(block).toContain('data-dose-set-aside-shown="yes"');
    // Con el nombre delante, como en la lista de arriba, y la regla del backend debajo.
    expect(textLines(block).join(" ")).toContain("crew-02 SIN-MEDIDA-DEL-BACKEND");
    expect(textLines(block)).toContain("REGLA-DEL-BACKEND");
    for (const color of ["c-red", "c-yellow", "c-blue", "c-cyan"]) expect(block).not.toContain(color);
    // Y la lista de arriba sigue siendo la de las medidas: crew-02 no está en ella.
    expect(html.split("<div data-dose-set-aside")[0]).not.toContain("crew-02");
  });

  it("sin nada apartado no pinta el bloque, ni con un backend que no lo da", () => {
    expect(render(given())).not.toContain("data-dose-set-aside");
    const empty = render(given({ dose_rate: { ...given().dose_rate, set_aside: [], set_aside_rule: null } }));
    expect(empty).not.toContain("data-dose-set-aside");
  });

  it("no redacta ninguna frase de radiación", () => {
    const source = readFileSync(fileURLToPath(new URL("./HabitatRadiation.tsx", import.meta.url)), "utf-8");
    for (const field of [
      "radiation.module_text", "radiation.shielding", "radiation.note", "solar.text", "solar.basis", "item.origin_text",
      "dose.missing_text", "dose.set_aside_display", "item.text", "dose.set_aside_rule",
    ]) {
      expect(source).toContain(field);
    }
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "");
    for (const written of ["sin declarar", "blindaje", "DONKI", "no se evalúa", "inferida", "medida", "apartada"]) {
      expect(code).not.toContain(written);
    }
  });
});
