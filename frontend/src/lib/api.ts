/**
 * Cliente de la API de EMMA.
 *
 * Los tipos copian la forma real de las respuestas (`backend/app/api/routes.py`).
 * La interfaz no redacta texto clinico: resumen, motivos y recomendaciones llegan
 * escritos del backend y se muestran tal cual (invariante 7 de CLAUDE.md).
 */

import { adoptLevelLabels } from "./levels";

/**
 * Una fuente citada: la ficha del registro unico del backend (`app/evidence/registry.py`,
 * especificacion §3 EvidenceRef) mas el motivo por el que se cita aqui.
 *
 * Un campo en `null` no es un cero: o esta en `unverified` (nadie lo ha leido en la fuente) o
 * en `not_applicable` (no procede para ese documento) o en `outside_enum` (se leyo y ningun valor
 * del enumerado lo cubre; `notes` dice por que). La interfaz no lo rellena.
 */
export interface EvidenceItem {
  /** Identificador estable de la ficha: el mismo en toda la API. */
  id: string;
  title: string;
  source: string;
  url: string | null;
  doi: string | null;
  pmid: string | null;
  organization: string | null;
  /** ISO 8601 con la precision de la fuente: "2017", "2017-06" o "2023-11-14". */
  date: string | null;
  /** Clase de documento. El diseño del estudio va en `grade`. */
  evidence_type: string | null;
  evidence_type_display: string;
  /** Entorno del estudio: el enumerado de las observaciones (`lib/provenance.ts`). */
  evidence_context: string | null;
  /** Sobre quien se midio. Un raton en la ISS es entorno "iss" y poblacion "animal". */
  population: "human" | "animal" | "human_and_animal" | null;
  population_display: string;
  /** La salvedad de alcance de la fuente (lo mismo que `scope_caveat`). */
  notes: string | null;
  not_applicable: string[];
  /** Campos con enumerado leidos en la fuente que ningun valor cubre (un estudio que junta entornos). */
  outside_enum: string[];
  outside_enum_display: string[];
  unverified: string[];
  unverified_display: string[];
  /** Para que se cita aqui; `null` si el texto que la acompaña ya lo dice. */
  relevance: string | null;
  scope_caveat: string | null;
  /**
   * Lo que se lee de la nota sin abrir nada: lo que dice antes de su primera lectura fechada, tal
   * cual, o la nota entera en una fuente con animales que empieza por la lectura. `null` si la
   * nota empieza por la lectura (o no hay nota). Lo corta el backend; si no es la nota entera,
   * la nota entera va plegada (`evidence/EvidenceEntry.tsx`).
   */
  scope_in_view: string | null;
  grade: EvidenceGrade;
}

/** La ficha del registro sin el motivo de una cita: `EvidenceRef.to_dict` del backend. */
export type EvidenceCard = Omit<EvidenceItem, "relevance" | "scope_caveat" | "scope_in_view">;

/**
 * Una frase leída que sostiene un paso de una guía o una definición del glosario
 * (`backend/app/guides.py`): la frase en su idioma, el sitio del documento, el día de lectura y la
 * ficha del registro tal cual.
 */
export interface GuideBasis {
  quote: string;
  where: string;
  read_on: string;
  citation: EvidenceItem;
}

/** Un paso de una guía: el texto lo redacta el backend; la frase de la fuente va al lado. */
export interface GuideStep {
  text: string;
  basis: GuideBasis[];
}

/** Un indicador del catálogo que mide la guía, con su nombre en español y su equipo. */
export interface GuideIndicator {
  key: string;
  display_es: string;
  equipment: string | null;
  mode_display: string | null;
}

export interface MeasurementGuide {
  id: string;
  title: string;
  indicators: GuideIndicator[];
  steps: GuideStep[];
  /** Lo leído de cómo cambia la medida en vuelo. */
  in_flight: GuideStep[];
  /** Lo que se buscó y no se encontró: un paso sin fuente no se escribe. */
  not_found: string[];
}

/** `GET /api/guides`. */
export interface MeasurementGuides {
  scope: string;
  guides: MeasurementGuide[];
  /** Lo que tiene su propia guía en otro panel (la ecografía). */
  elsewhere: { id: string; text: string; route: string; module: string }[];
}

export interface GlossaryTerm {
  id: string;
  term: string;
  definition: string;
  origin: "emma" | "source";
  /** El rótulo del origen, del backend: «definición de EMMA» o «definición tomada de la fuente». */
  origin_display: string;
  /** El fichero del repositorio que sostiene una definición de EMMA. */
  document: string | null;
  basis: GuideBasis[];
}

/** `GET /api/glossary`. */
export interface Glossary {
  scope: string;
  terms: GlossaryTerm[];
}

/** Nivel de evidencia de una fuente, desde su registro de PubMed (portado de Polaris). */
export interface EvidenceGrade {
  source: string;
  pmid: string | null;
  /** De donde sale el nivel: el registro, el texto de la cita (solo degrada) o nada. */
  basis: "record" | "text" | "none";
  tier: string;
  label: string;
  preclinical: boolean;
  reason: string;
}

export interface Recommendation {
  domain: string;
  action: string;
  rationale: string;
  urgency: "routine" | "soon" | "immediate";
  notify_ground: boolean;
  evidence: EvidenceItem[];
  /** La contramedida de la biblioteca: recursos, tiempo, protocolo y seguimiento. */
  countermeasure: Countermeasure | null;
  /**
   * Lo que una persona ya decidio sobre ella: hoy, solo «no adoptar» con su motivo. Es un
   * registro, no una evaluacion: la recomendacion sigue saliendo. Lo da `/api/status`; las
   * recomendaciones del modo anatomico no lo llevan.
   */
  decision?: RecommendationDecision | null;
  /**
   * Que paso las otras veces que se adopto esta contramedida para este tripulante. Historia, no
   * aviso: no cambia que se recomienda. `null` si la recomendacion no lleva contramedida.
   */
  prior_response?: PriorResponse | null;
  /**
   * Que recursos pide su contramedida y cuales constan como no disponibles o sin declarar. Un
   * aviso al lado: no cambia que se recomienda. `null` si la recomendacion no lleva contramedida.
   */
  resource_status?: ResourceStatus | null;
  /**
   * Sobre que se espera el beneficio de su contramedida, donde cae cada efecto adverso que la
   * biblioteca declara y con que otras esta adoptada a la vez (§5.39.17). Informacion, no aviso:
   * no cambia que se recomienda. `null` si la recomendacion no lleva contramedida; ausente en un
   * backend anterior.
   */
  effects?: CountermeasureEffects | null;
}

/** Donde puede caer un efecto adverso declarado: un dominio clinico o un indicador del catalogo. */
export interface AdverseEffect {
  affects: "domain" | "indicator";
  key: string;
  /** El nombre con que la tripulacion lo lee (del backend). */
  display: string;
  /** Lo que la nota de la entrada dice de el, y de donde sale. Textos del backend. */
  text: string;
  basis: string;
}

/** Una nota de co-adopcion: otra contramedida con seguimiento abierto para el mismo tripulante. */
export interface CoAdoptionNote {
  countermeasure_id: string;
  action: string;
  adoption_index: number;
  adopted_at: string;
  /** `true` si esta recomendacion tambien esta adoptada; `false`, la nota va en condicional. */
  adopted: boolean;
  /** «Adoptada junto con «…»: ninguna fuente leida dice como interactuan.» (o la frase de la fuente). */
  text: string;
  /** La ficha de la fuente leida que diga como interactuan; `null` si ninguna lo dice. */
  source: EvidenceItem | null;
}

/**
 * Los efectos de una contramedida (`advisor/effects.py`): fuera de la huella de reglas. Todo texto
 * lo redacta el backend; «no declarado» no es «no tiene», y lo dice `adverse_text`.
 */
export interface CountermeasureEffects {
  countermeasure_id: string;
  benefit: {
    domain: string | null;
    domain_display: string | null;
    parameter: string | null;
    parameter_display: string | null;
    /** «Beneficio esperado: sobre el dominio …» Sin magnitud. */
    text: string;
  };
  adverse_declared: boolean;
  adverse: AdverseEffect[];
  /** La frase de «no declarado» cuando la entrada no escribe ningun efecto; `null` si los declara. */
  adverse_text: string | null;
  co_adopted: CoAdoptionNote[];
  co_adoption_basis: string;
}

/**
 * Con que reglas se firmo una decision, frente a las de hoy (`record-integrity.md` §3.26). La
 * frase es del backend —«decidido con reglas@…; misma version que hoy», «… distinta de la de
 * hoy: reglas@… hoy» o «sin version registrada: …» para lo firmado antes del campo— y se enseña
 * tal cual, sin color: es informacion, no una señal.
 */
export interface DecidedWith {
  rules_version: string | null;
  same_as_today: boolean | null;
  text: string;
}

/** Decision firmada de no adoptar una contramedida. Los dos textos los compone el backend. */
export interface RecommendationDecision {
  action: "declined";
  ledger_index: number;
  decided_at: string;
  decided_by: string;
  reason: string;
  /** «Se decidio no adoptarla el … (quien): motivo». */
  text: string;
  /** Que significa y que no: no cierra ni silencia nada. */
  meaning: string;
  /** Con que reglas se firmo el «no». */
  rules?: DecidedWith;
}

/** Una adopcion anterior, contada con lo que su seguimiento ya dice. Textos del backend. */
export interface PriorAdoption {
  adoption_index: number;
  adopted_at: string;
  adopted_by: string;
  /** «Adoptada el … (quien).» */
  adopted_text: string;
  level_at_adoption: string;
  state: "open" | "closed";
  /** Como se cerro, con su motivo firmado, o que sigue en seguimiento. */
  state_text: string;
  closed_by: string | null;
  closed_reason: string | null;
  followup_checks_display: string[];
  repeated_checks_display: string[];
  /** Que indicadores seguia y cuales se repitieron. */
  checks_text: string;
  /** La evaluacion del seguimiento, sin retocar; `null` mientras la adopcion siga abierta. */
  evaluation: { outcome: string; text: string } | null;
  /** La misma, tras el rotulo de con que compara («Al cierre: …»). Texto del backend. */
  evaluation_text: string | null;
  /**
   * Del cierre, si lo guardo (los firmados desde 2026-10-13): el instante de su estado y el nivel
   * del dominio entonces. `null` en un cierre anterior o con la adopcion abierta.
   */
  closed_at?: string | null;
  /** Cuando se firmo el asiento de cierre; lo tiene todo cierre. */
  closed_recorded_at?: string | null;
  level_at_close?: string | null;
  /** Con que extremo compara `evaluation`: el nivel que guardo el cierre o el de este estado. */
  evaluation_basis?: "at_close" | "current_state" | null;
}

/** La respuesta previa a una contramedida (KB H5). Nunca una tasa ni una causa. */
export interface PriorResponse {
  state: "none" | "open" | "closed";
  count: number;
  /** Cuantas veces y cuando la ultima, o que no hay adopciones anteriores. */
  text: string;
  /** «Lo que paso despues, no una prueba de que fuera por la contramedida…». Va siempre. */
  caveat: string;
  /** Con que compara la evaluacion; `null` si no hay historia. */
  evaluation_basis: string | null;
  last: PriorAdoption | null;
  adoptions: PriorAdoption[];
}

/** Contramedida como dato (especificacion §8). Todo texto lo redacta el backend. */
export interface Countermeasure {
  id: string;
  /** "crew": sobre una persona. "habitat": comprobacion ambiental, sin dominio clinico. */
  scope: "crew" | "habitat";
  domain: string | null;
  ridge: string;
  ridge_display: string;
  action: string;
  indication: string;
  resources: string[];
  /** Solo con la lista vacia: la entrada declara por que (p. ej. «no requiere recursos»). */
  resources_note?: string | null;
  /** `null` si no hay fuente para el tiempo: no se inventa. */
  crew_time_minutes: number | null;
  crew_time_basis: string;
  protocol_ref: EvidenceItem | null;
  followup_checks: string[];
  followup_checks_display: string[];
  followup_window_hours: number;
  followup_basis: string;
  contraindications_note: string | null;
  /** Lo escrito por la revision medica o, si no hay nada, que esta pendiente (texto del backend). */
  contraindications_display?: string;
  adverse_effects_note: string | null;
  basis: "evidence-backed" | "demo";
  /**
   * Familia del vocabulario cerrado (`FAMILIES` en `advisor/countermeasures.py`) y su palabra.
   * Opcionales: un backend anterior no las manda, y entonces no se pinta nada.
   */
  family?: string;
  family_display?: string;
  /**
   * En la biblioteca (`GET /countermeasures`), los efectos de la entrada sin co-adopcion: no hay
   * tripulante. En una recomendacion van en `Recommendation.effects`. Ausente en un backend anterior.
   */
  effects?: CountermeasureEffects | null;
}

/** Una familia del vocabulario cerrado de contramedidas, con su criterio y cuántas hay. */
export interface CountermeasureFamily {
  key: string;
  display: string;
  criterion: string;
  /** `false` solo en la farmacológica: está en el vocabulario para decir que queda fuera. */
  in_scope: boolean;
  count: number;
}

/** `GET /countermeasures`: la biblioteca entera, por peligro RIDGE, con sus familias. */
export interface CountermeasureLibrary {
  countermeasures: Countermeasure[];
  by_ridge: { ridge: string; ridge_display: string; count: number; countermeasures: string[] }[];
  families: CountermeasureFamily[];
  note: string;
  family_basis: string;
  ridge_basis: string;
  /**
   * Las cuentas de los efectos y lo que una fuente leida diga de dos a la vez (hoy, nada). Con
   * otro nombre que la ficha de cada entrada (`Countermeasure.effects`): no tiene su forma.
   */
  effects_overview?: {
    note: string;
    co_adoption_basis: string;
    declared: number;
    not_declared: number;
    interactions: { between: string[]; source: EvidenceItem; quote: string }[];
    /** «Ninguna fuente leida dice como interactuan…» cuando la lista esta vacia. */
    interactions_note: string | null;
  } | null;
}

/** Una frase literal de la fuente de una contramedida en investigación, con su ficha. */
export interface ResearchQuote {
  ref: string;
  title: string;
  source: string;
  url: string | null;
  /** Página y sección. */
  where: string;
  quote: string;
}

/** Una contramedida en investigación: se enseña, no se ofrece (`offered` siempre `false`). */
export interface ResearchCountermeasure {
  id: string;
  name: string;
  ridge: string;
  ridge_display: string;
  targets: string;
  status: string;
  flight_note: string;
  quotes: ResearchQuote[];
  offered: false;
}

/** `GET /countermeasures/research`: aparte de la biblioteca, fuera de la huella de reglas. */
export interface ResearchCountermeasures {
  entries: ResearchCountermeasure[];
  note: string;
  offered: false;
  read_on: string;
  sources: Record<
    string,
    {
      title: string;
      source: string;
      url: string | null;
      extent: string;
      extent_text: string;
      what: string;
      /** El día de su lectura: el suyo si se leyó después que el fichero; si no, el del fichero. */
      read_on: string;
    }
  >;
  not_found: string[];
  read_not_included: string[];
}

/** Una contramedida adoptada y su seguimiento, derivado por el backend. */
export interface Followup {
  adoption_index: number;
  countermeasure: Countermeasure;
  domain: string;
  level_at_adoption: string;
  adopted_at: string;
  adopted_by: string;
  window_ends: string;
  state: "in_window" | "due" | "closed";
  repeated_checks: string[];
  evaluation: { outcome: "improved" | "unchanged" | "worsened" | "no_repeat"; text: string } | null;
  closed_by: string | null;
  closed_reason: string | null;
  /**
   * Del cierre, si guardo el nivel (2026-10-13): el instante de su estado, el nivel del dominio
   * entonces y la comparacion «al adoptar frente a al cerrar», AL LADO de `evaluation` (frente al
   * estado que se mira), que no cambia. `null` en un cierre anterior o sin cerrar.
   */
  closed_at?: string | null;
  closed_recorded_at?: string | null;
  level_at_close?: string | null;
  evaluation_at_close?: { outcome: "improved" | "unchanged" | "worsened" | "no_repeat"; text: string } | null;
  /** Con que reglas se firmaron la adopcion y el cierre (§3.26); `closure_rules` es `null` sin cerrar. */
  adoption_rules?: DecidedWith;
  closure_rules?: DecidedWith | null;
}

export interface DomainRisk {
  score: number;
  level: string;
  drivers: string[];
  /** «Recuperandose» o «empeorando» frente a una ventana antes; null si no cambio. */
  trajectory?: {
    direction: "recovering" | "worsening";
    from_level: string;
    to_level: string;
    since: string;
    basis: string;
    /** La frase hecha por el backend: hacia donde va y desde que nivel. La interfaz la pinta. */
    display: string;
    direction_display: string;
    from_level_display: string;
  } | null;
}

export interface ForecastCheck {
  key: string;
  display: string;
  display_es: string;
  unit: string | null;
  kind: "hindcast" | "snapshot";
  projected_change: number;
  projected_change_low: number;
  projected_change_high: number;
  actual_change: number;
  error: number;
  within_margin: boolean;
}

export interface CommsWindow {
  epoch: string;
  distance_au: number;
  one_way_minutes: number;
  round_trip_minutes: number;
  autonomy_required: boolean;
  target: string;
  description: string;
  /** Elongacion solar (S-O-T de Horizons, grados) y su marca `/T` o `/L`; `null` sin dato. */
  solar_elongation_deg?: number | null;
  solar_elongation_flag?: string | null;
}

/** Dolor referido en los ultimos dias, colocado sobre el esqueleto (Polaris `alinea`). */
export interface PainOnSkeleton {
  superposable: boolean;
  error_px: { mean: number; worst: number; threshold: number };
  window_days: number;
  marks: {
    zone: string;
    display: string;
    u: number;
    v: number;
    bone: string | null;
    /** "bone": en el centroide de su hueso (modo DIRECTO de Polaris); "fit": con el ajuste. */
    placed_on: "bone" | "fit";
    reports: number;
    last: string;
    intensity: number | null;
  }[];
}

/** Un pasaje de la documentacion de EMMA (Polaris `kb`), con su fichero y seccion. */
export interface KbResult {
  path: string;
  section: string;
  text: string;
}

/** PDF del estado (hasta `until`, el corte de Tierra), la cronica o el dosier. */
export function exportPdfUrl(kind: "estado" | "cronica" | "dosier", subject: string, until: Date | null): string {
  const cut = until === null ? "" : `&until=${encodeURIComponent(until.toISOString())}`;
  return `/api/export/${kind}.pdf?subject=${encodeURIComponent(subject)}${cut}`;
}

/**
 * El "ahora" de la linea temporal y de donde sale: los datos (el instante de referencia del
 * estado), el corte de Tierra o, solo sin lecturas, el reloj real. El texto es del backend.
 */
export interface TimelineAsOf {
  as_of: string;
  as_of_source: "data" | "cut" | "clock";
  as_of_basis: string;
}

/**
 * Un hecho de la cronica: la forma de Polaris `cronica.py` y lo que EMMA le añade. Sale del
 * ledger (lo firmado) o del estado ya calculado, la fase y la cabina (lo que paso).
 */
export interface ChronicleEvent {
  fecha: string;
  tipo: string;
  que: string;
  quien: string;
  fuente: string;
  clave: string;
  /**
   * El instante, y de que reloj: el de los datos o, si el asiento no declara otro, el de su firma.
   * `declared`: una fecha que declaro una persona para su carrera (misiones previas), con dia y sin
   * hora; va en la etapa `career`.
   */
  at: string;
  time_basis: "data" | "recorded" | "declared";
  recorded: string | null;
  mission_day: number | null;
  /**
   * Etapa de la especificacion (§10); `unplaced` si solo hay hora de firma; `career` para las
   * misiones previas declaradas, antes del prevuelo.
   */
  stage: string;
  fact: string;
  /** Nivel de riesgo, si el hecho es de una alerta. */
  level: string | null;
  /** Clase del limite de cabina, si es una excursion: normativo, de confort o rango objetivo. */
  severity: "health" | "performance" | "target" | null;
  /** Ni firmado ni leido del estado: recalculado hoy (`analysis/alert_history.py`). */
  recomputed: boolean;
  /**
   * El momento de «Cuerpo» que es este hecho (`anatomy.chronicle_moment`): un cambio de fase o una
   * toma posvuelo, con la clave y el rótulo del momento. Lo decide el backend; sin él, `null`.
   */
  moment?: { key: string; display: string } | null;
}

/** Un asiento firmado que cae en los pasos de un episodio recalculado: va al lado, no dentro. */
export interface AlertHistorySigned {
  ledger_index: number;
  kind: string;
  kind_display: string;
  domain: string;
  by: string;
  reference_time: string;
  /** Con que reglas se firmo (§3.26); `null` en los anuncios, que no llevan el campo. */
  rules?: DecidedWith | null;
}

/**
 * Un episodio pasado de un dominio, RECALCULADO hoy con las reglas de hoy: no es lo que el
 * sistema enseño entonces. Empieza y acaba en un paso, no en un instante.
 */
export interface AlertHistoryEpisode {
  id: string;
  domain: string;
  domain_display: string;
  peak_level: string;
  peak_level_display: string;
  first_step_start: string;
  last_step_end: string;
  steps: number;
  open: boolean;
  state_display: string;
  /** Ya estaba asi en el paso mas antiguo recalculado: su comienzo no se conoce. */
  start_unknown: boolean;
  start_note: string | null;
  levels: { step_start: string; step_end: string; level: string; level_display: string }[];
  signed: AlertHistorySigned[];
}

/** La historia recalculada de las alertas, con su rotulo, sus limites y su tope (del backend). */
export interface AlertHistory {
  subject: string;
  until: string | null;
  label: string;
  resting_level_display: string;
  rules_version: string;
  basis: string[];
  window_hours: number;
  steps_examined: number;
  max_steps: number;
  max_steps_basis: string;
  examined_from: string;
  examined_until: string;
  first_reading: string;
  complete: boolean;
  coverage: string;
  episodes: AlertHistoryEpisode[];
  none_display: string | null;
}

/** La cronica, con su ahora y sus etapas en el orden de la especificacion. */
export interface ChronicleView extends TimelineAsOf {
  stages: { key: string; display: string; count: number }[];
  events: ChronicleEvent[];
  lines: string[];
  /** La historia recalculada; `null` si no hay lecturas con que recalcular. */
  recomputed: AlertHistory | null;
}

/** Si una medida periodica llega a su ritmo (Polaris `estado_rutina`). */
export interface RoutineState {
  key: string;
  display: string;
  display_es: string;
  period_hours: number;
  basis: string;
  state: "al-dia" | "atrasada" | "rota" | "nunca-corrio";
  last_run: string | null;
  last_success: string | null;
  /**
   * De donde sale `period_hours`: el de diseño de siempre, o el acortado mientras dura un evento
   * solar activo (`routines.json` -> `during_event`). Opcionales: una respuesta anterior no los
   * trae y se lee como la de siempre.
   */
  period_source?: "design" | "event";
  design_period_hours?: number;
  event_id?: string | null;
  /** Solo orden (1 = primera) mientras dura el evento; no mueve niveles ni alertas. */
  priority?: number | null;
  /** La frase del backend que dice por que el periodo es otro, o `null`. */
  period_note?: string | null;
  /** Qué lo acorta: el evento de DONKI (`solar-event`) o la dosis de a bordo (`dose`). */
  trigger?: "solar-event" | "dose" | null;
  /** El nivel de misión vigente deja de esperarla (`routines.with_mission_level`): no se debe. */
  suspended?: boolean;
}

/** La respuesta de `/timeline/routines`. */
export interface RoutinesView {
  now: string;
  counts: Record<string, number>;
  routines: RoutineState[];
  /** El evento solar que acorta periodos en este ahora, o `null`. */
  active_event?: Record<string, unknown> | null;
  /**
   * Qué acorta los periodos ahora: el evento de DONKI o, sin él, la tasa de dosis de a bordo por
   * encima de su límite de peligro (`app/routines.py`, 2026-11-04); `null` sin ninguno.
   */
  active_trigger?: Record<string, unknown> | null;
  /** La frase del backend para todo el panel mientras dura el evento, o `null`. */
  event_note?: string | null;
  /** La frase del backend sin evento en curso; la iniciativa propia la dice cuando uno acaba. */
  event_over_note?: string | null;
  /** El nivel de misión vigente, su nombre del backend y la frase si suspende alguna medida. */
  mission_level?: string;
  mission_level_display?: string;
  suspended_note?: string | null;
  /** Las rachas de cada medida (`routines.streaks`); opcional. */
  streaks?: RoutineStreaks;
}

/**
 * Rachas de las medidas periodicas (`routines.streaks`): periodos de diseño seguidos con lectura
 * buena. Un recuento, no adherencia, y fuera del riesgo. Todo el texto lo da el backend.
 */
export interface RoutineStreaks {
  label: string;
  note: string;
  longest_label: string;
  routines: {
    key: string;
    display_es: string;
    period_hours: number;
    basis: string;
    current: number;
    longest: number;
    unit: string;
  }[];
}

/** Lo que lleva dias esperando a una persona (Polaris `atascos`), y lo que no cuadra. */
export interface WaitingView {
  threshold_days: number | null;
  waiting: { title: string; kind: string; days: number; since: string }[];
  incongruences: LabIncongruences["incongruences"];
}

/** Lo datado de la ventana (Polaris `anticipa.esta_semana`). */
export interface WeekView extends TimelineAsOf {
  days: number;
  items: { titulo: string; vence: string; siguiente_accion: string }[];
  block: string;
}

/** Que se recalcula (auto) o hay que revisar (humano) si cambia un dato (Polaris `cascada_mapa`). */
export interface DependsView {
  key: string;
  affected: { id: string; mode: "auto" | "humano"; title: string }[];
  map_errors: string[];
}

/** Calidad de las lecturas de un indicador (`backend/app/analysis/data_quality.py`). */
export interface IndicatorQuality {
  key: string;
  display: string;
  display_es: string;
  domain: string;
  /** Unidad UCUM del catalogo y decimales con que se lee el indicador. */
  unit: string;
  decimals: number;
  latest: {
    value: number;
    effective: string;
    /** Como firmo la fuente en el ledger, y su nombre legible. */
    source: string;
    source_label: string;
    observation_type: string;
    evidence_context: string;
    /** `null` si la fuente no declaro confianza: no se le pone numero. */
    confidence: number | null;
    state: string;
    label: string;
  };
  recent: {
    readings: number;
    low_confidence: number;
    undeclared: number;
    sources: { source: string; label: string; readings: number; low_confidence: number }[];
  };
  /** Lo que la linea base descontó por baja confianza, y la frase que lo cuenta. */
  baseline: {
    excluded_readings: number;
    capped_findings: number;
    discounted: boolean;
    text: string;
  };
}

export interface DataQuality {
  /** El umbral del motor: por debajo, una lectura es de baja confianza. */
  low_confidence_threshold: number;
  window_days: number;
  /** La ventana de lo reciente, en palabras del backend ("últimos 2 días"). */
  recent_label: string;
  /** Como se nombra cada estado. */
  labels: Record<"low" | "declared" | "undeclared", string>;
  summary: string;
  /** Cuantas lecturas recientes no declaran confianza; `null` si todas la declaran. */
  undeclared_note: string | null;
  recent: { readings: number; low_confidence: number; undeclared: number };
  indicators: IndicatorQuality[];
  /** Lecturas recientes de un dispositivo que constaba vinculado a otro tripulante. */
  device_bindings: DeviceBindingsNotice;
}

/**
 * `data.quality.device_bindings`: lo que el estado dice de las lecturas recientes frente a los
 * vinculos sensor-tripulante declarados. Es un aviso sobre el dato, no un nivel: esas lecturas
 * se analizan igual. Frases del backend (`ingest/bindings.py`); el identificador va abreviado.
 */
export interface DeviceBindingsNotice {
  /** `none`: nada que avisar. `not-checked`: el registro de vinculos no se pudo leer. */
  kind: "none" | "bound-to-other-crew" | "not-checked";
  label: string;
  /** Lecturas recientes de fuentes de wearable: las que se comparan. */
  readings: number;
  with_device: number;
  /** `null` si no se pudo comparar. */
  mismatched: number | null;
  groups: {
    source: string;
    source_display: string;
    whole_source: boolean;
    /** Abreviado: el identificador entero solo esta en `GET /sensor-bindings`. */
    device_display: string;
    crew: string;
    since: string;
    declared_by: string;
    /** El asiento de la declaracion con la que se comparo. */
    ledger_index: number;
    readings: number;
    first: string;
    last: string;
    indicators: { key: string; display: string; display_es: string; readings: number }[];
    text: string;
  }[];
  indicators: { key: string; display: string; display_es: string; readings: number }[];
  /** La primera lectura senalada de la ventana; `null` si no hay ninguna. */
  since: string | null;
  /** `null`: no hay nada que decir (ningun vinculo declarado). */
  text: string | null;
  analysis_note: string | null;
  device_note: string | null;
}

/** Si un dato externo esta caducado: lo decide el backend, con plazos en `rules_version`. */
export interface FreshnessVerdict {
  source: string;
  state: "fresh" | "stale" | "missing";
  /** La palabra del estado, del backend. */
  display: string;
  is_current: boolean;
  age_seconds: number | null;
  stale_after_seconds: number;
  stale_after_display: string;
}

/**
 * Lo que una persona declaro del enlace con Tierra (`environment/systems.py`, `earth_link`): el
 * sistema Comunicaciones entero. Solo texto: el retardo sigue saliendo de las efemerides y nada
 * de lo que decide lo lee. Las frases son del backend; la interfaz elige la marca del estado.
 */
