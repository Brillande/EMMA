import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
// Sin los `data-ui` del asistente: estas pruebas miran el marcado del panel.
import { renderToStaticMarkup } from "../assistant/staticMarkup";
import { describe, expect, it } from "vitest";

import { taggedPictogram } from "../advisor/visibleText";
import type { AlertDetail, AlertEvidence, AlertPersonalCut, CrewStatus } from "../lib/api";
import { AlertDetailView } from "./AlertDetailView";

/*
 * El detalle de una alerta MUESTRA lo que da el backend (`analysis/alert_context.py`): no
 * compone el contexto ni redacta por qué importa. Se comprueba pintando la vista con un detalle
 * de ejemplo y buscando cada frase tal cual, y leyendo su fuente para ver que no quedan las
 * frases que antes escribía.
 */

const LABEL = "correlación temporal, no causa";

const fiche = (id: string, title: string): AlertEvidence =>
  ({
    id,
    title,
    source: "NASA Human Research Program",
    url: `https://example.invalid/${id}`,
    grade: { label: "informe de evidencia" },
    cited_by: ["beh-sleep-hygiene"],
    role: "domain_risk",
    role_display: "riesgo del dominio",
    demo: true,
    demo_display: "citada aquí solo por comprobaciones demo",
  }) as unknown as AlertEvidence;

