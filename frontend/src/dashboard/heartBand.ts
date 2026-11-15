/**
 * Lo puro de la banda de pulso por Bluetooth (`HeartBandPanel.tsx`), aparte para probarlo.
 *
 * Por qué existe: el backend ya ingería tramas GATT Heart Rate Measurement (`POST
 * /api/wearable/ble`, `ingest/wearable.py`), pero nada de la consola las leía de una banda: no
 * había forma de conectar una (visto con una COOSPO HW9, 2026-11-12). La trama viaja ENTERA al
 * backend, que es quien la interpreta y la firma; aquí solo se pasa a hexadecimal y se leen sus
 * campos para enseñar que llegan, sin juzgarlos.
 */

/** Servicio y característica estándar del perfil de pulso (Bluetooth SIG). */
export const HEART_RATE_SERVICE = "heart_rate";
export const HEART_RATE_MEASUREMENT = "heart_rate_measurement";

/**
 * El tripulante para quien se firman las lecturas de la banda, sea cual sea el que se mira.
 *
 * Decisión del usuario (2026-11-13): un tripulante real aparte de los simulados, para que lo
 * simulado y lo real no se mezclen. Firmadas para el tripulante simulado que se estaba mirando,
 * las lecturas de la banda llevaban la hora real (2026-11-13) y quedaban «en el pasado» de una
 * simulación que ya iba por diciembre: se registraban, pero ningún gráfico las enseñaba.
 */
export const BAND_SUBJECT = "real-01";

/** Lo que la banda dice del contacto con la piel (bits 1-2 de las banderas). */
export type SensorContact = "detected" | "not_detected" | "unsupported";

/** Todo lo que trae una trama Heart Rate Measurement, en unidades de lectura. */
export interface FrameFields {
  heartRate: number;
  /** Intervalos R-R en milisegundos (la trama los da en 1/1024 s), en el orden en que llegan. */
  rrMs: number[];
  contact: SensorContact;
  /** Energía gastada acumulada en kJ, si la banda la manda en esta trama. */
  energyKj: number | null;
}

/**
 * Descodifica la trama según la especificación Heart Rate Measurement del Bluetooth SIG: bit 0,
 * pulso en uint16 (si no, uint8); bit 2, la banda informa del contacto, y bit 1, lo hay; bit 3,
 * sigue la energía gastada (uint16, kJ); bit 4, siguen intervalos R-R (uint16 cada uno, 1/1024 s).
 * `null` si la trama es más corta de lo que sus banderas anuncian: mejor nada que una cifra leída
 * de bytes que no son suyos. Solo es para enseñar que llega; el registro lo descodifica el backend.
 */
export function frameFields(view: DataView): FrameFields | null {
  if (view.byteLength < 2) return null;
  const flags = view.getUint8(0);
  let offset = 1;
  let heartRate: number;
  if ((flags & 0x01) !== 0) {
    if (view.byteLength < offset + 2) return null;
    heartRate = view.getUint16(offset, true);
    offset += 2;
  } else {
    heartRate = view.getUint8(offset);
    offset += 1;
  }
  const contact: SensorContact =
    (flags & 0x04) === 0 ? "unsupported" : (flags & 0x02) !== 0 ? "detected" : "not_detected";
  let energyKj: number | null = null;
  if ((flags & 0x08) !== 0) {
    if (view.byteLength < offset + 2) return null;
    energyKj = view.getUint16(offset, true);
    offset += 2;
  }
  const rrMs: number[] = [];
  if ((flags & 0x10) !== 0) {
    // Un byte suelto al final no es un intervalo: se ignora.
    for (; offset + 2 <= view.byteLength; offset += 2) rrMs.push((view.getUint16(offset, true) * 1000) / 1024);
  }
  return { heartRate, rrMs, contact, energyKj };
}

export function frameHex(view: DataView): string {
  let out = "";
  for (let i = 0; i < view.byteLength; i += 1) out += view.getUint8(i).toString(16).padStart(2, "0");
  return out;
}

/** La variabilidad que el backend calcula con los R-R ya registrados. */
export interface BandHrv {
  rmssdMs: number;
  sdnnMs: number;
}

/** Lo que cuenta la respuesta de `POST /api/wearable/ble`, con lo que falte en `null`. */
export interface BandReply {
  /** Cuántas observaciones firmó; `null` si la respuesta no lo dice. */
  recorded: number | null;
  /** La trama tal como la leyó el backend. */
  frame: FrameFields | null;
  hrv: BandHrv | null;
}

const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

/**
 * Lee la respuesta de la ingesta sin fiarse de su forma: un backend anterior no trae `frame` ni
 * `hrv`, y entonces el panel se queda con lo que descodificó él mismo, sin romperse.
 */
export function bandReply(body: unknown): BandReply {
  const root = (typeof body === "object" && body !== null ? body : {}) as Record<string, unknown>;
  const recorded = Array.isArray(root.recorded) ? root.recorded.length : null;
  let frame: FrameFields | null = null;
  const rawFrame = root.frame as Record<string, unknown> | null | undefined;
  if (typeof rawFrame === "object" && rawFrame !== null && finite(rawFrame.heart_rate)) {
    const contact = rawFrame.sensor_contact;
    frame = {
      heartRate: rawFrame.heart_rate,
      rrMs: Array.isArray(rawFrame.rr_ms) ? rawFrame.rr_ms.filter(finite) : [],
      contact: contact === "detected" || contact === "not_detected" ? contact : "unsupported",
      energyKj: finite(rawFrame.energy_kj) ? rawFrame.energy_kj : null,
    };
  }
  const rawHrv = root.hrv as Record<string, unknown> | null | undefined;
  const hrv =
    typeof rawHrv === "object" && rawHrv !== null && finite(rawHrv.rmssd_ms) && finite(rawHrv.sdnn_ms)
      ? { rmssdMs: rawHrv.rmssd_ms, sdnnMs: rawHrv.sdnn_ms }
      : null;
  return { recorded, frame, hrv };
}

/**
 * El identificador con que se firma la lectura, con la forma que acepta el backend
 * (`bindings.device_key`: minúsculas, cifras y `: . _ -`, hasta 64). Una banda se anuncia con
 * nombres como «HW9 012345»; sin nombre, se usa el identificador que da el navegador.
 */
export function deviceKey(name: string | undefined, id: string): string {
  const raw = (name && name.trim() !== "" ? name : id)
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9:._-]+/g, "-")
    .replace(/^[^a-z0-9]+/, "");
  return (raw === "" ? "banda" : raw).slice(0, 64);
}
