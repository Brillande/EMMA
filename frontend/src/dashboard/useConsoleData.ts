/**
 * La capa de datos de la consola: qué se pide al backend, cada cuánto, qué se deriva de ello y
 * qué se firma. Un solo sitio para las dos conchas —la clásica (`#clasica`) y la de la maqueta
 * (`consoleShell.css` y «Inicio» en `HomeBoard.tsx`; decisión del usuario del 2026-11-07 de hacerla
 * la consola)—: dos copias de
 * «cuándo se relee el estado» o «con qué sujeto se firma una alerta» acabarían discrepando, y lo
 * que se firma es del ledger, no de una pantalla.
 *
 * Lo que hace, tal como lo hacía `App`:
 * - pide el estado de a bordo cada `REFRESH_MS` (el backend recalcula en cada consulta; 30 s basta
 *   para datos horarios), o cada `LIVE_REFRESH_MS` mientras lo mirado llega en vivo (`isLive`: la
 *   banda de pulso), el enlace simulado con el corte por tiempo de luz y el estado que Tierra
 *   ya tiene (un 404 ahí es «todavía no ha llegado nada», no un fallo);
 * - descarta la respuesta de un tripulante que ya no es el elegido;
 * - trae la tripulación conocida (en Tierra, solo quien ya tiene lecturas llegadas) y, con el
 *   almacén vacío o un tripulante que ya no existe, cae al que toque;
 * - deriva las alertas activas, las reconocidas y las silenciadas de lo que se ve, y sus recuentos;
 * - firma cada acción sobre una alerta o contramedida con el tripulante que el backend dice haber
 *   analizado (`viewed`), y después relee: lo que se enseña es lo firmado, nunca un clic local.
 *
 * Las funciones puras van exportadas aparte para probarlas sin DOM.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  type Alert,
  type AlertCounts,
  acknowledgedIds,
  activeAlerts,
  annunciations,
  countAlerts,
} from "../lib/alerts";
import { ApiError, type CrewStatus, type LinkSync, api } from "../lib/api";
import { DEFAULT_SUBJECT, crewOptions, fallbackSubject, groundCut, linkedCut } from "../lib/crew";
import { type RequestOutcome, requestOutcome } from "../lib/marks";
import type { AlertActions } from "./AlertRow";
import type { CountermeasureActions } from "./CrewConsole";

export type ConsoleKey = "crew" | "ground";

// El backend recalcula en cada consulta; cada 30 s basta para datos horarios.
export const REFRESH_MS = 30_000;

// Con una banda de pulso escribiendo en vivo (~1 lectura/s de frecuencia cardiaca, la VFC cada
// minuto), 30 s dejaba la pantalla medio minuto por detrás de lo que la banda ya había firmado.
// Cada 5 s se ve moverse sin pedir el estado (que el backend recalcula entero) a cada latido: son
// tres peticiones por relectura (estado, enlace, recibido) y las series de «Inicio».
export const LIVE_REFRESH_MS = 5_000;

// Cuánto puede tener la última lectura frente al reloj para seguir llamándola «en vivo». Dos
// minutos cubren la VFC (una por minuto) y un corte breve del Bluetooth; pasado eso la banda está
// quieta y se vuelve a 30 s, sin tener que reconocer el corte en ningún otro sitio.
export const LIVE_WINDOW_MS = 2 * 60_000;

// Margen hacia delante: un reloj del equipo que va unos segundos por detrás del del backend no
// debe apagar el modo en vivo; una referencia muy en el futuro (un escenario simulado) no es vivo.
const LIVE_SKEW_MS = 60_000;

// Las fuentes que escriben en tiempo real. Las demás (simulador, Apple Health, Google Fit, FHIR)
// llegan por lotes: aunque su última lectura caiga cerca del reloj, releer cada 5 s no trae nada.
export const LIVE_SOURCES: readonly string[] = ["wearable-ble"];

/**
 * Si lo que se mira llega en vivo: tiene una fuente de tiempo real y su última lectura
 * (`reference_time`) está a menos de `LIVE_WINDOW_MS` del reloj (`now`, en milisegundos).
 */
