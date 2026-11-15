import { createElement } from "react";
// Sin los `data-ui` del asistente: estas pruebas miran el marcado del panel.
import { renderToStaticMarkup } from "../assistant/staticMarkup";
import { describe, expect, it } from "vitest";

import type {
  AlertContext,
  AnatomyRegionState,
  AnatomyRisk,
  CrewStatus,
  EvidenceItem,
  ResearchEvidenceItem,
} from "../lib/api";
import { LEVELS, adoptLevelLabels } from "../lib/levels";
import { RegionChain } from "./RegionChain";

// La palabra de cada nivel llega con el estado (`level_labels`); estas son las de este ejemplo.
adoptLevelLabels({
  nominal: "Nominal",
  watch: "Vigilancia",
  concern: "Precaución",
  critical: "Crítico",
});

/**
 * La cadena se pinta de verdad (a HTML estatico: sin navegador no corren los efectos, asi que no
 * hay red ni grafica) y se comprueba lo que la interfaz promete: los textos son los del backend,
 * el orden es el de la especificacion §10 y "sin datos" no se convierte en nominal.
 */

const status = {
  subject: "crew-01",
  mission: { start: "2026-11-01" },
  data: { reference_time: "2026-12-11T00:00:00+00:00", trend_window_days: 21 },
  inferred: [],
} as unknown as CrewStatus;

const grade = (label: string, preclinical = false): EvidenceItem["grade"] => ({
  source: "",
  pmid: null,
  // Sin PMID el nivel preclinico solo puede salir del texto de la cita (`evidence/tier.py`).
  basis: preclinical ? "text" : "none",
  tier: preclinical ? "modelo_animal" : "desconocido",
  label,
  preclinical,
  reason: "",
});

const HRP_RELEVANCE = "El vuelo prolongado produce desacondicionamiento cardiovascular.";
const OSD_288_RELEVANCE = "RNA-Seq de bazo de ratón tras 35 días en la ISS (misión SpaceX-9).";
const OSD_288_CAVEAT =
  "Modelo murino: 12 ratones volaron 35 días en la ISS y el conjunto de OSDR publica 9 muestras de bazo. NO mide signos vitales humanos.";

// Las dos fichas con la forma que da el registro unico del backend (`app/evidence/registry.py`):
// lo que no esta verificado va en `null` y se nombra en `unverified_display`.
const HRP: EvidenceItem = {
  id: "hrp-risk-cardiovascular",
  title: "Riesgo de acontecimientos cardiovasculares y desacondicionamiento",
  source: "NASA Human Research Program",
  url: "https://humanresearchroadmap.nasa.gov/risks/",
  doi: null,
  pmid: null,
  organization: "NASA Human Research Program",
  date: null,
  evidence_type: "hrp_risk",
  evidence_type_display: "riesgo del HRP",
  evidence_context: null,
  population: null,
  population_display: "sin clasificar",
  notes: null,
  not_applicable: [],
  outside_enum: [],
  outside_enum_display: [],
  unverified: ["doi", "date", "evidence_context", "population"],
  unverified_display: ["DOI", "fecha", "entorno del estudio", "población"],
  relevance: HRP_RELEVANCE,
  scope_caveat: null,
  scope_in_view: null,
  grade: grade("desconocido: no clasificable desde el registro"),
};

const OSD_288: EvidenceItem = {
  id: "osd-288",
  title: "Transcriptome analysis of murine spleen in space",
  source: "NASA OSDR · OSD-288",
  url: "https://osdr.nasa.gov/bio/repo/data/studies/OSD-288",
  doi: null,
  pmid: null,
  organization: "NASA OSDR",
  date: null,
  evidence_type: "dataset",
  evidence_type_display: "conjunto de datos",
  evidence_context: "iss",
  population: "animal",
  population_display: "animal",
  notes: OSD_288_CAVEAT,
  not_applicable: [],
  outside_enum: [],
  outside_enum_display: [],
  unverified: ["doi", "date"],
  unverified_display: ["DOI", "fecha"],
  relevance: OSD_288_RELEVANCE,
  scope_caveat: OSD_288_CAVEAT,
  scope_in_view: OSD_288_CAVEAT,
  grade: grade("modelo animal (preclínico)", true),
};

// Para qué sirve el órgano (vigésima ronda): la frase y la ficha con la forma del backend
// (`anatomy.HEART_FUNCTION`, ficha `seer-cardiovascular-system`).
const HEART_FUNCTION =
  "El corazón es una bomba muscular que impulsa la sangre por un circuito cerrado de vasos (arterias, venas y capilares); en los capilares la sangre cumple su función de transporte.";
const seerCard = (id: string, title: string, page: string, relevance: string): EvidenceItem => ({
  ...HRP,
  id,
  title,
  source: `National Cancer Institute (NCI, National Institutes of Health), SEER Training Modules, «${title}»`,
  url: `https://training.seer.cancer.gov/anatomy/${page}`,
  organization: "National Cancer Institute",
  evidence_type: "agency_page",
  evidence_type_display: "página de agencia",
  population: "human",
  population_display: "humano",
  not_applicable: ["doi", "evidence_context"],
  unverified: ["date"],
  unverified_display: ["fecha"],
  relevance,
});
const SEER_HEART = seerCard(
  "seer-cardiovascular-system",
  "Introduction to the Cardiovascular System",
  "cardiovascular/",
  "para qué sirven el corazón y la circulación",
);
// Las de las regiones que estas pruebas construyen a partir de otras: cada una con la suya.
const IMMUNE_FUNCTION =
  "Defiende al cuerpo de los microorganismos invasores y de la enfermedad: los órganos linfáticos filtran la linfa para retirar microorganismos y otras partículas extrañas, y contienen linfocitos que destruyen los organismos invasores.";