export interface DeclaredLink {
  system: string;
  system_display: string;
  /** Clave del vocabulario de sistemas; `undeclared` si nadie ha declarado nada. */
  state: string;
  state_display: string;
  declared: boolean;
  /** Declarado y no en el estado que no pide atencion: la franja y Tierra lo senalan. */
  attention: boolean;
  since: string | null;
  /** Quien firmo la declaracion del «desde»; `declared_by` es quien firmo la ultima. */
  since_declared_by: string | null;
  declared_by: string | null;
  note: string | null;
  ledger_index: number | null;
  label: string;
  /** La frase corta, con su rotulo; `null` si no hay nada que senalar. */
  headline: string | null;
  sentence: string;
  scope_rule: string;
}

/** El ajuste de la línea base por la fase del ciclo, tal como lo decide la puerta del backend. */
export interface CyclePhase {
  applied: boolean;
  phase: "luteal" | "follicular" | null;
  reason: string;
}

export interface CrewStatus {
  subject: string;
  summary: string;
  overall_level: string;
  /** Clave de nivel -> palabra de la insignia. La interfaz pone color y glifo, no la palabra. */
  level_labels: Record<string, string>;
  /**
   * La línea base por fase del ciclo (lote «ciclo», B3; `api/cycle_phase.py`): si se aplicó, en
   * qué fase y la frase del backend con su motivo. Opcional: un backend anterior no lo da.
   */
  cycle_phase?: CyclePhase | null;
  /** Caducidad de los datos externos del estado, frente al reloj del backend al responder. */
  freshness: { comms: FreshnessVerdict; solar: FreshnessVerdict; basis: string };
  isolation_factor: number;
  comms: CommsWindow | null;
  comms_data_age: string | null;
  comms_data_age_seconds: number | null;
  /** El enlace con Tierra declarado; para Tierra, lo declarado hasta su corte. */
  declared_link: DeclaredLink;
  solar_data_age: string | null;
  solar_data_age_seconds: number | null;
  active_solar_event: Record<string, unknown> | null;
  /** `null` si nadie ha facilitado la dosis acumulada: no es un cero. */
  dose: {
    cumulative_msv: number | null;
    limit_msv: number;
    fraction: number | null;
    /** De donde sale: el parametro de la consulta o la ultima dosis registrada. */
    source?: "parameter" | "observation" | null;
    /** La dosis efectiva siempre es calculada: el backend la rotula inferida. */
    observation_type: "inferred";
    /**
     * La ultima dosis acumulada registrada como inferida o predicha, que no llega al limite de
     * carrera (§5.37.1: solo lo medido decide). `null` si no hay. Opcional: un backend anterior no
     * lo da.
     */
    set_aside?: { value_msv: number; effective: string; recorded_type: string } | null;
  };
  /** Derivas reales proyectadas al horizonte de relevancia: datos PREDICHOS. */
  predictions: Prediction[];
  /** Cuantas lecturas de cada tipo y de cada entorno sostienen el veredicto. */
  provenance: {
    observation_type: Record<string, number>;
    evidence_context: Record<string, number>;
    /**
     * Lecturas que el veredicto NO leyo por su tipo (inferidas, predichas), por tipo, y la regla en
     * palabras del backend (§5.37.1). Opcionales: un backend anterior no los da.
     */
    set_aside?: Record<string, number>;
    rule?: string;
  };
  domains: Record<string, DomainRisk>;
  recommendations: Recommendation[];
  notes: string[];
  data: {
    observations: number;
    window_days: number;
    deviation_window_days: number;
    trend_window_days: number;
    reference_time: string;
    readings_ignored: Record<string, number>;
    integrity_ok: boolean;
    personal_baseline_fraction: number;
    basis: string;
    /** Confianza de las lecturas (especificacion §2, §10). Los textos son del backend. */
    quality: DataQuality;
  };
  mission: {
    start: string;
    mode: "simulation" | "mission" | "mixed";
    sources: string[];
    mission_day: number;
    duration_days: number;
    phase: "preflight" | "adaptation" | "stable" | "return" | "postflight";
    phase_display: string;
    /** Todas las fases, en orden y con el nombre del backend: la tira de la linea temporal. */
    phases: { key: string; display: string }[];
    /** La configurada, sin seguir a la fase. Se conserva por compatibilidad: no se pinta. */
    gravity_regime: string;
    /** La gravedad del momento: en posvuelo, «en Tierra (gravedad terrestre)»; si no, la de la mision. */
    gravity_now: string;
    /** La de la mision, declarada por configuracion, con su rotulo. */
    gravity_mission: string;
    gravity_mission_label: string;
    /** La frase que se muestra, compuesta en el backend (`core/mission.py`). */
    gravity_display: string;
    phase_basis: string;
    events: MissionEvent[];
    /** Dónde está el tripulante en el instante de referencia; `null` si no consta. */
    location: CrewLocation | null;
    /** Qué se sabe de esa ubicación (`analysis/location.py`): decide la marca, no el texto. */
    location_state: LocationState;
    /** Lo que se dice cuando no hay ubicación (texto del backend); `null` si la hay. */
    location_missing_text: string | null;
    /** De dónde sale la ubicación (texto del backend). */
    location_basis: string;
    /** Recursos de a bordo declarados por una persona (especificacion §3). No es un inventario. */
    available_resources?: AvailableResources | null;
    /** El perfil de mision declarado por configuracion. Descriptivo: no escala el riesgo. */
    profile?: MissionProfile | null;
    /** Que dias de la mision tienen efemerides en cache (§5.36.6). Descriptivo: no decide nada. */
    ephemeris_coverage?: EphemerisCoverage | null;
  };
  inferred: InferredState[];
  radiation: RadiationScales;
  /** ¿Acertaron las proyecciones? Retrospectiva e instantaneas firmadas. */
  forecast_checks: {
    checked: number;
    within_margin: number;
    checks: ForecastCheck[];
    basis: string;
  };
  rules_version: string;
  /** Alertas activas y si alguien las ha reconocido (firmado en el ledger). */
  alerts: AlertState[];
  /** Contramedidas adoptadas y su seguimiento. */
  followups: Followup[];
  /** F.6.2: con que capacidad vigila el sistema, y que se pierde de lo que falta. */
  monitoring: { level: "full" | "reduced"; capabilities: Capability[] };
}

export interface AlertState {
  id: string;
  domain: string;
  level: string;
  acknowledged: boolean;
  acknowledged_by: string | null;
  acknowledgement_index: number | null;
  /** Con que reglas se firmo el reconocimiento (§3.26); `null` sin reconocer. */
  acknowledgement_rules?: DecidedWith | null;
  /** Estados de Polaris `salud.py`: detectado → en_arreglo → resuelto (no cambian el calculo). */
  resolution?: {
    state: "detectado" | "en_arreglo" | "resuelto";
    note?: string;
    declared_by?: string;
    /** Con que reglas se firmo el estado declarado; no lo lleva «detectado». */
    rules?: DecidedWith;
  };
  /**
   * Descartada por una persona, con su motivo (firmado en el ledger); `null` si no lo esta. La
   * alerta sigue en la lista y su nivel no cambia; un estado declarado despues la deja atras.
   */
  dismissal?: AlertDismissal | null;
  /** F.6.4, "Annunciation State": si la alerta se anuncia o esta silenciada. */
  annunciation: "normal" | "suppressed" | "inhibited";
  silenced_until: string | null;
  silenced_by: string | null;
  silenced_reason: string | null;
  /** Que cambio, desde cuando y frente a que base (especificacion §10). */
  detail?: AlertDetail;
  /** Con que reglas se decidio (especificacion §12). */
  rules_version?: string;
  /** Deteccion → reconocimiento → contramedida, en tiempo de los datos. */
  time_to_action?: {
    onset: string;
    acknowledged_after_minutes: number | null;
    countermeasure_after_minutes: number | null;
    basis: string;
  } | null;
}

/** El descarte vigente de una alerta (`alert-dismissal`). La palabra del motivo la da el backend. */
export interface AlertDismissal {
  reason: string;
  reason_display: string;
  note: string;
  declared_by: string;
  ledger_index: number;
  reference_time: string;
  /** Con que reglas se firmo el descarte (§3.26). */
  rules?: DecidedWith;
}

/** Los motivos con que se puede descartar una alerta (`GET /alerts/dismissal-reasons`). */
export interface DismissalReasons {
  reasons: { code: string; display: string; note_required: boolean }[];
  /** Lo que el descarte es y lo que no, tal cual lo redacta el backend. */
  basis: string;
}

/**
 * Dónde está un tripulante en un instante (`analysis/location.py`): la ubicación que manda de lo
 * firmado. `source` dice quién la puso: la consola (la declara una persona, y manda siempre) o las
 * anclas de módulo de la nave que oye el wearable (estimada, con `last_seen`, la última lectura que
 * la sostiene). Ya no hay ubicación simulada (2026-11-10: «las queremos reales»).
 */
export interface CrewLocation {
  /** Clave de la lista declarada de modulos (`/habitat/modules`). */
  module: string;
  display: string;
  start: string;
  end: string;
  ledger_index: number;
  source: "console" | "anchors";
  /** La última lectura de anclas que sostiene una estimada; `null` en una declarada. */
  last_seen: string | null;
}

/**
 * Qué se sabe de la ubicación en el instante de referencia (`analysis/location.py`):
 * - `declared`: la declaró una persona en la consola;
 * - `estimated`: la estiman las anclas de módulo;
 * - `ambiguous`: dos módulos compiten y no se fuerza una respuesta;
 * - `stale`: la última lectura de anclas es demasiado vieja;
 * - `unavailable`: no hay anclas declaradas, así que no se puede medir;
 * - `missing`: hay con qué medir, pero ni declaración ni lecturas.
 */
export type LocationState = "declared" | "estimated" | "ambiguous" | "stale" | "unavailable" | "missing";

/** Un ancla de módulo declarada en la consola (`GET /location/anchors`): equipo de la nave, no de EMMA. */
export interface LocationAnchor {
  /** Lo que anuncia el ancla (iBeacon `uuid:major:minor`, Eddystone-UID…), tal cual lo oye el wearable. */
  anchor_id: string;
  /** Clave de la lista declarada de módulos (`/habitat/modules`). */
  module: string;
  display: string;
  since: string;
  ledger_index: number;
}

export interface LocationAnchors {
  /** Las vigentes: de cada ancla, la última declaración firmada. */
  anchors: LocationAnchor[];
  /** De dónde sale y qué no se sabe (texto del backend). */
  basis: string;
}

export interface MissionEvent {
  /**
   * "location": ubicacion declarada; solo ese tipo lleva `module`. "shift": cambio de turno o de
   * horario de sueño (decimoctava ronda, U4), con los mismos campos que una EVA.
   */
  kind: "eva" | "workload" | "location" | "shift";
  start: string;
  end: string;
  label: string;
  /** Clave de la lista declarada de modulos (`/habitat/modules`). */
  module?: string;
  declared_by: string;
  ledger_index: number;
}

/** Radiacion en tres escalas (KB §7). */
export interface RadiationScales {
  acute: {
    active_event: Record<string, unknown> | null;
    time_to_action: {
      detected_at: string;
      shelter_ready_by: string;
      max_stay_until: string;
      /** `null` si el evento es posterior a la referencia (Tierra): lo dice `elapsed_note`. */
      elapsed_minutes: number | null;
      elapsed_note: string | null;
      basis: string;
      source: { title: string; source: string; url: string };
    } | null;
    /** A bordo de Orion el aviso lo da HERA, y EMMA no lo lee (decimosexta ronda, E8). */
    onboard_warning?: RadiationReading;
    /** Lo que una fuente dice del fin del refugio, como fuente: EMMA no tiene umbral propio (E8). */
    shelter_exit?: RadiationReading;
  };
  mission: {
    value_msv: number;
    absorbed_mgy: number;
    quality_factor: number;
    hours_covered: number;
    observation_type: "inferred";
    model_version: string;
    basis: string;
  } | null;
  career: {
    value_msv: number | null;
    prior_msv?: number;
    /** `null` sin límite positivo (desde la decimocuarta ronda; antes la ruta fallaba). */
    fraction?: number | null;
    basis: string;
    limit_msv: number;
    limit_source: string;
  };
  /**
   * La dosis de misión proyectada al fin configurado, PREDICHA (decimocuarta ronda, C7). `null`
   * sin dosis de misión que prolongar; `value_msv` nulo si no queda tramo (la misión terminó).
   * No entra en la dosis acumulada ni en ningún nivel.
   */
  projection?: RadiationProjection | null;
  /** NASA-STD-3001 Vol 1, Tabla 4.8-1: en su unidad (mGy-Eq o mGy), solo para mostrar. */
  short_term_limits?: ShortTermLimits;
  /** La fase del ciclo solar en la nota fechada de NASA y NOAA: descriptiva (E8). */
  solar_cycle?: RadiationReading;
}

/**
 * Lo leído junto a la radiación (`evidence/radiation_read.py`, decimosexta ronda, E8): el texto,
 * su alcance y lo buscado sin encontrar, del backend; cada frase con su sitio y su ficha. Se
 * muestra y no decide nada.
 */
export interface RadiationReading {
  label: string;
  text: string;
  scope: string;
  not_found: string;
  read_on: string;
  /**
   * Cada frase, con su sitio en la fuente, el identificador de su ficha y el día en que se leyó
   * (decimoctava ronda: no todas el mismo; un backend anterior no lo manda).
   */
  quotes: { quote: string; where: string; ref: string; read_on?: string }[];
  /** Cada ficha citada una vez, resuelta, en el orden de su primera frase. */
  sources: EvidenceItem[];
  /** Solo en el aviso a bordo: siempre `false`, EMMA no tiene conexión con HERA. */
  emma_reads_it?: boolean;
  /** Solo en el ciclo solar: la fecha de la nota, que no es la de hoy. */
  as_of?: string;
}

export interface RadiationProjection {
  observation_type: "predicted";
  model_version: string;
  mission_end: string;
  end_day: number;
  scope: string;
  value_msv: number | null;
  basis: string;
  absorbed_mgy?: number;
  quality_factor?: number;
  rate_ugy_per_h?: number;
  remaining_days?: number;
  by_type?: {
    low_msv: number;
    high_msv: number;
    low_quality_factor: number;
    high_quality_factor: number;
    observation_type: "inferred";
    basis: string;
    /** La ficha del TEPC de SLS-1, resuelta: con su salvedad de alcance (`EvidenceEntry`). */
    source: EvidenceItem;
  };
  career?: {
    value_msv: number | null;
    prior_msv?: number;
    /** `null` sin límite positivo: no hay fracción que dar. */
    fraction?: number | null;
    basis: string;
    limit_msv: number;
    limit_source: string;
  };
}

/** Una casilla de la tabla: la cifra con su unidad, o lo que la norma dice en su lugar. */
export interface LimitCell {
  value: number | null;
  unit: string | null;
  absent: string | null;
  /** El texto de la norma en esa casilla, tal cual («Not applicable», «-»); `null` con cifra. */
  literal: string | null;
}

export interface ShortTermLimits {
  rows: {
    organ: string;
    organ_display: string;
    /** La unidad de la fila en la norma (mGy-Eq o mGy), la misma en sus casillas con cifra. */
    unit: string;
    thirty_day: LimitCell;
    one_year: LimitCell;
    career: LimitCell;
    note: string | null;
  }[];
  units: string;
  scope: string;
  /** La ficha de NASA-STD-3001 Vol 1, resuelta, con la tabla y la página en `relevance`. */
  source: EvidenceItem;
}

/** El corte personal que cruzo una lectura (§5.37.1). La frase la redacta el backend. */
export interface AlertPersonalCut {
  applies: boolean;
  percentile: number | null;
  value: number | null;
  unit: string;
  samples: number;
  statement: string;
  basis: string;
}

/** De que tipo son las lecturas que causaron la alerta y cuantas del dominio no decidieron. */
export interface AlertReadingTypes {
  causes: Record<string, number>;
  set_aside: Record<string, number>;
  statement: string;
  rule: string;
}

export interface AlertDetail {
  domain: string;
  ridge: string;
  ridge_display: string;
  onset: string | null;
  onset_basis: string;
  changed: {
    key: string;
    display: string;
    display_es: string;
    unit: string;
    value: number;
    effective: string;
    severity: string;
    /**
     * Hacia donde se desvia (F.4.3.1 d): por encima o por debajo de lo esperado. Opcional porque
     * un backend anterior no lo da: entonces la frase va sin flecha, no se deduce de su texto.
     */
    direction?: "high" | "low";
    basis: string | null;
    baseline_median: number | null;
    baseline_samples: number;
    compared_with: string;
    danger_limit: number | null;
    description: string;
    /**
     * Cuánto cambió frente a la mediana personal (§5.34.6), en %, solo en escala de razón; si no
     * se da, `statement` dice por qué. Descriptivo. Opcional: un backend anterior no lo da.
     */
    relative_change?: AlertRelativeChange;
    /**
     * El tipo de la lectura en el registro (§5.37.1: solo lo medido decide); `null` si no se
     * localizo. Opcional: un backend anterior no lo da.
     */
    observation_type?: string | null;
    /** El corte de su propia base que cruzo (percentil y valor, en su unidad), o por que no hay. */
    personal_cut?: AlertPersonalCut;
  }[];
  trends: {
    key: string;
    display: string;
    display_es: string;
    description: string;
    span_days: number;
    /** El sentido de la deriva, estructurado: la flecha sale de aqui, no de la frase. Opcional como arriba. */
    direction?: "rising" | "falling" | "stable";
  }[];
  /** Por que puede importar: el peligro RIDGE del dominio, redactado por el backend. */
  relevance: string;
  /** Concordancia entre señales del dominio (especificacion §6). Descriptiva. */
  concordance: AlertConcordance;
  /** Que cambio alrededor del inicio (especificacion §3, `context_correlations`). */
  context?: AlertContext;
  /** La ficha que redacta el «por que»: la primera citada que lo trae. `null` si ninguna. */
  relevance_evidence: { id: string; title: string; text: string } | null;
  /**
   * Que comprobar a continuacion (§10). Lo compone el backend; sin ninguna, lo dice. Desde
   * §5.34.6 cada una lleva su coste; `order_note` dice que el coste no las reordena y
   * `unclassified_note`, que quiere decir «sin clasificar» (si alguna lo lleva).
   */
  checks: {
    items: AlertCheck[];
    statement: string;
    order_note?: string | null;
    unclassified_note?: string | null;
  };
  /** Que evidencia lo respalda (§10): cada ficha una vez, con su grado. */
  evidence: { items: AlertEvidence[]; statement: string };
  /** Persistencia (§6), con la regla del motor de riesgo. Descriptiva. */
  persistence: AlertPersistence;
  /** Confianza (§3), en recuentos. No hay cifra unica: seria inventada. */
  confidence: AlertConfidence;
  /** El tipo de las lecturas que la causaron (§5.37.1). Opcional: un backend anterior no lo da. */
  readings?: AlertReadingTypes;
  /** Lo medido del dominio en la ventana actual: lecturas e indicadores (lo lee el paso «Medir»). */
  sensed?: { readings: number; indicators: number };
  /**
   * Por que paso del flujo de la base de conocimiento (§10: SENSE → … → FOLLOW-UP) va la alerta,
   * con los estados y palabras de los pasos de una hipotesis (§5.34.6). Opcional: un backend
   * anterior no lo da.
   */
  flow?: { steps: AlertFlowStep[]; basis: string };
}

/** Un paso del flujo de una alerta: el de una hipotesis mas su nombre en la base de conocimiento. */
export interface AlertFlowStep extends HypothesisStep {
  kb_name: string;
}

/** Cambio frente a la mediana personal (§5.34.6). `percent` es `null` cuando no se da. */
export interface AlertRelativeChange {
  applies: boolean;
  percent: number | null;
  median: number | null;
  statement: string;
  basis: string;
}

/** Un dato del coste de una comprobacion: rotulo y valor del backend; `missing` = no hay dato. */
export interface AlertCostFact {
  key: string;
  label: string;
  display: string;
  missing: boolean;
  /** De donde sale un tiempo (la biblioteca o el coste de medir); `null` si no hay base escrita. */
  basis?: string | null;
  /** La cifra leida de masa, volumen o potencia (decimosexta ronda); `null` en todo lo demas. */
  figure?: CostFigure | null;
}

/** Que cuesta una comprobacion (base de conocimiento §9; `ingest/cost.py`). */
export interface AlertCheckCost {
  /** El tiempo de la accion, de la biblioteca de contramedidas; `null` sin contramedida. */
  action: (AlertCostFact & { minutes: number | null }) | null;
  /** Cada indicador que la comprobacion repite, con su coste de medirlo. */
  indicators: { key: string; display_es: string; facts: AlertCostFact[]; statement: string }[];
  /** Lo que se dice cuando no hay indicador que repetir o contramedida detras. */
  statement: string | null;
}

/** Una comprobacion estructurada del dominio de la alerta: una contramedida de la biblioteca. */
export interface AlertCheck {
  id: string | null;
  title: string;
  indication: string | null;
  urgency: Recommendation["urgency"];
  basis: string | null;
  basis_display: string | null;
  /** La respalda solo el riesgo del dominio, no un protocolo concreto. */
  demo: boolean;
  evidence_ids: string[];
  /** Que cuesta (§5.34.6). Opcional: un backend anterior no lo da. */
  cost?: AlertCheckCost;
}

/** Una ficha citada por las comprobaciones de la alerta. */
export interface AlertEvidence extends EvidenceItem {
  /** Identificadores de las comprobaciones que la citan. */
  cited_by: string[];
  role: "protocol" | "domain_risk";
  role_display: string;
  /** Ninguna de las comprobaciones que la citan tiene protocolo propio. */
  demo: boolean;
  demo_display: string | null;
}

export interface AlertPersistence {
  indicators: {
    key: string;
    display: string;
    display_es: string;
    readings: number;
    out_of_expected: number;
    /** `null` sin lecturas en la ventana. */
    fraction: number | null;
    severe: number;
    required_fraction: number;
    required_severe: number;
    /** Lo decide el motor: si el indicador cuenta como hallazgo por sus lecturas. */
    sustained: boolean;
    rule: "persistence" | "burst" | null;
    trend: boolean;
    statement: string;
  }[];
  sustained: number;
  statement: string;
  basis: string;
}

export interface AlertConfidence {
  low_confidence_threshold: number;
  labels: Record<string, string>;
  readings: number;
  low_confidence: number;
  declared: number;
  undeclared: number;
  not_found: number;
  capped: number;
  personal_baseline: number;
  population_range: number;
  indicators: {
    key: string;
    display: string;
    display_es: string;
    readings: number;
    low_confidence: number;
    declared: number;
    undeclared: number;
    not_found: number;
    capped: number;
    personal_baseline: number;
    population_range: number;
    compared_with: string[];
    statement: string;
  }[];
  statement: string;
  trend_note: string | null;
  note: string;
  basis: string;
}

export type ConcordanceState = "concordant" | "against" | "unchanged" | "no_data";

/** Cuantos indicadores del dominio acompañan al que inicio la alerta. No cambia el nivel. */
export interface AlertConcordance {
  trigger: string | null;
  trigger_display: string | null;
  trigger_basis: string;
  total: number;
  with_data: number;
  concordant: number;
  against: number;
  unchanged: number;
  no_data: number;
  indicators: {
    key: string;
    display: string;
    display_es: string;
    state: ConcordanceState;
    state_display: string;
    is_trigger: boolean;
    /** "inicio la alerta" en el indicador que la inicio; `null` en los demas. */
    role_display: string | null;
    /** La frase del motor (cifra y sentido); `null` si no se desvia. */
    description: string | null;
  }[];
  statement: string;
  basis: string;
}

export type ContextSourceStatus = "with_data" | "partial" | "no_data";

/** Lo que solapa con la ventana alrededor del inicio: siempre "correlacion temporal, no causa". */
export interface AlertContext {
  label: string;
  summary: string;
  anchor: string;
  anchor_basis: string;
  window_start: string;
  window_end: string;
  window_hours_before: number;
  window_hours_after: number;
  window_basis: string;
  mission: { mission_day: number; phase: string; phase_display: string; statement: string };
  items: {
    kind:
      | "habitat"
      | "mission_event"
      | "phase_change"
      | "solar_event"
      | "countermeasure"
      | "exercise"
      | "fluid_intake"
      | "diet"
      | "sleep"
      | "system_status";
    label: string;
    title: string;
    /**
     * Texto declarado por una persona o por la biblioteca de contramedidas. En una excursion
     * del habitat con ubicacion declarada, la frase del backend sobre donde estaba el tripulante.
     */
    detail: string | null;
    /** Solo en excursiones del habitat y solo si el tripulante declaro ubicacion. */
    presence?: "present" | "elsewhere" | "undeclared" | null;
    start: string;
    end: string;
    timing: string;
    source: string;
    value: number | null;
    value_label: string | null;
    unit: string | null;
  }[];
  /** Cada fuente dice si tenia dato en la ventana: "sin excursiones" no es "sin sensor". */
  sources: {
    kind: string;
    display: string;
    status: ContextSourceStatus;
    status_display: string;
    found: number;
    note: string;
  }[];
  note: string;
}

/** Region del cuerpo y los dominios que la cubren (mapa declarado por el backend). */
export interface AnatomyRegion {
  key: string;
  display: string;
  /** Vacío en una región sin nivel propio (el hígado): no tiene dominio. */
  domains: string[];
  note: string;
  /** Los indicadores que enseña una región sin nivel propio; vacío en las demás. */
  analytes: string[];
  /** El dominio del que es su nivel, en una región sin nivel propio; `null` en las demás. */
  level_of: string | null;
  /** «El nivel es del dominio …», redactado por el backend; `null` si la región tiene nivel. */
  level_note: string | null;
  /** Las fichas en que se apoya la frase de la región (`note`); vacío casi siempre. */
  note_refs: EvidenceItem[];
  /** De dónde sale la lista de analitos de una región sin nivel propio; `null` en las demás. */
  analytes_source: EvidenceItem | null;
  /**
   * Para qué sirve el órgano o sistema en el cuerpo, redactado por el backend con una fuente
   * leída; `null` donde no hay órgano que describir (la radiación), y entonces `function_note`
   * lo dice.
   */
  function: string | null;
  /** Las fichas de las que sale `function`; vacío si no hay función. */
  function_refs: EvidenceItem[];
  /** La frase del backend que dice por qué no hay función; `null` si la hay. */
  function_note: string | null;
}

/** Deriva de un indicador tal y como la ajusto el motor (`analysis/trend.py`). */
export interface AnatomyTrend {
  direction: "rising" | "falling" | "stable";
  significant: boolean;
  /** Real, por encima del umbral clinico con confianza y en la direccion mala. */
  concerning: boolean;
  slope_per_week: number;
  span_days: number;
  points: number;
  /** Redactada por el backend; cuando preocupa, es uno de los motivos del dominio. */
  description: string;
}

/** Un indicador de la region con su ultimo valor y lo que el analisis dice de el. */
export interface AnatomyVariable {
  key: string;
  display: string;
  display_es: string;
  unit: string;
  decimals: number;
  domain: string;
  value: number;
  effective: string;
  observation_type: string;
  evidence_context: string;
  /** El motor la cuenta como hallazgo: desviacion representativa o deriva que preocupa. */
  contributes: boolean;
  /** La desviacion que el motor cuenta; `null` si no cuenta ninguna. */
  deviation: AlertDetail["changed"][number] | null;
  trend: AnatomyTrend | null;
}

/**
 * Una ficha de la capa de investigación (`anatomy.ResearchItem`): la cita de siempre más su rótulo
 * de población, redactado por el backend y a la vista junto a la ficha. Empieza por la clase que la
 * ficha declara en el registro («modelo animal: ratón; …», «humanos: 24 mujeres…», «humanos y
 * modelo animal: …»): la interfaz lo enseña tal cual, con la marca de esa clase.
 */
export interface ResearchEvidenceItem extends EvidenceItem {
  population_label: string;
}

/**
 * La cadena de una region (especificacion §10): estado → variables → evidencia → tendencia →
 * contramedida. Todo lo calcula y redacta el backend con el mismo analisis que `/status`.
 */
export interface AnatomyRegionState extends AnatomyRegion {
  /** `null`: sin lecturas y sin hallazgo. No es "nominal", y la interfaz no lo decide. */
  level: string | null;
  has_data: boolean;
  data_note: string | null;
  state: {
    domain: string;
    level: string | null;
    has_data: boolean;
    drivers: string[];
    /** El paso RIESGO (KB §11.1): los mismos campos que `/api/risks` (`risk_entity.summary`). */
    risk: AnatomyRisk;
  }[];
  /** Las que mueven el nivel, primero. */
  variables: AnatomyVariable[];
  unmeasured: { key: string; display: string; display_es: string; domain: string }[];
  /** Por dominio: que parte de la condicion cubre el sistema y sus referencias con su nivel. */
  evidence: { domain: string; amcl_alignment: string; items: EvidenceItem[] }[];
  /** Las mismas recomendaciones que `/status` para estos dominios, con su contramedida. */
  recommendations: Recommendation[];
  recommendations_note: string | null;
  /**
   * Lo de fuera del cuerpo que solapa en el tiempo: el contexto de una alerta, del mismo
   * constructor que `/status` (`null` solo si el backend no lo compuso).
   */
  context: AlertContext | null;
  /**
   * La capa aparte de evidencia de investigación (el hígado, §5.37.16; cerebro, músculo y sistema
   * inmune, §5.39.16): lo observado en estudios con otras personas o con animales, no medido en el
   * tripulante, con la frase del backend que lo dice, cada ficha con su rótulo de población y, si
   * la hay, la instalación donde se hace esa investigación (el NSRL, en el cerebro), aparte de los
   * estudios y con su propia frase; `null` en las regiones que no la tienen. Solo la trae la
   * cadena: no entra en el nivel, ni en la evidencia del dominio, ni en la matriz de riesgos.
   */
  research: {
    note: string;
    items: ResearchEvidenceItem[];
    facility: { note: string; item: EvidenceItem } | null;
  } | null;
  /** El paso RIESGO de una región sin nivel propio: el del dominio de su nivel; `null` en las demás. */
  level_risk: AnatomyRisk | null;
}