export function isLive(onboard: CrewStatus, now: number): boolean {
  if (!onboard.mission.sources.some((source) => LIVE_SOURCES.includes(source))) return false;
  const latest = Date.parse(onboard.data.reference_time);
  if (!Number.isFinite(latest)) return false;
  const age = now - latest;
  return age <= LIVE_WINDOW_MS && age >= -LIVE_SKEW_MS;
}

/** Cada cuánto se relee el estado: deprisa con datos en vivo, como siempre sin ellos. */
export function refreshPeriod(load: Load, now: number): number {
  return load.state === "ready" && isLive(load.onboard, now) ? LIVE_REFRESH_MS : REFRESH_MS;
}

export type Load =
  | { state: "loading" }
  | { state: "empty" }
  | { state: "error"; outcome: RequestOutcome }
  | { state: "ready"; onboard: CrewStatus; received: CrewStatus | null; sync: LinkSync };

/** El corte de Tierra por tiempo de luz para un estado de a bordo: su última lectura menos el retardo. */
export function lightCutOf(onboard: CrewStatus): Date | null {
  return groundCut(onboard.data.reference_time, onboard.comms?.one_way_minutes ?? null);
}

/**
 * El corte de Tierra: el del tiempo de luz, salvo que el enlace simulado declarado caído lo retenga
 * en la caída (`linkedCut`, §5.47). Es el que se pide a todas las rutas de Tierra.
 */
export function cutOf(onboard: CrewStatus, sync: LinkSync): Date | null {
  return linkedCut(lightCutOf(onboard), sync);
}

/**
 * Cambia cuando cambia lo que hay en el almacén: otro escenario, lecturas nuevas (una más en el
 * recuento o una última lectura posterior). Las series que se dibujan se vuelven a pedir con ella:
 * con solo la referencia, una lectura en vivo del mismo segundo no movía las gráficas.
 */
export function dataKeyOf(onboard: CrewStatus): string {
  return `${onboard.data.reference_time}|${onboard.mission.sources.join(",")}|${onboard.data.observations}`;
}

/** Lo que se enseña cuando el estado no llega: un 404 es el almacén vacío; lo demás, un fallo con su marca. */
export function loadOfFailure(error: unknown): Load {
  if (error instanceof ApiError && error.status === 404) return { state: "empty" };
  return { state: "error", outcome: requestOutcome(error) };
}

/**
 * El estado que Tierra puede tener: el calculado con las lecturas llegadas, es decir, hasta un
 * tiempo de luz antes de la última lectura a bordo. Si todavía no ha llegado ninguna, no hay estado
 * recibido (404 del backend). Es el del mismo tripulante que el de a bordo: el que el backend dice
 * haber analizado. `fetchStatus` es `api.status`; va inyectado para probarlo sin red.
 */
