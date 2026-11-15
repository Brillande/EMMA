/**
 * Lo que la vista «Qué se comparte y qué no» decide sin navegador: en qué orden van los destinos y
 * qué marca lleva cada grado. El texto, todo, lo da el backend (`GET /api/sharing`).
 *
 * Las marcas: lo que impone el código lleva la de visto, sin color (`OK_MARK`); lo que solo impone
 * en parte o no impone lleva la de un estado cuyo significado dice la palabra del backend
 * (`UNKNOWN_MARK`), sin color propio. No es una alarma ni un dato ausente: no va en amarillo ni en
 * cian (tabla F.5-1), y la palabra al lado es la que dice cuánto se puede fiar uno de la fila.
 */

import type { Sharing, SharingDestination, SharingItem } from "../lib/api";
import { OK_MARK, type StateMark, UNKNOWN_MARK } from "../lib/marks";

export function enforcementMark(enforcement: SharingItem["enforcement"]): StateMark {
  return enforcement === "code" ? OK_MARK : UNKNOWN_MARK;
}

export interface SharingGroup {
  id: SharingDestination;
  label: string;
  items: SharingItem[];
}

/**
 * Las filas agrupadas por destino, en el orden en que el backend da los destinos. Un destino sin
 * filas no sale, salvo internet (lleva sus propósitos) y Tierra (lleva las rutas con corte).
 */
export function itemsByDestination(body: Sharing): SharingGroup[] {
  return body.destinations
    .map((destination) => ({
      id: destination.id,
      label: destination.label,
      items: body.items.filter((item) => item.destination === destination.id),
    }))
    .filter((group) => group.items.length > 0 || group.id === "internet" || group.id === "ground");
}
