/**
 * Lo unico que el modo anatomico resuelve en el cliente: como se pinta lo que da el backend.
 *
 * Existe aparte del panel para poder probarlo. El panel calculaba el nivel de cada region (el
 * peor de sus dominios, "nominal" si faltaba), y eso son dos errores: el visor decidia un nivel
 * (especificacion §4: es cliente del estado, no fuente) y una region sin una sola lectura salia
 * nominal. Ahora el nivel llega hecho de `/api/anatomy/state`, y aqui solo queda nombrarlo:
 * `null` es "sin datos", nunca nominal, y un nivel desconocido falla en vez de pintarse.
 */

import { TIER_PICTOGRAMS } from "../evidence/sourceMarks";
import type { PictogramName } from "../icons/registry";
import type { FhirObservation } from "../lib/api";
import { missionElapsedSeconds } from "../lib/format";
import { tr } from "../lib/i18n";
import { levelStyle } from "../lib/levels";
import { UNKNOWN_PICTOGRAM, prefixedPictogram } from "../lib/marks";
import type { Token } from "../lib/palette";

export interface StateStyle {
  label: string;
  color: Token;
  pictogram: PictogramName;
}

/**
 * Sin lecturas y sin hallazgo: no hay estado. Cian, que en la tabla F.5-1 es "Missing or stale
 * data" (el gris es "no disponible", otra cosa), con el pictograma que la interfaz ya usa para
 * un dato que falta (`icons/sets/shapes.ts`). Nunca va solo el color (F.5.10 e): lleva palabra
 * y pictograma propios.
 */
export const NO_STATE: StateStyle = { label: tr("Sin datos", "No data"), color: "cyan", pictogram: "ring-dotted" };

/**
 * El dibujo de la capa de evidencia de investigación de una región (§5.37.16, §5.39.16): el matraz
 * de los niveles «modelo animal» e «in vitro» de las fichas (`evidence/sourceMarks.ts`), el de la
 * investigación de laboratorio frente a lo medido en el tripulante. Desde §5.39.16 la capa lleva
 * también estudios en otras personas: la población de cada ficha no la dice este dibujo, sino el
 * rótulo que cada una lleva encima, con la marca de su clase. Se toma de allí y no de la
 * biblioteca de contramedidas, donde el mismo dibujo dice otra cosa (lo que se está ensayando).
 */
export const RESEARCH_LAYER_PICTOGRAM: PictogramName = TIER_PICTOGRAMS["modelo_animal"] ?? UNKNOWN_PICTOGRAM;

/** El nivel que dio el backend, tal cual. `null` no es nominal; uno desconocido, tampoco. */
export function stateStyle(level: string | null): StateStyle {
  return level === null ? NO_STATE : levelStyle(level);
}

/**
 * El pictograma de un dominio de una region (`icons/sets/domains.ts`), para ponerlo delante del
 * `display` de la region en la lista del modo anatomico. Un dominio que la interfaz no conoce
 * lleva el dibujo de «desconocido», como hace `<DomainName>`: no se le supone uno.
 */
export function domainPictogram(domain: string): PictogramName {
  return prefixedPictogram("domain", domain);
}

/**
 * Las regiones sin dominio (sin nivel propio, como el hígado) llevan el dibujo de su órgano, no el
 * de un dominio: el hígado es el de la familia de los analitos hepáticos (`lib/indicatorFamily.ts`),
 * el mismo concepto, y los pulmones el de la familia respiratoria, que agrupa los mismos dos
 * indicadores. Una región sin dominio que no esté aquí lleva el de «desconocido».
 */
const ORGAN_PICTOGRAMS: Readonly<Record<string, PictogramName>> = { liver: "liver", lungs: "lungs" };

/** El dibujo de una región: el de su (primer) dominio o, sin dominio, el de su órgano. */
export function regionPictogram(region: { key: string; domains: readonly string[] }): PictogramName {
  const [domain] = region.domains;
  if (domain !== undefined) return domainPictogram(domain);
  return ORGAN_PICTOGRAMS[region.key] ?? UNKNOWN_PICTOGRAM;
}

const DAY = 86_400;

/** Segundos de mision de una lectura. */
export function metOf(missionStart: string, effective: string): number {
  return missionElapsedSeconds(missionStart, new Date(effective));
}

/**
 * Cuanto abarca la grafica de una variable: la ventana sobre la que el motor ajusto su
 * tendencia. Si la ultima lectura es anterior (un indicador que hace dias que no se mide), la
 * ventana se alarga hasta ella: una grafica vacia diria menos que una con el dato viejo a la
 * vista. Nunca empieza antes del origen de la mision.
 */
export function seriesWindowSeconds(
  variable: { effective: string; trend: { span_days: number } | null },
  trendWindowDays: number,
  missionStart: string,
  onboardUntil: number,
): number {
  const fitted = Math.max(trendWindowDays, variable.trend?.span_days ?? 0) * DAY;
  const sinceLast = onboardUntil - metOf(missionStart, variable.effective) + DAY;
  return Math.min(Math.max(fitted, sinceLast), Math.max(onboardUntil, 0));
}

/** Las lecturas de un indicador como puntos de la grafica, en orden de tiempo. */
export function seriesPoints(
  resources: Pick<FhirObservation, "effectiveDateTime" | "valueQuantity">[],
  missionStart: string,
): { met: number; value: number }[] {
  return resources
    .map((item) => ({
      met: metOf(missionStart, item.effectiveDateTime),
      value: item.valueQuantity.value,
    }))
    .sort((a, b) => a.met - b.met);
}
