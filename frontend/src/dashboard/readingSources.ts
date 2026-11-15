/**
 * Que pictograma acompaña al nombre de la fuente que firmo una lectura (`icons/sets/sources.ts`).
 *
 * Las claves y los prefijos son los de `backend/app/analysis/data_quality.py` (`_SOURCE_LABELS`
 * y `_SOURCE_PREFIXES`), que es quien pone el nombre legible: aqui solo se elige el dibujo, y la
 * prueba lee ese fichero para que una fuente nueva del backend no se quede sin el. Se resuelve
 * en el mismo orden que alli (primero los prefijos, despues la clave exacta) para que nombre y
 * dibujo salgan siempre de la misma regla. Una fuente que la interfaz no conoce se enseña con el
 * nombre con que firmo y el dibujo de «desconocido» (`pictogramTable.ts`): no se le supone un canal.
 *
 * El simulador lleva la onda generada del entorno «simulado» (`lib/provenance.ts`): es el mismo
 * origen del dato, y un origen no tiene dos dibujos.
 */

import type { PictogramName } from "../icons/registry";
import { type PictogramTable, pictogramFor } from "./pictogramTable";

const SOURCES: PictogramTable = {
  "wearable-ble": "wristwatch",
  "apple-health": "phone-heart",
  "google-fit": "phone-pulse",
  manual: "pencil",
  "pvt-test": "tablet-dot",
  "crew-diary": "notebook",
  "console-pvt": "monitor-dot",
  "console-cognition": "monitor-grid",
  ultrasound: "probe-arcs",
  "pain-report": "sheet-bolt",
};

/** Prefijo → dibujo. Como en el backend, el prefijo solo cuenta si lleva algo detras. */
const PREFIXES: PictogramTable = {
  "simulator:": "wave-zigzag",
  "analitica:": "sheet-lines",
};

export function readingSourcePictogram(source: string): PictogramName | null {
  for (const [prefix, pictogram] of Object.entries(PREFIXES)) {
    if (source.startsWith(prefix) && source.length > prefix.length) return pictogram;
  }
  return pictogramFor(SOURCES, source);
}