const SEER_LYMPHATIC = seerCard(
  "seer-lymphatic-system",
  "Introduction to the Lymphatic System",
  "lymphatic/",
  "para qué sirve la defensa del cuerpo",
);
const LIVER_FUNCTION =
  "El hígado tiene muchas funciones, muchas de ellas vitales; entre ellas, fabrica sales biliares y proteínas del plasma.";
const SEER_LIVER = seerCard("seer-digestive-accessory-organs", "Accessory Organs", "digestive/regions/accessory.html", "para qué sirve el hígado");
const BRAIN_FUNCTION =
  "El sistema nervioso, con el cerebro, es el principal sistema de control, regulación y comunicación del cuerpo.";
const SEER_NERVOUS = seerCard("seer-nervous-system", "Introduction to the Nervous System", "nervous/", "para qué sirve el sistema nervioso");
const NO_FUNCTION =
  "No es un órgano ni un sistema del cuerpo: la región reúne la radiación, que llega a todo el cuerpo. No hay una función que describir.";

const DRIVER = "Frecuencia cardiaca: 35 /min, por debajo del límite de peligro (40 /min)";
const TREND = "Frecuencia cardiaca: bajando 3 /min/semana a lo largo de 21 días";
const ACTION = "Repetir la medida en reposo y registrar los síntomas";
const RATIONALE = `cardiovascular (preocupación): ${DRIVER}`;

// El paso RIESGO con la forma de `risk_entity.summary` (backend).
const UNCERTAINTY =
  "EMMA no cuantifica la incertidumbre de este riesgo: no da probabilidad ni intervalo.";
const CARDIO_RISK: AnatomyRisk = {
  risk_id: "cardiovascular",
  display: "Cardiovascular",
  ridge: {
    category: "gravity",
    display: "campos gravitatorios",
    source: { id: "nasa-human-body-in-space", title: "The Human Body in Space", url: null },
  },
  hrp_risk: { id: HRP.id, title: HRP.title, url: HRP.url, evidence_type_display: "riesgo del HRP" },
  uncertainty_statement: UNCERTAINTY,
};

// El contexto externo con la forma de `alert_context.around` (backend), sin alerta.
const CONTEXT_NOTE = "Coincidir en el tiempo con el instante del estado no dice que sea causa de nada.";
const CONTEXT_ITEM = "CO₂ de cabina fuera de su límite normativo (NASA-STD-3001)";
const CONTEXT: AlertContext = {
  label: "correlación temporal, no causa",
  summary: "Registrado dentro de la ventana: 1.",
  anchor: "2026-12-11T00:00:00+00:00",
  anchor_basis: "sin alerta: se toma el instante del estado",
  window_start: "2026-12-10T00:00:00+00:00",
  window_end: "2026-12-11T00:00:00+00:00",
  window_hours_before: 24,
  window_hours_after: 6,
  window_basis: "Ventana de diseño EMMA.",
  mission: {
    mission_day: 40,
    phase: "stable",
    phase_display: "fase estable",
    statement: "Instante del estado: día de misión 40, fase estable, microgravedad.",
  },
  items: [
    {
      kind: "habitat",
      label: "correlación temporal, no causa",
      title: CONTEXT_ITEM,
      detail: null,
      start: "2026-12-10T20:00:00+00:00",
      end: "2026-12-10T22:00:00+00:00",
      timing: "última lectura fuera de límite 2,0 h antes del instante del estado",
      source: "telemetría de cabina, módulo m1",
      value: 6.2,
      value_label: "valor más alejado del límite",
      unit: "mm[Hg]",
    },
  ],
  sources: [
    { kind: "habitat", display: "Hábitat", status: "with_data", status_display: "con dato", found: 1, note: "" },
  ],
  note: CONTEXT_NOTE,
};

