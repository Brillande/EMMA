/**
 * Una sesión de la prueba PVT en la consola: el temporizador y qué se envía.
 *
 * Por qué está aparte del panel: lo que aquí se decide es delicado y se quiere probado con un
 * reloj falso. Una respuesta antes de la marca no tiene tiempo de reacción; un estímulo sin
 * respuesta tampoco; y una prueba abandonada no puede dejar nada que enviar. Nada de eso se
 * puede comprobar pulsando teclas delante de una pantalla.
 *
 * Aquí NO se puntúa. No se cuenta un lapso, no se descarta una respuesta rápida, no se
 * promedia: se anota un tiempo por estímulo y se envía la lista tal cual a
 * `POST /api/pvt/console`, que es quien puntúa. Las cifras de la sesión (cuántos estímulos, cuánta espera, cómo se
 * envía una respuesta prematura, cuánto se espera una respuesta) las da el backend
 * (`GET /api/pvt/protocol`); este fichero no tiene ninguna propia.
 *
 * El tiempo se mide con el reloj que se le pasa (`performance.now()` en el panel). Entre ese
 * reloj y lo que la persona ve y pulsa hay una latencia de pantalla y de teclado que no está
 * caracterizada: el panel lo dice con el texto del backend.
 */
import { formatNumber } from "../lib/format";
import type {
  PvtProtocol,
  PvtSessionSpec,
  PvtSubmissionBody,
  PvtSubmitted,
} from "../lib/api";

/** El reloj y los temporizadores, inyectados para poder probar con un reloj falso. */
export interface Clock {
  now: () => number;
  setTimer: (run: () => void, afterMs: number) => unknown;
  clearTimer: (handle: unknown) => void;
}

export type Phase = "idle" | "waiting" | "stimulus" | "finished" | "abandoned";

/** Quién abandonó: la persona, o nadie respondió dentro del tiempo máximo de espera. */
export type Abandoned = "user" | "no-response";

export interface Snapshot {
  phase: Phase;
  total: number;
  /** Estímulos ya cerrados con una respuesta, válida o antes de la marca. */
  done: number;
  /** La última respuesta se dio antes de la marca. Se apaga al aparecer la siguiente. */
  premature: boolean;
  abandoned: Abandoned | null;
  /** Un tiempo por estímulo cerrado, en ms. Vacío si la prueba se abandonó. */
  times: readonly number[];
}

export const IDLE: Snapshot = {
  phase: "idle",
  total: 0,
  done: 0,
  premature: false,
  abandoned: null,
  times: [],
};

/** Si las cifras del backend sirven para pasar una prueba. Si no, no se empieza. */
export function usable(spec: PvtSessionSpec): boolean {
  const numbers = [
    spec.trials,
    spec.foreperiod_min_ms,
    spec.foreperiod_max_ms,
    spec.premature_response_ms,
    spec.abandon_after_ms,
  ];
  return (
    numbers.every((value) => Number.isFinite(value)) &&
    Number.isInteger(spec.trials) &&
    spec.trials >= 1 &&
    spec.foreperiod_min_ms > 0 &&
    spec.foreperiod_max_ms >= spec.foreperiod_min_ms &&
    spec.abandon_after_ms > 0
  );
}

/** La espera antes de un estímulo: un valor entre los dos extremos que da el backend. */
export function foreperiod(spec: PvtSessionSpec, random: () => number): number {
  const draw = Math.min(Math.max(random(), 0), 1);
  return spec.foreperiod_min_ms + draw * (spec.foreperiod_max_ms - spec.foreperiod_min_ms);
}

export interface Session {
  start: () => void;
  /** Una pulsación o un toque. Fuera de una prueba en curso no hace nada. */
  respond: () => void;
  /** Abandona: se tiran los tiempos anotados y no queda nada que enviar. */
  abandon: () => void;
  snapshot: () => Snapshot;
  /** Para los temporizadores sin cambiar de estado (al desmontar el panel). */
  dispose: () => void;
}

