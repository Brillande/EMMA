/**
 * Alertas: lo que F.6.4 pide contar, y lo que el retardo significa para cada una.
 *
 * F.6.4 exige mostrar *"Active Emergency Count, Active Warning Count, Active Caution
 * Count, Unacknowledged/New Event Count"*. Aqui se derivan de los dominios que
 * evalua el backend; la interfaz no decide niveles, solo los cuenta.
 *
 * Y lo que ningun referente de `compliance/hmi-state-of-the-art.md` hace: a cada
 * alerta se le anade cuando la conocera Tierra y cuando podria llegar, como pronto,
 * su respuesta. A 14 minutos de ida, "avisar a Tierra" no es pedir ayuda: es
 * informar de algo que la tripulacion tendra que resolver sola. Verlo junto a la
 * alerta es el argumento de la autonomia, en la pantalla y no en una diapositiva.
 */

import type { AlertState, CommsWindow, DomainRisk, LinkSync } from "./api";
import { LEVELS, type Level, isLevel } from "./levels";
import { type StateMark, UNKNOWN_MARK, mark } from "./marks";
import { uiPictogram } from "./uiMarks";

export interface Alert {
  /** Clave estable: dominio y nivel. Si el nivel cambia, es una alerta nueva. */
  id: string;
  domain: string;
  level: Exclude<Level, "nominal">;
  drivers: string[];
}

export function activeAlerts(domains: Record<string, DomainRisk>): Alert[] {
  const alerts: Alert[] = [];
  for (const [domain, risk] of Object.entries(domains)) {
    if (!isLevel(risk.level)) {
      throw new RangeError(`nivel de riesgo desconocido en ${domain}: ${risk.level}`);
    }
    if (risk.level === "nominal") continue;
    alerts.push({
      id: `${domain}:${risk.level}`,
      domain,
      level: risk.level,
      drivers: risk.drivers,
    });
  }
  // Lo mas grave primero (F.6.4: ordenables por prioridad).
  const rank = (level: Level) => ["watch", "concern", "critical"].indexOf(level);
  return alerts.sort((a, b) => rank(b.level) - rank(a.level));
}

export type Annunciation = AlertState["annunciation"];
export type Resolution = NonNullable<AlertState["resolution"]>["state"];

/**
 * El pictograma de cada estado de una alerta, junto a la palabra que ya existia (F.5.10 e). Sin
 * color: son informacion sobre lo que alguien hizo, no una señal nueva; el color de la fila sigue
 * siendo el del nivel. El significado lo da la palabra.
 *
 * Desde la segunda pasada (§5.33.1) cada estado que deja un mando sale del mismo concepto que el
 * mando (`lib/uiMarks.ts`): «Suprimida» y «Suprimir…» llevan la misma campana tachada, «En
 * arreglo» la llave del botón, «Resuelta» la marca de visto, «Reconocida» la pluma de
 * «Reconocer». Un dibujo por concepto, y si el vocabulario cambia, cambian los dos a la vez.
 *
 * Resolucion (Polaris `salud.py`): un punto dentro de un anillo (detectada), una llave inglesa
 * (en arreglo) y la marca de hecho (resuelta). Anuncio (F.6.4): la que se anuncia no lleva señal
 * —no hay nada que señalar—; la suprimida, una campana tachada; la inhibida, una campana dentro
 * de un marco (el dominio entero, con la puerta cerrada). Reconocimiento: una pluma (alguien
 * firmo); la que nadie ha reconocido tampoco lleva señal propia: lo dicen el parpadeo de la
 * insignia y el boton de reconocer, y no hay palabra junto a la que ponerla.
 *
 * Un estado que la interfaz no conoce se enseña con su palabra y el dibujo de «desconocido»
 * (`UNKNOWN_MARK`): la fila sigue en pantalla con las demas alertas, en vez de tumbar la consola
 * desde dentro de un render.
 */
export const RESOLUTION_MARKS: Record<Resolution, StateMark> = {
  detectado: mark("dot-ringed", null),
  en_arreglo: mark(uiPictogram("inRepair"), null),
  resuelto: mark(uiPictogram("resolved"), null),
};

export const ANNUNCIATION_MARKS: Record<Annunciation, StateMark> = {
  normal: mark(null, null),
  suppressed: mark(uiPictogram("suppress"), null),
  inhibited: mark(uiPictogram("inhibit"), null),
};

export const ACKNOWLEDGEMENT_MARKS: Record<"acknowledged" | "unacknowledged", StateMark> = {
  acknowledged: mark(uiPictogram("acknowledge"), null),
  unacknowledged: mark(null, null),
};

