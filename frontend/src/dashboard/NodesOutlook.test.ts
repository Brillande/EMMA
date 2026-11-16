import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { CrewStatus, Prediction, ProfileMatrix } from "../lib/api";
import type { CorrelationPair, Correlations } from "../lib/outlookApi";
import { type Token, cssVar, palette } from "../lib/palette";
import type { Fetched, HomeData, HomeLinks } from "./HomeBoard";
import {
  CHALLENGES,
  NodesOutlookView,
  SCENARIO_ROWS,
  aspectText,
  defaultPair,
  orderedPairs,
  pairMark,
  resourceCounts,
  scenarioRows,
  shownProfile,
} from "./NodesOutlook";
import { scatterScale as scale } from "./HomeCharts";

/**
 * La última fila de «Distancia y nodos» (lote «reservas», unidad 5, 2026-11-14). Sin DOM ni red: la
 * lógica se prueba sola y la vista se pinta con `renderToStaticMarkup` sobre lo recibido. Lo que
 * vigila: toda cifra sale del backend (dosis de carrera, retardo, recuentos, r, proyecciones), lo
 * que falta lleva su marca, nada de porcentajes inventados ni de «IA», las frases del backend van
 * tal cual y las tarjetas siguen al perfil elegido.
 */

const REFERENCE = "2026-11-14T12:00:00Z";

const matrix = {
  no_source: "EMMA no tiene fuente",
  profiles: [
    {
      id: "leo",
      display: "órbita baja",
      declared: true,
      cells: [
        { key: "comm_delay", label: "retardo", text: "Frase del retardo en órbita baja." },
        { key: "radiation_environment", label: "radiación", text: "EMMA no tiene fuente" },
        { key: "resupply", label: "reabastecimiento", text: "Frase del reabastecimiento en órbita baja." },
      ],
    },
    {
      id: "mars-transit",
      display: "tránsito a Marte",
      declared: false,
      cells: [{ key: "comm_delay", label: "retardo", text: "Frase del retardo hacia Marte." }],
    },
  ],
} as unknown as ProfileMatrix;

const prediction = (key: string, concerning: boolean, change = 1.5): Prediction =>
  ({
    key,
    display: key,
    display_es: key.toUpperCase(),
    unit: "kg",
    decimals: 1,
    observation_type: "predicted",
    horizon_weeks: 4,
    projected_change: change,
    projected_change_low: change - 1,
    projected_change_high: change + 1,
    concerning,
    basis: "Base de la proyección, del backend.",
  }) as Prediction;

const statusOf = (over: Record<string, unknown> = {}): CrewStatus =>
  ({
    subject: "crew-01",
    summary: "Resumen.",
    overall_level: "watch",
    domains: {
      radiation: { score: 0, level: "nominal", drivers: [] },
      behavioral: { score: 1, level: "watch", drivers: [] },
    },
    data: { reference_time: REFERENCE, observations: 10 },
    comms: { one_way_minutes: 3, distance_au: 0.36 },
    freshness: { comms: { state: "fresh" } },
    mission: {
      gravity_display: "Microgravedad (declarada en la configuración)",
      profile: { ephemeris: { state: "consistent" } },
      available_resources: {
        declared: [
          { key: "a", state: "available" },
          { key: "b", state: "available" },
          { key: "c", state: "unavailable" },
        ],
        undeclared_count: 9,
      },
    },
    radiation: {
      career: { value_msv: 120, limit_msv: 600, limit_source: "NASA-STD-3001", basis: "Base de carrera." },
      projection: { observation_type: "predicted", value_msv: 42.25, basis: "Base de la dosis proyectada." },
    },
    predictions: [prediction("body-weight", false), prediction("vo2-peak", true, -2)],
    forecast_checks: { checked: 5, within_margin: 4, checks: [], basis: "Retrospectiva." },
    recommendations: [{ domain: "behavioral", action: "Acción redactada por el backend.", rationale: "Motivo." }],
    ...over,
  }) as unknown as CrewStatus;