export interface AnatomyRisk {
  risk_id: string;
  display: string;
  ridge: { category: string; display: string; source: { id: string; title: string; url: string | null } };
  /** La ficha del riesgo del dominio (`hrp_risk_id` en `/api/risks`), con su clase de documento. */
  hrp_risk: { id: string; title: string; url: string | null; evidence_type_display: string } | null;
  uncertainty_statement: string;
}

/** Un instante de la misión en que se puede pedir la cadena (`until`). */
export interface AnatomyMoment {
  key: string;
  /**
   * Un hito posvuelo agrupa los días R+ de su tramo (`anatomy.POSTFLIGHT_MILESTONES`), y uno
   * prevuelo los días L- del suyo (`anatomy.PREFLIGHT_MILESTONES`, decimosexta ronda).
   */
  kind: "phase_change" | "landing" | "postflight_milestone" | "preflight_milestone";
  display: string;
  until: string;
  /** El R+ de la lectura en que se pide un hito posvuelo; `null` en los demás. */
  days_after_landing?: number | null;
  /** El L- de la lectura en que se pide un hito prevuelo; `null` en los demás. */
  days_before_launch?: number | null;
}

/** Unos hitos y la ficha leída de la que salen, con lo que esa ficha cubre (`scope`). */
export interface MilestoneSource {
  days: number[];
  /** La ficha por su identificador, título y enlace; la nota entera la sirve `/api/dossier/references`. */
  source: { id: string; title: string; url: string | null; relevance: string | null };
  scope: string;
}

/**
 * De dónde sale cada hito, prevuelo o posvuelo: los leídos de una fuente, cada uno con su ficha, y
 * los de diseño de EMMA.
 */
export interface MissionMilestones {
  read: number[];
  design: number[];
  /** Falta en un backend anterior a la decimosexta ronda, que daba solo `source`. */
  sources?: MilestoneSource[];
  basis: string;
}

export interface AnatomyState {
  subject: string;
  reference_time: string;
  rules_version: string;
  regions: AnatomyRegionState[];
  /** Qué es este estado si se pidió en un momento pasado: un recálculo sin asiento. */
  moment: { until: string; label: string; basis: string[] } | null;
  /** Solo en el estado de ahora; pedido con `until`, `null` (la lista saldría cortada). */
  moments: {
    current_display: string;
    items: AnatomyMoment[];
    basis: string;
    /** Falta en un backend anterior a la decimoquinta ronda. */
    postflight_milestones?: MissionMilestones;
    /** Falta en un backend anterior a la decimosexta ronda. */
    preflight_milestones?: MissionMilestones;
  } | null;
}

/** Esqueleto de referencia (BodyParts3D, CC BY 4.0): centroide de cada hueso en la imagen. */
export interface AnatomySkeleton {
  region: string;
  width: number;
  height: number;
  bones: Record<string, { u: number; v: number }>;
  attribution: string;
}

export const SKELETON_IMAGE_URL = "/api/anatomy/skeleton.png";

/** Estado estimado, nunca medido en vuelo (especificacion §9). */
export interface InferredState {
  key: string;
  display: string;
  unit: string;
  observation_type: "inferred";
  model_version: string;
  now: { mission_day: number; loss_pct_low: number; loss_pct_high: number };
  trajectory: { mission_day: number; loss_pct_low: number; loss_pct_high: number }[];
  basis: string;
  source: { title: string; source: string; url: string };
  evidence_class: string;
  exercise_note: string;
  /** Lo MEDIDO que acompaña a la banda sin modificarla (`analysis/exercise_summary.py`). */
  exercise?: ExerciseMeasured;
  /** Solo en posvuelo: la banda se detiene en el día de regreso (`analysis/inferred.py`). */
  cut?: InferredCut;
  /**
   * La densitometría (DXA) MEDIDA en Tierra junto a la banda, si el tripulante tiene alguna
   * (`analysis/densitometry.py`). Comprueba la inferencia; no la mueve ni puntúa.
   */
  densitometry?: DensitometryCheck;
}

/** Una densitometría de una región, con su instante y su día de misión. */
export interface DensitometryReading {
  /** Cómo se nombra («antes del lanzamiento», «después del regreso»); lo da el backend. */
  label: string;
  value: number;
  effective: string;
  mission_day: number;
  /** Días desde el regreso; `null` en la de antes del lanzamiento. */
  days_after_return: number | null;
  /** Cuándo, con la notación de NASA y la cifra ya formateada («L-30,0 d», «R+5,0 d»). */
  when_display: string;
}

/** Una región (cadera, columna lumbar): la pérdida medida frente a la banda, o por qué no la hay. */
export interface DensitometryRegion {
  key: string;
  region: string;
  display_es: string;
  unit: string;
  decimals: number;
  state:
    | "compared"
    | "no_preflight"
    | "old_preflight"
    | "no_postflight"
    | "late_postflight"
    | "only_in_flight";
  preflight: DensitometryReading | null;
  postflight: DensitometryReading | null;
  later_postflight: number;
  /** Las fechadas en vuelo, que no se usan (la DXA no vuela); la frase lo dice. */
  in_flight: number;
  measured_loss_pct: number | null;
  position: "within" | "above" | "below" | null;
  statement: string;
}

/** La densitometría junto a la banda del día de regreso. Las frases son del backend. */
export interface DensitometryCheck {
  observation_type: "measured";
  relation: string;
  band_day: number;
  band: { loss_pct_low: number; loss_pct_high: number };
  postflight_window_days: number;
  preflight_window_days: number;
  /** Rótulos de la pérdida medida y de la banda, del backend. */
  loss_label: string;
  band_label: string;
  precision_note: string;
  source: { title: string; source: string; url: string };
  regions: DensitometryRegion[];
}

/** El corte de la banda en el regreso, con lo que dice una fuente leída de la recuperación. */
export interface InferredCut {
  phase: "postflight";
  label: string;
  basis: string;
  recovery: string;
  recovery_source: { title: string; source: string; url: string };
}

export type ExerciseRecordState = "recorded" | "recorded_zero" | "no_record";

/** Un indicador de ejercicio en la última semana de datos, como lo vio el motor. */
export interface ExerciseIndicator {
  key: string;
  display: string;
  display_es: string;
  unit: string;
  observation_type: "measured";
  /** Cuantas lecturas de cada entorno (simulado, vuelo...). */
  evidence_context: Record<string, number>;
  readings: number;
  first: string | null;
  last: string | null;
  latest: number | null;
  lowest: number | null;
  highest: number | null;
  outside_expected: number | null;
  baseline: { personal: boolean; median: number | null; samples: number; statement: string } | null;
  against_baseline: string | null;
  trend: string | null;
  trend_statement: string;
  statement: string;
}

/** Minutos de ejercicio e impactos de carga MEDIDOS. No hay "% de adherencia": `adherence` es null. */
export interface ExerciseMeasured {
  observation_type: "measured";
  window_days: number;
  window_start: string;
  window_end: string;
  window_basis: string;
  indicators: ExerciseIndicator[];
  record: { state: ExerciseRecordState; display: string; note: string };
  not_measured_excluded: number;
  relation: string;
  adherence: null;
  adherence_note: string;
}

interface AnnunciationRequest {
  subject: string;
  domain: string;
  reference_time: string;
  reason: string;
  requested_by: string;
}

const post = <T,>(path: string, body: unknown) =>
  request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

/** `?a=1&b=2` con los parametros que vengan definidos; nada si no viene ninguno. */
const queryOf = (params: Record<string, string | number | undefined>): string => {
  const pairs = Object.entries(params).filter(([, value]) => value !== undefined);
  return pairs.length === 0
    ? ""
    : `?${pairs.map(([name, value]) => `${name}=${encodeURIComponent(String(value))}`).join("&")}`;
};

export interface Capability {
  key: string;
  label: string;
  available: boolean;
  /** Por que falta: un dato ausente (cian) o una decision manual (amarillo). */
  cause: "missing" | "manual" | null;
  /** Que deja de vigilarse; `null` si la capacidad esta disponible. */
  consequence: string | null;
}

export interface Indicator {
  key: string;
  display: string;
  /**
   * El nombre con que lo lee la tripulación. `display` es el de LOINC y se queda en
   * inglés; ninguno de los dos lo redacta la interfaz. El origen dice de dónde sale
   * (`polaris` o `emma`), y el rótulo, que no es de LOINC.
   */
  display_es: string;
  /** `catalog`: en inglés, el nombre es el del catálogo (`display`), no uno redactado. */
  display_es_origin: "polaris" | "emma" | "catalog";
  display_es_origin_display: string;
  unit: string;
  domain: string;
  system: string;
  is_standard_code: boolean;
  /** Se registra y se ensena, pero el estado no lo lee (indicador descriptivo). */
  descriptive_only?: boolean;
  reference_low: number | null;
  reference_high: number | null;
  /** Procedencia del rango; `null` si el catálogo no le da rango (no hay base que declarar). */
  reference_basis: string | null;
  critical_low: number | null;
  critical_high: number | null;
  /** Decimales con que se lee (F.5.6 c). Los decide el backend, una vez. */
  decimals: number;
  /** Que hace falta para medirlo y cuanto tiempo de tripulacion cuesta (KB §9). */
  measurement_cost: {
    mode: string;
    mode_display: string;
    equipment: string;
    crew_time_minutes: number | null;
    crew_time_basis: string;
    /** Dónde se procesa, cuándo llega y consumibles; por clave de dimensión. */
    dimensions: Record<string, CostDimension>;
    /** Solo en un calculado: de qué indicadores se calcula, si hereda de ellos y por qué. */
    inputs?: string[];
    inherits?: boolean;
    inputs_basis?: string;
  } | null;
}

/** Recuperacion posvuelo frente a la linea base prevuelo del propio tripulante. */
export interface RecoveryReport {
  subject: string;
  launch: string;
  landing: string;
  basis: string;
  source: string | null;
  indicators: {
    key: string;
    display: string;
    display_es: string;
    unit: string;
    preflight: { samples: number; mean: number; low: number; high: number };
    postflight: {
      /** El instante de la toma; la cronica la cuenta con el (`timeline._recovery_events`). */
      at: string;
      days_after_landing: number;
      value: number;
      delta_pct: number | null;
      within_preflight_range: boolean;
    }[];
    /**
     * Cuándo vuelve y si vuelve (`recovery.return_to_range`): el primer R+ dentro del rango, si
     * las tomas siguientes se mantienen dentro y si la última sigue fuera. Sin veredicto: la
     * frase es del backend.
     */
    return_to_range: {
      state: "within" | "back-again" | "not-back";
      first_within_day: number | null;
      held: boolean | null;
      later_samples: number;
      within_since_day: number | null;
      last_day: number;
      text: string;
    };
  }[];
  /** Con tomas posvuelo y sin rango previo propio (menos de dos tomas): se dice, no se supone. */
  without_preflight_range: {
    key: string;
    display: string;
    display_es: string;
    unit: string;
    preflight_samples: number;
    postflight_samples: number;
    first_day: number;
    last_day: number;
    return_to_range: { state: "no-preflight-range"; text: string };
  }[];
}

// --------------------------------------------------------------------------- //
// Ecografia (backend/app/api/imaging.py)
// --------------------------------------------------------------------------- //

export interface MeasureSpec {
  name: string;
  display: string;
  lateral: boolean;
  /** Etiqueta -> puntos exactos; 0 = contorno con minimo aparte. En orden de marcado. */
  annotations: Record<string, number>;
  /** Que marcar en cada etiqueta, escrito por el backend. */
  instructions: Record<string, string>;
}

export interface ProtocolSign {
  key: string;
  display: string;
  /** Valor -> como se lee. Siempre incluye "no-valorable". */
  values: Record<string, string>;
}

export interface ProtocolView {
  key: string;
  display: string;
  signs: ProtocolSign[];
}

export interface UltrasoundProtocol {
  key: string;
  display: string;
  rationale: string;
  /** Ventanas con signos que se anotan (pulmon, FAST, higado). Vacio si el protocolo se mide. */
  views: ProtocolView[];
  /** Lista de calidad de la adquisicion, fijada por el proyecto. */
  checklist: string[];
  sources: string[];
  source_grades: EvidenceGrade[];
  measures: MeasureSpec[];
}

export interface RecordedFindings {
  ledger_index: number;
  recorded: string;
  protocol: string;
  checklist: { item: string; done: boolean }[];
  /** ventana -> signo -> valor */
  findings: Record<string, Record<string, string>>;
  recorded_by: string;
}

export interface MethodParameter {
  value: number;
  evidence: "established" | "contested" | "design";
  note: string;
  source: string;
}

export interface ProtocolCatalog {
  protocols: UltrasoundProtocol[];
  method: Record<string, MethodParameter>;
  /** Si las medidas ecograficas generan alertas, y lo que hay que saber si no. */
  alerting: { active: boolean; note: string };
}

export interface CalibratedRegion {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  mm_per_px_x: number;
  mm_per_px_y: number;
}

export interface ImagingStudy {
  ledger_index: number;
  recorded: string;
  subject: string;
  protocol: string;
  acquired: string;
  source: string;
  sha256: string;
  size_bytes: number;
  frames: number;
  rows: number;
  columns: number;
  /** Vacia: el estudio se puede ver, no medir en milimetros. */
  calibration: CalibratedRegion[];
  /** Lo que declara el ecografo sobre texto dibujado en los pixeles. */
  burned_in_annotation: "YES" | "NO" | "";
  /** Solo en fantomas: imagen dibujada, firmada como simulada, con su medida real. */
  synthetic?: boolean;
  ground_truth?: Record<string, number>;
  phantom_note?: string;
  /** Solo en ejemplos reales: de que dataset publico sale la imagen, y con que licencia. */
  sample?: string;
  dataset?: DatasetCitation;
}

export interface DatasetCitation {
  name: string;
  citation: string;
  doi: string;
  license: string;
  url: string;
}

/** Ecografia real de un dataset abierto que trae el paquete. Sin calibrar: se ve, no se mide. */
export interface ImagingSample {
  key: string;
  protocol: string;
  frames: number;
  dataset: DatasetCitation;
  burned_in_annotation: boolean;
}

export interface MarkedAnnotation {
  frame: number;
  points: [number, number][];
}

export interface MeasurementRequest {
  measure: string;
  laterality: "right" | "left" | null;
  annotations: Record<string, MarkedAnnotation>;
  measured_by: string;
}

export interface MeasurementResult {
  key: string;
  value: number;
  details: Record<string, number>;
  observation_index: number;
  provenance_index: number;
}

export interface MeasurementRecord {
  study_index: number;
  measure: string;
  laterality: "right" | "left" | null;
  annotations: Record<string, MarkedAnnotation>;
  details: Record<string, number>;
  measured_by: string;
  key: string;
  value: number;
  ledger_index: number;
  /** Cuando se registro a bordo: lo que decide si Tierra ya la tiene. */
  recorded: string;
}

export interface DraftSignoff {
  decision: "accepted" | "rejected";
  signed_by: string;
  comment: string;
  recorded: string;
  /** Solo en la primera firma: si el comentario registra una decision de alto riesgo. */
  high_risk?: { applies: boolean; reason: string };
  /** Fuente citada por la firma y si existe en su registro (confirmada, FABRICADA, no_resoluble, n/a). */
  source?: string;
  source_check?: { estado: string; detalle: string };
}

export interface SignoffBody {
  decision: "accepted" | "rejected";
  signed_by: string;
  comment: string;
  text_sha256: string;
  source?: string;
  /** Con `source` = "informe:<n>", el fragmento citado: se coteja que este en ese informe. */
  source_fragment?: string;
}

/** Acta de la firma: si hacia falta segunda firma de otra persona, si esta y si discrepan. */
export interface DecisionRecord {
  second_signature_required: boolean;
  complete: boolean;
  disagreement: boolean;
}

/** Borrador del modelo local. Solo lo que paso las barreras trae texto. */
/** Las objeciones del comite en un dosier (Polaris `paso_consolidacion`). */
export interface CommitteeDossier {
  committee: string[];
  head: { title: string; impact: "critica" | "alta" | "media"; quote: string | null; source: string }[];
  deferred: { title: string; impact: string; quote: string | null; source: string }[];
  warnings: string[];
  untraceable: boolean;
}

export interface InterpretationDraft {
  ledger_index: number;
  recorded: string;
  study_index: number;
  model: string;
  status: "unvalidated" | "blocked";
  text?: string;
  /** Huella del texto: la firma la devuelve, para firmar exactamente lo que se leyó. */
  text_sha256: string;
  reasons?: string[];
  verifier_problems: string[];
  /** Frases que las listas de Polaris marcarian y EMMA no bloquea: se muestran a quien firma. */
  language_notes?: string[];
  /** Modelos locales del comite que revisaron el borrador (patron de Polaris). */
  committee?: string[];
  /** Ausente en los borradores de antes de guardar las objeciones estructuradas. */
  dossier?: CommitteeDossier | null;
  signoff: DraftSignoff | null;
  countersign: DraftSignoff | null;
  record: DecisionRecord;
}

export interface UploadResult {
  ledger_index: number;
  sha256: string;
  calibrated: boolean;
  burned_in_annotation: "YES" | "NO" | "";
  removed_elements: number;
}

/** Observation FHIR R4, solo los campos que usa la interfaz. */
/** Zonas y tipos de dolor que se pueden marcar, con los nombres que se muestran. */
export interface PainCatalog {
  system: string;
  scale: { min: number; max: number; unit: string };
  /** `side` es el lado del tripulante, no el de quien mira la pantalla. */
  zones: { key: string; display: string; side: "left" | "right" | null }[];
  characters: { key: string; display: string }[];
}

/** Un informe de dolor tal y como esta firmado. Sin zonas es un "sin dolor". */
export interface PainReport {
  subject: string;
  effective: string;
  reported_by: string;
  zones: { zone: string; intensity: number; characters: string[] }[];
  /** La intensidad maxima: la cifra que entra en el analisis. */
  intensity: number;
  ledger_index: number;
  recorded: string;
  discuss: PainDiscussion;
}

/** Marca informativa del backend (no es una alerta): el texto se muestra tal cual. */
export interface PainDiscussion {
  reasons: string[];
  note: string | null;
}

export interface FhirObservation {
  code: { coding: { system: string; code: string; display: string }[]; text: string };
  effectiveDateTime: string;
  valueQuantity: { value: number; unit: string };
  device?: { display: string };
  /** Contexto, confianza, tipo (medido/inferido/predicho), entorno y modelo. */
  extension?: { url: string; valueCode?: string; valueDecimal?: number; valueString?: string }[];
}

/** Lectura de cabina tal y como esta firmada en el ledger. */
export interface HabitatReading {
  module: string;
  parameter: string;
  value: number;
  unit: string;
  effective: string;
  source: string;
  evidence_context: string;
}

export interface HabitatExcursion {
  module: string;
  parameter: string;
  display: string;
  unit: string;
  /**
   * "health": fuera del limite normativo. "performance": fuera de la zona de confort.
   * "target": fuera del rango objetivo de diseno (el O2 de [V2 6003]); aviso, como el confort.
   */
  kind: "health" | "performance" | "target";
  requirement: string;
  start: string;
  end: string;
  worst: number;
}

export interface HabitatParameter {
  key: string;
  display: string;
  unit: string;
  /**
   * Donde se ensena (`environment/habitat.py`, `GROUPS`): "cabin" (la atmosfera, con la luz),
   * "water" o "microbiology". Solo agrupa; `group_display` es su nombre, tal cual.
   */
  group?: string;
  group_display?: string;
  /** Toda lectura de habitat es una medida ("measured"): lo dice el backend. */
  observation_type?: string;
  limits: {
    low: number | null;
    high: number | null;
    requirement: string;
    kind: string;
    averaging_minutes: number | null;
    /** La clase en palabras del backend ("límite normativo", "rango objetivo"...). */
    kind_display?: string;
    /** Rotulo del backend: para que escribe la norma el limite. Se ensena tal cual. */
    label?: string | null;
    /**
     * Figura conjunta ([V2 6012]): el limite depende de la lectura simultanea de `pair`, y
     * `low`/`high` son solo su envolvente. Vertices como [valor, valor del par].
     */
    figure?: { name: string; pair: string; vertices: number[][] } | null;
  }[];
  averaging_minutes: number | null;
  /**
   * La ficha del registro de evidencia del documento de donde se leyeron los limites de ESTE
   * parametro (`environment/habitat.py`): OCHMO-TB-002 para el catalogo y OCHMO-TB-035 para el
   * ruido. `url` sale del registro; `read_on`, el dia de la lectura.
   */
  source: { id: string; title: string; url: string; read_on: string };
}

/**
 * Parametro del habitat que se muestra y NO se evalua (la luz, el agua potable, la
 * microbiologia del aire y las superficies): sin limites y sin norma que
 * citar. `limit_note` es la frase del backend que lo dice ("sin limite general").
 */
export interface HabitatDisplayOnly extends Omit<HabitatParameter, "source"> {
  limit_note: string;
  source: null;
  /** Requisitos leidos en la norma que se ensenan junto a la lectura y NO se evaluan. */
  reference_requirements?: HabitatReferenceRequirement[];
  /**
   * El rotulo del backend para esos requisitos, que dice por que no se evaluan ("requisito por
   * tarea; EMMA no conoce la tarea", "valor guia por tiempo de consumo (SWEG)…").
   */
  reference_label?: string | null;
  reference_source?: { id: string; title: string; read_on: string } | null;
  /** Solo en la luz: lo leido sobre la luz que recibe cada persona. Nunca se evalua. */
  personal_exposure?: PersonalLightExposure | null;
}

/**
 * La exposicion personal a la luz (`evidence/light_exposure.py`): NASA no publica un limite, y
 * la recomendacion leida es de Tierra y para otra magnitud. Todo el texto es del backend.
 */
export interface PersonalLightExposure {
  display: string;
  label: string;
  evaluated: false;
  nasa_personal_limit: InstrumentStatement | null;
  status: string | null;
  not_measured: string;
  searched: string[];
  recommendations: {
    quantity: string;
    setting: string;
    note: string;
    items: {
      period: string;
      label: string;
      low: number | null;
      high: number | null;
      unit: string;
      literal: string;
      statement: InstrumentStatement;
    }[];
    scope: InstrumentStatement[];
  };
  context: InstrumentStatement[];
  read_on: string;
}

/**
 * Un requisito de la norma que vale para una tarea, un periodo o un plano de medida que EMMA
 * no conoce: se pinta con su condicion y nunca como limite. `stated` es el valor que la tabla
 * da sin comparador; `same_quantity` en falso, que la magnitud no es la que lee EMMA.
 */
export interface HabitatReferenceRequirement {
  requirement: string;
  table: string;
  label: string;
  low: number | null;
  high: number | null;
  stated: number | null;
  unit: string;
  condition: string;
  same_quantity: boolean;
  source_row: string;
  evaluated: false;
}

/** Una frase o una fila de tabla leida en la fuente de un limite, con su seccion y su fecha. */
export interface SourcedStatement {
  ref: string;
  requirement: string;
  locator: string;
  quote: string;
  read_on: string;
}

/** Un paso del flujo de una hipotesis (especificacion §7): nombre, estado y frase del backend. */
export interface HypothesisStep {
  key: string;
  name: string;
  /** "done" | "awaiting_human" | "not_applicable" | "in_progress"; la palabra, en `state_display`. */
  state: string;
  state_display: string;
  detail: string;
}

export interface HabitatState {
  reference_time: string | null;
  readings: HabitatReading[];
  latest: HabitatReading[];
  excursions: HabitatExcursion[];
  active: HabitatExcursion[];
  /** La radiacion del habitat (2026-10-26): se muestra y no se evalua; `evaluated` lo dice. */
  radiation: HabitatRadiation;
}

/**
 * La radiacion del estado del habitat (`environment/habitat.py`, `radiation_state`): la ultima
 * tasa de dosis de cada dosimetro y el evento solar vigente, cada cifra con de donde sale. Sin
 * modulo (no se sabe donde esta el dosimetro) y sin factores de blindaje. Todo texto, del backend.
 */
export interface HabitatRadiation {
  display: string;
  module: null;
  module_text: string;
  shielding: string;
  evaluated: false;
  note: string;
  dose_rate: {
    key: string;
    display: string;
    basis: string;
    readings: HabitatDoseReading[];
    missing_text: string | null;
    /**
     * Quien tiene tasa de dosis que el estado no lee por su tipo (inferida, predicha), cuantas y
     * de que tipo, con la frase del backend; quien no tiene ninguna medida no sale en `readings`
     * y aqui se dice por que (§5.39.11). Opcionales: un backend anterior no los da.
     */
    set_aside_display?: string;
    set_aside?: HabitatDoseSetAside[];
    /** La regla en palabras del backend; `null` sin nada apartado. */
    set_aside_rule?: string | null;
  };
  solar_event: {
    display: string;
    /** "active" | "none" | "unavailable"; la frase, en `text`. */
    state: string;
    text: string;
    event: {
      event_id: string;
      event_type: string;
      time: string;
      link: string;
    } | null;
    source: string;
    data_age: string | null;
    data_age_seconds: number | null;
    freshness: FreshnessVerdict;
    /**
     * Sin evento vigente, el último SEP de esos datos de DONKI con su fecha real y la frase del
     * backend (sin red, el de la instantánea del paquete). Opcional: un backend anterior no lo da.
     */
    latest_recorded?: {
      event_id: string;
      event_type: string;
      time: string;
      link: string;
      text: string;
    } | null;
    basis: string;
  };
  summary: string;
}

/** La ultima lectura de tasa de dosis de un tripulante: de quien es y que la envio. */
export interface HabitatDoseReading {
  subject: string;
  value: number;
  /** Los decimales declarados del indicador (`core/display.py`): los de la frase del backend. */
  decimals: number;
  unit: string;
  effective: string;
  source: string;
  device: string | null;
  evidence_context: string | null;
  observation_type: string;
  origin_text: string;
  module: null;
}

/** Lo que un tripulante tiene de tasa de dosis y el estado aparta por su tipo (§5.39.11). */
export interface HabitatDoseSetAside {
  subject: string;
  /** Cuantas lecturas, por tipo (`inferred`, `predicted`). */
  counts: Record<string, number>;
  /** Si ademas tiene una medida en `readings`; en falso, es quien no sale en la lista. */
  shown: boolean;
  /** La frase del backend, sin el nombre: la consola lo pone delante, como en `readings`. */
  text: string;
}

/** Que es un cambio de turno y su fuente leida (`GET /mission/shift`): texto del backend. */
export interface ShiftBasis {
  kind: "shift";
  display: string;
  /** En que se distingue de un bloque de trabajo. */
  distinction: string;
  /** Lo que dice la fuente leida y lo que no. */
  source_says: string;
  source: { id: string; title: string; url: string | null; relevance: string | null };
}

/**
 * La tripulación ante un evento solar (`api/crew_radiation.py`, decimoctava ronda, U8): por
 * tripulante, su ubicación declarada y la dosis de misión y de carrera que ya calcula su estado,
 * junto al evento solar del estado y el refugio de su escala aguda. Sin factores de blindaje. Todo
 * texto, del backend.
 */
export interface CrewRadiation {
  display: string;
  basis: string;
  reference_time: string;
  /** El mismo bloque que la radiación del hábitat: vigente, ninguno o «no se sabe». */
  solar_event: HabitatRadiation["solar_event"];
  /** El procedimiento de refugio de Orion desde el evento; `null` sin evento vigente. */
  shelter: RadiationScales["acute"]["time_to_action"];
  shelter_missing_text: string | null;
  location_basis: string;
  crew: CrewRadiationMember[];
  shielding: string;
  evaluated: false;
  note: string;
}

export interface CrewRadiationMember {
  subject: string;
  /** El módulo, declarado o estimado, para el instante de referencia de la tripulación, o `null`. */
  location: CrewOverview["crew"][number]["location"];
  /** La misma regla que `/api/status`; opcional para no romper con un backend anterior. */
  location_state?: LocationState;
  location_missing_text: string | null;
  /** La dosis de esta misión de la escala del estado, con su tipo; `null` si no hay. */
  mission: RadiationScales["mission"];
  mission_missing_text: string | null;
  /**
   * La carrera de la escala del estado: `value_msv` nulo sin dosis previa declarada. `null` (como
   * `mission`) si el tripulante no tiene estado analizable: lo dice `state_missing_text`.
   */
  career: (RadiationScales["career"] & { observation_type?: string }) | null;
  state_missing_text: string | null;
}

export const crewRadiationApi = {
  /** Con `until`, lo que Tierra puede conocer. Solo lee. */
  get: (until?: Date) =>
    request<CrewRadiation>(`/crew/radiation${queryOf({ until: until?.toISOString() })}`),
};

/**
 * Una serie de iSWA (`GET /space-weather/series`, `environment/iswa.py`): el entorno en GOES y en L1,
 * no en la nave. Se muestra y no se evalúa: la referencia S1 viaja con `evaluated: false`.
 */
