/**
 * La comida frente a su criterio de aceptable, preparada para pintarla.
 *
 * Por qué existe: el usuario decidió (2026-10-15) que el criterio de 6,0 de la escala hedónica
 * se evalúe, y desde el 2026-10-16 el backend marca cada valoración de la comida por debajo con
 * la frase de NASA-STD-3001 Vol. 2 [V2 7002] y su página (`GET /api/nutrition/food-acceptability`).
 * Ninguna pantalla lo decía: el dominio de nutrición seguía «nominal», con razón, y no se veía
 * qué comida quedaba por debajo ni de dónde salía el 6. Aquí se prepara para el panel, y lo que
 * no puede pasar se comprueba sin navegador:
 *
 * - La marca no es una alerta: es sobre la comida, no sobre la persona. Va sin color de aviso,
 *   con el triángulo común y la palabra del backend; nunca rojo ni amarillo.
 * - Sin criterio leído no se marca nada: ni «por debajo» ni «no está por debajo».
 * - La frase de la norma va con su ubicación, su cita, cuánto se leyó y cuándo, en su idioma.
 * - Aquí no se redacta ni se calcula nada: si una valoración queda por debajo y cómo se lee su
 *   cifra lo da el backend, tal cual. Los recuentos pasan por `lib/format.ts`.
 * - Plato a plato (decisión del usuario, 2026-10-26): cada valoración lleva su alimento, y el
 *   backend las agrupa por plato con cuántas veces, en cuántos días y cada valoración en el
 *   tiempo. Es descriptivo: ni umbral ni veredicto de fatiga de menú, y sin color. El recuento
 *   de cada plato, la regla de agrupar y la nota de lo que no dice son del backend.
 * - De la primera a la última, y la fracción rechazada (decimonovena ronda, 2026-10-31): cada
 *   plato trae del backend la frase que compara su primera y su última valoración, y la de la
 *   fracción rechazada anotada con su nombre (o las palabras para «sin fracción declarada»). Se
 *   pintan tal cual, sin color ni flecha: dos cifras no son un veredicto.
 */
import type { FoodAcceptability, FoodDish, FoodRating } from "../lib/api";
import { formatNumber, formatUtc } from "../lib/format";
import { type StateMark, mark } from "../lib/marks";
import { type Cited, cited } from "../pvt/published";

/**
 * Por debajo del criterio: el triángulo común, en el color del texto (`text`, sin significado
 * de aviso: marcar la comida no es avisar de nada sobre la persona).
 */
const BELOW_CRITERION: StateMark = mark("shape-triangle", "text");

export interface FoodMark {
  /** Pictograma y color de la marca (`lib/marks.ts`). */
  mark: StateMark;
  /** La palabra del backend. */
  text: string;
}

/** La marca de una valoración, o `null` si no la lleva (o no hay criterio con que compararla). */
export function foodMark(rating: FoodRating): FoodMark | null {
  if (rating.below !== true || rating.mark === null) return null;
  return { mark: BELOW_CRITERION, text: rating.mark };
}

export interface FoodRow {
  key: string;
  when: string;
  value: string;
  /** El alimento firmado, o las palabras del backend para «sin alimento declarado». */
  food: string;
  /** Si la valoración lleva alimento: sin él, la palabra va con la marca de «no disponible». */
  hasFood: boolean;
  source: string;
  observationType: string;
  evidenceContext: string;
  mark: FoodMark | null;
}

export interface FoodCriterionView {
  /** La frase de la norma, con su ubicación y su cita. */
  quote: Cited;
  language: string;
  rule: string;
  appliesTo: string;
  scope: string;
}

export interface FoodDishPoint {
  key: string;
  when: string;
  value: string;
  mark: FoodMark | null;
}

export interface FoodDishRow {
  key: string;
  food: string;
  /** El recuento del plato, escrito por el backend. */
  statement: string;
  times: string;
  days: string;
  first: string;
  last: string;
  /** Cada valoración del plato, de la primera a la última. */
  series: FoodDishPoint[];
  /** De la primera a la última, con las palabras del backend; `null` si la respuesta no lo trae. */
  change: string | null;
  /** La fracción rechazada del plato, o las palabras del backend para «sin declarar»; `null` si la respuesta no lo trae. */
  rejected: string | null;
}