const home = (over: Partial<HomeData> = {}, status: CrewStatus = statusOf()): HomeData =>
  ({
    status,
    reference: Date.parse(REFERENCE),
    groups: [
      { hazard: "radiation", display: "radiación", domains: ["radiation"] },
      { hazard: "isolation", display: "aislamiento", domains: ["behavioral"] },
      { hazard: "distance", display: "distancia", domains: [] },
      { hazard: "gravity", display: "gravedad", domains: [] },
    ],
    matrix,
    matrixFailure: null,
    shownRoute: "leo",
    lowest: "nominal",
    ...over,
  }) as unknown as HomeData;

const pair = (over: Partial<CorrelationPair> = {}): CorrelationPair => ({
  x: { key: "sleep-duration", display_es: "Duración del sueño", unit: "h", decimals: 1 },
  y: { key: "pvt-mean-rt", display_es: "Tiempo de reacción", unit: "ms", decimals: 0 },
  theme: "sueño y desempeño",
  state: "computed",
  n: 12,
  r: 0.78,
  ci_low: 0.37,
  ci_high: 0.94,
  points: [
    { day: "2026-11-01", x: 6, y: 300 },
    { day: "2026-11-02", x: 7, y: 280 },
  ],
  simulated: false,
  text: "r = 0,78 (IC 95 %: 0,37 a 0,94; n = 12 días).",
  ...over,
});

const correlations = (pairs: CorrelationPair[] = [pair()]): Fetched<Correlations> => ({
  state: "ready",
  value: {
    subject: "crew-01",
    reference_time: REFERENCE,
    window_days: 30,
    min_days: 10,
    method: "Método del backend.",
    method_version: "pearson-daily-means-1",
    scope: "Correlación, no causa. Alcance del backend.",
    multiple: "Salvedad de varios pares.",
    pairs_basis: "Por qué estos pares.",
    simulated_text: "Series simuladas: texto del backend.",
    pairs,
  },
});

const links: HomeLinks = {
  openSection: () => undefined,
  sectionName: (key) => ({ hazards: "Peligros y alertas" })[key] ?? null,
};

const render = (props: {
  home?: HomeData;
  correlations?: Fetched<Correlations>;
  links?: HomeLinks;
  profileId?: string | null;
}) =>
  renderToStaticMarkup(
    createElement(NodesOutlookView, {
      home: props.home ?? home(),
      correlations: props.correlations ?? correlations(),
      links: props.links,
      profileId: props.profileId,
    }),
  );

describe("la lógica", () => {
  it("el perfil enseñado es el elegido o, sin elección, el de la ruta", () => {
    expect(shownProfile(home(), undefined)?.id).toBe("leo");
    expect(shownProfile(home(), "mars-transit")?.id).toBe("mars-transit");
    expect(shownProfile(home(), "nada")).toBeNull();
    expect(aspectText(shownProfile(home(), "leo"), "comm_delay")).toBe("Frase del retardo en órbita baja.");
    expect(aspectText(null, "comm_delay")).toBeNull();
  });

  it("cinco retos, cada uno con su aspecto del perfil", () => {
    expect(CHALLENGES.map((item) => item.key)).toEqual(["radiation", "isolation", "gravity", "latency", "resources"]);
    expect(new Set(CHALLENGES.map((item) => item.aspect)).size).toBe(CHALLENGES.length);
  });

  it("los recursos se cuentan sobre el vocabulario entero; sin declaraciones del backend, nada", () => {
    expect(resourceCounts(statusOf().mission.available_resources)).toEqual({
      available: 2,
      unavailable: 1,
      undeclared: 9,
      total: 12,
    });
    expect(resourceCounts(null)).toBeNull();
    expect(resourceCounts(undefined)).toBeNull();
  });

  it("el par por omisión es el primero con r; sin r, pocos días en cian y serie plana en gris", () => {
    const few = pair({ state: "insufficient", r: null });
    expect(defaultPair([few, pair()])).toBe(1);
    expect(defaultPair([few])).toBe(0);
    expect(pairMark(pair())).toBeNull();
    expect(pairMark(few)?.color).toBe("cyan");
    expect(pairMark(pair({ state: "constant", r: null }))?.color).toBe("gray");
  });

  it("enseña primero los pares con r, de mayor a menor |r|; luego pocos días y al final las series planas", () => {
    const flat = pair({ state: "constant", r: null });
    const few = pair({ state: "insufficient", r: null });
    const weak = pair({ r: 0.1 });
    const strong = pair({ r: -0.7 });
    expect(orderedPairs([flat, few, weak, strong])).toEqual([strong, weak, few, flat]);
  });

  it("la escala de la dispersión respeta el margen; una serie plana va al centro", () => {
    expect(scale(0, 0, 10, 100, 10)).toBe(10);
    expect(scale(10, 0, 10, 100, 10)).toBe(90);
    expect(scale(5, 5, 5, 100, 10)).toBe(50);
  });

  it("las proyecciones preocupantes primero, como mucho las que caben", () => {
    const rows = scenarioRows([prediction("a", false), prediction("b", true), prediction("c", false), prediction("d", false)]);
    expect(rows.map((item) => item.key)).toEqual(["b", "a", "c"]);
    expect(rows).toHaveLength(SCENARIO_ROWS);
  });
});