export type SpaceWeatherSeriesBlock =
  | {
      available: true;
      dataset: string;
      title: string;
      channels: { name: string; label: string; unit: string }[];
      window_hours: number;
      samples: ({ time: string; origin?: string } & Record<string, number | string | null | undefined>)[];
      latest: ({ time: string; origin?: string } & Record<string, number | string | null | undefined>) | null;
      last_sample_age_seconds: number | null;
      data_age: string | null;
      data_age_seconds: number | null;
      from_cache: boolean;
      live: boolean;
      source: string;
      reference?: { label: string; value: number; unit: string; channel: string; source: string; evaluated: false };
    }
  | { available: false; dataset: string; title: string; reason?: string; [key: string]: unknown };

export interface SpaceWeatherSeries {
  series: { protons: SpaceWeatherSeriesBlock; "solar-wind": SpaceWeatherSeriesBlock };
  scope: string;
  licence: string;
  events: string;
}

/**
 * Lo que el IMM de NASA publica sobre radiación (`GET /radiation/imm`, `evidence/imm_radiation.py`):
 * la probabilidad de al menos un síndrome agudo de radiación por misión de referencia, con su fila
 * citada, y la misión a la que EMMA asimila cada perfil. Todos los textos son del backend.
 */
export interface ImmRadiation {
  condition: string;
  condition_display: string;
  measure: string;
  measure_quote: string;
  caveat: string;
  caveat_quote: string;
  source: { id: string; title: string; source: string; url: string | null; date: string | null };
  read_on: string;
  drms: {
    key: string;
    display: string;
    drm_quote: string;
    table: string;
    row_quote: string;
    months: number;
    evas: number;
    probability: number;
    probability_text: string;
  }[];
  profiles: { id: string; declared: boolean; drm: string; reason: string; probability: number; probability_text: string }[];
  assigned_by: string;
  scope: string;
}

export const immRadiationApi = {
  /** Con `until`, el perfil declarado hasta el corte de Tierra. Solo lee. */
  get: (until?: Date) => request<ImmRadiation>(`/radiation/imm${queryOf({ until: until?.toISOString() })}`),
};

export const spaceWeatherSeriesApi = {
  /** Las últimas `hours` horas del flujo de protones ≥10 MeV y del viento solar. Solo lee. */
  get: (hours = 24) => request<SpaceWeatherSeries>(`/space-weather/series${queryOf({ hours: String(hours) })}`),
};

/** Lista declarada de modulos: parametro de diseno, no una nave concreta (`basis` lo dice). */
export interface HabitatModules {
  modules: { key: string; display: string; description: string }[];
  default: string;
  basis: string;
}

/** El estado vigente de un sistema, entero o en un modulo. Lo declara una persona: no se mide. */
export interface HabitatSystemStatus {
  /** `null`: la declaracion habla del sistema entero. */
  module: string | null;
  module_display: string;
  /** Clave del vocabulario del backend; `undeclared` si nadie ha declarado nada. */
  state: string;
  state_display: string;
  declared: boolean;
  /** El instante al que se refiere la primera declaracion seguida del estado vigente. */
  since: string | null;
  last_declared_at: string | null;
  declarations: number;
  note: string | null;
  declared_by: string | null;
  ledger_index: number | null;
  recorded: string | null;
}

/**
 * `GET /habitat/systems`: lo que una persona declaro del estado de los sistemas del habitat.
 * EMMA no lee el estado de ningun sistema; `label` y `note` lo dicen y la interfaz los ensena.
 */
export interface HabitatSystems {
  label: string;
  note: string;
  basis: string;
  /** Fichas del registro de evidencia en que se apoya `basis`; puede no haber ninguna. */
  basis_sources: { id: string; title: string; source: string; url: string | null }[];
  relation_basis: string;
  not_coded: string;
  rule: string;
  since_basis: string;
  default_state: string;
  whole_system_display: string;
  states: { key: string; display: string; declarable: boolean; description: string }[];
  systems: {
    key: string;
    display: string;
    description: string;
    /** Parametros de cabina con los que la relacion es de definicion. */
    parameters: { key: string; display: string }[];
    /** Siempre al menos uno: sin declaraciones, uno `undeclared`. */
    statuses: HabitatSystemStatus[];
  }[];
  declared: number;
  undeclared: number;
  summary: string;
  /** El enlace con Tierra declarado, el mismo de `/status`: Tierra lo lee de aquí antes de recibir nada. */
  declared_link: DeclaredLink;
  history: {
    system: string;
    system_display: string;
    state: string;
    state_display: string;
    previous_state: string;
    previous_state_display: string;
    changed: boolean;
    module: string | null;
    module_display: string;
    at: string;
    note: string | null;
    declared_by: string;
    ledger_index: number;
    recorded: string;
  }[];
}

/**
 * Un recurso de a bordo con su estado. `undeclared` es el caso por defecto y NO es «disponible»:
 * EMMA no lleva inventario. Nombres y palabras de estado, del backend.
 */
export interface ResourceRow {
  key: string;
  name: string;
  state: "available" | "unavailable" | "undeclared";
  state_display: string;
  since: string | null;
  note: string | null;
  declared_by: string | null;
  ledger_index: number | null;
  recorded: string | null;
}

/** Lo que le consta a una contramedida de los recursos que pide (`resource_status`). */
export interface ResourceStatus {
  state: "none-required" | "all-available" | "some-undeclared" | "some-unavailable";
  /** «declarado por una persona; EMMA no lleva inventario». */
  label: string;
  /** Cada recurso con el texto con que la contramedida lo nombra. */
  items: (ResourceRow & { description: string })[];
  unavailable: string[];
  undeclared: string[];
  text: string;
  /** Sin declarar no es disponible; la contramedida se ofrece igual. */
  caveat: string | null;
}

/** Una frase leida en una pagina oficial: literal, con su apartado y el dia en que se leyo. */
export interface ProfileCitation {
  ref: string;
  title: string;
  url: string | null;
  section: string;
  quote: string;
  read_on: string;
}

export type ProfileAspectStatus = "read" | "unverified";
export type ProfileEphemerisState = "consistent" | "mismatch" | "unchecked";

/** Un aspecto del perfil: lo que dice la fuente, o «sin verificar» con lo que se busco. */
export interface ProfileAspect {
  key: string;
  label: string;
  status: ProfileAspectStatus;
  status_text: string;
  statement: string | null;
  citations: ProfileCitation[];
  discrepancy: { text: string; citations: ProfileCitation[] } | null;
  searched: string | null;
  /** Lo que EMMA dice de si mismo junto al aspecto (sin cita: no es de la fuente), o null. */
  emma_note: string | null;
  /**
   * En un aspecto hecho solo con frases ya leidas (la capacidad medica, §5.36.7), para que se
   * leyo primero cada una, dicho por el backend; vacio en los demas.
   */
  reused_from: string[];
}

export type SolarConjunctionState = "no_ephemeris" | "not_recorded" | "within" | "clear" | "no_threshold";

/**
 * `mission.profile.solar_conjunction` y `/api/comms` (`app/environment/conjunction.py`): a cuantos
 * grados del Sol esta el objetivo visto desde la Tierra y, para Marte, si esta dentro del umbral
 * leido de JPL. Solo se dice: el retardo, el riesgo, los niveles y las recomendaciones no lo leen.
 * Todos los textos son del backend.
 */
export interface SolarConjunction {
  label: string;
  state: SolarConjunctionState;
  epoch: string | null;
  target_body: string;
  elongation_deg: number | null;
  elongation_flag: string | null;
  threshold_deg: number | null;
  text: string;
  note: string;
  citations: ProfileCitation[];
}

export type EphemerisCoverageState = "complete" | "partial" | "none";

/** Un tramo de dias seguidos (ISO 8601, ambos incluidos) con efemerides en cache o sin ellas. */
export interface EphemerisRun {
  start: string;
  end: string;
  days: number;
}

/**
 * `mission.ephemeris_coverage` (`app/environment/ephemeris_coverage.py`, §5.36.6): que dias de la
 * mision, del lanzamiento al regreso, tienen efemerides en cache. Sin red, los que no salen con el
 * retardo y la conjuncion «sin dato». Solo mira el disco y no decide nada: el retardo, el riesgo y
 * las alertas leen la efemeride del dia. Todos los textos son del backend.
 */
export interface EphemerisCoverage {
  state: EphemerisCoverageState;
  target: string;
  observer: string;
  start: string;
  end: string;
  days: number;
  covered_days: number;
  missing_days: number;
  covered: EphemerisRun[];
  missing: EphemerisRun[];
  /** El dia cuya efemeride enseña el estado: si cae dentro de la mision y si esta en cache. */
  day: { date: string; in_mission: boolean; covered: boolean };
  text: string;
  /** Como se precargan; null con la cobertura completa. */
  how_to_preload: string | null;
  note: string;
  citations: ProfileCitation[];
}

/**
 * `mission.profile` (`app/evidence/mission_profiles.py`): el perfil declarado y lo que una
 * fuente leida dice de el. Todos los textos son del backend. No cambia ningun nivel ni alerta.
 */
export interface MissionProfile {
  id: string;
  known: boolean;
  display: string;
  note: string;
  declared: string;
  unknown_text: string | null;
  ephemeris: { state: ProfileEphemerisState; target_body: string; text: string } | null;
  aspects: ProfileAspect[];
  /** Si el objetivo esta en conjuncion solar el dia de las efemerides (`environment/conjunction.py`). */
  solar_conjunction?: SolarConjunction | null;
  /** De donde sale el entorno vigente: el registro firmado o la configuracion. */
  declaration?: MissionProfileDeclaration;
  /** Cada pagina con los dias (ISO 8601) en que se leyo, del primero al ultimo. */
  pages_read: { title: string; url: string | null; read_on: string[] }[];
}

/**
 * Una casilla de la matriz de perfiles: el aspecto como se sirve, con `text` (la frase del backend
 * o «EMMA no tiene fuente»).
 */
export interface ProfileMatrixCell extends ProfileAspect {
  text: string;
}

/**
 * `GET /api/mission/profiles` (`app/evidence/mission_profiles.py`, `compare`): los tres perfiles
 * lado a lado, con los mismos aspectos y en el mismo orden. Todos los textos son del backend.
 * Descriptivo: nada que decida lo lee.
 */
export interface ProfileMatrix {
  note: string;
  declared_id: string;
  /** De donde sale el entorno declarado: la configuracion de partida y los asientos firmados. */
  declared_note: string;
  /** Si el perfil declarado no esta en el catalogo, la frase que lo dice; si esta, null. */
  declared_text: string | null;
  no_source: string;
  aspects: { key: string; label: string; reused_only: boolean }[];
  profiles: { id: string; display: string; declared: boolean; cells: ProfileMatrixCell[] }[];
  reused_note: string;
  medical_note: string;
  pages_read: MissionProfile["pages_read"];
}

export const missionProfilesApi = {
  /** Con `until`, la columna señalada es la del entorno declarado hasta el corte de Tierra. */
  get: (until?: Date) => request<ProfileMatrix>(`/mission/profiles${queryOf({ until: until?.toISOString() })}`),
};

/**
 * `GET /api/mission/profile` (`app/core/mission_profile_changes.py`): el entorno de la misión
 * vigente, el último firmado por la consola o, sin asientos, el de la configuración. Descriptivo:
 * declararlo no cambia niveles, alertas ni riesgo. Todos los textos son del backend.
 */
export interface MissionProfileDeclaration {
  id: string;
  display: string;
  previous: string | null;
  reason: string | null;
  declared_by: string | null;
  since: string | null;
  ledger_index: number | null;
  source: "registro" | "configuración";
  source_text: string;
  configured: string;
  configured_display: string;
  version: number;
  store_epoch: number;
  rule: string;
  descriptive: string;
  profiles: { id: string; display: string }[];
}

/** El cuerpo de `POST /api/mission/profile`: quien firma lo pone la consola. */
export interface MissionProfileChange {
  profile: string;
  reason: string;
  declared_by: string;
}

export const missionProfileApi = {
  get: (until?: Date) =>
    request<MissionProfileDeclaration>(`/mission/profile${queryOf({ until: until?.toISOString() })}`),
  set: (body: MissionProfileChange) => post<MissionProfileDeclaration>("/mission/profile", body),
};

/** `mission.available_resources`: lo declarado vigente, nunca una lista de «lo que hay». */
export interface AvailableResources {
  label: string;
  note: string;
  undeclared_note: string;
  declared: ResourceRow[];
  available: string[];
  unavailable: string[];
  undeclared_count: number;
  summary: string;
}

/** `GET /resources`: todo el vocabulario con su estado, y el historial de declaraciones. */
export interface ResourcesOverview extends AvailableResources {
  vocabulary_basis: string;
  rule: string;
  scope: string;
  /** Los estados que una persona puede firmar: «sin declarar» no es uno de ellos. */
  states: { key: string; display: string }[];
  undeclared_display: string;
  resources: (ResourceRow & { declarations: number; used_by: string[] })[];
  history: {
    resource: string;
    name: string;
    state: string;
    state_display: string;
    previous_state: string;
    previous_state_display: string;
    changed: boolean;
    since: string;
    note: string | null;
    declared_by: string;
    ledger_index: number;
    recorded: string;
  }[];
  countermeasures: { id: string; action: string; scope: string; resource_status: ResourceStatus }[];
}

/** Un vinculo sensor-tripulante vigente, tal y como lo declaro una persona. */
export interface SensorBinding {
  source: string;
  source_display: string;
  /** `null`: sin identificador, el vinculo es de la fuente entera. */
  device: string | null;
  device_display: string;
  crew: string;
  since: string;
  note: string | null;
  declared_by: string;
  declarations: number;
  ledger_index: number;
  recorded: string;
  /** Lo que EMMA no puede distinguir con este vinculo; `null` si no hay nada que advertir. */
  caveat: string | null;
}

/**
 * `GET /sensor-bindings`: que dispositivo lleva cada tripulante, segun lo declaro una persona.
 * EMMA no comprueba quien lo lleva puesto; `label` y `note` lo dicen y la interfaz los ensena.
 */
export interface SensorBindings {
  label: string;
  note: string;
  device_basis: string;
  rule: string;
  scope: string;
  whole_source_display: string;
  sources: { key: string; display: string }[];
  actions: string[];
  bindings: SensorBinding[];
  summary: string;
  history: {
    source: string;
    source_display: string;
    device: string | null;
    device_display: string;
    action: string;
    bound: boolean;
    crew: string | null;
    previous_crew: string | null;
    changed: boolean;
    since: string;
    note: string | null;
    declared_by: string;
    ledger_index: number;
    recorded: string;
  }[];
}

/** Quien estaba en el modulo de la excursion, segun la ubicacion declarada. */
export interface HypothesisLocation {
  module: string;
  module_display: string;
  present: string[];
  elsewhere: string[];
  /** Sin declarar en algun tramo: se les supone en el habitat compartido. */
  undeclared: string[];
}

/**
 * Un sistema de soporte vital declarado fuera de lo nominal en la ventana (base de conocimiento
 * §6). Lo declara una persona; `statement` es la frase entera, del backend.
 */
export interface HypothesisSystem {
  key: string;
  display: string;
  state: string;
  state_display: string;
  module: string | null;
  module_display: string;
  start: string;
  /** Null si es lo ultimo declarado. */
  end: string | null;
  /** Quienes firmaron el tramo hasta el instante comparado, por orden. */
  declared_by: string[];
  ledger_index: number;
  last_ledger_index: number;
  /** La nota mas reciente del tramo y quien la escribio; null si no hay. */
  note: string | null;
  note_by: string | null;
  label: string;
  statement: string;
}

/**
 * La radiacion registrada en la ventana (base de conocimiento §6 y §2.1): la tasa de dosis por
 * encima de su limite y los eventos de particulas solares de NASA DONKI. `statement` es la frase
 * entera, del backend; dice de donde sale cada cosa y que la tasa de dosis sola no dice si fue un
 * evento solar.
 */
export interface HypothesisRadiation {
  /** Null si ninguna lectura de tasa de dosis paso de su limite en la ventana. */
  dose: {
    key: string;
    unit: string;
    limit: number | null;
    subjects: string[];
    readings: number;
    first: string;
    last: string;
    peak: number;
    peak_subject: string;
    sources: string[];
  } | null;
  donki: {
    status: "with_data" | "partial" | "no_data";
    /** `SolarEvent.to_dict()` de `environment/donki.py`. */
    events: {
      event_id: string;
      event_type: string;
      time: string;
      severity: string;
      instruments: string[];
      linked_event_ids: string[];
      flare_class: string | null;
      link: string;
    }[];
  };
  statement: string;
}

/** Hipotesis de causa: siempre "correlacion, no causa". Texto del backend. */
export interface CrewHypothesis {
  kind: "shared_environment" | "shared_unknown" | "individual" | "declared_system" | "solar_event";
  label: string;
  title: string;
  affected: string[];
  excursion: HabitatExcursion | null;
  what_is_known: string | null;
  checks: string[];
  /** Fichas del registro de evidencia; en la norma, `relevance` es el requisito cruzado. */
  evidence: EvidenceItem[];
  steps: string[];
  /** Los siete pasos con su estado. Lo redacta el backend; la interfaz no deduce ninguno. */
  flow?: HypothesisStep[];
  /** Donde no hay "lo que se sabe": la frase que dice que solo esta la cita del limite. */
  knowledge_note?: string | null;
  /** Que clase de texto es `what_is_known` cuando sale de la norma y no de un estudio. */
  what_is_known_basis?: string | null;
  /** Las frases literales de la fuente que sostienen `what_is_known` (vacio en el CO2). */
  what_is_known_sources?: SourcedStatement[];
  /** Comprobaciones ambientales de la biblioteca (alcance "habitat"). */
  countermeasures?: Countermeasure[];
  /** Ultima revision humana (confirmada o descartada) y, si se confirmo, la recuperacion. */
  review: {
    decision: "confirmed" | "discarded";
    reason: string;
    decided_by: string;
    ledger_index: number;
    recovery?: { habitat_within_limit: boolean; still_affected: string[] };
  } | null;
  /**
   * Solo con alguna ubicacion declarada. "less_likely": la excursion no pudo alcanzar a dos o
   * mas afectados; va detras y `likelihood_reason` (texto del backend) dice por que.
   */
  likelihood?: "primary" | "less_likely";
  likelihood_reason?: string | null;
  location?: HypothesisLocation;
  /** Solo en `declared_system`: lo declarado, rotulado "coincidencia temporal, no causa". */
  system?: HypothesisSystem;
  /** Solo en `solar_event`: la radiacion registrada, rotulada "coincidencia temporal, no causa". */
  radiation?: HypothesisRadiation;
}

export interface CrewOverview {
  crew: {
    subject: string;
    overall_level: string;
    summary: string;
    reference_time: string;
    domains: Record<string, { level: string; drivers: string[] }>;
    /** Modulo, declarado o estimado por anclas, para el instante de referencia; null si no consta. */
    location: CrewLocation | null;
    /** La misma regla que `/api/status`; opcional para no romper con un backend anterior. */
    location_state?: LocationState;
    /** Lo que se dice cuando no hay ubicación (texto del backend). */
    location_missing_text?: string | null;
    /** Indicadores que dan un hallazgo en su estado: lo que tiene sentido comparar primero. */
    indicators: string[];
  }[];
  reference_time: string;
  correlation: {
    hypotheses: CrewHypothesis[];
    affected: string[];
    habitat_excursions: HabitatExcursion[];
    assumption: string;
    window_hours: number;
    /** Tripulantes con ubicacion declarada en la ventana; ausente si no hay ninguno. */
    location_declared?: string[];
  };
}

/** Un tripulante en la comparacion de un indicador. Todos los textos son del backend. */
export interface CrewCompareSeries {
  subject: string;
  /** Sin dato, sin lecturas en la ventana comparada, dentro de lo esperado o desviandose. */
  state: "no_data" | "no_recent" | "within" | "deviating";
  state_text: string;
  /** Solo si ninguna lectura del tramo tiene linea base personal con la que comparar. */
  baseline_text: string | null;
  deviating: boolean;
  /** Primera lectura fuera de lo esperado en la ventana; una deriva no tiene instante. */
  onset: string | null;
  /** Las frases que el estado de ese tripulante da como motivo, tal cual. */
  drivers: string[];
  latest: string | null;
  /** Tipo (medido, inferido, predicho) y entorno de sus lecturas: no se mezclan sin rotular. */
  origins: { type: string; context: string | null }[];
  /** Lecturas inferidas o predichas de este indicador que no deciden, por tipo (§5.38.7). */
  set_aside?: Record<string, number>;
  /** La frase del backend que las cuenta; null si no hay ninguna. */
  set_aside_text?: string | null;
  points: {
    effective: string;
    value: number;
    baseline: number | null;
    /** La lectura menos la mediana de su propia linea base; null sin base personal. */
    delta: number | null;
    concerning: boolean;
  }[];
}

/** `GET /crew/compare`: un indicador en toda la tripulacion, sobre el mismo eje. */
export interface CrewCompare {
  key: string;
  display: string;
  display_es: string;
  unit: string;
  /** Ultima lectura del indicador en la tripulacion: el "ahora" de la comparacion. */
  reference_time: string | null;
  since: string | null;
  baseline_basis: string;
  series: CrewCompareSeries[];
  /** El parametro de cabina pedido, sobre el mismo eje. null si no se pidio o no hay eje. */
  habitat: {
    parameter: HabitatParameter;
    state: "ok" | "no_data";
    state_text: string | null;
    evidence_contexts: string[];
    points: { effective: string; value: number; module: string }[];
    excursions: HabitatExcursion[];
  } | null;
  /** Descriptivo y rotulado como tal ("coincidencia temporal, no causa"). */
  summary: {
    label: string;
    text: string;
    deviating: string[];
    with_data: number;
    first_onset: string | null;
    simultaneous_since: string | null;
    onset_basis: string;
    undated_note: string | null;
    habitat_excursions: HabitatExcursion[];
    assumption: string;
    window_hours: number;
    window_basis: string;
  };
}

export interface Prediction {
  key: string;
  display: string;
  display_es: string;
  unit: string;
  decimals: number;
  observation_type: "predicted";
  model_version: string;
  horizon_weeks: number;
  window_days: number;
  projected_change: number;
  projected_change_low: number;
  projected_change_high: number;
  clinically_relevant: boolean;
  concerning: boolean;
  /** Redactado por el backend: que es y que no es esta proyeccion. */
  basis: string;
}

export interface AuditReport {
  entries: Record<string, unknown>[];
  total_entries: number;
  merkle_root: string | null;
  integrity_ok: boolean;
  failed_index: number | null;
  failure_reason: string | null;
}

export interface Scenario {
  key: string;
  label: string;
}

/**
 * Error con el `detail` que da el backend: la interfaz lo muestra, no lo oculta. `integrityBroken`
 * es el `integrity_ok: false` con el que el backend acompaña el 409 de un asiento manipulado
 * (`main._integrity_compromised`): lo que decide su marca (`lib/marks.ts`, §5.35.12) es ese campo,
 * no el texto del motivo.
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    readonly integrityBroken: boolean = false,
  ) {
    super(`HTTP ${status}: ${detail}`);
  }
}

/**
 * Cabecera propia de la consola en cada `POST` (`backend/app/api/console_header.py`). El backend
 * la exige en los `POST` que una peticion simple podria disparar desde otra pagina del navegador
 * (`/simulate`, `/comms/preload`, las importaciones); aqui va en todo metodo que no sea GET ni
 * HEAD —hoy, solo `POST`—, para que ningun sitio tenga que saber cuales. No es autenticacion: el
 * valor es fijo y publico.
 */
export const CONSOLE_HEADER = "X-EMMA-Console";
export const CONSOLE_HEADER_VALUE = "1";

/** `init` con la cabecera de la consola puesta si el metodo no es GET ni HEAD; un GET se queda igual. */
export function withConsoleHeader(init?: RequestInit): RequestInit {
  const method = (init?.method ?? "GET").toUpperCase();
  if (method === "GET" || method === "HEAD") return init ?? {};
  const headers = new Headers(init?.headers);
  headers.set(CONSOLE_HEADER, CONSOLE_HEADER_VALUE);
  return { ...init, headers };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, withConsoleHeader(init));
  if (!response.ok) {
    let detail = response.statusText;
    let integrityBroken = false;
    try {
      const body = (await response.json()) as { detail?: unknown; integrity_ok?: unknown };
      if (body.detail !== undefined) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
      integrityBroken = body.integrity_ok === false;
    } catch {
      // cuerpo no JSON: se queda el texto de estado
    }
    throw new ApiError(response.status, detail, integrityBroken);
  }
  return (await response.json()) as T;
}

/** URL de un fotograma como PNG. El backend lo saca del binario firmado ya comprobado. */
/** Pagina de un informe escaneado, como PNG, sacada del original firmado. */
export function reportPageUrl(report: number, page: number): string {
  return `/api/reports/${report}/pages/${page}`;
}

export type ReportKind = "analitica" | "informe-especialista" | "alta" | "otro";

export interface ReportPage {
  page: number;
  text: string;
  /** null: texto de la capa del PDF, no de OCR. */
  confidence: number | null;
  words: number;
  low_confidence: boolean;
  /** Texto sin identificadores; si no se pudo verificar, el texto viene vacio (retenido). */
  deidentification?: { redactions: number; verified: boolean; remaining: string[] };
}

/** Dos analiticas de la misma extraccion que no dicen lo mismo (Polaris `incongruencias_caso`). */
export interface LabIncongruences {
  incongruences: { key: string; sample: string; readings: { value: number; date: string; report: string }[] }[];
  undated_reports: number;
  tolerance: number;
}

/** Una cifra leida en una analitica, por confirmar o confirmada (`app/reports/labs.py`). */
export interface LabReading {
  key: string;
  name: string;
  value: number;
  unit: string;
  report_unit: string;
  ref_low: number | null;
  ref_high: number | null;
  out_of_range: boolean;
  confidence: string;
  comparator: string | null;
  requires_correction: boolean;
  status: "por_confirmar" | "confirmada";
  derived_from?: string;
  confirmation?: { confirmed_by: string; value: number; observation_index: number };
}

export interface ScannedReport {
  ledger_index: number;
  recorded: string;
  kind: ReportKind;
  media_type: string;
  pages: number;
  recorded_by: string;
  ocr: { available: boolean; engine?: string; min_confidence?: number; note?: string; pages: ReportPage[] };
  /** Si el informe es de este tripulante (Polaris `identidad_paciente`); ausente en los antiguos. */
  identity?: { verdict: string; explanation: string; usable: boolean };
  /** Cifras de la analitica; ausente en los informes antiguos. */
  lab_readings?: { date: string | null; readings: LabReading[] };
}

/** Una misión previa como se declara: los días no se declaran, los calcula el backend. */
export interface PriorMissionIn {
  name: string;
  start: string;
  end: string;
  /** `null`: no se conoce (no es cero). */
  dose_msv: number | null;
}

/** Una misión previa declarada, con los días entre sus fechas (`core/mission_history.py`). */
export interface PriorMission extends PriorMissionIn {
  days: number;
}

/** Un cotejo del historial con el perfil: `matches` `null` si no hay con qué cotejar. `overlap`
 *  solo aparece si una previa se solapa con la misión en curso (aviso, `matches` `false`). */
export interface MissionHistoryCheck {
  key: "missions" | "dose" | "overlap";
  matches: boolean | null;
  text: string;
}

/** Los topes que impone el backend al historial, para que el formulario no los copie. */
export interface MissionHistoryLimits {
  missions: number;
  name_length: number;
}

/**
 * El historial misión a misión vigente y su cotejo con el perfil (`GET /crew/mission-history`).
 * Las frases (`text`, `scope`, `days_basis` y las de cada cotejo) son del backend.
 */
export type MissionHistory =
  | {
      subject: string;
      declared: false;
      scope: string;
      limits: MissionHistoryLimits;
      text: string;
      missions: [];
      checks: [];
    }
  | {
      subject: string;
      declared: true;
      scope: string;
      limits: MissionHistoryLimits;
      days_basis: string;
      text: string;
      missions: PriorMission[];
      dose_sum_msv: number | null;
      missions_without_dose: number;
      declared_by: string;
      recorded: string;
      ledger_index: number;
      checks: MissionHistoryCheck[];
    };

/** Nombre y fecha de nacimiento declarados del tripulante, para cotejar sus informes. */
export type CrewIdentity =
  | { subject: string; declared: false }
  | { subject: string; declared: true; given_name: string; surnames: string; birth_date: string };

/** El visor web de Polaris (copiado tal cual) sobre una segmentación; `render` es su render.html. */
export function polarisViewerUrl(segmentation: number, page: "visor" | "render"): string {
  const base = `/api/volumes/segmentations/${segmentation}/polaris/`;
  return page === "visor" ? `${base}index.html` : `${base}render.html?fecha=estudio&ss=2`;
}

/** Fichero del visor 3D (volumen, etiquetas, malla) sacado del binario firmado. */
export function segmentationFileUrl(segmentation: number, name: string): string {
  return `/api/volumes/segmentations/${segmentation}/files/${encodeURIComponent(name)}`;
}

export interface VolumeStructure {
  key: string;
  nombre: string;
  etiqueta: number;
  malla: string | null;
  volumen_ml: number;
}

export interface VolumeLesion {
  id: number;
  estado: string;
  diametro_mm: number;
  volumen_ml: number;
  centro_mm: [number, number, number];
  region: number | null;
  pequena: boolean;
  acuerdo_2o_modelo: number | null;
  malla?: string;
}