const heart: AnatomyRegionState = {
  key: "heart",
  display: "Corazón y circulación",
  domains: ["cardiovascular"],
  note: "Pulso, variabilidad, presión y ortostatismo.",
  level: "concern",
  has_data: true,
  data_note: null,
  state: [{ domain: "cardiovascular", level: "concern", has_data: true, drivers: [DRIVER], risk: CARDIO_RISK }],
  variables: [
    {
      key: "heart-rate",
      display: "Heart rate",
      display_es: "Frecuencia cardiaca",
      unit: "/min",
      decimals: 0,
      domain: "cardiovascular",
      value: 35.4,
      effective: "2026-12-10T23:00:00+00:00",
      observation_type: "measured",
      evidence_context: "simulated",
      contributes: true,
      deviation: {
        key: "heart-rate",
        display: "Heart rate",
        display_es: "Frecuencia cardiaca",
        unit: "/min",
        value: 35,
        effective: "2026-12-10T22:00:00+00:00",
        severity: "severe",
        basis: "danger_limit",
        baseline_median: 61,
        baseline_samples: 336,
        compared_with: "línea base personal",
        danger_limit: 40,
        description: DRIVER,
      },
      trend: {
        direction: "falling",
        significant: true,
        concerning: false,
        slope_per_week: -3,
        span_days: 21,
        points: 504,
        description: TREND,
      },
    },
    {
      key: "body-temperature",
      display: "Body temperature",
      display_es: "Temperatura corporal",
      unit: "Cel",
      decimals: 1,
      domain: "cardiovascular",
      value: 36.64,
      effective: "2026-12-10T23:00:00+00:00",
      observation_type: "measured",
      evidence_context: "simulated",
      contributes: false,
      deviation: null,
      trend: null,
    },
  ],
  unmeasured: [{ key: "orthostatic-drop", display: "Orthostatic drop", display_es: "Caída de la presión sistólica al ponerse en pie", domain: "cardiovascular" }],
  evidence: [
    {
      domain: "cardiovascular",
      amcl_alignment: "EMMA vigila la tendencia y la desviación; no diagnostica la arritmia concreta",
      items: [HRP],
    },
  ],
  recommendations: [
    {
      domain: "cardiovascular",
      action: ACTION,
      rationale: RATIONALE,
      urgency: "soon",
      notify_ground: false,
      evidence: [HRP],
      countermeasure: {
        id: "cv-repeat-rest",
        scope: "crew",
        domain: "cardiovascular",
        ridge: "gravity",
        ridge_display: "Campos de gravedad",
        action: ACTION,
        indication: "Hallazgo cardiovascular",
        resources: ["Wearable"],
        crew_time_minutes: null,
        crew_time_basis: "sin fuente",
        protocol_ref: null,
        followup_checks: ["heart-rate"],
        followup_checks_display: ["Frecuencia cardiaca"],
        followup_window_hours: 24,
        followup_basis: "ventana de demo",
        contraindications_note: null,
        adverse_effects_note: null,
        basis: "demo",
      },
    },
  ],
  recommendations_note: null,
  context: CONTEXT,
  analytes: [],
  level_of: null,
  level_note: null,
  analytes_source: null,
  note_refs: [],
  research: null,
  level_risk: null,
  function: HEART_FUNCTION,
  function_refs: [SEER_HEART],
  function_note: null,
};

const NO_DATA = "Sin lecturas de esta región: no hay estado que valorar. No equivale a nominal.";
const NOTHING_TO_ASSESS = "Sin contramedidas propuestas: no hay lecturas de esta región que valorar.";

const immune: AnatomyRegionState = {
  key: "immune",
  display: "Sistema inmune (todo el cuerpo)",
  domains: ["immune"],
  note: "No es un órgano: recuento, reactivación viral y síntomas.",
  level: null,
  has_data: false,
  data_note: NO_DATA,
  state: [
    {
      domain: "immune",
      level: null,
      has_data: false,
      drivers: [],
      risk: { ...CARDIO_RISK, risk_id: "immune", display: "Inmunitario", hrp_risk: null },
    },
  ],
  variables: [],
  unmeasured: [{ key: "lymphocytes", display: "Lymphocytes", display_es: "Linfocitos (abs.)", domain: "immune" }],
  evidence: [{ domain: "immune", amcl_alignment: "No hay hemograma de uso ordinario a bordo", items: [OSD_288] }],
  recommendations: [],
  recommendations_note: NOTHING_TO_ASSESS,
  context: null,
  analytes: [],
  level_of: null,
  level_note: null,
  analytes_source: null,
  note_refs: [],
  research: null,
  level_risk: null,
  function: IMMUNE_FUNCTION,
  function_refs: [SEER_LYMPHATIC],
  function_note: null,
};

// El hígado (decimoquinta ronda, §5.35.11): una región sin dominio ni nivel propio, que enseña
// sus analitos y dice de quién es el nivel. Los textos son los de `anatomy.py`.
const LEVEL_NOTE = "El nivel es del dominio nutrición.";
const NUTRITION_UNCERTAINTY = "Incertidumbre del riesgo de nutrición, redactada por el backend.";
const LIVER_RECOMMENDATIONS = "Sin contramedidas propias: las del dominio nutrición salen en la región «Aparato digestivo: nutrición».";
const MEDLINEPLUS: EvidenceItem = {
  ...HRP,
  id: "medlineplus-liver-function-tests",
  title: "Liver Function Tests",
  source: "MedlinePlus, National Library of Medicine (actualizada el 5 de diciembre de 2023)",
  url: "https://medlineplus.gov/lab-tests/liver-function-tests/",
  evidence_type: "agency_page",
  evidence_type_display: "página de agencia",
  relevance: "qué analitos son pruebas de función hepática",
};
// La capa de investigación del hígado (§5.37.16; con rótulo de población e instalación desde
// §5.39.16), con los textos de `anatomy.py` y la forma de toda cita: el estudio en ratón con su
// población, su rótulo y su salvedad.
const RESEARCH_NOTE =
  "Lo observado en estudios con otras personas o con animales, no medido en este tripulante; cada ficha dice su población. No afirma que le esté ocurriendo y no cuenta en el nivel ni en las alertas.";