const detail: AlertDetail = {
  domain: "behavioral",
  ridge: "isolation",
  ridge_display: "aislamiento y confinamiento",
  onset: "2026-11-13T04:00:00+00:00",
  onset_basis: "primera lectura fuera de lo esperado dentro de la ventana actual",
  changed: [],
  trends: [],
  relevance: "Peligro RIDGE de NASA: aislamiento y confinamiento.",
  concordance: {
    trigger: "circadian-shift",
    trigger_display: "Desfase circadiano respecto al horario de misión",
    trigger_basis: "Se toma como el que inició la alerta el de la primera lectura.",
    total: 4,
    with_data: 3,
    concordant: 2,
    against: 0,
    unchanged: 1,
    no_data: 1,
    indicators: [
      {
        key: "circadian-shift",
        display: "Circadian phase shift from mission schedule",
        display_es: "Desfase circadiano respecto al horario de misión",
        state: "concordant",
        state_display: "se desvía en su sentido preocupante",
        is_trigger: true,
        role_display: "inició la alerta",
        description: "Desfase circadiano respecto al horario de misión: 2,4 h, por encima",
      },
      {
        key: "sleep-efficiency",
        display: "Sleep efficiency",
        display_es: "Eficiencia del sueño",
        state: "concordant",
        state_display: "se desvía en su sentido preocupante",
        is_trigger: false,
        role_display: null,
        description: "Eficiencia del sueño: bajando 3,0 %/semana",
      },
      {
        key: "mood-valence",
        display: "Self-reported mood valence",
        display_es: "Valencia del ánimo autoinformada",
        state: "unchanged",
        state_display: "con dato, sin desviación",
        is_trigger: false,
        role_display: null,
        description: null,
      },
      {
        key: "pvt-lapses",
        display: "Psychomotor vigilance task, lapses",
        display_es: "Lapsos en la tarea de vigilancia psicomotora (PVT; reacción de más de 500 ms)",
        state: "no_data",
        state_display: "sin dato",
        is_trigger: false,
        role_display: null,
        description: null,
      },
    ],
    statement: "Indicadores del dominio: 4. Con dato: 3. Desviados: 2. Sin dato: 1.",
    basis: "Descriptivo: no cambia el nivel de la alerta.",
  },
  context: {
    label: LABEL,
    summary: "Registrado dentro de la ventana: 2.",
    anchor: "2026-11-13T04:00:00+00:00",
    anchor_basis: "inicio de la alerta: primera lectura fuera de lo esperado",
    window_start: "2026-11-12T04:00:00+00:00",
    window_end: "2026-11-13T10:00:00+00:00",
    window_hours_before: 24,
    window_hours_after: 6,
    window_basis: "Ventana de diseño EMMA, sin fuente y sin ajustar con datos.",
    mission: {
      mission_day: 12.17,
      phase: "adaptation",
      phase_display: "adaptación",
      statement: "Inicio de la alerta: día de misión 12,2, adaptación, microgravedad.",
    },
    items: [
      {
        kind: "habitat",
        label: LABEL,
        title: "CO2 de cabina (presión parcial) fuera de su límite normativo ([V2 6004])",
        detail: null,
        start: "2026-11-12T05:00:00+00:00",
        end: "2026-11-14T23:00:00+00:00",
        timing: "fuera de límite en el inicio de la alerta; primera lectura fuera de límite 23,0 h antes",
        source: "telemetría de cabina, módulo habitat-principal",
        value: 5.314,
        value_label: "valor más alejado del límite",
        unit: "mm[Hg]",
      },
      {
        kind: "mission_event",
        label: LABEL,
        title: "EVA declarada",
        detail: "EVA 2",
        start: "2026-11-12T20:00:00+00:00",
        end: "2026-11-13T02:00:00+00:00",
        timing: "terminó 2,0 h antes del inicio de la alerta",
        source: "declarado por CDR, asiento 4321",
        value: null,
        value_label: null,
        unit: null,
      },
    ],
    sources: [
      {
        kind: "habitat",
        display: "Hábitat",
        status: "with_data",
        status_display: "con dato",
        found: 1,
        note: "Solo cuentan los límites normativos de NASA-STD-3001.",
      },
      {
        kind: "solar_event",
        display: "Evento solar",
        status: "no_data",
        status_display: "sin dato",
        found: 0,
        note: "Sin datos de NASA DONKI: no se sabe si hubo un evento solar.",
      },
      {
        kind: "sleep",
        display: "Sueño",
        status: "no_data",
        status_display: "sin dato",
        found: 0,
        note: "Sin lecturas de sueño en la ventana: que no conste no quiere decir que no lo hubiera.",
      },
    ],
    note: "Coincidir en el tiempo con el inicio de una alerta no dice que sea su causa.",
  },
  relevance_evidence: {
    id: "hrp-risk-behavioral",
    title: "Riesgo conductual",
    text: "El aislamiento y la alteración circadiana degradan el sueño.",
  },
  checks: {
    statement: "Comprobaciones estructuradas para este dominio: 2.",
    items: [
      {
        id: "beh-sleep-hygiene",
        title: "Revisar el horario de sueño de la semana",
        indication: "Sueño corto o fragmentado",
        urgency: "routine",
        basis: "demo",
        basis_display: "demo: la respalda solo el riesgo del dominio, no un protocolo concreto",
        demo: true,
        evidence_ids: ["hrp-risk-behavioral"],
      },
      {
        id: "beh-light",
        title: "Comprobar la exposición a luz antes del descanso",
        indication: "Desfase circadiano",
        urgency: "routine",
        basis: "evidence-backed",
        basis_display: "la respalda un protocolo concreto",
        demo: false,
        evidence_ids: ["hrp-risk-behavioral"],
      },
    ],
  },
  evidence: {
    statement: "Fichas de evidencia enlazadas: 1.",
    items: [fiche("hrp-risk-behavioral", "Riesgo conductual")],
  },
  persistence: {
    sustained: 1,
    statement: "Indicadores que cuentan como hallazgo por sus lecturas: 1 de 2.",
    basis: "Misma regla con la que el motor de riesgo de EMMA decide. Descriptivo.",
    indicators: [
      {
        key: "circadian-shift",
        display: "Circadian phase shift from mission schedule",
        display_es: "Desfase circadiano respecto al horario de misión",
        readings: 10,
        out_of_expected: 4,
        fraction: 0.4,
        severe: 0,
        required_fraction: 0.3,
        required_severe: 2,
        sustained: true,
        rule: "persistence",
        trend: false,
        statement: "Desfase circadiano respecto al horario de misión: 4 de 10 lecturas de la ventana actual fuera de lo esperado (40 %).",
      },
      {
        key: "sleep-efficiency",
        display: "Sleep efficiency",
        display_es: "Eficiencia del sueño",
        readings: 10,
        out_of_expected: 1,
        fraction: 0.1,
        severe: 0,
        required_fraction: 0.3,
        required_severe: 2,
        sustained: false,
        rule: null,
        trend: true,
        statement: "Eficiencia del sueño: 1 de 10 lecturas de la ventana actual fuera de lo esperado (10 %).",
      },
    ],
  },
  confidence: {
    low_confidence_threshold: 0.5,
    labels: { low: "baja confianza", declared: "confianza declarada", undeclared: "no declarada" },
    readings: 5,
    low_confidence: 1,
    declared: 0,
    undeclared: 4,
    not_found: 0,
    capped: 1,
    personal_baseline: 5,
    population_range: 0,
    indicators: [
      {
        key: "circadian-shift",
        display: "Circadian phase shift from mission schedule",
        display_es: "Desfase circadiano respecto al horario de misión",
        readings: 4,
        low_confidence: 1,
        declared: 0,
        undeclared: 3,
        not_found: 0,
        capped: 1,
        personal_baseline: 4,
        population_range: 0,
        compared_with: ["línea base personal"],
        statement: "Desfase circadiano respecto al horario de misión: 4 lecturas fuera de lo esperado; de baja confianza de medida, 1.",
      },
    ],
    statement: "Lecturas fuera de lo esperado de este dominio en la ventana actual: 5. De baja confianza: 1.",
    trend_note: "La tendencia no distingue la confianza de la medida.",
    note: "Sin cifra única de confianza: EMMA no la inventa. Se dan los recuentos.",
    basis: "Descriptivo: no cambia el nivel de la alerta.",
  },
};