/** Segmentacion automatica de un volumen (visor 3D de Polaris): sin validar, nunca un hallazgo. */
export interface VolumeSegmentation {
  ledger_index: number;
  recorded: string;
  preset: string;
  preset_nombre: string;
  estado: string;
  segmentador?: string;
  modalidad: string;
  ventana_hu: [number, number];
  estructuras: VolumeStructure[];
  lesiones: VolumeLesion[];
  volumen_organo_ml: number;
  /** Solo en el preset esqueleto: control de la cadena vertebral (backend `volumes/spine.py`). */
  cadena_vertebral?: SpineReview;
}

/** Nivel de un aviso del control, con el significado de la tabla F.5-1 (no es un nivel de riesgo). */
export type SpineNoticeLevel = "atencion" | "dato_ausente";

/** Una lista del control de la cadena vertebral: titulo y nombres los redacta el backend. */
export interface SpineReviewList {
  titulo: string;
  nivel: SpineNoticeLevel;
  elementos: string[];
}

/** Niveles que faltan por un extremo de la cadena, y si el volumen seguia mas alla. */
export interface SpineEnd {
  lado: "craneal" | "caudal";
  niveles: string[];
  volumen_continua: boolean | null;
  margen_mm: number | null;
  paso_mm: number | null;
}

/**
 * Control automatico de una segmentacion del esqueleto (funciones de Polaris, backend
 * `volumes/spine.py`): que niveles faltan y si el orden craneocaudal es coherente. Es un control
 * del modelo, no un hallazgo. Con `revisada` a false el control no se pudo hacer (`motivo`) y sus
 * listas de niveles no dicen nada.
 */
export interface SpineReview {
  revisada: boolean;
  control: string;
  motivo: string | null;
  nivel: SpineNoticeLevel | null;
  aviso: string | null;
  listas: SpineReviewList[];
  niveles_esperados: number | null;
  niveles_presentes: string[];
  niveles_ausentes: string[];
  huecos: string[];
  extremos: SpineEnd[];
  orden_coherente: boolean | null;
  invertida: boolean | null;
  rompen_orden: string[];
  niveles_pequenos: { nivel: string; volumen_mm3: number; en_extremo: boolean }[];
  umbral_pequeno_mm3: number | null;
  huesos_esperados: number;
  huesos_sin_voxeles: string[];
}

export interface VolumeStudy {
  ledger_index: number;
  recorded: string;
  subject: string;
  modality: "CT" | "MR";
  shape: number[];
  voxel_mm: number[];
  source: string;
  recorded_by: string;
  dataset?: DatasetCitation;
  segmentations: VolumeSegmentation[];
}

/**
 * Lesiones de dos segmentaciones del mismo preset, emparejadas y con el estado de cada una entre
 * los dos estudios. Todos los textos (`estado`, `criterio`, `aviso`, `evolucion.estado`) los da el
 * backend, que a su vez toma los de estado de `visor3d.evolucion` de Polaris: aqui no se redactan.
 */
export interface LesionComparison {
  antes: number;
  despues: number;
  estado: string;
  segmentador: string | null;
  criterio: string;
  aviso: string | null;
  lesiones: {
    id: number;
    estado: string | null;
    region: number | null;
    pequena: boolean | null;
    diametro_mm: number;
    volumen_ml: number;
    previa: { id: number; diametro_mm: number; volumen_ml: number } | null;
    evolucion: {
      estado: string;
      id_previo: number | null;
      delta_diametro_pct?: number | null;
      delta_volumen_pct?: number | null;
      distancia_emparejado_mm?: number | null;
    };
  }[];
  no_reencontradas: { id_previo: number; region: number | null; diametro_mm: number; volumen_ml: number }[];
}

export interface VolumeSample {
  key: string;
  nombre: string;
  preset: string;
  modalidad: string;
  dataset: DatasetCitation;
}

export function frameUrl(study: number, frame: number): string {
  return `/api/imaging/studies/${study}/frames/${frame}`;
}

/**
 * El aviso del freno HALT de Polaris, redactado por el backend (`api/safe_mode.halt_notice`):
 * la interfaz lo pinta tal cual. `since` es ISO 8601 en UTC, la fecha del fichero (sin firma).
 */
export interface HaltNoticeText {
  title: string;
  headline: string;
  summary: string;
  since: string | null;
  since_label: string;
  details_label: string;
  details: string[];
}

/** El freno por fichero de Polaris: no es el modo seguro, pero corta lo mismo (la red). */
export interface HaltState {
  active: boolean;
  file: string;
  since: string | null;
  /** Solo con el freno puesto; sin él, null y la consola no enseña nada. */
  notice: HaltNoticeText | null;
}

/** Modo seguro: corta toda salida a internet (la IA es local y sigue). */
export interface SafeModeState {
  active: boolean;
  reason: string | null;
  declared_by: string | null;
  since: string | null;
  /**
   * Cuántos cambios del modo seguro hay firmados (§5.38.13): sube en uno con cada cambio y nunca
   * baja. Va en la lectura y en la respuesta de cada cambio; entre dos respuestas, la de versión
   * más alta es la más nueva aunque llegue antes. No versiona `halt`.
   */
  version: number;
  /**
   * De qué almacén es esa versión: crece con cada almacén que abre el backend (cambiar de
   * escenario o reiniciar lo sustituye y la versión vuelve a 0). Se compara antes que `version`.
   */
  store_epoch: number;
  halt: HaltState;
}

/** Una cola de asientos de a bordo posteriores a un instante (`core/link_sync.backlog`). */
export interface LinkBacklog {
  count: number;
  /** Lecturas (fechadas con su hora) y el resto de asientos (fechados con su firma). */
  readings: number;
  other: number;
  first: string | null;
  last: string | null;
  first_index: number | null;
}

/**
 * El enlace con Tierra simulado (`GET /api/link-sync`, `core/link_sync.py`): declarado por una
 * persona, no medido. `cut` es el corte de Tierra con el enlace (nunca por delante del tiempo de
 * luz ni de la última vez que hubo enlace); `null`, todo lo de a bordo. Las frases son del backend.
 */
export interface LinkSync {
  label: string;
  state: "up" | "down";
  state_display: string;
  declared: boolean;
  since: string | null;
  declared_by: string | null;
  note: string | null;
  ledger_index: number | null;
  light_cut: string | null;
  cut: string | null;
  held: boolean;
  held_since: string | null;
  to_send: LinkBacklog;
  to_arrive: LinkBacklog;
  crew_sentence: string;
  ground_sentence: string;
  rule: string;
  not_measured: string;
  not_read_by: string;
  known_only_here: string;
  instant_basis: string;
  history: {
    state: "up" | "down";
    state_display: string;
    at: string;
    note: string | null;
    declared_by: string;
    ledger_index: number;
    recorded: string;
  }[];
  version: number;
  store_epoch: number;
}

/** Declarar el enlace simulado caído o restablecido desde un instante (de los datos). */
export interface LinkChange {
  state: "up" | "down";
  at: string;
  note: string;
  declared_by: string;
}

/** Los tres niveles de misión (`core/mission_modes.py`), de más medidas esperadas a menos. */
export type MissionLevel = "nominal" | "reduced" | "minimal";

/** Una medida del catálogo con los rasgos del coste de medir que la ponen de un lado o del otro. */
export interface MissionMeasure {
  key: string;
  name: string;
  mode: string;
  mode_display: string;
  consumables: string;
  consumables_display: string;
  crew_time_minutes: number | null;
  crew_time_basis: string;
  inputs: string[];
  /** Por qué se espera o se suspende, redactado por el backend. */
  why: string;
}

/**
 * El nivel de misión firmado (desconexión progresiva): qué medidas se siguen esperando. No cambia
 * la ingesta, el análisis, las alertas ni el modo seguro. `version` y `store_epoch` como en el
 * modo seguro (§5.38.13). Todo texto lo redacta el backend.
 */
export interface MissionModeState {
  level: MissionLevel;
  level_display: string;
  reason: string | null;
  declared_by: string | null;
  since: string | null;
  ledger_index: number | null;
  cited_system: string | null;
  cited_state: string | null;
  cited_system_display: string | null;
  cited_state_display: string | null;
  version: number;
  store_epoch: number;
  label: string;
  basis: string;
  rule: string;
  not_power: string;
  unchanged: string[];
  citable_systems: { key: string; display: string }[];
  citable_basis: string;
  levels: { key: MissionLevel; display: string; description: string; rank: number; expected: number }[];
  current: {
    key: MissionLevel;
    display: string;
    description: string;
    rank: number;
    expected: MissionMeasure[];
    suspended: MissionMeasure[];
  };
  /** Fuera de nominal, el aviso con la forma del del freno; en nominal, null. */
  notice: HaltNoticeText | null;
}

/** Lo que firma un cambio de nivel. El estado del sistema citado lo pone el backend. */
export interface MissionModeChange {
  level: MissionLevel;
  reason: string;
  declared_by: string;
  cited_system: string | null;
}