const HAYSLIP_CAVEAT = "Estudio preclínico: el experimento y el tratamiento son en hígado de ratón.";
const HAYSLIP_LABEL = "humanos y modelo animal: el experimento es en hígado de ratón, en Tierra";
const HAYSLIP: ResearchEvidenceItem = {
  ...OSD_288,
  id: "hayslip-2026",
  title: "Space radiation and microgravity as models of accelerated aging",
  source: "Hayslip N. et al., GeroScience 2026",
  url: "https://pubmed.ncbi.nlm.nih.gov/42337157/",
  evidence_type: "journal_article",
  evidence_type_display: "artículo de revista",
  population: "human_and_animal",
  population_display: "humano y animal",
  notes: HAYSLIP_CAVEAT,
  scope_caveat: HAYSLIP_CAVEAT,
  scope_in_view: HAYSLIP_CAVEAT,
  relevance: "un mecanismo en hígado de ratón, no medido en este tripulante",
  population_label: HAYSLIP_LABEL,
};
const liver: AnatomyRegionState = {
  ...immune,
  key: "liver",
  display: "Hígado",
  domains: [],
  note: "No es un dominio de EMMA: sus analitos cuentan en el dominio nutrición.",
  level: null,
  has_data: true,
  data_note: null,
  state: [],
  variables: [
    {
      key: "alt",
      display: "Alanine aminotransferase",
      display_es: "ALT",
      unit: "U/L",
      decimals: 0,
      domain: "nutrition",
      value: 30,
      effective: "2026-12-10T08:00:00+00:00",
      observation_type: "measured",
      evidence_context: "ground",
      contributes: false,
      deviation: null,
      trend: null,
    },
  ],
  unmeasured: [{ key: "ast", display: "Aspartate aminotransferase", display_es: "AST", domain: "nutrition" }],
  evidence: [],
  recommendations: [],
  recommendations_note: LIVER_RECOMMENDATIONS,
  analytes: ["alt", "ast"],
  level_of: "nutrition",
  level_note: LEVEL_NOTE,
  analytes_source: MEDLINEPLUS,
  research: { note: RESEARCH_NOTE, items: [HAYSLIP], facility: null },
  level_risk: { ...CARDIO_RISK, risk_id: "nutrition", display: "Nutrición", uncertainty_statement: NUTRITION_UNCERTAINTY },
  function: LIVER_FUNCTION,
  function_refs: [SEER_LIVER],
};

// El cerebro (§5.39.16): la capa con el informe del SNC, rotulado humanos y modelo animal, y
// detrás la instalación donde se hace esa investigación (el NSRL), con su propia frase.
const FACILITY_NOTE =
  "Dónde se hace parte de esa investigación: la ficha es de una instalación, no de un estudio, y no tiene población.";
const CNS_CAVEAT =
  "Informe de evidencia del riesgo del sistema nervioso central por radiación: lo humano es sobre todo de pacientes de radioterapia. No mide nada en este tripulante.";
const CNS_LABEL =
  "humanos y modelo animal: lo humano es sobre todo de pacientes de radioterapia y expuestos en Tierra; lo animal, sobre todo ratones y ratas irradiados en aceleradores";
const CNS: ResearchEvidenceItem = {
  ...HAYSLIP,
  id: "hrp-cns-radiation-evidence-report",
  title: "Evidence Report: Risk of Acute and Late Central Nervous System Effects from Radiation Exposure",
  source: "Nelson GA, Simonsen L, Huff JL. NASA Human Research Program (2016)",
  url: "https://ntrs.nasa.gov/citations/20160004368",
  evidence_type: "evidence_report",
  evidence_type_display: "informe de evidencia",
  evidence_context: null,
  outside_enum: ["evidence_context"],
  outside_enum_display: ["entorno del estudio"],
  notes: CNS_CAVEAT,
  scope_caveat: CNS_CAVEAT,
  scope_in_view: CNS_CAVEAT,
  relevance: "qué se sabe de la radiación espacial y el sistema nervioso central",
  population_label: CNS_LABEL,
  grade: grade("desconocido: no clasificable desde el registro"),
};
const NSRL_CAVEAT = "Página institucional del laboratorio, no un estudio.";
const NSRL: EvidenceItem = {
  ...MEDLINEPLUS,
  id: "bnl-nsrl",
  title: "NASA Space Radiation Laboratory",
  source: "Brookhaven National Laboratory · NASA Space Radiation Laboratory (NSRL)",
  url: "https://www.bnl.gov/nsrl/",
  organization: "Brookhaven National Laboratory",
  population: null,
  population_display: "no aplica",
  not_applicable: ["doi", "evidence_context", "population"],
  unverified: ["date"],
  unverified_display: ["fecha"],
  notes: NSRL_CAVEAT,
  scope_caveat: NSRL_CAVEAT,
  scope_in_view: NSRL_CAVEAT,
  relevance: "dónde se irradia con haces de iones pesados que simulan los rayos cósmicos",
};
const brain: AnatomyRegionState = {
  ...heart,
  key: "brain",
  display: "Cerebro: sueño, vigilancia, estado de ánimo",
  domains: ["behavioral"],
  note: "El dominio conductual: sueño, ritmo circadiano, PVT y autoinforme de ánimo.",
  research: { note: RESEARCH_NOTE, items: [CNS], facility: { note: FACILITY_NOTE, item: NSRL } },
  function: BRAIN_FUNCTION,
  function_refs: [SEER_NERVOUS],
};

