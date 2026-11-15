import { hasIndicatorFamily, indicatorFamily } from "../lib/indicatorFamily";
import { UNKNOWN_MARK } from "../lib/marks";
import { Mark } from "./Mark";

/**
 * El nombre de un indicador con el pictograma de su familia (`lib/indicatorFamily.ts`), sin
 * color: nombrar una medida no es avisar de nada. La palabra es `display_es`, tal cual la da el
 * backend; la lateralidad (derecha, izquierda) va en ese texto, no en el dibujo. `key` es palabra
 * reservada de React, por eso la clave del catálogo se llama `indicatorKey`.
 *
 * Una clave sin familia (un backend con un indicador que esta interfaz aún no conoce) se enseña
 * con su nombre y la marca de «desconocido», como un dominio desconocido: la consola no se cae
 * por un dibujo que falta. La paridad con el catálogo la vigila el backend.
 */
export function IndicatorName({ indicatorKey, displayEs }: { indicatorKey: string; displayEs: string }) {
  const pictogram = hasIndicatorFamily(indicatorKey) ? indicatorFamily(indicatorKey) : UNKNOWN_MARK.pictogram;
  return <Mark pictogram={pictogram}>{displayEs}</Mark>;
}