describe("la vista", () => {
  it("son tres tarjetas de «Inicio» con su data-ui", () => {
    const html = render({});
    for (const ui of ["nodes-distance-risks", "nodes-correlations", "nodes-scenarios"]) {
      expect(html).toMatch(new RegExp(`data-ui="${ui}" class="ref-card `));
    }
  });

  it("la radiación lleva la dosis de carrera del backend sobre su límite, y sin ella la marca", () => {
    const html = render({});
    expect(html).toContain("120,0");
    expect(html).toContain("600");
    const none = statusOf({
      radiation: { career: { value_msv: null, limit_msv: 600, limit_source: "x", basis: "Sin dosis previa." }, projection: null },
    });
    expect(render({ home: home({}, none) })).toMatch(/c-cyan[^>]*>.*sin dosis de carrera/);
  });

  it("ningún porcentaje inventado ni rótulo de «IA»", () => {
    // El «IC 95 %» es de la frase del backend; fuera de ella, ningún porcentaje.
    const html = render({ links }).replaceAll("IC 95 %", "");
    // En el texto visible (el ancho del medidor, `width:20%`, es estilo, no una cifra).
    expect(html).not.toMatch(/>[^<]*\d\s?%[^<]*</);
    expect(html).not.toMatch(/\bIA\b|Sin anomalías/);
  });

  it("el retardo y la gravedad solo con el perfil declarado; la frase del perfil sigue a la elección", () => {
    const leo = render({});
    expect(leo).toMatch(/3,0 min <small>ida<\/small>/);
    expect(leo).toContain("Microgravedad (declarada en la configuración)");
    expect(leo).toContain("Frase del retardo en órbita baja.");
    expect(leo).toContain("(Órbita baja)");
    const mars = render({ profileId: "mars-transit" });
    expect(mars).toContain("Frase del retardo hacia Marte.");
    expect(mars).not.toContain("Frase del retardo en órbita baja.");
    expect(mars).toContain("solo del perfil declarado");
    expect(mars).not.toContain("Microgravedad (declarada");
    expect(mars).toContain("(Tránsito a Marte)");
    expect(mars).toContain("la ruta elegida no las cambia");
  });

  it("la frase «sin fuente» del backend va en gris", () => {
    expect(render({})).toMatch(/c-gray[^>]*>.*EMMA no tiene fuente/);
  });

  it("los dominios de cada peligro con su nivel; un peligro sin dominios, «sin nivel» en gris", () => {
    const html = render({});
    expect(html).toContain('data-challenge="isolation"');
    expect(html).toMatch(/c-gray[^>]*>.*sin nivel/);
  });

  it("los recursos son los recuentos declarados, con sus marcas", () => {
    const html = render({});
    expect(html).toMatch(/<span class="num">2<\/span> disponibles/);
    expect(html).toMatch(/c-cyan[^>]*>.*<span class="num">9<\/span> sin declarar/);
    const none = statusOf();
    (none.mission as { available_resources?: unknown }).available_resources = null;
    expect(render({ home: home({}, none) })).toMatch(/data-challenge="resources".*c-gray[^>]*>.*no disponible/);
  });

  it("la correlación es la del backend: r, n, alcance y los días como puntos", () => {
    const html = render({});
    expect(html).toContain("r = 0,78");
    expect(html).toContain("(n = 12)");
    expect(html).toContain("Correlación, no causa. Alcance del backend.");
    expect(html.match(/class="board-scatter-dot"/g)).toHaveLength(2);
    expect(html).toContain("<title>2026-11-01: 6,0 h · 300 ms</title>");
    expect(html).not.toContain("Series simuladas");
    expect(render({ correlations: correlations([pair({ simulated: true })]) })).toContain("Series simuladas: texto del backend.");
  });

  it("un par sin días bastantes dice cuántos tiene, en cian, sin r", () => {
    const few = pair({ state: "insufficient", r: null, n: 3, text: "3 días con las dos series; hacen falta 10." });
    const html = render({ correlations: correlations([few]) });
    expect(html).toMatch(/c-cyan[^>]*>.*hacen falta 10/);
    expect(html).not.toContain("r = ");
  });

  it("la correlación que no llega lo dice", () => {
    const html = render({ correlations: { state: "failed", outcome: { mark: { pictogram: "cross", color: "red" }, text: "Falló la petición." } as never } });
    expect(html).toContain("Falló la petición.");
  });

  it("los escenarios: proyecciones PREDICHAS, dosis al fin, aciertos y la recomendación tal cual", () => {
    const html = render({});
    expect(html).toContain("VO2-PEAK");
    expect(html).toContain("42,3");
    expect(html).toMatch(/<span class="num">4<\/span> de <span class="num">5<\/span> dentro del margen/);
    expect(html).toContain("Acción redactada por el backend.");
    const empty = statusOf({ predictions: [], recommendations: [], forecast_checks: { checked: 0, within_margin: 0, checks: [], basis: "" } });
    const none = render({ home: home({}, empty) });
    expect(none).toContain("Sin proyecciones para este tripulante.");
    expect(none).toContain("ninguna aún");
  });

  it("con los accesos de la consola llevan a su sección; sin ellos, ningún mando más que los pares", () => {
    expect(render({ links })).toContain('aria-label="Abrir Peligros y alertas: escenarios y recomendaciones"');
    expect(render({})).not.toContain("Abrir ");
  });
});