/*
 * El estado lleva recomendaciones de este dominio que el detalle NO trae: si la vista volviera a
 * componer «qué comprobar» o la evidencia a partir de ellas, saldrían en pantalla.
 */
const STRAY = "Acción que solo está en las recomendaciones del estado";
const status = {
  mission: { start: "2026-11-01" },
  recommendations: [
    {
      domain: "behavioral",
      action: STRAY,
      evidence: [{ id: "stray", title: "Ficha que solo está en el estado", source: "x", url: null, relevance: STRAY }],
    },
  ],
} as unknown as CrewStatus;

const render = (shown: AlertDetail, level = "watch") =>
  renderToStaticMarkup(createElement(AlertDetailView, { detail: shown, level, status }));

/** Un cambio de «qué cambió» con el sentido estructurado que da el backend. */
const change = (key: string, direction: "high" | "low", description: string): AlertDetail["changed"][number] => ({
  key,
  display: key,
  display_es: key,
  unit: "/min",
  value: 92,
  effective: "2026-11-13T04:00:00+00:00",
  severity: "moderate",
  direction,
  basis: null,
  baseline_median: 60,
  baseline_samples: 40,
  compared_with: "línea base personal",
  danger_limit: null,
  description,
});

const trend = (key: string, direction: "rising" | "falling" | "stable", description: string): AlertDetail["trends"][number] => ({
  key,
  display: key,
  display_es: key,
  description,
  span_days: 7,
  direction,
});

