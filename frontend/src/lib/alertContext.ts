/**
 * Como se presenta el contexto de una alerta y su concordancia (`app/analysis/alert_context.py`),
 * y con que flecha va cada cambio de «que cambio» (`app/analysis/explain.py`).
 *
 * Existe para que la vista no decida nada por su cuenta: las frases las da el backend, y aqui
 * solo se fija con que señal se pinta lo que falta. La tabla F.5-1 de NASA-STD-3001 Vol 2 reserva
 * el cian para "Missing or stale data": una fuente sin dato en la ventana, o con dato parcial, es
 * exactamente eso, y nunca va solo el color (F.5.10 e): lleva su pictograma (el anillo punteado,
 * `ring-dotted`) y la palabra del backend. Lo que si tiene dato no lleva señal ni color: "se
 * desvia" o "va en contra" describen, no son un nivel de alerta, y pintarlos de amarillo o azul
 * diria otra cosa.
 *
 * La flecha de F.4.3.1 d («a yellow or red up or down arrow ... outside of upper or lower
 * thresholds») sale SOLO del campo estructurado `direction` que da el backend en cada cambio
 * (`high`/`low`) y en cada tendencia (`rising`/`falling`/`stable`): nunca se deduce de la frase.
 * Sin ese campo, o con un valor que la interfaz no conoce, no hay flecha: no se afirma un
 * sentido que no se sabe.
 */

import type { PictogramName } from "../icons/registry";
import type { AlertCostFact, ConcordanceState, ContextSourceStatus, CostFigure } from "./api";
import { formatNumber } from "./format";
import { type StateMark, MISSING_MARK, mark } from "./marks";

/** Con dato: nada que señalar, ni pictograma ni color. */
const PRESENT: StateMark = mark(null, null);

const SOURCE_MARKS: Record<ContextSourceStatus, StateMark> = {
  with_data: PRESENT,
  partial: MISSING_MARK,
  no_data: MISSING_MARK,
};

const STATE_MARKS: Record<ConcordanceState, StateMark> = {
  concordant: PRESENT,
  against: PRESENT,
  unchanged: PRESENT,
  no_data: MISSING_MARK,
};

/** Un estado que la interfaz no conoce no se pinta como "con dato": se dice. */
export function sourceStyle(status: string): StateMark {
  if (!Object.hasOwn(SOURCE_MARKS, status)) {
    throw new RangeError(`estado de fuente desconocido: ${status}`);
  }
  return SOURCE_MARKS[status as ContextSourceStatus];
}

export function concordanceStyle(state: string): StateMark {
  if (!Object.hasOwn(STATE_MARKS, state)) {
    throw new RangeError(`estado de concordancia desconocido: ${state}`);
  }
  return STATE_MARKS[state as ConcordanceState];
}

/** Sentido estructurado del backend -> flecha. Lo que no esta aqui no lleva flecha. */
const ARROWS: Record<string, PictogramName> = {
  high: "arrow-up",
  rising: "arrow-up",
  low: "arrow-down",
  falling: "arrow-down",
};

/**
 * La flecha de un cambio o de una tendencia (F.4.3.1 d), o `null` si el backend no da sentido
 * (`stable`, campo ausente de un backend anterior, valor desconocido). El color no se decide
 * aqui: es el del nivel de la alerta, y lo pone la vista.
 */
export function changeArrow(direction: string | null | undefined): PictogramName | null {
  if (direction === null || direction === undefined) return null;
  return Object.hasOwn(ARROWS, direction) ? (ARROWS[direction] ?? null) : null;
}

export interface CostFactGroups {
  /** Los datos que hay, y los que faltan con una base escrita: uno a uno, en su orden. */
  shown: AlertCostFact[];
  /** Los que faltan sin más, juntos por la palabra del backend que dice qué falta. */
  missing: { display: string; labels: string[] }[];
}

/**
 * Los datos del coste de una comprobación, partidos. Desde la decimosexta ronda cada indicador
 * lleva las dimensiones del coste (base de conocimiento §9 y conversación) y casi todas faltan: un «sin
 * clasificar» por cada una tapaba lo que sí se sabe. Lo que falta se junta por su palabra
 * («sin clasificar», «sin cifra con fuente»), que es del backend; qué falta lo dice `missing`,
 * no la palabra. Un dato ausente con base escrita (de dónde sale que no tenga cifra) va suelto,
 * para no perder la base. Nada se reordena entre los que hay.
 */
export function groupCostFacts(facts: AlertCostFact[]): CostFactGroups {
  const shown: AlertCostFact[] = [];
  const missing: CostFactGroups["missing"] = [];
  for (const fact of facts) {
    const hasBasis = fact.basis !== null && fact.basis !== undefined;
    if (!fact.missing || hasBasis) {
      shown.push(fact);
      continue;
    }
    const group = missing.find((item) => item.display === fact.display);
    if (group === undefined) missing.push({ display: fact.display, labels: [fact.label] });
    else group.labels.push(fact.label);
  }
  return { shown, missing };
}

/**
 * Lo que se pinta de un dato del coste de medir: una cifra leída (masa, volumen, potencia, volumen de datos) se
 * formatea aquí con `lib/format.ts`, con los decimales con que se leyó y su unidad tal cual; lo
 * demás es la palabra del backend. Lo usan el panel del coste de medir y el detalle de alerta,
 * para que la misma cifra se lea igual en las dos pantallas.
 */
export function costText(entry: { display: string; figure?: CostFigure | null }): string {
  if (entry.figure === null || entry.figure === undefined) return entry.display;
  return `${formatNumber(entry.figure.amount, entry.figure.decimals)} ${entry.figure.unit}`;
}

/** Decimales de una cifra de cabina: las pequeñas (0,02 ppm) necesitan mas para no leerse 0,0. */
export function cabinDecimals(value: number): number {
  return Math.abs(value) < 1 ? 2 : 1;
}
