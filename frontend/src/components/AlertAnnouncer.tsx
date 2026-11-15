import { useEffect, useRef, useState } from "react";

import type { Alert } from "../lib/alerts";
import {
  type AnnouncerState,
  INITIAL_ANNOUNCER,
  type LiveMessage,
  appendMessages,
  planAnnouncements,
} from "../lib/announce";

/**
 * Las dos regiones vivas de la consola, para el lector de pantalla del sistema (§5.41).
 *
 * Por qué dos y por qué siempre montadas: un lector solo anuncia lo que cambia dentro de una región
 * viva que ya existía; si la región nace con el texto dentro, NVDA y el Narrador suelen callarlo.
 * Así que las dos están en la página desde el primer render, vacías, y las alertas nuevas se
 * añaden como nodos nuevos. `aria-atomic="false"` en las dos: `role="alert"` y `role="status"`
 * lo traen implícito a `true`, y con `true` el lector releería todo lo guardado con cada alerta.
 *
 * Están fuera de la vista (`.sr-only`) porque en pantalla la alerta ya está en su fila con su
 * insignia, su forma y su color: esto no es otra señal visual, es la misma alerta dicha.
 */
export function LiveRegions({
  assertive,
  polite,
}: {
  assertive: readonly LiveMessage[];
  polite: readonly LiveMessage[];
}) {
  return (
    <div className="sr-only">
      <div role="alert" aria-atomic="false">
        {assertive.map((message) => (
          <p key={message.id}>{message.text}</p>
        ))}
      </div>
      <div role="status" aria-atomic="false">
        {polite.map((message) => (
          <p key={message.id}>{message.text}</p>
        ))}
      </div>
    </div>
  );
}

/**
 * Lleva lo ya anunciado entre sondeos y alimenta las regiones. La decisión (qué, cuándo, con qué
 * urgencia) es de `lib/announce.ts`; aquí solo se guarda el estado. Sin estado listo (`ready`
 * falso: cargando o con error) no se planifica nada: una caída del backend no debe hacer que, al
 * volver, se repitan todas las alertas como nuevas. Al entrar en otro ámbito (otra consola, otro
 * tripulante) las regiones se vacían antes de decir lo que hay: lo que queda guardado en ellas es
 * siempre de quien está en pantalla.
 */
export function AlertAnnouncer({
  ready,
  scope,
  alerts,
  annunciation,
  acknowledged,
  privacy,
}: {
  ready: boolean;
  scope: string;
  alerts: readonly Alert[];
  annunciation: ReadonlyMap<string, string>;
  acknowledged: ReadonlySet<string>;
  privacy: boolean;
}) {
  const state = useRef<AnnouncerState>(INITIAL_ANNOUNCER);
  const nextId = useRef(0);
  const [assertive, setAssertive] = useState<LiveMessage[]>([]);
  const [polite, setPolite] = useState<LiveMessage[]>([]);

  useEffect(() => {
    if (!ready) return;
    const plan = planAnnouncements(state.current, { scope, alerts, annunciation, acknowledged, privacy });
    state.current = plan.state;
    const loud = plan.announce.filter((item) => item.urgency === "assertive").map((item) => item.text);
    const quiet = plan.announce.filter((item) => item.urgency === "polite").map((item) => item.text);
    const loudId = nextId.current;
    const quietId = loudId + loud.length;
    nextId.current = quietId + quiet.length;
    if (plan.entered) {
      setAssertive(appendMessages([], loud, loudId));
      setPolite(appendMessages([], quiet, quietId));
    } else {
      if (loud.length > 0) setAssertive((current) => appendMessages(current, loud, loudId));
      if (quiet.length > 0) setPolite((current) => appendMessages(current, quiet, quietId));
    }
  }, [ready, scope, alerts, annunciation, acknowledged, privacy]);

  return <LiveRegions assertive={assertive} polite={polite} />;
}
