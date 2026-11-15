import type { ContrastPhaseDeclaration, VolumeSegmentation, VolumeStudy } from "../lib/api";

/**
 * Con que segmentacion anterior se puede comparar una dada.
 *
 * Por que existe aparte del panel: el backend rechaza (409) comparar dos presets o dos
 * segmentadores distintos, porque la "evolucion" mediria el cambio de modelo y no el de la lesion.
 * La interfaz no debe ofrecer un boton que acabe en ese rechazo, y la regla merece su prueba.
 * Los estudios que llegan aqui ya son de un solo tripulante: la lista se pide por sujeto.
 *
 * "Anterior" es la mas reciente de las registradas antes (indice de ledger menor): el ledger es
 * el unico orden que EMMA firma. Si ninguna de las dos tiene lesiones candidatas no hay nada que
 * emparejar y no se ofrece.
 */
export function previousSegmentation(
  studies: readonly VolumeStudy[],
  current: VolumeSegmentation,
): VolumeSegmentation | null {
  const earlier = studies
    .flatMap((study) => study.segmentations)
    .filter(
      (item) =>
        item.ledger_index < current.ledger_index &&
        item.preset === current.preset &&
        item.segmentador === current.segmentador &&
        (item.lesiones.length > 0 || current.lesiones.length > 0),
    );
  return earlier.reduce<VolumeSegmentation | null>(
    (best, item) => (best === null || item.ledger_index > best.ledger_index ? item : best),
    null,
  );
}

/**
 * Densidad (HU) de una lesion candidata o del parenquima de referencia, como la da el backend
 * (`volumes/geometry.py`). Los tipos viven aqui y no en `lib/api.ts` porque solo los lee la
 * comparacion; el backend los sirve tambien en cada segmentacion de `GET /api/volumes`.
 */
export interface HuDensity {
  valorable: boolean;
  voxeles: number;
  mediana_hu: number | null;
  media_hu: number | null;
  desviacion_hu: number | null;
  p10_hu: number | null;
  p90_hu: number | null;
  /** Por que no se da cifra, redactado por el backend. */
  motivo: string | null;
}

/** Lo que una segmentacion dice de la densidad de sus lesiones: unidad, minimo, referencia, notas. */
export interface DensityBlock {
  disponible: boolean;
  motivo: string | null;
  /** UCUM; se muestra por `displayUnit`. */
  unidad: string;
  minimo_voxeles: number;
  /** La palabra del backend para una lesion con menos voxeles que el minimo. */
  no_valorable: string;
  referencia: (HuDensity & { nombre: string }) | null;
  /** La fase que una persona declaro del estudio; `null` si nadie la ha declarado. */
  fase_contraste?: ContrastPhaseDeclaration | null;
  notas: string[];
}

export type DensitySides = { antes: DensityBlock | null; despues: DensityBlock | null };

/**
 * Que se ensena en una celda de densidad. Tres casos que no se pueden confundir (F.5-1): no hay
 * dato (la lesion no tiene pareja, o la segmentacion no da densidad), hay dato pero no es
 * valorable (pocos voxeles: el backend dice por que), o hay cifra.
 */
export type DensityCell =
  | { kind: "ausente" }
  | { kind: "no-valorable"; voxeles: number; motivo: string | null }
  | { kind: "cifra"; mediana: number; p10: number; p90: number; voxeles: number };

/** La densidad de una fila de la comparacion (lesion, lesion previa o no reencontrada), si viene. */
export function densityOf(row: object | null | undefined): HuDensity | null {
  if (row === null || row === undefined) return null;
  return (row as { densidad?: HuDensity | null }).densidad ?? null;
}

export function densityCell(density: HuDensity | null): DensityCell {
  if (density === null) return { kind: "ausente" };
  const { mediana_hu: mediana, p10_hu: p10, p90_hu: p90, voxeles } = density;
  // `valorable` manda: una cifra que el backend declara no valorable no se ensena aunque venga.
  if (!density.valorable || mediana === null || p10 === null || p90 === null) {
    return { kind: "no-valorable", voxeles, motivo: density.motivo };
  }
  return { kind: "cifra", mediana, p10, p90, voxeles };
}

/** Los dos bloques de densidad de una comparacion; `null` si el backend no los da. */
export function densitySides(comparison: object): DensitySides | null {
  const sides = (comparison as { densidad?: Partial<DensitySides> | null }).densidad;
  if (sides === null || sides === undefined) return null;
  const antes = sides.antes ?? null;
  const despues = sides.despues ?? null;
  return antes === null && despues === null ? null : { antes, despues };
}

/**
 * Lo que el backend dice junto a las cifras (que describen, que la fase de contraste no esta
 * declarada, por que un estudio no tiene densidad), sin repetir lo que dicen los dos estudios.
 * No se redacta nada aqui: son sus textos, en su orden.
 */
export function densityNotes(sides: DensitySides): string[] {
  const said: string[] = [];
  for (const block of [sides.antes, sides.despues]) {
    if (block === null) continue;
    for (const text of [block.motivo, ...block.notas]) {
      if (text !== null && text !== "" && !said.includes(text)) said.push(text);
    }
  }
  return said;
}

/** La unidad de las cifras: la del estudio posterior, o la del anterior si aquel no la da. */
export function densityUnit(sides: DensitySides): string | null {
  return (sides.despues ?? sides.antes)?.unidad ?? null;
}
