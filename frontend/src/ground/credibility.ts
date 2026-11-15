/**
 * La credibilidad de cada cifra INFERIDA o PREDICHA, ordenada para leerla.
 *
 * Por qué existe aparte de la vista: lo que aquí se puede equivocar es lógica. Una casilla que se
 * perdiera por traer un grupo que la interfaz no conoce dejaría un factor callado, que es justo
 * lo que la ficha del backend prohíbe (`app/evidence/credibility.py`: los once factores, todos).
 * Está en un `.ts` para que lo pruebe `credibility.test.ts`.
 *
 * Nada de aquí redacta ni puntúa: el estado de cada factor, su nombre y los grupos son los de
 * `GET /api/framework` → `credibility`. La norma (NASA-STD-7009B) puntúa cada factor con tablas
 * de nivel que EMMA no ha aplicado, así que aquí no hay color ni dibujo de nivel: solo se agrupa.
 */

import type { PictogramName } from "../icons/registry";
import type { Credibility, CredibilityLayer, CredibilityState } from "../lib/api";
import { UNKNOWN_PICTOGRAM } from "../lib/marks";
import { OBSERVATION_TYPES, type ObservationType } from "../lib/provenance";

export interface FactorGroup {
  id: string;
  /** Nombre del grupo tal como lo da el backend; `null` si el grupo no viene declarado. */
  name: string | null;
  rows: CredibilityState[];
}

/**
 * Los factores de una capa por grupo, en el orden de los grupos del backend. Un factor de un
 * grupo que no está declarado no se pierde: va después, en su propio grupo, con su clave.
 */
export function factorGroups(credibility: Credibility, layer: CredibilityLayer): FactorGroup[] {
  const groups: FactorGroup[] = credibility.groups.map((group) => ({
    id: group.id,
    name: group.name_es,
    rows: [],
  }));
  for (const item of layer.factors) {
    let group = groups.find((candidate) => candidate.id === item.group);
    if (group === undefined) {
      group = { id: item.group, name: null, rows: [] };
      groups.push(group);
    }
    group.rows.push(item);
  }
  return groups.filter((group) => group.rows.length > 0);
}

export interface LayerSign {
  pictogram: PictogramName;
  /** La palabra del backend (`observation_type_text`). */
  word: string;
  /** Qué significa el tipo, para el `title`; `null` si la interfaz no lo conoce. */
  meaning: string | null;
}

/**
 * El signo de una ficha: el pictograma de su tipo (`lib/provenance.ts`), el mismo que lleva la
 * cifra donde se enseña, con la palabra que da el backend. Un tipo que la interfaz no conoce lleva
 * el dibujo de «desconocido» y su palabra, sin significado: no se pinta como uno conocido, y una
 * ficha nueva no tumba el panel entero del marco.
 */
export function layerSign(layer: CredibilityLayer): LayerSign {
  // `Object.hasOwn` y no `in`: «toString» no es un tipo aunque lo herede el objeto.
  const known = Object.hasOwn(OBSERVATION_TYPES, layer.observation_type)
    ? OBSERVATION_TYPES[layer.observation_type as ObservationType]
    : null;
  return {
    pictogram: known?.pictogram ?? UNKNOWN_PICTOGRAM,
    word: layer.observation_type_text,
    meaning: known?.meaning ?? null,
  };
}
