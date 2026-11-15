/**
 * Lo poco que el panel de habitat decide por si mismo: con que pictograma y que color se pinta el
 * estado de un paso del flujo, y como se escribe un limite.
 *
 * Por que existe: los siete pasos de una hipotesis (especificacion §7) llegan del backend con
 * su nombre, su estado y su frase. La interfaz no redacta ni deduce ninguno —si dedujera "esta
 * pendiente" de que falta una revision, habria dos sitios decidiendo lo mismo—; solo elige la
 * marca. Y esa eleccion tiene reglas que merecen prueba: el color nunca va solo (pictograma y la
 * palabra del backend), el cian y el amarillo no se usan aqui (un paso pendiente no es un dato
 * ausente ni una precaucion), y un estado que esta version no conoce se pinta sin significado
 * en vez de fallar o de disfrazarse de otro.
 */

import type { HabitatParameter, HabitatReferenceRequirement } from "../lib/api";
import { displayUnit, formatNumber } from "../lib/format";
import { tr } from "../lib/i18n";
import { type StateMark, UNKNOWN_MARK, mark } from "../lib/marks";

/**
 * Tabla F.5-1: azul es "advisory" (algo espera a una persona o sigue abierto, sin ser una
 * alerta) y gris es "no disponible" (el paso no le corresponde a esta hipotesis). Hecho va sin
 * color: que algo este hecho no es un aviso. Los dibujos son los de los glifos que habia (✓ ☐ ↻ –).
 */
const MARKS: Record<string, StateMark> = {
  done: mark("check", "text"),
  awaiting_human: mark("box-empty", "blue"),
  in_progress: mark("refresh", "blue"),
  not_applicable: mark("dash", "gray"),
};

/** La marca de un estado. Uno desconocido no lleva significado: lo dice la palabra del backend. */
export function stepMark(state: string): StateMark {
  return MARKS[state] ?? UNKNOWN_MARK;
}

/**
 * La marca de la clase de un limite que se ha salido (`HabitatExcursion.kind`, §5.28): fuera del
 * limite normativo es precaucion (triangulo amarillo); fuera de la zona de confort o del rango
 * objetivo es aviso (rombo azul). Una sola tabla para la fila de atmosfera, la lista de
 * excursiones y la leyenda de la comparacion, que antes la escribian cada una a mano.
 */
const LIMIT_MARKS: Record<string, StateMark> = {
  health: mark("shape-triangle", "yellow"),
  performance: mark("shape-diamond", "blue"),
  target: mark("shape-diamond", "blue"),
};

export function limitMark(kind: string): StateMark {
  return LIMIT_MARKS[kind] ?? UNKNOWN_MARK;
}

/**
 * Unidades de escala de razon: el cero es la ausencia de lo medido (no hay CO2, no hay presion,
 * no hay contaminante, no hay vapor de agua), asi que «el doble del limite» es una cifra con
 * sentido fisico. El valor es el techo que la propia unidad impone: una humedad relativa no pasa
 * del 100 %. Los decibelios y los grados Celsius no estan: su cero es una convencion (umbral de
 * audicion, hielo fundente), y el doble de 85 dB(A) o de 27 °C no es «el doble» de nada.
 */
const RATIO_UNITS: Readonly<Record<string, number>> = {
  "mm[Hg]": Number.POSITIVE_INFINITY,
  kPa: Number.POSITIVE_INFINITY,
  "[ppm]": Number.POSITIVE_INFINITY,
  "%": 100,
};

export interface MeterScale {
  min: number;
  max: number;
  band: { low: number; high: number };
}

/**
 * La escala del medidor de un parametro de cabina (§5.33.4), o `null` si no se puede dar sin
 * inventarla.
 *
 * El backend no da una escala de presentacion: da el limite normativo. Por eso el medidor solo
 * existe donde ese limite basta para fijarla sin decidir nada clinico:
 *
 * - **Un solo limite normativo**: con varios (los SMAC de 1 h a 1000 d del CO y del amoniaco, los
 *   cuatro del O2) la banda tendria que elegir uno, y cual rige una lectura suelta depende de la
 *   media que el backend calcula, no de la interfaz.
 * - **Sin figura conjunta**: el de la temperatura depende de la humedad del mismo instante, y
 *   `low`/`high` son solo su envolvente.
 * - **Con techo y en unidad de razon** (`RATIO_UNITS`): escala `[0, 2 × techo]`, con el techo a
 *   media barra, para que «cuanto queda hasta el limite» y «cuanto se ha pasado» se lean igual;
 *   recortada al techo de la propia unidad. La banda es lo permitido: `[suelo o 0, techo]`.
 *
 * Nada de esto cambia niveles ni umbrales: es donde se pinta la barra.
 */
