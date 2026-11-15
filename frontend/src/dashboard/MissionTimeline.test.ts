import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textLines } from "../advisor/visibleText";
import type { CrewStatus, EphemerisCoverage, MissionEvent, MissionProfile, ShiftBasis } from "../lib/api";
import { UNKNOWN_MARK } from "../lib/marks";
import { MissionTimeline, ShiftBasisView } from "./MissionTimeline";
import { eventPictogram, gravityPictogram, phasePictogram } from "./missionPictograms";

/*
 * La cabecera de la linea temporal MUESTRA la gravedad que da el backend (`core/mission.py`).
 * Con datos posvuelo decia «posvuelo y recuperación» junto a «microgravedad»: pintaba la de
 * configuracion, que no sigue a la fase. Ahora pinta `gravity_display` tal cual; se comprueba
 * pintando el panel con un estado de ejemplo y leyendo su fuente. Y cada fase, la gravedad y
 * cada evento declarado llevan su pictograma junto a la palabra del backend (`missionPictograms.ts`).
 */

const PHASES = [
  { key: "preflight", display: "prevuelo" },
  { key: "adaptation", display: "adaptación" },
  { key: "stable", display: "fase estable" },
  { key: "return", display: "preparación del regreso" },
  { key: "postflight", display: "posvuelo y recuperación" },
];

const status = (mission: Partial<CrewStatus["mission"]>): CrewStatus =>
  ({
    subject: "crew-01",
    followups: [],
    mission: {
      // Fecha UTC, como la da el backend: es el origen del tiempo de mision de los eventos.
      start: "2026-11-01",
      mode: "simulation",
      sources: [],
      mission_day: 40,
      duration_days: 180,
      phase: "stable",
      phase_display: "fase estable",
      phases: PHASES,
      gravity_regime: "microgravedad",
      gravity_now: "microgravedad",
      gravity_mission: "microgravedad",
      gravity_mission_label: "rótulo del backend",
      gravity_display: "frase de la gravedad según el backend",
      phase_basis: "base de las fases según el backend",
      events: [],
      profile: null,
      ...mission,
    },
  }) as unknown as CrewStatus;

const render = (value: CrewStatus) =>
  renderToStaticMarkup(createElement(MissionTimeline, { status: value }));

describe("línea temporal: la gravedad", () => {
  it("en posvuelo pinta la frase del backend, no la gravedad de configuración sola", () => {
    const html = render(
      status({
        mission_day: 185.5,
        phase: "postflight",
        phase_display: "posvuelo y recuperación",
        gravity_now: "en Tierra (gravedad terrestre)",
        gravity_display:
          "en Tierra (gravedad terrestre); gravedad de la misión, declarada por configuración: microgravedad",
      }),
    );
    expect(html).toContain(
      "en Tierra (gravedad terrestre); gravedad de la misión, declarada por configuración: microgravedad",
    );
    // Lo de configuración solo aparece dentro de esa frase, no suelto junto a la fase.
    expect(html.split("microgravedad").length - 1).toBe(1);
  });

  it("fuera del posvuelo pinta la misma frase del backend, sola: es texto libre de configuracion", () => {
    const html = render(status({ gravity_display: "microgravedad" }));
    expect(html).toContain("· microgravedad · intervenciones");
    // Ningun dibujo que pueda contradecir a esa frase (podria decir la gravedad de una superficie).
    expect(html).not.toMatch(/<\/svg>microgravedad/);
    expect(html).not.toContain('data-pictogram="ball-on-line"');
  });

  it("la gravedad del momento solo se dibuja cuando el backend la fija: en Tierra tras el vuelo", () => {
    expect(gravityPictogram("postflight")).toBe("ball-on-line");
    for (const phase of ["preflight", "adaptation", "stable", "return", "otra"]) {
      expect(gravityPictogram(phase), phase).toBeNull();
    }
    const html = render(
      status({ phase: "postflight", gravity_display: "frase del backend sobre la Tierra" }),
    );
    expect(html).toMatch(
      /<span class="mark"><svg [^>]*data-pictogram="ball-on-line"[^>]*>.*?<\/svg>frase del backend sobre la Tierra<\/span> · intervenciones/,
    );
    expect(textLines(html).some((line) => line.includes("frase del backend sobre la Tierra · intervenciones"))).toBe(true);
  });

  it("no compone la gravedad: ni lee la de configuración ni escribe la de Tierra", () => {
    const source = readFileSync(
      fileURLToPath(new URL("./MissionTimeline.tsx", import.meta.url)),
      "utf8",
    );
    const composed_texts = ["mission.gravity_regime", "gravity_now", "gravity_mission", "terrestre"];
    for (const composed of composed_texts) {
      expect(source, composed).not.toContain(composed);
    }
    expect(source).toContain("mission.gravity_display");
  });
});