function lookup(table: Readonly<Record<string, StateMark>>, key: string): StateMark {
  return Object.hasOwn(table, key) ? (table[key] ?? UNKNOWN_MARK) : UNKNOWN_MARK;
}

export function resolutionMark(state: string): StateMark {
  return lookup(RESOLUTION_MARKS, state);
}

export function annunciationMark(state: string): StateMark {
  return lookup(ANNUNCIATION_MARKS, state);
}

export function acknowledgementMark(acknowledged: boolean): StateMark {
  return acknowledged ? ACKNOWLEDGEMENT_MARKS.acknowledged : ACKNOWLEDGEMENT_MARKS.unacknowledged;
}

export interface AlertCounts {
  warning: number;
  caution: number;
  advisory: number;
  /** Las que reclaman atencion: ni reconocidas ni silenciadas. */
  unacknowledged: number;
  suppressed: number;
  inhibited: number;
}

/** Estado de anuncio de cada alerta, segun el ledger. */
export function annunciations(states: readonly AlertState[]): ReadonlyMap<string, string> {
  return new Map(states.map((state) => [state.id, state.annunciation]));
}

/**
 * Las alertas reconocidas segun el backend. El reconocimiento vive en el ledger,
 * no en la sesion de la interfaz: recargar no lo pierde y queda su autor.
 */
export function acknowledgedIds(states: readonly AlertState[]): ReadonlySet<string> {
  return new Set(states.filter((state) => state.acknowledged).map((state) => state.id));
}

/**
 * F.6.4: contadores. Una alerta silenciada sigue contando como activa en su clase
 * —existe—, pero no como pendiente: ya no reclama atencion. Se cuenta aparte, para
 * que lo silenciado se vea siempre.
 */
export function countAlerts(
  alerts: Alert[],
  acknowledged: ReadonlySet<string>,
  silenced: ReadonlyMap<string, string> = new Map(),
): AlertCounts {
  const counts: AlertCounts = {
    warning: 0, caution: 0, advisory: 0, unacknowledged: 0, suppressed: 0, inhibited: 0,
  };
  for (const alert of alerts) {
    const cls = LEVELS[alert.level].alertClass;
    if (cls === "W") counts.warning += 1;
    else if (cls === "C") counts.caution += 1;
    else if (cls === "A") counts.advisory += 1;
    const state = silenced.get(alert.id) ?? "normal";
    if (state === "suppressed") counts.suppressed += 1;
    else if (state === "inhibited") counts.inhibited += 1;
    else if (!acknowledged.has(alert.id)) counts.unacknowledged += 1;
  }
  return counts;
}

export interface EarthTimeline {
  /** Cuando llega a Tierra lo que se ve a bordo en `at`. */
  earthKnowsAt: Date;
  /** La respuesta mas temprana posible: ida y vuelta, sin tiempo para pensar. */
  earliestReplyAt: Date;
}

/**
 * Sin efemerides no hay tiempos: se devuelve `null` y la interfaz lo muestra como
 * dato ausente (cian), nunca como si Tierra estuviera al lado.
 */
export function earthTimeline(at: Date, comms: CommsWindow | null): EarthTimeline | null {
  if (comms === null) return null;
  const oneWayMs = comms.one_way_minutes * 60_000;
  return {
    earthKnowsAt: new Date(at.getTime() + oneWayMs),
    earliestReplyAt: new Date(at.getTime() + 2 * oneWayMs),
  };
}

/**
 * Lo que la fila de una alerta puede decir de cuándo la verá Tierra (lógica 6). `earthTimeline`
 * solo mira las efemérides: con el enlace simulado declarado caído (§5.47) la fila seguía diciendo
 * «Tierra lo sabrá a …» un tiempo de luz después, mientras la franja decía «caído» y el backend
 * («Se envían … cuando se declare restablecido») que no sale nada hasta entonces. Caído, no se sabe
 * cuándo: es un dato ausente, como sin efemérides. Restablecido, lo firmado sale al firmarse y la
 * cuenta de siempre vale.
 */
export type EarthArrival =
  | { kind: "link-down" }
  | { kind: "no-ephemeris" }
  | { kind: "known"; timeline: EarthTimeline };

export function earthArrival(
  at: Date,
  comms: CommsWindow | null,
  sync: Pick<LinkSync, "state"> | null,
): EarthArrival {
  if (sync?.state === "down") return { kind: "link-down" };
  const timeline = earthTimeline(at, comms);
  return timeline === null ? { kind: "no-ephemeris" } : { kind: "known", timeline };
}
