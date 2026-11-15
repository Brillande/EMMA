/**
 * Dónde va cada rótulo de la silueta, por su alto medido, o si pasan todos a la lista de debajo.
 *
 * Por qué existe (decimoquinta ronda, §5.35.11): cada rótulo iba a la altura fija de su zona en
 * el dibujo, centrado en ella, con la franja que ocupa supuesta (dos líneas a 0,85 rem). Con el
 * texto del navegador al 150 % y al 200 % los rótulos crecen en alto y, a la misma altura fija,
 * se montaban unos sobre otros (Cardiovascular sobre Nutrición, Musculoesquelético sobre
 * Genitourinario, §5.34.14); y el hígado, a la altura de la espalda y por el mismo lado, chocaba
 * con «Musculoesquelético» incluso a tamaño normal.
 *
 * Aquí se colocan con su alto real: por cada lado del dibujo, de arriba abajo, los rótulos que se
 * pisarían se juntan en un bloque centrado lo más cerca posible de sus zonas (el centro que hace
 * mínima la suma de los cuadrados de lo que se aleja cada uno), dentro del alto de la figura. Si
 * para no pisarse alguno tendría que alejarse de su zona más de `MAX_SHIFT` —y entonces ya no se
 * lee junto a ella— o no caben en el alto de la figura, no se fuerza: pasan todos a la lista de
 * debajo, como en pantalla estrecha. Todo en unidades del lienzo (480 de alto): el que llama pasa
 * a ellas los píxeles medidos.
 *
 * Es solo colocación: no decide qué se dice ni de qué color. Función pura, para probarla sin
 * navegador.
 */

/** Un rótulo por colocar: su lado, la altura de su zona y su alto medido (unidades del lienzo). */
export interface SiteBox {
  readonly key: string;
  readonly side: "left" | "right";
  readonly anchor: number;
  readonly height: number;
}

export interface SitePlacement {
  /** `true`: no caben junto a sus zonas sin pisarse; van todos en la lista de debajo. */
  readonly listed: boolean;
  /** El centro de cada rótulo, en unidades del lienzo (vacío si van en la lista). */
  readonly centres: Readonly<Record<string, number>>;
}

/** Hueco entre dos rótulos del mismo lado: unos 4 px con la figura a 500 px. */
export const SITE_GAP = 4;
/**
 * Lo que un rótulo puede alejarse de su zona y seguir leyéndose junto a ella: unos 50 px con la
 * figura a 500 px, el alto de un rótulo de dos líneas a tamaño normal. Diseño de EMMA, sin fuente.
 */
export const MAX_SHIFT = 48;

interface Cluster {
  readonly items: SiteBox[];
  top: number;
}

/** Alto de un bloque de rótulos apilados, con sus huecos. */
function span(items: readonly SiteBox[]): number {
  return items.reduce((total, item) => total + item.height, 0) + SITE_GAP * (items.length - 1);
}

/** Desde el borde de arriba del bloque hasta el centro de cada rótulo. */
function offsets(items: readonly SiteBox[]): number[] {
  const found: number[] = [];
  let run = 0;
  for (const item of items) {
    found.push(run + item.height / 2);
    run += item.height + SITE_GAP;
  }
  return found;
}

/** El borde de arriba que deja cada rótulo lo más cerca de su zona, dentro de `0..canvas`. */
function bestTop(items: readonly SiteBox[], canvas: number): number {
  const from = offsets(items);
  const ideal = items.reduce((total, item, index) => total + item.anchor - (from[index] ?? 0), 0) / items.length;
  return Math.min(Math.max(ideal, 0), Math.max(canvas - span(items), 0));
}

function placeSide(boxes: readonly SiteBox[], canvas: number): Cluster[] {
  const clusters: Cluster[] = [...boxes]
    .sort((a, b) => a.anchor - b.anchor)
    .map((item) => ({ items: [item], top: bestTop([item], canvas) }));
  // Mientras dos bloques seguidos se pisen, se juntan y se recoloca el bloque entero.
  for (let index = 0; index + 1 < clusters.length; ) {
    const upper = clusters[index] as Cluster;
    const lower = clusters[index + 1] as Cluster;
    if (upper.top + span(upper.items) + SITE_GAP <= lower.top) {
      index += 1;
      continue;
    }
    const items = [...upper.items, ...lower.items];
    clusters.splice(index, 2, { items, top: bestTop(items, canvas) });
    // El bloque nuevo puede pisar ahora al de arriba: se vuelve a mirar desde él.
    index = Math.max(index - 1, 0);
  }
  return clusters;
}

/** Dónde va cada rótulo, o la lista si no caben junto a sus zonas. */
export function placeSites(boxes: readonly SiteBox[], canvas: number): SitePlacement {
  const centres: Record<string, number> = {};
  for (const side of ["left", "right"] as const) {
    for (const cluster of placeSide(boxes.filter((item) => item.side === side), canvas)) {
      if (span(cluster.items) > canvas) return { listed: true, centres: {} };
      const from = offsets(cluster.items);
      cluster.items.forEach((item, index) => {
        centres[item.key] = cluster.top + (from[index] ?? 0);
      });
    }
  }
  const far = boxes.some((item) => Math.abs((centres[item.key] ?? item.anchor) - item.anchor) > MAX_SHIFT);
  return far ? { listed: true, centres: {} } : { listed: false, centres };
}