describe("detalle de alerta: el contexto y la concordancia se muestran tal cual los da el backend", () => {
  const html = render(detail);
  const context = detail.context;
  if (context === undefined) throw new Error("el ejemplo lleva contexto");

  it("cada elemento de contexto lleva su rótulo de no-causa", () => {
    expect(html.split(`<em>${LABEL}</em>`).length - 1).toBe(context.items.length);
  });

  it("muestra cada frase del contexto sin tocarla", () => {
    for (const text of [
      context.summary,
      context.note,
      context.mission.statement,
      context.window_basis,
      ...context.items.flatMap((item) => [item.title, item.timing, item.source]),
      ...context.sources.map((source) => source.note),
      "EVA declarada</strong>: EVA 2",
    ]) {
      expect(html, text).toContain(text);
    }
  });

  it("las cifras y los instantes pasan por format.ts", () => {
    expect(html).toContain('valor más alejado del límite <span class="num">5,3</span> mmHg');
    expect(html).toContain('<span class="num">MET 11/05:00:00</span>');
    expect(html).toContain('<span class="num">MET 11/04:00:00</span> – <span class="num">MET 12/10:00:00</span>');
  });

  it("una fuente sin dato va en cian con su anillo punteado y su palabra; una con dato, sin señal", () => {
    expect(html).toMatch(
      /<span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted">.*?<\/svg>Evento solar: sin dato<\/span>/,
    );
    // Una fuente nueva (el sueño, decimonovena ronda) se pinta igual: la vista no distingue clases.
    expect(html).toMatch(
      /<span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted">.*?<\/svg>Sueño: sin dato<\/span>/,
    );
    expect(html).toContain('<span class="mark">Hábitat: con dato</span>');
  });

  it("muestra la concordancia: la frase, cada indicador con dato y los que no lo tienen", () => {
    expect(html).toContain(detail.concordance.statement);
    expect(html).toContain(detail.concordance.trigger_basis);
    expect(html).toContain(detail.concordance.basis);
    // Cada indicador con su nombre y el dibujo de su familia (`IndicatorName`), y su estado detrás.
    expect(html).toMatch(
      /<li><span class="mark"><svg [^>]*data-pictogram="moon-z">.*?<\/svg>Desfase circadiano respecto al horario de misión<\/span>: se desvía en su sentido preocupante<strong> · inició la alerta<\/strong>/,
    );
    expect(html).toMatch(
      /<li><span class="mark"><svg [^>]*data-pictogram="face-neutral">.*?<\/svg>Valencia del ánimo autoinformada<\/span>: con dato, sin desviación/,
    );
    expect(html).toMatch(
      /<p><span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted">.*?<\/svg>sin dato: Lapsos en la tarea de vigilancia psicomotora \(PVT; reacción de más de 500 ms\)<\/span><\/p>/,
    );
  });

  it("por qué puede importar es la frase del backend", () => {
    expect(html).toContain(detail.relevance);
  });

  it("sin contexto calculado no inventa uno", () => {
    const { context: _dropped, ...bare } = detail;
    const without = render(bare);
    expect(without).not.toContain(LABEL);
    expect(without).toContain(detail.concordance.statement);
  });
});

