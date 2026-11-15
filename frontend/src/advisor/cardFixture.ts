import type {
  CoAdoptionNote,
  Countermeasure,
  CountermeasureEffects,
  PriorAdoption,
  PriorResponse,
  Recommendation,
  ResourceRow,
  ResourceStatus,
} from "../lib/api";

/**
 * Una recomendacion «llena» para las pruebas de la tarjeta plegada: con contramedida, recursos
 * (uno declarado no disponible, con nota, y uno sin declarar), respuesta previa de dos adopciones
 * y decision firmada. Los textos imitan los del backend y cada uno es distinto de los demas, para
 * poder buscar donde queda cada cual. Solo lo usan las pruebas.
 */

export const TEXTS = {
  action: "Repetir la ecografía en ambos ojos.",
  rationale: "Diámetro de la vaina del nervio óptico por encima de lo habitual.",
  decisionText: "No adoptada el 2026-12-08 10:00 UTC (CDR): sonda averiada.",
  decisionMeaning: "La recomendación sigue vigente: decidir que no no la retira.",
  ridge: "Campos de gravedad",
  resourcesAsked: "ecógrafo · operador entrenado",
  crewTimeBasis: "sin fuente",
  followupBasis: "diseño EMMA",
  contraindications: "Pendiente de revisión médica: ninguna contraindicación escrita.",
  adverse: "Molestia ocular leve con la presión de la sonda.",
  label: "declarado por una persona; EMMA no lleva inventario",
  resourceText: "Consta como no disponible: ecógrafo. Sin declarar: operador entrenado.",
  resourceCaveat:
    "Sin declarar no es disponible: de un recurso del que nadie ha declarado nada, EMMA no sabe " +
    "si está a bordo ni si funciona. La contramedida se ofrece igual: si se puede hacer lo valora " +
    "una persona.",
  declarerNote: "sonda averiada desde el día 40",
  unavailableWord: "declarado no disponible",
  undeclaredWord: "sin declarar",
  priorSummary: "Se ha adoptado 2 veces para este tripulante; la última, el 2026-12-02 08:00 UTC (CDR).",
  priorCaveat: "Es lo que pasó después, no una prueba de que fuera por la contramedida.",
  priorBasis: "La evaluación compara con el nivel que guardó el cierre.",
  lastState: "Se cerró el 2026-12-04 08:00 UTC (CDR): motivo 2",
  lastChecks: "Seguía Diámetro de la vaina. Se repitió después de adoptarla (2).",
  lastEvaluation: "Texto de evaluación 2.",
  earlierAdopted: "Adoptada el 2026-12-01 08:00 UTC (CDR).",
  earlierEvaluation: "Texto de evaluación 1.",
} as const;

/**
 * Los efectos (§5.39.17): textos que imitan los del backend, cada uno distinto de los demás. Aparte
 * de `TEXTS` porque `fullRecommendation` no los lleva por defecto: la medida de la tarjeta plegada
 * (`foldedCard.test.ts`) se tomó sin ellos, y las pruebas de los efectos los añaden a propósito.
 */
export const EFFECTS_TEXTS = {
  benefit: "Beneficio esperado: sobre el dominio neuro-ocular, el que trata. Sin magnitud.",
  adverseWhere: "Presión intraocular",
  adverseEffectText: "La sonda eleva la presión mientras se apoya.",
  adverseBasis: "La nota de efectos de la propia entrada (diseño EMMA).",
  notDeclared: "No declarado: la entrada no escribe ningún efecto adverso, y no escrito no es no tiene.",
  coAdopted: "Adoptada junto con «Proteger el periodo de sueño.»: ninguna fuente leída dice cómo interactúan.",
  coAdoptedConditional:
    "Si se adopta, irá junto con «Proteger el periodo de sueño.», en seguimiento: ninguna fuente leída dice cómo interactúan.",
  coAdoptionBasis: "La nota de co-adopción sale de los seguimientos abiertos de este tripulante, no de ninguna fuente.",
} as const;

const coAdoptionNote = (adopted: boolean): CoAdoptionNote => ({
  countermeasure_id: "bh-protect-sleep",
  action: "Proteger el periodo de sueño.",
  adoption_index: 7,
  adopted_at: "2026-12-09T08:00:00+00:00",
  adopted,
  text: adopted ? EFFECTS_TEXTS.coAdopted : EFFECTS_TEXTS.coAdoptedConditional,
  source: null,
});

/** Los efectos de una contramedida que declara uno, con una nota de co-adopción. */
export const effectsOf = (over: Partial<CountermeasureEffects> = {}): CountermeasureEffects => ({
  countermeasure_id: "sans-repeat-both-eyes",
  benefit: {
    domain: "neuro-ocular",
    domain_display: "neuro-ocular",
    parameter: null,
    parameter_display: null,
    text: EFFECTS_TEXTS.benefit,
  },
  adverse_declared: true,
  adverse: [
    {
      affects: "indicator",
      key: "iop",
      display: EFFECTS_TEXTS.adverseWhere,
      text: EFFECTS_TEXTS.adverseEffectText,
      basis: EFFECTS_TEXTS.adverseBasis,
    },
  ],
  adverse_text: null,
  co_adopted: [coAdoptionNote(true)],
  co_adoption_basis: EFFECTS_TEXTS.coAdoptionBasis,
  ...over,
});