function render(region: AnatomyRegionState, pastUntil: string | null = null): string {
  return renderToStaticMarkup(
    createElement(RegionChain, {
      region,
      status,
      operator: "CMO",
      following: new Set<string>(),
      onAdopt: async () => {},
      pastUntil,
    }),
  );
}

/** El HTML escapa las comillas y los ampersands; los textos de prueba no llevan otros. */
const shown = (text: string) => text.replaceAll("&", "&amp;").replaceAll('"', "&quot;");

describe("especificacion §10: la cadena entera, en el propio panel", () => {
  const html = render(heart);

  it("recorre estado → variables → evidencia → tendencia → riesgo → contramedida (KB §11.1), y el contexto al final", () => {
    const steps = [
      "Estado",
      "Variables",
      "Evidencia",
      "Tendencia",
      "Riesgo",
      "Contramedida",
      "Contexto externo",
    ].map((step) =>
      html.indexOf(`<section aria-label="${step}">`),
    );
    expect(steps.every((position) => position >= 0)).toBe(true);
    expect([...steps].sort((a, b) => a - b)).toEqual(steps);
  });

  it("ensena el nivel que da el backend, con su palabra y su pictograma", () => {
    expect(html).toContain(LEVELS.concern.label);
    expect(html).toContain(`data-pictogram="${LEVELS.concern.pictogram}"`);
    expect(html).not.toContain(LEVELS.nominal.label);
  });

  it("no redacta: motivos, tendencia, alcance y contramedida son los textos del backend", () => {
    for (const text of [DRIVER, TREND, ACTION, RATIONALE, HRP_RELEVANCE, heart.note]) {
      expect(html).toContain(shown(text));
    }
    expect(html).toContain(shown(heart.evidence[0]?.amcl_alignment ?? "?"));
  });

  it("las cifras pasan por format.ts: sin decimales de mas, coma decimal y unidad legible", () => {
    expect(html).toContain('<span class="num">35</span> /min');
    expect(html).toContain('<span class="num">36,6</span> °C');
    expect(html).toContain("MET 39/23:00:00");
  });

  it("rotula de donde sale cada dato y que variable cuenta para el nivel", () => {
    expect(html).toContain("MEDIDO");
    expect(html).toContain("simulado");
    expect(html.match(/cuenta en el nivel/g)).toHaveLength(1);
  });

  it("dice por que cuenta: la lectura que conto el motor con su instante, no el ultimo valor", () => {
    // El ultimo valor (35,4 a las 23:00) y la lectura contada (35 a las 22:00) son dos datos.
    expect(html).toContain(
      `<p class="secondary">${shown(DRIVER)} <span class="num">(MET 39/22:00:00)</span></p>`,
    );
  });

  it("una deriva que no preocupa no se da como motivo del nivel", () => {
    expect(html).not.toContain(`<p class="secondary">${shown(TREND)}</p>`);
    const drifting = structuredClone(heart);
    const [first] = drifting.variables;
    if (first?.trend) first.trend.concerning = true;
    expect(render(drifting)).toContain(`<p class="secondary">${shown(TREND)}</p>`);
  });

  it("dice que variable no tiene tendencia calculada y cuales no tienen lectura", () => {
    // Dato ausente: anillo punteado en cian junto a la frase, sin glifo de texto.
    // La variable se nombra con el dibujo de su familia (`<IndicatorName>`), sin color.
    expect(html).toMatch(
      /<span class="mark"><svg [^>]*data-pictogram="[a-z-]+">.*?<\/svg>Temperatura corporal<\/span>: <span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted">.*?<\/svg>sin tendencia calculada<\/span>/,
    );
    expect(html).not.toContain("◌");
    expect(html).toContain("Caída de la presión sistólica al ponerse en pie");
  });

  it("cada titulo lleva su signo: el dominio en la region, el concepto en cada eslabon (§5.33.3)", () => {
    // La region, con el dibujo de su dominio, como en la lista y en la silueta.
    expect(html).toMatch(/<h3><svg [^>]*data-pictogram="domain-cardiovascular">.*?<\/svg>Corazón y circulación<\/h3>/);
    const titles: [string, string][] = [
      ["Estado", "toggle"],
      ["Variables", "ruler"],
      ["Evidencia", "sheet-lines"],
      ["Tendencia", "chart-line"],
      ["Riesgo", "list-lines"],
      ["Contramedida", "signpost"],
      ["Contexto externo", "house"],
    ];
    for (const [word, pictogram] of titles) {
      expect(html).toMatch(new RegExp(`<h4><svg [^>]*data-pictogram="${pictogram}">.*?</svg>${word}</h4>`));
    }
  });

  it("los dominios y las variables se nombran con su dibujo, y lo que no tiene lectura va en su plegable", () => {
    // El dominio en el estado y en la evidencia, con su pictograma y sin color.
    expect(html).toMatch(/<strong><span class="mark"><svg [^>]*data-pictogram="domain-cardiovascular">/);
    expect(html).toMatch(
      /<p class="secondary"><span class="mark"><svg [^>]*data-pictogram="domain-cardiovascular">.*?<\/svg>Cardiovascular<\/span>: EMMA vigila/,
    );
    expect(html).toMatch(/<strong><span class="mark"><svg [^>]*>.*?<\/svg>Frecuencia cardiaca<\/span><\/strong>/);
    // «Sin lectura (n)»: el plegable con el anillo punteado de lo que falta.
    expect(html).toMatch(
      /<details><summary><svg [^>]*data-pictogram="ring-dotted">.*?<\/svg>Sin lectura \(<span class="num">1<\/span>\)<\/summary>/,
    );
    expect(html).toMatch(/<li><span class="mark"><svg [^>]*>.*?<\/svg>Caída de la presión sistólica al ponerse en pie<\/span><\/li>/);
  });

  it("la serie elegida lleva el pictograma de «elegido» junto a la palabra, y las demas no", () => {
    // La primera variable que cuenta en el nivel se abre al entrar (`charted`).
    const pressed = html.match(/<button class="command" aria-pressed="true">(.*?)<\/button>/g) ?? [];
    expect(pressed).toHaveLength(1);
    expect(pressed[0]).toContain('data-pictogram="ring-dot"');
    expect(pressed[0]).toContain("Serie");
    const unpressed = html.match(/<button class="command" aria-pressed="false">(.*?)<\/button>/g) ?? [];
    expect(unpressed).toHaveLength(1);
    expect(unpressed[0]).not.toContain("data-pictogram");
    expect(html).not.toContain("●");
  });

  it("la evidencia lleva su nivel", () => {
    expect(html).toContain(`Nivel: ${HRP.grade.label}`);
  });
});