describe("línea temporal: fases y eventos con su pictograma", () => {
  it("cada fase lleva un dibujo distinto junto a su palabra, y la actual ademas el disco lleno", () => {
    const html = render(status({}));
    const drawn = new Set<string>();
    for (const phase of PHASES) {
      const pictogram = phasePictogram(phase.key);
      expect(pictogram, phase.key).not.toBe(UNKNOWN_MARK.pictogram);
      drawn.add(String(pictogram));
      expect(html).toMatch(
        new RegExp(`<span class="mark"><svg [^>]*data-pictogram="${pictogram}"[^>]*>.*?</svg>${phase.display}</span>`),
      );
    }
    expect(drawn.size).toBe(PHASES.length);
    // La actual: el anillo con punto de «elegido / actual» delante del nombre con su dibujo, y
    // `aria-current`. No el disco lleno, que es «medido».
    expect(html).toMatch(
      /<li aria-current="step"><span class="mark"><svg [^>]*data-pictogram="ring-dot"[^>]*>.*?<\/svg><span class="mark"><svg [^>]*data-pictogram="bubble-level"/,
    );
    expect(html.match(/data-pictogram="ring-dot"/g)).toHaveLength(1);
    expect(html).not.toContain('data-pictogram="dot-filled"');
    expect(html).not.toContain("●");
    // Una fase que la interfaz no conoce va con su palabra y el dibujo de «desconocido».
    expect(phasePictogram("orbit-insertion")).toBe(UNKNOWN_MARK.pictogram);
  });

  it("cada tipo de evento declarado lleva su dibujo junto a su rotulo", () => {
    const event = (kind: MissionEvent["kind"], index: number): MissionEvent => ({
      kind,
      start: "2026-11-10T08:00:00+00:00",
      end: "2026-11-10T14:00:00+00:00",
      label: `EVENTO-${kind}`,
      declared_by: "CDR",
      ledger_index: index,
      ...(kind === "location" ? { module: "node-2" } : {}),
    });
    const html = render(
      status({ events: [event("eva", 1), event("workload", 2), event("location", 3), event("shift", 4)] }),
    );
    expect(html).toMatch(/data-pictogram="helmet"[^>]*>.*?<\/svg>EVA<\/span>: EVENTO-eva/);
    expect(html).toMatch(/data-pictogram="briefcase"[^>]*>.*?<\/svg>bloque de trabajo<\/span>: EVENTO-workload/);
    expect(html).toMatch(/data-pictogram="pin"[^>]*>.*?<\/svg>ubicación<\/span>: EVENTO-location/);
    expect(html).toMatch(/data-pictogram="crescent-arrow"[^>]*>.*?<\/svg>cambio de turno<\/span>: EVENTO-shift/);
    const kinds = ["eva", "workload", "location", "shift"].map(eventPictogram);
    expect(new Set(kinds).size).toBe(4);
    expect(kinds).not.toContain(UNKNOWN_MARK.pictogram);
    expect(eventPictogram("maintenance")).toBe(UNKNOWN_MARK.pictogram);
  });
});