/** Los efectos de una contramedida que no declara ninguno, sin otra adoptada a la vez. */
export const notDeclaredEffects = (): CountermeasureEffects =>
  effectsOf({
    adverse_declared: false,
    adverse: [],
    adverse_text: EFFECTS_TEXTS.notDeclared,
    co_adopted: [],
  });

/** Los efectos con la nota de co-adopción en condicional: esta recomendación no está adoptada. */
export const conditionalCoAdoption = (): CountermeasureEffects =>
  effectsOf({ co_adopted: [coAdoptionNote(false)] });

const row = (over: Partial<ResourceRow> = {}): ResourceRow => ({
  key: "ultrasound-scanner",
  name: "ecógrafo",
  state: "undeclared",
  state_display: TEXTS.undeclaredWord,
  since: null,
  note: null,
  declared_by: null,
  ledger_index: null,
  recorded: null,
  ...over,
});

export const unavailableItem = (description = "ecógrafo"): ResourceStatus["items"][number] => ({
  ...row({
    state: "unavailable",
    state_display: TEXTS.unavailableWord,
    since: "2026-12-08T12:00:00+00:00",
    note: TEXTS.declarerNote,
    declared_by: "CDR",
    ledger_index: 40,
  }),
  description,
});

export const undeclaredItem = (): ResourceStatus["items"][number] => ({
  ...row({ key: "trained-operator", name: "operador entrenado" }),
  description: "operador entrenado",
});

export const availableItem = (): ResourceStatus["items"][number] => ({
  ...row({ state: "available", state_display: "declarado disponible" }),
  description: "ecógrafo",
});

export const resourceStatusOf = (over: Partial<ResourceStatus> = {}): ResourceStatus => ({
  state: "some-unavailable",
  label: TEXTS.label,
  items: [unavailableItem(), undeclaredItem()],
  unavailable: ["ecógrafo"],
  undeclared: ["operador entrenado"],
  text: TEXTS.resourceText,
  caveat: TEXTS.resourceCaveat,
  ...over,
});

export const allAvailable = (): ResourceStatus =>
  resourceStatusOf({
    state: "all-available",
    items: [availableItem()],
    unavailable: [],
    undeclared: [],
    text: "Todos los recursos que pide constan declarados disponibles.",
    caveat: null,
  });

const adoption = (index: number): PriorAdoption => ({
  adoption_index: index,
  adopted_at: `2026-12-0${index}T08:00:00+00:00`,
  adopted_by: "CDR",
  adopted_text: `Adoptada el 2026-12-0${index} 08:00 UTC (CDR).`,
  level_at_adoption: "concern",
  state: "closed",
  state_text: `Se cerró el 2026-12-0${index + 2} 08:00 UTC (CDR): motivo ${index}`,
  closed_by: "CDR",
  closed_reason: `motivo ${index}`,
  followup_checks_display: ["Diámetro de la vaina"],
  repeated_checks_display: ["Diámetro de la vaina"],
  checks_text: `Seguía Diámetro de la vaina. Se repitió después de adoptarla (${index}).`,
  evaluation: { outcome: "unchanged", text: `Texto de evaluación ${index}.` },
  evaluation_text: `Texto de evaluación ${index}.`,
});

export const priorOf = (count: number): PriorResponse => {
  const adoptions = Array.from({ length: count }, (_, index) => adoption(index + 1));
  const last = adoptions[adoptions.length - 1] ?? null;
  return {
    state: last === null ? "none" : "closed",
    count,
    text: last === null ? "Sin adopciones anteriores de esta contramedida." : TEXTS.priorSummary,
    caveat: TEXTS.priorCaveat,
    evaluation_basis: last === null ? null : TEXTS.priorBasis,
    last,
    adoptions,
  };
};

export const measureOf = (over: Partial<Countermeasure> = {}): Countermeasure => ({
  id: "sans-repeat-both-eyes",
  scope: "crew",
  domain: "sans",
  ridge: "gravity",
  ridge_display: TEXTS.ridge,
  action: TEXTS.action,
  indication: "i",
  resources: ["ecógrafo", "operador entrenado"],
  resources_note: null,
  crew_time_minutes: null,
  crew_time_basis: TEXTS.crewTimeBasis,
  protocol_ref: null,
  followup_checks: [],
  followup_checks_display: [],
  followup_window_hours: 48,
  followup_basis: TEXTS.followupBasis,
  contraindications_note: null,
  contraindications_display: TEXTS.contraindications,
  adverse_effects_note: TEXTS.adverse,
  basis: "demo",
  ...over,
});

export const fullRecommendation = (over: Partial<Recommendation> = {}): Recommendation => ({
  domain: "sans",
  action: TEXTS.action,
  rationale: TEXTS.rationale,
  urgency: "soon",
  notify_ground: true,
  evidence: [],
  countermeasure: measureOf(),
  decision: null,
  resource_status: resourceStatusOf(),
  prior_response: priorOf(2),
  ...over,
});