describe("una region sin lecturas", () => {
  const html = render(immune);

  it("dice 'sin datos' en cian y con la nota del backend; no aparece como nominal", () => {
    expect(html).toContain('<span class="mark level c-cyan">');
    expect(html).toContain('data-pictogram="ring-dotted"');
    expect(html).toContain("Sin datos");
    expect(html).toContain(shown(NO_DATA));
    expect(html).not.toContain(LEVELS.nominal.label);
    expect(html).not.toContain(`data-pictogram="${LEVELS.nominal.pictogram}"`);
  });

  it("la nota de datos y la de la serie llevan el anillo punteado en cian, no un glifo de texto", () => {
    expect(html).toMatch(
      new RegExp(`<span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted">.*?</svg>${shown(NO_DATA)}</span>`),
    );
    expect(html).toMatch(
      /<span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted">.*?<\/svg>Sin lecturas: no hay serie que mirar\.<\/span>/,
    );
    expect(html).not.toContain("◌");
  });

  it("ensena la nota del backend en vez de contramedidas", () => {
    expect(html).toContain(shown(NOTHING_TO_ASSESS));
    expect(html).not.toContain("Recomendación del sistema");
  });

  it("la evidencia de raton conserva su alcance, en amarillo, y su nivel preclinico", () => {
    // El alcance es una advertencia: amarillo con el triangulo delante (§5.33.5).
    expect(html).toContain(`</svg>Alcance: ${shown(OSD_288_CAVEAT)}</span></p>`);
    expect(html).toMatch(/<p><span class="mark c-yellow"><svg [^>]*data-pictogram="shape-triangle"><[^]*?<\/svg>Alcance: /);
    // El nivel con su pictograma (§5.32.5, `evidence/sourceMarks.ts`): matraz en amarillo.
    expect(html).toMatch(
      /<span class="mark c-yellow" title=""><svg [^>]*data-pictogram="flask"><[^]*?<\/svg>Nivel: modelo animal \(preclínico\)<\/span>/,
    );
    expect(html).toContain(shown(OSD_288_RELEVANCE));
  });

  it("dice que es la fuente: un estudio en animales lleva su poblacion en amarillo", () => {
    // La cadena pinta cada fuente con la misma ficha que las recomendaciones (`EvidenceEntry`):
    // clase de documento, poblacion y lo que el registro aun no ha verificado.
    expect(html).toContain("Tipo: conjunto de datos");
    expect(html).toMatch(
      /<span class="mark c-yellow"><svg [^>]*data-pictogram="paw"><[^]*?<\/svg>población: animal<\/span>/,
    );
    // Lo sin verificar, gris con la interrogacion: el color no va solo (§5.33.5).
    expect(html).toMatch(
      /<span class="mark c-gray"><svg [^>]*data-pictogram="question"><[^]*?<\/svg>sin verificar: DOI, fecha<\/span>/,
    );
  });
});

