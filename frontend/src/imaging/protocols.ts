/**
 * Con qué dibujo se nombra cada protocolo ecográfico y cada medida (`app/imaging/protocols.py`,
 * `app/imaging/measure.py`).
 *
 * Por qué existe aparte de los paneles: el protocolo aparece en el selector, en la lista de
 * estudios, en los botones de fantoma y de ejemplo y en la tabla de Tierra; si cada sitio eligiera
 * su dibujo, el mismo protocolo saldría con cuatro. Aquí está una vez. Los protocolos que miden
 * un órgano del catálogo llevan el pictograma de la familia de su indicador: la vaina del nervio
 * óptico es el mismo nervio óptico que `onsd-*`. Un protocolo que el backend añada y esta tabla
 * no conozca se enseña con su nombre y la marca de «desconocido» (`UNKNOWN_MARK`), como un dominio
 * desconocido: la consola no se cae por un dibujo que falta.
 *
 * Nada de aquí redacta: la palabra es siempre el `display` del backend.
 */

import type { PictogramName } from "../icons/registry";
import { hasIndicatorFamily, indicatorFamily } from "../lib/indicatorFamily";
import { UNKNOWN_MARK } from "../lib/marks";

/** Clave del protocolo → dibujo. Las claves son las de `PROTOCOLS` del backend. */
export const PROTOCOL_PICTOGRAMS: Readonly<Record<string, PictogramName>> = {
  "optic-nerve": "eye-nerve",
  "jugular-vein": "vessel-flow",
  bladder: "bladder",
  lung: "lungs",
  // Cuatro ventanas (hepatorrenal, esplenorrenal, pélvica, pericárdica): la ventana en cuartos.
  fast: "circle-quartered",
  liver: "liver",
};

export function protocolPictogram(key: string): PictogramName | null {
  return PROTOCOL_PICTOGRAMS[key] ?? UNKNOWN_MARK.pictogram;
}

/**
 * El dibujo de una medida es el de la familia del indicador en que entra. Una medida con lado
 * (`lateral`) entra como `<nombre>-right` o `<nombre>-left`, ambos de la misma familia; se mira el
 * derecho. Sin familia conocida, la marca de «desconocido».
 */
export function measurePictogram(spec: { name: string; lateral: boolean }): PictogramName | null {
  const key = spec.lateral ? `${spec.name}-right` : spec.name;
  return hasIndicatorFamily(key) ? indicatorFamily(key) : UNKNOWN_MARK.pictogram;
}
