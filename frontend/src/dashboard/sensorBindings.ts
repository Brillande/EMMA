/**
 * Lo poco que el panel decide por si mismo del vinculo sensor-tripulante: que filas ensena
 * primero, cuando se puede firmar y que se manda al firmar.
 *
 * Por que existe: EMMA no comprueba quien lleva puesto un dispositivo; lo declara una persona y
 * el backend lo entrega con su rotulo y sus frases (`ingest/bindings.py`). La interfaz no
 * redacta nada de eso. Lo que si hace tiene reglas que merecen prueba:
 *
 * - Un vinculo de OTRO tripulante no es un problema del que se mira: se ensena, sin color ni
 *   marca de aviso. El aviso lo escribe el backend: en la respuesta de la ingesta y, sobre las
 *   lecturas ya firmadas, en la calidad del dato del estado (`deviceBindings.ts`).
 * - Retirar un vinculo es otra declaracion, con la misma fuente y el mismo identificador que la
 *   fila que se retira, y sin tripulante. No hay borrar.
 * - El identificador solo viaja si se escribio uno: sin el, el vinculo es de la fuente entera,
 *   y eso lo explica el backend (`caveat`).
 */

import type { SensorBinding, SensorBindings } from "../lib/api";

export interface BindingRow {
  /** Clave estable para React: fuente e identificador (o la fuente entera). */
  key: string;
  binding: SensorBinding;
  /** Es del tripulante que se esta mirando. */
  own: boolean;
}

/** Los vinculos vigentes: primero los del tripulante que se mira, despues los demas. */
export function bindingRows(
  overview: Pick<SensorBindings, "bindings">,
  subject: string,
): BindingRow[] {
  const rows = overview.bindings.map((binding) => ({
    key: `${binding.source}:${binding.device ?? ""}`,
    binding,
    own: binding.crew === subject,
  }));
  return [...rows.filter((row) => row.own), ...rows.filter((row) => !row.own)];
}

export interface BindingForm {
  source: string;
  /** "" = sin identificador: la fuente entera. */
  device: string;
  note: string;
}

export const EMPTY_FORM: BindingForm = { source: "", device: "", note: "" };

/** Se puede firmar con una fuente y el nombre de quien declara. Lo demas es opcional. */
export function canBind(form: BindingForm, operator: string | undefined): boolean {
  return form.source !== "" && (operator ?? "").trim() !== "";
}

export interface BindingBody {
  source: string;
  device?: string;
  action: "bind" | "unbind";
  crew?: string;
  since: string;
  note: string;
  declared_by: string;
}

/** El cuerpo que vincula un dispositivo al tripulante que se mira. */
export function bindBody(
  form: BindingForm,
  subject: string,
  operator: string,
  since: string,
): BindingBody {
  const device = form.device.trim();
  return {
    source: form.source,
    ...(device === "" ? {} : { device }),
    action: "bind",
    crew: subject,
    since,
    note: form.note.trim(),
    declared_by: operator.trim(),
  };
}

/** El cuerpo que retira un vinculo vigente: el mismo dispositivo, y nadie. */
export function unbindBody(binding: SensorBinding, operator: string, since: string): BindingBody {
  return {
    source: binding.source,
    ...(binding.device === null ? {} : { device: binding.device }),
    action: "unbind",
    since,
    note: "",
    declared_by: operator.trim(),
  };
}

/**
 * El instante desde el que vale la declaracion: el de los datos si lo hay, porque una mision
 * simulada no vive en el reloj del ordenador; si no, ahora.
 */
export function bindingInstant(referenceTime: string | null, now: Date): string {
  return referenceTime ?? now.toISOString();
}
