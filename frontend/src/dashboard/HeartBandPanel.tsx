import { useEffect, useSyncExternalStore } from "react";

import { Command } from "../components/Command";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { ApiError, withConsoleHeader } from "../lib/api";
import { formatNumber } from "../lib/format";
import {
  LOADING_MARK,
  OK_MARK,
  type RequestOutcome,
  UNAVAILABLE_MARK,
  requestOutcome,
} from "../lib/marks";
import {
  BAND_SUBJECT,
  type BandHrv,
  type BandReply,
  type FrameFields,
  HEART_RATE_MEASUREMENT,
  HEART_RATE_SERVICE,
  type SensorContact,
  bandReply,
  deviceKey,
  frameFields,
  frameHex,
} from "./heartBand";

/**
 * Conectar una banda de pulso por Bluetooth y mandar sus lecturas al registro firmado.
 *
 * Por qué existe: petición del usuario (2026-11-12, «cómo conecto mi banda de frecuencia», una
 * COOSPO HW9). El backend ya sabía ingerir la trama estándar Heart Rate Measurement (`POST
 * /api/wearable/ble`), pero ninguna pantalla la leía de una banda. Vale cualquier banda que
 * anuncie el servicio de pulso estándar del Bluetooth SIG.
 *
 * Cada trama que notifica la banda va entera al backend, que la interpreta (pulso e intervalos
 * R-R) y la firma como `wearable-ble` para el tripulante real `BAND_SUBJECT`, aparte de los
 * simulados (decisión del usuario, 2026-11-13: firmadas para el simulado que se miraba, quedaban
 * antes del final de su simulación y ningún gráfico las enseñaba). Con la primera lectura firmada
 * la consola pasa a ese tripulante, que hasta entonces no existe en la lista.
 *
 * Aquí se enseña todo lo que da la banda (pulso, último R-R, contacto, energía) y la variabilidad
 * que calcula el backend, sin color ni umbral: el juicio es del análisis, no de este panel. Sin
 * Bluetooth en el navegador o en el equipo, se dice.
 */

interface Connected {
  kind: "connected";
  name: string;
  /** La última trama, descodificada aquí o, si aquí no se pudo, la que leyó el backend. */
  fields: FrameFields | null;
  /** El último R-R recibido: muchas tramas no traen ninguno y no por eso desaparece. */
  lastRrMs: number | null;
  /** La última variabilidad que dio el backend. */
  hrv: BandHrv | null;
  recorded: number;
  failed: number;
}

type BandState =
  | { kind: "idle" }
  | { kind: "connecting" }
  | Connected
  | { kind: "failed"; outcome: RequestOutcome }
  | { kind: "notFound"; quick: boolean };

/** Una cancelación más rápida que esto no es una búsqueda: es que no hay radio Bluetooth. */
const QUICK_CANCEL_MS = 1_500;

/**
 * Cuánto sigue conectada la banda sin ningún panel montado. Al pasar la consola a `BAND_SUBJECT`
 * la consola entera se desmonta mientras carga el nuevo tripulante y vuelve a montarse: soltar la
 * banda ahí la desconectaría justo tras su primera lectura. Pasado este margen sin panel, nadie la
 * está mirando y se suelta, como antes al salir del panel.
 */
const RELEASE_MS = 30_000;

// La conexión vive fuera del componente para sobrevivir a ese desmontaje.
let band: BandState = { kind: "idle" };
let device: BluetoothDevice | null = null;
/** Cada conexión su número: una respuesta tardía de la anterior no toca la actual. */
let connection = 0;
let mountedPanels = 0;
let release: ReturnType<typeof setTimeout> | null = null;
/** Cambiar el tripulante que se mira; lo pone el panel montado. */
let chooseSubject: ((subject: string) => void) | null = null;
const listeners = new Set<() => void>();

function setBand(next: BandState | ((current: BandState) => BandState)): void {
  band = typeof next === "function" ? next(band) : next;
  listeners.forEach((listener) => listener());
}

function updateConnected(id: number, update: (current: Connected) => Connected): void {
  if (id !== connection) return;
  setBand((current) => (current.kind === "connected" ? update(current) : current));
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function releaseBand(): void {
  connection += 1;
  const held = device;
  device = null;
  held?.gatt?.disconnect();
  setBand({ kind: "idle" });
}

async function sendFrame(frame: string, device: string): Promise<BandReply> {
  const response = await fetch(
    "/api/wearable/ble",
    withConsoleHeader({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frame_hex: frame, subject: BAND_SUBJECT, device }),
    }),
  );
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // cuerpo no JSON
    }
    throw new ApiError(response.status, detail);
  }
  try {
    return bandReply(await response.json());
  } catch {
    // Firmada, aunque la respuesta no se pueda leer.
    return bandReply(null);
  }
}