describe("el módulo y su hoja", () => {
  const source = readFileSync(fileURLToPath(new URL("./NodesOutlook.tsx", import.meta.url)), "utf8");
  const css = readFileSync(fileURLToPath(new URL("./nodesOutlook.css", import.meta.url)), "utf8");

  it("no trae nada del borrador de interpretación", () => {
    expect(source).not.toMatch(/from "[^"]*interpret/);
  });

  it("solo usa colores de la paleta", () => {
    const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, "");
    expect(withoutComments).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/);
    const known = new Set(Object.keys(palette).map((token) => cssVar(token as Token)));
    for (const name of new Set(css.match(/--c-[a-z-]+/g) ?? [])) expect(known.has(name), name).toBe(true);
  });

  it("ninguna letra por debajo del suelo de 0,875 rem", () => {
    const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, "");
    for (const [, value] of withoutComments.matchAll(/font-size:\s*([^;}]+)/g)) {
      const match = (value ?? "").trim().match(/^([\d.]+)rem$/);
      expect(match, value).not.toBeNull();
      expect(Number(match?.[1])).toBeGreaterThanOrEqual(0.875);
    }
  });

  // Lote «responsivo» (2026-11-16): los cortes miden el tablero (`@container ref-board`), no la
  // ventana; 1120 px de tablero son los 1400 de ventana de antes menos el carril.
  it("reparto 5 / 4 / 3 y a lo ancho en un tablero estrecho, medido por contenedor", () => {
    expect(css).toMatch(/\.no-risks \{ grid-column: span 5; \}/);
    expect(css).toMatch(/\.no-corr \{ grid-column: span 4; \}/);
    expect(css).toMatch(/\.no-scen \{ grid-column: span 3; \}/);
    expect(css).toMatch(/@container ref-board \(max-width: 1120px\) \{\s*\.ref-home \.no-risks \{ grid-column: span 12; \}/);
    expect(css).toMatch(/@container ref-board \(max-width: 820px\)[\s\S]*span 12/);
    expect(css.replace(/\/\*[\s\S]*?\*\//g, "")).not.toMatch(/@media \((max|min)-width/);
  });
});