describe("KB §11.1: el paso RIESGO y el contexto externo", () => {
  const html = render(heart);

  it("el riesgo es el del backend: RIDGE con su dibujo, ficha del HRP e incertidumbre, sin contramedida que lo traiga", () => {
    const bare = render({ ...heart, recommendations: [] });
    for (const out of [html, bare]) {
      expect(out).toMatch(/<svg [^>]*data-pictogram="ridge-gravity">.*?<\/svg>RIDGE: campos gravitatorios<\/span>/);
      expect(out).toContain(shown(HRP.title));
      expect(out).toContain(shown(UNCERTAINTY));
    }
    // El rótulo de la ficha lleva su signo (la hoja de la evidencia) y la ficha, su clase.
    expect(html).toMatch(/<span><svg [^>]*data-pictogram="sheet-lines">.*?<\/svg>Ficha del riesgo<\/span>/);
    expect(html).toContain("· riesgo del HRP");
  });

  it("sin ficha del riesgo lo dice con el anillo de lo que falta, en cian", () => {
    expect(render(immune)).toMatch(
      /<span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted">.*?<\/svg>Sin ficha del riesgo para este dominio\.<\/span>/,
    );
  });

  it("el contexto externo es el de una alerta: sus textos, su rótulo de no causa y cada fuente", () => {
    for (const text of [CONTEXT_NOTE, CONTEXT_ITEM, CONTEXT.mission.statement, CONTEXT.window_basis]) {
      expect(html).toContain(shown(text));
    }
    expect(html).toContain("<em>correlación temporal, no causa</em>");
    expect(html).toContain("Hábitat: con dato");
    expect(html).toContain('<span class="num">6,2</span>');
  });
});

describe("la cadena en un momento pasado (recalculada, sin asiento)", () => {
  const now = render(heart);
  const past = render(heart, "2026-11-14T23:59:59+00:00");

  it("el nivel va con su palabra pero sin la insignia de un nivel vigente", () => {
    expect(now).toContain(`data-pictogram="${LEVELS.concern.pictogram}"`);
    expect(past).not.toContain(`data-pictogram="${LEVELS.concern.pictogram}"`);
    expect(past).toMatch(
      new RegExp(`<span class="mark level secondary"><svg [^>]*data-pictogram="refresh">.*?</svg><span class="c-text">${LEVELS.concern.label}</span></span>`),
    );
  });

  it("no ofrece adoptar nada: se adopta sobre el estado de ahora", () => {
    expect(now).toContain("Adoptar y seguir");
    expect(past).not.toContain("Adoptar y seguir");
    // La contramedida sigue a la vista, con su texto del backend.
    expect(past).toContain(shown(ACTION));
  });

  it("sin datos sigue siendo sin datos, en cian", () => {
    expect(render(immune, "2026-11-14T23:59:59+00:00")).toContain('<span class="mark level c-cyan">');
  });
});

describe("un nivel que la interfaz no conoce", () => {
  it("no se pinta: falla", () => {
    expect(() => render({ ...heart, level: "severe", state: [{ ...heart.state[0]!, level: "severe" }] })).toThrow(
      RangeError,
    );
  });
});

