/**
 * De qué clase es cada asiento del registro firmado, para ponerle un pictograma junto a su tipo.
 *
 * Por qué existe: el ledger tiene una treintena de tipos de asiento (`app/core/storage.py`,
 * `app/core/ledger.py`) y la tabla de auditoría de Tierra los enseña por su nombre de la API
 * (`vital-observation`, `alert-acknowledgement`…). Treinta dibujos no se aprenden; diez sí: una
 * lectura, una alerta, una decisión firmada por una persona, una contramedida, un evento del plan,
 * una proyección fotografiada, el hábitat, una imagen, un informe y el propio sistema. El tipo
 * sigue escrito al lado, tal cual: el pictograma agrupa, no sustituye.
 *
 * Qué va en cada grupo lo decide la naturaleza del asiento, no quién lo firma: una fase de
 * contraste, un vínculo de sensor o un perfil de tripulante son declaraciones de una persona
 * sobre algo, y van con el lápiz; el estado de un sistema del hábitat también lo declara una
 * persona, pero habla del hábitat, y va con la casa. `ledgerEntries.test.ts` lee los dos ficheros
 * de Python y exige que cada tipo esté en un grupo, y que ningún grupo nombre un tipo que el
 * backend no tiene. Un tipo que llegue sin grupo se enseña con su nombre y la marca de
 * «desconocido», sin tumbar la tabla.
 */

import type { PictogramName } from "../icons/registry";
import { type StateMark, UNKNOWN_MARK, mark } from "../lib/marks";

export const ENTRY_GROUPS = {
  // Una lectura, o su enmienda: la corrección es una lectura más, enlazada a la anterior.
  "dot-filled": ["vital-observation", "amendment"],
  // Las alertas, y la petición de ayuda urgente de a bordo con su cierre (2026-11-14): un aviso que
  // pide atención, aunque no salga del análisis.
  "bell": [
    "alert-acknowledgement",
    "alert-resolution",
    "alert-dismissal",
    "alert-annunciation",
    "help-request",
    "help-request-close",
  ],
  "pen": [
    "hypothesis-review",
    "draft-signoff",
    "draft-countersign",
    "lab-confirmation",
    "volume-contrast-phase",
    "crew-profile",
    "crew-mission-history",
    "crew-identity",
    // El sexo que declara el tripulante (lote «ciclo», 2026-11-14): aparte del perfil y de la identidad.
    "crew-sex",
    "sensor-binding",
    "location-anchor",
    // Lo que una persona en Tierra dice a la tripulación (§5.38.1).
    "ground-note",
  ],
  "clipboard": ["countermeasure-followup"],
  // El plan: los eventos de la misión y las transacciones del planificador de la casa (Marplanner,
  // cuya base es el ledger, 2026-11-12).
  "calendar": ["mission-event", "planner-changeset"],
  // La misma cámara que la «instantánea firmada» de las proyecciones comprobadas: es el mismo asiento.
  "camera": ["prediction-snapshot"],
  // El inventario contado y el abastecimiento declarado (2026-11-14) hablan de la nave, como los
  // recursos de a bordo.
  "house": [
    "habitat-reading",
    "system-status",
    "resource-availability",
    "inventory-count",
    "inventory-resupply",
    "location-sightings",
  ],
  "picture": ["imaging-study", "imaging-measurement", "imaging-findings", "volume-study", "volume-segmentation"],
  "sheet-lines": ["scanned-report", "draft-interpretation", "pain-report"],
  // El propio sistema: qué corta la red, qué medidas se esperan (nivel de misión), qué entorno
  // se describe (entorno de la misión), el enlace con Tierra simulado (§5.47) y la discrepancia
  // del cálculo local de efemérides con JPL Horizons que firma el sistema (2026-11-11).
  "gear": ["safe-mode", "mission-mode", "mission-profile", "simulated-link", "ephemeris-discrepancy", "redaction"],
} as const satisfies Partial<Record<PictogramName, readonly string[]>>;

const BY_TYPE: ReadonlyMap<string, PictogramName> = new Map(
  (Object.entries(ENTRY_GROUPS) as [PictogramName, readonly string[]][]).flatMap(([pictogram, types]) =>
    types.map((type): [string, PictogramName] => [type, pictogram]),
  ),
);

/** Todos los tipos de asiento que la interfaz conoce, para cotejarlos con el backend. */
export function knownEntryTypes(): readonly string[] {
  return [...BY_TYPE.keys()];
}

/** La marca de un tipo de asiento: su grupo, sin color (un asiento no es una alerta); desconocido, el punto. */
export function entryMark(type: string): StateMark {
  const pictogram = BY_TYPE.get(type);
  return pictogram === undefined ? UNKNOWN_MARK : mark(pictogram, null);
}