export const api = {
  /**
   * Con `until`, el estado solo con las lecturas hasta ese instante. Con `subject`, el de ese
   * tripulante; sin el, el que el backend da por defecto.
   */
  status: (until?: Date, subject?: string) =>
    request<CrewStatus>(`/status${queryOf({ until: until?.toISOString(), subject })}`).then(
      (status) => {
        // Las palabras de nivel son las de este estado: toda insignia las lee de aqui.
        adoptLevelLabels(status.level_labels);
        return status;
      },
    ),
  indicators: () => request<{ indicators: Indicator[] }>("/indicators"),
  scenarios: () => request<{ scenarios: Scenario[] }>("/scenarios"),
  audit: (limit = 20) => request<AuditReport>(`/audit?limit=${limit}`),
  observations: (key: string, limit = 5000, subject?: string, until?: string) =>
    request<{ observations: FhirObservation[] }>(
      `/observations?key=${encodeURIComponent(key)}&limit=${limit}` +
        (subject === undefined ? "" : `&subject=${encodeURIComponent(subject)}`) +
        (until === undefined ? "" : `&until=${encodeURIComponent(until)}`),
    ),
  /** Hemograma real de los cuatro tripulantes de Inspiration4 (NASA OSDR, OSD-569). */
  replayInspiration4: () =>
    request<{ recorded: number; excluded: string[]; citation: string; subjects: string[] }>(
      "/replay/inspiration4",
      { method: "POST" },
    ),
  resolveAlert: (body: {
    subject: string;
    domain: string;
    level: string;
    reference_time: string;
    state: "en_arreglo" | "resuelto";
    note: string;
    declared_by: string;
  }) => post<{ ledger_index: number }>("/alerts/resolution", body),
  dismissalReasons: () => request<DismissalReasons>("/alerts/dismissal-reasons"),
  /** Descartar una alerta concreta: firmado, con motivo; no cambia ningun calculo. */
  dismissAlert: (body: {
    subject: string;
    domain: string;
    level: string;
    reference_time: string;
    reason: string;
    note: string;
    declared_by: string;
  }) => post<{ ledger_index: number }>("/alerts/dismissal", body),
  acknowledge: (body: {
    subject: string;
    domain: string;
    level: string;
    reference_time: string;
    acknowledged_by: string;
  }) =>
    request<{ ledger_index: number }>("/alerts/acknowledge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  suppress: (body: AnnunciationRequest & { level: string; duration_minutes: number }) =>
    post<{ ledger_index: number; until: string }>("/alerts/suppress", body),
  inhibit: (body: AnnunciationRequest & { level: string; duration_hours: number }) =>
    post<{ ledger_index: number; until: string }>("/alerts/inhibit", body),
  enable: (body: AnnunciationRequest) => post<{ ledger_index: number }>("/alerts/enable", body),
  habitat: (until?: Date) =>
    request<HabitatState>(
      until === undefined ? "/habitat" : `/habitat?until=${encodeURIComponent(until.toISOString())}`,
    ),
  recovery: (subject: string) =>
    request<RecoveryReport>(`/replay/recovery?subject=${encodeURIComponent(subject)}`),
  anatomy: () => request<{ regions: AnatomyRegion[] }>("/anatomy"),
  anatomyState: (subject: string, until?: string) =>
    request<AnatomyState>(
      `/anatomy/state?subject=${encodeURIComponent(subject)}` +
        (until === undefined ? "" : `&until=${encodeURIComponent(until)}`),
    ),
  anatomySkeleton: () => request<AnatomySkeleton>("/anatomy/skeleton"),
  painOnSkeleton: (subject: string) =>
    request<PainOnSkeleton>(`/anatomy/pain-on-skeleton?subject=${encodeURIComponent(subject)}`),
  safeMode: () => request<SafeModeState>("/safe-mode"),
  kb: (query: string) =>
    request<{ available: boolean; note?: string; results: KbResult[] }>(
      `/kb?q=${encodeURIComponent(query)}`,
    ),
  chronicle: (subject: string) =>
    request<ChronicleView>(`/timeline/chronicle?subject=${encodeURIComponent(subject)}`),
  /** Episodios pasados, recalculados hoy. Con `until`, con lo que Tierra tiene. No escribe nada. */
  alertHistory: (subject: string, until?: Date) =>
    request<AlertHistory>(
      `/alerts/history${queryOf({ subject, until: until?.toISOString() })}`,
    ),
  week: (subject: string, days = 7) =>
    request<WeekView>(`/timeline/week?subject=${encodeURIComponent(subject)}&days=${days}`),
  waiting: (subject: string) =>
    request<WaitingView>(`/timeline/waiting?subject=${encodeURIComponent(subject)}`),
  routines: (subject: string) =>
    request<RoutinesView>(
      `/timeline/routines?subject=${encodeURIComponent(subject)}`,
    ),
  dependsOn: (key: string) => request<DependsView>(`/timeline/depends/${encodeURIComponent(key)}`),
  setSafeMode: (body: { active: boolean; reason: string; declared_by: string }) =>
    post<SafeModeState>("/safe-mode", body),
  /** El nivel de misión vigente; con `until`, el firmado hasta el corte de Tierra. Solo lee. */
  missionMode: (until?: Date) =>
    request<MissionModeState>(`/mission-mode${queryOf({ until: until?.toISOString() })}`),
  setMissionMode: (body: MissionModeChange) => post<MissionModeState>("/mission-mode", body),
  /** El enlace con Tierra simulado y el corte de Tierra con él, dado el del tiempo de luz. */
  linkSync: (lightCut: Date | null) =>
    request<LinkSync>(`/link-sync${queryOf({ light_cut: lightCut?.toISOString() })}`),
  setLinkSync: (body: LinkChange) => post<LinkSync & { ledger_index: number }>("/link-sync", body),
  habitatParameters: () =>
    request<{ parameters: HabitatParameter[]; display_only?: HabitatDisplayOnly[] }>(
      "/habitat/parameters",
    ),
  habitatModules: () => request<HabitatModules>("/habitat/modules"),
  /** Las anclas de módulo vigentes (equipo de la nave que el wearable oye), con su base. */
  locationAnchors: () => request<LocationAnchors>("/location/anchors"),
  /**
   * Declara en qué módulo está instalada un ancla. Va al registro firmado; no se borra nada: se
   * corrige declarando de nuevo, y vale la última. Lleva la cabecera de la consola (`post`).
   */
  declareAnchor: (body: { anchor_id: string; module: string; since: string; declared_by: string }) =>
    post<{ ledger_index: number }>("/location/anchors", body),
  missionShift: () => request<ShiftBasis>("/mission/shift"),
  habitatSystems: (until?: Date) =>
    request<HabitatSystems>(`/habitat/systems${queryOf({ until: until?.toISOString() })}`),
  declareSystemStatus: (body: {
    system: string;
    state: string;
    module?: string;
    at: string;
    note: string;
    declared_by: string;
  }) => post<{ ledger_index: number }>("/habitat/systems/status", body),
  sensorBindings: () => request<SensorBindings>("/sensor-bindings"),
  declareSensorBinding: (body: {
    source: string;
    device?: string;
    action: "bind" | "unbind";
    crew?: string;
    since: string;
    note: string;
    declared_by: string;
  }) => post<{ ledger_index: number }>("/sensor-bindings", body),
  resources: () => request<ResourcesOverview>("/resources"),
  declareResource: (body: {
    resource: string;
    state: string;
    since: string;
    note: string;
    declared_by: string;
  }) => post<{ ledger_index: number }>("/resources", body),
  crew: (until?: Date) =>
    request<CrewOverview>(
      until === undefined ? "/crew" : `/crew?until=${encodeURIComponent(until.toISOString())}`,
    ),
  /**
   * Quienes forman la tripulacion conocida, sin analisis: para elegir a quien se mira. Con
   * `until`, solo quien ya tiene alguna lectura llegada a Tierra.
   */
  crewMembers: (until?: Date) =>
    request<{ crew: { subject: string }[] }>(
      `/crew/members${queryOf({ until: until?.toISOString() })}`,
    ),
  /**
   * El mismo indicador en cada tripulante, cada uno contra su propia linea base. Con `until`,
   * solo lo que Tierra puede conocer.
   */
  crewCompare: (
    key: string,
    options: { parameter?: string | undefined; until?: Date | undefined; hours?: number } = {},
  ) =>
    request<CrewCompare>(
      `/crew/compare${queryOf({
        key,
        parameter: options.parameter,
        until: options.until?.toISOString(),
        hours: options.hours,
      })}`,
    ),
  declareProfile: (body: {
    subject: string;
    prior_missions: number;
    prior_career_dose_msv: number | null;
    declared_by: string;
  }) => post<{ ledger_index: number }>("/crew/profile", body),
  /** El historial misión a misión y su cotejo con el perfil. Con `until`, el del corte de Tierra. */
  missionHistory: (subject: string, until?: Date) =>
    request<MissionHistory>(
      `/crew/mission-history${queryOf({ subject, until: until?.toISOString() })}`,
    ),
  /** Se declara la lista entera; vale la última. No toca el perfil ni su dosis previa. */
  declareMissionHistory: (body: { subject: string; missions: PriorMissionIn[]; declared_by: string }) =>
    post<{ ledger_index: number }>("/crew/mission-history", body),
  declareMissionEvent: (body: {
    /** De quien es el evento: el tripulante del estado en pantalla, nunca uno por defecto. */
    subject: string;
    kind: string;
    start: string;
    end: string;
    /** Opcional solo en una ubicacion: sin ella, el asiento lleva el nombre del modulo. */
    label?: string;
    declared_by: string;
    /** Solo en una ubicacion: en que modulo de la lista declarada. */
    module?: string;
  }) => post<{ ledger_index: number }>("/mission/events", body),
  reviewHypothesis: (body: {
    decision: "confirmed" | "discarded";
    parameter: string;
    excursion_start: string;
    reason: string;
    decided_by: string;
  }) => post<{ ledger_index: number }>("/crew/hypotheses/review", body),
  countermeasureLibrary: () => request<CountermeasureLibrary>("/countermeasures"),
  /** Las contramedidas en investigación: se enseñan aparte y no se ofrecen. */
  researchCountermeasures: () => request<ResearchCountermeasures>("/countermeasures/research"),
  /** Cómo se toma cada medida, paso a paso (`backend/app/guides.py`). */
  measurementGuides: () => request<MeasurementGuides>("/guides"),
  /** Los términos de la consola, con el origen de cada definición. */
  glossary: () => request<Glossary>("/glossary"),
  adoptCountermeasure: (body: {
    subject: string;
    countermeasure_id: string;
    reference_time: string;
    adopted_by: string;
  }) => post<{ ledger_index: number }>("/countermeasures/adopt", body),
  /** Deja firmado, con motivo, que una contramedida recomendada no se adopta. */
  declineCountermeasure: (body: {
    subject: string;
    countermeasure_id: string;
    reference_time: string;
    reason: string;
    declined_by: string;
  }) => post<{ ledger_index: number }>("/countermeasures/decline", body),
  closeFollowup: (body: {
    subject: string;
    adoption_index: number;
    reason: string;
    closed_by: string;
  }) => post<{ ledger_index: number }>("/countermeasures/close", body),
  imaging: {
    protocols: () => request<ProtocolCatalog>("/imaging/protocols"),
    /** Con `until`, solo lo registrado a bordo hasta ese instante: lo que Tierra ya tiene. */
    studies: (subject: string, until?: Date) =>
      request<ImagingStudy[]>(
        `/imaging/studies?subject=${encodeURIComponent(subject)}` +
          (until === undefined ? "" : `&until=${encodeURIComponent(until.toISOString())}`),
      ),
    /** El DICOM tal cual sale del equipo; el backend lo des-identifica antes de guardarlo. */
    upload: (file: Blob, protocol: string, subject: string, acquired?: string) =>
      request<UploadResult>(
        `/imaging/studies?protocol=${encodeURIComponent(protocol)}` +
          `&subject=${encodeURIComponent(subject)}` +
          (acquired ? `&acquired=${encodeURIComponent(acquired)}` : ""),
        { method: "POST", headers: { "Content-Type": "application/dicom" }, body: file },
      ),
    /** Fantoma sintetico de un protocolo con medida: entra firmado como simulado. */
    phantom: (protocol: string, subject: string) =>
      request<{ ledger_index: number; ground_truth: Record<string, number> }>(
        `/imaging/phantom?protocol=${encodeURIComponent(protocol)}&subject=${encodeURIComponent(subject)}`,
        { method: "POST" },
      ),
    samples: () => request<ImagingSample[]>("/imaging/samples"),
    /** Ecografia real de ejemplo: de un paciente de un dataset, no de este tripulante. */
    sample: (key: string, subject: string) =>
      request<{ ledger_index: number; protocol: string; dataset: DatasetCitation }>(
        `/imaging/samples/${encodeURIComponent(key)}?subject=${encodeURIComponent(subject)}`,
        { method: "POST" },
      ),
    interpretation: () =>
      request<{ available: boolean; model: string; committee: string[]; note: string | null }>(
        "/imaging/interpretation",
      ),
    drafts: (study: number) => request<InterpretationDraft[]>(`/imaging/studies/${study}/drafts`),
    requestDraft: (study: number) =>
      request<{ ledger_index: number; status: string; text: string }>(
        `/imaging/studies/${study}/draft`,
        { method: "POST" },
      ),
    signDraft: (draft: number, body: SignoffBody) =>
      post<{ ledger_index: number }>(`/imaging/drafts/${draft}/sign`, body),
    /** Segunda firma, de otra persona, de una decision de alto riesgo. */
    countersignDraft: (draft: number, body: SignoffBody) =>
      post<{ ledger_index: number; collation?: SecondSignatureCollation | null }>(
        `/imaging/drafts/${draft}/countersign`,
        body,
      ),
    findings: (study: number) => request<RecordedFindings[]>(`/imaging/studies/${study}/findings`),
    recordFindings: (
      study: number,
      body: {
        checklist: Record<string, boolean>;
        findings: Record<string, Record<string, string>>;
        recorded_by: string;
      },
    ) => post<{ ledger_index: number }>(`/imaging/studies/${study}/findings`, body),
    measurements: (study: number) =>
      request<MeasurementRecord[]>(`/imaging/studies/${study}/measurements`),
    measure: (study: number, body: MeasurementRequest) =>
      post<MeasurementResult>(`/imaging/studies/${study}/measurements`, body),
  },
  volumes: {
    segmenter: () =>
      request<{
        available: boolean;
        note: string | null;
        presets: { key: string; nombre: string; estructuras: string[]; lesiones: boolean }[];
      }>("/volumes/segmenter"),
    list: (subject: string) => request<VolumeStudy[]>(`/volumes?subject=${encodeURIComponent(subject)}`),
    upload: (file: Blob, modality: "CT" | "MR", subject: string, recordedBy: string) =>
      request<{ ledger_index: number }>(
        `/volumes?modality=${modality}&subject=${encodeURIComponent(subject)}` +
          `&recorded_by=${encodeURIComponent(recordedBy)}`,
        { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file },
      ),
    segment: (study: number, preset: string) =>
      request<{ job: string; state: string }>(`/volumes/${study}/segment?preset=${encodeURIComponent(preset)}`, {
        method: "POST",
      }),
    job: (job: string) =>
      request<{ state: "running" | "done" | "failed"; error?: string; ledger_index?: number }>(
        `/volumes/jobs/${job}`,
      ),
    samples: () => request<VolumeSample[]>("/volumes/samples"),
    sample: (key: string, subject: string) =>
      request<{ ledger_index: number; segmentation: number }>(
        `/volumes/samples/${encodeURIComponent(key)}?subject=${encodeURIComponent(subject)}`,
        { method: "POST" },
      ),
    compare: (before: number, after: number) =>
      request<LesionComparison>(`/volumes/compare?before=${before}&after=${after}`),
    contrastPhases: () => request<ContrastPhaseVocabulary>("/volumes/contrast-phases"),
    declareContrastPhase: (study: number, body: { phase: string; declared_by: string; note: string }) =>
      post<{ ledger_index: number }>(`/volumes/${study}/contrast-phase`, body),
  },
  reports: {
    ocr: () => request<{ available: boolean; engine: string | null; note: string | null }>("/reports/ocr"),
    list: (subject: string) => request<ScannedReport[]>(`/reports?subject=${encodeURIComponent(subject)}`),
    upload: (file: Blob, kind: ReportKind, subject: string, recordedBy: string) =>
      request<{ ledger_index: number; pages: number; low_confidence_pages: number[] }>(
        `/reports?kind=${kind}&subject=${encodeURIComponent(subject)}` +
          `&recorded_by=${encodeURIComponent(recordedBy)}`,
        { method: "POST", headers: { "Content-Type": file.type }, body: file },
      ),
    incongruences: (subject: string) =>
      request<LabIncongruences>(`/reports/incongruences?subject=${encodeURIComponent(subject)}`),
    confirmLab: (
      report: number,
      body: {
        reading_index: number;
        confirmed_by: string;
        effective_date: string;
        value?: number;
        unit?: string;
      },
    ) => post<{ observation_index: number; ledger_index: number }>(`/reports/${report}/labs/confirm`, body),
    identity: (subject: string) =>
      request<CrewIdentity>(`/crew/identity?subject=${encodeURIComponent(subject)}`),
    declareIdentity: (body: {
      subject: string;
      given_name: string;
      surnames: string;
      birth_date: string;
      declared_by: string;
    }) => post<{ ledger_index: number }>("/crew/identity", body),
  },
  pain: {
    catalog: () => request<PainCatalog>("/pain/catalog"),
    /** Con `until`, solo lo registrado a bordo hasta ese instante: lo que Tierra ya tiene. */
    reports: (subject: string, until?: Date) =>
      request<PainReport[]>(
        `/pain/reports?subject=${encodeURIComponent(subject)}` +
          (until === undefined ? "" : `&until=${encodeURIComponent(until.toISOString())}`),
      ),
    record: (body: {
      subject: string;
      reported_by: string;
      zones: { zone: string; intensity: number; characters: string[] }[];
      note?: string;
      note_origin?: "escrita" | "dictada-revisada" | "asistente-confirmada";
    }) => post<{ recorded: number[]; intensity: number; discuss: PainDiscussion }>("/pain/reports", body),
    voice: () => request<{ available: boolean; model: string }>("/pain/voice"),
    /** Borrador de la nota a partir de un audio Ogg/Opus: no se firma aqui. */
    transcribe: (audio: Blob) =>
      request<{ draft: string; model: string; origin: "dictada-revisada" }>("/pain/voice", {
        method: "POST",
        headers: { "Content-Type": "audio/ogg" },
        body: audio,
      }),
  },
  /** Con `replace`, sustituye la sesion simulada entera: la API se niega si hay datos reales. */
  simulate: (scenario: string, replace = false) =>
    request<{ recorded: number; replaced: boolean }>(
      `/simulate?scenario=${encodeURIComponent(scenario)}${replace ? "&replace=true" : ""}`,
      { method: "POST" },
    ),
};

/** La ficha de una herramienta de Polaris, tal cual la escribio su autora (`polaris/tools/fichas/`). */
export interface PolarisCard {
  para?: string;
  test?: string;
  estado_ficha?: string;
  [field: string]: string | undefined;
}

export interface PolarisTool {
  herramienta: string;
  /**
   * Si importa en la maquina donde corre el backend. `null`: el inventario no la importa a
   * proposito (hace algo solo con importarse), asi que no se sabe si cargaria.
   */
  carga: boolean | null;
  /** El estado con las palabras del backend: "carga", "no carga" o "no se importa". Se muestra tal cual. */
  estado: string;
  /** Por que no carga o por que no se importa, literal; `null` si carga. */
  motivo: string | null;
  /** Si el codigo de EMMA la pide por su nombre (lista declarada y atada por prueba en el backend). */
  en_uso: boolean;
  ficha: PolarisCard | null;
}

/** Un cambio decidido sobre la copia (`polaris/CAMBIOS.json`, AGPL §5a). */
export interface PolarisChange {
  ruta: string | null;
  fecha: string | null;
  motivo: string | null;
  reemplazos: number;
}

/** `GET /api/polaris/estado`: la copia de Polaris de esta instalacion, leida de sus propios ficheros. */
export interface PolarisStatus {
  origen: string;
  /** `null` si la instalacion no trae `polaris/ADOPTADO.txt`. */
  commit: string | null;
  /** `cargan`, las que no cargan y `no_se_importan` suman `total`. */
  cargan: number;
  total: number;
  en_uso: number;
  /** Las que el inventario no importa a proposito, cada una con su motivo literal. */
  no_se_importan: { herramienta: string; motivo: string | null }[];
  herramientas: PolarisTool[];
  cambios: PolarisChange[];
  /** Ficheros opcionales de la copia que no estan en esta instalacion. */
  faltan: string[];
}

export const polarisApi = {
  status: () => request<PolarisStatus>("/polaris/estado"),
};

/**
 * El PDF de las anotaciones de dolor (`GET /api/export/dolor.pdf`), con el mismo corte de Tierra
 * que `exportPdfUrl`. Va aparte porque este fichero solo admite anadidos al final.
 */
export function painPdfUrl(subject: string, until: Date | null): string {
  const cut = until === null ? "" : `&until=${encodeURIComponent(until.toISOString())}`;
  return `/api/export/dolor.pdf?subject=${encodeURIComponent(subject)}${cut}`;
}


/**
 * La frase literal que la boveda da para una cita `informe:<n>`: el texto des-identificado del
 * informe, tal cual. `no_localizada` no trae frase (nunca el fragmento tecleado); `no_aplica` es
 * una fuente que no es un informe.
 */
export interface SourceQuote {
  estado: "localizada" | "no_localizada" | "no_aplica";
  frase: string;
  detalle: string;
  puntero?: string;
  informe?: number;
  /** El asiento del registro que firma el informe. */
  asiento?: number;
  inicio?: number | null;
  fin?: number | null;
  /** Huella del texto de la boveda del que sale la frase. */
  sha256?: string | null;
  desidentificado?: boolean;
  /** Solo en una firma ya hecha: si declaro lo que vio antes de firmar. */
  vista?: boolean;
}

/** Lo que vio quien pone la segunda firma: si la boveda ya no da eso, el backend no firma. */
export interface SeenQuote {
  estado: "localizada" | "no_localizada";
  frase: string;
  sha256: string | null;
}

// Campos que se suman a tipos declarados mas arriba (las interfaces de TypeScript se funden por nombre).
export interface DraftSignoff {
  /**
   * En una firma que cita un informe y vio su frase (la segunda, siempre desde el 2026-10-13; la
   * primera, si la pidio ver). `no_aplica` solo en segundas firmas de antes del 2026-10-15 que
   * citaban otra fuente; desde entonces la segunda firma tiene que citar un informe.
   */
  source_quote?: SourceQuote;
}

export interface SignoffBody {
  /** Lo que se vio al pedir la frase. Obligatorio en la segunda firma, que cita un informe. */
  seen_quote?: SeenQuote;
}

/** Los textos de la regla de la segunda firma (`app/countersign_rule.py`): se pintan tal cual. */
export interface SecondSignatureRule {
  since: string;
  /** Lo que hace falta: citar un informe guardado, con la frase localizada y declarada leida. */
  must_cite: string;
  must_look: string;
  declaration: string;
  must_declare: string;
  /** Por que una fuente que no es un informe guardado no vale para la segunda firma. */
  not_collatable: string;
}

/** Lo que la lectura previa dice de la segunda firma con esa cita; `reason` es el texto del 422. */
export interface SecondSignatureGate {
  collatable: boolean;
  allowed: boolean;
  reason: string | null;
}

export interface InterpretationDraft {
  second_signature_rule?: SecondSignatureRule;
  /** Rotulo, derivado al leer, de una contrafirma admitida con la regla anterior; el asiento no cambia. */
  countersign_note?: string | null;
  /** Si la segunda firma se cotejo con la frase de un informe y, si no, por que; derivado al leer. */
  countersign_collation?: SecondSignatureCollation | null;
}

/** `countersign_rule.collation`: «cotejada» o «no cotejada» y por que. `text` se pinta tal cual. */
export interface SecondSignatureCollation {
  collated: boolean;
  label: string;
  why: string | null;
  text: string;
}

export const sourceQuoteApi = {
  /** Ver la frase antes de firmar. Lectura: no escribe en el registro ni sale a la red. */
  preview: (draft: number, body: { source: string; source_fragment: string; signed_by: string }) =>
    post<{ source: string; quote: SourceQuote; second_signature?: SecondSignatureGate }>(
      `/imaging/drafts/${draft}/source-quote`,
      body,
    ),
};

/** Un hueso de la figura del esqueleto: su centroide en fraccion de la imagen y su nombre. */
export interface SkeletonBone {
  u: number;
  v: number;
  display: string;
  /** Llega al borde del estudio: el punto es el centro del trozo que entra en el TAC. */
  truncated: boolean;
}

export interface NamedBone {
  name: string;
  display: string;
}

/**
 * `GET /api/anatomy/skeleton/own`: el esqueleto que se enseña de un tripulante. `source` dice si
 * sale de su TAC (backend `volumes/skeleton_view.py`) o es el de referencia; los rotulos (`label`,
 * `alt`, `caption`, `notes`, `fallback_reason`) los redacta el backend y se muestran tal cual.
 */
export interface SubjectSkeleton {
  region: string;
  width: number;
  height: number;
  bones: Record<string, SkeletonBone>;
  attribution: string | null;
  source: "own-ct" | "reference";
  label: string;
  alt: string;
  caption: string;
  /** El TAC es un ejemplo de un dataset abierto, firmado como simulado: no es el tripulante. */
  simulated: boolean;
  ledger: {
    segmentation_index: number;
    segmentation_recorded: string;
    study_index: number;
    study_recorded: string;
  } | null;
  extent_mm: { x: [number, number]; z: [number, number] } | null;
  absent_bones: NamedBone[];
  truncated_bones: NamedBone[];
  notes: string[];
  spine: { nivel: string | null; aviso: string | null; listas: SpineReviewList[] } | null;
  fallback_reason: string | null;
  /** Por que se ve la de referencia: sin esqueleto propio, o con uno que no se puede usar. */
  fallback_kind: "no-segmentation" | "not-usable" | null;
}

/** Dolor referido con la zona fuera de lo que cubre el estudio: se dice, no se pinta. */
export interface PainOutsideStudy {
  zone: string;
  display: string;
  reason: string;
  reports: number;
  last: string;
  intensity: number | null;
}

/**
 * `GET /api/anatomy/pain-on-skeleton` sobre la figura del tripulante: dice sobre cual se coloco
 * (`source`, `segmentation_index`) y, si no se superpone, por que (`reason`, texto del backend).
 */
export interface PainOnSubjectSkeleton extends Omit<PainOnSkeleton, "error_px"> {
  error_px: PainOnSkeleton["error_px"] | null;
  source: "own-ct" | "reference";
  segmentation_index: number | null;
  anchors: number;
  reason: string | null;
  outside_study: PainOutsideStudy[];
}

export const skeletonApi = {
  own: (subject: string) =>
    request<SubjectSkeleton>(`/anatomy/skeleton/own?subject=${encodeURIComponent(subject)}`),
  pain: (subject: string) =>
    request<PainOnSubjectSkeleton>(
      `/anatomy/pain-on-skeleton?subject=${encodeURIComponent(subject)}`,
    ),
};

/**
 * Un volumen guardado limpio (`POST /api/volumes?clean=true`): lo que el asiento firmado declara.
 * `fields` son nombres de campo, nunca su contenido; `note` la redacta el backend.
 */
export interface VolumeCleaning {
  fields: string[];
  received_sha256: string;
  received_size_bytes: number;
  note: string;
}

/** Anadido a `VolumeStudy` (fusion de declaraciones: este fichero solo admite anadidos al final). */
export interface VolumeStudy {
  /** Huella del NIfTI guardado y firmado. */
  sha256?: string;
  /** Solo si la cabecera se limpio en EMMA al entrar, a peticion del operador. */
  cleaned?: VolumeCleaning;
}

/**
 * La fase de contraste de un TAC tal y como la declaro una persona (backend
 * `volumes/contrast_phase.py`). `display` es el nombre de la fase, redactado por el backend; `at`
 * es cuando lo dijo quien lo declaro y `recorded` cuando se firmo el asiento.
 */
export interface ContrastPhaseDeclaration {
  code: string;
  display: string;
  declared_by: string;
  at: string;
  note: string | null;
  ledger_index: number;
  recorded: string;
}

/** Lo que consta de la fase de un estudio: la vigente (o ninguna: sin declarar) y su historial. */
export interface ContrastPhaseView {
  applicable: boolean;
  not_applicable_reason: string | null;
  current: ContrastPhaseDeclaration | null;
  undeclared_display: string;
  label: string;
  history: ContrastPhaseDeclaration[];
}

/** El vocabulario cerrado de fases que se pueden declarar, con los textos que lo acompanan. */
export interface ContrastPhaseVocabulary {
  phases: { code: string; display: string }[];
  undeclared_display: string;
  modality: string;
  label: string;
  basis: string;
  rule: string;
  scope: string;
}

/** Las fases de dos estudios en la comparacion. `estado` es una clave; `texto` lo redacta el backend. */
export interface ContrastPhaseComparison {
  estado: string;
  texto: string;
  antes: ContrastPhaseDeclaration | null;
  despues: ContrastPhaseDeclaration | null;
  sin_declarar: string;
  etiqueta: string;
}

/** Anadido a `VolumeStudy`: la fase de contraste declarada. */
export interface VolumeStudy {
  contrast_phase?: ContrastPhaseView;
}

/** Anadido a `LesionComparison`: lo que consta de las fases de los dos estudios. */
export interface LesionComparison {
  fase_contraste?: ContrastPhaseComparison;
}

/**
 * Sube un volumen y devuelve la respuesta sin interpretar: el rechazo de la puerta de datos
 * personales (422) trae mas que `detail` —si limpiar serviria y el texto de la oferta—, y
 * `request` solo conserva `detail`. Lo interpreta `volumes/upload.ts`, que tiene su prueba.
 * `clean` solo viaja cuando el operador ha pulsado el boton de limpiar.
 */
export async function postVolume(
  file: Blob,
  modality: "CT" | "MR",
  subject: string,
  recordedBy: string,
  clean: boolean,
): Promise<{ status: number; body: unknown }> {
  const response = await fetch(
    `/api/volumes?modality=${modality}&subject=${encodeURIComponent(subject)}` +
      `&recorded_by=${encodeURIComponent(recordedBy)}${clean ? "&clean=true" : ""}`,
    withConsoleHeader({
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: file,
    }),
  );
  let body: unknown = { detail: response.statusText };
  try {
    body = await response.json();
  } catch {
    // cuerpo no JSON: se queda el texto de estado
  }
  return { status: response.status, body };
}

/** Una pieza de EMMA que toca una hipotesis de diseño: modulo y, si la hay, su ruta. */
export interface DesignHypothesisTouch {
  module: string;
  method: "GET" | "POST" | null;
  route: string | null;
  what: string;
}

/**
 * Una hipotesis H1-H7 de la base de conocimiento del equipo (§13), con su enunciado literal.
 * Ningun `status` es "probada": la frase de cada estado (`status_text`) la escribe el backend.
 */
export interface DesignHypothesis {
  /** Con prefijo `KB-`: "H1…H18" a secas son los peligros del expediente de riesgos. */
  id: string;
  label: string;
  statement: string;
  status: string;
  status_text: string;
  /** Con que datos reales y con que alcance; `null` salvo en el estado que los declara. */
  real_data: string | null;
  scenario: string | null;
  documents: string[];
  touches: DesignHypothesisTouch[];
  not_demonstrated: string;
}

/** Un anclaje de la especificacion (§16) que nadie ha leido: solo identificadores, sin resumen. */
export interface UnreadAnchor {
  anchor: string;
  listed_in: string;
  status: string;
  status_text: string;
  references: { ntrs: string; title: string; url: string }[];
}

export interface DesignHypotheses {
  source: { document: string; section: string; title: string };
  note: string;
  statuses: { id: string; text: string }[];
  hypotheses: DesignHypothesis[];
  unread_anchors: UnreadAnchor[];
}

/**
 * Una frase leida en una fuente oficial de NASA: literal (`quote`), con su seccion (`where`),
 * su direccion, la ficha del registro de evidencia y cuanto se leyo del documento. `note` es
 * de EMMA. Todo lo escribe el backend (`app/evidence/nasa_framework.py`).
 */
export interface ReadStatement {
  id: string;
  label: string;
  quote: string;
  ref: string;
  source: string;
  title: string;
  url: string;
  where: string;
  /** Dia en que se leyo la fuente, ISO 8601. */
  read_on: string;
  extent: string;
  extent_text: string;
  note: string | null;
  /** Si la frase da el estado de un hueco del Human Research Roadmap: cual y en que estado. */
  gap: { id: string; status: string; status_text: string } | null;
}

/** El estado leido de un hueco del Roadmap, con la frase y la pagina que lo dicen. */
export interface GapStatus {
  id: string;
  /** open, closed, merged, archived o split, como lo publica la pagina del hueco. */
  status: string;
  status_text: string;
  statement: string;
  quote: string;
  where: string;
  url: string;
  source: string;
  /** Dia en que se leyo la pagina, ISO 8601. */
  read_on: string;
}

/**
 * Una pregunta que lo leido contesta (decimoquinta ronda: si IMPACT ha sustituido al IMM).
 * `answer` la redacta el backend con las palabras de las frases; `rests_on` son las frases del
 * bloque en que se apoya, en su orden, con la fecha de su documento (AAAA, AAAA-MM o
 * AAAA-MM-DD). El backend exige que entre ellas este la del documento mas reciente del bloque.
 */
export interface ReadQuestion {
  text: string;
  answer: string;
  rests_on: { id: string; label: string; date: string }[];
}

/**
 * Una fila de la tabla de cobertura (decimoseptima ronda, el CDSS de ExMC punto por punto): lo
 * que pide una frase del bloque (`asks`, letra por letra de su `quote`), que hace EMMA con ello y
 * en que ficheros. `coverage` es covered, partial u outside; su palabra, `coverage_text`.
 */
export interface ReadCoverageRow {
  statement: string;
  label: string;
  asks: string;
  coverage: string;
  coverage_text: string;
  emma: string;
  /** Rutas del repositorio; vacia solo si EMMA no lo hace. */
  files: string[];
}

export interface ReadCoverage {
  /** Que quiere decir «cubre» en esta tabla: lo escribe el backend. */
  about: string;
  /** Cuantas filas hay de cada cobertura, contadas por el backend. */
  counts: Record<string, number>;
  rows: ReadCoverageRow[];
}

/** Un bloque de lo leido: que dice la fuente y, aparte, que hace EMMA y que no se leyo. */
export interface ReadBlock {
  id: string;
  title: string;
  about: string;
  statements: ReadStatement[];
  /** La pregunta que contesta lo leido del bloque; `null` si no lleva. */
  question: ReadQuestion | null;
  /** Lo que pide cada frase y que hace EMMA; `null` si el bloque no lleva tabla. */
  coverage: ReadCoverage | null;
  emma: string;
  not_read: string[];
}

export interface ReadSources {
  note: string;
  /** Dia de la primera lectura, ISO 8601. Cada frase y cada fuente llevan el suyo: se pinta ese. */
  read_on: string;
  extents: { id: string; text: string }[];
  gap_statuses: { id: string; text: string }[];
  /** Las coberturas de una tabla de cobertura y su palabra, en el orden del backend. */
  coverages: { id: string; text: string }[];
  sources: {
    ref: string;
    title: string;
    url: string | null;
    /** Dia en que se leyo esta fuente, ISO 8601: no todas se leyeron el mismo dia. */
    read_on: string;
    extent: string;
    extent_text: string;
    what: string;
  }[];
  blocks: ReadBlock[];
}

/** `GET /api/framework`: el marco de NASA en que se inscribe EMMA. Inventario, no estado clinico. */
export interface Framework {
  standard: string;
  exmc_gaps: {
    source: string;
    url: string;
    /** Que los enunciados son de 2020 y que cada uno lleva su estado leido hoy. */
    note: string;
    med07: { label: string; gap: string; status: GapStatus; emma: string };
    med10: { label: string; gap: string; status: GapStatus; merged_into: GapStatus; emma: string };
  };
  imm: { url: string; what: string; not_duplicated: string };
  /** Peligro RIDGE de cada dominio; la clave es la del dominio en la API. */
  ridge: Record<string, { hazard: string; display: string }>;
  design_hypotheses: DesignHypotheses;
  /** Lo leido en las fuentes oficiales, con su cita. Citar no es implementar. */
  read_sources: ReadSources;
  /**
   * Cada cifra INFERIDA o PREDICHA con los factores de NASA-STD-7009B, sin nivel; `null` si el
   * fichero de fichas no pasa su contrato en el backend (el resto del marco se sirve igual).
   */
  credibility: Credibility | null;
}

/** Un factor de credibilidad de NASA-STD-7009B, con su pregunta literal (tablas 5 y 12). */
export interface CredibilityFactor {
  id: string;
  /** Nombre en la norma, en inglés. */
  name: string;
  name_es: string;
  question: string;
  where: string;
}

/** Lo que hay en un factor para una capa: en palabras, sin nivel ni puntuación. */
export interface CredibilityState {
  group: string;
  id: string;
  name_es: string;
  state: string;
}

/** La ficha de credibilidad de una cifra INFERIDA o PREDICHA (`app/evidence/credibility.py`). */
export interface CredibilityLayer {
  id: string;
  display: string;
  observation_type: string;
  observation_type_text: string;
  /** El de la cifra; `null` si no lo lleva, y entonces `model_note` dice por qué. */
  model_version: string | null;
  model_note: string | null;
  sites: string[];
  served_in: string[];
  tests: string[];
  factors: CredibilityState[];
  /**
   * Lo que hay en los dos ejes de criticidad del Apéndice D, en su orden; sin casilla. Un backend
   * anterior a la decimoctava ronda no lo manda.
   */
  criticality?: CredibilityAxisState[];
}

/** Lo que hay en un eje de criticidad para una capa: en palabras, sin categoría de la matriz. */
export interface CredibilityAxisState {
  axis: string;
  name_es: string;
  state: string;
}

/** Lo leído del Apéndice D de NASA-STD-7009B (criticidad del uso), con su día: sin aplicar. */
export interface CredibilityCriticality {
  read_on: string;
  title: string;
  about: string;
  /** Que la matriz no se ha aplicado a ninguna capa, y por qué. */
  not_applied: string;
  statements: { id: string; label: string; quote: string; where: string; source: string; ref: string }[];
  axes: { id: string; name: string; name_es: string; quote: string; where: string }[];
}

/** `GET /api/framework` → `credibility`: la norma leída y una ficha por capa. Inventario. */
export interface Credibility {
  note: string;
  title: string;
  about: string;
  read_on: string;
  sources: {
    ref: string;
    title: string;
    source: string;
    url: string | null;
    date: string | null;
    read_on: string;
    extent: string;
    extent_text: string;
    what: string;
  }[];
  statements: { id: string; label: string; quote: string; where: string; source: string; ref: string }[];
  groups: {
    id: string;
    name: string;
    name_es: string;
    requirement: string;
    quote: string;
    where: string;
    factors: CredibilityFactor[];
  }[];
  /** Que ninguna capa se ha evaluado con las tablas de nivel de la norma. */
  not_assessed: string;
  emma: string;
  layers: CredibilityLayer[];
  /** Lo leído del Apéndice D; un backend anterior a la decimoctava ronda no lo manda. */
  criticality?: CredibilityCriticality;
  out_of_scope: string[];
  not_read: string[];
}

export const frameworkApi = {
  get: () => request<Framework>("/framework"),
};

/** Una frase literal de la página de un banco, con su ficha del registro (`app/evidence/testbeds.py`). */
export interface TestbedQuote {
  quote: string;
  where: string;
  /** El día en que se leyó la frase en su página (el del banco o el de su columna). */
  read_on: string;
  ref: string;
  source: string;
  url: string | null;
  organization: string | null;
  /** ISO 8601 con la precisión que dé la fuente; `null` si la página no la muestra. */
  date: string | null;
  /** Campos de la ficha sin verificar, con su nombre en español. */
  unverified_display: string[];
}

/** Lo que un banco deja fuera: lo dice la fuente (con su frase) o lo deduce EMMA (con su motivo). */
export interface TestbedLeftOut {
  what: string;
  basis: "source" | "deduced";
  basis_text: string;
  why: string | null;
  cited: TestbedQuote | null;
}

/**
 * Una de las columnas que pedía la conversación de ideación (duración, participantes, datos,
 * proveedores):
 * la frase de la fuente o, si ninguna página leída la da, dónde se buscó. Nunca las dos.
 */
export interface TestbedColumn {
  id: string;
  /** El rótulo lo da el backend. */
  label: string;
  read_on: string;
  quotes: TestbedQuote[];
  not_found: string | null;
}

/**
 * Una celda de la matriz banco × peligro RIDGE: deducida por EMMA (con su motivo) o, donde la
 * ficha de NASA del banco nombra el peligro que estudia, con esa frase. Las palabras las da el
 * backend.
 */
export interface TestbedRidgeCell {
  hazard: string;
  hazard_display: string;
  status: "reproduces" | "partial" | "leaves_out" | "unknown";
  status_text: string;
  basis: "source" | "deduced";
  basis_text: string;
  why: string | null;
  cited: TestbedQuote | null;
}

export interface Testbed {
  id: string;
  name: string;
  full_name: string | null;
  where: string;
  read_on: string;
  rung: string;
  validation: string;
  validation_text: string;
  /** Un valor del enumerado de las observaciones, o `null` si ninguno lo cubre. */
  evidence_context: string | null;
  outside_enum_text: string | null;
  context_basis: string;
  reproduces: TestbedQuote[];
  leaves_out: TestbedLeftOut[];
  columns: TestbedColumn[];
  /** El día en que se hizo la fila del banco en la matriz RIDGE. */
  ridge_read_on: string;
  /** Los cinco peligros RIDGE, en su orden: qué reproduce el banco de cada uno. */
  ridge: TestbedRidgeCell[];
  /** Las variables del banco según la base de conocimiento (§3.1), o `null`. */
  variables_kb: string | null;
  emma_use: string;
}

/** Lo que EMMA tiene de una validación: un conjunto de datos, lo que no muestra y dónde están las cifras. */
export interface TestbedEmmaPart {
  id: string;
  ref: string;
  context: string;
  bank: string | null;
  what: string;
  does_not_show: string;
  figures_in: string;
  source: string;
  url: string | null;
}

export interface TestbedValidation {
  id: string;
  name: string;
  what: string;
  banks: string[];
  emma: TestbedEmmaPart[];
  /** `none` si la lista está vacía; el texto lo compone el backend. */
  emma_status: { status: "none" | "partial"; text: string };
  not_covered: string;
}

/** `GET /api/testbeds`: bancos de prueba, escalera Tierra-ISS-Luna-Marte y las dos validaciones. */
export interface Testbeds {
  note: string;
  rule: { text: string; where: string };
  principle: { text: string; where: string };
  /** La cabecera de la matriz RIDGE: su nota, los cinco peligros y los cuatro estados. */
  ridge: {
    note: string;
    hazards: { id: string; display: string }[];
    statuses: { id: string; text: string }[];
  };
  ladder: {
    title: string;
    where: string;
    rungs: {
      id: string;
      environment: string;
      strength: string;
      limitation: string;
      use: string;
      banks: string[];
    }[];
  };
  validations: TestbedValidation[];
  banks: Testbed[];
  not_found: string[];
}

export const testbedsApi = {
  get: () => request<Testbeds>("/testbeds"),
};

/**
 * Una frase literal de una fuente de la cadena de una instalación (`app/evidence/facilities.py`).
 * Sin `read_on` propio: la fecha de lectura es la del bloque entero (`Facilities.read_on`).
 */
export interface FacilityQuote extends Omit<TestbedQuote, "read_on"> {
  /** Sobre quién se midió, de la ficha; `null` en una página que no es un estudio. */
  population: string | null;
  population_display: string;
  evidence_type: string | null;
  evidence_type_display: string;
}

/** Un eslabón de la cadena: sus frases y, si algo no se encontró, qué falta y dónde se buscó. */
export interface FacilityLink {
  step: string;
  label: string;
  /** Lo calcula el backend de lo que tiene el eslabón; el texto también. */
  status: "read" | "partial" | "not_found";
  status_text: string;
  quotes: FacilityQuote[];
  missing: { what: string; searched: string[] } | null;
}

export interface Facility {
  id: string;
  name: string;
  full_name: string;
  experiment: string;
  kb_role: { text: string; where: string };
  /** La salvedad de alcance de una cadena que no mide solo personas, o `null`. */
  scope_caveat: string | null;
  links: FacilityLink[];
  /** Los rótulos de los eslabones sin ninguna frase. */
  unsourced: string[];
}

/** `GET /api/facilities`: EPM y Biolab, de la instalación a la aplicación (base de conocimiento §9). */
export interface Facilities {
  note: string;
  read_on: string;
  chain: { text: string; where: string };
  facilities: Facility[];
  not_found: string[];
}

export const facilitiesApi = {
  get: () => request<Facilities>("/facilities"),
};

/**
 * Una ficha del registro de evidencia vista desde quién la firma y qué organización da
 * (`app/evidence/people.py`). `organization` es la de la ficha entera, tal como la escribe; `year`,
 * el de la ficha (`null` si no tiene fecha).
 */
export interface PeopleReference {
  id: string;
  title: string;
  source: string;
  url: string | null;
  date: string | null;
  year: string | null;
  evidence_type_display: string;
  organization: string | null;
  /** Quien firma, con la grafía y el orden de la cita. */
  authors: string[];
  /** La cita abrevia la lista de firmantes («et al.»). */
  et_al: boolean;
  /** Quien la fuente nombra sin firmar, con el cargo que le da y su papel compuesto por el backend. */
  named_people: { name: string; role: string; role_text: string }[];
  /** La organización que el documento escribe junto a una persona, con la frase del backend. */
  affiliations: { name: string; organization: string; text: string }[];
  /** Las organizaciones que la fuente nombra sin darla, con el papel que les da. */
  named_organizations: { name: string; role: string; role_text: string }[];
}

/** Una ficha que nombra a una organización sin ser de ella. */
export interface PeopleNamedBy {
  ref: string;
  title: string;
  year: string | null;
  organization: string | null;
  role: string;
  role_text: string;
}

export interface PeopleOrganization {
  name: string;
  /** Las fichas que da; vacía si solo la nombran. */
  references: PeopleReference[];
  /** Las fichas que la nombran sin ser suyas. */
  named_by: PeopleNamedBy[];
}

/** Una ficha que cita a una persona, con su papel tal como lo compone el backend (`role_text`). */
export interface PeopleCitation {
  ref: string;
  title: string;
  year: string | null;
  organization: string | null;
  role: string;
  role_text: string;
  /** La organización que el documento escribe junto a esa persona, o `null`: no se deduce. */
  affiliation: string | null;
  affiliation_text: string | null;
}

export interface PeoplePerson {
  name: string;
  citations: PeopleCitation[];
}

export interface People {
  note: string;
  affiliation_rule: string;
  same_person_rule: string;
  named_organization_rule: string;
  no_organization: string;
  no_year: string;
  organizations: PeopleOrganization[];
  people: PeoplePerson[];
  without_organization: PeopleReference[];
  /** Fichas del registro recorridas en esta consulta. */
  references: number;
}

export const peopleApi = {
  get: () => request<People>("/people"),
};

/** Una frase literal de la fuente de un conjunto de datos, con su ficha (`app/evidence/human_datasets.py`). */
export interface DatasetQuote {
  quote: string;
  where: string;
  /** El día en que se leyó la frase (AAAA-MM-DD): el suyo, o el del fichero. */
  read_on: string;
  ref: string;
  source: string;
  url: string | null;
  /** Campos de la ficha sin verificar, con su nombre en español. */
  unverified_display: string[];
}

/** Lo que se sabe de las tomas de una fase; `status_text` es la palabra del backend. */
export interface DatasetPhase {
  status: string;
  status_text: string;
  /** Los días leídos (L-92, FD1, R+194…), cada uno escrito en alguna de las frases de `cited`. */
  labels: string[];
  cited: DatasetQuote[];
  why: string | null;
  searched: string | null;
}

/** Un tramo de la escalera de hitos con los días que caen en él; sin días, `text` dice por qué. */
export interface DatasetLadderCell {
  segment: string;
  phase: string;
  labels: string[];
  status: string;
  text: string | null;
}

export interface DatasetAccess {
  level: string;
  level_text: string;
  basis: string;
  basis_text: string;
  cited: DatasetQuote[];
  path: string | null;
  why: string | null;
  searched: string | null;
}

export interface DatasetEmmaUse {
  used: boolean;
  used_text: string;
  text: string;
  where: string | null;
  /** La ficha del registro que cita ese fichero; `null` sin uso. */
  cites: string | null;
}

/**
 * El papel del conjunto en la estrategia de datos (base de conocimiento §8: INPUT, KNOWLEDGE,
 * CONTEXT) y para qué sirve al modelo (entrenar, validar o solo contextualizar). Las dos son
 * deducción de EMMA sobre lo leído, y `basis_text` lo dice: se pintan sin marca.
 */
export interface DatasetRole {
  level: string;
  level_text: string;
  level_why: string;
  fitness: string;
  fitness_text: string;
  fitness_why: string;
  basis_text: string;
}

export interface HumanDataset {
  id: string;
  name: string;
  ref: string;
  title: string;
  source: string;
  url: string | null;
  population: string;
  population_display: string;
  evidence_context: string | null;
  outside_enum_text: string | null;
  /** Sobre quién son los ficheros abiertos; `null` si no hay ficheros abiertos o no se sabe. */
  open_population: string | null;
  open_population_display: string | null;
  open_population_note: string | null;
  /** La fila de la base de conocimiento, literal; `null` si no tiene. */
  kb_row: string | null;
  /** El apartado de la base de conocimiento de esa fila (§8, §3.1); `null` sin fila. */
  kb_where: string | null;
  subjects: DatasetQuote[];
  variables: (DatasetQuote & { what: string })[];
  /** Las áreas del estudio, enteras y contadas contra su frase; `null` si no se listan. */
  areas: DatasetAreas | null;
  phases: Record<string, DatasetPhase>;
  ladder: DatasetLadderCell[];
  /** El calendario de un análogo (reposo en cama), por etapas; `null` fuera de un análogo. */
  analog_schedule: DatasetScheduleStep[] | null;
  controls: DatasetControls;
  access: DatasetAccess;
  emma_use: DatasetEmmaUse;
  role: DatasetRole;
  caveat: string;
}

export interface DatasetAreas {
  count: number;
  cited: DatasetQuote;
  items: (DatasetQuote & { name: string; what: string })[];
}

/** Un paso del calendario de un análogo: sus etapas de la pauta de la base de conocimiento §3.2. */
export interface DatasetScheduleStep extends DatasetQuote {
  stages: string[];
}

/** Un control del conjunto, nombrado en su frase; `kind_text` y la población, del backend. */
export interface DatasetControl extends DatasetQuote {
  kind: string;
  kind_text: string;
  population: string;
  population_display: string;
}

export interface DatasetControls {
  status: string;
  status_text: string;
  items: DatasetControl[];
  /** Lo que la fuente dice que no hay (p. ej. sin controles en Tierra). */
  absent: DatasetQuote[];
  why: string | null;
  searched: string | null;
}

/** Un catálogo de la base de conocimiento §8: dice qué hay y dónde, no mide a nadie. */
export interface DatasetCatalog {
  id: string;
  name: string;
  ref: string;
  title: string;
  source: string;
  url: string | null;
  kb_row: string | null;
  kb_where: string | null;
  what: DatasetQuote[];
  access: DatasetAccess;
  emma_use: DatasetEmmaUse;
  caveat: string;
}

export interface CipherRung extends DatasetQuote {
  id: string;
}

export interface HumanDatasets {
  note: string;
  read_on: string;
  task: { text: string; where: string };
  rule: { text: string; where: string };
  /** La regla de la aptitud, literal de la conversación de ideación. */
  fitness_rule: { text: string; where: string };
  /** Las fases con su rótulo: `pre`, `inflight`, `post`. */
  phases: Record<string, string>;
  milestones: { text: string; where: string; segments: { label: string; phase: string }[] };
  /** La pauta de un análogo (base de conocimiento §3.2): PRE → EXPOSURE → … → RECOVERY. */
  analog_pattern: { text: string; where: string; points: string[] };
  /** Los puntos que la conversación pide en el mapa (Biolab), tal cual. */
  controls_rule: { points: string[]; where: string };
  datasets: HumanDataset[];
  catalogs: DatasetCatalog[];
  cipher: {
    name: string;
    full_name: string;
    what: DatasetQuote;
    studies: string[];
    studies_where: string;
    cohort: DatasetQuote;
    ladder: CipherRung[];
    phases: Record<string, DatasetPhase>;
    /** La fila de CIPHER en la escalera de hitos: sin días, con el estado de cada fase. */
    ladder_cells: DatasetLadderCell[];
    access: DatasetAccess;
    emma_study: string;
    emma_use: DatasetEmmaUse;
    role: DatasetRole;
  };
  not_found: string[];
}

export const humanDatasetsApi = {
  get: () => request<HumanDatasets>("/human-datasets"),
};

/** Una dimensión del coste de medir de un indicador. `basis` y `rule` son `null` sin clasificar. */
export interface CostDimension {
  value: string;
  display: string;
  basis: string | null;
  rule: string | null;
  /** Las entradas de las que lo hereda un calculado; `null` si lo da una regla o está sin clasificar. */
  inherited_from: string[] | null;
  /**
   * La cifra leída de masa, volumen o potencia (decimosexta ronda), copiada de su frase con su
   * unidad; `null` en todo lo demás. La interfaz la formatea con `lib/format.ts`.
   */
  figure: CostFigure | null;
}

/** Una cifra del coste de medir, tal cual se leyó (`figure`) y como número con sus decimales. */
export interface CostFigure {
  amount: number;
  decimals: number;
  unit: string;
  figure: string;
}

/**
 * Cada término de una lista del equipo (la base de conocimiento §9; desde la decimonovena ronda,
 * también la conversación de ideación), con dónde lo tiene EMMA. Un término que no entra
 * (`excluded`, `field` nulo) lleva en `note` por qué.
 */
export interface CostKbCoverage {
  display: string;
  origin: string;
  terms: {
    term: string;
    field: string | null;
    kind: "dimension" | "field" | "excluded";
    display: string;
    note: string | null;
  }[];
}

/** Lo buscado y no encontrado (`searched_not_found`), siempre sobre pares sin clasificar. */
export interface CostSearched {
  keys: string[];
  dimensions: string[];
  dimensions_display: string[];
  searched: string;
  searched_on: string;
}

/** Lo que la fuente de un perfil de misión dice de un aspecto, o que EMMA no tiene fuente. */
export interface GroundAspect {
  key: string;
  label: string;
  status: ProfileAspectStatus;
  text: string;
  citations: ProfileCitation[];
  discrepancy: { text: string; citations: ProfileCitation[] } | null;
  searched: string | null;
}

/**
 * «Hoy se sabe después» (`ingest/cost.py`, `ground_dependence`): lo que hoy depende de Tierra y, al
 * lado, lo que la fuente de cada perfil de misión dice del reabastecimiento y del regreso.
 */
export interface GroundDependence {
  display: string;
  note: string;
  origin: string;
  value: string;
  value_display: string;
  no_source: string;
  rules: string[];
  indicators: { key: string; rule: string | null; inherited_from: string[] | null; result: string }[];
  profiles: { id: string; display: string; aspects: GroundAspect[] }[];
}

/** Resumen de `GET /api/measurement-cost`: cuántos indicadores hay en cada clase y sin clasificar. */
export interface CostSummary {
  indicators: number;
  /** La lista de la base de conocimiento §9 y dónde está cada término (decimosexta ronda). */
  kb_coverage: CostKbCoverage;
  /** La lista de la conversación de ideación (~673) y dónde está cada término (decimonovena). */
  conversation_coverage: CostKbCoverage;
  /** Rótulo y nota, del backend, de una dimensión que EMMA deduce en vez de leer. */
  deduced_display: string;
  deduced_note: string;
  dimensions: {
    key: string;
    display: string;
    /** `true` si EMMA la deduce de la clase de medida (la capacidad de automatización). */
    deduced: boolean;
    values: { value: string; display: string; count: number }[];
    unclassified: number;
  }[];
  unclassified: number;
  fully_classified: number;
  unclassified_value: string;
  unclassified_display: string;
  unclassified_note: string;
  /** Rótulos de lo leído, del backend: `sources` y `discrepancies`. */
  reading_display: Record<CostReadingKind, string>;
  searched_display: string;
  searched: CostSearched[];
  ground_dependence: GroundDependence;
  rules: CostRule[];
}

export type CostReadingKind = "sources" | "discrepancies";

/**
 * Una frase leída en una fuente que sostiene o matiza una regla del coste de medir
 * (`ingest/cost.py`). En el idioma de la fuente; `note`, solo en lo que matiza.
 */
export interface CostReading {
  ref: string;
  title: string;
  source: string;
  url: string | null;
  quote: string;
  where: string;
  read_on: string;
  note?: string;
}

/** Una regla del coste de medir, con lo leído que la sostiene y lo que la matiza. */
export interface CostRule {
  id: string;
  basis: string;
  indicators: number;
  sources: CostReading[];
  discrepancies: CostReading[];
}

/** Un nivel del esquema del motor; `min_score` es `null` en el que queda bajo el primer umbral. */
export interface RiskSchemaLevel {
  level: string;
  display: string;
  label: string;
  min_score: number | null;
}

export interface RiskSeveritySchema {
  levels: RiskSchemaLevel[];
  basis: string;
  rules_version: string;
}

/** Lo que EMMA sabe decir de la incertidumbre de un riesgo. Sin probabilidad: no la cuantifica. */
export interface RiskUncertainty {
  quantified: boolean;
  statement: string;
  evidence: {
    references: {
      id: string;
      title: string;
      grade: string;
      tier: string;
      preclinical: boolean;
      unverified: string[];
      unverified_display: string[];
    }[];
    count: number;
    by_grade: { grade: string; count: number }[];
    preclinical: number;
    unverified_fields: number;
  };
  countermeasures: {
    count: number;
    by_basis: { basis: string; count: number }[];
    demo: number;
    note: string;
  };
  evaluation: {
    evaluated_with: string;
    evaluated_with_display: string;
    indicators: number;
    measured: number;
    calculated: string[];
    calculated_display: string;
    inferred_states: {
      key: string;
      display: string;
      observation_type: string;
      model_version: string;
      basis: string;
      note: string;
    }[];
    basis: string;
  };
}

/** Una ficha del registro como la enseña la matriz: qué es, de qué clase y sobre quién se midió. */
export interface RiskMatrixRef {
  id: string;
  title: string;
  url: string | null;
  evidence_type: string | null;
  evidence_type_display: string;
  population: string | null;
  population_display: string;
  not_applicable: string[];
  outside_enum: string[];
  relevance?: string | null;
}

/** Un paso de la regla de detección, con las cifras que usa el motor (`analysis/`). */
export interface RiskDetectionStep {
  key: string;
  display: string;
  statement: string;
  values: Record<string, unknown>;
}

/** La regla común de detección, leída del motor en cada consulta. */
export interface RiskDetectionRule {
  display: string;
  steps: RiskDetectionStep[];
  isolation: { autonomy_above_minutes: number; max_factor: number; saturates_at_minutes: number };
  validated_with: {
    display: string;
    dataset: RiskMatrixRef;
    scope: string | null;
    statement: string;
    /** Las claves que emite el cargador de MMASH (`validation/mmash.py`), en su orden. */
    keys: RiskMmashKey[];
    validates: string;
    /** Hasta dónde llega lo medido (rango de población y límites, más que base personal). */
    note: string;
    keys_basis: string;
  };
  basis: string;
  rules_version: string;
}

/** Un indicador que sale de MMASH, con el aparato del conjunto de datos del que sale. */
export interface RiskMmashKey {
  key: string;
  display_es: string;
  domain: string;
  source: string;
  source_display: string;
}

/** Qué indicadores de un riesgo salen de MMASH y qué valida eso; el dominio sin ninguno lo dice. */
export interface RiskValidation {
  dataset_id: string;
  keys: RiskMmashKey[];
  indicators: number;
  statement: string;
  validates: string | null;
  note: string | null;
  empty: string | null;
  basis: string;
}

/** Un deterioro de referencia que el inyector aplica a un indicador (`validation/injection.py`). */
export interface RiskInjection {
  label: string;
  /** La forma temporal (`Perturbation` del inyector), un conjunto cerrado. */
  kind: "drift" | "acute" | "step";
  kind_display: string;
}

/**
 * Sobre qué indicadores de un riesgo se ha medido la sensibilidad inyectando deterioros; el
 * dominio sin ninguno lo dice. Sin cifras: `reference` es donde están.
 */
export interface RiskSensitivity {
  keys: { key: string; display_es: string; injections: RiskInjection[] }[];
  indicators: number;
  statement: string;
  measures: string | null;
  reference: string;
  empty: string | null;
  basis: string;
}

/** El equipo de cada variable del riesgo, del coste de medir, agrupado por equipo. */
export interface RiskEquipment {
  groups: { equipment: string; indicators: { key: string; display_es: string }[] }[];
  basis: string;
}

/** Lo que cambia de un dominio a otro en la detección: límites, aislamiento y entorno. */
export interface RiskDetection {
  indicators: number;
  danger_limits: { key: string; display_es: string; statement: string }[];
  isolation_applies: boolean | null;
  isolation_statement: string;
  environment: { key: string; statement: string; summary: string }[];
  summary: string;
  basis: string;
}

/** Una contramedida de la biblioteca en la fila de su riesgo. */
export interface RiskCountermeasure {
  id: string;
  action: string;
  basis: string;
  basis_display: string;
  family: string | null;
  family_display: string | null;
  on_event: boolean;
  trigger_display: string | null;
}

/** Un riesgo entero (especificación §3): `GET /api/risks` junta lo que ya había, sin calcular. */
export interface RiskEntity {
  risk_id: string;
  display: string;
  ridge: { category: string; display: string; source: { id: string; title: string; url: string | null } };
  human_system: {
    /** Cada región con su frase y las fichas que esa frase nombra (§5.37.16). */
    regions: Pick<AnatomyRegion, "key" | "display" | "domains" | "note" | "note_refs" | "analytes_source">[];
    basis: string;
  };
  hrp_risk_id: string | null;
  evidence_refs: { id: string; title: string; source: string; url: string | null }[];
  amcl_alignment: string;
  severity_schema: RiskSeveritySchema;
  indicators: {
    key: string;
    display: string;
    display_es: string;
    unit: string;
    is_standard_code: boolean;
    mode: string | null;
    mode_display: string | null;
    equipment: string | null;
    from_mmash: boolean;
    sensitivity_measured: boolean;
    sensitivity_injections: RiskInjection[];
  }[];
  /** La fila de la matriz: efecto, dato, detección y contramedidas (el peligro es `ridge`). */
  effect: { source: RiskMatrixRef | null; statement: string; basis: string };
  data_sources: {
    datasets: RiskMatrixRef[];
    documents: RiskMatrixRef[];
    datasets_empty: string | null;
    documents_empty: string | null;
    basis: string;
  };
  detection: RiskDetection;
  countermeasures: { items: RiskCountermeasure[]; empty: string | null; basis: string };
  equipment: RiskEquipment;
  validation: RiskValidation;
  sensitivity: RiskSensitivity;
  uncertainty: RiskUncertainty;
}

export interface RisksResponse {
  count: number;
  risks: RiskEntity[];
  severity_schema: RiskSeveritySchema;
  uncertainty_statement: string;
  /** Los seis eslabones de la matriz, en su orden, con la palabra de cada uno. */
  chain: { links: { key: string; display: string }[]; basis: string };
  detection_rule: RiskDetectionRule;
}

/** Un dominio de EMMA que vigila un riesgo del HRP, con la frase de su alcance (marco de ExMC). */
export interface HrpCoverageDomain {
  key: string;
  display: string;
  scope: string;
}

/**
 * Un riesgo del Human Research Roadmap y qué hace EMMA con él (`app/evidence/hrp_coverage.py`).
 * Título, nombre corto, estado, elemento y fecha son los de su página; el eje RIDGE y la cobertura
 * son de EMMA, cada uno con su motivo. Todo el texto lo da el backend.
 */
export interface HrpCoverageRisk {
  hrr_id: number;
  url: string;
  title: string;
  short_title: string;
  status: string;
  status_display: string;
  hrp_element: string;
  last_published: string;
  ridge: { category: string; display: string; basis: string; basis_display: string; note: string };
  /** `covered`, `partial` u `outside`; la palabra que se lee va en `coverage_display`. */
  coverage: string;
  coverage_display: string;
  /** La cobertura en una frase, con los dominios por su nombre («en parte, por el dominio …»). */
  coverage_statement: string;
  domains: HrpCoverageDomain[];
  reason: string;
  /** Con la forma de toda cita: se pintan con `EvidenceList`, con su salvedad de alcance. */
  refs: EvidenceItem[];
  /** Medidas y analitos que nombra la fuente y el catálogo tiene (§5.38.5), con su código y su unidad. */
  in_catalog: HrpCoverageAnalyte[];
  /** Medidas y analitos que nombra la fuente y no están en el catálogo: pendientes, sin código. */
  pending: string[];
}

export interface HrpCoverageAnalyte {
  key: string;
  display_es: string;
  code: string;
  system: string;
  system_display: string;
  is_standard_code: boolean;
  /** UCUM, para contrastar; la que se lee es `unit_display`, del backend. */
  unit: string;
  unit_display: string;
  descriptive_only: boolean;
  descriptive_display: string | null;
}

export interface HrpCoverage {
  note: string;
  read_on: string;
  listing: { source: RiskMatrixRef; count_quote: string; element_quote: string; updates: string };
  count: number;
  counts: Record<string, number>;
  summary: string;
  coverage_display: Record<string, string>;
  element_basis: string;
  ridge_note: string;
  ridge_source: RiskMatrixRef;
  pending_note: string;
  in_catalog_note: string;
  risks: HrpCoverageRisk[];
}

export const risksApi = {
  get: () => request<RisksResponse>("/risks"),
  cost: () => request<{ summary: CostSummary }>("/measurement-cost"),
  hrpCoverage: () => request<HrpCoverage>("/risks/hrp-coverage"),
};

/** Una frase leida en una fuente, con su cita (`evidence/instruments_read.py`). En su idioma. */
export interface InstrumentStatement {
  id: string;
  label: string;
  quote: string;
  ref: string;
  source: string;
  title: string;
  url: string | null;
  where: string;
  read_on: string;
  extent: string;
  extent_text: string;
}

/** Un documento leido y cuanto se leyo de el. */
export interface InstrumentSource {
  ref: string;
  title: string;
  source: string;
  url: string | null;
  extent: string;
  extent_text: string;
  what: string;
}

/** El rotulo de un punto de una escala, tal como lo escribe su fuente (sin traducir). */
export interface ScaleLabel {
  value: number;
  label: string;
  statement: InstrumentStatement;
}

/** Un ancla de una escala propia: el punto y lo que EMMA decidio que significa. Sin cita. */
export interface DesignAnchor {
  value: number;
  label: string;
}

/**
 * Las anclas de una escala propia de la mision (ánimo, síntomas, apetito). No se leyeron en
 * ninguna fuente: las decidio EMMA, y `status_display` lo dice («sin validar»). Por eso no
 * llevan frase, ficha ni enlace, y van aparte de `labels`, que son rotulos leidos.
 */
export interface DesignAnchors {
  status: "design";
  status_display: string;
  decided_on: string;
  why: string;
  anchors: DesignAnchor[];
  between: string;
  reference: string;
}

/** Un indicador que el tripulante anota a mano (`GET /api/diary`). Lo decide el backend. */
export interface DiaryIndicator {
  key: string;
  display: string;
  display_es: string;
  unit: string;
  unit_display: string;
  domain: string;
  decimals: number;
  /** Rango fisico del catalogo: fuera de el, el backend rechaza la lectura. */
  physical_min: number | null;
  physical_max: number | null;
  range_text: string;
  equipment: string | null;
  mode_display: string | null;
  /**
   * Solo en indicadores de puntos. `labels` lleva solo los rotulos leidos en una fuente, en el
   * idioma de la fuente; `null` si no se leyo ninguno. `own`: escala propia de la mision, sin
   * fuente que la defina; sus anclas, decididas por EMMA y sin validar, van en `design_anchors`.
   */
  scale: {
    described_as: string | null;
    labels: ScaleLabel[] | null;
    labels_status?: "read" | "own" | "unverified" | "instrument";
    labels_language?: string | null;
    labels_note: string;
    labels_sources?: InstrumentSource[];
    labels_see_also?: InstrumentStatement[];
    labels_not_found?: string[];
    design_anchors?: DesignAnchors | null;
    /**
     * Desde el 2026-10-16, en los indicadores descriptivos con escala de puntos: lo leído de su
     * instrumento publicado (`labels_status: "instrument"`). Su fuente no escribe un rótulo
     * junto a cada número; si da categorías con palabras, van en `categories`, tal cual.
     */
    instrument?: DescriptiveMeasure | null;
    concerning: string;
    concerning_note: string | null;
  } | null;
  /** Se anota igual, pero el estado no lo lee (indicador descriptivo). */
  descriptive_only?: boolean;
  /**
   * Desde el 2026-10-26, en la aceptabilidad de la comida: el alimento valorado, obligatorio, con
   * su regla (decisión de diseño de EMMA, sin validar). Desde el 2026-10-31 también en la fracción
   * rechazada, opcional (`required`). `null` en los demás indicadores.
   */
  food_item?: FoodItemRule | null;
}

/**
 * El alimento que lleva una valoración de la comida: texto libre con la regla del backend
 * (`ingest/food_item.py`). Los textos son del backend; la consola solo los enseña.
 */
export interface FoodItemRule {
  label: string;
  /** Si el indicador exige el alimento (la valoración) o lo admite sin más (la fracción). */
  required: boolean;
  /** Lo que `required` significa aquí, con palabras del backend (desde el 2026-10-31). */
  requirement_note?: string;
  max_length: number;
  status: string;
  status_display: string;
  decided_on: string;
  rule: string;
  why_free_text: string;
  grouping: string;
  /** Las frases leídas que dicen que la valoración es de un alimento (no la regla: no tiene). */
  basis: InstrumentStatement[];
}

/**
 * Una categoría que la fuente da con palabras («mild (does not affect daily activities)»),
 * copiada tal cual en `literal`. El número es de EMMA: `DescriptiveMeasure.numbering` lo dice.
 */
export interface MeasureCategory {
  value: number;
  literal: string;
  statement: string;
}

/** Lo leído de la medida o el instrumento de un indicador descriptivo, con cada frase. */
export interface DescriptiveMeasure {
  instrument: string;
  /** Idioma de las frases (BCP 47): se marcan en el HTML y no se traducen. */
  language: string;
  /** Qué registra EMMA de ese instrumento. Texto del backend. */
  scope: string;
  statements: InstrumentStatement[];
  categories: MeasureCategory[];
  numbering: string | null;
  sources: InstrumentSource[];
  not_found: string[];
}

/**
 * Quien teclea en la consola (el operador), que se firma con cada valor. Los textos son del
 * backend; `missing_display` es como se nombra a quien no consta en una lectura antigua.
 */
export interface RecordedByRule {
  required: boolean;
  label: string;
  note: string;
  missing_display: string;
  legacy_note: string;
}

export interface DiaryCatalog {
  indicators: DiaryIndicator[];
  /** Con que procedencia firma el backend cada valor. La consola no la envia: la ensena. */
  provenance: {
    source: string;
    source_display: string;
    observation_type: string;
    evidence_context: string;
  };
  recorded_by: RecordedByRule;
  submit_to: string;
  notes: string[];
}

/** Una anotacion leida del registro firmado, con las palabras del backend. */
export interface DiaryEntry {
  key: string;
  display: string;
  display_es: string;
  value: number;
  value_text: string;
  effective: string;
  /** Con que fuente entro: la del diario, o «alta manual» si es anterior a ella. */
  source: string;
  source_display: string;
  /** Quien la tecleo, tal como quedo firmado; `null` si la lectura no lo lleva. */
  recorded_by: string | null;
  /** El nombre, o las palabras del backend para «no consta». */
  recorded_by_display: string;
  /** El alimento valorado, tal como quedó firmado; `null` si la lectura no lo lleva. */
  food?: string | null;
  observation_type: string;
  evidence_context: string;
  position: EntryPosition;
  position_note: string;
}

/**
 * Donde cae una entrada del diario o una sesion PVT respecto a lo que analiza el estado
 * (`api/diary.py`, `_position`): dentro de su ventana, antes, fechada despues de la referencia (el
 * estado la aparta), `descriptive` (un indicador descriptivo, que el estado no lee: sin color, no
 * avisa) o `not-analysed-by-type` (una lectura inferida o predicha: el estado no la lee por su
 * tipo y no se situa frente a su ventana, §5.39.11). La frase va siempre en `position_note`.
 */
export type EntryPosition = "current" | "earlier" | "after-reference" | "descriptive" | "not-analysed-by-type";

export interface DiaryEntries {
  subject: string;
  count: number;
  reference_time: string | null;
  entries: DiaryEntry[];
}

/**
 * Lo que el registro diario envia por cada valor: de quien es el dato y quien lo teclea. La
 * fuente, el tipo, el entorno y la hora los pone el backend; enviarlos es un 422.
 */
export interface DiaryObservationBody {
  key: string;
  value: number;
  subject: string;
  recorded_by: string;
  /**
   * El alimento: obligatorio en la aceptabilidad de la comida, opcional en la fracción rechazada
   * (desde el 2026-10-31), un 422 en los demás.
   */
  food?: string;
}

export const diaryApi = {
  catalog: () => request<DiaryCatalog>("/diary"),
  entries: (subject: string, limit = 10) =>
    request<DiaryEntries>(`/diary/entries${queryOf({ subject, limit })}`),
  /** Por la ruta del diario: una observacion firmada y en el ledger (invariante 4). */
  record: (body: DiaryObservationBody) =>
    post<{ ledger_index: number; content_hash: string }>("/diary/entries", body),
};

/**
 * El criterio de aceptable de la comida, leido en su fuente (`analysis/food_acceptability.py`).
 * La cifra, el trozo de frase que la escribe y la frase entera con su cita; los textos de la
 * regla, de a que se aplica y de su alcance son del backend.
 */
export interface FoodCriterion {
  value: number;
  value_text: string;
  literal: string;
  /** El idioma de la frase, que se pinta tal cual (sin traducir). */
  language: string;
  statement: InstrumentStatement;
  mark: string;
  rule: string;
  applies_to: string;
  scope: string;
}

/** Una valoracion de la comida del registro firmado, marcada frente al criterio. */
export interface FoodRating {
  effective: string;
  value: number;
  value_text: string;
  /** El alimento firmado con la valoracion; `null` si no lo lleva (lo anterior al campo). */
  food?: string | null;
  /** El alimento, o las palabras del backend para «sin alimento declarado». */
  food_display?: string;
  source: string;
  source_display: string;
  observation_type: string;
  evidence_context: string;
  /** `null` sin criterio leido: no es «no esta por debajo», es que no se compara. */
  below: boolean | null;
  mark: string | null;
}

/** Una valoracion de un plato, en su serie de la primera a la ultima. */
export interface FoodDishRating {
  effective: string;
  value: number;
  value_text: string;
  below: boolean | null;
  mark: string | null;
}

/** Una lectura de un plato en un instante: la cifra tal como la escribe el backend. */
export interface FoodDishPoint {
  effective: string;
  value: number;
  value_text: string;
}

/**
 * De la primera a la ultima valoracion de un plato (decimonovena ronda, 2026-10-31): dos cifras
 * y dos fechas, con la frase del backend. Descriptivo: sin umbral ni veredicto.
 */
export interface FoodDishChange {
  first: FoodDishPoint;
  last: FoodDishPoint;
  statement: string;
}

/** La fraccion rechazada anotada con el nombre del plato: cuantas veces, la primera y la ultima. */
export interface FoodDishRejected {
  times: number;
  first: FoodDishPoint;
  last: FoodDishPoint;
  statement: string;
  series: FoodDishPoint[];
}

/**
 * Un plato (decision del usuario, 2026-10-26): cuantas veces se valoro, en cuantos dias y cada
 * valoracion en el tiempo. Descriptivo: sin umbral ni veredicto. El recuento lo escribe el backend.
 */
export interface FoodDish {
  food: string;
  times: number;
  distinct_days: number;
  first_effective: string;
  last_effective: string;
  below: number | null;
  statement: string;
  series: FoodDishRating[];
  /** De la primera a la ultima valoracion, con palabras (desde el 2026-10-31). */
  change?: FoodDishChange | null;
  /** La fraccion rechazada de este plato, si se anoto con su nombre; `null` si no. */
  rejected?: FoodDishRejected | null;
  /** La frase de `rejected`, o las palabras del backend para «sin fraccion rechazada declarada». */
  rejected_display?: string;
}

/** `GET /api/nutrition/food-acceptability`: marca sobre la comida, no sobre la persona. */
export interface FoodAcceptability {
  subject: string;
  key: string;
  display: string;
  display_es: string;
  criterion: FoodCriterion | null;
  rated: number;
  below: number | null;
  statement: string;
  not_measured_excluded: number;
  not_measured_note: string;
  shown: number;
  ratings: FoodRating[];
  /** Plato a plato, sobre todas las valoraciones medidas con alimento (no solo las `shown`). */
  dishes?: FoodDish[];
  dishes_statement?: string;
  without_food?: number;
  without_food_note?: string;
  repetition_note?: string;
  /** Lo que dicen `change` y `rejected` de cada plato, y lo que no (desde el 2026-10-31). */
  change_note?: string;
  rejected_note?: string;
  grouping?: string;
}

/** La ficha LOINC leída de un código: la propiedad manda la unidad. */
export interface LoincRead {
  component: string;
  property: string;
  system: string;
  scale: string;
  method: string | null;
  example_ucum: string;
  status: string;
  version: string;
  read_on: string;
  url: string;
}

/** Una lectura firmada de un indicador descriptivo, tal como consta en el registro. */
export interface DescriptiveReading {
  effective: string;
  value: number;
  value_text: string;
  source: string;
  source_display: string;
  recorded_by: string | null;
  recorded_by_display: string;
  observation_type: string;
  evidence_context: string;
}

export interface DescriptiveIndicator {
  key: string;
  display: string;
  display_es: string;
  domain: string;
  domain_display: string;
  unit: string;
  unit_display: string;
  decimals: number;
  range_text: string;
  system: string;
  system_display: string;
  code: string;
  /** El día en que el usuario decidió que entrara (no todos entraron a la vez). */
  decided_on?: string;
  /** Por qué ese código: la ficha LOINC leída o lo que se buscó antes del código propio. */
  code_basis: {
    kind: "loinc" | "own";
    text: string;
    loinc: LoincRead | null;
    searched: string | null;
  };
  equipment: string | null;
  how_recorded: { route: string; text: string };
  instrument: DescriptiveMeasure | null;
  count: number;
  shown: number;
  readings: DescriptiveReading[];
}

/**
 * `GET /api/indicators/descriptive`: salud conductual más allá del ánimo, síntomas visuales,
 * forma física y la vitamina D 25-OH. Se firman y se enseñan; el estado no los lee (no son
 * alertas ni niveles). `decided_on` es la primera decisión; cada indicador lleva la suya.
 */
export interface DescriptiveIndicators {
  subject: string;
  decided_on: string;
  scope: string;
  statement: string;
  indicators: DescriptiveIndicator[];
}

export const indicatorsApi = {
  descriptive: (subject: string, limit = 10) =>
    request<DescriptiveIndicators>(`/indicators/descriptive${queryOf({ subject, limit })}`),
};

/**
 * La base contra la que se juzgó la última lectura de un indicador en un estado fisiológico
 * (`app/analysis/baseline_profile.py`). Cifras y frases del backend; la interfaz solo las pinta.
 */
export interface BaselineState {
  context: string;
  context_display: string;
  /** El estado de la última lectura del indicador. */
  latest: boolean;
  reading_effective: string;
  window: { start: string; end: string };
  drawn_from: "state" | "family";
  drawn_from_display: string;
  established: boolean;
  status_display: string;
  samples: number;
  min_samples: number;
  /** null mientras aprende: no es contra lo que se juzga. */
  median: number | null;
  spread: number | null;
  decimals: number;
  danger_limit: { low: number | null; high: number | null; text: string };
  judged_against: string;
  /**
   * De qué está hecha (§5.37.2): cuántas lecturas de la base hay de cada entorno y de cada tipo;
   * null si las lecturas de la ventana no son exactamente las de la base y no se puede saber.
   */
  composition: BaselineComposition | null;
  /** Frase del backend si la base mezcla entornos, tiene valores no medidos o no se sabe; null si no. */
  composition_display: string | null;
  /** Dónde corta: los percentiles del motor, de leve a grave; vacío mientras aprende. */
  cuts: BaselineCut[];
  /** Frase del backend si el indicador solo avisa por percentil hacia un lado; null si no. */
  cuts_note: string | null;
}

export interface BaselineComposition {
  samples: number;
  /** Por entorno (`lib/provenance.ts`), de la más frecuente a la menos. */
  evidence_context: Record<string, number>;
  /** Por tipo: medido, inferido o predicho. */
  observation_type: Record<string, number>;
}

/** Un corte de percentil de la base, en la unidad del indicador (`baseline._QUANTILE_THRESHOLDS`). */
export interface BaselineCut {
  severity: "mild" | "moderate" | "severe";
  display: string;
  quantile: number;
  min_samples: number;
  /** Si la base tiene las lecturas que esta gravedad pide; si no, sin cifra. */
  applies: boolean;
  /** Por arriba y por abajo; null por el lado que no se vigila o si no se aplica. */
  high: number | null;
  low: number | null;
  text: string;
}

export interface BaselineIndicator {
  key: string;
  display: string;
  display_es: string;
  domain: string;
  unit: string;
  /** Si la base de su última lectura estaba establecida; null si no se pudo atribuir a un estado. */
  established: boolean | null;
  reference: { low: number | null; high: number | null; basis: string | null; text: string };
  states: BaselineState[];
  unattributed_readings: number;
  /** Frase del backend si alguna lectura no se pudo atribuir a un estado; null si no. */
  unattributed_display: string | null;
}

/**
 * Una frase leída de un estudio con otra tripulación, con el sentido en que cambió el indicador
 * en vuelo (`app/evidence/flight_direction.py`). Todo texto es del backend.
 */
export interface FlightDirectionStatement {
  id: string;
  direction: "rises" | "falls" | "unchanged";
  direction_display: string;
  quote: string;
  /** La frase entre comillas, como se pinta. */
  quote_display: string;
  literal: string;
  compared_with: string;
  compared_with_display: string;
  population: string;
  where: string;
  ref: string;
  source: string;
  url: string | null;
  read_on: string;
  extent: string;
  extent_text: string;
}

/** Lo que se observó en otros vuelos para un indicador; no lo esperado en esta persona. */
export interface FlightDirectionIndicator {
  key: string;
  display_es: string;
  direction: "rises" | "falls" | "unchanged" | "contested" | "no_source";
  direction_display: string;
  text: string;
  scope: string | null;
  searched: string | null;
  /**
   * «Buscado y no encontrado: …» sin frase, o «Leído también, sin sentido en vuelo: …» junto a
   * un sentido, del backend; null si no se buscó ni se leyó nada más.
   */
  searched_display: string | null;
  /** La cita del registro de lo buscado (o leído también); vacía si no hay. */
  searched_sources: string[];
  /** El día en que se leyó cada ficha de `searched_sources` (AAAA-MM-DD), en su orden. */
  searched_read_on: string[];
  /** Cuánto se leyó de cada ficha de `searched_sources` («leído en parte»…), en su orden. */
  searched_extent_text: string[];
  statements: FlightDirectionStatement[];
}

export interface FlightDirection {
  note: string;
  statement: string;
  read_on: string;
  indicators: FlightDirectionIndicator[];
}

/** El perfil de línea base de un tripulante (especificación §3 `baseline_profile`, §10). */
export interface BaselineProfile {
  subject: string;
  reference_time: string;
  until: string | null;
  kind: "rolling";
  method: string;
  /** Cómo corta una base establecida, con las cifras del motor y el tope por baja confianza. */
  cuts_method: string;
  fixed_note: string;
  window_days: number;
  lag_hours: number;
  min_samples: number;
  statement: string;
  indicators: BaselineIndicator[];
  descriptive: { key: string; display_es: string; reason: string }[];
  /** Junto a la base, el sentido observado en otros vuelos de cada indicador analizado. */
  flight_direction: FlightDirection;
  /**
   * Sexo y edad (especificación §3, «sólo si el dataset lo permite»): el sexo se declara aparte
   * (`crew-sex`, 2026-11-14) y la edad no tiene campo; estas frases del backend dicen qué se guarda
   * y para qué (`baseline_profile.personal_data`).
   */
  personal_data: BaselinePersonalData;
}

export interface BaselinePersonalData {
  /** Lo que no tiene campo: hoy, solo la edad. */
  no_field: string[];
  statement: string;
  /** Para qué sirve el sexo declarado: solo ofrecer el seguimiento del ciclo. */
  cycle: string;
  radiation: string;
  elsewhere: string;
  privacy: string;
  source: { id: string; title: string; url: string | null; relevance: string | null };
}

export const baselineApi = {
  /** De solo lectura: no firma nada. Con `until`, con lo que Tierra tiene. */
  profile: (subject: string, until?: Date) =>
    request<BaselineProfile>(`/baseline-profile${queryOf({ subject, until: until?.toISOString() })}`),
};

/** Una de las cinco preguntas de la base de conocimiento §10, con su respuesta (`app/twins.py`). */
export interface TwinQuestion {
  key: "human" | "habitat" | "mission" | "countermeasure" | "decision";
  /** Las tres columnas de la tabla, literales: «Twin / capa», «Contenido» y «Pregunta». */
  twin: string;
  content: string;
  question: string;
  /** `nothing`: no hay nada que contar; `unavailable`: la fuente no respondió. */
  state: "answered" | "nothing" | "unavailable";
  answer: string;
  /** Cada parte de la respuesta; `level` solo si viene de un nivel de riesgo. */
  items: { text: string; level: string | null }[];
  notes: string[];
  /** De qué ruta y de qué campos sale la respuesta. */
  sources: string[];
}

export interface TwinQuestions {
  subject: string;
  reference_time: string;
  /** El corte de Tierra con que se respondió; `null` a bordo. */
  until: string | null;
  rules_version: string;
  source: string;
  note: string;
  questions: TwinQuestion[];
}

export const twinsApi = {
  /** Compone lo que el estado ya calculó; no firma nada que `/status` no firmara ya. Con `until`
   * (consola de Tierra), las cinco respuestas con lo llegado hasta ese corte, sin firmar nada. */
  questions: (subject: string, until?: Date) =>
    request<TwinQuestions>(`/twins${queryOf({ subject, until: until?.toISOString() })}`),
};

export const nutritionApi = {
  foodAcceptability: (subject: string, limit = 60) =>
    request<FoodAcceptability>(`/nutrition/food-acceptability${queryOf({ subject, limit })}`),
};

/** Lo que da una fuente para un parametro, en una version publicada de la prueba. */
export interface PvtPublishedValue {
  variant: string;
  variant_display: string;
  /** El trozo de la frase que lleva el valor, tal cual. */
  literal: string;
  value_ms: number | number[];
  /** Si el valor de EMMA es ese mismo: cifra y, si la fuente lo escribe, operador. Del backend. */
  same: boolean;
  /** Si coincide la cifra, aunque el operador no. */
  same_figure?: boolean;
  /** El operador que escribe la fuente delante de la cifra, si escribe uno. */
  operator?: string | null;
  emma_operator?: string | null;
  match?: "same" | "same_figure_different_operator" | "different" | "not_comparable";
  /** La marca junto al valor, tal cual; `null` si no es comparable. Texto del backend. */
  marker_display?: string | null;
  statement: InstrumentStatement;
}

/** El valor de EMMA frente a lo publicado, y en que difiere. Texto del backend. */
export interface PvtPublished {
  status:
    | "same_value"
    | "same_figure_different_operator"
    | "different_value"
    | "not_comparable"
    | "not_published";
  status_display: string;
  values: PvtPublishedValue[];
  see_also: InstrumentStatement[];
  difference: string;
}

/** Un parametro de la prueba PVT con lo que lo respalda (`GET /api/pvt/protocol`). */
export interface PvtParameter {
  key: string;
  display: string;
  value: number;
  value_text: string;
  /**
   * `repository`: respaldo escrito en el repositorio. `design`: nada escrito lo respalda.
   * `read`: valor de diseno que coincide con el leido en la fuente.
   */
  basis: "repository" | "design" | "read";
  basis_display: string;
  note: string;
  /** Si el valor entra en la puntuacion de una prueba. */
  scores?: boolean | undefined;
  published?: PvtPublished | undefined;
}

/** Las cifras con que la consola pasa la prueba. Las decide el backend. */
export interface PvtSessionSpec {
  trials: number;
  foreperiod_min_ms: number;
  foreperiod_max_ms: number;
  /** Como se envia una respuesta dada antes de la marca. */
  premature_response_ms: number;
  /** Sin respuesta en este tiempo, la prueba se abandona y no se envia nada. */
  abandon_after_ms: number;
}

export interface PvtResultField {
  key: string;
  display: string;
  unit_display: string;
  decimals: number;
  recorded_as: string | null;
}

/**
 * Una diferencia entre lo que hace EMMA y lo que dice la fuente leida. Todo el texto es del
 * backend; lo que dice de EMMA lo deduce del codigo que puntua.
 */
export interface PvtDivergence {
  key: string;
  display: string;
  /** Lo que hace EMMA. */
  emma: string;
  /** Lo que dice lo publicado, o que no hay valor publicado. */
  published: string;
  /**
   * `differs`, `matches` o `not_published`: lo calcula el backend frente a lo leido. Uno que
   * esta version no conoce se pinta sin color, con su palabra.
   */
  status: string;
  status_display: string;
  consequence: string;
  /** Si lo que difiere entra en la puntuacion de una prueba. */
  scores: boolean;
  /** Que no se ha cambiado y por que. */
  kept: string;
  /** Las frases leidas que la sostienen; vacio si no hay valor publicado. */
  sources: InstrumentStatement[];
  /** Lo que se busco y no se encontro. */
  not_found: string[];
}

export interface PvtProtocol {
  title: string;
  /** Que prueba es esta: ninguna de las publicadas, y por que. */
  identity?: string;
  /** Lo leido que no es de un solo parametro. */
  published?: {
    note: string;
    read_on: string;
    sources: InstrumentSource[];
    context: InstrumentStatement[];
    outcomes_note: string;
    not_found: string[];
  };
  /** Las divergencias con lo publicado, declaradas y no corregidas (desde el 2026-10-14). */
  divergences?: {
    note: string;
    items: PvtDivergence[];
  };
  instructions: string[];
  limits: string[];
  notices: { premature: string; abandoned: string; no_response: string };
  parameters: PvtParameter[];
  session: PvtSessionSpec;
  result_fields: PvtResultField[];
  records: { key: string; display: string; display_es: string }[];
  provenance: {
    source: string;
    source_display: string;
    observation_type: string;
    evidence_context: string;
    effective_note: string;
  };
  recorded_by: RecordedByRule;
  submit_to: string;
  notes: string[];
}

/**
 * Lo que la consola envia: un tiempo por estimulo, el tripulante y quien esta en la consola.
 * La hora y la fuente las pone el backend.
 */
export interface PvtSubmissionBody {
  reaction_times_ms: number[];
  subject: string;
  recorded_by: string;
}

/** Lo que devuelve `POST /api/pvt/console`: la puntuacion del backend y los asientos. */
export interface PvtSubmitted {
  result: Record<string, number>;
  recorded: number[];
}

/** Una prueba leida del registro firmado, con las palabras del backend. */
export interface PvtRecordedSession {
  effective: string;
  /** Con que fuente entro: hecha en la consola, o llegada por la ruta de siempre. */
  source: string;
  source_display: string;
  /** Quien estaba en la consola, tal como quedo firmado; `null` si la prueba no lo lleva. */
  recorded_by: string | null;
  recorded_by_display: string;
  observation_type: string;
  evidence_context: string;
  /** La misma posicion que una entrada del diario: la calcula la misma regla del backend. */
  position: EntryPosition;
  position_note: string;
  values: { key: string; display: string; display_es: string; value: number; value_text: string }[];
}

export interface PvtSessions {
  subject: string;
  count: number;
  reference_time: string | null;
  sessions: PvtRecordedSession[];
}

export const pvtApi = {
  protocol: () => request<PvtProtocol>("/pvt/protocol"),
  sessions: (subject: string, limit = 5) =>
    request<PvtSessions>(`/pvt/sessions${queryOf({ subject, limit })}`),
  /** Por la ruta de la consola: la puntua el backend, firmada y en el ledger (invariante 4). */
  submit: (body: PvtSubmissionBody) => post<PvtSubmitted>("/pvt/console", body),
};

/** Una puntuacion de una prueba de la bateria Cognition, con su rango y su frase leida. */
export interface CognitionField {
  key: string;
  measure: "speed" | "accuracy" | "risk";
  /** La palabra de la medida («velocidad», «precisión», «riesgo»), del backend. */
  measure_display: string;
  display: string;
  display_es: string;
  unit: string;
  unit_display: string;
  decimals: number;
  physical_min: number | null;
  physical_max: number | null;
  range_text: string;
  /** Que es esa cifra, con la frase de la fuente en su idioma. */
  statement: InstrumentStatement;
}

/** Una prueba de la bateria, en su orden de administracion (`GET /api/cognition/protocol`). */
export interface CognitionTestSpec {
  order: number;
  abbrev: string;
  sigla: string;
  name: string;
  /** Que mide, con su frase leida; `null` si no hay ninguna (lo dice `measures_note`). */
  measures: InstrumentStatement | null;
  measures_note: string | null;
  /** `false` en la PVT: se pasa y se registra en su consola. */
  recorded_here: boolean;
  fields: CognitionField[];
  /** En la MPT, la frase que dice que no tiene precision. */
  no_accuracy: InstrumentStatement | null;
  console: string | null;
  console_note: string | null;
}

export interface CognitionProtocol {
  title: string;
  identity: string;
  scope: string;
  limits: string[];
  battery: InstrumentStatement[];
  tests: CognitionTestSpec[];
  not_found: string[];
  provenance: {
    source: string;
    source_display: string;
    observation_type: string;
    evidence_context: string;
    effective_note: string;
  };
  recorded_by: { required: boolean; label: string; note: string; missing_display: string };
  submit_to: string;
}

/** Lo que la consola envia: las puntuaciones por clave, el tripulante y quien teclea. */
export interface CognitionSubmissionBody {
  scores: Record<string, number>;
  subject: string;
  recorded_by: string;
}

/** Lo que devuelve `POST /api/cognition/console`: los asientos y las claves firmadas. */
export interface CognitionSubmitted {
  recorded: number[];
  keys: string[];
  source: string;
  source_display: string;
  recorded_by: string;
}

/** Una sesion leida del registro firmado, con las palabras del backend. */
export interface CognitionRecordedSession {
  effective: string;
  source: string;
  source_display: string;
  recorded_by: string | null;
  recorded_by_display: string;
  observation_type: string;
  evidence_context: string;
  position: EntryPosition;
  position_note: string;
  values: {
    key: string;
    sigla: string;
    measure_display: string;
    display: string;
    display_es: string;
    value: number;
    value_text: string;
  }[];
}

export interface CognitionSessions {
  subject: string;
  count: number;
  reference_time: string | null;
  sessions: CognitionRecordedSession[];
}

export const cognitionApi = {
  protocol: () => request<CognitionProtocol>("/cognition/protocol"),
  sessions: (subject: string, limit = 5) =>
    request<CognitionSessions>(`/cognition/sessions${queryOf({ subject, limit })}`),
  /** Las puntuaciones que dio el programa de la bateria, firmadas en el ledger (invariante 4). */
  submit: (body: CognitionSubmissionBody) => post<CognitionSubmitted>("/cognition/console", body),
};

/** Una nota firmada en Tierra para la tripulación (`ground-note`, §5.38.1). El texto, tal cual. */
export interface GroundNote {
  ledger_index: number;
  kind: "information" | "question";
  /** La palabra de la clase, del backend. */
  kind_display: string;
  text: string;
  signed_by: string;
  /** Hora de firma en Tierra (la del asiento). A bordo se ve un tiempo de luz después. */
  signed_at: string;
  /** Un tripulante, o `tripulacion` para toda la tripulación (`crew_subject` de las reglas). */
  addressed_to: string;
  addressed_to_display: string;
}

export interface GroundNotes {
  subject: string;
  /** El corte con que se pidió: lo firmado después no se entrega ni se cuenta. */
  until: string | null;
  notes: GroundNote[];
  /** Ya llegadas y no enseñadas: otra clave, o un texto que la regla vigente rechaza. */
  withheld: number;
  withheld_note: string | null;
  basis: string;
}

/** Las reglas de una nota de Tierra, con sus palabras: la interfaz no las redacta. */
export interface GroundNoteRules {
  kinds: { code: GroundNote["kind"]; display: string }[];
  max_length: number;
  crew_subject: string;
  crew_display: string;
  basis: string;
  refused: string;
}

/** Una lista de fuentes del equipo (`GET /api/context-sources`). */
export interface ContextSourceList {
  id: string;
  document: string;
  section: string;
  title: string;
}

/**
 * Una fuente del contexto. `status` es el enumerado de `app/evidence/context_sources.py` y
 * `status_text`, su palabra: la interfaz enseña la palabra. De una lista del equipo trae
 * `listed_as`; de fuera, `why_added`. `not_read` es `null` solo en lo leído entero.
 */
export interface ContextSource {
  ref: string;
  lists: string[];
  listed_as: string | null;
  why_added: string | null;
  status: string;
  status_text: string;
  not_read: string | null;
  emma_use: string;
  card: EvidenceCard;
}

export interface ContextSources {
  note: string;
  read_on: string;
  lists: ContextSourceList[];
  sources: ContextSource[];
}

export const contextSourcesApi = {
  get: () => request<ContextSources>("/context-sources"),
};

/** A dónde llega un dato (`app/sharing.py` `DESTINATIONS`). */
export type SharingDestination = "internet" | "ground" | "board" | "device" | "nowhere";

/** Una categoría de dato de `GET /api/sharing`: todo su texto lo da el backend. */
export interface SharingItem {
  id: string;
  title: string;
  destination: SharingDestination;
  destination_text: string;
  text: string;
  enforcement: "code" | "partial" | "none";
  enforcement_text: string;
  limit: string | null;
  enforced_by: string[];
}

export interface SharingPurpose {
  purpose: string;
  what: string;
  carries: string;
  hosts: string[];
}

export interface SharingRoute {
  path: string;
  direction: "down" | "up";
  direction_text: string;
}

export interface Sharing {
  note: string;
  destinations: { id: SharingDestination; label: string }[];
  items: SharingItem[];
  internet: { offline: boolean; offline_text: string; purposes: SharingPurpose[] };
  ground_cut: { note: string; routes: SharingRoute[] };
}

export const sharingApi = {
  get: () => request<Sharing>("/sharing"),
};

export const groundNotesApi = {
  rules: () => request<GroundNoteRules>("/ground-notes/rules"),
  /** Con `until` (a bordo: el reloj menos un tiempo de luz), solo lo que ya ha llegado. */
  list: (subject: string, until?: Date) =>
    request<GroundNotes>(`/ground-notes${queryOf({ subject, until: until?.toISOString() })}`),
  /** La firma la consola de Tierra, con su propia clave; un texto que manda es un 422. */
  sign: (body: { subject: string; kind: GroundNote["kind"]; text: string; signed_by: string }) =>
    post<{ ledger_index: number; signed_at: string }>("/ground-notes", body),
};

/**
 * La petición de ayuda urgente (`backend/app/api/help_requests.py`, 2026-11-14): firmada a bordo, la
 * tripulación la ve al momento con el resto ordenado por cercanía, y Tierra con su corte. Todo
 * texto (titular, base, cercanía, ubicación, qué hacer sin más tripulantes) es del backend.
 */
export interface HelpNearby {
  subject: string;
  proximity: "same_module" | "other_module" | "unknown";
  proximity_display: string;
  location_display: string;
}

export interface HelpRequest {
  ledger_index: number;
  subject: string;
  /** Opcional: pedir ayuda no espera a que nadie escriba su nombre. */
  signed_by: string | null;
  reason: string | null;
  /** El instante de la misión en que se pidió (el de los datos). */
  at: string;
  /** La hora de firma del asiento: con ella cuenta el retardo hacia Tierra. */
  signed_at: string;
  location_display: string;
  nearby: HelpNearby[];
  nearby_note: string | null;
}

export interface HelpRequests {
  until: string | null;
  headline: string;
  basis: string;
  open: HelpRequest[];
}

export const helpRequestsApi = {
  /** Con `until` (Tierra: su corte de reloj), solo lo firmado a bordo que ya ha llegado. */
  list: (until?: Date) => request<HelpRequests>(`/help-requests${queryOf({ until: until?.toISOString() })}`),
  ask: (body: { subject: string; signed_by: string; reason: string; at: string }) =>
    post<{ ledger_index: number; signed_at: string }>("/help-requests", body),
  close: (ledgerIndex: number, signedBy: string) =>
    post<{ ledger_index: number; signed_at: string }>(`/help-requests/${ledgerIndex}/close`, { signed_by: signedBy }),
};

/**
 * El asistente «EMMA» (`frontend/src/assistant/`, `backend/app/api/assistant.py`). Qué hay: si el
 * modelo local responde, cuál es, por qué no si no, si hay voz (Whisper local) y el catálogo
 * cerrado de intenciones, cada una de lectura (`read`, se hace al momento) o de escritura
 * (`write`, se propone y solo se firma con «confirmo»). Todo texto es del backend.
 */
export interface AssistantIntent {
  id: string;
  kind: "read" | "write";
  label: string;
  args: string[];
}

export interface AssistantInfo {
  available: boolean;
  model: string | null;
  reason: string | null;
  voice_available: boolean;
  /** Quién oye lo dicho: el propio modelo del asistente o Whisper (`null`, nadie). */
  voice_by?: "model" | "whisper" | null;
  intents: AssistantIntent[];
  /** El inventario de la interfaz (`backend/app/data/assistant_ui.json`), sin su nota. */
  ui: UiInventory;
}

/** Dónde se monta un panel: la consola y la pestaña (`null`, fuera de las pestañas; `env-*`, las de entorno). */
export interface UiPlace {
  console: "crew" | "ground";
  section: string | null;
}

/** Un panel, apartado o pliegue: en el DOM lleva `data-ui="<id>"`. */
export interface UiPanel {
  id: string;
  kind: "panel" | "part" | "fold";
  label: string;
  aliases: string[];
  places: UiPlace[];
  /** Qué enseña y qué deja hacer, en una o dos frases: el mapa de la aplicación que lee el modelo. */
  about: string;
}

/** Un modo de pantalla y la intención que lo cambia. */
export interface UiMode {
  id: string;
  kind: "toggle" | "choice";
  intent: string;
  label: string;
  aliases: string[];
  about: string;
}

export interface UiSection {
  key: string;
  label: string;
  aliases: string[];
  about: string;
  /** Apartada de esta versión: la consola no la monta (`ConsoleSection.setAside`). */
  set_aside?: boolean;
}

export interface UiInventory {
  consoles: { id: "crew" | "ground"; label: string; aliases: string[]; about: string }[];
  sections: {
    crew: UiSection[];
    ground: UiSection[];
    environments: { prefix: string; aliases: string[]; about: string };
  };
  modes: UiMode[];
  panels: UiPanel[];
}

/** Un turno ya dicho de la conversación, de la persona o del asistente. */
export interface AssistantHistoryItem {
  role: "user" | "assistant";
  text: string;
}

export interface AssistantTurnRequest {
  text: string;
  console: "crew" | "ground";
  subject: string;
  /** Los últimos turnos de esta sesión, como mucho ocho; nunca se guardan. */
  history: AssistantHistoryItem[];
  operator: string;
  /**
   * Los modos de pantalla de sí o no que la consola tiene puestos ahora (`DisplayModes`): con
   * ellos el backend entiende «ya se han ido» con la privacidad puesta. No se guardan.
   */
  modes?: Record<string, boolean>;
  /**
   * Los botones que la consola tiene a la vista (`assistant/controls.ts`): su rótulo y si pulsarlo
   * guarda algo. Con ellos el asistente puede elegir uno para pulsarlo; nunca se guardan.
   */
  controls?: AssistantControl[];
}

/** Un botón a la vista. `writes`: pulsarlo guarda algo, y entonces no se pulsa sin «confirmo». */
export interface AssistantControl {
  label: string;
  writes: boolean;
}

/**
 * La respuesta a un turno. `reply` lo dice la consola tal cual; `reply_source` dice quién lo
 * redactó: el modelo local (con `label`, «sin validar»), el backend o una frase fija. Una
 * intención de escritura llega con `proposal` y `needs_confirmation`: la consola la enseña y no
 * firma nada hasta que la persona confirma. `checks` son las barreras del backend.
 */
export interface AssistantTurn {
  intent: string;
  args: Record<string, unknown>;
  reply: string;
  /** `general`: conocimiento del modelo, sin fuente, de algo no clínico; con su `label`. */
  reply_source: "model" | "backend" | "fixed" | "general";
  needs_confirmation: boolean;
  proposal: Record<string, unknown> | null;
  checks: { text_guard: boolean; numbers: boolean; no_prescription: boolean; schema: boolean };
  label: string | null;
}

export interface AssistantAudioTurn {
  transcript: string;
  heard_by?: "model" | "whisper";
  turn: AssistantTurn;
}

/** Lo que acompaña a un trozo de voz: lo mismo que un turno escrito, salvo el texto. */
export type AssistantAudioContext = Omit<AssistantTurnRequest, "text">;

/**
 * El cuerpo de `POST /api/assistant/audio`, en un solo sitio para ajustarlo al contrato final del
 * backend: `multipart/form-data` con el WAV (`audio`, PCM de 16 bits, 16 kHz, mono:
 * `assistant/wav.ts`), `console`, `subject`, `history` (JSON) y `operator`. El `Content-Type` con
 * su frontera lo pone el navegador.
 */
/** UTF-8 a base64, sin `btoa` sobre texto con tildes (que lanzaría). */
function utf8Base64(text: string): string {
  let binary = "";
  for (const byte of new TextEncoder().encode(text)) binary += String.fromCharCode(byte);
  return btoa(binary);
}

/**
 * La petición de un trozo de voz, tal como la espera `POST /api/assistant/audio`
 * (`backend/app/api/assistant.py`): el WAV como cuerpo binario, la consola y el tripulante en la
 * consulta, el historial en `X-EMMA-History` (JSON en UTF-8, en base64) y quien firma en
 * `X-EMMA-Operator` (codificado por ciento). La cabecera de la consola la pone `request`.
 */
export function assistantAudioRequest(audio: Blob, context: AssistantAudioContext): { path: string; init: RequestInit } {
  const query = new URLSearchParams({ console: context.console, subject: context.subject });
  const headers: Record<string, string> = {
    "Content-Type": audio.type || "audio/wav",
    "X-EMMA-History": utf8Base64(JSON.stringify(context.history)),
  };
  if (context.operator) headers["X-EMMA-Operator"] = encodeURIComponent(context.operator);
  // Los modos puestos, por sus ids (`privacy,lowVision`); vacía si no hay ninguno.
  if (context.modes) {
    headers["X-EMMA-Modes"] = Object.entries(context.modes)
      .filter(([, on]) => on)
      .map(([id]) => id)
      .join(",");
  }
  // Los botones a la vista, como `controls` en `/turn`: JSON en UTF-8, en base64.
  if (context.controls && context.controls.length > 0) {
    headers["X-EMMA-Controls"] = utf8Base64(JSON.stringify(context.controls));
  }
  return { path: `/assistant/audio?${query.toString()}`, init: { method: "POST", body: audio, headers } };
}

export const assistantApi = {
  info: () => request<AssistantInfo>("/assistant"),
  turn: (body: AssistantTurnRequest) => post<AssistantTurn>("/assistant/turn", body),
  /** Un trozo de voz en WAV: lo pasa a texto el modelo local que oye o Whisper, y se contesta como un turno. */
  audio: (audio: Blob, context: AssistantAudioContext) => {
    const { path, init } = assistantAudioRequest(audio, context);
    return request<AssistantAudioTurn>(path, init);
  },
};