describe("detalle de alerta: qué comprobar, evidencia, persistencia y confianza son del backend", () => {
  const html = render(detail);

  it("pinta cada comprobación con su título y su base, en el orden del backend", () => {
    const [first, second] = detail.checks.items;
    if (first === undefined || second === undefined) throw new Error("el ejemplo lleva dos");
    expect(html).toContain(`<li>${first.title}<span class="secondary"> — ${first.basis_display}</span></li>`);
    expect(html.indexOf(first.title)).toBeLessThan(html.indexOf(second.title));
  });

  it("pinta cada ficha con su fuente, su grado, su papel y si es demo", () => {
    expect(html).toContain(
      "— NASA Human Research Program · informe de evidencia · riesgo del dominio" +
        " · citada aquí solo por comprobaciones demo",
    );
    expect(html).toContain('<a href="https://example.invalid/hrp-risk-behavioral"');
  });

  it("no compone nada a partir de las recomendaciones del estado", () => {
    expect(html).not.toContain(STRAY);
    expect(html).not.toContain("Ficha que solo está en el estado");
  });

  it("no deduplica ni filtra: dos fichas con el mismo título se pintan las dos", () => {
    const twice = render({
      ...detail,
      evidence: {
        statement: "Fichas de evidencia enlazadas: 2.",
        items: [fiche("a", "Mismo título"), fiche("b", "Mismo título")],
      },
    });
    expect(twice.split("Mismo título").length - 1).toBe(2);
  });

  it("el porqué citado es el que eligió el backend", () => {
    expect(html).toContain(`<span class="secondary"> ${detail.relevance_evidence?.text}</span>`);
    expect(render({ ...detail, relevance_evidence: null })).not.toContain(
      detail.relevance_evidence?.text,
    );
  });

  it("sin comprobaciones ni fichas pinta la frase del backend, no un hueco", () => {
    const empty = render({
      ...detail,
      checks: { items: [], statement: "sin comprobación estructurada para este dominio" },
      evidence: { items: [], statement: "sin evidencia enlazada para este dominio" },
    });
    expect(empty).toContain('<span class="secondary">sin comprobación estructurada para este dominio</span>');
    expect(empty).toContain('<span class="secondary">sin evidencia enlazada para este dominio</span>');
  });

  it("pinta la persistencia: la frase, cada indicador y la base", () => {
    for (const text of [
      detail.persistence.statement,
      detail.persistence.basis,
      ...detail.persistence.indicators.map((item) => item.statement),
    ]) {
      expect(html, text).toContain(text);
    }
  });

  it("pinta la confianza en recuentos, con la nota de que no hay cifra única", () => {
    for (const text of [
      detail.confidence.statement,
      detail.confidence.note,
      detail.confidence.basis,
      detail.confidence.trend_note ?? "",
      ...detail.confidence.indicators.map((item) => item.statement),
    ]) {
      expect(html, text).toContain(text);
    }
    // El umbral es del motor y no se pinta como si fuera la confianza de la alerta.
    expect(html).not.toContain("0,5");
  });
});

describe("F.4.3.1 d: la flecha de «qué cambió» sale del sentido estructurado, con el color del nivel", () => {
  const shown: AlertDetail = {
    ...detail,
    changed: [change("hr-rest", "high", "FC en reposo: 92 lpm, por encima"), change("spo2", "low", "SpO2: 93 %, por debajo")],
    trends: [trend("sleep-efficiency", "falling", "Eficiencia del sueño: bajando"), trend("mood", "stable", "Ánimo: estable")],
  };

  it("por encima, flecha arriba; por debajo, flecha abajo; bajando, abajo; el color del nivel solo en la flecha", () => {
    const html = render(shown, "concern");
    expect(html).toMatch(/<li><span class="mark c-yellow"><svg [^>]*data-pictogram="arrow-up">.*?<\/svg><span class="c-text">FC en reposo: 92 lpm, por encima<\/span><\/span><\/li>/);
    expect(html).toMatch(/<li><span class="mark c-yellow"><svg [^>]*data-pictogram="arrow-down">.*?<\/svg><span class="c-text">SpO2: 93 %, por debajo<\/span><\/span><\/li>/);
    expect(html).toMatch(/<li><span class="mark c-yellow"><svg [^>]*data-pictogram="arrow-down">.*?<\/svg><span class="c-text">Eficiencia del sueño: bajando<\/span><\/span><\/li>/);
    expect(render(shown, "critical")).toMatch(/<span class="mark c-red"><svg [^>]*data-pictogram="arrow-up">/);
    expect(render(shown, "watch")).toMatch(/<span class="mark c-blue"><svg [^>]*data-pictogram="arrow-up">/);
  });

  it("sin sentido (estable) no hay flecha ni color: la frase tal cual", () => {
    expect(render(shown, "concern")).toContain('<li><span class="mark">Ánimo: estable</span></li>');
  });

  it("la flecha no se deduce de la frase: un backend que no da el sentido deja la frase sin flecha", () => {
    const { direction: _dropped, ...bare } = change("hr-rest", "high", "FC en reposo: 92 lpm, por encima");
    const html = render({ ...shown, changed: [bare as AlertDetail["changed"][number]], trends: [] }, "concern");
    expect(html).toContain('<li><span class="mark">FC en reposo: 92 lpm, por encima</span></li>');
    expect(html).not.toContain('data-pictogram="arrow-up"');
  });

  it("un nivel desconocido falla en vez de pintar un color cualquiera", () => {
    expect(() => render(shown, "grave")).toThrow(RangeError);
  });
});