/** Plato a plato: `null` si el backend no lo da (una respuesta anterior al campo). */
export interface FoodDishesView {
  statement: string;
  rows: FoodDishRow[];
  grouping: string;
  repetition: string;
  /** La nota del backend sobre las valoraciones sin alimento; `null` si no hay ninguna. */
  withoutFood: string | null;
  /** Lo que dicen y lo que no la comparación y la fracción rechazada; `null` si la respuesta no las trae. */
  changeNote: string | null;
  rejectedNote: string | null;
}

export interface FoodView {
  title: string;
  /** El recuento, escrito por el backend. */
  statement: string;
  /** Ninguna valoración en el registro: el recuento va con la marca de dato ausente. */
  empty: boolean;
  criterion: FoodCriterionView | null;
  rows: FoodRow[];
  /** «Las N últimas de M» si la lista no las trae todas; si no, `null`. */
  shown: string | null;
  /** Lecturas apartadas por no ser medidas, con la nota del backend; `null` si no hay. */
  notMeasured: string | null;
  dishes: FoodDishesView | null;
}

function dishRow(dish: FoodDish): FoodDishRow {
  return {
    key: dish.food,
    food: dish.food,
    statement: dish.statement,
    times: formatNumber(dish.times),
    days: formatNumber(dish.distinct_days),
    first: formatUtc(new Date(dish.first_effective)),
    last: formatUtc(new Date(dish.last_effective)),
    // Dos valoraciones del mismo plato pueden coincidir en instante y valor: la posición desempata.
    series: dish.series.map((point, index) => ({
      key: `${index}|${point.effective}|${point.value}`,
      when: formatUtc(new Date(point.effective)),
      value: point.value_text,
      mark: point.below === true && point.mark !== null ? { mark: BELOW_CRITERION, text: point.mark } : null,
    })),
    change: dish.change?.statement ?? null,
    rejected: dish.rejected_display ?? dish.rejected?.statement ?? null,
  };
}

/** Plato a plato, tal como lo da el backend; `null` si la respuesta no lo trae. */
export function dishesView(data: FoodAcceptability): FoodDishesView | null {
  if (data.dishes === undefined || data.dishes_statement === undefined) return null;
  return {
    statement: data.dishes_statement,
    rows: data.dishes.map(dishRow),
    grouping: data.grouping ?? "",
    repetition: data.repetition_note ?? "",
    // El recuento ya va en `statement`; aquí, la nota del backend, solo si hay alguna.
    withoutFood: (data.without_food ?? 0) > 0 ? (data.without_food_note ?? null) : null,
    changeNote: data.change_note ?? null,
    rejectedNote: data.rejected_note ?? null,
  };
}

export function foodView(data: FoodAcceptability): FoodView {
  const criterion = data.criterion;
  return {
    title: data.display_es,
    statement: data.statement,
    empty: data.rated === 0,
    criterion:
      criterion === null
        ? null
        : {
            quote: cited(criterion.statement),
            language: criterion.language,
            rule: criterion.rule,
            appliesTo: criterion.applies_to,
            scope: criterion.scope,
          },
    rows: data.ratings.map((rating) => ({
      key: `${rating.effective}|${rating.source}|${rating.value}`,
      when: formatUtc(new Date(rating.effective)),
      value: rating.value_text,
      food: rating.food_display ?? rating.food ?? "",
      hasFood: rating.food !== null && rating.food !== undefined,
      source: rating.source_display,
      observationType: rating.observation_type,
      evidenceContext: rating.evidence_context,
      mark: foodMark(rating),
    })),
    shown:
      data.shown < data.rated
        ? `Las ${formatNumber(data.shown)} últimas de ${formatNumber(data.rated)}.`
        : null,
    notMeasured:
      data.not_measured_excluded > 0
        ? `${formatNumber(data.not_measured_excluded)} apartadas. ${data.not_measured_note}`
        : null,
    dishes: dishesView(data),
  };
}