export function meterScale(spec: Pick<HabitatParameter, "unit" | "limits">): MeterScale | null {
  const health = spec.limits.filter((limit) => limit.kind === "health");
  const limit = health[0];
  if (health.length !== 1 || limit === undefined) return null;
  if (limit.figure != null || limit.high === null || !(limit.high > 0)) return null;
  const cap = RATIO_UNITS[spec.unit];
  if (cap === undefined) return null;
  const low = limit.low ?? 0;
  if (low < 0 || low > limit.high) return null;
  const max = Math.min(2 * limit.high, cap);
  if (max < limit.high) return null;
  return { min: 0, max, band: { low, high: limit.high } };
}

/** Cifras pequeñas (formaldehido 0,02 ppm) necesitan mas decimales para no leerse 0,0. */
export function decimalsFor(value: number): number {
  return Math.abs(value) < 1 ? 2 : 1;
}

function bound(low: number | null, high: number | null): string {
  if (low !== null && high !== null) {
    return `${formatNumber(low, decimalsFor(low))}–${formatNumber(high, decimalsFor(high))}`;
  }
  if (high !== null) return `≤ ${formatNumber(high, decimalsFor(high))}`;
  return `≥ ${formatNumber(low ?? 0, decimalsFor(low ?? 0))}`;
}

/**
 * La cifra de un requisito que se ensena junto a una lectura y NO se evalua (los niveles de
 * iluminacion por tarea). Solo escribe lo que da el backend: aqui no se compara con la lectura
 * ni se elige que requisito "toca", porque EMMA no conoce la tarea.
 */
export function referenceFigure(
  item: Pick<HabitatReferenceRequirement, "low" | "high" | "stated" | "unit">,
): string {
  const unit = displayUnit(item.unit);
  // El valor que la tabla da sin comparador se escribe sin comparador: ni "≥" ni "≤".
  if (item.stated !== null) {
    return `${formatNumber(item.stated, decimalsFor(item.stated))} ${unit}`;
  }
  // Sin cifra no se escribe ninguna (`bound` pondria un "≥ 0" que nadie ha leido).
  if (item.low === null && item.high === null) return "";
  return `${bound(item.low, item.high)} ${unit}`;
}

/**
 * Los limites de salud de un parametro, cada uno con su requisito. Un parametro puede tener
 * varios, cada uno con su tiempo de media (SMAC). Sin ninguno devuelve "": quien no tiene
 * limite no recibe uno inventado aqui; su frase la da el backend (`limit_note`).
 */
export function healthRange(spec: Pick<HabitatParameter, "unit" | "limits">): string {
  const unit = displayUnit(spec.unit);
  return spec.limits
    .filter((limit) => limit.kind === "health")
    .map((limit) =>
      limit.figure
        ? tr(
            `${bound(limit.low, limit.high)} ${unit} según la humedad simultánea `,
            `${bound(limit.low, limit.high)} ${unit} depending on the simultaneous humidity `,
          ) +
          `(${limit.requirement}, ${limit.figure.name}: ${figureVertices(limit.figure.vertices, unit)})`
        : `${bound(limit.low, limit.high)} ${unit} (${limit.requirement})`,
    )
    .join(" · ");
}

/**
 * Los vertices de una figura conjunta, cada cifra por `format.ts`. El par de la figura de
 * [V2 6012] es la humedad relativa: su unidad es el porcentaje.
 */
export function figureVertices(vertices: number[][], unit: string): string {
  return vertices
    .map(([value, pair]) =>
      value === undefined || pair === undefined
        ? ""
        : `${formatNumber(value, decimalsFor(value))} ${unit} ${formatNumber(pair, 0)} %`,
    )
    .filter((text) => text !== "")
    .join(", ");
}

/**
 * Los rotulos del backend de los limites que no son de confort (los normativos y el rango
 * objetivo), con su requisito delante. Se ensenan tal cual: la interfaz no los redacta.
 */
export function limitLabels(spec: Pick<HabitatParameter, "limits">): string[] {
  return spec.limits
    .filter((limit) => limit.kind !== "performance" && limit.label)
    .map((limit) => `${limit.requirement}: ${limit.label}`);
}