export function createSession(
  spec: PvtSessionSpec,
  clock: Clock,
  random: () => number,
  onChange: (snapshot: Snapshot) => void,
): Session {
  if (!usable(spec)) throw new RangeError("parámetros de la prueba no utilizables");

  let phase: Phase = "idle";
  let times: number[] = [];
  let premature = false;
  let abandoned: Abandoned | null = null;
  let shownAt = 0;
  let timer: unknown = null;

  const snapshot = (): Snapshot => ({
    phase,
    total: spec.trials,
    done: times.length,
    premature,
    abandoned,
    times: [...times],
  });
  const emit = () => onChange(snapshot());

  const stop = () => {
    if (timer !== null) clock.clearTimer(timer);
    timer = null;
  };

  const leave = (why: Abandoned) => {
    stop();
    // Una prueba a medias no es una prueba: no se conserva ningún tiempo.
    times = [];
    premature = false;
    abandoned = why;
    phase = "abandoned";
    emit();
  };

  const show = () => {
    timer = null;
    phase = "stimulus";
    premature = false;
    shownAt = clock.now();
    // Un estímulo sin respuesta no tiene tiempo de reacción: no se inventa uno.
    timer = clock.setTimer(() => leave("no-response"), spec.abandon_after_ms);
    emit();
  };

  const wait = () => {
    phase = "waiting";
    timer = clock.setTimer(show, foreperiod(spec, random));
  };

  const close = (time: number) => {
    stop();
    times.push(time);
    if (times.length >= spec.trials) phase = "finished";
    else wait();
    emit();
  };

  return {
    start: () => {
      stop();
      times = [];
      premature = false;
      abandoned = null;
      wait();
      emit();
    },
    respond: () => {
      if (phase === "stimulus") {
        const took = clock.now() - shownAt;
        // Un temporizador puede vencer tarde: una pulsación que llega pasado el tiempo
        // máximo de espera ya no es una respuesta a esa marca.
        if (took >= spec.abandon_after_ms) leave("no-response");
        else close(took);
      } else if (phase === "waiting") {
        // Antes de la marca: se envía como dice el backend, y él la cuenta.
        premature = true;
        close(spec.premature_response_ms);
      }
    },
    abandon: () => {
      if (phase === "waiting" || phase === "stimulus") leave("user");
    },
    snapshot,
    dispose: stop,
  };
}

export function running(snapshot: Snapshot): boolean {
  return snapshot.phase === "waiting" || snapshot.phase === "stimulus";
}

/**
 * El nombre de quien está en la consola, recortado, o `null` si no vale como nombre: vacío, o
 * sin una letra ni una cifra. Es la regla del backend, que lo rechaza igual. Sin nombre la
 * prueba no se empieza: acabarla para descubrir que no se puede firmar sería tirarla.
 */
export function operatorName(operator: string): string | null {
  const name = operator.trim();
  return /[\p{L}\p{N}]/u.test(name) ? name : null;
}

/**
 * Lo que se envía: solo una prueba entera, con un tiempo por estímulo, de quién es y quién
 * estaba en la consola. Abandonada, a medias, sin empezar o sin nombre no hay cuerpo que
 * enviar. No lleva hora ni fuente: las pone el backend al recibirla.
 */
export function submission(
  snapshot: Snapshot,
  subject: string,
  operator: string,
): PvtSubmissionBody | null {
  if (snapshot.phase !== "finished") return null;
  if (snapshot.total < 1 || snapshot.times.length !== snapshot.total) return null;
  if (subject === "") return null;
  const name = operatorName(operator);
  if (name === null) return null;
  return { reaction_times_ms: [...snapshot.times], subject, recorded_by: name };
}

export interface ResultRow {
  key: string;
  display: string;
  text: string;
  /** El indicador con que esta cifra queda en el registro, si queda. */
  recordedAs: string | null;
}

/**
 * La puntuación que devolvió el backend, con los nombres del backend. Una cifra que el
 * backend no devolvió no se pinta ni se calcula aquí.
 */
export function resultRows(protocol: PvtProtocol, submitted: PvtSubmitted): ResultRow[] {
  const rows: ResultRow[] = [];
  for (const field of protocol.result_fields) {
    const value = submitted.result[field.key];
    if (typeof value !== "number" || !Number.isFinite(value)) continue;
    const unit = field.unit_display === "" ? "" : ` ${field.unit_display}`;
    rows.push({
      key: field.key,
      display: field.display,
      text: formatNumber(value, field.decimals) + unit,
      recordedAs: field.recorded_as,
    });
  }
  return rows;
}