export async function receivedStatus(
  fetchStatus: (until: Date, subject: string) => Promise<CrewStatus>,
  onboard: CrewStatus,
  until: Date | null,
): Promise<CrewStatus | null> {
  if (until === null) return onboard;
  try {
    return await fetchStatus(until, onboard.subject);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export interface ConsoleData {
  load: Load;
  /** A quién se mira. Gobierna las dos consolas: el estado, sus series y lo que se firma. */
  subject: string;
  /** La tripulación conocida (en Tierra, solo quien ya tiene lecturas llegadas). */
  members: string[];
  /** Las opciones del selector: la tripulación conocida, con el elegido aunque Tierra no lo tenga aún. */
  options: string[];
  /** Elegir a otro tripulante: retira lo que hay en pantalla antes de pedir lo suyo. */
  choose: (next: string) => void;
  /** Volver a pedir el estado (tras firmar algo, cambiar de escenario, cargar el almacén…). */
  refresh: () => Promise<void>;
  /** El corte de Tierra vigente; `null` a bordo o sin efemérides. */
  cut: Date | null;
  /** Lo que la consola activa enseña: a bordo, el estado de ahora; en Tierra, el que ha llegado. */
  shown: CrewStatus | null;
  /** De quién es lo que hay en pantalla: el tripulante que el backend dice haber analizado. */
  viewed: string;
  alerts: Alert[];
  acknowledged: ReadonlySet<string>;
  silenced: ReadonlyMap<string, string>;
  counts: AlertCounts;
  actions: AlertActions;
  countermeasureActions: CountermeasureActions;
}

export function useConsoleData(active: ConsoleKey): ConsoleData {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [subject, setSubject] = useState(DEFAULT_SUBJECT);
  // La tripulación conocida y la elección (`choice`) vigente cuando se pidió: solo una lista pedida
  // después de elegir puede confirmar que el elegido no tiene datos (`fallbackSubject`).
  const [roster, setRoster] = useState<{ members: string[]; choice: number }>({ members: [], choice: 0 });
  const members = roster.members;
  // El elegido en este instante, para descartar la respuesta de quien ya no lo es.
  const selected = useRef(subject);
  // Cuántas veces se ha elegido: distingue una lista de antes de elegir de una de después.
  const choice = useRef(0);

  const choose = useCallback((next: string) => {
    if (next === selected.current) return;
    selected.current = next;
    choice.current += 1;
    setSubject(next);
    // Lo que hay en pantalla es de otra persona: se retira antes de pedir lo nuevo. Dejarlo
    // mientras carga sería enseñar los datos de un tripulante bajo el nombre de otro.
    setLoad({ state: "loading" });
  }, []);

  // Con relecturas cada 5 s, una respuesta lenta podía llegar después de otra más nueva y devolver
  // la pantalla atrás: se numeran y no se aplica una anterior a la última aplicada. Y el reloj no
  // lanza otra mientras una sigue en vuelo, para no apilarlas si el backend tarda más que el periodo.
  const issued = useRef(0);
  const applied = useRef(0);
  const inFlight = useRef(0);
  const refresh = useCallback(async () => {
    const request = ++issued.current;
    inFlight.current += 1;
    try {
      const onboard = await api.status(undefined, subject);
      // El enlace simulado, con el corte por tiempo de luz: da el corte de Tierra (`cutOf`).
      const sync = await api.linkSync(lightCutOf(onboard));
      const received = await receivedStatus(api.status, onboard, cutOf(onboard, sync));
      if (selected.current !== subject || request < applied.current) return;
      applied.current = request;
      setLoad({ state: "ready", onboard, received, sync });
    } catch (error) {
      if (selected.current !== subject || request < applied.current) return;
      applied.current = request;
      setLoad(loadOfFailure(error));
    } finally {
      inFlight.current -= 1;
    }
  }, [subject]);

  // Cada vuelta del reloj relee el estado y también la tripulación (`tick`): un tripulante nuevo
  // —la banda de pulso escribe en `real-01`, que no es el que se mira— no cambia el estado del
  // elegido, y sin esto no aparecía en el selector hasta cambiar algo más.
  const [tick, setTick] = useState(0);
  const period = refreshPeriod(load, Date.now());
  useEffect(() => {
    void refresh();
  }, [refresh]);
  useEffect(() => {
    const timer = setInterval(() => {
      setTick((value) => value + 1);
      if (inFlight.current === 0) void refresh();
    }, period);
    return () => clearInterval(timer);
  }, [refresh, period]);

  // La tripulación conocida. En la consola de Tierra, solo quien ya tiene lecturas llegadas:
  // que exista un tripulante con datos también viaja a la velocidad de la luz.
  const cut = load.state === "ready" && active === "ground" ? cutOf(load.onboard, load.sync) : null;
  const cutKey = cut?.toISOString() ?? "";
  const dataKey = load.state === "ready" ? dataKeyOf(load.onboard) : load.state;
  useEffect(() => {
    let cancelled = false;
    const asked = choice.current;
    api
      .crewMembers(cutKey === "" ? undefined : new Date(cutKey))
      .then((payload) => {
        if (!cancelled) setRoster({ members: payload.crew.map((item) => item.subject), choice: asked });
      })
      // Si falla se conserva la lista anterior: el error del backend ya lo cuenta el estado.
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // `subject` va en las dependencias: al elegir se pide una lista nueva, la única que puede
    // confirmar que el elegido no tiene datos.
  }, [cutKey, dataKey, subject, tick]);

  useEffect(() => {
    const next = fallbackSubject(members, subject, load.state === "empty", roster.choice === choice.current);
    if (next !== null) choose(next);
  }, [members, roster.choice, subject, load.state, choose]);

  // La franja común es la misma en las dos consolas (F.4.2), pero cada una cuenta
  // lo que sabe: a bordo, el estado de ahora; en Tierra, el que ha llegado.
  const shown = load.state !== "ready" ? null : active === "crew" ? load.onboard : load.received;
  const alerts = useMemo(() => (shown === null ? [] : activeAlerts(shown.domains)), [shown]);
  const acknowledged = useMemo(
    () => (shown === null ? new Set<string>() : acknowledgedIds(shown.alerts)),
    [shown],
  );
  const silenced = useMemo(
    () => (shown === null ? new Map<string, string>() : annunciations(shown.alerts)),
    [shown],
  );
  const counts = countAlerts(alerts, acknowledged, silenced);

  // De quién es lo que hay en pantalla: el tripulante que el backend dice haber analizado.
  // Cada firma lleva ese sujeto. Sin él, el backend la apuntaba a `crew-01`: reconocer una
  // alerta de crew-02 habría reconocido la de crew-01, que en un escenario compartido existe.
  const viewed = load.state === "ready" ? load.onboard.subject : subject;

  // Toda acción sobre una alerta escribe en el ledger y después se vuelve a pedir el
  // estado: lo que se muestra es lo que el backend tiene firmado, no un clic local.
  // Se refieren al estado de a bordo que se está viendo (`reference_time`).
  const reference = load.state === "ready" ? load.onboard.data.reference_time : "";
  const about = (alert: Alert, by: string, reason: string) => ({
    subject: viewed,
    domain: alert.domain,
    reference_time: reference,
    reason,
    requested_by: by,
  });
  const actions: AlertActions = {
    resolve: async (alert, by, state, note) => {
      await api.resolveAlert({
        subject: viewed,
        domain: alert.domain,
        level: alert.level,
        reference_time: reference,
        state,
        note,
        declared_by: by,
      });
      await refresh();
    },
    dismiss: async (alert, by, reason, note) => {
      await api.dismissAlert({
        subject: viewed,
        domain: alert.domain,
        level: alert.level,
        reference_time: reference,
        reason,
        note,
        declared_by: by,
      });
      await refresh();
    },
    acknowledge: async (alert, by) => {
      await api.acknowledge({
        subject: viewed,
        domain: alert.domain,
        level: alert.level,
        reference_time: reference,
        acknowledged_by: by,
      });
      await refresh();
    },
    suppress: async (alert, by, reason, minutes) => {
      await api.suppress({ ...about(alert, by, reason), level: alert.level, duration_minutes: minutes });
      await refresh();
    },
    inhibit: async (alert, by, reason, hours) => {
      await api.inhibit({ ...about(alert, by, reason), level: alert.level, duration_hours: hours });
      await refresh();
    },
    enable: async (alert, by, reason) => {
      await api.enable(about(alert, by, reason));
      await refresh();
    },
  };
  const countermeasureActions: CountermeasureActions = {
    adopt: async (countermeasureId, by) => {
      await api.adoptCountermeasure({
        subject: viewed,
        countermeasure_id: countermeasureId,
        reference_time: reference,
        adopted_by: by,
      });
      await refresh();
    },
    decline: async (countermeasureId, by, reason) => {
      await api.declineCountermeasure({
        subject: viewed,
        countermeasure_id: countermeasureId,
        reference_time: reference,
        reason,
        declined_by: by,
      });
      await refresh();
    },
    close: async (adoptionIndex, by, reason) => {
      await api.closeFollowup({
        subject: viewed,
        adoption_index: adoptionIndex,
        reason,
        closed_by: by,
      });
      await refresh();
    },
    declareProfile: async (missions, doseMsv, by) => {
      await api.declareProfile({
        subject: viewed,
        prior_missions: missions,
        prior_career_dose_msv: doseMsv,
        declared_by: by,
      });
      await refresh();
    },
    declareEvent: async (kind, start, end, label, by, where) => {
      await api.declareMissionEvent({
        subject: viewed,
        kind,
        start,
        end,
        declared_by: by,
        // Una ubicación sin descripción se firma con el nombre del módulo, que pone el backend.
        ...(label === "" ? {} : { label }),
        ...where,
      });
      await refresh();
    },
  };

  const options = crewOptions(members, subject);

  return {
    load,
    subject,
    members,
    options,
    choose,
    refresh,
    cut,
    shown,
    viewed,
    alerts,
    acknowledged,
    silenced,
    counts,
    actions,
    countermeasureActions,
  };
}
