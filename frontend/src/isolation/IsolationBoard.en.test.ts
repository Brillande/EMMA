/**
 * La sección «Aislamiento» en inglés (`lib/i18n.ts`): los rótulos propios del tablero salen en
 * inglés; la frase de la comida, el perfil y las palabras de nivel son del backend y no se tocan.
 */
import "../test/english";

import { type FunctionComponent, createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { language } from "../lib/i18n";
import {
  ISOLATION_KEYS,
  IsoAlerts,
  IsoCorrelations,
  IsoFactors,
  IsoGlobal,
  IsoHeader,
  IsoIndicators,
  IsoInteractions,
  IsoLight,
  IsoNutrition,
  IsoProgress,
  IsoRecommendations,
  IsoRisk,
  IsoSleep,
  IsoTests,
  IsoTrend,
  type IsolationData,
} from "./IsolationBoard";

const REFERENCE = Date.parse("2026-11-08T12:00:00Z");
const DAY = 24 * 3600 * 1000;

const ready = <T,>(value: T) => ({ state: "ready" as const, value });

/** Una lectura al día durante 14 días: hay dos semanas que comparar y racha de registros. */
const daily = (base: number) => Array.from({ length: 14 }, (_, index) => ({ at: REFERENCE - index * DAY - 3600 * 1000, value: base + index })).reverse();

const iso = {
  home: {
    reference: REFERENCE,
    catalog: new Map(),
    status: {
      subject: "crew-01",
      mission: { profile: { display: "PERFIL-DEL-BACKEND" } },
      domains: { behavioral: { level: "watch", score: 0.42, drivers: [], trajectory: null } },
      alerts: [],
      recommendations: [],
      data: { reference_time: new Date(REFERENCE).toISOString() },
    },
  },
  series: ready(Object.fromEntries(ISOLATION_KEYS.map((key) => [key, key === "pvt-lapses" ? [] : daily(5)]))),
  energy: ready([]),
  protocol: ready({ tests: [] }),
  sessions: ready({ sessions: [], count: 0 }),
  food: ready({ rated: 4, below: 1, statement: "FRASE-DEL-BACKEND" }),
  correlations: ready({ pairs: [], tested: 6, pairs_basis: "", simulated_text: "" }),
  risk: ready(null),
  habitat: ready({ readings: [] }),
  planner: ready({ members: [], leisure_rule: "" }),
  links: undefined,
} as unknown as IsolationData;

const render = (piece: FunctionComponent<{ iso: IsolationData }>) => renderToStaticMarkup(createElement(piece, { iso }));

describe("la sección «Aislamiento» en inglés", () => {
  it("este fichero corre en inglés", () => {
    expect(language()).toBe("en");
  });

  it("la cabecera: título, hora de los datos, antigüedad y tripulante", () => {
    const html = render(IsoHeader);
    expect(html).toContain('aria-label="Isolation and psychosocial health"');
    expect(html).toContain("Data as of");
    expect(html).toContain("Crew member:");
    expect(html).toMatch(/<span class="num">[^<]+<\/span> ago/);
    expect(html).toContain("PERFIL-DEL-BACKEND");
    expect(html).not.toMatch(/Aislamiento|Datos a|Tripulante|hace/);
  });

  it("el estado global y los indicadores", () => {
    const global = render(IsoGlobal);
    expect(global).toContain("Overall status (isolation)");
    expect(global).toContain("Active behavioral alerts");
    expect(global).toContain("Behavioral recommendations");
    expect(global).toContain("Indicators with a reading in 24 h");
    const indicators = render(IsoIndicators);
    expect(indicators).toContain("Behavioral indicators");
    expect(indicators).toContain("Mood (self-report)");
    expect(indicators).toContain("Sleep duration");
    expect(indicators).toContain("with a reading in 24 h");
    expect(global + indicators).not.toMatch(/Estado global|Alertas|Indicadores|Ánimo|Duración/);
  });

  it("tendencia, factores y sueño", () => {
    const trend = render(IsoTrend);
    expect(trend).toContain('aria-label="14-day trend"');
    expect(trend).toContain("Trend (14 days)");
    expect(trend).toContain("Axis: % of each curve&#x27;s span (daily means).");
    const factors = render(IsoFactors);
    expect(factors).toContain("Factors (weekly change)");
    expect(factors).toContain("PVT: lapses");
    expect(factors).toContain("under 2 weeks");
    const sleep = render(IsoSleep);
    expect(sleep).toContain("Sleep and circadian rhythm");
    expect(sleep).toContain("Hours of sleep per day");
    expect(sleep).toContain("Circadian shift (7 d)");
    expect(trend + factors + sleep).not.toMatch(/Tendencia|Factores|sin 2 semanas|Sueño|Desfase/);
  });

  it("interacciones, luz y nutrición: lo que no se mide se dice, y la frase del backend va tal cual", () => {
    const interactions = render(IsoInteractions);
    expect(interactions).toContain("Crew interactions");
    expect(interactions).toContain("no planner records this week");
    expect(interactions).toContain("From the planner; cohesion is not measured.");
    const light = render(IsoLight);
    expect(light).toContain("Light exposure");
    expect(light).toContain("no cabin light readings");
    expect(light).toContain("Cabin light, not light at the eye; not evaluated.");
    const nutrition = render(IsoNutrition);
    expect(nutrition).toContain("Nutrition and menu");
    expect(nutrition).toContain("Energy intake (7 d)");
    expect(nutrition).toContain("Dishes rated");
    expect(nutrition).toContain("Below the criterion");
    expect(nutrition).toContain("FRASE-DEL-BACKEND");
    expect(interactions + light + nutrition).not.toMatch(/Interacciones|planificador|Exposición|Luz de cabina|Nutrición|Platos|sin dato/);
  });

  it("pruebas, constancia y correlaciones", () => {
    expect(render(IsoTests)).toContain("Cognitive tests · Cognition battery");
    const progress = render(IsoProgress);
    expect(progress).toContain("Consistency (7 days)");
    expect(progress).toContain("Days with PVT");
    expect(progress).toMatch(/PVT streak: <span class="num">\d+<\/span> days in a row/);
    expect(progress).toContain("Mood self-report:");
    expect(progress).toContain("Counts only: EMMA gives no points or levels.");
    const correlations = render(IsoCorrelations);
    expect(correlations).toContain("Key correlations");
    expect(correlations).toContain("automatic search of 6 pairs");
    expect(correlations).toContain("no pair with enough days");
    expect(correlations).toContain("Ask the AI for a reading");
    expect(progress + correlations).not.toMatch(/Constancia|Racha|Solo recuentos|Correlaciones|búsqueda|Pedir lectura/);
  });

  it("riesgo, recomendaciones y alertas: sin nada que hacer, se dice sin sonar a orden", () => {
    const risk = render(IsoRisk);
    expect(risk).toContain("Risk (behavioral domain)");
    expect(risk).toContain("(0.42)");
    expect(risk).toContain("Score from EMMA&#x27;s risk engine, not a probability.");
    const recommendations = render(IsoRecommendations);
    expect(recommendations).toContain("Countermeasures (library)");
    expect(recommendations).toContain("No behavioral recommendations: nothing requires action.");
    const alerts = render(IsoAlerts);
    expect(alerts).toContain("Alerts (behavioral)");
    expect(alerts).toContain("No active behavioral alerts.");
    expect(risk + recommendations + alerts).not.toMatch(/Riesgo|Puntuación|Contramedidas|Sin recomendaciones|Alertas|Sin alertas/);
  });
});