async function connectBand(bluetooth: Bluetooth): Promise<void> {
  setBand({ kind: "connecting" });
  const started = Date.now();
  const id = (connection += 1);
  let chosen: BluetoothDevice | null = null;
  try {
    chosen = await bluetooth.requestDevice({ filters: [{ services: [HEART_RATE_SERVICE] }] });
    const server = await chosen.gatt!.connect();
    const service = await server.getPrimaryService(HEART_RATE_SERVICE);
    const measurement = await service.getCharacteristic(HEART_RATE_MEASUREMENT);
    if (id !== connection) {
      // Se soltó mientras se conectaba.
      chosen.gatt?.disconnect();
      return;
    }
    const key = deviceKey(chosen.name, chosen.id);
    const own = chosen;
    device = own;
    setBand({
      kind: "connected",
      name: chosen.name ?? "banda",
      fields: null,
      lastRrMs: null,
      hrv: null,
      recorded: 0,
      failed: 0,
    });
    // La consola pasa al tripulante de la banda una sola vez por conexión, y solo cuando ya tiene
    // una lectura firmada: antes no existe en la lista de tripulantes.
    let switched = false;
    measurement.addEventListener("characteristicvaluechanged", () => {
      const value = measurement.value;
      if (value === undefined || id !== connection) return;
      const fields = frameFields(value);
      if (fields !== null) {
        updateConnected(id, (s) => ({ ...s, fields, lastRrMs: fields.rrMs.at(-1) ?? s.lastRrMs }));
      }
      sendFrame(frameHex(value), key).then(
        (reply) => {
          updateConnected(id, (s) => ({
            ...s,
            fields: fields ?? reply.frame ?? s.fields,
            lastRrMs: fields === null ? (reply.frame?.rrMs.at(-1) ?? s.lastRrMs) : s.lastRrMs,
            hrv: reply.hrv ?? s.hrv,
            recorded: s.recorded + 1,
          }));
          if (!switched && id === connection && reply.recorded !== 0) {
            switched = true;
            chooseSubject?.(BAND_SUBJECT);
          }
        },
        () => updateConnected(id, (s) => ({ ...s, failed: s.failed + 1 })),
      );
    });
    own.addEventListener("gattserverdisconnected", () => {
      if (device !== own) return;
      device = null;
      connection += 1;
      setBand({ kind: "idle" });
    });
    await measurement.startNotifications();
  } catch (reason) {
    // Primero se suelta la referencia: el aviso de desconexión no debe tomarse por una caída.
    if (device === chosen) device = null;
    chosen?.gatt?.disconnect();
    if (id !== connection) return;
    // Sin banda elegida. Al instante: Electron cancela así cuando la radio Bluetooth del equipo
    // está apagada o no hay adaptador (visto el 2026-11-13: la radio estaba apagada en Windows y
    // el panel volvía a «Conectar banda» sin decir nada). Tras la búsqueda: no apareció ninguna.
    if (reason instanceof DOMException && reason.name === "NotFoundError") {
      setBand({ kind: "notFound", quick: Date.now() - started < QUICK_CANCEL_MS });
    } else {
      setBand({ kind: "failed", outcome: requestOutcome(reason) });
    }
  }
}

const CONTACT_TEXT: Record<SensorContact, string> = {
  detected: "con contacto",
  not_detected: "sin contacto",
  unsupported: "la banda no lo informa",
};

/** Una cifra de la banda, o lo que falta dicho con palabras. */
function Reading({ label, value, unit, decimals = 0 }: { label: string; value: number | null; unit: string; decimals?: number }) {
  return (
    <li>
      {label}:{" "}
      {value === null ? (
        <span className="secondary">sin dato todavía</span>
      ) : (
        <span className="num">
          {formatNumber(value, decimals)} {unit}
        </span>
      )}
    </li>
  );
}