describe("una region sin nivel propio (el higado, §5.35.11)", () => {
  const html = render(liver);

  it("el titulo lleva el dibujo de su organo, no el punto de «desconocido»", () => {
    expect(html).toMatch(/<h3[^>]*>.*?data-pictogram="liver".*?Hígado.*?<\/h3>/);
  });

  it("dice de quien es el nivel con la frase del backend, sin color ni insignia de nivel ni «sin datos»", () => {
    expect(html).toContain(LEVEL_NOTE);
    expect(html).toContain('<span class="mark level secondary"><svg');
    expect(html).toContain('data-pictogram="domain-nutrition"');
    expect(html).not.toMatch(/class="mark level c-/);
    for (const style of Object.values(LEVELS)) expect(html).not.toContain(`>${style.label}<`);
    expect(html).not.toContain("Sin datos");
  });

  it("ensena sus analitos y la fuente de la lista, y la nota de contramedidas del backend", () => {
    expect(html).toContain("ALT");
    expect(html).toContain("Liver Function Tests");
    expect(html).toContain(LIVER_RECOMMENDATIONS);
  });

  it("el paso RIESGO es el del dominio de su nivel, con la frase que lo dice", () => {
    const [, risk = ""] = html.split('<section aria-label="Riesgo">');
    const [step = ""] = risk.split("</section>");
    expect(step).toContain(LEVEL_NOTE);
    expect(step).toContain(NUTRITION_UNCERTAINTY);
    expect(step).toContain("RIDGE:");
  });
});

describe("la capa de evidencia de investigación (§5.37.16)", () => {
  const html = render(liver);
  const [, after = ""] = html.split('<section aria-label="Evidencia de investigación">');
  const [layer = ""] = after.split("</section>");

  it("va en su propia sección, después de la evidencia y antes de la tendencia", () => {
    const at = html.indexOf('<section aria-label="Evidencia de investigación">');
    expect(at).toBeGreaterThan(html.indexOf('<section aria-label="Evidencia">'));
    expect(at).toBeLessThan(html.indexOf('<section aria-label="Tendencia">'));
  });

  it("lleva el dibujo de «modelo animal», la frase del backend tal cual y la ficha con su salvedad de ratón", () => {
    expect(layer).toMatch(/<h4[^>]*>.*?data-pictogram="flask".*?Evidencia de investigación<\/h4>/);
    expect(layer).toContain(RESEARCH_NOTE);
    expect(layer).toContain(HAYSLIP.title);
    expect(layer).toContain(HAYSLIP_CAVEAT);
    // No entra en la evidencia del dominio: allí solo está la fuente de la lista de analitos.
    const [, evidence = ""] = html.split('<section aria-label="Evidencia">');
    const [domainEvidence = ""] = evidence.split("</section>");
    expect(domainEvidence).not.toContain(HAYSLIP.title);
    expect(domainEvidence).toContain(MEDLINEPLUS.title);
  });

  it("la frase va sin color: no es un estado ni un dato que falta", () => {
    expect(layer).toContain(`<p class="secondary">${RESEARCH_NOTE}</p>`);
  });

  it("una región sin capa no la enseña", () => {
    expect(render(heart)).not.toContain("Evidencia de investigación");
  });

  it("el título no se repite en la frase", () => {
    expect(layer.split("Evidencia de investigación").length).toBe(2);
  });

  // Decimonovena ronda (§5.39.16): el rótulo de población de cada ficha y la instalación.
  it("cada ficha lleva encima su rótulo de población, tal cual, con la marca de su clase en amarillo", () => {
    const label = layer.indexOf(shown(HAYSLIP_LABEL));
    expect(label).toBeGreaterThan(-1);
    expect(label).toBeLessThan(layer.indexOf(HAYSLIP.title));
    // La misma marca que `SourceFacts` da a «humano y animal»: la persona y la huella, en amarillo.
    const [mark = ""] = layer.slice(0, label).split("<p>").slice(-1);
    expect(mark).toContain('data-pictogram="person-paw"');
    expect(mark).toContain("c-yellow");
    // Y la ficha debajo, con la forma de toda cita: su salvedad sigue allí.
    expect(layer).toContain(HAYSLIP_CAVEAT);
  });

  it("una región con capa pero sin instalación no enseña la frase de la instalación", () => {
    expect(layer).not.toContain(FACILITY_NOTE);
    expect(layer).not.toContain(NSRL.title);
  });

  it("el cerebro enseña dónde se hace esa investigación detrás de los estudios, con su frase y sin contarla entre ellos", () => {
    const html = render(brain);
    const [, after = ""] = html.split('<section aria-label="Evidencia de investigación">');
    const [brainLayer = ""] = after.split("</section>");
    const study = brainLayer.indexOf(CNS.title);
    const note = brainLayer.indexOf(`<p class="secondary">${FACILITY_NOTE}</p>`);
    const facility = brainLayer.indexOf(NSRL.title);
    expect(study).toBeGreaterThan(-1);
    expect(note).toBeGreaterThan(study);
    expect(facility).toBeGreaterThan(note);
    // El rótulo del informe, con su marca; la instalación no lleva rótulo de población: no es un estudio.
    expect(brainLayer).toContain(shown(CNS_LABEL));
    expect(brainLayer.slice(note)).not.toContain("humanos");
    expect(brainLayer.slice(note)).toContain("población: no aplica");
    // Los estudios van en una lista y la instalación en otra: dos listas de evidencia.
    expect(brainLayer.split('<ul class="evidence">').length).toBe(3);
  });
});

describe("para qué sirve el órgano (el reto: «its function and health status»)", () => {
  const html = render(heart);
  const [, section = ""] = html.split('<section aria-label="Función">');
  const functionPart = section.split("</section>")[0] ?? "";

  it("va después de la frase de la región y antes del estado, con su signo", () => {
    const at = html.indexOf('<section aria-label="Función">');
    expect(at).toBeGreaterThan(html.indexOf(shown(heart.note)));
    expect(at).toBeLessThan(html.indexOf('<section aria-label="Estado">'));
    expect(html).toMatch(/<h4><svg [^>]*data-pictogram="figure-dot">.*?<\/svg>Función<\/h4>/);
  });

  it("enseña la frase del backend tal cual y su ficha, con la lista de evidencia de siempre", () => {
    expect(functionPart).toContain(`<p>${shown(HEART_FUNCTION)}</p>`);
    expect(functionPart).toContain(SEER_HEART.title);
    expect(functionPart).toContain(SEER_HEART.relevance);
    expect(functionPart).toContain('<ul class="evidence">');
  });

  it("sin órgano que describir enseña la frase del backend que lo dice, sin color y sin ficha", () => {
    const bare = render({ ...heart, function: null, function_refs: [], function_note: NO_FUNCTION });
    const [, part = ""] = bare.split('<section aria-label="Función">');
    const own = part.split("</section>")[0] ?? "";
    expect(own).toContain(`<p class="secondary">${shown(NO_FUNCTION)}</p>`);
    expect(own).not.toContain('<ul class="evidence">');
    expect(own).not.toMatch(/c-cyan|c-gray/);
  });

  it("sin función ni frase que lo diga no pinta una sección vacía", () => {
    const empty = render({ ...heart, function: null, function_refs: [], function_note: null });
    expect(empty).not.toContain('<section aria-label="Función">');
    expect(empty).not.toContain("Función</h4>");
  });

  it("cada región enseña su propia función, no la de la región de la que sale el ejemplo", () => {
    expect(render(brain)).toContain(shown(BRAIN_FUNCTION));
    expect(render(brain)).not.toContain(shown(HEART_FUNCTION));
    expect(render(liver)).toContain(shown(LIVER_FUNCTION));
    expect(render(immune)).toContain(SEER_LYMPHATIC.title);
  });
});
