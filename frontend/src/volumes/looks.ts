// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Cómo se pinta cada estructura segmentada, en un solo sitio para el visor completo
 * (`VolumeViewer`, NiiVue) y la vista previa ligera de «Distancia y nodos» (`SegmentationPreview`,
 * three.js): el mismo hígado se ve igual en los dos. Colores anatómicos de `palette.ts`: contenido de
 * imagen, no señales (solo dentro de lienzos 3D, lo vigila `palette.test.ts`).
 *
 * Sacado tal cual de `VolumeViewer.tsx` (2026-11-14), que lo portó de Polaris
 * (github.com/BeyondTheProtocol/polaris @ 7bf47257, `tools/visor3d_web/main.js`, AGPL-3.0-or-later,
 * (c) 2026 la autora de Polaris, «Beyond the Protocol»); los cambios §5a son los que ese fichero
 * declara (tokens `anatomy`, cava y vesícula translúcidas, preset de ojos).
 */
import { anatomy } from "../lib/palette";

export function rgb(hex: string): [number, number, number] {
  const n = Number.parseInt(hex.slice(1), 16);
  return [n >> 16, (n >> 8) & 255, n & 255];
}

/** Como se pinta cada estructura: color anatomico, opacidad en 3D y tinte en los cortes. */
export interface Look {
  color: [number, number, number];
  opacity: number; // 1 = opaca; < 1 = translucida, se carga al final (orden de transparencia)
  sliceAlpha: number; // tinte en los cortes; 0 = el TAC ya lo ensena
}

// De Polaris `visor3d_web/main.js`: el organo translucido a 0,22 y cargado el ultimo, vasos con
// alfa 200, porta opaca. Cava y vesicula no las pintaba en 3D; aqui van translucidas para no
// tapar el higado. En el preset de ojos, ambos globos son el organo translucido (antes solo el
// de la etiqueta 1 lo era, y un ojo salia opaco y el otro no).
const LOOKS: Record<string, Look> = {
  higado: { color: rgb(anatomy.organ), opacity: 0.22, sliceAlpha: 0 },
  vasos: { color: rgb(anatomy.vessels), opacity: 200 / 255, sliceAlpha: 120 },
  porta: { color: rgb(anatomy.portal), opacity: 1, sliceAlpha: 120 },
  vci: { color: rgb(anatomy.cava), opacity: 0.35, sliceAlpha: 90 },
  vesicula: { color: rgb(anatomy.gallbladder), opacity: 0.35, sliceAlpha: 90 },
  ojo_der: { color: rgb(anatomy.organ), opacity: 0.3, sliceAlpha: 0 },
  ojo_izq: { color: rgb(anatomy.organ), opacity: 0.3, sliceAlpha: 0 },
  cristalino_der: { color: rgb(anatomy.lens), opacity: 1, sliceAlpha: 120 },
  cristalino_izq: { color: rgb(anatomy.lens), opacity: 1, sliceAlpha: 120 },
  nervio_der: { color: rgb(anatomy.nerve), opacity: 1, sliceAlpha: 120 },
  nervio_izq: { color: rgb(anatomy.nerve), opacity: 1, sliceAlpha: 120 },
};
const FALLBACK: Look = { color: rgb(anatomy.bone), opacity: 1, sliceAlpha: 100 };
export const look = (key: string): Look => LOOKS[key] ?? FALLBACK;