export function HeartBandPanel({
  subject,
  onChooseSubject,
}: {
  /** El tripulante que se está mirando. */
  subject: string;
  /** Pasa la consola a otro tripulante (`choose` de `useConsoleData`). */
  onChooseSubject?: ((subject: string) => void) | undefined;
}) {
  // Los tipos de Web Bluetooth (`@types/web-bluetooth`) lo dan siempre; sin Bluetooth no existe.
  const bluetooth = navigator.bluetooth as Bluetooth | undefined;
  const state = useSyncExternalStore(subscribe, () => band);

  useEffect(() => {
    chooseSubject = onChooseSubject ?? null;
    return () => {
      if (chooseSubject === onChooseSubject) chooseSubject = null;
    };
  }, [onChooseSubject]);

  // Al salir del panel, la banda se suelta: no se queda grabando sin que nadie lo vea. Con el
  // margen de `RELEASE_MS`, para que el cambio de tripulante no la desconecte.
  useEffect(() => {
    mountedPanels += 1;
    if (release !== null) clearTimeout(release);
    release = null;
    return () => {
      mountedPanels -= 1;
      if (mountedPanels === 0) {
        release = setTimeout(() => {
          release = null;
          if (mountedPanels === 0) releaseBand();
        }, RELEASE_MS);
      }
    };
  }, []);

  return (
    <section data-ui="heart-band" className="panel" aria-label="Banda de pulso">
      <PanelTitle concept="devices">Banda de pulso (Bluetooth)</PanelTitle>
      {bluetooth === undefined ? (
        <p className="secondary">
          <MarkOf mark={UNAVAILABLE_MARK}>
            Este navegador no tiene Bluetooth: use la aplicación de escritorio de EMMA o Chrome/Edge.
          </MarkOf>
        </p>
      ) : (
        <>
          <p className="secondary">
            Póngase la banda, enciéndala y pulse «Conectar banda». Sus lecturas se firman para{" "}
            <strong>{BAND_SUBJECT}</strong>, un tripulante real aparte de los simulados, como lecturas
            reales de wearable; con la primera, la consola pasa a {BAND_SUBJECT}.
          </p>
          {state.kind === "connected" ? (
            <>
              <p>
                <MarkOf mark={OK_MARK}>Conectada: {state.name}</MarkOf>
              </p>
              {state.fields === null ? (
                <p className="secondary">Esperando la primera lectura.</p>
              ) : (
                <ul>
                  <Reading label="Pulso" value={state.fields.heartRate} unit="/min" />
                  <Reading label="Último intervalo R-R" value={state.lastRrMs} unit="ms" />
                  <Reading label="Variabilidad RMSSD" value={state.hrv?.rmssdMs ?? null} unit="ms" decimals={1} />
                  <Reading label="Variabilidad SDNN" value={state.hrv?.sdnnMs ?? null} unit="ms" decimals={1} />
                  <li>
                    Contacto con la piel: {CONTACT_TEXT[state.fields.contact]}
                  </li>
                  {state.fields.energyKj !== null && (
                    <Reading label="Energía gastada" value={state.fields.energyKj} unit="kJ" />
                  )}
                </ul>
              )}
              <p className="secondary">
                <span className="num">{formatNumber(state.recorded)}</span> registradas
                {state.failed > 0 && (
                  <>
                    {" "}· <span className="num">{formatNumber(state.failed)}</span> rechazadas
                  </>
                )}
              </p>
              {subject !== BAND_SUBJECT && state.recorded > 0 && onChooseSubject !== undefined && (
                <Command concept="devices" type="button" onClick={() => onChooseSubject(BAND_SUBJECT)}>
                  Ver a {BAND_SUBJECT}
                </Command>
              )}{" "}
              <Command concept="devices" type="button" onClick={releaseBand}>
                Desconectar
              </Command>
            </>
          ) : (
            <Command
              concept="devices"
              type="button"
              disabled={state.kind === "connecting"}
              onClick={() => void connectBand(bluetooth)}
            >
              {state.kind === "connecting" ? <MarkOf mark={LOADING_MARK}>Buscando banda…</MarkOf> : "Conectar banda"}
            </Command>
          )}
          {state.kind === "notFound" && (
            <p>
              <MarkOf mark={UNAVAILABLE_MARK}>
                {state.quick
                  ? "El Bluetooth del equipo está apagado o no está disponible: enciéndalo en Windows (Configuración › Bluetooth) y vuelva a pulsar «Conectar banda»."
                  : "No apareció ninguna banda: compruebe que está puesta y encendida, y que no está conectada al móvil u otro equipo."}
              </MarkOf>
            </p>
          )}
          {state.kind === "failed" && (
            <p>
              <MarkOf mark={state.outcome.mark}>{state.outcome.text}</MarkOf>
            </p>
          )}
        </>
      )}
    </section>
  );
}
