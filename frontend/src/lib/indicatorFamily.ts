/**
 * A qué familia —y por tanto a qué pictograma— va cada indicador del catálogo.
 *
 * Por qué existe: el catálogo del backend (`app/ingest/codes.py`) tiene decenas de indicadores y
 * ningún campo que diga con qué dibujo se acompaña su nombre; inventarlo en cada panel daría un
 * dibujo distinto por pantalla. Aquí está una vez: cada clave del catálogo en una familia, y cada
 * familia es un pictograma de `icons/sets/indicators.ts`. La lateralidad (derecha, izquierda) y lo
 * que mide lo dice `display_es`, que va al lado; el pictograma solo dice de qué va.
 *
 * La paridad con el catálogo la vigila el backend (`tests/test_indicator_families.py`: ni una
 * clave de más ni de menos). Una clave que no está aquí falla en vez de pintarse con un dibujo
 * supuesto.
 */

import type { indicators } from "../icons/sets/indicators";

/** Una familia es, por construcción, un pictograma del conjunto `indicators`. */
export type IndicatorFamily = keyof typeof indicators;

/** Las claves del catálogo de cada familia. Se escribe por familia para leerse como el catálogo. */
export const FAMILY_KEYS: Readonly<Record<IndicatorFamily, readonly string[]>> = {
  "heart-pulse": ["heart-rate", "hrv-sdnn", "hrv-rmssd"],
  gauge: ["systolic-bp", "diastolic-bp", "orthostatic-drop"],
  lungs: ["respiratory-rate", "oxygen-saturation"],
  // La temperatura corporal y, desde el 2026-11-14, la basal (descriptiva, código propio): las dos
  // se miden con un termómetro; cuál es cuál lo dice `display_es`.
  thermometer: ["body-temperature", "basal-body-temperature"],
  // Masas del cuerpo: el peso y la masa magra del cuerpo entero por DXA (descriptiva, 2026-10-31).
  balance: ["body-weight", "dxa-lean-mass"],
  "moon-z": ["sleep-duration", "sleep-efficiency", "circadian-shift"],
  // Pruebas en pantalla: la PVT y las otras nueve pruebas de la batería Cognition
  // (descriptivas, 2026-10-31), de la que la PVT es la décima. Qué prueba y qué mide (velocidad o
  // precisión) lo dice `display_es`.
  stopwatch: [
    "pvt-mean-rt",
    "pvt-lapses",
    "cognition-mpt-speed",
    "cognition-volt-speed",
    "cognition-volt-accuracy",
    "cognition-f2b-speed",
    "cognition-f2b-accuracy",
    "cognition-am-speed",
    "cognition-am-accuracy",
    "cognition-lot-speed",
    "cognition-lot-accuracy",
    "cognition-ert-speed",
    "cognition-ert-accuracy",
    "cognition-mrt-speed",
    "cognition-mrt-accuracy",
    "cognition-dsst-speed",
    "cognition-dsst-accuracy",
    "cognition-bart-speed",
    "cognition-bart-risk",
  ],
  // Autoinformes: ánimo, carga de trabajo y diario de síntomas (no son muestras de laboratorio);
  // desde el 2026-10-31, el estrés de la escala visual analógica del Reaction Self Test y las tres
  // afirmaciones de cohesión del cuestionario de fin de día (descriptivos).
  "face-neutral": [
    "mood-valence",
    "nasa-tlx-workload",
    "symptom-burden",
    "stress-rating-vas",
    "team-cohesion-cared",
    "team-cohesion-task-focus",
    "team-cohesion-shared-purpose",
    // Los sofocos y los sudores nocturnos (descriptivos, 2026-11-15): síntomas que declara quien
    // los tiene, con la gravedad de HealthKit; van con la cara, como el diario de síntomas.
    "hot-flashes",
    "night-sweats",
  ],
  vial: ["cortisol-salivary", "latent-virus-shedding"],
  trefoil: ["absorbed-dose-rate", "cumulative-dose"],
  // Forma física y pruebas funcionales: ejercicio, VO2 pico, prensión, la tracción isométrica y
  // las dos pruebas sensoriomotoras de Standard Measures (descriptivas, 2026-10-31): el dibujo
  // dice «prueba de forma física funcional»; qué mide cada una lo dice su nombre.
  dumbbell: [
    "exercise-minutes",
    "loading-impacts",
    "vo2-peak",
    "grip-strength-right",
    "grip-strength-left",
    "imtp-peak-force",
    "tandem-walk-correct-steps",
    "recovery-from-fall-time",
  ],
  // Hueso: el NTx de su resorción, sus minerales y la vitamina D 25-OH (descriptiva), y su
  // densidad medida en Tierra por DXA (descriptiva, 2026-10-26).
  crystal: [
    "ntx-telopeptide",
    "calcium",
    "phosphate",
    "magnesium",
    "vitamin-d-25oh",
    "bmd-dxa-lumbar-spine",
    "bmd-dxa-hip",
  ],
  "eye-nerve": ["onsd-right", "onsd-left", "vision-change"],
  "vessel-flow": ["ijv-csa-right", "ijv-csa-left"],
  bladder: ["bladder-volume", "fluid-intake-24h", "urine-volume-24h", "urine-specific-gravity"],
  cells: [
    "leukocytes",
    "lymphocytes",
    "neutrophils",
    "neutrophils-percent",
    "lymphocytes-percent",
    "neutrophil-lymphocyte-ratio",
    "c-reactive-protein",
    "erythrocytes",
    "hemoglobin",
    "hematocrit",
    "mcv",
    "mch",
    "mchc",
    "platelets",
  ],
  kidneys: [
    "urea",
    "creatinine",
    "bun-creatinine-ratio",
    "sodium",
    "potassium",
    "chloride",
    // La química de la orina de 24 horas del riesgo de cálculos renales (descriptivos): el riñón,
    // donde se forma el cálculo, no la vejiga del volumen y la densidad.
    "urine-calcium-24h",
    "urine-oxalate-24h",
    "urine-urate-24h",
    "urine-citrate-24h",
    "urine-ph-24h",
    "urine-sodium-24h",
    "urine-osmolality-24h",
    "urine-caox-supersaturation-24h",
  ],
  liver: [
    "glucose",
    "glucose-capillary",
    "total-protein",
    "albumin",
    "ast",
    "alt",
    "ggt",
    "alkaline-phosphatase",
    "bilirubin-total",
    "bilirubin-direct",
    "ldh",
  ],
  molecule: ["tsh", "free-t4", "estradiol", "fsh", "lh"],
  flag: [
    "ca-15-3",
    "cea",
    "ca-125",
    "ca-19-9",
    "ca-27-29",
    "beta2-microglobulin",
    "chromogranin-a",
    "neuron-specific-enolase",
  ],
  // Comida: la energía y, desde el 2026-10-31, los nutrientes ingeridos al día (descriptivos).
  "fork-knife": [
    "energy-intake-daily",
    "appetite-rating",
    "food-rejected-fraction",
    "food-acceptability",
    "sodium-intake-daily",
    "calcium-intake-daily",
    "protein-intake-daily",
    "vitamin-d-intake-daily",
  ],
  bolt: ["pain-intensity"],
  // Los registros del ciclo menstrual y de la anticoncepción (descriptivos, 2026-11-14), con las
  // categorías de HealthKit. No van con la molécula de las hormonas: ninguno es un analito, y el
  // anticonceptivo registrado no dice si es hormonal.
  "drop-cycle": [
    "menstrual-flow",
    "menstruation-start",
    "intermenstrual-bleeding",
    "ovulation-test",
    "contraceptive-in-use",
    // El estado reproductivo declarado y la terapia hormonal de la menopausia (descriptivos,
    // 2026-11-15): registros de la vida reproductiva, no analitos.
    "reproductive-status",
    "menopausal-hormone-therapy",
  ],
};

