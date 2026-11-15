/**
 * Que ensena el panel de calidad del dato del aviso de «sensor vinculado a otro tripulante».
 *
 * Por que existe: ese aviso solo salia en la respuesta de la ingesta, y quien abria la consola
 * despues veia esas lecturas como las demas. Ahora el backend lo compone sobre las lecturas ya
 * firmadas (`ingest/bindings.py`, `data.quality.device_bindings`) y aqui solo se decide con que
 * senal se pinta. Las frases son suyas: la interfaz no redacta.
 *
 * Reglas, con prueba:
 *
 * - NO es un nivel de salud. Es un aviso sobre el dato, asi que lleva la misma senal que una
 *   lectura de baja confianza (triangulo y amarillo, `lib/provenance.ts`), nunca la de una alerta.
 * - Sin vinculos declarados no se pinta nada: es el caso normal y no es un fallo.
 * - Con vinculos y ninguna lectura senalada, la frase tranquila del backend va en secundario,
 *   sin senal.
 * - Un tipo de aviso que la interfaz no conoce falla: no se pinta como si no pasara nada.
 */

import type { DeviceBindingsNotice } from "../lib/api";
import { type QualityStyle, qualityStyle } from "../lib/provenance";

export interface DeviceBindingsView {
  /** La frase del backend, tal cual. */
  text: string;
  /** Lo que el backend anade sobre el identificador abreviado, si lo anade. */
  note: string | null;
  /** La senal de «baja confianza» si hay algo que mirar; `null` si es solo informativo. */
  style: QualityStyle | null;
}

const NOTHING: Record<DeviceBindingsNotice["kind"], boolean> = {
  none: true,
  "bound-to-other-crew": false,
  "not-checked": false,
};

/** Lo que se pinta, o `null` si no hay nada que decir. */
export function deviceBindingsView(notice: DeviceBindingsNotice): DeviceBindingsView | null {
  if (!(notice.kind in NOTHING)) throw new Error(`aviso de vínculo desconocido: ${notice.kind}`);
  if (notice.text === null) return null;
  return {
    text: notice.text,
    note: notice.device_note,
    style: NOTHING[notice.kind] ? null : qualityStyle("low"),
  };
}
