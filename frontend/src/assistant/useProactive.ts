import { useCallback, useEffect, useRef } from "react";

import type { Speaker } from "../components/ReadAloud";
import type { Alert } from "../lib/alerts";
import { type CrewStatus, api } from "../lib/api";
import { emit } from "./bus";
import {
  type AlertMemory,
  INITIAL_ALERT_MEMORY,
  INITIAL_PACER,
  type Notice,
  type Pacer,
  type RoutineMemory,
  drain,
  enqueue,
  routineNotices,
  silenceFor,
  silencedUntil,
  statusNotices,
} from "./proactive";

/** Cada cuánto se mira la cola: solo reloj local, ninguna petición. */
const DRAIN_TICK_MS = 1_000;

/**
 * La iniciativa propia en el navegador: la parte de `proactive.ts` que lee el backend y habla. Qué
 * se dice, cuándo y en qué orden se decide allí, en funciones puras con prueba; aquí solo se
 * guardan los estados entre sondeos, se pide la lectura de medidas periódicas con cada estado
 * nuevo (la única petición que añade este modo, y solo en la consola de a bordo: la de Tierra
 * juzga con su corte, que `/timeline/routines` no recibe aquí) y se dice con la voz.
 *
 * Sin voz local (`speaker.availability`), apagado: no se dice nada, ni al canal.
 */
export function useProactive({
  enabled,
  speaker,
  scope,
  consoleName,
  subject,
  status,
  alerts,
  annunciation,
  acknowledged,
  privacy,
  routines,
}: {
  enabled: boolean;
  speaker: Speaker;
  /** El ámbito en pantalla: consola y tripulante. */
  scope: string;
  consoleName: string;
  subject: string;
  /** El estado que se ve; `null` cargando o con error (entonces no se planifica nada). */
  status: CrewStatus | null;
  alerts: readonly Alert[];
  annunciation: ReadonlyMap<string, string>;
  acknowledged: ReadonlySet<string>;
  privacy: boolean;
  /** De quién se leen las medidas periódicas; `null` para no leerlas (consola de Tierra). */
  routines: string | null;
}): void {
  const on = enabled && speaker.availability === "ready";
  const alertMemory = useRef<AlertMemory>(INITIAL_ALERT_MEMORY);
  const routineMemory = useRef<{ scope: string; memory: RoutineMemory } | null>(null);
  const pacer = useRef<Pacer>(INITIAL_PACER);
  const scopeNow = useRef(scope);
  scopeNow.current = scope;
  const { say } = speaker;

  const flush = useCallback(() => {
    const now = Date.now();
    const result = drain(pacer.current, now, silencedUntil());
    pacer.current = result.pacer;
    if (result.speak.length === 0) return;
    say(result.speak.flatMap((notice: Notice) => notice.chunks), result.interrupt);
    // Ya dicho: el canal lo lleva al hilo del asistente, que no lo vuelve a decir.
    for (const notice of result.speak) emit({ kind: "say", text: notice.chunks.join(" ") });
  }, [say]);

  const offer = useCallback(
    (notices: readonly Notice[]) => {
      if (notices.length === 0) return;
      pacer.current = enqueue(pacer.current, notices, Date.now(), silencedUntil());
      flush();
    },
    [flush],
  );

  // Apagar el modo (o quedarse sin voz) lo olvida todo: al volver, saluda y parte de cero. Apagarlo
  // a mano quita también el silencio: si no, uno de antes se tragaría el saludo sin decir por qué.
  useEffect(() => {
    if (on) return;
    alertMemory.current = INITIAL_ALERT_MEMORY;
    routineMemory.current = null;
    pacer.current = INITIAL_PACER;
    if (!enabled) silenceFor(0);
  }, [on, enabled]);

  useEffect(() => {
    if (!on || status === null) return;
    const result = statusNotices(alertMemory.current, {
      scope,
      console: consoleName,
      subject,
      summary: status.summary,
      alerts,
      annunciation,
      acknowledged,
      privacy,
      now: Date.now(),
    });
    alertMemory.current = result.memory;
    offer(result.notices);
    // `status` cambia con cada sondeo; las alertas y su estado de anuncio salen de él.
  }, [on, status, scope, consoleName, subject, alerts, annunciation, acknowledged, privacy, offer]);

  useEffect(() => {
    if (!on || status === null || routines === null) return;
    let cancelled = false;
    const asked = scope;
    api
      .routines(routines)
      .then((view) => {
        // La respuesta de otro ámbito (se cambió de tripulante o de consola mientras tanto) no vale.
        if (cancelled || scopeNow.current !== asked) return;
        const previous = routineMemory.current?.scope === asked ? routineMemory.current.memory : null;
        const result = routineNotices(previous, view, asked, Date.now());
        routineMemory.current = { scope: asked, memory: result.memory };
        offer(result.notices);
      })
      // Una lectura fallida no es un cambio: se queda la anterior como línea de partida.
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [on, status, scope, routines, offer]);

  // Lo que espera turno sale cuando le toca: un reloj local, sin pedir nada al backend.
  useEffect(() => {
    if (!on) return;
    const timer = setInterval(flush, DRAIN_TICK_MS);
    return () => clearInterval(timer);
  }, [on, flush]);
}