/** Clave del catálogo → familia. Una clave en dos familias es un error de esta tabla, y se dice. */
const FAMILY_OF: ReadonlyMap<string, IndicatorFamily> = (() => {
  const map = new Map<string, IndicatorFamily>();
  for (const [family, keys] of Object.entries(FAMILY_KEYS) as [IndicatorFamily, readonly string[]][]) {
    for (const key of keys) {
      if (map.has(key)) throw new Error(`indicador en dos familias: ${key}`);
      map.set(key, family);
    }
  }
  return map;
})();

export const INDICATOR_FAMILIES: readonly IndicatorFamily[] = Object.keys(FAMILY_KEYS) as IndicatorFamily[];

/** Todas las claves del catálogo que tienen familia, en el orden de la tabla. */
export function indicatorKeys(): readonly string[] {
  return [...FAMILY_OF.keys()];
}

/** Si la clave tiene familia: para enseñar un indicador nuevo sin suponerle dibujo ni fallar. */
export function hasIndicatorFamily(key: string): boolean {
  return FAMILY_OF.has(key);
}

/** La familia de un indicador. Una clave desconocida falla: no se le supone un dibujo. */
export function indicatorFamily(key: string): IndicatorFamily {
  const family = FAMILY_OF.get(key);
  if (family === undefined) throw new RangeError(`indicador sin familia: ${key}`);
  return family;
}