describe("línea temporal: la cobertura de efemérides (§5.37.18)", () => {
  const coverage: EphemerisCoverage = {
    state: "none",
    target: "000",
    observer: "399",
    start: "2026-11-01",
    end: "2026-11-02",
    days: 2,
    covered_days: 0,
    missing_days: 2,
    covered: [],
    missing: [{ start: "2026-11-01", end: "2026-11-02", days: 2 }],
    day: { date: "2026-11-02", in_mission: true, covered: false },
    text: "FRASE-DE-LA-COBERTURA",
    how_to_preload: "COMO-PRECARGAR",
    note: "NOTA-DE-LA-COBERTURA",
    citations: [],
  };
  const profile: MissionProfile = {
    id: "leo",
    known: true,
    display: "PERFIL-DEL-BACKEND",
    note: "nota",
    declared: "declarado",
    unknown_text: null,
    ephemeris: null,
    aspects: [],
    pages_read: [],
  };

  it("la pinta después del perfil, y también sin perfil", () => {
    const withProfile = render(status({ profile, ephemeris_coverage: coverage }));
    expect(withProfile).toContain("FRASE-DE-LA-COBERTURA");
    expect(withProfile.indexOf("PERFIL-DEL-BACKEND")).toBeLessThan(withProfile.indexOf("FRASE-DE-LA-COBERTURA"));
    const alone = render(status({ ephemeris_coverage: coverage }));
    for (const text of ["FRASE-DE-LA-COBERTURA", "COMO-PRECARGAR", "NOTA-DE-LA-COBERTURA"]) {
      expect(alone).toContain(text);
    }
  });

  it("un backend sin el bloque no pinta nada de ella", () => {
    expect(render(status({}))).not.toContain("Efemérides en caché");
    expect(render(status({ ephemeris_coverage: null }))).not.toContain("Efemérides en caché");
  });
});

describe("línea temporal: qué es un cambio de turno (decimoctava ronda, U4)", () => {
  it("enseña la distinción y la fuente tal cual las da el backend", () => {
    const basis: ShiftBasis = {
      kind: "shift",
      display: "Cambio de turno o de horario de sueño",
      distinction: "FRASE-DE-LA-DISTINCION",
      source_says: "FRASE-DE-LA-FUENTE",
      source: { id: "flynn-evans-2016-circadian-iss", title: "TITULO-DE-LA-FICHA", url: "https://example.org/x", relevance: null },
    };
    const html = renderToStaticMarkup(createElement(ShiftBasisView, { basis }));
    expect(html).toContain("<p>FRASE-DE-LA-DISTINCION</p>");
    expect(html).toContain('FRASE-DE-LA-FUENTE <a href="https://example.org/x" target="_blank" rel="noreferrer">TITULO-DE-LA-FICHA</a>');
    const without = renderToStaticMarkup(createElement(ShiftBasisView, { basis: { ...basis, source: { ...basis.source, url: null } } }));
    expect(without).not.toContain("<a ");
    expect(without).toContain("FRASE-DE-LA-FUENTE TITULO-DE-LA-FICHA");
  });
});

describe("línea temporal: el tablero", () => {
  it("el día de misión sobre la duración en el medidor neutro, y los recuentos en píldoras", () => {
    const html = render(status({ events: [] }));
    expect(html).toContain('role="meter" aria-label="Día de misión sobre la duración prevista" aria-valuemin="0" aria-valuemax="180" aria-valuenow="40"');
    expect(html).toMatch(/en seguimiento<\/span> <span class="num">0<\/span>/);
    expect(html).toMatch(/eventos declarados<\/span> <span class="num">0<\/span>/);
  });

  it("sin duración prevista no hay escala: no se dibuja el medidor", () => {
    expect(render(status({ duration_days: 0 }))).not.toContain('role="meter"');
  });
});