describe("§5.34.6: cuánto cambió, qué cuesta comprobar y por qué paso va, tal cual del backend", () => {
  const RATIO = "Un 14 % por debajo de su mediana personal.";
  const ORDINAL = "Sin cambio relativo: es una puntuación ordinal o de valoración: sus distancias no son proporciones.";
  const withRelative = (statement: string, applies: boolean): AlertDetail["changed"][number] => ({
    ...change("hrv-sdnn", "low", "Variabilidad: 43 ms, por debajo"),
    relative_change: { applies, percent: applies ? -14 : null, median: applies ? 50 : null, statement, basis: "b" },
  });
  const fact = (key: string, label: string, display: string, missing = false) => ({ key, label, display, missing });
  const [first, second] = detail.checks.items;
  if (first === undefined || second === undefined) throw new Error("el ejemplo lleva dos");
  const shown: AlertDetail = {
    ...detail,
    changed: [withRelative(RATIO, true), { ...withRelative(ORDINAL, false), key: "mood-valence" }],
    checks: {
      ...detail.checks,
      order_note: "En el orden en que las da el recomendador: el coste se anota al lado, no las reordena.",
      unclassified_note: "«Sin clasificar» es que no se deduce de lo que el repositorio dice del indicador.",
      items: [
        {
          ...first,
          cost: {
            action: { ...fact("crew_time", "Tiempo de tripulación de la acción", "sin cifra con fuente", true), minutes: null, basis: null },
            indicators: [
              {
                key: "sleep-duration",
                display_es: "Duración del sueño",
                statement: "s",
                facts: [
                  fact("mode", "Clase de medida", "continuo y pasivo"),
                  fact("crew_time", "Tiempo de tripulación para medirlo", "sin cifra con fuente", true),
                  fact("processing", "Dónde se procesa", "a bordo, en el propio dispositivo"),
                  fact("consumables", "Consumibles", "sin clasificar", true),
                ],
              },
            ],
            statement: null,
          },
        },
        {
          ...second,
          cost: {
            action: { ...fact("crew_time", "Tiempo de tripulación de la acción", "10 min"), minutes: 10, basis: "procedimiento" },
            indicators: [],
            statement: "No repite ningún indicador: no hay coste de medida que anotar.",
          },
        },
      ],
    },
    flow: {
      basis: "Flujo de la base de conocimiento del equipo (§10).",
      steps: [
        { key: "sense", name: "Medir", kb_name: "SENSE", state: "done", state_display: "hecho", detail: "40 lecturas de 3 indicadores." },
        { key: "human_decision", name: "Decisión humana", kb_name: "HUMAN DECISION", state: "awaiting_human", state_display: "pendiente de una persona", detail: "Pendiente de que una persona la reconozca." },
        { key: "follow_up", name: "Seguimiento", kb_name: "FOLLOW-UP", state: "not_applicable", state_display: "no aplica", detail: "Sin contramedida adoptada." },
        { key: "new", name: "Paso nuevo", kb_name: "NEW", state: "future_state", state_display: "estado nuevo", detail: "d" },
      ],
    },
  };
  const html = render(shown);

  it("el cambio relativo es la frase del backend; el que no se da, en secundario", () => {
    expect(html).toContain(`<span> · ${RATIO}</span>`);
    expect(html).toContain(`<span class="secondary"> · ${ORDINAL}</span>`);
  });

  it("cada comprobación lleva su coste plegado, con rótulos y valores del backend", () => {
    expect(html).toMatch(taggedPictogram("summary", "coins", "Qué cuesta comprobarlo"));
    expect(html).toContain("Clase de medida: continuo y pasivo");
    expect(html).toContain("Dónde se procesa: a bordo, en el propio dispositivo");
    expect(html).toContain('Tiempo de tripulación de la acción: 10 min<span class="secondary"> (procedimiento)</span>');
    expect(html).toContain('<li class="secondary">No repite ningún indicador: no hay coste de medida que anotar.</li>');
    // El nombre del indicador con su dibujo, como en el resto del detalle.
    expect(html).toMatch(/<span class="mark"><svg [^>]*data-pictogram="[a-z-]+">.*?<\/svg>Duración del sueño<\/span>: /);
  });

  it("lo que falta del coste va en cian con el anillo punteado, decidido por `missing`", () => {
    // Desde la decimosexta ronda lo que falta de un indicador va junto, por su palabra del backend.
    expect(html).toMatch(/<span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted">.*?<\/svg>sin clasificar<\/span>: <span class="secondary">[^<]*Consumibles[^<]*<\/span>/);
    expect(html).toMatch(/Tiempo de tripulación de la acción: <span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted">.*?<\/svg>sin cifra con fuente<\/span>/);
    expect(html).not.toMatch(/Clase de medida: <span class="mark c-cyan">/);
  });

  it("las comprobaciones salen en el orden del backend, con las dos notas", () => {
    expect(html.indexOf(first.title)).toBeLessThan(html.indexOf(second.title));
    expect(html).toContain(`${shown.checks.order_note} ${shown.checks.unclassified_note}`);
  });

  it("los pasos del flujo: nombre, la marca de los pasos de una hipótesis y la frase", () => {
    expect(html).toMatch(/<strong>Medir<\/strong> <span class="mark c-text"><svg [^>]*data-pictogram="check">.*?<\/svg>hecho<\/span>/);
    expect(html).toMatch(/<span class="mark c-blue"><svg [^>]*data-pictogram="box-empty">.*?<\/svg>pendiente de una persona<\/span>/);
    expect(html).toMatch(/<span class="mark c-gray"><svg [^>]*data-pictogram="dash">.*?<\/svg>no aplica<\/span>/);
    // Un estado que esta versión no conoce: su palabra, sin significado propio.
    expect(html).toMatch(/<span class="mark c-text"><svg [^>]*data-pictogram="dot-small">.*?<\/svg>estado nuevo<\/span>/);
    for (const step of shown.flow?.steps ?? []) expect(html, step.detail).toContain(step.detail);
    expect(html).toContain(shown.flow?.basis);
  });

  it("un backend anterior sin estos campos no rompe la vista", () => {
    const old = render(detail);
    expect(old).not.toContain("Qué cuesta comprobarlo");
    expect(old).toMatch(taggedPictogram("dt", "squares-arrow", "Por qué paso va</dt>"));
  });
});

describe("la vista no redacta lo que antes componía", () => {
  const source = readFileSync(fileURLToPath(new URL("./AlertDetailView.tsx", import.meta.url)), "utf8");

  it("no escribe el peligro RIDGE, ni la fase, ni remite a otro panel", () => {
    for (const composed of [
      "Peligro RIDGE",
      "día de misión",
      "phase_display",
      "gravity_regime",
      "active_solar_event",
      "Tripulación y hábitat",
      "no causa",
      // Lo que componía con las recomendaciones del estado: filtrar, deduplicar y elegir.
      "recommendations",
      "flatMap",
      "seen.has",
      ".relevance ??",
      "sin recomendación",
      "sin comprobación",
      "Sin cifra única",
      "low_confidence_threshold",
      // Lo de §5.34.6: el cambio relativo, el coste y los pasos los redacta el backend.
      "mediana personal",
      "Sin cambio relativo",
      "Clase de medida",
      "Dónde se procesa",
      "pendiente de una persona",
      "Reconocida por",
      "sort(",
    ]) {
      expect(source, composed).not.toContain(composed);
    }
  });
});

describe("cada pregunta del detalle lleva su signo (segunda pasada, §5.33.1)", () => {
  const html = render(detail);

  it("el plegable lleva el de «detalle», con la palabra de siempre", () => {
    expect(html).toMatch(taggedPictogram("summary", "text-lines", "Detalle: qué cambió, desde cuándo y por qué"));
    expect(html).toMatch(/^<details class="alert-detail">/);
  });

  it("cada clave con un dibujo distinto, del vocabulario común salvo «qué depende»", () => {
    const signs: [string, string][] = [
      ["chart-line", "Qué cambió"],
      ["clock", "Desde cuándo"],
      ["pillars", "Frente a qué base"],
      ["bars-two", "Concordancia entre señales"],
      ["arrows-cycle", "Persistencia"],
      ["percent", "Confianza de las lecturas"],
      ["stopwatch", "Tiempo hasta la acción"],
      ["clock-rewind", "Qué contexto cambió"],
      ["bubble-lines", "Por qué puede importar"],
      ["magnifier", "Qué comprobar"],
      ["squares-arrow", "Por qué paso va"],
      ["dot-tree", "Qué depende de estos datos"],
      ["sheet-lines", "Evidencia"],
    ];
    for (const [pictogram, word] of signs) {
      expect(html, word).toMatch(taggedPictogram("dt", pictogram, `${word}</dt>`));
    }
    expect(new Set(signs.map(([pictogram]) => pictogram)).size).toBe(signs.length);
    expect(html.split("<dt>").length - 1).toBe(signs.length);
  });
});

describe("el tipo de las lecturas y el corte personal que cruzaron (§5.37.1)", () => {
  const CUT = "Por encima del percentil 99 de su línea base personal (70 /min, sobre 188 lecturas).";
  const NO_CUT = "Juzgada contra el rango poblacional: no hay corte de línea base personal.";
  const READINGS = "Lecturas fuera de lo esperado que la causaron: 2 lecturas medidas.";
  const RULE = "La línea base, la tendencia y el riesgo solo leen lecturas medidas.";
  const cut = (applies: boolean, statement: string): AlertPersonalCut => ({
    applies,
    percentile: applies ? 99 : null,
    value: applies ? 70 : null,
    unit: "/min",
    samples: 188,
    statement,
    basis: "b",
  });
  const readings = { causes: { measured: 2 }, set_aside: {}, statement: READINGS, rule: RULE };
  const shown: AlertDetail = {
    ...detail,
    changed: [
      { ...change("heart-rate", "high", "FC: 92 lpm, por encima"), observation_type: "measured", personal_cut: cut(true, CUT) },
      { ...change("spo2", "low", "SpO2: 88 %, por debajo"), observation_type: null, personal_cut: cut(false, NO_CUT) },
    ],
    readings,
  };
  const html = render(shown);

  it("cada cambio lleva la insignia del tipo de su lectura; sin tipo localizado, ninguna", () => {
    expect(html.split('class="mark obs-type"').length - 1).toBe(1);
    expect(html).toMatch(/FC: 92 lpm, por encima.*?<span class="mark obs-type"[^>]*>.*?MEDIDO<\/span>/);
  });

  it("dice el corte personal que cruzó con la frase del backend, y en secundario por qué no lo hay", () => {
    expect(html).toContain(` · ${CUT}`);
    expect(html).toContain(`<span class="secondary"> · ${NO_CUT}</span>`);
  });

  it("dice de qué tipo son las lecturas que la causaron, con la regla", () => {
    expect(html).toContain(`<p class="secondary">${READINGS} ${RULE}</p>`);
  });

  it("sin cambios ni lecturas apartadas no repite la frase de «sin lecturas»", () => {
    const bare = render({ ...shown, changed: [], readings: { ...readings, statement: "nada" } });
    expect(bare).not.toContain("nada");
  });
});
